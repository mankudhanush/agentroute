const LINKS = [
  ["product", "Product"],
  ["architecture", "Architecture"],
  ["agents", "Agents"],
  ["tools", "Tools"],
] as const;

export function Footer({ onLaunch }: { onLaunch: () => void }) {
  function go(id: string) {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(id)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }

  return (
    <footer className="px-4 py-10 sm:px-6">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-sm font-semibold">AgentRoute</div>
          <div className="mt-1 text-xs tracking-[0.14em] text-[var(--muted)] uppercase">Intelligent AI routing</div>
        </div>
        <nav className="flex flex-wrap gap-x-4 gap-y-2" aria-label="Footer">
          {LINKS.map(([id, label]) => (
            <button key={id} type="button" onClick={() => go(id)} className="text-xs text-[var(--muted)] hover:text-[var(--text)]">
              {label}
            </button>
          ))}
          <button type="button" onClick={onLaunch} className="text-xs text-[var(--text)]">
            Launch App
          </button>
        </nav>
      </div>
    </footer>
  );
}
