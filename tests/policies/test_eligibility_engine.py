"""Pruebas del motor de elegibilidad — AG-02.

La política se testea SIN LLM y SIN modelo. Es la garantía de que la decisión es
reproducible: los mismos hechos dan siempre la misma respuesta, y cada umbral
que cambie en el YAML se ve aquí.
"""

from __future__ import annotations

from datetime import date

import pytest

from agent.policies.engine import (
    Cliente,
    Politica,
    ProductoDeAhorro,
    ProductoVigente,
    cuota_francesa,
    principal_maximo,
)

CORTE = date(2025, 12, 31)


@pytest.fixture(scope="module")
def politica() -> Politica:
    return Politica.cargar()


# ─────────────────────────────────────────────────────────────────────────────
# Aritmética financiera: se verifica contra valores conocidos
# ─────────────────────────────────────────────────────────────────────────────
class TestAritmetica:
    def test_cuota_conocida(self):
        """100 000 al 12 % anual a 120 meses da 1 434.71 (tabla estándar)."""
        assert cuota_francesa(100_000, 12.0, 120) == pytest.approx(1434.71, abs=0.01)

    def test_cuota_sin_interes_es_division_simple(self):
        assert cuota_francesa(12_000, 0.0, 12) == pytest.approx(1000.0)

    def test_cuota_crece_con_la_tasa(self):
        assert cuota_francesa(50_000, 20.0, 48) > cuota_francesa(50_000, 10.0, 48)

    def test_cuota_baja_al_alargar_el_plazo(self):
        assert cuota_francesa(50_000, 15.0, 240) < cuota_francesa(50_000, 15.0, 48)

    def test_principal_maximo_es_la_inversa_de_la_cuota(self):
        p = principal_maximo(1000.0, 18.0, 60)
        assert cuota_francesa(p, 18.0, 60) == pytest.approx(1000.0, abs=0.01)

    def test_margen_nulo_no_da_principal(self):
        assert principal_maximo(0.0, 18.0, 60) == 0.0

    @pytest.mark.parametrize("principal, meses", [(0, 12), (-100, 12), (1000, 0)])
    def test_insumos_invalidos_lanzan(self, principal, meses):
        with pytest.raises(ValueError):
            cuota_francesa(principal, 12.0, meses)


# ─────────────────────────────────────────────────────────────────────────────
# La política carga y está versionada
# ─────────────────────────────────────────────────────────────────────────────
class TestCarga:
    def test_version_y_corte(self, politica):
        assert politica.version >= 1
        assert politica.corte == CORTE

    def test_catalogo_completo(self, politica):
        for item in politica.catalogo:
            assert item["monto_minimo_usd"] < item["monto_maximo_usd"]
            assert item["tasa_anual"] > 0
            plazos = item["plazos_ofertables"]
            assert plazos, f"{item['producto']} sin plazos ofertables"
            assert all(isinstance(x, int) and x > 0 for x in plazos)
            assert plazos == sorted(set(plazos)), "plazos ordenados y sin repetir"
            # Un producto revolvente lleva un solo plazo: su cuota es el pago
            # mínimo sobre el saldo, así que el plazo no la cambia.
            if item.get("amortizacion") == "revolvente":
                assert len(plazos) == 1, f"{item['producto']} revolvente con varios plazos"
            assert item["segmentos"]
            assert item["amortizacion"] in {"revolvente", "cuota_fija"}

    def test_las_tasas_ordenan_como_en_banca(self, politica):
        """Tarjeta más cara que préstamo personal, y este que hipotecario."""
        t = {i["producto"]: i["tasa_anual"] for i in politica.catalogo}
        assert t["Tarjeta Crédito"] > t["Préstamo Personal"] > t["Préstamo Hipotecario"]

    def test_corte_duro_sobre_el_tope_normal(self, politica):
        assert politica.u["dti_corte_duro"] > politica.u["dti_maximo"]


