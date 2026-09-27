.PHONY: help setup ingest audit build train eval serve ui test lint check clean

PY ?= python

help:
	@echo "setup   - instala dependencias y hooks"
	@echo "ingest  - S3 -> data/bronze/*.parquet + manifest"
	@echo "audit   - perfil de calidad de las 13 tablas"
	@echo "build   - dbt: bronze -> silver -> gold"
	@echo "train   - baseline + PD + capacidad de pago -> MLflow"
	@echo "eval    - harness: baseline vs tools vs tools+SCM"
	@echo "serve   - API FastAPI en local"
	@echo "ui      - frontend Next.js en local"
	@echo "check   - lint + tests + gitleaks"

setup:
	$(PY) -m pip install -e ".[dev]"
	pre-commit install

ingest:
	$(PY) -m data_platform.ingestion.ingest_s3 --workers 16

summary:
	$(PY) -m data_platform.ingestion.summarize_manifest

ingest-light:
	$(PY) -m data_platform.ingestion.ingest_s3 --skip digital_events --workers 16

audit:
	$(PY) -m data_platform.contracts.audit

build:
	cd data_platform/dbt && dbt build --target duckdb

build-databricks:
	cd data_platform/dbt && dbt build --target databricks

train:
	$(PY) -m ml.training.run_all

eval:
	$(PY) -m eval.harness.run --systems baseline tools tools_scm

serve:
	uvicorn api.main:app --reload --port 8000

ui:
	cd ui && npm run dev

test:
	pytest

lint:
	ruff check .
	ruff format --check .

check: lint test
	gitleaks detect --no-banner --redact

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ data_platform/dbt/target
