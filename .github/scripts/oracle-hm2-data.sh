#!/usr/bin/env bash
# OR-HM2 data for the jobs of .github/workflows/oracle-hm2.yml (python/oracle/prereg/OR-HM2.md, "Data" and "How the cut
# is enforced"; build plan section 7, "Fetch block for each data file").
# Coin minutes 2020-01-01 to 2025-12-31 only. Every minute-like file (spot, perp, funding, open interest and the
# inventory-found BTCDOM / Coinbase / book files) is checked for 13-digit millisecond stamps on its first and last rows
# (a file in seconds would keep its 2026 rows through the cut), then cut with oracle-heat.yml's awk at HEAT_END
# (2026-01-01 UTC) on column 1 before anything computes on it, then the last stamp is asserted below the cut. Rows
# before heat_xdata.MS_LO (2019-01-01 UTC) are dropped by the same awk (review fix: a Coinbase backfill starts at
# 2015 by default, and the strict loaders refuse a row before 2019, so such a file would stop every job of its coin
# after the preflight passed; the coin minutes start at 2020-01-01 in heat.load_minutes either way). The
# calendar and the daily series are in the repository and are checked in Python (heat_xdata.load_extra, strict). The
# loaders refuse a later row as well. NEVER DOGE.
#
# Run from the repository root, with python/oracle's requirements installed and the Drive remote set up
# (.github/actions/drive-setup). DRIVE_LAB overrides deploy/drive_lab.sh (tests).
#
#   oracle-hm2-data.sh series <ASSET> <RUN> <DIR> [FOUND]
#       The four coins' Binance spot 1-minute files (the cross-coin readings), the job coin's perp (binance-um), funding and
#       open-interest files, the inventory-found files of the job coin (FOUND: the preflight's JSON {"btcdom": [path, ...],
#       "cb": {COIN: path}, "book": {COIN: path}}, paths under raw/perp-ta-history/), the main run's metas of the 16 series
#       (models/oracle-heat/runs/<RUN>/<COIN>[-twinN]/meta.json) and HM1's stored pairs of the job coin
#       (models/oracle-heat/runs/<RUN>/league/pairs/pairs_<COIN>.csv.gz). Writes <DIR>/flags.txt (heat_hm2's data flags
#       without --twin and --main-meta, one per line), <DIR>/found.json and <DIR>/hm1_pairs.txt (the pairs file's path).
#       With OUTSIDE=true in the environment (an [hm2-outside] study; read only, nothing is written under raw/): also the OR-XD
#       data contract of the job coin, raw/outside/binance/<ASSET>/ (metrics, premium and mark minutes, the premium stamp test,
#       funding, the spot and perp aggTrades month files agg_spot/ and agg_perp/ WITHOUT the 2026 months, the bookdepth file,
#       the manifest) and raw/outside/binance/BTCDOM/idx1h.csv.gz, then 'python -m oracle.heat_outside cut' on both (every row
#       at or after 2026-01-01 00:00 UTC is dropped before anything reads it), into <DIR>/outside/<ASSET>/ and <DIR>/outside/BTCDOM/.
#       Writes <DIR>/outside_flags.txt (--outside-dir D [--outside-btcdom F], one per line; empty without OUTSIDE=true). The job stops
#       when metrics, premium, the stamp test, funding or either aggTrades folder is missing (a half-fed all-against-all study
#       would cost hours and answer less); a missing bookdepth or BTCDOM file only warns (the families then are left out, as
#       the contract says bookdepth starts in 2023).
#   oracle-hm2-data.sh outside <ASSET> <DIR>
#       Only the OUTSIDE=true part of 'series': the OR-XD contract of <ASSET> and BTCDOM's bars into <DIR>/outside/, cut, and
#       <DIR>/outside_flags.txt (also the way to test it).
#   oracle-hm2-data.sh cut <FILE> [LABEL]
#       The 13-digit check, the cut and the last-stamp assertion on one local file.
#   oracle-hm2-data.sh stamps <DRIVE NAME>
#       The first and last stamps of a Drive file, read from its two ends (no download), and the 13-digit check.
set -euo pipefail

LAB=${DRIVE_LAB:-deploy/drive_lab.sh}
ROOT=${DRIVE_ROOT:-gdrive:kalshi-bot-archive}
COINS=(BTC ETH SOL XRP)

