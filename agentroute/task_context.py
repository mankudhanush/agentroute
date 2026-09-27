"""Task-context continuity for one conversation.

This layer does not route, select a model, or call a provider. After the
existing route has chosen an agent and a model, it decides which stored task
branch the prompt belongs to and builds the text that execution should see.

A branch is not owned by an agent, a model, a provider, or a tool. Switching
any of those leaves the branch in place.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

# Closed-class and generic words. These are not topics, so they never count as
# evidence that two requests are about the same work.
_STOP = frozenset(
    """
    a an the to for of and or with on in from by at as is are be was were been
    this that these those it its itself they them their there here
    now please me my we you your our into onto over under than then also just
    still again only about into per via
    use make add write create design build implement explain define describe
    compare summarize summarise develop what how why when who which do does did
    can could should would will
    model models test tests testing code data file files function method class
    type value name text info information thing things stuff part parts way ways
    more simply simple new next same wide long short small large big old
    complete fully really very
    """.split()
)

_TOKEN = re.compile(r"[a-z0-9][a-z0-9+.#_-]{2,}", re.I)

# A request that names a new subject of its own. Questions are not included:
# "what does the script tag do?" still refers to the work already stored.
_FRESH_SUBJECT = re.compile(
    r"^(?:please\s+)?(?:design|build|create|implement|develop|write)\s+(?:a|an|the)\b",
    re.I,
)

# A request that introduces its own subject, rather than continuing one.
_NEW_TOPIC = re.compile(
    r"^(?:please\s+)?"
    r"(?:explain|define|describe|summarize|summarise|compare)\b"
    r"|^(?:what|who|why|how|when|where)\b"
    r"|^(?:please\s+)?(?:design|build|create|implement|develop|write)\s+(?:a|an|the)\b",
    re.I,
)

# Points at something already established. Not sufficient on its own when a
# different branch shares real topic tokens — overlap wins first.
_ANAPHORA = re.compile(
    r"\b(?:it|its|itself|this|that|these|those|them|they|above|previous)\b",
    re.I,
)

# Short imperatives that modify work already underway.
_MODIFIER = re.compile(
    r"^(?:please\s+)?(?:now\s+|also\s+|then\s+)?"
    r"(?:add|use|make|set|change|update|remove|include|put|keep|turn|give|"
    r"apply|increase|decrease|rename|move|resize|adjust|enable|disable|switch|fix)\b",
    re.I,
)

# Asks about work already done rather than asking for it to change.
_EXPLAIN = re.compile(
    r"^(?:please\s+)?"
    r"(?:explain|describe|summarize|summarise|analyse|analyze|review|compare)\b"
    r"|^(?:what|why|how|who|when|where|which)\b",
    re.I,
)

# Repairs work already underway.
_FIX = re.compile(
    r"^(?:please\s+)?(?:now\s+|also\s+|then\s+)?"
    r"(?:fix|repair|debug|correct|resolve)\b"
    r"|\b(?:is broken|not working|does ?n[o']t work|throws an error)\b",
    re.I,
)

# Adds to work already underway.
_EXTEND = re.compile(
    r"^(?:please\s+)?(?:now\s+|also\s+|then\s+)?(?:add|include|append|extend)\b",
    re.I,
)

# Points back at a stored result as the thing to produce again.
_SAME_ARTIFACT = re.compile(
    r"\b(?:same|existing|current|above|previous)\s+"
    r"(?:file|page|document|script|code|artifact|version|one)\b",
    re.I,
)

# What the request does to the work, as opposed to what the work is about.
CREATE = "create"
MODIFY = "modify"
FIX = "fix"
EXTEND = "extend"
CONTINUE = "continue"
EXPLAIN = "explain"

OPERATIONS = (CREATE, MODIFY, FIX, EXTEND, CONTINUE, EXPLAIN)

# Operations that rewrite the stored artifact itself. These are the ones that
# must return the artifact in full.
REWRITING_OPERATIONS = frozenset({MODIFY, FIX, EXTEND})

_MAX_CONTEXT_CHARS = 12000
_SUMMARY_CHARS = 400


def content_tokens(text: str) -> set:
    """Topic tokens in ``text``. Function words and generic fillers are dropped."""
    found = set()
    for raw in _TOKEN.findall((text or "").lower()):
        cleaned = raw.strip(".")
        if not cleaned or cleaned in _STOP:
            continue
        found.add(cleaned)
    return found


@dataclass
class TaskContext:
    """One task branch: every turn that belongs to the same piece of work."""

    context_id: str
    turns: list = field(default_factory=list)
    tokens: set = field(default_factory=set)
    capability: Optional[str] = None
    intent: Optional[str] = None
    last_agent: Optional[str] = None
    last_model: Optional[str] = None
    last_provider: Optional[str] = None
    latest_artifact: Optional[str] = None
    revision: int = 0

    def add_turn(self, turn) -> None:
        self.turns.append(turn)
        self.tokens.update(content_tokens(turn.prompt))
        if turn.response:
            self.tokens.update(content_tokens(turn.response))
        artifact = _working_artifact(getattr(turn, "response", None))
        if artifact is not None:
            self.latest_artifact = artifact
        if getattr(turn, "capability", None):
            self.capability = turn.capability
        if getattr(turn, "intent", None):
            self.intent = turn.intent
        self.last_agent = turn.agent
        if getattr(turn, "selected_model", None):
            self.last_model = turn.selected_model
        if getattr(turn, "model_provider", None):
            self.last_provider = turn.model_provider


@dataclass
class ContextMatch:
    """Read-only decision. Does not create or append a branch."""

    continued: bool
    context: Optional[TaskContext]
    prior_turns: list
    operation: str = CREATE

    @property
    def artifact(self) -> Optional[str]:
        if self.continued and self.context is not None:
            return self.context.latest_artifact
        return None

    def public_fields(self) -> dict:
        context_id = self.context.context_id if self.context is not None else None
        return {
            "context_id": context_id,
            "context_continued": self.continued,
            "context_turns": len(self.prior_turns),
            "context_summary": context_summary(self.prior_turns),
            "operation": self.operation,
            "has_artifact": bool(self.artifact),
        }


def empty_context_fields() -> dict:
    return {
        "context_id": None,
        "context_continued": False,
        "context_turns": 0,
        "context_summary": None,
        "operation": CREATE,
        "has_artifact": False,
    }


def context_summary(turns, limit: int = _SUMMARY_CHARS) -> Optional[str]:
    if not turns:
        return None
    text = " | ".join(turn.prompt.strip() for turn in turns if getattr(turn, "prompt", None))
    if len(text) <= limit:
        return text or None
    return text[: limit - 1].rstrip() + "…"


def match_task_context(
    prompt: str,
    state,
    capability: Optional[str] = None,
    selected_agent: Optional[str] = None,
) -> ContextMatch:
    """Pick the branch this prompt continues, or report that none matches.

    Overlap is measured against every turn already stored on a branch, not
    only the previous prompt. ``capability`` breaks a tie between equal
    overlaps; it cannot open a match by itself. A newly selected agent does
    not continue another agent's branch on a single shared token. A request
    that introduces its own subject does not continue on one shared token.
    A follow-up that names one branch's own request returns to that branch.
    Otherwise a short follow-up stays on the latest branch.
    """
    contexts = [ctx for ctx in getattr(state, "contexts", []) if ctx.turns]
    if not contexts:
        return ContextMatch(False, None, [], derive_operation(prompt, has_artifact=False))

    prompt_tokens = content_tokens(prompt)
    ranked = []
    overlap_size = {}
    for ctx in contexts:
        overlap = prompt_tokens & ctx.tokens
        if overlap and not _agent_overlap_counts(ctx, overlap, selected_agent):
            overlap = set()
        overlap_size[id(ctx)] = len(overlap)
        weight = (
            sum(len(token) for token in overlap) / sum(len(token) for token in prompt_tokens)
            if overlap and prompt_tokens
            else 0.0
        )
        ranked.append((weight, ctx))
    ranked.sort(key=lambda item: (item[0], item[1].revision), reverse=True)
    best_weight, best = ranked[0]
    second_weight = ranked[1][0] if len(ranked) > 1 else 0.0

    def established(ctx) -> bool:
        """A self-contained new request needs more than one shared token."""
        if not _FRESH_SUBJECT.search((prompt or "").strip()):
            return True
        return overlap_size.get(id(ctx), 0) >= 2

    if best_weight > second_weight and best_weight > 0 and established(best):
        return _continued(prompt, best)

    if best_weight > 0 and best_weight == second_weight and capability:
        tied = [
            ctx
            for weight, ctx in ranked
            if weight == best_weight and ctx.capability == capability and established(ctx)
        ]
        if len(tied) == 1:
            return _continued(prompt, tied[0])

    referred = _referenced_branch(prompt, prompt_tokens, contexts)
    if referred is not None:
        return _continued(prompt, referred)

    if _elliptical(prompt, prompt_tokens):
        return _continued(prompt, max(contexts, key=lambda ctx: ctx.revision))

    return ContextMatch(False, None, [], derive_operation(prompt, has_artifact=False))


def _request_tokens(context: TaskContext) -> set:
    """Tokens from the branch's own requests. Replies are not topics."""
    found = set()
    for turn in context.turns:
        found.update(content_tokens(getattr(turn, "prompt", "") or ""))
    return found


