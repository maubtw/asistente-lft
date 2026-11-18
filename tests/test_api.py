"""Tests de la API sin OpenAI ni modelos: los eventos del pipeline se reemplazan."""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app, get_base_settings, get_events_fn
from rag.config import Settings

KEY = {"X-OpenAI-Key": "sk-user"}

CONTRACT = {
    "estado": "respondida",
    "frase_principal": "Te corresponden 16 días de vacaciones.",
    "parrafos": [
        {
            "texto": "La ley parte de 12 días.",
            "citas": [{"articulo": "76", "pasaje": "que en ningún caso podrá ser inferior"}],
        }
    ],
    "sugerencia": None,
    "articulos": {
        "76": {
            "titulo": "Título tercero, Condiciones de Trabajo",
            "capitulo": "Capítulo IV, Vacaciones",
            "texto": "… que en ningún caso podrá ser inferior a doce días …",
            "referencias": [],
        }
    },
    "fecha_reforma": "2026-05-14",
    "debug": {"consulta_reescrita": "periodo anual", "latencias_ms": {"total": 6}},
}
EVENTS = [
    {"event": "etapa", "data": {"etapa": "busqueda", "mensaje": "Buscando en la ley…"}},
    {"event": "articulos", "data": {"ids": ["76", "78"]}},
    {"event": "frase", "data": {"frase_principal": CONTRACT["frase_principal"]}},
    {"event": "parrafo", "data": {"indice": 0, **CONTRACT["parrafos"][0]}},
    {"event": "fin", "data": CONTRACT},
]


@pytest.fixture
def calls() -> list[tuple[str, Settings]]:
    received: list[tuple[str, Settings]] = []

    def fake_events(question: str, settings: Settings):
        received.append((question, settings))
        yield from EVENTS

    app.dependency_overrides[get_events_fn] = lambda: fake_events
    app.dependency_overrides[get_base_settings] = lambda: Settings(
        _env_file=None, openai_api_key="sk-env"
    )
    yield received
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)  # sin `with`: no corre el lifespan (no carga modelos)


def test_ask_returns_exact_contract(client, calls) -> None:
    response = client.post("/ask", json={"pregunta": "¿Vacaciones en mi tercer año?"}, headers=KEY)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "estado",
        "frase_principal",
        "parrafos",
        "sugerencia",
        "articulos",
        "fecha_reforma",
    }
    assert body["parrafos"][0]["citas"][0]["articulo"] == "76"
    assert body["sugerencia"] is None  # null explícito, como en el contrato
    assert "texto_parcial" not in body["articulos"]["76"]  # campo opcional ausente


def test_unverifiable_passage_is_explicit_null(client, calls) -> None:
    CONTRACT["parrafos"][0]["citas"].append({"articulo": "76", "pasaje": None})
    try:
        body = client.post("/ask", json={"pregunta": "¿Vacaciones?"}, headers=KEY).json()
    finally:
        CONTRACT["parrafos"][0]["citas"].pop()
    assert body["parrafos"][0]["citas"][1] == {"articulo": "76", "pasaje": None}


def test_ask_debug_adds_debug_block(client, calls) -> None:
    body = client.post("/ask", json={"pregunta": "¿Vacaciones?", "debug": True}, headers=KEY).json()
    assert body["debug"]["consulta_reescrita"] == "periodo anual"


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_stream_emits_sse_events_in_order(client, calls) -> None:
    response = client.post("/ask/stream", json={"pregunta": "¿Vacaciones?"}, headers=KEY)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert [name for name, _ in events] == ["etapa", "articulos", "frase", "parrafo", "fin"]
    assert events[0][1]["mensaje"] == "Buscando en la ley…"
    assert "debug" not in events[-1][1]


def test_stream_error_becomes_error_event(client, calls) -> None:
    import httpx
    import openai

    def failing(question, settings):
        yield EVENTS[0]
        request = httpx.Request("POST", "https://api.openai.com")
        raise openai.AuthenticationError(
            "bad key sk-user", response=httpx.Response(401, request=request), body=None
        )

    app.dependency_overrides[get_events_fn] = lambda: failing
    response = client.post("/ask/stream", json={"pregunta": "¿Vacaciones?"}, headers=KEY)
    events = _parse_sse(response.text)
    assert events[-1] == ("error", {"codigo": 401, "mensaje": "La API key de OpenAI no es válida."})
    assert "sk-user" not in response.text


def test_modes_map_to_measured_configs(client, calls) -> None:
    client.post("/ask", json={"pregunta": "¿Vacaciones?", "modo": "ligero"}, headers=KEY)
    client.post("/ask", json={"pregunta": "¿Vacaciones?", "modo": "completo"}, headers=KEY)
    ligero, completo = calls[0][1], calls[1][1]
    assert not ligero.use_reranker and ligero.use_query_rewrite
    assert completo.use_reranker and completo.use_hybrid and completo.rerank_query == "max"


def test_request_uses_the_user_key(client, calls) -> None:
    client.post("/ask", json={"pregunta": "¿Vacaciones?"}, headers={"X-OpenAI-Key": "sk-otra"})
    assert calls[0][1].openai_api_key.get_secret_value() == "sk-otra"


def test_env_key_is_never_used(client, calls) -> None:
    """Repo público: aunque el servidor tenga clave en .env, cada petición debe traer la suya."""
    for path in ("/ask", "/ask/stream"):
        for headers in ({}, {"X-OpenAI-Key": "   "}):
            response = client.post(path, json={"pregunta": "¿Vacaciones?"}, headers=headers)
            assert response.status_code == 400
            assert "clave de API" in response.json()["detail"]
    assert calls == []  # nunca llegó al pipeline


@pytest.mark.parametrize("payload", [{"pregunta": "a"}, {"pregunta": "¿x?", "modo": "turbo"}])
def test_invalid_requests(client, calls, payload) -> None:
    assert client.post("/ask", json=payload, headers=KEY).status_code == 422


def test_openai_auth_error_maps_to_401(client, calls) -> None:
    import httpx
    import openai

    def failing(question, settings):
        request = httpx.Request("POST", "https://api.openai.com")
        raise openai.AuthenticationError(
            "bad key sk-user", response=httpx.Response(401, request=request), body=None
        )
        yield  # generador

    app.dependency_overrides[get_events_fn] = lambda: failing
    response = client.post("/ask", json={"pregunta": "¿Vacaciones?"}, headers=KEY)
    assert response.status_code == 401
    assert "sk-user" not in response.text


def test_cors_allows_local_frontend(client, calls) -> None:
    response = client.options(
        "/ask",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-OpenAI-Key, Content-Type",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
