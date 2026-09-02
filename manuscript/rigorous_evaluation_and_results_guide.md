# Rigorous Evaluation, Observation, and Results Guide

**Purpose:** A concrete plan for testing AgentScope rigorously and turning the resulting evidence into a defensible Evaluation/Results section. This guide extends PRD §10 and Build Plan §7; it does not report new measurements.

**Evidence rule:** A passing unit test establishes behavior for its fixtures. It does not establish production accuracy, low overhead, low latency, security in all environments, or usability. Every numerical claim in the final paper must point to a raw artifact, run manifest, code revision, and analysis script.

## 1. Start With Research Questions, Not Test Counts

Use a small set of research questions (RQs) to organize both experiments and the final paper.

| RQ | Question | Primary outcome |
|---|---|---|
| RQ1 — Capture fidelity | Does AgentScope reconstruct the correct trace tree, owning agent, delegation chain, and hop number across supported integration paths and concurrency patterns? | Exact graph/metadata agreement with ground truth |
| RQ2 — Detection quality | How accurately and how quickly do the six deterministic rules identify their intended failures without co-firing on valid progress? | Precision, recall, F1, false positives per 1,000 spans, detection delay |
| RQ3 — Privacy-preserving utility | Does redaction prevent protected content/key leakage while preserving the Failure Loops rule's same-versus-changed discrimination? | Leakage count = 0; classification agreement with full capture |
| RQ4 — Live performance | How quickly do accepted spans and anomaly flags become visible, and how does latency scale with load and trace complexity? | p50/p95/p99 ingest-to-WS and trigger-to-alert latency |
| RQ5 — Host overhead | What execution-time, CPU, memory, and network cost does instrumentation add in CPU-trivial and LLM-bound workloads? | Paired absolute/relative overhead with confidence intervals |
| RQ6 — Reliability | Does SDK/backend/worker/dashboard failure affect the monitored agent, accepted-event durability, order, or recovery time? | Host success rate, lost/duplicate/reordered events, recovery time |
| RQ7 — Diagnostic usefulness | Can unfamiliar observers identify the failure, locate supporting evidence, and explain an appropriate next action? | Task success, time, errors, confidence, qualitative themes |
| RQ8 — Comparative position | Under matched workloads and resources, how does AgentScope differ from Langfuse and Phoenix in setup effort, visibility delay, diagnostic evidence, and overhead? | Matched comparison; no forced equivalence where a feature is absent |

### Pre-register hypotheses and decision rules

Before collecting the final dataset, write one directional or non-directional hypothesis per RQ and define what counts as success. Examples:

- H1: every supported custom-agent scenario has 100% parent-edge, owning-agent, chain, and hop agreement with the workload's generated ground truth.
- H2: each rule meets the PRD targets of at least 90% precision and 85% recall on a held-out labeled corpus after threshold selection on a separate tuning corpus.
- H3: redacted and full-capture modes produce identical Failure Loops classifications for same-versus-changed progress sequences, while protected raw values and HMAC key material occur zero times in captured wire bytes and service logs.
- H4: event-to-dashboard p95 remains below the PRD's 200 ms target in the declared reference-load condition. Other load points are reported without silently extending the target.
- H5: SDK overhead remains below 5% only for the declared LLM-bound workload class; CPU-trivial results are reported separately.

Do not choose thresholds, workload labels, exclusions, or statistical tests after seeing final-test outcomes. Use a tuning/validation split and keep all misses.

## 2. Freeze a Reproducible Evaluation Build

Every final experiment directory should contain a machine-readable manifest with:

- Git commit and dirty-worktree status.
- Date/time/time zone and experiment ID.
- OS, CPU model/core count, RAM, storage type, Python/Node/Docker versions.
- Exact package lockfiles and container image digests, not only tags such as `latest`.
- Docker Compose configuration, worker count, Redis persistence configuration, resource limits, and network topology.
- Model/provider/version, temperature, seed where supported, and whether calls are real, replayed, or simulated.
- Capture mode, SDK configuration, retry settings, detector thresholds, and HMAC process lifecycle.
- Workload name/version, concurrency, trace depth/fan-out, span count, payload size, and trial count.
- Clock source and whether the load generator runs on the same host.
- Raw artifact paths and SHA-256 hashes.

