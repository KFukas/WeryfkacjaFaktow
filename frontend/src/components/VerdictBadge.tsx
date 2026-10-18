import type { Verdict } from "../api";
import { VERDICT_STYLE } from "../lib/verdict";

export function VerdictBadge({ verdict, small = false }: { verdict: Verdict; small?: boolean }) {
  const s = VERDICT_STYLE[verdict] ?? VERDICT_STYLE.oczekuje;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium ring-1 ring-inset ${s.badge} ${
        small ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm"
      }`}
      title={`${s.label} (${s.description})`}
    >
      <span aria-hidden="true">{s.icon}</span>
      {s.label}
    </span>
  );
}

export function VerdictLegend() {
  return (
    <ul className="flex flex-wrap gap-3 text-xs text-slate-600 dark:text-slate-300" aria-label="Legenda werdyktów">
      {(Object.keys(VERDICT_STYLE) as Verdict[]).map((v) => (
        <li key={v} className="flex items-center gap-1.5">
          <span className={`rounded px-1 ${VERDICT_STYLE[v].mark} ${VERDICT_STYLE[v].pattern}`}>
            {VERDICT_STYLE[v].icon} {VERDICT_STYLE[v].label}
          </span>
          <span className="sr-only">— {VERDICT_STYLE[v].description}</span>
        </li>
      ))}
    </ul>
  );
}
