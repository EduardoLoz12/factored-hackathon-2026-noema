"""Exportar gold en una transacción; confirmar filas mediante relectura."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import duckdb

TABLES = ["customer_360", "credit_features_asof", "product_policy", "dq_report"]


def pg_type(duck_type: str) -> str:
    if duck_type in {"VARCHAR", "UUID"}:
        return "TEXT"
    if duck_type == "BOOLEAN":
        return "BOOLEAN"
    if duck_type == "DATE":
        return "DATE"
    if duck_type.startswith("TIMESTAMP"):
        return "TIMESTAMP"
    if duck_type in {"BIGINT", "INTEGER", "SMALLINT", "TINYINT", "UBIGINT", "HUGEINT"}:
        return "NUMERIC"
    if duck_type in {"DOUBLE", "FLOAT"} or duck_type.startswith("DECIMAL"):
        return "DOUBLE PRECISION"
    raise ValueError(f"Tipo no soportado: {duck_type}")


def export(database: Path, dsn: str | None, execute: bool = False) -> dict:
    with duckdb.connect(str(database), read_only=True) as source:
        plan = {
            table: source.execute(f"SELECT count(*) FROM noema_gold.{table}").fetchone()[0]
            for table in TABLES
        }
        if not execute:
            return {"executed": False, "rows": plan}
        if not dsn:
            raise ValueError("Falta POSTGRES_DSN")
        import psycopg
        from psycopg import sql

        try:
            with psycopg.connect(dsn) as target:
                with target.cursor() as cursor:
                    cursor.execute("CREATE SCHEMA IF NOT EXISTS noema_gold")
                    for table in TABLES:
                        description = source.execute(f"DESCRIBE noema_gold.{table}").fetchall()
                        fields = sql.SQL(",").join(
                            sql.SQL("{} {}").format(
                                sql.Identifier(row[0]), sql.SQL(pg_type(row[1]))
                            )
                            for row in description
                        )
                        dest = sql.Identifier("noema_gold", table)
                        cursor.execute(
                            sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(dest, fields)
                        )
                        cursor.execute(sql.SQL("DELETE FROM {}").format(dest))
                        names = sql.SQL(",").join(sql.Identifier(row[0]) for row in description)
                        source.execute(f"SELECT * FROM noema_gold.{table}")
                        with cursor.copy(
                            sql.SQL("COPY {} ({}) FROM STDIN").format(dest, names)
                        ) as copy:
                            while batch := source.fetchmany(10000):
                                for row in batch:
                                    copy.write_row(row)
                        cursor.execute(sql.SQL("SELECT count(*) FROM {}").format(dest))
                        if cursor.fetchone()[0] != plan[table]:
                            raise RuntimeError("Relectura no coincide; rollback")
                        # Relectura de contenido ordenado; no basta el conteo de filas.
                        keys = {
                            "customer_360": ["customer_id"],
                            "credit_features_asof": ["customer_id", "asof_date"],
                            "product_policy": ["product_type", "currency"],
                            "dq_report": ["table_name", "metric", "column_name"],
                        }[table]
                        order = sql.SQL(",").join(sql.Identifier(key) for key in keys)
                        cursor.execute(
                            sql.SQL("SELECT {} FROM {} ORDER BY {}").format(names, dest, order)
                        )
                        source.execute(
                            f"SELECT * FROM noema_gold.{table} ORDER BY {','.join(keys)}"
                        )
                        while expected := source.fetchmany(10000):
                            actual = cursor.fetchmany(len(expected))
                            if actual != expected:
                                raise RuntimeError("Contenido releído no coincide; rollback")
                # Context manager confirma solo al terminar todas las tablas.
        except Exception as exc:
            raise RuntimeError("Exportación no confirmada; transacción revertida") from exc
        return {"executed": True, "rows": plan, "verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path("data/noema.duckdb"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    print(json.dumps(export(args.database, os.getenv("POSTGRES_DSN"), args.execute)))


if __name__ == "__main__":
    main()
