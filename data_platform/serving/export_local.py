"""Publicar Parquet gold después de un dbt build correcto."""

from pathlib import Path

import duckdb

from data_platform.contracts.quarantine import quote
from data_platform.serving.export_to_postgres import TABLES


def main():
    output = Path("data/gold")
    output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect("data/noema.duckdb", read_only=True) as conn:
        for table in TABLES:
            path = output / f"{table}.parquet"
            conn.execute(f"COPY noema_gold.{table} TO {quote(str(path))} (FORMAT PARQUET)")
        path = Path("data/quarantine/transaction_fx/part.parquet")
        path.parent.mkdir(parents=True, exist_ok=True)
        conn.execute(
            f"COPY noema_silver.quarantine_transaction_fx TO {quote(str(path))} (FORMAT PARQUET)"
        )


if __name__ == "__main__":
    main()
