# 26 · Deployment runbook

This project needs a public URL for the hackathon deliverable. The repository now has a
minimal deployment path for the current stack:

- Backend: FastAPI, deployable on Render from `render.yaml`.
- Frontend: Next.js, deployable on Vercel from the `ui/` directory.
- Health proof: `GET /health` must return `{"status":"ok"}`.

## Backend: Render

1. Push the repository branch that contains `render.yaml`.
2. In Render, create a Blueprint from the repository.
3. Configure the service environment variables:
   - `NOEMA_CORS_ORIGINS`: the final Vercel URL, for example `https://noema.vercel.app`.
   - `GOOGLE_API_KEY`: only if the LLM drafting path should call Gemini.
   - `NOEMA_ANALYTICS_DB`: keep `data/noema.duckdb` only if the file exists in the deployed artifact.
   - `NOEMA_LEDGER_DB`: `data/noema_ledger.duckdb`.
4. Deploy the service.
5. Verify:

```bash
curl -sS https://<render-service>.onrender.com/health
```

Expected response:

```json
{"status":"ok"}
```

## Frontend: Vercel

1. Import the same repository in Vercel.
2. Set the project root to `ui`.
3. Set `NEXT_PUBLIC_API_BASE_URL` to the Render backend URL, for example
   `https://<render-service>.onrender.com`.
4. Build command: `npm run build`.
5. Output is handled by Next.js.

## Current deployment caveat

This is deployable infrastructure, not proof that the hosted demo is production-safe. The API
still depends on local DuckDB/model artifacts for real customer data paths. If those files are not
packaged or mounted in the hosting platform, the deployed API will pass `/health` but customer
profile and model-backed flows will degrade or abstain.
