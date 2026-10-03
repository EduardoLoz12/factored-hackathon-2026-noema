# Bot Interaction Accuracy Report

Date: 2026-10-02

Scope: recent local evidence for the chatbot and prototype behavior.

## Bottom Line

The chatbot was hallucination-prone because the main FastAPI path used the LLM as
the default answer path for ordinary banking questions.

That has now been changed.

The bot now fails closed:

- sensitive account facts require demo identity verification first;
- the UI starts each refresh with identity unknown and asks the user to identify themselves;
- balance questions answer from DuckDB customer data;
- product questions answer from the versioned policy catalog;
- capability questions list only implemented actions;
- recommendation questions produce a bounded, profile-grounded next-step suggestion;
- credit eligibility questions abstain unless verified policy inputs are evaluated;
- unknown questions abstain instead of guessing;
- the LLM provider is bypassed unless a future verified path explicitly enables it.

This makes the bot less conversational, but materially more accurate.

## Evidence Available

Recent interactions are now logged locally at:

```text
logs/traces/chat_interactions.jsonl
```

Each log row contains:

- user message;
- assistant response;
- action taken;
- escalation flag;
- visible step-by-step logic trace;
- Databricks target tables;
- `private_reasoning_logged=false`.

The log contains the visible procedural trace, not hidden/private reasoning.

## Actual Customer Data Used By The UI Demo

The UI no longer starts with a hard-coded visible customer identity. It starts
without a customer ID, asks the user to state their full name, and the backend
looks up the matching row in `noema_gold.customer_360`.

After a successful match, the backend returns the verified `customer_id`,
display name, and segment. The UI then uses that customer ID for follow-up
account questions in the current page session.

Blunt assessment:

- The UI now selects the local demo customer by typed full name.
- This is still not a real authenticated bank session.
- If duplicate full names exist, the current prototype uses the first exact match.
- The verification is a demo identity check, not real bank authentication.
- Verification is intentionally not persisted in browser storage; a page refresh
  resets identity to unknown.

## Current FastAPI Chatbot Smoke Tests

I tested the current `/api/chat` endpoint directly.

### Balance Question

Prompt:

```text
What is my balance?
```

Observed response before identity verification:

```text
I need to verify the demo identity before showing account balances. Type: my name is <your full name>.
```

Observed response after identity verification:

```text
For Elena, the recorded total balance is $6,959.74 USD. This comes from the local DuckDB customer_360 table.
```

Assessment:

- This is grounded in local DuckDB data.
- The bot no longer calls Gemini for this fact.
- This is gated behind demo identity verification.
- This is accurate for the hard-coded UI demo customer.

### Identity Verification

Prompt:

```text
my name is Sandra Suárez Moreno
```

Observed response:

```text
Demo identity verified for Sandra Suárez Moreno. You can now ask for account facts available in this local demo.
```

Verified customer ID:

```text
CLI-ZC5L8UWRLUX3
```

Prompt:

```text
my name is Not A Real Person
```

Observed response:

```text
I cannot verify the name 'Not A Real Person'. Please check the full name and try again.
```

Assessment:

- The app can now verify demo identity against the loaded local customer profile.
- This is not real bank authentication. It is a local demo identity check.

### Capability Question

Prompt:

```text
What can you do?
```

Observed response after identity verification:

```text
I can currently do these grounded actions: verify a demo identity by full name; show the recorded account balance after verification; list the versioned product catalog; explain that credit eligibility requires deterministic policy evaluation; trigger human escalation when you ask for a person or show frustration; and show the visible policy/guardrail trace in the UI.
```

Assessment:

- This is deterministic.
- It lists implemented behavior instead of pretending the assistant is complete.

### Recommendation Question

Prompt:

```text
Great, what do you recommend for my account?
```

Observed response after identity verification:

```text
Based on the verified local profile I can see segment=Plus and recorded balance=$2,609.98 USD. The current policy catalog contains: Tarjeta Crédito, Préstamo Personal, Préstamo Hipotecario.
```

Assessment:

- This is grounded in `noema_gold.customer_360` and the policy catalog.
- It is not a credit approval.
- It recommends a safe next step: ask for product catalog or policy eligibility check.

### Product Catalog Question

Prompt:

```text
What products do you have?
```

Observed response:

```text
The versioned policy catalog contains these products: Tarjeta Crédito, Préstamo Personal, Préstamo Hipotecario. These are not offers until the policy engine evaluates verified customer facts.
```

Assessment:

- This is grounded in the deterministic policy catalog.
- It correctly avoids turning catalog products into personalized offers.

### Credit Eligibility Question

Prompt:

```text
Am I eligible for a loan?
```

Observed response:

```text
I will not decide credit eligibility from chat text. The deterministic policy engine must evaluate verified income, obligations, capacity, and product terms first.
```

Assessment:

- This is correct.
- The bot no longer pretends to approve or deny credit from a chat message.

### Unknown Account Question

Prompt:

```text
Tell me something random about my account
```

Observed response:

```text
I do not have a grounded tool-backed answer for that request yet. I will not guess or invent banking information.
```

Assessment:

- This is correct.
- The bot abstains instead of hallucinating.

