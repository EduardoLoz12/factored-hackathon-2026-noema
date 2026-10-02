# Lo que falta — concepto antes que código

Generado el 1-oct-2026 (D5 de 9). Complementa `docs/knowledge/checklist.md`, que dice *qué* falta.
Este documento dice *por qué* cada ítem existe y *qué decisión* encierra. Si un ítem se recorta, aquí
está lo que se pierde al recortarlo.

**Estado:** 37 ítems faltan, 4 avanzados. Todos de Eduardo. Federico cerró sus 21 (18 terminados,
3 avanzados: `DAT-11` parcial, `DAT-13`/`DAT-14` bloqueados por credenciales).

---

## Dos huecos conceptuales que hay que cerrar antes de escribir código

Estos no son ítems del checklist. Son decisiones sin tomar que bloquean ítems.

### 1. Las nueve herramientas nunca se enumeraron

`AG-04` dice «las nueve herramientas implementadas» y apunta a `agent/tools/{customer,credit,cases}.py`.
Ningún documento del repo lista cuáles son las nueve. `docs/05_security.md:31` sí define el **contrato**
de cada tool (`requires_auth`, `writes`, `allowed_roles`) y `:32` exige `idempotency_key` en las de
escritura, pero no el catálogo.

Hay que fijar la lista antes de `AG-03`, porque el registro, la allowlist por rol y los casos de
evaluación cuelgan de ella. Reparto implícito por los archivos de evidencia: lectura de cliente,
lectura de crédito, escritura de casos.

### 2. ¿Cinco etapas o seis?

`docs/00_challenge_brief.md:19` cita la slide 11 del reto: **cinco** etapas, *Understand → Decide →
Act → Verify → Escalate*, y exige que sean «visibles en el código y en las trazas». `AG-06` dice
**seis**. La sexta no está definida en ningún documento.

La candidata natural es una etapa previa de identificación, porque `AG-05` (AccessGuard) ya existe
como ítem aparte y el reto exige autenticar antes de responder. Pero eso es inferencia, no spec.
Decidirlo ahora: el nombre de las etapas es lo que el jurado va a leer en la traza y en el panel
Caja de Vidrio, y tiene que ser el mismo string en los tres lugares.

---

## Agente — 11 ítems, D5–D6

El bloque más grande y el que bloquea todo lo demás. `eval/`, `api/` y `ui/` no pueden empezar sin
un ciclo de agente que cierre de punta a punta.

### `AG-03` · Registro de tools con allowlist por rol
**Concepto:** los permisos viven en código, no en el prompt. El reto lo exige explícito (slide 13).
Un agente que decide si puede escribir preguntándole al LLM «¿estás autorizado?» no tiene control de
acceso: tiene una sugerencia. El registro declara por tool `requires_auth`, `writes` y
`allowed_roles`, y el ejecutor valida **antes** de invocar y **registra el intento rechazado**.
**Lo que se demuestra:** que un tool de escritura invocado con sesión no verificada falla. Es prueba
obligatoria según `docs/05_security.md:33`.

### `AG-04` · Las nueve herramientas
**Concepto:** es la frontera entre conversar y hacer. El LLM no emite SQL nunca
(`docs/05_security.md:38`): elige una tool con parámetros tipados, y las consultas las escribimos
nosotros, parametrizadas. Toda cifra que aparezca en una respuesta tiene que haber salido de aquí —
eso es lo que `AG-09` después verifica mecánicamente.
**Lo que se demuestra:** que el sistema es un sistema de servicio, no un chatbot (slide 10, la
exigencia que más pesa).

### `AG-05` · AccessGuard
**Concepto:** el agente no habla de dinero con quien no verificó. Tres intentos y corta. El
`customer_id` va **dentro** del JWT, no como parámetro que el modelo pueda elegir — si el modelo
puede escribir el id del cliente, puede pedir los datos de otro.
**Trampa del dataset:** el teléfono **no** sirve para verificar identidad. 48.4 % de los clientes
tiene teléfono de otro país (`docs/09_etl_spec.md:40`). Usarlo como factor sería un hallazgo en
contra nuestra.

