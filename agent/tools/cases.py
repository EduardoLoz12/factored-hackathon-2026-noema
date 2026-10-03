"""Escalamiento: abrir el expediente y releerlo — AG-04, tools 10 y 11.

Las dos piezas del handoff que el reto pide: «structured handoff… not raw
transcripts» (slide 11). El expediente lleva **hechos verificados con su fuente**,
las acciones ejecutadas y las preguntas abiertas — no la conversación.

Dos decisiones que importan:

- **El modelo no escribe el expediente.** Lo arma el tool con la evidencia que los
  tools de lectura dejaron en el turno. El modelo solo elige el **motivo**, de una
  lista cerrada, y puede añadir la pregunta del cliente en texto, marcada como lo que
  es. Si el expediente viniera del modelo, sus «hechos verificados» serían lo que el
  modelo recuerde.
- **Los motivos son exactamente las flechas que entran a `ESCALATE`** en la máquina de
  estados de ADR-0010. No hay un escalamiento que el diagrama no explique.
"""

from __future__ import annotations

import logging
from enum import StrEnum

from agent.core.handoff import validar_o_degradar
from agent.core.verifier import CAMPOS_EXPEDIENTE, VERIFICADOR
from agent.tools.ledger import EscrituraDuplicada, LedgerStore
from agent.tools.registry import REGISTRY, Param, Role, Session, ToolResult, ToolSpec
from agent.tools.store import Contexto

LOGGER = logging.getLogger(__name__)


class MotivoEscalamiento(StrEnum):
    """Las cinco aristas que llegan a `ESCALATE` (ADR-0010), y nada más."""

    ABSTENCION_DE_POLITICA = "abstencion_de_politica"
    CONTRADICCION_IRRESOLUBLE = "contradiccion_irresoluble"
    RELECTURA_FALLIDA = "relectura_fallida"
    IDENTIDAD_BLOQUEADA = "identidad_bloqueada"
    PETICION_DEL_CLIENTE = "peticion_del_cliente"


MOTIVOS = tuple(m.value for m in MotivoEscalamiento)


