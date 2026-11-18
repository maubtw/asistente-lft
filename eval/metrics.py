"""Métricas de evaluación (funciones puras, testeadas en tests/test_metrics.py).

Recuperación: se evalúa sobre las *unidades* que llegan al generador (top-k). Con chunking por
artículo una unidad es un artículo; con chunks fijos una unidad puede contener varios artículos.
El rango de un artículo esperado es la posición de la primera unidad que lo contiene.
"""

from __future__ import annotations

from statistics import mean


def first_relevant_rank(units: list[list[str]], expected: list[str]) -> int | None:
    """Posición (1-based) de la primera unidad que contiene algún artículo esperado."""
    targets = set(expected)
    for rank, unit in enumerate(units, start=1):
        if targets.intersection(unit):
            return rank
    return None


def hit_at_k(rank: int | None, k: int) -> float:
    return 1.0 if rank is not None and rank <= k else 0.0


def reciprocal_rank(rank: int | None) -> float:
    return 1.0 / rank if rank else 0.0


def recall_at_k(units: list[list[str]], expected: list[str], k: int) -> float:
    """Fracción de los artículos esperados que aparecen en las primeras k unidades."""
    if not expected:
        return 0.0
    found = {article for unit in units[:k] for article in unit}
    return len(set(expected) & found) / len(set(expected))


def retrieval_metrics(units: list[list[str]], expected: list[str], k: int) -> dict:
    """Métricas de ranking sobre el top-k y de cobertura sobre todo el contexto.

    Con expansión de referencias el contexto puede traer más de k unidades (las referidas van
    después del top-k): `hit@ctx` / `recall@ctx` miden lo que efectivamente ve el generador.
    """
    rank = first_relevant_rank(units[:k], expected)
    return {
        "rank": rank,
        "hit@1": hit_at_k(rank, 1),
        f"hit@{k}": hit_at_k(rank, k),
        "rr": reciprocal_rank(rank),
        f"recall@{k}": recall_at_k(units, expected, k),
        "hit@ctx": hit_at_k(first_relevant_rank(units, expected), len(units)),
        "recall@ctx": recall_at_k(units, expected, len(units)),
    }


def passage_metrics(methods: list[str]) -> dict:
    """% de pasajes verificables (exacto + normalizado + difuso) y desglose por método."""
    if not methods:
        return {"pasajes_verificables": None, "pasajes_exactos": None, "n_pasajes": 0}
    verifiable = [m for m in methods if m != "no_verificable"]
    return {
        "pasajes_verificables": round(len(verifiable) / len(methods), 4),
        "pasajes_exactos": round(methods.count("exacto") / len(methods), 4),
        "n_pasajes": len(methods),
    }


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def aggregate(results: list[dict], k: int) -> dict:
    """Resume los resultados por pregunta. Ver docstring de cada métrica en docs/decisiones.md.

    Cada resultado trae: debe_responder, retrieval (de `retrieval_metrics`), abstencion,
    cita_valida_modelo, cita_esperada, fidelidad, correccion, latencias_ms, tokens_contexto.
    """
    answerable = [r for r in results if r["debe_responder"]]
    out_of_scope = [r for r in results if not r["debe_responder"]]
    answered = [r for r in answerable if not r["abstencion"]]

    return {
        "n_preguntas": len(results),
        "hit@1": _avg([r["retrieval"]["hit@1"] for r in answerable]),
        f"hit@{k}": _avg([r["retrieval"][f"hit@{k}"] for r in answerable]),
        "mrr": _avg([r["retrieval"]["rr"] for r in answerable]),
        f"recall@{k}": _avg([r["retrieval"][f"recall@{k}"] for r in answerable]),
        "hit@ctx": _avg([r["retrieval"].get("hit@ctx", 0.0) for r in answerable]),
        "recall@ctx": _avg([r["retrieval"].get("recall@ctx", 0.0) for r in answerable]),
        # % de preguntas fuera de alcance que el sistema rechazó
        "abstencion_correcta": _avg([float(r["abstencion"]) for r in out_of_scope]),
        # % de preguntas con respuesta en la ley que el sistema rechazó (no debería)
        "falsa_abstencion": _avg([float(r["abstencion"]) for r in answerable]),
        # % de respuestas crudas del modelo (no abstenciones) con al menos una cita válida
        "cita_valida": _avg(
            [float(r["cita_valida_modelo"]) for r in results if r["cita_valida_modelo"] is not None]
        ),
        # % de preguntas respondibles cuya respuesta cita al menos un artículo esperado
        "cita_esperada": _avg([float(r["cita_esperada"]) for r in answerable]),
        # % de pasajes citados que son texto literal del artículo (resaltables en el frontend)
        **passage_metrics([m for r in results for m in r.get("pasajes", [])]),
        "fidelidad": _avg([r["fidelidad"] for r in answered if r["fidelidad"] is not None]),
        "correccion": _avg([r["correccion"] for r in answerable if r["correccion"] is not None]),
        "latencia_ms": _avg([r["latencias_ms"]["total"] for r in results]),
        "tokens_contexto": _avg([r["tokens_contexto"] for r in results]),
    }
