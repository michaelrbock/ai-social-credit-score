from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_prompt.py"
FAKE_CLAUDE = ROOT / "tests" / "fixtures" / "fake_claude.py"
sys.path.insert(0, str(ROOT / "scripts"))

from capture_prompt import log_path


class CapturePromptTest(unittest.TestCase):
    def run_hook(
        self,
        payload: object,
        log_file: Path,
        *,
        disabled: bool = False,
        scoring_enabled: bool = False,
        scorer_child: bool = False,
        claude_executable: Path | None = None,
        raw_input: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("AI_SOCIAL_CREDIT_SCORE_DEBUG", None)
        environment.pop("ANTHROPIC_API_KEY", None)
        environment["AI_SOCIAL_CREDIT_SCORE_LOG_FILE"] = str(log_file)
        if disabled:
            environment["AI_SOCIAL_CREDIT_SCORE_DISABLED"] = "1"
        else:
            environment.pop("AI_SOCIAL_CREDIT_SCORE_DISABLED", None)
        if scoring_enabled:
            environment["AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED"] = "1"
            environment["AI_SOCIAL_CREDIT_SCORE_CLAUDE_EXECUTABLE"] = str(
                claude_executable or "/definitely/missing/claude"
            )
        else:
            environment.pop("AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED", None)
        if scorer_child:
            environment["AI_SOCIAL_CREDIT_SCORE_SCORER_CHILD"] = "1"
        else:
            environment.pop("AI_SOCIAL_CREDIT_SCORE_SCORER_CHILD", None)

        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=raw_input if raw_input is not None else json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

    def test_captures_exact_prompt_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "nested" / "prompts.jsonl"
            payload = {
                "session_id": "session-123",
                "transcript_path": "/private/transcript.jsonl",
                "cwd": "/workspace/demo",
                "permission_mode": "default",
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Please help me.\nThank you! 🌱",
            }

            result = self.run_hook(payload, log_file)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")

            records = [json.loads(line) for line in log_file.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["schema_version"], 1)
            uuid.UUID(record["prompt_id"])
            self.assertEqual(record["event"], "user_prompt")
            self.assertEqual(record["session_id"], "session-123")
            self.assertEqual(record["cwd"], "/workspace/demo")
            self.assertEqual(record["prompt"], payload["prompt"])
            self.assertNotIn("transcript_path", record)
            datetime.fromisoformat(record["captured_at"].replace("Z", "+00:00"))

            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(log_file.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(log_file.parent.stat().st_mode), 0o700)

    def test_appends_one_json_object_per_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            first = {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "First",
            }
            second = {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Second",
            }

            self.run_hook(first, log_file)
            self.run_hook(second, log_file)

            records = [json.loads(line) for line in log_file.read_text().splitlines()]
            self.assertEqual([record["prompt"] for record in records], ["First", "Second"])

    def test_ignores_other_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            result = self.run_hook(
                {"hook_event_name": "SessionStart", "prompt": "Not a prompt event"},
                log_file,
            )

            self.assertEqual(result.returncode, 0)
            self.assertFalse(log_file.exists())

    def test_scoring_failure_is_recorded_without_losing_the_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            result = self.run_hook(
                {"hook_event_name": "UserPromptSubmit", "prompt": "Score me"},
                log_file,
                scoring_enabled=True,
            )

            self.assertEqual(result.returncode, 0)
            prompt_record = json.loads(log_file.read_text())
            error_record = json.loads(
                log_file.with_name("score_errors.jsonl").read_text()
            )
            self.assertEqual(error_record["prompt_id"], prompt_record["prompt_id"])
            self.assertEqual(error_record["error_type"], "ScoringError")
            self.assertIn("executable was not found", error_record["message"])

    def test_capture_and_subscription_score_are_linked_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            result = self.run_hook(
                {
                    "session_id": "session-123",
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "Please fix this.",
                },
                log_file,
                scoring_enabled=True,
                claude_executable=FAKE_CLAUDE,
            )

            self.assertEqual(result.returncode, 0)
            prompt_record = json.loads(log_file.read_text())
            score_record = json.loads(log_file.with_name("scores.jsonl").read_text())
            self.assertEqual(score_record["prompt_id"], prompt_record["prompt_id"])
            self.assertEqual(score_record["session_id"], "session-123")
            self.assertEqual(score_record["backend"], "claude-code")
            self.assertEqual(score_record["overall_niceness"], 68)

    def test_uses_claude_plugin_data_as_the_default_storage_directory(self) -> None:
        path = log_path(
            {"CLAUDE_PLUGIN_DATA": "/tmp/example-plugin-data"},
            platform="darwin",
        )

        self.assertEqual(
            path,
            Path("/tmp/example-plugin-data/prompts.jsonl"),
        )

    def test_preserves_a_prompt_id_from_claude_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            result = self.run_hook(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt_id": "native-prompt-id",
                    "prompt": "Hello",
                },
                log_file,
            )

            self.assertEqual(result.returncode, 0)
            record = json.loads(log_file.read_text())
            self.assertEqual(record["prompt_id"], "native-prompt-id")

    def test_scorer_child_marker_prevents_recursive_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            result = self.run_hook(
                {"hook_event_name": "UserPromptSubmit", "prompt": "Do not capture"},
                log_file,
                scorer_child=True,
            )

            self.assertEqual(result.returncode, 0)
            self.assertFalse(log_file.exists())

    def test_disabled_capture_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            result = self.run_hook(
                {"hook_event_name": "UserPromptSubmit", "prompt": "Do not save me"},
                log_file,
                disabled=True,
            )

            self.assertEqual(result.returncode, 0)
            self.assertFalse(log_file.exists())

    def test_malformed_input_never_blocks_the_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "prompts.jsonl"
            result = self.run_hook({}, log_file, raw_input="not json")

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertFalse(log_file.exists())


if __name__ == "__main__":
    unittest.main()
