from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report import build_report, entry_time, terminal_text


class ReportTest(unittest.TestCase):
    def test_history_keeps_legacy_prompts_and_deduplicates_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            prompts = [
                {"event": "user_prompt", "prompt": "Before prompt IDs"},
                {"event": "user_prompt", "prompt_id": "one", "prompt": "Please help"},
                {"event": "user_prompt", "prompt_id": "pending", "prompt": "Not scored yet"},
            ]
            scores = [
                {"event": "prompt_score", "prompt_id": "one", "overall_niceness": 50, "schema_version": 1},
                {"event": "prompt_score", "prompt_id": "one", "overall_niceness": 70, "schema_version": 2},
                {"event": "prompt_score", "prompt_id": "missing-text", "overall_niceness": 50},
                {"event": "prompt_score", "prompt_id": "bad", "overall_niceness": True},
            ]
            (path / "prompts.jsonl").write_text("\n".join(map(json.dumps, prompts)), encoding="utf-8")
            (path / "scores.jsonl").write_text("\n".join(map(json.dumps, scores)) + '\n{"partial":', encoding="utf-8")
            result = build_report({"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": directory})
            self.assertEqual(result["overall_score"], 630)
            self.assertEqual(result["scored_prompt_count"], 2)
            self.assertEqual(result["captured_prompt_count"], 3)
            self.assertEqual(result["unscored_prompt_count"], 2)
            self.assertEqual(result["skipped_record_count"], 2)
            self.assertEqual(result["prompts"][1]["score"], 685)
            self.assertIsNone(result["prompts"][-1]["prompt"])

    def test_summary_is_read_only_and_does_not_include_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing"
            result = subprocess.run([sys.executable, str(ROOT / "scripts/report.py"),
                                     "--data-dir", str(path), "--summary", "--json"],
                                    text=True, capture_output=True, check=True)
            report = json.loads(result.stdout)
            self.assertIsNone(report["overall_score"])
            self.assertNotIn("prompts", report)
            self.assertNotIn("username", report)
            self.assertFalse(path.exists())

    def test_legacy_identity_is_ignored_and_left_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            legacy = path / "identity.json"
            legacy.write_bytes(b"old unreadable identity\xff")
            score = {"event": "prompt_score", "prompt_id": "one", "overall_niceness": 70}
            (path / "scores.jsonl").write_text(json.dumps(score), encoding="utf-8")
            result = build_report({"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": directory})
            self.assertEqual(result["overall_score"], 685)
            self.assertNotIn("username", result)
            self.assertEqual(legacy.read_bytes(), b"old unreadable identity\xff")

    def test_recent_history_is_chronological_including_orphaned_scores(self):
        entries = [
            {"captured_at": "2026-10-01T12:00:00Z"},
            {"scored_at": "2026-09-01T12:00:00+00:00"},
            {"captured_at": "invalid"},
        ]
        self.assertEqual(sorted(entries, key=entry_time), [entries[2], entries[1], entries[0]])

    def test_prompt_control_characters_cannot_control_terminal(self):
        text = terminal_text("Hello\x1b[2J\u202esecret\nnext line")
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\u202e", text)
        self.assertIn("\n", text)


if __name__ == "__main__":
    unittest.main()
