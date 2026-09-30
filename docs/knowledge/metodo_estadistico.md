# Método estadístico y de limpieza — contrato del proyecto

Destilado del curso de Navarra (Preparación de Datos, Contraste de Hipótesis, Regresión Lineal Multivariable) y convertido en reglas ejecutables para este repo. **Antes de afirmar que una variable sirve o no sirve, se pasa por esta lista.**

Origen: material de clase de Eduardo Lozada — Juan José Fernández Tébar (Preparación de Datos), Elena Martín de Diego (Contraste de Hipótesis), Montserrat-Ana Miranda Galcerán (Regresión Lineal Multivariable). Instituto DATAI, Universidad de Navarra, curso 2023-2024.

---

## 0 · La frase que ordena todo

> «Torture the data, and it will confess to anything.» — Ronald Coase

Y su corolario operativo, de Andrew Ng: el 99 % de la investigación se centra en el modelo, cuando **subir la calidad del dato mueve más la aguja que un modelo más complejo**.

---

## 1 · Limpieza — lo que se comprueba antes de mirar ninguna métrica

### Calidad de dato ≠ ingeniería de variables
Siete comprobaciones, en este orden:

| # | Comprobación | Qué valida |
|---|---|---|
| 1 | **Sintáctica** | El formato: una fecha tiene forma de fecha, un teléfono solo dígitos |
| 2 | **Semántica** | El significado: una fecha de nacimiento no está en el futuro |
| 3 | **Integridad** | Están los campos obligatorios |
| 4 | **Validez** | El valor es admisible (email bien formado, Luhn en tarjeta) |
| 5 | **Coherencia** | El mismo dato coincide entre sistemas |
| 6 | **Exactitud** | El valor corresponde a la realidad |
| 7 | **Unicidad** | No hay duplicados |

**La 5 es la que este proyecto falló** (ver `F-025`): mezclar COP, ARS y MXN en una misma columna pasa las seis restantes y reprueba la coherencia.

### Higiene de columnas
- Columnas de **valor único** → eliminar.
- Columnas con **muy pocos valores** → considerar.
- Columnas de **varianza baja** → eliminar.
- **Filas duplicadas** → identificar y eliminar **antes** de partir train/test, o el mismo registro aparece en ambos lados.

### Outliers
Un outlier es una observación distante del resto. **No hay definición matemática rígida.** Dos métodos, y la elección depende de la distribución:

- **3 sigma** — solo válido si la distribución es gaussiana.
- **IQR** (`Q1 − 1.5·IQR`, `Q3 + 1.5·IQR`) — para distribuciones no gaussianas. **Este es el que aplica aquí**: las 26 variables del feature store fallan la prueba de normalidad.

**Regla de decisión:** si el outlier **no** viene de un error de construcción de la base, **eliminarlo no es la solución**. Se le quita peso:
- **Media recortada** (*trimming*): se excluye el 10 % superior e inferior.
- **Media winsorizada**: se sustituyen los extremos por sus inmediatos anteriores.
- **Estandarización robusta**: calcular media y desviación ignorando los extremos.
- **Transformación logarítmica** para asimetría fuerte.

**El diagnóstico barato:** comparar **media contra mediana**. El ejemplo de clase: `10,10,11,12,12,13,14,15,15,15,16,18,19` da media 13.85; cambiar el último por 200 la lleva a 27.77. **Un solo valor mueve la media el doble.** Si media y mediana difieren mucho, los extremos mandan.

### Nulos
- `NA` no disponible · `NULL` nulo · `Inf` división por cero · `NaN` no numérico.
- Ojo con los nulos **disfrazados**: un `-1` en un campo que solo puede ser positivo, un `0` donde el cero es imposible.
- **Imputar por media/cero altera los estadísticos de resumen, modifica la distribución e infla la presencia de un valor.** Elegir según la forma: media si es normal, **mediana si hay asimetría**, moda para categóricas, o un modelo (KNN, MissForest).
- **Un nulo es información.** En este repo se acompaña de su bandera (`credit_score_faltante`, `ingreso_faltante`).

