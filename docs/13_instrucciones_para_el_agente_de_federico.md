# Instrucciones para el agente de Federico

**A quién va dirigido:** al agente de código que trabaja para Federico Vargas en este repo. No es un
documento para el jurado ni para el cliente. Es el contrato de trabajo: qué leer, qué tocar, dónde
escribir y con cuánto rigor.

Última revisión: **2-oct-2026**, después de cerrar `AG-01` a `AG-10`.

---

## 0 · Lo primero, en treinta segundos

Esto es una competencia con jurado externo y cierre duro: **5-oct-2026, 23:59 hora Colombia**. El
repo es público. Todo lo que escribas lo va a leer alguien que no te conoce y que va a asumir que lo
que afirma el código es verdad.

La tesis del sistema es una sola frase: **se separa la conversación de la decisión.** El modelo de
lenguaje conversa y explica; nunca produce una cifra ni decide una elegibilidad. Toda cifra sale de
una tabla o de un tool que consultó una tabla. Si tu capa devuelve un número que nadie puede
rastrear hasta una fila, rompiste la tesis del proyecto, no un detalle de estilo.

---

## 1 · Tu frontera

Tenés dos frentes y un agente dedicado a cada uno. **Usá el que corresponde**, no el genérico.

| Frente | Agente | Spec | Ítems |
|---|---|---|---|
| Datos y ETL | `data-etl` | `docs/09_etl_spec.md` | `DAT-03` a `DAT-14`, `ML-04` |
| Cognición (SCM) | `scm-cognition` | `docs/07_scm_spec.md` | `SCM-01` a `SCM-08` |

**Lo que es tuyo:** `data_platform/`, `ml/training/capacity.py`, `agent/cognition/`,
`tests/cognition/`.

**Lo que no toques**, ni para «arreglar algo de paso»: `agent/core/`, `agent/tools/`,
`agent/policies/`, `agent/guardrails/`, `ml/training/pd_lightgbm.py`,
`ml/training/baseline_logreg.py`, `eval/`, `api/`, `ui/`.

Esto no es territorialidad. El hackathon mide el aporte de cada integrante por separado, y
`make review` marca cualquier commit que cruce una frontera y lo acumula en
`docs/knowledge/contributions.md`. Un commit tuyo dentro de `agent/core/` le resta a Federico en la
evaluación, incluso si el cambio era correcto.

**Si encontrás un bug del otro lado de la frontera:** no lo arregles. Escribilo en
`docs/knowledge/findings.md` con el número de hallazgo que siga, y dejá dicho en el worklog que está
ahí. Así es como Eduardo te manda los suyos —`docs/12_cambios_para_federico.md` tiene nueve
secciones de eso— y funciona.

---

## 2 · Qué leer, en este orden

No empieces a escribir código hasta terminar los cuatro primeros.

1. **`CLAUDE.md`** — el contrato operativo. Las siete reglas no negociables y la tabla de fronteras.
2. **`docs/12_cambios_para_federico.md`** — nueve secciones de avisos de Eduardo hacia tu capa, tres
   de ellos bugs abiertos. **Empezá por la §8 y la §9**, son las últimas y las que tienen trabajo
   pendiente.
3. **Tu spec** — `docs/09_etl_spec.md` o `docs/07_scm_spec.md` según el frente.
4. **`docs/knowledge/findings.md`** — cuarenta y ocho hallazgos. No es historia: son las suposiciones
   que ya se murieron. Leer los `F-012` a `F-020` y los `F-037` a `F-048` te ahorra repetir trabajo
   que ya se descartó con evidencia.
5. `docs/01_data_audit.md` — el perfil real de las trece tablas.
6. `docs/knowledge/checklist.md` — el estado de los 75 ítems, generado. No lo edites a mano.
7. `logs/worklog/` — las bitácoras. La última de Eduardo es del 2-oct.
8. `docs/decisions/` — doce ADRs. Si vas a tomar una decisión que ya está tomada ahí, no la retomes.

