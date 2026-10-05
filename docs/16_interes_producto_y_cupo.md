# Interés de producto y cupo por cliente

## Qué se entrega

Rama `trabajo/federico-data-cognition`, sincronizada con `origin/main` (`9c0175d`).
Modelo entrenado localmente sobre campañas reales del dataset sintético del reto;
consulta por cliente de límites registrados; pruebas; reporte reproducible.
No se reentrena el riesgo ni se altera la política de Eduardo.

Tres preguntas diferentes:

| Pregunta | Respuesta implementada | Lo que no demuestra |
|---|---|---|
| ¿Responderá a una oferta? | Probabilidad experimental de conversión en 30 días | Deseo explícito o primera compra |
| ¿Tiene un cupo registrado? | `credit_limit` por producto y moneda, con fecha de observación | Disponibilidad actual ni límite global de cliente |
| ¿Qué monto nuevo puede recibir? | Contrato de integración con `Politica.evaluar`; se abstiene sin entradas verificadas | Una aprobación bancaria basada en la propensión |

«Cuota» puede significar pago mensual; «cupo», límite de crédito. La consulta nueva
expone **cupo registrado**. El estimador existente `predict_capacity` devuelve
**pago mensual proxy**; el motor existente devuelve `monto_maximo_usd` y
`cuota_estimada_usd`. Estos tres valores no son intercambiables.

## Paso 1. Formular una etiqueta observable

La unidad es una exposición cliente–campaña, no una persona. Se define
`y = 1` si `had_conversion` y `send_date <= conversion_date <= send_date + 30 días`.
Se excluyen ventanas inmaduras al 2025-12-31, conversiones inconsistentes,
identificadores ausentes, campaña sin producto y fechas de proceso anteriores al envío.
La auditoría reporta motivos superpuestos: **no deben sumarse** como rechazos exclusivos.
Los envíos posteriores también contribuyen al contador de ventanas inmaduras.

No se entrena un clasificador de intención lingüística: las transcripciones son
plantillas. Tampoco se etiqueta «no quiere» cuando no hubo conversión. La falta de
conversión puede reflejar canal, entrega, exposición o condiciones de oferta.
No se usa `was_delivered` para filtrar: sería un resultado posterior al envío.

## Paso 2. Construir variables disponibles antes de la decisión

Lista cerrada: producto promovido, canal propuesto, mes del envío y número de
exposiciones previas del cliente. El historial usa `process_date < send_date` y
`process_date >= send_date` del evento histórico: ni eventos del mismo día ni
cargas tardías desconocidas pueden entrar antes de tiempo. Se cuentan únicamente
exposiciones válidas con producto y canal, igual en entrenamiento e inferencia.

Se excluyen resultado, clic, apertura, conversión, ingreso, score, nombres,
documentos, país, género y el identificador del cliente como predictor. El ID
solo sirve para historial y bootstrap. No usar atributos sensibles no garantiza
ausencia de sesgo: sigue pendiente auditar resultados por cohortes autorizadas.
Los perfiles y límites del snapshot no se reconstruyen como si fueran históricos.

## Paso 3. Escoger un modelo comprobable

Regresión logística L2: `p(y=1|x) = sigmoid(b + w·x)`. Codificación categórica,
imputación y escalado viven dentro de `Pipeline`, ajustados solo con entrenamiento.
Se compara con la prevalencia de entrenamiento (`DummyClassifier`). No se balancean
artificialmente clases para no distorsionar las probabilidades. No hay búsqueda
iterativa sobre test ni umbral arbitrario 0.5 de «quiere/no quiere».

La logística permite inspeccionar coeficientes y cuesta poco. Puede perder
interacciones no lineales; una red profunda añadiría capacidad sin resolver la
falta de etiquetas de deseo o snapshots versionados. Normalidad de residuos OLS
no es un requisito para este clasificador. La dependencia entre exposiciones de
un mismo cliente se reconoce mediante intervalos bootstrap por cliente.

