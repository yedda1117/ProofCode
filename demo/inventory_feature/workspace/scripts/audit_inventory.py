from __future__ import annotations

import json
import sys
from pathlib import Path

from inventory.domain import load_inventory, risk_status, summarize


def audit_inventory(path: Path) -> dict:
    """Audit one inventory JSON file and return a machine-readable report."""
    products = load_inventory(path)
    errors: list[dict] = []

    seen: set[str] = set()
    for index, product in enumerate(products):
        sku = str(product.get("sku", "")).strip()
        if not sku:
            errors.append({"row": index + 1, "message": "missing required field 'sku'"})
            continue
        if sku in seen:
            errors.append({"row": index + 1, "message": f"duplicate SKU '{sku}'"})
        seen.add(sku)

        for field in ("name", "category"):
            if not str(product.get(field, "")).strip():
                errors.append({"row": index + 1, "message": f"missing required field '{field}'"})

        try:
            stock = int(product.get("stock"))
        except (TypeError, ValueError):
            errors.append({"row": index + 1, "message": "stock must be an integer"})
            stock = None
        try:
            reorder = int(product.get("reorder_level"))
        except (TypeError, ValueError):
            errors.append({"row": index + 1, "message": "reorder_level must be an integer"})
            reorder = None

        if stock is not None and stock < 0:
            errors.append({"row": index + 1, "message": "stock must be non-negative"})
        if reorder is not None and reorder < 0:
            errors.append({"row": index + 1, "message": "reorder_level must be non-negative"})

    return {
        "valid": not errors,
        "summary": summarize(products),
        "errors": errors,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m scripts.audit_inventory <inventory.json>")
    report = audit_inventory(Path(sys.argv[1]))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["valid"] else 1)
