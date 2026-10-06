"""Tools de identidad y perfil — AG-04, tools 1 a 4.

Se prueban contra una base **en memoria** con el esquema real de silver, no contra
los 3 GB de `data/noema.duckdb`: así corren en CI y en un clon limpio. Las columnas
y los tipos son los que trae la base de verdad —`date_of_birth` es VARCHAR,
`products.currency` existe y `customers` no tiene columna de moneda— porque una
prueba contra un esquema inventado no prueba nada.

Lo que más importa de este archivo: **la conversión a dólares**. El ingreso viaja en
moneda local, equivocar la moneda cambia la cifra hasta 3 994 veces y no lanza
ninguna excepción (F-040). Casi la mitad de las pruebas de acá existen por eso.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from agent.tools import customer as mod
from agent.tools.registry import Role, Session, ToolDenied, ToolRegistry, TurnValues
from agent.tools.store import AnalyticsStore, Contexto, ConversionImposible

CORTE = date(2025, 12, 31)

# Tasas de la base de prueba, elegidas redondas para que las cuentas se lean.
COP_USD = 0.00025
ARS_USD = 0.003
MXN_USD = 0.06


@pytest.fixture
def analitica():
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
          ('C1','11111111','DNI','1980-05-10','Colombia','Plus', 9192466.0, DATE '2020-01-15'),
          ('C2','22222222','CE', '1990-01-01','México','Basic',    39220.0, DATE '2025-10-01'),
          ('C3','33333333','DNI','1975-03-03','Argentina','Premium',  NULL, DATE '2015-01-01'),
          ('C4','44444444','Pasaporte','1988-08-08','Brasil','Plus',5000.0, DATE '2019-01-01')
    """)
    con.execute("""
        CREATE TABLE noema_silver.stg_products (
            product_id VARCHAR, customer_id VARCHAR, product_type VARCHAR,
            currency VARCHAR, current_balance DOUBLE, credit_limit DOUBLE,
            interest_rate DOUBLE, opening_date DATE, expiration_date DATE,
            product_status VARCHAR, last_updated TIMESTAMP, last_transaction_date DATE
        )""")
    con.execute("""
        INSERT INTO noema_silver.stg_products VALUES
          -- C1: tarjeta en COP vigente, cuenta de ahorro, y un prestamo CERRADO
          ('P1','C1','Tarjeta Crédito','COP', 1500000.0, 25000000.0, 31.52,
             DATE '2021-01-01', DATE '2027-01-01','Active',
             TIMESTAMP '2026-05-01', DATE '2026-05-01'),
          ('P2','C1','Cuenta Ahorro','COP', 40000000.0, NULL, NULL,
             DATE '2020-02-01', NULL,'Active', NULL, NULL),
          ('P3','C1','Préstamo Personal','COP', 2000000.0, 8000000.0, 20.10,
             DATE '2022-01-01', NULL,'Closed', NULL, NULL),
          ('P4','C1','Seguro','COP', 100.0, NULL, NULL,
             DATE '2022-01-01', NULL,'Active', NULL, NULL),
          ('P5','C1','Inversión','COP', 10000000.0, NULL, NULL,
             DATE '2021-06-01', NULL,'Active', NULL, NULL),
          -- producto abierto DESPUES del corte: no existe para la evaluacion
          ('P6','C1','Préstamo Personal','COP', 0.0, 5000000.0, 20.10,
             DATE '2026-03-01', NULL,'Active', NULL, NULL),
          -- C2: tarjeta en USD
          ('P7','C2','Tarjeta Crédito','USD', 1000.0, 5000.0, 29.0,
             DATE '2024-01-01', NULL,'Active', NULL, NULL),
          -- C4: producto en una moneda sin tasa en la tabla
          ('P8','C4','Tarjeta Crédito','BRL', 500.0, 3000.0, 30.0,
             DATE '2021-01-01', NULL,'Active', NULL, NULL)
    """)
    con.execute("""
        CREATE TABLE noema_silver.stg_daily_exchange_rates (
            date DATE, source_currency VARCHAR, target_currency VARCHAR, exchange_rate DOUBLE
        )""")
    filas = []
    for d in ("2025-12-10", "2025-12-20", "2025-12-30"):
        filas += [
            f"(DATE '{d}','COP','USD',{COP_USD})",
            f"(DATE '{d}','ARS','USD',{ARS_USD})",
            f"(DATE '{d}','MXN','USD',{MXN_USD})",
        ]
    # Una cotizacion POSTERIOR al corte, que no debe usarse nunca.
    filas.append("(DATE '2026-05-01','COP','USD',0.99)")
    con.execute("INSERT INTO noema_silver.stg_daily_exchange_rates VALUES " + ",".join(filas))
    return AnalyticsStore(conexion=con)


