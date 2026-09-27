# logs/

Dos cosas distintas viven aquí, y conviene no confundirlas:

1. **Lo que el sistema escribe cuando corre** — trazas, errores, corridas. **No se versiona.**
2. **La bitácora de trabajo** (`logs/worklog/`) — lo que cada persona hizo en cada sesión. **Sí se versiona**, porque es documentación del avance.

Existen por una razón concreta del rubro: el reto evalúa observabilidad (slide 15) y pide poder demostrar que una acción **realmente ocurrió**. Sin un lugar fijo y con formato acordado, esa evidencia se dispersa en la consola y se pierde.

## Dónde va cada cosa

| Si estás escribiendo… | Va en | ¿Se versiona? |
|---|---|---|
| Salida de la ingesta desde S3 | `logs/ingest/` | No |
| Salida de dbt y de los contratos de calidad | `logs/build/` | No |
| Errores y eventos de la API y del orquestador | `logs/agent/` | No |
| **La traza de cada turno de conversación** | `logs/traces/` | No |
| El ledger de acciones ejecutadas | `logs/traces/actions.jsonl` | No |
| Corridas del harness de evaluación | `logs/eval/` | No |
| **Lo que hiciste hoy, qué decidiste, qué se rompió** | `logs/worklog/` | **Sí** |

**Nunca escribas logs fuera de `logs/`.** Ni en la raíz, ni junto al código, ni en `data/`. Si necesitas una carpeta nueva, agrégala aquí y documéntala.

## Estructura

| Carpeta | Qué guarda | Formato |
|---|---|---|
| `logs/ingest/` | Corridas de ingesta desde S3: archivos descargados, fallos por archivo, duración | texto plano |
| `logs/build/` | Corridas de dbt y de los contratos de calidad: qué modelo corrió, qué test falló, qué fue a cuarentena | texto plano |
| `logs/agent/` | Log de aplicación de la API y del orquestador: errores con contexto, reintentos, degradaciones | JSONL |
| `logs/traces/` | **Una traza por turno de conversación.** Es la evidencia central del entregable | JSONL |
| `logs/eval/` | Corridas del harness: qué caso, qué brazo, qué desenlace | JSONL |
| `logs/worklog/` | **Bitácora de trabajo, versionada.** Una entrada por persona y por día | Markdown |

## La traza por turno

Un registro por **etapa**, no por conversación. Campos obligatorios:

```json
{
  "trace_id": "uuid",
  "session_id": "sha256 truncado, nunca el identificador real",
  "turn": 3,
  "stage": "UNDERSTAND | ACCESS_GUARD | DECIDE | ACT | VERIFY | ESCALATE",
  "tool": "assess_credit_risk",
  "latency_ms": 412,
  "tokens_in": 1840,
  "tokens_out": 260,
  "cost_usd": 0.0091,
  "model_version": "noema_pd:v3",
  "policy_version": "eligibility_v1",
  "outcome": "resolved | clarified | abstained | escalated | blocked",
  "error": null,
  "ts": "2026-09-27T22:41:03Z"
}
```

De aquí salen tres de las métricas que el reto exige medir: resolución automática segura, acciones inseguras y costo por resolución. El panel Caja de Vidrio del frontend lee exactamente esta estructura.

## El ledger de acciones

`logs/traces/actions.jsonl` es **solo de adición**, nunca se edita ni se borra. Una línea por intento de escritura:

```json
{"trace_id":"…","action":"create_case","idempotency_key":"…",
 "payload_hash":"…","result":"ok","verified":true,"read_back":{…},"ts":"…"}
```

`verified` es el resultado de la etapa VERIFY: releímos el registro y comparamos campo por campo. **Si `verified` es falso, el agente no le afirmó nada al cliente.** Ese campo es la prueba de que la verificación existe y no es decorativa.

## La bitácora de trabajo — `logs/worklog/`

Es la única parte de `logs/` que se versiona, y es **parte del trabajo, no un extra**. El commit dice *qué cambió*; la bitácora dice *por qué, con qué fricción, y qué quedó a medias*. Sin ella, nadie —ni el otro integrante, ni un agente que retome mañana, ni el jurado— puede reconstruir cómo se llegó a lo que hay.

Un archivo por persona y por día: `logs/worklog/2026-09-27-eduardo.md`. Varias sesiones el mismo día se acumulan en el mismo archivo.

```bash
python -m scripts.worklog "Silver de productos y clientes"   # crea o agrega la sesión de hoy
python -m scripts.worklog --list                              # últimas entradas de todos
python -m scripts.worklog --show                              # la de hoy
```

Cada entrada responde cinco cosas, y ninguna es opcional:

| Bloque | Para qué sirve |
|---|---|
| **Ítems del checklist que moví** | Liga el trabajo al entregable. Si no moviste ninguno, dilo y explica por qué valía la pena |
| **Qué hice** | Para que el otro no tenga que leer el diff |
| **Decisiones que tomé** | Si cambia el contrato o la arquitectura, va **también** a `docs/decisions/` |
| **Qué se rompió o me frenó** | Si contradice una suposición previa, va **también** a `docs/knowledge/findings.md` |
| **Qué sigue** | Para que quien retome —tú mañana o un agente— no empiece de cero |

**Se rellena antes de cerrar la sesión y se commitea junto con el trabajo.** Una bitácora escrita tres días después es ficción.

## Cómo se conecta todo

| Pregunta | Dónde se responde |
|---|---|
| ¿Qué falta por hacer y de quién es? | `docs/knowledge/checklist.md` — `make checklist` |
| ¿Qué cambió, cuándo y quién? | `CHANGELOG.md` — `make changelog` |
| ¿Alguien se salió de su carril? | `docs/knowledge/contributions.md` — `make review` |
| ¿Por qué se hizo así? | `docs/decisions/` y `docs/knowledge/findings.md` |
| ¿Cómo fue el trabajo de ese día? | `logs/worklog/` |
| ¿El sistema realmente hizo lo que dijo? | `logs/traces/` y el ledger de acciones |

## Reglas

1. **Nada de datos personales en claro.** `document_number`, correo y teléfono van hasheados con `PII_HASH_SALT`; los nombres se truncan. El texto completo del cliente no se registra en nivel `INFO`.
2. **Nada se cae en silencio.** Toda llamada externa va en `try/except` y todo error real se escribe con contexto suficiente para diagnosticar después — no solo «algo falló».
3. **Retención:** trazas 30 días, ledger de acciones y expedientes de escalamiento 90 días. Declarado en `docs/05_security.md`.
4. **Un archivo por día**, nombrado `YYYY-MM-DD.jsonl`, para poder rotar y borrar por fecha sin leer el contenido.
