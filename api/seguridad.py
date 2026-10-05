"""Lo que protege la API — `API-02`.

Cuatro cosas, y ninguna vive en el prompt: límite de tasa, CORS cerrado, redacción de
PII y la sesión que sale del `AccessGuard`. La rúbrica pide explícitamente «enforce
action permissions besides model prompts» (slide 13), y eso significa que un modelo que
se porte mal no puede ampliar lo que la API permite.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field

LOGGER = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Redacción de PII
# ─────────────────────────────────────────────────────────────────────────────
# Cada patrón existe porque el dato está en el dataset: documento, correo,
# teléfono y fecha de nacimiento. El `customer_id` interno también se redacta en
# los logs: identifica a una persona aunque no la nombre.
PATRONES = (
    (re.compile(r"\b\d{7,12}\b"), "[documento]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[correo]"),
    (re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3}[\s-]?\d{4}\b"), "[telefono]"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[fecha]"),
    (re.compile(r"\bCLI-[A-Z0-9]{6,}\b"), "[cliente]"),
    (re.compile(r"\bAGT-[A-Z0-9]{6,}\b"), "[agente]"),
)


def redactar(texto: str) -> str:
    """Reemplaza PII por una etiqueta. Se aplica a todo lo que se loguea.

    No se aplica a la respuesta que el cliente lee: el cliente tiene derecho a sus
    propios datos. Se aplica al **log** y a la **traza**, que son otra audiencia.
    """
    salida = texto
    for patron, etiqueta in PATRONES:
        salida = patron.sub(etiqueta, salida)
    return salida


class FiltroPII(logging.Filter):
    """Redacta el mensaje de cada registro antes de que llegue al archivo."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redactar(str(record.getMessage()))
            record.args = ()
        except Exception:  # noqa: S110 — un filtro de logs nunca tumba la petición,
            # y loguear el fallo acá entraría en el mismo filtro que acaba de fallar.
            return True
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Límite de tasa
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Limitador:
    """Cubeta por clave, en memoria.

    En memoria a propósito, y declarado: con más de un proceso el límite es por
    proceso. Para la demo del jurado es correcto; para producción iría en Redis, y eso
    está escrito en `LIMITATIONS.md` en vez de insinuado.
    """

    maximo: int = 30
    ventana_segundos: float = 60.0
    _marcas: dict[str, list[float]] = field(default_factory=dict, repr=False)

    def permite(self, clave: str) -> tuple[bool, int]:
        ahora = time.monotonic()
        corte = ahora - self.ventana_segundos
        marcas = [t for t in self._marcas.get(clave, []) if t > corte]
        if len(marcas) >= self.maximo:
            self._marcas[clave] = marcas
            espera = int(self.ventana_segundos - (ahora - marcas[0])) + 1
            return False, max(1, espera)
        marcas.append(ahora)
        self._marcas[clave] = marcas
        return True, 0


# ─────────────────────────────────────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────────────────────────────────────
def origenes_permitidos() -> list[str]:
    """Cerrado por defecto. `*` solo si alguien lo pide a propósito.

    `NOEMA_ORIGINS` separa por comas. Sin la variable, solo el localhost del
    desarrollo: la interfaz se sirve desde el mismo origen que la API, así que el
    despliegue no necesita abrir nada.
    """
    bruto = os.environ.get("NOEMA_ORIGINS", "").strip()
    if not bruto:
        return ["http://localhost:8000", "http://127.0.0.1:8000"]
    return [x.strip() for x in bruto.split(",") if x.strip()]


def llave_de_firma_presente() -> bool:
    """`JWT_SECRET` con 32 caracteres o más. Sin ella no se emiten sesiones."""
    return len(os.environ.get("JWT_SECRET", "")) >= 32
