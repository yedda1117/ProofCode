from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Todo:
    id: int
    title: str
    completed: bool = False

    @classmethod
    def from_dict(cls, value: dict) -> "Todo":
        return cls(
            id=int(value["id"]),
            title=str(value["title"]),
            completed=bool(value.get("completed", False)),
        )

    def to_dict(self) -> dict:
        return asdict(self)