Create separate immutable directories for `pilot`, `tuning`, and `final`. Pilot data may reveal bugs and tune procedures; it must not be mixed into the final inferential dataset.

## 3. Build a Ground-Truth Workload Corpus

The present harness demonstrates that rules can trigger, but it is not yet a rigorous accuracy corpus. Build a generator that emits a ground-truth record alongside every span sequence:

```text
scenario_id, seed, intended_rule, expected_trigger_span,
expected_trigger_time, expected_graph_edges, expected_agent_by_span,
expected_delegation_chain_by_span, expected_hop_by_span,
protected_values_present, near_boundary_case, notes
```

Use at least three independent scenario families:

1. **Hand-crafted minimal cases** isolate one rule and one edge condition.
2. **Parameterized synthetic cases** vary counts, timings, depth, payloads, and concurrency over many seeds.
3. **Realistic multi-agent cases** use the LangGraph, custom framework-free, and support-triage applications with deterministic/replayed LLM responses for repeatability; a separate real-LLM robustness set measures ecological variability.

Split scenarios by template, not merely by random seed, so the held-out set contains structurally different workflows. Otherwise the test set may be a near-duplicate of tuning data.

### Required negative controls

For every positive failure, create a semantically close non-failure:

- Failure loop: repeated call name with changing input/progress; repeated input outside the window; count one below threshold; same values under a different agent; redacted same and redacted changing inputs.
- Crash: handled error represented as successful recovery; expected null output; non-error status with diagnostic text; a parent completing after a recovered child error.
- Timeout: exactly below, exactly at, and exactly above the ceiling; active span without `end_time`; clock-skewed/invalid timestamps rejected at schema or ingest boundary.
- Token spike: threshold −1, threshold, threshold +1; prompt-heavy and completion-heavy cases; cumulative session usage across multiple traces must not be conflated.
- Message storm: short burst above instantaneous rate but below required duration; sustained rate at threshold; multiple independent traces whose aggregate traffic must not become a per-trace false positive unless the rule is intentionally global.
- Delegation cycle: repeated tool names without repeated agent; siblings sharing an agent; valid return to a coordinator after child completion; true A→B→A and longer A→B→C→A cycles; concurrent traces reusing the same agent names.

## 4. RQ1 — Capture and Graph-Fidelity Testing

### Scenario matrix

Cross the following factors instead of testing one happy path:

| Factor | Levels |
|---|---|
| Integration path | LangGraph callback; custom decorator only; decorator + OpenAI patch; decorator + Anthropic patch |
| Execution style | Sync; async sequential; `asyncio.gather`; cancellation; exception propagation |
| Topology | Linear; branching; nested delegation; fan-out/fan-in; re-entrant same agent; genuine cycle |
| Depth | 1, 2, 5, 10, and a stress depth selected below Python/runtime limits |
| Concurrency | 1, 10, 50, 100 independent traces |
| Capture mode | Full capture; redacted |
| Patch location | Inside traced delegation; inside non-delegation span; outside any trace |
| Failure timing | Before child; inside child; inside patched LLM call; cancellation during await |

Also test thread/executor boundaries. Python `contextvars` propagate across asyncio tasks but not every arbitrary thread/process boundary automatically. Record the expected behavior; if cross-thread propagation is unsupported, report it as a limitation rather than silently accepting broken graphs.

### Ground-truth metrics

For every run, compare emitted spans against the generator's expected graph:

- Span capture recall = expected spans observed / expected spans.
- Unexpected-span rate = extra spans / observed spans.
- Parent-edge precision and recall.
- Root-count correctness (normally exactly one root per trace).
- Trace-ID consistency within a run and separation across concurrent runs.
- Owning-agent accuracy.
- Exact delegation-chain match rate.
- Hop-number exact match rate and mean absolute error.
- Start/completion pairing rate for span updates.
- Duplicate completion rate.
- Live/history final-state parity.

The existing 2026-08-23 observation that live WebSocket state missed two completion updates while history held the durable final state must become an explicit regression scenario. Send bursts of active/completed updates for the same span, then assert that the dashboard's eventual live state converges to replay state after queue drain/reconnect.

