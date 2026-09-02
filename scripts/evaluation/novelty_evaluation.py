"""Evaluate delegation-aware context and privacy-preserving loop detection.

This runner is deliberately independent of any multi-agent framework: it uses
only AgentScope's ``@trace`` decorator and ordinary Python callables/tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from common import add_repo_paths, distribution, environment_manifest, write_json

add_repo_paths()

from agentscope.config import reset_redaction_config, set_redaction_enabled
from agentscope.context import get_execution_context
from agentscope.schema import Span, SpanStatus
from agentscope.sender import _prepare_span_for_send, sender
from agentscope.trace import trace
from worker.rules.failure_loops import FailureLoopRule


SEED = 20260830


def _latest(spans: list[Span]) -> list[Span]:
    by_id: dict[str, Span] = {}
    for span in spans:
        by_id[span.span_id] = span
    return list(by_id.values())


def _validate_chain(spans: list[Span], prefix: str, depth: int) -> dict[str, Any]:
    completed = _latest([span for span in spans if span.name.startswith(prefix)])
    by_name = {span.name: span for span in completed}
    expected_names = [f"{prefix}-agent-{index}" for index in range(depth)] + [f"{prefix}-leaf"]
    edge_checks = []
    owner_checks = []
    chain_checks = []
    hop_checks = []
    trace_ids = {by_name[name].trace_id for name in expected_names if name in by_name}

    for index, name in enumerate(expected_names):
        if name not in by_name:
            continue
        span = by_name[name]
        expected_owner = f"{prefix}-agent-{min(index, depth - 1)}"
        expected_chain = [f"{prefix}-agent-{hop}" for hop in range(min(index + 1, depth))]
        owner_checks.append(span.agent_id == expected_owner)
        chain_checks.append(span.delegation_chain == expected_chain)
        hop_checks.append(span.hop_number == max(len(expected_chain) - 1, 0))
        if index == 0:
            edge_checks.append(span.parent_span_id is None)
        else:
            edge_checks.append(span.parent_span_id == by_name[expected_names[index - 1]].span_id)

    total_expected = len(expected_names)
    return {
        "prefix": prefix,
        "depth": depth,
        "expected_span_count": total_expected,
        "observed_span_count": len(completed),
        "single_trace": len(trace_ids) == 1,
        "parent_edge_accuracy": sum(edge_checks) / total_expected if total_expected else 1.0,
        "agent_owner_accuracy": sum(owner_checks) / total_expected if total_expected else 1.0,
        "delegation_chain_accuracy": sum(chain_checks) / total_expected if total_expected else 1.0,
        "hop_number_accuracy": sum(hop_checks) / total_expected if total_expected else 1.0,
        "passed": (
            len(completed) == total_expected
            and len(trace_ids) == 1
            and all(edge_checks)
            and all(owner_checks)
            and all(chain_checks)
            and all(hop_checks)
        ),
    }


def _make_sync_chain(depth: int, prefix: str) -> Callable[[], str]:
    @trace(f"{prefix}-leaf", span_type="tool_call")
    def leaf() -> str:
        return "ok"

    function: Callable[[], str] = leaf
    for index in reversed(range(depth)):
        child = function

        @trace(f"{prefix}-agent-{index}", span_type="delegation", agent_id=f"{prefix}-agent-{index}")
        def level(child: Callable[[], str] = child) -> str:
            return child()

        function = level
    return function


def _make_async_chain(depth: int, prefix: str, gate: asyncio.Event | None = None):
    @trace(f"{prefix}-leaf", span_type="tool_call")
    async def leaf() -> str:
        if gate is not None:
            await gate.wait()
        await asyncio.sleep(0)
        return "ok"

    function = leaf
    for index in reversed(range(depth)):
        child = function

        @trace(f"{prefix}-agent-{index}", span_type="delegation", agent_id=f"{prefix}-agent-{index}")
        async def level(child=child) -> str:
            await asyncio.sleep(0)
            return await child()

        function = level
    return function


async def _delegation_evaluation() -> dict[str, Any]:
    captured: list[Span] = []
    original_send = sender.send
    sender.send = captured.append
    scenarios: list[dict[str, Any]] = []
    try:
        for depth in (1, 2, 5, 10):
            prefix = f"sync-d{depth}"
            _make_sync_chain(depth, prefix)()
            scenarios.append(_validate_chain(captured, prefix, depth))

        for depth in (2, 5, 10):
            prefix = f"async-d{depth}"
            await _make_async_chain(depth, prefix)()
            scenarios.append(_validate_chain(captured, prefix, depth))

        concurrent_prefixes = [f"concurrent-{index:03d}" for index in range(100)]
        await asyncio.gather(*[_make_async_chain(3, prefix)() for prefix in concurrent_prefixes])
        concurrent = [_validate_chain(captured, prefix, 3) for prefix in concurrent_prefixes]

        @trace("exception-root", span_type="delegation", agent_id="exception-root")
        def raises() -> None:
            raise RuntimeError("intentional evaluation exception")

        try:
            raises()
        except RuntimeError:
            pass
        restored_after_exception = get_execution_context("fallback-agent", "fallback-trace")

        gate = asyncio.Event()
        cancelled_task = asyncio.create_task(_make_async_chain(2, "cancel", gate)())
        await asyncio.sleep(0)
        cancelled_task.cancel()
        try:
            await cancelled_task
        except asyncio.CancelledError:
            pass
        restored_after_cancel = get_execution_context("fallback-agent", "fallback-trace")
    finally:
        sender.send = original_send

    all_results = scenarios + concurrent
    return {
        "integration": "framework-free @trace adapter",
        "scenario_count": len(all_results),
        "sequential_scenarios": scenarios,
        "concurrency": {
            "task_count": len(concurrent),
            "passed_count": sum(result["passed"] for result in concurrent),
            "cross_task_context_leaks": sum(not result["passed"] for result in concurrent),
        },
        "context_restoration": {
            "after_exception": restored_after_exception.__dict__,
            "after_exception_passed": (
                restored_after_exception.trace_id == "fallback-trace"
                and restored_after_exception.parent_span_id is None
                and restored_after_exception.agent_id == "fallback-agent"
                and restored_after_exception.delegation_chain == ()
            ),
            "after_cancellation": restored_after_cancel.__dict__,
            "after_cancellation_passed": (
                restored_after_cancel.trace_id == "fallback-trace"
                and restored_after_cancel.parent_span_id is None
                and restored_after_cancel.agent_id == "fallback-agent"
                and restored_after_cancel.delegation_chain == ()
            ),
        },
        "overall_passed": all(result["passed"] for result in all_results),
    }


def _loop_span(input_value: Any, index: int, *, fingerprint: str | None = None) -> Span:
    start = datetime(2026, 8, 30, tzinfo=timezone.utc) + timedelta(seconds=index)
    return Span(
        trace_id="privacy-sequence",
        span_id=f"span-{index}",
        parent_span_id=None,
        span_type="tool_call",
        name="protected-tool",
        input=input_value,
        output={"ok": True},
        start_time=start,
        end_time=start + timedelta(milliseconds=1),
        status=SpanStatus(status="success"),
        agent_id="privacy-agent",
        progress_fingerprint=fingerprint,
    )


def _mode_sequence(values: list[Any], mode: str) -> bool:
    rule = FailureLoopRule({"count": 4, "window_seconds": 60})
    detected = False
    for index, value in enumerate(values):
        raw = _loop_span(value, index)
        if mode == "full_capture":
            candidate = raw
        elif mode == "literal_redaction":
            candidate = raw.model_copy(update={"input": "[REDACTED]", "output": "[REDACTED]"})
        elif mode == "hmac_redaction":
            candidate = _prepare_span_for_send(raw)
        else:
            raise ValueError(mode)
        detected = rule.evaluate(candidate) is not None or detected
    return detected


def _privacy_ablation() -> dict[str, Any]:
    set_redaction_enabled(True)
    try:
        cases = []
        for index in range(100):
            repeated = [{"secret": f"repeat-{index}", "step": 1}] * 4
            changing = [{"secret": f"change-{index}-{step}", "step": step} for step in range(4)]
            cases.extend([("repeated", True, repeated), ("changing", False, changing)])

        modes: dict[str, Any] = {}
        full_predictions: list[bool] = []
        for mode in ("full_capture", "literal_redaction", "hmac_redaction"):
            tp = fp = fn = tn = 0
            predictions = []
            for _, expected, values in cases:
                predicted = _mode_sequence(values, mode)
                predictions.append(predicted)
                if expected and predicted:
                    tp += 1
                elif expected:
                    fn += 1
                elif predicted:
                    fp += 1
                else:
                    tn += 1
            if mode == "full_capture":
                full_predictions = predictions
            modes[mode] = {
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "tn": tn,
                "accuracy": (tp + tn) / len(cases),
                "agreement_with_full_capture": (
                    1.0
                    if mode == "full_capture"
                    else sum(a == b for a, b in zip(predictions, full_predictions)) / len(cases)
                ),
            }

        sentinel = "AGENTSCOPE-SECRET-SENTINEL-9f6bd4"
        output_sentinel = "AGENTSCOPE-OUTPUT-SENTINEL-3cb7a1"
        secret_span = _prepare_span_for_send(
            _loop_span({"credential": sentinel}, 0).model_copy(
                update={"output": {"private_result": output_sentinel}}
            )
        )
        serialized = secret_span.model_dump_json()

        sizes = (128, 4096, 65536, 1048576)
        timings = {}
        for size in sizes:
            iterations = 1000 if size <= 4096 else 200 if size <= 65536 else 25
            raw = _loop_span({"payload": "x" * size}, 0)
            samples = []
            for _ in range(iterations):
                started = time.perf_counter_ns()
                _prepare_span_for_send(raw)
                samples.append((time.perf_counter_ns() - started) / 1000.0)
            timings[str(size)] = {"iterations": iterations, "microseconds": distribution(samples)}

        from agentscope import privacy

        first = privacy.compute_progress_fingerprint({"value": "same-secret"})
        original_key = privacy._HMAC_KEY
        privacy._HMAC_KEY = b"evaluation-restart-key".ljust(32, b"0")
        try:
            after_restart = privacy.compute_progress_fingerprint({"value": "same-secret"})
        finally:
            privacy._HMAC_KEY = original_key

        return {
            "case_count": len(cases),
            "class_balance": {"positive": 100, "negative": 100},
            "modes": modes,
            "wire_leak_scan": {
                "sentinel_present": sentinel in serialized,
                "raw_input_present": "credential" in serialized,
                "raw_output_present": output_sentinel in serialized,
                "fingerprint_present": bool(secret_span.progress_fingerprint),
                "fingerprint_length_hex": len(secret_span.progress_fingerprint or ""),
                "passed": (
                    sentinel not in serialized
                    and "credential" not in serialized
                    and output_sentinel not in serialized
                    and "private_result" not in serialized
                ),
            },
            "restart_semantics": {
                "same_value_different_process_key_differs": first != after_restart,
                "scope": "fingerprints are comparable only within one SDK process lifetime",
            },
            "redaction_preparation_cost": timings,
        }
    finally:
        reset_redaction_config()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = {
        "study": "delegation_context_and_privacy_ablation",
        "manifest": environment_manifest(SEED, " ".join(sys.argv)),
        "delegation_context": await _delegation_evaluation(),
        "privacy_ablation": _privacy_ablation(),
    }
    write_json(args.output, payload)
    print(json.dumps({"output": str(args.output), "passed": payload["delegation_context"]["overall_passed"]}))
    return 0 if payload["delegation_context"]["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