**Dato que cambia cómo leés todo lo demás:** el diccionario de datos del reto **miente en siete
puntos**, documentados en `docs/01_data_audit.md`. Enums en español donde promete inglés, una moneda
que no existe, cero duplicados donde promete 2 %, nulos estructurales muy distintos al 5 % declarado.
No cites el diccionario como fuente. Medí la tabla.

---

## 3 · Qué está pendiente de verdad

`SCM-01` a `SCM-08` están **cerrados**, las 26 pruebas de aceptación en verde. Ese frente está
terminado salvo que algo se rompa.

Del lado de datos quedan tres ítems en `avanzado`, que significa «el archivo existe y no es
esqueleto, pero no está terminado»:

| Ítem | Qué falta |
|---|---|
| `DAT-11` | Catálogo y condiciones de producto validadas contra la política versionada |
| `DAT-13` | Espejo en Databricks verificado en el workspace real, no en local |
| `DAT-14` | Export de gold a Postgres **con relectura verificada en el destino** |

Y cuatro avisos abiertos de Eduardo, por prioridad:

1. **§9.1 — `noema_gold.product_policy` está entera en NULL.** Es el más urgente. Si el endpoint
   `/analytics` publica esa tabla, el jurado abre el dashboard y ve la política del banco vacía. Ya
   hay otra fuente identificada en esa sección.
2. **§8.1 — `customer_360.estimated_monthly_income` está en moneda local**, no en dólares. Cualquier
   comparación entre países que la use está mal por un factor de mil o más.
3. **§8.2 — `customer_360` valora con una cotización del futuro.** Es fuga de información temporal:
   una fila con corte en marzo usa el tipo de cambio de junio.
4. **§8.3 y §8.4** — inconsistencias de idioma en `transaction_status` y dos tablas con nombres casi
   iguales. Menores, pero confunden a quien lea.

`DAT-14` tiene una particularidad que no es negociable y conviene entender antes de implementarla:
**toda escritura se vuelve a leer antes de afirmar que ocurrió.** Un `INSERT` que no levantó
excepción no es prueba de que la fila esté en el destino. Escribís, leés de vuelta, comparás, y solo
entonces lo reportás como hecho. Si no coincide, no se afirma: se escala. La misma regla rige
`agent/core/verifier.py` del lado de Eduardo, así que hay un ejemplo trabajado de cómo se ve.

---

## 4 · Dónde documentar — cada cosa tiene su archivo

Esto es la parte que más se salta y la que más cuesta después.

| Qué | Dónde | Cuándo |
|---|---|---|
| Un supuesto que se murió | `docs/knowledge/findings.md` | **Antes de seguir codificando** |
| Una decisión no obvia | `docs/decisions/ADR-00NN-titulo.md` | Antes de implementarla |
| Qué hiciste, con qué fricción, qué quedó a medias | `logs/worklog/AAAA-MM-DD-federico.md` | Antes de cerrar la sesión |
| El avance de un ítem | se genera: `make checklist` | Al terminar la tarea |
| Un bug del lado de Eduardo | `docs/knowledge/findings.md` + aviso en el worklog | Cuando lo encontrás |
| Lo que corrió el ETL o el build | `logs/ingest/`, `logs/build/` — nunca en la raíz | En cada corrida |

### Todo va firmado a nombre de Federico

Esto importa para la evaluación, no es formalidad. El aporte de cada integrante se mide por separado,
y lo que no está atribuido no cuenta para nadie.

- **La bitácora lleva su nombre en el archivo:** `logs/worklog/2026-10-03-federico.md`. Un archivo por
  día y por persona. No escribas en el de Eduardo —`...-eduardo.md`— ni siquiera para agregar una
  línea.
- **Los hallazgos van firmados.** Cada `F-0NN` que escribas cierra con una línea
  `*Encontrado por: Federico Vargas · AAAA-MM-DD · DAT-NN*`. Los cuarenta y ocho que ya hay siguen la
  numeración corrida: tomá el siguiente libre, nunca reutilices uno, nunca renumeres los de otro.
- **Los ADR llevan su autoría** en el encabezado, igual que los doce que ya existen.
- **El commit lo firma su usuario de git**, y `make review` cruza autor contra frontera y lo deja en
  `docs/knowledge/contributions.md`. Ese archivo es la evidencia de quién hizo qué.

