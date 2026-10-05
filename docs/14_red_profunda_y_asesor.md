# Red profunda y asesor analítico — ML-12

## Resultado

Existe una red neuronal entrenada, no solo un diseño: MLP de tres capas ocultas
32 → 16 → 8, con 14 entradas codificadas y una salida sigmoide. Se ejecuta en CPU
con `sklearn.neural_network.MLPClassifier`, Adam, entropía cruzada y regularización
L2. No necesita PyTorch ni GPU para esta arquitectura pequeña. No es un LLM ni
un chatbot; es un modelo tabular integrado a una herramienta analítica por cliente.

El asesor consulta datos locales, compara la red con el modelo recomendado,
ordena productos por propensión comercial, consulta cupos registrados y, **si el
llamador aporta evidencia financiera verificada**, ejecuta el motor de Eduardo.
Sin esa evidencia, informa abstención para nuevas ofertas. No genera cifras con
texto libre ni usa probabilidad comercial como aprobación de crédito.

## Qué se incorporó del trabajo de Eduardo

| Fuente revisada | Uso concreto |
|---|---|
| `ml/features/build_features.py` y sus pruebas | Se preservan contratos as-of; no se cruza un snapshot de diciembre con campañas de años anteriores |
| `ml/training/baseline_logreg.py` y F-017/F-027–F-034 | La red no usa mora sintética como objetivo de elegibilidad |
| `agent/policies/engine.py` y YAML v1 | Cálculo de cuota, DTI, margen y monto por producto reutilizado directamente |
| `docs/12_cambios_para_federico.md` | No se conecta automáticamente ingreso crudo de customer_360 ni valoración FX futura |
| HTML «Política de Elegibilidad», v1.0, 30-sep | Separación interés/capacidad, cuotas sobre plazo original, revolvente, abstención y capacidad que solo restringe |
| PDF «Bronze contra Silver», 20 páginas, 29-sep | Silver como fuente, nulos estructurales no imputados, sucursal inválida excluida, no aprender mora ni agregar monedas |

Los documentos originales no se publican en Git; incluyen un ejemplo de cliente.
Se registran su título, fecha, conclusiones pertinentes y discrepancias, sin copiar
identificadores ni importes personales del expediente.

### Diferencias que no se deben ocultar

El HTML dice abstenerse si falta el límite de un producto. El motor actual omite
la obligación incompleta y avisa en `_carga`; el adaptador nuevo se abstiene antes
de llamarlo si falta límite o tasa. Es una protección del contrato del asesor,
no una modificación del motor de Eduardo.

El HTML describe pago mínimo sobre toda la línea. El código más reciente permite
saldo dispuesto y estrés de línea no dispuesta, además de reservas. Se conserva
esa política actual y versionada; no se copian cifras ilustrativas a pesos de la red.
El adaptador devuelve exactamente la decisión del motor para entradas válidas.

El PDF menciona usar mora observada en política; el HTML posterior y el motor
actual explicitan que no se determina mora. Se conserva el comportamiento actual.
El PDF muestra preservación de distribuciones y evidencia contra una etiqueta de
riesgo útil; no prueba ausencia universal de fuga, MCAR o independencia. Su frase
«una centésima del umbral» no coincide con KS 0.00203 frente a 0.01. No se heredan
esas afirmaciones como garantías estadísticas.

## Datos y entrenamiento

Se reutilizan los 979 681 ejemplos admisibles y la lista cerrada de cuatro variables
originales: producto, canal, mes y exposiciones previas disponibles. No se añaden
columnas solo porque existan: perfiles financieros finales, sucursales inválidas,
días de mora y datos posteriores al envío no tienen un contrato temporal adecuado
para esta etiqueta. `FEATURES` selecciona las únicas entradas antes del preprocessing.
Los nulos estructurales de crédito no entran en imputación porque esas columnas no
son entradas de la red. En política, faltantes financieros no se imputan.

- Entrenamiento: 557 603 exposiciones, anteriores a diciembre de 2024.
- Validación: 99 158, enero–marzo de 2025; embargo antes de test.
- Test: 248 875, mayo–noviembre de 2025 con 30 días completos antes del corte.
- Preprocessing ajustado exclusivamente en train y serializado con la red.
- Máximo 20 épocas; checkpoint por menor log-loss de validación, paciencia 4.
- Red elegida en época 14. No hay split aleatorio interno para early stopping.
- Semilla 42; batch 1024; tasa Adam 0.001; L2 alpha 0.01; CPU limitada a 2 hilos.