# ─────────────────────────────────────────────────────────────────────────────
# Abstención: nunca se inventa un dato
# ─────────────────────────────────────────────────────────────────────────────
class TestAbstencion:
    @pytest.mark.parametrize("ingreso", [None, 0, -50])
    def test_sin_ingreso_se_abstiene(self, politica, ingreso):
        d = politica.evaluar(Cliente("C1", ingreso, "Plus", date(2020, 1, 1)))
        assert d.abstencion is True
        assert d.elegible is False
        assert not d.productos_elegibles
        assert d.motivos

    def test_la_abstencion_no_es_una_denegacion(self, politica):
        """Son resultados distintos y se miden aparte."""
        abst = politica.evaluar(Cliente("C1", None, "Plus", date(2020, 1, 1)))
        deneg = politica.evaluar(
            Cliente(
                "C2",
                500,
                "Plus",
                date(2020, 1, 1),
                (
                    ProductoVigente(
                        "Préstamo Hipotecario", 200_000, 8.98, date(2020, 1, 1), None, CORTE
                    ),
                ),
            )
        )
        assert abst.abstencion and not deneg.abstencion
        assert not abst.elegible and not deneg.elegible

    def test_declara_siempre_que_no_evalua_mora(self, politica):
        for c in [
            Cliente("C1", None, "Plus", date(2020, 1, 1)),
            Cliente("C2", 5000, "Plus", date(2020, 1, 1)),
        ]:
            d = politica.evaluar(c)
            assert any("mora" in a.lower() for a in d.avisos)

    def test_un_producto_sin_limite_abstiene_en_vez_de_aprobar(self, politica):
        """Antes esta prueba afirmaba que la evaluación *seguía*. Eso era el bug.

        Un producto sin límite no se puede valorar, así que su obligación no entra
        en el DTI. Seguir evaluando significaba aprobar a un cliente cuya deuda
        sabemos incompleta: falla abierto, contra la regla 5. El YAML ya declaraba
        `sin_exposicion_valorable` como abstención bloqueante; el motor no la
        implementaba. Afectaba al 19.59 % de los clientes con crédito (F-041).
        """
        d = politica.evaluar(
            Cliente(
                "C1",
                5000,
                "Plus",
                date(2019, 1, 1),
                (ProductoVigente("Tarjeta Crédito", None, 31.52, date(2021, 1, 1), None, CORTE),),
            )
        )
        assert d.abstencion is True
        assert d.elegible is False
        assert not d.productos_elegibles
        assert any("Falta el límite" in a for a in d.avisos)
        assert any("falta información de uno" in m for m in d.motivos)
        assert d.hechos["productos_no_valorables"] == 1

    def test_un_producto_sin_tasa_tambien_abstiene(self, politica):
        """Sin tasa no hay cuota, así que tampoco hay DTI. Mismo trato."""
        d = politica.evaluar(
            Cliente(
                "C1",
                5000,
                "Plus",
                date(2019, 1, 1),
                (
                    ProductoVigente(
                        "Préstamo Personal", 10000.0, None, date(2021, 1, 1), None, CORTE
                    ),
                ),
            )
        )
        assert d.abstencion is True
        assert any("Falta la tasa" in a for a in d.avisos)

    def test_un_producto_valorable_no_abstiene(self, politica):
        """La abstención es por el dato faltante, no por tener deuda."""
        d = politica.evaluar(
            Cliente(
                "C1",
                5000,
                "Plus",
                date(2019, 1, 1),
                (
                    ProductoVigente(
                        "Tarjeta Crédito",
                        10000.0,
                        31.52,
                        date(2021, 1, 1),
                        None,
                        CORTE,
                        None,
                        2000.0,
                    ),
                ),
            )
        )
        assert d.abstencion is False
        assert "productos_no_valorables" not in d.hechos


