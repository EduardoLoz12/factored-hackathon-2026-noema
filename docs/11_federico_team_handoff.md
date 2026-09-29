# Federico handoff: data platform, payment capacity, and SCM

**Date:** 28 September 2026
**Working branch:** `trabajo/federico-data-cognition`
**Local commits:** `3ba73a2`, `b5eee82`, `f763872`

## What was delivered

Federico's work covered three connected areas:

1. A reproducible data-quality audit and quarantine process for all 13 source tables.
2. Silver and gold transformations for the agent and downstream models.
3. A conservative payment-capacity model and the Semantic Cognition Matrix (SCM).

The local pipeline processed **23,495,188 source rows**. The dbt build completed all
20 models and 5 data tests. The Python test suite passed with SCM enabled and disabled.

The language model still does not decide credit eligibility. The capacity model supplies one
measured input, the SCM reports what is known or missing, and a separate versioned policy must
make the final decision.

## Work performed, step by step

### 1. Read the project contracts and audited the available data

The implementation followed `docs/09_etl_spec.md`, `docs/07_scm_spec.md`, the existing data
audit, and the temporal-cutoff ADR. The raw Parquet files under `data/bronze/` were treated as
immutable evidence.

The manifest was converted into a versioned column inventory. Semantic contracts were then
added by hand so observed types, ranges, required fields, enumerations, primary keys, and
foreign keys were reviewed rather than generated blindly.

### 2. Ran quality checks over all 13 tables

`data_platform/contracts/audit.py` now measures:

- Actual rows compared with documented counts.
- Missing values and structural nulls.
- Duplicate primary keys.
- Broken foreign keys.
- Phone-country inconsistencies.
- Product-currency inconsistencies.
- Transactions whose operation and processing dates differ.

Every row is accounted for. A row either reaches the validated layer or is written to a
quarantine with its rejection reason and original lineage.

The audit found no excess primary-key duplicates and no broken essential customer/product
relationships. It did find **150,826 invalid optional branch references**:

- 149,995 customer registration-branch references.
- 831 service-agent branch references.

Dropping those records would have destroyed nearly the whole customer table. The cleaned
layer therefore sets only the invalid optional relationship to `NULL`, while preserving the
original row and reason in `data/quarantine_references/`.

### 3. Built the silver layer

All 13 validated datasets are typed and normalized in dbt. The important changes are:

- Dates, timestamps, numbers, and booleans are explicitly cast.
- Product names are normalized into one Spanish vocabulary.
- Transaction types are normalized from English into Spanish.
- The redundant call-center `contact_reason` field is removed because it duplicates
  `reason_category`.
- USD transaction values are recalculated using the exchange rate from the operation date.
- **607 transactions** without an exact-date exchange rate go to FX quarantine instead of
  receiving a guessed or future rate.

Bronze was never modified.

### 4. Built the gold layer

The local build produces four business tables:

| Table | Rows | Purpose |
|---|---:|---|
| `customer_360` | 150,000 | Customer identity, products, balances, tenure, and delinquency summary |
| `credit_features_asof` | 141,445 | Cutoff-safe behavioral variables for modeling |
| `product_policy` | 9 | Observed product catalog with policy readiness state |
| `dq_report` | 682 | Data-quality metrics ready for analytics |

`product_policy` intentionally has `policy_ready=false` and `NULL` offer conditions. The
dataset contains no defensible score, amount, term, or interest thresholds. Eduardo's
versioned policy is required before these rows can support an eligibility decision.

### 5. Prevented temporal leakage

The declared feature cutoff is **31 December 2025**. Both `transaction_date` and
`process_date` must be earlier than the cutoff. This blocks late-arriving records that happened
earlier but were not yet available to the system.

The latest event and processing dates in `credit_features_asof` are both 30 December 2025.
The feature table excludes:

- `current_balance`
- `last_transaction_date`
- `product_status`
- `days_past_due`
- Any post-cutoff aggregate

Dedicated dbt and Python tests fail if future records or prohibited columns enter the feature
table.

### 6. Built the payment-capacity model

The model uses approved transaction history grouped by customer and currency. It does not use
the declared `estimated_monthly_income`, which is missing for 30,033 customers and is not
directly observed cash flow.

The predictive variables are:

| Variable | Meaning |
|---|---|
| `mean_deposits` | Average deposits during the previous three complete months |
| `mean_outflows` | Average payments, purchases, and withdrawals over those months |
| `min_surplus` | Lowest monthly value of deposits minus outflows |
| `active_months` | Number of months with observed activity |

Transfers and adjustments are counted as `ambiguous_count`. They are not used as directional
cash flow because the dataset does not identify whether they are incoming, outgoing, or
committed. A recent ambiguous movement causes abstention.

The training target is a conservative proxy:

```text
minimum(
    positive monthly deposits minus outflows,
    30% of monthly deposits
)
```

Features use the preceding three months, while the target belongs to the following month.
Missing calendar months are inserted with zero activity. A positive linear regression is
trained, and its output is clipped between zero and the conservative cash-flow ceiling.

### 7. Evaluated the model with a temporal holdout

