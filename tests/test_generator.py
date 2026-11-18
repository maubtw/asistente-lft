"""Generador con salida estructurada, sin llamar a la API."""

import json

import pytest

from rag.config import Settings
from rag.generator import (
    ANSWER_SCHEMA,
    SYSTEM_PROMPT,
    apply_structured_rules,
    build_messages,
    extract_citations,
    format_context,
    generate,
    normalize_citation,
    parse_answer,
    parse_partial,
)
from rag.retriever import RetrievedArticle

SETTINGS = Settings(_env_file=None)


def _article(articulo: str, texto: str = "texto", chunk_id: int = 1) -> RetrievedArticle:
    return RetrievedArticle(
        chunk_id=chunk_id,
        articulo=articulo,
        titulo="TÍTULO TERCERO Condiciones de Trabajo",
        capitulo="CAPÍTULO IV Vacaciones",
        texto=texto,
        score=0.8,
    )


def _answer(**overrides) -> dict:
    data = {
        "estado": "respondida",
        "frase_principal": "Te corresponden 16 días de vacaciones.",
        "parrafos": [
            {
                "texto": "La ley parte de 12 días y suma 2 por año.",
                "citas": [{"articulo": "76", "pasaje": "que en ningún caso podrá ser inferior"}],
            }
        ],
        "sugerencia": None,
    }
    return {**data, **overrides}


def test_context_is_numbered_with_citation_labels() -> None:
    context = format_context([_article("76", "doce días"), _article("78", "continuos", 2)])
    assert context.startswith("[1] Art. 76, LFT — TÍTULO TERCERO")
    assert "\n\n[2] Art. 78, LFT" in context


def test_prompt_asks_for_literal_passages_and_keeps_rules() -> None:
    messages = build_messages("¿Vacaciones?", [_article("76")], "2026-05-14")
    assert "LITERALMENTE" in messages[0]["content"]
    assert "régimen especial" in messages[0]["content"]
    assert "DOF 2026-05-14" in messages[1]["content"]
    assert SYSTEM_PROMPT == messages[0]["content"]


def test_schema_is_strict_and_orders_frase_before_parrafos() -> None:
    assert ANSWER_SCHEMA["additionalProperties"] is False
    keys = list(ANSWER_SCHEMA["properties"])
    assert keys.index("estado") < keys.index("frase_principal") < keys.index("parrafos")
    assert set(ANSWER_SCHEMA["required"]) == set(keys)


def test_valid_answer_is_kept() -> None:
    answer = apply_structured_rules(_answer(), {"76", "78"})
    assert answer.estado == "respondida"
    assert answer.citas == ["76"]
    assert answer.as_text().endswith("(Art. 76, LFT)")


def test_citation_outside_context_is_dropped_and_recorded() -> None:
    data = _answer(
        parrafos=[
            {
                "texto": "Algo.",
                "citas": [{"articulo": "76", "pasaje": "x"}, {"articulo": "999", "pasaje": "y"}],
            }
        ]
    )
    answer = apply_structured_rules(data, {"76"})
    assert answer.citas == ["76"]
    assert answer.citas_invalidas == ["999"]


def test_paragraph_without_valid_citation_is_removed() -> None:
    """Sin cita no hay afirmación."""
    data = _answer(
        parrafos=[
            {"texto": "Con respaldo.", "citas": [{"articulo": "76", "pasaje": "x"}]},
            {"texto": "Sin respaldo.", "citas": []},
            {"texto": "Cita inventada.", "citas": [{"articulo": "999", "pasaje": "y"}]},
        ]
    )
    answer = apply_structured_rules(data, {"76"})
    assert [p.texto for p in answer.parrafos] == ["Con respaldo."]


def test_no_supported_paragraph_becomes_sin_respuesta() -> None:
    data = _answer(parrafos=[{"texto": "Algo.", "citas": [{"articulo": "999", "pasaje": "y"}]}])
    answer = apply_structured_rules(data, {"76"})
    assert answer.estado == "sin_respuesta"
    assert answer.frase_principal == "No encontré esto en la LFT."
    assert answer.parrafos == []


def test_model_sin_respuesta_keeps_explanation_and_suggestion() -> None:
    data = _answer(
        estado="sin_respuesta",
        frase_principal="La LFT explica cómo se fija el salario mínimo, pero no dice cuánto es.",
        parrafos=[],
        sugerencia="¿Cómo se fija el salario mínimo?",
    )
    answer = apply_structured_rules(data, {"94"})
    assert answer.estado == "sin_respuesta"
    assert answer.sugerencia == "¿Cómo se fija el salario mínimo?"
    assert answer.frase_principal.startswith("La LFT explica")


@pytest.mark.parametrize("raw", ["", "no es json", "[1, 2]", '{"estado": "otro"}'])
def test_invalid_model_output_is_sin_respuesta(raw: str) -> None:
    assert parse_answer(raw, {"76"}).estado == "sin_respuesta"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("76", "76"), ("Art. 76", "76"), ("3o.", "3"), ("3 Bis", "3 Bis"), ("Artículo 39-A", "39-A")],
)
def test_normalize_citation(raw: str, expected: str) -> None:
    assert normalize_citation(raw) == expected


def test_extract_citations_from_plain_text() -> None:
    text = "Uno (Art. 76, LFT) y (Art. 132, XXVII Bis, LFT) y (Art. 3 Bis, LFT) (Art. 76, LFT)"
    assert extract_citations(text) == ["76", "132", "3 Bis"]


def test_parse_partial_json() -> None:
    partial = parse_partial('{"estado":"respondida","frase_principal":"Te toc')
    assert partial == {"estado": "respondida", "frase_principal": "Te toc"}
    assert parse_partial("") == {}


def test_generate_without_articles_skips_llm() -> None:
    def fail(_messages: list[dict]) -> str:
        raise AssertionError("no debe llamar al LLM sin contexto")

    assert generate("¿Algo?", [], SETTINGS, complete=fail).abstencion


def test_generate_parses_structured_output() -> None:
    result = generate(
        "¿Vacaciones?", [_article("76")], SETTINGS, "2026-05-14", lambda _: json.dumps(_answer())
    )
    assert result.citas == ["76"]
    assert not result.abstencion
    assert "(Art. 76, LFT)" in result.respuesta
