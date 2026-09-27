import { LaunchButton } from "./Reveal";
import { RoutingFlow } from "./RoutingFlow";
import { HeroField } from "./Visuals";

const PATH = ["REQUEST", "DECISION", "AGENT", "MODEL", "TOOLS", "RESULT"] as const;

export function HeroSection({ onLaunch, onArchitecture }: { onLaunch: () => void; onArchitecture: () => void }) {
  return (
    <section className="relative overflow-hidden border-b border-[var(--line)] px-4 py-16 sm:px-6 sm:py-24 lg:py-28">
      <div className="mx-auto grid max-w-6xl items-center gap-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(18rem,24rem)]">
        <div className="lp-hero-copy">
          <p className="section-label">AgentRoute</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            One Request.
            <br />
            The Right Agent.
            <br />
            The Right Model.
          </h1>
          <p className="mt-5 max-w-xl text-sm leading-6 text-[var(--muted)] sm:text-base">
            AgentRoute intelligently routes AI tasks based on what the task actually requires — selecting
            the appropriate agent, model, provider, and tools for execution.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <LaunchButton onLaunch={onLaunch}>Launch AgentRoute →</LaunchButton>
            <button
              type="button"
              onClick={onArchitecture}
              className="inline-flex h-10 items-center border border-[var(--line)] bg-[var(--bg)] px-4 text-sm transition-colors duration-200 hover:border-[var(--accent)]"
            >
              Explore Architecture
            </button>
          </div>
          <ol className="mt-8 flex flex-wrap gap-2" aria-label="Request path">
            {PATH.map((step, index) => (
              <li key={step} className="flex items-center gap-2 font-mono text-[10px] tracking-[0.12em] text-[var(--muted)]">
                {index > 0 && <span aria-hidden="true">→</span>}
                {step}
              </li>
            ))}
          </ol>
        </div>
        <div className="relative min-h-[28rem]">
          <HeroField />
          <div className="relative">
            <RoutingFlow />
          </div>
        </div>
      </div>
    </section>
  );
}
