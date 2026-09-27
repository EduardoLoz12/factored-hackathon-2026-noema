# 09 · Limpieza, ETL y capacidad de pago — especificación

**Dueño: Federico Vargas.** Junto con `docs/07_scm_spec.md`, este documento es tu tarea completa. Son 15 ítems del checklist: `DAT-03` a `DAT-14` y `ML-04`.

---

## 1. En una frase

Convertir 23 millones de filas crudas en cuatro tablas de negocio en las que el agente pueda confiar — y estimar cuánto puede pagar realmente cada cliente al mes.

## 2. Por qué existe

Todo lo demás del sistema descansa aquí. El agente responde **solo con cifras traídas de la base**: si la base está sucia, el agente miente con confianza. El modelo de riesgo se entrena sobre tus tablas: si se cuela una columna que refleja el desenlace, el modelo "adivina el futuro", las métricas salen espectaculares y falsas, y el jurado lo detecta en dos minutos — la prevención de fuga es criterio explícito del rubro.

Además, la calidad de datos **es entregable en sí misma**: uno de los cuatro pilares evaluados es Data Analytics, y nuestra carta fuerte ahí es que el diccionario oficial no coincide con el dato. Tú produces esa evidencia.

## 3. De dónde partes

**Bronze ya existe.** No tienes que descargar nada:

```bash
make ingest    # solo si data/bronze/ está vacío; toma ~4 minutos
```

Son 7 671 archivos Parquet, **23 495 188 filas**, 1.5 GB, con `manifest.json` que guarda el checksum de cada archivo. Bronze es el dato **tal como llegó**: todo string, sin normalizar, más dos columnas de linaje (`_source_file`, `_ingested_at`).

**Lee `docs/01_data_audit.md` antes de escribir una línea.** Ahí está medido —no supuesto— qué tiene el dato realmente.

## 4. Lo que ya sabemos que está mal

Esto no es teoría; está medido sobre las tablas completas.

| Problema | Magnitud | Qué tiene que hacer silver |
|---|---|---|
| Enums en idioma mixto | `product_type` en español (`Cuenta Ahorro`, `Tarjeta Crédito`), `transaction_type` en inglés (`Withdrawal`) | Normalizar por tabla, no con un mapa global |
| `MXN` no existe | 0 productos en pesos mexicanos, con 74 907 clientes mexicanos | Reportarlo; convertir con las monedas que sí están |
| Conteos que no cuadran | 23 495 188 filas reales vs ~19 M documentados; difieren las 8 tablas de hechos | No usar ningún número del diccionario como verdad |
| Nulos estructurales | `credit_limit` y `days_past_due` 68.7 % — solo aplican a productos de crédito | Nulo estructural ≠ nulo faltante: se tratan distinto |
| Ingreso ausente | `estimated_monthly_income` nulo en 20 % | **Por eso `ML-04` estima del flujo transaccional** |
| Teléfono de otro país | 48.4 % de los clientes | Reportar, no corregir. Nunca usarlo para verificar identidad |
| Llegadas tardías | 25.5 % de transacciones con `transaction_date` fuera de su partición | `process_date` gobierna la partición; `transaction_date` gobierna el orden temporal |
| Columna redundante | `contact_reason` es idéntica a `reason_category` | Descartarla |
| Duplicados prometidos que no aparecen | 0 en productos, clientes y particiones muestreadas, pese al «~2 %» documentado | **Verificar a escala y reportar el resultado, sea cual sea** |
| `credit_score` | Rango real 422-850, documentado 300-850 | Contrato contra el rango observado |

## 5. Tus entregables

### 5.1 Contratos de calidad — `DAT-03`, `DAT-04`, `DAT-05`

`data_platform/contracts/schemas.py` — un esquema pandera por tabla: tipos, obligatoriedad, rangos y valores permitidos, escritos **contra el dato observado**.

`data_platform/contracts/audit.py` — corre sobre las 13 tablas completas y produce un reporte con: filas por tabla contra lo documentado, tasa de nulos por columna distinguiendo estructural de faltante, **duplicados reales por llave primaria**, huérfanos de llave foránea, y las inconsistencias entre campos (teléfono contra país, moneda contra país).

`data_platform/contracts/quarantine.py` — las filas que violan el contrato **no se borran**: van a `data/quarantine/<tabla>/` con la razón del rechazo. Perder una fila en silencio es peor que tener una fila mala marcada.

El reporte alimenta `DAT-12` y termina publicado en `/analytics`.

### 5.2 dbt y la capa silver — `DAT-06`, `DAT-07`, `DAT-08`

Proyecto dbt con perfil **duckdb** por defecto. Silver normaliza: enums al español, monedas a USD usando `daily_exchange_rates`, tipos correctos, huérfanos fuera, columnas redundantes descartadas. Bronze no se toca nunca.

### 5.3 La capa gold — `DAT-09` a `DAT-12`

