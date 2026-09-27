"""Bitácora de trabajo: una entrada por sesión, por persona, por día.

Responde la pregunta que ni el checklist ni el changelog responden: **qué pasó
durante el trabajo** — qué se decidió, qué se rompió, qué quedó a medias y qué
sigue. El commit dice qué cambió; la bitácora dice por qué y con qué fricción.

Los archivos viven en `logs/worklog/YYYY-MM-DD-<persona>.md` y **sí se versionan**,
a diferencia del resto de `logs/`, porque son documentación del avance.

Uso:
    python -m scripts.worklog "Silver de productos y clientes"    # abre/crea la entrada de hoy
    python -m scripts.worklog --list                               # últimas entradas
    python -m scripts.worklog --show                               # imprime la de hoy
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DIR = Path("logs/worklog")

PLANTILLA = """# {fecha} · {persona}

## {hora} — {titulo}

**Ítems del checklist que moví**
- `XXX-00` — qué quedó y en qué estado (avanzado / terminado)

**Qué hice**
-

**Decisiones que tomé**
- (si cambia algo del contrato o de la arquitectura, va también a `docs/decisions/`)

**Qué se rompió o me frenó**
- (si contradice una suposición previa, va también a `docs/knowledge/findings.md`)

**Qué sigue**
-

---
"""

ENTRADA = """
## {hora} — {titulo}

**Ítems del checklist que moví**
- `XXX-00` —

**Qué hice**
-

**Decisiones que tomé**
-

**Qué se rompió o me frenó**
-

**Qué sigue**
-

---
"""


def git(*args: str) -> str:
    """Lee la configuración local de git. Argumentos constantes del script."""
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout.strip()


def slug(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-") or "anonimo"


def persona() -> str:
    nombre = git("config", "user.name") or "anonimo"
    return slug(nombre.split()[0])


def ruta_hoy() -> Path:
    return DIR / f"{date.today():%Y-%m-%d}-{persona()}.md"


def main() -> int:
    ap = argparse.ArgumentParser(description="Bitácora de trabajo")
    ap.add_argument("titulo", nargs="?", default=None, help="en qué trabajaste")
    ap.add_argument("--list", dest="listar", action="store_true")
    ap.add_argument("--show", dest="mostrar", action="store_true")
    args = ap.parse_args()

    DIR.mkdir(parents=True, exist_ok=True)
    destino = ruta_hoy()

    if args.listar:
        entradas = sorted(DIR.glob("*.md"), reverse=True)
        if not entradas:
            print('Sin entradas todavía. Crea una: python -m scripts.worklog "en qué trabajaste"')
            return 0
        for p in entradas[:15]:
            titulos = [
                ln[3:].strip()
                for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.startswith("## ")
            ]
            print(f"{p.name}  ({len(titulos)} sesion{'es' if len(titulos) != 1 else ''})")
            for t in titulos:
                print(f"    · {t}")
        return 0

    if args.mostrar:
        if destino.exists():
            print(destino.read_text(encoding="utf-8"))
        else:
            print('Sin entrada para hoy. Crea una: python -m scripts.worklog "título"')
        return 0

    if not args.titulo:
        ap.error('falta el título: python -m scripts.worklog "en qué trabajaste"')

    ahora = datetime.now().strftime("%H:%M")
    if destino.exists():
        destino.write_text(
            destino.read_text(encoding="utf-8").rstrip()
            + "\n"
            + ENTRADA.format(hora=ahora, titulo=args.titulo),
            encoding="utf-8",
        )
        print(f"Sesión agregada a {destino}")
    else:
        destino.write_text(
            PLANTILLA.format(
                fecha=f"{date.today():%Y-%m-%d}",
                persona=persona().capitalize(),
                hora=ahora,
                titulo=args.titulo,
            ),
            encoding="utf-8",
        )
        print(f"Bitácora creada: {destino}")

    print("Rellénala antes de cerrar la sesión. Se commitea junto con el trabajo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
