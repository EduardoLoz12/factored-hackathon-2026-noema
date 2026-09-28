# Memoria de hallazgos

Un hallazgo por entrada. **Regla: si descubres algo que contradice una suposición, escríbelo aquí antes de seguir codificando.**

Formato: `## F-NNN · fecha · área — título` seguido de *qué se encontró*, *evidencia*, *qué decisión produjo*.

Áreas: `datos` · `ml` · `agente` · `eval` · `plataforma` · `rubro`

---

## F-001 · 2026-09-26 · datos — Los transcripts no tienen contenido real

**Qué.** Las 200 000 transcripciones del dataset son 2 plantillas de texto repetidas, con un solo intent (`consulta_general`, 94 %), cero portugués, y los valores **sin rellenar**: `{monto}`, `{moneda}`, `{limite}`.

**Evidencia.** Muestra de 794 transcripciones de 4 días repartidos en 3 años. 2 plantillas únicas (397 cada una). `detected_language` = `es` en el 100 %. Ocurrencias: `{moneda}` 1 191, `{monto}` 794, `{limite}` 397.

**Decisión.** No se usa como corpus de entrenamiento ni de RAG. Se usa como **plantilla para generar los casos de evaluación**, rellenando los huecos desde las tablas gold → conversaciones con respuesta correcta conocida. Es la jugada central del proyecto. → ADR-0003.

---

## F-002 · 2026-09-26 · ml — Sí hay etiquetas de riesgo, pero son una fotografía

**Qué.** `products.days_past_due` tiene 125 350 valores no nulos y ~15 % de casos en mora con corte en 30 días. Pero el dataset no dice **en qué fecha** se midió esa mora, y `last_updated` por producto va de 2019 a 2026.

**Evidencia.** 0 días: 106 585 · 1-29: 3 114 · 30-59: 3 117 · 60-89: 3 112 · 90+: 9 422. Máximo 180.

**Decisión.** El modelo PD es viable. El corte temporal para construir variables es un **supuesto declarado**, no un hecho observado, y se documenta como tal. Se excluyen explícitamente `current_balance`, `last_transaction_date` y `product_status` por riesgo de fuga. → ADR-0004.

---

## F-003 · 2026-09-26 · datos — El diccionario promete cosas que el dato no cumple

**Qué.** Siete discrepancias entre `LATAM_Bank_Complete_Data_Dictionary` y los datos reales: enums en español donde documenta inglés, MXN inexistente pese a 74 907 clientes mexicanos, cero duplicados donde promete 2 %, nulos estructurales muy distintos al 5 % declarado, `credit_score` desde 422 y no desde 300, y `contact_reason` duplicada de `reason_category`.

**Evidencia.** Lectura completa de `products.csv` (400 000) y `customers.csv` (150 000) más muestreo de particiones diarias. Detalle en `docs/01_data_audit.md`.

**Decisión.** Los contratos de esquema se escriben contra el **dato observado**, no contra el diccionario. La discrepancia se reporta como entregable del pilar de Data Analytics en `/analytics`.

---

## F-004 · 2026-09-26 · datos — 48.4 % de los clientes tiene teléfono de otro país

**Qué.** 72 548 de 150 000 clientes tienen prefijo telefónico que no corresponde a su país de residencia.

**Evidencia.** Comparación de prefijo (`+52`, `+57`, `+54`) contra la columna `country`. Caso real: DNI, teléfono `+54`, ciudad Guadalajara, país México, acento `mexican`.

**Decisión.** El teléfono **no** se usa como factor de verificación de identidad. La puerta usa `document_type` + `document_number` + `date_of_birth`, que sí es único en las 150 000 filas.

---

## F-005 · 2026-09-26 · datos — Llegadas tardías confirmadas

**Qué.** 25.5 % de las transacciones de un día tienen `transaction_date` fuera de la partición `process_date` en la que están guardadas.

**Evidencia.** `transactions/year=2026/month=06/day=10`: 1 343 de 5 268 filas.

**Decisión.** En la ingesta, `process_date` gobierna la partición; en el análisis de comportamiento, `transaction_date` gobierna el orden temporal. Ambas se conservan en bronze.

---

## F-006 · 2026-09-27 · plataforma — Databricks Free Edition no puede leer el S3 de Factored

**Qué.** Free Edition es serverless-only, sin consola de cuenta ni APIs de nivel cuenta, y con salida a internet **restringida a un conjunto de dominios de confianza**. No hay instance profile ni credencial de almacenamiento para registrar un bucket de terceros como external location.

**Evidencia.** Documentación oficial de limitaciones de Free Edition; pendiente el spike empírico del D1.

**Decisión.** La ingesta ocurre **fuera** de Databricks (Python + boto3 local), la curación canónica en DuckDB + dbt, y Databricks recibe los Parquet por Volume para ser el lakehouse Delta y el registry de MLflow. El serving nunca consulta Databricks. → ADR-0002.

---

## F-007 · 2026-09-27 · agente — El esqueleto inicial simulaba la verificación

