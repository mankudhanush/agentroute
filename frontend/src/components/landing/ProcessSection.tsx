import { Reveal } from "./Reveal";

const STEPS = [
  ["01", "USER REQUEST", "Natural-language request enters AgentRoute."],
  ["02", "LAYA", "The decision layer analyzes the task and helps determine the routing direction. Laya is not a model, agent, provider, or tool."],
  ["03", "AGENT SELECTION", "Select one of the existing specialized agents."],
  ["04", "TASK REQUIREMENTS", "Determine capability, complexity, context, reasoning, tools, and output requirements."],
  ["05", "MODEL SELECTION", "Select a model based on task requirements rather than simply using a fixed model."],
  ["06", "TOOL EXECUTION", "Use tools only when the selected task requires them."],
  ["07", "EVALUATION", "Validate the result and detect failures or incomplete execution."],
  ["08", "RETRY / FALLBACK", "Retry intelligently or fall back when execution fails."],
  ["09", "RESULT", "Return the final result to the user."],
] as const;

export function ProcessSection() {
  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="section-label">Process</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight">How AgentRoute Works</h2>
        </Reveal>
        <ol className="lp-rail relative mt-10 max-w-3xl list-none p-0">
          <span className="lp-particle" aria-hidden="true" />
          {STEPS.map(([index, title, text]) => (
            <li key={index} className="relative pb-4 pl-10">
              <span className="absolute top-4 left-2.5 h-2 w-2 border border-[var(--accent)] bg-[var(--bg)]" />
              <Reveal>
                <div className="border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
                  <div className="font-mono text-[11px] text-[var(--faint)]">{index}</div>
                  <h3 className="mt-1 text-sm font-semibold tracking-wide">{title}</h3>
                  <p className="mt-1 text-sm leading-6 text-[var(--muted)]">{text}</p>
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
