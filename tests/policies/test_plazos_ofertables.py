"""Varios plazos por producto — política versión 2.

Nace de una objeción de Eduardo al validar el catálogo: con las tasas observadas se
le puede dar al cliente tres opciones moviendo el plazo, **sin cambiar la TEA del
producto**, para que elija según su capacidad de pago.

Las dos propiedades financieras que estas pruebas fijan:

1. **La TEA no depende del plazo.** El motor amortiza con `i = tasa_anual/100/12`,
   así que la efectiva es `(1+i)^12 − 1` y el plazo no entra. Si alguien cambiara la
   convención de capitalización, esta prueba lo detecta.
2. **El plazo largo no es gratis.** Más plazo baja la cuota y sube el interés total.
   La oferta declara las dos cifras, porque mostrar solo la cuota haría parecer que
   alargar el plazo no cuesta nada.
"""

from __future__ import annotations

from datetime import date

import pytest

from agent.policies.engine import (
    Cliente,
    Politica,
    ProductoDeAhorro,
    ProductoVigente,
    cifra,
    cuota_francesa,
    tea_desde_nominal,
)

CORTE = date(2025, 12, 31)
FIJA = ("Préstamo Personal", "Préstamo Hipotecario")


@pytest.fixture
def politica():
    return Politica.cargar()


def cliente(**kw):
    """Cliente holgado y con reservas: así ningún producto cae por otra regla.

    Lleva `capacidad_estimada_usd` deliberadamente alta: estas pruebas miden el efecto
    del **plazo**, y sin capacidad observada la política recorta el margen y excluye el
    hipotecario (v3). Eso se prueba aparte, en `test_sin_capacidad_observada.py`; acá
    estorbaría.
    """
    base = dict(
        customer_id="C1",
        ingreso_mensual_usd=4000.0,
        segmento="Premium",
        alta=date(2015, 1, 1),
        ahorros=(ProductoDeAhorro(tipo="Cuenta Ahorro", saldo_usd=8000.0),),
        capacidad_estimada_usd=1_000_000.0,
    )
    return Cliente(**{**base, **kw})


