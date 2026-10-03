# Deep Validation Report

Date: 2026-10-02

Branch validated: `trabajo/federico-data-cognition`

Purpose: deep validation of the current code after merging latest `origin/main` into
Federico's branch, with module-by-module and line-level review of the active code
paths.

## Executive Result

The project is runnable locally and the validation suite is green.

Evidence:

- Backend tests: `945 passed, 1 warning`
- Python lint on changed/runtime modules: `All checks passed`
- UI lint: passed
- UI production build: passed with `next build --webpack`
- Policy diagnostics: `pass`, policy version `3`, four checks
- Databricks dry run: `7,686` files, `2,355,684,137` bytes, no cloud write
- Git whitespace check: clean

Fixes made during this validation:

- Removed Google Fonts from `ui/src/app/layout.tsx` so the UI build does not need
  live font downloads.
- Changed `ui/package.json` build script to `next build --webpack` because Next 16
  Turbopack fails in this environment while binding an internal port.
- Wrapped a long line in `ml/training/churn_prediction.py` so the stricter lint pass
  is clean.

## Validation Commands And Results

### Backend

```bash
.venv/bin/python -m pytest
```

Result:

```text
945 passed, 1 warning in 40.28s
```

The warning is from FastAPI/Starlette test tooling:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated.
```

### Python Lint

```bash
.venv/bin/ruff check api/main.py data_platform/databricks/upload_to_volume.py ml/training/churn_prediction.py prototype tests/test_local_prototype.py
```

Result:

```text
All checks passed!
```

### UI

```bash
npm run lint
npm run build
```

Result:

```text
eslint completed successfully
next build --webpack completed successfully
```

### Policy Diagnostics

```text
pass 3 4
True Eligible verified customer receives at least one policy offer | elegible=True, abstencion=False, offers=1
True Missing income produces abstention | abstencion=True, elegible=False
True Incomplete current debt terms produce abstention | abstencion=True, motivos=1
True Missing observed capacity restricts mortgage offers | offers=Tarjeta Crédito
```

### Databricks Dry Run

```json
{"bundle": "databricks-inputs", "files": 7686, "bytes": 2355684137, "executed": false, "verified_files": 0}
```

## Line-Level Review: `api/main.py`

Lines 1-15:

- Imports are valid and narrow enough for the current API.
- `requests` is only used for Gemini.
- `duckdb`, `joblib`, and `pandas` are runtime dependencies.
- The policy-engine import supports the diagnostics endpoint.

Lines 16-26:

- Environment loading and FastAPI app setup are correct for local development.
- CORS is limited to local UI origins.
- Production gap: allowed origins should be config-driven.

Lines 29-35:

- `SemanticCognitionMatrix` is only a keyword router.
- It catches obvious English escalation terms.
- Gap: it does not catch Spanish escalation terms as well as the local prototype.

Lines 38-55:

- The customer query is parameterized with `WHERE customer_id = ?`.
- This fixes the SQL injection risk from direct string interpolation.
- Gap: the DuckDB connection should use a context manager so it closes on exceptions.
- Gap: `print(f"DB Error: {e}")` should become structured logging.

Lines 58-80:

- `GEMINI_API_KEY` is loaded once at startup.
- Missing or placeholder keys fail closed with a clear local-demo message.
- Operational gap: key rotation requires process restart.

Lines 82-94:

- Customer profile values are injected into the LLM context when available.
- Gap: generated answers are not passed through the grounding verifier before return.

Lines 95-127:

- Gemini call has a timeout and limited retry behavior.
- Gap: the prompt does not explicitly include the latest `query`; it relies on
  `history`. Direct API callers can send an empty history and the model will not see
  the current message.
- Gap: `res.raise_for_status()` is missing.
- Gap: response parsing assumes `candidates[0].content.parts[0].text` always exists.
- Gap: API key is in the URL query string, so logs/proxies must be handled carefully.

Lines 140-144:

- Escalation model loading fails safe by disabling the model.
- Gap: corrupted model artifacts are silently hidden.

Lines 147-160:

- Request/response models are clear.
- Gap: `customer_id` and `message` lack length constraints.

Lines 162-173:

- Diagnostics response models are explicit and align with the UI.

Lines 175-263:

- Diagnostics run the real deterministic policy engine.
- The four checks cover eligible customer, missing income, missing obligation terms,
  and missing observed capacity.
- Gap: UI diagnostics do not yet include injection, grounding, access-token, or
  write-readback checks.

Lines 266-297:

- `/api/chat` returns a stable response shape.
- Gap: escalation model prediction errors are not caught.

Lines 300-307:

- Health and policy diagnostic endpoints are simple and valid.

Verdict: good local demo API, but not production-ready until it uses the full
orchestrator/verifier path.

## Line-Level Review: `data_platform/databricks/upload_to_volume.py`

Lines 1-6:

- Module purpose is clear: plan or upload local artifacts to an existing Unity
  Catalog Volume.

Lines 10-14:

- Imports are standard library only until execute mode.
- Good: Databricks SDK is lazy-loaded.

Lines 16-33:

- Bundles are explicit.
- `databricks-inputs` includes bronze, validated, and quality.
- `complete` adds gold, quarantine, models, prototype database files, and logs.

Lines 36-39:

- SHA-256 hashes are computed from file bytes.

Lines 41-59:

- Files are collected deterministically.
- Duplicate paths are skipped.
- Symlinks are rejected.
- Logs outside `data/` are mapped under remote `logs/`.

Lines 62-80:

- Volume path must be `/Volumes/catalog/schema/volume`.
- `..` path traversal is rejected.
- Required local datasets are checked before planning.
- Validation found and fixed the required-file check before this report: it now
  checks actual glob matches.

Lines 83-123:

- Dry run returns counts and byte totals without writing to Databricks.
- Execute mode requires `DATABRICKS_HOST` and `DATABRICKS_TOKEN`.
- Upload verifies remote bytes by downloading and comparing SHA-256.
- Gap: partial uploads are not rolled back.

Lines 126-150:

- CLI is clear.
- `--execute` is opt-in.
- `--plan-file` can preserve the checksum manifest.

Verdict: strong dry-run and checksum validation; add staging/rollback before heavy
production use.

## Line-Level Review: `ml/training/churn_prediction.py`

Lines 1-18:

- Imports are appropriate and lint-clean.

Lines 20-24:

- Output directories are created.
- DuckDB opens read-only.
- Gap: use a context manager to guarantee close.

Lines 26-46:

- Training data comes from `noema_gold.customer_360`.
- Income is converted to USD for Colombia, Argentina, and Mexico.
- Gap: exchange rates are hard-coded; prefer the platform exchange-rate table or
  already-normalized USD fields.

Lines 48-50:

- Churn target is based on `Closed`, `Suspended`, and `Inactive`.
- This removes the earlier target-leakage problem.

Lines 51-65:

- Features are explicit.
- Rows missing required features are dropped after structural null handling.
- Gap: if a class disappears after dropping rows, stratified split can fail.

Lines 67-82:

- Numeric and categorical preprocessing are correct.
- Random forest uses balanced class weights.

Lines 84-96:

- Split is stratified.
- Metrics are standard.
- Gap: `precision_score`, `recall_score`, and `f1_score` should use
  `zero_division=0` for rare one-sided predictions.

Lines 97-115:

- Model artifact and model card are written.
- Model card records target, features, model type, version, and metrics.

Verdict: improved and test-backed; remaining work is robustness and provenance.

## Line-Level Review: `ui/src/app/page.tsx`

Lines 1-23:

- Client component is correct.
- Types match backend diagnostics.
- Gap: `API_BASE` is hard-coded to localhost.

Lines 25-42:

- State handling and auto-scroll are correct.

Lines 44-77:

- Empty sends and duplicate sends are blocked.
- The UI sends `customer_id`, `message`, and joined history.
- Gap: hard-coded customer ID limits the UI to one demo customer.
- Gap: non-OK chat responses are not handled separately.
- Gap: no request timeout or abort controller.

Lines 79-95:

- Diagnostics fetch checks `response.ok`.
- Error message is understandable for local use.

Lines 97-151:

- Chat layout is functional and readable.
- Send button state is visible.

Lines 153-226:

- Policy Diagnostics panel exposes expected and observed policy results.
- Good: it makes policy behavior visible in the product UI.
- Gap: it does not yet validate all agent safety policies.

Verdict: good local UI; needs environment config and stronger error handling for
deployment.

## Line-Level Review: `ui/src/app/layout.tsx`

Lines 1-3:

- Imports are minimal.
- Google Fonts were removed, eliminating the network build dependency.

Lines 5-8:

- Metadata now names Noema instead of Create Next App.

Lines 10-16:

- Root layout is simple and build-safe.

Verdict: fixed and clean.

## Line-Level Review: `ui/src/app/globals.css`

Lines 1-13:

- Tailwind import and theme variables are valid.
- Font variables now use system stacks.

Lines 15-20:

- Dark-mode variables remain.

Lines 22-26:

- Body font fallback is consistent with the theme.

Verdict: clean and offline-build-safe.

## Line-Level Review: `prototype/app.py`

Lines 17-21:

- Local DB path is configurable.
- Trusted hosts and origins are localhost-only.

Lines 24-40:

- POST requests require allowed origin and `x-noema-local: 1`.
- Responses set no-store, nosniff, CSP, and permissions policy.

Lines 43-49:

- Authentication requires cookie plus CSRF header.

Lines 52-58:

- Request lengths are constrained.

Lines 60-67:

- Health endpoint honestly declares local demo mode.

Lines 70-75:

- Session cookie is HTTP-only and strict.
- Gap: no `secure=True`, acceptable for localhost HTTP but not production HTTPS.

Lines 78-100:

- Chat, confirm, and case reads are authenticated.
- Case list is session-scoped.

Lines 103-139:

- Audio upload is capped.
- Transcription fails closed if local Whisper model is absent.
- Gap: audio content type is not validated.

Verdict: safe for local demo, not intended for real banking connection.

## Line-Level Review: `prototype/core.py`

Lines 35-57:

- SQLite schema separates sessions, actions, ledger, and cases.

Lines 59-74:

- Session and CSRF secrets are random.
- Expiry is enforced.
- CSRF comparison uses constant-time comparison.

Lines 76-130:

- Deterministic routing runs before local LLM fallback.
- LLM is limited to intent classification.
- Unknown is safe fallback.

Lines 132-144:

- Case creation writes and reads back the case.

Lines 146-195:

- Confirmed actions are idempotent.
- Transfers validate positive amount and sufficient demo balance.
- Balance and card state are read back after writes.

Lines 196-215:

- Chat state explicitly marks bank identity as unverified.
- User language cannot self-verify identity.

Lines 216-235:

- Balance and transactions are session-scoped reads.

Lines 236-278:

- Human/complaint creates local cases.
- Transfer/freeze create pending actions that require confirmation.
- Amount parsing rejects negative, foreign-currency, ambiguous, and multi-number
  transfer requests.

Lines 279-300:

- Product and eligibility answers are grounded in policy artifacts.
- Demo mode refuses real approvals without verified evidence.

Lines 301-347:

- Analysis uses local model artifacts when present.
- Missing model artifacts cause abstention, not hallucinated estimates.

Lines 348-361:

- Unknown intent returns safe capabilities.
- Final output is included in SCM snapshot.

Verdict: this is the safest chatbot path in the repo and should guide the main API.

## Policy Engine Validation

File: `agent/policies/engine.py`

Validated behavior:

- Invalid financial inputs fail.
- Missing income abstains.
- Existing obligations missing limit or rate abstain.
- Revolving credit uses minimum-payment logic.
- Fixed loans use original term, not remaining term.
- Missing observed capacity restricts offers.
- Mortgage is excluded when capacity is missing.
- Every decision includes traceable facts, motives, and warnings.

Main tests:

- `tests/policies/test_eligibility_engine.py`
- `tests/policies/test_sin_capacidad_observada.py`
- `tests/policies/test_plazos_ofertables.py`
- `tests/policies/test_formato_de_cifras.py`
- `tests/policies/test_hechos_anclan_la_respuesta.py`

Verdict: deterministic, well-tested, and appropriate as the source of credit
eligibility decisions.

## Data Platform Validation

Validated behavior:

- Schema contracts define non-null primary keys.
- Quarantine conserves rows and records rejection reasons.
- Future and late transactions do not leak into feature training.
- Export planning fails before any cloud write when local prerequisites are missing.
- Databricks upload planning includes checksums.

Risk:

- Some SQL builders use f-strings for controlled table/column identifiers. This is
  acceptable for internal schema-driven code but must not be reused with user input.

Verdict: strong validation posture; cloud execution still requires Databricks
credentials and a target volume.

## Guardrails And Agent Tools Validation

Validated behavior from the test suite:

- Customer identity travels inside signed tokens, not request parameters.
- Invalid, expired, mismatched, or foreign tokens fail closed.
- Traces avoid token and PII leakage.
- Tool registry enforces declared permissions.
- Write actions are verified by reading back state.
- Prompt-injection attempts are contained.
- Grounding checks block unsupported numeric claims.
- Handoff/orchestration refuses unsafe evidence gaps.

Verdict: the safety architecture exists and passes tests. The main remaining gap is
that the simpler `api/main.py` chatbot endpoint does not yet enforce the whole stack.

## Remaining Findings

1. Main chat prompt can omit the latest user message.
   - File: `api/main.py`
   - Lines: 95-110
   - Severity: medium
   - Fix: include `query` explicitly in the Gemini prompt.

2. Main chat endpoint does not run final answers through grounding/verifier.
   - File: `api/main.py`
   - Lines: 95-124
   - Severity: high for production
   - Fix: route through the orchestrator/verifier path or add a grounding gate.

3. Main chat request validation is weaker than the local prototype.
   - File: `api/main.py`
   - Lines: 147-154
   - Severity: medium
   - Fix: add min/max lengths and stricter enums.

4. Churn model uses hard-coded exchange rates.
   - File: `ml/training/churn_prediction.py`
   - Lines: 39-44
   - Severity: medium
   - Fix: reuse platform-derived USD fields or exchange-rate tables.

5. Churn metrics need rare-class safeguards.
   - File: `ml/training/churn_prediction.py`
   - Lines: 92-95
   - Severity: low to medium
   - Fix: use `zero_division=0`.

6. Databricks upload has no rollback for partial upload.
   - File: `data_platform/databricks/upload_to_volume.py`
   - Lines: 103-123
   - Severity: medium operational risk
   - Fix: upload to a run-scoped staging prefix, verify all files, then promote.

7. UI API base and customer ID are hard-coded.
   - File: `ui/src/app/page.tsx`
   - Lines: 23 and 59
   - Severity: low for demo, medium for deployment
   - Fix: use environment configuration and session/customer identity.

## Recommended Next Work

1. Move the main API chat endpoint onto the safer local-prototype/orchestrator pattern.
2. Add UI diagnostics for grounding, injection containment, access tokens, tool
   permissions, and write-readback.
3. Replace hard-coded churn exchange rates with governed USD features.
4. Add Databricks staging manifests for resumable and auditable uploads.
5. Add frontend tests for diagnostic rendering and backend failure states.

## Final Verdict

The branch is merged, runnable, documented, and validated. The core policy and agent
safety modules are the strongest parts of the system. The main thing left is product
integration: make the visible FastAPI chatbot use the same strict guardrail path that
already exists in the repository.
