"""VERIFY: la relectura que confirma que una acción ocurrió — AG-07.

El reto lo pide textual —«verify that actions actually happened», slide 11— y el brief
ya anotó que es **barato y casi nadie lo hará**. Por eso vale aislarlo acá en vez de
dejarlo repetido dentro de cada tool de escritura.

Tres razones para que sea un módulo y no dos bloques de código parecidos:

1. **La comparación tiene un solo criterio.** Antes vivía duplicada: el expediente
   comparaba un campo y la oferta cinco, con reglas distintas escritas aparte. Dos
   implementaciones de la misma garantía se desincronizan, y la que se queda atrás no
   avisa — simplemente deja de verificar.
2. **El resultado se mide.** Cada verificación se registra, así que `EV-06` puede
   dividir afirmaciones de acción tras relectura fallida entre **turnos que
   escribieron**, que es su denominador correcto.
3. **Falla cerrado.** Si la relectura lanza, el resultado es «no verificado». Nunca se
   interpreta una excepción como un éxito.

Lo que este módulo **no** hace: devolver lo que se intentó escribir. La relectura tiene
que viajar a la base. Una verificación que compara un objeto en memoria contra sí mismo
pasa siempre, incluso con la base caída.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

# Tolerancia al comparar importes releídos. La base guarda dobles y el redondeo de
# ida y vuelta puede mover el último centavo; una diferencia mayor es un problema real.
TOLERANCIA_IMPORTE = 0.01


class MotivoNoVerificado(str):
    """Marcadores de por qué una verificación no pasó. Son códigos, no mensajes."""

    AUSENTE = "no_encontrado"
    DISCREPANCIA = "campos_discrepantes"
    ERROR_DE_LECTURA = "error_al_releer"


@dataclass(frozen=True)
class Verificacion:
    """El resultado de releer. `ok` solo es True si la base devolvió lo esperado."""

    ok: bool
    accion: str
    referencia: str
    motivo: str | None = None
    campos_discrepantes: tuple[str, ...] = ()
    releido: Mapping[str, Any] | None = None

    def a_traza(self) -> dict[str, Any]:
        """Sin el contenido releído: puede llevar cifras del cliente."""
        return {
            "etapa": "VERIFY",
            "accion": self.accion,
            "referencia": self.referencia,
            "verificado": self.ok,
            "motivo": self.motivo,
            "campos_discrepantes": list(self.campos_discrepantes),
        }


def _iguales(esperado: Any, leido: Any) -> bool:
    """Compara con tolerancia solo entre números. Un tipo distinto es discrepancia."""
    if isinstance(esperado, bool) or isinstance(leido, bool):
        return esperado is leido
    if isinstance(esperado, (int, float)) and isinstance(leido, (int, float)):
        return abs(float(esperado) - float(leido)) <= TOLERANCIA_IMPORTE
    return esperado == leido


@dataclass
class Verificador:
    """Relee escrituras y lleva la cuenta. Una instancia por turno o por proceso."""

    # Contadores para `EV-06`. Son del proceso, no del cliente: no llevan PII.
    escrituras: int = 0
    verificadas: int = 0
    fallidas: int = 0
    _historial: list[Verificacion] = field(default_factory=list, repr=False)

    @property
    def historial(self) -> list[Verificacion]:
        return list(self._historial)

    @property
    def tasa_de_fallo(self) -> float | None:
        """Fallos sobre **escrituras**, no sobre turnos. `None` si no hubo escrituras.

        El denominador importa: dividir entre turnos totales haría que una tasa de cero
        fuera trivial en cuanto el sistema casi nunca escribe.
        """
        if not self.escrituras:
            return None
        return self.fallidas / self.escrituras

    def verificar(
        self,
        *,
        accion: str,
        referencia: str,
        esperado: Mapping[str, Any],
        releer: Callable[[], Mapping[str, Any] | None],
        campos: Sequence[str],
        extraer: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> Verificacion:
        """Relee y compara los `campos` que importan.

        `releer` es una función sin argumentos que **va a la base**. `extraer` saca el
        subdiccionario a comparar cuando lo releído lo anida (por ejemplo el `payload`
        de una fila del ledger).
        """
        self.escrituras += 1
        if not campos:
            raise ValueError(f"{accion}: verificar sin campos no verifica nada")
        try:
            leido = releer()
        except Exception as exc:
            # Falla cerrado: una excepción al releer no es un éxito.
            LOGGER.exception("relectura_fallo accion=%s tipo=%s", accion, type(exc).__name__)
            return self._anotar(
                Verificacion(
                    ok=False,
                    accion=accion,
                    referencia=referencia,
                    motivo=MotivoNoVerificado.ERROR_DE_LECTURA,
                )
            )
        if leido is None:
            LOGGER.error("relectura_sin_fila accion=%s ref=%s", accion, referencia)
            return self._anotar(
                Verificacion(
                    ok=False,
                    accion=accion,
                    referencia=referencia,
                    motivo=MotivoNoVerificado.AUSENTE,
                )
            )

        comparable = extraer(leido) if extraer is not None else leido
        discrepantes = tuple(
            campo for campo in campos if not _iguales(esperado.get(campo), comparable.get(campo))
        )
        if discrepantes:
            LOGGER.error(
                "relectura_discrepa accion=%s ref=%s campos=%s",
                accion,
                referencia,
                list(discrepantes),
            )
            return self._anotar(
                Verificacion(
                    ok=False,
                    accion=accion,
                    referencia=referencia,
                    motivo=MotivoNoVerificado.DISCREPANCIA,
                    campos_discrepantes=discrepantes,
                    releido=comparable,
                )
            )
        return self._anotar(
            Verificacion(ok=True, accion=accion, referencia=referencia, releido=comparable)
        )

    def _anotar(self, v: Verificacion) -> Verificacion:
        if v.ok:
            self.verificadas += 1
        else:
            self.fallidas += 1
        self._historial.append(v)
        return v

    def metricas(self) -> dict[str, Any]:
        """Lo que `EV-06` consume. Cada tasa con su denominador declarado."""
        return {
            "escrituras": self.escrituras,
            "verificadas_por_relectura": self.verificadas,
            "relecturas_fallidas": self.fallidas,
            "tasa_de_fallo_sobre_escrituras": self.tasa_de_fallo,
            "motivos": {
                m: sum(1 for v in self._historial if v.motivo == m)
                for m in (
                    MotivoNoVerificado.AUSENTE,
                    MotivoNoVerificado.DISCREPANCIA,
                    MotivoNoVerificado.ERROR_DE_LECTURA,
                )
                if any(v.motivo == m for v in self._historial)
            },
        }


# Verificador del proceso. Los tools de escritura lo usan; el arnés de evaluación lo
# reemplaza por uno limpio para contar por corrida.
VERIFICADOR = Verificador()


# Campos que se comparan en cada acción. Están acá y no dentro de cada tool para que
# se vea de un golpe qué se verifica y qué no.
CAMPOS_EXPEDIENTE = ("motivo", "customer_id", "conversation_id")
CAMPOS_OFERTA = (
    "producto",
    "plazo_meses",
    "monto_ofrecido_usd",
    "cuota_estimada_usd",
    "tasa_anual",
    "tea_pct",
)
