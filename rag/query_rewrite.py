"""Reescritura de consulta: lenguaje coloquial → términos que usaría la propia LFT.

"Me corrieron sin darme razón" y "rescisión de la relación de trabajo sin causa justificada"
significan lo mismo, pero comparten pocas palabras y el embedding no siempre los acerca. La
reescritura genera una segunda consulta en lenguaje jurídico; el retriever busca con ambas y las
fusiona con RRF (la original nunca se descarta).

Reglas del prompt, deliberadas:
- Sin ejemplos ni listas de vocabulario: escribirlos sería filtrar las respuestas del set de
  evaluación ("despido" → "rescisión" es exactamente lo que se mide).
- Sin números de artículo: el modelo no debe usar su memoria de la LFT (puede estar desactualizada).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from rag.config import Settings

REWRITE_SYSTEM = """Reescribes preguntas de personas trabajadoras en México para buscarlas en el \
texto de la Ley Federal del Trabajo.

Devuelve UNA sola línea (10 a 35 palabras) con la misma pregunta expresada con los términos \
técnicos que emplearía la propia ley, incluyendo sinónimos jurídicos relevantes.
- No respondas la pregunta.
- No menciones números de artículo ni cifras que no estén en la pregunta.
- No agregues temas que la pregunta no plantea.
- Escribe solo la línea, sin comillas ni explicaciones."""

CompletionFn = Callable[[list[dict]], str]


def build_rewrite_messages(question: str) -> list[dict]:
    return [
        {"role": "system", "content": REWRITE_SYSTEM},
        {"role": "user", "content": question},
    ]


def clean_rewrite(raw: str, question: str) -> str:
    """Primera línea no vacía, sin comillas ni prefijos. Si sale vacía, se usa la original."""
    lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
    if not lines:
        return question
    text = re.sub(r"^(?:consulta|reescritura|pregunta)\s*:\s*", "", lines[0], flags=re.IGNORECASE)
    return text.strip(" \"'“”«»") or question


def openai_rewriter(settings: Settings) -> CompletionFn:
    from openai import OpenAI

    if settings.openai_api_key is None:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")
    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    def complete(messages: list[dict]) -> str:
        kwargs: dict = {"model": settings.rewrite_model or settings.llm_model, "messages": messages}
        if settings.rewrite_reasoning_effort:
            kwargs["reasoning_effort"] = settings.rewrite_reasoning_effort
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    return complete


def rewrite_query(question: str, settings: Settings, complete: CompletionFn | None = None) -> str:
    complete = complete or openai_rewriter(settings)
    return clean_rewrite(complete(build_rewrite_messages(question)), question)


def retrieval_queries(
    question: str, settings: Settings, complete: CompletionFn | None = None
) -> list[str]:
    """Consultas con las que se busca: la original y, si USE_QUERY_REWRITE, la reescrita."""
    if not settings.use_query_rewrite:
        return [question]
    rewritten = rewrite_query(question, settings, complete)
    return [question] if rewritten.lower() == question.lower() else [question, rewritten]
