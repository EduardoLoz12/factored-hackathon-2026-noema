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
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path("CHANGELOG.md")

# Prefijos en espanol, que es lo que se lee en GitHub. Se aceptan tambien los
# ingleses de Conventional Commits por los commits que ya existian.
TIPOS = {
    "nuevo": "Nuevo",
    "corrige": "Corregido",
    "mejora": "Mejorado",
    "docs": "Documentacion",
    "pruebas": "Pruebas",
    "infra": "Infraestructura",
    "limpieza": "Limpieza",
    "revierte": "Revertido",
    # equivalencias en ingles
    "feat": "Nuevo",
    "fix": "Corregido",
    "perf": "Mejorado",
    "refactor": "Mejorado",
    "test": "Pruebas",
    "build": "Infraestructura",
    "ci": "Infraestructura",
    "chore": "Limpieza",
    "revert": "Revertido",
}
ORDEN = [
    "Nuevo",
    "Corregido",
    "Mejorado",
    "Documentacion",
    "Pruebas",
    "Infraestructura",
    "Limpieza",
    "Revertido",
    "Otros",
]

RE_HEAD = re.compile(
    r"^(?P<tipo>[A-Za-zÁÉÍÓÚÑáéíóúñ]+)(?:\((?P<ambito>[^)]+)\))?(?P<bang>!)?:\s*(?P<texto>.+)$"
)


def normaliza(t: str) -> str:
    """minusculas y sin tildes, para buscar el tipo."""
    base = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return base.lower()


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
            seccion = TIPOS.get(normaliza(m.group("tipo")), "Otros")
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
        "Formato de commit: `Tipo (ÍTEM): qué cambió, en español y sin jerga`. "
        "Por ejemplo: `Nuevo (DAT-06): la capa silver normaliza los tipos de producto "
        "que venían en español y en inglés`. "
        "Tipos: `Nuevo`, `Corrige`, `Mejora`, `Docs`, `Pruebas`, `Infra`, `Limpieza`, `Revierte`."
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
