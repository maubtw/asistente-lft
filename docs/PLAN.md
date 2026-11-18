# Plan del proyecto

Cada fase termina con algo que funciona y se puede mostrar. No avanzar sin cumplir
el criterio de "Listo cuando".

## Fase 0 — Setup
- [x] `uv init`, dependencias en `pyproject.toml` (LLM: OpenAI)
- [x] `docker compose up -d` levanta Postgres con pgvector y ejecuta `sql/init.sql`
- [x] `.env` a partir de `.env.example`
- [x] Descargar `LFT.pdf` a `data/raw/`

**Listo cuando:** `psql` muestra la tabla `articulos` vacía y la extensión `vector` activa.

## Fase 1 — Parser de la ley
- [x] `ingest/parse_ley.py`: PDF → texto limpio (sin encabezados/pies de página)
- [x] Extraer fecha de última reforma
- [x] Dividir por artículo con jerarquía (título, capítulo)
- [x] Marcar derogados y transitorios
- [x] Detectar referencias cruzadas
- [x] Tests con encabezados difíciles (`1o.`, `39-A`, `3o. Bis`, `330-K`)
- [x] Script de verificación: cuántos artículos, cuáles faltan en la secuencia (`python -m ingest.verify`)

**Listo cuando:** `lft.jsonl` tiene todos los artículos del cuerpo principal, sin
huecos inexplicables en la numeración, y los tests pasan.

## Fase 2 — Pipeline básico de punta a punta
- [x] `ingest/embed.py`: embeddings con bge-m3 y carga a Postgres
- [x] `rag/retriever.py`: solo búsqueda vectorial, top-5
- [x] `rag/generator.py`: prompt con artículos numerados, citas obligatorias, abstención (OpenAI)
- [x] `rag/pipeline.py`: función `answer(question) -> {respuesta, citas, fecha_reforma}`
- [x] Probar desde CLI

**Listo cuando:** "¿Cuántos días de vacaciones me tocan en mi tercer año?" responde citando el Art. 76.

## Fase 3 — Evaluación (línea base)
- [x] Revisar `eval/preguntas.jsonl` contra el texto parseado y corregir artículos esperados
- [x] `eval/run_eval.py` con métricas:
  - Recuperación: Hit@1, Hit@5, MRR (sobre `articulos_esperados`)
  - Abstención: % de preguntas fuera de alcance correctamente rechazadas
  - Generación: fidelidad y corrección (LLM como juez, escala 1–5) y % de respuestas con cita válida
- [x] Guardar resultados en JSON + imprimir tabla markdown
- [x] Correr baseline: **chunking fijo de 500 tokens** vs **chunking por artículo**

**Listo cuando:** existe una tabla con ambas configuraciones y está documentada en `docs/decisiones.md`.

## Fase 4 — Mejoras medidas (una a la vez)
- [x] Búsqueda híbrida: vectorial + full-text `spanish`, fusión con RRF (medida: no mejora, queda off)
- [x] Reranker cross-encoder (recuperar 20, quedarse con 5) (mejor combinado con híbrida)
- [x] Expansión por referencias cruzadas (incluye "artículo anterior/siguiente")
- [x] Reescritura de consulta (lenguaje coloquial → términos de la ley)
- [x] Tras cada una: correr eval, guardar resultado, actualizar tabla

**Listo cuando:** la tabla del README muestra la progresión de métricas por mejora.

## Fase 5 — API y demo
- [x] FastAPI: `POST /ask`, `GET /articulo/{id}`, `GET /health`
- [x] Streamlit: chat, citas desplegables con el texto del artículo, fecha de reforma, aviso legal
- [x] Preguntas de ejemplo clicables en la demo
- [x] Mostrar latencia y artículos recuperados (modo "debug" opcional)

**Listo cuando:** alguien que no conoce el proyecto puede usar la demo sin instrucciones.

## Fase 6 — Deploy y presentación
- [ ] Deploy (Hugging Face Spaces / Railway / Render) con Postgres administrado (Neon/Supabase)
- [ ] README: GIF de la demo, diagrama de arquitectura, tabla de métricas, decisiones, cómo correrlo
- [ ] Post en LinkedIn contando qué mejoró cada técnica y por qué

## Extensiones (después)
- [ ] Agregar Ley del Seguro Social con filtro por ley
- [ ] Calculadoras deterministas (vacaciones, aguinaldo, finiquito) llamadas como herramientas
- [ ] Observabilidad con Langfuse (costo y latencia por consulta)
