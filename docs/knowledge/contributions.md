# Bitácora de contribuciones

Generada por `make review`. Responde quién cambió qué, si respetó su frontera, y cómo va el avance contra los hitos del entregable.

Las revisiones más recientes van arriba.

---

## Revisión · 2026-10-05 14:35

42 commits · historial completo

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| Eduardo Lozada | 33 | API, agentes, cognición (SCM), contratos de datos, documentación, evaluación, fixtures, frontend, guardrails, herramientas, integración continua, modelos, multilingüe, observabilidad, orquestador, plataforma de datos, políticas, raíz del proyecto, utilidades |
| fedevargas93 | 9 | capacidad de pago, cognición (SCM), contratos de datos, documentación, modelos, plataforma de datos, raíz del proyecto, utilidades |

### Cruces de frontera

| Commit | Autor | Archivo | Área |
|---|---|---|---|
| `7a8785e` | fedevargas93 | `ml/model_cards/depth_experiment.json` | modelos |
| `7a8785e` | fedevargas93 | `ml/training/depth_experiment.py` | modelos |
| `4a95803` | fedevargas93 | `ml/model_cards/deep_interest.json` | modelos |
| `4a95803` | fedevargas93 | `ml/serving/client_analysis.py` | modelos |
| `4a95803` | fedevargas93 | `ml/serving/product_advisor.py` | modelos |
| `4a95803` | fedevargas93 | `ml/training/deep_interest.py` | modelos |
| `e3203c5` | fedevargas93 | `ml/model_cards/product_interest.json` | modelos |
| `e3203c5` | fedevargas93 | `ml/serving/product_advisor.py` | modelos |
| `e3203c5` | fedevargas93 | `ml/training/product_interest.py` | modelos |
| `b5eee82` | fedevargas93 | `scripts/review_contributions.py` | utilidades |
| `3ba73a2` | fedevargas93 | `scripts/generate_schemas.py` | utilidades |
| `3ba73a2` | fedevargas93 | `scripts/review_contributions.py` | utilidades |
| `3ba73a2` | fedevargas93 | `tests/data/test_feature_contract.py` | contratos de datos |
| `3ba73a2` | fedevargas93 | `tests/data/test_pipeline.py` | contratos de datos |

> Federico solo debe tocar `agent/cognition/` y `tests/cognition/`. Un cruce no es necesariamente un error, pero tiene que ser deliberado y conversado.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | existe |
| Transformaciones dbt | existe |
| Modelo baseline | existe |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | existe |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | existe |
| Herramientas del agente | existe |
| Orquestador 6 etapas | existe |
| Guardrails / grounding | existe |
| API | existe |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | existe |

**12 de 16 hitos iniciados.**

### Commits

