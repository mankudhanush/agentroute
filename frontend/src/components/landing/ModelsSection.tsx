import { Reveal } from "./Reveal";
import { ModelField } from "./Visuals";

const FIT = ["TASK", "REQUIREMENTS", "CAPABILITY DEMAND", "COMPLEXITY", "MODEL FIT", "SELECTED MODEL"] as const;

const PROVIDERS = [
  ["Gemini", ["gemini-flash-latest", "gemini-flash-lite-latest"]],
  ["NVIDIA", ["nvidia/nemotron-3-ultra-550b-a55b", "nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b"]],
  ["Groq", ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]],
] as const;

export function ModelsSection() {
  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">The Model Is Chosen For The Task</h2>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-[var(--muted)]">
            AgentRoute does not rely on a single fixed model. Model selection is requirement-driven and
            considers the capabilities demanded by the task, availability, specialization, complexity,
            context, tools, and other routing signals.
          </p>
        </Reveal>
        <ModelField />
        <div className="mt-14 grid gap-10 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <ol className="m-0 list-none space-y-2 p-0" aria-label="Model fit pipeline">
            {FIT.map((step, index) => (
              <li key={step}>
                {index > 0 && <div className="py-1 text-center text-[var(--faint)]" aria-hidden="true">↓</div>}
                <div className="border border-[var(--line)] bg-[var(--elevated)] px-3 py-2 font-mono text-[11px] tracking-wide">
                  {step}
                </div>
              </li>
            ))}
          </ol>
          <div className="grid gap-4 sm:grid-cols-3">
            {PROVIDERS.map(([provider, models]) => (
              <Reveal key={provider}>
                <article className="h-full border border-[var(--line)] bg-[var(--panel)] p-4">
                  <h3 className="text-sm font-semibold">{provider}</h3>
                  <ul className="mt-3 space-y-2">
                    {models.map((model) => (
                      <li key={model} className="font-mono text-[11px] leading-5 break-all text-[var(--muted)]">
                        {model}
                      </li>
                    ))}
                  </ul>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
        <p className="mt-4 text-xs text-[var(--faint)]">
          These are verified callable models in the AgentRoute registry. The selector still chooses among
          available models for the task. Listed-only ids are not shown here.
        </p>
      </div>
    </section>
  );
}
