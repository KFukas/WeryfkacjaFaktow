import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ArticleStatusControl } from "./components/ArticleStatusControl";

function wrap(ui: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("ArticleStatusControl", () => {
  it("pokazuje status i pozwala zatwierdzić artykuł po weryfikacji", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: 2, status: "verified" }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    wrap(<ArticleStatusControl articleId={2} status="in_review" hasClaims />);
    expect(screen.getByText(/Status: w weryfikacji/)).toBeInTheDocument();
    const btn = screen.getByRole("button", { name: /Oznacz jako zweryfikowany/ });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/articles/2");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ status: "verified" });
  });

  it("bez twierdzeń przycisk jest widoczny, ale nieaktywny — z podanym powodem", () => {
    wrap(<ArticleStatusControl articleId={3} status="draft" hasClaims={false} />);
    expect(screen.getByRole("button", { name: /Oznacz jako zweryfikowany/ })).toBeDisabled();
    expect(screen.getByText(/najpierw uruchom weryfikację/)).toBeInTheDocument();
  });

  it("zweryfikowany artykuł pokazuje status i możliwość cofnięcia", () => {
    wrap(<ArticleStatusControl articleId={1} status="verified" hasClaims />);
    expect(screen.getByText(/Status: zweryfikowany/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cofnij zatwierdzenie" })).toBeEnabled();
  });
});
