import { Reveal } from "./Reveal";

export function CapabilitySection() {
  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-2">
        <Reveal>
          <article className="lp-card h-full border border-[var(--line)] bg-[var(--panel)] p-5">
            <h2 className="text-sm font-semibold tracking-[0.14em]">BLENDER</h2>
            <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
              Turn 3D tasks into executable Blender workflows.
            </p>
            <Chain steps={["THREE_D_AGENT", "BLENDER_TOOL", "BLENDER", "3D SCENE"]} />
          </article>
        </Reveal>
        <Reveal>
          <article className="lp-card h-full border border-[var(--line)] bg-[var(--panel)] p-5">
            <h2 className="text-sm font-semibold tracking-[0.14em]">PLAYWRIGHT</h2>
            <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
              Execute browser tasks against real web pages.
            </p>
            <Chain steps={["WEB_AGENT", "PLAYWRIGHT_TOOL", "REAL BROWSER", "RESULT"]} />
          </article>
        </Reveal>
      </div>
    </section>
  );
}

function Chain({ steps }: { steps: string[] }) {
  return (
    <ol className="mt-5 list-none space-y-1 p-0 font-mono text-[11px]">
      {steps.map((step, index) => (
        <li key={step}>
          {index > 0 && <div className="text-[var(--faint)]">↓</div>}
          {step}
        </li>
      ))}
    </ol>
  );
}