- `c4beaa8` · 2026-10-05 · **Eduardo Lozada** — Nuevo (AG-05/UI-02): la identidad se verifica conversando, y la conversacion tiene ritmo
- `d8053c1` · 2026-10-05 · **Eduardo Lozada** — Nuevo (UI-04): tres conversaciones guiadas que corren el flujo real, y el agente por fin dice las cifras
- `a60e262` · 2026-10-05 · **Eduardo Lozada** — Mejora (UI-02/UI-03): la interfaz toma el diseno que armo Federico
- `8e18195` · 2026-10-05 · **Eduardo Lozada** — Mejora (UI-03): el panel pasa de un log de etapas a una auditoria paso a paso
- `49a0081` · 2026-10-05 · **Eduardo Lozada** — Nuevo (UI-08): base reducida, perfiles de demostracion y la auditoria de Federico en el panel
- `aed6905` · 2026-09-29 · **fedevargas93** — Docs (INF-03): incorpora la auditoria interactiva de bronze contra silver
- `81fd155` · 2026-10-05 · **Eduardo Lozada** — Docs (ENT-01/ENT-02): el protocolo de evaluacion y las limitaciones del cierre
- `2989f01` · 2026-10-05 · **Eduardo Lozada** — Nuevo (API-01/API-02, UI-02..UI-07): la API y la interfaz que el jurado usa, en un solo origen
- `529c9d9` · 2026-10-05 · **Eduardo Lozada** — Nuevo (EV-01..EV-06): el conjunto retenido, los tres brazos y la tabla que los compara
- `a626fd6` · 2026-10-05 · **Eduardo Lozada** — Nuevo (ML-11..ML-13): entra la propension comercial que Federico midio bien, y queda fuera lo que no paso su propio metodo
- `85a296a` · 2026-10-05 · **Eduardo Lozada** — Corrige (EV-06): la suite vuelve a correr con SCM_ENABLED=false, que es como se mide el tercer brazo
- `7a8785e` · 2026-10-01 · **fedevargas93** — Nuevo (ML-13): compara seis capas neuronales con control temporal del sobreajuste
- `4a95803` · 2026-09-30 · **fedevargas93** — Nuevo (ML-12): integra red profunda y política de Eduardo en el asesor por cliente
- `e3203c5` · 2026-09-30 · **fedevargas93** — Nuevo (ML-11): estima interés comercial y consulta cupos registrados por cliente
- `393ba32` · 2026-10-02 · **Eduardo Lozada** — Docs (INF-07): contrato de trabajo para el agente de Federico, con el nivel de validador que exige cada entregable
- `7cf87b3` · 2026-10-02 · **Eduardo Lozada** — Docs (INF-07): control de cambios al dia, y el generador deja de romper su propio commit
- `ee3f5d3` · 2026-10-02 · **Eduardo Lozada** — Nuevo (AG-03..AG-10): el ciclo del agente cierra de punta a punta
- `9c0175d` · 2026-09-30 · **Eduardo Lozada** — Docs (INF-07): tres avisos para Federico sobre la capa de datos, dos de ellos bugs
- `337be65` · 2026-09-30 · **Eduardo Lozada** — Corrige (ML-01): todo importe del feature store pasa a USD, y se retiran cuatro variables que repetian informacion
- `3ce2b6e` · 2026-09-30 · **Eduardo Lozada** — Docs (INF-07): control de cambios regenerado con el trabajo del dia 4
- `32a1d7b` · 2026-09-30 · **Eduardo Lozada** — Nuevo (AG-01/AG-02): la elegibilidad se calcula con una politica versionada, porque el dataset no permite aprenderla
- `232d041` · 2026-09-29 · **Eduardo Lozada** — Docs (ML-03): days_past_due no son dias de mora y fraud_score no sale de un modelo — ningun objetivo del dataset es aprendible
- `d95ab93` · 2026-09-29 · **Eduardo Lozada** — Corrige (ML-01/ML-02): la cohorte de trabajo vuelve a 76 906 clientes — el filtro que la bajaba a 7 078 no se sostiene
- `89c75a6` · 2026-09-29 · **Eduardo Lozada** — Nuevo (ML-01/ML-02): feature store con corte temporal honesto y baseline que no discrimina
- `7dfd52d` · 2026-09-29 · **Eduardo Lozada** — Corrige (INF-06): dos de los tres agentes no se registraban por culpa de los finales de linea
- `1d78dd2` · 2026-09-29 · **Eduardo Lozada** — Docs (INF-07): bitacora del dia, control de cambios y guia de lo que cambio para Federico
- `c6324a9` · 2026-09-29 · **Eduardo Lozada** — Docs (ML-01/ML-03): la etiqueta de riesgo es un sorteo — no hay modelo de riesgo posible
- `e5c411a` · 2026-09-29 · **Eduardo Lozada** — Limpieza: el id de usuario que genera dbt no se versiona
- `c157a5c` · 2026-09-29 · **Eduardo Lozada** — Docs (DAT-04/ML-01): segunda pasada sobre nulos y llaves — cinco hallazgos que cambian el plan del modelo
- `1912b85` · 2026-09-28 · **fedevargas93** — Docs: acredita a Codex como agente colaborador de Federico
- `f8ef800` · 2026-09-28 · **fedevargas93** — Docs (ML-04): agrega entrega técnica para el equipo
- `f763872` · 2026-09-28 · **fedevargas93** — Docs (ML-04): registra resultados del modelo y limpieza de datos
- `b5eee82` · 2026-09-28 · **fedevargas93** — Docs (INF-07): registra avance y fronteras de la entrega de Federico
- `3ba73a2` · 2026-09-28 · **fedevargas93** — Nuevo (DAT-03/ML-04/SCM-02): completa datos, capacidad y cognición de Federico
- `05d54d5` · 2026-09-28 · **Eduardo Lozada** — Corrige: el formateador y el limite de ancho se contradecian en una prueba
- `0a76652` · 2026-09-27 · **Eduardo Lozada** — Mejora: Federico pasa a ser dueno de la limpieza, el ETL y la capacidad de pago
- `637dd0f` · 2026-09-27 · **Eduardo Lozada** — Nuevo (INF-07): bitacora de trabajo, carpeta de logs y control de cambios legible
- `cc4b84f` · 2026-09-27 · **Eduardo Lozada** — feat(INF-07): checklist vivo, plan por dias, logs y control de cambios
- `e091828` · 2026-09-27 · **Eduardo Lozada** — fix(build): declarar paquetes explícitos — pip install -e fallaba
- `93cedac` · 2026-09-27 · **Eduardo Lozada** — feat: onboarding de Federico, contrato del SCM y revisión de contribuciones

