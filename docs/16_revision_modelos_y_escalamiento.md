# Revisión de modelos y nuevo objetivo: escalamiento

Fecha: 1 de octubre de 2026. Trabajo local en `trabajo/federico-data-cognition`.

## Resultado de la revisión

Se actualizó la información remota con `git fetch origin`. `origin/main` sigue en
`9c0175d`, del 30 de septiembre; ese historial ya está integrado en esta rama.
No apareció trabajo posterior de Eduardo durante esta revisión. Sus cambios
relevantes son `337be65` (importes del feature store a USD y eliminación de
variables redundantes) y `32a1d7b` (motor de elegibilidad con política versionada).
También se revisaron sus avisos en `docs/12_cambios_para_federico.md` y los
hallazgos en `docs/knowledge/findings.md`.

Hay dos familias de interés comercial: regresión logística y redes MLP. Las
redes de tres y seis capas predicen el **mismo** objetivo; no son tres problemas
independientes. El cupo se trata por separado: límite registrado del producto o
escenario determinista de política, nunca una aprobación inferida por el LLM.

| Modelo | Objetivo | Resultado de test | Decisión |
|---|---|---|---|
| Logística | Conversión de campaña en 30 días | AUC 0.6767; AP 0.00813 | Referencia recomendada, experimental |
| MLP de tres capas, experimento original | Mismo objetivo | AUC 0.6739; AP 0.00814 | Comparador experimental |
| MLP de seis capas, semilla 42 | Mismo objetivo | AUC 0.6776; AP 0.00824 | No supera consistentemente en selección |
| Logística de escalamiento, nueva | Escalamiento observado en soporte | AUC 0.4974; AP 0.09799 | No activar como decisor |

Los informes fuente están en `ml/model_cards/`. El experimento de profundidad
compara tres semillas y selecciona por validación, no por test. El test ya se
consultó en iteraciones anteriores: sus cifras son un benchmark retrospectivo,
no una nueva evaluación externa. Más capas no garantizan mayor capacidad útil.
L2 y parada temprana reducen sobreajuste, pero no prueban que no exista: faltan
validaciones en otros periodos y clientes no vistos. No debe confundirse una
AUC de ~0.68 con precisión del 68 %. La baja prevalencia comercial (~0.49 %)
requiere AP, calibración, lift y costos de contacto, además de ROC-AUC.

## Nuevo experimento reproducible

Hipótesis: canal, tipo de interacción y razón declarada al inicio podrían ayudar
a anticipar si una interacción termina escalada. Se eligió una logística regularizada
antes de una red porque es una prueba interpretable de señal en tres variables
categóricas. Fallar aquí no demuestra que ningún modelo pueda aprender: demuestra
que este conjunto de variables y protocolo no respalda desplegar este predictor.

Fuente: `noema_silver.stg_call_center_interactions`. La tabla completa contiene
686,296 registros, de los que 68,386 tienen escalamiento observado. El entrenamiento
filtra fechas incoherentes, disponibilidad posterior al corte y entradas nulas.
No usa duración, resolución, sentimiento ni otros campos posteriores al desenlace.
`OneHotEncoder` se ajusta dentro del pipeline únicamente con entrenamiento.

- Entrenamiento: antes de enero de 2025.
- Validación: febrero a abril de 2025, 37,375 interacciones.
- Test: junio a diciembre, antes del 31 de diciembre de 2025, 88,976 interacciones.
- Enero y mayo quedan fuera de las particiones.
- Umbral exploratorio para activar: AUC de validación ≥0.60 y AP ≥1.2 veces la
  prevalencia de validación. No es una certificación de seguridad bancaria.

Validación: AUC **0.50126**, AP **0.10154**, prevalencia **0.10071**.
Test: AUC **0.49740**, AP **0.09799**, prevalencia **0.09925**.
El umbral falla. La alta exactitud aparente de predecir siempre «no» no justificaría
negar atención a quien la solicita. El prototipo no carga este artefacto para enrutar.

```bash
.venv/bin/python -m ml.training.support_escalation
```

Genera `data/models/support_escalation.joblib` (local, ignorado por Git) y
`ml/model_cards/support_escalation.json`. No publica datos ni artefactos.

## Lo que hace falta para aprender una escalación correcta

`was_escalated` describe lo que ocurrió, no si era correcto. Se necesitan contactos
anonimizados con contexto disponible al inicio, categoría de riesgo, petición
explícita de humano, decisión revisada por especialistas y su motivo, desenlace,
tiempos de cada campo y criterios de resolución. Separar por fecha y cliente;
reservar un conjunto externo, medir recall de casos críticos, precisión/carga de
asesores, calibración, abstención y diferencias por idioma. No entrenar con respuestas
inventadas presentadas como verdad. Identificadores no deben ser predictores.

La solicitud explícita de una persona, el fraude y situaciones fuera de alcance
necesitan reglas y una vía de atención aun si un modelo futuro devuelve bajo riesgo.
Para el siguiente objetivo cuantitativo también es razonable investigar flujo neto
a 30 días por cuenta usando solo transacciones anteriores al corte; primero hay
que reconstruir snapshots y comprobar señal frente a un pronóstico ingenuo. No
se afirma haber entrenado ese segundo objetivo adicional.
