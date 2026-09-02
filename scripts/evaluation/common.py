"""Shared helpers for versioned, machine-readable evaluation artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]


def percentile(values: Sequence[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] * (1 - fraction) + ordered[upper] * fraction)


def distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "p99": None}
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "min": min(values),
        "max": max(values),
    }


def bootstrap_mean_ci(
    values: Sequence[float], *, seed: int = 20260830, samples: int = 10_000
) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        means.append(sum(rng.choice(values) for _ in values) / len(values))
    return [percentile(means, 2.5), percentile(means, 97.5)]


def wilson_interval(successes: int, total: int, z: float = 1.96) -> list[float] | None:
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return [(centre - margin) / denominator, (centre + margin) / denominator]


def classification_metrics(tp: int, fp: int, fn: int, tn: int) -> dict[str, Any]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "precision_wilson_95": wilson_interval(tp, tp + fp),
        "recall": recall,
        "recall_wilson_95": wilson_interval(tp, tp + fn),
        "specificity": specificity,
        "f1": f1,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_text(args: list[str]) -> str | None:
    try:
        return subprocess.run(
            args,
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def environment_manifest(seed: int, command: str) -> dict[str, Any]:
    package_names = ["pydantic", "httpx", "openai", "anthropic", "websockets", "locust"]
    packages: dict[str, str | None] = {}
    try:
        from importlib.metadata import PackageNotFoundError, version

        for name in package_names:
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = None
    except ImportError:
        packages = {name: None for name in package_names}

    status = _run_text(["git", "status", "--porcelain"])
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "seed": seed,
        "git_commit": _run_text(["git", "rev-parse", "HEAD"]),
        "git_branch": _run_text(["git", "branch", "--show-current"]),
        "git_worktree_dirty": bool(status),
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "packages": packages,
        "docker": _run_text(["docker", "--version"]),
    }


def artifact_index(directory: Path) -> dict[str, Any]:
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            files.append(
                {
                    "path": path.relative_to(directory).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return {"files": files}


def add_repo_paths() -> None:
    for path in (REPO_ROOT, REPO_ROOT / "sdk"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized) if materialized else 0.0
