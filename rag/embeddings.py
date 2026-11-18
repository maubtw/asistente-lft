"""Carga del modelo de embeddings (bge-m3), compartido por la ingesta y el retriever."""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING, Any, TypeVar

import numpy as np

# bge-m3 y bge-reranker son públicos: no enviar un token guardado (si caducó, HF responde 401).
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
# El cliente Xet de HF falló dos veces en macOS dejando enlaces rotos sin error; HTTP es estable.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

T = TypeVar("T")

MAX_SEQ_LENGTH = 1024  # los chunks están acotados a ~800 tokens; limita memoria y latencia


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_local_first(factory: Callable[..., T], model_name: str, **kwargs: Any) -> T:
    """Carga el modelo desde el caché local sin tocar la red; solo si falta, lo descarga.

    Con red, `huggingface_hub` consulta si hay versiones nuevas en cada carga, y una vez esa
    petición se quedó colgada 20 minutos sin timeout. Los modelos del proyecto no cambian.
    """
    try:
        return factory(model_name, local_files_only=True, **kwargs)
    except OSError:
        return factory(model_name, **kwargs)


@lru_cache(maxsize=2)
def load_embedding_model(model_name: str) -> SentenceTransformer:
    from sentence_transformers import SentenceTransformer

    model = load_local_first(SentenceTransformer, model_name, device=pick_device())
    model.max_seq_length = MAX_SEQ_LENGTH
    return model


def embed_texts(
    texts: list[str], model_name: str, batch_size: int = 16, show_progress: bool = False
) -> np.ndarray:
    """Embeddings normalizados (L2), listos para distancia coseno en pgvector."""
    model = load_embedding_model(model_name)
    return model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=show_progress,
        convert_to_numpy=True,
    )
