#!/usr/bin/env bash
# Numbers one look at the confirm days (history-twin.yml). Every look is a small file on Drive under
# derived/twin-confirm-looks (copy only: nothing is ever deleted there); the number is the count of files + 1.
# Prints the number on stdout, everything else on stderr. Needs rclone set up (.github/actions/drive-setup).
# A look needs a note: one that is empty after control characters and spaces are stripped is refused (exit 1) before
# anything is read from or written to Drive.
#
#   twin-look.sh "<the dispatch's confirm_look_note>"
set -euo pipefail
NOTE=${1-}
LAB=${DRIVE_LAB:-deploy/drive_lab.sh}
# Control characters become spaces, the ends are trimmed, 200 characters at most (research/historyTwin.ts does the same).
CLEAN=$(printf '%s' "$NOTE" | tr '\000-\037\177' ' ' | sed -E 's/^ +//; s/ +$//' | cut -c1-200)
[ -n "$CLEAN" ] || { echo "[twin] ERROR: split=confirm needs a confirm_look_note (empty after control characters and spaces are stripped): every look at the confirm days is numbered and logged" >&2; exit 1; }
WORK=$(mktemp -d)
mkdir -p "$WORK/seen" "$WORK/new"
rc=0
bash "$LAB" get derived/twin-confirm-looks "$WORK/seen" >&2 || rc=$?
{ [ "$rc" -eq 0 ] || [ "$rc" -eq 3 ]; } || { echo "[twin] ERROR: could not read the look log on Drive (exit $rc)" >&2; exit 1; }
SEEN=$(find "$WORK/seen" -maxdepth 1 -name 'look-*' | wc -l)
N=$((SEEN + 1))
printf 'look %s\nrun %s attempt %s\nat %s UTC\nnote %s\n' "$N" "${GITHUB_RUN_ID:-local}" "${GITHUB_RUN_ATTEMPT:-1}" "$(date -u +%FT%TZ)" "$CLEAN" \
  > "$WORK/new/look-$(printf '%03d' "$N")-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.txt"
bash "$LAB" put derived/twin-confirm-looks "$WORK/new" >&2
echo "[twin] CONFIRM LOOK #$N logged on Drive" >&2
echo "$N"
