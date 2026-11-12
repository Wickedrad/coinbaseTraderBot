#!/usr/bin/env python3
"""Raw-tape audit of a tennis TA sweep run's underdog trades (information only; nothing here judges or cuts an arm).

Checks the sim's underdog episodes against Kalshi's own trade tape (the history the sweep replays:
<hist>/<SERIES>/trades/<close day>.jsonl, one line per market {ticker, trades: [[ts ms, YES price, contracts, taker side
(1 = bought YES, 0 = bought NO)]]}), so a reader can see whether the sim's entries and losses are what the market did:

1. Entry vs tape: the sim's first fill price against the last print at or before the entry (gap in cents).
2. After the entry, until the episode's exit (and until the match's close): the highest print, the lowest print, and
   whether any print reached the entry price + 1c / + 2c / + 3c (a profitable exit was on the tape), with the minutes to
   the first such print.
3. The losers by exit leg: how many never saw a print above the entry + 2c before the exit (the call was wrong from the
   start) and how many did (an exit was on the tape and the rules did not take it).
4. The worst trades, each with its tape path (times in New York time and UTC).

Episodes come from the run's shard files (out/a-s<stage>-<k>-<j>.json.gz). Prices are YES prices of the market held.

  python3 research/tennis_ta_loser_tape.py shards/*.json.gz --hist data/tennis/kalshi --arms 'A|s2|hs1prod|F1' --out tape.md
"""
import argparse
import bisect
import datetime as dt
import gzip
import json
import os
import statistics
import sys
from collections import defaultdict

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo('America/New_York')
except Exception:  # pragma: no cover
    NY = None

DEFAULT_EP_COLS = ['m', 'k', 't', 'leg', 'px', 'n', 'ph', 'sig', 'x', 'hold', 'pnl', 'br']
STEPS = (0.01, 0.02, 0.03)


def when(ms):
    u = dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
    if NY is None:
        return u.strftime('%b %d %H:%M UTC')
    e = u.astimezone(NY)
    return f"{e.strftime('%b %d %I:%M %p').replace(' 0', ' ')} {e.tzname()} / {u.strftime('%H:%M')} UTC"


def read_shards(paths, arms):
    """[(arm id, episode dict with ticker, close, result)] for the underdog leg of the chosen arms."""
    out = []
    for p in sorted(paths):
        with gzip.open(p, 'rt') as fh:
            d = json.load(fh)
        meta, runs = d.get('meta') or {}, d.get('runs')
        if not isinstance(runs, list):
            raise ValueError(f'{os.path.basename(p)}: not a shard file (runs expected)')
        cols = meta.get('episodeCols') or DEFAULT_EP_COLS
        ml = d.get('matchList') or []
        for r in runs:
            if r.get('window') is True or (arms and r['id'] not in arms):
                continue
            for row in r.get('episodes') or []:
                e = dict(zip(cols, row))
                if not str(e.get('leg') or '').startswith('underdog'):
                    continue
                mi, k = e.get('m'), e.get('k')
                if not (isinstance(mi, int) and 0 <= mi < len(ml)):
                    continue
                m = ml[mi]
                tickers = m.get('tickers') or []
                if not (isinstance(k, int) and 0 <= k < len(tickers)):
                    continue
                ra = m.get('resultA')
                e['ticker'] = tickers[k]
                e['series'] = m.get('series') or tickers[k].split('-')[0]
                e['close'] = m.get('close')
                e['start'], e['start_pub'] = m.get('start'), m.get('startPublished') is True
                e['won'] = None if ra is None else (ra == 1) == (k == 0)
                out.append((r['id'], e))
    return out


