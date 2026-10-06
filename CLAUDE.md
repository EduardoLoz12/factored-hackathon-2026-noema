# CLAUDE.md — factored-hackathon-2026-noema

Contrato operativo del proyecto. Léelo antes de tocar código.

## Qué es esto

Sistema de servicio al cliente bancario para el **Factored AI & Data Hackathon 2026**.
Workflow elegido: **Credit-Product Information & Eligibility** (1 de 4 permitidos).

- **Equipo:** `noema` — Eduardo Lozada + Federico Vargas
- **Cierre:** 5-oct-2026, 23:59 hora Colombia. Premiación 16-oct.
- **Entregables:** repo público · URL desplegada · 5 slides · video ≤3 min → `hackathon.admin@factored.ai`

Tesis: **separar la conversación de la decisión**. El LLM conversa y explica; nunca produce una cifra ni decide una elegibilidad.

## Reglas no negociables

1. **Ninguna cifra sale del LLM.** Toda cifra viene de un tool que consultó la base. El `GroundingChecker` valida la respuesta final contra los valores devueltos por los tools de ese turno y bloquea si aparece un número huérfano.
2. **El LLM no decide elegibilidad.** Decide `agent/policies/eligibility_v1.yaml`. La política se testea sin LLM.
3. **Toda escritura se vuelve a leer** antes de confirmarle nada al cliente. Si no coincide, no se afirma: se escala.
4. **Nada se cae en silencio.** Toda llamada externa (LLM, DB, modelo, S3) va en `try/except`, con fallback visible al usuario y log con contexto suficiente para diagnosticar.
5. **Falla cerrado.** Si el modelo de riesgo no carga, el sistema no aprueba nada: escala y lo dice.
6. **Cero secretos en git.** `.env` y `materiales/` fuera. `gitleaks` corre en pre-commit y en CI.
7. **Abstenerse es un resultado válido**, se mide aparte y no se penaliza.

## Frontera de responsabilidades — léelo antes de escribir código

| Área | Dueño | Spec |
|---|---|---|
| `data_platform/` — limpieza, ETL, silver y gold | **Federico Vargas** | `docs/09_etl_spec.md` |
| `ml/training/capacity.py` — capacidad de pago | **Federico Vargas** | `docs/09_etl_spec.md` §5.5 |
| `agent/cognition/` y `tests/cognition/` — SCM-lite | **Federico Vargas** | `docs/07_scm_spec.md` |
| Modelos de riesgo, agente, evaluación, API, frontend y entregables | **Eduardo Lozada** | — |

**Si trabajas para Federico:** empieza por `docs/13_instrucciones_para_el_agente_de_federico.md` — qué leer, qué validador exige cada entregable, dónde firmar los hallazgos y qué loguear. Luego tienes dos frentes y un agente para cada uno.
- Datos y ETL → agente **`data-etl`**, spec `docs/09_etl_spec.md`. Son 15 ítems: `DAT-03` a `DAT-14` y `ML-04`.
- Cognición → agente **`scm-cognition`**, spec `docs/07_scm_spec.md`. Son 8 ítems: `SCM-01` a `SCM-08`.

No toques `agent/core/`, `agent/tools/`, `agent/policies/`, `agent/guardrails/`, `ml/training/pd_lightgbm.py`, `ml/training/baseline_logreg.py`, `eval/`, `api/` ni `ui/`.

**Si trabajas para Eduardo:** usa el agente **`hackathon-factored`**. Puedes andamiar contratos de las capas de Federico —esqueletos, tipos, pruebas de aceptación— pero no las implementes: su aporte se mide por separado.

`make review` marca cualquier commit que cruce una frontera y acumula el resultado en `docs/knowledge/contributions.md`.

**Dependencia crítica:** el modelo de riesgo (Eduardo, D4) se entrena sobre `credit_features_asof` (Federico, D3). Es el único punto donde una demora de uno bloquea al otro. La prueba `tests/data/test_feature_contract.py` verifica mecánicamente que esa tabla no traiga columnas con fuga de información.

**Contrato del SCM** — `agent/cognition/scm.py` expone `SemanticState` con exactamente cuatro métodos públicos:

```python
assert_fact(subject, predicate, value, source, confidence) -> None
missing_evidence() -> set[str]
contradictions() -> list[Contradiction]
snapshot() -> dict
```

