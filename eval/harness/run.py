"""Corre los tres brazos y publica el resultado — `EV-05`, `EV-06`, `EV-07`.

    python -m eval.harness.run              # sin LLM: el baseline queda sin correr
    python -m eval.harness.run --llm        # los tres brazos, con el modelo real

Escribe `eval/results/resultados.json` con el detalle caso por caso y
`eval/results/comparacion.md` con las tablas. El detalle se versiona: una corrida que no
se puede auditar caso por caso no es evidencia.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from eval.casos import leer
from eval.harness.brazos import (
    BASE,
    MODELO,
    cliente_anthropic,
    correr_baseline,
    correr_tools,
    redactor_llm,
)
from eval.harness.metricas import Panel, panel, tabla

LOGGER = logging.getLogger(__name__)

DATOS = Path("eval/datasets")
SALIDA = Path("eval/results")
CONJUNTOS = {
    "Español (retenido)": DATOS / "es_holdout.jsonl",
    "Portugués de Brasil (construido)": DATOS / "pt_holdout.jsonl",
    "Adversarial": DATOS / "adversarial.jsonl",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Harness de los tres brazos (EV-05)")
    ap.add_argument("--llm", action="store_true", help="corre el baseline y la prosa con el modelo")
    ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--limite", type=int, default=0, help="recorta cada conjunto, para probar")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.base.exists():
        print(f"No existe {args.base}. Correr `make ingest` y `make build` primero.")
        return 2

    cliente = cliente_anthropic() if args.llm else None
    if args.llm and cliente is None:
        print("Se pidió --llm pero no hay cliente disponible. El baseline quedará sin correr.")
    redactor = redactor_llm(cliente) if cliente is not None else None

    todo: list[dict] = []
    secciones: list[str] = []
    resumen: dict[str, dict] = {}

    for titulo, ruta in CONJUNTOS.items():
        casos = leer(ruta)
        if not casos:
            print(f"{titulo}: sin casos en {ruta}; correr `python -m eval.generator.build`")
            continue
        if args.limite:
            casos = casos[: args.limite]
        print(f"{titulo}: {len(casos)} casos")

        resultados = []
        resultados += correr_baseline(casos, cliente=cliente)
        resultados += correr_tools(
            casos, scm=False, base=args.base, redactor=redactor, contador=cliente
        )
        resultados += correr_tools(
            casos, scm=True, base=args.base, redactor=redactor, contador=cliente
        )

        paneles: list[Panel] = [panel(b, resultados) for b in ("baseline", "tools", "tools_scm")]
        secciones.append(tabla(paneles, titulo))
        resumen[titulo] = {p.brazo: p.a_json() for p in paneles}
        todo += [r.a_json() for r in resultados]
        for p in paneles:
            print(
                f"   {p.brazo:>10}: resolución segura {p.resolucion_segura * 100:5.1f} % · "
                f"inseguras {p.acciones_inseguras:>2} · "
                f"anclaje {'—' if p.anclaje is None else f'{p.anclaje * 100:.1f} %'}"
            )

    if not todo:
        print("No se corrió nada.")
        return 1

    SALIDA.mkdir(parents=True, exist_ok=True)
    corrida = {
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "modelo": MODELO if cliente is not None else None,
        "con_llm": cliente is not None,
        "resumen": resumen,
        "detalle": todo,
    }
    (SALIDA / "resultados.json").write_text(
        json.dumps(corrida, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )

    cabecera = [
        "# Resultados de la evaluación — tres brazos",
        "",
        f"Corrida del {corrida['fecha']}.",
        f"Modelo de la prosa y del baseline: `{corrida['modelo'] or 'no corrido'}`.",
        "",
        "Generado por `make eval`. El detalle caso por caso está en `resultados.json`.",
        "",
        "Las tres columnas se diferencian en una sola cosa: de dónde puede salir una "
        "cifra. `baseline` tiene el modelo y el catálogo como texto; `tools` tiene las "
        "once herramientas, la política versionada, la relectura y el grounding; "
        "`tools_scm` añade el estado semántico con procedencia y la detección de "
        "contradicciones.",
        "",
        "**La abstención no se penaliza.** Preguntar cuando falta un dato y escalar "
        "cuando la política se abstiene son los resultados correctos de esos casos.",
        "",
    ]
    (SALIDA / "comparacion.md").write_text("\n".join(cabecera) + "\n".join(secciones), "utf-8")
    print(f"\n-> {SALIDA / 'comparacion.md'}\n-> {SALIDA / 'resultados.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
