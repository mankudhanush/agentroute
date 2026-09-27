import { Reveal } from "./Reveal";

const BRANCHES = [
  ["CODING TASK", "coding branch"],
  ["BLENDER TASK", "3D branch"],
  ["BROWSER TASK", "browser branch"],
] as const;

export function ContextSection() {
  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-2">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">Context Without Cross-Contamination</h2>
          <p className="mt-4 text-sm leading-6 text-[var(--muted)]">
            AgentRoute keeps separate conversation branches. A coding task, a 3D task, and a browser task
            are not one shared subject. A follow-up returns to the branch it continues.
          </p>
          <p className="mt-4 border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-sm">
            Follow-up → returns to the correct task branch
          </p>
        </Reveal>
        <div className="space-y-3">
          {BRANCHES.map(([task, branch]) => (
            <Reveal key={task}>
              <div className="border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
                <div className="text-xs font-semibold tracking-wide">{task}</div>
                <div className="lp-branch-line mt-2 ml-3 border-l border-[var(--line)] pl-3 font-mono text-[11px] text-[var(--muted)]">
                  └── {branch}
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
