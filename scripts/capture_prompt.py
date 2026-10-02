#!/usr/bin/env python3
"""Persist Claude Code UserPromptSubmit events as local JSON Lines."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from paths import log_path
from score_prompt import BACKEND, SCORER_CHILD_VARIABLE, score_prompt, scoring_enabled
from statusline_state import update_status


SCHEMA_VERSION = 1
TRUTHY_VALUES = {"1", "true", "yes", "on"}


def is_disabled(environment: Mapping[str, str]) -> bool:
    """Return whether prompt capture has been explicitly disabled."""

    return (
        environment.get("AI_SOCIAL_CREDIT_SCORE_DISABLED", "").lower()
        in TRUTHY_VALUES
    )


def is_scorer_child(environment: Mapping[str, str]) -> bool:
    """Prevent a scorer subprocess from recursively invoking this hook."""

    return environment.get(SCORER_CHILD_VARIABLE, "").lower() in TRUTHY_VALUES


def capture_record(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Convert a valid UserPromptSubmit payload into the stored schema."""

    if event.get("hook_event_name") != "UserPromptSubmit":
        return None

    prompt = event.get("prompt")
    if not isinstance(prompt, str):
        return None

    event_prompt_id = event.get("prompt_id")
    prompt_id = (
        event_prompt_id.strip()
        if isinstance(event_prompt_id, str) and event_prompt_id.strip()
        else str(uuid.uuid4())
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "prompt_id": prompt_id,
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "user_prompt",
        "session_id": event.get("session_id"),
        "cwd": event.get("cwd"),
        "prompt": prompt,
    }


def related_log_path(
    prompt_log_path: Path,
    environment: Mapping[str, str],
    variable: str,
    filename: str,
) -> Path:
    configured_file = environment.get(variable)
    return (
        Path(configured_file).expanduser()
        if configured_file
        else prompt_log_path.with_name(filename)
    )


def scoring_error_record(
    record: Mapping[str, Any],
    error: Exception,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "failed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "prompt_score_error",
        "prompt_id": record["prompt_id"],
        "session_id": record.get("session_id"),
        "backend": BACKEND,
        "error_type": type(error).__name__,
        "message": str(error),
    }


def append_record(path: Path, record: Mapping[str, Any]) -> None:
    """Append one private JSONL record, locking where the platform supports it."""

    parent_existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not parent_existed and os.name != "nt":
        path.parent.chmod(0o700)

    payload = (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)

    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)

        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
    finally:
        os.close(descriptor)


def debug(message: str, environment: Mapping[str, str]) -> None:
    """Keep hooks silent unless the user explicitly asks for diagnostics."""

    if (
        environment.get("AI_SOCIAL_CREDIT_SCORE_DEBUG", "").lower()
        in TRUTHY_VALUES
    ):
        print(f"ai-social-credit-score: {message}", file=sys.stderr)


def main() -> int:
    """Read one hook event from stdin without ever blocking the user's prompt."""

    environment = os.environ
    if is_disabled(environment) or is_scorer_child(environment):
        return 0

    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0

        record = capture_record(event)
        if record is not None:
            prompt_log_path = log_path(environment)
            append_record(prompt_log_path, record)
            if scoring_enabled(environment):
                job_id = str(uuid.uuid4())
                status_event = "failure"
                try:
                    update_status(environment, event="start", job_id=job_id)
                except Exception as error:
                    debug(f"Status summary: {error}", environment)
                try:
                    score = score_prompt(
                        record["prompt"],
                        record["prompt_id"],
                        record.get("session_id"),
                        environment,
                    )
                    scores_path = related_log_path(
                        prompt_log_path,
                        environment,
                        "AI_SOCIAL_CREDIT_SCORE_SCORES_FILE",
                        "scores.jsonl",
                    )
                    append_record(scores_path, score)
                    status_event = "success"
                except Exception as error:
                    errors_path = related_log_path(
                        prompt_log_path,
                        environment,
                        "AI_SOCIAL_CREDIT_SCORE_ERRORS_FILE",
                        "score_errors.jsonl",
                    )
                    append_record(
                        errors_path,
                        scoring_error_record(record, error),
                    )
                    debug(str(error), environment)
                finally:
                    try:
                        update_status(environment, event=status_event, job_id=job_id)
                    except Exception as error:
                        debug(f"Status summary: {error}", environment)
    except Exception as error:  # A capture failure must not interrupt Claude Code.
        debug(str(error), environment)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
