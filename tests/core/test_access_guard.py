"""La puerta de identidad — AG-05.

Lo que estas pruebas tienen que dejar clavado, porque es contrato de seguridad y no
preferencia de diseño (`docs/05_security.md` §2):

1. **Tres intentos y bloqueo**, con espera creciente, contados **en la base** y no en
   memoria del proceso: un contador en memoria se reinicia con cada worker y entonces
   el límite no existe.
2. **Mensaje idéntico en todo fallo de credenciales.** Distinguir «ese documento no
   existe» de «la fecha no coincide» permite enumerar documentos probando.
3. **El `customer_id` viaja dentro del token**, nunca como parámetro (F-007).
4. **Sin llave de firma no se emite sesión.** Firmar con una por defecto sería peor que
   no firmar: el sistema parecería autenticar.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import duckdb
import jwt
import pytest

from agent.core.access_guard import (
    MENSAJE_FALLO,
    AccessGuard,
    SinLlaveDeFirma,
)
from agent.tools import customer as cmod
from agent.tools.registry import Role, ToolRegistry
from agent.tools.store import AnalyticsStore, Contexto

CORTE = date(2025, 12, 31)
LLAVE = "x" * 48
BUENOS = {
    "document_type": "DNI",
    "document_number": "11111111",
    "date_of_birth": "1980-05-10",
}


@pytest.fixture(autouse=True)
def llave(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", LLAVE)


@pytest.fixture
def guard():
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA noema_silver")
    con.execute("""
        CREATE TABLE noema_silver.stg_customers (
            customer_id VARCHAR, document_number VARCHAR, document_type VARCHAR,
            date_of_birth VARCHAR, country VARCHAR, segment VARCHAR,
            estimated_monthly_income DOUBLE, registration_date DATE
        )""")
    con.execute("""
        INSERT INTO noema_silver.stg_customers VALUES
          ('CLI-1','11111111','DNI','1980-05-10','Colombia','Plus', 9000000.0, DATE '2020-01-15')
    """)
    registry = ToolRegistry()
    cmod.registrar(registry)
    g = AccessGuard(
        registry=registry,
        conexion=con,
        contexto=Contexto(analitica=AnalyticsStore(conexion=con), corte=CORTE),
    )
    g.crear_esquema()
    return g


def fallos(guard, conversation_id, veces, **kw):
    malos = {**BUENOS, "date_of_birth": "1900-01-01", **kw}
    salidas = []
    for _ in range(veces):
        salidas.append(guard.verificar(conversation_id, **malos))
    return salidas


# ═════════════════════════════════════════════════════════════════════════════
# El camino correcto
# ═════════════════════════════════════════════════════════════════════════════


def test_los_tres_factores_correctos_emiten_sesion(guard):
    r = guard.verificar("conv-1", **BUENOS)
    assert r.verificado is True
    assert r.token
    assert r.bloqueado is False


def test_el_customer_id_viaja_dentro_del_token(guard):
    """El cliente nunca lo envía: si pudiera, podría pedir los datos de otro (F-007)."""
    r = guard.verificar("conv-1", **BUENOS)
    datos = jwt.decode(r.token, LLAVE, algorithms=["HS256"])
    assert datos["sub"] == "CLI-1"
    assert datos["rol"] == Role.CUSTOMER.value
    assert datos["cid"] == "conv-1"


def test_la_sesion_dura_quince_minutos(guard):
    r = guard.verificar("conv-1", **BUENOS)
    datos = jwt.decode(r.token, LLAVE, algorithms=["HS256"])
    assert 14 * 60 <= datos["exp"] - datos["iat"] <= 15 * 60


def test_el_token_se_convierte_en_una_sesion_usable(guard):
    r = guard.verificar("conv-1", **BUENOS)
    ses = guard.sesion_desde_token(r.token)
    assert ses is not None
    assert ses.verified is True
    assert ses.customer_id == "CLI-1"
    assert ses.role is Role.CUSTOMER
    assert ses.vigente() is True


# ═════════════════════════════════════════════════════════════════════════════
# Los tres intentos y el bloqueo
# ═════════════════════════════════════════════════════════════════════════════


def test_el_tercer_fallo_bloquea(guard):
    uno, dos, tres = fallos(guard, "conv-1", 3)
    assert uno.intentos_restantes == 2
    assert dos.intentos_restantes == 1
    assert tres.bloqueado is True
    assert tres.espera_segundos > 0


def test_bloqueado_no_se_evalua_aunque_los_datos_sean_correctos(guard):
    fallos(guard, "conv-1", 3)
    r = guard.verificar("conv-1", **BUENOS)
    assert r.verificado is False
    assert r.bloqueado is True
    assert r.token is None


def test_el_bloqueo_es_por_conversacion(guard):
    """Bloquear a todo el mundo porque uno falló sería una negación de servicio."""
    fallos(guard, "conv-1", 3)
    assert guard.verificar("conv-2", **BUENOS).verificado is True


def test_la_espera_se_duplica_con_cada_fallo_extra(guard):
    """Un intento bloqueado no se registra, así que tras el límite solo se suma un
    fallo por bloqueo cumplido. La espera tiene que crecer con ese fallo, no cada
    tres: si no, el backoff es casi lineal."""
    fallos(guard, "conv-1", 3)
    primera = guard.verificar("conv-1", **BUENOS).espera_segundos

    def vencer_el_bloqueo():
        guard.conexion.execute(
            "UPDATE identity_attempts SET intentado_en = ? WHERE conversation_id = 'conv-1'",
            [datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(seconds=900)],
        )

    vencer_el_bloqueo()
    fallos(guard, "conv-1", 1)  # cuarto fallo registrado
    segunda = guard.verificar("conv-1", **BUENOS).espera_segundos
    vencer_el_bloqueo()
    fallos(guard, "conv-1", 1)  # quinto
    tercera = guard.verificar("conv-1", **BUENOS).espera_segundos

    assert primera < segunda < tercera
    assert segunda >= 2 * primera - 2  # tolerancia por el segundo que transcurre


def test_el_tope_del_bloqueo_no_supera_la_ventana_de_intentos(guard):
    """Si el bloqueo durara más que la ventana, los fallos envejecerían y el contador
    volvería a cero mientras el cliente espera: la progresión se detendría sola y la
    espera declarada sería una que el sistema no aplica."""
    from agent.core.access_guard import (
        SEGUNDOS_TOPE_BLOQUEO,
        VENTANA_INTENTOS_MINUTOS,
    )

    assert SEGUNDOS_TOPE_BLOQUEO <= VENTANA_INTENTOS_MINUTOS * 60
    ahora = datetime.now(tz=UTC).replace(tzinfo=None)
    assert guard._espera(40, ahora) <= SEGUNDOS_TOPE_BLOQUEO


def test_los_intentos_se_cuentan_en_la_base_no_en_memoria(guard):
    """Un contador en memoria se reinicia con cada worker y el límite desaparece."""
    fallos(guard, "conv-1", 2)
    otro_worker = AccessGuard(
        registry=guard.registry, conexion=guard.conexion, contexto=guard.contexto
    )
    r = otro_worker.verificar("conv-1", **{**BUENOS, "date_of_birth": "1900-01-01"})
    assert r.bloqueado is True, "el tercer intento desde otro worker debe bloquear"


def test_un_parametro_mal_formado_gasta_intento(guard):
    """Si no lo gastara, se podría sondear indefinidamente sin consumir intentos."""
    for _ in range(3):
        guard.verificar("conv-1", document_type="RUT", document_number="x", date_of_birth="mal")
    assert guard.verificar("conv-1", **BUENOS).bloqueado is True


def test_un_exito_no_se_cuenta_como_fallo(guard):
    guard.verificar("conv-1", **BUENOS)
    guard.verificar("conv-1", **BUENOS)
    guard.verificar("conv-1", **BUENOS)
    assert guard.verificar("conv-1", **BUENOS).verificado is True


# ═════════════════════════════════════════════════════════════════════════════
# Mensajes idénticos
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "params",
    [
        {"document_type": "CE"},
        {"date_of_birth": "1999-01-01"},
        {"document_number": "99999999"},
    ],
    ids=["tipo_erroneo", "nacimiento_erroneo", "documento_inexistente"],
)
def test_todo_fallo_de_credenciales_dice_lo_mismo(guard, params):
    """Distinguirlos permitiría averiguar qué documentos existen probando."""
    r = guard.verificar("conv-1", **{**BUENOS, **params})
    assert r.verificado is False
    assert r.mensaje == MENSAJE_FALLO


def test_el_mensaje_de_fallo_no_nombra_el_factor_que_falló():
    for palabra in ("documento no existe", "fecha incorrecta", "no encontrado"):
        assert palabra not in MENSAJE_FALLO.lower()


def test_el_bloqueo_si_se_declara(guard):
    """Decirlo no revela nada sobre documentos: solo sobre los intentos propios."""
    fallos(guard, "conv-1", 3)
    r = guard.verificar("conv-1", **BUENOS)
    assert "seguridad" in r.mensaje.lower()
    assert r.mensaje != MENSAJE_FALLO


# ═════════════════════════════════════════════════════════════════════════════
# La llave de firma
# ═════════════════════════════════════════════════════════════════════════════


def test_sin_llave_no_se_emite_sesion(guard, monkeypatch):
    """Falla cerrado. Firmar con una llave por defecto haría que el sistema
    pareciera autenticar."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(SinLlaveDeFirma):
        guard.verificar("conv-1", **BUENOS)


