# Arquitectura

La tesis del sistema cabe en una frase: **separar la conversación de la decisión**. El
modelo entiende lo que el cliente dice y lo explica; ninguna cifra y ninguna elegibilidad
salen de él. Todo lo demás es la consecuencia de sostener esa frase.

---

## 1 · El recorrido de un turno

```
mensaje del cliente
      │
      ▼
┌─────────────────────┐   el texto se envuelve en un bloque con sello aleatorio.
│ guardrail de entrada│   Es un dato a interpretar, nunca una instrucción.
└─────────┬───────────┘   agent/guardrails/injection.py · AG-10
          ▼
┌─────────────────────┐   intención + slots. Determinista, para que el sistema
│ extracción          │   corra sin llave de LLM y las trazas se reproduzcan.
└─────────┬───────────┘   api/extraccion.py
          ▼
┌─────────────────────┐   0 · IDENTIFY   sin sesión no sale nada personal
│                     │   1 · UNDERSTAND falta un hecho → se pregunta
│   orquestador       │   2 · DECIDE     decide la política, no el modelo
│   seis etapas       │   3 · ACT        escribe solo si hay confirmación
│                     │   4 · VERIFY     relee lo escrito y ancla las cifras
│                     │   5 · ESCALATE   expediente estructurado al humano
└─────────┬───────────┘   agent/core/orchestrator.py · AG-06, ADR-0010
          ▼
┌─────────────────────┐   toda cifra de la respuesta tiene que venir de un tool
│ guardrail de salida │   de ESTE turno. Dos intentos y se escala.
└─────────┬───────────┘   agent/guardrails/grounding.py · AG-09
          ▼
   respuesta + traza
```

La traza no es un adorno: **lo que el cliente lee y lo que el panel muestra salen del
mismo turno**. No hay una ruta que conteste sin pasar por la máquina de estados.

---

## 2 · Las capas, y por qué están separadas

| Capa | Qué hace | Dónde |
|---|---|---|
| **Plataforma de datos** | S3 → bronze → silver → gold con dbt, contratos de calidad y cuarentena | `data_platform/` |
| **Herramientas** | once, con allowlist por rol; el permiso se valida **antes** de ejecutar | `agent/tools/` |
| **Política** | umbrales, catálogo y ocho reglas ordenadas, versionadas en YAML | `agent/policies/` |
| **Orquestador** | la máquina de seis etapas, sin LLM | `agent/core/` |
| **Cognición** | estado semántico con procedencia y contradicciones, tras una bandera | `agent/cognition/` |
| **Guardrails** | contención de inyección y anclaje de cifras | `agent/guardrails/` |
| **Evaluación** | conjunto retenido y los tres brazos | `eval/` |
| **API e interfaz** | diez rutas y una página, servidas desde el mismo origen | `api/` |

**La política está en YAML y no en código** porque un umbral de crédito lo discute alguien
de riesgo, no alguien que lee Python. Se versiona (`version: 3`) y el número viaja en cada
decisión, así que una respuesta de hace un mes se puede reconstruir.

**El SCM vive tras `SCM_ENABLED`** y con la bandera apagada el sistema funciona idéntico.
Esa bandera no es cortesía: es el instrumento que mide su aporte como tercer brazo de la
evaluación. La suite completa corre en los dos estados.

---

## 3 · Las decisiones que un jurado va a querer discutir

**La elegibilidad se calcula, no se predice** (`ADR-0006`). No es una preferencia de
diseño: está demostrado que el dataset no contiene la decisión de suscripción. Predecir
qué producto tiene un cliente desde su perfil da AUC 0.4973 contra un control de 0.5000,
y la tabla de límite por score × ingreso es plana. Ver `docs/01_data_audit.md` y los
hallazgos F-027 a F-034.

**La ruta canónica es DuckDB, el lakehouse es espejo** (`ADR-0002`). Un juez reproduce
todo con un comando y sin cuenta de nadie. Databricks Free Edition es serverless y no
puede leer el S3 de Factored, así que la ingesta va local y el espejo recibe los Parquet
ya convertidos.

**El `customer_id` viaja dentro del token, nunca en el cuerpo de la petición.** El cliente
no puede nombrar a otro cliente porque no hay parámetro donde hacerlo.

**La prosa del cliente es determinista** (`api/redaccion.py`). Si la frase la arma una
plantilla sobre las cifras que los tools publicaron, no queda ningún punto del camino
donde un número pueda aparecer sin respaldo. Y esa prosa **igual pasa por el verificador
de anclaje**: que el control se aplique a nuestra propia redacción, y no solo a la del
modelo, es lo que hace que la garantía valga.

**Toda escritura se vuelve a leer antes de afirmarla.** Si la relectura no coincide, no se
afirma: se escala. Es barato y casi nadie lo hace.

---

## 4 · Dónde está el estado

| Qué | Dónde | Por qué ahí |
|---|---|---|
| Analítica | DuckDB, **solo lectura** | la API no escribe en gold |
| Sesiones e intentos | DuckDB propio | el AccessGuard necesita contarlos |
| Expedientes y acciones | ledger separado | una escritura de negocio no vive junto a la analítica |
| Traza del turno | memoria, para el panel | el almacén auditable son los archivos de `logs/traces/` |

Los tres almacenes están separados a propósito: un fallo en uno no arrastra a los otros, y
el export a Postgres del serving no toca la base que el agente consulta.

---

## 5 · Lo que no hay

No hay cola de mensajes, ni caché, ni réplica. Una instancia, un proceso. El límite de
tasa vive en memoria, así que con más de una instancia sería por instancia. Está escrito
en `LIMITATIONS.md` y no insinuado: para la demostración es correcto, para producción no.
