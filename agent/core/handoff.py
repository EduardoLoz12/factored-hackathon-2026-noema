"""El expediente de escalamiento, validado por esquema — AG-08.

El reto lo pide así: «structured handoff… **not raw transcripts**» (slide 11). Un
expediente con hechos verificados, las acciones ejecutadas y las preguntas abiertas —
no la conversación.

Lo que un esquema aporta acá **no son los tipos**. Que un campo sea `str` no evita
ninguno de los problemas reales. Lo que se valida es:

1. **Todo hecho tiene fuente.** Si un bloque de `hechos_verificados` no aparece en
   `fuentes`, se está entregando como verificado algo cuya procedencia nadie puede
   responder. Eso vacía la palabra «verificado».
2. **No viaja PII en claro.** `document_number`, correo, teléfono y nombres no tienen
   nada que hacer en el expediente: el humano busca al cliente por su identificador
   (`docs/05_security.md` §5). Se rechaza por **nombre de campo, a cualquier
   profundidad**, no por inspección manual.
3. **El texto del cliente va aparte y marcado.** Si pudiera mezclarse con los hechos,
   lo que el cliente dijo se leería como establecido.
4. **Nada de NaN ni infinitos.** Un expediente que no se puede serializar no se puede
   guardar ni releer, y la relectura de AG-07 fallaría después, no antes.

**Falla degradado, no cerrado.** Si el expediente no se puede armar bien, el caso **se
abre igual** con un expediente mínimo marcado como incompleto. El escalamiento existe
para que una persona atienda al cliente: negarlo porque nuestro propio ensamblado falló
castigaría al cliente por un bug nuestro. Lo que no se hace es entregarlo como completo.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

# Campos que no pueden aparecer en un expediente, a ninguna profundidad. El asesor
# localiza al cliente por `customer_id`; el resto es exposición sin uso.
CAMPOS_PROHIBIDOS = frozenset(
    {
        "document_number",
        "document_type",
        "date_of_birth",
        "email",
        "mobile_phone",
        "landline_phone",
        "phone",
        "address",
        "first_name",
        "last_name",
        "full_name",
    }
)

# Bloques que un expediente completo tiene que traer. `evidencia_faltante` está en la
# lista a propósito: un expediente que omite lo que faltó esconde lo que el humano más
# necesita saber.
BLOQUES_REQUERIDOS = (
    "hechos_verificados",
    "fuentes",
    "ofertas_cotizadas",
    "evidencia_faltante",
    "pregunta_abierta_no_verificada",
    "conversation_id",
)

PROFUNDIDAD_MAXIMA = 12


class ExpedienteInvalido(Exception):
    """El expediente no cumple el esquema. Lleva la lista de problemas."""

    def __init__(self, problemas: list[str]) -> None:
        super().__init__("; ".join(problemas))
        self.problemas = problemas


@dataclass
class Validacion:
    """Resultado de validar. `ok` solo es True si no hay ningún problema."""

    ok: bool
    problemas: list[str] = field(default_factory=list)

    def a_traza(self) -> dict[str, Any]:
        return {"etapa": "ESCALATE", "esquema_ok": self.ok, "problemas": list(self.problemas)}


def _recorrer(nodo: Any, ruta: str, problemas: list[str], profundidad: int = 0) -> None:
    """Busca campos prohibidos y números no finitos, a cualquier profundidad."""
    if profundidad > PROFUNDIDAD_MAXIMA:
        problemas.append(f"{ruta}: anidamiento mayor a {PROFUNDIDAD_MAXIMA} niveles")
        return
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if str(clave).lower() in CAMPOS_PROHIBIDOS:
                # No se dice el valor en el mensaje: sería filtrarlo en el log.
                problemas.append(f"{ruta}.{clave}: dato personal que no va en el expediente")
            _recorrer(valor, f"{ruta}.{clave}", problemas, profundidad + 1)
    elif isinstance(nodo, (list, tuple)):
        for i, valor in enumerate(nodo):
            _recorrer(valor, f"{ruta}[{i}]", problemas, profundidad + 1)
    elif isinstance(nodo, float) and not math.isfinite(nodo):
        problemas.append(f"{ruta}: número no finito ({nodo})")


def validar(expediente: Any) -> Validacion:
    """Comprueba el esquema. No lanza: devuelve los problemas para decidir qué hacer."""
    problemas: list[str] = []
    if not isinstance(expediente, dict):
        return Validacion(ok=False, problemas=["el expediente no es un objeto"])

    for bloque in BLOQUES_REQUERIDOS:
        if bloque not in expediente:
            problemas.append(f"falta el bloque obligatorio «{bloque}»")

    hechos = expediente.get("hechos_verificados")
    fuentes = expediente.get("fuentes")
    if not isinstance(hechos, dict):
        problemas.append("hechos_verificados: debe ser un objeto")
        hechos = {}
    if not isinstance(fuentes, dict):
        problemas.append("fuentes: debe ser un objeto")
        fuentes = {}

    # El corazón del esquema: un hecho sin fuente no es un hecho verificado.
    sin_fuente = sorted(set(hechos) - set(fuentes))
    if sin_fuente:
        problemas.append("hechos sin fuente declarada: " + ", ".join(sin_fuente))
    # Una fuente sin hecho es menos grave, pero indica un ensamblado roto.
    huerfanas = sorted(set(fuentes) - set(hechos))
    if huerfanas:
        problemas.append("fuentes que no respaldan ningún hecho: " + ", ".join(huerfanas))

    for bloque in ("evidencia_faltante", "ofertas_cotizadas"):
        if bloque in expediente and not isinstance(expediente[bloque], list):
            problemas.append(f"{bloque}: debe ser una lista")

    pregunta = expediente.get("pregunta_abierta_no_verificada")
    if pregunta is not None and not isinstance(pregunta, str):
        problemas.append("pregunta_abierta_no_verificada: debe ser texto o nulo")

    _recorrer(expediente, "expediente", problemas)
    return Validacion(ok=not problemas, problemas=problemas)


def expediente_degradado(conversation_id: str | None, problemas: list[str]) -> dict[str, Any]:
    """Expediente mínimo y **marcado**, para cuando el ensamblado falla.

    El caso se abre igual: el escalamiento existe para que una persona atienda al
    cliente, y negarlo por un bug nuestro lo castigaría a él. Lo que no se hace es
    entregarlo como completo — el asesor ve que está degradado y por qué.
    """
    LOGGER.error("expediente_degradado problemas=%s", problemas)
    return {
        "hechos_verificados": {},
        "fuentes": {},
        "ofertas_cotizadas": [],
        "evidencia_faltante": ["expediente_no_ensamblado"],
        "pregunta_abierta_no_verificada": None,
        "conversation_id": conversation_id,
        # Las dos marcas que impiden leerlo como un expediente normal.
        "degradado": True,
        "problemas_de_esquema": list(problemas),
    }


def validar_o_degradar(
    expediente: Any, conversation_id: str | None
) -> tuple[dict[str, Any], Validacion]:
    """Devuelve el expediente a guardar y el resultado de la validación."""
    resultado = validar(expediente)
    if resultado.ok:
        return expediente, resultado
    return expediente_degradado(conversation_id, resultado.problemas), resultado
