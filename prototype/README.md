# Noema local — prototipo para revisión de Federico

**No publicar todavía.** Frontend, backend y configuración del LLM permanecen
locales hasta que Federico los revise. No hay conexión bancaria ni servicio de pago.

## Arranque

Desde la raíz del repositorio, con el entorno del proyecto instalado:

```bash
uv pip install --python .venv/bin/python -r prototype/requirements.txt
ollama pull qwen2.5:1.5b
ollama create noema-bank-local -f prototype/Modelfile
.venv/bin/python -c "from faster_whisper.utils import download_model; download_model('tiny', output_dir='data/models/whisper-tiny')"
.venv/bin/python -m uvicorn prototype.app:app --host 127.0.0.1 --port 8765
```

Ollama debe estar en ejecución en `127.0.0.1:11434`. Abrir
<http://127.0.0.1:8765>. Las descargas iniciales necesitan Internet; la inferencia
usa archivos locales. El entorno preparado en esta máquina ya tiene los pesos.
Si faltan los artefactos comerciales, la conversación funciona pero se abstiene
al pedir análisis. Para recrearlos, consultar los documentos 13 y 15 de `docs/`.
La dependencia `av<17` evita una incompatibilidad comprobada con `av==19` y
`faster-whisper==1.2.1`. El entorno base necesita las dependencias ML del proyecto.

## Recorrido de revisión

1. «Consultar mi saldo»: muestra 2450.75 USD **ficticios** al iniciar sesión.
2. «Transferir 100 USD»: prepara una transferencia solo al ahorro demo; no interpreta
   beneficiarios libres. Revisar destino y monto en el botón antes de confirmar.
3. Confirmar y volver a consultar saldo: 2350.75 USD. Repetir la misma confirmación
   no vuelve a descontar. Un nuevo borrador sustituye los borradores anteriores.
4. «Bloquear tarjeta»: requiere confirmación y verifica el estado guardado.
5. «Analizar comportamiento»: compara logística y red de seis capas en un escenario
   fijo de campaña y resume movimientos simulados. No perfila un cliente real.
6. «Quiero conocer mi cupo»: se abstiene; la sesión demo no verifica identidad.
7. «Necesito un humano»: guarda un caso en «Mis solicitudes». No avisa a una persona
   real; falta integrar la cola con un sistema de atención.
8. «Hablar con Noema»: autorizar micrófono si se desea; grabar hasta 30 segundos,
   revisar/corregir la transcripción y enviarla. Nunca se ejecuta una orden de voz
   directamente. La lectura en voz alta usa solo voces locales españolas disponibles.

Cada recarga crea una sesión demo independiente; no es una cuenta persistente.
La sesión dura dos horas. Los datos simulados quedan en `data/prototype/demo.sqlite`;
no se almacenan audios ni textos originales del chat. No introducir información
personal real. El servidor debe mantenerse en loopback, nunca exponerse a la red.

## Alcance y validación

Consultar `docs/17_noema_local_arquitectura.md` para contratos, decisiones,
limitaciones y plan de especialización. Pruebas:

```bash
.venv/bin/pytest
.venv/bin/ruff check prototype ml/training/support_escalation.py tests/test_local_prototype.py
```

El LLM se especializó mediante instrucciones y salida estructurada: **no se
ajustaron sus pesos**. No es un asesor bancario autónomo ni un sistema de producción.
