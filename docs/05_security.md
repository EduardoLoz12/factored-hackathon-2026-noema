# 05 · Seguridad

El dataset es sintético, pero **el sistema se construye como si los datos fueran reales**. Esta página es el contrato de seguridad del proyecto; cada punto tiene una prueba asociada o una razón escrita.

---

## 1. Secretos y credenciales

- Las credenciales de AWS vienen en un **PDF repartido a ~800 participantes**. Se tratan como **comprometidas por diseño**: son read-only y se usan **exclusivamente** en la ingesta local.
- **Nunca** viajan al contenedor de la API ni al frontend. `data_platform/ingestion/` es la única ruta del repo que las lee.
- `.env` y `materiales/` están en `.gitignore`. `.env.example` no contiene valores.
- **`gitleaks`** corre como hook de pre-commit y como job de CI. Nada llega a `main` sin pasarlo.
- En Databricks, los tokens viven en un **secret scope**, nunca en el notebook.

## 2. Verificación de identidad — la puerta

Ninguna información personal sale antes de esta etapa.

| Control | Implementación | Por qué |
|---|---|---|
| Factores | `document_type` + `document_number` + `date_of_birth` contra `customers` | `document_number` es único en las 150 000 filas |
| El teléfono **no** es factor | — | 48.4 % de los clientes tiene prefijo de otro país (F-004) |
| Intentos | Máximo 3 por sesión, luego bloqueo con backoff exponencial | Fuerza bruta |
| Mensajes de error | **Idénticos** en todos los casos de fallo | Impide enumerar qué documentos existen |
| Comparación | `hmac.compare_digest` | No filtrar por latencia |
| Sesión | JWT firmado, 15 minutos, con el `customer_id` **dentro** | El cliente nunca envía `customer_id`; cierra el agujero del esqueleto inicial (F-007) |
| Estado | Tabla `sessions` con TTL, no memoria del proceso | Sobrevive a múltiples workers |

## 3. Autorización de acciones

- **Allowlist por rol en código, no en el prompt.** Cada tool declara `requires_auth`, `writes` y `allowed_roles`; el ejecutor valida **antes** de invocar y registra todo intento rechazado.
- Las herramientas de escritura son **idempotentes** mediante `idempotency_key` derivada de (sesión, intención, payload). Un reintento no abre dos casos.
- **Prueba obligatoria:** invocar un tool de escritura con sesión no verificada **debe fallar**. Está en `tests/`.

## 4. Defensa contra inyección de prompt

- El texto del cliente **nunca** se concatena en la instrucción de sistema. Va en un bloque de datos delimitado, marcado como contenido no confiable.
- **El modelo nunca emite SQL.** Solo elige tools con parámetros tipados; las consultas son parametrizadas y escritas por nosotros.
- **`GroundingChecker`**: extrae números y datos personales de la respuesta final y verifica que cada uno exista entre los valores devueltos por los tools de ese turno. Un valor huérfano bloquea la respuesta; al segundo intento fallido, se escala.
- **Suite adversarial versionada** (~20 casos): instrucciones ocultas en el mensaje, suplantación de identidad, petición de datos de otro cliente, presión social, extracción del prompt de sistema.

## 5. Datos personales

- En logs y trazas, `document_number`, `email` y teléfono se guardan **hasheados** (SHA-256 con sal de entorno, `PII_HASH_SALT`); los nombres se truncan.
- El texto completo del cliente **no** se registra en nivel `INFO`.
- **Retención:** trazas 30 días · expedientes de escalamiento 90 días.
- Usuario de base de datos de la API: **solo lectura** sobre las tablas gold; **solo inserción** sobre `cases` y `action_ledger`. Sin `DELETE` ni `UPDATE`.

## 6. Superficie de red

- HTTPS obligatorio. CORS restringido al dominio del frontend. Rate limit por IP y por sesión. Tamaño máximo de payload.
- Sin endpoints de administración expuestos. `/metrics` protegido con token.
- Dependencias fijadas con lockfile; `pip-audit` en CI.

## 7. Comportamiento ante fallo

**Falla cerrado, nunca abierto.** Si el modelo de riesgo no carga, el sistema **no aprueba nada**: escala y lo dice. Si la relectura posterior a una escritura no coincide, el agente **no afirma** que la acción ocurrió.

Toda llamada externa —LLM, base de datos, modelo, S3— va dentro de `try/except`, con fallback visible al usuario y log con contexto suficiente para diagnosticar. **Nada se cae en silencio.**
