import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Claim, type ClaimSource, type FinalVerdict } from "../api";
import { FLAG_LABEL, RELATION_LABEL, safeHref, scoreColor, SOURCE_TYPE_LABEL } from "../lib/verdict";
import { VerdictBadge } from "./VerdictBadge";

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2" aria-label={`Ocena wiarygodności ${score} na 100`}>
      <div className="h-2 w-24 overflow-hidden rounded bg-slate-200 dark:bg-slate-700">
        <div className={`h-full ${scoreColor(score)}`} style={{ width: `${Math.max(2, score)}%` }} />
      </div>
      <span className="font-mono text-sm tabular-nums">{score}/100</span>
    </div>
  );
}

export function SourceCard({ link }: { link: ClaimSource }) {
  const [open, setOpen] = useState(false);
  const s = link.source;
  const flags = s.injection_flags ?? [];
  const high = flags.filter((f) => f.severity === "high");
  const href = safeHref(s.final_url || s.url);
  const b = s.credibility_breakdown ?? {};
  return (
    <li className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-slate-500">
            {RELATION_LABEL[link.relation]} · {SOURCE_TYPE_LABEL[s.source_type] ?? s.source_type}
            {s.is_primary ? " · pierwotne" : ""}
          </p>
          <p className="truncate font-medium" title={s.title}>
            {s.title || s.url}
          </p>
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="break-all text-xs text-sky-700 underline dark:text-sky-400">
              {s.final_url || s.url}
            </a>
          ) : (
            <span className="break-all text-xs text-slate-500">{s.final_url || s.url}</span>
          )}
          {s.publisher && <p className="text-xs text-slate-500">Wydawca: {s.publisher}</p>}
        </div>
        <ScoreBar score={s.credibility_score} />
      </div>
      {flags.length > 0 && (
        <div role="alert" className="mt-2 rounded border border-rose-300 bg-rose-50 p-2 text-sm text-rose-900 dark:border-rose-700 dark:bg-rose-950 dark:text-rose-100">
          <p className="font-semibold">
            ⚠ {high.length > 0 ? "Strona zawierała ukryte polecenia lub próby manipulacji — oceniona niżej." : "Wykryto sygnały ostrzegawcze."}
          </p>
          <ul className="mt-1 list-inside list-disc text-xs">
            {[...new Set(flags.map((f) => f.type))].map((t) => (
              <li key={t}>{FLAG_LABEL[t] ?? t}</li>
            ))}
          </ul>
        </div>
      )}
      {link.quote && (
        <blockquote className="mt-2 border-l-4 border-slate-300 pl-3 text-sm italic text-slate-700 dark:border-slate-600 dark:text-slate-300">
          „{link.quote}”
          {link.quote_verified && <span className="ml-1 not-italic text-xs text-emerald-700 dark:text-emerald-400">(cytat zweryfikowany w tekście źródła)</span>}
        </blockquote>
      )}
      {s.summary && <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{s.summary}</p>}
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="mt-2 text-xs text-sky-700 underline dark:text-sky-400">
        {open ? "Ukryj" : "Pokaż"} rozpisanie oceny
      </button>
      {open && (
        <table className="mt-2 w-full text-xs">
          <tbody>
            {(b.deterministic ?? []).map((item, i) => (
              <tr key={i} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-0.5 pr-2">{item.detail}</td>
                <td className="py-0.5 text-right font-mono tabular-nums">{item.points > 0 ? `+${item.points}` : item.points}</td>
              </tr>
            ))}
            <tr className="border-t border-slate-200 dark:border-slate-700">
              <td className="py-0.5 pr-2">Korekta modelu{b.llm_reason ? ` — ${b.llm_reason}` : ""}</td>
              <td className="py-0.5 text-right font-mono">{(b.llm_adjustment ?? 0) >= 0 ? "+" : ""}{b.llm_adjustment ?? 0}</td>
            </tr>
            <tr>
              <td className="py-0.5 pr-2">Korroboracja (niezależne źródła zgodne)</td>
              <td className="py-0.5 text-right font-mono">+{b.corroboration ?? 0}</td>
            </tr>
            <tr className="border-t font-semibold">
              <td className="py-0.5 pr-2">Wynik</td>
              <td className="py-0.5 text-right font-mono">{s.credibility_score}</td>
            </tr>
          </tbody>
        </table>
      )}
    </li>
  );
}

