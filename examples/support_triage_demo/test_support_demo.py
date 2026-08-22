"""
Offline unit tests for the support-triage demo (no API key, no network).

The LLM is faked; these tests pin the deterministic behaviors the live demo
relies on: tool poison conditions, ticket sizing, adapter agent-id mapping,
and the graph wiring.
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[2] / "sdk"))

import pytest


def test_ticket_set():
    from tickets import TICKETS, HAPPY_PATH, POISON
    assert len(HAPPY_PATH) == 4
    assert len(POISON) == 4
    assert set(TICKETS) == set(HAPPY_PATH + POISON)


def test_tool_poison_conditions():
    from tools import check_billing_history, lookup_account
    assert "NO_BILLING_HISTORY" in check_billing_history.invoke({"ticket_id": "DELEGATION-CYCLE-001"})
    assert "BILLING_OK" in check_billing_history.invoke({"ticket_id": "HAPPY-BILLING-001"})
    assert "AMBIGUOUS" in lookup_account.invoke({"ticket_id": "FAIL-LOOP-002"})
    assert "ACCOUNT_OK" in lookup_account.invoke({"ticket_id": "HAPPY-ACCOUNT-003"})


def test_diagnostic_clean_paths():
    from tools import run_diagnostic
    assert "DIAG_CLEAN" in run_diagnostic.invoke({"ticket_id": "DELEGATION-CYCLE-001"})
    assert "DIAG_OK" in run_diagnostic.invoke({"ticket_id": "HAPPY-TECH-002"})


def test_token_spike_history_is_large():
    """The TOKEN-SPIKE ticket's history must push one composer call >8k tokens."""
    import tiktoken
    from tickets import TICKETS
    enc = tiktoken.get_encoding("cl100k_base")
    t = TICKETS["TOKEN-SPIKE-004"]
    tokens = len(enc.encode(t["subject"] + t["body"] + t["history"]))
    assert tokens > 8000, f"history too small: {tokens} tokens"


def test_adapter_agent_id_mapping():
    """agent_id_by_run changes span identity; unmapped runs keep the default."""
    from agentscope import LangGraphAdapter
    mapping = {"BillingAgent": "billing-agent"}
    adapter = LangGraphAdapter("root-id", "t", agent_id_by_run=mapping)
    assert adapter._resolve_agent_id("BillingAgent") == "billing-agent"
    assert adapter._resolve_agent_id("SomethingElse") == "root-id"
    callable_adapter = LangGraphAdapter("root-id", "t", agent_id_by_run=lambda n: {"router": "triage-router"}.get(n))
    assert callable_adapter._resolve_agent_id("router") == "triage-router"
    assert callable_adapter._resolve_agent_id("other") == "root-id"


def test_call_budget_ceiling():
    os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-import-only")
    from agent import CallBudget, CallBudgetExceeded
    b = CallBudget(limit=3)
    for _ in range(3):
        b.check()
    with pytest.raises(CallBudgetExceeded):
        b.check()
