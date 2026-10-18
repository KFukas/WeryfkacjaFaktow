import type { Claim } from "../api";
import { buildSegments } from "../lib/segments";
import { VERDICT_STYLE } from "../lib/verdict";

interface Props {
  body: string;
  claims: Claim[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function AnnotatedArticle({ body, claims, selectedId, onSelect }: Props) {
  const segments = buildSegments(body, claims);
  return (
    <div className="whitespace-pre-wrap text-lg leading-9 text-slate-800 dark:text-slate-100" data-testid="article-body">
      {segments.map((seg) => {
        if (!seg.item) return <span key={seg.start}>{seg.text}</span>;
        const c = seg.item;
        const s = VERDICT_STYLE[c.effective_verdict] ?? VERDICT_STYLE.oczekuje;
        const selected = c.id === selectedId;
        return (
          <button
            key={seg.start}
            type="button"
            onClick={() => onSelect(c.id)}
            aria-pressed={selected}
            aria-label={`Twierdzenie: ${s.label}. ${c.text}`}
            className={`rounded px-0.5 text-left underline-offset-4 transition ${s.mark} ${s.pattern} ${
              selected ? "ring-2 ring-sky-500 ring-offset-1 dark:ring-offset-slate-900" : "hover:brightness-95"
            }`}
          >
            <sup aria-hidden="true" className="mr-0.5 select-none font-bold">
              {s.icon}
            </sup>
            {seg.text}
          </button>
        );
      })}
    </div>
  );
}