def read_tapes(hist, need):
    """{ticker: sorted [(ts, price, count, side)]} for the tickers needed, streamed from every trades file."""
    tapes = {}
    for series in sorted({s for s, _ in need}):
        tdir = os.path.join(hist, series, 'trades')
        if not os.path.isdir(tdir):
            continue
        want = {t for s, t in need if s == series}
        for f in sorted(os.listdir(tdir)):
            if not f.endswith('.jsonl'):
                continue
            with open(os.path.join(tdir, f)) as fh:
                for line in fh:
                    if not want:
                        break
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    t = rec.get('ticker')
                    if t in want:
                        tapes[t] = sorted((int(x[0]), float(x[1]), float(x[2]), int(x[3])) for x in rec.get('trades') or [])
                        want.discard(t)
    return tapes


def audit(e, tape):
    """Tape facts for one episode, or None with no tape."""
    if not tape:
        return None
    ts = [x[0] for x in tape]
    t0, px = int(e['t']), float(e['px'])
    t_exit = t0 + int(round(float(e.get('hold') or 0) * 1000))
    close = int(e['close']) if e.get('close') else (tape[-1][0] + 1)
    i0 = bisect.bisect_right(ts, t0)
    before = tape[i0 - 1] if i0 > 0 else None
    upto_exit = tape[i0:bisect.bisect_right(ts, t_exit)]
    upto_close = tape[i0:bisect.bisect_right(ts, close)]
    res = {'gap': None if before is None else round((px - before[1]) * 100, 2), 'last_before': before,
           'n_after': len(upto_close), 'exit_ts': t_exit,
           # Minutes from the entry to the market's last print (about when the match ended) and from the published start.
           'to_end': (tape[-1][0] - t0) / 60000,
           'from_start': None if not e.get('start') else (t0 - int(e['start'])) / 60000}
    for tag, seg in (('exit', upto_exit), ('close', upto_close)):
        res[f'hi_{tag}'] = max((x[1] for x in seg), default=None)
        res[f'lo_{tag}'] = min((x[1] for x in seg), default=None)
        for s in STEPS:
            hit = next((x for x in seg if x[1] >= px + s - 1e-9), None)
            res[f'up{int(round(s * 100))}_{tag}'] = None if hit is None else (hit[0] - t0) / 60000
        # A bid that someone sold into (a NO-taker print) at the entry + 2c or more: a taker exit could have sold there.
        bid = next((x for x in seg if x[3] == 0 and x[1] >= px + 0.02 - 1e-9), None)
        res[f'bid2_{tag}'] = None if bid is None else (bid[0] - t0) / 60000
    return res


def pct(a, b):
    return f'{100 * a / b:.0f}%' if b else '-'


