import { useEffect, useRef } from "react";
import { WAITING_STEPS } from "../display";
import type { AgentTurn, Turn } from "../types";
import { EmptyState } from "./EmptyState";
import { AssistantMessage, NoticeMessage, UserMessage } from "./Message";

type ChatPanelProps = {
  turns: Turn[];
  pending: boolean;
  activeId: string | null;
  onSelect: (turn: AgentTurn) => void;
};

export function ChatPanel({ turns, pending, activeId, onSelect }: ChatPanelProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [turns, pending]);

  return (
    <main className="scroll min-w-0 px-4 py-6 sm:px-6 lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
      {turns.length === 0 && !pending && <EmptyState />}
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
        {turns.map((turn) => {
          if (turn.kind === "user") return <UserMessage key={turn.id} text={turn.text} />;
          if (turn.kind === "notice") return <NoticeMessage key={turn.id} text={turn.text} />;
          return (
            <AssistantMessage
              key={turn.id}
              turn={turn}
              selected={turn.id === activeId}
              onSelect={onSelect}
            />
          );
        })}
        {pending && (
          <div className="rise border border-[var(--line)] bg-[var(--panel)] px-4 py-3.5" aria-busy="true">
            <p className="section-label">AgentRoute</p>
            <p className="mb-3 text-sm text-[var(--muted)]">
              Waiting on the core. None of these lines is a completed decision.
            </p>
            <ol className="m-0 list-none p-0">
              {WAITING_STEPS.map((step) => (
                <li key={step} className="flex items-center gap-3 py-1 text-sm text-[var(--muted)]">
                  <span className="h-1.5 w-1.5 border border-[var(--faint)]" />
                  {step}
                </li>
              ))}
            </ol>
          </div>
        )}
        <div ref={endRef} />
      </div>
    </main>
  );
}
