# AgentScope — Manuscript (Working Assembly)

Status: assembled Weeks 9-12 (local-complete, pre-AWS). Sections that genuinely depend on a live AWS deployment (deployed-instance experience, Flow 6 claims) are deliberately absent and will be added by the deferred AWS Go-Live pass.

## Sections

| Section | File | Status |
|---|---|---|
| System Design | `system-design.md` | Draft (Track B) |
| Instrumentation Methodology | `instrumentation-methodology.md` | Draft (Track A) |
| Evaluation Results | `evaluation-results.md` | Draft (Track B) |
| Usability Findings | — | **Not written.** Requires the real observer session (see `docs/usability-test-prep.md`); will be drafted only from recorded answers. |

## Number-tracing audit (RULES.md §6) — performed 2026-08-22

Every quantitative claim below was checked against the CHANGELOG entry and artifact that produced it. Numbers without a traceable source were cut.

| Claim in manuscript | Value | Source (CHANGELOG entry) |
|---|---|---|
| Event-to-dashboard p95 @50u | 156ms (n=300) | [2026-08-21 23:50] Week 9 Track B |
| Pre-optimization p95 @50u | 3600ms | [2026-08-21 23:50] Week 9 Track B |
| HTTP agg p95 @50u (saturation) | 320ms (reported as measured) | [2026-08-21 23:50] Week 9 Track B |
| SDK overhead, demo workload | +3.3ms abs; +79.7%/+60.7% rel | [2026-08-21 23:30] Week 9 Track A |
| SDK overhead, LLM-bound | +3.6ms abs; +1.76% mean/median | [2026-08-21 23:30] Week 9 Track A |
| Phoenix comparison | +201.7%/+2.6% vs AgentScope +93.1%/−0.5% | [2026-08-22 01:20] Week 10 Track B |
| Resilience outcomes | 30/30 workloads; 0 lost events; ~2s recovery; 48/52ms unchanged | [2026-08-22 00:45] + [2026-08-22 01:20] |
| Accessibility | axe 0 violations; Lighthouse a11y 100 | [2026-08-21 00:20] + [2026-08-22 01:40] Track C |
| Precision/recall per rule | **No claim made** — targets only; validation incomplete | RULES.md §6 |
| Sustainability % | **No claim made** — never measured | RULES.md §6 |

The <5% overhead and <200ms latency targets are stated as targets, with the measured values (including misses and their scope) alongside — per RULES.md §6.
