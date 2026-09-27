import type { RoutingSnapshot } from "./types";

/** Waiting copy only. These lines are not routing results. */
export const WAITING_STEPS = [
  "Analyzing request",
  "Routing through Laya",
  "Selecting model",
  "Generating response",
] as const;

export function text(value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "string" && value.trim()) return value;
  return "—";
}

export function complexityCode(result: RoutingSnapshot): string {
  if (typeof result.complexity_level === "number") return `L${result.complexity_level}`;
  return result.complexity?.trim() || "—";
}

export function complexityLabel(result: RoutingSnapshot): string {
  return result.complexity_name?.trim() || result.complexity?.trim() || "—";
}

/** The model id after the provider prefix. Still the API string. */
export function modelSlug(id: string | null | undefined): string {
  if (!id) return "—";
  const slash = id.lastIndexOf("/");
  return slash >= 0 ? id.slice(slash + 1) : id;
}

/**
 * Split a core `model_reason` on its own "Deciding factors:" clause.
 * Factors are substrings of that field, not labels invented in the UI.
 */
export function reasonParts(reason: string): { lead: string; factors: string[]; tail: string } {
  const marker = "Deciding factors:";
  const index = reason.indexOf(marker);
  if (index === -1) return { lead: reason.trim(), factors: [], tail: "" };
  const lead = reason.slice(0, index).trim();
  const rest = reason.slice(index + marker.length).trim();
  const factors: string[] = [];
  const tails: string[] = [];
  for (const part of rest.split(/,\s+/)) {
    const sentence = part.search(/\.\s+/);
    if (sentence === -1) {
      const factor = part.replace(/\.$/, "").trim();
      if (factor) factors.push(factor);
    } else {
      const factor = part.slice(0, sentence).trim();
      const extra = part.slice(sentence + 1).trim();
      if (factor) factors.push(factor);
      if (extra) tails.push(extra);
    }
  }
  return { lead, factors, tail: tails.join(" ") };
}
