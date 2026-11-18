"""Recuperación de artículos.

- Vectorial: coseno en pgvector (bge-m3).
- Léxica: full-text `spanish` de Postgres. La pregunta se convierte en lexemas (stems) y se buscan
  artículos que contengan *cualquiera* (OR). Como `ts_rank` no usa IDF, por defecto cada artículo
  se puntúa con la suma del IDF de los lexemas que contiene: "despid" pesa mucho más que "trabaj".
- Híbrida (USE_HYBRID): ambas listas se fusionan con Reciprocal Rank Fusion.
- Reranker (USE_RERANKER): cross-encoder sobre los `retrieve_k` candidatos.
- Expansión (USE_REFERENCE_EXPANSION): agrega, después del top-k, los artículos a los que remiten
  los recuperados ("artículo 47", "artículo anterior"), profundidad 1.

Las demás variantes de la Fase 4 se activan con flags de `rag/config.py`.
"""

from __future__ import annotations

import math
import time
from collections.abc import Generator
from dataclasses import dataclass, field, replace
from functools import lru_cache

import psycopg
from psycopg import sql

from rag.config import Settings
from rag.db import connect
from rag.embeddings import embed_texts

VECTOR_SQL = """
SELECT id, articulo, articulos_en_chunk, titulo, capitulo, texto, referencias, fecha_reforma,
       1 - (embedding <=> %(vec)s) AS score
FROM articulos
WHERE estrategia = %(strategy)s
  AND ley = 'LFT'
  AND NOT derogado
  AND NOT es_transitorio
  AND embedding IS NOT NULL
ORDER BY embedding <=> %(vec)s
LIMIT %(limit)s
"""


FILTERS = """
  a.estrategia = %(strategy)s
  AND a.ley = 'LFT'
  AND NOT a.derogado
  AND NOT a.es_transitorio
  AND a.embedding IS NOT NULL
"""

COLUMNS = """a.id, a.articulo, a.articulos_en_chunk, a.titulo, a.capitulo, a.texto, a.referencias,
       a.fecha_reforma"""

LEXEMES_SQL = "SELECT tsvector_to_array(to_tsvector('spanish', %(q)s)) AS lexemes"

DOC_FREQ_SQL = "SELECT word, ndoc FROM ts_stat(%(inner)s)"

LEXICAL_IDF_SQL = f"""
SELECT {COLUMNS}, sum(q.idf) AS score
FROM articulos a
JOIN unnest(%(lexemes)s::text[], %(idfs)s::float8[]) AS q(lexeme, idf)
  ON a.tsv @@ quote_literal(q.lexeme)::tsquery
WHERE {FILTERS}
GROUP BY a.id
ORDER BY score DESC, a.id
LIMIT %(limit)s
"""

LEXICAL_TS_RANK_SQL = f"""
SELECT {COLUMNS}, ts_rank(a.tsv, q.query, 1) AS score
FROM articulos a,
     (SELECT to_tsquery('simple', array_to_string(%(lexemes)s::text[], ' | ')) AS query) q
WHERE {FILTERS} AND a.tsv @@ q.query
ORDER BY score DESC, a.id
LIMIT %(limit)s
"""


REFERENCED_SQL = f"""
SELECT DISTINCT ON (a.articulo) {COLUMNS}, 1 - (a.embedding <=> %(vec)s) AS score
FROM articulos a
WHERE {FILTERS} AND a.articulo = ANY(%(ids)s)
ORDER BY a.articulo, a.embedding <=> %(vec)s
"""


@dataclass
class RetrievedArticle:
    chunk_id: int
    articulo: str | None
    titulo: str | None
    capitulo: str | None
    texto: str
    score: float
    referencias: list[str] = field(default_factory=list)
    fecha_reforma: str | None = None
    fuente: str = "vector"  # vector | lexical | hybrid | referencia
    articulos_en_chunk: list[str] = field(default_factory=list)
    ranks: dict[str, int | str] = field(default_factory=dict)  # posición en cada lista (debug)

    @property
    def article_ids(self) -> list[str]:
        """Artículos contenidos: uno con chunking por artículo, varios con chunks fijos."""
        if self.articulos_en_chunk:
            return self.articulos_en_chunk
        return [self.articulo] if self.articulo else []

    @property
    def key(self) -> str:
        """Identidad para deduplicar: el artículo, o el chunk si no pertenece a uno solo."""
        return self.articulo or f"chunk-{self.chunk_id}"


def _row_to_article(row: dict, fuente: str) -> RetrievedArticle:
    fecha = row["fecha_reforma"]
    return RetrievedArticle(
        chunk_id=row["id"],
        articulo=row["articulo"],
        titulo=row["titulo"],
        capitulo=row["capitulo"],
        texto=row["texto"],
        score=float(row["score"]),
        referencias=list(row["referencias"] or []),
        fecha_reforma=fecha.isoformat() if fecha else None,
        fuente=fuente,
        articulos_en_chunk=list(row.get("articulos_en_chunk") or []),
    )


