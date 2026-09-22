from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAKE_CLAUDE = ROOT / "tests" / "fixtures" / "fake_claude.py"
sys.path.insert(0, str(ROOT / "scripts"))

from score_prompt import ScoringError, score_prompt, validate_assessment


class FakeResponse:
    def __init__(self, payload: object):
        self.buffer = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self, amount: int = -1) -> bytes:
        return self.buffer.read(amount)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class ScorePromptTest(unittest.TestCase):
    def test_calls_anthropic_with_forced_tool_and_returns_linked_score(self) -> None:
        captured: dict[str, object] = {}
        api_response = {
            "model": "claude-haiku-4-5-20251001",
            "content": [
                {
                    "type": "tool_use",
                    "name": "record_niceness_score",
                    "input": {
                        "directedness": "directed_at_ai",
                        "respect": 3,
                        "warmth": 2,
                        "cooperation": 3,
                        "hostility": 0,
                        "overall_niceness": 68,
                        "confidence": 0.9,
                        "rationale": "Direct and respectful, with neutral warmth.",
                    },
                }
            ],
            "usage": {"input_tokens": 300, "output_tokens": 80},
        }

        def fake_urlopen(request: object, timeout: int) -> FakeResponse:
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(api_response)

        result = score_prompt(
            "Fix this, please.",
            "prompt-123",
            "session-456",
            {
                "AI_SOCIAL_CREDIT_SCORE_BACKEND": "api",
                "ANTHROPIC_API_KEY": "test-secret",
            },
            urlopen=fake_urlopen,
        )

        request = captured["request"]
        request_body = json.loads(request.data)
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers["x-api-key"], "test-secret")
        self.assertEqual(captured["timeout"], 90)
        self.assertEqual(
            request_body["tool_choice"],
            {"type": "tool", "name": "record_niceness_score"},
        )
        self.assertIn("Fix this, please.", request_body["messages"][0]["content"])

        self.assertEqual(result["prompt_id"], "prompt-123")
        self.assertEqual(result["backend"], "api")
        self.assertEqual(result["session_id"], "session-456")
        self.assertEqual(result["overall_niceness"], 68)
        self.assertEqual(result["rubric_version"], "niceness-rubric-v1")
        self.assertEqual(result["usage"]["input_tokens"], 300)
        self.assertNotIn("prompt", result)

    def test_requires_an_explicit_api_key(self) -> None:
        with self.assertRaisesRegex(ScoringError, "ANTHROPIC_API_KEY"):
            score_prompt(
                "Hello",
                "prompt-1",
                "session-1",
                {"AI_SOCIAL_CREDIT_SCORE_BACKEND": "api"},
            )

    def test_uses_claude_code_subscription_backend_without_an_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            invocation_log = Path(temporary_directory) / "invocation.json"
            environment = os.environ.copy()
            environment.pop("ANTHROPIC_API_KEY", None)
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
            self.assertEqual(result["usage"]["cache_creation_input_tokens"], 1000)

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
