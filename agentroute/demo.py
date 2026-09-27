"""AgentRoute CLI demo (Step 4).

Usage:
    python demo.py             # interactive (real model calls; needs API keys)
    python demo.py --demo      # offline: routing decisions, agent, model, tools
    python demo.py --stats     # offline: historical routing statistics
    python demo.py --validate  # offline: architectural invariant checks

Offline modes make NO model API calls and do not require Blender.
"""

import argparse
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv optional; env may already be set
    pass

from agents.registry import AGENT_NAMES, build_agent_registry
from classifier import classify
from conversation_state import ConversationState
from errors import AgentRouteError
from models import known_model_ids
from router import route
from routing_memory import RoutingMemory
from routing_policy import (
    STEP4_CANDIDATES,
    AdaptiveRoutingPolicy,
    BaselineAgentPolicy,
    THREE_D_AGENT,
)
from tools.registry import get_tool, list_tools, tool_metadata

SEP = "-" * 40

EXAMPLES = [
    "What is a Python decorator?",
    "Write a FastAPI authentication system.",
    "Explain how to design a scalable multi-agent architecture.",
    "Research the latest approaches to RAG evaluation.",
    "Create a modern 3D wardrobe in Blender.",
]


def _print_routing(prompt, classification, decision, agent):
    print(SEP)
    print("AgentRoute Step 4")
    print(SEP)
    print(f"\nPROMPT:\n{prompt}")
    print(f"\nINTENT:\n{classification['intent']}")
    print(f"\nCOMPLEXITY:\n{classification['complexity']}")
    print(f"\nPOLICY:\n{decision['policy']}")
    print(f"\nSELECTED AGENT:\n{decision['selected_agent']}")
    print(f"\nMODEL:\n{agent.model_id}  (provider: {agent.model_provider})")
    fallbacks = list(agent.fallback_model_ids)
    print(f"\nFALLBACK MODELS:\n{', '.join(fallbacks) if fallbacks else '(none)'}")
    tools = list(agent.available_tools)
    print(f"\nTOOLS:\n{', '.join(tools) if tools else '(none)'}")
    print(f"\nREASON:\n{decision['reason']}")
    print(SEP + "\n")


def run_offline_demo(memory):
    print("Offline demo: routing decisions only. No model API calls, no Blender.\n")
    registry = build_agent_registry()
    policy = BaselineAgentPolicy()

    for prompt in EXAMPLES:
        classification = classify(prompt)
        decision = policy.select_agent(
            classification["intent"],
            classification["complexity"],
            classification["confidence"],
        )
        agent = registry[decision["selected_agent"]]
        _print_routing(prompt, classification, decision, agent)

        # For the 3D example, show the agent -> tool -> ToolResult flow offline.
        if decision["selected_agent"] == THREE_D_AGENT:
            script = agent.build_blender_script(prompt)  # deterministic, no model
            tool = agent.get_tool("BLENDER_TOOL")        # the AGENT picks the tool
            result = tool.run(script)
            print("  THREE_D_AGENT -> BLENDER_TOOL flow (offline):")
            print(f"    tool:      {result.tool}")
            print(f"    success:   {result.success}")
            print(f"    executed:  {result.metadata.get('executed')}")
            print(f"    output:    {result.output}")
            print(f"    artifacts: {result.artifacts or '(none)'}")
            print(f"    script:    {len(script)} chars of valid bpy\n")

    print(SEP)
    print("Registered agents:", ", ".join(AGENT_NAMES))
    print("Registered tools: ", ", ".join(list_tools()))
    print(SEP)


def run_validation():
    """Offline architectural invariant checks (section 20). No API keys needed."""
    registry = build_agent_registry()
    tools = set(list_tools())
    policy = BaselineAgentPolicy()
    model_ids = known_model_ids()

    selections = set()
    for prompt in EXAMPLES:
        c = classify(prompt)
        selections.add(
            policy.select_agent(c["intent"], c["complexity"], c["confidence"])[
                "selected_agent"
            ]
        )

    checks = [
        ("Router selects agents only",
         selections <= set(AGENT_NAMES)),
        ("Router does not select models",
         not (selections & model_ids)),
        ("Router does not select tools",
         not (selections & tools)),
        ("Blender is a tool",
         "BLENDER_TOOL" in tools),
        ("Blender is not an agent",
         not any("BLENDER" in name.upper() for name in registry)),
        ("OpenRouter models are agent implementation details",
         all(a.model_id for a in registry.values())
         and not (set(registry) & model_ids)),
        ("Agents own model calls",
         all(a.model_provider for a in registry.values())),
        ("Agents decide whether tools are needed",
         "BLENDER_TOOL" in registry[THREE_D_AGENT].available_tools),
        ("Tools return structured ToolResults",
         hasattr(get_tool("BLENDER_TOOL").run("import bpy"), "success")),
        ("Adaptive routing chooses agents, not tools",
         all(set(v) <= set(AGENT_NAMES) for v in STEP4_CANDIDATES.values())),
        ("Model fallback happens inside agents",
         any(a.fallback_model_ids for a in registry.values())),
        ("Adding a tool does not require rewriting router.py",
         "BLENDER_TOOL" not in _router_source() and "tools" not in _router_imports()),
        ("Adding a model does not require rewriting router.py",
         not any(m in _router_source() for m in model_ids)),
        ("Adding an agent does not require rewriting the tool layer",
         "AGENT" not in _tools_registry_source().replace("BASE_TOOL", "")),
    ]

    print(SEP)
    print("Architectural validation (offline)")
    print(SEP)
    failed = 0
    for label, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {label}")
        failed += 0 if ok else 1
    print(SEP)
    print(f"{len(checks) - failed}/{len(checks)} checks passed")
    return 0 if failed == 0 else 1


