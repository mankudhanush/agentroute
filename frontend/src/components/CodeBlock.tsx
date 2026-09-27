import { isValidElement, type CSSProperties, type ReactElement, type ReactNode } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { CopyButton } from "./CopyButton";

const SUPPORTED = new Set(SyntaxHighlighter.supportedLanguages);

const ALIAS: Record<string, string> = {
  py: "python",
  js: "javascript",
  ts: "typescript",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  yml: "yaml",
  html: "markup",
  xml: "markup",
  svg: "markup",
  md: "markdown",
  plaintext: "plain",
  text: "plain",
  txt: "plain",
};

const syntaxStyle: Record<string, CSSProperties> = {
  'code[class*="language-"]': {
    color: "var(--text)",
    background: "none",
    fontFamily: "var(--font-mono)",
    fontSize: "0.8125rem",
    lineHeight: 1.55,
    textShadow: "none",
    whiteSpace: "pre",
  },
  'pre[class*="language-"]': {
    color: "var(--text)",
    background: "transparent",
    fontFamily: "var(--font-mono)",
    fontSize: "0.8125rem",
    lineHeight: 1.55,
    margin: 0,
    padding: "0.85rem 0.95rem",
    overflow: "auto",
    textShadow: "none",
  },
  comment: { color: "var(--hl-comment)", fontStyle: "italic" },
  prolog: { color: "var(--hl-comment)" },
  doctype: { color: "var(--hl-comment)" },
  cdata: { color: "var(--hl-comment)" },
  punctuation: { color: "var(--hl-punct)" },
  property: { color: "var(--hl-attr)" },
  tag: { color: "var(--hl-tag)" },
  boolean: { color: "var(--hl-number)" },
  number: { color: "var(--hl-number)" },
  constant: { color: "var(--hl-number)" },
  symbol: { color: "var(--hl-number)" },
  deleted: { color: "var(--hl-tag)" },
  selector: { color: "var(--hl-keyword)" },
  "attr-name": { color: "var(--hl-attr)" },
  string: { color: "var(--hl-string)" },
  char: { color: "var(--hl-string)" },
  builtin: { color: "var(--hl-function)" },
  inserted: { color: "var(--hl-string)" },
  operator: { color: "var(--hl-punct)" },
  entity: { color: "var(--hl-keyword)" },
  url: { color: "var(--hl-string)" },
  atrule: { color: "var(--hl-keyword)" },
  "attr-value": { color: "var(--hl-string)" },
  keyword: { color: "var(--hl-keyword)" },
  function: { color: "var(--hl-function)" },
  "class-name": { color: "var(--hl-function)" },
  regex: { color: "var(--hl-number)" },
  important: { color: "var(--hl-tag)", fontWeight: 650 },
  variable: { color: "var(--text)" },
};

function textOf(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

function fenceLanguage(className: string): string {
  return /language-([\w+-]+)/.exec(className)?.[1] ?? "";
}

function resolveLanguage(raw: string): string | null {
  const key = raw.trim().toLowerCase();
  if (!key) return null;
  const name = ALIAS[key] ?? key;
  return SUPPORTED.has(name) ? name : null;
}

export function CodeBlock({ children }: { children?: ReactNode }) {
  const node = (Array.isArray(children) ? children.find(isValidElement) : children) as
    | ReactElement<{ className?: string; children?: ReactNode }>
    | undefined;
  const className = node && isValidElement(node) ? (node.props.className ?? "") : "";
  const code = (node && isValidElement(node) ? textOf(node.props.children) : textOf(children)).replace(/\n$/, "");
  const label = fenceLanguage(className);
  const language = resolveLanguage(label);

  return (
    <div className="code-block">
      <div className="code-block-bar">
        <span>{label || "text"}</span>
        <CopyButton text={code} label="Copy code" />
      </div>
      {language ? (
        <SyntaxHighlighter language={language} style={syntaxStyle} useInlineStyles>
          {code}
        </SyntaxHighlighter>
      ) : (
        <pre>
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}