### Novelty-specific ablation

Evaluate the same custom A→B→LLM workloads under:

- Current shared delegation context.
- A controlled ablation that omits context inheritance at the patch boundary.
- Explicit manual identity threading as an upper-bound/reference implementation.

Do not mutate production code for the ablation. Use a test-only adapter or a reproducible historical revision. Report graph/owner accuracy and instrumentation effort (lines or call sites changed), not vague claims of convenience.

## 5. RQ2 — Six-Rule Detection Validation

### Dataset construction

Use separate tuning and final-validation sets. The final set should include balanced positive/negative cases for analysis plus a prevalence-weighted mixed stream resembling expected use; balanced data estimates sensitivity cleanly, while prevalence-weighted data estimates operational alert burden.

For each rule report:

- TP, FP, TN, FN and the full confusion matrix.
- Precision, recall/sensitivity, specificity, F1, and balanced accuracy.
- Exact 95% confidence intervals (Wilson or bootstrap, named explicitly).
- False positives per 1,000 spans and per trace.
- Detection delay from the first moment the rule condition becomes true to anomaly persistence and dashboard visibility.
- Duplicate-alert count per incident.
- Cross-rule co-firing matrix.

Macro-average metrics across rules, but never replace per-rule results with only a macro average. A weak rule must remain visible.

### Threshold sweeps

Sweep the provisional thresholds on tuning data:

- Failure Loops: count × time window.
- Timeout: ceiling seconds.
- Token Spikes: single-call and session-rate thresholds separately.
- Message Storms: event count × sustained window.

Plot precision-recall or false-positive/recall trade-offs. Select thresholds using a declared objective tied to user cost—for example, maximize F1 subject to recall ≥85%—then freeze them before final validation. Crashes and delegation cycles need logical-case coverage rather than arbitrary numeric tuning.

### Temporal and state isolation

Run mixed interleaved traces and ensure rule state is isolated by the intended key. Test:

- Identical agents in different traces.
- Multiple agents in one trace.
- Out-of-window history pruning.
- Duplicate active/completed versions of the same span.
- Worker restart midway through a detector window.
- Redis replay/catch-up without double-counting.
- Long-running evaluation for state growth/memory leakage.

The current Failure Loops history is keyed by `agent_id`; rigorous testing should determine whether identical agent IDs across independent traces can contaminate each other. Diagnose and report the behavior before deciding whether any code change is warranted.

## 6. RQ3 — Privacy-Preserving Loop Detection

### Functional equivalence tests

Create labeled sequences in full-capture and redacted modes:

- Same protected input repeated.
- Different protected input on every retry.
- Semantically identical dictionaries with different key order.
- Unicode normalization variants.
- Nested lists/dictionaries, numeric types, booleans, empty input, and `None`.
- Non-JSON objects handled through the current `repr` fallback.

Measure detector classification agreement between modes. The key result is not merely “fingerprints differ”; it is that redaction preserves the intended loop/no-loop decision.

### Leakage tests

Use high-entropy sentinel strings and scan all observable boundaries:

- Serialized HTTP request bytes.
- Redis event/anomaly streams.
- Backend, worker, Nginx, and SDK logs at all configured levels.
- Dashboard network responses and rendered DOM.
- Exception messages and retry warnings.
- Exported benchmark/test artifacts.

Assert zero occurrences of raw input/output, literal key bytes, key text encodings, and key hex/base64 forms. Capture traffic at the loopback/network boundary when possible, not only the object passed to an HTTP mock.

### Security interpretation

Report exactly what the design guarantees:

- The raw value and key are not transmitted by the tested paths.
- Equal inputs within one SDK process yield equal fingerprints, intentionally revealing equality to the server-side detector.
- Fingerprints are not stable across process restarts because the key is process-local.
- Truncation to 128 bits gives a low accidental-collision probability for the tested scale but does not prove zero collisions.
- HMAC protects against offline guessing by a party without the key; this should not be described as mathematical “non-reversibility” without qualification.

Test restart behavior explicitly: identical protected values on opposite sides of a process restart should normally have different fingerprints. Confirm whether this can split a loop window and report it as a limitation.

