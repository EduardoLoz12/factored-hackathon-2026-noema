# Complete Plain-English Code Report

2 October 2026 · Branch `trabajo/federico-data-cognition` after merging latest
`origin/main`.

This report explains what has been built in the repository, module by module,
what each program does, what logs exist, and what tests have been run. It is
written in plain English on purpose: the goal is that Federico, Eduardo, a judge,
or a future coding agent can understand the system without first reading every
source file.

## Executive Summary

Noema is a banking customer-service agent for the Factored AI & Data Hackathon
2026. The selected workflow is **Credit-Product Information & Eligibility**.

The system is built around one main idea:

> The language model may converse and explain, but it must not invent numbers,
> decide credit eligibility, or confirm an action that was not verified.

So the repository separates the work into:

1. **Data platform**: ingest, audit, clean, validate, and build local gold tables.
2. **Machine learning**: measure what can and cannot be learned from the dataset.
3. **Policy engine**: make eligibility decisions with deterministic rules, not an LLM.
4. **SCM, the Semantic Cognition Matrix**: track what the system knows, what is
   missing, and what contradicts.
5. **Agent tools and orchestration**: authenticate, read customer facts, decide,
   act, verify, and escalate.
6. **Guardrails**: block unsupported numbers and contain prompt-injection attempts.
7. **Prototype/API/UI**: local demo layers for chat, voice, and product interaction.
8. **Documentation and logs**: record decisions, findings, worklogs, metrics, and
   reproducible commands.

The most recent full Python test run on the merged branch passed:

```text
945 passed, 1 warning
```

That run used:

```bash
.venv/bin/python -m pytest
```

The first attempt after merging failed because the local virtual environment was
missing `PyJWT`, even though `pyjwt>=2.9` is declared in `pyproject.toml`. It was
installed with:

```bash
uv pip install --python .venv/bin/python 'PyJWT>=2.9'
```

## Current Git State

Latest merge:

```text
3bb9e8c Merge remote-tracking branch 'origin/main' into trabajo/federico-data-cognition
```

Branch comparison after the merge:

```text
origin/main...HEAD = 0 commits missing from main / 6 commits local to Federico branch
```

That means the local Federico branch contains latest `origin/main`. It has not
been pushed yet.

There is still local uncommitted work for the demo/API/UI/prototype layer,
including:

- `api/main.py`
- `prototype/`
- `ui/`
- `docs/15_ai_customer_solution.md`
- `docs/16_revision_modelos_y_escalamiento.md`
- `docs/17_noema_local_arquitectura.md`
- `docs/18_noema_ai_final_architecture.md`
- `docs/19_estado_integracion_federico.md`
- `tests/test_local_prototype.py`
- `tmp/`

## Project Contract

The operating contract lives in `CLAUDE.md`.

The key rules are:

1. **No number comes from the LLM.** Every number must come from a tool, a table,
   a policy threshold, or a verified model output.
2. **The LLM does not decide eligibility.** Eligibility comes from
   `agent/policies/eligibility_v1.yaml` evaluated by deterministic code.
3. **Every write is read back.** The system only confirms an action after reading
   the stored state and verifying it matches.
4. **Failure is explicit.** External calls, model loading, database access, and
   LLM calls must fail closed or escalate.
5. **Abstention is valid.** If the system lacks evidence, it asks, abstains, or
   escalates instead of guessing.
6. **Secrets stay out of Git.** `.env`, datasets, model binaries, and challenge
   materials are not meant to be committed.

Ownership:

| Area | Owner | Main files |
|---|---|---|
| Data platform, ETL, silver/gold | Federico | `data_platform/`, `docs/09_etl_spec.md` |
| Payment capacity model | Federico | `ml/training/capacity.py` |
| SCM | Federico | `agent/cognition/scm.py` |
| Policy, agent, API, UI, evaluation | Eduardo | `agent/core/`, `agent/tools/`, `agent/policies/`, `api/`, `ui/` |

## Root Configuration and Commands

### `pyproject.toml`

Defines the Python package, dependencies, linting rules, and test configuration.
Important dependencies include:

- `duckdb`, `pandas`, `pyarrow` for local data work.
- `scikit-learn`, `joblib`, `mlflow`, `lightgbm`, `shap` for ML.
- `fastapi`, `uvicorn`, `pyjwt`, `httpx` for serving and auth.
- `pytest`, `ruff`, `pre-commit`, `pip-audit` for quality.