---
## Revisión · 2026-09-29 10:32

16 commits · historial completo

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| Eduardo Lozada | 11 | API, agentes, cognición (SCM), contratos de datos, documentación, evaluación, fixtures, frontend, guardrails, herramientas, integración continua, modelos, multilingüe, observabilidad, orquestador, plataforma de datos, políticas, raíz del proyecto, utilidades |
| fedevargas93 | 5 | capacidad de pago, cognición (SCM), contratos de datos, documentación, plataforma de datos, raíz del proyecto, utilidades |

### Cruces de frontera

| Commit | Autor | Archivo | Área |
|---|---|---|---|
| `b5eee82` | fedevargas93 | `scripts/review_contributions.py` | utilidades |
| `3ba73a2` | fedevargas93 | `scripts/generate_schemas.py` | utilidades |
| `3ba73a2` | fedevargas93 | `scripts/review_contributions.py` | utilidades |
| `3ba73a2` | fedevargas93 | `tests/data/test_feature_contract.py` | contratos de datos |
| `3ba73a2` | fedevargas93 | `tests/data/test_pipeline.py` | contratos de datos |

> Federico solo debe tocar `agent/cognition/` y `tests/cognition/`. Un cruce no es necesariamente un error, pero tiene que ser deliberado y conversado.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | existe |
| Transformaciones dbt | existe |
| Modelo baseline | pendiente |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | existe |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | pendiente |
| Herramientas del agente | pendiente |
| Orquestador 6 etapas | pendiente |
| Guardrails / grounding | pendiente |
| API | pendiente |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | pendiente |

**5 de 16 hitos iniciados.**

### Commits

- `c6324a9` · 2026-09-29 · **Eduardo Lozada** — Docs (ML-01/ML-03): la etiqueta de riesgo es un sorteo — no hay modelo de riesgo posible
- `e5c411a` · 2026-09-29 · **Eduardo Lozada** — Limpieza: el id de usuario que genera dbt no se versiona
- `c157a5c` · 2026-09-29 · **Eduardo Lozada** — Docs (DAT-04/ML-01): segunda pasada sobre nulos y llaves — cinco hallazgos que cambian el plan del modelo
- `1912b85` · 2026-09-28 · **fedevargas93** — Docs: acredita a Codex como agente colaborador de Federico
- `f8ef800` · 2026-09-28 · **fedevargas93** — Docs (ML-04): agrega entrega técnica para el equipo
- `f763872` · 2026-09-28 · **fedevargas93** — Docs (ML-04): registra resultados del modelo y limpieza de datos
- `b5eee82` · 2026-09-28 · **fedevargas93** — Docs (INF-07): registra avance y fronteras de la entrega de Federico
- `3ba73a2` · 2026-09-28 · **fedevargas93** — Nuevo (DAT-03/ML-04/SCM-02): completa datos, capacidad y cognición de Federico
- `05d54d5` · 2026-09-28 · **Eduardo Lozada** — Corrige: el formateador y el limite de ancho se contradecian en una prueba
- `0a76652` · 2026-09-27 · **Eduardo Lozada** — Mejora: Federico pasa a ser dueno de la limpieza, el ETL y la capacidad de pago
- `637dd0f` · 2026-09-27 · **Eduardo Lozada** — Nuevo (INF-07): bitacora de trabajo, carpeta de logs y control de cambios legible
- `cc4b84f` · 2026-09-27 · **Eduardo Lozada** — feat(INF-07): checklist vivo, plan por dias, logs y control de cambios
- `e091828` · 2026-09-27 · **Eduardo Lozada** — fix(build): declarar paquetes explícitos — pip install -e fallaba
- `93cedac` · 2026-09-27 · **Eduardo Lozada** — feat: onboarding de Federico, contrato del SCM y revisión de contribuciones
- `d44be93` · 2026-09-27 · **Eduardo Lozada** — chore: repo en la raíz de la carpeta de trabajo + resumen del manifest
- `bef23c5` · 2026-09-27 · **Eduardo Lozada** — feat: scaffold del proyecto, ingesta S3 y auditoría del dataset

