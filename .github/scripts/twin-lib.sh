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
