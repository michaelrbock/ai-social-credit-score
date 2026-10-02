from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from chart import build_chart, format_chart, parse_time, HEIGHT, WIDTH
from report import build_report


def assessment(key, score, date=None, **fields):
    return {"event": "prompt_score", "prompt_id": key,
            "overall_niceness": score, "scored_at": date, **fields}


class ChartTest(unittest.TestCase):
    def save_scores(self, directory, records):
        (Path(directory) / "scores.jsonl").write_text(
            "\n".join(map(json.dumps, records)), encoding="utf-8",
        )
        return {"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": str(directory)}

    def test_sorted_cumulative_history_uses_last_valid_score_and_matches_report(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.save_scores(directory, [
                assessment("a", 80, "2026-10-03T00:00:00Z"),
                assessment("b", 0, "2026-09-30T00:00:00Z"),
                assessment("c", 50, "2026-10-02T00:00:00Z"),
                assessment("b", 20, "2026-10-01T00:00:00Z"),
                assessment("b", True),  # Invalid replacement must not erase b.
                {"event": "not_a_score"},
            ])
            result = build_chart(env)
            self.assertEqual(result["axis"], "time")
            self.assertEqual([p["overall_score"] for p in result["points"]], [410, 493, 575])
            self.assertEqual(result["overall_score"], build_report(env)["overall_score"])
            self.assertEqual(result["scored_prompt_count"], 3)
            self.assertEqual(result["skipped_record_count"], 2)

    def test_timezones_are_normalized_before_sorting(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.save_scores(directory, [
                assessment("later", 100, "2026-10-01T08:00:00-07:00"),
                assessment("earlier", 0, "2026-10-01T14:30:00Z"),
            ])
            result = build_chart(env)
            self.assertEqual([p["overall_score"] for p in result["points"]], [300, 575])
            self.assertIn("2026-10-01 15:00", format_chart(result))
            self.assertIn("Time (UTC)", format_chart(result))

    def test_missing_or_invalid_dates_use_first_seen_prompt_order(self):
        for date in (None, "bad\x1b[2J", "0001-01-01T00:00:00+12:00"):
            with self.subTest(date=date), tempfile.TemporaryDirectory() as directory:
                env = self.save_scores(directory, [
                    assessment("a", 0, "2026-10-03T00:00:00Z"),
                    assessment("b", 20, date),
                    assessment("a", 80, "2026-10-04T00:00:00Z"),
                ])
                result = build_chart(env)
                self.assertEqual(result["axis"], "prompt_order")
                self.assertEqual([p["overall_score"] for p in result["points"]], [740, 575])
                rendered = format_chart(result)
                self.assertIn("timestamps incomplete", rendered)
                self.assertIn("#1", rendered)
                self.assertIn("#2", rendered)
                self.assertNotIn("\x1b", rendered)

    def test_identical_dates_fall_back_to_prompt_order(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.save_scores(directory, [
                assessment("a", 0, "2026-10-01T00:00:00Z"),
                assessment("b", 100, "2026-10-01T00:00:00+00:00"),
            ])
            result = build_chart(env)
            self.assertEqual(result["axis"], "prompt_order")
            self.assertIn("all timestamps identical", format_chart(result))

    def test_single_point_and_flat_histories_at_scale_edges(self):
        for score in (0, 50, 100):
            for count in (1, 20):
                with self.subTest(score=score, count=count), tempfile.TemporaryDirectory() as directory:
                    result = build_chart(self.save_scores(directory, [
                        assessment(str(i), score) for i in range(count)
                    ]))
                    rendered = format_chart(result)
                    rows = re.findall(r"^.{3} \|.*$", rendered, re.MULTILINE)
                    self.assertEqual(len(rows), HEIGHT)
                    self.assertEqual(sum(row.count("@") for row in rows), 1)
                    self.assertTrue(all(len(row) <= WIDTH + 5 for row in rows))
                    labels = [int(row[:3]) for row in rows if row[:3].strip()]
                    self.assertGreaterEqual(min(labels), 300)
                    self.assertLessEqual(max(labels), 850)
                    self.assertGreaterEqual(max(labels) - min(labels), 50)
                    self.assertEqual("One point so far" in rendered, count == 1)

    def test_time_axis_spaces_observations_by_elapsed_time(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_chart(self.save_scores(directory, [
                assessment("a", 50, "2026-10-01T00:00:00Z"),
                assessment("b", 50, "2026-10-02T00:00:00Z"),
                assessment("c", 50, "2026-10-11T00:00:00Z"),
            ]))
            row = next(row[5:] for row in format_chart(result).splitlines()
                       if re.match(r"^.{3} \|", row) and "@" in row)
            self.assertEqual([i for i, char in enumerate(row) if char == "*"], [0, 5])
            self.assertEqual(row.index("@"), WIDTH - 1)

    def test_large_history_is_compact_ascii_and_keeps_latest_score(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.save_scores(directory, [
                assessment(str(i), (i * 37) % 101) for i in range(10000)
            ])
            result = build_chart(env)
            rendered = format_chart(result)
            self.assertTrue(rendered.isascii())
            self.assertLess(len(rendered), 1800)
            self.assertLess(len(rendered.splitlines()), 30)
            self.assertEqual(result["overall_score"], build_report(env)["overall_score"])
            self.assertIn(f"Now: {result['overall_score']} / 850", rendered)

    def test_private_content_is_not_read_or_rendered_and_history_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            env = self.save_scores(directory, [
                assessment("PRIVATE_ID", 50, "2026-10-01T00:00:00Z",
                           rationale="PRIVATE_REASON", prompt="PRIVATE_PROMPT",
                           cwd="PRIVATE_PATH", session_id="PRIVATE_SESSION"),
            ])
            data = Path(directory)
            (data / "prompts.jsonl").write_bytes(b"PRIVATE_PROMPT\xff")
            before = {p.name: p.read_bytes() for p in data.iterdir()}
            result = build_chart(env)
            self.assertNotIn("PRIVATE_", json.dumps(result) + format_chart(result))
            self.assertEqual(before, {p.name: p.read_bytes() for p in data.iterdir()})

    def test_empty_history_and_malformed_records_are_handled_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            result = build_chart({"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": str(missing)})
            self.assertIsNone(result["overall_score"])
            self.assertIn("No scored prompts yet", format_chart(result))
            self.assertFalse(missing.exists())
            (Path(directory) / "scores.jsonl").write_text('{"partial":', encoding="utf-8")
            result = build_chart({"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": directory})
            self.assertEqual(result["skipped_record_count"], 1)
            self.assertIn("Skipped 1", format_chart(result))

    def test_cli_data_dir_overrides_inherited_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            self.save_scores(directory, [assessment("a", 50)])
            other = Path(directory) / "other.jsonl"
            other.write_text(json.dumps(assessment("b", 100)), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/chart.py"), "--data-dir", directory, "--json"],
                env=dict(os.environ, AI_SOCIAL_CREDIT_SCORE_SCORES_FILE=str(other)),
                text=True, capture_output=True, check=True,
            )
            self.assertEqual(json.loads(result.stdout)["overall_score"], 575)

    def test_skill_runs_read_only_helper_with_quoted_plugin_data_path(self):
        skill = (ROOT / "skills/chart/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn("allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/chart.py *)", skill)
        self.assertIn("verbatim inside one fenced `text` code block", skill)
        command, = re.findall(r"^!`(.+)`$", skill, re.MULTILINE)
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "plugin data with spaces"
            data.mkdir()
            self.save_scores(data, [assessment("a", 50)])
            environment = {key: value for key, value in os.environ.items()
                           if not key.startswith("AI_SOCIAL_CREDIT_SCORE_")}
            environment.update(CLAUDE_PLUGIN_ROOT=str(ROOT), CLAUDE_PLUGIN_DATA=str(data))
            result = subprocess.run(["/bin/sh", "-c", command], env=environment,
                                    text=True, capture_output=True, check=True)
            self.assertTrue(result.stdout.startswith("Your score over time\n"))
            self.assertNotIn("(=^.^=)", result.stdout)
            self.assertIn("Now: 575 / 850", result.stdout)

    def test_parse_time_accepts_legacy_naive_dates_as_utc(self):
        self.assertEqual(parse_time("2026-10-01T00:00:00"), parse_time("2026-10-01T00:00:00Z"))
        for value in (None, 1, {}, "", "not-a-date"):
            self.assertIsNone(parse_time(value))


if __name__ == "__main__":
    unittest.main()