---
## Revisión · 2026-09-28 17:59

1 commits · desde `1.day`

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| fedevargas93 | 1 | capacidad de pago, cognición (SCM), contratos de datos, documentación, gobierno, plataforma de datos, raíz del proyecto |

### Fronteras

Sin cruces. Cada quien trabajó dentro de su área.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | existe |
| Transformaciones dbt | existe |
| Modelo baseline | pendiente |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | existe |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | pendiente |
| Herramientas del agente | pendiente |
| Orquestador 6 etapas | pendiente |
| Guardrails / grounding | pendiente |
| API | pendiente |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | pendiente |

**5 de 16 hitos iniciados.**

### Commits

- `3ba73a2` · 2026-09-28 · **fedevargas93** — Nuevo (DAT-03/ML-04/SCM-02): completa datos, capacidad y cognición de Federico

---
## Revisión · 2026-09-27 17:47

6 commits · historial completo

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| Eduardo Lozada | 6 | API, agentes, cognición (SCM), documentación, evaluación, fixtures, frontend, guardrails, herramientas, integración continua, modelos, multilingüe, observabilidad, orquestador, plataforma de datos, políticas, raíz del proyecto, utilidades |

### Fronteras

Sin cruces. Cada quien trabajó dentro de su área.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | pendiente |
| Transformaciones dbt | pendiente |
| Modelo baseline | pendiente |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | pendiente |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | pendiente |
| Herramientas del agente | pendiente |
| Orquestador 6 etapas | pendiente |
| Guardrails / grounding | pendiente |
| API | pendiente |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | pendiente |

**2 de 16 hitos iniciados.**

### Commits

- `637dd0f` · 2026-09-27 · **Eduardo Lozada** — Nuevo (INF-07): bitacora de trabajo, carpeta de logs y control de cambios legible
- `cc4b84f` · 2026-09-27 · **Eduardo Lozada** — feat(INF-07): checklist vivo, plan por dias, logs y control de cambios
- `e091828` · 2026-09-27 · **Eduardo Lozada** — fix(build): declarar paquetes explícitos — pip install -e fallaba
- `93cedac` · 2026-09-27 · **Eduardo Lozada** — feat: onboarding de Federico, contrato del SCM y revisión de contribuciones
- `d44be93` · 2026-09-27 · **Eduardo Lozada** — chore: repo en la raíz de la carpeta de trabajo + resumen del manifest
- `bef23c5` · 2026-09-27 · **Eduardo Lozada** — feat: scaffold del proyecto, ingesta S3 y auditoría del dataset

---
## Revisión · 2026-09-27 17:38

5 commits · historial completo

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| Eduardo Lozada | 5 | API, agentes, cognición (SCM), documentación, evaluación, fixtures, frontend, guardrails, herramientas, integración continua, modelos, multilingüe, observabilidad, orquestador, plataforma de datos, políticas, raíz del proyecto, utilidades |

### Fronteras

Sin cruces. Cada quien trabajó dentro de su área.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | pendiente |
| Transformaciones dbt | pendiente |
| Modelo baseline | pendiente |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | pendiente |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | pendiente |
| Herramientas del agente | pendiente |
| Orquestador 6 etapas | pendiente |
| Guardrails / grounding | pendiente |
| API | pendiente |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | pendiente |

**2 de 16 hitos iniciados.**

### Commits

- `cc4b84f` · 2026-09-27 · **Eduardo Lozada** — feat(INF-07): checklist vivo, plan por dias, logs y control de cambios
- `e091828` · 2026-09-27 · **Eduardo Lozada** — fix(build): declarar paquetes explícitos — pip install -e fallaba
- `93cedac` · 2026-09-27 · **Eduardo Lozada** — feat: onboarding de Federico, contrato del SCM y revisión de contribuciones
- `d44be93` · 2026-09-27 · **Eduardo Lozada** — chore: repo en la raíz de la carpeta de trabajo + resumen del manifest
- `bef23c5` · 2026-09-27 · **Eduardo Lozada** — feat: scaffold del proyecto, ingesta S3 y auditoría del dataset