### `AG-06` · Orquestador de las seis etapas
**Concepto:** el corazón de la tesis — separar la conversación de la decisión. El orquestador decide
qué etapa toca; el LLM solo redacta dentro de la etapa. Las etapas tienen que ser **visibles**:
mismo nombre en el código, en la traza JSON y en el panel del frontend. Si el jurado no puede ver
las cinco etapas, el punto de la slide 11 no se cobra aunque el código las tenga.
**Depende de:** la decisión 5-vs-6 de arriba.

### `AG-07` · VERIFY: relectura real + ledger de acciones
**Concepto:** después de escribir, se vuelve a leer del store y se compara. Si no coincide, **no se
afirma**: se escala. Regla 3 del contrato del proyecto.
**Por qué importa desproporcionadamente:** el reto lo pide textual («Verify that actions actually
happened», slide 11) y el brief ya anotó que es *barato y casi nadie lo hará*. Es el ítem con mejor
relación esfuerzo/punto de todo el checklist.

### `AG-08` · Handoff estructurado validado por esquema
**Concepto:** cuando escala a un humano, no se le manda la transcripción. Se le manda un expediente:
hechos verificados con su fuente, acciones ya ejecutadas, preguntas abiertas. Validado por esquema,
no por confianza en el formato que produjo el LLM.
**Lo que se demuestra:** slide 11, «structured handoff… not raw transcripts».

### `AG-09` · GroundingChecker
**Concepto:** la regla 1 del proyecto hecha máquina. Extrae cifras y datos personales de la
respuesta final y verifica que cada uno exista entre los valores que devolvieron los tools **de ese
turno**. Un número huérfano bloquea la respuesta; al segundo intento fallido, escala
(`docs/05_security.md:39`).
**Por qué es el guardrail central:** sin esto, «el LLM no inventa cifras» es una promesa. Con esto,
es una propiedad verificable y medible en la evaluación.
**Nota del hallazgo de hoy:** cuidado con exponer dos probabilidades para lo mismo. Si un payload
trae la cifra del modelo recomendado *y* la del rechazado, el checker acepta una cifra que el
protocolo de selección descartó.

### `AG-10` · Defensa contra inyección de prompt
**Concepto:** el texto del cliente es dato, no instrucción. Y los transcripts del dataset traen
placeholders sin rellenar (`{monto}`, `{moneda}`, `{limite}`) que son vector de inyección gratis.
La defensa no puede ser «le pedimos al modelo que ignore instrucciones»: tiene que ser la allowlist
de `AG-03` sosteniendo el perímetro aunque el modelo se deje convencer.
**Se mide en:** `EV-04`, la suite adversarial. El reto la exige (slide 13).

### `AG-11` · Multilingüe ES/PT
**Concepto:** el reto es regional. Detección de idioma + prompts separados.
**Dato duro:** el corpus de transcripts tiene **cero portugués** (`docs/01_data_audit.md`). El set PT
de `EV-03` se construye traduciendo las plantillas, y eso hay que declararlo como limitación — no
presentarlo como evidencia de cobertura real.

### `AG-12` · Observabilidad: traza por turno, costo, health checks
**Concepto:** una traza por turno con etapas, tools invocados, valores devueltos, decisión y costo.
Es a la vez el insumo del panel Caja de Vidrio (`UI-03`), la evidencia de las métricas
(`EV-06`) y lo que hace el sistema depurable en vivo frente al jurado.
**Destino:** `logs/traces/`, nunca la raíz (`logs/README.md`).

### `AG-13` · Integración del SCM tras `SCM_ENABLED`
**Concepto:** el SCM de Federico entra como tercer brazo medible, no como dependencia. Con
`SCM_ENABLED=false` el sistema funciona **idéntico** y toda la suite sigue verde. La bandera no es
cortesía: es el instrumento que mide el aporte del SCM en el ablation de `EV-05`.
**Mecánica:** si `missing_evidence()` no está vacío, el orquestador **pregunta en vez de decidir**
(`docs/07_scm_spec.md:80`). Ahí es donde el SCM gana o no gana puntos.

