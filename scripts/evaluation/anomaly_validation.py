"""Labeled tuning/held-out validation for AgentScope's six fixed rules."""

from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from common import add_repo_paths, classification_metrics, distribution, environment_manifest, write_json

add_repo_paths()

from agentscope.schema import Span, SpanStatus, TokenUsage
from worker.rules.crashes import CrashRule
from worker.rules.delegation_cycles import DelegationCycleRule
from worker.rules.engine import AnomalyEngine, THRESHOLDS
from worker.rules.failure_loops import FailureLoopRule
from worker.rules.message_storms import MessageStormRule
from worker.rules.timeouts import TimeoutRule
from worker.rules.token_spikes import TokenSpikeRule


SEED = 20260830
RULES = (
    "crashes",
    "failure_loops",
    "timeouts",
    "token_spikes",
    "message_storms",
    "delegation_cycles",
)
BASE = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)


@dataclass
class Scenario:
    scenario_id: str
    target_rule: str
    split: str
    label: bool
    variant: str
    spans: list[Span]
    expected_trigger_index: int | None


def _span(
    scenario_id: str,
    index: int,
    *,
    trace_id: str | None = None,
    agent_id: str = "agent-a",
    parent_span_id: str | None = None,
    span_id: str | None = None,
    span_type: str = "tool_call",
    name: str = "operation",
    input_value: Any = None,
    output: Any = None,
    status: str = "success",
    duration: float = 0.01,
    offset: float | None = None,
    tokens: int | None = None,
) -> Span:
    start = BASE + timedelta(seconds=index if offset is None else offset)
    return Span(
        trace_id=trace_id or f"trace-{scenario_id}",
        span_id=span_id or f"{scenario_id}-span-{index}",
        parent_span_id=parent_span_id,
        span_type=span_type,
        name=name,
        input=input_value if input_value is not None else {"step": index},
        output={"result": index} if output is None else output,
        start_time=start,
        end_time=start + timedelta(seconds=duration),
        status=SpanStatus(status=status, exception_details="synthetic" if status == "error" else None),
        token_usage=TokenUsage(total_tokens=tokens) if tokens is not None else None,
        agent_id=agent_id,
    )


def _case_id(split: str, rule: str, label: bool, index: int) -> str:
    return f"{split}-{rule}-{'pos' if label else 'neg'}-{index:03d}"


def _crash_cases(split: str, count: int) -> list[Scenario]:
    cases = []
    for label in (True, False):
        for index in range(count):
            sid = _case_id(split, "crashes", label, index)
            if label and index % 2 == 0:
                spans = [_span(sid, 0, status="error")]
                variant = "explicit_error"
            elif label:
                spans = [_span(sid, 0, span_type="llm_call", output="")]
                variant = "empty_llm_completion"
            else:
                spans = [_span(sid, 0, span_type="llm_call", output={"text": "answer"})]
                variant = "successful_completion"
            cases.append(Scenario(sid, "crashes", split, label, variant, spans, 0 if label else None))
    return cases


def _timeout_cases(split: str, count: int) -> list[Scenario]:
    cases = []
    positive_durations = [30.001, 31.0, 45.0, 120.0]
    negative_durations = [0.01, 10.0, 29.0, 30.0]
    for label in (True, False):
        for index in range(count):
            sid = _case_id(split, "timeouts", label, index)
            duration = (positive_durations if label else negative_durations)[index % 4]
            cases.append(
                Scenario(
                    sid,
                    "timeouts",
                    split,
                    label,
                    f"duration_{duration}",
                    [_span(sid, 0, duration=duration)],
                    0 if label else None,
                )
            )
    return cases


