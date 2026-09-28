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

import copy
import json
import math
from dataclasses import dataclass, field
from enum import Enum
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


class SourceLayer(str, Enum):  # noqa: UP042
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


class ContradictionType(str, Enum):  # noqa: UP042
    VALUE_CONFLICT = "value_conflict"  # mismo (subject, predicate), valores distintos
    PROVENANCE_CONFLICT = "provenance_conflict"  # fuente fuerte vs fuente débil
    PRECONDITION_VIOLATION = "precondition_violation"  # falta un hecho requerido


@dataclass(frozen=True)
class Contradiction:
    type: ContradictionType
    left: Fact
    right: Fact | None = None
    detail: str = ""


class EpistemicStatus(str, Enum):  # noqa: UP042
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
        if not isinstance(source, Source) or not isinstance(source.layer, SourceLayer):
            raise ValueError("source debe ser una procedencia tipada")
        if not isinstance(source.ref, str) or not source.ref.strip():
            raise ValueError("source.ref es obligatorio")
        if source.version is not None and not isinstance(source.version, str):
            raise ValueError("source.version debe ser texto")
        if any(not isinstance(x, str) or not x.strip() for x in (subject, predicate)):
            raise ValueError("subject y predicate son obligatorios")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, int | float)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("confidence debe estar entre 0.0 y 1.0")
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("value debe ser JSON finito") from exc
        self._facts.append(Fact(subject, predicate, copy.deepcopy(value), source, confidence))

    def missing_evidence(self) -> set[str]:
        """La identidad requiere True explícito; UNKNOWN, vacío y None faltan."""
        if self.intent not in REQUIRED_SLOTS:
            return {"intent"}
        required = REQUIRED_SLOTS[self.intent]
        present = set()
        for fact in self._facts:
            value = fact.value
            if value is None or (
                isinstance(value, str) and value.strip().upper() in {"", "UNKNOWN"}
            ):
                continue
            if fact.predicate == "identity_verified":
                if fact.subject != "customer" or value is not True:
                    continue
            present.add(fact.predicate)
        return required - present

    def contradictions(self) -> list[Contradiction]:
        """Conflictos detectados. El SCM los reporta; no los resuelve."""
        contradictions = []

        # Check value conflicts and provenance conflicts
        grouped_facts = {}
        for f in self._facts:
            key = (f.subject, f.predicate)
            grouped_facts.setdefault(key, []).append(f)

        for facts in grouped_facts.values():
            if len(facts) > 1:
                # Compare all pairs
                for i in range(len(facts)):
                    for j in range(i + 1, len(facts)):
                        f1 = facts[i]
                        f2 = facts[j]
                        if type(f1.value) is not type(f2.value) or f1.value != f2.value:
                            contradictions.append(
                                Contradiction(
                                    type=ContradictionType.VALUE_CONFLICT,
                                    left=f1,
                                    right=f2,
                                    detail=f"Conflicto de valor: {f1.value} vs {f2.value}",
                                )
                            )
                        elif f1.source.layer != f2.source.layer and SourceLayer.LANGUAGE in {
                            f1.source.layer,
                            f2.source.layer,
                        }:
                            # provenance conflict
                            contradictions.append(
                                Contradiction(
                                    type=ContradictionType.PROVENANCE_CONFLICT,
                                    left=f1,
                                    right=f2,
                                    detail="Procedencia: lenguaje frente a fuente estructurada",
                                )
                            )

        # Check precondition violations
        # Example: product eligibility_decision requires customer identity_verified == True
        has_eligibility = any(f.predicate == "eligibility_decision" for f in self._facts)
        identity_verified = any(
            f.subject == "customer" and f.predicate == "identity_verified" and f.value is True
            for f in self._facts
        )

        if has_eligibility and not identity_verified:
            left = next(f for f in self._facts if f.predicate == "eligibility_decision")
            right = next((f for f in self._facts if f.predicate == "identity_verified"), None)
            contradictions.append(
                Contradiction(
                    type=ContradictionType.PRECONDITION_VIOLATION,
                    left=left,
                    right=right,
                    detail="eligibility_decision requires identity_verified=True",
                )
            )

        return copy.deepcopy(contradictions)

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

        def serialize_fact(f: Fact) -> dict:
            src = {"layer": f.source.layer.value, "ref": f.source.ref}
            if f.source.version is not None:
                src["version"] = f.source.version
            return {
                "subject": f.subject,
                "predicate": f.predicate,
                "value": copy.deepcopy(f.value),
                "confidence": f.confidence,
                "source": src,
            }

        facts_json = [serialize_fact(f) for f in self._facts]
        missing = sorted(list(self.missing_evidence()))

        contradictions_json = []
        for c in self.contradictions():
            c_dict = {"type": c.type.value, "detail": c.detail, "left": serialize_fact(c.left)}
            if c.right:
                c_dict["right"] = serialize_fact(c.right)
            else:
                c_dict["right"] = None
            contradictions_json.append(c_dict)

        if contradictions_json:
            epistemic_status = EpistemicStatus.CONFLICTED
        elif missing:
            epistemic_status = EpistemicStatus.INCOMPLETE
        else:
            epistemic_status = EpistemicStatus.COMPLETE

        return {
            "intent": self.intent,
            "facts": facts_json,
            "missing_evidence": missing,
            "contradictions": contradictions_json,
            "epistemic_status": epistemic_status.value,
        }
