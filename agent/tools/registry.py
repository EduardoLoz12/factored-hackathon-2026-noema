"""Registro de herramientas con allowlist por rol — AG-03.

Contrato de `docs/05_security.md` §3: cada tool declara `requires_auth`, `writes`
y `allowed_roles`; el ejecutor valida **antes** de invocar y registra todo intento
rechazado. Las de escritura son idempotentes por `idempotency_key`.

Tres propiedades que este módulo garantiza y que no se pueden delegar al prompt:

1. **El permiso se evalúa antes de ejecutar.** Ninguna validación ocurre dentro
   del handler, donde un error de implementación la saltaría.
2. **El cliente nunca elige de quién son los datos.** Un `ToolSpec` que declare un
   parámetro `customer_id` se rechaza al registrarse, no en tiempo de invocación:
   el id se inyecta desde la sesión. Cierra F-007.
3. **Toda cifra devuelta queda enumerada.** Cada `ToolResult` expone sus valores en
   `grounded_values`, que es el conjunto finito contra el que el `GroundingChecker`
   (AG-09) valida la respuesta final. Sin esto, «ninguna cifra sale del LLM» sería
   una promesa en vez de una propiedad verificable.

Nada se cae en silencio (regla 4): el handler corre dentro de `try/except` y un
fallo se convierte en un `ToolResult` con error, nunca en una excepción que tumbe
el turno.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

LOGGER = logging.getLogger(__name__)

# El `customer_id` viaja dentro del JWT, nunca como parámetro. Si un tool lo
# declarara, el cliente podría pedir los datos de otro (F-007).
PARAMETROS_PROHIBIDOS = frozenset({"customer_id", "cliente_id", "subject_customer_id"})


class Role(StrEnum):
    """Roles de la allowlist. Cada uno existe porque hay un consumidor real.

    Ver ADR-0009. `ANONYMOUS` es la sesión antes de verificar identidad;
    `CUSTOMER` es el cliente verificado y solo alcanza sus propios datos;
    `HUMAN_AGENT` es el asesor que recibe un escalamiento; `EVAL_HARNESS` es el
    arnés de los tres brazos (EV-05), acotado a un store aislado.
    """

    ANONYMOUS = "anonymous"
    CUSTOMER = "customer"
    HUMAN_AGENT = "human_agent"
    EVAL_HARNESS = "eval_harness"


class Rechazo(StrEnum):
    """Razones de rechazo. Son códigos, no mensajes al cliente.

    El mensaje que ve el cliente es deliberadamente genérico: distinguir
    «no existe el tool» de «no tienes permiso» permitiría enumerar la superficie
    (mismo criterio que los mensajes idénticos de identidad, `docs/05_security.md` §2).
    """

    TOOL_DESCONOCIDO = "unknown_tool"
    ROL_NO_AUTORIZADO = "role_not_allowed"
    SESION_NO_VERIFICADA = "session_not_verified"
    SESION_EXPIRADA = "session_expired"
    SIN_CUSTOMER_ID = "session_without_customer_id"
    PARAMETRO_DESCONOCIDO = "unknown_parameter"
    PARAMETRO_FALTANTE = "missing_parameter"
    PARAMETRO_INVALIDO = "invalid_parameter"
    ESCRITURA_SIN_IDEMPOTENCIA = "write_without_idempotency_key"


MENSAJE_GENERICO_RECHAZO = (
    "No puedo completar esa consulta en este momento. Si necesitas ayuda, "
    "puedo derivarte con un asesor."
)


@dataclass(frozen=True)
class Session:
    """Sesión emitida por el AccessGuard (AG-05).

    `customer_id` está **dentro** de la sesión porque viene dentro del JWT. El
    cliente no lo envía nunca.
    """

    role: Role
    verified: bool = False
    customer_id: str | None = None
    jti: str | None = None
    conversation_id: str | None = None
    expires_at: float | None = None  # epoch segundos

    def vigente(self, ahora: float | None = None) -> bool:
        if self.expires_at is None:
            return True
        return (ahora if ahora is not None else time.time()) < self.expires_at


@dataclass(frozen=True)
class Param:
    """Parámetro tipado de un tool. El modelo no escribe SQL: escribe esto."""

    name: str
    tipo: type
    requerido: bool = True
    # Validador de dominio. Devuelve None si está bien, o el motivo si no.
    valida: Callable[[Any], str | None] | None = None


@dataclass
class ToolResult:
    """Resultado de un tool.

    `grounded_values` es el contrato con AG-09: todo número y todo dato personal
    que este resultado pone a disposición de la redacción. Si una cifra aparece en
    la respuesta final y no está acá, es huérfana y la respuesta se bloquea.

    `ausencias` es el contrato con la política: distingue «no hay dato» de «el dato
    es cero». La política necesita esa diferencia — el 29 % de los productos no
    registra pagos (F-029) y eso no es cero pagos, es ausencia de historial.
    """

    tool: str
    ok: bool
    data: Any = None
    grounded_values: tuple[Any, ...] = ()
    ausencias: tuple[str, ...] = ()
    source: str | None = None
    error: str | None = None
    mensaje_cliente: str | None = None
    latencia_ms: float | None = None
    idempotency_key: str | None = None
    reintento: bool = False

    def a_traza(self) -> dict[str, Any]:
        """Lo que va a la traza del turno (AG-12). Sin PII en claro."""
        return {
            "tool": self.tool,
            "ok": self.ok,
            "source": self.source,
            "n_valores": len(self.grounded_values),
            "ausencias": list(self.ausencias),
            "error": self.error,
            "latencia_ms": self.latencia_ms,
            "idempotency_key": self.idempotency_key,
            "reintento": self.reintento,
        }


@dataclass(frozen=True)
class ToolSpec:
    """Declaración de una herramienta. Es el contrato de `docs/05_security.md` §3."""

    name: str
    module: str
    descripcion: str
    handler: Callable[..., ToolResult]
    params: tuple[Param, ...] = ()
    requires_auth: bool = True
    writes: bool = False
    allowed_roles: frozenset[Role] = frozenset({Role.CUSTOMER})
    source: str | None = None

    def __post_init__(self) -> None:
        # Coherencias que no pueden quedar a revisión humana.
        prohibidos = {p.name for p in self.params} & PARAMETROS_PROHIBIDOS
        if prohibidos:
            raise ValueError(
                f"{self.name}: el id de cliente se inyecta desde la sesión, no se "
                f"recibe como parámetro (F-007). Parámetros prohibidos: {sorted(prohibidos)}"
            )
        if len({p.name for p in self.params}) != len(self.params):
            raise ValueError(f"{self.name}: parámetros con nombre repetido")
        if self.writes and not self.requires_auth:
            raise ValueError(f"{self.name}: un tool de escritura no puede ser público")
        if self.writes and Role.ANONYMOUS in self.allowed_roles:
            raise ValueError(f"{self.name}: `anonymous` no puede escribir")
        if self.requires_auth and self.allowed_roles == frozenset({Role.ANONYMOUS}):
            raise ValueError(f"{self.name}: exige sesión pero solo admite `anonymous`")
        if not self.allowed_roles:
            raise ValueError(f"{self.name}: sin roles no es invocable por nadie")


class ToolDenied(Exception):
    """Rechazo de permiso. Lleva el código interno y el mensaje genérico al cliente."""

    def __init__(self, tool: str, razon: Rechazo) -> None:
        super().__init__(f"{tool}: {razon.value}")
        self.tool = tool
        self.razon = razon
        self.mensaje_cliente = MENSAJE_GENERICO_RECHAZO


def hash_pii(valor: str) -> str:
    """SHA-256 con sal de entorno, para logs y trazas (`docs/05_security.md` §5)."""
    sal = os.environ.get("PII_HASH_SALT", "")
    return hashlib.sha256(f"{sal}{valor}".encode()).hexdigest()[:16]


def derivar_idempotency_key(session: Session, intencion: str, payload: Mapping[str, Any]) -> str:
    """Clave de idempotencia de (sesión, intención, payload) — `docs/05_security.md` §3.

    La parte de «sesión» es `conversation_id`, **no** el `jti` del JWT. Razón: el
    JWT dura 15 minutos y se renueva; si la clave dependiera del `jti`, un
    reintento después de renovar abriría un segundo caso para la misma intención,
    que es exactamente lo que la idempotencia tiene que impedir. El
    `conversation_id` vive mientras vive la conversación.
    """
    ancla = session.conversation_id or session.jti or ""
    if not ancla:
        raise ValueError("sesión sin ancla de idempotencia: falta conversation_id")
    partes = [ancla, intencion, *(f"{k}={payload[k]!r}" for k in sorted(payload))]
    return hashlib.sha256("\x1f".join(partes).encode()).hexdigest()


class ToolRegistry:
    """Catálogo cerrado de herramientas. El modelo solo puede nombrar lo que está acá."""

    def __init__(self) -> None:
        # Bitácora del turno: qué tool se llamó, con qué resultado y desde qué
        # fuente. No es el log —ese va a `logs/`— sino lo que el panel de la
        # interfaz necesita para mostrar qué dato se recolectó, cuál se guardó y
        # cuál se validó. La vacía quien la consume, con `drenar`.
        self._bitacora: list[dict[str, Any]] = []
        self._tools: dict[str, ToolSpec] = {}
        self._rechazos: list[dict[str, Any]] = []
        self._ledger_idempotencia: dict[str, ToolResult] = {}

    # ── registro ────────────────────────────────────────────────────────────
    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ValueError(f"{spec.name}: ya registrado")
        self._tools[spec.name] = spec
        return spec

    def drenar(self) -> list[dict[str, Any]]:
        """Devuelve la bitácora acumulada y la vacía. Una llamada, un turno."""
        salida = self._bitacora
        self._bitacora = []
        return salida

    def _anotar(self, resultado: ToolResult, escribe: bool = False) -> ToolResult:
        self._bitacora.append(
            {
                "tool": resultado.tool,
                "ok": resultado.ok,
                "escribe": escribe,
                "fuente": resultado.source,
                "ms": round(resultado.latencia_ms or 0.0, 1),
                "cifras": len(resultado.grounded_values or ()),
                "ausencias": list(resultado.ausencias or ()),
                "error": resultado.error,
                "reintento": bool(getattr(resultado, "reintento", False)),
            }
        )
        return resultado

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def nombres(self) -> list[str]:
        return sorted(self._tools)

    def catalogo_para(self, role: Role) -> list[str]:
        """Lo que este rol puede nombrar. El prompt solo recibe esta lista."""
        return sorted(n for n, s in self._tools.items() if role in s.allowed_roles)

    @property
    def rechazos(self) -> list[dict[str, Any]]:
        """Intentos rechazados, en orden. Exigido por `docs/05_security.md` §3."""
        return list(self._rechazos)

    # ── autorización, antes de ejecutar ─────────────────────────────────────
    def autorizar(self, name: str, session: Session, params: Mapping[str, Any]) -> ToolSpec:
        """Valida y devuelve el spec, o lanza `ToolDenied`. No ejecuta nada.

        El orden importa: primero existencia y rol —lo que no depende del
        contenido—, después sesión, y al final los parámetros. Así un rol no
        autorizado nunca llega a que se le validen los datos que mandó.
        """
        spec = self._tools.get(name)
        if spec is None:
            raise self._rechazar(name, session, Rechazo.TOOL_DESCONOCIDO)
        if session.role not in spec.allowed_roles:
            raise self._rechazar(name, session, Rechazo.ROL_NO_AUTORIZADO)
        if spec.requires_auth:
            if not session.verified:
                raise self._rechazar(name, session, Rechazo.SESION_NO_VERIFICADA)
            if not session.vigente():
                raise self._rechazar(name, session, Rechazo.SESION_EXPIRADA)
            if session.role is Role.CUSTOMER and not session.customer_id:
                raise self._rechazar(name, session, Rechazo.SIN_CUSTOMER_ID)
        self._validar_params(spec, session, params)
        return spec

    def _validar_params(self, spec: ToolSpec, session: Session, params: Mapping[str, Any]) -> None:
        declarados = {p.name: p for p in spec.params}
        for clave in params:
            if clave not in declarados:
                raise self._rechazar(spec.name, session, Rechazo.PARAMETRO_DESCONOCIDO)
        for p in spec.params:
            if p.name not in params:
                if p.requerido:
                    raise self._rechazar(spec.name, session, Rechazo.PARAMETRO_FALTANTE)
                continue
            valor = params[p.name]
            # `bool` es subclase de `int`: un True donde se espera un entero es un
            # error de tipo, no un 1.
            if isinstance(valor, bool) is not (p.tipo is bool) or not isinstance(valor, p.tipo):
                raise self._rechazar(spec.name, session, Rechazo.PARAMETRO_INVALIDO)
            if p.valida is not None and p.valida(valor) is not None:
                raise self._rechazar(spec.name, session, Rechazo.PARAMETRO_INVALIDO)

    def _rechazar(self, name: str, session: Session, razon: Rechazo) -> ToolDenied:
        # Un permiso denegado también es información del turno: el panel tiene que
        # poder mostrar que el sistema se negó, no solo lo que sí hizo.
        registro = {
            "tool": name,
            "razon": razon.value,
            "role": session.role.value,
            "verified": session.verified,
            "sesion": hash_pii(session.jti) if session.jti else None,
            "ts": time.time(),
        }
        self._rechazos.append(registro)
        self._bitacora.append(
            {
                "tool": name,
                "ok": False,
                "escribe": False,
                "fuente": None,
                "ms": 0.0,
                "cifras": 0,
                "ausencias": [],
                "error": "denegado: " + razon.value,
                "reintento": False,
            }
        )
        LOGGER.warning(
            "tool_denied tool=%s razon=%s role=%s verified=%s",
            name,
            razon.value,
            session.role.value,
            session.verified,
        )
        return ToolDenied(name, razon)

    # ── invocación ──────────────────────────────────────────────────────────
    def invoke(
        self,
        name: str,
        session: Session,
        params: Mapping[str, Any] | None = None,
        *,
        intencion: str = "",
        contexto: Any = None,
    ) -> ToolResult:
        """Autoriza, ejecuta e inyecta el `customer_id` desde la sesión.

        Un fallo del handler **no** se propaga: se devuelve un `ToolResult` con
        error y mensaje al cliente (regla 4). Lo que sí se propaga es `ToolDenied`,
        porque un rechazo de permiso es una decisión del sistema, no una falla:
        el orquestador tiene que distinguirlos para no reintentar lo prohibido.
        """
        params = dict(params or {})
        spec = self.autorizar(name, session, params)

        clave: str | None = None
        if spec.writes:
            if not intencion:
                raise self._rechazar(name, session, Rechazo.ESCRITURA_SIN_IDEMPOTENCIA)
            try:
                clave = derivar_idempotency_key(session, intencion, params)
            except ValueError:
                raise self._rechazar(name, session, Rechazo.ESCRITURA_SIN_IDEMPOTENCIA) from None
            previo = self._ledger_idempotencia.get(clave)
            if previo is not None:
                # Un reintento no abre dos casos. Devuelve el resultado original.
                return self._anotar(ToolResult(**{**vars(previo), "reintento": True}), escribe=True)

        inicio = time.perf_counter()
        try:
            resultado = spec.handler(
                session=session, params=params, contexto=contexto, idempotency_key=clave
            )
            if not isinstance(resultado, ToolResult):
                raise TypeError(f"{name}: el handler no devolvió ToolResult")
        except Exception as exc:  # fallback visible, log con contexto, sin PII
            LOGGER.exception(
                "tool_failed tool=%s error_type=%s role=%s",
                name,
                type(exc).__name__,
                session.role.value,
            )
            return self._anotar(
                ToolResult(
                    tool=name,
                    ok=False,
                    error=type(exc).__name__,
                    mensaje_cliente=(
                        "Tuvimos un problema técnico al consultar esa información. "
                        "Puedo derivarte con un asesor."
                    ),
                    latencia_ms=(time.perf_counter() - inicio) * 1000,
                    idempotency_key=clave,
                ),
                escribe=bool(spec.writes),
            )

        resultado.latencia_ms = (time.perf_counter() - inicio) * 1000
        resultado.idempotency_key = clave
        if spec.source and resultado.source is None:
            resultado.source = spec.source
        if spec.writes and clave and resultado.ok:
            self._ledger_idempotencia[clave] = resultado
        return self._anotar(resultado, escribe=bool(spec.writes))


def comparar_secreto(a: str, b: str) -> bool:
    """Comparación en tiempo constante (`docs/05_security.md` §2)."""
    return hmac.compare_digest(a.encode(), b.encode())


# Registro del proceso. Los módulos de tools se registran contra este.
REGISTRY = ToolRegistry()


@dataclass
class TurnValues:
    """Valores devueltos por los tools de **un** turno.

    Es la memoria contra la que AG-09 valida. Se vacía en cada turno: una cifra
    traída dos turnos atrás no ancla la respuesta de ahora, porque el dato pudo
    cambiar y porque el reto pide que la afirmación sea verificable **en su turno**.
    """

    valores: list[Any] = field(default_factory=list)
    fuentes: dict[str, str] = field(default_factory=dict)
    ausencias: set[str] = field(default_factory=set)

    def registrar(self, resultado: ToolResult) -> None:
        if not resultado.ok:
            return
        self.valores.extend(resultado.grounded_values)
        self.ausencias.update(resultado.ausencias)
        if resultado.source:
            self.fuentes[resultado.tool] = resultado.source

    def limpiar(self) -> None:
        self.valores.clear()
        self.fuentes.clear()
        self.ausencias.clear()
