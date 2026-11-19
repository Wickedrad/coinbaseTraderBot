"""Runner stages of the heat direction loop (research/heat_direction). Aggregates only on stdout: one `HEATLOOP <stage> <json>` line each.

  smoke   --coin C --csv F --league L --live-meta M --meta ME   a 2-month warm-up slice: engine time, memory, event counts, the meta checks
  events  --coin C --scope dev|val [--twin N] --csv F --league L --meta ME --out DIR
  round0  --dev DIR --league L                                 the live lane's settings on DEV, the ten naive rules, the twin gate
  dev     --dev DIR --league L --out DIR                       the coordinate descent on DEV (no VAL minute is read)
  val     --spec JSON --val DIR --league L --private DIR       one look: prints one bit, writes the per-check table to a private file
  cut     --coin C --csv F --league L --meta ME --spec JSON    truncate-and-rebuild test of the causality rule
"""
import argparse
import collections
import dataclasses
import datetime
import glob
import hashlib
import json
import os
import resource
import sys
import time

import numpy as np

from heatloop import calls as C
from heatloop import eventset as ES
from heatloop import evaluate as EV
from heatloop import events, gate, guards, optimize, rubric, universe

LEAGUE_SHA = '1931ecbca4a7da1e0e1f5ba38b677d8fcbe6d9381f9e92407d5046123a3d62b7'
LIVE_META_SHA = 'efd5e4490ecfa348f7a8c3e9f941c29af899f67e230bc4484486c7595747cd24'
COINS = ('BTC', 'ETH')
TWINS = (1, 2, 3)


def emit(stage: str, obj) -> None:
    print(f'HEATLOOP {stage} ' + json.dumps(obj, sort_keys=True, default=_jd), flush=True)


def _jd(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return None if x != x else float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, C.Spec):
        return x.as_dict()
    raise TypeError(type(x))


def mem_mb() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def load_universe(league: str) -> list:
    got = universe.sha256(league)
    if got != LEAGUE_SHA:
        sys.exit(f'league file hash {got} is not the one in Amendment 1')
    return universe.load(league)


def load_meta(path: str) -> dict:
    with open(path) as f:
        m = json.load(f)
    return {'price_step': m.get('price_step'), 'edges': m.get('edges', {}), 'table_sha256': m.get('table_sha256')}


def spec_from(d) -> C.Spec:
    d = dict(d)
    d['coins'], d['tfs'] = tuple(d['coins']), tuple(d['tfs'])
    return C.Spec(**d)


def read_sets(dirname: str, scope: str):
    """{coin: real EventSet}, {(coin, twin): EventSet} found in dirname."""
    real, twins = {}, {}
    for p in sorted(glob.glob(os.path.join(dirname, f'{scope}-*.npz'))):
        es = ES.load(p)
        if es.scope != scope:
            sys.exit(f'{p} holds scope {es.scope}, not {scope}')
        (twins.__setitem__((es.coin, es.twin), es) if es.twin else real.__setitem__(es.coin, es))
    return real, twins


def scope_ms(scope: str, val_end=None):
    return guards.scope_range(scope, val_end)


# ------------------------------------------------------------------------------------------------------------------ smoke
def cmd_smoke(a):
    rows = load_universe(a.league)
    meta = load_meta(a.meta)
    with open(a.live_meta) as f:
        live = json.load(f)
    if universe.sha256(a.live_meta) != LIVE_META_SHA:
        sys.exit('live_meta.json hash is not the one in Amendment 1')
    same = {k: v == live[a.coin]['edges'][k] for k, v in meta['edges'].items() if k in live[a.coin]['edges']}
    out = dict(coin=a.coin, meta_table_sha_matches_live=meta['table_sha256'] == live[a.coin]['table_sha256'],
               step=meta['price_step'], live_step=live[a.coin]['price_step'], edges_meta=len(meta['edges']), edges_live=len(live[a.coin]['edges']),
               edges_overlap=len(same), edges_equal=sum(same.values()))
    with open(a.csv) as f:
        out['csv_header'] = f.readline().strip()
    hi = guards.ms(a.end)
    if hi > guards.DEV[0]:
        sys.exit('the smoke slice must end before DEV starts')
    keys = universe.all_keys(rows, a.coin)
    t = time.time()
    m = events.load_grid(a.csv, guards.WARMUP_START, hi)
    out['grid_rows'], out['grid_seconds'] = int(m['n']), round(time.time() - t, 1)
    t = time.time()
    ev = events.event_rows(m, meta, keys, 0, m['n'])
    out['events'], out['events_seconds'], out['mem_mb'] = len(ev), round(time.time() - t, 1), mem_mb()
    by = {}
    for _, k in ev:
        by[k.split(':', 1)[0]] = by.get(k.split(':', 1)[0], 0) + 1
    out['events_by_bar'], out['keys'], out['keys_firing'] = by, len(keys), len(set(k for _, k in ev))
    zone_missing = sorted({k.rsplit('=', 1)[0] for k in keys if not k.rsplit('=', 1)[0].endswith(' sign')} - set(meta['edges']))
    out['zone_keys_without_edges'] = len(zone_missing)
    out['zone_keys_without_edges_sample'] = zone_missing[:8]
    emit('smoke', out)


