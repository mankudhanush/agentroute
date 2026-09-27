"""Routing evaluation — measures routing behaviour and surfaces failures.

Usage:
    python evaluation.py              # offline, baseline decision layer
    python evaluation.py --laya       # use the real Laya Decision AI (slow)

IMPORTANT ON WHAT THIS MEASURES:
  * `expected_capability` is a defensible label: these prompts belong to an
    obvious domain, so a routing miss is a real signal.
  * `expected_level` is a HINT, not ground truth. Complexity is a judgement
    call, so it is reported and compared loosely, never asserted as correct.
  * The selected MODEL is recorded but NOT scored. We have no evaluation basis
    for claiming a given model is objectively right for a prompt; that needs
    measured outcomes (routing memory + feedback), which is a later step.

No model API calls are made: evaluation runs through router.preview().
"""

import argparse

from router import preview
from routing_policy import BaselineAgentPolicy

# prompt, expected_capability, expected_level (hint only)
EVAL_CASES = (
    # --- general ---------------------------------------------------------
    ("What is photosynthesis?", "general", 1),
    ("Explain what a Python decorator is.", "general", 1),
    ("Summarize the water cycle in three sentences.", "general", 1),
    ("What is the capital of Japan?", "general", 1),
    ("Explain the difference between TCP and UDP.", "general", 2),
    # --- coding ----------------------------------------------------------
    ("Write a Python function to reverse a string.", "coding", 1),
    ("Write a function to sort a list of integers.", "coding", 1),
    ("Debug this regex that fails on empty input.", "coding", 2),
    ("Build a FastAPI authentication service with PostgreSQL.", "coding", 3),
    ("Refactor a Django codebase to use async database queries.", "coding", 3),
    ("Implement a lock-free concurrent queue in Rust.", "coding", 4),
    # --- reasoning / architecture ----------------------------------------
    ("Design a scalable microservices architecture.", "reasoning", 3),
    ("Compare the trade-offs of event sourcing versus CRUD.", "reasoning", 3),
    ("Design a distributed system for millions of concurrent users.", "reasoning", 4),
    ("Plan a migration strategy from a monolith to services.", "reasoning", 3),
    ("Analyze the failure modes of a multi-agent system design.", "reasoning", 4),
    # --- research --------------------------------------------------------
    ("Research the advantages and disadvantages of RAG.", "research", 2),
    ("Research RAG approaches and compare their tradeoffs using evidence.", "research", 3),
    ("Survey the state of the art in vector database indexing.", "research", 3),
    ("Investigate recent advances in model quantization.", "research", 3),
    ("Research and compare evidence on prompt caching strategies.", "research", 3),
    # --- 3D / creative ---------------------------------------------------
    ("Create a 3D model of a wooden chair.", "creative_3d", 2),
    ("Generate a Blender Python script for a wardrobe.", "creative_3d", 2),
    ("Create a detailed 3D interior with materials, lighting and rendering.", "creative_3d", 4),
    ("Model a low-poly tree mesh in Blender.", "creative_3d", 2),
    ("Create a detailed 3D kitchen with cabinets, materials and a realistic render.",
     "creative_3d", 4),
    # --- context-dependent (second turn of a conversation) ---------------
    ("Now add authentication and PostgreSQL.", "coding", 2),
    ("Now make it handle ten times the traffic.", "reasoning", 3),
    ("Now write the unit tests for it.", "coding", 2),
    ("Explain that last answer more simply.", "general", 1),
    ("Now render it with better lighting.", "creative_3d", 2),
)


AGENT_FOR_CAPABILITY = {
    "general": "GENERAL_AGENT",
    "coding": "CODING_AGENT",
    "reasoning": "REASONING_AGENT",
    "research": "RESEARCH_AGENT",
    "creative_3d": "THREE_D_AGENT",
}


def run_eval(policy=None, cases=EVAL_CASES) -> list:
    """Route every case and return one row per prompt. No API calls.

    The PRIMARY metric is the selected AGENT - that is the routing decision the
    system actually acts on.
    """
    policy = policy or BaselineAgentPolicy()
    rows = []
    for prompt, expected_capability, expected_level in cases:
        result = preview(prompt, policy=policy)
        expected_agent = AGENT_FOR_CAPABILITY[expected_capability]
        rows.append(
            {
                "prompt": prompt,
                "expected_agent": expected_agent,
                "agent_match": result["selected_agent"] == expected_agent,
                "expected_capability": expected_capability,
                "capability": result["capability"],
                "capability_match": result["capability"] == expected_capability,
                "expected_level": expected_level,
                "complexity_level": result["complexity_level"],
                "selected_agent": result["selected_agent"],
                "selected_model": result["selected_model"],
                "provider": result["model_provider"],
                "model_reason": result["model_reason"],
                "fallback_models": result.get("model_fallbacks", []),
                "requires_tools": result["requires_tools"],
                "required_tools": result["required_tools"],
                "decision_layer": result["decision_layer"],
            }
        )
    return rows


def _spread(cases, limit):
    """Pick `limit` cases round-robin across capabilities, not just the first N.

    Also prefers the hardest case per capability, so live runs exercise the
    higher complexity tiers rather than only trivial prompts.
    """
    if limit >= len(cases):
        return list(cases)
    buckets = {}
    for case in cases:
        buckets.setdefault(case[1], []).append(case)
    for capability in buckets:
        buckets[capability].sort(key=lambda c: -c[2])
    picked, index = [], 0
    while len(picked) < limit:
        added = False
        for capability in sorted(buckets):
            if index < len(buckets[capability]) and len(picked) < limit:
                picked.append(buckets[capability][index])
                added = True
        if not added:
            break
        index += 1
    return picked


