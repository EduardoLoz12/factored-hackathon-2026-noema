"""Acceso de lectura a las capas silver y gold — soporte de AG-04.

Dos razones para que esto sea un módulo y no una conexión suelta en cada tool:

1. **El modelo nunca emite SQL** (`docs/05_security.md` §4). Las consultas viven en
   los tools, parametrizadas, y pasan por acá. Un solo punto donde comprobar que no
   se interpola nada.
2. **La conversión a USD es un lugar donde un error no se ve.** El ingreso viaja en
   moneda local y equivocar la moneda cambia la cifra hasta 3 994 veces sin lanzar
   ninguna excepción (F-040). Que la tasa se busque en un solo sitio, con la fecha
   de corte, y se devuelva junto al importe convertido, es lo que hace la cuenta
   auditable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

LOGGER = logging.getLogger(__name__)

# F-040: el ingreso de `customers` no trae moneda y se deduce del país. Probado
# midiendo la mediana por país: convertida con su moneda da 2 283 · 2 301 · 2 310
# USD (CV 0.61 %); con cualquier moneda única, CV 151.9 %.
#
# **Solo para el ingreso.** Todo importe de producto usa su propio `currency`:
# Argentina tiene productos en ARS y en USD, Colombia en COP y en USD, y México
# —que no tiene ni un producto en MXN— cobra su ingreso en MXN.
MONEDA_POR_PAIS: dict[str, str] = {
    "Argentina": "ARS",
    "Colombia": "COP",
    "México": "MXN",
}

# Ventana sobre la que se toma la mediana de la tasa. Una mediana de 30 días
# absorbe el ruido diario sin arrastrar tendencia.
DIAS_VENTANA_FX = 30


class ConversionImposible(Exception):
    """No hay tasa con la que convertir. Nunca se sustituye por 1.0.

    Asumir paridad ante una tasa faltante convertiría 9 192 466 COP en 9 192 466
    USD. Falla cerrado: el tool se abstiene y lo dice.
    """


@dataclass
class AnalyticsStore:
    """Lectura de silver y gold. Solo `SELECT`, siempre con parámetros."""

    conexion: Any
    _cache_fx: dict[tuple[str, date], float] = field(default_factory=dict, repr=False)

    # ── consultas ───────────────────────────────────────────────────────────
    def filas(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        cur = self.conexion.execute(sql, list(params))
        columnas = [c[0] for c in cur.description]
        return [dict(zip(columnas, f, strict=True)) for f in cur.fetchall()]

    def una(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        filas = self.filas(sql, params)
        return filas[0] if filas else None

    # ── conversión a dólares ────────────────────────────────────────────────
    def tasa_a_usd(self, moneda: str, corte: date) -> float:
        """Mediana de la tasa a USD en los `DIAS_VENTANA_FX` días hasta el corte.

        Nunca mira después del corte: una cotización posterior sería fuga
        temporal, y `customer_360` ya trae una valuación cinco meses posterior al
        corte (F-036).
        """
        if not isinstance(moneda, str) or not moneda.strip():
            raise ConversionImposible("moneda vacía")
        moneda = moneda.strip().upper()
        if moneda == "USD":
            return 1.0
        clave = (moneda, corte)
        if clave in self._cache_fx:
            return self._cache_fx[clave]
        fila = self.una(
            """
            SELECT median(exchange_rate) AS tasa, count(*) AS n
            FROM noema_silver.stg_daily_exchange_rates
            WHERE source_currency = ? AND target_currency = 'USD'
              AND date > ? AND date <= ?
            """,
            (moneda, corte - timedelta(days=DIAS_VENTANA_FX), corte),
        )
        if not fila or not fila["n"] or fila["tasa"] is None or fila["tasa"] <= 0:
            raise ConversionImposible(f"sin tasa {moneda}->USD al corte {corte}")
        self._cache_fx[clave] = float(fila["tasa"])
        return self._cache_fx[clave]

    def a_usd(self, importe: float | None, moneda: str, corte: date) -> tuple[float | None, float]:
        """Convierte e informa la tasa usada. `None` entra y sale como `None`.

        Devolver la tasa no es decorativo: sin ella, una conversión silenciosa es
        indistinguible de un error de moneda (F-040).
        """
        tasa = self.tasa_a_usd(moneda, corte)
        if importe is None:
            return None, tasa
        return round(float(importe) * tasa, 2), tasa

    def moneda_del_pais(self, pais: str | None) -> str:
        """Moneda del ingreso. Un país no mapeado no se asume en dólares."""
        if pais is None or pais not in MONEDA_POR_PAIS:
            raise ConversionImposible(f"país sin moneda conocida: {pais!r}")
        return MONEDA_POR_PAIS[pais]


class MotivoCapacidad(StrEnum):
    """Por qué `predict_capacity` no entregó una cifra. Los tres se tratan distinto.

    Devolver `None` a secas era el bug que ADR-0009 corrigió: el motor añadía «el
    estimador no tenía historial suficiente» tanto si se abstuvo como si el modelo
    no cargó. Lo primero es un resultado válido; lo segundo es un fallo que **no
    puede aprobar nada** (regla 5).
    """

    # El estimador corrió y no tuvo historial suficiente. El 94 % de los casos.
    # Se procede con el margen de política y se declara.
    ABSTENCION = "abstencion"
    # ML-09 todavía no existe en el repo. Estado de desarrollo, NO de producción:
    # cuando `predictor.py` se publique, este motivo deja de ser alcanzable y su
    # lugar lo ocupa `ERROR_DE_CARGA`. Hay una prueba que lo recuerda.
    NO_CONFIGURADO = "no_configurado"
    # Está configurado y falló al cargar o al predecir. Falla cerrado: se abstiene
    # la decisión completa y se escala.
    ERROR_DE_CARGA = "error_de_carga"


@dataclass(frozen=True)
class Capacidad:
    """Resultado de `predict_capacity`. El motivo importa tanto como el valor."""

    valor_usd: float | None
    motivo: MotivoCapacidad | None = None

    @property
    def bloquea(self) -> bool:
        """Solo un fallo real bloquea. Abstenerse y no estar configurado, no."""
        return self.motivo is MotivoCapacidad.ERROR_DE_CARGA


@dataclass
class Evidencia:
    """Lo que los tools de lectura de **este turno** dejaron sobre la mesa.

    El orquestador (AG-06) la arma llamando a los tools uno por uno —así cada
    llamada queda en la traza y en el panel Caja de Vidrio— y se la pasa a
    `evaluate_eligibility`. El tool de decisión **no vuelve a consultar la base**:
    si lo hiciera, podría leer con filtros distintos a los que la traza muestra, y
    el anclaje de AG-09 dejaría de ser comprobable.
    """

    perfil: dict[str, Any] | None = None
    creditos: dict[str, Any] | None = None
    activos: dict[str, Any] | None = None
    pagos: dict[str, Any] | None = None
    actividad: dict[str, Any] | None = None
    capacidad: Capacidad | None = None
    # Lo que devolvió `evaluate_eligibility`. `record_offer_quote` busca aquí la
    # oferta que el modelo nombró: así el modelo elige **cuál** cotizar y las cifras
    # siguen saliendo de la política.
    decision: dict[str, Any] | None = None
    ausencias: tuple[str, ...] = ()

    def completa_para_elegibilidad(self) -> list[str]:
        """Qué falta para poder decidir. Vacío significa que se puede."""
        faltan = []
        if self.perfil is None:
            faltan.append("perfil")
        if self.creditos is None:
            faltan.append("creditos")
        if self.activos is None:
            faltan.append("activos")
        return faltan


@dataclass
class Contexto:
    """Lo que los handlers reciben del orquestador.

    Llega por el parámetro `contexto` del registro, no por los parámetros del tool:
    el modelo no elige la base de datos ni la fecha de corte.
    """

    analitica: AnalyticsStore
    corte: date
    politica: Any = None
    expedientes: Any = None
    # Evidencia acumulada del turno. La arma el orquestador; `evaluate_eligibility`
    # la consume y no consulta la base por su cuenta.
    evidencia: Evidencia | None = None


def abrir_analitica(ruta: str = "data/noema.duckdb") -> AnalyticsStore:
    """Conexión de solo lectura a la base analítica.

    `read_only=True` no es cortesía: `docs/05_security.md` §5 da a la API solo
    lectura sobre gold, y las escrituras van a otro store.
    """
    import duckdb

    return AnalyticsStore(conexion=duckdb.connect(ruta, read_only=True))
