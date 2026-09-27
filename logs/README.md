# logs/

Dónde aterriza todo lo que el sistema escribe cuando corre. **El contenido no se versiona** — solo esta estructura y esta página.

Existe por una razón concreta del rubro: el reto evalúa observabilidad (slide 15) y pide poder demostrar que una acción **realmente ocurrió**. Sin un lugar fijo y con formato acordado, esa evidencia se dispersa en la consola y se pierde.

## Estructura

| Carpeta | Qué guarda | Formato |
|---|---|---|
| `logs/ingest/` | Corridas de ingesta desde S3: archivos descargados, fallos por archivo, duración | texto plano |
| `logs/build/` | Corridas de dbt y de los contratos de calidad: qué modelo corrió, qué test falló, qué fue a cuarentena | texto plano |
| `logs/agent/` | Log de aplicación de la API y del orquestador: errores con contexto, reintentos, degradaciones | JSONL |
| `logs/traces/` | **Una traza por turno de conversación.** Es la evidencia central del entregable | JSONL |
| `logs/eval/` | Corridas del harness: qué caso, qué brazo, qué desenlace | JSONL |

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

## Reglas

1. **Nada de datos personales en claro.** `document_number`, correo y teléfono van hasheados con `PII_HASH_SALT`; los nombres se truncan. El texto completo del cliente no se registra en nivel `INFO`.
2. **Nada se cae en silencio.** Toda llamada externa va en `try/except` y todo error real se escribe con contexto suficiente para diagnosticar después — no solo «algo falló».
3. **Retención:** trazas 30 días, ledger de acciones y expedientes de escalamiento 90 días. Declarado en `docs/05_security.md`.
4. **Un archivo por día**, nombrado `YYYY-MM-DD.jsonl`, para poder rotar y borrar por fecha sin leer el contenido.
