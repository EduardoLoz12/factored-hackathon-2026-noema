"""Pruebas del registro de herramientas — AG-03.

Se testea sin LLM y sin base de datos: el control de acceso es determinista o no
es control de acceso. Los handlers son dobles de prueba.

La prueba marcada OBLIGATORIA en `docs/05_security.md` §3 es
`test_escritura_con_sesion_no_verificada_falla`.
"""

from __future__ import annotations

import time

import pytest

from agent.tools.registry import (
    MENSAJE_GENERICO_RECHAZO,
    Param,
    Rechazo,
    Role,
    Session,
    ToolDenied,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    TurnValues,
    derivar_idempotency_key,
)

# ─────────────────────────────────────────────────────────────────────────────
# Dobles de prueba
# ─────────────────────────────────────────────────────────────────────────────


def handler_lectura(session, params, contexto, idempotency_key):
    return ToolResult(
        tool="leer",
        ok=True,
        data={"customer_id": session.customer_id},
        grounded_values=(1234.56,),
        source="noema_gold.customer_360",
    )


def handler_escritura(session, params, contexto, idempotency_key):
    handler_escritura.llamadas += 1
    return ToolResult(tool="escribir", ok=True, data={"case_id": "C-1"}, source="cases")


handler_escritura.llamadas = 0


def handler_que_explota(session, params, contexto, idempotency_key):
    raise RuntimeError("la base no responde")


def spec_lectura(**kw):
    base = dict(
        name="leer",
        module="customer",
        descripcion="lectura de prueba",
        handler=handler_lectura,
        requires_auth=True,
        writes=False,
        allowed_roles=frozenset({Role.CUSTOMER}),
    )
    return ToolSpec(**{**base, **kw})


def spec_escritura(**kw):
    base = dict(
        name="escribir",
        module="cases",
        descripcion="escritura de prueba",
        handler=handler_escritura,
        requires_auth=True,
        writes=True,
        allowed_roles=frozenset({Role.CUSTOMER}),
    )
    return ToolSpec(**{**base, **kw})


def sesion_verificada(**kw):
    base = dict(
        role=Role.CUSTOMER,
        verified=True,
        customer_id="CUST-1",
        jti="jti-1",
        conversation_id="conv-1",
    )
    return Session(**{**base, **kw})


@pytest.fixture
def registry():
    handler_escritura.llamadas = 0
    return ToolRegistry()


# ─────────────────────────────────────────────────────────────────────────────
# La prueba obligatoria del contrato de seguridad
# ─────────────────────────────────────────────────────────────────────────────


def test_escritura_con_sesion_no_verificada_falla(registry):
    """OBLIGATORIA — `docs/05_security.md` §3."""
    registry.register(spec_escritura())
    sesion = Session(role=Role.CUSTOMER, verified=False, conversation_id="conv-1")

    with pytest.raises(ToolDenied) as exc:
        registry.invoke("escribir", sesion, {}, intencion="escalar")

    assert exc.value.razon is Rechazo.SESION_NO_VERIFICADA
    # Y, sobre todo, el handler nunca corrió.
    assert handler_escritura.llamadas == 0
    assert registry.rechazos[-1]["razon"] == "session_not_verified"


def test_el_rechazo_no_distingue_causa_ante_el_cliente(registry):
    """Mensaje idéntico en todo rechazo: distinguirlos permitiría enumerar."""
    registry.register(spec_lectura())
    anonima = Session(role=Role.ANONYMOUS, verified=False)

    with pytest.raises(ToolDenied) as rol:
        registry.invoke("leer", anonima)
    with pytest.raises(ToolDenied) as inexistente:
        registry.invoke("no_existe", sesion_verificada())

    assert rol.value.mensaje_cliente == inexistente.value.mensaje_cliente
    assert rol.value.mensaje_cliente == MENSAJE_GENERICO_RECHAZO
    # El código interno sí distingue, para poder diagnosticar.
    assert rol.value.razon is not inexistente.value.razon


