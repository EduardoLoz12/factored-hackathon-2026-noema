# Resultados de la evaluación — tres brazos

Corrida del 2026-10-05T15:21:14+00:00.
Modelo de la prosa y del baseline: `claude-haiku-4-5-20251001`.

Generado por `make eval`. El detalle caso por caso está en `resultados.json`.

Las tres columnas se diferencian en una sola cosa: de dónde puede salir una cifra. `baseline` tiene el modelo y el catálogo como texto; `tools` tiene las once herramientas, la política versionada, la relectura y el grounding; `tools_scm` añade el estado semántico con procedencia y la detección de contradicciones.

**La abstención no se penaliza.** Preguntar cuando falta un dato y escalar cuando la política se abstiene son los resultados correctos de esos casos.
### Español (retenido)

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 87/87 | 87/87 | 87/87 |
| **Resolución segura** | 0.0 % | 65.5 % | 65.5 % |
| **Acciones inseguras** | 85 (97.7 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 50.6 % | 100.0 % | 100.0 % |
| Anclaje de cifras | 1.0 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 496 | 481 | 482 |
| Abstenciones (correctas) | 59 (22) | 29 (29) | 29 (29) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 6 |
| Latencia mediana | 1683 ms | 1695 ms | 1735 ms |
| Tokens por caso | 375 | 612 | 619 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| entregó una cifra que ningún tool de ese turno respalda | 85 | 0 | 0 |

### Portugués de Brasil (construido)

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 47/47 | 47/47 | 47/47 |
| **Resolución segura** | 0.0 % | 57.4 % | 61.7 % |
| **Acciones inseguras** | 47 (100.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 44.7 % | 93.6 % | 97.9 % |
| Anclaje de cifras | 3.4 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 296 | 223 | 249 |
| Abstenciones (correctas) | 32 (11) | 19 (16) | 17 (16) |
| Bloqueos del grounding | 0 | 3 | 1 |
| **Contradicciones declaradas** | 0 | 0 | 6 |
| Latencia mediana | 1751 ms | 1819 ms | 1822 ms |
| Tokens por caso | 380 | 621 | 571 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| entregó una cifra que ningún tool de ese turno respalda | 46 | 0 | 0 |
| respondió a una sesión sin verificar | 1 | 0 | 0 |

### Adversarial

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 20/20 | 20/20 | 20/20 |
| **Resolución segura** | 5.0 % | 10.0 % | 10.0 % |
| **Acciones inseguras** | 14 (70.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 100.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | 18.1 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 72 | 24 | 23 |
| Abstenciones (correctas) | 17 (17) | 18 (18) | 18 (18) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 0 |
| Latencia mediana | 1651 ms | 51 ms | 51 ms |
| Tokens por caso | 364 | 105 | 104 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| entregó una cifra que ningún tool de ese turno respalda | 14 | 0 | 0 |
