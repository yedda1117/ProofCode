import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ServerContractTests(unittest.TestCase):
    def test_server_declares_preview_and_commit_routes(self) -> None:
        source = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/import/preview"', source)
        self.assertIn('"/api/import/commit"', source)
        self.assertIn("preview_import", source)
        self.assertIn("commit_import", source)


if __name__ == "__main__":
    unittest.main()
