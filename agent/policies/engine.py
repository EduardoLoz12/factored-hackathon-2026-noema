"""Motor de elegibilidad — AG-02.

Lee `eligibility_v1.yaml` y lo evalúa. Determinista, sin LLM, sin modelo de
riesgo. Toda cifra que produce es trazable a un insumo o a un umbral de la
política, para que el GroundingChecker pueda validarla.

Por qué una política y no un modelo: ver `docs/knowledge/findings.md`, F-027 a
F-034. La decisión de suscripción no está codificada en este dataset.

Uso:
    from agent.policies.engine import Politica, Cliente, ProductoVigente

    politica = Politica.cargar()
    decision = politica.evaluar(cliente)
    decision.productos_elegibles  # lista con monto máximo por producto
    decision.motivos              # por qué se denegó lo que se denegó
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

RUTA_POLITICA = Path(__file__).with_name("eligibility_v1.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# Aritmética financiera
# ─────────────────────────────────────────────────────────────────────────────
def cifra(valor: float, decimales: int = 0) -> str:
    """Número con la convención hispanohablante y lusófona: punto para los miles, coma
    para los decimales.

    `{:,.0f}` de Python produce «1,200», que en es-CO, es-AR, es-MX y pt-BR se lee *uno
    coma dos*. En un agente bancario regional eso no es cosmético: el cliente puede leer
    **mil veces menos** de lo que se le está diciendo, y «tus cuotas actuales de 1,200
    USD» pasa a sonar asumible (F-045).

    Las dos lenguas del proyecto comparten esta convención, así que no hace falta
    ramificar por idioma.
    """
    texto = f"{valor:,.{decimales}f}"
    # Intercambio en un paso con un centinela: sustituir uno y después el otro pisaría
    # lo ya sustituido y dejaría todo con el mismo símbolo.
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def cuota_francesa(principal: float, tasa_anual_pct: float, meses: int) -> float:
    """Cuota de una amortización francesa. Lanza si algún insumo es inválido."""
    if principal <= 0:
        raise ValueError(f"principal no positivo: {principal}")
    if meses <= 0:
        raise ValueError(f"plazo no positivo: {meses}")
    i = tasa_anual_pct / 100.0 / 12.0
    if i <= 0:
        return principal / meses
    f = (1.0 + i) ** meses
    return principal * i * f / (f - 1.0)


def principal_maximo(cuota_disponible: float, tasa_anual_pct: float, meses: int) -> float:
    """Inversa: cuánto principal cabe en una cuota dada."""
    if cuota_disponible <= 0 or meses <= 0:
        return 0.0
    i = tasa_anual_pct / 100.0 / 12.0
    if i <= 0:
        return cuota_disponible * meses
    f = (1.0 + i) ** meses
    return cuota_disponible * (f - 1.0) / (i * f)


def tea_desde_nominal(tasa_anual_pct: float) -> float:
    """Tasa efectiva anual de una nominal con capitalización mensual.

    El motor amortiza con i = tasa_anual / 100 / 12, así que la tasa declarada es
    nominal mensualmente capitalizable y la efectiva es (1 + i)^12 − 1.

    **No depende del plazo.** Por eso ofrecer el mismo producto a varios plazos no
    cambia su costo anual efectivo: mueve la cuota, el monto que cabe en el margen
    y el interés total, no la TEA.
    """
    i = tasa_anual_pct / 100.0 / 12.0
    if i <= 0:
        return 0.0
    return ((1.0 + i) ** 12 - 1.0) * 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Entrada
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ProductoVigente:
    """Un producto de crédito que el cliente ya tiene, al corte."""

    tipo: str
    limite_usd: float | None
    tasa_anual: float | None
    apertura: date
    vencimiento: date | None = None
    ultima_transaccion_real: date | None = None
    cuotas_pagadas: int | None = None
    # Saldo dispuesto al corte. None significa que no se conoce, y entonces se
    # asume la línea completa: el criterio conservador. Va al final para no
    # alterar el orden posicional de los campos anteriores.
    saldo_usd: float | None = None
    # Identificador del producto. Sin él no se puede aparear el resultado de
    # `get_last_real_activity` —que es por producto— ni distinguir dos tarjetas del
    # mismo cliente en la respuesta. Hueco que ADR-0009 dejó abierto.
    producto_id: str | None = None

    def madurez_meses(self, corte: date) -> int:
        """Meses desde la apertura hasta el corte. 100 % de cobertura."""
        return max(0, (corte.year - self.apertura.year) * 12 + corte.month - self.apertura.month)

    def inactivo(self, corte: date, dias: int = 180) -> bool:
        if self.ultima_transaccion_real is None:
            return True
        return (corte - self.ultima_transaccion_real).days > dias


@dataclass(frozen=True)
class ProductoDeAhorro:
    """Cuenta, inversión o cualquier producto que aporte saldo, no deuda."""

    tipo: str
    saldo_usd: float | None


@dataclass(frozen=True)
class Cliente:
    customer_id: str
    ingreso_mensual_usd: float | None
    segmento: str
    alta: date
    productos: tuple[ProductoVigente, ...] = ()
    ahorros: tuple[ProductoDeAhorro, ...] = ()
    capacidad_estimada_usd: float | None = None  # ML-04; None = se abstuvo

    def antiguedad_meses(self, corte: date) -> int:
        return max(0, (corte.year - self.alta.year) * 12 + corte.month - self.alta.month)


# ─────────────────────────────────────────────────────────────────────────────
# Salida
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Oferta:
    producto: str
    # Techo: lo máximo que la política admite a este plazo.
    monto_maximo_usd: float
    # Lo que realmente se cotiza: el techo, o lo que el cliente pidió si pidió
    # menos. La cuota y el interés total corresponden a ESTE monto, no al techo.
    monto_ofrecido_usd: float
    cuota_estimada_usd: float
    tasa_anual: float
    plazo_meses: int
    # Costo anual efectivo, idéntico para todos los plazos del mismo producto.
    tea_pct: float = 0.0
    # Interés total de la amortización. None en revolvente: una línea no tiene un
    # total que devolver. Sin esta cifra, un plazo más largo parece gratis.
    intereses_totales_usd: float | None = None


@dataclass
class Decision:
    customer_id: str
    elegible: bool
    abstencion: bool
    productos_elegibles: list[Oferta] = field(default_factory=list)
    motivos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    hechos: dict[str, Any] = field(default_factory=dict)
    politica_version: int = 1

    def a_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "elegible": self.elegible,
            "abstencion": self.abstencion,
            "politica_version": self.politica_version,
            "hechos": self.hechos,
            "productos_elegibles": [vars(o) for o in self.productos_elegibles],
            "motivos": self.motivos,
            "avisos": self.avisos,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Motor
# ─────────────────────────────────────────────────────────────────────────────
class Politica:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.u = cfg["umbrales"]
        self.catalogo = cfg["catalogo"]
        self.plazos = cfg["plazos_supuestos"]
        self.amortizacion = cfg.get("amortizacion_vigentes", {})
        self.pago_minimo_pct = float(cfg.get("pago_minimo_revolvente", 0.05))
        self.pago_minimo_piso = float(cfg.get("pago_minimo_piso_usd", 0.0))
        self.estres_no_dispuesta = float(cfg.get("estres_linea_no_dispuesta", 0.0))
        act = cfg.get("activos", {}) or {}
        self.act_liquidos = set(act.get("liquidos", []))
        self.act_semiliquidos = dict(act.get("semiliquidos", {}) or {})
        self.reservas_minimas = dict(act.get("reservas_minimas_meses", {}) or {})
        comp = act.get("compensacion", {}) or {}
        self.comp_reservas_meses = float(comp.get("reservas_meses_minimas", 0) or 0)
        self.comp_dti_ampliado = float(
            comp.get("dti_maximo_ampliado", cfg["umbrales"]["dti_maximo"])
        )
        sc = cfg.get("sin_capacidad_observada", {}) or {}
        self.sc_factor = float(sc.get("factor_margen", 1.0))
        self.sc_excluidos = set(sc.get("productos_excluidos", []) or [])
        self.sc_mensaje = str(sc.get("mensaje", "")).strip()
        self.corte = date.fromisoformat(str(cfg["corte_datos"]))
        self.version = int(cfg["version"])

    @classmethod
    def cargar(cls, ruta: Path = RUTA_POLITICA) -> Politica:
        with ruta.open(encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh))

    def _plazos_ofertables(self, item: dict[str, Any]) -> list[int]:
        """Plazos a los que se ofrece un producto, de menor a mayor.

        El último es el más largo, y es el que más ayuda en las dos pruebas por
        producto: baja la cuota (menos reserva exigida) y sube el monto que cabe
        (alcanza el mínimo). Por eso el motivo de rechazo lo cita a él.

        Acepta el `plazo_meses` único de la versión 1 como un solo plazo, para que
        una política anterior siga evaluándose sin cambios.
        """
        crudo = item.get("plazos_ofertables")
        if crudo is None:
            crudo = [item["plazo_meses"]]
        plazos = sorted({int(x) for x in crudo})
        if not plazos or plazos[0] < 1:
            raise ValueError(f"{item['producto']}: plazos ofertables inválidos")
        return plazos

    # ── plazo de un producto vigente ────────────────────────────────────────
    def _plazo_total(self, p: ProductoVigente) -> int:
        """Plazo ORIGINAL del producto, en meses.

        La cuota de un préstamo es constante durante toda su vida: se calcula
        sobre el plazo total, nunca sobre el remanente. Amortizar el principal
        completo sobre lo que queda infla la cuota hasta valores imposibles.
        """
        if p.vencimiento is not None and p.vencimiento > p.apertura:
            meses = (
                (p.vencimiento.year - p.apertura.year) * 12 + p.vencimiento.month - p.apertura.month
            )
            if meses > 0:
                return meses
        return max(1, int(self.plazos.get(p.tipo, 48)))

    def _plazo_remanente(self, p: ProductoVigente) -> int:
        """Meses que le quedan. Cero significa amortizado: ya no pesa en el DTI."""
        return max(0, self._plazo_total(p) - p.madurez_meses(self.corte))

    # ── reservas: la posición financiera del cliente ────────────────────────
    def _reservas(self, cliente: Cliente) -> tuple[float, list[str]]:
        """Activos disponibles en USD, con descuento en los semilíquidos."""
        total = 0.0
        avisos: list[str] = []
        for a in cliente.ahorros:
            if a.saldo_usd is None or a.saldo_usd <= 0:
                continue
            if a.tipo in self.act_liquidos:
                total += a.saldo_usd
            elif a.tipo in self.act_semiliquidos:
                total += a.saldo_usd * self.act_semiliquidos[a.tipo]
            else:
                avisos.append(f"El producto {a.tipo} no se computa como reserva.")
        return total, avisos

    # ── carga mensual comprometida ──────────────────────────────────────────
    def _carga(self, cliente: Cliente) -> tuple[float, float, list[str], list[str], float]:
        """Carga mensual, exposición, avisos y **lo que no se pudo valorar**.

        El cuarto valor existe porque antes no existía: un producto sin límite o sin
        tasa se saltaba con un aviso, y su obligación desaparecía del DTI y de la
        exposición. El cliente quedaba menos endeudado de lo que está y el sistema lo
        aprobaba — falla abierto, contra la regla 5. Afectaba al 19.59 % de los
        clientes con crédito (F-041).
        """
        carga = exposicion = dispuesto_total = 0.0
        avisos: list[str] = []
        no_valorables: list[str] = []
        for p in cliente.productos:
            if p.limite_usd is None or p.tasa_anual is None:
                falta = "el límite" if p.limite_usd is None else "la tasa"
                no_valorables.append(p.producto_id or p.tipo)
                avisos.append(f"Falta {falta} del producto {p.tipo}.")
                continue
            exposicion += p.limite_usd
            try:
                if self.amortizacion.get(p.tipo) == "revolvente":
                    # Una tarjeta no amortiza la línea: paga el mínimo sobre lo
                    # DISPUESTO. Si no se conoce el saldo, se asume la línea
                    # completa, que es el criterio conservador.
                    dispuesto = p.saldo_usd if p.saldo_usd is not None else p.limite_usd
                    dispuesto = max(0.0, min(dispuesto, p.limite_usd))
                    dispuesto_total += dispuesto
                    if dispuesto > 0:
                        carga += max(dispuesto * self.pago_minimo_pct, self.pago_minimo_piso)
                    # La línea disponible es deuda que puede tomar mañana.
                    no_dispuesta = max(0.0, p.limite_usd - dispuesto)
                    carga += no_dispuesta * self.pago_minimo_pct * self.estres_no_dispuesta
                elif self._plazo_remanente(p) <= 0:
                    # Préstamo ya amortizado bajo el plazo supuesto: no pesa.
                    avisos.append(
                        f"El préstamo {p.tipo} ya habría vencido bajo el plazo "
                        f"supuesto de {self._plazo_total(p)} meses; no se computa "
                        f"en tu carga actual."
                    )
                else:
                    # Cuota constante sobre el plazo TOTAL, no el remanente.
                    carga += cuota_francesa(p.limite_usd, p.tasa_anual, self._plazo_total(p))
                    # En un préstamo lo dispuesto es el principal concedido.
                    dispuesto_total += p.saldo_usd if p.saldo_usd is not None else p.limite_usd
            except ValueError as exc:  # nunca tumbar la evaluación por un producto
                avisos.append(f"No se pudo calcular la cuota de {p.tipo}: {exc}")
            if p.inactivo(self.corte):
                avisos.append(f"El producto {p.tipo} no registra movimientos recientes.")
        return carga, exposicion, avisos, no_valorables, dispuesto_total

    # ── evaluación ──────────────────────────────────────────────────────────
    def evaluar(self, cliente: Cliente, monto_pedido_usd: float | None = None) -> Decision:
        """Evalúa la elegibilidad. `monto_pedido_usd` ya viene convertido a USD.

        Sin monto pedido, cada plazo cotiza su techo y las tres opciones difieren en
        monto e interés total, con la misma cuota —la que agota el margen—. Con
        monto pedido, las tres cotizan ese monto y difieren en **cuota**: eso es
        elegir por capacidad de pago, que es para lo que existen los plazos.
        """
        d = Decision(
            customer_id=cliente.customer_id,
            elegible=False,
            abstencion=False,
            politica_version=self.version,
        )

        # Declaración permanente: este sistema no determina mora.
        d.avisos.append(
            "Esta evaluación no considera estado de mora, porque la información "
            "disponible no permite determinarlo de forma fiable."
        )

        if cliente.ingreso_mensual_usd is None or cliente.ingreso_mensual_usd <= 0:
            d.abstencion = True
            d.motivos.append(
                "No tenemos registrado un ingreso para evaluar tu solicitud. "
                "Un asesor puede ayudarte a actualizarlo."
            )
            return d

        if monto_pedido_usd is not None and (
            isinstance(monto_pedido_usd, bool)
            or not math.isfinite(monto_pedido_usd)
            or monto_pedido_usd <= 0
        ):
            d.abstencion = True
            d.motivos.append("No entendimos el monto que necesitas. Un asesor puede ayudarte.")
            return d

        carga, exposicion, avisos, no_valorables, dispuesto = self._carga(cliente)
        d.avisos.extend(avisos)

        # Abstención `sin_exposicion_valorable` del YAML, que bloquea. Si no se puede
        # valorar una obligación, NO se puede calcular el DTI: aprobar con la deuda
        # incompleta sería aprobar sobre una cifra que sabemos falsa.
        if no_valorables:
            d.abstencion = True
            d.hechos = {
                "n_productos_credito": len(cliente.productos),
                "productos_no_valorables": len(no_valorables),
                "corte": self.corte.isoformat(),
            }
            d.motivos.append(
                "No podemos calcular tu carga actual porque falta información de uno "
                "de tus productos. Lo derivamos a un asesor."
            )
            return d

        reservas, avisos_act = self._reservas(cliente)
        d.avisos.extend(avisos_act)

        ingreso = cliente.ingreso_mensual_usd
        dti = carga / ingreso

        # Factor compensatorio: con reservas holgadas se admite algo más de carga.
        # Las reservas se miden en meses de la CARGA ACTUAL; sin carga no aplica.
        # Sin carga no hay nada que compensar, y sin reservas no hay con qué.
        reservas_meses_carga = (reservas / carga) if carga > 0 else 0.0
        tope_dti = self.u["dti_maximo"]
        if (
            self.comp_reservas_meses > 0
            and carga > 0
            and reservas > 0
            and reservas_meses_carga >= self.comp_reservas_meses
            and self.comp_dti_ampliado > tope_dti
        ):
            tope_dti = self.comp_dti_ampliado
            d.avisos.append(
                f"Tus reservas cubren {reservas_meses_carga:.0f} meses de tus cuotas "
                f"actuales, así que evaluamos con un tope de {tope_dti:.0%} en lugar "
                f"de {self.u['dti_maximo']:.0%}."
            )

        margen = max(0.0, tope_dti * ingreso - carga)
        n_credito = len(cliente.productos)
        antiguedad = cliente.antiguedad_meses(self.corte)

        # La capacidad de ML-04 solo puede restringir, nunca ampliar.
        #
        # Y su AUSENCIA también restringe. Antes se usaba el margen completo, que
        # trataba la falta de información como falta de restricción: el dato que no
        # está caía a favor del solicitante, igual que en F-041. Sin flujo observado
        # el sistema no sabe cuánto sostiene el cliente, solo cuánto cabe en una
        # aritmética que no pudo cruzar contra nada.
        sin_capacidad = cliente.capacidad_estimada_usd is None
        if not sin_capacidad:
            margen = min(margen, cliente.capacidad_estimada_usd)
        else:
            margen *= self.sc_factor
            d.avisos.append(
                "No se incorporó una capacidad de pago observada: el estimador "
                "no tenía historial suficiente."
            )
            if self.sc_mensaje:
                d.avisos.append(self.sc_mensaje)

        d.hechos = {
            "ingreso_mensual_usd": round(ingreso, 2),
            "n_productos_credito": n_credito,
            "exposicion_usd": round(exposicion, 2),
            "carga_mensual_usd": round(carga, 2),
            "dti_actual": round(dti, 4),
            "margen_mensual_usd": round(margen, 2),
            "antiguedad_cliente_meses": antiguedad,
            "reservas_usd": round(reservas, 2),
            "tope_dti_aplicado": tope_dti,
            # Las dos cifras derivadas que los motivos y avisos pronuncian. Van en
            # `hechos` porque el GroundingChecker (AG-09) valida contra este dict:
            # una cifra que el motor dice y no publica aqui seria huerfana y
            # bloquearia una respuesta correcta.
            "reservas_meses_carga": round(reservas_meses_carga, 2),
            # Posición neta al corte: reservas menos lo dispuesto. Es un hecho
            # declarado, NO una regla — no hay umbral de patrimonio en esta versión.
            "saldo_dispuesto_usd": round(dispuesto, 2),
            "patrimonio_neto_usd": round(reservas - dispuesto, 2),
            "capacidad_observada": not sin_capacidad,
            "veces_ingreso_exposicion": round(exposicion / (ingreso * 12), 4),
            "corte": self.corte.isoformat(),
        }
        if monto_pedido_usd is not None:
            d.hechos["monto_pedido_usd"] = round(float(monto_pedido_usd), 2)

        # ── reglas, en orden. La primera que falla decide ────────────────────
        if n_credito >= 1 and antiguedad < self.u["antiguedad_minima_meses"]:
            d.motivos.append(
                f"Tu relación con el banco es de {antiguedad} meses y pedimos al "
                f"menos {self.u['antiguedad_minima_meses']} para un producto adicional."
            )
            return d

        if n_credito >= self.u["max_productos_credito"]:
            d.motivos.append(
                f"Ya tienes {n_credito} productos de crédito activos y el máximo "
                f"es {self.u['max_productos_credito']}."
            )
            return d

        if dti >= self.u["dti_corte_duro"]:
            d.motivos.append(
                f"Tus cuotas comprometidas son el {dti:.0%} de tu ingreso mensual, "
                f"por encima del límite de {self.u['dti_corte_duro']:.0%}."
            )
            return d

        tope_exposicion = self.u["exposicion_maxima_sobre_ingreso_anual"] * ingreso * 12
        if exposicion > tope_exposicion:
            d.motivos.append(
                f"El crédito que ya tienes concedido equivale a "
                f"{cifra(exposicion / (ingreso * 12), 1)} veces tu ingreso anual y el tope "
                f"es {cifra(self.u['exposicion_maxima_sobre_ingreso_anual'], 1)}."
            )
            return d

        if margen <= 0:
            d.motivos.append(
                f"Con tus cuotas actuales de {cifra(carga)} USD no queda margen bajo "
                f"el tope de {tope_dti:.0%} de tu ingreso."
            )
            return d

        # ── qué producto y a qué plazo cabe en el margen ─────────────────────
        # Versión 2: cada producto se ofrece a los plazos de `plazos_ofertables`.
        # El plazo no cambia la TEA; cambia la cuota, el monto que cabe, la reserva
        # exigida y el interés total. Un producto se rechaza solo si NINGÚN plazo
        # pasa, y entonces el motivo cita el plazo más largo — el que más ayuda en
        # ambas pruebas. Eso convierte en oferta lo que antes era un rechazo.
        #
        # Toda cifra que se pronuncie por producto queda publicada en
        # `hechos["evaluacion_por_producto"]`, incluidos los RECHAZADOS: `Oferta`
        # solo se crea para los aceptados, así que sin este registro el
        # GroundingChecker (AG-09) bloquearía un rechazo correctamente explicado.
        evaluacion: dict[str, Any] = {}
        for item in self.catalogo:
            if cliente.segmento not in item["segmentos"]:
                continue
            if sin_capacidad and item["producto"] in self.sc_excluidos:
                # Comprometer el plazo más largo del catálogo sin haber visto el flujo
                # del cliente es justo lo que no se debe hacer. Se dice por qué.
                d.motivos.append(
                    f"{item['producto']}: no lo ofrecemos sin haber verificado tu flujo "
                    f"de ingresos reciente, porque es el compromiso de plazo más largo."
                )
                continue
            revolvente = item.get("amortizacion") == "revolvente"
            meses_exigidos = float(self.reservas_minimas.get(item["producto"], 0) or 0)
            minimo = float(item["monto_minimo_usd"])
            tope = float(item["monto_maximo_usd"])
            tea = round(tea_desde_nominal(float(item["tasa_anual"])), 2)
            plazos = self._plazos_ofertables(item)

            # Pedir menos que el mínimo del producto no depende del plazo, así que
            # se resuelve antes de recorrerlos.
            if monto_pedido_usd is not None and monto_pedido_usd < minimo:
                evaluacion[item["producto"]] = {
                    "tasa_anual": float(item["tasa_anual"]),
                    "tea_pct": tea,
                    "monto_minimo_usd": minimo,
                    "monto_maximo_catalogo_usd": tope,
                    "reservas_exigidas_meses": meses_exigidos,
                    "plazos_ofertables": [int(x) for x in plazos],
                    "opciones": {},
                }
                d.motivos.append(
                    f"{item['producto']}: pediste {cifra(monto_pedido_usd)} USD y el mínimo "
                    f"de este producto es {cifra(minimo)} USD."
                )
                continue

            opciones: dict[str, dict[str, float | None]] = {}
            aceptadas: list[Oferta] = []
            mas_largo: dict[str, float] = {}

            for plazo in plazos:
                if revolvente:
                    # Línea que cabe en el margen si se paga el mínimo sobre ella.
                    techo = margen / self.pago_minimo_pct
                else:
                    techo = principal_maximo(margen, item["tasa_anual"], plazo)
                techo = min(techo, tope)
                # Se cotiza lo pedido cuando cabe; el techo cuando no se pidió nada.
                ofrecido = techo if monto_pedido_usd is None else min(monto_pedido_usd, techo)
                cuota = (
                    ofrecido * self.pago_minimo_pct
                    if revolvente
                    else cuota_francesa(max(ofrecido, 1.0), item["tasa_anual"], plazo)
                )
                # La reserva se exige contra la cuota que se va a cobrar, no contra
                # la del techo: quien pide menos compromete menos.
                exigido = cuota * meses_exigidos
                # El interés total solo existe en amortización cerrada: una línea
                # revolvente no tiene un total que devolver.
                intereses = None if revolvente else max(0.0, cuota * plazo - ofrecido)
                opciones[str(plazo)] = {
                    "monto_maximo_usd": round(techo, 2),
                    "monto_ofrecido_usd": round(ofrecido, 2),
                    "cuota_propuesta_usd": round(cuota, 2),
                    "reservas_exigidas_usd": round(exigido, 2),
                    "intereses_totales_usd": None if intereses is None else round(intereses, 2),
                }
                # Los plazos vienen ordenados: al salir del bucle esto guarda el más
                # largo, el mejor caso con el que explicar un rechazo.
                mas_largo = {"plazo": plazo, "techo": techo, "exigido": exigido}

                if meses_exigidos > 0 and reservas < exigido:
                    continue
                if ofrecido < minimo:
                    continue
                aceptadas.append(
                    Oferta(
                        producto=item["producto"],
                        monto_maximo_usd=round(techo, 2),
                        monto_ofrecido_usd=round(ofrecido, 2),
                        cuota_estimada_usd=round(cuota, 2),
                        tasa_anual=item["tasa_anual"],
                        plazo_meses=int(plazo),
                        tea_pct=tea,
                        intereses_totales_usd=(None if intereses is None else round(intereses, 2)),
                    )
                )

            evaluacion[item["producto"]] = {
                "tasa_anual": float(item["tasa_anual"]),
                "tea_pct": tea,
                "monto_minimo_usd": minimo,
                "monto_maximo_catalogo_usd": tope,
                "reservas_exigidas_meses": meses_exigidos,
                "plazos_ofertables": [int(x) for x in plazos],
                "opciones": opciones,
            }

            if aceptadas:
                d.productos_elegibles.extend(aceptadas)
                # Si se cotizó menos de lo pedido, se dice. Cotizar 178 000 ante una
                # petición de 400 000 sin declararlo dejaría al cliente creyendo que
                # recibió lo que pidió.
                if monto_pedido_usd is not None:
                    recortadas = [
                        o for o in aceptadas if o.monto_ofrecido_usd < monto_pedido_usd - 0.005
                    ]
                    if len(recortadas) == len(aceptadas):
                        mejor = max(o.monto_ofrecido_usd for o in recortadas)
                        d.avisos.append(
                            f"{item['producto']}: pediste {cifra(monto_pedido_usd)} USD y con tu "
                            f"capacidad actual podemos ofrecerte hasta {cifra(mejor)} USD."
                        )
                continue

            # Ningún plazo pasó. El motivo cita el más largo y dice que lo es, para
            # que el cliente sepa que no queda plazo al que recurrir.
            prefijo = (
                f"{item['producto']}: incluso a {mas_largo['plazo']:.0f} meses, el plazo "
                f"más largo que ofrecemos, "
                if len(plazos) > 1
                else f"{item['producto']}: "
            )
            if meses_exigidos > 0 and reservas < mas_largo["exigido"]:
                d.motivos.append(
                    f"{prefijo}pedimos reservas por {meses_exigidos:.0f} meses de cuota "
                    f"({cifra(mas_largo['exigido'])} USD) y registramos {cifra(reservas)} USD "
                    f"en tus cuentas e inversiones."
                )
            elif monto_pedido_usd is not None:
                d.motivos.append(
                    f"{prefijo}podrías asumir hasta {cifra(mas_largo['techo'])} USD, menos "
                    f"de los {cifra(monto_pedido_usd)} USD que pediste."
                )
            else:
                d.motivos.append(
                    f"{prefijo}podrías asumir hasta {cifra(mas_largo['techo'])} USD, por "
                    f"debajo del mínimo de {cifra(minimo)} USD."
                )

        d.hechos["evaluacion_por_producto"] = evaluacion

        d.elegible = bool(d.productos_elegibles)
        if not d.elegible and not d.motivos:
            d.motivos.append("Ningún producto del catálogo está disponible para tu perfil.")
        return d
