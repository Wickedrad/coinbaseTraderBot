#!/usr/bin/env bash
# Pulls archived days from Google Drive (written by .github/workflows/drive-archive.yml) into a lab's data dir, so the
# lab reads no server at all for those days.
#
#   deploy/drive_pull.sh <data dir> <YYYY-MM-DD[,YYYY-MM-DD...]>
#
# Needs rclone with the "gdrive" remote (RCLONE_CONF secret, see drive-archive.yml). Writes
# <data dir>/recordings/md-<day>.jsonl.gz and <data dir>/audit/audit-<day>*, as the bot lays them out. A day Drive holds
# only in compact form (md-<day>.mdc) is decoded to that gzip name by drive_lab.sh recording.
# Prints the days Drive did not have on stdout's last line ("missing: ..."), so a workflow can read only those from
# the server (exit 0 either way; exit 1 only on a bad argument or a failed download).
set -euo pipefail
DATA=${1:?data dir}; DAYS=${2:?days}
[[ "$DAYS" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}(,[0-9]{4}-[0-9]{2}-[0-9]{2})*$ ]] || { echo "days must be YYYY-MM-DD[,YYYY-MM-DD...]" >&2; exit 1; }
ROOT=${DRIVE_ROOT:-gdrive:kalshi-bot-archive}
mkdir -p "$DATA/recordings" "$DATA/audit"
HERE=$(dirname "$0")
HAVE=$(bash "$HERE/drive_lab.sh" days)
MISSING=()
for d in ${DAYS//,/ }; do
  if ! grep -qx "$d" <<<"$HAVE"; then MISSING+=("$d"); continue; fi
  bash "$HERE/drive_lab.sh" recording "$d" "$DATA/recordings"
  rclone copy "$ROOT/audit" "$DATA/audit/" --include "audit-$d*" --transfers 4
  echo "$d: from Drive"
done
echo "missing: $(IFS=,; echo "${MISSING[*]}")"
