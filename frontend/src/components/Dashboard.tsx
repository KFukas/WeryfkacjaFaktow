import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type ArticleStatus, type Verdict } from "../api";
import { VERDICT_STYLE } from "../lib/verdict";

const STATUS_LABEL: Record<ArticleStatus, string> = {
  draft: "szkic",
  in_review: "w weryfikacji",
  verified: "zweryfikowany",
};

function NewArticleForm({ onCreated }: { onCreated: (id: number) => void }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [body, setBody] = useState("");
  const m = useMutation({
    mutationFn: () => api.createArticle({ title, author, body }),
    onSuccess: (a) => {
      qc.invalidateQueries({ queryKey: ["articles"] });
      onCreated(a.id);
    },
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        m.mutate();
      }}
      className="space-y-2 rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 className="text-lg font-semibold">Nowy artykuł</h2>
      <input required placeholder="Tytuł" value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800" />
      <input placeholder="Autor" value={author} onChange={(e) => setAuthor(e.target.value)} className="w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800" />
      <textarea required placeholder="Wklej treść artykułu…" rows={6} value={body} onChange={(e) => setBody(e.target.value)} className="w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800" />
      <button type="submit" disabled={m.isPending} className="rounded bg-sky-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50">
        Dodaj artykuł
      </button>
      {m.isError && <p className="text-sm text-rose-700">Błąd: {(m.error as Error).message}</p>}
    </form>
  );
}

export function Dashboard({ onOpen }: { onOpen: (id: number) => void }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["articles"], queryFn: api.articles, refetchInterval: 5000 });
  const verify = useMutation({
    mutationFn: (id: number) => api.verify(id),
    onSuccess: (_run, id) => {
      qc.invalidateQueries({ queryKey: ["runs", id] });
      onOpen(id);
    },
  });
  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <section>
        <h2 className="mb-3 text-xl font-semibold">Artykuły</h2>
        {q.isLoading && <p>Wczytywanie…</p>}
        {q.isError && <p className="text-rose-700">Nie można połączyć się z API: {(q.error as Error).message}</p>}
        <ul className="space-y-2">
          {(q.data ?? []).map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
              <div className="min-w-0">
                <button type="button" onClick={() => onOpen(a.id)} className="text-left font-medium text-sky-800 hover:underline dark:text-sky-300">
                  {a.title}
                </button>
                <p className="text-xs text-slate-500">
                  #{a.id} · {a.author || "—"} · {STATUS_LABEL[a.status]}
                </p>
                <p className="mt-1 flex flex-wrap gap-2 text-xs">
                  {(Object.entries(a.claim_counts) as [Verdict, number][]).map(([v, n]) => (
                    <span key={v} className={`rounded px-1.5 ${VERDICT_STYLE[v]?.mark ?? ""}`}>
                      {VERDICT_STYLE[v]?.icon} {v}: {n}
                    </span>
                  ))}
                  {Object.keys(a.claim_counts).length === 0 && <span className="text-slate-400">nie weryfikowano</span>}
                </p>
              </div>
              <button type="button" onClick={() => verify.mutate(a.id)} disabled={verify.isPending} className="rounded bg-sky-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-800 disabled:opacity-50">
                Weryfikuj
              </button>
            </li>
          ))}
        </ul>
      </section>
      <NewArticleForm onCreated={onOpen} />
    </div>
  );
}
