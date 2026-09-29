# Qué cambió al entrar tu rama — 29-sep-2026

Para Federico y para los agentes `data-etl` y `scm-cognition`.

Tu rama `trabajo/federico-data-cognition` está mergeada en `main`. Este documento
dice qué se verificó, qué se cambió al entrar, qué encontró la auditoría posterior
y qué de tu plan cambia por eso. Léelo antes de retomar: hay dos cosas que ya no
valen la pena hacer y una que cambia el objetivo del modelo.

Commits: `7975169` (merge), `c157a5c` (segunda pasada), `c6324a9` (la etiqueta).

---

## 1. Tu entrega, verificada ejecutando

No se revisó leyendo tus documentos: se corrió todo en un worktree aislado.

| Ítem | Estado | Cómo se comprobó |
|---|---|---|
| DAT-03 contratos pandera | **real** | `make audit` valida 13 tablas, 23 495 188 filas |
| DAT-04 reporte de calidad | **real** | 682 métricas en `noema_gold.dq_report` |
| DAT-05 cuarentena | **real** | 607 filas en `quarantine_transaction_fx` |
| DAT-06/07/08 dbt, silver, FX | **real** | `dbt build` PASS=25 ERROR=0 en 85 s |
| DAT-09 customer_360 | **real** | 150 000 filas |
| DAT-10 credit_features_asof | **real, sin fuga** | 141 445 filas, corte respetado |
| DAT-11 product_policy | cascarón | 9 filas, condiciones todas nulas |
| DAT-12 dq_report | **real** | materializado |
| DAT-13 Databricks | no ejecutado | falta host y token |
| DAT-14 Postgres | no ejecutado | `execute=False` por defecto |
| ML-04 capacidad | real, sin margen | ver §4 |
| SCM-01 a SCM-08 | **real** | **49 pruebas de cognición en verde**; en `main` estaban todas en skip |

El SCM cumple el contrato: exactamente los cuatro métodos públicos, sin extras, y
con `SCM_ENABLED=false` la suite completa sigue verde. Que las 26 pruebas de
aceptación pasen de verdad es el trabajo mejor cerrado de la entrega.

Marcaste DAT-11, DAT-13 y DAT-14 como parciales y no como terminados. Esa
honestidad se agradece y ahorra tiempo.

---

## 2. Tres cambios al entrar

**`scripts/review_contributions.py` vuelve a la versión de `main`.** Tu rama
reasignó la carpeta `tests/data/` a Federico y agregó el propio revisor como área
compartida. Con eso `make review` dejaba de reportar tus cruces de frontera. No es
un reproche sobre la intención — probablemente fue para que dejara de marcar tus
commits — pero el revisor no se edita desde la rama que revisa. Si el mapa de
fronteras está mal, se discute y se cambia en un commit propio.

**`tests/data/test_feature_contract.py` conserva la versión de `main`.** Tu cambio
era reformato y revertía el arreglo de ancho del commit `05d54d5`.

**Se declaró `encoding="utf-8"` en toda lectura y escritura de texto.** Este sí era
un bug real y tuyo no del todo: en Windows la codificación por defecto es `cp1252`,
así que `Path(...).read_text()` sin argumentos leía el SQL con acentos corrupto y
la prueba `test_dbt_cutoff_applies_to_operation_and_availability` fallaba comparando
contra `'Depósito'`. Afectaba también a `data_platform/contracts/audit.py` y a
`ml/training/capacity.py`, que escriben JSON con `ensure_ascii=False`. Corregido en
cuatro archivos. **Regla para adelante: ningún `read_text` ni `write_text` sin
`encoding="utf-8"`.**

Estado tras el merge: 57 pruebas pasan, 4 se saltan, `ruff` limpio, con y sin
`SCM_ENABLED`.

---

## 3. Lo que encontró la auditoría posterior

Seis hallazgos nuevos, todos en `docs/knowledge/findings.md` como F-012 a F-017.
El reporte visual con las gráficas está publicado aparte; pídele el enlace a
Eduardo.

### F-012 · `registration_branch_id` no es una llave foránea

Tu F-011 describía el síntoma: 149 995 referencias huérfanas. La causa es otra.
**La columna tiene 150 000 valores distintos para 150 000 clientes**, uno propio por
cliente, contra 350 sucursales. No apunta mal: no apunta. Se descartó normalizar
espacios, mayúsculas y el guion — no recupera ni una coincidencia.

Tu decisión de poner a NULL en vez de rechazar la fila era la correcta y se queda.

**Lo que sí se puede hacer y no estaba:** derivar la sucursal del cliente por
`products.opening_branch_id`, que sí es válida al 100 %. Cubre 139 578 de 150 000
clientes (93.05 %), y 28 189 sin ambigüedad. Vale como columna de `customer_360`.

### F-013 · El `amount_usd` de la fuente trae ruido de ±2 %

Tu pipeline recalcula el monto en dólares y guarda el de la fuente como
`reported_amount_usd`. Eso está bien y ahora sabemos por qué: el valor de la fuente
está **deliberadamente corrompido** con ruido uniforme multiplicativo de ±2 %.
Desviación observada 0.011675 contra 0.011547 que predice una uniforme(−2 %, +2 %),
curtosis −1.177 contra −1.2 teórico, KS 0.043 contra uniforme y 0.084 contra normal.
No es la tasa de compra ni la de venta: contra esas el error es mayor.

Tu decisión pasa de «defendible» a «la única correcta». Queda documentada con la
prueba.

### F-014 · Los nulos son dos fenómenos, no uno

