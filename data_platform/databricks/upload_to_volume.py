"""Planificar/subir artefactos locales a un Volume existente de Unity Catalog.

Por defecto sube el espejo de datos que Databricks necesita para reconstruir dbt:
`bronze`, `validated` y `quality`. Con `--bundle complete` agrega `gold`,
cuarentenas, artefactos de modelos, logs de build y manifiestos locales.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath

DEFAULT_PATTERNS = {
    "bronze": ["bronze/**/*.parquet", "bronze/manifest.json"],
    "validated": ["validated/**/*.parquet"],
    "quality": ["quality/**/*.parquet"],
}

COMPLETE_EXTRA_PATTERNS = {
    "gold": ["gold/**/*.parquet", "gold/*.json"],
    "quarantine": ["quarantine/**/*.parquet", "quarantine_references/**/*.parquet"],
    "models": ["models/*.json", "models/*.joblib"],
    "prototype": ["prototype/*.sqlite"],
    "build_logs": ["../logs/build/**/*.json", "../logs/build/**/*.log"],
}

BUNDLES = {
    "databricks-inputs": DEFAULT_PATTERNS,
    "complete": {**DEFAULT_PATTERNS, **COMPLETE_EXTRA_PATTERNS},
}


def _sha256(path: Path) -> str:
    with open(path, "rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _collect_files(data: Path, bundle: str) -> list[tuple[Path, str]]:
    if bundle not in BUNDLES:
        raise ValueError(f"bundle inválido: {bundle}")
    files: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for patterns in BUNDLES[bundle].values():
        for pattern in patterns:
            for path in sorted(data.glob(pattern)):
                if not path.is_file() or path in seen:
                    continue
                if path.is_symlink():
                    raise ValueError("No se suben enlaces simbólicos")
                try:
                    relative = path.relative_to(data).as_posix()
                except ValueError:
                    relative = "logs/" + path.relative_to(data.parent / "logs").as_posix()
                files.append((path, relative))
                seen.add(path)
    return files


def upload_plan(data: Path, volume: str, bundle: str = "databricks-inputs") -> list[dict]:
    parts = PurePosixPath(volume).parts
    if len(parts) != 5 or parts[1] != "Volumes" or ".." in parts:
        raise ValueError("Volume debe ser /Volumes/catalog/schema/volume")
    for required in ("bronze", "validated", "quality"):
        has_required_files = any(
            any(data.glob(pattern)) for pattern in BUNDLES[bundle].get(required, [])
        )
        if required in BUNDLES[bundle] and not has_required_files:
            raise FileNotFoundError(f"Falta {required}; ejecutar ingesta/auditoría primero")
    return [
        {
            "local": str(path),
            "remote": volume.rstrip("/") + "/" + relative,
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path, relative in _collect_files(data, bundle)
    ]


def upload(
    data: Path,
    volume: str,
    bundle: str = "databricks-inputs",
    execute: bool = False,
) -> dict:
    plan = upload_plan(data, volume, bundle)
    result = {
        "bundle": bundle,
        "files": len(plan),
        "bytes": sum(x["bytes"] for x in plan),
        "executed": False,
        "verified_files": 0,
    }
    if not execute:
        return result
    if not os.getenv("DATABRICKS_HOST") or not os.getenv("DATABRICKS_TOKEN"):
        raise ValueError("Faltan DATABRICKS_HOST y/o DATABRICKS_TOKEN")
    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient()
    # El SDK gestiona reintentos. No sustituye archivos existentes sin solicitud explícita.
    for item in plan:
        try:
            client.files.create_directory(str(PurePosixPath(item["remote"]).parent))
            with open(item["local"], "rb") as source:
                client.files.upload(item["remote"], source, overwrite=False)
            # Releer bytes, no solo confirmar que el API aceptó la escritura.
            remote = client.files.download(item["remote"])
            with remote.contents as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if item["sha256"] != actual:
                raise RuntimeError("Checksum remoto no coincide")
            result["verified_files"] += 1
        except Exception as exc:
            raise RuntimeError(
                "Carga interrumpida; no se confirma el espejo completo. "
                f"Archivos verificados: {result['verified_files']}"
            ) from exc
    result["executed"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--volume", default=os.getenv("NOEMA_VOLUME"))
    parser.add_argument(
        "--bundle",
        choices=sorted(BUNDLES),
        default="databricks-inputs",
        help="databricks-inputs sube bronze/validated/quality; complete agrega gold, "
        "cuarentenas, modelos y logs",
    )
    parser.add_argument("--plan-file", type=Path, help="guardar plan JSON con rutas y checksums")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.volume:
        parser.error("Falta --volume o NOEMA_VOLUME")
    if args.plan_file:
        plan = upload_plan(args.data, args.volume, args.bundle)
        args.plan_file.parent.mkdir(parents=True, exist_ok=True)
        args.plan_file.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(upload(args.data, args.volume, args.bundle, args.execute)))


if __name__ == "__main__":
    main()
