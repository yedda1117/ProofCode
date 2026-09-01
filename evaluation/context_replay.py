from __future__ import annotations

import json
from dataclasses import dataclass

from proofcode.context import Conversation
from proofcode.state import WorkspaceState
from proofcode.tools import format_tool_result
from proofcode.types import ToolCall, ToolResult


@dataclass(frozen=True)
class ReplayResult:
    rounds: int
    linear_total_chars: int
    layered_total_chars: int
    linear_peak_chars: int
    truncated_total_chars: int
    truncated_peak_chars: int
    truncated_visible_evidence_chars: int
    layered_peak_chars: int
    raw_evidence_chars: int
    recovered_evidence_chars: int

    @property
    def reduction_ratio(self) -> float:
        return 1 - self.layered_total_chars / self.linear_total_chars


def serialized_size(messages: list[dict[str, object]]) -> int:
    return len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))


def run_replay(*, rounds: int = 18, payload_chars: int = 6_000) -> ReplayResult:
    linear = Conversation("system", "Inspect, modify, and validate the project")
    truncated = Conversation("system", "Inspect, modify, and validate the project")
    layered = Conversation("system", "Inspect, modify, and validate the project")
    state = WorkspaceState("Inspect, modify, and validate the project")
    linear_sizes: list[int] = []
    truncated_sizes: list[int] = []
    layered_sizes: list[int] = []

    for number in range(1, rounds + 1):
        path = f"src/module_{number % 6}.py"
        if number in {7, 13}:
            call = ToolCall(
                f"call-{number}",
                "replace_text",
                {"path": path, "old_text": "old", "new_text": "new"},
            )
            result = ToolResult(
                True,
                f"updated {path}",
                {
                    "changed": True,
                    "path": path,
                    "before_hash": "a" * 64,
                    "after_hash": "b" * 64,
                },
            )
        elif number in {6, 12, 18}:
            call = ToolCall(
                f"call-{number}",
                "run_command",
                {"argv": ["python", "-m", "unittest", "discover", "-v"]},
            )
            result = ToolResult(
                True,
                "test output\n" + "passed case\n" * (payload_chars // 12),
                {"exit_code": 0, "duration": 0.3},
            )
        else:
            call = ToolCall(f"call-{number}", "read_file", {"path": path})
            result = ToolResult(
                True,
                f"{path}\n" + "source line\n" * (payload_chars // 12),
                {
                    "path": path,
                    "start": 1,
                    "end": payload_chars // 12,
                    "content_hash": f"{number:064x}",
                },
            )

        recorded = state.record(call, result)
        assistant_message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
            ],
        }
        tool_message = {
            "role": "tool",
            "tool_call_id": call.id,
            "content": format_tool_result(recorded),
        }
        linear.add_exchange(assistant_message, [tool_message])
        truncated.add_exchange(assistant_message, [tool_message])
        layered.add_exchange(assistant_message, [tool_message])

        linear_sizes.append(serialized_size(linear.messages(120_000)))
        truncated_sizes.append(serialized_size(truncated.messages(24_000)))
        layered_sizes.append(
            serialized_size(layered.messages(24_000, state.prompt_context()))
        )

    raw_chars = sum(len(record.content) for record in state.records)
    final_truncated_messages = truncated.messages(24_000)
    visible_evidence_chars = sum(
        len(str(message.get("content", "")))
        for message in final_truncated_messages
        if message.get("role") == "tool"
    )
    recovered_chars = sum(
        len(json.loads(state.describe(record.id) or "{}").get("content", ""))
        for record in state.records
    )
    return ReplayResult(
        rounds=rounds,
        linear_total_chars=sum(linear_sizes),
        layered_total_chars=sum(layered_sizes),
        linear_peak_chars=max(linear_sizes),
        truncated_total_chars=sum(truncated_sizes),
        truncated_peak_chars=max(truncated_sizes),
        truncated_visible_evidence_chars=visible_evidence_chars,
        layered_peak_chars=max(layered_sizes),
        raw_evidence_chars=raw_chars,
        recovered_evidence_chars=recovered_chars,
    )


def main() -> None:
    result = run_replay()
    print(f"rounds={result.rounds}")
    print(f"linear_total_chars={result.linear_total_chars}")
    print(f"truncated_total_chars={result.truncated_total_chars}")
    print(f"layered_total_chars={result.layered_total_chars}")
    print(f"reduction={result.reduction_ratio:.1%}")
    print(f"linear_peak_chars={result.linear_peak_chars}")
    print(f"truncated_peak_chars={result.truncated_peak_chars}")
    print(f"layered_peak_chars={result.layered_peak_chars}")
    print(f"truncated_visible_evidence_chars={result.truncated_visible_evidence_chars}")
    print(f"raw_evidence_chars={result.raw_evidence_chars}")
    print(f"recovered_evidence_chars={result.recovered_evidence_chars}")


if __name__ == "__main__":
    main()
