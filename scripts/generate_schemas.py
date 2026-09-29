"""Regenerate the bronze column inventory from the ingestion manifest.

This deliberately does not rewrite ``schemas.py``: semantic constraints are
reviewed code, while the raw column inventory is reproducible metadata.
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    manifest = json.loads(Path("data/bronze/manifest.json").read_text(encoding="utf-8"))
    tables: dict[str, list[str]] = {}
    for metadata in manifest["files"].values():
        tables.setdefault(metadata["table"], metadata["columns"])

    output = Path("data_platform/contracts/columns.json")
    output.write_text(
        json.dumps(dict(sorted(tables.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(tables)} table schemas to {output}")


if __name__ == "__main__":
    main()
