# ADR-0006 · La elegibilidad la decide una política, no un modelo

**Fecha:** 2026-09-30 · **Estado:** aceptado, con evidencia reproducible en `docs/knowledge/findings.md` (F-023 a F-034).

## Contexto

ADR-0005 dejó dos huecos: la política versionada no existía y `product_policy` quedó con `policy_ready=false` esperando que Eduardo aportara mínimos de score, montos y plazos. Al ir a escribirla se hizo primero la pregunta que faltaba: ¿el dataset permite aprender la decisión de suscripción, en lugar de que alguien la escriba a mano?

La respuesta es no, y está probada por cinco vías independientes.

## Lo que se comprobó

**La variable objetivo no existe.** `days_past_due` no concuerda con ninguno de los siete fenómenos que acompañan la mora en una cartera real: un producto bloqueado tiene la misma tasa de mora que uno activo (7.76 % contra 7.48 %), la utilización de línea de un moroso a 90 días es 0.3083 contra 0.2902 del cliente al día, el 87.2 % de los productos de menos de 30 días arrastra más días de mora que días de existencia, el moroso opera con la misma frecuencia que el sano, **no existe categoría de cobranza en el centro de llamadas**, y los tres grupos registran 0.43 pagos en 180 días. Detalle en F-027.

**Las alternativas tampoco.** `product_status` como objetivo daba AUC 0.9005 con el control barajado en 0.5017 — y era tautología: los productos no activos tienen **cero transacciones por construcción**, así que el modelo medía «no operó». Sin las variables transaccionales, 0.4960. `last_transaction_date` coincide con la última transacción real en 427 de 305 721 productos. F-028.

**No se puede construir.** Una tarjeta con 45 meses de vida registra 1.29 pagos totales. De 160 054 productos con historial, **cero tienen calendario de pagos regular**. Y todos los montos del dataset son uniformes: las seis clases de transacción coinciden con `(máx−mín)/√12` hasta el segundo decimal y dan curtosis −1.2. Un pago es Uniforme(50, 2000) USD, independiente del saldo, del límite y de la tasa. Sin fecha de vencimiento no hay atraso. F-029, F-030.

**La causa raíz.** Las transacciones se generaron sobre una ventana fija (2023-06 a 2026-06) y los productos sobre otra, uniforme entre 2018 y 2026, y se unieron por `product_id` sin comprobar coherencia temporal. El 18.7 % de las transacciones ocurre antes de que exista la cuenta que las contiene: **83.31 % en los productos de menos de un año contra 0.00 % en los de más de cinco**. F-031.

**Y la elegibilidad tampoco es aprendible.** Predecir qué producto tiene un cliente desde su perfil da AUC 0.4973 contra un control de 0.5000. El límite asignado no depende del cliente: la tabla de límite mediano por quintil de score cruzado con quintil de ingreso es **plana** —24 533 USD en la esquina peor contra 25 546 en la mejor—, y un modelo con atributos del cliente más el tipo de producto (R² 0.2441) es **peor** que usar solo el tipo (R² 0.2620). F-034.

## Decisión

**1 · ML-03 deja de ser un modelo de riesgo y pasa a ser el informe de validación del dato.** Se entrena, se mide y se reporta que no discrimina, pero el entregable es la cadena de evidencia. Para el jurado, la tabla del 83 % contra 0 % de desfase temporal vale más que cualquier AUC, porque demuestra que el equipo fue al dato y no al modelo.

**2 · La elegibilidad se calcula, no se predice.** `agent/policies/eligibility_v1.yaml` y `agent/policies/engine.py`. Cinco pasos: cuota de cada producto vigente → carga mensual comprometida → DTI → margen bajo el tope de política → monto máximo por producto invirtiendo la amortización. Los umbrales son decisión de negocio en un archivo versionado, no coeficientes aprendidos.

Esto cierra el hueco que ADR-0005 dejó abierto. La política **no** deriva tasas de oferta de los productos existentes como condiciones del cliente: usa las medianas por tipo de producto como condiciones de catálogo, que es otra cosa, y lo declara. Las tasas resultaron ser el único dato coherente del conjunto — rangos disjuntos y ordenados: tarjeta 18–45 %, personal 12–28 %, hipotecario 6–12 %.

**3 · El sistema no afirma si un cliente está en mora, y lo declara en toda respuesta.** Podría pronunciarse usando la columna del dataset y sonaría más completo. No lo hace. Es preferible decir «esto no lo sé» que dar una cifra que no se sostiene, y esa abstención se mide aparte sin penalizarse.

**4 · La capacidad de pago de ML-04 solo puede restringir el margen, nunca ampliarlo.** Cuando `predict_capacity` estima, el margen es el menor entre el de política y el estimado. Cuando se abstiene —el 94 % de los casos— se usa solo el de política y la respuesta lo dice. ML-04 se mantiene como pieza de ingeniería y se reporta como **estimador sobre datos sintéticos**: sus montos de entrada son uniformes, lo que explica su 0.39 % de mejora sobre el baseline.

**5 · La posición financiera completa entra en el cálculo.** Cuentas e inversiones se computan como reservas — Cuenta Ahorro y Corriente al 100 %, Inversión al 70 % por fricción de liquidación — y operan como requisito por producto (hipotecario 3 meses de cuota, personal 1, tarjeta 0) y como factor compensatorio (reservas ≥ 6 meses de la carga actual suben el tope de DTI del 40 al 45 %, sin tocar el corte duro del 60 %). `current_balance` está vetada como variable de modelo por fuga; describir la posición al corte para una política es otro uso y no lo es.

## Consecuencias

- La parte que decide **se testea sin LLM y sin modelo**: 58 pruebas en `tests/policies/`.
- El negocio ajusta el apetito de riesgo editando una línea del YAML y subiendo la versión. No hay reentrenamiento ni despliegue.
- Toda cifra que el agente pronuncie sale del expediente que produce el motor, y el `GroundingChecker` la valida contra esos valores.
- Ninguna prueba permite que el sistema deniegue sin motivo: el cliente recibe el número que no alcanzó y el umbral que debía alcanzar.
- **Refuerza la tesis del proyecto.** Separar la conversación de la decisión no era una precaución de diseño: el dataset lo demostró por la vía dura. Cuando el modelo no puede decidir, lo que sostiene el sistema es la política auditable y el anclaje sobre hechos.

## Supuestos declarados

Plazo de préstamos (48 y 240 meses — `expiration_date` tiene cobertura cero en préstamos y 95 % en tarjetas), pago mínimo revolvente (5 % de lo dispuesto), estrés de línea no dispuesta (10 %), descuento de inversiones (30 %), vencimiento de cuota a fin de mes, y tope de DTI del 40 %. Todos viven en el YAML y se declaran en la respuesta cuando la afectan.

## Aplazado

Ofrecer el mismo producto a varios plazos —hipotecario a 120 y 240 meses con cuotas distintas— para que el cliente elija. Añade complejidad al catálogo y a la conversación; se decidió no hacerlo todavía.
