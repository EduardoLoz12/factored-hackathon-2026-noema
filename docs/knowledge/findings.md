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

## F-021 · 2026-09-30 · modelos — El barrido completo de las 13 tablas confirma el techo: 74 variables, ninguna sobrevive el control

> **CORREGIDO el 30-sep, ver [[F-023]].** La primera versión de este hallazgo usó como objetivo la columna `etiqueta_posterior`, que **no es la mora**: es un indicador de si el producto fue observado después del corte. Las cifras de abajo se recalcularon con el objetivo correcto (`mora_90`). La conclusión no cambia —ninguna variable sobrevive el control— pero los números sí, y están actualizados en este texto. El error propio y su mecanismo están documentados en F-023.

**Qué.** Hasta hoy la conclusión de F-017 se apoyaba en 10 variables a nivel producto y 14 a nivel cliente, todas derivadas de **4 de las 13 tablas**. Eduardo objetó lo obvio: con 307 columnas de un banco de verdad, es improbable que no haya un predictor. Tenía razón en que no estaba probado. Se probó.

**Qué se hizo.** Se construyeron **74 variables candidatas** agregadas por cliente y filtradas al corte 2025-12-31, cubriendo **las 13 tablas** —incluidas las nueve que el feature store nunca tocó: `call_center_interactions`, `call_transcripts`, `campaign_sends`, `digital_events` (15.6 M filas), `satisfaction_surveys`, `service_agents`, `branches`, `marketing_campaigns`, `daily_exchange_rates`— más las columnas de `transactions`, `products`, `complaints` y `customers` que el feature store deja fuera (`fraud_score`, `interest_rate`, `merchant_category`, `sla_breached`, `resolution_days`, edad, canal de apertura, y demás).

**El control.** Todo AUC se reporta dos veces: global, y **dentro del estrato `n_productos_credito == 1`** (48 396 clientes, 3 128 positivos), donde la tautología de agregación de F-017 no puede operar.

**Univariado — 74 variables medidas.** Diez superan |AUC−0.5| > 0.03 globalmente. Al estratificar, **las diez colapsan**:

Ocho superan |AUC-0.5| > 0.03 globalmente, todas conteos de diversidad que miden **cuántos productos tiene el cliente** y no su riesgo. Dentro del estrato de un solo producto de crédito, **ninguna** llega a ese umbral: la desviación máxima es 0.0112 (`ss_score_medio`).

**Multivariado — la prueba definitiva.** LightGBM (400 árboles, 31 hojas), partición retenida del 30 %, IC 95 % por bootstrap de 200 remuestreos, semilla 20260930:

| Corrida | AUC | IC 95 % | Lectura |
|---|---:|---|---|
| **Dentro de 1 producto, 74 variables** | **0.4991** | **[0.4852, 0.5154]** | Contiene 0.50 |
| Control barajado, 74 variables | 0.4973 | [0.4786, 0.5120] | Contiene 0.50 |

**El resultado clave:** el modelo con todas las variables del banco, dentro del estrato limpio, da **0.4991** — y la misma corrida con la etiqueta permutada al azar da **0.4973**. El modelo real es *indistinguible de su propio control de ruido*.

Las variables que el modelo global más usa —`pr_tasa_media`, `cu_credit_score`, `cc_espera_media`, `ss_horas_respuesta`, `cc_sentimiento_medio`, `cu_ingreso`— son las mismas que colapsan al estratificar. El modelo no encontró señal: encontró el conteo de productos.

**Decisión.** Se confirma F-017 con cobertura completa del dataset, no parcial. El techo de AUC = 0.50 ya no es una inferencia sobre 14 variables: es un resultado medido sobre 74, de las 13 tablas, con control de agregación y control barajado. **ML-03 se entrega como esta evidencia.**

**Corrección de alcance sobre F-017.** La conclusión de F-017 era correcta pero su base era estrecha. Cualquier afirmación de «ninguna columna predice» debía cubrir las 13 tablas antes de escribirse. Quedó cubierta el 30-sep.

**Evidencia.** `logs/eval/barrido_univariado.csv` (74 filas) · `logs/eval/ml03_multivariado.json` · `logs/eval/ancha.parquet` (76 906 × 76).

## F-022 · 2026-09-30 · modelos — El modelo de capacidad le gana al baseline por 0.4 %, y se abstiene en el 94 % de los casos

**Qué.** Primera corrida real de `ML-04` (`python -m ml.training.capacity`). Hasta hoy no existía artefacto con métricas.

**Resultado.** MAE de validación del modelo **92 369.45** contra baseline **92 731.04**: gana por **0.39 %**. `selected = "model"`, así que el artefacto se publica como modelo — pero el margen es marginal.

**Por moneda**, que es lo único comparable (el MAE agregado mezcla ARS, COP y USD):

| Moneda | Filas | MAE modelo | MAE baseline | Diferencia |
|---|---:|---:|---:|---|
| ARS | 2 750 | 28 725.90 | 29 387.48 | −2.25 % |
| COP | 3 756 | 343 242.66 | 344 184.99 | −0.27 % |
| USD | 8 314 | 84.15 | 84.15 | **idéntico** |

En USD el modelo y el baseline dan el mismo número hasta el decimal: el techo `min(min_surplus, 0.30 × mean_deposits)` **muerde siempre**, así que la predicción del modelo nunca llega a aplicarse. El modelo solo aporta algo en ARS, y poco.

**Lo que más importa:** de 14 820 filas de validación, solo **825 (5.6 %)** pasan la puerta de abstención —3 meses activos y cero transacciones ambiguas—. **El sistema se va a abstener en ~94 % de los clientes.** Eso no es un defecto del modelo; es el dato que no alcanza. Pero cambia la demo y la evaluación: la abstención no es el caso raro, es el caso típico, y la conversación tiene que estar diseñada para eso.

**Decisión.** ML-04 se reporta con el desglose por moneda y con la tasa de abstención al frente, no con el MAE agregado. `eligibility_v1.yaml` debe tratar «sin capacidad estimable» como rama principal, no como excepción. Se avisa a Federico.

**Evidencia.** `data/models/capacity.json` · `logs/build/capacity_metrics.json`.

## F-023 · 2026-09-30 · modelos — `etiqueta_posterior` no es la mora, y por un rato la usamos como objetivo

**Qué.** Error propio, detectado al investigar una variable con Information Value absurdo. Queda escrito porque el mecanismo se puede repetir.

**El síntoma.** En el análisis de variables razonadas, `cond_antig_producto` —antigüedad del producto de crédito más viejo— dio **IV = 8.42** dentro del estrato de un producto. La convención de scorecards dice que un IV sobre 0.5 casi nunca es señal: es fuga. Al abrir la distribución por clase, los productos abiertos menos de 90 días antes del corte tenían **86.8 % de mora**, contra 5.2 % en los maduros. Imposible en crédito real: no se puede acumular 90 días de mora en un producto de 30 días.

**La causa.** `ml/features/build_features.py`, línea 292:

```sql
case when e.mora_90_estricta is not null then 1 else 0 end as etiqueta_posterior
```

`etiqueta_posterior` **no es la variable objetivo**. Es un indicador de *cobertura*: vale 1 cuando el cliente tiene al menos un producto de crédito cuyo `last_updated` cae después del corte, o sea cuando existe una observación válida. El nombre invita al error; la columna que sí es la mora es `mora_90` (cohorte completa) o `mora_90_estricta` (subconjunto observado después del corte).

Los barridos univariado y multivariado de F-021 se corrieron con `etiqueta_posterior` como `y`. Estuvieron prediciendo **«¿a este producto lo actualizaron después del corte?»**, no «¿entró en mora?». Y la antigüedad del producto predice eso muy bien, porque a los productos recién abiertos los tocan más.

**Qué no falló.** `ml/training/baseline_logreg.py` (ML-02) **sí** usa el objetivo correcto: su tasa de positivos es 10.56 %, que es la de `mora_90`. Ninguna cifra publicada de ML-01 ni ML-02 estaba afectada. El error fue del análisis exploratorio nuevo, no del código del repo.

**Qué cambia al corregirlo.** Se recorrió todo con `mora_90`. La conclusión se sostiene y de hecho se refuerza:

| | con objetivo equivocado | con `mora_90` |
|---|---:|---:|
| Variables con \|AUC−0.5\| > 0.03 dentro de 1 producto | 1 de 74 | **0 de 74** |
| Desviación máxima dentro de 1 producto | 0.0396 | **0.0112** |
| `cond_antig_producto` IV (1 producto) | 8.4209 | **0.0014** |

**Regla que deja.** Dos, y las dos son de higiene:

1. **Un IV sobre 0.5 es una acusación, no un logro.** Antes de incorporar una variable con IV alto, abrir su distribución por clase. Es el mismo reflejo que ya dejó F-020 para el AUC.
2. **Antes de usar una columna como `y`, verificar su tasa de positivos contra la tasa de mora documentada.** `etiqueta_posterior` daba 9.20 %; `mora_90` da 10.56 %. Un punto y medio de diferencia era la pista, y estaba disponible desde el principio.

**Acción sobre el código.** `etiqueta_posterior` debe renombrarse a `tiene_observacion_posterior` en `build_features.py`. El nombre actual es una trampa para quien retome el repo. Queda como tarea sobre ML-01.

## F-024 · 2026-09-30 · modelos — Ninguna variable con fundamento de riesgo de crédito pasa el umbral de utilidad

**Qué.** El barrido de F-021 respondía «¿se miró todo?». No respondía «¿se miró bien?». Un barrido mete columnas por meter; un análisis de riesgo elige cada variable porque hay una razón financiera por la que debería predecir el default, y la valida con el instrumento del oficio: **Information Value sobre Weight of Evidence**, no AUC suelto.

**Qué se construyó.** **26 variables**, cada una con su razón escrita, organizadas por los bloques clásicos de suscripción:

| Bloque | Pregunta | Variables |
|---|---|---|
| **A · Capacidad** | ¿puede pagar? | `cap_dti` (salidas/ingreso), `cap_carga_credito` (límite/ingreso anual), `cap_margen`, `cap_cobertura`, `cap_volatilidad` (inestabilidad del ingreso), `cs_ingreso` |
| **B · Comportamiento** | ¿paga? | `comp_pagos_n`, `comp_pagos_por_mes`, `comp_monto_medio`, `comp_esfuerzo` (pagos/límite), `comp_meses_sin_pago`, `comp_irregularidad` |
| **C · Estrés** | ¿está bajo presión? | `est_tasa_rechazo`, `est_tasa_reversion`, `est_dormancia`, `est_retiros_ratio` |
| **D · Exposición** | ¿cuánto debe? | `exp_limite_total`, `exp_n_credito` |
| **E · Condiciones** | ¿qué le cobran? | `cond_tasa_media`, `cond_antig_producto` |
| **F · Relación** | ¿cuánto lo conocen? | `rel_antig_cliente`, `rel_n_productos` |
| **G · Bureau** | ¿qué dice el score? | `cs_credit_score` |
| **H · Tendencia** | ¿va peor? | `tend_entradas`, `tend_pagos` |
| **I · Servicio** | | `srv_quejas` |

El bloque **B es nuevo**: el historial de pagos sobre productos de crédito —el predictor más fuerte en banca real, por delante del score— nunca se había construido. Sale de las 738 964 transacciones de tipo `Payment` unidas a productos de crédito por `product_id`. El feature store no lo tenía.

**Cómo se validó.** Para cada variable: IV sobre 10 bins con corrección de Haldane-Anscombe; prueba de Mann-Whitney U (no asume normalidad); corrección de **Benjamini-Hochberg** por las 26 pruebas simultáneas; contraste del **signo observado contra el signo esperado** declarado *antes* de mirar el dato; y coeficiente de Spearman entre el orden del bin y la tasa de mora, para medir monotonía. Todo por duplicado: global y dentro del estrato de un producto de crédito.

