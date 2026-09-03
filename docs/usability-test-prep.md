# Usability Test #9 — Controlled Study Pack (Flow 3, PRD §10.9)

**Status: PREPARED, NOT CONDUCTED.** This test requires a real, unfamiliar human observer watching a live failure and explaining unaided what happened. No such session has taken place; no findings exist yet, and none may be written until one does. The `manuscript/` Usability Findings section is intentionally unwritten.

## Minimum formative session

- One observer who has NOT seen AgentScope before (no familiarity with the dashboard or the project).
- ~15 minutes: 2 min brief, ~5 min observation, ~5 min debrief questions, rest buffer.
- A screen showing the dashboard in Live mode (`npm run dev` in `dashboard/`, local stack running) with the failure injection below ready to trigger.

For a manuscript outcome, use the counterbalanced protocol and blank instruments in `manuscript/usability-study/README.md`. One observer is a formative case, not a generalizable study.

## Test scenario

**Failure to inject: repeated tool failures (anomalous node with visible alert).**

The injection ingests a repeating sequence of failing `tool_call` spans for one agent. Verified against the local stack (2026-08-22): the `crashes` rule fires on the very first error span, so the anomalous node (amber, dashed border, ⚠ badge) and its anomaly details in the InspectPanel appear within seconds; with 4+ failures in 60s the failure-loops rule also engages. It runs entirely against the LOCAL stack.

Run this during the session, from the repo root, AFTER telling the observer "an agent is about to misbehave; watch the screen":

```powershell
python -c "
import json, time, uuid, httpx
from datetime import datetime, timezone
s = httpx.Session()
h = {'Authorization': 'Bearer test-key', 'Content-Type': 'application/json'}
for i in range(8):
    now = datetime.now(timezone.utc).isoformat()
    span = {'trace_id':'usability-test','span_id':str(uuid.uuid4()),'parent_span_id':None,
            'span_type':'tool_call','name':'flaky_tool','input':{'attempt':i},'output':None,
            'start_time':now,'end_time':now,
            'status':{'status':'error','exception_details':'tool timeout, retrying'},
            'token_usage':None,'agent_id':'usability-agent'}
    r = s.post('http://localhost/ingest', json=span, headers=h)
    assert r.status_code == 200
    time.sleep(1.5)
print('injection complete')
"
```

(If the failure-loops rule needs more events than 8 to trip at current thresholds, increase the loop count; the rule baseline is 4 calls/60s per PRD §7.)

## The one question (ask verbatim, after the injection completes)

> "In your own words — what just happened on this screen? What would you do next?"

Record the answer verbatim (audio or typed notes). Do not prompt, hint, or ask leading follow-ups before the observer has finished their full explanation.

## Secondary prompts (only AFTER the main question is fully answered)

1. "Which part of the screen told you that?" (probes whether the anomaly state was actually discoverable)
2. "Can you find more detail about the problem?" (probes InspectPanel discoverability — clicking/keyboard-focusing the anomalous node)
3. "Was anything on the screen confusing or redundant?"

## Recording the results

Fill in per session:

| Field | Value |
|---|---|
| Date / observer identifier | |
| Observer's verbatim main answer | |
| Secondary answers (1–3) | |
| Did the observer identify a failure without prompting? (Y/N) |
| Did the observer locate the anomaly detail unaided? (Y/N) |
| Notes | |

**Success criterion (Flow 3):** the observer can explain that an agent component was failing/repeating failures and point to the anomalous node — unaided.

## After the session

Only then draft `manuscript/usability-findings.md` from the recorded answers, citing this pack and the session date. If the observer could NOT explain the failure, that is the finding — record it as such.

Do not replace the participant with a developer, an automated browser check, or an AI-generated response. Automated checks establish interface readiness only.
