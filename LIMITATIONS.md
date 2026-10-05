# Limitaciones

El kickoff pide ser honesto sobre lo que falta. Esta página se escribe desde el día 1 y se cerró el 5 de octubre de 2026, con lo que realmente faltó.

## Datos

1. **El dataset no tiene portugués.** Las 200 000 transcripciones están en español al 100 %, con dos plantillas y un solo intent. El set de evaluación en PT-BR es **generado y traducido por nosotros**, y sus métricas se reportan por separado. La diversidad lingüística de esos casos está acotada por la de las plantillas originales.
2. **No existe verdad de campo sobre aprobación crediticia.** El dataset no registra decisiones históricas de aprobación o rechazo. La política de elegibilidad es **declarada por nosotros** — razonable y documentada, pero no observada. Medimos consistencia con esa política, no acierto contra lo que el banco hizo.
3. **La mora es una fotografía sin fecha de medición.** El corte temporal usado para construir variables es un supuesto declarado (ADR-0004), no un hecho del dataset.
4. **El diccionario y el dato no coinciden.** Conteos de filas, enums, rangos, duplicados y nulos difieren de lo documentado (ver `docs/01_data_audit.md`). Trabajamos contra el dato observado, pero eso significa que cualquier comparación con otro equipo que haya confiado en el diccionario no será directa.
5. **MXN no existe en `products`** pese a que la mitad de los clientes son mexicanos. Las conversiones se hacen contra las monedas realmente presentes.
6. **El dataset es internamente incoherente en el tiempo.** El 18.7 % de las transacciones ocurre antes de que exista la cuenta que las contiene — 83.31 % en los productos de menos de un año contra 0.00 % en los de más de cinco (F-031). Es la causa raíz de que ninguna etiqueta sea aprendible, y no se puede arreglar desde nuestro lado.

## Modelos

7. **Ninguna columna del dataset es un objetivo de riesgo aprendible**, probado por cinco vías (`ML-03`, F-017 a F-034). `ML-03` se entrega como el informe de esa evidencia, no como un AUC. La elegibilidad se calcula con una política versionada, no se predice.
8. **`ML-09` no existe: no hay estimador de capacidad observada.** El sistema decide sin él, lo declara al cliente y recorta el margen al 80 % sin ofrecer el plazo más largo. Hay una prueba puesta para que, el día que exista, un fallo de carga **bloquee** en vez de aprobar.
9. **`ML-04` se reporta como estimador sobre datos sintéticos.** Su ingeniería está bien; el dato debajo no mide un fenómeno. Se abstiene en el 94 % de los casos, y esa abstención es el resultado honesto.
10. **El único objetivo con señal no es el riesgo, es la respuesta comercial.** `ML-11` da AUC 0.677 con prevalencia del 0.49 %. La red profunda de `ML-13` **no le gana** a la logística (0.656 y 0.649 contra 0.657), y el modelo recomendado es el lineal. Ninguno de los dos decide nada: no aprueban crédito ni disparan contacto. Siguen marcados `production_ready: false` por falta de snapshots versionados de etiquetas.
11. **Menos variables por prevención de fuga.** Excluimos deliberadamente columnas que reflejan el desenlace, a costa de métricas más modestas. Preferimos un AUC creíble a uno inflado.
12. **Sin reentrenamiento continuo ni monitoreo de drift.** Se reporta estabilidad sobre el período retenido, nada más.

## Evaluación

13. **El conjunto retenido son 154 casos, no miles.** Las diferencias pequeñas entre brazos no son significativas con esa n. Lo que reportamos como resultado son las diferencias grandes.
14. **El detector de inyección no generaliza.** 100 % sobre su propio corpus; 42 %, 91.7 % y 28.6 % en rondas ciegas sucesivas. La garantía del sistema no es la detección sino la **contención** —el texto del cliente se canaliza como dato— y eso se probó sobre los 10 textos que el detector no ve. El detector quedó declarado como observabilidad, no como control.
15. **Los 20 casos adversariales son nuestros.** Un atacante con tiempo encontrará formas que no están en esa lista.
16. **La prosa del cliente la escribe un LLM y eso cuesta dinero y tiempo.** `make eval` sin `ANTHROPIC_API_KEY` corre igual, pero el brazo `baseline` queda marcado `no_corrido` en vez de simulado: un baseline inventado sería peor que no tenerlo.

