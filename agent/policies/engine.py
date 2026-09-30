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

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

RUTA_POLITICA = Path(__file__).with_name("eligibility_v1.yaml")


# ─────────────────────────────────────────────────────────────────────────────
# Aritmética financiera
# ─────────────────────────────────────────────────────────────────────────────
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
    monto_maximo_usd: float
    cuota_estimada_usd: float
    tasa_anual: float
    plazo_meses: int


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
        self.corte = date.fromisoformat(str(cfg["corte_datos"]))
        self.version = int(cfg["version"])

    @classmethod
    def cargar(cls, ruta: Path = RUTA_POLITICA) -> Politica:
        with ruta.open(encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh))

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
    def _carga(self, cliente: Cliente) -> tuple[float, float, list[str]]:
        carga = exposicion = 0.0
        avisos: list[str] = []
        for p in cliente.productos:
            if p.limite_usd is None or p.tasa_anual is None:
                avisos.append(f"Falta información del producto {p.tipo}.")
                continue
            exposicion += p.limite_usd
            try:
                if self.amortizacion.get(p.tipo) == "revolvente":
                    # Una tarjeta no amortiza la línea: paga el mínimo sobre lo
                    # DISPUESTO. Si no se conoce el saldo, se asume la línea
                    # completa, que es el criterio conservador.
                    dispuesto = p.saldo_usd if p.saldo_usd is not None else p.limite_usd
                    dispuesto = max(0.0, min(dispuesto, p.limite_usd))
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
            except ValueError as exc:  # nunca tumbar la evaluación por un producto
                avisos.append(f"No se pudo calcular la cuota de {p.tipo}: {exc}")
            if p.inactivo(self.corte):
                avisos.append(f"El producto {p.tipo} no registra movimientos recientes.")
        return carga, exposicion, avisos

    # ── evaluación ──────────────────────────────────────────────────────────
    def evaluar(self, cliente: Cliente) -> Decision:
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

        carga, exposicion, avisos = self._carga(cliente)
        d.avisos.extend(avisos)
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
        if cliente.capacidad_estimada_usd is not None:
            margen = min(margen, cliente.capacidad_estimada_usd)
        else:
            d.avisos.append(
                "No se incorporó una capacidad de pago observada: el estimador "
                "no tenía historial suficiente."
            )

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
            "corte": self.corte.isoformat(),
        }

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
                f"{exposicion / (ingreso * 12):.1f} veces tu ingreso anual y el tope "
                f"es {self.u['exposicion_maxima_sobre_ingreso_anual']:.1f}."
            )
            return d

        if margen <= 0:
            d.motivos.append(
                f"Con tus cuotas actuales de {carga:,.0f} USD no queda margen bajo "
                f"el tope de {tope_dti:.0%} de tu ingreso."
            )
            return d

        # ── qué producto cabe en el margen ───────────────────────────────────
        for item in self.catalogo:
            if cliente.segmento not in item["segmentos"]:
                continue
            if item.get("amortizacion") == "revolvente":
                # Línea que cabe en el margen si se paga el mínimo sobre ella.
                monto = margen / self.pago_minimo_pct
            else:
                monto = principal_maximo(margen, item["tasa_anual"], item["plazo_meses"])
            monto = min(monto, float(item["monto_maximo_usd"]))
            # Reservas mínimas: meses de la cuota propuesta que debe cubrir.
            meses_exigidos = float(self.reservas_minimas.get(item["producto"], 0) or 0)
            if meses_exigidos > 0:
                cuota_propuesta = (
                    monto * self.pago_minimo_pct
                    if item.get("amortizacion") == "revolvente"
                    else cuota_francesa(max(monto, 1.0), item["tasa_anual"], item["plazo_meses"])
                )
                exigido = cuota_propuesta * meses_exigidos
                if reservas < exigido:
                    d.motivos.append(
                        f"{item['producto']}: pedimos reservas por "
                        f"{meses_exigidos:.0f} meses de cuota ({exigido:,.0f} USD) y "
                        f"registramos {reservas:,.0f} USD en tus cuentas e inversiones."
                    )
                    continue
            if monto < item["monto_minimo_usd"]:
                d.motivos.append(
                    f"{item['producto']}: podrías asumir hasta {monto:,.0f} USD, "
                    f"por debajo del mínimo de {item['monto_minimo_usd']:,.0f} USD."
                )
                continue
            d.productos_elegibles.append(
                Oferta(
                    producto=item["producto"],
                    monto_maximo_usd=round(monto, 2),
                    cuota_estimada_usd=round(
                        monto * self.pago_minimo_pct
                        if item.get("amortizacion") == "revolvente"
                        else cuota_francesa(monto, item["tasa_anual"], item["plazo_meses"]),
                        2,
                    ),
                    tasa_anual=item["tasa_anual"],
                    plazo_meses=item["plazo_meses"],
                )
            )

        d.elegible = bool(d.productos_elegibles)
        if not d.elegible and not d.motivos:
            d.motivos.append("Ningún producto del catálogo está disponible para tu perfil.")
        return d
