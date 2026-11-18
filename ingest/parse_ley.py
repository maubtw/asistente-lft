"""PDF de la LFT → data/processed/lft.jsonl (un artículo por línea).

Pasos:
1. Extraer texto por página y quitar el encabezado de página (termina en "N de M").
2. Separar el cuerpo de la ley de los artículos transitorios.
3. Recorrer el cuerpo línea por línea: TÍTULO / CAPÍTULO / Sección actualizan la jerarquía,
   un encabezado "Artículo N.-" abre un artículo nuevo, las notas de reforma ("Artículo
   reformado DOF ...") se separan del texto.
4. Marcar derogados, detectar referencias cruzadas y escribir el JSONL.

Uso: uv run python -m ingest.parse_ley [--pdf data/raw/LFT.pdf] [--out data/processed/lft.jsonl]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

LEY = "LFT"
DEFAULT_PDF = Path("data/raw/LFT.pdf")
DEFAULT_OUT = Path("data/processed/lft.jsonl")

# --- Patrones (basados en ejemplos reales del PDF, ver tests/test_parse_ley.py) ---------------

# "Artículo 1o.-", "Artículo 22.", "Artículo 39-A.-", "Artículo 3o. Bis.-", "Artículo 153-F Bis.",
# "Artículo 353-Ñ.-", "Artículo 890- Se deroga.", "Artículo 1º.-" (transitorios)
SUFFIXES = ["Bis", "Ter", "Quáter", "Quintus", "Quinquies", "Sexies"]
HEADER_RE = re.compile(
    r"^Art[íi]culo\s+(?P<num>\d{1,4})\s*(?:o|º|°)?\.?"
    r"(?:\s*-\s*(?P<letter>[A-ZÑ])(?![A-Za-zÁÉÍÓÚáéíóúñ]))?"
    r"(?:\.?\s+(?P<suffix>Bis|Ter|Qu[aá]ter|Quintus|Quinquies|Sexies)\b)?"
    r"\s*(?:\.\s*-|\.|-)\s*(?P<rest>.*)$"
)
LETTERS = "ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"

TITLE_RE = re.compile(r"^T[ÍI]TULO\s+[A-ZÁÉÍÓÚ]+(?:\s+BIS)?$")
# "CAPITULO IV", "CAPÍTULO XII BIS", "Capítulo III BIS", "Capitulo XIII Bis" (todas aparecen)
CHAPTER_RE = re.compile(
    r"^(?:CAP[ÍI]TULO|Cap[íi]tulo)\s+[IVXLC]+(?:\s+(?:BIS|TER|QU[AÁ]TER|Bis|Ter|Qu[aá]ter))?$"
)
SECTION_RE = re.compile(
    r"^Secci[óo]n\s+(?:Primera|Segunda|Tercera|Cuarta|Quinta|Sexta|S[ée]ptima|Octava|Novena|"
    r"D[ée]cima)$"
)

# Notas editoriales de la Cámara: "Artículo reformado DOF ...", "Párrafo con fracciones
# adicionado DOF ...", "Fe de erratas al artículo DOF ...", "Reforma DOF 01-05-2026: Derogó ...".
NOTE_RE = re.compile(
    r"^(?:"
    r"(?:Art[íi]culo|P[áa]rrafo|Fracci[óo]n|Inciso|Numeral|Apartado|Cap[íi]tulo|T[íi]tulo|"
    r"Secci[óo]n|Denominaci[óo]n|[ÚU]ltimo p[áa]rrafo)\b[^.]{0,60}?"
    r"\b(?:reformad|adicionad|derogad|recorrid|reubicad)[oa]s?\b.*DOF"
    r"|Fe de erratas\b.*DOF"
    r"|Reforma DOF \d"
    r"|Derogad[oa] DOF"
    r"|Nota: El decreto"
    r")"
)
DATE_START_RE = re.compile(r"^\d{2}-\d{2}-\d{4}")
PAGE_COUNTER_RE = re.compile(r"^\d+ de \d+$")
REFORM_DATE_RE = re.compile(r"[ÚU]ltima [Rr]eforma publicada(?: DOF)?\s+(\d{2})-(\d{2})-(\d{4})")
DEROGATED_RE = re.compile(r"^\(?\s*Se deroga\.?\s*\)?\.?$")

TRANSITORIOS_RE = re.compile(r"^TRANSITORIOS$")
DECREES_START_RE = re.compile(r"^ART[ÍI]CULOS TRANSITORIOS DE DECRETOS DE REFORMA")
DECREE_PUBLISHED_RE = re.compile(
    r"^Publicad[oa] en el Diario Oficial de la Federaci[óo]n el (\d{1,2})o? de (\w+) de (\d{4})"
)
DECREE_TRANSITORIOS_RE = re.compile(r"^(?:ART[ÍI]CULOS? )?TRANSITORIOS?$", re.IGNORECASE)
MONTHS = {
    month: i + 1
    for i, month in enumerate(
        [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]
    )
}

# Referencias cruzadas: "artículo 50", "artículos 47 y 51", "artículos 154 a 156",
# "fracción III del artículo 132", "artículo 3o. Bis", "artículo 39-A".
REF_ID = r"\d{1,4}(?:\s*o\.?|º)?(?:-[A-ZÑ](?![a-záéíóúñ]))?(?:\s+(?:Bis|Ter|Qu[aá]ter)\b)?"
REF_LIST_RE = re.compile(
    rf"\bart[íi]culos?\s+(?P<list>{REF_ID}(?:\s*(?:,|\by\b|\be\b|\bo\b|\bal?\b)\s*{REF_ID})*)",
    re.IGNORECASE,
)
REF_ID_RE = re.compile(
    r"(?P<num>\d{1,4})(?:\s*o\.?|º)?(?:-(?P<letter>[A-ZÑ]))?(?:\s+(?P<suffix>Bis|Ter|Qu[aá]ter))?"
)
REF_RANGE_RE = re.compile(r"^(\d{1,4})\s+al?\s+(\d{1,4})$")
# Si justo después de la cita aparece otra ley, no es una referencia interna.
EXTERNAL_LAW_RE = re.compile(
    r"^[^.;]{0,80}?(?:Constituci[óo]n|[Cc]onstitucional|C[óo]digo|Reglamento|Transitorio|"
    r"de la Ley (?!Federal del Trabajo)|de la presente Ley del|Ley del Seguro|Ley General)"
)
# "en los casos del artículo anterior", "el artículo precedente", "el artículo siguiente".
# Plurales ("artículos anteriores") se ignoran: no dicen cuántos ni cuáles.
PREVIOUS_ARTICLE_RE = re.compile(
    r"\bart[íi]culo\s+(?:anterior|precedente|que\s+antecede)\b", re.IGNORECASE
)
NEXT_ARTICLE_RE = re.compile(r"\bart[íi]culo\s+siguiente\b", re.IGNORECASE)
MAX_RANGE = 30
MAX_NUMBER_JUMP = 15  # un encabezado que salta más que esto se trata como texto


# --- Modelo ---------------------------------------------------------------------------------


@dataclass
class Article:
    articulo: str
    texto: str
    titulo: str | None = None
    capitulo: str | None = None
    seccion: str | None = None
    referencias: list[str] = field(default_factory=list)
    notas_reforma: list[str] = field(default_factory=list)
    derogado: bool = False
    es_transitorio: bool = False
    fecha_reforma: str | None = None
    ley: str = LEY

    def to_json(self) -> str:
        data = asdict(self)
        ordered = {"ley": data.pop("ley"), "articulo": data.pop("articulo"), **data}
        return json.dumps(ordered, ensure_ascii=False)


@dataclass(frozen=True)
class ArticleHeader:
    num: int
    letter: str | None
    suffix: str | None
    rest: str

    @property
    def article_id(self) -> str:
        return normalize_id(self.num, self.letter, self.suffix)

    @property
    def sort_key(self) -> tuple[int, int, int]:
        return article_sort_key(self.num, self.letter, self.suffix)


# --- Funciones puras (testeadas) ------------------------------------------------------------


def normalize_suffix(suffix: str | None) -> str | None:
    if not suffix:
        return None
    return "Quáter" if suffix.lower().startswith("qu") and "ter" in suffix.lower() else suffix


def normalize_id(num: int, letter: str | None = None, suffix: str | None = None) -> str:
    """(3, None, 'Bis') → '3 Bis'; (39, 'A', None) → '39-A'; (153, 'F', 'Bis') → '153-F Bis'."""
    article_id = str(num)
    if letter:
        article_id += f"-{letter}"
    if suffix := normalize_suffix(suffix):
        article_id += f" {suffix}"
    return article_id


def article_sort_key(num: int, letter: str | None, suffix: str | None) -> tuple[int, int, int]:
    """Orden legal: 3 < 3 Bis < 3 Ter < 4 ; 153-F < 153-F Bis < 153-G ; 353-N < 353-Ñ < 353-O."""
    letter_rank = LETTERS.index(letter) + 1 if letter else 0
    suffix = normalize_suffix(suffix)
    suffix_rank = SUFFIXES.index(suffix) + 1 if suffix else 0
    return (num, letter_rank, suffix_rank)


def parse_header(line: str) -> ArticleHeader | None:
    match = HEADER_RE.match(line.strip())
    if not match:
        return None
    return ArticleHeader(
        num=int(match["num"]),
        letter=match["letter"],
        suffix=normalize_suffix(match["suffix"]),
        rest=match["rest"].strip(),
    )


def is_reform_note(line: str) -> bool:
    return bool(NOTE_RE.match(line.strip()))


def is_derogated(text: str) -> bool:
    return bool(DEROGATED_RE.match(text.strip()))


def extract_reform_date(text: str) -> str | None:
    """'Última reforma publicada 14-05-2026' → '2026-05-14'."""
    match = REFORM_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def strip_page_header(page_text: str) -> list[str]:
    """Quita todo hasta la línea 'N de M' (encabezado de la Cámara de Diputados)."""
    lines = [line.strip() for line in page_text.splitlines()]
    for i, line in enumerate(lines[:15]):
        if PAGE_COUNTER_RE.match(line):
            return lines[i + 1 :]
    return lines


def join_paragraphs(lines: list[str]) -> str:
    """Une líneas cortadas del PDF; los párrafos (separados por línea vacía) quedan con '\\n'."""
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(re.sub(r"\s+", " ", p).strip() for p in paragraphs)


def _ref_ids_from_list(list_text: str) -> list[str]:
    ids: list[str] = []
    for part in re.split(r"\s*(?:,|\by\b|\be\b|\bo\b)\s*", list_text):
        part = part.strip()
        if not part:
            continue
        if range_match := REF_RANGE_RE.match(part):
            start, end = int(range_match[1]), int(range_match[2])
            if 0 < end - start <= MAX_RANGE:
                ids.extend(str(n) for n in range(start, end + 1))
                continue
        for id_match in REF_ID_RE.finditer(part):
            ids.append(normalize_id(int(id_match["num"]), id_match["letter"], id_match["suffix"]))
    return ids


def extract_references(text: str, self_id: str | None = None) -> list[str]:
    """Referencias a otros artículos de esta ley, en orden de aparición y sin duplicados."""
    refs: list[str] = []
    for match in REF_LIST_RE.finditer(text):
        if EXTERNAL_LAW_RE.match(text[match.end() :]):
            continue
        for ref in _ref_ids_from_list(match["list"]):
            if ref != self_id and ref not in refs:
                refs.append(ref)
    return refs


def numbering_gaps(article_ids: list[str]) -> list[int]:
    """Números base (1..max) que no aparecen en ningún artículo."""
    nums = {int(re.match(r"\d+", a)[0]) for a in article_ids if re.match(r"\d+", a)}
    if not nums:
        return []
    return [n for n in range(1, max(nums) + 1) if n not in nums]


# --- Recorrido del documento ----------------------------------------------------------------


def _normalize_heading(line: str) -> str:
    """'TITULO QUINTO BIS' → 'TÍTULO QUINTO BIS'; 'Capitulo XIII Bis' → 'CAPÍTULO XIII BIS'."""
    line = re.sub(r"^TITULO\b", "TÍTULO", line)
    if CHAPTER_RE.match(line):
        return "CAPÍTULO " + line.split(maxsplit=1)[1].upper()
    return line


def _read_heading_name(lines: list[str], start: int) -> tuple[str, int]:
    """Lee el nombre de un TÍTULO/CAPÍTULO (1–3 líneas, puede venir tras un salto de página)."""
    i = start
    while i < len(lines) and not lines[i]:
        i += 1
    name_parts: list[str] = []
    while (
        i < len(lines)
        and lines[i]
        and not is_reform_note(lines[i])
        and not parse_header(lines[i])
        and len(name_parts) < 3
    ):
        name_parts.append(lines[i])
        i += 1
    return " ".join(name_parts), i


@dataclass
class _ParserState:
    titulo: str | None = None
    capitulo: str | None = None
    seccion: str | None = None
    current: Article | None = None
    current_lines: list[str] = field(default_factory=list)
    last_key: tuple[int, int, int] = (0, 0, 0)
    in_note: bool = False
    rejected_headers: list[str] = field(default_factory=list)


def _close_article(state: _ParserState, articles: list[Article]) -> None:
    if state.current is None:
        return
    state.current.texto = join_paragraphs(state.current_lines)
    state.current.derogado = is_derogated(state.current.texto)
    articles.append(state.current)
    state.current, state.current_lines = None, []


def _accepts_header(header: ArticleHeader, last_key: tuple[int, int, int]) -> bool:
    """Evita falsos positivos: la numeración del cuerpo siempre avanza y sin saltos grandes."""
    if last_key == (0, 0, 0):  # primer artículo
        return True
    return header.sort_key > last_key and header.num - last_key[0] <= MAX_NUMBER_JUMP


def parse_body(lines: list[str], fecha_reforma: str | None) -> tuple[list[Article], list[str]]:
    """Devuelve (artículos, encabezados rechazados) del cuerpo principal de la ley."""
    state = _ParserState()
    articles: list[Article] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1

        if TITLE_RE.match(line) or CHAPTER_RE.match(line) or SECTION_RE.match(line):
            _close_article(state, articles)
            name, i = _read_heading_name(lines, i)
            heading = f"{_normalize_heading(line)} {name}".strip()
            if TITLE_RE.match(line):
                state.titulo, state.capitulo, state.seccion = heading, None, None
            elif CHAPTER_RE.match(line):
                state.capitulo, state.seccion = heading, None
            else:
                state.seccion = heading
            continue

        if is_reform_note(line) or (state.in_note and (DATE_START_RE.match(line) or "DOF" in line)):
            state.in_note = True
            if state.current is not None:
                state.current.notas_reforma.append(line)
            continue
        state.in_note = False

        header = parse_header(line)
        if header and _accepts_header(header, state.last_key):
            _close_article(state, articles)
            state.last_key = header.sort_key
            state.current = Article(
                articulo=header.article_id,
                texto="",
                titulo=state.titulo,
                capitulo=state.capitulo,
                seccion=state.seccion,
                fecha_reforma=fecha_reforma,
            )
            state.current_lines = [header.rest] if header.rest else []
            continue
        if header:
            state.rejected_headers.append(line)

        if state.current is not None:
            state.current_lines.append(line)

    _close_article(state, articles)
    _merge_note_continuations(articles)
    return articles, state.rejected_headers


def _merge_note_continuations(articles: list[Article]) -> None:
    """Notas largas ocupan 2 líneas en el PDF: se unen en una sola."""
    for article in articles:
        merged: list[str] = []
        for note in article.notas_reforma:
            if merged and not is_reform_note(note):
                merged[-1] = f"{merged[-1]} {note}"
            else:
                merged.append(note)
        article.notas_reforma = merged


def split_body_and_transitorios(lines: list[str]) -> tuple[list[str], list[str]]:
    """El cuerpo termina en la primera línea 'TRANSITORIOS' (tras el último artículo)."""
    for i, line in enumerate(lines):
        if TRANSITORIOS_RE.match(line):
            return lines[:i], lines[i + 1 :]
    return lines, []


def parse_original_transitorios(lines: list[str], fecha_reforma: str | None) -> list[Article]:
    """Transitorios de la ley de 1970: 'Artículo 1º.-' ... (reinician la numeración)."""
    articles: list[Article] = []
    current_id, current_lines = None, []
    for line in lines:
        header = parse_header(line)
        if header:
            if current_id:
                articles.append(_transitorio(current_id, current_lines, fecha_reforma))
            current_id = f"Transitorio {header.article_id} (1970)"
            current_lines = [header.rest]
        elif current_id:
            current_lines.append(line)
    if current_id:
        articles.append(_transitorio(current_id, current_lines, fecha_reforma))
    return articles


def _transitorio(
    article_id: str, lines: list[str], fecha_reforma: str | None, titulo: str | None = None
) -> Article:
    return Article(
        articulo=article_id,
        texto=join_paragraphs(lines),
        titulo=titulo or "TRANSITORIOS",
        es_transitorio=True,
        fecha_reforma=fecha_reforma,
    )


def _decree_date(lines: list[str]) -> str | None:
    for line in lines[:12]:
        if match := DECREE_PUBLISHED_RE.match(line):
            day, month, year = match.groups()
            month_num = MONTHS.get(month.lower())
            if month_num:
                return f"{int(day):02d}-{month_num:02d}-{year}"
    return None


def parse_decree_transitorios(lines: list[str], fecha_reforma: str | None) -> list[Article]:
    """Un registro por decreto de reforma, con el texto de sus transitorios."""
    starts = [i for i, line in enumerate(lines) if line.startswith("DECRETO")]
    articles: list[Article] = []
    seen: dict[str, int] = {}
    for start, end in zip(starts, starts[1:] + [len(lines)], strict=True):
        block = lines[start:end]
        title_lines = []
        for line in block:
            if not line or line.startswith("Publicad"):
                break
            title_lines.append(line)
        date = _decree_date(block) or "fecha desconocida"
        seen[date] = seen.get(date, 0) + 1
        article_id = f"Transitorios DOF {date}"
        if seen[date] > 1:
            article_id += f" ({seen[date]})"
        trans_start = next(
            (i + 1 for i, line in enumerate(block) if DECREE_TRANSITORIOS_RE.match(line)), 0
        )
        articles.append(
            _transitorio(article_id, block[trans_start:], fecha_reforma, " ".join(title_lines))
        )
    return articles


def parse_transitorios(lines: list[str], fecha_reforma: str | None) -> list[Article]:
    decrees_at = next((i for i, line in enumerate(lines) if DECREES_START_RE.match(line)), None)
    original = lines if decrees_at is None else lines[:decrees_at]
    decrees = [] if decrees_at is None else lines[decrees_at + 1 :]
    return parse_original_transitorios(original, fecha_reforma) + parse_decree_transitorios(
        decrees, fecha_reforma
    )


def adjacent_references(text: str, previous_id: str | None, next_id: str | None) -> list[str]:
    """Resuelve "artículo anterior/siguiente" al artículo vecino en el orden de la ley.

    Ej. Art. 75: "En los casos del artículo anterior…" → ["74"]; Art. 52: "…las causas
    mencionadas en el artículo anterior" → ["51"].
    """
    refs = []
    if previous_id and PREVIOUS_ARTICLE_RE.search(text):
        refs.append(previous_id)
    if next_id and NEXT_ARTICLE_RE.search(text):
        refs.append(next_id)
    return refs


def add_references(articles: list[Article]) -> None:
    """Referencias explícitas ("artículo 50") y relativas ("artículo anterior").

    Solo se guardan referencias a artículos que existen en el cuerpo de la ley. Las relativas van
    primero: sin el vecino, el artículo no se entiende (el 75 no dice qué días son feriados).
    """
    body = [a for a in articles if not a.es_transitorio]
    known = {a.articulo for a in body}
    for i, article in enumerate(body):
        if article.derogado:
            continue
        previous_id = body[i - 1].articulo if i > 0 else None
        next_id = body[i + 1].articulo if i + 1 < len(body) else None
        adjacent = adjacent_references(article.texto, previous_id, next_id)
        explicit = extract_references(article.texto, article.articulo)
        refs = list(dict.fromkeys(adjacent + explicit))  # sin duplicados, en orden
        article.referencias = [r for r in refs if r in known and r != article.articulo]


# --- Entrada / salida -----------------------------------------------------------------------


def read_pdf_lines(pdf_path: Path) -> tuple[list[str], str | None]:
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        pages = [page.get_text() for page in doc]
    fecha = extract_reform_date(pages[0]) if pages else None
    lines = [line for page in pages for line in strip_page_header(page)]
    return lines, fecha


def parse_pdf(pdf_path: Path) -> tuple[list[Article], list[str], str | None]:
    lines, fecha = read_pdf_lines(pdf_path)
    body, trans = split_body_and_transitorios(lines)
    articles, rejected = parse_body(body, fecha)
    articles += parse_transitorios(trans, fecha)
    add_references(articles)
    return articles, rejected, fecha


def write_jsonl(articles: list[Article], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for article in articles:
            f.write(article.to_json() + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parsea el PDF de la LFT a JSONL por artículo.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    articles, rejected, fecha = parse_pdf(args.pdf)
    write_jsonl(articles, args.out)
    print(f"Fecha de última reforma: {fecha}")
    print(f"Escritos {len(articles)} registros en {args.out}")
    if rejected:
        print(f"Encabezados descartados por numeración ({len(rejected)}):")
        for line in rejected:
            print(f"  - {line[:100]}")
    print("Para el reporte completo: uv run python -m ingest.verify")


if __name__ == "__main__":
    main()
