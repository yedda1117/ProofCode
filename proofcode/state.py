from __future__ import annotations

from dataclasses import dataclass
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


class WorkspaceState:
    def __init__(self) -> None:
        self.revision = 0
        self.changed_files: set[str] = set()
        self._records: list[EvidenceRecord] = []

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    def record(self, call: ToolCall, result: ToolResult) -> ToolResult:
        metadata = dict(result.metadata)
        path = metadata.get("path")
        if result.ok and metadata.get("changed") and isinstance(path, str):
            self.revision += 1
            self.changed_files.add(path)

        evidence_id = f"E{len(self._records) + 1:04d}"
        metadata.update({"evidence_id": evidence_id, "revision": self.revision})
        self._records.append(
            EvidenceRecord(
                id=evidence_id,
                tool=call.name,
                arguments=dict(call.arguments),
                ok=result.ok,
                content=result.content,
                metadata=dict(metadata),
                revision=self.revision,
            )
        )
        return ToolResult(result.ok, result.content, metadata)

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        return next((record for record in self._records if record.id == evidence_id), None)
