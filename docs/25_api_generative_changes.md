# Documentación de Cambios: Capa Generativa en la API (NLU y Drafting)

## Contexto
Tras una auditoría técnica profunda, se detectó que el sistema NOEMA implementaba un modelo de "Potemkin AI", donde la NLU (extracción de intenciones y slots) se realizaba mediante expresiones regulares y búsquedas de subcadenas estáticas, y la redacción de respuestas (Drafting) se lograba concatenando plantillas fijas en lugar de usar inferencia generativa real.

Para cumplir con los objetivos del hackathon de presentar un "AI-First Banking Core" sin alterar la lógica determinista y de control del agente (`agent/core/`, SCM, ni `NoemaCore`), se han implementado cambios arquitectónicos estrictamente en la capa de la API (`api/main.py`).

## Cambios Implementados

### 1. Extracción Estructurada por LLM (Slot Filling)
**Archivo Modificado:** `api/main.py`
**Función:** `_slots_from_message`

Se reemplazó la extracción frágil basada en expresiones regulares (`re.findall`) por inferencia estructurada usando Gemini.
- La API ahora construye un prompt que solicita la extracción en formato JSON de `product_type`, `requested_amount` y `currency`.
- El modelo devuelve la estructura solicitada, permitiendo al sistema entender el texto natural del usuario de manera robusta.
- Se ha mantenido la lógica original basada en regex **únicamente como fallback seguro** en caso de que la inferencia falle o falte una API key.

### 2. Generación de Texto Guiada (Generative Drafting)
**Archivo Modificado:** `api/main.py`
**Función:** `_run_orchestrator_turn` (callback `redactar`)

Se reemplazó la generación estática por la redacción fluida mediante LLM:
- En lugar de devolver cadenas preensambladas (`_draft_orchestrated_response(turn)`), el callback `redactar` ahora invoca un LLM (`_generate_with_llm`).
- **Seguridad Preservada:** El LLM recibe la decisión determinista y la información del cliente del orquestador en forma de contexto duro (`System Information`).
- **Grounding Activo:** Se instruye al modelo para que **no invente números** y la respuesta resultante sigue siendo validada por la función `CHECKER.revisar` del orquestador. Si el modelo alucina una cifra que no estaba en el estado del sistema, el `CHECKER` lo bloquea de inmediato tras el número máximo de intentos, escalando a un humano.
### 3. Reescritura Dinámica de Respuestas Estáticas (Fallback Drafting)
**Archivo Modificado:** `api/main.py`
**Función:** `chat_endpoint`

Se agregó una capa de envoltura (wrapper) generativa en el endpoint final de chat para procesar las respuestas que bypassan el orquestador y son resueltas internamente por las reglas duras de `NoemaCore` (por ejemplo, los comandos de verificación de identidad de la demo, mensajes de escalamiento final, o consultas de saldo simples).
- Antes, la API devolvía la cadena pre-programada exacta desde `core_result["msg"]`.
- Ahora, el texto estático es interceptado e inyectado como `System Information` en un prompt hacia el LLM.
- El modelo reformula el mensaje en tono conversacional y fluido basándose *exclusivamente* en los hechos del sistema, mitigando las alucinaciones sin necesitar pasar por el motor de verificación pesado.


## Límites Respetados (Restricciones del Usuario)
De acuerdo a las directrices:
- **No se modificó la lógica del Agente:** El ruteo de herramientas, el ledger, y el motor de políticas en `agent/core/` se mantienen deterministas y sin cambios.
- **No se modificó el SCM:** La lógica de `agent/cognition/scm.py` para medir procedencia, confianza y resolver contradicciones sigue inalterada.
- **No se alteró la clase `NoemaCore`:** Las reglas de escalamiento predefinidas y la evaluación rápida de intención (`SemanticCognitionMatrix.evaluate()`) se mantuvieron sin cambios, modificando únicamente la extracción de slots independiente y el ensamblado final de turnos orquestados.
- **DuckDB se mantuvo intacto:** No se intentó una migración a RDBMS para no romper dependencias de lectura y analítica de datos en el core agentico.

### 4. Corrección de Ruteo de Políticas y Prevención de Alucinaciones Inducidas por el Usuario
**Archivos Modificados:** `api/main.py`
**Funciones:** `_slots_from_message`, `chat_endpoint`, callback `redactar`

Tras la integración inicial, se detectaron errores de traducción de intent y conflictos severos con el verificador de anclaje (grounding) del orquestador:
- **Alineación de Entidades (Entity Resolution):** El LLM inicialmente extraía tipos de producto en inglés (ej. `"credit_card"`). La política determinista (`agent/policies/engine.py`) los rechazaba silenciosamente al esperar `"Tarjeta Crédito"`, provocando que devolviera un catálogo vacío y forzando respuestas default como `"Estas son las condiciones del producto"`. Se corrigió el esquema JSON en el prompt de extracción para forzar estrictamente los strings mapeados por el motor (`"Tarjeta Crédito" | "Préstamo Personal" | "Préstamo Hipotecario"`).
- **Protección contra Alucinaciones Pasivas (Orphan Figures):** Cuando un usuario solicitaba un límite (ej. `Tell me about credit cards for $7,000`), el LLM por cortesía repetía la solicitud (*"You asked about credit cards for $7,000..."*). El motor de verificación rígido de NOEMA (`CHECKER.revisar`) detectaba el número `7000` como no verificado (orphan figure) porque no provenía de la política, y bloqueaba la respuesta asumiendo que era una alucinación (escalando al humano por `relectura_fallida`).
- **Retroalimentación Dinámica (Dynamic Prompt Feedback):** Para solucionar esto, se actualizó el bucle del callback `redactar`. Ahora, si el verificador de NOEMA bloquea un intento del LLM por detectar números no anclados (`cifra_sin_anclaje`), la API pasa la alerta `_previous.motivo` al LLM en su segundo intento y le instruye rigurosamente a omitir cualquier número proveniente del cliente que no esté en la política oficial (`System Information`).
- **Tiempos de Espera:** Se incrementó el `timeout` de la API de Gemini a 30 segundos, ya que la evaluación generativa a veces demoraba más del límite original de 10 segundos, causando errores de `ReadTimeout` que rompían la generación.