104 de 287 columnas de silver tienen nulos, en dos regímenes que piden tratamientos
opuestos:

- **Estructural** — significa «no aplica». `days_past_due` y `credit_limit` son
  100 % nulos en Cuenta Ahorro, Cuenta Corriente, Tarjeta Débito, Inversión y
  Seguro. `merchant_name` es 100 % nulo salvo en Compra.
- **Inyectado** — el generador borró al azar a tasas redondas: `credit_score` 15 %,
  ingreso 20 %, `interest_rate` 10 %, `fraud_score` 20 %.

Se comprobó que el inyectado es aleatorio de verdad: la mora es 6.545 % entre
clientes sin `credit_score` y 6.550 % entre los que lo tienen. Se puede imputar sin
sesgar.

**Esto toca tu capa gold.** Lo estructural se codifica como categoría `no_aplica` y
no se imputa nunca; lo inyectado se imputa y lleva su indicador `_faltante`.

Aparte: **`complaints.origin_interaction_id` está vacía al 100 %** en las 67 095
filas. El camino queja → interacción no existe.

### F-015 y F-017 · No hay modelo de riesgo posible

Este es el que cambia el plan.

`days_past_due` solo existe en los tres productos de crédito. El universo
etiquetable son **84 926 clientes**, no 150 000, y la tasa de mora a 90 días es
**10.71 % por cliente, 7.52 % por producto**. Tratar el nulo como «al día» infla el
denominador un 64 %.

Y la etiqueta no se relaciona con nada. Diez variables medidas a nivel producto
sobre 125 350 filas, todas entre AUC 0.496 y 0.506 — incluida la utilización de
línea, que en banca real es el segundo predictor más fuerte. Cochran-Armitage sobre
tramos de score: **p = 0.43**. La mora va de 7.63 % bajo 600 a 7.32 % sobre 800.

El `credit_score` sí es coherente: correlaciona 0.356 con el ingreso y ordena por
segmento. **El problema es la etiqueta, no el score.**

`days_past_due` es una **Bernoulli(0.075166) sorteada de forma independiente por
producto de crédito**. La prueba: la tasa por cliente sigue exactamente
`1 − (1 − 0.075166)^k` según su número de productos — 7.36 % observado contra 7.52 %
predicho con uno, 14.76 % contra 14.47 % con dos, 21.18 % contra 20.90 % con tres.
El techo real del modelo es **AUC = 0.50**.

### F-016 · La normalización español/inglés no normalizaba nada

Tu `CASE` de dieciséis ramas en `stg_products` no colapsa ningún nivel. No hay
mezcla de idiomas: `product_type` está íntegramente en español, `transaction_type`
íntegramente en inglés. El idioma varía entre columnas, no dentro de una.

**No es culpa tuya:** `docs/01_data_audit.md` afirmaba que `product_type` venía en
inglés, y el `CLAUDE.md` usaba esa normalización como ejemplo. Ambos corregidos. El
`CASE` se conserva porque es defensivo y no cuesta nada.

---

## 4. Qué cambia en tu trabajo

### No rehagas esto

- **La llave de sucursal.** No hay nada que reparar. Tu política de NULL es final.
- **La normalización de enums.** El `CASE` se queda como está. No hay más pares que
  mapear.
- **La conversión FX.** Está bien y la conservación es exacta: razón 1.000000 y
  error absoluto máximo 0.00 en las tres monedas.

### Sí cambia

**ML-04, capacidad de pago.** Tu modelo entrena de verdad, con split temporal y
features rezagados sin fuga. El problema es el margen: `validation_mae` 92 369
contra `baseline_mae` 92 731, una mejora de 0.39 %. En USD el MAE es idéntico al
baseline porque el clipeo `min(baseline, pred)` impide estructuralmente ganarle, y
solo 825 de 14 820 filas cumplen la condición de elegibilidad.

Dos salidas, la que prefieras:
1. Presentarlo como **baseline de capacidad**, no como modelo, y decirlo así.
2. Quitar el clipeo y reportar sobre las 825 filas elegibles, con el intervalo.

Dado F-017, la opción 1 es coherente con el resto del discurso: en este dataset los
modelos no mandan, y demostrarlo es el entregable.

**DAT-11, catálogo de producto.** El dataset no trae condiciones de producto. No las
inventes ni esperes encontrarlas. Van a `LIMITATIONS.md` y las aporta
`agent/policies/eligibility_v1.yaml`, que es de Eduardo.

**DAT-09, customer_360.** Vale agregar la sucursal derivada de F-012 y los
indicadores `_faltante` de F-014.

---

## 5. Cómo reproducir todo esto

```bash
make setup
make audit                      # 13 tablas, ~2 min
cd data_platform/dbt && dbt build --profiles-dir . --target duckdb   # 85 s
```

Queda `data/noema.duckdb` con los esquemas `noema_silver` y `noema_gold`. Los
números de este documento salen de consultas directas sobre esa base; la semilla de
todo muestreo es `20260929`.

Si `make` no existe en tu entorno Windows, los pasos equivalentes son
`python -m data_platform.contracts.audit` y el `dbt build` de arriba.

---

## 6. Reglas que quedan para los dos

1. Ninguna lectura o escritura de texto sin `encoding="utf-8"`.
2. `scripts/review_contributions.py` no se edita desde una rama de trabajo.
3. Si un hallazgo contradice una suposición, va a `docs/knowledge/findings.md`
   **antes** de seguir codificando. F-012 a F-017 salieron de dudar de un resultado
   que no cuadraba, no de revisar código.
4. Ningún número de estos documentos se cita sin la consulta que lo produce.
