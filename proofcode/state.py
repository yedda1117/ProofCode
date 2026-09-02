from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from proofcode.memory import MemoryCandidate
from proofcode.project import ValidationPolicy
from proofcode.types import ToolCall, ToolResult
from proofcode.validation import (
    classify_validation,
    normalized_validation_argv,
    validation_scope,
)


ADMINISTRATIVE_TOOLS = frozenset(
    {
        "list_context",
        "search_context",
        "read_context",
        "update_working_memory",
        "search_memory",
        "read_memory",
        "propose_memory",
    }
)


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    tool: str
    arguments: dict[str, Any]
    ok: bool
    content: str
    metadata: dict[str, Any]
    revision: int


@dataclass
class ContextEntry:
    id: str
    kind: str
    title: str
    summary: str
    evidence_ids: tuple[str, ...]
    revision: int
    paths: tuple[str, ...] = ()
    stale: bool = False


@dataclass
class ValidationRecord:
    id: str
    argv: tuple[str, ...]
    kind: str
    ok: bool
    evidence_id: str
    revision: int
    scope: str = "project"
    stale: bool = False


@dataclass
class WorkingMemoryItem:
    id: str
    kind: str
    content: str
    evidence_ids: tuple[str, ...]
    paths: tuple[str, ...]
    revision: int
    stale: bool = False


