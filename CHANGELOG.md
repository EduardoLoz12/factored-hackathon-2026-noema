# Control de cambios

Generado con `make changelog` desde el historial de git. Agrupa por día y por tipo, y liga cada cambio al ítem del checklist que movió.

Formato de commit: `tipo(ámbito): descripción`. Usa el identificador del ítem como ámbito cuando aplique — por ejemplo `feat(DAT-06): silver de productos`. Tipos: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`, `revert`.

Última generación: 2026-09-27 17:34

## 2026-09-27 — Eduardo

### Nuevo

- onboarding de Federico, contrato del SCM y revisión de contribuciones — Eduardo (`93cedac`)
- scaffold del proyecto, ingesta S3 y auditoría del dataset — Eduardo (`bef23c5`)

### Corregido

- **build** · declarar paquetes explícitos — pip install -e fallaba — Eduardo (`e091828`)

### Mantenimiento

- repo en la raíz de la carpeta de trabajo + resumen del manifest — Eduardo (`d44be93`)

