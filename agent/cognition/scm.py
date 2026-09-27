"""Semantic Cognition Matrix (SCM-lite).

Estado semántico tipado entre el lenguaje del cliente y la decisión del sistema.
Guarda qué sabe el agente, cómo lo sabe, qué le falta y si algo se contradice.

DUEÑO: Federico Vargas. Especificación completa en `docs/07_scm_spec.md`.

Contrato — exactamente cuatro métodos públicos. Ninguna otra parte del sistema
importa nada más de este módulo:

    assert_fact(subject, predicate, value, source, confidence) -> None
    missing_evidence() -> set[str]
    contradictions() -> list[Contradiction]
    snapshot() -> dict

El SCM **no decide nada**. Reporta. Quien decide es `agent/policies/eligibility_v1.yaml`.

Con SCM_ENABLED=false el sistema completo debe funcionar igual. Esa bandera es el
instrumento que permite medir el aporte del SCM como tercer brazo de la evaluación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "SemanticState",
    "Fact",
    "Source",
    "SourceLayer",
    "Contradiction",
    "ContradictionType",
    "EpistemicStatus",
    "REQUIRED_SLOTS",
]


class SourceLayer(StrEnum):
    """De qué capa del sistema proviene un hecho."""

    LANGUAGE = "language"  # inferido del texto del cliente — confianza baja
    TABLE = "table"  # leído de una tabla gold — confianza 1.0
    MODEL = "model"  # salida de un modelo entrenado
    POLICY = "policy"  # derivado del motor de reglas
    TOOL = "tool"  # devuelto por una herramienta del agente


@dataclass(frozen=True)
class Source:
    """Procedencia de un hecho. Obligatoria: sin fuente no hay hecho.

    Lo que hace medible la métrica de aserciones sin soporte es poder responder,
    para cualquier cosa que el agente afirme, de dónde salió y con qué versión.
    """

    layer: SourceLayer
    ref: str  # "gold.customer_360", "noema_pd", "eligibility_v1.yaml"
    version: str | None = None  # "v3", "2026-09-27", None si no aplica


@dataclass(frozen=True)
class Fact:
    """Una tripleta con procedencia y confianza."""

    subject: str
    predicate: str
    value: Any
    source: Source
    confidence: float = 1.0


class ContradictionType(StrEnum):
    VALUE_CONFLICT = "value_conflict"  # mismo (subject, predicate), valores distintos
    PROVENANCE_CONFLICT = "provenance_conflict"  # fuente fuerte vs fuente débil
    PRECONDITION_VIOLATION = "precondition_violation"  # falta un hecho requerido


@dataclass(frozen=True)
class Contradiction:
    type: ContradictionType
    left: Fact
    right: Fact | None = None
    detail: str = ""


class EpistemicStatus(StrEnum):
    COMPLETE = "COMPLETE"  # sin evidencia faltante y sin contradicciones
    INCOMPLETE = "INCOMPLETE"  # falta evidencia
    CONFLICTED = "CONFLICTED"  # hay contradicciones (gana sobre INCOMPLETE)


# Slots mínimos por intención. Mientras falte alguno, el orquestador pregunta
# en vez de decidir — es el comportamiento que el reto premia.
REQUIRED_SLOTS: dict[str, set[str]] = {
    "CREDIT_ELIGIBILITY": {
        "identity_verified",
        "requested_amount",
        "currency",
        "product_type",
    },
    "PRODUCT_INFO": {"product_type"},
}


@dataclass
class SemanticState:
    """Estado semántico de una conversación.

    Se instancia una vez por conversación y se va poblando turno a turno.
    """

    intent: str = "CREDIT_ELIGIBILITY"
    _facts: list[Fact] = field(default_factory=list)

    # ------------------------------------------------------------------ API

    def assert_fact(
        self,
        subject: str,
        predicate: str,
        value: Any,
        source: Source,
        confidence: float = 1.0,
    ) -> None:
        """Registra un hecho.

        Reglas:
        - `source` es obligatoria. Sin fuente -> ValueError.
        - `confidence` fuera de [0, 1] -> ValueError.
        - Un hecho NUNCA se sobrescribe en silencio: si llega un valor distinto
          para la misma (subject, predicate), ambos quedan y aparece una
          contradicción.
        """
        raise NotImplementedError("SCM: implementar assert_fact — docs/07_scm_spec.md §5.1")

    def missing_evidence(self) -> set[str]:
        """Slots requeridos por la intención que todavía no tienen hecho conocido.

        Un slot cuenta como presente si existe un hecho cuyo `predicate` lo cubre
        y cuyo valor no es None ni la cadena "UNKNOWN".
        """
        raise NotImplementedError("SCM: implementar missing_evidence — docs/07_scm_spec.md §5.2")

    def contradictions(self) -> list[Contradiction]:
        """Conflictos detectados. El SCM los reporta; no los resuelve."""
        raise NotImplementedError("SCM: implementar contradictions — docs/07_scm_spec.md §5.3")

    def snapshot(self) -> dict:
        """Estado serializable a JSON. Se pinta tal cual en el panel Caja de Vidrio.

        Forma esperada:
            {
              "intent": str,
              "facts": [
                 {"subject","predicate","value","confidence",
                  "source": {"layer","ref","version"}}
              ],
              "missing_evidence": [str, ...],
              "contradictions": [
                 {"type","detail","left": {...}, "right": {...} | None}
              ],
              "epistemic_status": "COMPLETE" | "INCOMPLETE" | "CONFLICTED"
            }
        """
        raise NotImplementedError("SCM: implementar snapshot — docs/07_scm_spec.md §5.4")
