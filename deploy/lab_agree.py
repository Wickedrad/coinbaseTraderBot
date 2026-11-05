"""Does the exit lab (deploy/cross_study.py) agree with the TS replay (research/replayCheck.ts) on the same stretch?

usage: python3 deploy/lab_agree.py <replay-check json (--out)> <cross_study LAB_HOURLY json> [window hours, default 6]

Project convention for a lab that may be read for levels, not only ranks: per window, the lab's contracts within +-15%
of the replay's, and window P&L correlation >= 0.8. Both sides count contracts filled (entries and sales; settlements fill
nothing) by UTC hour of the fill, and realized P&L by UTC hour of the close or settlement. The replay chooses its own
entries; the lab takes paper's audited entries at the $10-$20 band, so a miss on contracts is an entry-set difference
and a miss on P&L with matched contracts is an exit or fill difference. Paper's own record is shown as a third column.
"""
import json, math, sys


def corr(a, b):
    n = len(a)
    if n < 3: return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0: return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def main():
    rc = json.load(open(sys.argv[1])); lab = json.load(open(sys.argv[2]))
    W = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    lo, hi = rc['from'][:13], rc['to'][:13]
    print(f"stretch {rc['from']} to {rc['to']} UTC; windows of {W} h (UTC hour blocks)")
    rep, pap = rc['replay'], rc['paper']
    print(f"replay total: {sum(rep['contractsByHour'].values()):.0f} contracts, P&L {rep['pnl']:+.2f}; paper: {sum(pap['contractsByHour'].values()):.0f} contracts, P&L {pap['pnl']:+.2f}")

    def block(h):  # 'YYYY-MM-DDTHH' -> its W-hour block label
        hh = int(h[11:13]) // W * W
        return f"{h[:11]}{hh:02d}"

    for tag in sorted(lab):
        L = {h: v for h, v in lab[tag].items() if lo <= h <= hi}
        keys = sorted({block(h) for h in list(L) + [h for h in rep['contractsByHour'] if lo <= h <= hi] + [h for h in rep['byHour'] if lo <= h <= hi]})
        agg = {k: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for k in keys}  # lab c, lab $, replay c, replay $, paper c, paper $
        for h, (c, x) in L.items(): agg[block(h)][0] += c; agg[block(h)][1] += x
        for src, i in ((rep, 2), (pap, 4)):
            for h, c in src['contractsByHour'].items():
                if lo <= h <= hi and block(h) in agg: agg[block(h)][i] += c
            for h, x in src['byHour'].items():
                if lo <= h <= hi and block(h) in agg: agg[block(h)][i + 1] += x
        print(f"\n== lab row {tag}")
        print('  window (UTC)     lab c  replay c  ratio   paper c |    lab $  replay $   paper $')
        inb = 0
        for k in keys:
            a = agg[k]; r = a[0] / a[2] if a[2] > 0 else None
            ok = r is not None and abs(r - 1) <= 0.15; inb += ok
            print(f"  {k.replace('T', ' ')}h  {a[0]:7.0f}  {a[2]:8.0f}  {('%.2f' % r) if r is not None else '  n/a'}{' *' if ok else '  '} {a[4]:7.0f} | {a[1]:+8.2f}  {a[3]:+8.2f}  {a[5]:+8.2f}")
        tl, tr = sum(agg[k][0] for k in keys), sum(agg[k][2] for k in keys)
        cp = corr([agg[k][1] for k in keys], [agg[k][3] for k in keys])
        cpp = corr([agg[k][1] for k in keys], [agg[k][5] for k in keys])
        crp = corr([agg[k][3] for k in keys], [agg[k][5] for k in keys])
        f = lambda v: 'n/a' if v is None else f'{v:+.2f}'
        print(f"  total contracts lab {tl:.0f} vs replay {tr:.0f} ({(tl / tr if tr else float('nan')):.2f}x); windows within +-15%: {inb} of {len(keys)}")
        print(f"  window P&L corr: lab vs replay {f(cp)}, lab vs paper {f(cpp)}, replay vs paper {f(crp)}; P&L lab {sum(agg[k][1] for k in keys):+.2f} vs replay {sum(agg[k][3] for k in keys):+.2f}")
        level = tr > 0 and abs(tl / tr - 1) <= 0.15 and inb >= 0.8 * len(keys) and cp is not None and cp >= 0.8
        print(f"  VERDICT {tag}: {'levels (contracts within 15% and window P&L corr >= 0.8)' if level else 'rank-only (the lab misses the replay on contracts or window P&L)'}")


if __name__ == '__main__':
    main()