### Todo se loguea, también lo que corrió bien

La regla no es «loguear los errores». Es que **una corrida sin registro no ocurrió**, porque nadie
puede reproducirla ni auditarla después.

Cada corrida de ETL, build, carga o entrenamiento deja en `logs/` —en la subcarpeta que
corresponda— al menos esto:

| Qué se registra | Por qué |
|---|---|
| Cuándo empezó y cuándo terminó | Para saber si una corrida quedó colgada |
| **Filas leídas y filas escritas, por tabla** | Si no coinciden y nadie lo nota, se perdieron datos en silencio |
| Filas que fueron a cuarentena, y por qué regla | Es la mitad del reporte de calidad |
| La versión del código y del contrato que corrió | Un número de ayer puede no ser reproducible hoy |
| Cada excepción, con el contexto que haga falta para diagnosticar | Un log que dice «falló» no sirve |
| Cuando un dato esperado viene vacío: **el payload crudo** | Es lo único que permite entender después qué llegó |

Las reglas de formato, PII y retención están en `logs/README.md`. **Ningún log lleva datos personales
en claro.** El contenido de `logs/` no se versiona; su estructura sí.

Un conteo de filas que no cuadra es el bug más barato de encontrar y el más caro de no encontrar. Si
una tabla silver tiene menos filas que su bronze y la diferencia no está explicada por una regla de
cuarentena registrada, eso es un hallazgo, no una curiosidad.

**La regla dura:** si descubrís algo que contradice una suposición del proyecto, lo escribís en
`findings.md` **antes** de seguir escribiendo código. No al final de la sesión. La razón es práctica:
el hallazgo suele cambiar lo que estabas por implementar, y escribirlo primero es lo que te obliga a
notarlo.

**Un hallazgo bien escrito tiene cuatro partes**, y así están los cuarenta y ocho que ya hay:

```
## F-0NN · [la afirmación, en una línea, no «problema con X»]

**Dónde salió.** El comando o el archivo donde apareció.
**Qué pasaba.** El mecanismo, con la cifra medida.
**Por qué importa.** La consecuencia de negocio, no la técnica.
**Qué se cambió.** El archivo y la línea.
**Regla que deja.** Qué revisar la próxima vez para que no vuelva.
```

La última parte es la que vale. Un hallazgo sin regla es una anécdota.

**La bitácora es parte del trabajo, no un extra.** El commit dice qué cambió; la bitácora dice por
qué, con qué fricción, y qué quedó a medias. Sin ella, quien retome mañana —Eduardo o un agente—
empieza de cero. Incluí lo que no funcionó: un camino descartado con su razón vale más que tres
cosas que salieron bien.

---

## 5 · Qué validador le pone a cada entregable

Esta es la parte que más se subestima. «Corrió sin error» no es una validación: es la ausencia de una
excepción, que no es lo mismo. Un entregable de datos sin validador declarado es una afirmación sin
respaldo, y en este proyecto esas no se aceptan ni de Eduardo ni de Federico.

### Los cinco niveles

Van de menos a más. Cada nivel supone los anteriores: no se salta.

| Nivel | Qué comprueba | Con qué | Qué deja como evidencia |
|---|---|---|---|
| **V1 · Esquema** | Que las columnas existan, con el tipo y la nulabilidad declarados | `pandera` | El contrato en `data_platform/contracts/` |
| **V2 · Calidad** | Rangos, dominios de los enums, unicidad de la llave, cardinalidades | `pandera` + el reporte DQ | Filas en cuarentena, contadas y con su regla |
| **V3 · Invariante de negocio** | Que lo que la tabla afirma pueda ser verdad en un banco | `pytest` | Una prueba por invariante, con su nombre en español |
| **V4 · Relectura en el destino** | Que lo que escribiste esté realmente ahí | consulta al destino real | El conteo y la comparación, logueados |
| **V5 · Validación estadística formal** | Que una variable tenga señal, y de qué tamaño | prueba de hipótesis + tamaño del efecto | El estadístico, los grados de libertad, el p-valor **y el tamaño del efecto** |

