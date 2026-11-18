"""Tests del parser con líneas copiadas tal cual del PDF oficial (DOF 14-05-2026)."""

import pytest

from ingest.parse_ley import (
    Article,
    add_references,
    adjacent_references,
    article_sort_key,
    extract_references,
    extract_reform_date,
    is_derogated,
    is_reform_note,
    join_paragraphs,
    numbering_gaps,
    parse_body,
    parse_decree_transitorios,
    parse_header,
    split_body_and_transitorios,
    strip_page_header,
)

# --- Encabezados de artículo -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected_id", "expected_rest"),
    [
        ("Artículo 1o.- La presente Ley es de observancia general", "1", "La presente Ley es"),
        ("Artículo 10.- Patrón es la persona física o moral", "10", "Patrón es"),
        ("Artículo 22. Los mayores de quince años pueden prestar", "22", "Los mayores"),
        ("Artículo 39-A.- En los casos en que la relación", "39-A", "En los casos"),
        ("Artículo 3o. Bis.- Para efectos de esta Ley se entiende por:", "3 Bis", "Para efectos"),
        ("Artículo 3o. Ter.- Para efectos de esta Ley se entenderá por:", "3 Ter", "Para efectos"),
        ("Artículo 48 Bis.- Para efectos del artículo 48 de esta Ley", "48 Bis", "Para efectos"),
        ("Artículo 330-K.- Las personas empleadoras", "330-K", "Las personas"),
        ("Artículo 153-F Bis. Los patrones deberán conservar", "153-F Bis", "Los patrones"),
        ("Artículo 512-D Ter. En el caso de que las autoridades", "512-D Ter", "En el caso"),
        ("Artículo 353-Ñ.- Los sindicatos y las directivas", "353-Ñ", "Los sindicatos"),
        ("Artículo 15-A. Se deroga.", "15-A", "Se deroga."),
        ("Artículo 890- Se deroga.", "890", "Se deroga."),
        ("Artículo 525. (Se deroga).", "525", "(Se deroga)."),
        ("Artículo 1º.- Esta Ley entrará en vigor el día 1o. de mayo de 1970", "1", "Esta Ley"),
        ("Artículo 110.-", "110", ""),
    ],
)
def test_parse_header_real_formats(line: str, expected_id: str, expected_rest: str) -> None:
    header = parse_header(line)
    assert header is not None
    assert header.article_id == expected_id
    assert header.rest.startswith(expected_rest)


@pytest.mark.parametrize(
    "line",
    [
        "Artículo reformado DOF 27-12-2022",
        "Artículo adicionado DOF 30-11-2012. Derogado DOF 23-04-2021",
        "Artículo 123, Apartado A, de la Constitución.",
        "Artículo 27 Constitucional en Materia Nuclear; 9, fracción I,",
        "artículo 50 de esta Ley",
        "Artículo Único.- Se reforman los artículos",
    ],
)
def test_parse_header_rejects_non_headers(line: str) -> None:
    assert parse_header(line) is None


def test_sort_key_follows_legal_order() -> None:
    ordered = [
        (3, None, None),
        (3, None, "Bis"),
        (3, None, "Ter"),
        (4, None, None),
        (153, "F", None),
        (153, "F", "Bis"),
        (153, "G", None),
        (353, "N", None),
        (353, "Ñ", None),
        (353, "O", None),
    ]
    keys = [article_sort_key(*args) for args in ordered]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


# --- Limpieza --------------------------------------------------------------------------------


def test_strip_page_header() -> None:
    page = (
        "LEY FEDERAL DEL TRABAJO \n \nCÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN \n"
        "Secretaría General \nSecretaría de Servicios Parlamentarios \n"
        "Última Reforma DOF 14-05-2026 \n \n \n120 de 457 \nContrato colectivo de trabajo \n"
    )
    assert strip_page_header(page) == ["Contrato colectivo de trabajo"]


def test_extract_reform_date() -> None:
    text = "TEXTO VIGENTE \nÚltima reforma publicada 14-05-2026 \n"
    assert extract_reform_date(text) == "2026-05-14"
    assert extract_reform_date("Última reforma publicada DOF 24-12-2024") == "2024-12-24"
    assert extract_reform_date("sin fecha") is None


