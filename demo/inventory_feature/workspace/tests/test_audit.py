import tempfile
import unittest
from pathlib import Path

from inventory.domain import save_inventory
from scripts.audit_inventory import audit_inventory


class InventoryAuditTests(unittest.TestCase):
    def test_audit_returns_risk_summary_for_valid_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            save_inventory(path, [
                {"sku": "A-1", "name": "A", "category": "C", "stock": 0, "reorder_level": 2},
                {"sku": "B-2", "name": "B", "category": "C", "stock": 1, "reorder_level": 2},
            ])
            report = audit_inventory(path)
            self.assertTrue(report["valid"])
            self.assertEqual(report["summary"]["out"], 1)
            self.assertEqual(report["summary"]["low"], 1)

    def test_audit_detects_duplicate_and_invalid_stock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            save_inventory(path, [
                {"sku": "A-1", "name": "A", "category": "C", "stock": -1, "reorder_level": 2},
                {"sku": "A-1", "name": "B", "category": "C", "stock": 2, "reorder_level": 1},
            ])
            report = audit_inventory(path)
            self.assertFalse(report["valid"])
            self.assertGreaterEqual(len(report["errors"]), 2)


if __name__ == "__main__":
    unittest.main()
