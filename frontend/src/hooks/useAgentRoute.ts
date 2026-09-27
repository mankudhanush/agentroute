import { useEffect, useRef, useState } from "react";
import { checkHealth, loadConversation, sendChat } from "../api/agentroute";
import type { AgentTurn, ChatResult, Turn } from "../types";

const CONVERSATION_KEY = "agentroute.conversationId";
const THEME_KEY = "agentroute.theme";

function id(): string {
  return crypto.randomUUID();
}

export function useAgentRoute() {
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme !== "light");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [active, setActive] = useState<AgentTurn | null>(null);
  const [pending, setPending] = useState(false);
  const [pendingPrompt, setPendingPrompt] = useState<string | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    let cancel = false;
    const ping = () => {
      void checkHealth().then((ok) => {
        if (!cancel) setConnected(ok);
      });
    };
    ping();
    const timer = window.setInterval(ping, 8000);
    return () => {
      cancel = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const saved = sessionStorage.getItem(CONVERSATION_KEY);
    if (!saved) return;
    let cancel = false;
    void loadConversation(saved).then((payload) => {
      if (cancel) return;
      if (!payload) {
        sessionStorage.removeItem(CONVERSATION_KEY);
        return;
      }
      const restored: Turn[] = [];
      let last: AgentTurn | null = null;
      for (const message of payload.messages) {
        restored.push({ id: id(), kind: "user", text: message.prompt });
        const agent: AgentTurn = {
          id: id(),
          kind: "agent",
          prompt: message.prompt,
          text: message.response,
          result: { ...message.routing, conversation_id: payload.conversation_id },
        };
        restored.push(agent);
        last = agent;
      }
      setConversationId(payload.conversation_id);
      setTurns(restored);
      setActive(last);
    });
    return () => {
      cancel = true;
    };
  }, []);

  function toggleTheme() {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(THEME_KEY, next);
    setDark(next === "dark");
  }

  function newConversation() {
    generation.current += 1;
    setPending(false);
    setPendingPrompt(null);
    setTurns([]);
    setActive(null);
    setConversationId(null);
    sessionStorage.removeItem(CONVERSATION_KEY);
  }

  async function onSend(message: string, blender = true, playwright = true) {
    const token = generation.current;
    setPending(true);
    setPendingPrompt(message);
    setTurns((current) => [...current, { id: id(), kind: "user", text: message }]);
    try {
      const result: ChatResult = await sendChat(message, conversationId, blender, playwright);
      if (generation.current !== token) return;
      const agent: AgentTurn = {
        id: id(),
        kind: "agent",
        prompt: message,
        text: result.response ?? "",
        result,
      };
      setConversationId(result.conversation_id);
      sessionStorage.setItem(CONVERSATION_KEY, result.conversation_id);
      setTurns((existing) => [...existing, agent]);
      setActive(agent);
    } catch (error) {
      if (generation.current !== token) return;
      const text = error instanceof Error ? error.message : "The request failed.";
      setTurns((existing) => [...existing, { id: id(), kind: "notice", text }]);
    } finally {
      if (generation.current === token) {
        setPending(false);
        setPendingPrompt(null);
      }
    }
  }

  return {
    dark,
    connected,
    turns,
    active,
    pending,
    pendingPrompt,
    toggleTheme,
    newConversation,
    setActive,
    onSend,
  };
}
