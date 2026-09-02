import tempfile
import unittest
from pathlib import Path

from inventory import domain


VALID = """sku,name,category,stock,reorder_level
CAM-005,Camera,Accessories,7,3
LT-006,Light,Accessories,2,4
"""


class InventoryDomainTests(unittest.TestCase):
    def test_risk_status(self) -> None:
        self.assertEqual(domain.risk_status({"stock": 0, "reorder_level": 4}), "out")
        self.assertEqual(domain.risk_status({"stock": 3, "reorder_level": 4}), "low")
        self.assertEqual(domain.risk_status({"stock": 4, "reorder_level": 4}), "normal")

    def test_summary_counts_risk_groups(self) -> None:
        products = [
            {"stock": 0, "reorder_level": 2},
            {"stock": 1, "reorder_level": 2},
            {"stock": 5, "reorder_level": 2},
        ]
        self.assertEqual(
            domain.summarize(products),
            {"total": 3, "out": 1, "low": 1, "normal": 1},
        )

    def test_preview_rejects_batch_and_existing_duplicates(self) -> None:
        csv_text = """sku,name,category,stock,reorder_level
KB-001,Existing,Peripherals,2,1
NEW-1,First,Other,3,1
NEW-1,Duplicate,Other,4,1
"""
        preview = domain.preview_import(csv_text, [{"sku": "KB-001"}])
        self.assertFalse(preview["can_commit"])
        self.assertTrue(any("already exists" in error["message"] for error in preview["errors"]))
        self.assertTrue(any("duplicate" in error["message"] for error in preview["errors"]))

    def test_preview_rejects_missing_fields_and_negative_numbers(self) -> None:
        missing = domain.preview_import("sku,name\nA-1,Item\n", [])
        negative = domain.preview_import(
            "sku,name,category,stock,reorder_level\nA-1,Item,Other,-1,2\n", []
        )
        self.assertFalse(missing["can_commit"])
        self.assertFalse(negative["can_commit"])
        self.assertTrue(any("required" in error["message"] for error in missing["errors"]))
        self.assertTrue(any("non-negative" in error["message"] for error in negative["errors"]))

    def test_valid_preview_returns_typed_rows(self) -> None:
        preview = domain.preview_import(VALID, [])
        self.assertTrue(preview["can_commit"])
        self.assertEqual(preview["rows"][0]["stock"], 7)
        self.assertEqual(preview["rows"][1]["reorder_level"], 4)

    def test_invalid_commit_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            original = [{"sku": "KB-001", "name": "Keyboard", "category": "P", "stock": 2, "reorder_level": 1}]
            domain.save_inventory(path, original)
            with self.assertRaises(ValueError):
                domain.commit_import(
                    "sku,name,category,stock,reorder_level\nBAD,Bad,Other,-1,2\n",
                    path,
                )
            self.assertEqual(domain.load_inventory(path), original)

    def test_valid_commit_appends_whole_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.json"
            domain.save_inventory(path, [])
            result = domain.commit_import(VALID, path)
            self.assertEqual(result["imported"], 2)
            self.assertEqual(len(domain.load_inventory(path)), 2)


if __name__ == "__main__":
    unittest.main()
