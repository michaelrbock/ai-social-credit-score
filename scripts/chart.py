#!/usr/bin/env python3
"""Draw a local ASCII history of the cumulative score without reading prompts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from typing import Any, Mapping

from report import load_scores, terminal_text
from score_prompt import credit_score_from_total


WIDTH = 49
HEIGHT = 11


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def build_chart(environment: Mapping[str, str]) -> dict[str, Any]:
    _, scores, skipped = load_scores(environment)
    records = [(record, parse_time(record.get("scored_at"))) for record in scores.values()]
    dated = bool(records) and all(date is not None for _, date in records)
    if dated:
        records.sort(key=lambda pair: pair[1])
    points = []
    total = 0
    for count, (record, date) in enumerate(records, 1):
        total += record["overall_niceness"]
        points.append({
            "scored_prompt_count": count,
            "overall_score": credit_score_from_total(total, count),
            "scored_at": date.isoformat() if date is not None else None,
        })
    axis = "time" if dated else "prompt_order"
    reason = "timestamps incomplete" if records and not dated else None
    if dated and len(points) > 1 and points[0]["scored_at"] == points[-1]["scored_at"]:
        axis, reason = "prompt_order", "all timestamps identical"
    return {
        "overall_score": points[-1]["overall_score"] if points else None,
        "scored_prompt_count": len(points),
        "axis": axis,
        "axis_reason": reason,
        "points": points,
        "skipped_record_count": skipped,
    }


def format_chart(result: Mapping[str, Any]) -> str:
    lines = ["Your score over time", ""]
    points = result["points"]
    if not points:
        lines.append("No scored prompts yet. Send a prompt and wait for scoring.")
    else:
        values = [point["overall_score"] for point in points]
        # Auto-zoom in multiples of 25, with padding and a minimum 50-point span.
        low = max(300, ((min(values) - 25) // 25) * 25)
        high = min(850, ((max(values) + 49) // 25) * 25)
        if high - low < 50:
            low, high = max(300, high - 50), min(850, low + 50)
        if result["axis"] == "time":
            times = [parse_time(point["scored_at"]) for point in points]
            positions = [(date - times[0]).total_seconds() for date in times]
            labels = [times[0].strftime("%Y-%m-%d %H:%M"),
                      times[-1].strftime("%Y-%m-%d %H:%M")]
            axis_label = "Time (UTC)"
        else:
            positions = list(range(len(points)))
            labels = ["#1", f"#{len(points)}"]
            axis_label = f"Prompt order ({result['axis_reason']})"
        span = positions[-1]
        coordinates = [
            (round(position / span * (WIDTH - 1)) if span else 0,
             round((high - score) / (high - low) * (HEIGHT - 1)))
            for position, score in zip(positions, values)
        ]
        grid = [[" "] * WIDTH for _ in range(HEIGHT)]
        # Connect the observations, including vertical moves when points share
        # a column. Dots indicate interpolation, not additional assessments.
        for (x0, y0), (x1, y1) in zip(coordinates, coordinates[1:]):
            steps = max(abs(x1 - x0), abs(y1 - y0))
            for step in range(1, steps):
                x = round(x0 + (x1 - x0) * step / steps)
                y = round(y0 + (y1 - y0) * step / steps)
                grid[y][x] = "."
        for x, y in coordinates:
            grid[y][x] = "*"
        x, y = coordinates[-1]
        grid[y][x] = "@"
        count = len(points)
        lines.append(f"Now: {values[-1]} / 850 | {count} scored prompt{'s' if count != 1 else ''}")
        lines.append(f"Start: {values[0]} | Change: {values[-1] - values[0]:+d}")
        lines.append("")
        for row, cells in enumerate(grid):
            label = str(round(high - row * (high - low) / (HEIGHT - 1))) if row % 2 == 0 else ""
            lines.append(f"{label:>3} |" + "".join(cells).rstrip())
        lines.append("    +" + "-" * WIDTH)
        if len(points) == 1:
            lines.append("     " + labels[0])
        else:
            lines.append("     " + labels[0] + " " * (WIDTH - len(labels[0]) - len(labels[1])) + labels[1])
        lines.extend([
            axis_label,
            "* cumulative score   @ latest   . connecting line",
            "Y-axis auto-zooms; possible scores range from 300 to 850.",
            "Reconstructed from the latest assessment per prompt.",
        ])
        if result["axis"] == "prompt_order":
            lines.append("Order follows each prompt's first appearance in the score log.")
        if len(points) == 1:
            lines.append("One point so far. Your trail grows as more prompts are scored.")
    if result["skipped_record_count"]:
        lines.append(f"Skipped {result['skipped_record_count']} incomplete or invalid score records.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="Directory containing local score logs")
    parser.add_argument("--plugin-data-dir", help="Claude Code's persistent plugin data directory")
    parser.add_argument("--json", action="store_true", help="Print the reconstructed history as JSON")
    args = parser.parse_args()
    environment = dict(os.environ)
    if args.plugin_data_dir:
        environment["CLAUDE_PLUGIN_DATA"] = args.plugin_data_dir
    if args.data_dir:
        environment.pop("AI_SOCIAL_CREDIT_SCORE_LOG_FILE", None)
        environment.pop("AI_SOCIAL_CREDIT_SCORE_SCORES_FILE", None)
        environment["AI_SOCIAL_CREDIT_SCORE_DATA_DIR"] = args.data_dir
    try:
        result = build_chart(environment)
    except (OSError, UnicodeError) as error:
        print(f"Could not read local scores: {terminal_text(error)}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2) if args.json else format_chart(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