---

## 2 · Fuga de datos

Fuga es usar, para construir el modelo, información que no estaría disponible en el momento de predecir. Tres formas, las tres relevantes aquí:

1. **Partir al azar datos con estructura temporal.** En series temporales los datos están correlacionados en el tiempo: la partición va **por tiempo**, no aleatoria.
2. **Imputar o escalar con estadísticos calculados sobre el conjunto completo.** Media, mediana, `fit_transform`: solo del conjunto de entrenamiento. `transform` en test, nunca `fit`.
3. **No quitar duplicados antes de partir.**

> **Deuda declarada de este proyecto:** el binning de WoE/IV para `F-024` se calculó sobre la cohorte completa, no solo sobre entrenamiento. Es fuga de procedimiento. No invalida la conclusión —que es de ausencia de señal, y la fuga solo puede inflar, nunca deprimir— pero si alguna variable hubiera pasado el umbral habría que recalcularla particionando primero.

---

## 3 · Selección de variables

### Por qué reducir
Mejor rendimiento · menos sobreajuste · entrenamiento más rápido · **más explicabilidad** · menos deuda técnica. Y la clave para este proyecto: **aplicar conocimiento experto del negocio es lo que decide qué variable entra**, no un barrido.

### Tres familias
| Familia | Cómo | Ejemplos |
|---|---|---|
| **Filtro** | Estadística pura, sin modelo. Rápido. | Correlación, χ², información mutua, **IV/WoE** |
| **Wrapper** | Busca subconjuntos evaluando un modelo. Caro. | Forward Selection, Backward Elimination, RFE |
| **Intrínseco** | El algoritmo selecciona al entrenar. | Árboles, LASSO |

**No existe el mejor método de importancia de variables.** Se descubre por experimentación sistemática para el problema concreto.

### Correlación — cuál usar
- **Pearson**: dos variables cuantitativas, relación lineal, distribución normal.
- **Kendall**: distribuciones distintas de la normal.
- **Spearman**: **no asume nada sobre la distribución**, adecuada para datos ordinales. *Es la que aplica aquí*, y la que se usó para medir la monotonía del `credit_score` por decil.

### Multicolinealidad
Principio de parsimonia de Ockham: entre dos explicaciones, la más simple completa.

- **VIF** = `1 / (1 − R²ₖ)`, con `R²ₖ` de regresar `xₖ` contra el resto.
- **VIF ≥ 5** → moderada (R² = 0.8) · **VIF ≥ 10** → severa (R² = 0.9).
- Limitación: el VIF dice *qué* variable es colineal, no *cuál* eliminar.
- Dos salidas: eliminar la de VIF más alto, o **reagrupar** las que responden al mismo concepto sumándolas.
- **Si el VIF sale `NaN`, la matriz es singular: hay colinealidad perfecta.** Buscar el par con `|r| > 0.999` — es la misma variable reescalada. *Pasó aquí: `comp_pagos_n` y `comp_pagos_por_mes` eran la misma columna dividida entre 6.*

---

## 4 · Contraste de hipótesis

### El marco
- **H₀**: el efecto no existe; las diferencias observadas son azar. **Es la que se contrasta.**
- **H₁**: existe algún efecto distinto de cero.
- **Error Tipo I** (α): rechazar H₀ siendo verdadera. **Error Tipo II** (β): aceptarla siendo falsa.
- **Potencia = 1 − β**: capacidad de detectar un efecto que sí existe.
- Hay **compromiso entre α y β**: bajar uno sube el otro.

### El p-valor, y lo que NO es
El p-valor es la probabilidad de observar una diferencia **al menos tan extrema** como la observada, **si H₀ fuera cierta**.

Tres advertencias que el curso subraya y que aquí importan:
1. **Un test no significativo no demuestra que H₀ sea cierta**, solo que no hay evidencia para rechazarla.
2. **El p-valor no mide la fuerza de la asociación** ni la causalidad.
3. **Lo que más influye en el p-valor es el tamaño de muestra.** Muestras grandes rechazan H₀ con facilidad.

