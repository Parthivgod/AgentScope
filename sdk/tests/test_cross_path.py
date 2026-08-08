import pytest
from datetime import datetime, timezone
import uuid
from langchain_core.tracers.schemas import Run
from agentscope.adapters.langgraph import LangGraphAdapter
from agentscope.trace import trace
from agentscope.sender import sender

@pytest.fixture(autouse=True)
def mock_sender_queue():
    while not sender.queue.empty():
        sender.queue.get_nowait()
    yield
    while not sender.queue.empty():
        sender.queue.get_nowait()

def test_identical_schema_production():
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
        outputs=2,
    )
    adapter._persist_run(run)
    adapter_span = sender.queue.get_nowait()
    
    # Produce via decorator
    @trace(name="test_op", span_type="tool_call", agent_id="test-agent")
    def test_op(arg1):
        return arg1 * 2
        
    test_op(1)
    decorator_span = sender.queue.get_nowait()
    
    # Assert they are structurally identical for the important fields
    assert adapter_span.name == decorator_span.name
    assert adapter_span.span_type == decorator_span.span_type
    assert adapter_span.agent_id == decorator_span.agent_id
    assert adapter_span.input == decorator_span.input
    assert adapter_span.output == decorator_span.output
    assert adapter_span.status.status == decorator_span.status.status
