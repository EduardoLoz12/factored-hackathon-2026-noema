"""Modelo experimental de conversión a 30 días; nunca decide crédito."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CATEGORICAL = ["promoted_product", "send_channel"]
NUMERIC = ["prior_sends", "send_month"]
FEATURES = CATEGORICAL + NUMERIC
VERSION = "product_interest_v1"


def build_examples(conn, cutoff="2025-12-31") -> tuple[pd.DataFrame, dict]:
    """Historial de exposiciones anterior al envío; sin aperturas/clics del objetivo."""
    cutoff = pd.Timestamp(cutoff).date()
    # La tabla temporal permite reutilizar el mismo filtro al auditar y entrenar.
    conn.execute("""
        CREATE OR REPLACE TEMP TABLE interest_source AS
        SELECT s.send_id, s.customer_id, s.send_date, s.process_date,
               s.send_channel, s.had_conversion, s.conversion_date,
               m.promoted_product
        FROM noema_silver.stg_campaign_sends s
        LEFT JOIN noema_silver.stg_marketing_campaigns m USING (campaign_id)
    """)
    audit = dict(
        zip(
            ["source_rows", "invalid_process_order", "missing_product", "immature_rows"],
            conn.execute(
                """
            SELECT count(*), count(*) FILTER (WHERE process_date < send_date),
                count(*) FILTER (WHERE promoted_product IS NULL),
                count(*) FILTER (WHERE send_date + INTERVAL 30 DAY >= ?)
            FROM interest_source
        """,
                [cutoff],
            ).fetchone(),
            strict=True,
        )
    )
    frame = conn.execute(
        """
        WITH valid AS (
            SELECT * FROM interest_source
            WHERE customer_id IS NOT NULL AND send_id IS NOT NULL
              AND promoted_product IS NOT NULL AND send_channel IS NOT NULL
              AND process_date >= send_date AND process_date < ?
              AND send_date < ?
        ), history AS (
            SELECT customer_id, process_date, count(*) AS n
            FROM valid GROUP BY 1, 2
        ), cumulative AS (
            SELECT customer_id, process_date,
                sum(n) OVER (PARTITION BY customer_id ORDER BY process_date) AS n
            FROM history
        )
        SELECT v.*, coalesce(h.n, 0)::DOUBLE AS prior_sends,
            month(v.send_date)::DOUBLE AS send_month,
            CASE WHEN had_conversion AND conversion_date >= send_date
                      AND conversion_date <= send_date + INTERVAL 30 DAY
                 THEN 1 ELSE 0 END AS target
        FROM valid v ASOF LEFT JOIN cumulative h
          ON v.customer_id = h.customer_id AND v.send_date > h.process_date
        WHERE v.send_date + INTERVAL 30 DAY < ?
          AND had_conversion IS NOT NULL
          AND (NOT had_conversion AND conversion_date IS NULL
               OR had_conversion AND conversion_date >= send_date)
        ORDER BY v.send_date, v.send_id
    """,
        [cutoff, cutoff, cutoff],
    ).df()
    if frame.send_id.duplicated().any():
        raise ValueError("send_id duplicado o campaña no única")
    audit["eligible_rows"] = len(frame)
    audit["cutoff"] = str(cutoff)
    return frame, audit


def split_examples(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Ventanas fijas y embargo de 30 días para madurar las etiquetas."""
    dates = pd.to_datetime(frame.send_date)
    splits = {
        "train": frame[dates < "2024-12-01"],
        "validation": frame[(dates >= "2025-01-01") & (dates < "2025-04-01")],
        "test": frame[dates >= "2025-05-01"],
    }
    if "process_date" in frame:
        splits["train"] = splits["train"][
            pd.to_datetime(splits["train"].process_date) < "2025-01-01"
        ]
        splits["validation"] = splits["validation"][
            pd.to_datetime(splits["validation"].process_date) < "2025-05-01"
        ]
    for name, part in splits.items():
        if len(part) < 100 or part.target.nunique() != 2:
            raise ValueError(f"{name}: requiere al menos 100 filas y ambas clases")
    return splits


def make_pipeline() -> Pipeline:
    preprocess = ColumnTransformer(
        [
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                CATEGORICAL,
            ),
            (
                "numeric",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                        ("scale", StandardScaler()),
                    ]
                ),
                NUMERIC,
            ),
        ]
    )
    return Pipeline(
        [
            ("preprocess", preprocess),
            ("classifier", LogisticRegression(C=1.0, max_iter=1000, random_state=42)),
        ]
    )


