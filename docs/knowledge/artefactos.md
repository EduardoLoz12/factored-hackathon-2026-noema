# Artefactos publicados

Páginas vivas del proyecto. **Se actualizan republicando a la misma URL** — nunca crear una nueva, o el enlace que ya circula queda obsoleto sin avisar.

| Artefacto | Qué es | URL |
|---|---|---|
| **Feature Store** | Diccionario canónico de las 47 variables candidatas: definición y fórmula, limpieza aplicada, razón conceptual de riesgo de crédito con signo esperado, panel estadístico completo, y a qué modelo va cada una. | https://claude.ai/artifact/RyQRVdkTCQczkYtNLCinyi |
| **Modelos de Noema** | La lógica de cada modelo entrenado: qué predice, con qué variables, con qué corte temporal, métricas reales y veredicto. | https://claude.ai/artifact/SJcpsM3MWDXAeuBXPqwgqj |
| **Política de Elegibilidad** | Cómo se decide si un cliente puede recibir otro producto: el cálculo en cinco pasos, las ocho reglas, los supuestos declarados y por qué es una política y no un modelo. Conceptual, para equipo y jurado. | https://claude.ai/artifact/74seF6uXDstBkkKdn7SKB4 |

## Feature Store — qué fija

Corte as-of **2025-12-31** · cohorte **76 906** clientes · **8 101** morosos a 90 días (10.53 %) · estrato de un solo producto de crédito **48 396**.

El embudo: **307 columnas** en 13 tablas → **47 candidatas**, tras descartar metadatos de ingesta, identificadores y PII, las **6 columnas de fuga** que veta `tests/data/test_feature_contract.py`, texto libre, y las 9 tablas barridas sin señal en F-021.

Cada variable se reporta con **cobertura, separación media-mediana, outliers por IQR, IV global e IV estratificado, d de Cohen global y estratificado, q de Benjamini-Hochberg y VIF**. El contrato de qué se mide y por qué está en [`metodo_estadistico.md`](metodo_estadistico.md).

**Criterio de admisión a ML-03:** IV estratificado ≥ 0.10, |d de Cohen| ≥ 0.20 y signo en la dirección esperada. **Cero de 42 variables numéricas lo cumplen.** El modelo se entrena igual y se reporta que no discrimina; esa evidencia es el entregable.

## Deuda que el diccionario destapó

Dos defectos en `ml/features/build_features.py` que siguen abiertos:

1. **Moneda sin convertir.** `ingreso_declarado` y `limite_total` salen en moneda local: mediana Colombia **9 200 526**, Argentina **798 549**, México **39 475**. Las transaccionales sí están bien —`volumen_usd_180d` da ≈ 6 400 en los tres países, que es el control de que la conversión funciona donde se aplicó—. Factores a USD con la tasa mediana a 30 días del corte: ARS **0.00284668**, COP **0.00025036**, MXN **0.05890935**.
2. **Multicolinealidad severa.** Seis variables con VIF ≥ 10. `n_productos` 61.10 y `n_sucursales` 58.70 correlacionan **0.9913** —cada producto arrastra su sucursal de apertura—; `ticket_max_usd_180d` y `ticket_sd_usd_180d`, **0.9444**. La poda propuesta está en el artefacto.

Y una tercera, ya corregida en el análisis pero pendiente en el código: **`etiqueta_posterior` no es la mora**, es un indicador de cobertura (F-023). El nombre es una trampa; debe pasar a `tiene_observacion_posterior`.

**Evidencia.** `logs/eval/catalogo_feature_store.json` · `logs/eval/catalogo_numericas.csv` · `logs/eval/eda_variables.csv` · `logs/eval/vif.json` · `logs/eval/fx_revalidacion.json` · hallazgos F-021 a F-025 en [`findings.md`](findings.md).

## Política de Elegibilidad — qué fija

**AG-01 y AG-02, cerrados el 30-sep-2026.**

| Pieza | Archivo |
|---|---|
| Política versionada | `agent/policies/eligibility_v1.yaml` |
| Motor determinista | `agent/policies/engine.py` |
| Pruebas — **42 en verde** | `tests/policies/test_eligibility_engine.py` |

**La idea:** no se predice quién incumple, **se calcula cuánto puede pagar**. Cinco pasos: cuota de cada producto vigente → carga mensual comprometida → DTI → margen bajo el tope de política → monto máximo por producto invirtiendo la amortización.

**Umbrales** (los parámetros que el negocio mueve): DTI máximo 40 %, corte duro 60 %, máximo 4 productos de crédito, exposición ≤ 3× ingreso anual, antigüedad mínima 6 meses, cumplimiento mínimo 5 %.

