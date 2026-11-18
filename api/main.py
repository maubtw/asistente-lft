"""API del Asistente LFT.

    uv run uvicorn api.main:app --reload

- POST /ask              pregunta → respuesta estructurada con pasajes (contrato de DESIGN.md)
- POST /ask/stream       lo mismo por Server-Sent Events: etapa, articulos, frase, parrafo, fin
- GET  /meta             fecha de última reforma y número de artículos vigentes
- GET  /articulo/{id}    texto completo de un artículo (p. ej. /articulo/76, /articulo/3%20Bis)
- GET  /health           estado de la base y de la configuración

Cada pregunta debe traer la clave de OpenAI del usuario en el encabezado `X-OpenAI-Key`: se usa
solo para esa petición y nunca se guarda ni se registra. La API **no** usa la clave del `.env`
(esa es solo para la evaluación y el CLI de quien desarrolla): el repositorio es público y cada
persona usa su propia clave.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rag.config import Settings, get_settings
from rag.db import connect, database_stats, get_article
from rag.modes import MODE_DESCRIPTIONS, MODES, settings_for_mode
from rag.pipeline import AVISO_LEGAL, answer_events

logger = logging.getLogger("asistente_lft")

EventsFn = Callable[[str, Settings], Iterator[dict]]


# --- Contrato (docs/design/DESIGN.md, "Contrato de API que necesita este diseño") ---------


class AskRequest(BaseModel):
    pregunta: str = Field(min_length=3, max_length=500, examples=["¿Cuántos días de vacaciones?"])
    modo: Literal["completo", "ligero"] = "completo"
    debug: bool = False


class Cita(BaseModel):
    articulo: str
    # Subcadena literal de articulos[articulo].texto, o null si no se pudo verificar
    # (la cita se conserva, solo no hay resaltado).
    pasaje: str | None


class Parrafo(BaseModel):
    texto: str
    citas: list[Cita]


class ArticuloCitado(BaseModel):
    titulo: str | None
    capitulo: str | None
    texto: str
    referencias: list[str]
    texto_parcial: bool | None = None  # solo en artículos muy largos (p. ej. el 513)


class AskResponse(BaseModel):
    estado: Literal["respondida", "sin_respuesta"]
    frase_principal: str
    parrafos: list[Parrafo]
    sugerencia: str | None
    articulos: dict[str, ArticuloCitado]
    fecha_reforma: str | None
    debug: dict | None = None  # solo con debug=true


class Meta(BaseModel):
    fecha_reforma: str | None
    articulos_vigentes: int


class Articulo(BaseModel):
    articulo: str
    titulo: str | None
    capitulo: str | None
    texto: str
    referencias: list[str]
    derogado: bool
    es_transitorio: bool
    fecha_reforma: str | None


# --- Dependencias (se reemplazan en los tests) --------------------------------------------


def get_events_fn() -> EventsFn:
    return answer_events


def get_base_settings() -> Settings:
    return get_settings()


# --- App ---------------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Carga los modelos al arrancar: la primera pregunta no paga ~30 s de carga."""
    settings = get_settings()
    from rag.embeddings import embed_texts

    embed_texts(["precalentamiento"], settings.embedding_model)
    if any(flags["use_reranker"] for flags in MODES.values()):
        from rag.reranker import load_reranker

        load_reranker(settings.reranker_model)
    yield


app = FastAPI(
    title="Asistente LFT",
    description="Preguntas sobre la Ley Federal del Trabajo con el artículo exacto citado. "
    + AVISO_LEGAL,
    version="0.2.0",
    lifespan=lifespan,
)
# El frontend corre en local en otro puerto (Next.js: 3000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-OpenAI-Key"],
)


def _request_settings(request: AskRequest, base: Settings, user_key: str | None) -> Settings:
    """Configuración de la petición con la clave del usuario (obligatoria)."""
    user_key = (user_key or "").strip()
    if not user_key:
        raise HTTPException(
            400, "Falta tu clave de API de OpenAI: envíala en el encabezado X-OpenAI-Key."
        )
    return settings_for_mode(request.modo, api_key=user_key, base=base)


