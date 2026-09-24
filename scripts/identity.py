#!/usr/bin/env python3
"""Create and manage a local, pseudonymous plugin identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


SCHEMA_VERSION = 1
TRUTHY_VALUES = {"1", "true", "yes", "on"}
ADJECTIVES = (
    "Bouncy", "Brave", "Bright", "Cheerful", "Clever", "Cosmic",
    "Curious", "Dapper", "Daring", "Dreamy", "Gentle", "Jolly",
    "Lively", "Mellow", "Merry", "Nimble", "Playful", "Quirky",
    "Sunny", "Whimsical",
)
ANIMALS = (
    "Badger", "Capybara", "Dingo", "Dolphin", "Ferret", "Fox",
    "Giraffe", "Hedgehog", "Koala", "Lemur", "Narwhal", "Otter",
    "Panda", "Penguin", "Puffin", "Quokka", "Raccoon", "Seal",
    "Sloth", "Wombat",
)
USERNAME_PATTERN = re.compile(r"^[A-Za-z]+[0-9]{3}$")
LEGACY_USERNAME_PATTERN = re.compile(r"^(?P<name>[A-Za-z]+)-[A-Z2-9]{6}$")


def log_path(environment: Mapping[str, str], platform: str = sys.platform) -> Path:
    """Resolve data the same way as prompt capture, including user overrides."""

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


def identity_path(environment: Mapping[str, str], platform: str = sys.platform) -> Path:
    return log_path(environment, platform).with_name("identity.json")


def new_username() -> str:
    return f"{secrets.choice(ADJECTIVES)}{secrets.choice(ANIMALS)}{secrets.randbelow(1000):03d}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_identity(path: Path) -> dict[str, str | int]:
    with path.open(encoding="utf-8") as file:
        identity = json.load(file)
    if not isinstance(identity, dict) or identity.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Invalid identity file: {path}")
    if not isinstance(identity.get("username"), str) or not (
        USERNAME_PATTERN.fullmatch(identity["username"])
        or LEGACY_USERNAME_PATTERN.fullmatch(identity["username"])
    ):
        raise ValueError(f"Invalid username in identity file: {path}")
    if not isinstance(identity.get("installation_id"), str):
        raise ValueError(f"Invalid installation ID in identity file: {path}")
    try:
        uuid.UUID(identity["installation_id"])
    except ValueError as error:
        raise ValueError(f"Invalid installation ID in identity file: {path}") from error
    return identity


def prepare_parent(path: Path) -> None:
    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed and os.name != "nt":
        path.parent.chmod(0o700)


def write_prepared_temp(path: Path, identity: Mapping[str, str | int]) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".identity-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(identity, file, ensure_ascii=False, separators=(",", ":"))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        return temporary_path
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def replace_identity(path: Path, identity: Mapping[str, str | int]) -> None:
    temporary_path = write_prepared_temp(path, identity)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def migrate_legacy_identity(path: Path, identity: dict[str, str | int]) -> dict[str, str | int]:
    """Keep the cute name and private ID while changing the old suffix format."""

    old_username = str(identity["username"])
    match = LEGACY_USERNAME_PATTERN.fullmatch(old_username)
    if match is None:
        return identity

    digest = hashlib.sha256(
        f"{identity['installation_id']}:{old_username}".encode("utf-8")
    ).digest()
    number = int.from_bytes(digest[:8], "big") % 1000
    updated = dict(identity)
    updated["username"] = f"{match.group('name')}{number:03d}"
    updated["username_updated_at"] = utc_now()
    replace_identity(path, updated)
    return updated


def ensure_identity(path: Path) -> dict[str, str | int]:
    """Publish a complete identity exactly once, even across concurrent sessions."""

    try:
        identity = read_identity(path)
    except FileNotFoundError:
        pass
    else:
        return migrate_legacy_identity(path, identity)

    prepare_parent(path)
    identity: dict[str, str | int] = {
        "schema_version": SCHEMA_VERSION,
        "installation_id": str(uuid.uuid4()),
        "username": new_username(),
        "created_at": utc_now(),
    }
    temporary_path = write_prepared_temp(path, identity)
    try:
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            return migrate_legacy_identity(path, read_identity(path))
        return identity
    finally:
        temporary_path.unlink(missing_ok=True)


def reroll_identity(path: Path) -> dict[str, str | int]:
    """Change only the public handle, preserving the stable internal ID."""

    identity = ensure_identity(path)
    previous = identity["username"]
    while True:
        username = new_username()
        if username != previous:
            break
    updated = dict(identity)
    updated["username"] = username
    updated["username_updated_at"] = utc_now()
    replace_identity(path, updated)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage your local anonymous username")
    parser.add_argument("action", choices=("init", "show", "reroll"))
    parser.add_argument("--plugin-data-dir", help="Claude Code's persistent plugin data directory")
    arguments = parser.parse_args()
    action = arguments.action

    environment = dict(os.environ)
    if arguments.plugin_data_dir:
        environment["CLAUDE_PLUGIN_DATA"] = arguments.plugin_data_dir
    if action == "init" and (
        environment.get("AI_SOCIAL_CREDIT_SCORE_DISABLED", "").lower() in TRUTHY_VALUES
        or environment.get("AI_SOCIAL_CREDIT_SCORE_SCORER_CHILD", "").lower() in TRUTHY_VALUES
    ):
        return 0

    try:
        path = identity_path(environment)
        is_new_install = not path.exists()
        identity = reroll_identity(path) if action == "reroll" else ensure_identity(path)
        if action == "init":
            from publication import initialize_publication, publication_path

            initialize_publication(publication_path(path), new_install=is_new_install)
        else:
            print(identity["username"])
    except Exception as error:
        if action == "init":
            if environment.get("AI_SOCIAL_CREDIT_SCORE_DEBUG", "").lower() in TRUTHY_VALUES:
                print(f"ai-social-credit-score: {error}", file=sys.stderr)
            return 0  # Identity setup must never block a Claude Code session.
        print(f"ai-social-credit-score: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