die() { echo "::error::$*" >&2; exit 1; }
no_doge() { local x; for x in "$@"; do [[ "${x^^}" != *DOGE* ]] || die "NEVER DOGE: $x"; done; }
ms13() { [[ "$1" =~ ^[0-9]{13}(\.0*)?$ ]]; }
coin_ok() { [[ " ${COINS[*]} " == *" $1 "* ]] || die "asset '$1': BTC, ETH, SOL or XRP only (never DOGE)"; }
labels() { local tw C; for tw in 0 1 2 3; do for C in "${COINS[@]}"; do if [ "$tw" = 0 ]; then echo "$C"; else echo "$C-twin$tw"; fi; done; done; }

heat_end() {
  local e
  e=$(cd python && python3 -c "from oracle.heat import HEAT_END; print(HEAT_END)")
  [ "$e" = 1767225600000 ] || die "HEAT_END is $e, not 2026-01-01 00:00 UTC (1767225600000)"
  echo "$e"
}

LO=1546300800000                                  # heat_xdata.MS_LO, 2019-01-01 00:00 UTC (asserted in ms_lo)
ms_lo() {
  local e
  e=$(cd python && python3 -c "from oracle.heat_xdata import MS_LO; print(MS_LO)")
  [ "$e" = "$LO" ] || die "heat_xdata.MS_LO is $e, not 2019-01-01 00:00 UTC ($LO)"
}

cut_file() {
  local f=$1 l=${2:-$1} first last rows
  no_doge "$f"
  [ -s "$f" ] || die "$l: no file or an empty one ($f)"
  first=$(awk -F, 'NR == 2 { print $1; exit }' "$f"); first=${first%$'\r'}
  last=$(awk -F, 'NR > 1 && NF > 1 { x = $1 } END { print x }' "$f"); last=${last%$'\r'}
  { ms13 "$first" && ms13 "$last"; } || die "$l: the time column is not 13-digit milliseconds (first '$first', last '$last'): a file in seconds would keep its 2026 rows through the cut"
  # the cut: rows at or after HEAT_END (2026-01-01 UTC) are dropped here, before anything computes on them, and rows
  # before MS_LO (2019-01-01 UTC), which the strict loaders refuse
  awk -F, -v lo="$LO" -v e="$END" 'NR == 1 || (($1 + 0) >= lo && ($1 + 0) < e)' "$f" > "$f.cut"
  mv "$f.cut" "$f"
  first=$(awk -F, 'NR > 1 && NF > 1 { printf "%.0f", $1 + 0; exit }' "$f")
  last=$(awk -F, 'NR > 1 && NF > 1 { x = $1 + 0 } END { printf "%.0f", x }' "$f")
  rows=$(awk -F, 'NR > 1 && NF > 1 { n++ } END { print n + 0 }' "$f")
  [ "$rows" -gt 0 ] || die "$l: no row from 2019-01-01 to the cut"
  [ "$last" -lt "$END" ] || die "$l: a row at or after the cut is still in the file"
  [ "$first" -ge "$LO" ] || die "$l: a row before 2019-01-01 is still in the file"
  echo "$l: $(du -h "$f" | cut -f1), $rows rows, header '$(head -1 "$f" | cut -c1-80)', first $first, last $last (kept $LO to $END)"
}

