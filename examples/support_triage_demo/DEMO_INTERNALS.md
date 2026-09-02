# Support-Triage Demo Internals

This document explains the current implementation of `examples/support_triage_demo/`, including the mechanics behind its four deliberately anomalous tickets. It distinguishes the application's real model work from its synthetic fixture data and calls out places where the current code differs from the surrounding documentation or historical design claims.

The directory no longer has its own `README.md`: the consolidation recorded in `CHANGELOG.md:88-104` moved its setup documentation to the root `README.md:105-131`. `RUN_ORDER.md` points there explicitly (`RUN_ORDER.md:3-6`).

## 1. Architecture Overview

### State and graph wiring

The graph carries a `TriageState` containing the ticket identity and text, the router's selected `route`, accumulated `specialist_notes`, an optional `history`, and the final `response` (`agent.py:95-103`). `make_initial_state()` copies `subject`, `body`, and optional `history` from `TICKETS` (`agent.py:275-278`).

`build_graph()` constructs and compiles this exact `StateGraph` (`agent.py:254-272`):

```text
START
  |
  v
router -- route == "billing"   --> billing   --+
       -- route == "technical" --> technical --+--> composer --> END
       -- route == "account"   --> account   --+
```

The five registered nodes are `router`, `billing`, `technical`, `account`, and `composer` (`agent.py:255-260`). The concrete edges are:

- `START -> router` (`agent.py:262`).
- A conditional edge from `router`, using `lambda s: s["route"]`, with the explicit mapping `billing -> billing`, `technical -> technical`, and `account -> account` (`agent.py:263-267`).
- One unconditional edge from each specialist node to `composer` (`agent.py:268-270`).
- `composer -> END` (`agent.py:271`).

The router makes a real model call with the ticket subject and body. It normalizes any response containing `bill` to `billing`, any response containing `account` to `account`, and every other response to `technical` (`agent.py:108-123`). The final fallback is therefore Technical, not an error or a retry.

At the graph level, exactly one of the three specialist nodes is selected. The Billing/Technical ping-pong used by the delegation-cycle fixture does **not** add more StateGraph edges. It happens recursively inside the selected specialist node through nested `RunnableLambda` calls named `BillingAgent` and `TechnicalAgent` (`agent.py:189-216`). This distinction matters when reading the execution tree: the top-level path is still Router -> one specialist node -> Composer, while additional specialist hand-offs appear as nested child runs beneath that selected node.

Each ordinary specialist performs a graph-controlled tool call and then a real model call:

- Billing calls `check_billing_history`, asks the model to interpret it, and may hand off to Technical only when both the tool result contains `NO_BILLING_HISTORY` and the model emits the exact token `REROUTE_TECHNICAL` (`agent.py:155-170`).
- Technical calls `run_diagnostic`, asks the model to interpret it, and may hand off to Billing only when both the tool result contains `DIAG_CLEAN` and the model emits `REROUTE_BILLING` (`agent.py:173-184`).
- Account calls `lookup_account`, retrying ambiguous results up to five times, and then asks the model for an answer or next step (`agent.py:227-241`).

The composer joins the specialist notes, appends ticket history when present, and makes one final real model call under a prompt requiring a concise, empathetic, specific customer reply (`agent.py:147-150`, `agent.py:244-251`).

### Zero-rewrite AgentScope attachment

The agent implementation itself has no AgentScope import and no telemetry calls: its imports are LangChain/LangGraph, the three local tools, and the ticket fixtures (`agent.py:20-30`). None of `router_node`, `billing_node`, `technical_node`, `account_node`, or `composer_node` contains AgentScope-specific behavior. Their `RunnableConfig` arguments are normal LangChain configuration objects used to propagate configuration into child tool/runnable calls; they are not coupled to a particular observer.

All observability is attached in `main.py`:

```python
adapter = LangGraphAdapter(
    agent_id="support-triage",
    trace_id=trace_id,
    agent_id_by_run=AGENT_ID_BY_RUN,
)
result = await graph.ainvoke(
    make_initial_state(ticket_id),
    config={"callbacks": [adapter]},
)
```

