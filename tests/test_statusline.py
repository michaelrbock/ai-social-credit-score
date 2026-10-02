from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import capture_prompt
from capture_prompt import append_record
from report import build_report
from setup_statusline import configure
from statusline import read_summary, render_score
from statusline_state import aggregate, summary_path, update_status


def score(key, value):
    return {"event": "prompt_score", "prompt_id": key, "overall_niceness": value}


class StatuslineTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data with spaces"
        self.data.mkdir()
        self.config = self.root / "claude config"
        self.environment = {"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": str(self.data)}

    def add_score(self, key, value):
        append_record(self.data / "scores.jsonl", score(key, value))

    def read_settings(self):
        return json.loads((self.config / "settings.json").read_text())

    def write_settings(self, settings):
        self.config.mkdir(exist_ok=True)
        (self.config / "settings.json").write_text(json.dumps(settings))

    def run_renderer(self, *, input_text="{}"):
        return subprocess.run(self.read_settings()["statusLine"]["command"], shell=True,
                              input=input_text, text=True, capture_output=True, check=True,
                              env=dict(os.environ, NO_COLOR="1"), timeout=5).stdout

    def test_exact_deltas_follow_append_order_including_replacements(self):
        self.add_score("a", 0)
        state = update_status(self.environment)
        self.assertEqual((state["overall_score"], state["last_delta"]), (300, None))
        self.add_score("b", 100)
        state = update_status(self.environment)
        self.assertEqual((state["overall_score"], state["last_delta"]), (575, 275))
        self.add_score("a", 80)
        self.add_score("a", True)
        state = update_status(self.environment)
        self.assertEqual((state["overall_score"], state["last_delta"]), (795, 220))
        self.assertEqual(state["scored_prompt_count"], 2)
        self.assertEqual(state["skipped_record_count"], 1)
        self.assertEqual(state["overall_score"], build_report(self.environment)["overall_score"])
        self.add_score("c", 0)
        state = update_status(self.environment)
        self.assertEqual(state["last_delta"], -165)

    def test_refresh_does_not_reset_last_delta_and_partial_records_are_skipped(self):
        self.add_score("a", 50)
        self.add_score("b", 51)
        self.assertEqual(update_status(self.environment)["last_delta"], 3)
        with (self.data / "scores.jsonl").open("a") as target:
            target.write('\n{"incomplete":')
        state = update_status(self.environment)
        self.assertEqual(state["last_delta"], 3)
        self.assertEqual(state["skipped_record_count"], 1)

    def test_pending_success_failure_and_expired_jobs(self):
        update_status(self.environment, event="start", job_id="a", now=100)
        state = update_status(self.environment, event="start", job_id="b", now=101)
        self.assertEqual(len(state["pending"]), 2)
        self.assertIn("scoring... (2)", render_score(state, now=102))
        self.add_score("one", 70)
        state = update_status(self.environment, event="success", job_id="a", now=103)
        self.assertEqual(set(state["pending"]), {"b"})
        self.assertIn("AI Score: 685", render_score(state, now=103))
        state = update_status(self.environment, event="failure", job_id="b", now=104)
        self.assertEqual(state["pending"], {})
        self.assertIn("last score failed", render_score(state, now=104))
        state = update_status(self.environment, event="start", job_id="crashed", now=105)
        self.assertIn("timed out", render_score(state, now=300))
        state = update_status(self.environment, event="start", job_id="new", now=301)
        self.assertEqual(set(state["pending"]), {"new"})

    def test_concurrent_completions_keep_all_scores_and_clear_pending_jobs(self):
        def work(index):
            update_status(self.environment, event="start", job_id=str(index))
            self.add_score(str(index), index * 3)
            update_status(self.environment, event="success", job_id=str(index))
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(work, range(25)))
        state = json.loads(summary_path(self.environment).read_text())
        self.assertEqual(state["pending"], {})
        self.assertEqual(state["scored_prompt_count"], 25)
        self.assertEqual(state["overall_score"], build_report(self.environment)["overall_score"])
        self.assertEqual(state["last_delta"], aggregate(self.data / "scores.jsonl")["last_delta"])

    def test_summary_avoids_private_fields_and_uses_private_permissions(self):
        (self.data / "prompts.jsonl").write_bytes(b"PRIVATE_PROMPT\xff")
        record = score("PRIVATE_ID", 50)
        record.update(prompt="PRIVATE_PROMPT", rationale="PRIVATE_RATIONALE",
                      cwd="PRIVATE_PATH", session_id="PRIVATE_SESSION")
        append_record(self.data / "scores.jsonl", record)
        before = (self.data / "scores.jsonl").read_bytes()
        update_status(self.environment)
        content = summary_path(self.environment).read_text()
        self.assertNotIn("PRIVATE_", content)
        self.assertEqual((self.data / "scores.jsonl").read_bytes(), before)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(summary_path(self.environment).stat().st_mode), 0o600)

    def test_overridden_score_file_has_separate_summary(self):
        alternate = self.data / "other.jsonl"
        append_record(alternate, score("a", 100))
        env = dict(self.environment, AI_SOCIAL_CREDIT_SCORE_SCORES_FILE=str(alternate))
        self.assertEqual(update_status(env)["overall_score"], 850)
        self.assertEqual(summary_path(env), self.data / "other.jsonl.status.json")
        self.assertFalse(summary_path(self.environment).exists())

    def test_corrupt_summary_is_rebuilt_and_renderer_handles_unavailable_state(self):
        path = summary_path(self.environment)
        path.write_text("broken")
        self.assertEqual(read_summary(path, color=False), "AI Score: unavailable")
        self.add_score("a", 70)
        update_status(self.environment)
        self.assertEqual(read_summary(path, color=False), "AI Score: 685")
        self.assertEqual(read_summary(self.data / "missing", color=False), "AI Score: unavailable")

    def test_colors_first_score_empty_and_untrusted_values(self):
        self.assertEqual(render_score({}), "AI Score: -- | no scores yet")
        state = {"overall_score": 700, "last_delta": 3}
        self.assertEqual(render_score(state), "AI Score: 700 (+3 last)")
        self.assertIn("\x1b[32m", render_score(state, color=True))
        state["last_delta"] = -2
        self.assertIn("\x1b[31m", render_score(state, color=True))
        state["last_delta"] = 0
        self.assertNotIn("\x1b", render_score(state, color=True))
        self.assertEqual(render_score({"overall_score": "\x1b[2J"}), "AI Score: unavailable")

    def test_setup_is_idempotent_preserves_stdin_output_and_restores_settings(self):
        previous = {"type": "command", "padding": 2,
                    "command": shlex.join([sys.executable, "-c", "import json,sys; print(json.load(sys.stdin)['marker'])"])}
        original = {"statusLine": previous, "model": "existing-model", "permissions": {"allow": ["Read"]}}
        self.write_settings(original)
        self.add_score("a", 50)
        self.add_score("b", 60)
        configure("enable", self.config, self.environment)
        installed = self.read_settings()
        self.assertEqual(installed["statusLine"]["refreshInterval"], 1)
        self.assertEqual(installed["statusLine"]["padding"], 2)
        configure("enable", self.config, self.environment)
        self.assertEqual(self.read_settings(), installed)
        self.assertEqual(self.run_renderer(input_text='{"marker":"ORIGINAL STATUS"}'),
                         "ORIGINAL STATUS\nAI Score: 603 (+28 last)\n")
        installed["model"] = "later-model"
        self.write_settings(installed)
        configure("disable", self.config, self.environment)
        original["model"] = "later-model"
        self.assertEqual(self.read_settings(), original)

    def test_new_setup_bootstraps_existing_history_and_removes_only_its_setting(self):
        self.add_score("a", 100)
        before = (self.data / "scores.jsonl").read_bytes()
        configure("enable", self.config, self.environment)
        self.assertEqual(self.run_renderer(), "AI Score: 850\n")
        self.assertEqual((self.data / "scores.jsonl").read_bytes(), before)
        configure("disable", self.config, self.environment)
        self.assertEqual(self.read_settings(), {})
        self.assertIn("already disabled", configure("disable", self.config, self.environment))

    def test_status_does_not_create_any_files(self):
        self.assertIn("not enabled", configure("status", self.config, self.environment))
        self.assertFalse(self.config.exists())
        self.assertEqual(list(self.data.iterdir()), [])

    def test_manually_changed_statusline_is_never_overwritten(self):
        configure("enable", self.config, self.environment)
        newer = {"statusLine": {"type": "command", "command": "printf newer"}, "theme": "custom"}
        self.write_settings(newer)
        with self.assertRaisesRegex(ValueError, "changed since setup"):
            configure("enable", self.config, self.environment)
        self.assertEqual(self.read_settings(), newer)
        configure("disable", self.config, self.environment)
        self.assertEqual(self.read_settings(), newer)
        configure("enable", self.config, self.environment)
        self.assertTrue(self.run_renderer().startswith("newer\nAI Score:"))

    def test_invalid_settings_and_symlinks_are_left_untouched(self):
        self.config.mkdir()
        path = self.config / "settings.json"
        path.write_bytes(b"not-json")
        with self.assertRaises(ValueError):
            configure("enable", self.config, self.environment)
        self.assertEqual(path.read_bytes(), b"not-json")
        path.unlink()
        target = self.root / "linked-settings.json"
        target.write_text("{}")
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            configure("enable", self.config, self.environment)
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(), "{}")

    def test_settings_changed_during_setup_are_preserved(self):
        self.write_settings({"model": "before"})
        from setup_statusline import atomic_write as real_write
        def simulate_editor(path, content):
            real_write(path, content)
            self.write_settings({"model": "edited"})
        with patch("setup_statusline.atomic_write", side_effect=simulate_editor):
            with self.assertRaisesRegex(ValueError, "changed during setup"):
                configure("enable", self.config, self.environment)
        self.assertEqual(self.read_settings(), {"model": "edited"})
        # A retry recovers the saved backup without nesting the renderer.
        configure("enable", self.config, self.environment)
        self.assertEqual(self.read_settings()["model"], "edited")

    def test_stable_renderer_survives_retiring_the_plugin_cache(self):
        cache = self.root / "old-plugin-cache"
        shutil.copytree(ROOT / "scripts", cache, ignore=shutil.ignore_patterns("__pycache__"))
        self.add_score("a", 50)
        subprocess.run([sys.executable, str(cache / "setup_statusline.py"), "enable",
                        "--config-dir", str(self.config), "--data-dir", str(self.data)], check=True,
                       capture_output=True, text=True)
        cache.rename(self.root / "retired-plugin-cache")
        self.assertNotIn("plugin-cache", self.read_settings()["statusLine"]["command"])
        self.assertEqual(self.run_renderer(), "AI Score: 575\n")
        configure("enable", self.config, self.environment)  # Refresh from current version.
        self.assertEqual(self.run_renderer(), "AI Score: 575\n")

    def test_slow_previous_command_does_not_hide_score(self):
        self.write_settings({"statusLine": {"type": "command", "command": shlex.join(
            [sys.executable, "-c", "import time; time.sleep(30)"] )}})
        configure("enable", self.config, self.environment)
        self.assertEqual(self.run_renderer(), "AI Score: -- | no scores yet\n")

    def test_hook_exposes_pending_then_completed_without_waiting_for_renderer(self):
        env = dict(self.environment, AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED="1")
        observed = []
        def fake_score(*args):
            state = json.loads(summary_path(env).read_text())
            observed.append(render_score(state))
            return score(args[1], 80)
        with patch.dict(os.environ, env, clear=True), patch("sys.stdin", io.StringIO(json.dumps({
            "hook_event_name": "UserPromptSubmit", "prompt": "private prompt",
        }))), patch("capture_prompt.score_prompt", side_effect=fake_score):
            self.assertEqual(capture_prompt.main(), 0)
        self.assertIn("scoring...", observed[0])
        self.assertEqual(read_summary(summary_path(env), color=False), "AI Score: 740")

    def test_cache_failures_never_turn_successful_scoring_into_an_error(self):
        env = dict(self.environment, AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED="1")
        with patch.dict(os.environ, env, clear=True), patch("sys.stdin", io.StringIO(json.dumps({
            "hook_event_name": "UserPromptSubmit", "prompt": "test",
        }))), patch("capture_prompt.score_prompt", return_value=score("a", 60)), \
                patch("capture_prompt.update_status", side_effect=OSError("disk unavailable")):
            self.assertEqual(capture_prompt.main(), 0)
        self.assertTrue((self.data / "scores.jsonl").exists())
        self.assertFalse((self.data / "score_errors.jsonl").exists())

    def test_failed_scoring_clears_pending(self):
        env = dict(self.environment, AI_SOCIAL_CREDIT_SCORE_SCORING_ENABLED="1")
        with patch.dict(os.environ, env, clear=True), patch("sys.stdin", io.StringIO(json.dumps({
            "hook_event_name": "UserPromptSubmit", "prompt": "test",
        }))), patch("capture_prompt.score_prompt", side_effect=ValueError("test error")):
            self.assertEqual(capture_prompt.main(), 0)
        state = json.loads(summary_path(env).read_text())
        self.assertEqual(state["pending"], {})
        self.assertTrue(state["last_error"])
        self.assertIn("last score failed", render_score(state))

    def test_skill_commands_respect_config_and_plugin_data_directories(self):
        skill = (ROOT / "skills/statusline/SKILL.md").read_text()
        self.assertIn("disable-model-invocation: true", skill)
        commands = re.findall(r"```sh\n(.*?)\n```", skill, re.DOTALL)
        self.assertEqual(len(commands), 3)
        self.assertTrue(all("$ARGUMENTS" not in command for command in commands))
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("AI_SOCIAL_CREDIT_SCORE_")}
        environment.update(CLAUDE_CONFIG_DIR=str(self.config), CLAUDE_PLUGIN_ROOT=str(ROOT),
                           CLAUDE_PLUGIN_DATA=str(self.data))
        for command in commands:
            subprocess.run(command, shell=True, env=environment, text=True,
                           capture_output=True, check=True)
        self.assertEqual(self.read_settings(), {})
        self.assertTrue(summary_path(self.environment).exists())

    def test_hook_subprocess_updates_the_installed_renderer(self):
        self.add_score("existing", 50)
        configure("enable", self.config, self.environment)
        self.assertEqual(self.run_renderer(), "AI Score: 575\n")
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("AI_SOCIAL_CREDIT_SCORE_")}
        environment.update(self.environment)
        environment["AI_SOCIAL_CREDIT_SCORE_CLAUDE_EXECUTABLE"] = str(ROOT / "tests/fixtures/fake_claude.py")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/capture_prompt.py")],
                                env=environment, input=json.dumps({
                                    "hook_event_name": "UserPromptSubmit", "prompt": "test prompt",
                                }), text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.run_renderer(), "AI Score: 625 (+50 last)\n")


if __name__ == "__main__":
    unittest.main()
