# 00 · El reto, decodificado

Síntesis del kickoff (25-sep-2026) y de los slides, traducida a criterios accionables.

## Lo esencial

- **Un solo workflow**, profundo, de cuatro opciones. Elegimos *Credit-Product Information & Eligibility* (ADR-0001).
- **Prototipo end-to-end funcionando**, desplegado y accesible.
- **Español y portugués.**
- Ciclo obligatorio: **Understand → Decide → Act → Verify → Escalate**.
- Entregables → `hackathon.admin@factored.ai`: repo `factored-hackathon-2026-noema`, URL desplegada, 4-6 slides, video ≤3 min.
- **Cierre: 5-oct-2026, 23:59 hora Colombia.** Premiación 16-oct: los cinco finalistas defienden en vivo.

## Qué se evalúa, en el orden en que pesa

| Exigencia | Fuente | Qué significa al calificar |
|---|---|---|
| «Don't build a chatbot, build a customer-service system» | slide 10 | Tools, estado, acciones ejecutadas y entrega a humano. Un RAG conversacional pierde. |
| «First and foremost our solution should work» | slide 20 y kickoff | **Criterio número uno:** que el jurado pueda usarlo. Deploy vivo y setup de un comando pesan más que la sofisticación. |
| Understand → Decide → Act → Verify → Escalate | slide 11 | Cinco etapas **visibles** en el código y en las trazas. |
| «AI should not be autonomous just because it can be» | slide 11 | Abstenerse y escalar bien **suma**. Un agente que contesta todo pierde. |
| «Verify that actions actually happened» | slide 11 | Releer el estado tras escribir. Barato y casi nadie lo hará. |
| «Structured handoff… not raw transcripts» | slide 11 | Expediente con hechos verificados, acciones y preguntas abiertas. |
| «Baseline → Proposed System → Held-out Evaluation» | slide 12 | Sin tabla comparativa no hay puntos de rigor. |
| «Valid labels», «Leakage prevention», «Appropriate split» | slide 12 | Poder decir de dónde salió cada etiqueta. Aquí se cae la mayoría. |
| «Learned component: benchmark against a baseline model» | slide 12 | Exigen un **modelo entrenado**, no solo un LLM. |
| Safe Automated Resolution · **Unsafe Outcomes** · Cost Efficiency | slide 12 | La tasa de acciones inseguras es la métrica estrella. Meta: cero, demostrada. |
| «Enforce action permissions besides model prompts» | slide 13 | Permisos en código, no en el prompt. |
| «Stress-test held-out cases against injection» | slide 13 | Suite adversarial obligatoria. |
| Observabilidad · Fiabilidad · Seguridad · Reproducibilidad | slide 15 | Trazas, reintentos acotados, autenticación y retención, versionado. |
| «Be honest about what's missing» | slide 15 | `LIMITATIONS.md` es entregable evaluado, no disculpa. |
| «El porqué importa más que el cómo» | Diego Ralón, kickoff | ADRs con razón de negocio. |
| Cuatro pilares: AI Eng · ML · Data Eng · Data Analytics | slide 14 y 20 | Profundizar donde somos fuertes sin dejar ninguno flojo. |

## La lectura estratégica

De las dieciséis exigencias, **tres** tienen que ver con qué tan inteligente es el agente. Las otras **trece** son disciplina: evidencia, control, medición y honestidad. Ahí se decide el primer lugar.

## Nuestra respuesta, en una frase

Un asistente de crédito que verifica quién le habla, responde solo con cifras traídas de la base, decide con un modelo entrenado más una política escrita, comprueba lo que ejecutó, se abstiene cuando no sabe, y entrega hechos verificados —no la transcripción— cuando necesita un humano.
