"""Generación de la respuesta con OpenAI a partir de artículos numerados.

El modelo responde con JSON estructurado (structured outputs con esquema estricto):
una frase principal, párrafos con sus citas y, por cita, el **pasaje literal** del artículo que la
sustenta (lo resalta el frontend; se valida en `rag/passages.py`).

Principios del proyecto: toda afirmación cita un artículo del contexto; si el contexto no alcanza,
`estado = "sin_respuesta"`; nunca se usa conocimiento propio del modelo sobre la LFT.
Las reglas se aplican en código además del prompt (`apply_structured_rules`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Literal

from rag.config import Settings
from rag.retriever import RetrievedArticle

ABSTENTION = "No encontré esto en la LFT"

SYSTEM_PROMPT = """Eres un asistente que responde preguntas sobre la Ley Federal del Trabajo de \
México (LFT) usando EXCLUSIVAMENTE los artículos que se te proporcionan en el contexto.

Responde con un JSON con esta forma:
- "estado": "respondida" si el contexto permite responder; "sin_respuesta" si no.
- "frase_principal": una sola oración que responda directo a la pregunta, sin citas ni números de \
artículo. Si el estado es "sin_respuesta", explica en una o dos oraciones qué dice y qué no dice \
la ley sobre el tema, solo con lo que esté en el contexto; si el contexto no trata el tema, \
escribe "No encontré esto en la LFT.".
- "parrafos": de 1 a 3 párrafos que desarrollen la respuesta (lista vacía si "sin_respuesta"). \
Cada párrafo tiene "texto" y "citas".
  - "texto": explicación clara para alguien sin formación jurídica, sin escribir "(Art. X)" ni \
citas dentro del texto.
  - "citas": al menos una por párrafo. Cada cita tiene "articulo" (el número tal como aparece en \
el contexto: "76", "39-A", "3 Bis") y "pasaje": el fragmento de ESE artículo que sustenta el \
párrafo, COPIADO LITERALMENTE del contexto, carácter por carácter, sin cambiar, quitar ni \
agregar palabras (entre 8 y 45 palabras; sin puntos suspensivos).
- "sugerencia": si el estado es "sin_respuesta", una pregunta relacionada que los artículos del \
contexto SÍ responden (o null si no hay ninguna); si el estado es "respondida", null.

Reglas obligatorias:
1. Usa solo el texto de los artículos del contexto. No uses tu conocimiento previo sobre la LFT: \
la ley se reforma con frecuencia y tu memoria puede estar desactualizada.
2. Solo puedes citar artículos que aparezcan en el contexto. Toda afirmación de un párrafo debe \
estar respaldada por sus citas.
3. Revisa el TÍTULO y CAPÍTULO de cada artículo. Si un artículo pertenece a un régimen especial \
(por ejemplo, del TÍTULO SEXTO "Trabajos Especiales": trabajo del hogar, del campo, en \
plataformas digitales, etc.) y la pregunta no menciona ese régimen, no lo presentes como la regla \
general: da primero la regla general si está en el contexto y, si mencionas el régimen especial, \
di explícitamente a quién aplica.
4. Si la pregunta implica un cálculo (días, montos), muéstralo paso a paso a partir del texto \
de la ley.
5. Si la pregunta admite más de una interpretación (por ejemplo, "mi tercer año" puede \
significar años cumplidos o el año en curso), dilo y da la respuesta para cada caso.
6. Escribe en español, de forma clara y breve."""

USER_TEMPLATE = """Contexto (artículos de la LFT, texto vigente con última reforma DOF {fecha}):

{contexto}

