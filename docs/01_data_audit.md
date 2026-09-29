# 01 · Auditoría del dataset

**Fecha:** 26–27 de septiembre de 2026 · **Fuente:** bucket S3 read-only de Factored · **Método:** listado completo por API y muestreo dirigido; las tablas de dimensión se leyeron enteras.

Esta auditoría se hizo **antes de diseñar nada**. Tres de sus hallazgos cambiaron el diseño del sistema.

---

## 1. Inventario real

| Concepto | Valor |
|---|---|
| Objetos bajo `data/` | **7 671** archivos CSV |
| Tamaño | **5.35 GB** |
| Tablas | 13 — 6 dimensiones planas + 7 hechos particionados |
| Particionado | `year=/month=/day=`, 1 097 días consecutivos (2023-06-17 → 2026-06-17) |
| Filas ingeridas | **23 495 188** (el diccionario declara ~19 000 000) |
| Extra | `data_backup_20260831/`, copia paralela sin `call_transcripts` ni `satisfaction_surveys` |

### Conteo real por tabla contra el declarado

Ingesta completa: 7 671 archivos, **0 fallos**, 5.35 GB CSV → 1.50 GB Parquet en poco más de 4 minutos.

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
| `customers` · `products` · `branches` · `service_agents` · `marketing_campaigns` | exacto | exacto | 0 % |

Las cinco dimensiones coinciden al dígito; **todas** las tablas de hechos difieren. Seis de ellas caen entre −11 % y −16 %, un patrón demasiado regular para ser azar: sugiere que las cifras del diccionario son objetivos de generación y no conteos medidos. **Ningún conteo del diccionario se usa como verdad en este proyecto.**

Peso por tabla: `digital_events` 3.76 GB · `transactions` 0.81 GB · `campaign_sends` 0.33 GB · `products` 68 MB · `customers` 47 MB · `call_center_interactions` y `call_transcripts` 0.14 GB cada una · el resto, marginal.

**Consecuencia de diseño:** 5.35 GB caben en una laptop. No hace falta un clúster para curar estos datos, y eso permite que el jurado reproduzca la curación con un comando. Ver [ADR-0002](decisions/ADR-0002-ruta-de-datos.md).

---

## 2. El diccionario oficial y el dato no coinciden

La **estructura** documentada sí se cumple: las 13 tablas existen, con sus columnas y sus llaves foráneas. Lo que no se cumple es el contenido.

| Campo | Dice el diccionario | Dice el dato | Decisión |
|---|---|---|---|
| `products.product_type` | `Checking Account`, `Credit Card`, `Personal Loan`… (inglés) | `Cuenta Ahorro` 120 203 · `Tarjeta Crédito` 100 102 · `Cuenta Corriente` 99 979 · `Tarjeta Débito` 39 938 · `Préstamo Personal` 19 960 · `Préstamo Hipotecario` 11 910 · `Inversión` 5 859 · `Seguro` 2 049 | Los 8 niveles están **solo en español**; no hay mezcla que normalizar. El `CASE` de silver no colapsa ningún nivel (F-016) |
| `currency` | MXN, COP, ARS, USD | **MXN no existe**: USD 220 501 · COP 107 975 · ARS 71 524 — con 74 907 clientes mexicanos | Se reporta; conversión vía `daily_exchange_rates` |
| `transaction_type` | inglés | inglés (`Withdrawal`, `Payment`, `Purchase`) — **idioma mixto entre tablas** | Normalización por tabla, no global |
| `customers.credit_score` | 300 – 850 | **422 – 850** | El contrato usa el rango observado |
| Duplicados | «~2 % en todas las tablas» | **0** en `products` (400 000), `customers` (150 000) y en las particiones diarias muestreadas de transactions, digital_events y call_center_interactions | Verificar a escala en `make audit` y reportar la discrepancia |
| Nulos | «~5 % en campos opcionales» | Estructurados y muy distintos (tabla abajo) | Nulo estructural ≠ nulo faltante |
| `call_center_interactions.contact_reason` | «motivo principal, distinto de la categoría» | **Idéntica** a `reason_category`, mismos 6 valores | Columna redundante: se descarta |
| Evolución de esquema | «los esquemas pueden cambiar» | Sin cambios entre 2023 y 2026 en las tablas revisadas | Contratos igual, por si aparece |

### Nulos reales en `products` (400 000 filas)