### Fingerprint ablation

Compare:

- Full capture, old input-based signature.
- Redaction with the literal `[REDACTED]` only.
- Redaction with the HMAC fingerprint.

On a corpus containing both stuck retries and changing retries, show how literal-only redaction changes FP/FN counts and how the HMAC path restores agreement with full capture. This is the strongest direct evaluation of the new privacy contribution.

## 7. RQ4 — End-to-End Latency and Scalability

### Measure distinct latency intervals

Do not collapse all delays into one number:

1. SDK enqueue time on the host thread.
2. Span creation/end to successful `/ingest` acceptance.
3. Ingest acceptance to span arrival on WebSocket.
4. Detector condition becoming true to anomaly persistence.
5. Anomaly persistence to dashboard arrival.
6. End-to-end condition-to-visible-alert latency.
7. Historical-query response time by trace size and total store size.

The existing probe measures interval 3. Add correlated IDs/timestamps for intervals 4–6, which are more directly tied to the revised novelty claim.

### Load matrix

Run at least:

- Concurrency: 1, 10, 25, 50, 100, then increase until saturation is observed.
- Traffic mix: ingest-only; ingest + live WS; ingest + history; mixed production-like ratio.
- Trace sizes: 10, 100, 1,000 spans.
- Payload sizes: small metadata, typical captured content, maximum allowed request.
- WebSocket clients: 0, 1, 10, 50; normal and slow/non-reading.
- Backend workers: 1 and reference configuration.
- Capture modes: full and redacted, because HMAC/canonicalization adds client cost.

Use fixed-duration steady-state windows after warmup, repeat each cell on at least three separate runs, and preserve every failure/timeout. Report throughput, error rate, p50/p95/p99/max, queue depth, CPU, memory, Redis stream growth, and saturation point. A percentile without sample count and error rate is incomplete.

If generator and system share one host, measure and disclose resource contention. Prefer a separate load-generator host for final claims. Synchronize clocks or compute each latency interval on one clock domain.

### Re-run requirement after the 2026-08-27 changes

The recorded 156 ms p95 result predates delegation-chain fields and redaction fingerprints. It remains valid evidence for that earlier revision, but final-paper performance claims about the current build should rerun the latency/load suite with the new schema in both capture modes.

## 8. RQ5 — SDK Overhead

### Improve the paired design

Retain paired identical workloads, but counterbalance order rather than always running baseline before instrumented:

- Randomly assign AB or BA within each pair.
- Use warmups and report them separately.
- Pin or record CPU power mode and background utilization.
- Run enough pairs based on a pilot variance/power calculation; do not choose sample size only because 30 is conventional.
- Report paired absolute differences and paired relative differences with bootstrap 95% confidence intervals.
- Include median, interquartile range, standard deviation, min/max, and the raw pair plot.

### Workload classes

Measure:

- CPU-trivial graph (instrumentation-dominated lower bound).
- Simulated LLM-bound graph at several delays, not just 100 ms.
- Real API workload, reported separately because network/model variance is large.
- Custom decorator-only and decorator+patch paths.
- LangGraph path.
- Full capture versus redacted HMAC mode.
- Increasing span counts/depth/fan-out.

Record wall time, host CPU time, peak RSS, allocations if feasible, bytes sent, queue depth, and drain time. Microbenchmark `_canonical_bytes`/HMAC cost by payload size, but never substitute the microbenchmark for end-to-end overhead.

The existing +3.3–3.6 ms absolute result and Phoenix comparison predate the new mechanisms. Re-run them for the final build; report the old data only as development history if the new data supersede it.

## 9. RQ6 — Resilience, Durability, and Ordering

Use controlled fault schedules while continuously ingesting uniquely numbered events:

- Kill/restart anomaly worker at 25%, 50%, and 75% of a run.
- Kill/restart backend workers.
- Restart Redis with AOF enabled; separately test abrupt container termination.
- Stop Nginx/network path while the host agent continues.
- Drop, delay, duplicate, or reorder network packets using a fault proxy where available.
- Connect slow and disconnected WebSocket clients.
- Exhaust sender queue/backoff scenarios.
- Fill disk or enforce a small Redis memory limit in an isolated test environment.
- Send malformed/oversized payloads and invalid credentials under load.

