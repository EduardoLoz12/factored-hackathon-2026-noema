"""El caso de evaluación y su etiqueta — `EV-01`.

Un caso no es un texto suelto: es un texto **más** el resultado que el sistema debería
alcanzar y la razón por la que ese resultado es el correcto. Sin esa segunda mitad no
hay evaluación, hay demo.

De dónde sale cada parte, que es lo que la rúbrica llama «valid labels»:

- El **texto** se arma sobre las dos plantillas reales de `stg_call_transcripts`
  (`ADR-0003`). El dataset trae dos moldes, un solo intent y placeholders sin rellenar
  —`{monto}`, `{moneda}`—, así que sirven como registro de habla, no como corpus.
- La **etiqueta** la calcula `agent/policies/engine.py` sobre los hechos del cliente
  leídos de la base. Es un cálculo versionado y reproducible, no un juicio.
- El **cliente** es real: un `customer_id` de `noema_silver.stg_customers`.

Los casos en portugués se declaran construidos: el dataset no tiene una sola línea en
portugués (`LIMITATIONS.md` §1).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Familia(StrEnum):
    """Qué está probando el caso. Cada familia tiene su propia regla de etiqueta."""

    INFO_PRODUCTO = "info_producto"
    ELEGIBILIDAD = "elegibilidad"
    FALTA_DATO = "falta_dato"
    PIDE_HUMANO = "pide_humano"
    INTENCION_DESCONOCIDA = "intencion_desconocida"
    SIN_VERIFICAR = "sin_verificar"
    # El cliente afirma un dato que la base contradice. Es la única familia donde
    # `tools` y `tools_scm` pueden diferir: sin SCM no hay nada que detecte el
    # conflicto, y por eso es la familia que hace medible el tercer brazo.
    CONTRADICCION = "contradiccion"
    # Adversariales — `EV-04`.
    INYECCION = "inyeccion"
    SUPLANTACION = "suplantacion"
    EXFILTRACION = "exfiltracion"

    @property
    def adversarial(self) -> bool:
        return self in {Familia.INYECCION, Familia.SUPLANTACION, Familia.EXFILTRACION}


# Qué desenlace cuenta como correcto. `Desenlace` vive en el orquestador; acá se guarda
# como cadena para que el archivo de casos no dependa del código del agente.
DESENLACES = {"respuesta", "pregunta", "escalado", "bloqueado"}


@dataclass
class Caso:
    """Un caso retenido, con su etiqueta y la procedencia de la etiqueta."""

    case_id: str
    familia: Familia
    idioma: str  # "es" | "pt"
    customer_id: str | None
    intencion: str
    texto: str
    slots: dict[str, Any] = field(default_factory=dict)
    verificado: bool = True
    pide_humano: bool = False
    producto_elegido: list[Any] | None = None

    # ── la etiqueta ──────────────────────────────────────────────────────────
    desenlace_esperado: str = "respuesta"
    # Varios desenlaces pueden ser correctos para el mismo caso, y forzar uno solo
    # convierte un acierto en un fallo contable. Pasó con los adversariales: el
    # sistema pregunta por el monto que falta y nunca llega a la inyección — no
    # obedeció, no filtró y no escribió, así que preguntar es seguro. Vacío
    # significa «solo el esperado».
    desenlaces_aceptables: list[str] = field(default_factory=list)
    # Por qué ese desenlace es el correcto. Se escribe para que un juez pueda
    # discutir la etiqueta sin leer el código.
    razon_etiqueta: str = ""
    # De dónde sale: "politica_v3" | "maquina_de_estados" | "contrato_de_seguridad".
    fuente_etiqueta: str = "politica_v3"
    # Datos que NO deben aparecer en la respuesta. En los adversariales es el
    # corazón de la prueba: si alguno aparece, la acción fue insegura.
    prohibido: list[str] = field(default_factory=list)
    # Plantilla real sobre la que se construyó el texto.
    plantilla: str = ""

    def __post_init__(self) -> None:
        if self.desenlace_esperado not in DESENLACES:
            raise ValueError(f"desenlace desconocido: {self.desenlace_esperado!r}")
        for d in self.desenlaces_aceptables:
            if d not in DESENLACES:
                raise ValueError(f"desenlace aceptable desconocido: {d!r}")
        if not self.razon_etiqueta:
            raise ValueError(f"{self.case_id}: una etiqueta sin razón no es una etiqueta")
        if self.idioma not in {"es", "pt"}:
            raise ValueError(f"idioma no soportado: {self.idioma!r}")

    @property
    def aceptables(self) -> set[str]:
        """Los desenlaces que cuentan como correctos para este caso."""
        return set(self.desenlaces_aceptables) or {self.desenlace_esperado}

    def a_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["familia"] = self.familia.value
        return d

    @classmethod
    def de_json(cls, d: dict[str, Any]) -> Caso:
        d = dict(d)
        d["familia"] = Familia(d["familia"])
        return cls(**d)


def escribir(casos: list[Caso], ruta: Path) -> Path:
    """Un caso por línea. JSONL para poder leer el archivo sin cargarlo entero."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8") as fh:
        for c in casos:
            fh.write(json.dumps(c.a_json(), ensure_ascii=False) + "\n")
    return ruta


def leer(ruta: Path) -> list[Caso]:
    if not ruta.exists():
        return []
    casos = []
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if linea:
                casos.append(Caso.de_json(json.loads(linea)))
    return casos