## Sistema

17. **Alcance deliberadamente estrecho:** un solo workflow de los cuatro permitidos. Los otros tres no están cubiertos.
18. **No hay integración con un core bancario real.** Las escrituras van a nuestra propia base; la relectura posterior es real contra ese store, no contra un sistema bancario.
19. **Sin autenticación biométrica ni segundo factor.** La puerta de identidad usa tres datos del cliente, que es lo que el dataset permite. El teléfono **no** es uno de ellos: el 48.4 % de los clientes tiene prefijo de otro país (F-004).
20. **El límite de tasa vive en memoria del proceso.** Con más de una instancia el límite es por instancia. Para la demostración es correcto; en producción iría en un almacén compartido.
21. **La consola del asesor está abierta en la demostración.** En producción iría detrás del inicio de sesión del asesor. Por eso devuelve el identificador del cliente **hasheado** y el listado no incluye el contenido de los expedientes.
22. **La traza por turno que alimenta el panel vive en memoria.** El almacén auditable son los archivos de `logs/traces/`; el panel es una vista de demostración y se pierde al reiniciar.
23. **Sin alta disponibilidad.** Una sola región, una sola instancia. No hay plan de recuperación ante desastre.
24. **Sin cumplimiento regulatorio formal.** No hay evaluación de sesgo por género o edad con umbrales regulatorios, ni revisión legal de la política de crédito.

## Lo que planeamos y no entregamos

25. **El espejo en Databricks quedó sin verificar (`DAT-13`).** Hay código de subida a un Unity Catalog Volume y un perfil de dbt para correr los mismos modelos allí, pero nunca se ejecutó contra un workspace real: no tuvimos `DATABRICKS_HOST` ni `DATABRICKS_TOKEN`. La ruta canónica del proyecto es DuckDB y eso no cambió — un juez reproduce todo con un comando y sin cuenta de nadie (`ADR-0002`). Lo decimos porque el código está en el repo y sería deshonesto dejarlo pasar por verificado. Lo mismo vale para el export a Postgres (`DAT-14`).
26. **La interfaz no es Next.js (`UI-01`).** Es una página de una sola pieza servida por la propia API. Fue la regla de corte del día 6, aplicada tarde. Se gana cero dependencias nuevas, un solo proceso y nada de CORS que abrir; se pierde el componente de interfaz que el plan prometía.
27. **`noema_gold.product_policy` está vacía.** La tabla existe y sus columnas están en NULL. El catálogo que el sistema usa de verdad es `agent/policies/eligibility_v1.yaml`, que sí está versionado y probado; la tabla gold no se publica en `/analytics` precisamente por esto.
28. **Dos días del plan no produjeron trabajo.** El 3 y el 4 de octubre no tienen commits. La evaluación, la API y la interfaz se construyeron el día del cierre, y eso explica que `ML-05` a `ML-10` —calibración, SHAP, MLflow, estabilidad por país— se quedaran fuera. No fue una decisión de alcance: fue tiempo perdido, y preferimos escribirlo que disimularlo.

## Qué costaría hacerlo real

| Falta | Esfuerzo estimado |
|---|---|
| Portugués con datos reales | Corpus etiquetado de clientes BR — semanas, no días |
| Verdad de campo de aprobaciones | Acceso al histórico de decisiones del banco |
| Un dataset temporalmente coherente | Regenerarlo desde el origen; no es un arreglo de limpieza |
| Integración con core bancario | Contratos de API, ambiente de pruebas, certificación |
| Espejo en Databricks verificado | Una cuenta y un token; la subida y el perfil de dbt ya están escritos |
| Monitoreo de drift y reentrenamiento | Pipeline programado + alertas + gobierno de modelos |
| Evaluación de sesgo regulatorio | Métricas de equidad por grupo protegido y revisión legal |
| Alta disponibilidad | Multi-instancia, réplicas de base de datos, pruebas de carga |
