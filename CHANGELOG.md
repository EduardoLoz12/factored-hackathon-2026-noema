# Control de cambios

Generado con `make changelog` desde el historial de git. Agrupa por día y por tipo, y liga cada cambio al ítem del checklist que movió.

Formato de commit: `Tipo (ÍTEM): qué cambió, en español y sin jerga`. Por ejemplo: `Nuevo (DAT-08): la capa silver convierte todos los montos a dólares con la tasa del día`. Tipos: `Nuevo`, `Corrige`, `Mejora`, `Docs`, `Pruebas`, `Infra`, `Limpieza`, `Revierte`.

Última generación: 2026-10-05 14:35

## 2026-10-05 — Eduardo

### Otros

- `AG-05` `UI-02` · Nuevo (AG-05/UI-02): la identidad se verifica conversando, y la conversacion tiene ritmo — Eduardo (`c4beaa8`)
- `UI-04` · Nuevo (UI-04): tres conversaciones guiadas que corren el flujo real, y el agente por fin dice las cifras — Eduardo (`d8053c1`)
- `UI-02` `UI-03` · Mejora (UI-02/UI-03): la interfaz toma el diseno que armo Federico — Eduardo (`a60e262`)
- `UI-03` · Mejora (UI-03): el panel pasa de un log de etapas a una auditoria paso a paso — Eduardo (`8e18195`)
- `UI-08` · Nuevo (UI-08): base reducida, perfiles de demostracion y la auditoria de Federico en el panel — Eduardo (`49a0081`)
- `ENT-01` `ENT-02` · Docs (ENT-01/ENT-02): el protocolo de evaluacion y las limitaciones del cierre — Eduardo (`81fd155`)
- `API-01` `API-02` `UI-02` `UI-07` · Nuevo (API-01/API-02, UI-02..UI-07): la API y la interfaz que el jurado usa, en un solo origen — Eduardo (`2989f01`)
- `EV-01` `EV-06` · Nuevo (EV-01..EV-06): el conjunto retenido, los tres brazos y la tabla que los compara — Eduardo (`529c9d9`)
- `ML-11` `ML-13` · Nuevo (ML-11..ML-13): entra la propension comercial que Federico midio bien, y queda fuera lo que no paso su propio metodo — Eduardo (`a626fd6`)
- `EV-06` · Corrige (EV-06): la suite vuelve a correr con SCM_ENABLED=false, que es como se mide el tercer brazo — Eduardo (`85a296a`)

## 2026-10-02 — Eduardo

### Otros

- `INF-07` · Docs (INF-07): contrato de trabajo para el agente de Federico, con el nivel de validador que exige cada entregable — Eduardo (`393ba32`)
- `INF-07` · Docs (INF-07): control de cambios al dia, y el generador deja de romper su propio commit — Eduardo (`7cf87b3`)
- `AG-03` `AG-10` · Nuevo (AG-03..AG-10): el ciclo del agente cierra de punta a punta — Eduardo (`ee3f5d3`)

## 2026-10-01 — fedevargas93

### Otros

- `ML-13` · Nuevo (ML-13): compara seis capas neuronales con control temporal del sobreajuste — fedevargas93 (`7a8785e`)

## 2026-09-30 — Eduardo, fedevargas93

### Otros

- `ML-12` · Nuevo (ML-12): integra red profunda y política de Eduardo en el asesor por cliente — fedevargas93 (`4a95803`)
- `ML-11` · Nuevo (ML-11): estima interés comercial y consulta cupos registrados por cliente — fedevargas93 (`e3203c5`)
- `INF-07` · Docs (INF-07): tres avisos para Federico sobre la capa de datos, dos de ellos bugs — Eduardo (`9c0175d`)
- `ML-01` · Corrige (ML-01): todo importe del feature store pasa a USD, y se retiran cuatro variables que repetian informacion — Eduardo (`337be65`)
- `INF-07` · Docs (INF-07): control de cambios regenerado con el trabajo del dia 4 — Eduardo (`3ce2b6e`)
- `AG-01` `AG-02` · Nuevo (AG-01/AG-02): la elegibilidad se calcula con una politica versionada, porque el dataset no permite aprenderla — Eduardo (`32a1d7b`)

## 2026-09-29 — Eduardo, fedevargas93

### Limpieza

- el id de usuario que genera dbt no se versiona — Eduardo (`e5c411a`)

### Otros

- `INF-03` · Docs (INF-03): incorpora la auditoria interactiva de bronze contra silver — fedevargas93 (`aed6905`)
- `ML-03` · Docs (ML-03): days_past_due no son dias de mora y fraud_score no sale de un modelo — ningun objetivo del dataset es aprendible — Eduardo (`232d041`)
- `ML-01` `ML-02` · Corrige (ML-01/ML-02): la cohorte de trabajo vuelve a 76 906 clientes — el filtro que la bajaba a 7 078 no se sostiene — Eduardo (`d95ab93`)
- `ML-01` `ML-02` · Nuevo (ML-01/ML-02): feature store con corte temporal honesto y baseline que no discrimina — Eduardo (`89c75a6`)
- `INF-06` · Corrige (INF-06): dos de los tres agentes no se registraban por culpa de los finales de linea — Eduardo (`7dfd52d`)
- `INF-07` · Docs (INF-07): bitacora del dia, control de cambios y guia de lo que cambio para Federico — Eduardo (`1d78dd2`)
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
