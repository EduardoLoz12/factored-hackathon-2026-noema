"""Sin capacidad de pago observada, la política restringe — política v3.

Nace de una objeción de Eduardo al validar la deuda del estimador: que ML-04 no entregue
una cifra **no puede ser neutro**, porque «afecta su capacidad de pago y patrimonio».

El defecto era del mismo tipo que F-041 y es la **tercera** vez que aparece el patrón:
el motor usaba el margen COMPLETO cuando no había capacidad observada, es decir trataba
la ausencia de información como ausencia de restricción, y el dato que no está volvía a
caer a favor del solicitante.

Dos efectos, los dos declarados en la respuesta:

1. **Recorte del margen** por `factor_margen`. No estima nada: es la prudencia de no
   prestar al tope de un cálculo que no se pudo cruzar contra flujo real.
2. **Exclusión de los productos de plazo largo.** Comprometer 240 meses sin haber visto
   el flujo del cliente es justo lo que no se debe hacer.
"""

from __future__ import annotations

from datetime import date

import pytest

from agent.policies.engine import Cliente, Politica, ProductoDeAhorro, ProductoVigente

CORTE = date(2025, 12, 31)
HOLGADA = 1_000_000.0


@pytest.fixture
def politica():
    return Politica.cargar()


def cliente(**kw):
    """Premium con reservas: sin esto el hipotecario caería por reservas, no por capacidad."""
    base = dict(
        customer_id="C1",
        ingreso_mensual_usd=6000.0,
        segmento="Premium",
        alta=date(2015, 1, 1),
        ahorros=(
            ProductoDeAhorro(tipo="Cuenta Ahorro", saldo_usd=40_000.0),
            ProductoDeAhorro(tipo="Inversión", saldo_usd=40_000.0),
        ),
    )
    return Cliente(**{**base, **kw})


# ═════════════════════════════════════════════════════════════════════════════
# 1 · El recorte del margen
# ═════════════════════════════════════════════════════════════════════════════


def test_sin_capacidad_el_margen_se_recorta(politica):
    con = politica.evaluar(cliente(capacidad_estimada_usd=HOLGADA))
    sin = politica.evaluar(cliente())
    esperado = con.hechos["margen_mensual_usd"] * politica.sc_factor
    assert sin.hechos["margen_mensual_usd"] == pytest.approx(esperado, abs=0.01)
    assert sin.hechos["margen_mensual_usd"] < con.hechos["margen_mensual_usd"]


def test_el_factor_del_recorte_sale_del_yaml(politica):
    """Es decisión de negocio en un archivo versionado, no una constante en el código."""
    assert 0 < politica.sc_factor < 1


def test_una_capacidad_observada_baja_sigue_mandando(politica):
    """El recorte no sustituye a la capacidad: cuando hay cifra, manda la cifra."""
    d = politica.evaluar(cliente(capacidad_estimada_usd=150.0))
    assert d.hechos["margen_mensual_usd"] == pytest.approx(150.0)


def test_el_recorte_no_se_aplica_dos_veces(politica):
    """Con capacidad observada no hay recorte, ni siquiera si la capacidad es alta."""
    con = politica.evaluar(cliente(capacidad_estimada_usd=HOLGADA))
    tope = politica.u["dti_maximo"] * 6000.0
    assert con.hechos["margen_mensual_usd"] == pytest.approx(tope, abs=0.01)


# ═════════════════════════════════════════════════════════════════════════════
# 2 · La exclusión de productos
# ═════════════════════════════════════════════════════════════════════════════


def test_sin_capacidad_no_se_ofrece_el_plazo_mas_largo(politica):
    sin = politica.evaluar(cliente())
    ofrecidos = {o.producto for o in sin.productos_elegibles}
    assert politica.sc_excluidos, "el YAML debe declarar qué se excluye"
    assert not (ofrecidos & politica.sc_excluidos)


def test_con_capacidad_el_producto_excluido_vuelve(politica):
    """La exclusión es por la ausencia del dato, no por el producto."""
    con = politica.evaluar(cliente(capacidad_estimada_usd=HOLGADA))
    ofrecidos = {o.producto for o in con.productos_elegibles}
    assert politica.sc_excluidos <= ofrecidos


def test_la_exclusion_se_explica_al_cliente(politica):
    """Un rechazo sin motivo no es una respuesta."""
    sin = politica.evaluar(cliente())
    for producto in politica.sc_excluidos:
        assert any(m.startswith(producto) and "flujo de ingresos" in m for m in sin.motivos), (
            f"falta el motivo de {producto}"
        )


