from pathlib import Path

import duckdb
import pandas as pd
import pytest

from data_platform.contracts.audit import rejection_checks
from data_platform.contracts.quarantine import partition
from data_platform.contracts.schemas import ALL_SCHEMAS
from ml.training.capacity import examples, monthly_panel, predict_capacity, train


def test_quarantine_conserves_rows_and_reason(tmp_path):
    with duckdb.connect() as c:
        c.execute("create table fixture(id integer, _rejection_reason varchar)")
        c.execute("insert into fixture values (1,''),(2,'bad_fk'),(3,'duplicate')")
        assert partition(c, "fixture", "select * from fixture", tmp_path) == (1, 2)
        assert (
            c.read_parquet(str(tmp_path / "quarantine/fixture/part.parquet"))
            .count("*")
            .fetchone()[0]
            == 2
        )


def test_all_tables_have_real_primary_key_constraints():
    assert len(ALL_SCHEMAS) == 13
    for schema in ALL_SCHEMAS.values():
        assert schema.unique
        for key in schema.unique:
            assert not schema.columns[key].nullable


def test_observed_score_and_currency_contracts():
    schema = ALL_SCHEMAS["customers"]
    check = schema.columns["credit_score"].checks[0]
    assert check(pd.Series(["422", "850"])).check_passed
    assert not check(pd.Series(["421"])).check_passed
    assert not check(pd.Series(["nan"])).check_passed
    assert (
        ALL_SCHEMAS["transactions"]
        .columns["fraud_score"]
        .checks[0](pd.Series(["99.99"]))
        .check_passed
    )


def history():
    rows = []
    for customer in ["a", "b"]:
        for month in pd.date_range("2024-01-01", "2025-11-01", freq="MS"):
            for kind, amount in [("Deposit", 1000), ("Payment", 500)]:
                rows.append(
                    dict(
                        customer_id=customer,
                        currency="USD",
                        transaction_date=month,
                        process_date=month,
                        transaction_status="Approved",
                        transaction_type=kind,
                        amount=amount,
                    )
                )
    return pd.DataFrame(rows)


def test_future_and_late_transactions_cannot_change_training():
    data = history()
    base = examples(monthly_panel(data))
    future = data.iloc[[0]].copy()
    future["amount"] = 1e12
    future["transaction_date"] = pd.Timestamp("2026-01-01")
    future["process_date"] = pd.Timestamp("2026-01-01")
    late = future.copy()
    late["transaction_date"] = pd.Timestamp("2025-01-01")
    pd.testing.assert_frame_equal(base, examples(monthly_panel(pd.concat([data, future, late]))))


def test_training_target_is_not_same_month_feature(tmp_path):
    data = history()
    artifact = train(data, tmp_path / "capacity.json")
    result = predict_capacity(data, "a", "USD", artifact)
    assert result["status"] == "estimated"
    assert 0 <= result["affordable_payment"] <= 300
    assert artifact["metrics"]["validation_start"] == "2025-10-01"
    assert predict_capacity(data, "a", "COP", artifact)["status"] == "abstain"
    ambiguous = data.iloc[[0]].copy()
    ambiguous["transaction_type"] = "Transfer"
    ambiguous["transaction_date"] = ambiguous["process_date"] = pd.Timestamp("2025-11-01")
    assert (
        predict_capacity(pd.concat([data, ambiguous]), "a", "USD", artifact)["status"] == "abstain"
    )


def test_essential_links_reject_optional_links_are_repaired():
    checks = dict(rejection_checks("transactions"))
    assert "customer_id:orphan" in checks
    assert "product_id:orphan" in checks
    assert "branch_id:orphan" not in checks


def test_dbt_cutoff_applies_to_operation_and_availability():
    # Ejecuta SQL compilado sobre un escenario adverso, sin depender del dataset.
    from jinja2 import Environment

    sql = Path("data_platform/dbt/models/gold/credit_features_asof.sql").read_text(encoding="utf-8")
    env = Environment()
    compiled = env.from_string(sql).render(
        ref=lambda name: name,
        var=lambda name: "2025-12-31",
        days_between=lambda start, end: f"date_diff('day',{start},{end})",
    )
    with duckdb.connect() as c:
        c.execute("create table stg_customers(customer_id varchar, registration_date date)")
        c.execute("insert into stg_customers values ('a','2024-01-01')")
        c.execute(
            "create table stg_transactions(customer_id varchar, transaction_date date, "
            "process_date date, transaction_status varchar, "
            "amount_usd double, transaction_type varchar)"
        )
        c.execute(
            "insert into stg_transactions values "
            "('a','2025-11-01','2025-11-02','Approved',100,'Depósito'),"
            "('a','2026-01-01','2026-01-01','Approved',999999,'Depósito'),"
            "('a','2025-11-01','2026-01-01','Approved',999999,'Depósito'),"
            "('a','2025-12-31','2025-12-31','Approved',999999,'Depósito')"
        )
        row = c.execute(compiled).df().iloc[0]
        assert row.deposits_usd_180d == 100
        assert row.transaction_count_180d == 1


def test_export_plans_fail_before_any_cloud_write(tmp_path):
    from data_platform.databricks.upload_to_volume import upload_plan
    from data_platform.serving.export_to_postgres import pg_type

    with pytest.raises(ValueError):
        upload_plan(tmp_path, "/Volumes/../../bad")
    with pytest.raises(FileNotFoundError):
        upload_plan(tmp_path, "/Volumes/catalog/schema/volume")
    assert pg_type("VARCHAR") == "TEXT"
    with pytest.raises(ValueError):
        pg_type("STRUCT(x INTEGER)")
