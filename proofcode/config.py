from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from proofcode.errors import ConfigurationError


@dataclass(frozen=True)
class Settings:
    workspace: Path
    proofcode_home: Path
    api_key: str
    base_url: str
    model: str
    max_steps: int = 20
    context_chars: int = 120_000
    tool_output_chars: int = 20_000
    command_timeout: int = 120

    @classmethod
    def from_environment(
        cls,
        workspace: str | Path,
        *,
        max_steps: int = 20,
    ) -> "Settings":
        api_key = os.environ.get("MODEL_API_KEY", "").strip()
        base_url = os.environ.get("MODEL_BASE_URL", "").strip()
        model = os.environ.get("MODEL_NAME", "").strip()
        missing = [
            name
            for name, value in (
                ("MODEL_API_KEY", api_key),
                ("MODEL_BASE_URL", base_url),
                ("MODEL_NAME", model),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Missing environment variables: " + ", ".join(missing)
            )
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            raise ConfigurationError(f"Workspace is not a directory: {root}")
        if max_steps < 1:
            raise ConfigurationError("max_steps must be at least 1")
        configured_home = os.environ.get("PROOFCODE_HOME", "").strip()
        proofcode_home = (
            Path(configured_home).expanduser().resolve()
            if configured_home
            else (Path.home() / ".proofcode").resolve()
        )
        return cls(
            workspace=root,
            proofcode_home=proofcode_home,
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            model=model,
            max_steps=max_steps,
        )
