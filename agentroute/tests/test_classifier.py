"""Tests for the baseline classifier. No API keys and no `laya` required."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from classifier import COMPLEXITIES, INTENTS, classify  # noqa: E402
from errors import ClassifierError  # noqa: E402


class TestClassifier(unittest.TestCase):
    def test_blender_intents(self):
        for prompt in (
            "Create a 3D chair in Blender",
            "Generate a Blender Python script for a wardrobe",
        ):
            self.assertEqual(classify(prompt)["intent"], "blender", prompt)

    def test_coding_intent(self):
        self.assertEqual(
            classify("Write a Python function to sort a list")["intent"], "coding"
        )

    def test_reasoning_intent(self):
        self.assertEqual(
            classify("Design the architecture of a multi-agent system")["intent"],
            "reasoning",
        )

    def test_general_intent(self):
        self.assertEqual(classify("What is Python?")["intent"], "general")

    def test_schema_is_valid(self):
        result = classify("Design the architecture of a multi-agent system")
        self.assertIn(result["intent"], INTENTS)
        self.assertIn(result["complexity"], COMPLEXITIES)
        self.assertTrue(0.0 <= result["confidence"] <= 1.0)

    def test_empty_prompt_raises(self):
        with self.assertRaises(ClassifierError):
            classify("   ")

    def test_does_not_depend_on_laya(self):
        # classify() already ran above without laya installed; assert it's absent.
        self.assertNotIn("laya", sys.modules)


if __name__ == "__main__":
    unittest.main()