The project expects Python 3.11 or newer. In the current local setup the venv uses
Python 3.13.

### `Makefile`

Important commands:

| Command | Purpose |
|---|---|
| `make setup` | Install Python dependencies and pre-commit hooks |
| `make ingest` | Download/convert S3 data into bronze Parquet |
| `make audit` | Audit source tables and create quality reports |
| `make build` | Run dbt bronze → silver → gold and export local data |
| `make train` | Train model family |
| `make train-capacity` | Train payment-capacity model |
| `make train-interest` | Train product-interest model |
| `make train-deep-interest` | Train deep-interest MLP |
| `make train-depth-experiment` | Run depth comparison experiment |
| `make serve` | Run FastAPI API locally |
| `make ui` | Run Next.js frontend locally |
| `make test` | Run pytest |
| `make lint` | Run Ruff lint and format check |
| `make check` | Run lint, tests, and gitleaks |

## Data Platform

The data platform turns the supplied synthetic banking dataset into local,
auditable tables that the agent and models can use.

### `data_platform/ingestion/ingest_s3.py`

Downloads the challenge S3 files and converts source CSV data to local Parquet.
It writes bronze files under `data/bronze/` and creates a manifest with row counts
and checksums.

Current evidence:

- The project reports 7,671 downloaded files.
- The full dataset contains **23,495,188 rows**, not the roughly 19 million
  described in the challenge dictionary.
- Raw data is local and ignored by Git.

### `data_platform/ingestion/summarize_manifest.py`

Creates a smaller, committable summary of the full manifest. The summary exists at:

```text
docs/data/manifest_summary.json
```

### `data_platform/contracts/schemas.py`

Defines the expected source columns, key fields, type expectations, allowed
values, and ranges for all source tables.

This is the schema contract the audit uses.

### `data_platform/contracts/audit.py`

Audits the complete bronze dataset. It checks:

- Missing required values.
- Type conversion failures.
- Non-finite numeric values.
- Range violations.
- Enum violations.
- Duplicate primary keys.
- Broken foreign keys.
- Product/customer mismatches in transactions.
- Optional branch references that should be repaired instead of dropping rows.

The audit partitions rows into:

- validated rows;
- quarantined rejected rows;
- repaired optional-reference rows.

Important findings from the audit:

- The dataset has **23,495,188 actual rows**.
- Essential customer/product relationships are mostly usable.
- Optional branch references are mostly invalid, so they are nulled and reported
  instead of destroying the customer table.
- Many nulls are structural, not missing data.
- Source `amount_usd` contains deliberate noise, so the pipeline recalculates USD
  amounts from exchange rates.

Current audit log:

```text
logs/build/dq_report.json
```

### `data_platform/contracts/quarantine.py`

Implements the row partitioning used by the audit. It ensures rejected rows carry
their rejection reason and original lineage.

### `data_platform/dbt/`

The dbt project builds silver and gold tables.

Silver models standardize and type source tables. Important behaviors:

- explicit date/number/boolean casts;
- product names normalized to Spanish vocabulary;
- transaction types translated to Spanish;
- redundant call-center `contact_reason` removed;
- transaction USD values recalculated from exchange rates;
- FX quarantine for rows without exact-date exchange rate.

Gold models include:

| Table | Purpose |
|---|---|
| `customer_360` | Customer profile, balances, tenure, delinquency summary |
| `credit_features_asof` | Cutoff-safe features for modeling |
| `product_policy` | Observed product catalog, marked not policy-ready where conditions are missing |
| `dq_report` | Data-quality metrics usable by analytics |

Known caveats documented elsewhere:

- Some `customer_360` income fields were found to be local currency unless
  converted.
- A valuation date issue was documented: future FX dates must not be used for
  cutoff calculations.

### `data_platform/serving/export_local.py`

Exports dbt-built tables to local files and local DuckDB serving state.

Local artifacts observed:

- `data/noema.duckdb`
- `data/gold/customer_360.parquet`
- `data/gold/credit_features_asof.parquet`
- `data/gold/product_policy.parquet`
- `data/gold/dq_report.parquet`

### `data_platform/serving/export_to_postgres.py`

Prepared for exporting gold tables to Postgres. It is designed to verify reads
after loading, but it has not been marked complete because a real destination
environment is needed.

### `data_platform/databricks/upload_to_volume.py`

Prepared for uploading Parquet outputs to Databricks volumes. This is blocked or
unverified without real Databricks credentials.

