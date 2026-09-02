from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class MemoryCandidate:
    id: str
    kind: str
    title: str
    content: str
    keywords: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...]
    source_path: str | None = None


class LongTermMemoryStore:
    """Project-local, persistent L1/L2/L3 memory.

    L1 is a compact generated index. L2 stores verified project facts. L3
    stores reusable SOPs and exact copies of validated Python skills. Raw L4
    sessions remain in ``.proofcode/runs`` and are managed by the trajectory
    recorder rather than this store.
    """

    def __init__(self, workspace: Path) -> None:
        self.root = workspace.resolve() / ".proofcode" / "memory"
        self.index_path = self.root / "l1_index.json"

    def index_prompt(self, *, max_entries: int = 24) -> str:
        entries = [entry for entry in self._entries() if entry.get("active", True)]
        entries.sort(
            key=lambda item: (
                int(item.get("use_count", 0)),
                str(item.get("created_at", "")),
            ),
            reverse=True,
        )
        shown = entries[:max_entries]
        lines = [
            "LONG-TERM L1 MEMORY INDEX",
            f"available_entries: {len(entries)}; showing: {len(shown)}",
            "routing: call read_memory with an ID; use search_memory when no pointer matches",
        ]
        for entry in shown:
            keywords = ",".join(entry.get("keywords", []))
            lines.append(
                f"- {entry['id']} [{entry['kind']}] {entry['title']} "
                f"keywords={keywords}"
            )
        if not shown:
            lines.append("- no consolidated cross-task memory yet")
        return "\n".join(lines)

    def search(self, query: str, *, max_results: int = 10) -> tuple[dict[str, Any], ...]:
        needle = query.strip().casefold()
        if not needle:
            raise ValueError("memory query must not be empty")
        matches: list[dict[str, Any]] = []
        for entry in self._entries():
            if not entry.get("active", True):
                continue
            content = self._read_entry_content(entry)
            haystack = " ".join(
                [
                    str(entry.get("title", "")),
                    " ".join(entry.get("keywords", [])),
                    content,
                ]
            ).casefold()
            if needle not in haystack:
                continue
            matches.append(
                {
                    "id": entry["id"],
                    "kind": entry["kind"],
                    "title": entry["title"],
                    "keywords": entry.get("keywords", []),
                }
            )
            if len(matches) >= max_results:
                break
        return tuple(matches)

    def read(self, memory_id: str) -> str | None:
        payload = self._load_index()
        entry = next(
            (
                item
                for item in payload["entries"]
                if item.get("id") == memory_id and item.get("active", True)
            ),
            None,
        )
        if entry is None:
            return None
        content = self._read_entry_content(entry)
        rendered = json.dumps(
            {
                "id": entry["id"],
                "kind": entry["kind"],
                "title": entry["title"],
                "keywords": entry.get("keywords", []),
                "content": content,
                "workspace_path": ".proofcode/memory/" + str(entry.get("path", "")),
                "execution_policy": (
                    "invoke through run_command with normal approval"
                    if entry.get("kind") == "skill"
                    else "not executable"
                ),
                "provenance": entry.get("provenance", []),
                "created_at": entry.get("created_at"),
                "source_run_id": entry.get("source_run_id"),
                "supersedes": entry.get("supersedes"),
            },
            ensure_ascii=False,
        )
        entry["use_count"] = int(entry.get("use_count", 0)) + 1
        self._write_index(payload)
        return rendered

    def commit(
        self,
        candidates: tuple[MemoryCandidate, ...],
        *,
        run_id: str,
    ) -> tuple[str, ...]:
        if not candidates:
            return ()
        payload = self._load_index()
        entries = payload["entries"]
        committed: list[str] = []
        for candidate in candidates:
            digest = hashlib.sha256(
                f"{candidate.kind}\0{candidate.title}\0{candidate.content}".encode("utf-8")
            ).hexdigest()
            duplicate = next(
                (
                    entry
                    for entry in entries
                    if entry.get("active", True)
                    and entry.get("content_hash") == digest
                ),
                None,
            )
            if duplicate is not None:
                committed.append(str(duplicate["id"]))
                continue

            previous = next(
                (
                    entry
                    for entry in reversed(entries)
                    if entry.get("active", True)
                    and entry.get("kind") == candidate.kind
                    and str(entry.get("title", "")).casefold()
                    == candidate.title.casefold()
                ),
                None,
            )
            if previous is not None:
                previous["active"] = False

            memory_id = self._allocate_id(payload, candidate.kind)
            relative_path = self._write_candidate(memory_id, candidate)
            entry = {
                "id": memory_id,
                "kind": candidate.kind,
                "title": candidate.title,
                "keywords": list(candidate.keywords),
                "path": relative_path,
                "content_hash": digest,
                "created_at": datetime.now(UTC).isoformat(),
                "source_run_id": run_id,
                "source_candidate_id": candidate.id,
                "provenance": list(candidate.evidence),
                "supersedes": previous.get("id") if previous else None,
                "active": True,
                "use_count": 0,
            }
            entries.append(entry)
            committed.append(memory_id)
        self._write_index(payload)
        return tuple(committed)

    def _entries(self) -> list[dict[str, Any]]:
        return list(self._load_index()["entries"])

    def _load_index(self) -> dict[str, Any]:
        empty = {
            "version": 1,
            "next_ids": {"fact": 1, "sop": 1, "skill": 1},
            "entries": [],
        }
        if not self.index_path.is_file():
            return empty
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
                raise OSError("invalid long-term memory index structure")
            payload.setdefault("version", 1)
            payload.setdefault("next_ids", empty["next_ids"].copy())
            return payload
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise OSError(f"cannot read long-term memory index: {exc}") from exc

    def _write_index(self, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.index_path)

    def _allocate_id(self, payload: dict[str, Any], kind: str) -> str:
        prefixes = {"fact": "F", "sop": "S", "skill": "K"}
        number = int(payload["next_ids"].get(kind, 1))
        payload["next_ids"][kind] = number + 1
        return f"{prefixes[kind]}{number:04d}"

    def _write_candidate(self, memory_id: str, candidate: MemoryCandidate) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", candidate.title).strip("-").lower()
        slug = (slug or "memory")[:60]
        if candidate.kind == "fact":
            directory = self.root / "l2_facts"
            suffix = ".md"
        elif candidate.kind == "sop":
            directory = self.root / "l3_sops"
            suffix = ".md"
        else:
            directory = self.root / "l3_skills"
            suffix = ".py"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{memory_id}_{slug}{suffix}"
        if candidate.kind == "skill":
            rendered = candidate.content
        else:
            rendered = f"# {candidate.title}\n\n{candidate.content.strip()}\n"
        path.write_text(rendered, encoding="utf-8", newline="\n")
        return path.relative_to(self.root).as_posix()

    def _read_entry_content(self, entry: dict[str, Any]) -> str:
        relative = entry.get("path")
        if not isinstance(relative, str):
            return "[memory content unavailable]"
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return "[invalid memory path]"
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return "[memory content unavailable]"
