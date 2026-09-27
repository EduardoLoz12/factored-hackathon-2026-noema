# ADR-0002 · Ruta de datos: ingesta local, curación en DuckDB, lakehouse en Databricks

**Fecha:** 2026-09-27 · **Estado:** aceptado (pendiente confirmar el spike empírico)

## Contexto

El dataset vive en un bucket S3 **de Factored**, con credenciales read-only repartidas en un PDF a ~800 participantes. Queríamos usar Databricks —lo sugiere el propio kickoff y era la preferencia del equipo—, así que la ruta natural era leer el S3 directamente desde un notebook.

Al revisar las limitaciones de **Databricks Free Edition** encontramos que es **serverless-only**, sin acceso a consola de cuenta ni APIs de nivel cuenta, y con **salida a internet restringida a un conjunto de dominios de confianza**. No hay instance profile ni credencial de almacenamiento propia para registrar un bucket de terceros como *external location*. Es decir: no debemos asumir que Databricks puede leer ese S3.

Dato adicional de la auditoría: el volumen total es **5.35 GB en 7 671 archivos**. Eso cabe holgadamente en una laptop.

## Decisión

Cuatro capas, con una frontera explícita en cada una:

1. **Ingesta local** (`data_platform/ingestion/`) — boto3 lee el S3, escribe Parquet particionado y genera `manifest.json` con checksum SHA-256 por archivo. Es la **única pieza del sistema que toca las credenciales de Factored**.
2. **Curación canónica en DuckDB + dbt** — bronze → silver → gold. Esto es lo que un juez reproduce con un comando, sin cuenta de nadie.
3. **Espejo en Databricks** — los Parquet de bronze se suben a un Unity Catalog Volume y los mismos modelos dbt corren con perfil `databricks` para materializar Delta. Ahí viven el entrenamiento y **MLflow** (tracking, registry, model cards).
4. **Serving en Postgres** — la API **no** consulta Databricks. Lee de Postgres/Supabase, alimentado por un export de las tablas gold.

**Spike del D1, timeboxed a 90 minutos:** intentar la lectura directa del S3 desde un notebook de Free Edition. Si funciona, el paso 3 se simplifica y se documenta. El resultado se anota aquí en cualquier caso.

## Alternativas consideradas

- **Todo en Databricks.** Rechazada por el riesgo de red y de cuotas: un demo que se cae por cuota el día de la premiación es una derrota autoinfligida.
- **Todo en DuckDB, sin Databricks.** Técnicamente suficiente y más simple, pero renuncia a demostrar el pilar de ingeniería de datos con una herramienta que el propio jurado sugirió.
- **Snowflake trial.** El trial de 30 días puede vencer antes del 16 de octubre, día en que los finalistas defienden en vivo.

## Consecuencias

- **Reproducibilidad como ventaja:** cualquiera corre `make ingest && make build` y obtiene exactamente nuestras tablas, con checksums para probarlo.
- **La ruta crítica del demo no depende de una plataforma gratuita con cuotas.**
- Costo: mantener dos perfiles de dbt (duckdb y databricks). Se acepta porque el SQL es casi idéntico y el beneficio de reproducibilidad es mayor.
- El manifest con checksums permite detectar si Factored cambia el dataset a mitad del hackathon.