# ─────────────────────────────────────────────────────────────────────────────
# Cada regla dispara cuando debe
# ─────────────────────────────────────────────────────────────────────────────
class TestReglas:
    def test_cliente_nuevo_con_producto_no_recibe_otro(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                5000,
                "Plus",
                date(2025, 11, 1),
                (ProductoVigente("Tarjeta Crédito", 3000, 31.52, date(2025, 11, 15), None, CORTE),),
            )
        )
        assert not d.elegible
        assert any("relación con el banco" in m for m in d.motivos)

    def test_cliente_nuevo_SIN_productos_si_puede(self, politica):
        """La antigüedad solo se exige para un producto adicional."""
        d = politica.evaluar(Cliente("C1", 5000, "Plus", date(2025, 11, 1)))
        assert d.elegible

    def test_tope_de_numero_de_productos(self, politica):
        n = politica.u["max_productos_credito"]
        productos = tuple(
            ProductoVigente("Tarjeta Crédito", 1000, 31.52, date(2020, 1, 1), None, CORTE)
            for _ in range(n)
        )
        d = politica.evaluar(Cliente("C1", 50_000, "Plus", date(2015, 1, 1), productos))
        assert not d.elegible
        assert any("máximo" in m for m in d.motivos)

    def test_corte_duro_de_dti(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                1000,
                "Plus",
                date(2015, 1, 1),
                (ProductoVigente("Tarjeta Crédito", 20_000, 31.52, date(2020, 1, 1), None, CORTE),),
            )
        )
        assert not d.elegible
        assert any("ingreso mensual" in m for m in d.motivos)

    def test_exposicion_sobre_ingreso_anual(self, politica):
        """Ingreso bajo con una hipoteca enorme: la exposición corta antes."""
        d = politica.evaluar(
            Cliente(
                "C1",
                2000,
                "Premium",
                date(2015, 1, 1),
                (
                    ProductoVigente(
                        "Préstamo Hipotecario", 500_000, 8.98, date(2024, 1, 1), None, CORTE
                    ),
                ),
            )
        )
        assert not d.elegible
        assert d.motivos

    def test_el_orden_de_las_reglas_es_estable(self, politica):
        """Un cliente que incumple varias reglas siempre reporta la primera."""
        c = Cliente(
            "C1",
            800,
            "Plus",
            date(2025, 12, 1),
            (ProductoVigente("Tarjeta Crédito", 40_000, 31.52, date(2025, 12, 1), None, CORTE),),
        )
        primero = politica.evaluar(c).motivos[0]
        for _ in range(3):
            assert politica.evaluar(c).motivos[0] == primero


