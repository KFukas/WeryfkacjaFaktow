import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api } from "../api";
import { AnnotatedArticle } from "./AnnotatedArticle";
import { AuditLog } from "./AuditLog";
import { ClaimPanel } from "./ClaimPanel";
import { RunProgress } from "./RunProgress";
import { VerdictLegend } from "./VerdictBadge";

export function ArticleView({ id, onBack }: { id: number; onBack: () => void }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"text" | "audit">("text");
  const [selected, setSelected] = useState<number | null>(null);
  const article = useQuery({ queryKey: ["article", id], queryFn: () => api.article(id) });
  const claims = useQuery({ queryKey: ["claims", id], queryFn: () => api.claims(id) });
  const runs = useQuery({ queryKey: ["runs", id], queryFn: () => api.runs(id), refetchInterval: 4000 });
  const active = (runs.data ?? []).find((r) => r.status === "queued" || r.status === "running");
  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ["article", id] }), [qc, id]);

  const verify = useMutation({ mutationFn: () => api.verify(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", id] }) });
  const reverify = useMutation({
    mutationFn: (claimId: number) => api.reverify(claimId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", id] }),
  });
  const setStatus = useMutation({
    mutationFn: () => api.updateArticle(id, { status: "verified" }),
    onSuccess: () => {
      refresh();
      qc.invalidateQueries({ queryKey: ["articles"] });
    },
  });

  if (article.isLoading) return <p>Wczytywanie…</p>;
  if (article.isError || !article.data) return <p className="text-rose-700">Nie znaleziono artykułu.</p>;
  const a = article.data;
  const claim = (claims.data ?? []).find((c) => c.id === selected) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" onClick={onBack} className="text-sm text-sky-700 hover:underline dark:text-sky-400">
          ← lista artykułów
        </button>
        <div className="flex flex-wrap gap-2 text-sm">
          <button type="button" onClick={() => verify.mutate()} disabled={!!active || verify.isPending} className="rounded bg-sky-700 px-3 py-1.5 font-medium text-white hover:bg-sky-800 disabled:opacity-50">
            {claims.data?.length ? "Weryfikuj ponownie" : "Uruchom weryfikację"}
          </button>
          <a href={api.reportUrl(id, "md")} className="rounded border border-slate-300 px-3 py-1.5 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800">
            Raport .md
          </a>
          <a href={api.reportUrl(id, "json")} target="_blank" rel="noreferrer" className="rounded border border-slate-300 px-3 py-1.5 hover:bg-slate-100 dark:border-slate-600 dark:hover:bg-slate-800">
            Raport .json
          </a>
          {a.status !== "verified" && (
            <button type="button" onClick={() => setStatus.mutate()} className="rounded border border-emerald-700 px-3 py-1.5 text-emerald-800 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-slate-800">
              Oznacz jako zweryfikowany
            </button>
          )}
        </div>
      </div>
      {active && <RunProgress key={active.id} run={active} onFinished={refresh} />}
      <div role="tablist" className="flex gap-4 border-b border-slate-200 dark:border-slate-700">
        {(["text", "audit"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)} className={`-mb-px border-b-2 px-1 pb-2 text-sm ${tab === t ? "border-sky-600 font-semibold" : "border-transparent text-slate-500"}`}>
            {t === "text" ? "Tekst z adnotacjami" : "Log agenta (audyt)"}
          </button>
        ))}
      </div>
      {tab === "text" ? (
        <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
          <article className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
            <h1 className="text-2xl font-bold">{a.title}</h1>
            <p className="mb-4 text-sm text-slate-500">{a.author}</p>
            <VerdictLegend />
            <div className="mt-4">
              <AnnotatedArticle body={a.body} claims={claims.data ?? []} selectedId={selected} onSelect={setSelected} />
            </div>
            {claims.data?.length === 0 && <p className="mt-4 text-sm text-slate-500">Brak twierdzeń — uruchom weryfikację.</p>}
          </article>
          <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
            {claim ? (
              <ClaimPanel claim={claim} onReverify={() => reverify.mutate(claim.id)} busy={!!active || reverify.isPending} />
            ) : (
              <p className="text-sm text-slate-500">Kliknij podświetlone twierdzenie, aby zobaczyć werdykt, źródła i oceny.</p>
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900">
          <AuditLog key={runs.data?.[0]?.id ?? "none"} runs={runs.data ?? []} />
        </div>
      )}
    </div>
  );
}