These are `main.py:74-81`. The adapter import is also confined to `main.py:26`. This implements RULES.md Decision #5 exactly: callback-tracer attachment through `config["callbacks"]`, with no monkey-patching or observability branches in the node logic (`RULES.md:39-42`).

`agent_id_by_run()` maps graph nodes, nested specialist runs, the Bedrock model, and tools to distinct AgentScope `agent_id` values (`main.py:31-60`). This is not needed to execute the agent; it makes the emitted hierarchy semantically meaningful. In particular, assigning tools their own identities prevents a tool child from looking like an immediate revisit of its owning agent, while mapping both `billing` and `BillingAgent` to `billing-agent` lets a genuine nested return to Billing satisfy the delegation-cycle detector. Unknown LangGraph run names receive `graph-internal-<name>` rather than the root identity (`main.py:53-57`). The changelog records that this mapping was added after shared identities caused false cycle alerts on normal traffic (`CHANGELOG.md:127-140`).

### Bedrock model and credentials

The current client is instantiated once at module import in `agent.py:65-70`:

```python
llm = ChatBedrockConverse(
    model=MODEL,
    region_name=AWS_REGION_DEFAULT,
    temperature=0,
    max_tokens=1024,
)
```

`MODEL` is `TRIAGE_MODEL` when set, otherwise `openai.gpt-oss-120b-1:0`; `AWS_REGION_DEFAULT` is `AWS_REGION` when set, otherwise `us-east-1` (`agent.py:38-40`). Thus the default is GPT-OSS 120B through Amazon Bedrock in `us-east-1`, using `langchain_aws.ChatBedrockConverse` (`agent.py:26`). Temperature is zero for relatively stable classification, and completion output is capped at 1,024 tokens so the reasoning model does not unnecessarily approach the 30-second anomaly threshold (`agent.py:62-70`). The graph invokes tools itself, so the model is used only for plain text input/output; it is not asked to perform Bedrock/LangChain tool calling (`agent.py:32-37`, `CHANGELOG.md:127-133`).

