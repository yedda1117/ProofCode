import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_legacy import check_legacy_data


class LegacyCheckTests(unittest.TestCase):
    def test_checker_accepts_old_records_after_schema_evolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            path.write_text(
                json.dumps([{"id": 1, "title": "Legacy", "completed": False}]),
                encoding="utf-8",
            )
            self.assertTrue(check_legacy_data(path))


if __name__ == "__main__":
    unittest.main()