Con `SCM_ENABLED=false` el sistema debe funcionar idéntico y toda la suite de tests debe seguir en verde. **Esa bandera no es cortesía: es el instrumento que mide el aporte del SCM** como tercer brazo de la evaluación (`baseline` · `tools` · `tools_scm`).

Las pruebas de aceptación de Federico son `tests/cognition/test_scm_contract.py`. Hoy se saltan solas; cuando pasen todas, su parte está terminada.

## Comandos

```bash
make setup      # entorno, dependencias, pre-commit
make ingest     # S3 → data/bronze/*.parquet + manifest con checksums
make audit      # perfil de calidad de las 13 tablas → docs/01_data_audit.md
make build      # dbt: bronze → silver → gold (perfil duckdb por defecto)
make train      # baseline logreg + PD LightGBM + capacidad → MLflow
make eval       # harness: baseline vs tools vs tools+SCM
make checklist  # estado de los 75 ítems del entregable, por dueño y por día
make review     # quién cambió qué, cruces de frontera, + checklist
make serve      # API FastAPI local
make test       # pytest
make check      # lint + tests + gitleaks
```

## Estado del dataset (auditado, no supuesto)

S3 read-only de Factored: **5.4 GB, 7 683 objetos, 13 tablas**, 2023-06-17 → 2026-06-17.
Seis dimensiones planas + siete hechos particionados `year=/month=/day=`.

Hallazgos que cambian decisiones — el detalle vive en `docs/01_data_audit.md`:

- **Los transcripts no sirven como corpus**: 2 plantillas únicas, 1 intent, cero portugués, placeholders sin rellenar (`{monto}`, `{moneda}`, `{limite}`). Se usan como **plantillas** para generar los casos de evaluación, no como texto de entrenamiento.
- **Sí hay etiquetas de riesgo**: `products.days_past_due` con 125 350 no nulos, ~15 % en mora.
- **El diccionario miente en 7 puntos**: enums en español, MXN inexistente, cero duplicados donde promete 2 %, nulos estructurales muy distintos al 5 % declarado, `contact_reason` duplicada de `reason_category`.
- **No hay enums mezclados español/inglés.** Cada columna categórica está en un solo idioma —`product_type` en español, `transaction_type` en inglés— y la normalización de silver no colapsa ningún nivel (F-016). El `CASE` se conserva por defensivo, no porque haga algo.
- **`registration_branch_id` no es una llave foránea**: 150 000 valores distintos para 150 000 clientes, contra 350 sucursales. La sucursal del cliente se deriva por `products.opening_branch_id`, que sí es válida al 100 % (F-012).
- **Ninguna columna del dataset es un objetivo supervisado aprendible.** Probado sobre seis candidatos (F-017, F-019, F-020).
  - `days_past_due` **no son días de mora**: toma siete valores —0, 15, 30, 60, 90, 120, 180— y las seis cubetas no-cero son equiprobables (χ² = 4.51, gl 5, **p = 0.48**). Una cartera real decae por tasas de traspaso. No existe calendario de pagos con el cual calcularla, y un producto con 180 días de mora tiene el mismo historial de pagos que uno al día: 2.91 pagos contra 2.87.
  - `fraud_score` **no es la salida de un modelo**: es Uniforme(0,100) si hay fraude y Uniforme(0,30) si no. σ 28.948 y 8.661 contra 28.868 y 8.660 teóricas, curtosis −1.203 y −1.201 contra −1.2. Su AUC de 0.8469 la explica ese esquema sin residuo (teórica 0.8464).
  - Cliente inactivo 0.505, `sla_breached` 0.500, NPS detractor 0.504. Conversión de campaña 0.810, pero es dependencia de embudo.
  - El `credit_score` **sí** es coherente: correlaciona 0.356 con el ingreso y ordena por segmento. El problema es la etiqueta, no el score.
  - **Consecuencia:** ML-03 se entrena y se reporta que no discrimina, con esta evidencia. La elegibilidad la decide `eligibility_v1.yaml` sobre hechos verificables, no sobre un PD estimado. Esto refuerza la tesis: ni el LLM ni el modelo deciden.
  - **Regla:** antes de tratar una columna como objetivo, mirar su distribución **por clase**. Siete valores equiprobables, o dos uniformes de distinto rango, no son fenómenos medidos.
