"""Resume el manifest de ingesta en un artefacto pequeño y versionable.

El manifest completo pesa ~9 MB (una entrada por archivo de S3) y no va al repo.
Este resumen sí: da conteos por tabla y un hash del manifest, de modo que la
auditoría publicada en docs/01_data_audit.md sea verificable sin subir 9 MB.

Uso:
    python -m data_platform.ingestion.summarize_manifest
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Conteos declarados en LATAM_Bank_Complete_Data_Dictionary, para contrastar.
DECLARED = {
    "customers": 150_000,
    "products": 400_000,
    "branches": 350,
    "service_agents": 1_200,
    "marketing_campaigns": 200,
    "transactions": 5_000_000,
    "call_center_interactions": 800_000,
    "call_transcripts": 200_000,
    "satisfaction_surveys": 250_000,
    "digital_events": 10_000_000,
    "complaints": 80_000,
    "campaign_sends": 2_000_000,
    "daily_exchange_rates": 3_000,
}


def main() -> int:
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    manifest_path = data_dir / "bronze" / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"No existe {manifest_path}. Corre `make ingest` primero.")

    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)

    rows: collections.Counter[str] = collections.Counter()
    files: collections.Counter[str] = collections.Counter()
    size: collections.Counter[str] = collections.Counter()
    columns: dict[str, list[str]] = {}

    for entry in manifest["files"].values():
        table = entry["table"]
        rows[table] += entry["rows"]
        files[table] += 1
        size[table] += entry["local_size"]
        columns.setdefault(table, entry["columns"])

    tables = []
    for table in sorted(rows, key=lambda t: -rows[t]):
        declared = DECLARED.get(table)
        tables.append(
            {
                "table": table,
                "rows_observed": rows[table],
                "rows_declared": declared,
                "delta_pct": (
                    round((rows[table] - declared) / declared * 100, 1) if declared else None
                ),
                "files": files[table],
                "parquet_mb": round(size[table] / 1e6, 1),
                "columns": columns[table],
            }
        )

    summary = {
        "bucket": manifest["bucket"],
        "prefix": manifest["prefix"],
        "generated_at": manifest["generated_at"],
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "files_total": len(manifest["files"]),
        "rows_total": sum(rows.values()),
        "rows_total_declared": sum(DECLARED.values()),
        "parquet_mb_total": round(sum(size.values()) / 1e6, 1),
        "tables": tables,
    }

    out = Path("docs/data/manifest_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{out} · {summary['files_total']} archivos · {summary['rows_total']:,} filas")
    for t in tables:
        d = f"{t['delta_pct']:+.1f}%" if t["delta_pct"] is not None else "—"
        print(f"  {t['table']:28s} {t['rows_observed']:12,d}  vs declarado {d:>8s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
