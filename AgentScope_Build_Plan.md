# AgentScope — Build Plan

**Team:** Eshan Gahlot, Parthiv Godrihal, Nilay Jain | Mentor: Prof. Sapna Shah
**Source docs:** `AgentScope_PRD.md` v1.0, `AgentScope_User_Flows.md` (both updated to match the locked decisions below)
**Purpose:** A complete, traceable plan covering every requirement in the PRD, split into 3 parallel tracks so the team can build simultaneously without stepping on each other.

---

## 0. Project Recap (so this doc is self-contained)

**What it is:** A lightweight, open-source, self-hosted observability platform for multi-agent LLM systems — live visualization, zero-rewrite instrumentation, and real-time rule-based anomaly detection, in one tool (no existing tool combines all three — PRD §1–2).

**Goals & success metrics (PRD §3):**
| Goal | Metric |
|---|---|
| Live observability | <200ms p95 event-to-dashboard latency |
| Zero-rewrite instrumentation | SDK import + adapter attach only, no agent logic changes |
| Reliable anomaly detection | ≥90% precision, ≥85% recall per rule |
| Lightweight self-hosting | Single `docker-compose up` on one EC2 instance |
| Low overhead | SDK adds <5% to agent execution time |
| Open & reusable | MIT release, docs, demo video, submitted manuscript |

**Personas:** Dana (solo LangGraph dev, wants 5-minute install), Rahul (research lab, custom agent code, self-hosted), Priya (startup backend lead, cost/security-conscious).

**In scope (PRD §5.1):** Python SDK, FastAPI + Redis Streams pipeline, React dashboard, LangGraph adapter + generic decorator/patch adapter, 6 anomaly rules, Docker Compose on one EC2 instance, API-key + TLS ingestion security, MIT release + docs + demo + manuscript.

**Explicitly out of scope (PRD §5.2) — do not build these:** multi-cloud/multi-region deployment, distributed tracing across agent clusters, full user auth/RBAC/multi-tenancy, mobile/native clients, native non-LangGraph adapters (AutoGen, CrewAI), ML-based anomaly detection, native MCP/A2A protocol instrumentation. If any of these come up mid-build as "quick additions," they're future work — log them, don't build them.

---

## 1. Decisions — Locked

All items below are decided. PRD and User Flows have been updated to match (see Section 10).