No access key is passed to `ChatBedrockConverse` in code. The underlying AWS/Boto credential provider reads standard AWS configuration, while this entry point deliberately requires `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to be present in the environment before it will run (`main.py:63-68`). `AWS_REGION` is read from the environment but has the `us-east-1` fallback above. The root setup also requires the AgentScope stack and its `AGENTSCOPE_API_KEY`/`AGENTSCOPE_INGEST_URL` configuration (`README.md:105-120`).

Every classification, specialist interpretation, and final draft calls this real Bedrock client through `ask_llm()` (`agent.py:87-90`). `_content_text()` handles Bedrock Converse's list-of-content-blocks response and joins its text fields (`agent.py:74-84`).

## 2. Tool Layer

All three tools are LangChain `@tool` functions, but they are local synthetic functions rather than clients for a billing database, diagnostic service, or account store (`tools.py:1-11`). They do not read a separate mocked database or even import `tickets.py`; their entire data source is hard-coded string data selected from the supplied `ticket_id`. Their return type is always a plain string, not a structured object.

### `check_billing_history(ticket_id)`

For ordinary tickets it returns a `BILLING_OK` string describing two invoices, the most recent paid invoice (`INV-77413`, `$49.00`), and a `$12.40` proration (`tools.py:14-24`). This is the normal well-behaved return shape:

```text
BILLING_OK: 2 invoices on file, most recent paid in full ... One proration ...
```

Only a `ticket_id` beginning with `DELEGATION-CYCLE` receives the poison `NO_BILLING_HISTORY` result.

### `run_diagnostic(ticket_id)`

For ordinary tickets it immediately returns a `DIAG_OK` string saying that a stale sync lock was found and cleared and sync should resume within five minutes (`tools.py:27-42`):

```text
DIAG_OK: workspace healthy; a stale sync lock was found and cleared ...
```

The `DELEGATION-CYCLE` prefix instead returns `DIAG_CLEAN`, and the `TIMEOUT` prefix sleeps for 31 seconds before returning `DIAG_TIMEOUT_PATH`.

### `lookup_account(ticket_id)`

For ordinary tickets it returns one `ACCOUNT_OK` string containing a Pro/active/MFA-enabled/us-east account record (`tools.py:45-53`):

```text
ACCOUNT_OK: plan=Pro, status=active, mfa=enabled, region=us-east.
```

Only a `ticket_id` beginning with `FAIL-LOOP` receives the repeatable `AMBIGUOUS` result.

## 3. Happy-Path Tickets

The happy paths are declared in `tickets.py:15-38`; `HAPPY_PATH` is derived by selecting every ID beginning with `HAPPY` (`tickets.py:83`). Each is intended to take the same basic path:

1. Router: one real GPT-OSS 120B call classifies the ticket.
2. Selected specialist: one local tool call, followed by one real GPT-OSS 120B call interpreting its result.
3. Composer: one real GPT-OSS 120B call writes the customer response.

That is normally **three real LLM calls and one tool call per ticket**. Because the model is real, wording and latency are not fixture-controlled. The response is stored in `state["response"]`; the CLI prints only its character count, not the draft text (`main.py:79-82`). The expected content below therefore describes the prompt-driven result rather than a fixed golden string.

| Ticket | Expected route | Normal result |
|---|---|---|
| `HAPPY-BILLING-001` | Billing | Billing sees the normal invoice/proration record, reasons about the reported duplicate July charge, and the composer drafts an empathetic billing response with an investigation/refund-oriented next step. |
| `HAPPY-TECH-002` | Technical | Technical sees `DIAG_OK` with the stale sync lock cleared, relates it to the failed Export behavior, and the composer drafts a concise recovery/follow-up response. |
| `HAPPY-ACCOUNT-003` | Account | Account receives the normal active Pro account record on its first lookup, so the retry loop exits immediately; the composer drafts an email-change/account-verification next step. |
| `HAPPY-BILLING-004` | Billing | Billing receives the normal billing history and reasons about Pro versus Team pricing and mid-cycle switching; the composer turns those findings into a customer-facing plan answer. |

These four fixtures exercise all three routes, including two different Billing intents, without any poison markers, retry-producing ambiguity, artificial delay, or bloated history. They are explicitly the false-positive check (`tickets.py:1-10`): normal nested LLM/tool activity must leave `delegation_cycles`, `failure_loops`, `timeouts`, and `token_spikes` silent. Historical live verification recorded zero false positives across all four (`CHANGELOG.md:135-140`), and the subsequent replay fix verified the same zero-anomaly result in historical mode (`CHANGELOG.md:66-71`). That evidence is historical, not a guarantee that a real network/model call can never be slow.

## 4. Poison Tickets

RULES.md Decision #3 fixes the Sprint-1 starting thresholds at the PRD draft values and says they remain provisional (`RULES.md:35-40`). The worker's current concrete values are four matching calls in 60 seconds, a duration over 30 seconds, and either more than 8,000 tokens in one call or more than 20,000 in one minute (`worker/rules/engine.py:7-14`). Delegation-cycle detection has no numeric threshold: it fires when the current span's `agent_id` already occurs in its ancestor chain (`worker/rules/delegation_cycles.py:20-55`).

### `DELEGATION-CYCLE-001` -> `delegation_cycles`

**Injection.** The ticket text is intentionally mixed—charged for a feature that crashes (`tickets.py:41-51`)—but the injected failure is in two tool branches:

```python
if ticket_id.startswith("DELEGATION-CYCLE"):
    return "NO_BILLING_HISTORY: ... very likely NOT a billing issue."
```

from `tools.py:17-21`, and:

```python
if ticket_id.startswith("DELEGATION-CYCLE"):
    return "DIAG_CLEAN: ... no technical defect reproduced."
