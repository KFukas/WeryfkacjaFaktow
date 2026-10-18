// Podział treści artykułu na segmenty: zwykły tekst i fragmenty twierdzeń (wg offsetów z API).

export interface Segment<T> {
  start: number;
  end: number;
  text: string;
  item: T | null;
}

export interface Span {
  start_offset: number;
  end_offset: number;
}

/** Zakresy nakładające się lub wychodzące poza tekst są pomijane — UI nigdy nie dubluje ani nie gubi tekstu. */
export function buildSegments<T extends Span>(body: string, items: T[]): Segment<T>[] {
  const sorted = [...items]
    .filter((c) => c.start_offset >= 0 && c.end_offset <= body.length && c.end_offset > c.start_offset)
    .sort((a, b) => a.start_offset - b.start_offset || b.end_offset - a.end_offset);
  const out: Segment<T>[] = [];
  let pos = 0;
  for (const c of sorted) {
    if (c.start_offset < pos) continue;
    if (c.start_offset > pos) out.push({ start: pos, end: c.start_offset, text: body.slice(pos, c.start_offset), item: null });
    out.push({ start: c.start_offset, end: c.end_offset, text: body.slice(c.start_offset, c.end_offset), item: c });
    pos = c.end_offset;
  }
  if (pos < body.length) out.push({ start: pos, end: body.length, text: body.slice(pos), item: null });
  return out;
}