@pytest.fixture
def contexto(analitica):
    return Contexto(analitica=analitica, corte=CORTE)


@pytest.fixture
def registry():
    r = ToolRegistry()
    mod.registrar(r)
    return r


def sesion(customer_id="C1", role=Role.CUSTOMER, verified=True):
    return Session(
        role=role,
        verified=verified,
        customer_id=customer_id,
        jti="j",
        conversation_id="conv-1",
    )


def llamar(registry, contexto, nombre, ses=None, params=None):
    return registry.invoke(nombre, ses or sesion(), params or {}, contexto=contexto)


# ═════════════════════════════════════════════════════════════════════════════
# La conversión a dólares — el lugar donde un error no se ve
# ═════════════════════════════════════════════════════════════════════════════


def test_la_tasa_es_la_mediana_de_la_ventana(analitica):
    assert analitica.tasa_a_usd("COP", CORTE) == COP_USD
    assert analitica.tasa_a_usd("ARS", CORTE) == ARS_USD


def test_los_dolares_no_se_convierten(analitica):
    assert analitica.tasa_a_usd("USD", CORTE) == 1.0


def test_nunca_se_usa_una_cotizacion_posterior_al_corte(analitica):
    """La base trae una tasa de 0.99 en mayo de 2026. Usarla sería fuga temporal."""
    assert analitica.tasa_a_usd("COP", CORTE) == COP_USD
    assert analitica.tasa_a_usd("COP", CORTE) != 0.99


def test_una_moneda_sin_tasa_no_se_asume_en_paridad(analitica):
    """Asumir 1.0 convertiría 9 192 466 COP en 9 192 466 USD. Falla cerrado."""
    with pytest.raises(ConversionImposible):
        analitica.tasa_a_usd("BRL", CORTE)


def test_un_pais_no_mapeado_no_se_asume_en_dolares(analitica):
    with pytest.raises(ConversionImposible):
        analitica.moneda_del_pais("Brasil")
    with pytest.raises(ConversionImposible):
        analitica.moneda_del_pais(None)


def test_el_mapeo_de_moneda_es_el_probado_en_f040():
    assert mod.__doc__  # el módulo documenta la regla
    from agent.tools.store import MONEDA_POR_PAIS

    assert MONEDA_POR_PAIS == {"Argentina": "ARS", "Colombia": "COP", "México": "MXN"}


def test_convertir_devuelve_la_tasa_junto_al_importe(analitica):
    """Sin la tasa, una conversión silenciosa es indistinguible de un error."""
    importe, tasa = analitica.a_usd(1000000.0, "COP", CORTE)
    assert importe == 250.0
    assert tasa == COP_USD


def test_un_importe_nulo_sigue_siendo_nulo(analitica):
    importe, tasa = analitica.a_usd(None, "COP", CORTE)
    assert importe is None
    assert tasa == COP_USD


# ═════════════════════════════════════════════════════════════════════════════
# 1 · verify_identity
# ═════════════════════════════════════════════════════════════════════════════


def test_los_tres_factores_correctos_verifican(registry, contexto):
    r = llamar(
        registry,
        contexto,
        "verify_identity",
        sesion(customer_id=None, verified=False, role=Role.ANONYMOUS),
        {"document_type": "DNI", "document_number": "11111111", "date_of_birth": "1980-05-10"},
    )
    assert r.ok and r.data["verificado"] is True
    assert r.data["customer_id_interno"] == "C1"


@pytest.mark.parametrize(
    "params",
    [
        {"document_type": "CE", "document_number": "11111111", "date_of_birth": "1980-05-10"},
        {"document_type": "DNI", "document_number": "11111111", "date_of_birth": "1980-05-11"},
        {"document_type": "DNI", "document_number": "99999999", "date_of_birth": "1980-05-10"},
    ],
    ids=["tipo_erroneo", "nacimiento_erroneo", "documento_inexistente"],
)
def test_cualquier_factor_mal_no_verifica_y_no_filtra_el_id(registry, contexto, params):
    r = llamar(
        registry,
        contexto,
        "verify_identity",
        sesion(customer_id=None, verified=False, role=Role.ANONYMOUS),
        params,
    )
    assert r.ok is True, "un fallo de identidad no es un error del tool"
    assert r.data["verificado"] is False
    assert r.data["customer_id_interno"] is None


def test_la_identidad_no_aporta_cifras_al_grounding(registry, contexto):
    """Un resultado de identidad no es un dato que el agente pronuncie."""
    turno = TurnValues()
    turno.registrar(
        llamar(
            registry,
            contexto,
            "verify_identity",
            sesion(customer_id=None, verified=False, role=Role.ANONYMOUS),
            {"document_type": "DNI", "document_number": "11111111", "date_of_birth": "1980-05-10"},
        )
    )
    assert turno.valores == []


