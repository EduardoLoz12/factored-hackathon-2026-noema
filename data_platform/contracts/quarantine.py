"""Partición sin pérdidas: válidos y rechazos conservan linaje y razones."""

from pathlib import Path


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def partition(connection, table: str, query: str, output: Path) -> tuple[int, int]:
    """Query debe devolver _rejection_reason; nunca imprime datos personales."""
    connection.execute(f"CREATE OR REPLACE TEMP VIEW checked AS {query}")
    counts = connection.execute(
        "SELECT count(*) FILTER (WHERE _rejection_reason = ''), "
        "count(*) FILTER (WHERE _rejection_reason <> '') FROM checked"
    ).fetchone()
    for folder, condition in [("validated", "= ''"), ("quarantine", "<> ''")]:
        path = output / folder / table / "part.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = "* EXCLUDE (_rejection_reason)" if folder == "validated" else "*"
        connection.execute(
            f"COPY (SELECT {columns} FROM checked WHERE _rejection_reason {condition}) "
            f"TO {quote(str(path))} (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    return counts
