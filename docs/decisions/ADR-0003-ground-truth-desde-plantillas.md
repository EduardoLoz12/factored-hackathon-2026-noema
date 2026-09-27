# ADR-0003 · El ground truth de evaluación se genera desde las plantillas del propio dataset

**Fecha:** 2026-09-26 · **Estado:** aceptado

## Contexto

El rubro exige **etiquetas válidas** y **juicios de relevancia fundamentados**, y exige medir alucinación. Pero en un sistema conversacional no existe «la respuesta correcta» a menos que alguien la escriba a mano, y escribir a mano más de cien conversaciones etiquetadas en ocho días no es realista. Es el punto donde la mayoría de los equipos va a improvisar.

La auditoría (F-001) mostró que las 200 000 transcripciones del dataset son **2 plantillas** con un solo intent y, crucialmente, con los valores **sin rellenar**:

```
Agente: Su saldo actual es {monto} {moneda} y su límite disponible es de {limite} {moneda}.
```

## Decisión

Usar esas plantillas como **esqueleto de generación**, rellenando los huecos con valores traídos de las tablas gold. Cada conversación generada queda acompañada de:

- el valor correcto de cada hueco, tomado de la base;
- el desenlace esperado — `resolve`, `clarify`, `abstain` o `escalate` — derivado del estado real del cliente y de la política, no de una opinión;
- la semilla que la produjo.

El generador vive en `eval/generator/` y es determinista con semilla fija.

## Consecuencias

- **La alucinación deja de ser una apreciación y pasa a ser una tasa.** Si el agente dice un número distinto al de la tabla, lo sabemos con certeza.
- **Las etiquetas son defendibles** ante el jurado: salen del dato, no de nosotros.
- **El portugués se resuelve de paso.** Las mismas plantillas traducidas a PT-BR generan el set en portugués, sin inventar clientes brasileños en un dataset que no los tiene. Se declara abiertamente que es sintético y se mide por separado.
- **Escala.** Podemos generar 120 casos o 1 200 variando montos, monedas, países y perfiles de riesgo.
- **Limitación honesta:** la diversidad lingüística de los casos está acotada por la de las plantillas. Se mitiga con variaciones redactadas a mano sobre el mismo esqueleto semántico, y se declara en `LIMITATIONS.md`.
