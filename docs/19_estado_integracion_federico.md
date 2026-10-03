# Estado de integración de la rama de Federico

2 de octubre de 2026 · Revisión local después de sincronizar remotos.
Actualizado después del merge de `origin/main` en la rama de Federico.

## Resumen ejecutivo

Se actualizó la referencia remota de Git, se avanzó `main` local hasta
`origin/main` en el commit `393ba32` y después se fusionó `origin/main` dentro de
`trabajo/federico-data-cognition` con el merge commit `3bb9e8c`. Antes del merge
se guardó temporalmente el trabajo local sin commit y después se restauró.

La rama local de Federico ya contiene los tres commits nuevos de `main`. La rama
remota `origin/trabajo/federico-data-cognition` todavía no refleja este merge:
el estado local está por delante del remoto.

Además de lo ya enviado a la rama remota, el checkout local contiene una capa
nueva sin publicar: API FastAPI, prototipo local, UI Next.js, documentación 15-18
y ajustes sobre churn. Esa capa es valiosa para la demo, pero todavía no está
lista para entrar como entrega limpia: faltan correcciones de lint, seguridad,
configuración y build frontend.

## Estado de ramas

Rama actual local:

```text
trabajo/federico-data-cognition
```

Punteros relevantes después de `git fetch --all --prune`:

| Referencia | Commit | Lectura |
|---|---|---|
| `origin/main` | `393ba32` | Main remoto actualizado |
| `main` | `393ba32` | Main local fast-forward a remoto |
| `origin/trabajo/federico-data-cognition` | `d1a0726` | Rama remota de Federico |
| `trabajo/federico-data-cognition` | `3bb9e8c` + cambios locales | Rama local con `origin/main` fusionado |

Comparación remota:

```text
origin/main...HEAD = 0 commits en main / 6 commits en Federico local
```

Commits de `main` que faltaban y ya entraron por el merge:

| Commit | Tema |
|---|---|
| `ee3f5d3` | Ciclo del agente AG-03..AG-10 |
| `7cf87b3` | Control de cambios y corrección del generador |
| `393ba32` | Contrato de trabajo para el agente de Federico |

Commits de Federico que siguen sin estar en `main`:

| Commit | Tema |
|---|---|
| `7feeccb` | Interés comercial y cupos registrados por cliente |
| `60f1736` | Red profunda y política de Eduardo en el asesor |
| `3f2f8cd` | Experimento de profundidad de seis capas |
| `76594fc` | Churn prediction y segmentation mockup |
| `d1a0726` | Churn prediction y segmentation mockup |
| `3bb9e8c` | Merge de `origin/main` dentro de la rama de Federico |

`git cherry -v origin/main origin/trabajo/federico-data-cognition` marcó los
cinco commits con `+`, por lo que Git no los reconoce como ya aplicados en main
por cherry-pick equivalente.

## Diferencia de la rama remota de Federico contra main

La rama remota aporta 32 archivos modificados o nuevos y unas 4,090 inserciones.
Bloques principales:

| Área | Archivos principales | Estado |
|---|---|---|
| Producto/interés comercial | `ml/training/product_interest.py`, `ml/serving/product_advisor.py`, `docs/13_interes_producto_y_cupo.md` | No está en main |
| Red profunda y asesor | `ml/training/deep_interest.py`, `ml/serving/client_analysis.py`, `docs/14_red_profunda_y_asesor.md` | No está en main |
| Experimento de profundidad | `ml/training/depth_experiment.py`, `docs/15_experimento_profundidad.md` | No está en main |
| Escalamiento observado | `ml/training/support_escalation.py`, `ml/model_cards/support_escalation.json` | No está en main |
| Churn y segmentación | `ml/training/churn_prediction.py`, `ml/training/customer_segmentation.py`, `docs/churn_prediction_model.md` | No está en main |
| Pruebas ML | `tests/ml/test_product_interest.py`, `tests/ml/test_deep_interest.py`, `tests/ml/test_depth_experiment.py`, `tests/ml/test_churn_prediction.py` | No está en main |
| Documentación y run targets | `README.md`, `Makefile`, `pyproject.toml`, `docs/knowledge/*` | Requiere revisar con main actualizado |

