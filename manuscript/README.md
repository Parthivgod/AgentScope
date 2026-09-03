# AgentScope Manuscript — Working Assembly

Status: synchronized with the local evidence through 2026-09-03. The system, instrumentation, related-work positioning, and quantitative evaluation drafts are assembled. AWS deployment evidence and unfamiliar-human usability results remain deliberately absent.

## Sections

| Section | File | Status |
|---|---|---|
| System Design | `system-design.md` | Synchronized draft |
| Instrumentation Methodology | `instrumentation-methodology.md` | Draft |
| Related Work and Positioning | `related_work_draft.md` | Synchronized draft; citation metadata needs final review |
| Evaluation Results | `evaluation-results.md` | Synchronized through payload-index rerun |
| Evaluation Protocol | `rigorous_evaluation_and_results_guide.md` | Protocol plus current evidence ledger |
| Usability Findings | — | Not written; a real unfamiliar-human session is required |

## Current evidence ledger

| Evidence | Current result | Primary artifact |
|---|---|---|
| Delegation fidelity | 107/107 deterministic scenarios | `2026-08-30-current-build/novelty_evaluation.json` |
| Six anomaly rules | Each 50 TP, 50 TN; precision/recall/F1 1.000 on held-out synthetic cases | `2026-08-31-post-fix/anomaly_validation_postfix.json` |
| Privacy ablation | Full and HMAC: 100 TP/100 TN; literal redaction: 100 FP | `2026-08-30-current-build/privacy_ablation.json` |
| 50-user latency after payload index | Event p95 125.0, 156.8, 125.0 ms; mean 135.6 ms | `2026-09-03-history-payload-index/` |
| Latest three-way overhead | 100 ms/node means: AgentScope 4.81%, Langfuse 5.24%, Phoenix 6.56%; overlapping low-powered intervals | `2026-09-02-replicated/` |
| Live/history convergence | 9/9 bursts; reconnect 20/20 ordered events | `2026-08-31-post-fix/live_history_convergence_postfix.json` |
| Redis restart | 20 pre + 20 post, 40 final, approximately 1 s recovery | `CHANGELOG.md` entry 2026-09-03 14:35 |
| Usability | Not conducted | `docs/usability-test-prep.md` |

Every target is reported alongside the measurement and its scope. Synthetic accuracy is not field accuracy; local performance is not universal production performance; three comparison repetitions do not establish a product ranking.
