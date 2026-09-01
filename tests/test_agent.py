from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

from proofcode.agent import CodingAgent
from proofcode.tools import ToolRegistry
from proofcode.types import ModelResponse, StopReason, ToolCall


def tool_response(call_id: str, name: str, arguments: dict[str, Any]) -> ModelResponse:
    raw_call = {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }
    return ModelResponse(
        content=None,
        tool_calls=(ToolCall(call_id, name, arguments),),
        raw_message={"role": "assistant", "content": None, "tool_calls": [raw_call]},
        finish_reason="tool_calls",
    )


def final_response(content: str) -> ModelResponse:
    return ModelResponse(
        content=content,
        tool_calls=(),
        raw_message={"role": "assistant", "content": content},
        finish_reason="stop",
    )


class ScriptedModel:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = iter(responses)
        self.seen_messages: list[list[dict[str, Any]]] = []

    def complete(self, messages, tools):
        self.seen_messages.append(messages)
        return next(self.responses)


class CodingAgentTests(unittest.TestCase):
    def test_changed_file_requires_successful_command_before_completion(self) -> None:
        root = Path(__file__).parent / "runtime" / "agent"
        (root / "value.txt").write_text("old", encoding="utf-8")
        model = ScriptedModel(
            [
                tool_response(
                    "1",
                    "replace_text",
                    {"path": "value.txt", "old_text": "old", "new_text": "new"},
                ),
                final_response("Done."),
                tool_response(
                    "2",
                    "run_command",
                    {"argv": [sys.executable, "-c", "print('ok')"]},
                ),
                final_response("Changed value.txt and validated it."),
            ]
        )
        registry = ToolRegistry(root, approve=lambda _name, _args: True)

        result = CodingAgent(model=model, tools=registry, max_steps=5).run("Update it")

        self.assertEqual(result.reason, StopReason.COMPLETED)
        self.assertEqual(root.joinpath("value.txt").read_text(encoding="utf-8"), "new")
        self.assertEqual(result.steps, 4)
        self.assertIn("Completion is not accepted", str(model.seen_messages[2]))

    def test_stops_repeated_identical_action(self) -> None:
        root = Path(__file__).parent / "runtime" / "agent"
        response = tool_response("1", "list_files", {"path": "."})
        model = ScriptedModel([response, response, response])
        registry = ToolRegistry(root, approve=lambda _name, _args: True)

        result = CodingAgent(model=model, tools=registry, max_steps=5).run("Inspect")

        self.assertEqual(result.reason, StopReason.REPEATED_ACTION)
        self.assertEqual(result.steps, 3)


if __name__ == "__main__":
    unittest.main()
