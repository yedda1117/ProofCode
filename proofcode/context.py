from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


class Conversation:
    def __init__(self, system_prompt: str, user_task: str) -> None:
        self._initial = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_task},
        ]
        self._exchanges: list[list[dict[str, Any]]] = []

    def add_exchange(
        self,
        assistant_message: dict[str, Any],
        tool_messages: list[dict[str, Any]],
    ) -> None:
        self._exchanges.append([deepcopy(assistant_message), *deepcopy(tool_messages)])

    def add_feedback(self, assistant_message: dict[str, Any], feedback: str) -> None:
        self._exchanges.append(
            [
                deepcopy(assistant_message),
                {"role": "user", "content": feedback},
            ]
        )

    def messages(self, max_chars: int) -> list[dict[str, Any]]:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        selected: list[list[dict[str, Any]]] = []
        used = self._size(self._initial)
        for exchange in reversed(self._exchanges):
            exchange_size = self._size(exchange)
            if selected and used + exchange_size > max_chars:
                break
            selected.append(exchange)
            used += exchange_size

        selected.reverse()
        omitted = len(self._exchanges) - len(selected)
        messages = deepcopy(self._initial)
        if omitted:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"{omitted} earlier tool exchange(s) were omitted to fit the "
                        "context budget. Re-read files or rerun commands when evidence "
                        "from those exchanges is needed."
                    ),
                }
            )
        for exchange in selected:
            messages.extend(deepcopy(exchange))
        return messages

    @staticmethod
    def _size(messages: list[dict[str, Any]]) -> int:
        return len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")))
