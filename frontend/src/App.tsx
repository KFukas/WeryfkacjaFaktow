import { useEffect, useState } from "react";
import { ArticleView } from "./components/ArticleView";
import { Dashboard } from "./components/Dashboard";

function useHashRoute(): [number | null, (id: number | null) => void] {
  const parse = () => {
    const m = window.location.hash.match(/^#\/artykul\/(\d+)/);
    return m ? Number(m[1]) : null;
  };
  const [id, setId] = useState<number | null>(parse);
  useEffect(() => {
    const onHash = () => setId(parse());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [id, (next) => (window.location.hash = next ? `#/artykul/${next}` : "#/")];
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem("theme");
      return saved ? saved === "dark" : window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
    } catch {
      return false;
    }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* brak localStorage */
    }
  }, [dark]);
  return (
    <button type="button" onClick={() => setDark(!dark)} aria-label="Przełącz tryb jasny/ciemny" className="rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-600">
      {dark ? "☀ jasny" : "☾ ciemny"}
    </button>
  );
}

export default function App() {
  const [articleId, go] = useHashRoute();
  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <header className="mb-6 flex items-center justify-between gap-4">
        <a href="#/" className="flex items-baseline gap-2">
          <span className="text-2xl font-black tracking-tight">Kurier Faktów</span>
          <span className="text-sm text-slate-500">panel weryfikacji (redakcja fikcyjna)</span>
        </a>
        <ThemeToggle />
      </header>
      {articleId ? <ArticleView id={articleId} onBack={() => go(null)} /> : <Dashboard onOpen={(id) => go(id)} />}
    </div>
  );
}