def test_una_llave_corta_se_rechaza(guard, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "corta")
    with pytest.raises(SinLlaveDeFirma):
        guard.verificar("conv-1", **BUENOS)


def test_un_token_firmado_con_otra_llave_no_vale(guard):
    ajeno = jwt.encode(
        {
            "jti": "x",
            "sub": "CLI-1",
            "cid": "conv-1",
            "rol": "customer",
            "exp": int(
                (datetime.now(tz=UTC).replace(tzinfo=None) + timedelta(minutes=5)).timestamp()
            ),
        },
        "y" * 48,
        algorithm="HS256",
    )
    assert guard.sesion_desde_token(ajeno) is None


def test_un_token_sin_fila_en_la_tabla_no_vale(guard):
    """Firma válida pero sin estado: es de otro despliegue. Falla cerrado."""
    huerfano = jwt.encode(
        {
            "jti": "no-existe",
            "sub": "CLI-1",
            "cid": "conv-1",
            "rol": "customer",
            "exp": int(
                (datetime.now(tz=UTC).replace(tzinfo=None) + timedelta(minutes=5)).timestamp()
            ),
        },
        LLAVE,
        algorithm="HS256",
    )
    assert guard.sesion_desde_token(huerfano) is None


def test_un_token_expirado_no_vale(guard):
    r = guard.verificar("conv-1", **BUENOS)
    guard.conexion.execute(
        "UPDATE sessions SET expira_en = ? ",
        [datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(minutes=1)],
    )
    assert guard.sesion_desde_token(r.token) is None


