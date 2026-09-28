# Cognición neurosimbólica: estado, evidencia y límites

El lenguaje propone hechos; `SemanticState` conserva tripletas tipadas con fuente, versión y confianza. No concede crédito ni resuelve conflictos. Sus cuatro métodos permiten al orquestador registrar hechos, consultar faltantes, inspeccionar contradicciones y mostrar el estado en Caja de Vidrio.

La identidad necesita el booleano `True` sobre `customer`; texto como `"true"` no verifica a nadie. La procedencia es obligatoria. Valores no serializables y números no finitos se rechazan. Se copian entradas y salidas para impedir cambios de evidencia por mutación externa. Los conflictos conservan ambos hechos; una contradicción domina el estado incompleto.

Una decisión sin identidad verificada produce violación de precondición. Dos valores distintos de la misma relación producen conflicto de valor; acuerdo entre lenguaje y una fuente de otra capa conserva la discrepancia de procedencia. Ninguna fuente sustituye silenciosamente otra.

## Integración pendiente del orquestador

Eduardo debe instanciar el estado por conversación, inyectar resultados de herramientas verificadas, preguntar por evidencia faltante y detener decisiones ante conflictos. `SCM_ENABLED=false` omite esa integración; la clase permanece determinista y no interpreta variables globales. Ejecutar la suite con esa bandera comprueba compatibilidad, pero no demuestra una ablación del orquestador que aún no existe.

Los snapshots contienen datos de la conversación. No deben registrarse sin redacción de PII; la autenticación y autorización pertenecen al orquestador. El SCM registra procedencia declarada, no autentica a quien llama.

## Evidencia

`tests/cognition/test_scm_contract.py` contiene 26 casos de aceptación y `test_scm_edge_cases.py` cubre entradas ambiguas y mutabilidad. La eficacia sobre grounding y abstención requiere comparar `tools` y `tools_scm` con el mismo conjunto retenido. No se afirma mejora empírica antes de esa evaluación.
