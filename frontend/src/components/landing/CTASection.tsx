import { LaunchButton } from "./Reveal";
import { ConvergeField } from "./Visuals";

export function CTASection({ onLaunch }: { onLaunch: () => void }) {
  return (
    <section className="lp-cta relative overflow-hidden border-b border-[var(--line)] px-4 py-28 text-center sm:px-6 sm:py-36">
      <ConvergeField />
      <div className="relative pt-16">
      <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Ready to Route Your Next Task?</h2>
      <p className="mx-auto mt-4 max-w-lg text-sm leading-6 text-[var(--muted)]">
        Give AgentRoute a request. Let the system determine how it should be handled.
      </p>
      <div className="relative mt-8">
        <LaunchButton onLaunch={onLaunch}>Launch AgentRoute →</LaunchButton>
      </div>
      </div>
    </section>
  );
}
