import type { Verdict } from "../api";

// Kolor + ikona + wzór podkreślenia — rozróżnialne także bez rozpoznawania kolorów.
export const VERDICT_STYLE: Record<
  Verdict,
  { label: string; icon: string; mark: string; badge: string; pattern: string; description: string }
> = {
  potwierdzone: {
    label: "Potwierdzone",
    icon: "✔",
    mark: "bg-emerald-100 dark:bg-emerald-900/50 decoration-emerald-700 dark:decoration-emerald-400",
    badge: "bg-emerald-100 text-emerald-900 ring-emerald-600 dark:bg-emerald-900/60 dark:text-emerald-100",
    pattern: "underline decoration-solid decoration-2",
    description: "podkreślenie ciągłe",
  },
  wątpliwe: {
    label: "Wątpliwe",
    icon: "?",
    mark: "bg-amber-100 dark:bg-amber-900/50 decoration-amber-700 dark:decoration-amber-300",
    badge: "bg-amber-100 text-amber-900 ring-amber-600 dark:bg-amber-900/60 dark:text-amber-100",
    pattern: "underline decoration-dashed decoration-2",
    description: "podkreślenie przerywane",
  },
  fałszywe: {
    label: "Fałszywe",
    icon: "✘",
    mark: "bg-rose-100 dark:bg-rose-900/50 decoration-rose-700 dark:decoration-rose-300",
    badge: "bg-rose-100 text-rose-900 ring-rose-600 dark:bg-rose-900/60 dark:text-rose-100",
    pattern: "underline decoration-wavy decoration-2",
    description: "podkreślenie faliste",
  },
  oczekuje: {
    label: "Oczekuje",
    icon: "…",
    mark: "bg-slate-200 dark:bg-slate-700/60 decoration-slate-500",
    badge: "bg-slate-200 text-slate-800 ring-slate-500 dark:bg-slate-700 dark:text-slate-100",
    pattern: "underline decoration-dotted decoration-2",
    description: "podkreślenie kropkowane",
  },
};

export const RELATION_LABEL = { supports: "wspiera", contradicts: "przeczy", context: "kontekst" } as const;

export const FLAG_LABEL: Record<string, string> = {
  hidden_text: "ukryty tekst",
  instruction_override: "próba nadpisania instrukcji",
  role_marker: "fałszywy znacznik roli",
  persona_change: "próba zmiany roli agenta",
  tool_instruction: "polecenie wywołania narzędzia",
  verdict_manipulation: "próba wymuszenia werdyktu",
  exfiltration: "próba wyprowadzenia danych",
  fetch_instruction: "polecenie odwiedzenia adresu",
  social_engineering: "socjotechnika",
  self_declared_credibility: "samozwańcza wiarygodność",
  encoded_payload: "zakodowane polecenie",
  unicode_smuggling: "ukryte znaki Unicode",
  homoglyph: "homoglify",
  hidden_visible_mismatch: "ukryta treść sprzeczna z widoczną",
  secret_request: "prośba o dane poufne",
  pdf_active_content: "aktywna zawartość PDF",
  resource_limit: "przekroczone limity",
  cross_domain_redirect: "przekierowanie na inną domenę",
  parse_error: "błąd odczytu",
};

export const SOURCE_TYPE_LABEL: Record<string, string> = {
  official_statistics: "urząd statystyczny / bank centralny",
  public_register: "rejestr publiczny",
  primary_data: "dane pierwotne",
  government: "administracja publiczna",
  intergovernmental: "organizacja międzynarodowa",
  scientific: "instytucja naukowa",
  established_media: "media o ustalonej renomie",
  encyclopedia: "encyklopedia",
  other_media: "inne media",
  unknown: "nieznane",
  blog: "blog",
  forum: "forum",
  social_media: "media społecznościowe",
};

export function scoreColor(score: number): string {
  if (score >= 70) return "bg-emerald-600";
  if (score >= 50) return "bg-amber-500";
  return "bg-rose-600";
}

/** Tylko http(s) — inne schematy (javascript:, data:) nie trafiają do atrybutu href. */
export function safeHref(url: string): string | undefined {
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.toString() : undefined;
  } catch {
    return undefined;
  }
}