## Machine Learning

The ML layer is unusually honest: much of the work proves what the dataset cannot
support.

### `ml/features/build_features.py`

Builds an as-of feature store for risk analysis. It reads Federico’s silver/gold
data and writes:

```text
data/gold/features_asof.parquet
data/gold/features_asof.manifest.json
```

The feature store:

- uses a declared cutoff of `2025-12-31`;
- filters by both event date and process/availability date;
- excludes leakage columns such as `current_balance`, `last_transaction_date`,
  `product_status`, and `days_past_due`;
- converts income to USD using country-derived currency;
- labels rows for strict/cohort sensitivity analysis.

Log evidence:

```text
logs/build/interest_feature_store.log
```

Key logged output:

```text
rows: 141,483
with label: 76,906
strict cohort: 7,078
complete cohort: 76,906
```

### `ml/training/baseline_logreg.py`

Baseline risk model work. The important conclusion is not “we have a great risk
model”; it is that the supplied risk target does not behave like a real learnable
target.

Related model summaries:

```text
models/baseline_logreg_estricta.json
models/baseline_logreg_completa.json
```

### `ml/training/capacity.py`

Federico’s payment-capacity estimator. It uses transaction history to estimate a
conservative payment-capacity proxy.

Inputs:

- average deposits;
- average outflows;
- minimum monthly surplus;
- active months;
- ambiguity from transfers/adjustments.

It avoids using declared income directly because that field is incomplete and
currency-sensitive.

Output:

```text
data/models/capacity.json
logs/build/capacity_metrics.json
```

Important metrics from `logs/build/capacity_metrics.json`:

| Metric | Value |
|---|---:|
| Training rows | 150,000 |
| Validation rows | 14,820 |
| Eligible validation rows | 825 |
| Validation MAE | 92,369.45 |
| Baseline MAE | 92,731.04 |

Interpretation:

- The model is conservative and abstains often.
- Only 5.57% of validation rows met the conditions for an estimate.
- The improvement over baseline is small because the synthetic transaction
  amounts are close to uniform and weakly connected to future flow.

### `ml/training/product_interest.py`

Trains an experimental product-interest model. It predicts 30-day campaign
conversion, not credit eligibility and not explicit customer desire.

It:

- builds examples from campaign sends and campaign metadata;
- removes invalid process-order rows;
- uses only pre-send history;
- splits by time;
- uses logistic regression with one-hot encoded categorical variables;
- compares against a prior baseline;
- reports AP, ROC-AUC, Brier, log-loss, calibration, and top-10% lift.

Output:

```text
data/models/product_interest.joblib
ml/model_cards/product_interest.json
```

Document:

```text
docs/13_interes_producto_y_cupo.md
```

### `ml/serving/product_advisor.py`

Serves product-interest estimates and observed credit limits. It intentionally
keeps three ideas separate:

1. Product-interest probability.
2. Existing observed product credit limits.
3. Any new-product quota scenario from the deterministic policy.

It does not approve credit and does not invent available credit.

### `ml/training/deep_interest.py`

Trains a small neural network, an MLP with three hidden layers, against the same
campaign-conversion target as the logistic model.

The key point: this is a challenger model, not a replacement for policy and not
a proof of customer intent.

Output:

```text
data/models/deep_interest.joblib
ml/model_cards/deep_interest.json
logs/build/deep_interest_training.log
```

Logged test comparison:

| Model | ROC-AUC | AP | Lift top 10% |
|---|---:|---:|---:|
| Deep MLP | 0.6739 | 0.00814 | 1.8573 |
| Logistic | 0.6767 | 0.00813 | 1.7719 |
| Prior | 0.5000 | 0.00489 | 1.0000 |

The report selects logistic as the recommended model by validation logic.

### `ml/training/depth_experiment.py`

Compares three-hidden-layer and six-hidden-layer neural networks across multiple
seeds. It controls model selection separately from test evaluation.

Output:

```text
data/models/deeper_interest.joblib
ml/model_cards/depth_experiment.json
logs/build/depth_experiment.log
```

Logged architecture/seed entries include:

- `three_hidden`, seeds 42, 43, 44;
- `six_hidden`, seeds 42, 43, 44;
- best epochs and selection log-loss for each.

Conclusion:

- The six-layer model is kept as an optional challenger.
- It is not presented as a proven superior model.

### `ml/serving/client_analysis.py`

Combines:

