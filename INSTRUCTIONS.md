# AgentScope — Agent Operating Instructions (INSTRUCTIONS.md)

**Audience:** Any coding agent (Antigravity, Claude Code, etc.) working autonomously or semi-autonomously in this repository.
**Read alongside:** `RULES.md` (hard guardrails — read that one first), `AgentScope_PRD.md`, `AgentScope_Build_Plan.md`, `AgentScope_User_Flows.md`.

This file is about **how to work**, not what to build. `RULES.md` tells you the boundaries. This file tells you the process for operating inside them.

---

## 1. Before You Start Any Task

1. Re-read `RULES.md`. Assume it's current even if it feels repetitive — it's short on purpose.
2. Identify which track owns the area you're touching (Build Plan §3–§4): SDK/`sdk/` (Track A), backend+worker+infra/`backend/` `worker/` `infra/` (Track B), or dashboard/`dashboard/` (Track C). If your task spans tracks, say so explicitly in your plan before starting.
3. Check `CHANGELOG.md` (see §3) for recent related work — don't duplicate or silently override something another session already did.
4. Check `docs/future-work.md` — if the task looks like it might be an out-of-scope item (RULES.md §1), confirm it's not there already before building it.

---

## 2. When to Ask vs. When to Proceed

**Ask a clarifying question before proceeding when:**
- The task conflicts with, or is ambiguous against, anything in `RULES.md`.
- The task would require changing a "Locked Decision" (RULES.md §2) — schema shape, layout library, redaction default, LangGraph hooking mechanism, target LLM client for `patch()`, or the repo/track structure.
- The task implies AgentScope taking an action on the monitored agent (auto-kill, auto-restart, etc.) — this is never assumed, always confirmed, and per RULES.md §1 almost certainly should be declined and logged as future work instead.
- You're about to assert a performance/accuracy number (latency, overhead, precision/recall) that hasn't actually been measured this session (RULES.md §6).
- Two source documents (PRD / Build Plan / User Flows) appear to disagree and you can't resolve it from context — don't guess which one is authoritative; ask.
- A requirement is genuinely underspecified in a way that would waste real effort if you guess wrong (e.g., exact API response shape not covered anywhere).

**Don't ask, just proceed (using your best judgment and stating the assumption inline in your commit/log entry) when:**
- The ambiguity is a minor implementation detail with no cross-track dependency (variable naming, internal file layout within your own track's directory, log message wording).
- The PRD/Build Plan already gives a clear enough default and the only open question is "how exactly," not "what."
- Asking would just be deferring a decision you're equipped to make — state the assumption and move on.

When you do ask, ask **one focused question at a time** where possible, and say what you'd do by default if you don't hear back, so the human can either confirm or redirect quickly rather than having to design the answer from scratch.

---

## 3. Change Logging — Required for Every Session

Maintain a single running `CHANGELOG.md` at the repo root. This is not optional and not a "nice to have" — treat it as part of the definition of done for any task.

**Format** (append-only, newest entry at the top):

```markdown
## [YYYY-MM-DD HH:MM] — <short title> — Track <A/B/C/Shared> — <agent/session id if known>

**What changed:**
- Bullet list of concrete changes (files touched, functions added/modified, config changed)

**Why:**
- One or two lines tying this back to a specific PRD requirement, Build Plan task, or user flow (e.g. "FR-2", "Build Plan §4 Track A Week 2", "Flow 4 Step 3")

**Assumptions made (if any):**
- Anything you decided without asking, and why you judged it safe to decide (per §2 above)

**Open questions / follow-ups (if any):**
- Anything flagged for human review, or logged to `docs/future-work.md`

**Tests added/run:**
- What was tested, and the result
```

Rules for the changelog itself:
- Every commit-worthy unit of work gets an entry, even small ones. A missing changelog entry for a real code change is itself a defect to fix.
- Never edit or delete a past entry to "clean it up" — if something in a past entry turned out to be wrong, add a new entry noting the correction, don't rewrite history.
- If you touch `RULES.md` itself (only on explicit human instruction — see RULES.md §7), the changelog entry must say so prominently and quote which rule changed and why.

---

## 4. Cross-Track Coordination

The three tracks (SDK / Backend+Worker+Infra / Dashboard) are designed to be buildable in parallel but share one contract: the `Span`/`Trace` schema in `sdk/agentscope/schema.py` (Build Plan §1 Decision 2, §3).

- If your task would change that schema, treat it as a breaking, cross-track change: flag it explicitly, don't just edit it and move on, and note in the changelog which other tracks' code may now need review.
- Respect the integration checkpoints in Build Plan §5 (Weeks 1, 3, 4/M1, 6, 8/M2, 11–12/M3). If you're doing work that's supposed to land at one of these checkpoints, say so in your task plan so a human can sequence it correctly against the other tracks.
- If you find yourself blocked because an upstream track's piece isn't ready, say that explicitly rather than working around it with a throwaway mock that might quietly become permanent. A clearly-labeled temporary mock, logged as such, is fine; a silent one is not.

---

## 5. Working Style Expectations

- **Small, reviewable units of work.** Prefer several focused changes with their own changelog entries over one large undifferentiated change.
- **State your plan before large or ambiguous tasks.** For anything more than a small fix, briefly outline what you're about to do and why before doing it, so a misunderstanding is caught early rather than after significant work.
- **Don't silently expand scope.** If while doing task X you notice task Y that seems worth doing, note it (in the changelog's "Open questions / follow-ups" or in `docs/future-work.md`) rather than doing it unasked, unless it's trivially part of X.
- **Cite the source doc.** When implementing a requirement, reference which PRD section / FR / NFR / Build Plan task / User Flow step it maps to. This keeps traceability intact as the codebase grows past what any one person can hold in their head.
- **Provisional numbers stay provisional.** If you implement one of the six anomaly rule thresholds, comment in code that it's a Sprint-1 starting value pending injection-harness validation (RULES.md §6) — don't let a placeholder read as a finished, tuned constant.

---

## 6. `docs/future-work.md` — Where Good Ideas Go to Wait

Any idea that's plausible but out of current scope (RULES.md §1), or that's in-scope but deferred (e.g., a second LLM client for `patch()` beyond OpenAI, a statistical timeout variant beyond the fixed ceiling), goes here instead of into the codebase:

```markdown
## <short title>
- **Proposed by:** <session/date>
- **Why it's deferred:** <out of scope per RULES.md §1 / deferred per Build Plan §X / etc.>
- **What it would take:** <brief note, optional>
```

This keeps good ideas from being lost, without letting them quietly creep into "in scope" by being implemented before anyone decided they should be.

---

## 7. Quick Reference — Where Things Live

| Need to know... | Look in... |
|---|---|
| Is this in scope at all? | `RULES.md` §1 |
| Is this decision already locked? | `RULES.md` §2 |
| Full requirement detail / rationale | `AgentScope_PRD.md` |
| Week-by-week task breakdown, track ownership | `AgentScope_Build_Plan.md` |
| What should this look like from a user's perspective? | `AgentScope_User_Flows.md` |
| What changed and why, historically | `CHANGELOG.md` |
| Good ideas we're not building yet | `docs/future-work.md` |

---

*If anything in this file or `RULES.md` seems to be blocking legitimate, in-scope work, that's worth flagging too — these documents are meant to prevent scope creep and rework, not to prevent progress. Say so, and ask.*
