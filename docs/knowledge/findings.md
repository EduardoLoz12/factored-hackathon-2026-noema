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

## F-012 · 2026-09-29 · datos — `registration_branch_id` no es una llave foránea

**Qué.** La columna tiene **150 000 valores distintos para 150 000 clientes**, uno propio por cliente, cuando solo existen 350 sucursales. No es una referencia rota: es un identificador generado de cero. Lo mismo ocurre con `service_agents.assigned_branch_id` (833 distintos para 1 200 agentes, 2 coincidencias). Las otras dos referencias a sucursal sí son válidas al 100 %: `products.opening_branch_id` y `transactions.branch_id` usan las 350 sucursales reales.

**Evidencia.** Mismo prefijo `SUC-`, misma longitud (12), mismo alfabeto (`0-9A-Z`), sin espacios ni diferencias de mayúsculas. Normalizar (`strip`, `upper`, quitar guion) no recupera ni una coincidencia más: se mantiene en 5, que es ruido. Es un defecto del generador del dataset, no de nuestra ingesta.

**Decisión.** Confirmada la política de poner a NULL: no hay nada que reparar. Pero la sucursal del cliente **sí se puede derivar** por sus productos: 139 578 de 150 000 clientes (93.05 %) tienen al menos una, y 28 189 tienen exactamente una, sin ambigüedad. El agente responde «¿en qué sucursal…?» por esa ruta, declarando que es la sucursal de apertura del producto y no la de registro. Ver también F-011, que describía el síntoma sin llegar a la causa.

## F-013 · 2026-09-29 · datos — El `amount_usd` de la fuente trae ruido inyectado de ±2 %

**Qué.** Donde el origen reporta su propio monto en dólares, no coincide con el que resulta de multiplicar el monto local por la tasa del día: difiere con error relativo **uniforme en ±2 %** y error absoluto de hasta 200 USD. No es una tasa distinta —el desvío contra `buy_rate` y `sell_rate` es aún mayor (1.26 % y 1.28 % contra 0.98 % del `exchange_rate`)— ni un rezago de fecha.

**Evidencia.** Sobre 1 886 980 transacciones no-USD: sesgo medio +0.0003 (simétrico), desviación 0.011675 contra 0.011547 que predice una uniforme(−2 %, +2 %), curtosis de exceso −1.177 contra −1.2 teórico. KS contra uniforme 0.043, contra normal 0.084. El error absoluto es proporcional al monto (r = 0.81), o sea multiplicativo.

**Decisión.** El pipeline hace lo correcto al usar el valor recalculado desde `daily_exchange_rates`: es reproducible y consistente. El valor de la fuente se conserva como `reported_amount_usd` para poder mostrar la discrepancia. **Va al documento de limitaciones con la prueba**, no como sospecha: es un dato duro sobre cómo se generó el dataset.

## F-014 · 2026-09-29 · datos — Los nulos son de dos clases y hay que tratarlos distinto

**Qué.** 104 de 287 columnas de silver tienen nulos, en dos regímenes claramente separables.

*Estructural* — el nulo significa «no aplica», condicionado a la fila. `days_past_due` y `credit_limit` son 100 % nulos en Cuenta Ahorro, Cuenta Corriente, Tarjeta Débito, Inversión y Seguro, y ~5 % nulos dentro de los tres productos de crédito. `merchant_name` es 100 % nulo salvo en Compra. `complaints.closing_date` solo existe en quejas cerradas.

*Inyectado* — el generador borró valores al azar a tasas redondas, homogéneas entre estratos: `credit_score` 15.0 %, `estimated_monthly_income` 20.0 %, `interest_rate` 10.0 %, `fraud_score` 20.0 %, `ip_address` 5.0 %.

**Evidencia.** La tasa de nulos de `credit_score` va de 14.53 % a 15.95 % en las doce celdas segmento × país. Y no informa: entre clientes con `credit_score` nulo la mora a 90 días es 6.545 %, entre los que lo tienen 6.550 %. Es aleatorio de verdad (MCAR), no un nulo que esconda riesgo.

**Caso aparte:** `complaints.origin_interaction_id` está **vacía al 100 %** en las 67 095 filas. El camino queja → interacción de call center no existe; el agente no puede reconstruir esa trazabilidad.

**Decisión.** El nulo estructural se codifica como categoría (`no_aplica`), nunca se imputa: imputar la mediana de `credit_limit` en una cuenta de ahorro inventa un producto que no existe. El nulo inyectado sí se imputa, y como es MCAR la imputación no sesga. Toda columna imputada lleva su indicador `_faltante` al modelo.

