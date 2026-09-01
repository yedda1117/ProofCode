from __future__ import annotations

import json
from typing import Any, Callable

from proofcode.context import Conversation
from proofcode.errors import ModelError, ProtocolError
from proofcode.model import ChatModel
from proofcode.state import WorkspaceState
from proofcode.tools import ToolRegistry, format_tool_result
from proofcode.types import AgentResult, ModelResponse, StopReason, ToolCall


SYSTEM_PROMPT = """You are a coding agent operating inside a local workspace.

Inspect relevant files before editing and use existing tests to understand behavior when practical. Make the smallest change that satisfies the task. After editing, run the most relevant tests first and use failures as feedback for the next change. Run broader regression tests when they are available and proportionate to the task. Do not use an unrelated successful command as evidence of completion. Explain the final changes and the validation evidence concisely.

Tool paths are relative to the workspace. Commands must be expressed as an argv array and run without a shell. If a tool fails, inspect its structured error and change approach. Do not repeat the same failing action.
Use show_diff to review workspace changes when useful. apply_patch accepts unified-diff hunks for one existing file; use create_file for new files.
"""


EventCallback = Callable[[str, dict[str, Any]], None]


class CodingAgent:
    def __init__(
        self,
        *,
        model: ChatModel,
        tools: ToolRegistry,
        max_steps: int = 20,
        context_chars: int = 120_000,
        recent_history_chars: int = 24_000,
        on_event: EventCallback | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        if recent_history_chars < 1:
            raise ValueError("recent_history_chars must be at least 1")
        self.model = model
        self.tools = tools
        self.max_steps = max_steps
        self.context_chars = context_chars
        self.recent_history_chars = recent_history_chars
        self.on_event = on_event or (lambda _kind, _data: None)

    def run(self, task: str) -> AgentResult:
        if not task.strip():
            raise ValueError("task must not be empty")
        conversation = Conversation(SYSTEM_PROMPT, task.strip())
        workspace_state = WorkspaceState(task)
        self.tools.attach_state(workspace_state)
        signatures: dict[str, int] = {}

        for step in range(1, self.max_steps + 1):
            self.on_event("step", {"step": step})
            try:
                response = self.model.complete(
                    conversation.messages(
                        min(self.context_chars, self.recent_history_chars),
                        workspace_state.prompt_context(),
                    ),
                    self.tools.schemas(),
                )
            except (ModelError, ProtocolError) as exc:
                self.on_event("model_error", {"step": step, "error": str(exc)})
                return AgentResult(StopReason.MODEL_ERROR, str(exc), step)

            self.on_event(
                "model_response",
                {
                    "step": step,
                    "content": response.content,
                    "finish_reason": response.finish_reason,
                    "tool_calls": len(response.tool_calls),
                    "usage": response.usage,
                },
            )

            if response.tool_calls:
                tool_messages = self._execute_calls(
                    response,
                    workspace_state,
                    signatures,
                )
                if tool_messages is None:
                    return AgentResult(
                        StopReason.REPEATED_ACTION,
                        "The same tool call was requested three times; execution stopped.",
                        step,
                    )
                conversation.add_exchange(response.raw_message, tool_messages)
                continue

            if not response.content:
                return AgentResult(
                    StopReason.MODEL_ERROR,
                    "Model returned neither tool calls nor a final answer.",
                    step,
                )

            feedback = workspace_state.completion_feedback()
            if feedback:
                self.on_event("verification_rejected", {"reason": feedback})
                conversation.add_feedback(response.raw_message, feedback)
                continue
            return AgentResult(StopReason.COMPLETED, response.content, step)

        return AgentResult(
            StopReason.MAX_STEPS,
            f"Stopped after reaching the maximum of {self.max_steps} model steps.",
            self.max_steps,
        )

    def _execute_calls(
        self,
        response: ModelResponse,
        workspace_state: WorkspaceState,
        signatures: dict[str, int],
    ) -> list[dict[str, Any]] | None:
        messages: list[dict[str, Any]] = []
        for call in response.tool_calls:
            signature = json.dumps(
                [call.name, call.arguments],
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            signatures[signature] = signatures.get(signature, 0) + 1
            if signatures[signature] >= 3:
                return None
            self.on_event(
                "tool_call",
                {"id": call.id, "name": call.name, "arguments": call.arguments},
            )
            result = self.tools.execute(call.name, call.arguments)
            result = workspace_state.record(call, result)
            self.on_event(
                "tool_result",
                {
                    "id": call.id,
                    "name": call.name,
                    "ok": result.ok,
                    "result": result.content,
                    "metadata": result.metadata,
                },
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": format_tool_result(result),
                }
            )
        return messages
