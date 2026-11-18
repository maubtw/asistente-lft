"""data/processed/lft.jsonl → embeddings bge-m3 → tabla `articulos` en Postgres.

Idempotente: borra las filas de la estrategia antes de insertarlas de nuevo.

Uso: uv run python -m ingest.embed [--strategy by_article] [--jsonl data/processed/lft.jsonl]
     uv run python -m ingest.embed --refs-only   # solo actualiza `referencias` (sin re-vectorizar)
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ingest.chunking import Chunk, build_chunks
from ingest.parse_ley import DEFAULT_OUT
from rag.config import get_settings
from rag.db import connect
from rag.embeddings import embed_texts

INSERT_SQL = """
INSERT INTO articulos (estrategia, ley, articulo, articulos_en_chunk, titulo, capitulo, texto,
                       referencias, derogado, es_transitorio, fecha_reforma, embedding)
VALUES (%s, 'LFT', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def embed_chunks(chunks: list[Chunk], model_name: str, batch_size: int) -> list[np.ndarray | None]:
    to_embed = [i for i, chunk in enumerate(chunks) if chunk.embeddable]
    vectors = embed_texts(
        [chunks[i].embedding_text() for i in to_embed], model_name, batch_size, show_progress=True
    )
    result: list[np.ndarray | None] = [None] * len(chunks)
    for i, vector in zip(to_embed, vectors, strict=True):
        result[i] = vector
    return result


def store_chunks(
    database_url: str, strategy: str, chunks: list[Chunk], vectors: list[np.ndarray | None]
) -> None:
    rows = [
        (
            strategy,
            chunk.articulo,
            chunk.articulos_en_chunk,
            chunk.titulo,
            chunk.capitulo,
            chunk.texto,
            chunk.referencias,
            chunk.derogado,
            chunk.es_transitorio,
            chunk.fecha_reforma,
            vector,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    with connect(database_url) as conn, conn.transaction():
        conn.execute("DELETE FROM articulos WHERE estrategia = %s", (strategy,))
        with conn.cursor() as cur:
            cur.executemany(INSERT_SQL, rows)


def update_references(database_url: str, articles: list[dict]) -> int:
    """Actualiza `referencias` de todas las filas de cada artículo (no toca los embeddings)."""
    rows = [(a["referencias"], a["articulo"]) for a in articles if not a["es_transitorio"]]
    with connect(database_url) as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            "UPDATE articulos SET referencias = %s WHERE articulo = %s AND NOT es_transitorio",
            rows,
        )
    return len(rows)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Carga embeddings de la LFT a Postgres.")
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--strategy", default=settings.chunking_strategy)
    parser.add_argument("--refs-only", action="store_true", help="solo actualiza referencias")
    args = parser.parse_args()

    articles = load_jsonl(args.jsonl)
    if args.refs_only:
        n = update_references(settings.database_url, articles)
        print(f"Referencias actualizadas para {n} artículos")
        return
    chunks = build_chunks(articles, args.strategy, settings.max_chunk_tokens)
    n_embed = sum(c.embeddable for c in chunks)
    print(f"{len(articles)} artículos → {len(chunks)} chunks ({n_embed} con embedding)")

    start = time.perf_counter()
    vectors = embed_chunks(chunks, settings.embedding_model, settings.embedding_batch_size)
    print(f"Embeddings en {time.perf_counter() - start:.1f}s")

    store_chunks(settings.database_url, args.strategy, chunks, vectors)
    print(f"Guardados {len(chunks)} registros con estrategia '{args.strategy}'")


if __name__ == "__main__":
    main()
