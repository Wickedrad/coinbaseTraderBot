"""J22: aggregate private already-scored Kalshi direction rows into day/coin/side/kind rates.

No test results are treated as independent trades. One prospective frozen config,
12 predeclared full-book UTC days, one fixed look. No auto-pass and no curve edits.
"""
import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean, stdev

from .window_core import MIN_PUBLIC_CELL, bootstrapped_gap, gap_of, jsonl


def range12(start: str) -> list[str]:
    d = date.fromisoformat(start)
    return [(d + timedelta(days=i)).isoformat() for i in range(12)]


def group_upper90_by_day(xs: list[dict]) -> float | None:
    """Exploratory negative-split flag, NOT a binding owner-approved threshold."""
    per = defaultdict(list)
    for r in xs:
        per[r["day"]].append(gap_of(r))
    days = [mean(a) for a in per.values()]
    if len(days) < 4:
        return None
    return mean(days) + 1.282 * stdev(days) / len(days) ** 0.5


def make_report(rows: list[dict], coverage: dict, start_day: str) -> dict:
    requested = range12(start_day)
    full = set(coverage.get("full_days") or [])
    missing_days = [d for d in requested if d not in full]
    scored = [r for r in rows if r.get("status") == "scored" and r.get("day") in requested
              and r.get("source_mode") == "forward"]
    mixed_mode = sum(r.get("day") in requested and r.get("source_mode") != "forward" for r in rows)
    by_day = defaultdict(list)
    for r in scored:
        by_day[r["day"]].append(r)
    daily = []
    for day in requested:
        xs = by_day[day]
        ok = day in full and bool(xs)
        result = {"day": day, "full_book": day in full, "eligible": bool(ok),
                  "n": len(xs) if len(xs) >= MIN_PUBLIC_CELL else "suppressed"}
        if ok and len(xs) >= MIN_PUBLIC_CELL:
            result.update({"paired_gap": round(mean(gap_of(x) for x in xs), 6),
                           "positive": bool(mean(gap_of(x) for x in xs) > 0)})
        daily.append(result)
    # A day with <5 entries cannot be revealed publicly, and cannot silently be counted as favorable.
    valid_days = [d for d in daily if d.get("positive") is not None]
    positive = sum(1 for d in valid_days if d["positive"])
    by_split = defaultdict(list)
    for r in scored:
        for name, key in (("coin", r["asset"]), ("side", r["side"]),
                          ("kind", r["kind"]), ("regime", r.get("regime", "unknown"))):
            by_split[(name, key)].append(r)
    splits = []
    for (name, key), rs in sorted(by_split.items()):
        if len(rs) < MIN_PUBLIC_CELL:
            continue
        upper90 = group_upper90_by_day(rs)
        splits.append({"dimension": name, "value": key, "n": len(rs),
                       "paired_gap": round(mean(gap_of(r) for r in rs), 6),
                       "upper90_exploratory": round(upper90, 6) if upper90 is not None else None,
                       "clearly_negative_exploratory": upper90 < 0 if upper90 is not None else None})
    # No counting a historical day as fresh prospective, or declaring a gate from this analysis-only code.
    complete = not missing_days and len(valid_days) == 12
    return {"schema": "ralph-j22-diagnostic-v1", "job": "J22", "risk": "R0", "trial_count": 1,
            "start_utc": start_day, "end_utc_inclusive": requested[-1],
            "full_book_missing_days": missing_days, "scorable_days": len(valid_days),
            "non_forward_records_excluded": mixed_mode,
            "daily_positive": positive, "daily_required": 9,
            "positive_days_condition": (positive >= 9 if complete else None),
            "status": "diagnostic_only" if complete and not mixed_mode else "underpowered_or_missing_capture",
            "mde": bootstrapped_gap(scored)["mde_gap"],
            "overall": bootstrapped_gap(scored), "daily": daily, "splits": splits,
            "warnings": ["Not the pinned evaluator", "No binding pass/fail, no live action",
                         "Coin/side negative definition needs pin confirmation",
                         "All 12 consecutive UTC days must be covered; no picking lucky days"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scores", nargs="+", required=True, help="PRIVATE J06-scored JSONL files")
    p.add_argument("--coverage", required=True, help="PRIVATE coverage JSON {full_days:[...]} verified independently")
    p.add_argument("--start-day", required=True, help="Precommitted first UTC day, cannot change after outcome look")
    p.add_argument("--public-output", required=True)
    a = p.parse_args()
    rows = [r for path in a.scores for r in jsonl(path)]
    cov = json.loads(Path(a.coverage).read_text(encoding="utf8"))
    result = make_report(rows, cov, a.start_day)
    Path(a.public_output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.public_output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"job": "J22", "status": result["status"], "scorable_days": result["scorable_days"],
                      "metrics_written": True}))


if __name__ == "__main__":
    main()