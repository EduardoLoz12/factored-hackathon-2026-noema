# ADR-0009 · El catálogo de herramientas se deriva de la política, no se inventa

**Fecha:** 2026-10-01 · **Estado:** aceptado, revisado tras auditoría de diseño · **Mueve:** `AG-03`, `AG-04`

## Contexto

`AG-04` decía «las nueve herramientas implementadas» y apuntaba a
`agent/tools/{customer,credit,cases}.py`. Ningún documento del repo listaba cuáles eran.
`docs/05_security.md` §3 define el **contrato** que cada tool debe cumplir —`requires_auth`,
`writes`, `allowed_roles`, idempotencia en las de escritura— pero no el catálogo.

El riesgo de escribir la lista a mano era elegir nombres que sonaran completos. Eso dejaría
herramientas sin consumidor y, peor, algún dato que la política sí necesita sin fuente —
convirtiendo una abstención legítima en un hueco de implementación.

**Resultado de derivarla en vez de elegirla: son once, no nueve.** El número del checklist era
una estimación; la coherencia manda sobre el número y el ítem se actualiza.

## Método: la lista se deriva de dos consumidores

**1 · `Politica.evaluar(cliente)` consume un `Cliente`** (`agent/policies/engine.py:96`). Campo por
campo:

| Campo | De dónde sale | Tool |
|---|---|---|
| `customer_id` | del JWT, nunca del cliente (F-007) | — (AccessGuard) |
| `ingreso_mensual_usd` | `customers`, **convertido a USD dentro del tool** | `get_customer_profile` |
| `segmento`, `alta` | `customers` / `customer_360` | `get_customer_profile` |
| `productos: tuple[ProductoVigente]` | `products`, filtrado a crédito | `get_customer_credit_products` |
| `ahorros: tuple[ProductoDeAhorro]` | `products`, filtrado a activos | `get_customer_assets` |
| `ProductoVigente.ultima_transaccion_real` | `max(transaction_date)` real | `get_last_real_activity` |
| `ProductoVigente.cuotas_pagadas` | conteo de pagos | `get_payment_history` — **descriptivo, no decide** |
| `capacidad_estimada_usd` | ML-04 | **no es tool** — ver decisión 1 |

**2 · `REQUIRED_SLOTS` del SCM** (`agent/cognition/scm.py:99`) declara las dos intenciones del
workflow elegido:

- `PRODUCT_INFO` exige `product_type`. Se responde con el catálogo de oferta, sin tocar un dato
  personal. `get_product_catalog` lo resuelve entero.
- `CREDIT_ELIGIBILITY` exige `identity_verified`, `requested_amount`, `currency`, `product_type`.
  Dispara la cadena completa. **`requested_amount` y `currency` no llegaban a la política**:
  `evaluate_eligibility` los normaliza a USD con `calculo.tasas_a_usd` antes de comparar el monto
  pedido contra `Oferta.monto_maximo_usd`.

Y el lado de escritura ya estaba acotado por `docs/05_security.md` §5 sin nombrarse: el usuario de
base de datos de la API solo toca `cases` y `action_ledger`.

## Decisión — las once

| # | Tool | Módulo | `requires_auth` | `writes` | Qué resuelve |
|---|---|---|---|---|---|
| 1 | `verify_identity` | `customer.py` | **No** | No | `document_type` + `document_number` + `date_of_birth`. Único tool sin sesión, porque es el que la crea. |
| 2 | `get_customer_profile` | `customer.py` | Sí | No | Ingreso **en USD**, segmento, alta. Alimenta R1, R8 y el denominador del DTI. |
| 3 | `get_customer_credit_products` | `customer.py` | Sí | No | Los `ProductoVigente`. Alimenta R2, R3, R4. |
| 4 | `get_customer_assets` | `customer.py` | Sí | No | Cuentas e inversiones. Alimenta reservas y el factor compensatorio. |
| 5 | `get_product_catalog` | `credit.py` | **No** | No | Catálogo del YAML: tasa, plazo, mínimos, máximos, segmentos. |
| 6 | `get_payment_history` | `credit.py` | Sí | No | Pagos registrados por producto. **Hecho descriptivo declarado.** |
| 7 | `get_last_real_activity` | `credit.py` | Sí | No | `max(transaction_date)` real. Alimenta el aviso `producto_inactivo`. |
| 8 | `evaluate_eligibility` | `credit.py` | Sí | No | Arma el `Cliente`, normaliza el monto pedido y llama `Politica.evaluar`. |
| 9 | `record_offer_quote` | `credit.py` | Sí | **Sí** | Persiste en `action_ledger` la oferta exacta cotizada. Ver decisión 3. |
| 10 | `create_escalation_case` | `cases.py` | Sí | **Sí** | Inserta el expediente estructurado en `cases`. |
| 11 | `get_escalation_case` | `cases.py` | Sí | No | Relee lo insertado. Sin esto no hay `AG-07` ni `/console`. |

