from __future__ import annotations

from pathlib import Path


def check_legacy_data(path: Path) -> bool:
    """Return whether an old Todo JSON file is compatible with the current app."""
    return False


if __name__ == "__main__":
    raise SystemExit("legacy compatibility check is not implemented")
