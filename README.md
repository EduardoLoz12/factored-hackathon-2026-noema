# NOEMA — Asistente de elegibilidad de crédito

**Factored AI & Data Hackathon 2026** · Equipo `noema` · Workflow: *Credit-Product Information & Eligibility*

> Cualquiera puede hacer que un modelo de lenguaje suene como un asesor bancario.
> Nosotros construimos el sistema que sabe cuándo ese asesor se está inventando algo — y lo puede probar con un número.

---

## Qué es

Un sistema de servicio al cliente bancario que atiende en **español y portugués**, verifica la identidad de quien escribe, responde **únicamente con cifras traídas de la base**, evalúa elegibilidad crediticia con un **modelo entrenado más una política determinista versionada**, **comprueba lo que ejecutó**, se **abstiene** cuando no sabe, y cuando necesita un humano le entrega un **expediente estructurado** en vez de la transcripción del chat.

No es un chatbot con documentos. El modelo de lenguaje conversa y explica; **nunca decide ni produce una cifra**.

## El principio

```
                 conversación          │          decisión
   ┌──────────────────────────────────┐│┌──────────────────────────────────┐
   │  LLM: entiende, aclara, explica  │││  Motor de reglas YAML + modelos  │
   │  Nunca emite un número propio    │││  Determinista, testeable sin LLM │
   └──────────────────────────────────┘│└──────────────────────────────────┘
```

Tres reglas que no se negocian en ninguna parte del código:

1. **Ninguna cifra sale del LLM.** Un `GroundingChecker` valida la respuesta final contra lo que devolvieron los tools y bloquea cualquier número huérfano.
2. **El LLM no decide elegibilidad.** Decide `agent/policies/eligibility_v1.yaml`.
3. **Toda escritura se vuelve a leer** antes de confirmarla. Si no coincide, no se afirma: se escala.

## Las cinco etapas

```
UNDERSTAND → ACCESS GUARD → DECIDE → ACT → VERIFY → ESCALATE
   idioma        documento    política  tools  relectura  expediente
   intención     + fecha nac. + modelos allowlist real     estructurado
   SCM-lite      3 intentos            idempotente
```

## Arquitectura

```
UI (Next.js)  ──HTTPS+JWT──▶  API FastAPI  ──▶  Postgres (gold + casos)
 /chat + panel Caja de Vidrio      │          ──▶  Modelos (MLflow registry)
 /console (expedientes)            │
 /analytics (métricas + datos)     │
                                   ▼
                        Databricks (Delta + MLflow)
                                   ▲
                      Parquet ── DuckDB + dbt ── Ingesta S3
```

El frontend **nunca** toca el lakehouse ni la base. Solo habla con la API.

## Cómo correrlo

```bash
cp .env.example .env     # rellenar credenciales (ver Data Dictionary, pág. 1)
make setup               # entorno y dependencias
make ingest              # S3 → data/bronze/*.parquet + manifest con checksums
make build               # dbt: bronze → silver → gold
make train               # baseline + modelo PD + capacidad de pago
make eval                # baseline vs tools vs tools+SCM
make serve               # API en local
```

Detalle completo en [`docs/06_runbook.md`](docs/06_runbook.md).

## Documentación

| Documento | Qué contiene |
|---|---|
| [`docs/00_challenge_brief.md`](docs/00_challenge_brief.md) | El rubro de Factored, decodificado |
| [`docs/01_data_audit.md`](docs/01_data_audit.md) | Auditoría real del dataset: dónde el diccionario y el dato no coinciden |
| [`docs/02_architecture.md`](docs/02_architecture.md) | Arquitectura y el porqué de cada decisión |
| [`docs/03_credit_policy.md`](docs/03_credit_policy.md) | Política de elegibilidad y escalamiento |
| [`docs/04_evaluation.md`](docs/04_evaluation.md) | Protocolo, baseline y resultados |
| [`docs/05_security.md`](docs/05_security.md) | Secretos, identidad, autorización, inyección, PII, red |
| [`docs/knowledge/findings.md`](docs/knowledge/findings.md) | Memoria de hallazgos del proyecto |
| [`docs/decisions/`](docs/decisions/) | ADRs |
| [`LIMITATIONS.md`](LIMITATIONS.md) | Qué falta y qué costaría hacerlo real |

## Equipo

- **Eduardo Lozada** — plataforma de datos, modelos, agente, evaluación, API y frontend.
- **Federico Vargas** — Semantic Cognition Matrix (`agent/cognition/`).

## Nota sobre los datos

El dataset es sintético y fue provisto por Factored para el hackathon. Aun así **se trata como si fuera información personal real**: los identificadores se hashean en logs y trazas, y la política de retención está escrita en `docs/05_security.md`.
