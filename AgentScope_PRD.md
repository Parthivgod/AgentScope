# AgentScope — Product Requirements Document (PRD)

**Product:** AgentScope — Live Topology Viewer for Multi-Agent AI Workflows
**Team:** Eshan Gahlot, Parthiv Godrihal, Nilay Jain | Mentor: Prof. Sapna Shah
**Institution:** SVKM's NMIMS, MPSTME, Dept. of AI | Capstone, Sem VII, AY 2026-27
**Document version:** 1.0 — Draft for Topic Approval

---

## 1. Executive Summary

AgentScope is a lightweight, open-source, self-hosted observability platform for multi-agent LLM systems. It provides **live** visualization of agent execution, **zero-rewrite** instrumentation, and **real-time rule-based anomaly detection** — a combination no existing tool (Langfuse, AgentOps, Arize Phoenix, or the five academic systems reviewed in our literature study) currently offers together. Where existing tools reconstruct execution graphs *after* a run completes, AgentScope renders and alerts on failures **while they are happening**, targeting under 200ms event-to-dashboard latency.

---

## 2. Problem Statement

> Developers lack a lightweight, open-source, self-hosted platform to observe multi-agent interactions live and get immediate alerts when failure modes trigger.

### 2.1 Problem Definition
- **Trace Viewer Limitations:** Existing platforms (Langfuse, AgentOps, Arize Phoenix) act as post-hoc trace viewers, reconstructing historical graphs only after execution completes.
- **Enterprise Barriers:** Full-stack observability tools are typically closed-source, vendor-locked, or too complex for smaller teams and researchers to self-host.
- **Debugging Blind Spots:** When a delegation chain fails across multiple agents, existing tools show *that* something broke but rarely *why* — root-cause attribution still requires manual log correlation.
- **Delayed Cost Visibility:** Token consumption and API spend are typically visible only after a run completes or a billing cycle closes, letting runaway loops burn budget for minutes or hours unnoticed.

### 2.2 Research Gap
Prior work addresses individual slices of this problem — general distributed tracing (Dapper, 2010), agent-aware span taxonomies (AgentOps, 2024), kernel-level security tracing (AgentSight, 2025), real-time governance enforcement (GAAT, 2026), and causal root-cause ranking (AgentTrace-USC, 2026) — but none combine live visualization + zero-rewrite instrumentation + real-time anomaly detection + self-hosted deployment into a single platform. This is the specific gap AgentScope fills.

---

## 3. Goals & Success Criteria