outside_data() {          # OUTSIDE=true: the OR-XD contract of coin $1 and BTCDOM's hourly bars, cut at 2026-01-01 00:00 UTC (7:00 PM EST on Dec 31)
  local A=$1 O="$2/outside" f
  no_doge "$A" "$O"
  mkdir -p "$O/$A" "$O/BTCDOM"
  bash "$LAB" get "raw/outside/binance/$A" "$O/$A" --exclude '/agg_spot/2026-*' --exclude '/agg_perp/2026-*' \
    --include '/metrics.csv.gz' --include '/premium_1m.csv.gz' --include '/premium_stamp.json' --include '/mark_1m.csv.gz' \
    --include '/funding.csv.gz' --include '/bookdepth_1pct.csv.gz' --include '/manifest.json' \
    --include '/agg_spot/*.parquet' --include '/agg_perp/*.parquet' || die "no raw/outside/binance/$A on Drive: run the outside-fetch jobs first"
  for f in metrics.csv.gz premium_1m.csv.gz premium_stamp.json funding.csv.gz; do
    [ -s "$O/$A/$f" ] || die "raw/outside/binance/$A/$f is not on Drive (required for [hm2-outside])"
  done
  for f in agg_spot agg_perp; do
    [ -n "$(ls "$O/$A/$f" 2>/dev/null | head -1)" ] || die "raw/outside/binance/$A/$f/ has no month file (required for [hm2-outside])"
  done
  [ -s "$O/$A/bookdepth_1pct.csv.gz" ] || echo "::warning::no bookdepth_1pct.csv.gz for $A: BOOKP:Imb1 and BOOK:Imb are left out"
  if bash "$LAB" get "raw/outside/binance/BTCDOM" "$O/BTCDOM" --include '/idx1h.csv.gz' && [ -s "$O/BTCDOM/idx1h.csv.gz" ]; then :; else
    echo "::warning::no raw/outside/binance/BTCDOM/idx1h.csv.gz: IDX:BTCDOM1h and 4h are left out"; fi
  (cd python && python3 -m oracle.heat_outside cut --dir "$O/$A" && python3 -m oracle.heat_outside cut --dir "$O/BTCDOM")
  du -sh "$O" | cut -f1 | sed "s/^/outside data: /"
  for f in agg_spot agg_perp; do echo "$A/$f: $(ls "$O/$A/$f" | wc -l) month files, first $(ls "$O/$A/$f" | head -1), last $(ls "$O/$A/$f" | tail -1)"; done
  { echo --outside-dir; echo "$O/$A"; if [ -s "$O/BTCDOM/idx1h.csv.gz" ]; then echo --outside-btcdom; echo "$O/BTCDOM/idx1h.csv.gz"; fi; } > "$2/outside_flags.txt"
}

series() {
  local A=$1 RUN=$2 DIR=$3 FOUND=${4:-} H C p key d others=() inc=() found='{}'
  coin_ok "$A"
  [[ "$RUN" =~ ^[0-9]+$ ]] || die "run id '$RUN' is not a number"
  mkdir -p "$DIR"; DIR=$(cd "$DIR" && pwd); H="$DIR/hist"
  END=$(heat_end)
  for C in "${COINS[@]}"; do                      # the four coins' spot minutes (raw/perp-ta-history/<C>, read only)
    bash "$LAB" get "raw/perp-ta-history/$C" "$H" --include "/binance-1m/$C/1m.csv" || die "no $C spot 1-minute file on Drive"
    cut_file "$H/binance-1m/$C/1m.csv" "$C spot 1m"
    [ "$C" = "$A" ] || others+=("$C=$H/binance-1m/$C/1m.csv")
  done
  bash "$LAB" get "raw/perp-ta-history/$A" "$H" --include "/binance-um/$A/1m.csv" --include "/binance-funding/$A/funding.csv" \
    --include "/binance-oi/$A/oi.csv" || die "no $A perp, funding or open-interest file on Drive"
  cut_file "$H/binance-um/$A/1m.csv" "$A perp 1m (binance-um)"
  cut_file "$H/binance-funding/$A/funding.csv" "$A funding (calc_time)"
  cut_file "$H/binance-oi/$A/oi.csv" "$A open interest (create_time)"
  (cd python && python3 -m oracle.heat_xdata stamps --cut "$H/binance-um/$A/1m.csv" "$H/binance-funding/$A/funding.csv" "$H/binance-oi/$A/oi.csv")
  if [ -n "$FOUND" ] && [ "$FOUND" != null ] && [ "$FOUND" != '{}' ]; then   # inventory-found sources of this coin
    for key in btcdom cb book; do
      if [ "$key" = btcdom ]; then p=$(jq -r '(.btcdom // []) | if type == "array" then (.[0] // empty) else . end' <<< "$FOUND")
      else p=$(jq -r --arg k "$key" --arg a "$A" '(.[$k] // {})[$a] // empty' <<< "$FOUND"); fi
      [ -n "$p" ] || continue
      no_doge "$p"
      [[ "$p" =~ ^(BTC|ETH|SOL|XRP)/[A-Za-z0-9._/-]+$ && "$p" != *..* ]] || die "found $key: bad path '$p'"
      bash "$LAB" get "raw/perp-ta-history/${p%%/*}" "$DIR/found/${p%%/*}" --include "/${p#*/}" || die "found $key: $p is not on Drive"
      cut_file "$DIR/found/$p" "found $key ($p)"
      found=$(jq -c --arg k "$key" --arg v "$DIR/found/$p" '. + {($k): $v}' <<< "$found")
    done
  fi
  echo "$found" > "$DIR/found.json"
  for d in $(labels); do inc+=(--include "/$d/meta.json"); done    # the main run's metas (zone edges, price step)
  bash "$LAB" get "models/oracle-heat/runs/$RUN" "$DIR/metas" "${inc[@]}" || die "no metas of run $RUN on Drive"
  for d in $(labels); do [ -s "$DIR/metas/$d/meta.json" ] || die "no main-run meta $d/meta.json of run $RUN"; done
  bash "$LAB" get "models/oracle-heat/runs/$RUN/league/pairs" "$DIR/hm1" --include "/pairs_$A.csv.gz" || die "no HM1 pairs of run $RUN"
  [ -s "$DIR/hm1/pairs_$A.csv.gz" ] || die "no HM1 pairs file pairs_$A.csv.gz of run $RUN (provenance 'stored')"
  echo "$DIR/hm1/pairs_$A.csv.gz" > "$DIR/hm1_pairs.txt"
  local IFS=,
  printf '%s\n' --asset "$A" --csv "$H/binance-1m/$A/1m.csv" --others "${others[*]}" --perp "$H/binance-um/$A/1m.csv" \
    --fund "$H/binance-funding/$A/funding.csv" --oi "$H/binance-oi/$A/oi.csv" --cal "$PWD/python/oracle/calendars/macro_calendar_2020_2025.csv" \
    --dom "$PWD/research/btcd_fractal/data" --found "$DIR/found.json" --other-metas "$DIR/metas" > "$DIR/flags.txt"
  : > "$DIR/outside_flags.txt"
  if [ "${OUTSIDE:-}" = true ]; then outside_data "$A" "$DIR"; fi
  echo "data flags ($DIR/flags.txt):"; paste -sd' ' "$DIR/flags.txt"
  df -h "$DIR" | tail -1 | awk '{ print "free disk after the fetch: " $4 }'
}

