# Política de crédito

La fuente de verdad es [`agent/policies/eligibility_v1.yaml`](../agent/policies/eligibility_v1.yaml),
**versión 3**, vigente desde el 2-oct-2026, con corte de datos **2025-12-31**. Esta página
explica qué decide y por qué; el YAML dice exactamente cómo.

**La idea, en una línea:** no se predice quién incumple; **se calcula cuánto puede pagar**,
y de ahí sale qué producto le cabe.

---

## 1 · Por qué una política y no un modelo

Porque está demostrado que este dataset no contiene la decisión de suscripción. Predecir
qué producto tiene un cliente desde su perfil da **AUC 0.4973** contra un control de
0.5000, y el límite asignado no depende del score ni del ingreso: la tabla de límite por
score × ingreso es plana (F-034). No es que el modelo saliera flojo — es que no hay nada
que aprender ahí.

Lo mismo con el riesgo. `days_past_due` no son días de mora: toma siete valores y las seis
cubetas no-cero son equiprobables (χ² = 4.51, gl 5, **p = 0.48**). La causa raíz es que
productos y transacciones se generaron por separado: el **18.7 %** de las transacciones
ocurre antes de que exista la cuenta que las contiene. La cadena completa está en
`docs/knowledge/findings.md`, F-017 a F-034, y la decisión en `ADR-0006`.

**Consecuencia honesta:** la política **declara siempre que no evalúa estado de mora**,
porque el dato no lo permite. Mejor decir «esto no lo sé» que dar una cifra que no se
sostiene.

---

## 2 · El cálculo, en cinco pasos

1. **Cuota de cada producto vigente.** Un préstamo amortiza a cuota fija sobre su plazo
   **total**; una tarjeta es revolvente y su obligación es el **pago mínimo sobre el saldo
   dispuesto**.
2. **Carga mensual** = suma de esas cuotas.
3. **DTI** = carga ÷ ingreso mensual, ambos en USD.
4. **Margen** = (tope de DTI × ingreso) − carga.
5. **Monto máximo por producto**, invirtiendo la amortización sobre ese margen, a cada
   plazo ofertable.

### Umbrales

| Parámetro | Valor | Por qué |
|---|---:|---|
| DTI máximo | 40 % | estándar de suscripción en banca de consumo |
| DTI de corte duro | 60 % | por encima no se ofrece nada aunque el cálculo dé margen |
| Productos de crédito simultáneos | 4 | tope de concentración por cliente |
| Exposición sobre ingreso anual | 3.0× | crédito ya concedido, no dispuesto |
| Antigüedad mínima | 6 meses | antes de conceder un segundo producto |

### La posición financiera completa

Las cuentas e inversiones entran como **reservas** —ahorro y corriente al 100 %, inversión
al 70 % por fricción de liquidación— y hacen dos cosas: son **requisito** (hipotecario 3
meses de cuota, personal 1, tarjeta 0) y son **factor compensatorio** (reservas ≥ 6 meses
de la carga suben el tope de DTI del 40 % al 45 %, sin saltar nunca el corte duro del
60 %).

---

## 3 · Las reglas, en orden

La primera que falla decide, y su veredicto se publica: el panel las muestra una por una.

| Id | Exige | Si falla |
|---|---|---|
| `R1_antiguedad` | antigüedad ≥ 6 meses, si ya tiene crédito | se dice cuántos meses lleva y cuántos pedimos |
| `R2_numero_de_productos` | menos de 4 productos de crédito | se dicen los que tiene y el máximo |
| `R3_corte_duro_de_dti` | DTI < 60 % | se dice su DTI y el límite |
| `R4_exposicion_sobre_ingreso` | exposición ≤ 3× ingreso anual | se dicen las veces y el tope |
| `R5_margen_disponible` | margen > 0 | se dice su carga actual y el tope aplicado |
| `R7_monto_minimo` | el monto que le cabe ≥ mínimo del producto | por producto |
| `R8_segmento` | el producto está disponible para su segmento | por producto |

**`R6_cumplimiento` se retiró** y el hueco en la numeración queda a propósito. Su umbral
del 5 % habría rechazado al cliente mediano —el cumplimiento mediano de la cartera es
3.81 %— y no hay calendario de vencimientos con el cual calcularla (F-029, F-030). Nunca
llegó a ejecutarse: el motor no la leía. Ver F-038.

Un rechazo por regla **dice las dos cifras**: la del cliente y el umbral que no alcanza.
Decirle a alguien que sus cuotas comprometidas son el 99 % de su ingreso, con el límite al
lado, es haber resuelto su consulta — por eso un rechazo explicado cuenta como resolución
y no como escalamiento (F-052).

---

## 4 · El catálogo

| Producto | Amortización | Tasa anual | Plazos | Monto |
|---|---|---:|---|---|
| Tarjeta Crédito | revolvente | 31.52 % | 48 | 500 – 100 000 USD |
| Préstamo Personal | cuota fija | 20.10 % | 24 · 48 · 72 | 1 000 – 150 000 USD |
| Préstamo Hipotecario | cuota fija | 8.98 % | 120 · 180 · 240 | 20 000 – 500 000 USD |

Las tasas son las medianas observadas por tipo de producto, que en este dataset sí
resultaron coherentes: rangos disjuntos y ordenados tarjeta > personal > hipotecario.

**Varios plazos por producto.** El plazo **no cambia la TEA** —la fija la tasa nominal con
su capitalización—, así que moverlo cambia la cuota y el monto que cabe sin tocar el costo
anual efectivo. A plazo más largo: cuota menor, monto mayor, reserva exigida menor e
**interés total mayor**, y ese último dato se declara en cada opción porque sin él un plazo
largo parece gratis. El efecto que importa: **convierte rechazos en ofertas**.

La tarjeta lleva un solo plazo a propósito: siendo revolvente, moverlo no cambiaría nada.

---

## 5 · Los tres errores de negocio que aparecieron al probar

Ninguno se ve sin ejecutar la política contra clientes reales.

1. **Una tarjeta no es un préstamo.** Amortizar una línea de 30 000 USD a 48 meses daba
   una cuota de 1 400 y un **DTI de 451 %**. Su obligación es el pago mínimo.
2. **La cuota no cambia con la edad del préstamo.** Calcularla sobre el plazo *remanente*
   daba, para un préstamo de 47 meses de vida, una cuota de **39 611 USD/mes**. Va sobre el
   plazo **total**; el remanente solo dice si la obligación sigue viva.
3. **La tarjeta pesaba por la línea completa y no por lo dispuesto.** Saldo mediano
   1 501 USD contra línea de 25 536: sobreestimaba la obligación **17 veces**.

---

## 6 · Lo que la política no hace

- **No evalúa mora**, y lo dice en cada decisión.
- **No usa un modelo de riesgo.** `ML-09` no existe: el sistema decide sin capacidad
  observada, lo declara, y recorta el margen al 80 % sin ofrecer el plazo más largo. Hay
  una prueba puesta para que, el día que exista, un fallo de carga **bloquee** en vez de
  aprobar.
- **No aprueba nada.** Cotiza una oferta y la registra; la concesión es de un humano.
