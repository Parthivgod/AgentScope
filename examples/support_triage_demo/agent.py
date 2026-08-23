"""
Support-triage multi-agent demo (Flow 1 — zero-rewrite instrumentation).

A supervisor/router LangGraph: the router classifies each ticket with a real
LLM call and routes to a specialist; each specialist makes a real LLM call
plus a local tool lookup; a composer drafts the final reply with a real LLM
call. The LangGraphAdapter is attached purely via config callbacks — nothing
in this file knows about AgentScope (the only import is in main.py where the
adapter is attached).

Demo-application guardrails (this file's own responsible design; AgentScope
itself only observes):
  - Hard per-run LLM call ceiling (MAX_LLM_CALLS) to bound API spend if a
    bug ever causes a runaway loop.
  - Cheap/fast default model tier (gpt-4o-mini) — sufficient for
    classification/drafting, ~an order of magnitude cheaper than frontier
    tiers.
"""

import asyncio
import os
from typing import Any, Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda, RunnableConfig
from langchain_aws import ChatBedrockConverse
from langgraph.graph import StateGraph, START, END

from tools import check_billing_history, run_diagnostic, lookup_account
from tickets import TICKETS

# Model: GPT-OSS 120B on Amazon Bedrock (us-east-1 default), via
# ChatBedrockConverse with standard IAM credentials (AWS_ACCESS_KEY_ID /
# AWS_SECRET_ACCESS_KEY / AWS_REGION). Evaluated and chosen per the
# 2026-08-22 model evaluation: plain text-in/text-out is all this demo needs
# (tools are invoked by the graph code, not model-driven), so the unreliable
# LangChain tool-calling paths for Bedrock gpt-oss are never exercised.
MODEL = os.environ.get("TRIAGE_MODEL", "openai.gpt-oss-120b-1:0")
AWS_REGION_DEFAULT = os.environ.get("AWS_REGION", "us-east-1")
MAX_LLM_CALLS = 15  # hard ceiling: abort the run rather than burn budget on a bug


class CallBudgetExceeded(RuntimeError):
    pass


class CallBudget:
    """Per-run LLM call ceiling (demo-app safety net, not AgentScope enforcement)."""

    def __init__(self, limit: int = MAX_LLM_CALLS):
        self.limit = limit
        self.used = 0

    def check(self):
        if self.used >= self.limit:
            raise CallBudgetExceeded(
                f"Demo safety net: per-run LLM call ceiling ({self.limit}) reached — aborting."
            )
        self.used += 1


# gpt-oss is a reasoning model: cap output tokens so reasoning stays brief
# (long reasoning pushes per-call latency toward the 30s timeout ceiling and
# makes demo pacing sluggish). temperature 0 for deterministic-ish routing.
llm = ChatBedrockConverse(
    model=MODEL,
    region_name=AWS_REGION_DEFAULT,
    temperature=0,
    max_tokens=1024,
)
budget = CallBudget()


