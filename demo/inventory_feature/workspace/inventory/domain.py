from __future__ import annotations

import csv
import io
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


def risk_status(product: dict) -> str:
    """Classify a product's stock risk: out / low / normal."""
    stock = product.get("stock", 0)
    reorder = product.get("reorder_level", 0)
    if stock <= 0:
        return "out"
    if stock < reorder:
        return "low"
    return "normal"


def summarize(products: list[dict]) -> dict:
    """Return counts of total products and each risk group."""
    counts = {"out": 0, "low": 0, "normal": 0}
    for product in products:
        counts[risk_status(product)] += 1
    return {"total": len(products), **counts}


def _parse_csv(csv_text: str) -> tuple[list[dict], list[dict]]:
    """Parse CSV text into typed rows. Returns (rows, errors)."""
    rows: list[dict] = []
    errors: list[dict] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        errors.append({"row": 1, "message": "CSV is empty or missing a header row"})
        return rows, errors

    missing_headers = REQUIRED_FIELDS - set(reader.fieldnames)
    if missing_headers:
        errors.append(
            {
                "row": 1,
                "message": "required columns missing: " + ", ".join(sorted(missing_headers)),
            }
        )
        return rows, errors

    for index, raw in enumerate(reader, start=2):
        row_errors: list[str] = []
        for field in REQUIRED_FIELDS:
            value = (raw.get(field) or "").strip()
            if not value:
                row_errors.append(f"missing required field '{field}'")
        if row_errors:
            errors.append({"row": index, "message": "; ".join(row_errors)})
            continue

        try:
            stock = int(raw["stock"].strip())
        except ValueError:
            errors.append({"row": index, "message": "stock must be an integer"})
            continue
        try:
            reorder = int(raw["reorder_level"].strip())
        except ValueError:
            errors.append({"row": index, "message": "reorder_level must be an integer"})
            continue

        if stock < 0:
            errors.append({"row": index, "message": "stock must be non-negative"})
            continue
        if reorder < 0:
            errors.append({"row": index, "message": "reorder_level must be non-negative"})
            continue

        rows.append(
            {
                "sku": raw["sku"].strip(),
                "name": raw["name"].strip(),
                "category": raw["category"].strip(),
                "stock": stock,
                "reorder_level": reorder,
            }
        )
    return rows, errors


def preview_import(csv_text: str, existing: list[dict]) -> dict:
    """Validate CSV rows against existing inventory. Returns preview report."""
    rows, errors = _parse_csv(csv_text)

    existing_skus = {str(product.get("sku", "")).strip() for product in existing}
    seen: set[str] = set()

    for row in rows:
        sku = row["sku"]
        if sku in existing_skus:
            errors.append({"row": 0, "message": f"SKU '{sku}' already exists in inventory"})
        elif sku in seen:
            errors.append({"row": 0, "message": f"duplicate SKU '{sku}' within the batch"})
        else:
            seen.add(sku)

    return {
        "can_commit": not errors,
        "rows": rows,
        "errors": errors,
    }


def commit_import(csv_text: str, path: Path) -> dict:
    """Validate and atomically append a whole CSV batch to the inventory file."""
    existing = load_inventory(path)
    preview = preview_import(csv_text, existing)
    if not preview["can_commit"]:
        raise ValueError("CSV import rejected: " + "; ".join(e["message"] for e in preview["errors"]))

    combined = existing + preview["rows"]
    save_inventory(path, combined)
    return {"imported": len(preview["rows"])}
