"""Auditoría completa y cuarentena reproducible, sin PII en reportes."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import duckdb

from data_platform.contracts.quarantine import partition, quote
from data_platform.contracts.schemas import (
    COLUMNS,
    DOCUMENTED,
    FOREIGN_KEYS,
    KEYS,
    ORDER,
    RANGES,
    allowed,
    kind,
    required,
)


def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def rejection_checks(table: str) -> list[tuple[str, str]]:
    checks = []
    for column in COLUMNS[table]:
        c = f"b.{qi(column)}"
        if required(table, column):
            checks.append((f"{column}:required", f"({c} IS NULL OR trim({c}) = '')"))
        t = kind(column)
        if t != "VARCHAR":
            checks.append((f"{column}:type", f"{c} IS NOT NULL AND try_cast({c} AS {t}) IS NULL"))
        if t == "DOUBLE":
            checks.append((f"{column}:finite", f"NOT isfinite(try_cast({c} AS DOUBLE))"))
        low, high = RANGES.get(column, (None, None))
        if low is not None:
            checks.append((f"{column}:minimum", f"try_cast({c} AS DOUBLE) < {low}"))
        if high is not None:
            checks.append((f"{column}:maximum", f"try_cast({c} AS DOUBLE) > {high}"))
        values = allowed(table, column)
        if values:
            checks.append((f"{column}:enum", f"{c} NOT IN ({','.join(map(quote, values))})"))
    checks.append(("duplicate_primary_key", "b._key_count > 1"))
    for column in FOREIGN_KEYS.get(table, {}):
        if column in {"customer_id", "product_id", "interaction_id", "campaign_id"}:
            checks.append((f"{column}:orphan", f"b.{qi('_invalid_' + column)}"))
    if table == "transactions":
        checks.append(("product_customer_mismatch", "b._product_customer_mismatch"))
    return checks


def run(bronze: Path, output: Path, report_path: Path) -> dict:
    connection = duckdb.connect()
    connection.execute("SET memory_limit='2GB'")
    connection.execute("SET threads=2")
    temp_directory = Path("logs/build/duckdb_tmp")
    temp_directory.mkdir(parents=True, exist_ok=True)
    connection.execute(f"SET temp_directory='{temp_directory.as_posix()}'")
    report = {"scope": "full_dataset", "tables": {}, "warnings": []}
    metrics = []
    try:
        for table in ORDER:
            path = bronze / table / "**" / "*.parquet"
            if not list((bronze / table).rglob("*.parquet")):
                raise FileNotFoundError(
                    f"Falta bronze/{table}; no se presenta una auditoría parcial"
                )
            connection.read_parquet(str(path), hive_partitioning=False).create_view(f"raw_{table}")
            actual = [d[0] for d in connection.execute(f"DESCRIBE raw_{table}").fetchall()]
            missing = set(COLUMNS[table]) - set(actual)
            extra = set(actual) - set(COLUMNS[table])
            if missing or extra:
                raise ValueError(f"Cambio de esquema en {table}: faltan={missing}, extra={extra}")
            keys = ",".join(map(qi, KEYS[table]))
            foreign = FOREIGN_KEYS.get(table, {})
            optional = {
                col
                for col in foreign
                if col not in {"customer_id", "product_id", "interaction_id", "campaign_id"}
            }
            connection.execute(
                f"CREATE OR REPLACE TEMP TABLE duplicate_keys AS SELECT {keys}, count(*) AS n "
                f"FROM raw_{table} GROUP BY {keys} HAVING count(*)>1"
            )
            duplicate_match = " AND ".join(
                f"d.{qi(key)} IS NOT DISTINCT FROM r.{qi(key)}" for key in KEYS[table]
            )
            joins = [f"LEFT JOIN duplicate_keys d ON {duplicate_match}"]
            flags = ["coalesce(d.n,1) AS _key_count"]
            for index, (col, (parent, key)) in enumerate(foreign.items()):
                alias = f"p{index}"
                joins.append(f"LEFT JOIN valid_{parent} {alias} ON r.{qi(col)}={alias}.{qi(key)}")
                flags.append(
                    f"(r.{qi(col)} IS NOT NULL AND {alias}.{qi(key)} IS NULL) "
                    f"AS {qi('_invalid_' + col)}"
                )
                if table == "transactions" and col == "product_id":
                    flags.append(
                        f"({alias}.customer_id<>r.customer_id) AS _product_customer_mismatch"
                    )
            connection.execute(
                f"CREATE OR REPLACE TEMP VIEW batch AS SELECT r.*, "
                f"{','.join(flags)} FROM raw_{table} r {' '.join(joins)}"
            )
            original_columns = ",".join(f"b.{qi(col)}" for col in COLUMNS[table])
            repaired_rows = 0
            if optional:
                condition = " OR ".join(f"b.{qi('_invalid_' + col)}" for col in sorted(optional))
                repaired_rows = connection.execute(
                    f"SELECT count(*) FROM batch b WHERE {condition}"
                ).fetchone()[0]
                repair_path = output / "quarantine_references" / table / "part.parquet"
                repair_path.parent.mkdir(parents=True, exist_ok=True)
                reasons = ",".join(
                    f"CASE WHEN b.{qi('_invalid_' + col)} THEN {quote(col + ':orphan')} END"
                    for col in sorted(optional)
                )
                connection.execute(
                    f"COPY (SELECT {original_columns}, concat_ws(';', {reasons}) "
                    f"AS _rejection_reason FROM batch b WHERE {condition}) "
                    f"TO {quote(str(repair_path))} (FORMAT PARQUET, COMPRESSION ZSTD)"
                )
            expressions = [
                f"CASE WHEN b.{qi('_invalid_' + col)} THEN NULL ELSE b.{qi(col)} END AS {qi(col)}"
                if col in optional
                else f"b.{qi(col)}"
                for col in COLUMNS[table]
            ]
            exprs = [f"count(*) FILTER (WHERE {qi(c)} IS NULL)" for c in COLUMNS[table]]
            counts = connection.execute(
                f"SELECT count(*),{','.join(exprs)} FROM raw_{table}"
            ).fetchone()
            n = counts[0]
            duplicates = connection.execute(
                "SELECT coalesce(sum(n-1),0) FROM duplicate_keys"
            ).fetchone()[0]
            nulls = {
                c: {
                    "count": count,
                    "rate": count / n if n else 0,
                    "classification": "missing_or_optional",
                }
                for c, count in zip(COLUMNS[table], counts[1:], strict=True)
            }
            if table == "products":
                for c in ["credit_limit", "days_past_due"]:
                    structural = connection.execute(
                        f"SELECT count(*) FROM raw_products WHERE {c} "
                        "IS NULL AND product_type NOT IN ('Tarjeta Crédito','Préstamo Personal',"
                        "'Préstamo Hipotecario','Credit Card','Personal Loan','Mortgage Loan')"
                    ).fetchone()[0]
                    nulls[c].update(
                        structural_count=structural,
                        missing_count=nulls[c]["count"] - structural,
                        classification="conditional_on_product_type",
                    )
            checks = rejection_checks(table)
            reasons = ",".join(
                f"CASE WHEN ({expr}) THEN {quote(reason)} END" for reason, expr in checks
            )
            query = f"SELECT {','.join(expressions)}, concat_ws(';', {reasons}) "
            query += "AS _rejection_reason FROM batch b"
            valid, rejected = partition(connection, table, query, output)
            assert valid + rejected == n
            connection.read_parquet(str(output / "validated" / table / "part.parquet")).create_view(
                f"valid_{table}"
            )
            orphan_counts = {}
            for col, (parent, key) in FOREIGN_KEYS.get(table, {}).items():
                orphan_counts[col] = connection.execute(
                    f"SELECT count(*) FROM raw_{table} b "
                    f"WHERE b.{qi(col)} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM raw_{parent} p "
                    f"WHERE p.{qi(key)}=b.{qi(col)})"
                ).fetchone()[0]
            entry = {
                "rows": n,
                "documented_rows": DOCUMENTED[table],
                "duplicate_excess_rows": duplicates,
                "nulls": nulls,
                "orphan_foreign_keys": orphan_counts,
                "valid_rows": valid,
                "quarantined_rows": rejected,
                "repaired_reference_rows": repaired_rows,
            }
            if table == "customers":
                entry["phone_country_mismatch"] = connection.execute(
                    "SELECT count(*) FROM raw_customers "
                    "WHERE mobile_phone IS NOT NULL AND NOT starts_with(mobile_phone, "
                    "CASE country WHEN 'México' THEN '+52' WHEN 'Colombia' THEN '+57' "
                    "WHEN 'Argentina' THEN '+54' ELSE '?' END)"
                ).fetchone()[0]
            if table == "products":
                entry["mexican_customers_non_mxn_products"] = connection.execute(
                    "SELECT count(*) FROM raw_products p JOIN raw_customers c USING(customer_id) "
                    "WHERE c.country='México' AND p.currency<>'MXN'"
                ).fetchone()[0]
            if table == "transactions":
                entry["operation_outside_process_date"] = connection.execute(
                    "SELECT count(*) FROM "
                    "raw_transactions WHERE try_cast(transaction_date AS DATE)<>"
                    "try_cast(process_date AS DATE)"
                ).fetchone()[0]
            report["tables"][table] = entry
            for metric, value in entry.items():
                if isinstance(value, int | float):
                    metrics.append((table, metric, "", float(value)))
            for col, values in nulls.items():
                for metric in ["count", "rate", "structural_count", "missing_count"]:
                    if metric in values:
                        metrics.append((table, "null_" + metric, col, float(values[metric])))
            for col, value in orphan_counts.items():
                metrics.append((table, "orphan_foreign_key", col, float(value)))
            print(f"{table}: {n:,} filas; {rejected:,} en cuarentena", flush=True)
        connection.execute(
            "CREATE TABLE metrics(table_name VARCHAR, metric VARCHAR, "
            "column_name VARCHAR, value DOUBLE)"
        )
        connection.executemany("INSERT INTO metrics VALUES (?,?,?,?)", metrics)
        target = output / "quality" / "dq_report.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        connection.execute(f"COPY metrics TO {quote(str(target))} (FORMAT PARQUET)")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return report
    finally:
        connection.close()
        # DuckDB deja archivos de spill cuando una consulta necesita más que el
        # límite de memoria. Son temporales de esta auditoría, no evidencia.
        shutil.rmtree(temp_directory, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze", type=Path, default=Path("data/bronze"))
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=Path("logs/build/dq_report.json"))
    args = parser.parse_args()
    run(args.bronze, args.output, args.report)


if __name__ == "__main__":
    main()
