#!/usr/bin/env python3
"""Explain the saved personal score without reading prompts or calling a model."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Mapping

from report import load_scores, terminal_text
from score_prompt import credit_score_from_niceness, credit_score_from_total


DIMENSIONS = ("respect", "warmth", "cooperation", "hostility")
FORMULA = "300 + round_half_up(550 * niceness_total / (100 * scored_prompt_count))"


def saved_rationale(record: Mapping[str, Any]) -> str | None:
    value = record.get("rationale")
    return value[:300] if isinstance(value, str) and value.strip() else None


def build_explanation(environment: Mapping[str, str]) -> dict[str, Any]:
    _, scores, skipped = load_scores(environment)
    records = list(scores.values())
    count = len(records)
    total = sum(record["overall_niceness"] for record in records)
    overall = credit_score_from_total(total, count) if count else None
    dimensions = {}
    for dimension in DIMENSIONS:
        values = [record[dimension] for record in records
                  if isinstance(record.get(dimension), int)
                  and not isinstance(record[dimension], bool)
                  and 0 <= record[dimension] <= 4]
        dimensions[dimension] = {
            "mean": round(sum(values) / len(values), 2) if values else None,
            "assessment_count": len(values),
            "scale": "0–4; lower means less hostility" if dimension == "hostility"
                     else "0–4; 2 is neutral, higher is more positive",
        }

    groups = {
        "below_neutral": sorted((r for r in records if r["overall_niceness"] < 50),
                                key=lambda r: r["overall_niceness"]),
        "neutral": [r for r in records if r["overall_niceness"] == 50],
        "above_neutral": sorted((r for r in records if r["overall_niceness"] > 50),
                                key=lambda r: -r["overall_niceness"]),
    }
    evidence = []
    distribution = {}
    for name, group in groups.items():
        # These unrounded contributions add to the overall offset from 575.
        # All assessments have equal weight; optional dimensions are descriptive.
        distribution[name] = {
            "count": len(group),
            "credit_points_vs_neutral": round(
                5.5 * sum(r["overall_niceness"] - 50 for r in group) / count, 2
            ) if count else 0,
        }
        seen = set()
        for record in group:
            rationale = saved_rationale(record)
            key = (record["overall_niceness"], rationale)
            if rationale is None or key in seen:
                continue
            seen.add(key)
            date = record.get("scored_at")
            evidence.append({
                "group": name,
                "credit_score": credit_score_from_niceness(record["overall_niceness"]),
                "scored_at": date[:40] if isinstance(date, str) else None,
                "rationale": rationale,
            })
            if len(seen) == 3:
                break

    return {
        "overall_score": overall,
        "scored_prompt_count": count,
        "niceness_total": total,
        "mean_niceness": round(total / count, 2) if count else None,
        "neutral_credit_score": 575,
        "formula": FORMULA,
        "distribution": distribution,
        "dimensions": dimensions,
        "assessments_with_rationale": sum(saved_rationale(r) is not None for r in records),
        "evidence": evidence,
        "skipped_record_count": skipped,
        "notes": [
            "Each distinct scored prompt has equal weight; the last valid assessment wins.",
            "Missing or failed scores are excluded, not treated as zero.",
            "Dimension averages describe the assessments; they do not calculate overall niceness.",
            "Means and group contributions are displayed rounded; the final score uses the exact total.",
            "Evidence is a limited sample of saved rationales, not a new assessment or the full history.",
            "Short, direct requests and missing 'please' are neutral, not inherently rude.",
        ],
    }


def format_explanation(result: Mapping[str, Any]) -> str:
    lines = ["AI Social Credit Score — explanation"]
    count = result["scored_prompt_count"]
    if not count:
        lines.append("No scored prompts yet. Submit a prompt and wait for background scoring.")
    else:
        lines.extend([
            f"Overall: {result['overall_score']} / 850 (range 300–850), based on {count} scored prompts.",
            f"Average niceness: {result['mean_niceness']} / 100. Neutral corresponds to 575.",
            f"Calculation: {result['formula']}",
            f"Niceness total: {result['niceness_total']}; scored prompt count: {count}.",
            "\nWhat moves the score (compared with every prompt being neutral):",
        ])
        for name, group in result["distribution"].items():
            lines.append(f"  {name.replace('_', ' ').capitalize()}: {group['count']} prompts, "
                         f"{group['credit_points_vs_neutral']:+.2f} credit points")
        lines.append("\nSaved rubric averages (not the formula for the overall score):")
        for name, values in result["dimensions"].items():
            average = "unavailable" if values["mean"] is None else f"{values['mean']} / 4"
            lines.append(f"  {name.capitalize()}: {average} ({values['assessment_count']} assessments)")
        lines.append("  Lower hostility is better; higher respect, warmth, and cooperation are more positive.")
        lines.append(f"\nSaved reasons available for {result['assessments_with_rationale']} of {count} assessments.")
        for example in result["evidence"]:
            date = f" · {terminal_text(example['scored_at'])}" if example["scored_at"] else ""
            lines.append(f"  [{example['credit_score']}{date}] {terminal_text(example['rationale'])}")
        lines.append("\n" + "\n".join(result["notes"]))
    if result["skipped_record_count"]:
        lines.append(f"Skipped {result['skipped_record_count']} incomplete or invalid score records.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", help="Directory containing local score logs")
    parser.add_argument("--plugin-data-dir", help="Claude Code's persistent plugin data directory")
    parser.add_argument("--json", action="store_true", help="Print structured explanation data")
    args = parser.parse_args()
    environment = dict(os.environ)
    if args.plugin_data_dir:
        environment["CLAUDE_PLUGIN_DATA"] = args.plugin_data_dir
    if args.data_dir:
        environment.pop("AI_SOCIAL_CREDIT_SCORE_LOG_FILE", None)
        environment.pop("AI_SOCIAL_CREDIT_SCORE_SCORES_FILE", None)
        environment["AI_SOCIAL_CREDIT_SCORE_DATA_DIR"] = args.data_dir
    try:
        result = build_explanation(environment)
    except (OSError, UnicodeError) as error:
        print(f"Could not read local scores: {terminal_text(error)}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else format_explanation(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