@pytest.mark.parametrize(
    "line",
    [
        "Artículo reformado DOF 27-12-2022",
        "Párrafo reformado DOF 01-05-2019, 15-01-2026",
        "Fracción adicionada DOF 09-01-1974. Fe de erratas DOF 10-01-1974.",
        "Párrafo con fracciones reformado DOF 01-05-2019",
        "Fe de erratas al artículo DOF 30-04-1970. Reformado DOF 23-04-2021",
        "Denominación del Título reformada DOF 31-12-1974",
        "Capítulo reubicado y denominación reformada DOF 04-01-1980.",
        "Reforma DOF 01-05-2026: Derogó del artículo el entonces párrafo segundo",
        "Nota: El decreto de reforma DOF 01-05-2019 no derogó el artículo 641-A de esta Ley.",
    ],
)
def test_reform_notes_detected(line: str) -> None:
    assert is_reform_note(line)


@pytest.mark.parametrize(
    "line",
    [
        "Artículo 76.- Las personas trabajadoras que tengan más de un año de servicios",
        "Nota: El porcentaje de valuación lo determinará el criterio con la categoría más alta.",
        "publicada en el DOF el día siguiente",
    ],
)
def test_law_text_is_not_a_note(line: str) -> None:
    assert not is_reform_note(line)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Se deroga.", True),
        ("(Se deroga).", True),
        ("Se deroga", True),
        ("Se deroga la fracción III del artículo 51.", False),
        ("Las personas trabajadoras que tengan más de un año", False),
    ],
)
def test_is_derogated(text: str, expected: bool) -> None:
    assert is_derogated(text) is expected


def test_join_paragraphs_merges_wrapped_lines() -> None:
    lines = ["I.", "Realizar en materia local la función", "conciliadora;", "", "II. Otra."]
    assert (
        join_paragraphs(lines) == "I. Realizar en materia local la función conciliadora;\nII. Otra."
    )


# --- Referencias cruzadas --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("conforme a lo previsto en el artículo 76 de esta Ley", ["76"]),
        ("en los términos de los artículos 47 y 51", ["47", "51"]),
        ("las fracciones I y II del artículo 132", ["132"]),
        ("los artículos 485, 486 y 501", ["485", "486", "501"]),
        ("lo dispuesto en los artículos 154 a 156", ["154", "155", "156"]),
        ("según el artículo 3o. Bis y el artículo 39-A", ["3 Bis", "39-A"]),
        ("comprendidas en el artículo 123, Apartado A, de la Constitución.", []),
        ("a que se refiere el artículo 140 Bis de la Ley del Seguro Social.", []),
        ("el artículo 9o. Transitorio.", []),
    ],
)
def test_extract_references(text: str, expected: list[str]) -> None:
    assert extract_references(text) == expected


def test_extract_references_excludes_self() -> None:
    assert extract_references("Para efectos del artículo 48 de esta Ley", self_id="48") == []


# --- Recorrido del documento -----------------------------------------------------------------

BODY = """TITULO TERCERO
Condiciones de Trabajo

CAPITULO IV
Vacaciones
Denominación del Capítulo reformada DOF 27-12-2022

Artículo 76.- Las personas trabajadoras que tengan más de un año de servicios disfrutarán de un
periodo anual de vacaciones pagadas.

A partir del sexto año, el periodo de vacaciones aumentará en dos días por cada cinco de servicios.
Artículo reformado DOF 27-12-2022

Artículo 76 Bis.- Se deroga.
Artículo adicionado DOF 30-11-2012. Derogado DOF 23-04-2021

Artículo 77.- Los trabajadores que presten servicios discontinuos conforme al
Artículo 50. Con texto que no es un encabezado.

CAPITULO IX
Comisión nacional para la participación de los trabajadores en las utilidades de las
empresas

Sección Primera
Reglas Generales
Sección adicionada DOF 04-01-1980

Artículo 78.- Del total del periodo conforme al artículo 76 de esta Ley.
Artículo reformado DOF 30-11-2012, 01-05-2019. Reformado en su totalidad con “Tabla
valuación de incapacidades” DOF 04-12-2023
"""


def _parse(text: str):
    return parse_body([line.strip() for line in text.splitlines()], "2026-05-14")


def test_parse_body_hierarchy_and_text() -> None:
    articles, _ = _parse(BODY)
    by_id = {a.articulo: a for a in articles}
    assert list(by_id) == ["76", "76 Bis", "77", "78"]

    art76 = by_id["76"]
    assert art76.titulo == "TÍTULO TERCERO Condiciones de Trabajo"
    assert art76.capitulo == "CAPÍTULO IV Vacaciones"
    assert art76.texto.startswith("Las personas trabajadoras")
    assert "\nA partir del sexto año" in art76.texto
    assert "DOF" not in art76.texto
    assert art76.notas_reforma == ["Artículo reformado DOF 27-12-2022"]
    assert art76.fecha_reforma == "2026-05-14"


