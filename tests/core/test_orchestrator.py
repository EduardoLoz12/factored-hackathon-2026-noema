"""El orquestador de las seis etapas — AG-06.

ADR-0010 pide **un test por arista** del diagrama, y eso es lo que hay acá. Todo corre
**sin LLM**: si la secuencia de etapas dependiera del modelo, no sería reproducible ni
demostrable ante el jurado, que es el punto de separar la conversación de la decisión.

Las aristas, en el orden del diagrama:

1. identidad sin verificar → bloqueado
2. el cliente pide una persona → escalado
3. intención desconocida → escalado
4. contradicción entre dos fuentes de la base → escalado
5. contradicción con el cliente → se resuelve, el turno sigue
6. falta evidencia → se pregunta, fin del turno
7. consulta de producto → salta decisión y acción
8. la política se abstiene → escalado
9. elegible y sin producto elegido → no se escribe nada
10. elegible con producto elegido → se cotiza y se relee
11. la relectura falla → escalado, y **no se afirma** que ocurrió
12. cifra sin anclaje → escalado
13. todo cuadra → respuesta
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from agent.cognition.scm import Source, SourceLayer
from agent.core.orchestrator import Desenlace, Etapa, Orquestador
from agent.policies.engine import Politica
from agent.tools import cases as ca
from agent.tools import credit as cr
from agent.tools import customer as cu
from agent.tools.ledger import abrir_ledger_en_memoria
from agent.tools.registry import Role, Session, ToolRegistry
from agent.tools.store import AnalyticsStore, Contexto

CORTE = date(2025, 12, 31)
P_CARD = "PRD-CARD"


@pytest.fixture
def analitica():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA noema_silver")
    con.execute("""
        CREATE TABLE noema_silver.stg_customers (
            customer_id VARCHAR, document_number VARCHAR, document_type VARCHAR,
            date_of_birth VARCHAR, country VARCHAR, segment VARCHAR,
            estimated_monthly_income DOUBLE, registration_date DATE
        )""")
    # Ingreso en USD para que la cuenta se lea sin conversión.
    con.execute("""
        INSERT INTO noema_silver.stg_customers VALUES
          ('C1','11111111','DNI','1980-05-10','Colombia','Premium', 24000000.0, DATE '2018-01-01'),
          ('C-SIN','22222222','DNI','1990-01-01','Colombia','Premium', NULL, DATE '2018-01-01')
    """)
    con.execute("""
        CREATE TABLE noema_silver.stg_products (
            product_id VARCHAR, customer_id VARCHAR, product_type VARCHAR,
            currency VARCHAR, current_balance DOUBLE, credit_limit DOUBLE,
            interest_rate DOUBLE, opening_date DATE, expiration_date DATE,
            product_status VARCHAR
        )""")
    con.execute(f"""
        INSERT INTO noema_silver.stg_products VALUES
          ('{P_CARD}','C1','Tarjeta Crédito','USD', 1000.0, 10000.0, 31.52,
             DATE '2020-01-01', DATE '2027-01-01','Active'),
          ('PRD-AHO','C1','Cuenta Ahorro','USD', 30000.0, NULL, NULL,
             DATE '2019-01-01', NULL,'Active')
    """)
    con.execute("""
        CREATE TABLE noema_silver.stg_transactions (
            transaction_id VARCHAR, product_id VARCHAR, transaction_type VARCHAR,
            transaction_date DATE, process_date DATE, transaction_status VARCHAR,
            amount_usd DOUBLE
        )""")
    con.execute(f"""
        INSERT INTO noema_silver.stg_transactions VALUES
          ('T1','{P_CARD}','Pago', DATE '2025-06-01', DATE '2025-06-02','Approved', 300.0)
    """)
    con.execute("""
        CREATE TABLE noema_silver.stg_daily_exchange_rates (
            date DATE, source_currency VARCHAR, target_currency VARCHAR, exchange_rate DOUBLE
        )""")
    con.execute("""
        INSERT INTO noema_silver.stg_daily_exchange_rates VALUES
          (DATE '2025-12-20','COP','USD',0.00025)
    """)
    return AnalyticsStore(conexion=con)


@pytest.fixture
def contexto(analitica):
    return Contexto(
        analitica=analitica,
        corte=CORTE,
        politica=Politica.cargar(),
        expedientes=abrir_ledger_en_memoria(),
    )


@pytest.fixture
def registry():
    r = ToolRegistry()
    for mod in (cu, cr, ca):
        mod.registrar(r)
    return r


@pytest.fixture
def orq(registry, contexto):
    return Orquestador(registry=registry, contexto=contexto)


def ses(customer_id="C1", verified=True, role=Role.CUSTOMER):
    return Session(
        role=role,
        verified=verified,
        customer_id=customer_id,
        jti="jti-1",
        conversation_id="conv-1",
    )


SLOTS = {"requested_amount": 5000.0, "currency": "USD", "product_type": "Tarjeta Crédito"}


def elegibilidad(orq, **kw):
    params = dict(session=ses(), intencion="CREDIT_ELIGIBILITY", slots=dict(SLOTS))
    params.update(kw)
    return orq.turno(**params)


# ═════════════════════════════════════════════════════════════════════════════
# 1 · IDENTIFY
# ═════════════════════════════════════════════════════════════════════════════


def test_sin_verificar_no_sale_ninguna_informacion(orq):
    t = orq.turno(ses(verified=False, customer_id=None), intencion="CREDIT_ELIGIBILITY")
    assert t.desenlace is Desenlace.BLOQUEADO
    assert t.etapas_recorridas == ["IDENTIFY"]
    assert t.decision is None and not t.ofertas


def test_identify_se_marca_como_extension_propia(orq):
    """El reto pide cinco etapas. La sexta es nuestra y el panel lo dice."""
    t = elegibilidad(orq)
    identify = next(x for x in t.etapas if x.etapa is Etapa.IDENTIFY)
    assert identify.es_extension_propia is True
    assert all(x.es_extension_propia is False for x in t.etapas if x.etapa is not Etapa.IDENTIFY)


def test_las_cinco_etapas_del_reto_llevan_su_nombre_textual():
    assert [e.value for e in Etapa if e.del_reto] == [
        "UNDERSTAND",
        "DECIDE",
        "ACT",
        "VERIFY",
        "ESCALATE",
    ]


# ═════════════════════════════════════════════════════════════════════════════
# 2 · El cliente pide una persona
# ═════════════════════════════════════════════════════════════════════════════


def test_el_cliente_siempre_puede_pedir_una_persona(orq):
    t = elegibilidad(orq, pide_humano=True)
    assert t.desenlace is Desenlace.ESCALADO
    assert t.case_id is not None
    assert t.etapas_recorridas == ["IDENTIFY", "ESCALATE"]


# ═════════════════════════════════════════════════════════════════════════════
# 3 · Intención desconocida
# ═════════════════════════════════════════════════════════════════════════════


def test_una_intencion_desconocida_escala(orq):
    t = orq.turno(ses(), intencion="PEDIR_HIPOTECA_INVERSA", slots={})
    assert t.desenlace is Desenlace.ESCALADO
    assert "intención desconocida" in " ".join(x.razon for x in t.etapas)


# ═════════════════════════════════════════════════════════════════════════════
# 4 y 5 · Contradicciones — las resuelve el orquestador, por tipo
# ═════════════════════════════════════════════════════════════════════════════


def test_un_cliente_que_se_corrige_no_escala(orq):
    """«Quiero 5 000… mejor 8 000» genera un conflicto legítimo del cliente.

    Es la trampa de `contradictions()`: marca cualquier par de valores distintos para
    el mismo predicado, y `assert_fact` nunca sobrescribe. Escalar aquí haría inusable
    el sistema."""
    t = orq.turno(
        ses(),
        intencion="CREDIT_ELIGIBILITY",
        slots={**SLOTS, "requested_amount": 8000.0},
    )
    assert t.desenlace is not Desenlace.ESCALADO


def test_dos_fuentes_de_la_base_que_discrepan_escalan(orq, monkeypatch):
    """Ahí el sistema no tiene criterio para preferir una, y afirmar sería inventar."""
    from agent.core import orchestrator as mod

    real = mod.SemanticState

    class ConConflicto(real):  # type: ignore[misc,valid-type]
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            tabla = Source(SourceLayer.TABLE, "gold.customer_360")
            herramienta = Source(SourceLayer.TOOL, "get_customer_profile")
            super().assert_fact("customer", "ingreso_mensual_usd", 6000.0, tabla)
            super().assert_fact("customer", "ingreso_mensual_usd", 9000.0, herramienta)

    monkeypatch.setattr(mod, "SemanticState", ConConflicto)
    t = elegibilidad(orq)
    assert t.desenlace is Desenlace.ESCALADO
    assert "dos fuentes de la base discrepan" in " ".join(x.razon for x in t.etapas)


# ═════════════════════════════════════════════════════════════════════════════
# 6 · Falta evidencia → se pregunta en vez de decidir
# ═════════════════════════════════════════════════════════════════════════════


def test_si_falta_un_slot_se_pregunta(orq):
    t = orq.turno(ses(), intencion="CREDIT_ELIGIBILITY", slots={"product_type": "Tarjeta Crédito"})
    assert t.desenlace is Desenlace.PREGUNTA
    assert set(t.pregunta_por) == {"requested_amount", "currency"}
    assert t.decision is None, "no se decide con evidencia incompleta"
    assert t.case_id is None, "preguntar no es escalar"


def test_un_slot_en_unknown_cuenta_como_ausente(orq):
    t = orq.turno(ses(), intencion="CREDIT_ELIGIBILITY", slots={**SLOTS, "currency": "UNKNOWN"})
    assert t.desenlace is Desenlace.PREGUNTA
    assert "currency" in t.pregunta_por


# ═════════════════════════════════════════════════════════════════════════════
# 7 · PRODUCT_INFO salta DECIDE y ACT
# ═════════════════════════════════════════════════════════════════════════════


def test_una_consulta_de_producto_no_pasa_por_la_politica(orq):
    """Forzarla produciría una abstención falsa en la métrica."""
    t = orq.turno(ses(), intencion="PRODUCT_INFO", slots={"product_type": "Préstamo Personal"})
    assert t.desenlace is Desenlace.RESPUESTA
    assert "DECIDE" not in t.etapas_recorridas
    assert "ACT" not in t.etapas_recorridas
    assert "VERIFY" in t.etapas_recorridas
    assert t.ofertas and t.ofertas[0]["tea_pct"] == 22.06


def test_la_consulta_de_producto_no_exige_monto(orq):
    t = orq.turno(ses(), intencion="PRODUCT_INFO", slots={"product_type": "Tarjeta Crédito"})
    assert t.desenlace is Desenlace.RESPUESTA


# ═════════════════════════════════════════════════════════════════════════════
# 8 · La política se abstiene
# ═════════════════════════════════════════════════════════════════════════════


def test_una_abstencion_de_politica_escala(orq):
    """Cliente sin ingreso registrado: la política abstiene y se deriva."""
    t = orq.turno(ses(customer_id="C-SIN"), intencion="CREDIT_ELIGIBILITY", slots=dict(SLOTS))
    assert t.desenlace is Desenlace.ESCALADO
    assert t.case_id is not None
    assert "DECIDE" in t.etapas_recorridas
    assert "la política se abstuvo" in " ".join(x.razon for x in t.etapas)


# ═════════════════════════════════════════════════════════════════════════════
# 9, 10, 13 · Camino feliz, con y sin acción
# ═════════════════════════════════════════════════════════════════════════════


def test_elegible_sin_producto_elegido_no_escribe_nada(orq):
    t = elegibilidad(orq)
    assert t.desenlace is Desenlace.RESPUESTA
    assert t.action_id is None
    assert "nada que escribir" in " ".join(x.razon for x in t.etapas)


def test_elegible_con_producto_elegido_cotiza_y_relee(orq):
    t = elegibilidad(orq, producto_elegido=("Tarjeta Crédito", 48))
    assert t.desenlace is Desenlace.RESPUESTA
    assert t.action_id is not None
    assert "relectura confirmada" in " ".join(x.razon for x in t.etapas)
    assert t.etapas_recorridas == [
        "IDENTIFY",
        "UNDERSTAND",
        "DECIDE",
        "ACT",
        "VERIFY",
    ]


def test_la_cotizacion_queda_en_el_ledger(orq, contexto):
    t = elegibilidad(orq, producto_elegido=("Tarjeta Crédito", 48))
    guardado = contexto.expedientes.releer_accion(t.action_id, "C1")
    assert guardado is not None
    assert guardado["payload"]["producto"] == "Tarjeta Crédito"
    assert guardado["politica_version"] == contexto.politica.version


def test_el_turno_feliz_ancla_sus_cifras(orq):
    t = elegibilidad(orq, producto_elegido=("Tarjeta Crédito", 48))
    assert len(t.cifras_ancladas) > 10


# ═════════════════════════════════════════════════════════════════════════════
# 11 · La relectura falla → no se afirma que ocurrió
# ═════════════════════════════════════════════════════════════════════════════


def test_si_la_relectura_falla_no_se_afirma_la_accion(orq, contexto, monkeypatch):
    monkeypatch.setattr(contexto.expedientes, "releer_accion", lambda *a, **k: None)
    t = elegibilidad(orq, producto_elegido=("Tarjeta Crédito", 48))
    assert t.desenlace is Desenlace.ESCALADO
    assert t.action_id is None, "no se devuelve un id que no se pudo confirmar"
    razones = " ".join(x.razon for x in t.etapas)
    assert "cotización no confirmada" in razones
    assert "relectura fallida" in razones


def test_un_producto_que_la_politica_no_ofrecio_no_se_cotiza(orq):
    t = elegibilidad(orq, producto_elegido=("Préstamo Hipotecario", 240))
    assert t.desenlace is Desenlace.ESCALADO
    assert t.action_id is None


# ═════════════════════════════════════════════════════════════════════════════
# 12 · Cifra sin anclaje
# ═════════════════════════════════════════════════════════════════════════════


def test_una_cifra_sin_anclaje_bloquea_la_respuesta(orq, monkeypatch):
    """Es el suelo sobre el que AG-09 construye: acá se valida la carga estructurada."""
    import agent.core.orchestrator as mod

    monkeypatch.setattr(mod.Orquestador, "_anclaje", lambda self, datos, valores: {123456.78})
    t = elegibilidad(orq)
    assert t.desenlace is Desenlace.ESCALADO
    assert "cifras sin anclaje" in " ".join(x.razon for x in t.etapas)


def test_el_anclaje_acepta_lo_que_los_tools_devolvieron(orq):
    t = elegibilidad(orq)
    assert t.desenlace is Desenlace.RESPUESTA, "sin huérfanas en el camino normal"


# ═════════════════════════════════════════════════════════════════════════════
# La bandera del SCM — el tercer brazo de la evaluación
# ═════════════════════════════════════════════════════════════════════════════


def test_con_el_scm_apagado_el_piso_de_seguridad_no_cambia(orq, monkeypatch):
    monkeypatch.setenv("SCM_ENABLED", "false")
    t = elegibilidad(orq, producto_elegido=("Tarjeta Crédito", 48))
    assert t.desenlace is Desenlace.RESPUESTA
    assert t.action_id is not None
    assert t.scm is None, "sin SCM no hay estado semántico que publicar"


def test_con_el_scm_apagado_la_pregunta_por_slots_sigue_igual(orq, monkeypatch):
    """La comprobación equivalente replica `missing_evidence()`: mismo criterio."""
    monkeypatch.setenv("SCM_ENABLED", "false")
    t = orq.turno(ses(), intencion="CREDIT_ELIGIBILITY", slots={"product_type": "Tarjeta Crédito"})
    assert t.desenlace is Desenlace.PREGUNTA
    assert set(t.pregunta_por) == {"requested_amount", "currency"}


def test_con_el_scm_apagado_no_se_detectan_contradicciones(orq, monkeypatch):
    """Lo que SÍ cambia, y es exactamente lo que `EV-06` mide como tercer brazo.

    Nada replica `contradictions()`: una comprobación de slots no lo hace."""
    monkeypatch.setenv("SCM_ENABLED", "false")
    t = elegibilidad(orq)
    assert t.scm is None
    assert not any("contradicción" in x.razon for x in t.etapas)


def test_con_el_scm_encendido_se_publica_el_estado_epistemico(orq):
    t = elegibilidad(orq)
    assert t.scm is not None
    assert t.scm["epistemic_status"] in {"COMPLETE", "INCOMPLETE", "CONFLICTED"}


# ═════════════════════════════════════════════════════════════════════════════
# La traza — lo que alimenta el panel y las métricas
# ═════════════════════════════════════════════════════════════════════════════


def test_la_traza_lleva_la_secuencia_con_su_razon(orq):
    t = elegibilidad(orq, producto_elegido=("Tarjeta Crédito", 48))
    traza = t.a_traza()
    assert [e["etapa"] for e in traza["etapas"]] == t.etapas_recorridas
    assert all(e["razon"] for e in traza["etapas"]), "cada transición dice por qué"
    assert traza["etapas"][0]["del_reto"] is False, "IDENTIFY es nuestra"


def test_la_traza_no_lleva_prosa_del_cliente(orq):
    t = elegibilidad(orq)
    assert "mensaje" not in t.a_traza()


def test_cada_desenlace_es_distinguible_para_las_metricas(orq):
    """`EV-06` cuenta resolución segura, abstención y bloqueo por separado."""
    respuesta = elegibilidad(orq).desenlace
    pregunta = orq.turno(ses(), intencion="CREDIT_ELIGIBILITY", slots={}).desenlace
    escalado = orq.turno(
        ses(customer_id="C-SIN"), intencion="CREDIT_ELIGIBILITY", slots=dict(SLOTS)
    ).desenlace
    bloqueado = orq.turno(ses(verified=False, customer_id=None), intencion="PRODUCT_INFO").desenlace
    assert len({respuesta, pregunta, escalado, bloqueado}) == 4


# ═════════════════════════════════════════════════════════════════════════════
# El orquestador no llama al LLM
# ═════════════════════════════════════════════════════════════════════════════


def test_el_orquestador_no_importa_el_cliente_del_llm():
    """Si la secuencia dependiera del modelo, no sería reproducible ni demostrable."""
    import agent.core.orchestrator as mod

    fuente = (mod.__file__ or "").replace(".pyc", ".py")
    texto = open(fuente, encoding="utf-8").read()
    for prohibido in ("import anthropic", "from anthropic"):
        assert prohibido not in texto