function DecisionForm({ claim }: { claim: Claim }) {
  const qc = useQueryClient();
  const [editor, setEditor] = useState(() => {
    try {
      return localStorage.getItem("editor-name") ?? "";
    } catch {
      return "";
    }
  });
  const [verdict, setVerdict] = useState<FinalVerdict | "">("");
  const [note, setNote] = useState("");
  const m = useMutation({
    mutationFn: () => api.decide(claim.id, { editor, override_verdict: verdict || null, note }),
    onSuccess: () => {
      try {
        localStorage.setItem("editor-name", editor);
      } catch {
        /* brak dostępu do localStorage */
      }
      setNote("");
      setVerdict("");
      qc.invalidateQueries({ queryKey: ["claims", claim.article_id] });
    },
  });
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
    >
      <h4 className="font-semibold">Decyzja redaktora</h4>
      <label className="block text-sm">
        Redaktor
        <input required value={editor} onChange={(e) => setEditor(e.target.value)} className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800" />
      </label>
      <label className="block text-sm">
        Werdykt
        <select value={verdict} onChange={(e) => setVerdict(e.target.value as FinalVerdict | "")} className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800">
          <option value="">— bez zmiany (tylko notatka) —</option>
          <option value="potwierdzone">potwierdzone</option>
          <option value="wątpliwe">wątpliwe</option>
          <option value="fałszywe">fałszywe</option>
        </select>
      </label>
      <label className="block text-sm">
        Notatka
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800" />
      </label>
      <button type="submit" disabled={m.isPending || !editor} className="rounded bg-sky-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50">
        Zapisz decyzję
      </button>
      {m.isError && <p className="text-sm text-rose-700">Błąd: {(m.error as Error).message}</p>}
    </form>
  );
}

export function ClaimPanel({ claim, onReverify, busy }: { claim: Claim; onReverify: () => void; busy: boolean }) {
  const overridden = claim.effective_verdict !== claim.verdict;
  const manip = claim.verdict_details?.manipulation_detected ?? [];
  const order = { supports: 0, contradicts: 1, context: 2 };
  const sources = [...claim.sources].sort((a, b) => order[a.relation] - order[b.relation] || b.source.credibility_score - a.source.credibility_score);
  return (
    <aside aria-label="Szczegóły twierdzenia" className="space-y-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">Twierdzenie · {claim.category}</p>
        <p className="mt-1 font-medium">{claim.text}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <VerdictBadge verdict={claim.effective_verdict} />
        {overridden && <span className="text-xs text-slate-500">agent: {claim.verdict} · nadpisane przez redaktora</span>}
        {claim.confidence !== null && (
          <span className="text-sm text-slate-600 dark:text-slate-300">pewność {(claim.confidence * 100).toFixed(0)}%</span>
        )}
      </div>
      {claim.rationale && (
        <section>
          <h4 className="font-semibold">Uzasadnienie</h4>
          <p className="text-sm leading-relaxed">{claim.rationale}</p>
        </section>
      )}
      {manip.length > 0 && (
        <section role="alert" className="rounded border border-amber-300 bg-amber-50 p-2 text-sm dark:border-amber-700 dark:bg-amber-950">
          <h4 className="font-semibold">Wykryte próby manipulacji</h4>
          <ul className="list-inside list-disc text-xs">
            {manip.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h4 className="font-semibold">Źródła ({sources.length})</h4>
        {sources.length === 0 ? (
          <p className="text-sm text-slate-500">Brak źródeł odnoszących się do twierdzenia.</p>
        ) : (
          <ul className="mt-2 space-y-3">
            {sources.map((l) => (
              <SourceCard key={l.id} link={l} />
            ))}
          </ul>
        )}
      </section>
      <button type="button" onClick={onReverify} disabled={busy} className="rounded border border-sky-700 px-3 py-1.5 text-sm text-sky-800 hover:bg-sky-50 disabled:opacity-50 dark:text-sky-300 dark:hover:bg-slate-800">
        ↻ Zweryfikuj ponownie to twierdzenie
      </button>
      <DecisionForm claim={claim} />
      {claim.decisions.length > 0 && (
        <section>
          <h4 className="font-semibold">Historia decyzji</h4>
          <ol className="mt-1 space-y-1 text-xs">
            {[...claim.decisions].reverse().map((d) => (
              <li key={d.id} className="rounded bg-slate-100 p-2 dark:bg-slate-800">
                <span className="font-medium">{d.editor}</span> · {new Date(d.created_at).toLocaleString("pl-PL")} ·{" "}
                {d.previous_verdict} → {d.override_verdict ?? "(bez zmiany)"}
                {d.note && <p className="mt-0.5">{d.note}</p>}
              </li>
            ))}
          </ol>
        </section>
      )}
    </aside>
  );
}