def _referenced_branch(prompt: str, prompt_tokens: set, contexts: list):
    """The one older branch a follow-up names, when the latest branch does not.

    A request that introduces its own subject is not a reference. A token that
    also belongs to another branch is not enough to choose between them.
    """
    if _FRESH_SUBJECT.search((prompt or "").strip()) or not prompt_tokens:
        return None
    hits = []
    for ctx in contexts:
        others = set()
        for other in contexts:
            if other is not ctx:
                others |= _request_tokens(other)
        distinctive = (prompt_tokens & _request_tokens(ctx)) - others
        if distinctive:
            hits.append((len(distinctive), sum(len(token) for token in distinctive), ctx))
    if not hits:
        return None
    hits.sort(key=lambda item: (item[0], item[1], item[2].revision), reverse=True)
    if len(hits) > 1 and hits[0][0] == hits[1][0] and hits[0][1] == hits[1][1]:
        return None
    return hits[0][2]


def _agent_overlap_counts(context: TaskContext, overlap: set, selected_agent: Optional[str]) -> bool:
    """A different agent needs more than one incidental shared token."""
    if not selected_agent or not context.last_agent or selected_agent == context.last_agent:
        return True
    return len(overlap) >= 2


def _continued(prompt: str, context: TaskContext) -> ContextMatch:
    operation = derive_operation(prompt, has_artifact=bool(context.latest_artifact))
    return ContextMatch(True, context, list(context.turns), operation)


