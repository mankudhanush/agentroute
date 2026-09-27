import { useEffect, useRef, useState, type ReactNode } from "react";

export function Reveal({ children, className = "" }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        setShown(true);
        observer.disconnect();
      },
      { threshold: 0.16 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={`lp-reveal${shown ? " is-in" : ""} ${className}`}>
      {children}
    </div>
  );
}

export function Mark() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M8 1.4 14.6 8 8 14.6 1.4 8Z" fill="none" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

export function LaunchButton({ onLaunch, children }: { onLaunch: () => void; children: string }) {
  return (
    <button
      type="button"
      onClick={onLaunch}
      className="inline-flex h-10 items-center justify-center border border-[var(--accent)] bg-[var(--accent)] px-4 text-sm font-medium text-[var(--accent-ink)] transition-opacity duration-200 hover:opacity-90"
    >
      {children}
    </button>
  );
}
