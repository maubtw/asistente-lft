"""Validación de pasajes con textos reales de la LFT (DOF 14-05-2026)."""

import random

import pytest

from rag.passages import clean_passage, normalize_with_map, validate_passage

ART_76 = (
    "Las personas trabajadoras que tengan más de un año de servicios disfrutarán de un periodo "
    "anual de vacaciones pagadas, que en ningún caso podrá ser inferior a doce días laborables, y "
    "que aumentará en dos días laborables, hasta llegar a veinte, por cada año subsecuente de "
    "servicios.\nA partir del sexto año, el periodo de vacaciones aumentará en dos días por cada "
    "cinco de servicios."
)
ART_78 = (
    "Del total del periodo que le corresponda conforme a lo previsto en el artículo 76 de esta "
    "Ley, la persona trabajadora disfrutará de doce días de vacaciones continuos, por lo menos. "
    "Dicho periodo, a potestad de la persona trabajadora podrá ser distribuido en la forma y "
    "tiempo que así lo requiera."
)
ART_132_FRAGMENT = (
    "XXVII.- Proporcionar a las mujeres embarazadas la protección que establezcan los "
    "reglamentos.\n"
    "XXVII Bis. Otorgar permiso de paternidad de cinco días laborables con goce de sueldo, a los "
    "hombres trabajadores, por el nacimiento de sus hijos y de igual manera en el caso de la "
    "adopción de un infante;"
)


def assert_literal(result, text: str) -> None:
    assert result.pasaje is not None
    assert result.pasaje in text
    assert text[result.inicio : result.inicio + len(result.pasaje)] == result.pasaje


def test_exact_passage() -> None:
    passage = "que en ningún caso podrá ser inferior a doce días laborables"
    result = validate_passage(passage, ART_76)
    assert result.metodo == "exacto"
    assert result.pasaje == passage
    assert_literal(result, ART_76)


@pytest.mark.parametrize(
    "passage",
    [
        # comillas tipográficas y punto final agregados por el modelo
        "“que en ningún caso podrá ser inferior a doce días laborables.”",
        # salto de línea del artículo convertido en espacio
        "por cada año subsecuente de servicios. A partir del sexto año",
        # mayúscula inicial y espacios dobles
        "Que en ningún caso  podrá ser inferior a doce días laborables",
    ],
)
def test_normalized_passage_returns_original_text(passage: str) -> None:
    result = validate_passage(passage, ART_76)
    assert result.metodo == "normalizado"
    assert_literal(result, ART_76)
    assert "“" not in result.pasaje and not result.pasaje.endswith(".”")


def test_normalized_keeps_article_line_break() -> None:
    result = validate_passage("de servicios. A partir del sexto año", ART_76)
    assert "\n" in result.pasaje  # el tramo literal conserva el salto de línea original


def test_ellipsis_with_nearby_fragments_highlights_whole_span() -> None:
    passage = (
        "que en ningún caso podrá ser inferior a doce días laborables, … hasta llegar a veinte"
    )
    result = validate_passage(passage, ART_76)
    assert result.metodo == "normalizado"
    assert result.pasaje.startswith("que en ningún caso")
    assert result.pasaje.endswith("hasta llegar a veinte")
    assert_literal(result, ART_76)


def test_trailing_ellipsis_from_contract_example() -> None:
    result = validate_passage(
        "que en ningún caso podrá ser inferior a doce días laborables, …", ART_76
    )
    assert result.pasaje == "que en ningún caso podrá ser inferior a doce días laborables"


def test_ellipsis_with_distant_fragments_uses_longest() -> None:
    passage = "Las personas trabajadoras que tengan más de un año … cada cinco de servicios"
    result = validate_passage(passage, ART_76)
    assert result.pasaje == "Las personas trabajadoras que tengan más de un año"


def test_fuzzy_passage_tolerates_accent_and_expands_to_whole_words() -> None:
    # "período" (modelo) vs. "periodo" (ley vigente)
    result = validate_passage("disfrutarán de un período anual de vacaciones pagadas", ART_76)
    assert result.metodo == "difuso"
    assert result.pasaje.startswith("disfrutarán de un periodo")
    assert_literal(result, ART_76)


def test_substituted_legal_word_is_not_verifiable() -> None:
    """La maqueta de diseño cita el Art. 78 con "a elección del trabajador"; la ley vigente dice
    "a potestad de la persona trabajadora". Resaltarlo afirmaría una palabra que la ley no usa."""
    result = validate_passage("a elección de la persona trabajadora podrá ser distribuido", ART_78)
    assert result.pasaje is None


def test_passage_from_another_article_is_not_verifiable() -> None:
    result = validate_passage("permiso de paternidad de cinco días laborables", ART_76)
    assert result.pasaje is None
    assert result.metodo == "no_verificable"


def test_short_passages_are_not_fuzzy_matched() -> None:
    assert validate_passage("doce dias", ART_76).pasaje is None  # 9 caracteres, sin acento
    assert validate_passage("doce días", ART_76).metodo == "exacto"


@pytest.mark.parametrize("passage", [None, "", "   ", "…", '""'])
def test_empty_passages(passage) -> None:
    assert validate_passage(passage, ART_76).pasaje is None


def test_roman_numeral_fraction_passage() -> None:
    passage = "Otorgar permiso de paternidad de cinco días laborables con goce de sueldo"
    result = validate_passage(passage, ART_132_FRAGMENT)
    assert result.metodo == "exacto"
    assert_literal(result, ART_132_FRAGMENT)


def test_property_result_is_always_literal_substring() -> None:
    """Para entradas arbitrarias (recortes, mutaciones, basura) el resultado es None o literal."""
    rng = random.Random(42)
    texts = [ART_76, ART_78, ART_132_FRAGMENT]
    for _ in range(400):
        text = rng.choice(texts)
        start = rng.randrange(len(text) - 10)
        piece = text[start : start + rng.randrange(5, 120)]
        mutation = rng.choice(["none", "upper", "drop", "quote", "ellipsis", "noise"])
        if mutation == "upper":
            piece = piece.upper()
        elif mutation == "drop" and len(piece) > 3:
            i = rng.randrange(len(piece))
            piece = piece[:i] + piece[i + 1 :]
        elif mutation == "quote":
            piece = f"“{piece}”"
        elif mutation == "ellipsis":
            piece = piece[: len(piece) // 2] + " … " + piece[len(piece) // 2 :]
        elif mutation == "noise":
            piece = "".join(rng.choice("abcxyz ñ,.") for _ in range(rng.randrange(1, 60)))
        result = validate_passage(piece, text)
        if result.pasaje is not None:
            assert_literal(result, text)


def test_normalize_map_points_to_original_characters() -> None:
    text = "Uno  dos\n“tres”"
    norm, index_map = normalize_with_map(text)
    assert norm == 'uno dos "tres"'
    assert len(norm) == len(index_map)
    assert text[index_map[norm.index("tres")]] == "t"


def test_clean_passage() -> None:
    assert clean_passage(" “…doce días laborables.” ") == "doce días laborables"