def dedupe_by_article(results: list[RetrievedArticle], k: int) -> list[RetrievedArticle]:
    """Un artículo largo partido en chunks no debe ocupar varios lugares del top-k."""
    seen: set[str] = set()
    unique: list[RetrievedArticle] = []
    for result in results:
        if result.key in seen:
            continue
        seen.add(result.key)
        unique.append(result)
        if len(unique) == k:
            break
    return unique


def vector_search(
    conn: psycopg.Connection, question: str, settings: Settings, limit: int
) -> list[RetrievedArticle]:
    [vector] = embed_texts([question], settings.embedding_model)
    conn.execute(f"SET hnsw.ef_search = {int(settings.hnsw_ef_search)}")
    rows = conn.execute(
        VECTOR_SQL, {"vec": vector, "strategy": settings.chunking_strategy, "limit": limit}
    ).fetchall()
    return [_row_to_article(row, "vector") for row in rows]


def bm25_idf(n_docs: int, doc_freq: int) -> float:
    return math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)


@lru_cache(maxsize=4)
def _document_frequencies(database_url: str, strategy: str) -> tuple[dict[str, int], int]:
    """Frecuencia de documento de cada lexema (se calcula una vez por proceso)."""
    with connect(database_url) as conn:
        # ts_stat recibe la consulta como texto: el literal se escapa con psycopg.
        inner = FILTERS.replace("%(strategy)s", sql.Literal(strategy).as_string(conn))
        inner_query = f"SELECT a.tsv FROM articulos a WHERE {inner}"
        rows = conn.execute(DOC_FREQ_SQL, {"inner": inner_query}).fetchall()
        n_docs = conn.execute(
            f"SELECT count(*) AS n FROM articulos a WHERE {FILTERS}", {"strategy": strategy}
        ).fetchone()["n"]
    return {row["word"]: row["ndoc"] for row in rows}, n_docs


def query_lexemes(conn: psycopg.Connection, question: str) -> list[str]:
    row = conn.execute(LEXEMES_SQL, {"q": question}).fetchone()
    return list(row["lexemes"] or [])


def lexical_search(
    conn: psycopg.Connection, question: str, settings: Settings, limit: int
) -> list[RetrievedArticle]:
    doc_freq, n_docs = _document_frequencies(settings.database_url, settings.chunking_strategy)
    lexemes = [lex for lex in query_lexemes(conn, question) if lex in doc_freq]
    if not lexemes:
        return []
    params = {"lexemes": lexemes, "strategy": settings.chunking_strategy, "limit": limit}
    if settings.lexical_ranking == "ts_rank":
        rows = conn.execute(LEXICAL_TS_RANK_SQL, params).fetchall()
    else:
        params["idfs"] = [bm25_idf(n_docs, doc_freq[lex]) for lex in lexemes]
        rows = conn.execute(LEXICAL_IDF_SQL, params).fetchall()
    return [_row_to_article(row, "lexical") for row in rows]


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[RetrievedArticle]], rrf_k: int
) -> list[RetrievedArticle]:
    """RRF: score(d) = Σ 1 / (rrf_k + rango_i(d)). Solo usa posiciones, no scores, así que no
    hay que normalizar escalas distintas (coseno vs. suma de IDF).

    Un artículo largo está partido en chunks y cada lista puede haber elegido uno distinto: se
    conserva el chunk de la lista donde el artículo quedó mejor posicionado (es el que contiene el
    pasaje relevante; p. ej. la fracción de paternidad dentro del Art. 132).
    """
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    best: dict[str, tuple[int, RetrievedArticle]] = {}
    for source, results in ranked_lists.items():
        for rank, result in enumerate(results, start=1):
            scores[result.key] = scores.get(result.key, 0.0) + 1.0 / (rrf_k + rank)
            ranks.setdefault(result.key, {})[source] = rank
            if result.key not in best or rank < best[result.key][0]:
                best[result.key] = (rank, result)
    ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [
        replace(best[key][1], score=scores[key], fuente="hybrid", ranks=ranks[key])
        for key in ordered
    ]


def _check_flags(settings: Settings) -> None:
    """Todas las variantes de la Fase 4 están implementadas; se conserva como punto único para
    rechazar combinaciones inválidas."""
    if settings.use_reference_expansion and settings.chunking_strategy == "fixed_chunks":
        raise ValueError("La expansión de referencias requiere CHUNKING_STRATEGY=by_article")


def references_to_add(results: list[RetrievedArticle], limit: int) -> list[tuple[str, str]]:
    """(artículo referido, artículo que lo cita), en orden de rango y sin repetir lo recuperado."""
    present = {i for r in results for i in r.article_ids}
    picked: list[tuple[str, str]] = []
    for result in results:
        for ref in result.referencias:
            if ref not in present and ref not in {p for p, _ in picked}:
                picked.append((ref, result.articulo or ""))
            if len(picked) == limit:
                return picked
    return picked


