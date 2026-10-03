"""Catálogo, evidencia de pago y decisión — AG-04, tools 5 a 9.

Cuatro de lectura y una de escritura. La de escritura (`record_offer_quote`) existe
por una razón de evaluación, no de negocio: sin ella el camino feliz no escribe nada
y la relectura que el reto premia nunca correría en el caso que el jurado prueba
primero (ADR-0009, decisión 3).

Lo que distingue a este módulo del de cliente: aquí vive la frontera entre traer
evidencia y **decidir**. `evaluate_eligibility` no consulta la base — consume la
evidencia que el orquestador ya recogió tool por tool, para que la traza muestre cada
lectura y el anclaje de AG-09 sea comprobable sobre esas mismas cifras.
"""

from __future__ import annotations

import logging

from agent.core.verifier import CAMPOS_OFERTA, VERIFICADOR
from agent.policies.engine import Cliente, ProductoDeAhorro, ProductoVigente
from agent.tools.ledger import EscrituraDuplicada
from agent.tools.registry import REGISTRY, Param, Role, Session, ToolResult, ToolSpec
from agent.tools.store import Capacidad, Contexto, Evidencia, MotivoCapacidad

LOGGER = logging.getLogger(__name__)

# Un pago es una transacción de tipo `Pago` **aprobada**. `Declined` y `Reversed`
# no son pagos, y `Pending` todavía no lo es.
TIPO_PAGO = "Pago"
ESTADO_APROBADO = "Approved"


