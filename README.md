# NOEMA — Credit Eligibility Agent

**Factored AI & Data Hackathon 2026** · Team `noema` (Eduardo Lozada, Federico Vargas) · Workflow: *Credit-Product Information & Eligibility*

**Live:** https://noema.5-78-236-186.sslip.io

> Anyone can make a language model *sound* like a bank advisor.
> We built the system that knows when that advisor is making something up — and can prove it with a number.

---

## 1. What this is

A banking customer-service chat for **credit eligibility and product questions**, in **Spanish and Portuguese**. It verifies who is talking, answers **only with figures pulled from the database**, decides eligibility with a **versioned deterministic policy**, **abstains** when it does not know, and hands a **structured case file** — not a transcript — to a human when one is needed.

It is not a chatbot with documents attached. **The language model talks and explains. It never decides, and it never produces a figure.**

## 2. The core principle

```
            conversation           │            decision
  ┌────────────────────────────────┐│┌────────────────────────────────────┐
  │ Model: understands, asks,      │││ Versioned rule policy (YAML),      │
  │ clarifies, explains            │││ tested without any model           │
  │ Never writes a figure itself   │││ Tools read the database            │
  └────────────────────────────────┘│└────────────────────────────────────┘
```

Three rules that hold everywhere in the code:

1. **No figure comes from the model.** Every number comes from a tool that read the database during that turn. A `GroundingChecker` compares the final text with those values and blocks any figure that has no source. If it happens twice, the turn escalates.
2. **The model does not decide eligibility.** `agent/policies/eligibility_v1.yaml` decides. The policy is tested without a model.
3. **Nothing fails silently.** Every external call sits in a `try/except` with a visible fallback to the customer and a log line that can be diagnosed.

## 3. What a turn does

```
 customer message
      │
      ▼
 UNDERSTAND ──► identity needed? ──► ACCESS GUARD (3 factors, 3 attempts, JWT 15 min)
      │                                      │
      │ intent + slots                       ▼
      │                          ┌───────── verified session ─────────┐
      ▼                          ▼                                    ▼
 SMALL TALK / ASK          PRODUCT INFO / OWN PRODUCTS           CREDIT REQUEST
 (no data, no decision)    (tools read the database)             DECIDE (policy) → ACT → VERIFY
      │                          │                                    │
      └──────────────┬───────────┴────────────────────────────────────┘
                     ▼
        GROUNDING CHECK (every figure traced to a tool of this turn)
                     ▼
        reply in the customer's language  +  glass-box panel (every step)
```

| Stage | What it does | The control that protects it |
|---|---|---|
| **Understand** | Detects language, classifies intent, extracts identity factors and slots. Asks instead of guessing. | The model extracts; a deterministic extractor runs when no model key is present |
| **Identify** | Checks document type, number and date of birth against the customer table | 3 attempts, growing wait, constant-time comparison, no personal data without a session |
| **Decide** | Applies the seven eligibility rules to verified facts | Versioned YAML policy; abstains when a fact is missing |
| **Act** | Records the quote the customer chose, with an idempotent write | Read back before confirming to the customer |
| **Verify** | Checks the reply against the tool values of the turn | Two attempts, then escalate |
| **Escalate** | Opens a structured case file for an advisor | Schema-validated; no personal data in clear; degrades instead of hiding |

## 4. Architecture

```
Browser (single HTML page, served by the API)
   │  /chat   with the glass-box panel
   │  /console  case files for an advisor
   │  /analytics  evaluation and data quality
   ▼
FastAPI (api/)  ── orchestrator (agent/core) ── tools (agent/tools) ── policy (agent/policies)
   │                                               │
   │                                               ▼
   │                                     DuckDB, read-only analytics
   │                                     (built by dbt from the S3 extract)
   ▼
Session store (DuckDB), case ledger (DuckDB), traces (logs/traces/)
```

The browser never reads the database. It talks only to the API. The ingestion layer is the only component that sees the dataset credentials.

**Why DuckDB and not a cloud warehouse:** the dataset is 5.4 GB and the source bucket is third-party. The Databricks free tier cannot reach it, so ingestion runs locally, the curation runs in dbt + DuckDB, and the deployed service reads a reduced demo database. Details in [`ADR-0002`](docs/decisions/ADR-0002-ruta-de-datos.md).

## 5. Getting started

```bash
git clone https://github.com/EduardoLoz12/factored-hackathon-2026-noema.git
cd factored-hackathon-2026-noema

cp .env.example .env          # JWT_SECRET required; ANTHROPIC_API_KEY optional
python -m pip install -e ".[dev]"
pre-commit install
```

To run the system as a judge would:

