"""Checklist vivo del entregable.

Lee la lista canónica de `docs/checklist.json` y la evalúa contra el estado real
del repositorio: qué archivos existen, si todavía son esqueleto, y quién tocó
cada uno por última vez. Renderiza `docs/knowledge/checklist.md`.

La idea es que nadie tenga que actualizar estados a mano: cuando Eduardo o
Federico hacen un commit que crea o completa un archivo de evidencia, el ítem
correspondiente avanza solo en la siguiente corrida.

Estados:
    falta      ningún archivo de evidencia existe
    avanzado   existe parte, o existe todo pero sigue habiendo NotImplementedError
    terminado  se cumple el criterio del ítem

Uso:
    python -m scripts.checklist                      # re-evalúa y escribe
    python -m scripts.checklist --print              # solo imprime
    python -m scripts.checklist --done SCM-06 --note "26/26 en verde"
    python -m scripts.checklist --undone SCM-06
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SPEC = Path("docs/checklist.json")
STATE = Path("docs/knowledge/checklist_state.json")
OUT = Path("docs/knowledge/checklist.md")

FALTA, AVANZADO, TERMINADO = "falta", "avanzado", "terminado"
MARK = {FALTA: "[ ]", AVANZADO: "[~]", TERMINADO: "[x]"}

DIAS = {
    1: "D1 · 27-sep",
    2: "D2 · 28-sep",
    3: "D3 · 29-sep",
    4: "D4 · 30-sep",
    5: "D5 · 1-oct",
    6: "D6 · 2-oct",
    7: "D7 · 3-oct",
    8: "D8 · 4-oct",
    9: "D9 · 5-oct",
}


def git(*args: str) -> str:
    """Lee el historial local. `git` es un binario de confianza del entorno y los
    argumentos son constantes del script, no entrada externa."""
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def last_touch(paths: list[str]) -> str:
    """Quién tocó por última vez alguno de estos archivos."""
    existing = [p for p in paths if Path(p).exists()]
    if not existing:
        return "—"
    out = git("log", "-1", "--pretty=format:%an|%ad", "--date=short", "--", *existing)
    if not out or "|" not in out:
        return "sin commit"
    author, date = out.split("|", 1)
    short = author.split()[0] if author else "?"
    return f"{short} · {date}"


def is_stub(path: str) -> bool:
    try:
        return "NotImplementedError" in Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def evaluate(item: dict, overrides: dict) -> str:
    if item["id"] in overrides:
        return overrides[item["id"]]["status"]

    paths = item.get("evidence", [])
    rule = item.get("done", "paths")

    if rule == "manual":
        # Sin override, se infiere solo lo evidente: si no hay nada, falta.
        present = [p for p in paths if Path(p).exists()]
        if not paths or not present:
            return FALTA
        return AVANZADO

    present = [p for p in paths if Path(p).exists()]
    if not present:
        return FALTA
    if len(present) < len(paths):
        return AVANZADO
    if rule == "nostub" and any(is_stub(p) for p in present):
        return AVANZADO
    return TERMINADO


def bar(done: int, total: int, width: int = 12) -> str:
    filled = round(width * done / total) if total else 0
    return "█" * filled + "░" * (width - filled)


def main() -> int:
    ap = argparse.ArgumentParser(description="Checklist vivo del entregable")
    ap.add_argument("--done", metavar="ID", help="marca un ítem como terminado")
    ap.add_argument("--advanced", metavar="ID", help="marca un ítem como avanzado")
    ap.add_argument("--undone", metavar="ID", help="quita la marca manual de un ítem")
    ap.add_argument("--note", default="", help="nota que acompaña la marca")
    ap.add_argument("--print", dest="only_print", action="store_true")
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    overrides: dict = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}

    for flag, status in ((args.done, TERMINADO), (args.advanced, AVANZADO)):
        if flag:
            overrides[flag] = {
                "status": status,
                "note": args.note,
                "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
    if args.undone:
        overrides.pop(args.undone, None)
    if args.done or args.advanced or args.undone:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")

    total = {FALTA: 0, AVANZADO: 0, TERMINADO: 0}
    per_owner: dict[str, dict[str, int]] = {}
    lines: list[str] = []

    lines.append("# Checklist del entregable")
    lines.append("")
    lines.append(
        "Generado por `make checklist` contra el estado real del repo. "
        "Cuando alguien crea o completa un archivo de evidencia, el ítem avanza solo "
        "en la siguiente corrida. **No editar estados a mano aquí** — usar "
        '`python -m scripts.checklist --done ID --note "..."`.'
    )
    lines.append("")
    lines.append(f"Última evaluación: {datetime.now():%Y-%m-%d %H:%M}")
    lines.append("")
    lines.append("Estados: `[ ]` falta · `[~]` avanzado · `[x]` terminado")
    lines.append("")

    body: list[str] = []
    for area in spec["areas"]:
        rows = []
        counts = {FALTA: 0, AVANZADO: 0, TERMINADO: 0}
        for item in area["items"]:
            status = evaluate(item, overrides)
            counts[status] += 1
            total[status] += 1
            owner = item.get("owner", area["owner"])
            per_owner.setdefault(owner, {FALTA: 0, AVANZADO: 0, TERMINADO: 0})
            per_owner[owner][status] += 1
            note = overrides.get(item["id"], {}).get("note", "")
            rows.append(
                f"| {MARK[status]} | `{item['id']}` | {item['tarea']} | {owner.capitalize()} | "
                f"{DIAS.get(item['dia'], item['dia'])} | {last_touch(item.get('evidence', []))} |"
                + (f" {note}" if note else "")
            )
        n = sum(counts.values())
        body.append(f"## {area['nombre']} — {counts[TERMINADO]}/{n} `{bar(counts[TERMINADO], n)}`")
        body.append("")
        body.append("|  | ID | Tarea | Dueño | Día | Último movimiento |")
        body.append("|---|---|---|---|---|---|")
        body.extend(rows)
        body.append("")

    n = sum(total.values())
    lines.append(f"## Avance global — {total[TERMINADO]}/{n} `{bar(total[TERMINADO], n, 24)}`")
    lines.append("")
    lines.append(
        f"**{total[TERMINADO]} terminado · {total[AVANZADO]} avanzado · {total[FALTA]} falta**"
    )
    lines.append("")
    lines.append("| Dueño | Terminado | Avanzado | Falta | Total |")
    lines.append("|---|---:|---:|---:|---:|")
    for owner, c in sorted(per_owner.items()):
        lines.append(
            f"| {owner.capitalize()} | {c[TERMINADO]} | {c[AVANZADO]} | {c[FALTA]} | "
            f"{sum(c.values())} |"
        )
    lines.append("")
    lines.extend(body)

    text = "\n".join(lines)
    print(text)

    if not args.only_print:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text + "\n", encoding="utf-8")
        print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