# ─────────────────────────────────────────────────────────────────────────────
# El permiso se evalúa antes de ejecutar
# ─────────────────────────────────────────────────────────────────────────────


def test_rol_no_autorizado_no_llega_al_handler(registry):
    registry.register(spec_escritura(allowed_roles=frozenset({Role.HUMAN_AGENT})))
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("escribir", sesion_verificada(), {}, intencion="escalar")
    assert exc.value.razon is Rechazo.ROL_NO_AUTORIZADO
    assert handler_escritura.llamadas == 0


def test_el_rol_se_valida_antes_que_los_parametros(registry):
    """Un rol no autorizado no debe recibir diagnóstico sobre sus parámetros."""
    registry.register(
        spec_lectura(
            params=(Param("monto", float),),
            allowed_roles=frozenset({Role.HUMAN_AGENT}),
        )
    )
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("leer", sesion_verificada(), {"parametro_inventado": 1})
    assert exc.value.razon is Rechazo.ROL_NO_AUTORIZADO


def test_sesion_expirada_se_rechaza(registry):
    registry.register(spec_lectura())
    vencida = sesion_verificada(expires_at=time.time() - 1)
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("leer", vencida)
    assert exc.value.razon is Rechazo.SESION_EXPIRADA


def test_cliente_verificado_sin_customer_id_se_rechaza(registry):
    """Sesión marcada verificada pero sin id es un bug, no un permiso."""
    registry.register(spec_lectura())
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("leer", sesion_verificada(customer_id=None))
    assert exc.value.razon is Rechazo.SIN_CUSTOMER_ID


# ─────────────────────────────────────────────────────────────────────────────
# El cliente nunca elige de quién son los datos (F-007)
# ─────────────────────────────────────────────────────────────────────────────


def test_un_tool_no_puede_declarar_customer_id_como_parametro():
    """Se rechaza al registrar, no al invocar: el agujero no debe ser alcanzable."""
    with pytest.raises(ValueError, match="se inyecta desde la sesión"):
        spec_lectura(params=(Param("customer_id", str),))


def test_el_handler_recibe_el_customer_id_de_la_sesion(registry):
    registry.register(spec_lectura())
    resultado = registry.invoke("leer", sesion_verificada(customer_id="CUST-9"))
    assert resultado.data["customer_id"] == "CUST-9"


# ─────────────────────────────────────────────────────────────────────────────
# Coherencias que el spec no permite declarar
# ─────────────────────────────────────────────────────────────────────────────


def test_escritura_publica_es_imposible():
    with pytest.raises(ValueError, match="escritura no puede ser público"):
        spec_escritura(requires_auth=False)


def test_anonimo_no_puede_escribir():
    with pytest.raises(ValueError, match="`anonymous` no puede escribir"):
        spec_escritura(allowed_roles=frozenset({Role.ANONYMOUS, Role.CUSTOMER}))


def test_tool_sin_roles_no_es_registrable():
    with pytest.raises(ValueError, match="sin roles"):
        spec_lectura(allowed_roles=frozenset())


def test_no_se_registra_dos_veces_el_mismo_nombre(registry):
    registry.register(spec_lectura())
    with pytest.raises(ValueError, match="ya registrado"):
        registry.register(spec_lectura())


# ─────────────────────────────────────────────────────────────────────────────
# Parámetros tipados — el modelo no escribe SQL, escribe esto
# ─────────────────────────────────────────────────────────────────────────────


def test_parametro_no_declarado_se_rechaza(registry):
    registry.register(spec_lectura())
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("leer", sesion_verificada(), {"drop_table": "customers"})
    assert exc.value.razon is Rechazo.PARAMETRO_DESCONOCIDO


def test_parametro_requerido_faltante_se_rechaza(registry):
    registry.register(spec_lectura(params=(Param("product_type", str),)))
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("leer", sesion_verificada(), {})
    assert exc.value.razon is Rechazo.PARAMETRO_FALTANTE


