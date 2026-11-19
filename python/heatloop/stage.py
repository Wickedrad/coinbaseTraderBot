"""Runner stages of the heat direction loop (research/heat_direction). Aggregates only on stdout: one `HEATLOOP <stage> <json>` line each.

  smoke   --coin C --csv F --league L --live-meta M --meta ME   a 2-month warm-up slice: engine time, memory, event counts, the meta checks
  events  --coin C --scope dev|val [--twin N] --csv F --league L --meta ME --out DIR
  round0  --dev DIR --league L                                 the live lane's settings on DEV, the ten naive rules, the twin gate
  dev     --dev DIR --league L --out DIR [--family h1|h2]      the coordinate descent on DEV (no VAL minute is read); h2 = PREREG-2.md
  val     --spec JSON --val DIR --league L --private DIR       one look: prints the bits, writes the per-check table to a private file
  looks   --rounds JSON --val DIR --league L --private DIR     H2: the looks of PREREG-2.md section 3 item 3, in round order, at most 3
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
    plan, start, budget = optimize.family(a.family)
    os.makedirs(a.out, exist_ok=True)
    fh = open(os.path.join(a.out, 'trials.jsonl'), 'w')
    n = [0]

    def log(rec):
        n[0] += 1
        fh.write(json.dumps(rec, sort_keys=True, default=_jd) + '\n')
    t = time.time()
    rounds = optimize.descend(real, rows, lo, hi, 'bimonth', log=log, plan=plan, start=start, ref=start)
    fh.close()
    with open(os.path.join(a.out, 'rounds.json'), 'w') as f:
        json.dump(rounds, f, indent=1, default=_jd)
    for r in rounds:
        emit('round', dict(round=r['round'], group=r['group'], trials=r['trials'], improved=r['improved'], stalled=r.get('stalled', False),
                           start=dict(total=r['start']['total'], hit=r['start']['hit'], hash=r['start']['hash'][:12]), best=r['best']))
    if rounds:
        emit('dev_start', dict(family=a.family, start=rounds[0]['start']))
    emit('dev', dict(family=a.family, trials=n[0], budget=budget, rounds=len(rounds), seconds=round(time.time() - t), mem_mb=mem_mb()))


# --------------------------------------------------------------------------------------------------------------- inspect
def cmd_inspect(a):
    """DEV only: the ten checks, one row each, for the best spec of every DEV round (what the one-line round log leaves out)."""
    rows = load_universe(a.league)
    real, _ = read_sets(a.dev, 'dev')
    lo, hi = scope_ms('dev')
    with open(a.rounds) as f:
        rounds = json.load(f)
    for r in rounds:
        spec = spec_from(r['best']['spec'])
        res = EV.evaluate(spec, real, rows, lo, hi, 'bimonth')
        emit('inspect', dict(round=r['round'], group=r['group'], hash=res['hash'][:12], total=res['total'], core8=res['core8'],
                             hit=round(res['hit_rate'], 4), n_decided=res['n_decided'], n_dec_by_coin=res['n_dec_by_coin'],
                             flat=round(res['flat_share'], 5), naive={k: round(v, 4) for k, v in res['naive'].items()},
                             naive_base=None if not res.get('_base') else {k: round(v, 4) for k, v in res['_base'].items()},
                             checks=[dict(id=x['id'], name=x['name'], passed=x['passed'], floor_ok=x['floor_ok'], value=x['value'],
                                          **({'best_rule': x['best_rule']} if 'best_rule' in x else {})) for x in res['checks']]))


# --------------------------------------------------------------------------------------------------------------- timing
def cmd_timing(a):
    """DEV only: the heat map's side or the heat map's timing? The fade of the last 15 minutes at every minute against at the heat
    events of a round's best spec, and who is right where the heat side and the fade side differ."""
    rows = load_universe(a.league)
    real, _ = read_sets(a.dev, 'dev')
    lo, hi = scope_ms('dev')
    with open(a.rounds) as f:
        rounds = json.load(f)
    base = {}
    for coin, es in sorted(real.items()):
        step = float(es.step) if es.step else 1.0
        e = np.arange(max(es.lo_row, 60), es.n - 17, dtype=np.int64)
        p15 = np.sign(np.round((es.o[e] - es.o[e - 15]) / step)).astype(int)
        mv = (es.o[e + 15] - es.o[e]) / step
        ok = p15 != 0
        dec, hit = rubric.right(-p15[ok], mv[ok])
        sub = ((e[ok] - es.lo_row) % 15) == 0
        base[coin] = dict(minutes=int(len(e)), decided=int(dec.sum()), fade15=round(float(hit[dec].mean()), 4),
                          decided_every15=int((dec & sub).sum()), fade15_every15=round(float(hit[dec & sub].mean()), 4))
        # the same rule month by month, warm-up months (2025-06 to 2025-12, never scored by the loop) and DEV months alike
        e0 = np.arange(60, es.n - 17, dtype=np.int64)
        q = np.sign(np.round((es.o[e0] - es.o[e0 - 15]) / step)).astype(int)
        m0 = (es.o[e0 + 15] - es.o[e0]) / step
        okq = q != 0
        dq, hq = rubric.right(-q[okq], m0[okq])
        mon = (es.t0 + e0[okq] * 60_000).astype('datetime64[ms]').astype('datetime64[M]').astype(str)
        base[coin]['by_month'] = {k: [int((dq & (mon == k)).sum()), round(float(hq[dq & (mon == k)].mean()), 4)] for k in sorted(set(mon))}
    emit('timing_all_minutes', base)
    for r in rounds:
        if r['round'] not in (1, 2, 4, 5, 6):
            continue
        res = EV.evaluate(spec_from(r['best']['spec']), real, rows, lo, hi, 'bimonth')
        c = res['_calls'][0]
        dec, hit = rubric.right(c.side, c.move)
        f15 = -np.asarray(c.past[15])
        agree, differ, nopast = (f15 == c.side) & (f15 != 0), (f15 != c.side) & (f15 != 0), f15 == 0
        rate = lambda m: round(float(hit[dec & m].mean()), 4) if (dec & m).any() else None
        emit('timing_events', dict(round=r['round'], group=r['group'], decided=int(dec.sum()), heat_hit=rate(np.ones(len(c), bool)),
                                   same_side=dict(n=int((dec & agree).sum()), heat_hit=rate(agree)),
                                   other_side=dict(n=int((dec & differ).sum()), heat_hit=rate(differ)),
                                   no_past_move=dict(n=int((dec & nopast).sum()), heat_hit=rate(nopast))))


