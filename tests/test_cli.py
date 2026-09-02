import io
import unittest
from contextlib import redirect_stdout

from proofcode.cli import Console, _compact_arguments, _indent
from proofcode.types import StopReason


class ConsoleTests(unittest.TestCase):
    def test_plain_console_keeps_structured_labels_without_ansi(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            console = Console(color=False)
            console.event("step", {"step": 2})
            console.event(
                "tool_call",
                {"name": "run_command", "arguments": {"argv": ["python", "-m", "unittest"]}},
            )
            console.event("tool_result", {"ok": True, "result": "exit_code=0\nOK"})
            console.final(StopReason.COMPLETED, "Done")

        rendered = output.getvalue()
        self.assertNotIn("\033[", rendered)
        self.assertIn("步骤 02", rendered)
        self.assertIn("◆ 工具  run_command", rendered)
        self.assertIn("✓ 任务完成", rendered)

    def test_color_console_wraps_semantic_status_with_ansi(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            Console(color=True).event(
                "verification_rejected",
                {"reason": "project-wide validation is missing"},
            )

        self.assertIn("\033[", output.getvalue())
        self.assertIn("完成门控", output.getvalue())

    def test_argument_compaction_and_indentation(self) -> None:
        self.assertEqual(
            _compact_arguments({"argv": ["python", "-m", "unittest"], "cwd": "."}),
            'argv=python -m unittest · cwd="."',
        )
        self.assertEqual(_indent("first\nsecond", "  "), "  first\n  second")


if __name__ == "__main__":
    unittest.main()