def ofertas_de(decision, producto):
    return sorted(
        (o for o in decision.productos_elegibles if o.producto == producto),
        key=lambda o: o.plazo_meses,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1 · La TEA, que es el punto de la objeción
# ─────────────────────────────────────────────────────────────────────────────


def test_la_tea_no_depende_del_plazo(politica):
    for item in politica.catalogo:
        teas = {round(tea_desde_nominal(item["tasa_anual"]), 10) for _ in item["plazos_ofertables"]}
        assert len(teas) == 1


def test_la_tea_sale_de_capitalizacion_mensual():
    """31.52 % nominal mensual es 36.50 % efectiva. Fija la convención."""
    assert tea_desde_nominal(31.52) == pytest.approx(36.4969, abs=1e-3)
    assert tea_desde_nominal(20.10) == pytest.approx(22.0591, abs=1e-3)
    assert tea_desde_nominal(8.98) == pytest.approx(9.3590, abs=1e-3)
    # Una nominal con capitalización mensual siempre es menor que su efectiva.
    for nominal in (6.0, 12.0, 31.52, 45.0):
        assert tea_desde_nominal(nominal) > nominal
    assert tea_desde_nominal(0.0) == 0.0


def test_todas_las_ofertas_de_un_producto_llevan_la_misma_tea(politica):
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    for producto in FIJA:
        ofs = ofertas_de(d, producto)
        assert len(ofs) >= 2
        assert len({o.tea_pct for o in ofs}) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 2 · Tres opciones por capacidad: la cuota es lo que cambia
# ─────────────────────────────────────────────────────────────────────────────


def test_con_monto_pedido_la_cuota_baja_y_el_interes_sube(politica):
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    for producto in FIJA:
        ofs = ofertas_de(d, producto)
        assert len(ofs) == 3, f"{producto}: se esperaban tres opciones"
        cuotas = [o.cuota_estimada_usd for o in ofs]
        intereses = [o.intereses_totales_usd for o in ofs]
        assert len(set(cuotas)) == 3, "las tres cuotas deben diferir"
        assert cuotas == sorted(cuotas, reverse=True), "más plazo, menos cuota"
        assert intereses == sorted(intereses), "más plazo, más interés total"
        assert len(set(intereses)) == 3
        assert all(o.monto_ofrecido_usd == 30000.0 for o in ofs)


def test_sin_monto_pedido_cada_plazo_cotiza_su_techo(politica):
    """Sin monto pedido la cuota agota el margen en todos los plazos: las opciones
    difieren en monto, no en cuota. Es la otra lectura, y se conserva."""
    d = politica.evaluar(cliente())
    ofs = ofertas_de(d, "Préstamo Personal")
    assert len(ofs) == 3
    montos = [o.monto_ofrecido_usd for o in ofs]
    assert montos == sorted(montos) and len(set(montos)) == 3
    assert all(o.monto_ofrecido_usd == o.monto_maximo_usd for o in ofs)


def test_el_interes_total_cuadra_con_la_cuota_y_el_plazo(politica):
    """No basta con que crezca: tiene que ser cuota × plazo − principal."""
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    for o in d.productos_elegibles:
        if o.intereses_totales_usd is None:
            continue
        esperado = o.cuota_estimada_usd * o.plazo_meses - o.monto_ofrecido_usd
        assert o.intereses_totales_usd == pytest.approx(esperado, abs=1.0)


def test_la_cuota_cuadra_con_la_amortizacion_francesa(politica):
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    for o in d.productos_elegibles:
        if o.producto == "Tarjeta Crédito":
            continue
        esperado = cuota_francesa(o.monto_ofrecido_usd, o.tasa_anual, o.plazo_meses)
        assert o.cuota_estimada_usd == pytest.approx(esperado, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# 3 · La tarjeta es revolvente: un solo plazo, sin interés total
# ─────────────────────────────────────────────────────────────────────────────


def test_la_tarjeta_lleva_un_solo_plazo(politica):
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    assert len(ofertas_de(d, "Tarjeta Crédito")) == 1


def test_el_revolvente_no_declara_interes_total(politica):
    """Una línea no tiene un total que devolver: inventarlo sería una cifra falsa."""
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    tarjeta = ofertas_de(d, "Tarjeta Crédito")[0]
    assert tarjeta.intereses_totales_usd is None


def test_la_cuota_de_la_tarjeta_es_el_pago_minimo(politica):
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    tarjeta = ofertas_de(d, "Tarjeta Crédito")[0]
    assert tarjeta.cuota_estimada_usd == pytest.approx(30000.0 * politica.pago_minimo_pct)


# ─────────────────────────────────────────────────────────────────────────────
# 4 · Lo que la objeción desbloquea: rechazos que pasan a ser ofertas
# ─────────────────────────────────────────────────────────────────────────────


def test_un_plazo_mas_largo_amplia_el_monto_que_cabe(politica):
    """Es el mecanismo por el que un plazo largo convierte un rechazo en oferta."""
    d = politica.evaluar(cliente())
    opciones = d.hechos["evaluacion_por_producto"]["Préstamo Hipotecario"]["opciones"]
    techos = [opciones[k]["monto_maximo_usd"] for k in sorted(opciones, key=int)]
    assert techos == sorted(techos) and len(set(techos)) == 3


def test_el_rechazo_cita_el_plazo_mas_largo(politica):
    """Si ni el plazo más largo alcanza, el motivo lo dice: no queda a qué recurrir."""
    pobre = cliente(ingreso_mensual_usd=900.0, ahorros=(), capacidad_estimada_usd=1_000_000.0)
    d = politica.evaluar(pobre)
    motivos = " ".join(d.motivos)
    assert "el plazo más largo que ofrecemos" in motivos
    assert "240 meses" in motivos  # el más largo del hipotecario


def test_un_producto_de_un_solo_plazo_no_habla_de_plazo_mas_largo(politica):
    """La tarjeta tiene un plazo: decir «el más largo» sería ruido."""
    sin_margen = Cliente(
        customer_id="C9",
        # Margen de 23 USD: el techo de la línea (460) no llega al mínimo de 500.
        ingreso_mensual_usd=620.0,
        segmento="Student",  # solo tarjeta
        alta=date(2015, 1, 1),
        capacidad_estimada_usd=1_000_000.0,
        productos=(
            ProductoVigente(
                tipo="Tarjeta Crédito",
                limite_usd=9000.0,
                tasa_anual=31.52,
                apertura=date(2020, 1, 1),
                saldo_usd=4000.0,
            ),
        ),
    )
    d = politica.evaluar(sin_margen)
    assert not d.productos_elegibles
    assert "el plazo más largo" not in " ".join(d.motivos)


# ─────────────────────────────────────────────────────────────────────────────
# 5 · El monto pedido: validación y honestidad
# ─────────────────────────────────────────────────────────────────────────────


def test_pedir_menos_que_el_minimo_lo_dice_sin_hablar_de_plazos(politica):
    d = politica.evaluar(cliente(), monto_pedido_usd=1200.0)
    hipotecario = [m for m in d.motivos if m.startswith("Préstamo Hipotecario")]
    assert hipotecario
    assert "el mínimo de este producto es" in hipotecario[0]
    assert "plazo más largo" not in hipotecario[0]


def test_cotizar_menos_de_lo_pedido_se_declara(politica):
    """Cotizar 178 000 ante una petición de 400 000 sin decirlo dejaría al cliente
    creyendo que recibió lo que pidió."""
    d = politica.evaluar(cliente(), monto_pedido_usd=400000.0)
    assert d.productos_elegibles
    avisos = " ".join(d.avisos)
    for producto in (*FIJA, "Tarjeta Crédito"):
        assert f"{producto}: pediste {cifra(400000.0)} USD" in avisos


def test_no_se_avisa_recorte_cuando_se_cotiza_lo_pedido(politica):
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    assert not any("podemos ofrecerte hasta" in a for a in d.avisos)


@pytest.mark.parametrize("malo", [0.0, -1.0, float("nan"), float("inf"), True])
def test_un_monto_pedido_invalido_abstiene(politica, malo):
    d = politica.evaluar(cliente(), monto_pedido_usd=malo)
    assert d.abstencion is True
    assert not d.productos_elegibles


def test_el_monto_pedido_queda_publicado_en_hechos(politica):
    """Si el agente va a pronunciar la cifra, tiene que estar anclada (AG-09)."""
    d = politica.evaluar(cliente(), monto_pedido_usd=30000.0)
    assert d.hechos["monto_pedido_usd"] == 30000.0
    sin = politica.evaluar(cliente())
    assert "monto_pedido_usd" not in sin.hechos


# ─────────────────────────────────────────────────────────────────────────────
# 6 · Compatibilidad con la forma de la versión 1
# ─────────────────────────────────────────────────────────────────────────────


def test_se_acepta_un_catalogo_con_plazo_unico(politica):
    """Una política anterior, con `plazo_meses` en vez de la lista, sigue corriendo."""
    assert politica._plazos_ofertables({"producto": "X", "plazo_meses": 48}) == [48]


def test_los_plazos_se_ordenan_y_se_deduplican(politica):
    item = {"producto": "X", "plazos_ofertables": [72, 24, 48, 24]}
    assert politica._plazos_ofertables(item) == [24, 48, 72]


@pytest.mark.parametrize("plazos", [[], [0], [-12, 48]])
def test_un_plazo_invalido_no_pasa_en_silencio(politica, plazos):
    with pytest.raises(ValueError, match="plazos ofertables inválidos"):
        politica._plazos_ofertables({"producto": "X", "plazos_ofertables": plazos})