Reparto: `customer.py` 4 · `credit.py` 5 · `cases.py` 2.

## Las cinco decisiones de diseño que el catálogo encierra

**1 · `predict_capacity` (ML-04) no es herramienta: vive dentro de `evaluate_eligibility`.**
La capacidad estimada **solo puede restringir el margen, nunca ampliarlo** (ADR-0006 punto 4). Si
fuera un tool que el modelo elige, omitirlo solo podría aflojar el criterio — y eso no puede quedar
a criterio del LLM. Se registra en la traza como llamada interna.

**Pero devolver `None` no alcanza.** El motor recibe `None` y añade «el estimador no tenía historial
suficiente» (`engine.py:303-309`) **tanto si se abstuvo como si el modelo no cargó**. Lo segundo es
fallar abierto (regla 5) y además afirmar algo falso (regla 1). Por eso `predict_capacity` devuelve
`Capacidad(valor | None, motivo ∈ {abstencion, error_de_carga})`:

- `abstencion` (el 94 % de los casos) → se procede con el margen de política y se declara.
- `error_de_carga` → **no se aprueba nada**: `Decision.abstencion = True` y se escala, según
  `docs/05_security.md` §7.

**2 · `get_payment_history` y `get_last_real_activity` existen, pero no deciden.** Son tools
separados porque las fuentes son distintas —conteo de pagos contra `max(transaction_date)`— y porque
la política prohíbe el camino corto: `last_updated` trae 6.42 % de valores posteriores al corte y
`last_transaction_date` un 17.29 % de incoherencias (F-028). Aislar el cálculo correcto en un archivo
cuyo único propósito es no usar la columna fácil lo hace auditable en un diff.

Lo que **no** hacen es decidir. `ultima_transaccion_real` solo produce un aviso (`engine.py:244`), y
el historial de pagos ya no alimenta ninguna regla: **R6_cumplimiento se retiró del YAML** el
1-oct-2026. Razón corta: el umbral del 5 % habría rechazado al cliente mediano, cuyo cumplimiento es
3.81 %, y no existe calendario de vencimientos con el cual calcularlo (F-029, F-030). El motivo largo
está escrito en el YAML, en el hueco que dejó la regla.

**3 · Hay dos herramientas de escritura, y la segunda existe por una razón de evaluación.**
La primera intención fue una sola —`create_escalation_case`— y eso dejaba un agujero: **en el camino
feliz no se escribe nada**. Cliente elegible, oferta entregada, cero escrituras. Entonces la
relectura que el reto premia textualmente (`docs/00_challenge_brief.md:22`, «verify that actions
actually happened») **nunca correría en el caso que el jurado va a probar primero**.

`record_offer_quote` lo cierra: persiste la oferta exacta cotizada —producto, monto, cuota, tasa,
plazo, `politica_version`, `corte`— y la relee antes de pronunciarla. No es una escritura decorativa:
es un hecho de servicio al cliente, porque el banco queda atado a lo que cotizó y con qué versión de
política lo hizo. Y hace que `VERIFY` tenga relectura real en el 100 % de los turnos de elegibilidad.

Lo que seguimos **sin** hacer es originar el producto. Eso es otro workflow y se declara en
`LIMITATIONS.md`.

**4 · Activos y productos de crédito se leen con tools distintos**, aunque salgan de la misma tabla.
Semántica: unos son obligaciones y otros reservas, y entran al cálculo por lados opuestos.
Seguridad: un flujo de `PRODUCT_INFO` no necesita la posición financiera, y tools separados permiten
no traerla. Mínima exposición por diseño.

**5 · Todo importe se convierte a USD dentro del tool que lo trae.**
`customer_360.estimated_monthly_income` viaja en **moneda local** y `stg_customers` no trae columna de
moneda (F-036). Con ingreso en COP contra umbrales en USD, R3, R4 y R5 son falsos entre países —y el
error no se vería, porque la cifra sigue siendo un número plausible. `get_customer_profile` convierte
con la tasa de `daily_exchange_rates` a fecha ≤ `corte_datos`, y devuelve `moneda_origen` y
`tasa_aplicada` junto a la cifra para que la traza lo audite. Ningún tool devuelve un importe sin
declarar en qué moneda está.

## Roles, alcance de fila y perfil de despliegue — son tres cosas distintas

Confundirlas era un agujero. El rol dice *qué puede hacer*; el alcance de fila dice *sobre quién*; el
perfil de despliegue dice *contra qué base de datos*.

