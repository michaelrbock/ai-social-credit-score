#!/usr/bin/env python3
"""Standalone status-line renderer, copied to a stable location during setup."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def render_score(state: dict, *, color: bool = False, now: float | None = None) -> str:
    now = time.time() if now is None else now
    score = state.get("overall_score")
    if score is None:
        result = "AI Score: --"
    elif isinstance(score, int) and not isinstance(score, bool) and 300 <= score <= 850:
        result = f"AI Score: {score}"
        delta = state.get("last_delta")
        if isinstance(delta, int) and not isinstance(delta, bool) and -550 <= delta <= 550:
            change = f"({delta:+d} last)"
            if color and delta:
                change = f"\033[{32 if delta > 0 else 31}m{change}\033[0m"
            result += " " + change
    else:
        return "AI Score: unavailable"
    pending = state.get("pending", {})
    deadlines = [value for value in pending.values()
                 if isinstance(value, (int, float)) and not isinstance(value, bool)] if isinstance(pending, dict) else []
    active = sum(deadline > now for deadline in deadlines)
    if active:
        result += " | scoring..." + (f" ({active})" if active > 1 else "")
    elif deadlines:
        result += " | scoring timed out"
    elif state.get("last_error"):
        result += " | last score failed"
    elif score is None:
        result += " | no scores yet"
    return result


def read_summary(path: Path, *, color: bool) -> str:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            return "AI Score: unavailable"
        return render_score(state, color=color)
    except (OSError, ValueError, UnicodeError):
        return "AI Score: unavailable"


def previous_output(command: str, input_text: str) -> str:
    with subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, start_new_session=os.name != "nt") as child:
        try:
            stdout, _ = child.communicate(input_text, timeout=0.7)
            return stdout
        except subprocess.TimeoutExpired:
            return ""
        finally:
            # End only the command tree we started, not an unrelated shell/session.
            if child.poll() is None:
                try:
                    if os.name != "nt":
                        os.killpg(child.pid, signal.SIGKILL)
                    else:
                        child.kill()
                except ProcessLookupError:
                    pass
                child.communicate()


def interrupted(signum, frame):
    # Claude can cancel a refresh. Run finally blocks so composed commands do not leak.
    raise SystemExit(0)


def main() -> int:
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, help="Preview a summary without the installed configuration")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()
    color = not args.no_color and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
    if args.state_file:
        print(read_summary(args.state_file, color=color))
        return 0
    try:
        config = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
        if not config.get("enabled"):
            return 0
        state_file = Path(config["state_file"])
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, AttributeError):
        print("AI Score: unavailable")
        return 0
    input_text = sys.stdin.read()
    previous = config.get("previous")
    if isinstance(previous, dict) and previous.get("type") == "command" and isinstance(previous.get("command"), str):
        # This is the user's existing, explicitly configured command, not score data.
        try:
            output = previous_output(previous["command"], input_text)
            if output.strip():
                print(output.rstrip("\n"))
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            pass  # A slow/broken previous segment must not hide the score.
    print(read_summary(state_file, color=color))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