# ----------------------------------------------------------------------------------------------------------------- events
def cmd_events(a):
    rows = load_universe(a.league)
    meta = load_meta(a.meta)
    keys = universe.all_keys(rows, a.coin)
    t = time.time()
    es = ES.build(a.coin, a.csv, meta, keys, a.scope, twin=a.twin)
    os.makedirs(a.out, exist_ok=True)
    name = f'{a.scope}-{a.coin}-t{a.twin}.npz'
    ES.save(es, os.path.join(a.out, name))
    emit('events', dict(coin=a.coin, scope=a.scope, twin=a.twin, rows=es.n, events=int(len(es.rows)), keys_firing=len(es.keys),
                        seconds=round(time.time() - t), mem_mb=mem_mb(), file=name, bytes=os.path.getsize(os.path.join(a.out, name)),
                        sha256=hashlib.sha256(es.o.tobytes()).hexdigest()[:16]))


# ----------------------------------------------------------------------------------------------------------------- round 0
def calls_per_day(res, lo, hi) -> dict:
    days = (hi - lo) / 86_400_000
    return {k: round(v / days, 2) for k, v in res['n_by_coin'].items()}


def cmd_round0(a):
    rows = load_universe(a.league)
    real, twins = read_sets(a.dev, 'dev')
    lo, hi = scope_ms('dev')
    spec = optimize.ROUND0
    res = EV.evaluate(spec, real, rows, lo, hi, 'bimonth')
    c, i, u = res['_calls']
    g = gate.gate(spec, res, twins, rows, lo, hi) if twins else None
    out = dict(spec=spec.as_dict(), hash=res['hash'], total=res['total'], core8=res['core8'], gate=res['gate'], n_calls=res['n_calls'],
               n_decided=res['n_decided'], n_by_coin=res['n_by_coin'], per_day=calls_per_day(res, lo, hi), hit=round(res['hit_rate'], 4),
               flat_share=round(res['flat_share'], 5), voided=res['voided'], naive={k: round(v, 4) for k, v in res['naive'].items()},
               checks=[dict(id=x['id'], name=x['name'], passed=x['passed'], floor_ok=x['floor_ok'], value=x['value']) for x in res['checks']],
               twin_gate=g)
    for coin in COINS:
        m = c.coin == coin
        dec, hit = rubric.right(c.side[m], c.move[m])
        out.setdefault('by_coin', {})[coin] = dict(calls=int(m.sum()), decided=int(dec.sum()), hit=round(float(hit[dec].mean()), 4) if dec.any() else None)
    for side, nm in ((1, 'up'), (-1, 'down')):
        dec, hit = rubric.right(c.side[c.side == side], c.move[c.side == side])
        out.setdefault('by_side', {})[nm] = dict(decided=int(dec.sum()), hit=round(float(hit[dec].mean()), 4) if dec.any() else None)
    emit('round0', out)