**V3 es el nivel que casi nadie pone y el que encuentra los bugs caros.** Un invariante de negocio no
es un rango: es una afirmación que un banquero reconocería. Ejemplos reales de este dominio:

- La suma de los saldos por producto de un cliente no puede superar la suma de sus límites.
- Un producto abierto no puede tener fecha de apertura posterior al corte de la tabla.
- La deuda de un cliente al corte no puede usar una cotización de una fecha posterior al corte
  —exactamente el bug de la §8.2—.
- Si un producto no es valorable, no puede desaparecer del cálculo: tiene que aparecer **contado
  aparte**. Ese fue el bug que aprobaba al 19.59 % de la cartera.

**V5 lleva tamaño del efecto, siempre.** Un p-valor dice si el efecto existe; el tamaño del efecto dice
si sirve para decidir. Con 150 000 clientes casi todo sale significativo, así que un p-valor solo es
ruido con autoridad. Si afirmás que una variable sirve, va acompañada de su razón financiera primero,
la prueba formal después, y la magnitud siempre.

### Qué nivel exige cada entregable tuyo

| Entregable | Nivel mínimo | Lo que no alcanza |
|---|---|---|
| Contratos de calidad `DAT-03`/`DAT-04` | **V2** | Un contrato que valida solo tipos |
| Reporte DQ `DAT-05` | **V2** | Un porcentaje sin el conteo absoluto al lado |
| Cuarentena `DAT-06` | **V2** | Descartar filas sin registrar cuántas ni por qué |
| Silver `DAT-07`–`DAT-09` | **V3** | Que el conteo de filas cuadre |
| `credit_features_asof` `DAT-10` | **V3 + prueba de fuga** | Ya existe `tests/data/test_feature_contract.py`: tiene que seguir en verde |
| `product_policy` `DAT-11` | **V3** | Que la tabla exista. Hoy está **entera en NULL** y existe |
| Espejo en Databricks `DAT-13` | **V4** | Que la carga no haya tirado excepción |
| Export a Postgres `DAT-14` | **V4** | El `rowcount` que devuelve el driver |
| Capacidad de pago `ML-04` | **V5** | Un R² o un AUC sin mirar la distribución por clase |
| SCM `SCM-01`–`SCM-08` | **V3** + la suite con `SCM_ENABLED=false` | Las 26 pruebas en verde con la bandera encendida nada más |

### Las tres preguntas antes de declarar un entregable terminado

1. **¿Qué afirma esto que podría ser falso sin que nada se caiga?** Esa es la prueba que falta. Si la
   respuesta es «nada», el entregable no afirma nada útil.
2. **¿Qué pasa si el camino raro es el normal?** El estimador de capacidad **se abstiene en el 94 % de
   los casos**: lo que parecía la excepción era la regla. Mirá la frecuencia real de cada rama antes de
   decidir cuál merece cuidado.
3. **¿La prueba falla si rompo el código a propósito?** Rompelo y comprobalo. Una prueba que pasa con
   una lista vacía, o un invariante sobre un `DataFrame` sin filas, no está probando nada — y ambas
   cosas pasaron en este repo.

---

## 6 · Cuánto rigor — esto es lo que el otro lado está haciendo

No es una exigencia abstracta. Son los cinco patrones de bug que **se midieron** en este repo, y
ninguno de los cinco fallaba de forma ruidosa. Úsalos como lista de revisión sobre tu propio código.

### 1 · Un dato ausente sustituido por el valor neutro

Apareció **tres veces en el mismo archivo**. El caso grave: el motor de elegibilidad descartaba las
obligaciones que no podía valorar —límite nulo, tasa nula— y seguía calculando el ratio de
endeudamiento con la deuda incompleta. Resultado: **aprobaba al 19.59 % de los clientes con crédito
sabiendo que no tenía toda su deuda**. Fallaba abierto, en la dirección que le cuesta dinero al banco
y le da un crédito impagable al cliente.

