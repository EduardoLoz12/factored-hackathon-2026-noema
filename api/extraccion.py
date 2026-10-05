"""De texto del cliente a slots — la única pieza donde el lenguaje entra al sistema.

El contrato del proyecto es que **el modelo extrae y el orquestador decide**. Acá se
hace la extracción, y está escrita para funcionar sin modelo: un extractor determinista
sobre expresiones regulares, con el LLM como mejora opcional. Dos razones:

1. El jurado tiene que poder correr el sistema sin llave de API. Si `/chat` dependiera
   del modelo para extraer, sin llave no hay demo.
2. Una extracción determinista es reproducible, y las trazas del conjunto retenido se
   pueden volver a generar iguales.

Lo que **no** hace: decidir. Devuelve datos; la elegibilidad la calcula la política.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

LOGGER = logging.getLogger(__name__)

# El orden importa: se recorre de lo más específico a lo más general. «crédito
# hipotecario» tiene que dar hipotecario, y con «credito» entre las pistas de la
# tarjeta daba tarjeta — la palabra «crédito» por sí sola no nombra un producto, es
# la categoría entera. Así que la tarjeta exige que se la nombre.
PRODUCTOS = (
    ("Préstamo Hipotecario", ("hipotec", "vivienda", "imovel", "imóvel", "casa propia")),
    ("Tarjeta Crédito", ("tarjeta", "cartao", "cartão")),
    ("Préstamo Personal", ("prestamo", "préstamo", "personal", "emprestimo", "empréstimo")),
)

MONEDAS = {
    "USD": ("dolar", "dólar", "dolares", "dólares", "usd", "us$"),
    "COP": ("peso colombiano", "pesos colombianos", "cop"),
    "ARS": ("peso argentino", "pesos argentinos", "ars"),
    "MXN": ("peso mexicano", "pesos mexicanos", "mxn"),
}

PIDE_HUMANO = (
    "asesor",
    "una persona",
    "humano",
    "atendente",
    "pessoa",
    "hablar con alguien",
    "falar com",
)

# `muéstrame` lleva el pronombre adosado y la tilde movida: un patrón escrito en
# inglés deja pasar la mitad de las formas en español (F-041).
CONSULTA = (
    "condicion",
    "condiç",
    "cuanto cuesta",
    "que tasa",
    "qué tasa",
    "cual es la tasa",
    "cuál es la tasa",
    "informacion",
    "información",
    "informaç",
    "requisito",
    "saber",
    "me interesa saber",
)

# Pedir los datos que el banco tiene guardados no es una consulta de producto ni una
# solicitud de crédito: es otra cosa, y no se resuelve por este canal. Reconocerla
# sirve para escalar diciendo por qué, en vez de contestar «no entendí».
# Un sustantivo solo no alcanza: «quiero cambiar mi dirección postal» nombra un dato
# personal y no es una petición de datos. Hace falta el verbo de petición **y** el dato.
VERBOS_PEDIR = (
    "dame",
    "dime",
    "damelo",
    "muestrame",
    "enviame",
    "mandame",
    "pasame",
    "me das",
    "me puedes dar",
    "cual es mi",
    "cuales son mis",
    "necesito saber",
    "quiero saber",
    "me diga",
    "me passe",
    "me envie",
    "qual e o meu",
    "quais sao os meus",
)

DATOS_GUARDADOS = (
    "documento",
    "telefono",
    "correo",
    "email",
    "direccion",
    "fecha de nacimiento",
    "data de nascimento",
    "datos registrados",
    "datos que tienes",
    "tienes registrados",
    "tienes registrado",
    "meus dados",
    "numero de identidad",
)

PIDE_MONTO = (
    "quiero",
    "quisiera",
    "necesito",
    "solicitar",
    "pedir",
    "gostaria",
    "preciso",
    "quero",
)

# 1 500 · 1.500 · 1,500 · 1500.50 — y el separador de miles varía por país.
NUMERO = re.compile(r"\d[\d\s.,]{0,14}\d|\d")


def _plano(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar sin depender de la acentuación."""
    sin = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin if unicodedata.category(c) != "Mn")


