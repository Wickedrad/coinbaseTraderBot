#!/usr/bin/env bash
# Runs stages of the daily loss-review loop (python/lossreview/daily.py, docs/LOSS_REVIEW_ROUTINE.md) on a GitHub runner over a
# work folder pulled from private Drive (derived/loss-review) and put back after. Needs rclone with the "gdrive" remote
# (.github/actions/drive-setup); runs from the repository root. All input comes in through the environment (never interpolated
# into a command):
#
#   LR_DAY        UTC day the stages are for, YYYY-MM-DD (required)
#   LR_STAGES     space or comma separated, run in order: pending prepare-tags apply-tags prepare-hyp apply-hyp apply-adv sweep
#                 shadow status budget window done            (default: status)
#   LR_USAGE      model steps to log before the stages, "step:tokens_in:tokens_out:items;..." (steps: tag hypothesize adversary audit)
#   LR_RESPONSES  JSON object {name: reply} of the model steps' replies, saved as work/DAY/NAME.response.json before the stages
#   LR_SINCE, LR_UNTIL   the window stage's UTC clock bounds, HH:MM[:SS]
#
# The repository is public: the log shows the stages' aggregate lines only; per-trade files stay on Drive and the runner.
# What goes back to Drive: registry.jsonl, usage.jsonl and work/DAY/ (never days/, never anything else), and only when something
# that writes ran; a stage that fails stops the run before the put.
set -euo pipefail
DAY=${LR_DAY:-}
STAGES=${LR_STAGES:-status}
USAGE=${LR_USAGE:-}
SINCE=${LR_SINCE:-}
UNTIL=${LR_UNTIL:-}
[[ "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "::error::bad day: '$DAY'" >&2; exit 1; }
for c in "$SINCE" "$UNTIL"; do
  [ -z "$c" ] || [[ "$c" =~ ^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$ ]] || { echo "::error::bad clock time: '$c'" >&2; exit 1; }
done
READONLY=" pending status budget "
LIST=()
IFS=', ' read -ra TOK <<< "$STAGES"
for s in ${TOK[@]+"${TOK[@]}"}; do
  case "$s" in
    pending|prepare-tags|apply-tags|prepare-hyp|apply-hyp|apply-adv|sweep|shadow|status|budget|window|done) LIST+=("$s") ;;
    *) echo "::error::unknown stage: '$s'" >&2; exit 1 ;;
  esac
done
[ ${#LIST[@]} -gt 0 ] || { echo "::error::no stages given" >&2; exit 1; }
STEPS=()
if [ -n "$USAGE" ]; then
  IFS=';' read -ra ENT <<< "$USAGE"
  for e in "${ENT[@]}"; do
    [[ "$e" =~ ^(tag|hypothesize|adversary|audit):[0-9]{1,9}:[0-9]{1,9}:[0-9]{1,5}$ ]] || { echo "::error::bad usage entry: '$e'" >&2; exit 1; }
    STEPS+=("$e")
  done
fi

W="${RUNNER_TEMP:-/tmp}/loss-loop-$DAY"
rm -rf "$W"; mkdir -p "$W"
trap 'rm -rf "$W"' EXIT
# The work folder: every trip file (the sweep reads the days after a loss), the registry and usage logs, the done marks and this
# day's prompts and replies. Exit 3 from the Drive helper = nothing there at all, which means no trip file was ever built.
bash deploy/drive_lab.sh get derived/loss-review "$W" --include 'days/trips-*.jsonl' --include registry.jsonl --include usage.jsonl \
  --include 'work/*/done.json' --include "work/$DAY/**" || { echo "::error::no loss-review folder on Drive (or the pull failed)"; exit 1; }
if ! compgen -G "$W/days/trips-*.jsonl" >/dev/null; then echo "::error::the pull brought no trip file"; exit 1; fi

D() { PYTHONPATH=python python3 -B -m lossreview.daily "$@"; }
D canary --w "$W"      # a broken validator stops the run before it writes anything
WRITES=
for e in ${STEPS[@]+"${STEPS[@]}"}; do
  IFS=: read -r step tin tout items <<< "$e"
  D usage "$DAY" --w "$W" --step "$step" --tokens-in "$tin" --tokens-out "$tout" --items "$items"
  WRITES=1
done
if [ -n "${LR_RESPONSES:-}" ]; then D responses "$DAY" --w "$W"; WRITES=1; fi
for s in "${LIST[@]}"; do
  case "$s" in
    pending|status) D "$s" --w "$W" ;;
    window) D window "$DAY" --w "$W" ${SINCE:+--since "$SINCE"} ${UNTIL:+--until "$UNTIL"}; WRITES=1 ;;
    *) D "$s" "$DAY" --w "$W"; [[ "$READONLY" == *" $s "* ]] || WRITES=1 ;;
  esac
done
if [ -n "$WRITES" ]; then
  bash deploy/drive_lab.sh put derived/loss-review "$W" --include registry.jsonl --include usage.jsonl --include "work/$DAY/**"
else
  echo "read-only stages: nothing put back to Drive"
fi
