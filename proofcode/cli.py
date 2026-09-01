from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from proofcode.agent import CodingAgent
from proofcode.config import Settings
from proofcode.errors import ConfigurationError
from proofcode.model import OpenAICompatibleModel
from proofcode.trajectory import TrajectoryRecorder
from proofcode.tools import ToolRegistry
from proofcode.types import StopReason


class Console:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"

    def __init__(self, *, color: bool | None = None) -> None:
        if color is None:
            color = (
                sys.stdout.isatty()
                and "NO_COLOR" not in os.environ
                and os.environ.get("TERM", "") != "dumb"
            )
        self.color = color

    def style(self, text: str, *codes: str) -> str:
        if not self.color:
            return text
        return "".join(codes) + text + self.RESET

    def banner(self, *, workspace: Path, model: str, max_steps: int) -> None:
        print()
        print(self.style("╭─ ProofCode · evidence-driven coding agent", self.BOLD, self.CYAN))
        print(f"│ workspace  {workspace}")
        print(f"│ model      {model}")
        print(f"│ max steps  {max_steps}")
        print(self.style("╰─ model proposes · runtime verifies", self.DIM))

    def approval(self, name: str, arguments: dict[str, Any]) -> bool:
        print()
        print(self.style(f"╭─ APPROVAL REQUIRED · {name}", self.BOLD, self.YELLOW))
        for key, value in arguments.items():
            rendered = json.dumps(value, ensure_ascii=False)
            if len(rendered) > 240:
                rendered = rendered[:237] + "..."
            print(f"│ {key:<10} {rendered}")
        print(self.style("╰─ this action can change state or execute code", self.DIM))
        try:
            answer = input(self.style("Allow this action? [y/N] ", self.BOLD, self.YELLOW))
        except EOFError:
            return False
        return answer.strip().lower() in {"y", "yes"}

    def event(self, kind: str, data: dict[str, Any]) -> None:
        if kind == "step":
            label = f" STEP {data['step']:02d} "
            print("\n" + self.style(f"━━{label}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", self.BOLD, self.BLUE))
        elif kind == "tool_call":
            print(self.style(f"◆ TOOL  {data['name']}", self.BOLD, self.CYAN))
            print("  " + _compact_arguments(data["arguments"]))
        elif kind == "tool_result":
            if data["ok"]:
                print(self.style("✓ RESULT", self.BOLD, self.GREEN))
            else:
                print(self.style("✗ RESULT", self.BOLD, self.RED))
            print(_indent(str(data["result"]), "  "))
        elif kind == "verification_rejected":
            print(self.style("◇ COMPLETION GATE · CONTINUE", self.BOLD, self.YELLOW))
            print(_indent(data["reason"], "  "))

    def final(self, reason: StopReason, answer: str) -> None:
        if reason == StopReason.COMPLETED:
            heading = self.style("✓ COMPLETED · evidence gate satisfied", self.BOLD, self.GREEN)
        else:
            heading = self.style(f"■ STOPPED · {reason.value}", self.BOLD, self.RED)
        print(f"\n{heading}\n{answer}")


def _compact_arguments(arguments: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in arguments.items():
        if key == "argv" and isinstance(value, list):
            rendered = " ".join(str(item) for item in value)
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        if len(rendered) > 120:
            rendered = rendered[:117] + "..."
        parts.append(f"{key}={rendered}")
    return " · ".join(parts) if parts else "no arguments"


def _indent(value: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in value.splitlines())


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
    parser.add_argument(
        "--no-trajectory",
        action="store_true",
        help="Do not write a JSONL run trajectory under .proofcode/runs",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors while keeping structured output",
    )
    return parser


def _approval(approve_all: bool, console: Console):
    def approve(name: str, arguments: dict[str, Any]) -> bool:
        if approve_all:
            return True
        return console.approval(name, arguments)

    return approve


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
    console = Console(color=False if args.no_color else None)
    console.banner(
        workspace=settings.workspace,
        model=settings.model,
        max_steps=settings.max_steps,
    )
    tools = ToolRegistry(
        settings.workspace,
        output_limit=settings.tool_output_chars,
        command_timeout=settings.command_timeout,
        approve=_approval(args.approve_all, console),
    )
    recorder = None if args.no_trajectory else TrajectoryRecorder.create(settings.workspace)

    def emit(kind: str, data: dict[str, Any]) -> None:
        console.event(kind, data)
        if recorder is not None:
            recorder(kind, data)

    if recorder is not None:
        recorder(
            "run_started",
            {
                "task": task,
                "workspace": str(settings.workspace),
                "model": settings.model,
                "max_steps": settings.max_steps,
            },
        )
        print(f"[trajectory] {recorder.path}")
    result = CodingAgent(
        model=model,
        tools=tools,
        max_steps=settings.max_steps,
        context_chars=settings.context_chars,
        on_event=emit,
    ).run(task)
    if recorder is not None:
        recorder(
            "run_finished",
            {
                "reason": result.reason.value,
                "answer": result.answer,
                "steps": result.steps,
            },
        )
    console.final(result.reason, result.answer)
    return 0 if result.reason == StopReason.COMPLETED else 1


if __name__ == "__main__":
    raise SystemExit(main())
