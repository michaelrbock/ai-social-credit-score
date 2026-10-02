#!/usr/bin/env python3
"""Read local prompt history and scores without invoking a model or network."""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from paths import log_path
from score_prompt import credit_score_from_niceness, credit_score_from_total


def read_records(path: Path) -> tuple[list[dict[str, Any]], int]:
    records = []
    skipped = 0
    try:
        with path.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                if isinstance(value, dict):
                    records.append(value)
                else:
                    skipped += 1
    except FileNotFoundError:
        pass
    return records, skipped


def entry_time(entry: Mapping[str, Any]) -> datetime:
    """Keep old/orphaned scores in chronological order, with unknown dates first."""
    for field in ("captured_at", "scored_at"):
        value = entry.get(field)
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except ValueError:
            continue
    return datetime.min.replace(tzinfo=timezone.utc)


def valid_score(record: Mapping[str, Any]) -> bool:
    value = record.get("overall_niceness")
    key = record.get("prompt_id")
    return (record.get("event") == "prompt_score" and isinstance(key, str) and bool(key)
            and isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100)


def load_scores(environment: Mapping[str, str]) -> tuple[Path, dict[str, dict[str, Any]], int]:
    """Read the last valid assessment per prompt, shared by report and explain."""
    prompt_file = log_path(environment)
    configured_scores = environment.get("AI_SOCIAL_CREDIT_SCORE_SCORES_FILE")
    score_file = Path(configured_scores).expanduser() if configured_scores else prompt_file.with_name("scores.jsonl")
    raw_scores, skipped_scores = read_records(score_file)
    scores = {}
    for record in raw_scores:
        key = record.get("prompt_id")
        if valid_score(record):
            scores[key] = record  # Last valid record wins, including pre-v2 scores.
        else:
            skipped_scores += 1
    return score_file, scores, skipped_scores


def build_report(environment: Mapping[str, str]) -> dict[str, Any]:
    prompt_file = log_path(environment)
    prompts, skipped_prompts = read_records(prompt_file)
    score_file, scores, skipped_scores = load_scores(environment)

    entries: dict[tuple[str, Any], dict[str, Any]] = {}
    matched = set()
    for index, prompt in enumerate(prompts):
        if prompt.get("event") != "user_prompt" or not isinstance(prompt.get("prompt"), str):
            skipped_prompts += 1
            continue
        key = prompt.get("prompt_id")
        key = key if isinstance(key, str) and key else None
        score = scores.get(key)
        if score:
            matched.add(key)
        entries[("id", key) if key else ("legacy", index)] = {
            "prompt_id": key,
            "prompt": prompt["prompt"],
            "captured_at": prompt.get("captured_at"),
            "scored_at": score.get("scored_at") if score else None,
            "score": credit_score_from_niceness(score["overall_niceness"]) if score else None,
            "rationale": score.get("rationale") if score else None,
        }

    captured_count = len(entries)
    unscored_count = sum(entry["score"] is None for entry in entries.values())
    for key, score in scores.items():
        if key not in matched:
            entries[("score", key)] = {
                "prompt_id": key, "prompt": None, "captured_at": None,
                "scored_at": score.get("scored_at"),
                "score": credit_score_from_niceness(score["overall_niceness"]),
                "rationale": score.get("rationale"),
            }

    count = len(scores)
    overall = credit_score_from_total(sum(score["overall_niceness"] for score in scores.values()), count) if count else None
    return {
        "overall_score": overall,
        "scored_prompt_count": count,
        "captured_prompt_count": captured_count,
        "unscored_prompt_count": unscored_count,
        "skipped_record_count": skipped_prompts + skipped_scores,
        "data_directory": str(prompt_file.parent),
        "scores_file": str(score_file),
        "prompts": sorted(entries.values(), key=entry_time),
    }


def terminal_text(value: Any) -> str:
    """Display untrusted prompt text without terminal escapes or bidi controls."""
    return "".join(
        char if char == "\n" or not unicodedata.category(char).startswith("C")
        else f"\\u{ord(char):04x}"
        for char in str(value)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="Directory containing local prompt and score logs")
    parser.add_argument("--plugin-data-dir", help="Claude Code's persistent plugin data directory")
    parser.add_argument("--summary", action="store_true", help="Show the overall score without prompt text")
    parser.add_argument("--json", action="store_true", help="Print structured JSON")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--limit", type=int, default=10, help="Number of recent prompts to show (default: 10)")
    group.add_argument("--all", action="store_true", help="Show all local prompts")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    environment = dict(os.environ)
    if args.plugin_data_dir:
        environment["CLAUDE_PLUGIN_DATA"] = args.plugin_data_dir
    if args.data_dir:
        environment.pop("AI_SOCIAL_CREDIT_SCORE_LOG_FILE", None)
        environment.pop("AI_SOCIAL_CREDIT_SCORE_SCORES_FILE", None)
        environment["AI_SOCIAL_CREDIT_SCORE_DATA_DIR"] = args.data_dir
    try:
        report = build_report(environment)
    except (OSError, UnicodeError) as error:
        print(f"Could not read local scores: {terminal_text(error)}", file=sys.stderr)
        return 1
    entries = report.pop("prompts")
    if not args.summary:
        report["prompts"] = entries if args.all else entries[-args.limit:]
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("AI Social Credit Score")
    overall = report["overall_score"]
    print(f"Overall score: {overall} / 850 (range 300–850)" if overall is not None else "Overall score: No scored prompts yet")
    print(f"Scored prompts: {report['scored_prompt_count']} · Captured prompts: {report['captured_prompt_count']} · Without a score: {report['unscored_prompt_count']}")
    print(f"Data directory: {terminal_text(report['data_directory'])}")
    if report["skipped_record_count"]:
        print(f"Skipped {report['skipped_record_count']} incomplete or invalid log records.")
    for entry in report.get("prompts", []):
        value = str(entry["score"]) if entry["score"] is not None else "Not scored"
        date = entry["captured_at"] or entry["scored_at"] or "Date unavailable"
        print(f"\n[{value}] {terminal_text(date)}")
        print(terminal_text(entry["prompt"]) if entry["prompt"] is not None else "[Prompt text not available locally]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
