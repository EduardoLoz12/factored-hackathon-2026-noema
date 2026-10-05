"""Evaluación de los tres brazos — `EV-01` a `EV-07`.

La rúbrica pide `Baseline → Proposed System → Held-out Evaluation` (slide 12). Acá
viven las tres piezas: el generador de casos con su etiqueta, los tres brazos, y las
métricas con las que se comparan.

El principio que ordena todo el módulo: **la etiqueta no la pone un modelo**. Sale de
`agent/policies/eligibility_v1.yaml` sobre hechos leídos de la base, así que de cada
caso se puede decir exactamente de dónde viene su resultado esperado.
"""
