import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { api, type AgentRun } from "../api";

const TYPE_STYLE: Record<string, string> = {
  tool_violation: "text-rose-700 dark:text-rose-300 font-semibold",
  egress_blocked: "text-rose-700 dark:text-rose-300 font-semibold",
  provenance_blocked: "text-rose-700 dark:text-rose-300 font-semibold",
  injection_detected: "text-amber-700 dark:text-amber-300 font-semibold",
  error: "text-rose-700",
  llm_call: "text-violet-700 dark:text-violet-300",
  tool_call: "text-sky-700 dark:text-sky-300",
};

export function AuditLog({ runs }: { runs: AgentRun[] }) {
  const [runId, setRunId] = useState<string>(runs[0]?.id ?? "");
  const [filter, setFilter] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const q = useQuery({ queryKey: ["events", runId], queryFn: () => api.events(runId), enabled: !!runId });
  const events = (q.data ?? []).filter((e) => !filter || e.type === filter);
  const types = [...new Set((q.data ?? []).map((e) => e.type))].sort();
  if (!runs.length) return <p className="text-sm text-slate-500">Brak przebiegów agenta dla tego artykułu.</p>;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-sm">
        <label>
          Przebieg{" "}
          <select value={runId} onChange={(e) => setRunId(e.target.value)} className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800">
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {new Date(r.started_at).toLocaleString("pl-PL")} · {r.status} · {r.llm_provider}
                {r.claim_id ? ` · twierdzenie ${r.claim_id}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          Typ{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-600 dark:bg-slate-800">
            <option value="">wszystkie</option>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-2">#</th>
              <th className="pr-2">czas</th>
              <th className="pr-2">etap</th>
              <th className="pr-2">typ</th>
              <th className="pr-2">nazwa</th>
              <th className="pr-2">tw.</th>
              <th className="pr-2 text-right">ms</th>
              <th className="pr-2 text-right">tokeny</th>
              <th className="text-right">USD</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <Fragment key={e.id}>
                <tr onClick={() => setOpen(open === e.id ? null : e.id)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900">
                  <td className="py-1 pr-2 font-mono">{e.id}</td>
                  <td className="pr-2 font-mono">{new Date(e.ts).toLocaleTimeString("pl-PL")}</td>
                  <td className="pr-2">{e.stage}</td>
                  <td className={`pr-2 ${TYPE_STYLE[e.type] ?? ""}`}>{e.type}</td>
                  <td className="pr-2">{e.name}</td>
                  <td className="pr-2">{e.claim_id ?? ""}</td>
                  <td className="pr-2 text-right font-mono">{e.duration_ms || ""}</td>
                  <td className="pr-2 text-right font-mono">{e.input_tokens + e.output_tokens || ""}</td>
                  <td className="text-right font-mono">{e.cost_usd ? e.cost_usd.toFixed(5) : ""}</td>
                </tr>
                {open === e.id && (
                  <tr>
                    <td colSpan={9}>
                      <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-100 p-2 text-[11px] dark:bg-slate-900">
                        {JSON.stringify(e.payload, null, 2)}
                      </pre>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