Para tu capa: un `COALESCE(x, 0)` sobre un importe es una decisión de negocio disfrazada de higiene
de SQL. Cero no es «no sé». Si una tasa falta, la fila no es valorable y hay que decirlo, no ponerle
cero. Buscá cada `COALESCE`, cada `fillna`, y cada `else` que acompañe a un `if dato is not None`, y
preguntá qué pasa si ese camino es el normal y no el excepcional.

### 2 · Medir contra el corpus propio es medir el corpus

El detector de inyección se endureció tres veces. Cada vuelta llegó al **100 % sobre su propia
ronda**, y la siguiente ronda ciega —escrita después de congelar el detector— dio **42 %, luego
91.7 %, luego 28.6 %**. No generaliza, y los números lo dicen sin ambigüedad.

Para tu capa: un contrato de pandera que pasa sobre la muestra con la que lo escribiste no mide nada.
La cifra que vale es la de una partición que no mirabas cuando lo escribiste. Y si un control no
generaliza, la salida no es perfeccionarlo: es mover la garantía a una capa que no dependa de él y
dejarlo declarado como observabilidad, **con los dos números a la vista**.

### 3 · Antes de tratar una columna como objetivo, mirá su distribución por clase

Se probaron seis candidatos a variable objetivo y **ninguno es aprendible**. `days_past_due` no son
días de mora: toma siete valores y las seis cubetas no-cero son equiprobables —χ² = 4.51, 5 grados de
libertad, **p = 0.48**—. Una cartera real decae por tasas de traspaso, no uniformemente. `fraud_score`
no sale de un modelo: es Uniforme(0,100) con fraude y Uniforme(0,30) sin fraude, y su AUC de 0.8469 la
explica ese esquema sin residuo, con teórica 0.8464.

Esto es directamente tu ítem `ML-04`. Siete valores equiprobables, o dos uniformes de distinto rango,
no son fenómenos medidos: son un generador sintético. **Razón financiera primero, validación formal
después, y el tamaño del efecto siempre** — un p-valor sin tamaño de efecto no dice si la variable
sirve para decidir.

### 4 · Lo que compara representaciones se prueba contra la salida real

El validador de cifras comparaba números y la respuesta escribe texto: `3.375` se publica como
«338 %». Y el tokenizador leía «9000» como «900» por la alternancia del regex, así que una cifra
**correctamente anclada** aparecía como inventada en el camino feliz. Ese es el falso positivo por el
que alguien termina apagando un control.

### 5 · Un control de texto se prueba en el idioma en que llega

En español el pronombre se adosa al verbo **y le mueve la tilde**: «muestra» pasa a «muéstrame». Un
patrón escrito en inglés pasa las pruebas en inglés y deja pasar la mitad de lo que llegaría de
verdad, en silencio. El dataset tiene **cero portugués**, así que todo caso en portugués es
construido y hay que declararlo como tal.

### De forma, pero muerde

- Un `\s` escrito con doble barra dentro de una cadena `r"…"` significa «barra literal más s».
  Compila sin error y **nunca coincide**. Entraron quince en una sola vuelta de edición.
- **`F-048`:** una herramienta de calidad fijada en dos lugares con versiones distintas no es un
  control redundante, es un control que se contradice a sí mismo, y la contradicción sale recién en el
  commit. `ruff` estaba en 0.16.9 en local, 0.7.4 en pre-commit y «la última» en CI. Si fijás una
  versión en `.pre-commit-config.yaml`, el mismo número va en las dependencias.

---

## 7 · El método — cómo se trabaja de este lado

Esto no es una lista de buenas intenciones: es el ciclo que produjo los cuarenta y ocho hallazgos y
los doce ADR, y la razón por la que el ciclo del agente cerró sin un solo número inventado. Copialo.

### 1 · Nunca trabajes solo

Es la regla de Eduardo y es la que más cambia el resultado. Ningún entregable sale de un solo pase.

- **Antes de escribir código**, el diseño se escribe y **se valida con la persona**. Un ADR con la
  decisión y sus alternativas, no un párrafo. Si Federico no vio el diseño, no empieces a
  implementarlo: la probabilidad de que lo que entendiste no sea lo que quería es alta, y el costo de
  descubrirlo después de trescientas líneas es de horas.
