# Checklist del entregable

Generado por `make checklist` contra el estado real del repo. Cuando alguien crea o completa un archivo de evidencia, el ítem avanza solo en la siguiente corrida. **No editar estados a mano aquí** — usar `python -m scripts.checklist --done ID --note "..."`.

Última evaluación: 2026-10-05 15:08

Estados: `[ ]` falta · `[~]` avanzado · `[x]` terminado

## Avance global — 65/79 `████████████████████░░░░`

**65 terminado · 4 avanzado · 10 falta**

| Dueño | Terminado | Avanzado | Falta | Total |
|---|---:|---:|---:|---:|
| Eduardo | 44 | 1 | 10 | 55 |
| Federico | 21 | 3 | 0 | 24 |

## Plataforma de datos — 12/15 `██████████░░`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `DAT-01` | Ingesta S3 a bronze, con manifest y checksums | Eduardo | D1 · 27-sep | Eduardo · 2026-09-27 |
| [x] | `DAT-02` | Resumen versionable del manifest | Eduardo | D1 · 27-sep | Eduardo · 2026-09-27 |
| [x] | `DAT-03` | Contratos de esquema por tabla (pandera) | Federico | D2 · 28-sep | Eduardo · 2026-09-29 |
| [x] | `DAT-04` | Reporte de calidad a escala: duplicados, nulos, huerfanos de FK, telefono vs pais | Federico | D2 · 28-sep | Eduardo · 2026-09-29 |
| [x] | `DAT-05` | Cuarentena de registros que violan contrato | Federico | D2 · 28-sep | fedevargas93 · 2026-09-28 |
| [x] | `DAT-06` | dbt configurado con perfil duckdb | Federico | D2 · 28-sep | fedevargas93 · 2026-09-28 |
| [x] | `DAT-07` | Silver: normalizacion de enums espanol/ingles | Federico | D2 · 28-sep | fedevargas93 · 2026-09-28 |
| [x] | `DAT-08` | Silver: conversion FX a USD con daily_exchange_rates | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [x] | `DAT-09` | Gold: customer_360 | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [x] | `DAT-10` | Gold: credit_features_asof (con corte temporal) | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [~] | `DAT-11` | Gold: catalogo y condiciones de producto validadas con politica versionada | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [x] | `DAT-12` | Gold: dq_report publicable en /analytics | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [~] | `DAT-13` | Espejo en Databricks: carga y dbt verificados en el workspace real | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [~] | `DAT-14` | Export gold a Postgres con relectura verificada en el destino real | Federico | D5 · 1-oct | fedevargas93 · 2026-09-28 |
| [x] | `DAT-15` | Prueba que falla si una columna prohibida por fuga entra a credit_features_asof | Eduardo | D3 · 29-sep | Eduardo · 2026-09-28 | verificado el 5-oct: existe y corre

## Modelos — 7/13 `██████░░░░░░`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `ML-01` | Feature store as-of, sin fuga (corte 2025-12-31) | Eduardo | D3 · 29-sep | Eduardo · 2026-09-30 | deuda cerrada: moneda a USD, poda por redundancia, etiqueta_posterior renombrada y bloque de cuotas
| [x] | `ML-02` | Baseline: regresion logistica solo con credit_score | Eduardo | D3 · 29-sep | Eduardo · 2026-09-30 |
| [x] | `ML-03` | Modelo de riesgo de incumplimiento (LightGBM) | Eduardo | D4 · 30-sep | — | se entrega como informe de validacion: la variable objetivo no existe (F-027 a F-034)
| [x] | `ML-04` | Modelo de capacidad de pago desde flujo transaccional | Federico | D4 · 30-sep | Eduardo · 2026-09-29 |
| [ ] | `ML-05` | Metricas y calibracion: AUC, PR-AUC, KS, Brier | Eduardo | D4 · 30-sep | — |
| [ ] | `ML-06` | SHAP: los 3 factores que sustentan cada prediccion | Eduardo | D4 · 30-sep | — |
| [ ] | `ML-07` | MLflow: tracking y registry de los tres modelos | Eduardo | D4 · 30-sep | — |
| [ ] | `ML-08` | Model cards con supuestos y columnas excluidas | Eduardo | D6 · 2-oct | — |
| [ ] | `ML-09` | predictor.py: predict_risk y predict_capacity | Eduardo | D4 · 30-sep | — |
| [ ] | `ML-10` | Estabilidad del modelo por pais | Eduardo | D6 · 2-oct | — |
| [x] | `ML-11` | Propension experimental de conversion y consulta de cupos registrados por cliente | Federico | D4 · 30-sep | Eduardo · 2026-10-05 | propension de conversion de campana, cherry-pick de la rama de Federico
| [x] | `ML-12` | Red profunda comercial y asesor con puerta de evidencia para politica de Eduardo | Federico | D4 · 30-sep | fedevargas93 · 2026-09-30 | red profunda y asesor con puerta de evidencia, cherry-pick
| [x] | `ML-13` | Comparar tres y seis capas con varias semillas y control temporal de sobreajuste | Federico | D5 · 1-oct | fedevargas93 · 2026-10-01 | experimento de profundidad: la logistica gana

