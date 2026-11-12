"""Entry point: python -m exitfill.run --capture DIR --out FILE [--run python/exitfill/RUN] [--exits python/exitfill/data/exits.csv]

Reads the request, runs the guard, loads ONLY books/markets files of the named artifacts inside the window, replays the
exit list against them and writes the card (aggregates only)."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

from . import BLOCK_MS, HORIZONS_S, OTHER_T0_SHIFTS_MS, T0_SHIFTS_MS
from .book import Capture, load_capture
from .events import Exit, load_exits
from .guard import check_request, read_run
from .report import render_card
from .rules import evaluate, make_ctx, rules_hash, usable

HERE = os.path.dirname(os.path.abspath(__file__))
CTX_REASONS = ('not_in_capture', 'no_s0', 'no_bid')


def build_rows(exits: List[Exit], cap: Capture) -> List[dict]:
    rows: List[dict] = []
    for ex in exits:
        for sh in (T0_SHIFTS_MS if ex.etype == 'ratchet' else OTHER_T0_SHIFTS_MS):
            ctx, why = make_ctx(ex, cap, sh)
            for h in HORIZONS_S:
                base = {'etype': ex.etype, 'shift': sh, 'H': h, 'block': (ex.t0_ms + sh) // BLOCK_MS, 'n_contracts': ex.count,
                        'kind': 'n/a', 'arms': None, 's0_age_ms': None, 'ref_diff_ticks': None}
                if ctx is None:
                    rows.append({**base, 'reason': why})
                    continue
                base['kind'] = ctx.kind
                base['s0_age_ms'] = ctx.t0 - ctx.s0.k
                if ex.ref_bid_u is not None:
                    step = ctx.hg.up(min(ctx.hb0.bids[0][0], ex.ref_bid_u))
                    base['ref_diff_ticks'] = int(round((ctx.hb0.bids[0][0] - ex.ref_bid_u) / step))
                why_not = usable(ctx, h)
                if why_not:
                    rows.append({**base, 'reason': why_not})
                    continue
                rows.append({**base, 'reason': None, 'arms': evaluate(ctx, h)})
    return rows


def coverage(exits: List[Exit], rows: List[dict]) -> Dict[str, Dict[str, int]]:
    def count(pred):
        return {t: sum(1 for r in rows if r['shift'] == 0 and r['etype'] == t and pred(r)) for t in ('ratchet', 'other_sale')}
    first = HORIZONS_S[0]
    cov: Dict[str, Dict[str, int]] = {'exits in the list': {t: sum(1 for e in exits if e.etype == t) for t in ('ratchet', 'other_sale')}}
    cov['ticker found in the capture'] = count(lambda r: r['H'] == first and r['reason'] != 'not_in_capture')
    cov['a sampled book before the decision'] = count(lambda r: r['H'] == first and r['reason'] not in ('not_in_capture', 'no_s0'))
    cov['a bid on the held side in it'] = count(lambda r: r['H'] == first and r['reason'] not in CTX_REASONS)
    for h in HORIZONS_S:
        cov[f'usable at {h} s'] = count(lambda r, h=h: r['H'] == h and r['reason'] is None)
    for kind in ('15m', 'hourly'):
        cov[f'  of which {kind} at {HORIZONS_S[1]} s'] = count(lambda r, kind=kind: r['H'] == HORIZONS_S[1] and r['reason'] is None and r['kind'] == kind)
    return cov


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--capture', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--run', default=os.path.join(HERE, 'RUN'))
    ap.add_argument('--exits', default=os.path.join(HERE, 'data', 'exits.csv'))
    a = ap.parse_args(argv)
    req_raw = read_run(a.run)
    req = check_request(req_raw)
    exits = load_exits(a.exits)
    dirs = sorted(os.path.join(a.capture, n) for n in req['artifacts'])
    missing = [d for d in dirs if not os.path.isdir(d)]
    if missing:
        print(f'::error::{len(missing)} named artifact folders are missing')
        return 3
    cap = load_capture(dirs, req['from_ms'], req['to_ms'])
    print('load:', {k: v for k, v in cap.stats.items()}, f'tickers={len(cap.series)} markets={len(cap.markets)}')
    if not cap.stats['books_kept']:
        print('::error::no book rows inside the window')
        return 3
    rows = build_rows(exits, cap)
    meta = {'run': req['run'], 'hash': rules_hash(), 'readlog': req['readlog'], 'from': req_raw['from'], 'to': req_raw['to'],
            'segments': str(cap.stats['books_files'])}
    card = render_card(meta, coverage(exits, rows), rows)
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write(card)
    print(card)
    return 0


if __name__ == '__main__':
    sys.exit(main())