def expand_references(
    conn: psycopg.Connection, question: str, results: list[RetrievedArticle], settings: Settings
) -> list[RetrievedArticle]:
    """Agrega al final los artículos referidos (sin derogados). De un artículo largo partido en
    chunks se toma el chunk más parecido a la pregunta."""
    wanted = references_to_add(results, settings.max_reference_articles)
    if not wanted:
        return results
    [vector] = embed_texts([question], settings.embedding_model)
    rows = conn.execute(
        REFERENCED_SQL,
        {"vec": vector, "strategy": settings.chunking_strategy, "ids": [w for w, _ in wanted]},
    ).fetchall()
    found = {row["articulo"]: _row_to_article(row, "referencia") for row in rows}
    extra = [
        replace(found[ref], ranks={"referido_por": cited_by})
        for ref, cited_by in wanted
        if ref in found
    ]
    return results + extra


def _source_name(kind: str, query_index: int) -> str:
    return kind if query_index == 0 else f"{kind}_reescrita"


def candidate_pool(
    question: str, settings: Settings, n: int, queries: list[str] | None = None
) -> list[RetrievedArticle]:
    """Los n mejores artículos para las consultas dadas.

    Una sola consulta y sin USE_HYBRID: búsqueda vectorial directa. Con varias consultas
    (reescritura) y/o híbrida: una lista por consulta y por tipo de búsqueda, fusionadas con RRF.
    """
    queries = queries or [question]
    with connect(settings.database_url) as conn:
        if len(queries) == 1 and not settings.use_hybrid:
            # Se piden más chunks para que la deduplicación por artículo no deje huecos.
            return dedupe_by_article(vector_search(conn, question, settings, n * 3), n)
        m = max(n, settings.retrieve_k)  # cada lista aporta al menos retrieve_k a la fusión
        ranked: dict[str, list[RetrievedArticle]] = {}
        for i, query in enumerate(queries):
            ranked[_source_name("vector", i)] = dedupe_by_article(
                vector_search(conn, query, settings, m * 3), m
            )
            if settings.use_hybrid:
                ranked[_source_name("lexical", i)] = dedupe_by_article(
                    lexical_search(conn, query, settings, m * 3), m
                )
    return reciprocal_rank_fusion(ranked, settings.rrf_k)[:n]


def rerank_queries(question: str, queries: list[str], settings: Settings) -> list[str]:
    """Consultas con las que puntúa el reranker (ver `Settings.rerank_query`)."""
    if len(queries) < 2 or settings.rerank_query == "original":
        return [question]
    if settings.rerank_query == "rewrite":
        return [queries[1]]
    return [question, queries[1]]  # "max"


def retrieve_steps(
    question: str,
    settings: Settings,
    k: int | None = None,
    queries: list[str] | None = None,
    timings: dict[str, int] | None = None,
) -> Generator[str, None, list[RetrievedArticle]]:
    """Igual que `retrieve`, pero emite el nombre de cada etapa *antes* de ejecutarla
    ("busqueda", "reranker", "referencias") y devuelve los resultados al terminar.

    Lo usa el streaming de la API para mostrar el avance: `results = yield from retrieve_steps(…)`.
    """
    _check_flags(settings)
    k = k or settings.top_k
    timings = {} if timings is None else timings
    if queries is None:
        from rag.query_rewrite import retrieval_queries

        queries = retrieval_queries(question, settings)

    yield "busqueda"
    t0 = time.perf_counter()
    if settings.use_reranker:
        from rag.reranker import rerank

        candidates = candidate_pool(question, settings, settings.retrieve_k, queries)
        timings["busqueda"] = _ms(t0, time.perf_counter())
        yield "reranker"
        t1 = time.perf_counter()
        results = rerank(
            rerank_queries(question, queries, settings),
            candidates,
            settings.reranker_model,
            k,
        )
        timings["reranker"] = _ms(t1, time.perf_counter())
    else:
        results = candidate_pool(question, settings, k, queries)
        timings["busqueda"] = _ms(t0, time.perf_counter())

    if not settings.use_reference_expansion:
        return results
    yield "referencias"
    t2 = time.perf_counter()
    with connect(settings.database_url) as conn:
        expanded = expand_references(conn, question, results, settings)
    timings["referencias"] = _ms(t2, time.perf_counter())
    return expanded


def retrieve(
    question: str,
    settings: Settings,
    k: int | None = None,
    queries: list[str] | None = None,
    timings: dict[str, int] | None = None,
) -> list[RetrievedArticle]:
    """Top-k artículos para la pregunta (sin derogados ni transitorios), más los referidos si
    USE_REFERENCE_EXPANSION (hasta `max_reference_articles`, al final de la lista).

    `queries`: consultas de búsqueda ya calculadas (p. ej. original + reescrita). Si no se pasan y
    USE_QUERY_REWRITE está activo, se reescribe aquí. El reranker y la expansión usan la
    pregunta original (la expansión siempre; el reranker salvo RERANK_QUERY=rewrite/max).
    `timings`: si se pasa, se llena con la latencia (ms) de cada etapa, para el modo debug.
    """
    steps = retrieve_steps(question, settings, k, queries, timings)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def _ms(start: float, end: float) -> int:
    return round((end - start) * 1000)
