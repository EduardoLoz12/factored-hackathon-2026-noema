# ADR-0011 · Cada producto se ofrece a varios plazos, y el plazo no toca la TEA

**Fecha:** 2026-10-01 · **Estado:** aceptado · **Política:** versión 1 → **2**
**Revierte:** el «Aplazado» de ADR-0006 · **Mueve:** `AG-01`, `AG-02`

## Contexto

ADR-0006 cerró con esto en su sección *Aplazado*:

> Ofrecer el mismo producto a varios plazos —hipotecario a 120 y 240 meses con cuotas distintas— para
> que el cliente elija. Añade complejidad al catálogo y a la conversación; se decidió no hacerlo
> todavía.

Al validar el catálogo de la política, Eduardo lo objetó:

> «En base a las tasas observadas podrías ofrecerle al cliente tasas mayores o menores moviendo
> respectivamente el plazo para no cambiar la TEA del producto. De esta manera el cliente puede tener
> 3 opciones para recibir como oferta del bot de acuerdo a su capacidad de pago.»

## Por qué el argumento financiero es correcto

El motor amortiza con `i = tasa_anual / 100 / 12`. Esa es una tasa **nominal anual con capitalización
mensual**, así que la efectiva es `(1 + i)^12 − 1` y **el plazo no entra en la fórmula**. Verificado
en código y fijado con pruebas:

| Producto | Nominal | TEA | Plazos ofertables |
|---|---:|---:|---|
| Tarjeta Crédito | 31.52 % | **36.50 %** | 48 |
| Préstamo Personal | 20.10 % | **22.06 %** | 24 · 48 · 72 |
| Préstamo Hipotecario | 8.98 % | **9.36 %** | 120 · 180 · 240 |

Mover el plazo mueve la cuota, el monto que cabe en el margen, la reserva exigida y el interés total.
No mueve el costo anual efectivo. Ofrecer tres plazos no es ofrecer tres precios: es ofrecer tres
formas de pagar el mismo precio.

## Lo que la implementación destapó, y que la objeción no decía

Al cotizar **sin** monto pedido, cada plazo satura el margen completo. Resultado con margen de
1 600 USD:

| Plazo | Monto máximo | Cuota | Interés total |
|---:|---:|---:|---:|
| 24 m | 31 407 | **1 600** | 6 993 |
| 48 m | 52 487 | **1 600** | 24 313 |
| 72 m | 66 637 | **1 600** | 48 563 |

**Las tres cuotas son idénticas.** Esas no son «tres opciones según su capacidad de pago»: son tres
opciones según cuánto querés pedir, todas consumiendo el 100 % del margen.

Para que sean opciones por capacidad hace falta el **monto que el cliente pide**. Con 30 000 USD:

| Plazo | Cotizado | Cuota | Interés total |
|---:|---:|---:|---:|
| 24 m | 30 000 | **1 528** | 6 680 |
| 48 m | 30 000 | **915** | 13 896 |
| 72 m | 30 000 | **720** | 21 863 |

Ahí sí elige por lo que puede pagar. Y ese dato ya estaba en el flujo: `REQUIRED_SLOTS` del SCM exige
`requested_amount` y `currency` para `CREDIT_ELIGIBILITY`. Lo que faltaba era que llegara al motor —
el hueco que la auditoría de diseño había marcado primero.

## Decisión

**1 · El catálogo declara `plazos_ofertables` por producto**, en lugar de un `plazo_meses` único. La
política pasa a **versión 2**, porque esto sí cambia el comportamiento observable (a diferencia del
retiro de R6, que no cambiaba nada).

**2 · `Politica.evaluar(cliente, monto_pedido_usd=None)`.** Con monto pedido, cada plazo cotiza ese
monto y las opciones difieren en cuota. Sin monto pedido, cada plazo cotiza su techo y difieren en
monto. Las dos lecturas se conservan porque las dos son útiles: la primera para quien ya sabe cuánto
necesita, la segunda para quien pregunta cuánto podría pedir.