| Columna | Nulos | Naturaleza |
|---|---|---|
| `credit_limit` | 68.7 % | **Estructural** — solo aplica a productos de crédito |
| `days_past_due` | 68.7 % | **Estructural** — idem |
| `expiration_date` | 66.7 % | **Estructural** — solo productos con vencimiento |
| `last_transaction_date` | 23.6 % | Faltante real |
| `interest_rate` | 10.0 % | Faltante real |

### Nulos reales en `customers` (150 000 filas)

`detected_accent` 29.9 % · `estimated_monthly_income` 20.0 % · `credit_score` 15.0 % · `education_level` 12.0 % · `occupation` 10.0 % · `postal_code` 10.0 % · `mobile_phone` 3.1 % · `email` 2.0 % · `gender` 0.0 %.

**Consecuencia de diseño:** el ingreso mensual estimado falta en uno de cada cinco clientes. Por eso la **capacidad de pago se estima del flujo transaccional**, no del ingreso declarado.

---

## 3. Los transcripts no sirven como corpus

Muestra de **794 transcripciones** tomadas de cuatro días distintos repartidos en tres años (2023-08-14, 2024-03-05, 2025-09-22, 2026-06-10):

- **2 plantillas de texto únicas** en toda la muestra, 397 apariciones cada una.
- `detected_intents`: 94 % `consulta_general`, el resto vacío.
- `detected_language`: **`es` en el 100 %**. Cero portugués en todo el dataset.
- `detected_keywords`: la misma bolsa de tres palabras (`cuenta`, `banco`, `servicio`) permutada.
- El texto trae **los valores sin rellenar**:

```
Cliente: Buenas tardes, necesito consultar el saldo de mi tarjeta de crédito.
Agente: ... Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}.
```

Ocurrencias de placeholders en la muestra: `{moneda}` 1 191 · `{monto}` 794 · `{limite}` 397.

**Consecuencia de diseño — y es la más importante del proyecto.** Un corpus con dos plantillas y un intent no sirve para modelado de tópicos, clasificación de intención ni RAG. Pero un **hueco con nombre es una pregunta cuya respuesta está en una tabla**. Rellenamos esas plantillas desde las tablas gold y obtenemos conversaciones **con respuesta correcta conocida**: medición exacta de alucinación, etiquetas defendibles, y el set en portugués por traducción. Ver [ADR-0003](decisions/ADR-0003-ground-truth-desde-plantillas.md).

---

## 4. Sí existen etiquetas de riesgo

`products.days_past_due` — 125 350 valores no nulos (los productos de crédito):

| Días de mora | Productos |
|---|---|
| 0 | 106 585 |
| 1 – 29 | 3 114 |
| 30 – 59 | 3 117 |
| 60 – 89 | 3 112 |
| 90 o más | 9 422 |

Máximo observado: 180 días. **≈15 % de casos positivos** con el corte en 30 días — un balance de clases sano para entrenar sin remuestreo agresivo.

**Advertencia registrada:** es una **fotografía**, no una serie de tiempo. El dataset no dice en qué fecha se midió la mora, y `last_updated` por producto va de 2019 a 2026. El corte temporal para las variables es por tanto un **supuesto declarado**, no un hecho observado. Ver [ADR-0004](decisions/ADR-0004-corte-temporal-y-fuga.md).

---

## 5. Inconsistencias entre campos

- **48.4 % de los clientes** tiene un prefijo telefónico que no corresponde a su país de residencia (72 548 de 150 000). Ejemplo real: cliente con DNI, teléfono `+54…`, ciudad Guadalajara, estado Jalisco, país México, acento detectado `mexican`.
- **25.5 % de las transacciones** de un día tienen `transaction_date` fuera de su partición `process_date` — llegadas tardías confirmadas.
- `document_number` es único en las 150 000 filas → sirve como llave de verificación de identidad.

**Consecuencia de diseño:** el teléfono **no** se usa como factor de verificación de identidad. La puerta usa `document_type` + `document_number` + `date_of_birth`. Y en la ingesta, `process_date` gobierna la partición mientras `transaction_date` gobierna el comportamiento.

---

## 6. Qué reproduce estos números

```bash
make ingest    # descarga y convierte, con manifest y checksums
make audit     # regenera los conteos de esta página
```

El manifest (`data/bronze/manifest.json`) guarda por archivo: key de S3, etag, checksum SHA-256 del contenido descargado, filas y columnas. Cualquiera puede verificar que auditamos exactamente lo que dice este documento.