### Dos distinciones de negocio que hay que respetar

Las dos salieron al probar con casos reales y ninguna se ve sin ejecutar el motor.

1. **Una tarjeta no es un préstamo.** Amortizar la línea completa de 30 000 USD a 48 meses daba una cuota de 1 400 y un **DTI de 451 %**. Una tarjeta es revolvente: su obligación mensual es el pago mínimo sobre lo dispuesto. El YAML lo declara por producto con `amortizacion: revolvente` o `cuota_fija`, y `pago_minimo_revolvente: 0.05` es el parámetro.

2. **La cuota de un préstamo no cambia con su edad.** Se estaba calculando sobre el plazo **remanente**: un préstamo de 47 meses de vida con plazo supuesto de 48 quedaba con 1 mes restante y una cuota de 39 611 USD al mes. **La cuota va sobre el plazo TOTAL** — es constante durante toda la vida del préstamo. El remanente solo decide si la obligación sigue viva o ya se liquidó, y en ese caso sale del DTI con su aviso.

### Madurez del producto: qué fuente usar

| Fuente | Cobertura | Incoherentes | Veredicto |
|---|---:|---:|---|
| **Edad al corte** (`opening_date` → corte) | 100 % | 0 % | **la que se usa** |
| `max(transaction_date)` real | 85 % | 0 % | validación cruzada: inactivo si no hay movimientos en 180 días |
| `last_updated` | 100 % | **6.42 %** | no usar — llega a 2026-12-24, reparto uniforme ~13 % por año |
| `last_transaction_date` | 76.5 % | **17.29 %** | no usar (F-028) |

### Lo que la política declara siempre

Que **no evalúa estado de mora**. Es deliberado: el sistema podría pronunciarse usando la columna del dataset y sonaría más completo, pero esa columna no resistió la validación (F-027, F-029, F-030). Mejor decir «esto no lo sé» que dar una cifra que no se sostiene.

### Por qué política y no modelo

Demostrado en F-034: predecir qué producto tiene un cliente desde su perfil da **AUC 0.4973** contra un control de 0.5000, y el límite asignado no depende del score ni del ingreso — la tabla de límite por quintil de score × quintil de ingreso es **plana** (24 533 USD en la esquina peor contra 25 546 en la mejor). No hay decisión de suscripción que aprender. La cadena completa va de **F-027 a F-034**.

### Refinamiento del 30-sep: la posición financiera completa

Eduardo señaló que la capacidad no está solo en el crédito: lo que el cliente tiene en cuentas e inversiones es capacidad real. En suscripción eso son las **reservas**, y entran de dos formas.

**Los activos y su cómputo** (`current_balance` tiene 100 % de cobertura en todos los tipos):

| Producto | Saldo mediano USD | Cómputo | Clientes |
|---|---:|---:|---:|
| Cuenta Ahorro | 4 989 | 100 % | 113 147 |
| Cuenta Corriente | 2 500 | 100 % | 94 265 |
| Inversión | 14 885 | **70 %** (descuento por liquidación) | 5 526 |

**Como requisito:** hipotecario exige reservas por 3 meses de su cuota, personal 1, tarjeta ninguna.
**Como factor compensatorio:** si las reservas cubren ≥ 6 meses de las cuotas actuales, el tope de DTI sube del 40 al 45 %. Exige carga **y** reservas reales — con cero deuda no hay nada que compensar. **No** salta el corte duro del 60 %.

**Y la tarjeta pesa por lo dispuesto, no por la línea.** El saldo mediano de tarjeta es **1 501 USD** contra una línea de **25 536** — utilización del 6 %. Asumir la línea agotada sobreestimaba la obligación **diecisiete veces**: 1 277 USD/mes contra 75 reales. Ahora se usa `saldo_usd`; cuando no se conoce se asume la línea completa (criterio conservador), y la línea **no dispuesta** se computa al 10 % porque es deuda que el cliente puede tomar mañana.

**Nota sobre `current_balance`:** está vetada como **variable de modelo** (fuga — un producto en default arrastra un saldo que codifica el desenlace). Describir la posición financiera al corte para un cálculo de política es otro uso y no es fuga: no se predice nada, se mide lo que hay.

**Bug encontrado y corregido:** con carga cero, `reservas / carga` daba infinito y el factor compensatorio se activaba sin reservas. Ahora exige `carga > 0` y `reservas > 0`.

Pruebas: **58 en verde** (16 nuevas en `TestPosicionFinanciera`).

**Pendiente, aplazado por decisión de Eduardo:** ofrecer el mismo producto a varios plazos (120 y 240 meses en hipotecario, con cuotas distintas). Añade complejidad al catálogo y a la conversación; se hará después.