- El universo etiquetable son 84 926 clientes con producto de crédito, no 150 000; la tasa de mora a 90 días es 10.71 % por cliente y 7.52 % por producto (F-015).

Regla: **si descubres algo que contradice una suposición, escríbelo en `docs/knowledge/findings.md` antes de seguir codificando.**

## Cómo se sigue el avance

| Archivo | Qué es |
|---|---|
| `docs/checklist.json` | La lista canónica: 75 ítems con dueño, día y evidencia. Se edita a mano solo para agregar o reformular tareas. |
| `docs/knowledge/checklist.md` | El estado, generado con `make checklist`. Un ítem pasa a `avanzado` cuando existe su archivo de evidencia y a `terminado` cuando deja de ser esqueleto. |
| `docs/knowledge/plan_por_dias.md` | Qué ítems debe cerrar cada día y las reglas de corte. |
| `docs/knowledge/contributions.md` | Quién cambió qué y si respetó su frontera. |
| `CHANGELOG.md` | Control de cambios: qué cambió, cuándo, quién y qué ítem movió. Se genera con `make changelog`. |
| `logs/` | Dónde escribe el sistema cuando corre: ingesta, dbt, agente, **trazas por turno** y ledger de acciones. El contenido no se versiona; su estructura y reglas están en `logs/README.md`. |

**Antes de una tarea**, identifica qué ítem mueve. **Al terminarla**, corre `make checklist` y nombra el ítem en el commit: `feat(DAT-06): ...`. Si la evidencia es que unas pruebas pasan y no que un archivo exista, márcalo con `python -m scripts.checklist --done ID --note "..."`.

## Convenciones

- Código en inglés (`snake_case`); documentación, políticas y **mensajes de commit** en español.
- **Mensajes de commit legibles, sin jerga.** Formato: `Tipo (ÍTEM): qué cambió, en español`.
  Tipos: `Nuevo`, `Corrige`, `Mejora`, `Docs`, `Pruebas`, `Infra`, `Limpieza`, `Revierte`.
  Bien: `Nuevo (DAT-08): la capa silver convierte todos los montos a dólares con la tasa del día`.
  Mal: `feat(silver): normalize enums`.
  El asunto debe entenderse **sin abrir el diff**. El cuerpo explica el porqué, no el cómo.
- Ramas `trabajo/`, `arreglo/`, `docs/`. `main` protegida, PR + CI en verde.
- Toda decisión no obvia se registra como ADR en `docs/decisions/`.

## Antes de cerrar cualquier sesión de trabajo

Tres cosas, siempre, en este orden:

```bash
python -m scripts.worklog "en qué trabajaste"   # bitácora: decisiones, qué se rompió, qué sigue
make checklist                                   # el ítem avanza solo si el trabajo existe
git commit -m "Nuevo (ÍTEM): descripción legible en español"
```

**La bitácora es parte del trabajo, no un extra.** El commit dice qué cambió; la bitácora dice por qué, con qué fricción y qué quedó a medias. Sin ella, quien retome mañana —el otro integrante o un agente— empieza de cero. Se rellena **antes** de cerrar, no tres días después.

Los logs que el sistema escribe al correr van **siempre** dentro de `logs/`, en la carpeta que corresponda (`ingest/`, `build/`, `agent/`, `traces/`, `eval/`). Nunca en la raíz ni junto al código. Las reglas de formato, PII y retención están en `logs/README.md`.

## Dónde vive el proyecto

La raíz del repo es **`C:\Users\eduar\Factored AI & DATA Hackathon`** — la misma carpeta de trabajo de Eduardo, no una subcarpeta. Al lado del código, sin versionar:

- `materiales/` — PDFs originales del reto (contienen las llaves de AWS en texto plano), transcripciones, y `referencia/` con el código que envió Federico.
- `documentos/` — los Word de estrategia generados para el equipo.
- `data/` — bronze en Parquet, 1.5 GB.

**Los push se hacen solo cuando Eduardo lo pide.** Commits locales sí, `git push` no, salvo que lo diga explícitamente.

## Estado actual