def _a_numero(bruto: str) -> float | None:
    """Interpreta un importe escrito a la latinoamericana.

    La trampa: `1.500` son mil quinientos en Colombia y uno punto cinco en notación
    anglosajona. Se resuelve por posición — si el último separador deja exactamente
    tres dígitos a su derecha, es separador de miles.
    """
    s = bruto.strip().replace(" ", "")
    if not s:
        return None
    ultimo_punto, ultima_coma = s.rfind("."), s.rfind(",")
    corte = max(ultimo_punto, ultima_coma)
    if corte == -1:
        limpio = s
    else:
        decimales = len(s) - corte - 1
        if decimales == 3:
            limpio = s.replace(".", "").replace(",", "")
        else:
            limpio = s[:corte].replace(".", "").replace(",", "") + "." + s[corte + 1 :]
    try:
        return float(limpio)
    except ValueError:
        return None


def detectar_idioma(texto: str) -> str:
    """Español o portugués. Solo dos, porque solo dos pide el reto."""
    p = _plano(texto)
    marcas_pt = ("voce", "nao", "obrigado", "bom dia", "gostaria", "emprestimo", "cartao", "mes")
    marcas_es = ("usted", "buenos dias", "quisiera", "prestamo", "tarjeta", "gracias", "mes")
    pt = sum(1 for m in marcas_pt if m in p)
    es = sum(1 for m in marcas_es if m in p)
    return "pt" if pt > es else "es"


def extraer(texto: str) -> dict[str, Any]:
    """Devuelve intención, slots e idioma. Nunca decide nada."""
    p = _plano(texto)
    slots: dict[str, Any] = {}

    producto = None
    for nombre, pistas in PRODUCTOS:
        if any(x in p for x in pistas):
            producto = nombre
            break
    if producto:
        slots["product_type"] = producto

    moneda = None
    for codigo, pistas in MONEDAS.items():
        if any(x in p for x in pistas):
            moneda = codigo
            break

    monto = None
    for bruto in NUMERO.findall(texto):
        v = _a_numero(bruto)
        # Un importe de crédito no es 3 ni 48: los números pequeños son plazos,
        # cantidades de productos o partes de una fecha.
        if v is not None and v >= 100:
            monto = v
            break
    if monto is not None:
        slots["requested_amount"] = monto
        # Si pidió un importe sin nombrar moneda, se asume la del catálogo, que
        # está en USD, y se declara como supuesto en la traza.
        slots["currency"] = moneda or "USD"
    elif moneda:
        slots["currency"] = moneda

    pide_humano = any(x in p for x in PIDE_HUMANO)
    pide_datos = any(v in p for v in VERBOS_PEDIR) and any(x in p for x in DATOS_GUARDADOS)
    consulta = any(x in p for x in CONSULTA)
    pide = any(x in p for x in PIDE_MONTO)

    # Un verbo de solicitud no basta: «quiero cambiar mi dirección» también empieza
    # con «quiero». Para que el turno entre al workflow de crédito tiene que haber un
    # producto del catálogo o un importe. Si no, es otra cosa y se escala.
    del_workflow = producto is not None or monto is not None
    if pide_datos:
        # Fuera del workflow a propósito: el turno escala y la redacción dice por qué.
        intencion = "DATOS_PERSONALES"
    elif pide_humano:
        intencion = "CREDIT_ELIGIBILITY"
    elif consulta and del_workflow and not (pide and monto is not None):
        intencion = "PRODUCT_INFO"
    elif del_workflow and (pide or monto is not None):
        intencion = "CREDIT_ELIGIBILITY"
    else:
        # Fuera del workflow. El orquestador lo escala en vez de improvisar.
        intencion = "DESCONOCIDA"

    return {
        "intencion": intencion,
        "slots": slots,
        "idioma": detectar_idioma(texto),
        "pide_humano": pide_humano,
        "pide_datos_personales": pide_datos,
        "supuestos": (
            ["moneda asumida en USD porque no se nombró ninguna"]
            if monto is not None and moneda is None
            else []
        ),
    }
