"""Catálogo, evidencia de pago y decisión — AG-04, tools 5 a 8.

Base en memoria con el esquema real. Las transacciones del fixture están construidas
para ejercitar los tres filtros de coherencia de F-042, que no son defensivos: cambian
el veredicto activo/inactivo en el 9.07 % de los productos de crédito reales.

Lo que más importa acá: **`evaluate_eligibility` no consulta la base**. Consume la
evidencia que el orquestador recogió tool por tool. Si volviera a leer, podría usar
filtros distintos a los que la traza muestra y el anclaje de AG-09 dejaría de ser
comprobable sobre las cifras que el jurado ve.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from agent.policies.engine import Politica
from agent.tools import credit as mod
from agent.tools.registry import Role, Session, ToolDenied, ToolRegistry, TurnValues
from agent.tools.store import (
    AnalyticsStore,
    Capacidad,
    Contexto,
    Evidencia,
    MotivoCapacidad,
)

CORTE = date(2025, 12, 31)
P_CARD = "PRD-CARD"
P_LOAN = "PRD-LOAN"


@pytest.fixture
def analitica():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA noema_silver")
    con.execute("""
        CREATE TABLE noema_silver.stg_products (
            product_id VARCHAR, customer_id VARCHAR, product_type VARCHAR,
            currency VARCHAR, current_balance DOUBLE, credit_limit DOUBLE,
            interest_rate DOUBLE, opening_date DATE, expiration_date DATE,
            product_status VARCHAR
        )""")
    con.execute(f"""
        INSERT INTO noema_silver.stg_products VALUES
          ('{P_CARD}','C1','Tarjeta Crédito','USD', 2000.0, 20000.0, 31.52,
             DATE '2022-01-01', DATE '2027-01-01','Active'),
          ('{P_LOAN}','C1','Préstamo Personal','USD', 5000.0, 10000.0, 20.10,
             DATE '2023-06-01', NULL,'Active')
    """)
    con.execute("""
        CREATE TABLE noema_silver.stg_transactions (
            transaction_id VARCHAR, product_id VARCHAR, transaction_type VARCHAR,
            transaction_date DATE, process_date DATE, transaction_status VARCHAR,
            amount_usd DOUBLE
        )""")
    con.execute(f"""
        INSERT INTO noema_silver.stg_transactions VALUES
          -- TARJETA: dos pagos validos
          ('T1','{P_CARD}','Pago', DATE '2025-03-10', DATE '2025-03-11','Approved', 300.0),
          ('T2','{P_CARD}','Pago', DATE '2025-09-05', DATE '2025-09-06','Approved', 400.0),
          -- rechazado: no es un pago
          ('T3','{P_CARD}','Pago', DATE '2025-11-20', DATE '2025-11-21','Declined', 999.0),
          -- revertido: tampoco
          ('T4','{P_CARD}','Pago', DATE '2025-11-25', DATE '2025-11-26','Reversed', 888.0),
          -- POSTERIOR AL CORTE: no se conoce al evaluar
          ('T5','{P_CARD}','Pago', DATE '2026-02-01', DATE '2026-02-02','Approved', 500.0),
          -- compra aprobada: cuenta como actividad, NO como pago
          ('T6','{P_CARD}','Compra', DATE '2025-12-15', DATE '2025-12-16','Approved', 120.0),
          -- PRESTAMO: todo su movimiento es ANTERIOR a la apertura (F-031)
          ('T7','{P_LOAN}','Pago', DATE '2023-01-15', DATE '2023-01-16','Approved', 250.0),
          ('T8','{P_LOAN}','Compra', DATE '2023-02-20', DATE '2023-02-21','Approved', 90.0),
          -- procesada ANTES de ocurrir, y la fecha real cae tras el corte
          ('T9','{P_LOAN}','Pago', DATE '2026-03-01', DATE '2025-12-01','Approved', 700.0)
    """)
    con.execute("""
        CREATE TABLE noema_silver.stg_daily_exchange_rates (
            date DATE, source_currency VARCHAR, target_currency VARCHAR, exchange_rate DOUBLE
        )""")
    return AnalyticsStore(conexion=con)


@pytest.fixture
def politica():
    return Politica.cargar()


@pytest.fixture
def contexto(analitica, politica):
    return Contexto(analitica=analitica, corte=CORTE, politica=politica)


@pytest.fixture
def registry():
    r = ToolRegistry()
    mod.registrar(r)
    return r


def sesion(role=Role.CUSTOMER, verified=True, customer_id="C1"):
    return Session(
        role=role, verified=verified, customer_id=customer_id, jti="j", conversation_id="conv-1"
    )


def llamar(registry, contexto, nombre, params=None, ses=None):
    return registry.invoke(nombre, ses or sesion(), params or {}, contexto=contexto)


# ═════════════════════════════════════════════════════════════════════════════
# 5 · get_product_catalog
# ═════════════════════════════════════════════════════════════════════════════


def test_el_catalogo_no_exige_sesion(registry, contexto):
    anon = Session(role=Role.ANONYMOUS, verified=False, conversation_id="conv-1")
    r = llamar(registry, contexto, "get_product_catalog", ses=anon)
    assert r.ok and r.data["n"] == 3


def test_el_catalogo_declara_la_tea_y_los_plazos(registry, contexto):
    r = llamar(registry, contexto, "get_product_catalog", {"product_type": "Préstamo Personal"})
    p = r.data["productos"][0]
    assert p["tasa_anual"] == 20.10
    assert p["tea_pct"] == 22.06
    assert p["plazos_ofertables"] == [24, 48, 72]


def test_el_catalogo_sale_de_la_politica_versionada(registry, contexto, politica):
    """No de `noema_gold.product_policy`, que está entera en NULL con
    `policy_ready = false` — es el cascarón de DAT-11 esperando los valores."""
    r = llamar(registry, contexto, "get_product_catalog")
    assert r.source == "agent/policies/eligibility_v1.yaml"
    assert r.data["politica_version"] == politica.version


def test_un_producto_desconocido_se_declara_ausente_sin_error(registry, contexto):
    r = llamar(registry, contexto, "get_product_catalog", {"product_type": "Hipoteca Inversa"})
    assert r.ok is True
    assert r.data["n"] == 0
    assert r.ausencias == ("producto_desconocido:Hipoteca Inversa",)


def test_sin_politica_cargada_el_catalogo_falla_con_mensaje(registry, analitica):
    ctx = Contexto(analitica=analitica, corte=CORTE, politica=None)
    r = llamar(registry, ctx, "get_product_catalog")
    assert r.ok is False and r.error == "policy_unavailable"
    assert "asesor" in r.mensaje_cliente


# ═════════════════════════════════════════════════════════════════════════════
# 6 · get_payment_history — los tres filtros de F-042
# ═════════════════════════════════════════════════════════════════════════════


def test_solo_cuentan_los_pagos_aprobados(registry, contexto):
    """La tarjeta tiene 2 aprobados, 1 rechazado y 1 revertido antes del corte."""
    r = llamar(registry, contexto, "get_payment_history", {"product_ids": [P_CARD]})
    h = r.data["historial"][0]
    assert h["pagos_registrados"] == 2
    assert h["pagado_usd"] == 700.0
    assert h["descartados_no_aprobados"] == 2


def test_no_cuenta_lo_posterior_al_corte(registry, contexto):
    r = llamar(registry, contexto, "get_payment_history", {"product_ids": [P_CARD]})
    assert r.data["historial"][0]["ultimo_pago"] == date(2025, 9, 5)


def test_una_compra_no_es_un_pago(registry, contexto):
    """T6 es una compra aprobada de diciembre: no entra en el historial de pagos."""
    r = llamar(registry, contexto, "get_payment_history", {"product_ids": [P_CARD]})
    assert r.data["historial"][0]["pagos_registrados"] == 2


def test_los_pagos_anteriores_a_la_apertura_no_cuentan(registry, contexto):
    """F-031: el 18.71 % de las transacciones precede a su cuenta. Son imposibles."""
    r = llamar(registry, contexto, "get_payment_history", {"product_ids": [P_LOAN]})
    h = r.data["historial"][0]
    assert h["pagos_registrados"] is None
    assert h["descartados_antes_de_apertura"] == 1


def test_sin_pagos_se_declara_ausencia_no_cero(registry, contexto):
    """El 29 % de los productos no registra pagos, y eso no es «pagó cero veces»."""
    r = llamar(registry, contexto, "get_payment_history", {"product_ids": [P_LOAN]})
    assert r.data["historial"][0]["pagos_registrados"] is None
    assert f"cuotas_pagadas:{P_LOAN}" in r.ausencias


def test_el_historial_declara_que_no_decide(registry, contexto):
    """R6 se retiró (F-038): esto es hecho descriptivo, no regla."""
    r = llamar(registry, contexto, "get_payment_history", {"product_ids": [P_CARD]})
    assert r.data["decide"] is False


def test_una_lista_de_productos_vacia_se_rechaza(registry, contexto):
    with pytest.raises(ToolDenied):
        llamar(registry, contexto, "get_payment_history", {"product_ids": []})


def test_no_se_puede_pedir_el_historial_de_otro_cliente(registry, contexto):
    """El `customer_id` del WHERE sale de la sesión: pedir ids ajenos no devuelve nada."""
    otro = sesion(customer_id="C-OTRO")
    r = llamar(registry, contexto, "get_payment_history", {"product_ids": [P_CARD]}, ses=otro)
    assert r.data["historial"] == []


# ═════════════════════════════════════════════════════════════════════════════
# 7 · get_last_real_activity
# ═════════════════════════════════════════════════════════════════════════════


def test_la_actividad_real_excluye_lo_posterior_al_corte(registry, contexto):
    r = llamar(registry, contexto, "get_last_real_activity", {"product_ids": [P_CARD]})
    a = r.data["actividad"][0]
    # T6 (compra aprobada, 15-dic) es la última real; T5 es de 2026.
    assert a["ultima_transaccion_real"] == date(2025, 12, 15)
    assert a["ultima_sin_filtrar"] == date(2026, 2, 1)


def test_un_producto_cuya_actividad_es_toda_imposible_no_tiene_actividad(registry, contexto):
    """Es el caso del 9.07 %: la consulta ingenua diría que tiene movimiento reciente."""
    r = llamar(registry, contexto, "get_last_real_activity", {"product_ids": [P_LOAN]})
    a = r.data["actividad"][0]
    assert a["ultima_transaccion_real"] is None
    assert a["ultima_sin_filtrar"] == date(2026, 3, 1)
    assert a["descartados_antes_de_apertura"] == 2
    assert f"ultima_transaccion_real:{P_LOAN}" in r.ausencias


def test_se_guarda_la_fecha_cruda_para_explicar_la_diferencia(registry, contexto):
    """Se guarda para poder decir por qué se descartó, nunca para usarla."""
    r = llamar(registry, contexto, "get_last_real_activity", {"product_ids": [P_CARD, P_LOAN]})
    for a in r.data["actividad"]:
        assert "ultima_sin_filtrar" in a


def test_las_fechas_no_entran_al_grounding_numerico(registry, contexto):
    r = llamar(registry, contexto, "get_last_real_activity", {"product_ids": [P_CARD]})
    assert r.grounded_values == ()


# ═════════════════════════════════════════════════════════════════════════════
# predict_capacity — dentro de la decisión, nunca como tool
# ═════════════════════════════════════════════════════════════════════════════


def test_la_capacidad_no_es_una_herramienta(registry):
    """Si el modelo pudiera omitirla, solo podría aflojar el criterio (ADR-0006 §4)."""
    assert "predict_capacity" not in registry.nombres()
    assert "estimate_capacity" not in registry.nombres()


def test_la_capacidad_no_configurada_es_deuda_declarada(contexto):
    """ML-09 (`ml/serving/predictor.py`) todavía no existe.

    Cuando exista, este test debe fallar y hay que cambiarlo: un fallo de carga
    pasará a ser `ERROR_DE_CARGA`, que bloquea. Mientras devuelva `NO_CONFIGURADO`,
    el sistema decide sin capacidad observada y lo declara.
    """
    cap = mod.estimar_capacidad(contexto, "C1")
    assert cap.motivo is MotivoCapacidad.NO_CONFIGURADO
    assert cap.valor_usd is None
    assert cap.bloquea is False


def test_solo_un_fallo_real_bloquea():
    assert Capacidad(None, MotivoCapacidad.ERROR_DE_CARGA).bloquea is True
    assert Capacidad(None, MotivoCapacidad.ABSTENCION).bloquea is False
    assert Capacidad(1500.0).bloquea is False


# ═════════════════════════════════════════════════════════════════════════════
# 8 · evaluate_eligibility
# ═════════════════════════════════════════════════════════════════════════════


def evidencia_completa(**kw):
    base = dict(
        perfil={
            "segmento": "Premium",
            "ingreso_mensual_usd": 6000.0,
            "alta": date(2018, 1, 1),
            "antiguedad_cliente_meses": 95,
        },
        creditos={
            "productos": [
                {
                    "producto_id": P_CARD,
                    "tipo": "Tarjeta Crédito",
                    "limite_usd": 20000.0,
                    "saldo_usd": 2000.0,
                    "tasa_anual": 31.52,
                    "apertura": date(2022, 1, 1),
                    "vencimiento": date(2027, 1, 1),
                }
            ],
            "n": 1,
        },
        activos={"activos": [{"tipo": "Cuenta Ahorro", "saldo_usd": 12000.0}], "n": 1},
        pagos={"historial": [{"producto_id": P_CARD, "pagos_registrados": 2}]},
        actividad={
            "actividad": [{"producto_id": P_CARD, "ultima_transaccion_real": date(2025, 12, 15)}]
        },
    )
    return Evidencia(**{**base, **kw})


def test_sin_evidencia_no_decide(registry, contexto):
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert r.ok is False and r.error == "incomplete_evidence"
    assert r.data["falta"] == ["evidencia"]


def test_con_evidencia_parcial_no_decide(registry, contexto):
    contexto.evidencia = Evidencia(perfil={"segmento": "Plus"})
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert r.ok is False
    assert r.data["falta"] == ["creditos", "activos"]


def test_la_decision_usa_la_politica_versionada(registry, contexto, politica):
    contexto.evidencia = evidencia_completa()
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert r.ok and r.data["politica_version"] == politica.version
    assert r.source == "agent.policies.engine"


def test_devuelve_ofertas_por_plazo(registry, contexto):
    contexto.evidencia = evidencia_completa()
    r = llamar(registry, contexto, "evaluate_eligibility", {"requested_amount_usd": 9000.0})
    personales = [o for o in r.data["productos_elegibles"] if o["producto"] == "Préstamo Personal"]
    assert len(personales) == 3
    cuotas = [o["cuota_estimada_usd"] for o in personales]
    assert len(set(cuotas)) == 3, "tres plazos, tres cuotas"


def test_un_error_de_carga_de_capacidad_falla_cerrado(registry, contexto):
    """Regla 5: si el estimador falla, no se aprueba nada. Se escala y se dice."""
    contexto.evidencia = evidencia_completa(
        capacidad=Capacidad(None, MotivoCapacidad.ERROR_DE_CARGA)
    )
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert r.ok is True
    assert r.data["abstencion"] is True
    assert r.data["elegible"] is False
    assert r.data["motivo_tecnico"] == "error_de_carga"
    assert "capacidad_estimada_usd" in r.ausencias


def test_una_abstencion_de_capacidad_no_bloquea(registry, contexto):
    """El 94 % de los casos: se procede con el margen de política y se declara."""
    contexto.evidencia = evidencia_completa(capacidad=Capacidad(None, MotivoCapacidad.ABSTENCION))
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert r.data["abstencion"] is False
    assert r.data["elegible"] is True
    assert "capacidad_estimada_usd" in r.ausencias


def test_la_capacidad_restringe_el_margen_y_nunca_lo_amplia(registry, contexto):
    """Con una capacidad altísima el margen es el de política, no más; con una baja,
    manda la capacidad. La **ausencia** de capacidad se prueba aparte, en
    `test_sin_capacidad_observada.py`: desde la v3 también restringe."""
    contexto.evidencia = evidencia_completa(capacidad=Capacidad(1_000_000.0))
    margen_politica = llamar(registry, contexto, "evaluate_eligibility").data["hechos"][
        "margen_mensual_usd"
    ]

    contexto.evidencia = evidencia_completa(capacidad=Capacidad(150.0))
    estrecho = llamar(registry, contexto, "evaluate_eligibility").data["hechos"][
        "margen_mensual_usd"
    ]
    assert estrecho == 150.0 < margen_politica

    contexto.evidencia = evidencia_completa(capacidad=Capacidad(margen_politica * 10))
    ancho = llamar(registry, contexto, "evaluate_eligibility").data["hechos"]["margen_mensual_usd"]
    assert ancho == margen_politica, "una capacidad alta no puede ampliar el margen"


def test_un_producto_no_valorable_abstiene(registry, contexto):
    """F-041: el 19.59 % de los clientes tenía una obligación que el motor saltaba."""
    rota = evidencia_completa()
    rota.creditos["productos"][0]["tasa_anual"] = None
    contexto.evidencia = rota
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert r.data["abstencion"] is True
    assert r.data["hechos"]["productos_no_valorables"] == 1


def test_la_decision_ancla_todas_sus_cifras(registry, contexto):
    """AG-09 valida contra `hechos` ∪ campos de `Oferta`."""
    contexto.evidencia = evidencia_completa()
    turno = TurnValues()
    r = llamar(registry, contexto, "evaluate_eligibility", {"requested_amount_usd": 9000.0})
    turno.registrar(r)
    assert r.data["hechos"]["ingreso_mensual_usd"] in turno.valores
    assert 9000.0 in turno.valores
    for o in r.data["productos_elegibles"]:
        assert o["cuota_estimada_usd"] in turno.valores


def test_las_ausencias_del_turno_se_arrastran_a_la_decision(registry, contexto):
    contexto.evidencia = evidencia_completa(ausencias=("cuotas_pagadas:PRD-X",))
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert "cuotas_pagadas:PRD-X" in r.ausencias


def test_un_monto_pedido_negativo_se_rechaza_en_el_parametro(registry, contexto):
    contexto.evidencia = evidencia_completa()
    with pytest.raises(ToolDenied):
        llamar(registry, contexto, "evaluate_eligibility", {"requested_amount_usd": -100.0})


def test_la_decision_no_consulta_la_base(registry, contexto):
    """Con la conexión cerrada la decisión sigue funcionando: toda su entrada es la
    evidencia del turno. Si consultara, esto lanzaría."""
    contexto.evidencia = evidencia_completa()
    contexto.analitica.conexion.close()
    r = llamar(registry, contexto, "evaluate_eligibility")
    assert r.ok is True and r.data["elegible"] is True


# ═════════════════════════════════════════════════════════════════════════════
# Perímetro
# ═════════════════════════════════════════════════════════════════════════════


def test_solo_el_catalogo_es_publico(registry):
    assert registry.catalogo_para(Role.ANONYMOUS) == ["get_product_catalog"]


def test_de_este_modulo_solo_escribe_la_cotizacion(registry):
    """Las cuatro de evidencia y decisión leen. La única que escribe es la que
    registra la oferta cotizada, y existe por `AG-07` (ADR-0009, decisión 3)."""
    escriben = sorted(n for n in registry.nombres() if registry.get(n).writes)
    assert escriben == ["record_offer_quote"]


def test_sin_sesion_no_se_evalua_elegibilidad(registry, contexto):
    anon = Session(role=Role.ANONYMOUS, verified=False, conversation_id="conv-1")
    contexto.evidencia = evidencia_completa()
    with pytest.raises(ToolDenied):
        llamar(registry, contexto, "evaluate_eligibility", ses=anon)
