"""Private, atomic score summaries for the lightweight status-line renderer."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping

from paths import log_path
from report import valid_score
from score_prompt import credit_score_from_total


def scores_path(environment: Mapping[str, str]) -> Path:
    override = environment.get("AI_SOCIAL_CREDIT_SCORE_SCORES_FILE")
    return Path(override).expanduser() if override else log_path(environment).with_name("scores.jsonl")


def summary_path(environment: Mapping[str, str]) -> Path:
    return Path(str(scores_path(environment)) + ".status.json")


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)


def atomic_write(path: Path, content: bytes) -> None:
    private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, value: Any) -> None:
    atomic_write(path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))


@contextmanager
def file_lock(path: Path):
    private_directory(path.parent)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name != "nt":
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def aggregate(path: Path) -> dict[str, Any]:
    """Replay append order so replacements and concurrent completions have exact deltas."""
    values = {}
    total, skipped = 0, 0
    overall = delta = None
    try:
        stream = path.open(encoding="utf-8")
    except FileNotFoundError:
        return {"overall_score": None, "last_delta": None, "scored_prompt_count": 0,
                "skipped_record_count": 0}
    with stream:
        if os.name != "nt":
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(record, dict) or not valid_score(record):
                skipped += 1
                continue
            key, value = record["prompt_id"], record["overall_niceness"]
            total += value - values.get(key, 0)
            values[key] = value
            previous = overall
            overall = credit_score_from_total(total, len(values))
            delta = overall - previous if previous is not None else None
    return {"overall_score": overall, "last_delta": delta, "scored_prompt_count": len(values),
            "skipped_record_count": skipped}


def update_status(environment: Mapping[str, str], *, event: str = "refresh",
                  job_id: str | None = None, now: float | None = None) -> dict[str, Any]:
    if event not in {"refresh", "start", "success", "failure"}:
        raise ValueError("Unknown status event")
    timestamp = time.time() if now is None else now
    path = summary_path(environment)
    with file_lock(Path(str(path) + ".lock")):
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, UnicodeError):
            old = {}
        if not isinstance(old, dict):
            old = {}
        pending = old.get("pending", {})
        if not isinstance(pending, dict):
            pending = {}
        pending = {key: deadline for key, deadline in pending.items()
                   if isinstance(deadline, (int, float)) and not isinstance(deadline, bool)
                   and deadline > timestamp}
        if job_id is not None:
            if event == "start":
                # The hook is limited to 120 seconds. Expire killed/crashed jobs.
                pending[job_id] = timestamp + 150
            elif event in {"success", "failure"}:
                pending.pop(job_id, None)
        state = aggregate(scores_path(environment))
        state.update(schema_version=1, pending=pending, updated_at=timestamp,
                     last_error=event == "failure" if event != "refresh" else bool(old.get("last_error")))
        atomic_json(path, state)
        return state
