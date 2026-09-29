"""Capacidad proxy: flujo mensual futuro; nunca ingreso declarado ni aprobación."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

FEATURES = ["mean_deposits", "mean_outflows", "min_surplus", "active_months"]
CUTOFF = pd.Timestamp("2025-12-31")


def monthly_panel(transactions: pd.DataFrame, cutoff=CUTOFF) -> pd.DataFrame:
    """Fechas de operación y disponibilidad anteriores al corte; meses completos."""
    cutoff = pd.Timestamp(cutoff)
    if cutoff > CUTOFF:
        raise ValueError("Corte posterior al contrato temporal")
    data = transactions.copy()
    for col in ["transaction_date", "process_date"]:
        data[col] = pd.to_datetime(data[col], errors="raise")
    data = data[
        (data.transaction_date < cutoff.replace(day=1))
        & (data.process_date < cutoff)
        & (data.transaction_status == "Approved")
    ].copy()
    if data.empty:
        raise ValueError("No hay transacciones históricas aprobadas")
    data["month"] = (
        data[["transaction_date", "process_date"]].max(axis=1).dt.to_period("M").dt.to_timestamp()
    )
    amount = pd.to_numeric(data.amount, errors="raise").astype(float).abs()
    data["deposits"] = np.where(data.transaction_type.isin(["Deposit", "Depósito"]), amount, 0)
    data["outflows"] = np.where(
        data.transaction_type.isin(
            ["Payment", "Purchase", "Withdrawal", "Pago", "Compra", "Retiro"]
        ),
        amount,
        0,
    )
    data["ambiguous"] = data.transaction_type.isin(
        ["Transfer", "Adjustment", "Transferencia", "Ajuste"]
    ).astype(int)
    grouped = data.groupby(["customer_id", "currency", "month"])[
        ["deposits", "outflows", "ambiguous"]
    ].sum()
    pairs = data[["customer_id", "currency"]].drop_duplicates()
    months = pd.DataFrame(
        {
            "month": pd.date_range(
                data.month.min(), cutoff.replace(day=1) - pd.Timedelta(days=1), freq="MS"
            )
        }
    )
    panel = pairs.merge(months, how="cross").merge(grouped.reset_index(), how="left").fillna(0)
    panel = panel.sort_values(["customer_id", "currency", "month"])
    panel["active"] = ((panel.deposits + panel.outflows) > 0).astype(int)
    panel["surplus"] = (panel.deposits - panel.outflows).clip(lower=0)
    panel["target"] = np.minimum(panel.surplus, 0.30 * panel.deposits)
    return panel


def examples(panel: pd.DataFrame) -> pd.DataFrame:
    result = panel.copy()
    groups = result.groupby(["customer_id", "currency"], sort=False)
    for source, output, operation in [
        ("deposits", "mean_deposits", "mean"),
        ("outflows", "mean_outflows", "mean"),
        ("surplus", "min_surplus", "min"),
        ("active", "active_months", "sum"),
        ("ambiguous", "ambiguous_count", "sum"),
    ]:
        result[output] = groups[source].transform(
            lambda s, op=operation: getattr(s.shift(1).rolling(3, min_periods=3), op)()
        )
    return result.dropna(subset=FEATURES)


def train(transactions: pd.DataFrame, output: Path, cutoff=CUTOFF) -> dict:
    data = examples(monthly_panel(transactions, cutoff))
    # Validación de los dos últimos meses completos; ninguna etiqueta posterior al corte.
    boundary = pd.Timestamp(cutoff).replace(day=1) - pd.DateOffset(months=2)
    training = data[data.month < boundary]
    validation = data[data.month >= boundary]
    if len(training) < 10 or validation.empty:
        raise ValueError("Historia insuficiente para entrenamiento y validación temporal")
    training = training.sample(min(150000, len(training)), random_state=42)
    model = LinearRegression(positive=True).fit(training[FEATURES], training.target)
    baseline = np.minimum(validation.min_surplus, validation.mean_deposits * 0.30)
    predictions = np.minimum(baseline, np.maximum(0, model.predict(validation[FEATURES])))
    metrics = {
        "validation_mae": float(mean_absolute_error(validation.target, predictions)),
        "baseline_mae": float(mean_absolute_error(validation.target, baseline)),
        "training_rows": len(training),
        "validation_rows": len(validation),
        "validation_start": str(boundary.date()),
        "cutoff": str(pd.Timestamp(cutoff).date()),
        "target": "proxy=min(max(deposits-outflows,0),0.30*deposits)",
        "limitation": (
            "Proxy de flujo, no solvencia observada. "
            "MAE agregado en monedas mixtas no comparable entre países."
        ),
    }
    metrics["eligible_validation_rows"] = int(
        ((validation.active_months == 3) & (validation.ambiguous_count == 0)).sum()
    )
    metrics["by_currency"] = {}
    for currency in sorted(validation.currency.unique()):
        mask = validation.currency == currency
        metrics["by_currency"][currency] = {
            "rows": int(mask.sum()),
            "model_mae": float(
                mean_absolute_error(validation.loc[mask, "target"], predictions[mask])
            ),
            "baseline_mae": float(
                mean_absolute_error(validation.loc[mask, "target"], baseline[mask])
            ),
        }
    # Se publica el modelo únicamente como estimador; si pierde, se usa baseline documentado.
    artifact = {
        "version": "capacity_v1",
        "features": FEATURES,
        "coefficients": model.coef_.tolist(),
        "intercept": float(model.intercept_),
        "selected": "model" if metrics["validation_mae"] < metrics["baseline_mae"] else "baseline",
        "metrics": metrics,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return artifact


def predict_capacity(
    history: pd.DataFrame, customer_id: str, currency: str, artifact: dict, cutoff=CUTOFF
) -> dict:
    """Punto de integración para el predictor de Eduardo; salida en moneda solicitada."""
    base = {
        "customer_id": customer_id,
        "currency": currency,
        "model_version": artifact["version"],
        "asof_date": str(pd.Timestamp(cutoff).date()),
        "is_proxy": True,
    }
    selected = history[(history.customer_id == customer_id) & (history.currency == currency)]
    if selected.empty:
        return {**base, "status": "abstain", "affordable_payment": None, "reason": "no_history"}
    try:
        panel = monthly_panel(selected, cutoff).tail(3)
    except ValueError:
        return {**base, "status": "abstain", "affordable_payment": None, "reason": "no_history"}
    if len(panel) < 3 or panel.active.sum() < 3 or panel.ambiguous.sum() > 0:
        return {
            **base,
            "status": "abstain",
            "affordable_payment": None,
            "reason": "insufficient_or_ambiguous_cashflow",
        }
    features = [
        panel.deposits.mean(),
        panel.outflows.mean(),
        panel.surplus.min(),
        panel.active.sum(),
    ]
    ceiling = min(features[2], 0.30 * features[0])
    estimate = float(np.dot(features, artifact["coefficients"]) + artifact["intercept"])
    if artifact["selected"] == "baseline":
        estimate = ceiling
    if not np.isfinite(estimate):
        raise ValueError("Predicción no finita; no confirmar capacidad")
    return {
        **base,
        "status": "estimated",
        "affordable_payment": round(max(0, min(estimate, ceiling)), 2),
        "source": "approved_transactions_before_cutoff",
        "estimator": artifact["selected"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/noema.duckdb")
    parser.add_argument("--output", type=Path, default=Path("data/models/capacity.json"))
    args = parser.parse_args()
    with duckdb.connect(args.database, read_only=True) as conn:
        frame = conn.execute(
            "SELECT customer_id,currency,transaction_date,process_date, "
            "transaction_status,transaction_type,amount FROM noema_silver.stg_transactions "
            "WHERE hash(customer_id) % 20 = 0"
        ).df()
    artifact = train(frame, args.output)
    artifact["metrics"]["sampling"] = (
        "Deterministic hash(customer_id) % 20 = 0; at most 150000 training examples, seed 42"
    )
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log = Path("logs/build/capacity_metrics.json")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        json.dumps(artifact["metrics"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(artifact["metrics"], ensure_ascii=False))


if __name__ == "__main__":
    main()