- deep-interest model outputs;
- recommended model outputs;
- observed quotas from `product_advisor`;
- deterministic policy scenarios from `agent.policies.engine`.

It only runs policy scenarios when the caller supplies verified inputs through
`VerifiedPolicyInput`. This is crucial: neither the neural network nor the user’s
free text is allowed to construct verified financial facts.

### `ml/training/support_escalation.py`

Tests whether support escalation can be predicted from channel, interaction type,
and reason category.

Output:

```text
data/models/support_escalation.joblib
ml/model_cards/support_escalation.json
logs/build/support_escalation.log
```

Important result:

```text
signal_gate_passed: false
test ROC-AUC: 0.4974
test AP: 0.09799
```

Conclusion:

The model should **not** be used to decide whether a customer gets a human. It is
documented as a failed signal experiment.

### `ml/training/churn_prediction.py`

Local branch work adds a churn-prediction model and model card. It is currently
part of uncommitted local work and still needs cleanup because Ruff reports line
length issues.

### `ml/training/customer_segmentation.py`

Local branch work for customer segmentation. It reads `customer_360` fields and
clusters or segments customers for analysis/demo purposes. It is not part of the
core eligibility decision.

## Agent Cognition

### `agent/cognition/scm.py`

The Semantic Cognition Matrix tracks facts, sources, missing evidence, and
contradictions.

It exposes exactly four public methods:

```python
assert_fact(subject, predicate, value, source, confidence)
missing_evidence()
contradictions()
snapshot()
```

What it does:

- requires a typed source for every fact;
- rejects invalid confidence values;
- rejects non-JSON-safe values;
- preserves conflicting facts instead of overwriting them;
- requires `identity_verified=True` explicitly;
- reports missing required slots by intent;
- reports contradictions by value, provenance, and precondition;
- returns a JSON-safe snapshot with epistemic status.

What it does not do:

- It does not decide eligibility.
- It does not approve actions.
- It does not replace policy.

Tests:

- `tests/cognition/test_scm_contract.py`
- `tests/cognition/test_scm_edge_cases.py`

The SCM is complete according to the project checklist.

## Policy Engine

### `agent/policies/eligibility_v1.yaml`

The versioned credit-eligibility policy. It contains:

- data cutoff;
- thresholds;
- catalog/product conditions;
- active product assumptions;
- reserves and liquidity rules;
- behavior when observed capacity is absent;
- abstention messages.

This file is the decision authority, not the LLM.

### `agent/policies/engine.py`

Evaluates the YAML policy deterministically.

Major pieces:

- `Cliente`, `ProductoVigente`, and `ProductoDeAhorro` represent verified inputs.
- `Politica.cargar()` reads the YAML.
- `Politica.evaluar(cliente)` returns a `Decision`.
- `Decision.hechos` publishes the facts and calculations needed for grounding.
- `cifra()` formats money/numbers using Spanish/Portuguese conventions.

Important protections:

- Missing product limit or rate now causes abstention instead of silently skipping
  a debt.
- Missing observed capacity applies a conservative restriction instead of using
  full margin.
- The policy publishes enough calculation details for the grounding checker to
  validate rejection explanations.
- Product offers can be evaluated across multiple terms.

Tests:

- `tests/policies/test_eligibility_engine.py`
- `tests/policies/test_formato_de_cifras.py`
- `tests/policies/test_hechos_anclan_la_respuesta.py`
- `tests/policies/test_plazos_ofertables.py`
- `tests/policies/test_sin_capacidad_observada.py`

## Agent Tools

The tools implement the “read facts from trusted systems” and “write only with
verification” parts of the architecture.

### `agent/tools/registry.py`

Defines tool registration, roles, sessions, tool specs, parameters, and results.

Important behavior:

- tools are allowlisted by role;
- tools cannot accept `customer_id` as a user parameter;
- `customer_id` must come from the verified session;
- tool outputs carry grounded values for later checking.

Tests:

- `tests/tools/test_registry.py`

### `agent/tools/store.py`

Read-only analytical store wrapper. It knows how to query DuckDB, convert values,
derive income currency by country, and report conversion failures.

It separates analytical reads from write/ledger behavior.

### `agent/tools/customer.py`

Customer-facing facts and identity tools:

1. `verify_identity`
2. `get_customer_profile`
3. `get_customer_credit_products`
4. customer asset/product reads

Important behavior:

