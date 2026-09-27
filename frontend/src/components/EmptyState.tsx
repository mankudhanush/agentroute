export function EmptyState() {
  return (
    <div className="mx-auto max-w-lg pt-16">
      <p className="section-label">Conversation</p>
      <h1 className="text-2xl font-semibold tracking-tight">Route a task through the core</h1>
      <p className="mt-3 max-w-md text-sm leading-6 text-[var(--muted)]">
        The reply, the agent, the complexity, and the model all come back from AgentRoute. This
        screen only displays that result.
      </p>
    </div>
  );
}
