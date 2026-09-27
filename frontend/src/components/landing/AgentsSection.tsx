import { Reveal } from "./Reveal";
import { AgentNetwork } from "./Visuals";

const AGENTS = [
  ["GENERAL_AGENT", "Everyday", "General-purpose tasks and everyday requests."],
  ["CODING_AGENT", "Code", "Software development, debugging, implementation, and code-related tasks."],
  ["REASONING_AGENT", "Analysis", "Complex reasoning, analysis, architecture, and difficult problem solving."],
  ["RESEARCH_AGENT", "Synthesis", "Research-oriented tasks requiring information gathering and synthesis."],
  ["THREE_D_AGENT", "3D", "3D and Blender-based workflows. Blender remains a tool owned by this agent."],
  ["WEB_AGENT", "Browser", "Browser-based tasks and web interaction using Playwright. Playwright remains a tool."],
] as const;

export function AgentsSection() {
  return (
    <section id="agents" className="scroll-mt-20 border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">Specialized Agents</h2>
          <p className="mt-3 text-sm text-[var(--muted)]">One platform. Multiple task-specific capabilities.</p>
        </Reveal>
        <AgentNetwork />
        <div className="mt-16 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {AGENTS.map(([name, capability, text]) => (
            <Reveal key={name}>
              <article className="lp-card lp-card-edge h-full border border-[var(--line)] bg-[var(--panel)] p-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="grid h-8 w-8 place-items-center border border-[var(--line)] text-[var(--accent)]" aria-hidden="true">
                    <svg width="12" height="12" viewBox="0 0 16 16">
                      <path d="M8 1.6 14.2 8 8 14.4 1.8 8Z" fill="none" stroke="currentColor" strokeWidth="1.2" />
                    </svg>
                  </span>
                  <span className="font-mono text-[10px] tracking-[0.14em] text-[var(--faint)] uppercase">{capability}</span>
                </div>
                <h3 className="mt-4 font-mono text-xs tracking-wide">{name}</h3>
                <p className="mt-3 text-sm leading-6 text-[var(--muted)]">{text}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