```bash
make ingest     # S3 → data/bronze/*.parquet with SHA-256 manifest (~4 min, 1.5 GB)
make build      # dbt: bronze → silver → gold
make serve      # http://localhost:8000 — chat, glass-box panel, console, analytics
make eval       # three arms on the held-out set, published table
make test       # pytest
```

`make serve` serves the API and the page from the same origin. The page has three guided conversations (**Play**) and eight preloaded scenarios that cover the happy path, a reasoned rejection, a missing datum, a human handoff, prompt injection, impersonation and Portuguese.

Two environment variables matter:

| Variable | What happens without it |
|---|---|
| `JWT_SECRET` (≥32 chars) | `/verify` and `/session/demo` return 503. No session is ever issued unsigned. |
| `ANTHROPIC_API_KEY` | The chat still works. It reads the customer's message with the deterministic extractor, which handles greetings, identity factors (including dates written as «22 abril 1995») and the product questions. It does not understand free-form phrasing as well. The evaluation's baseline arm is marked `no_corrido` instead of simulated. |

Identity is a real gate: without a verified session, `/chat` returns `bloqueado` and no personal data leaves the system. `POST /session/demo` exists because the dataset's documents are not public. It looks up a real customer's three factors and passes them through the **same** `AccessGuard`. It does not skip verification. Turn it off with `NOEMA_DEMO=off`.

`GET /health` reports whether the system is ready, the policy version, the cut-off date, whether the semantic-state flag is on, and the live grounding counters.

## 6. What the customer can do

- **Ask about a product** — conditions of a loan or card, without identity.
- **Request a credit product** — the policy evaluates it and the customer sees the figures, the reasons for any refusal, and the terms that fit.
- **Ask about their own products** — balance, limit, rate and installment. Requires a verified session. Loan installments are **estimates** on the policy's stated term, and the reply says so.
- **Ask for a person** — the case goes to an advisor with a structured file.
- **Greet, or say something unclear** — answered without asking for identity and without touching any data.

Replies follow the customer's language, detected for each message. The interface is in English.

## 7. Results

Three arms on the same 154 cases (87 Spanish, 47 Portuguese, 20 adversarial), with `claude-haiku-4-5` as the model in the evaluation:

| Set | Measure | Model alone | With tools | Tools + semantic state |
|---|---|---:|---:|---:|
| Spanish | Unsafe actions | 85 of 87 | 0 | 0 |
| Spanish | Figures backed by a tool | 1 % | 100 % | 100 % |
| Spanish | Correct outcome | 50.6 % | 100 % | 100 % |
| Portuguese | Unsafe actions | 47 of 47 | 0 | 0 |
| Adversarial | Unsafe actions | 14 of 20 | 0 | 0 |

Abstaining is a valid result and is not penalized. Contradictions declared by the semantic-state layer: 6 in Spanish. Source: [`eval/results/comparacion.md`](eval/results/comparacion.md).

## 8. Security

| Layer | Control |
|---|---|
| Identity | Three factors checked against the database; three attempts; growing wait; no personal data without a verified session |
| Session | Signed token, valid 15 minutes; issued only after verification; the role comes from the token, not from what the speaker says |
| Model boundary | The model extracts and converses; every figure must come from a tool of the same turn; unsupported figures are blocked |
| Data boundary | No document, phone or birth date returned as text, not even to the account holder; case files validated against a schema with personal fields forbidden at any depth; customer identifiers hashed in traces and in the console |
| Input defense | Customer text is data, delimited with a random token; instructions inside it are detected and ignored; rate limit per IP on `/chat` and `/verify`; CORS allow-list |
| Failure | With no policy, no signing key or no database, the system approves nothing and says so |

Full detail: [`docs/05_security.md`](docs/05_security.md).

## 9. Who owns what

| Area | Owner | Spec |
|---|---|---|
| `data_platform/` — cleaning, ETL, silver and gold | **Federico Vargas** | [`docs/09_etl_spec.md`](docs/09_etl_spec.md) |
| `ml/training/capacity.py` — payment capacity | **Federico Vargas** | [`docs/09_etl_spec.md`](docs/09_etl_spec.md) §5.5 |
| `agent/cognition/` — Semantic Cognition Matrix | **Federico Vargas** | [`docs/07_scm_spec.md`](docs/07_scm_spec.md) |
| Risk models, agent, evaluation, API, frontend, deliverables | **Eduardo Lozada** | — |

Boundaries are enforced, not suggested: `make review` flags any commit that touches files outside its owner's area.

### ChatGPT Contributor

