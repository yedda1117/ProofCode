from __future__ import annotations

import sys
import tempfile
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
    def test_changed_file_requires_project_validation_before_completion(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "value.txt").write_text("old", encoding="utf-8")
            (root / "test_sample.py").write_text(
                "import unittest\n\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
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
                    tool_response(
                        "3",
                        "run_command",
                        {"argv": [sys.executable, "-m", "unittest", "discover"]},
                    ),
                    final_response("Changed value.txt and validated it."),
                ]
            )
            registry = ToolRegistry(root, approve=lambda _name, _args: True)

            result = CodingAgent(model=model, tools=registry, max_steps=7).run("Update it")

            self.assertEqual(result.reason, StopReason.COMPLETED)
            self.assertEqual(root.joinpath("value.txt").read_text(encoding="utf-8"), "new")
            self.assertEqual(result.steps, 6)
            self.assertIn("Completion is not accepted", str(model.seen_messages[2]))
            self.assertIn("unrelated successful command", str(model.seen_messages[4]))

    def test_failed_validation_is_returned_as_feedback_before_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "value.txt").write_text("old", encoding="utf-8")
            (root / "test_sample.py").write_text(
                "import unittest\n"
                "from pathlib import Path\n\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertEqual(Path('value.txt').read_text(), 'new')\n",
                encoding="utf-8",
            )
            model = ScriptedModel(
                [
                    tool_response(
                        "1",
                        "replace_text",
                        {"path": "value.txt", "old_text": "old", "new_text": "bad"},
                    ),
                    tool_response(
                        "2",
                        "run_command",
                        {"argv": [sys.executable, "-m", "unittest", "discover"]},
                    ),
                    final_response("Done."),
                    tool_response(
                        "3",
                        "replace_text",
                        {"path": "value.txt", "old_text": "bad", "new_text": "new"},
                    ),
                    tool_response(
                        "4",
                        "run_command",
                        {"argv": [sys.executable, "-m", "unittest", "discover"]},
                    ),
                    final_response("Changed and tested value.txt."),
                ]
            )
            registry = ToolRegistry(root, approve=lambda _name, _args: True)

            result = CodingAgent(model=model, tools=registry, max_steps=6).run("Update it")

            self.assertEqual(result.reason, StopReason.COMPLETED)
            self.assertEqual(result.steps, 6)
            self.assertIn("recorded test or check still fails", str(model.seen_messages[3]))

    def test_stops_repeated_identical_action(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            response = tool_response("1", "list_files", {"path": "."})
            model = ScriptedModel([response, response, response])
            registry = ToolRegistry(Path(directory), approve=lambda _name, _args: True)

            result = CodingAgent(model=model, tools=registry, max_steps=5).run("Inspect")

            self.assertEqual(result.reason, StopReason.REPEATED_ACTION)
            self.assertEqual(result.steps, 3)

    def test_injects_hierarchical_context_into_each_model_call(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "value.txt").write_text("value", encoding="utf-8")
            model = ScriptedModel(
                [
                    tool_response("1", "read_file", {"path": "value.txt"}),
                    final_response("Inspected value.txt."),
                ]
            )
            registry = ToolRegistry(root, approve=lambda _name, _args: True)

            result = CodingAgent(model=model, tools=registry).run("Inspect the value")

            self.assertEqual(result.reason, StopReason.COMPLETED)
            first_context = str(model.seen_messages[0])
            second_context = str(model.seen_messages[1])
            self.assertIn("L1 CONTEXT INDEX", first_context)
            self.assertIn("no verified workspace observations", first_context)
            self.assertIn("C0001", second_context)
            self.assertIn("E0001", second_context)


if __name__ == "__main__":
    unittest.main()
