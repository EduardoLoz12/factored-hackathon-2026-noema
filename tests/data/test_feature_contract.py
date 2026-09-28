"""Guardarraíl de fuga de información sobre `credit_features_asof`.

Esta prueba no opina sobre cómo se construye la tabla. Solo verifica, de forma
mecánica, que no entren columnas que reflejan el desenlace en vez de precederlo.

Existe porque el error es fácil de cometer y difícil de detectar: un modelo con
fuga produce métricas espectaculares, y eso se siente como éxito hasta que
alguien lo revisa. La prevención de fuga es criterio explícito del rubro.

Se salta sola mientras la tabla no exista. Spec: docs/09_etl_spec.md §6.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

# Fecha de corte declarada en ADR-0004. Las variables solo pueden mirar hacia atrás.
CUTOFF = date(2025, 12, 31)

# Columnas que nunca pueden entrar como variable, y por qué.
PROHIBIDAS = {
    "current_balance": "refleja el estado posterior al incumplimiento",
    "last_transaction_date": "un cliente en mora deja de transar: codifica el desenlace",
    "product_status": "es consecuencia de la mora, no causa",
    "days_past_due": "es la etiqueta, nunca una variable",
    "resolution_date": "posterior al hecho que se quiere predecir",
    "compensation_granted": "posterior al hecho que se quiere predecir",
}

CANDIDATOS = [
    Path("data/gold/credit_features_asof.parquet"),
    Path("data/gold/credit_features_asof"),
]


def _tabla() -> Path | None:
    for p in CANDIDATOS:
        if p.exists():
            return p
    return None


def _leer():
    ruta = _tabla()
    if ruta is None:
        return None
    duckdb = pytest.importorskip("duckdb")
    return duckdb.sql(
        f"SELECT * FROM '{ruta.as_posix()}/*.parquet'"
        if ruta.is_dir()
        else f"SELECT * FROM '{ruta.as_posix()}'"
    )


pytestmark = pytest.mark.skipif(
    _tabla() is None,
    reason=(
        "credit_features_asof todavía no existe — es DAT-10, de Federico. Ver docs/09_etl_spec.md"
    ),
)


def test_ninguna_columna_prohibida_entra_como_variable():
    rel = _leer()
    columnas = {c.lower() for c in rel.columns}
    encontradas = {c: motivo for c, motivo in PROHIBIDAS.items() if c in columnas}
    assert not encontradas, (
        "Hay columnas con fuga de información en credit_features_asof:\n"
        + "\n".join(f"  - {c}: {motivo}" for c, motivo in encontradas.items())
        + "\n\nSi crees que alguna debería entrar, discútelo y déjalo escrito en un ADR "
        "antes de desactivar esta prueba. Ver docs/09_etl_spec.md §6."
    )


def test_la_tabla_tiene_las_llaves_acordadas():
    columnas = {c.lower() for c in _leer().columns}
    faltan = {"customer_id", "asof_date"} - columnas
    assert not faltan, f"credit_features_asof debe llevar customer_id y asof_date; faltan: {faltan}"


def test_ninguna_fila_mira_despues_del_corte():
    rel = _leer()
    if "asof_date" not in {c.lower() for c in rel.columns}:
        pytest.skip("sin asof_date no se puede verificar el corte")
    import duckdb  # noqa: F401  (ya validado por importorskip en _leer)

    maximo = rel.aggregate("max(asof_date) AS m").fetchone()[0]
    if maximo is None:
        pytest.skip("tabla vacía")
    maximo = maximo.date() if hasattr(maximo, "date") else maximo
    assert maximo <= CUTOFF, (
        f"Hay filas con asof_date {maximo}, posterior al corte declarado {CUTOFF}. "
        "Eso es mirar el futuro. Ver ADR-0004."
    )


def test_el_corte_esta_declarado_en_el_entorno_o_en_el_adr():
    """La fecha de corte es un supuesto, no un hecho del dataset: tiene que estar escrita."""
    declarado = os.getenv("FEATURES_CUTOFF")
    adr = Path("docs/decisions/ADR-0004-corte-temporal-y-fuga.md")
    assert (
        declarado or adr.exists()
    ), "La fecha de corte debe estar declarada en FEATURES_CUTOFF o en el ADR-0004."
