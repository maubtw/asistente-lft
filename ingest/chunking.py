"""Estrategias de chunking. Cada una produce `Chunk`s que `ingest/embed.py` carga a Postgres."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken


@dataclass
class Chunk:
    texto: str
    articulo: str | None
    titulo: str | None = None
    capitulo: str | None = None
    referencias: list[str] = field(default_factory=list)
    articulos_en_chunk: list[str] = field(default_factory=list)
    derogado: bool = False
    es_transitorio: bool = False
    fecha_reforma: str | None = None
    embeddable: bool = True  # derogados y transitorios se guardan sin embedding
    with_header: bool = True  # False en chunks fijos: se vectorizan tal cual

    def embedding_text(self) -> str:
        """Texto que se vectoriza: incluye artículo y jerarquía para dar contexto semántico.

        Los chunks fijos se vectorizan tal cual (son la línea base sin estructura).
        """
        if not self.with_header or self.articulo is None:
            return self.texto
        header = " — ".join(
            part for part in (f"Artículo {self.articulo}", self.titulo, self.capitulo) if part
        )
        return f"{header}\n{self.texto}" if self.articulo else self.texto


@lru_cache
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


def split_long_text(text: str, max_tokens: int) -> list[str]:
    """Parte por párrafos sin pasar de `max_tokens`; un párrafo gigante se corta por tokens."""
    parts: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for paragraph in text.split("\n"):
        tokens = count_tokens(paragraph)
        if tokens > max_tokens:
            if current:
                parts.append("\n".join(current))
                current, current_tokens = [], 0
            encoded = _encoder().encode(paragraph)
            parts += [
                _encoder().decode(encoded[i : i + max_tokens])
                for i in range(0, len(encoded), max_tokens)
            ]
            continue
        if current and current_tokens + tokens > max_tokens:
            parts.append("\n".join(current))
            current, current_tokens = [], 0
        current.append(paragraph)
        current_tokens += tokens
    if current:
        parts.append("\n".join(current))
    return parts


def chunks_by_article(articles: list[dict], max_tokens: int) -> list[Chunk]:
    """Un chunk por artículo. Los muy largos (Art. 513, tablas) se parten conservando el ID."""
    chunks: list[Chunk] = []
    for article in articles:
        embeddable = not article["derogado"] and not article["es_transitorio"]
        texts = split_long_text(article["texto"], max_tokens) if embeddable else [article["texto"]]
        for text in texts:
            chunks.append(
                Chunk(
                    texto=text,
                    articulo=article["articulo"],
                    titulo=article["titulo"],
                    capitulo=article["capitulo"],
                    referencias=article["referencias"],
                    articulos_en_chunk=[article["articulo"]],
                    derogado=article["derogado"],
                    es_transitorio=article["es_transitorio"],
                    fecha_reforma=article["fecha_reforma"],
                    embeddable=embeddable,
                )
            )
    return chunks


FIXED_CHUNK_TOKENS = 500
FIXED_CHUNK_OVERLAP = 50


def chunks_fixed(
    articles: list[dict], size: int = FIXED_CHUNK_TOKENS, overlap: int = FIXED_CHUNK_OVERLAP
) -> list[Chunk]:
    """Línea base "ingenua": la ley vigente como un solo texto, en ventanas de `size` tokens.

    Cada artículo se antepone con "Artículo X.-" (como en el PDF) para que el LLM pueda citarlo.
    `articulos_en_chunk` registra qué artículos toca cada ventana, para medir la recuperación.
    """
    encoder = _encoder()
    tokens: list[int] = []
    spans: list[tuple[int, int, dict]] = []
    for article in articles:
        if article["derogado"] or article["es_transitorio"]:
            continue
        encoded = encoder.encode(f"Artículo {article['articulo']}.- {article['texto']}\n\n")
        spans.append((len(tokens), len(tokens) + len(encoded), article))
        tokens.extend(encoded)

    chunks: list[Chunk] = []
    step = size - overlap
    for start in range(0, len(tokens), step):
        end = min(start + size, len(tokens))
        inside = [a for s, e, a in spans if s < end and e > start]
        ids = [a["articulo"] for a in inside]
        chunks.append(
            Chunk(
                texto=encoder.decode(tokens[start:end]).strip(),
                articulo=ids[0] if len(ids) == 1 else None,
                titulo=inside[0]["titulo"],
                capitulo=inside[0]["capitulo"],
                articulos_en_chunk=ids,
                fecha_reforma=inside[0]["fecha_reforma"],
                with_header=False,
            )
        )
        if end == len(tokens):
            break
    return chunks


def build_chunks(articles: list[dict], strategy: str, max_tokens: int) -> list[Chunk]:
    if strategy == "by_article":
        return chunks_by_article(articles, max_tokens)
    if strategy == "fixed_chunks":
        return chunks_fixed(articles)
    raise ValueError(f"Estrategia de chunking desconocida: {strategy}")
