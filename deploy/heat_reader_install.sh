#!/usr/bin/env bash
# Installs the curve reader beside the bot. Run on the server from a release, after every deploy and after
# changing HEAT_LANE in ~/bot/bot.env:
#
#   bash ~/bot/current/deploy/heat_reader_install.sh
#
# Idempotent: a second run with nothing changed only restarts the reader. What it does:
#  - HEAT_LANE is not true in ~/bot/bot.env: stops and disables heat-reader.service, installs nothing, exits 0.
#  - HEAT_LANE=true:
#     1. builds the reader's own Python venv, ~/bot/.venv-heat-reader, from the HASH-PINNED requirements
#        (python/heat_reader/requirements.txt: binary wheels only, pip refuses a file whose SHA-256 is not listed,
#        nothing is compiled, the TA-Lib wheel carries its C library). Rebuilt only when that file or the Python
#        version changes. Needs Python 3.11 to 3.14 with the venv module.
#     2. copies the traded pack and the coin metas the release ships into ~/bot/data/heat_reader/tables (they stay
#        there across releases),
#     3. writes ~/bot/heat-reader.env from the reader's settings found in bot.env (a fixed list of HEAT_* names, no
#        secret among them: the reader's unit never reads bot.env itself),
#     4. installs or refreshes /etc/systemd/system/heat-reader.service, enables it and restarts it.
# It never touches the bot's service (kalshi-bot) and never edits bot.env.
# Exit code: 0 = the reader is in the state bot.env asks for; 1 = HEAT_LANE=true and it could not be installed or
# started (the bot is not affected: without a fresh calls file the heat lane opens nothing).
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
REL="$(dirname "$DIR")"
BOT=~/bot
ENV="$BOT/bot.env"
VENV="$BOT/.venv-heat-reader"
TABLES="$BOT/data/heat_reader/tables"
READER_ENV="$BOT/heat-reader.env"
UNIT=heat-reader
UNIT_FILE="${HEAT_READER_UNIT_DIR:-/etc/systemd/system}/$UNIT.service"      # the folder is a setting only so the script can be tested
REQ="$REL/python/heat_reader/requirements.txt"
say() { echo "heat-reader: $*"; }
# The last value of a name in bot.env, quotes removed (as deploy/https.sh reads it).
val() { grep -E "^$1=" "$ENV" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"; }
have_unit() { [ -f "$UNIT_FILE" ]; }

lane="$(val HEAT_LANE | tr '[:upper:]' '[:lower:]')"
if [ "$lane" != "true" ] && [ "$lane" != "1" ]; then
  if have_unit; then
    sudo systemctl disable --now "$UNIT" >/dev/null 2>&1 || true
    say "HEAT_LANE is not true in $ENV: the reader is stopped and disabled"
  else
    say "HEAT_LANE is not true in $ENV: nothing installed"
  fi
  exit 0
fi

die() { say "$1"; say "NOT running. The bot is not affected: without a fresh calls file the heat lane opens nothing."; exit 1; }

# ---- the calls file must be where both sides find it ----
# The bot and the reader run from different folders, and the reader may write only under ~/bot/data.
calls="$(val HEAT_CALLS_FILE)"
case "$calls" in
  '') ;;
  "$BOT/data/"*) ;;
  *) die "HEAT_CALLS_FILE in $ENV must be a full path under $BOT/data/ (or left out: the default is $BOT/data/heat_calls.json)" ;;
esac

# ---- what the release must ship ----
[ -f "$REQ" ] && [ -f "$REL/python/heat_reader/cli.py" ] || die "this release does not ship python/heat_reader (see docs/HEAT_READER.md, 'What the deploy needs')"
[ -f "$REL/python/oracle/heat_live.py" ] || die "this release does not ship python/oracle (the engine the reader runs)"

# ---- Python 3.11 to 3.14 with venv ----
PY=""
for c in python3 python3.12 python3.13 python3.11 python3.14; do
  p="$(command -v "$c" 2>/dev/null)" || continue
  if "$p" -c 'import sys, venv, ensurepip; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)' 2>/dev/null; then PY="$p"; break; fi
done
[ -n "$PY" ] || die "needs Python 3.11 to 3.14 with the venv module (this server: $(python3 --version 2>&1)). On Ubuntu 22.04: sudo apt-get install -y python3.11 python3.11-venv; on 24.04: sudo apt-get install -y python3-venv"
PYV="$("$PY" -c 'import platform; print(platform.python_version(), platform.machine())')"