# ------------------------------------------------------------------------------------------------------------------- val
MAX_LOOKS = 3                       # PREREG-2.md section 3 item 3


def look(spec, round_no, rows, real, twins, lo, hi, private, blocks='month') -> dict:
    """One look at VAL for one candidate: the twin gate first (a gate failure uses no look), then the ten checks. The per-check table
    goes to a private file; what comes back (and gets printed) is two bits and the gate. primary = 9 of 10 with checks 1 to 3 among
    them; core = checks 1 to 8 all pass (PREREG-2.md section 3 item 2). Both need the gate and a flat share under the void limit."""
    res = EV.evaluate(spec, real, rows, lo, hi, blocks)
    g = gate.gate(spec, res, twins, rows, lo, hi, blocks)
    table = dict(round=round_no, hash=res['hash'], total=res['total'], core8=res['core8'], gate=res['gate'], passed=res['passed'],
                 n_decided=res['n_decided'], n_by_coin=res['n_dec_by_coin'], hit=res['hit_rate'], flat=res['flat_share'],
                 checks=res['checks'], naive=res['naive'], naive_base=res.get('_base'), twin_gate=g)
    os.makedirs(private, exist_ok=True)
    with open(os.path.join(private, f'val-look-round{round_no}.json'), 'w') as f:
        json.dump(table, f, indent=1, default=_jd)
    ok = bool(g['ok'] and not res['voided'])
    return dict(round=round_no, hash=res['hash'][:12], gate_ok=bool(g['ok']), bit=int(bool(res['passed'] and ok)),
                core_bit=int(bool(res['core8'] == 8 and ok)))


def cmd_val(a):
    if os.environ.get('HEATLOOP_VAL') != '1':
        sys.exit('VAL is read only by the one-bit look (HEATLOOP_VAL=1)')
    rows = load_universe(a.league)
    with open(a.spec) as f:
        spec = spec_from(json.load(f))
    real, twins = read_sets(a.val, 'val')
    lo, hi = scope_ms('val', a.val_end)
    emit('val', look(spec, a.round, rows, real, twins, lo, hi, a.private))


def qualifying(rounds: list, max_looks: int = MAX_LOOKS) -> list:
    """The rounds whose best goes to VAL (PREREG-2.md section 3 item 3): eligible, strictly better than the round's start, and all of
    checks 1 to 8 passing on DEV. Round order, one look per candidate, at most `max_looks`."""
    out, seen = [], set()
    for r in rounds:
        b = r['best']
        if not (r.get('improved') and b['eligible'] and sum(b['passed'][:8]) == 8) or b['hash'] in seen:
            continue
        seen.add(b['hash'])
        out.append(r)
    return out[:max_looks]


