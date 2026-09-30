"""Feature store as-of para el modelo de riesgo — ML-01.

Lee la capa silver y gold que construye Federico y produce una tabla de
variables con corte temporal explícito, sin fuga, más la etiqueta y las marcas
que dicen de qué se puede fiar uno.

No modifica ninguna tabla de `data_platform/`: solo lee. La capa gold de
Federico (`credit_features_asof`, DAT-10) entra como insumo y sale intacta.

## Por qué esto no es un `SELECT *`

Tres cosas del dataset obligan a un diseño más cuidadoso de lo habitual.

**1. `products` y `customers` son fotos, no historia.** Una fila por producto,
con el estado actual y un `last_updated`. No hay forma de saber cuánto valía el
`credit_limit` de un cliente en la fecha de corte: solo se sabe cuánto vale hoy.
El 12 % de los productos y el 12 % de los clientes se actualizaron *después* del
corte, así que para esas filas el valor refleja información que en el corte no
existía.

**2. La etiqueta viene de esa misma foto.** `days_past_due` es el estado de mora
al momento del extracto —junio de 2026—, que es posterior al corte. Esa es la
lectura correcta y vale para los 76 906 clientes con producto de crédito.

Se exploró una lectura más restrictiva: que `last_updated` indicara cuándo se
registró ese estado, y que por lo tanto solo fueran válidas las filas con
`last_updated` posterior al corte. **Esa lectura no se sostiene.** El campo está
repartido de forma uniforme sobre nueve años (KS contra uniforme 0.049, curtosis
−1.161 contra −1.2 teórico) y es estadísticamente idéntico entre productos en
mora y al día: media −182.3 días contra −181.6. Si un incumplimiento provocara
una escritura de fila, los productos en mora tendrían `last_updated` reciente.
No lo tienen. Es un sello de modificación sorteado, no un registro de cuándo
cambió la mora.

**3. La etiqueta no discrimina.** Ver `docs/knowledge/findings.md` F-017:
`days_past_due` es una Bernoulli(0.075) sorteada por producto, independiente de
todo. Este módulo igual se construye con rigor, porque el rigor es el entregable
y porque la tabla sirve para el agente aunque no sirva para predecir.

## Qué produce

Una tabla con las dos cohortes marcadas. No se borra ninguna fila: el filtrado
lo decide quien entrena.

- **`completa`** — los 76 906 clientes con producto de crédito. Es la cohorte de
  trabajo.
- **`estricta`** — además exige `last_updated` posterior al corte. Son 7 078.
  Se conserva como **análisis de sensibilidad**, no como cohorte principal: si
  la conclusión aguanta con 7 078 y con 76 906, no depende de cómo se lea ese
  campo. Y aguanta: AUC 0.5012 y 0.4693, ambas con el intervalo cruzando 0.5.

## Niveles de confianza de cada variable

- **`asof`** — derivada de hechos anteriores al corte: transacciones filtradas,
  antigüedad desde `opening_date` y `registration_date`. Seguras.
- **`snapshot`** — viene de la foto. La marca `*_posterior` dice si esa fila se
  escribió después del corte. Es una precaución, no una prueba: por lo dicho
  arriba, el campo acota cuándo *pudo* cambiar el valor, no cuándo cambió.
- **prohibida** — no entra nunca. La lista vive en `COLUMNAS_PROHIBIDAS` y la
  prueba `tests/data/test_feature_contract.py` la verifica sola.

Uso:
    python -m ml.features.build_features
    python -m ml.features.build_features --corte 2025-06-30 --salida data/gold
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

log = logging.getLogger("features")

# Corte declarado en ADR-0004. Se verificó empíricamente que moverlo no cambia
# el tamaño del universo (el `last_updated` está repartido al azar, así que
# ~12 % cae después de cualquier fecha), pero sí la historia transaccional
# disponible: 2025-12-31 da 30 meses y 3.74 M de transacciones.
CORTE_POR_DEFECTO = date(2025, 12, 31)

# Ventana de las variables transaccionales, en días.
VENTANA_DIAS = 180

# Umbral de incumplimiento. 90 días es el estándar de Basilea.
DIAS_MORA = 90

# Los tres productos que pueden entrar en mora. En el resto `days_past_due` es
# nulo estructural: significa «no aplica», no «al día». Ver F-014.
PRODUCTOS_DE_CREDITO = ("Tarjeta Crédito", "Préstamo Personal", "Préstamo Hipotecario")

# Nunca entran como variable. Espejo de tests/data/test_feature_contract.py.
COLUMNAS_PROHIBIDAS = {
    "current_balance": "refleja el estado posterior al incumplimiento",
    "last_transaction_date": "un cliente en mora deja de transar: codifica el desenlace",
    "product_status": "es consecuencia de la mora, no causa",
    "days_past_due": "es la etiqueta, nunca una variable",
    "resolution_date": "posterior al hecho que se quiere predecir",
    "compensation_granted": "posterior al hecho que se quiere predecir",
}

# Columnas de la foto que se aceptan, con la marca que las acompaña.
SNAPSHOT_CLIENTE = ("credit_score", "estimated_monthly_income")
SNAPSHOT_PRODUCTO = ("credit_limit",)

# Moneda en la que está expresado el ingreso declarado, por país del cliente.
#
# `estimated_monthly_income` viene en moneda local y `stg_customers` no trae
# columna de moneda, así que hay que derivarla del país. Los productos sí traen
# `currency` y se convierten con ella directamente.
#
# Sin esta conversión un cliente colombiano parece 234 veces más rico que uno
# mexicano por la pura unidad de cuenta: mediana 9 200 526 COP contra 39 475 MXN.
# Ver F-025.
MONEDA_POR_PAIS = {
    "Argentina": "ARS",
    "Colombia": "COP",
    "México": "MXN",
}

# Variables que se retiran del feature store por redundancia. Cada una repite
# información ya presente en otra, con VIF por encima de 10 o correlación sobre
# 0.84. Se conserva la de mejor cobertura o la de VIF menor. Ver F-025.
# Silver TRADUCE `transaction_type` al español —Compra, Retiro, Transferencia,
# Pago, Depósito, Ajuste— y deja `transaction_status` en inglés. Usar los valores
# de bronze aquí devuelve cero filas en silencio, que es exactamente lo que pasó
# al construir el bloque de cuotas. Las constantes están para que no vuelva.
TIPO_PAGO = "Pago"
ESTADO_APROBADO = "Approved"

RETIRADAS_POR_REDUNDANCIA = {
    "n_sucursales": "duplica n_productos (r = 0.9913): cada producto arrastra su sucursal",
    "ticket_sd_usd_180d": "duplica ticket_max_usd_180d (r = 0.9444)",
    "ticket_max_usd_180d": "duplica volumen_usd_180d y ticket_medio (r = 0.8288)",
    "tx_180d": "duplica meses_activos_180d (r = 0.8404); se conserva el de VIF menor",
}


def _sql_cohortes(corte: str, sig: str) -> str:
    """Construye la consulta completa. Se deja en un solo SQL a propósito.

    DuckDB resuelve esto en una pasada sobre parquet; partirlo en pandas
    obligaría a materializar 4.4 M de transacciones en memoria sin ganar nada
    en claridad.
    """
    tipos = ", ".join(f"'{t}'" for t in PRODUCTOS_DE_CREDITO)
    # Mapa país → moneda para convertir el ingreso declarado. `stg_customers` no
    # trae columna de moneda; los productos sí, y se convierten con la suya.
    caso_moneda = " ".join(f"when '{p}' then '{m}'" for p, m in MONEDA_POR_PAIS.items())
    # `sig` = día siguiente al corte. Las variables cubren el día del corte
    # completo, así que una etiqueta solo lo *sigue* si se observó desde el
    # día siguiente. Sin esto, una observación a las 14:00 del día del corte
    # pasaría el filtro con cero días de separación.
    sql = f"""
    with
    -- Tasa de cambio a USD por moneda, mediana de los 30 días previos al corte.
    -- Se usa la mediana y no la del día exacto para no quedar a merced de un
    -- festivo sin cotización. Nunca una fecha posterior al corte.
    tasas as (
        select source_currency                                               as moneda,
               median(exchange_rate)                                          as a_usd
        from noema_silver.stg_daily_exchange_rates
        where target_currency = 'USD'
          and date <= DATE '{corte}'
          and date >  DATE '{corte}' - INTERVAL 30 DAY
        group by 1
    ),

    -- Etiqueta. Solo productos de crédito con valor: el nulo de una cuenta de
    -- ahorro significa «no aplica» y contarlo como «al día» infla el
    -- denominador un 64 % (F-015).
    -- La etiqueta del cliente es un `max()` sobre sus productos, así que la
    -- validez temporal hay que imponerla DENTRO de la agregación, no marcarla
    -- después: un cliente con un producto observado antes del corte y otro
    -- después produciría una etiqueta que mezcla una observación válida con una
    -- inválida. Por eso se agregan dos etiquetas separadas y la marca de
    -- cobertura se deriva de que exista la estricta, no de un `max()` de marcas.
    etiqueta as (
        select
            customer_id,
            -- completa: todos los productos de crédito, sin importar cuándo se
            -- observó su estado. Es la que infla el universo; se conserva para
            -- poder mostrar con números que no vale.
            max(case when days_past_due >= {DIAS_MORA} then 1 else 0 end)   as mora_90,
            max(case when days_past_due >  0           then 1 else 0 end)   as mora_cualquiera,
            count(*)                                                        as n_productos_credito,

            -- estricta: solo productos cuyo estado se registró después del
            -- corte, o sea después de las variables. Queda nula si el cliente
            -- no tiene ninguno.
            max(case when last_updated >= DATE '{sig}' and days_past_due >= {DIAS_MORA}
                     then 1 when last_updated >= DATE '{sig}' then 0 end) as mora_90_estricta,
            count(*) filter (where last_updated >= DATE '{sig}') as n_credito_estricto,

            -- Días entre el corte y la observación, sobre el subconjunto
            -- estricto. Positivo por construcción.
            min(date_diff('day', DATE '{corte}', last_updated))
                filter (where last_updated >= DATE '{sig}') as dias_hasta_etiqueta
        from noema_silver.stg_products
        where days_past_due is not null
          and product_type in ({tipos})
          and opening_date <= DATE '{corte}'
        group by 1
    ),

    -- Variables transaccionales. Filtro por fecha de evento Y de proceso: mirar
    -- solo la de evento dejaría entrar movimientos que en el corte todavía no
    -- estaban registrados en el sistema.
    tx as (
        select
            customer_id,
            count(*)                                                        as tx_180d,
            count(distinct date_trunc('month', transaction_date))            as meses_activos_180d,
            sum(converted_amount_usd)                                        as volumen_usd_180d,
            sum(case when transaction_type = 'Depósito'
                     then converted_amount_usd else 0 end)                   as entradas_usd_180d,
            sum(case when transaction_type in ('Pago','Compra','Retiro')
                     then converted_amount_usd else 0 end)                   as salidas_usd_180d,
            sum(case when transaction_type in ('Transferencia','Ajuste')
                     then 1 else 0 end)                                      as tx_ambiguas_180d,
            avg(converted_amount_usd) as ticket_medio_usd_180d,
            count(distinct channel)                                          as canales_180d,
            sum(case when transaction_status = 'Declined'  then 1 else 0 end) as tx_rechazadas_180d,
            sum(case when transaction_status = 'Reversed'  then 1 else 0 end) as tx_reversadas_180d,
            max(transaction_date)                                            as ultima_tx,
            min(transaction_date)                                            as primera_tx
        from noema_silver.transactions_with_fx
        where transaction_date <= DATE '{corte}'
          and process_date     <= DATE '{corte}'
          and transaction_date >  DATE '{corte}' - INTERVAL {VENTANA_DIAS} DAY
        group by 1
    ),

    -- Cartera de productos al corte. `credit_limit` es de la foto, así que
    -- viaja con la marca de si se actualizó después.
    cartera as (
        select
            customer_id,
            count(*)                                                        as n_productos,
            count(*) filter (where product_type in ({tipos}))                as n_credito,
            -- El límite viene en la moneda del producto. Sin convertir, sumar
            -- una tarjeta en COP con una hipoteca en USD no significa nada.
            sum(credit_limit * coalesce(fx.a_usd, case when p.currency = 'USD'
                                                      then 1.0 end))        as limite_total_usd,
            count(*) filter (where credit_limit is not null
                               and fx.a_usd is null
                               and p.currency <> 'USD')                      as limites_sin_tasa,
            max(date_diff('day', opening_date, DATE '{corte}')) as antiguedad_producto_dias,
            min(date_diff('day', opening_date, DATE '{corte}')) as producto_mas_nuevo_dias,
            avg(interest_rate)                                              as tasa_interes_media,
            max(case when last_updated >= DATE '{sig}' then 1 else 0 end) as limite_posterior,
            -- Sucursal derivada: `registration_branch_id` no es llave foránea
            -- (F-012), pero `opening_branch_id` sí lo es y cubre el 93 %.
            -- `n_sucursales` se retiró por redundancia: duplicaba n_productos
            -- con r = 0.9913. Ver RETIRADAS_POR_REDUNDANCIA.
            mode(opening_branch_id)                                          as sucursal_derivada
        from noema_silver.stg_products p
        left join tasas fx on fx.moneda = p.currency
        where opening_date <= DATE '{corte}'
        group by 1
    ),

    -- Comportamiento de pago sobre productos de crédito. Hecho DESCRIPTIVO, no
    -- predictor: se incorpora porque el agente necesita poder decirle al cliente
    -- cuántas cuotas registra, y la política puede decidir sobre el cumplimiento.
    -- No discrimina riesgo y no debe usarse como tal (F-030, F-033).
    --
    -- El supuesto es vencimiento mensual, y se declara como supuesto: el dataset
    -- no tiene calendario de pagos (F-029).
    cuotas as (
        select
            p.customer_id,
            sum(date_diff('month', p.opening_date, DATE '{corte}'))          as cuotas_esperadas,
            coalesce(sum(g.n), 0)                                            as cuotas_pagadas,
            coalesce(sum(g.pagado_usd), 0)                                   as pagado_usd
        from noema_silver.stg_products p
        left join (
            select product_id,
                   count(*)                                                  as n,
                   sum(converted_amount_usd)                                 as pagado_usd
            from noema_silver.transactions_with_fx
            where transaction_type   = '{TIPO_PAGO}'
              and transaction_status = '{ESTADO_APROBADO}'
              and transaction_date  <= DATE '{corte}'
              and process_date      <= DATE '{corte}'
            group by 1
        ) g on g.product_id = p.product_id
        where p.product_type in ({tipos})
          and p.opening_date <= DATE '{corte}'
        group by 1
    ),

    -- Quejas anteriores al corte. Señal de fricción, no de riesgo, pero el
    -- agente la usa y conviene tenerla medida.
    quejas as (
        select customer_id,
               count(*)                                                     as quejas_180d,
               count(*) filter (where claimed_amount is not null)            as quejas_con_monto
        from noema_silver.stg_complaints
        -- Filtro por fecha de creación Y de proceso, igual que en transacciones:
        -- una queja creada antes del corte pero procesada después no se conocía
        -- en el corte. `resolution_date` y `compensation_granted` no se tocan:
        -- están en la lista de prohibidas por ser posteriores al hecho.
        where creation_date <= DATE '{corte}'
          and process_date  <= DATE '{corte}'
          and creation_date >  DATE '{corte}' - INTERVAL {VENTANA_DIAS} DAY
        group by 1
    )

    select
        c.customer_id,
        DATE '{corte}'                                                       as asof_date,

        -- ── nivel asof: derivadas de hechos anteriores al corte ──
        date_diff('day', c.registration_date, DATE '{corte}') as antiguedad_cliente_dias,
        coalesce(k.n_productos, 0)                                           as n_productos,
        coalesce(k.n_credito, 0)                                             as n_productos_credito,
        k.antiguedad_producto_dias,
        k.producto_mas_nuevo_dias,
        coalesce(t.meses_activos_180d, 0)                                    as meses_activos_180d,
        coalesce(t.volumen_usd_180d, 0)                                      as volumen_usd_180d,
        coalesce(t.entradas_usd_180d, 0)                                     as entradas_usd_180d,
        coalesce(t.salidas_usd_180d, 0)                                      as salidas_usd_180d,
        coalesce(t.tx_ambiguas_180d, 0)                                      as tx_ambiguas_180d,
        t.ticket_medio_usd_180d,
        coalesce(t.canales_180d, 0)                                          as canales_180d,
        coalesce(t.tx_rechazadas_180d, 0)                                    as tx_rechazadas_180d,
        coalesce(t.tx_reversadas_180d, 0)                                    as tx_reversadas_180d,
        case when t.volumen_usd_180d > 0
             then t.salidas_usd_180d / t.volumen_usd_180d end                as razon_salidas,
        case when t.entradas_usd_180d > 0
             then t.salidas_usd_180d / t.entradas_usd_180d end               as cobertura_salidas,
        date_diff('day', t.ultima_tx, DATE '{corte}') as dias_desde_ultima_tx,
        coalesce(q.quejas_180d, 0)                                           as quejas_180d,

        -- ── nivel snapshot: de la foto, con su marca ──
        c.credit_score,
        -- Ingreso convertido a USD. `stg_customers` no trae moneda, así que se
        -- deriva del país con MONEDA_POR_PAIS. Sin esto, un cliente colombiano
        -- parece 234 veces más rico que uno mexicano (F-025).
        c.estimated_monthly_income * fxc.a_usd                               as ingreso_usd,
        case when c.estimated_monthly_income is not null and fxc.a_usd is null
             then 1 else 0 end                                               as ingreso_sin_tasa,
        k.limite_total_usd,
        coalesce(k.limites_sin_tasa, 0)                                      as limites_sin_tasa,
        k.tasa_interes_media,

        -- ── comportamiento de pago: hecho descriptivo, NO predictor ──
        -- Supuesto declarado: vencimiento mensual. No hay calendario de pagos
        -- en el dataset (F-029), así que las cuotas esperadas son los meses
        -- transcurridos desde la apertura de cada producto de crédito.
        cu.cuotas_esperadas,
        coalesce(cu.cuotas_pagadas, 0)                                       as cuotas_pagadas,
        coalesce(cu.pagado_usd, 0)                                           as pagado_usd,
        case when cu.cuotas_esperadas > 0
             then cu.cuotas_pagadas::DOUBLE / cu.cuotas_esperadas end        as cumplimiento,
        case when c.last_updated >= DATE '{sig}' then 1 else 0 end as cliente_posterior,
        coalesce(k.limite_posterior, 0)                                      as limite_posterior,

        -- ── categóricas ──
        c.segment                                                            as segmento,
        c.country                                                            as pais,
        c.occupation                                                         as ocupacion,
        c.education_level                                                    as educacion,
        k.sucursal_derivada,

        -- ── indicadores de faltante: el nulo inyectado es aleatorio y se
        --    imputa, pero la marca va al modelo igual (F-014) ──
        case when c.credit_score is null then 1 else 0 end as credit_score_faltante,
        case when c.estimated_monthly_income is null then 1 else 0 end       as ingreso_faltante,
        case when k.tasa_interes_media is null then 1 else 0 end             as tasa_faltante,
        case when t.tx_180d is null then 1 else 0 end                        as sin_actividad_180d,

        -- ── etiqueta y su validez temporal ──
        -- `mora_90` es la etiqueta que se entrena. En la cohorte estricta toma
        -- el valor observado después del corte; en la completa, el agregado de
        -- todos los productos. Son columnas distintas a propósito: mezclarlas
        -- en una sola es exactamente el error que este módulo evita.
        e.mora_90,
        e.mora_cualquiera,
        e.mora_90_estricta,
        coalesce(e.n_credito_estricto, 0)                                    as n_credito_estricto,
        e.dias_hasta_etiqueta,
        -- NO es la mora: es un indicador de COBERTURA. Vale 1 cuando existe una
        -- observación válida después del corte. Se llamaba `etiqueta_posterior`
        -- y ese nombre hizo que se usara como variable objetivo durante un rato
        -- (F-023). La mora es `mora_90` o `mora_90_estricta`.
        case when e.mora_90_estricta is not null then 1 else 0 end   as tiene_observacion_posterior,
        case when e.customer_id is null then 0 else 1 end                    as etiquetable

    from noema_silver.stg_customers c
    left join etiqueta e using(customer_id)
    left join tx       t using(customer_id)
    left join cartera  k using(customer_id)
    left join quejas   q using(customer_id)
    left join cuotas   cu using(customer_id)
    left join tasas    fxc on fxc.moneda = case c.country {caso_moneda} end
    where c.registration_date <= DATE '{corte}'
    """  # noqa: S608 — lo único interpolado son fechas ya validadas por
    # date.fromisoformat y constantes del módulo; no hay entrada de usuario.
    return sql


def construir(con: duckdb.DuckDBPyConnection, corte: date) -> list[str]:
    """Materializa el feature store como vista `features` y devuelve sus columnas.

    Se crea la vista desde el texto del SQL y no desde una relación de Python:
    DuckDB resuelve las variables de Python mirando el frame que llama, así que
    una vista construida sobre `rel` deja de resolver en cuanto se consulta
    desde otra función.
    """
    log.info("construyendo variables con corte %s, ventana de %d días", corte, VENTANA_DIAS)
    sql = _sql_cohortes(corte.isoformat(), (corte + timedelta(days=1)).isoformat())
    con.sql(f"create or replace temp view features as {sql}")
    return [r[0] for r in con.sql("describe features").fetchall()]


def verificar_sin_fuga(columnas: list[str]) -> None:
    """Falla si entró una columna prohibida. Se corre antes de escribir nada.

    Es la misma lista que `tests/data/test_feature_contract.py`, duplicada a
    propósito: la prueba protege la tabla de Federico, esta protege la mía, y
    ninguna de las dos debe depender de que la otra se ejecute.
    """
    presentes = {c.lower() for c in columnas}
    fuga = {c: m for c, m in COLUMNAS_PROHIBIDAS.items() if c in presentes}
    if fuga:
        detalle = "\n".join(f"  - {c}: {m}" for c, m in fuga.items())
        raise ValueError(
            f"El feature store trae columnas con fuga de información:\n{detalle}\n\n"
            "Si alguna debe entrar, escríbelo en un ADR antes de tocar esta verificación."
        )


def resumen(con: duckdb.DuckDBPyConnection, corte: date) -> dict[str, Any]:
    """Estadísticas de la tabla construida, para el manifest y el reporte."""

    def uno(q: str) -> Any:
        return con.sql(q).fetchone()

    total, etiquetables, estrictos = uno("""
        select count(*),
               sum(etiquetable),
               sum(case when etiquetable = 1 and tiene_observacion_posterior = 1 then 1 else 0 end)
        from features""")

    tasa_estricta, pos_estrictos = uno("""
        select avg(mora_90_estricta), sum(mora_90_estricta) from features
        where tiene_observacion_posterior = 1""")

    tasa_completa, pos_completos = uno("""
        select avg(mora_90), sum(mora_90) from features where etiquetable = 1""")

    contaminadas = uno("""
        select sum(cliente_posterior), sum(limite_posterior) from features""")

    faltantes = (
        con.sql("""
        select 'credit_score' as col, avg(credit_score_faltante) as tasa from features
        union all select 'ingreso',   avg(ingreso_faltante)   from features
        union all select 'tasa',      avg(tasa_faltante)      from features
        union all select 'actividad', avg(sin_actividad_180d) from features
    """)
        .df()
        .to_dict("records")
    )

    return {
        "corte": corte.isoformat(),
        "ventana_dias": VENTANA_DIAS,
        "dias_mora": DIAS_MORA,
        "filas": int(total),
        "etiquetables": int(etiquetables or 0),
        "cohorte_estricta": int(estrictos or 0),
        "tasa_mora_estricta": float(tasa_estricta or 0),
        "positivos_estrictos": int(pos_estrictos or 0),
        "tasa_mora_completa": float(tasa_completa or 0),
        "positivos_completos": int(pos_completos or 0),
        "clientes_snapshot_posterior": int(contaminadas[0] or 0),
        "limites_snapshot_posterior": int(contaminadas[1] or 0),
        "tasas_faltante": {r["col"]: float(r["tasa"]) for r in faltantes},
        "columnas_prohibidas_verificadas": sorted(COLUMNAS_PROHIBIDAS),
        "generado": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Construye el feature store as-of (ML-01)")
    p.add_argument("--db", type=Path, default=Path("data/noema.duckdb"))
    p.add_argument("--corte", type=date.fromisoformat, default=CORTE_POR_DEFECTO)
    p.add_argument("--salida", type=Path, default=Path("data/gold"))
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.db.exists():
        raise SystemExit(
            f"No existe {args.db}. Corre primero `make audit` y el `dbt build` "
            "de data_platform/dbt."
        )

    con = duckdb.connect(str(args.db), read_only=True)
    columnas = construir(con, args.corte)
    verificar_sin_fuga(columnas)

    args.salida.mkdir(parents=True, exist_ok=True)
    destino = args.salida / "features_asof.parquet"
    con.sql(f"copy features to '{destino.as_posix()}' (format parquet)")

    info = resumen(con, args.corte)
    info["archivo"] = destino.as_posix()
    info["columnas"] = columnas

    manifest = args.salida / "features_asof.manifest.json"
    manifest.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    log.info("")
    log.info("escrito %s", destino)
    log.info("  filas                  %10s", f"{info['filas']:,}")
    log.info("  con etiqueta           %10s", f"{info['etiquetables']:,}")
    log.info(
        "  cohorte estricta       %10s   tasa de mora %.3f %%  (%s positivos)",
        f"{info['cohorte_estricta']:,}",
        info["tasa_mora_estricta"] * 100,
        f"{info['positivos_estrictos']:,}",
    )
    log.info(
        "  cohorte completa       %10s   tasa de mora %.3f %%  (%s positivos)",
        f"{info['etiquetables']:,}",
        info["tasa_mora_completa"] * 100,
        f"{info['positivos_completos']:,}",
    )
    log.info("  manifest               %s", manifest)


if __name__ == "__main__":
    main()
