/** Divide el texto del artículo en tramos normales y resaltados.
 *
 * El backend garantiza que cada pasaje es una subcadena literal del texto (rag/passages.py),
 * así que basta con buscarlo. Varios pasajes del mismo artículo se fusionan si se traslapan.
 */
export type Segment = { text: string; marked: boolean };

export function highlightSegments(text: string, passages: (string | null)[]): Segment[] {
  const ranges: [number, number][] = [];
  for (const passage of passages) {
    if (!passage) continue;
    const start = text.indexOf(passage);
    if (start >= 0) ranges.push([start, start + passage.length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const range of ranges) {
    const last = merged.at(-1);
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([...range]);
  }

  const segments: Segment[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) segments.push({ text: text.slice(cursor, start), marked: false });
    segments.push({ text: text.slice(start, end), marked: true });
    cursor = end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), marked: false });
  return segments;
}

/** "Artículo remite al artículo 76" / "a los artículos 51 y 50" */
export function referencePhrase(ids: string[]): { prefix: string; ids: string[] } {
  return ids.length === 1
    ? { prefix: "Este artículo remite al artículo", ids }
    : { prefix: "Este artículo remite a los artículos", ids };
}
