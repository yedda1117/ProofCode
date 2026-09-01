from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from proofcode.agent import CodingAgent
from proofcode.config import Settings
from proofcode.errors import ConfigurationError
from proofcode.model import OpenAICompatibleModel
from proofcode.tools import ToolRegistry
from proofcode.types import StopReason


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proofcode",
        description="Run a coding agent in a local workspace.",
    )
    parser.add_argument("task", nargs="?", help="Programming task. Prompts when omitted.")
    parser.add_argument("--workspace", default=".", help="Workspace directory")
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum model calls")
    parser.add_argument(
        "--approve-all",
        action="store_true",
        help="Run write and command tools without interactive confirmation",
    )
    return parser


def _approval(approve_all: bool):
    def approve(name: str, arguments: dict[str, Any]) -> bool:
        if approve_all:
            return True
        print(f"\nApproval required for {name}:")
        print(json.dumps(arguments, ensure_ascii=False, indent=2))
        try:
            answer = input("Allow? [y/N] ").strip().lower()
        except EOFError:
            return False
        return answer in {"y", "yes"}

    return approve


def _event(kind: str, data: dict[str, Any]) -> None:
    if kind == "step":
        print(f"\n[step {data['step']}]")
    elif kind == "tool_call":
        arguments = json.dumps(data["arguments"], ensure_ascii=False)
        print(f"[tool] {data['name']} {arguments}")
    elif kind == "tool_result":
        status = "ok" if data["ok"] else "error"
        print(f"[{status}] {data['result']}")
    elif kind == "verification_rejected":
        print(f"[verification] {data['reason']}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    task = args.task
    if not task:
        try:
            task = input("Task: ").strip()
        except EOFError:
            task = ""
    if not task:
        print("A non-empty task is required.", file=sys.stderr)
        return 2

    try:
        settings = Settings.from_environment(
            Path(args.workspace),
            max_steps=args.max_steps,
        )
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    model = OpenAICompatibleModel(
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.model,
    )
    tools = ToolRegistry(
        settings.workspace,
        output_limit=settings.tool_output_chars,
        command_timeout=settings.command_timeout,
        approve=_approval(args.approve_all),
    )
    result = CodingAgent(
        model=model,
        tools=tools,
        max_steps=settings.max_steps,
        context_chars=settings.context_chars,
        on_event=_event,
    ).run(task)
    print(f"\n[{result.reason.value}]\n{result.answer}")
    return 0 if result.reason == StopReason.COMPLETED else 1


if __name__ == "__main__":
    raise SystemExit(main())
