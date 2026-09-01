import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from proofcode.tools import ToolRegistry
from proofcode.state import WorkspaceState
from proofcode.types import ToolCall, ToolResult


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
        self.assertEqual(len(result.metadata["content_hash"]), 64)

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

    def test_replace_records_before_and_after_hashes(self) -> None:
        path = self.root / "a.txt"
        path.write_text("old", encoding="utf-8")

        result = self.registry.execute(
            "replace_text",
            {"path": "a.txt", "old_text": "old", "new_text": "new"},
        )

        self.assertTrue(result.ok)
        self.assertNotEqual(result.metadata["before_hash"], result.metadata["after_hash"])

    def test_apply_patch_updates_file_and_records_hashes(self) -> None:
        path = self.root / "a.txt"
        path.write_text("first\nsecond\nthird\n", encoding="utf-8")

        result = self.registry.execute(
            "apply_patch",
            {
                "path": "a.txt",
                "patch": "@@ -1,3 +1,4 @@\n first\n-second\n+changed\n third\n+fourth",
            },
        )

        self.assertTrue(result.ok)
        self.assertEqual(path.read_text(encoding="utf-8"), "first\nchanged\nthird\nfourth\n")
        self.assertNotEqual(result.metadata["before_hash"], result.metadata["after_hash"])

    def test_apply_patch_rejects_stale_context_without_modifying_file(self) -> None:
        path = self.root / "a.txt"
        path.write_text("current\n", encoding="utf-8")

        result = self.registry.execute(
            "apply_patch",
            {"path": "a.txt", "patch": "@@ -1 +1 @@\n-old\n+new"},
        )

        self.assertFalse(result.ok)
        self.assertIn("context does not match", result.content)
        self.assertEqual(path.read_text(encoding="utf-8"), "current\n")

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_show_diff_reports_tracked_and_untracked_changes(self) -> None:
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        (self.root / "a.txt").write_text("before\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=self.root, check=True)
        (self.root / "a.txt").write_text("after\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=self.root, check=True)
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")

        result = self.registry.execute("show_diff", {})

        self.assertTrue(result.ok)
        self.assertIn("-before", result.content)
        self.assertIn("+after", result.content)
        self.assertIn("?? new.txt", result.content)

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

    def test_context_tools_retrieve_index_and_raw_evidence(self) -> None:
        state = WorkspaceState("Inspect")
        state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(
                True,
                "1 | source",
                {"path": "a.py", "start": 1, "end": 1, "content_hash": "d" * 64},
            ),
        )
        self.registry.attach_state(state)

        index = self.registry.execute("list_context", {})
        evidence = self.registry.execute("read_context", {"id": "E0001"})

        self.assertTrue(index.ok)
        self.assertIn("L1 CONTEXT INDEX", index.content)
        self.assertTrue(evidence.ok)
        self.assertIn("1 | source", evidence.content)

    def test_truncated_tool_result_retains_full_content_for_evidence(self) -> None:
        registry = ToolRegistry(
            self.root,
            output_limit=120,
            approve=lambda _name, _args: True,
        )
        (self.root / "long.txt").write_text("x" * 500, encoding="utf-8")

        result = registry.execute("read_file", {"path": "long.txt"})

        self.assertTrue(result.metadata["truncated"])
        self.assertLess(len(result.content), len(result.raw_content))

    def test_read_context_supports_chunked_recovery(self) -> None:
        state = WorkspaceState("Inspect")
        state.record(
            ToolCall("call-1", "read_file", {"path": "long.py"}),
            ToolResult(True, "x" * 500, {"path": "long.py", "start": 1, "end": 1}),
        )
        self.registry.attach_state(state)

        first = self.registry.execute(
            "read_context",
            {"id": "E0001", "offset": 0, "max_chars": 100},
        )
        second = self.registry.execute(
            "read_context",
            {"id": "E0001", "offset": first.metadata["next_offset"], "max_chars": 100},
        )

        self.assertEqual(len(first.content), 100)
        self.assertEqual(second.metadata["offset"], 100)
        self.assertGreater(second.metadata["total_chars"], 500)


if __name__ == "__main__":
    unittest.main()
