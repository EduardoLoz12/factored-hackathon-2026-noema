# 07 · Semantic Cognition Matrix (SCM-lite) — especificación

**Dueño: Federico Vargas.** Este documento es tu tarea completa. Si lo lees y sigues, no necesitas nada más del resto del repo.

---

## 1. En una frase

Construir el **estado semántico** que se sitúa entre el lenguaje del cliente y la decisión del sistema: una estructura tipada que guarda **qué sabe el agente, cómo lo sabe, qué le falta, y si algo se contradice**.

## 2. Por qué existe (el objetivo de negocio)

El reto exige que el agente **pregunte en vez de adivinar** y que sepa **cuándo no actuar**. Sin el SCM, eso sería un juicio del modelo de lenguaje: opaco, no testeable, distinto en cada corrida.

Con el SCM se vuelve **computable**. `missing_evidence()` devuelve un conjunto; si no está vacío, el orquestador pregunta en vez de decidir. Eso no es una preferencia de estilo: es la diferencia entre poder demostrarle al jurado que el sistema se detiene por una razón verificable, o pedirle que nos crea.

El segundo objetivo es **procedencia**. Cada hecho sabe de dónde vino: de qué tabla, de qué modelo y versión, de qué política. Con eso podemos medir **aserciones sin soporte** — una respuesta que afirma algo cuyo hecho no existe en el estado o no tiene fuente. Esa métrica es la prueba empírica de que el SCM aporta.

## 3. Cómo alimenta el proyecto

Se evalúan **tres configuraciones** sobre exactamente los mismos casos:

| Brazo | Qué es |
|---|---|
| `baseline` | LLM con documentos, sin tools ni política |
| `tools` | Agente completo con tools y motor de reglas, **SCM apagado** |
| `tools_scm` | Lo mismo, **SCM encendido** |

Si `tools_scm` reduce las aserciones sin soporte y mejora la abstención apropiada frente a `tools`, tenemos una **prueba empírica**, no una afirmación de arquitectura. Si no las reduce, lo reportamos igual — eso también es rigor y el rubro lo premia.

Por eso la bandera `SCM_ENABLED` no es opcional ni cortesía: **es el instrumento de medición**.

## 4. Alcance

**Dentro:** un archivo, `agent/cognition/scm.py`, más sus tests en `tests/cognition/`.

**Fuera:** todo lo demás. No toques `data_platform/`, `ml/`, `agent/core/`, `agent/tools/`, `agent/policies/`, `api/`, `ui/` ni `eval/`. Si necesitas que un dato entre al estado, **pídelo** — Eduardo lo inyecta desde el orquestador. `make review` marca cualquier commit que cruce esa frontera.

**No portes Samantha/LUMA.** Python plano, sin dependencias nuevas fuera de las que ya están en `pyproject.toml`. Si crees que necesitas una, pídela primero.

## 5. El contrato

`agent/cognition/scm.py` expone `SemanticState` con **exactamente cuatro métodos públicos**. Ninguna otra parte del sistema importará nada más de este módulo.

```python
assert_fact(subject: str, predicate: str, value: Any, source: Source,
            confidence: float = 1.0) -> None
missing_evidence() -> set[str]
contradictions() -> list[Contradiction]
snapshot() -> dict
```

El esqueleto con firmas, tipos y docstrings ya está en el repo: **`agent/cognition/scm.py`**. Ábrelo, es tu punto de partida. Los `NotImplementedError` marcan exactamente lo que falta.

### 5.1 `assert_fact`

Registra un hecho como una tripleta con procedencia.

- `subject` — la entidad: `"customer"`, `"product"`, `"request"`, `"policy"`.
- `predicate` — la relación: `"has_risk_band"`, `"affordable_payment"`, `"requested_amount"`, `"identity_verified"`.
- `value` — el valor. Cualquier tipo serializable a JSON.
- `source` — **obligatorio**. De dónde salió: qué capa, qué artefacto, qué versión.
- `confidence` — 0.0 a 1.0. Un hecho leído de la base es 1.0; uno inferido del lenguaje del cliente, menos.

Reglas:
- Un hecho **nunca se sobrescribe en silencio**. Si llega un valor distinto para la misma `(subject, predicate)`, ambos quedan registrados y aparece una contradicción.
- Un hecho **sin `source` no se acepta.** Debe lanzar `ValueError`.
- `confidence` fuera de `[0, 1]` debe lanzar `ValueError`.

### 5.2 `missing_evidence`

Devuelve el conjunto de slots requeridos que todavía no tienen hecho conocido.

