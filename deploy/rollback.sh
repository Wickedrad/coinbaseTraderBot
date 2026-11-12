#!/usr/bin/env bash
# Swap back to the previous release (the bot first, then the heat curve reader).
set -euo pipefail
[ -L ~/bot/previous ] || { echo "no previous release"; exit 1; }
# This script's own folder, symlinks resolved before the switch (run as ~/bot/current/deploy/rollback.sh, that path
# points at the other release afterwards).
HERE="$(cd "$(dirname "$0")" && pwd -P)"
PREV="$(readlink ~/bot/previous)"
ln -sfn "$(readlink ~/bot/current)" ~/bot/previous
ln -sfn "$PREV" ~/bot/current
sudo systemctl restart kalshi-bot
echo "rolled back to $PREV"
# The heat curve reader follows the release now current: that release's deploy/heat_reader_install.sh when it has
# one, else the reader is stopped and disabled if installed. Never fails the rollback.
bash "$HERE/heat_reader_follow.sh" "$PREV/deploy" || echo "heat reader: NOT running: heat_reader_follow.sh exited $? (the bot is not affected)"
