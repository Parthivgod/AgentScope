# AgentScope — Agent Build Rules (RULES.md)

**Audience:** Any autonomous/semi-autonomous coding agent (Antigravity, Claude Code, or human contributor) working in this repository.
**Status:** Binding. These rules encode locked product decisions from `AgentScope_PRD.md` v1.0 and `AgentScope_Build_Plan.md`. If a task appears to require breaking one of these rules, **stop and ask a human** (see `INSTRUCTIONS.md` §2) rather than proceeding.

---

## 0. How to use this file

Read this file in full before writing any code in this repo. It is not background reading — every rule below has caused real design churn in the source docs (see PRD §14, Build Plan §13) and exists specifically to prevent that churn from recurring. When in doubt, this file wins over your own judgment about what seems "obviously fine" to add.

---

## 1. Hard Scope Boundary — Do Not Build These

Per PRD §5.2, the following are **explicitly out of scope**. They may look like small, reasonable additions mid-build. They are not. If any of these come up as a "quick win," do not implement them — log them in `docs/future-work.md` instead and move on.

- Multi-cloud or multi-region deployment
- Distributed tracing across multiple agent clusters
- Full user authentication, RBAC, or multi-tenant access control
- Mobile/native dashboard clients
- Native adapters for non-LangGraph frameworks (AutoGen, CrewAI, etc.) beyond the generic decorator/patch adapter
- ML-based anomaly detection (only the 6 rule-based detectors in PRD §7 are in scope)
- Native MCP / A2A protocol instrumentation
- **Any form of automatic remediation** — auto-kill, auto-restart, auto-scale, or any code path that lets AgentScope act on the monitored agent rather than merely observing it (see §4 below — this is the single most important boundary in the whole project)

**Do not conflate** API-key ingestion auth (in scope, narrow — secures the `/ingest` endpoint only) with user-facing authentication/RBAC (out of scope). These are different things; do not "helpfully" expand the former into the latter.

---

## 2. Locked Decisions — Do Not Re-Litigate

These are closed decisions (Build Plan §1). Do not propose alternatives, do not "improve" them unprompted, do not silently substitute a different library or pattern because it seems better.

| # | Decision |
|---|---|
| 1 | Dashboard layout is **hierarchical/dagre** (`@xyflow/react` + `@dagrejs/dagre`) — not force-directed D3. |
| 2 | Event/span schema is a **Pydantic model** (`Span`, `Trace`) living in exactly one place: `sdk/agentscope/schema.py`. `backend/` and `worker/` consume it via local editable install (`pip install -e ../sdk`) — never redefine or fork the schema. |
| 3 | The six anomaly rule thresholds start at the PRD §7 draft values (4 calls/60s, 30s timeout, 8k tokens/call, 20 events/sec, etc.) as the Sprint 1 baseline. They are provisional and **must** be re-tuned against the injection harness (Weeks 5–8) before being called final in any report — but do not invent different starting numbers. |
| 4 | Redaction is **opt-in**; default is full capture. Redaction, when enabled, happens **client-side in the SDK** — scrubbed data must never leave the user's process. Do not implement server-side redaction as a substitute. |
| 5 | LangGraph integration uses the **callback-tracer pattern**: subclass `langchain_core.tracers.base.AsyncBaseTracer`, inject via `config["callbacks"]`. Do not monkey-patch LangGraph internals instead. |
| 6 | First (and for now, only) LLM client targeted by `agentscope.patch()` is **OpenAI**. |
| 7 | Repository is a **monorepo** with the ownership structure in Build Plan §3 (`sdk/`, `backend/`, `worker/`, `dashboard/`, `infra/`, `examples/`, `docs/`, `manuscript/`). Do not restructure this layout without explicit sign-off — other tracks depend on these paths.

---

## 3. Non-Negotiable Architectural Invariants

These apply to every line of code touching the hot path, regardless of which track/file you're in.