def _expediente(contexto: Contexto, session: Session, pregunta: str | None) -> dict:
    """Arma el expediente con lo que los tools trajeron, no con lo que el modelo diga."""
    ev = contexto.evidencia
    hechos: dict = {}
    fuentes: dict[str, str] = {}
    ofertas: list[dict] = []
    ausencias: list[str] = []
    if ev is not None:
        if ev.perfil:
            hechos["perfil"] = {
                k: ev.perfil.get(k)
                for k in (
                    "segmento",
                    "ingreso_mensual_usd",
                    "moneda_origen",
                    "tasa_aplicada",
                    "antiguedad_cliente_meses",
                )
            }
            fuentes["perfil"] = "noema_silver.stg_customers"
        if ev.creditos:
            hechos["productos_credito"] = ev.creditos.get("productos", [])
            fuentes["productos_credito"] = "noema_silver.stg_products"
        if ev.activos:
            hechos["activos"] = ev.activos.get("activos", [])
            fuentes["activos"] = "noema_silver.stg_products"
        if ev.decision:
            hechos["decision"] = {
                k: ev.decision.get(k)
                for k in ("elegible", "abstencion", "politica_version", "hechos", "motivos")
            }
            fuentes["decision"] = "agent.policies.engine"
            ofertas = ev.decision.get("productos_elegibles", [])
        ausencias = list(ev.ausencias)
    return {
        "hechos_verificados": hechos,
        "fuentes": fuentes,
        "ofertas_cotizadas": ofertas,
        # Lo que el sistema NO pudo establecer. Va explícito: un humano que retoma el
        # caso necesita saber qué falta, no deducirlo de lo que no está.
        "evidencia_faltante": ausencias,
        # Texto del cliente, marcado como no verificado para que nadie lo lea como
        # hecho establecido.
        "pregunta_abierta_no_verificada": pregunta,
        "conversation_id": session.conversation_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 10 · create_escalation_case
# ─────────────────────────────────────────────────────────────────────────────
def _create_escalation_case(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Inserta el expediente. Idempotente por restricción única en la base."""
    store: LedgerStore | None = contexto.expedientes
    if store is None:
        return ToolResult(
            tool="create_escalation_case",
            ok=False,
            error="ledger_unavailable",
            mensaje_cliente=(
                "No pude registrar tu caso. Por favor contáctanos de nuevo en unos minutos."
            ),
        )
    pol_version = getattr(contexto.politica, "version", None)
    expediente = _expediente(contexto, session, params.get("pregunta_abierta"))

    # AG-08: el esquema se valida ANTES de guardar. Si el ensamblado falló, el caso se
    # abre igual con un expediente degradado y marcado — el escalamiento existe para
    # que una persona atienda al cliente, y negarlo por un bug nuestro lo castigaría a
    # él. Lo que no se hace es entregarlo como completo.
    expediente, validacion = validar_o_degradar(expediente, session.conversation_id)
    try:
        case_id = store.insertar_caso(
            idempotency_key=idempotency_key or "",
            customer_id=session.customer_id or "",
            conversation_id=session.conversation_id or "",
            intencion="escalar",
            motivo=params["motivo"],
            expediente=expediente,
            politica_version=pol_version,
        )
        reintento = False
    except EscrituraDuplicada:
        # El caso ya existe para esta conversación e intención: no se abre otro.
        previo = store.caso_por_clave(idempotency_key or "")
        if previo is None:  # pragma: no cover - solo si otro proceso lo borró
            raise
        case_id = previo["case_id"]
        reintento = True

    # VERIFY (AG-07). La comparación la hace el verificador, no este tool: un solo
    # criterio, y el resultado queda contado para `EV-06`. Si no coincide, NO se afirma
    # que el caso quedó abierto.
    verificacion = VERIFICADOR.verificar(
        accion="create_escalation_case",
        referencia=case_id,
        esperado={
            "motivo": params["motivo"],
            "customer_id": session.customer_id,
            "conversation_id": session.conversation_id,
        },
        releer=lambda: store.releer_caso(case_id, session.customer_id or ""),
        campos=CAMPOS_EXPEDIENTE,
    )
    if not verificacion.ok:
        return ToolResult(
            tool="create_escalation_case",
            ok=False,
            error="readback_mismatch",
            data={
                "motivo_tecnico": verificacion.motivo,
                "campos_discrepantes": list(verificacion.campos_discrepantes),
            },
            mensaje_cliente=(
                "No pude confirmar que tu caso quedó registrado. Te pido que nos "
                "contactes de nuevo para asegurarlo."
            ),
            source="cases",
        )
    leido = verificacion.releido or {}
    return ToolResult(
        tool="create_escalation_case",
        ok=True,
        data={
            "case_id": case_id,
            "motivo": leido["motivo"],
            "verificado_por_relectura": True,
            "esquema_ok": validacion.ok,
            "problemas_de_esquema": list(validacion.problemas),
            "reintento": reintento,
            "politica_version": leido["politica_version"],
        },
        # El identificador del caso es lo único que el agente pronuncia de acá, y es
        # texto, no cifra.
        grounded_values=(),
        source="cases",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 11 · get_escalation_case
# ─────────────────────────────────────────────────────────────────────────────
def _get_escalation_case(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Relee un expediente. Sin esto no hay `AG-07` ni consola para el asesor.

    El `customer_id` del filtro sale de la sesión: un cliente solo relee lo suyo. El
    asesor humano llega por el `case_id` que el expediente ya le entregó.
    """
    store: LedgerStore | None = contexto.expedientes
    if store is None:
        return ToolResult(
            tool="get_escalation_case",
            ok=False,
            error="ledger_unavailable",
            mensaje_cliente="No puedo consultar tu caso ahora.",
        )
    leido = store.releer_caso(params["case_id"], session.customer_id or "")
    if leido is None:
        # No se distingue «no existe» de «no es tuyo»: enumerar casos ajenos por la
        # diferencia de respuesta sería el mismo agujero que los mensajes de identidad.
        return ToolResult(
            tool="get_escalation_case",
            ok=True,
            data={"encontrado": False},
            ausencias=("expediente",),
            source="cases",
        )
    return ToolResult(
        tool="get_escalation_case",
        ok=True,
        data={
            "encontrado": True,
            "case_id": leido["case_id"],
            "motivo": leido["motivo"],
            "politica_version": leido["politica_version"],
            "creado_en": leido["creado_en"],
            "expediente": leido["expediente"],
        },
        grounded_values=(),
        source="cases",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Registro
# ─────────────────────────────────────────────────────────────────────────────
def registrar(registry=REGISTRY) -> None:
    ya = set(registry.nombres())
    if "create_escalation_case" not in ya:
        registry.register(
            ToolSpec(
                name="create_escalation_case",
                module="cases",
                descripcion=(
                    "Abre un expediente para un asesor humano, con los hechos verificados "
                    "del turno, las ofertas cotizadas y la evidencia que faltó."
                ),
                handler=_create_escalation_case,
                params=(
                    Param(
                        "motivo",
                        str,
                        valida=lambda v: None if v in MOTIVOS else "motivo fuera de la lista",
                    ),
                    Param(
                        "pregunta_abierta",
                        str,
                        requerido=False,
                        valida=lambda v: None if len(v) <= 500 else "demasiado largo",
                    ),
                ),
                requires_auth=True,
                writes=True,
                allowed_roles=frozenset({Role.CUSTOMER, Role.HUMAN_AGENT, Role.EVAL_HARNESS}),
                source="cases",
            )
        )
    if "get_escalation_case" not in ya:
        registry.register(
            ToolSpec(
                name="get_escalation_case",
                module="cases",
                descripcion="Relee un expediente ya abierto, para confirmar que quedó registrado.",
                handler=_get_escalation_case,
                params=(
                    Param(
                        "case_id",
                        str,
                        valida=lambda v: (
                            None if v.startswith("CASE-") else "identificador inválido"
                        ),
                    ),
                ),
                requires_auth=True,
                writes=False,
                allowed_roles=frozenset({Role.CUSTOMER, Role.HUMAN_AGENT, Role.EVAL_HARNESS}),
                source="cases",
            )
        )
