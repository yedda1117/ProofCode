from __future__ import annotations

import json
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
    def test_verified_change_automatically_triggers_memory_consolidation(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "value.txt").write_text("old", encoding="utf-8")
            (root / "test_sample.py").write_text(
                "import unittest\n\n"
                "class SampleTests(unittest.TestCase):\n"
                "    def test_value_exists(self):\n"
                "        self.assertTrue(True)\n",
                encoding="utf-8",
            )
            required_command = [sys.executable, "-m", "unittest", "discover", "-v"]
            (root / ".proofcode.json").write_text(
                json.dumps({"validation": {"required_commands": [required_command]}}),
                encoding="utf-8",
            )
            model = ScriptedModel(
                [
                    tool_response(
                        "1",
                        "replace_text",
                        {"path": "value.txt", "old_text": "old", "new_text": "new"},
                    ),
                    tool_response("2", "run_command", {"argv": required_command}),
                    final_response("Implemented and validated."),
                    final_response("Implemented and validated; no reusable memory candidate."),
                ]
            )
            events: list[str] = []
            registry = ToolRegistry(root, approve=lambda _name, _args: True)

            result = CodingAgent(
                model=model,
                tools=registry,
                max_steps=4,
                on_event=lambda kind, _data: events.append(kind),
            ).run("Update it")

            self.assertEqual(result.reason, StopReason.COMPLETED)
            self.assertEqual(events.count("memory_reflection"), 1)
            self.assertIn("自动经验固化阶段", str(model.seen_messages[3]))

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
            self.assertIn("暂不接受完成声明", str(model.seen_messages[2]))
            self.assertIn("无关的成功命令", str(model.seen_messages[4]))

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
            self.assertIn("测试或检查失败", str(model.seen_messages[3]))

    def test_stops_repeated_identical_action(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            response = tool_response(
                "1", "run_command", {"argv": [sys.executable, "-c", "print('same')"]}
            )
            model = ScriptedModel([response, response, response])
            registry = ToolRegistry(Path(directory), approve=lambda _name, _args: True)

            result = CodingAgent(model=model, tools=registry, max_steps=5).run("Inspect")

            self.assertEqual(result.reason, StopReason.REPEATED_ACTION)
            self.assertEqual(result.steps, 3)

    def test_stops_repeated_observation_cycle_without_revision_progress(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "a.py").write_text("a = 1\n", encoding="utf-8")
            (root / "b.py").write_text("b = 2\n", encoding="utf-8")
            model = ScriptedModel(
                [
                    tool_response("1", "read_file", {"path": "a.py"}),
                    tool_response("2", "read_file", {"path": "b.py"}),
                    tool_response("3", "read_file", {"path": "a.py"}),
                    tool_response("4", "read_file", {"path": "b.py"}),
                    tool_response("5", "read_file", {"path": "a.py"}),
                    final_response("Inspection complete using the existing evidence."),
                ]
            )
            registry = ToolRegistry(root, approve=lambda _name, _args: True)

            result = CodingAgent(model=model, tools=registry, max_steps=8).run("Inspect")

            self.assertEqual(result.reason, StopReason.COMPLETED)
            self.assertEqual(result.steps, 6)
            self.assertIn("停止重复侦察", str(model.seen_messages[4]))
            self.assertIn("未重复执行", str(model.seen_messages[5]))

    def test_repeated_context_recovery_is_skipped_without_stopping(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "a.py").write_text("a = 1\n", encoding="utf-8")
            model = ScriptedModel(
                [
                    tool_response("1", "read_file", {"path": "a.py"}),
                    tool_response("2", "read_context", {"id": "E0001", "max_chars": 6000}),
                    tool_response("3", "read_context", {"id": "E0001", "max_chars": 6000}),
                    tool_response("4", "read_context", {"id": "E0001", "max_chars": 6000}),
                    final_response("Continued using E0001."),
                ]
            )
            events: list[str] = []
            registry = ToolRegistry(root, approve=lambda _name, _args: True)

            result = CodingAgent(
                model=model,
                tools=registry,
                max_steps=5,
                on_event=lambda kind, _data: events.append(kind),
            ).run("Inspect")

            self.assertEqual(result.reason, StopReason.COMPLETED)
            self.assertEqual(events.count("tool_call_skipped"), 1)

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
            self.assertIn("LONG-TERM L1 MEMORY INDEX", first_context)
            self.assertIn("RUNTIME STATE", first_context)
            self.assertIn("no verified workspace observations", first_context)
            self.assertIn("C0001", second_context)
            self.assertIn("E0001", second_context)

    def test_successful_run_consolidates_memory_for_the_next_run(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
                encoding="utf-8",
            )
            first_model = ScriptedModel(
                [
                    tool_response("1", "read_file", {"path": "pyproject.toml"}),
                    tool_response(
                        "2",
                        "propose_memory",
                        {
                            "kind": "fact",
                            "title": "Test directory",
                            "content": "Project tests are discovered under tests/.",
                            "keywords": ["pytest", "tests"],
                            "evidence_ids": ["E0001"],
                        },
                    ),
                    final_response("Inspected the test configuration."),
                ]
            )
            first_registry = ToolRegistry(root, approve=lambda _name, _args: True)

            first_result = CodingAgent(
                model=first_model,
                tools=first_registry,
                run_id="run-first",
            ).run("Inspect the test configuration")

            self.assertEqual(first_result.reason, StopReason.COMPLETED)
            second_model = ScriptedModel(
                [tool_response("3", "read_file", {"path": "pyproject.toml"}), final_response("Done.")]
            )
            second_registry = ToolRegistry(root, approve=lambda _name, _args: True)

            second_result = CodingAgent(
                model=second_model,
                tools=second_registry,
                run_id="run-second",
            ).run("Check how tests are organized")

            self.assertEqual(second_result.reason, StopReason.COMPLETED)
            second_run_initial_context = str(second_model.seen_messages[0])
            self.assertIn("project:F0001 [fact] Test directory", second_run_initial_context)
            self.assertNotIn("Project tests are discovered under tests/", second_run_initial_context)


if __name__ == "__main__":
    unittest.main()