```

from `tools.py:30-34`.

**Execution.** Assuming the real router selects Billing or Technical, the sequence is symmetric:

1. The router makes one real Bedrock call and selects one of those two teams.
2. The first specialist calls its poisoned local tool once. Billing receives “not billing”; Technical receives “no technical defect.”
3. The first specialist makes a **real** Bedrock call. A hand-off occurs only if that real response follows the prompt and ends with the required `REROUTE_*` token as well as the tool marker being present (`agent.py:128-140`, `agent.py:166-169`, `agent.py:182-183`).
4. `_reroute()` waits one second, appends the actual model reply to the correspondence, and invokes the other specialist as a nested named runnable (`agent.py:189-216`). The other specialist calls its poisoned tool once and makes another **real** Bedrock call over the growing correspondence.
5. On the next hand-off, the first specialist is entered again as a nested run. Its tool result is reused from shared state (`agent.py:155-161`, `agent.py:173-177`), so the revisit does not create a third tool call.

At that third specialist consultation—the first revisit—the new `billing-agent` or `technical-agent` span has an ancestor carrying the same `agent_id`. Because the adapter emits active spans on run creation, the delegation rule can flag the revisit as soon as that nested run begins. Before this point there have normally been **three real LLM calls total** (router plus two specialist calls) and **two actual tool calls**. This rule is path-based; the numeric thresholds in Decision #3 do not apply to it.

The run does not stop when AgentScope detects the anomaly. `_reroute()` permits depths 0, 1, 2, and 3, then refuses another hand-off when `depth >= MAX_HANDOFF_DEPTH` (`agent.py:187-216`). A fully compliant ping-pong therefore performs four specialist LLM calls, two cached tool lookups total, and then one composer LLM call: approximately **six real LLM calls and two tool calls for the full ticket**. This is an application guardrail; AgentScope remains detection-only, as required by `RULES.md:51-58`.

**Real versus fixture.** Every routing, specialist, and composer LLM call is a real GPT-OSS 120B Bedrock request doing real classification/reasoning/drafting. The two returned tool facts for this ticket ID are the rigged fixtures. The hand-off also depends on the real model obeying the exact reroute instruction; its response is not mocked.

### `FAIL-LOOP-002` -> `failure_loops`

**Injection.** The fixture asks for an account check after a failed password reset (`tickets.py:53-60`). The exact local tool branch is:

```python
if ticket_id.startswith("FAIL-LOOP"):
    return "AMBIGUOUS: account record incomplete (fields missing). Retry advised."
```

(`tools.py:48-52`). The same input deterministically returns the same incomplete record on every invocation.

**Execution.** Assuming the real router selects Account:

1. The router makes one real Bedrock classification call.
2. `account_node()` initializes `result = "AMBIGUOUS"` and runs `for attempt in range(5)` (`agent.py:227-233`).
3. Each iteration invokes `lookup_account` with the identical input `{"ticket_id": "FAIL-LOOP-002"}`. Because the result always contains `AMBIGUOUS`, none breaks at `agent.py:234-235`; every iteration, including the fifth, sleeps 0.75 seconds (`agent.py:236-239`). Five actual tool invocations occur.
4. Only after all retries does Account make one **real** Bedrock call using the final ambiguous result, and Composer makes another **real** Bedrock call (`agent.py:240-251`). The normal full-ticket count is therefore three real LLM calls and five fixture tool calls.

The detector hashes `span.name` plus sorted `span.input`, groups by `agent_id`, keeps a 60-second window, and flags when the current signature count is at least four (`worker/rules/failure_loops.py:18-55`). The adapter maps all these tool runs to `account-lookup-tool` (`main.py:45-49`), so their signatures match.

There is a subtle but important current behavior: `LangGraphAdapter` emits each run once on creation and again on completion (`sdk/agentscope/adapters/langgraph.py:103-111`), and the worker evaluates both events. Consequently, on a fresh worker the “four identical calls” counter reaches four on the **completion event of the second actual tool invocation**, not on the fourth invocation. The code still executes all five retries, producing ten matching span events; the changelog's live observation explicitly reported the signature as seen 10 times (`CHANGELOG.md:135-140`). This differs from the simplified intended description “four identical calls inside 60 seconds”; see Discrepancies Noticed.

**Real versus fixture.** The router, Account's interpretation, and Composer are real GPT-OSS 120B calls. Only the five repeated account-store results are rigged strings. No model response is forced, and there is no LLM call inside each retry iteration.

### `TIMEOUT-003` -> `timeouts`

**Injection.** The technical ticket asks for a workspace diagnostic (`tickets.py:62-67`). Its tool has this exact prefix branch:

```python
if ticket_id.startswith("TIMEOUT"):
    time.sleep(31)
    return "DIAG_TIMEOUT_PATH: diagnostic eventually completed after a long hang."
