from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from explain import build_explanation, format_explanation
from report import build_report


def assessment(key, niceness, **fields):
    return {"event": "prompt_score", "prompt_id": key,
            "overall_niceness": niceness, **fields}


class ExplainTest(unittest.TestCase):
    def save_scores(self, directory, records):
        path = Path(directory) / "scores.jsonl"
        path.write_text("\n".join(map(json.dumps, records)), encoding="utf-8")
        return {"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": directory}

    def test_uses_same_deduplicated_score_as_report_and_explains_contributions(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.save_scores(directory, [
                assessment("a", 0, rationale="Superseded assessment"),
                assessment("a", 80, respect=3, hostility=0, rationale="Warm and cooperative"),
                assessment("b", 50, respect=2, hostility=1, rationale="Neutral request"),
                assessment("c", 20, respect=1, hostility=4, rationale="Hostile wording"),
                assessment("invalid", True),
                {"event": "unrelated", "overall_niceness": 100},
            ])
            result = build_explanation(environment)
            self.assertEqual(result["overall_score"], build_report(environment)["overall_score"])
            self.assertEqual(result["overall_score"], 575)
            self.assertEqual(result["niceness_total"], 150)
            self.assertEqual(result["scored_prompt_count"], 3)
            self.assertEqual(result["distribution"]["above_neutral"]["credit_points_vs_neutral"], 55)
            self.assertEqual(result["distribution"]["below_neutral"]["credit_points_vs_neutral"], -55)
            self.assertEqual(result["dimensions"]["respect"]["mean"], 2)
            self.assertEqual(result["dimensions"]["hostility"]["mean"], 1.67)
            self.assertIsNone(result["dimensions"]["warmth"]["mean"])
            self.assertEqual(result["skipped_record_count"], 2)
            self.assertNotIn("Superseded", json.dumps(result))

    def test_does_not_read_prompt_log_or_modify_history(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.save_scores(directory, [
                assessment("a", 50, rationale="Neutral", prompt="RAW_PROMPT_SECRET",
                           cwd="PRIVATE_PROJECT", session_id="PRIVATE_SESSION"),
            ])
            prompts = Path(directory) / "prompts.jsonl"
            prompts.write_bytes(b"RAW_PROMPT_SECRET\xff")  # Reading as UTF-8 would fail.
            before = {path.name: path.read_bytes() for path in Path(directory).iterdir()}
            result = build_explanation(environment)
            self.assertEqual(result["overall_score"], 575)
            rendered = json.dumps(result)
            for secret in ("RAW_PROMPT_SECRET", "PRIVATE_PROJECT", "PRIVATE_SESSION"):
                self.assertNotIn(secret, rendered)
            self.assertEqual(before, {path.name: path.read_bytes() for path in Path(directory).iterdir()})

    def test_empty_history_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/explain.py"),
                 "--data-dir", str(missing), "--json"],
                text=True, capture_output=True, check=True,
            )
            parsed = json.loads(result.stdout)
            self.assertIsNone(parsed["overall_score"])
            self.assertEqual(parsed["scored_prompt_count"], 0)
            self.assertIn("No scored prompts", format_explanation(parsed))
            self.assertFalse(missing.exists())

    def test_examples_are_bounded_and_terminal_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            records = [assessment(str(i), i * 5, rationale="\x1b[2J" + "x" * 500,
                                  scored_at="d" * 500, warmth=True)
                       for i in range(20)]
            result = build_explanation(self.save_scores(directory, records))
            self.assertLessEqual(len(result["evidence"]), 9)
            self.assertEqual(result["assessments_with_rationale"], 20)
            for item in result["evidence"]:
                self.assertLessEqual(len(item["rationale"]), 300)
                self.assertLessEqual(len(item["scored_at"]), 40)
            self.assertNotIn("\x1b", format_explanation(result))
            self.assertEqual(result["dimensions"]["warmth"]["assessment_count"], 0)

    def test_exact_rounding_does_not_use_displayed_mean(self):
        with tempfile.TemporaryDirectory() as directory:
            records = [assessment(str(i), int(i == 0)) for i in range(11)]
            result = build_explanation(self.save_scores(directory, records))
            self.assertEqual(result["mean_niceness"], 0.09)
            self.assertEqual(result["overall_score"], 301)
            self.assertEqual(result["assessments_with_rationale"], 0)
            self.assertEqual(result["evidence"], [])

    def test_repeated_rationales_do_not_crowd_out_other_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            records = [assessment(str(i), 80, rationale="Same reason") for i in range(5)]
            records.append(assessment("other", 70, rationale="Different reason"))
            result = build_explanation(self.save_scores(directory, records))
            self.assertEqual(len(result["evidence"]), 2)
            self.assertEqual(result["assessments_with_rationale"], 6)

    def test_cli_data_directory_overrides_inherited_file_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            self.save_scores(directory, [assessment("a", 50)])
            other = Path(directory) / "other.jsonl"
            other.write_text(json.dumps(assessment("b", 100)), encoding="utf-8")
            environment = dict(os.environ, AI_SOCIAL_CREDIT_SCORE_SCORES_FILE=str(other))
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/explain.py"),
                 "--data-dir", directory, "--json"],
                env=environment, text=True, capture_output=True, check=True,
            )
            self.assertEqual(json.loads(result.stdout)["overall_score"], 575)


if __name__ == "__main__":
    unittest.main()