**Qué.** En `factored_hackathon_noema.py` (maqueta previa), `GlassBoxExecutor` hacía `verified_state = simulated_write_success` con `simulated_write_success = True`: la relectura posterior a la escritura era una tautología. Además `AccessGuard` aceptaba cualquier cadena no vacía, y `client_id` llegaba como parámetro libre — cualquiera podía consultar a cualquiera.

**Evidencia.** Líneas 103-113 y 43-49 del archivo original.

**Decisión.** La verificación debe releer del store real y comparar campo por campo. El `customer_id` viaja **dentro del JWT** emitido tras pasar la puerta de identidad, nunca como parámetro del cliente. Se conserva el vocabulario (`AccessGuard`, `AxiomEngine`, `GlassBoxExecutor`) y se reescribe el contenido.

---

## F-008 · 2026-09-27 · plataforma — La ingesta completa cabe en una laptop

**Qué.** El bucket tiene 7 671 objetos CSV y 5.35 GB bajo `data/`. Convertido a Parquet comprimido se reduce a una fracción.

**Evidencia.** Listado completo por API y corrida de ingesta con 16 hilos.

**Decisión.** No se necesita clúster para curar. Esto habilita que el jurado reproduzca toda la curación con `make ingest && make build`, sin cuenta de Databricks ni de AWS propia — lo cual ataca directamente el criterio #1 de evaluación («que la solución se pueda correr»).

---

## F-009 · 2026-09-27 · datos — El conteo de filas no coincide con el documentado en 9 de 13 tablas

**Qué.** La ingesta completa arrojó **23 495 188 filas**, no los ~19 000 000 declarados. Las cinco tablas de dimensión coinciden exactamente; **todas** las tablas de hechos difieren, y no en la misma dirección.

**Evidencia.** Conteo exacto sobre los 7 671 archivos descargados (0 fallos), derivado del manifest:

| Tabla | Real | Diccionario | Delta |
|---|---:|---:|---:|
| `digital_events` | 15 620 994 | 10 000 000 | **+56.2 %** |
| `daily_exchange_rates` | 13 164 | 3 000 | **+338.8 %** |
| `transactions` | 4 425 008 | 5 000 000 | −11.5 % |
| `campaign_sends` | 1 746 801 | 2 000 000 | −12.7 % |
| `call_center_interactions` | 686 296 | 800 000 | −14.2 % |
| `call_transcripts` | 171 321 | 200 000 | −14.3 % |
| `satisfaction_surveys` | 212 759 | 250 000 | −14.9 % |
| `complaints` | 67 095 | 80 000 | −16.1 % |
| `customers`, `products`, `branches`, `service_agents`, `marketing_campaigns` | exacto | exacto | 0 % |

**Lectura.** El patrón es demasiado regular para ser azar: seis tablas de hechos caen entre −11 % y −16 %, lo que sugiere que las cifras del diccionario son **objetivos de generación** y no conteos medidos, y que el generador descartó filas (probablemente por colisión de identificadores o por validaciones internas). `digital_events` y `daily_exchange_rates` van al alza, así que no es un solo mecanismo.

**Decisión.** Ningún conteo del diccionario se usa como verdad. Los contratos de esquema se escriben contra el dato observado y el manifest queda como evidencia reproducible. La tabla de arriba se publica en `/analytics` como parte del reporte de calidad de datos: **encontrar esto es entregable, no anécdota.**

## F-010 · 2026-09-28 · capacidad y catálogo — Faltan dirección y condiciones

**Qué.** `transactions` no trae dirección de transferencia ni identifica cuotas comprometidas. `ml/serving/predictor.py` y la política de producto, citados como disponibles en la spec, aún no existen. MXN sí aparece en otras tablas; su ausencia observada se limita a productos y transacciones.

**Evidencia.** Esquema local de bronze; categorías de transacción; inventario del repositorio y `docs/03_credit_policy.md`.

**Decisión.** Depósitos como entrada observable, pagos/compras/retiros como salida; transferencias y ajustes se reportan como ambiguos. El estimador se declara proxy, no capacidad real validada. Catálogo con condiciones desconocidas y `policy_ready=false` hasta recibir la política de Eduardo. No inventar umbrales ni implementar el predictor de riesgo. Ver ADR-0005.

## F-011 · 2026-09-28 · datos — Referencias de sucursal mayormente huérfanas

**Qué.** La auditoría completa detectó 149 995 referencias `customers.registration_branch_id` sin sucursal entre 150 000 clientes; también 831 agentes con sucursal inexistente.

**Evidencia.** Anti-join de bronze contra las 350 sucursales, reproducido en `logs/build/dq_report.json`.

**Decisión.** No descartar casi todos los clientes por una relación opcional. Conservar la fila original y motivo en cuarentena de referencias; limpiar a NULL solo las relaciones opcionales inválidas. Relaciones esenciales cliente/producto siguen rechazando la fila completa. El reporte distingue reparación de relación y rechazo de fila; bronze permanece intacto.