def _token_cases(split: str, count: int) -> list[Scenario]:
    cases = []
    for label in (True, False):
        for index in range(count):
            sid = _case_id(split, "token_spikes", label, index)
            if label and index % 2 == 0:
                token_counts = [8001 + index]
                variant = "single_call"
            elif label:
                token_counts = [6000, 6000, 6000, 3001]
                variant = "session_rate"
            elif index % 2 == 0:
                token_counts = [8000]
                variant = "single_boundary"
            else:
                token_counts = [5000, 5000, 5000, 5000]
                variant = "session_boundary"
            spans = [_span(sid, step, tokens=tokens) for step, tokens in enumerate(token_counts)]
            cases.append(
                Scenario(sid, "token_spikes", split, label, variant, spans, len(spans) - 1 if label else None)
            )
    return cases


def _storm_cases(split: str, count: int) -> list[Scenario]:
    cases = []
    for label in (True, False):
        for index in range(count):
            sid = _case_id(split, "message_storms", label, index)
            if label:
                size = 21 + index % 5
                offsets = [step * 0.1 for step in range(size)]
                variant = f"burst_{size}"
                trigger = 20
            elif index % 2 == 0:
                size = 20
                offsets = [step * 0.1 for step in range(size)]
                variant = "boundary_20"
                trigger = None
            else:
                size = 21
                offsets = [step * 0.31 for step in range(size)]
                variant = "spread_21"
                trigger = None
            spans = [
                _span(sid, step, offset=offset, name=f"message-{step}", input_value={"unique": step})
                for step, offset in enumerate(offsets)
            ]
            cases.append(Scenario(sid, "message_storms", split, label, variant, spans, trigger))
    return cases


def _loop_cases(split: str, count: int) -> list[Scenario]:
    cases = []
    negative_variants = ("changing_input", "below_count", "outside_window", "cross_trace", "duplicate_versions")
    for label in (True, False):
        for index in range(count):
            sid = _case_id(split, "failure_loops", label, index)
            if label:
                size = 4 + index % 3
                spans = [
                    _span(sid, step, name="retry-tool", input_value={"same": index}) for step in range(size)
                ]
                variant = f"repeated_{size}"
                trigger = 3
            else:
                variant = negative_variants[index % len(negative_variants)]
                trigger = None
                if variant == "changing_input":
                    spans = [
                        _span(sid, step, name="retry-tool", input_value={"step": step}) for step in range(4)
                    ]
                elif variant == "below_count":
                    spans = [
                        _span(sid, step, name="retry-tool", input_value={"same": index}) for step in range(3)
                    ]
                elif variant == "outside_window":
                    spans = [
                        _span(
                            sid,
                            step,
                            name="retry-tool",
                            input_value={"same": index},
                            offset=step * 61.0,
                        )
                        for step in range(4)
                    ]
                elif variant == "cross_trace":
                    spans = [
                        _span(
                            sid,
                            step,
                            trace_id=f"{sid}-trace-{step}",
                            name="retry-tool",
                            input_value={"same": index},
                        )
                        for step in range(4)
                    ]
                else:
                    first = _span(sid, 0, span_id=f"{sid}-call-a", name="retry-tool", input_value={"same": index})
                    second = _span(sid, 1, span_id=f"{sid}-call-b", name="retry-tool", input_value={"same": index})
                    spans = [first.model_copy(update={"end_time": None}), first, second.model_copy(update={"end_time": None}), second]
            cases.append(Scenario(sid, "failure_loops", split, label, variant, spans, trigger))
    return cases


def _cycle_cases(split: str, count: int) -> list[Scenario]:
    cases = []
    for label in (True, False):
        for index in range(count):
            sid = _case_id(split, "delegation_cycles", label, index)
            agents = ["agent-a", "agent-b", "agent-a" if label else "agent-c"]
            spans = []
            parent = None
            for step, agent in enumerate(agents):
                span = _span(
                    sid,
                    step,
                    span_type="delegation",
                    name=f"delegate-{agent}-{step}",
                    agent_id=agent,
                    parent_span_id=parent,
                )
                spans.append(span)
                parent = span.span_id
            cases.append(
                Scenario(
                    sid,
                    "delegation_cycles",
                    split,
                    label,
                    "a_b_a" if label else "a_b_c",
                    spans,
                    2 if label else None,
                )
            )
    return cases