La simulación de merge no mostró conflictos duros. `pyproject.toml` aparece como
modificado en ambos lados, así que debe revisarse manualmente al integrar.

## Trabajo local adicional no publicado

El árbol local agrega una segunda capa por encima de la rama remota. Esta capa no
está en `origin/trabajo/federico-data-cognition`.

Archivos principales:

| Área | Archivos |
|---|---|
| API local | `api/main.py` |
| Prototipo local | `prototype/app.py`, `prototype/core.py`, `prototype/web/*`, `prototype/README.md`, `prototype/Modelfile` |
| UI Next.js | `ui/package.json`, `ui/src/app/page.tsx`, `ui/src/app/globals.css`, configuración de Next/Tailwind/ESLint |
| Documentación nueva | `docs/15_ai_customer_solution.md`, `docs/16_revision_modelos_y_escalamiento.md`, `docs/17_noema_local_arquitectura.md`, `docs/18_noema_ai_final_architecture.md` |
| Churn | `ml/training/churn_prediction.py`, `ml/model_cards/churn_prediction.json`, `tests/ml/test_churn_prediction.py` |
| Pruebas locales | `tests/test_local_prototype.py` |
| Archivos no relacionados | `tmp/` |

Lectura de riesgo: esta capa ya apunta a una demo ejecutable, pero mezcla código
de producto, prototipo, documentación y archivos temporales. Conviene separarla
en commits pequeños antes de pedir merge.

## Verificación ejecutada

### Python

Con el Python global del sistema, la suite falla en importación porque el entorno
no corresponde al proyecto. El error observado fue:

```text
TypeError: zip() takes no keyword arguments
```

El entorno global también mostró librerías de Anaconda antiguas. Conclusión:
usar siempre el virtualenv del proyecto.

Después del merge, el primer intento con `.venv/bin/python` falló porque el
entorno local no tenía `PyJWT`, aunque `pyjwt>=2.9` ya está declarado en
`pyproject.toml`. Se instaló con `uv pip install --python .venv/bin/python
'PyJWT>=2.9'` y se repitió la suite.

Resultado actual con `.venv/bin/python`:

```text
945 pruebas pasaron, 1 warning
```

Comando usado:

```bash
.venv/bin/python -m pytest
```

### Ruff

Ruff falla en el estado local actual.

Problemas relevantes:

| Archivo | Problema |
|---|---|
| `api/main.py` | Query SQL construida con f-string sobre `customer_id`; riesgo S608 |
| `api/main.py` | Líneas mayores a 100 caracteres |
| `ml/training/churn_prediction.py` | Línea mayor a 100 caracteres |
| `tests/ml/test_churn_prediction.py` | Líneas mayores a 100 caracteres |
| `tmp/pdfs/build_anthropic_cv.py` | Import sin usar y muchas líneas largas; parece material temporal ajeno al repo |

Conclusión: el código funcional pasa pruebas, pero el repo no está listo para
`make check` hasta corregir lint y excluir o limpiar `tmp/`.

### API FastAPI

La API local importa correctamente:

```text
Noema AI-First Banking Core
```

Problemas encontrados antes de usarla como demo:

1. `api/main.py` consulta DuckDB con interpolación directa de `customer_id`.
2. La API espera `GEMINI_API_KEY`, pero `.env.example` documenta `ANTHROPIC_API_KEY`
   y `LLM_MODEL=claude-sonnet-5`.
3. El modelo mencionado en la URL es `gemini-3.5-flash-lite`; se debe verificar
   nombre real y disponibilidad antes de prometerlo.
4. La API depende de `data/noema.duckdb`, que existe localmente y pesa cerca de
   3.0 GB, pero no vive en Git.

### Prototipo local

El prototipo importa correctamente:

```text
Noema Local · Demo
```

Está documentado en `prototype/README.md` y depende de:

- `.venv`
- `prototype/requirements.txt`
- Ollama en `127.0.0.1:11434`
- modelo `noema-bank-local` creado desde `prototype/Modelfile`
- pesos locales de Whisper tiny en `data/models/whisper-tiny`
- artefactos comerciales opcionales en `data/models/`