## Cognicion (SCM) — 8/8 `████████████`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `SCM-01` | Tipos, procedencia, contradicciones y estado epistemico definidos | Federico | D1 · 27-sep | fedevargas93 · 2026-09-28 |
| [x] | `SCM-02` | assert_fact con fuente obligatoria y sin sobrescritura silenciosa | Federico | D2 · 28-sep | fedevargas93 · 2026-09-28 |
| [x] | `SCM-03` | missing_evidence contra los slots requeridos por intencion | Federico | D2 · 28-sep | fedevargas93 · 2026-09-28 |
| [x] | `SCM-04` | contradictions: valor, procedencia y precondicion | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [x] | `SCM-05` | snapshot serializable con epistemic_status | Federico | D3 · 29-sep | fedevargas93 · 2026-09-28 |
| [x] | `SCM-06` | Las 26 pruebas de aceptacion pasando | Federico | D4 · 30-sep | Eduardo · 2026-09-27 | 26 pruebas de aceptación y casos adversos en verde
| [x] | `SCM-07` | Endurecido contra entradas ambiguas y contradictorias | Federico | D4 · 30-sep | fedevargas93 · 2026-09-28 |
| [x] | `SCM-08` | Seccion neurosimbolica de la documentacion | Federico | D6 · 2-oct | fedevargas93 · 2026-09-28 |

## Agente — 13/13 `████████████`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `AG-01` | Politica de elegibilidad versionada en YAML | Eduardo | D4 · 30-sep | Eduardo · 2026-10-02 | politica versionada en YAML: umbrales, catalogo, 8 reglas, abstencion, activos y reservas
| [x] | `AG-02` | Motor de reglas determinista, testeable sin LLM | Eduardo | D4 · 30-sep | — | motor determinista sin LLM, 58 pruebas en verde
| [x] | `AG-03` | Registro de tools con allowlist por rol | Eduardo | D5 · 1-oct | Eduardo · 2026-10-05 |
| [x] | `AG-04` | Las once herramientas implementadas (ADR-0009: el catalogo se derivo de la politica, son once no nueve) | Eduardo | D5 · 1-oct | Eduardo · 2026-10-02 |
| [x] | `AG-05` | AccessGuard: identidad, 3 intentos, JWT con customer_id dentro | Eduardo | D5 · 1-oct | Eduardo · 2026-10-02 |
| [x] | `AG-06` | Orquestador de las seis etapas | Eduardo | D5 · 1-oct | Eduardo · 2026-10-05 |
| [x] | `AG-07` | VERIFY: relectura real del store y ledger de acciones | Eduardo | D5 · 1-oct | Eduardo · 2026-10-02 |
| [x] | `AG-08` | Handoff estructurado validado por esquema | Eduardo | D5 · 1-oct | Eduardo · 2026-10-02 |
| [x] | `AG-09` | GroundingChecker: ninguna cifra fuera de los tools | Eduardo | D6 · 2-oct | Eduardo · 2026-10-02 |
| [x] | `AG-10` | Defensa contra inyeccion de prompt | Eduardo | D6 · 2-oct | Eduardo · 2026-10-02 |
| [x] | `AG-11` | Multilingue: deteccion y prompts espanol/portugues | Eduardo | D6 · 2-oct | — | verificado el 5-oct: existe y corre
| [x] | `AG-12` | Observabilidad: traza por turno, costo, health checks | Eduardo | D5 · 1-oct | — | verificado el 5-oct: existe y corre
| [x] | `AG-13` | Integracion del SCM tras la bandera SCM_ENABLED | Eduardo | D5 · 1-oct | Eduardo · 2026-10-05 | verificado el 5-oct: existe y corre

## Evaluacion — 7/7 `████████████`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `EV-01` | Generador de casos desde las plantillas reales | Eduardo | D7 · 3-oct | — | conjunto retenido 86 es / 46 pt / 20 adversariales, tres brazos y tabla comparativa
| [x] | `EV-02` | Conjunto retenido en espanol (~80 casos) | Eduardo | D7 · 3-oct | — | conjunto retenido 86 es / 46 pt / 20 adversariales, tres brazos y tabla comparativa
| [x] | `EV-03` | Conjunto en portugues de Brasil (~40 casos) | Eduardo | D7 · 3-oct | — | conjunto retenido 86 es / 46 pt / 20 adversariales, tres brazos y tabla comparativa
| [x] | `EV-04` | Suite adversarial (~20 casos de inyeccion y suplantacion) | Eduardo | D6 · 2-oct | — | conjunto retenido 86 es / 46 pt / 20 adversariales, tres brazos y tabla comparativa
| [x] | `EV-05` | Harness de los tres brazos: baseline, tools, tools+SCM | Eduardo | D7 · 3-oct | Eduardo · 2026-10-05 | conjunto retenido 86 es / 46 pt / 20 adversariales, tres brazos y tabla comparativa
| [x] | `EV-06` | Metricas: resolucion segura, acciones inseguras, grounding, costo | Eduardo | D8 · 4-oct | — | conjunto retenido 86 es / 46 pt / 20 adversariales, tres brazos y tabla comparativa
| [x] | `EV-07` | Resultados publicados y comparados | Eduardo | D8 · 4-oct | — | verificado el 5-oct: existe y corre