```

(`tools.py:35-40`). The injected condition is real elapsed wall time in the local tool call, not a fabricated duration field.

**Execution.** Assuming the real router selects Technical:

1. The router makes one real Bedrock classification call.
2. Technical invokes `run_diagnostic` once. The actual tool execution sleeps for 31 seconds.
3. The timeout ceiling is 30 seconds, and the detector uses the strict condition `duration > ceiling_seconds` (`worker/rules/timeouts.py:8-21`). The completed tool span therefore crosses the threshold by roughly one second and is flagged after that single actual tool invocation returns.
4. Technical then makes a **real** Bedrock call over `DIAG_TIMEOUT_PATH`; it is not a `DIAG_CLEAN` result, so it does not enter the Billing hand-off branch. Composer makes one final **real** Bedrock call. The usual total is three real LLM calls and one deliberately slow fixture tool call.

The worker has no periodic timeout tick. A just-created active span is evaluated immediately and will not yet be 30 seconds old; the first reliable alert comes when the 31-second tool span completes (`worker/rules/timeouts.py:13-33`). The graph is still running at that point because specialist reasoning and composition follow. Longer-lived parent spans can also exceed 30 seconds and receive timeout flags as they finish; live verification recorded the tool and cascading parent spans at approximately 37.9 and 41.4 seconds (`CHANGELOG.md:135-140`).

**Real versus fixture.** All three LLM calls are real GPT-OSS 120B requests. Only this ticket ID's diagnostic behavior is rigged: the local function deliberately waits 31 seconds and then returns its fixed result. The LLM timing is not forged.

### `TOKEN-SPIKE-004` -> `token_spikes`

**Injection.** Unlike the other three poison tickets, this one has no special branch in any tool. Its fixture is the `history` field in `tickets.py`, built as a header plus the same synthetic interaction-log sentence repeated 1,100 times (`tickets.py:69-79`):

```python
"history": (
    "PREVIOUS INTERACTION LOG (excerpt):\n"
    + ("Customer opened ticket about invoice discrepancies, ... reopened.\n" * 1100)
)
```

The composer explicitly appends this history to its user prompt when it is non-empty (`agent.py:244-250`). This is a rigged input/context fixture, not a rigged tool response.

**Execution.** The expected route is Billing based on the invoice-dispute subject:

1. Router makes a real Bedrock classification call. Its prompt contains only subject/body, not the large history (`agent.py:114-115`).
2. Billing makes one normal `check_billing_history` tool call and one real Bedrock specialist call. The specialist prompt also does not include `state["history"]`.
3. Composer receives the accumulated notes and appends the approximately 100 KB history, then makes one **real** Bedrock call over that genuinely large input.
4. On the completed composer LLM span, the adapter extracts Bedrock's actual usage metadata (`sdk/agentscope/adapters/langgraph.py:53-81`). The token rule flags a single call only when `total_tokens > 8000`, not when it equals 8,000 (`worker/rules/token_spikes.py:17-28`). Thus the rule fires after the one oversized Composer request completes—the third real LLM call in the expected run. `max_tokens=1024` caps generated output, not the input history, so it does not prevent the spike.

The fixture size is pinned by an offline test requiring the ticket text/history to exceed 8,000 `cl100k_base` tokens (`test_support_demo.py:43-50`). In the recorded Bedrock run, the composer reported 37,984 prompt plus 485 completion tokens (38,469 total), comfortably above the threshold (`CHANGELOG.md:66-69`).

**Real versus fixture.** The Router, Billing, and Composer requests are real GPT-OSS 120B calls, and the anomalous token count comes from the real Bedrock usage report for the actual large prompt. What is rigged is the synthetic 1,100-line ticket-history fixture. The Billing tool follows its normal path; there is no ticket-specific tool-layer response for this anomaly.

## 5. Safety Guardrails

### Fifteen-call LLM ceiling

`MAX_LLM_CALLS = 15` and the shared `CallBudget` are defined at `agent.py:38-59`. Every call flows through `ask_llm()`, which runs `budget.check()` immediately before `llm.ainvoke()` (`agent.py:87-90`). `run_ticket()` resets `budget.used` to zero before each ticket (`main.py:71-73`), and `main()` runs tickets sequentially (`main.py:110-112`).

The first 15 LLM calls are allowed. On an attempted sixteenth call, `check()` sees `used >= limit` and raises `CallBudgetExceeded` before contacting Bedrock. `run_ticket()` catches that exception and prints `ABORTED by demo safety net: ...` (`main.py:80-84`). It does not cap tool calls, terminate a Bedrock call already in progress, or represent AgentScope enforcement. It is demo-application cost containment, consistent with the detection-versus-enforcement boundary in `RULES.md:57`.

### Runtime and credential requirements

The current root instructions require:

- The local AgentScope stack and dashboard when demonstrating live traces (`README.md:12-50`, `RUN_ORDER.md:3-6`).
- `langgraph`, `langchain-core`, `langchain-aws`, Boto3, and the local AgentScope SDK (`requirements.txt:1-6`).
- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`; the README also tells the operator to set `AWS_REGION=us-east-1` (`README.md:105-116`).
- `AGENTSCOPE_API_KEY` (the local example uses `test-key`) and `AGENTSCOPE_INGEST_URL` (`README.md:110-116`).

