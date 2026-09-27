# ADR-0001 · Workflow elegido y separación entre conversación y decisión

**Fecha:** 2026-09-26 · **Estado:** aceptado

## Contexto

El reto obliga a elegir **un solo** workflow bancario entre cuatro: consultas de cuenta y pagos, soporte de tarjetas, disputas de transacciones, o información y elegibilidad de productos de crédito. Además exige un «componente aprendido» comparado contra un modelo base, y penaliza explícitamente la autonomía innecesaria.

La idea inicial del equipo giraba alrededor de **cobranza**: clasificar clientes en mora y enrutarlos a canales de contacto según los días de atraso.

## Decisión

1. **Workflow: Credit-Product Information & Eligibility.**
2. **El modelo de lenguaje conversa y explica; no decide ni produce cifras.** La decisión de elegibilidad la toma un motor de reglas versionado que consume las salidas de modelos entrenados.

## Alternativas consideradas

- **Cobranza como workflow principal.** Descartada: no está entre las cuatro opciones permitidas y la selección de workflow es criterio central de evaluación.
- **Disputas de transacciones.** Muy «agéntica» y demostrable, pero el componente aprendido queda decorativo — se perdería la ventaja de tener etiquetas de riesgo reales.
- **Consultas de cuenta y pagos.** La más fácil de hacer funcionar y la más commodity; alto riesgo de leerse como «un chatbot más».

## Consecuencias

- La inteligencia de la idea original **no se pierde, cambia de lugar**: el modelo de incumplimiento y la capacidad de pago se vuelven *tools* del agente; el motor de reglas por severidad se vuelve la política de decisión y escalamiento; los canales se vuelven el enrutamiento del caso escalado.
- Aprobar crédito a quien no puede pagarlo es un daño concreto y explicable → «saber cuándo no actuar» deja de ser una frase y se vuelve medible como `unsafe_action_rate`.
- El motor de reglas es testeable sin ejecutar el LLM, lo que permite una suite determinista rápida.
