"""LLM como juez (escala 1–5): fidelidad al contexto y corrección frente a la referencia."""

from __future__ import annotations

import json
from collections.abc import Callable

from rag.config import Settings

JUDGE_SYSTEM = """Eres un evaluador estricto de respuestas sobre la Ley Federal del Trabajo de \
México. Calificas con enteros del 1 al 5 y respondes SOLO con JSON válido."""

JUDGE_TEMPLATE = """Pregunta del usuario:
{pregunta}

Artículos que el sistema recuperó y le dio al modelo (CONTEXTO):
{contexto}

Artículos de referencia que contienen la respuesta correcta (REFERENCIA):
{referencia}

Respuesta del sistema:
{respuesta}

Califica:
- "fidelidad": ¿cada afirmación de la respuesta está respaldada por el CONTEXTO?
  5 = todo respaldado; 3 = alguna afirmación sin respaldo menor; 1 = inventa o contradice.
- "correccion": ¿la respuesta contesta correcta y completamente la pregunta según la REFERENCIA?
  5 = correcta y completa; 3 = parcialmente correcta o incompleta; 1 = incorrecta o no responde.
  Revisa los cálculos (días, porcentajes, plazos) contra el texto de la REFERENCIA.

Responde exactamente: {{"fidelidad": <1-5>, "correccion": <1-5>, "justificacion": "<una frase>"}}"""

JudgeFn = Callable[[list[dict]], str]


def build_judge_messages(pregunta: str, contexto: str, referencia: str, respuesta: str) -> list:
    user = JUDGE_TEMPLATE.format(
        pregunta=pregunta, contexto=contexto, referencia=referencia, respuesta=respuesta
    )
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]


def parse_judgement(raw: str) -> dict:
    """Extrae el JSON del juez; si no es válido, devuelve None en las calificaciones."""
    start, end = raw.find("{"), raw.rfind("}")
    try:
        data = json.loads(raw[start : end + 1])
        return {
            "fidelidad": _score(data.get("fidelidad")),
            "correccion": _score(data.get("correccion")),
            "justificacion": str(data.get("justificacion", "")),
        }
    except (ValueError, TypeError):
        return {"fidelidad": None, "correccion": None, "justificacion": f"JSON inválido: {raw!r}"}


def _score(value: object) -> int | None:
    try:
        score = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return score if 1 <= score <= 5 else None


def openai_judge(settings: Settings) -> JudgeFn:
    from openai import OpenAI

    if settings.openai_api_key is None:
        raise RuntimeError("Falta OPENAI_API_KEY en .env")
    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    def judge(messages: list[dict]) -> str:
        kwargs: dict = {
            "model": settings.judge_model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if settings.llm_reasoning_effort:
            kwargs["reasoning_effort"] = settings.llm_reasoning_effort
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    return judge
