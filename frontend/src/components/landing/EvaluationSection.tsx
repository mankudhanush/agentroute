import { Reveal } from "./Reveal";

export function EvaluationSection() {
  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto grid max-w-6xl items-start gap-10 lg:grid-cols-2">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">Execution Is Not The End</h2>
          <p className="mt-4 text-sm leading-6 text-[var(--muted)]">
            AgentRoute is designed to detect incomplete execution, invalid tool results, failures, and
            other execution problems before returning the final result. A failed model call can continue
            through that agent’s fallback chain. There is no separate evaluation service.
          </p>
        </Reveal>
        <div className="border border-[var(--line)] bg-[var(--panel)] p-5 font-mono text-[11px] leading-6">
          <div>EXECUTE</div>
          <div className="text-[var(--faint)]">↓</div>
          <div>VALIDATE</div>
          <div className="text-[var(--faint)]">↓</div>
          <div>SUCCESS?</div>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <div className="border border-[var(--line)] p-3">
              YES
              <div className="text-[var(--faint)]">↓</div>
              RESULT
            </div>
            <div className="border border-[var(--line)] p-3">
              NO
              <div className="text-[var(--faint)]">↓</div>
              RETRY
              <div className="text-[var(--faint)]">↓</div>
              FALLBACK
              <div className="text-[var(--faint)]">↓</div>
              RESULT
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
