from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from proofcode.context import Conversation
from proofcode.errors import ModelError, ProtocolError
from proofcode.model import ChatModel
from proofcode.state import WorkspaceState
from proofcode.tools import ToolRegistry, format_tool_result
from proofcode.types import AgentResult, ModelResponse, StopReason, ToolCall


SYSTEM_PROMPT = """You are a coding agent operating inside a local workspace.

Inspect relevant files before editing. Make the smallest change that satisfies the task. Use tools instead of guessing about repository contents. Run relevant tests or validation after changing files. Do not claim success when validation failed or was not run. Explain the final changes and the validation evidence concisely.

Tool paths are relative to the workspace. Commands must be expressed as an argv array and run without a shell. If a tool fails, inspect its structured error and change approach. Do not repeat the same failing action.
"""


EventCallback = Callable[[str, dict[str, Any]], None]


@dataclass
class Evidence:
    changed_files: set[str] = field(default_factory=set)
    commands: list[dict[str, Any]] = field(default_factory=list)

    def observe(self, call: ToolCall, result_metadata: dict[str, Any], ok: bool) -> None:
        if result_metadata.get("changed") and result_metadata.get("path"):
            self.changed_files.add(str(result_metadata["path"]))
        if call.name == "run_command":
            self.commands.append(
                {
                    "argv": call.arguments.get("argv"),
                    "ok": ok,
                    "exit_code": result_metadata.get("exit_code"),
                }
            )

    def completion_feedback(self) -> str | None:
        if self.changed_files and not any(command["ok"] for command in self.commands):
            return (
                "Completion is not accepted yet: files were changed but no command has "
                "completed successfully. Run the most relevant available test, build, "
                "or syntax-check command. If no validation command exists, inspect the "
                "diff with an appropriate local command and explain the limitation."
            )
        return None


class CodingAgent:
    def __init__(
        self,
        *,
        model: ChatModel,
        tools: ToolRegistry,
        max_steps: int = 20,
        context_chars: int = 120_000,
        on_event: EventCallback | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1")
        self.model = model
        self.tools = tools
        self.max_steps = max_steps
        self.context_chars = context_chars
        self.on_event = on_event or (lambda _kind, _data: None)

    def run(self, task: str) -> AgentResult:
        if not task.strip():
            raise ValueError("task must not be empty")
        conversation = Conversation(SYSTEM_PROMPT, task.strip())
        evidence = Evidence()
        workspace_state = WorkspaceState()
        signatures: dict[str, int] = {}

        for step in range(1, self.max_steps + 1):
            self.on_event("step", {"step": step})
            try:
                response = self.model.complete(
                    conversation.messages(self.context_chars),
                    self.tools.schemas(),
                )
            except (ModelError, ProtocolError) as exc:
                return AgentResult(StopReason.MODEL_ERROR, str(exc), step)

            if response.tool_calls:
                tool_messages = self._execute_calls(
                    response,
                    evidence,
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

            feedback = evidence.completion_feedback()
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
        evidence: Evidence,
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
            evidence.observe(call, result.metadata, result.ok)
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
