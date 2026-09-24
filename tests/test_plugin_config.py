from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginConfigTest(unittest.TestCase):
    def test_session_start_initializes_identity(self) -> None:
        configuration = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        handler = configuration["hooks"]["SessionStart"][0]["hooks"][0]

        self.assertEqual(handler["type"], "command")
        self.assertIn("identity.py init", handler["command"])

    def test_prompt_processing_hook_is_asynchronous(self) -> None:
        configuration = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        handler = configuration["hooks"]["UserPromptSubmit"][0]["hooks"][0]

        self.assertEqual(handler["type"], "command")
        self.assertTrue(handler["async"])
        self.assertIn("capture_prompt.py", handler["command"])


if __name__ == "__main__":
    unittest.main()
