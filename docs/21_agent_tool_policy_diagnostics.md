# Agent Tool and Policy Diagnostics

2 October 2026 · Local diagnostics after merging latest `origin/main`.

## What Was Added

Two validation layers were added so the chatbot UI can show whether the policy
engine is behaving correctly.

1. Backend endpoint:

```text
GET /api/policy-diagnostics
```

Implemented in:

```text
api/main.py
```

2. Chatbot UI diagnostics panel:

```text
ui/src/app/page.tsx
```

The panel appears beside the chat. Press **Run** to call the backend and display
policy version, overall status, and each validation check.

While adding the endpoint, `api/main.py` was also cleaned up so the customer lookup
uses a parameterized DuckDB query instead of interpolating `customer_id` into SQL.

## What the Backend Checks

The endpoint runs live scenarios through the real deterministic policy engine:

```python
Politica.cargar().evaluar(cliente)
```

It does not use the LLM. It does not call Gemini. It does not rely on mocked
frontend state.

Current checks:

| Check | Expected behavior |
|---|---|
| Eligible verified customer receives at least one policy offer | `elegible=true`, `abstencion=false`, offers > 0 |
| Missing income produces abstention | policy must abstain instead of inventing income |
| Incomplete current debt terms produce abstention | existing obligation without limit/rate blocks evaluation |
| Missing observed capacity restricts mortgage offers | mortgage is not offered when recent flow capacity was not observed |

These checks cover the most important policy failure modes found earlier:

- missing data cannot silently become zero;
- missing data cannot silently become full margin;
- incomplete obligations cannot be skipped;
- the policy, not the LLM, decides eligibility.

## Smoke-Test Result

Command:

```bash
.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from api.main import app
payload = TestClient(app).get('/api/policy-diagnostics').json()
print(payload['status'], payload['policy_version'], len(payload['checks']))
for check in payload['checks']:
    print(check['passed'], check['name'], '|', check['observed'])
PY
```

Result:

```text
pass 3 4
True Eligible verified customer receives at least one policy offer | elegible=True, abstencion=False, offers=1
True Missing income produces abstention | abstencion=True, elegible=False
True Incomplete current debt terms produce abstention | abstencion=True, motivos=1
True Missing observed capacity restricts mortgage offers | offers=Tarjeta Crédito
```

Policy version:

```text
3
```

## Agent Tool Diagnostic Suite

Command:

```bash
.venv/bin/python -m pytest tests/tools tests/core tests/policies tests/guardrails tests/cognition
```

Result:

```text
875 passed in 17.91s
```

Coverage by folder:

| Folder | What it validates |
|---|---|
| `tests/tools` | registry permissions, customer tools, credit tools, write/read-back |
| `tests/core` | access guard, orchestrator, verifier, handoff |
| `tests/policies` | deterministic policy, formatting, facts, terms, missing capacity |
| `tests/guardrails` | grounding and injection containment |
| `tests/cognition` | SCM contract and contradiction/missing-evidence behavior |

## UI Validation

Command:

```bash
cd ui
npm run lint
```

Result:

```text
passed with no reported lint errors
```

## API Lint Validation

Command:

```bash
.venv/bin/ruff check api/main.py
```

Result:

```text
All checks passed!
```

The UI now displays:

- chat conversation;
- live agent logic trace;
- achieved, not achieved, and pending counters;
- rule, observed behavior, evidence, and Databricks target for each step;
- policy diagnostic status;
- policy version;
- each policy check;
- expected result;
- observed backend result;
- pass/fail indicator.

## Live Agent Logic Panel

The chatbot now uses a two-column validation layout:

- the chatbot conversation stays on the left;
- the live agent logic trace stays on the right;
- every chatbot response can refresh the right-side trace;
- every trace step is rendered as visible bullets.

Each trace step has one of three statuses:

- `achieved`: the rule or safeguard passed;
- `not_achieved`: the rule did not pass, or the action was not triggered;
- `pending`: the rule is intentionally visible but not fully integrated yet.

The current live checks include:

- **Step 1 · Input**: capture the user request;
- **Step 2 · Session**: check the identity boundary;
- **Step 3 · Data**: load customer facts from DuckDB;
- **Step 4 · Cognition**: route the request intent;
- **Step 5 · Safeguard**: apply deterministic escalation rules;
- **Step 6 · Model**: apply the support-escalation model;
- **Step 7 · Policy**: check deterministic credit policy diagnostics;
- **Step 8 · LLM**: check whether the provider was called, bypassed, failed, or
  completed;
- **Step 9 · Verifier**: show whether grounded-response verification is attached;
- **Step 10 · Decision**: select the final action;
- **Step 11 · Observability**: prepare the Databricks trace event.

The panel is intentionally blunt. If a provider call fails, the LLM step is shown as
`not_achieved`. If deterministic escalation handles the turn, the provider step is
shown as `pending` because the LLM was deliberately bypassed.

## Databricks Integration Shape

The `/api/chat` response now includes a structured `trace` array. Each item has:

```json
{
  "step": 7,
  "layer": "Policy",
  "phase": "policy",
  "status": "achieved",
  "title": "Credit policy diagnostics available",
  "detail": "4 of 4 policy checks passed.",
  "policy": "Eligibility is deterministic policy logic, not an LLM decision.",
  "evidence": "policy_version=3; status=pass",
  "databricks_target": "gold.policy_diagnostics"
}
```

This is intentionally Databricks-friendly. The same fields can later be written as
rows into:

- `bronze.agent_events` for raw UI/backend events;
- `silver.agent_identity_checks` for identity and session decisions;
- `silver.agent_intent_trace` for routing decisions;
- `gold.policy_diagnostics` for policy validation;
- `gold.grounding_audit` for grounded-response validation;
- `gold.escalation_audit` for human-handoff decisions.

No Databricks write happens from the chatbot UI today. The UI shows target table
names so reviewers can visually validate the intended integration path before cloud
credentials are connected.

## Local Interaction Logs

Every `/api/chat` call now appends a JSONL record to:

```text
logs/traces/chat_interactions.jsonl
```

Each record contains:

- `trace_id`;
- UTC timestamp;
- customer ID;
- channel metadata;
- user message;
- assistant response;
- final action;
- escalation flag;
- `visible_logic_trace`;
- Databricks target tables;
- `private_reasoning_logged=false`.

The log intentionally records the visible procedural trace, not private hidden
reasoning. The `visible_logic_trace` field is the auditable step-by-step logic shown
in the UI: input, identity boundary, data lookup, routing, safeguards, policy,
provider, verifier, final action, and observability.

This file is the local precursor to a Databricks `bronze.agent_events` ingestion.
Each JSONL row can be loaded as one raw event, while the nested `visible_logic_trace`
array can be exploded later into silver/gold audit tables.

## How to Run Locally

Start the API:

```bash
.venv/bin/python -m uvicorn api.main:app --reload --port 8000
```

Start the UI:

```bash
cd ui
npm run dev
```

Open:

```text
http://localhost:3000
```

Click **Run** in the Policy Diagnostics panel.

## Known Limitations

The diagnostics validate the policy engine and major safety assumptions, not the
entire live banking stack.

They do not prove:

- that Gemini or another LLM provider is configured;
- that Databricks upload is complete;
- that a real bank core integration exists.

They do prove that the local backend can call the real policy engine and that the
UI can show the outcome of those checks.
