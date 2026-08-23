"""
Entry point for the support-triage demo.

Runs tickets through the multi-agent graph with the AgentScope LangGraph
adapter attached — this file is the ONLY place observability is wired in,
and it is pure attachment: config callbacks, zero changes to agent logic.

Usage:
    export AGENTSCOPE_API_KEY=test-key
    export AGENTSCOPE_INGEST_URL=http://localhost:8000/ingest   # or via Nginx: http://localhost/ingest
    export OPENAI_API_KEY=sk-...                                 # REQUIRED — real LLM calls

    python main.py happy                 # all happy-path tickets
    python main.py poison                # all four poison tickets
    python main.py HAPPY-BILLING-001 DELEGATION-CYCLE-001 ...   # specific tickets
    python main.py all
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid

from agentscope import LangGraphAdapter

from agent import build_graph, budget, CallBudgetExceeded, make_initial_state
from tickets import TICKETS, HAPPY_PATH, POISON

# Per-run-name agent identity for spans. Distinct ids per agent make the
# delegation-cycle rule meaningful (a shared id would trivially "cycle" on
# any nested run). Unknown run names fall back to the graph-level id.
_AGENT_MAP = {
    "LangGraph": "support-triage",
    "router": "triage-router",
    "billing": "billing-agent",
    "BillingAgent": "billing-agent",
    "technical": "technical-agent",
    "TechnicalAgent": "technical-agent",
    "account": "account-agent",
    "AccountAgent": "account-agent",
    "composer": "response-composer",
    "ChatOpenAI": "llm", "ChatBedrockConverse": "llm",  # leaf spans; never ancestors, so no false cycles
    # Tools get their OWN identities: a tool span's parent is its owning
    # agent's span, so sharing the agent's id would read as an instant cycle.
    "check_billing_history": "billing-history-tool",
    "run_diagnostic": "diagnostic-tool",
    "lookup_account": "account-lookup-tool",
}


def agent_id_by_run(name: str) -> str:
    # Unknown run names (e.g. LangGraph's internal "Unnamed" edge lambdas) get
    # a unique id per name — falling back to the ROOT id would make the
    # delegation-cycle rule trivially fire on every such span.
    return _AGENT_MAP.get(name, f"graph-internal-{name or 'anonymous'}")


AGENT_ID_BY_RUN = agent_id_by_run


def check_env():
    if not (os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")):
        print("ERROR: AWS credentials not set. This demo makes REAL LLM calls "
              "(GPT-OSS 120B on Amazon Bedrock). Set AWS_ACCESS_KEY_ID, "
              "AWS_SECRET_ACCESS_KEY and AWS_REGION, then retry.", file=sys.stderr)
        sys.exit(2)


async def run_ticket(graph, ticket_id: str) -> None:
    budget.used = 0  # per-ticket ceiling
    trace_id = f"triage-{ticket_id.lower()}"
    adapter = LangGraphAdapter(
        agent_id="support-triage",
        trace_id=trace_id,
        agent_id_by_run=AGENT_ID_BY_RUN,
    )
    print(f"\n=== {ticket_id}: {TICKETS[ticket_id]['subject']}")
    try:
        result = await graph.ainvoke(make_initial_state(ticket_id), config={"callbacks": [adapter]})
        print(f"    route resolved -> composer response ({len(result.get('response', ''))} chars)")
    except CallBudgetExceeded as e:
        print(f"    ABORTED by demo safety net: {e}")
    await asyncio.sleep(1.0)  # let the fail-silent sender drain


async def main():
    logging.basicConfig(level=logging.WARNING)
    check_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("tickets", nargs="+",
                        help="ticket ids, or groups: happy | poison | all")
    args = parser.parse_args()

    ids: list[str] = []
    for t in args.tickets:
        if t == "happy":
            ids += HAPPY_PATH
        elif t == "poison":
            ids += POISON
        elif t == "all":
            ids += list(TICKETS)
        elif t in TICKETS:
            ids.append(t)
        else:
            print(f"Unknown ticket '{t}'. Available: {', '.join(TICKETS)}", file=sys.stderr)
            sys.exit(2)

    graph = build_graph()
    for ticket_id in ids:
        await run_ticket(graph, ticket_id)


if __name__ == "__main__":
    asyncio.run(main())
