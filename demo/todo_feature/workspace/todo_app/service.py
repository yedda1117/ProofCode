from __future__ import annotations

from todo_app.models import Todo
from todo_app.storage import TodoStorage


class TodoService:
    def __init__(self, storage: TodoStorage) -> None:
        self.storage = storage

    def add(self, title: str) -> Todo:
        todos = self.storage.load()
        next_id = max((todo.id for todo in todos), default=0) + 1
        todo = Todo(id=next_id, title=title)
        todos.append(todo)
        self.storage.save(todos)
        return todo

    def list_all(self) -> list[Todo]:
        return self.storage.load()

    def complete(self, todo_id: int) -> Todo:
        todos = self.storage.load()
        for todo in todos:
            if todo.id == todo_id:
                todo.completed = True
                self.storage.save(todos)
                return todo
        raise ValueError(f"todo {todo_id} not found")