1. **Observability must never risk availability.** Nothing in the SDK's send path may raise into the host agent's process, or block synchronously on network I/O. Every SDK PR must be checked against: *"Could this crash the monitored agent? Could this stall it waiting on us?"* If the answer to either is yes, the code is wrong — fix it before proceeding, don't ship it with a caveat.
2. **Fail silent, not fail loud, on the SDK side.** Backend unreachable, invalid API key, network timeout — all of these log a local warning and continue. They never raise, never block, never crash the host.
3. **Schema-identical spans across integration paths.** The LangGraph adapter and the decorator/patch path must produce spans that are indistinguishable to the backend, worker, and dashboard. Neither the ingestion API, the anomaly rules, nor the dashboard should ever need a "which integration path produced this" branch.
4. **Events are processed in strict arrival order.** Do not reorder by span type, priority, or convenience — anomaly rules (especially loop/cycle detection) depend on causal sequence being preserved.
5. **One rendering path for live and historical views.** `dashboard/` must reuse the same graph-rendering component for live WebSocket data and for historical replay from stored events. The only permitted difference is the event *source*. Do not build a second "quick" historical view — per Build Plan §11, it will diverge and become a maintenance liability.
6. **Anomaly worker isolation is load-bearing, not incidental.** The worker must be independently killable and restartable without the ingestion path noticing or losing events. Treat any code that couples worker liveness to ingestion liveness as a bug, not a shortcut.
7. **Detection ≠ enforcement, everywhere in the codebase.** AgentScope surfaces anomalies; it never acts on the monitored agent. There is no exception to this. If a feature request implies AgentScope taking an action on the agent being watched, it is out of scope — see §1.

---

## 4. Security & Data Handling Rules

- `/ingest` **must** reject any request without a valid API key (FR-7). Never add a bypass, even for local dev convenience, without gating it clearly behind a non-default flag.
- All ingestion traffic is TLS-encrypted in the reference deployment (Nginx terminates TLS). Don't design features that assume plaintext transport is acceptable.
- Redaction is client-side and opt-in (see §2, Decision 4). When redaction is on, scrubbed fields must be genuinely absent from what leaves the SDK process — not just hidden in the dashboard UI.
- Treat `input`/`output` span fields as potentially containing PII/sensitive content by default (full-capture is the default precisely because Dana needs debuggability — but don't forget Priya's threat model exists too when touching this code).

---

## 5. Testing Requirements That Block Merge

Per PRD §10 / Build Plan §7, the following are not optional "nice to have" tests — treat failing or missing coverage here as a blocking issue:

- Every SDK PR: unit tests for capture correctness, plus the cross-path schema-identity test (adapter output vs. decorator output against equivalent synthetic workloads).
- Every ingestion/schema change: schema validation tests + API-key rejection test.
- Every anomaly rule: tested against hand-crafted event sequences before it's considered "done," and re-validated against the injection harness before its threshold is treated as final.
- Any change touching the worker/ingestion boundary: a resilience check that the worker can be killed/restarted without the ingestion path losing data or stalling.

---

## 6. Numbers You May Not Assert Without Evidence

Do not write any of the following into docs, code comments, READMEs, or the manuscript as an established fact unless the corresponding test in PRD §10 has actually been run and the result is what's being cited:

- "<200ms p95 latency" — only after Week 9 load testing (Locust/k6).
- "<5% SDK overhead" — only after the Week 9 with/without-SDK benchmark.
- "≥90% precision / ≥85% recall" per anomaly rule — only after injection-harness validation (Weeks 5–8).
- Any sustainability/efficiency percentage (PRD §11) — only after being measured against a defined baseline; never asserted as a target dressed up as a finding.

Draft/target values are fine to state as targets. Do not let a target quietly become a claim.

---

## 7. When These Rules Conflict With a Request

If a task you're asked to do would require violating any rule in this file:

1. Do not silently comply.
2. Do not silently refuse and do nothing.
3. Flag the conflict explicitly, name the specific rule, and ask for clarification before proceeding (see `INSTRUCTIONS.md`).

These rules can be changed — but only by explicit human decision, recorded as an update to this file (with a changelog entry, per `INSTRUCTIONS.md` §3), never by an agent inferring that an exception is warranted in the moment.