def test_booleano_no_cuela_como_entero(registry):
    """`bool` es subclase de `int`: True no es 1 en un parámetro tipado."""
    registry.register(spec_lectura(params=(Param("plazo_meses", int),)))
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("leer", sesion_verificada(), {"plazo_meses": True})
    assert exc.value.razon is Rechazo.PARAMETRO_INVALIDO


def test_entero_valido_pasa(registry):
    registry.register(spec_lectura(params=(Param("plazo_meses", int),)))
    assert registry.invoke("leer", sesion_verificada(), {"plazo_meses": 48}).ok


def test_validador_de_dominio_se_aplica(registry):
    registry.register(
        spec_lectura(
            params=(
                Param(
                    "monto",
                    float,
                    valida=lambda v: None if v > 0 else "debe ser positivo",
                ),
            )
        )
    )
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("leer", sesion_verificada(), {"monto": -5.0})
    assert exc.value.razon is Rechazo.PARAMETRO_INVALIDO
    assert registry.invoke("leer", sesion_verificada(), {"monto": 5.0}).ok


def test_parametro_opcional_ausente_no_rompe(registry):
    registry.register(spec_lectura(params=(Param("canal", str, requerido=False),)))
    assert registry.invoke("leer", sesion_verificada(), {}).ok


# ─────────────────────────────────────────────────────────────────────────────
# Nada se cae en silencio (regla 4)
# ─────────────────────────────────────────────────────────────────────────────


def test_fallo_del_handler_devuelve_resultado_con_fallback(registry):
    registry.register(spec_lectura(handler=handler_que_explota))
    resultado = registry.invoke("leer", sesion_verificada())
    assert resultado.ok is False
    assert resultado.error == "RuntimeError"
    assert "asesor" in resultado.mensaje_cliente
    assert resultado.latencia_ms is not None


def test_un_fallo_no_aporta_valores_al_grounding(registry):
    """Si el tool falló, no ancló nada: la respuesta no puede citar cifras suyas."""
    registry.register(spec_lectura(handler=handler_que_explota))
    turno = TurnValues()
    turno.registrar(registry.invoke("leer", sesion_verificada()))
    assert turno.valores == []


def test_handler_que_no_devuelve_toolresult_se_trata_como_fallo(registry):
    registry.register(spec_lectura(handler=lambda **kw: {"ok": True}))
    resultado = registry.invoke("leer", sesion_verificada())
    assert resultado.ok is False
    assert resultado.error == "TypeError"


# ─────────────────────────────────────────────────────────────────────────────
# Idempotencia de las escrituras
# ─────────────────────────────────────────────────────────────────────────────


def test_un_reintento_no_abre_dos_casos(registry):
    registry.register(spec_escritura())
    sesion = sesion_verificada()
    primero = registry.invoke("escribir", sesion, {}, intencion="escalar")
    segundo = registry.invoke("escribir", sesion, {}, intencion="escalar")

    assert handler_escritura.llamadas == 1
    assert segundo.reintento is True
    assert primero.reintento is False
    assert segundo.data == primero.data


def test_la_clave_no_depende_del_jti_renovado():
    """El JWT dura 15 minutos; renovarlo no debe abrir un segundo caso."""
    payload = {"motivo": "sin_ingreso"}
    antes = Session(
        role=Role.CUSTOMER, verified=True, customer_id="C", jti="jti-1", conversation_id="conv-1"
    )
    despues = Session(
        role=Role.CUSTOMER, verified=True, customer_id="C", jti="jti-2", conversation_id="conv-1"
    )
    assert derivar_idempotency_key(antes, "escalar", payload) == derivar_idempotency_key(
        despues, "escalar", payload
    )


def test_otra_conversacion_si_abre_otro_caso():
    payload = {"motivo": "sin_ingreso"}
    a = Session(role=Role.CUSTOMER, verified=True, customer_id="C", conversation_id="conv-1")
    b = Session(role=Role.CUSTOMER, verified=True, customer_id="C", conversation_id="conv-2")
    assert derivar_idempotency_key(a, "escalar", payload) != derivar_idempotency_key(
        b, "escalar", payload
    )


