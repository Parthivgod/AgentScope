import pytest
from datetime import datetime, timezone
import uuid
from unittest.mock import MagicMock
from langchain_core.tracers.schemas import Run
from agentscope.adapters.langgraph import LangGraphAdapter
from agentscope.trace import trace
from agentscope.patch import patch
from agentscope.sender import sender
from agentscope.schema import Span, TokenUsage

@pytest.fixture(autouse=True)
def clear_sender_queue():
    while not sender.queue.empty():
        sender.queue.get_nowait()
    yield
    while not sender.queue.empty():
        sender.queue.get_nowait()

@pytest.mark.asyncio
async def test_identical_schema_decorator_and_adapter():
    # Produce via adapter
    adapter = LangGraphAdapter(agent_id="test-agent", trace_id="trace-123")
    run_id = uuid.uuid4()
    t1 = datetime.now(timezone.utc)
    t2 = datetime.now(timezone.utc)
    
    run = Run(
        id=run_id,
        name="test_op",
        run_type="tool",
        start_time=t1,
        end_time=t2,
        inputs={"args": (1,), "kwargs": {}},
        outputs={"output": 2},
    )
    await adapter._on_run_update(run)
    adapter_span: Span = sender.queue.get_nowait()
    
    # Produce via decorator
    @trace(name="test_op", span_type="tool_call", agent_id="test-agent")
    def test_op(arg1):
        return {"output": arg1 * 2}
        
    test_op(1)
    decorator_span: Span = sender.queue.get_nowait()
    
    # Assert structural identity for shared fields across adapter and decorator
    assert adapter_span.name == decorator_span.name
    assert adapter_span.span_type == decorator_span.span_type
    assert adapter_span.agent_id == decorator_span.agent_id
    assert adapter_span.status.status == decorator_span.status.status
    assert type(adapter_span.model_dump()) == type(decorator_span.model_dump())

@pytest.mark.asyncio
async def test_identical_schema_llm_calls_adapter_and_patch():
    # 1. Produce LLM span via LangGraphAdapter (Flow 1)
    adapter = LangGraphAdapter(agent_id="test-agent", trace_id="trace-llm")
    run_id = uuid.uuid4()
    t1 = datetime.now(timezone.utc)
    t2 = datetime.now(timezone.utc)
    
    llm_run = Run(
        id=run_id,
        name="gpt-4o",
        run_type="llm",
        start_time=t1,
        end_time=t2,
        inputs={"messages": [{"role": "user", "content": "Hello"}]},
        outputs={"llm_output": {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}},
    )
    await adapter._on_run_update(llm_run)
    adapter_llm_span: Span = sender.queue.get_nowait()

    # 2. Produce LLM span via patch(openai) (Flow 2 - OpenAI)
    mock_openai_response = MagicMock()
    mock_openai_response.usage.prompt_tokens = 10
    mock_openai_response.usage.completion_tokens = 5
    mock_openai_response.usage.total_tokens = 15
    mock_openai_response.model_dump.return_value = {"id": "chatcmpl-123", "choices": []}
    mock_openai_client = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        from openai.resources.chat.completions import Completions
        def dummy_openai_create(self, *a, **kw):
            return mock_openai_response
        m.setattr("openai.resources.chat.completions.Completions.create", dummy_openai_create)
        
        if hasattr(Completions.create, "_agentscope_patched"):
            delattr(Completions.create, "_agentscope_patched")
            
        patch(target_module="openai", agent_id="test-agent", trace_id="trace-llm")
        completions_inst = Completions(client=mock_openai_client)
        completions_inst.create(model="gpt-4o", messages=[{"role": "user", "content": "Hello"}])

    openai_span: Span = sender.queue.get_nowait()

    # 3. Produce LLM span via patch(anthropic) (Flow 2 - Anthropic)
    from types import ModuleType
    import sys

    class AnthropicUsage:
        input_tokens = 10
        output_tokens = 5

    mock_anthropic_response = MagicMock()
    mock_anthropic_response.usage = AnthropicUsage()
    mock_anthropic_response.model_dump.return_value = {"id": "msg-123", "content": []}

    mock_anthropic = ModuleType("anthropic")
    mock_messages_mod = ModuleType("anthropic.resources.messages")

    class DummyMessages:
        def create(self, *args, **kwargs):
            return mock_anthropic_response

    class DummyAsyncMessages:
        async def create(self, *args, **kwargs):
            return mock_anthropic_response

    mock_messages_mod.Messages = DummyMessages
    mock_messages_mod.AsyncMessages = DummyAsyncMessages
    mock_anthropic.resources = ModuleType("anthropic.resources")
    mock_anthropic.resources.messages = mock_messages_mod

    with pytest.MonkeyPatch.context() as m:
        m.setitem(sys.modules, "anthropic", mock_anthropic)
        m.setitem(sys.modules, "anthropic.resources.messages", mock_messages_mod)

        patch(target_module="anthropic", agent_id="test-agent", trace_id="trace-llm")
        msg_inst = DummyMessages()
        msg_inst.create(model="claude-3-5-sonnet", messages=[{"role": "user", "content": "Hello"}])

    anthropic_span: Span = sender.queue.get_nowait()

    # Confirm 3-way schema-identical spans (RULES.md §3 Invariant #3)
    assert adapter_llm_span.span_type == openai_span.span_type == anthropic_span.span_type == "llm_call"
    assert adapter_llm_span.agent_id == openai_span.agent_id == anthropic_span.agent_id == "test-agent"
    assert adapter_llm_span.trace_id == openai_span.trace_id == anthropic_span.trace_id == "trace-llm"
    assert adapter_llm_span.status.status == openai_span.status.status == anthropic_span.status.status == "success"
    
    # Token usage structure & count equivalence across all 3 paths
    assert adapter_llm_span.token_usage == openai_span.token_usage == anthropic_span.token_usage
    assert anthropic_span.token_usage.prompt_tokens == 10
    assert anthropic_span.token_usage.completion_tokens == 5
    assert anthropic_span.token_usage.total_tokens == 15

    # Confirm Pydantic schema dump structure identity
    assert set(adapter_llm_span.model_dump().keys()) == set(openai_span.model_dump().keys()) == set(anthropic_span.model_dump().keys())

