.PHONY: setup db ingest pdf parse api web demo test lint eval

# Dependencias de Python y del frontend, y Postgres con pgvector
setup:
	uv sync
	npm --prefix web install
	docker compose up -d

db:
	docker compose up -d

# data/processed/lft.jsonl (ya incluido) → embeddings bge-m3 → Postgres. ~6 min la primera vez.
ingest: db
	uv run python -m ingest.embed

# Opcional: regenerar lft.jsonl desde el PDF oficial (la Cámara lo actualiza con cada reforma)
pdf:
	mkdir -p data/raw
	curl -fL -o data/raw/LFT.pdf https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf

parse:
	uv run python -m ingest.parse_ley
	uv run python -m ingest.verify

api:
	uv run uvicorn api.main:app --port 8000

web:
	npm --prefix web run dev

# API (8000) + web (3000). Ctrl+C detiene ambas.
demo: db
	@trap 'kill 0' EXIT; \
	uv run uvicorn api.main:app --port 8000 & \
	echo "Cargando modelos en la API (~30 s)..."; \
	until curl -sf http://localhost:8000/meta >/dev/null; do sleep 2; done; \
	echo "Abre http://localhost:3000 y pega tu clave de OpenAI en Ajustes."; \
	npm --prefix web run dev

test:
	uv run pytest
	cd web && npx tsc --noEmit && npm run lint

lint:
	uv run ruff check . && uv run ruff format --check .

# Evalúa una configuración. Usa OPENAI_API_KEY del .env y cuesta API (~80 llamadas).
# Ej.: make eval CONFIG=completo
eval:
	uv run python -m eval.run_eval --config $(or $(CONFIG),completo)