### Paramétrico o no paramétrico
Las pruebas paramétricas exigen **normalidad** y **homocedasticidad**. Usarlas sobre datos que no las cumplen **da resultados imprecisos**.

- Normalidad: descriptivos (media vs mediana, asimetría, curtosis), Q-Q plot, **Shapiro-Wilk** (n ≤ 50, y no pasa de 5000), **Kolmogorov-Smirnov**. Cuidado: con n grande, desviaciones mínimas rechazan normalidad. Funcionan mejor entre n = 20 y 200.
- Homocedasticidad: **Levene** o **Bartlett**. Con n grande, diferencias pequeñas salen significativas.
- Sin normalidad → **Mann-Whitney** (independientes) o **Wilcoxon** (relacionadas). Dan p-valor pero **normalmente no dan intervalo de confianza**, y tienen menos potencia.

### Comparaciones múltiples
Con α = 0.05 y tres comparaciones, la probabilidad de al menos un error Tipo I sube a **14.3 %**. Con 5 poblaciones y 10 comparaciones, al **40 %**.

Corregir siempre: **Bonferroni** (α/nº comparaciones, muy conservador), **Tukey**, o **Benjamini-Hochberg** (controla la tasa de falsos descubrimientos; es la usada en este repo por ser menos brutal con 26 pruebas).

---

## 5 · Tamaño del efecto — la regla que salva este proyecto

> **Significación estadística ≠ significación práctica.**

Con muestra suficiente, **una diferencia irrelevante sale significativa**. Subir la eficacia un 0.1 % es significativo con miles de sujetos y no sirve para nada.

**d de Cohen** — diferencia estandarizada de medias:

| d | Magnitud | Interpretación |
|---|---|---|
| 0.2 | pequeño | El sujeto medio del grupo mayor supera al 58 % del otro |
| 0.5 | medio | Supera al 69 % |
| 0.8 | grande | Supera al 79 % |

Variantes: **Delta de Glass** si las desviaciones de los dos grupos son muy distintas; **g de Hedges** si las muestras son pequeñas.

**Orden obligatorio del contraste:**
1. Descartar el azar (¿es estadísticamente significativo?)
2. **Medir la magnitud (tamaño del efecto).**

Saltarse el paso 2 con n = 76 906 produce el error que este repo cometió y corrigió en `F-025`.

### Potencia y n
`n_G ≥ 2σ²(Z_α/2 + Z_β)² / (μ₂ − μ₁)²`

Para potencia 80 % y α = 0.05: detectar **d = 0.2** exige **392 por grupo**; **d = 0.8**, solo **25**. A la inversa, con n muy grande el **d mínimo detectable** se vuelve minúsculo — y ese número hay que reportarlo, porque explica los p-valores.

---

## 6 · Métricas

### Regresión
- **R²**: proporción de varianza explicada. **Se infla al añadir variables aunque sean inútiles** → usar **R² ajustado**. Si R² < 0, el modelo es peor que predecir la media.
- **MAE**: en unidades de la variable, todos los errores pesan igual.
- **RMSE**: penaliza más los errores grandes. **RMSE ≥ MAE siempre**, y crece con el tamaño de muestra → **no comparar RMSE entre muestras de distinto tamaño**. El cociente RMSE/MAE mide cuánto mandan los extremos.

### Clasificación
- **Accuracy engaña con clases desbalanceadas**: 99 positivos y 1 negativo, predecir todo positivo da 99 %.
- **Recall** — de todos los positivos reales, cuántos detecto. **Precisión** — de los que llamo positivos, cuántos acierto. **F1** — equilibra ambos.
- **AUC** para comparar modelos.

### Baseline obligatorio
Antes de celebrar cualquier mejora:
- Clasificación: acierto de predecir siempre la clase mayoritaria (`DummyClassifier`).
- Regresión: predecir siempre la media (`DummyRegressor`, R² ≈ 0).
- **En este repo se va más lejos:** la referencia es **la misma corrida con la etiqueta permutada al azar**. Si el modelo real no le gana a su propio ruido, no hay señal.

