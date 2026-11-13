#!/usr/bin/env bash
# One day's loss-review trip file, built on a GitHub runner from the audit days already archived on Drive (no server
# contact). Needs rclone with the "gdrive" remote (.github/actions/drive-setup) and runs from the repository root.
#
#   bash .github/scripts/loss_review_run.sh YYYY-MM-DD
#
# Per-trade rows go to Drive (derived/loss-review/days) and nowhere else: the repository is public, so nothing is an Actions
# artifact and the log prints aggregates only (python/lossreview/nightly.py).
set -euo pipefail
DAY=${1:?usage: loss_review_run.sh YYYY-MM-DD}
[[ "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad day: $DAY" >&2; exit 1; }
W="${RUNNER_TEMP:-/tmp}/loss-review-$DAY"
rm -rf "$W"; mkdir -p "$W/audit" "$W/out"
prev=$(date -u -d "$DAY - 1 day" +%F); next=$(date -u -d "$DAY + 1 day" +%F)
for d in "$prev" "$DAY" "$next"; do
  bash deploy/drive_lab.sh audit "$d" "$W/audit" || echo "no audit for $d on Drive"
done
echo "audit files on the runner: $(ls -1 "$W/audit" | wc -l) ($(du -sh "$W/audit" | cut -f1))"
if ! ls "$W/audit" | grep -q "^audit-$DAY"; then
  echo "::error::Drive has no audit for $DAY yet (the daily archive runs at 07:20 UTC for the day before)"; exit 1
fi
PYTHONPATH=python python3 -B -m lossreview.nightly --day "$DAY" --audit-dir "$W/audit" --out "$W/out"
bash deploy/drive_lab.sh put derived/loss-review/days "$W/out" --include "trips-$DAY.jsonl" --include "agg-$DAY.json" --include "report-$DAY.md"
rm -rf "$W"
