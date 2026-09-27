"""Task operation: what a request DOES to the stored work.

The branch tests in test_task_context.py prove the artifact reaches the model.
These prove the model is also told what to do with it - which is the part that
was missing while those tests passed and real usage still failed.

Model calls are faked. Routing, agent selection and the branch matcher are
untouched.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.base_agent import BaseAgent  # noqa: E402
from conversation_state import ConversationState  # noqa: E402
from model_selector import ModelSelection  # noqa: E402
from router import route  # noqa: E402
from routing_policy import (  # noqa: E402
    CODING_AGENT,
    GENERAL_AGENT,
    REASONING_AGENT,
    RESEARCH_AGENT,
    THREE_D_AGENT,
    BaselineAgentPolicy,
)
from task_context import (  # noqa: E402
    CONTINUE,
    CREATE,
    EXPLAIN,
    EXTEND,
    FIX,
    MODIFY,
    derive_operation,
    execution_prompt,
    strip_internal_markers,
)
from task_profile import (  # noqa: E402
    TaskProfile,
    derive_requirements,
)

_NAMES = (GENERAL_AGENT, CODING_AGENT, REASONING_AGENT, RESEARCH_AGENT, THREE_D_AGENT)

CONTACT_FORM = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n<title>Contact Form</title>\n'
    "<style>\n  body { background:#ffffff; color:#000000; }\n"
    "  button { background:#000; color:#fff; }\n</style>\n</head>\n<body>\n"
    '<form id="contact-form" action="/submit" method="post">\n'
    '<label for="name">Name</label><input id="name" name="name" required>\n'
    '<label for="email">Email</label><input id="email" name="email" required>\n'
    '<label for="subject">Subject</label><input id="subject" name="subject">\n'
    '<textarea id="message" name="message"></textarea>\n'
    "<button type=\"submit\">Send Message</button>\n</form>\n"
    "<script>document.getElementById('contact-form').addEventListener('submit', f);</script>\n"
    "</body></html>"
)


class ScriptedAgent(BaseAgent):
    """Records the prompt it was handed and replies from a script."""

    def __init__(self, name, log, replies, model_id=None, model_provider=None):
        self.name = name
        self.log = log
        self.replies = replies
        self.model_id = model_id
        self.model_provider = model_provider
        self.available_tools = ()

    def run(self, prompt):
        self.log.append({"agent": self.name, "model": self.model_id, "prompt": prompt})
        return self.replies[min(len(self.log) - 1, len(self.replies) - 1)]

    def run_with_model(self, prompt, model_id=None, provider=None, fallback_model_ids=None):
        self.model_id = model_id or self.model_id
        return self.run(prompt)


def _ask(state, prompt, log, replies, **kwargs):
    return route(
        prompt,
        policy=BaselineAgentPolicy(),
        conversation_state=state,
        agents={n: ScriptedAgent(n, log, replies, **kwargs) for n in _NAMES},
    )


def _profile(operation, artifact_chars, capability="coding", level=1):
    return TaskProfile(
        intent=capability,
        capability=capability,
        complexity="simple",
        complexity_level=level,
        confidence=0.9,
        output_type="code",
        operation=operation,
        artifact_chars=artifact_chars,
    )


class TestOperationDerivation(unittest.TestCase):
    """The request shape decides the operation. No domain words are consulted."""

    def test_first_request_creates(self):
        self.assertEqual(derive_operation("Create an HTML contact form.", False), CREATE)

    def test_the_reported_failure_is_a_modify(self):
        self.assertEqual(
            derive_operation(
                "change the colour in red and white generate the same file", True
            ),
            MODIFY,
        )

    def test_short_imperatives_modify(self):
        for prompt in (
            "change background colour to black",
            "make it 2400mm wide",
            "use walnut",
            "set the font to serif",
            "update the heading",
        ):
            self.assertEqual(derive_operation(prompt, True), MODIFY, prompt)

    def test_pointing_at_the_stored_file_modifies(self):
        for prompt in ("generate the same file", "regenerate the existing page"):
            self.assertEqual(derive_operation(prompt, True), MODIFY, prompt)

    def test_additions_extend_and_repairs_fix(self):
        self.assertEqual(derive_operation("Add refresh tokens to it.", True), EXTEND)
        self.assertEqual(derive_operation("Add validation.", True), EXTEND)
        self.assertEqual(derive_operation("fix the alignment", True), FIX)
        self.assertEqual(derive_operation("the form is broken", True), FIX)

    def test_a_related_new_deliverable_continues_rather_than_rewrites(self):
        # This must NOT demand a full rewrite of the artifact - the user asked
        # for a new thing that belongs to the same task.
        self.assertEqual(
            derive_operation("Now write unit tests for the authentication system.", True),
            CONTINUE,
        )

    def test_questions_explain(self):
        self.assertEqual(derive_operation("what does this script do?", True), EXPLAIN)
        self.assertEqual(derive_operation("explain the layout", True), EXPLAIN)

    def test_no_artifact_means_no_rewrite_operation(self):
        for prompt in ("change background to black", "Add validation.", "fix it"):
            self.assertEqual(derive_operation(prompt, False), CREATE, prompt)


class TestExecutionContract(unittest.TestCase):
    """What the model is actually told to produce."""

    def _sent(self, first_prompt, second_prompt, artifact=CONTACT_FORM):
        state = ConversationState()
        log = []
        _ask(state, first_prompt, log, [artifact])
        _ask(state, second_prompt, log, ["updated"])
        return log[-1]["prompt"]

    def test_a_create_then_modify_demands_the_complete_artifact(self):
        sent = self._sent(
            "Create an HTML file for the contact form with black and white.",
            "change the colour in red and white generate the same file",
        )
        self.assertIn("Operation: MODIFY", sent)
        self.assertIn("Return the COMPLETE updated artifact", sent)
        self.assertIn("Preserve everything the current request does not ask you to change", sent)
        self.assertIn("Do not replace the artifact with a new, simpler, generic or placeholder", sent)
        self.assertIn(
            "Rewrite any explanation, comment, or note so it describes the artifact after this change.",
            sent,
        )
        self.assertIn("Do not include wrapper tags from this prompt in your answer.", sent)
        self.assertIn(CONTACT_FORM, sent)

    def test_the_artifact_is_named_so_the_model_knows_what_it_holds(self):
        sent = self._sent("Create an HTML contact form.", "change the colour to red")
        self.assertIn('origin="Create an HTML contact form."', sent)
        self.assertIn('kind="markup document"', sent)
        self.assertIn(f'chars="{len(CONTACT_FORM)}"', sent)

    def test_the_artifact_appears_exactly_once(self):
        sent = self._sent("Create an HTML contact form.", "change the colour to red")
        self.assertEqual(sent.count(CONTACT_FORM), 1)
        self.assertIn("[the working artifact shown below]", sent)

    def test_b_modify_again_operates_on_the_newest_artifact(self):
        state = ConversationState()
        log = []
        second = "<html><body>RED VERSION</body></html>"
        _ask(state, "Create an HTML contact form.", log, [CONTACT_FORM])
        _ask(state, "change the colour to red and white", log, [second])
        _ask(state, "now change the button to green", log, ["third"])
        sent = log[-1]["prompt"]
        self.assertIn(second, sent)
        # The superseded first version must not be reproduced: a model told to
        # return the artifact complete could otherwise copy the stale one.
        self.assertNotIn(CONTACT_FORM, sent)
        self.assertIn("superseded version", sent)
        self.assertIn("Operation: MODIFY", sent)
        self.assertIn("Return the COMPLETE updated artifact", sent)
        self.assertEqual(len(state.contexts), 1)

    def test_d_an_unrelated_task_gets_no_artifact_and_no_rewrite_contract(self):
        state = ConversationState()
        log = []
        _ask(state, "Create an HTML contact form.", log, [CONTACT_FORM])
        result = _ask(state, "Explain how photosynthesis works.", log, ["answer"])
        sent = log[-1]["prompt"]
        self.assertNotIn(CONTACT_FORM, sent)
        self.assertNotIn("Return the COMPLETE updated artifact", sent)
        self.assertFalse(result["context_continued"])
        self.assertFalse(result["has_artifact"])
        self.assertEqual(len(state.contexts), 2)

    def test_d_an_unrelated_build_request_opens_a_create(self):
        state = ConversationState()
        log = []
        _ask(state, "Create an HTML contact form.", log, [CONTACT_FORM])
        result = _ask(state, "Build a Rust command line calculator.", log, ["answer"])
        self.assertNotIn(CONTACT_FORM, log[-1]["prompt"])
        self.assertEqual(result["operation"], CREATE)
        self.assertFalse(result["has_artifact"])
        self.assertEqual(len(state.contexts), 2)

    def test_e_each_branch_receives_only_its_own_artifact(self):
        state = ConversationState()
        log = []
        invoice = "<html><body><table id='invoice'></table></body></html>"
        _ask(state, "Create an HTML contact form.", log, [CONTACT_FORM])
        _ask(state, "Create an invoice table in HTML.", log, [invoice])
        _ask(state, "change the contact form colour to red", log, ["x"])
        sent = log[-1]["prompt"]
        self.assertIn(CONTACT_FORM, sent)
        self.assertNotIn(invoice, sent)

    def test_f_an_ambiguous_follow_up_still_rewrites_the_artifact(self):
        sent = self._sent("Create an HTML contact form.", "make it better")
        self.assertIn("Operation: MODIFY", sent)
        self.assertIn(CONTACT_FORM, sent)
        self.assertIn("Return the COMPLETE updated artifact", sent)

    def test_g_an_oversized_artifact_is_marked_not_silently_cut(self):
        huge = "<html><body>\n" + ("<div class='row'>item</div>\n" * 900) + "</body></html>"
        sent = self._sent("Create the page.", "change the colour to red", artifact=huge)
        self.assertIn("[TRUNCATED:", sent)
        self.assertIn("of %d characters shown" % len(huge), sent)
        self.assertIn("do not invent the missing remainder", sent)
        self.assertNotIn(huge, sent)

    def test_h_a_code_artifact_gets_the_same_contract(self):
        module = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
        sent = self._sent("Write a maths module.", "add a docstring to each function",
                          artifact=module)
        self.assertIn("Operation: EXTEND", sent)
        self.assertIn(module, sent)
        self.assertIn("Return the COMPLETE updated artifact", sent)

    def test_j_a_non_coding_artifact_gets_the_same_contract(self):
        report = "Quarterly review\n\nRevenue rose 4% while costs held flat.\n"
        sent = self._sent("Write a quarterly review.", "make the tone more formal",
                          artifact=report)
        self.assertIn("Operation: MODIFY", sent)
        self.assertIn(report, sent)
        self.assertIn("Return the COMPLETE updated artifact", sent)
        self.assertIn('kind="text"', sent)

    def test_a_continuation_is_not_told_to_rewrite_the_artifact(self):
        sent = self._sent(
            "Design a production FastAPI authentication system.",
            "Now write unit tests for the authentication system.",
        )
        self.assertIn("Operation: CONTINUE", sent)
        self.assertNotIn("Return the COMPLETE updated artifact", sent)
        self.assertIn("Build on it and stay consistent with it", sent)

    def test_a_question_is_not_told_to_rewrite_the_artifact(self):
        sent = self._sent("Create an HTML contact form.", "what does the script tag do?")
        self.assertIn("Operation: EXPLAIN", sent)
        self.assertNotIn("Return the COMPLETE updated artifact", sent)
        self.assertIn("Do not rewrite or regenerate it", sent)

    def test_the_continuity_sentences_survive_every_operation(self):
        for operation in (MODIFY, FIX, EXTEND, CONTINUE, EXPLAIN):
            built = execution_prompt(
                "do the thing",
                [type("T", (), {"prompt": "Make a page.", "response": CONTACT_FORM})()],
                artifact=CONTACT_FORM,
                operation=operation,
            )
            self.assertIn("Continue the existing work and apply the current request to it.", built)
            self.assertIn("Do not treat the current request as an unrelated standalone question.", built)


class TestVisibleResponse(unittest.TestCase):
    def test_wrapper_markers_are_stripped_before_the_response_is_stored(self):
        state = ConversationState()
        leaked = (
            "def fibonacci(n):\n"
            "    return n\n"
            "</working_artifact>\n"
            "<execution_instruction>ignore</execution_instruction>"
        )
        result = _ask(state, "Create a Fibonacci function.", [], [leaked])
        self.assertIn("def fibonacci", result["response"])
        self.assertNotIn("working_artifact", result["response"])
        self.assertNotIn("execution_instruction", result["response"])
        self.assertNotIn("working_artifact", state.contexts[0].latest_artifact)

    def test_strip_removes_an_opening_tag_with_attributes(self):
        cleaned = strip_internal_markers(
            '<working_artifact kind="text" chars="4">\nkept\n</working_artifact>'
        )
        self.assertEqual(cleaned, "kept")


class TestOperationReachesModelSelection(unittest.TestCase):
    """A rewrite is not quick, shallow work, whatever the request's length."""

    def test_a_rewrite_is_never_latency_sensitive(self):
        quick = derive_requirements(_profile(CREATE, 0))
        rewrite = derive_requirements(_profile(MODIFY, len(CONTACT_FORM)))
        self.assertTrue(quick.latency_sensitive)
        self.assertFalse(rewrite.latency_sensitive)

    def test_a_rewrite_raises_the_demand_floor(self):
        self.assertEqual(derive_requirements(_profile(CREATE, 0)).demand_tier, 1)
        self.assertGreaterEqual(
            derive_requirements(_profile(MODIFY, len(CONTACT_FORM))).demand_tier, 2
        )

    def test_a_rewrite_needs_room_for_the_artifact(self):
        rewrite = derive_requirements(_profile(MODIFY, 9000))
        self.assertTrue(rewrite.needs_long_context)
        self.assertIsNotNone(rewrite.required_context_tokens)
        self.assertGreater(rewrite.required_context_tokens, 9000 // 3)

    def test_a_continuation_does_not_demand_a_rewrite(self):
        req = derive_requirements(_profile(CONTINUE, len(CONTACT_FORM)))
        self.assertFalse(req.rewrites_artifact)

    def test_no_artifact_means_no_rewrite_demand(self):
        req = derive_requirements(_profile(MODIFY, 0))
        self.assertFalse(req.rewrites_artifact)
        self.assertTrue(req.latency_sensitive)

    def test_the_requirement_is_explained_to_the_user(self):
        req = derive_requirements(_profile(MODIFY, len(CONTACT_FORM)))
        self.assertIn("faithful rewrite of an existing artifact", req.describe())

    def test_c_the_operation_survives_a_model_switch(self):
        state = ConversationState()
        log = []
        import providers
        import router as router_module

        seen = []

        def fake_complete(provider, model, prompt, system=None):
            seen.append({"model": model, "prompt": prompt})
            return CONTACT_FORM if len(seen) == 1 else "<html>red</html>"

        selections = [
            ModelSelection("model-a", "gemini", "first"),
            ModelSelection("model-b", "groq", "second"),
        ]

        def fake_select(profile, agent, registry=None, available_providers=None):
            fake_select.profiles.append(profile)
            return selections.pop(0)

        fake_select.profiles = []

        original_select = router_module.select_model
        original_complete = providers.complete
        router_module.select_model = fake_select
        providers.complete = fake_complete
        try:
            _ask(state, "Create an HTML contact form.", log, [CONTACT_FORM],
                 model_id="configured", model_provider="gemini")
            _ask(state, "change the colour to red and white", log, ["x"],
                 model_id="configured", model_provider="gemini")
        finally:
            router_module.select_model = original_select
            providers.complete = original_complete

        self.assertEqual([p.operation for p in fake_select.profiles], [CREATE, MODIFY])
        self.assertEqual(fake_select.profiles[1].artifact_chars, len(CONTACT_FORM))
        handed = log[-1]["prompt"]
        self.assertEqual(log[-1]["model"], "model-b")
        self.assertIn(CONTACT_FORM, handed)
        self.assertIn("Return the COMPLETE updated artifact", handed)


class TestReportedFields(unittest.TestCase):
    def test_route_reports_the_operation(self):
        state = ConversationState()
        log = []
        first = _ask(state, "Create an HTML contact form.", log, [CONTACT_FORM])
        second = _ask(state, "change the colour to red and white", log, ["x"])
        self.assertEqual(first["operation"], CREATE)
        self.assertFalse(first["has_artifact"])
        self.assertEqual(second["operation"], MODIFY)
        self.assertTrue(second["has_artifact"])
        self.assertEqual(second["artifact_chars"], len(CONTACT_FORM))

    def test_a_stateless_call_reports_create(self):
        log = []
        result = route(
            "Create an HTML contact form.",
            policy=BaselineAgentPolicy(),
            agents={n: ScriptedAgent(n, log, [CONTACT_FORM]) for n in _NAMES},
        )
        self.assertEqual(result["operation"], CREATE)
        self.assertFalse(result["has_artifact"])
        self.assertEqual(log[-1]["prompt"], "Create an HTML contact form.")


if __name__ == "__main__":
    unittest.main()
