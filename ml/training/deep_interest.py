"""Red profunda tabular con selección temporal explícita; no decide crédito."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import duckdb
import joblib
import numpy as np
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

from ml.training.product_interest import (
    FEATURES,
    bootstrap_intervals,
    build_examples,
    evaluate,
    make_pipeline,
    split_examples,
)

VERSION = "deep_interest_v1"


def train_deep(frame, audit, epochs=20, patience=4):
    """Checkpoint por log-loss de validación; test jamás controla el entrenamiento."""
    if epochs < 1 or patience < 1:
        raise ValueError("epochs y patience deben ser positivos")
    splits = split_examples(frame)
    training, validation = splits["train"], splits["validation"]
    preprocess = make_pipeline().named_steps["preprocess"]
    x_train = preprocess.fit_transform(training[FEATURES])
    x_valid = preprocess.transform(validation[FEATURES])
    network = MLPClassifier(
        hidden_layer_sizes=(32, 16, 8),
        activation="relu",
        solver="adam",
        alpha=0.01,
        batch_size=min(1024, len(training)),
        learning_rate_init=0.001,
        early_stopping=False,
        random_state=42,
        shuffle=True,
    )
    best_loss, best, best_epoch, stale = float("inf"), None, 0, 0
    learning_curve = []
    with threadpool_limits(limits=2):
        for epoch in range(1, epochs + 1):
            network.partial_fit(x_train, training.target, classes=np.array([0, 1]))
            loss = float(log_loss(validation.target, network.predict_proba(x_valid)))
            if not np.isfinite(loss):
                raise ValueError("Pérdida no finita")
            learning_curve.append(
                {"epoch": epoch, "train_loss": float(network.loss_), "validation_log_loss": loss}
            )
            if loss < best_loss - 1e-7:
                best_loss, best, best_epoch, stale = loss, copy.deepcopy(network), epoch, 0
            else:
                stale += 1
            if stale >= patience:
                break
        neural = Pipeline([("preprocess", preprocess), ("classifier", best)])
        logistic = make_pipeline().fit(training[FEATURES], training.target)
        prior = DummyClassifier(strategy="prior").fit(training[FEATURES], training.target)
        candidates = {"deep_mlp": neural, "logistic": logistic, "prior": prior}
        report = {
            "version": VERSION,
            "audit": audit,
            "sklearn": sklearn.__version__,
            "architecture": [int(x_train.shape[1]), 32, 16, 8, 1],
            "activation": "relu_hidden_sigmoid_output",
            "optimizer": "adam",
            "seed": 42,
            "alpha": 0.01,
            "batch_size": min(1024, len(training)),
            "learning_rate": 0.001,
            "max_epochs": epochs,
            "patience": patience,
            "best_epoch": best_epoch,
            "learning_curve": learning_curve,
            "production_ready": False,
            "splits": {},
        }
        # Fijar selección antes de evaluar test.
        valid_metrics = {
            name: evaluate(validation.target, model.predict_proba(validation[FEATURES])[:, 1])
            for name, model in candidates.items()
        }
        eligible = [
            name
            for name in ("logistic", "deep_mlp")
            if valid_metrics[name]["average_precision"]
            > valid_metrics["prior"]["average_precision"]
            and valid_metrics[name]["brier"] < valid_metrics["prior"]["brier"]
        ]
        selected = (
            min(eligible, key=lambda n: valid_metrics[n]["log_loss"]) if eligible else "prior"
        )
        report["selected_on_validation"] = selected
        report["selection_rule"] = (
            "Mejor log-loss entre candidatos que mejoran AP y Brier del prior"
        )
        for split, part in splits.items():
            report["splits"][split] = {
                name: evaluate(part.target, model.predict_proba(part[FEATURES])[:, 1])
                for name, model in candidates.items()
            }
        if "customer_id" in splits["test"]:
            test = splits["test"]
            report["deep_test_uncertainty"] = bootstrap_intervals(
                test, neural.predict_proba(test[FEATURES])[:, 1]
            )
    report["limitations"] = [
        "Conversión de campaña, no intención explícita ni adquisición nueva.",
        "Mismas variables y supuestos retrospectivos que product_interest_v1.",
        "Test ya reportado para logística; no es una nueva validación externa.",
        "Una arquitectura y semilla; falta robustez entre semillas y cohortes.",
        "El ranking de productos refleja campañas observadas, no efectos causales.",
    ]
    artifact = {
        "version": VERSION,
        "features": FEATURES,
        "model": neural,
        "selected": "deep_mlp",
        "recommended_model": selected,
        "recommended_pipeline": candidates[selected],
        "products": sorted(training.promoted_product.unique().tolist()),
        "channels": sorted(training.send_channel.unique().tolist()),
        "report": report,
    }
    return artifact, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/noema.duckdb")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("data/models/deep_interest.joblib"))
    parser.add_argument("--report", type=Path, default=Path("ml/model_cards/deep_interest.json"))
    args = parser.parse_args()
    with duckdb.connect(args.database, read_only=True) as conn:
        frame, audit = build_examples(conn)
    artifact, report = train_deep(frame, audit, epochs=args.epochs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "best_epoch": report["best_epoch"],
                "selected": report["selected_on_validation"],
                "test": report["splits"]["test"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
