"""El expediente validado por esquema — AG-08.

El reto pide «structured handoff… **not raw transcripts**» (slide 11). Lo que un esquema
aporta no son los tipos: que un campo sea `str` no evita ninguno de los problemas reales.
Lo que estas pruebas fijan es lo que sí los evita:

1. **Un hecho sin fuente no es un hecho verificado.** Entregarlo como tal vacía la
   palabra, y es justo lo que el jurado va a mirar en el expediente.
2. **No viaja PII en claro**, y se rechaza por nombre de campo **a cualquier
   profundidad** — no por revisión manual del ensamblado.
3. **Falla degradado, no cerrado.** Si el expediente no se puede armar, el caso se abre
   igual con uno mínimo y **marcado**: el escalamiento existe para que una persona
   atienda al cliente, y negarlo por un bug nuestro lo castigaría a él.
"""

from __future__ import annotations

import duckdb
import pytest

from agent.core.handoff import (
    BLOQUES_REQUERIDOS,
    CAMPOS_PROHIBIDOS,
    expediente_degradado,
    validar,
    validar_o_degradar,
)
from agent.policies.engine import Politica
from agent.tools import cases as ca
from agent.tools.ledger import abrir_ledger_en_memoria
from agent.tools.registry import Role, Session, ToolRegistry
from agent.tools.store import AnalyticsStore, Contexto, Evidencia


def expediente(**kw):
    base = {
        "hechos_verificados": {"perfil": {"segmento": "Premium", "ingreso_mensual_usd": 6000.0}},
        "fuentes": {"perfil": "noema_silver.stg_customers"},
        "ofertas_cotizadas": [],
        "evidencia_faltante": [],
        "pregunta_abierta_no_verificada": None,
        "conversation_id": "conv-1",
    }
    return {**base, **kw}


# ═════════════════════════════════════════════════════════════════════════════
# Lo válido
# ═════════════════════════════════════════════════════════════════════════════


def test_un_expediente_completo_pasa():
    r = validar(expediente())
    assert r.ok is True
    assert r.problemas == []


def test_la_pregunta_del_cliente_puede_venir_como_texto():
    r = validar(expediente(pregunta_abierta_no_verificada="quiero hablar con alguien"))
    assert r.ok is True


# ═════════════════════════════════════════════════════════════════════════════
# 1 · Todo hecho tiene fuente
# ═════════════════════════════════════════════════════════════════════════════


def test_un_hecho_sin_fuente_no_pasa():
    """Entregar como verificado algo cuya procedencia nadie puede responder vacía la
    palabra «verificado», que es el centro de lo que el reto pide."""
    r = validar(expediente(hechos_verificados={"perfil": {}, "productos_credito": []}))
    assert r.ok is False
    assert any("productos_credito" in p and "sin fuente" in p for p in r.problemas)


def test_una_fuente_sin_hecho_tambien_se_reporta():
    """Menos grave, pero indica un ensamblado roto."""
    r = validar(expediente(fuentes={"perfil": "x", "inventado": "y"}))
    assert r.ok is False
    assert any("no respaldan" in p for p in r.problemas)


def test_el_expediente_real_declara_la_fuente_de_cada_bloque():
    """La prueba cruzada contra el ensamblado de verdad, no contra uno de laboratorio."""
    ctx = Contexto(analitica=AnalyticsStore(conexion=duckdb.connect(":memory:")), corte=None)
    ctx.evidencia = Evidencia(
        perfil={"segmento": "Plus", "ingreso_mensual_usd": 3000.0},
        creditos={"productos": []},
        activos={"activos": []},
        decision={
            "elegible": True,
            "abstencion": False,
            "politica_version": 3,
            "hechos": {},
            "motivos": [],
            "productos_elegibles": [],
        },
    )
    ses = Session(
        role=Role.CUSTOMER, verified=True, customer_id="C1", jti="j", conversation_id="conv-1"
    )
    assert validar(ca._expediente(ctx, ses, None)).ok is True


# ═════════════════════════════════════════════════════════════════════════════
# 2 · PII, a cualquier profundidad
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("campo", sorted(CAMPOS_PROHIBIDOS))
def test_ningun_dato_personal_pasa(campo):
    r = validar(
        expediente(hechos_verificados={"perfil": {campo: "x"}}, fuentes={"perfil": "tabla"})
    )
    assert r.ok is False
    assert any(campo in p for p in r.problemas)


