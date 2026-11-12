#!/usr/bin/env python3
"""Exit study summary of a tennis TA sweep run (information only; nothing here judges or cuts an arm).

Reads a run's shard files (out/a-s<stage>-<k>-<j>.json.gz, as research/tennisTaSweep.ts writes them) and prints, per
F-arm (config x fill model), the episodes by ENTRY leg: the underdog leg (the direction-found hot spot) and the favourite
leg separately, because an exit setting moves the favourite leg's entries through the caps and the end-entry block, so
an arm's total is not an exit effect. For the underdog leg: entries, wins (realized net > 0), net after fees, net per
entry, money deployed (first fill price x most contracts held), net per $100 deployed, median minutes held, settlement
breaches, and the three most common exit legs. The anchor (--anchor, default A|s2|hs1prod|F1) is compared by
difference in net per entry.

  python3 research/tennis_ta_exit_summary.py shards/*.json.gz --run 43173887974 --out summary.md
"""
import argparse
import gzip
import json
import os
import sys
from collections import Counter

DEFAULT_EP_COLS = ['m', 'k', 't', 'leg', 'px', 'n', 'ph', 'sig', 'x', 'hold', 'pnl', 'br']


def episodes(path):
    """{run id: {'fill', 'window', 'placebo', 'eps': [dict]}} of one shard file."""
    with gzip.open(path, 'rt') as fh:
        d = json.load(fh)
    meta, runs = d.get('meta') or {}, d.get('runs')
    if not isinstance(runs, list):
        raise ValueError(f'{os.path.basename(path)}: not a shard file (runs expected)')
    cols = meta.get('episodeCols') or DEFAULT_EP_COLS
    out = {}
    for r in runs:
        eps = [dict(zip(cols, row)) for row in (r.get('episodes') or [])]
        out[r['id']] = {'fill': r.get('fill'), 'window': r.get('window') is True, 'placebo': r.get('placebo'), 'eps': eps}
    return meta, out


def leg_group(leg):
    leg = str(leg or '')
    if leg.startswith('underdog'):
        return 'underdog'
    if leg.startswith('fav'):
        return 'fav'
    return 'other'


def stats(eps):
    n = len(eps)
    net = sum(float(e.get('pnl') or 0) for e in eps)
    dep = sum(float(e.get('px') or 0) * float(e.get('n') or 0) for e in eps)
    wins = sum(1 for e in eps if float(e.get('pnl') or 0) > 0)
    holds = sorted(float(e.get('hold') or 0) for e in eps)
    med = holds[len(holds) // 2] / 60 if holds else 0.0
    br = sum(1 for e in eps if e.get('br'))
    xs = Counter(str(e.get('x') or '') for e in eps).most_common(3)
    return {'n': n, 'net': net, 'per': net / n if n else 0.0, 'dep': dep, 'per100': 100 * net / dep if dep else 0.0,
            'win': wins / n if n else 0.0, 'med_min': med, 'br': br, 'xs': xs}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('shards', nargs='+')
    ap.add_argument('--run', default='')
    ap.add_argument('--anchor', default='A|s2|hs1prod|F1')
    ap.add_argument('--out', default='')
    a = ap.parse_args(argv)
    arms, metas = {}, []
    for p in sorted(a.shards):
        meta, runs = episodes(p)
        metas.append(meta)
        for rid, r in runs.items():
            if r['window'] or r['placebo']:
                continue
            arm = arms.setdefault(rid, {'fill': r['fill'], 'eps': []})
            arm['eps'] += r['eps']
    if not arms:
        print('no F-arm episodes in these shards', file=sys.stderr)
        return 1
    rows = []
    for rid, arm in arms.items():
        g = {'underdog': [], 'fav': [], 'other': []}
        for e in arm['eps']:
            g[leg_group(e.get('leg'))].append(e)
        rows.append((rid, arm['fill'], stats(g['underdog']), stats(g['fav']), stats(arm['eps'])))
    anchor = next((r for r in rows if r[0] == a.anchor), None)
    rows.sort(key=lambda r: -r[2]['per'])
    days = sorted({m.get('from') for m in metas if m.get('from')} | {m.get('to') for m in metas if m.get('to')})
    lines = [f"## Exit study summary{(' of run ' + a.run) if a.run else ''} (information only)", '',
             f"{len(a.shards)} shard file(s), {len(arms)} F-arm(s), shard days {days[0] if days else '?'} to {days[-1] if days else '?'}. "
             'Episodes by ENTRY leg; net is realized after fees (settlement included); deployed = first fill price x most contracts held. '
             'Sorted by underdog net per entry.' + (f" Anchor {a.anchor}: underdog {anchor[2]['n']} entries, ${anchor[2]['net']:,.2f}, ${anchor[2]['per']:+.3f} an entry." if anchor else ''),
             '',
             '| arm | fill | ud entries | ud win % | ud net | ud $/entry | vs anchor | ud deployed | ud net per $100 | ud med min held | ud breaches | ud top exits | fav entries | fav net | all net |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for rid, fill, u, f, t in rows:
        vs = f"{u['per'] - anchor[2]['per']:+.3f}" if anchor else '-'
        xs = ', '.join(f'{x} {c}' for x, c in u['xs'])
        lines.append(f"| {rid.replace('|', chr(92) + '|')} | {fill} | {u['n']} | {100 * u['win']:.1f} | ${u['net']:,.2f} | {u['per']:+.3f} | {vs} | ${u['dep']:,.0f} | "
                     f"{u['per100']:+.2f} | {u['med_min']:.1f} | {u['br']} | {xs} | {f['n']} | ${f['net']:,.2f} | ${t['net']:,.2f} |")
    text = '\n'.join(lines) + '\n'
    if a.out:
        with open(a.out, 'w') as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
