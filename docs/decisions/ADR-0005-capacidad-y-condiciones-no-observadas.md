# ADR-0005 · Capacidad observable y condiciones pendientes

**Fecha:** 2026-09-28 · **Estado:** supuesto de implementación, requiere validación del equipo.

Los importes de transacciones no distinguen dirección de transferencias ni cuotas comprometidas. Usamos depósitos aprobados como entrada y compras, pagos y retiros aprobados como salida. Transferencias y ajustes quedan fuera del neto y se cuentan como incertidumbre. No se usa ingreso declarado.

La capacidad es un proxy conservador del flujo observado: menor entre excedente mensual y 30 % de depósitos mensuales, nunca negativo. El 30 % es un supuesto de modelado, no una política bancaria. Se entrena una regresión sobre ventanas históricas para predecir el proxy del mes siguiente, con validación temporal antes del corte. No implica aprobación ni demuestra solvencia. Sin historia suficiente o con flujos ambiguos la respuesta se abstiene.

Tanto fecha de operación como fecha de proceso deben preceder estrictamente 2025-12-31. Así no entran registros tardíos que aún no se conocían al corte. FX usa fecha de operación; nunca una cotización futura. Ventanas incluyen meses sin transacciones, con ceros.

El dataset no contiene mínimos de score, montos ni plazos de oferta. `product_policy` conserva tipos observados y condiciones nulas, con `policy_ready=false`. Eduardo debe aportar la política versionada antes de habilitar decisiones. Las tasas de productos existentes no se convierten en tasas de oferta.

La spec menciona un predictor acordado que aún no está en disco. Federico entrega una función `predict_capacity` en su módulo; Eduardo la conecta al predictor compartido y al orquestador. El SCM tampoco configura `SCM_ENABLED`: la bandera pertenece a esa integración.

## Relaciones opcionales huérfanas

La auditoría completa encontró que casi todas las referencias de sucursal de clientes son huérfanas. Se conserva el registro original en `data/quarantine_references/<tabla>/` y se elimina únicamente la relación inválida (NULL) en validated. Las relaciones de cliente y producto transaccional son esenciales y rechazan filas. Así se preservan clientes útiles sin inventar sucursales; el reporte expone cada reparación. La cuarentena de referencias es evidencia adicional, no filas rechazadas a sumar a la conservación de filas.
