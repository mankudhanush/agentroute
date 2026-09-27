import { useEffect, useState } from "react";

const STEPS = [
  "Incoming request",
  "“Debug this Python application.”",
  "Laya analyzing…",
  "CODING_AGENT",
  "Requirements: code, debugging",
  "Model selected",
  "Result ready",
] as const;

export function DemoSection() {
  const [motion, setMotion] = useState(true);

  useEffect(() => {
    setMotion(!window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);

  return (
    <section className="border-b border-[var(--line)] px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-xl">
        <h2 className="text-3xl font-semibold tracking-tight">A Request, Illustrated</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">
          A visual sequence only. AgentRoute does not run this example, and no result is fabricated.
        </p>
        <ol className={`lp-demo mt-8 list-none space-y-2 p-0 ${motion ? "is-run" : ""}`}>
          {STEPS.map((step) => (
            <li key={step} className="lp-demo-step border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-sm">
              {step}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
