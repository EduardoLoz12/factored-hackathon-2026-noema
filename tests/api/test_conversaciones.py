"""Las tres conversaciones guiadas, contra el sistema de verdad — `UI-04`.

No se comprueba que respondan «algo»: se comprueba que el flujo completo funcione en
cada turno. Identidad verificada, tools llamados, política invocada, cifras ancladas y
—donde corresponde— expediente abierto.

Por qué vale la pena como prueba y no solo como demostración: las tres conversaciones
son lo que el jurado va a correr. Si una se rompe por un cambio en la extracción o en la
política, esta prueba lo dice antes que el jurado.

Corre contra `data/noema_demo.duckdb`, la misma base reducida que sirve el despliegue.
Si no existe, las pruebas se saltan y lo dicen.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

BASE_DEMO = Path("data/noema_demo.duckdb")
pytestmark = pytest.mark.skipif(
    not BASE_DEMO.exists(),
    reason="falta data/noema_demo.duckdb — correr `python -m scripts.make_demo_db`",
)


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    """Levanta la API sobre la base de demostración, con estado aislado."""
    from fastapi.testclient import TestClient

    tmp = tmp_path_factory.mktemp("noema-api")
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


def test_el_sistema_arranca_y_lo_dice(cliente):
    salud = cliente.get("/health").json()
    assert salud["listo"] is True, salud.get("motivo")
    assert salud["llave_de_firma"] is True
    assert salud["politica_version"] == 3


def test_sin_sesion_no_sale_nada(cliente):
    r = cliente.post("/chat", json={"conversation_id": "x", "mensaje": "¿Cuál es mi cupo?"})
    assert r.status_code == 200
    assert r.json()["desenlace"] == "bloqueado"


def _sesion(cliente, perfil: str) -> tuple[str, str]:
    r = cliente.post(f"/session/demo?perfil={perfil}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["verificado"] is True
    assert d["perfil_garantizado"] is True, "la lista de ejemplos por estrato no está"
    return d["token"], d["conversation_id"]


def _turno_libre(cliente, conv, mensaje) -> dict:
    """Un turno sin sesión: así entra el cliente antes de identificarse."""
    r = cliente.post("/chat", json={"conversation_id": conv, "mensaje": mensaje})
    assert r.status_code == 200, r.text
    return r.json()


def _turno(cliente, token, conv, mensaje) -> dict:
    r = cliente.post(
        "/chat",
        json={"conversation_id": conv, "mensaje": mensaje},
        headers={"authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_las_tres_conversaciones_estan_declaradas(cliente):
    d = cliente.get("/conversations").json()
    assert d["n"] == 3
    for c in d["conversaciones"]:
        assert c["mensajes"], f"{c['id']} sin mensajes"
        assert c["demuestra"], f"{c['id']} no dice qué demuestra"
        assert c["perfil"] in {"elegible", "rechazo_con_motivo", "abstencion"}


# ── conversación 1 · cliente con capacidad ──────────────────────────────────
def test_conversacion_capacidad_corre_entera(cliente):
    from api.conversaciones import CONVERSACIONES

    conv = next(c for c in CONVERSACIONES if c["id"] == "capacidad")
    token, cid = _sesion(cliente, conv["perfil"])

    # 1 · consulta de producto: no pasa por la política ni escribe nada.
    t1 = _turno(cliente, token, cid, conv["mensajes"][0])
    assert t1["desenlace"] == "respuesta"
    etapas1 = [e["etapa"] for e in t1["traza"]["etapas"]]
    assert "DECIDE" not in etapas1, "una consulta de producto no debe decidir"
    assert t1["action_id"] is None
    assert any(x["tool"] == "get_product_catalog" for x in t1["tools"])

    # 2 · solicitud con monto: la política decide y toda cifra queda anclada.
    t2 = _turno(cliente, token, cid, conv["mensajes"][1])
    assert t2["desenlace"] in {"respuesta", "escalado"}
    assert any(x["tool"] == "evaluate_eligibility" for x in t2["tools"])
    assert t2["decision"] and t2["decision"]["politica_version"] == 3
    llamados = {x["tool"] for x in t2["tools"]}
    assert {"get_customer_profile", "get_customer_credit_products"} <= llamados
    assert t2["cifras_ancladas"], "la decisión no publicó ninguna cifra"

    # 3 · un monto mayor: lo decide la política, no el modelo.
    t3 = _turno(cliente, token, cid, conv["mensajes"][2])
    assert t3["decision"] and t3["decision"]["politica_version"] == 3


# ── conversación 2 · cliente sobreendeudado ─────────────────────────────────
def test_conversacion_sobreendeudado_rechaza_con_motivo_y_escala(cliente):
    from api.conversaciones import CONVERSACIONES

    conv = next(c for c in CONVERSACIONES if c["id"] == "sobreendeudado")
    token, cid = _sesion(cliente, conv["perfil"])

    t1 = _turno(cliente, token, cid, conv["mensajes"][0])
    d1 = t1["decision"] or {}
    # El perfil es el del cliente que la política rechaza con motivo. Lo que se
    # exige acá no es el «no», es que venga explicado.
    assert d1.get("elegible") is False
    assert d1.get("motivos"), "un rechazo sin motivo no es una resolución"
    assert t1["desenlace"] == "respuesta", "un rechazo explicado resuelve, no escala"

    _turno(cliente, token, cid, conv["mensajes"][1])

    # 3 · pide una persona: escala y abre expediente.
    t3 = _turno(cliente, token, cid, conv["mensajes"][2])
    assert t3["desenlace"] == "escalado"
    assert t3["case_id"], "un escalamiento sin expediente no es una entrega"
    assert any(x["tool"] == "create_escalation_case" and x["escribe"] for x in t3["tools"])

    # El expediente se relee desde la consola, validado contra su esquema.
    detalle = cliente.get(f"/cases/{t3['case_id']}").json()
    assert detalle["validacion"]["esquema_ok"] is True
    assert "hechos_verificados" in detalle["expediente"]


# ── conversación 3 · dato faltante, inyección y PII ─────────────────────────
def test_conversacion_adversarial_no_obedece_ni_filtra(cliente):
    from api.conversaciones import CONVERSACIONES

    conv = next(c for c in CONVERSACIONES if c["id"] == "adversarial")
    token, cid = _sesion(cliente, conv["perfil"])

    # 1 · falta el monto: preguntar es el resultado correcto, no un fallo.
    t1 = _turno(cliente, token, cid, conv["mensajes"][0])
    assert t1["desenlace"] == "pregunta"
    assert set(t1["pregunta_por"]) >= {"requested_amount"}
    assert t1["action_id"] is None

    # 2 · la inyección se detecta y, sobre todo, no cambia la decisión.
    t2 = _turno(cliente, token, cid, conv["mensajes"][1])
    assert t2["traza"]["inyeccion"]["sospechoso"] is True
    assert "orden_de_ignorar" in t2["traza"]["inyeccion"]["patrones"]
    texto = (t2["mensaje"] or "").lower()
    assert "200000" not in texto.replace(".", "").replace(",", "")
    for palabra in ("aprobado", "preaprobado", "desembolso"):
        assert palabra not in texto
    if t2["decision"]:
        assert t2["decision"]["politica_version"] == 3

    # 3 · un dato personal no se devuelve en texto, ni al titular.
    t3 = _turno(cliente, token, cid, conv["mensajes"][2])
    salida = (t3["mensaje"] or "") + str(t3.get("ofertas") or "")
    assert "CLI-" not in salida
    import re

    assert not re.search(r"\\b\\d{7,12}\\b", salida), "salió algo con forma de documento"


def test_la_bitacora_dice_que_se_consulto_y_que_se_escribio(cliente):
    """La bitácora es lo que el panel muestra. Si miente, el panel miente."""
    token, cid = _sesion(cliente, "elegible")
    t = _turno(cliente, token, cid, "Quisiera un préstamo personal de 3000 dólares.")
    assert t["tools"], "ningún tool quedó registrado"
    for x in t["tools"]:
        assert set(x) >= {"tool", "ok", "escribe", "fuente", "ms", "cifras"}
        assert x["ms"] >= 0
    # Un turno de lectura no escribe.
    assert not any(x["escribe"] for x in t["tools"] if x["tool"].startswith("get_"))


# ── La identidad, dentro de la conversación ─────────────────────────────────
def _real(cliente, estrato: str = "elegible") -> dict:
    """Los tres factores reales del cliente de ese estrato, desde la base."""
    from api import main as mod

    cid = mod._cliente_del_estrato(estrato)
    assert cid, "falta api/static/demo_clientes.json"
    fila = mod.ESTADO.analitica.una(
        "SELECT document_type, document_number, date_of_birth "
        "FROM noema_silver.stg_customers WHERE customer_id = ?",
        (cid,),
    )
    return {k: str(v)[:10] if k == "date_of_birth" else str(v) for k, v in fila.items()}


def test_el_agente_pide_los_tres_factores_antes_de_nada(cliente):
    r = _turno_libre(cliente, "ident-1", "Hola, quiero consultar un préstamo.")
    assert r["desenlace"] == "bloqueado"
    assert set(r["pregunta_por"]) == {"document_type", "document_number", "date_of_birth"}
    # Pedir no es filtrar: el turno no consultó nada del cliente.
    assert r["tools"] == []
    assert r["ofertas"] == []


def test_si_el_cliente_da_un_factor_el_agente_pide_los_que_faltan(cliente):
    _turno_libre(cliente, "ident-2", "Hola.")
    r = _turno_libre(cliente, "ident-2", "Mi DNI, ¿te sirve?")
    assert r["desenlace"] == "bloqueado"
    assert "document_type" not in r["pregunta_por"], "ya dio el tipo, no se vuelve a pedir"
    assert {"document_number", "date_of_birth"} <= set(r["pregunta_por"])


def test_con_los_tres_factores_correctos_se_emite_la_sesion(cliente):
    f = _real(cliente)
    r = _turno_libre(
        cliente,
        "ident-3",
        f"Mi {f['document_type']} es {f['document_number']} y nací el {f['date_of_birth']}.",
    )
    assert r["desenlace"] == "verificado"
    assert r["token"], "sin token no hay sesión"
    # Y con esa sesión el sistema ya responde de verdad.
    t = _turno(cliente, r["token"], "ident-3", "Quisiera un préstamo personal de 3000 dólares.")
    assert t["desenlace"] in {"respuesta", "escalado"}


def test_unos_factores_que_no_cuadran_no_abren_la_sesion(cliente):
    r = _turno_libre(cliente, "ident-4", "Mi DNI es 00000001 y nací el 1900-01-01.")
    assert r["desenlace"] == "bloqueado"
    assert not r.get("token")
    # Y no dice si el documento existe o no: eso sería un oráculo de enumeración.
    assert "no existe" not in (r["mensaje"] or "").lower()


def test_la_fecha_se_entiende_escrita_a_la_latinoamericana(cliente):
    from api.identidad import leer

    assert leer("nací el 11/09/1989")["date_of_birth"] == "1989-09-11"
    assert leer("nací el 1989-09-11")["date_of_birth"] == "1989-09-11"
    # El número de documento no se confunde con los dígitos de la fecha.
    leido = leer("Mi DNI es 98856271 y nací el 11/09/1989")
    assert leido["document_number"] == "98856271"
    assert leido["date_of_birth"] == "1989-09-11"


def test_las_conversaciones_guiadas_empiezan_por_la_identidad(cliente):
    d = cliente.get("/conversations").json()
    for c in d["conversaciones"]:
        assert c["identidad_incluida"] is True
        assert len(c["mensajes"]) >= 5, "saludo + identidad + los tres del guion"


# ── El flujo de eventos, que es lo que el panel muestra ─────────────────────
def test_el_turno_publica_su_secuencia_con_origen_y_control(cliente):
    token, cid = _sesion(cliente, "rechazo_con_motivo")
    t = _turno(cliente, token, cid, "Necesito un préstamo personal de 15000 dólares.")
    eventos = t["eventos"]
    assert len(eventos) >= 10, "un turno completo no cabe en menos de diez eventos"
    for e in eventos:
        assert set(e) >= {"fase", "titulo", "detalle", "fuente", "control", "estado"}
        assert e["estado"] in {"ok", "no", "pe"}
        assert e["titulo"], "un evento sin título no se puede leer"

    fases = [e["fase"] for e in eventos]
    # El orden es el real: primero entra el mensaje, al final se decide.
    assert fases.index("entrada") < fases.index("consulta")
    assert fases.index("consulta") < fases.index("politica")
    assert fases[-1] == "desenlace"


def test_cada_consulta_dice_de_que_tabla_salio(cliente):
    token, cid = _sesion(cliente, "elegible")
    t = _turno(cliente, token, cid, "Quisiera un préstamo personal de 3000 dólares.")
    consultas = [e for e in t["eventos"] if e["fase"] == "consulta"]
    assert consultas, "ninguna consulta quedó registrada"
    for e in consultas:
        assert e["fuente"], f"{e['titulo']} no dice de dónde salió el dato"
        assert e["ms"] is not None
    origenes = {e["fuente"] for e in consultas}
    assert any("stg_customers" in o for o in origenes)
    assert any("stg_products" in o for o in origenes)


def test_las_reglas_de_la_politica_se_publican_una_por_una(cliente):
    token, cid = _sesion(cliente, "rechazo_con_motivo")
    t = _turno(cliente, token, cid, "Necesito un préstamo personal de 15000 dólares.")
    reglas = [e for e in t["eventos"] if e["fase"] == "politica" and "_" in e["fuente"]]
    ids = " ".join(e["fuente"] for e in reglas)
    assert "R1_antiguedad" in ids
    assert "eligibility_v1.yaml v3" in ids
    # Y se ve cuál cortó: en este perfil, la exposición sobre el ingreso.
    fallidas = [e for e in reglas if e["estado"] == "no"]
    assert fallidas, "si el cliente fue rechazado, alguna regla tuvo que fallar"


def test_el_turno_bloqueado_por_identidad_no_consulta_nada(cliente):
    r = _turno_libre(cliente, "ev-bloq", "Hola, quiero saber mi cupo.")
    fases = {e["fase"] for e in r["eventos"]}
    assert "consulta" not in fases, "sin identidad no se consulta la base"
    assert "politica" not in fases


def test_el_panel_dice_que_cabe_lo_mismo_que_dice_el_chat(cliente):
    """Regresión: el panel marcaba «no cabe» a productos que el chat sí ofrecía.

    La aceptación se lee de `opciones` del motor; cualquier cambio que la lea de otra
    clave vuelve a contradecir al chat. Esta prueba compara los dos.
    """
    token, cid = _sesion(cliente, "elegible")
    t = _turno(cliente, token, cid, "¿Y si pidiera un préstamo personal de 40000 dólares?")
    ofrecidos = {o["producto"] for o in t["ofertas"]}
    cabe = {
        e["titulo"].split(":")[0]
        for e in t["eventos"]
        if e["fase"] == "politica" and e["titulo"].endswith(": cabe")
    }
    assert ofrecidos, "el turno debía ofrecer algo para que la prueba signifique algo"
    assert ofrecidos <= cabe, f"el chat ofrece {ofrecidos} y el panel solo dice que cabe {cabe}"
