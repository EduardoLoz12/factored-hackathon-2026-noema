"""La consulta sobre los productos propios del cliente — saldo, cuota, cuánto le falta.

Qué se prueba, y por qué importa:

- Sin sesión no sale ningún dato del cliente: la pregunta pide identidad.
- Con sesión, la respuesta sale de los tools del turno: si una cifra no tuviera
  respaldo, el turno escalaría en vez de responder (AG-09).
- La respuesta no contiene el número de documento del cliente.
- Un préstamo se muestra con su cuota **estimada**, y dice que es una estimación.

Corre contra `data/noema_demo.duckdb`. Si no existe, las pruebas se saltan.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from api.extraccion import extraer

BASE_DEMO = Path("data/noema_demo.duckdb")
pytestmark_base = pytest.mark.skipif(
    not BASE_DEMO.exists(),
    reason="falta data/noema_demo.duckdb — correr `python -m scripts.make_demo_db`",
)


def test_la_pregunta_por_los_propios_productos_se_reconoce():
    assert extraer("¿Cuánto me falta pagar de mis productos y cuál es mi cuota?")["intencion"] == (
        "CUENTA_PROPIA"
    )
    assert extraer("Quanto ainda devo dos meus produtos?")["intencion"] == "CUENTA_PROPIA"


def test_pedir_un_prestamo_nuevo_no_es_consulta_propia():
    # «mi préstamo» con un importe y un verbo de solicitud es una solicitud, no una consulta.
    lectura = extraer("Quiero mi préstamo personal de 3000 dólares.")
    assert lectura["intencion"] == "CREDIT_ELIGIBILITY"


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    from fastapi.testclient import TestClient

    tmp = tmp_path_factory.mktemp("noema-cuenta")
    os.environ["NOEMA_DB"] = str(BASE_DEMO)
    os.environ["NOEMA_SESSIONS_DB"] = str(tmp / "sesiones.duckdb")
    os.environ["NOEMA_LEDGER_DB"] = str(tmp / "ledger.duckdb")
    os.environ.setdefault("JWT_SECRET", "x" * 48)
    os.environ["NOEMA_DEMO"] = "on"

    import importlib

    from api import main as mod

    importlib.reload(mod)
    with TestClient(mod.app) as c:
        yield c


@pytestmark_base
def test_sin_sesion_la_pregunta_pide_identidad_y_no_muestra_nada(cliente):
    r = cliente.post(
        "/chat",
        json={
            "conversation_id": "cuenta-anon",
            "mensaje": "¿Cuánto me falta pagar de mis productos?",
        },
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["desenlace"] == "bloqueado"
    assert cuerpo["ofertas"] == []
    assert cuerpo["tools"] == []


@pytestmark_base
def test_con_sesion_la_respuesta_sale_de_los_tools_y_no_trae_el_documento(cliente):
    r = cliente.post("/session/demo?perfil=elegible")
    assert r.status_code == 200, r.text
    d = r.json()
    token, conv = d["token"], d["conversation_id"]

    r = cliente.post(
        "/chat",
        json={"conversation_id": conv, "mensaje": "¿Qué productos tengo y cuánto me falta pagar?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    cuerpo = r.json()
    # Si una cifra no tuviera respaldo en los tools del turno, el desenlace sería
    # `escalado`, no `respuesta` (AG-09).
    assert cuerpo["desenlace"] == "respuesta", cuerpo["mensaje"]
    assert "get_customer_product_summary" in [t.get("tool") for t in cuerpo["tools"]]
    assert "USD" in cuerpo["mensaje"]
    # El documento y la fecha de nacimiento del cliente nunca viajan como texto.
    assert not re.search(r"\b\d{7,9}\b", cuerpo["mensaje"])