**Proyecto terminado en código — 5-oct-2026.** Checklist **65/79** en el último `make checklist` (antes de las dos últimas funciones; ver nota). Faltan el video, el envío y las integraciones declaradas.

- **Qué está entregado:** chat con identidad verificada, política de siete reglas, tres brazos de evaluación, interfaz en inglés con respuestas en el idioma del cliente, tres conversaciones guiadas, y consulta de productos propios (saldo, límite, tasa y cuota estimada) con sesión verificada.
- **URL pública:** https://noema.5-78-236-186.sslip.io — Hetzner, servicio `noema.service`, puerto 8100, tope de memoria 320 MB. El servidor también corre GFV y el trading bot: no tocar sus servicios.
- **Evaluación de tres brazos** (`make cases` y `make eval`), 154 casos, modelo real `claude-haiku-4-5`. Español: solo modelo 85 de 87 con cifras sin respaldo; con tools 0; con SCM 0 y 6 contradicciones declaradas. Portugués y adversarial, ver `eval/results/comparacion.md`.
- **Pruebas:** 1 000 pruebas recolectadas, 50 de API. Ruff limpio.
- **Presentación:** `docs/presentacion/noema_deck_v3.pptx` (11 diapositivas, en inglés). El plan en `docs/presentacion/plan.md` es de la versión anterior de diez diapositivas.
- **Pendiente de entrega:** `ENT-04` video ≤3 min (llamada en vivo con ambos presentando el deck), `ENT-05` envío a `hackathon.admin@factored.ai`. `ENT-03` (diapositivas) queda hecho con el v3.
- **Pendiente técnico:** `DAT-13` y `DAT-14` esperan credenciales de Databricks (ADR-0002); `INF-08` igual. `ML-05` a `ML-10` quedaron fuera por tiempo. `UI-01` (Next.js) no aplica: la interfaz es una página servida por la API. Todo en `LIMITATIONS.md`.
- **Capacidad de pago:** el proxy por flujo de caja (Federico) tiene una ganancia modesta sobre su base y se abstiene en la mayoría de clientes. La cuota máxima por ingreso está en curso y no está conectada a las reglas 3 y 5 todavía.
- **Estimación de cuota:** la base no registra la cuota ni el plazo original. La cuota de un préstamo es una estimación con el plazo supuesto de la política, y la respuesta lo dice.

## Operación: ramas, merge y despliegue

- **`main` está protegido.** Todo cambio entra por PR. Federico subió siete commits directo a `main` el 2 y 3 de octubre; se revirtieron en `fccc096` (ver `docs/knowledge/findings.md`).
- **CI puede quedar en cola** (runners hospedados por GitHub). Si ocurre, el merge con `--admin` solo se hace con aprobación explícita de Eduardo, y se deja escrito.
- **Despliegue:** el Hetzner sirve `main`. En el servidor, el clon es superficial: `git fetch --depth=1 origin main && git reset --hard FETCH_HEAD`, luego `systemctl restart noema.service`, y comprobar que `gfv-bot.service` sigue activo.
- **Antes de una operación destructiva** (reset, rollback) se crea un respaldo local `respaldo/<rama>` y se revierte con commits, nunca con `push --force`.

## Idioma

- **La interfaz es en inglés**: página, panel, etiquetas de fase, títulos de eventos y textos de conversación.
- **El chatbot responde en el idioma del cliente.** El idioma se detecta por marcas de cada mensaje, y la conversación 2 es en portugués de punta a punta.
- **Los motivos de rechazo del motor están en español.** En conversaciones en portugués se traducen por plantilla (`api/redaccion.py`, `MOTIVOS_PT`) conservando las cifras, porque el anclaje compara números.
- **Los documentos del repo (`docs/`, README) siguen en español.** Traducirlos está pendiente y no se ha pedido.

## Validación antes de empezar cualquier arreglo

- `node --check` **no detecta** funciones usadas y no definidas en el JavaScript de la página. Un reemplazo de bloque dejó `espera`, `burbuja` y `linea` sin definir, y solo se vio en el navegador. Para la interfaz se valida en Chrome headless por el protocolo de depuración: cargar la página, pulsar el botón y revisar `Runtime.exceptionThrown`.
- Antes de decir que algo funciona, se corre el flujo completo contra la base de demostración. Una prueba unitaria no alcanza para el chat.
