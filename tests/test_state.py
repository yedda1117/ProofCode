import unittest

from proofcode.state import WorkspaceState
from proofcode.types import ToolCall, ToolResult


class WorkspaceStateTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
