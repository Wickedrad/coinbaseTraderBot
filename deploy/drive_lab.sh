#!/usr/bin/env bash
# Google Drive storage for labs (Steven's rule, 2026-11-02: Drive instead of Actions caches or the server).
# Needs rclone with the "gdrive" remote (.github/actions/drive-setup). Layout under gdrive:kalshi-bot-archive:
#   recordings/md-DAY.jsonl.gz, audit/audit-DAY*   the nightly archive (drive-archive.yml)
#   lab-copies/<workflow>/<run id>/               what a lab run copied besides archived days, for reruns
#   derived/<name>/                               lab data rebuilt from history (rebuild only after a code change)
#
#   drive_lab.sh days                          archived days, one per line
#   drive_lab.sh recording <DAY> <dir>         pull md-DAY.jsonl.gz into <dir> (exit 3 if Drive lacks it)
#   drive_lab.sh audit <DAY> <dir>             pull audit-DAY* into <dir>
#   drive_lab.sh put <name> <src dir> [exclude file]   upload a lab copy or derived set (name: lab-copies/x/123 or derived/y)
#   drive_lab.sh get <name> <dest dir>         download it (exit 3 if Drive has nothing there)
set -euo pipefail
ROOT=${DRIVE_ROOT:-gdrive:kalshi-bot-archive}
day() { [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "bad day: $1" >&2; exit 1; }; }
name() { [[ "$1" =~ ^(lab-copies|derived)/[A-Za-z0-9._/-]+$ && "$1" != *..* ]] || { echo "bad name: $1" >&2; exit 1; }; }
case "${1:-}" in
  days)
    rclone lsf "$ROOT/recordings" --files-only | sed -nE 's/^md-([0-9]{4}-[0-9]{2}-[0-9]{2})\.jsonl\.gz$/\1/p' | sort -u ;;
  recording)
    day "$2"; mkdir -p "$3"
    [ -n "$(rclone lsf "$ROOT/recordings" --files-only --include "md-$2.jsonl.gz")" ] || exit 3
    rclone copy "$ROOT/recordings/md-$2.jsonl.gz" "$3/"
    gzip -t "$3/md-$2.jsonl.gz" ;;
  audit)
    day "$2"; mkdir -p "$3"; rclone copy "$ROOT/audit" "$3/" --include "audit-$2*" --transfers 4 ;;
  put)
    name "$2"; X=()
    [ -n "${4:-}" ] && X=(--exclude-from "$4")
    rclone copy "$3" "$ROOT/$2" "${X[@]}" --transfers 4
    echo "kept on Drive: $2 ($(rclone size "$ROOT/$2" | tail -1 | sed 's/^ *//'))" ;;
  get)
    name "$2"; mkdir -p "$3"
    [ -n "$(rclone lsf "$ROOT/$2" --max-depth 1 2>/dev/null)" ] || exit 3
    rclone copy "$ROOT/$2" "$3" --transfers 4 ;;
  *) sed -n '2,14p' "$0"; exit 1 ;;
esac
