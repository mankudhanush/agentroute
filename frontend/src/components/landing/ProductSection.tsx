import { Reveal } from "./Reveal";

const CARDS = [
  ["01", "UNDERSTAND", "Understand the request, context, complexity, capabilities, and output requirements."],
  ["02", "ROUTE", "Select the appropriate existing agent and determine the model that best fits the task requirements."],
  ["03", "EXECUTE", "Use the selected agent, model, and required tools to complete and evaluate the task."],
] as const;

export function ProductSection() {
  return (
    <section id="product" className="scroll-mt-20 border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="max-w-xl text-3xl font-semibold tracking-tight">AI Routing That Understands The Task</h2>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-[var(--muted)]">
            Different tasks need different capabilities. AgentRoute separates the decision process from
            execution so that a request can be matched with the right agent, the right model, and the right
            tools instead of relying on a single fixed model.
          </p>
        </Reveal>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {CARDS.map(([index, title, text]) => (
            <Reveal key={title}>
              <article className="lp-card h-full border border-[var(--line)] bg-[var(--panel)] p-5">
                <div className="font-mono text-[11px] text-[var(--faint)]">{index}</div>
                <h3 className="mt-3 text-sm font-semibold tracking-[0.14em]">{title}</h3>
                <p className="mt-3 text-sm leading-6 text-[var(--muted)]">{text}</p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
