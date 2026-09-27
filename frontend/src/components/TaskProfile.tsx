import { text } from "../display";
import type { ChatResult, TaskProfile as Profile } from "../types";

type TaskProfileProps = {
  result: ChatResult;
};

function profileValue(profile: Profile | undefined, result: ChatResult, key: keyof Profile) {
  if (profile && key in profile && profile[key] !== undefined) return profile[key];
  return result[key as keyof ChatResult];
}

function join(values: string[] | undefined): string {
  if (!values || values.length === 0) return "—";
  return values.join(", ");
}

export function TaskProfile({ result }: TaskProfileProps) {
  const profile = result.task_profile;
  const rows: Array<[string, string]> = [
    ["Capability", text(profileValue(profile, result, "capability"))],
    ["Complexity", text(profile?.complexity_name ?? result.complexity_name ?? result.complexity)],
    ["Breadth", text(profile?.breadth)],
    ["Output", text(profileValue(profile, result, "output_type"))],
    ["Tools", join(profile?.required_tools ?? result.required_tools)],
    ["Tool requirement", text(profileValue(profile, result, "requires_tools"))],
    ["Context", text(profileValue(profile, result, "context_dependent"))],
  ];

  return (
    <details className="border border-[var(--line)] bg-[var(--elevated)]">
      <summary className="cursor-pointer px-3.5 py-2.5 text-[11px] font-semibold tracking-[0.14em] text-[var(--faint)] uppercase">
        Task profile
      </summary>
      <dl className="kv border-t border-[var(--line)] px-3.5 py-3">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
