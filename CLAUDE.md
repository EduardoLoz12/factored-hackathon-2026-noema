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

| Área | Dueño |
|---|---|
| `agent/cognition/` y `tests/cognition/` (SCM-lite) | **Federico Vargas** |
| Todo lo demás | **Eduardo Lozada** |

**Si trabajas para Federico:** tu tarea completa está en **`docs/07_scm_spec.md`** y tu punto de partida es `agent/cognition/scm.py`, que ya tiene los tipos y los `NotImplementedError` marcando lo que falta. Usa el agente **`scm-cognition`**. No toques `data_platform/`, `ml/`, `agent/core/`, `agent/tools/`, `agent/policies/`, `api/`, `ui/` ni `eval/` — si necesitas un dato en el estado, pídelo.

**Si trabajas para Eduardo:** usa el agente **`hackathon-factored`**. Puedes andamiar el contrato de la capa de cognición, pero no la implementes: es de Federico, y su aporte se mide por separado.

La frontera es asimétrica a propósito y se verifica: `make review` marca cualquier commit que la cruce y acumula el resultado en `docs/knowledge/contributions.md`.

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
make review     # quién cambió qué, cruces de frontera, avance vs los 16 hitos
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

Regla: **si descubres algo que contradice una suposición, escríbelo en `docs/knowledge/findings.md` antes de seguir codificando.**

## Convenciones

- Código en inglés (`snake_case`); documentación y políticas en español.
- Ramas `feat/`, `fix/`, `docs/`. Commits convencionales. `main` protegida, PR + CI en verde.
- Toda decisión no obvia se registra como ADR en `docs/decisions/`.

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
