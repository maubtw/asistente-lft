import pytest

from rag.config import Settings
from rag.query_rewrite import (
    REWRITE_SYSTEM,
    build_rewrite_messages,
    clean_rewrite,
    retrieval_queries,
)

QUESTION = "Me corrieron sin darme ninguna razón, ¿qué puedo hacer?"


def test_prompt_has_no_examples_or_article_numbers() -> None:
    """El prompt no debe filtrar respuestas del set de evaluación."""
    assert "rescisi" not in REWRITE_SYSTEM.lower()
    assert not any(char.isdigit() for char in REWRITE_SYSTEM.replace("10 a 35", ""))
    messages = build_rewrite_messages(QUESTION)
    assert messages[1] == {"role": "user", "content": QUESTION}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "rescisión de la relación de trabajo sin causa justificada",
            "rescisión de la relación de trabajo sin causa justificada",
        ),
        (
            '"despido injustificado del trabajador"\n\nExplicación: ...',
            "despido injustificado del trabajador",
        ),
        ("Consulta: separación injustificada", "separación injustificada"),
        ("   \n  ", QUESTION),
    ],
)
def test_clean_rewrite(raw: str, expected: str) -> None:
    assert clean_rewrite(raw, QUESTION) == expected


def test_retrieval_queries_keeps_original_first() -> None:
    settings = Settings(_env_file=None, use_query_rewrite=True)
    queries = retrieval_queries(QUESTION, settings, complete=lambda _: "despido injustificado")
    assert queries == [QUESTION, "despido injustificado"]


def test_retrieval_queries_without_flag_skips_llm() -> None:
    def fail(_messages: list[dict]) -> str:
        raise AssertionError("no debe llamar al LLM")

    assert retrieval_queries(QUESTION, Settings(_env_file=None), complete=fail) == [QUESTION]


def test_identical_rewrite_is_not_duplicated() -> None:
    settings = Settings(_env_file=None, use_query_rewrite=True)
    assert retrieval_queries(QUESTION, settings, complete=lambda _: QUESTION) == [QUESTION]