### Human Escalation Request

Prompt:

```text
I need a human please
```

Observed response:

```text
I am transferring you to a human expert who can better assist you right away.
```

Assessment:

- This behavior is correct for the demo.
- It is deterministic and does not require Gemini.
- It does not actually connect to a human queue. It only returns an escalation
  response.

## Stored Prototype Interactions

The local prototype database exists:

```text
data/prototype/demo.sqlite
```

Stored state:

- `4` demo sessions;
- `1` completed transfer action;
- `1` ledger entry;
- `0` cases.

The completed action:

| Field | Value |
|---|---|
| kind | transfer |
| amount | 100.00 USD |
| status | done |
| read-back balance | 2,350.75 USD |
| source | demo_ledger_readback |

Assessment:

- This prototype behavior is accurate within its demo limits.
- It clearly marks the action as simulated.
- It verifies the write by reading back state.
- It does not represent a real bank transfer.

## Serious Issue Found And Fixed

The API previously returned raw provider exception text to the user when Gemini DNS
resolution failed.

That raw exception included the provider request URL. Because the API key was placed
in the query string, this could expose the key in the chatbot response.

Fix applied:

- `api/main.py` now logs only the exception type;
- the user receives a generic provider-unavailable message if that path is ever used;
- the API key is no longer returned to the user in this error path.

Blunt assessment:

- This was a serious security bug.
- It is now patched for this failure path.
- The better long-term design is still to avoid provider keys in URLs.

## Accuracy Assessment

### Accurate Now

- Balance answers come from DuckDB customer facts.
- Balance answers require demo identity verification first.
- Refreshing the app resets identity to unknown.
- The Verify identity control now inserts the expected identity-claim format and focuses the chat input.
- Capability and recommendation questions now have deterministic non-LLM answers.
- Product catalog answers come from the policy catalog.
- Credit eligibility abstains instead of hallucinating.
- Unknown requests abstain instead of hallucinating.
- Human escalation by obvious keyword works.
- The visible trace shows when the LLM provider is bypassed.
- The interaction log records the visible logic process.
- Prototype simulated transfer behavior is internally accurate and read-back verified.

### Still Weak Or Misleading

- The UI still uses a hard-coded customer ID.
- Unknown customer IDs need a clearer `customer_not_found` UX.
- Policy diagnostics are still global health checks, not a customer-specific approval.
- The main API still does not use the stronger local prototype flow for transactions,
  transfer confirmation, card blocking, or local case creation.
- The grounding verifier is still marked pending in the main API.
- Databricks integration is still a local log/schema shape, not a live cloud write.
- Multilingual escalation is still keyword-based and incomplete.

## Behavior By Capability

| Capability | Current status | Direct verdict |
|---|---|---|
| Demo identity verification | Matches typed name to local profile | Works for demo |
| Balance question | Answers from DuckDB after identity check | Reliable for demo customer |
| Product catalog question | Answers from policy catalog | Reliable as catalog, not offer |
| Capability question | Lists implemented actions | Reliable |
| Recommendation question | Summarizes verified facts and safe next steps | Bounded, not approval |
| Loan eligibility question | Abstains | Correct until policy inputs are wired |
| Unknown account question | Abstains | Correct fail-closed behavior |
| Human escalation | Works for obvious trigger words | Mostly reliable for demo |
| Spanish escalation | Partial only | Not robust |
| Customer data grounding | Balance uses DuckDB directly | Improved |
| Unknown customer handling | Needs clearer UX | Weak |
| Policy diagnostics | Works | Reliable as global checks |
| Live trace UI | Works visually | Useful, but not full proof |
| Logs | JSONL now exists | Useful for audit and Databricks ingestion |
| Databricks integration | Schema/log shape only | Not integrated |
| Prototype transfer | Works as simulated flow | Accurate within demo limits |

## Direct Conclusion

The bot should no longer hallucinate through the main response path for normal
banking questions. It now gives deterministic answers where it has grounded data and
abstains where it does not.

It is accurate to present it as:

- a local demo shell;
- a visual audit-trace prototype;
- a deterministic policy diagnostics viewer;
- a deterministic balance/catalog responder for the hard-coded demo customer;
- a proof that safer prototype flows exist in the repo.

It is not accurate to present it as:

- a complete customer-service agent;
- a Databricks-integrated live agent;
- a complete grounded banking assistant;
- a production-ready chatbot;
- a real credit advisor.

## Required Fixes Before Strong Demo Claims

1. Replace demo identity matching with real authentication for any production claim.
2. Return a clear `customer_not_found` state when the customer ID is absent.
3. Attach the grounding verifier before enabling generated answers again.
4. Make policy trace request-specific, not only global diagnostics.
5. Replace the hard-coded UI customer ID with session/customer selection.
6. Add Databricks event export for the trace schema.
7. Stop relying on keyword substring matching for multilingual escalation.
8. Promote the safer local prototype tools into the main API.

## Final Verdict

The hallucination issue was real. The main cause was the free-form LLM default path.
That path has been disabled for the visible banking responses.

The bot is safer now. It is also narrower. That is the right tradeoff for this
project.
