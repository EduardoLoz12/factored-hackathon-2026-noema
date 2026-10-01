"""Asesor analítico: red profunda, cupos observados y política verificable de Eduardo."""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import duckdb
import joblib
import pandas as pd

from agent.policies.engine import Cliente, Politica
from ml.serving.product_advisor import advise, predict_interest

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedPolicyInput:
    """Hechos certificados por el llamador autorizado, no por la red ni el LLM."""

    client: Cliente
    asof: date
    evidence_ref: str
    obligations_complete: bool


def policy_analysis(customer_id, asof, verified: VerifiedPolicyInput | None, policy=None):
    """Puerta de evidencia antes de la aritmética existente; no replica umbrales."""
    base = {
        "status": "abstain",
        "amount": None,
        "source": "agent.policies.engine",
        "reason": "verified_inputs_required",
    }
    if verified is None:
        return base
    try:
        policy = policy or Politica.cargar()
        client = verified.client
        if (
            client.customer_id != customer_id
            or verified.asof != pd.Timestamp(asof).date()
            or verified.asof != policy.corte
        ):
            return {**base, "reason": "identity_or_cutoff_mismatch"}
        if not verified.evidence_ref.strip() or verified.obligations_complete is not True:
            return {**base, "reason": "incomplete_evidence"}
        # Ningún NaN/inf debe alcanzar reglas basadas en comparaciones numéricas.
        json.dumps(asdict(client), default=str, allow_nan=False)
        amounts = [client.ingreso_mensual_usd, client.capacidad_estimada_usd]
        if client.alta > verified.asof:
            return {**base, "reason": "future_customer"}
        for product in client.productos:
            if product.limite_usd is None or product.tasa_anual is None:
                return {**base, "reason": "missing_obligation_terms"}
            if product.tipo not in policy.amortizacion:
                return {**base, "reason": "unsupported_obligation"}
            if (
                product.apertura > verified.asof
                or product.ultima_transaccion_real is not None
                and product.ultima_transaccion_real > verified.asof
            ):
                return {**base, "reason": "future_obligation"}
            if product.vencimiento is not None and product.vencimiento <= product.apertura:
                return {**base, "reason": "invalid_obligation_dates"}
            amounts.extend(
                [product.limite_usd, product.tasa_anual, product.saldo_usd, product.cuotas_pagadas]
            )
        amounts.extend(asset.saldo_usd for asset in client.ahorros)
        if any(
            isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in amounts if v is not None
        ):
            return {**base, "reason": "invalid_financial_input"}
        decision = policy.evaluar(client).a_dict()
        json.dumps(decision, allow_nan=False)
        decision.pop("customer_id", None)
        return {
            "status": "policy_scenario",
            "source": "agent.policies.engine",
            "evidence_ref": verified.evidence_ref,
            "decision": decision,
            "is_bank_approval": False,
        }
    except Exception as exc:
        LOGGER.warning("policy_analysis_unavailable error_type=%s", type(exc).__name__)
        return {**base, "reason": "invalid_or_unavailable_policy_inputs"}


def analyze_client(
    conn,
    customer_id,
    channel="Email",
    asof="2025-12-31",
    model_path=Path("data/models/deep_interest.joblib"),
    verified=None,
):
    """Análisis interno tras autorización: ranking experimental y evidencia separada."""
    base = {"status": "abstain", "product_analysis": [], "production_ready": False}
    if pd.Timestamp(asof) < pd.Timestamp("2025-05-01"):
        return {**base, "reason": "asof_before_model_selection"}
    try:
        exists = conn.execute(
            "SELECT count(*) FROM noema_silver.stg_customers WHERE customer_id = ?",
            [customer_id],
        ).fetchone()[0]
        if exists != 1:
            return {**base, "reason": "unknown_or_duplicate_customer"}
        artifact = joblib.load(model_path)  # solo artefactos locales de confianza
        if artifact.get("version") != "deep_interest_v1":
            return {**base, "reason": "incompatible_model"}
        products = artifact["products"]
        if not products:
            return {**base, "reason": "empty_product_catalog"}
        # Reutiliza el contrato validado de historial y cupos.
        first = advise(conn, customer_id, products[0], channel, asof, model_path)
        history = conn.execute(
            """
            SELECT count(*) FROM noema_silver.stg_campaign_sends s
            JOIN noema_silver.stg_marketing_campaigns m USING (campaign_id)
            WHERE s.customer_id = ? AND s.send_date < ? AND s.process_date < ?
              AND s.process_date >= s.send_date AND m.promoted_product IS NOT NULL
              AND s.send_channel IS NOT NULL AND s.send_id IS NOT NULL
        """,
            [customer_id, pd.Timestamp(asof).date(), pd.Timestamp(asof).date()],
        ).fetchone()[0]
        champion = {
            **artifact,
            "model": artifact["recommended_pipeline"],
            "selected": artifact["recommended_model"],
        }
        ranking = []
        for product in products:
            neural = predict_interest(artifact, product, channel, int(history), asof)
            recommended = predict_interest(champion, product, channel, int(history), asof)
            ranking.append(
                {
                    "product_type": product,
                    "deep_learning": neural,
                    "recommended_estimator": recommended,
                }
            )
        ranking.sort(
            key=lambda r: (
                r["recommended_estimator"]["probability"]
                if r["recommended_estimator"]["probability"] is not None
                else -1
            ),
            reverse=True,
        )
        return {
            "status": (
                "experimental_analysis"
                if any(r["deep_learning"]["probability"] is not None for r in ranking)
                else "abstain"
            ),
            "production_ready": False,
            "asof_date": str(pd.Timestamp(asof).date()),
            "product_analysis": ranking,
            "existing_quotas": first["existing_quotas"],
            "new_product_quota": policy_analysis(customer_id, asof, verified),
            "evidence": {
                "prior_valid_campaign_sends": int(history),
                "policy_input_supplied": verified is not None,
                "recommended_model": artifact["recommended_model"],
            },
            "explanation": [
                "Probabilidades de conversión tras campaña; no confirman deseo ni primera compra.",
                "Ranking descriptivo: comparar campañas no estima el efecto causal de ofrecerlas.",
                "Cupos registrados y escenarios de política están separados de la red.",
                "No se determina mora; no se contacta al cliente ni se aprueba crédito.",
            ],
        }
    except Exception as exc:
        LOGGER.warning("client_analysis_unavailable error_type=%s", type(exc).__name__)
        return {**base, "reason": "model_or_data_unavailable"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/noema.duckdb")
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--channel", default="Email")
    parser.add_argument("--asof", default="2025-12-31")
    parser.add_argument("--model", type=Path, default=Path("data/models/deep_interest.joblib"))
    args = parser.parse_args()
    with duckdb.connect(args.database, read_only=True) as conn:
        result = analyze_client(conn, args.customer_id, args.channel, args.asof, args.model)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
