# ADR-0012 · Las escrituras van a un store separado, de solo añadir

**Fecha:** 2026-10-01 · **Estado:** aceptado · **Mueve:** `AG-04` (tools 9 a 11), `AG-07`

## Contexto

El sistema escribe dos cosas y nada más: el expediente de un escalamiento y la oferta que cotizó.
`docs/05_security.md` §5 ya lo había acotado sin nombrarlo — el usuario de base de datos de la API
tiene **solo lectura** sobre gold e **inserción y lectura** sobre `cases` y `action_ledger`, sin
`UPDATE` ni `DELETE`.

Faltaba decidir dónde viven esas dos tablas, porque la base analítica no sirve: son **2.99 GB** que en
despliegue se abren `read_only=True`, y meter escrituras ahí obligaría a abrirla en modo escritura
entera, perdiendo la garantía que el propio contrato exige.

## Decisión

**Un archivo DuckDB aparte, `data/noema_ledger.duckdb`, con dos tablas de solo añadir.**

| | Por qué |
|---|---|
| **Separado de la analítica** | Permite abrir gold en solo lectura de verdad. El modelo de permisos del §5 deja de ser una intención y pasa a ser la forma del despliegue. |
| **DuckDB y no Postgres** | `DAT-14` —el export a Postgres— es de Federico y está **bloqueado** por credenciales. DuckDB funciona en un clon recién hecho y en CI, sin secretos. La interfaz son cuatro métodos, así que cambiarla después está contenido. |
| **Solo añadir** | Sin `UPDATE` ni `DELETE` en el código. La inmutabilidad del ledger la garantiza que esas sentencias no existan, no que falte el `SELECT` — eso ya se corrigió (F-039). |
| **Índice único sobre `idempotency_key`** | Es lo que hace la idempotencia real. El caché en memoria del registro (`AG-03`) evita el trabajo repetido; lo que impide que **dos workers concurrentes** abran dos casos es la restricción en la base. Ningún `if` detecta esa carrera. |

### Las dos tablas

`cases` guarda el expediente de un escalamiento: cliente, conversación, intención, motivo, el
expediente estructurado y la versión de política con la que se evaluó.

`action_ledger` guarda cada acción ejecutada: hoy solo la oferta cotizada, con producto, monto, cuota,
tasa, TEA, plazo, versión de política y corte de datos. Dos ofertas del mismo producto a plazos
distintos son **dos cotizaciones distintas**, y el `idempotency_key` las separa porque el plazo entra
en el payload.

### La relectura es un viaje de ida y vuelta real

`AG-07` existe porque el reto lo pide textual: «verify that actions actually happened»
(`docs/00_challenge_brief.md:22`). Para que signifique algo, `releer()` tiene que **consultar la base**
y comparar lo que volvió contra lo que se quiso escribir. Devolver el objeto que se acaba de construir
en memoria sería una verificación que no verifica nada — pasaría siempre, incluso con la base caída.

Hay una prueba que lo fuerza: escribe, cierra la conexión, abre otra y relee.

## Lo que esto no resuelve, y hay que decir

**La retención no la puede hacer la API.** `docs/05_security.md` §5 fija trazas a 30 días y
expedientes a 90, y a la vez le quita el `DELETE` al usuario de la API. Las dos cosas son correctas y no
se contradicen: la retención es un **trabajo operativo con otras credenciales**, no algo que el agente
pueda hacer mientras atiende a un cliente. Un sistema cuyo proceso de atención puede borrar su propio
registro de acciones no tiene registro de acciones.

Queda como deuda declarada en `LIMITATIONS.md`: el trabajo de retención no está implementado.

## Datos personales en el expediente

El expediente lleva **hechos verificados y cifras**, no identidad en claro. El `customer_id` sí entra —
es el identificador opaco del propio sistema (`CLI-…`), el mismo que viaja dentro del JWT, y sin él el
expediente no sirve para que un humano retome el caso. Lo que **no** entra es `document_number`, correo
ni teléfono: §5 los quiere hasheados en trazas y aquí directamente no hacen falta.

## Consecuencias

- `record_offer_quote` y `create_escalation_case` escriben; `get_escalation_case` relee. Son las tools
  9, 10 y 11 de `AG-04`.
- `AG-07` tiene contra qué comparar, y la relectura corre en el **100 %** de los turnos de
  elegibilidad, no solo cuando hay escalamiento (ADR-0009, decisión 3).
- `data/noema_ledger.duckdb` no se versiona: `data/` ya está fuera de git. Las pruebas usan
  `:memory:`, así que la suite corre sin tocar disco.
- El esquema se crea solo al abrir el store, de forma idempotente. No hay migraciones todavía; cuando
  haya, este es el archivo donde se declaran.