**3 · `Oferta` distingue el techo de lo cotizado.** `monto_maximo_usd` es lo máximo que la política
admite a ese plazo; `monto_ofrecido_usd` es lo que realmente se cotiza. La cuota y el interés total
corresponden al segundo. Sin esa distinción, una cotización recortada se leería como el techo.

**4 · Toda oferta declara el interés total.** Es la cifra que impide que un plazo largo parezca
gratis: 72 meses da una cuota de 720 contra 1 528, y cuesta **21 863 de interés contra 6 680**. Un
sistema que muestra solo la cuota está vendiendo, no asesorando. En revolvente el interés total es
`None`, no cero: una línea no tiene un total que devolver, e inventarlo sería una cifra falsa.

**5 · La tarjeta lleva un solo plazo.** Es revolvente: su obligación es el pago mínimo sobre el saldo
dispuesto, no una amortización, así que el plazo no cambia la cuota. Ofrecerla «a tres plazos» sería
decorativo, y el proyecto ya rechazó una vez la tentación de inventar superficie para que algo parezca
más completo.

**6 · Cotizar menos de lo pedido se declara.** Ante una petición de 400 000 con techo de 178 086, el
sistema cotiza 178 086 y **dice** «pediste 400 000 y podemos ofrecerte hasta 178 086». Sin ese aviso
el cliente creería que recibió lo que pidió — no es una cifra inventada, pero sí una omisión que
induce a error.

**7 · El rechazo cita el plazo más largo.** Si ningún plazo pasa, el motivo dice «incluso a 240 meses,
el plazo más largo que ofrecemos…». El plazo más largo es el mejor caso en las dos pruebas por
producto —baja la cuota, así que exige menos reserva, y sube el monto, así que alcanza el mínimo—, de
modo que citarlo le dice al cliente que no queda plazo al que recurrir. Un producto de un solo plazo
no usa esa frase, porque ahí sería ruido.

## La consecuencia que no estaba en la objeción

**Esto convierte rechazos en ofertas.** R7 rechaza cuando el monto que el cliente puede asumir no
alcanza el mínimo del catálogo. A plazo más largo el mismo margen soporta más principal: el
hipotecario pasa de 126 415 a 120 meses a 178 086 a 240. Un cliente que no calificaba a un plazo
corto sí califica a uno largo, y la respuesta pasa de «no puedo ofrecerte nada» a «puedo, a este
plazo».

Para el reto eso cuenta doble: sube la resolución segura sin tocar el apetito de riesgo —los umbrales
no se movieron— y mejora la calidad de la explicación, que es donde se juzga que el sistema asesora en
vez de denegar.

## Supuestos declarados

Los plazos ofertables son **supuesto de política, no dato**: `expiration_date` tiene cobertura cero en
préstamos y 95 % en tarjetas, donde además es el vencimiento del plástico y no un plan de
amortización. Elegir 24/48/72 y 120/180/240 es decisión de negocio, de la misma naturaleza que el 48 y
el 240 que ya estaban, y se declara igual.

## Consecuencias

- 19 pruebas nuevas en `tests/policies/test_plazos_ofertables.py`, sin LLM y sin base de datos. Dos
  fijan propiedades financieras que no se pueden romper en silencio: que la TEA no dependa del plazo
  (detecta un cambio de convención de capitalización) y que el interés total sea exactamente
  `cuota × plazo − principal`.
- `_plazos_ofertables` acepta el `plazo_meses` único de la versión 1, así que una política anterior
  sigue evaluándose. La suite completa quedó en verde sin tocar las 64 pruebas existentes.
- `hechos["evaluacion_por_producto"][producto]["opciones"]` publica la aritmética de cada plazo, con
  techo, cotizado, cuota, reserva exigida e interés total. Es lo que `AG-09` valida y lo que el panel
  Caja de Vidrio tiene que mostrar.
- `record_offer_quote` (`AG-04`, tool 9) persiste la oferta **con su plazo y su TEA**: dos ofertas del
  mismo producto a plazos distintos son dos cotizaciones distintas, y el `idempotency_key` las
  distingue porque el plazo está en el payload.
