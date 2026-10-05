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
    "verify_identity": "Compares the three identity factors against the database",
    "get_customer_profile": "Reads income, segment and tenure",
    "get_customer_credit_products": "Reads the credit products active at the cut-off",
    "get_customer_assets": "Reads accounts and investments, which count as reserves",
    "get_payment_history": "Counts observed payments per product",
    "get_last_real_activity": "Finds the last real transaction of each product",
    "get_product_catalog": "Reads the catalogue and its current conditions",
    "evaluate_eligibility": "Runs the policy over the facts gathered",
    "record_offer_quote": "Records the quote and reads it back",
    "create_escalation_case": "Opens the case file for the advisor",
}

NOMBRE_REGLA = {
    "R1_antiguedad": "Minimum tenure as a client",
    "R2_numero_de_productos": "Cap on active credit products",
    "R3_corte_duro_de_dti": "Hard debt-service cut-off",
    "R4_exposicion_sobre_ingreso": "Exposure over annual income",
    "R5_margen_disponible": "Monthly margin under the DTI cap",
    "R7_monto_minimo": "Product minimum amount",
    "R8_segmento": "Product available for the client's segment",
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
            "Client message received",
            detalle=f"idioma detected: {lectura['idioma']}",
            fuente="api/extraccion.py",
            control="language detection",
        ),
        _ev(
            "identidad",
            "Reading identity factors",
            detalle=("collected: " + (", ".join(reunidos) if reunidos else "none yet")),
            fuente="api/identidad.py",
            control="three factors: document type, number and date of birth",
            estado="ok" if reunidos else "pe",
        ),
    ]
    if faltan:
        eventos.append(
            _ev(
                "identidad",
                "Nothing queried yet",
                detalle="missing: " + ", ".join(faltan),
                fuente="agent/core/access_guard.py",
                control="AG-05 · no personal information without a session",
                estado="pe",
            )
        )
        return eventos

    eventos.append(
        _ev(
            "identidad",
            "Checking against the database"
            if r is None
            else ("Identity verified" if r.verificado else "Factors do not match"),
            detalle=(f"attempts left: {r.intentos_restantes}" if r is not None else ""),
            fuente="noema_silver.stg_customers",
            control="AG-05 · 3 attempts, growing wait, JWT valid 15 min",
            estado="ok" if (r is not None and r.verificado) else "no",
        )
    )
    return eventos


def _decision_txt(d: dict[str, Any], hechos: dict[str, Any]) -> str:
    """Lo que la decisión concluyó, en una línea. No repite el motivo de otro producto."""
    if d.get("abstencion"):
        return "the policy abstained: the turn asks or escalates instead of asserting"
    if d.get("eligible"):
        nombres = sorted({str(o.get("producto")) for o in (d.get("productos_eligibles") or [])})
        return "products that fit: " + ", ".join(nombres) if nombres else "eligible"
    return (d.get("motivos") or ["no eligible"])[0]


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
            "Message wrapped as data, not as an instruction",
            detalle=(
                "patterns detected: " + ", ".join(patrones) if patrones else "no injection patterns"
            ),
            fuente="agent/guardrails/injection.py",
            control="AG-10 · containment with a per-turn random seal",
            estado="pe" if sospechoso else "ok",
        )
    )

    # 2 · Qué entendió, sin decidir nada.
    slots = sorted(lectura.get("slots") or {})
    eventos.append(
        _ev(
            "entrada",
            f"Intent: {lectura['intencion']}",
            detalle=("data extracted: " + ", ".join(slots)) if slots else "no data in the text",
            fuente="api/extraccion.py",
            control="the model extracts, the orchestrator decides",
        )
    )

    # 3 · Sesión.
    eventos.append(
        _ev(
            "identidad",
            "Verified session",
            detalle="the client identifier travels inside the token",
            fuente="agent/core/access_guard.py",
            control="AG-05 · permissions enforced in code, not in the prompt",
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
                        f"{x['cifras']} figures published"
                        + (" · read back after writing" if x["escribe"] else "")
                    )
                ),
                fuente=TABLAS.get(nombre, x.get("fuente") or "—"),
                control=f"AG-03 · {nombre}, allowed for this role",
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
                control="AG-02 · eligibility is computed by the policy, not by the model",
                estado="ok" if (aplica and cumple) else ("no" if aplica else "pe"),
            )
        )

    # 6 · El veredicto por producto, que es donde se ve el techo.
    # Un producto fits si tiene al menos una opción de plazo. Así lo publica el motor
    # (`opciones` vacío = ningún plazo pasa). Si does not fit, el motivo está en la lista
    # de motivos de la decisión, que empieza por el nombre del producto.
    motivos = d.get("motivos") or []
    for producto, detalle in (hechos.get("evaluacion_por_producto") or {}).items():
        opciones = detalle.get("opciones") or {}
        acepta = bool(opciones)
        if acepta:
            plazos = ", ".join(str(m) for m in sorted(opciones, key=lambda x: int(x)))
            detalle_txt = f"fits at {plazos} months"
        else:
            motivo = next((m for m in motivos if str(m).startswith(producto)), "")
            detalle_txt = motivo or "no term passes the rules"
        eventos.append(
            _ev(
                "politica",
                f"{producto}: {'fits' if acepta else 'does not fit'}",
                detalle=str(detalle_txt)[:200],
                fuente="eligibility_v1.yaml · catalogue",
                control="R7 minimum amount · R8 segment · term options",
                estado="ok" if acepta else "no",
            )
        )

    if d:
        eventos.append(
            _ev(
                "politica",
                "Policy decision",
                detalle=_decision_txt(d, hechos),
                fuente=(
                    f"eligibility_v1.yaml v{d.get('politica_version')} · "
                    f"corte {hechos.get('corte')}"
                ),
                control="abstaining is a valid outcome",
                estado="pe" if d.get("abstencion") else ("ok" if d.get("eligible") else "no"),
            )
        )

    # 7 · El estado semántico, si la bandera está encendida.
    scm = turno.scm
    if scm:
        conflictos = len(scm.get("contradictions") or [])
        eventos.append(
            _ev(
                "cognicion",
                f"Epistemic state: {scm.get('epistemic_status')}",
                detalle=(
                    f"{conflictos} contradiction(s) between sources"
                    if conflictos
                    else "no source contradicts another"
                ),
                fuente="agent/cognition/scm.py",
                control="SCM_ENABLED · typed facts with provenance",
                estado="pe" if conflictos else "ok",
            )
        )

    # 8 · El anclaje de la respuesta.
    citadas = turno.a_traza().get("n_cifras_ancladas", 0)
    eventos.append(
        _ev(
            "verificacion",
            "Every figure in the reply comes from a tool of this turn",
            detalle=(f"{citadas} figures anchored" if citadas else "this turn stated no figures"),
            fuente="agent/guardrails/grounding.py",
            control="AG-09 · two attempts, then escalate",
            estado="ok",
        )
    )

    # 9 · El desenlace.
    eventos.append(
        _ev(
            "desenlace",
            f"Outcome: {turno.desenlace.value}",
            detalle=(
                f"case file {turno.case_id}"
                if turno.case_id
                else (f"action {turno.action_id}" if turno.action_id else "no write")
            ),
            fuente="agent/core/orchestrator.py",
            control="six-stage state machine, one test per edge",
            estado="ok" if turno.desenlace.value in {"respuesta", "verificado"} else "pe",
        )
    )
    return eventos
