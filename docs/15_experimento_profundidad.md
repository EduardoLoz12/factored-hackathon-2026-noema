# Comparación controlada de profundidad — ML-13

## Pregunta y alcance

¿Más capas mejoran la conversión comercial estimada sin empeorar generalización?
No existe un mínimo universal de cuatro capas: capacidad, señal, regularización,
optimización y calidad de etiquetas importan más que el conteo aislado.

Se añade una red de **seis capas ocultas** (32–32–16–16–8–8), frente a la anterior
de tres (32–16–8). La capa de salida sigmoide es adicional: siete y cuatro capas
con parámetros respectivamente. No se cuenta la entrada como capa entrenable.
No es un estudio que aísle únicamente profundidad: también aumenta el número de
parámetros. No se modifica el motor de crédito ni se inventan etiquetas nuevas.

## Protocolo fijado antes de comparar

- Mismas cuatro variables originales, misma fuente silver y mismo entrenamiento
  hasta noviembre 2024. La codificación/escala se aprende únicamente en train.
- Enero 2025 para parada temprana; etiquetas a 30 días. Registros de enero deben
  estar disponibles antes del 3 de marzo.
- Febrero y los dos primeros días de marzo quedan fuera de la selección para
  madurar incluso etiquetas de envíos del 31 de enero.
- Desde el 3 al 31 de marzo para comparar modelos; no modifica sus pesos.
- Test desde mayo: solo evaluación posterior a selección. Es el test ya conocido
  de ML-11/12, no una validación externa nueva.
- Tres semillas predefinidas (42, 43, 44), sin elegir la más favorable.
- Adam, ReLU, L2 alpha 0.01, tasa 0.001, batch hasta 1024, límite de 30 épocas,
  paciencia 4 y mejora mínima 1e-7. Restaurar siempre el mejor checkpoint de enero.

El promedio de log-loss de marzo compara las familias. La red de seis capas
entregada usa **semilla 42**, fijada previamente. Su recomendación individual exige
mejorar log-loss, AP y Brier de la logística en marzo; nunca depende del test.
La dispersión entre tres semillas es descriptiva, no un intervalo de confianza.
El criterio es conservador y no es una prueba de superioridad estadística.

## Sobreajuste

Cada ejecución conserva su curva de entrenamiento y parada, mejor época y número
de parámetros. El objetivo de entrenamiento incluye regularización y promedia
minibatches mientras cambian los pesos; no debe compararse directamente con
log-loss de validación como si fueran la misma medición. El reporte también calcula
métricas finales del checkpoint sobre train y selección con la misma función.

Una pérdida de entrenamiento que baja mientras empeora la validación sugiere
sobreajuste, pero fluctuaciones pequeñas no lo demuestran. Llegar a la época 30
sin parada temprana tampoco demuestra ausencia de sobreajuste: solo se alcanzó
el presupuesto prefijado. No se aumenta ese presupuesto mirando el test.

El artefacto de seis capas queda separado y no reemplaza el asesor por defecto.
La política sigue requiriendo entradas verificadas y puede abstenerse.

## Reproducción

```bash
python -m ml.training.depth_experiment
python -m ml.serving.client_analysis --customer-id ID_AUTORIZADO \
  --model data/models/deeper_interest.joblib
pytest tests/ml/test_depth_experiment.py
```

Artefacto local: `data/models/deeper_interest.joblib`. Reporte agregado versionado:
`ml/model_cards/depth_experiment.json`. Las pruebas comprueban seis capas reales,
serialización y que alterar etiquetas del test no cambia pesos ni selección.

No se han resuelto las limitaciones del dataset: conversión no es deseo explícito,
los outcomes no tienen historial completo de revisiones y falta evaluación en
clientes nuevos y múltiples cortes temporales. Más capas no corrigen esas carencias.

## Resultado medido

| Selección marzo, tres semillas | 3 capas ocultas | 6 capas ocultas |
|---|---:|---:|
| Parámetros entrenables | 1 153 | 2 553 |
| Log-loss medio (menor es mejor) | 0.032557 | 0.032581 |
| AP media | 0.008370 | 0.007988 |
| ROC-AUC media | 0.65570 | 0.64950 |
| Mejor época, semillas 42/43/44 | 8 / 13 / 16 | 30 / 30 / 4 |

La familia de tres capas gana la comparación promedio. La logística obtiene
log-loss de selección 0.032346, mejor que las dos familias; sigue recomendada.

| Test, semilla fija 42 | 3 capas ocultas | 6 capas ocultas | Logística |
|---|---:|---:|---:|
| ROC-AUC | 0.66885 | 0.67758 | 0.67672 |
| Log-loss | 0.029426 | 0.029264 | 0.029242 |
| AP | 0.007994 | 0.008237 | 0.008133 |
| Lift top 10% | 1.78682 | 1.89219 | 1.77191 |

La mejora de AUC de seis capas sobre logística es 0.00086: no se declara
significativa ni se cambia el modelo recomendado mirando test. El baseline de
3 capas de esta comparación usa un checkpoint de enero, por eso sus cifras no
coinciden con ML-12, que usó enero–marzo para elegir época. Es un cambio de protocolo,
no una regresión del artefacto anterior, que se conserva intacto.

No se observa una ganancia consistente por añadir capas. Tampoco se diagnostica
sobreajuste fuerte solo por el número de capas: hay sensibilidad de optimización
y mejora limitada. Para seis capas, dos semillas llegan al límite de épocas y otra
se detiene en la octava conservando la cuarta. Se requiere evidencia externa antes
de promover cualquiera de ellas. Suite completa: 162 pruebas pasan, cero skips.

## Excel de muestras aportado durante la revisión

`muestras_13_tablas.xlsx` contiene 13 hojas con muestras. `campaign_sends` tiene
200 filas, tres conversiones, una campaña y fechas de envío 1–2 de julio de 2023.
Se verificó que sus 200 identificadores de envío existen en la tabla silver local,
que contiene 1 746 801 filas antes de filtros. Esa coincidencia verifica pertenencia
por ID, no igualdad de todos los campos ni admisibilidad de cada fila para entrenar.
El entrenamiento se realizó con las tablas completas y filtros documentados;
el Excel se revisó después, no se usó como archivo de entrenamiento. Esa muestra
sola no permite el protocolo temporal ni una evaluación fiable de la red.
