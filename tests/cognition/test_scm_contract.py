"""Pruebas de aceptación del Semantic Cognition Matrix.

Estas pruebas SON la definición de "terminado" para `agent/cognition/scm.py`.
Mientras el módulo esté sin implementar se saltan solas con un mensaje claro;
en cuanto `SemanticState` deje de lanzar NotImplementedError, corren de verdad.

Ejecutar:  pytest tests/cognition/ -v
Spec:      docs/07_scm_spec.md
Fixtures:  tests/fixtures/scm_inputs.json   (sin base de datos, sin LLM)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.cognition.scm import (
    ContradictionType,
    EpistemicStatus,
    SemanticState,
    Source,
    SourceLayer,
)

FIXTURES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "scm_inputs.json").read_text(encoding="utf-8")
)
CASES = {c["id"]: c for c in FIXTURES["cases"]}


def _implemented() -> bool:
    try:
        SemanticState().assert_fact("customer", "x", 1, Source(SourceLayer.TABLE, "t"), 1.0)
    except NotImplementedError:
        return False
    except Exception:
        return True
    return True


pytestmark = pytest.mark.skipif(
    not _implemented(),
    reason="SCM sin implementar todavía — es la tarea de Federico. Ver docs/07_scm_spec.md",
)


def build(case_id: str) -> SemanticState:
    """Construye un estado poblado con los hechos de una fixture."""
    case = CASES[case_id]
    state = SemanticState(intent=case["intent"])
    for f in case["facts"]:
        src = f["source"]
        state.assert_fact(
            subject=f["subject"],
            predicate=f["predicate"],
            value=f["value"],
            source=Source(
                layer=SourceLayer(src["layer"]),
                ref=src["ref"],
                version=src.get("version"),
            ),
            confidence=f.get("confidence", 1.0),
        )
    return state


# --------------------------------------------------------------- invariantes


def test_la_fuente_es_obligatoria():
    """Un hecho sin procedencia no es un hecho. Sin esto no se puede medir
    la tasa de aserciones sin soporte, que es el aporte del SCM."""
    with pytest.raises(ValueError):
        SemanticState().assert_fact("customer", "monthly_income", 100, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [-0.1, 1.1, 2.0])
def test_confianza_fuera_de_rango_falla(bad):
    with pytest.raises(ValueError):
        SemanticState().assert_fact(
            "customer", "monthly_income", 100, Source(SourceLayer.TABLE, "gold.customer_360"), bad
        )


def test_un_hecho_no_se_sobrescribe_en_silencio():
    """Dos valores distintos para el mismo (subject, predicate): ambos quedan
    registrados y aparece una contradicción. Perder el primero sería perder
    la evidencia de que el cliente dijo algo distinto a lo que dice la base."""
    s = SemanticState()
    s.assert_fact(
        "customer", "monthly_income", 5_000_000, Source(SourceLayer.LANGUAGE, "turn_1"), 0.5
    )
    s.assert_fact(
        "customer", "monthly_income", 1_200_000, Source(SourceLayer.TABLE, "gold.customer_360"), 1.0
    )

    snap = s.snapshot()
    incomes = [f for f in snap["facts"] if f["predicate"] == "monthly_income"]
    assert len(incomes) == 2, "los dos valores deben conservarse"
    assert len(s.contradictions()) >= 1


# ----------------------------------------------------------- casos completos


@pytest.mark.parametrize("case_id", list(CASES))
def test_evidencia_faltante_por_caso(case_id):
    state = build(case_id)
    assert state.missing_evidence() == set(CASES[case_id]["expected"]["missing_evidence"])


@pytest.mark.parametrize("case_id", list(CASES))
def test_numero_de_contradicciones_por_caso(case_id):
    state = build(case_id)
    assert len(state.contradictions()) == CASES[case_id]["expected"]["contradictions"]


@pytest.mark.parametrize("case_id", list(CASES))
def test_estado_epistemico_por_caso(case_id):
    state = build(case_id)
    assert state.snapshot()["epistemic_status"] == CASES[case_id]["expected"]["epistemic_status"]


@pytest.mark.parametrize(
    "case_id", [c for c in CASES if CASES[c]["expected"].get("contradiction_types")]
)
def test_tipo_de_contradiccion_por_caso(case_id):
    state = build(case_id)
    got = {c.type for c in state.contradictions()}
    want = {ContradictionType(t) for t in CASES[case_id]["expected"]["contradiction_types"]}
    assert want <= got, f"faltan tipos de contradicción: {want - got}"


def test_conflicto_gana_sobre_incompleto():
    """SCM-04 tiene evidencia faltante Y una contradicción. El estado debe ser
    CONFLICTED: una contradicción es peor que un dato ausente."""
    state = build("SCM-04-precondicion-violada")
    assert state.missing_evidence(), "el caso debe tener evidencia faltante"
    assert state.snapshot()["epistemic_status"] == EpistemicStatus.CONFLICTED.value


# ------------------------------------------------------------------ snapshot


def test_snapshot_es_serializable_a_json():
    """El snapshot se pinta tal cual en el panel Caja de Vidrio del frontend.
    Si no serializa, el jurado no lo ve."""
    snap = build("SCM-02-completo").snapshot()
    json.dumps(snap)  # no debe lanzar


def test_snapshot_trae_la_forma_acordada():
    snap = build("SCM-02-completo").snapshot()
    esperado = {"intent", "facts", "missing_evidence", "contradictions", "epistemic_status"}
    assert esperado <= set(snap)
    assert isinstance(snap["facts"], list) and snap["facts"]
    for f in snap["facts"]:
        assert {"subject", "predicate", "value", "confidence", "source"} <= set(f)
        assert {"layer", "ref"} <= set(f["source"])


def test_la_procedencia_sobrevive_al_snapshot():
    """Cada hecho debe poder responder de dónde salió y con qué versión.
    Es lo que permite auditar una respuesta del agente."""
    snap = build("SCM-02-completo").snapshot()
    band = next(f for f in snap["facts"] if f["predicate"] == "has_risk_band")
    assert band["source"]["layer"] == SourceLayer.MODEL.value
    assert band["source"]["ref"] == "noema_pd"
    assert band["source"]["version"] == "v3"