def test_la_pii_se_detecta_aunque_este_anidada_hondo():
    hondo = {"a": {"b": {"c": [{"d": {"email": "x@y.z"}}]}}}
    r = validar(expediente(hechos_verificados={"perfil": hondo}, fuentes={"perfil": "t"}))
    assert r.ok is False
    assert any("email" in p for p in r.problemas)


def test_el_mensaje_de_error_no_filtra_el_valor():
    """Decir el valor en el problema sería escribirlo en el log, que es lo que se evita."""
    r = validar(
        expediente(
            hechos_verificados={"perfil": {"email": "secreto@banco.com"}}, fuentes={"perfil": "t"}
        )
    )
    assert not any("secreto@banco.com" in p for p in r.problemas)


def test_el_identificador_del_cliente_si_puede_viajar():
    """Es el identificador propio del sistema, y sin él el asesor no puede retomar nada."""
    assert "customer_id" not in CAMPOS_PROHIBIDOS
    assert (
        validar(
            expediente(
                hechos_verificados={"perfil": {"customer_id": "CLI-1"}}, fuentes={"perfil": "t"}
            )
        ).ok
        is True
    )


# ═════════════════════════════════════════════════════════════════════════════
# 3 · Bloques obligatorios y formas
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bloque", BLOQUES_REQUERIDOS)
def test_falta_un_bloque_obligatorio(bloque):
    incompleto = expediente()
    del incompleto[bloque]
    r = validar(incompleto)
    assert r.ok is False
    assert any(bloque in p for p in r.problemas)


def test_la_evidencia_faltante_es_bloque_obligatorio():
    """Un expediente que omite lo que faltó esconde lo que el humano más necesita."""
    assert "evidencia_faltante" in BLOQUES_REQUERIDOS


def test_una_lista_que_no_es_lista_no_pasa():
    r = validar(expediente(evidencia_faltante="cuotas_pagadas:P1"))
    assert r.ok is False
    assert any("debe ser una lista" in p for p in r.problemas)


def test_un_expediente_que_no_es_objeto_no_pasa():
    assert validar("texto suelto").ok is False
    assert validar(None).ok is False


# ═════════════════════════════════════════════════════════════════════════════
# 4 · Números no serializables
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("malo", [float("nan"), float("inf"), float("-inf")])
def test_un_numero_no_finito_no_pasa(malo):
    """Si no se puede serializar, la relectura de AG-07 fallaría después, no antes."""
    r = validar(expediente(hechos_verificados={"perfil": {"dti": malo}}, fuentes={"perfil": "t"}))
    assert r.ok is False
    assert any("no finito" in p for p in r.problemas)


def test_un_anidamiento_absurdo_se_corta():
    nodo: dict = {"fin": 1}
    for _ in range(30):
        nodo = {"n": nodo}
    r = validar(expediente(hechos_verificados={"perfil": nodo}, fuentes={"perfil": "t"}))
    assert r.ok is False
    assert any("anidamiento" in p for p in r.problemas)


# ═════════════════════════════════════════════════════════════════════════════
# 5 · Falla degradado, no cerrado
# ═════════════════════════════════════════════════════════════════════════════


def test_el_expediente_degradado_es_valido_y_esta_marcado():
    degradado = expediente_degradado("conv-1", ["algo falló"])
    assert validar(degradado).ok is True
    assert degradado["degradado"] is True
    assert degradado["problemas_de_esquema"] == ["algo falló"]
    assert degradado["evidencia_faltante"] == ["expediente_no_ensamblado"]


def test_validar_o_degradar_devuelve_lo_bueno_tal_cual():
    bueno = expediente()
    salida, r = validar_o_degradar(bueno, "conv-1")
    assert salida is bueno and r.ok is True


def test_validar_o_degradar_sustituye_lo_malo():
    salida, r = validar_o_degradar(expediente(fuentes={}), "conv-1")
    assert r.ok is False
    assert salida["degradado"] is True
    assert salida["conversation_id"] == "conv-1"