## F-015 · 2026-09-29 · modelos — El universo de la etiqueta es la mitad de lo que parecía, y el techo de señal es AUC ≈ 0.58

**Qué.** Tres correcciones encadenadas sobre la etiqueta de riesgo.

*El universo.* `days_past_due` solo existe en los tres productos de crédito: 131 972 productos, 125 350 con valor. Eso son **84 926 clientes etiquetables**, no 150 000, y 80 057 al cruzar con `credit_features_asof`. Tratar el NULL como «al día» —el error fácil— infla el denominador un 64 % y baja la tasa de mora de **10.71 % a 6.52 %**.

*La etiqueta es casi plana.* `days_past_due` toma **siete valores** (0, 15, 30, 60, 90, 120, 180) y los no-cero se reparten casi en partes iguales (~3 100 cada uno). La tasa de mora a 90 días es 7.4–7.8 % en **todos** los estratos: por tipo de producto, por segmento, por país y por tramo de `credit_score`. Un cliente con score bajo 550 cae en mora el 7.81 % de las veces; uno sobre 750, el 7.42 %.

*El techo aparente.* Sobre 79 492 clientes y 14 variables, con partición retenida del 30 %: regresión logística AUC 0.5678, gradient boosting AUC 0.5816. El baseline de ML-02, solo `credit_score`, da AUC 0.5033.

**Corrección — ver [[F-017]].** Ese 0.58 resultó ser un artefacto de agregación, no señal. El techo real es 0.50.

**Decisión.** Superada por F-017.

## F-017 · 2026-09-29 · modelos — `days_past_due` es un sorteo independiente: no hay nada que aprender

**Qué.** La etiqueta de riesgo no guarda relación con ninguna variable del dataset. No es que la señal sea débil: **no existe**. `days_past_due` se comporta exactamente como una Bernoulli(0.075166) sorteada de forma independiente por cada producto de crédito.

**Por qué se investigó.** Porque es ilógico que el `credit_score` del propio banco no prediga la mora de ese banco. La sospecha era un error de medición. No lo había.

**Evidencia, en cuatro pasos.**

*1. El score sí es coherente.* No es ruido: correlaciona con el ingreso (r = 0.356) y ordena limpiamente por segmento — Premium 797.4, Plus 699.2, Student 649.0, Basic 599.5. Su distribución es plausible (422–850, media 647.1, asimetría +0.67). El generador lo construyó bien a partir del perfil del cliente. El problema no está ahí.

*2. La mora no se relaciona con nada.* Diez variables medidas a nivel producto sobre 125 350 filas: `credit_score` r = −0.0038, ingreso −0.0017, saldo −0.0026, límite −0.0001, **utilización +0.0048**, tasa de interés −0.0006, antigüedad del producto +0.0017, antigüedad del cliente −0.0041, número de productos +0.0011, saldo total +0.0009. Todas las AUC caen entre 0.496 y 0.506. Que la utilización de línea —el segundo predictor más fuerte en banca real, después del score— dé 0.4978 es concluyente.

*3. No hay tendencia por tramo de score.* Prueba de Cochran-Armitage sobre cuatro tramos: **z = −0.79, p = 0.43**. La mora va de 7.63 % bajo 600 a 7.32 % sobre 800: **0.31 puntos porcentuales a lo largo de 230 puntos de score**. Un score que funciona separa del orden de 25 % a 1 % entre deciles extremos.

*4. El 0.58 de F-015 era un artefacto de agregación.* La etiqueta del cliente es `max()` sobre sus productos, así que quien tiene más productos de crédito tiene más sorteos y más probabilidad de que alguno salga en mora. Las tasas observadas reproducen la predicción de independencia casi exactamente: 1 producto 7.36 % (predicho 7.52 %), 2 productos 14.76 % (14.47 %), 3 productos 21.18 % (20.90 %), 5 productos 31.60 % (32.34 %). El conteo de productos de crédito solo, sin modelo, da AUC 0.6217. Y al estratificar por ese conteo, **todas** las AUC colapsan: dentro de los 51 164 clientes con un solo producto de crédito, transacciones 0.4942, salidas 0.4937, meses activos 0.4952, score 0.4994.

**Decisión.** El techo real del modelo de riesgo es **AUC = 0.50**. Cualquier cifra por encima proviene de una de dos tautologías —tener producto de crédito, o tener más de uno— y ninguna es riesgo.

