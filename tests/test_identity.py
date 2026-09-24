from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "identity.py"
USERNAME_PATTERN = re.compile(r"^[A-Za-z]+[0-9]{3}$")


class IdentityTest(unittest.TestCase):
    def run_command(
        self, action: str, data_dir: Path, *, disabled: bool = False
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.pop("AI_SOCIAL_CREDIT_SCORE_LOG_FILE", None)
        environment.pop("AI_SOCIAL_CREDIT_SCORE_DATA_DIR", None)
        environment.pop("CLAUDE_PLUGIN_DATA", None)
        environment["AI_SOCIAL_CREDIT_SCORE_DISABLED"] = "1" if disabled else "0"
        return subprocess.run(
            [sys.executable, str(SCRIPT), action, "--plugin-data-dir", str(data_dir)],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

    def test_init_creates_private_stable_identity_without_prompt_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory) / "nested" / "plugin-data"
            first = self.run_command("init", data_dir)
            self.assertEqual(first.returncode, 0)
            self.assertEqual(first.stdout, "")
            self.assertEqual(first.stderr, "")

            path = data_dir / "identity.json"
            identity = json.loads(path.read_text())
            self.assertEqual(identity["schema_version"], 1)
            uuid.UUID(identity["installation_id"])
            self.assertRegex(identity["username"], USERNAME_PATTERN)
            self.assertNotIn("prompt", identity)
            self.assertFalse((data_dir / "prompts.jsonl").exists())
            self.assertEqual(self.run_command("show", data_dir).stdout.strip(), identity["username"])
            self.assertEqual(json.loads(path.read_text()), identity)

            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(data_dir.stat().st_mode), 0o700)

    def test_reroll_changes_only_public_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            self.run_command("init", data_dir)
            before = json.loads((data_dir / "identity.json").read_text())

            result = self.run_command("reroll", data_dir)
            after = json.loads((data_dir / "identity.json").read_text())

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), after["username"])
            self.assertRegex(after["username"], USERNAME_PATTERN)
            self.assertNotEqual(after["username"], before["username"])
            self.assertEqual(after["installation_id"], before["installation_id"])
            self.assertEqual(after["created_at"], before["created_at"])
            self.assertIn("username_updated_at", after)

    def test_old_username_is_migrated_once_without_changing_private_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            path = data_dir / "identity.json"
            original = {
                "schema_version": 1,
                "installation_id": str(uuid.uuid4()),
                "username": "CuriousCapybara-4H7K2P",
                "created_at": "2026-09-22T12:00:00Z",
            }
            path.write_text(json.dumps(original))

            first = self.run_command("show", data_dir)
            migrated = json.loads(path.read_text())
            second = self.run_command("show", data_dir)

            self.assertEqual(first.returncode, 0)
            self.assertRegex(first.stdout.strip(), r"^CuriousCapybara[0-9]{3}$")
            self.assertEqual(second.stdout, first.stdout)
            self.assertEqual(json.loads(path.read_text()), migrated)
            self.assertEqual(migrated["installation_id"], original["installation_id"])
            self.assertEqual(migrated["created_at"], original["created_at"])
            self.assertIn("username_updated_at", migrated)

    def test_concurrent_init_uses_one_complete_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory) / "plugin-data"
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(lambda _: self.run_command("init", data_dir), range(12)))

            self.assertTrue(all(result.returncode == 0 for result in results))
            self.assertTrue(all(result.stderr == "" for result in results))
            identity = json.loads((data_dir / "identity.json").read_text())
            self.assertRegex(identity["username"], USERNAME_PATTERN)
            self.assertEqual(len(list(data_dir.glob(".identity-*"))), 0)

    def test_disabled_hook_does_not_create_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory) / "plugin-data"
            result = self.run_command("init", data_dir, disabled=True)

            self.assertEqual(result.returncode, 0)
            self.assertFalse(data_dir.exists())

    def test_corrupt_identity_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data_dir = Path(temporary_directory)
            path = data_dir / "identity.json"
            path.write_text("not json")

            result = self.run_command("show", data_dir)

            self.assertEqual(result.returncode, 1)
            self.assertIn("ai-social-credit-score:", result.stderr)
            self.assertEqual(path.read_text(), "not json")


if __name__ == "__main__":
    unittest.main()
