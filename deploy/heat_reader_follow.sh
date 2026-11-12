#!/usr/bin/env bash
# Makes the heat curve reader (docs/HEAT_READER.md) follow the release that ~/bot/current now points at. Run by
# deploy/activate.sh once the bot is up and its dashboard answers, and by deploy/rollback.sh after the switch, with
# that release's deploy folder:
#
#   bash deploy/heat_reader_follow.sh <release>/deploy
#
#  - The release ships deploy/heat_reader_install.sh: runs it. It stops the reader when HEAT_LANE is not true in
#    ~/bot/bot.env; with HEAT_LANE=true it builds the reader's venv (the first time, pip takes minutes), checks the
#    release ships the reader, the oracle engine and the packs, and (re)starts heat-reader.service. Bounded to
#    HEAT_READER_INSTALL_TIMEOUT seconds (default 900 = 15 min; the deploy's ssh step allows 60 min in all).
#    It runs with oom_score_adj 1000: the pip build and its import checks come right after the bot's restart, on a
#    1.9 GB server without swap, and if memory runs out the kernel must kill them, never the bot (which has no
#    OOMScoreAdjust of its own). The reader's unit, started by systemd, keeps its own OOMScoreAdjust.
#    When the installer fails or is cut off, heat-reader.service (if installed) is stopped and disabled: the installer
#    exits at its checks before it touches the unit, so a reader started from an earlier release would otherwise keep
#    running that release's code and packs beside this bot, and a reboot could start a half-built venv. Its next
#    successful run enables it again.
#  - It does not, and heat-reader.service is installed: stops and disables the reader, which runs from ~/bot/current
#    and so cannot run from a release without it.
#  - Otherwise: one line, nothing done.
# Always exits 0. The reader never fails a deploy or a rollback and never rolls the bot back: without it the bot's
# heat lane opens nothing, everything else runs as before.
set -uo pipefail
D="${1:?usage: heat_reader_follow.sh <release>/deploy}"
INSTALL="$D/heat_reader_install.sh"
UNIT_FILE="${HEAT_READER_UNIT_DIR:-/etc/systemd/system}/heat-reader.service"   # the folder is a setting only for the tests
LIMIT="${HEAT_READER_INSTALL_TIMEOUT:-900}"
if [ -f "$INSTALL" ]; then
  rc=0
  # timeout signals the installer's whole process group (pip with it); a run cut short leaves no venv stamp, so the
  # next run builds the venv again from the start. The subshell raises only the installer's oom_score_adj (raising it
  # needs no privilege; pip and everything else the installer starts inherits it).
  ( { echo 1000 > /proc/self/oom_score_adj; } 2>/dev/null || true; exec timeout -k 30 "$LIMIT" bash "$INSTALL" ) || rc=$?
  off=""
  if [ "$rc" -ne 0 ] && [ -f "$UNIT_FILE" ]; then
    sudo systemctl disable --now heat-reader >/dev/null 2>&1 || true
    off=" heat-reader.service is stopped and disabled until an install succeeds."
  fi
  case "$rc" in
    0) ;;
    124|137) echo "heat reader: NOT running: heat_reader_install.sh did not finish within $LIMIT s (exit $rc).$off The bot is not affected; to finish the first venv build run: bash ~/bot/current/deploy/heat_reader_install.sh" ;;
    *) echo "heat reader: NOT running: heat_reader_install.sh exited $rc (the heat-reader lines above say why).$off The bot is not affected." ;;
  esac
elif [ -f "$UNIT_FILE" ]; then
  sudo systemctl disable --now heat-reader >/dev/null 2>&1 || true
  echo "heat reader: $D has no heat_reader_install.sh: the reader is stopped and disabled (this release does not carry it)"
else
  echo "heat reader: $D has no heat_reader_install.sh: nothing to install"
fi
exit 0
