#!/usr/bin/env bash
# One day's loss-review trip file, built on a GitHub runner from the audit days already archived on Drive (no server
# contact). Needs rclone with the "gdrive" remote (.github/actions/drive-setup) and runs from the repository root.
#
#   bash .github/scripts/loss_review_run.sh YYYY-MM-DD [catchup]
#   bash .github/scripts/loss_review_run.sh --one YYYY-MM-DD       (what each day's build runs as: a process of its own, so that
#                                                                   errexit holds inside it; a function tested with || would not)
#
# With "catchup" (the scheduled and archive-triggered runs) the up-to-3 days before YYYY-MM-DD that have an audit on Drive but no
# trip file yet are built first, oldest first: a night the archive missed or a run that failed is picked up by the next one.
# Per-trade rows go to Drive (derived/loss-review/days) and nowhere else: the repository is public, so nothing is an Actions
# artifact and the log prints aggregates only (python/lossreview/nightly.py).
set -euo pipefail
ONE=
if [ "${1:-}" = --one ]; then ONE=1; shift; fi
DAY=${1:?usage: loss_review_run.sh [--one] YYYY-MM-DD [catchup]}
CATCHUP=${2:-}
[[ "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad day: $DAY" >&2; exit 1; }
ROOT=${DRIVE_ROOT:-gdrive:kalshi-bot-archive}

build_day() {
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
  echo "$DAY: audit files on the runner: $(ls -1 "$W/audit" | wc -l) ($(du -sh "$W/audit" | cut -f1))"
  if ! compgen -G "$W/audit/audit-$DAY*.jsonl" >/dev/null && ! compgen -G "$W/audit/audit-$DAY*.jsonl.gz" >/dev/null; then
    echo "::error::Drive has no audit for $DAY yet (the daily archive copies each finished day)"; exit 1
  fi
  # nightly.py exits non-zero when the day has no records at all, and (3) when the public candle and result join failed for most
  # trips (a degraded file must not replace a good one on Drive). A day with records but no heat trips is a quiet day (a notice,
  # the files are still written so the routine can tell "no trips" from "not built").
  PYTHONPATH=python python3 -B -m lossreview.nightly --day "$DAY" --audit-dir "$W/audit" --out "$W/out" ${LOSSREVIEW_NIGHTLY_ARGS:-}
  for f in "trips-$DAY.jsonl" "agg-$DAY.json" "report-$DAY.md"; do
    [ -f "$W/out/$f" ] || { echo "::error::$f was not written"; exit 1; }
  done
  if [ ! -s "$W/out/trips-$DAY.jsonl" ]; then echo "::notice::$DAY had audit records but no heat trips"; fi
  bash deploy/drive_lab.sh put derived/loss-review/days "$W/out" --include "trips-$DAY.jsonl" --include "agg-$DAY.json" --include "report-$DAY.md"
  rm -rf "$W"
}

if [ -n "$ONE" ]; then build_day; exit 0; fi

days=()
if [ "$CATCHUP" = catchup ]; then
  for k in 3 2 1; do
    d=$(date -u -d "$DAY - $k days" +%F)
    has_audit=$(rclone lsf "$ROOT/audit" --files-only --include "audit-$d*" 2>/dev/null | head -1 || true)
    has_trips=$(rclone lsf "$ROOT/derived/loss-review/days" --files-only --include "trips-$d.jsonl" 2>/dev/null | head -1 || true)
    if [ -n "$has_audit" ] && [ -z "$has_trips" ]; then echo "catching up $d (audit on Drive, no trip file)"; days+=("$d"); fi
  done
fi
days+=("$DAY")
status=0
for d in "${days[@]}"; do
  bash "$0" --one "$d" || { echo "::error::the build of $d failed"; status=1; }
done
exit $status
