from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class TrajectoryRecorder:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id

    @classmethod
    def create(cls, workspace: Path) -> "TrajectoryRecorder":
        now = datetime.now(UTC)
        run_id = f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        directory = workspace.resolve() / ".proofcode" / "runs"
        directory.mkdir(parents=True, exist_ok=True)
        return cls(directory / f"{run_id}.jsonl", run_id)

    def __call__(self, kind: str, data: dict[str, Any]) -> None:
        record = {
            "run_id": self.run_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": kind,
            "data": data,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