Measure:

- Monitored-agent completion and output correctness.
- Accepted, persisted, processed, streamed, duplicated, and missing event IDs.
- Arrival-order violations.
- Worker catch-up time and duplicate anomaly flags.
- Backend recovery time and transient error duration.
- Sender warning count and queue drain/drop count.
- Live/history convergence after reconnect.

Define “zero data loss” carefully: events rejected while Redis is unavailable are not accepted events. Report accepted-event durability separately from attempted-event delivery.

## 10. RQ7 — Security and Abuse Testing

Beyond the existing 401/TLS checks, test:

- Missing, malformed, expired/rotated, and wrong API keys.
- Timing/rate behavior for repeated authentication failures.
- TLS protocol/cipher configuration and certificate validation in the deployment environment.
- WebSocket access-control expectations; document endpoints that are intentionally unauthenticated.
- Oversized and deeply nested JSON, unexpected types, NaN/infinite values, and timestamp abuse.
- HTML/script strings in names, inputs, outputs, and exception details to detect stored/reflected XSS in the dashboard.
- Redis/Nginx/backend ports are not unintentionally exposed by Compose/cloud firewall rules.
- Secrets are absent from images, Git history, logs, client bundles, and error responses.
- Redaction behavior on retries, serialization failures, and malformed objects.

Use dependency and container-image scans as supporting evidence, but distinguish “no known vulnerability found by tool X on date Y” from “secure.” Arrange an independent manual review if the paper makes a security contribution claim.

## 11. RQ7 — Usability and Diagnostic Comprehension

The prepared one-observer session is useful as a formative case study, not a generalizable usability result. For a paper-quality comparison:

### Participants

- Recruit participants unfamiliar with AgentScope but representative of developers/research engineers.
- Determine sample size through a pilot and power analysis for the primary quantitative outcome.
- Record relevant experience (Python, multi-agent systems, tracing tools) without collecting unnecessary personal data.
- Obtain consent and institutional/departmental approval if required.

### Study design

Use a within-subject, counterbalanced design comparing AgentScope with a defined baseline such as raw logs or the trace view of one established platform. Randomize tool order and scenario order to reduce learning effects. Use distinct but difficulty-matched failures for each condition.

Tasks should cover:

- Identify whether a failure occurred.
- Identify the affected agent/tool.
- Classify the failure type.
- Reconstruct the delegation path.
- Locate supporting evidence.
- State an appropriate human next action without implying AgentScope auto-remediates.

Measure task success, time to correct diagnosis, wrong-node clicks, hints needed, confidence, and a validated usability questionnaire such as SUS. Add NASA-TLX only if workload is a research question; avoid survey accumulation without analytic purpose. Record screens and think-aloud comments with consent, then code qualitative themes using at least two reviewers or report single-coder limitations.

### Observer neutrality

Do not tell participants which rule will fire. Use a standardized briefing, prohibit leading prompts before the primary response, and predefine scoring rubrics. If the observer fails, that is a result.

## 12. RQ8 — Fair Comparative Evaluation

Compare AgentScope with both Langfuse and Phoenix because current documentation shows meaningful overlap.

### Match what can be matched

- Same host or equivalent resource limits.
- Same Python version, application workload, model responses, concurrency, and payload capture policy.
- Same warmup/trial count and randomized execution order.
- Verified export/ingestion for every tool.
- Document batching, sampling, flushing, and exporter configuration.
- Self-host all systems where possible; otherwise separate deployment/network differences from tool differences.

### Outcomes

- Integration effort: changed call sites, configuration steps, and setup time under a defined protocol.
- Capture fidelity: expected spans/edges/agent ownership.
- Time to first visible span and complete graph.
- Time from known failure condition to visible diagnostic evidence.
- Availability and specificity of failure evidence.
- Instrumentation overhead and resource usage.
- Live/history parity and trace-query latency.

Do not assign a synthetic detector to a baseline and then claim the product has that feature. If Langfuse/Phoenix lacks an equivalent built-in per-trace rule, state “no matched built-in condition in the evaluated configuration” and compare trace visibility separately. Conversely, do not ignore their evaluations, dashboards, OTel interoperability, or richer platform features simply because AgentScope does not implement them.

