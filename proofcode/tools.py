from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from proofcode.errors import ApprovalDenied, PathViolation, ToolError
from proofcode.patching import apply_unified_hunks
from proofcode.state import WorkspaceState
from proofcode.types import ToolResult


JsonSchema = dict[str, Any]
ApprovalCallback = Callable[[str, dict[str, Any]], bool]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: JsonSchema
    handler: Callable[[dict[str, Any]], ToolResult]
    requires_approval: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, value: str, *, must_exist: bool = False) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ToolError("path must be a non-empty string")
        candidate = (self.root / value).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PathViolation(f"path escapes workspace: {value}") from exc
        if must_exist and not candidate.exists():
            raise ToolError(f"path does not exist: {value}")
        return candidate

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix() or "."


class ToolRegistry:
    def __init__(
        self,
        workspace: Path,
        *,
        output_limit: int = 20_000,
        command_timeout: int = 120,
        approve: ApprovalCallback | None = None,
    ) -> None:
        self.workspace = Workspace(workspace)
        self.output_limit = output_limit
        self.command_timeout = command_timeout
        self.approve = approve or (lambda _name, _args: False)
        self.state: WorkspaceState | None = None
        self._tools = self._build_tools()

    def attach_state(self, state: WorkspaceState) -> None:
        self.state = state

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, f"unknown tool: {name}", {"category": "unknown_tool"})
        if not isinstance(arguments, dict):
            return ToolResult(False, "tool arguments must be an object", {"category": "invalid_arguments"})
        try:
            self._validate_required(tool.parameters, arguments)
            if tool.requires_approval and not self.approve(name, arguments):
                raise ApprovalDenied(f"approval denied for {name}")
            result = tool.handler(arguments)
            content, truncated = self._truncate(result.content)
            metadata = dict(result.metadata)
            if truncated:
                metadata["truncated"] = True
            return ToolResult(
                result.ok,
                content,
                metadata,
                result.content if truncated else result.raw_content,
            )
        except ApprovalDenied as exc:
            return ToolResult(False, str(exc), {"category": "approval_denied"})
        except PathViolation as exc:
            return ToolResult(False, str(exc), {"category": "path_violation"})
        except (ToolError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
            return ToolResult(False, str(exc), {"category": "tool_error"})

    def _build_tools(self) -> dict[str, Tool]:
        tools = [
            Tool(
                "list_files",
                "List files under a workspace directory. Hidden VCS metadata is excluded.",
                self._object_schema(
                    {"path": {"type": "string"}, "max_entries": {"type": "integer"}},
                    ["path"],
                ),
                self._list_files,
            ),
            Tool(
                "search_text",
                "Search UTF-8 text files and return matching lines with file paths and line numbers.",
                self._object_schema(
                    {
                        "query": {"type": "string"},
                        "path": {"type": "string"},
                        "glob": {"type": "string"},
                        "max_results": {"type": "integer"},
                    },
                    ["query", "path"],
                ),
                self._search_text,
            ),
            Tool(
                "read_file",
                "Read a UTF-8 text file with one-based line numbers.",
                self._object_schema(
                    {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    ["path"],
                ),
                self._read_file,
            ),
            Tool(
                "replace_text",
                "Replace one unique text block in an existing UTF-8 file. The old text must occur exactly once.",
                self._object_schema(
                    {
                        "path": {"type": "string"},
                        "old_text": {"type": "string"},
                        "new_text": {"type": "string"},
                    },
                    ["path", "old_text", "new_text"],
                ),
                self._replace_text,
                requires_approval=True,
            ),
            Tool(
                "create_file",
                "Create a new UTF-8 file. Fails when the target already exists.",
                self._object_schema(
                    {"path": {"type": "string"}, "content": {"type": "string"}},
                    ["path", "content"],
                ),
                self._create_file,
                requires_approval=True,
            ),
            Tool(
                "apply_patch",
                "Apply standard unified-diff hunks to one existing UTF-8 file. Pass the target path separately and omit file headers.",
                self._object_schema(
                    {"path": {"type": "string"}, "patch": {"type": "string"}},
                    ["path", "patch"],
                ),
                self._apply_patch,
                requires_approval=True,
            ),
            Tool(
                "show_diff",
                "Show uncommitted Git changes for the workspace or one path without modifying files.",
                self._object_schema({"path": {"type": "string"}}, []),
                self._show_diff,
            ),
            Tool(
                "run_command",
                "Run a local process without a shell. Pass the executable and every argument as separate argv items.",
                self._object_schema(
                    {
                        "argv": {"type": "array", "items": {"type": "string"}},
                        "cwd": {"type": "string"},
                        "timeout": {"type": "integer"},
                    },
                    ["argv"],
                ),
                self._run_command,
                requires_approval=True,
            ),
            Tool(
                "list_context",
                "Show the compact context index and current working context.",
                self._object_schema({}, []),
                self._list_context,
            ),
            Tool(
                "read_context",
                "Read a bounded chunk of one context entry or raw evidence record by its C or E identifier.",
                self._object_schema(
                    {
                        "id": {"type": "string"},
                        "offset": {"type": "integer"},
                        "max_chars": {"type": "integer"},
                    },
                    ["id"],
                ),
                self._read_context,
            ),
        ]
        return {tool.name: tool for tool in tools}

    def _list_files(self, args: dict[str, Any]) -> ToolResult:
        path = self.workspace.resolve(args["path"], must_exist=True)
        if not path.is_dir():
            raise ToolError(f"not a directory: {args['path']}")
        limit = self._bounded_int(args.get("max_entries", 200), 1, 1_000, "max_entries")
        entries: list[str] = []
        for item in sorted(path.rglob("*")):
            relative = self.workspace.relative(item)
            if any(part in {".git", ".venv", "__pycache__"} for part in item.parts):
                continue
            entries.append(relative + ("/" if item.is_dir() else ""))
            if len(entries) == limit:
                break
        suffix = "\n[entry limit reached]" if len(entries) == limit else ""
        return ToolResult(
            True,
            "\n".join(entries) + suffix,
            {"entries": len(entries), "path": args["path"]},
        )

    def _search_text(self, args: dict[str, Any]) -> ToolResult:
        query = args["query"]
        if not isinstance(query, str) or not query:
            raise ToolError("query must be a non-empty string")
        path = self.workspace.resolve(args["path"], must_exist=True)
        pattern = args.get("glob", "*")
        if not isinstance(pattern, str):
            raise ToolError("glob must be a string")
        limit = self._bounded_int(args.get("max_results", 100), 1, 500, "max_results")
        candidates = [path] if path.is_file() else path.rglob("*")
        matches: list[str] = []
        for candidate in candidates:
            if not candidate.is_file() or not fnmatch.fnmatch(candidate.name, pattern):
                continue
            if ".git" in candidate.parts or candidate.stat().st_size > 2_000_000:
                continue
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, PermissionError):
                continue
            for number, line in enumerate(lines, 1):
                if query in line:
                    matches.append(f"{self.workspace.relative(candidate)}:{number}: {line}")
                    if len(matches) == limit:
                        return ToolResult(
                            True,
                            "\n".join(matches) + "\n[result limit reached]",
                            {
                                "path": args["path"],
                                "query": query,
                                "matches": len(matches),
                                "limit_reached": True,
                            },
                        )
        return ToolResult(
            True,
            "\n".join(matches) if matches else "no matches",
            {"path": args["path"], "query": query, "matches": len(matches)},
        )

    def _read_file(self, args: dict[str, Any]) -> ToolResult:
        path = self.workspace.resolve(args["path"], must_exist=True)
        if not path.is_file():
            raise ToolError(f"not a file: {args['path']}")
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return ToolResult(
                True,
                "[empty file]",
                {
                    "path": args["path"],
                    "start": 0,
                    "end": 0,
                    "content_hash": self._file_hash(path),
                },
            )
        start = self._bounded_int(args.get("start_line", 1), 1, max(1, len(lines)), "start_line")
        default_end = min(len(lines), start + 399)
        end = self._bounded_int(args.get("end_line", default_end), start, max(start, len(lines)), "end_line")
        if end - start + 1 > 400:
            raise ToolError("read_file accepts at most 400 lines per call")
        content = "\n".join(f"{index:>6} | {lines[index - 1]}" for index in range(start, end + 1))
        return ToolResult(
            True,
            content,
            {
                "path": args["path"],
                "start": start,
                "end": end,
                "content_hash": self._file_hash(path),
            },
        )

    def _replace_text(self, args: dict[str, Any]) -> ToolResult:
        path = self.workspace.resolve(args["path"], must_exist=True)
        if not path.is_file():
            raise ToolError(f"not a file: {args['path']}")
        old_text = args["old_text"]
        new_text = args["new_text"]
        if not isinstance(old_text, str) or not old_text:
            raise ToolError("old_text must be a non-empty string")
        if not isinstance(new_text, str):
            raise ToolError("new_text must be a string")
        content = path.read_text(encoding="utf-8")
        before_hash = self._file_hash(path)
        count = content.count(old_text)
        if count != 1:
            raise ToolError(f"old_text must occur exactly once; found {count} occurrences")
        path.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return ToolResult(
            True,
            f"updated {args['path']}",
            {
                "changed": True,
                "path": args["path"],
                "before_hash": before_hash,
                "after_hash": self._file_hash(path),
            },
        )

    def _create_file(self, args: dict[str, Any]) -> ToolResult:
        path = self.workspace.resolve(args["path"])
        content = args["content"]
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        if path.exists():
            raise ToolError(f"target already exists: {args['path']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(
            True,
            f"created {args['path']}",
            {
                "changed": True,
                "path": args["path"],
                "after_hash": self._file_hash(path),
            },
        )

    def _apply_patch(self, args: dict[str, Any]) -> ToolResult:
        path = self.workspace.resolve(args["path"], must_exist=True)
        if not path.is_file():
            raise ToolError(f"not a file: {args['path']}")
        if path.stat().st_size > 2_000_000:
            raise ToolError("apply_patch does not accept files larger than 2 MB")
        content = path.read_text(encoding="utf-8")
        before_hash = self._file_hash(path)
        updated = apply_unified_hunks(content, args["patch"])
        if updated == content:
            raise ToolError("patch does not change the file")
        path.write_text(updated, encoding="utf-8", newline="")
        return ToolResult(
            True,
            f"patched {args['path']}",
            {
                "changed": True,
                "path": args["path"],
                "before_hash": before_hash,
                "after_hash": self._file_hash(path),
            },
        )

    def _show_diff(self, args: dict[str, Any]) -> ToolResult:
        requested = args.get("path")
        relative = None
        if requested is not None:
            path = self.workspace.resolve(requested, must_exist=True)
            relative = self.workspace.relative(path)
        command = ["git", "diff", "--no-ext-diff", "--no-color", "HEAD", "--"]
        if relative is not None:
            command.append(relative)
        completed = subprocess.run(
            command,
            cwd=self.workspace.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(30, self.command_timeout),
            shell=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ToolError(f"git diff failed: {detail}")
        status_command = ["git", "status", "--short", "--untracked-files=normal"]
        if relative is not None:
            status_command.extend(["--", relative])
        status = subprocess.run(
            status_command,
            cwd=self.workspace.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(30, self.command_timeout),
            shell=False,
        )
        if status.returncode != 0:
            raise ToolError(f"git status failed: {status.stderr.strip()}")
        diff = completed.stdout.strip()
        untracked = [line for line in status.stdout.splitlines() if line.startswith("?? ")]
        sections = [diff] if diff else []
        if untracked:
            sections.append("Untracked files:\n" + "\n".join(untracked))
        content = "\n\n".join(sections) or "no uncommitted changes"
        return ToolResult(
            True,
            content,
            {"path": relative or ".", "untracked": len(untracked)},
        )

    def _run_command(self, args: dict[str, Any]) -> ToolResult:
        argv = args["argv"]
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item for item in argv):
            raise ToolError("argv must be a non-empty array of non-empty strings")
        if Path(argv[0]).name.lower() in {"bash", "sh", "zsh", "cmd", "cmd.exe", "powershell", "pwsh"}:
            raise ToolError("shell interpreters are not allowed; invoke the target program directly")
        cwd = self.workspace.resolve(args.get("cwd", "."), must_exist=True)
        if not cwd.is_dir():
            raise ToolError("cwd must be a directory")
        timeout = self._bounded_int(args.get("timeout", self.command_timeout), 1, self.command_timeout, "timeout")
        before_workspace = self._workspace_snapshot()
        started = time.monotonic()
        try:
            completed = subprocess.run(
                argv,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            output = ((exc.stdout or "") + "\n" + (exc.stderr or "")).strip()
            after_workspace = self._workspace_snapshot()
            workspace_changes = sorted(
                path
                for path in set(before_workspace) | set(after_workspace)
                if before_workspace.get(path) != after_workspace.get(path)
            )
            return ToolResult(
                False,
                f"command timed out after {timeout}s\n{output}",
                {
                    "category": "timeout",
                    "timeout": timeout,
                    "workspace_changes": workspace_changes,
                },
            )
        elapsed = round(time.monotonic() - started, 3)
        output = "\n".join(
            part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
        ) or "[no output]"
        after_workspace = self._workspace_snapshot()
        workspace_changes = sorted(
            path
            for path in set(before_workspace) | set(after_workspace)
            if before_workspace.get(path) != after_workspace.get(path)
        )
        return ToolResult(
            completed.returncode == 0,
            f"exit_code={completed.returncode}\nduration={elapsed}s\n{output}",
            {
                "exit_code": completed.returncode,
                "duration": elapsed,
                "workspace_changes": workspace_changes,
            },
        )

    def _workspace_snapshot(self) -> dict[str, tuple[int, int]]:
        ignored_parts = {
            ".git",
            ".proofcode",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".tox",
            ".venv",
            "venv",
            "node_modules",
            "target",
        }
        snapshot: dict[str, tuple[int, int]] = {}
        for path in self.workspace.root.rglob("*"):
            relative = path.relative_to(self.workspace.root)
            if any(part in ignored_parts for part in relative.parts) or not path.is_file():
                continue
            try:
                stat = path.stat()
            except (FileNotFoundError, PermissionError):
                continue
            snapshot[relative.as_posix()] = (stat.st_size, stat.st_mtime_ns)
        return snapshot

    def _list_context(self, _args: dict[str, Any]) -> ToolResult:
        if self.state is None:
            raise ToolError("context state is not attached")
        return ToolResult(True, self.state.prompt_context())

    def _read_context(self, args: dict[str, Any]) -> ToolResult:
        if self.state is None:
            raise ToolError("context state is not attached")
        identifier = args["id"]
        if not isinstance(identifier, str) or not identifier:
            raise ToolError("id must be a non-empty string")
        content = self.state.describe(identifier)
        if content is None:
            raise ToolError(f"unknown context identifier: {identifier}")
        offset = self._bounded_int(args.get("offset", 0), 0, len(content), "offset")
        max_chars = self._bounded_int(args.get("max_chars", 8_000), 1, 12_000, "max_chars")
        end = min(len(content), offset + max_chars)
        return ToolResult(
            True,
            content[offset:end],
            {
                "context_id": identifier,
                "offset": offset,
                "end": end,
                "total_chars": len(content),
                "next_offset": end if end < len(content) else None,
            },
        )

    def _truncate(self, content: str) -> tuple[str, bool]:
        if len(content) <= self.output_limit:
            return content, False
        half = max(1, (self.output_limit - 100) // 2)
        omitted = len(content) - (2 * half)
        shortened = content[:half] + f"\n...[{omitted} characters omitted]...\n" + content[-half:]
        return shortened, True

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _validate_required(schema: JsonSchema, arguments: dict[str, Any]) -> None:
        missing = [name for name in schema.get("required", []) if name not in arguments]
        if missing:
            raise ToolError("missing required arguments: " + ", ".join(missing))
        unknown = set(arguments) - set(schema.get("properties", {}))
        if unknown:
            raise ToolError("unknown arguments: " + ", ".join(sorted(unknown)))

    @staticmethod
    def _bounded_int(value: Any, minimum: int, maximum: int, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ToolError(f"{name} must be an integer")
        if not minimum <= value <= maximum:
            raise ToolError(f"{name} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _object_schema(properties: JsonSchema, required: list[str]) -> JsonSchema:
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }


def format_tool_result(result: ToolResult) -> str:
    return json.dumps(
        {"ok": result.ok, "content": result.content, "metadata": result.metadata},
        ensure_ascii=False,
    )
