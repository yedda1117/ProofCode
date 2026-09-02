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
    """Two-scope persistent memory for coding work.

    Project-specific L2 facts stay beside the repository. Reusable L3 SOPs
    and executable skills live in the agent home so they can transfer across
    workspaces. L1 is assembled from both indexes; L4 remains project-local.
    """

    def __init__(self, workspace: Path, agent_home: Path | None = None) -> None:
        self.workspace = workspace.resolve()
        self.root = self.workspace / ".proofcode" / "memory"
        self.index_path = self.root / "l1_index.json"
        home = (agent_home or (Path.home() / ".proofcode")).expanduser().resolve()
        self.global_root = home / "memory"
        self.global_index_path = self.global_root / "l1_index.json"

    def index_prompt(self, *, max_entries: int = 24) -> str:
        entries = [
            (scope, entry)
            for scope, entry in self._scoped_entries()
            if entry.get("active", True)
        ]
        entries.sort(
            key=lambda item: (
                int(item[1].get("use_count", 0)),
                str(item[1].get("created_at", "")),
            ),
            reverse=True,
        )
        shown = entries[:max_entries]
        lines = [
            "LONG-TERM L1 MEMORY INDEX",
            f"available_entries: {len(entries)}; showing: {len(shown)}",
            "routing: call read_memory with an ID; use search_memory when no pointer matches",
        ]
        for scope, entry in shown:
            keywords = ",".join(entry.get("keywords", []))
            lines.append(
                f"- {scope}:{entry['id']} [{entry['kind']}] {entry['title']} "
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
        for scope, entry in self._scoped_entries():
            if not entry.get("active", True):
                continue
            content = self._read_entry_content(entry, scope)
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
                    "id": f"{scope}:{entry['id']}",
                    "scope": scope,
                    "kind": entry["kind"],
                    "title": entry["title"],
                    "keywords": entry.get("keywords", []),
                }
            )
            if len(matches) >= max_results:
                break
        return tuple(matches)

    def read(self, memory_id: str) -> str | None:
        requested_scope, separator, bare_id = memory_id.partition(":")
        scopes = (requested_scope,) if separator and requested_scope in {"project", "global"} else ("global", "project")
        target_id = bare_id if separator else memory_id
        located = None
        for scope in scopes:
            payload = self._load_index(scope)
            entry = next((item for item in payload["entries"] if item.get("id") == target_id and item.get("active", True)), None)
            if entry is not None:
                located = (scope, payload, entry)
                break
        if located is None:
            return None
        scope, payload, entry = located
        content = self._read_entry_content(entry, scope)
        rendered = json.dumps(
            {
                "id": f"{scope}:{entry['id']}",
                "scope": scope,
                "kind": entry["kind"],
                "title": entry["title"],
                "keywords": entry.get("keywords", []),
                "content": content,
                "storage_path": str(self._root_for_scope(scope) / str(entry.get("path", ""))),
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
        self._write_index(payload, scope)
        return rendered

    def commit(
        self,
        candidates: tuple[MemoryCandidate, ...],
        *,
        run_id: str,
    ) -> tuple[str, ...]:
        if not candidates:
            return ()
        committed: list[str] = []
        for candidate in candidates:
            scope = "project" if candidate.kind == "fact" else "global"
            payload = self._load_index(scope)
            entries = payload["entries"]
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
                committed.append(f"{scope}:{duplicate['id']}")
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
            relative_path = self._write_candidate(memory_id, candidate, scope)
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
                "scope": scope,
                "source_workspace": str(self.workspace),
            }
            entries.append(entry)
            committed.append(f"{scope}:{memory_id}")
            self._write_index(payload, scope)
        return tuple(committed)

    def _scoped_entries(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            *[("project", item) for item in self._load_index("project")["entries"]],
            *[("global", item) for item in self._load_index("global")["entries"]],
        ]

    def _load_index(self, scope: str = "project") -> dict[str, Any]:
        empty = {
            "version": 1,
            "next_ids": {"fact": 1, "sop": 1, "skill": 1},
            "entries": [],
        }
        index_path = self._index_for_scope(scope)
        if not index_path.is_file():
            return empty
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
                raise OSError("invalid long-term memory index structure")
            payload.setdefault("version", 1)
            payload.setdefault("next_ids", empty["next_ids"].copy())
            return payload
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise OSError(f"cannot read long-term memory index: {exc}") from exc

    def _write_index(self, payload: dict[str, Any], scope: str = "project") -> None:
        root = self._root_for_scope(scope)
        index_path = self._index_for_scope(scope)
        root.mkdir(parents=True, exist_ok=True)
        temporary = index_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(index_path)

    def _allocate_id(self, payload: dict[str, Any], kind: str) -> str:
        prefixes = {"fact": "F", "sop": "S", "skill": "K"}
        number = int(payload["next_ids"].get(kind, 1))
        payload["next_ids"][kind] = number + 1
        return f"{prefixes[kind]}{number:04d}"

    def _write_candidate(self, memory_id: str, candidate: MemoryCandidate, scope: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", candidate.title).strip("-").lower()
        slug = (slug or "memory")[:60]
        if candidate.kind == "fact":
            directory = self._root_for_scope(scope) / "l2_facts"
            suffix = ".md"
        elif candidate.kind == "sop":
            directory = self._root_for_scope(scope) / "l3_sops"
            suffix = ".md"
        else:
            directory = self._root_for_scope(scope) / "l3_skills"
            suffix = ".py"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{memory_id}_{slug}{suffix}"
        if candidate.kind == "skill":
            rendered = candidate.content
        else:
            rendered = f"# {candidate.title}\n\n{candidate.content.strip()}\n"
        path.write_text(rendered, encoding="utf-8", newline="\n")
        return path.relative_to(self._root_for_scope(scope)).as_posix()

    def _read_entry_content(self, entry: dict[str, Any], scope: str) -> str:
        relative = entry.get("path")
        if not isinstance(relative, str):
            return "[memory content unavailable]"
        root = self._root_for_scope(scope)
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            return "[invalid memory path]"
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return "[memory content unavailable]"

    def _root_for_scope(self, scope: str) -> Path:
        return self.global_root if scope == "global" else self.root

    def _index_for_scope(self, scope: str) -> Path:
        return self.global_index_path if scope == "global" else self.index_path
