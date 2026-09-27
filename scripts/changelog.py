"""Control de cambios: genera CHANGELOG.md desde el historial de git.

Agrupa los commits por día y por tipo (Conventional Commits), nombra al autor y
detecta los identificadores del checklist mencionados en el mensaje — de modo que
cada cambio quede ligado al ítem del entregable que movió.

No sustituye a `docs/knowledge/contributions.md` (que mira fronteras y avance),
sino que responde otra pregunta: **qué cambió, cuándo y por qué**.

Uso:
    python -m scripts.changelog            # regenera CHANGELOG.md
    python -m scripts.changelog --print     # solo imprime
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path("CHANGELOG.md")

TIPOS = {
    "feat": "Nuevo",
    "fix": "Corregido",
    "perf": "Rendimiento",
    "refactor": "Refactor",
    "docs": "Documentación",
    "test": "Pruebas",
    "build": "Construcción",
    "ci": "Integración continua",
    "chore": "Mantenimiento",
    "revert": "Revertido",
}
ORDEN = list(TIPOS.values()) + ["Otros"]

RE_HEAD = re.compile(r"^(?P<tipo>[a-z]+)(?:\((?P<ambito>[^)]+)\))?(?P<bang>!)?:\s*(?P<texto>.+)$")
RE_ITEM = re.compile(r"\b((?:DAT|ML|SCM|AG|EV|API|UI|ENT|INF)-\d{2})\b")


def git(*args: str) -> str:
    """Lee el historial local. `git` es un binario de confianza del entorno y los
    argumentos son constantes del script, no entrada externa."""
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Control de cambios del proyecto")
    ap.add_argument("--print", dest="only_print", action="store_true")
    args = ap.parse_args()

    raw = git("log", "--no-merges", "--pretty=format:%H%x1f%an%x1f%ad%x1f%s%x1f%b", "--date=short")
    if not raw:
        print("Sin commits.")
        return 0

    por_dia: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    autores_dia: dict[str, set[str]] = defaultdict(set)

    for entry in raw.split("\n"):
        partes = entry.split("\x1f")
        if len(partes) < 4:
            continue
        sha, autor, fecha, asunto = partes[0], partes[1], partes[2], partes[3]
        cuerpo = partes[4] if len(partes) > 4 else ""

        m = RE_HEAD.match(asunto)
        if m:
            seccion = TIPOS.get(m.group("tipo"), "Otros")
            texto = m.group("texto")
            ambito = m.group("ambito")
            breaking = bool(m.group("bang")) or "BREAKING CHANGE" in cuerpo
        else:
            seccion, texto, ambito, breaking = "Otros", asunto, None, False

        items = sorted(set(RE_ITEM.findall(asunto + " " + cuerpo)))
        etiquetas = ""
        if ambito and not RE_ITEM.fullmatch(ambito or ""):
            etiquetas += f"**{ambito}** · "
        if items:
            etiquetas += " ".join(f"`{i}`" for i in items) + " · "

        linea = (
            f"- {'**RUPTURA** ' if breaking else ''}{etiquetas}{texto} "
            f"— {autor.split()[0]} (`{sha[:7]}`)"
        )
        por_dia[fecha][seccion].append(linea)
        autores_dia[fecha].add(autor.split()[0])

    lineas: list[str] = []
    lineas.append("# Control de cambios")
    lineas.append("")
    lineas.append(
        "Generado con `make changelog` desde el historial de git. Agrupa por día y por tipo, "
        "y liga cada cambio al ítem del checklist que movió."
    )
    lineas.append("")
    lineas.append(
        "Formato de commit: `tipo(ámbito): descripción`. Usa el identificador del ítem como "
        "ámbito cuando aplique — por ejemplo `feat(DAT-06): silver de productos`. "
        "Tipos: " + ", ".join(f"`{t}`" for t in TIPOS) + "."
    )
    lineas.append("")
    lineas.append(f"Última generación: {datetime.now():%Y-%m-%d %H:%M}")
    lineas.append("")

    for fecha in sorted(por_dia, reverse=True):
        quienes = ", ".join(sorted(autores_dia[fecha]))
        lineas.append(f"## {fecha} — {quienes}")
        lineas.append("")
        for seccion in ORDEN:
            if seccion in por_dia[fecha]:
                lineas.append(f"### {seccion}")
                lineas.append("")
                lineas.extend(por_dia[fecha][seccion])
                lineas.append("")

    texto = "\n".join(lineas)
    print(texto)

    if not args.only_print:
        OUT.write_text(texto + "\n", encoding="utf-8")
        print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