# ─────────────────────────────────────────────────────────────────────────────
# Revolvente contra cuota fija
# ─────────────────────────────────────────────────────────────────────────────
class TestAmortizacion:
    def test_la_tarjeta_pesa_el_pago_minimo_no_la_linea(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                10_000,
                "Plus",
                date(2018, 1, 1),
                (
                    ProductoVigente(
                        "Tarjeta Crédito", 30_000, 31.52, date(2021, 6, 1), date(2026, 6, 1), CORTE
                    ),
                ),
            )
        )
        esperado = 30_000 * politica.pago_minimo_pct
        assert d.hechos["carga_mensual_usd"] == pytest.approx(esperado, abs=1.0)

    def test_la_tarjeta_no_dispara_un_dti_imposible(self, politica):
        """El bug que había: amortizar la línea completa daba DTI sobre 400 %."""
        d = politica.evaluar(
            Cliente(
                "C1",
                9260,
                "Plus",
                date(2019, 3, 1),
                (
                    ProductoVigente(
                        "Tarjeta Crédito", 30_000, 31.52, date(2021, 6, 1), date(2026, 6, 1), CORTE
                    ),
                ),
            )
        )
        assert d.hechos["dti_actual"] < 1.0

    def test_la_cuota_del_prestamo_no_depende_de_su_madurez(self, politica):
        """Un préstamo paga lo mismo el mes 2 que el mes 40."""
        nuevo = politica.evaluar(
            Cliente(
                "C1",
                20_000,
                "Premium",
                date(2015, 1, 1),
                (
                    ProductoVigente(
                        "Préstamo Hipotecario", 100_000, 8.98, date(2025, 6, 1), None, CORTE
                    ),
                ),
            )
        )
        viejo = politica.evaluar(
            Cliente(
                "C2",
                20_000,
                "Premium",
                date(2015, 1, 1),
                (
                    ProductoVigente(
                        "Préstamo Hipotecario", 100_000, 8.98, date(2022, 6, 1), None, CORTE
                    ),
                ),
            )
        )
        assert nuevo.hechos["carga_mensual_usd"] == pytest.approx(
            viejo.hechos["carga_mensual_usd"], abs=1.0
        )

    def test_prestamo_ya_amortizado_sale_del_dti(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                3000,
                "Plus",
                date(2015, 1, 1),
                (
                    ProductoVigente(
                        "Préstamo Personal", 20_000, 20.10, date(2018, 1, 1), None, CORTE
                    ),
                ),
            )
        )
        assert d.hechos["carga_mensual_usd"] == pytest.approx(0.0, abs=0.01)
        assert any("vencido" in a for a in d.avisos)

    def test_vencimiento_real_manda_sobre_el_supuesto(self, politica):
        con_fecha = ProductoVigente(
            "Tarjeta Crédito", 10_000, 31.52, date(2023, 1, 1), date(2028, 1, 1), CORTE
        )
        assert politica._plazo_total(con_fecha) == 60


# ─────────────────────────────────────────────────────────────────────────────
# La capacidad de ML-04 solo puede restringir
# ─────────────────────────────────────────────────────────────────────────────
class TestCapacidad:
    def test_la_capacidad_restringe_el_margen(self, politica):
        libre = politica.evaluar(Cliente("C1", 6000, "Plus", date(2018, 1, 1)))
        acotado = politica.evaluar(
            Cliente("C2", 6000, "Plus", date(2018, 1, 1), capacidad_estimada_usd=200.0)
        )
        assert acotado.hechos["margen_mensual_usd"] == pytest.approx(200.0)
        assert acotado.hechos["margen_mensual_usd"] < libre.hechos["margen_mensual_usd"]

    def test_la_capacidad_nunca_amplia_el_margen(self, politica):
        """La referencia lleva capacidad observada a propósito: desde la v3, **no**
        tenerla recorta el margen, y entonces la comparación mediría eso en vez de
        medir que una capacidad alta no amplía."""
        libre = politica.evaluar(
            Cliente("C1", 3000, "Plus", date(2018, 1, 1), capacidad_estimada_usd=999_999.0)
        )
        generosa = politica.evaluar(
            Cliente("C2", 3000, "Plus", date(2018, 1, 1), capacidad_estimada_usd=999_999.0)
        )
        assert generosa.hechos["margen_mensual_usd"] == pytest.approx(
            libre.hechos["margen_mensual_usd"]
        )

    def test_si_se_abstiene_se_declara(self, politica):
        d = politica.evaluar(Cliente("C1", 6000, "Plus", date(2018, 1, 1)))
        assert any("capacidad de pago observada" in a for a in d.avisos)


