"""Configuración del pipeline, leída de `.env`.

Cada variante del pipeline se activa con un flag para poder compararlas en `eval/run_eval.py`.
Para una corrida con otra configuración sin tocar el `.env`:

    settings = get_settings().model_copy(update={"use_hybrid": True})
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ChunkingStrategy = Literal["by_article", "fixed_chunks"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM (OpenAI) ---
    openai_api_key: SecretStr | None = None
    llm_model: str = "gpt-5-mini"
    judge_model: str = "gpt-5-mini"
    # Solo para modelos de razonamiento (gpt-5*, o*): "minimal" | "low" | "medium" | "high".
    # Vacío = no se envía el parámetro (necesario para modelos como gpt-4.1).
    llm_reasoning_effort: str | None = None
    # Reescritura de consulta: por defecto el mismo modelo, con el mínimo razonamiento (es una
    # paráfrasis, no un análisis). Vacío = no se envía el parámetro.
    rewrite_model: str | None = None
    rewrite_reasoning_effort: str | None = "minimal"
    # Con qué consulta puntúa el reranker si hay reescritura. "original" = intención del usuario;
    # "rewrite" = consulta en términos de la ley (el cross-encoder no sabe que "PTU" es
    # "participación de los trabajadores en las utilidades"); "max" = el mejor puntaje de las dos
    # (la reescritura puede desviarse del tema: q13 en docs/decisiones.md).
    rerank_query: Literal["original", "rewrite", "max"] = "original"

    # --- Base de datos ---
    database_url: str = "postgresql://lft:lft@localhost:5432/lft"

    # --- Modelos locales ---
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    embedding_batch_size: int = 16
    # Artículos más largos que esto (tokens) se parten en varios chunks (p. ej. Art. 513).
    max_chunk_tokens: int = 800

    # --- Flags del pipeline ---
    chunking_strategy: ChunkingStrategy = "by_article"
    use_hybrid: bool = False  # Fase 4: vectorial + full-text 'spanish' con RRF
    use_reranker: bool = False  # Fase 4: cross-encoder sobre `retrieve_k` candidatos
    use_reference_expansion: bool = False  # Fase 4: traer artículos referidos (profundidad 1)
    use_query_rewrite: bool = False  # Fase 4: lenguaje coloquial → términos de la ley

    # --- Parámetros de recuperación ---
    top_k: int = 5  # artículos que llegan al generador
    retrieve_k: int = 20  # candidatos antes de reranker / fusión
    rrf_k: int = 60  # constante de Reciprocal Rank Fusion
    # Ranking léxico: "idf" = suma del IDF de los términos que coinciden (estilo BM25 sin tf);
    # "ts_rank" = ranking nativo de Postgres (no usa IDF).
    lexical_ranking: Literal["idf", "ts_rank"] = "idf"
    max_reference_articles: int = 3  # tope de artículos extra por expansión de referencias
    hnsw_ef_search: int = 100

    @property
    def config_name(self) -> str:
        """Nombre legible de la combinación de flags, para resultados de evaluación."""
        parts = [self.chunking_strategy]
        flags = {
            "hybrid": self.use_hybrid,
            "rerank": self.use_reranker,
            "refs": self.use_reference_expansion,
            "rewrite": self.use_query_rewrite,
            f"rerank_{self.rerank_query}": self.use_reranker
            and self.use_query_rewrite
            and self.rerank_query != "original",
        }
        parts += [name for name, enabled in flags.items() if enabled]
        return "+".join(parts)


@lru_cache
def get_settings() -> Settings:
    return Settings()
