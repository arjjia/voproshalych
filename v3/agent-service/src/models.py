"""Модели данных agent-service."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Intent(Enum):
    KB_QA = "kb_qa"
    META = "meta"
    TOOL_REQUIRED = "tool_required"
    OFF_TOPIC = "off_topic"
    CLARIFY = "clarify"


class Complexity(Enum):
    SIMPLE = "simple"
    MULTI_STEP = "multi_step"


@dataclass
class Profile:
    user_id: str = "anonymous"
    role: str = "guest"


@dataclass
class AgentState:
    messages: list[dict[str, str]]
    dialog_context: str = ""
    intent: Intent | None = None
    complexity: Complexity | None = None
    required_tools: list[str] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    final_answer: str | None = None
    sources: list[dict[str, str]] | None = None
    error: str | None = None
    profile: Profile = field(default_factory=Profile)
    request_id: str = ""


@dataclass
class SSEMessage:
    event: str
    data: str