def test_un_tipo_de_documento_inventado_se_rechaza_antes_de_la_base(registry, contexto):
    with pytest.raises(ToolDenied):
        llamar(
            registry,
            contexto,
            "verify_identity",
            sesion(customer_id=None, verified=False, role=Role.ANONYMOUS),
            {"document_type": "RUT", "document_number": "11111111", "date_of_birth": "1980-05-10"},
        )


def test_una_fecha_mal_formada_se_rechaza(registry, contexto):
    with pytest.raises(ToolDenied):
        llamar(
            registry,
            contexto,
            "verify_identity",
            sesion(customer_id=None, verified=False, role=Role.ANONYMOUS),
            {"document_type": "DNI", "document_number": "11111111", "date_of_birth": "10/05/1980"},
        )


# ═════════════════════════════════════════════════════════════════════════════
# 2 · get_customer_profile
# ═════════════════════════════════════════════════════════════════════════════


def test_el_ingreso_sale_en_dolares_con_su_tasa(registry, contexto):
    r = llamar(registry, contexto, "get_customer_profile")
    assert r.data["ingreso_mensual_usd"] == round(9192466.0 * COP_USD, 2)
    assert r.data["moneda_origen"] == "COP"
    assert r.data["tasa_aplicada"] == COP_USD
    assert r.data["segmento"] == "Plus"


def test_el_ingreso_convertido_queda_en_rango_de_negocio(registry, contexto):
    """2 298 USD de mediana regional (F-040). Un orden de magnitud fuera es un bug."""
    r = llamar(registry, contexto, "get_customer_profile")
    assert 100 < r.data["ingreso_mensual_usd"] < 100000


def test_mexico_se_convierte_con_mxn_aunque_no_tenga_productos_en_mxn(registry, contexto):
    r = llamar(registry, contexto, "get_customer_profile", sesion(customer_id="C2"))
    assert r.data["moneda_origen"] == "MXN"
    assert r.data["ingreso_mensual_usd"] == round(39220.0 * MXN_USD, 2)


def test_la_antiguedad_se_cuenta_hasta_el_corte(registry, contexto):
    r = llamar(registry, contexto, "get_customer_profile")
    # 2020-01-15 -> 2025-12-31
    assert r.data["antiguedad_cliente_meses"] == 71


def test_un_ingreso_nulo_se_declara_ausente_y_no_se_vuelve_cero(registry, contexto):
    """La política distingue «no hay ingreso» (abstiene) de «ingreso cero» (decide)."""
    r = llamar(registry, contexto, "get_customer_profile", sesion(customer_id="C3"))
    assert r.ok is True
    assert r.data["ingreso_mensual_usd"] is None
    assert "ingreso_mensual_usd" in r.ausencias


def test_un_pais_sin_moneda_conocida_deja_el_ingreso_ausente(registry, contexto):
    """Falla cerrado: 5 000 BRL no se convierten en 5 000 USD."""
    r = llamar(registry, contexto, "get_customer_profile", sesion(customer_id="C4"))
    assert r.ok is True
    assert r.data["ingreso_mensual_usd"] is None
    assert "ingreso_mensual_usd" in r.ausencias


def test_un_cliente_inexistente_falla_con_mensaje_y_sin_excepcion(registry, contexto):
    r = llamar(registry, contexto, "get_customer_profile", sesion(customer_id="NO-EXISTE"))
    assert r.ok is False
    assert r.error == "customer_not_found"
    assert "asesor" in r.mensaje_cliente


def test_el_perfil_ancla_sus_cifras(registry, contexto):
    turno = TurnValues()
    turno.registrar(llamar(registry, contexto, "get_customer_profile"))
    assert round(9192466.0 * COP_USD, 2) in turno.valores
    assert 71 in turno.valores
    assert COP_USD in turno.valores, "la tasa también se pronuncia"


# ═════════════════════════════════════════════════════════════════════════════
# 3 · get_customer_credit_products
# ═════════════════════════════════════════════════════════════════════════════


def test_solo_trae_productos_de_credito_vigentes(registry, contexto):
    r = llamar(registry, contexto, "get_customer_credit_products")
    ids = {p["producto_id"] for p in r.data["productos"]}
    assert ids == {"P1"}, "P3 está cerrado, P4 es Seguro, P5 es activo, P6 abre tras el corte"


def test_los_importes_del_producto_usan_la_moneda_del_producto(registry, contexto):
    r = llamar(registry, contexto, "get_customer_credit_products")
    p = r.data["productos"][0]
    assert p["limite_usd"] == round(25000000.0 * COP_USD, 2)
    assert p["saldo_usd"] == round(1500000.0 * COP_USD, 2)
    assert p["moneda_origen"] == "COP"