Tres consecuencias operativas:

1. **ML-03 no se presenta como modelo de riesgo.** Se entrena, se mide y se reporta que no discrimina, con esta evidencia. Ese es el entregable: el rubro premia explícitamente la honestidad sobre lo que falta, y detectar que la etiqueta es sintética demuestra más criterio que exhibir un AUC inflado que el jurado puede desarmar en una pregunta.
2. **ML-02 gana sentido, no lo pierde.** El baseline de `credit_score` da 0.5033 y ahora sabemos por qué. La tabla baseline contra propuesto se mantiene, con ambos en 0.50 y la explicación al lado.
3. **La política de elegibilidad no se apoya en un PD estimado.** `eligibility_v1.yaml` decide con reglas sobre hechos verificables —ingreso, capacidad de pago, mora observada, antigüedad— y no con una probabilidad que no existe. Esto **refuerza** la tesis del proyecto: separar la conversación de la decisión, y que la decisión la tome una política auditable y no un modelo. El peso de la demo y de la evaluación se corre a grounding, tasa de acciones inseguras y verificación tras escritura, que es donde hay diferencia medible y donde más pesa el rubro.

## F-016 · 2026-09-29 · datos — La normalización de enums español/inglés no tenía nada que normalizar

**Qué.** `stg_products` implementa un `CASE` de dieciséis ramas para unificar `'Savings Account' → 'Cuenta Ahorro'` y pares equivalentes. **No colapsa ningún nivel.** No hay mezcla de idiomas dentro de ninguna columna categórica: `products.product_type` está íntegramente en español (8 niveles), `transactions.transaction_type` íntegramente en inglés (6 niveles), y lo mismo en `product_status`, `opening_channel`, `transaction_status`, `channel`, `segment`, `customer_status`, `education_level` y `marital_status`. El idioma varía **entre** columnas, no dentro de una.

**Evidencia.** Cardinalidad idéntica antes y después en las cinco columnas medidas (8→8, 6→6, 4→4, 4→4, 3→3). El `CASE` es inerte.

**Decisión.** El `CASE` se conserva porque es defensivo y no cuesta nada. Lo que se corrige es la **documentación**: `docs/01_data_audit.md` afirmaba que `product_type` venía en inglés, y el `CLAUDE.md` usaba esa normalización como ejemplo de mensaje de commit. Ambos corregidos. Un jurado que abra `stg_products.sql` y luego los datos habría visto la contradicción.

## F-018 · 2026-09-29 · modelos — `last_updated` no dice cuándo se registró la mora

**Qué.** El campo `last_updated` de `products` y `customers` es un sello de modificación **sorteado al azar**, sin relación con los eventos del negocio. No sirve para decidir si la etiqueta de mora precede o sigue a las variables.

**Por qué se investigó.** La primera versión de ML-01 usaba ese campo para separar una «cohorte estricta»: solo los productos con `last_updated` posterior al corte tendrían la etiqueta observada después de las variables. Bajo esa lectura, el universo entrenable caía de 76 906 clientes a 7 078 — se descartaba el **91 %** de los datos. Eduardo objetó que descartar 130 000 clientes necesitaba mejor justificación. La tenía.

**Evidencia.**

*El campo no reacciona a la mora.* Si un incumplimiento provocara una escritura de fila, los productos en mora tendrían el sello más reciente. Sobre 125 350 productos con `days_past_due`: media de −182.35 días en los que están en mora a 90 días, −181.63 en los que están al día o con mora leve. **Una diferencia de 0.72 días.** Si el campo registrara el evento, la diferencia sería de meses.

*El campo es uniforme.* Sobre 400 000 productos y nueve años de rango: KS contra una uniforme **0.049**, curtosis de exceso **−1.161** contra −1.2 que predice exactamente una uniforme, histograma plano en 18 cajas. Un campo de auditoría real se concentra donde hubo actividad.

*Lo que sí es coherente.* Nunca es anterior a `opening_date` (0 violaciones en 400 000 filas) y correlaciona 0.65 con `last_transaction_date`. Es plausible como «última escritura de la fila»; no lo es como «cuándo cambió la mora».

**Decisión.** El filtro no se aplica. La lectura correcta de `days_past_due` en una tabla de estado actual es el estado al momento del extracto —junio de 2026—, posterior al corte para todos. **La cohorte de trabajo son los 76 906 clientes con producto de crédito.**

