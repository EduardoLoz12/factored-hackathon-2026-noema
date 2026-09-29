# Espejo de datos

Instalar `.[cloud]`. Crear un Volume y configurar `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_CATALOG` y `NOEMA_VOLUME=/Volumes/catalog/schema/volume`. No guardar valores en git.

`python -m data_platform.databricks.upload_to_volume` imprime el plan sin escribir. `--execute` carga bronze, validated y quality en el Volume y relee cada archivo para verificar SHA-256. El Volume debe estar vacío; no sobrescribe datos existentes. Después `make build-databricks` ejecuta los mismos modelos sobre esos Parquet. Cuarentenas locales no se publican.

No se ha verificado contra Databricks: esta copia del proyecto no tiene credenciales. La instalación del adaptador y una ejecución real siguen siendo necesarias para aceptar DAT-13.
