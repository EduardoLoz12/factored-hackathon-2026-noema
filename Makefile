.PHONY: help setup ingest summary audit build train eval review checklist changelog worklog serve ui test lint check clean

PY ?= python
DBT ?= dbt

help:
	@echo "setup   - instala dependencias y hooks"
	@echo "ingest  - S3 -> data/bronze/*.parquet + manifest"
	@echo "audit   - perfil de calidad de las 13 tablas"
	@echo "build   - dbt: bronze -> silver -> gold"
	@echo "train   - baseline + PD + capacidad de pago -> MLflow"
	@echo "eval    - harness: baseline vs tools vs tools+SCM"
	@echo "review  - quien cambio que, si respeto su frontera, + checklist"
	@echo "checklist - estado de los 75 items del entregable, por dueno y por dia"
	@echo "changelog - control de cambios desde el historial de git"
	@echo "worklog   - bitacora de trabajo de hoy (logs/worklog/)"
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

build: audit
	cd data_platform/dbt && $(DBT) build --profiles-dir . --target duckdb --log-path ../../logs/build/dbt
	$(PY) -m data_platform.serving.export_local

build-databricks:
	cd data_platform/dbt && $(DBT) build --profiles-dir . --target databricks --log-path ../../logs/build/dbt

train:
	$(PY) -m ml.training.run_all

eval:
	$(PY) -m eval.harness.run --systems baseline tools tools_scm

serve:
	uvicorn api.main:app --reload --port 8000

ui:
	cd ui && npm run dev

review:
	$(PY) -m scripts.review_contributions
	$(PY) -m scripts.checklist
	$(PY) -m scripts.changelog

checklist:
	$(PY) -m scripts.checklist

changelog:
	$(PY) -m scripts.changelog

worklog:
	$(PY) -m scripts.worklog --list

test:
	pytest

lint:
	ruff check .
	ruff format --check .

check: lint test
	gitleaks detect --no-banner --redact

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ data_platform/dbt/target

train-capacity:
	$(PY) -m ml.training.capacity

.PHONY: train-interest
train-interest:
	$(PY) -m ml.training.product_interest

.PHONY: train-deep-interest
train-deep-interest:
	$(PY) -m ml.training.deep_interest

.PHONY: train-depth-experiment
train-depth-experiment:
	$(PY) -m ml.training.depth_experiment
