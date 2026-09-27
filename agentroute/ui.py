"""AgentRoute Streamlit UI.

Run with:
    streamlit run ui.py

Purpose (Step 5): visibly prove that the ROUTER switches between AGENTS based on
the prompt, even when one provider (Gemini) powers all of them.

    USER -> ROUTER -> SELECTED AGENT -> MODEL -> RESPONSE -> UI

This file contains NO model API calls and NO routing rules. It calls
router.route() / router.preview() and renders whatever they return.
"""

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv optional; env may already be set
    pass

import providers
from agents.registry import build_agent_registry
from conversation_state import ConversationState
from errors import AgentRouteError, ConfigurationError
from models import get_model, get_provider, model_env_var
from router import preview, route
from routing_memory import RoutingMemory
from routing_policy import build_policy
from ui_helpers import (
    build_flow,
    decision_layer_label,
    extract_code_blocks,
    strip_code_blocks,
    truncate,
)

EXAMPLES = [
    ("GENERAL", "What is photosynthesis?"),
    ("CODING", "Write a Python function to reverse a string."),
    ("REASONING", "Design a scalable microservices architecture."),
    ("RESEARCH", "Research the advantages and disadvantages of RAG."),
    ("3D", "Create a 3D model of a wooden chair."),
]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def active_provider() -> str:
    return get_provider("general")


def active_model() -> str:
    return get_model("general") or "(not configured)"


def provider_ready() -> bool:
    return providers.is_configured(active_provider())


def init_state():
    if "history" not in st.session_state:
        st.session_state.history = []
    if "conversation" not in st.session_state:
        st.session_state.conversation = ConversationState()


