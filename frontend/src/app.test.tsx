import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Claim, ClaimSource } from "./api";
import { AnnotatedArticle } from "./components/AnnotatedArticle";
import { ClaimPanel, SourceCard } from "./components/ClaimPanel";
import { buildSegments } from "./lib/segments";
import { safeHref } from "./lib/verdict";

const body = "Wstęp. Polska przystąpiła do UE 1 maja 2004 r. Do NATO Polska wstąpiła w 2001 roku. Koniec.";

function claim(text: string, verdict: Claim["verdict"], id: number, extra: Partial<Claim> = {}): Claim {
  const start = body.indexOf(text);
  return {
    id, article_id: 1, text, start_offset: start, end_offset: start + text.length, category: "datowe", verdict,
    effective_verdict: verdict, confidence: 0.8, rationale: "Uzasadnienie.", checked_at: null, verdict_details: {},
    sources: [], decisions: [], ...extra,
  };
}

function wrap(ui: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe("buildSegments", () => {
  it("dzieli tekst bez gubienia i dublowania znaków", () => {
    const c = [claim("Do NATO Polska wstąpiła w 2001 roku.", "fałszywe", 2), claim("Polska przystąpiła do UE 1 maja 2004 r.", "potwierdzone", 1)];
    const segs = buildSegments(body, c);
    expect(segs.map((s) => s.text).join("")).toBe(body);
    expect(segs.filter((s) => s.item).map((s) => s.item!.id)).toEqual([1, 2]);
  });
  it("pomija zakresy nakładające się i spoza tekstu", () => {
    const segs = buildSegments("abcdef", [
      { start_offset: 0, end_offset: 4 },
      { start_offset: 2, end_offset: 5 },
      { start_offset: 3, end_offset: 99 },
    ]);
    expect(segs.map((s) => s.text).join("")).toBe("abcdef");
    expect(segs.filter((s) => s.item)).toHaveLength(1);
  });
});

describe("AnnotatedArticle", () => {
  it("podświetla twierdzenia z ikoną (dostępność) i reaguje na kliknięcie", () => {
    const onSelect = vi.fn();
    const c = [claim("Do NATO Polska wstąpiła w 2001 roku.", "fałszywe", 2)];
    render(<AnnotatedArticle body={body} claims={c} selectedId={null} onSelect={onSelect} />);
    const btn = screen.getByRole("button", { name: /Fałszywe/ });
    expect(btn).toHaveTextContent("✘");
    expect(btn.className).toContain("decoration-wavy");
    fireEvent.click(btn);
    expect(onSelect).toHaveBeenCalledWith(2);
  });
});

const flaggedSource: ClaimSource = {
  id: 1, relation: "supports", quote: "<img src=x onerror=alert(1)>", quote_verified: true,
  source: {
    id: 1, url: "javascript:alert(1)", final_url: "javascript:alert(1)", title: "<script>alert('x')</script>",
    publisher: "", source_type: "unknown", published_at: null, fetched_at: null, content_sha256: "",
    credibility_score: 4, credibility_breakdown: { deterministic: [{ criterion: "injection", points: -45, detail: "flagi" }] },
    injection_flags: [{ type: "hidden_text", severity: "high" }, { type: "tool_instruction", severity: "high" }],
    summary: "<b>pogrubione?</b>", is_primary: false,
  },
};

describe("SourceCard — treść zewnętrzna wyłącznie jako tekst", () => {
  it("nie renderuje HTML z cytatu/tytułu i nie tworzy linku javascript:", () => {
    const { container } = render(<ul><SourceCard link={flaggedSource} /></ul>);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.getByText(/<script>alert/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("ukryte polecenia");
    expect(screen.getByText("ukryty tekst")).toBeInTheDocument();
  });
  it("safeHref przepuszcza tylko http/https", () => {
    expect(safeHref("https://stat.gov.pl/")).toBe("https://stat.gov.pl/");
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("data:text/html,x")).toBeUndefined();
  });
});

describe("ClaimPanel", () => {
  it("pokazuje werdykt, pewność, źródła i nadpisanie redaktora", () => {
    const c = claim("Do NATO Polska wstąpiła w 2001 roku.", "fałszywe", 2, {
      effective_verdict: "wątpliwe",
      sources: [flaggedSource],
      decisions: [{ id: 1, claim_id: 2, editor: "red. Nowak", override_verdict: "wątpliwe", previous_verdict: "fałszywe", note: "sprawdzić", created_at: new Date().toISOString() }],
    });
    wrap(<ClaimPanel claim={c} onReverify={() => {}} busy={false} />);
    expect(screen.getByText(/pewność 80%/)).toBeInTheDocument();
    expect(screen.getByText(/nadpisane przez redaktora/)).toBeInTheDocument();
    expect(screen.getByText(/red. Nowak/)).toBeInTheDocument();
    expect(screen.getByText(/Źródła \(1\)/)).toBeInTheDocument();
  });
});

describe("bezpieczeństwo kodu", () => {
  it("nigdzie nie używa dangerouslySetInnerHTML ani innerHTML", () => {
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const f of readdirSync(dir)) {
        const p = join(dir, f);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(tsx?|jsx?)$/.test(f) && !f.endsWith(".test.tsx")) files.push(p);
      }
    };
    walk(join(__dirname));
    expect(files.length).toBeGreaterThan(5);
    for (const f of files) {
      const src = readFileSync(f, "utf-8");
      expect(src, f).not.toMatch(/dangerouslySetInnerHTML|\.innerHTML\s*=|outerHTML|insertAdjacentHTML/);
    }
  });
});
