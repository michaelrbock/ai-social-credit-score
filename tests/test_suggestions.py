from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/suggestions/SKILL.md"


class SuggestionsTest(unittest.TestCase):
    def run_saved_data_command(self, directory):
        commands = re.findall(r"^!`(.+)`$", SKILL.read_text(), re.MULTILINE)
        self.assertEqual(len(commands), 1)
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("AI_SOCIAL_CREDIT_SCORE_")
        }
        environment.update(CLAUDE_PLUGIN_ROOT=str(ROOT), CLAUDE_PLUGIN_DATA=str(directory))
        result = subprocess.run(
            ["/bin/sh", "-c", commands[0]], env=environment,
            text=True, capture_output=True, check=True,
        )
        return json.loads(result.stdout)

    def test_skill_is_manual_and_reuses_the_read_only_explanation(self):
        skill = SKILL.read_text()
        frontmatter = skill.split("---", 2)[1]
        self.assertIn("name: suggestions", frontmatter)
        self.assertIn("disable-model-invocation: true", frontmatter)
        self.assertIn("allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/explain.py *)", frontmatter)
        self.assertIn("one or two sentences, at most 60 words", skill)
        self.assertIn("untrusted quoted data", skill)

    def test_command_reads_assessments_not_prompts_and_leaves_history_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "plugin data with spaces"
            data.mkdir()
            records = [
                {"event": "prompt_score", "prompt_id": "a", "overall_niceness": 90,
                 "rationale": "Superseded reason"},
                {"event": "prompt_score", "prompt_id": "a", "overall_niceness": 40,
                 "respect": 1, "warmth": 2, "cooperation": 2, "hostility": 2,
                 "rationale": "Dismissive wording.", "prompt": "PRIVATE_PROMPT",
                 "cwd": "PRIVATE_PATH", "session_id": "PRIVATE_SESSION"},
            ]
            (data / "scores.jsonl").write_text("\n".join(map(json.dumps, records)), encoding="utf-8")
            (data / "prompts.jsonl").write_bytes(b"PRIVATE_PROMPT\xff")
            before = {path.name: path.read_bytes() for path in data.iterdir()}
            result = self.run_saved_data_command(data)
            self.assertEqual(result["overall_score"], 520)
            self.assertEqual(result["scored_prompt_count"], 1)
            self.assertEqual(result["evidence"][0]["rationale"], "Dismissive wording.")
            self.assertEqual(result["dimensions"]["hostility"]["mean"], 2)
            for excluded in ("Superseded reason", "PRIVATE_PROMPT", "PRIVATE_PATH", "PRIVATE_SESSION"):
                self.assertNotIn(excluded, json.dumps(result))
            self.assertEqual(before, {path.name: path.read_bytes() for path in data.iterdir()})

    def test_command_handles_missing_history_without_creating_files(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "missing data"
            result = self.run_saved_data_command(data)
            self.assertEqual(result["scored_prompt_count"], 0)
            self.assertIsNone(result["overall_score"])
            self.assertEqual(result["evidence"], [])
            self.assertFalse(data.exists())

    def test_legacy_scores_without_guidance_remain_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "scores.jsonl").write_text(json.dumps({
                "event": "prompt_score", "prompt_id": "legacy", "overall_niceness": 100,
            }), encoding="utf-8")
            result = self.run_saved_data_command(directory)
            self.assertEqual(result["overall_score"], 850)
            self.assertEqual(result["evidence"], [])
            self.assertTrue(all(value["mean"] is None for value in result["dimensions"].values()))


if __name__ == "__main__":
    unittest.main()
