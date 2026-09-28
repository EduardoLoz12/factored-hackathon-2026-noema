import json

import pytest

from agent.cognition.scm import SemanticState, Source, SourceLayer

SRC = Source(SourceLayer.TABLE, "gold.customers")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "1", None])
def test_bad_confidence(value):
    with pytest.raises(ValueError):
        SemanticState().assert_fact("customer", "x", 1, SRC, value)


@pytest.mark.parametrize("value", ["false", "true", 1, {}, False, None])
def test_identity_requires_boolean_true(value):
    state = SemanticState()
    state.assert_fact("customer", "identity_verified", value, SRC)
    assert "identity_verified" in state.missing_evidence()


def test_wrong_subject_cannot_verify_customer():
    state = SemanticState()
    state.assert_fact("product", "identity_verified", True, SRC)
    assert "identity_verified" in state.missing_evidence()


@pytest.mark.parametrize("value", [float("nan"), {"nested": float("inf")}, object(), {1, 2}])
def test_non_json_rejected(value):
    with pytest.raises(ValueError):
        SemanticState().assert_fact("customer", "x", value, SRC)


def test_mutation_cannot_change_evidence():
    state = SemanticState()
    value = {"a": [1]}
    state.assert_fact("customer", "x", value, SRC)
    value["a"].append(2)
    snap = state.snapshot()
    snap["facts"][0]["value"]["a"].append(3)
    assert state.snapshot()["facts"][0]["value"] == {"a": [1]}
    json.dumps(state.snapshot(), allow_nan=False)


@pytest.mark.parametrize("source", [None, {}, Source(SourceLayer.TABLE, ""), Source("table", "x")])
def test_invalid_sources(source):
    with pytest.raises(ValueError):
        SemanticState().assert_fact("customer", "x", 1, source)


def test_unknown_intent_requires_clarification():
    state = SemanticState(intent="UNKNOWN")
    assert state.missing_evidence() == {"intent"}
    assert state.snapshot()["epistemic_status"] == "INCOMPLETE"
