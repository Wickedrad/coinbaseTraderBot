#!/usr/bin/env bash
# Rebuilds python/heat_reader/requirements.txt: every wheel the curve reader needs, pinned by version and SHA-256.
#
#   bash python/heat_reader/pin_requirements.sh            (uses python3 -m pip; PIP="/path/to/pip" to choose another)
#
# How: for each Python version and machine type the pins cover, `pip download` fetches the binary wheels (never a
# source package: the server must not compile, and the TA-Lib wheel carries its C library inside), then `pip hash`
# gives each file's SHA-256. deploy/heat_reader_install.sh installs with --require-hashes, so pip refuses a file
# whose hash is not listed here. To move a version: change it below, run this, run the tests, commit both files.
set -euo pipefail
cd "$(dirname "$0")"
PIP=${PIP:-python3 -m pip}

# Python versions and machine types covered. TA-Lib 0.8.3 has no bundled wheel for Python 3.10 or older.
PYTHONS="3.11 3.12 3.13 3.14"
ARCHES="x86_64 aarch64"
# name==version, then the environment marker ('' = every covered Python). numpy 2.5 needs Python 3.12, so 3.11 gets
# the last numpy that still supports it.
PINS=(
  'numpy==2.5.4|python_version >= "3.12"'
  'numpy==2.4.4|python_version == "3.11"'
  'pandas==3.1.1|'
  'TA-Lib==0.8.3|'
  'python-dateutil==4.0.0|'
  'tzdata==2026.6|'
)

W=$(mktemp -d)
trap 'rm -rf "$W"' EXIT
OUT=requirements.txt.new
{
  echo "# Hash-pinned requirements of the curve reader (python/heat_reader). Written by pin_requirements.sh: do not edit by hand."
  echo "# Covers CPython $(echo $PYTHONS | sed 's/ /, /g') on Linux $(echo $ARCHES | sed 's/ / and /g') (glibc 2.28 or newer). Binary wheels only:"
  echo "# nothing is compiled on the server, and the TA-Lib wheel bundles the TA-Lib C library."
  echo "# Install: pip install --require-hashes --only-binary=:all: -r python/heat_reader/requirements.txt"
  echo "# pandas needs numpy and python-dateutil; python-dateutil needs tzdata; TA-Lib needs numpy. Nothing else is installed."
} > "$OUT"

for pin in "${PINS[@]}"; do
  req=${pin%%|*}; marker=${pin#*|}
  d="$W/$(echo "$req" | tr -c 'A-Za-z0-9.\n' '_')"; mkdir -p "$d"
  for py in $PYTHONS; do
    # only the Pythons this pin's marker names
    case "$marker" in
      *'>= "3.12"'*) [ "$py" = 3.11 ] && continue ;;
      *'== "3.11"'*) [ "$py" = 3.11 ] || continue ;;
    esac
    for arch in $ARCHES; do
      $PIP download -q --disable-pip-version-check --no-deps --only-binary=:all: --python-version "$py" --implementation cp \
        --abi "cp${py/./}" --platform "manylinux_2_28_$arch" --platform "manylinux2014_$arch" -d "$d" "$req"
    done
  done
  {
    echo
    for f in $(ls "$d" | sort); do echo "#   $f"; done
    if [ -n "$marker" ]; then printf '%s ; %s' "$req" "$marker"; else printf '%s' "$req"; fi
    for f in $(ls "$d" | sort); do
      h=$($PIP hash --disable-pip-version-check -a sha256 "$d/$f" | sed -n 's/^--hash=sha256:\([0-9a-f]\{64\}\)$/\1/p')
      [ -n "$h" ] || { echo "no hash for $f" >&2; exit 1; }
      printf ' \\\n    --hash=sha256:%s' "$h"
    done
    echo
  } >> "$OUT"
done
mv "$OUT" requirements.txt
echo "wrote $(pwd)/requirements.txt: $(grep -c -- '--hash=sha256:' requirements.txt) wheel hashes"
