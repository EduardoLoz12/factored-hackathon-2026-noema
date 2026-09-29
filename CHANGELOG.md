# Control de cambios

Generado con `make changelog` desde el historial de git. Agrupa por día y por tipo, y liga cada cambio al ítem del checklist que movió.

Formato de commit: `Tipo (ÍTEM): qué cambió, en español y sin jerga`. Por ejemplo: `Nuevo (DAT-08): la capa silver convierte todos los montos a dólares con la tasa del día`. Tipos: `Nuevo`, `Corrige`, `Mejora`, `Docs`, `Pruebas`, `Infra`, `Limpieza`, `Revierte`.

Última generación: 2026-09-29 10:32

## 2026-09-29 — Eduardo

### Limpieza

- el id de usuario que genera dbt no se versiona — Eduardo (`e5c411a`)

### Otros

- `ML-01` `ML-03` · Docs (ML-01/ML-03): la etiqueta de riesgo es un sorteo — no hay modelo de riesgo posible — Eduardo (`c6324a9`)
- `DAT-04` `ML-01` · Docs (DAT-04/ML-01): segunda pasada sobre nulos y llaves — cinco hallazgos que cambian el plan del modelo — Eduardo (`c157a5c`)

## 2026-09-28 — Eduardo, fedevargas93

### Corregido

- el formateador y el limite de ancho se contradecian en una prueba — Eduardo (`05d54d5`)

### Documentacion

- acredita a Codex como agente colaborador de Federico — fedevargas93 (`1912b85`)

### Otros

- `ML-04` · Docs (ML-04): agrega entrega técnica para el equipo — fedevargas93 (`f8ef800`)
- `ML-04` · Docs (ML-04): registra resultados del modelo y limpieza de datos — fedevargas93 (`f763872`)
- `INF-07` · Docs (INF-07): registra avance y fronteras de la entrega de Federico — fedevargas93 (`b5eee82`)
- `DAT-03` `ML-04` `SCM-02` · Nuevo (DAT-03/ML-04/SCM-02): completa datos, capacidad y cognición de Federico — fedevargas93 (`3ba73a2`)

## 2026-09-27 — Eduardo

### Nuevo

- `INF-07` · checklist vivo, plan por dias, logs y control de cambios — Eduardo (`cc4b84f`)
- onboarding de Federico, contrato del SCM y revisión de contribuciones — Eduardo (`93cedac`)
- scaffold del proyecto, ingesta S3 y auditoría del dataset — Eduardo (`bef23c5`)

### Corregido

- **build** · declarar paquetes explícitos — pip install -e fallaba — Eduardo (`e091828`)

### Mejorado

- Federico pasa a ser dueno de la limpieza, el ETL y la capacidad de pago — Eduardo (`0a76652`)

### Limpieza

- repo en la raíz de la carpeta de trabajo + resumen del manifest — Eduardo (`d44be93`)

### Otros

- `INF-07` · Nuevo (INF-07): bitacora de trabajo, carpeta de logs y control de cambios legible — Eduardo (`637dd0f`)