La comparación incluye logística y prior reentrenados sobre las mismas filas. La
recomendación usa solo validación: mejorar AP y Brier del prior, luego minimizar
log-loss. La red siempre queda disponible como `deep_mlp`, aunque no gane.
El test se había reportado para logística en ML-11: se reutiliza como benchmark,
no se presenta como un nuevo estudio externo independiente. No se escogieron
arquitectura ni hiperparámetros iterando sobre ese test.

## Resultados de esta ejecución

| Test | Red 32–16–8 | Logística | Prior |
|---|---:|---:|---:|
| ROC-AUC | 0.67394 | 0.67672 | 0.50000 |
| Average precision | 0.008142 | 0.008133 | 0.004886 |
| Log-loss | 0.029298 | 0.029242 | 0.030937 |
| Lift del 10% superior | 1.85734 | 1.77191 | 1.00000 |

La logística gana en validación y sigue recomendada. La ventaja de lift de la red
no demuestra superioridad global ni causal. IC bootstrap por cliente del 95% para
AUC de la red: [0.66548, 0.68577]; para AP: [0.007480, 0.008966]. Se usan 100
réplicas Poisson, semilla 42; no cubren variación entre semillas ni drift futuro.
El reporte completo conserva curvas de aprendizaje y calibración, métricas por
partición, arquitectura y supuestos en `ml/model_cards/deep_interest.json`.

## Cómo ejecutar la IA de análisis

```bash
python -m ml.training.deep_interest
python -m ml.serving.client_analysis --customer-id ID_AUTORIZADO --channel Email
```

El modelo queda local en `data/models/deep_interest.joblib` (ignorado por Git).
La consulta necesita la base silver local y acceso autorizado al cliente. No ofrece
una API pública, interfaz de chat, autenticación ni envío de campañas. Es el
componente que el orquestador del equipo puede llamar después de autenticar.
No se permite consultar con un corte anterior a la selección del modelo.

Devuelve:

- `product_analysis`: probabilidades de la red y del modelo recomendado por producto.
- `existing_quotas`: límites documentados por producto y moneda, con fecha.
- `new_product_quota`: abstención o escenario del motor de Eduardo con evidencia.
- `evidence` y `explanation`: historial utilizado, método y límites de interpretación.

Ranking descriptivo, no «next best action» causal: la asignación de campañas puede
estar sesgada y la tenencia histórica no permite afirmar que el producto sea nuevo.
Debe confirmarse la intención con el cliente. Antes de contacto, validar consentimiento.

### Integración con hechos verificados

```python
from datetime import date
from ml.serving.client_analysis import VerifiedPolicyInput, analyze_client

# cliente_verificado: Cliente de Eduardo, creado por la capa autorizada con USD,
# fechas, ingreso y obligaciones completas. No construido por el modelo neuronal.
evidence = VerifiedPolicyInput(
    client=cliente_verificado,
    asof=date(2025, 12, 31),
    evidence_ref="referencia_interna_del_expediente",
    obligations_complete=True,
)
result = analyze_client(connection, cliente_verificado.customer_id, verified=evidence)
```

`VerifiedPolicyInput` es un contrato del llamador, no prueba por sí mismo la
verificación. El adaptador comprueba coincidencia cliente/corte, referencia no vacía,
completitud declarada, valores finitos/no negativos, fechas y términos de obligaciones.
Sin ingresos válidos el motor se abstiene. El estimador ML-04 existente puede aportar
`capacidad_estimada_usd` una vez convertida y verificada; solo restringe el margen.
No se convierte automáticamente la estimación en moneda local a USD sin FX adecuado.
La política devuelve escenarios del hackathon; `is_bank_approval=false` es permanente.

## Validación y trabajo pendiente

Pruebas: arquitectura real, serialización, independencia de etiquetas de test,
paridad con el motor de Eduardo, NaN/infinito, fechas/identidad, obligación incompleta,
capacidad restrictiva, cliente desconocido y análisis integrado. Los datos sintéticos
de esas pruebas no se mezclan con entrenamiento ni con el reporte de desempeño.

Antes de producción: intención explícita etiquetada, snapshots versionados de
campañas/outcomes/tenencia, ingreso y obligaciones verificadas, evaluación por
cohortes y semillas, validación temporal externa y revisión de política. Una red
más grande no corrige esas ausencias.

Referencia de implementación: [scikit-learn, redes neuronales supervisadas](https://scikit-learn.org/stable/modules/neural_networks_supervised.html).
Fundamento: [Aaron Wang, Data Science Cheatsheet](https://github.com/aaronwangy/Data-Science-Cheatsheet),
redes neuronales, regularización y evaluación de clasificación.
