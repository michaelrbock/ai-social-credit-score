from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAKE_CLAUDE = ROOT / "tests" / "fixtures" / "fake_claude.py"
sys.path.insert(0, str(ROOT / "scripts"))

from score_prompt import (
    ScoringError,
    credit_score_from_niceness,
    score_prompt,
    scoring_enabled,
    validate_assessment,
)


class ScorePromptTest(unittest.TestCase):
    def test_scoring_is_enabled_by_default_with_explicit_opt_out(self) -> None:
        self.assertTrue(scoring_enabled({}))
        for value in ("1", "true", "yes", "on", "TRUE"):
            self.assertTrue(scoring_enabled({"AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED": value}))
        for value in ("0", "false", "no", "off", ""):
            self.assertFalse(scoring_enabled({"AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED": value}))

    def test_rejects_retired_api_backend_settings(self) -> None:
        for backend in ("api", "messages-api", "auto"):
            with self.subTest(backend=backend):
                with self.assertRaisesRegex(ScoringError, "no longer supports direct API scoring"):
                    score_prompt(
                        "Hello",
                        "prompt-1",
                        "session-1",
                        {
                            "AI_SOCIAL_CREDIT_SCORE_BACKEND": backend,
                            "ANTHROPIC_API_KEY": "test-secret",
                        },
                        runner=lambda *args, **kwargs: self.fail("Scorer was called"),
                    )

    def test_defaults_to_subscription_even_with_api_credentials_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            invocation_log = Path(temporary_directory) / "invocation.json"
            environment = os.environ.copy()
            environment.pop("AI_SOCIAL_CREDIT_SCORE_BACKEND", None)
            environment["AI_SOCIAL_CREDIT_SCORE_CLAUDE_EXECUTABLE"] = str(
                FAKE_CLAUDE
            )
            environment["FAKE_CLAUDE_INVOCATION_LOG"] = str(invocation_log)
            environment["CLAUDECODE"] = "1"
            environment["ANTHROPIC_API_KEY"] = "must-not-reach-child"
            environment["ANTHROPIC_AUTH_TOKEN"] = "must-not-reach-child"

            result = score_prompt(
                "Fix this, please.",
                "prompt-123",
                "session-456",
                environment,
            )

            invocation = json.loads(invocation_log.read_text())
            self.assertIn("-p", invocation["args"])
            self.assertIn("--safe-mode", invocation["args"])
            self.assertIn("--no-session-persistence", invocation["args"])
            self.assertIn("--json-schema", invocation["args"])
            tools_index = invocation["args"].index("--tools")
            self.assertEqual(invocation["args"][tools_index + 1], "")
            self.assertNotIn("Fix this, please.", invocation["args"])
            self.assertIn("Fix this, please.", invocation["stdin"])
            self.assertEqual(invocation["scorer_child"], "1")
            self.assertFalse(invocation["claudecode_present"])
            self.assertFalse(invocation["api_key_present"])
            self.assertFalse(invocation["auth_token_present"])

            self.assertEqual(result["backend"], "claude-code")
            self.assertEqual(result["provider"], "firstParty")
            self.assertEqual(result["overall_niceness"], 68)
            self.assertEqual(result["credit_score"], 674)
            self.assertEqual(result["schema_version"], 2)
            self.assertEqual(result["usage"]["cache_creation_input_tokens"], 1000)

    def test_credit_score_maps_niceness_to_300_850(self) -> None:
        self.assertEqual(credit_score_from_niceness(0), 300)
        self.assertEqual(credit_score_from_niceness(1), 306)
        self.assertEqual(credit_score_from_niceness(50), 575)
        self.assertEqual(credit_score_from_niceness(68), 674)
        self.assertEqual(credit_score_from_niceness(100), 850)
        with self.assertRaises(ValueError):
            credit_score_from_niceness(-1)
        with self.assertRaises(ValueError):
            credit_score_from_niceness(101)
        with self.assertRaises(ValueError):
            credit_score_from_niceness(True)

    def test_rejects_out_of_range_model_output(self) -> None:
        with self.assertRaisesRegex(ScoringError, "hostility"):
            validate_assessment(
                {
                    "directedness": "directed_at_ai",
                    "respect": 2,
                    "warmth": 2,
                    "cooperation": 2,
                    "hostility": 7,
                    "overall_niceness": 50,
                    "confidence": 0.8,
                    "rationale": "Neutral.",
                }
            )


if __name__ == "__main__":
    unittest.main()