- identity comparison uses constant-time comparison;
- document verification does not leak `customer_id`;
- customer profile converts income to USD;
- credit products report missing limits/rates instead of filling with zero;
- product currency is read from product rows, not guessed by country.

Tests:

- `tests/tools/test_customer_tools.py`

### `agent/tools/credit.py`

Credit-related tools. These gather policy inputs such as capacity, last real
activity, payment history, and product conditions.

Important design:

- activity queries filter approved transactions only;
- event date, process date, and product opening date are all respected;
- impossible or future transactions are excluded.

Tests:

- `tests/tools/test_credit_tools.py`

### `agent/tools/cases.py`

Creates structured escalation cases.

Design:

- a customer can always ask for a human;
- escalation produces a structured case file, not a raw transcript;
- case output is meant to avoid PII leakage.

### `agent/tools/ledger.py`

Append-only write store for actions and cases.

Design:

- writes are idempotent by key;
- actions are read back before confirmation;
- no update/delete style mutable ledger behavior is used for confirmed facts.

Tests:

- `tests/tools/test_escrituras_y_relectura.py`

## Agent Core

### `agent/core/access_guard.py`

Implements identity/session security around the identity tool.

Important behavior:

- three attempts and backoff;
- JWT contains `customer_id`;
- customer identity comes from verified factors, not request parameters;
- time handling was corrected to avoid timezone-dependent failures.

Tests:

- `tests/core/test_access_guard.py`

### `agent/core/orchestrator.py`

The six-stage state machine:

1. `IDENTIFY` — local extension, verifies session before personal data.
2. `UNDERSTAND` — checks intent, required slots, SCM evidence.
3. `DECIDE` — evaluates policy.
4. `ACT` — calls the selected tool/action.
5. `VERIFY` — validates grounded output and read-back.
6. `ESCALATE` — creates a structured handoff.

Important behavior:

- It is tested without an LLM.
- If evidence is missing, it asks instead of guessing.
- Unknown intents escalate.
- Direct human requests escalate.
- Product info can avoid credit-decision stages.
- SCM contradictions are handled before deciding.

Tests:

- `tests/core/test_orchestrator.py`

### `agent/core/verifier.py`

Handles verification of executed actions and the VERIFY stage.

Tests:

- `tests/core/test_verifier.py`

### `agent/core/handoff.py`

Builds structured escalation files for human advisors.

Important behavior:

- validates schema;
- removes PII;
- includes known facts, missing facts, decisions, and open questions;
- degrades to a minimal case if full assembly fails.

Tests:

- `tests/core/test_handoff.py`

## Guardrails

### `agent/guardrails/grounding.py`

The GroundingChecker enforces the rule: no unsupported numbers in final answers.

It:

- extracts dates, numbers, percentages, emails, and long digit sequences;
- compares rendered text forms, not raw floats;
- accepts Spanish/Portuguese and English separator variants;
- blocks orphan numbers or PII;
- records traceable verification results.

Why rendered comparison matters:

- `0.6` may appear as `60%`;
- `1234.56` may appear as `1.235` or `1,235`;
- comparing floats directly would block correct answers.

Tests:

- `tests/guardrails/test_grounding.py`
- policy grounding tests in `tests/policies/`

### `agent/guardrails/injection.py`

Detects and labels prompt-injection patterns across Spanish, Portuguese, and
English. It canonicalizes text, strips some obfuscation, handles accents, and
tracks suspicious requests.

Important conclusion:

Detection does not generalize perfectly. The security guarantee is therefore not
“we detect every attack”; it is “even undetected attacks cannot access other
customers, call unregistered tools, invent grounded numbers, or write without
idempotency.”

Tests:

- `tests/guardrails/test_injection.py`
- `tests/guardrails/test_contencion_inyeccion.py`

Fixture:

```text
tests/fixtures/injection_corpus.json
```

## API Layer

### `api/main.py`

Local FastAPI mock/backend in the current uncommitted work.

Endpoints:

- `POST /api/chat`
- `GET /health`

Behavior:

- loads `.env`;
- allows CORS from local Next.js;
- reads `data/noema.duckdb`;
- calls a Gemini HTTP endpoint if `GEMINI_API_KEY` exists;
- optionally loads `data/models/support_escalation.joblib`;
- escalates if the simple SCM or escalation model says to escalate.

Current warnings:

- The SQL query interpolates `customer_id` with an f-string. That must be
  parameterized before production or PR.
- It expects `GEMINI_API_KEY`, while `.env.example` documents Anthropic settings.
- It treats the support escalation model as actionable, but the model review says
  the escalation experiment did not pass its signal gate.
