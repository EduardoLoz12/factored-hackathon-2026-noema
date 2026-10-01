# ADR-0008 · Red profunda como alternativa comercial y política con evidencia

Fecha: 2026-09-30. Estado: implementado, experimental.

Federico solicita deep learning e incorporar el HTML de elegibilidad y la auditoría
Bronze/Silver. Se agrega MLP tabular 32–16–8 con entrenamiento real, checkpoint por
validación temporal y comparación con logística/prior. Se mantiene la lista cerrada
de entradas de campaña para no incorporar snapshots posteriores ni etiquetas de
mora sin validez. La red no aprende a imitar aprobaciones inventadas por reglas.

Un asesor único combina ranking experimental, cupos observados y una llamada al
motor de Eduardo con `VerifiedPolicyInput`. No altera sus umbrales o aritmética.
Agrega una puerta de evidencia: identidad/corte coherentes, obligaciones completas,
términos conocidos y números finitos. Esto implementa la abstención por obligaciones
faltantes descrita en el HTML, que el cálculo de carga actual no impone por sí solo.

Resultado: la red se entrega entrenada y ejecutable; la logística sigue recomendada
por validación. El modelo neuronal queda visible para comparar, sin promoción
automática por ser más complejo. Los documentos aportan contratos y advertencias,
no etiquetas para entrenamiento. Ningún escenario se presenta como aprobación real.

Limitación: el asesor es una herramienta interna, no un servicio autenticado ni una
interfaz conversacional desplegada. El llamador certifica la procedencia de inputs;
el adaptador verifica coherencia, no realiza verificación documental del cliente.