La cohorte de 7 078 se conserva en la misma tabla, marcada, como **análisis de sensibilidad**: si la conclusión aguanta con las dos, no depende de cómo se lea el campo. Aguanta — el baseline de ML-02 da AUC 0.5012 con 76 906 y 0.4693 con 7 078, ambos con el intervalo cruzando 0.5.

Queda en pie, más débil, la precaución sobre las variables de la foto: si `last_updated` es posterior al corte, esa fila **pudo** reescribirse después, así que `credit_score` y `credit_limit` podrían reflejar información posterior. Las marcas `cliente_posterior` y `limite_posterior` viajan en la tabla como precaución declarada, no como prueba.

**Regla que deja.** Ningún filtro que descarte una fracción grande de los datos entra sin una prueba que lo sostenga. «Suena razonable» no basta cuando el costo es el 91 % del universo. Ver [[F-015]] y [[F-017]].

## F-019 · 2026-09-29 · datos — `days_past_due` no son días de mora: es una etiqueta de cubeta sorteada

**Qué.** El campo no mide días. Toma **siete valores y nada más** —0, 15, 30, 60, 90, 120, 180— y los seis no-cero se reparten de forma **equiprobable**. No hay ningún registro de pagos en el dataset con el cual se hubiera podido calcular una mora real, y el valor no guarda relación con el comportamiento de pago que sí existe.

**Por qué se investigó.** Eduardo, revisando el dato a mano: «ese `days_past_due` son números repetidos de 90, 180, 360 o algo así. ¿Eso son el máximo de días antes de cobrar mora del producto o cómo? Creo que no son los días que lleva de mora el cliente porque no veo un registro diario por cliente de pago o no de la deuda.» Las dos mitades de la observación resultaron correctas, aunque no por la razón propuesta.

**Evidencia.**

*No es un parámetro del producto.* La hipótesis de que fuera un plazo de gracia por tipo de producto no se sostiene: los tres tipos de crédito presentan los siete valores en proporciones casi idénticas (~85 % en cero), y 9 518 clientes tienen valores distintos entre sus propios productos. Tampoco se relaciona con las condiciones: la tasa de interés media es 27.3–27.9 y el límite medio ~43 M en todas las cubetas.

*Las cubetas son equiprobables.* Conteos de 3 114, 3 117, 3 112, 3 233, 3 083 y 3 106 sobre 18 765 no-ceros. **χ² = 4.51 con 5 grados de libertad, p = 0.48**: no se rechaza la uniformidad. Cada cubeta se lleva el 2.46–2.58 % de la cartera. Una cartera real decae geométricamente por tasas de traspaso —de cada cubeta solo una fracción pasa a la siguiente—, así que incluso con un traspaso optimista del 50 % la última cubeta debería tener 0.08 % y no 2.48 %.

*No existe con qué calcularla.* Ninguna tabla trae cuota, fecha de vencimiento, pago mínimo, estado de cuenta ni calendario de amortización. Se buscaron todas las columnas con `pay`, `due`, `install`, `minimum`, `statement`, `billing`, `schedule`, `delinq` o `arrear`: las únicas coincidencias son el propio `days_past_due` y tres umbrales de la política de producto.

*Y no concuerda con los pagos que sí hay.* Un producto con 180 días de mora registra **2.91 pagos de media y 309 días desde el último**; uno al día, 2.87 pagos y 314 días. Idénticos. Además 2.9 pagos en tres años no es un calendario de amortización: una tarjeta real acumula ~36.

**El diccionario dice otra cosa.** Define `days_past_due INTEGER — Days past due (for credits)`. Esa era la intención; el dato generado no la cumple. Es el octavo punto en que el diccionario no coincide con el dato.

**Ninguna otra etiqueta del dataset es aprendible.** Se probaron cinco alternativas antes de cerrar la puerta:

| Objetivo | Tasa | Mejor AUC | Veredicto |
|---|---:|---:|---|
| Cliente cerrado o inactivo | 11.93 % | 0.5046 | ruido |
| `sla_breached` en quejas | 20.11 % | 0.4995 | ruido |
| NPS detractor | 74.52 % | 0.5036 | ruido |
| Conversión de campaña | 0.55 % | 0.8101 | dependencia de embudo: hay que abrir para convertir |
| `is_fraud` | 0.10 % | 0.8469 | dos uniformes de distinto rango: ver F-020 |

El fraude merece su propio hallazgo: ver F-020. Parecía la excepción —`fraud_score` da AUC 0.8469 contra `is_fraud`— pero esa capacidad discriminante también está fabricada.

