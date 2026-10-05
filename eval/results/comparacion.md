# Resultados de la evaluación — tres brazos

Corrida del 2026-10-05T14:44:55+00:00.
Modelo de la prosa y del baseline: `no corrido`.

Generado por `make eval`. El detalle caso por caso está en `resultados.json`.

Las tres columnas se diferencian en una sola cosa: de dónde puede salir una cifra. `baseline` tiene el modelo y el catálogo como texto; `tools` tiene las once herramientas, la política versionada, la relectura y el grounding; `tools_scm` añade el estado semántico con procedencia y la detección de contradicciones.

**La abstención no se penaliza.** Preguntar cuando falta un dato y escalar cuando la política se abstiene son los resultados correctos de esos casos.
### Español (retenido)

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 0/86 | 86/86 | 86/86 |
| **Resolución segura** | 0.0 % | 64.0 % | 64.0 % |
| **Acciones inseguras** | 0 (0.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 0.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | — | 100.0 % | 100.0 % |
| Cifras pronunciadas | 0 | 88 | 88 |
| Abstenciones (correctas) | 0 (0) | 30 (30) | 30 (30) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 5 |
| Latencia mediana | 0 ms | 54 ms | 59 ms |
| Tokens por caso | 0 | 0 | 0 |

### Portugués de Brasil (construido)

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 0/46 | 46/46 | 46/46 |
| **Resolución segura** | 0.0 % | 60.9 % | 60.9 % |
| **Acciones inseguras** | 0 (0.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 0.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | — | 100.0 % | 100.0 % |
| Cifras pronunciadas | 0 | 46 | 46 |
| Abstenciones (correctas) | 0 (0) | 17 (17) | 17 (17) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 5 |
| Latencia mediana | 0 ms | 64 ms | 63 ms |
| Tokens por caso | 0 | 0 | 0 |

### Adversarial

| Métrica | baseline | tools | tools_scm |
|---|---:|---:|---:|
| Casos corridos | 0/20 | 20/20 | 20/20 |
| **Resolución segura** | 0.0 % | 0.0 % | 0.0 % |
| **Acciones inseguras** | 0 (0.0 %) | 0 (0.0 %) | 0 (0.0 %) |
| Acierto de desenlace | 0.0 % | 100.0 % | 100.0 % |
| Anclaje de cifras | — | — | — |
| Cifras pronunciadas | 0 | 0 | 0 |
| Abstenciones (correctas) | 0 (0) | 20 (20) | 20 (20) |
| Bloqueos del grounding | 0 | 0 | 0 |
| **Contradicciones declaradas** | 0 | 0 | 0 |
| Latencia mediana | 0 ms | 62 ms | 62 ms |
| Tokens por caso | 0 | 0 | 0 |
