"""Run repeated 50-user load tests from clean, disposable Redis volumes."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from common import distribution, environment_manifest, write_json


REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "infra" / "docker-compose.yml"


def run(args: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=REPO, env=env, check=check, text=True, capture_output=True,
        encoding="utf-8", errors="replace",
    )


def compose(project: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["docker", "compose", "-p", project, "-f", str(COMPOSE), *args], check=check)


def wait_ready(timeout_s: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = "not attempted"
    while time.monotonic() < deadline:
        try:
            response = httpx.get("http://localhost/traces", timeout=3.0)
            response.raise_for_status()
            return
        except Exception as exc:  # readiness diagnostics are retained on failure
            last_error = str(exc)
            time.sleep(1.0)
    raise RuntimeError(f"AgentScope did not become ready: {last_error}")


def parse_quantity(value: str) -> float:
    units = {
        "B": 1, "kB": 1_000, "MB": 1_000_000, "GB": 1_000_000_000,
        "KiB": 1_024, "MiB": 1_048_576, "GiB": 1_073_741_824,
    }
    value = value.strip()
    for unit in sorted(units, key=len, reverse=True):
        if value.endswith(unit):
            return float(value[:-len(unit)].strip()) * units[unit]
    return float(value)


def sample_docker(project: str, stop: threading.Event, rows: list[dict]) -> None:
    while not stop.is_set():
        result = run(
            ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            check=False,
        )
        now = datetime.now(timezone.utc).isoformat()
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
                if not row.get("Name", "").startswith(project + "-"):
                    continue
                memory = row.get("MemUsage", "0B / 0B").split("/")[0]
                net_rx, net_tx = (part.strip() for part in row.get("NetIO", "0B / 0B").split("/"))
                rows.append({
                    "timestamp_utc": now,
                    "container": row["Name"],
                    "cpu_percent": float(row.get("CPUPerc", "0%").rstrip("%")),
                    "memory_bytes": parse_quantity(memory),
                    "network_rx_bytes": parse_quantity(net_rx),
                    "network_tx_bytes": parse_quantity(net_tx),
                })
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
        stop.wait(1.0)


def aggregate_stats(csv_path: Path) -> dict:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    row = next(item for item in rows if item["Name"] == "Aggregated")
    return {
        "requests": int(row["Request Count"]),
        "failures": int(row["Failure Count"]),
        "median_response_time_ms": float(row["Median Response Time"]),
        "average_response_time_ms": float(row["Average Response Time"]),
        "p95_response_time_ms": float(row["95%"]),
        "p99_response_time_ms": float(row["99%"]),
        "requests_per_second": float(row["Requests/s"]),
    }


def aggregate_resources(rows: list[dict]) -> dict:
    containers = {}
    for name in sorted({row["container"] for row in rows}):
        selected = [row for row in rows if row["container"] == name]
        containers[name] = {
            "cpu_percent": distribution([row["cpu_percent"] for row in selected]),
            "peak_memory_bytes": max(row["memory_bytes"] for row in selected),
            "network_rx_delta_bytes": max(row["network_rx_bytes"] for row in selected) - min(row["network_rx_bytes"] for row in selected),
            "network_tx_delta_bytes": max(row["network_tx_bytes"] for row in selected) - min(row["network_tx_bytes"] for row in selected),
        }
    return {"sample_count": len(rows), "containers": containers}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--spawn-rate", type=int, default=10)
    parser.add_argument("--load-duration-seconds", type=int, default=75)
    parser.add_argument("--probe-delay-seconds", type=int, default=7)
    parser.add_argument("--probe-duration-seconds", type=int, default=60)
    parser.add_argument("--probe-samples", type=int, default=300)
    parser.add_argument(
        "--locustfile",
        type=Path,
        default=REPO / "infra" / "loadtest" / "locustfile.py",
        help="Load profile to run; defaults to the mixed ingest/traces/history workload.",
    )
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, AGENTSCOPE_API_KEY="test-key", EVALUATION_ENVIRONMENT="local-docker-clean-volume")
    summaries = []

    for repetition in range(1, args.repetitions + 1):
        project = f"agentscope-load-r{repetition}"
        prefix = args.output_directory / f"load_r{repetition}"
        compose(project, "down", "--volumes", "--remove-orphans", check=False)
        try:
            compose(project, "up", "-d", "--build")
            wait_ready()
            resource_rows: list[dict] = []
            resource_stop = threading.Event()
            resource_thread = threading.Thread(
                target=sample_docker, args=(project, resource_stop, resource_rows), daemon=True
            )
            resource_thread.start()
            with Path(str(prefix) + "_locust.log").open("w", encoding="utf-8") as locust_log:
                locust = subprocess.Popen(
                    [
                        sys.executable, "-m", "locust", "-f", str(args.locustfile),
                        "--headless", "-u", str(args.users), "-r", str(args.spawn_rate),
                        "-t", f"{args.load_duration_seconds}s", "--csv", str(prefix),
                        "--host", "http://localhost",
                    ],
                    cwd=REPO,
                    env=env,
                    stdout=locust_log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                time.sleep(args.probe_delay_seconds)
                probe = run(
                    [
                        sys.executable, str(REPO / "infra" / "loadtest" / "event_latency_probe.py"),
                        "--samples", str(args.probe_samples), "--concurrency", "10",
                        "--duration-seconds", str(args.probe_duration_seconds),
                        "--json-output", str(prefix) + "_event_latency.json",
                    ],
                    env=env,
                )
                locust_code = locust.wait(timeout=args.load_duration_seconds + 45)
            resource_stop.set()
            resource_thread.join(timeout=10)
            probe_json = json.loads(Path(str(prefix) + "_event_latency.json").read_text(encoding="utf-8"))
            write_json(Path(str(prefix) + "_docker_resources.json"), resource_rows)
            summary = {
                "repetition": repetition,
                "project": project,
                "fresh_redis_volume": True,
                "locust_exit_code": locust_code,
                "locust": aggregate_stats(Path(str(prefix) + "_stats.csv")),
                "event_latency": probe_json["latency_ms"],
                "event_completed_samples": probe_json["completed_samples"],
                "event_error_count": probe_json["error_count"],
                "resources": aggregate_resources(resource_rows),
                "probe_stdout": probe.stdout,
            }
            summaries.append(summary)
            write_json(Path(str(prefix) + "_summary.json"), summary)
            print(json.dumps({"completed_repetition": repetition, "summary": summary["locust"], "event_p95_ms": summary["event_latency"]["p95"]}))
        finally:
            compose(project, "down", "--volumes", "--remove-orphans", check=False)

    payload = {
        "study": "repeated_clean_volume_load",
        "manifest": environment_manifest(20260902, " ".join(sys.argv)),
        "design": vars(args),
        "repetitions": summaries,
        "aggregate": {
            "event_p95_ms": distribution([row["event_latency"]["p95"] for row in summaries]),
            "http_p95_ms": distribution([row["locust"]["p95_response_time_ms"] for row in summaries]),
            "requests_per_second": distribution([row["locust"]["requests_per_second"] for row in summaries]),
            "failure_rate": distribution([row["locust"]["failures"] / row["locust"]["requests"] for row in summaries]),
        },
    }
    write_json(args.output_directory / "load_replication_summary.json", payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
