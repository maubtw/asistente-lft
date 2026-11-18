"""Evalúa una configuración del pipeline sobre eval/preguntas.jsonl.

Uso:
    uv run python -m eval.run_eval --config by_article
    uv run python -m eval.run_eval --config fixed_chunks
    uv run python -m eval.run_eval --config current      # usa el .env tal cual
    uv run python -m eval.run_eval --config by_article --limit 5 --no-save   # prueba rápida
    uv run python -m eval.run_eval --config full --ids q13,q16,q30   # subconjunto (ahorra API)

Las reescrituras de consulta se cachean en eval/cache/rewrites.json (ver eval/rewrite_cache.py).

Guarda eval/results/<fecha>_<config>.json (nunca sobrescribe) e imprime la tabla markdown.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from eval.judge import JudgeFn, build_judge_messages, openai_judge, parse_judgement
from eval.metrics import aggregate, retrieval_metrics
from eval.report import markdown_table
from eval.rewrite_cache import CachedRewriter
from ingest.chunking import count_tokens
from rag.config import Settings, get_settings
from rag.db import connect, fetch_articles, latest_reform_date
from rag.embeddings import embed_texts
from rag.generator import (
    CompletionFn,
    build_messages,
    format_context,
    generate,
    normalize_citation,
    openai_completion,
)
from rag.modes import MODES
from rag.pipeline import ArticleStore, build_contract, db_fetch
from rag.query_rewrite import retrieval_queries
from rag.retriever import RetrievedArticle, retrieve

QUESTIONS = Path("eval/preguntas.jsonl")
RESULTS_DIR = Path("eval/results")

# Cada preset fija TODOS los flags, para que una corrida no dependa de lo que diga el .env.
BASE_FLAGS = {
    "chunking_strategy": "by_article",
    "rerank_query": "original",
    "use_hybrid": False,
    "use_reranker": False,
    "use_reference_expansion": False,
    "use_query_rewrite": False,
}
PRESETS: dict[str, dict] = {
    "by_article": {},
    "baseline": {},
    "fixed_chunks": {"chunking_strategy": "fixed_chunks"},
    "hybrid": {"use_hybrid": True},
    "rerank": {"use_reranker": True},
    "hybrid_rerank": {"use_hybrid": True, "use_reranker": True},
    "refs": {"use_reference_expansion": True},
    "hybrid_rerank_refs": {
        "use_hybrid": True,
        "use_reranker": True,
        "use_reference_expansion": True,
    },
    "refs_rewrite": {"use_reference_expansion": True, "use_query_rewrite": True},
    "full": {
        "use_hybrid": True,
        "use_reranker": True,
        "use_reference_expansion": True,
        "use_query_rewrite": True,
    },
    "full_rerank_max": {
        "use_hybrid": True,
        "use_reranker": True,
        "use_reference_expansion": True,
        "use_query_rewrite": True,
        "rerank_query": "max",
    },
    "full_rerank_rewrite": {
        "use_hybrid": True,
        "use_reranker": True,
        "use_reference_expansion": True,
        "use_query_rewrite": True,
        "rerank_query": "rewrite",
    },
}
# Los modos de la demo (rag/modes.py) también se pueden evaluar por nombre.
PRESETS.update({name: dict(flags) for name, flags in MODES.items()})


def settings_for(config: str) -> Settings:
    settings = get_settings()
    if config == "current":
        return settings
    if config not in PRESETS:
        raise SystemExit(f"Config desconocida '{config}'. Opciones: current, {', '.join(PRESETS)}")
    return settings.model_copy(update={**BASE_FLAGS, **PRESETS[config]})


def load_questions(path: Path, limit: int | None, ids: list[str] | None = None) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]
    if ids:
        missing = set(ids) - {q["id"] for q in questions}
        if missing:
            raise SystemExit(f"IDs inexistentes: {sorted(missing)}")
        questions = [q for q in questions if q["id"] in ids]
    return questions[:limit] if limit else questions


def reference_text(expected: list[str], settings: Settings) -> str:
    if not expected:
        return "(ninguno: la pregunta está fuera del alcance de la LFT)"
    with connect(settings.database_url) as conn:
        found = fetch_articles(conn, expected)
    return "\n\n".join(f"Art. {i}, LFT\n{found[i]['texto']}" for i in expected if i in found)


def raw_model_citations(raw: str) -> tuple[bool, list[str]]:
    """(¿el modelo respondió?, artículos que citó) leyendo el JSON crudo, antes de las reglas."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return False, []
    if not isinstance(data, dict) or data.get("estado") != "respondida":
        return False, []
    cited = [
        normalize_citation(str(c.get("articulo") or ""))
        for p in data.get("parrafos") or []
        for c in p.get("citas") or []
    ]
    return True, cited