### Qualitative feature matrix

Every feature cell must be one of:

- Verified in a running experiment.
- Documented by the official source, with version/access date.
- Not found in the reviewed documentation.
- Not tested.

Never convert “not found” into “does not exist.”

## 13. Statistical Analysis Plan

- Preserve raw trial-level data; never report only aggregates.
- Report sample size for every result and define the unit of analysis (span, trace, trial, or participant).
- Use bootstrap confidence intervals for skewed latency/overhead distributions.
- Use paired tests for paired workloads (paired t-test only if assumptions are reasonable; otherwise Wilcoxon signed-rank) and report an effect size such as paired standardized difference or rank-biserial correlation.
- For categorical detection outcomes, report exact/binomial intervals and compare paired classifiers with McNemar's test where appropriate.
- Correct for multiple comparisons if many hypotheses are tested; name the method.
- Report practical effect sizes and uncertainty, not only p-values.
- Do not remove outliers unless the exclusion rule was defined before analysis; report analyses with and without exclusions if exclusions are scientifically justified.
- Treat repeated spans from one trace as clustered observations. Use trace-level aggregation or a clustered/hierarchical analysis instead of pretending all spans are independent.
- Publish analysis scripts that regenerate every table and figure from raw artifacts.

## 14. Evidence Already Available vs. Still Required

| Area | Current evidence | What it supports | What is still missing |
|---|---|---|---|
| Delegation context | SDK 30/30; nested custom A→B→LLM and async isolation tests | Functional correctness for covered fixtures | Large graph-fidelity matrix, cancellation/thread cases, live/history convergence, ablation |
| Privacy fingerprint | Same/different input and wire-serialization tests | Covered HMAC equality and sentinel non-leakage behavior | Full boundary capture, mode-equivalence corpus, restart semantics, overhead by payload size |
| Detection | Hand-crafted harness and four poison/four happy demo observations | Rules can trigger on selected cases | Held-out labeled corpus, threshold sweep, per-rule precision/recall/F1, co-fire analysis |
| Latency | 156 ms p95 at 50 users, n=300, older build | Earlier build met the declared event-to-dashboard target in one local condition | Current-build rerun, trigger-to-alert latency, repetitions/CIs, saturation curve |
| Overhead | +3.3–3.6 ms absolute; Phoenix baseline, older build | Earlier-build local paired results | Current-build rerun, counterbalanced order, custom path, redaction/HMAC, resource use |
| Resilience | Backend/worker/Redis/slow-WS scenarios | Strong local evidence for tested faults | Longer soak, duplicates/order, queue exhaustion, disk/memory pressure, live convergence |
| Security | API-key rejection, local TLS, wire redaction | Tested local boundary behavior | Deployment exposure, XSS/payload abuse, secret scan, independent review |
| Accessibility | axe 0 violations, Lighthouse a11y 100, keyboard tests | Automated checks for tested UI | Human assistive-technology evaluation and current-build rerun |
| Usability | Prepared protocol only | No outcome claim | Actual participants, counterbalanced study, recorded/scored results |
| Comparative | Phoenix overhead only | One performance comparison | Langfuse run; graph/detection delay and diagnostic-quality comparison |
| Deployment | Local Compose only | Local self-hosting | AWS/reference cloud deployment if the final paper claims it |

## 15. How to Record Observations Properly

An observation is what occurred; a result is the analyzed pattern; a discussion explains why it matters. Keep them separate.

### Per-run observation log

Use one row per trial:

| Field | Example form |
|---|---|
| Experiment/run ID | `rq2-loop-final-s042-r03` |
| Timestamp and commit | ISO time + Git SHA |
| Planned condition | rule, threshold, load, capture mode |
| Expected outcome | trigger/no trigger; expected span |
| Observed raw outcome | response codes, event IDs, anomaly IDs, timings |
| Deviations | restart, warning, model/provider error, operator mistake |
| Inclusion decision | include/exclude with predeclared rule |
| Artifact links/hashes | raw JSONL, logs, packet capture, screenshot |
| Observer note | factual description, not interpretation |