def test_un_expediente_roto_abre_el_caso_igual():
    """El cliente no puede quedarse sin asesor porque nuestro ensamblado falló."""
    led = abrir_ledger_en_memoria()
    reg = ToolRegistry()
    ca.registrar(reg)
    ctx = Contexto(
        analitica=AnalyticsStore(conexion=duckdb.connect(":memory:")),
        corte=Politica.cargar().corte,
        politica=Politica.cargar(),
        expedientes=led,
    )
    # El correo va dentro de un PRODUCTO, que es el vector real: `_expediente` copia
    # el perfil con lista blanca —ahí no entra nada nuevo— pero los productos y los
    # activos se copian enteros. El esquema es el respaldo de esos bloques.
    ctx.evidencia = Evidencia(
        perfil={"segmento": "Plus", "ingreso_mensual_usd": 3000.0},
        creditos={
            "productos": [{"producto_id": "P1", "tipo": "Tarjeta Crédito", "email": "x@y.z"}]
        },
        activos={"activos": []},
    )
    ses = Session(
        role=Role.CUSTOMER, verified=True, customer_id="C1", jti="j", conversation_id="conv-1"
    )
    r = reg.invoke(
        "create_escalation_case",
        ses,
        {"motivo": "peticion_del_cliente"},
        intencion="escalar",
        contexto=ctx,
    )
    assert r.ok is True, "el caso se abre"
    assert r.data["esquema_ok"] is False, "pero marcado como no válido"
    assert r.data["problemas_de_esquema"]
    guardado = led.releer_caso(r.data["case_id"], "C1")
    assert guardado["expediente"]["degradado"] is True
    # El diagnóstico NOMBRA el campo a propósito, para que se pueda arreglar. Lo que no
    # puede viajar es el VALOR.
    guardado_txt = str(guardado["expediente"])
    assert "x@y.z" not in guardado_txt, "el valor del dato personal no llegó a la base"
    assert "email" in guardado_txt, "pero el problema sí se nombra, para poder corregirlo"


def test_el_perfil_se_copia_con_lista_blanca():
    """Primera barrera, antes del esquema: `_expediente` solo copia campos nombrados del
    perfil, así que un campo nuevo en el tool no llega al expediente por descuido. Los
    productos y los activos sí se copian enteros, y para esos el esquema es el respaldo."""
    ctx = Contexto(analitica=AnalyticsStore(conexion=duckdb.connect(":memory:")), corte=None)
    ctx.evidencia = Evidencia(
        perfil={"segmento": "Plus", "email": "x@y.z", "document_number": "123"},
        creditos={"productos": []},
        activos={"activos": []},
    )
    ses = Session(
        role=Role.CUSTOMER, verified=True, customer_id="C1", jti="j", conversation_id="conv-1"
    )
    exp = ca._expediente(ctx, ses, None)
    assert "email" not in exp["hechos_verificados"]["perfil"]
    assert "document_number" not in exp["hechos_verificados"]["perfil"]
    assert validar(exp).ok is True


def test_un_expediente_bueno_se_guarda_sin_marca():
    led = abrir_ledger_en_memoria()
    reg = ToolRegistry()
    ca.registrar(reg)
    ctx = Contexto(
        analitica=AnalyticsStore(conexion=duckdb.connect(":memory:")),
        corte=Politica.cargar().corte,
        politica=Politica.cargar(),
        expedientes=led,
    )
    ctx.evidencia = Evidencia(
        perfil={"segmento": "Plus", "ingreso_mensual_usd": 3000.0},
        creditos={"productos": []},
        activos={"activos": []},
    )
    ses = Session(
        role=Role.CUSTOMER, verified=True, customer_id="C1", jti="j", conversation_id="conv-1"
    )
    r = reg.invoke(
        "create_escalation_case",
        ses,
        {"motivo": "abstencion_de_politica"},
        intencion="escalar",
        contexto=ctx,
    )
    assert r.data["esquema_ok"] is True
    guardado = led.releer_caso(r.data["case_id"], "C1")
    assert "degradado" not in guardado["expediente"]


# ═════════════════════════════════════════════════════════════════════════════
# La traza
# ═════════════════════════════════════════════════════════════════════════════


def test_la_traza_dice_si_el_esquema_paso():
    r = validar(expediente(fuentes={}))
    traza = r.a_traza()
    assert traza["etapa"] == "ESCALATE"
    assert traza["esquema_ok"] is False
    assert traza["problemas"]