# ------------------------------------------------------------------------------------------------------------------ dev
def cmd_dev(a):
    rows = load_universe(a.league)
    real, _ = read_sets(a.dev, 'dev')
    lo, hi = scope_ms('dev')
    os.makedirs(a.out, exist_ok=True)
    fh = open(os.path.join(a.out, 'trials.jsonl'), 'w')
    n = [0]

    def log(rec):
        n[0] += 1
        fh.write(json.dumps(rec, sort_keys=True, default=_jd) + '\n')
    t = time.time()
    rounds = optimize.descend(real, rows, lo, hi, 'bimonth', log=log)
    fh.close()
    with open(os.path.join(a.out, 'rounds.json'), 'w') as f:
        json.dump(rounds, f, indent=1, default=_jd)
    for r in rounds:
        emit('round', dict(round=r['round'], group=r['group'], trials=r['trials'], improved=r['improved'], stalled=r.get('stalled', False),
                           start=dict(total=r['start']['total'], hit=r['start']['hit'], hash=r['start']['hash'][:12]), best=r['best']))
    emit('dev', dict(trials=n[0], budget=optimize.BUDGET, rounds=len(rounds), seconds=round(time.time() - t), mem_mb=mem_mb()))


# ------------------------------------------------------------------------------------------------------------------- val
def cmd_val(a):
    """One look at VAL for one candidate: the twin gate first (a gate failure uses no look), then the ten checks. Stdout gets one bit."""
    if os.environ.get('HEATLOOP_VAL') != '1':
        sys.exit('VAL is read only by the one-bit look (HEATLOOP_VAL=1)')
    rows = load_universe(a.league)
    with open(a.spec) as f:
        spec = spec_from(json.load(f))
    real, twins = read_sets(a.val, 'val')
    lo, hi = scope_ms('val', a.val_end)
    res = EV.evaluate(spec, real, rows, lo, hi, 'month')
    g = gate.gate(spec, res, twins, rows, lo, hi, 'month')
    table = dict(round=a.round, hash=res['hash'], total=res['total'], core8=res['core8'], gate=res['gate'], passed=res['passed'],
                 n_decided=res['n_decided'], n_by_coin=res['n_dec_by_coin'], hit=res['hit_rate'], flat=res['flat_share'],
                 checks=res['checks'], naive=res['naive'], twin_gate=g)
    os.makedirs(a.private, exist_ok=True)
    with open(os.path.join(a.private, f'val-look-round{a.round}.json'), 'w') as f:
        json.dump(table, f, indent=1, default=_jd)
    bit = int(bool(res['passed'] and g['ok'] and not res['voided']))
    emit('val', dict(round=a.round, hash=res['hash'][:12], gate_ok=bool(g['ok']), bit=bit))