---

## Modelos — 6 ítems, deuda de D4

Pesan menos de lo que parece: `ML-03` ya se cerró como **informe de validación**, no como modelo que
discrimina. La variable objetivo no existe en el dataset (F-027 a F-034). Eso no es un fracaso: es el
argumento de que la elegibilidad la decide una política escrita, no un PD estimado.

| Ítem | Concepto |
|---|---|
| `ML-05` | Métricas y calibración: AUC, PR-AUC, KS, Brier. **La calibración importa más que el ranking** — una probabilidad que no está calibrada no se puede usar en una decisión de crédito, y el Brier es lo que lo dice. |
| `ML-06` | SHAP, los 3 factores por predicción. Es el ítem de **explicabilidad**: si no se puede decir por qué, no entra al sistema. Y alimenta la respuesta que el agente le da al cliente cuando explica un rechazo. |
| `ML-07` | MLflow: tracking y registry. Es reproducibilidad (slide 15), no burocracia — poder decir qué versión produjo qué número. |
| `ML-08` | Model cards con supuestos y **columnas excluidas**. La lista de lo que se excluyó por fuga es tan evaluable como el modelo. |
| `ML-09` | `predictor.py`: `predict_risk` y `predict_capacity`. La frontera de servicio. **Falla cerrado** (regla 5): si el modelo no carga, no aprueba nada, escala y lo dice. |
| `ML-10` | Estabilidad por país. Un modelo que ordena bien en agregado y mal en un país es un problema de equidad, no de performance. |

---

## Evaluación — 7 ítems, D6–D8. **No se recorta nunca**

Es lo que se califica. La regla de corte del plan es explícita: si el día 6 el agente no cierra, se
recorta la interfaz a Streamlit; la evaluación nunca.

| Ítem | Concepto |
|---|---|
| `EV-01` | Generador de casos desde las plantillas **reales**. Los transcripts no sirven como corpus (2 plantillas, 1 intent, cero PT) pero sí como molde. Que los casos salgan de las plantillas del dataset y no de nuestra imaginación es lo que los hace defendibles. |
| `EV-02` | ~80 casos retenidos en español. **Retenidos** significa que no se tocan mientras se desarrolla. Es la mitad del valor del número que reporten. |
| `EV-03` | ~40 casos en portugués de Brasil. Traducidos, porque el dataset no trae PT. Declararlo. |
| `EV-04` | ~20 casos adversariales: inyección y suplantación. Exigido por la slide 13. Mide `AG-10` y `AG-05`. |
| `EV-05` | Harness de los **tres brazos**: `baseline` · `tools` · `tools_scm`. Sin la tabla comparativa no hay puntos de rigor (slide 12). El baseline es lo que prueba que las tools aportan; el tercer brazo es lo que mide el SCM. |
| `EV-06` | Métricas: resolución segura, **acciones inseguras**, grounding, costo. La tasa de acciones inseguras es la métrica estrella del reto. Meta: cero, demostrada. Y **la abstención se mide aparte y no se penaliza** (regla 7) — si se cuenta como fallo, el sistema aprende a contestar siempre, que es exactamente lo que el reto castiga. |
| `EV-07` | Resultados publicados y comparados. Publicados = el jurado los ve sin correr nada. |

---

## API — 2 ítems, D7

| Ítem | Concepto |
|---|---|
| `API-01` | FastAPI: `chat`, `trace`, `cases`, `metrics`, `eval`, `scenarios`. `trace` no es un extra de debug: es el endpoint que alimenta la Caja de Vidrio, o sea el argumento visual del proyecto. |
| `API-02` | JWT, rate limit, CORS cerrado, **redacción de PII**. El `customer_id` dentro del token (ver `AG-05`). La redacción de PII aplica también a los logs — `logs/README.md` fija las reglas. |

---

## Frontend — 8 ítems, D6–D7. Hoy `ui/` está vacío

