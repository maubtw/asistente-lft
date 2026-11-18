"""Eventos del pipeline (streaming) con LLM, reescritura, recuperación y base falsos."""

import json

import pytest

from rag import pipeline
from rag.config import Settings
from rag.pipeline import ArticleStore, answer, answer_events, format_heading
from rag.retriever import RetrievedArticle

ART_76 = (
    "Las personas trabajadoras que tengan más de un año de servicios disfrutarán de un periodo "
    "anual de vacaciones pagadas, que en ningún caso podrá ser inferior a doce días laborables."
)
ART_80 = (
    "Los trabajadores tendrán derecho a una prima no menor de veinticinco por ciento sobre los "
    "salarios que les correspondan durante el período de vacaciones."
)
DB = {
    "76": {
        "titulo": "TÍTULO TERCERO Condiciones de Trabajo",
        "capitulo": "CAPÍTULO IV Vacaciones",
        "texto": ART_76,
        "referencias": [],
    },
    "80": {
        "titulo": "TÍTULO TERCERO Condiciones de Trabajo",
        "capitulo": "CAPÍTULO IV Vacaciones",
        "texto": ART_80,
        "referencias": ["76"],
    },
}
MODEL_JSON = json.dumps(
    {
        "estado": "respondida",
        "frase_principal": "Te corresponden al menos 12 días.",
        "parrafos": [
            {
                "texto": "El mínimo es de 12 días laborables.",
                "citas": [
                    {
                        "articulo": "76",
                        "pasaje": "“que en ningún caso podrá ser inferior a doce días laborables.”",
                    }
                ],
            },
            {
                "texto": "Además hay una prima del 25 %.",
                "citas": [
                    {"articulo": "80", "pasaje": "una prima no menor de veinticinco por ciento"}
                ],
            },
            {
                "texto": "Párrafo con cita inventada.",
                "citas": [{"articulo": "999", "pasaje": "nada"}],
            },
        ],
        "sugerencia": None,
    },
    ensure_ascii=False,
)


def _retrieved(articulo: str, texto: str) -> RetrievedArticle:
    return RetrievedArticle(
        1, articulo, DB[articulo]["titulo"], DB[articulo]["capitulo"], texto, 0.9
    )


@pytest.fixture
def fake_retrieval(monkeypatch):
    def steps(question, settings, k=None, queries=None, timings=None):
        yield "busqueda"
        yield "referencias"
        return [_retrieved("76", ART_76), _retrieved("80", ART_80)]

    monkeypatch.setattr(pipeline, "retrieve_steps", steps)


def _events(text: str = MODEL_JSON, chunk: int = 7) -> list[dict]:
    settings = Settings(_env_file=None, use_query_rewrite=True)
    return list(
        answer_events(
            "¿Cuántas vacaciones?",
            settings,
            stream=lambda _messages: (text[i : i + chunk] for i in range(0, len(text), chunk)),
            rewriter=lambda _messages: "periodo anual de vacaciones",
            fetch=lambda ids: {i: DB[i] for i in ids if i in DB},
        )
    )


def test_event_order(fake_retrieval) -> None:
    names = [e["event"] for e in _events()]
    assert names == [
        "etapa",
        "etapa",
        "etapa",
        "articulos",
        "etapa",
        "frase",
        "parrafo",
        "parrafo",
        "fin",
    ]
    stages = [e["data"]["etapa"] for e in _events() if e["event"] == "etapa"]
    assert stages == ["reescritura", "busqueda", "referencias", "generacion"]


def test_streamed_paragraphs_match_final_contract(fake_retrieval) -> None:
    events = _events()
    streamed = [e["data"] for e in events if e["event"] == "parrafo"]
    final = events[-1]["data"]
    assert [p["texto"] for p in streamed] == [p["texto"] for p in final["parrafos"]]
    assert [p["citas"] for p in streamed] == [p["citas"] for p in final["parrafos"]]
    assert [p["indice"] for p in streamed] == [0, 1]


def test_contract_shape_and_literal_passages(fake_retrieval) -> None:
    final = _events()[-1]["data"]
    assert set(final) == {
        "estado",
        "frase_principal",
        "parrafos",
        "sugerencia",
        "articulos",
        "fecha_reforma",
        "debug",
    }
    assert final["estado"] == "respondida"
    assert len(final["parrafos"]) == 2  # el de la cita inventada se descartó
    for parrafo in final["parrafos"]:
        for cita in parrafo["citas"]:
            assert cita["pasaje"] in final["articulos"][cita["articulo"]]["texto"]
    # la versión del modelo traía comillas y punto: se devuelve el tramo literal
    assert final["parrafos"][0]["citas"][0]["pasaje"].startswith("que en ningún caso")
    assert final["articulos"]["80"]["referencias"] == ["76"]
    assert final["articulos"]["76"]["titulo"] == "Título tercero, Condiciones de Trabajo"
    assert final["debug"]["citas_invalidas"] == ["999"]
    assert final["debug"]["consulta_reescrita"] == "periodo anual de vacaciones"
    methods = [c["metodo"] for c in final["debug"]["verificacion"]]
    assert methods == ["normalizado", "exacto"]


