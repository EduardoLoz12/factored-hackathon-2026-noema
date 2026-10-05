"""El turno, evento a evento — lo que alimenta el panel de la derecha.

El panel mostraba siete tarjetas que aparecían de golpe. Eduardo pidió verlo **segundo
a segundo**, y con más detalle: de qué base sale cada dato, qué regla de la política se
evaluó, qué verificador de seguridad corrió. Esto arma esa lista.

El orden importa y es el real: el servidor sabe en qué secuencia ocurrieron las cosas,
así que la secuencia se arma acá y la interfaz solo la reproduce. Si la interfaz
inventara el orden, estaría contando una historia en vez de mostrar una traza.

Cada evento declara cuatro cosas, y ninguna es decorativa:

- **qué** pasó, en una línea que un juez entienda sin leer el código;
- **de dónde** salió — tabla, archivo de política, módulo del guardrail;
- **qué regla o control** se estaba aplicando, con su identificador;
- **cómo** terminó: cumplido, incumplido, se abstuvo, o no aplicaba.
"""

from __future__ import annotations

from typing import Any

# Qué tabla lee cada herramienta. Está acá y no en el tool porque es información
# para el panel, no para la ejecución; el tool ya declara su `source`.
TABLAS = {
    "verify_identity": "noema_silver.stg_customers",
    "get_customer_profile": "noema_silver.stg_customers",
    "get_customer_credit_products": "noema_silver.stg_products",
    "get_customer_assets": "noema_silver.stg_products",
    "get_payment_history": "noema_silver.stg_transactions",
    "get_last_real_activity": "noema_silver.stg_transactions",
    "get_product_catalog": "agent/policies/eligibility_v1.yaml",
    "evaluate_eligibility": "agent/policies/engine.py",
    "record_offer_quote": "ledger · action_ledger",
    "create_escalation_case": "ledger · cases",
    "get_escalation_case": "ledger · cases",
}

QUE_HACE = {
    "verify_identity": "Compara los tres factores contra la base",
    "get_customer_profile": "Lee ingreso, segmento y antigüedad",
    "get_customer_credit_products": "Lee los productos de crédito vigentes al corte",
    "get_customer_assets": "Lee cuentas e inversiones, que entran como reservas",
    "get_payment_history": "Cuenta los pagos observados por producto",
    "get_last_real_activity": "Busca la última transacción real de cada producto",
    "get_product_catalog": "Lee el catálogo y sus condiciones vigentes",
    "evaluate_eligibility": "Ejecuta la política sobre los hechos reunidos",
    "record_offer_quote": "Registra la cotización y la vuelve a leer",
    "create_escalation_case": "Abre el expediente para el asesor",
}

NOMBRE_REGLA = {
    "R1_antiguedad": "Antigüedad mínima como cliente",
    "R2_numero_de_productos": "Tope de productos de crédito activos",
    "R3_corte_duro_de_dti": "Corte duro de endeudamiento",
    "R4_exposicion_sobre_ingreso": "Exposición sobre el ingreso anual",
    "R5_margen_disponible": "Margen mensual bajo el tope de DTI",
    "R7_monto_minimo": "Monto mínimo del producto",
    "R8_segmento": "Producto disponible para el segmento",
}


def _ev(
    fase: str,
    titulo: str,
    *,
    detalle: str = "",
    fuente: str = "",
    control: str = "",
    estado: str = "ok",
    ms: float | None = None,
) -> dict[str, Any]:
    return {
        "fase": fase,
        "titulo": titulo,
        "detalle": detalle,
        "fuente": fuente,
        "control": control,
        "estado": estado,
        "ms": round(ms, 1) if ms is not None else None,
    }


def de_identidad(lectura: dict[str, Any], reunidos: list[str], faltan: list[str], r: Any) -> list:
    """El tramo de identidad, que ocurre antes de que exista sesión."""
    eventos = [
        _ev(
            "entrada",
            "Mensaje del cliente recibido",
            detalle=f"idioma detectado: {lectura['idioma']}",
            fuente="api/extraccion.py",
            control="detección de idioma",
        ),
        _ev(
            "identidad",
            "Lectura de los factores de identidad",
            detalle=("reunidos: " + (", ".join(reunidos) if reunidos else "ninguno todavía")),
            fuente="api/identidad.py",
            control="tres factores: tipo, número y fecha de nacimiento",
            estado="ok" if reunidos else "pe",
        ),
    ]
    if faltan:
        eventos.append(
            _ev(
                "identidad",
                "No se consulta nada todavía",
                detalle="faltan " + ", ".join(faltan),
                fuente="agent/core/access_guard.py",
                control="AG-05 · sin sesión no sale información personal",
                estado="pe",
            )
        )
        return eventos

    eventos.append(
        _ev(
            "identidad",
            "Verificación contra la base"
            if r is None
            else ("Identidad verificada" if r.verificado else "Los factores no coinciden"),
            detalle=(f"intentos restantes: {r.intentos_restantes}" if r is not None else ""),
            fuente="noema_silver.stg_customers",
            control="AG-05 · 3 intentos, espera creciente, JWT de 15 min",
            estado="ok" if (r is not None and r.verificado) else "no",
        )
    )
    return eventos


