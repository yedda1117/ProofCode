from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from proofcode.types import ToolCall, ToolResult


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


class WorkspaceState:
    def __init__(self, task: str = "") -> None:
        self.task = task.strip()
        self.revision = 0
        self.changed_files: set[str] = set()
        self._records: list[EvidenceRecord] = []
        self._entries: list[ContextEntry] = []

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    @property
    def entries(self) -> tuple[ContextEntry, ...]:
        return tuple(self._entries)

    def record(self, call: ToolCall, result: ToolResult) -> ToolResult:
        metadata = dict(result.metadata)
        path = metadata.get("path")
        if result.ok and metadata.get("changed") and isinstance(path, str):
            self.revision += 1
            self.changed_files.add(path)
            self._invalidate_for_change(path)

        evidence_id = f"E{len(self._records) + 1:04d}"
        metadata.update({"evidence_id": evidence_id, "revision": self.revision})
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
            self._add_entry(
                kind="command",
                title=" ".join(str(item) for item in argv),
                summary=f"Command {status}; exit_code={metadata.get('exit_code')}",
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
            if entry.kind == "command" or covers_changed_path:
                entry.stale = True
