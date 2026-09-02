import unittest

from proofcode.state import WorkspaceState
from proofcode.types import ToolCall, ToolResult


class WorkspaceStateTests(unittest.TestCase):
    def test_completion_requires_workspace_evidence(self) -> None:
        state = WorkspaceState("Fix a.py")

        self.assertIn("尚未取得任何工作区证据", state.completion_feedback())

        state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(True, "source", {"path": "a.py"}),
        )
        self.assertIsNone(state.completion_feedback())

    def test_context_navigation_alone_is_not_workspace_evidence(self) -> None:
        state = WorkspaceState("Fix a.py")
        state.record(
            ToolCall("call-1", "list_context", {}),
            ToolResult(True, "empty index", {}),
        )

        self.assertIn("尚未取得任何工作区证据", state.completion_feedback())

    def test_records_evidence_with_stable_ids(self) -> None:
        state = WorkspaceState()

        first = state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(True, "source", {"path": "a.py", "content_hash": "abc"}),
        )
        second = state.record(
            ToolCall("call-2", "run_command", {"argv": ["python", "-V"]}),
            ToolResult(True, "Python", {"exit_code": 0}),
        )

        self.assertEqual(first.metadata["evidence_id"], "E0001")
        self.assertEqual(second.metadata["evidence_id"], "E0002")
        self.assertEqual(state.get("E0001").content, "source")

    def test_successful_edit_advances_workspace_revision(self) -> None:
        state = WorkspaceState()

        read_result = state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(True, "source", {"path": "a.py"}),
        )
        edit_result = state.record(
            ToolCall("call-2", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "a.py"}),
        )

        self.assertEqual(read_result.metadata["revision"], 0)
        self.assertEqual(edit_result.metadata["revision"], 1)
        self.assertEqual(state.revision, 1)
        self.assertEqual(state.changed_files, {"a.py"})

    def test_failed_edit_does_not_advance_revision(self) -> None:
        state = WorkspaceState()

        result = state.record(
            ToolCall("call-1", "replace_text", {"path": "a.py"}),
            ToolResult(False, "not changed", {"changed": True, "path": "a.py"}),
        )

        self.assertEqual(result.metadata["revision"], 0)
        self.assertEqual(state.changed_files, set())

    def test_file_context_points_to_raw_evidence(self) -> None:
        state = WorkspaceState("Understand the project")

        state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(
                True,
                "1 | value = 1",
                {"path": "a.py", "start": 1, "end": 1, "content_hash": "a" * 64},
            ),
        )

        entry = state.entries[0]
        self.assertEqual(entry.kind, "file")
        self.assertEqual(entry.evidence_ids, ("E0001",))
        self.assertIn('"content": "1 | value = 1"', state.describe("E0001"))

    def test_edit_marks_related_context_and_old_commands_stale(self) -> None:
        state = WorkspaceState("Change a.py")
        state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(True, "source", {"path": "a.py", "start": 1, "end": 1}),
        )
        state.record(
            ToolCall("call-2", "run_command", {"argv": ["python", "-m", "unittest"]}),
            ToolResult(True, "OK", {"exit_code": 0}),
        )

        state.record(
            ToolCall("call-3", "replace_text", {"path": "a.py"}),
            ToolResult(
                True,
                "updated a.py",
                {"changed": True, "path": "a.py", "after_hash": "b" * 64},
            ),
        )

        self.assertTrue(state.entries[0].stale)
        self.assertTrue(state.entries[1].stale)
        self.assertFalse(state.entries[2].stale)
        self.assertEqual(state.entries[2].revision, 1)

    def test_index_is_compact_and_does_not_copy_raw_file_content(self) -> None:
        state = WorkspaceState("Inspect")
        state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(
                True,
                "secret raw source body",
                {"path": "a.py", "start": 1, "end": 20, "content_hash": "c" * 64},
            ),
        )

        index = state.index()

        self.assertIn("C0001", index)
        self.assertIn("E0001", index)
        self.assertNotIn("secret raw source body", index)

    def test_omitted_early_entry_remains_discoverable_through_catalog(self) -> None:
        state = WorkspaceState("Inspect a long trajectory")
        for number in range(15):
            state.record(
                ToolCall(f"call-{number}", "read_file", {"path": f"module_{number}.py"}),
                ToolResult(
                    True,
                    f"content for unique-marker-{number}",
                    {
                        "path": f"module_{number}.py",
                        "start": 1,
                        "end": 1,
                        "content_hash": f"{number:064x}",
                    },
                ),
            )

        index = state.index(max_entries=12)
        matches = state.search_context("unique-marker-0")

        self.assertNotIn("C0001", index)
        self.assertEqual(matches[0]["id"], "E0001")
        recovered = state.describe(matches[0]["id"])
        self.assertIn("unique-marker-0", recovered or "")

    def test_context_search_excludes_stale_evidence_unless_requested(self) -> None:
        state = WorkspaceState("Change a.py")
        state.record(
            ToolCall("call-1", "read_file", {"path": "a.py"}),
            ToolResult(True, "old-marker", {"path": "a.py", "start": 1, "end": 1}),
        )
        state.record(
            ToolCall("call-2", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "a.py"}),
        )

        self.assertEqual(state.search_context("old-marker"), ())
        historical = state.search_context("old-marker", include_stale=True)
        self.assertEqual(historical[0]["id"], "E0001")
        self.assertTrue(historical[0]["stale"])

    def test_search_context_becomes_stale_when_covered_path_changes(self) -> None:
        state = WorkspaceState("Find and change a symbol")
        state.record(
            ToolCall("call-1", "search_text", {"path": "src", "query": "target"}),
            ToolResult(
                True,
                "src/a.py:1: target",
                {"path": "src", "query": "target", "matches": 1},
            ),
        )

        state.record(
            ToolCall("call-2", "replace_text", {"path": "src/a.py"}),
            ToolResult(
                True,
                "updated src/a.py",
                {"changed": True, "path": "src/a.py", "after_hash": "e" * 64},
            ),
        )

        self.assertEqual(state.entries[0].kind, "search")
        self.assertTrue(state.entries[0].stale)

    def test_unrelated_successful_command_is_not_completion_evidence(self) -> None:
        state = WorkspaceState("Change a.py")
        state.record(
            ToolCall("call-1", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "a.py"}),
        )
        state.record(
            ToolCall("call-2", "run_command", {"argv": ["python", "-c", "print('ok')"]}),
            ToolResult(True, "ok", {"exit_code": 0}),
        )

        self.assertEqual(state.validation_status(), "missing")
        self.assertIn("无关的成功命令", state.completion_feedback())

    def test_test_result_is_recorded_as_validation(self) -> None:
        state = WorkspaceState("Change a.py")
        state.record(
            ToolCall("call-1", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "a.py"}),
        )

        result = state.record(
            ToolCall("call-2", "run_command", {"argv": ["python", "-m", "unittest"]}),
            ToolResult(True, "OK", {"exit_code": 0}),
        )

        self.assertEqual(result.metadata["validation_id"], "V0001")
        self.assertEqual(result.metadata["validation_kind"], "test")
        self.assertEqual(state.validation_status(), "passed")
        self.assertIsNone(state.completion_feedback())
        self.assertIn("validation_status: passed", state.index())

    def test_focused_test_alone_does_not_allow_completion(self) -> None:
        state = WorkspaceState("Change auth.py")
        state.record(
            ToolCall("call-1", "replace_text", {"path": "auth.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "auth.py"}),
        )
        state.record(
            ToolCall("call-2", "run_command", {"argv": ["pytest", "tests/test_math.py"]}),
            ToolResult(True, "passed", {"exit_code": 0}),
        )

        self.assertEqual(state.validation_status(), "focused_only")
        self.assertIn("项目级 baseline", state.completion_feedback())

    def test_command_workspace_change_invalidates_previous_validation(self) -> None:
        state = WorkspaceState("Change generated.py")
        state.record(
            ToolCall("call-1", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "a.py"}),
        )
        state.record(
            ToolCall("call-2", "run_command", {"argv": ["pytest"]}),
            ToolResult(True, "passed", {"exit_code": 0}),
        )
        state.record(
            ToolCall("call-3", "run_command", {"argv": ["generator"]}),
            ToolResult(True, "generated", {"exit_code": 0, "workspace_changes": ["generated.py"]}),
        )

        self.assertEqual(state.revision, 2)
        self.assertIn("generated.py", state.changed_files)
        self.assertEqual(state.validation_status(), "missing")

    def test_failed_validation_must_be_resolved(self) -> None:
        state = WorkspaceState("Change a.py")
        state.record(
            ToolCall("call-1", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "a.py"}),
        )
        command = ["python", "-m", "unittest", "discover"]
        state.record(
            ToolCall("call-2", "run_command", {"argv": command}),
            ToolResult(False, "FAILED", {"exit_code": 1}),
        )

        self.assertEqual(state.validation_status(), "failed")

        state.record(
            ToolCall("call-3", "run_command", {"argv": command}),
            ToolResult(True, "OK", {"exit_code": 0}),
        )

        self.assertEqual(state.validation_status(), "passed")

    def test_edit_invalidates_previous_validation(self) -> None:
        state = WorkspaceState("Change a.py")
        state.record(
            ToolCall("call-1", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated", {"changed": True, "path": "a.py"}),
        )
        state.record(
            ToolCall("call-2", "run_command", {"argv": ["pytest"]}),
            ToolResult(True, "passed", {"exit_code": 0}),
        )
        state.record(
            ToolCall("call-3", "replace_text", {"path": "a.py"}),
            ToolResult(True, "updated again", {"changed": True, "path": "a.py"}),
        )

        self.assertTrue(state.validations[0].stale)
        self.assertEqual(state.validation_status(), "missing")


if __name__ == "__main__":
    unittest.main()
