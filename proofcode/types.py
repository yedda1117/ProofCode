from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    raw_message: dict[str, Any]
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_content: str | None = None


class StopReason(str, Enum):
    COMPLETED = "completed"
    MAX_STEPS = "max_steps"
    REPEATED_ACTION = "repeated_action"
    MODEL_ERROR = "model_error"


@dataclass(frozen=True)
class AgentResult:
    reason: StopReason
    answer: str
    steps: int
