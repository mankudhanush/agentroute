import { modelSlug, text } from "../display";
import type { ChatResult } from "../types";

type ModelCardProps = {
  result: ChatResult;
};

export function ModelCard({ result }: ModelCardProps) {
  const id = result.selected_model ?? "";
  const slug = modelSlug(id || null);
  const showId = Boolean(id) && slug !== id;

  return (
    <section className="border border-[var(--line)] bg-[var(--elevated)] px-3.5 py-3 shadow-[var(--shadow)]">
      <h2 className="section-label">Selected model</h2>
      <p className="text-lg leading-6 font-semibold tracking-tight break-all">{slug}</p>
      {showId && <p className="mt-1 font-mono text-[11px] leading-5 text-[var(--muted)] break-all">{id}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="border border-[var(--line)] bg-[var(--panel)] px-2 py-1 font-mono text-[10px] tracking-[0.14em] text-[var(--text)] uppercase">
          {text(result.model_provider)}
        </span>
        {typeof result.model_tier === "number" && (
          <span className="text-[11px] text-[var(--muted)]">Tier {result.model_tier}</span>
        )}
      </div>
    </section>
  );
}
