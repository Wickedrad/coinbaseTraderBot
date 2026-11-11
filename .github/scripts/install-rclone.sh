#!/usr/bin/env bash
# Installs rclone for the Drive jobs. apt first, one bounded try. When the runner cannot reach the Ubuntu mirrors (as from
# about 10:05 AM EST / 15:05 UTC on Nov 11 2026, when the nightly Drive archive failed on "Temporary failure resolving"),
# the same version Ubuntu 24.04 ships (1.60.1) comes from rclone's GitHub release page instead, and is installed only if it
# matches the SHA-256 pinned here (the value in rclone's own SHA256SUMS for that release). Does nothing when rclone is
# already on the runner.
set -euo pipefail

if command -v rclone >/dev/null; then exit 0; fi

if sudo timeout 120 apt-get install -y -qq rclone >/dev/null; then
  command -v rclone >/dev/null && exit 0
fi

echo "::warning::apt could not install rclone; installing the pinned rclone release file"
arch=$(dpkg --print-architecture)
if [ "$arch" != amd64 ]; then echo "::error::no pinned rclone release file for $arch"; exit 1; fi
V=v1.60.1
SUM=1c89af499e9d81c3ee2af8fa74a88414c22657c3df439f4d812e803bff5671cd
deb="${RUNNER_TEMP:-/tmp}/rclone-$V-linux-amd64.deb"
curl -fsSL --retry 3 --retry-delay 5 --max-time 300 -o "$deb" "https://github.com/rclone/rclone/releases/download/$V/rclone-$V-linux-amd64.deb"
echo "$SUM  $deb" | sha256sum -c --status - || { echo "::error::the rclone release file does not match the pinned SHA-256"; exit 1; }
# An apt run cut off by the timeout above can leave dpkg half-done; finish that before installing the file.
sudo dpkg --configure -a >/dev/null 2>&1 || true
sudo dpkg -i "$deb" >/dev/null
command -v rclone >/dev/null || { echo "::error::could not install rclone"; exit 1; }
rclone version | head -1
