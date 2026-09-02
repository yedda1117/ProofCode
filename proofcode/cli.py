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
        print(self.style("╭─ ProofCode · 执行证据驱动的编程智能体", self.BOLD, self.CYAN))
        print(f"│ 工作区      {workspace}")
        print(f"│ 模型        {model}")
        print(f"│ 最大步数    {max_steps}")
        print(self.style("╰─ 模型提出操作 · Runtime 执行验证", self.DIM))

    def approval(self, name: str, arguments: dict[str, Any]) -> str:
        print()
        print(self.style(f"╭─ 需要人工确认 · {name}", self.BOLD, self.YELLOW))
        for key, value in arguments.items():
            rendered = json.dumps(value, ensure_ascii=False)
            if len(rendered) > 240:
                rendered = rendered[:237] + "..."
            print(f"│ {key:<10} {rendered}")
        print(self.style("│ y：仅允许本次 · a：本次运行后续操作全部允许", self.DIM))
        print(self.style("╰─ 此操作可能修改工作区或执行代码", self.DIM))
        try:
            answer = input(self.style("请选择 [y/N/a] ", self.BOLD, self.YELLOW))
        except EOFError:
            return "deny"
        normalized = answer.strip().lower()
        if normalized in {"a", "always"}:
            return "always"
        if normalized in {"y", "yes"}:
            return "once"
        return "deny"

    def event(self, kind: str, data: dict[str, Any]) -> None:
        if kind == "step":
            label = f" 步骤 {data['step']:02d} "
            print("\n" + self.style(f"━━{label}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", self.BOLD, self.BLUE))
        elif kind == "tool_call":
            print(self.style(f"◆ 工具  {data['name']}", self.BOLD, self.CYAN))
            print("  " + _compact_arguments(data["arguments"]))
        elif kind == "tool_result":
            if data["ok"]:
                print(self.style("✓ 执行成功", self.BOLD, self.GREEN))
            else:
                print(self.style("✗ 执行失败", self.BOLD, self.RED))
            print(_indent(str(data["result"]), "  "))
        elif kind == "verification_rejected":
            print(self.style("◇ 完成门控 · 证据不足，继续执行", self.BOLD, self.YELLOW))
            print(_indent(data["reason"], "  "))

    def final(self, reason: StopReason, answer: str) -> None:
        if reason == StopReason.COMPLETED:
            heading = self.style("✓ 任务完成 · 已满足执行证据门控", self.BOLD, self.GREEN)
        else:
            heading = self.style(f"■ 任务停止 · {reason.value}", self.BOLD, self.RED)
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
        description="在本地工作区运行 ProofCode 编程智能体。",
    )
    parser.add_argument("task", nargs="?", help="编程任务；省略时将交互式询问")
    parser.add_argument("--workspace", default=".", help="工作区目录")
    parser.add_argument("--max-steps", type=int, default=20, help="最大模型调用次数")
    parser.add_argument(
        "--approve-all",
        action="store_true",
        help="无需交互确认，直接允许写操作和命令执行",
    )
    parser.add_argument(
        "--no-trajectory",
        action="store_true",
        help="不在 .proofcode/runs 下保存 JSONL 运行轨迹",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="关闭 ANSI 颜色，但保留结构化输出",
    )
    return parser


def _approval(approve_all: bool, console: Console):
    approve_remaining = False

    def approve(name: str, arguments: dict[str, Any]) -> bool:
        nonlocal approve_remaining
        if approve_all or approve_remaining:
            return True
        decision = console.approval(name, arguments)
        if decision == "always":
            approve_remaining = True
        return decision in {"once", "always"}

    return approve


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    task = args.task
    if not task:
        try:
            task = input("请输入任务：").strip()
        except EOFError:
            task = ""
    if not task:
        print("必须提供非空任务。", file=sys.stderr)
        return 2

    try:
        settings = Settings.from_environment(
            Path(args.workspace),
            max_steps=args.max_steps,
        )
    except ConfigurationError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
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
        print(f"[运行轨迹] {recorder.path}")
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