def test_un_producto_en_dolares_no_se_convierte(registry, contexto):
    r = llamar(registry, contexto, "get_customer_credit_products", sesion(customer_id="C2"))
    p = r.data["productos"][0]
    assert p["limite_usd"] == 5000.0
    assert p["tasa_aplicada"] == 1.0


def test_el_producto_trae_identificador(registry, contexto):
    """Sin él no se puede aparear la última actividad ni distinguir dos tarjetas."""
    r = llamar(registry, contexto, "get_customer_credit_products")
    assert all(p["producto_id"] for p in r.data["productos"])


def test_la_tasa_del_producto_es_la_suya_no_la_del_catalogo(registry, contexto):
    r = llamar(registry, contexto, "get_customer_credit_products")
    assert r.data["productos"][0]["tasa_anual"] == 31.52


def test_no_se_resuelve_la_ultima_actividad_aqui(registry, contexto):
    """Sale de `get_last_real_activity`: las columnas fáciles están vetadas (F-028)."""
    r = llamar(registry, contexto, "get_customer_credit_products")
    assert "ultima_transaccion_real" not in r.data["productos"][0]
    assert "last_updated" not in r.data["productos"][0]
    assert "last_transaction_date" not in r.data["productos"][0]


def test_un_producto_sin_tasa_de_cambio_se_declara_ausente(registry, contexto):
    """Dispara la abstención `sin_exposicion_valorable`; no se descarta en silencio."""
    r = llamar(registry, contexto, "get_customer_credit_products", sesion(customer_id="C4"))
    assert r.ok is True
    assert any(a.startswith("limite_usd:") for a in r.ausencias)
    assert r.data["productos"][0]["limite_usd"] is None


def test_un_cliente_sin_credito_devuelve_lista_vacia_sin_error(registry, contexto):
    r = llamar(registry, contexto, "get_customer_credit_products", sesion(customer_id="C3"))
    assert r.ok is True and r.data["n"] == 0


# ═════════════════════════════════════════════════════════════════════════════
# 4 · get_customer_assets
# ═════════════════════════════════════════════════════════════════════════════


def test_los_activos_son_los_del_bloque_de_reservas(registry, contexto):
    r = llamar(registry, contexto, "get_customer_assets")
    tipos = {a["tipo"] for a in r.data["activos"]}
    assert tipos == {"Cuenta Ahorro", "Inversión"}, "Seguro no es activo valorable"


def test_los_saldos_de_activos_salen_en_dolares(registry, contexto):
    r = llamar(registry, contexto, "get_customer_assets")
    por_tipo = {a["tipo"]: a["saldo_usd"] for a in r.data["activos"]}
    assert por_tipo["Cuenta Ahorro"] == round(40000000.0 * COP_USD, 2)
    assert por_tipo["Inversión"] == round(10000000.0 * COP_USD, 2)


def test_los_activos_no_incluyen_productos_de_credito(registry, contexto):
    r = llamar(registry, contexto, "get_customer_assets")
    assert not {a["tipo"] for a in r.data["activos"]} & set(mod.TIPOS_CREDITO)


# ═════════════════════════════════════════════════════════════════════════════
# El perímetro: quién puede llamar a qué
# ═════════════════════════════════════════════════════════════════════════════


def test_una_sesion_anonima_solo_alcanza_la_verificacion(registry):
    assert registry.catalogo_para(Role.ANONYMOUS) == ["verify_identity"]


def test_el_cliente_verificado_alcanza_las_cinco(registry):
    assert registry.catalogo_para(Role.CUSTOMER) == [
        "get_customer_assets",
        "get_customer_credit_products",
        "get_customer_product_summary",
        "get_customer_profile",
        "verify_identity",
    ]


def test_sin_verificar_no_se_lee_el_perfil(registry, contexto):
    anonima = Session(role=Role.ANONYMOUS, verified=False, conversation_id="conv-1")
    with pytest.raises(ToolDenied):
        llamar(registry, contexto, "get_customer_profile", anonima)


def test_los_marcadores_coinciden_con_los_tipos():
    """El SQL lleva los `?` literales para no interpolar nada. Si alguien añade un
    tipo de producto a la tupla y no añade el marcador, DuckDB falla en runtime; esto
    lo detecta al correr las pruebas."""
    assert len(mod.TIPOS_CREDITO) == 3, "ajustar `IN (?, ?, ?)` en get_customer_credit_products"
    assert len(mod.TIPOS_ACTIVO) == 4, "ajustar `IN (?, ?, ?, ?)` en get_customer_assets"


def test_ningun_tool_acepta_el_customer_id_como_parametro(registry):
    """El cliente no elige de quién son los datos (F-007)."""
    for nombre in registry.nombres():
        assert not {p.name for p in registry.get(nombre).params} & {"customer_id"}
