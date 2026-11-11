"""Step 0 of the heat-map live test: do the Atlas heat maps ever call a different
direction from their own constant prior?

Reads ONLY model outputs (forecasts.jsonl: p, uniform, prior) from the two
existing Atlas forward-trial artifacts. No outcome, no Kalshi price, no coin
price is read or printed. Prints aggregates only.
"""
import json, sys, statistics as st
from collections import defaultdict
from pathlib import Path


def sign(x, eps=1e-10):
    return 0 if abs(x) < eps else (1 if x > 0 else -1)


def pct(a, b):
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


def main(paths):
    rows = []
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    g = defaultdict(list)
    for r in rows:
        g[(r["asset"], r["horizon"])].append(r)
    out = ["| Asset | Horizon | Forecasts | Map call differs from prior | Learned differs from uniform | Up calls | Median shift off prior (pts) | 90th pct shift | Max shift | Max top-class p |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    tot = defaultdict(int)
    for (asset, h), rs in sorted(g.items()):
        n = len(rs)
        differ = sum(sign(r["p"][0] - r["p"][2]) != sign(r["prior"][0] - r["prior"][2]) for r in rs)
        lu = sum(sign(r["p"][0] - r["p"][2]) != sign(r["uniform"][0] - r["uniform"][2]) for r in rs)
        up = sum(r["p"][0] > r["p"][2] for r in rs)
        shift = sorted(abs((r["p"][0] - r["p"][2]) - (r["prior"][0] - r["prior"][2])) * 100 for r in rs)
        top = max(max(r["p"]) for r in rs)
        out.append(f"| {asset} | {h}m | {n} | {differ} ({pct(differ, n)}) | {lu} ({pct(lu, n)}) | {pct(up, n)} | {st.median(shift):.2f} | {shift[int(0.9 * (n - 1))]:.2f} | {shift[-1]:.2f} | {top:.3f} |")
        tot["n"] += n; tot["d"] += differ; tot["lu"] += lu
    out.append(f"\nAll: {tot['n']} forecasts; map call differs from prior in {tot['d']} ({pct(tot['d'], tot['n'])}); learned differs from uniform in {tot['lu']} ({pct(tot['lu'], tot['n'])}).")
    out.append("Shift = |(p_up - p_down) - (prior_up - prior_down)| in percentage points. Model outputs only; no outcomes or prices read.")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1:])
