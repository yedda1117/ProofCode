from __future__ import annotations

from pathlib import Path


def audit_inventory(path: Path) -> dict:
    """Audit one inventory JSON file and return a machine-readable report."""
    raise NotImplementedError("inventory audit is not implemented")


if __name__ == "__main__":
    raise SystemExit("inventory audit is not implemented")
