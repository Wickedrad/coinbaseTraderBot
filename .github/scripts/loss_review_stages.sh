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
#   LR_RESPONSES  JSON object {name: reply} of the model steps' replies, each the output of `python3 -m lossreview.screen NAME`
#                 (a reply screening would change is refused); saved as work/DAY/NAME.response.json before the stages
#   LR_SINCE, LR_UNTIL   the window stage's UTC clock bounds, HH:MM[:SS] (00:00 to 23:59:59, or 24:00 for the end of the day)
#   LR_WEEKLY     the weekly token allowance the budget stage also checks (digits), when the plan's limit is near
#
# The usage and budget stages are keyed to the day the tokens are spent (today, UTC), not to the day of the trips: the allowance is
# per calendar day. A usage entry is logged once per workflow run (GITHUB_RUN_ID.N), so "Re-run failed jobs" does not count it twice.
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
WEEKLY=${LR_WEEKLY:-}
TODAY=$(date -u +%F)
RUN=${GITHUB_RUN_ID:-local}
[[ "$DAY" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "::error::bad day: '$DAY'" >&2; exit 1; }
for c in "$SINCE" "$UNTIL"; do
  [ -z "$c" ] || [[ "$c" =~ ^(([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?|24:00(:00)?)$ ]] || { echo "::error::bad clock time: '$c'" >&2; exit 1; }
done
[ -z "$WEEKLY" ] || [[ "$WEEKLY" =~ ^[0-9]{1,10}$ ]] || { echo "::error::bad weekly allowance: '$WEEKLY'" >&2; exit 1; }
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
n=0
for e in ${STEPS[@]+"${STEPS[@]}"}; do
  IFS=: read -r step tin tout items <<< "$e"
  n=$((n + 1))
  D usage "$TODAY" --w "$W" --step "$step" --tokens-in "$tin" --tokens-out "$tout" --items "$items" --run "$RUN.$n"
  WRITES=1
done
if [ -n "${LR_RESPONSES:-}" ]; then D responses "$DAY" --w "$W"; WRITES=1; fi
for s in "${LIST[@]}"; do
  case "$s" in
    pending|status) D "$s" --w "$W" ;;
    budget) D budget "$TODAY" --w "$W" ${WEEKLY:+--weekly "$WEEKLY"} ;;
    window) D window "$DAY" --w "$W" ${SINCE:+--since "$SINCE"} ${UNTIL:+--until "$UNTIL"}; WRITES=1 ;;
    *) D "$s" "$DAY" --w "$W"; [[ "$READONLY" == *" $s "* ]] || WRITES=1 ;;
  esac
done
if [ -n "$WRITES" ]; then
  # The registry and the usage log first, then the day's work folder (it holds done.json): a put that stops half way can leave a
  # day not marked done, never a day marked done without its registry.
  bash deploy/drive_lab.sh put derived/loss-review "$W" --include registry.jsonl --include usage.jsonl
  bash deploy/drive_lab.sh put derived/loss-review "$W" --include "work/$DAY/**"
else
  echo "read-only stages: nothing put back to Drive"
fi
