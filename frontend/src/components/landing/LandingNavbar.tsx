import { useEffect, useState } from "react";
import { LaunchButton, Mark } from "./Reveal";

const LINKS = [
  ["product", "Product"],
  ["architecture", "Architecture"],
  ["agents", "Agents"],
  ["tools", "Tools"],
] as const;

type LandingNavbarProps = {
  scroller: HTMLElement | null;
  onLaunch: () => void;
};

export function LandingNavbar({ scroller, onLaunch }: LandingNavbarProps) {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState("product");

  useEffect(() => {
    if (!scroller) return;
    const onScroll = () => setScrolled(scroller.scrollTop > 8);
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, [scroller]);

  useEffect(() => {
    if (!scroller) return;
    const nodes = LINKS.map(([id]) => document.getElementById(id)).filter((node): node is HTMLElement => !!node);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target.id) setActive(visible.target.id);
      },
      { root: scroller, rootMargin: "-20% 0px -55% 0px", threshold: [0.15, 0.4] },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [scroller]);

  function go(id: string) {
    setOpen(false);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(id)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }

  return (
    <header
      className={`sticky top-0 z-20 border-b border-[var(--line)] px-4 transition-colors duration-200 sm:px-6 ${
        scrolled ? "bg-[color-mix(in_srgb,var(--panel)_88%,transparent)] backdrop-blur-md" : "bg-[var(--panel)]"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-8 w-8 shrink-0 place-items-center border border-[var(--line)] text-[var(--accent)]">
            <Mark />
          </span>
          <div className="min-w-0">
            <div className="text-[15px] font-semibold tracking-tight">AgentRoute</div>
            <div className="truncate text-[10px] tracking-[0.16em] text-[var(--muted)] uppercase">
              Intelligent AI routing
            </div>
          </div>
        </div>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Landing">
          {LINKS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => go(id)}
              className={`h-8 px-3 text-xs transition-colors duration-200 ${
                active === id ? "text-[var(--text)]" : "text-[var(--muted)] hover:text-[var(--text)]"
              }`}
              aria-current={active === id ? "true" : undefined}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <span className="hidden sm:inline-flex">
            <LaunchButton onLaunch={onLaunch}>Launch AgentRoute →</LaunchButton>
          </span>
          <button
            type="button"
            className="inline-flex h-8 items-center border border-[var(--line)] px-2.5 text-xs md:hidden"
            aria-expanded={open}
            aria-label="Open navigation"
            onClick={() => setOpen((value) => !value)}
          >
            Menu
          </button>
        </div>
      </div>
      {open && (
        <div className="border-t border-[var(--line)] pb-3 md:hidden">
          {LINKS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => go(id)}
              className="block h-10 w-full px-1 text-left text-sm text-[var(--muted)]"
            >
              {label}
            </button>
          ))}
          <LaunchButton onLaunch={onLaunch}>Launch AgentRoute →</LaunchButton>
        </div>
      )}
    </header>
  );
}