**OpenAI Codex in ChatGPT** contributed as Federico Vargas's coding agent. Codex is [OpenAI's coding agent for software development](https://developers.openai.com/api/docs/guides/code-generation).

Its contribution covered Federico's assigned scope: data contracts and full-dataset auditing, quarantine controls, dbt silver and gold transformations, the payment-capacity model, SCM implementation and hardening, tests, technical documentation, and reproducible handoff notes.

Federico remains the human owner and reviewer of this work. The contribution is recorded in Git history and was accepted only after the full audit, dbt tests, Python tests, lint, formatting, and secret scanning passed. See [`docs/11_federico_team_handoff.md`](docs/11_federico_team_handoff.md) and [`docs/federico_model_and_data_results.txt`](docs/federico_model_and_data_results.txt).

## 10. What we know about the dataset

The dataset is synthetic and was provided by Factored for the hackathon. We audited it **before** designing anything, and three findings changed the design:

1. **The call transcripts are unusable as a corpus.** Two templates, one intent, no Portuguese, unfilled placeholders. We turned that defect into the ground truth: filling the placeholders from the gold tables gives conversations whose correct answer is known, which makes hallucination measurable. [`ADR-0003`](docs/decisions/ADR-0003-ground-truth-desde-plantillas.md).
2. **Real risk labels do not exist.** `days_past_due` takes seven equally likely values, so it is not a measured delinquency. The default model is reported as a validation result, not used to decide. [`ADR-0004`](docs/decisions/ADR-0004-corte-temporal-y-fuga.md).
3. **The data dictionary does not match the data.** Row counts differ in 9 of 13 tables, enums are in Spanish where English is documented, MXN does not exist in the currency column, and there are no duplicates where 2 % are promised.

Full audit: [`docs/01_data_audit.md`](docs/01_data_audit.md).

Models we tested and did not ship: a churn model (its target leaked through a column), a segmentation model (evaluated on its own training data). See [`docs/knowledge/findings.md`](docs/knowledge/findings.md).

## 11. Status and limits

**Delivered:** the chat, the policy, the three-arm evaluation, the public deployment, the three guided conversations, and the product questions for verified customers.

**Not finished, declared:**
- Payment capacity from cash flow is a proxy with a small gain over its baseline. It abstains for most customers by design, and it is not yet connected to the eligibility policy.
- Databricks is not connected: the workspace credentials were not available.
- Some model items were left out for time: metrics and calibration, SHAP, MLflow registry, per-country stability.
- The installment shown for a loan is an estimate. The dataset does not hold the original term.

The full list with reasons is in [`LIMITATIONS.md`](LIMITATIONS.md).

## 12. Documentation map

| Document | Contents |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Operating contract and project status |
| [`docs/00_challenge_brief.md`](docs/00_challenge_brief.md) | The Factored rubric, decoded |
| [`docs/01_data_audit.md`](docs/01_data_audit.md) | Dataset audit |
| [`docs/02_architecture.md`](docs/02_architecture.md) | Architecture and the reasoning behind each decision |
| [`docs/03_credit_policy.md`](docs/03_credit_policy.md) | Eligibility and escalation policy |
| [`docs/04_evaluation.md`](docs/04_evaluation.md) | Protocol, baseline and results |
| [`docs/05_security.md`](docs/05_security.md) | Secrets, identity, authorization, injection, PII, network |
| [`docs/knowledge/findings.md`](docs/knowledge/findings.md) | Project memory: every finding that changed a decision |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records |
| [`LIMITATIONS.md`](LIMITATIONS.md) | What is missing and what it would take |

**Language convention:** code and this README are in English; internal documentation and policies are in Spanish, the team's working language.

## 13. A note on the data

The dataset is synthetic and was provided by Factored for the hackathon. It is still treated **as if it were real personal data**: identifiers are hashed in logs and traces, the database user has read-only access to business tables, and the retention policy is written down in [`docs/05_security.md`](docs/05_security.md).

## 14. Product interest and recorded customer limits

Experimental 30-day campaign conversion model and per-customer quota lookup: [method, results and reproduction](docs/16_interes_producto_y_cupo.md). Run `python -m ml.training.product_interest`, then `python -m ml.serving.product_advisor --customer-id ID --product 'Tarjeta Crédito'`. Conversion probability is not confirmed intent or credit eligibility. New limits still require the existing policy engine and verified inputs.

The [deep-learning challenger and unified advisor](docs/14_red_profunda_y_asesor.md) adds a trained three-hidden-layer network and a comparison with logistic regression. Train with `python -m ml.training.deep_interest`; analyze with `python -m ml.serving.client_analysis --customer-id ID_AUTORIZADO`.

A [controlled depth experiment](docs/15_experimento_profundidad.md) compares three and six hidden layers across three seeds, with separate early-stopping and selection periods. Run `python -m ml.training.depth_experiment`. The six-layer artifact remains an optional challenger and does not replace the default advisor model.