---
## Revisión · 2026-09-27 17:34

4 commits · historial completo

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| Eduardo Lozada | 4 | API, agentes, cognición (SCM), documentación, evaluación, fixtures, frontend, guardrails, herramientas, integración continua, modelos, multilingüe, observabilidad, orquestador, plataforma de datos, políticas, raíz del proyecto, utilidades |

### Fronteras

Sin cruces. Cada quien trabajó dentro de su área.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | pendiente |
| Transformaciones dbt | pendiente |
| Modelo baseline | pendiente |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | pendiente |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | pendiente |
| Herramientas del agente | pendiente |
| Orquestador 6 etapas | pendiente |
| Guardrails / grounding | pendiente |
| API | pendiente |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | pendiente |

**2 de 16 hitos iniciados.**

### Commits

- `e091828` · 2026-09-27 · **Eduardo Lozada** — fix(build): declarar paquetes explícitos — pip install -e fallaba
- `93cedac` · 2026-09-27 · **Eduardo Lozada** — feat: onboarding de Federico, contrato del SCM y revisión de contribuciones
- `d44be93` · 2026-09-27 · **Eduardo Lozada** — chore: repo en la raíz de la carpeta de trabajo + resumen del manifest
- `bef23c5` · 2026-09-27 · **Eduardo Lozada** — feat: scaffold del proyecto, ingesta S3 y auditoría del dataset

---
## Revisión · 2026-09-27 17:16

2 commits · historial completo

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| Eduardo Lozada | 2 | API, agentes, cognición (SCM), documentación, evaluación, fixtures, frontend, guardrails, herramientas, integración continua, modelos, multilingüe, observabilidad, orquestador, plataforma de datos, políticas, raíz del proyecto |

### Fronteras

Sin cruces. Cada quien trabajó dentro de su área.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | pendiente |
| Transformaciones dbt | pendiente |
| Modelo baseline | pendiente |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | pendiente |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | pendiente |
| Herramientas del agente | pendiente |
| Orquestador 6 etapas | pendiente |
| Guardrails / grounding | pendiente |
| API | pendiente |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | pendiente |

**2 de 16 hitos iniciados.**

### Commits

- `d44be93` · 2026-09-27 · **Eduardo Lozada** — chore: repo en la raíz de la carpeta de trabajo + resumen del manifest
- `bef23c5` · 2026-09-27 · **Eduardo Lozada** — feat: scaffold del proyecto, ingesta S3 y auditoría del dataset

---
## Revisión · 2026-09-27 17:14

2 commits · historial completo

| Autor | Commits | Áreas tocadas |
|---|---:|---|
| Eduardo Lozada | 2 | API, agentes, cognición (SCM), documentación, evaluación, fixtures, frontend, guardrails, herramientas, integración continua, modelos, multilingüe, observabilidad, orquestador, plataforma de datos, políticas, raíz del proyecto |

### Fronteras

Sin cruces. Cada quien trabajó dentro de su área.

### Avance contra los hitos del entregable

| Hito | Estado |
|---|---|
| Ingesta S3 → bronze | existe |
| Contratos de calidad | pendiente |
| Transformaciones dbt | pendiente |
| Modelo baseline | pendiente |
| Modelo de riesgo (PD) | pendiente |
| Capacidad de pago | pendiente |
| Servicio de predicción | pendiente |
| SCM (Federico) | existe |
| Motor de reglas | pendiente |
| Herramientas del agente | pendiente |
| Orquestador 6 etapas | pendiente |
| Guardrails / grounding | pendiente |
| API | pendiente |
| Frontend | pendiente |
| Generador de casos | pendiente |
| Harness de evaluación | pendiente |

**2 de 16 hitos iniciados.**

### Commits

- `d44be93` · 2026-09-27 · **Eduardo Lozada** — chore: repo en la raíz de la carpeta de trabajo + resumen del manifest
- `bef23c5` · 2026-09-27 · **Eduardo Lozada** — feat: scaffold del proyecto, ingesta S3 y auditoría del dataset

---