- Ruff currently reports S608 and line-length issues here.

This API is useful for local exploration, but it is not yet aligned with the
stricter core agent contract.

## Local Prototype

### `prototype/core.py`

A self-contained local demo core.

It uses:

- SQLite at `data/prototype/demo.sqlite`;
- local sessions and CSRF;
- deterministic intent routing first;
- optional local Ollama classification;
- demo balance, transfer, card-blocking, cases, and analysis flows;
- SCM snapshots;
- read-back verification for simulated writes.

Important behavior:

- every browser session gets a demo account;
- transfers are simulated and only to a demo savings destination;
- card blocking is simulated;
- confirmed actions are read back;
- cases are queued locally;
- eligibility abstains unless identity and evidence are verified;
- voice input is reviewed before sending.

### `prototype/app.py`

FastAPI app for the prototype. It serves:

- session creation;
- chat;
- confirmation;
- transcription;
- local cases;
- static web files.

### `prototype/web/`

Small browser UI for the local prototype.

### `prototype/README.md`

Run instructions:

```bash
uv pip install --python .venv/bin/python -r prototype/requirements.txt
ollama pull qwen2.5:1.5b
ollama create noema-bank-local -f prototype/Modelfile
.venv/bin/python -c "from faster_whisper.utils import download_model; download_model('tiny', output_dir='data/models/whisper-tiny')"
.venv/bin/python -m uvicorn prototype.app:app --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

Tests:

- `tests/test_local_prototype.py`

## UI

### `ui/`

Next.js frontend in the current local work.

Important files:

- `ui/package.json`
- `ui/src/app/page.tsx`
- `ui/src/app/layout.tsx`
- `ui/src/app/globals.css`

Current behavior:

- simple chat interface;
- sends messages to `http://localhost:8000/api/chat`;
- uses hardcoded demo `customer_id`;
- displays assistant/user messages.

Validation already run:

```text
npm run lint
```

Result:

```text
0 errors, 1 warning
```

Warning:

```text
ui/src/app/page.tsx: unused catch variable `e`
```

Production build status:

```text
npm run build
```

failed because Next.js tried to fetch Google-hosted Geist fonts and the
environment could not reach `fonts.googleapis.com`.

Fix options:

- self-host fonts;
- remove `next/font/google`;
- allow proxy/network access during build.

## Scripts

### `scripts/checklist.py`

Generates current checklist status from `docs/checklist.json` and real evidence.
Output:

```text
docs/knowledge/checklist.md
docs/knowledge/checklist_state.json
logs/build/*_checklist.log
```

### `scripts/changelog.py`

Generates `CHANGELOG.md` from Git history and task metadata.

### `scripts/review_contributions.py`

Reviews who touched what and whether changes crossed ownership boundaries.
Output:

```text
docs/knowledge/contributions.md
```

### `scripts/worklog.py`

Creates daily worklog entries under `logs/worklog/`.

### `scripts/generate_schemas.py`

Helps generate or update schema-related artifacts.

## Documentation

Major docs:

| File | Purpose |
|---|---|
| `README.md` | Project overview and commands |
| `CLAUDE.md` | Operating contract and ownership rules |
| `LIMITATIONS.md` | Honest limits and cost to make real |
| `docs/00_challenge_brief.md` | Challenge/rubric interpretation |
| `docs/01_data_audit.md` | Dataset audit |
| `docs/02_architecture.md` | Architecture |
| `docs/03_credit_policy.md` | Credit policy explanation |
| `docs/04_evaluation.md` | Evaluation protocol |
| `docs/05_security.md` | Security model |
| `docs/06_runbook.md` | Operating runbook |
| `docs/07_scm_spec.md` | SCM specification |
| `docs/09_etl_spec.md` | ETL/data spec |
| `docs/10_federico_runbook.md` | Federico runbook |
| `docs/11_federico_team_handoff.md` | Federico delivery handoff |
| `docs/12_cambios_para_federico.md` | Changes and warnings for Federico |
| `docs/13_interes_producto_y_cupo.md` | Product-interest and quota work |
| `docs/14_red_profunda_y_asesor.md` | Deep model and advisor |
| `docs/15_experimento_profundidad.md` | Depth experiment |
| `docs/16_revision_modelos_y_escalamiento.md` | Model and escalation review |
| `docs/17_noema_local_arquitectura.md` | Local prototype architecture |
| `docs/18_noema_ai_final_architecture.md` | AI architecture note |
| `docs/19_estado_integracion_federico.md` | Branch/merge/test status |
| `docs/20_reporte_completo_codigo.md` | This report |