---

## 7 · La lista que se corre antes de afirmar nada

```
 1. ¿Columnas de valor único, varianza nula, duplicados?
 2. ¿Cuánto falta por variable, y de qué tipo es el nulo?
 3. ¿Coherencia de unidades? (moneda, escala, zona horaria)
 4. Media vs mediana vs moda. ¿Cuánto se separan?
 5. Outliers por IQR y por 3-sigma. ¿Coinciden?
 6. Normalidad → decide paramétrico o no paramétrico.
 7. VIF. ¿NaN? → hay colinealidad perfecta, buscar el par.
 8. IV/WoE o el filtro que corresponda.
 9. p-valor con corrección por multiplicidad.
10. TAMAÑO DEL EFECTO. Sin esto, el paso 9 no dice nada.
11. d mínimo detectable con esta n.
12. Baseline: mayoritaria, media, y etiqueta barajada.
13. ¿Hay fuga? Temporal, de imputación, de duplicados.
14. Mirar el gráfico. Anscombe: cuatro nubes distintas, mismos estadísticos.
15. Si el AUC sale alto: quitar el bloque de variables más obvio y volver a medir.
16. Antes de aceptar una columna como `y`: exigirle el cortejo de fenómenos que
    la acompañarían si fuera real.
```

### El paso 15, por qué está

`product_status` como objetivo dio **AUC 0.9005** con el control barajado en 0.5017. Pasa cualquier validación estándar. Al quitar las variables transaccionales cayó a **0.4960**: los productos no activos tienen cero transacciones por construcción, así que el modelo medía «no operó», no riesgo. **Cuando un modelo separa bien, quitar el bloque de variables más obvio y repetir.** Si el AUC se desploma, lo que había era una relación estructural.

### El paso 16, por qué está

Una columna que se llama `days_past_due` no es mora por llamarse así. En una cartera real la mora arrastra un cortejo observable: estado del producto coherente, saldo pendiente, línea agotada, ausencia de pagos, contactos de cobranza, producto bloqueado, y una antigüedad compatible. **Si ninguno concuerda, la columna es una etiqueta pegada.** Los siete cruces están en F-027; el 87.2 % de los productos de menos de 30 días arrastra más días de mora que días de existencia.

Esta comprobación va **antes** que toda la estadística: si la variable dependiente no existe, ningún IV, ningún d de Cohen y ningún AUC significan nada.

---

## 8 · Las preguntas de cierre

Del resumen mental de proyectos de datos, las dos que este repo tuvo que responder de verdad:

> **5. ¿Los datos recopilados son representativos del problema que se va a resolver?**
> **8. ¿El modelo utilizado realmente responde a la pregunta inicial, o es necesario ajustarlo?**

Aquí la respuesta a la 5 fue **no** —la etiqueta es un sorteo sintético— y por eso la 8 se resolvió cambiando dónde se apoya el sistema: la decisión la toma `eligibility_v1.yaml` sobre hechos verificables, no un modelo.

15. Si el objetivo se construye contando un subconjunto de eventos, comprobar
    si el total de eventos esta acotado. Si lo esta, el objetivo es el
    complemento de lo que no se conto, y cualquier variable de composicion lo
    predice sin saber nada. Ver F-033: `pagos = total - no_pagos`.

17. Al filtrar una capa derivada por un valor de enum, comprobar que ese valor
    existe EN ESA CAPA, no en la de origen. Silver traduce `transaction_type`
    al español y deja `transaction_status` en inglés; un filtro por el valor de
    bronze devuelve cero filas sin avisar. Ver F-035.
18. Un agregado que sale EXACTAMENTE cero es sospechoso del filtro, no un
    hallazgo. Los ceros redondos son de código; un fenómeno real deja cola.

19. El contrato temporal cubre DOS cosas: cuándo se observó el hecho, y con qué
    fecha se valoró el importe. Una conversión de moneda es una observación más
    y su fecha tiene que respetar el corte. Ver F-036: customer_360 valora con
    una cotización cinco meses posterior al corte.
