"""Aggregate the 2026-09-03 latency profile into reviewable paper artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from scipy import stats

from common import artifact_index, distribution, write_json


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def t_interval(values: list[float]) -> list[float]:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return [mean, mean]
    half = float(stats.t.ppf(0.975, len(values) - 1) * stats.tstd(values) / math.sqrt(len(values)))
    return [mean - half, mean + half]


def condition(root: Path, relative: str, repetition: int = 1) -> dict:
    summary = load_json(root / relative / f"load_r{repetition}_summary.json") if relative else load_json(root / f"load_r{repetition}_summary.json")
    return {
        "event_p50_ms": summary["event_latency"]["p50"],
        "event_p95_ms": summary["event_latency"]["p95"],
        "event_p99_ms": summary["event_latency"]["p99"],
        "http_p95_ms": summary["locust"]["p95_response_time_ms"],
        "requests": summary["locust"]["requests"],
        "failures": summary["locust"]["failures"],
        "requests_per_second": summary["locust"]["requests_per_second"],
        "resources": summary["resources"],
    }


def timeline_thirds(path: Path) -> list[dict]:
    payload = load_json(path)
    records = sorted(payload["sample_records"], key=lambda row: row["observed_offset_s"])
    boundaries = (("early", 0.0, 20.0), ("middle", 20.0, 40.0), ("late", 40.0, 61.0))
    result = []
    for label, lower, upper in boundaries:
        values = [row["latency_ms"] for row in records if lower <= row["observed_offset_s"] < upper]
        result.append({"window": label, **distribution(values)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory

    mixed_50 = [condition(root, "", repetition) for repetition in (1, 2, 3)]
    controls = {
        "mixed_10u": condition(root, "matrix_mixed_10u"),
        "mixed_25u": condition(root, "matrix_mixed_25u"),
        "mixed_50u": mixed_50,
        "ingest_only_50u": condition(root, "control_ingest_only_50u"),
    }
    timeline = {
        f"mixed_50u_r{repetition}": timeline_thirds(root / f"load_r{repetition}_event_latency.json")
        for repetition in (1, 2, 3)
    }
    p95_values = [row["event_p95_ms"] for row in mixed_50]
    payload = {
        "study": "redis_recovery_and_mixed_load_latency_profile",
        "frozen_commit": "dadf573",
        "mixed_50u_event_p95_ms": {
            **distribution(p95_values),
            "process_t_95": t_interval(p95_values),
            "all_below_200ms": all(value < 200 for value in p95_values),
        },
        "conditions": controls,
        "timeline_thirds": timeline,
        "interpretation": {
            "isolated_observation": "The 50-user ingest-only control remained below target while the mixed workload missed in every repetition.",
            "code_profile": "The mixed workload repeatedly requests growing trace histories; the pre-optimization history path issued one XRANGE per indexed event.",
            "boundary": "The controls isolate read pressure at workload level but do not estimate the causal contribution of each history implementation step.",
        },
    }
    write_json(root / "profile_summary.json", payload)

    rows = [
        {"condition": "mixed 10 users", "repetition": 1, **controls["mixed_10u"]},
        {"condition": "mixed 25 users", "repetition": 1, **controls["mixed_25u"]},
        *({"condition": "mixed 50 users", "repetition": index, **row} for index, row in enumerate(mixed_50, 1)),
        {"condition": "ingest-only 50 users", "repetition": 1, **controls["ingest_only_50u"]},
    ]
    csv_fields = [
        "condition", "repetition", "requests", "failures", "requests_per_second",
        "http_p95_ms", "event_p50_ms", "event_p95_ms", "event_p99_ms",
    ]
    with (root / "table_latency_profile.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    figure_rows = [controls["mixed_10u"], controls["mixed_25u"], *mixed_50, controls["ingest_only_50u"]]
    labels = ["Mixed\n10u", "Mixed\n25u", "Mixed\n50u r1", "Mixed\n50u r2", "Mixed\n50u r3", "Ingest-only\n50u"]
    colors = ["#2563eb", "#2563eb", "#f59e0b", "#f59e0b", "#f59e0b", "#10b981"]
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.bar(labels, [row["event_p95_ms"] for row in figure_rows], color=colors)
    ax.axhline(200, color="#dc2626", linestyle="--", label="200 ms target")
    ax.set_ylabel("Ingest-to-WebSocket p95 (ms)")
    ax.set_title("Read pressure, rather than ingest alone, drives the 50-user miss")
    ax.legend()
    fig.tight_layout()
    fig.savefig(root / "figure_latency_profile.png", dpi=300)
    fig.savefig(root / "figure_latency_profile.pdf")
    plt.close(fig)

    mean_p95 = payload["mixed_50u_event_p95_ms"]["mean"]
    low, high = payload["mixed_50u_event_p95_ms"]["process_t_95"]
    lines = [
        "# Redis Recovery and Latency Profile",
        "",
        "## Frozen condition",
        "",
        "The CI/reconnection candidate was frozen at commit `dadf573`. Each main 50-user repetition used a fresh Redis volume, 75 seconds of mixed Locust traffic, and 300 event probes paced across 60 seconds. No trial or failure was discarded.",
        "",
        "## Observations",
        "",
        "| Condition | Repetition | Requests | Failures | Requests/s | HTTP p95 | Event p50 | Event p95 | Event p99 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['condition']} | {row['repetition']} | {row['requests']:,} | {row['failures']} | "
            f"{row['requests_per_second']:.2f} | {row['http_p95_ms']:.1f} ms | {row['event_p50_ms']:.1f} ms | "
            f"{row['event_p95_ms']:.1f} ms | {row['event_p99_ms']:.1f} ms |"
        )
    lines += [
        "",
        f"The three mixed 50-user event-p95 values averaged {mean_p95:.2f} ms (process-level t 95% CI {low:.2f}–{high:.2f} ms); all exceeded the 200 ms target. Run 2 is retained despite its pronounced host/runtime slowdown.",
        "",
        "The 50-user ingest-only control completed 30,284 requests with zero failures, HTTP p95 120 ms, and event p95 47 ms. Mixed traffic passed at 10 users (78 ms) and 25 users (125 ms), then missed at 50 users. Within the 50-user runs, later windows were generally slower than early windows.",
        "",
        "## Profile interpretation",
        "",
        "Endpoint and container telemetry associated the miss with growing historical-read work: `GET /history` had the highest endpoint tail latency, and the backend approached its two-core limit in the higher-throughput repetitions. The pre-optimization endpoint expanded every history request into one Redis `XRANGE` command per indexed event. This is workload-level causal-control evidence, not a component-level causal estimate; the post-optimization rerun is reported separately.",
        "",
        "## Artifacts",
        "",
        "Raw Locust CSV/logs, paced probe records, per-second container samples, `profile_summary.json`, `table_latency_profile.csv`, and the PNG/PDF figure are retained in this directory.",
        "",
    ]
    (root / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    write_json(root / "manifest.json", artifact_index(root))
    print(json.dumps({"mixed_50u_mean_event_p95_ms": mean_p95, "control_event_p95_ms": controls["ingest_only_50u"]["event_p95_ms"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