These are billable, networked Bedrock calls. A full eight-ticket run was historically estimated at a few cents (`README.md:108`), while the hard ceiling and 1,024-token output limit bound accidental spend and latency. The price statement is a historical/demo estimate, not a calculation performed by this document.

## 6. Run Order

`RUN_ORDER.md` recommends running one ticket at a time with the dashboard already open in Live mode, waiting for completion so the audience can watch each hierarchy develop (`RUN_ORDER.md:3-6`):

1. `HAPPY-BILLING-001`, then `HAPPY-TECH-002`: establish normal behavior, show two routes, demonstrate Router -> Specialist/tool -> Composer, and make the absence of false-positive flags visible (`RUN_ORDER.md:8-19`).
2. `DELEGATION-CYCLE-001`: use the most visually legible anomaly as the opener—the nested Billing/Technical ping-pong and revisit badge (`RUN_ORDER.md:21-32`).
3. `FAIL-LOOP-002`: inspect repeated account lookup spans and the failure-loop evidence (`RUN_ORDER.md:34-43`).
4. `TOKEN-SPIKE-004`: inspect the Composer's actual Bedrock token usage and show a cost/context-hygiene issue (`RUN_ORDER.md:45-54`).
5. `TIMEOUT-003`: close with the slow case because the injected sleep makes it take roughly 35 seconds end to end (`RUN_ORDER.md:56-65`). It also reinforces that AgentScope reports the condition without controlling the monitored application.
6. Optional encore: run `python main.py happy` to show normal behavior again (`RUN_ORDER.md:67-71`).

The ordering is a presentation choice rather than a dependency between tickets: establish trust with normal traffic, lead the anomaly sequence with the strongest graph visual, keep the faster anomaly examples together, and defer the intentionally slow timeout until last.