ADR files:

| ADR | Topic |
|---|---|
| `ADR-0001` | Workflow and responsibility split |
| `ADR-0002` | Data route and Databricks constraints |
| `ADR-0003` | Ground truth from templates |
| `ADR-0004` | Temporal cutoff and leakage |
| `ADR-0005` | Capacity and unobserved conditions |
| `ADR-0006` | Eligibility by policy, not model |
| `ADR-0007` | Product interest and quotas |
| `ADR-0008` | Deep network and evidence gate |
| `ADR-0009` | Tool catalog |
| `ADR-0010` | Six-stage agent cycle |
| `ADR-0011` | Multiple product terms |
| `ADR-0012` | Separate write store |

Knowledge docs:

- `docs/knowledge/findings.md`: findings F-001 through F-048 and additional audit notes.
- `docs/knowledge/checklist.md`: generated checklist status.
- `docs/knowledge/contributions.md`: contribution ledger.
- `docs/knowledge/metodo_estadistico.md`: statistical method contract.
- `docs/knowledge/pendientes_concepto.md`: conceptual pending work.

## Logs

Logs live under `logs/`. They are evidence of actual runs and decisions.

### `logs/README.md`

Defines logging rules, PII expectations, and retention conventions.

### Build logs

| Log | What it records |
|---|---|
| `logs/build/dbt/dbt.log` | dbt build execution details |
| `logs/build/dq_report.json` | full data-quality audit report |
| `logs/build/capacity_metrics.json` | payment-capacity model metrics |
| `logs/build/interest_feature_store.log` | feature-store build summary |
| `logs/build/deep_interest_training.log` | deep-interest model training/test metrics |
| `logs/build/depth_experiment.log` | depth experiment architectures, seeds, epochs |
| `logs/build/support_escalation.log` | support-escalation experiment metrics |
| `logs/build/deep_checklist.log` | checklist snapshot after deep-interest work |
| `logs/build/depth_checklist.log` | checklist snapshot after depth experiment |

Important log excerpts:

Capacity:

```text
training_rows: 150000
validation_rows: 14820
eligible_validation_rows: 825
validation_mae: 92369.45
baseline_mae: 92731.04
```

Feature store:

```text
rows: 141,483
with label: 76,906
strict cohort: 7,078
complete cohort: 76,906
```

Deep-interest training:

```text
deep_mlp ROC-AUC: 0.6739
logistic ROC-AUC: 0.6767
prior ROC-AUC: 0.5000
selected: logistic
```

Depth experiment:

```text
three_hidden seeds: 42, 43, 44
six_hidden seeds: 42, 43, 44
selection log-loss recorded for each
```

Support escalation:

```text
signal_gate_passed: false
test ROC-AUC: 0.4974
```

### Worklogs

| File | Summary |
|---|---|
| `logs/worklog/2026-09-27-eduardo.md` | Initial repo, ingestion, audit, project scaffolding |
| `logs/worklog/2026-09-28-fedevargas93.md` | Federico data/capacity/SCM work |
| `logs/worklog/2026-09-29-eduardo.md` | Risk-target investigation and policy direction |
| `logs/worklog/2026-09-30-eduardo.md` | Feature-store and policy findings |
| `logs/worklog/2026-09-30-fedevargas93.md` | ML-11 product interest and ML-12 deep advisor |
| `logs/worklog/2026-10-01-eduardo.md` | Tools, policy fixes, write/read-back, AG-03/AG-04 |
| `logs/worklog/2026-10-01-fedevargas93.md` | ML-13 depth experiment |
| `logs/worklog/2026-10-02-eduardo.md` | Handoff, grounding, anti-injection, AG-08/AG-10 |

### Agent, ingest, eval logs

Directories exist:

```text
logs/agent/
logs/ingest/
logs/eval/
```

At the moment they mostly contain placeholders or are reserved for runtime traces.

## Test Suite

Latest full run:

```bash
.venv/bin/python -m pytest
```

Result:

```text
945 passed, 1 warning in 39.88s
```

