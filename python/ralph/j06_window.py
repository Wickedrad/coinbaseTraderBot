"""J06 research-only: derive the frozen one-test rows for one UTC day.

This is an adapter/scorer draft, NOT the pinned protected evaluator. Inputs must be
independently assembled and verified from the captured market/heat records.
Public JSON contains aggregates only. Private scored rows never enter this repo.
"""
import argparse
import json
from pathlib import Path

from .window_core import candidate_scores, aggregate_public


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--day", required=True, help="UTC YYYY-MM-DD")
    p.add_argument("--calls", required=True, help="PRIVATE normalized ex-ante candidate JSONL")
    p.add_argument("--markets", required=True, help="PRIVATE contract metadata JSONL")
    p.add_argument("--books", required=True, help="PRIVATE full-book snapshots JSONL, including following UTC day")
    p.add_argument("--private-output", required=True, help="PRIVATE per-entry diagnostic JSONL (never upload to public repo)")
    p.add_argument("--public-output", required=True, help="Aggregate JSON safe for public review")
    a = p.parse_args()
    priv, pub = Path(a.private_output), Path(a.public_output)
    if priv.resolve() == pub.resolve():
        p.error("private and public outputs must differ")
    rows, excluded = candidate_scores(a.calls, a.markets, a.books, a.day)
    priv.parent.mkdir(parents=True, exist_ok=True)
    with priv.open("w", encoding="utf8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    report = aggregate_public(rows, excluded)
    report.update({"job": "J06", "utc_day": a.day, "status": "draft_only",
                   "requires": ["full-book day attestation", "historical contract coverage",
                                "locked heat-call selection parity", "verified fee schedule",
                                "TS scorer parity before any binding grade"]})
    pub.parent.mkdir(parents=True, exist_ok=True)
    pub.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"job": "J06", "status": "draft_only", "scored_count": report["scored"],
                      "metrics_written": True}))


if __name__ == "__main__":
    main()