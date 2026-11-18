import pytest

from eval.judge import parse_judgement
from eval.metrics import (
    aggregate,
    first_relevant_rank,
    hit_at_k,
    recall_at_k,
    reciprocal_rank,
    retrieval_metrics,
)
from ingest.chunking import chunks_fixed

UNITS = [["69"], ["76"], ["78"], ["80"], ["81"]]


def test_first_relevant_rank() -> None:
    assert first_relevant_rank(UNITS, ["76"]) == 2
    assert first_relevant_rank(UNITS, ["81", "76"]) == 2  # el primero que aparezca
    assert first_relevant_rank(UNITS, ["999"]) is None
    assert first_relevant_rank(UNITS, []) is None


def test_rank_with_multi_article_chunks() -> None:
    units = [["74", "75"], ["76", "77", "78"]]
    assert first_relevant_rank(units, ["78"]) == 2


def test_hit_and_reciprocal_rank() -> None:
    assert hit_at_k(1, 1) == 1.0
    assert hit_at_k(2, 1) == 0.0
    assert hit_at_k(5, 5) == 1.0
    assert hit_at_k(None, 5) == 0.0
    assert reciprocal_rank(2) == 0.5
    assert reciprocal_rank(None) == 0.0


def test_recall_at_k() -> None:
    assert recall_at_k(UNITS, ["76", "999"], 5) == 0.5
    assert recall_at_k(UNITS, ["76", "81"], 2) == 0.5
    assert recall_at_k(UNITS, [], 5) == 0.0


def test_retrieval_metrics_only_look_at_top_k() -> None:
    metrics = retrieval_metrics([["1"], ["2"], ["3"]], ["3"], k=2)
    assert metrics["rank"] is None
    assert metrics["hit@2"] == 0.0


def test_context_metrics_see_expanded_units() -> None:
    """Las referidas van después del top-k: Hit@5 no las ve, hit@ctx sí."""
    units = [["1"], ["2"], ["3"], ["4"], ["5"], ["74"]]
    metrics = retrieval_metrics(units, ["75", "74"], k=5)
    assert metrics["hit@5"] == 0.0
    assert metrics["hit@ctx"] == 1.0
    assert metrics["recall@ctx"] == 0.5


def _result(debe_responder: bool, abstencion: bool, rank: int | None, **extra) -> dict:
    return {
        "debe_responder": debe_responder,
        "abstencion": abstencion,
        "retrieval": {
            "hit@1": hit_at_k(rank, 1),
            "hit@5": hit_at_k(rank, 5),
            "rr": reciprocal_rank(rank),
            "recall@5": 1.0 if rank else 0.0,
        },
        "cita_valida_modelo": extra.get("cita_valida_modelo"),
        "cita_esperada": extra.get("cita_esperada", False),
        "fidelidad": extra.get("fidelidad"),
        "correccion": extra.get("correccion"),
        "latencias_ms": {"total": 1000},
        "tokens_contexto": 100,
    }


def test_aggregate_separates_answerable_and_out_of_scope() -> None:
    results = [
        _result(
            True, False, 1, cita_valida_modelo=True, cita_esperada=True, fidelidad=5, correccion=4
        ),
        _result(True, True, 2, correccion=1),
        _result(False, True, None),
        _result(False, False, None, cita_valida_modelo=False),
    ]
    m = aggregate(results, k=5)
    assert m["hit@1"] == 0.5  # solo cuenta preguntas respondibles
    assert m["hit@5"] == 1.0
    assert m["mrr"] == 0.75
    assert m["abstencion_correcta"] == 0.5
    assert m["falsa_abstencion"] == 0.5
    assert m["cita_valida"] == 0.5
    assert m["cita_esperada"] == 0.5
    assert m["fidelidad"] == 5  # solo sobre respuestas no abstenidas
    assert m["correccion"] == 2.5  # abstenerse en respondibles cuenta como 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"fidelidad": 5, "correccion": 4, "justificacion": "ok"}', (5, 4)),
        ('texto antes {"fidelidad": "3", "correccion": 2} después', (3, 2)),
        ('{"fidelidad": 9, "correccion": 0}', (None, None)),
        ("no es json", (None, None)),
    ],
)
def test_parse_judgement(raw: str, expected: tuple) -> None:
    result = parse_judgement(raw)
    assert (result["fidelidad"], result["correccion"]) == expected


def test_fixed_chunks_track_articles_and_overlap() -> None:
    def art(i: str, words: int, **kw) -> dict:
        base = {"articulo": i, "texto": "palabra " * words, "titulo": "T", "capitulo": "C"}
        return {**base, "derogado": False, "es_transitorio": False, "fecha_reforma": None, **kw}

    articles = [art("1", 300), art("2", 300), art("3", 10, derogado=True), art("4", 300)]
    chunks = chunks_fixed(articles, size=200, overlap=20)
    all_ids = {i for c in chunks for i in c.articulos_en_chunk}
    assert all_ids == {"1", "2", "4"}  # derogados fuera
    assert any(len(c.articulos_en_chunk) > 1 for c in chunks)  # ventanas que cruzan artículos
    assert chunks[0].texto.startswith("Artículo 1.-")
    assert all(c.with_header is False for c in chunks)
    assert all(c.articulo is None for c in chunks if len(c.articulos_en_chunk) > 1)
