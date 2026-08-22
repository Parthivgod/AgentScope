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

import os
from typing import Any, Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda, RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from tools import check_billing_history, run_diagnostic, lookup_account
from tickets import TICKETS

MODEL = os.environ.get("TRIAGE_MODEL", "gpt-4o-mini")
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


llm = ChatOpenAI(model=MODEL, temperature=0)
budget = CallBudget()


async def ask_llm(system: str, user: str) -> str:
    budget.check()
    resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    return resp.content.strip()


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
    history = await check_billing_history.ainvoke({"ticket_id": state["ticket_id"]}, config=config)
    reply = await ask_llm(BILLING_SYSTEM, _TICKET_CONTEXT.format(**state) + f"\n\nBilling lookup: {history}")
    if "REROUTE_TECHNICAL" in reply:
        return await _reroute(state, config, "billing", "technical", reply, depth)
    return {"specialist_notes": [f"[billing] {reply}"]}


async def _technical_work(state: TriageState, config: RunnableConfig, depth: int = 0) -> Dict[str, Any]:
    diag = await run_diagnostic.ainvoke({"ticket_id": state["ticket_id"]}, config=config)
    reply = await ask_llm(TECHNICAL_SYSTEM, _TICKET_CONTEXT.format(**state) + f"\n\nDiagnostic: {diag}")
    if "REROUTE_BILLING" in reply:
        return await _reroute(state, config, "technical", "billing", reply, depth)
    return {"specialist_notes": [f"[technical] {reply}"]}


async def _reroute(state, config, from_agent: str, to_agent: str, reply: str, depth: int) -> Dict[str, Any]:
    """Hand off to the other specialist as a NESTED runnable so the parent/child
    delegation structure is real (this is what makes a revisit visible as an
    actual delegation cycle in the span tree)."""
    visited = state.get("visited", []) + [from_agent]
    if to_agent in visited or depth >= 2:
        # App-level guardrail: stop bouncing, let the composer close it out.
        return {"specialist_notes": state.get("specialist_notes", []) + [f"[{from_agent}] {reply}"],
                "visited": visited}
    payload = {**state, "visited": visited}

    async def run_billing(p, cfg=None):
        return await _billing_work(p, config, depth + 1)

    async def run_technical(p, cfg=None):
        return await _technical_work(p, config, depth + 1)

    if to_agent == "technical":
        agent = RunnableLambda(run_technical).with_config(run_name="TechnicalAgent")
    else:
        agent = RunnableLambda(run_billing).with_config(run_name="BillingAgent")
    result = await agent.ainvoke(payload, config=config)
    notes = state.get("specialist_notes", []) + [f"[{from_agent}] {reply}"]
    return {"specialist_notes": notes + result.get("specialist_notes", []),
            "visited": result.get("visited", visited)}


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
