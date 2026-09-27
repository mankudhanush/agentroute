import { Reveal } from "./Reveal";

const STEPS = ["Agent", "Permissions", "Allowed Tools", "Allowed Resources", "Execution"] as const;

export function SecuritySection() {
  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">Capability Boundaries By Design</h2>
          <p className="mt-4 max-w-2xl text-sm leading-6 text-[var(--muted)]">
            An agent can use only the tools listed for that agent. THREE_D_AGENT is permitted to use
            BLENDER_TOOL. WEB_AGENT is permitted to use PLAYWRIGHT_TOOL. Tool use stays inside that
            permission. Prompt-injection handling and human approval for high-risk operations are design
            boundaries, not a separate security product in this application.
          </p>
        </Reveal>
        <ol className="mt-8 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          {STEPS.map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              {index > 0 && <span className="hidden text-[var(--faint)] sm:inline">↓</span>}
              <span className="border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-sm">{step}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
