"""Identidad y perfil del cliente — AG-04, tools 1 a 4.

Las cuatro salen de la derivación de ADR-0009: son exactamente los campos que
`Politica.evaluar` consume de un `Cliente`, más la puerta de identidad.

Tres reglas que se cumplen en las cuatro:

- **El `customer_id` llega de la sesión**, nunca de los parámetros. El registro
  rechaza al registrarse un tool que lo declare como parámetro (F-007).
- **Todo importe sale en USD con su tasa declarada.** El ingreso viaja en moneda
  local sin columna de moneda; equivocarla cambia la cifra hasta 3 994 veces sin
  lanzar nada (F-036, F-040).
- **Un dato ausente se declara ausente, no se rellena con cero.** La política
  distingue «no hay ingreso» de «ingreso cero»: la primera abstiene, la segunda
  sería una decisión.
"""

from __future__ import annotations

import hmac
import logging
from datetime import date
from typing import Any

from agent.policies.engine import cuota_francesa
from agent.tools.registry import REGISTRY, Param, Role, Session, ToolResult, ToolSpec
from agent.tools.store import Contexto, ConversionImposible

LOGGER = logging.getLogger(__name__)

# Tipos de documento que existen en el dataset. Un valor fuera de esta lista se
# rechaza en el parámetro, antes de tocar la base.
TIPOS_DOCUMENTO = ("DNI", "CE", "CC", "Pasaporte")

# Productos que son obligación de crédito. Son las claves de `amortizacion_vigentes`
# en la política: lo que la política sabe amortizar es lo que cuenta como deuda.
TIPOS_CREDITO = ("Tarjeta Crédito", "Préstamo Personal", "Préstamo Hipotecario")

# Productos que aportan saldo y no deuda. Coinciden con el bloque `activos` del YAML.
TIPOS_ACTIVO = ("Cuenta Ahorro", "Cuenta Corriente", "Tarjeta Débito", "Inversión")

# Solo los productos vigentes entran en la evaluación. `Closed`, `Blocked` y
# `Suspended` no son obligaciones vivas ni activos disponibles.
ESTADO_VIGENTE = "Active"

# Fila ficticia contra la que se compara cuando el documento no existe, para que el
# trabajo tenga la misma forma y no se pueda enumerar por tiempo de respuesta.
_SEÑUELO = {"document_type": "\x00", "date_of_birth": "\x00", "customer_id": None}


def _iguales(a: str | None, b: str | None) -> bool:
    """Comparación en tiempo constante (`docs/05_security.md` §2)."""
    return hmac.compare_digest(str(a or "").encode(), str(b or "").encode())


def _meses_entre(desde: date, hasta: date) -> int:
    return max(0, (hasta.year - desde.year) * 12 + hasta.month - desde.month)


