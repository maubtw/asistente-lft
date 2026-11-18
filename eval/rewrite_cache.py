"""Caché en disco de reescrituras de consulta para la evaluación.

- Ahorra llamadas a la API: una pregunta se reescribe una sola vez por (modelo, prompt).
- Hace la recuperación determinista entre corridas: comparar dos configuraciones con la misma
  reescritura aísla el efecto del cambio que se está midiendo.

La clave incluye un hash del prompt de reescritura: si el prompt cambia, se vuelve a reescribir.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rag.config import Settings
from rag.query_rewrite import REWRITE_SYSTEM, CompletionFn, openai_rewriter

CACHE_PATH = Path("eval/cache/rewrites.json")


def cache_key(question: str, settings: Settings) -> str:
    prompt_hash = hashlib.sha1(REWRITE_SYSTEM.encode()).hexdigest()[:8]
    model = settings.rewrite_model or settings.llm_model
    return f"{model}|{settings.rewrite_reasoning_effort}|{prompt_hash}|{question}"


def load_cache(path: Path = CACHE_PATH) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_cache(cache: dict[str, str], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")


class CachedRewriter:
    """`CompletionFn` que consulta la caché antes de llamar al LLM."""

    def __init__(self, settings: Settings, path: Path = CACHE_PATH) -> None:
        self.settings = settings
        self.path = path
        self.cache = load_cache(path)
        self.hits = 0
        self.calls = 0
        self._llm: CompletionFn | None = None

    def __call__(self, messages: list[dict]) -> str:
        question = messages[-1]["content"]
        key = cache_key(question, self.settings)
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        if self._llm is None:
            self._llm = openai_rewriter(self.settings)
        self.calls += 1
        self.cache[key] = self._llm(messages)
        save_cache(self.cache, self.path)
        return self.cache[key]
