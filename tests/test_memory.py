import json
import tempfile
import unittest
from pathlib import Path

from proofcode.memory import LongTermMemoryStore, MemoryCandidate
from proofcode.state import WorkspaceState
from proofcode.tools import ToolRegistry
from proofcode.types import ToolCall, ToolResult


def record(
    state: WorkspaceState,
    name: str,
    arguments: dict,
    *,
    ok: bool = True,
    content: str = "ok",
    metadata: dict | None = None,
) -> str:
    result = state.record(
        ToolCall(f"call-{len(state.records) + 1}", name, arguments),
        ToolResult(ok, content, metadata or {}),
    )
    return result.metadata["evidence_id"]


class LongTermMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            dir=Path(__file__).parent
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.agent_home = self.root / "agent-home"

    def candidate(self, *, title: str = "Test convention", content: str = "Use unittest.") -> MemoryCandidate:
        return MemoryCandidate(
            id="MC0001",
            kind="fact",
            title=title,
            content=content,
            keywords=("tests", "unittest"),
            evidence=({"evidence_id": "E0001", "revision": 0},),
        )

    def test_commit_builds_bounded_index_and_reads_content_on_demand(self) -> None:
        store = LongTermMemoryStore(self.root, self.agent_home)

        committed = store.commit((self.candidate(),), run_id="run-1")

        self.assertEqual(committed, ("project:F0001",))
        index = store.index_prompt()
        self.assertIn("project:F0001 [fact] Test convention", index)
        self.assertNotIn("Use unittest.", index)
        recalled = store.read("F0001")
        self.assertIn('"content": "# Test convention\\n\\nUse unittest.\\n"', recalled or "")
        self.assertIn('"source_run_id": "run-1"', recalled or "")

    def test_exact_duplicate_is_reused_and_same_title_supersedes(self) -> None:
        store = LongTermMemoryStore(self.root, self.agent_home)
        first = store.commit((self.candidate(),), run_id="run-1")
        duplicate = store.commit((self.candidate(),), run_id="run-2")
        replacement = store.commit(
            (self.candidate(content="Run python -m unittest discover."),),
            run_id="run-3",
        )

        self.assertEqual(first, duplicate)
        self.assertEqual(replacement, ("project:F0002",))
        payload = json.loads(store.index_path.read_text(encoding="utf-8"))
        self.assertFalse(payload["entries"][0]["active"])
        self.assertEqual(payload["entries"][1]["supersedes"], "F0001")

    def test_corrupt_index_is_not_silently_overwritten(self) -> None:
        store = LongTermMemoryStore(self.root, self.agent_home)
        store.root.mkdir(parents=True)
        store.index_path.write_text("not json", encoding="utf-8")

        with self.assertRaises(OSError):
            store.commit((self.candidate(),), run_id="run-1")

        self.assertEqual(store.index_path.read_text(encoding="utf-8"), "not json")

    def test_global_sop_is_visible_from_another_workspace(self) -> None:
        first_workspace = self.root / "first"
        second_workspace = self.root / "second"
        first_workspace.mkdir()
        second_workspace.mkdir()
        sop = MemoryCandidate(
            id="MC0001",
            kind="sop",
            title="Safe smoke test",
            content="Use a temporary data copy.",
            keywords=("smoke", "temporary"),
            evidence=({"evidence_id": "E0001", "revision": 1},),
        )

        first = LongTermMemoryStore(first_workspace, self.agent_home)
        self.assertEqual(first.commit((sop,), run_id="run-1"), ("global:S0001",))
        second = LongTermMemoryStore(second_workspace, self.agent_home)

        self.assertIn("global:S0001 [sop] Safe smoke test", second.index_prompt())
        self.assertIn("Use a temporary data copy.", second.read("global:S0001") or "")
        self.assertFalse((first_workspace / ".proofcode" / "memory" / "l3_sops").exists())


