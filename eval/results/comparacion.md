# Resultados de la evaluación — tres brazos

Corrida del 2026-10-05T14:49:35+00:00.
Modelo de la prosa y del baseline: `claude-haiku-4-5-20251001`.

Generado por `make eval`. El detalle caso por caso está en `resultados.json`.

Las tres columnas se diferencian en una sola cosa: de dónde puede salir una cifra. `baseline` tiene el modelo y el catálogo como texto; `tools` tiene las once herramientas, la política versionada, la relectura y el grounding; `tools_scm` añade el estado semántico con procedencia y la detección de contradicciones.

**La abstención no se penaliza.** Preguntar cuando falta un dato y escalar cuando la política se abstiene son los resultados correctos de esos casos.
### Español (retenido)

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 2/2 | 2/2 | 2/2 |
| **Resolución segura** | 0.0 % | 100.0 % | 100.0 % |
| **Acciones inseguras** | 2 (100.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 50.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | 0.0 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 12 | 24 | 21 |
| Abstenciones (correctas) | 1 (0) | 0 (0) | 0 (0) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 0 |
| Latencia mediana | 2056 ms | 2134 ms | 1940 ms |
| Tokens por caso | 386 | 0 | 0 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| pronunció una cifra que ninguna consulta respalda | 2 | 0 | 0 |

### Portugués de Brasil (construido)

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 2/2 | 2/2 | 2/2 |
| **Resolución segura** | 0.0 % | 100.0 % | 100.0 % |
| **Acciones inseguras** | 2 (100.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 50.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | 0.0 % | 100.0 % | 100.0 % |
| Cifras pronunciadas | 9 | 21 | 19 |
| Abstenciones (correctas) | 1 (0) | 0 (0) | 0 (0) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 0 |
| Latencia mediana | 1663 ms | 1832 ms | 1891 ms |
| Tokens por caso | 380 | 0 | 0 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| pronunció una cifra que ninguna consulta respalda | 2 | 0 | 0 |

### Adversarial

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 2/2 | 2/2 | 2/2 |
| **Resolución segura** | 0.0 % | 0.0 % | 0.0 % |
| **Acciones inseguras** | 2 (100.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 100.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | 7.4 % | — | — |
| Cifras pronunciadas | 27 | 0 | 0 |
| Abstenciones (correctas) | 2 (2) | 2 (2) | 2 (2) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 0 |
| Latencia mediana | 1824 ms | 65 ms | 60 ms |
| Tokens por caso | 404 | 0 | 0 |

**Por qué fueron inseguras**

| Motivo | baseline | tools | tools_scm |
|---|---:|---:|---:|
| pronunció una cifra que ninguna consulta respalda | 1 | 0 | 0 |
| afirmó una aprobación que la política no emitió | 1 | 0 | 0 |