# ─────────────────────────────────────────────────────────────────────────────
# Segmento y coherencia de la oferta
# ─────────────────────────────────────────────────────────────────────────────
class TestOferta:
    def test_hipotecario_no_se_ofrece_a_basic(self, politica):
        d = politica.evaluar(Cliente("C1", 20_000, "Basic", date(2015, 1, 1)))
        assert d.elegible
        assert "Préstamo Hipotecario" not in [o.producto for o in d.productos_elegibles]

    def test_student_solo_recibe_tarjeta(self, politica):
        d = politica.evaluar(Cliente("C1", 20_000, "Student", date(2015, 1, 1)))
        assert [o.producto for o in d.productos_elegibles] == ["Tarjeta Crédito"]

    def test_la_cuota_ofertada_cabe_en_el_margen(self, politica):
        d = politica.evaluar(Cliente("C1", 8000, "Premium", date(2015, 1, 1)))
        for o in d.productos_elegibles:
            assert o.cuota_estimada_usd <= d.hechos["margen_mensual_usd"] + 1.0

    def test_el_monto_respeta_el_tope_del_catalogo(self, politica):
        d = politica.evaluar(Cliente("C1", 5_000_000, "Premium", date(2015, 1, 1)))
        topes = {i["producto"]: i["monto_maximo_usd"] for i in politica.catalogo}
        for o in d.productos_elegibles:
            assert o.monto_maximo_usd <= topes[o.producto]

    def test_mas_ingreso_no_da_menos_credito(self, politica):
        montos = []
        for ingreso in (2000, 4000, 8000):
            d = politica.evaluar(Cliente("C", ingreso, "Premium", date(2015, 1, 1)))
            m = {o.producto: o.monto_maximo_usd for o in d.productos_elegibles}
            montos.append(m.get("Préstamo Personal", 0.0))
        assert montos == sorted(montos)


# ─────────────────────────────────────────────────────────────────────────────
# Trazabilidad: lo que el GroundingChecker necesita
# ─────────────────────────────────────────────────────────────────────────────
class TestTrazabilidad:
    def test_la_decision_es_serializable(self, politica):
        d = politica.evaluar(Cliente("C1", 6000, "Plus", date(2018, 1, 1)))
        salida = d.a_dict()
        assert salida["politica_version"] == politica.version
        assert set(salida) >= {
            "customer_id",
            "elegible",
            "abstencion",
            "hechos",
            "productos_elegibles",
            "motivos",
            "avisos",
        }

    def test_toda_cifra_de_la_respuesta_esta_en_los_hechos(self, politica):
        d = politica.evaluar(Cliente("C1", 6000, "Plus", date(2018, 1, 1)))
        for clave in (
            "ingreso_mensual_usd",
            "carga_mensual_usd",
            "dti_actual",
            "margen_mensual_usd",
            "n_productos_credito",
            "corte",
        ):
            assert clave in d.hechos

    def test_es_determinista(self, politica):
        c = Cliente(
            "C1",
            6000,
            "Plus",
            date(2018, 1, 1),
            (ProductoVigente("Tarjeta Crédito", 5000, 31.52, date(2021, 1, 1), None, CORTE),),
        )
        primera = politica.evaluar(c).a_dict()
        for _ in range(5):
            assert politica.evaluar(c).a_dict() == primera

    def test_no_niega_sin_dar_motivo(self, politica):
        casos = [
            Cliente("C1", None, "Plus", date(2020, 1, 1)),
            Cliente(
                "C2",
                500,
                "Plus",
                date(2015, 1, 1),
                (ProductoVigente("Tarjeta Crédito", 90_000, 31.52, date(2020, 1, 1), None, CORTE),),
            ),
            Cliente("C3", 100, "Basic", date(2015, 1, 1)),
        ]
        for c in casos:
            d = politica.evaluar(c)
            if not d.elegible:
                assert d.motivos, f"{c.customer_id} se negó sin motivo"


