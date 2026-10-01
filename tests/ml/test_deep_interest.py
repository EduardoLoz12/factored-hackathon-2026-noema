"""Red profunda: aislamiento de test, artefactos y puerta de evidencia de política."""

from dataclasses import replace
from datetime import date

import duckdb
import joblib
import numpy as np
import pytest

from agent.policies.engine import Cliente, Politica, ProductoVigente
from ml.serving.client_analysis import VerifiedPolicyInput, analyze_client, policy_analysis
from ml.serving.product_advisor import predict_interest
from ml.training.deep_interest import train_deep
from ml.training.product_interest import FEATURES
from tests.ml.test_product_interest import example_frame


@pytest.fixture(scope="module")
def trained():
    return train_deep(example_frame(), {}, epochs=2)


def test_network_has_three_hidden_layers_and_serializes(trained, tmp_path):
    artifact, report = trained
    assert artifact["model"].named_steps["classifier"].hidden_layer_sizes == (32, 16, 8)
    assert len(report["learning_curve"]) == 2
    path = tmp_path / "deep.joblib"
    joblib.dump(artifact, path)
    result = predict_interest(joblib.load(path), "Tarjeta Crédito", "Email", 3, "2025-12-31")
    assert result["estimator"] == "deep_mlp"
    assert result["model_version"] == "deep_interest_v1"
    assert 0 <= result["probability"] <= 1


def test_test_labels_do_not_change_weights_checkpoint_or_champion(trained):
    artifact, report = trained
    frame = example_frame()
    mask = frame.send_date >= "2025-05-01"
    frame.loc[mask, "target"] = 1 - frame.loc[mask, "target"]
    other, other_report = train_deep(frame, {}, epochs=2)
    assert report["best_epoch"] == other_report["best_epoch"]
    assert artifact["recommended_model"] == other["recommended_model"]
    np.testing.assert_allclose(
        artifact["model"].predict_proba(frame[FEATURES]),
        other["model"].predict_proba(frame[FEATURES]),
    )


def verified_client():
    client = Cliente("test", 5000, "Plus", date(2020, 1, 1))
    return VerifiedPolicyInput(client, date(2025, 12, 31), "test_fixture", True)


def test_policy_matches_eduardo_engine_exactly():
    verified = verified_client()
    actual = policy_analysis("test", "2025-12-31", verified)
    expected = Politica.cargar().evaluar(verified.client).a_dict()
    expected.pop("customer_id")
    assert actual["decision"] == expected
    assert actual["is_bank_approval"] is False


def test_missing_limits_abstain_instead_of_skipping_debt():
    verified = verified_client()
    debt = ProductoVigente("Tarjeta Crédito", None, 30, date(2020, 1, 1))
    verified = replace(verified, client=replace(verified.client, productos=(debt,)))
    assert policy_analysis("test", "2025-12-31", verified)["reason"] == "missing_obligation_terms"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_income_cannot_produce_offer(value):
    verified = verified_client()
    verified = replace(verified, client=replace(verified.client, ingreso_mensual_usd=value))
    assert policy_analysis("test", "2025-12-31", verified)["status"] == "abstain"


def test_wrong_identity_cutoff_or_incomplete_history_abstains():
    verified = verified_client()
    assert policy_analysis("other", "2025-12-31", verified)["status"] == "abstain"
    assert policy_analysis("test", "2026-12-31", verified)["status"] == "abstain"
    assert (
        policy_analysis("test", "2025-12-31", replace(verified, obligations_complete=False))[
            "status"
        ]
        == "abstain"
    )


def test_capacity_can_only_restrict_offers():
    verified = verified_client()
    full = policy_analysis("test", "2025-12-31", verified)["decision"]
    low = replace(verified, client=replace(verified.client, capacidad_estimada_usd=100))
    restricted = policy_analysis("test", "2025-12-31", low)["decision"]
    assert restricted["hechos"]["margen_mensual_usd"] <= full["hechos"]["margen_mensual_usd"]


def test_unified_advisor_and_unknown_client(trained, tmp_path):
    path = tmp_path / "deep.joblib"
    joblib.dump(trained[0], path)
    with duckdb.connect() as conn:
        conn.execute("CREATE SCHEMA noema_silver")
        conn.execute("CREATE TABLE noema_silver.stg_customers AS SELECT 'test' customer_id")
        conn.execute("""CREATE TABLE noema_silver.stg_marketing_campaigns AS
            SELECT 'm' campaign_id, 'Tarjeta Crédito' promoted_product""")
        conn.execute("""CREATE TABLE noema_silver.stg_campaign_sends AS
            SELECT 'test' customer_id, 'm' campaign_id, 's' send_id,
            DATE '2024-01-01' send_date, DATE '2024-01-01' process_date, 'Email' send_channel""")
        conn.execute("""CREATE TABLE noema_silver.stg_products (
            customer_id VARCHAR, product_id VARCHAR, product_type VARCHAR, currency VARCHAR,
            credit_limit DOUBLE, opening_date DATE, last_updated TIMESTAMP,
            product_status VARCHAR)""")
        result = analyze_client(conn, "test", model_path=path, verified=verified_client())
        assert result["status"] == "experimental_analysis"
        assert result["product_analysis"][0]["deep_learning"]["estimator"] == "deep_mlp"
        assert result["new_product_quota"]["status"] == "policy_scenario"
        assert analyze_client(conn, "missing", model_path=path)["reason"] == (
            "unknown_or_duplicate_customer"
        )
