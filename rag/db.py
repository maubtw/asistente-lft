"""Conexión a Postgres con soporte de pgvector."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row


@contextmanager
def connect(database_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        register_vector(conn)
        yield conn


def latest_reform_date(conn: psycopg.Connection, ley: str = "LFT") -> str | None:
    row = conn.execute(
        "SELECT max(fecha_reforma) AS fecha FROM articulos WHERE ley = %s", (ley,)
    ).fetchone()
    return row["fecha"].isoformat() if row and row["fecha"] else None


def fetch_articles(conn: psycopg.Connection, article_ids: list[str]) -> dict[str, dict]:
    """Texto completo por artículo (une los chunks de artículos largos, p. ej. el 513)."""
    if not article_ids:
        return {}
    rows = conn.execute(
        """
        SELECT articulo, min(titulo) AS titulo, min(capitulo) AS capitulo,
               string_agg(texto, E'\\n' ORDER BY id) AS texto, bool_or(derogado) AS derogado,
               max(referencias) AS referencias  -- iguales en todos los chunks
        FROM articulos
        WHERE estrategia = 'by_article' AND ley = 'LFT' AND NOT es_transitorio
          AND articulo = ANY(%s)
        GROUP BY articulo
        """,
        (article_ids,),
    ).fetchall()
    return {row["articulo"]: row for row in rows}


def get_article(conn: psycopg.Connection, article_id: str) -> dict | None:
    """Un artículo completo (incluye derogados y transitorios), para GET /articulo/{id}."""
    return conn.execute(
        """
        SELECT articulo, min(titulo) AS titulo, min(capitulo) AS capitulo,
               string_agg(texto, E'\\n' ORDER BY id) AS texto,
               max(referencias) AS referencias,  -- iguales en todos los chunks
               bool_or(derogado) AS derogado, bool_or(es_transitorio) AS es_transitorio,
               max(fecha_reforma) AS fecha_reforma
        FROM articulos
        WHERE estrategia = 'by_article' AND ley = 'LFT' AND articulo = %s
        GROUP BY articulo
        """,
        (article_id,),
    ).fetchone()


def database_stats(conn: psycopg.Connection) -> dict:
    return conn.execute(
        """
        SELECT count(DISTINCT articulo) FILTER (WHERE NOT derogado AND NOT es_transitorio)
                   AS articulos_vigentes,
               max(fecha_reforma) AS fecha_reforma
        FROM articulos WHERE estrategia = 'by_article' AND ley = 'LFT'
        """
    ).fetchone()
