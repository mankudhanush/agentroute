/** Fields copied from router.route(). The UI does not add routing decisions. */

export type TaskProfile = {
  capability?: string;
  breadth?: number;
  output_type?: string;
  requires_tools?: boolean;
  required_tools?: string[];
  context_dependent?: boolean;
  complexity_level?: number;
  complexity_name?: string;
  complexity_source?: string;
  intent?: string;
  confidence?: number;
  decision_layer?: string;
};

export type RoutingSnapshot = {
  response?: string;
  response_success?: boolean;
  selected_agent?: string;
  intent?: string;
  complexity?: string;
  confidence?: number;
  policy?: string;
  decision_layer?: string;
  routing_reason?: string;
  fallback_used?: boolean;
  latency_ms?: number;
  outcome_score?: number;
  capability?: string;
  complexity_level?: number;
  complexity_name?: string;
  complexity_source?: string;
  requires_tools?: boolean;
  required_tools?: string[];
  context_dependent?: boolean;
  output_type?: string;
  task_profile?: TaskProfile;
  selected_model?: string | null;
  model_provider?: string | null;
  model_reason?: string;
  matched_capabilities?: string[];
  model_fallbacks?: string[];
  model_tier?: number | null;
  /** Why the decision layer degraded, when fallback_used is true. */
  laya_error?: string | null;
  /** Task-context continuity for this turn. */
  context_id?: string | null;
  context_continued?: boolean;
  context_turns?: number;
  context_summary?: string | null;
  /** What this request does to the stored work. */
  operation?: "create" | "modify" | "fix" | "extend" | "continue" | "explain";
  has_artifact?: boolean;
  artifact_chars?: number;
  /** Present only after BLENDER_TOOL writes a scene.blend. */
  blender_scene?: { scene_id: string };
  /** Present while Playwright is holding a visible Chromium window open. */
  browser_active?: boolean;
};

export type ChatResult = RoutingSnapshot & {
  conversation_id: string;
};

export type StoredMessage = {
  prompt: string;
  response: string;
  agent: string;
  routing: RoutingSnapshot | null;
};

export type ConversationPayload = {
  conversation_id: string;
  messages: StoredMessage[];
};

export type UserTurn = {
  id: string;
  kind: "user";
  text: string;
};

export type AgentTurn = {
  id: string;
  kind: "agent";
  prompt: string;
  text: string;
  result: ChatResult;
};

export type NoticeTurn = {
  id: string;
  kind: "notice";
  text: string;
};

export type Turn = UserTurn | AgentTurn | NoticeTurn;
