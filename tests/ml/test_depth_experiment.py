"""El experimento de profundidad no selecciona pesos con etiquetas de test."""

import numpy as np
import pandas as pd

from ml.training.depth_experiment import fit_candidate, run_experiment
from ml.training.product_interest import FEATURES
from tests.ml.test_product_interest import example_frame


def experiment_frame():
    frame = example_frame()
    frame.loc[400:599, "send_date"] = pd.Timestamp("2025-01-01")
    frame.loc[600:799, "send_date"] = pd.Timestamp("2025-03-10")
    return frame


def test_six_hidden_layers_fit_and_invalid_config():
    import pytest

    frame = example_frame()
    model, report = fit_candidate(
        frame.iloc[:400], frame.iloc[400:800], (32, 32, 16, 16, 8, 8), 42, epochs=2
    )
    assert len(model.named_steps["classifier"].coefs_) == 7
    assert report["best_epoch"] <= report["epochs_run"] == 2
    with pytest.raises(ValueError):
        fit_candidate(frame, frame, (8,), 42, epochs=0)


def test_test_outcomes_never_control_depth_selection(tmp_path):
    frame = experiment_frame()
    first, report = run_experiment(frame, {}, tmp_path / "one", epochs=2, seeds=(42,))
    changed = frame.copy()
    changed.loc[800:, "target"] = 1 - changed.loc[800:, "target"]
    second, other = run_experiment(changed, {}, tmp_path / "two", epochs=2, seeds=(42,))
    assert report["preferred_neural_family"] == other["preferred_neural_family"]
    assert report["recommended_model"] == other["recommended_model"]
    np.testing.assert_allclose(
        first["model"].predict_proba(frame[FEATURES]),
        second["model"].predict_proba(frame[FEATURES]),
    )
    assert (tmp_path / "one" / "deeper_interest.joblib").exists()