Pregunta: {pregunta}"""

_CITA_SCHEMA = {
    "type": "object",
    "properties": {"articulo": {"type": "string"}, "pasaje": {"type": "string"}},
    "required": ["articulo", "pasaje"],
    "additionalProperties": False,
}
# El orden de las propiedades importa para el streaming: estado y frase llegan primero.
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "estado": {"type": "string", "enum": ["respondida", "sin_respuesta"]},
        "frase_principal": {"type": "string"},
        "parrafos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "texto": {"type": "string"},
                    "citas": {"type": "array", "items": _CITA_SCHEMA},
                },
                "required": ["texto", "citas"],
                "additionalProperties": False,
            },
        },
        "sugerencia": {"type": ["string", "null"]},
    },
    "required": ["estado", "frase_principal", "parrafos", "sugerencia"],
    "additionalProperties": False,
}
RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "respuesta_lft", "strict": True, "schema": ANSWER_SCHEMA},
}

# (Art. 76, LFT) en el texto plano derivado; también se reconocen variantes que escriben modelos.
CITATION_RE = re.compile(
    r"\(\s*Art(?:[íi]culo|\.)\s*(?P<id>\d{1,4}(?:o\.?|º)?(?:-[A-ZÑ])?(?:\s+(?:Bis|Ter|Qu[aá]ter))?)"
    r"(?:(?:\s*,\s*|\s+)(?P<detalle>[^(),]{1,40}?))?"
    r"\s*,\s*LFT\s*\)"
)

CompletionFn = Callable[[list[dict]], str]
StreamFn = Callable[[list[dict]], Iterator[str]]
Estado = Literal["respondida", "sin_respuesta"]


@dataclass
class Cita:
    articulo: str
    pasaje: str  # tal como lo escribió el modelo; se valida contra el artículo en el pipeline


@dataclass
class Parrafo:
    texto: str
    citas: list[Cita]


@dataclass
class StructuredAnswer:
    estado: Estado
    frase_principal: str
    parrafos: list[Parrafo] = field(default_factory=list)
    sugerencia: str | None = None
    citas_invalidas: list[str] = field(default_factory=list)  # artículos fuera del contexto

    @property
    def citas(self) -> list[str]:
        """Artículos citados, sin repetir, en orden de aparición."""
        return list(dict.fromkeys(c.articulo for p in self.parrafos for c in p.citas))

    def as_text(self) -> str:
        """Texto plano con citas (Art. X, LFT): para el CLI y el juez de la evaluación."""
        if self.estado == "sin_respuesta":
            return self.frase_principal
        lines = [self.frase_principal]
        for parrafo in self.parrafos:
            cites = " ".join(f"(Art. {c.articulo}, LFT)" for c in parrafo.citas)
            lines.append(f"{parrafo.texto} {cites}")
        return "\n\n".join(lines)


@dataclass
class GeneratedAnswer:
    """Resultado del generador. `respuesta` es el texto plano derivado de `estructura`."""

    estructura: StructuredAnswer
    respuesta_modelo: str = ""  # JSON crudo del LLM, antes de aplicar reglas

    @property
    def respuesta(self) -> str:
        return self.estructura.as_text()

    @property
    def citas(self) -> list[str]:
        return self.estructura.citas

    @property
    def citas_invalidas(self) -> list[str]:
        return self.estructura.citas_invalidas

    @property
    def abstencion(self) -> bool:
        return self.estructura.estado == "sin_respuesta"


def format_context(articles: list[RetrievedArticle]) -> str:
    blocks = []
    for i, article in enumerate(articles, start=1):
        location = " / ".join(part for part in (article.titulo, article.capitulo) if part)
        if article.articulo:
            label = f"Art. {article.articulo}, LFT"
        else:
            label = f"Fragmento de la LFT (contiene Arts. {', '.join(article.article_ids)})"
        blocks.append(
            f"[{i}] {label}" + (f" — {location}" if location else "") + f"\n{article.texto}"
        )
    return "\n\n".join(blocks)


def build_messages(
    question: str, articles: list[RetrievedArticle], fecha_reforma: str | None
) -> list[dict]:
    user = USER_TEMPLATE.format(
        fecha=fecha_reforma or "desconocida",
        contexto=format_context(articles) or "(sin artículos)",
        pregunta=question,
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def normalize_citation(raw_id: str) -> str:
    """'3o.' → '3', 'Art. 76' → '76', 'Quater' → 'Quáter', espacios colapsados."""
    citation = re.sub(r"^\s*art(?:[íi]culo|\.)?\s*", "", raw_id.strip(), flags=re.IGNORECASE)
    citation = re.sub(r"(\d)(?:o\.?|º)", r"\1", citation)
    citation = re.sub(r"\s+", " ", citation).strip()
    return citation.replace("Quater", "Quáter")


def extract_citations(text: str) -> list[str]:
    """Citas (Art. X, LFT) de un texto plano, sin repetir."""
    return list(dict.fromkeys(normalize_citation(m["id"]) for m in CITATION_RE.finditer(text)))


def abstention(frase: str | None = None, sugerencia: str | None = None) -> StructuredAnswer:
    return StructuredAnswer("sin_respuesta", frase or f"{ABSTENTION}.", [], sugerencia)


def filter_paragraph(raw: dict, context_ids: set[str], invalid: list[str]) -> Parrafo | None:
    """Conserva solo citas a artículos del contexto; sin cita válida, el párrafo se descarta."""
    texto = str(raw.get("texto") or "").strip()
    citas: list[Cita] = []
    for raw_cita in raw.get("citas") or []:
        articulo = normalize_citation(str(raw_cita.get("articulo") or ""))
        if articulo not in context_ids:
            if articulo and articulo not in invalid:
                invalid.append(articulo)
            continue
        if articulo not in {c.articulo for c in citas}:
            citas.append(Cita(articulo, str(raw_cita.get("pasaje") or "")))
    return Parrafo(texto, citas) if texto and citas else None


def apply_structured_rules(data: dict, context_ids: set[str]) -> StructuredAnswer:
    """Reglas del proyecto sobre la salida del modelo (no solo en el prompt)."""
    frase = str(data.get("frase_principal") or "").strip()
    sugerencia = data.get("sugerencia") or None
    if data.get("estado") != "respondida":
        return abstention(frase, sugerencia)
    invalid: list[str] = []
    parrafos = [
        p
        for p in (filter_paragraph(raw, context_ids, invalid) for raw in data.get("parrafos") or [])
        if p is not None
    ]
    if not parrafos or not frase:
        # Sin cita válida no hay respuesta: la frase del modelo no se muestra sin respaldo.
        answer = abstention()
        answer.citas_invalidas = invalid
        return answer
    return StructuredAnswer("respondida", frase, parrafos, None, invalid)


def parse_answer(raw: str, context_ids: set[str]) -> StructuredAnswer:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return abstention()
    if not isinstance(data, dict):
        return abstention()
    return apply_structured_rules(data, context_ids)


def context_ids_of(articles: list[RetrievedArticle]) -> set[str]:
    return {article_id for a in articles for article_id in a.article_ids}


def _request_kwargs(settings: Settings, messages: list[dict]) -> dict:
    kwargs: dict = {
        "model": settings.llm_model,
        "messages": messages,
        "response_format": RESPONSE_FORMAT,
    }
    if settings.llm_reasoning_effort:
        kwargs["reasoning_effort"] = settings.llm_reasoning_effort
    return kwargs


def _client(settings: Settings):
    from openai import OpenAI

    if settings.openai_api_key is None:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")
    return OpenAI(api_key=settings.openai_api_key.get_secret_value())


def openai_completion(settings: Settings) -> CompletionFn:
    client = _client(settings)

    def complete(messages: list[dict]) -> str:
        response = client.chat.completions.create(**_request_kwargs(settings, messages))
        return response.choices[0].message.content or ""

    return complete


def openai_stream(settings: Settings) -> StreamFn:
    """Devuelve los fragmentos de texto (JSON parcial) conforme llegan."""
    client = _client(settings)

    def stream(messages: list[dict]) -> Iterator[str]:
        response = client.chat.completions.create(
            **_request_kwargs(settings, messages), stream=True
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    return stream


def parse_partial(raw: str) -> dict:
    """JSON incompleto → dict con lo que ya llegó (cadenas truncadas incluidas)."""
    import jiter

    try:
        data = jiter.from_json(raw.encode(), partial_mode="trailing-strings")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def generate(
    question: str,
    articles: list[RetrievedArticle],
    settings: Settings,
    fecha_reforma: str | None = None,
    complete: CompletionFn | None = None,
) -> GeneratedAnswer:
    """Generación sin streaming (evaluación)."""
    if not articles:
        return GeneratedAnswer(abstention())
    complete = complete or openai_completion(settings)
    raw = complete(build_messages(question, articles, fecha_reforma))
    return GeneratedAnswer(parse_answer(raw, context_ids_of(articles)), raw)
