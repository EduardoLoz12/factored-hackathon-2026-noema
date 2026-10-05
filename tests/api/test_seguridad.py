"""Lo que protege la API — `API-02`.

Cada prueba rompe algo a propósito: si la redacción, el límite o el CORS dejaran de
hacer su trabajo, acá se ve.
"""

from __future__ import annotations

from api.seguridad import Limitador, origenes_permitidos, redactar


# ── redacción de PII ────────────────────────────────────────────────────────
def test_el_documento_no_sobrevive_al_log():
    assert "12345678" not in redactar("documento 12345678 verificado")


def test_el_identificador_interno_del_cliente_tampoco():
    """Identifica a una persona aunque no la nombre."""
    assert "CLI-3J8RBP9XLCRT" not in redactar("turno de CLI-3J8RBP9XLCRT")


def test_correo_telefono_y_fecha_de_nacimiento_se_redactan():
    salida = redactar("ana@banco.com, +57 300 1234567, nació el 1980-05-10")
    for crudo in ("ana@banco.com", "1980-05-10"):
        assert crudo not in salida
    assert "[correo]" in salida and "[fecha]" in salida


def test_lo_que_no_es_pii_se_conserva():
    """Redactar de más deja un log inútil."""
    assert "escalado" in redactar("turno escalado por peticion_del_cliente")


# ── límite de tasa ──────────────────────────────────────────────────────────
def test_el_limite_corta_al_pasarse_y_dice_cuanto_esperar():
    lim = Limitador(maximo=3, ventana_segundos=60)
    for _ in range(3):
        ok, _ = lim.permite("ip-1")
        assert ok
    ok, espera = lim.permite("ip-1")
    assert not ok
    assert espera >= 1, "cortar sin decir cuándo reintentar deja al cliente a ciegas"


def test_el_limite_es_por_clave_y_no_castiga_a_los_demas():
    lim = Limitador(maximo=1, ventana_segundos=60)
    assert lim.permite("ip-1")[0]
    assert not lim.permite("ip-1")[0]
    assert lim.permite("ip-2")[0], "el límite de uno no puede bloquear a otro"


def test_la_ventana_se_reabre():
    lim = Limitador(maximo=1, ventana_segundos=0.01)
    assert lim.permite("ip-1")[0]
    import time

    time.sleep(0.03)
    assert lim.permite("ip-1")[0]


# ── CORS ────────────────────────────────────────────────────────────────────
def test_cors_cerrado_por_defecto(monkeypatch):
    monkeypatch.delenv("NOEMA_ORIGINS", raising=False)
    origenes = origenes_permitidos()
    assert "*" not in origenes
    assert all(o.startswith("http://localhost") or o.startswith("http://127.") for o in origenes)


def test_cors_se_abre_solo_si_alguien_lo_pide(monkeypatch):
    monkeypatch.setenv("NOEMA_ORIGINS", "https://noema.example, https://otro.example")
    assert origenes_permitidos() == ["https://noema.example", "https://otro.example"]