| # | Item | Decision | Notes |
|---|---|---|---|
| 1 | Dashboard layout algorithm | **Hierarchical / dagre** (`@xyflow/react` + `@dagrejs/dagre`), not force-directed D3. | Clearer flow direction, proven handling of cycles/subgraphs. |
| 2 | Event/span schema | Formalized as a **Pydantic model** (`Span`, `Trace`), single source of truth in `sdk/agentscope/schema.py`. | Both backend and worker import it locally (editable install) rather than re-defining it — avoids drift. |
| 3 | Numeric thresholds for the 6 anomaly rules | **PRD's draft values locked as the Sprint 1 starting point** (4 calls/60s, 30s timeout, 8k tokens/call, 20/sec message storm, etc.). | Provisional until validated against the injection harness (Weeks 5–8). |
| 4 | Redaction/metadata-only mode default | **Default = full capture; redaction is opt-in**, implemented **client-side in the SDK** (so PII never leaves the user's process when enabled). | Favors Dana's out-of-the-box debuggability; Priya opts in. |
| 5 | Target journal/venue | **Deferred to Phase 3** — non-blocking for build. | |
| 6 | LangGraph adapter hooking mechanism | **Callback-tracer pattern**: subclass `langchain_core.tracers.base.AsyncBaseTracer`, inject into the graph's `config["callbacks"]`. | Officially supported API, not a monkey-patch of LangGraph internals. |
| 7 | Where the SDK writes events | Tracer's `_on_chain_end` / `_on_llm_end` / `_on_tool_end` / `_error` handlers build a `Span`, hand it to an async non-blocking sender that posts to the ingestion endpoint. | Design deliberately — FR-3 and FR-4 both depend on this path. |
| 8 | First LLM client library for `agentscope.patch()` | **OpenAI client first**; others follow later. | |

---

## 2. Architecture Recap (PRD §6)

```
┌────────────┐   spans (async, non-blocking)   ┌───────────┐
│  SDK        │ ───────────────────────────────▶│  Nginx     │
│  (Adapter / │        HTTPS + API key          │  (TLS,     │
│  Decorator) │                                  │  reverse   │
└────────────┘                                   │  proxy)    │
                                                  └─────┬─────┘
                                                        │
                                                  ┌─────▼─────┐
                                                  │ FastAPI    │──▶ Redis Streams (durable, ordered)
                                                  │ Backend    │◀── Anomaly Worker (reads raw, writes flags)
                                                  └─────┬─────┘
                                                        │ WebSocket
                                                  ┌─────▼─────┐
                                                  │ React      │
                                                  │ Dashboard  │
                                                  └────────────┘
```

Four conceptual layers (PRD §6.1): **Instrumentation → Event Pipeline → Analysis Engine → Live Visualization**, deliberately kept as separately deployable/testable units — the anomaly worker must be able to crash and restart without interrupting ingestion (FR-5, §9.2).

**Event/span schema (PRD §6.3, locked as the Week 1 contract):** `trace_id`, `span_id`/`parent_span_id`, `span_type` (`llm_call`/`tool_call`/`delegation`/`state_update`), `name`, `input`/`output` (redaction-subject), `start_time`/`end_time`, `status`, `token_usage`, `agent_id`. Events processed in strict arrival order.

---

## 3. Repository Structure & Ownership

```
agentscope/
├── sdk/                        ◀── TRACK A owns this
│   ├── agentscope/
│   │   ├── schema.py            # Span/Trace Pydantic models — THE shared contract (Week 1)
│   │   ├── adapters/langgraph.py
│   │   ├── trace.py             # @agentscope.trace decorator
│   │   ├── patch.py             # agentscope.patch(openai)
│   │   ├── sender.py            # async buffered/retrying, fail-silent
│   │   └── config.py            # env vars, redaction toggle
│   └── tests/
├── backend/                     ◀── TRACK B owns this
│   ├── app/
│   │   ├── main.py, ingest.py (API-key middleware), ws.py, history.py, redis_client.py
│   └── tests/
├── worker/                      ◀── TRACK B owns this
│   ├── worker/main.py, rules/ (6 modules), harness/ (injection harness)
│   └── tests/
├── dashboard/                   ◀── TRACK C owns this
│   ├── src/components/ (Graph.tsx, InspectPanel.tsx, AlertBadge.tsx)
│   ├── src/hooks/useWebSocket.ts, src/layout.ts (dagre)
│   └── tests/
├── infra/                       ◀── TRACK B owns this
│   ├── docker-compose.yml, nginx/, .env.example
├── examples/                    ◀── TRACK A owns this
│   ├── langgraph_demo_agent/, custom_demo_agent/
├── docs/                         ◀── shared, each track writes its own section
└── manuscript/                  ◀── shared, each track drafts its own results section
```

**Key coordination point:** `backend/` and `worker/` import `sdk/agentscope/schema.py` via a local editable install (`pip install -e ../sdk`) rather than redefining the schema — this is a monorepo, so there's no reason for two copies of the same contract to drift apart.

---

## 4. The Three Tracks

Three roughly-equal, independently-buildable tracks, mapped to the four architecture layers by grouping Analysis Engine with Event Pipeline (both are server-side Python owned by one person) so each of the three teammates owns a coherent, self-contained slice. Suggested default mapping below — swap based on actual skill fit, this isn't a firm assignment:

| Track | Suggested Owner | Layer(s) | Skillset |
|---|---|---|---|
| **A — SDK & Instrumentation** | Eshan | Instrumentation | Python, LangChain/LangGraph internals |
| **B — Backend, Pipeline & Analysis** | Parthiv | Event Pipeline + Analysis Engine + Infra | Python, FastAPI, Redis, Docker/deployment |
| **C — Dashboard & Visualization** | Nilay | Live Visualization | React/TypeScript, UX |

Each track below lists: what it owns, which PRD requirements it's responsible for, its own week-by-week plan, and where it depends on another track.

---

### Track A — SDK & Instrumentation

**Owns:** `sdk/`, `examples/`
**Responsible for:** FR-1, FR-2, contributes to FR-3 (non-blocking client send) and FR-4 (reliable delivery); NFR 9.5 (overhead), NFR 9.4 (redaction implementation)
**Test items owned:** #1 (SDK-side unit tests), #5 (overhead benchmark); contributes to #2 (integration), #6/#7 (SDK-side failure/security behavior)
**Manuscript section:** Instrumentation methodology + overhead benchmark results

| Week | Task | Depends on / feeds |
|---|---|---|
| 1 | Design & finalize `Span`/`Trace` Pydantic models in `schema.py` — **this is the Week 1 contract everyone else needs.** Scaffold package structure. | Share with Track B day 1; both review together before locking. |
| 2 | Build `LangGraphAdapter` (`AsyncBaseTracer` subclass, injected via `config["callbacks"]`, Decision #6/#7), `@agentscope.trace` decorator, `sender.py` (async, buffered, fail-silent), `config.py` (env vars). | Independent — no dependency on Track B/C yet. |
| 3 | Build `patch.py` for OpenAI (Decision #8). Test both integration paths against a **mock** ingestion server, confirming schema-identical spans (shared fixture test, per Flow 2 design implication). | Uses a local mock; doesn't need Track B's real backend yet. |
| 4 | Build `examples/langgraph_demo_agent/` (linear + branching, mirroring the LangGraphics test-fixture pattern). Attach `LangGraphAdapter`. **[Integration checkpoint — M1]:** join Track B/C for the first real end-to-end run proving "zero-rewrite." | Needs Track B's real `/ingest` + Track C's dashboard live. |
| 5 | Build `examples/custom_demo_agent/` (Flow 2 demo). Begin overhead-benchmark harness scaffolding (full run in Week 9). | — |
| 6 | Implement the redaction toggle (client-side scrubbing before send, Decision #4) and harden sender retry/backoff. | — |
| 7 | Docs pass on both integration paths; expand SDK test coverage; stretch goal — second LLM client for `patch()`. | — |
| 8 | **[Integration checkpoint — M2]:** confirm SDK correctly targets the AWS-deployed backend via env vars (Flow 6, Step 4). | Needs Track B's AWS deployment live. |
| 9 | Run the full overhead benchmark (with/without SDK), report against the <5% target (NFR 9.5, Test #5). | — |
| 10 | Support resilience/security testing from the SDK side — simulate backend-unreachable scenarios end-to-end; finalize redaction-mode tests. | Coordinates with Track B's Test #6/#7. |
| 11 | SDK documentation (quickstart for both paths); draft the **Instrumentation Methodology** manuscript section. | — |
| 12 | Final polish, packaging, release support. | — |

---

### Track B — Backend, Pipeline, Analysis Engine & Infra

**Owns:** `backend/`, `worker/`, `infra/`
**Responsible for:** FR-3, FR-4, FR-5, FR-7, FR-8, FR-9; NFR 9.1, 9.2, 9.3, 9.6; contributes to NFR 9.4 (schema-level support)
**Test items owned:** #2 (integration), #3 (anomaly validation), #4 (performance), #6 (resilience), #7 (security), #8 (comparative baseline)
**Manuscript section:** System design write-up + evaluation results (precision/recall, latency)

| Week | Task | Depends on / feeds |
|---|---|---|
| 1 | FastAPI skeleton, `POST /ingest` validating against Track A's `Span` schema, API-key middleware (FR-7). Redis-only `docker-compose.yml`. First CI tests (schema + auth rejection). | Needs Track A's schema locked day 1. |
| 2 | Wire ingest → Redis Streams write. Confirm both of Track A's integration paths produce spans the backend accepts identically. | — |
| 3 | `ws.py` WebSocket relay. **[Integration checkpoint]:** join Track A/C for the first synthetic end-to-end pipeline test (mock agent → ingest → Redis → WS → dashboard placeholder). | Track C needs this live to build against. |
| 4 | **[Integration checkpoint — M1]:** support Track A's real LangGraph demo hitting the real ingestion path. | — |
| 5 | Anomaly worker skeleton (independent process, reads raw Redis Streams events, never blocks ingestion — FR-5, §9.2). Implement **Failure Loops** + **Crashes** rules. Start the synthetic failure injection harness (prerequisite for §10.3/§10.8). | — |
| 6 | Implement **Timeouts**, **Token Spikes**, **Message Storms**, **Delegation Cycles**. Wire anomaly flags back through Redis → WS. **[Integration checkpoint]:** hand off to Track C for alert-state wiring. | Track C needs flags flowing to build `AlertBadge`. |
| 7 | `history.py` historical query endpoint (FR-8). Support Track C's shared live/historical rendering design (event source differs, rendering logic doesn't — Flow 5). | — |
| 8 | **[Integration checkpoint — M2]:** full `docker-compose` (Nginx + FastAPI + Redis + Worker) deployed to AWS EC2; confirm unauthenticated-request rejection (Flow 6, Step 5). Run the injection harness across all 6 rules, tune thresholds, record precision/recall/F1. | Everyone joins for the M2 demo. |
| 9 | Load testing (Locust/k6), report p50/p95/p99 latency against the <200ms target (Test #4, NFR 9.1). | — |
| 10 | Resilience testing (kill worker mid-run, restart Redis, slow WS client — Test #6); security testing (TLS termination, API-key rejection — Test #7); set up the comparative baseline test vs. Phoenix/Langfuse (Test #8). | — |
| 11 | Backend/infra documentation; draft **System Design** + **Evaluation Results** manuscript sections. | — |
| 12 | Final deployment hardening, release support. | — |

---

### Track C — Dashboard & Visualization

**Owns:** `dashboard/`
**Responsible for:** FR-6; contributes to perceived-latency aspects of FR-3
**Test items owned:** #9 (usability testing); contributes to #2 (integration), #8 (UI side of comparative baseline)
**Manuscript section:** Usability testing findings + visualization design rationale

| Week | Task | Depends on / feeds |
|---|---|---|
| 1 | Scaffold (Vite + React + TS), install `@xyflow/react` + `@dagrejs/dagre`, build `layout.ts` per Decision #1. Static placeholder graph render. | — |
| 2 | `useWebSocket` hook built against **mocked** JSON events (Track B's real WS isn't ready yet). Node/edge status state machine (idle/active/complete). | Use synthetic fixtures matching Track A's schema. |
| 3 | **[Integration checkpoint]:** connect to Track B's real WebSocket relay; live pulsing node states (Flow 3, Steps 1–3). | Needs Track B's Week 3 deliverable. |
| 4 | `InspectPanel.tsx` (hover/click detail: input/output, duration, token usage — Flow 3, Step 4). **[Integration checkpoint — M1]:** join the real LangGraph demo. | — |
| 5 | Polish graph interactions; scaffold `AlertBadge.tsx` ahead of Track B's rules landing. | — |
| 6 | **[Integration checkpoint]:** wire `AlertBadge` to real anomaly flags; click-to-inspect anomaly detail (Flow 4, Step 4) — distinct visual state from normal "active" pulsing. | Needs Track B's Week 6 deliverable. |
| 7 | Historical replay UI — reuse `Graph.tsx`/`InspectPanel` for a stored-event source (Flow 5); live/historical toggle. | Needs Track B's `history.py`. |
| 8 | **[Integration checkpoint — M2]:** full-stack demo against the AWS-deployed backend; UI polish. | — |
| 9–10 | UX polish; redaction-mode UI indicator (shows when metadata-only mode is active); accessibility/performance pass. | — |
| 11 | Dashboard documentation; run the **usability test** (Test #9 — unfamiliar observer watches a live failure, explains what happened unaided, per Flow 3 success criteria/§10.9); draft **Usability Findings** manuscript section. | — |
| 12 | Final polish; support demo video recording (the dashboard is the visual centerpiece of the Flow 1 and Flow 4 demos). | — |

---

## 5. Cross-Track Integration Checkpoints (don't skip these)

| Week | What happens | Who joins |
|---|---|---|
| 1 | Schema contract locked (`Span`/`Trace`) | A + B review together |
| 3 | First synthetic end-to-end pipeline (mock agent → ingest → Redis → WS → dashboard) | A + B + C |
| 4 | **M1** — real LangGraph agent, zero-rewrite demo, live dashboard | A + B + C |
| 6 | Anomaly flags wired end-to-end into the dashboard alert state | B + C |
| 8 | **M2** — full stack on AWS, all 6 rules threshold-tuned | A + B + C |
| 11–12 | **M3** — docs, demo video, manuscript sections assembled, public release | A + B + C |

If a track finds itself blocked at one of these points because an upstream track slipped, that's the signal to pull people over rather than letting the blocked track sit idle — these are hard sync points, not soft suggestions.

---

## 6. Requirements Traceability

### Functional Requirements (PRD §8)
| ID | Requirement | Owning Track | Delivered by |
|---|---|---|---|
| FR-1 | SDK captures LLM/tool/delegation events, zero business-logic changes | A | Week 2 |
| FR-2 | Native LangGraph adapter + generic decorator/patch adapter | A | Weeks 2–3 |
| FR-3 | Stream events to dashboard, p95 < 200ms | A (client non-block) + B (server) | Validated Week 9 |
| FR-4 | Durable event persistence, no data loss on consumer restart | B | Week 5, validated Week 10 |
| FR-5 | Anomaly worker evaluates all 6 rules, writes flags back | B | Weeks 5–6, tuned Week 8 |
| FR-6 | Dashboard renders live hierarchical graph, active/idle/anomalous states | C | Weeks 1–6 |
| FR-7 | Ingestion rejects requests without valid API key | B | Week 1 |
| FR-8 | Historical replay of completed traces | B (endpoint) + C (UI) | Week 7 |
| FR-9 | Full stack deploys via single Docker Compose command | B | Week 8 |

### Non-Functional Requirements (PRD §9)
| ID | Requirement | Owning Track | Validated by |
|---|---|---|---|
| 9.1 Performance | <200ms p95 latency under load | B | Week 9 load test |
| 9.2 Reliability | Worker failure never interrupts ingestion | B | Week 10 fault injection |
| 9.3 Security | TLS + API-key on all ingestion traffic | B | Week 10 security test |
| 9.4 Data Handling | Configurable redaction, default full-capture/opt-in | A (implementation) | Week 6 build, Week 10 test |
| 9.5 Overhead | SDK adds <5% execution overhead | A | Week 9 benchmark |
| 9.6 Portability | No kernel privileges / specific OS required | B | Design-time (Docker-based, inherent) |
| 9.7 Licensing | MIT license on full codebase | Shared | Week 1 (license file) |

---

## 7. Full Testing & Validation Plan (PRD §10, all 9 items mapped)

| # | Test | Owning Track | Week |
|---|---|---|---|
| 1 | Unit testing (SDK capture, ingestion schema, per-rule logic) | A + B (own their own units) | Ongoing, every push (CI) |
| 2 | Integration testing (full Docker Compose stack, real + custom traffic) | B, with A + C | Weeks 3, 4, 8 |
| 3 | Anomaly detection validation (injection harness, precision/recall/F1) | B | Weeks 5–8 |
| 4 | Performance/latency testing (Locust/k6, p50/p95/p99) | B | Week 9 |
| 5 | Overhead testing (with/without SDK) | A | Week 9 |
| 6 | Resilience testing (kill worker, restart Redis, slow WS client) | B | Week 10 |
| 7 | Security testing (API-key rejection, TLS termination) | B | Week 10 |
| 8 | Comparative baseline testing (vs. Phoenix/Langfuse, time-to-detection) | B (backend timing) + C (UI) | Week 10 |
| 9 | Usability testing (unfamiliar observer, live failure, unaided explanation) | C | Week 11 |

---

## 8. Six Anomaly Rules — Implementation Notes (Track B)

| Rule | Draft Threshold (PRD §7) | State Needed | Notes |
|---|---|---|---|
| Failure Loops | ≥4 identical calls within 60s, state not materially changing | Rolling window of (call signature, state hash) per agent | State-diff/hash comparison needed, not just call-name matching |
| Crashes | Unhandled exception, non-2xx tool response, null/empty completion | Stateless, per-span check | Simplest — build first |
| Timeouts | Fixed ceiling (e.g. 30s) or N std-devs above historical average | Running mean/stddev per span type | Start with fixed ceiling; add statistical variant once historical data exists |
| Token Spikes | Single call >8k tokens, or session cumulative >20k tokens/min | Per-trace running token counter | Needs `token_usage` populated correctly by the SDK — verify in Week 2, not Week 6 |
| Message Storms | >20 events/sec sustained for 5+ seconds | Sliding time-window event counter | Cheap to implement, easy to test with synthetic bursts |
| Delegation Cycles | Delegation graph revisits a previously-visited agent before task completion | Per-trace visited-agent set | Requires `agent_id` reliably populated across both SDK integration paths |

Every threshold is provisional — must be empirically justified via the injection harness before appearing as final numbers in the manuscript's Evaluation section (PRD §7).

---

## 9. Risk Register (PRD §13)

| Risk | Mitigation | Owner |
|---|---|---|
| 12-week timeline is aggressive across SDK + backend + frontend + 6 detectors + AWS + manuscript | M1/M2/M3 checkpoints surface slippage early; don't let one track's delay silently cascade — flag at the weekly sync | Shared |
| Anomaly thresholds undefined until validated | Injection harness prioritized in Week 5, not deferred to Week 8 | Track B |
| Single EC2 instance = single point of failure | Accepted out-of-scope limitation; documented as future work | Track B |
| <200ms latency claim unproven until tested | Load-testing scheduled Week 9, prerequisite to the manuscript claim | Track B |
| Citation/reference completeness | Cross-verify all literature-review citations before submission | Shared, Week 11–12 |

---

## 10. Research Track (Shared, Runs Parallel to Engineering)

Per PRD §12, a research track runs alongside development:
- **Weeks 1–4:** Literature review + methodology draft — shared across all three (split by whichever prior-work area each person is most familiar with: general tracing/AgentOps, real-time governance/AgentSight, causal root-cause ranking).
- **Weeks 5–8:** System design write-up + evaluation plan — drafted primarily by Track B since it owns the evaluation harness, reviewed by all.
- **Weeks 9–12:** Results, discussion, manuscript submission — each track drafts the section tied to its own results (Section 4 above lists which), then the team assembles and cross-edits the full manuscript together in Week 12.
- **Sustainability note (PRD §11):** the manuscript's discussion should tie real-time anomaly prevention to reduced wasted LLM compute (UN SDG 12 primarily) — but only with numbers actually measured in Weeks 9–10 testing, not asserted as a target.

---

## 11. Cross-Cutting Engineering Rules (apply on every track)

1. **Observability must never risk availability.** Any code on the SDK's hot path must be reviewed for: could this raise into the host agent? Could this block synchronously on I/O? Required checklist item on every SDK PR (Track A).
2. **Schema-identical spans across integration paths.** CI test diffs `Span` output from both the adapter and decorator paths against equivalent synthetic workloads (Track A).
3. **Anomaly worker isolation.** Must be independently killable/restartable without ingestion noticing — test this explicitly (Track B).
4. **One rendering path for live and historical.** Don't build a "quick" separate historical view — it will diverge (Track C).
5. **Detection, not enforcement — anywhere in the codebase.** No auto-kill/auto-restart logic. Out of scope per §5.2; log as future work if proposed (all tracks).

---

## 12. Day-1 Checklist, Per Track

**Track A:** `sdk/agentscope/schema.py` with `Span` Pydantic model matching PRD §6.3 fields.
**Track B:** `backend/app/ingest.py` (`POST /ingest`, API-key middleware, validates against Track A's schema); `infra/docker-compose.yml` with Redis; `.env.example` with `AGENTSCOPE_API_KEY` placeholder.
**Track C:** Dashboard scaffold with `@xyflow/react` + `dagre` installed, static placeholder graph rendering.
**Shared:** MIT license file added to repo root; first CI workflow running schema + ingestion tests on push.

---

## 13. Decisions Reflected in Source Docs

The PRD and User Flows have been updated to match every locked decision in Section 1 — no remaining inconsistency between this plan and the source documents:
- **Layout algorithm:** PRD §5.1, §6.1, §6.2, and FR-6 now specify hierarchical/dagre. User Flows Flow 3, Step 3 updated to match.
- **Redaction default:** PRD §9.4 now states the default explicitly.
- **§14 open items:** two of five marked resolved; thresholds and the injection harness remain open by design (they require empirical data); venue explicitly deferred.
- **Event schema (§6.3):** still a draft table in the PRD itself (fine for a requirements doc); this build plan treats formalizing it as a Pydantic model as the Week-1 task for Track A.

---

*Companion inputs: `AgentScope_PRD.md`, `AgentScope_User_Flows.md`.*
