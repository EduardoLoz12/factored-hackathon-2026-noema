# NOEMA — Credit Eligibility Agent

**Factored AI & Data Hackathon 2026** · Team `noema` · Workflow: *Credit-Product Information & Eligibility*

> Anyone can make a language model *sound* like a bank advisor.
> We built the system that knows when that advisor is making something up — and can prove it with a number.

---

## 1. What this is

A banking customer-service system that handles **credit eligibility** conversations in **Spanish and Portuguese**. It verifies who is talking, answers **only with figures pulled from the database**, evaluates eligibility with a **trained model plus a versioned deterministic policy**, **verifies what it executed**, **abstains** when it doesn't know, and hands a **structured case file** — not a chat transcript — to a human when one is needed.

It is not a chatbot with documents attached. **The language model talks and explains. It never decides, and it never produces a number.**

## 2. The core principle

```
            conversation           │            decision
  ┌────────────────────────────────┐│┌────────────────────────────────────┐
  │ LLM: understands, asks,        │││ YAML rule engine + trained models  │
  │ clarifies, explains            │││ Deterministic, testable without an │
  │ Never emits a figure of its own│││ LLM in the loop                    │
  └────────────────────────────────┘│└────────────────────────────────────┘
```

Three rules that are not negotiable anywhere in the codebase:

1. **No figure comes from the LLM.** Every number comes from a tool that queried the database. A `GroundingChecker` validates the final answer against the values the tools returned and blocks any orphan number.
2. **The LLM does not decide eligibility.** `agent/policies/eligibility_v1.yaml` decides. The policy is unit-tested without an LLM.
3. **Every write is read back** before anything is confirmed to the customer. If it doesn't match, the agent does not claim it happened — it escalates.

## 3. The six stages

```
UNDERSTAND → ACCESS GUARD → DECIDE → ACT → VERIFY → ESCALATE
 language      document +     policy   typed   real     structured
 intent        birth date     engine   tools   read     case file
 SCM state     3 attempts     + models idempotent back
```

| Stage | What it does | The control that protects it |
|---|---|---|
| **Understand** | Detects language, classifies intent, extracts slots. If something essential is missing, it asks instead of guessing. | The **SCM** records what is known, what is unknown, and where each fact came from |
| **Access Guard** | Validates `document_type` + `document_number` + `date_of_birth` against the `customers` table | 3 attempts, identical error messages, constant-time comparison |
| **Decide** | The rule engine combines risk, payment capacity and product conditions | The LLM does not participate; the policy is a versioned file |
| **Act** | Executes through tools with typed contracts | Role allowlist enforced in code; writes are idempotent |
| **Verify** | Reads back what it wrote and compares field by field | On mismatch: claim nothing, escalate |
| **Escalate** | Hands over verified facts, executed actions and open questions | Schema-validated object, not free text |

## 4. Architecture

```
UI (Next.js, Vercel)  ──HTTPS + JWT──▶  API (FastAPI)  ──▶  Postgres  (gold tables, cases, ledger)
 /chat   + Glass Box panel                    │          ──▶  Models    (MLflow registry)
 /console  (case files)                       │
 /analytics (metrics + data quality)          ▼
                                   Databricks (Delta + MLflow)
                                              ▲
                          Parquet ── DuckDB + dbt ── S3 ingestion
```

The frontend **never** touches Databricks or the database. It only talks to the API.
The ingestion layer is the **only** component that ever sees the dataset credentials.

**Why the data path looks like this:** Databricks Free Edition is serverless-only and restricts outbound internet to a trusted domain list, so it cannot read Factored's third-party S3 bucket. Ingestion therefore runs locally, canonical curation happens in DuckDB + dbt (5.35 GB runs in minutes on a laptop), and Databricks receives converted Parquet to act as the Delta lakehouse and model registry. Full reasoning in [`docs/decisions/ADR-0002`](docs/decisions/ADR-0002-ruta-de-datos.md).

## 5. Getting started

```bash
git clone https://github.com/EduardoLoz12/factored-hackathon-2026-noema.git
cd factored-hackathon-2026-noema

cp .env.example .env          # fill in credentials — see page 1 of the Data Dictionary
python -m pip install -e ".[dev]"
pre-commit install
```

Then, depending on what you need:

```bash
make ingest     # S3 → data/bronze/*.parquet + manifest with SHA-256 checksums (~4 min, 1.5 GB)
make summary    # small, committable summary of the manifest
make build      # dbt: bronze → silver → gold
make train      # baseline + default-risk model + payment capacity → MLflow
make eval       # harness: baseline vs tools vs tools+SCM
make serve      # local API
make test       # pytest
make review     # who changed what, and whether it stayed inside its boundary
```

**You do not need to run `make ingest` to work on the cognition layer.** Fixtures in `tests/fixtures/` cover that.

## 6. Who owns what

| Area | Owner | Spec |
|---|---|---|
| `data_platform/` — cleaning, ETL, silver and gold | **Federico Vargas** | [`docs/09_etl_spec.md`](docs/09_etl_spec.md) |
| `ml/training/capacity.py` — payment capacity model | **Federico Vargas** | [`docs/09_etl_spec.md`](docs/09_etl_spec.md) §5.5 |
| `agent/cognition/` — Semantic Cognition Matrix | **Federico Vargas** | [`docs/07_scm_spec.md`](docs/07_scm_spec.md) |
| Risk models, agent, evaluation, API, frontend, deliverables | **Eduardo Lozada** | — |

