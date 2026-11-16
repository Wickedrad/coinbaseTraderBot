"""J06: aggregate paired direction one-test rates over registered historical dates.

This cannot certify profit or forward publication. Full pre-event Kalshi books are
required. Out-of-history records and any unidentified data provenance are blockers.
"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from .window_core import aggregate_public, jsonl


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scores", nargs="+", required=True, help="PRIVATE per-day scorer JSONL")
    p.add_argument("--coverage", required=True, help="PRIVATE independently attested coverage JSON")
    p.add_argument("--from-day", default="2026-08-01")
    p.add_argument("--through-day", default="2026-11-04")
    p.add_argument("--public-output", required=True)
    a = p.parse_args()
    cov = json.loads(Path(a.coverage).read_text(encoding="utf8"))
    start, end = date.fromisoformat(a.from_day), date.fromisoformat(a.through_day)
    required = set((start + timedelta(days=i)).isoformat() for i in range((end-start).days+1))
    full = set(cov.get("full_days") or [])
    missing = sorted(required - full)
    all_rows = [r for path in a.scores for r in jsonl(path) if r.get("day") in required]
    wrong_mode = sum(r.get("source_mode") != "historical_shadow" for r in all_rows)
    rows = [r for r in all_rows if r.get("source_mode") == "historical_shadow"]
    roll = aggregate_public(rows, {})
    # Exactly one registered historical candidate. Not a self-authorizing binding gate.
    roll.update({"job": "J06", "risk": "R0", "from_utc": a.from_day, "through_utc": a.through_day,
                 "full_book_days_present": len(required & full), "full_book_days_required": len(required),
                 "missing_full_book_day_count": len(missing), "incompatible_mode_count": wrong_mode,
                 "mode": "historical_shadow_not_prospective",
                 "capture_completeness_verified": bool(cov.get("capture_completeness_verified")),
                 "fee_schedule_verified": bool(cov.get("fee_schedule_verified")),
                 "curve_selection_verified": bool(cov.get("curve_selection_verified")),
                 "status": "data_blocked" if (missing or wrong_mode or not cov.get("capture_completeness_verified") or
                        not cov.get("fee_schedule_verified") or not cov.get("curve_selection_verified")) else "diagnostic_only",
                 "warning": "Does NOT mark Stage D passed. Requires independent protected grader and signed source receipts."})
    Path(a.public_output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.public_output).write_text(json.dumps(roll, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"job": "J06", "status": roll["status"],
                      "missing_full_book_days": roll["missing_full_book_day_count"], "metrics_written": True}))


if __name__ == "__main__":
    main()