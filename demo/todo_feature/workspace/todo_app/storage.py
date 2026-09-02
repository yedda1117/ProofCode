from __future__ import annotations

import json
from pathlib import Path

from todo_app.models import Todo


class TodoStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Todo]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return [Todo.from_dict(item) for item in payload]

    def save(self, todos: list[Todo]) -> None:
        self.path.write_text(
            json.dumps([todo.to_dict() for todo in todos], ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
