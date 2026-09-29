"""Validadores del feature store as-of — ML-01.

Estas pruebas no comprueban que el código corra: comprueban que la tabla que
produce sea **usable para entrenar sin engañarse**. Cada una existe porque el
error que atrapa es fácil de cometer y produce métricas que se sienten como
éxito.

Se saltan solas mientras el feature store no exista. Para generarlo:

    python -m ml.features.build_features

Spec: `docs/checklist.json` ML-01. Corte: ADR-0004.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ml.features.build_features import (
    COLUMNAS_PROHIBIDAS,
    CORTE_POR_DEFECTO,
    DIAS_MORA,
    PRODUCTOS_DE_CREDITO,
    verificar_sin_fuga,
)

TABLA = Path("data/gold/features_asof.parquet")
SIN_TABLA = "features_asof.parquet no existe: corre `python -m ml.features.build_features`"

pytestmark = pytest.mark.skipif(not TABLA.exists(), reason=SIN_TABLA)


@pytest.fixture(scope="module")
def df():
    pd = pytest.importorskip("pandas")
    return pd.read_parquet(TABLA)


# ── Fuga de información ──────────────────────────────────────────────────────


def test_ninguna_columna_prohibida_entra(df):
    """La lista de prohibidas es la misma que protege la tabla de Federico.

    Está duplicada a propósito: su prueba cuida `credit_features_asof` y esta
    cuida el feature store. Ninguna debe depender de que la otra se ejecute.
    """
    presentes = {c.lower() for c in df.columns}
    fuga = {c: m for c, m in COLUMNAS_PROHIBIDAS.items() if c in presentes}
    assert not fuga, "Columnas con fuga en el feature store:\n" + "\n".join(
        f"  - {c}: {m}" for c, m in fuga.items()
    )


def test_el_verificador_falla_cuando_debe():
    """El guardarraíl tiene que disparar. Una prueba que nunca falla no protege nada."""
    with pytest.raises(ValueError, match="fuga"):
        verificar_sin_fuga(["customer_id", "days_past_due"])
    # Y no debe dar falsos positivos con nombres que solo se parecen.
    verificar_sin_fuga(["customer_id", "dias_hasta_etiqueta", "mora_90"])


def test_ninguna_fila_mira_despues_del_corte(df):
    maximo = df.asof_date.max()
    maximo = maximo.date() if hasattr(maximo, "date") else maximo
    assert maximo <= CORTE_POR_DEFECTO, (
        f"Hay filas con asof_date {maximo}, posterior al corte {CORTE_POR_DEFECTO}."
    )


def test_la_antiguedad_nunca_es_negativa(df):
    """Una antigüedad negativa significa que el cliente se registró después del
    corte, o sea que la fila no debería existir."""
    for col in ["antiguedad_cliente_dias", "antiguedad_producto_dias"]:
        v = df[col].dropna()
        assert (v >= 0).all(), (
            f"{col} tiene {int((v < 0).sum())} valores negativos: "
            "hay filas construidas con hechos posteriores al corte."
        )


# ── Validez temporal de la etiqueta ──────────────────────────────────────────


def test_la_cohorte_estricta_observa_la_etiqueta_despues_del_corte(df):
    """El corazón de ML-01.

    Si la etiqueta se registró antes que las variables, el modelo predice el
    pasado con el futuro. En este dataset le pasa al 88 % de los productos, así
    que la cohorte entrenable es la minoría y hay que separarla explícitamente.
    """
    estricta = df[df.etiqueta_posterior == 1]
    assert len(estricta) > 0, "La cohorte estricta quedó vacía."
    assert (estricta.dias_hasta_etiqueta > 0).all(), (
        "Hay filas en la cohorte estricta cuya etiqueta se observó antes del corte."
    )
    assert estricta.mora_90_estricta.notna().all(), (
        "Hay filas marcadas como estrictas sin etiqueta estricta."
    )
    # La etiqueta estricta solo puede venir de productos observados después.
    assert (estricta.n_credito_estricto > 0).all()


def test_la_etiqueta_estricta_no_mezcla_observaciones(df):
    """El bug que esta prueba atrapó la primera vez.

    Un cliente con dos productos de crédito —uno observado antes del corte y
    otro después— quedaba marcado como estricto con una etiqueta agregada sobre
    ambos. La validez temporal tiene que imponerse dentro de la agregación, no
    marcarse después.
    """
    fuera = df[df.etiqueta_posterior == 0]
    assert fuera.mora_90_estricta.isna().all(), (
        "Hay etiqueta estricta en filas que no deberían tenerla."
    )
    # Donde hay ambas, la estricta no puede superar a la completa: se calcula
    # sobre un subconjunto de los mismos productos.
    ambas = df[(df.etiqueta_posterior == 1) & df.mora_90.notna()]
    assert (ambas.mora_90_estricta <= ambas.mora_90).all(), (
        "La etiqueta estricta marca mora donde la completa no: imposible, "
        "porque se agrega sobre un subconjunto."
    )


def test_la_cohorte_estricta_es_mas_chica_que_la_completa(df):
    """Si fueran iguales, la marca `etiqueta_posterior` no estaría funcionando."""
    completa = int((df.etiquetable == 1).sum())
    estricta = int(((df.etiquetable == 1) & (df.etiqueta_posterior == 1)).sum())
    assert 0 < estricta < completa, (
        f"estricta={estricta}, completa={completa}: la separación temporal no está aplicando."
    )


def test_la_etiqueta_solo_existe_donde_hay_producto_de_credito(df):
    """`days_past_due` es nulo estructural fuera del crédito (F-014).

    Contarlo como «al día» infla el denominador un 64 % y baja la tasa de mora
    de 10.7 % a 6.5 % (F-015).
    """
    etiquetados = df[df.etiquetable == 1]
    assert (etiquetados.n_productos_credito > 0).all(), (
        f"{int((etiquetados.n_productos_credito == 0).sum())} clientes tienen etiqueta "
        "sin tener producto de crédito: el nulo estructural se coló como cero."
    )


def test_la_etiqueta_es_binaria_y_coherente(df):
    e = df[df.etiquetable == 1]
    assert set(e.mora_90.unique()) <= {0, 1}
    # Quien está en mora a 90 días lo está también «en cualquier grado».
    assert (e.mora_90 <= e.mora_cualquiera).all(), (
        "Hay clientes con mora_90 = 1 y mora_cualquiera = 0: son incompatibles."
    )


# ── Regímenes de nulo (F-014) ────────────────────────────────────────────────


def test_cada_columna_imputable_lleva_su_indicador(df):
    """El nulo inyectado se imputa, pero la marca viaja al modelo igual."""
    pares = [
        ("credit_score", "credit_score_faltante"),
        ("ingreso_declarado", "ingreso_faltante"),
        ("tasa_interes_media", "tasa_faltante"),
    ]
    for valor, marca in pares:
        assert marca in df.columns, f"falta el indicador {marca}"
        assert (df[valor].isna() == (df[marca] == 1)).all(), (
            f"{marca} no coincide con los nulos reales de {valor}."
        )


def test_las_marcas_de_contaminacion_existen(df):
    """`products` y `customers` son fotos: el 12 % se actualizó después del corte.

    Esas filas llevan información que en el corte no existía, y el modelo tiene
    que poder excluirlas.
    """
    for marca in ["cliente_posterior", "limite_posterior"]:
        assert marca in df.columns, f"falta la marca {marca}"
        assert df[marca].isin([0, 1]).all()
    assert df.cliente_posterior.sum() > 0, (
        "Ninguna fila marcada como posterior al corte: la marca no está midiendo nada."
    )


# ── Coherencia interna ───────────────────────────────────────────────────────


def test_las_llaves_son_unicas(df):
    assert not df.customer_id.duplicated().any(), "hay customer_id repetidos"
    assert df.customer_id.notna().all()


def test_los_conteos_no_son_negativos(df):
    conteos = [
        c for c in df.columns if c.startswith(("tx_", "n_", "quejas_", "meses_", "canales_"))
    ]
    for c in conteos:
        v = df[c].dropna()
        if v.dtype.kind in "if":
            assert (v >= 0).all(), f"{c} tiene valores negativos"


def test_las_razones_estan_acotadas(df):
    """`razon_salidas` es una proporción: fuera de [0, 1] indica un error de signo."""
    v = df.razon_salidas.dropna()
    if len(v):
        assert (v >= 0).all() and (v <= 1.0001).all(), (
            f"razon_salidas fuera de [0,1]: min {v.min():.4f}, max {v.max():.4f}"
        )


def test_sin_actividad_coincide_con_cero_transacciones(df):
    assert (df.sin_actividad_180d == (df.tx_180d == 0).astype(int)).all()


# ── Constantes del contrato ──────────────────────────────────────────────────


def test_el_umbral_de_mora_es_el_estandar():
    assert DIAS_MORA == 90, "90 días es el estándar de Basilea; cambiarlo exige un ADR."


def test_los_productos_de_credito_estan_declarados():
    assert set(PRODUCTOS_DE_CREDITO) == {
        "Tarjeta Crédito",
        "Préstamo Personal",
        "Préstamo Hipotecario",
    }


def test_el_corte_esta_documentado():
    adr = Path("docs/decisions/ADR-0004-corte-temporal-y-fuga.md")
    assert adr.exists(), "El corte es un supuesto: tiene que estar escrito en el ADR-0004."
    assert CORTE_POR_DEFECTO == date(2025, 12, 31)
