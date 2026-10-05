"""Base reducida para el despliegue público — `UI-08`.

`data/noema.duckdb` pesa 3 GB porque guarda 23 millones de transacciones. Un juez no
necesita las 23 millones: necesita poder conversar con el sistema, ver la traza y
comprobar que las cifras salen de la base. Esta base lleva una muestra de clientes
**reales y completos** — con todos sus productos y todas sus transacciones — más las
tablas que el sistema consulta siempre.

No es un recorte cosmético y conviene decir qué cambia y qué no:

- **Lo que no cambia:** cada cliente que está, está entero. Su posición financiera al
  corte se calcula con los mismos datos que en la base completa, así que la política
  decide exactamente lo mismo. Las cotizaciones de moneda van completas.
- **Lo que cambia:** el universo. La base completa tiene 75 798 clientes etiquetables y
  esta tiene los que se le pidan. Las métricas del conjunto retenido **no** se calculan
  acá: se calculan contra la base completa y se publican como archivo.

    python -m scripts.make_demo_db --clientes 2000
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import duckdb

LOGGER = logging.getLogger(__name__)

ORIGEN = Path("data/noema.duckdb")
DESTINO = Path("data/noema_demo.duckdb")

# Tablas que el sistema consulta por cliente: se filtran por la muestra.
POR_CLIENTE = {
    "noema_silver.stg_customers": "customer_id",
    "noema_silver.stg_products": "customer_id",
    "noema_silver.stg_transactions": "customer_id",
}
# Tablas que se copian completas: son pequeñas y el sistema las necesita enteras.
# Sin las cotizaciones no hay conversión a USD, y el tool falla cerrado.
COMPLETAS = (
    "noema_silver.stg_daily_exchange_rates",
    "noema_gold.dq_report",
)


def construir(clientes: int, origen: Path = ORIGEN, destino: Path = DESTINO) -> dict[str, int]:
    if not origen.exists():
        raise FileNotFoundError(f"falta {origen}: correr `make ingest` y `make build` primero")
    if destino.exists():
        destino.unlink()

    con = duckdb.connect(str(destino))
    # ATTACH no admite parámetros en DuckDB, así que la ruta va en la cadena. Se
    # resuelve a absoluta y se rechaza una comilla antes de interpolarla.
    ruta = str(origen.resolve())
    if "'" in ruta:
        raise ValueError(f"ruta con comilla simple, no se interpola: {ruta!r}")
    con.execute(f"ATTACH '{ruta}' AS origen_completo (READ_ONLY)")  # noqa: S608
    con.execute("CREATE SCHEMA IF NOT EXISTS noema_silver")
    con.execute("CREATE SCHEMA IF NOT EXISTS noema_gold")

    # La muestra se toma entre los clientes **con producto de crédito vigente**: un
    # cliente sin crédito no puede ejercitar el workflow, y llenar la demo con ellos
    # daría abstenciones por falta de datos que no son el caso interesante.
    con.execute(
        """
        CREATE TEMP TABLE muestra AS
        SELECT DISTINCT c.customer_id
        FROM origen_completo.noema_silver.stg_customers c
        JOIN origen_completo.noema_silver.stg_products p ON p.customer_id = c.customer_id
        WHERE p.product_status = 'Active'
          AND p.product_type IN ('Tarjeta Crédito', 'Préstamo Personal', 'Préstamo Hipotecario')
          AND c.document_number IS NOT NULL AND c.date_of_birth IS NOT NULL
        ORDER BY c.customer_id
        LIMIT ?
        """,
        [max(1, clientes)],
    )

    conteos: dict[str, int] = {}
    for tabla, llave in POR_CLIENTE.items():
        con.execute(
            f"CREATE TABLE {tabla} AS "  # noqa: S608 — nombres de un diccionario fijo
            f"SELECT * FROM origen_completo.{tabla} "
            f"WHERE {llave} IN (SELECT customer_id FROM muestra)"
        )
        conteos[tabla] = con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]  # noqa: S608

    for tabla in COMPLETAS:
        try:
            con.execute(f"CREATE TABLE {tabla} AS SELECT * FROM origen_completo.{tabla}")  # noqa: S608
            conteos[tabla] = con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]  # noqa: S608
        except Exception as exc:
            # No se cae: se dice qué falta. `dq_report` puede no existir si no se
            # corrió la capa gold, y el resto del sistema funciona igual sin ella.
            LOGGER.warning("no se pudo copiar %s: %s", tabla, exc)
            conteos[tabla] = 0

    con.execute("DETACH origen_completo")
    con.close()

    _elegir_ejemplos(destino)

    # Relectura real en el destino: la regla 3 del proyecto vale también para esto.
    # Un archivo creado no es un archivo que se puede leer.
    verif = duckdb.connect(str(destino), read_only=True)
    for tabla, esperado in conteos.items():
        if esperado == 0:
            continue
        leido = verif.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]  # noqa: S608
        if leido != esperado:
            verif.close()
            raise RuntimeError(f"{tabla}: se escribieron {esperado} filas y se leyeron {leido}")
    verif.close()
    return conteos


EJEMPLOS = Path("api/static/demo_clientes.json")


def _elegir_ejemplos(base: Path, por_estrato: int = 3) -> dict[str, list[str]]:
    """Elige clientes de la muestra para cada estrato de la política.

    Sin esto, `/session/demo` abría sesión con el primer cliente que encontrara y el
    juez veía una abstención como primera pantalla — un resultado correcto, pero el
    menos informativo de los tres. Con esto la demostración puede mostrar los tres
    caminos a propósito: oferta, rechazo explicado y abstención.

    La clasificación la hace la **misma** política que decide en vivo, con la misma
    reconstrucción del cliente que usa el generador del conjunto retenido. No se
    marcan a mano.
    """
    from datetime import date

    from agent.policies.engine import Politica
    from agent.tools.store import AnalyticsStore
    from eval.generator.build import cargar_poblacion, etiqueta

    corte = date(2025, 12, 31)
    con = duckdb.connect(str(base), read_only=True)
    store = AnalyticsStore(conexion=con)
    pol = Politica.cargar()
    ids = [
        r[0]
        for r in con.execute(
            "SELECT customer_id FROM noema_silver.stg_customers ORDER BY customer_id LIMIT 400"
        ).fetchall()
    ]
    poblacion = cargar_poblacion(con, store, ids, corte)

    por: dict[str, list[str]] = {"elegible": [], "rechazo_con_motivo": [], "abstencion": []}
    for cid, cliente in poblacion.items():
        _, _, estrato = etiqueta(pol, cliente, 3000.0)
        if estrato in por and len(por[estrato]) < por_estrato:
            por[estrato].append(cid)
        if all(len(v) >= por_estrato for v in por.values()):
            break
    con.close()

    faltan = [k for k, v in por.items() if not v]
    if faltan:
        # No se calla: si un estrato no aparece en la muestra, la demostración no
        # puede ofrecer ese camino y hay que saberlo antes de desplegar.
        LOGGER.warning("estratos sin ejemplo en la muestra: %s", ", ".join(faltan))

    EJEMPLOS.parent.mkdir(parents=True, exist_ok=True)
    EJEMPLOS.write_text(json.dumps(por, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("ejemplos por estrato -> %s", EJEMPLOS)
    return por


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Base reducida para el despliegue (UI-08)")
    ap.add_argument("--clientes", type=int, default=2000)
    ap.add_argument("--origen", type=Path, default=ORIGEN)
    ap.add_argument("--destino", type=Path, default=DESTINO)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    conteos = construir(args.clientes, args.origen, args.destino)
    for tabla, n in conteos.items():
        print(f"{tabla:45} {n:>10,} filas")
    mb = args.destino.stat().st_size / 1024 / 1024
    completo = args.origen.stat().st_size / 1024 / 1024
    print(f"\n{args.destino} -> {mb:,.1f} MB (la completa pesa {completo:,.0f} MB)")
    print("Relectura verificada en el destino: los conteos coinciden tabla por tabla.")
    if EJEMPLOS.exists():
        por = json.loads(EJEMPLOS.read_text(encoding="utf-8"))
        print("\nClientes de ejemplo por estrato de la política:")
        for estrato, cids in por.items():
            print(f"  {estrato:20} {len(cids)} cliente(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
