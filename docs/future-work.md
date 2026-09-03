## Future Work

Any idea that's plausible but out of current scope (RULES.md §1), or that's in-scope but deferred goes here instead of into the codebase.

<!-- Example format:
## <short title>
- **Proposed by:** <session/date>
- **Why it's deferred:** <out of scope per RULES.md §1 / deferred per Build Plan §X / etc.>
- **What it would take:** <brief note, optional>
-->

## Monitored-Agent Termination Affordance
- **Proposed by:** Dashboard UI redesign / 2026-08-23
- **Why it's deferred:** Out of scope under RULES.md §1 and §3 invariant #7. AgentScope detects and explains anomalies; it must not terminate or otherwise remediate the monitored agent automatically or through a dashboard control.
- **What it would take:** An explicit product-scope and safety-policy change, plus a trustworthy process identity/control contract (the current span schema has no PID or equivalent termination target). Until then, the reference image's “Terminate Agent” control is intentionally omitted.

## Causal Incident Grouping
- **Proposed by:** Delegation-aware adapter review / 2026-08-27
- **Why it's deferred:** Deliberately excluded from the delegation-context and privacy-preserving loop-detection cycle. The review scored it Medium-High effort and not fully novel because causal graph reconstruction and root-cause ranking overlap existing AgentTrace functionality.
- **What it would take:** A separately approved design for grouping causally related flags from the existing six rules, distinguishing initiating signals from downstream symptoms, defining evaluation ground truth, and updating the dashboard without introducing a new anomaly category or enforcement behavior.

## Reconnect Retention and Invalid-Cursor Policy
- **Proposed by:** Production convergence evaluation / 2026-09-03
- **Why it's deferred:** The current cursor catch-up is verified only while referenced Redis stream entries remain retained. The project has no approved long-disconnection retention contract.
- **What it would take:** Define stream-trimming and cursor-expiry semantics, expose a detectable resynchronization response, force an authoritative history snapshot when a cursor is invalid, and test multi-hour disconnections plus Redis restoration.

## Container-Isolated Comparison Telemetry
- **Proposed by:** Replicated three-way comparison / 2026-09-03
- **Why it's deferred:** Current process CPU/RSS excludes product server containers, and host network counters can include unrelated traffic.
- **What it would take:** Pin identical resource limits, record per-container CPU/RSS/network/storage for AgentScope, Langfuse, and Phoenix, and repeat with enough independent hosts or processes for useful uncertainty estimates.