## Discrepancies Noticed

1. **Stale OpenAI/gpt-4o-mini comments remain after the Bedrock migration.** `agent.py:15-17` still calls `gpt-4o-mini` the default even though `agent.py:38-70` uses GPT-OSS 120B/Bedrock. `main.py:8-12` still tells operators to export `OPENAI_API_KEY`, while the executable check requires AWS keys (`main.py:63-68`). This conflicts with the Bedrock migration recorded at `CHANGELOG.md:127-133` and the current root README.

2. **The failure-loop threshold counts span events, not actual invocations.** The intended language is “at least four identical calls in 60 seconds” (`RULES.md:39`, `RUN_ORDER.md:40-43`), but the adapter emits both start and completion for a tool run and the worker counts both. On a fresh worker, two actual tool invocations supply four matching events and can trigger the rule. The five-invocation fixture supplies ten events, matching the changelog's observed “seen 10x” result. Additionally, `FailureLoopRule.history` is keyed only by `agent_id`, not by trace ID (`worker/rules/failure_loops.py:15-16`, `worker/rules/failure_loops.py:32-49`), so earlier tickets handled by the same long-lived worker can make a later trace fire even sooner.

3. **Timeout detection is not periodic.** `RUN_ORDER.md:62-64` can be read as saying the alert fires while the diagnostic span is still incomplete. The worker evaluates an incomplete span only when that event arrives and has no periodic tick (`worker/rules/timeouts.py:22-33`). In this demo, the reliable first timeout flag appears on the tool's completion event after the 31-second sleep. The overall graph is still running afterward, so an alert can still appear before the ticket run as a whole finishes.

4. **The token-spike poison is not tool-layer injection.** Broad descriptions in `tickets.py:7-10` and `CHANGELOG.md:157-160` group all poison conditions under the tool layer, but `TOKEN-SPIKE-004` is injected directly as synthetic ticket history and the Composer adds it to the model prompt. Its tool follows the normal Billing path.

5. **“Deterministic poison” applies to fixture conditions, not the entire end-to-end outcome.** The local branches are deterministic, but routing and specialist reroute tokens come from real model outputs. `DELEGATION-CYCLE-001` needs the router to choose Billing/Technical and each specialist to emit the requested exact reroute token; `FAIL-LOOP-002` needs an Account route. Temperature zero and strongly written tickets make those results stable in the verified setup, but the code does not hard-code them.

6. **The optional encore says “remaining” tickets but reruns all four happy paths.** `python main.py happy` expands to the complete `HAPPY_PATH` list (`main.py:96-103`), including the two tickets already used at the start; it does not select only `HAPPY-ACCOUNT-003` and `HAPPY-BILLING-004` as the comment at `RUN_ORDER.md:69-71` implies.

7. **`AWS_REGION` is documented as required but is optional in code.** The README and error message tell the operator to set it, while `agent.py:39` defaults to `us-east-1` and `check_env()` validates only the access-key and secret-key variables (`main.py:63-68`). Conversely, although Boto can normally use a wider AWS credential-provider chain, this entry point rejects execution unless those two environment variables exist.

8. **The `visited` state field still describes an old guardrail.** `TriageState.visited` is commented as “agents already consulted (cycle-guard in app logic)” and the router initializes it (`agent.py:102`, `agent.py:123`), but no current code reads or updates it. The active guardrail is `MAX_HANDOFF_DEPTH=3`, consistent with the changelog's statement that the no-revisit guard was replaced so the demo could actually exhibit a cycle (`CHANGELOG.md:132`). This is stale state/commentary, not active cycle prevention.

9. **The offline-test module says it pins graph wiring, but no test currently does so.** `test_support_demo.py:4-6` includes graph wiring in its description, while its six tests cover ticket grouping, poison tool outputs, diagnostic outputs, token-spike sizing, adapter ID mapping, and call-budget enforcement (`test_support_demo.py:22-72`). The changelog accurately reports six passing tests but the module docstring overstates their coverage.
