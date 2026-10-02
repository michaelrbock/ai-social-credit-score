from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from paths import log_path


class PathsTest(unittest.TestCase):
    def test_override_precedence_is_preserved(self):
        environment = {
            "AI_SOCIAL_CREDIT_SCORE_LOG_FILE": "/logs/custom.jsonl",
            "AI_SOCIAL_CREDIT_SCORE_DATA_DIR": "/custom-data",
            "CLAUDE_PLUGIN_DATA": "/plugin-data",
        }
        self.assertEqual(log_path(environment), Path("/logs/custom.jsonl"))
        environment.pop("AI_SOCIAL_CREDIT_SCORE_LOG_FILE")
        self.assertEqual(log_path(environment), Path("/custom-data/prompts.jsonl"))
        environment.pop("AI_SOCIAL_CREDIT_SCORE_DATA_DIR")
        self.assertEqual(log_path(environment), Path("/plugin-data/prompts.jsonl"))

    def test_platform_defaults_are_preserved(self):
        with patch("paths.Path.home", return_value=Path("/user-home")):
            for platform, suffix in (
                ("darwin", "Library/Application Support/ai-social-credit-score/prompts.jsonl"),
                ("linux", ".local/share/ai-social-credit-score/prompts.jsonl"),
                ("win32", "AppData/Local/ai-social-credit-score/prompts.jsonl"),
            ):
                with self.subTest(platform=platform):
                    self.assertEqual(log_path({}, platform), Path("/user-home") / suffix)
        self.assertEqual(log_path({"XDG_DATA_HOME": "/xdg"}, "linux"),
                         Path("/xdg/ai-social-credit-score/prompts.jsonl"))
        self.assertEqual(log_path({"LOCALAPPDATA": "/local"}, "win32"),
                         Path("/local/ai-social-credit-score/prompts.jsonl"))

    def test_user_paths_expand_home(self):
        self.assertEqual(log_path({"AI_SOCIAL_CREDIT_SCORE_DATA_DIR": "~/scores"}),
                         Path.home() / "scores/prompts.jsonl")


if __name__ == "__main__":
    unittest.main()
