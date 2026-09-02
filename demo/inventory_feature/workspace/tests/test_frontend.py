import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class FrontendContractTests(unittest.TestCase):
    def test_page_exposes_dashboard_and_import_controls(self) -> None:
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        for marker in ("stat-total", "stat-out", "stat-low", "stat-normal", "csv-input", "preview-table", "import-button"):
            self.assertIn(marker, html)

    def test_client_uses_preview_and_commit_endpoints(self) -> None:
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/import/preview", script)
        self.assertIn("/api/import/commit", script)
        self.assertIn("risk", script)

    def test_page_has_accessible_status_and_filter_controls(self) -> None:
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('aria-live="polite"', html)
        self.assertIn('data-filter="out"', html)
        self.assertIn('data-filter="low"', html)
        self.assertIn('data-filter="normal"', html)


if __name__ == "__main__":
    unittest.main()