def derive_operation(prompt: str, has_artifact: bool) -> str:
    """What the request does to the work, not what the work is about.

    Reads only the request and whether a stored artifact exists. No domain
    vocabulary, no model call, no new decision layer - it reuses the same
    request shapes the branch matcher already recognises.
    """
    text = (prompt or "").strip()
    if not has_artifact:
        return EXPLAIN if _EXPLAIN.search(text) else CREATE
    if _EXPLAIN.search(text):
        return EXPLAIN
    if _FIX.search(text):
        return FIX
    if _EXTEND.search(text):
        return EXTEND
    if _MODIFIER.search(text) or _SAME_ARTIFACT.search(text):
        return MODIFY
    if _NEW_TOPIC.search(text):
        # Reads as a fresh request, but it landed on an existing branch, so it
        # builds on that work rather than replacing it.
        return CONTINUE
    if _ANAPHORA.search(text):
        return MODIFY
    return CONTINUE


def adopt_context(state, match: ContextMatch) -> TaskContext:
    """Return the matched branch, or open a new one. Does not append a turn."""
    if match.continued and match.context is not None:
        return match.context
    created = TaskContext(context_id=str(uuid.uuid4()))
    state.contexts.append(created)
    return created


def execution_prompt(
    user_prompt: str,
    prior_turns,
    *,
    fresh: bool = False,
    artifact: Optional[str] = None,
    operation: Optional[str] = None,
) -> str:
    """Text for the model already chosen by ModelSelector.

    A first turn with no stored branch stays the raw prompt. A new branch
    beside other work is marked as a new task and carries no previous branch
    or artifact. A continued branch includes the stored turns, the branch's
    latest working artifact named so the model knows what it is holding, and
    the execution contract for THIS operation - a request that rewrites the
    artifact is told to return it complete, which a request that merely builds
    on it is not.
    """
    if not prior_turns:
        if fresh:
            return user_prompt
        return (
            "<task_context>\n"
            "New task.\n"
            "</task_context>\n\n"
            "<previous_work>\n"
            "None.\n"
            "</previous_work>\n\n"
            "<current_request>\n"
            f"{user_prompt}\n"
            "</current_request>"
        )
    stored = artifact if artifact is not None else _latest_stored_artifact(prior_turns)
    operation = operation if operation in OPERATIONS else derive_operation(
        user_prompt, has_artifact=bool(stored)
    )
    artifact_text, truncated = _fit_artifact(stored) if stored else ("None.", False)
    return (
        "<task_context>\n"
        "We are continuing an existing task/project from the previous conversation turns.\n"
        f"Operation: {operation.upper()} - {_OPERATION_SUMMARY[operation]}\n"
        "</task_context>\n\n"
        "<previous_work>\n"
        f"{_render_prior(prior_turns, stored, operation in REWRITING_OPERATIONS)}\n"
        "</previous_work>\n\n"
        f"{_artifact_open_tag(prior_turns, stored)}\n"
        f"{artifact_text}\n"
        "</working_artifact>\n\n"
        "<current_request>\n"
        f"{user_prompt}\n"
        "</current_request>\n\n"
        "<execution_instruction>\n"
        f"{_contract(operation, bool(stored), truncated)}\n"
        "</execution_instruction>"
    )


