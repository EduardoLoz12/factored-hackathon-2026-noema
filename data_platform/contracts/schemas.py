"""Contratos bronze: validación semántica sin borrar ni imputar valores."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

COLUMNS = json.loads(Path(__file__).with_name("columns.json").read_text(encoding="utf-8"))
KEYS = {
    "branches": ["branch_id"],
    "customers": ["customer_id"],
    "products": ["product_id"],
    "service_agents": ["agent_id"],
    "marketing_campaigns": ["campaign_id"],
    "transactions": ["transaction_id"],
    "digital_events": ["event_id"],
    "call_center_interactions": ["interaction_id"],
    "call_transcripts": ["transcript_id"],
    "campaign_sends": ["send_id"],
    "complaints": ["complaint_id"],
    "satisfaction_surveys": ["survey_id"],
    "daily_exchange_rates": ["date", "source_currency", "target_currency"],
}
FOREIGN_KEYS = {
    "customers": {"registration_branch_id": ("branches", "branch_id")},
    "service_agents": {"assigned_branch_id": ("branches", "branch_id")},
    "products": {
        "customer_id": ("customers", "customer_id"),
        "opening_branch_id": ("branches", "branch_id"),
    },
    "transactions": {
        "customer_id": ("customers", "customer_id"),
        "product_id": ("products", "product_id"),
        "branch_id": ("branches", "branch_id"),
    },
    "digital_events": {
        "customer_id": ("customers", "customer_id"),
        "product_id": ("products", "product_id"),
    },
    "call_center_interactions": {
        "customer_id": ("customers", "customer_id"),
        "agent_id": ("service_agents", "agent_id"),
    },
    "call_transcripts": {
        "customer_id": ("customers", "customer_id"),
        "agent_id": ("service_agents", "agent_id"),
        "interaction_id": ("call_center_interactions", "interaction_id"),
    },
    "campaign_sends": {
        "customer_id": ("customers", "customer_id"),
        "campaign_id": ("marketing_campaigns", "campaign_id"),
    },
    "complaints": {
        "customer_id": ("customers", "customer_id"),
        "affected_product_id": ("products", "product_id"),
        "related_branch_id": ("branches", "branch_id"),
        "origin_interaction_id": ("call_center_interactions", "interaction_id"),
        "assigned_agent_id": ("service_agents", "agent_id"),
    },
    "satisfaction_surveys": {
        "customer_id": ("customers", "customer_id"),
        "agent_id": ("service_agents", "agent_id"),
        "interaction_id": ("call_center_interactions", "interaction_id"),
    },
}
ORDER = [
    "branches",
    "marketing_campaigns",
    "daily_exchange_rates",
    "customers",
    "service_agents",
    "products",
    "transactions",
    "call_center_interactions",
    "call_transcripts",
    "campaign_sends",
    "complaints",
    "satisfaction_surveys",
    "digital_events",
]
DOCUMENTED = dict(
    zip(
        ORDER,
        [
            350,
            200,
            3000,
            150000,
            1200,
            400000,
            5000000,
            800000,
            200000,
            2000000,
            80000,
            250000,
            10000000,
        ],
        strict=True,
    )
)
PRODUCT_TYPES = {
    "Cuenta Ahorro": "Cuenta Ahorro",
    "Savings Account": "Cuenta Ahorro",
    "Cuenta Corriente": "Cuenta Corriente",
    "Checking Account": "Cuenta Corriente",
    "Tarjeta Crédito": "Tarjeta Crédito",
    "Credit Card": "Tarjeta Crédito",
    "Tarjeta Débito": "Tarjeta Débito",
    "Debit Card": "Tarjeta Débito",
    "Préstamo Personal": "Préstamo Personal",
    "Personal Loan": "Préstamo Personal",
    "Préstamo Hipotecario": "Préstamo Hipotecario",
    "Mortgage Loan": "Préstamo Hipotecario",
    "Inversión": "Inversión",
    "Investment": "Inversión",
    "Seguro": "Seguro",
    "Insurance": "Seguro",
}
TRANSACTION_TYPES = {
    "Deposit": "Depósito",
    "Withdrawal": "Retiro",
    "Payment": "Pago",
    "Purchase": "Compra",
    "Transfer": "Transferencia",
    "Adjustment": "Ajuste",
}
TRANSACTION_TYPES.update({v: v for v in list(TRANSACTION_TYPES.values())})
ENUMS = {
    ("products", "product_type"): list(PRODUCT_TYPES),
    ("transactions", "transaction_type"): list(TRANSACTION_TYPES),
    ("transactions", "transaction_status"): ["Approved", "Declined", "Pending", "Reversed"],
    ("customers", "country"): ["México", "Colombia", "Argentina"],
}
RANGES = {
    "credit_score": (422, 850),
    "days_past_due": (0, 180),
    "exchange_rate": (1e-12, None),
    "buy_rate": (1e-12, None),
    "sell_rate": (1e-12, None),
    "credit_limit": (0, None),
    "estimated_monthly_income": (0, None),
    "fraud_score": (0, 100),
    "accent_confidence": (0, 1),
    "sentiment_score": (-1, 1),
    "latitude": (-90, 90),
    "longitude": (-180, 180),
}
NUMERIC = set(RANGES) | {
    "amount",
    "amount_usd",
    "current_balance",
    "interest_rate",
    "duration_seconds",
    "wait_time_seconds",
    "atm_count",
    "teller_window_count",
    "budget",
    "expected_conversion_rate",
    "click_count",
    "conversion_value",
    "send_cost",
    "claimed_amount",
    "resolution_days",
    "compensation_granted",
    "resolution_satisfaction",
    "event_value",
    "main_score",
    "response_time_hours",
    "campaign_response_rate",
    "avg_csat",
    "total_monthly_interactions",
}


def kind(column: str) -> str:
    if column in NUMERIC:
        return "DOUBLE"
    if column.endswith("_date") or column == "date":
        return "DATE"
    if column in {"last_updated", "_ingested_at"}:
        return "TIMESTAMP"
    if column.startswith(("is_", "has_", "was_")) or column in {
        "requires_followup",
        "had_conversion",
        "accepts_marketing",
        "sla_breached",
    }:
        return "BOOLEAN"
    return "VARCHAR"


def required(table: str, column: str) -> bool:
    return (
        column in KEYS[table]
        or column in {"_source_file", "_ingested_at"}
        or (
            table == "transactions"
            and column
            in {
                "transaction_date",
                "process_date",
                "amount",
                "currency",
                "product_id",
                "customer_id",
                "transaction_type",
                "transaction_status",
            }
        )
        or (table == "products" and column in {"customer_id", "product_type", "currency"})
        or (
            table == "customers" and column in {"document_number", "document_type", "date_of_birth"}
        )
        or (table == "daily_exchange_rates" and column == "exchange_rate")
    )


def allowed(table: str, column: str) -> list[str] | None:
    if column in {"currency", "source_currency", "target_currency"}:
        return ["USD", "MXN", "COP", "ARS"]
    return ENUMS.get((table, column))


def semantic_check(series: pd.Series, column: str) -> pd.Series:
    t = kind(column)
    if t == "DOUBLE":
        x = pd.to_numeric(series, errors="coerce")
        valid = x.notna() & x.ne(float("inf")) & x.ne(float("-inf"))
        low, high = RANGES.get(column, (None, None))
        if low is not None:
            valid &= x.ge(low)
        if high is not None:
            valid &= x.le(high)
        return valid
    if t in {"DATE", "TIMESTAMP"}:
        return pd.to_datetime(series, errors="coerce", format="mixed").notna()
    if t == "BOOLEAN":
        return series.str.lower().isin(["true", "false", "1", "0"])
    return series.str.strip().ne("")


def make_schema(table: str) -> pa.DataFrameSchema:
    columns = {}
    for column in COLUMNS[table]:
        checks = [pa.Check(lambda s, c=column: semantic_check(s, c), name="semantic_type")]
        values = allowed(table, column)
        if values:
            checks.append(pa.Check.isin(values))
        columns[column] = pa.Column(str, checks, nullable=not required(table, column), coerce=True)
    return pa.DataFrameSchema(columns, unique=KEYS[table], strict=True, name=table)


ALL_SCHEMAS = {table: make_schema(table) for table in COLUMNS}
globals().update({f"{table}_schema": schema for table, schema in ALL_SCHEMAS.items()})
