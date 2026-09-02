import json
import tempfile
import unittest
from pathlib import Path

from todo_app.models import Todo
from todo_app.storage import TodoStorage


class ModelAndStorageTests(unittest.TestCase):
    def test_priority_round_trips_through_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "todos.json"
            storage = TodoStorage(path)
            storage.save([Todo(id=1, title="Release", priority="high")])
            self.assertEqual(storage.load()[0].priority, "high")

    def test_old_json_without_priority_remains_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "todos.json"
            path.write_text(
                json.dumps([{"id": 1, "title": "Legacy", "completed": False}]),
                encoding="utf-8",
            )
            todo = TodoStorage(path).load()[0]
            self.assertEqual(todo.priority, "medium")

    def test_invalid_priority_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            Todo(id=1, title="Invalid", priority="urgent")


if __name__ == "__main__":
    unittest.main()
