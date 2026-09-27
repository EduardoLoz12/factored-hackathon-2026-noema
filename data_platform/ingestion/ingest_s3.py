"""Ingesta S3 → bronze (Parquet).

Única pieza del sistema que toca las credenciales de Factored.
Nunca se importa desde la API ni desde el agente.

Diseño:
- Lee el bucket read-only y escribe Parquet particionado en data/bronze/.
- Genera manifest.json con checksum por archivo → reproducibilidad y detección de drift.
- Reanudable: si el manifest ya tiene el archivo y el destino existe con el mismo tamaño, lo salta.
- Falla por archivo, no por corrida: los errores se acumulan y se reportan al final.

Uso:
    python -m data_platform.ingestion.ingest_s3                 # todo
    python -m data_platform.ingestion.ingest_s3 --tables products customers
    python -m data_platform.ingestion.ingest_s3 --skip digital_events
    python -m data_platform.ingestion.ingest_s3 --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import boto3
import pandas as pd
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s ingest: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")

# Tablas de dimensión: un solo CSV plano en la raíz de data/
FLAT_TABLES = [
    "customers",
    "products",
    "branches",
    "service_agents",
    "marketing_campaigns",
    "daily_exchange_rates",
]

# Tablas de hechos: particionadas year=/month=/day=
PARTITIONED_TABLES = [
    "transactions",
    "call_center_interactions",
    "call_transcripts",
    "satisfaction_surveys",
    "complaints",
    "campaign_sends",
    "digital_events",
]

ALL_TABLES = FLAT_TABLES + PARTITIONED_TABLES


@dataclass
class IngestStats:
    files_ok: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    rows: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    errors: list[str] = field(default_factory=list)


def build_client():
    """Cliente S3 read-only. Las credenciales salen del .env, nunca del código."""
    key = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-2")
    if not key or not secret:
        raise SystemExit(
            "Faltan AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY en .env. "
            "Copia .env.example a .env y rellénalos (ver primera página del Data Dictionary)."
        )
    return boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name=region,
        config=Config(max_pool_connections=32, retries={"max_attempts": 5, "mode": "adaptive"}),
    )


def list_objects(s3, bucket: str, prefix: str) -> list[dict]:
    """Lista completa con paginación. Devuelve key, size, etag."""
    out: list[dict] = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kwargs)
        for c in resp.get("Contents", []):
            out.append({"key": c["Key"], "size": c["Size"], "etag": c["ETag"].strip('"')})
        if not resp.get("IsTruncated"):
            break
        token = resp["NextContinuationToken"]
    return out


def table_of(key: str, prefix: str) -> str | None:
    """Deriva el nombre de tabla desde la key de S3."""
    rel = key[len(prefix) :] if key.startswith(prefix) else key
    parts = rel.split("/")
    if len(parts) == 1:
        return parts[0].rsplit(".", 1)[0] if parts[0].endswith(".csv") else None
    return parts[0]


def local_target(key: str, prefix: str, data_dir: Path) -> Path:
    """data/bronze/<tabla>/[year=/month=/day=/]<archivo>.parquet"""
    rel = key[len(prefix) :] if key.startswith(prefix) else key
    parts = rel.split("/")
    if len(parts) == 1:
        table = parts[0].rsplit(".", 1)[0]
        return data_dir / "bronze" / table / f"{table}.parquet"
    filename = parts[-1].rsplit(".", 1)[0] + ".parquet"
    return data_dir / "bronze" / "/".join(parts[:-1]) / filename


def ingest_one(s3, bucket: str, obj: dict, prefix: str, data_dir: Path) -> dict:
    """Descarga un CSV, lo convierte a Parquet y devuelve su entrada de manifest.

    Todo el contenido se lee como string: la normalización de tipos es trabajo
    de la capa silver. Bronze conserva el dato tal como llegó.
    """
    key = obj["key"]
    dest = local_target(key, prefix, data_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)

    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    df = pd.read_csv(io.BytesIO(body), dtype=str, keep_default_na=False, na_values=[""])

    # Linaje: de qué archivo salió cada fila y cuándo entró.
    df["_source_file"] = key
    df["_ingested_at"] = pd.Timestamp.now(tz="UTC").isoformat()

    df.to_parquet(dest, index=False, compression="snappy")

    return {
        "key": key,
        "table": table_of(key, prefix),
        "local": str(dest.relative_to(data_dir)),
        "s3_size": obj["size"],
        "s3_etag": obj["etag"],
        "local_size": dest.stat().st_size,
        "sha256": hashlib.sha256(body).hexdigest(),
        "rows": int(len(df)),
        "columns": list(df.columns),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingesta S3 → bronze (Parquet)")
    ap.add_argument("--tables", nargs="*", default=None, help="solo estas tablas")
    ap.add_argument("--skip", nargs="*", default=[], help="excluir estas tablas")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bucket = os.getenv("S3_BUCKET")
    prefix = os.getenv("S3_PREFIX", "data/")
    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    if not bucket:
        raise SystemExit("Falta S3_BUCKET en .env")

    wanted = set(args.tables or ALL_TABLES) - set(args.skip)
    unknown = wanted - set(ALL_TABLES)
    if unknown:
        raise SystemExit(f"Tablas desconocidas: {sorted(unknown)}")

    s3 = build_client()
    log.info("Listando s3://%s/%s ...", bucket, prefix)
    objects = [o for o in list_objects(s3, bucket, prefix) if o["key"].endswith(".csv")]
    objects = [o for o in objects if table_of(o["key"], prefix) in wanted]

    total_bytes = sum(o["size"] for o in objects)
    log.info(
        "%d objetos · %.2f GB · tablas: %s",
        len(objects),
        total_bytes / 1e9,
        ", ".join(sorted(wanted)),
    )

    if args.dry_run:
        return 0

    manifest_path = data_dir / "bronze" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {})
        log.info("Manifest previo: %d archivos ya registrados", len(manifest))

    pending = []
    stats = IngestStats(bytes_in=total_bytes)
    for o in objects:
        prev = manifest.get(o["key"])
        dest = local_target(o["key"], prefix, data_dir)
        if prev and prev.get("s3_etag") == o["etag"] and dest.exists():
            stats.files_skipped += 1
            stats.rows += prev.get("rows", 0)
            continue
        pending.append(o)

    log.info("Por descargar: %d · ya presentes: %d", len(pending), stats.files_skipped)
    started = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(ingest_one, s3, bucket, o, prefix, data_dir): o for o in pending}
        done = 0
        for fut in as_completed(futures):
            obj = futures[fut]
            try:
                entry = fut.result()
                manifest[entry["key"]] = entry
                stats.files_ok += 1
                stats.rows += entry["rows"]
                stats.bytes_out += entry["local_size"]
            except Exception as exc:  # una falla no tumba la corrida
                stats.files_failed += 1
                stats.errors.append(f"{obj['key']}: {type(exc).__name__}: {exc}")
                log.warning("FALLÓ %s → %s", obj["key"], exc)
            done += 1
            if done % 250 == 0 or done == len(pending):
                elapsed = time.time() - started
                log.info(
                    "%d/%d archivos · %.0fs · %.1f arch/s",
                    done,
                    len(pending),
                    elapsed,
                    done / max(elapsed, 1),
                )

    manifest_path.write_text(
        json.dumps(
            {
                "bucket": bucket,
                "prefix": prefix,
                "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "tables": sorted(wanted),
                "files": manifest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    log.info(
        "LISTO · ok=%d saltados=%d fallidos=%d · filas=%s · %.2f GB CSV → %.2f GB Parquet",
        stats.files_ok,
        stats.files_skipped,
        stats.files_failed,
        f"{stats.rows:,}",
        stats.bytes_in / 1e9,
        stats.bytes_out / 1e9,
    )
    if stats.errors:
        log.error("Errores (%d), primeros 10:", len(stats.errors))
        for e in stats.errors[:10]:
            log.error("  %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