def build_corpus(per_class: int = 50) -> list[Scenario]:
    corpus = []
    builders = (_crash_cases, _loop_cases, _timeout_cases, _token_cases, _storm_cases, _cycle_cases)
    for split in ("tuning", "heldout"):
        for builder in builders:
            corpus.extend(builder(split, per_class))
    random.Random(SEED).shuffle(corpus)
    return corpus


def _factory(rule_name: str, parameters: dict[str, Any] | None = None):
    params = parameters or THRESHOLDS.get(rule_name, {})
    return {
        "crashes": lambda: CrashRule(),
        "failure_loops": lambda: FailureLoopRule(params),
        "timeouts": lambda: TimeoutRule(params),
        "token_spikes": lambda: TokenSpikeRule(params),
        "message_storms": lambda: MessageStormRule(params),
        "delegation_cycles": lambda: DelegationCycleRule(),
    }[rule_name]()


def _evaluate_case(scenario: Scenario, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    rule = _factory(scenario.target_rule, parameters)
    detections = []
    durations = []
    for index, span in enumerate(scenario.spans):
        started = time.perf_counter_ns()
        result = rule.evaluate(span)
        durations.append((time.perf_counter_ns() - started) / 1000.0)
        if result is not None:
            detections.append(index)
    first = detections[0] if detections else None
    predicted = first is not None
    return {
        "scenario_id": scenario.scenario_id,
        "rule": scenario.target_rule,
        "split": scenario.split,
        "label": scenario.label,
        "variant": scenario.variant,
        "span_count": len(scenario.spans),
        "predicted": predicted,
        "first_detection_index": first,
        "expected_trigger_index": scenario.expected_trigger_index,
        "detection_delay_events": (
            first - scenario.expected_trigger_index
            if first is not None and scenario.expected_trigger_index is not None
            else None
        ),
        "evaluation_microseconds": durations,
    }


def _summarize(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(row["label"] and row["predicted"] for row in evaluations)
    fp = sum(not row["label"] and row["predicted"] for row in evaluations)
    fn = sum(row["label"] and not row["predicted"] for row in evaluations)
    tn = sum(not row["label"] and not row["predicted"] for row in evaluations)
    delays = [row["detection_delay_events"] for row in evaluations if row["detection_delay_events"] is not None]
    timings = list(itertools.chain.from_iterable(row["evaluation_microseconds"] for row in evaluations))
    false_positive_variants = Counter(
        row["variant"] for row in evaluations if not row["label"] and row["predicted"]
    )
    return {
        **classification_metrics(tp, fp, fn, tn),
        "scenario_count": len(evaluations),
        "detection_delay_events": distribution(delays),
        "evaluation_microseconds_per_event": distribution(timings),
        "false_positive_variants": dict(false_positive_variants),
    }


def _candidate_grid(rule_name: str) -> list[dict[str, Any]]:
    return {
        "crashes": [{}],
        "failure_loops": [
            {"count": count, "window_seconds": window}
            for count in (3, 4, 5)
            for window in (30, 60, 90)
        ],
        "timeouts": [{"ceiling_seconds": value} for value in (20, 30, 40)],
        "token_spikes": [
            {"single_call": single, "session_rate": session}
            for single in (6000, 8000, 10000)
            for session in (16000, 20000, 24000)
        ],
        "message_storms": [
            {"count": count, "window_seconds": window}
            for count in (10, 20, 30)
            for window in (3, 5, 10)
        ],
        "delegation_cycles": [{}],
    }[rule_name]


def _tune(rule_name: str, cases: list[Scenario]) -> dict[str, Any]:
    candidates = []
    for params in _candidate_grid(rule_name):
        rows = [_evaluate_case(case, params) for case in cases]
        summary = _summarize(rows)
        candidates.append({"parameters": params, "metrics": summary})
    eligible = [item for item in candidates if item["metrics"]["recall"] >= 0.85]
    pool = eligible or candidates
    selected = max(
        pool,
        key=lambda item: (
            item["metrics"]["f1"],
            item["metrics"]["precision"],
            item["metrics"]["recall"],
            item["parameters"] == THRESHOLDS.get(rule_name, {}),
        ),
    )
    return {"selected": selected, "candidate_count": len(candidates), "candidates": candidates}


def _whole_engine_cofiring(cases: list[Scenario]) -> dict[str, Any]:
    pair_counts: Counter[str] = Counter()
    observed_by_target: dict[str, Counter[str]] = {rule: Counter() for rule in RULES}
    scenario_rows = []
    for scenario in cases:
        engine = AnomalyEngine()
        observed: set[str] = set()
        for span in scenario.spans:
            # Active events are evaluated immediately in production. Keep that
            # property in the offline corpus so a fixed historical timestamp
            # cannot manufacture an unrelated timeout co-fire.
            candidate = span
            if span.end_time is None:
                candidate = span.model_copy(update={"start_time": datetime.now(timezone.utc)})
            observed.update(anomaly["rule"] for anomaly in engine.evaluate(candidate))
        for rule in observed:
            observed_by_target[scenario.target_rule][rule] += 1
        for left, right in itertools.combinations(sorted(observed), 2):
            pair_counts[f"{left}|{right}"] += 1
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "target_rule": scenario.target_rule,
                "label": scenario.label,
                "observed_rules": sorted(observed),
            }
        )
    return {
        "pair_counts": dict(pair_counts),
        "observed_rule_counts_by_target": {
            target: dict(counts) for target, counts in observed_by_target.items()
        },
        "scenarios": scenario_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-class", type=int, default=50)
    args = parser.parse_args()

    corpus = build_corpus(args.per_class)
    by_rule = {rule: [case for case in corpus if case.target_rule == rule] for rule in RULES}
    tuning = {}
    heldout = {}
    raw_heldout = {}
    for rule in RULES:
        tuning_cases = [case for case in by_rule[rule] if case.split == "tuning"]
        heldout_cases = [case for case in by_rule[rule] if case.split == "heldout"]
        tuning[rule] = _tune(rule, tuning_cases)
        production_rows = [_evaluate_case(case) for case in heldout_cases]
        selected_params = tuning[rule]["selected"]["parameters"]
        selected_rows = [_evaluate_case(case, selected_params) for case in heldout_cases]
        heldout[rule] = {
            "production_parameters": THRESHOLDS.get(rule, {}),
            "production_metrics": _summarize(production_rows),
            "tuning_selected_parameters": selected_params,
            "selected_metrics": _summarize(selected_rows),
        }
        raw_heldout[rule] = production_rows

    heldout_cases = [case for case in corpus if case.split == "heldout"]
    payload = {
        "study": "labeled_anomaly_rule_validation",
        "manifest": environment_manifest(SEED, " ".join(sys.argv)),
        "design": {
            "rules": list(RULES),
            "per_rule_per_class_per_split": args.per_class,
            "total_scenarios": len(corpus),
            "tuning_scenarios": sum(case.split == "tuning" for case in corpus),
            "heldout_scenarios": sum(case.split == "heldout" for case in corpus),
            "policy": "Tune on tuning split; report production and selected parameters on untouched held-out split.",
        },
        "tuning": tuning,
        "heldout": heldout,
        "heldout_raw": raw_heldout,
        "whole_engine_cofiring": _whole_engine_cofiring(heldout_cases),
    }
    write_json(args.output, payload)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "total_scenarios": len(corpus),
                "production_f1": {
                    rule: heldout[rule]["production_metrics"]["f1"] for rule in RULES
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
