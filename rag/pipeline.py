"""Pipeline de punta a punta: pregunta → artículos → respuesta estructurada con pasajes.

El pipeline es un generador de eventos (`answer_events`). Un solo camino de código para:
- `POST /ask/stream` (SSE): reenvía cada evento conforme ocurre;
- `POST /ask` y el CLI: consumen los eventos y devuelven el último (`fin`);
- los tests: inyectan funciones falsas de LLM y de base de datos.

Eventos: etapa → articulos → etapa(generacion) → frase → parrafo* → fin  (o `error` en la API).

Uso: uv run python -m rag.pipeline "¿Cuántos días de vacaciones me tocan en mi tercer año?"
     uv run python -m rag.pipeline "..." --debug     # recuperación, verificación y latencias
     uv run python -m rag.pipeline "..." --json      # el contrato JSON completo
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from rag.config import Settings, get_settings
from rag.db import connect, fetch_articles, latest_reform_date
from rag.generator import (
    Parrafo,
    StreamFn,
    StructuredAnswer,
    abstention,
    apply_structured_rules,
    build_messages,
    context_ids_of,
    filter_paragraph,
    openai_stream,
    parse_partial,
)
from rag.passages import validate_passage
from rag.query_rewrite import CompletionFn as RewriteFn
from rag.query_rewrite import retrieval_queries
from rag.retriever import RetrievedArticle, retrieve_steps

AVISO_LEGAL = "Información orientativa. No sustituye asesoría legal profesional."

# Más largos que esto (p. ej. Art. 513, tablas: ~313k caracteres) se envían solo con los chunks
# que vio el modelo, marcados con `texto_parcial`.
MAX_ARTICLE_CHARS = 20_000

STAGE_MESSAGES = {
    "reescritura": "Reescribiendo tu pregunta…",
    "busqueda": "Buscando en la ley…",
    "reranker": "Reordenando artículos…",
    "referencias": "Revisando artículos relacionados…",
    "generacion": "Redactando la respuesta…",
}

FetchFn = Callable[[list[str]], dict[str, dict]]
Event = dict  # {"event": str, "data": dict}

_HEADING_RE = re.compile(
    r"^(?P<kind>T[ÍI]TULO|CAP[ÍI]TULO)\s+(?P<num>[A-ZÁÉÍÓÚ]+(?:\s+(?:BIS|TER|QU[AÁ]TER))?)"
    r"(?:\s+(?P<name>.+))?$"
)


def format_heading(heading: str | None) -> str | None:
    """'TÍTULO TERCERO Condiciones de Trabajo' → 'Título tercero, Condiciones de Trabajo';
    'CAPÍTULO III BIS De la Productividad…' → 'Capítulo III Bis, De la Productividad…'.

    El nombre oficial se conserva; solo se pasa a oración si viene todo en mayúsculas.
    """
    if not heading:
        return None
    match = _HEADING_RE.match(heading.strip())
    if not match:
        return heading
    is_title = match["kind"].upper().startswith("T")
    words = match["num"].split()
    if is_title:  # ordinales en palabras: "TERCERO", "QUINTO BIS"
        number = " ".join(w.lower() for w in words)
    else:  # romanos: "III BIS" → "III Bis"
        number = " ".join([words[0], *(w.capitalize() for w in words[1:])])
    label = f"{'Título' if is_title else 'Capítulo'} {number}"
    name = match["name"]
    if name and name.isupper():
        name = name.capitalize()
    return f"{label}, {name}" if name else label


def db_fetch(settings: Settings) -> FetchFn:
    def fetch(ids: list[str]) -> dict[str, dict]:
        with connect(settings.database_url) as conn:
            return fetch_articles(conn, ids)

    return fetch


@dataclass
class ArticleStore:
    """Textos de los artículos citados, tal como se envían en `articulos` (y contra los que se
    valida cada pasaje: un pasaje es válido si es subcadena de *ese* texto)."""

    fetch: FetchFn
    retrieved: list[RetrievedArticle]
    cache: dict[str, dict] = field(default_factory=dict)

    def get(self, ids: list[str]) -> dict[str, dict]:
        missing = [i for i in ids if i not in self.cache]
        if missing:
            for article_id, row in self.fetch(missing).items():
                self.cache[article_id] = self._entry(article_id, row)
        return {i: self.cache[i] for i in ids if i in self.cache}

    def _entry(self, article_id: str, row: dict) -> dict:
        texto = row["texto"]
        parcial = len(texto) > MAX_ARTICLE_CHARS
        if parcial:  # solo lo que vio el modelo: los pasajes salen de ahí
            seen = [a.texto for a in self.retrieved if a.articulo == article_id]
            texto = "\n".join(seen) or texto[:MAX_ARTICLE_CHARS]
        entry = {
            "titulo": format_heading(row.get("titulo")),
            "capitulo": format_heading(row.get("capitulo")),
            "texto": texto,
            "referencias": list(row.get("referencias") or []),
        }
        if parcial:
            entry["texto_parcial"] = True
        return entry


def validate_paragraph(parrafo: Parrafo, store: ArticleStore) -> tuple[dict, list[dict]]:
    """Párrafo del contrato con pasajes literales + detalle de la verificación de cada cita."""
    articles = store.get([c.articulo for c in parrafo.citas])
    citas, checks = [], []
    for cita in parrafo.citas:
        texto = articles.get(cita.articulo, {}).get("texto", "")
        match = validate_passage(cita.pasaje, texto)
        citas.append({"articulo": cita.articulo, "pasaje": match.pasaje})
        checks.append(
            {"articulo": cita.articulo, "metodo": match.metodo, "pasaje_modelo": cita.pasaje}
        )
    return {"texto": parrafo.texto, "citas": citas}, checks


def build_contract(
    answer: StructuredAnswer, store: ArticleStore, fecha: str | None
) -> tuple[dict, list[dict]]:
    """El JSON de respuesta de la API (ver `AskResponse` en api/main.py)."""
    parrafos, checks = [], []
    for parrafo in answer.parrafos:
        contract_paragraph, paragraph_checks = validate_paragraph(parrafo, store)
        parrafos.append(contract_paragraph)
        checks += paragraph_checks
    contract = {
        "estado": answer.estado,
        "frase_principal": answer.frase_principal,
        "parrafos": parrafos,
        "sugerencia": answer.sugerencia,
        "articulos": store.get(answer.citas),
        "fecha_reforma": fecha,
    }
    return contract, checks


def _reform_date(articles: list[RetrievedArticle], settings: Settings) -> str | None:
    dates = [a.fecha_reforma for a in articles if a.fecha_reforma]
    if dates:
        return max(dates)
    with connect(settings.database_url) as conn:
        return latest_reform_date(conn)


def _event(name: str, **data) -> Event:
    return {"event": name, "data": data}


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _stream_answer(
    raw_chunks: Iterator[str], context_ids: set[str], store: ArticleStore
) -> Iterator[Event | str]:
    """Lee el JSON parcial del modelo: emite la frase y cada párrafo en cuanto está completo
    (ya filtrado y con pasajes validados). Al final emite el JSON crudo completo (str)."""
    raw = ""
    frase_sent = False
    paragraphs_seen = 0  # párrafos crudos ya procesados
    paragraphs_sent = 0
    for chunk in raw_chunks:
        raw += chunk
        partial = parse_partial(raw)
        if partial.get("estado") != "respondida":
            continue
        if not frase_sent and "parrafos" in partial and partial.get("frase_principal"):
            frase_sent = True  # "parrafos" ya empezó: la frase está completa
            yield _event("frase", frase_principal=partial["frase_principal"].strip())
        complete = partial.get("parrafos", [])[:-1]  # el último puede seguir llegando
        for raw_paragraph in complete[paragraphs_seen:]:
            event = _paragraph_event(raw_paragraph, context_ids, store, paragraphs_sent)
            if event is not None:
                yield event
                paragraphs_sent += 1
        paragraphs_seen = max(paragraphs_seen, len(complete))

    # Fin del stream: el último párrafo ya está completo.
    final = parse_partial(raw)
    if final.get("estado") == "respondida":
        if not frase_sent and final.get("frase_principal"):
            yield _event("frase", frase_principal=final["frase_principal"].strip())
        for raw_paragraph in final.get("parrafos", [])[paragraphs_seen:]:
            event = _paragraph_event(raw_paragraph, context_ids, store, paragraphs_sent)
            if event is not None:
                yield event
                paragraphs_sent += 1
    yield raw


def _paragraph_event(
    raw_paragraph: dict, context_ids: set[str], store: ArticleStore, indice: int
) -> Event | None:
    parrafo = filter_paragraph(raw_paragraph, context_ids, [])
    if parrafo is None:
        return None
    data, _ = validate_paragraph(parrafo, store)
    return _event("parrafo", indice=indice, **data)


def answer_events(
    question: str,
    settings: Settings | None = None,
    stream: StreamFn | None = None,
    rewriter: RewriteFn | None = None,
    fetch: FetchFn | None = None,
) -> Iterator[Event]:
    """Eventos del pipeline. El último es `fin` con el contrato completo + bloque `debug`."""
    settings = settings or get_settings()
    t_start = time.perf_counter()
    latencies: dict[str, int] = {}

    if settings.use_query_rewrite:
        yield _event("etapa", etapa="reescritura", mensaje=STAGE_MESSAGES["reescritura"])
    t0 = time.perf_counter()
    queries = retrieval_queries(question, settings, rewriter)
    if settings.use_query_rewrite:
        latencies["reescritura"] = _ms(t0)

    steps = retrieve_steps(question, settings, queries=queries, timings=latencies)
    while True:
        try:
            stage = next(steps)
        except StopIteration as done:
            articles: list[RetrievedArticle] = done.value
            break
        yield _event("etapa", etapa=stage, mensaje=STAGE_MESSAGES[stage])
    yield _event("articulos", ids=list(dict.fromkeys(i for a in articles for i in a.article_ids)))

    fecha = _reform_date(articles, settings)
    store = ArticleStore(fetch or db_fetch(settings), articles)
    context_ids = context_ids_of(articles)

    yield _event("etapa", etapa="generacion", mensaje=STAGE_MESSAGES["generacion"])
    t1 = time.perf_counter()
    raw = ""
    if articles:
        stream = stream or openai_stream(settings)
        for item in _stream_answer(
            stream(build_messages(question, articles, fecha)), context_ids, store
        ):
            if isinstance(item, str):
                raw = item
            else:
                yield item
    try:
        final = apply_structured_rules(json.loads(raw), context_ids) if raw else abstention()
    except ValueError:
        final = abstention()
    latencies["generacion"] = _ms(t1)
    latencies["total"] = _ms(t_start)

    contract, checks = build_contract(final, store, fecha)
    contract["debug"] = {
        "config": settings.config_name,
        "consulta_reescrita": queries[1] if len(queries) > 1 else None,
        "recuperados": [
            {
                "articulo": a.articulo,
                "articulos": a.article_ids,
                "titulo": a.titulo,
                "capitulo": a.capitulo,
                "score": round(a.score, 4),
                "fuente": a.fuente,
                "ranks": a.ranks,
            }
            for a in articles
        ],
        "verificacion": checks,
        "citas_invalidas": final.citas_invalidas,
        "respuesta_texto": final.as_text(),
        "respuesta_modelo": raw,
        "latencias_ms": latencies,
    }
    yield _event("fin", **contract)


def answer(question: str, settings: Settings | None = None, **kwargs) -> dict:
    """Contrato completo (con bloque `debug`) sin streaming."""
    final: dict = {}
    for event in answer_events(question, settings, **kwargs):
        if event["event"] == "fin":
            final = event["data"]
    return final


def _print_human(result: dict, debug: bool) -> None:
    print(f"\n{result['frase_principal']}\n")
    for parrafo in result["parrafos"]:
        cites = ", ".join(f"Art. {c['articulo']}" for c in parrafo["citas"])
        print(f"{parrafo['texto']}  [{cites}]\n")
    if result["estado"] == "sin_respuesta" and result.get("sugerencia"):
        print(f"Sugerencia: {result['sugerencia']}\n")
    for article_id, article in result["articulos"].items():
        print(f"  • Art. {article_id} — {article['capitulo'] or article['titulo']}")
    print(f"\nTexto vigente: última reforma DOF {result['fecha_reforma']}")
    print(f"⚠️  {AVISO_LEGAL}")
    if not debug:
        return
    info = result["debug"]
    print(f"\n[debug] config: {info['config']}")
    if info["consulta_reescrita"]:
        print(f"[debug] consulta reescrita: {info['consulta_reescrita']}")
    print("[debug] recuperados:")
    for r in info["recuperados"]:
        label = r["articulo"] or "fragmento " + ", ".join(r["articulos"])
        ranks = " ".join(
            f"← citado por Art. {v}" if k == "referido_por" else f"{k}#{v}"
            for k, v in r["ranks"].items()
        )
        print(f"    Art. {label:<10} score={r['score']:.4f} ({r['fuente']}) {ranks}")
    print("[debug] verificación de pasajes:")
    for check in info["verificacion"]:
        print(
            f"    Art. {check['articulo']:<8} {check['metodo']:<15} {check['pasaje_modelo'][:70]!r}"
        )
    if info["citas_invalidas"]:
        print(f"[debug] citas fuera de contexto: {info['citas_invalidas']}")
    print(f"[debug] latencias (ms): {info['latencias_ms']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pregúntale a la Ley Federal del Trabajo.")
    parser.add_argument("pregunta")
    parser.add_argument("--debug", action="store_true", help="recuperación, pasajes y latencias")
    parser.add_argument("--json", action="store_true", help="imprime el contrato JSON")
    args = parser.parse_args()

    result = answer(args.pregunta)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(result, args.debug)


if __name__ == "__main__":
    main()
