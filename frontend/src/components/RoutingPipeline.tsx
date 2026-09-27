import { complexityCode, complexityLabel } from "../display";
import type { ChatResult } from "../types";

type RoutingPipelineProps = {
  prompt: string | null;
  result: ChatResult | null;
  pending: boolean;
};

type Stage = {
  label: string;
  value: string;
};

function stagesFor(prompt: string | null, result: ChatResult | null, pending: boolean): Stage[] {
  if (pending || !result) {
    return [
      { label: "Prompt", value: prompt?.trim() || "Waiting" },
      { label: "Layer", value: "Waiting" },
      { label: "Agent", value: "Waiting" },
      { label: "Complexity", value: "Waiting" },
      { label: "Model", value: "Waiting" },
      { label: "Provider", value: "Waiting" },
    ];
  }
  const code = complexityCode(result);
  const name = complexityLabel(result);
  const complexity = code === "—" ? name : name === "—" || name === code ? code : `${code} · ${name}`;
  return [
    { label: "Prompt", value: prompt?.trim() || "—" },
    { label: "Layer", value: result.decision_layer ?? result.policy ?? "—" },
    { label: "Agent", value: result.selected_agent ?? "—" },
    { label: "Complexity", value: complexity },
    { label: "Model", value: result.selected_model || "—" },
    { label: "Provider", value: result.model_provider || "—" },
  ];
}

export function RoutingPipeline({ prompt, result, pending }: RoutingPipelineProps) {
  const stages = stagesFor(prompt, result, pending);

  return (
    <ol className="m-0 list-none p-0" aria-label="Routing pipeline">
      {stages.map((stage, index) => (
        <li key={stage.label} className="grid grid-cols-[1.25rem_minmax(0,1fr)]">
          <div className="flex flex-col items-center">
            <span
              className="mt-3 h-2 w-2 shrink-0 border border-[var(--accent)]"
              style={{ background: pending ? "transparent" : "var(--accent)" }}
            />
            {index < stages.length - 1 && (
              <span className={pending ? "rail-flow my-1 w-px flex-1" : "my-1 w-px flex-1 bg-[var(--line)]"} />
            )}
          </div>
          <div className={index < stages.length - 1 ? "pb-2" : ""}>
            <div className="border border-[var(--line)] bg-[var(--elevated)] px-2.5 py-2">
              <div className="text-[10px] font-semibold tracking-[0.14em] text-[var(--faint)] uppercase">
                {stage.label}
              </div>
              <div
                className="mt-0.5 font-mono text-xs leading-5 break-all"
                style={{ color: pending && stage.label !== "Prompt" ? "var(--faint)" : "var(--text)" }}
                title={stage.value}
              >
                {stage.value}
              </div>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
