"""Contratos de fuga temporal, cuotas y abstención del asesor comercial."""

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from ml.serving.product_advisor import advise, observed_quotas, predict_interest
from ml.training.product_interest import (
    FEATURES,
    VERSION,
    build_examples,
    evaluate,
    split_examples,
    train,
)


def test_point_in_time_history_and_maturation():
    conn = duckdb.connect()
    conn.execute("CREATE SCHEMA noema_silver")
    conn.execute("""CREATE TABLE noema_silver.stg_marketing_campaigns AS
        SELECT 'm' AS campaign_id, 'Tarjeta Crédito' AS promoted_product""")
    conn.execute("""CREATE TABLE noema_silver.stg_campaign_sends (
        send_id VARCHAR, customer_id VARCHAR, campaign_id VARCHAR, send_date DATE,
        process_date DATE, send_channel VARCHAR, had_conversion BOOLEAN, conversion_date DATE)""")
    conn.execute("""INSERT INTO noema_silver.stg_campaign_sends VALUES
        ('1','c','m','2025-01-01','2025-01-01','Email',true,'2025-01-03'),
        ('2','c','m','2025-01-01','2025-01-01','Email',false,NULL),
        ('3','c','m','2025-01-02','2025-03-01','Email',false,NULL),
        ('4','c','m','2025-02-01','2025-02-01','Email',false,NULL),
        ('5','c','m','2025-02-02','2025-01-01','Email',false,NULL),
        ('6','c','m','2025-12-20','2025-12-20','Email',false,NULL),
        ('7','c','m','2025-01-01','2026-01-01','Email',false,NULL)""")
    frame, audit = build_examples(conn)
    counts = frame.set_index("send_id").prior_sends.to_dict()
    assert counts == {"1": 0, "2": 0, "3": 2, "4": 2}
    assert frame.set_index("send_id").loc["1", "target"] == 1
    assert audit["invalid_process_order"] == 1
    assert not set(FEATURES) & {"had_conversion", "was_clicked", "conversion_date", "customer_id"}
    conn.close()


def example_frame():
    rng = np.random.default_rng(42)
    frames = []
    for date in ["2024-06-01", "2025-02-01", "2025-06-01"]:
        channel = np.tile(["Email", "SMS"], 200)
        frames.append(
            pd.DataFrame(
                {
                    "send_date": pd.Timestamp(date),
                    "promoted_product": "Tarjeta Crédito",
                    "send_channel": channel,
                    "prior_sends": rng.integers(0, 10, 400),
                    "send_month": pd.Timestamp(date).month,
                    "target": (rng.random(400) < np.where(channel == "Email", 0.7, 0.1)).astype(
                        int
                    ),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_training_holdout_does_not_change_selection_or_predictions(tmp_path):
    import joblib

    frame = example_frame()
    artifact, report = train(frame, {})
    changed = frame.copy()
    mask = changed.send_date >= "2025-05-01"
    changed.loc[mask, "target"] = 1 - changed.loc[mask, "target"]
    other, _ = train(changed, {})
    np.testing.assert_allclose(
        artifact["model"].predict_proba(frame[FEATURES]),
        other["model"].predict_proba(frame[FEATURES]),
    )
    path = tmp_path / "model.joblib"
    joblib.dump(artifact, path)
    restored = joblib.load(path)
    prediction = predict_interest(restored, "Tarjeta Crédito", "Email", 3, "2025-12-31")
    assert prediction["status"] == "experimental_estimate"
    assert 0 <= prediction["probability"] <= 1
    assert report["production_ready"] is False
    json.dumps(report, allow_nan=False)
    assert predict_interest(restored, "Unknown", "Email", 3, "2025-12-31")["status"] == "abstain"


def test_constant_predictions_have_unit_lift():
    metrics = evaluate([0, 0, 1, 0, 0, 1, 0, 0, 0, 0], np.repeat(0.2, 10))
    assert metrics["lift_top_10pct"] == pytest.approx(1)


def test_split_rejects_single_class():
    frame = example_frame()
    frame["target"] = 0
    with pytest.raises(ValueError, match="ambas clases"):
        split_examples(frame)


def test_quotas_preserve_currencies_and_reject_future_or_invalid_snapshots():
    rows = []
    for ident, currency, limit, updated in [
        ("a", "USD", 1000, "2025-11-01"),
        ("b", "COP", 4000000, "2025-11-01"),
        ("future", "USD", 9999, "2026-01-01"),
        ("invalid", "USD", float("inf"), "2025-11-01"),
        ("structural", "USD", None, "2025-11-01"),
    ]:
        rows.append(
            dict(
                customer_id="c",
                product_id=ident,
                currency=currency,
                credit_limit=limit,
                product_type="Tarjeta Crédito",
                opening_date="2020-01-01",
                last_updated=updated,
                product_status="Active",
            )
        )
    result = observed_quotas(pd.DataFrame(rows), "c", "2025-12-31")
    assert [p["product_id"] for p in result["products"]] == ["a", "b"]
    assert all(p["available_credit"] is None for p in result["products"])
    json.dumps(result, allow_nan=False)
    assert observed_quotas(pd.DataFrame(rows), "missing", "2025-12-31")["status"] == "abstain"


def test_missing_data_and_model_fail_closed():
    conn = duckdb.connect()
    result = advise(conn, "unknown", "Tarjeta Crédito", "Email", "2025-12-31", Path("missing"))
    assert result["interest"]["status"] == "abstain"
    assert result["existing_quotas"]["status"] == "abstain"
    assert result["new_product_quota"]["amount"] is None
    conn.close()


def test_incompatible_artifact():
    assert predict_interest({}, "p", "c", 0, "2025-12-31")["reason"] == "incompatible_artifact"
    assert VERSION


def test_late_arriving_rows_cannot_cross_training_boundary():
    frame = example_frame()
    frame["process_date"] = frame.send_date
    frame.loc[0, "process_date"] = pd.Timestamp("2025-02-01")
    frame.loc[400, "process_date"] = pd.Timestamp("2025-06-01")
    split = split_examples(frame)
    assert 0 not in split["train"].index
    assert 400 not in split["validation"].index
    assert len(split["test"]) == 400
