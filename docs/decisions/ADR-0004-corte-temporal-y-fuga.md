# ADR-0004 · Corte temporal y prevención de fuga de información

**Fecha:** 2026-09-27 · **Estado:** aceptado

## Contexto

El rubro exige explícitamente **prevención de fuga** y un **split retenido realista**. La etiqueta de riesgo disponible es `products.days_past_due`, que tiene 125 350 valores no nulos y ~15 % de casos positivos con corte en 30 días (F-002).

El problema: `products` es un **snapshot**, no una serie de tiempo. El dataset **no dice en qué fecha se midió** la mora, y `last_updated` por producto va de 2019 a 2026. Varias columnas de esa misma tabla reflejan el desenlace en vez de precederlo.

Si entrenamos ingenuamente con todas las columnas, el modelo aprende a leer el futuro: los números salen espectaculares y falsos. Un revisor con oficio lo detecta en dos minutos.

## Decisión

1. **Fecha de corte declarada: `2025-12-31`.** Las variables se construyen únicamente con información anterior a esa fecha. Evaluación sobre `2026-01-01` → `2026-06-17`.
2. **Columnas excluidas por riesgo de fuga**, y la razón de cada una:
   - `current_balance` — refleja el estado posterior al incumplimiento.
   - `last_transaction_date` — un cliente en mora deja de transar; la fecha codifica el desenlace.
   - `product_status` (`Blocked`, `Suspended`) — es consecuencia de la mora, no causa.
   - Cualquier agregado de `transactions` posterior al corte.
3. **La ambigüedad de la fecha del snapshot se declara como supuesto**, en este ADR, en `LIMITATIONS.md` y en la model card. No se presenta como hecho observado.
4. **Baseline honesto:** regresión logística usando **solo** `credit_score`. Si el modelo completo no le gana de forma clara en AUC y KS sobre el período retenido, lo reportamos así.
5. **Calibración obligatoria** (Brier + curva de calibración): una probabilidad que alimenta una política de crédito tiene que significar lo que dice, no solo ordenar bien.

## Alternativas consideradas

- **Split aleatorio.** Más fácil y con mejores números, pero irreal y penalizado por el rubro. Descartada.
- **Reconstruir una serie temporal de mora** desde `transactions`. Costoso y especulativo en ocho días; además no hay pagos de cuota identificables de forma confiable.
- **Ignorar el problema.** Descartada: es exactamente el error que el rubro busca.

## Consecuencias

- Menos variables disponibles y probablemente métricas más modestas. **Se acepta**: un AUC creíble vale más que uno inflado.
- La model card documenta la fecha de corte, las columnas excluidas y por qué.
- El supuesto sobre la fecha del snapshot es una limitación declarada, no un defecto oculto.
