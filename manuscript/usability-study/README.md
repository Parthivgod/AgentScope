# Usability Study Protocol and Status

**Status: materials validated; no participant data collected.** This directory is intentionally free of invented observations. A researcher must obtain any required ethics/departmental approval, recruit unfamiliar participants, collect consent, and record the sessions before a manuscript usability result can be written.

## Research question and primary outcome

Can a developer unfamiliar with AgentScope correctly diagnose an injected multi-agent failure using the dashboard, and how does diagnosis compare with a baseline trace/log view?

Primary outcome: correct diagnosis under the predefined rubric. Secondary outcomes: time to correct diagnosis, affected-agent/tool identification, delegation-path reconstruction, evidence location, wrong-node selections, hints, confidence, and SUS.

## Design

- Within-subject comparison: AgentScope dashboard versus a frozen baseline view selected before recruitment.
- Counterbalance interface order (AB/BA) and rotate difficulty-matched scenarios.
- Use separate trace identifiers and reset storage between tasks.
- Begin with a pilot; determine the final sample size from the pilot effect/variance and planned analysis. Do not choose a convenient sample and imply statistical power afterward.
- Recruit Python or agent-system developers who have not used AgentScope. Record experience bands, not unnecessary identity data.

## Standardized session

1. Assign a pseudonymous participant ID and record consent version.
2. Read the same neutral briefing; do not name the anomaly or expected rule.
3. Give a two-minute interface familiarization using a non-study trace.
4. Start the assigned condition and scenario; start the timer when evidence first becomes visible.
5. Ask: “In your own words, what happened, which component was involved, and what would you do next?”
6. Stop the timer at the first rubric-correct diagnosis or at the predefined timeout.
7. Only after the unprompted answer, ask the secondary evidence and confusion prompts.
8. Repeat with the other condition and a matched scenario.
9. Administer SUS once per evaluated interface and record open comments.

## Scoring rubric

Score the primary diagnosis correct only when the participant independently identifies all required elements: a failure/repetition occurred, the affected agent or tool, the failure class at the scenario's intended granularity, and one visible supporting signal. Partial elements belong in separate columns; do not retrospectively relax the criterion. Record failures, timeouts, hints, and missing recordings.

## Data handling and analysis

- Use `observations.csv`; one row per participant-condition-scenario trial.
- Keep recordings outside Git. Store only de-identified derived data here if consent permits.
- Preserve exclusions and protocol deviations. Never delete unsuccessful trials.
- Report numerator/denominator task success with an interval, paired time differences with participant as the unit, SUS descriptively with uncertainty, and order/scenario effects.
- Have two reviewers code qualitative themes when possible; otherwise report the single-coder limitation.
- Do not claim comparative superiority from a formative one-person run.

## Readiness gate

Before the first participant: production dashboard build and lint pass; demo-readiness test passes; both scenarios have been rehearsed without a participant; timer/event definitions are frozen; baseline and AgentScope screenshots/configurations are archived; consent and retention decisions are recorded.

After collection, create a dated immutable raw-data directory, record the tested commit and environment, run an analysis script that regenerates tables/figures, and only then add `manuscript/usability-findings.md`.
