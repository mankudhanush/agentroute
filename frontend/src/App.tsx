import { useState } from "react";
import type { Turn } from "./types";
import { BackendNote } from "./components/BackendNote";
import { ChatPanel } from "./components/ChatPanel";
import { Composer } from "./components/Composer";
import { Header } from "./components/Header";
import { Landing } from "./components/Landing";
import { RoutingInspector } from "./components/RoutingInspector";
import { useAgentRoute } from "./hooks/useAgentRoute";

export default function App() {
  const route = useAgentRoute();
  const hasMessages = route.turns.length > 0 || route.pending;
  const [blenderEnabled, setBlenderEnabled] = useState(false);
  const [playwrightEnabled, setPlaywrightEnabled] = useState(false);
  const [entered, setEntered] = useState(false);
  const browserActive = latestBrowserActive(route.turns);

  if (!entered) {
    return <Landing onEnter={() => setEntered(true)} />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <BackendNote />
      <Header
        connected={route.connected}
        dark={route.dark}
        hasMessages={hasMessages}
        onToggleTheme={route.toggleTheme}
        onNew={route.newConversation}
        browserActive={browserActive}
      />
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        <PluginSidebar
          blenderEnabled={blenderEnabled}
          playwrightEnabled={playwrightEnabled}
          onToggleBlender={() => setBlenderEnabled((enabled) => !enabled)}
          onTogglePlaywright={() => setPlaywrightEnabled((enabled) => !enabled)}
          browserActive={browserActive}
        />
        <ChatPanel
          turns={route.turns}
          pending={route.pending}
          activeId={route.active?.id ?? null}
          onSelect={route.setActive}
        />
        <RoutingInspector
          pending={route.pending}
          prompt={route.pending ? route.pendingPrompt : (route.active?.prompt ?? null)}
          result={route.pending ? null : (route.active?.result ?? null)}
        />
      </div>
      <Composer
        pending={route.pending}
        onSend={(message) => void route.onSend(message, blenderEnabled, playwrightEnabled)}
      />
    </div>
  );
}

function latestBrowserActive(turns: Turn[]): boolean {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    const turn = turns[index];
    if (turn.kind === "agent") return Boolean(turn.result.browser_active);
  }
  return false;
}

type PluginSidebarProps = {
  blenderEnabled: boolean;
  playwrightEnabled: boolean;
  browserActive: boolean;
  onToggleBlender: () => void;
  onTogglePlaywright: () => void;
};

function PluginSidebar({
  blenderEnabled,
  playwrightEnabled,
  browserActive,
  onToggleBlender,
  onTogglePlaywright,
}: PluginSidebarProps) {
  return (
    <aside className="scroll shrink-0 border-b border-[var(--line)] bg-[var(--panel)] lg:w-60 lg:overflow-y-auto lg:border-r lg:border-b-0">
      <div className="flex flex-col gap-3 px-4 py-4">
        <p className="section-label">Plugins</p>
        <div className="flex flex-col gap-2">
          <PluginToggle label="Blender" enabled={blenderEnabled} onToggle={onToggleBlender} />
          <PluginToggle
            label="Playwright"
            enabled={playwrightEnabled}
            onToggle={onTogglePlaywright}
          />
        </div>
        {blenderEnabled && (
          <PluginNote
            title="Blender"
            heading="3D Workspace"
            detail="Blender capability enabled."
            status="Ready for Blender tasks."
          />
        )}
        {browserActive && (
          <PluginNote
            title="Playwright"
            heading="Browser Active · Playwright"
            detail="A Chromium window is open."
            status="The page stays open for follow-up actions."
          />
        )}
        {playwrightEnabled && !browserActive && (
          <PluginNote
            title="Playwright"
            heading="Browser Workspace"
            detail="Playwright capability enabled."
            status="Ready for browser tasks."
          />
        )}
      </div>
    </aside>
  );
}

function PluginToggle({
  label,
  enabled,
  onToggle,
}: {
  label: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={enabled}
      onClick={onToggle}
      className="inline-flex h-8 w-full items-center gap-2 border border-[var(--line)] bg-[var(--bg)] px-2.5 text-left text-xs transition-colors duration-200 hover:border-[var(--accent)] hover:text-[var(--text)]"
    >
      <span
        aria-hidden="true"
        className="grid h-3.5 w-3.5 shrink-0 place-items-center border border-[var(--line)] text-[10px] leading-none text-[var(--accent)]"
      >
        {enabled ? "✓" : ""}
      </span>
      {label}
    </button>
  );
}

function PluginNote({
  title,
  heading,
  detail,
  status,
}: {
  title: string;
  heading: string;
  detail: string;
  status: string;
}) {
  return (
    <div className="border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2.5">
      <p className="section-label mb-1.5">{title}</p>
      <p className="text-sm text-[var(--text)]">{heading}</p>
      <p className="mt-1 text-xs leading-5 text-[var(--muted)]">{detail}</p>
      <p className="text-xs leading-5 text-[var(--muted)]">{status}</p>
    </div>
  );
}