**Decisión.** Queda cerrado y probado: **este dataset no contiene ningún objetivo supervisado aprendible.** Eso supera a [[F-017]], que lo había establecido solo para el riesgo de crédito.

Tres consecuencias:

1. **No se entrena ML-03 como modelo de riesgo.** Se reporta la medición y la prueba de por qué. El rubro premia explícitamente la honestidad sobre lo que falta, y esta evidencia —cubetas equiprobables con p = 0.48, ausencia de calendario de pagos, cinco objetivos alternativos descartados— demuestra más criterio analítico que cualquier AUC que se pudiera fabricar.
2. **ML-01 y ML-02 conservan su valor.** El feature store alimenta las herramientas del agente, que necesita cifras verificables sobre el cliente aunque no necesite predecirlas. Y el baseline es la medición que sostiene el punto 1.
3. **La elegibilidad se decide con reglas sobre hechos observables**, no con una probabilidad estimada. Es la tesis del proyecto llevada hasta el final: ni el LLM ni el modelo deciden.

**Regla que deja.** Antes de tratar una columna como objetivo, mirar su distribución. Siete valores distintos y seis equiprobables no es un fenómeno medido: es un sorteo. Toma dos minutos y evita entrenar contra ruido.


## F-020 · 2026-09-29 · datos — `fraud_score` no es la salida de un modelo: son dos uniformes de distinto rango

**Qué.** Al descartar objetivos aprendibles ([[F-019]]) el fraude parecía la excepción: `fraud_score` alcanza **AUC 0.8469** contra `is_fraud` sobre 3 539 851 transacciones. Eduardo lo miró y dijo que se veía como un modelo por detrás. Tiene la forma de uno —score alto, fraude— pero no lo es. El generador hace dos sorteos con rangos distintos:

```
si is_fraud:  fraud_score ~ Uniforme(0, 100)
si no:        fraud_score ~ Uniforme(0,  30)
```

**Evidencia.** Las dos distribuciones son uniformes con precisión de tercera cifra.

| Clase | n | Rango | σ observada | σ teórica | Curtosis | KS |
|---|---:|---|---:|---:|---:|---:|
| No fraude | 3 536 426 | [0.00, **30.00**] | 8.6609 | 8.6603 = 30/√12 | −1.2012 | 0.0020 |
| Fraude | 3 425 | [0.01, 99.99] | 28.9484 | 28.8675 = 100/√12 | −1.2029 | 0.0157 |

La curtosis de exceso de una uniforme es exactamente −1.2 y ambas caen a tres milésimas. El máximo en no-fraude es **30.00 clavado**: `P(score > 30 | no fraude) = 0.000000` sobre tres millones y medio de filas.

*El esquema explica el AUC sin residuo.* Si el 69.28 % de los fraudes cae sobre 30 —donde gana siempre— y el 31 % restante se compara contra una uniforme del mismo tramo —donde gana la mitad de las veces—, la AUC teórica es 0.6928 + 0.3072 × 0.5 = **0.8464**. Observada: **0.8469**.

*Y se ve en los tramos.* Bajo 30 la tasa de fraude es plana en 0.026–0.031 % a lo largo de seis tramos de cinco puntos, porque la razón entre dos densidades uniformes es constante. Entre 30 y 35 salta a 22.32 %, y de 35 en adelante es **100 % en todos los tramos**: ahí no puede haber no-fraudes.

*No hay señal fuera de esa columna.* Un gradient boosting con monto, latitud, longitud, canal, país, estado y hora —sin `fraud_score`— da **AUC 0.4743**.

**Por qué importa la distinción.** Una salida de modelo real nunca es uniforme: se concentra en valores bajos con una cola delgada a la derecha, porque la mayoría de las transacciones son claramente legítimas. Que las dos clases sean uniformes perfectas dentro de su rango es la firma de un generador, no de un clasificador.

**Decisión.** Se confirma F-019 sin excepciones: **ninguna columna de este dataset es un objetivo supervisado aprendible.** `fraud_score` no se usa como variable en ningún modelo ni se presenta como evidencia de que el fraude sea predecible. Sí se puede exponer al agente como dato descriptivo de una transacción, declarando que es un puntaje del sistema de origen y no una predicción propia.

**Regla que deja.** Ante una variable que discrimina sospechosamente bien, mirar su distribución **por clase** antes de celebrarla. Dos uniformes de distinto rango, una variable derivada de la etiqueta y una fuga de información producen todas el mismo síntoma —AUC alto— y se distinguen en un histograma.
