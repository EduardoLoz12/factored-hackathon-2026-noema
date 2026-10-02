"""GroundingChecker: ninguna cifra sale del modelo — AG-09.

Es la regla 1 del proyecto hecha máquina, y el guardrail central: sin él «el modelo no
inventa cifras» es una promesa en vez de una propiedad verificable.

Lo que estas pruebas tienen que dejar clavado:

1. **Se comparan renderizados, no flotantes.** `dti_actual = 3.375` se escribe «338%».
   Buscar el flotante no encuentra nada, y un checker que no lo entiende bloquea
   respuestas correctas — que es la forma en que un guardrail termina apagado.
2. **Se admiten las dos ambigüedades** —la escala del porcentaje y la convención del
   separador de miles— porque un falso positivo cuesta más que un falso negativo acá:
   bloquea una respuesta correcta y erosiona la confianza en el control.
3. **Una cifra inventada se bloquea**, aunque sea plausible.
4. **Dos intentos y se escala.** Insistir con un modelo que ya inventó dos veces gasta
   dinero y no mejora la respuesta.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from agent.guardrails.grounding import (
    TOLERADOS,
    GroundingChecker,
    renderizados,
)
from agent.policies.engine import Cliente, Politica, ProductoVigente


@pytest.fixture
def ck():
    return GroundingChecker()


# ═════════════════════════════════════════════════════════════════════════════
# 1 · Renderizados: el corazón del asunto
# ═════════════════════════════════════════════════════════════════════════════


def test_un_dti_se_reconoce_como_porcentaje():
    """3.375 se escribe «338%». Es el caso que F-037 dejó anotado."""
    assert "338" in renderizados(3.375)


def test_un_tope_se_reconoce_como_porcentaje():
    assert "60" in renderizados(0.6)
    assert "40" in renderizados(0.4)


def test_un_importe_se_reconoce_con_y_sin_separador():
    formas = renderizados(1234.56)
    assert "1,235" in formas
    assert "1235" in formas


def test_un_importe_se_reconoce_con_la_convencion_espanola():
    """`{:,.0f}` produce «1,235», que en es-CO se lee uno coma dos. Si algún día se
    corrige el formato de los mensajes, el guardrail no hay que tocarlo."""
    assert "1.235" in renderizados(1234.56)


def test_un_entero_no_arrastra_decimales():
    assert "48" in renderizados(48.0)


# ═════════════════════════════════════════════════════════════════════════════
# 2 · El caso real del motor
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def decision_real():
    pol = Politica.cargar()
    d = pol.evaluar(
        Cliente(
            customer_id="C",
            ingreso_mensual_usd=1200.0,
            segmento="Premium",
            alta=date(2015, 1, 1),
            capacidad_estimada_usd=1e9,
            productos=(
                ProductoVigente(
                    tipo="Tarjeta Crédito",
                    limite_usd=90000.0,
                    tasa_anual=31.52,
                    apertura=date(2020, 1, 1),
                    ultima_transaccion_real=date(2025, 12, 1),
                    saldo_usd=80000.0,
                ),
            ),
        )
    )
    valores = [
        v for v in d.hechos.values() if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    return d, valores, list(pol.u.values())


def test_el_motivo_que_el_motor_produce_pasa_el_anclaje(ck, decision_real):
    """La prueba cruzada: el texto real contra los hechos reales."""
    d, valores, umbrales = decision_real
    r = ck.revisar(d.motivos[0], valores=valores, textos=[d.hechos["corte"]], umbrales=umbrales)
    assert r.ok is True, f"huérfanas: {[h.texto for h in r.huerfanas]}"
    assert r.cifras_citadas == r.cifras_ancladas


def test_todos_los_avisos_del_motor_pasan_el_anclaje(ck, decision_real):
    d, valores, umbrales = decision_real
    for aviso in d.avisos:
        r = ck.revisar(aviso, valores=valores, textos=[d.hechos["corte"]], umbrales=umbrales)
        assert r.ok is True, f"«{aviso}» → {[h.texto for h in r.huerfanas]}"


def test_el_umbral_de_politica_cuenta_como_anclado(ck, decision_real):
    """Un motivo honesto dice dos cifras: la del cliente y la que debía alcanzar. La
    segunda es política, no cliente, y si no se admite el guardrail bloquea lo correcto."""
    d, valores, _ = decision_real
    sin_umbrales = ck.revisar(d.motivos[0], valores=valores, textos=[d.hechos["corte"]])
    con_umbrales = ck.revisar(
        d.motivos[0], valores=valores, textos=[d.hechos["corte"]], umbrales=[0.6]
    )
    assert con_umbrales.ok is True
    assert sin_umbrales.ok is False


# ═════════════════════════════════════════════════════════════════════════════
# 3 · Cifras inventadas
# ═════════════════════════════════════════════════════════════════════════════


def test_una_cifra_inventada_se_bloquea(ck):
    r = ck.revisar("Podrías pedir hasta 45,000 USD.", valores=[9000.0, 288.0])
    assert r.ok is False
    assert r.motivo == "cifra_sin_anclaje"
    assert [h.texto for h in r.huerfanas] == ["45,000"]


def test_una_cifra_plausible_pero_no_anclada_se_bloquea(ck):
    """No importa que suene razonable: importa que venga de un tool de ese turno."""
    r = ck.revisar("Tu cuota sería de 290 USD.", valores=[288.0])
    assert r.ok is False


def test_un_porcentaje_inventado_se_bloquea(ck):
    r = ck.revisar("Tu DTI es del 55%.", valores=[0.09])
    assert r.ok is False
    assert r.huerfanas[0].es_porcentaje is True


def test_se_nombran_todas_las_huerfanas(ck):
    r = ck.revisar("Entre 1,000 y 7,500 USD a 99 meses.", valores=[288.0])
    assert len({h.texto for h in r.huerfanas}) == 3


def test_la_posicion_de_la_huerfana_se_reporta(ck):
    """Para poder señalarla en el panel sin volver a buscarla."""
    r = ck.revisar("Hasta 45,000 USD.", valores=[9000.0])
    assert r.huerfanas[0].posicion == len("Hasta ")


# ═════════════════════════════════════════════════════════════════════════════
# 4 · Falsos positivos: lo que NO debe bloquear
# ═════════════════════════════════════════════════════════════════════════════


def test_la_fecha_de_corte_no_se_parte_en_tres(ck):
    """Sin tratarla como unidad, «2025-12-31» daría tres huérfanas."""
    r = ck.revisar("Datos al 2025-12-31.", valores=[], textos=["2025-12-31"])
    assert r.ok is True


def test_los_numeros_de_prosa_corriente_no_bloquean(ck):
    """«una de 2 opciones» no es una afirmación sobre el cliente. La lista es corta a
    propósito: cada entrada es un agujero."""
    r = ck.revisar("Tienes 2 opciones.", valores=[])
    assert r.ok is True
    assert TOLERADOS == frozenset({"0", "1", "2"})


def test_el_mismo_importe_escrito_sin_separador_pasa(ck):
    r = ck.revisar("Hasta 9000 USD.", valores=[9000.0])
    assert r.ok is True


def test_el_mismo_importe_con_dos_decimales_pasa(ck):
    r = ck.revisar("Cuota de 288.00 USD.", valores=[288.0])
    assert r.ok is True


def test_el_redondeo_del_formateo_no_bloquea(ck):
    """«338%» viene de 3.375: el redondeo mueve el valor y no puede contar como invento."""
    r = ck.revisar("El 338% de tu ingreso.", valores=[3.375])
    assert r.ok is True


def test_las_dos_lecturas_del_porcentaje_se_admiten(ck):
    """«40%» puede venir de 0.40 o de 40. Admitir solo una produce falsos positivos."""
    assert ck.revisar("El 40%.", valores=[0.40]).ok is True
    assert ck.revisar("El 40%.", valores=[40.0]).ok is True


# ═════════════════════════════════════════════════════════════════════════════
# 5 · Datos personales
# ═════════════════════════════════════════════════════════════════════════════


def test_un_correo_sin_respaldo_se_bloquea(ck):
    r = ck.revisar("Te escribo a juan@banco.com.", valores=[])
    assert r.ok is False
    assert r.motivo == "pii_sin_respaldo"


def test_una_secuencia_larga_de_digitos_se_bloquea(ck):
    """Un documento o una tarjeta que ningún tool devolvió."""
    r = ck.revisar("Tu documento 40123456 figura en el sistema.", valores=[])
    assert r.ok is False
    assert "secuencia_de_digitos_sin_respaldo" in r.pii_detectada


def test_el_hallazgo_de_pii_no_incluye_el_valor(ck):
    """Incluirlo lo escribiría en el log, que es justo lo que se evita."""
    r = ck.revisar("Escribo a secreto@banco.com.", valores=[])
    assert not any("secreto@banco.com" in p for p in r.pii_detectada)


def test_un_importe_largo_pero_anclado_no_es_pii(ck):
    r = ck.revisar("Exposición de 12345678 USD.", valores=[12345678.0])
    assert r.ok is True


# ═════════════════════════════════════════════════════════════════════════════
# 6 · Las métricas
# ═════════════════════════════════════════════════════════════════════════════


def test_la_tasa_se_divide_entre_respuestas_revisadas(ck):
    ck.revisar("Cuota de 288 USD.", valores=[288.0])
    ck.revisar("Hasta 45,000 USD.", valores=[288.0])
    assert ck.revisadas == 2
    assert ck.bloqueadas == 1
    assert ck.tasa_de_bloqueo == pytest.approx(0.5)


def test_sin_revisiones_la_tasa_es_indefinida(ck):
    assert ck.tasa_de_bloqueo is None
    assert ck.metricas()["tasa_de_bloqueo_sobre_revisadas"] is None


def test_las_metricas_desglosan_el_motivo(ck):
    ck.revisar("Hasta 45,000 USD.", valores=[288.0])
    ck.revisar("Escribo a x@y.com.", valores=[])
    m = ck.metricas()
    assert m["motivos"]["cifra_sin_anclaje"] == 1
    assert m["motivos"]["pii_sin_respaldo"] == 1


def test_la_traza_no_repite_las_cifras(ck):
    r = ck.revisar("Cuota de 288 USD.", valores=[288.0])
    traza = r.a_traza()
    assert traza["control"] == "grounding"
    assert "288" not in str(traza)


# ═════════════════════════════════════════════════════════════════════════════
# 7 · Dos intentos y se escala — la regla de §4
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def orq():
    from agent.core.orchestrator import Orquestador
    from agent.tools import cases as ca
    from agent.tools.ledger import abrir_ledger_en_memoria
    from agent.tools.registry import ToolRegistry
    from agent.tools.store import AnalyticsStore, Contexto, Evidencia

    reg = ToolRegistry()
    ca.registrar(reg)
    ctx = Contexto(
        analitica=AnalyticsStore(conexion=duckdb.connect(":memory:")),
        corte=Politica.cargar().corte,
        politica=Politica.cargar(),
        expedientes=abrir_ledger_en_memoria(),
    )
    ctx.evidencia = Evidencia(perfil={}, creditos={"productos": []}, activos={"activos": []})
    return Orquestador(registry=reg, contexto=ctx)


def sesion():
    from agent.tools.registry import Role, Session

    return Session(
        role=Role.CUSTOMER, verified=True, customer_id="C1", jti="j", conversation_id="conv-1"
    )


def turno_base():
    from agent.core.orchestrator import Desenlace, Turno

    return Turno(desenlace=Desenlace.RESPUESTA, cifras_ancladas=(288.0, 9000.0))


def test_si_el_primer_intento_ancla_no_hay_segundo(orq):
    llamadas = []

    def redactar(intento, previo):
        llamadas.append(intento)
        return "Tu cuota sería de 288 USD por 9000 USD."

    t, texto = orq.redactar_y_verificar(turno_base(), sesion(), redactar)
    assert llamadas == [1]
    assert texto is not None
    assert t.mensaje == texto


def test_el_segundo_intento_recibe_el_resultado_del_primero(orq):
    vistos = []

    def redactar(intento, previo):
        vistos.append(previo)
        return "Hasta 45,000 USD." if intento == 1 else "Hasta 9000 USD."

    t, texto = orq.redactar_y_verificar(turno_base(), sesion(), redactar)
    assert vistos[0] is None
    assert vistos[1] is not None and vistos[1].ok is False
    assert texto is not None, "el segundo intento, corregido, pasa"


def test_dos_intentos_fallidos_escalan(orq):
    from agent.core.orchestrator import Desenlace

    t, texto = orq.redactar_y_verificar(
        turno_base(), sesion(), lambda intento, previo: "Hasta 45,000 USD."
    )
    assert texto is None, "no se entrega una respuesta que no se puede respaldar"
    assert t.desenlace is Desenlace.ESCALADO
    assert t.case_id is not None
    assert "asesor" in t.mensaje


def test_no_hay_tercer_intento(orq):
    """Insistir con un modelo que ya inventó dos veces gasta dinero y no mejora nada."""
    llamadas = []

    def redactar(intento, previo):
        llamadas.append(intento)
        return "Hasta 45,000 USD."

    orq.redactar_y_verificar(turno_base(), sesion(), redactar)
    assert llamadas == [1, 2]


def test_cada_intento_queda_en_la_traza(orq):
    t, _ = orq.redactar_y_verificar(turno_base(), sesion(), lambda i, p: "Hasta 45,000 USD.")
    razones = [x.razon for x in t.etapas if "anclaje de la respuesta" in x.razon]
    assert len(razones) == 2
    assert "intento 1" in razones[0] and "intento 2" in razones[1]
