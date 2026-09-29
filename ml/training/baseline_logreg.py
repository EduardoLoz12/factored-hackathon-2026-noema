"""Baseline de riesgo: regresión logística sobre `credit_score` — ML-02.

El baseline más simple que un banco defendería: una sola variable, la que el
propio banco ya calcula para decidir crédito. Cualquier modelo que no le gane a
esto no justifica su complejidad.

## Por qué este baseline importa más de lo normal

En este dataset el baseline **no discrimina**, y demostrarlo es el resultado.
`days_past_due` resulta ser una Bernoulli(0.075) sorteada de forma independiente
por producto de crédito, sin relación con ninguna variable — ver
`docs/knowledge/findings.md` F-017. El `credit_score` sí está bien construido
(correlaciona 0.356 con el ingreso, ordena por segmento), así que lo roto es la
etiqueta, no el score.

Un baseline en 0.50 no es un fracaso del baseline: es la medición que permite
decir, con evidencia, que ningún modelo sobre esta etiqueta puede hacerlo mejor.

## Qué mide

Además del AUC se calculan las métricas que un comité de riesgo pediría, porque
cada una falla de forma distinta y juntas cuentan la historia completa:

- **AUC-ROC** — probabilidad de ordenar bien un par mora/no-mora.
- **PR-AUC** — más honesta que el AUC cuando la clase positiva es rara (7.5 %).
  Su línea base es la tasa de mora, no 0.5.
- **KS** — máxima separación entre las acumuladas de buenos y malos. Es la
  métrica que la banca usa en la práctica.
- **Brier** — error cuadrático de la probabilidad. Mide calibración, no orden.
- **Brier skill** — el Brier contra el de predecir siempre la tasa base. Si sale
  negativo, el modelo es peor que no tener modelo.
- **Calibración por deciles** — dónde miente la probabilidad.

## Controles

Dos, y ninguno es decorativo:

- **Etiqueta barajada.** Se reentrena con la etiqueta permutada. Si el AUC real
  no supera claramente al barajado, no hay señal. Es el control que atrapa la
  fuga y el sobreajuste al mismo tiempo.
- **Intervalo por bootstrap.** 1 000 remuestreos sobre validación. Sin intervalo,
  un AUC de 0.52 sobre 2 000 filas no se distingue de 0.50.

Uso:
    python -m ml.training.baseline_logreg
    python -m ml.training.baseline_logreg --cohorte completa
"""

from __future__ import annotations

import argparse
import json
import logging
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore", category=FutureWarning)

log = logging.getLogger("baseline")

SEMILLA = 20260929
N_BOOTSTRAP = 1000
FRACCION_VALIDACION = 0.30

# La única variable del baseline. Es el punto: una sola, la del propio banco.
VARIABLE = "credit_score"


def cargar(ruta: Path, cohorte: str) -> pd.DataFrame:
    """Carga el feature store y se queda con la cohorte pedida.

    `completa` es la cohorte de trabajo: los 76 906 clientes con producto de
    crédito. `days_past_due` vive en una tabla de estado actual, así que su
    valor es el del momento del extracto —junio de 2026— que es posterior al
    corte para todos. Esa es la lectura correcta.

    `estricta` se conserva como análisis de sensibilidad. Exige además que
    `last_updated` sea posterior al corte, bajo el supuesto de que ese campo
    indica cuándo se registró el estado de mora. **Ese supuesto no se sostiene**
    y por eso la cohorte dejó de ser la principal: `last_updated` está repartido
    de forma uniforme sobre nueve años (KS contra uniforme 0.049, curtosis
    −1.161 contra −1.2 teórico) y es idéntico entre productos en mora y al día
    (media −182.3 días contra −181.6). Si un incumplimiento provocara una
    escritura de fila, los productos en mora tendrían `last_updated` reciente.
    No lo tienen: es un sello de modificación sorteado, no un registro de
    cuándo cambió la mora.

    Se mantiene porque si la conclusión aguanta con 7 078 clientes y con 76 906,
    la conclusión no depende de esa lectura.
    """
    df = pd.read_parquet(ruta)
    if cohorte == "estricta":
        # `mora_90_estricta` se agrega solo sobre productos observados después
        # del corte. Es una columna distinta de `mora_90` a propósito.
        df = df[df.etiqueta_posterior == 1].copy()
        df["mora_90"] = df.mora_90_estricta.astype(int)
    elif cohorte == "completa":
        df = df[df.etiquetable == 1].copy()
    else:
        raise ValueError(f"cohorte desconocida: {cohorte}")
    return df.reset_index(drop=True)


