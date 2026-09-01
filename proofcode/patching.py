from __future__ import annotations

import re

from proofcode.errors import ToolError


HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


def apply_unified_hunks(content: str, patch: str) -> str:
    if not isinstance(patch, str) or not patch.strip():
        raise ToolError("patch must be a non-empty string")
    patch_lines = patch.splitlines()
    if any(line.startswith(("--- ", "+++ ")) for line in patch_lines):
        raise ToolError("file headers are not allowed; pass the target path separately")

    newline = "\r\n" if "\r\n" in content else "\n"
    source = content.splitlines()
    trailing_newline = content.endswith(("\n", "\r"))
    output: list[str] = []
    source_cursor = 0
    index = 0
    hunks = 0

    while index < len(patch_lines):
        header = HUNK_HEADER.match(patch_lines[index])
        if header is None:
            raise ToolError(f"expected unified diff hunk header at patch line {index + 1}")
        old_start = int(header.group(1))
        old_count = int(header.group(2) or "1")
        new_count = int(header.group(4) or "1")
        target_index = old_start - 1 if old_start > 0 else 0
        if target_index < source_cursor or target_index > len(source):
            raise ToolError("patch hunks are overlapping or outside the file")
        output.extend(source[source_cursor:target_index])
        source_cursor = target_index
        index += 1
        old_seen = 0
        new_seen = 0

        while index < len(patch_lines) and not patch_lines[index].startswith("@@ "):
            line = patch_lines[index]
            if line == "\\ No newline at end of file":
                index += 1
                continue
            if not line or line[0] not in {" ", "+", "-"}:
                raise ToolError(f"invalid unified diff line at patch line {index + 1}")
            marker, text = line[0], line[1:]
            if marker in {" ", "-"}:
                if source_cursor >= len(source) or source[source_cursor] != text:
                    raise ToolError(f"patch context does not match the file at line {source_cursor + 1}")
                if marker == " ":
                    output.append(text)
                    new_seen += 1
                source_cursor += 1
                old_seen += 1
            else:
                output.append(text)
                new_seen += 1
            index += 1

        if old_seen != old_count or new_seen != new_count:
            raise ToolError(
                f"hunk count mismatch: expected -{old_count}/+{new_count}, "
                f"received -{old_seen}/+{new_seen}"
            )
        hunks += 1

    if hunks == 0:
        raise ToolError("patch contains no hunks")
    output.extend(source[source_cursor:])
    result = newline.join(output)
    if trailing_newline:
        result += newline
    return result