def run_live_eval(policy=None, cases=EVAL_CASES, limit=6) -> list:
    """Execute real API calls for a LIMITED subset and record latency/success.

    Opt-in only: this spends real provider quota. Never called by unit tests.
    Records no prompts' responses and no credentials - only routing metadata,
    latency and success.
    """
    from time import perf_counter

    # Credentials are loaded HERE, not at import time: importing this module
    # must never push real keys into a unit-test process.
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    from agents.registry import build_agent_registry
    from router import route

    policy = policy or BaselineAgentPolicy()
    registry = build_agent_registry()
    rows = []
    for prompt, expected_capability, _level in _spread(cases, limit):
        started = perf_counter()
        try:
            result = route(prompt, policy=policy, agents=registry)
            latency_ms = int((perf_counter() - started) * 1000)
            rows.append({
                "prompt": prompt,
                "expected_capability": expected_capability,
                "capability": result["capability"],
                "capability_match": result["capability"] == expected_capability,
                "complexity_level": result["complexity_level"],
                "selected_agent": result["selected_agent"],
                "selected_model": result["selected_model"],
                "provider": result["model_provider"],
                "success": result["response_success"],
                "latency_ms": result.get("latency_ms", latency_ms),
                "error": None if result["response_success"] else result["response"][:120],
            })
        except Exception as exc:  # noqa: BLE001 - record, never crash the run
            rows.append({
                "prompt": prompt,
                "expected_capability": expected_capability,
                "capability": None, "capability_match": False,
                "complexity_level": None, "selected_agent": None,
                "selected_model": None, "provider": None,
                "success": False,
                "latency_ms": int((perf_counter() - started) * 1000),
                "error": f"{type(exc).__name__}",
            })
    return rows


def summarize(rows: list) -> dict:
    total = len(rows)
    matched = sum(1 for r in rows if r["capability_match"])
    agent_matched = sum(1 for r in rows if r.get("agent_match"))
    return {
        "total": total,
        "agent_matched": agent_matched,
        "agent_accuracy": round(agent_matched / total, 3) if total else 0.0,
        "capability_matched": matched,
        "capability_accuracy": round(matched / total, 3) if total else 0.0,
        "misses": [r for r in rows if not r.get("agent_match")],
        "levels_seen": sorted({r["complexity_level"] for r in rows}),
        "decision_layers": sorted({r["decision_layer"] for r in rows}),
        "models_used": sorted({r["selected_model"] for r in rows if r["selected_model"]}),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="AgentRoute routing evaluation")
    parser.add_argument("--laya", action="store_true",
                        help="use the real Laya Decision AI (loads the model)")
    parser.add_argument("--live", action="store_true",
                        help="make REAL provider API calls (spends quota)")
    parser.add_argument("--limit", type=int, default=6,
                        help="how many cases to run live (default 6)")
    args = parser.parse_args(argv)

    if args.laya:
        from laya_routing_policy import LayaRoutingPolicy

        policy = LayaRoutingPolicy(fallback=BaselineAgentPolicy())
    else:
        policy = BaselineAgentPolicy()

    if args.live:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass
        import providers

        print(f"available providers: {', '.join(sorted(providers.available_providers()))}")
        print(f"running {args.limit} LIVE cases (real API calls)\n")
        live_rows = run_live_eval(policy, limit=args.limit)
        head = f"{'PROMPT':44s} {'AGENT':16s} {'PROVIDER':10s} {'OK':3s} {'ms':>6s}  MODEL"
        print(head)
        print("-" * len(head))
        for row in live_rows:
            print(f"{row['prompt'][:42]:44s} {str(row['selected_agent']):16s} "
                  f"{str(row['provider']):10s} {'yes' if row['success'] else 'NO ':3s} "
                  f"{row['latency_ms']:>6}  {row['selected_model']}")
            if row["error"]:
                print(f"    error: {row['error']}")
        ok = sum(1 for r in live_rows if r["success"])
        print(f"\nlive: {ok}/{len(live_rows)} succeeded")
        return 0 if ok else 1

    rows = run_eval(policy)
    header = f"{'PROMPT':52s} {'EXP-CAP':12s} {'CAP':12s} {'LVL':3s} {'AGENT':16s} MODEL"
    print(header)
    print("-" * len(header))
    for row in rows:
        mark = " " if row["capability_match"] else "*"
        print(
            f"{mark}{row['prompt'][:50]:51s} {row['expected_capability']:12s} "
            f"{row['capability']:12s} {row['complexity_level']:<3} "
            f"{row['selected_agent']:16s} {row['selected_model']}"
        )

    stats = summarize(rows)
    print()
    # Never let a fallback masquerade as a Laya decision.
    layers = sorted({row["decision_layer"] for row in rows})
    print(f"decision layer(s)   : {', '.join(layers)}")
    if args.laya and any(layer != "laya" for layer in layers):
        print("  WARNING: Laya did NOT decide these rows - the fallback ran. "
              "These results measure the fallback, not Laya.")
    print(f"AGENT accuracy      : {stats['agent_matched']}/{stats['total']} "
          f"({stats['agent_accuracy']:.0%})   <- the actual routing decision")
    print(f"capability accuracy : {stats['capability_matched']}/{stats['total']} "
          f"({stats['capability_accuracy']:.0%})")
    print(f"complexity levels   : {stats['levels_seen']}")
    print(f"models selected     : {', '.join(stats['models_used'])}")
    if stats["misses"]:
        print("\nmisses (* above):")
        for row in stats["misses"]:
            print(f"  {row['prompt']}")
            print(f"    expected {row['expected_capability']} -> got {row['capability']}")
    print("\nNote: selected models are recorded, not scored - there is no "
          "evaluation basis yet for calling a model 'correct'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