class MemoryAdmissionTests(unittest.TestCase):
    def test_fact_requires_real_successful_current_evidence(self) -> None:
        state = WorkspaceState("Inspect project")
        failed = record(
            state,
            "read_file",
            {"path": "auth.py"},
            ok=False,
            metadata={"path": "auth.py"},
        )

        with self.assertRaisesRegex(ValueError, "failed evidence"):
            state.propose_memory(
                kind="fact",
                title="Authentication rule",
                content="Empty tokens are rejected.",
                keywords=["auth"],
                evidence_ids=[failed],
            )

    def test_sop_requires_current_project_validation(self) -> None:
        state = WorkspaceState("Fix auth")
        evidence = record(
            state,
            "read_file",
            {"path": "auth.py"},
            metadata={"path": "auth.py", "content_hash": "a" * 64},
        )

        with self.assertRaisesRegex(ValueError, "project validation"):
            state.propose_memory(
                kind="sop",
                title="Authentication validation",
                content="Run the complete authentication suite.",
                keywords=["auth", "test"],
                evidence_ids=[evidence],
            )

    def test_candidate_becomes_invalid_when_its_evidence_becomes_stale(self) -> None:
        state = WorkspaceState("Inspect auth")
        evidence = record(
            state,
            "read_file",
            {"path": "auth.py"},
            metadata={"path": "auth.py", "content_hash": "a" * 64},
        )
        candidate = state.propose_memory(
            kind="fact",
            title="Authentication entry point",
            content="auth.py contains the authentication entry point.",
            keywords=["auth"],
            evidence_ids=[evidence],
        )
        record(
            state,
            "replace_text",
            {"path": "auth.py"},
            metadata={"path": "auth.py", "changed": True, "after_hash": "b" * 64},
        )

        with self.assertRaisesRegex(ValueError, "no longer has current"):
            state.validate_memory_candidate(candidate)

    def test_sensitive_material_is_rejected(self) -> None:
        state = WorkspaceState("Inspect configuration")
        evidence = record(
            state,
            "read_file",
            {"path": "config.py"},
            metadata={"path": "config.py", "content_hash": "a" * 64},
        )

        with self.assertRaisesRegex(ValueError, "credential or secret"):
            state.propose_memory(
                kind="fact",
                title="Deployment secret",
                content="api_key=abcdefghijklmnop",
                keywords=["deployment"],
                evidence_ids=[evidence],
            )


class SkillCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            dir=Path(__file__).parent
        )
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "check_project.py"
        self.source.write_text("print('checked')\n", encoding="utf-8")
        self.agent_home = self.root / "agent-home"
        self.registry = ToolRegistry(
            self.root,
            agent_home=self.agent_home,
            approve=lambda _name, _args: True,
        )
        self.state = WorkspaceState(
            "Create a reusable check", self.registry.validation_policy
        )
        self.registry.attach_state(self.state)

    def stage_skill(self) -> None:
        source_evidence = record(
            self.state,
            "read_file",
            {"path": "check_project.py"},
            content="print('checked')",
            metadata={"path": "check_project.py", "content_hash": "a" * 64},
        )
        validation_evidence = record(
            self.state,
            "run_command",
            {"argv": ["python", "-m", "unittest", "discover"]},
            content="OK",
            metadata={"exit_code": 0, "workspace_changes": []},
        )
        self.state.propose_memory(
            kind="skill",
            title="Project checker",
            content=self.source.read_text(encoding="utf-8"),
            keywords=["check", "unittest"],
            evidence_ids=[source_evidence, validation_evidence],
            source_path="check_project.py",
        )

    def test_skill_commits_only_from_unchanged_validated_source(self) -> None:
        self.stage_skill()

        committed = self.registry.commit_memory(run_id="run-1")

        self.assertEqual(committed, ("global:K0001",))
        saved = next((self.agent_home / "memory" / "l3_skills").glob("*.py"))
        self.assertEqual(saved.read_text(encoding="utf-8"), "print('checked')\n")

    def test_skill_source_cannot_be_swapped_after_staging(self) -> None:
        self.stage_skill()
        self.source.write_text("print('different')\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "changed after staging"):
            self.registry.commit_memory(run_id="run-1")


if __name__ == "__main__":
    unittest.main()
