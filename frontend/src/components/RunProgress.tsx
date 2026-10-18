import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type AgentEvent, type AgentRun } from "../api";

const STAGE_LABEL: Record<string, string> = {
  queued: "w kolejce",
  load: "wczytywanie artykułu",
  extract: "wyodrębnianie twierdzeń",
  claims: "weryfikacja twierdzeń",
  done: "zakończono",
};

/** Postęp na żywo przez Server-Sent Events. Po zakończeniu odświeża twierdzenia i listę przebiegów. */
export function RunProgress({ run, onFinished }: { run: AgentRun; onFinished?: () => void }) {
  const qc = useQueryClient();
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [state, setState] = useState<AgentRun>(run);

  useEffect(() => {
    const es = new EventSource(api.streamUrl(run.id));
    es.addEventListener("agent", (e) => {
      const ev = JSON.parse((e as MessageEvent).data) as AgentEvent;
      setEvents((prev) => [...prev.slice(-200), ev]);
      if (ev.type === "progress") setState((s) => ({ ...s, status: "running", progress: ev.payload as AgentRun["progress"] }));
      if (ev.type === "verdict") qc.invalidateQueries({ queryKey: ["claims", run.article_id] });
    });
    es.addEventListener("end", (e) => {
      setState(JSON.parse((e as MessageEvent).data) as AgentRun);
      es.close();
      qc.invalidateQueries({ queryKey: ["claims", run.article_id] });
      qc.invalidateQueries({ queryKey: ["runs", run.article_id] });
      qc.invalidateQueries({ queryKey: ["articles"] });
      onFinished?.();
    });
    es.onerror = () => es.close();
    return () => es.close();
  }, [run.id, run.article_id, qc, onFinished]);

  const p = state.progress ?? {};
  const pct = p.total ? Math.round(((p.done ?? 0) / p.total) * 100) : state.status === "completed" ? 100 : 5;
  const blocked = events.filter((e) => ["tool_violation", "egress_blocked", "provenance_blocked"].includes(e.type)).length;
  const injections = events.filter((e) => e.type === "injection_detected").length;
  return (
    <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm dark:border-sky-800 dark:bg-sky-950" aria-live="polite">
      <div className="flex justify-between gap-2">
        <span className="font-medium">
          Przebieg {state.id.slice(0, 8)} — {state.status === "running" || state.status === "queued" ? STAGE_LABEL[p.stage ?? "queued"] ?? p.stage : state.status}
        </span>
        <span className="font-mono text-xs">
          {p.done ?? 0}/{p.total ?? "?"} · {state.tool_calls} narzędzi · ${state.cost_usd.toFixed(4)}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded bg-sky-100 dark:bg-sky-900" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full bg-sky-600 transition-all" style={{ width: `${pct}%` }} />
      </div>
      {p.current_text && state.status === "running" && <p className="mt-1 truncate text-xs">Teraz: {p.current_text}</p>}
      {(injections > 0 || blocked > 0) && (
        <p className="mt-1 text-xs text-rose-800 dark:text-rose-300">
          ⚠ wykryte manipulacje w źródłach: {injections} · zablokowane działania: {blocked}
        </p>
      )}
      {state.error && <p className="mt-1 text-xs text-rose-700">Błąd: {state.error}</p>}
    </div>
  );
}
