"""La extracción de slots — `API-01`.

Es la única pieza donde el lenguaje entra al sistema, así que es donde se cuelan los
errores de interpretación. Cada prueba de acá corresponde a una forma real de escribir
que se vio en el dataset o en las pruebas manuales.
"""

from __future__ import annotations

import pytest

from api.extraccion import _a_numero, detectar_idioma, extraer


# ── importes escritos a la latinoamericana ──────────────────────────────────
@pytest.mark.parametrize(
    ("escrito", "esperado"),
    [
        ("3000", 3000.0),
        ("3 000", 3000.0),
        # Mil quinientos, no uno punto cinco: el último separador deja tres dígitos.
        ("1.500", 1500.0),
        ("1,500", 1500.0),
        ("40.000", 40000.0),
        # Dos decimales: ahí el separador sí es decimal.
        ("1500.50", 1500.50),
        ("1500,50", 1500.50),
        ("1.500.000", 1500000.0),
    ],
)
def test_un_importe_se_lee_igual_escrito_de_cualquiera_de_las_formas(escrito, esperado):
    assert _a_numero(escrito) == pytest.approx(esperado)


def test_un_importe_ilegible_no_se_adivina():
    assert _a_numero("") is None
    assert _a_numero("mil") is None


# ── intención ───────────────────────────────────────────────────────────────
def test_pedir_un_monto_es_una_solicitud_de_elegibilidad():
    r = extraer("Quisiera un préstamo personal de 3000 dólares.")
    assert r["intencion"] == "CREDIT_ELIGIBILITY"
    assert r["slots"]["requested_amount"] == 3000.0
    assert r["slots"]["currency"] == "USD"
    assert r["slots"]["product_type"] == "Préstamo Personal"


def test_preguntar_condiciones_no_es_pedir_un_credito():
    r = extraer("Quisiera saber las condiciones de la tarjeta de crédito.")
    assert r["intencion"] == "PRODUCT_INFO"
    assert "requested_amount" not in r["slots"]


def test_pedir_una_persona_se_detecta_aunque_venga_con_otra_cosa():
    r = extraer("Quiero un préstamo de 5000 dólares, pero prefiero hablar con un asesor.")
    assert r["pide_humano"] is True


def test_algo_fuera_del_workflow_queda_como_desconocido():
    assert extraer("Quiero cambiar mi dirección postal.")["intencion"] == "DESCONOCIDA"


def test_un_numero_pequeno_no_es_un_monto_de_credito():
    """48 es un plazo y 3 es una cantidad de productos. Confundirlos daba cuotas absurdas."""
    r = extraer("Tengo 3 productos y quiero saber las condiciones a 48 meses.")
    assert "requested_amount" not in r["slots"]


def test_si_no_se_nombra_moneda_se_asume_y_se_declara():
    r = extraer("Necesito un préstamo personal de 8000.")
    assert r["slots"]["currency"] == "USD"
    assert r["supuestos"], "un supuesto que no se declara es una cifra inventada"


def test_una_moneda_nombrada_gana_sobre_el_supuesto():
    r = extraer("Necesito un préstamo personal de 8000000 pesos colombianos.")
    assert r["slots"]["currency"] == "COP"
    assert not r["supuestos"]


# ── idioma ──────────────────────────────────────────────────────────────────
def test_se_distingue_portugues_de_espanol():
    assert detectar_idioma("Olá, bom dia. Gostaria de um empréstimo pessoal.") == "pt"
    assert detectar_idioma("Hola, buenos días. Quisiera un préstamo personal.") == "es"


def test_el_pronombre_adosado_del_espanol_no_rompe_la_lectura():
    """«muéstrame» lleva el pronombre pegado y la tilde movida (F-041)."""
    r = extraer("Muéstrame las condiciones del préstamo hipotecario.")
    assert r["slots"]["product_type"] == "Préstamo Hipotecario"


def test_el_hipotecario_gana_sobre_el_personal_cuando_se_nombra():
    assert (
        extraer("Quiero un crédito hipotecario de 50000 dólares.")["slots"]["product_type"]
        == "Préstamo Hipotecario"
    )
