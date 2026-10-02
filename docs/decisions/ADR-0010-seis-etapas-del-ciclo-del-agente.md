# ADR-0010 · Seis etapas: las cinco del reto más la puerta de identidad

**Fecha:** 2026-10-01 · **Estado:** aceptado, revisado tras auditoría de diseño
**Mueve:** `AG-05`, `AG-06`, `AG-07`, `AG-08`

## Contexto

`docs/00_challenge_brief.md:20` cita la slide 11 del reto: **cinco** etapas, *Understand → Decide →
Act → Verify → Escalate*, con la exigencia de que sean «visibles en el código y en las trazas».
`AG-06` del checklist dice **seis**. La sexta nunca se definió en ningún documento del repo.

No es cosmético. El nombre de las etapas es el mismo string en tres lugares —el código, la traza JSON
de `AG-12` y el panel Caja de Vidrio de `UI-03`— y es lo que el jurado va a leer para comprobar la
exigencia de la slide 11. Si el string no coincide con el de la slide, el punto no se cobra aunque el
comportamiento esté implementado.

## Decisión

**Seis etapas: `IDENTIFY` precede a las cinco del reto, que conservan su nombre textual.**

| # | Etapa | ¿Del reto? | Qué hace | Ítem |
|---|---|---|---|---|
| 0 | `IDENTIFY` | **No — añadida** | Verifica identidad y emite sesión. Ninguna información personal sale antes. | `AG-05` |
| 1 | `UNDERSTAND` | Sí, slide 11 | Intención y slots. Puebla el SCM. Pregunta si falta evidencia; resuelve contradicciones por tipo. | `AG-06`, `AG-13` |
| 2 | `DECIDE` | Sí, slide 11 | `Politica.evaluar`. Determinista, sin LLM. Puede abstenerse. | `AG-06` |
| 3 | `ACT` | Sí, slide 11 | Ejecuta: cotizar la oferta, o abrir el expediente. | `AG-04`, `AG-06` |
| 4 | `VERIFY` | Sí, slide 11 | Relee del store lo que escribió **y** valida que ninguna cifra sea huérfana. | `AG-07`, `AG-09` |
| 5 | `ESCALATE` | Sí, slide 11 | Expediente estructurado para un humano. | `AG-08` |

Los nombres van en inglés porque el código va en inglés (convención del proyecto) y porque así son
idénticos a los de la slide. La documentación y los mensajes al cliente, en español y portugués.

### Por qué `IDENTIFY` es una etapa y no un middleware

**Es una puerta con estado, no un filtro.** `docs/05_security.md` §2 le da reglas propias: tres
intentos por sesión, backoff exponencial, mensajes de error **idénticos** en todo fallo para impedir
enumeración, `hmac.compare_digest`, sesión de 15 minutos en tabla con TTL, y un estado `blocked`
resultante. Un middleware que devuelve 401 no tiene nada de eso.

**Si no es etapa, no aparece en la traza.** Y entonces no se puede demostrar dónde se cruzó la
puerta, ni mostrar en la Caja de Vidrio que el sistema no habló de dinero antes de verificar. La
exigencia de la slide 11 es que las etapas sean *visibles*; la verificación de identidad es
precisamente la que más conviene que se vea.

**El checklist ya la trataba como componente propio.** `AG-05` es un ítem separado con su propio
archivo (`agent/core/access_guard.py`).

### Cómo se declara, para no inflar el cumplimiento

La traza etiqueta las seis, y el panel muestra `IDENTIFY` **marcada como extensión nuestra**, no como
parte de la slide 11. Las otras cinco llevan el nombre textual del reto. El jurado tiene que poder
mapear 1:1 sin interpretar, y tiene que ver que no contamos una etapa inventada como si la hubieran
pedido. Si al jurado le sobra, sobra una de más — no falta ninguna de las cinco pedidas.

## El ciclo no es una tubería: es una máquina de estados

Ningún turno recorre las seis en orden fijo. Decirlo explícito evita implementar un
`for stage in STAGES` que fuerce etapas sin sentido.

```
IDENTIFY ──fallo ×3──────────────────────────────> blocked (fin de sesión)
    │ ok
    v
UNDERSTAND
    ├─ contradictions() con PRECONDITION_VIOLATION ──> ESCALATE   (falla cerrado)
    ├─ VALUE_CONFLICT entre dos fuentes estructuradas ──> ESCALATE
    ├─ VALUE_CONFLICT con una fuente LANGUAGE, o PROVENANCE_CONFLICT ──>
    │       gana la fuente estructurada, se declara en la respuesta, el turno sigue
    ├─ missing_evidence() ≠ ∅ ───────────────────> pregunta al cliente (fin del turno)
    ├─ intent = PRODUCT_INFO ──> catálogo ──> VERIFY ──> respuesta  (sin DECIDE ni ACT)
    v intent = CREDIT_ELIGIBILITY
DECIDE
    ├─ abstención ───────────────────────────────> ESCALATE
    v decisión con motivo
ACT ──nada que escribir──> VERIFY (solo grounding)
    │ cotizó la oferta o abrió el expediente
    v
VERIFY
    ├─ relectura no coincide ────────────────────> ESCALATE (y NO se afirma que ocurrió)
    ├─ cifra huérfana ──> reintento; al segundo ─> ESCALATE
    v todo cuadra
respuesta al cliente
```

### Las contradicciones las resuelve el orquestador, por tipo

`agent/cognition/scm.py:179` es explícito: «el SCM los reporta; no los resuelve». Y
`Politica.evaluar(cliente)` no tiene por dónde recibirlos — su firma solo acepta un `Cliente`. El
dueño de la arista es el orquestador, y el tipo de contradicción queda en la traza.