_OPERATION_SUMMARY = {
    CREATE: "produce new work.",
    MODIFY: "change the working artifact below and return it complete.",
    FIX: "correct the working artifact below and return it complete.",
    EXTEND: "add to the working artifact below and return it complete.",
    CONTINUE: "build on the previous work below.",
    EXPLAIN: "answer about the previous work below without rewriting it.",
}

# Sentences kept verbatim across every continued operation so the model always
# sees the continuity rule, whatever the operation adds on top.
_CONTINUITY = (
    "Continue the existing work and apply the current request to it.\n"
    "Modify the latest working artifact when the current request changes that work.\n"
    "Use the previous work when it is relevant.\n"
    "Do not treat the current request as an unrelated standalone question.\n"
    "Do not include wrapper tags from this prompt in your answer."
)

# The output contract for a request that rewrites the artifact. Without this the
# model is free to answer the request with a new, smaller example instead.
_REWRITE_CONTRACT = (
    "Return the COMPLETE updated artifact - not a fragment, not a diff, not a "
    "description of the change.\n"
    "Preserve everything the current request does not ask you to change: every "
    "section, element, field, label, name, id, class, attribute, handler, "
    "function and the overall structure and layout.\n"
    "Rewrite any explanation, comment, or note so it describes the artifact "
    "after this change. Do not keep wording that describes the previous version, "
    "and do not recommend a change the updated artifact already contains.\n"
    "Change only what the current request asks for.\n"
    "Do not replace the artifact with a new, simpler, generic or placeholder "
    "example, and do not rename or restructure anything you were not asked to.\n"
    "Output the full artifact first, in one block, then at most one short "
    "sentence naming what changed."
)

_TRUNCATION_WARNING = (
    "The working artifact above was cut off at the context limit and is "
    "incomplete. Reproduce exactly the part you were given, keep the change "
    "the current request asks for, and say in one line that the artifact was "
    "truncated - do not invent the missing remainder."
)


_INTERNAL_TAG = re.compile(
    r"</?(?:working_artifact|task_context|previous_work|current_request|execution_instruction)\b[^>]*>",
    re.IGNORECASE,
)