def ks(y: np.ndarray, p: np.ndarray) -> float:
    """Estadístico de Kolmogórov-Smirnov: la mayor brecha entre acumuladas."""
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def bootstrap_auc(y: np.ndarray, p: np.ndarray, n: int = N_BOOTSTRAP) -> tuple[float, float]:
    """Intervalo percentil del 95 % para el AUC, por remuestreo con reemplazo."""
    rng = np.random.default_rng(SEMILLA)
    vals = []
    idx = np.arange(len(y))
    for _ in range(n):
        s = rng.choice(idx, len(idx), replace=True)
        if len(np.unique(y[s])) < 2:
            continue
        vals.append(roc_auc_score(y[s], p[s]))
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def calibracion(y: np.ndarray, p: np.ndarray, k: int = 10) -> list[dict[str, Any]]:
    """Tasa observada contra probabilidad predicha, por decil de predicción."""
    orden = np.argsort(p)
    grupos = np.array_split(orden, k)
    out = []
    for i, g in enumerate(grupos, 1):
        if len(g) == 0:
            continue
        out.append(
            {
                "decil": i,
                "n": int(len(g)),
                "predicho": float(p[g].mean()),
                "observado": float(y[g].mean()),
                "p_min": float(p[g].min()),
                "p_max": float(p[g].max()),
            }
        )
    return out


def metricas(y: np.ndarray, p: np.ndarray, tasa_base: float) -> dict[str, Any]:
    """Todas las métricas de un conjunto, con su interpretación implícita."""
    brier = brier_score_loss(y, p)
    # Brier de predecir siempre la tasa base. Es el «no tener modelo».
    brier_ref = brier_score_loss(y, np.full_like(p, tasa_base))
    lo, hi = bootstrap_auc(y, p)
    return {
        "n": int(len(y)),
        "positivos": int(y.sum()),
        "tasa": float(y.mean()),
        "auc": float(roc_auc_score(y, p)),
        "auc_ic95": [lo, hi],
        "pr_auc": float(average_precision_score(y, p)),
        "pr_auc_base": float(y.mean()),  # la línea base del PR-AUC es la prevalencia
        "ks": ks(y, p),
        "brier": float(brier),
        "brier_referencia": float(brier_ref),
        "brier_skill": float(1 - brier / brier_ref) if brier_ref > 0 else None,
        "calibracion": calibracion(y, p),
    }


def entrenar(df: pd.DataFrame) -> dict[str, Any]:
    """Entrena, mide y corre el control de etiqueta barajada."""
    usable = df[df[VARIABLE].notna()].copy()
    descartadas = len(df) - len(usable)
    y = usable.mora_90.to_numpy()
    X = usable[[VARIABLE]].to_numpy(dtype=float)

    if len(np.unique(y)) < 2:
        raise SystemExit("La cohorte no tiene ambas clases: no se puede entrenar.")

    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=FRACCION_VALIDACION, random_state=SEMILLA, stratify=y
    )
    modelo = LogisticRegression(max_iter=2000).fit(Xtr, ytr)
    p_tr = modelo.predict_proba(Xtr)[:, 1]
    p_te = modelo.predict_proba(Xte)[:, 1]
    tasa = float(ytr.mean())

    # Control: la misma tubería con la etiqueta permutada. Si el AUC real no
    # supera claramente a este, no hay señal que reportar.
    rng = np.random.default_rng(SEMILLA)
    ytr_b = rng.permutation(ytr)
    modelo_b = LogisticRegression(max_iter=2000).fit(Xtr, ytr_b)
    auc_barajado = float(roc_auc_score(rng.permutation(yte), modelo_b.predict_proba(Xte)[:, 1]))

    return {
        "variable": VARIABLE,
        "filas_cohorte": int(len(df)),
        "filas_usables": int(len(usable)),
        "descartadas_por_variable_nula": int(descartadas),
        "coeficiente": float(modelo.coef_[0][0]),
        "intercepto": float(modelo.intercept_[0]),
        # El signo esperado es negativo: más score, menos mora.
        "signo_esperado": "negativo",
        "signo_observado": "negativo" if modelo.coef_[0][0] < 0 else "positivo",
        "entrenamiento": metricas(ytr, p_tr, tasa),
        "validacion": metricas(yte, p_te, tasa),
        "control_barajado_auc": auc_barajado,
        "semilla": SEMILLA,
        "fraccion_validacion": FRACCION_VALIDACION,
    }