# ─────────────────────────────────────────────────────────────────────────────
# 5 · get_product_catalog
# ─────────────────────────────────────────────────────────────────────────────
def _get_product_catalog(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Condiciones de oferta, leídas de la política versionada.

    **No** lee `noema_gold.product_policy`: esa tabla está entera en NULL con
    `policy_ready = false` y `policy_version = 'pending_team_policy'` — es el
    cascarón de DAT-11 esperando los valores. La autoridad es
    `agent/policies/eligibility_v1.yaml`, que ya los tiene y está versionado.

    Resuelve entero el intent `PRODUCT_INFO` sin tocar un dato personal, y por eso
    no exige sesión.
    """
    pol = contexto.politica
    if pol is None:
        return ToolResult(
            tool="get_product_catalog",
            ok=False,
            error="policy_unavailable",
            mensaje_cliente=(
                "No puedo consultar las condiciones de los productos ahora. "
                "Puedo derivarte con un asesor."
            ),
        )
    pedido = params.get("product_type")
    productos: list[dict] = []
    valores: list[float] = []
    for item in pol.catalogo:
        if pedido is not None and item["producto"] != pedido:
            continue
        plazos = pol._plazos_ofertables(item)
        # La TEA se declara: es el costo anual efectivo y no depende del plazo.
        from agent.policies.engine import tea_desde_nominal

        tea = round(tea_desde_nominal(float(item["tasa_anual"])), 2)
        productos.append(
            {
                "producto": item["producto"],
                "amortizacion": item.get("amortizacion"),
                "tasa_anual": float(item["tasa_anual"]),
                "tea_pct": tea,
                "plazos_ofertables": [int(x) for x in plazos],
                "monto_minimo_usd": float(item["monto_minimo_usd"]),
                "monto_maximo_usd": float(item["monto_maximo_usd"]),
                "segmentos": list(item["segmentos"]),
                "moneda": pol.cfg.get("calculo", {}).get("moneda", "USD"),
            }
        )
        valores.extend(
            [
                float(item["tasa_anual"]),
                tea,
                float(item["monto_minimo_usd"]),
                float(item["monto_maximo_usd"]),
                *[float(x) for x in plazos],
            ]
        )
    if pedido is not None and not productos:
        return ToolResult(
            tool="get_product_catalog",
            ok=True,
            data={"productos": [], "n": 0},
            ausencias=(f"producto_desconocido:{pedido}",),
            source="agent/policies/eligibility_v1.yaml",
        )
    return ToolResult(
        tool="get_product_catalog",
        ok=True,
        data={
            "productos": productos,
            "n": len(productos),
            "politica_version": pol.version,
            "corte": pol.corte.isoformat(),
        },
        grounded_values=tuple(valores),
        source="agent/policies/eligibility_v1.yaml",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6 · get_payment_history
# ─────────────────────────────────────────────────────────────────────────────
def _get_payment_history(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Pagos registrados por producto. **Hecho descriptivo: no decide nada.**

    Desde que R6_cumplimiento se retiró del YAML (F-038), esto no alimenta ninguna
    regla. El agente puede decir cuántos pagos registra un producto; no se concluye
    nada de ello, porque no existe calendario de vencimientos con el cual comparar
    (F-029, F-030).

    Lleva los tres filtros de coherencia de F-042 y **declara cuántas filas
    descartó por cada motivo**: «no tiene pagos» y «sus pagos son incoherentes» son
    dos cosas distintas que merecen dos respuestas distintas.
    """
    filas = contexto.analitica.filas(
        """
        SELECT p.product_id,
               count(t.transaction_id) FILTER (
                   WHERE t.transaction_status = ?
                     AND t.transaction_date <= ? AND t.process_date <= ?
                     AND t.transaction_date >= p.opening_date
               ) AS pagos,
               sum(t.amount_usd) FILTER (
                   WHERE t.transaction_status = ?
                     AND t.transaction_date <= ? AND t.process_date <= ?
                     AND t.transaction_date >= p.opening_date
               ) AS pagado_usd,
               max(t.transaction_date) FILTER (
                   WHERE t.transaction_status = ?
                     AND t.transaction_date <= ? AND t.process_date <= ?
                     AND t.transaction_date >= p.opening_date
               ) AS ultimo_pago,
               count(t.transaction_id) FILTER (
                   WHERE t.transaction_date < p.opening_date
               ) AS descartados_antes_de_apertura,
               count(t.transaction_id) FILTER (
                   WHERE t.transaction_status <> ?
               ) AS descartados_no_aprobados
        FROM noema_silver.stg_products p
        LEFT JOIN noema_silver.stg_transactions t
               ON t.product_id = p.product_id AND t.transaction_type = ?
        WHERE p.customer_id = ?
          AND p.product_id IN (SELECT unnest(?))
        GROUP BY p.product_id
        ORDER BY p.product_id
        """,
        (
            ESTADO_APROBADO,
            contexto.corte,
            contexto.corte,
            ESTADO_APROBADO,
            contexto.corte,
            contexto.corte,
            ESTADO_APROBADO,
            contexto.corte,
            contexto.corte,
            ESTADO_APROBADO,
            TIPO_PAGO,
            session.customer_id,
            list(params["product_ids"]),
        ),
    )
    historial: list[dict] = []
    ausencias: list[str] = []
    valores: list[float] = []
    for f in filas:
        n = int(f["pagos"] or 0)
        if n == 0:
            # Ausencia explícita, no cero: el 29 % de los productos no registra
            # pagos y eso no es «pagó cero veces» (F-029).
            ausencias.append(f"cuotas_pagadas:{f['product_id']}")
        historial.append(
            {
                "producto_id": f["product_id"],
                "pagos_registrados": n if n else None,
                "pagado_usd": round(float(f["pagado_usd"]), 2) if f["pagado_usd"] else None,
                "ultimo_pago": f["ultimo_pago"],
                "descartados_antes_de_apertura": int(f["descartados_antes_de_apertura"] or 0),
                "descartados_no_aprobados": int(f["descartados_no_aprobados"] or 0),
            }
        )
        if n:
            valores.append(n)
            if f["pagado_usd"]:
                valores.append(round(float(f["pagado_usd"]), 2))
    return ToolResult(
        tool="get_payment_history",
        ok=True,
        data={"historial": historial, "decide": False},
        grounded_values=tuple(valores),
        ausencias=tuple(ausencias),
        source="noema_silver.stg_transactions",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7 · get_last_real_activity
# ─────────────────────────────────────────────────────────────────────────────
def _get_last_real_activity(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """`max(transaction_date)` real por producto. Alimenta el aviso de inactividad.

    Existe como tool aparte porque la política **prohíbe el camino corto**:
    `last_updated` trae 6.42 % de valores posteriores al corte y
    `last_transaction_date` un 17.29 % de incoherencias (F-028). Aislar el cálculo
    correcto en una función cuyo único propósito es no usar la columna fácil lo hace
    auditable en un diff.

    Los tres filtros de F-042 cambian el veredicto activo/inactivo en el 9.07 % de
    los productos de crédito, así que no son defensivos: son el cálculo.
    """
    filas = contexto.analitica.filas(
        """
        SELECT p.product_id,
               max(t.transaction_date) FILTER (
                   WHERE t.transaction_status = ?
                     AND t.transaction_date <= ? AND t.process_date <= ?
                     AND t.transaction_date >= p.opening_date
               ) AS ultima_real,
               max(t.transaction_date) AS ultima_cruda,
               count(t.transaction_id) FILTER (
                   WHERE t.transaction_date < p.opening_date
               ) AS descartados_antes_de_apertura
        FROM noema_silver.stg_products p
        LEFT JOIN noema_silver.stg_transactions t ON t.product_id = p.product_id
        WHERE p.customer_id = ?
          AND p.product_id IN (SELECT unnest(?))
        GROUP BY p.product_id
        ORDER BY p.product_id
        """,
        (
            ESTADO_APROBADO,
            contexto.corte,
            contexto.corte,
            session.customer_id,
            list(params["product_ids"]),
        ),
    )
    actividad: list[dict] = []
    ausencias: list[str] = []
    for f in filas:
        real = f["ultima_real"]
        if real is None:
            ausencias.append(f"ultima_transaccion_real:{f['product_id']}")
        actividad.append(
            {
                "producto_id": f["product_id"],
                "ultima_transaccion_real": real,
                # Se guarda la cruda para poder explicar la diferencia, nunca para
                # usarla: es la que incluye las transacciones imposibles.
                "ultima_sin_filtrar": f["ultima_cruda"],
                "descartados_antes_de_apertura": int(f["descartados_antes_de_apertura"] or 0),
            }
        )
    return ToolResult(
        tool="get_last_real_activity",
        ok=True,
        data={"actividad": actividad},
        # Las fechas no son cifras que el GroundingChecker valide como números.
        grounded_values=(),
        ausencias=tuple(ausencias),
        source="noema_silver.stg_transactions",
    )


# ─────────────────────────────────────────────────────────────────────────────
# predict_capacity — NO es tool, por diseño
# ─────────────────────────────────────────────────────────────────────────────
def estimar_capacidad(contexto: Contexto, customer_id: str) -> Capacidad:
    """Capacidad de pago observada (ML-04). Vive **dentro** de la decisión.

    No es una herramienta que el modelo elija, porque la capacidad estimada solo
    puede **restringir** el margen (ADR-0006 punto 4): omitirla únicamente podría
    aflojar el criterio, y eso no puede quedar a criterio del LLM.

    Hoy devuelve `NO_CONFIGURADO`: `ml/serving/predictor.py` (ML-09) todavía no
    existe. **Eso es un estado de desarrollo, no de producción** — cuando ML-09 se
    publique, un fallo de carga tiene que devolver `ERROR_DE_CARGA`, que sí bloquea.
    `test_la_capacidad_no_configurada_es_deuda_declarada` lo recuerda.
    """
    try:
        from ml.serving.predictor import predict_capacity  # type: ignore[import-not-found]
    except ImportError:
        return Capacidad(valor_usd=None, motivo=MotivoCapacidad.NO_CONFIGURADO)
    try:
        valor = predict_capacity(customer_id, corte=contexto.corte)
    except Exception as exc:  # falla cerrado: no se aprueba nada
        LOGGER.exception("capacidad_error_de_carga tipo=%s", type(exc).__name__)
        return Capacidad(valor_usd=None, motivo=MotivoCapacidad.ERROR_DE_CARGA)
    if valor is None:
        return Capacidad(valor_usd=None, motivo=MotivoCapacidad.ABSTENCION)
    return Capacidad(valor_usd=float(valor))


# ─────────────────────────────────────────────────────────────────────────────
# 8 · evaluate_eligibility
# ─────────────────────────────────────────────────────────────────────────────
def _evaluate_eligibility(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Arma el `Cliente` con la evidencia del turno y llama a la política.

    No consulta la base. Si lo hiciera podría leer con filtros distintos a los que
    la traza muestra, y el anclaje de AG-09 dejaría de ser comprobable sobre las
    mismas cifras que el jurado ve en el panel.
    """
    pol = contexto.politica
    ev: Evidencia | None = contexto.evidencia
    if pol is None:
        return ToolResult(
            tool="evaluate_eligibility",
            ok=False,
            error="policy_unavailable",
            mensaje_cliente="No puedo evaluar tu solicitud ahora. Te derivo con un asesor.",
        )
    if ev is None or (faltan := ev.completa_para_elegibilidad()):
        return ToolResult(
            tool="evaluate_eligibility",
            ok=False,
            error="incomplete_evidence",
            data={"falta": faltan if ev is not None else ["evidencia"]},
            mensaje_cliente="Me falta información para evaluarte. Te derivo con un asesor.",
        )

    capacidad = ev.capacidad or estimar_capacidad(contexto, session.customer_id)
    if capacidad.bloquea:
        # Falla cerrado (`docs/05_security.md` §7): si el estimador está configurado
        # y falló, no se aprueba nada. Se escala y se dice.
        LOGGER.warning("elegibilidad_bloqueada_por_capacidad motivo=%s", capacidad.motivo)
        return ToolResult(
            tool="evaluate_eligibility",
            ok=True,
            data={
                "abstencion": True,
                "elegible": False,
                "motivos": [
                    "No podemos completar la evaluación en este momento. "
                    "Te derivamos con un asesor."
                ],
                "motivo_tecnico": capacidad.motivo.value,
            },
            ausencias=("capacidad_estimada_usd",),
            source="agent.policies.engine",
        )

    actividad = {
        a["producto_id"]: a.get("ultima_transaccion_real")
        for a in (ev.actividad or {}).get("actividad", [])
    }
    pagos = {
        h["producto_id"]: h.get("pagos_registrados") for h in (ev.pagos or {}).get("historial", [])
    }
    perfil = ev.perfil
    cliente = Cliente(
        customer_id=session.customer_id,
        ingreso_mensual_usd=perfil.get("ingreso_mensual_usd"),
        segmento=perfil.get("segmento"),
        alta=perfil.get("alta"),
        productos=tuple(
            ProductoVigente(
                tipo=p["tipo"],
                limite_usd=p.get("limite_usd"),
                tasa_anual=p.get("tasa_anual"),
                apertura=p["apertura"],
                vencimiento=p.get("vencimiento"),
                ultima_transaccion_real=actividad.get(p["producto_id"]),
                cuotas_pagadas=pagos.get(p["producto_id"]),
                saldo_usd=p.get("saldo_usd"),
                producto_id=p.get("producto_id"),
            )
            for p in ev.creditos.get("productos", [])
        ),
        ahorros=tuple(
            ProductoDeAhorro(tipo=a["tipo"], saldo_usd=a.get("saldo_usd"))
            for a in ev.activos.get("activos", [])
        ),
        capacidad_estimada_usd=capacidad.valor_usd,
    )

    decision = pol.evaluar(cliente, monto_pedido_usd=params.get("requested_amount_usd"))
    salida = decision.a_dict()
    # Lo que el agente puede pronunciar: los hechos de la política y los campos de
    # cada oferta. AG-09 valida contra este conjunto.
    valores: list[float] = []

    def recolectar(nodo):
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

    recolectar(salida["hechos"])
    recolectar(salida["productos_elegibles"])
    ausencias = list(ev.ausencias)
    if capacidad.valor_usd is None:
        ausencias.append("capacidad_estimada_usd")
    return ToolResult(
        tool="evaluate_eligibility",
        ok=True,
        data={**salida, "capacidad_motivo": capacidad.motivo.value if capacidad.motivo else None},
        grounded_values=tuple(valores),
        ausencias=tuple(dict.fromkeys(ausencias)),
        source="agent.policies.engine",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9 · record_offer_quote
# ─────────────────────────────────────────────────────────────────────────────
def _record_offer_quote(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Persiste la oferta cotizada y la **relee** antes de darla por buena.

    Por qué existe: con una sola escritura —el expediente— el camino feliz no
    escribía nada, y la relectura que el reto premia textualmente nunca habría
    corrido en el caso que el jurado prueba primero (ADR-0009, decisión 3). Con esto,
    `VERIFY` tiene relectura real en el 100 % de los turnos de elegibilidad.

    El modelo elige **cuál** oferta cotizar nombrando producto y plazo. Las cifras no
    las aporta: se buscan en la decisión que la política ya produjo. Si el par
    (producto, plazo) no está entre las ofertas, se rechaza — no se cotiza algo que
    la política no aprobó.
    """
    store = contexto.expedientes
    if store is None:
        return ToolResult(
            tool="record_offer_quote",
            ok=False,
            error="ledger_unavailable",
            mensaje_cliente="No pude registrar la oferta. Te derivo con un asesor.",
        )
    ev = contexto.evidencia
    ofertas = (ev.decision or {}).get("productos_elegibles", []) if ev else []
    if not ofertas:
        return ToolResult(
            tool="record_offer_quote",
            ok=False,
            error="no_offer_to_record",
            mensaje_cliente="Todavía no tengo una oferta que registrar.",
        )
    elegida = next(
        (
            o
            for o in ofertas
            if o.get("producto") == params["producto"]
            and int(o.get("plazo_meses", -1)) == int(params["plazo_meses"])
        ),
        None,
    )
    if elegida is None:
        # El modelo nombró algo que la política no ofreció. No se cotiza.
        LOGGER.warning(
            "oferta_inexistente producto=%s plazo=%s", params["producto"], params["plazo_meses"]
        )
        return ToolResult(
            tool="record_offer_quote",
            ok=False,
            error="offer_not_in_decision",
            mensaje_cliente=(
                "Esa combinación de producto y plazo no está entre las que puedo ofrecerte."
            ),
        )

    pol = contexto.politica
    payload = {
        **elegida,
        "politica_version": (ev.decision or {}).get("politica_version"),
        "corte": pol.corte.isoformat() if pol is not None else None,
    }
    try:
        action_id = store.insertar_accion(
            idempotency_key=idempotency_key or "",
            customer_id=session.customer_id or "",
            conversation_id=session.conversation_id or "",
            accion="record_offer_quote",
            payload=payload,
            politica_version=payload["politica_version"],
            corte=pol.corte if pol is not None else None,
        )
        reintento = False
    except EscrituraDuplicada:
        previo = store.accion_por_clave(idempotency_key or "")
        if previo is None:  # pragma: no cover
            raise
        action_id = previo["action_id"]
        reintento = True

    # VERIFY (AG-07). Mismo verificador que el expediente: un solo criterio de
    # comparación para las dos escrituras del sistema.
    verificacion = VERIFICADOR.verificar(
        accion="record_offer_quote",
        referencia=action_id,
        esperado=payload,
        releer=lambda: store.releer_accion(action_id, session.customer_id or ""),
        campos=CAMPOS_OFERTA,
        extraer=lambda fila: fila.get("payload") or {},
    )
    if not verificacion.ok:
        return ToolResult(
            tool="record_offer_quote",
            ok=False,
            error="readback_mismatch",
            data={
                "motivo_tecnico": verificacion.motivo,
                "campos_discrepantes": list(verificacion.campos_discrepantes),
            },
            mensaje_cliente=(
                "No pude confirmar el registro de la oferta, así que prefiero no "
                "dártela por cerrada. Te derivo con un asesor."
            ),
            source="action_ledger",
        )
    guardado = dict(verificacion.releido or {})
    return ToolResult(
        tool="record_offer_quote",
        ok=True,
        data={
            "action_id": action_id,
            "verificado_por_relectura": True,
            "reintento": reintento,
            "oferta": guardado,
        },
        # Las cifras que el agente puede pronunciar son las RELEÍDAS, no las que se
        # intentó escribir: lo que el cliente oye es lo que quedó registrado.
        grounded_values=tuple(
            float(guardado[k])
            for k in (
                "monto_ofrecido_usd",
                "cuota_estimada_usd",
                "tea_pct",
                "plazo_meses",
                "tasa_anual",
            )
            if isinstance(guardado.get(k), (int, float))
        ),
        source="action_ledger",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Registro
# ─────────────────────────────────────────────────────────────────────────────
def _lista_de_ids(v) -> str | None:
    if not isinstance(v, (list, tuple)) or not v:
        return "se espera una lista no vacía de identificadores"
    if len(v) > 50:
        return "demasiados productos"
    if not all(isinstance(x, str) and 3 <= len(x) <= 64 for x in v):
        return "identificador inválido"
    return None


def registrar(registry=REGISTRY) -> None:
    """Registra las cuatro de lectura y la decisión. `record_offer_quote` va aparte."""
    ya = set(registry.nombres())
    lectura = dict(
        module="credit",
        requires_auth=True,
        writes=False,
        allowed_roles=frozenset({Role.CUSTOMER, Role.HUMAN_AGENT, Role.EVAL_HARNESS}),
        source="noema_silver.stg_transactions",
    )

    if "get_product_catalog" not in ya:
        registry.register(
            ToolSpec(
                name="get_product_catalog",
                module="credit",
                descripcion=(
                    "Condiciones de oferta: tasa nominal, TEA, plazos ofertables, montos "
                    "mínimo y máximo, y segmentos habilitados."
                ),
                handler=_get_product_catalog,
                params=(Param("product_type", str, requerido=False),),
                # Sin datos personales: no exige sesión.
                requires_auth=False,
                writes=False,
                allowed_roles=frozenset(
                    {Role.ANONYMOUS, Role.CUSTOMER, Role.HUMAN_AGENT, Role.EVAL_HARNESS}
                ),
                source="agent/policies/eligibility_v1.yaml",
            )
        )
    if "get_payment_history" not in ya:
        registry.register(
            ToolSpec(
                name="get_payment_history",
                descripcion="Pagos aprobados por producto. Hecho descriptivo: no decide.",
                handler=_get_payment_history,
                params=(Param("product_ids", list, valida=_lista_de_ids),),
                **lectura,
            )
        )
    if "get_last_real_activity" not in ya:
        registry.register(
            ToolSpec(
                name="get_last_real_activity",
                descripcion="Fecha de la última transacción real y coherente por producto.",
                handler=_get_last_real_activity,
                params=(Param("product_ids", list, valida=_lista_de_ids),),
                **lectura,
            )
        )
    if "evaluate_eligibility" not in ya:
        registry.register(
            ToolSpec(
                name="evaluate_eligibility",
                descripcion=(
                    "Evalúa la elegibilidad con la política versionada sobre la evidencia "
                    "del turno. Devuelve hechos, motivos, avisos y ofertas por plazo."
                ),
                handler=_evaluate_eligibility,
                params=(
                    Param(
                        "requested_amount_usd",
                        float,
                        requerido=False,
                        valida=lambda v: None if v > 0 else "el monto debe ser positivo",
                    ),
                ),
                **{**lectura, "source": "agent.policies.engine"},
            )
        )
    if "record_offer_quote" not in ya:
        registry.register(
            ToolSpec(
                name="record_offer_quote",
                module="credit",
                descripcion=(
                    "Registra la oferta cotizada en el ledger y la relee para confirmar "
                    "que quedó asentada. El producto y el plazo deben estar entre los "
                    "que la política aprobó."
                ),
                handler=_record_offer_quote,
                params=(
                    Param("producto", str),
                    Param(
                        "plazo_meses",
                        int,
                        valida=lambda v: None if 1 <= v <= 480 else "plazo fuera de rango",
                    ),
                ),
                requires_auth=True,
                writes=True,
                allowed_roles=frozenset({Role.CUSTOMER, Role.HUMAN_AGENT, Role.EVAL_HARNESS}),
                source="action_ledger",
            )
        )
