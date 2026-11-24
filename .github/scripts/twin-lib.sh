# Sourced by the steps of history-twin.yml (source .github/scripts/twin-lib.sh); not run on its own.
#
# twin_fail MESSAGE: fail the step with the reason where it can be read. It prints the ::error:: annotation (the Actions UI)
# AND appends a '[twin] ERROR: MESSAGE' line to the job's log file ($TWIN_LOG, else $RUNNER_TEMP/build.log), which the job's
# commit comment keeps: a failure's reason must not live only in the job log, which the cloud session may not be able to read.
# Counts and plain messages only (the repository is public).
twin_fail() {
  echo "::error::$*"
  echo "[twin] ERROR: $*" >> "${TWIN_LOG:-${RUNNER_TEMP:-/tmp}/build.log}"
  exit 1
}

# twin_failed_steps RUN_ID OWNER/REPO JOB_REGEX: one 'JOB NAME<TAB>FAILED STEP NAME' line for each job of the run whose name matches
# JOB_REGEX (a jq/Oniguruma regex) and has a failed step (the first one). Used by the reports that must say WHERE a job stopped when
# no log file exists for it (a prep day, a verdict job that failed before its Verdict step). Needs GH_TOKEN and the job's
# 'actions: read' permission. It never fails: when the jobs cannot be listed it prints nothing. Step names are the workflow's own text.
twin_failed_steps() {
  local f; f=$(mktemp)
  if gh api "repos/$2/actions/runs/$1/jobs?per_page=100" > "$f" 2>/dev/null; then
    jq -r --arg re "$3" '.jobs[] | select(.name | test($re)) | .name as $j | ([.steps[]? | select(.conclusion == "failure") | .name] | .[0]) as $s | select($s != null) | "\($j)\t\($s)"' "$f" 2>/dev/null || true
  fi
  rm -f "$f"
}

# ---------------------------------------------------------------------------------------------------------------------------------
# The job's time budget (round S1). The build job has a hard limit (timeout-minutes, TWIN_JOB_LIMIT_MIN below: the workflow sets it from
# the same number and a test holds the two together). P2 (run 45094523646) was cancelled at that limit in the middle of the match step:
# a cancelled job keeps no log, no cache and no Drive copy, and none of its later steps run. So a heavy command runs under `timeout` with
# the seconds the job has LEFT, computed from the job clock (JOB_START, epoch seconds, written by the build job's clock step) at the moment
# the command starts, never a fixed number: a confirm run starts the step later (7 FIT days to fit and calibrate) and gets less.
#
#   left = limit - (now - JOB_START + slack) - reserve
#
#   TWIN_JOB_LIMIT_MIN  the job's timeout-minutes (default 340)
#   TWIN_RESERVE_MIN    minutes kept for what runs AFTER the stage: the cache saves, the Drive put and the report (default 25); the steps
#                       that still run after a cut (always()) have timeout-minutes of their own whose sum stays inside it (a test says so)
#   TWIN_CLOCK_SLACK_S  seconds the job had already used before its clock step (set-up of the job, checkout; default 120)
#
# twin_now is the clock (a test replaces this function with a fake one).
twin_now() { date +%s; }

# twin_seconds_left: the seconds a heavy command may still run (can be <= 0). Without a usable JOB_START it assumes the job has just begun
# and says so on stderr and in the log (a missing clock must not stop the run, but it must not pass silently either).
twin_seconds_left() {
  local limit=$(( ${TWIN_JOB_LIMIT_MIN:-340} * 60 )) reserve=$(( ${TWIN_RESERVE_MIN:-25} * 60 )) slack=${TWIN_CLOCK_SLACK_S:-120} start=${JOB_START:-} now used
  now=$(twin_now)
  if [[ "$start" =~ ^[0-9]+$ ]] && [ "$start" -le "$now" ]; then
    used=$(( now - start + slack ))
  else
    used=0
    echo "[twin] WARNING: the job clock (JOB_START) is not set or is in the future: the time budget assumes the job has just begun" | tee -a "${TWIN_LOG:-${RUNNER_TEMP:-/tmp}/build.log}" >&2
  fi
  echo $(( limit - used - reserve ))
}

# twin_budgeted NAME JOBS COMMAND...: run COMMAND (stdout and stderr, kept in the job's log file, the [twin] and Error lines also on stdout) under `timeout` with the
# seconds twin_seconds_left gives. NAME is match, fill or features; JOBS is only for the message. When the budget runs out (timeout's 124, or a kill after it) it
# prints the '[twin] ERROR: NAME was cut ...' line (twin_fail: the log and the annotation) and exits the step non-zero, so the always() steps after it (the Drive
# put and the report) still run inside the reserve; with no time left at all the command is not started (a timeout of 0 would mean "no limit"). Any other failure
# of COMMAND is returned as it is.
twin_budgeted() {
  local name=$1 jobs=$2; shift 2
  local log="${TWIN_LOG:-${RUNNER_TEMP:-/tmp}/build.log}" left t0 t1 rc=0 had_e=0
  left=$(twin_seconds_left)
  echo "[twin] time budget: $name may run up to $left s (the job's ${TWIN_JOB_LIMIT_MIN:-340}-minute limit less the time used and a ${TWIN_RESERVE_MIN:-25}-minute reserve for the steps after it)" | tee -a "$log"
  [ "$left" -gt 0 ] || twin_fail "$name was cut at the job's time budget after 0 s (jobs $jobs); the rest of this run was not built (it was not started: no time was left for it)"
  t0=$(twin_now)
  case $- in *e*) had_e=1;; esac
  set +e
  timeout --kill-after=60 "$left" "$@" 2>&1 | tee -a "$log" | grep -E '^\[twin\]|Error'
  rc=${PIPESTATUS[0]}
  [ "$had_e" = 0 ] || set -e
  t1=$(twin_now)
  if [ "$rc" -eq 124 ] || { [ "$rc" -ge 128 ] && [ $(( t1 - t0 )) -ge "$left" ]; }; then
    twin_fail "$name was cut at the job's time budget after $(( t1 - t0 )) s (jobs $jobs); the rest of this run was not built"
  fi
  return "$rc"
}
