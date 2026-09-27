"""Laya Decision AI adapter — the decision layer that selects ONE logical agent.

Laya is a non-autoregressive "System 1" decision engine (Convai Innovations). It
answers typed questions (choice / score / noul) over a state in a single forward
pass and returns calibrated probabilities.

    Package : laya            (https://pypi.org/project/laya/)
    Import  : from laya import Router
    Source  : https://huggingface.co/convaiinnovations/laya

API used here (verified against the PyPI README, laya-ai.com and the Hugging
Face model card):

    from laya import Router
    router = Router(preload=True)
    result = router.predict(state, questions)
    result["answers"]["<key>"]["choice"]       -> the chosen option key
    result["answers"]["<key>"]["confidence"]   -> calibrated probability
    result["routing"]["model" | "repo" | "reason"]

What this module is NOT:
  * Not an agent. Laya only decides WHICH agent handles a request.
  * Not a model provider. The selected agent owns its own provider (Gemini).
  * Not a tool selector. Laya never sees or chooses tools.

The candidate options handed to Laya are exactly AGENT_NAMES, so an out-of-range
answer is impossible by construction - and is still validated defensively.
"""

import logging

from classifier import COMPLEXITIES, INTENTS
from config import optional_env
from errors import ConfigurationError, RoutingDecisionError
from routing_policy import AGENT_NAMES, GENERAL_AGENT, BaselineAgentPolicy, RoutingPolicy
from task_profile import LAYA_LEVEL_KEYS

logger = logging.getLogger("agentroute.laya")

DEFAULT_CHECKPOINT = "convaiinnovations/laya"

# Decision keys used in the single Laya predict() call.
AGENT_QUESTION = "agent"
INTENT_QUESTION = "intent"
COMPLEXITY_QUESTION = "complexity"
LEVEL_QUESTION = "complexity_level"

# Natural-language criteria describing each candidate agent. These are INPUTS to
# Laya's decision - they are descriptions, not a lookup table. Laya reads the
# request and picks among them.
AGENT_CRITERIA = {
    "GENERAL_AGENT": (
        "general knowledge questions, explanations, definitions, summarization "
        "and simple everyday tasks"
    ),
    "CODING_AGENT": (
        "writing, debugging or explaining concrete source code; implementing a "
        "specific function, script, class or program where the answer is code"
    ),
    "REASONING_AGENT": (
        "designing a system or architecture, scalability and infrastructure "
        "trade-offs, planning, strategy and deep analysis, where the answer is "
        "a design or an argument rather than source code"
    ),
    "RESEARCH_AGENT": (
        "research questions, surveying or comparing approaches, weighing "
        "advantages and disadvantages, evidence-oriented investigation"
    ),
    "THREE_D_AGENT": (
        "3D modelling and design, Blender workflows, scenes, geometry, "
        "materials, meshes and Blender Python scripts"
    ),
    "WEB_AGENT": (
        "opening a website, navigating pages, clicking, typing into a page, "
        "reading what a live page shows, taking a screenshot, and other "
        "multi-step work that has to happen in a browser"
    ),
}

INTENT_CRITERIA = {
    "general": "a general knowledge or explanation request",
    "coding": "a programming or software implementation request",
    "reasoning": "a complex reasoning, planning or architecture request",
    "research": "a research, comparison or investigation request",
    "blender": "a 3D modelling or Blender request",
}

COMPLEXITY_CRITERIA = {
    "simple": "a short, direct request answerable without much depth",
    "medium": "a moderately involved request needing some detail",
    "complex": "a demanding request requiring deep analysis or many parts",
}

# 4-level scale (Step 6). Keys map to levels 1-4 via task_profile.LAYA_LEVEL_KEYS.
LEVEL_CRITERIA = {
    "level_1_simple": "a quick factual or single-step request",
    "level_2_moderate": "a request with several steps or some detail required",
    "level_3_complex": (
        "a substantial request with multiple interacting parts, design choices "
        "or in-depth analysis"
    ),
    "level_4_expert": (
        "a request demanding deep specialist expertise, such as large-scale "
        "system design, rigorous evaluation or production-grade engineering"
    ),
}


def _agent_from_specialized_intent(agent_choice: str, laya_intent: str) -> str:
    """A general agent answer must not discard a specialized intent.

    Laya answers "which agent" and "what kind of request" separately. Only the
    agent answer used to be kept, so a research or reasoning intent paired with
    GENERAL_AGENT was executed as a general task. A specialist agent answer is
    left as Laya gave it.
    """
    if agent_choice != GENERAL_AGENT or laya_intent not in INTENTS or laya_intent == "general":
        return agent_choice
    specialist = BaselineAgentPolicy().select_agent(laya_intent, "simple", 0.0)
    return specialist["selected_agent"]