### UI

`npm run lint` en `ui/` pasa con una advertencia:

```text
ui/src/app/page.tsx:40:14  'e' is defined but never used
```

`npm run build` falla porque Next intenta descargar fuentes desde Google:

```text
Failed to fetch Geist from Google Fonts.
Failed to fetch Geist Mono from Google Fonts.
```

Conclusión: el build de producción requiere self-host de fuentes, quitar
`next/font/google`, o permitir salida de red/proxy hacia `fonts.googleapis.com`.
Para una demo local, `npm run dev` puede ser suficiente, pero no reemplaza el
build de entrega.

## Qué falta para dejarlo corriendo

### Camino mínimo de demo local

1. Usar el entorno correcto:

```bash
.venv/bin/python -m pytest
```

2. Correr API:

```bash
.venv/bin/python -m uvicorn api.main:app --reload --port 8000
```

3. Correr UI:

```bash
cd ui
npm run dev
```

4. Abrir UI en `http://localhost:3000`.

Este camino depende de que `.env` tenga la llave del proveedor LLM que realmente
se vaya a usar y de que `data/noema.duckdb` exista localmente.

### Camino de prototipo local más completo

Desde la raíz:

```bash
uv pip install --python .venv/bin/python -r prototype/requirements.txt
ollama pull qwen2.5:1.5b
ollama create noema-bank-local -f prototype/Modelfile
.venv/bin/python -c "from faster_whisper.utils import download_model; \
download_model('tiny', output_dir='data/models/whisper-tiny')"
.venv/bin/python -m uvicorn prototype.app:app --host 127.0.0.1 --port 8765
```

Abrir `http://127.0.0.1:8765`.

Este flujo no debe exponerse a Internet. Es una demo local con cuenta simulada,
sesiones temporales y operaciones ficticias.

## Correcciones recomendadas antes de integrar

1. Guardar el estado actual en commits separados:
   - integración de rama remota de Federico contra main;
   - API local;
   - prototipo local;
   - UI;
   - documentación;
   - churn.
2. Rebasear o mergear `origin/main` sobre `trabajo/federico-data-cognition`.
3. Revisar manualmente `pyproject.toml`.
4. Cambiar la query de `api/main.py` a parámetros DuckDB, no f-string.
5. Alinear `.env.example`, README y API sobre un solo proveedor LLM real.
6. Quitar o ignorar `tmp/` para que Ruff no falle por archivos temporales.
7. Corregir líneas largas en API/churn/tests.
8. Resolver fuentes de Next para que `npm run build` funcione sin red.
9. Cambiar el `catch (e)` de la UI por un manejo sin variable no usada.
10. Decidir si la API de `api/main.py` o el prototipo `prototype/app.py` será la
    demo oficial; mantener ambos puede confundir al jurado si no se explica.

## Preguntas abiertas

1. ¿La demo final usará Gemini, Anthropic o Ollama local?
2. ¿La rama de Federico debe llevar también la UI/API local, o solo modelos,
   datos, SCM y documentación?
3. ¿Los commits duplicados de churn (`76594fc` y `d1a0726`) representan una
   corrección real o conviene compactarlos antes del merge?
4. ¿El prototipo local es el entregable de demo o una herramienta de revisión
   previa para Federico?
5. ¿El frontend `ui/` reemplaza al frontend original esperado en la arquitectura
   o es solo un mock mínimo para conectar al API?

## Estado recomendado

No pedir merge a `main` todavía con el árbol local tal como está. Ya se trajeron
los tres commits nuevos de main a la rama local de Federico y la suite Python
pasa completa en el estado combinado. Todavía falta limpiar la capa local
API/prototipo/UI antes de abrir o actualizar el PR.

La capa local API/prototipo/UI debe estabilizarse como demo separada. Las pruebas
funcionales ya dan buena señal, pero los fallos de lint, el riesgo SQL, la
configuración LLM inconsistente y el build frontend con fuentes externas son los
bloqueos concretos para declarar que el proyecto está listo para correr de punta
a punta.
