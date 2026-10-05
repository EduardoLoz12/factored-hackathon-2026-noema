"""La prosa que lee el cliente — `AG-09`.

Determinista a propósito, y vale la pena defender la decisión: el contrato del proyecto
dice que ninguna cifra sale del modelo. Si además la **frase** la arma una plantilla
sobre las cifras que los tools devolvieron, entonces no hay ningún punto del camino
donde un número pueda aparecer sin respaldo. El modelo queda para lo que sabe hacer
—entender el mensaje del cliente— y la aritmética y su enunciado quedan del lado del
sistema.

El texto que produce esta capa **igual pasa por el `GroundingChecker`**. No es
redundante: la plantilla podría estar mal escrita y pronunciar un número que no está en
la carga del turno. Que el control se aplique a nuestra propia redacción, y no solo a la
del modelo, es lo que hace que la garantía valga.

Los importes se formatean con `cifra()` del motor de política: punto para los miles y
coma para los decimales, que es como se lee en los cuatro países del dataset. Escribir
«1,200 USD» a un cliente colombiano le dice *uno coma dos* (F-045).
"""

from __future__ import annotations

from typing import Any

from agent.policies.engine import cifra

ES = "es"
PT = "pt"


def _moneda(valor: float, decimales: int = 0) -> str:
    return f"{cifra(valor, decimales)} USD"


def _lista(partes: list[str], idioma: str) -> str:
    """Une con comas y la conjunción del idioma."""
    y = "e" if idioma == PT else "y"
    if len(partes) <= 1:
        return partes[0] if partes else ""
    return ", ".join(partes[:-1]) + f" {y} " + partes[-1]


def _catalogo(turno: Any, idioma: str) -> str:
    """Consulta de producto: condiciones del catálogo, sin decidir nada."""
    filas = []
    for p in turno.ofertas[:3]:
        nombre = p.get("producto") or p.get("nombre")
        tasa = p.get("tasa_anual")
        minimo, maximo = p.get("monto_minimo_usd"), p.get("monto_maximo_usd")
        trozos = [str(nombre)]
        if tasa is not None:
            trozos.append(
                f"taxa anual de {cifra(tasa, 2)} %"
                if idioma == PT
                else f"tasa anual de {cifra(tasa, 2)} %"
            )
        if minimo is not None and maximo is not None:
            trozos.append(
                f"de {_moneda(minimo)} a {_moneda(maximo)}"
                if idioma == PT
                else f"desde {_moneda(minimo)} hasta {_moneda(maximo)}"
            )
        filas.append(
            ": ".join([trozos[0], ", ".join(trozos[1:])]) if len(trozos) > 1 else trozos[0]
        )

    if not filas:
        return (
            "Não tenho as condições desse produto à mão."
            if idioma == PT
            else "No tengo a mano las condiciones de ese producto."
        )
    cabeza = (
        "Estas são as condições vigentes:"
        if idioma == PT
        else "Estas son las condiciones vigentes:"
    )
    cola = (
        "Para saber quanto cabe no seu caso, me diga o valor que precisa."
        if idioma == PT
        else "Para saber cuánto te cabe a ti, dime el monto que necesitas."
    )
    return cabeza + "\n· " + "\n· ".join(filas) + "\n" + cola


def _oferta(o: dict[str, Any], idioma: str) -> str:
    """Una oferta concreta, con su cuota y —si la hay— su interés total."""
    monto = o.get("monto_ofrecido_usd") or o.get("monto_maximo_usd")
    cuota = o.get("cuota_estimada_usd")
    plazo = o.get("plazo_meses")
    tea = o.get("tea_pct")
    interes = o.get("interes_total_usd")

    if idioma == PT:
        t = f"{o.get('producto')} de {_moneda(monto)}"
        if plazo:
            t += f" em {plazo} meses"
        if cuota is not None:
            t += f", com parcela estimada de {_moneda(cuota, 2)}"
        if tea:
            t += f" e custo anual efetivo de {cifra(tea, 2)} %"
        if interes is not None:
            t += f". Juros totais: {_moneda(interes, 2)}"
        return t + "."

    t = f"{o.get('producto')} de {_moneda(monto)}"
    if plazo:
        t += f" a {plazo} meses"
    if cuota is not None:
        t += f", con una cuota estimada de {_moneda(cuota, 2)}"
    if tea:
        t += f" y un costo anual efectivo de {cifra(tea, 2)} %"
    if interes is not None:
        t += f". El interés total sería de {_moneda(interes, 2)}"
    return t + "."


NOMBRE_SLOT = {
    "requested_amount": ("el monto que necesitas", "o valor que você precisa"),
    "currency": ("la moneda", "a moeda"),
    "product_type": ("qué producto te interesa", "qual produto lhe interessa"),
    "identity_verified": ("verificar tu identidad", "verificar sua identidade"),
}


