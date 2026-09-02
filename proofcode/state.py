from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from proofcode.types import ToolCall, ToolResult
from proofcode.validation import classify_validation, validation_scope


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


class WorkspaceState:
    def __init__(self, task: str = "") -> None:
        self.task = task.strip()
        self.revision = 0
        self.changed_files: set[str] = set()
        self._records: list[EvidenceRecord] = []
        self._entries: list[ContextEntry] = []
        self._validations: list[ValidationRecord] = []

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    @property
    def entries(self) -> tuple[ContextEntry, ...]:
        return tuple(self._entries)

    @property
    def validations(self) -> tuple[ValidationRecord, ...]:
        return tuple(self._validations)

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
        return ToolResult(result.ok, result.content, metadata)

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return next((record for record in self._records if record.id == evidence_id), None)

    def get_entry(self, entry_id: str) -> ContextEntry | None:
        return next((entry for entry in self._entries if entry.id == entry_id), None)

    def index(self, *, max_entries: int = 12) -> str:
        active = [entry for entry in self._entries if not entry.stale]
        stale_count = len(self._entries) - len(active)
        lines = [
            "L1 CONTEXT INDEX",
            f"task: {self.task or '[not set]'}",
            f"workspace_revision: {self.revision}",
            "changed_files: " + (", ".join(sorted(self.changed_files)) or "none"),
            f"active_entries: {len(active)}; stale_entries: {stale_count}",
            f"validation_status: {self.validation_status()}",
        ]
        for entry in active[-max_entries:]:
            lines.append(
                f"- {entry.id} [{entry.kind}] r{entry.revision} {entry.title} "
                f"-> {','.join(entry.evidence_ids)}"
            )
        return "\n".join(lines)

    def working_context(self, *, max_entries: int = 8) -> str:
        active = [entry for entry in self._entries if not entry.stale]
        lines = ["L2 WORKING CONTEXT"]
        for entry in active[-max_entries:]:
            lines.append(
                f"- {entry.id} [{entry.kind}] {entry.summary} "
                f"(revision={entry.revision}; evidence={','.join(entry.evidence_ids)})"
            )
        if len(lines) == 1:
            lines.append("- no verified workspace observations yet")
        return "\n".join(lines)

    def prompt_context(self) -> str:
        return self.index() + "\n\n" + self.working_context()

    def validation_status(self) -> str:
        if not self.changed_files:
            return "not_required"
        current = [record for record in self._validations if not record.stale]
        if not current:
            return "missing"
        latest_by_command = {record.argv: record for record in current}
        if any(not record.ok for record in latest_by_command.values()):
            return "failed"
        if any(record.ok and record.scope == "project" for record in latest_by_command.values()):
            return "passed"
        if any(record.ok for record in latest_by_command.values()):
            return "focused_only"
        return "missing"

    def completion_feedback(self) -> str | None:
        if not self._records:
            return (
                "暂不接受完成声明：尚未取得任何工作区证据。"
                "请先检查相关文件或项目状态，再报告任务完成。"
            )
        status = self.validation_status()
        if status in {"not_required", "passed"}:
            return None
        if status == "failed":
            return (
                "暂不接受完成声明：当前代码仍有已记录的测试或检查失败。"
                "请根据执行输出修正实现，然后重新运行验证。"
            )
        if status == "focused_only":
            return (
                "暂不接受完成声明：focused validation 已通过，但当前工作区 revision "
                "还没有成功的项目级 baseline validation。请运行项目的完整测试、"
                "构建、类型检查、lint 或语法检查。"
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
