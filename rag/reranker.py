"""Reranker cross-encoder (BAAI/bge-reranker-v2-m3).

El retriever (bi-encoder) vectoriza pregunta y artículo por separado: es rápido pero compara
resúmenes. El cross-encoder lee pregunta y artículo *juntos* y puntúa su relevancia: es más
preciso pero caro, así que solo se aplica a los `retrieve_k` candidatos (20) y se quedan `top_k`.
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import TYPE_CHECKING

from rag.embeddings import load_local_first, pick_device

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

    from rag.retriever import RetrievedArticle

MAX_LENGTH = 1024  # los chunks están acotados a ~800 tokens


@lru_cache(maxsize=1)
def load_reranker(model_name: str) -> CrossEncoder:
    import torch
    from sentence_transformers import CrossEncoder

    device = pick_device()
    # float16 en GPU: en un Mac de 8 GB, float32 hace swap y tarda ~25 s por pregunta; float16
    # tarda ~3 s con el mismo top-5 (medido en docs/decisiones.md).
    dtype = torch.float16 if device in ("mps", "cuda") else torch.float32
    return load_local_first(
        CrossEncoder,
        model_name,
        device=device,
        max_length=MAX_LENGTH,
        model_kwargs={"torch_dtype": dtype},
    )


def passage_text(article: RetrievedArticle) -> str:
    """Mismo formato que se vectoriza: número de artículo y capítulo dan contexto al modelo."""
    if not article.articulo:
        return article.texto
    header = f"Artículo {article.articulo}"
    if article.capitulo:
        header += f" — {article.capitulo}"
    return f"{header}\n{article.texto}"


def rerank(
    queries: str | list[str], candidates: list[RetrievedArticle], model_name: str, k: int
) -> list[RetrievedArticle]:
    """Reordena candidatos por relevancia del cross-encoder y devuelve los k mejores.

    Con varias consultas (original + reescrita), cada candidato se queda con su mejor puntaje:
    basta con que sea relevante para una de las dos formulaciones.
    """
    if not candidates:
        return []
    queries = [queries] if isinstance(queries, str) else queries
    model = load_reranker(model_name)
    per_query = [
        model.predict([(query, passage_text(c)) for c in candidates], batch_size=8)
        for query in queries
    ]
    scores = [max(float(q_scores[i]) for q_scores in per_query) for i in range(len(candidates))]
    order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [
        replace(
            candidates[i],
            score=scores[i],
            ranks={**candidates[i].ranks, "candidato": i + 1, "rerank": new_rank},
        )
        for new_rank, i in enumerate(order[:k], start=1)
    ]
