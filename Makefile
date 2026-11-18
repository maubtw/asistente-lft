.PHONY: setup db ingest api app demo test lint eval

# Instala dependencias y levanta Postgres
setup:
	uv sync
	docker compose up -d

db:
	docker compose up -d

# PDF → JSONL → embeddings en Postgres (~6 min la primera vez)
ingest:
	uv run python -m ingest.parse_ley
	uv run python -m ingest.embed

api:
	uv run uvicorn api.main:app --port 8000

app:
	uv run streamlit run app/streamlit_app.py

# API en segundo plano + demo; Ctrl+C detiene ambas
demo: db
	@trap 'kill 0' EXIT; \
	uv run uvicorn api.main:app --port 8000 & \
	echo "Cargando modelos en la API (~30 s)..."; \
	until curl -sf http://localhost:8000/health >/dev/null; do sleep 2; done; \
	uv run streamlit run app/streamlit_app.py

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

# Evalúa una configuración (cuesta API). Ej.: make eval CONFIG=completo
eval:
	uv run python -m eval.run_eval --config $(or $(CONFIG),current)