Cuatro tablas. Estas columnas son un contrato: el agente y los modelos las consumen por nombre.

**`customer_360`** — una fila por cliente: identidad y contacto, país, segmento, `credit_score`, productos que tiene, saldo total en USD, antigüedad, y su estado de mora actual.

**`credit_features_asof`** — una fila por `(customer_id, asof_date)`, con las variables de comportamiento. **Lee el apartado 6 antes de tocarla.**

**`product_policy`** — condiciones por tipo de producto: puntaje mínimo, monto mínimo y máximo, plazos, tasa. El motor de reglas la consulta.

**`dq_report`** — el reporte de calidad en forma de tabla, listo para pintarse.

### 5.4 Databricks y serving — `DAT-13`, `DAT-14`

Subir los Parquet de bronze a un Unity Catalog Volume y correr los mismos modelos dbt con perfil `databricks` para materializar Delta. Después, exportar gold a Postgres, que es de donde lee la API.

Databricks Free Edition **no puede leer el S3 de Factored** (es serverless y restringe la salida a internet); por eso la ingesta va local y Databricks recibe los archivos ya convertidos. Está en `ADR-0002`.

### 5.5 Capacidad de pago — `ML-04`

`ml/training/capacity.py`: estima la **cuota mensual máxima sostenible** de un cliente.

No uses `estimated_monthly_income`: falta en 20 % de los casos y es declarado, no observado. Constrúyela del flujo real de `transactions` — entradas recurrentes menos salidas comprometidas, en una ventana anterior a la fecha de corte. Devuelve la cuota en la moneda del cliente y expón el resultado por `ml/serving/predictor.py`, que ya tiene la firma acordada.

**Aplica la misma regla de corte temporal del apartado 6.** Esto no es un reporte: es una entrada a una decisión de crédito.

## 6. La regla de fuga de información — léela dos veces

`credit_features_asof` tiene una fecha de corte declarada: **2025-12-31**. Todas las variables se construyen **únicamente** con información anterior a esa fecha. La evaluación ocurre entre 2026-01-01 y 2026-06-17.

**Columnas prohibidas**, y la razón de cada una:

| Columna | Por qué no puede entrar |
|---|---|
| `current_balance` | Refleja el estado **posterior** al incumplimiento |
| `last_transaction_date` | Un cliente en mora deja de transar: la fecha codifica el desenlace |
| `product_status` (`Blocked`, `Suspended`) | Es **consecuencia** de la mora, no causa |
| `days_past_due` | Es la etiqueta. Nunca entra como variable |
| Cualquier agregado de `transactions` posterior al corte | Mira el futuro |

Si una de estas entra, el modelo predice con una precisión irreal y el trabajo entero pierde credibilidad. Hay una prueba que lo verifica mecánicamente:

```bash
pytest tests/data/test_feature_contract.py -v
```

Se salta sola mientras la tabla no exista. En cuanto exista, **falla si aparece cualquier columna prohibida**. No la desactives: si crees que una de esas columnas debería entrar, dilo y lo discutimos — puede que tengas razón, pero tiene que quedar escrito en un ADR.

## 7. Cómo sabes que terminaste

```bash
make audit                                  # reporte de calidad sobre las 13 tablas
make build                                  # dbt: bronze -> silver -> gold, tests en verde
pytest tests/data/ -v                       # contratos y guardarraíl de fuga
make checklist                              # tus ítems pasan a terminado solos
```

## 8. Fechas

| Día | Qué debe existir |
|---|---|
| **D2 · 28-sep** | `DAT-03` a `DAT-07`: contratos, reporte de calidad, cuarentena, dbt configurado, silver de productos y clientes |
| **D3 · 29-sep** | `DAT-08` a `DAT-13`: silver de transacciones con FX, las cuatro tablas gold, subida a Databricks |
| **D4 · 30-sep** | `ML-04`: capacidad de pago entrenada y expuesta por `predictor.py` |
| **D5 · 1-oct** | `DAT-14`: export de gold a Postgres |

**`credit_features_asof` es lo que más urge.** El modelo de riesgo se entrena sobre esa tabla el día 4. Si el día 3 no está, avísalo el día 3, no el día 4.

## 9. Cómo trabajar

```bash
git pull
git checkout -b trabajo/etl-<lo-que-hagas>
# ... trabajas ...
make audit && make build && pytest tests/data/
python -m scripts.worklog "en qué trabajaste"
make checklist
git commit -m "Nuevo (DAT-07): la capa silver normaliza los tipos de producto"
git push -u origin trabajo/etl-<lo-que-hagas>
```

PR contra `main`. Mensajes de commit en español y sin jerga. **No hagas push directo a `main`.**

Si algo del contrato no te cierra —una columna gold que crees que falta, una regla de limpieza que no aplica— **dilo antes de implementarlo**. Cambiarlo el día 4 cuesta mucho más que discutirlo el día 2.
