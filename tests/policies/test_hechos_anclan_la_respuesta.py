"""Toda cifra que el motor pronuncia tiene que estar publicada en `hechos`.

Es el contrato con el `GroundingChecker` (AG-09) visto desde el otro lado. AG-09
bloquea una respuesta cuando contiene una cifra que no devolvió ningún tool de ese
turno; las cifras de una decisión de crédito salen de `Decision.hechos` y de
`Oferta`. Si el motor dice un número en un `motivo` o un `aviso` y no lo publica en
`hechos`, AG-09 bloquearía una respuesta **correcta** — un falso positivo que en la
demo parece un bug del guardrail y en realidad es un hueco del motor.

Esto ya pasó: `reservas_meses_carga` y `exposicion / (ingreso * 12)` se
pronunciaban sin publicarse. Esta prueba existe para que no vuelva a pasar.

Nota de diseño para AG-09: los mensajes traen las cifras **formateadas** —`{dti:.0%}`
convierte 0.4012 en «40%», `{carga:,.0f}` convierte 1234.56 en «1,235»—. El
checker no puede comparar flotantes: tiene que comparar *renderizados*. El
`formatos_posibles` de abajo es el prototipo mínimo de ese emparejamiento.
"""

from __future__ import annotations

import re
from datetime import date

from agent.policies.engine import (
    Cliente,
    Politica,
    ProductoDeAhorro,
    ProductoVigente,
    cifra,
)

CORTE = date(2025, 12, 31)

# Números dentro del texto, con separador de miles y decimales opcionales.
NUMERO = re.compile(r"\d[\d,]*(?:\.\d+)?")


def formatos_posibles(valor: float) -> set[str]:
    """Las formas en que el motor puede renderizar un valor numérico.

    Incluye las que produce `cifra()`, que es la convención hispanohablante que el motor
    usa de verdad —punto para los miles, coma para los decimales— y no la de Python
    (F-045). Se llama al helper real en vez de replicar su lógica: si cambia, la prueba
    lo sigue.
    """
    formas = set()
    for plantilla in ("{:.0%}", "{:.1%}", "{:,.0f}", "{:,.2f}", "{:.0f}", "{:.1f}", "{:.2f}"):
        try:
            formas.add(plantilla.format(valor).rstrip("%"))
        except (ValueError, TypeError):
            continue
    for decimales in (0, 1, 2):
        formas.add(cifra(valor, decimales))
    formas.add(str(valor))
    if isinstance(valor, float) and valor.is_integer():
        formas.add(str(int(valor)))
    return formas


def anclas(decision, politica: Politica) -> set[str]:
    """El conjunto permitido: hechos ∪ campos de Oferta ∪ umbrales de la política.

    Los umbrales entran porque un motivo honesto dice las dos cifras —la del
    cliente y la que debía alcanzar— y la segunda es la política, no el cliente.
    """
    valores: list[float] = []

    def recolectar(nodo) -> None:
        """Baja por dicts y listas: `evaluacion_por_producto` es anidado."""
        if isinstance(nodo, bool):
            return
        if isinstance(nodo, (int, float)):
            valores.append(float(nodo))
        elif isinstance(nodo, dict):
            for v in nodo.values():
                recolectar(v)
        elif isinstance(nodo, (list, tuple)):
            for v in nodo:
                recolectar(v)

    recolectar(decision.hechos)
    for oferta in decision.productos_elegibles:
        recolectar(vars(oferta))
    recolectar(politica.u)
    recolectar(politica.reservas_minimas)
    recolectar([item for item in politica.catalogo])
    valores.append(float(politica.comp_dti_ampliado))
    valores.append(float(politica.comp_reservas_meses))

    permitidos: set[str] = set()
    for v in valores:
        permitidos |= formatos_posibles(v)
    return permitidos


