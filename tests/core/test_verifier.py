"""VERIFY: la relectura que confirma que una acción ocurrió — AG-07.

El reto lo pide textual —«verify that actions actually happened»— y el brief anotó que
es barato y casi nadie lo hará. Lo que estas pruebas tienen que dejar clavado:

1. **Falla cerrado.** Una excepción al releer es «no verificado», nunca un éxito.
2. **La comparación tiene un solo criterio**, el mismo para las dos escrituras del
   sistema. Antes vivía duplicada, con un campo en el expediente y cinco en la oferta.
3. **La tasa se divide entre escrituras**, no entre turnos: con el denominador
   equivocado, una tasa de cero es trivial en cuanto el sistema casi nunca escribe.
"""

from __future__ import annotations

import pytest

from agent.core.verifier import (
    CAMPOS_EXPEDIENTE,
    CAMPOS_OFERTA,
    TOLERANCIA_IMPORTE,
    MotivoNoVerificado,
    Verificador,
)

ESPERADO = {"motivo": "abstencion_de_politica", "customer_id": "C1", "conversation_id": "conv-1"}


@pytest.fixture
def v():
    return Verificador()


def verificar(v, leido, esperado=None, campos=CAMPOS_EXPEDIENTE, **kw):
    return v.verificar(
        accion="create_escalation_case",
        referencia="CASE-1",
        esperado=esperado or ESPERADO,
        releer=lambda: leido,
        campos=campos,
        **kw,
    )


# ═════════════════════════════════════════════════════════════════════════════
# El camino correcto
# ═════════════════════════════════════════════════════════════════════════════


def test_lo_releido_igual_verifica(v):
    r = verificar(v, dict(ESPERADO))
    assert r.ok is True
    assert r.motivo is None
    assert r.campos_discrepantes == ()


def test_los_campos_que_no_se_comparan_pueden_diferir(v):
    """La base añade su propio `creado_en` y su id: eso no es discrepancia."""
    r = verificar(v, {**ESPERADO, "creado_en": "2026-10-02", "case_id": "CASE-1"})
    assert r.ok is True


# ═════════════════════════════════════════════════════════════════════════════
# Falla cerrado
# ═════════════════════════════════════════════════════════════════════════════


def test_si_no_hay_fila_no_se_verifica(v):
    r = verificar(v, None)
    assert r.ok is False
    assert r.motivo == MotivoNoVerificado.AUSENTE


def test_si_la_relectura_lanza_no_se_verifica(v):
    """Una excepción no es un éxito. Es el caso que una verificación ingenua aprueba."""

    def explota():
        raise RuntimeError("la base no responde")

    r = v.verificar(
        accion="create_escalation_case",
        referencia="CASE-1",
        esperado=ESPERADO,
        releer=explota,
        campos=CAMPOS_EXPEDIENTE,
    )
    assert r.ok is False
    assert r.motivo == MotivoNoVerificado.ERROR_DE_LECTURA


def test_verificar_sin_campos_es_un_error_de_programacion(v):
    """Comparar cero campos pasaría siempre: no verificaría nada."""
    with pytest.raises(ValueError, match="no verifica nada"):
        v.verificar(accion="x", referencia="r", esperado={}, releer=lambda: {}, campos=())


# ═════════════════════════════════════════════════════════════════════════════
# La comparación
# ═════════════════════════════════════════════════════════════════════════════


def test_un_campo_distinto_se_nombra(v):
    r = verificar(v, {**ESPERADO, "motivo": "peticion_del_cliente"})
    assert r.ok is False
    assert r.motivo == MotivoNoVerificado.DISCREPANCIA
    assert r.campos_discrepantes == ("motivo",)


def test_se_nombran_todos_los_campos_que_discrepan(v):
    r = verificar(v, {"motivo": "otro", "customer_id": "C-OTRO", "conversation_id": "conv-1"})
    assert set(r.campos_discrepantes) == {"motivo", "customer_id"}


def test_un_campo_ausente_en_lo_releido_es_discrepancia(v):
    r = verificar(v, {"customer_id": "C1", "conversation_id": "conv-1"})
    assert r.ok is False
    assert "motivo" in r.campos_discrepantes


def test_el_expediente_compara_cliente_y_conversacion(v):
    """Antes solo comparaba el motivo. Una fila del cliente equivocado pasaba."""
    assert "customer_id" in CAMPOS_EXPEDIENTE
    assert "conversation_id" in CAMPOS_EXPEDIENTE
    r = verificar(v, {**ESPERADO, "customer_id": "C-AJENO"})
    assert r.ok is False


# ═════════════════════════════════════════════════════════════════════════════
# Importes: tolerancia al redondeo, no a la diferencia
# ═════════════════════════════════════════════════════════════════════════════


def test_un_centavo_de_redondeo_no_rompe_la_verificacion(v):
    esperado = {"cuota_estimada_usd": 274.35}
    r = verificar(v, {"cuota_estimada_usd": 274.355}, esperado, ("cuota_estimada_usd",))
    assert r.ok is True


