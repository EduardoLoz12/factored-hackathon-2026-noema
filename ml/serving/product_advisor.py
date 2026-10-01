"""Lectura por cliente: interés experimental y límites observados, sin aprobar crédito."""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

import duckdb
import joblib
import pandas as pd

from ml.training.product_interest import FEATURES, VERSION

LOGGER = logging.getLogger(__name__)


def predict_interest(artifact: dict, product: str, channel: str, prior_sends: int, asof) -> dict:
    """Probabilidad condicional al contacto; no confirma deseo ni primera compra."""
    base = {"status": "abstain", "probability": None, "production_ready": False}
    if artifact.get("version") != VERSION or artifact.get("features") != FEATURES:
        return {**base, "reason": "incompatible_artifact"}
    if product not in artifact["products"] or channel not in artifact["channels"]:
        return {**base, "reason": "unsupported_product_or_channel"}
    if isinstance(prior_sends, bool) or not isinstance(prior_sends, int) or prior_sends < 0:
        return {**base, "reason": "invalid_history"}
    frame = pd.DataFrame(
        [
            {
                "promoted_product": product,
                "send_channel": channel,
                "prior_sends": prior_sends,
                "send_month": pd.Timestamp(asof).month,
            }
        ]
    )
    probability = float(artifact["model"].predict_proba(frame[FEATURES])[0, 1])
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        return {**base, "reason": "invalid_prediction"}
    return {
        **base,
        "status": "experimental_estimate",
        "probability": probability,
        "target": "campaign_conversion_within_30_days",
        "model_version": VERSION,
        "estimator": artifact["selected"],
        "product_type": product,
        "channel": channel,
        "asof_date": str(pd.Timestamp(asof).date()),
        "confirmed_desire": None,
        "is_new_to_customer": None,
    }


def observed_quotas(products: pd.DataFrame, customer_id: str, asof) -> dict:
    """No suma monedas ni usa estados del snapshot posteriores al corte."""
    cutoff = pd.Timestamp(asof)
    own = products[products.customer_id == customer_id].copy()
    result = {
        "status": "abstain",
        "products": [],
        "source": "noema_silver.stg_products",
        "asof_date": str(cutoff.date()),
        "reason": "no_verifiable_credit_limits",
    }
    for row in own.to_dict("records"):
        updated = pd.to_datetime(row["last_updated"], errors="coerce")
        opened = pd.to_datetime(row["opening_date"], errors="coerce")
        if pd.isna(updated) or pd.isna(opened) or not opened <= updated <= cutoff:
            continue
        if row["product_status"] != "Active":
            continue
        limit = row["credit_limit"]
        if pd.isna(limit) or not math.isfinite(float(limit)) or float(limit) < 0:
            continue
        if not isinstance(row["currency"], str) or not row["currency"].strip():
            continue
        result["products"].append(
            {
                "product_id": row["product_id"],
                "product_type": row["product_type"],
                "currency": row["currency"],
                "recorded_credit_limit": float(limit),
                "observed_at": str(updated),
                "available_credit": None,
                "note": "Límite registrado; no confirma vigencia actual ni cupo disponible.",
            }
        )
    if result["products"]:
        result.update(status="observed_snapshot", reason=None)
    return result


def advise(conn, customer_id: str, product: str, channel: str, asof, model_path: Path) -> dict:
    """Solo invocar tras autenticar cliente; no registrar ni exportar identificadores."""
    asof_date = pd.Timestamp(asof).date()
    interest = {"status": "abstain", "probability": None, "reason": "model_unavailable"}
    try:
        history = conn.execute(
            """
            SELECT count(*) FROM noema_silver.stg_campaign_sends s
            JOIN noema_silver.stg_marketing_campaigns m USING (campaign_id)
            WHERE s.customer_id = ? AND s.send_date < ? AND s.process_date < ?
              AND s.process_date >= s.send_date AND m.promoted_product IS NOT NULL
              AND s.send_channel IS NOT NULL AND s.send_id IS NOT NULL
        """,
            [customer_id, asof_date, asof_date],
        ).fetchone()[0]
        # Solo archivos locales generados por el entrenamiento de confianza.
        artifact = joblib.load(model_path)
        interest = predict_interest(artifact, product, channel, int(history), asof_date)
    except Exception as exc:  # fallback visible; no PII ni detalles de filas en logs
        LOGGER.warning("interest_unavailable error_type=%s", type(exc).__name__)
    try:
        products = conn.execute(
            """
            SELECT customer_id, product_id, product_type, currency, credit_limit,
                opening_date, last_updated, product_status
            FROM noema_silver.stg_products WHERE customer_id = ?
        """,
            [customer_id],
        ).df()
        quota = observed_quotas(products, customer_id, asof_date)
    except Exception as exc:
        LOGGER.warning("quota_unavailable error_type=%s", type(exc).__name__)
        quota = {"status": "abstain", "products": [], "reason": "data_unavailable"}
    return {
        "interest": interest,
        "existing_quotas": quota,
        "new_product_quota": {
            "status": "requires_policy_evaluation",
            "amount": None,
            "source": "agent.policies.engine.Politica.evaluar",
            "required": [
                "verified_income_usd",
                "existing_obligations",
                "product_terms",
                "identity_verification",
                "validated_asof_inputs",
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/noema.duckdb")
    parser.add_argument("--model", type=Path, default=Path("data/models/product_interest.joblib"))
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--channel", default="Email")
    parser.add_argument("--asof", default="2025-12-31")
    args = parser.parse_args()
    with duckdb.connect(args.database, read_only=True) as conn:
        result = advise(conn, args.customer_id, args.product, args.channel, args.asof, args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