# ---- venv from the hash-pinned requirements (rebuilt only when the pins or the Python change) ----
stamp="$(sha256sum "$REQ" | cut -d' ' -f1) $PYV"
if [ "$(cat "$VENV/.heat-reader-stamp" 2>/dev/null)" != "$stamp" ] || ! "$VENV/bin/python" -c 'import talib, numpy, pandas' 2>/dev/null; then
  say "building $VENV (Python $PYV, pins $(echo "$stamp" | cut -c1-12))"
  have_unit && sudo systemctl stop "$UNIT" >/dev/null 2>&1
  rm -rf "$VENV"
  "$PY" -m venv "$VENV" || die "python -m venv failed"
  nice -n 10 "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --no-cache-dir --require-hashes --only-binary=:all: -r "$REQ" \
    || { rm -rf "$VENV"; die "pip could not install the pinned wheels (no wheel for this Python or machine, a hash that does not match, or no network)"; }
  "$VENV/bin/python" -c 'import talib, numpy, pandas; print("heat-reader: TA-Lib", talib.__version__, "numpy", numpy.__version__, "pandas", pandas.__version__)' \
    || { rm -rf "$VENV"; die "the installed wheels do not load"; }
  echo "$stamp" > "$VENV/.heat-reader-stamp"
else
  say "venv unchanged ($VENV, Python $PYV)"
fi
# Compiled once here: the service runs with the home folder read-only and could not keep its own.
"$VENV/bin/python" -m compileall -q "$REL/python/heat_reader" "$REL/python/oracle" >/dev/null 2>&1 || true

# ---- the pack and the metas ----
mkdir -p "$TABLES"
put() { # put <source> <name in the tables folder>: copied only when different, swapped in whole
  [ -f "$1" ] || return 1
  cmp -s "$1" "$TABLES/$2" 2>/dev/null && return 0
  cp "$1" "$TABLES/.$2.new" && mv "$TABLES/.$2.new" "$TABLES/$2" && say "tables: $2 from $(basename "$(dirname "$1")")/$(basename "$1")"
}
SHIPPED="$REL/research/oracle_heat/latest"
put "$SHIPPED/traded_pack.json" traded_pack.json || true
put "$SHIPPED/live_meta.json" live_meta.json || true
# No pack from the oracle run in this release and none installed yet: the first pack, which ships with the reader.
[ -f "$TABLES/traded_pack.json" ] || put "$REL/python/heat_reader/fixtures/traded_pack.first.json" traded_pack.json || true
[ -f "$TABLES/traded_pack.json" ] || say "WARNING no traded pack in $TABLES: every coin will be written as not ok"
if [ ! -f "$TABLES/live_meta.json" ] && ! ls "$TABLES"/*/meta.json >/dev/null 2>&1; then
  say "WARNING no coin meta in $TABLES (live_meta.json, or <COIN>/meta.json from Drive models/oracle-heat/runs/<run>/): every coin will be written as not ok until it is there"
fi

# ---- the reader's settings: the HEAT_* names it reads, copied out of bot.env (no secret is among them) ----
tmp="$(mktemp "$READER_ENV.XXXX")"
echo "# Written by deploy/heat_reader_install.sh from $ENV. Edit bot.env, then run that script again." > "$tmp"
for name in HEAT_CALLS_FILE HEAT_ASSETS HEAT_WINDOW_BARS HEAT_READER_DIR HEAT_PACK_FILE HEAT_META_DIR HEAT_ORACLE_PATH HEAT_RUN HEAT_BINANCE_API; do
  v="$(val "$name")"
  [ -n "$v" ] && printf '%s=%s\n' "$name" "$v" >> "$tmp"
done
chmod 644 "$tmp"
mv "$tmp" "$READER_ENV"

# ---- the unit, with this server's user and home ----
unit="$(mktemp)"
sed -e "s#/home/ubuntu#$HOME#g" -e "s#^User=ubuntu#User=$(id -un)#" "$DIR/heat-reader.service" > "$unit"
if ! cmp -s "$unit" "$UNIT_FILE" 2>/dev/null; then
  sudo cp "$unit" "$UNIT_FILE" && sudo systemctl daemon-reload || { rm -f "$unit"; die "could not install $UNIT_FILE (needs passwordless sudo, as the bot's unit does)"; }
  say "unit installed: $UNIT_FILE"
fi
rm -f "$unit"
sudo systemctl enable "$UNIT" >/dev/null 2>&1 || true
# A restart every time: the release under ~/bot/current may be new, and the minute cache makes a restart cheap.
sudo systemctl restart "$UNIT" || die "systemctl restart $UNIT failed"
sleep 5
if ! systemctl is-active --quiet "$UNIT"; then
  sudo journalctl -u "$UNIT" -n 30 --no-pager 2>&1 || true
  die "the reader did not stay up"
fi
say "running ($(systemctl show -p MainPID --value "$UNIT" 2>/dev/null | sed 's/^/pid /')). The first start downloads the minute window (a few minutes); then one file a minute: ${calls:-$BOT/data/heat_calls.json}"
say "look: sudo journalctl -u $UNIT -n 20 --no-pager; cat $BOT/data/heat_reader/status.json"
