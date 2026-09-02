"""Generate publication tables, confidence intervals, figures, and narrative."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

from common import artifact_index, distribution, write_json


ARMS = ("agentscope", "langfuse", "phoenix")
LABELS = {"agentscope": "AgentScope", "langfuse": "Langfuse", "phoenix": "Phoenix"}
WORKLOADS = ("cpu_trivial", "llm_bound_100ms_per_node")
WORKLOAD_LABELS = {"cpu_trivial": "CPU-trivial", "llm_bound_100ms_per_node": "100 ms/node"}
COLORS = {"agentscope": "#2563eb", "langfuse": "#f59e0b", "phoenix": "#10b981"}


def t_summary(values: list[float]) -> dict:
    n = len(values)
    mean = sum(values) / n
    sd = stats.tstd(values) if n > 1 else 0.0
    half = stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        **distribution(values),
        "sd": float(sd),
        "mean_t_95": [float(mean - half), float(mean + half)],
        "raw_process_means": values,
    }


def comparison_rows(directory: Path) -> list[dict]:
    rows = []
    for arm in ARMS:
        for repetition in range(1, 4):
            path = directory / f"comparison_{arm}_r{repetition}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload["verified_ingestion"]["delta"] < payload["verified_ingestion"]["expected_delta"]:
                raise RuntimeError(f"Incomplete ingestion in {path}")
            common = {
                "arm": arm,
                "product": LABELS[arm],
                "repetition": repetition,
                "trace_delta": payload["verified_ingestion"]["delta"],
                "visibility_ms": payload["verified_ingestion"]["visibility_wait_after_final_flush_ms"],
                "process_cpu_seconds": payload["resource_observation"]["process_cpu_seconds"],
                "peak_rss_mb": payload["resource_observation"]["process_peak_rss_bytes"] / 1_000_000,
                "host_network_mb": (
                    payload["resource_observation"]["host_network_bytes_sent"]
                    + payload["resource_observation"]["host_network_bytes_received"]
                ) / 1_000_000,
                "query_p95_ms": payload["trace_catalog_query_latency_ms"]["p95"],
            }
            for configuration in payload["configurations"]:
                rows.append({
                    **common,
                    "workload": configuration["label"],
                    "overhead_percent": configuration["paired_overhead_percent"]["mean"],
                    "absolute_delta_ms": configuration["paired_difference_ms"]["mean"],
                    "baseline_mean_ms": configuration["baseline_ms"]["mean"],
                    "instrumented_mean_ms": configuration["instrumented_ms"]["mean"],
                })
    return rows


def load_rows(directory: Path) -> list[dict]:
    payload = json.loads((directory / "load_replication_summary.json").read_text(encoding="utf-8"))
    return [
        {
            "repetition": row["repetition"],
            "requests": row["locust"]["requests"],
            "failures": row["locust"]["failures"],
            "requests_per_second": row["locust"]["requests_per_second"],
            "http_p95_ms": row["locust"]["p95_response_time_ms"],
            "event_p50_ms": row["event_latency"]["p50"],
            "event_p95_ms": row["event_latency"]["p95"],
            "event_p99_ms": row["event_latency"]["p99"],
            "event_samples": row["event_completed_samples"],
            "event_errors": row["event_error_count"],
            "meets_event_p95_target": row["event_latency"]["p95"] < 200.0,
        }
        for row in payload["repetitions"]
    ]


def aggregate_comparison(rows: list[dict]) -> list[dict]:
    result = []
    for arm in ARMS:
        for workload in WORKLOADS:
            selected = [row for row in rows if row["arm"] == arm and row["workload"] == workload]
            result.append({
                "arm": arm,
                "product": LABELS[arm],
                "workload": workload,
                "workload_label": WORKLOAD_LABELS[workload],
                "process_repetitions": len(selected),
                "measured_pairs_total": 30 * len(selected),
                "overhead_percent": t_summary([row["overhead_percent"] for row in selected]),
                "absolute_delta_ms": t_summary([row["absolute_delta_ms"] for row in selected]),
                "baseline_mean_ms": t_summary([row["baseline_mean_ms"] for row in selected]),
                "instrumented_mean_ms": t_summary([row["instrumented_mean_ms"] for row in selected]),
            })
    return result


def aggregate_resources(rows: list[dict]) -> list[dict]:
    result = []
    unique = {(row["arm"], row["repetition"]): row for row in rows}.values()
    for arm in ARMS:
        selected = [row for row in unique if row["arm"] == arm]
        result.append({
            "arm": arm,
            "product": LABELS[arm],
            "process_repetitions": len(selected),
            "process_cpu_seconds": t_summary([row["process_cpu_seconds"] for row in selected]),
            "peak_rss_mb": t_summary([row["peak_rss_mb"] for row in selected]),
            "host_network_mb": t_summary([row["host_network_mb"] for row in selected]),
            "visibility_ms": t_summary([row["visibility_ms"] for row in selected]),
            "query_p95_ms": t_summary([row["query_p95_ms"] for row in selected]),
            "verified_traces": sum(row["trace_delta"] for row in selected),
        })
    return result


def save_tables(directory: Path, load: list[dict], comparison: list[dict], resources: list[dict]) -> None:
    pd.DataFrame(load).to_csv(directory / "table_load_replications.csv", index=False)
    comparison_flat = []
    for row in comparison:
        comparison_flat.append({
            "product": row["product"], "workload": row["workload_label"],
            "process_repetitions": row["process_repetitions"],
            "measured_pairs_total": row["measured_pairs_total"],
            "mean_overhead_percent": row["overhead_percent"]["mean"],
            "overhead_t95_low": row["overhead_percent"]["mean_t_95"][0],
            "overhead_t95_high": row["overhead_percent"]["mean_t_95"][1],
            "mean_absolute_delta_ms": row["absolute_delta_ms"]["mean"],
            "absolute_delta_t95_low": row["absolute_delta_ms"]["mean_t_95"][0],
            "absolute_delta_t95_high": row["absolute_delta_ms"]["mean_t_95"][1],
        })
    pd.DataFrame(comparison_flat).to_csv(directory / "table_three_way_summary.csv", index=False)
    resource_flat = []
    for row in resources:
        resource_flat.append({
            "product": row["product"], "process_repetitions": row["process_repetitions"],
            "mean_process_cpu_seconds": row["process_cpu_seconds"]["mean"],
            "mean_peak_rss_mb": row["peak_rss_mb"]["mean"],
            "mean_host_network_mb": row["host_network_mb"]["mean"],
            "mean_visibility_ms": row["visibility_ms"]["mean"],
            "mean_query_p95_ms": row["query_p95_ms"]["mean"],
            "verified_traces": row["verified_traces"],
        })
    pd.DataFrame(resource_flat).to_csv(directory / "table_resource_and_visibility_summary.csv", index=False)


def save_figures(directory: Path, load: list[dict], comparison: list[dict], resources: list[dict]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    reps = [row["repetition"] for row in load]
    ax.plot(reps, [row["event_p95_ms"] for row in load], marker="o", linewidth=2, label="Ingest-to-WebSocket p95")
    ax.plot(reps, [row["http_p95_ms"] for row in load], marker="s", linewidth=2, label="Mixed HTTP p95")
    ax.axhline(200, color="#dc2626", linestyle="--", linewidth=1.5, label="200 ms event target")
    ax.set(xlabel="Fresh-volume repetition", ylabel="Latency (ms)", xticks=reps)
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(directory / "figure_load_latency.png", dpi=300)
    fig.savefig(directory / "figure_load_latency.pdf")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4))
    for ax, workload in zip(axes, WORKLOADS):
        selected = [row for row in comparison if row["workload"] == workload]
        for index, row in enumerate(selected):
            mean = row["overhead_percent"]["mean"]
            low, high = row["overhead_percent"]["mean_t_95"]
            ax.bar(index, mean, color=COLORS[row["arm"]], alpha=0.75)
            ax.errorbar(index, mean, yerr=[[mean - low], [high - mean]], fmt="none", color="black", capsize=4)
            ax.scatter([index - 0.12, index, index + 0.12], row["overhead_percent"]["raw_process_means"], color="black", s=20, zorder=3)
        ax.set_title(WORKLOAD_LABELS[workload])
        ax.set_xticks(range(3), [LABELS[arm] for arm in ARMS], rotation=15)
        ax.set_ylabel("Mean paired overhead (%)")
        if workload == "llm_bound_100ms_per_node":
            ax.axhline(5, color="#dc2626", linestyle="--", linewidth=1.2, label="5% target")
            ax.legend()
    fig.suptitle("Fresh-process overhead means with process-level t 95% CIs (n=3)")
    fig.tight_layout()
    fig.savefig(directory / "figure_three_way_overhead.png", dpi=300)
    fig.savefig(directory / "figure_three_way_overhead.pdf")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.2))
    products = [row["product"] for row in resources]
    axes[0].bar(products, [row["visibility_ms"]["mean"] for row in resources], color=[COLORS[a] for a in ARMS])
    axes[0].set_ylabel("Post-flush visibility wait (ms)")
    axes[0].set_title("Trace visibility")
    axes[1].bar(products, [row["query_p95_ms"]["mean"] for row in resources], color=[COLORS[a] for a in ARMS])
    axes[1].set_ylabel("Trace-catalog query p95 (ms)")
    axes[1].set_title("Product-native query latency")
    for ax in axes:
        ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(directory / "figure_visibility_and_query.png", dpi=300)
    fig.savefig(directory / "figure_visibility_and_query.pdf")
    plt.close(fig)


def interval_text(metric: dict, digits: int = 2) -> str:
    low, high = metric["mean_t_95"]
    return f"{metric['mean']:.{digits}f} ({low:.{digits}f} to {high:.{digits}f})"


def save_results(directory: Path, load: list[dict], comparison: list[dict], resources: list[dict]) -> None:
    load_event = t_summary([row["event_p95_ms"] for row in load])
    load_http = t_summary([row["http_p95_ms"] for row in load])
    load_rps = t_summary([row["requests_per_second"] for row in load])
    lines = [
        "# Replicated Post-Fix Evaluation",
        "",
        "## Observation protocol",
        "",
        "The frozen implementation candidate is commit `80ae5b6`. The load protocol used three independent 75-second, 50-user Locust runs, each from a newly created Redis volume. A 300-sample ingest-to-WebSocket probe was evenly scheduled across 60 seconds of each loaded interval. The three-way comparison used three fresh Python processes and fresh product storage stacks per product, 30 measured paired invocations per workload after five warm-ups, no outlier removal, and exact pinned container images.",
        "",
        "Uncertainty below is a two-sided Student t 95% confidence interval over the three independent process/run means. With only three repetitions these intervals are low-powered and can be very wide. Within-process bootstrap intervals remain in the raw JSON but are not substituted for process-level replication.",
        "",
        "## Loaded latency and reliability",
        "",
        "| Repetition | Requests | Failures | Requests/s | HTTP p95 (ms) | Event p50 (ms) | Event p95 (ms) | Event p99 (ms) | Event samples/errors |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in load:
        lines.append(f"| {row['repetition']} | {row['requests']:,} | {row['failures']} | {row['requests_per_second']:.2f} | {row['http_p95_ms']:.1f} | {row['event_p50_ms']:.2f} | {row['event_p95_ms']:.2f} | {row['event_p99_ms']:.2f} | {row['event_samples']}/{row['event_errors']} |")
    lines += [
        "",
        f"Mean event p95 was {interval_text(load_event)} ms; all three run-level values exceeded the 200 ms target. Mean mixed-HTTP p95 was {interval_text(load_http)} ms and mean throughput was {interval_text(load_rps)} requests/s. Across {sum(r['requests'] for r in load):,} requests and 900 event probes, the recorded HTTP and probe error counts were both zero.",
        "",
        "The earlier one-run 78 ms p95 observation is therefore not reproducible under this longer whole-window protocol and must not support a general under-load target claim.",
        "",
        "## Three-way execution overhead",
        "",
        "| Product | Workload | Process reps | Paired trials | Mean overhead %, t 95% CI | Mean absolute delta ms, t 95% CI |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in comparison:
        lines.append(f"| {row['product']} | {row['workload_label']} | {row['process_repetitions']} | {row['measured_pairs_total']} | {interval_text(row['overhead_percent'])} | {interval_text(row['absolute_delta_ms'], 3)} |")
    lines += [
        "",
        "The CPU-trivial percentage is unstable because millisecond-scale absolute costs divide by a very small baseline; it should not be treated as representative of LLM-dominated systems. The 100 ms/node results are the more interpretable overhead condition. Run-to-run intervals overlap substantially, so these three repetitions do not establish a reliable product ranking.",
        "",
        "## Resource, visibility, and query observations",
        "",
        "| Product | Process CPU s | Peak process RSS MB | Host network MB | Post-flush visibility ms | Native query p95 ms | Verified traces |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in resources:
        lines.append(f"| {row['product']} | {row['process_cpu_seconds']['mean']:.2f} | {row['peak_rss_mb']['mean']:.1f} | {row['host_network_mb']['mean']:.3f} | {row['visibility_ms']['mean']:.2f} | {row['query_p95_ms']['mean']:.2f} | {row['verified_traces']} |")
    lines += [
        "",
        "CPU and RSS cover only the comparison Python process, not each product's server containers. Network values use host-wide counters and can include unrelated traffic. Query measurements use each product's native trace-catalog/count endpoint, whose semantics and storage paths differ; they are operational observations, not an apples-to-apples query benchmark. Post-flush visibility is batch-level time from exporter flush completion until all 70 expected traces were query-visible, not per-trace end-to-end latency.",
        "",
        "## Claim boundary",
        "",
        "The evidence supports exact ingestion completeness (210/210 expected traces per product across three fresh processes) and reports measured local overhead, resources, visibility, query latency, and loaded event latency. It does not establish production generalization, overall product superiority, server-side resource efficiency, or causality for the observed performance differences.",
        "",
        "## Generated artifacts",
        "",
        "- `table_load_replications.csv`",
        "- `table_three_way_summary.csv`",
        "- `table_resource_and_visibility_summary.csv`",
        "- `figure_load_latency.png` and `.pdf`",
        "- `figure_three_way_overhead.png` and `.pdf`",
        "- `figure_visibility_and_query.png` and `.pdf`",
        "- `aggregate_results.json` and `manifest.json`",
        "",
    ]
    (directory / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    comparison_raw = comparison_rows(args.directory)
    load = load_rows(args.directory)
    comparison = aggregate_comparison(comparison_raw)
    resources = aggregate_resources(comparison_raw)
    payload = {
        "study": "replicated_post_fix_load_and_three_way_comparison",
        "inference_unit": "independent clean-stack/process repetition",
        "process_repetitions_per_condition": 3,
        "load": {"runs": load, "event_p95_ms": t_summary([row["event_p95_ms"] for row in load])},
        "comparison": comparison,
        "resources_visibility_query": resources,
        "limitations": [
            "Only three independent repetitions per condition; process-level intervals are low-powered.",
            "Comparison CPU/RSS exclude product server containers.",
            "Network counters are host-wide and not OS-isolated.",
            "Product-native query endpoints are not semantically identical.",
        ],
    }
    write_json(args.directory / "aggregate_results.json", payload)
    save_tables(args.directory, load, comparison, resources)
    save_figures(args.directory, load, comparison, resources)
    save_results(args.directory, load, comparison, resources)
    write_json(args.directory / "manifest.json", artifact_index(args.directory))
    print(json.dumps({
        "event_p95_mean_ms": payload["load"]["event_p95_ms"]["mean"],
        "all_load_runs_meet_200ms": all(row["meets_event_p95_target"] for row in load),
        "verified_traces_per_product": {row["product"]: row["verified_traces"] for row in resources},
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