def test_last_paragraph_is_streamed_too(fake_retrieval) -> None:
    """Regresión: el último párrafo solo se sabía completo al cerrar el stream y no se emitía."""
    data = json.loads(MODEL_JSON)
    data["parrafos"] = data["parrafos"][:2]  # el último párrafo es válido
    events = _events(json.dumps(data, ensure_ascii=False))
    streamed = [e["data"]["texto"] for e in events if e["event"] == "parrafo"]
    assert streamed == [p["texto"] for p in events[-1]["data"]["parrafos"]]
    assert len(streamed) == 2


def test_single_chunk_still_emits_frase_and_paragraphs(fake_retrieval) -> None:
    names = [e["event"] for e in _events(chunk=100_000)]
    assert names.count("frase") == 1
    assert names.count("parrafo") == 2


@pytest.mark.parametrize("chunk", [1, 3, 50, 10_000])
def test_streaming_is_independent_of_chunk_size(fake_retrieval, chunk) -> None:
    events = _events(chunk=chunk)
    assert [e["data"]["texto"] for e in events if e["event"] == "parrafo"] == [
        "El mínimo es de 12 días laborables.",
        "Además hay una prima del 25 %.",
    ]


def test_unverifiable_passage_keeps_citation_without_highlight(fake_retrieval) -> None:
    text = MODEL_JSON.replace(
        "una prima no menor de veinticinco por ciento", "texto inventado que no está"
    )
    final = _events(text)[-1]["data"]
    cita_80 = final["parrafos"][1]["citas"][0]
    assert cita_80 == {"articulo": "80", "pasaje": None}


def test_sin_respuesta(fake_retrieval) -> None:
    text = json.dumps(
        {
            "estado": "sin_respuesta",
            "frase_principal": "La LFT no fija el monto.",
            "parrafos": [],
            "sugerencia": "¿Cómo se fija el salario mínimo?",
        }
    )
    events = _events(text)
    assert not [e for e in events if e["event"] in ("frase", "parrafo")]
    final = events[-1]["data"]
    assert final["estado"] == "sin_respuesta"
    assert final["sugerencia"] == "¿Cómo se fija el salario mínimo?"
    assert final["articulos"] == {}


def test_truncated_model_output_is_sin_respuesta(fake_retrieval) -> None:
    assert _events(MODEL_JSON[:120])[-1]["data"]["estado"] == "sin_respuesta"


def test_answer_returns_final_contract(fake_retrieval) -> None:
    settings = Settings(_env_file=None)
    result = answer(
        "¿Vacaciones?",
        settings,
        stream=lambda _m: iter([MODEL_JSON]),
        fetch=lambda ids: {i: DB[i] for i in ids},
    )
    assert result["estado"] == "respondida"


def test_long_articles_are_sent_partially() -> None:
    long_text = "Fracción. " * 3000
    retrieved = [RetrievedArticle(1, "513", None, None, "Fracción. Fracción.", 0.9)]
    store = ArticleStore(
        lambda ids: {
            "513": {"titulo": None, "capitulo": None, "texto": long_text, "referencias": []}
        },
        retrieved,
    )
    entry = store.get(["513"])["513"]
    assert entry["texto_parcial"] is True
    assert entry["texto"] == "Fracción. Fracción."


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TÍTULO TERCERO Condiciones de Trabajo", "Título tercero, Condiciones de Trabajo"),
        ("TÍTULO QUINTO BIS Trabajo de los Menores", "Título quinto bis, Trabajo de los Menores"),
        ("CAPÍTULO IV Vacaciones", "Capítulo IV, Vacaciones"),
        ("CAPÍTULO III BIS De la Productividad", "Capítulo III Bis, De la Productividad"),
        (
            "CAPÍTULO IX BIS TRABAJO EN PLATAFORMAS DIGITALES",
            "Capítulo IX Bis, Trabajo en plataformas digitales",
        ),
        (None, None),
    ],
)
def test_format_heading(raw, expected) -> None:
    assert format_heading(raw) == expected