## API — 2/2 `████████████`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `API-01` | FastAPI con chat, trace, cases, metrics, eval, scenarios | Eduardo | D7 · 3-oct | Eduardo · 2026-10-05 | FastAPI con nueve rutas y la interfaz de una pagina servida desde el mismo origen
| [x] | `API-02` | Seguridad: JWT, rate limit, CORS cerrado, redaccion de PII | Eduardo | D7 · 3-oct | — | FastAPI con nueve rutas y la interfaz de una pagina servida desde el mismo origen

## Frontend — 7/8 `██████████░░`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [ ] | `UI-01` | Proyecto Next.js configurado | Eduardo | D6 · 2-oct | — |
| [x] | `UI-02` | /chat en espanol y portugues | Eduardo | D6 · 2-oct | — | FastAPI con nueve rutas y la interfaz de una pagina servida desde el mismo origen
| [x] | `UI-03` | Panel Caja de Vidrio con la traza en vivo | Eduardo | D6 · 2-oct | — | FastAPI con nueve rutas y la interfaz de una pagina servida desde el mismo origen
| [x] | `UI-04` | Escenarios precargados para el jurado | Eduardo | D6 · 2-oct | — | tres conversaciones guiadas que corren el flujo real, con prueba de punta a punta
| [x] | `UI-05` | /console con los expedientes estructurados | Eduardo | D7 · 3-oct | — | FastAPI con nueve rutas y la interfaz de una pagina servida desde el mismo origen
| [x] | `UI-06` | /analytics: metricas del agente y evidencia del ablation | Eduardo | D7 · 3-oct | — | FastAPI con nueve rutas y la interfaz de una pagina servida desde el mismo origen
| [x] | `UI-07` | /analytics: insights del negocio y calidad de datos | Eduardo | D7 · 3-oct | — | FastAPI con nueve rutas y la interfaz de una pagina servida desde el mismo origen
| [x] | `UI-08` | Deploy publico accesible para el jurado | Eduardo | D7 · 3-oct | — | https://noema.5-78-236-186.sslip.io en el Hetzner, systemd con tope de memoria y HTTPS por certbot

## Entregables — 2/5 `█████░░░░░░░`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `ENT-01` | docs 02 arquitectura, 03 politica, 04 evaluacion, 06 runbook completos | Eduardo | D8 · 4-oct | Eduardo · 2026-10-05 | 02 arquitectura, 03 politica y 06 runbook escritos; 04 evaluacion ya estaba
| [x] | `ENT-02` | LIMITATIONS final, con lo que realmente falto | Eduardo | D8 · 4-oct | Eduardo · 2026-10-05 | verificado el 5-oct: existe y corre
| [ ] | `ENT-03` | Cinco diapositivas | Eduardo | D9 · 5-oct | — |
| [ ] | `ENT-04` | Video de maximo 3 minutos | Eduardo | D9 · 5-oct | — |
| [ ] | `ENT-05` | Envio a hackathon.admin@factored.ai | Eduardo | D9 · 5-oct | — |

## Infraestructura y gobierno — 7/8 `██████████░░`

|  | ID | Tarea | Dueño | Día | Último movimiento |
|---|---|---|---|---|---|
| [x] | `INF-01` | Repo publico, estructura y contrato operativo | Eduardo | D1 · 27-sep | fedevargas93 · 2026-09-29 |
| [x] | `INF-02` | CI: secretos, lint, tests, dependencias | Eduardo | D1 · 27-sep | Eduardo · 2026-10-02 |
| [x] | `INF-03` | Auditoria del dataset documentada | Eduardo | D1 · 27-sep | Eduardo · 2026-09-29 |
| [x] | `INF-04` | Decisiones de arquitectura registradas | Eduardo | D1 · 27-sep | Eduardo · 2026-09-27 |
| [x] | `INF-05` | Contrato de seguridad escrito | Eduardo | D1 · 27-sep | Eduardo · 2026-10-02 |
| [x] | `INF-06` | Onboarding de Federico: spec, esqueleto, fixtures, agente | Eduardo | D1 · 27-sep | Eduardo · 2026-10-02 |
| [x] | `INF-07` | Revision de contribuciones y checklist vivo | Eduardo | D1 · 27-sep | Eduardo · 2026-09-27 |
| [~] | `INF-08` | Cuenta de Databricks conectada (bloqueado: falta host y token) | Eduardo | D2 · 28-sep | fedevargas93 · 2026-09-28 |
