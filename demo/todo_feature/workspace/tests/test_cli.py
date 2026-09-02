import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from todo_app.cli import main


class TodoCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name) / "todos.json"

    def run_cli(self, *arguments: str) -> str:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(["--data", str(self.data), *arguments])
        self.assertEqual(result, 0)
        return output.getvalue()

    def test_add_list_and_stats_work_together(self) -> None:
        self.run_cli("add", "Write report", "--priority", "high")
        self.run_cli("add", "Read notes", "--priority", "low")

        listing = self.run_cli("list")
        stats = self.run_cli("stats")

        self.assertIn("HIGH", listing)
        self.assertLess(listing.index("Write report"), listing.index("Read notes"))
        self.assertIn("Total: 2", stats)
        self.assertIn("Completed: 0", stats)
        self.assertIn("High: 1", stats)
        self.assertIn("Low: 1", stats)

    def test_priority_choices_are_exposed_by_parser(self) -> None:
        with self.assertRaises(SystemExit):
            main(["--data", str(self.data), "add", "Bad", "--priority", "urgent"])


if __name__ == "__main__":
    unittest.main()
