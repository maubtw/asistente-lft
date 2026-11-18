from ingest.chunking import build_chunks, count_tokens, split_long_text
from rag.config import Settings
from rag.retriever import RetrievedArticle, dedupe_by_article


def _article(articulo: str, texto: str, **kwargs) -> dict:
    return {
        "articulo": articulo,
        "texto": texto,
        "titulo": "TÍTULO NOVENO Riesgos de Trabajo",
        "capitulo": None,
        "referencias": [],
        "derogado": False,
        "es_transitorio": False,
        "fecha_reforma": "2026-05-14",
        **kwargs,
    }


def test_short_article_is_one_chunk_with_context_header() -> None:
    [chunk] = build_chunks([_article("76", "Doce días.")], "by_article", max_tokens=800)
    assert chunk.articulo == "76"
    assert chunk.texto == "Doce días."
    assert chunk.embedding_text() == "Artículo 76 — TÍTULO NOVENO Riesgos de Trabajo\nDoce días."


def test_long_article_is_split_keeping_id() -> None:
    texto = "\n".join(f"Párrafo {i} " + "palabra " * 50 for i in range(40))
    chunks = build_chunks([_article("513", texto)], "by_article", max_tokens=200)
    assert len(chunks) > 1
    assert {c.articulo for c in chunks} == {"513"}
    assert all(count_tokens(c.texto) <= 200 for c in chunks)
    assert "\n".join(c.texto for c in chunks) == texto


def test_giant_paragraph_is_cut_by_tokens() -> None:
    parts = split_long_text("palabra " * 1000, max_tokens=100)
    assert len(parts) >= 10
    assert all(count_tokens(p) <= 100 for p in parts)


def test_derogated_and_transitory_are_not_embedded() -> None:
    chunks = build_chunks(
        [
            _article("15-A", "Se deroga.", derogado=True),
            _article("Transitorio 1 (1970)", "Esta Ley entrará en vigor...", es_transitorio=True),
            _article("76", "Doce días."),
        ],
        "by_article",
        max_tokens=800,
    )
    assert [c.embeddable for c in chunks] == [False, False, True]


def test_dedupe_keeps_best_chunk_per_article() -> None:
    def r(chunk_id: int, articulo: str, score: float) -> RetrievedArticle:
        return RetrievedArticle(chunk_id, articulo, None, None, "t", score)

    results = [r(1, "513", 0.9), r(2, "513", 0.8), r(3, "76", 0.7), r(4, "78", 0.6)]
    assert [a.articulo for a in dedupe_by_article(results, k=2)] == ["513", "76"]


def test_config_name_reflects_flags() -> None:
    base = Settings(_env_file=None)
    assert base.config_name == "by_article"
    assert base.model_copy(update={"use_hybrid": True}).config_name == "by_article+hybrid"