def strip_internal_markers(text: str) -> str:
    """Remove prompt-wrapper tags from a model reply before anyone sees it."""
    if not text or not _INTERNAL_TAG.search(text):
        return text
    cleaned = _INTERNAL_TAG.sub("", text)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _contract(operation: str, has_artifact: bool, truncated: bool) -> str:
    lines = [_CONTINUITY]
    if has_artifact and operation in REWRITING_OPERATIONS:
        lines.append(_REWRITE_CONTRACT)
        if truncated:
            lines.append(_TRUNCATION_WARNING)
    elif has_artifact and operation == EXPLAIN:
        lines.append(
            "Answer about the working artifact above. Do not rewrite or "
            "regenerate it unless the current request asks for that."
        )
    elif has_artifact:
        lines.append(
            "The working artifact above is the current state of this task. "
            "Build on it and stay consistent with it; produce what the current "
            "request asks for without discarding or contradicting that work."
        )
    return "\n".join(lines)


def _artifact_open_tag(turns, artifact: Optional[str]) -> str:
    """Name the artifact so the model knows WHAT it is holding."""
    if not artifact:
        return "<working_artifact>"
    origin = ""
    for turn in turns:
        if _working_artifact(getattr(turn, "response", None)) == artifact:
            origin = (getattr(turn, "prompt", "") or "").strip().replace('"', "'")
            break
    attributes = f' kind="{_artifact_kind(artifact)}" chars="{len(artifact)}"'
    if origin:
        if len(origin) > 160:
            origin = origin[:159].rstrip() + "…"
        attributes = f' origin="{origin}"' + attributes
    return f"<working_artifact{attributes}>"


def _artifact_kind(text: str) -> str:
    """A coarse, domain-neutral label. Never a language or framework name."""
    stripped = (text or "").lstrip()
    if stripped.startswith("<") and "</" in stripped:
        return "markup document"
    if "```" in stripped:
        return "document with code blocks"
    return "text"


def _elliptical(prompt: str, tokens: set) -> bool:
    """A follow-up that does not stand on its own as a new request."""
    if _ANAPHORA.search(prompt or ""):
        return True
    if _NEW_TOPIC.search((prompt or "").strip()):
        return False
    if len(tokens) <= 2:
        return True
    return len(tokens) <= 5 and bool(_MODIFIER.search((prompt or "").strip()))


def _working_artifact(response: Optional[str]) -> Optional[str]:
    """The stored model result, when it is actual work rather than an error note."""
    if not response or not response.strip():
        return None
    if response.lstrip().startswith("[error]"):
        return None
    return response


def _latest_stored_artifact(turns) -> Optional[str]:
    latest = None
    for turn in turns:
        artifact = _working_artifact(getattr(turn, "response", None))
        if artifact is not None:
            latest = artifact
    return latest


def _fit_artifact(text: str) -> tuple:
    """Return (text, truncated). A cut is always marked, never silent."""
    if len(text) <= _MAX_CONTEXT_CHARS:
        return text, False
    kept = text[:_MAX_CONTEXT_CHARS]
    marker = (
        f"\n[TRUNCATED: {len(kept)} of {len(text)} characters shown. "
        "The remainder was not included.]"
    )
    return kept + marker, True


def _render_prior(turns, artifact: Optional[str] = None, collapse_superseded: bool = False) -> str:
    """Full branch, oldest first. Assistant text is dropped from the front if needed.

    The response that IS the working artifact is not repeated here - it is
    shown once, under <working_artifact>, where the contract points at it.

    When the current request rewrites that artifact, earlier responses are
    superseded versions of it. They are named rather than reproduced: a model
    asked to return the artifact complete must not be able to copy a stale
    version of it out of the history.
    """
    blocks = []
    for turn in turns:
        response = turn.response or ""
        if artifact and response == artifact:
            response = "[the working artifact shown below]"
        elif collapse_superseded and _working_artifact(response) is not None:
            response = (
                f"[superseded version, {len(response)} characters - "
                "replaced by the working artifact below]"
            )
        blocks.append((turn.prompt, response))

    def render():
        lines = []
        for prompt, response in blocks:
            if response:
                lines.append(f"User: {prompt}\nAssistant: {response}")
            else:
                lines.append(f"User: {prompt}")
        return "\n\n".join(lines)

    text = render()
    index = 0
    while len(text) > _MAX_CONTEXT_CHARS and index < len(blocks):
        prompt, _response = blocks[index]
        blocks[index] = (prompt, "")
        index += 1
        text = render()
    return text