def del_turno(
    turno: Any,
    lectura: dict[str, Any],
    bitacora: list[dict[str, Any]],
    analisis_inyeccion: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """La secuencia completa de un turno con sesión verificada."""
    eventos: list[dict[str, Any]] = []
    d = turno.decision or {}
    hechos = d.get("hechos") or {}

    # 1 · El texto entra como dato, nunca como instrucción.
    sospechoso = bool((analisis_inyeccion or {}).get("sospechoso"))
    patrones = (analisis_inyeccion or {}).get("patrones") or []
    eventos.append(
        _ev(
            "entrada",
            "El mensaje se envuelve como dato, no como instrucción",
            detalle=(
                "patrones detectados: " + ", ".join(patrones)
                if patrones
                else "sin patrones de inyección"
            ),
            fuente="agent/guardrails/injection.py",
            control="AG-10 · contención con sello aleatorio por turno",
            estado="pe" if sospechoso else "ok",
        )
    )

    # 2 · Qué entendió, sin decidir nada.
    slots = sorted(lectura.get("slots") or {})
    eventos.append(
        _ev(
            "entrada",
            f"Intención: {lectura['intencion']}",
            detalle=("datos extraídos: " + ", ".join(slots)) if slots else "sin datos en el texto",
            fuente="api/extraccion.py",
            control="el modelo extrae, el orquestador decide",
        )
    )

    # 3 · Sesión.
    eventos.append(
        _ev(
            "identidad",
            "Sesión verificada",
            detalle="el identificador del cliente viaja dentro del token",
            fuente="agent/core/access_guard.py",
            control="AG-05 · permisos en código, no en el prompt",
        )
    )

    # 4 · Cada herramienta, con su tabla y su latencia.
    for x in bitacora:
        nombre = x["tool"]
        eventos.append(
            _ev(
                "escritura" if x["escribe"] else "consulta",
                QUE_HACE.get(nombre, nombre),
                detalle=(
                    x["error"]
                    if x["error"]
                    else (
                        f"{x['cifras']} cifras publicadas"
                        + (" · releída tras escribir" if x["escribe"] else "")
                    )
                ),
                fuente=TABLAS.get(nombre, x.get("fuente") or "—"),
                control=f"AG-03 · {nombre}, permitido para este rol",
                estado="no" if x["error"] else "ok",
                ms=x["ms"],
            )
        )

    # 5 · Las reglas de la política, una por una.
    reglas = hechos.get("reglas") or []
    for r in reglas:
        aplica = r.get("aplica", True)
        cumple = r.get("cumple", True)
        eventos.append(
            _ev(
                "politica",
                NOMBRE_REGLA.get(r["id"], r["id"]),
                detalle=r.get("exige", ""),
                fuente=f"eligibility_v1.yaml v{d.get('politica_version')} · {r['id']}",
                control="AG-02 · la elegibilidad la calcula la política, no el modelo",
                estado="ok" if (aplica and cumple) else ("no" if aplica else "pe"),
            )
        )

    # 6 · El veredicto por producto, que es donde se ve el techo.
    for producto, detalle in (hechos.get("evaluacion_por_producto") or {}).items():
        acepta = bool(detalle.get("aceptado", detalle.get("acepta", False)))
        motivo = detalle.get("motivo") or detalle.get("razon") or ""
        eventos.append(
            _ev(
                "politica",
                f"{producto}: {'cabe' if acepta else 'no cabe'}",
                detalle=str(motivo)[:160],
                fuente="eligibility_v1.yaml · catálogo",
                control="R7 monto mínimo · R8 segmento · plazos ofertables",
                estado="ok" if acepta else "no",
            )
        )

    if d:
        eventos.append(
            _ev(
                "politica",
                "Decisión de la política",
                detalle=(d.get("motivos") or ["elegible"])[0][:160],
                fuente=(
                    f"eligibility_v1.yaml v{d.get('politica_version')} · "
                    f"corte {hechos.get('corte')}"
                ),
                control="abstenerse es un resultado válido",
                estado="pe" if d.get("abstencion") else ("ok" if d.get("elegible") else "no"),
            )
        )

    # 7 · El estado semántico, si la bandera está encendida.
    scm = turno.scm
    if scm:
        conflictos = len(scm.get("contradictions") or [])
        eventos.append(
            _ev(
                "cognicion",
                f"Estado epistémico: {scm.get('epistemic_status')}",
                detalle=(
                    f"{conflictos} contradicción(es) entre fuentes"
                    if conflictos
                    else "ninguna fuente contradice a otra"
                ),
                fuente="agent/cognition/scm.py",
                control="SCM_ENABLED · hechos tipados con procedencia",
                estado="pe" if conflictos else "ok",
            )
        )

    # 8 · El anclaje de la respuesta.
    citadas = turno.a_traza().get("n_cifras_ancladas", 0)
    eventos.append(
        _ev(
            "verificacion",
            "Toda cifra de la respuesta viene de un tool de este turno",
            detalle=(
                f"{citadas} cifras ancladas" if citadas else "este turno no pronunció ninguna cifra"
            ),
            fuente="agent/guardrails/grounding.py",
            control="AG-09 · dos intentos y se escala",
            estado="ok",
        )
    )

    # 9 · El desenlace.
    eventos.append(
        _ev(
            "desenlace",
            f"Desenlace: {turno.desenlace.value}",
            detalle=(
                f"expediente {turno.case_id}"
                if turno.case_id
                else (f"acción {turno.action_id}" if turno.action_id else "sin escritura")
            ),
            fuente="agent/core/orchestrator.py",
            control="máquina de seis etapas, una prueba por arista",
            estado="ok" if turno.desenlace.value in {"respuesta", "verificado"} else "pe",
        )
    )
    return eventos