Good observation: “At 50 users, run 3 produced 298 matched WebSocket samples; two probes timed out after 10 s and remain counted as failures.”

Weak observation: “Performance was good under heavy load.”

Good observation: “The fourth identical protected input generated the same fingerprint as attempts 1–3 and the Failure Loops rule emitted one flag; four changing protected inputs generated four fingerprints and no loop flag.”

Weak observation: “HMAC fixed privacy.”

### Incident/deviation log

Maintain a second chronological log for every unexpected event. Never silently rerun and discard a bad trial. Classify it after collection as system failure, harness failure, environmental failure, or operator error, using a predeclared rule.

### Screenshots and qualitative evidence

Screenshots illustrate UI state but do not replace event logs. Pair every screenshot with trace/span/anomaly IDs, capture time, scenario ID, and the raw JSON that produced it.

## 16. Recommended Results-Section Structure

### 16.1 Experimental setup

State the frozen build, hardware/software, topology, workloads, trial counts, seeds, thresholds, baselines, capture modes, and statistical methods. Distinguish simulated from real LLM calls and local from cloud deployment.

### 16.2 Capture fidelity (RQ1)

Present graph/owner/chain/hop metrics by integration path and topology. Include one failure case if any. A useful figure is expected versus observed graph fidelity across depth/concurrency; a useful table reports edge recall, owner accuracy, chain exact match, and live/history convergence.

### 16.3 Rule quality and detection delay (RQ2)

Provide one confusion-matrix row per rule, threshold selected on tuning data, final held-out metrics with 95% CIs, false alerts per 1,000 spans, and median/p95 detection delay. Add a cross-rule co-firing heatmap so correlated alerts are visible.

### 16.4 Privacy-preserving utility (RQ3)

Report leakage scans, full-versus-redacted classification agreement, fingerprint restart behavior, and the three-arm ablation. Explicitly discuss equality leakage and process-lifetime scope.

### 16.5 Latency and scalability (RQ4)

Plot p50/p95/p99 and error rate against concurrency. Report condition-to-dashboard-alert latency separately from ingest-to-WebSocket span latency. Mark the 200 ms target visually, but do not omit conditions that miss it.

### 16.6 Host overhead (RQ5)

Show paired trial distributions and confidence intervals for each workload/path/mode. Report absolute milliseconds beside percentages so CPU-trivial workloads are not misleading.

### 16.7 Reliability and security (RQ6)

Use a fault-outcome table with attempted/accepted/persisted/processed/streamed counts, recovery time, duplicates, order violations, and host completion. Follow with the privacy/auth/TLS/abuse-test outcomes and clearly bounded claims.

### 16.8 Diagnostic usefulness (RQ7)

Report participant characteristics in aggregate, task success, diagnosis time, hints, confidence/SUS, and coded themes with representative short quotations where consent and venue rules allow. If only one observer is available, call it a formative case study and avoid percentages suggesting population validity.

### 16.9 Comparative evaluation (RQ8)

Separate verified quantitative comparisons from documentation-derived features. Include tool versions/configurations and disclose unmatched capabilities. Avoid a single “winner” score that hides fundamentally different scopes.

### 16.10 Threats to validity and limitations

At minimum discuss:

- Synthetic versus real workloads.
- Single-host/local deployment and absent AWS evidence.
- Limited frameworks/providers and Python-only custom path.
- Custom non-OTel/OpenInference schema and no W3C cross-service propagation.
- Deterministic rules cover known signatures, not silent semantic failures.
- Process-local fingerprint discontinuity and equality leakage.
- Threshold dependence and dataset representativeness.
- Potential observer learning and small usability sample.
- Rapidly evolving comparison platforms and version sensitivity.

## 17. Table and Figure Templates

### Per-rule final validation

| Rule | Threshold | Pos/Neg traces | TP | FP | FN | TN | Precision [95% CI] | Recall [95% CI] | F1 | FP/1k spans | Detection delay p50/p95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Failure Loops | [frozen value] | [TBD] | | | | | | | | | |
| Crashes | logical | [TBD] | | | | | | | | | |
| Timeouts | [frozen value] | [TBD] | | | | | | | | | |
| Token Spikes | [frozen values] | [TBD] | | | | | | | | | |
| Message Storms | [frozen values] | [TBD] | | | | | | | | | |
| Delegation Cycles | logical | [TBD] | | | | | | | | | |

