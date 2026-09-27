import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AgentTurn } from "../types";
import { BlenderScene } from "./BlenderScene";
import { CodeBlock } from "./CodeBlock";
import { CopyButton } from "./CopyButton";

type UserMessageProps = {
  text: string;
};

export function UserMessage({ text }: UserMessageProps) {
  return (
    <article className="rise ml-auto w-full max-w-[40rem]">
      <p className="section-label text-right">You</p>
      <div className="border border-[var(--line)] bg-[var(--user)] px-3.5 py-3 text-sm leading-6 whitespace-pre-wrap">
        {text}
      </div>
    </article>
  );
}

type AssistantMessageProps = {
  turn: AgentTurn;
  selected: boolean;
  onSelect: (turn: AgentTurn) => void;
};

export function AssistantMessage({ turn, selected, onSelect }: AssistantMessageProps) {
  const failed = turn.result.response_success === false;
  const model = turn.result.selected_model;
  const provider = turn.result.model_provider;
  const meta = [model, provider].filter((part) => part && String(part).trim()).join(" · ");

  return (
    <article
      className="rise w-full max-w-[46rem] border bg-[var(--panel)] px-4 py-3.5 shadow-[var(--shadow)] transition-colors duration-200"
      style={{ borderColor: selected ? "var(--accent)" : failed ? "var(--bad)" : "var(--line)" }}
      onClick={(event) => {
        const target = event.target as HTMLElement;
        if (target.closest("a, button")) return;
        onSelect(turn);
      }}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="section-label mb-1">AgentRoute</p>
          <p className="text-sm font-medium tracking-tight" style={{ color: failed ? "var(--bad)" : undefined }}>
            {turn.result.selected_agent ?? "AgentRoute"}
            {failed ? " · execution failed" : ""}
          </p>
          {meta && <p className="mt-1 font-mono text-[11px] text-[var(--muted)] break-all">{meta}</p>}
        </div>
        {turn.text.trim() && <CopyButton text={turn.text} label="Copy response" />}
      </div>
      <div className="md text-sm leading-6">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            ),
            pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          }}
        >
          {turn.text || "The core returned an empty response."}
        </ReactMarkdown>
      </div>
      <BlenderScene sceneId={turn.result.blender_scene?.scene_id} />
    </article>
  );
}

export function NoticeMessage({ text }: { text: string }) {
  return (
    <p className="rise border border-[var(--bad)] bg-[var(--panel)] px-3.5 py-3 text-sm leading-6 text-[var(--bad)]">
      {text}
    </p>
  );
}
