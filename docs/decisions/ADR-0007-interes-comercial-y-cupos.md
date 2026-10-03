# ADR-0007 · Separar propensión comercial, límites registrados y ofertas

Fecha: 2026-09-30. Estado: experimental; no habilita decisiones productivas.

La solicitud de Federico requiere interés en producto y cupo por cliente. Existen
campañas con conversiones y productos con `credit_limit`; no existen etiquetas
fiables de deseo explícito ni primera adquisición. La política de Eduardo ya
calcula escenarios de nuevas ofertas.

Se entrena logística regularizada contra prior con variables previas a exposición,
ventanas temporales y embargo. Se reporta conversión a 30 días como proxy, sin
convertirla en aprobación ni contacto automático. El modelo se selecciona solo
con validación y permanece experimental por falta de snapshots de etiquetas.

Los cupos existentes se leen por producto/moneda con procedencia y última fecha.
No se agregan monedas, reconstruyen saldos históricos ni inventan disponibles.
Las nuevas ofertas requieren el motor existente y entradas verificadas; sin ellas
el asesor devuelve requisitos pendientes. No modifica políticas ni ML-04.

Se descarta entrenar una red profunda por ahora: no resuelve los defectos de
etiquetado. La consecuencia es una entrega ejecutable y medible, con abstención
explícita en las partes que los datos no respaldan.
