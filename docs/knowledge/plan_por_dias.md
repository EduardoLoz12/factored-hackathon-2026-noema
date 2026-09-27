# Plan por días

Ocho días útiles más el día de envío. **Cierre: 5-oct-2026, 23:59 hora Colombia.** Premiación 16-oct.

Cada día apunta a ítems concretos del [checklist](checklist.md). Si un día termina y sus ítems siguen en `falta`, el retraso se arrastra — escríbelo en [findings](findings.md) en vez de esperar a que se note solo.

| Día | Eduardo | Federico | Ítems que deben cerrar |
|---|---|---|---|
| **D1 · 27-sep** ✅ | Repo, estructura, contrato operativo, CI, agentes y memoria. Ingesta S3 completa. Auditoría del dataset. 4 ADRs. Onboarding de Federico. | Leer el repo y congelar el contrato de `scm.py`. | `INF-01..07`, `DAT-01`, `DAT-02`, `SCM-01` |
| **D2 · 28-sep** | Contratos de esquema, reporte de calidad a escala, cuarentena, dbt con perfil duckdb, silver de productos y clientes. Spike de Databricks. | `assert_fact` y `missing_evidence` con sus tests en verde. | `DAT-03..07`, `SCM-02`, `SCM-03` |
| **D3 · 29-sep** | Silver de transacciones con FX. Gold: `customer_360`, `credit_features_asof`, `product_policy`, `dq_report`. Subida a Databricks. Feature store y baseline. | `contradictions` y `snapshot` con procedencia. | `DAT-08..13`, `ML-01`, `ML-02`, `SCM-04`, `SCM-05` |
| **D4 · 30-sep** | Modelo de riesgo, capacidad de pago, métricas y calibración, SHAP, MLflow, `predictor.py`. Política YAML y motor de reglas. | Endurecer el SCM; las 26 pruebas de aceptación en verde. | `ML-03..07`, `ML-09`, `AG-01`, `AG-02`, `SCM-06`, `SCM-07` |
| **D5 · 1-oct** | Tools con allowlist, AccessGuard, orquestador de las seis etapas, VERIFY con relectura real, handoff estructurado, observabilidad. Integración del SCM tras la bandera. Export a Postgres. | Acompañar la integración y corregir lo que salga del uso real. | `AG-03..08`, `AG-12`, `AG-13`, `DAT-14` |
| **D6 · 2-oct** | GroundingChecker, defensa anti-inyección, multilingüe ES/PT, suite adversarial. Model cards y estabilidad por país. `/chat` con panel Caja de Vidrio y escenarios. | Congelar el SCM y escribir la sección neurosimbólica. | `AG-09..11`, `ML-08`, `ML-10`, `EV-04`, `UI-01..04`, `SCM-08` |
| **D7 · 3-oct** | Generador de casos, conjuntos retenidos ES y PT, harness de los tres brazos. API con seguridad. `/console`, `/analytics` y deploy público. | Preparar sus 40 segundos del video. | `EV-01..03`, `EV-05`, `API-01`, `API-02`, `UI-05..08` |
| **D8 · 4-oct** | Corrida completa de los tres brazos, métricas, evidencia en `/analytics`. Documentación 02/03/04/06 y LIMITATIONS final. | Revisar los resultados del brazo con SCM y redactar su lectura. | `EV-06`, `EV-07`, `ENT-01`, `ENT-02` |
| **D9 · 5-oct** | Cinco diapositivas, video de tres minutos, envío. Colchón. | Ensayo del pitch. | `ENT-03..05` |

## Reglas de corte

- Si el **día 6** el ciclo del agente no cierra de punta a punta, se recorta la interfaz a Streamlit. **Nunca se recorta la evaluación** — es lo que se califica.
- Si el **día 4** el SCM no pasa sus pruebas, se apaga con `SCM_ENABLED=false` y se reporta como limitación. El sistema debe seguir funcionando igual.
- Si el **día 3** Databricks sigue bloqueado, se sigue solo con DuckDB y se documenta en el ADR-0002. La ruta canónica ya es DuckDB, así que no es un bloqueo real del entregable.

## Estado

**D1 cerrado en fecha.** La ingesta era lo único de ese día con riesgo de tomar medio día; tomó cuatro minutos.

**Bloqueos abiertos:** cuenta de Databricks (`INF-08`, falta host y token).