`CONFLICTED` **precede** a `INCOMPLETE` (`scm.py:94`): si hay contradicción, se resuelve antes de
preguntar por lo que falta. Preguntar mientras hay un conflicto sin resolver produce una pregunta
sobre premisas falsas.

**La trampa que hay que evitar:** `contradictions()` marca `VALUE_CONFLICT` ante **cualquier** par de
valores distintos del mismo `(subject, predicate)` (`scm.py:195-203`), y `assert_fact` nunca
sobrescribe (SCM-02). Entonces un cliente que se corrige —«quiero 5 000… mejor 8 000»— genera un
`VALUE_CONFLICT` legítimo que **no debe escalar**. Regla: cuando una de las dos fuentes es
`SourceLayer.LANGUAGE`, el conflicto se resuelve a favor de la fuente estructurada si la hay, y a
favor del hecho más reciente si ambas son del cliente. Escalan los conflictos **entre dos fuentes
estructuradas** —`TABLE`, `TOOL`, `MODEL`, `POLICY`—, porque ahí el sistema no tiene criterio para
preferir una y afirmar sería inventar.

### Las otras tres propiedades que esta forma garantiza

**`UNDERSTAND` puede terminar el turno.** Si `missing_evidence()` no está vacío, el orquestador
**pregunta en vez de decidir** (`docs/07_scm_spec.md:80`). No es un error: es lo que el reto premia
(«AI should not be autonomous just because it can be», slide 11).

**`PRODUCT_INFO` salta `DECIDE` y `ACT`.** Responder qué tasa tiene un préstamo no es una decisión de
crédito ni una acción. Forzarlo por la política produciría una abstención falsa en la métrica.

**`VERIFY` corre siempre, con una o dos comprobaciones.** El reto pide una etapa, no una
comprobación; son dos cosas distintas que el proyecto venía tratando como una:

- *Relectura del store* (`AG-07`) — solo si `ACT` escribió. Responde «¿la acción ocurrió?»
  (`docs/00_challenge_brief.md:22`).
- *Grounding* (`AG-09`) — siempre, incluso en `PRODUCT_INFO`. Responde «¿toda cifra de esta respuesta
  salió de un tool de este turno?» (regla 1 del proyecto).

Se mantiene el string `VERIFY` y se cuentan los dos fallos por separado en `EV-06`, porque un fallo
de relectura y una cifra huérfana son de naturaleza distinta.

Con `record_offer_quote` en el catálogo (ADR-0009, decisión 3), la relectura corre en el **100 % de
los turnos de elegibilidad**, no solo cuando hay escalamiento. Antes de eso, el camino feliz no
escribía nada y la relectura nunca se habría demostrado en el caso que el jurado prueba primero.

**`ESCALATE` es destino, no final de fila.** Se llega desde contradicción irresoluble, abstención de
la política, fallo de relectura, cifra huérfana persistente y bloqueo por identidad. En todos los
casos el sistema **no afirma** lo que no puede sostener. Reglas 3 y 5 del contrato, hechas topología.

## Las métricas se miden sobre lo observable, no sobre las aristas

Una primera versión de este ADR definía `EV-06` «por arista». Está mal por dos razones: el brazo
`baseline` **no tiene máquina de estados**, así que la tabla de tres brazos quedaría con una columna
medida de otra forma; y sin denominador declarado, una tasa de acción insegura de cero es trivial
cuando nunca se actúa.

Cada métrica se define con su denominador, se calcula sobre la respuesta y el ledger —observables en
los tres brazos— y se estratifica por intención:

| Métrica | Numerador | Denominador |
|---|---|---|
| Resolución segura | respuestas entregadas con grounding en verde | turnos totales |
| **Tasa de acción insegura** | afirmaciones de acción tras relectura fallida | **turnos que escribieron** |
| Abstención | salidas por `ESCALATE` desde `DECIDE` | **turnos de `CREDIT_ELIGIBILITY`** |
| Cifra huérfana | respuestas bloqueadas por grounding | turnos totales |

## Qué cambia con `SCM_ENABLED=false`

El contrato del proyecto dice que con la bandera apagada el sistema debe funcionar **idéntico** y la
suite seguir en verde, y a la vez que la bandera **es el instrumento que mide el aporte del SCM** como
tercer brazo. Las dos cosas son ciertas si «idéntico» se lee como lo que es: **el piso de seguridad no
cambia**, no que la salida sea igual. Si la salida fuera igual, el brazo `tools_scm` no podría diferir
de `tools` y el aporte de Federico sería inmedible.

- **No cambia:** la puerta de identidad, la política, la relectura, el grounding, la abstención como
  resultado válido, y toda la suite en verde. Una comprobación de slots equivalente a
  `missing_evidence()` sostiene la pregunta en vez de la decisión.
- **Sí cambia, y es exactamente lo que `EV-06` mide:** la detección de contradicciones y la
  procedencia tipada. Con la bandera apagada esas aristas no existen y esos casos salen por el camino
  normal. **Nada replica `contradictions()`** — una comprobación de slots no lo hace.

## Consecuencias

- `AG-06` implementa una máquina de estados con transiciones explícitas y testeables sin LLM, igual
  que el motor de política. La prueba es que **cada arista del diagrama tenga un test**.
- La traza de `AG-12` lleva, por turno, la secuencia de etapas recorridas y la razón de cada
  transición —incluido el tipo de contradicción cuando hubo—. Eso alimenta `UI-03` y `EV-06`.
- `UI-03` tiene seis casillas que encender, una rotulada como extensión propia.

## Supuesto declarado

Que la sexta etapa sea la identidad es nuestra lectura del hueco, no una exigencia del reto. El reto
pide cinco. Añadimos una porque el contrato de seguridad ya le había dado reglas propias y porque
conviene que se vea.
