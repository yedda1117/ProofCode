from __future__ import annotations

import argparse
from pathlib import Path

from todo_app.service import TodoService
from todo_app.storage import TodoStorage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo")
    parser.add_argument("--data", type=Path, default=Path("todos.json"))
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add")
    add.add_argument("title")
    commands.add_parser("list")
    done = commands.add_parser("done")
    done.add_argument("id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = TodoService(TodoStorage(args.data))
    if args.command == "add":
        todo = service.add(args.title)
        print(f"Added #{todo.id}: {todo.title}")
    elif args.command == "list":
        for todo in service.list_all():
            mark = "x" if todo.completed else " "
            print(f"[{mark}] #{todo.id} {todo.title}")
    elif args.command == "done":
        todo = service.complete(args.id)
        print(f"Completed #{todo.id}: {todo.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
