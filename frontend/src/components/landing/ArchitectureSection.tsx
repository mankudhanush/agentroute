import { Reveal } from "./Reveal";

const LAYERS = [
  ["USER", "The request"],
  ["LAYER 1", "LAYA / DECISION LAYER", "Routing decision. Not a model, agent, provider, or tool."],
  ["LAYER 2", "AGENT SELECTION", "Task capability. One of the six existing agents."],
  ["LAYER 3", "TASK REQUIREMENTS", "What the task demands of a model."],
  ["LAYER 4", "MODEL SELECTION", "Best-fit model. The provider follows the model."],
  ["LAYER 5", "SELECTED AGENT", "The agent that executes the task."],
  ["LAYER 6", "TOOLS", "Execution capability, only when required."],
  ["LAYER 7", "EXECUTION", "The selected agent runs the task."],
  ["LAYER 8", "EVALUATION", "Result validation."],
  ["LAYER 9", "RETRY / FALLBACK", "Recovery when execution fails."],
  ["RESULT", "Returned to the user"],
] as const;

export function ArchitectureSection() {
  return (
    <section id="architecture" className="scroll-mt-20 border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-3xl">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">Built Around Clear Decision Boundaries</h2>
          <ul className="mt-6 grid gap-3 sm:grid-cols-2">
            <li className="border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-sm"><span className="font-semibold">Laya</span> <span className="text-[var(--muted)]">Routing decision</span></li>
            <li className="border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-sm"><span className="font-semibold">Agent</span> <span className="text-[var(--muted)]">Task capability</span></li>
            <li className="border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-sm"><span className="font-semibold">Model selector</span> <span className="text-[var(--muted)]">Best-fit model</span></li>
            <li className="border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-sm"><span className="font-semibold">Tool layer</span> <span className="text-[var(--muted)]">Execution capability</span></li>
          </ul>
        </Reveal>
        <ol className="lp-rail relative mt-10 list-none p-0">
          <span className="lp-particle" aria-hidden="true" />
          {LAYERS.map((layer) => {
            const [kicker, title, note] = layer.length === 3 ? layer : [layer[0], layer[0], layer[1]];
            return (
              <li key={kicker + title} className="relative pb-3 pl-10">
                <span className="absolute top-4 left-2.5 h-2 w-2 border border-[var(--accent)] bg-[var(--bg)]" />
                <div className="border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
                  <div className="font-mono text-[10px] tracking-[0.14em] text-[var(--faint)]">{kicker}</div>
                  <div className="mt-1 text-sm font-semibold">{title}</div>
                  <p className="mt-1 text-sm text-[var(--muted)]">{note}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
