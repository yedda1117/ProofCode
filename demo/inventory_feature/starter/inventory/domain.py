from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FIELDS = {"sku", "name", "category", "stock", "reorder_level"}


def load_inventory(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_inventory(path: Path, products: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(products, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