The model trained on 150,000 examples and was evaluated on 14,820 later examples beginning
1 October 2025.

| Currency | Model MAE | Baseline MAE | Improvement |
|---|---:|---:|---:|
| ARS | 28,725.90 | 29,387.48 | 2.25% |
| COP | 343,242.66 | 344,184.99 | 0.27% |
| USD | 84.15 | 84.15 | 0.00% |
| Aggregate | 92,369.45 | 92,731.04 | 0.39% |

MAE is measured in native currency units, so raw ARS, COP, and USD errors must not be compared
to each other. The learned model was selected because aggregate holdout MAE was lower, but its
gain over the conservative baseline is modest.

Only 825 of the 14,820 validation rows, **5.57%**, met the conditions for an estimate. This
low coverage reflects the current safety rule: three active months and no ambiguous recent
cash flow. Broader coverage requires better transfer-direction data or a revised, validated
business rule.

### 8. Verified concrete prediction behavior

Examples use synthetic identifiers from the supplied dataset.

| Scenario | Result |
|---|---|
| `CLI-E7PQSLAHL7VP`, COP, positive three-month surplus | Estimated capacity: 1,308,614.45 COP/month |
| `CLI-YXI5AR5Q9F5P`, COP, smaller surplus | Estimated capacity: 512,593.87 COP/month |
| `CLI-0ZR8KOSEFPRS`, USD, sufficient history but no positive ceiling | Estimated capacity: 0 USD/month |
| `CLI-NNKQ1P33O6CK`, COP, ambiguous cash flow | Abstain: `insufficient_or_ambiguous_cashflow` |
| Customer without transaction history | Abstain: `no_history` |

An estimate is not an approval. It is a bounded input to the future eligibility policy.

### 9. Completed and hardened the SCM

`agent/cognition/scm.py` now:

- Requires a typed source for every fact.
- Rejects invalid confidence values and non-JSON evidence.
- Preserves conflicting facts rather than overwriting them.
- Requires literal boolean `True` for verified customer identity.
- Reports missing evidence by intent.
- Reports value, provenance, and precondition contradictions.
- Produces a JSON-safe snapshot with `COMPLETE`, `INCOMPLETE`, or `CONFLICTED` status.
- Copies mutable values so external code cannot alter recorded evidence afterward.

All 26 acceptance tests and the added adversarial cases pass. The full repository suite also
passes with `SCM_ENABLED=false`.

## Important measured data findings

- 23,495,188 actual source rows versus roughly 19 million documented.
- Zero excess primary-key duplicates across the 13 tables.
- 72,548 customer phone-country mismatches; reported but not auto-corrected.
- 1,106,307 transactions whose operation date differs from processing date.
- 200,398 products for Mexican customers denominated in currencies other than MXN.
- 30,033 customers without declared monthly income.
- 268,028 structurally valid null credit limits and 6,655 genuinely missing applicable values.

These findings are retained in `dq_report`; they were not hidden through imputation.

## How to reproduce the local result

Use Python 3.11 or later in a virtual environment:

```bash
pip install -e ".[dev,data]"
make audit
make build
make train-capacity
pytest
SCM_ENABLED=false pytest
```

Expected checks:

- Full audit: 13 tables and 23,495,188 rows.
- dbt: 20 models plus 5 tests, all passing.
- Python: 61 tests passing with SCM enabled.
- Python: 61 tests passing with SCM disabled.
- Lint, formatting, and pre-commit secret scan passing.

Generated local artifacts are intentionally ignored by Git:

- `logs/build/dq_report.json`
- `logs/build/capacity_metrics.json`
- `data/models/capacity.json`
- `data/gold/*.parquet`
- `data/noema.duckdb`

## Files a teammate should read first

- `docs/10_federico_runbook.md`: concise execution and integration guide.
- `docs/federico_model_and_data_results.txt`: detailed numeric results.
- `docs/decisions/ADR-0005-capacidad-y-condiciones-no-observadas.md`: assumptions and limits.
- `data_platform/contracts/audit.py`: full audit and quarantine behavior.
- `data_platform/dbt/models/`: silver and gold transformations.
- `ml/training/capacity.py`: training, evaluation, and inference behavior.
- `agent/cognition/scm.py`: semantic-state contract.

## Remaining work and ownership

### Eduardo / agent integration

- Provide the versioned credit policy and real product thresholds.
- Connect `predict_capacity` to the shared serving predictor.
- Feed verified tool results into the SCM from the orchestrator.
- Implement the `SCM_ENABLED` ablation at orchestration level.
- Run the held-out `tools` versus `tools_scm` evaluation.

### External environments

- Run and verify the Databricks upload and dbt profile with real workspace credentials.
- Run the Postgres export with the loader role and verify destination read-back.

Both integrations have dry-run plans and verification logic, but they have not been marked
complete without access to the real destinations.

## Current Git status

The implementation and result files are committed locally on
`trabajo/federico-data-cognition`. GitHub rejected the previous push because account
`fedevargas93` does not have write access to `EduardoLoz12/factored-hackathon-2026-noema`.
The repository owner must add that account as a collaborator, or the team must choose a fork
workflow, before the commits can be published.