def build_state(prompt: str, context: dict | None = None) -> dict:
    """The state Laya reasons over: the request, plus conversation context.

    Context comes from the existing ConversationState - no separate memory
    system. `previous_request` is only included when there IS history, so a
    first-turn state stays exactly {"request": ...}.
    """
    state = {"request": prompt}
    previous = (context or {}).get("previous_prompts") or []
    if previous:
        state["previous_request"] = previous[-1]
    return state


def build_questions(with_context: bool = False) -> dict:
    """The typed questions posed to Laya in one forward pass."""
    follow_up = (
        " If `request` is a follow-up that refers back to earlier work "
        "(for example \"now add...\" or \"write tests for it\"), judge it "
        "together with `previous_request`."
        if with_context
        else ""
    )
    return {
        AGENT_QUESTION: {
            "type": "choice",
            # Laya's own presets reference the state key in backticks.
            "instructions": (
                "Which specialist agent should handle the user's `request`? "
                "Choose the single best-suited agent." + follow_up
            ),
            # Candidates are exactly the valid logical agents.
            "criteria": {name: AGENT_CRITERIA[name] for name in AGENT_NAMES},
        },
        INTENT_QUESTION: {
            "type": "choice",
            "instructions": "What kind of `request` is this?" + follow_up,
            "criteria": dict(INTENT_CRITERIA),
        },
        COMPLEXITY_QUESTION: {
            "type": "choice",
            "instructions": "How complex is the user's `request`?",
            "criteria": dict(COMPLEXITY_CRITERIA),
        },
        # First-class 4-level complexity (Step 6). Answered in the same forward
        # pass; consumers fall back to the 3-value answer if it is absent.
        LEVEL_QUESTION: {
            "type": "choice",
            "instructions": "What level of effort and expertise does the `request` demand?",
            "criteria": dict(LEVEL_CRITERIA),
        },
    }


