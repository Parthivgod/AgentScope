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

## Trace-Indexed Lookup (Sorted Set per Trace)
- **Proposed by:** Track B / Week 7
- **Why it's deferred:** Premature optimization at Sprint 1 scale. Current `/history` relies on scanning XRANGE and in-memory filtering.
- **What it would take:** Adding secondary indexing logic to the ingestion path (e.g. `ZADD trace:{trace_id} <timestamp> <span_id>`).

## Week 9 Load Test Case
- **Proposed by:** Track B / Week 7
- **Why it's deferred:** Requires load-testing harness (scheduled for Week 9).
- **What it would take:** Simulate concurrent `/history` queries + `/ingest` load to confirm ingestion p95 doesn't degrade.