def _content_text(content) -> str:
    """Bedrock Converse returns content blocks (list); join the text parts."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("text"):
            parts.append(block["text"])
    return "".join(parts)


async def ask_llm(system: str, user: str) -> str:
    budget.check()
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    return _content_text(resp.content).strip()


# ── State ──────────────────────────────────────────────────────────────

class TriageState(TypedDict, total=False):
    ticket_id: str
    subject: str
    body: str
    history: str
    route: str                 # billing | technical | account
    specialist_notes: List[str]
    visited: List[str]         # agents already consulted (cycle-guard in app logic)
    response: str


# ── Router ─────────────────────────────────────────────────────────────

ROUTER_SYSTEM = (
    "You are the routing classifier for a software support team. Classify the "
    "ticket into exactly one category: BILLING, TECHNICAL, or ACCOUNT. "
    "Reply with the single word only."
)

async def router_node(state: TriageState, config: RunnableConfig) -> Dict[str, Any]:
    answer = await ask_llm(ROUTER_SYSTEM, f"Subject: {state['subject']}\n\n{state['body']}")
    route = answer.lower().strip(" .")
    if "bill" in route:
        route = "billing"
    elif "account" in route:
        route = "account"
    else:
        route = "technical"
    return {"route": route, "specialist_notes": [], "visited": []}


# ── Specialists ────────────────────────────────────────────────────────

BILLING_SYSTEM = (
    "You are the billing specialist on a support team. Use the billing "
    "history lookup result to help the customer. If (and only if) the lookup "
    "explicitly says this is NOT a billing issue, end your reply with the "
    "exact token REROUTE_TECHNICAL. Otherwise give a helpful billing answer."
)

TECHNICAL_SYSTEM = (
    "You are the technical specialist on a support team. Use the diagnostic "
    "result to help the customer. If (and only if) the diagnostic explicitly "
    "says no technical defect was found, end your reply with the exact token "
    "REROUTE_BILLING. Otherwise give a helpful technical answer."
)

ACCOUNT_SYSTEM = (
    "You are the account specialist on a support team. Use the account "
    "lookup result to help the customer and give a clear answer or next step."
)

COMPOSER_SYSTEM = (
    "You draft the final customer-facing reply for a support ticket, using "
    "the specialist's findings. Be concise, empathetic, and specific."
)

_TICKET_CONTEXT = ("Subject: {subject}\n\n{body}\n\nTicket ID: {ticket_id}")


async def _billing_work(state: TriageState, config: RunnableConfig, depth: int = 0) -> Dict[str, Any]:
    # Reuse a lookup already in the shared state (hand-offs carry context) —
    # a specialist doesn't re-run a tool whose result the team already has.
    history = state.get("billing_lookup")
    if history is None:
        history = await check_billing_history.ainvoke({"ticket_id": state["ticket_id"]}, config=config)
        state["billing_lookup"] = history
    thread = "\n".join(state.get("specialist_notes", []))
    reply = await ask_llm(BILLING_SYSTEM, _TICKET_CONTEXT.format(**state)
                          + f"\n\nBilling lookup: {history}"
                          + (f"\n\nPrior correspondence in this thread:\n{thread}" if thread else ""))
    # Reroute only when the DATA says it's not a billing issue AND the LLM
    # agrees — keeps routing deterministic on happy-path tickets.
    if "NO_BILLING_HISTORY" in history and "REROUTE_TECHNICAL" in reply:
        return await _reroute(state, config, "billing", "technical", reply, depth)
    return {"specialist_notes": [f"[billing] {reply}"]}


async def _technical_work(state: TriageState, config: RunnableConfig, depth: int = 0) -> Dict[str, Any]:
    diag = state.get("diagnostic_result")
    if diag is None:
        diag = await run_diagnostic.ainvoke({"ticket_id": state["ticket_id"]}, config=config)
        state["diagnostic_result"] = diag
    thread = "\n".join(state.get("specialist_notes", []))
    reply = await ask_llm(TECHNICAL_SYSTEM, _TICKET_CONTEXT.format(**state)
                          + f"\n\nDiagnostic: {diag}"
                          + (f"\n\nPrior correspondence in this thread:\n{thread}" if thread else ""))
    if "DIAG_CLEAN" in diag and "REROUTE_BILLING" in reply:
        return await _reroute(state, config, "technical", "billing", reply, depth)
    return {"specialist_notes": [f"[technical] {reply}"]}


MAX_HANDOFF_DEPTH = 3  # app-level guardrail: cap total specialist hand-offs

async def _reroute(state, config, from_agent: str, to_agent: str, reply: str, depth: int) -> Dict[str, Any]:
    """Hand off to the other specialist as a NESTED runnable so the parent/child
    delegation structure is real. Each specialist genuinely believes the other
    team owns the ticket, so they ping-pong — the app caps the hand-off depth
    (plus the 15-call LLM budget); AgentScope flags the revisit the moment the
    first agent appears twice in one delegation chain."""
    if depth >= MAX_HANDOFF_DEPTH:
        return {"specialist_notes": state.get("specialist_notes", []) + [f"[{from_agent}] {reply}"]}
    await asyncio.sleep(1.0)  # hand-off latency between specialists
    # Carry the accumulated correspondence so the next specialist reads the thread
    payload = {**state, "specialist_notes": state.get("specialist_notes", []) + [f"[{from_agent}] {reply}"]}

    async def run_billing(p, cfg=None):
        # Use the nested runnable's own config (cfg) so inner spans chain to
        # THIS agent's run, not back to the outer node — that chaining is what
        # makes a revisit show up as a real delegation cycle in the span tree.
        return await _billing_work(p, cfg or config, depth + 1)

    async def run_technical(p, cfg=None):
        return await _technical_work(p, cfg or config, depth + 1)

    if to_agent == "technical":
        agent = RunnableLambda(run_technical).with_config(run_name="TechnicalAgent")
    else:
        agent = RunnableLambda(run_billing).with_config(run_name="BillingAgent")
    result = await agent.ainvoke(payload, config=config)
    notes = state.get("specialist_notes", []) + [f"[{from_agent}] {reply}"]
    return {"specialist_notes": notes + result.get("specialist_notes", [])}


async def billing_node(state: TriageState, config: RunnableConfig) -> Dict[str, Any]:
    return await _billing_work(state, config)


async def technical_node(state: TriageState, config: RunnableConfig) -> Dict[str, Any]:
    return await _technical_work(state, config)


async def account_node(state: TriageState, config: RunnableConfig) -> Dict[str, Any]:
    # Retry the identical lookup when the record comes back ambiguous — the
    # realistic reaction to a flaky account store, and a deterministic
    # failure-loop trigger (>= 4 identical calls inside 60s).
    result = "AMBIGUOUS"
    for attempt in range(5):
        result = await lookup_account.ainvoke({"ticket_id": state["ticket_id"]}, config=config)
        if "AMBIGUOUS" not in result:
            break
        # Brief backoff between retries: identical-call cadence stays well
        # inside the failure-loop rule's 60s window without spiking the event
        # rate past the message-storm threshold.
        await asyncio.sleep(0.75)
    reply = await ask_llm(ACCOUNT_SYSTEM, _TICKET_CONTEXT.format(**state) + f"\n\nAccount lookup: {result}")
    return {"specialist_notes": [f"[account] {reply}"]}


async def composer_node(state: TriageState, config: RunnableConfig) -> Dict[str, Any]:
    notes = "\n".join(state.get("specialist_notes", []))
    history = state.get("history", "")
    user = _TICKET_CONTEXT.format(**state) + f"\n\nSpecialist findings:\n{notes}"
    if history:
        user += f"\n\n{history}"  # TOKEN-SPIKE ticket rides in here (>8k tokens)
    draft = await ask_llm(COMPOSER_SYSTEM, user)
    return {"response": draft}


def build_graph():
    builder = StateGraph(TriageState)
    builder.add_node("router", router_node)
    builder.add_node("billing", billing_node)
    builder.add_node("technical", technical_node)
    builder.add_node("account", account_node)
    builder.add_node("composer", composer_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        lambda s: s["route"],
        {"billing": "billing", "technical": "technical", "account": "account"},
    )
    builder.add_edge("billing", "composer")
    builder.add_edge("technical", "composer")
    builder.add_edge("account", "composer")
    builder.add_edge("composer", END)
    return builder.compile()


def make_initial_state(ticket_id: str) -> TriageState:
    t = TICKETS[ticket_id]
    return {"ticket_id": ticket_id, "subject": t["subject"], "body": t["body"],
            "history": t.get("history", "")}