### Graph fidelity

| Path/topology | Traces | Span recall | Edge precision | Edge recall | Owner accuracy | Chain exact match | Hop exact match | Live/history convergence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LangGraph—branching | | | | | | | | |
| Custom—nested sync | | | | | | | | |
| Custom—nested async | | | | | | | | |
| Custom—concurrent | | | | | | | | |

### Privacy ablation

| Mode | Raw leakage count | Key leakage count | Loop precision | Loop recall | Agreement with full capture | SDK cost |
|---|---:|---:|---:|---:|---:|---:|
| Full capture | N/A | N/A | | | reference | |
| Literal redaction only | 0 | N/A | | | | |
| HMAC redaction | 0 | 0 | | | | |

### Fault injection

| Fault | Attempted | Accepted | Persisted | Processed | Streamed | Lost accepted | Duplicates | Order violations | Recovery | Host result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Worker kill | | | | | | | | | | |
| Redis restart | | | | | | | | | | |
| Backend outage | | | | | | | | | | |
| Slow WebSocket | | | | | | | | | | |

Recommended figures:

1. Architecture/evaluation points diagram.
2. Threshold precision-recall curves per tunable rule.
3. Detection-delay distributions per rule.
4. Event-to-alert latency versus concurrency with error-rate overlay.
5. Paired overhead plots by workload and capture mode.
6. Full/redacted/fingerprint ablation confusion matrices.
7. Cross-rule co-firing heatmap.
8. Participant diagnosis-time/task-success plot if the sample supports it.

## 18. Writing the Results Without Overclaiming

Use a four-part pattern for each finding:

1. **Protocol:** what was measured, where, and how many trials.
2. **Observation:** exact values with uncertainty and failures.
3. **Result:** whether the preregistered criterion was met.
4. **Boundary:** what the evidence does not establish.

Example:

> Across [n] held-out custom-agent traces spanning depths [x–y] and concurrency [a–b], AgentScope reconstructed [value]% of expected parent edges (95% CI [..]) and assigned the correct owner on [value]% of spans. The preregistered exact-fidelity criterion [was/was not] met. These results apply to the tested Python async/sync paths and do not establish cross-process propagation.

Example for a miss:

> At 100 concurrent users, event-to-alert p95 increased to [value] ms with [error rate]% failures, exceeding the 200 ms target. The target was met through [condition] but not beyond it; the saturation point was associated with [measured resource evidence].

Avoid:

- “Real time” without a measured interval and condition.
- “Zero overhead,” “zero rewrite,” “secure,” “privacy preserving,” or “no data loss” without operational definitions.
- “Outperforms Phoenix/Langfuse” from a feature checklist or one configuration.
- “Accurate anomaly detection” from positive-only injection examples.
- “Users understood the dashboard” from the development team's own observation.
- Turning the PRD thresholds into findings.

## 19. Final Evidence-Integrity Checklist

- [ ] Final commit/tag is frozen and recorded.
- [ ] All final datasets are held out from threshold tuning.
- [ ] Every run has a manifest and raw artifact hash.
- [ ] Failures/timeouts are retained and reported.
- [ ] Every metric names its unit of analysis and sample size.
- [ ] Confidence intervals and effect sizes accompany point estimates.
- [ ] Per-rule results are shown; macro averages do not hide weak detectors.
- [ ] New delegation and HMAC mechanisms are evaluated with ablations.
- [ ] Current-build load and overhead tests are rerun after the 2026-08-27 changes.
- [ ] Live versus historical final-state convergence is explicitly tested.
- [ ] Langfuse and Phoenix versions/configurations are recorded and comparison claims are matched fairly.
- [ ] Raw/key leakage scans cover wire, stores, logs, and UI boundaries.
- [ ] Usability claims come from real participants and a predefined rubric.
- [ ] AWS, precision/recall, sustainability, and usability claims remain absent until measured.
- [ ] Every table/figure is regenerated automatically from raw data.
- [ ] Results, interpretation, and limitations are visibly separated.