# ─────────────────────────────────────────────────────────────────────────────
# 1 · verify_identity
# ─────────────────────────────────────────────────────────────────────────────
def _verify_identity(session: Session, params, contexto: Contexto, idempotency_key) -> ToolResult:
    """Compara tres factores. **No** emite sesión: eso es del AccessGuard (AG-05).

    Tampoco cuenta intentos ni bloquea — el límite de tres y el backoff son estado
    de sesión y viven en AG-05. Este tool solo responde si los tres factores
    coinciden.

    `data["customer_id_interno"]` lo consume el AccessGuard para meterlo **dentro**
    del JWT. No va al prompt, no va a la traza y no va a `grounded_values`: el
    modelo no debe poder pronunciarlo ni reutilizarlo.
    """
    fila = (
        contexto.analitica.una(
            """
            SELECT customer_id, document_type, date_of_birth
            FROM noema_silver.stg_customers
            WHERE document_number = ?
            """,
            (params["document_number"],),
        )
        or _SEÑUELO
    )
    # Las dos comparaciones corren siempre, también contra el señuelo.
    tipo_ok = _iguales(fila["document_type"], params["document_type"])
    nacimiento_ok = _iguales(fila["date_of_birth"], params["date_of_birth"])
    verificado = bool(tipo_ok and nacimiento_ok and fila["customer_id"])
    LOGGER.info("identity_check verificado=%s", verificado)
    return ToolResult(
        tool="verify_identity",
        ok=True,
        data={
            "verificado": verificado,
            "customer_id_interno": fila["customer_id"] if verificado else None,
        },
        # Ninguna cifra: un resultado de identidad no se pronuncia como dato.
        grounded_values=(),
        source="noema_silver.stg_customers",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2 · get_customer_profile
# ─────────────────────────────────────────────────────────────────────────────
def _get_customer_profile(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Ingreso en USD, segmento y antigüedad. Alimenta R1, R8 y el DTI."""
    fila = contexto.analitica.una(
        """
        SELECT segment, country, estimated_monthly_income, registration_date
        FROM noema_silver.stg_customers
        WHERE customer_id = ?
        """,
        (session.customer_id,),
    )
    if fila is None:
        return ToolResult(
            tool="get_customer_profile",
            ok=False,
            error="customer_not_found",
            mensaje_cliente="No encuentro tus datos. Te derivo con un asesor.",
            source="noema_silver.stg_customers",
        )

    ausencias: list[str] = []
    ingreso_usd: float | None = None
    tasa: float | None = None
    moneda: str | None = None
    try:
        moneda = contexto.analitica.moneda_del_pais(fila["country"])
        ingreso_usd, tasa = contexto.analitica.a_usd(
            fila["estimated_monthly_income"], moneda, contexto.corte
        )
    except ConversionImposible as exc:
        # Falla cerrado: sin moneda o sin tasa NO se asume paridad. El ingreso queda
        # ausente y la política abstiene, que es un resultado válido y medido.
        LOGGER.warning("ingreso_sin_conversion motivo=%s", exc)
        ausencias.append("ingreso_mensual_usd")
    if ingreso_usd is None and "ingreso_mensual_usd" not in ausencias:
        ausencias.append("ingreso_mensual_usd")

    alta = fila["registration_date"]
    antiguedad = _meses_entre(alta, contexto.corte) if alta is not None else None
    if antiguedad is None:
        ausencias.append("antiguedad_cliente_meses")

    valores: list[float] = [v for v in (ingreso_usd, antiguedad) if v is not None]
    if tasa is not None and moneda != "USD":
        valores.append(tasa)
    return ToolResult(
        tool="get_customer_profile",
        ok=True,
        data={
            "segmento": fila["segment"],
            "ingreso_mensual_usd": ingreso_usd,
            "moneda_origen": moneda,
            "tasa_aplicada": tasa,
            "alta": alta,
            "antiguedad_cliente_meses": antiguedad,
        },
        grounded_values=tuple(valores),
        ausencias=tuple(ausencias),
        source="noema_silver.stg_customers",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3 · get_customer_credit_products
# ─────────────────────────────────────────────────────────────────────────────
def _get_customer_credit_products(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Los `ProductoVigente`. Alimenta R2, R3 y R4.

    Deja `ultima_transaccion_real` sin resolver a propósito: sale de
    `get_last_real_activity`, que la calcula sobre transacciones. Las columnas
    fáciles están vetadas — `last_updated` trae 6.42 % de valores posteriores al
    corte y `last_transaction_date` un 17.29 % de incoherencias (F-028).
    """
    filas = contexto.analitica.filas(
        # Marcadores literales: la consulta es una cadena constante y no se
        # interpola nada, ni un `?`. `test_los_marcadores_coinciden_con_los_tipos`
        # falla si alguien añade un tipo y no añade el marcador.
        """
        SELECT product_id, product_type, currency, credit_limit, current_balance,
               interest_rate, opening_date, expiration_date
        FROM noema_silver.stg_products
        WHERE customer_id = ?
          AND product_status = ?
          AND product_type IN (?, ?, ?)
          AND opening_date IS NOT NULL
          AND opening_date <= ?
        ORDER BY opening_date, product_id
        """,
        (session.customer_id, ESTADO_VIGENTE, *TIPOS_CREDITO, contexto.corte),
    )

    productos: list[dict] = []
    ausencias: list[str] = []
    valores: list[float] = []
    for f in filas:
        try:
            limite, tasa_fx = contexto.analitica.a_usd(
                f["credit_limit"], f["currency"], contexto.corte
            )
            saldo, _ = contexto.analitica.a_usd(f["current_balance"], f["currency"], contexto.corte)
        except ConversionImposible as exc:
            # Un producto que no se puede valorar bloquea la evaluación por la
            # abstención `sin_exposicion_valorable`. No se descarta en silencio.
            LOGGER.warning("producto_sin_conversion id=%s motivo=%s", f["product_id"], exc)
            ausencias.append(f"limite_usd:{f['product_id']}")
            limite = saldo = tasa_fx = None
        # Las dos ausencias que disparan `sin_exposicion_valorable`: sin límite no
        # hay exposición y sin tasa no hay cuota. El 5.1 % y el 10.2 % de los
        # productos de crédito activos, respectivamente (F-041).
        if limite is None:
            ausencias.append(f"limite_usd:{f['product_id']}")
        if f["interest_rate"] is None:
            ausencias.append(f"tasa_anual:{f['product_id']}")
        productos.append(
            {
                "producto_id": f["product_id"],
                "tipo": f["product_type"],
                "limite_usd": limite,
                "saldo_usd": saldo,
                "tasa_anual": f["interest_rate"],
                "apertura": f["opening_date"],
                "vencimiento": f["expiration_date"],
                "moneda_origen": f["currency"],
                "tasa_aplicada": tasa_fx,
            }
        )
        valores.extend(v for v in (limite, saldo, f["interest_rate"]) if v is not None)
    return ToolResult(
        tool="get_customer_credit_products",
        ok=True,
        data={"productos": productos, "n": len(productos)},
        grounded_values=(len(productos), *valores),
        ausencias=tuple(dict.fromkeys(ausencias)),
        source="noema_silver.stg_products",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4 · get_customer_assets
# ─────────────────────────────────────────────────────────────────────────────
def _get_customer_assets(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Cuentas e inversiones. Alimenta las reservas y la compensación de DTI.

    Separado del anterior aunque salga de la misma tabla: unos son obligaciones y
    otros reservas, y entran al cálculo por lados opuestos. Y un flujo de
    `PRODUCT_INFO` no necesita la posición financiera — mínima exposición.
    """
    filas = contexto.analitica.filas(
        """
        SELECT product_id, product_type, currency, current_balance
        FROM noema_silver.stg_products
        WHERE customer_id = ?
          AND product_status = ?
          AND product_type IN (?, ?, ?, ?)
        ORDER BY product_type, product_id
        """,
        (session.customer_id, ESTADO_VIGENTE, *TIPOS_ACTIVO),
    )
    activos: list[dict] = []
    ausencias: list[str] = []
    valores: list[float] = []
    for f in filas:
        try:
            saldo, tasa_fx = contexto.analitica.a_usd(
                f["current_balance"], f["currency"], contexto.corte
            )
        except ConversionImposible as exc:
            LOGGER.warning("activo_sin_conversion id=%s motivo=%s", f["product_id"], exc)
            ausencias.append(f"saldo_usd:{f['product_id']}")
            continue
        if saldo is None:
            ausencias.append(f"saldo_usd:{f['product_id']}")
        activos.append(
            {
                "producto_id": f["product_id"],
                "tipo": f["product_type"],
                "saldo_usd": saldo,
                "moneda_origen": f["currency"],
                "tasa_aplicada": tasa_fx,
            }
        )
        if saldo is not None:
            valores.append(saldo)
    return ToolResult(
        tool="get_customer_assets",
        ok=True,
        data={"activos": activos, "n": len(activos)},
        grounded_values=(len(activos), *valores),
        ausencias=tuple(dict.fromkeys(ausencias)),
        source="noema_silver.stg_products",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Registro
# ─────────────────────────────────────────────────────────────────────────────
def _get_customer_product_summary(
    session: Session, params, contexto: Contexto, idempotency_key
) -> ToolResult:
    """Lo que el cliente pregunta por sus productos: saldo, límite, tasa, cuota.

    Sale de la misma lectura de `get_customer_credit_products`, así que no hay una segunda
    consulta que pueda divergir. Dos cuidados:

    - La **cuota de un préstamo es una estimación**. La base no registra ni la cuota ni el
      plazo original; la política usa un plazo supuesto por producto y la misma fórmula, y
      el resumen lo declara. Se calcula igual que la carga de la política.
    - La **tarjeta** se muestra con su pago mínimo, que es lo que la política también
      cobra: no es una cuota de amortización.
    """
    base = _get_customer_credit_products(session, None, contexto, None)
    if not base.ok:
        return base
    politica = contexto.politica
    productos: list[dict] = []
    valores: list[Any] = [base.data["n"]]
    ausencias = list(base.ausencias)
    for p in base.data["productos"]:
        tipo = p["tipo"]
        saldo, limite, tasa = p["saldo_usd"], p["limite_usd"], p["tasa_anual"]
        modalidad = politica.amortizacion.get(tipo) if politica is not None else None
        fila: dict[str, Any] = {
            "tipo": tipo,
            "modalidad": modalidad,
            "saldo_usd": saldo,
            "limite_usd": limite,
            "tasa_anual": tasa,
            "cuota_estimada_usd": None,
            "plazo_supuesto_meses": None,
            "pago_minimo_usd": None,
        }
        if modalidad == "revolvente":
            if saldo is not None:
                fila["pago_minimo_usd"] = round(
                    max(saldo * politica.pago_minimo_pct, politica.pago_minimo_piso), 2
                )
                valores.append(fila["pago_minimo_usd"])
        elif politica is not None and limite is not None and tasa is not None:
            plazo = int(politica.plazos.get(tipo, 48))
            fila["plazo_supuesto_meses"] = plazo
            fila["cuota_estimada_usd"] = round(cuota_francesa(limite, tasa, plazo), 2)
            valores.extend([plazo, fila["cuota_estimada_usd"]])
        if saldo is not None:
            valores.append(saldo)
        if limite is not None:
            valores.append(limite)
        if tasa is not None:
            valores.append(tasa)
        productos.append(fila)
    return ToolResult(
        tool="get_customer_product_summary",
        ok=True,
        data={"productos": productos, "n": len(productos)},
        grounded_values=tuple(valores),
        ausencias=tuple(dict.fromkeys(ausencias)),
        source="noema_silver.stg_products",
    )


def registrar(registry=REGISTRY) -> None:
    """Registra las cuatro. Idempotente por `nombres()`, para poder llamarla en tests."""
    ya = set(registry.nombres())

    if "verify_identity" not in ya:
        registry.register(
            ToolSpec(
                name="verify_identity",
                module="customer",
                descripcion=(
                    "Verifica la identidad del cliente con tipo y número de documento más "
                    "fecha de nacimiento. El teléfono no es factor."
                ),
                handler=_verify_identity,
                params=(
                    Param(
                        "document_type",
                        str,
                        valida=lambda v: None if v in TIPOS_DOCUMENTO else "tipo desconocido",
                    ),
                    Param(
                        "document_number",
                        str,
                        valida=lambda v: None if 3 <= len(v.strip()) <= 40 else "largo inválido",
                    ),
                    Param(
                        "date_of_birth",
                        str,
                        valida=lambda v: (
                            None if len(v) == 10 and v[4] == v[7] == "-" else "AAAA-MM-DD"
                        ),
                    ),
                ),
                # Es el único tool que corre sin sesión: es el que la hace posible.
                requires_auth=False,
                writes=False,
                allowed_roles=frozenset({Role.ANONYMOUS, Role.CUSTOMER}),
                source="noema_silver.stg_customers",
            )
        )

    comunes = dict(
        module="customer",
        requires_auth=True,
        writes=False,
        allowed_roles=frozenset({Role.CUSTOMER, Role.HUMAN_AGENT, Role.EVAL_HARNESS}),
        source="noema_silver.stg_products",
    )
    if "get_customer_profile" not in ya:
        registry.register(
            ToolSpec(
                name="get_customer_profile",
                descripcion="Ingreso mensual en USD, segmento y antigüedad del cliente.",
                handler=_get_customer_profile,
                **{**comunes, "source": "noema_silver.stg_customers"},
            )
        )
    if "get_customer_credit_products" not in ya:
        registry.register(
            ToolSpec(
                name="get_customer_credit_products",
                descripcion="Productos de crédito vigentes, con límite y saldo en USD.",
                handler=_get_customer_credit_products,
                **comunes,
            )
        )
    if "get_customer_product_summary" not in ya:
        registry.register(
            ToolSpec(
                name="get_customer_product_summary",
                descripcion=(
                    "Resumen de los productos de crédito del cliente: saldo, límite, tasa y "
                    "cuota estimada (o pago mínimo en tarjeta), en USD."
                ),
                handler=_get_customer_product_summary,
                **comunes,
            )
        )
    if "get_customer_assets" not in ya:
        registry.register(
            ToolSpec(
                name="get_customer_assets",
                descripcion="Cuentas e inversiones vigentes, con saldo en USD.",
                handler=_get_customer_assets,
                **comunes,
            )
        )
