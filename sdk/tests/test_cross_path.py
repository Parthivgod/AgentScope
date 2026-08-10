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
    await adapter._persist_run(run)
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
    # 1. Produce LLM span via LangGraphAdapter
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
    await adapter._persist_run(llm_run)
    adapter_llm_span: Span = sender.queue.get_nowait()

    # 2. Produce LLM span via patch(openai)
    patch(agent_id="test-agent", trace_id="trace-llm")
    
    import openai
    from openai.resources.chat.completions import Completions
    
    mock_response = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.usage.total_tokens = 15
    mock_response.model_dump.return_value = {"id": "chatcmpl-123", "choices": []}
    
    mock_client = MagicMock()

    with pytest.MonkeyPatch.context() as m:
        def dummy_create(self, *a, **kw):
            return mock_response
        m.setattr("openai.resources.chat.completions.Completions.create", dummy_create)
        
        if hasattr(Completions.create, "_agentscope_patched"):
            delattr(Completions.create, "_agentscope_patched")
            
        patch(agent_id="test-agent", trace_id="trace-llm")
        completions_inst = Completions(client=mock_client)
        completions_inst.create(model="gpt-4o", messages=[{"role": "user", "content": "Hello"}])

    patch_llm_span: Span = sender.queue.get_nowait()

    # Confirm schema-identical spans (RULES.md §3 Invariant #3)
    assert adapter_llm_span.span_type == patch_llm_span.span_type == "llm_call"
    assert adapter_llm_span.agent_id == patch_llm_span.agent_id == "test-agent"
    assert adapter_llm_span.trace_id == patch_llm_span.trace_id == "trace-llm"
    assert adapter_llm_span.status.status == patch_llm_span.status.status == "success"
    assert adapter_llm_span.token_usage == patch_llm_span.token_usage
    assert patch_llm_span.token_usage.prompt_tokens == 10
    assert patch_llm_span.token_usage.completion_tokens == 5
    assert patch_llm_span.token_usage.total_tokens == 15
