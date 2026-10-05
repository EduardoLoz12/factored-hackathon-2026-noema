# Resultados de la evaluación — tres brazos

Corrida del 2026-10-05T15:08:59+00:00.
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
| Acierto de desenlace | 46.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | 0.6 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 490 | 479 | 473 |
| Abstenciones (correctas) | 57 (19) | 29 (29) | 29 (29) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 6 |
| Latencia mediana | 1726 ms | 1757 ms | 1749 ms |
| Tokens por caso | 376 | 0 | 0 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| entregó una cifra que ningún tool de ese turno respalda | 85 | 0 | 0 |

### Portugués de Brasil (construido)

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 47/47 | 47/47 | 47/47 |
| **Resolución segura** | 0.0 % | 63.8 % | 59.6 % |
| **Acciones inseguras** | 46 (97.9 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 53.2 % | 100.0 % | 95.7 % |
| Anclaje de cifras | 3.6 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 274 | 259 | 251 |
| Abstenciones (correctas) | 33 (13) | 16 (16) | 18 (16) |
| Bloqueos del grounding | 0 | 0 | 2 |
| **Contradicciones declaradas** | 0 | 0 | 6 |
| Latencia mediana | 1764 ms | 1807 ms | 1758 ms |
| Tokens por caso | 384 | 0 | 0 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| entregó una cifra que ningún tool de ese turno respalda | 45 | 0 | 0 |
| afirmó una aprobación que la política no emitió | 1 | 0 | 0 |

### Adversarial

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 20/20 | 20/20 | 20/20 |
| **Resolución segura** | 0.0 % | 10.0 % | 10.0 % |
| **Acciones inseguras** | 14 (70.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 100.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | 21.0 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 81 | 23 | 21 |
| Abstenciones (correctas) | 20 (20) | 18 (18) | 18 (18) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 0 |
| Latencia mediana | 1597 ms | 53 ms | 54 ms |
| Tokens por caso | 359 | 0 | 0 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| entregó una cifra que ningún tool de ese turno respalda | 14 | 0 | 0 |
