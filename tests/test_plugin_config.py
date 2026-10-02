from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PluginConfigTest(unittest.TestCase):
    def test_marketplace_installs_the_root_plugin(self) -> None:
        marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        entry, = marketplace["plugins"]
        self.assertEqual(marketplace["name"], "ai-social-credit-score")
        self.assertEqual(entry["name"], plugin["name"])
        self.assertEqual((ROOT / entry["source"]).resolve(), ROOT)
        self.assertNotIn("version", entry)  # Keep one source of truth for releases.

    def test_no_identity_hooks_or_commands(self) -> None:
        configuration = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        self.assertEqual(set(configuration["hooks"]), {"UserPromptSubmit"})
        self.assertEqual(
            {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")},
            {"score", "explain", "suggestions", "chart", "statusline"},
        )
        self.assertFalse((ROOT / "scripts/identity.py").exists())

    def test_prompt_processing_hook_is_asynchronous(self) -> None:
        configuration = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        handler = configuration["hooks"]["UserPromptSubmit"][0]["hooks"][0]

        self.assertEqual(handler["type"], "command")
        self.assertTrue(handler["async"])
        self.assertIn("capture_prompt.py", handler["command"])


if __name__ == "__main__":
    unittest.main()