| Rol | Quién es | Qué puede | Alcance de fila |
|---|---|---|---|
| `anonymous` | sesión sin verificar | solo `verify_identity` y `get_product_catalog` | ninguna |
| `customer` | sesión verificada | los 11 | el `customer_id` **del JWT**, no un parámetro |
| `human_agent` | asesor en `/console` (`UI-05`) | lecturas y los dos writes; no verifica identidad | `customer_id` explícito y **registrado en el ledger** |
| `blocked` | tras 3 intentos fallidos (`docs/05_security.md` §2) | nada | ninguna |

**`eval_harness` no es un rol.** Es un **perfil de despliegue**: se activa por variable de entorno al
arrancar el proceso y apunta a otro esquema de base de datos. Ningún token emitido por la API pública
puede obtenerlo. Si fuera un rol de la allowlist, sería acuñable con la misma llave que firma los JWT
de cliente — un rol que escribe a un store aislado, alcanzable desde fuera.

El ejecutor valida **antes** de invocar y registra todo intento rechazado. La prueba obligatoria de
`docs/05_security.md` §3 se instancia como `create_escalation_case` con sesión no verificada, y está
en `tests/tools/test_registry.py`.

## El `idempotency_key` se ancla en la conversación, no en el token

`docs/05_security.md` §3 lo deriva de (sesión, intención, payload). «Sesión» tenía dos lecturas y una
está mal: con el `jti` del JWT, que dura 15 minutos, un reintento tras renovar el token abriría un
segundo caso — exactamente lo que la idempotencia debe impedir, y una conversación de elegibilidad
supera los 15 minutos sin esfuerzo.

```
idempotency_key = sha256(customer_id ‖ conversation_id ‖ intencion ‖ json_canonico(payload))
```

`conversation_id` vive en la fila de `sessions` y sobrevive a la renovación. El payload se
canonicaliza con claves ordenadas, sin marcas de tiempo, y con `politica_version` dentro: una oferta
cotizada bajo otra versión de política es otra oferta.

**Y la garantía última es un índice único sobre la columna en `cases` y `action_ledger`, no la
lógica de aplicación.** El caché en memoria del registro evita el trabajo repetido; lo que impide
que dos workers concurrentes abran dos casos es la base de datos. Ningún `if` detecta esa carrera.

## El conjunto que ancla las respuestas

`AG-09` valida contra `Decision.hechos` ∪ campos de `Oferta` ∪ **todos los escalares de la política**
—umbrales, catálogo y `reservas_minimas_meses`—, no solo los umbrales. Un motivo honesto dice dos
cifras: la del cliente y la que debía alcanzar, y la segunda es política.

Al escribir la prueba de ese invariante aparecieron **cuatro cifras que el motor pronunciaba sin
publicar**. Dos eran derivadas de todo el cliente (`reservas_meses_carga`, `veces_ingreso_exposicion`)
y dos eran **por producto rechazado** —su reserva exigida y su monto máximo—, que es el caso
estructuralmente difícil: `Oferta` solo se crea para los aceptados, así que un rechazo bien explicado
pronunciaba cifras que nada respaldaba. `AG-09` lo habría bloqueado: un falso positivo que en la demo
parece bug del guardrail y era hueco del motor.

Se cerró publicando `hechos["evaluacion_por_producto"]` con la aritmética completa de cada producto
del catálogo, aceptado o rechazado. La prueba vive en
`tests/policies/test_hechos_anclan_la_respuesta.py`.

**Nota para implementar `AG-09`:** los mensajes traen las cifras **formateadas** —`{dti:.0%}` vuelve
0.4012 en «40 %», `{carga:,.0f}` vuelve 1234.56 en «1,235»—. El checker no puede comparar flotantes:
tiene que comparar *renderizados*.

## Consecuencias

- `AG-03` tiene un catálogo cerrado que registrar y `EV-01` tiene once superficies contra las que
  generar casos.
- Ningún tool devuelve un cero donde falta un dato: devuelve ausencia explícita en
  `ToolResult.ausencias`. La política distingue «no hay pagos» de «cero pagos» (F-029) y de esa
  distinción depende qué se declara.
- El modelo nunca ve SQL ni nombres de tabla. Solo once firmas con parámetros tipados.
- `AG-04` pasa de «nueve» a «once» en el checklist, con esta razón escrita.

## Lo que queda abierto

**`ProductoVigente` no tiene identificador de producto** (`engine.py:62-75`): solo `tipo`. Dos
consecuencias que hay que resolver en `AG-04`: `get_last_real_activity` es por producto y no habría
con qué aparear su resultado, y un cliente con dos tarjetas no puede distinguirlas en la respuesta.
Se resuelve añadiendo `producto_id` al dataclass —es aditivo, va al final y no altera el orden
posicional— o aparejando por `(tipo, apertura)`, que no es único. La primera es la correcta.
