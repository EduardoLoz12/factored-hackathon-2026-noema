"""Escrituras, idempotencia y relectura — AG-04 (tools 9 a 11) y AG-07.

Lo que este archivo tiene que demostrar, porque el reto lo pide textual —«verify that
actions actually happened», slide 11— y el brief ya anotó que es barato y casi nadie
lo hará:

1. **La relectura es un viaje de ida y vuelta real.** Hay una prueba que escribe,
   **cierra la conexión**, abre otra y relee. Devolver el objeto construido en memoria
   pasaría siempre, incluso con la base caída: no verificaría nada.
2. **La idempotencia la garantiza la base, no un `if`.** La restricción única sobre
   `idempotency_key` es lo que impide que dos procesos concurrentes abran dos casos.
3. **Si la relectura no coincide, el sistema no afirma que la acción ocurrió.**
   Regla 3 del contrato del proyecto, y `docs/05_security.md` §7.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from agent.policies.engine import Politica
from agent.tools import cases as cmod
from agent.tools import credit as crmod
from agent.tools.ledger import (
    EscrituraDuplicada,
    LedgerStore,
    abrir_ledger_en_memoria,
)
from agent.tools.registry import Role, Session, ToolDenied, ToolRegistry, TurnValues
from agent.tools.store import AnalyticsStore, Contexto, Evidencia

CORTE = date(2025, 12, 31)


@pytest.fixture
def ledger():
    return abrir_ledger_en_memoria()


@pytest.fixture
def politica():
    return Politica.cargar()


@pytest.fixture
def contexto(ledger, politica):
    return Contexto(
        analitica=AnalyticsStore(conexion=duckdb.connect(":memory:")),
        corte=CORTE,
        politica=politica,
        expedientes=ledger,
    )


@pytest.fixture
def registry():
    r = ToolRegistry()
    cmod.registrar(r)
    crmod.registrar(r)
    return r


def sesion(conversation_id="conv-1", customer_id="C1", role=Role.CUSTOMER, verified=True):
    return Session(
        role=role,
        verified=verified,
        customer_id=customer_id,
        jti="jti-1",
        conversation_id=conversation_id,
    )


OFERTA = {
    "producto": "Préstamo Personal",
    "monto_maximo_usd": 52487.0,
    "monto_ofrecido_usd": 9000.0,
    "cuota_estimada_usd": 274.35,
    "tasa_anual": 20.10,
    "plazo_meses": 48,
    "tea_pct": 22.06,
    "intereses_totales_usd": 4168.8,
}


def evidencia_con_oferta(**kw):
    base = dict(
        perfil={"segmento": "Premium", "ingreso_mensual_usd": 6000.0, "alta": date(2018, 1, 1)},
        creditos={"productos": [], "n": 0},
        activos={"activos": [], "n": 0},
        decision={
            "elegible": True,
            "abstencion": False,
            "politica_version": 2,
            "hechos": {"ingreso_mensual_usd": 6000.0, "margen_mensual_usd": 2400.0},
            "motivos": [],
            "productos_elegibles": [OFERTA],
        },
    )
    return Evidencia(**{**base, **kw})


# ═════════════════════════════════════════════════════════════════════════════
# El store: solo añadir, y la base impone la idempotencia
# ═════════════════════════════════════════════════════════════════════════════


def test_la_base_rechaza_la_clave_repetida(ledger):
    """No es un `if` de la aplicación: es una restricción única.

    Dos workers concurrentes con el mismo payload no se detectan con lógica."""
    comunes = dict(
        customer_id="C1",
        conversation_id="conv-1",
        intencion="escalar",
        expediente={"hechos": {}},
        politica_version=2,
    )
    ledger.insertar_caso(idempotency_key="K1", motivo="abstencion_de_politica", **comunes)
    with pytest.raises(EscrituraDuplicada):
        ledger.insertar_caso(idempotency_key="K1", motivo="abstencion_de_politica", **comunes)


def test_el_store_no_expone_actualizar_ni_borrar(ledger):
    """La inmutabilidad la garantiza que esas operaciones no existan (F-039)."""
    metodos = {m for m in dir(ledger) if not m.startswith("_")}
    assert not {m for m in metodos if "actualizar" in m or "borrar" in m or "update" in m}


def test_un_nan_no_puede_entrar_a_un_expediente(ledger):
    with pytest.raises(ValueError):
        ledger.insertar_caso(
            idempotency_key="K-nan",
            customer_id="C1",
            conversation_id="conv-1",
            intencion="escalar",
            motivo="abstencion_de_politica",
            expediente={"valor": float("nan")},
            politica_version=2,
        )


def test_un_expediente_no_se_relee_para_otro_cliente(ledger):
    case_id = ledger.insertar_caso(
        idempotency_key="K2",
        customer_id="C1",
        conversation_id="conv-1",
        intencion="escalar",
        motivo="abstencion_de_politica",
        expediente={"hechos": {}},
        politica_version=2,
    )
    assert ledger.releer_caso(case_id, "C1") is not None
    assert ledger.releer_caso(case_id, "C-OTRO") is None


def test_la_relectura_viaja_a_la_base_de_verdad(tmp_path):
    """Escribe, **cierra la conexión**, abre otra y relee.

    Si `releer_caso` devolviera el objeto construido en memoria, esto pasaría igual
    con la base caída — y la verificación de AG-07 no verificaría nada.
    """
    ruta = str(tmp_path / "ledger.duckdb")
    escritor = LedgerStore(conexion=duckdb.connect(ruta))
    escritor.crear_esquema()
    case_id = escritor.insertar_caso(
        idempotency_key="K3",
        customer_id="C1",
        conversation_id="conv-1",
        intencion="escalar",
        motivo="relectura_fallida",
        expediente={"hechos_verificados": {"ingreso_mensual_usd": 6000.0}},
        politica_version=2,
    )
    escritor.conexion.close()

    lector = LedgerStore(conexion=duckdb.connect(ruta, read_only=True))
    leido = lector.releer_caso(case_id, "C1")
    assert leido is not None
    assert leido["motivo"] == "relectura_fallida"
    assert leido["expediente"]["hechos_verificados"]["ingreso_mensual_usd"] == 6000.0


# ═════════════════════════════════════════════════════════════════════════════
# 10 · create_escalation_case
# ═════════════════════════════════════════════════════════════════════════════


def test_abrir_un_caso_se_confirma_releyendo(registry, contexto):
    contexto.evidencia = evidencia_con_oferta()
    r = registry.invoke(
        "create_escalation_case",
        sesion(),
        {"motivo": "abstencion_de_politica"},
        intencion="escalar",
        contexto=contexto,
    )
    assert r.ok is True
    assert r.data["verificado_por_relectura"] is True
    assert r.data["case_id"].startswith("CASE-")
    assert r.data["reintento"] is False


def test_un_reintento_no_abre_dos_casos(registry, contexto):
    contexto.evidencia = evidencia_con_oferta()
    ses = sesion()
    uno = registry.invoke(
        "create_escalation_case",
        ses,
        {"motivo": "peticion_del_cliente"},
        intencion="escalar",
        contexto=contexto,
    )
    # Segunda llamada con otro registro, para saltar el caché en memoria y llegar a
    # la base: es la base la que tiene que impedir el duplicado.
    otro = ToolRegistry()
    cmod.registrar(otro)
    dos = otro.invoke(
        "create_escalation_case",
        ses,
        {"motivo": "peticion_del_cliente"},
        intencion="escalar",
        contexto=contexto,
    )
    assert dos.data["case_id"] == uno.data["case_id"]
    assert dos.data["reintento"] is True
    assert len(contexto.expedientes.casos_abiertos()) == 1


def test_el_expediente_lleva_hechos_con_su_fuente(registry, contexto):
    contexto.evidencia = evidencia_con_oferta(ausencias=("cuotas_pagadas:PRD-X",))
    r = registry.invoke(
        "create_escalation_case",
        sesion(),
        {"motivo": "abstencion_de_politica"},
        intencion="escalar",
        contexto=contexto,
    )
    leido = contexto.expedientes.releer_caso(r.data["case_id"], "C1")
    exp = leido["expediente"]
    assert exp["hechos_verificados"]["perfil"]["ingreso_mensual_usd"] == 6000.0
    assert exp["fuentes"]["perfil"] == "noema_silver.stg_customers"
    assert exp["fuentes"]["decision"] == "agent.policies.engine"
    assert exp["ofertas_cotizadas"] == [OFERTA]
    assert exp["evidencia_faltante"] == ["cuotas_pagadas:PRD-X"]


def test_el_texto_del_cliente_va_marcado_como_no_verificado(registry, contexto):
    """Un humano que retoma el caso no debe confundirlo con un hecho establecido."""
    contexto.evidencia = evidencia_con_oferta()
    r = registry.invoke(
        "create_escalation_case",
        sesion(),
        {"motivo": "peticion_del_cliente", "pregunta_abierta": "quiero hablar con alguien"},
        intencion="escalar",
        contexto=contexto,
    )
    exp = contexto.expedientes.releer_caso(r.data["case_id"], "C1")["expediente"]
    assert exp["pregunta_abierta_no_verificada"] == "quiero hablar con alguien"


def test_el_expediente_no_lo_escribe_el_modelo(registry):
    """El modelo solo aporta motivo y pregunta: los hechos salen de los tools."""
    params = {p.name for p in registry.get("create_escalation_case").params}
    assert params == {"motivo", "pregunta_abierta"}


def test_un_motivo_fuera_de_la_lista_se_rechaza(registry, contexto):
    contexto.evidencia = evidencia_con_oferta()
    with pytest.raises(ToolDenied):
        registry.invoke(
            "create_escalation_case",
            sesion(),
            {"motivo": "porque_si"},
            intencion="escalar",
            contexto=contexto,
        )


def test_los_motivos_son_las_aristas_que_entran_a_escalate():
    """ADR-0010: no hay un escalamiento que el diagrama no explique."""
    assert set(cmod.MOTIVOS) == {
        "abstencion_de_politica",
        "contradiccion_irresoluble",
        "relectura_fallida",
        "identidad_bloqueada",
        "peticion_del_cliente",
    }


def test_sin_ledger_no_se_afirma_que_el_caso_quedo_abierto(registry, politica):
    ctx = Contexto(
        analitica=AnalyticsStore(conexion=duckdb.connect(":memory:")),
        corte=CORTE,
        politica=politica,
        expedientes=None,
        evidencia=evidencia_con_oferta(),
    )
    r = registry.invoke(
        "create_escalation_case",
        sesion(),
        {"motivo": "abstencion_de_politica"},
        intencion="escalar",
        contexto=ctx,
    )
    assert r.ok is False
    assert r.error == "ledger_unavailable"
    assert "contáctanos" in r.mensaje_cliente


def test_si_la_relectura_no_coincide_no_se_afirma(registry, contexto, monkeypatch):
    """Regla 3: si no coincide, no se afirma que la acción ocurrió."""
    contexto.evidencia = evidencia_con_oferta()
    monkeypatch.setattr(contexto.expedientes, "releer_caso", lambda *a, **k: None)
    r = registry.invoke(
        "create_escalation_case",
        sesion(),
        {"motivo": "abstencion_de_politica"},
        intencion="escalar",
        contexto=contexto,
    )
    assert r.ok is False
    assert r.error == "readback_mismatch"
    assert "no pude confirmar" in r.mensaje_cliente.lower()


# ═════════════════════════════════════════════════════════════════════════════
# 11 · get_escalation_case
# ═════════════════════════════════════════════════════════════════════════════


def test_se_relee_el_caso_propio(registry, contexto):
    contexto.evidencia = evidencia_con_oferta()
    abierto = registry.invoke(
        "create_escalation_case",
        sesion(),
        {"motivo": "abstencion_de_politica"},
        intencion="escalar",
        contexto=contexto,
    )
    r = registry.invoke(
        "get_escalation_case", sesion(), {"case_id": abierto.data["case_id"]}, contexto=contexto
    )
    assert r.data["encontrado"] is True
    assert r.data["politica_version"] == 3


def test_un_caso_ajeno_responde_igual_que_uno_inexistente(registry, contexto):
    """Distinguirlos permitiría enumerar casos de otros clientes."""
    contexto.evidencia = evidencia_con_oferta()
    abierto = registry.invoke(
        "create_escalation_case",
        sesion(),
        {"motivo": "abstencion_de_politica"},
        intencion="escalar",
        contexto=contexto,
    )
    ajeno = registry.invoke(
        "get_escalation_case",
        sesion(customer_id="C-OTRO"),
        {"case_id": abierto.data["case_id"]},
        contexto=contexto,
    )
    inexistente = registry.invoke(
        "get_escalation_case", sesion(), {"case_id": "CASE-NOEXISTE"}, contexto=contexto
    )
    assert ajeno.data == inexistente.data == {"encontrado": False}


def test_un_identificador_mal_formado_se_rechaza(registry, contexto):
    with pytest.raises(ToolDenied):
        registry.invoke("get_escalation_case", sesion(), {"case_id": "x"}, contexto=contexto)


# ═════════════════════════════════════════════════════════════════════════════
# 9 · record_offer_quote — la que hace correr VERIFY en el camino feliz
# ═════════════════════════════════════════════════════════════════════════════


def test_cotizar_una_oferta_se_confirma_releyendo(registry, contexto):
    contexto.evidencia = evidencia_con_oferta()
    r = registry.invoke(
        "record_offer_quote",
        sesion(),
        {"producto": "Préstamo Personal", "plazo_meses": 48},
        intencion="cotizar",
        contexto=contexto,
    )
    assert r.ok is True
    assert r.data["verificado_por_relectura"] is True
    assert r.data["oferta"]["monto_ofrecido_usd"] == 9000.0


def test_las_cifras_que_se_pronuncian_son_las_releidas(registry, contexto):
    """Lo que el cliente oye es lo que quedó registrado, no lo que se intentó escribir."""
    contexto.evidencia = evidencia_con_oferta()
    turno = TurnValues()
    r = registry.invoke(
        "record_offer_quote",
        sesion(),
        {"producto": "Préstamo Personal", "plazo_meses": 48},
        intencion="cotizar",
        contexto=contexto,
    )
    turno.registrar(r)
    assert 9000.0 in turno.valores
    assert 274.35 in turno.valores
    assert 22.06 in turno.valores


def test_no_se_cotiza_una_combinacion_que_la_politica_no_aprobo(registry, contexto):
    """El modelo elige entre ofertas validadas; no inventa producto ni plazo."""
    contexto.evidencia = evidencia_con_oferta()
    r = registry.invoke(
        "record_offer_quote",
        sesion(),
        {"producto": "Préstamo Personal", "plazo_meses": 72},
        intencion="cotizar",
        contexto=contexto,
    )
    assert r.ok is False
    assert r.error == "offer_not_in_decision"
    assert contexto.expedientes.casos_abiertos() == []


def test_sin_decision_no_hay_nada_que_cotizar(registry, contexto):
    contexto.evidencia = Evidencia(perfil={"segmento": "Plus"})
    r = registry.invoke(
        "record_offer_quote",
        sesion(),
        {"producto": "Préstamo Personal", "plazo_meses": 48},
        intencion="cotizar",
        contexto=contexto,
    )
    assert r.ok is False and r.error == "no_offer_to_record"


def test_la_oferta_registrada_lleva_version_de_politica_y_corte(registry, contexto):
    """El banco queda atado a lo que cotizó y bajo qué política."""
    contexto.evidencia = evidencia_con_oferta()
    r = registry.invoke(
        "record_offer_quote",
        sesion(),
        {"producto": "Préstamo Personal", "plazo_meses": 48},
        intencion="cotizar",
        contexto=contexto,
    )
    leido = contexto.expedientes.releer_accion(r.data["action_id"], "C1")
    assert leido["politica_version"] == 2
    assert leido["corte"] == CORTE
    assert leido["payload"]["tea_pct"] == 22.06


def test_si_la_relectura_de_la_oferta_no_coincide_no_se_cierra(registry, contexto, monkeypatch):
    contexto.evidencia = evidencia_con_oferta()
    monkeypatch.setattr(
        contexto.expedientes,
        "releer_accion",
        lambda *a, **k: {"payload": {**OFERTA, "cuota_estimada_usd": 999.0}},
    )
    r = registry.invoke(
        "record_offer_quote",
        sesion(),
        {"producto": "Préstamo Personal", "plazo_meses": 48},
        intencion="cotizar",
        contexto=contexto,
    )
    assert r.ok is False
    assert r.error == "readback_mismatch"
    assert "no pude confirmar" in r.mensaje_cliente.lower()


def test_dos_plazos_del_mismo_producto_son_dos_cotizaciones(registry, contexto):
    """El plazo entra en el payload, así que el `idempotency_key` las distingue."""
    otra = {**OFERTA, "plazo_meses": 72, "cuota_estimada_usd": 200.0}
    contexto.evidencia = evidencia_con_oferta(
        decision={
            "elegible": True,
            "abstencion": False,
            "politica_version": 2,
            "hechos": {},
            "motivos": [],
            "productos_elegibles": [OFERTA, otra],
        }
    )
    ses = sesion()
    a = registry.invoke(
        "record_offer_quote",
        ses,
        {"producto": "Préstamo Personal", "plazo_meses": 48},
        intencion="cotizar",
        contexto=contexto,
    )
    b = registry.invoke(
        "record_offer_quote",
        ses,
        {"producto": "Préstamo Personal", "plazo_meses": 72},
        intencion="cotizar",
        contexto=contexto,
    )
    assert a.data["action_id"] != b.data["action_id"]


# ═════════════════════════════════════════════════════════════════════════════
# Perímetro de las escrituras
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("tool", ["create_escalation_case", "record_offer_quote"])
def test_una_escritura_con_sesion_no_verificada_falla(registry, contexto, tool):
    """La prueba obligatoria de `docs/05_security.md` §3, sobre las tools reales."""
    contexto.evidencia = evidencia_con_oferta()
    sin_verificar = Session(role=Role.CUSTOMER, verified=False, conversation_id="conv-1")
    params = (
        {"motivo": "abstencion_de_politica"}
        if tool == "create_escalation_case"
        else {"producto": "Préstamo Personal", "plazo_meses": 48}
    )
    with pytest.raises(ToolDenied):
        registry.invoke(tool, sin_verificar, params, intencion="x", contexto=contexto)
    assert contexto.expedientes.casos_abiertos() == []


@pytest.mark.parametrize("tool", ["create_escalation_case", "record_offer_quote"])
def test_una_escritura_sin_intencion_declarada_falla(registry, contexto, tool):
    """Sin intención no hay clave de idempotencia, y sin clave no se escribe."""
    contexto.evidencia = evidencia_con_oferta()
    params = (
        {"motivo": "abstencion_de_politica"}
        if tool == "create_escalation_case"
        else {"producto": "Préstamo Personal", "plazo_meses": 48}
    )
    with pytest.raises(ToolDenied):
        registry.invoke(tool, sesion(), params, contexto=contexto)


def test_solo_dos_tools_escriben(registry):
    assert sorted(n for n in registry.nombres() if registry.get(n).writes) == [
        "create_escalation_case",
        "record_offer_quote",
    ]
