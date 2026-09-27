import { useEffect, useState } from "react";
import { StatusBadge } from "./StatusBadge";

type HeaderProps = {
  connected: boolean | null;
  dark: boolean;
  hasMessages: boolean;
  browserActive?: boolean;
  onToggleTheme: () => void;
  onNew: () => void;
};

export function Header({ connected, dark, hasMessages, browserActive = false, onToggleTheme, onNew }: HeaderProps) {
  const [confirm, setConfirm] = useState(false);
  const status =
    connected === null ? "Checking core" : connected ? "Core connected" : "Core unavailable";
  const tone = connected ? "ok" : connected === false ? "bad" : "neutral";

  useEffect(() => {
    if (!confirm) return;
    const timer = window.setTimeout(() => setConfirm(false), 4000);
    return () => window.clearTimeout(timer);
  }, [confirm]);

  function startNew() {
    if (!hasMessages) {
      onNew();
      return;
    }
    if (!confirm) {
      setConfirm(true);
      return;
    }
    setConfirm(false);
    onNew();
  }

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-[var(--line)] bg-[var(--panel)] px-4 sm:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center border border-[var(--line)] text-[var(--accent)]">
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M8 1.4 14.6 8 8 14.6 1.4 8Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.3"
            />
          </svg>
        </span>
        <div className="min-w-0">
          <div className="text-[15px] font-semibold tracking-tight">AgentRoute</div>
          <div className="truncate text-xs text-[var(--muted)]">Intelligent AI routing</div>
        </div>
      </div>
      <div className="flex items-center gap-2 sm:gap-3">
        <span className="hidden sm:inline-flex">
          <StatusBadge tone={tone} pulse={connected === true}>
            {status}
          </StatusBadge>
        </span>
        {browserActive && (
          <StatusBadge tone="ok" pulse>
            Browser Active · Playwright
          </StatusBadge>
        )}
        <button
          type="button"
          onClick={onToggleTheme}
          aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
          className="inline-flex h-8 items-center gap-1.5 border border-[var(--line)] bg-[var(--bg)] px-2.5 text-xs text-[var(--muted)] transition-colors duration-200 hover:text-[var(--text)]"
        >
          {dark ? <SunIcon /> : <MoonIcon />}
          Theme
        </button>
        <button
          type="button"
          onClick={startNew}
          className="inline-flex h-8 items-center gap-1.5 border border-[var(--line)] bg-[var(--bg)] px-2.5 text-xs transition-colors duration-200 hover:border-[var(--accent)] hover:text-[var(--text)]"
        >
          <PlusIcon />
          {confirm ? "Clear chat" : "New"}
        </button>
      </div>
    </header>
  );
}

function SunIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="2.4" fill="none" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M8 1.6v1.6M8 12.8v1.6M1.6 8h1.6M12.8 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M10.2 2.2a5.2 5.2 0 1 0 3.6 8.8 5.6 5.6 0 0 1-3.6-8.8Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.3"
      />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M8 3.2v9.6M3.2 8h9.6" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
