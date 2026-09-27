import { Reveal } from "./Reveal";
import { ToolField } from "./Visuals";

const TOOLS = [
  ["BLENDER", "BLENDER_TOOL"],
  ["PLAYWRIGHT", "PLAYWRIGHT_TOOL"],
  ["WEB SEARCH", "WEB_SEARCH_TOOL"],
  ["CODE EXECUTION", "CODE_EXECUTION_TOOL"],
  ["FILESYSTEM", "FILESYSTEM_TOOL"],
  ["GITHUB", "GITHUB_TOOL"],
] as const;

const CHAIN = ["SELECTED AGENT", "REQUIRED CAPABILITY", "PERMITTED TOOL", "EXECUTION", "RESULT"] as const;

export function ToolsSection() {
  return (
    <section id="tools" className="scroll-mt-20 border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <h2 className="text-3xl font-semibold tracking-tight">Tools When They Are Needed</h2>
          <p className="mt-3 text-sm text-[var(--muted)]">Agents use capabilities. Tools provide execution.</p>
          <p className="mt-2 text-sm text-[var(--text)]">Tools are capabilities, not agents.</p>
        </Reveal>
        <ToolField />
        <div className="mt-14 flex flex-wrap gap-2">
          {CHAIN.map((step, index) => (
            <div key={step} className="flex items-center gap-2">
              {index > 0 && <span className="text-[var(--faint)]">↓</span>}
              <span className="border border-[var(--line)] bg-[var(--elevated)] px-2.5 py-1.5 font-mono text-[10px] tracking-wide">
                {step}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TOOLS.map(([label, id]) => (
            <Reveal key={id}>
              <article className="lp-card border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
                <div className="text-xs font-semibold tracking-wide">{label}</div>
                <div className="mt-1 font-mono text-[11px] text-[var(--faint)]">{id}</div>
              </article>
            </Reveal>
          ))}
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <Ownership from="THREE_D_AGENT" to="BLENDER_TOOL" />
          <Ownership from="WEB_AGENT" to="PLAYWRIGHT_TOOL" />
        </div>
      </div>
    </section>
  );
}

function Ownership({ from, to }: { from: string; to: string }) {
  return (
    <div className="border border-[var(--line)] bg-[var(--inset)] px-4 py-3 font-mono text-[11px] leading-6">
      {from}
      <div className="text-[var(--faint)]">↓</div>
      {to}
    </div>
  );
}