class WorkspaceState:
    def __init__(
        self,
        task: str = "",
        validation_policy: ValidationPolicy | None = None,
        long_term_index: str = "",
    ) -> None:
        self.task = task.strip()
        self.validation_policy = validation_policy or ValidationPolicy()
        self.long_term_index = long_term_index.strip()
        self.revision = 0
        self.changed_files: set[str] = set()
        self._records: list[EvidenceRecord] = []
        self._entries: list[ContextEntry] = []
        self._validations: list[ValidationRecord] = []
        self.working_goal = self.task
        self.next_action = "inspect the workspace and identify the relevant code"
        self._working_memory: list[WorkingMemoryItem] = []
        self.checkpoint_revision = 0
        self.checkpoint_workspace_revision = 0
        self.checkpoint_evidence_count = 0
        self._next_memory_id = 1
        self._memory_candidates: list[MemoryCandidate] = []

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    @property
    def entries(self) -> tuple[ContextEntry, ...]:
        return tuple(self._entries)

    @property
    def validations(self) -> tuple[ValidationRecord, ...]:
        return tuple(self._validations)

    @property
    def working_memory(self) -> tuple[WorkingMemoryItem, ...]:
        return tuple(self._working_memory)

    @property
    def memory_candidates(self) -> tuple[MemoryCandidate, ...]:
        return tuple(self._memory_candidates)

    def record(self, call: ToolCall, result: ToolResult) -> ToolResult:
        metadata = dict(result.metadata)
        path = metadata.get("path")
        command_changes = metadata.get("workspace_changes", [])
        changed_paths = (
            [path]
            if result.ok and metadata.get("changed") and isinstance(path, str)
            else [item for item in command_changes if isinstance(item, str)]
        )
        if changed_paths:
            self.revision += 1
            for changed_path in changed_paths:
                self.changed_files.add(changed_path)
                self._invalidate_for_change(changed_path)

        evidence_id = f"E{len(self._records) + 1:04d}"
        metadata.update({"evidence_id": evidence_id, "revision": self.revision})
        validation = self._record_validation(call, result, evidence_id)
        if validation is not None:
            metadata.update(
                {
                    "validation_id": validation.id,
                    "validation_kind": validation.kind,
                    "validation_scope": validation.scope,
                }
            )
        metadata.update(
            {
                "workspace_revision": self.revision,
                "validation_status": self.validation_status(),
            }
        )
        self._records.append(
            EvidenceRecord(
                id=evidence_id,
                tool=call.name,
                arguments=dict(call.arguments),
                ok=result.ok,
                content=result.raw_content if result.raw_content is not None else result.content,
                metadata=dict(metadata),
                revision=self.revision,
            )
        )
        self._derive_context(call, result, evidence_id, metadata)
        return ToolResult(result.ok, result.content, metadata, result.raw_content)

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return next((record for record in self._records if record.id == evidence_id), None)

    def get_entry(self, entry_id: str) -> ContextEntry | None:
        return next((entry for entry in self._entries if entry.id == entry_id), None)

    def index(self, *, max_entries: int = 12) -> str:
        active = [entry for entry in self._entries if not entry.stale]
        stale_count = len(self._entries) - len(active)
        shown = active[-max_entries:]
        lines = [
            "RUNTIME STATE",
            f"task: {self.task or '[not set]'}",
            f"workspace_revision: {self.revision}",
            "changed_files: " + (", ".join(sorted(self.changed_files)) or "none"),
            f"active_entries: {len(active)}; stale_entries: {stale_count}",
            f"evidence_records: {len(self._records)}; showing_active_entries: {len(shown)}",
            (
                "evidence_route: use search_context to locate omitted C/E records, "
                "then read_context to recover exact content"
            ),
            f"validation_policy: {self.validation_policy.prompt_line()}",
            f"validation_status: {self.validation_status()}",
        ]
        for entry in shown:
            lines.append(
                f"- {entry.id} [{entry.kind}] r{entry.revision} {entry.title} "
                f"-> {','.join(entry.evidence_ids)}"
            )
        return "\n".join(lines)

    def working_context(self, *, max_entries: int = 8) -> str:
        active = [entry for entry in self._entries if not entry.stale]
        lines = ["SESSION EVIDENCE ROUTES"]
        for entry in active[-max_entries:]:
            lines.append(
                f"- {entry.id} [{entry.kind}] {entry.summary} "
                f"(revision={entry.revision}; evidence={','.join(entry.evidence_ids)})"
            )
        if len(lines) == 1:
            lines.append("- no verified workspace observations yet")
        return "\n".join(lines)

    def prompt_context(self) -> str:
        sections = []
        if self.long_term_index:
            sections.append(self.long_term_index)
        sections.append(self.index())
        sections.append(self.working_memory_context())
        sections.append(self.working_context())
        return "\n\n".join(sections)

    def propose_memory(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        keywords: list[str],
        evidence_ids: list[str],
        source_path: str | None = None,
    ) -> MemoryCandidate:
        if kind not in {"fact", "sop", "skill"}:
            raise ValueError("memory kind must be fact, sop, or skill")
        if not isinstance(title, str) or not title.strip() or len(title) > 100:
            raise ValueError("memory title must contain 1-100 characters")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("memory content must not be empty")
        content_limit = 20_000 if kind == "skill" else 2_000
        if len(content) > content_limit:
            raise ValueError(f"{kind} memory exceeds {content_limit} characters")
        if not isinstance(keywords, list) or not 1 <= len(keywords) <= 8:
            raise ValueError("memory keywords must contain 1-8 items")
        if not all(
            isinstance(keyword, str) and keyword.strip() and len(keyword) <= 40
            for keyword in keywords
        ):
            raise ValueError("memory keywords must be non-empty and at most 40 characters")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ValueError("long-term memory requires evidence_ids")

        normalized_ids = tuple(
            dict.fromkeys(identifier.strip() for identifier in evidence_ids)
        )
        records: list[EvidenceRecord] = []
        for identifier in normalized_ids:
            record = self.get(identifier)
            if record is None:
                raise ValueError(f"unknown memory evidence: {identifier}")
            if record.tool in ADMINISTRATIVE_TOOLS:
                raise ValueError(f"administrative evidence cannot enter memory: {identifier}")
            if kind in {"fact", "skill"} and not record.ok:
                raise ValueError(f"failed evidence cannot support {kind} memory: {identifier}")
            if kind in {"fact", "skill"} and self._evidence_is_stale(identifier):
                raise ValueError(f"stale evidence cannot support {kind} memory: {identifier}")
            records.append(record)

        if kind in {"sop", "skill"}:
            cited_project_validation = any(
                validation.evidence_id in normalized_ids
                and validation.ok
                and not validation.stale
                and validation.scope == "project"
                for validation in self._validations
            )
            if not cited_project_validation:
                raise ValueError(
                    f"{kind} memory must cite successful current project validation"
                )
        if kind == "skill" and (
            source_path is None or not source_path.casefold().endswith(".py")
        ):
            raise ValueError("skill memory must come from a validated Python source file")
        if self._looks_sensitive(title + "\n" + content):
            raise ValueError("memory appears to contain a credential or secret")

        normalized_keywords = tuple(
            dict.fromkeys(keyword.strip().casefold() for keyword in keywords)
        )
        provenance = tuple(
            {
                "evidence_id": record.id,
                "tool": record.tool,
                "arguments": record.arguments,
                "revision": record.revision,
                "path": record.metadata.get("path"),
                "content_hash": record.metadata.get("content_hash")
                or record.metadata.get("after_hash"),
                "validation_id": record.metadata.get("validation_id"),
                "validation_scope": record.metadata.get("validation_scope"),
                "exit_code": record.metadata.get("exit_code"),
            }
            for record in records
        )
        candidate = MemoryCandidate(
            id=f"MC{len(self._memory_candidates) + 1:04d}",
            kind=kind,
            title=title.strip(),
            content=content.strip() + ("\n" if kind == "skill" else ""),
            keywords=normalized_keywords,
            evidence=provenance,
            source_path=source_path,
        )
        duplicate = next(
            (
                item
                for item in self._memory_candidates
                if item.kind == candidate.kind
                and item.title.casefold() == candidate.title.casefold()
            ),
            None,
        )
        if duplicate is not None:
            self._memory_candidates.remove(duplicate)
        self._memory_candidates.append(candidate)
        return candidate

    def validate_memory_candidate(self, candidate: MemoryCandidate) -> None:
        evidence_ids = tuple(
            str(item.get("evidence_id", "")) for item in candidate.evidence
        )
        records = [self.get(identifier) for identifier in evidence_ids]
        if any(record is None for record in records):
            raise ValueError(f"candidate {candidate.id} lost its source evidence")
        concrete = [record for record in records if record is not None]
        if candidate.kind in {"fact", "skill"} and any(
            not record.ok or self._evidence_is_stale(record.id)
            for record in concrete
        ):
            raise ValueError(
                f"candidate {candidate.id} no longer has current successful evidence"
            )
        if candidate.kind in {"sop", "skill"} and not any(
            validation.evidence_id in evidence_ids
            and validation.ok
            and not validation.stale
            and validation.scope == "project"
            for validation in self._validations
        ):
            raise ValueError(
                f"candidate {candidate.id} no longer has current project validation"
            )

    @staticmethod
    def _looks_sensitive(value: str) -> bool:
        patterns = (
            r"(?i)(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"]?[^\s'\"]{8,}",
            r"(?i)bearer\s+[a-z0-9._~-]{16,}",
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        )
        return any(re.search(pattern, value) for pattern in patterns)

    def update_working_memory(
        self,
        *,
        goal: str,
        items: list[dict[str, Any]],
        next_action: str,
    ) -> str:
        """Replace the decision-relevant checkpoint with evidence-grounded items.

        The model chooses what is decision-relevant, while the runtime verifies
        that every retained claim points to real, current tool evidence and
        derives conservative file dependencies from that evidence.
        """
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("working-memory goal must be a non-empty string")
        if len(goal) > 360:
            raise ValueError("working-memory goal is too long")
        if not isinstance(next_action, str) or not next_action.strip():
            raise ValueError("working-memory next_action must be a non-empty string")
        if len(next_action) > 360:
            raise ValueError("working-memory next_action is too long")
        if not isinstance(items, list):
            raise ValueError("working-memory items must be an array")
        if not items:
            raise ValueError("working memory requires at least one evidence-grounded item")
        if len(items) > 16:
            raise ValueError("working memory accepts at most 16 items")

        allowed_kinds = {"finding", "constraint", "hypothesis", "progress", "risk"}
        normalized: list[WorkingMemoryItem] = []
        seen: set[tuple[str, str]] = set()
        next_memory_id = self._next_memory_id
        for position, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"working-memory item {position} must be an object")
            unknown = set(item) - {"kind", "content", "evidence_ids"}
            if unknown:
                raise ValueError(
                    f"working-memory item {position} has unknown fields: "
                    + ", ".join(sorted(unknown))
                )
            kind = item.get("kind")
            content = item.get("content")
            evidence_ids = item.get("evidence_ids")
            if kind not in allowed_kinds:
                raise ValueError(
                    f"working-memory item {position} kind must be finding, constraint, "
                    "hypothesis, progress, or risk"
                )
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f"working-memory item {position} requires content")
            content = content.strip()
            if len(content) > 360:
                raise ValueError(f"working-memory item {position} is too long")
            if not isinstance(evidence_ids, list) or not evidence_ids or not all(
                isinstance(identifier, str) and identifier.strip()
                for identifier in evidence_ids
            ):
                raise ValueError(
                    f"working-memory item {position} requires evidence_ids"
                )

            normalized_evidence_ids = tuple(
                dict.fromkeys(identifier.strip() for identifier in evidence_ids)
            )
            records: list[EvidenceRecord] = []
            for identifier in normalized_evidence_ids:
                record = self.get(identifier.strip())
                if record is None:
                    raise ValueError(
                        f"working-memory item {position} references unknown evidence: "
                        f"{identifier}"
                    )
                if record.tool in ADMINISTRATIVE_TOOLS:
                    raise ValueError(
                        f"working-memory item {position} cites administrative evidence: "
                        f"{identifier}"
                    )
                if self._evidence_is_stale(record.id):
                    raise ValueError(
                        f"working-memory item {position} cites stale evidence: {identifier}"
                    )
                records.append(record)

            key = (kind, content.casefold())
            if key in seen:
                raise ValueError(f"duplicate working-memory item {position}")
            seen.add(key)
            paths = self._evidence_paths(records)
            normalized.append(
                WorkingMemoryItem(
                    id=f"M{next_memory_id:04d}",
                    kind=kind,
                    content=content,
                    evidence_ids=normalized_evidence_ids,
                    paths=paths,
                    revision=self.revision,
                )
            )
            next_memory_id += 1

        self.working_goal = goal.strip()
        self.next_action = next_action.strip()
        self._working_memory = normalized
        self._next_memory_id = next_memory_id
        self.checkpoint_revision += 1
        self.checkpoint_workspace_revision = self.revision
        self.checkpoint_evidence_count = self._substantive_evidence_count()
        return self.working_memory_context()

    def working_memory_context(self) -> str:
        active = [item for item in self._working_memory if not item.stale]
        stale_count = len(self._working_memory) - len(active)
        lines = [
            f"WORKING MEMORY CHECKPOINT v{self.checkpoint_revision}",
            f"goal: {self.working_goal or self.task or '[not set]'}",
        ]
        lines.append(
            f"checkpoint_state: {self.checkpoint_state()}; "
            f"workspace_revision: {self.checkpoint_workspace_revision}"
        )
        if active:
            for item in active:
                dependencies = ",".join(item.paths) or "workspace-state"
                lines.append(
                    f"- {item.id} [{item.kind}] {item.content} "
                    f"(evidence={','.join(item.evidence_ids)}; depends_on={dependencies})"
                )
        else:
            lines.append("- no evidence-grounded findings recorded yet")
        if stale_count:
            lines.append(
                f"stale_items: {stale_count}; use source evidence or inspect current files "
                "before restating them"
            )
        lines.append(f"next_action: {self.next_action}")
        return "\n".join(lines)

    def checkpoint_state(self) -> str:
        if not self.checkpoint_revision:
            return "uninitialized"
        if (
            self.checkpoint_workspace_revision != self.revision
            or self.checkpoint_evidence_count != self._substantive_evidence_count()
        ):
            return "needs_refresh"
        return "current"

    def validation_status(self) -> str:
        if not self.changed_files:
            return "not_required"
        if self.validation_policy.warning:
            return "policy_invalid"
        current = [record for record in self._validations if not record.stale]
        if not current:
            return "missing"
        latest_by_command = {
            normalized_validation_argv(record.argv): record for record in current
        }
        if any(not record.ok for record in latest_by_command.values()):
            return "failed"
        if self.validation_policy.required_commands:
            required = [
                latest_by_command.get(normalized_validation_argv(command))
                for command in self.validation_policy.required_commands
            ]
            if all(record is not None and record.ok for record in required):
                return "passed"
            if any(record.ok for record in current):
                return "required_missing"
            return "missing"
        if any(record.ok and record.scope == "project" for record in latest_by_command.values()):
            return "passed"
        if any(record.ok for record in latest_by_command.values()):
            return "focused_only"
        return "missing"

    def completion_feedback(self) -> str | None:
        workspace_records = [
            record
            for record in self._records
            if record.tool not in ADMINISTRATIVE_TOOLS
        ]
        if not workspace_records:
            return (
                "暂不接受完成声明：尚未取得任何工作区证据。"
                "请先检查相关文件或项目状态，再报告任务完成。"
            )
        if self.checkpoint_revision and self.checkpoint_state() != "current":
            return (
                "暂不接受完成声明：working checkpoint 之后又产生了新的实质证据，"
                "其中的关键认识或下一步可能已经过时。请基于当前 E 证据刷新检查点，"
                "再报告完成。"
            )
        status = self.validation_status()
        if status in {"not_required", "passed"}:
            return None
        if status == "failed":
            return (
                "暂不接受完成声明：当前代码仍有已记录的测试或检查失败。"
                "请根据执行输出修正实现，然后重新运行验证。"
            )
        if status == "policy_invalid":
            return (
                "暂不接受完成声明：项目存在 .proofcode.json，但验证策略无效。"
                f"请修正配置后再验证。原因：{self.validation_policy.warning}"
            )
        if status == "focused_only":
            return (
                "暂不接受完成声明：focused validation 已通过，但当前工作区 revision "
                "还没有成功的项目级 baseline validation。请运行项目的完整测试、"
                "构建、类型检查、lint 或语法检查。"
            )
        if status == "required_missing":
            required = "；".join(
                " ".join(command)
                for command in self.validation_policy.required_commands
            )
            return (
                "暂不接受完成声明：已有检查通过，但尚未取得项目验证策略要求的"
                f"当前 revision 证据。请运行：{required}"
            )
        return (
            "暂不接受完成声明：工作区已经变化，但还没有成功的项目级 validation。"
            "请运行项目的完整测试、构建、类型检查、lint 或语法检查；"
            "无关的成功命令不能作为完成证据。"
        )

    def describe(self, identifier: str) -> str | None:
        entry = self.get_entry(identifier)
        if entry is not None:
            return json.dumps(
                {
                    "id": entry.id,
                    "kind": entry.kind,
                    "title": entry.title,
                    "summary": entry.summary,
                    "evidence_ids": entry.evidence_ids,
                    "revision": entry.revision,
                    "paths": entry.paths,
                    "stale": entry.stale,
                },
                ensure_ascii=False,
            )
        record = self.get(identifier)
        if record is None:
            return None
        return json.dumps(
            {
                "id": record.id,
                "tool": record.tool,
                "arguments": record.arguments,
                "ok": record.ok,
                "content": record.content,
                "metadata": record.metadata,
                "revision": record.revision,
            },
            ensure_ascii=False,
        )

    def search_context(
        self,
        query: str,
        *,
        include_stale: bool = False,
        max_results: int = 20,
    ) -> tuple[dict[str, Any], ...]:
        """Search the compact catalog and raw evidence without injecting it all.

        Offsets refer to the exact serialized value returned by ``describe`` so
        callers can pass them directly to ``read_context``.
        """
        needle = query.strip().casefold()
        if not needle:
            raise ValueError("query must not be empty")
        if max_results < 1:
            raise ValueError("max_results must be positive")

        candidates: list[tuple[str, str, int, bool]] = []
        for entry in self._entries:
            candidates.append((entry.id, entry.kind, entry.revision, entry.stale))
        for record in self._records:
            stale = self._evidence_is_stale(record.id)
            candidates.append(
                (record.id, f"evidence:{record.tool}", record.revision, stale)
            )

        matches: list[dict[str, Any]] = []
        for identifier, kind, revision, stale in candidates:
            if stale and not include_stale:
                continue
            serialized = self.describe(identifier)
            if serialized is None:
                continue
            position = serialized.casefold().find(needle)
            if position < 0:
                continue
            offset = max(0, position - 100)
            end = min(len(serialized), position + len(query) + 140)
            snippet = serialized[offset:end].replace("\n", " ")
            matches.append(
                {
                    "id": identifier,
                    "kind": kind,
                    "revision": revision,
                    "stale": stale,
                    "offset": offset,
                    "match_offset": position,
                    "snippet": snippet,
                }
            )
            if len(matches) >= max_results:
                break
        return tuple(matches)

    def _evidence_is_stale(self, evidence_id: str) -> bool:
        linked_entries = [
            entry for entry in self._entries if evidence_id in entry.evidence_ids
        ]
        if linked_entries:
            return all(entry.stale for entry in linked_entries)
        record = self.get(evidence_id)
        return record is not None and record.revision < self.revision

    def _substantive_evidence_count(self) -> int:
        return sum(
            record.tool not in ADMINISTRATIVE_TOOLS for record in self._records
        )

    @staticmethod
    def _evidence_paths(records: list[EvidenceRecord]) -> tuple[str, ...]:
        paths: set[str] = set()
        for record in records:
            record_paths: set[str] = set()
            path = record.metadata.get("path")
            if isinstance(path, str):
                record_paths.add(path)
            argument_path = record.arguments.get("path")
            if not record_paths and isinstance(argument_path, str) and record.tool in {
                "list_files",
                "search_text",
                "read_file",
                "replace_text",
                "create_file",
                "apply_patch",
                "show_diff",
            }:
                record_paths.add(argument_path.replace("\\", "/"))
            workspace_changes = record.metadata.get("workspace_changes", [])
            if isinstance(workspace_changes, list):
                record_paths.update(
                    changed_path
                    for changed_path in workspace_changes
                    if isinstance(changed_path, str)
                )
            # A command result describes behavior of the workspace revision as
            # a whole unless the runtime can derive a narrower dependency set.
            if record.tool == "run_command":
                record_paths.add(".")
            if not record.ok and not record_paths:
                record_paths.add(".")
            paths.update(record_paths)
        return tuple(sorted(paths))

    def _add_entry(
        self,
        *,
        kind: str,
        title: str,
        summary: str,
        evidence_id: str,
        paths: tuple[str, ...] = (),
    ) -> None:
        self._entries.append(
            ContextEntry(
                id=f"C{len(self._entries) + 1:04d}",
                kind=kind,
                title=title,
                summary=summary,
                evidence_ids=(evidence_id,),
                revision=self.revision,
                paths=paths,
            )
        )

    def _derive_context(
        self,
        call: ToolCall,
        result: ToolResult,
        evidence_id: str,
        metadata: dict[str, Any],
    ) -> None:
        path = metadata.get("path")
        paths = (path,) if isinstance(path, str) else ()
        if call.name == "read_file" and result.ok and paths:
            line_range = f"lines {metadata.get('start')}-{metadata.get('end')}"
            digest = str(metadata.get("content_hash", ""))[:12]
            self._add_entry(
                kind="file",
                title=path,
                summary=f"Read {path} {line_range}; hash={digest}",
                evidence_id=evidence_id,
                paths=paths,
            )
        elif call.name == "list_files" and result.ok and paths:
            self._add_entry(
                kind="listing",
                title=path,
                summary=f"Listed {path}; entries={metadata.get('entries')}",
                evidence_id=evidence_id,
                paths=paths,
            )
        elif call.name == "search_text" and result.ok and paths:
            self._add_entry(
                kind="search",
                title=str(metadata.get("query", "")),
                summary=(
                    f"Searched {path} for {metadata.get('query')!r}; "
                    f"matches={metadata.get('matches')}"
                ),
                evidence_id=evidence_id,
                paths=paths,
            )
        elif metadata.get("changed") and result.ok and paths:
            digest = str(metadata.get("after_hash", ""))[:12]
            self._add_entry(
                kind="change",
                title=path,
                summary=f"Changed {path}; current_hash={digest}",
                evidence_id=evidence_id,
                paths=paths,
            )
        elif call.name == "run_command":
            argv = call.arguments.get("argv", [])
            status = "passed" if result.ok else "failed"
            validation_kind = classify_validation(argv) if isinstance(argv, list) else None
            kind = "validation" if validation_kind else "command"
            validation_id = metadata.get("validation_id")
            self._add_entry(
                kind=kind,
                title=" ".join(str(item) for item in argv),
                summary=(
                    f"{validation_id or 'unclassified'} "
                    f"{validation_kind or 'command'} {status}; "
                    f"exit_code={metadata.get('exit_code')}"
                ),
                evidence_id=evidence_id,
            )
        elif not result.ok:
            self._add_entry(
                kind="error",
                title=call.name,
                summary=f"{call.name} failed: {result.content[:240]}",
                evidence_id=evidence_id,
                paths=paths,
            )

    def _invalidate_for_change(self, path: str) -> None:
        for entry in self._entries:
            covers_changed_path = any(
                scope == "." or path == scope or path.startswith(scope.rstrip("/") + "/")
                for scope in entry.paths
            )
            if entry.kind in {"command", "validation"} or covers_changed_path:
                entry.stale = True
        for validation in self._validations:
            validation.stale = True
        for item in self._working_memory:
            depends_on_change = any(
                scope == "." or path == scope or path.startswith(scope.rstrip("/") + "/")
                for scope in item.paths
            )
            if depends_on_change or any(
                self._evidence_is_stale(evidence_id)
                for evidence_id in item.evidence_ids
            ):
                item.stale = True

    def _record_validation(
        self,
        call: ToolCall,
        result: ToolResult,
        evidence_id: str,
    ) -> ValidationRecord | None:
        if call.name != "run_command":
            return None
        argv = call.arguments.get("argv")
        if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
            return None
        kind = classify_validation(argv)
        if kind is None:
            return None
        record = ValidationRecord(
            id=f"V{len(self._validations) + 1:04d}",
            argv=tuple(argv),
            kind=kind,
            ok=result.ok,
            evidence_id=evidence_id,
            revision=self.revision,
            scope=validation_scope(argv) or "focused",
        )
        self._validations.append(record)
        return record
