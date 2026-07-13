import os
import tempfile

import pytest

from src.trace_logger import write_trace, get_traces


@pytest.fixture(autouse=True)
def unique_trace_dir():
    old = os.environ.get("AGENT_TRACE_DIR")
    os.environ["AGENT_TRACE_DIR"] = tempfile.mkdtemp(prefix="agent-traces-test-")
    yield
    if old:
        os.environ["AGENT_TRACE_DIR"] = old
    else:
        del os.environ["AGENT_TRACE_DIR"]


@pytest.mark.asyncio
async def test_write_and_read_trace():
    request_id = "test-id-123"
    await write_trace(request_id, step=0, phase="reasoning", thought="thinking about it")
    await write_trace(request_id, step=1, phase="acting", action="call_tool", action_input='{"q":"test"}')
    await write_trace(request_id, step=1, phase="evaluation", observation="done")

    traces = await get_traces(request_id)
    assert len(traces) == 3
    assert traces[0]["phase"] == "reasoning"
    assert traces[0]["thought"] == "thinking about it"
    assert traces[1]["action"] == "call_tool"
    assert traces[2]["observation"] == "done"


@pytest.mark.asyncio
async def test_get_traces_empty_for_unknown_id():
    traces = await get_traces("nonexistent-id")
    assert traces == []


@pytest.mark.asyncio
async def test_traces_scoped_by_request_id():
    rid1 = "req-1"
    rid2 = "req-2"

    await write_trace(rid1, step=0, phase="reasoning", thought="first")
    await write_trace(rid2, step=0, phase="reasoning", thought="second")

    traces1 = await get_traces(rid1)
    assert len(traces1) == 1
    assert traces1[0]["thought"] == "first"

    traces2 = await get_traces(rid2)
    assert len(traces2) == 1
    assert traces2[0]["thought"] == "second"
