"""Shared paths for local prompt and score storage."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping


def log_path(environment: Mapping[str, str], platform: str = sys.platform) -> Path:
    """Resolve the prompt log without changing existing storage locations."""

    configured_file = environment.get("AI_SOCIAL_CREDIT_SCORE_LOG_FILE")
    if configured_file:
        return Path(configured_file).expanduser()

    configured_directory = environment.get("AI_SOCIAL_CREDIT_SCORE_DATA_DIR")
    if configured_directory:
        return Path(configured_directory).expanduser() / "prompts.jsonl"

    plugin_data_directory = environment.get("CLAUDE_PLUGIN_DATA")
    if plugin_data_directory:
        return Path(plugin_data_directory).expanduser() / "prompts.jsonl"

    home = Path.home()
    if platform == "darwin":
        data_directory = home / "Library" / "Application Support" / "ai-social-credit-score"
    elif platform == "win32":
        local_app_data = environment.get("LOCALAPPDATA")
        data_directory = (
            Path(local_app_data).expanduser()
            if local_app_data
            else home / "AppData" / "Local"
        ) / "ai-social-credit-score"
    else:
        xdg_data_home = environment.get("XDG_DATA_HOME")
        data_directory = (
            Path(xdg_data_home).expanduser()
            if xdg_data_home
            else home / ".local" / "share"
        ) / "ai-social-credit-score"

    return data_directory / "prompts.jsonl"
