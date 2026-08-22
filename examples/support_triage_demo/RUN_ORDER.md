# RUN_ORDER — scripted demo sequence

Run with the dashboard open in Live mode (http://localhost:5173) and the
local stack up. Each command from `examples/support_triage_demo/` with
AWS credentials + `AWS_REGION` exported (real Bedrock LLM calls — see README). Wait for each run to finish before starting the next so the
audience can watch each graph build live.

## 1. Establish normalcy — two happy-path tickets

```bash
python main.py HAPPY-BILLING-001
python main.py HAPPY-TECH-002
```

**Say:** "Real LLM classifies the ticket, the right specialist investigates
with its tool, the composer drafts the reply. Note the hierarchy — router,
specialist with its tool calls, composer — and that nothing is flagged.
Observability attached with two lines; the agent code never imported
AgentScope." *(Zero false positives is part of the credibility.)*

## 2. Delegation cycle — strongest visual opener

```bash
python main.py DELEGATION-CYCLE-001
```

**Say:** "The ticket is genuinely ambiguous — billed for a feature that
crashes. Billing correctly says 'not billing', Technical correctly says 'not
technical', and routing bounces back to a previously visited agent —
AgentScope flags the cycle the moment the revisit happens." *(Watch the
nested Billing → Technical → Billing structure and the ⚠ badge appear
live.)*

## 3. Failure loop

```bash
python main.py FAIL-LOOP-002
```

**Say:** "The account store keeps returning an ambiguous record, the agent
does the reasonable thing and retries — four identical calls inside sixty
seconds and AgentScope flags the loop." *(Click the account node → inspect
the retries in the span detail.)*

## 4. Token spike

```bash
python main.py TOKEN-SPIKE-004
```

**Say:** "This customer attached their entire interaction history. The
composer's single LLM call crosses the eight-thousand-token threshold — a
cost and context-hygiene problem surfacing live." *(Inspect the composer
node's token usage.)*

## 5. Timeout — closer (takes ~35s, so run it last)

```bash
python main.py TIMEOUT-003
```

**Say:** "The diagnostic tool hangs past thirty seconds for this workspace —
the pulsing incomplete node and the timeout alert fire while the graph is
still running. AgentScope surfaced all four; it never touched the agent —
detection, not enforcement."

## Optional encore

```bash
python main.py happy   # remaining happy-path tickets — system still normal
```
