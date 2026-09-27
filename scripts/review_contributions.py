"""Revisión de contribuciones: quién cambió qué, y si respetó su frontera.

El repo lo trabajan dos personas con áreas separadas. Este script responde tres
preguntas que el agente del proyecto necesita para saber si todo va sumando:

  1. ¿Qué commits hubo, de quién, y qué áreas del proyecto tocaron?
  2. ¿Alguien cruzó su frontera? (Federico solo debe tocar agent/cognition/)
  3. ¿Cómo va el avance contra los hitos del entregable?

Escribe el resultado en docs/knowledge/contributions.md, que es memoria del
proyecto: se versiona y sobrevive entre sesiones.

Uso:
    python -m scripts.review_contributions                # desde el último registro
    python -m scripts.review_contributions --since 3.days
    python -m scripts.review_contributions --dry-run      # solo imprime
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# La consola de Windows usa cp1252 por defecto y revienta con acentos o flechas
# que vienen de los mensajes de commit. Forzamos UTF-8 en la salida.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LEDGER = Path("docs/knowledge/contributions.md")

# Áreas del proyecto y a quién pertenecen. El orden importa: gana el prefijo
# más específico, por eso agent/cognition/ va antes que agent/.
AREAS: list[tuple[str, str, str]] = [
    ("agent/cognition/", "cognición (SCM)", "federico"),
    ("tests/cognition/", "cognición (SCM)", "federico"),
    ("tests/data/", "contratos de datos", "eduardo"),
    ("data_platform/", "plataforma de datos", "federico"),
    ("ml/training/capacity.py", "capacidad de pago", "federico"),
    ("ml/", "modelos", "eduardo"),
    ("agent/core/", "orquestador", "eduardo"),
    ("agent/tools/", "herramientas", "eduardo"),
    ("agent/policies/", "políticas", "eduardo"),
    ("agent/guardrails/", "guardrails", "eduardo"),
    ("agent/i18n/", "multilingüe", "eduardo"),
    ("agent/observability/", "observabilidad", "eduardo"),
    ("api/", "API", "eduardo"),
    ("ui/", "frontend", "eduardo"),
    ("eval/", "evaluación", "eduardo"),
    ("tests/fixtures/", "fixtures", "eduardo"),
    ("scripts/", "utilidades", "eduardo"),
    ("docs/", "documentación", "compartida"),
    (".claude/", "agentes", "compartida"),
    (".github/", "integración continua", "eduardo"),
]

# Hitos del entregable. Un hito se considera iniciado cuando existe la ruta.
MILESTONES: list[tuple[str, str]] = [
    ("Ingesta S3 → bronze", "data_platform/ingestion/ingest_s3.py"),
    ("Contratos de calidad", "data_platform/contracts/audit.py"),
    ("Transformaciones dbt", "data_platform/dbt/dbt_project.yml"),
    ("Modelo baseline", "ml/training/baseline_logreg.py"),
    ("Modelo de riesgo (PD)", "ml/training/pd_lightgbm.py"),
    ("Capacidad de pago", "ml/training/capacity.py"),
    ("Servicio de predicción", "ml/serving/predictor.py"),
    ("SCM (Federico)", "agent/cognition/scm.py"),
    ("Motor de reglas", "agent/policies/eligibility_v1.yaml"),
    ("Herramientas del agente", "agent/tools/registry.py"),
    ("Orquestador 6 etapas", "agent/core/orchestrator.py"),
    ("Guardrails / grounding", "agent/guardrails/grounding.py"),
    ("API", "api/main.py"),
    ("Frontend", "ui/package.json"),
    ("Generador de casos", "eval/generator/build_cases.py"),
    ("Harness de evaluación", "eval/harness/run.py"),
]


def git(*args: str) -> str:
    """Lee el historial local. `git` es un binario de confianza del entorno de
    desarrollo y los argumentos son constantes del script, no entrada externa."""
    return subprocess.run(  # noqa: S603, S607
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def classify(path: str) -> tuple[str, str]:
    """Devuelve (área, dueño) del archivo."""
    for prefix, area, owner in AREAS:
        if path.startswith(prefix):
            return area, owner
    return "raíz del proyecto", "compartida"


def owner_of_author(author: str) -> str:
    """Mapea el autor del commit a un dueño de frontera."""
    a = author.lower()
    if "federico" in a or "fedevargas" in a or "fvargas" in a:
        return "federico"
    return "eduardo"


def main() -> int:
    ap = argparse.ArgumentParser(description="Revisión de contribuciones por autor y frontera")
    ap.add_argument("--since", default=None, help='p.ej. "3.days", "2026-09-27"')
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rng = ["--since", args.since] if args.since else []
    raw = git("log", *rng, "--no-merges", "--pretty=format:%H%x1f%an%x1f%ad%x1f%s", "--date=short")
    if not raw:
        print("Sin commits en el rango.")
        return 0

    commits = []
    for line in raw.splitlines():
        sha, author, date, subject = line.split("\x1f")
        files = git("show", "--pretty=", "--name-only", sha).splitlines()
        commits.append(
            {
                "sha": sha[:7],
                "author": author,
                "date": date,
                "subject": subject,
                "files": [f for f in files if f],
            }
        )

    by_author: dict[str, list] = defaultdict(list)
    areas_touched: dict[str, set[str]] = defaultdict(set)
    violations: list[tuple[str, str, str, str]] = []

    for c in commits:
        who = owner_of_author(c["author"])
        by_author[c["author"]].append(c)
        for f in c["files"]:
            area, owner = classify(f)
            areas_touched[c["author"]].add(area)
            # La frontera es asimétrica y así está escrita en CLAUDE.md: Federico
            # solo toca la capa de cognición. Eduardo es responsable del resto del
            # entregable y sí puede andamiar el contrato de esa capa.
            if who == "federico" and owner == "eduardo":
                violations.append((c["sha"], c["author"], f, area))

    lines: list[str] = []
    lines.append(f"## Revisión · {datetime.now():%Y-%m-%d %H:%M}")
    lines.append("")
    rango = f"desde `{args.since}`" if args.since else "historial completo"
    lines.append(f"{len(commits)} commits · {rango}")
    lines.append("")

    lines.append("| Autor | Commits | Áreas tocadas |")
    lines.append("|---|---:|---|")
    for author, cs in sorted(by_author.items()):
        lines.append(f"| {author} | {len(cs)} | {', '.join(sorted(areas_touched[author]))} |")
    lines.append("")

    if violations:
        lines.append("### Cruces de frontera")
        lines.append("")
        lines.append("| Commit | Autor | Archivo | Área |")
        lines.append("|---|---|---|---|")
        for sha, author, f, area in violations:
            lines.append(f"| `{sha}` | {author} | `{f}` | {area} |")
        lines.append("")
        lines.append(
            "> Federico solo debe tocar `agent/cognition/` y `tests/cognition/`. "
            "Un cruce no es necesariamente un error, pero tiene que ser deliberado y conversado."
        )
    else:
        lines.append("### Fronteras")
        lines.append("")
        lines.append("Sin cruces. Cada quien trabajó dentro de su área.")
    lines.append("")

    lines.append("### Avance contra los hitos del entregable")
    lines.append("")
    lines.append("| Hito | Estado |")
    lines.append("|---|---|")
    done = 0
    for name, path in MILESTONES:
        exists = Path(path).exists()
        done += exists
        lines.append(f"| {name} | {'existe' if exists else 'pendiente'} |")
    lines.append("")
    lines.append(f"**{done} de {len(MILESTONES)} hitos iniciados.**")
    lines.append("")
    lines.append("### Commits")
    lines.append("")
    for c in commits[:40]:
        lines.append(f"- `{c['sha']}` · {c['date']} · **{c['author']}** — {c['subject']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    block = "\n".join(lines)
    print(block)

    if args.dry_run:
        return 0

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Bitácora de contribuciones\n\n"
        "Generada por `make review`. Responde quién cambió qué, si respetó su frontera, "
        "y cómo va el avance contra los hitos del entregable.\n\n"
        "Las revisiones más recientes van arriba.\n\n---\n\n"
    )
    previous = ""
    if LEDGER.exists():
        text = LEDGER.read_text(encoding="utf-8")
        previous = text.split("---\n\n", 1)[1] if "---\n\n" in text else text
    LEDGER.write_text(header + block + previous, encoding="utf-8")
    print(f"\n→ {LEDGER}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