**El criterio número uno del reto es que funcione y que el jurado pueda usarlo** (slide 20 y
kickoff): deploy vivo y setup de un comando pesan más que la sofisticación. Por eso `UI-08` no es el
último ítem de una lista, es casi el primero en importancia.

| Ítem | Concepto |
|---|---|
| `UI-01` | Next.js configurado. **Regla de corte vigente:** si el día 6 el ciclo del agente no cierra de punta a punta, esto se recorta a Streamlit. Decidir temprano cuesta menos que decidir el día 7. |
| `UI-02` | `/chat` en ES y PT. La puerta de entrada del jurado. |
| `UI-03` | **Panel Caja de Vidrio** con la traza en vivo. El ítem más valioso de todo el frontend: hace visible la tesis. El jurado ve las etapas, los tools invocados, las cifras con su fuente, y la decisión de la política. Un chat sin este panel parece un chatbot — justo lo que la slide 10 castiga. |
| `UI-04` | Escenarios precargados. El jurado tiene minutos, no media hora. Si tiene que inventar un caso para probar el sistema, va a probar el camino que peor funciona. Los escenarios guían hacia la demostración: un aprobado, un rechazo explicado, una abstención, una escalación. |
| `UI-05` | `/console` con los expedientes estructurados. Es `AG-08` hecho visible: el lado humano del handoff. |
| `UI-06` | `/analytics`: métricas del agente y **evidencia del ablation**. La tabla de los tres brazos, vista sin correr código. |
| `UI-07` | `/analytics`: insights de negocio y calidad de datos. Es donde el pilar de Data Analytics se cobra, y donde el `dq_report` de Federico (`DAT-12`) se vuelve entregable. |
| `UI-08` | Deploy público. Sin URL viva no hay entregable. |

---

## Entregables — 3 ítems + 2 avanzados, D8–D9

| Ítem | Concepto |
|---|---|
| `ENT-01` | Docs 02/03/04/06 completos. **Tres de esos cuatro son hoy marcadores declarados** (`02_architecture.md`, `04_evaluation.md`). Son los documentos que el jurado abre primero. |
| `ENT-02` | `LIMITATIONS.md` final. **Es entregable evaluado, no disculpa** (slide 15). Lo que ya tenemos para llenarlo es fuerte: la variable objetivo que no existe, el `fraud_score` que no sale de un modelo, los transcripts sin portugués, el `signal_gate` que se rechazó solo. Honestidad documentada con números es un activo, no una deuda. |
| `ENT-03` | Cinco diapositivas. Cinco. El recorte es el trabajo. |
| `ENT-04` | Video ≤3 min. Guion antes de grabar. 40 segundos son de Federico (plan D7). |
| `ENT-05` | Envío a `hackathon.admin@factored.ai`. Repo público + URL desplegada + slides + video. Cierre **5-oct 23:59 hora Colombia**. |

---

## Cómo se ordena esto en los 4 días que quedan

La dependencia dura es una: **`EV`, `API` y `UI` no arrancan sin un ciclo de agente que cierre**.
Dentro de `AG`, el camino mínimo para cerrar el ciclo es
`AG-03` → `AG-04` → `AG-05` → `AG-06` → `AG-07`. `AG-08` a `AG-13` endurecen un ciclo que ya corre.

Los ítems de mejor relación punto/esfuerzo, por si hay que priorizar bajo presión:

1. `AG-07` (VERIFY) — exigido textual, barato, casi nadie lo hará.
2. `UI-03` (Caja de Vidrio) — convierte todo el rigor invisible en algo que el jurado ve.
3. `EV-06` (acciones inseguras) — la métrica estrella del reto.
4. `ENT-02` (LIMITATIONS) — ya tenemos el contenido; es redactar lo que ya se midió.
5. `UI-04` (escenarios) — barato, y decide qué ve el jurado en sus tres minutos.

Lo que **no** se recorta bajo ninguna circunstancia: la evaluación (`EV-*`) y el deploy (`UI-08`).