def test_parse_body_derogated_and_false_header() -> None:
    articles, rejected = _parse(BODY)
    by_id = {a.articulo: a for a in articles}
    assert by_id["76 Bis"].derogado
    assert not by_id["76"].derogado
    # "Artículo 50." al inicio de línea dentro del Art. 77 retrocede en la numeración → es texto
    assert "Artículo 50. Con texto" in by_id["77"].texto
    assert rejected == ["Artículo 50. Con texto que no es un encabezado."]


def test_parse_body_wrapped_chapter_section_and_note() -> None:
    articles, _ = _parse(BODY)
    art78 = articles[-1]
    assert art78.capitulo == (
        "CAPÍTULO IX Comisión nacional para la participación de los trabajadores en las "
        "utilidades de las empresas"
    )
    assert art78.seccion == "Sección Primera Reglas Generales"
    assert "DOF" not in art78.texto
    assert len(art78.notas_reforma) == 1
    assert art78.notas_reforma[0].endswith("DOF 04-12-2023")


def test_parse_body_chapter_case_variants() -> None:
    text = """Capítulo III BIS
De la Productividad, Formación y Capacitación de los Trabajadores
Capítulo adicionado DOF 28-04-1978. Denominación reformada DOF 30-11-2012

Artículo 153-A. Los patrones tienen la obligación de proporcionar capacitación.

Capitulo XIII Bis
De las Personas Trabajadoras de Plataformas Digitales

Artículo 153-B.- Texto.
"""
    articles, _ = _parse(text)
    assert articles[0].capitulo == (
        "CAPÍTULO III BIS De la Productividad, Formación y Capacitación de los Trabajadores"
    )
    assert articles[1].capitulo.startswith("CAPÍTULO XIII BIS De las Personas")
    assert "Capitulo" not in articles[0].texto


def test_split_body_and_transitorios() -> None:
    lines = ["Artículo 1010.- Las sanciones se harán efectivas.", "", "TRANSITORIOS", "", "x"]
    body, trans = split_body_and_transitorios(lines)
    assert body[-2:] == ["Artículo 1010.- Las sanciones se harán efectivas.", ""]
    assert trans == ["", "x"]


def test_parse_decree_transitorios() -> None:
    lines = [
        "DECRETO por el que se reforma el artículo 74 de la Ley Federal del Trabajo.",
        "",
        "Publicado en el Diario Oficial de la Federación el 17 de enero de 2006",
        "",
        "ARTÍCULO ÚNICO.- Se reforma el artículo 74.",
        "",
        "TRANSITORIO",
        "",
        "ÚNICO.- El presente Decreto entrará en vigor al día siguiente.",
    ]
    [decree] = parse_decree_transitorios(lines, "2026-05-14")
    assert decree.articulo == "Transitorios DOF 17-01-2006"
    assert decree.es_transitorio
    assert decree.texto == "ÚNICO.- El presente Decreto entrará en vigor al día siguiente."
    assert decree.titulo.startswith("DECRETO por el que se reforma el artículo 74")


def test_numbering_gaps() -> None:
    assert numbering_gaps(["1", "2", "3 Bis", "5", "5-A"]) == [4]
    assert numbering_gaps([]) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("En los casos del artículo anterior los trabajadores y los patrones…", ["74"]),
        ("las causas mencionadas en el artículo anterior y tendrá derecho", ["74"]),
        ("lo dispuesto en el artículo precedente", ["74"]),
        ("en los términos del artículo siguiente", ["76"]),
        ("lo previsto en los artículos anteriores", []),  # plural: ambiguo
        ("la fracción anterior", []),
    ],
)
def test_adjacent_references(text: str, expected: list[str]) -> None:
    assert adjacent_references(text, previous_id="74", next_id="76") == expected


def test_add_references_resolves_previous_article_first() -> None:
    articles = [
        Article(articulo="74", texto="Son días de descanso obligatorio: I. El 1o. de enero;"),
        Article(articulo="74 Bis", texto="Se deroga.", derogado=True),
        Article(
            articulo="75",
            texto="En los casos del artículo anterior… conforme al artículo 76 de esta Ley.",
        ),
        Article(articulo="76", texto="Las vacaciones… artículo anterior."),
    ]
    add_references(articles)
    assert articles[2].referencias == [
        "74 Bis",
        "76",
    ]  # vecino literal (aunque derogado) + explícito
    assert articles[3].referencias == ["75"]
