// Klient REST API redakcji. Wszystkie dane zewnętrzne (tytuły, cytaty, streszczenia źródeł) są renderowane
// wyłącznie jako tekst — aplikacja nigdy nie wstawia surowego HTML (pilnuje tego test w app.test.tsx).

export type Verdict = "potwierdzone" | "wątpliwe" | "fałszywe" | "oczekuje";
export type FinalVerdict = Exclude<Verdict, "oczekuje">;
export type ArticleStatus = "draft" | "in_review" | "verified";

export interface ArticleSummary {
  id: number;
  title: string;
  author: string;
  status: ArticleStatus;
  created_at: string;
  claim_counts: Partial<Record<Verdict, number>>;
}

export interface Article extends ArticleSummary {
  body: string;
}

export interface InjectionFlag {
  type: string;
  severity: "high" | "medium" | "low";
  channel?: string;
  evidence?: string;
}

export interface BreakdownItem {
  criterion: string;
  points: number;
  detail: string;
}

export interface Source {
  id: number;
  url: string;
  final_url: string;
  title: string;
  publisher: string;
  source_type: string;
  published_at: string | null;
  fetched_at: string | null;
  content_sha256: string;
  credibility_score: number;
  credibility_breakdown: {
    deterministic_score?: number;
    deterministic?: BreakdownItem[];
    llm_adjustment?: number;
    llm_reason?: string;
    corroboration?: number;
    final?: number;
  };
  injection_flags: InjectionFlag[];
  summary: string;
  is_primary: boolean;
}

export interface ClaimSource {
  id: number;
  relation: "supports" | "contradicts" | "context";
  quote: string;
  quote_verified: boolean;
  source: Source;
}

export interface EditorDecision {
  id: number;
  claim_id: number;
  editor: string;
  override_verdict: FinalVerdict | null;
  previous_verdict: string;
  note: string;
  created_at: string;
}

export interface Claim {
  id: number;
  article_id: number;
  text: string;
  start_offset: number;
  end_offset: number;
  category: string;
  verdict: Verdict;
  effective_verdict: Verdict;
  confidence: number | null;
  rationale: string;
  checked_at: string | null;
  verdict_details: {
    rule_verdict?: string;
    model_verdict?: string;
    rule_reasons?: string[];
    notes?: string[];
    manipulation_detected?: string[];
  };
  sources: ClaimSource[];
  decisions: EditorDecision[];
}

export interface AgentRun {
  id: string;
  article_id: number;
  claim_id: number | null;
  status: "queued" | "running" | "completed" | "failed" | "budget_exceeded";
  llm_provider: string;
  model: string;
  started_at: string;
  finished_at: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  tool_calls: number;
  progress: { stage?: string; done?: number; total?: number; current_claim?: number; current_text?: string };
  error: string;
}

export interface AgentEvent {
  id: number;
  run_id: string;
  ts: string;
  stage: string;
  type: string;
  name: string;
  claim_id: number | null;
  payload: Record<string, unknown>;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* brak treści JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string; llm_provider: string; model: string }>("/api/health"),
  articles: () => request<ArticleSummary[]>("/api/articles"),
  article: (id: number) => request<Article>(`/api/articles/${id}`),
  createArticle: (data: { title: string; body: string; author: string }) =>
    request<Article>("/api/articles", { method: "POST", body: JSON.stringify(data) }),
  updateArticle: (id: number, data: Partial<Pick<Article, "title" | "body" | "author" | "status">>) =>
    request<Article>(`/api/articles/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  claims: (articleId: number) => request<Claim[]>(`/api/articles/${articleId}/claims`),
  verify: (articleId: number) =>
    request<AgentRun>(`/api/articles/${articleId}/verify`, {
      method: "POST",
      body: JSON.stringify({ idempotency_key: null }),
    }),
  reverify: (claimId: number) => request<AgentRun>(`/api/claims/${claimId}/reverify`, { method: "POST" }),
  decide: (claimId: number, data: { editor: string; override_verdict: FinalVerdict | null; note: string }) =>
    request<EditorDecision>(`/api/claims/${claimId}/decisions`, { method: "POST", body: JSON.stringify(data) }),
  runs: (articleId: number) => request<AgentRun[]>(`/api/runs?article_id=${articleId}&limit=20`),
  run: (runId: string) => request<AgentRun>(`/api/runs/${runId}`),
  events: (runId: string) => request<AgentEvent[]>(`/api/runs/${runId}/events`),
  streamUrl: (runId: string) => `${API_BASE}/api/runs/${runId}/stream`,
  reportUrl: (articleId: number, format: "md" | "json") => `${API_BASE}/api/articles/${articleId}/report?format=${format}`,
};
