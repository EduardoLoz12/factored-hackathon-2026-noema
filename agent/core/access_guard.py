"""La puerta de identidad — AG-05, etapa `IDENTIFY` de ADR-0010.

Ninguna información personal sale antes de esta etapa. `docs/05_security.md` §2 le da
reglas propias, y por eso es una etapa con estado y no un middleware que devuelve 401:
tres intentos, bloqueo con espera creciente, mensajes idénticos en todo fallo,
comparación en tiempo constante, y sesión de 15 minutos con el `customer_id`
**dentro** del token.

Tres decisiones que importan:

- **La comparación no la hace este módulo**: la hace el tool `verify_identity`, invocado
  por el registro. Así el intento queda en la traza y la allowlist se aplica igual que a
  cualquier otra llamada. Acá vive lo que el tool no puede saber: cuántas veces ya se
  intentó.
- **El estado va en la base, no en memoria del proceso.** Una cuenta de intentos en
  memoria se reinicia con cada worker, y entonces el límite de tres no existe.
- **Las dos tablas son de solo añadir.** El número de intentos es un `count(*)` sobre
  las filas, no un contador que se actualiza. Además de evitar el `UPDATE`, deja la
  secuencia de intentos auditable.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from agent.tools.registry import Role, Session, ToolDenied, ToolRegistry

LOGGER = logging.getLogger(__name__)

# `docs/05_security.md` §2.
MAX_INTENTOS = 3
MINUTOS_DE_SESION = 15
# Ventana en la que se cuentan los intentos de una conversación.
VENTANA_INTENTOS_MINUTOS = 30
# Espera base del bloqueo, que se duplica con cada fallo por encima del límite.
SEGUNDOS_BASE_BLOQUEO = 30
# Tope del bloqueo. No es arbitrario: **no puede superar la ventana de intentos**.
# Un bloqueo más largo que la ventana haría que los fallos envejecieran y el contador
# volviera a cero mientras el cliente espera, así que la progresión se detendría sola.
# Poner un número mayor sería declarar una espera que el sistema no aplica.
SEGUNDOS_TOPE_BLOQUEO = VENTANA_INTENTOS_MINUTOS * 60
ALGORITMO = "HS256"

# Mensaje **idéntico** en todo fallo de credenciales. Distinguir «ese documento no
# existe» de «la fecha no coincide» permitiría enumerar qué documentos existen
# probando, que es justo lo que §2 quiere impedir.
MENSAJE_FALLO = (
    "Los datos no coinciden con nuestros registros. Revisa el tipo y número de "
    "documento y tu fecha de nacimiento."
)

ESQUEMA = (
    """
    CREATE TABLE IF NOT EXISTS identity_attempts (
        attempt_id      VARCHAR PRIMARY KEY,
        conversation_id VARCHAR NOT NULL,
        exito           BOOLEAN NOT NULL,
        intentado_en    TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        jti             VARCHAR PRIMARY KEY,
        conversation_id VARCHAR NOT NULL,
        customer_id     VARCHAR NOT NULL,
        rol             VARCHAR NOT NULL,
        emitida_en      TIMESTAMP NOT NULL,
        expira_en       TIMESTAMP NOT NULL
    )
    """,
)


class SinLlaveDeFirma(Exception):
    """No hay llave para firmar sesiones. Falla cerrado: no se emite ninguna.

    Firmar con una llave por defecto sería peor que no firmar, porque el sistema
    parecería autenticar.
    """


@dataclass(frozen=True)
class Resultado:
    """Lo que la puerta devuelve. `token` solo existe si se verificó."""

    verificado: bool
    token: str | None = None
    bloqueado: bool = False
    espera_segundos: int = 0
    intentos_restantes: int = 0
    mensaje: str = ""

    def a_traza(self) -> dict[str, Any]:
        """Sin PII y sin el token: lo que puede ir a `logs/traces/`."""
        return {
            "etapa": "IDENTIFY",
            "verificado": self.verificado,
            "bloqueado": self.bloqueado,
            "espera_segundos": self.espera_segundos,
            "intentos_restantes": self.intentos_restantes,
        }


def _ahora() -> datetime:
    """UTC **sin** zona, a propósito.

    DuckDB convierte un datetime con zona a hora LOCAL al guardarlo en una columna
    `TIMESTAMP` naive: se inserta 22:58 UTC y queda 17:58. Al releerlo como si fuera
    UTC, cada marca parecía cinco horas más vieja — y el bloqueo por intentos leía
    siempre como ya expirado, así que **el límite de tres no se disparaba nunca**
    (F-043).

    La disciplina es una sola: UTC naive de los dos lados, en lo que se escribe y en
    lo que se compara. Un `TIMESTAMPTZ` también serviría; lo que no sirve es mezclar.
    """
    return datetime.now(tz=UTC).replace(tzinfo=None)


def _epoch(valor: datetime) -> float:
    """Epoch UTC de una marca naive-UTC, sin pasar por la zona del servidor."""
    return valor.replace(tzinfo=UTC).timestamp()


def _sin_zona(valor: datetime) -> datetime:
    """Normaliza a UTC naive lo que vuelva de la base, venga con zona o sin ella."""
    if valor.tzinfo is not None:
        return valor.astimezone(UTC).replace(tzinfo=None)
    return valor


def _llave() -> str:
    llave = os.environ.get("JWT_SECRET", "")
    if len(llave) < 32:
        raise SinLlaveDeFirma("JWT_SECRET ausente o demasiado corta (mínimo 32 caracteres)")
    return llave


@dataclass
class AccessGuard:
    """Verifica identidad y emite la sesión. Etapa 0 del ciclo."""

    registry: ToolRegistry
    conexion: Any
    contexto: Any
    max_intentos: int = MAX_INTENTOS

    def crear_esquema(self) -> None:
        for sql in ESQUEMA:
            self.conexion.execute(sql)

    # ── intentos ────────────────────────────────────────────────────────────
    def _fallos_recientes(self, conversation_id: str) -> int:
        fila = self.conexion.execute(
            """
            SELECT count(*) FROM identity_attempts
            WHERE conversation_id = ? AND exito = FALSE AND intentado_en > ?
            """,
            [conversation_id, _ahora() - timedelta(minutes=VENTANA_INTENTOS_MINUTOS)],
        ).fetchone()
        return int(fila[0]) if fila else 0

    def _ultimo_fallo(self, conversation_id: str) -> datetime | None:
        fila = self.conexion.execute(
            """
            SELECT max(intentado_en) FROM identity_attempts
            WHERE conversation_id = ? AND exito = FALSE
            """,
            [conversation_id],
        ).fetchone()
        return fila[0] if fila and fila[0] is not None else None

    def _registrar_intento(self, conversation_id: str, exito: bool) -> None:
        self.conexion.execute(
            "INSERT INTO identity_attempts VALUES (?, ?, ?, ?)",
            [f"ATT-{uuid.uuid4().hex[:16]}", conversation_id, exito, _ahora()],
        )

    def _espera(self, fallos: int, ultimo: datetime | None) -> int:
        """Espera que queda, en segundos. **Se duplica con cada fallo extra.**

        Una primera versión la duplicaba cada tres fallos, y era casi lineal en la
        práctica: un intento bloqueado no se registra, así que tras el límite solo se
        suma un fallo por bloqueo cumplido y llegar al segundo ciclo costaba tres
        esperas. Con la base en el número de fallos, el tercero espera 30 s, el cuarto
        60 y el quinto 120 — que es lo que «backoff exponencial» quiere decir.
        """
        if fallos < self.max_intentos or ultimo is None:
            return 0
        total = min(
            SEGUNDOS_BASE_BLOQUEO * (2 ** (fallos - self.max_intentos)),
            SEGUNDOS_TOPE_BLOQUEO,
        )
        restante = total - (_ahora() - _sin_zona(ultimo)).total_seconds()
        return max(0, int(restante))

    # ── la puerta ───────────────────────────────────────────────────────────
    def verificar(
        self,
        conversation_id: str,
        *,
        document_type: str,
        document_number: str,
        date_of_birth: str,
    ) -> Resultado:
        """Tres factores. El teléfono **no** es uno de ellos.

        El 48.4 % de los clientes tiene prefijo telefónico de otro país (F-004), así
        que usarlo como factor sería un hallazgo en contra nuestra.
        """
        fallos = self._fallos_recientes(conversation_id)
        espera = self._espera(fallos, self._ultimo_fallo(conversation_id))
        if espera > 0:
            # El bloqueo sí se dice, con su espera: no revela nada sobre qué
            # documentos existen —solo sobre los intentos del propio solicitante— y
            # sin decirlo el cliente reintentaría a ciegas.
            LOGGER.warning("identidad_bloqueada fallos=%s espera=%s", fallos, espera)
            return Resultado(
                verificado=False,
                bloqueado=True,
                espera_segundos=espera,
                mensaje=(
                    "Por seguridad bloqueamos la verificación por unos minutos. "
                    "Vuelve a intentarlo más tarde o pide hablar con un asesor."
                ),
            )

        anonima = Session(role=Role.ANONYMOUS, verified=False, conversation_id=conversation_id)
        try:
            resultado = self.registry.invoke(
                "verify_identity",
                anonima,
                {
                    "document_type": document_type,
                    "document_number": document_number,
                    "date_of_birth": date_of_birth,
                },
                contexto=self.contexto,
            )
        except ToolDenied:
            # Un parámetro mal formado se cuenta como intento: si no, se podría
            # sondear sin gastar intentos.
            self._registrar_intento(conversation_id, exito=False)
            fallos += 1
            return self._fallo(conversation_id, fallos)

        if not resultado.ok or not resultado.data.get("verificado"):
            self._registrar_intento(conversation_id, exito=False)
            fallos += 1
            return self._fallo(conversation_id, fallos)

        self._registrar_intento(conversation_id, exito=True)
        customer_id = resultado.data["customer_id_interno"]
        token = self._emitir(conversation_id, customer_id)
        LOGGER.info("identidad_verificada conversation=%s", conversation_id[:8])
        return Resultado(
            verificado=True,
            token=token,
            intentos_restantes=self.max_intentos,
            mensaje="Identidad verificada.",
        )

    def _fallo(self, conversation_id: str, fallos: int) -> Resultado:
        restantes = max(0, self.max_intentos - fallos)
        espera = self._espera(fallos, self._ultimo_fallo(conversation_id))
        if restantes == 0:
            return Resultado(
                verificado=False,
                bloqueado=True,
                espera_segundos=espera,
                mensaje=(
                    "Por seguridad bloqueamos la verificación por unos minutos. "
                    "Vuelve a intentarlo más tarde o pide hablar con un asesor."
                ),
            )
        return Resultado(
            verificado=False,
            intentos_restantes=restantes,
            mensaje=MENSAJE_FALLO,
        )

    # ── sesión ──────────────────────────────────────────────────────────────
    def _emitir(self, conversation_id: str, customer_id: str) -> str:
        """JWT de 15 minutos con el `customer_id` **dentro**.

        El cliente nunca envía su identificador: si pudiera, podría pedir los datos de
        otro (F-007). Va firmado en el token y el registro lo inyecta desde la sesión.
        """
        jti = uuid.uuid4().hex
        emitida = _ahora()
        expira = emitida + timedelta(minutes=MINUTOS_DE_SESION)
        self.conexion.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            [jti, conversation_id, customer_id, Role.CUSTOMER.value, emitida, expira],
        )
        return jwt.encode(
            {
                "jti": jti,
                "sub": customer_id,
                "cid": conversation_id,
                "rol": Role.CUSTOMER.value,
                # `.timestamp()` sobre un naive lo interpreta como hora LOCAL, y
                # eso deja `iat` en el futuro: PyJWT rechaza el token con
                # `ImmatureSignatureError`. El epoch se calcula desde un valor con
                # zona explícita (F-043).
                "iat": int(_epoch(emitida)),
                "exp": int(_epoch(expira)),
            },
            _llave(),
            algorithm=ALGORITMO,
        )

    def sesion_desde_token(self, token: str) -> Session | None:
        """Valida firma, vigencia **y** existencia en la tabla. `None` si algo falla.

        La comprobación contra la tabla no es redundante: un token con firma válida
        cuya fila no está es un token emitido por otro despliegue, o por uno cuyo
        estado se perdió. Falla cerrado.
        """
        try:
            datos = jwt.decode(token, _llave(), algorithms=[ALGORITMO])
        except SinLlaveDeFirma:
            raise
        except Exception as exc:
            LOGGER.warning("token_invalido tipo=%s", type(exc).__name__)
            return None
        fila = self.conexion.execute(
            """
            SELECT customer_id, conversation_id, rol, expira_en
            FROM sessions WHERE jti = ? AND expira_en > ?
            """,
            [datos.get("jti", ""), _ahora()],
        ).fetchone()
        if fila is None:
            LOGGER.warning("sesion_no_vigente")
            return None
        customer_id, conversation_id, rol, expira = fila
        if customer_id != datos.get("sub"):
            # La fila y el token discrepan: no se confía en ninguno de los dos.
            LOGGER.error("sesion_incoherente_con_token")
            return None
        expira = _sin_zona(expira)
        return Session(
            role=Role(rol),
            verified=True,
            customer_id=customer_id,
            jti=datos["jti"],
            conversation_id=conversation_id,
            # `Session.vigente()` compara contra `time.time()`, que es epoch UTC.
            expires_at=_epoch(expira),
        )