def cmd_looks(a):
    """H2: the looks of PREREG-2.md section 3 item 3. Stops at the first look where either bit is 1, or at a gate failure (that
    uses no look and means the evaluator, not the candidate, needs a human)."""
    if os.environ.get('HEATLOOP_VAL') != '1':
        sys.exit('VAL is read only by the looks (HEATLOOP_VAL=1)')
    with open(a.rounds) as f:
        rounds = json.load(f)
    cand = qualifying(rounds)
    for r in cand:                                     # a stale or foreign rounds file must not be looked at under another candidate's name
        if C.spec_hash(spec_from(r['best']['spec'])) != r['best']['hash']:
            sys.exit(f"round {r['round']}: the spec in rounds.json does not hash to its recorded hash")
    emit('looks_plan', dict(candidates=[dict(round=r['round'], hash=r['best']['hash'][:12]) for r in cand], max_looks=MAX_LOOKS))
    if not cand:
        emit('looks', dict(taken=0, stopped='no round qualifies on DEV'))
        return
    rows = load_universe(a.league)
    real, twins = read_sets(a.val, 'val')
    lo, hi = scope_ms('val', a.val_end)
    taken, stopped = 0, 'looks used up'
    for r in cand:
        out = look(spec_from(r['best']['spec']), r['round'], rows, real, twins, lo, hi, a.private)
        emit('val', out)
        if not out['gate_ok']:
            stopped = 'gate failed (no look used)'
            break
        taken += 1
        if out['bit'] or out['core_bit']:
            stopped = 'a bit is 1'
            break
    emit('looks', dict(taken=taken, stopped=stopped))


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
             dataclasses.replace(optimize.ROUND0, top_n=40, ta_confirm='precedes', ta_conf_k=15, ta_inv_k=5, combiner='vote', vote_k=3, margin=1),
             optimize.ROUND0_H2,                   # H2: the side is against the last k minute move, measured from the entry minute's open
             dataclasses.replace(optimize.ROUND0_H2, top_n=40, fade_k=60, lag=0, ta_confirm='follows', ta_conf_k=15, ta_inv_k=15, ta_pool=40),
             dataclasses.replace(optimize.ROUND0_H2, top_n=20, fade_k=1, lag=1, ta_confirm='none', ta_inv_k=0)]
    pts = cut_points(lo, hi, extra=a.extra)
    # cuts placed exactly on the entry minute of real fade calls: the file then ends at the call's own minute, so a side that used anything
    # after open[e] (or an event that used a bar after its own row) changes or drops that call and shows up as a mismatch
    d0 = EV.decide_coin(dataclasses.replace(optimize.ROUND0_H2, coins=(a.coin,)), full, rows, a.coin)
    own = [c[0] for c in d0['calls'] if lo <= full.t0 + c[0] * 60_000 < hi]
    if own and a.at_calls:
        pick = np.random.default_rng(20261122).choice(own, size=min(a.at_calls, len(own)), replace=False)
        pts = sorted(set(pts) | {int(full.t0 + int(e) * 60_000) for e in pick})
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
        n_calls = same_calls = n_raw = 0
        for sp in specs:
            sp1 = dataclasses.replace(sp, coins=(a.coin,))
            df, dt_ = EV.decide_coin(sp1, full, rows, a.coin), EV.decide_coin(sp1, trunc, rows, a.coin)
            for k in ('calls', 'inv', 'unconf'):          # the raw calls (entry row, side), every one entered before the file ends
                xs = [(c[0], c[1]) for c in df[k] if c[0] < n_cut]
                ys = [(c[0], c[1]) for c in dt_[k] if c[0] < n_cut]
                n_raw += len(xs)
                bad += int(xs != ys)
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
                   calls_compared=n_calls, raw_calls_compared=n_raw)
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
    d.add_argument('--family', choices=optimize.FAMILIES, default='h1')
    i = sub.add_parser('inspect'); i.add_argument('--dev', required=True); i.add_argument('--league', required=True); i.add_argument('--rounds', required=True)
    t = sub.add_parser('timing'); t.add_argument('--dev', required=True); t.add_argument('--league', required=True); t.add_argument('--rounds', required=True)
    v = sub.add_parser('val'); v.add_argument('--spec', required=True); v.add_argument('--val', required=True); v.add_argument('--league', required=True)
    v.add_argument('--private', required=True); v.add_argument('--round', type=int, required=True)
    v.add_argument('--val-end', dest='val_end', type=int, default=None)
    lk = sub.add_parser('looks'); lk.add_argument('--rounds', required=True); lk.add_argument('--val', required=True); lk.add_argument('--league', required=True)
    lk.add_argument('--private', required=True); lk.add_argument('--val-end', dest='val_end', type=int, default=None)
    c = sub.add_parser('cut'); c.add_argument('--coin', required=True); c.add_argument('--csv', required=True); c.add_argument('--league', required=True)
    c.add_argument('--meta', required=True); c.add_argument('--extra', type=int, default=6); c.add_argument('--at-calls', dest='at_calls', type=int, default=4)
    a = ap.parse_args(argv)
    if getattr(a, 'coin', None) == 'DOGE':
        sys.exit('NEVER DOGE')
    {'smoke': cmd_smoke, 'events': cmd_events, 'round0': cmd_round0, 'dev': cmd_dev, 'inspect': cmd_inspect, 'timing': cmd_timing, 'val': cmd_val, 'looks': cmd_looks, 'cut': cmd_cut}[a.cmd](a)


if __name__ == '__main__':
    main()
