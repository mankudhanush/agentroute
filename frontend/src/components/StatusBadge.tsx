type StatusBadgeProps = {
  tone?: "ok" | "bad" | "neutral" | "accent";
  pulse?: boolean;
  children: string;
};

const tones = {
  ok: "var(--ok)",
  bad: "var(--bad)",
  neutral: "var(--faint)",
  accent: "var(--accent)",
};

export function StatusBadge({ tone = "neutral", pulse = false, children }: StatusBadgeProps) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-[var(--muted)]">
      <span
        className={pulse ? "live-dot h-1.5 w-1.5 rounded-full" : "h-1.5 w-1.5 rounded-full"}
        style={{ background: tones[tone] }}
      />
      {children}
    </span>
  );
}