def veredicto(r: dict[str, Any]) -> str:
    """Traduce las métricas a una frase que se pueda poner en una slide."""
    auc = r["validacion"]["auc"]
    lo, hi = r["validacion"]["auc_ic95"]
    if lo <= 0.5 <= hi:
        return (
            f"No discrimina. AUC {auc:.4f}, IC95 [{lo:.4f}, {hi:.4f}] — el intervalo "
            "contiene 0.5, así que no se distingue del azar."
        )
    if auc < 0.55:
        return f"Discriminación despreciable: AUC {auc:.4f}, IC95 [{lo:.4f}, {hi:.4f}]."
    return f"AUC {auc:.4f}, IC95 [{lo:.4f}, {hi:.4f}]."


def main() -> None:
    p = argparse.ArgumentParser(description="Baseline de riesgo con credit_score (ML-02)")
    p.add_argument("--features", type=Path, default=Path("data/gold/features_asof.parquet"))
    p.add_argument("--cohorte", choices=["completa", "estricta"], default="completa")
    p.add_argument("--salida", type=Path, default=None)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.features.exists():
        raise SystemExit(
            f"No existe {args.features}. Corre primero `python -m ml.features.build_features`."
        )

    salida = args.salida or Path(f"models/baseline_logreg_{args.cohorte}.json")
    df = cargar(args.features, args.cohorte)
    log.info(
        "cohorte %s: %s clientes, %s en mora (%.3f %%)",
        args.cohorte,
        f"{len(df):,}",
        f"{int(df.mora_90.sum()):,}",
        df.mora_90.mean() * 100,
    )

    r = entrenar(df)
    r["cohorte"] = args.cohorte
    r["features"] = args.features.as_posix()
    r["generado"] = datetime.now().isoformat(timespec="seconds")
    r["veredicto"] = veredicto(r)

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    v = r["validacion"]
    log.info("")
    log.info("  variable                 %s (una sola, a propósito)", VARIABLE)
    log.info("  coeficiente              %+.6f  (esperado negativo)", r["coeficiente"])
    log.info("")
    log.info("  validación · n = %s, %s positivos", f"{v['n']:,}", f"{v['positivos']:,}")
    log.info(
        "    AUC-ROC                %.4f   IC95 [%.4f, %.4f]",
        v["auc"],
        v["auc_ic95"][0],
        v["auc_ic95"][1],
    )
    log.info("    PR-AUC                 %.4f   (línea base = %.4f)", v["pr_auc"], v["pr_auc_base"])
    log.info("    KS                     %.4f", v["ks"])
    log.info(
        "    Brier                  %.6f  (sin modelo: %.6f)", v["brier"], v["brier_referencia"]
    )
    log.info("    Brier skill            %+.5f", v["brier_skill"])
    log.info("    control barajado       %.4f", r["control_barajado_auc"])
    log.info("")
    log.info("  %s", r["veredicto"])
    log.info("  escrito %s", salida)


if __name__ == "__main__":
    main()
