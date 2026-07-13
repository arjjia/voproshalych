import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _get_trace_dir() -> str:
    return os.environ.get("AGENT_TRACE_DIR", "/tmp/agent-traces")


def _ensure_dir() -> str:
    d = _get_trace_dir()
    os.makedirs(d, exist_ok=True)
    return d


def _trace_file(request_id: str) -> str:
    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    return os.path.join(_ensure_dir(), f"traces-{date_prefix}.jsonl")


async def write_trace(
    request_id: str,
    step: int,
    phase: str,
    thought: str | None = None,
    action: str | None = None,
    action_input: str | None = None,
    observation: str | None = None,
) -> None:
    entry = {
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "phase": phase,
        "thought": thought,
        "action": action,
        "action_input": action_input,
        "observation": observation,
    }
    entry = {k: v for k, v in entry.items() if v is not None}
    try:
        with open(_trace_file(request_id), "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning(f"Failed to write trace: {e}")


async def get_traces(request_id: str) -> list[dict[str, Any]]:
    traces = []
    trace_file = _trace_file(request_id)
    if not os.path.exists(trace_file):
        return traces
    try:
        with open(trace_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("request_id") == request_id:
                    traces.append(entry)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to read traces: {e}")
    return traces
