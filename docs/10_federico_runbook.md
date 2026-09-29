# Entrega de Federico

## Ejecución local

Python 3.11 o superior; instalar `pip install -e '.[dev,data]'` dentro de un entorno virtual. Activarlo antes de usar `make`.

1. `make audit`: recorre las 13 tablas; crea validación, cuarentenas y reporte agregado en `logs/build/dq_report.json`.
2. `make build`: repite auditoría, ejecuta dbt y sus pruebas; exporta gold a `data/gold/`.
3. `make train-capacity`: entrena el proxy y baseline temporal; artefacto JSON en `data/models/capacity.json`, métricas en `logs/build/capacity_metrics.json`.
4. `pytest` y `SCM_ENABLED=false pytest`: contratos y casos adversos.

Bronze nunca se modifica. Las filas rechazadas conservan razones y linaje. Referencias opcionales huérfanas quedan nulas en validated y el original se conserva en `data/quarantine_references/`. Filas con FK esenciales inválidas o duplicados de PK se rechazan sin elegir arbitrariamente un ganador.

La capa silver tipa y normaliza los 13 conjuntos; transacciones se convierten con FX del día de operación. Sin esa cotización van a cuarentena. Gold contiene `customer_360`, `credit_features_asof`, `product_policy` y `dq_report`. La fecha de valoración del saldo actual es explícita y no es una variable de entrenamiento.

## Límites e integración

- Política: falta una oferta versionada de Eduardo. `product_policy` tiene condiciones NULL y `policy_ready=false`; ninguna aprobación debe usarla todavía.
- Capacidad: proxy de flujo, no verdad observada de solvencia. Ver ADR-0005. `predict_capacity` vive en `ml/training/capacity.py` para que Eduardo lo conecte al predictor compartido. Se abstiene ante historia insuficiente o flujos ambiguos.
- SCM: clase y pruebas listas; la conexión a `SCM_ENABLED` y evaluación de ablación siguen a cargo del orquestador de Eduardo.
- Databricks: ver `data_platform/databricks/README.md`; no hay credenciales locales.
- Postgres: `python -m data_platform.serving.export_to_postgres` muestra plan. Con `POSTGRES_DSN` y `--execute` reemplaza tablas gold dentro de una transacción y verifica conteos. Debe ejecutarse con el rol de carga, nunca el rol de lectura de la API. La conexión real sigue pendiente.

No se hicieron cambios en el orquestador, riesgo, API ni interfaz.