def test_un_token_que_no_cuadra_con_su_fila_no_vale(guard):
    """Si la fila y el token discrepan, no se confía en ninguno de los dos."""
    r = guard.verificar("conv-1", **BUENOS)
    guard.conexion.execute("UPDATE sessions SET customer_id = 'CLI-OTRO'")
    assert guard.sesion_desde_token(r.token) is None


def test_basura_no_tumba_la_validacion(guard):
    for malo in ("", "no-es-un-token", "a.b.c"):
        assert guard.sesion_desde_token(malo) is None


# ═════════════════════════════════════════════════════════════════════════════
# Lo que la puerta registra
# ═════════════════════════════════════════════════════════════════════════════


def test_la_traza_no_lleva_el_token_ni_pii(guard):
    r = guard.verificar("conv-1", **BUENOS)
    traza = r.a_traza()
    assert traza["etapa"] == "IDENTIFY"
    assert "token" not in traza
    for valor in traza.values():
        assert BUENOS["document_number"] != str(valor)


def test_los_intentos_no_guardan_el_documento(guard):
    """La tabla de intentos no necesita saber qué se intentó: el sujeto es la
    conversación. Guardarlo sería PII sin uso."""
    fallos(guard, "conv-1", 1)
    columnas = [f[0] for f in guard.conexion.execute("DESCRIBE identity_attempts").fetchall()]
    assert set(columnas) == {"attempt_id", "conversation_id", "exito", "intentado_en"}


def test_la_secuencia_de_intentos_queda_auditable(guard):
    fallos(guard, "conv-1", 2)
    guard.verificar("conv-1", **BUENOS)
    filas = guard.conexion.execute(
        "SELECT exito FROM identity_attempts WHERE conversation_id = 'conv-1' ORDER BY intentado_en"
    ).fetchall()
    assert [f[0] for f in filas] == [False, False, True]
