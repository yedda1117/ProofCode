from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Protocol

from proofcode.errors import ModelError, ProtocolError
from proofcode.types import ModelResponse, ToolCall


class ChatModel(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse: ...


class OpenAICompatibleModel:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int = 120,
        retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self.model = model
        self.timeout = timeout
        self.retries = retries

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelResponse:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return self._parse(body)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:2_000]
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise ModelError(f"Model API returned HTTP {exc.code}: {detail}") from exc
                last_error = ModelError(f"Model API returned HTTP {exc.code}: {detail}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(2**attempt)
        raise ModelError(f"Model request failed after retries: {last_error}")

    @staticmethod
    def _parse(body: dict[str, Any]) -> ModelResponse:
        try:
            choice = body["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProtocolError("Model response does not contain choices[0].message") from exc

        raw_calls = message.get("tool_calls") or []
        calls: list[ToolCall] = []
        for raw_call in raw_calls:
            try:
                function = raw_call["function"]
                arguments = json.loads(function.get("arguments") or "{}")
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must be an object")
                calls.append(
                    ToolCall(
                        id=str(raw_call["id"]),
                        name=str(function["name"]),
                        arguments=arguments,
                    )
                )
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ProtocolError(f"Invalid tool call in model response: {raw_call!r}") from exc

        normalized = {
            "role": "assistant",
            "content": message.get("content"),
        }
        if raw_calls:
            normalized["tool_calls"] = raw_calls
        return ModelResponse(
            content=message.get("content"),
            tool_calls=tuple(calls),
            raw_message=normalized,
            finish_reason=choice.get("finish_reason"),
        )
