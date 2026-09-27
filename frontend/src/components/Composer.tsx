import { useEffect, useRef, useState } from "react";

type ComposerProps = {
  pending: boolean;
  onSend: (message: string) => void;
};

export function Composer({ pending, onSend }: ComposerProps) {
  const [value, setValue] = useState("");
  const field = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const element = field.current;
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.min(element.scrollHeight, 168)}px`;
  }, [value]);

  function submit() {
    const message = value.trim();
    if (!message || pending) return;
    setValue("");
    onSend(message);
  }

  return (
    <form
      className="shrink-0 border-t border-[var(--line)] bg-[var(--panel)] px-4 py-3 sm:px-5"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="mx-auto w-full max-w-6xl">
        <div
          className="flex items-end gap-2 border border-[var(--line)] bg-[var(--inset)] px-3 py-2 transition-colors duration-200 focus-within:border-[var(--accent)]"
          style={{ opacity: pending ? 0.7 : 1 }}
        >
          <label className="min-w-0 flex-1">
            <span className="sr-only">Message</span>
            <textarea
              ref={field}
              value={value}
              rows={1}
              placeholder="Ask AgentRoute anything..."
              disabled={pending}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              className="max-h-40 w-full resize-none bg-transparent py-1.5 text-sm leading-6 outline-none placeholder:text-[var(--faint)] disabled:cursor-default"
            />
          </label>
          <button
            type="submit"
            disabled={pending || !value.trim()}
            className="mb-0.5 inline-flex h-8 shrink-0 items-center gap-1.5 bg-[var(--accent)] px-3 text-xs font-medium text-[var(--accent-ink)] transition-opacity duration-200 disabled:opacity-40"
          >
            {pending ? "Sending" : "Send"}
            <ArrowIcon />
          </button>
        </div>
        <p className="mt-1.5 text-[11px] text-[var(--faint)]">Enter to send · Shift+Enter for a new line</p>
      </div>
    </form>
  );
}

function ArrowIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M3 8h10M9 4l4 4-4 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