def _public(contract: dict, debug: bool) -> dict:
    return contract if debug else {k: v for k, v in contract.items() if k != "debug"}


@app.post("/ask", response_model=AskResponse, response_model_exclude_unset=True)
def ask(
    request: AskRequest,
    events_fn: Annotated[EventsFn, Depends(get_events_fn)],
    base: Annotated[Settings, Depends(get_base_settings)],
    x_openai_key: Annotated[str | None, Header()] = None,
) -> dict:
    settings = _request_settings(request, base, x_openai_key)
    try:
        final = next(
            e["data"] for e in events_fn(request.pregunta, settings) if e["event"] == "fin"
        )
    except Exception as exc:
        raise _error(exc) from exc
    return _public(final, request.debug)


@app.post("/ask/stream")
def ask_stream(
    request: AskRequest,
    events_fn: Annotated[EventsFn, Depends(get_events_fn)],
    base: Annotated[Settings, Depends(get_base_settings)],
    x_openai_key: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Server-Sent Events. Eventos: `etapa` {etapa, mensaje}, `articulos` {ids},
    `frase` {frase_principal}, `parrafo` {indice, texto, citas}, `fin` {contrato},
    `error` {codigo, mensaje}.

    El frontend usa fetch + ReadableStream (EventSource no admite POST ni encabezados).
    """
    settings = _request_settings(request, base, x_openai_key)

    def sse() -> Iterator[str]:
        try:
            for event in events_fn(request.pregunta, settings):
                data = event["data"]
                if event["event"] == "fin":
                    data = _public(data, request.debug)
                yield _sse(event["event"], data)
        except Exception as exc:  # el stream ya empezó: el error viaja como evento
            error = _error(exc)
            yield _sse("error", {"codigo": error.status_code, "mensaje": error.detail})

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/meta", response_model=Meta)
def meta(settings: Annotated[Settings, Depends(get_base_settings)]) -> dict:
    stats = _stats(settings)
    fecha = stats["fecha_reforma"]
    return {
        "fecha_reforma": fecha.isoformat() if fecha else None,
        "articulos_vigentes": stats["articulos_vigentes"],
    }


@app.get("/health")
def health(settings: Annotated[Settings, Depends(get_base_settings)]) -> dict:
    stats = _stats(settings)
    fecha = stats["fecha_reforma"]
    return {
        "status": "ok",
        "articulos_vigentes": stats["articulos_vigentes"],
        "fecha_reforma": fecha.isoformat() if fecha else None,
        "modos": MODE_DESCRIPTIONS,
        "requiere_clave_usuario": True,  # la API nunca usa la clave del .env
    }


def _stats(settings: Settings) -> dict:
    try:
        with connect(settings.database_url) as conn:
            return database_stats(conn)
    except Exception as exc:  # la base no responde: la API sigue viva pero degradada
        raise HTTPException(503, f"Base de datos no disponible: {type(exc).__name__}") from exc


@app.get("/articulo/{article_id}", response_model=Articulo)
def articulo(article_id: str, settings: Annotated[Settings, Depends(get_base_settings)]) -> dict:
    with connect(settings.database_url) as conn:
        row = get_article(conn, article_id.strip())
    if row is None:
        raise HTTPException(404, f"No existe el artículo '{article_id}' en la LFT.")
    fecha = row["fecha_reforma"]
    return {
        **row,
        "referencias": list(row["referencias"] or []),
        "fecha_reforma": fecha.isoformat() if fecha else None,
    }


def _error(exc: Exception) -> HTTPException:
    """Traduce errores a códigos HTTP útiles, sin filtrar la key en el mensaje."""
    import openai

    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, openai.AuthenticationError):
        return HTTPException(401, "La API key de OpenAI no es válida.")
    if isinstance(exc, openai.RateLimitError):
        return HTTPException(429, "OpenAI rechazó la petición por límite de uso o saldo.")
    if isinstance(exc, openai.APIError):
        return HTTPException(502, f"Error de OpenAI: {type(exc).__name__}")
    logger.exception("Error inesperado al responder")
    return HTTPException(500, "Error interno al generar la respuesta.")
