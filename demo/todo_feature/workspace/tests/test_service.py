import tempfile
import unittest
from pathlib import Path

from todo_app.models import Todo
from todo_app.service import TodoService
from todo_app.storage import TodoStorage


class TodoServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = TodoStorage(Path(self.directory.name) / "todos.json")
        self.service = TodoService(self.storage)

    def test_add_accepts_priority(self) -> None:
        todo = self.service.add("Release", priority="high")
        self.assertEqual(todo.priority, "high")

    def test_list_places_incomplete_high_priority_first(self) -> None:
        self.storage.save(
            [
                Todo(id=1, title="Completed", completed=True, priority="high"),
                Todo(id=2, title="Low", priority="low"),
                Todo(id=3, title="High", priority="high"),
                Todo(id=4, title="Medium", priority="medium"),
            ]
        )
        self.assertEqual(
            [todo.id for todo in self.service.list_all()],
            [3, 4, 2, 1],
        )

    def test_stats_reports_completion_and_priority_counts(self) -> None:
        self.storage.save(
            [
                Todo(id=1, title="A", completed=True, priority="high"),
                Todo(id=2, title="B", priority="high"),
                Todo(id=3, title="C", priority="low"),
            ]
        )
        self.assertEqual(
            self.service.stats(),
            {
                "total": 3,
                "completed": 1,
                "high": 2,
                "medium": 0,
                "low": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