- **Después de escribir código**, pasa un **agente supervisor** que revisa con otro criterio. No para
  que diga «se ve bien»: para que busque específicamente las contradicciones entre lo que el documento
  declara y lo que el código hace. Así se encontraron dos de las cuatro cifras huérfanas. Las otras
  dos las encontró una prueba de invariante que yo mismo escribí **después** del supervisor — los dos
  pasos encuentran cosas distintas y ninguno reemplaza al otro.
- **Cada paso importante se corrobora con la persona.** No cada línea: las decisiones. Si una elección
  cambia lo que el sistema le dice a un cliente, o cambia un número que el jurado va a ver, se
  pregunta antes.

### 2 · Validá el diseño antes del código, no el código después del diseño

Un bug de concepto cuesta mil veces más que un bug de sintaxis, y ninguna prueba lo encuentra: las
pruebas comprueban que el código hace lo que dijiste, no que lo que dijiste esté bien. Tres de los
cinco patrones de la §6 eran bugs de concepto que pasaban todas las pruebas.

Para datos, «validar el diseño» significa concretamente: antes de construir una tabla gold, escribí
qué afirma cada columna, de dónde sale, y qué tendría que ser verdad para que esa afirmación se
sostenga. Si no podés escribir eso, no sabés todavía qué estás construyendo.

### 3 · Razón primero, estadística después, magnitud siempre

El orden no es decorativo:

1. **¿Por qué esta variable debería predecir esto, en términos de negocio?** Si no hay una razón
   financiera que puedas decir en una frase, el resto es minería de ruido.
2. **La prueba formal**, con su estadístico y sus grados de libertad.
3. **El tamaño del efecto**, siempre, al lado del p-valor.

Así se descubrió que ninguna columna del dataset es un objetivo aprendible: la razón financiera no
cerraba —una cartera real no decae uniformemente— y la prueba formal lo confirmó con `p = 0.48`.
Primero fue la sospecha de negocio.

### 4 · Cuando algo no tiene sentido de negocio, investigá en vez de defender

Un AUC de 0.85 sobre un dataset sintético no es una buena noticia: es una señal de que algo está mal.
`fraud_score` daba exactamente eso y resultó ser dos distribuciones uniformes. Si un resultado es
mejor de lo que el problema permite, el bug está en la medición.

La forma de equivocarse acá es defender el número. La forma de acertar es ir a mirar la distribución.

### 5 · Dejá el límite por escrito, con su número

Un entregable que declara lo que **no** logra vale más que uno que lo esconde, y con un jurado técnico
es la diferencia entre que te crean el resto o no.

Los tres ejemplos que ya están en el repo, y que conviene imitar:

- El detector de inyección publica sus cifras de no generalización —**42 %, 91.7 %, 28.6 %**— y lleva
  una lista con los **diez ataques que no detecta**, declarados en su propio apartado. Un corpus donde
  todo se detecta solo demostraría que fue escrito para el detector.
- `ML-03` se entrena y **se reporta que no discrimina**, con la evidencia de por qué el dataset no lo
  permite.
- `agent/core/verifier.py` devuelve `None` y no `0.0` cuando no hubo escrituras, porque una tasa de
  fallo de cero sobre cero escrituras no es un sistema confiable: es uno que no hizo nada.

**Abstenerse es un resultado válido.** Se mide aparte y no se penaliza. Lo que sí se penaliza es
afirmar.

### 6 · Escribí el hallazgo antes de seguir

Repetido a propósito, porque es el paso que se saltea. El hallazgo casi siempre cambia lo que estabas
por implementar, y escribirlo primero es lo que te obliga a notarlo. Si lo dejás para el final de la
sesión, ya escribiste código sobre una suposición que sabías falsa.

---

## 8 · Las reglas no negociables que te tocan

Las siete están en `CLAUDE.md`. Estas cuatro caen de lleno en tu capa:

1. **Nada se cae en silencio.** Toda llamada externa —S3, DuckDB, Databricks, Postgres, MLflow— va en
   `try/except`, con un mensaje visible y un log que alcance para diagnosticar después. No
   `except: pass`. No un log que diga «falló».