def test_distinta_intencion_distinta_clave():
    s = Session(role=Role.CUSTOMER, verified=True, customer_id="C", conversation_id="conv-1")
    assert derivar_idempotency_key(s, "escalar", {}) != derivar_idempotency_key(s, "otra", {})


def test_la_clave_no_depende_del_orden_del_payload():
    s = Session(role=Role.CUSTOMER, verified=True, customer_id="C", conversation_id="conv-1")
    assert derivar_idempotency_key(s, "escalar", {"a": 1, "b": 2}) == derivar_idempotency_key(
        s, "escalar", {"b": 2, "a": 1}
    )


def test_sesion_sin_ancla_no_puede_escribir(registry):
    registry.register(spec_escritura())
    sin_ancla = Session(role=Role.CUSTOMER, verified=True, customer_id="C")
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("escribir", sin_ancla, {}, intencion="escalar")
    assert exc.value.razon is Rechazo.ESCRITURA_SIN_IDEMPOTENCIA


def test_escritura_sin_intencion_declarada_se_rechaza(registry):
    registry.register(spec_escritura())
    with pytest.raises(ToolDenied) as exc:
        registry.invoke("escribir", sesion_verificada(), {})
    assert exc.value.razon is Rechazo.ESCRITURA_SIN_IDEMPOTENCIA


# ─────────────────────────────────────────────────────────────────────────────
# El catálogo que ve el modelo
# ─────────────────────────────────────────────────────────────────────────────


def test_el_catalogo_por_rol_oculta_lo_no_autorizado(registry):
    registry.register(spec_lectura())
    registry.register(
        spec_escritura(
            name="publico",
            requires_auth=False,
            writes=False,
            allowed_roles=frozenset({Role.ANONYMOUS, Role.CUSTOMER}),
            handler=handler_lectura,
        )
    )
    assert registry.catalogo_para(Role.ANONYMOUS) == ["publico"]
    assert registry.catalogo_para(Role.CUSTOMER) == ["leer", "publico"]


def test_todo_rechazo_queda_registrado(registry):
    registry.register(spec_lectura())
    for _ in range(3):
        with pytest.raises(ToolDenied):
            registry.invoke("leer", Session(role=Role.ANONYMOUS))
    assert len(registry.rechazos) == 3
    assert all(r["razon"] == "role_not_allowed" for r in registry.rechazos)


def test_el_registro_de_rechazos_no_guarda_el_jti_en_claro(registry):
    registry.register(spec_lectura())
    with pytest.raises(ToolDenied):
        registry.invoke("leer", Session(role=Role.ANONYMOUS, jti="jti-secreto"))
    assert registry.rechazos[-1]["sesion"] != "jti-secreto"


# ─────────────────────────────────────────────────────────────────────────────
# Valores del turno — el contrato con AG-09
# ─────────────────────────────────────────────────────────────────────────────


def test_los_valores_se_acumulan_por_turno_y_se_limpian(registry):
    registry.register(spec_lectura())
    turno = TurnValues()
    turno.registrar(registry.invoke("leer", sesion_verificada()))
    assert 1234.56 in turno.valores
    assert turno.fuentes["leer"] == "noema_gold.customer_360"

    turno.limpiar()
    assert turno.valores == []
    assert turno.fuentes == {}


def test_la_ausencia_de_dato_no_es_un_cero(registry):
    """La política distingue «no hay pagos» de «cero pagos» (F-029)."""

    def sin_historial(session, params, contexto, idempotency_key):
        return ToolResult(
            tool="leer", ok=True, data=None, grounded_values=(), ausencias=("cuotas_pagadas",)
        )

    registry.register(spec_lectura(handler=sin_historial))
    turno = TurnValues()
    turno.registrar(registry.invoke("leer", sesion_verificada()))
    assert turno.valores == []
    assert "cuotas_pagadas" in turno.ausencias
