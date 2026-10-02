#!/usr/bin/env python3
"""Enable, inspect, or disable the optional score status line."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import sys

from statusline_state import atomic_json, atomic_write, file_lock, summary_path, update_status


def read_object(path: Path) -> tuple[dict, bytes | None]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}, None
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"Invalid JSON in {path}; left untouched") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}; left untouched")
    return value, raw


def settings_unchanged(path: Path, original: bytes | None) -> None:
    current = path.read_bytes() if path.exists() else None
    if current != original:
        raise ValueError("Settings changed during setup; retry to preserve the newer edits")


def configure(action: str, config_root: Path, environment: dict) -> str:
    config_root = config_root.expanduser().resolve()
    settings_file = config_root / "settings.json"
    install_dir = config_root / "ai-social-credit-score"
    renderer = install_dir / "statusline.py"
    backup_file = renderer.with_suffix(".json")
    if action == "status":
        settings, _ = read_object(settings_file)
        saved, _ = read_object(backup_file)
        active = saved.get("enabled") and settings.get("statusLine") == saved.get("managed")
        return "Score status line is enabled." if active else "Score status line is not enabled."
    # Avoid replacing a user-managed symlink with a regular file.
    for path in (settings_file, renderer, backup_file):
        if path.is_symlink():
            raise ValueError(f"Refusing to replace symlink {path}; left untouched")
    with file_lock(install_dir / "setup.lock"):
        settings, original = read_object(settings_file)
        saved, _ = read_object(backup_file)
        current = settings.get("statusLine")
        if action == "disable":
            if not saved.get("enabled"):
                return "Score status line is already disabled."
            restored = current == saved.get("managed")
            if restored:
                if saved.get("previous_present"):
                    settings["statusLine"] = saved.get("previous")
                else:
                    settings.pop("statusLine", None)
                settings_unchanged(settings_file, original)
                atomic_json(settings_file, settings)
            saved["enabled"] = False
            atomic_json(backup_file, saved)
            return ("Score status line disabled; previous status line restored." if restored else
                    "Score status line disabled; your newer status-line setting was left untouched.")
        if action != "enable":
            raise ValueError("Unknown setup action")
        if saved.get("enabled"):
            # Also recover an interrupted setup that saved the backup before settings.
            previous_matches = (current == saved.get("previous")
                                and ("statusLine" in settings) == saved.get("previous_present"))
            if current != saved.get("managed") and not previous_matches:
                raise ValueError("Your status line changed since setup. Run disable, then enable to use the new one.")
            previous = saved.get("previous")
            previous_present = saved.get("previous_present", False)
        else:
            previous, previous_present = current, "statusLine" in settings
        if previous is not None and (not isinstance(previous, dict)
                                     or previous.get("type") != "command"
                                     or not isinstance(previous.get("command"), str)):
            raise ValueError("Existing status line is not a supported command; left untouched")
        if previous and str(renderer) in previous["command"]:
            raise ValueError("Existing command points to this renderer without a usable backup; left untouched")
        # These files do not live in Claude's versioned plugin cache, so upgrading
        # or removing an older cache directory cannot break the configured command.
        managed = dict(previous or {})
        managed.update(type="command", command=shlex.join([sys.executable, str(renderer)]), refreshInterval=1)
        update_status(environment)
        atomic_write(renderer, Path(__file__).with_name("statusline.py").read_bytes())
        atomic_json(backup_file, {
            "enabled": True, "previous_present": previous_present,
            "previous": previous, "managed": managed,
            "state_file": str(summary_path(environment).resolve()),
        })
        settings_unchanged(settings_file, original)
        settings["statusLine"] = managed
        atomic_json(settings_file, settings)
        return ("Score status line enabled (1-second refresh). Existing status-line output is preserved. "
                "Run disable before uninstalling the plugin.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enable", "disable", "status"), nargs="?", default="enable")
    parser.add_argument("--config-dir", type=Path, help="Claude configuration directory")
    parser.add_argument("--data-dir", help="Directory containing local score logs")
    parser.add_argument("--plugin-data-dir", help="Claude Code's persistent plugin data directory")
    args = parser.parse_args()
    environment = dict(os.environ)
    if args.plugin_data_dir:
        environment["CLAUDE_PLUGIN_DATA"] = args.plugin_data_dir
    if args.data_dir:
        environment.pop("AI_SOCIAL_CREDIT_SCORE_LOG_FILE", None)
        environment.pop("AI_SOCIAL_CREDIT_SCORE_SCORES_FILE", None)
        environment["AI_SOCIAL_CREDIT_SCORE_DATA_DIR"] = args.data_dir
    config_root = args.config_dir or Path(environment.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        print(configure(args.action, config_root, environment))
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Could not configure score status line: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
