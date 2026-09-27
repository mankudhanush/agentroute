export function HeroField() {
  return (
    <svg className="lp-visual pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 420 560" aria-hidden="true">
      <g className="lp-dash" fill="none" stroke="var(--line)" strokeWidth="1">
        <path d="M210 48 V500" />
        <path d="M210 140 H320" />
        <path d="M210 250 H100" />
        <path d="M210 360 H330" />
      </g>
      <FlowDot />
      {[
        [210, 48, "USER"],
        [210, 140, "LAYA"],
        [210, 250, "AGENT"],
        [210, 360, "MODEL"],
        [210, 450, "TOOLS"],
        [210, 520, "RESULT"],
      ].map(([x, y, label]) => (
        <g key={String(label)}>
          <circle className="lp-node-dot" cx={Number(x)} cy={Number(y)} r="4" />
          <text x={Number(x) + 14} y={Number(y) + 4} fill="var(--faint)" fontSize="10" fontFamily="ui-monospace, monospace">
            {label}
          </text>
        </g>
      ))}
    </svg>
  );
}

const AGENT_NODES = ["GENERAL", "RESEARCH", "CODING", "REASONING", "WEB", "3D"] as const;

export function AgentNetwork() {
  const nodes = [
    [320, 46, "GENERAL"],
    [92, 168, "RESEARCH"],
    [548, 168, "CODING"],
    [320, 250, "REASONING"],
    [196, 318, "WEB"],
    [444, 318, "3D"],
  ] as const;
  return (
    <>
      <ol className="mx-auto mt-12 max-w-xs list-none space-y-2 p-0 sm:hidden" aria-label="AgentRoute at the center of the six existing agents">
        <li className="border border-[var(--accent)] bg-[var(--panel)] px-3 py-2 text-center font-mono text-[11px] tracking-wide">AGENTROUTE</li>
        {AGENT_NODES.map((name) => (
          <li key={name} className="border border-[var(--line)] px-3 py-2 text-center font-mono text-[11px] tracking-wide text-[var(--muted)]">{name}</li>
        ))}
      </ol>
    <svg className="lp-visual mx-auto mt-12 hidden h-auto w-full max-w-3xl sm:block" viewBox="0 0 640 360" role="img" aria-label="AgentRoute at the center of the six existing agents">
      <g className="lp-dash" fill="none" stroke="var(--line)" strokeWidth="1">
        {nodes.map(([x, y]) => (
          <path key={`${x}-${y}`} d={`M320 180 L${x} ${y}`} />
        ))}
      </g>
      {nodes.map(([x, y, label]) => (
        <g key={label}>
          <circle className="lp-node-dot" cx={x} cy={y} r="4" />
          <text x={x} y={y - 14} textAnchor="middle" fill="var(--muted)" fontSize="16" fontFamily="ui-monospace, monospace">
            {label}
          </text>
        </g>
      ))}
      <rect x="262" y="164" width="116" height="32" fill="var(--panel)" stroke="var(--accent)" />
      <text x="320" y="184" textAnchor="middle" fill="var(--text)" fontSize="11" fontFamily="ui-monospace, monospace">
        AGENTROUTE
      </text>
    </svg>
    </>
  );
}

const MODEL_STEPS = ["TASK", "REQUIREMENTS", "CAPABILITY", "MODEL FIT", "SELECTED MODEL"] as const;

export function ModelField() {
  const steps = MODEL_STEPS;
  return (
    <>
      <ol className="mx-auto mt-12 max-w-xs list-none space-y-2 p-0 sm:hidden" aria-hidden="true">
        {MODEL_STEPS.map((step) => (
          <li key={step} className="border border-[var(--line)] px-3 py-2 text-center font-mono text-[11px] tracking-wide">{step}</li>
        ))}
        <li className="pt-2 text-center font-mono text-[10px] tracking-wide text-[var(--faint)]">Gemini · NVIDIA · Groq</li>
      </ol>
    <svg className="lp-visual mx-auto mt-12 hidden h-auto w-full max-w-xl sm:block" viewBox="0 0 520 280" aria-hidden="true">
      <g className="lp-dash" fill="none" stroke="var(--line)" strokeWidth="1">
        <path d="M70 28 V252" />
        <path d="M70 90 H250" />
        <path d="M70 160 H250" />
        <path d="M70 230 H250" />
      </g>
      <circle className="lp-flow-model" cx="70" cy="28" r="2.5" fill="var(--accent)" />
      {steps.map((label, index) => (
        <g key={label}>
          <circle className="lp-node-dot" cx="70" cy={28 + index * 56} r="4" />
          <text x="86" y={32 + index * 56} fill="var(--muted)" fontSize="13" fontFamily="ui-monospace, monospace">
            {label}
          </text>
        </g>
      ))}
      <text x="270" y="94" fill="var(--faint)" fontSize="13" fontFamily="ui-monospace, monospace">Gemini</text>
      <text x="270" y="164" fill="var(--faint)" fontSize="13" fontFamily="ui-monospace, monospace">NVIDIA</text>
      <text x="270" y="234" fill="var(--faint)" fontSize="13" fontFamily="ui-monospace, monospace">Groq</text>
    </svg>
    </>
  );
}

const TOOL_MARKS = ["Blender", "Playwright", "Web Search", "Code", "Filesystem", "GitHub"] as const;

export function ToolField() {
  return (
    <div className="mt-10 border border-[var(--line)] bg-[var(--inset)] p-4 sm:p-6">
      <svg className="lp-visual mx-auto h-28 w-full max-w-md" viewBox="0 0 320 110" aria-hidden="true">
        <path className="lp-dash" d="M160 8 V96" fill="none" stroke="var(--line)" strokeWidth="1" />
        {["AGENT", "CAPABILITY", "TOOL", "EXECUTION"].map((label, index) => (
          <g key={label}>
            <circle className="lp-node-dot" cx="160" cy={12 + index * 28} r="3.5" />
            <text x="176" y={16 + index * 28} fill="var(--muted)" fontSize="14" fontFamily="ui-monospace, monospace">
              {label}
            </text>
          </g>
        ))}
      </svg>
      <ul className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {TOOL_MARKS.map((name) => (
          <li key={name} className="border border-[var(--line)] bg-[var(--panel)] px-2 py-3 text-center">
            <Mark />
            <div className="mt-2 text-[10px] tracking-wide text-[var(--muted)]">{name}</div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-center text-xs text-[var(--faint)]">Tools are capabilities, not agents.</p>
    </div>
  );
}

export function ConvergeField() {
  return (
    <svg className="lp-visual pointer-events-none absolute inset-x-0 top-0 h-40 w-full" viewBox="0 0 800 160" aria-hidden="true">
      <g className="lp-dash" fill="none" stroke="var(--line)" strokeWidth="1">
        <path d="M40 20 L400 120" />
        <path d="M160 10 L400 120" />
        <path d="M400 8 L400 120" />
        <path d="M640 10 L400 120" />
        <path d="M760 20 L400 120" />
      </g>
      <circle className="lp-node-dot" cx="400" cy="124" r="5" />
    </svg>
  );
}

function FlowDot() {
  return <circle className="lp-flow-y" cx="210" cy="48" r="2.5" fill="var(--accent)" />;
}

function Mark() {
  return (
    <svg className="mx-auto" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <path d="M8 1.6 14.2 8 8 14.4 1.8 8Z" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}
