#!/usr/bin/env bash
# Recorded days from Google Drive first (Steven, Nov 2: storage on Drive, the server only for days Drive lacks).
#   snn_drive_first.sh <file list from the server's recordings/> <dest dir>
# Every md-DAY.jsonl.gz in the list that the Drive archive holds ($RUNNER_TEMP/drive-days.txt, written by
# .github/actions/drive-setup) is pulled from Drive (unless already present) and dropped from the list, so the caller's
# rsync reads only the rest from the server.
set -euo pipefail
LIST=$1 DEST=$2; mkdir -p "$DEST"
DAYS="$RUNNER_TEMP/drive-days.txt"; [ -s "$DAYS" ] || { echo "Drive day list missing: everything from the server"; exit 0; }
KEEP="$LIST.server"; : > "$KEEP"; n=0
while IFS= read -r f; do
  d=$(printf '%s' "$f" | sed -nE 's#^(.*/)?md-([0-9]{4}-[0-9]{2}-[0-9]{2})\.jsonl\.gz$#\2#p')
  if [ -n "$d" ] && [ "$f" = "md-$d.jsonl.gz" ] && grep -qx "$d" "$DAYS"; then
    if [ -s "$DEST/$f" ] || bash deploy/drive_lab.sh recording "$d" "$DEST"; then n=$((n + 1)); continue; fi
  fi
  printf '%s\n' "$f" >> "$KEEP"
done < "$LIST"
mv "$KEEP" "$LIST"
echo "from Drive: $n recorded day(s); from the server: $(wc -l < "$LIST") file(s)"
