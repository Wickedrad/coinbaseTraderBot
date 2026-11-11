"""One health line per capture segment (counts only), printed as a commit-comment JSON body."""
import gzip, json, sys
from pathlib import Path

d, seg = Path(sys.argv[1]), sys.argv[2]
s = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
c = s.get("counts", {})
iso = lambda ms: __import__("datetime").datetime.fromtimestamp(ms / 1000, __import__("datetime").timezone.utc).strftime("%b %d %H:%M UTC") if ms else "?"
lines = [f"Heat shadow capture, segment {seg}: {iso(s.get('startedAt'))} to {iso(s.get('endedAt'))}",
         "", "```", json.dumps(c), json.dumps(s.get("coins", [])), "```"]
ev = d / "events.jsonl.gz"
if ev.exists():
    rows = [json.loads(l) for l in gzip.open(ev, "rt") if l.strip()]
    warm = [r for r in rows if r.get("kind") == "warm"]
    errs = [r for r in rows if r.get("kind", "").endswith(("error", "failed"))]
    if warm: lines += ["warm-up: " + json.dumps({k: warm[0].get(k) for k in ("ms", "clockOffset", "dominance", "coins")})]
    if errs: lines += [f"errors: {len(errs)}; first: " + json.dumps(errs[0])[:300]]
fc = d / "forecasts.jsonl.gz"
if fc.exists():
    rows = [json.loads(l) for l in gzip.open(fc, "rt") if l.strip()]
    by = {}
    for r in rows:
        k = f"{r['asset']}{r['horizon']}"; b = by.setdefault(k, [0, 0, 99, 0]); b[0] += 1; b[1] += r["p"][0] > r["p"][2]; b[2] = min(b[2], r["axes"]); b[3] = max(b[3], r["curves"])
    lines += ["calls (n, up calls, fewest readings, most curves): " + json.dumps(by)]
print(json.dumps({"body": "\n".join(lines)}))
