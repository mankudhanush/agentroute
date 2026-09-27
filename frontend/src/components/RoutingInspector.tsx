import { useEffect, useState } from "react";
import {
  WAITING_STEPS,
  complexityCode,
  complexityLabel,
  reasonParts,
  text,
} from "../display";
import type { ChatResult } from "../types";
import { ModelCard } from "./ModelCard";
import { RoutingPipeline } from "./RoutingPipeline";
import { TaskProfile } from "./TaskProfile";

type RoutingInspectorProps = {
  pending: boolean;
  prompt: string | null;
  result: ChatResult | null;
};

export function RoutingInspector({ pending, prompt, result }: RoutingInspectorProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!pending) {
      setElapsed(0);
      return;
    }
    const started = Date.now();
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [pending]);

  return (
    <aside className="scroll min-h-0 min-w-0 border-t border-[var(--line)] bg-[var(--panel)] lg:w-[24.5rem] lg:shrink-0 lg:overflow-y-auto lg:border-t-0 lg:border-l">
      <div className="flex flex-col gap-5 px-4 py-5">
        <div>
          <p className="section-label mb-1">Routing inspector</p>
          <p className="text-xs leading-5 text-[var(--muted)]">Values are copied from the core response.</p>
        </div>

        {pending && (
          <div aria-busy="true">
            <p className="mb-3 text-sm leading-6 text-[var(--muted)]">
              Waiting on the model provider{elapsed > 0 ? ` · ${elapsed}s` : ""}. Nothing below is a
              decision until the core responds.
            </p>
            <ol className="mb-4 list-none p-0">
              {WAITING_STEPS.map((step) => (
                <li key={step} className="flex items-center gap-3 py-1 text-sm text-[var(--muted)]">
                  <span className="h-1.5 w-1.5 border border-[var(--faint)]" />
                  {step}
                </li>
              ))}
            </ol>
            <RoutingPipeline prompt={prompt} result={null} pending />
          </div>
        )}

        {!pending && !result && (
          <p className="text-sm leading-6 text-[var(--muted)]">
            Send a prompt. The decision layer, agent, complexity, and model will appear here from
            the API response.
          </p>
        )}

        {!pending && result && <ResultView prompt={prompt} result={result} />}
      </div>
    </aside>
  );
}

function ResultView({ prompt, result }: { prompt: string | null; result: ChatResult }) {
  const reason = result.model_reason?.trim() ?? "";
  const parts = reason ? reasonParts(reason) : null;
  const code = complexityCode(result);
  const name = complexityLabel(result);

  return (
    <div className="flex flex-col gap-4">
      {result.fallback_used && (
        <p className="border border-[var(--warn)] px-3 py-2 text-xs leading-5 text-[var(--warn)]">
          {result.routing_reason || "The decision layer used its fallback."}
          {result.laya_error && (
            <span className="mt-1 block opacity-80">Cause: {result.laya_error}</span>
          )}
        </p>
      )}

      <RoutingPipeline prompt={prompt} result={result} pending={false} />

      <section className="border border-[var(--line)] bg-[var(--elevated)] px-3.5 py-3">
        <h2 className="section-label">Decision layer</h2>
        <p className="text-lg font-semibold tracking-tight">{text(result.decision_layer ?? result.policy)}</p>
        {typeof result.confidence === "number" && (
          <p className="mt-1 text-xs text-[var(--muted)]">Confidence {text(result.confidence)}</p>
        )}
      </section>

      {result.operation && result.operation !== "create" && (
        <section className="border border-[var(--line)] bg-[var(--elevated)] px-3.5 py-3">
          <h2 className="section-label">Operation</h2>
          <p className="text-lg font-semibold tracking-tight uppercase">{result.operation}</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {result.has_artifact
              ? `Applied to the stored artifact (${result.artifact_chars ?? 0} chars)`
              : "No stored artifact for this branch"}
          </p>
        </section>
      )}

      <section className="border border-[var(--line)] bg-[var(--elevated)] px-3.5 py-3">
        <h2 className="section-label">Selected agent</h2>
        <p className="text-lg font-semibold tracking-tight break-all">{text(result.selected_agent)}</p>
        {result.intent && <p className="mt-1 text-xs text-[var(--muted)]">Intent {result.intent}</p>}
      </section>

      <section className="border border-[var(--line)] bg-[var(--elevated)] px-3.5 py-3">
        <h2 className="section-label">Complexity</h2>
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-2xl font-semibold tracking-tight">{code}</span>
          <span className="text-xs font-semibold tracking-[0.14em] text-[var(--muted)] uppercase">{name}</span>
        </div>
      </section>

      <ModelCard result={result} />

      <section className="border border-[var(--line)] bg-[var(--elevated)] px-3.5 py-3">
        <h2 className="section-label">Why this model</h2>
        {parts ? (
          <>
            {parts.lead && <p className="text-sm leading-6">{parts.lead}</p>}
            {parts.factors.length > 0 && (
              <ul className="mt-3 flex list-none flex-col gap-2 p-0">
                {parts.factors.map((factor) => (
                  <li key={factor} className="flex gap-2 text-sm leading-5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 bg-[var(--accent)]" />
                    <span>{factor}</span>
                  </li>
                ))}
              </ul>
            )}
            {parts.tail && <p className="mt-3 text-sm leading-6 text-[var(--muted)]">{parts.tail}</p>}
          </>
        ) : (
          <p className="text-sm leading-6 text-[var(--muted)]">The core did not return a selection reason.</p>
        )}
      </section>

      {result.routing_reason && !result.fallback_used && (
        <p className="text-xs leading-5 text-[var(--muted)]">{result.routing_reason}</p>
      )}

      <TaskProfile result={result} />
      <TechnicalDetail result={result} />
    </div>
  );
}

function TechnicalDetail({ result }: { result: ChatResult }) {
  const rows: Array<[string, string]> = [
    ["Policy", text(result.policy)],
    ["Source", text(result.complexity_source)],
    ["Matched", text(result.matched_capabilities?.join(", "))],
    ["Fallbacks", text(result.model_fallbacks?.join(", "))],
    ["Latency", typeof result.latency_ms === "number" ? `${result.latency_ms} ms` : "—"],
    ["Outcome", text(result.outcome_score)],
  ];

  return (
    <details className="border border-[var(--line)] bg-[var(--elevated)]">
      <summary className="cursor-pointer px-3.5 py-2.5 text-[11px] font-semibold tracking-[0.14em] text-[var(--faint)] uppercase">
        Technical detail
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
