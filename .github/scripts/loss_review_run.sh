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
# The day itself is required: a failed pull of it is an error, never a silent empty run. The neighbouring days only supply
# trips that straddle midnight, so a missing one is a notice.
for d in "$prev" "$DAY" "$next"; do
  if bash deploy/drive_lab.sh audit "$d" "$W/audit"; then :; elif [ "$d" = "$DAY" ]; then
    echo "::error::pulling the audit for $DAY from Drive failed"; exit 1
  else echo "::notice::no audit pulled for $d (only supplies trips across midnight)"; fi
done
# Partial or temporary copies never count (an interrupted rclone copy leaves *.partial).
find "$W/audit" -type f \( -name '*.partial' -o -name '*.tmp' \) -delete
echo "audit files on the runner: $(ls -1 "$W/audit" | wc -l) ($(du -sh "$W/audit" | cut -f1))"
if ! ls "$W/audit" | grep -Eq "^audit-$DAY.*\.jsonl(\.gz)?$"; then
  echo "::error::Drive has no audit for $DAY yet (the daily archive runs at 07:20 UTC for the day before)"; exit 1
fi
# nightly.py exits non-zero when the day has no records at all; a day with records but no heat trips is a quiet day (a
# notice, the file is still written so the routine can tell "no trips" from "not built").
PYTHONPATH=python python3 -B -m lossreview.nightly --day "$DAY" --audit-dir "$W/audit" --out "$W/out"
for f in "trips-$DAY.jsonl" "agg-$DAY.json" "report-$DAY.md"; do
  [ -f "$W/out/$f" ] || { echo "::error::$f was not written"; exit 1; }
done
if [ ! -s "$W/out/trips-$DAY.jsonl" ]; then echo "::notice::$DAY had audit records but no heat trips"; fi
bash deploy/drive_lab.sh put derived/loss-review/days "$W/out" --include "trips-$DAY.jsonl" --include "agg-$DAY.json" --include "report-$DAY.md"
rm -rf "$W"
