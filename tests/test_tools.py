import sys
import tempfile
import unittest
from pathlib import Path

from proofcode.tools import ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        (self.root / "a.py").write_text("", encoding="utf-8")
        (self.root / "a.txt").write_text("", encoding="utf-8")
        self.registry = ToolRegistry(self.root, approve=lambda _name, _args: True)

    def test_read_file_adds_line_numbers(self) -> None:
        (self.root / "a.py").write_text("first\nsecond\n", encoding="utf-8")

        result = self.registry.execute("read_file", {"path": "a.py"})

        self.assertTrue(result.ok)
        self.assertIn("1 | first", result.content)
        self.assertIn("2 | second", result.content)

    def test_path_cannot_escape_workspace(self) -> None:
        result = self.registry.execute("read_file", {"path": "../outside.txt"})

        self.assertFalse(result.ok)
        self.assertEqual(result.metadata["category"], "path_violation")

    def test_replace_requires_unique_match(self) -> None:
        path = self.root / "a.txt"
        path.write_text("same\nsame\n", encoding="utf-8")

        result = self.registry.execute(
            "replace_text",
            {"path": "a.txt", "old_text": "same", "new_text": "new"},
        )

        self.assertFalse(result.ok)
        self.assertEqual(path.read_text(encoding="utf-8"), "same\nsame\n")

    def test_run_command_captures_exit_code(self) -> None:
        result = self.registry.execute(
            "run_command",
            {"argv": [sys.executable, "-c", "print('verified')"]},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.metadata["exit_code"], 0)
        self.assertIn("verified", result.content)

    def test_rejects_unknown_arguments(self) -> None:
        result = self.registry.execute(
            "read_file",
            {"path": "a.py", "unexpected": True},
        )

        self.assertFalse(result.ok)
        self.assertIn("unknown arguments", result.content)


if __name__ == "__main__":
    unittest.main()