# ------------------------------------------------------------------------------------------------------------------- cut
def cut_points(lo_ms: int, hi_ms: int, seed: int = 20261121, extra: int = 6) -> list:
    """The cut minutes (ms): the last minute of the first and last day of each DEV fold, plus random minutes inside the scope."""
    day = 86_400_000
    folds = [guards.ms(x) for x in ('2026-01-01', '2026-03-01', '2026-05-01', '2026-07-01')]
    pts = []
    for a_, b_ in zip(folds[:-1], folds[1:]):
        pts += [a_ + day - 60_000, b_ - 60_000]
    rng = np.random.default_rng(seed)
    pts += [int(x) // 60_000 * 60_000 for x in rng.integers(lo_ms + day, hi_ms - day, size=extra)]
    return sorted(set(p for p in pts if lo_ms <= p < hi_ms))


def cmd_cut(a):
    rows = load_universe(a.league)
    meta = load_meta(a.meta)
    keys = universe.all_keys(rows, a.coin)
    lo, hi = scope_ms('dev')
    full = ES.build(a.coin, a.csv, meta, keys, 'dev')
    specs = [optimize.ROUND0, dataclasses.replace(optimize.ROUND0, top_n=40, ta_confirm='follows', ta_conf_k=15, ta_inv_k=15, ta_pool=40),
             dataclasses.replace(optimize.ROUND0, top_n=40, ta_confirm='precedes', ta_conf_k=15, ta_inv_k=5, combiner='vote', vote_k=3, margin=1)]
    pts = cut_points(lo, hi, extra=a.extra)
    results, bad = [], 0
    for p in pts:
        end = p + 60_000                          # keep the cut minute itself: the file holds minutes up to and including p
        m = events.load_grid(a.csv, guards.WARMUP_START, end)
        ev = events.event_rows(m, meta, keys, max(0, full.lo_row - ES.PAD), m['n'])
        n_cut = m['n']
        want = [(r, k) for r, k in full.events_for(keys) if r < n_cut]
        got = [(r, k) for r, k in ev if r < n_cut]
        same_ev = want == got
        diag = None
        if not same_ev:                           # aggregates and event rows only: how the two lists differ
            cw, cg = collections.Counter(want), collections.Counter(got)
            of, ot = cw - cg, cg - cw
            diag = dict(n_full=len(want), n_cut=len(got), only_full=sum(of.values()), only_cut=sum(ot.values()),
                        order_only=not of and not ot, first_full=list(of)[:3], first_cut=list(ot)[:3])
            del cw, cg, of, ot
        names = sorted(set(k for _, k in ev))
        trunc = ES.EventSet(a.coin, 0, 'dev', m['t0'], m['n'], full.lo_row, m['o'], full.step, names,
                            [r for r, _ in ev], [names.index(k) for _, k in ev])
        n_calls = same_calls = 0
        for sp in specs:
            sp1 = dataclasses.replace(sp, coins=(a.coin,))
            rf = EV.run(sp1, {a.coin: full}, rows)
            rt = EV.run(sp1, {a.coin: trunc}, rows)
            for k in ('calls', 'inv', 'unconf'):
                x, y = rf[k], rt[k]
                xs = [] if x is None else [(int(t), int(s)) for t, s in zip(x.ts, x.side) if (int(t) - full.t0) // 60_000 < n_cut - 16]
                ys = [] if y is None else [(int(t), int(s)) for t, s in zip(y.ts, y.side) if (int(t) - full.t0) // 60_000 < n_cut - 16]
                n_calls += len(xs)
                same_calls += int(xs == ys)
                bad += int(xs != ys)
        bad += int(not same_ev)
        row = dict(cut=datetime.datetime.fromtimestamp(p / 1000, datetime.timezone.utc).strftime('%Y-%m-%d %H:%M'), events=len(want), events_equal=same_ev,
                   calls_compared=n_calls)
        if diag:
            row['diff'] = diag
        results.append(row)
    emit('cut', dict(coin=a.coin, cuts=len(results), mismatches=bad, ok=bad == 0, results=results, mem_mb=mem_mb()))
    if bad:
        sys.exit(1)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='heatloop.stage')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('smoke'); s.add_argument('--coin', required=True); s.add_argument('--csv', required=True)
    s.add_argument('--league', required=True); s.add_argument('--live-meta', dest='live_meta', required=True)
    s.add_argument('--meta', required=True); s.add_argument('--end', default='2025-08-01')
    e = sub.add_parser('events'); e.add_argument('--coin', required=True); e.add_argument('--scope', required=True, choices=['dev', 'val'])
    e.add_argument('--twin', type=int, default=0); e.add_argument('--csv', required=True); e.add_argument('--league', required=True)
    e.add_argument('--meta', required=True); e.add_argument('--out', required=True)
    r = sub.add_parser('round0'); r.add_argument('--dev', required=True); r.add_argument('--league', required=True)
    d = sub.add_parser('dev'); d.add_argument('--dev', required=True); d.add_argument('--league', required=True); d.add_argument('--out', required=True)
    v = sub.add_parser('val'); v.add_argument('--spec', required=True); v.add_argument('--val', required=True); v.add_argument('--league', required=True)
    v.add_argument('--private', required=True); v.add_argument('--round', type=int, required=True)
    v.add_argument('--val-end', dest='val_end', type=int, default=None)
    c = sub.add_parser('cut'); c.add_argument('--coin', required=True); c.add_argument('--csv', required=True); c.add_argument('--league', required=True)
    c.add_argument('--meta', required=True); c.add_argument('--extra', type=int, default=6)
    a = ap.parse_args(argv)
    if getattr(a, 'coin', None) == 'DOGE':
        sys.exit('NEVER DOGE')
    {'smoke': cmd_smoke, 'events': cmd_events, 'round0': cmd_round0, 'dev': cmd_dev, 'val': cmd_val, 'cut': cmd_cut}[a.cmd](a)


if __name__ == '__main__':
    main()