class LayaRoutingPolicy(RoutingPolicy):
    """RoutingPolicy backed by the real Laya Decision AI.

    Args:
        client:   a preconstructed Laya router (dependency injection for tests).
        preload:  passed to laya.Router(preload=...).
        fallback: optional RoutingPolicy used when Laya is unavailable. Results
                  produced by the fallback are ALWAYS labelled as such and are
                  never reported as a Laya decision.
    """

    name = "laya"

    def __init__(self, client=None, preload=None, fallback=None, checkpoint=None):
        self._client = client
        self.checkpoint = checkpoint or optional_env("LAYA_CHECKPOINT", DEFAULT_CHECKPOINT)
        if preload is None:
            preload = (optional_env("LAYA_PRELOAD", "false") or "").lower() == "true"
        self.preload = preload
        self.fallback = fallback

    # --- Laya client --------------------------------------------------------
    def is_available(self) -> bool:
        """Whether the laya package can be imported (does not load a model)."""
        if self._client is not None:
            return True
        import importlib.util
        import sys

        sentinel = object()
        module = sys.modules.get("laya", sentinel)
        if module is None:  # explicitly blocked (import would raise)
            return False
        if module is not sentinel:  # already imported/injected
            return True
        try:
            return importlib.util.find_spec("laya") is not None
        except (ImportError, ValueError):
            return False

    def _get_client(self):
        if self._client is None:
            try:
                from laya import Router
            except ImportError as exc:
                raise ConfigurationError(
                    "Laya Decision AI is not installed. Install it with "
                    "'pip install laya' (requires Python >=3.10 and pulls "
                    "torch/transformers). See https://pypi.org/project/laya/"
                ) from exc
            self._client = Router(preload=self.preload)
        return self._client

    # --- decision -----------------------------------------------------------
    def select_agent(self, intent, complexity, confidence, context=None) -> dict:
        prompt = (context or {}).get("prompt")
        if not prompt:
            raise RoutingDecisionError(
                "Laya needs the request text as its decision state, but no "
                "'prompt' was supplied in the routing context."
            )

        try:
            client = self._get_client()
            state = build_state(prompt, context)
            result = client.predict(
                state, build_questions(with_context="previous_request" in state)
            )
        except ConfigurationError as exc:
            return self._fallback(intent, complexity, confidence, context,
                                  f"Laya unavailable - {exc}")
        except RoutingDecisionError:
            raise
        except Exception as exc:  # noqa: BLE001 - any Laya runtime failure
            return self._fallback(
                intent, complexity, confidence, context,
                f"Laya unavailable - {type(exc).__name__}",
            )

        return self._interpret(result, intent, complexity, confidence, context)

    def _interpret(self, result, intent, complexity, confidence, context) -> dict:
        answers = (result or {}).get("answers")
        if not isinstance(answers, dict) or AGENT_QUESTION not in answers:
            return self._reject(
                "Laya returned no answer for the agent decision",
                intent, complexity, confidence, context,
            )

        chosen = answers[AGENT_QUESTION].get("choice")
        # Defensive validation: only the registered logical agents are acceptable.
        # Rejects tool names (BLENDER_TOOL), model IDs (gemini-*), provider
        # names and any retired agent name alike.
        if chosen not in AGENT_NAMES:
            return self._reject(
                f"Laya returned an invalid agent {chosen!r}; "
                f"valid agents are {', '.join(AGENT_NAMES)}",
                intent, complexity, confidence, context,
            )

        laya_confidence = answers[AGENT_QUESTION].get("confidence")
        classification = self._classification(answers, intent, complexity,
                                              confidence, laya_confidence)
        raw_agent = chosen
        chosen = _agent_from_specialized_intent(chosen, classification["intent"])
        routing = (result or {}).get("routing") or {}

        detail = f"confidence {laya_confidence:.2f}" if isinstance(
            laya_confidence, (int, float)
        ) else "confidence unavailable"
        checkpoint = routing.get("model") or routing.get("repo") or self.checkpoint

        # First-class complexity level, when Laya answered that question.
        level = LAYA_LEVEL_KEYS.get(
            (answers.get(LEVEL_QUESTION) or {}).get("choice")
        )
        if chosen != raw_agent:
            reason = (
                f"Laya intent {classification['intent']} selects {chosen}; "
                f"the general-agent answer was not used ({detail}) "
                f"[checkpoint: {checkpoint}]"
            )
        else:
            reason = (
                f"Laya Decision AI selected {chosen} ({detail}) from "
                f"{len(AGENT_NAMES)} candidate agents [checkpoint: {checkpoint}]"
            )

        return {
            "selected_agent": chosen,
            "policy": self.name,
            "decision_layer": "laya",
            "complexity_level": level,
            "reason": reason,
            "fallback_used": False,
            "classification": classification,
            "laya": {"routing": routing, "confidence": laya_confidence},
        }

    @staticmethod
    def _classification(answers, intent, complexity, confidence, laya_confidence):
        """Prefer Laya's own intent/complexity answers; validate before use."""
        laya_intent = (answers.get(INTENT_QUESTION) or {}).get("choice")
        laya_complexity = (answers.get(COMPLEXITY_QUESTION) or {}).get("choice")
        resolved_conf = (
            round(float(laya_confidence), 2)
            if isinstance(laya_confidence, (int, float))
            else confidence
        )
        return {
            "intent": laya_intent if laya_intent in INTENTS else intent,
            "complexity": (
                laya_complexity if laya_complexity in COMPLEXITIES else complexity
            ),
            "confidence": max(0.0, min(1.0, resolved_conf)),
        }

    # --- failure handling ---------------------------------------------------
    def _reject(self, message, intent, complexity, confidence, context) -> dict:
        """Laya answered, but the answer is not a valid agent."""
        if self.fallback is None:
            raise RoutingDecisionError(message)
        return self._fallback(intent, complexity, confidence, context, message)

    def _fallback(self, intent, complexity, confidence, context, message) -> dict:
        """Use the fallback policy, labelled so it is never mistaken for Laya."""
        # A silent degradation looks identical to normal operation in the UI and
        # in the logs, so every fallback says why, once, at WARNING.
        logger.warning("decision layer degraded to fallback routing: %s", message)
        if self.fallback is None:
            raise ConfigurationError(message)
        decision = self.fallback.select_agent(intent, complexity, confidence, context)
        return {
            "selected_agent": decision["selected_agent"],
            # Deliberately NOT "laya": a fallback decision is never reported as
            # a Laya decision.
            "policy": f"{self.fallback.name} (laya-fallback)",
            "decision_layer": "fallback",
            "reason": f"Laya unavailable - fallback routing: {decision['reason']}",
            "fallback_used": True,
            "laya_error": message,
        }