def evaluate(y, probabilities) -> dict:
    """AP (área PR escalonada), calibración y ranking, sin accuracy engañosa."""
    y = np.asarray(y)
    p = np.asarray(probabilities)
    k = max(1, int(np.ceil(len(y) * 0.1)))
    # Empates: rendimiento esperado al seleccionar aleatoriamente dentro del empate.
    boundary = np.sort(p)[-k]
    above, tied = p > boundary, p == boundary
    precision = (y[above].sum() + (k - above.sum()) * y[tied].mean()) / k
    bins = pd.DataFrame({"y": y, "p": p})
    bins["bin"] = pd.cut(bins.p, bins=np.linspace(0, 1, 11), include_lowest=True)
    calibration = [
        {"rows": len(g), "predicted": float(g.p.mean()), "observed": float(g.y.mean())}
        for _, g in bins.groupby("bin", observed=True)
    ]
    return {
        "rows": len(y),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "average_precision": float(average_precision_score(y, p)),
        "roc_auc": float(roc_auc_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "precision_top_10pct": float(precision),
        "lift_top_10pct": float(precision / y.mean()),
        "calibration": calibration,
    }


def bootstrap_intervals(part: pd.DataFrame, probabilities, repetitions=100) -> dict:
    """Bootstrap por cliente: conserva dependencia de exposiciones repetidas."""
    ids, customers = pd.factorize(part.customer_id)
    rng = np.random.default_rng(42)
    values = []
    for _ in range(repetitions):
        weights = rng.poisson(1, len(customers))[ids]
        if not weights[part.target == 1].sum() or not weights[part.target == 0].sum():
            continue
        values.append(
            [
                roc_auc_score(part.target, probabilities, sample_weight=weights),
                average_precision_score(part.target, probabilities, sample_weight=weights),
            ]
        )
    if not values:
        return {"status": "insufficient_classes"}
    interval = np.quantile(values, [0.025, 0.975], axis=0)
    return {
        "method": "customer_cluster_poisson_bootstrap",
        "seed": 42,
        "repetitions": len(values),
        "confidence": 0.95,
        "roc_auc": interval[:, 0].tolist(),
        "average_precision": interval[:, 1].tolist(),
        "limitation": "Condicional al período; no mide incertidumbre ante cambios temporales.",
    }


def train(frame: pd.DataFrame, audit: dict) -> tuple[dict, dict]:
    splits = split_examples(frame)
    training = splits["train"]
    model = make_pipeline().fit(training[FEATURES], training.target)
    baseline = DummyClassifier(strategy="prior").fit(training[FEATURES], training.target)
    report = {"version": VERSION, "audit": audit, "splits": {}, "sklearn": sklearn.__version__}
    for name, part in splits.items():
        report["splits"][name] = {
            "start": str(pd.Timestamp(part.send_date.min()).date()),
            "end": str(pd.Timestamp(part.send_date.max()).date()),
            "model": evaluate(part.target, model.predict_proba(part[FEATURES])[:, 1]),
            "baseline": evaluate(part.target, baseline.predict_proba(part[FEATURES])[:, 1]),
        }
    valid = report["splits"]["validation"]
    selected = (
        "logistic"
        if valid["model"]["average_precision"] > valid["baseline"]["average_precision"]
        and valid["model"]["brier"] < valid["baseline"]["brier"]
        else "prior"
    )
    report.update(
        {
            "selected_on_validation": selected,
            "production_ready": False,
            "target": "campaign_conversion_within_30_days",
            "limitations": [
                "Conversión no implica deseo explícito, primera adquisición ni elegibilidad.",
                "Etiquetas retrospectivas sin historial de revisiones; maduración asumida.",
                "Metadatos de campaña asumidos estables; falta vigencia versionada.",
                "Clientes repetidos: evalúa futuras exposiciones, no clientes nuevos.",
                "Sin inferencia causal, sin umbral de contacto ni aprobación automática.",
            ],
        }
    )
    chosen = model if selected == "logistic" else baseline
    test = splits["test"]
    if "customer_id" in test:
        probabilities = chosen.predict_proba(test[FEATURES])[:, 1]
        report["test_uncertainty"] = bootstrap_intervals(test, probabilities)
    report["model_coefficients"] = dict(
        zip(
            model.named_steps["preprocess"].get_feature_names_out().tolist(),
            model.named_steps["classifier"].coef_[0].tolist(),
            strict=True,
        )
    )
    report["model_intercept"] = float(model.named_steps["classifier"].intercept_[0])
    artifact = {
        "version": VERSION,
        "model": model if selected == "logistic" else baseline,
        "selected": selected,
        "features": FEATURES,
        "products": sorted(training.promoted_product.unique().tolist()),
        "channels": sorted(training.send_channel.unique().tolist()),
        "report": report,
    }
    return artifact, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/noema.duckdb")
    parser.add_argument("--output", type=Path, default=Path("data/models/product_interest.joblib"))
    parser.add_argument("--report", type=Path, default=Path("ml/model_cards/product_interest.json"))
    args = parser.parse_args()
    with duckdb.connect(args.database, read_only=True) as conn:
        frame, audit = build_examples(conn)
    artifact, report = train(frame, audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
