# AgentScope — User Flow Document

**Companion to:** AgentScope_PRD.md
**Purpose:** Detail every major end-to-end journey a user takes through AgentScope, from first install to responding to a live incident, so implementation decisions are grounded in actual usage rather than architecture alone.

---

## Personas Referenced in These Flows
- **Dana** — Independent developer, LangGraph-based agent, first-time user
- **Rahul** — Research lab engineer, custom (non-framework) agent code
- **Priya** — Startup backend lead, production deployment, cost/security-conscious

---

## Flow 1 — Installation & SDK Integration (LangGraph Path)

**Persona:** Dana
**Trigger:** Dana's LangGraph agent has silently failed in a loop twice this week; she wants visibility before it happens again.
**Goal:** Get AgentScope observing her existing LangGraph app with minimal code change.

| Step | User Action | System Behavior | Notes / Edge Cases |
|---|---|---|---|
| 1 | Runs `pip install agentscope-sdk` | Package installs; no network calls made yet | Zero external dependency until explicitly configured |
| 2 | Adds `from agentscope import LangGraphAdapter` and attaches it to her existing `StateGraph` instance | Adapter registers a callback handler on the graph's node-transition hooks — **no changes to node logic itself** | This is the "zero-rewrite" moment — worth demoing live in the presentation |
| 3 | Sets `AGENTSCOPE_API_KEY` and `AGENTSCOPE_INGEST_URL` env vars, pointing to her running AgentScope backend | SDK validates the key against the backend on first event send | If invalid: SDK logs a warning locally and **does not block agent execution** — observability failure must never become an availability failure |
| 4 | Runs her agent as normal | On each node transition, the adapter builds a span (per PRD §6.3 schema) and sends it asynchronously to the ingestion endpoint | Async send — agent execution is not blocked waiting on network I/O |
| 5 | Opens the AgentScope dashboard URL in her browser | Dashboard establishes a WebSocket connection; nodes begin appearing as the agent runs | **Success state:** Dana sees her agent's execution graph appear live, in real time, with zero code changes to her actual agent logic |

**Failure/edge paths to design for:**
- Backend unreachable at startup → SDK should buffer briefly and retry, then fail silently (never crash the host agent).
- Agent runs to completion before Dana opens the dashboard → she should still be able to see the full run via historical replay (Flow 5).

---

## Flow 2 — Installation & SDK Integration (Custom Agent Path)

**Persona:** Rahul
**Trigger:** His research agent isn't built on any named framework — just custom orchestration code.
**Goal:** Instrument hand-rolled code with minimal manual annotation.

