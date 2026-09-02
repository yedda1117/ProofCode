from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from proofcode.context import Conversation
from proofcode.errors import ModelError, ProtocolError
from proofcode.model import ChatModel
from proofcode.state import WorkspaceState
from proofcode.tools import ToolRegistry, format_tool_result
from proofcode.types import AgentResult, ModelResponse, StopReason, ToolCall


SYSTEM_PROMPT = """You are a coding agent operating inside a local workspace.

Inspect relevant files before editing and use existing tests to understand behavior when practical. Make the smallest change that satisfies the task. After editing, run the most relevant tests first and use failures as feedback for the next change. Run broader regression tests when they are available and proportionate to the task. Do not use an unrelated successful command as evidence of completion. Explain the final changes and the validation evidence concisely.

Maintain decision-relevant working memory, not an operation diary. After initial repository inspection, and whenever a material discovery, code change, validation failure, or next action changes the working theory, call update_working_memory. Record concise findings, constraints, hypotheses, progress, and risks; every item must cite the E evidence that supports it. Never invent a finding from memory alone. The runtime will invalidate items when their evidence or dependent files become stale. Keep the checkpoint small enough to guide the next decision after older conversation is evicted.

The LONG-TERM L1 MEMORY INDEX contains only cross-task pointers. Read a relevant F/S/K entry on demand before rediscovering the same project fact or workflow. Do not treat memory as more authoritative than the current workspace. Propose long-term memory only for stable, difficult-to-reconstruct, reusable knowledge: fact for verified project facts, sop for validated recovery/workflows, and skill only for an exact validated Python file. Never store temporary state, guesses, routine steps, credentials, or facts easily recovered with one read. A proposal is only staged; the runtime commits it after successful completion.

Tool paths are relative to the workspace. Commands must be expressed as an argv array and run without a shell. If a tool fails, inspect its structured error and change approach. Do not repeat the same failing action.
Use show_diff to review workspace changes when useful. apply_patch accepts unified-diff hunks for one existing file; use create_file for new files.
Working memory combines runtime state, an evidence-grounded checkpoint, recent exchanges, and session evidence routes. Long-term memory follows L1 index -> L2 verified facts / L3 SOPs and skills -> L4 raw session archive. When an earlier observation is omitted or a tool result is marked truncated, use search_context and read_context; for reusable cross-task knowledge, route through the long-term L1 index with read_memory or search_memory. Do not rerun an expensive command merely because its visible output was compressed.
"""


EventCallback = Callable[[str, dict[str, Any]], None]

OBSERVATION_TOOLS = {
    "list_files",
    "search_text",
    "read_file",
    "show_diff",
    "list_context",
    "search_context",
    "read_context",
    "search_memory",
    "read_memory",
}


class CodingAgent:
    def __init__(
        self,
        *,
        model: ChatModel,
        tools: ToolRegistry,
        max_steps: int = 20,
        context_chars: int = 120_000,
        recent_history_chars: int = 64_000,
        run_id: str | None = None,
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
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        self.on_event = on_event or (lambda _kind, _data: None)

    def run(self, task: str) -> AgentResult:
        if not task.strip():
            raise ValueError("task must not be empty")
        conversation = Conversation(SYSTEM_PROMPT, task.strip())
        workspace_state = WorkspaceState(
            task,
            self.tools.validation_policy,
            self.tools.memory_store.index_prompt(),
        )
        self.tools.attach_state(workspace_state)
        action_streak: dict[str, Any] = {
            "key": None,
            "count": 0,
            "failed_count": 0,
            "revision_counts": {},
            "revision_evidence": {},
        }
        consolidation_requested = False

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
                    "raw_message": response.raw_message,
                    "finish_reason": response.finish_reason,
                    "tool_calls": len(response.tool_calls),
                    "usage": response.usage,
                },
            )

            if response.tool_calls:
                tool_messages = self._execute_calls(
                    response,
                    workspace_state,
                    action_streak,
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
            if (
                workspace_state.changed_files
                and workspace_state.validation_policy.required_commands
                and not workspace_state.memory_candidates
                and not consolidation_requested
            ):
                consolidation_requested = True
                reflection = (
                    "任务已经通过项目策略要求的当前版本验证。进入自动经验固化阶段："
                    "检查本次 E 证据，只把稳定、难以轻易重新发现且可跨任务复用的经验"
                    "提交为长期记忆候选。项目事实使用 fact；可复用验证或恢复流程使用 "
                    "sop；本次形成且经过验证的通用 Python 脚本使用 skill，并提供其真实 "
                    "source_path。可以在一次响应中提交多个候选。如果没有值得固化的经验，"
                    "不要勉强创建，直接重新给出最终答案。"
                )
                self.on_event("memory_reflection", {"reason": reflection})
                conversation.add_feedback(response.raw_message, reflection)
                continue
            try:
                committed = self.tools.commit_memory(run_id=self.run_id)
            except (OSError, ValueError) as exc:
                committed = ()
                self.on_event("memory_error", {"error": str(exc)})
            if committed:
                self.on_event("memory_committed", {"ids": list(committed)})
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
        action_streak: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        messages: list[dict[str, Any]] = []
        recovery_feedback: list[str] = []
        for call in response.tool_calls:
            signature = json.dumps(
                [workspace_state.revision, call.name, call.arguments],
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            revision_counts = action_streak["revision_counts"]
            revision_counts[signature] = revision_counts.get(signature, 0) + 1
            if action_streak["key"] == signature:
                action_streak["count"] += 1
            else:
                action_streak["key"] = signature
                action_streak["count"] = 1
                action_streak["failed_count"] = 0
            if (
                revision_counts[signature] >= 3
                and call.name in OBSERVATION_TOOLS
            ):
                evidence_id = action_streak["revision_evidence"].get(
                    signature, "an earlier E evidence item"
                )
                message = (
                    f"未重复执行：当前 revision 中相同的 {call.name} 已有证据 "
                    f"{evidence_id}。请通过 working checkpoint、search_context 或 "
                    "read_context 恢复该证据，并继续实现；不要重新侦察。"
                )
                self.on_event(
                    "tool_call_skipped",
                    {"id": call.id, "name": call.name, "reason": message},
                )
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": message}
                )
                recovery_feedback.append(message)
                continue
            if action_streak["count"] >= 3:
                return None
            if revision_counts[signature] >= 3:
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
                    "raw_result": result.raw_content or result.content,
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
            if result.ok:
                action_streak["failed_count"] = 0
                evidence_id = result.metadata.get("evidence_id")
                if evidence_id:
                    action_streak["revision_evidence"][signature] = evidence_id
                if (
                    revision_counts[signature] == 2
                    and call.name in OBSERVATION_TOOLS
                ):
                    evidence_id = result.metadata.get("evidence_id", "the earlier evidence")
                    recovery_feedback.append(
                        f"恢复策略：当前 revision 已第二次执行相同的 {call.name}。"
                        f"内容没有因代码变化而更新；请使用 {evidence_id} 或 working "
                        "checkpoint 中的已有证据，停止重复侦察并进入实现或验证。"
                    )
            else:
                action_streak["failed_count"] += 1
                if action_streak["failed_count"] == 2:
                    recovery_feedback.append(
                        f"恢复策略：同一失败操作 {call.name} 已连续失败两次。"
                        "不要进行第三次相同调用；请根据现有错误修改参数、"
                        "读取缺失证据，或切换实现方案。"
                    )
        if recovery_feedback:
            messages.append(
                {
                    "role": "user",
                    "content": "\n".join(recovery_feedback),
                }
            )
        return messages