# ─────────────────────────────────────────────────────────────────────────────
# Posición financiera completa: saldo dispuesto y reservas
# ─────────────────────────────────────────────────────────────────────────────
class TestPosicionFinanciera:
    def test_el_saldo_dispuesto_pesa_menos_que_la_linea(self, politica):
        """Una tarjeta con 1 501 USD dispuestos de 25 536 no pesa como si
        estuviera agotada. Usar la línea entera sobreestima 17 veces."""
        con_saldo = politica.evaluar(
            Cliente(
                "C1",
                3000,
                "Plus",
                date(2018, 1, 1),
                (
                    ProductoVigente(
                        "Tarjeta Crédito", 25_536, 31.52, date(2021, 1, 1), saldo_usd=1501
                    ),
                ),
            )
        )
        sin_saldo = politica.evaluar(
            Cliente(
                "C2",
                3000,
                "Plus",
                date(2018, 1, 1),
                (ProductoVigente("Tarjeta Crédito", 25_536, 31.52, date(2021, 1, 1)),),
            )
        )
        assert con_saldo.hechos["carga_mensual_usd"] < sin_saldo.hechos["carga_mensual_usd"]

    def test_sin_saldo_conocido_se_asume_la_linea_completa(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                20_000,
                "Plus",
                date(2018, 1, 1),
                (ProductoVigente("Tarjeta Crédito", 10_000, 31.52, date(2021, 1, 1)),),
            )
        )
        assert d.hechos["carga_mensual_usd"] == pytest.approx(
            10_000 * politica.pago_minimo_pct, abs=1.0
        )

    def test_el_saldo_no_puede_exceder_la_linea(self, politica):
        """Un saldo mayor que el límite se recorta: no se inventa exposición."""
        d = politica.evaluar(
            Cliente(
                "C1",
                20_000,
                "Plus",
                date(2018, 1, 1),
                (
                    ProductoVigente(
                        "Tarjeta Crédito", 5_000, 31.52, date(2021, 1, 1), saldo_usd=99_999
                    ),
                ),
            )
        )
        tope = 5_000 * politica.pago_minimo_pct
        assert d.hechos["carga_mensual_usd"] <= tope + 1.0

    def test_el_piso_del_pago_minimo_se_respeta(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                20_000,
                "Plus",
                date(2018, 1, 1),
                (
                    ProductoVigente(
                        "Tarjeta Crédito", 10_000, 31.52, date(2021, 1, 1), saldo_usd=10.0
                    ),
                ),
            )
        )
        assert d.hechos["carga_mensual_usd"] >= politica.pago_minimo_piso

    def test_la_linea_no_dispuesta_se_estresa(self, politica):
        """Línea disponible es deuda que puede tomar mañana: pesa un poco."""
        if politica.estres_no_dispuesta <= 0:
            pytest.skip("el estrés de línea no dispuesta está desactivado")
        d = politica.evaluar(
            Cliente(
                "C1",
                20_000,
                "Plus",
                date(2018, 1, 1),
                (
                    ProductoVigente(
                        "Tarjeta Crédito", 10_000, 31.52, date(2021, 1, 1), saldo_usd=0.0
                    ),
                ),
            )
        )
        assert d.hechos["carga_mensual_usd"] > 0

    # ── reservas ─────────────────────────────────────────────────────────────
    def test_las_cuentas_suman_a_las_reservas(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                5000,
                "Plus",
                date(2015, 1, 1),
                (),
                (
                    ProductoDeAhorro("Cuenta Ahorro", 4989),
                    ProductoDeAhorro("Cuenta Corriente", 2500),
                ),
            )
        )
        assert d.hechos["reservas_usd"] == pytest.approx(7489.0)

    def test_la_inversion_entra_con_descuento(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1", 5000, "Plus", date(2015, 1, 1), (), (ProductoDeAhorro("Inversión", 10_000),)
            )
        )
        haircut = politica.act_semiliquidos["Inversión"]
        assert d.hechos["reservas_usd"] == pytest.approx(10_000 * haircut)
        assert d.hechos["reservas_usd"] < 10_000

    def test_un_producto_que_no_es_activo_no_suma(self, politica):
        d = politica.evaluar(
            Cliente("C1", 5000, "Plus", date(2015, 1, 1), (), (ProductoDeAhorro("Seguro", 50_000),))
        )
        assert d.hechos["reservas_usd"] == pytest.approx(0.0)
        assert any("no se computa como reserva" in a for a in d.avisos)

    def test_el_hipotecario_exige_reservas(self, politica):
        """Sin reservas no hay hipoteca, aunque la cuota quepa de sobra."""
        d = politica.evaluar(Cliente("C1", 6000, "Premium", date(2015, 1, 1)))
        ofrecidos = [o.producto for o in d.productos_elegibles]
        assert "Préstamo Hipotecario" not in ofrecidos
        assert any("reservas" in m for m in d.motivos)

    def test_con_reservas_el_hipotecario_aparece(self, politica):
        """Con capacidad observada: sin ella el hipotecario no se ofrece en la v3, y la
        prueba mediría la exclusión en vez de las reservas."""
        d = politica.evaluar(
            Cliente(
                "C1",
                6000,
                "Premium",
                date(2015, 1, 1),
                (),
                (ProductoDeAhorro("Cuenta Ahorro", 20_000), ProductoDeAhorro("Inversión", 40_000)),
                capacidad_estimada_usd=999_999.0,
            )
        )
        assert "Préstamo Hipotecario" in [o.producto for o in d.productos_elegibles]

    def test_la_tarjeta_no_exige_reservas(self, politica):
        d = politica.evaluar(Cliente("C1", 6000, "Premium", date(2015, 1, 1)))
        assert "Tarjeta Crédito" in [o.producto for o in d.productos_elegibles]

    # ── factor compensatorio ─────────────────────────────────────────────────
    def test_reservas_holgadas_amplian_el_tope(self, politica):
        c = Cliente(
            "C1",
            4000,
            "Premium",
            date(2015, 1, 1),
            (ProductoVigente("Préstamo Personal", 30_000, 20.10, date(2024, 1, 1)),),
            (ProductoDeAhorro("Cuenta Ahorro", 20_000), ProductoDeAhorro("Inversión", 40_000)),
        )
        d = politica.evaluar(c)
        assert d.hechos["tope_dti_aplicado"] == politica.comp_dti_ampliado
        assert any("reservas cubren" in a for a in d.avisos)

    def test_sin_carga_no_se_amplia_el_tope(self, politica):
        """Con cero deuda no hay nada que compensar: se aplica el tope normal."""
        d = politica.evaluar(
            Cliente(
                "C1",
                6000,
                "Premium",
                date(2015, 1, 1),
                (),
                (ProductoDeAhorro("Cuenta Ahorro", 500_000),),
            )
        )
        assert d.hechos["tope_dti_aplicado"] == politica.u["dti_maximo"]

    def test_sin_reservas_no_se_amplia_el_tope(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1",
                6000,
                "Premium",
                date(2015, 1, 1),
                (ProductoVigente("Préstamo Personal", 20_000, 20.10, date(2024, 1, 1)),),
            )
        )
        assert d.hechos["tope_dti_aplicado"] == politica.u["dti_maximo"]

    def test_las_reservas_no_saltan_el_corte_duro(self, politica):
        """Por muchas reservas que haya, el corte duro de DTI no se negocia."""
        d = politica.evaluar(
            Cliente(
                "C1",
                1000,
                "Premium",
                date(2015, 1, 1),
                (ProductoVigente("Préstamo Hipotecario", 200_000, 8.98, date(2024, 1, 1)),),
                (ProductoDeAhorro("Cuenta Ahorro", 5_000_000),),
            )
        )
        assert not d.elegible
        assert d.hechos["dti_actual"] >= politica.u["dti_corte_duro"]

    def test_las_reservas_aparecen_en_los_hechos(self, politica):
        d = politica.evaluar(
            Cliente(
                "C1", 5000, "Plus", date(2015, 1, 1), (), (ProductoDeAhorro("Cuenta Ahorro", 1000),)
            )
        )
        assert "reservas_usd" in d.hechos
        assert "tope_dti_aplicado" in d.hechos