2. **Falla cerrado.** Si algo no carga, el sistema no aprueba: escala y lo dice. Nunca un valor por
   defecto que permita seguir.
3. **Toda escritura se vuelve a leer** antes de afirmar que ocurrió. Aplica a `DAT-14` y a cualquier
   carga a Databricks.
4. **Cero secretos en git.** `.env` y `materiales/` fuera —los PDFs del reto traen las llaves de AWS
   en texto plano—. `gitleaks` corre en pre-commit y en CI, y si lo esquivás se ve en el log.

Y un contrato que no es cortesía: **con `SCM_ENABLED=false` el sistema tiene que funcionar idéntico y
toda la suite tiene que seguir en verde.** Esa bandera es el instrumento que mide el aporte del SCM
como tercer brazo de la evaluación —`baseline`, `tools`, `tools_scm`—. Si el sistema deja de
funcionar sin el SCM, el aporte del SCM deja de ser medible, y con él se va la parte más original de
la propuesta.

---

## 9 · Cómo se cierra una sesión

Tres cosas, siempre, en este orden. No es opcional y no se hace tres días después.

```bash
python -m scripts.worklog "en qué trabajaste"
make checklist
git commit -m "Nuevo (DAT-11): descripción legible en español"
```

Si la evidencia de un ítem es que unas pruebas pasan y no que un archivo exista:

```bash
python -m scripts.checklist --done DAT-11 --note "por qué quedó cerrado"
```

**Antes** de empezar una tarea, identificá qué ítem mueve. **Al terminarla**, nombrá el ítem en el
commit.

### Mensajes de commit

Código en inglés con `snake_case`; documentación, políticas y **mensajes de commit en español**.

Formato: `Tipo (ÍTEM): qué cambió, en español`. Tipos: `Nuevo`, `Corrige`, `Mejora`, `Docs`,
`Pruebas`, `Infra`, `Limpieza`, `Revierte`.

El asunto tiene que entenderse **sin abrir el diff**. El cuerpo explica el porqué, no el cómo.

- Bien: `Nuevo (DAT-08): la capa silver convierte todos los montos a dólares con la tasa del día`
- Mal: `feat(silver): normalize enums`

### Ramas y push

Ramas `trabajo/`, `arreglo/`, `docs/`. `main` está protegida: PR con CI en verde.

**El push lo decide la persona, no el agente.** Commits locales sí; `git push` solo si Federico lo
pide explícitamente.

---

## 10 · Lo que no hay que hacer, y por qué

- **No simules la parte difícil.** Si un modelo no converge o una carga no se puede verificar contra
  el destino real, eso es el resultado y se reporta así. Un número inventado en una capa de datos
  viaja hasta una cifra que el sistema le dice a un cliente sobre su crédito. En una revisión previa
  de esta rama se descartaron dos modelos y unas cuatrocientas líneas precisamente por eso.
- **No «mejores» algo del otro lado de la frontera.** Está en la §1 y es la causa más común de
  conflicto.
- **No trates el diccionario de datos como fuente.** Miente en siete puntos. Medí.
- **No cierres un ítem porque el archivo existe.** `make checklist` distingue `avanzado` de
  `terminado`, y un esqueleto con tipos no es un entregable.
- **No afirmes que algo funciona sin haberlo corrido.** Si corriste las pruebas y dos fallan, decilo
  con la salida. El proyecto tiene una regla explícita de que abstenerse es un resultado válido: se
  mide aparte y no se penaliza. Eso también vale para vos.

---

## 11 · Si algo no te cierra

Si una instrucción de este documento contradice lo que ves en el código, **el código gana y el
hallazgo va a `findings.md`**. Pasó ya tres veces en este repo: la política declaraba una abstención
que el motor no implementaba, el documento de seguridad prohibía la lectura que él mismo exigía, y un
hook de lint pedía lo contrario a la práctica vigente. Los tres se encontraron porque alguien
desconfió de la documentación y fue a mirar.

Y si el resultado de algo no tiene sentido de negocio, **investigá en vez de defenderlo**. Casi
siempre hay un bug, y es la forma en que se encontraron los cinco patrones de la §5.
