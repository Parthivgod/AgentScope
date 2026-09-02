import asyncio
from unittest.mock import MagicMock

import pytest
from openai.resources.chat.completions import Completions

from agentscope.context import get_execution_context
from agentscope.patch import patch
from agentscope.schema import Span
from agentscope.sender import sender
from agentscope.trace import trace


def _completed(spans, name):
    return next(span for span in spans if span.name == name and span.end_time is not None)


def test_custom_agent_chain_nests_patched_llm_without_argument_plumbing(monkeypatch):
    captured = []
    monkeypatch.setattr(sender, "send", captured.append)

    response = MagicMock()
    response.usage.prompt_tokens = 4
    response.usage.completion_tokens = 2
    response.usage.total_tokens = 6
    response.model_dump.return_value = {"choices": [{"message": {"content": "done"}}]}

    def dummy_create(self, *args, **kwargs):
        return response

    monkeypatch.setattr(Completions, "create", dummy_create)
    patch(target_module="openai", agent_id="fallback-agent", trace_id="fallback-trace")
    client = Completions(client=MagicMock())

    @trace(name="agent-b", span_type="delegation")
    def agent_b():
        return client.create(model="gpt-test", messages=[{"role": "user", "content": "work"}])

    @trace(name="agent-a", span_type="delegation")
    def agent_a():
        return agent_b()

    agent_a()

    agent_a_span = _completed(captured, "agent-a")
    agent_b_span = _completed(captured, "agent-b")
    llm_span = _completed(captured, "openai.gpt-test")

    assert agent_a_span.parent_span_id is None
    assert agent_a_span.agent_id == "agent-a"
    assert agent_a_span.delegation_chain == ["agent-a"]
    assert agent_a_span.hop_number == 0

    assert agent_b_span.parent_span_id == agent_a_span.span_id
    assert agent_b_span.agent_id == "agent-b"
    assert agent_b_span.delegation_chain == ["agent-a", "agent-b"]
    assert agent_b_span.hop_number == 1

    assert llm_span.parent_span_id == agent_b_span.span_id
    assert llm_span.trace_id == agent_a_span.trace_id == agent_b_span.trace_id
    assert llm_span.agent_id == "agent-b"
    assert llm_span.delegation_chain == ["agent-a", "agent-b"]
    assert llm_span.hop_number == 1


@pytest.mark.asyncio
async def test_concurrent_custom_agent_chains_do_not_leak_context(monkeypatch):
    captured = []
    monkeypatch.setattr(sender, "send", captured.append)

    @trace(name="x-child", span_type="delegation")
    async def x_child():
        await asyncio.sleep(0)

    @trace(name="x-root", span_type="delegation")
    async def x_root():
        await asyncio.sleep(0)
        await x_child()

    @trace(name="y-child", span_type="delegation")
    async def y_child():
        await asyncio.sleep(0)

    @trace(name="y-root", span_type="delegation")
    async def y_root():
        await asyncio.sleep(0)
        await y_child()

    await asyncio.gather(x_root(), y_root())

    x_root_span = _completed(captured, "x-root")
    x_child_span = _completed(captured, "x-child")
    y_root_span = _completed(captured, "y-root")
    y_child_span = _completed(captured, "y-child")

    assert x_child_span.delegation_chain == ["x-root", "x-child"]
    assert x_child_span.parent_span_id == x_root_span.span_id
    assert x_child_span.trace_id == x_root_span.trace_id

    assert y_child_span.delegation_chain == ["y-root", "y-child"]
    assert y_child_span.parent_span_id == y_root_span.span_id
    assert y_child_span.trace_id == y_root_span.trace_id

    assert x_root_span.trace_id != y_root_span.trace_id
    assert all(not agent.startswith("y-") for agent in x_child_span.delegation_chain)
    assert all(not agent.startswith("x-") for agent in y_child_span.delegation_chain)

    restored = get_execution_context("fallback-agent", "fallback-trace")
    assert restored.trace_id == "fallback-trace"
    assert restored.agent_id == "fallback-agent"
    assert restored.parent_span_id is None
    assert restored.delegation_chain == ()