Warning:

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
install httpx2 instead.
```

Test groups:

| Test folder/file | What it covers |
|---|---|
| `tests/data/` | data pipeline, feature contracts, leakage protection |
| `tests/cognition/` | SCM contract and edge cases |
| `tests/policies/` | deterministic policy, formatting, facts, terms, capacity absence |
| `tests/tools/` | registry, customer tools, credit tools, write/read-back |
| `tests/core/` | access guard, orchestrator, verifier, handoff |
| `tests/guardrails/` | grounding checker, injection detection, containment |
| `tests/ml/` | product interest, deep interest, depth experiment, churn, feature store |
| `tests/test_local_prototype.py` | local prototype session/actions/chat behavior |

Earlier validation milestones recorded in worklogs:

| Date | Result |
|---|---|
| 2026-09-28 | 61 tests with SCM enabled/disabled, according to handoff |
| 2026-09-30 | 149 tests for ML-11 product interest |
| 2026-09-30 | 160 tests for ML-12 deep advisor |
| 2026-10-01 | 162 tests for ML-13 depth experiment |
| 2026-10-01 | 303 tests after tool work |
| 2026-10-02 | 945 tests after merging latest main |

## Current Quality Status

What is green:

- Full Python pytest suite: **945 passed**.
- Merge from `origin/main` into Federico branch completed.
- Pre-commit hooks passed during the merge commit.
- `gitleaks` passed during merge commit.

Known issues still open:

1. `api/main.py` has unsafe SQL string interpolation and line-length issues.
2. The local API expects Gemini config while `.env.example` documents Anthropic.
3. The local API uses the support-escalation artifact as a trigger even though the
   experiment failed its signal gate.
4. `tmp/` contains unrelated local files and causes lint noise.
5. The UI production build fails on Google Fonts fetch.
6. `ui/src/app/page.tsx` has one unused catch variable warning.
7. The demo/API/UI/prototype layer is still uncommitted local work and should be
   split into clean commits.

## What Has Been Done So Far

In plain English:

1. We built the data foundation.
   - Downloaded and audited the dataset.
   - Found that the data dictionary is not fully trustworthy.
   - Built local DuckDB/dbt silver and gold layers.
   - Created data-quality reports and quarantine logic.

2. We proved many apparent ML targets are not real business targets.
   - Risk labels behave synthetically.
   - Transaction amounts are synthetic/uniform.
   - Some fields are snapshots, not history.
   - The system should not pretend to learn credit approval from this data.

3. We built conservative models where useful.
   - Payment-capacity proxy.
   - Product-interest conversion model.
   - Deep-learning challengers for product interest.
   - Escalation experiment, which correctly failed activation.

4. We built the deterministic decision layer.
   - YAML policy.
   - Python policy engine.
   - Tests around eligibility, product terms, facts, and formatting.

5. We built the semantic tracking layer.
   - SCM records facts, sources, missing evidence, and contradictions.
   - It reports; it does not decide.

6. We built agent tools and orchestration.
   - Identity verification.
   - Customer profile tools.
   - Credit-product tools.
   - Case tools.
   - Read/write stores.
   - Six-stage orchestrator.
   - Access guard and handoff builder.

7. We built safety guardrails.
   - Grounding checker for all numbers.
   - Injection detection and containment.
   - PII and unsupported-number blocking.

8. We built demo layers.
   - FastAPI mock API.
   - Local prototype with SQLite, Ollama, Whisper, demo actions.
   - Next.js UI.

9. We documented the work heavily.
   - ADRs.
   - findings.
   - worklogs.
   - runbooks.
   - branch integration report.
   - this complete code report.

## Recommended Next Steps

Before merging or presenting the demo:

1. Clean `api/main.py`:
   - parameterize DuckDB query;
   - align LLM provider config;
   - decide whether this API or `prototype/app.py` is the official demo path.
2. Remove or ignore `tmp/`.
3. Fix the UI warning and production-font issue.
4. Split local work into clear commits:
   - docs/reporting;
   - API;
   - prototype;
   - UI;
   - churn/segmentation.
5. Run:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
cd ui && npm run lint
cd ui && npm run build
```

6. Update `docs/19_estado_integracion_federico.md` after those checks.

## Bottom Line

The repo now contains a serious end-to-end banking-agent architecture: audited
data, deterministic policy, semantic evidence tracking, agent tools, verification,
guardrails, and local demo layers. The strongest part is not that it “uses AI”;
it is that it knows when **not** to trust AI.

The remaining work is mostly integration hygiene: choose the final demo path,
clean the local API/UI/prototype layer, and make the frontend build reproducible.
