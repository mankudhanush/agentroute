import { Reveal } from "./Reveal";

const CARDS = [
  ["01", "REQUIREMENT-DRIVEN ROUTING", "Route based on what the task needs."],
  ["02", "SPECIALIZED AGENTS", "Different tasks can use different task-oriented agents."],
  ["03", "MULTI-PROVIDER MODELS", "Use the configured model ecosystem instead of depending on one model."],
  ["04", "TOOL-AWARE EXECUTION", "Use external capabilities when the task requires them."],
  ["05", "CONTEXT-AWARE TASKS", "Keep related work together without mixing unrelated branches."],
  ["06", "EVALUATION & FALLBACK", "Validate execution and recover from failures when possible."],
] as const;

export function WhySection() {
  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">Why AgentRoute</h2>
        </Reveal>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {CARDS.map(([index, title, text]) => (
            <Reveal key={index}>
              <article className="lp-card h-full border border-[var(--line)] bg-[var(--panel)] p-5">
                <div className="font-mono text-[11px] text-[var(--faint)]">{index}</div>
                <h3 className="mt-3 text-sm font-semibold tracking-wide">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{text}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
