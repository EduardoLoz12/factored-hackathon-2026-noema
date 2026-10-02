"""Las cifras que el cliente lee usan la convención de su región — F-045.

`{:,.0f}` de Python produce «1,200», que en es-CO, es-AR, es-MX y pt-BR se lee *uno coma
dos*. En un agente bancario regional eso no es cosmético: el cliente puede leer **mil
veces menos** de lo que se le está diciendo, y «tus cuotas actuales de 1,200 USD» pasa a
sonar perfectamente asumible.

Las dos lenguas del proyecto comparten la convención —punto para los miles, coma para los
decimales— así que no hace falta ramificar por idioma.

La prueba que más vale de este archivo es la última: recorre el motor y falla si alguien
vuelve a interpolar un importe con el formato de Python.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from agent.policies.engine import Cliente, Politica, ProductoDeAhorro, ProductoVigente, cifra

# ═════════════════════════════════════════════════════════════════════════════
# El formateador
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("valor", "decimales", "esperado"),
    [
        (1200.0, 0, "1.200"),
        (1234.56, 0, "1.235"),
        (90000.0, 0, "90.000"),
        (178086.0, 0, "178.086"),
        (1234567.0, 0, "1.234.567"),
        (3.0, 1, "3,0"),
        # Python redondea a la media par: 6.25 da 6,2 y no 6,3.
        (6.25, 1, "6,2"),
        (288.35, 2, "288,35"),
        (0.0, 0, "0"),
        (-80000.0, 0, "-80.000"),
    ],
)
def test_la_convencion_es_punto_para_miles_y_coma_para_decimales(valor, decimales, esperado):
    assert cifra(valor, decimales) == esperado


def test_el_intercambio_no_se_pisa_a_si_mismo():
    """Sustituir un símbolo y después el otro dejaría todo con el mismo. Con un valor que
    lleva los dos separadores se ve si el intercambio está bien hecho."""
    assert cifra(1234567.89, 2) == "1.234.567,89"


def test_un_entero_no_arrastra_coma_decimal():
    assert cifra(48.0, 0) == "48"


# ═════════════════════════════════════════════════════════════════════════════
# Lo que el cliente lee
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def politica():
    return Politica.cargar()


def test_un_importe_en_un_motivo_sale_con_punto(politica):
    """El caso que originó el arreglo: «1,200 USD» en una frase en español."""
    d = politica.evaluar(
        Cliente(
            customer_id="C",
            ingreso_mensual_usd=4000.0,
            segmento="Premium",
            alta=date(2015, 1, 1),
            capacidad_estimada_usd=1e9,
            productos=(
                ProductoVigente(
                    tipo="Tarjeta Crédito",
                    limite_usd=50000.0,
                    tasa_anual=31.52,
                    apertura=date(2020, 1, 1),
                    ultima_transaccion_real=date(2025, 12, 1),
                    saldo_usd=40000.0,
                ),
            ),
        )
    )
    texto = " ".join([*d.motivos, *d.avisos])
    assert re.search(r"\d\.\d{3}", texto), "se esperaba al menos un importe con punto de miles"
    assert not re.search(r"\d,\d{3}\b", texto), "quedó un separador de miles con coma"


def test_un_aviso_de_recorte_sale_con_punto(politica):
    d = politica.evaluar(
        Cliente(
            customer_id="C",
            ingreso_mensual_usd=6000.0,
            segmento="Premium",
            alta=date(2015, 1, 1),
            capacidad_estimada_usd=1e9,
            ahorros=(ProductoDeAhorro(tipo="Cuenta Ahorro", saldo_usd=80000.0),),
        ),
        monto_pedido_usd=400000.0,
    )
    avisos = " ".join(d.avisos)
    assert f"pediste {cifra(400000.0)} USD" in avisos
    assert "400,000" not in avisos


def test_el_multiplo_de_ingreso_sale_con_coma_decimal(politica):
    """«6,2 veces tu ingreso», no «6.2»."""
    d = politica.evaluar(
        Cliente(
            customer_id="C",
            ingreso_mensual_usd=1500.0,
            segmento="Premium",
            alta=date(2015, 1, 1),
            capacidad_estimada_usd=1e9,
            productos=(
                ProductoVigente(
                    tipo="Tarjeta Crédito",
                    limite_usd=80000.0,
                    tasa_anual=31.52,
                    apertura=date(2020, 1, 1),
                    ultima_transaccion_real=date(2025, 12, 1),
                    saldo_usd=1000.0,
                ),
            ),
        )
    )
    motivos = " ".join(d.motivos)
    if "veces tu ingreso" in motivos:
        assert re.search(r"\d,\d veces", motivos), f"formato decimal inglés en: {motivos}"


# ═════════════════════════════════════════════════════════════════════════════
# La guarda contra la regresión
# ═════════════════════════════════════════════════════════════════════════════


def test_ningun_mensaje_del_motor_usa_el_formato_de_python():
    """Falla si alguien vuelve a interpolar un importe con `{:,.0f}`.

    Es la prueba que impide que esto se revierta por descuido en el próximo mensaje que
    se agregue. La mención en la documentación del formateador no cuenta: se filtra por
    líneas que son f-string."""
    fuente = Path("agent/policies/engine.py").read_text(encoding="utf-8")
    ofensores = [
        (i + 1, ln.strip())
        for i, ln in enumerate(fuente.splitlines())
        # Se excluye la línea del propio `cifra()`: es la implementación, no un mensaje.
        if ":,." in ln and 'f"' in ln and "{decimales}" not in ln
    ]
    assert not ofensores, f"usar cifra() en vez del formato de Python: {ofensores}"