| Goal | Success Metric |
|---|---|
| Live observability | Event-to-dashboard latency < 200ms (p95, under realistic concurrent load) |
| Zero-rewrite instrumentation | Integration requires only SDK import + adapter attach — no changes to agent business logic |
| Reliable anomaly detection | ≥90% precision, ≥85% recall per rule, validated via synthetic failure injection |
| Lightweight self-hosting | Full stack deployable via a single `docker-compose up` on one EC2 instance, within free-tier/student credit budget |
| Low instrumentation overhead | SDK adds <5% overhead to monitored agent execution time (benchmark target, comparable to AgentSight's published <3%) |
| Open, reusable | MIT-licensed public release with documentation, demo video, and a submitted research manuscript |

---

## 4. Target Users & Personas

**Primary persona — "Dana, the Independent AI Developer"**
Builds LangGraph-based agents solo or in a small team. Has hit silent failure loops in production/dev and currently debugs via scattered print statements and manual log review. Wants a five-minute install with no infrastructure commitment.

**Secondary persona — "Rahul, the Research Lab Engineer"**
Runs experimental multi-agent workflows for a university/small research group. Needs self-hosted (no data leaving university infrastructure), and values the tool being open-source and inspectable over enterprise polish.

**Tertiary persona — "Priya, the Startup Backend Lead"**
Running agents in a small production pipeline. Cost-sensitive (can't justify an enterprise observability contract), needs to catch token-burn incidents before they hit the AWS bill, and cares about basic ingestion security (API keys, TLS) even without full multi-user RBAC.

---

## 5. Scope

### 5.1 In Scope
- Pip-installable, zero-rewrite Python SDK for agent instrumentation
- FastAPI backend + Redis Streams event pipeline
- Live React + React Flow dashboard (hierarchical/dagre layout, pulsing active nodes)
- Native LangGraph adapter + generic custom-app adapter (decorators/runtime patching)
- Six rule-based anomaly detectors (see §7)
- Docker Compose deployment on a single AWS EC2 instance
- API-key-based ingestion authentication + TLS-encrypted WebSocket transport
- Open-source (MIT) release, documentation, demo video, and research manuscript

### 5.2 Out of Scope (Future Work)
- Multi-cloud or multi-region deployment
- Distributed tracing across multiple agent clusters
- Full user authentication, RBAC, or multi-tenant access control
- Mobile/native dashboard clients
- Native adapters for non-LangGraph frameworks (AutoGen, CrewAI) beyond the generic custom adapter
- ML-based (as opposed to rule-based) anomaly detection
- Native MCP / A2A protocol instrumentation (logical future extension of the adapter model, not core scope)

> **Note:** Item "User authentication, RBAC, multi-tenant access control" is explicitly out of scope per the current deck. API-key ingestion auth (a narrower mechanism securing the ingestion endpoint only) remains in scope and should not be conflated with full user-facing auth/RBAC when this is discussed — see prior Q&A prep for the exact phrasing to use if asked.

---

## 6. System Architecture

### 6.1 Four-Layer Conceptual Model
1. **Instrumentation** — SDK captures agent/tool/LLM execution via decorators and runtime patching; LangGraph adapter uses native node-transition callbacks.
2. **Event Pipeline** — Events streamed to Redis Streams with trace/span/parent-span hierarchy; durable delivery enables historical replay.
3. **Analysis Engine** — Decoupled anomaly worker reads raw events, evaluates against six rules, writes results back to Redis — isolated so its failure never blocks ingestion.
4. **Live Visualization** — FastAPI streams processed events via WebSocket; React + React Flow renders an interactive, hierarchically-arranged (dagre) live execution graph.

### 6.2 Infrastructure Topology
- **Nginx** — reverse proxy; edge isolation, REST + WebSocket routing, TLS termination
- **FastAPI Backend** — central coordinator for ingestion, historical queries, WebSocket relay
- **Redis Streams** — durable, ordered event buffer and store
- **Decoupled Anomaly Worker** — independent Python service; reads raw events, writes anomaly flags back to Redis
- **React + React Flow Dashboard** — client UI outside the deployment boundary, connects via WebSocket; graph rendered with a hierarchical (dagre) layout, chosen over force-directed for clearer flow direction and proven handling of cycles/subgraphs in agent execution graphs

All components run via Docker Compose on a single AWS EC2 instance (explicit scope boundary — see §5.2).

### 6.3 Event/Span Schema (draft)
| Field | Description |
|---|---|
| `trace_id` | Unique ID for the full agent run |
| `span_id` / `parent_span_id` | This call's ID and its causal parent (builds the hierarchy) |
| `span_type` | `llm_call`, `tool_call`, `delegation`, `state_update` |
| `name` | e.g., `search_web`, `gpt-4o.complete` |
| `input` / `output` | Captured arguments/response (subject to redaction policy, §9.4) |
| `start_time` / `end_time` | Drives duration and latency-based rules |
| `status` | success / error + exception details |
| `token_usage` | Prompt/completion tokens — feeds the token-spike rule |
| `agent_id` | Which agent/node made the call — needed for delegation-cycle detection |

Events are processed in **strict arrival order** (not reordered by call type), preserving the causal sequence anomaly rules depend on.

---

## 7. Anomaly Detection Requirements

Six rule-based detectors, each requiring a concrete, testable threshold (to be finalized via the validation process in §10):

| Rule | Draft Detection Logic (to validate/tune) |
|---|---|
| **Failure Loops** | Same tool call or node re-entered ≥N times (e.g., 4) within a rolling window (e.g., 60s) without state materially changing |
| **Crashes** | Any span ending in an unhandled exception, non-2xx tool response, or unexpected null/empty LLM completion |
| **Timeouts** | Any span exceeding a fixed ceiling (e.g., 30s) or N standard deviations above that step's historical average |
| **Token Spikes** | Single LLM call exceeding a token threshold (e.g., 8k), or cumulative session usage exceeding a rate (e.g., 20k tokens/min) |
| **Message Storms** | Event/message volume exceeding N events/sec sustained over a window (e.g., >20/sec for 5+ seconds) |
| **Delegation Cycles** | The delegation graph revisits a previously-visited agent/node before task completion |

**Requirement:** Every threshold above must be empirically justified via synthetic failure injection (§10.3) before the manuscript's Evaluation section is written — thresholds cannot ship as arbitrary constants.

---

## 8. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | SDK SHALL capture LLM calls, tool calls, and delegation events without requiring changes to agent business logic |
| FR-2 | System SHALL support both a native LangGraph adapter and a generic decorator/patching-based adapter for arbitrary Python agent code |
| FR-3 | System SHALL stream captured events to the dashboard with p95 latency under 200ms |
| FR-4 | System SHALL persist all raw events durably such that a consumer restart does not lose data |
| FR-5 | Anomaly worker SHALL evaluate all six rules against the live event stream and write flagged anomalies back to the store |
| FR-6 | Dashboard SHALL render a live, hierarchically-arranged (dagre) graph of agent/tool/LLM nodes, visually distinguishing active vs. idle vs. anomalous nodes |
| FR-7 | Ingestion endpoint SHALL reject requests without a valid API key |
| FR-8 | System SHALL support historical replay of a completed trace from stored events |
| FR-9 | Full stack SHALL deploy via a single Docker Compose command |

## 9. Non-Functional Requirements

| Category | Requirement |
|---|---|
| 9.1 Performance | Event-to-dashboard latency < 200ms (p95) under realistic concurrent load |
| 9.2 Reliability | Anomaly worker failure/restart SHALL NOT interrupt event ingestion (validated via fault injection, §10.5) |
| 9.3 Security | All ingestion traffic SHALL be TLS-encrypted; ingestion SHALL require API-key authentication |
| 9.4 Data Handling | System SHOULD support a configurable redaction/metadata-only mode for captured `input`/`output` fields, given potential PII/sensitive content in agent traces. **Default: full capture; redaction is opt-in** via configuration, favoring out-of-the-box debuggability for the primary persona (Dana) while leaving redaction available for security-conscious deployments (Priya) |
| 9.5 Overhead | SDK instrumentation SHALL add no more than ~5% overhead to monitored agent execution time |
| 9.6 Portability | Deployment SHALL NOT require kernel-level privileges or a specific OS (in contrast to AgentSight's Linux/eBPF-only approach) |
| 9.7 Licensing | Full codebase SHALL be released under MIT license |

---

## 10. Testing & Validation Plan (Summary)

*(Full detail previously covered in-conversation; summarized here for PRD completeness — see companion testing plan for exhaustive detail.)*

1. **Unit testing** — SDK capture correctness, ingestion schema validation, per-rule logic against hand-crafted event sequences (pytest / Jest CI on every push).
2. **Integration testing** — full Docker Compose stack, real LangGraph + custom app traffic, end-to-end round trip validation.
3. **Anomaly detection validation** — synthetic failure injection harness generating known-positive and known-negative runs; precision/recall/F1 computed per rule; threshold sweep to justify final constants.
4. **Performance/latency testing** — load testing (Locust/k6) at increasing concurrency; p50/p95/p99 latency reporting against the <200ms target.
5. **Overhead testing** — same workload with/without SDK attached; report overhead as a percentage.
6. **Resilience testing** — kill anomaly worker mid-run, restart Redis, simulate slow WebSocket clients; confirm no ingestion interruption/data loss.
7. **Security testing** — confirm API-key rejection, verify TLS termination, basic unauthenticated-access check.
8. **Comparative baseline testing** — same synthetic failure through AgentScope vs. a post-hoc tool (Phoenix/Langfuse); measure time-to-detection as the core novelty proof point.
9. **Usability testing** — unfamiliar observer watches a live failure on the dashboard; can they identify what went wrong without explanation?

---

## 11. Sustainability & Environmental Impact

AgentScope's real-time detection prevents computationally wasteful agent behavior (loops, redundant calls, token spikes) from running to completion, reducing avoidable LLM compute consumption and associated energy use — a live-prevention model rather than a post-hoc measurement model. This aligns primarily with **UN SDG 12 (Responsible Consumption & Production)**, with secondary, more indirect relevance to SDG 9 (Infrastructure) and SDG 13 (Climate Action). Any specific efficiency percentage claims (e.g., reduced redundant calls) must be measured against a defined baseline during testing (§10) before being stated as a finding, not asserted as a target.

---

## 12. Timeline & Milestones (12 Weeks)

| Phase | Weeks | Development Track | Research Track | Milestone |
|---|---|---|---|---|
| Foundation | 1–4 | SDK core, event pipeline, adapters, live dashboard | Literature review, methodology draft | **M1 (Wk4):** SDK + LangGraph adapter complete, live dashboard operational |
| Development | 5–8 | Anomaly detection (6 rules) + validation harness, AWS deployment | System design write-up, evaluation plan | **M2 (Wk8):** All 6 rules validated, full stack deployed on AWS |
| Finalization | 9–12 | Performance benchmarking, hardening, docs, demo video, public release | Results, discussion, manuscript submission | **M3 (Wk12):** Public MIT release; manuscript submitted to target venue |

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| 12-week timeline is aggressive across SDK + backend + frontend + 6 detectors + AWS + manuscript | Milestone checkpoints (M1/M2/M3) built in specifically to surface slippage early; anomaly-detection work assigned to more than one team member to avoid a single-person bottleneck |
| Anomaly rule thresholds currently undefined | Synthetic failure injection harness prioritized early in Month 2, before threshold tuning begins |
| Single EC2 instance = single point of failure | Explicitly accepted as out-of-scope limitation for this capstone; documented as future work (multi-region/HA) |
| <200ms latency claim unproven | Load-testing plan (§10.4) scheduled in Month 3, prerequisite to finalizing the claim in the manuscript |
| Citation/reference completeness | All literature-review citations cross-verified against source (arXiv IDs, authors, dates) prior to submission |

---

## 14. Open Items Before Build Begins
- [x] Decide default behavior for `input`/`output` redaction (§9.4) — **resolved: full capture by default, opt-in redaction**
- [x] Resolve the force-directed vs. hierarchical layout inconsistency between §5.1/§6.2/FR-6 and the original pitch deck — **resolved: hierarchical (dagre), see §5.1, §6.2, FR-6**
- [ ] Draft numeric thresholds for all six anomaly rules are locked as the Sprint 1 starting point (§7); still require empirical validation via the injection harness before being finalized in the manuscript's Evaluation section
- [ ] Confirm target journal/venue for manuscript submission — **deferred to Phase 3 (Weeks 9–12), non-blocking for build**
- [ ] Build synthetic failure injection harness (prerequisite for §10.3 and §10.8)

---

*Companion document: **AgentScope_User_Flows.md** — detailed user journeys from installation through incident response.*