| Step | User Action | System Behavior | Notes |
|---|---|---|---|
| 1 | Installs SDK (same as Flow 1, Step 1) | — | — |
| 2 | Wraps his own LLM-calling function with `@agentscope.trace` | Decorator intercepts calls transparently, capturing args/return/timing | This is the **explicit** capture path (vs. LangGraph's implicit callback path) |
| 3 | *(Optional)* Enables auto-patching for a known LLM client library (`agentscope.patch(openai)`) | SDK monkey-patches the library's call method at import time | Covers code Rahul didn't write himself (e.g., inside a third-party client) |
| 4 | Runs his agent | Spans are captured and sent identically to Flow 1, Step 4 onward | From this point, both integration paths converge into the same pipeline |

**Design implication:** The decorator and adapter paths must produce **schema-identical spans** — the dashboard and anomaly worker should never need to know which integration method produced an event.

---

## Flow 3 — First Live Monitoring Session

**Persona:** Dana
**Trigger:** Agent is now instrumented (post-Flow 1); she starts a real run and watches it live.
**Goal:** Understand what her agent is doing, in real time, without reading logs.

| Step | User Action | System Behavior |
|---|---|---|
| 1 | Opens dashboard, sees an empty/idle graph | WebSocket connected, awaiting events |
| 2 | Starts her agent | First span arrives → a node appears on the graph, "pulsing" to indicate active execution |
| 3 | Watches the agent call a tool, then reason again | New nodes/edges appear in real time; the dashboard recomputes the hierarchical (dagre) layout as new nodes/edges are added, keeping causal flow direction clear |
| 4 | Hovers over a node | Dashboard shows span detail: input/output (or redacted metadata), duration, token usage |
| 5 | Agent completes | All nodes settle to an "idle/complete" visual state; graph remains on screen (not cleared) |

**Success criteria:** Dana can explain what her agent did, in order, without opening a single log file — this is the usability test described in PRD §10.9.

---

## Flow 4 — Anomaly Detection & Alert Response

**Persona:** Priya
**Trigger:** A production agent enters a failure loop mid-run.
**Goal:** Priya is alerted immediately, understands what's happening, and can act before cost/impact grows.

| Step | System Behavior | User Experience |
|---|---|---|
| 1 | Agent begins repeating the same tool call | Nothing visible yet — under the loop-detection threshold |
| 2 | Repeat count crosses the configured threshold (e.g., 4th identical call within 60s) | Anomaly worker flags the pattern, writes an anomaly event back to the store |
| 3 | Dashboard receives the anomaly flag over WebSocket | The looping node visually changes state (e.g., color/pulse pattern shifts to an alert state) — **distinct from normal "active" pulsing** |
| 4 | Priya, watching or notified, clicks the flagged node | Dashboard surfaces: which rule fired (loop), the repeated call details, and a timeline of the repeated attempts |
| 5 | Priya intervenes (kills the process externally — AgentScope does not auto-kill agents, it is observability, not enforcement) | Trace remains available for post-incident review (Flow 5) |

**Explicit design boundary:** AgentScope **detects and alerts**; it does not autonomously terminate or intervene in the monitored agent. This is worth stating clearly if a panel or user asks "does it stop the agent" — conflating observability with enforcement is scope creep beyond what's defined in the PRD.

**Notification requirement (open item):** The current scope defines *dashboard* alerting. Whether a push notification / webhook / email alert channel is needed for the "away from the dashboard" case is an **open product question** — flag for scoping decision, likely future work given current scope boundaries.

---

## Flow 5 — Historical Trace Review / Post-Incident Debugging

**Persona:** Dana
**Trigger:** A failure happened overnight; she wasn't watching the dashboard live.
**Goal:** Reconstruct exactly what happened, after the fact.

| Step | User Action | System Behavior |
|---|---|---|
| 1 | Opens dashboard, navigates to trace history | FastAPI serves a historical query against Redis Streams' durable log |
| 2 | Selects the failed run by timestamp/trace ID | Full span sequence for that trace is loaded |
| 3 | Dashboard replays the graph's construction in order | Same visual rendering as live mode, but reconstructed from stored events rather than a live WebSocket feed |
| 4 | Dana finds the flagged anomaly node in the replay | Same detail view as Flow 4, Step 4 — consistent UI between live and historical modes |

**Design implication:** Live and historical modes should share the same rendering component — the only difference is the event *source* (WebSocket stream vs. stored query), not the visualization logic itself.

---

## Flow 6 — Deployment & Admin Setup

**Persona:** Priya (as the one standing up the shared team deployment)
**Trigger:** Team wants a shared AgentScope instance rather than everyone running it locally.
**Goal:** Stand up the full stack securely, once.

| Step | User Action | System Behavior |
|---|---|---|
| 1 | Clones the repo, copies `.env.example` to `.env` | — |
| 2 | Sets an API key value and TLS cert paths in `.env` | Config consumed by Nginx/FastAPI at startup |
| 3 | Runs `docker-compose up -d` | Nginx, FastAPI, Redis, Anomaly Worker all start; Nginx terminates TLS and proxies to FastAPI |
| 4 | Distributes the API key + dashboard URL to her team | Each teammate configures their SDK per Flow 1/2, Step 3, pointing at the shared instance |
| 5 | Confirms an unauthenticated request to the ingestion endpoint is rejected | Basic security validation before trusting the deployment with real traffic (ties to PRD §10.7) |

**Explicit boundary to communicate to Priya's team:** this shared instance has **no per-user accounts or RBAC** (out of scope, PRD §5.2) — everyone sharing the API key has equivalent access. If her team needs per-user isolation, that's a documented future-work gap, not a current capability.

---

## Cross-Flow Design Principles (Apply to All Flows Above)

1. **Observability must never risk availability.** Every flow above assumes the SDK fails silently and asynchronously — a broken AgentScope connection should never crash, block, or meaningfully slow the monitored agent.
2. **Live and historical views share one visual language.** A user should never have to learn a second UI for post-incident review — Flow 3 and Flow 5 render identically.
3. **Detection ≠ enforcement**, consistently, across every flow — AgentScope surfaces problems; a human (or a separate system) decides what to do about them.
4. **Zero-rewrite is a first-run promise, not just a slide claim.** Flows 1 and 2 are the literal proof of the "zero-rewrite" claim from the PRD/pitch — they should be the easiest flows to actually demo live to the capstone panel.

---

*Companion document: **AgentScope_PRD.md** — full requirements, architecture, and testing plan this document assumes.*