def test_los_productos_de_plazo_corto_siguen_disponibles(politica):
    """Restringir no es cerrar: la tarjeta y el personal se siguen ofreciendo."""
    sin = politica.evaluar(cliente())
    ofrecidos = {o.producto for o in sin.productos_elegibles}
    assert "Tarjeta Crédito" in ofrecidos
    assert "Préstamo Personal" in ofrecidos


# ═════════════════════════════════════════════════════════════════════════════
# 3 · Lo que se declara
# ═════════════════════════════════════════════════════════════════════════════


def test_se_declara_el_criterio_conservador(politica):
    sin = politica.evaluar(cliente())
    assert any("criterio más conservador" in a for a in sin.avisos)
    assert any("capacidad de pago observada" in a for a in sin.avisos)


def test_con_capacidad_no_se_declara_lo_que_no_pasa(politica):
    con = politica.evaluar(cliente(capacidad_estimada_usd=HOLGADA))
    assert not any("criterio más conservador" in a for a in con.avisos)


def test_los_hechos_dicen_si_hubo_capacidad_observada(politica):
    """El panel y el expediente tienen que poder distinguir los dos casos."""
    assert politica.evaluar(cliente()).hechos["capacidad_observada"] is False
    assert (
        politica.evaluar(cliente(capacidad_estimada_usd=HOLGADA)).hechos["capacidad_observada"]
        is True
    )


# ═════════════════════════════════════════════════════════════════════════════
# 4 · El patrimonio neto, como hecho declarado
# ═════════════════════════════════════════════════════════════════════════════


def test_el_patrimonio_neto_se_publica(politica):
    """Eduardo nombró el patrimonio además de la capacidad. Se publica como hecho;
    **no** hay umbral de patrimonio en esta versión, y poner uno sin que el negocio lo
    fije sería inventar un criterio."""
    d = politica.evaluar(cliente())
    assert "patrimonio_neto_usd" in d.hechos
    assert "saldo_dispuesto_usd" in d.hechos


def test_el_patrimonio_es_reservas_menos_lo_dispuesto(politica):
    d = politica.evaluar(
        cliente(
            productos=(
                ProductoVigente(
                    tipo="Tarjeta Crédito",
                    limite_usd=20_000.0,
                    tasa_anual=31.52,
                    apertura=date(2021, 1, 1),
                    ultima_transaccion_real=CORTE,
                    saldo_usd=5_000.0,
                ),
            )
        )
    )
    assert d.hechos["saldo_dispuesto_usd"] == pytest.approx(5_000.0)
    esperado = d.hechos["reservas_usd"] - d.hechos["saldo_dispuesto_usd"]
    assert d.hechos["patrimonio_neto_usd"] == pytest.approx(esperado, abs=0.01)


def test_un_patrimonio_negativo_no_bloquea_todavia(politica):
    """Se declara y no decide. Si el negocio quiere un umbral, va al YAML y sube versión."""
    d = politica.evaluar(
        cliente(
            ahorros=(ProductoDeAhorro(tipo="Cuenta Ahorro", saldo_usd=100.0),),
            productos=(
                ProductoVigente(
                    tipo="Tarjeta Crédito",
                    limite_usd=20_000.0,
                    tasa_anual=31.52,
                    apertura=date(2021, 1, 1),
                    ultima_transaccion_real=CORTE,
                    saldo_usd=9_000.0,
                ),
            ),
            capacidad_estimada_usd=HOLGADA,
        )
    )
    assert d.hechos["patrimonio_neto_usd"] < 0
    assert d.abstencion is False


def test_el_patrimonio_queda_anclado_para_el_grounding(politica):
    """Si el agente va a pronunciar la cifra, tiene que estar en `hechos` (F-037)."""
    d = politica.evaluar(cliente())
    for clave in ("patrimonio_neto_usd", "saldo_dispuesto_usd", "capacidad_observada"):
        assert clave in d.hechos


# ═════════════════════════════════════════════════════════════════════════════
# 5 · La versión de la política
# ═════════════════════════════════════════════════════════════════════════════


def test_la_version_subio_porque_el_comportamiento_cambio(politica):
    """A diferencia de retirar R6 —texto muerto, versión intacta—, esto sí cambia lo
    que el sistema decide."""
    assert politica.version >= 3
