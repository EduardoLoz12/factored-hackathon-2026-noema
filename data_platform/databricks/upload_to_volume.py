"""Planificar/subir Parquet a un Volume existente de Unity Catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath


def upload_plan(data: Path, volume: str) -> list[dict]:
    parts = PurePosixPath(volume).parts
    if len(parts) != 5 or parts[1] != "Volumes" or ".." in parts:
        raise ValueError("Volume debe ser /Volumes/catalog/schema/volume")
    files = []
    for layer in ["bronze", "validated", "quality"]:
        paths = sorted((data / layer).rglob("*.parquet"))
        if not paths:
            raise FileNotFoundError(f"Falta {layer}; ejecutar ingesta/auditoría primero")
        for path in paths:
            if path.is_symlink():
                raise ValueError("No se suben enlaces simbólicos")
            relative = path.relative_to(data).as_posix()
            files.append(
                {
                    "local": str(path),
                    "remote": volume.rstrip("/") + "/" + relative,
                    "bytes": path.stat().st_size,
                }
            )
    return files


def upload(data: Path, volume: str, execute: bool = False) -> dict:
    plan = upload_plan(data, volume)
    result = {
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
            with open(item["local"], "rb") as source:
                expected = hashlib.file_digest(source, "sha256").hexdigest()
            with remote.contents as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if expected != actual:
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
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.volume:
        parser.error("Falta --volume o NOEMA_VOLUME")
    print(json.dumps(upload(args.data, args.volume, args.execute)))


if __name__ == "__main__":
    main()
