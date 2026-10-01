"""Experimento predefinido de profundidad: 3 vs 6 capas, tres semillas, sin ajustar test."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from threadpoolctl import threadpool_limits

from ml.training.product_interest import (
    FEATURES,
    build_examples,
    evaluate,
    make_pipeline,
    split_examples,
)

ARCHITECTURES = {"three_hidden": (32, 16, 8), "six_hidden": (32, 32, 16, 16, 8, 8)}
SEEDS = (42, 43, 44)


def fit_candidate(training, stopping, layers, seed, epochs=30, patience=4):
    """Aprende transformaciones en train y pesos sin observar selección ni test."""
    if epochs < 1 or patience < 1 or not layers or any(n < 1 for n in layers):
        raise ValueError("Configuración inválida")
    preprocess = make_pipeline().named_steps["preprocess"]
    x = preprocess.fit_transform(training[FEATURES])
    xv = preprocess.transform(stopping[FEATURES])
    net = MLPClassifier(
        hidden_layer_sizes=layers,
        activation="relu",
        solver="adam",
        alpha=0.01,
        batch_size=min(1024, len(training)),
        learning_rate_init=0.001,
        random_state=seed,
        early_stopping=False,
    )
    best, best_loss, best_epoch, stale = None, float("inf"), 0, 0
    curve = []
    for epoch in range(1, epochs + 1):
        net.partial_fit(x, training.target, classes=np.array([0, 1]))
        loss = float(log_loss(stopping.target, net.predict_proba(xv)))
        if not np.isfinite(loss):
            raise ValueError("Pérdida no finita")
        curve.append(
            {"epoch": epoch, "train_objective": float(net.loss_), "stopping_log_loss": loss}
        )
        if loss < best_loss - 1e-7:
            best, best_loss, best_epoch, stale = copy.deepcopy(net), loss, epoch, 0
        else:
            stale += 1
        if stale >= patience:
            break
    model = Pipeline([("preprocess", preprocess), ("classifier", best)])
    return model, {
        "seed": seed,
        "hidden_layers": list(layers),
        "best_epoch": best_epoch,
        "epochs_run": len(curve),
        "curve": curve,
        "parameters": sum(w.size for w in best.coefs_ + best.intercepts_),
        "stopped_early": len(curve) < epochs,
    }


def run_experiment(frame, audit, output_dir, epochs=30, seeds=SEEDS):
    if 42 not in seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Incluir semilla fija 42, sin duplicados")
    splits = split_examples(frame)
    training = splits["train"]
    validation = splits["validation"]
    # 30 días entre última etiqueta de stopping y primera exposición de selección.
    dates = pd.to_datetime(validation.send_date)
    stopping = validation[dates < "2025-02-01"]
    selection = validation[dates >= "2025-03-03"]
    if "process_date" in stopping:
        stopping = stopping[pd.to_datetime(stopping.process_date) < "2025-03-03"]
    for part in (stopping, selection):
        if len(part) < 100 or part.target.nunique() != 2:
            raise ValueError("Enero y marzo requieren al menos 100 filas y ambas clases")
    report = {
        "version": "depth_experiment_v1",
        "audit": audit,
        "seeds": list(seeds),
        "epochs_limit": epochs,
        "patience": 4,
        "alpha": 0.01,
        "learning_rate": 0.001,
        "runs": {},
        "summary": {},
        "protocol": (
            "train hasta nov-2024; stopping enero; selección desde marzo-03; test desde mayo"
        ),
        "production_ready": False,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with threadpool_limits(limits=2):
        logistic = make_pipeline().fit(training[FEATURES], training.target)
        prior = float(training.target.mean())
        logistic_metrics = evaluate(
            selection.target, logistic.predict_proba(selection[FEATURES])[:, 1]
        )
        prior_metrics = evaluate(selection.target, np.full(len(selection), prior))
        report["selection_baselines"] = {"logistic": logistic_metrics, "prior": prior_metrics}
        fixed = {}
        for name, layers in ARCHITECTURES.items():
            report["runs"][name] = []
            for seed in seeds:
                model, run = fit_candidate(training, stopping, layers, seed, epochs=epochs)
                run["selection"] = evaluate(
                    selection.target, model.predict_proba(selection[FEATURES])[:, 1]
                )
                run["train"] = evaluate(
                    training.target, model.predict_proba(training[FEATURES])[:, 1]
                )
                report["runs"][name].append(run)
                if seed == 42:
                    fixed[name] = model
                print(
                    json.dumps(
                        {
                            "architecture": name,
                            "seed": seed,
                            "best_epoch": run["best_epoch"],
                            "selection_log_loss": run["selection"]["log_loss"],
                        }
                    ),
                    flush=True,
                )
            report["summary"][name] = {
                metric: {
                    "mean": float(np.mean([r["selection"][metric] for r in report["runs"][name]])),
                    "std": float(np.std([r["selection"][metric] for r in report["runs"][name]])),
                }
                for metric in ("log_loss", "average_precision", "roc_auc", "brier")
            }
        report["preferred_neural_family"] = min(
            report["summary"], key=lambda n: report["summary"][n]["log_loss"]["mean"]
        )
        # El modelo profundo solicitado siempre se entrega. Semilla 42 fijada de antemano.
        deep = report["runs"]["six_hidden"][list(seeds).index(42)]["selection"]
        promote = (
            deep["log_loss"] < logistic_metrics["log_loss"]
            and deep["average_precision"] > logistic_metrics["average_precision"]
            and deep["brier"] < logistic_metrics["brier"]
        )
        report["recommended_model"] = "six_hidden" if promote else "logistic"
        # La recomendación queda fijada antes de leer etiquetas de test.
        test = splits["test"]
        report["test_fixed_seed_42"] = {
            name: evaluate(test.target, model.predict_proba(test[FEATURES])[:, 1])
            for name, model in {**fixed, "logistic": logistic}.items()
        }
    report["limitations"] = [
        "Test reutilizado de ML-11/12; no equivale a validación externa nueva.",
        "Tres semillas describen sensibilidad; su desviación no es intervalo de confianza.",
        "Sin validación en clientes exclusivamente nuevos ni múltiples cortes rodantes.",
        "Conversión no es intención explícita ni solvencia; uso experimental.",
    ]
    artifact = {
        "version": "deep_interest_v1",
        "features": FEATURES,
        "model": fixed["six_hidden"],
        "selected": "deep_mlp_six_hidden",
        "recommended_model": report["recommended_model"],
        "recommended_pipeline": fixed["six_hidden"] if promote else logistic,
        "products": sorted(training.promoted_product.unique().tolist()),
        "channels": sorted(training.send_channel.unique().tolist()),
        "report": report,
    }
    joblib.dump(artifact, output_dir / "deeper_interest.joblib")
    return artifact, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/noema.duckdb")
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()
    with duckdb.connect(args.database, read_only=True) as conn:
        frame, audit = build_examples(conn)
    _, report = run_experiment(frame, audit, Path("data/models"), epochs=args.epochs)
    Path("ml/model_cards/depth_experiment.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
