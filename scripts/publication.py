#!/usr/bin/env python3
"""Publish only aggregate Claude Code scores to the TransAIUnion leaderboard."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import urlparse

from identity import identity_path, read_identity, reroll_identity
from score_prompt import RUBRIC_VERSION, credit_score_from_total


SCHEMA_VERSION = 1
DEFAULT_UPLOAD_URL = "https://transaiunion.michaelrbock.chatgpt.site/api/score"
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
TRUTHY_VALUES = {"1", "true", "yes", "on"}


class PublicationError(RuntimeError):
    """A safe-to-log publication failure without a prompt or token."""


class UsernameTaken(PublicationError):
    """The requested pseudonym is already reserved by another installation."""


def publication_path(identity_file: Path) -> Path:
    return identity_file.with_name("publication.json")


def _new_state(enabled: bool) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": enabled,
        "pending_delete": False,
        "token": secrets.token_urlsafe(32),
        "last_uploaded_count": 0,
        "next_upload_count": secrets.randbelow(10) + 1,
    }


def _read_state(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        state = json.load(file)
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != SCHEMA_VERSION
        or not isinstance(state.get("enabled"), bool)
        or not isinstance(state.get("pending_delete"), bool)
        or not isinstance(state.get("token"), str)
        or not TOKEN_PATTERN.fullmatch(state["token"])
        or not isinstance(state.get("last_uploaded_count"), int)
        or isinstance(state["last_uploaded_count"], bool)
        or state["last_uploaded_count"] < 0
        or not isinstance(state.get("next_upload_count"), int)
        or isinstance(state["next_upload_count"], bool)
        or state["next_upload_count"] < 1
    ):
        raise PublicationError("The local publication state is invalid")
    return state


def initialize_publication(path: Path, *, new_install: bool) -> dict[str, Any]:
    """Automatically enable only new installations; preserve legacy local-only users."""

    try:
        return _read_state(path)
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)
    state = _new_state(new_install)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return _read_state(path)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(state, file, separators=(",", ":"))
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    return state


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".publication-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(state, file, separators=(",", ":"))
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(".lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name != "nt":
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if os.name != "nt":
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def score_summary(scores_file: Path) -> dict[str, Any] | None:
    """Aggregate the latest valid score for each prompt, including v1 records."""

    try:
        lines = scores_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    scores: dict[str, dict[str, Any]] = {}
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("event") != "prompt_score":
            continue
        prompt_id = record.get("prompt_id")
        niceness = record.get("overall_niceness")
        scored_at = record.get("scored_at")
        if (
            isinstance(prompt_id, str)
            and prompt_id
            and isinstance(niceness, int)
            and not isinstance(niceness, bool)
            and 0 <= niceness <= 100
            and isinstance(scored_at, str)
            and scored_at.endswith("Z")
        ):
            scores[prompt_id] = record
    if not scores:
        return None
    latest = max(record["scored_at"] for record in scores.values())
    total = sum(record["overall_niceness"] for record in scores.values())
    return {
        "score": credit_score_from_total(total, len(scores)),
        "prompt_count": len(scores),
        "score_date": latest,
        "rubric_version": RUBRIC_VERSION,
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: urllib.request.Request, fp: Any,
                         code: int, message: str, headers: Any, newurl: str) -> None:
        return None


def upload_url(environment: Mapping[str, str]) -> str:
    url = environment.get("AI_SOCIAL_CREDIT_SCORE_UPLOAD_URL", DEFAULT_UPLOAD_URL)
    parsed = urlparse(url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise PublicationError("The upload URL must use HTTPS")
    if parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise PublicationError("The upload URL is invalid")
    return url


def _request(
    method: str,
    token: str,
    environment: Mapping[str, str],
    payload: Mapping[str, Any] | None = None,
    *,
    opener: Callable[..., Any] | None = None,
) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload else None
    request = urllib.request.Request(
        upload_url(environment),
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    open_request = opener or urllib.request.build_opener(_NoRedirect()).open
    try:
        with open_request(request, timeout=5) as response:
            if response.status not in ({200, 201} if method == "PUT" else {204}):
                raise PublicationError(f"The leaderboard returned HTTP {response.status}")
    except urllib.error.HTTPError as error:
        if error.code == 409 and b"username_taken" in error.read(256):
            raise UsernameTaken("That username is already in use") from error
        raise PublicationError(f"The leaderboard returned HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise PublicationError("The leaderboard could not be reached") from error


def publish_after_score(
    identity_file: Path,
    scores_file: Path,
    environment: Mapping[str, str],
    *,
    opener: Callable[..., Any] | None = None,
) -> bool:
    """Publish on a random 1–10-new-score cadence without sending prompts."""

    state_file = publication_path(identity_file)
    with _locked(state_file):
        state = _read_state(state_file)
        if state["pending_delete"]:
            _request("DELETE", state["token"], environment, opener=opener)
            state.update(pending_delete=False, token=secrets.token_urlsafe(32))
            _write_state(state_file, state)
            return False
        if not state["enabled"] or environment.get(
            "AI_SOCIAL_CREDIT_SCORE_PUBLISH_DISABLED", ""
        ).lower() in TRUTHY_VALUES:
            return False
        summary = score_summary(scores_file)
        if summary is None or summary["prompt_count"] < state["next_upload_count"]:
            return False
        for attempt in range(10):
            username = read_identity(identity_file)["username"]
            payload = {"username": username, **summary}
            try:
                _request("PUT", state["token"], environment, payload, opener=opener)
                break
            except UsernameTaken:
                if attempt == 9:
                    raise PublicationError("Could not find an available username") from None
                reroll_identity(identity_file)
        state["last_uploaded_count"] = summary["prompt_count"]
        state["next_upload_count"] = summary["prompt_count"] + secrets.randbelow(10) + 1
        _write_state(state_file, state)
        return True


def scores_path(identity_file: Path, environment: Mapping[str, str]) -> Path:
    configured = environment.get("AI_SOCIAL_CREDIT_SCORE_SCORES_FILE")
    return Path(configured).expanduser() if configured else identity_file.with_name("scores.jsonl")


def unpublish(identity_file: Path, environment: Mapping[str, str],
              *, opener: Callable[..., Any] | None = None) -> None:
    state_file = publication_path(identity_file)
    initialize_publication(state_file, new_install=False)
    with _locked(state_file):
        state = _read_state(state_file)
        state.update(enabled=False, pending_delete=True)
        _write_state(state_file, state)
        _request("DELETE", state["token"], environment, opener=opener)
        state.update(pending_delete=False, token=secrets.token_urlsafe(32))
        _write_state(state_file, state)


def enable(identity_file: Path, environment: Mapping[str, str]) -> None:
    state_file = publication_path(identity_file)
    initialize_publication(state_file, new_install=False)
    with _locked(state_file):
        state = _read_state(state_file)
        if state["pending_delete"]:
            raise PublicationError("Finish unpublishing before enabling again")
        summary = score_summary(scores_path(identity_file, environment))
        current_count = summary["prompt_count"] if summary else 0
        state["enabled"] = True
        state["next_upload_count"] = current_count + secrets.randbelow(10) + 1
        _write_state(state_file, state)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage TransAIUnion score publishing")
    parser.add_argument("action", choices=("status", "enable", "unpublish"))
    parser.add_argument("--plugin-data-dir")
    arguments = parser.parse_args()
    environment = dict(os.environ)
    if arguments.plugin_data_dir:
        environment["CLAUDE_PLUGIN_DATA"] = arguments.plugin_data_dir
    identity_file = identity_path(environment)
    try:
        if arguments.action == "enable":
            enable(identity_file, environment)
            print("Score publishing enabled. The next upload follows 1–10 new scores.")
        elif arguments.action == "unpublish":
            unpublish(identity_file, environment)
            print("Publishing stopped; your leaderboard record and history were deleted.")
        else:
            state = initialize_publication(publication_path(identity_file), new_install=False)
            status = "deletion pending" if state["pending_delete"] else (
                "enabled" if state["enabled"] else "disabled"
            )
            print(f"Publishing: {status}")
    except Exception as error:
        print(f"ai-social-credit-score: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
