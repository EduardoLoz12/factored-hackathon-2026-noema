"""Evalúa escalación observada como objetivo nuevo; no automatiza el rechazo de ayuda."""

import json
from pathlib import Path

import duckdb
import joblib
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from ml.training.product_interest import evaluate

FEATURES = ["channel", "interaction_type", "reason_category"]


def train(database="data/noema.duckdb"):
    with duckdb.connect(database, read_only=True) as conn:
        frame = conn.execute("""
            SELECT channel, interaction_type, reason_category, interaction_date,
                   was_escalated::INTEGER AS target
            FROM noema_silver.stg_call_center_interactions
            WHERE interaction_date < DATE '2025-12-31'
              AND process_date >= interaction_date AND process_date < DATE '2025-12-31'
              AND was_escalated IS NOT NULL
              AND channel IS NOT NULL AND interaction_type IS NOT NULL
              AND reason_category IS NOT NULL
        """).df()
    dates = frame.interaction_date.astype(str)
    splits = {
        "train": frame[dates < "2025-01-01"],
        "validation": frame[(dates >= "2025-02-01") & (dates < "2025-05-01")],
        "test": frame[dates >= "2025-06-01"],
    }
    for part in splits.values():
        if part.target.nunique() != 2:
            raise ValueError("Se requieren ambas clases en cada partición")
    training = splits["train"]
    model = make_pipeline(
        OneHotEncoder(handle_unknown="ignore"), LogisticRegression(max_iter=500, random_state=42)
    )
    model.fit(training[FEATURES], training.target)
    prior = DummyClassifier(strategy="prior").fit(training[FEATURES], training.target)
    report = {
        "target": "observed_support_escalation",
        "features": FEATURES,
        "protocol": "train <2025-01; valid feb-abr; test jun-dic antes del corte",
        "splits": {},
        "production_ready": False,
    }
    for name, part in splits.items():
        report["splits"][name] = {
            "logistic": evaluate(part.target, model.predict_proba(part[FEATURES])[:, 1]),
            "prior": evaluate(part.target, prior.predict_proba(part[FEATURES])[:, 1]),
        }
    v = report["splits"]["validation"]
    report["signal_gate_passed"] = bool(
        v["logistic"]["roc_auc"] >= 0.60
        and v["logistic"]["average_precision"] >= 1.2 * v["prior"]["average_precision"]
    )
    report["limitations"] = [
        "Escalación observada no equivale a necesidad correcta de escalación.",
        "Razón de contacto asumida disponible al ingreso; falta timestamp por campo.",
        "Snapshot sin historial del outcome; evaluación retrospectiva.",
        "No se usan duración, resolución, sentimiento ni seguimiento posteriores.",
        "El cliente siempre puede pedir una persona, cualquiera sea el score.",
    ]
    Path("data/models").mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"model": model, "features": FEATURES, "report": report},
        "data/models/support_escalation.joblib",
    )
    Path("ml/model_cards/support_escalation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"signal_gate_passed": report["signal_gate_passed"], "test": report["splits"]["test"]},
            ensure_ascii=False,
        )
    )
    return report


if __name__ == "__main__":
    train()
