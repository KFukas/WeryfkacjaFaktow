import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ArticleStatus } from "../api";

export const STATUS_LABEL: Record<ArticleStatus, string> = {
  draft: "szkic",
  in_review: "w weryfikacji",
  verified: "zweryfikowany",
};

const STATUS_STYLE: Record<ArticleStatus, string> = {
  draft: "bg-slate-200 text-slate-800 ring-slate-500 dark:bg-slate-700 dark:text-slate-100",
  in_review: "bg-amber-100 text-amber-900 ring-amber-600 dark:bg-amber-900/60 dark:text-amber-100",
  verified: "bg-emerald-100 text-emerald-900 ring-emerald-600 dark:bg-emerald-900/60 dark:text-emerald-100",
};

export function StatusBadge({ status }: { status: ArticleStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLE[status]}`}>
      {status === "verified" && <span aria-hidden="true">✔</span>}
      Status: {STATUS_LABEL[status]}
    </span>
  );
}

interface Props {
  articleId: number;
  status: ArticleStatus;
  hasClaims: boolean;
  busy?: boolean;
}

/** Status artykułu + zatwierdzenie przez redaktora (i cofnięcie zatwierdzenia). */
export function ArticleStatusControl({ articleId, status, hasClaims, busy = false }: Props) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (next: ArticleStatus) => api.updateArticle(articleId, { status: next }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["article", articleId] });
      qc.invalidateQueries({ queryKey: ["articles"] });
    },
  });
  const reason = busy ? "trwa weryfikacja" : !hasClaims ? "najpierw uruchom weryfikację" : "";
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <StatusBadge status={status} />
      {status === "verified" ? (
        <button
          type="button"
          onClick={() => m.mutate("in_review")}
          disabled={m.isPending}
          className="rounded border border-slate-400 px-3 py-1.5 text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-500 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          Cofnij zatwierdzenie
        </button>
      ) : (
        <>
          <button
            type="button"
            onClick={() => m.mutate("verified")}
            disabled={m.isPending || !!reason}
            title={reason ? `Niedostępne: ${reason}` : "Zatwierdź artykuł jako zweryfikowany"}
            className="rounded bg-emerald-700 px-3 py-1.5 font-medium text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ✔ Oznacz jako zweryfikowany
          </button>
          {reason && <span className="text-xs text-slate-500">({reason})</span>}
        </>
      )}
      {m.isError && <span className="text-xs text-rose-700">Błąd: {(m.error as Error).message}</span>}
    </div>
  );
}