def _read(path):
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, path), encoding="utf-8") as fh:
        return fh.read()


def _router_source():
    return _read("router.py")


def _router_imports():
    return "\n".join(
        line for line in _router_source().splitlines()
        if line.startswith(("import ", "from "))
    )


def _tools_registry_source():
    import os

    return _read(os.path.join("tools", "registry.py"))


def _print_stats(memory):
    print("\n" + SEP)
    print("Historical routing statistics (per agent)")
    print(SEP)
    stats = memory.get_agent_statistics()
    if not stats:
        print("(no observations recorded yet - run interactive sessions to populate)")
        return
    for agent, s in sorted(stats.items()):
        print(f"\n{agent}:")
        print(f"    attempts:            {s['attempts']}")
        print(f"    successes:           {s['successes']}")
        print(f"    success_rate:        {s['success_rate']}")
        print(f"    average_score:       {s['average_score']}")
        print(f"    average_latency_ms:  {s['average_latency_ms']}")

    print("\n" + SEP)
    print("By intent")
    print(SEP)
    for intent, per_agent in sorted(memory.get_statistics_by_intent().items()):
        print(f"\n[{intent}]")
        for agent, s in sorted(per_agent.items()):
            print(
                f"    {agent}: attempts={s['attempts']} "
                f"avg_score={s['average_score']} "
                f"avg_latency_ms={s['average_latency_ms']}"
            )


def run_interactive(memory):
    print("AgentRoute interactive demo (Step 4). Type a prompt, or 'quit' to exit.\n")
    registry = build_agent_registry()
    state = ConversationState()
    policy = AdaptiveRoutingPolicy(
        memory,
        baseline=BaselineAgentPolicy(),
        candidates_by_intent=STEP4_CANDIDATES,
    )
    while True:
        try:
            prompt = input("prompt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        if not prompt:
            continue
        if prompt.lower() in {"quit", "exit", "q"}:
            print("Bye.")
            break

        try:
            result = route(
                prompt,
                policy=policy,
                conversation_state=state,
                memory=memory,
                agents=registry,
            )
        except AgentRouteError as exc:
            print(f"\n[error] {exc}\n")
            continue
        except Exception as exc:  # noqa: BLE001 - keep the CLI alive
            print(f"\n[unexpected error] {type(exc).__name__}: {exc}\n")
            continue

        agent = registry[result["selected_agent"]]
        print(SEP)
        print("AgentRoute Step 4")
        print(SEP)
        print(f"\nPROMPT:\n{prompt}")
        print(f"\nINTENT:\n{result['intent']}")
        print(f"\nSELECTED AGENT:\n{result['selected_agent']}")
        print(f"\nMODEL:\n{agent.model_id}")
        tools = list(agent.available_tools)
        print(f"\nTOOLS:\n{', '.join(tools) if tools else '(none)'}")
        print(f"\nREASON:\n{result['routing_reason']}")
        print(f"\nSUCCESS:\n{result['response_success']} (latency {result['latency_ms']} ms)")
        print(f"\nRESPONSE:\n{result['response']}")
        print(SEP + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="AgentRoute demo CLI (Step 4)")
    parser.add_argument("--demo", action="store_true", help="offline routing demo")
    parser.add_argument("--stats", action="store_true", help="show routing statistics")
    parser.add_argument("--validate", action="store_true", help="architecture checks")
    parser.add_argument("--tools", action="store_true", help="list registered tools")
    parser.add_argument("--db", default=None, help="path to routing memory DB")
    args = parser.parse_args(argv)

    if args.validate:
        return run_validation()
    if args.tools:
        for meta in tool_metadata():
            print(
                f"{meta['name']:22s} implemented={meta['implemented']!s:5s} "
                f"available={meta['available']!s:5s}  {meta['description']}"
            )
        return 0

    memory = RoutingMemory(args.db) if args.db else RoutingMemory()
    try:
        if args.stats:
            _print_stats(memory)
        elif args.demo:
            run_offline_demo(memory)
        else:
            run_interactive(memory)
    finally:
        memory.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
