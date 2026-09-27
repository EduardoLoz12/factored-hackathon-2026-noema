# Limitaciones

El kickoff pide ser honesto sobre lo que falta. Esta página se escribe desde el día 1 y se actualiza al cierre.

## Datos

1. **El dataset no tiene portugués.** Las 200 000 transcripciones están en español al 100 %, con dos plantillas y un solo intent. El set de evaluación en PT-BR es **generado y traducido por nosotros**, y sus métricas se reportan por separado. La diversidad lingüística de esos casos está acotada por la de las plantillas originales.
2. **No existe verdad de campo sobre aprobación crediticia.** El dataset no registra decisiones históricas de aprobación o rechazo. La política de elegibilidad es **declarada por nosotros** — razonable y documentada, pero no observada.
3. **La mora es una fotografía sin fecha de medición.** El corte temporal usado para construir variables es un supuesto declarado (ADR-0004), no un hecho del dataset.
4. **El diccionario y el dato no coinciden.** Conteos de filas, enums, rangos, duplicados y nulos difieren de lo documentado (ver `docs/01_data_audit.md`). Trabajamos contra el dato observado, pero eso significa que cualquier comparación con otro equipo que haya confiado en el diccionario no será directa.
5. **MXN no existe en `products`** pese a que la mitad de los clientes son mexicanos. Las conversiones se hacen contra las monedas realmente presentes.

## Modelos

6. **Menos variables por prevención de fuga.** Excluimos deliberadamente columnas que reflejan el desenlace, a costa de métricas más modestas. Preferimos un AUC creíble a uno inflado.
7. **Sin reentrenamiento continuo ni monitoreo de drift en producción.** Se reporta estabilidad por país sobre el período retenido, nada más.

## Sistema

8. **Alcance deliberadamente estrecho:** un solo workflow de los cuatro permitidos. Los otros tres no están cubiertos.
9. **No hay integración con un core bancario real.** Las escrituras van a nuestra propia base; la verificación posterior es real contra ese store, no contra un sistema bancario.
10. **Sin autenticación biométrica ni segundo factor.** La puerta de identidad usa tres datos del cliente, que es lo que el dataset permite.
11. **Sin alta disponibilidad.** Una sola región, una sola instancia. No hay plan de recuperación ante desastre.
12. **Sin cumplimiento regulatorio formal.** No hay evaluación de sesgo por género o edad con umbrales regulatorios, ni revisión legal de la política de crédito.

## Qué costaría hacerlo real

| Falta | Esfuerzo estimado |
|---|---|
| Portugués con datos reales | Corpus etiquetado de clientes BR — semanas, no días |
| Verdad de campo de aprobaciones | Acceso al histórico de decisiones del banco |
| Integración con core bancario | Contratos de API, ambiente de pruebas, certificación |
| Monitoreo de drift y reentrenamiento | Pipeline programado + alertas + gobierno de modelos |
| Evaluación de sesgo regulatorio | Métricas de equidad por grupo protegido y revisión legal |
| Alta disponibilidad | Multi-instancia, réplicas de base de datos, pruebas de carga |