**Resultado.** Umbrales de scorecard: IV < 0.02 inútil · 0.02–0.1 débil · 0.1–0.3 medio · 0.3–0.5 fuerte.

| | Global | Dentro de 1 producto |
|---|---:|---:|
| Variables con IV ≥ 0.02 | 4 de 26 | **1 de 25** |
| Significativas tras Benjamini-Hochberg | 17 | **0** |
| Signo en la dirección esperada | 15 de 26 | 8 de 25 |
| IV máximo | 0.0485 (`exp_limite_total`) | **0.0254** (`comp_irregularidad`) |

**Ninguna variable alcanza siquiera la banda «media» (IV ≥ 0.1).** Dentro del estrato limpio, cero sobreviven la corrección por multiplicidad, y el signo acierta 8 de 25 — peor que tirar una moneda, que es lo que se espera cuando no hay relación.

**Multivariado con el juego razonado.** LightGBM sobre las 26, retenido del 30 %:

| Corrida | AUC | IC 95 % |
|---|---:|---|
| Global | 0.5980 | [0.5881, 0.6092] |
| **Dentro de 1 producto** | **0.5065** | [0.4894, 0.5260] |
| Control barajado, dentro de 1 producto | 0.4830 | [0.4638, 0.4974] |

El control barajado se desvía 0.017 de 0.50 con su intervalo excluyendo el 0.50: eso mide el ruido del propio procedimiento a este tamaño de muestra. El 0.5065 del modelo real cae **dentro** de esa banda de ruido. Las 26 variables razonadas juntas no superan a permutar la etiqueta al azar.

**El benchmark, que es el corazón del asunto.** `credit_score` debe ser input y vara de medir a la vez, con relación **monótona decreciente**: a mayor score, menor mora. Es la lógica del producto y hay que exigirla:

| Decil de score | Rango | n | Tasa de mora |
|---|---|---:|---:|
| d1 | 422–561 | 6 703 | 11.02 % |
| d5 | 614–631 | 6 562 | 11.32 % |
| d10 | 761–850 | 6 546 | 10.17 % |

**IV = 0.0019.** Spearman entre decil y tasa de mora: **ρ = −0.297, p = 0.405**. Un score que funciona da ρ cercano a −1 y separa del orden de 25 % a 1 % entre deciles extremos. Este separa **11.02 % a 10.17 %: 0.85 puntos porcentuales a lo largo de 429 puntos de score**, sin monotonía y sin significancia.

**Decisión.** Queda cerrado con el instrumento correcto, no solo con cobertura. La conclusión de F-017 y F-021 se sostiene bajo análisis de riesgo de crédito hecho como corresponde: **la etiqueta de este dataset no guarda relación con ninguna variable que tenga fundamento financiero.** ML-03 se entrega como esta evidencia.

**Lo que sí queda para ML-01 y ML-02.** El bloque B —comportamiento de pago— es una construcción correcta y reutilizable aunque aquí no discrimine: el agente la necesita para *explicarle* al cliente su situación, y `eligibility_v1.yaml` puede decidir sobre ella como hecho verificable (`comp_meses_sin_pago`, `comp_esfuerzo`). Se incorpora al feature store por su valor descriptivo, declarando que no es predictiva.

**Evidencia.** `logs/eval/iv_riesgo_credito.json` · `logs/eval/features_riesgo.parquet` · `logs/eval/ml03_multivariado.json`.

## F-025 · 2026-09-30 · modelos — Auditoría del feature store contra el método: tres errores propios, y la conclusión sobrevive

**Qué.** Se aplicó al feature store la lista completa de `docs/knowledge/metodo_estadistico.md` — limpieza, descriptivos robustos, outliers, normalidad, VIF, tamaño del efecto y potencia. El análisis de `F-024` había saltado la mitad de esos pasos. Aparecieron tres errores propios y una deuda declarada.

### Error 1 — Monedas mezcladas sin convertir

`cs_ingreso` salió de `customers.estimated_monthly_income` y `exp_limite_total` de `products.credit_limit`, **ambas leídas de bronze en moneda local**. Las medianas por país lo delatan: Colombia **9 192 466 COP**, Argentina **801 955 ARS**, México **39 220**. Un cliente colombiano parecía **234 veces más rico** que uno mexicano por la pura unidad de cuenta. Todo lo que dividía por esas columnas —`cap_dti`, `cap_carga_credito`— quedaba corrompido.

El síntoma estaba a la vista en el descriptivo, que no se había mirado:

| Variable | Media | Mediana | Separación |
|---|---:|---:|---:|
| `cs_ingreso` crudo | 5 875 426 | 336 125 | **1 648 %** |
| `cs_ingreso` en USD | 4 633 | 2 309 | 101 % |
| `exp_limite_total` crudo | 60 595 680 | 126 869 | **47 662 %** |
| `exp_limite_total` en USD | 55 367 | 40 926 | 35 % |

Es exactamente el diagnóstico barato del curso: **si media y mediana se separan un orden de magnitud, algo está mal antes de modelar.** Se corrigió con las tasas de `daily_exchange_rates` a 30 días del corte: ARS 0.0028467, COP 0.00025036, MXN 0.058909.

**Revalidación tras corregir:**

| Variable (USD) | IV global | IV dentro de 1 producto | d Cohen global | d dentro de 1 producto |
|---|---:|---:|---:|---:|
| `ingreso_usd` | 0.0010 | 0.0021 | −0.0110 | — |
| `limite_usd` | 0.0729 | **0.0017** | +0.2569 | **−0.0093** |
| `carga_credito_usd` | 0.0340 | 0.0020 | +0.1577 | — |

El límite corregido **sí** aparece con efecto pequeño global (d = 0.2569). Y **se desploma a −0.0093 dentro del estrato de un producto** — el signo hasta se invierte. Usando el límite **medio por producto**, que elimina el efecto conteo, el d global es −0.0160. Es la tautología de siempre: más productos, más límite total, más sorteos.

La tasa de mora por número de productos sigue reproduciendo la independencia casi exacta:

| Productos de crédito | n | Mora observada | Predicho por independencia |
|---:|---:|---:|---:|
| 1 | 48 396 | 7.41 % | 7.52 % |
| 2 | 21 203 | 13.86 % | 14.47 % |
| 3 | 5 865 | 20.94 % | 20.91 % |
| 5 | 207 | 29.47 % | 32.35 % |

**La conclusión de F-017, F-021 y F-024 se mantiene con las variables corregidas.**

### Error 2 — Una variable duplicada

`comp_pagos_n` y `comp_pagos_por_mes` son **la misma columna dividida entre 6**. El VIF lo delató devolviendo `NaN`: matriz singular por colinealidad perfecta. Los dos d de Cohen idénticos (+0.1484) lo confirman. Se elimina una.

### Error 3 — No se había medido el tamaño del efecto

Es el error grave, porque invalida cómo se presentaron los resultados de `F-024`. Allí se reportaron **17 variables «significativas» tras Benjamini-Hochberg**. Con el tamaño del efecto al lado, esa cifra no significa nada:

| Variable | d de Cohen | Magnitud |
|---|---:|---|
| `exp_n_credito` | +0.4887 | pequeño |
| `rel_n_productos` | +0.2371 | pequeño |
| `cond_antig_producto` | +0.1565 | **despreciable** |
| `comp_pagos_n` | +0.1484 | despreciable |
| `comp_meses_sin_pago` | −0.1415 | despreciable |
| … | | |
| `cs_credit_score` | **−0.0147** | despreciable |

**Solo 2 de 26 variables alcanzan d ≥ 0.2**, y las dos son conteos de productos: la tautología. El `credit_score` tiene un efecto de **−0.0147**, que en la escala de Cohen es indistinguible de cero.

**Y la cifra que lo explica todo:** con 8 101 morosos y 68 805 sanos, el **d mínimo detectable con potencia 80 % y α = 0.05 es 0.0329**. Cualquier diferencia por encima de eso sale significativa. Por eso 17 variables daban p pequeño: **no porque midan riesgo, sino porque n = 76 906**. Es el caso de manual de significación estadística sin significación práctica.

### Lo que sí estaba bien