stamps() {
  local n=$1 first last
  no_doge "$n"
  # awk reads its whole input (8 KiB): an early exit would close the pipe on rclone (SIGPIPE, status 141 under pipefail)
  first=$(rclone cat --head 8192 "$ROOT/$n" | awk -F, 'NR == 2 { x = $1 } END { print x }'); first=${first%$'\r'}
  last=$(rclone cat --tail 8192 "$ROOT/$n" | awk -F, 'NF > 1 { x = $1 } END { print x }'); last=${last%$'\r'}
  { ms13 "$first" && ms13 "$last"; } || die "$n: first '$first', last '$last': not 13-digit milliseconds"
  [ "${last%.*}" -ge "$LO" ] || die "$n: last stamp $last is before 2019-01-01: the cut would leave no row"
  [ "${first%.*}" -lt 1767225600000 ] || die "$n: first stamp $first is at or after 2026-01-01: the cut would leave no row"
  local note=''
  [ "${first%.*}" -ge "$LO" ] || note=' (rows before 2019-01-01 are dropped by the cut)'
  echo "$n: first $first ($(date -u -d "@$((${first%.*} / 1000))" '+%F %H:%M')), last $last ($(date -u -d "@$((${last%.*} / 1000))" '+%F %H:%M')) UTC$note"
}

case "${1:-}" in
  series) [ $# -ge 4 ] || die "usage: $0 series <ASSET> <RUN> <DIR> [FOUND]"; ms_lo; series "$2" "$3" "$4" "${5:-}" ;;
  outside) [ $# -ge 3 ] || die "usage: $0 outside <ASSET> <DIR>"; coin_ok "$2"; mkdir -p "$3"; outside_data "$2" "$(cd "$3" && pwd)" ;;
  cut) [ $# -ge 2 ] || die "usage: $0 cut <FILE> [LABEL]"; END=$(heat_end); ms_lo; cut_file "$2" "${3:-$2}" ;;
  stamps) [ $# -ge 2 ] || die "usage: $0 stamps <DRIVE NAME>"; stamps "$2" ;;
  *) sed -n '2,30p' "$0"; exit 1 ;;
esac