def preguntar(turno: Any, idioma: str = ES) -> str:
    """Cuando falta un dato, se nombra cuál. «Me falta un dato» no sirve de nada."""
    pt = idioma == PT
    faltan = [NOMBRE_SLOT.get(s, (s, s))[1 if pt else 0] for s in (turno.pregunta_por or ())]
    if not faltan:
        return turno.mensaje
    cabeza = (
        "Para lhe dizer quanto pode pedir, preciso de "
        if pt
        else "Para decirte cuánto puedes pedir necesito "
    )
    return cabeza + _lista(faltan, idioma) + "."


def sin_datos_personales(idioma: str = ES) -> str:
    """Un dato personal no vuelve en texto por este canal, ni al titular."""
    if idioma == PT:
        return (
            "Não devolvo documentos, telefones nem datas de nascimento por este canal, "
            "mesmo sendo seus. Vou lhe passar para um atendente, que pode confirmá-los "
            "com você de forma segura."
        )
    return (
        "No devuelvo documentos, teléfonos ni fechas de nacimiento por este canal, "
        "aunque sean tuyos. Te derivo con un asesor, que puede confirmártelos de "
        "forma segura."
    )


def redactar(turno: Any, idioma: str = ES, pedido: str | None = None) -> str:
    """Arma la respuesta del turno. Solo usa cifras que los tools publicaron.

    `pedido` es el producto que el cliente nombró. Si la política lo admite, la
    respuesta **empieza por ese** y no por el primero de la lista: un cliente que
    pidió un préstamo y recibe una tarjeta sin explicación cree que no se le
    escuchó.
    """
    pt = idioma == PT
    d = turno.decision or {}

    # Consulta de producto: no pasa por la política.
    if turno.ofertas and not d:
        return _catalogo(turno, idioma)

    ofertas = list(turno.ofertas or [])
    if ofertas:
        elegida = next((o for o in ofertas if o.get("producto") == pedido), None)
        otras = [o for o in ofertas if o is not elegida]
        if elegida is None:
            elegida, otras = ofertas[0], ofertas[1:]

        partes = []
        if pedido and elegida.get("producto") != pedido:
            # Pidió uno y le cabe otro. Se dice, con el motivo del que pidió.
            motivo = next((m for m in (d.get("motivos") or []) if m.startswith(str(pedido))), "")
            motivo = motivo.split(":", 1)[1].strip() if ":" in motivo else motivo
            partes.append(
                (f"Agora não posso lhe oferecer {pedido}. " + (motivo + " " if motivo else ""))
                if pt
                else (
                    f"Ahora mismo no puedo ofrecerte {pedido}. " + (motivo + " " if motivo else "")
                )
            )
            partes.append("O que posso oferecer é: " if pt else "Lo que sí puedo ofrecerte es: ")
        else:
            partes.append("Posso lhe oferecer: " if pt else "Puedo ofrecerte: ")
        partes.append(_oferta(elegida, idioma))

        # El techo lo pone la política, no lo que el cliente pidió. Se dice con
        # palabras y sin repetir la cifra que él nombró: esa cifra es suya, no la
        # publicó ningún tool, y pronunciarla la dejaría sin anclaje.
        ofrecido, techo = elegida.get("monto_ofrecido_usd"), elegida.get("monto_maximo_usd")
        if ofrecido and techo and float(ofrecido) >= float(techo):
            partes.append(
                " É o máximo que a sua capacidade de pagamento admite."
                if pt
                else " Es el máximo que admite tu capacidad de pago."
            )

        # Solo los productos **distintos** del ofrecido. La política devuelve el
        # mismo producto a varios plazos, y repetirlo en «también te caben» hacía
        # que la respuesta se contradijera a sí misma.
        nombres = sorted(
            {str(o.get("producto")) for o in otras if o.get("producto") != elegida.get("producto")}
        )
        if nombres:
            partes.append(
                (" Também se encaixam: " if pt else " También te caben: ")
                + _lista(nombres, idioma)
                + "."
            )
        return "".join(partes)

    # Sin oferta: rechazo explicado. Es una resolución, no una evasiva.
    motivos = [m for m in (d.get("motivos") or []) if m]
    if motivos:
        cabeza = (
            "Agora não posso lhe oferecer um produto de crédito, e lhe digo por quê: "
            if pt
            else "Ahora mismo no puedo ofrecerte un producto de crédito, y te digo por qué: "
        )
        cuerpo = motivos[0]
        cola = (
            ""
            if len(motivos) == 1
            else ("\\nOutros motivos: " if pt else "\nOtros motivos: ") + " ".join(motivos[1:3])
        )
        return cabeza + cuerpo + cola

    # Nada que decir con respaldo: se devuelve el mensaje del orquestador tal cual.
    return turno.mensaje or (
        "Não tenho dados suficientes para lhe responder com precisão."
        if pt
        else "No tengo datos suficientes para responderte con precisión."
    )


def redactor(idioma: str, pedido: str | None):
    """Adaptador para `Orquestador.redactar_y_verificar`.

    Ignora el número de intento: una plantilla determinista no se corrige a sí misma.
    Si su texto no ancla, el turno escala, que es exactamente lo que debe pasar — y
    significa que la plantilla tiene un error, no el cliente.
    """

    def escribir(turno: Any):
        def _f(_intento: int, _previo: Any) -> str:
            return redactar(turno, idioma, pedido)

        return _f

    return escribir