**If you are Federico (or Federico's coding agent):** you have two fronts, each with its own agent and its own spec. Data and ETL → agent `data-etl`, spec [`docs/09_etl_spec.md`](docs/09_etl_spec.md). Cognition → agent `scm-cognition`, spec [`docs/07_scm_spec.md`](docs/07_scm_spec.md). Both contain the task, the contract, the acceptance tests and the dates. Start there; you do not need anything else from the rest of the repo.

**Critical dependency:** the risk model (Eduardo, day 4) trains on `credit_features_asof` (Federico, day 3). That is the single point where a delay by one blocks the other. `tests/data/test_feature_contract.py` mechanically verifies that this table carries no leaking columns.

Boundaries are enforced, not suggested: `make review` flags any commit that touches files outside its owner's area.

### ChatGPT Contributor

**OpenAI Codex in ChatGPT** contributed as Federico Vargas's coding agent. Codex is
[OpenAI's coding agent for software development](https://developers.openai.com/api/docs/guides/code-generation).

Its contribution covered Federico's assigned scope: data contracts and full-dataset auditing,
quarantine controls, dbt silver and gold transformations, the payment-capacity model, SCM
implementation and hardening, tests, technical documentation, and reproducible handoff notes.

Federico remains the human owner and reviewer of this work. The contribution is recorded in
Git history and was accepted only after the full audit, dbt tests, Python tests, lint,
formatting, and secret scanning passed. See
[`docs/11_federico_team_handoff.md`](docs/11_federico_team_handoff.md) for the implementation
summary and [`docs/federico_model_and_data_results.txt`](docs/federico_model_and_data_results.txt)
for measured results.

## 7. What we know about the dataset

We audited the S3 bucket **before** designing anything. Three findings changed the design:

1. **The call transcripts are unusable as a corpus.** Two unique templates across a 794-row sample spanning three years, one intent, zero Portuguese — and unfilled placeholders (`{monto}`, `{moneda}`, `{limite}`). **We turned that defect into our ground truth**: filling those placeholders from the gold tables produces conversations whose correct answer we know in advance, which is what makes hallucination measurable as a rate rather than an opinion. See [`ADR-0003`](docs/decisions/ADR-0003-ground-truth-desde-plantillas.md).
2. **Real risk labels exist.** `products.days_past_due` has 125,350 non-null values, ~15 % delinquent at a 30-day cutoff — but it is a *snapshot with no measurement date*, so the temporal cutoff is a declared assumption, not an observed fact. See [`ADR-0004`](docs/decisions/ADR-0004-corte-temporal-y-fuga.md).
3. **The data dictionary does not match the data.** Row counts differ in 9 of 13 tables (23,495,188 actual vs ~19 M documented), enums are in Spanish where English is documented, MXN does not exist despite 74,907 Mexican customers, and there are zero duplicates where 2 % are promised.

Full audit with reproducible numbers: [`docs/01_data_audit.md`](docs/01_data_audit.md).

## 8. Documentation map

| Document | Contents |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Operating contract — read this before writing code |
| [`docs/00_challenge_brief.md`](docs/00_challenge_brief.md) | The Factored rubric, decoded |
| [`docs/01_data_audit.md`](docs/01_data_audit.md) | Dataset audit: where the dictionary and the data disagree |
| [`docs/02_architecture.md`](docs/02_architecture.md) | Architecture and the reasoning behind each decision |
| [`docs/03_credit_policy.md`](docs/03_credit_policy.md) | Eligibility and escalation policy |
| [`docs/04_evaluation.md`](docs/04_evaluation.md) | Protocol, baseline and results |
| [`docs/05_security.md`](docs/05_security.md) | Secrets, identity, authorization, injection, PII, network |
| [`docs/07_scm_spec.md`](docs/07_scm_spec.md) | **Federico's task**: the Semantic Cognition Matrix |
| [`docs/09_etl_spec.md`](docs/09_etl_spec.md) | **Federico's task**: cleaning, ETL and payment capacity |
| [`docs/knowledge/findings.md`](docs/knowledge/findings.md) | Project memory — every finding that changed a decision |
| [`docs/knowledge/contributions.md`](docs/knowledge/contributions.md) | Contribution ledger: who changed what, and whether it advanced the project |
| [`docs/decisions/`](docs/decisions/) | Architecture Decision Records |
| [`LIMITATIONS.md`](LIMITATIONS.md) | What is missing and what it would take to make it real |

**Language convention:** code and this README are in English; internal documentation, policies and business comments are in Spanish, because that is the working language of the team.

## 9. A note on the data

The dataset is synthetic and was provided by Factored for the hackathon. It is nonetheless treated **as if it were real personal data**: identifiers are hashed in logs and traces, the API database user has read-only access to business tables, and the retention policy is written down in [`docs/05_security.md`](docs/05_security.md).

## 10. Deliverables

Repository · live URL · 5 slides · 3-minute video → `hackathon.admin@factored.ai`
**Deadline: 5 October 2026, 23:59 Colombia time.**

## Product interest and recorded customer limits

Experimental 30-day campaign conversion model and per-customer quota lookup:
[method, results and reproduction](docs/13_interes_producto_y_cupo.md).
Run `python -m ml.training.product_interest`, then
`python -m ml.serving.product_advisor --customer-id ID --product 'Tarjeta Crédito'`.
Conversion probability is not confirmed intent or credit eligibility. New limits
still require the existing policy engine and verified inputs.

The [deep-learning challenger and unified advisor](docs/14_red_profunda_y_asesor.md)
add a trained three-hidden-layer MLP, comparison with logistic regression, and an
integration with Eduardo's policy engine for verified inputs. Train with
`python -m ml.training.deep_interest`; analyze with
`python -m ml.serving.client_analysis --customer-id ID_AUTORIZADO`.
