"""Tabla comparativa de todas las corridas en eval/results/.

Uso: uv run python -m eval.report            # todas las corridas, en orden cronológico
     uv run python -m eval.report --latest   # solo la corrida más reciente de cada config
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

RESULTS_DIR = Path("eval/results")

COLUMNS = [
    ("Config", lambda r, m: r["config"]),
    ("Hit@1", lambda r, m: _pct(m.get("hit@1"))),
    ("Hit@5", lambda r, m: _pct(m.get("hit@5"))),
    ("MRR", lambda r, m: _num(m.get("mrr"))),
    ("Recall@5", lambda r, m: _pct(m.get("recall@5"))),
    ("Recall ctx", lambda r, m: _pct(m.get("recall@ctx"))),
    ("Abstención ✓", lambda r, m: _pct(m.get("abstencion_correcta"))),
    ("Falsa abst.", lambda r, m: _pct(m.get("falsa_abstencion"))),
    ("Cita esperada", lambda r, m: _pct(m.get("cita_esperada"))),
    ("Pasajes verif.", lambda r, m: _pct(m.get("pasajes_verificables"))),
    ("Fidelidad", lambda r, m: _num(m.get("fidelidad"), 2)),
    ("Corrección", lambda r, m: _num(m.get("correccion"), 2)),
    ("Tokens ctx", lambda r, m: _num(m.get("tokens_contexto"), 0)),
    ("Latencia", lambda r, m: f"{m['latencia_ms'] / 1000:.1f} s" if m.get("latencia_ms") else "—"),
]


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def markdown_table(results: list[dict]) -> str:
    header = "| " + " | ".join(name for name, _ in COLUMNS) + " |"
    sep = "|" + "|".join("---" for _ in COLUMNS) + "|"
    rows = ["| " + " | ".join(fn(r, r["metricas"]) for _, fn in COLUMNS) + " |" for r in results]
    return "\n".join([header, sep, *rows])


def load_results(latest_only: bool) -> list[dict]:
    results = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS_DIR.glob("*.json"))
    ]
    results = [r for r in results if not r.get("parcial")]  # subconjuntos: no comparables
    results.sort(key=lambda r: r["fecha"])
    if latest_only:
        by_config = {r["config"]: r for r in results}
        results = sorted(by_config.values(), key=lambda r: r["fecha"])
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest", action="store_true")
    args = parser.parse_args()
    print(markdown_table(load_results(args.latest)))


if __name__ == "__main__":
    main()
