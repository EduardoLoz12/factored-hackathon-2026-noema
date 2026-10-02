"""Store de escritura: expedientes y ledger de acciones — soporte de AG-04 y AG-07.

Dos tablas de **solo añadir**, en un archivo aparte de la base analítica (ADR-0012).
Sin `UPDATE` y sin `DELETE`: la inmutabilidad la garantiza que esas sentencias no
existan en este módulo.

Lo que hace que `AG-07` signifique algo está acá: `releer_caso` y `releer_accion`
**consultan la base**. Devolver el objeto que se acaba de construir en memoria sería
una verificación que pasa siempre, incluso con la base caída.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

LOGGER = logging.getLogger(__name__)

# Cada tabla declara su clave de idempotencia como UNIQUE. Eso —y no el caché en
# memoria del registro— es lo que impide que dos workers concurrentes abran dos
# casos para la misma intención. Ningún `if` detecta esa carrera.
ESQUEMA = (
    """
    CREATE TABLE IF NOT EXISTS cases (
        case_id          VARCHAR PRIMARY KEY,
        idempotency_key  VARCHAR NOT NULL UNIQUE,
        customer_id      VARCHAR NOT NULL,
        conversation_id  VARCHAR NOT NULL,
        intencion        VARCHAR NOT NULL,
        motivo           VARCHAR NOT NULL,
        expediente       VARCHAR NOT NULL,
        politica_version INTEGER,
        creado_en        TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_ledger (
        action_id        VARCHAR PRIMARY KEY,
        idempotency_key  VARCHAR NOT NULL UNIQUE,
        customer_id      VARCHAR NOT NULL,
        conversation_id  VARCHAR NOT NULL,
        accion           VARCHAR NOT NULL,
        payload          VARCHAR NOT NULL,
        politica_version INTEGER,
        corte            DATE,
        registrado_en    TIMESTAMP NOT NULL
    )
    """,
)


class EscrituraDuplicada(Exception):
    """La clave de idempotencia ya existe. No es un error: la acción ya ocurrió."""

    def __init__(self, clave: str) -> None:
        super().__init__(f"idempotency_key ya registrada: {clave[:12]}…")
        self.clave = clave


def _ahora() -> datetime:
    """UTC **sin** zona. Misma disciplina que el AccessGuard y por la misma razón:
    DuckDB guarda un datetime con zona como hora local en una columna naive, así que
    mezclar los dos lados corrompe cualquier comparación de tiempo (F-043). Acá no se
    comparan marcas todavía, pero la retención y el orden del ledger dependen de que
    sean lo que dicen ser."""
    return datetime.now(tz=UTC).replace(tzinfo=None)


def _json(valor: Any) -> str:
    """Serializa rechazando NaN e infinitos: no deben llegar a un expediente."""
    return json.dumps(valor, ensure_ascii=False, allow_nan=False, default=str)


@dataclass
class LedgerStore:
    """Expedientes y acciones. Solo `INSERT` y `SELECT`."""

    conexion: Any

    def crear_esquema(self) -> None:
        for sql in ESQUEMA:
            self.conexion.execute(sql)

    # ── escrituras ──────────────────────────────────────────────────────────
    def insertar_caso(
        self,
        *,
        idempotency_key: str,
        customer_id: str,
        conversation_id: str,
        intencion: str,
        motivo: str,
        expediente: dict[str, Any],
        politica_version: int | None,
    ) -> str:
        case_id = f"CASE-{uuid.uuid4().hex[:16].upper()}"
        try:
            self.conexion.execute(
                """
                INSERT INTO cases (case_id, idempotency_key, customer_id, conversation_id,
                                   intencion, motivo, expediente, politica_version, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    case_id,
                    idempotency_key,
                    customer_id,
                    conversation_id,
                    intencion,
                    motivo,
                    _json(expediente),
                    politica_version,
                    _ahora(),
                ],
            )
        except Exception as exc:
            if _es_conflicto(exc):
                raise EscrituraDuplicada(idempotency_key) from exc
            raise
        return case_id

    def insertar_accion(
        self,
        *,
        idempotency_key: str,
        customer_id: str,
        conversation_id: str,
        accion: str,
        payload: dict[str, Any],
        politica_version: int | None,
        corte: date | None,
    ) -> str:
        action_id = f"ACT-{uuid.uuid4().hex[:16].upper()}"
        try:
            self.conexion.execute(
                """
                INSERT INTO action_ledger (action_id, idempotency_key, customer_id,
                                           conversation_id, accion, payload,
                                           politica_version, corte, registrado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    action_id,
                    idempotency_key,
                    customer_id,
                    conversation_id,
                    accion,
                    _json(payload),
                    politica_version,
                    corte,
                    _ahora(),
                ],
            )
        except Exception as exc:
            if _es_conflicto(exc):
                raise EscrituraDuplicada(idempotency_key) from exc
            raise
        return action_id

    # ── relecturas: esto es AG-07 ───────────────────────────────────────────
    def releer_caso(self, case_id: str, customer_id: str) -> dict[str, Any] | None:
        """Viaje de ida y vuelta real a la base. El filtro por cliente no es opcional:
        un expediente solo se relee para su propio dueño."""
        return self._una(
            """
            SELECT case_id, idempotency_key, customer_id, conversation_id, intencion,
                   motivo, expediente, politica_version, creado_en
            FROM cases WHERE case_id = ? AND customer_id = ?
            """,
            (case_id, customer_id),
            campos_json=("expediente",),
        )

    def releer_accion(self, action_id: str, customer_id: str) -> dict[str, Any] | None:
        return self._una(
            """
            SELECT action_id, idempotency_key, customer_id, conversation_id, accion,
                   payload, politica_version, corte, registrado_en
            FROM action_ledger WHERE action_id = ? AND customer_id = ?
            """,
            (action_id, customer_id),
            campos_json=("payload",),
        )

    def caso_por_clave(self, idempotency_key: str) -> dict[str, Any] | None:
        """Para resolver un reintento sin abrir un segundo caso."""
        return self._una(
            """
            SELECT case_id, idempotency_key, customer_id, conversation_id, intencion,
                   motivo, expediente, politica_version, creado_en
            FROM cases WHERE idempotency_key = ?
            """,
            (idempotency_key,),
            campos_json=("expediente",),
        )

    def accion_por_clave(self, idempotency_key: str) -> dict[str, Any] | None:
        return self._una(
            """
            SELECT action_id, idempotency_key, customer_id, conversation_id, accion,
                   payload, politica_version, corte, registrado_en
            FROM action_ledger WHERE idempotency_key = ?
            """,
            (idempotency_key,),
            campos_json=("payload",),
        )

    def casos_abiertos(self, limite: int = 50) -> list[dict[str, Any]]:
        """Consola del asesor (`UI-05`). Sin filtro de cliente: es el rol humano."""
        cur = self.conexion.execute(
            """
            SELECT case_id, customer_id, intencion, motivo, politica_version, creado_en
            FROM cases ORDER BY creado_en DESC LIMIT ?
            """,
            [min(max(int(limite), 1), 500)],
        )
        columnas = [c[0] for c in cur.description]
        return [dict(zip(columnas, f, strict=True)) for f in cur.fetchall()]

    # ── interno ─────────────────────────────────────────────────────────────
    def _una(
        self, sql: str, params: tuple[Any, ...], campos_json: tuple[str, ...] = ()
    ) -> dict[str, Any] | None:
        cur = self.conexion.execute(sql, list(params))
        fila = cur.fetchone()
        if fila is None:
            return None
        columnas = [c[0] for c in cur.description]
        registro = dict(zip(columnas, fila, strict=True))
        for campo in campos_json:
            if isinstance(registro.get(campo), str):
                registro[campo] = json.loads(registro[campo])
        return registro


def _es_conflicto(exc: Exception) -> bool:
    """¿Es una violación de la restricción única? Se reconoce por el texto porque
    DuckDB no expone un código estable para esto."""
    texto = str(exc).lower()
    return "constraint" in texto or "duplicate" in texto or "unique" in texto


def abrir_ledger(ruta: str = "data/noema_ledger.duckdb") -> LedgerStore:
    """Store de escritura. Archivo aparte de la analítica (ADR-0012)."""
    import duckdb

    store = LedgerStore(conexion=duckdb.connect(ruta))
    store.crear_esquema()
    return store


def abrir_ledger_en_memoria() -> LedgerStore:
    """Para pruebas: la suite no toca disco."""
    import duckdb

    store = LedgerStore(conexion=duckdb.connect(":memory:"))
    store.crear_esquema()
    return store
