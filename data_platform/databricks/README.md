# Espejo de datos y artefactos en Databricks

Este repo ya tiene una ruta de subida a un **Unity Catalog Volume**. La subida no
crea el workspace ni el Volume: esos recursos deben existir antes.

## 1. Preparar credenciales

Instalar dependencias cloud:

```bash
uv pip install --python .venv/bin/python -e ".[cloud]"
```

Configurar variables de entorno. No guardar estos valores en Git.

```bash
export DATABRICKS_HOST="https://<workspace>.cloud.databricks.com"
export DATABRICKS_TOKEN="<token>"
export DATABRICKS_HTTP_PATH="<sql-warehouse-http-path>"
export DATABRICKS_CATALOG="noema"
export DATABRICKS_SCHEMA="bronze"
export NOEMA_VOLUME="/Volumes/noema/bronze/raw"
```

`NOEMA_VOLUME` debe tener esta forma exacta:

```text
/Volumes/catalog/schema/volume
```

El Volume debe estar vacío para esa carga. El uploader usa `overwrite=False`.

## 2. Elegir bundle

El script `data_platform.databricks.upload_to_volume` tiene dos bundles:

| Bundle | Qué sube | Uso |
|---|---|---|
| `databricks-inputs` | `data/bronze`, `data/validated`, `data/quality` | Mínimo para reconstruir silver/gold con dbt en Databricks |
| `complete` | Lo anterior + `data/gold`, `data/quarantine`, `data/quarantine_references`, `data/models`, `data/prototype/*.sqlite`, `logs/build` | Respaldo completo local con datos procesados, modelos y evidencia |

Los modelos `.joblib` son artefactos locales de confianza. No cargarlos desde una
fuente desconocida: `joblib` puede ejecutar código al deserializar.

## 3. Dry-run con plan y checksums

Plan mínimo para Databricks:

```bash
.venv/bin/python -m data_platform.databricks.upload_to_volume \
  --volume "$NOEMA_VOLUME" \
  --bundle databricks-inputs \
  --plan-file logs/build/databricks_upload_plan_inputs.json
```

Plan completo con gold, modelos y logs:

```bash
.venv/bin/python -m data_platform.databricks.upload_to_volume \
  --volume "$NOEMA_VOLUME" \
  --bundle complete \
  --plan-file logs/build/databricks_upload_plan_complete.json
```

Resultado local verificado el 2-oct-2026, sin escribir en Databricks:

```text
databricks-inputs: 7,686 archivos, 2,355,684,137 bytes
complete:          7,731 archivos, 2,610,842,926 bytes
```

El plan JSON incluye por archivo:

- ruta local;
- ruta remota en el Volume;
- tamaño en bytes;
- SHA-256 local.

## 4. Ejecutar subida real

Cuando las variables apunten al workspace real:

```bash
.venv/bin/python -m data_platform.databricks.upload_to_volume \
  --volume "$NOEMA_VOLUME" \
  --bundle databricks-inputs \
  --execute
```

O, si se quiere respaldar todo:

```bash
.venv/bin/python -m data_platform.databricks.upload_to_volume \
  --volume "$NOEMA_VOLUME" \
  --bundle complete \
  --execute
```

Con `--execute`, el script:

1. crea directorios remotos;
2. sube cada archivo sin sobrescribir;
3. descarga cada archivo recién subido;
4. recalcula SHA-256 remoto;
5. falla si el checksum no coincide.

Si se interrumpe, el error indica cuántos archivos se verificaron. No se debe
declarar el espejo completo hasta que todos los archivos estén verificados.

## 5. Construir dbt en Databricks

Después de subir `databricks-inputs`, correr:

```bash
make build-databricks
```

Equivalente:

```bash
cd data_platform/dbt
dbt build --profiles-dir . --target databricks --log-path ../../logs/build/dbt
```

El perfil Databricks vive en `data_platform/dbt/profiles.yml` y usa:

- `DATABRICKS_HOST`
- `DATABRICKS_HTTP_PATH`
- `DATABRICKS_TOKEN`
- `DATABRICKS_CATALOG`

## 6. Qué falta para marcar DAT-13 como terminado

DAT-13 no queda aceptado por un dry-run. Falta una ejecución real contra el
workspace Databricks:

1. crear catálogo/schema/Volume;
2. ejecutar upload con `--execute`;
3. verificar que `verified_files == files`;
4. correr `make build-databricks`;
5. guardar `logs/build/dbt/dbt.log` y el resultado de la subida;
6. confirmar que los modelos silver/gold existen en Databricks.