Los slots requeridos dependen de la intención declarada. Para `CREDIT_ELIGIBILITY` el mínimo es:

```
identity_verified · requested_amount · currency · product_type
```

Si el conjunto **no está vacío**, el orquestador **pregunta en vez de decidir**. Ese es el comportamiento que el reto premia.

### 5.3 `contradictions`

Devuelve la lista de conflictos detectados. Tres tipos, en orden de importancia:

1. **Valor en conflicto** — dos hechos con la misma `(subject, predicate)` y valores distintos. Ejemplo: el cliente dice que gana 5 000 y la base dice 1 200.
2. **Conflicto de procedencia** — el mismo predicado afirmado por una fuente de alta confianza (la base) y por una de baja (el lenguaje del cliente). Gana la base, pero **queda registrado**.
3. **Violación de precondición** — un hecho que requiere otro que no existe. Ejemplo: `product` tiene `eligibility_decision` pero `customer` no tiene `identity_verified`.

Cada contradicción lleva los dos hechos en conflicto y su tipo. **El SCM no las resuelve** — las reporta. Quien decide qué hacer es el motor de reglas.

### 5.4 `snapshot`

Devuelve un `dict` serializable a JSON con todo el estado: hechos con su procedencia y confianza, evidencia faltante, contradicciones y `epistemic_status`.

`epistemic_status` es uno de:

| Estado | Cuándo |
|---|---|
| `COMPLETE` | Sin evidencia faltante y sin contradicciones |
| `INCOMPLETE` | Hay evidencia faltante |
| `CONFLICTED` | Hay contradicciones, haya o no evidencia faltante |

Este `snapshot` se pinta tal cual en el **panel Caja de Vidrio** del frontend. Es lo que el jurado ve en vivo mientras conversa con el agente — literalmente tu trabajo en pantalla.

## 6. El ejemplo que tiene que funcionar

Frase del cliente:

> «Estoy pensando sacar un préstamo de unos 5 millones, pero últimamente he estado bastante justo de plata.»

Estado esperado después de la etapa Understand:

```
intent            = CREDIT_ELIGIBILITY
requested_amount  = 5_000_000        (source: language, confidence 0.8)
currency          = UNKNOWN
financial_stress  = PRESENT          (source: language, confidence 0.6)
identity_verified = False
missing_evidence  = {identity_verified, currency, product_type}
epistemic_status  = INCOMPLETE
```

Y después de que el orquestador consulte la base y los modelos:

```
customer  has_risk_band      LOW          (source: model noema_pd v3)
customer  affordable_payment 1_250_000    (source: model noema_capacity v1)
product   requires_score     680          (source: table gold.product_policy)
request   governed_by        policy_v1    (source: policy eligibility_v1.yaml)
```

## 7. Cómo sabes que terminaste

```bash
pytest tests/cognition/ -v
```

`tests/cognition/test_scm_contract.py` son las **pruebas de aceptación**. Hoy se saltan solas porque el módulo está sin implementar; en cuanto `SemanticState` deje de lanzar `NotImplementedError`, corren de verdad. **Cuando pasen todas, terminaste.**

Las entradas de ejemplo están en `tests/fixtures/scm_inputs.json`. No necesitas base de datos, ni modelo de lenguaje, ni haber corrido la ingesta.

Además:

```bash
SCM_ENABLED=false pytest        # la suite completa debe seguir en verde
ruff check agent/cognition/     # lint limpio
```

## 8. Fechas

| Día | Qué debe existir |
|---|---|
| D2 · 28-sep | Tipos, `assert_fact`, `missing_evidence`, sus tests en verde |
| D3 · 29-sep | `contradictions` y `snapshot` con procedencia |
| D4 · 30-sep | Endurecido contra entradas ambiguas y contradictorias; cobertura alta |
| D5 · 1-oct | Eduardo lo integra tras la bandera; tú corriges lo que salga del uso real |
| D6 · 2-oct | **Congelado.** Escribes la sección neurosimbólica de la documentación |

## 9. Cómo trabajar en el repo

```bash
git pull
git checkout -b feat/scm-<lo-que-hagas>
# ... trabajas en agent/cognition/ y tests/cognition/ ...
pytest tests/cognition/ -v
git commit -m "feat(scm): ..."
git push -u origin feat/scm-<lo-que-hagas>
```

PR contra `main`. Commits convencionales. **No hagas push directo a `main`.**

Si algo del contrato no te cierra, **dilo antes de implementarlo**. Cambiar el contrato el día 4 cuesta más que discutirlo el día 1.
