import pytest

from rag.config import Settings
from rag.retriever import (
    RetrievedArticle,
    _check_flags,
    bm25_idf,
    reciprocal_rank_fusion,
    references_to_add,
    rerank_queries,
)


def _r(articulo: str, score: float = 0.0, chunk_id: int = 0) -> RetrievedArticle:
    return RetrievedArticle(chunk_id, articulo, None, None, "t", score)


def test_rrf_rewards_agreement_between_lists() -> None:
    fused = reciprocal_rank_fusion(
        {"vector": [_r("76"), _r("78"), _r("80")], "lexical": [_r("78"), _r("99")]}, rrf_k=60
    )
    assert [a.articulo for a in fused] == ["78", "76", "99", "80"]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[0].ranks == {"vector": 2, "lexical": 1}
    assert fused[0].fuente == "hybrid"


def test_rrf_ignores_raw_scores() -> None:
    """Coseno (~0.6) y suma de IDF (~15) tienen escalas distintas: RRF solo usa posiciones."""
    fused = reciprocal_rank_fusion(
        {"vector": [_r("1", 0.61)], "lexical": [_r("2", 15.0)]}, rrf_k=60
    )
    assert fused[0].score == fused[1].score


def test_rrf_keeps_chunk_from_best_ranked_list() -> None:
    """Art. 132 partido en chunks: la léxica halla el de paternidad (155) en 3er lugar y la
    vectorial otro chunk (156) en 9o. Al LLM debe llegar el 155."""
    vector = [_r(str(i)) for i in range(8)] + [_r("132", chunk_id=156)]
    lexical = [_r("a"), _r("b"), _r("132", chunk_id=155)]
    fused = reciprocal_rank_fusion({"vector": vector, "lexical": lexical}, rrf_k=60)
    [art132] = [a for a in fused if a.articulo == "132"]
    assert art132.chunk_id == 155


def test_rrf_handles_empty_list() -> None:
    fused = reciprocal_rank_fusion({"vector": [_r("1")], "lexical": []}, rrf_k=60)
    assert [a.articulo for a in fused] == ["1"]


def test_idf_penalizes_common_terms() -> None:
    # "trabaj" aparece en 861 de 1,274 chunks; "despid" en muy pocos
    assert bm25_idf(1274, 861) < bm25_idf(1274, 20) < bm25_idf(1274, 1)
    assert bm25_idf(1274, 861) > 0


def test_flag_combinations() -> None:
    every_flag = {
        "use_hybrid": True,
        "use_reranker": True,
        "use_reference_expansion": True,
        "use_query_rewrite": True,
    }
    _check_flags(Settings(_env_file=None, **every_flag))  # todas implementadas
    with pytest.raises(ValueError, match="by_article"):
        _check_flags(
            Settings(_env_file=None, chunking_strategy="fixed_chunks", use_reference_expansion=True)
        )


def test_passage_text_includes_article_and_chapter() -> None:
    from rag.reranker import passage_text

    article = RetrievedArticle(1, "76", "TÍTULO TERCERO", "CAPÍTULO IV Vacaciones", "Doce días.", 0)
    assert passage_text(article) == "Artículo 76 — CAPÍTULO IV Vacaciones\nDoce días."
    fragment = RetrievedArticle(2, None, None, None, "Artículo 75.- ...", 0)
    assert passage_text(fragment) == "Artículo 75.- ..."


def test_rerank_orders_by_cross_encoder_score(monkeypatch: pytest.MonkeyPatch) -> None:
    from rag import reranker

    class FakeModel:
        def predict(self, pairs, batch_size):
            return [len(passage) for _, passage in pairs]  # el pasaje más largo gana

    monkeypatch.setattr(reranker, "load_reranker", lambda name: FakeModel())
    candidates = [
        RetrievedArticle(1, "1", None, None, "corto", 0.9),
        RetrievedArticle(2, "2", None, None, "texto bastante más largo", 0.5),
        RetrievedArticle(3, "3", None, None, "medio largo", 0.7),
    ]
    result = reranker.rerank("¿?", candidates, "fake", k=2)
    assert [a.articulo for a in result] == ["2", "3"]
    assert result[0].ranks == {"candidato": 2, "rerank": 1}


def _with_refs(articulo: str, refs: list[str]) -> RetrievedArticle:
    return RetrievedArticle(0, articulo, None, None, "t", 0.0, referencias=refs)


def test_references_to_add_in_rank_order_without_duplicates() -> None:
    results = [
        _with_refs("291-M", ["47", "291-P"]),
        _with_refs("75", ["74"]),
        _with_refs("47", ["43"]),  # 47 ya recuperado: no se vuelve a agregar
    ]
    assert references_to_add(results, limit=3) == [("291-P", "291-M"), ("74", "75"), ("43", "47")]


def test_references_to_add_respects_limit() -> None:
    results = [_with_refs("50", ["49", "48", "291-D"]), _with_refs("52", ["51"])]
    assert references_to_add(results, limit=2) == [("49", "50"), ("48", "50")]


def test_rerank_query_selection() -> None:
    queries = ["¿tope de PTU?", "límite de la participación de los trabajadores en las utilidades"]

    def settings(mode: str) -> Settings:
        return Settings(_env_file=None, use_query_rewrite=True, rerank_query=mode)

    assert rerank_queries("¿tope de PTU?", queries, settings("original")) == queries[:1]
    assert rerank_queries("¿tope de PTU?", queries, settings("rewrite")) == queries[1:]
    assert rerank_queries("¿tope de PTU?", queries, settings("max")) == queries
    assert rerank_queries("¿tope de PTU?", queries[:1], settings("max")) == queries[:1]


def test_rerank_max_keeps_best_score_per_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    from rag import reranker

    class FakeModel:
        def predict(self, pairs, batch_size):
            # la consulta "a" favorece al artículo 1; la "b" al 2
            return [1.0 if (q == "a") == p.endswith("uno") else 0.1 for q, p in pairs]

    monkeypatch.setattr(reranker, "load_reranker", lambda name: FakeModel())
    candidates = [
        RetrievedArticle(1, "1", None, None, "uno", 0),
        RetrievedArticle(2, "2", None, None, "dos", 0),
        RetrievedArticle(3, "3", None, None, "tres", 0),
    ]
    result = reranker.rerank(["a", "b"], candidates, "fake", k=3)
    assert {a.articulo for a in result[:2]} == {"1", "2"}
    assert result[2].articulo == "3"
