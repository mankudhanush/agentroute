import type { ChatResult, ConversationPayload } from "../types";

const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const CHAT_TIMEOUT_MS = 240_000;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
  }
  if (status === 422) return "Enter a message and try again.";
  return `The API returned status ${status}.`;
}

async function readBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function checkHealth(): Promise<boolean> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(`${BASE}/api/health`, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function sendChat(
  message: string,
  conversationId: string | null,
  blender = true,
  playwright = true,
): Promise<ChatResult> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        blender,
        playwright,
      }),
      signal: controller.signal,
    });
    const data = await readBody(response);
    if (!response.ok) throw new ApiError(response.status, errorMessage(data, response.status));
    return data as ChatResult;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "The request timed out before AgentRoute returned.");
    }
    throw new ApiError(0, "Cannot reach the AgentRoute API. Start the backend and try again.");
  } finally {
    window.clearTimeout(timer);
  }
}

export function blenderSceneUrl(sceneId: string): string {
  return `${BASE}/api/blender/scene/${encodeURIComponent(sceneId)}`;
}

export async function openBlenderScene(sceneId: string): Promise<void> {
  const response = await fetch(`${BASE}/api/blender/scene/${encodeURIComponent(sceneId)}/open`, {
    method: "POST",
  });
  const data = await readBody(response);
  if (!response.ok) throw new ApiError(response.status, errorMessage(data, response.status));
}

export async function loadConversation(conversationId: string): Promise<ConversationPayload | null> {
  try {
    const response = await fetch(`${BASE}/api/conversations/${encodeURIComponent(conversationId)}`);
    if (response.status === 404) return null;
    const data = await readBody(response);
    if (!response.ok) throw new ApiError(response.status, errorMessage(data, response.status));
    return data as ConversationPayload;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    return null;
  }
}