def huerfanas(decision, politica: Politica) -> set[str]:
    """Cifras pronunciadas que no están ancladas. Debe ser vacío siempre."""
    permitidos = anclas(decision, politica)
    sueltas = set()
    for texto in [*decision.motivos, *decision.avisos]:
        for bruto in NUMERO.findall(texto):
            limpio = bruto.replace(",", "")
            if bruto in permitidos or limpio in permitidos:
                continue
            # Un entero suelto puede venir de un umbral entero renderizado.
            if limpio.rstrip(".0") and any(limpio == f.replace(",", "") for f in permitidos):
                continue
            sueltas.add(bruto)
    return sueltas


# ─────────────────────────────────────────────────────────────────────────────
# Clientes que recorren cada rama con cifras en el mensaje
# ─────────────────────────────────────────────────────────────────────────────


def tarjeta(limite=10000.0, saldo=5000.0, apertura=date(2020, 1, 1), **kw):
    base = dict(
        tipo="Tarjeta Crédito",
        limite_usd=limite,
        tasa_anual=31.52,
        apertura=apertura,
        saldo_usd=saldo,
    )
    return ProductoVigente(**{**base, **kw})


def cliente(**kw):
    base = dict(
        customer_id="C1",
        ingreso_mensual_usd=3000.0,
        segmento="Plus",
        alta=date(2015, 1, 1),
    )
    return Cliente(**{**base, **kw})


def test_cliente_elegible_no_pronuncia_cifras_huerfanas():
    politica = Politica.cargar()
    d = politica.evaluar(cliente(productos=(tarjeta(),)))
    assert huerfanas(d, politica) == set()


def test_rechazo_por_dti_no_pronuncia_cifras_huerfanas():
    """R3: carga altísima contra ingreso bajo. El motivo dice DTI y umbral."""
    politica = Politica.cargar()
    d = politica.evaluar(
        cliente(ingreso_mensual_usd=400.0, productos=(tarjeta(limite=90000.0, saldo=80000.0),))
    )
    assert d.elegible is False
    assert d.motivos, "se esperaba un motivo con cifras"
    assert huerfanas(d, politica) == set()


def test_rechazo_por_exposicion_publica_veces_ingreso():
    """R4 pronuncia `exposicion / (ingreso * 12)`. Tiene que estar en `hechos`."""
    politica = Politica.cargar()
    d = politica.evaluar(
        cliente(
            ingreso_mensual_usd=1500.0,
            productos=(
                tarjeta(limite=40000.0, saldo=1000.0),
                tarjeta(limite=40000.0, saldo=1000.0),
            ),
        )
    )
    assert "veces_ingreso_exposicion" in d.hechos
    assert huerfanas(d, politica) == set()


def test_compensacion_por_reservas_publica_meses_de_carga():
    """El aviso de compensación pronuncia `reservas_meses_carga`."""
    politica = Politica.cargar()
    d = politica.evaluar(
        cliente(
            productos=(tarjeta(limite=10000.0, saldo=4000.0),),
            ahorros=(ProductoDeAhorro(tipo="Cuenta Ahorro", saldo_usd=60000.0),),
        )
    )
    assert "reservas_meses_carga" in d.hechos
    assert huerfanas(d, politica) == set()


def test_abstencion_por_falta_de_ingreso_no_inventa_cifras():
    politica = Politica.cargar()
    d = politica.evaluar(cliente(ingreso_mensual_usd=None))
    assert d.abstencion is True
    assert huerfanas(d, politica) == set()


def test_los_dos_hechos_derivados_coinciden_con_el_calculo():
    """No basta con que la clave exista: tiene que valer lo que el motor dice."""
    politica = Politica.cargar()
    c = cliente(
        ingreso_mensual_usd=2000.0,
        productos=(tarjeta(limite=30000.0, saldo=10000.0),),
        ahorros=(ProductoDeAhorro(tipo="Cuenta Ahorro", saldo_usd=9000.0),),
    )
    d = politica.evaluar(c)
    esperado_veces = d.hechos["exposicion_usd"] / (d.hechos["ingreso_mensual_usd"] * 12)
    assert d.hechos["veces_ingreso_exposicion"] == round(esperado_veces, 4)
    esperado_meses = d.hechos["reservas_usd"] / d.hechos["carga_mensual_usd"]
    assert d.hechos["reservas_meses_carga"] == round(esperado_meses, 2)
