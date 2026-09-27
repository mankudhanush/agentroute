const STEPS = [
  ["USER REQUEST", ""],
  ["LAYA", "Decision layer"],
  ["AGENT SELECTED", "One existing agent"],
  ["MODEL SELECTION", "Requirement fit"],
  ["TOOLS IF NEEDED", "Not an agent"],
  ["EXECUTION", ""],
] as const;

export function RoutingFlow() {
  return (
    <div className="lp-rail border border-[var(--line)] bg-[color-mix(in_srgb,var(--panel)_82%,transparent)] p-4 backdrop-blur-[2px] sm:p-5" aria-hidden="true">
      <span className="lp-particle" />
      <ol className="m-0 list-none space-y-3 p-0">
        {STEPS.map(([title, note], index) => (
          <li key={title} className="relative pl-8">
            <span
              className="lp-node absolute top-3 left-2.5 h-2 w-2 border border-[var(--accent)] bg-[var(--panel)]"
              style={{ animationDelay: `${index * 1.1}s` }}
            />
            <div className="border border-[var(--line)] bg-[var(--elevated)] px-3 py-2.5">
              <div className="font-mono text-[11px] tracking-[0.14em] text-[var(--text)]">{title}</div>
              {note && <div className="mt-0.5 text-[11px] text-[var(--faint)]">{note}</div>}
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[11px] text-[var(--faint)]">Illustration only. No request is sent.</p>
    </div>
  );
}