- **Limpieza básica:** cero columnas de valor único, cero de varianza casi nula, cero `customer_id` duplicados, cero filas duplicadas.
- **La prueba no paramétrica era la correcta, y ahora está justificada:** las **26 variables rechazan normalidad** (D'Agostino-Pearson, p < 0.05 en todas; varias con p = 0). Mann-Whitney era lo que tocaba.
- **El criterio de outliers también:** al no ser normales, el IQR es el método válido. Las colas son extremas — `comp_esfuerzo` curtosis 2 149, `est_retiros_ratio` 1 048, `cap_cobertura` 824 — con 10-17 % de outliers por IQR en las variables de razón.
- **Multicolinealidad limpia:** de las 15 variables con cobertura suficiente, **ninguna llega a VIF 5**. El máximo es `cap_carga_credito` con 2.07. Ningún par supera `|r| = 0.90`.
- **El control de etiqueta barajada** es un baseline más exigente que el `DummyClassifier` que pide el método.

### El problema de cobertura que nadie había mirado

Once de las 26 variables **faltan en más de la mitad de la cohorte**:

| Variable | % nulo |
|---|---:|
| `comp_irregularidad` | 84.8 % |
| `tend_pagos` | 82.8 % |
| `comp_esfuerzo` | 82.9 % |
| `comp_monto_medio` | 82.5 % |
| `cap_volatilidad` | 82.4 % |
| `tend_entradas` | 79.2 % |
| `cap_margen` / `est_retiros_ratio` | 71.6 % |
| `comp_pagos_n` | 60.0 % |
| `cap_cobertura` | 55.9 % |

**El bloque de comportamiento de pago, que se presentó en `F-024` como la gran incorporación, existe para el 15-40 % de los clientes.** No es utilizable como variable de modelo. Sigue siendo útil como hecho descriptivo para el agente cuando existe, y esa es la única forma en que debe presentarse.

### Deuda declarada

El binning de WoE/IV de `F-024` se calculó **sobre la cohorte completa**, no solo sobre entrenamiento. Es fuga de procedimiento según el método. No invalida una conclusión de *ausencia* de señal —la fuga solo puede inflar el resultado, nunca deprimirlo— pero si alguna variable hubiera pasado el umbral, habría que recalcularla particionando primero. Queda escrito para que nadie lo herede sin saberlo.

### Decisión

1. **`cs_ingreso`, `exp_limite_total`, `cap_dti` y `cap_carga_credito` se recalculan en USD** antes de entrar a cualquier tabla. La conversión de moneda es una comprobación de **coherencia**, no de formato: pasa las otras seis validaciones sin problema.
2. **`comp_pagos_por_mes` se elimina** por ser `comp_pagos_n / 6`.
3. **Toda variable se reporta con tamaño del efecto junto al p-valor.** Sin el d de Cohen, un p-valor a esta escala de muestra es decorativo.
4. **Toda variable se reporta con su cobertura.** Un IV calculado sobre el 15 % de la cohorte no es comparable con uno calculado sobre el 100 %.
5. El método queda escrito en **`docs/knowledge/metodo_estadistico.md`** y es el contrato para cualquier afirmación estadística de este repo.

**Evidencia.** `logs/eval/eda_variables.csv` · `logs/eval/eda_auditoria.json` · `logs/eval/vif.json` · `logs/eval/fx_revalidacion.json`.

## F-026 · 2026-09-30 · modelos — La prueba a nivel producto: seis umbrales de mora, tres tipos de producto, un scorecard, y nada separa

**Qué.** Eduardo objetó el «cero de 42 variables califica»: un criterio puede estar mal puesto y entonces el cero no dice nada. Tres sospechas legítimas, las tres probadas.

**Sospecha 1 — el criterio era más estricto que la práctica real.** Cierto. Un scorecard bancario se construye con variables de IV 0.02–0.10 que *combinadas* funcionan; exigir IV ≥ 0.10 por variable individual es más duro que la industria.

**Sospecha 2 — estratificar por `n_productos_credito == 1` tiraba el 37 % de la cohorte.** También cierto, y había un control mejor sin usar: **modelar a nivel producto**, que es donde vive `days_past_due`. Ahí la tautología del `max()` **no existe por construcción**, y se usan 117 949 filas en vez de 76 906 clientes, sin descartar a los multi-producto.

**Sospecha 3 — solo se había probado una definición de etiqueta.**

### La tabla a nivel producto

117 949 productos de crédito con `days_past_due` no nulo, corte 2025-12-31, ventana de 180 días. Variables a nivel producto —límite en USD, tasa, antigüedad, app vinculada, movimientos, pagos, rechazos, reversiones, uso de línea, ratios sobre ingreso— más el contexto del cliente. LightGBM, retenido del 30 %, IC 95 % por bootstrap.

| Umbral de mora | Positivos | Tasa | AUC | IC 95 % |
|---|---:|---:|---:|---|
| dpd ≥ 1 | 17 664 | 14.98 % | 0.5103 | [0.5026, 0.5190] |
| dpd ≥ 15 | 17 664 | 14.98 % | 0.5103 | [0.5026, 0.5190] |
| **dpd ≥ 30** | 14 741 | 12.50 % | **0.4984** | [0.4885, 0.5086] |
| dpd ≥ 60 | 11 809 | 10.01 % | 0.5009 | [0.4911, 0.5121] |
| dpd ≥ 90 | 8 876 | 7.53 % | 0.4960 | [0.4877, 0.5091] |
| dpd ≥ 120 | 5 835 | 4.95 % | 0.5014 | [0.4895, 0.5132] |
| **CONTROL barajado** | — | — | **0.5092** | [0.4981, 0.5210] |

**La fila que cierra el asunto es la última.** El mejor resultado de los seis umbrales es 0.5103 — y el control con la etiqueta permutada al azar da **0.5092**. Una diferencia de **0.0011**. Todo lo demás cae por debajo del ruido del propio procedimiento.

### Por tipo de producto

Tarjeta, préstamo personal e hipotecario tienen dinámicas de riesgo distintas en banca real. Aquí no:

| Producto | n | AUC | IC 95 % |
|---|---:|---:|---|
| Tarjeta Crédito | 89 464 | 0.4920 | [0.4799, 0.5038] |
| Préstamo Personal | 17 877 | 0.4954 | [0.4631, 0.5228] |
| Préstamo Hipotecario | 10 608 | 0.5002 | [0.4643, 0.5413] |

### El conteo de productos deja de aportar

A nivel cliente, `n_productos_credito` daba d de Cohen +0.4890 — el mayor del catálogo. **A nivel producto, añadirlo como covariable da AUC 0.4962**, contra 0.4960 sin él. No aporta nada. Es la confirmación directa de que ese efecto era **puro artefacto de agregación** y no una propiedad del riesgo.

Restringiendo además a clientes con un solo producto de crédito: 0.4978.

### El scorecard: ¿combinan las variables débiles?

Se construyó como se construye uno de verdad: **regresión logística sobre variables transformadas a WoE**, con el binning ajustado **solo en entrenamiento** —lo que de paso salda la deuda de fuga declarada en `metodo_estadistico.md`—.

| Modelo | Variables | AUC | IC 95 % |
|---|---:|---:|---|
| Scorecard con **todas**, sin filtro de IV | 16 | **0.4967** | [0.4864, 0.5094] |

Los cortes por IV ≥ 0.01 y ≥ 0.02 **no llegaron a correr: ninguna variable los alcanza.** El IV máximo ajustado honestamente en entrenamiento es **0.0026** (`ticket_max`), seguido de `credit_score` con **0.0022**. El umbral de «inútil» de la convención de scorecards es 0.02: estamos **casi ocho veces por debajo del piso de lo inútil**.

### La distribución que lo explica

A nivel producto, `days_past_due` se reparte así: **0 → 100 285**, y luego 15 → 2 923 · 30 → 2 932 · 60 → 2 933 · 90 → 3 041 · 120 → 2 903 · 180 → 2 932.

Seis cubetas prácticamente idénticas. Una cartera real decae por tasas de traspaso —de 30 a 60 días pasa una fracción, de 60 a 90 una menor—. Aquí no hay decaimiento: hay un sorteo uniforme sobre seis niveles, condicionado a que el producto esté en mora.

### Decisión

**El «cero de 42» no era un artefacto del criterio.** Se probó relajándolo hasta desaparecer —un scorecard sin ningún filtro de IV—, cambiando la unidad de análisis a la que es correcta, probando seis definiciones de la etiqueta y segmentando por tipo de producto. **Ninguna combinación separa del azar, y la mejor de todas queda por debajo de su propio control barajado.**

ML-03 se entrega con esta tabla. Es una respuesta más fuerte que la de F-024, porque ya no depende de un umbral elegido por quien escribe.

**Lo que además queda resuelto:** la deuda de fuga en el binning de WoE. El scorecard de este hallazgo ajusta el WoE solo en entrenamiento y aplica el mapa a validación, que es lo que el método exige.

**Evidencia.** `logs/eval/nivel_producto.json`.

## F-027 · 2026-09-30 · datos — `days_past_due` no es mora: siete cruces de validación, siete fallos

**Qué.** Eduardo cuestionó la premisa entera: «¿para qué usas `days_past_due` si eso no me dice si el cliente cayó en mora?». La objeción correcta, y la que no se había hecho. Todo el trabajo previo —F-017, F-021, F-024, F-026— daba por bueno que esa columna era la variable objetivo porque **en banca real lo es**: Basilea define default como 90+ días de atraso. Pero eso es el concepto. Que una columna *se llame* así no prueba que *mida* eso.

En una cartera real la mora nunca viene sola. Un producto en default arrastra un cortejo de fenómenos observables. Se cruzaron los siete.

### 1 · El estado del producto no sabe nada de la mora

| `product_status` | n | % mora 90+ | dpd medio |
|---|---:|---:|---:|
| Active | 106 596 | 7.48 % | 12.3 |
| Closed | 10 024 | 7.65 % | 12.4 |
| **Blocked** | 6 223 | **7.76 %** | 12.7 |
| **Suspended** | 2 507 | **7.90 %** | 13.0 |

Un producto **bloqueado** tiene la misma tasa de mora que uno **activo**. En cualquier banco, un producto se bloquea o se suspende *a causa* del impago: la relación debería ser casi determinista. Aquí el rango completo es de 0.42 puntos porcentuales.

### 2 · No hay deuda que deber

| Grupo | n | % con saldo cero | Saldo mediano | Utilización media |
|---|---:|---:|---:|---:|
| Al día | 106 585 | 2.14 % | 11 648.93 | 0.2902 |
| Mora 1–89 | 9 343 | 2.42 % | 10 695.47 | 0.3010 |
| **Mora 90+** | 9 422 | **2.30 %** | 14 452.50 | **0.3083** |

La utilización de línea de un moroso a 90 días es **0.3083**; la de uno al día, **0.2902**. En banca real el moroso llega al default con la línea agotada, utilización por encima de 0.9. Además, el 2.30 % de los productos en mora 90+ tiene **saldo cero o negativo**: se puede deber nada y estar en mora de ello.

### 3 · La prueba que lo cierra: mora mayor que la vida del producto

| Vida del producto | n | % dpd ≥ 90 | % dpd ≥ 180 | **Imposibles** |
|---|---:|---:|---:|---:|
| **Menos de 30 días** | 8 620 | 7.32 % | **2.32 %** | **7 518** |
| 30–90 días | 2 534 | 7.06 % | 2.53 % | 219 |
| 90–180 días | 3 771 | 7.88 % | 2.47 % | 121 |
| Más de 180 días | 110 425 | 7.53 % | 2.49 % | 0 |

«Imposibles» son los productos cuya mora **supera su propia edad**. De los 8 620 productos abiertos hace menos de 30 días, **7 518 —el 87.2 %— arrastran más días de mora que días de existencia.** Doscientos productos abiertos hace tres semanas figuran con 180 días de atraso.

Esto no es ruido ni error de medición: es la firma de una columna **rellenada al azar sin mirar la fecha de apertura**. En total, **7 858 de 125 350 productos (6.27 %) son contablemente imposibles**.

Y obsérvese la segunda columna: la tasa de mora a 90 días es 7.32 %, 7.06 %, 7.88 % y 7.53 % según la vida del producto. En una cartera real la mora temprana se concentra en los primeros doce meses; aquí es **plana respecto a la edad del producto**, que es otra manera de decir lo mismo.

### 4 · La tarjeta sigue funcionando

| Grupo | n | Días desde última transacción | % activo últimos 30 días |
|---|---:|---:|---:|
| Al día | 81 554 | 562.9 | 25.01 % |
| Mora 1–89 | 7 082 | 567.1 | 24.43 % |
| **Mora 90+** | 7 168 | **559.6** | **25.04 %** |

Un producto en default se bloquea. Aquí el moroso a 90 días opera **igual, y de hecho un poco más reciente** que el cliente al día. Sin bloqueo no hay default.

### 5 · No existe la cobranza

Categorías de contacto en `call_center_interactions`:

| `reason_category` | n |
|---|---:|
| Transaccional | 240 056 |
| Producto | 150 863 |
| Queja | 117 021 |
| Técnico | 102 899 |
| Comercial | 54 879 |
| Retención | 20 578 |

**No hay categoría de cobranza.** Ni «Cobranza», ni «Collections», ni «Recuperación». En un banco con 9 422 productos en mora a 90 días, la cobranza es de los mayores volúmenes de contacto del centro de llamadas. Su ausencia total significa que **el dataset no simula un proceso de cobranza**, y sin cobranza la mora no es un fenómeno del negocio: es una etiqueta suelta.

Lo mismo en `complaints`: los tipos son Complaint, Claim, Request y Suggestion. Ninguno de recuperación de cartera.

### 6 · El moroso paga igual que el sano

| Grupo | n | Pagos medios en 180 días | % sin ningún pago | Días desde el último pago |
|---|---:|---:|---:|---:|
| Al día | 106 585 | 0.431 | 69.41 % | 80.3 |
| Mora 1–89 | 9 343 | 0.424 | 69.72 % | 79.0 |
| **Mora 90+** | 9 422 | **0.429** | **69.44 %** | **79.0** |

Idénticos hasta el tercer decimal. **Dejar de pagar es la definición operativa de caer en mora**, y aquí el grupo en mora 90+ paga exactamente lo mismo que el que está al día.

Hay además un absurdo colateral: **el 69.41 % de los productos al día tampoco registra ningún pago en seis meses.** Una tarjeta de crédito vigente sin un solo pago en medio año no existe.

### 7 · No hay una definición mejor en ninguna otra columna

Se buscó. `product_status` tiene cuatro niveles —Active, Closed, Blocked, Suspended— y ninguno es «Castigado», «Vencido» ni «Default»; ya se vio en la prueba 1 que además no correlacionan con la mora. Las 132 118 transacciones de tipo `Adjustment`, que en un core bancario podrían ser castigos o condonaciones, tienen `transaction_category` **nula en el 100 % de los casos** y un monto mediano de 507.93 USD: son ajustes genéricos, no write-offs. No hay tabla de cobranzas, ni de refinanciaciones, ni calendario de pagos con el cual derivar un atraso.

### Qué significa

**Eduardo tenía razón y el error conceptual era del análisis, no del criterio estadístico.** `days_past_due` es un número entre siete valores posibles, adosado al producto, que **no concuerda con el estado del producto, ni con el saldo, ni con la utilización, ni con la antigüedad, ni con la actividad transaccional, ni con el historial de pagos, ni con proceso de cobranza alguno —porque no existe—.**

No es que el default sea difícil de predecir en este dataset. **Es que el default no está medido.** La pregunta «¿qué variables predicen la mora?» no tiene respuesta porque la variable dependiente no existe: lo que hay es un identificador de cubeta sorteado.

Esto **refuerza** los hallazgos anteriores en vez de invalidarlos: F-026 mostró que ninguna combinación de variables separa del azar ni siquiera a nivel producto, con seis umbrales y un scorecard sin filtro. Ahora se sabe **por qué**, y la respuesta no es «el dataset es difícil» sino «esa columna no es lo que su nombre dice».

### Decisión

1. **ML-03 no se presenta como un modelo de riesgo que falló.** Se presenta como **la validación que demuestra que la variable objetivo no existe**, con esta tabla de siete cruces. Es un resultado más fuerte y más difícil de refutar que un AUC.
2. **Ninguna decisión del sistema se apoya en `days_past_due`.** Ni el modelo, ni la política, ni el agente. Puede exponerse al cliente como dato descriptivo del sistema de origen, declarando su procedencia, nunca como juicio de riesgo.
3. **La regla que deja, y es la más importante del proyecto:** antes de aceptar una columna como variable objetivo, exigirle **el cortejo de fenómenos que la acompañarían si fuera real**. Una distribución sospechosa (F-019, F-020) levanta la duda; el cruce con los hechos colaterales la resuelve. Una columna que se llama `days_past_due` y no se relaciona con el bloqueo del producto, el saldo, los pagos ni la cobranza, no es mora por mucho que se llame así.
4. `eligibility_v1.yaml` decide sobre hechos verificables —ingreso en USD, capacidad de pago estimada, antigüedad, condiciones del producto— que **sí** son observables y consistentes. Esa era la tesis desde el principio y ahora tiene su demostración completa.

**Evidencia.** Salida de `scripts` de validación en `logs/eval/`; las siete tablas son reproducibles contra `data/bronze/products`, `transactions` y `call_center_interactions`.

## F-028 · 2026-09-30 · datos — Las dos alternativas a `days_past_due` tampoco son mora, y una casi engaña

**Qué.** Descartada `days_past_due` (F-027), Eduardo propuso dos candidatas mejores. Ambas son razonables en banca real. Ninguna sobrevive.

---

### A · `last_transaction_date` — no es la fecha de la última operación

La idea es correcta: saber cuándo operó por última vez un producto, o cuándo pagó, es información de primer orden. El problema es que esta columna **no contiene eso**.

Se cruzaron los 305 721 productos que la tienen contra la última transacción real de ese mismo producto en la tabla `transactions`:

| Comprobación | Resultado |
|---|---:|
| Coincide con la última transacción real | **427** de 305 721 · **0.14 %** |
| Coincide con el último pago real | **191** · **0.06 %** |
| Desfase medio respecto a la última transacción real | **−650.5 días** |
| Anterior a la fecha de apertura del producto | 0 |

Y el rango la delata:

| Fuente | Mínimo | Máximo |
|---|---|---|
| `products.last_transaction_date` | **2018-06-21** | 2026-06-17 |
| `transactions.transaction_date` | **2023-06-17** | 2026-06-18 |

La columna arranca en **2018**, cinco años antes de que exista la primera transacción del dataset. Es un campo generado de forma independiente, no derivado de los movimientos. El único constraint que sí respeta es no ser anterior a la apertura del producto.

**Por eso está en la lista de columnas vetadas**, aunque por otra razón: si fuera real sería fuga de información —un producto en mora deja de transar, así que la fecha codificaría el desenlace—. Resulta que además ni siquiera es real.

---

### B · `product_status` — la trampa que casi pasa

Esta era la hipótesis fuerte: si un producto está **Blocked** o **Suspended**, quizá *ese* es el default de verdad, y `days_past_due` es un campo decorativo. En banca se bloquea un producto precisamente por impago.

La primera medición parecía darle la razón de forma espectacular:

| Objetivo | Tasa | AUC | IC 95 % |
|---|---:|---:|---|
| Blocked o Suspended | 6.96 % | **0.9005** | [0.8971, 0.9034] |
| Solo Blocked | 4.99 % | 0.8942 | [0.8907, 0.8978] |
| Solo Suspended | 1.98 % | 0.8795 | [0.8744, 0.8843] |
| Closed | 8.01 % | 0.9057 | [0.9027, 0.9086] |
| CONTROL barajado | 6.96 % | 0.5017 | [0.4927, 0.5131] |

**AUC 0.90 con el control barajado en 0.50.** Después de cinco hallazgos diciendo que aquí no hay señal, esto parecía el vuelco.

**No lo era.** El perfil de los grupos lo destapa:

| `product_status` | n | Pagos medios | Transacciones medias | Días desde la última |
|---|---:|---:|---:|---|
| Active | 105 603 | 0.549 | 2.13 | 60.7 |
| Blocked | 6 193 | **0.000** | **0.00** | — |
| Closed | 9 945 | **0.000** | **0.00** | — |
| Suspended | 2 454 | **0.000** | **0.00** | — |

Y la comprobación directa sobre **todas** las transacciones del dataset, sin filtro de fecha:

| `product_status` | n | Sin ninguna transacción | % |
|---|---:|---:|---:|
| Active | 112 224 | 0 | **0.00 %** |
| Closed | 10 550 | 10 550 | **100 %** |
| Blocked | 6 554 | 6 554 | **100 %** |
| Suspended | 2 644 | 2 644 | **100 %** |

**Separación perfecta por construcción.** El generador sencillamente no creó ninguna transacción para los productos que no están activos. Cualquier variable derivada de transacciones predice el estado de forma trivial: no está midiendo riesgo, está midiendo que un producto cerrado no opera.

La prueba definitiva es quitar todo lo transaccional y repetir:

| Objetivo, **sin variables transaccionales** | Tasa | AUC | IC 95 % |
|---|---:|---:|---|
| Blocked o Suspended | 6.96 % | **0.4960** | [0.4847, 0.5053] |
| Closed | 8.01 % | 0.4997 | [0.4875, 0.5103] |
| Sin transaccionales y **sin `dpd`** | 6.96 % | 0.4960 | [0.4847, 0.5053] |
| CONTROL barajado | 6.96 % | 0.5025 | [0.4915, 0.5136] |

**De 0.9005 a 0.4960.** Todo el poder predictivo era la tautología del «no transó».

Y las medianas del perfil confirman que no hay nada que distinga a un producto bloqueado:

| `product_status` | Límite | Saldo | Tasa | Antigüedad | Score | Utilización | dpd |
|---|---:|---:|---:|---:|---:|---:|---:|
| Active | 93 829 | 11 691 | 27.43 | 1 378 | 631 | 0.072 | 0 |
| Blocked | 85 898 | 11 733 | 27.43 | 1 379 | 632 | 0.073 | 0 |
| Closed | 91 271 | 10 893 | 27.45 | 1 381 | 632 | 0.070 | 0 |
| Suspended | 76 060 | 9 596 | 27.34 | 1 408 | 629 | 0.069 | 0 |

Score 631 contra 632. Utilización 0.072 contra 0.073. Antigüedad 1 378 contra 1 379. Un producto bloqueado es, en todo lo observable, **idéntico** a uno activo.

---

### Qué deja

1. **No hay definición alternativa de default en este dataset.** Se probaron las tres candidatas: `days_past_due` (F-027), `product_status` y `last_transaction_date`. Ninguna es un fenómeno medido.
2. **La lección de método es la más valiosa del proyecto.** Un AUC de 0.90 con el control barajado en 0.50 pasa cualquier validación estándar. Lo que lo destapó fue **mirar el perfil de los grupos antes de celebrar**: tres estados con exactamente cero transacciones es una imposibilidad operativa, no un hallazgo. La regla que dejó F-020 —«ante una variable que discrimina sospechosamente bien, mirar su distribución por clase»— se aplica igual a un **objetivo** que discrimina sospechosamente bien.
3. **Se añade una comprobación al método:** cuando un modelo separa con AUC alto, **quitar el bloque de variables más obvio y volver a medir**. Si el AUC se desploma, lo que había era una relación estructural, no riesgo.
4. La tesis del proyecto queda con su demostración completa: la elegibilidad la decide `eligibility_v1.yaml` sobre hechos verificables, porque **los tres candidatos a variable objetivo de este dataset son sintéticos y está probado uno por uno**.

**Evidencia.** `logs/eval/` — reproducible contra `data/bronze/products`, `transactions` y `customers`.

## F-029 · 2026-09-30 · datos — No hay pagos: **todos los montos de transacción son uniformes**. La mora no se puede construir porque no existe el calendario

**Qué.** Eduardo reencuadró el problema correctamente: si no existe el default, **construyamos nosotros la mora al corte**. Un producto de crédito con saldo pendiente y sin pagar desde hace N días **está** en mora por definición contable; no hace falta que nadie lo etiquete. Y insistió, con razón, en que la fecha del último pago tenía que servir para algo.

Distinción que hubo que hacer primero: lo descartado en F-028 fue **`products.last_transaction_date`**, un campo del snapshot que no coincide con nada. Lo que Eduardo proponía es distinto y no se había probado: **`max(transaction_date)` de las transacciones de tipo `Payment`**, que es dato observado.

Se construyó. El resultado invalida la premisa entera, y va más allá de `days_past_due`.

### 1 · El pago no es un fenómeno regular

| Producto | n | Meses de vida | **Pagos TOTALES** | Pagos/mes | Sin ningún pago jamás |
|---|---:|---:|---:|---:|---:|
| Tarjeta Crédito | 94 258 | 45.4 | **1.29** | 0.028 | **33.64 %** |
| Préstamo Personal | 18 780 | 45.2 | 5.16 | 0.114 | 15.13 % |
| Préstamo Hipotecario | 11 157 | 45.2 | 5.15 | 0.114 | 14.76 % |

Una tarjeta de crédito con **45 meses de vida** registra **1.29 pagos en total**. Debería registrar unos 45. Un préstamo hipotecario a casi cuatro años lleva **5.15 cuotas**.

Y el reparto: **29.14 % de los productos no tiene ni un solo pago**, 21.78 % tiene exactamente uno, 17.28 % tiene dos. **El 68 % acumula dos pagos o menos en cuatro años.**

### 2 · No existe calendario de pagos en ningún producto

Espaciado entre pagos consecutivos, sobre 328 025 intervalos medidos:

| Métrica | Valor | Lo esperable |
|---|---:|---|
| Espaciado medio | **183.6 días** | ~30 |
| Mediana | 129 días | ~30 |
| Desviación estándar | **172.6 días** | pequeña |
| % de intervalos mensuales (25–35 días) | **5.09 %** | ~100 % |

Y al buscar el subconjunto que sí tuviera calendario:

| Criterio | Productos |
|---|---:|
| Con 2 o más pagos | 160 054 |
| Con 6 o más intervalos | 19 961 |
| Con espaciado medio mensual | **3** |
| **Con calendario regular** (mensual y sd < 10 días) | **0** |

**Cero.** De 160 054 productos con historial, ninguno amortiza con periodicidad.

### 3 · El monto del pago no se relaciona con nada del producto

| Correlación del pago medio con… | r |
|---|---:|
| Saldo del producto | **0.0027** |
| Límite de crédito | −0.0007 |
| Tasa de interés | −0.0006 |

En un préstamo real la cuota es función directa del principal, la tasa y el plazo: r cercano a 1. Y el pago mediano es **~1 030 USD igual para tarjeta, préstamo personal e hipotecario**, con saldos medianos de 3.3 M, 16.8 M y 177.5 M respectivamente. La cuota de una hipoteca y el pago de una tarjeta salen de la misma urna.

### 4 · La razón de fondo: **todos los montos del dataset son uniformes**

Esta es la conclusión que trasciende la pregunta original. Se contrastó cada tipo de transacción contra la uniforme teórica de su propio rango:

| Tipo | n | Mín | Máx | σ observada | σ teórica | Curtosis | KS p |
|---|---:|---:|---:|---:|---:|---:|---:|
| Purchase | 462 526 | 5.00 | 500.00 | 143.11 | **142.89** | −1.204 | 0.142 |
| Withdrawal | 411 832 | 20.00 | 500.00 | 138.50 | **138.56** | −1.199 | 0.794 |
| Transfer | 382 069 | 100.02 | 9 999.96 | 2 858.03 | **2 857.87** | −1.200 | 0.395 |
| **Payment** | 314 610 | 50.00 | 2 000.00 | **563.52** | **562.92** | **−1.200** | 0.197 |
| Deposit | 260 364 | 50.02 | 4 999.99 | 1 426.72 | **1 428.93** | −1.195 | 0.741 |
| Adjustment | 56 151 | 10.03 | 1 000.00 | 285.94 | **285.78** | −1.199 | 0.858 |

La curtosis de una uniforme es **−1.2 exacta**. Las seis dan entre −1.195 y −1.204. Las seis desviaciones coinciden con `(máx − mín)/√12` hasta el segundo decimal. El test de Kolmogorov-Smirnov **no rechaza la uniformidad en ninguno** (todos los p sobre 0.05).

**Cada monto de este dataset es un sorteo uniforme sobre un rango fijo por tipo de transacción.** Un pago es Uniforme(50, 2000) USD, echado con independencia del saldo, del límite y de la tasa.

### 5 · Qué pasa si se construye la mora de todas formas

Aplicando la definición contable honesta —saldo pendiente y sin pagar desde hace N días—:

| Definición | Productos en mora | Total | % |
|---|---:|---:|---:|
| Mora 30 días | 113 455 | 124 195 | **91.35 %** |
| Mora 60 días | 106 305 | 124 195 | 85.60 % |
| Mora 90 días | 99 722 | 124 195 | **80.29 %** |
| Mora 180 días | 84 423 | 124 195 | 67.98 % |

**El 80 % de la cartera estaría en default a 90 días.** Eso no es una cartera con problemas: es una cartera que no existe. Ningún banco opera con una NPL del 80 %.

Y el contraste contra la columna original confirma que ambas cosas son independientes:

| Según `days_past_due` | n | Días sin pagar (media) | % en mora construida a 90 | Pagos totales |
|---|---:|---:|---:|---:|
| Al día | 100 285 | 3 113.0 | 80.30 % | 2.226 |
| Mora 1–89 | 15 034 | 3 174.9 | 80.55 % | 2.179 |
| **Mora 90+** | 8 876 | **3 138.5** | **79.81 %** | 2.221 |

El producto «en mora 90+» según la columna lleva **3 138 días sin pagar**; el que está «al día», **3 113**. Veinticinco días de diferencia sobre ocho años y medio.

### Qué significa

**La intuición de Eduardo era correcta y el método también.** Si no hay default, se construye la mora desde el comportamiento de pago: es exactamente lo que haría un analista de riesgo con una foto de cartera. El problema no está en la idea sino en que **no hay pagos que observar**: hay transacciones etiquetadas `Payment` cuyo monto es un sorteo uniforme y cuya fecha no obedece a ningún calendario.

Sin fecha de vencimiento no hay atraso. **La mora no es una variable difícil de construir en este dataset: es una variable que no tiene referente.**

### Consecuencia para ML-04 — hay que avisar a Federico

El modelo de capacidad de pago se construye sobre montos de `Deposit` y `Withdrawal`. **Ambos son uniformes.** Eso explica sin residuo por qué su MAE le gana al baseline por apenas **0.39 %** y por qué en USD las dos cifras coinciden hasta el decimal: no hay nada que estimar, porque el flujo futuro es independiente del pasado por construcción.

No invalida el modelo como **pieza de ingeniería** —el corte temporal, el techo duro y la puerta de abstención están bien hechos y son lo que se evalúa—, pero sí obliga a reportarlo como **estimador sobre datos sintéticos**, no como medición de capacidad real.

### Decisión

1. **El sistema no puede determinar si un cliente está en mora, y lo dice.** No es una limitación que se esconde: es un resultado. `eligibility_v1.yaml` trata «estado de mora no determinable» como rama de primera clase, no como excepción — coherente con la regla del proyecto de que abstenerse es un resultado válido.
2. **Lo que sí se puede afirmar al cliente** son hechos observados con su procedencia: cuántos pagos registra, de qué monto, en qué fechas, cuál es su saldo y su límite. Todo eso existe y es consultable. Lo que no se puede es **derivar de ahí un juicio de mora**.
3. **ML-03 se entrega como la cadena completa de validación**: no existe la variable objetivo (F-027), no existe en las alternativas (F-028), y **no se puede construir** porque no hay calendario de pagos (F-029). Tres niveles de evidencia, cada uno más fundamental que el anterior.
4. **Regla nueva para el método:** ante una tabla de hechos, contrastar los **montos** contra la uniforme de su propio rango antes de construir nada encima. σ = (máx−mín)/√12 y curtosis = −1.2 son dos números que se calculan en un minuto y ahorran días. Ya lo había enseñado `fraud_score` en F-020; aquí aplica a **toda** la tabla de transacciones.

**Evidencia.** `logs/eval/` — reproducible contra `data/bronze/transactions` y `data/bronze/products`.

## F-030 · 2026-09-30 · datos — El calendario supuesto: kappa 0.0001 entre la mora construida y `days_past_due`

**Qué.** Método propuesto por Eduardo, implementado tal cual: **suponer que la cuota vence a fin de cada mes**, contar los meses desde la apertura del producto hasta el corte para saber cuántas cuotas *debería* haber pagado, contar las que pagó de verdad, y con la diferencia levantar la bandera de mora. Validar además contra la fecha de la última transacción.

El supuesto se declara como supuesto, no como dato. Es exactamente lo que haría un analista con una foto de cartera sin calendario de pagos.

**Sobre las columnas prohibidas.** `products.last_transaction_date` está vetada **como variable de modelo** —fuga: un producto en default deja de transar, así que la fecha codifica el desenlace—. Construir un **estado descriptivo al corte** es otro uso y no constituye fuga. Aun así no se usó esa columna, porque F-028 probó que no coincide con las transacciones reales: se usó `max(transaction_date)` observado.

### El cálculo

```
cuotas_esperadas = meses entre apertura y corte
cuotas_pagadas   = transacciones Payment aprobadas antes del corte
cuotas_atrasadas = esperadas − pagadas
cumplimiento     = pagadas / esperadas
flag_mora_30     = más de 30 días sin un pago
```

### Resultado

| Producto | Cuotas esperadas (mediana) | Cuotas pagadas (mediana) | **Atrasadas** | Cumplimiento medio |
|---|---:|---:|---:|---:|
| Tarjeta Crédito | 45 | 1 | **43** | 4.6 % |
| Préstamo Personal | 45 | 3 | **41** | 9.8 % |
| Préstamo Hipotecario | 45 | 3 | **41** | 9.7 % |

Distribución del cumplimiento:

| Fracción de cuotas pagadas | Productos | % |
|---|---:|---:|
| **0 %** | 35 805 | **29.14 %** |
| 0–5 % | 38 114 | 31.02 % |
| 5–10 % | 19 891 | 16.19 % |
| 10–25 % | 17 801 | 14.49 % |
| 25–50 % | 6 130 | 4.99 % |
| 50–80 % | 1 867 | 1.52 % |
| **80–100 %** | 1 268 | **1.03 %** |

**El 60 % de la cartera ha pagado menos del 5 % de sus cuotas.** Solo el 1.03 % está al corriente.

Las banderas resultantes:

| Bandera | Productos | % |
|---|---:|---:|
| Al menos una cuota atrasada | 119 885 | **96.53 %** |
| Más de 30 días sin pagar | 115 991 | **93.39 %** |

### La validación cruzada contra la última transacción — la idea que Eduardo pedía comprobar

| Días sin transaccionar | Productos | % con bandera de mora | **Cuotas atrasadas (mediana)** | dpd medio según la columna |
|---|---:|---:|---:|---:|
| 0–30 días | 28 929 | 71.64 % | **42** | 12.22 |
| 31–90 | 37 071 | 100 % | **42** | 12.43 |
| 91–180 | 24 690 | 100 % | **42** | 12.17 |
| 181–365 | 12 989 | 100 % | **42** | 12.61 |
| Más de un año | 1 918 | 100 % | **42** | 10.64 |

**Cuarenta y dos cuotas atrasadas en todos los tramos.** Un producto que transó ayer arrastra el mismo atraso que uno que lleva más de un año sin moverse. Y el `dpd` de la columna se mantiene plano —de 12.22 a 10.64— justo al revés de lo que debería: el tramo de mayor abandono es el que menos mora registra.

### El número que lo cierra: kappa de Cohen = 0.0001

Cruzando la bandera construida contra `days_past_due ≥ 90`:

| Según `days_past_due` | % con bandera de mora |
|---|---:|
| Al día | **93.40 %** |
| Mora 1–89 | 93.13 % |
| Mora 90+ | **93.44 %** |

Acuerdo observado **0.1282**, acuerdo esperado por azar **0.1281**. **Kappa = 0.0001.**

Los dos indicadores de mora —uno construido desde el comportamiento de pago observado, otro leído de la columna del dataset— **coinciden exactamente lo que coincidirían dos monedas lanzadas al aire**.

### El ejemplo que lo ilustra

Productos con más cuotas atrasadas, ordenados:

| Producto | Cuotas esperadas | Pagadas | Atrasadas | Cumplimiento | Días sin pago | **`days_past_due`** |
|---|---:|---:|---:|---:|---:|---:|
| Tarjeta Crédito | 90 | 0 | 90 | 0 % | nunca pagó | **0** |
| Préstamo Personal | 90 | 0 | 90 | 0 % | nunca pagó | **0** |
| Préstamo Hipotecario | 90 | 0 | 90 | 0 % | nunca pagó | **0** |

Una hipoteca de siete años y medio, cero pagos registrados, y el dataset la marca **al día**.

### Sobre los AUC del flag construido — advertencia de honestidad

Usar la bandera como variable objetivo da AUC 0.9932 para `flag_mora_cuotas` y 0.8486 para `cumplimiento < 5 %`. **Esas cifras no valen**: `cuotas_esperadas` está a la vez entre las variables predictoras y dentro de la construcción del objetivo. Es tautología, la misma clase de artefacto que el conteo de productos en F-017 o el «no transó» de F-028. Se dejan escritas para que nadie las cite como hallazgo.

Y con 93–96 % de positivos, la bandera **no sirve como objetivo de modelo** por falta de varianza: predecir «sí» a todo acertaría el 96 %.

### Qué queda, y es útil

El método de Eduardo **no encuentra la mora, pero produce el hecho verificable** que el sistema sí puede afirmar:

> «Este producto registra **1 pago** de las **45 cuotas** que corresponderían desde su apertura, bajo el supuesto de vencimiento mensual.»

Eso es una cifra trazable, con su supuesto declarado, que sale de un tool y que el `GroundingChecker` puede validar. **No es un juicio de mora** —para eso haría falta un calendario de pagos que no existe— pero es información real que el cliente tiene derecho a ver, y es más de lo que da `days_past_due`.

### Decisión

1. **Se incorpora `cuotas_esperadas`, `cuotas_pagadas` y `cumplimiento` al feature store como hechos descriptivos**, con el supuesto de vencimiento mensual declarado en el nombre del campo y en la respuesta del agente.
2. **No se usan como variable objetivo ni como predictores** de nada: sin varianza y con tautología de construcción.
3. **`eligibility_v1.yaml` puede decidir sobre el cumplimiento** —por ejemplo, exigir un mínimo de cuotas pagadas— porque es un hecho observado, a diferencia de la mora, que no lo es.
4. La cadena de evidencia sobre la variable objetivo queda cerrada en cuatro niveles: no existe (F-027), no está en las alternativas (F-028), no se puede construir por falta de calendario (F-029), y **al construirla con un calendario supuesto el acuerdo con la columna es kappa 0.0001** (F-030).

**Evidencia.** `logs/eval/` — reproducible contra `data/bronze/products` y `transactions`.

## F-031 · 2026-09-30 · datos — **La causa raíz: productos y transacciones se generaron por separado y se unieron después**

**Qué.** Eduardo señaló dos cosas que yo había pasado por alto y que, juntas, destapan el mecanismo de todo lo anterior.

La primera: *«la mediana de cuotas atrasadas es 42 en los cinco tramos. ¿Por qué 42? Algo anda mal en la data»*. Yo lo había reportado como «plano, sin señal» sin preguntarme de dónde salía el número.

La segunda: *«no me puedes decir 90 % al día y 90 % en mora; deben sumar 100»*. Es el primer informe que se mira en riesgo de crédito y no lo había hecho.

### La clasificación de cartera, que debió ser el chequeo número uno

Misma cartera, mismo corte, dos lecturas. Las dos suman 100 %.

| Tramo | Según `days_past_due` | Según el pago observado |
|---|---:|---:|
| Al día | **85.03 %** | **6.61 %** |
| 1–30 días | 4.97 % | — |
| 31–60 | 2.48 % | 5.89 % |
| 61–90 | 2.58 % | 5.43 % |
| 91–180 | — | 12.59 % |
| Más de 180 | — | 40.35 % |
| 90+ | 4.94 % | — |
| Nunca pagó | — | **29.14 %** |

Una dice que **el 85 % de la cartera está al corriente**. La otra, que **el 6.6 %** lo está. No pueden ser las dos ciertas, y la contradicción estaba disponible desde el primer día con dos consultas.

### De dónde sale el 42

Mediana de cuotas esperadas: **45**. Mediana de cuotas pagadas: **1**. El 42 no es comportamiento: **es aritmética**, 45 menos 1 menos el redondeo de la mediana. Y se repite idéntico en todos los tramos porque la fecha de apertura no guarda relación con la actividad transaccional.

Por qué la mediana de cuotas esperadas es 45 para todo: **`opening_date` es una uniforme perfecta** sobre 2018-06-18 a 2026-06-17.

| Estadístico | Observado | Teórico si es uniforme |
|---|---:|---:|
| Media (días desde el inicio) | 1 460.6 | **1 460.5** |
| Desviación estándar | 843.04 | **843.22** |
| Asimetría | 0.0012 | 0 |
| Curtosis | −1.1978 | **−1.2** |
| Kolmogorov-Smirnov | p = 0.3201 | no se rechaza |

Aperturas por año: 50 118 · 49 918 · 50 110 · 50 115 · 50 091 · 50 042 · 49 644. Cincuenta mil clavados cada año, con 2018 y 2026 a medias por ser años parciales. Ningún banco crece así.

### La prueba de integridad que nunca hice

**El 18.7 % de las transacciones tiene fecha anterior a la apertura de su propio producto.** Son **827 610** transacciones que ocurren antes de que exista la cuenta donde ocurren.

Y no es un sesgo de un producto concreto: 18.76 % en Cuenta Ahorro, 18.66 % en Tarjeta Crédito, 18.58 % en Cuenta Corriente, 18.62 % en Tarjeta Débito, 18.94 % en Préstamo Personal, 18.95 % en Hipotecario, 18.94 % en Inversión, 20.34 % en Seguro. **Uniforme en las ocho.**

### Y aquí está el mecanismo

Cruzando el desfase contra la edad del producto:

| Edad del producto | Transacciones | **% anteriores a su apertura** |
|---|---:|---:|
| Menos de 1 año | 549 501 | **83.31 %** |
| 1–3 años | 1 105 447 | **33.45 %** |
| 3–5 años | 1 110 128 | **0.00 %** |
| Más de 5 años | 1 659 932 | **0.00 %** |

Ese patrón tiene una sola explicación posible.

**Las transacciones se generaron sobre una ventana fija —2023-06-17 a 2026-06-18— y los productos sobre otra, uniforme entre 2018 y 2026. Después se unieron por `product_id` sin comprobar la coherencia temporal.**

Un producto abierto en 2019 recibe transacciones de 2023–2026: todas caen después de su apertura, y el desfase es 0 %. Un producto abierto en 2025 recibe transacciones del mismo pozo: el 83 % cae antes de que existiera.

### Lo que esto explica de golpe

Toda la cadena de hallazgos anteriores es consecuencia de esto:

| Hallazgo | Queda explicado por |
|---|---|
| Ninguna variable predice la mora (F-017, F-021, F-024, F-026) | Las transacciones no pertenecen al producto que las contiene |
| Una tarjeta de 45 meses con 1.29 pagos (F-029) | Se reparten ~13 transacciones por producto de un pozo común |
| No hay calendario de pagos (F-029) | Nunca hubo amortización: hay sorteos con fecha |
| El pago no se relaciona con saldo ni límite (F-029) | Montos uniformes, asignados sin mirar el producto |
| `days_past_due` supera la edad del producto en el 87 % de los nuevos (F-027) | La mora se sorteó sin mirar `opening_date` |
| Kappa 0.0001 entre la mora construida y la columna (F-030) | Dos sorteos independientes |
| El 15 % de productos sin transacciones, igual en los 8 tipos (nuevo) | Descarte uniforme del generador |
| Volumen mensual plano en ~122 000, sin estacionalidad (nuevo) | Ventana fija con tasa constante |
| 13.02 transacciones por producto, sd 3.6, máximo 32 (nuevo) | Reparto acotado, no la cola pesada de la banca real |

### Mi error de método, y queda escrito

Reporté «42 en todos los tramos» como evidencia de ausencia de señal **sin preguntarme por qué 42**. Un número que se repite idéntico a través de estratos independientes **no es un resultado: es una pista**. Y salté a modelos, IV y tamaños del efecto sin haber hecho antes la clasificación de cartera, que es el informe de una línea que habría mostrado la contradicción de inmediato.

### Reglas que deja

1. **Antes de modelar riesgo de crédito, sacar la clasificación de cartera.** Los tramos deben sumar 100 % y el reparto debe ser plausible para un banco. Si dos definiciones de la misma cartera dan 85 % y 6.6 % de clientes al día, no hay nada que modelar hasta resolver eso.
2. **Un número que se repite idéntico entre estratos independientes es una pista, no un hallazgo.** Hay que perseguir su origen aritmético.
3. **Comprobar la coherencia temporal entre tablas relacionadas antes que nada**: ningún hecho puede ser anterior a la existencia de la entidad que lo contiene. Es una consulta de tres líneas.
4. **Las fechas también se contrastan contra la uniforme.** Media, desviación `(máx−mín)/√12`, asimetría 0 y curtosis −1.2. Lo mismo que ya se aplicaba a los montos en F-029.

### Decisión

Esto **cierra la investigación sobre la variable objetivo** y es el hallazgo que encabeza el entregable de ML-03. No es «el modelo no encontró señal»: es **«las dos tablas que habría que cruzar para medir riesgo se generaron por separado, y se demuestra con el 83 % contra 0 % de desfase por edad de producto»**.

Para el jurado, esta tabla vale más que cualquier AUC. Demuestra que el equipo fue al dato, no al modelo.

**Evidencia.** `logs/eval/` — reproducible con dos consultas sobre `data/bronze/products` y `data/bronze/transactions`.

## F-032 · 2026-09-30 · modelos — El pipeline completo contra la mora construida: el `credit_score` tampoco la explica

**Qué.** Cierre del pipeline que pide Eduardo: si la mora del dataset no sirve, **usar la mora construida como variable objetivo** y medir contra ella el baseline y el modelo. La prueba conceptual es clara y correcta: un `credit_score` alto debería ir con menos mora. Si se cumple, hay baseline válido y objetivo real.

**Regla anti-tautología aplicada desde el diseño:** nada derivado de pagos entra como predictor, porque el objetivo se construye con pagos. Solo atributos de producto y cliente.

### Dos objetivos, uno de ellos balanceado

| Objetivo | Definición | Positivos | Tasa |
|---|---|---:|---:|
| **A** · mora 90 construida | saldo > 0 y más de 90 días sin pagar | 99 722 | 80.29 % |
| **B** · cumplimiento bajo | fracción de cuotas pagadas por debajo de la mediana (0.0339) | 61 265 | **49.33 %** |

El B existe para responder por adelantado la objeción de varianza: con 80 % de positivos un modelo puede parecer bueno acertando siempre «sí». **El B está balanceado al 49.33 %.**

### La prueba conceptual de Eduardo: score alto ⇒ menos mora

**Objetivo A**, tasa de mora construida por decil de `credit_score`:

| Decil | Rango de score | n | Tasa de mora |
|---|---|---:|---:|
| 1 | 422–561 | 10 979 | **80.42 %** |
| 5 | 615–631 | 10 611 | 80.00 % |
| 10 | 762–850 | 10 529 | **80.22 %** |

**Spearman ρ = +0.0061, p = 0.9867.** Diferencia entre deciles extremos: **0.20 puntos porcentuales** a lo largo de 428 puntos de score. Y el signo es **positivo**, o sea al revés de lo esperado.

**Objetivo B**, el balanceado:

| Decil | Tasa de cumplimiento bajo |
|---|---:|
| 1 (score más bajo) | **48.67 %** |
| 10 (score más alto) | **49.32 %** |

**Spearman ρ = −0.0973, p = 0.7892.** El decil de mejor score tiene *más* incumplimiento que el peor.

**El `credit_score` no explica la mora construida.** No es un problema de la etiqueta del dataset: no la explica tampoco cuando la etiqueta la construimos nosotros desde el comportamiento de pago observado.

### El modelo con las variables del feature store

| Corrida | Objetivo A | Objetivo B |
|---|---:|---:|
| Baseline · `credit_score` solo | 0.4947 | 0.5019 |
| Modelo · 15 variables | **0.6449** | **0.7892** |
| Solo `antig_producto` | 0.4969 | **0.6844** |
| Modelo · 14 variables, sin `antig_producto` | **0.6481** | 0.6562 |
| Control barajado | 0.4992 | 0.4989 |

Dos artefactos, encontrados aplicando la regla 15 del método —*si el AUC sale alto, quitar el bloque más obvio y remedir*—:

**Primero**, en el objetivo B, `antig_producto` sola da **0.6844**. Es tautología: `cuotas_esperadas` son los meses desde la apertura, o sea el denominador del objetivo. Un producto nuevo llega a cumplimiento alto con un solo pago.

**Segundo**, y más sutil: quitando la antigüedad, el modelo aún da **0.6481** en el objetivo A, y ahí `antig_producto` sola daba 0.4969, así que no era la edad. La tabla por tipo de producto lo explica:

| Tipo de producto | n | Mora construida |
|---|---:|---:|
| Tarjeta Crédito | 94 258 | **86.46 %** |
| Préstamo Personal | 18 780 | 61.30 % |
| Préstamo Hipotecario | 11 157 | 60.21 % |

El generador asignó **1.29 pagos por tarjeta y 5.15 por préstamo** (F-029). Por eso las tarjetas caen en mora construida mucho más. Y `tasa` (AUC univariado 0.6246) y `limite_usd` (0.3949) son **proxies del tipo de producto**: las tarjetas tienen tasas altas y límites pequeños; las hipotecas, al revés.

### El control decisivo

Quitando `product_type`, `tasa` y `limite_usd` —los tres proxies— y dejando solo atributos del cliente:

| Corrida | AUC | IC 95 % | Control barajado |
|---|---:|---|---:|
| Todos los productos de crédito | **0.4989** | [0.4910, 0.5064] | 0.4986 |
| **Tarjeta Crédito** (n = 94 258) | **0.5010** | [0.4917, 0.5111] | 0.5038 |
| **Préstamo Personal** (n = 18 780) | **0.4905** | [0.4756, 0.5074] | 0.5117 |
| **Préstamo Hipotecario** (n = 11 157) | **0.5027** | [0.4812, 0.5238] | 0.5005 |

**De 0.6481 a 0.4989.** Todo el poder predictivo era saber qué tipo de producto es — y el tipo determina cuántos pagos le asignó el generador, no su riesgo. Dentro de cada tipo, el modelo empata con su propio control barajado.

### Qué queda establecido

1. **El pipeline que pide Eduardo está completo y se ejecutó entero**: ingeniería de variables sobre las 13 tablas → feature store de 47 candidatas → selección conceptual por bloques de suscripción → validación estadística con IV, tamaño del efecto y corrección por multiplicidad → construcción de un objetivo propio cuando el del dataset resultó sintético → medición del baseline y del modelo contra ese objetivo → controles de estratificación y de etiqueta barajada.
2. **El resultado es negativo y está probado en todos los niveles.** El `credit_score` no separa ni contra `days_past_due` (ρ = −0.297, p = 0.405) ni contra la mora construida (ρ = +0.0061, p = 0.9867). Y el modelo completo, controlado, empata con el azar.
3. **La causa está identificada** (F-031): productos y transacciones se generaron por separado y se unieron sin coherencia temporal. No hay relación que aprender porque no se construyó ninguna.

### Lo que esto le da al entregable

El baseline de ML-02 **gana sentido**: ya no es «una regresión sobre una variable», es la pieza contra la que se contrasta cada intento, y hay **cinco intentos documentados** que no le ganan — 74 variables de barrido, 26 razonadas, scorecard sobre WoE, nivel producto con seis umbrales, y ahora el objetivo construido.

Un jurado que pregunte «¿probaron con otra definición de mora?» tiene la respuesta con números. Y la pregunta «¿cómo saben que su baseline es válido si no lo compararon contra nada?» —que es exactamente la de Eduardo— queda contestada: se comparó contra todo lo que el dataset admite.

**Evidencia.** `logs/eval/mora_sintetica.json` · reproducible contra `data/bronze/products`, `transactions` y `customers`.

## F-033 · 2026-09-30 · modelos — La búsqueda de modelo completa: 0.5837 que resulta ser una resta

**Qué.** Objeción de Eduardo: *«el modelo nuevo debería ser mejor que el baseline usando más variables; capaz no se han elegido las mejores variables o la combinación correcta»*. La objeción era **correcta en el método**: hasta F-032 se usaba una configuración fija de LightGBM sobre un set fijo de variables. Eso no es buscar un modelo.

Se hizo la búsqueda completa sobre el estrato más limpio y grande —**Tarjeta Crédito, 94 258 productos**— contra la mora construida, con validación cruzada de 5 pliegues, 43 variables candidatas que incluyen las de las otras nueve tablas, ratios e interacciones con sentido de crédito.

### El barrido univariado: nada

| Variable | AUC | \|desviación\| |
|---|---:|---:|
| `de_ses` (sesiones digitales) | 0.5054 | **0.0054** |
| `ot_n_productos` | 0.5031 | 0.0031 |
| `limite_sobre_ingreso` | 0.5027 | 0.0027 |
| `credit_score` | 0.4979 | 0.0021 |

**Cero de 43 variables supera \|AUC − 0.5\| > 0.03.** La desviación máxima es 0.0054.

### Pero combinadas, sí separan

| Modelo | Variables | AUC validación cruzada |
|---|---:|---:|
| **Baseline** · logística sobre `credit_score` | 1 | **0.5020** ± 0.0028 |
| Logística | 43 | 0.5480 ± 0.0075 |
| Random Forest | 43 | 0.5747 ± 0.0044 |
| **LightGBM** (63 hojas, lr 0.03, 800 árboles) | 43 | **0.5760** ± 0.0063 |
| **Selección secuencial hacia delante** | 7 | **0.5837** |
| **CONTROL · etiqueta barajada, mismo pipeline** | 43 | **0.5010** ± 0.0040 |
| CONTROL · las 8 seleccionadas, barajada | 8 | 0.5019 ± 0.0043 |

**Eduardo tenía razón: la combinación importa y no se había buscado.** 0.5837 con el control en 0.5019 no es ruido del procedimiento.

Las variables que elige la selección secuencial, en orden:

| Paso | Variable | AUC acumulado |
|---|---|---:|
| 1 | `tasa_rechazo` | 0.5770 |
| 2 | `gasto_sobre_limite` | 0.5819 |
| 3 | `np_reversiones` | 0.5821 |
| 4 | `app` | 0.5828 |
| 5 | `np_paises` | 0.5835 |
| 6 | `antig_cliente` | 0.5830 |
| 7 | `np_rechazos` | **0.5837** |

### Y aquí está lo que realmente encontró

Todas las variables elegidas son de **actividad no-pago** del producto. El objetivo es «no hay pago en más de 90 días». Aplicando la regla 15 del método —*si el AUC sale alto, quitar el bloque más obvio y remedir*—, se comprobó la relación aritmética.

El total de transacciones por producto es **10.98 con desviación 3.31**, mínimo 1 y máximo 28: un presupuesto acotado repartido al azar entre los seis tipos de transacción. Correlación entre pagos y no-pagos: **r = −0.3591**.

Condicionando al total exacto de transacciones, la relación se vuelve determinista:

| Productos con exactamente 10 transacciones | n | % sin ningún pago |
|---|---:|---:|
| ≤ 6 no-pago | 4 853 | **0.0 %** |
| 7–9 no-pago | 25 387 | **0.0 %** |
| 10–11 no-pago | 10 640 | **100 %** |

| Productos con exactamente 12 transacciones | n | % sin ningún pago |
|---|---:|---:|
| ≤ 11 no-pago | 29 639 | **0.0 %** |
| 12+ no-pago | 7 619 | **100 %** |

**`pagos = total − no_pagos`.** Si un producto tiene 10 transacciones y 10 son de tipo no-pago, tiene cero pagos **por definición aritmética**. Las variables que el modelo eligió —`tasa_rechazo`, `gasto_sobre_limite`, `np_reversiones`, `np_paises`, `np_rechazos`— son todas proxies de *cuántas transacciones no-pago tiene este producto*, que es lo que mecánicamente determina cuántos pagos quedan.

**El 0.5837 no es riesgo de crédito: es el modelo resolviendo una resta.**

### La consecuencia más profunda del proyecto

Esto no es un defecto de la mora construida: es una propiedad del dataset que **cierra la puerta a cualquier objetivo basado en pagos**.

El número total de transacciones por producto está acotado (~11, σ 3.3, máx 28) y se reparte al azar entre seis tipos. Por lo tanto **cualquier variable objetivo derivada de la actividad de pago es el complemento aritmético de la actividad de compra**. No existe forma de construir un indicador de mora en este dataset que no sea, en el fondo, contar compras.

Es la explicación última de por qué nada funciona, y es más fundamental que F-031: aunque las dos tablas se hubieran unido con coherencia temporal, el presupuesto fijo de transacciones seguiría impidiendo que la mora fuera un fenómeno independiente.

### Lo que la objeción de Eduardo dejó

1. **Se hizo la búsqueda de modelo que faltaba**: barrido univariado, cuatro familias de algoritmo, tres configuraciones de hiperparámetros, selección secuencial con validación cruzada, ratios e interacciones. El entregable de ML-03 ya no puede ser acusado de no haber buscado.
2. **Se encontró el único efecto multivariado real del dataset, y se identificó como aritmético.** Un AUC de 0.5837 con control en 0.5019 habría pasado cualquier revisión superficial. Lo que lo destapó fue condicionar al total de transacciones: dos líneas de consulta.
3. **Regla que se añade al método:** cuando un objetivo se construye contando un subconjunto de eventos, comprobar si el total de eventos está acotado. Si lo está, el objetivo es el complemento de lo que no se contó, y cualquier variable de composición lo predice sin saber nada.

**Evidencia.** `logs/eval/busqueda_modelo.json`.

## F-034 · 2026-09-30 · modelos — La elegibilidad tampoco es aprendible: el banco de este dataset asignó productos y límites al azar

**Qué.** Descartado el default (F-027 a F-033), Eduardo redirigió al objetivo correcto del workflow —**Credit-Product Info & Eligibility**— y pidió dos variables: la capacidad de pago, que ya existe, y **una que diga si al cliente se le puede dar otro producto**.

El razonamiento para construirla era sólido y no depende de ninguna etiqueta sintética: **aprender a quién le dio el banco cada producto**. Eso no es una etiqueta inventada por el generador, es la composición observada de la cartera — la decisión que el banco tomó de verdad. Si esa decisión está codificada en los atributos del cliente, se puede reproducir y usar como criterio de elegibilidad.

Se probó. No lo está.

### A · ¿Quién tiene cada producto? No es aprendible

Cohorte de 141 445 clientes. Predictores: **solo atributos del cliente** —score, ingreso en USD, edad, antigüedad, segmento, país, ocupación, educación, estado civil, género, acepta marketing, estado—. Ninguno derivado de productos ni transacciones. LightGBM con validación cruzada de 5 pliegues.

| Objetivo | Tasa | AUC validación cruzada |
|---|---:|---:|
| Tiene Tarjeta Crédito | 46.70 % | **0.5022** ± 0.0030 |
| Tiene Préstamo Personal | 11.68 % | 0.4945 ± 0.0048 |
| Tiene Préstamo Hipotecario | 7.13 % | 0.4996 ± 0.0053 |
| **Tiene 2 o más productos de crédito** | 20.18 % | **0.4973** ± 0.0028 |
| **CONTROL barajado** | 46.70 % | **0.5000** ± 0.0034 |

**La asignación de productos es independiente del perfil del cliente.** Que alguien tenga hipoteca no guarda relación con su ingreso, su score, su edad ni su ocupación. Un banco real concede hipotecas a perfiles muy concretos; aquí se repartieron al azar.

Esto contesta directamente la propuesta de Eduardo de meter el conteo de productos: **`n_productos_credito ≥ 2` da AUC 0.4973**. No se puede aprender quién llega a tener dos productos.

### B · ¿Qué límite asigna el banco? Solo el tipo de producto

Límites medianos por tipo:

| Tipo de producto | n | Límite mediano USD | Media | Desviación |
|---|---:|---:|---:|---:|
| Préstamo Hipotecario | 9 961 | 77 346 | 76 997 | 41 700 |
| Préstamo Personal | 16 759 | 77 376 | 77 159 | 41 768 |
| Tarjeta Crédito | 84 420 | 25 536 | 25 512 | 14 136 |

Regresión sobre `log(límite)` con atributos del cliente más el tipo de producto:

| Modelo | R² |
|---|---:|
| Atributos del cliente **+ tipo de producto** | **0.2441** |
| **Solo el tipo de producto** | **0.2620** |
| Baseline (predecir la media) | −0.0000 |
| Control con el límite barajado | −0.0195 |

**El modelo completo (0.2441) es peor que usar solo el tipo de producto (0.2620).** Los atributos del cliente no aportan nada al límite: solo añaden ruido. Todo lo explicado es «las hipotecas y los préstamos personales tienen límites de ~77 000 USD y las tarjetas de ~25 500».

### C · La tabla que lo cierra

Límite mediano de tarjeta de crédito, en USD, por quintil de score cruzado con quintil de ingreso:

| Score ↓ / Ingreso → | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---:|---:|---:|---:|---:|
| **Q1** (peor score) | 24 533 | 25 751 | 26 229 | 25 913 | 12 501 |
| Q2 | 26 157 | 25 281 | 25 764 | 25 447 | 27 187 |
| Q3 | 26 120 | 24 881 | 25 238 | 26 245 | 25 038 |
| Q4 | 24 530 | 26 531 | 25 575 | 25 797 | 25 012 |
| **Q5** (mejor score) | 25 967 | 28 275 | 23 696 | 25 077 | **25 546** |

**Plana en las dos dimensiones.** El cliente del peor score y el menor ingreso recibe 24 533 USD de línea; el del mejor score y mayor ingreso, 25 546. Diferencia del 4 %. En cualquier banco real esta tabla crece monótonamente en ambos ejes y el rango entre esquinas es de un orden de magnitud.

**El límite se sorteó de una distribución por tipo de producto, sin mirar al cliente.**

### Qué significa, y es la conclusión del proyecto

No hay decisión de suscripción codificada en este dataset. Ni quién recibe qué producto, ni con qué línea. Por lo tanto **la elegibilidad no puede aprenderse: tiene que decidirse**.

Y eso es exactamente lo que el proyecto definió el primer día: `eligibility_v1.yaml`, una política versionada y auditable sobre hechos verificables, testeable sin LLM y sin modelo. **Lo que era una decisión de diseño ahora es un resultado demostrado.** No se eligió una política porque fuera más elegante que un modelo: se demuestra que un modelo no es posible.

### Las dos variables que pide Eduardo, resueltas

**1 · Capacidad de pago** — existe, es `ML-04`. Estimador sobre flujo transaccional con techo duro y puerta de abstención. Se reporta como estimador sobre datos sintéticos (F-029) y se abstiene en el 94 % de los casos, que pasa a ser el comportamiento esperado.

**2 · ¿Se le puede dar otro producto?** — **no es un modelo, es una regla.** Y todos sus insumos son hechos observables y verificables:

| Criterio | Insumo | Tipo |
|---|---|---|
| Exposición total sobre ingreso | `limite_usd` sumado / `ingreso_usd × 12` | hecho, 94.9 % y 80.2 % de cobertura |
| Número de productos de crédito vigentes | `n_productos_credito` | hecho, 100 % |
| Capacidad de pago estimada | `predict_capacity` o abstención | estimador declarado |
| Antigüedad de la relación | `antig_cliente` | hecho, 100 % |
| Cuotas registradas frente a esperadas | `cumplimiento` con supuesto mensual | hecho con supuesto declarado (F-030) |
| Condiciones vigentes | `tasa_interes_media`, `antiguedad_producto_dias` | hecho, 90 % y 100 % |

La política fija los umbrales —cuántos productos como máximo, qué carga sobre ingreso se admite, qué cuota sostenible se exige— y esos umbrales son **decisión de negocio escrita en YAML, versionada y revisable**, no un coeficiente aprendido de un dataset que no contiene la decisión.

**El conteo de productos de Eduardo sí entra**, pero como **tope de política** («no más de N productos de crédito», «carga total no mayor a X veces el ingreso anual»), no como variable predictora — porque no predice nada.

### Regla que deja

Antes de construir un modelo de elegibilidad, comprobar que **la decisión histórica esté codificada en los datos**. Si el perfil del cliente no explica qué producto tiene ni con qué límite, no hay política que aprender: hay una política que escribir. Se comprueba con dos consultas —AUC de «tiene el producto» contra atributos del cliente, y tabla cruzada de límite por score × ingreso— y ambas caben en una tarde.

**Evidencia.** `logs/eval/elegibilidad.json`.

## F-035 · 2026-09-30 · datos — Silver traduce `transaction_type` al español y deja el estado en inglés: un filtro con los valores de bronze devuelve cero filas en silencio

**Qué.** Al construir el bloque de cuotas sobre `noema_silver.transactions_with_fx` el filtro `transaction_type = 'Payment'` devolvió **cero filas**, sobre una tabla de 4 425 008. No hubo error, no hubo aviso: el `LEFT JOIN` rellenó con nulos y el `coalesce` los convirtió en ceros. El resultado parecía plausible —«los clientes no pagan», que es coherente con F-029— y solo se destapó al mirar la distribución: **mediana de cuotas pagadas exactamente 0 y `pagado_usd` exactamente 0** para todos los clientes con producto de crédito.

**La causa.** La capa silver **traduce** los niveles de `transaction_type` y **no** los de `transaction_status`:

| Columna | Bronze | Silver |
|---|---|---|
| `transaction_type` | Purchase · Withdrawal · Transfer · **Payment** · Deposit · Adjustment | Compra · Retiro · Transferencia · **Pago** · Depósito · Ajuste |
| `transaction_status` | Approved · Declined · Pending · Reversed | **iguales** |

Los conteos coinciden uno a uno —Compra 1 083 406 contra Purchase 1 083 406, Pago 738 964 contra Payment 738 964—, así que **F-016 sigue siendo correcto**: la normalización no colapsa ningún nivel. Pero sí renombra, y eso F-016 no lo decía.

**Por qué es peligroso.** Un filtro por un valor que no existe no falla: devuelve el conjunto vacío. Combinado con `LEFT JOIN` más `coalesce(..., 0)` —que es la forma correcta de tratar la ausencia de pagos— produce una tabla de ceros indistinguible de un hallazgo real. Y en este proyecto **había un hallazgo real muy parecido** (F-029: el 29 % de los productos no registra ningún pago), lo que hacía el error aún más creíble.

**Cómo se detectó.** Mirando la mediana. Que `cuotas_pagadas` y `pagado_usd` fueran **exactamente** 0 y no «casi 0» es la firma de un filtro vacío, no de un comportamiento. Un fenómeno real deja cola; un conjunto vacío no.

Con los valores correctos: media 3.31 pagos, mediana 2, cumplimiento mediano 3.81 %, y **20.86 %** de clientes con producto de crédito sin ningún pago — coherente con F-029 a nivel producto.

**Corrección.** `TIPO_PAGO = "Pago"` y `ESTADO_APROBADO = "Approved"` como constantes en `ml/features/build_features.py`, con el comentario que explica la asimetría. El `tx` CTE ya usaba los valores en español y por eso funcionaba; el bloque nuevo se escribió mirando bronze.

**Regla que deja.** Al filtrar una capa derivada por un valor de enum, **comprobar que ese valor existe en esa capa**, no en la de origen. Una consulta de una línea —`select distinct <columna>`— antes de escribir el filtro. Y ante un agregado que sale **exactamente** cero, sospechar del filtro antes de creerse el hallazgo: los ceros redondos son de código, no de negocio.

**Evidencia.** `select transaction_type, count(*) from noema_silver.transactions_with_fx group by 1` contra la misma consulta sobre `data/bronze/transactions`.

## F-036 · 2026-09-30 · datos — `customer_360` valora con una cotización cinco meses posterior al corte, y no convierte el ingreso

**Qué.** Dos defectos en la capa gold de Federico, encontrados al revisar si el cierre de la deuda de ML-01 rompía algo de su lado. No rompía nada, pero destapó esto. Quedan documentados en `docs/12_cambios_para_federico.md` §8 y **no se tocan**: son de su frontera.

### 1 · El ingreso viaja en moneda local

`customer_360` convierte el saldo y no el ingreso:

| País | `estimated_monthly_income` mediano | `total_balance_usd` mediano |
|---|---:|---:|
| Colombia | **9 192 466** | 7 562 |
| Argentina | **801 955** | 7 727 |
| México | **39 220** | 7 717 |

El saldo está bien —las tres medianas son del mismo orden, que es el control—. El ingreso no: un cliente colombiano parece **234 veces más rico** que uno mexicano por la unidad de cuenta. Es el mismo defecto que F-025 en el feature store, en otra capa.

La causa es la misma: `stg_customers` **no trae columna de moneda**, solo `country`, así que hay que derivarla. En `ml/features/build_features.py` se resolvió con `MONEDA_POR_PAIS` y una CTE de tasas.

**Dónde debería vivir la conversión.** En silver, no en el feature store. Si la capa de datos expusiera `estimated_monthly_income_usd`, ni ML-01 ni la política tendrían que convertir por su cuenta, y no habría dos implementaciones del mismo mapa país → moneda que puedan divergir. Se propone así en el aviso.

### 2 · La fecha de valuación es posterior al corte

```sql
select distinct valuation_date from noema_gold.customer_360;
-- 2026-06-17
```

Sale de `select max(date) from stg_daily_exchange_rates`, y esa tabla llega hasta **2026-06-17**. El corte del proyecto es **2025-12-31**: son **cinco meses y medio de cotización futura** usados para valorar saldos del corte.

**ADR-0005 lo prohíbe explícitamente:** «FX usa fecha de operación; nunca una cotización futura».

Es fuga de información de la clase sutil: no introduce una columna prohibida —`test_feature_contract.py` no la detecta— sino una **fecha**. El contrato temporal del proyecto vigila qué columnas entran y desde cuándo se observan los hechos, pero no vigila con qué fecha se valora un importe.

`transactions_with_fx` sí lo hace bien: usa la fecha de la operación. El patrón correcto ya está en la misma capa, solo que `customer_360` no lo sigue.

### Por qué importa más de lo que parece

Las dos afectan a decisiones que el agente va a pronunciar. La política de elegibilidad compara ingreso contra carga y contra exposición; con el ingreso en moneda local, **todo umbral sobre ingreso está mal entre países**. Y valorar con una cotización futura convierte una cifra que el cliente ve en una que no se podía conocer al corte.

### Regla que deja

El contrato temporal debe cubrir **dos** cosas, no una:

1. **Cuándo se observó el hecho** — ya está: doble filtro de fecha de evento y de proceso, y la prueba de columnas prohibidas.
2. **Con qué fecha se valoró el importe** — no estaba. Una conversión de moneda es una observación más, y su fecha tiene que respetar el corte igual que la del hecho.

Conviene añadir a `tests/data/test_feature_contract.py` una prueba de que ninguna fecha de valuación de gold supere el corte. Queda como tarea sobre el contrato de datos.

**Evidencia.** `select distinct valuation_date from noema_gold.customer_360` y la tabla de medianas de ingreso por país, ambas reproducibles contra `data/noema.duckdb`.

## Interés comercial y cupos — auditoría de implementación (2026-09-30)

La solicitud nueva requiere separar interés, cupo observado y oferta de política.
Consulta reproducible: `select had_conversion, count(*) from
noema_silver.stg_campaign_sends group by 1` devuelve 1 737 002 negativos y
9 799 positivos. Hay 436 429 registros con `process_date < send_date`
(`select count(*) ... where process_date < send_date`). Se excluyen del modelo.
La conversión de campaña es un proxy de respuesta comercial, no una etiqueta de
«quiere un producto nuevo», ni prueba de primera adquisición. El snapshot no
versiona resultados: la validación retrospectiva asume que las etiquetas estaban
completas al finalizar 30 días; esto impide promover el modelo a producción.
Los límites existentes vienen de `products.credit_limit`, por producto y moneda;
no son una asignación nueva. `products.last_updated` contiene fechas hasta 2027:
no se debe presentar su snapshot como estado histórico al corte sin filtrar.

## Documentos aportados y red profunda (ML-12, 2026-09-30)

Se revisaron el HTML «Política de Elegibilidad» (v1.0, 30-sep) y las 20 páginas
de «Bronze contra Silver» (29-sep; exportado 30-sep). El reporte de auditoría
respalda excluir mora, referencias de sucursal inválidas, FX reportado y nulos
estructurales de entradas ingenuas. No demuestra que cualquier objetivo sea
imposible: la respuesta a campaña es una etiqueta distinta del incumplimiento.
La red MLP de tres capas se entrena sobre esa respuesta, no sobre mora.

Diferencia verificada con el código actual: el HTML afirma abstención ante límite
faltante, mientras `Politica._carga` omite productos sin límite/tasa y emite aviso.
El nuevo adaptador `policy_analysis` exige términos completos antes de invocar
ese motor. No altera el código de Eduardo. El HTML también precede el soporte
actual de saldo dispuesto, estrés de línea no dispuesta y reservas: manda el YAML
versionado al ejecutar, no los números ilustrativos del HTML.

Precaución estadística: no rechazar una hipótesis no prueba independencia ni MCAR;
KS 0.00203 no es «una centésima» del umbral 0.01. La conservación de distribuciones
no demuestra ausencia de fuga en todas las tablas gold. Se conservan las advertencias
posteriores de Eduardo sobre FX y snapshots. Los documentos se incorporan como
contratos y límites de evidencia, no como filas sintéticas para entrenar la red.
