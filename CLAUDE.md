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

**Si trabajas para Federico:** tienes dos frentes y un agente para cada uno.
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
- **No hay modelo de riesgo posible: el techo es AUC = 0.50.** `days_past_due` es una Bernoulli(0.075) sorteada de forma independiente por producto de crédito. No se relaciona con el score (r = −0.004), ni con la utilización de línea (r = +0.005), ni con nada: diez variables, todas entre AUC 0.496 y 0.506; Cochran-Armitage sobre tramos de score p = 0.43. El `credit_score` sí es coherente —correlaciona 0.356 con el ingreso y ordena por segmento— así que el problema es la etiqueta, no el score (F-017). **Consecuencia:** ML-03 se entrena y se reporta que no discrimina; la elegibilidad la decide `eligibility_v1.yaml` sobre hechos verificables, no sobre un PD estimado. Esto refuerza la tesis en vez de debilitarla.
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

**D1 — 27-sep-2026, completado.** Repo público creado y publicado. Ingesta completa: 7 671 archivos, **23 495 188 filas**, 0 fallos, 5.35 GB → 1.50 GB Parquet. Auditoría con 9 hallazgos. 4 ADRs.

**Bloqueado:** el spike de Databricks espera `DATABRICKS_HOST` y `DATABRICKS_TOKEN`. El workflow de CI espera `gh auth refresh -h github.com -s workflow`.

**Listo para Federico:** spec (`docs/07_scm_spec.md`), esqueleto con tipos (`agent/cognition/scm.py`), fixtures (`tests/fixtures/scm_inputs.json`), 26 pruebas de aceptación y su agente `scm-cognition`. Puede trabajar recién clonado el repo, sin base de datos ni ingesta.

**Siguiente (D2):** contratos de calidad con pandera, reporte DQ a escala —confirmar si el «2 % de duplicados» existe— y capa silver.