def evaluate_question(
    question: dict,
    articles: list[RetrievedArticle],
    retrieval_ms: int,
    settings: Settings,
    fecha: str | None,
    complete: CompletionFn,
    judge: JudgeFn | None,
) -> dict:
    t0 = time.perf_counter()
    generated = generate(question["pregunta"], articles, settings, fecha, complete)
    generation_ms = round((time.perf_counter() - t0) * 1000)

    expected = question["articulos_esperados"]
    units = [a.article_ids for a in articles]
    context_ids = {i for unit in units for i in unit}
    raw_is_answer, raw_citations = raw_model_citations(generated.respuesta_modelo)
    # Mismos textos y validación que la API: un pasaje es verificable si es subcadena literal.
    _, checks = build_contract(
        generated.estructura, ArticleStore(db_fetch(settings), articles), fecha
    )

    judgement = {"fidelidad": None, "correccion": None, "justificacion": ""}
    if judge and question["debe_responder"]:
        if generated.abstencion:
            judgement = {"fidelidad": None, "correccion": 1, "justificacion": "Se abstuvo."}
        else:
            messages = build_judge_messages(
                question["pregunta"],
                format_context(articles),
                reference_text(expected, settings),
                generated.respuesta,
            )
            judgement = parse_judgement(judge(messages))

    return {
        "id": question["id"],
        "pregunta": question["pregunta"],
        "categoria": question["categoria"],
        "debe_responder": question["debe_responder"],
        "articulos_esperados": expected,
        "recuperados": units,
        "retrieval": retrieval_metrics(units, expected, settings.top_k),
        "respuesta": generated.respuesta,
        "respuesta_modelo": generated.respuesta_modelo,
        "citas": generated.citas,
        "citas_invalidas": generated.citas_invalidas,
        "abstencion": generated.abstencion,
        "cita_valida_modelo": any(c in context_ids for c in raw_citations)
        if raw_is_answer
        else None,
        "cita_esperada": bool(set(generated.citas) & set(expected)),
        "pasajes": [c["metodo"] for c in checks],
        "verificacion": checks,
        **judgement,
        "tokens_contexto": count_tokens(format_context(articles)),
        "tokens_prompt": count_tokens(
            "".join(m["content"] for m in build_messages(question["pregunta"], articles, fecha))
        ),
        "latencias_ms": {
            "recuperacion": retrieval_ms,
            "generacion": generation_ms,
            "total": retrieval_ms + generation_ms,
        },
    }


def run(
    config: str, limit: int | None, use_judge: bool, workers: int, ids: list[str] | None = None
) -> dict:
    settings = settings_for(config)
    questions = load_questions(QUESTIONS, limit, ids)
    rewriter = CachedRewriter(settings)
    with connect(settings.database_url) as conn:
        fecha = latest_reform_date(conn)

    # Precalentar el modelo para que su carga (~13 s) no cuente como latencia de la 1a pregunta.
    embed_texts(["precalentamiento"], settings.embedding_model)
    if settings.use_reranker:
        from rag.reranker import load_reranker

        load_reranker(settings.reranker_model)

    # 1) Recuperación secuencial (el modelo de embeddings vive en este proceso).
    retrieved: list[tuple[list[RetrievedArticle], int]] = []
    rewrites: dict[str, str | None] = {}
    for question in questions:
        t0 = time.perf_counter()
        queries = retrieval_queries(question["pregunta"], settings, rewriter)
        articles = retrieve(question["pregunta"], settings, queries=queries)
        retrieved.append((articles, round((time.perf_counter() - t0) * 1000)))
        rewrites[question["id"]] = queries[1] if len(queries) > 1 else None
        print(f"  recuperación {question['id']}: {[a.key for a in articles]}")

    if settings.use_query_rewrite:
        print(f"  reescrituras: {rewriter.hits} de caché, {rewriter.calls} llamadas a la API")

    # 2) Generación + juez en paralelo (llamadas a la API).
    complete = openai_completion(settings)
    judge = openai_judge(settings) if use_judge else None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(evaluate_question, q, arts, ms, settings, fecha, complete, judge)
            for q, (arts, ms) in zip(questions, retrieved, strict=True)
        ]
        results = [f.result() for f in futures]
    for result in results:
        result["consulta_reescrita"] = rewrites[result["id"]]

    return {
        "config": config,
        "config_flags": settings.config_name,
        # Corrida sobre un subconjunto de preguntas: sus métricas no son comparables con la tabla.
        "parcial": [q["id"] for q in questions] if (ids or limit) else None,
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "fecha_reforma_ley": fecha,
        "settings": settings.model_dump(exclude={"openai_api_key", "database_url"}),
        "juez": settings.judge_model if use_judge else None,
        "metricas": aggregate(results, settings.top_k),
        "preguntas": results,
    }


def save(result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now():%Y-%m-%d}_{result['config']}"
    if result.get("parcial"):
        stem += "_parcial"
    path = RESULTS_DIR / f"{stem}.json"
    n = 2
    while path.exists():  # nunca sobrescribir
        path = RESULTS_DIR / f"{stem}_{n}.json"
        n += 1
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa el pipeline RAG de la LFT.")
    parser.add_argument("--config", default="current")
    parser.add_argument("--limit", type=int, default=None, help="solo las primeras N preguntas")
    parser.add_argument("--no-judge", action="store_true", help="omite el LLM juez")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--no-save", action="store_true", help="no guarda el resultado (pruebas)")
    parser.add_argument(
        "--ids", type=lambda v: v.split(","), default=None, help="solo estas preguntas: q13,q16"
    )
    args = parser.parse_args()

    result = run(args.config, args.limit, not args.no_judge, args.workers, args.ids)
    if not args.no_save:
        print(f"\nGuardado en {save(result)}\n")
    print(markdown_table([result]))


if __name__ == "__main__":
    main()
