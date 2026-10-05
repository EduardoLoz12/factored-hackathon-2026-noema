"""El orquestador de las seis etapas — AG-06, la máquina de estados de ADR-0010.

Es el corazón de la tesis: **separar la conversación de la decisión**. El orquestador
decide qué etapa toca; el modelo de lenguaje solo redacta dentro de la etapa que ya se
eligió. Por eso este módulo **se testea sin LLM**, igual que el motor de política: si la
secuencia de etapas dependiera del modelo, no sería reproducible ni demostrable.

Tres propiedades que la forma garantiza, y que una tubería lineal no:

- **`UNDERSTAND` puede terminar el turno.** Si falta evidencia, se pregunta en vez de
  decidir. No es un error: es lo que el reto premia.
- **Una consulta de producto salta `DECIDE` y `ACT`.** Forzarla por la política
  produciría una abstención falsa en la métrica.
- **`ESCALATE` es destino de cinco aristas**, no el final de la fila. En todas, el
  sistema **no afirma** lo que no puede sostener.

Las etapas llevan el nombre textual del reto, salvo `IDENTIFY`, que es **nuestra** y se
marca como tal: el jurado tiene que poder mapear las cinco pedidas sin interpretar.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agent.cognition.scm import (
    REQUIRED_SLOTS,
    ContradictionType,
    SemanticState,
    Source,
    SourceLayer,
)
from agent.guardrails.grounding import CHECKER
from agent.guardrails.grounding import Resultado as Anclaje
from agent.tools.registry import Session, ToolDenied, ToolRegistry, TurnValues
from agent.tools.store import Contexto, Evidencia

LOGGER = logging.getLogger(__name__)

# Predicados que afirma el sistema y no el cliente. Si llegan entre los slots, no se
# vuelven a afirmar con procedencia de lenguaje: serían un conflicto de procedencia
# consigo mismos.
SISTEMA_NO_CLIENTE = frozenset({"identity_verified"})

# Los nombres son los de la slide 11, para que el jurado los mapee 1:1.
ETAPAS_DEL_RETO = ("UNDERSTAND", "DECIDE", "ACT", "VERIFY", "ESCALATE")


class Etapa(StrEnum):
    # Añadida por nosotros. No está en la slide 11 y se declara como extensión.
    IDENTIFY = "IDENTIFY"
    UNDERSTAND = "UNDERSTAND"
    DECIDE = "DECIDE"
    ACT = "ACT"
    VERIFY = "VERIFY"
    ESCALATE = "ESCALATE"

    @property
    def del_reto(self) -> bool:
        return self.value in ETAPAS_DEL_RETO


class Desenlace(StrEnum):
    """Cómo terminó el turno. Es lo que `EV-06` cuenta."""

    RESPUESTA = "respuesta"  # se contestó con grounding en verde
    PREGUNTA = "pregunta"  # faltaba evidencia: se preguntó en vez de decidir
    ESCALADO = "escalado"  # expediente abierto para un humano
    BLOQUEADO = "bloqueado"  # identidad bloqueada por intentos


# Fuentes estructuradas: entre dos de estas, un conflicto no se puede resolver solo.
ESTRUCTURADAS = frozenset(
    {SourceLayer.TABLE, SourceLayer.TOOL, SourceLayer.MODEL, SourceLayer.POLICY}
)

FUENTE_CLIENTE = Source(layer=SourceLayer.LANGUAGE, ref="mensaje_del_cliente")


@dataclass(frozen=True)
class Transicion:
    """Una arista recorrida, con la razón. Es lo que va a la traza y al panel."""

    etapa: Etapa
    razon: str
    es_extension_propia: bool = False

    def a_traza(self) -> dict[str, Any]:
        return {
            "etapa": self.etapa.value,
            "razon": self.razon,
            "del_reto": not self.es_extension_propia,
        }


@dataclass
class Turno:
    """El resultado de un turno. Sin prosa: la redacción es de otra capa."""

    desenlace: Desenlace
    etapas: list[Transicion] = field(default_factory=list)
    mensaje: str = ""
    pregunta_por: tuple[str, ...] = ()
    decision: dict[str, Any] | None = None
    ofertas: list[dict[str, Any]] = field(default_factory=list)
    case_id: str | None = None
    action_id: str | None = None
    cifras_ancladas: tuple[Any, ...] = ()
    ausencias: tuple[str, ...] = ()
    avisos: list[str] = field(default_factory=list)
    scm: dict[str, Any] | None = None

    @property
    def etapas_recorridas(self) -> list[str]:
        return [t.etapa.value for t in self.etapas]

    def a_traza(self) -> dict[str, Any]:
        """Lo que va a `logs/traces/`. Sin PII y sin prosa del cliente."""
        return {
            "desenlace": self.desenlace.value,
            "etapas": [t.a_traza() for t in self.etapas],
            "pregunta_por": list(self.pregunta_por),
            "n_ofertas": len(self.ofertas),
            "n_cifras_ancladas": len(self.cifras_ancladas),
            "ausencias": list(self.ausencias),
            "case_id": self.case_id,
            "action_id": self.action_id,
            "epistemic_status": (self.scm or {}).get("epistemic_status"),
        }


def scm_habilitado() -> bool:
    """La bandera que mide el aporte del SCM como tercer brazo (`EV-05`).

    Con `SCM_ENABLED=false` el **piso de seguridad no cambia** —identidad, política,
    relectura, grounding y abstención siguen igual, y la suite sigue en verde—, pero sí
    cambia la detección de contradicciones y la procedencia tipada: con la bandera
    apagada esas aristas no existen. Decir que no cambia nada haría inmedible el aporte.
    """
    return os.environ.get("SCM_ENABLED", "true").strip().lower() not in {
        "false",
        "0",
        "no",
    }


@dataclass
class Orquestador:
    """Conduce un turno por la máquina de estados. No llama al LLM."""

    registry: ToolRegistry
    contexto: Contexto

    # ── el turno ────────────────────────────────────────────────────────────
    def turno(
        self,
        session: Session,
        *,
        intencion: str,
        slots: dict[str, Any] | None = None,
        producto_elegido: tuple[str, int] | None = None,
        pide_humano: bool = False,
    ) -> Turno:
        """Un turno completo. `slots` ya viene extraído del mensaje del cliente.

        Que los slots lleguen como datos y no como texto es deliberado: el modelo
        extrae, el orquestador decide. Así la secuencia de etapas es reproducible y se
        puede probar arista por arista.
        """
        slots = dict(slots or {})
        etapas: list[Transicion] = []
        valores = TurnValues()

        # ── 0 · IDENTIFY ────────────────────────────────────────────────────
        if not session.verified or not session.customer_id:
            etapas.append(
                Transicion(
                    Etapa.IDENTIFY,
                    "sesión sin verificar: no sale ninguna información personal",
                    es_extension_propia=True,
                )
            )
            return Turno(
                desenlace=Desenlace.BLOQUEADO,
                etapas=etapas,
                mensaje=("Antes de hablar de tus productos necesito verificar tu identidad."),
            )
        etapas.append(Transicion(Etapa.IDENTIFY, "identidad verificada", es_extension_propia=True))

        if pide_humano:
            # Arista directa: el cliente siempre puede pedir una persona.
            return self._escalar(session, etapas, valores, "peticion_del_cliente", slots)

        # ── 1 · UNDERSTAND ──────────────────────────────────────────────────
        estado = SemanticState(intent=intencion) if scm_habilitado() else None
        if estado is not None:
            estado.assert_fact(
                "customer", "identity_verified", True, Source(SourceLayer.TOOL, "verify_identity")
            )
            for predicado, valor in slots.items():
                # `identity_verified` ya entró arriba con procedencia de tool, y es
                # estado de la sesión, no algo que el cliente nos cuente. Volver a
                # afirmarlo como hecho del cliente generaba un `provenance_conflict`
                # en **todos** los turnos: el 95 % de los casos del conjunto retenido
                # salía `CONFLICTED`, con lo cual el estado epistémico no informaba
                # nada y el panel lo mostraba siempre en rojo. Ver F-051.
                if predicado in SISTEMA_NO_CLIENTE:
                    continue
                estado.assert_fact("customer", predicado, valor, FUENTE_CLIENTE, 0.6)

        if intencion not in REQUIRED_SLOTS:
            etapas.append(Transicion(Etapa.UNDERSTAND, f"intención desconocida: {intencion}"))
            return self._escalar(
                session,
                etapas,
                valores,
                "contradiccion_irresoluble",
                slots,
                mensaje="No entendí qué necesitas. Te derivo con un asesor.",
            )

        evidencia: Evidencia | None = None
        if intencion == "CREDIT_ELIGIBILITY":
            evidencia = self._reunir_evidencia(session, valores, estado)
            if evidencia is None:
                etapas.append(Transicion(Etapa.UNDERSTAND, "no se pudo leer la evidencia"))
                return self._escalar(
                    session,
                    etapas,
                    valores,
                    "abstencion_de_politica",
                    slots,
                    mensaje="No pude consultar tus datos. Te derivo con un asesor.",
                )

        # Contradicciones antes de lo que falta: `CONFLICTED` precede a `INCOMPLETE`.
        if estado is not None:
            veredicto, detalle = self._resolver_contradicciones(estado)
            if veredicto == "escalar":
                etapas.append(Transicion(Etapa.UNDERSTAND, f"contradicción irresoluble: {detalle}"))
                return self._escalar(
                    session,
                    etapas,
                    valores,
                    "contradiccion_irresoluble",
                    slots,
                    scm=estado.snapshot(),
                )
            if detalle:
                etapas.append(Transicion(Etapa.UNDERSTAND, f"contradicción resuelta: {detalle}"))

        faltan = (
            estado.missing_evidence()
            if estado is not None
            else self._slots_faltantes(intencion, slots)
        )
        if faltan:
            # Preguntar en vez de decidir. No es un error.
            etapas.append(Transicion(Etapa.UNDERSTAND, f"falta evidencia: {sorted(faltan)}"))
            return Turno(
                desenlace=Desenlace.PREGUNTA,
                etapas=etapas,
                pregunta_por=tuple(sorted(faltan)),
                mensaje="Me falta un dato para poder responderte con precisión.",
                cifras_ancladas=tuple(valores.valores),
                ausencias=tuple(sorted(valores.ausencias)),
                scm=estado.snapshot() if estado is not None else None,
            )
        etapas.append(Transicion(Etapa.UNDERSTAND, "evidencia completa"))

        # Consulta de producto: no es una decisión de crédito ni una acción.
        if intencion == "PRODUCT_INFO":
            return self._informar_producto(session, etapas, valores, slots, estado)

        # ── 2 · DECIDE ──────────────────────────────────────────────────────
        self.contexto.evidencia = evidencia
        try:
            decision = self.registry.invoke(
                "evaluate_eligibility",
                session,
                {"requested_amount_usd": float(slots["requested_amount"])}
                if slots.get("requested_amount") is not None
                else {},
                contexto=self.contexto,
            )
        except ToolDenied as exc:
            etapas.append(Transicion(Etapa.DECIDE, f"decisión rechazada: {exc.razon.value}"))
            return self._escalar(session, etapas, valores, "abstencion_de_politica", slots)
        valores.registrar(decision)
        if not decision.ok:
            etapas.append(Transicion(Etapa.DECIDE, f"no se pudo decidir: {decision.error}"))
            return self._escalar(session, etapas, valores, "abstencion_de_politica", slots)

        datos = decision.data
        if estado is not None:
            estado.assert_fact(
                "customer",
                "elegibilidad",
                datos["elegible"],
                Source(SourceLayer.POLICY, "eligibility_v1.yaml", str(datos["politica_version"])),
            )
        if datos.get("abstencion"):
            etapas.append(Transicion(Etapa.DECIDE, "la política se abstuvo"))
            return self._escalar(
                session,
                etapas,
                valores,
                "abstencion_de_politica",
                slots,
                decision=datos,
                scm=estado.snapshot() if estado is not None else None,
            )
        etapas.append(
            Transicion(Etapa.DECIDE, "elegible" if datos["elegible"] else "no elegible, con motivo")
        )

        # ── 3 · ACT ─────────────────────────────────────────────────────────
        action_id = None
        self.contexto.evidencia.decision = datos
        ofertas = datos.get("productos_elegibles", [])
        if ofertas and producto_elegido is not None:
            producto, plazo = producto_elegido
            cotizacion = self.registry.invoke(
                "record_offer_quote",
                session,
                {"producto": producto, "plazo_meses": int(plazo)},
                intencion=f"cotizar:{intencion}",
                contexto=self.contexto,
            )
            valores.registrar(cotizacion)
            if not cotizacion.ok:
                # La relectura no confirmó: NO se afirma que la oferta quedó registrada.
                etapas.append(
                    Transicion(Etapa.ACT, f"cotización no confirmada: {cotizacion.error}")
                )
                etapas.append(Transicion(Etapa.VERIFY, "relectura fallida"))
                return self._escalar(
                    session, etapas, valores, "relectura_fallida", slots, decision=datos
                )
            action_id = cotizacion.data["action_id"]
            etapas.append(Transicion(Etapa.ACT, f"oferta cotizada a {plazo} meses"))
        else:
            etapas.append(Transicion(Etapa.ACT, "nada que escribir en este turno"))

        # ── 4 · VERIFY ──────────────────────────────────────────────────────
        huerfanas = self._anclaje(datos, valores)
        if huerfanas:
            etapas.append(Transicion(Etapa.VERIFY, f"cifras sin anclaje: {sorted(huerfanas)[:3]}"))
            return self._escalar(
                session, etapas, valores, "relectura_fallida", slots, decision=datos
            )
        etapas.append(
            Transicion(
                Etapa.VERIFY,
                "relectura confirmada y sin cifras huérfanas"
                if action_id
                else "sin cifras huérfanas",
            )
        )
        return Turno(
            desenlace=Desenlace.RESPUESTA,
            etapas=etapas,
            mensaje="Puedo responderte con estas cifras.",
            decision=datos,
            ofertas=ofertas,
            action_id=action_id,
            cifras_ancladas=tuple(valores.valores),
            ausencias=tuple(sorted(valores.ausencias)),
            avisos=list(datos.get("avisos", [])),
            scm=estado.snapshot() if estado is not None else None,
        )

    # ── piezas ──────────────────────────────────────────────────────────────
    def _slots_faltantes(self, intencion: str, slots: dict[str, Any]) -> set[str]:
        """Equivalente de `missing_evidence()` con la bandera del SCM apagada.

        Replica el mismo criterio: `None`, vacío y `UNKNOWN` cuentan como ausentes, y la
        identidad exige `True` explícito. Lo que **no** replica es la detección de
        contradicciones — nada lo hace, y eso es exactamente lo que el tercer brazo mide.
        """
        requeridos = set(REQUIRED_SLOTS[intencion])
        presentes = set()
        for predicado, valor in {"identity_verified": True, **slots}.items():
            if valor is None:
                continue
            if isinstance(valor, str) and valor.strip().upper() in {"", "UNKNOWN"}:
                continue
            if predicado == "identity_verified" and valor is not True:
                continue
            presentes.add(predicado)
        return requeridos - presentes

    def _resolver_contradicciones(self, estado: SemanticState) -> tuple[str, str]:
        """Las resuelve **el orquestador**, por tipo. El SCM reporta y no resuelve, y
        la firma del motor de política no las recibe.

        La trampa que hay que evitar: un cliente que se corrige —«quiero 5 000… mejor
        8 000»— genera un `VALUE_CONFLICT` legítimo que **no debe escalar**. Escalan los
        conflictos entre dos fuentes estructuradas, donde el sistema no tiene criterio
        para preferir una y afirmar sería inventar.
        """
        resueltas: list[str] = []
        for c in estado.contradictions():
            if c.type is ContradictionType.PRECONDITION_VIOLATION:
                return "escalar", f"falta un hecho requerido ({c.detail})"
            capas = {c.left.source.layer} | ({c.right.source.layer} if c.right else set())
            if c.type is ContradictionType.VALUE_CONFLICT and capas <= ESTRUCTURADAS:
                return "escalar", f"dos fuentes de la base discrepan ({c.detail})"
            # Una de las dos es el cliente: gana la fuente estructurada si la hay, y el
            # hecho más reciente si ambas son suyas. Se declara y el turno sigue.
            resueltas.append(c.type.value)
        return "seguir", ", ".join(sorted(set(resueltas)))

    def _reunir_evidencia(
        self, session: Session, valores: TurnValues, estado: SemanticState | None
    ) -> Evidencia | None:
        """Llama a los tools de lectura **uno por uno**, para que cada llamada quede en
        la traza y en el panel. Un tool que agrupara las cinco mostraría una sola."""
        try:
            perfil = self.registry.invoke("get_customer_profile", session, contexto=self.contexto)
            creditos = self.registry.invoke(
                "get_customer_credit_products", session, contexto=self.contexto
            )
            activos = self.registry.invoke("get_customer_assets", session, contexto=self.contexto)
        except ToolDenied as exc:
            LOGGER.warning("evidencia_denegada razon=%s", exc.razon.value)
            return None
        for r in (perfil, creditos, activos):
            valores.registrar(r)
        if not perfil.ok or not creditos.ok or not activos.ok:
            return None

        ids = [p["producto_id"] for p in creditos.data["productos"] if p.get("producto_id")]
        pagos = actividad = None
        if ids:
            pagos = self.registry.invoke(
                "get_payment_history", session, {"product_ids": ids}, contexto=self.contexto
            )
            actividad = self.registry.invoke(
                "get_last_real_activity", session, {"product_ids": ids}, contexto=self.contexto
            )
            valores.registrar(pagos)
            valores.registrar(actividad)

        if estado is not None:
            # Los hechos de la base entran con su procedencia. Si el cliente dijo un
            # ingreso distinto al registrado, acá aparece la contradicción.
            fuente = Source(SourceLayer.TOOL, "get_customer_profile")
            for predicado in ("ingreso_mensual_usd", "segmento"):
                if perfil.data.get(predicado) is not None:
                    estado.assert_fact("customer", predicado, perfil.data[predicado], fuente)

        return Evidencia(
            perfil=perfil.data,
            creditos=creditos.data,
            activos=activos.data,
            pagos=pagos.data if pagos is not None else {"historial": []},
            actividad=actividad.data if actividad is not None else {"actividad": []},
            ausencias=tuple(sorted(valores.ausencias)),
        )

    def _informar_producto(
        self,
        session: Session,
        etapas: list[Transicion],
        valores: TurnValues,
        slots: dict[str, Any],
        estado: SemanticState | None,
    ) -> Turno:
        """`PRODUCT_INFO` salta `DECIDE` y `ACT`: no es decisión ni acción."""
        catalogo = self.registry.invoke(
            "get_product_catalog",
            session,
            {"product_type": slots["product_type"]} if slots.get("product_type") else {},
            contexto=self.contexto,
        )
        valores.registrar(catalogo)
        if not catalogo.ok:
            etapas.append(Transicion(Etapa.UNDERSTAND, f"catálogo no disponible: {catalogo.error}"))
            return self._escalar(session, etapas, valores, "abstencion_de_politica", slots)
        etapas.append(
            Transicion(
                Etapa.VERIFY,
                "sin cifras huérfanas (consulta de producto: no pasa por la política)",
            )
        )
        return Turno(
            desenlace=Desenlace.RESPUESTA,
            etapas=etapas,
            mensaje="Estas son las condiciones del producto.",
            ofertas=catalogo.data["productos"],
            cifras_ancladas=tuple(valores.valores),
            ausencias=tuple(sorted(valores.ausencias)),
            scm=estado.snapshot() if estado is not None else None,
        )

    def _anclaje(self, datos: dict[str, Any], valores: TurnValues) -> set[float]:
        """Toda cifra de la respuesta tiene que venir de un tool **de este turno**.

        Es el suelo sobre el que `AG-09` construye: acá se valida la carga estructurada;
        allá, la prosa que el modelo redacta a partir de ella. Si una cifra no está
        anclada ya en este nivel, el problema es del sistema y no de la redacción.
        """
        anclados = {round(float(v), 4) for v in valores.valores if isinstance(v, (int, float))}
        huerfanas: set[float] = set()

        def recorrer(nodo: Any) -> None:
            if isinstance(nodo, bool) or nodo is None:
                return
            if isinstance(nodo, (int, float)):
                if round(float(nodo), 4) not in anclados:
                    huerfanas.add(float(nodo))
            elif isinstance(nodo, dict):
                for v in nodo.values():
                    recorrer(v)
            elif isinstance(nodo, (list, tuple)):
                for v in nodo:
                    recorrer(v)

        recorrer(datos.get("hechos"))
        recorrer(datos.get("productos_elegibles"))
        return huerfanas

    # ── AG-09: la prosa, con la regla de los dos intentos ───────────────────
    def redactar_y_verificar(
        self,
        turno: Turno,
        session: Session,
        redactar: Callable[[int, Anclaje | None], str],
        *,
        max_intentos: int = 2,
    ) -> tuple[Turno, str | None]:
        """Redacta la respuesta y comprueba su anclaje. Dos intentos y se escala.

        El checker de `AG-09` trabaja sobre la **prosa**: `_anclaje` ya validó la carga
        estructurada, pero el modelo puede escribir una cifra que no está en ella. Acá se
        comprueba lo que el cliente va a leer.

        `redactar(intento, anclaje_previo)` recibe el resultado del intento anterior para
        poder corregirse. Si el segundo falla, no se reescribe una tercera vez: se escala
        (`docs/05_security.md` §4). Insistir con un modelo que ya inventó dos veces
        gasta dinero y no mejora la respuesta.
        """
        umbrales = (
            list(self.contexto.politica.u.values()) if self.contexto.politica is not None else []
        )
        textos = []
        if turno.decision and isinstance(turno.decision.get("hechos"), dict):
            corte = turno.decision["hechos"].get("corte")
            if isinstance(corte, str):
                textos.append(corte)

        previo: Anclaje | None = None
        for intento in range(1, max_intentos + 1):
            texto = redactar(intento, previo)
            previo = CHECKER.revisar(
                texto,
                valores=list(turno.cifras_ancladas),
                textos=textos,
                umbrales=umbrales,
            )
            turno.etapas.append(
                Transicion(
                    Etapa.VERIFY,
                    f"anclaje de la respuesta, intento {intento}: "
                    + ("en verde" if previo.ok else f"{previo.motivo}"),
                )
            )
            if previo.ok:
                turno.mensaje = texto
                return turno, texto

        # Dos intentos fallidos: no se entrega la respuesta.
        LOGGER.error("grounding_agotado motivo=%s", previo.motivo if previo else None)
        escalado = self._escalar(
            session,
            turno.etapas,
            TurnValues(valores=list(turno.cifras_ancladas)),
            "relectura_fallida",
            {},
            decision=turno.decision,
            mensaje=("Prefiero no darte cifras que no pueda respaldar. Te derivo con un asesor."),
        )
        escalado.ofertas = turno.ofertas
        escalado.action_id = turno.action_id
        return escalado, None

    def _escalar(
        self,
        session: Session,
        etapas: list[Transicion],
        valores: TurnValues,
        motivo: str,
        slots: dict[str, Any],
        *,
        decision: dict[str, Any] | None = None,
        mensaje: str = "",
        scm: dict[str, Any] | None = None,
    ) -> Turno:
        """Destino de cinco aristas. En todas, el sistema **no afirma** lo que no sostiene."""
        if self.contexto.evidencia is not None and decision is not None:
            self.contexto.evidencia.decision = decision
        case_id = None
        try:
            caso = self.registry.invoke(
                "create_escalation_case",
                session,
                {"motivo": motivo},
                intencion=f"escalar:{motivo}",
                contexto=self.contexto,
            )
            if caso.ok:
                case_id = caso.data["case_id"]
            else:
                LOGGER.error("escalamiento_no_registrado error=%s", caso.error)
        except ToolDenied as exc:
            LOGGER.error("escalamiento_denegado razon=%s", exc.razon.value)
        etapas.append(Transicion(Etapa.ESCALATE, f"escalado por {motivo}"))
        return Turno(
            desenlace=Desenlace.ESCALADO,
            etapas=etapas,
            mensaje=mensaje
            or "Prefiero que esto lo vea un asesor. Ya le dejé tu caso con todo el detalle.",
            decision=decision,
            case_id=case_id,
            cifras_ancladas=tuple(valores.valores),
            ausencias=tuple(sorted(valores.ausencias)),
            avisos=list((decision or {}).get("avisos", [])),
            scm=scm,
        )
