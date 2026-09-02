from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

from proofcode.context import Conversation
from proofcode.state import WorkspaceState
from proofcode.tools import ToolRegistry, format_tool_result
from proofcode.types import ToolCall, ToolResult


@dataclass(frozen=True)
class DesignScenarioResult:
    long_output_visible: bool
    long_output_searchable: bool
    long_output_recovered: bool
    early_pointer_visible: bool
    early_evidence_searchable: bool
    early_evidence_recovered: bool
    validation_states: tuple[str, ...]


def run_design_scenarios() -> DesignScenarioResult:
    marker = "ROOT_CAUSE_AUTH_401"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        root.joinpath("failure.log").write_text(
            "setup log\n" + "noise\n" * 198 + marker + "\n" + "noise\n" * 200,
            encoding="utf-8",
        )
        long_state = WorkspaceState("Diagnose a long test failure")
        registry = ToolRegistry(root, output_limit=600, approve=lambda _name, _args: True)
        call = ToolCall("long-1", "read_file", {"path": "failure.log"})
        visible_result = registry.execute(call.name, call.arguments)
        recorded_result = long_state.record(call, visible_result)
        registry.attach_state(long_state)
        long_search = registry.execute("search_context", {"query": marker})
        long_match = next(
            item for item in long_search.metadata["matches"] if item["id"] == "E0001"
        )
        long_read = registry.execute(
            "read_context",
            {"id": long_match["id"], "offset": long_match["offset"], "max_chars": 400},
        )
        long_output_visible = marker in recorded_result.content
        long_output_searchable = long_search.metadata["count"] > 0
        long_output_recovered = marker in long_read.content

    history_state = WorkspaceState("Recover an early observation after a long trajectory")
    conversation = Conversation("system", "Recover an early API contract")
    for number in range(18):
        call = ToolCall(
            f"history-{number}",
            "read_file",
            {"path": f"src/module_{number}.py"},
        )
        recorded = history_state.record(
            call,
            ToolResult(
                True,
                (
                    f"implementation detail EARLY_API_CONTRACT_{number}\n"
                    + f"module {number} body\n" * 20
                ),
                {
                    "path": f"src/module_{number}.py",
                    "start": 1,
                    "end": 1,
                    "content_hash": f"{number:064x}",
                },
            ),
        )
        conversation.add_exchange(
            {
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
            },
            [
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": format_tool_result(recorded),
                }
            ],
        )
    model_view = json.dumps(
        conversation.messages(4_000, history_state.prompt_context()),
        ensure_ascii=False,
    )
    history_registry = ToolRegistry(Path("."), approve=lambda _name, _args: True)
    history_registry.attach_state(history_state)
    early_search = history_registry.execute(
        "search_context", {"query": "EARLY_API_CONTRACT_0"}
    )
    early_match = next(
        item for item in early_search.metadata["matches"] if item["id"] == "E0001"
    )
    early_read = history_registry.execute(
        "read_context",
        {"id": early_match["id"], "offset": early_match["offset"], "max_chars": 400},
    )

    validation_state = WorkspaceState("Modify and validate auth.py")
    validation_state.record(
        ToolCall("gate-1", "replace_text", {"path": "auth.py"}),
        ToolResult(True, "first edit", {"changed": True, "path": "auth.py"}),
    )
    states = [validation_state.validation_status()]
    validation_state.record(
        ToolCall("gate-2", "run_command", {"argv": ["pytest"]}),
        ToolResult(True, "passed", {"exit_code": 0}),
    )
    states.append(validation_state.validation_status())
    validation_state.record(
        ToolCall("gate-3", "replace_text", {"path": "auth.py"}),
        ToolResult(True, "second edit", {"changed": True, "path": "auth.py"}),
    )
    states.append(validation_state.validation_status())
    validation_state.record(
        ToolCall("gate-4", "run_command", {"argv": ["pytest", "tests/test_auth.py"]}),
        ToolResult(True, "focused passed", {"exit_code": 0}),
    )
    states.append(validation_state.validation_status())
    validation_state.record(
        ToolCall("gate-5", "run_command", {"argv": ["pytest"]}),
        ToolResult(True, "project passed", {"exit_code": 0}),
    )
    states.append(validation_state.validation_status())

    return DesignScenarioResult(
        long_output_visible=long_output_visible,
        long_output_searchable=long_output_searchable,
        long_output_recovered=long_output_recovered,
        early_pointer_visible="EARLY_API_CONTRACT_0" in model_view,
        early_evidence_searchable=early_search.metadata["count"] > 0,
        early_evidence_recovered="EARLY_API_CONTRACT_0" in early_read.content,
        validation_states=tuple(states),
    )


def main() -> None:
    result = run_design_scenarios()
    print("[场景一] 长工具输出中的中段错误")
    print(f"  默认可见: {result.long_output_visible}")
    print(f"  索引检索: {result.long_output_searchable}")
    print(f"  原文恢复: {result.long_output_recovered}")
    print("[场景二] 长轨迹中已移出常驻索引的早期证据")
    print(f"  常驻可见: {result.early_pointer_visible}")
    print(f"  按需检索: {result.early_evidence_searchable}")
    print(f"  原文恢复: {result.early_evidence_recovered}")
    print("[场景三] 修改后的验证状态迁移")
    print("  " + " -> ".join(result.validation_states))


if __name__ == "__main__":
    main()
