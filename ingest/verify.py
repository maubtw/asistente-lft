"""Verifica data/processed/lft.jsonl: conteos, huecos en la numeración y muestras.

Uso: uv run python -m ingest.verify [--jsonl data/processed/lft.jsonl] [--muestras 76 47 3 Bis]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ingest.parse_ley import DEFAULT_OUT, numbering_gaps


def load_articles(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize(articles: list[dict]) -> dict:
    body = [a for a in articles if not a["es_transitorio"]]
    ids = [a["articulo"] for a in body]
    duplicates = [a for a, n in Counter(ids).items() if n > 1]
    return {
        "total_registros": len(articles),
        "articulos_cuerpo": len(body),
        "vigentes": sum(not a["derogado"] for a in body),
        "derogados": sum(a["derogado"] for a in body),
        "transitorios": len(articles) - len(body),
        "con_letra_o_bis": sum(not a.isdigit() for a in ids),
        "con_referencias": sum(bool(a["referencias"]) for a in body),
        "sin_titulo": sum(a["titulo"] is None for a in body),
        "sin_capitulo": sum(a["capitulo"] is None for a in body),
        "texto_vacio": [a["articulo"] for a in body if not a["texto"].strip()],
        "duplicados": duplicates,
        "huecos": numbering_gaps(ids),
        "primero": ids[0] if ids else None,
        "ultimo": ids[-1] if ids else None,
        "fecha_reforma": articles[0]["fecha_reforma"] if articles else None,
    }


def print_article(article: dict) -> None:
    print(f"\n--- Art. {article['articulo']}, LFT ---")
    print(f"titulo:      {article['titulo']}")
    print(f"capitulo:    {article['capitulo']}")
    if article.get("seccion"):
        print(f"seccion:     {article['seccion']}")
    print(f"derogado:    {article['derogado']}")
    print(f"referencias: {article['referencias']}")
    print(f"notas:       {article.get('notas_reforma', [])}")
    print(f"texto:\n{article['texto']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--muestras", nargs="*", default=["76", "47", "3 Bis"])
    args = parser.parse_args()

    articles = load_articles(args.jsonl)
    for key, value in summarize(articles).items():
        print(f"{key:18} {value}")

    by_id = {a["articulo"]: a for a in articles if not a["es_transitorio"]}
    for sample in args.muestras:
        if sample in by_id:
            print_article(by_id[sample])
        else:
            print(f"\n(No existe el artículo {sample})")


if __name__ == "__main__":
    main()