def test_una_diferencia_real_de_importe_no_pasa(v):
    esperado = {"cuota_estimada_usd": 274.35}
    r = verificar(v, {"cuota_estimada_usd": 999.0}, esperado, ("cuota_estimada_usd",))
    assert r.ok is False


def test_la_tolerancia_es_de_un_centavo(v):
    assert TOLERANCIA_IMPORTE == 0.01


def test_un_booleano_no_cuela_como_numero(v):
    """`True == 1` en Python. Un booleano donde se esperaba un importe es discrepancia."""
    r = verificar(
        v, {"monto_ofrecido_usd": True}, {"monto_ofrecido_usd": 1.0}, ("monto_ofrecido_usd",)
    )
    assert r.ok is False


def test_un_texto_que_parece_numero_no_cuela(v):
    r = verificar(v, {"plazo_meses": "48"}, {"plazo_meses": 48}, ("plazo_meses",))
    assert r.ok is False


# ═════════════════════════════════════════════════════════════════════════════
# Lo anidado: el payload del ledger
# ═════════════════════════════════════════════════════════════════════════════


def test_se_compara_dentro_del_payload(v):
    oferta = {
        "producto": "Préstamo Personal",
        "plazo_meses": 48,
        "monto_ofrecido_usd": 9000.0,
        "cuota_estimada_usd": 274.35,
        "tasa_anual": 20.10,
        "tea_pct": 22.06,
    }
    r = v.verificar(
        accion="record_offer_quote",
        referencia="ACT-1",
        esperado=oferta,
        releer=lambda: {"action_id": "ACT-1", "payload": dict(oferta)},
        campos=CAMPOS_OFERTA,
        extraer=lambda fila: fila.get("payload") or {},
    )
    assert r.ok is True
    assert r.releido["producto"] == "Préstamo Personal"


def test_un_payload_vacio_discrepa_en_todo(v):
    r = v.verificar(
        accion="record_offer_quote",
        referencia="ACT-1",
        esperado={"producto": "X", "plazo_meses": 48},
        releer=lambda: {"payload": {}},
        campos=("producto", "plazo_meses"),
        extraer=lambda fila: fila.get("payload") or {},
    )
    assert r.ok is False
    assert set(r.campos_discrepantes) == {"producto", "plazo_meses"}


def test_la_oferta_compara_el_plazo_y_la_tea(v):
    """Dos plazos del mismo producto son dos cotizaciones: el plazo tiene que entrar."""
    assert "plazo_meses" in CAMPOS_OFERTA
    assert "tea_pct" in CAMPOS_OFERTA


# ═════════════════════════════════════════════════════════════════════════════
# Las métricas de EV-06
# ═════════════════════════════════════════════════════════════════════════════


def test_la_tasa_se_divide_entre_escrituras(v):
    """Con turnos totales en el denominador, cero sería trivial si casi no se escribe."""
    verificar(v, dict(ESPERADO))
    verificar(v, dict(ESPERADO))
    verificar(v, None)
    assert v.escrituras == 3
    assert v.verificadas == 2
    assert v.fallidas == 1
    assert v.tasa_de_fallo == pytest.approx(1 / 3)


def test_sin_escrituras_la_tasa_no_es_cero_sino_indefinida(v):
    """Cero fallos de cero escrituras no es un sistema fiable: es un sistema inactivo."""
    assert v.tasa_de_fallo is None
    assert v.metricas()["tasa_de_fallo_sobre_escrituras"] is None


def test_las_metricas_desglosan_el_motivo(v):
    verificar(v, None)
    verificar(v, {**ESPERADO, "motivo": "otro"})
    m = v.metricas()
    assert m["motivos"][MotivoNoVerificado.AUSENTE] == 1
    assert m["motivos"][MotivoNoVerificado.DISCREPANCIA] == 1


def test_el_historial_guarda_cada_verificacion(v):
    verificar(v, dict(ESPERADO))
    verificar(v, None)
    assert [x.ok for x in v.historial] == [True, False]


# ═════════════════════════════════════════════════════════════════════════════
# La traza
# ═════════════════════════════════════════════════════════════════════════════


def test_la_traza_no_lleva_lo_releido(v):
    """Lo releído puede traer cifras del cliente; la traza no las necesita."""
    r = verificar(v, dict(ESPERADO))
    traza = r.a_traza()
    assert traza["etapa"] == "VERIFY"
    assert traza["verificado"] is True
    assert "releido" not in traza
    assert ESPERADO["customer_id"] not in str(traza.values())


def test_la_traza_nombra_los_campos_que_fallaron(v):
    r = verificar(v, {**ESPERADO, "motivo": "otro"})
    assert r.a_traza()["campos_discrepantes"] == ["motivo"]


# ═════════════════════════════════════════════════════════════════════════════
# Los tools usan ESTE verificador, no su propia comparación
# ═════════════════════════════════════════════════════════════════════════════


def test_los_dos_tools_de_escritura_delegan_aqui():
    """Dos implementaciones de la misma garantía se desincronizan, y la que se queda
    atrás no avisa: simplemente deja de verificar."""
    for ruta in ("agent/tools/cases.py", "agent/tools/credit.py"):
        texto = open(ruta, encoding="utf-8").read()
        assert "VERIFICADOR.verificar(" in texto, ruta
