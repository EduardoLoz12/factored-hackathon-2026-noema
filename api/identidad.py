"""La identidad se verifica conversando — etapa 0 del ciclo.

Hasta ahora la demostración abría la sesión con un botón y el jurado nunca veía la
etapa que más pesa en el contrato de seguridad. Acá el agente **pide** los tres
factores, los va juntando turno a turno y no entrega nada hasta tenerlos los tres.

Lo que esta capa hace y lo que no:

- **Hace:** leer del texto del cliente el tipo de documento, el número y la fecha de
  nacimiento, y decir cuáles faltan.
- **No hace:** decidir si la identidad es válida. Eso lo resuelve `AccessGuard` contra
  la base, con sus tres intentos y su espera creciente. Esta capa solo arma los
  parámetros de esa llamada.

Los tres factores son los que el dataset permite. El teléfono **no** es uno: el 48.4 %
de los clientes tiene prefijo de otro país (F-004), así que usarlo sería un hallazgo en
nuestra contra.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Los cuatro tipos que existen en la base, con las formas en que la gente los nombra.
TIPOS = {
    "DNI": ("dni", "documento nacional"),
    "CC": ("cc", "cedula de ciudadania", "cedula ciudadania"),
    "CE": ("ce", "cedula de extranjeria", "cedula extranjeria"),
    "Pasaporte": ("pasaporte", "passport", "pasaport"),
}

# 1990-05-10 · 10/05/1990 · 10-05-1990
ISO = re.compile(r"\b(19|20)\d{2}-\d{1,2}-\d{1,2}\b")
LATINA = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.]((?:19|20)\d{2})\b")
MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "setembro": 9,
    "outubro": 10,
    "dezembro": 12,
}
# 22 abril 1995 · 22 de abril de 1995 · 22 abr 1995 (y la forma portuguesa)
EN_PALABRAS = re.compile(r"\b(\d{1,2})\s+(?:de\s+)?([a-zçãé]+)\.?\s+(?:de\s+)?((?:19|20)\d{2})\b")
# El número de documento: de 6 a 14 caracteres, puede empezar por letra (pasaporte).
NUMERO = re.compile(r"\b([A-Za-z]{0,2}\d{5,13})\b")

FACTORES = ("document_type", "document_number", "date_of_birth")
NOMBRE = {
    "document_type": ("el tipo de documento", "o tipo de documento"),
    "document_number": ("el número de documento", "o número do documento"),
    "date_of_birth": ("tu fecha de nacimiento", "sua data de nascimento"),
}


def _plano(texto: str) -> str:
    sin = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin if unicodedata.category(c) != "Mn")


def leer(texto: str) -> dict[str, str]:
    """Saca del mensaje los factores que estén. No inventa los que falten."""
    p = _plano(texto)
    salida: dict[str, str] = {}

    for canonico, formas in TIPOS.items():
        if any(re.search(rf"\b{re.escape(f)}\b", p) for f in formas):
            salida["document_type"] = canonico
            break

    fecha = ISO.search(texto)
    lat = LATINA.search(texto)
    palabras = EN_PALABRAS.search(_plano(texto))
    if fecha:
        a, m, d = fecha.group(0).split("-")
        salida["date_of_birth"] = f"{a}-{int(m):02d}-{int(d):02d}"
    elif lat:
        d, m, a = lat.groups()
        salida["date_of_birth"] = f"{a}-{int(m):02d}-{int(d):02d}"
    elif palabras and _plano(palabras.group(2)) in {_plano(k) for k in MESES}:
        d, mes, a = palabras.groups()
        m = MESES[next(k for k in MESES if _plano(k) == _plano(mes))]
        salida["date_of_birth"] = f"{a}-{m:02d}-{int(d):02d}"

    # El número se busca después de retirar la fecha, o se llevaría sus dígitos.
    resto = texto
    if "date_of_birth" in salida:
        if fecha:
            resto = resto.replace(fecha.group(0), " ")
        elif lat:
            resto = LATINA.sub(" ", resto)
        else:
            resto = EN_PALABRAS.sub(" ", _plano(resto))
    num = NUMERO.search(resto)
    if num:
        salida["document_number"] = num.group(1).upper()

    return salida


def sin_identidad(texto: str, factores: dict[str, str]) -> str:
    """El mensaje sin sus datos de identidad, para que no se lean como importes.

    Sin esto, un documento de 8 dígitos entra al extractor como un monto de crédito y el
    turno se va al workflow equivocado.
    """
    salida = texto
    if factores.get("document_number"):
        salida = re.sub(re.escape(factores["document_number"]), " ", salida, flags=re.I)
    if "date_of_birth" in factores:
        salida = ISO.sub(" ", salida)
        salida = LATINA.sub(" ", salida)
        salida = EN_PALABRAS.sub(" ", _plano(salida))
        salida = re.sub(r"\b(19|20)\d{2}\b", " ", salida)
    return salida


def faltantes(reunidos: dict[str, Any]) -> list[str]:
    return [f for f in FACTORES if not reunidos.get(f)]


def pedir(faltan: list[str], idioma: str = "es", primera_vez: bool = True) -> str:
    """El mensaje que pide lo que falta. Dice por qué, no solo qué."""
    pt = idioma == "pt"
    nombres = [NOMBRE[f][1 if pt else 0] for f in faltan]
    if len(nombres) > 1:
        unidos = ", ".join(nombres[:-1]) + (" e " if pt else " y ") + nombres[-1]
    else:
        unidos = nombres[0] if nombres else ""

    if primera_vez:
        if pt:
            return (
                "Antes de falar dos seus produtos preciso confirmar que é você. "
                f"Pode me dizer {unidos}?"
            )
        return (
            f"Antes de hablar de tus productos necesito confirmar que eres tú. ¿Me dices {unidos}?"
        )
    if pt:
        return f"Obrigado. Ainda me falta {unidos}."
    return f"Gracias. Todavía me falta {unidos}."


def confirmada(idioma: str = "es") -> str:
    """La frase que confirma la identidad cuando el mismo mensaje trae también un pedido."""
    return "Identidade confirmada." if idioma == "pt" else "Identidad confirmada."


def bienvenida(idioma: str = "es") -> str:
    if idioma == "pt":
        return "Identidade confirmada. Em que posso lhe ajudar?"
    return "Identidad confirmada. ¿En qué puedo ayudarte?"
