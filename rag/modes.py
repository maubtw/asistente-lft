"""Modos del pipeline expuestos en la API y la demo. Cada uno es una configuración medida.

- completo: la mejor configuración medida (Fase 4). Necesita el reranker (~2 GB de RAM extra).
- ligero: la mejor sin reranker; para máquinas con poca RAM.

`eval/run_eval.py` usa estos mismos diccionarios, así la demo corre exactamente lo que se midió.
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr

from rag.config import Settings, get_settings

Mode = Literal["completo", "ligero"]

MODES: dict[str, dict] = {
    "completo": {
        "chunking_strategy": "by_article",
        "use_hybrid": True,
        "use_reranker": True,
        "use_reference_expansion": True,
        "use_query_rewrite": True,
        "rerank_query": "max",
    },
    "ligero": {
        "chunking_strategy": "by_article",
        "use_hybrid": False,
        "use_reranker": False,
        "use_reference_expansion": True,
        "use_query_rewrite": True,
        "rerank_query": "original",
    },
}

MODE_DESCRIPTIONS: dict[str, str] = {
    "completo": "Híbrida + reranker + referencias + reescritura. Mejor calidad, ~10–15 s.",
    "ligero": "Vectorial + referencias + reescritura. Sin reranker (menos RAM), ~7 s.",
}


def settings_for_mode(
    mode: Mode, api_key: str | None = None, base: Settings | None = None
) -> Settings:
    """Configuración para un modo; `api_key` (opcional) reemplaza la del `.env` solo en esta
    petición, nunca se guarda."""
    update: dict = dict(MODES[mode])
    if api_key:
        update["openai_api_key"] = SecretStr(api_key)
    return (base or get_settings()).model_copy(update=update)