Referencia metodológica: [Aaron Wang, Data Science Cheatsheet](https://github.com/aaronwangy/Data-Science-Cheatsheet)
(regresión logística, regularización, sesgo/varianza y curvas PR).
Implementación de prevención de fuga: [scikit-learn, Common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html).
No se copia material del cheatsheet al código.

## Paso 4. Separar entrenamiento, selección y prueba

- Entrenamiento: envíos anteriores a 2024-12-01, disponibles antes de 2025-01-01.
- Validación: 2025-01-01 a 2025-03-31, disponibles antes de 2025-05-01.
- Test final: desde 2025-05-01, con ventana de 30 días completa antes del corte.
- Diciembre 2024 y abril 2025 funcionan como embargo para maduración.

La selección usa solo validación: logística debe mejorar AP y Brier frente al
prior. El test queda para evaluación. No se reajusta con test ni se hace
validación cruzada aleatoria, porque la pregunta es generalización temporal.
Clientes repetidos se permiten: se evalúan nuevas exposiciones, no necesariamente
clientes nunca vistos. El bootstrap Poisson por cliente usa 100 réplicas, semilla
42 e intervalos percentiles del 95%; no mide cambios futuros de distribución.

El reporte JSON incluye ROC-AUC, average precision (AP, área PR escalonada, **no**
integral trapezoidal), Brier, log-loss, calibración, precision y lift del 10% superior,
filas y positivos. Empates en el ranking reciben su contribución esperada, evitando
que el orden de filas fabrique lift para el baseline constante.

## Paso 5. Interpretar el resultado

Los resultados exactos están en `ml/model_cards/product_interest.json`, incluidos
coeficientes, ventanas, versión sklearn, auditoría e intervalos. Hay señal comercial
modesta y una tasa base muy baja; no es evidencia de solvencia. El modelo se conserva
como `production_ready=false`, aunque supere al prior.

Limitación principal: `process_date` no versiona cada actualización de la etiqueta.
La evaluación supone que el resultado final de 30 días ya estaba completo al vencer
la ventana. Sin logs de publicación de etiquetas no puede certificarse un backtest
plenamente histórico. Los metadatos de campaña también se asumen estables.

### Ejecución local verificada

979 681 ejemplos admisibles antes de aplicar los embargos. Entrenamiento: 557 603;
validación: 99 158; test: 248 875. Test contiene 1 216 conversiones (0.4886%).

| Métrica test | Logística | Prior constante |
|---|---:|---:|
| ROC-AUC | 0.6767 | 0.5000 |
| Average precision | 0.00813 | 0.00489 |
| Lift del 10% superior | 1.7719 | 1.0000 |
| Brier | 0.004852 | 0.004863 |

IC 95% bootstrap por cliente: ROC-AUC [0.6675, 0.6889]; AP [0.00744, 0.00922].
Estos resultados corresponden al artefacto y al snapshot local de esta ejecución;
son retrospectivos, no una promesa de desempeño productivo.

## Paso 6. Consultar un cliente

Desde la raíz, con el entorno instalado y la base local existente:

```bash
.venv/bin/python -m ml.training.product_interest
.venv/bin/python -m ml.serving.product_advisor \
  --customer-id ID_AUTORIZADO \
  --product 'Tarjeta Crédito' --channel Email --asof 2025-12-31
.venv/bin/pytest tests/ml/test_product_interest.py
```

El primer comando lee silver sin modificarla y crea:

- `data/models/product_interest.joblib`: modelo local, ignorado por Git.
- `ml/model_cards/product_interest.json`: métricas agregadas versionables, sin clientes.

`joblib` solo debe cargar artefactos propios de confianza; puede ejecutar código al
cargar archivos maliciosos. La consulta es una herramienta interna, no una API pública:
el orquestador debe verificar identidad y autorización antes de llamarla. El estado
actual de consentimiento debe verificarse antes de cualquier contacto comercial.
Este trabajo no envía campañas ni mensajes a clientes.

Respuesta: `interest`, `existing_quotas`, `new_product_quota`. Los límites registrados
solo aparecen cuando la apertura y la última actualización son coherentes y no
superan el corte, el producto está activo en ese snapshot y el importe es finito.
Se mantienen producto, moneda y fecha: no se suman COP, USD y ARS. No se resta
`current_balance` del límite: falta un contrato fiable de disponible y obligaciones.
Ausencia de un registro verificable produce abstención, nunca «cupo cero».

Para **nuevas ofertas**, el componente existente ya expone:

```python
from agent.policies.engine import Politica

# cliente_verificado es un Cliente creado con hechos autorizados, moneda USD
# y fechas verificadas; no con valores generados por el LLM.
decision = Politica.cargar().evaluar(cliente_verificado).a_dict()
```

El asesor nuevo devuelve los requisitos pendientes y la ruta de integración.
No construye `Cliente` desde `customer_360` automáticamente: el aviso 8 de
`docs/12_cambios_para_federico.md` registra ingreso sin moneda y FX posterior al
corte. Usarlo sin corregir esos contratos daría cifras engañosas. Las ofertas del
motor siguen siendo escenarios de la política del hackathon, no ofertas autorizadas
por una entidad. El modelo comercial nunca modifica el límite.

## Paso 7. Datos necesarios para la siguiente versión

1. Solicitudes/interacciones etiquetadas y revisadas: producto, intención explícita,
   negación, fecha, idioma, consentimiento y evidencia; separar deseo de contratación.
2. Historial de tenencia para identificar producto realmente nuevo por cliente;
   altas, cierres y estados versionados.
3. Campañas con vigencia de metadatos, seguimiento completo, publicación del outcome
   y grupo de control. Permitiría estimar efecto incremental, no solo correlación.
4. Cupos aprobados/disponibles con moneda, fecha de vigencia, obligaciones mensuales,
   ingreso verificado y catálogo autorizado de tasas/plazos.
5. Corregir y probar conversiones de moneda y temporalidad antes de conectar ofertas.
6. Evaluación externa temporal, por producto/canal y por clientes nuevos; curvas PR
   y de calibración con soporte suficiente. Umbrales según coste real de contacto,
   no según accuracy. Revisar drift, consentimiento y aprobación humana antes de uso.

## Validación y límites de entrega

Las pruebas nuevas cubren disponibilidad temporal, embargo, separación de test,
serialización, categorías desconocidas, cuotas futuras/no finitas, monedas y fallback.
La suite completa pasa: **149 pruebas, cero skips**. Se reconstruyó localmente
`features_asof.parquet` con `python -m ml.features.build_features` para incluir
las pruebas heredadas. Ruff lint global y formato de archivos nuevos pasan. El
formato global detecta un archivo heredado sin modificar (`test_feature_store.py`).
El hook de commit ejecutó `gitleaks` y pasó la revisión de secretos.
No se descargan otra vez los 5.4 GB de S3: la base y archivos locales ya existen;
Git actualiza código y documentación, no datos ignorados. La calidad/frescura del
snapshot se declara por el corte y no se confunde con la sincronización de Git.