def med(xs):
    return f'{statistics.median(xs):.1f}' if xs else '-'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('shards', nargs='+')
    ap.add_argument('--hist', required=True, help='history root holding <SERIES>/trades/*.jsonl')
    ap.add_argument('--arms', default='', help="arm ids, comma separated (empty = every non-window arm)")
    ap.add_argument('--run', default='')
    ap.add_argument('--worst', type=int, default=12)
    ap.add_argument('--out', default='')
    a = ap.parse_args(argv)
    arms = {x for x in a.arms.split(',') if x}
    eps = read_shards(a.shards, arms)
    if not eps:
        print('no underdog episodes for these arms', file=sys.stderr)
        return 1
    tapes = read_tapes(a.hist, {(e['series'], e['ticker']) for _, e in eps})
    by_arm = defaultdict(list)
    for rid, e in eps:
        by_arm[rid].append((e, audit(e, tapes.get(e['ticker']))))
    lines = [f"## Raw-tape audit of underdog trades{(' in run ' + a.run) if a.run else ''} (information only)", '',
             f"{len(eps)} underdog episode(s) in {len(by_arm)} arm(s); {len(tapes)} of {len({e['ticker'] for _, e in eps})} markets have a tape. "
             'Prices are YES prices of the market held, from Kalshi\'s trade tape (the history the sweep replays). '
             '"+2c on tape" = some print after the entry reached the entry price + 2c (before the exit, or before the match\'s close). '
             'A taker round trip on an 8-25c contract costs about 1-2c a contract in fees.', '']
    lines += ['### Entries against the tape', '',
              '| arm | entries | with tape | median gap to last print (c) | gap > +2c | gap < -2c | median prints after entry |',
              '|---|---|---|---|---|---|---|']
    for rid, rows in sorted(by_arm.items()):
        ok = [r for _, r in rows if r]
        gaps = [r['gap'] for r in ok if r['gap'] is not None]
        lines.append(f"| {rid.replace('|', chr(92) + '|')} | {len(rows)} | {len(ok)} | {med(gaps)} | {sum(1 for g in gaps if g > 2)} | "
                     f"{sum(1 for g in gaps if g < -2)} | {med([r['n_after'] for r in ok])} |")
    lines += ['', '### What the tape offered after each entry, by exit leg', '',
              'Each row: trades with a tape; share whose tape reached the entry + 1c / + 2c / + 3c BEFORE THE EXIT (any print); share '
              'with a bid hit at the entry + 2c or more before the exit (a NO-taker print: a taker sell could have filled there); share '
              'reaching + 2c before the match closed; median minutes to the first + 2c print; median lowest print after entry minus '
              'the entry (c); net; for settle, how many the held player lost.', '',
              '| arm | exit | trades | net ($) | +1c before exit | +2c before exit | +3c before exit | bid hit +2c before exit | +2c before close | min to +2c | median low vs entry (c) | settle lost |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for rid, rows in sorted(by_arm.items()):
        legs = defaultdict(list)
        for e, r in rows:
            if r:
                legs[str(e.get('x') or '')].append((e, r))
        for x, rr in sorted(legs.items(), key=lambda kv: sum(float(e.get('pnl') or 0) for e, _ in kv[1])):
            n = len(rr)
            net = sum(float(e.get('pnl') or 0) for e, _ in rr)
            c = {s: sum(1 for _, r in rr if r[f'up{s}_exit'] is not None) for s in (1, 2, 3)}
            c2 = sum(1 for _, r in rr if r['up2_close'] is not None)
            cb = sum(1 for _, r in rr if r['bid2_exit'] is not None)
            mins = [r['up2_exit'] for _, r in rr if r['up2_exit'] is not None]
            lows = [(r['lo_close'] - float(e['px'])) * 100 for e, r in rr if r['lo_close'] is not None]
            lost = sum(1 for e, _ in rr if e.get('won') is False) if x == 'settle' else None
            lines.append(f"| {rid.replace('|', chr(92) + '|')} | {x} | {n} | {net:+,.2f} | {pct(c[1], n)} | {pct(c[2], n)} | {pct(c[3], n)} | {pct(cb, n)} | {pct(c2, n)} | "
                         f"{med(mins)} | {med(lows)} | {'-' if lost is None else f'{lost} of {n}'} |")
    lines += ['', '### When the entries came: phase the sim saw, published start, and the match\'s end on the tape', '',
              'Phase = the sim\'s label at entry (pre = it saw no live match yet). Minutes from start = entry minus the market\'s '
              'published start (negative = before it). Minutes to end = entry to the market\'s last print (about when the match '
              'ended). A pre-match underdog entry normally has a whole match (1.5 to 3 h) ahead of it. The last column: the '
              'market stopped trading before the start the history publishes, so that start cannot be the match\'s start.', '',
              '| arm | exit | trades | pre share | median min from published start | median min to end of tape | ends within 45 min | ends within 90 min | tape ends before the published start |',
              '|---|---|---|---|---|---|---|---|---|']
    for rid, rows in sorted(by_arm.items()):
        legs = defaultdict(list)
        for e, r in rows:
            if r:
                legs[str(e.get('x') or '')].append((e, r))
        for x, rr in sorted(legs.items(), key=lambda kv: sum(float(e.get('pnl') or 0) for e, _ in kv[1])):
            n = len(rr)
            fs = [r['from_start'] for e, r in rr if r['from_start'] is not None and e.get('start_pub')]
            te = [r['to_end'] for _, r in rr]
            lines.append(f"| {rid.replace('|', chr(92) + '|')} | {x} | {n} | {pct(sum(1 for e, _ in rr if e.get('ph') == 'pre'), n)} | {med(fs)} | {med(te)} | "
                         f"{pct(sum(1 for t in te if t <= 45), n)} | {pct(sum(1 for t in te if t <= 90), n)} | "
                         f"{pct(sum(1 for e, r in rr if r['from_start'] is not None and e.get('start_pub') and r['to_end'] < -r['from_start']), n)} |")
        all_rr = [(e, r) for e, r in rows if r]
        n = len(all_rr)
        if n:
            fs = [r['from_start'] for e, r in all_rr if r['from_start'] is not None and e.get('start_pub')]
            te = [r['to_end'] for _, r in all_rr]
            lines.append(f"| {rid.replace('|', chr(92) + '|')} | **all** | {n} | {pct(sum(1 for e, _ in all_rr if e.get('ph') == 'pre'), n)} | {med(fs)} | {med(te)} | "
                         f"{pct(sum(1 for t in te if t <= 45), n)} | {pct(sum(1 for t in te if t <= 90), n)} | "
                         f"{pct(sum(1 for e, r in all_rr if r['from_start'] is not None and e.get('start_pub') and r['to_end'] < -r['from_start']), n)} |")
    lines += ['', '### Losers: wrong from the start, or an exit the rules left on the tape', '',
              'Losing trades (net < 0) split by whether any print after the entry reached the entry + 2c before the exit.', '',
              '| arm | losers | net ($) | never +2c before exit | their net ($) | +2c on tape before exit | their net ($) | of which a bid hit +2c | their net ($) |', '|---|---|---|---|---|---|---|---|---|']
    for rid, rows in sorted(by_arm.items()):
        lo = [(e, r) for e, r in rows if r and float(e.get('pnl') or 0) < 0]
        nev = [(e, r) for e, r in lo if r['up2_exit'] is None]
        had = [(e, r) for e, r in lo if r['up2_exit'] is not None]
        hb = [(e, r) for e, r in had if r['bid2_exit'] is not None]
        s = lambda xs: sum(float(e.get('pnl') or 0) for e, _ in xs)
        lines.append(f"| {rid.replace('|', chr(92) + '|')} | {len(lo)} | {s(lo):+,.2f} | {len(nev)} | {s(nev):+,.2f} | {len(had)} | {s(had):+,.2f} | {len(hb)} | {s(hb):+,.2f} |")
    for rid, rows in sorted(by_arm.items()):
        worst = sorted([(e, r) for e, r in rows if r], key=lambda er: float(er[0].get('pnl') or 0))[:a.worst]
        if not worst:
            continue
        lines += ['', f"### Worst {len(worst)} trades of {rid.replace('|', chr(92) + '|')}, with the tape", '',
                  '| market | entry | phase | min from published start | min to end of tape | entry px | last print before (px, side) | contracts | exit | held min | net ($) | high before exit | low before exit | high before close | player won |',
                  '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for e, r in worst:
            lb = r['last_before']
            lbs = '-' if lb is None else f"{lb[1]:.2f} {'YES' if lb[3] == 1 else 'NO'} taker"
            f2 = lambda v: '-' if v is None else f'{v:.2f}'
            fs = '-' if r['from_start'] is None or not e.get('start_pub') else f"{r['from_start']:.0f}"
            lines.append(f"| {e['ticker']} | {when(int(e['t']))} | {e.get('ph')} | {fs} | {r['to_end']:.0f} | {float(e['px']):.2f} | {lbs} | {float(e.get('n') or 0):.0f} | {e.get('x')} | "
                         f"{float(e.get('hold') or 0) / 60:.0f} | {float(e.get('pnl') or 0):+.2f} | {f2(r['hi_exit'])} | {f2(r['lo_exit'])} | {f2(r['hi_close'])} | "
                         f"{'-' if e.get('won') is None else ('yes' if e['won'] else 'no')} |")
    text = '\n'.join(lines) + '\n'
    if a.out:
        with open(a.out, 'w') as fh:
            fh.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
