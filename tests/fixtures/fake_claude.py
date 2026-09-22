#!/usr/bin/env python3
"""Deterministic fake for subscription-backend integration tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


invocation_log = os.environ.get("FAKE_CLAUDE_INVOCATION_LOG")
if invocation_log:
    Path(invocation_log).write_text(
        json.dumps(
            {
                "args": sys.argv[1:],
                "stdin": sys.stdin.read(),
                "scorer_child": os.environ.get(
                    "AI_SOCIAL_CREDIT_SCORE_SCORER_CHILD"
                ),
                "claudecode_present": "CLAUDECODE" in os.environ,
                "api_key_present": "ANTHROPIC_API_KEY" in os.environ,
                "auth_token_present": "ANTHROPIC_AUTH_TOKEN" in os.environ,
            }
        )
    )

print(
    json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "provider": "firstParty",
            "structured_output": {
                "directedness": "directed_at_ai",
                "respect": 3,
                "warmth": 2,
                "cooperation": 3,
                "hostility": 0,
                "overall_niceness": 68,
                "confidence": 0.9,
                "rationale": "Direct and respectful, with neutral warmth.",
            },
            "modelUsage": {
                "claude-haiku-4-5-20251001": {
                    "inputTokens": 100,
                    "outputTokens": 50,
                }
            },
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_creation_input_tokens": 1000,
            },
        }
    )
)
