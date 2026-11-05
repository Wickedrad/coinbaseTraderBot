#!/usr/bin/env bash
# Build, check and upload the trial-registry shard of one all-pairs run (registry v1 of the meta plan thread):
# gdrive:kalshi-bot-archive/registry/shards/all-pairs/<run>.jsonl, one row per config x gated arm with $ per day.
#   bash allpairs/registry_shard.sh <run id> <results dir> <code sha> <run url> [flag ...]     (from python/)
# The rows are checked with the registry's own validator and make_id (research/registry.py: main once merged, else
# the meta plan's branch); without it no shard is written (the run itself does not fail).
set -euo pipefail
RUN=$1; RES=$2; SHA=$3; URL=$4; shift 4
R="${DRIVE_ROOT:-gdrive:kalshi-bot-archive}"
T="${RUNNER_TEMP:-/tmp}/registry"
mkdir -p "$T/prior" "$T/out"
if [ ! -s "$T/registry.py" ]; then
  for ref in main claude/project-thread-79ntof; do
    if git fetch -q --depth=1 origin "$ref" 2>/dev/null && git show FETCH_HEAD:research/registry.py > "$T/registry.py" 2>/dev/null; then break; fi
    rm -f "$T/registry.py"
  done
  # Earlier shards of this thread: a run without its own base configuration pairs with a control run's row.
  rclone copy "$R/registry/shards/all-pairs" "$T/prior" 2>/dev/null || true
fi
[ -s "$T/registry.py" ] || { echo "registry: research/registry.py not found; no shard for run $RUN"; exit 0; }
flags=()
for f in "$@"; do flags+=(--flag "$f"); done
python -W ignore -m allpairs.registry_rows --results "$RES" --run-id "$RUN" --code-sha "$SHA" --run-url "$URL" \
  --prior "$T/prior" "${flags[@]}" --out "$T/out/$RUN.jsonl"
python - "$T/registry.py" <<'EOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location('registry', sys.argv[1])
reg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reg)
from allpairs.registry_rows import make_id
a = ('all-pairs', 'all-pairs-policy', 'x', 'sha', ['2026-06-20', '2026-06-19'])
assert make_id(*a) == reg.make_id(*a), 'make_id differs from the registry'
EOF
python "$T/registry.py" validate "$T/out/$RUN.jsonl"
if [ -s "$T/out/$RUN.jsonl" ]; then
  rclone copyto "$T/out/$RUN.jsonl" "$R/registry/shards/all-pairs/$RUN.jsonl"
  cp "$T/out/$RUN.jsonl" "$T/prior/"
  echo "registry: $(wc -l < "$T/out/$RUN.jsonl") rows -> registry/shards/all-pairs/$RUN.jsonl"
else
  echo "registry: run $RUN has no gated real-data arm"
fi