def card(lines: list):
    body = "<br>".join(lines)
    st.markdown(
        f"""<div style="border:1px solid rgba(128,128,128,0.4);border-radius:8px;
        padding:14px 16px;margin:8px 0;">{body}</div>""",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# sidebar
# --------------------------------------------------------------------------
def render_sidebar(registry):
    with st.sidebar:
        st.subheader("AGENTS")
        for agent in registry.values():
            st.markdown(f"● **{agent.name}** — {agent.description}")

        st.divider()
        st.subheader("CURRENT PROVIDER")
        st.markdown(f"**{providers.display_name(active_provider())}**")

        st.subheader("MODEL")
        st.code(active_model(), language=None)
        st.caption(f"Configured via `{model_env_var('general')}`")

        st.divider()
        st.subheader("SYSTEM STATUS")
        ready = provider_ready()
        st.markdown(
            f"""
- Router &nbsp;&nbsp;&nbsp;&nbsp;✓
- Classifier &nbsp;✓
- {providers.display_name(active_provider())} &nbsp;&nbsp;&nbsp;&nbsp;{'✓' if ready else '⚠'}
- Agents &nbsp;&nbsp;&nbsp;&nbsp;✓ ({len(registry)})
"""
        )
        if not ready:
            st.caption(
                f"Set `{providers.key_env_var(active_provider())}` in .env to enable "
                "live model execution."
            )


# --------------------------------------------------------------------------
# result rendering
# --------------------------------------------------------------------------
def render_agent_card(agent):
    lines = [
        f"<b>{agent.name}</b>",
        "",
        agent.description,
        "",
        f"Model: {providers.display_name(agent.model_provider)}",
    ]
    if "BLENDER_TOOL" in agent.available_tools:
        lines.append("Tool: BLENDER_TOOL (future)")
    card(lines)


def render_flow(result, agent, live):
    steps = build_flow(
        result["selected_agent"],
        providers.display_name(agent.model_provider),
        live,
        decision_layer=decision_layer_label(result),
    )
    st.code("\n  ↓\n".join(steps), language=None)


def render_result(prompt, result, agent, live, response, error):
    st.subheader("USER REQUEST")
    st.write(prompt)

    st.subheader("ROUTING DECISION")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selected Agent", result["selected_agent"])
    c2.metric("Task", result.get("capability", result["intent"]))
    c3.metric(
        "Complexity",
        f"Level {result.get('complexity_level', '?')}",
        help=result.get("complexity_name", ""),
    )
    c4.metric("Confidence", f"{result['confidence']:.2f}")

    st.subheader("AGENT")
    render_agent_card(agent)

    st.subheader("MODEL")
    selected_model = result.get("selected_model") or agent.model_id
    model_provider = result.get("model_provider") or agent.model_provider
    st.markdown(
        f"Provider: **{providers.display_name(model_provider)}**  \n"
        f"Model: `{selected_model}`"
    )
    if result.get("model_reason"):
        st.caption(f"Why this model? {result['model_reason']}")
    required_tools = result.get("required_tools") or []
    if required_tools:
        need = "required" if result.get("requires_tools") else "permitted"
        st.caption(f"Tools ({need}): {', '.join(required_tools)}")

    st.subheader("FLOW")
    render_flow(result, agent, live)

    st.subheader("RESPONSE")
    if error:
        st.error(error)
    elif not live:
        st.info(
            "Routing preview only — no model was called, so there is no response. "
            "Configure the API key to run this prompt live."
        )
    else:
        blocks = extract_code_blocks(response)
        prose = strip_code_blocks(response)
        if prose:
            st.markdown(prose)
        for block in blocks:
            st.code(block, language="python")
        if not prose and not blocks:
            st.markdown(response or "_(empty response)_")
        if blocks and result["selected_agent"] == "THREE_D_AGENT":
            st.caption(
                "Blender script generated. It is NOT executed — Blender execution "
                "arrives in a later step."
            )

    with st.expander("Routing Inspector"):
        rows = {
            "Decision Layer": decision_layer_label(result),
            "Task": result.get("capability", result["intent"]),
            "Intent": result["intent"],
            "Complexity": (
                f"Level {result.get('complexity_level', '?')} "
                f"({result.get('complexity_name', '?')}, "
                f"{result.get('complexity_source', '?')})"
            ),
            "Confidence": result["confidence"],
            "Selected Agent": result["selected_agent"],
            "Routing Policy": result["policy"],
            "Routing Reason": result["routing_reason"],
            "Fallback Used": result.get("fallback_used", False),
            "Provider": providers.display_name(
                result.get("model_provider") or agent.model_provider
            ),
            "Selected Model": result.get("selected_model") or agent.model_id,
            "Why this model?": result.get("model_reason", "n/a"),
            "Model Fallbacks": ", ".join(result.get("model_fallbacks") or []) or "(none)",
            "Tools": ", ".join(result.get("required_tools") or []) or "(none)",
            "Context Dependent": result.get("context_dependent", False),
            "Output Type": result.get("output_type", "text"),
            "Latency (ms)": result.get("latency_ms", "n/a (no model call)"),
            "Mode": "live" if live else "routing preview",
        }
        for key, value in rows.items():
            st.markdown(f"**{key}:** {value}")


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------
def handle_prompt(prompt, registry):
    """Always goes through the router - never picks an agent directly."""
    policy = build_policy()
    conversation = st.session_state.conversation
    live = provider_ready()
    error = None
    response = ""

    if not live:
        result = preview(prompt, policy=policy, conversation_state=conversation)
    else:
        try:
            with RoutingMemory() as memory:
                result = route(
                    prompt,
                    policy=policy,
                    conversation_state=conversation,
                    memory=memory,
                    agents=registry,
                )
            response = result["response"]
            if not result["response_success"]:
                error = response
                response = ""
        except ConfigurationError as exc:
            result = preview(prompt, policy=policy, conversation_state=conversation)
            error = f"Configuration problem: {exc}"
            live = False
        except AgentRouteError as exc:
            result = preview(prompt, policy=policy, conversation_state=conversation)
            error = f"Model request failed: {exc}"
        except Exception as exc:  # noqa: BLE001 - UI must never crash
            result = preview(prompt, policy=policy, conversation_state=conversation)
            error = f"Unexpected error: {type(exc).__name__}"

    agent = registry[result["selected_agent"]]
    st.session_state.history.append(
        {"prompt": prompt, "agent": result["selected_agent"], "live": live and not error}
    )
    render_result(prompt, result, agent, live and not error, response, error)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="AgentRoute", page_icon="🧭", layout="wide")
    init_state()
    registry = build_agent_registry()

    st.title("AgentRoute")
    st.caption("Intelligent Multi-Agent Routing")
    st.caption("Router → Agent → Model → Result")

    render_sidebar(registry)

    if not provider_ready():
        st.warning(
            f"{providers.display_name(active_provider())} API key not configured. "
            "Routing preview is available, but live model execution is disabled."
        )

    prompt_text = st.text_area(
        "Describe what you want AgentRoute to do...",
        key="prompt_input",
        height=120,
        placeholder="Describe what you want AgentRoute to do...",
    )
    run_clicked = st.button("Run AgentRoute", type="primary")

    st.markdown("**Quick tests** — the button only supplies the prompt; the router decides.")
    columns = st.columns(len(EXAMPLES))
    pending = None
    for column, (label, example) in zip(columns, EXAMPLES):
        if column.button(label, key=f"example_{label}", use_container_width=True):
            pending = example
        column.caption(example)

    if run_clicked and prompt_text.strip():
        pending = prompt_text.strip()
    elif run_clicked:
        st.warning("Enter a prompt first.")

    if pending:
        st.divider()
        handle_prompt(pending, registry)

    if st.session_state.history:
        st.divider()
        st.subheader("Recent requests")
        for index, item in enumerate(reversed(st.session_state.history[-10:]), start=1):
            mode = "" if item["live"] else "  _(preview)_"
            st.markdown(f"{index}. {truncate(item['prompt'])} → **{item['agent']}**{mode}")


if __name__ == "__main__":
    main()
