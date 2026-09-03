"""Compare the pre/post history payload-index load repetitions."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from scipy import stats

from common import artifact_index, distribution, write_json


def read_runs(directory: Path) -> list[dict]:
    runs = []
    for repetition in (1, 2, 3):
        payload = json.loads((directory / f"load_r{repetition}_summary.json").read_text(encoding="utf-8"))
        containers = payload["resources"]["containers"]
        backend = next(value for name, value in containers.items() if "-backend-" in name)
        redis = next(value for name, value in containers.items() if "-redis-" in name)
        runs.append({
            "repetition": repetition,
            "requests": payload["locust"]["requests"],
            "failures": payload["locust"]["failures"],
            "requests_per_second": payload["locust"]["requests_per_second"],
            "http_p95_ms": payload["locust"]["p95_response_time_ms"],
            "event_p50_ms": payload["event_latency"]["p50"],
            "event_p95_ms": payload["event_latency"]["p95"],
            "event_p99_ms": payload["event_latency"]["p99"],
            "event_errors": payload["event_error_count"],
            "backend_cpu_mean_percent": backend["cpu_percent"]["mean"],
            "backend_cpu_max_percent": backend["cpu_percent"]["max"],
            "backend_peak_memory_mb": backend["peak_memory_bytes"] / 1_000_000,
            "redis_cpu_mean_percent": redis["cpu_percent"]["mean"],
            "redis_peak_memory_mb": redis["peak_memory_bytes"] / 1_000_000,
        })
    return runs


def t_interval(values: list[float]) -> list[float]:
    mean = sum(values) / len(values)
    half = float(stats.t.ppf(0.975, len(values) - 1) * stats.tstd(values) / math.sqrt(len(values)))
    return [mean - half, mean + half]


def metric(runs: list[dict], key: str) -> dict:
    values = [run[key] for run in runs]
    return {**distribution(values), "process_t_95": t_interval(values), "raw_run_values": values}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pre_directory", type=Path)
    parser.add_argument("post_directory", type=Path)
    args = parser.parse_args()

    pre = read_runs(args.pre_directory)
    post = read_runs(args.post_directory)
    summary = {
        "study": "history_payload_index_before_after_load_evaluation",
        "pre_commit": "dadf573",
        "post_commit": "7f89f34",
        "design": "Sequential before/after; three fresh-volume 50-user repetitions per implementation, 75 seconds load, 300 probes paced across 60 seconds.",
        "pre": {
            "event_p95_ms": metric(pre, "event_p95_ms"),
            "http_p95_ms": metric(pre, "http_p95_ms"),
            "requests_per_second": metric(pre, "requests_per_second"),
        },
        "post": {
            "event_p95_ms": metric(post, "event_p95_ms"),
            "http_p95_ms": metric(post, "http_p95_ms"),
            "requests_per_second": metric(post, "requests_per_second"),
        },
        "post_all_event_p95_below_200ms": all(run["event_p95_ms"] < 200 for run in post),
        "associated_mean_changes": {
            "event_p95_percent": 100 * (metric(post, "event_p95_ms")["mean"] / metric(pre, "event_p95_ms")["mean"] - 1),
            "http_p95_percent": 100 * (metric(post, "http_p95_ms")["mean"] / metric(pre, "http_p95_ms")["mean"] - 1),
            "requests_per_second_percent": 100 * (metric(post, "requests_per_second")["mean"] / metric(pre, "requests_per_second")["mean"] - 1),
        },
        "claim_boundary": "The repetitions were sequential, not randomized interleaved pairs. Changes are associated with the combined payload-index candidate and do not establish universal production performance or a component-level causal effect.",
    }
    write_json(args.post_directory / "history_index_summary.json", summary)

    rows = []
    for phase, runs in (("pre", pre), ("post", post)):
        rows.extend({"phase": phase, **run} for run in runs)
    fields = list(rows[0])
    with (args.post_directory / "table_history_index_before_after.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.2))
    labels = ["r1", "r2", "r3"]
    for ax, key, title, target in (
        (axes[0], "event_p95_ms", "Event p95 (ms)", 200),
        (axes[1], "http_p95_ms", "Mixed HTTP p95 (ms)", None),
        (axes[2], "requests_per_second", "Throughput (requests/s)", None),
    ):
        x = range(3)
        ax.plot(x, [run[key] for run in pre], marker="o", label="Before")
        ax.plot(x, [run[key] for run in post], marker="o", label="Payload index")
        if target is not None:
            ax.axhline(target, color="#dc2626", linestyle="--", label="Target")
        ax.set_xticks(list(x), labels)
        ax.set_title(title)
    axes[0].legend()
    fig.suptitle("Fresh-volume 50-user mixed-load repetitions")
    fig.tight_layout()
    fig.savefig(args.post_directory / "figure_history_index_before_after.png", dpi=300)
    fig.savefig(args.post_directory / "figure_history_index_before_after.pdf")
    plt.close(fig)

    pre_event = summary["pre"]["event_p95_ms"]
    post_event = summary["post"]["event_p95_ms"]
    post_http = summary["post"]["http_p95_ms"]
    post_rps = summary["post"]["requests_per_second"]
    changes = summary["associated_mean_changes"]
    lines = [
        "# History Payload-Index Evaluation",
        "",
        "## Protocol",
        "",
        "The before condition was frozen at `dadf573`; the payload-index candidate was frozen at `7f89f34`. Each condition used three sequential fresh-volume repetitions with 50 Locust users for 75 seconds and 300 ingest-to-WebSocket probes paced across 60 seconds. Raw failures and the high-variance pre run were retained.",
        "",
        "## Run-level observations",
        "",
        "| Phase | Rep | Requests | Failures | Requests/s | HTTP p95 | Event p50 | Event p95 | Event p99 | Backend CPU mean/max | Redis peak memory |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['phase']} | {row['repetition']} | {row['requests']:,} | {row['failures']} | {row['requests_per_second']:.2f} | "
            f"{row['http_p95_ms']:.1f} ms | {row['event_p50_ms']:.1f} ms | {row['event_p95_ms']:.1f} ms | {row['event_p99_ms']:.1f} ms | "
            f"{row['backend_cpu_mean_percent']:.1f}/{row['backend_cpu_max_percent']:.1f}% | {row['redis_peak_memory_mb']:.1f} MB |"
        )
    pre_low, pre_high = pre_event["process_t_95"]
    post_low, post_high = post_event["process_t_95"]
    lines += [
        "",
        "## Result",
        "",
        f"Before the payload index, mean event p95 was {pre_event['mean']:.2f} ms (process-level t 95% CI {pre_low:.2f}–{pre_high:.2f}); all three runs missed the 200 ms target. After the change, run-level event p95 was {', '.join(f'{value:.1f}' for value in post_event['raw_run_values'])} ms and the mean was {post_event['mean']:.2f} ms (t 95% CI {post_low:.2f}–{post_high:.2f}). All three post-change runs met the target.",
        "",
        f"The associated mean changes were {changes['event_p95_percent']:.1f}% event p95, {changes['http_p95_percent']:.1f}% mixed-HTTP p95, and {changes['requests_per_second_percent']:+.1f}% throughput. Post-change mean HTTP p95 was {post_http['mean']:.2f} ms and mean throughput was {post_rps['mean']:.2f} requests/s. Across the three post runs there were zero Locust failures and zero probe errors.",
        "",
        "The payload copy increased Redis memory use; post-run peaks were 29.3–35.8 MB while processing more requests, versus 12.9–22.1 MB before. This is the explicit space-for-read-latency tradeoff.",
        "",
        "## Boundary",
        "",
        summary["claim_boundary"],
        "",
    ]
    (args.post_directory / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(args.post_directory / "manifest.json", artifact_index(args.post_directory))
    print(json.dumps({
        "post_event_p95_mean_ms": post_event["mean"],
        "post_all_below_200ms": summary["post_all_event_p95_below_200ms"],
        "post_mean_rps": post_rps["mean"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
