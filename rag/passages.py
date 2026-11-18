"""Validación de pasajes: cada "pasaje" que cita el modelo debe ser texto literal del artículo.

El frontend resalta el pasaje dentro del artículo, así que no puede haber diferencias ni de una
coma. Regla de fondo: **nunca se devuelve el texto que escribió el modelo**, sino el tramo
recortado del artículo real. Por construcción, el resultado es `None` o una subcadena literal.

Niveles, del más estricto al más laxo:
1. exacto       — `texto.find(pasaje)`.
2. normalizado  — igual tras unificar espacios, comillas, guiones y mayúsculas (con un mapa de
                  índices para recortar el tramo original). Incluye pasajes con "…" internos.
3. difuso       — `rapidfuzz` (puntaje ≥ 90, pasaje ≥ 20 caracteres), ampliado a palabras
                  completas. Cubre "período" vs. "periodo" o una palabra cambiada.
4. no_verificable — se conserva la cita, sin resaltado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

Method = Literal["exacto", "normalizado", "difuso", "no_verificable"]

FUZZY_MIN_SCORE = 90.0
FUZZY_MIN_LENGTH = 20
MAX_ELLIPSIS_GAP = 80  # caracteres de ley omitidos entre fragmentos "…" que aún se resaltan juntos
MIN_FRAGMENT_LENGTH = 8

_CHAR_MAP = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "‑": "-",
        " ": " ",
    }
)
_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3}|…)\s*")
_EDGE_CHARS = " \t\n\"'“”«»‘’.,;:…"


@dataclass(frozen=True)
class PassageMatch:
    pasaje: str | None  # tramo literal del artículo, o None
    metodo: Method
    inicio: int | None = None  # posición en el texto del artículo

    @property
    def verificable(self) -> bool:
        return self.pasaje is not None


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Texto normalizado + para cada carácter, su índice en el original.

    Colapsa espacios (incluye saltos de línea), unifica comillas y guiones, y pasa a minúsculas.
    """
    chars: list[str] = []
    index_map: list[int] = []
    previous_space = False
    for i, char in enumerate(text.translate(_CHAR_MAP)):
        if char.isspace():
            if previous_space or not chars:
                continue
            chars.append(" ")
            index_map.append(i)
            previous_space = True
            continue
        chars.append(char.lower()[0])
        index_map.append(i)
        previous_space = False
    while chars and chars[-1] == " ":
        chars.pop()
        index_map.pop()
    return "".join(chars), index_map


def clean_passage(passage: str) -> str:
    """Quita comillas, puntos suspensivos y puntuación de las orillas."""
    return passage.strip(_EDGE_CHARS)


def _literal(text: str, start: int, end: int, method: Method) -> PassageMatch:
    """Recorta el tramo original, sin espacios en las orillas."""
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start >= end:
        return PassageMatch(None, "no_verificable")
    return PassageMatch(text[start:end], method, start)


def _span_in_original(index_map: list[int], norm_start: int, norm_end: int) -> tuple[int, int]:
    return index_map[norm_start], index_map[norm_end - 1] + 1


def _find_normalized(
    norm_passage: str, norm_text: str, index_map: list[int], text: str
) -> PassageMatch | None:
    position = norm_text.find(norm_passage)
    if position < 0:
        return None
    start, end = _span_in_original(index_map, position, position + len(norm_passage))
    return _literal(text, start, end, "normalizado")


def _find_fragments(
    passage: str, norm_text: str, index_map: list[int], text: str
) -> PassageMatch | None:
    """Pasaje con "…" internos: cada fragmento debe estar en el artículo, en orden."""
    fragments = [normalize_with_map(clean_passage(f))[0] for f in _ELLIPSIS_RE.split(passage)]
    fragments = [f for f in fragments if len(f) >= MIN_FRAGMENT_LENGTH]
    if len(fragments) < 2:
        return None
    spans: list[tuple[int, int]] = []
    cursor = 0
    for fragment in fragments:
        position = norm_text.find(fragment, cursor)
        if position < 0:
            break
        spans.append((position, position + len(fragment)))
        cursor = position + len(fragment)
    if len(spans) == len(fragments):
        gaps = [b[0] - a[1] for a, b in zip(spans, spans[1:], strict=False)]
        if max(gaps) <= MAX_ELLIPSIS_GAP:
            start, end = _span_in_original(index_map, spans[0][0], spans[-1][1])
            return _literal(text, start, end, "normalizado")
    # Fragmentos lejanos o alguno no encontrado: se resalta el fragmento más largo que exista.
    found = sorted(
        (f for f in fragments if len(f) >= FUZZY_MIN_LENGTH and f in norm_text),
        key=len,
        reverse=True,
    )
    if not found:
        return None
    position = norm_text.find(found[0])
    start, end = _span_in_original(index_map, position, position + len(found[0]))
    return _literal(text, start, end, "normalizado")


def _expand_to_words(norm_text: str, start: int, end: int) -> tuple[int, int]:
    while start > 0 and norm_text[start - 1].isalnum():
        start -= 1
    while end < len(norm_text) and norm_text[end].isalnum():
        end += 1
    return start, end


def _find_fuzzy(
    norm_passage: str, norm_text: str, index_map: list[int], text: str
) -> PassageMatch | None:
    if len(norm_passage) < FUZZY_MIN_LENGTH:
        return None
    alignment = fuzz.partial_ratio_alignment(norm_passage, norm_text, score_cutoff=FUZZY_MIN_SCORE)
    if alignment is None or alignment.dest_end <= alignment.dest_start:
        return None
    norm_start, norm_end = _expand_to_words(norm_text, alignment.dest_start, alignment.dest_end)
    start, end = _span_in_original(index_map, norm_start, norm_end)
    return _literal(text, start, end, "difuso")


def validate_passage(passage: str | None, text: str) -> PassageMatch:
    """Devuelve el tramo literal de `text` que corresponde a `passage` (o no_verificable)."""
    if not passage or not text:
        return PassageMatch(None, "no_verificable")
    raw = passage.strip()
    position = text.find(raw)
    if raw and position >= 0:
        return _literal(text, position, position + len(raw), "exacto")

    cleaned = clean_passage(raw)
    norm_text, index_map = normalize_with_map(text)
    norm_passage = normalize_with_map(cleaned)[0]
    if not norm_passage or not norm_text:
        return PassageMatch(None, "no_verificable")

    for finder in (
        lambda: _find_normalized(norm_passage, norm_text, index_map, text),
        lambda: _find_fragments(cleaned, norm_text, index_map, text),
        lambda: _find_fuzzy(norm_passage, norm_text, index_map, text),
    ):
        match = finder()
        if match is not None and match.verificable:
            return match
    return PassageMatch(None, "no_verificable")
