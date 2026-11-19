"""Runner stages of the direction sweep (research/heat_direction/PREREG-3.md). Aggregates and rule parameters only on stdout:
one `HEATLOOP ds <json>` line per result.

  python -m dirsweep.stage run    --btc <1m.csv> --eth <1m.csv> --twin 0|1|2|3 --out <dir>   S1, S2 on the real coins (twin 0) or a no-signal twin
  python -m dirsweep.stage causal --coin BTC --csv <1m.csv>                                   the cut test of section 7 on the real file
  python -m dirsweep.stage floors --btc <1m.csv> --eth <1m.csv> --twin 0|1|2|3 --out <dir>   AMENDMENT-3.md: the frequency frontier (floors 3 to 60)
  python -m dirsweep.stage choose --dir <dir>                                                  AMENDMENT-3.md section 4: the one FINAL candidate
  python -m dirsweep.stage freeze --btc <1m.csv> --eth <1m.csv> --floor F --expect-rid R --out <dir>   the chosen rule and its control, recomputed
  python -m dirsweep.stage topcheck --coin BTC --csv <1m.csv> --day YYYY-MM-DD                  the exchange's daily file against the sweep's file, one search day
  python -m dirsweep.stage topup --first YYYY-MM-DD --last YYYY-MM-DD --out <dir>               the FINAL days' minute files from the exchange's daily files
  python -m dirsweep.stage freezefile --data <freeze-data.json> --choose <choose.json> --first-day <Monday> --out <FREEZE-DS.json>   the freeze file, with hashes
  python -m dirsweep.stage verify --freeze <FREEZE-DS.json>                                     every hash of the freeze file against the checked-out files
  python -m dirsweep.stage final --freeze <FREEZE-DS.json> --btc <csv> --eth <csv> --out <dir>  the FINAL (one look); --plumbing runs it on search weeks
"""
import argparse
import json
import os
import resource
import sys
import time

import numpy as np

from dirsweep import data
from dirsweep import features as F
from dirsweep import final as FIN
from dirsweep import floors as FL
from dirsweep import grid as G
from dirsweep import hist as H
from dirsweep import infer as I
from dirsweep import nested as N
from dirsweep import oracle as O
from dirsweep import replay as R
from dirsweep import topup as T


def mem_mb() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)


def _jd(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    raise TypeError(type(x))


def clean(x):
    """JSON-safe copy: nan and inf become null."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.ndarray):
        return clean(x.tolist())
    return x


def emit(part: str, obj: dict) -> None:
    print('HEATLOOP ds ' + json.dumps(clean(dict(obj, part=part)), sort_keys=True), flush=True)


def save(out: str, name: str, obj) -> None:
    if out:
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, name), 'w') as f:
            json.dump(clean(obj), f, sort_keys=True)


def cmd_run(a) -> None:
    t0 = time.time()
    paths = {'BTC': a.btc, 'ETH': a.eth}
    grids = {c: data.load(p, a.twin) for c, p in paths.items()}
    emit('load', {'twin': a.twin, 'coins': {c: data.info(m) for c, m in grids.items()}, 'search_days': G.ND, 'mem_mb': mem_mb()})
    pre = {c: F.prepare(m) for c, m in grids.items()}
    periods = G.period_days()
    blocks = G.block_days()
    nact = G.n_active(np.arange(G.N_CELLS))
    bench_cells = [ik * G.PER_K for ik in range(len(G.K))]
    brief = a.twin != 0
    leagues, survivors_total, matrix, md_lines = {}, 0, None, []
    s1 = None
    for h in (15,) + tuple(x for x in G.HORIZONS if x != 15):
        arrs = {c: H.cell_arrays(grids[c], G.STEP[c], h, pre=pre[c]) for c in grids}
        pooled = H.add(arrs['BTC'], arrs['ETH'])
        if h == 15:
            coins = {c: (arrs[c]['ndec'], arrs[c]['cf']) for c in arrs}
            ndec, cf = pooled['ndec'], pooled['cf']
            nested = N.run_nested(ndec, cf, blocks, nact, bench_cells, coins=coins)
            fr = N.freeze(ndec, cf, blocks, nact, coins=coins)
            emit('s1-nested', {'twin': a.twin, 'nested_hit': nested.get('pooled', {}).get('hit'), 'nested': {k: v for k, v in nested.items() if k not in ('sel_n', 'sel_r', 'ben_n', 'ben_r')},
                               'secs': round(time.time() - t0), 'mem_mb': mem_mb()})
            rc = I.reality_check(ndec, cf)
            pb = I.pbo(ndec, cf, blocks)
            pair = None
            if 'ben_n' in nested and 'sel_n' in nested:
                pair = I.paired_bootstrap(nested['sel_n'], nested['sel_r'], nested['ben_n'], nested['ben_r'])
            ver = N.verdict(nested, fr, rc, pb, pair)
            s1 = {'twin': a.twin, 'frozen': fr, 'reality_check': rc, 'pbo': pb, 'paired_vs_benchmark': pair, 'verdict': ver, 'nested_hit': nested.get('pooled', {}).get('hit'),
                  'bench_hit': nested.get('bench_pooled', {}).get('hit'), 'secs': round(time.time() - t0), 'mem_mb': mem_mb()}
            emit('s1-verdict', s1)
            save(a.out, f's1-twin{a.twin}.json', {'nested': {k: v for k, v in nested.items() if k not in ('sel_n', 'sel_r', 'ben_n', 'ben_r')}, **s1})
            matrix = O.matrix(pooled, periods, 15)
            del coins, ndec, cf
        lg = O.league(pooled, h, periods)
        leagues[h] = lg
        survivors_total += lg['n_survivors']
        if brief:
            top = lg['league'][0] if lg['league'] else None
            emit('s2', {'twin': a.twin, 'h': h, 'eligible_rules': lg['eligible_rules'], 'n_survivors': lg['n_survivors'],
                        'best_A_heat': None if top is None else top['A']['heat'], 'best_rule': None if top is None else top['rule']})
        else:
            emit('s2', {'twin': a.twin, **lg, 'mem_mb': mem_mb()})
            md_lines += O.render_league(lg)
        save(a.out, f's2-twin{a.twin}-h{h}.json', lg)
        del arrs, pooled
    if not brief:
        emit('s2-matrix', {'twin': a.twin, **matrix})
        save(a.out, 's2-matrix.json', matrix)
        md_lines += O.render_matrix(matrix)
    for line in md_lines:                              # the same tables, readable (derived from the lines above)
        print('HEATLOOP ds-md ' + line, flush=True)
    if a.out and md_lines:
        with open(os.path.join(a.out, f'tables-twin{a.twin}.md'), 'w') as f:
            f.write('\n'.join(md_lines) + '\n')
    emit('done', {'twin': a.twin, 'survivors_all_horizons': survivors_total, 'secs': round(time.time() - t0), 'mem_mb': mem_mb()})


def cmd_causal(a) -> None:
    m = data.load(a.csv)
    res = F.cut_test(m, ks=G.K, cuts=a.cuts)
    emit('causal', {'coin': a.coin, 'rows': int(m['n']), 'cuts': res['cuts'], 'rows_compared': res['rows_compared'], 'mismatches': res['mismatches'],
                    'ok': res['ok'], 'grid_ends_before_search_end': bool(m['t0'] + m['n'] * G.MIN <= G.SEARCH_END), 'mem_mb': mem_mb()})
    if not res['ok']:
        sys.exit(1)


def cmd_floors(a) -> None:
    """AMENDMENT-3.md: the nested walk-forward, frozen rule, RC, PBO and lockout replay repeated with the eligibility floor raised. h = 15 only."""
    t0 = time.time()
    paths = {'BTC': a.btc, 'ETH': a.eth}
    grids = {c: data.load(p, a.twin) for c, p in paths.items()}
    pre = {c: F.prepare(m) for c, m in grids.items()}
    arrs = {c: H.cell_arrays(grids[c], G.STEP[c], 15, pre=pre[c]) for c in grids}
    pooled = H.add(arrs['BTC'], arrs['ETH'])
    coins = {c: (arrs[c]['ndec'], arrs[c]['cf']) for c in arrs}
    ndec, cf = pooled['ndec'], pooled['cf']
    del arrs
    replayers = {c: R.Replayer(grids[c], G.STEP[c], pre[c]) for c in grids}
    periods, blocks = G.period_days(), G.block_days()
    nact = G.n_active(np.arange(G.N_CELLS))
    bench_cells = [ik * G.PER_K for ik in range(len(G.K))]
    emit('floors-load', {'twin': a.twin, 'floors': list(FL.FLOORS), 'mem_mb': mem_mb()})
    floors = []
    for fl in FL.FLOORS:
        res = FL.run_floor(fl, ndec, cf, blocks, nact, bench_cells, coins, replayers, periods)
        res['secs'] = round(time.time() - t0)
        floors.append(res)
        emit('floor', {'twin': a.twin, **res})
    save(a.out, f'floors-twin{a.twin}.json', {'twin': a.twin, 'floors': floors})
    emit('floors-done', {'twin': a.twin, 'secs': round(time.time() - t0), 'mem_mb': mem_mb()})


def cmd_choose(a) -> None:
    """Read floors-twin0..3.json from --dir and print the one FINAL candidate (AMENDMENT-3.md section 4)."""
    results = {}
    for t in range(4):
        p = os.path.join(a.dir, f'floors-twin{t}.json')
        if os.path.exists(p):
            with open(p) as f:
                results[t] = json.load(f)
    if 0 not in results:
        sys.exit('no floors-twin0.json')
    ch = FL.choose(results)
    emit('choose', {'twins_read': sorted(results), **ch})
    save(a.out or a.dir, 'choose.json', ch)


def _freeze_arrays(a):
    paths = {'BTC': a.btc, 'ETH': a.eth}
    grids = {c: data.load(p, 0) for c, p in paths.items()}
    pre = {c: F.prepare(m) for c, m in grids.items()}
    arrs = {c: H.cell_arrays(grids[c], G.STEP[c], 15, pre=pre[c]) for c in grids}
    pooled = H.add(arrs['BTC'], arrs['ETH'])
    coins = {c: (arrs[c]['ndec'], arrs[c]['cf']) for c in arrs}
    replayers = {c: R.Replayer(grids[c], G.STEP[c], pre[c]) for c in grids}
    return pooled['ndec'], pooled['cf'], coins, replayers


def cmd_freeze(a) -> None:
    """The chosen floor's rule and its always-on control, recomputed from the search days; fails if the rule is not the one `choose` named."""
    ndec, cf, coins, replayers = _freeze_arrays(a)
    nact = G.n_active(np.arange(G.N_CELLS))
    bench_cells = [ik * G.PER_K for ik in range(len(G.K))]
    out = FIN.freeze_data(a.floor, ndec, cf, G.block_days(), nact, bench_cells, coins, replayers, G.period_days())
    emit('freeze', out)
    save(a.out, 'freeze-data.json', out)
    if a.expect_rid is not None and out['rule']['rid'] != a.expect_rid:
        sys.exit(f"the rule is {out['rule']['rid']}, `choose` named {a.expect_rid}")


def cmd_topcheck(a) -> None:
    """One search day of one coin: the exchange's daily file against the minute file the sweep read."""
    from heatloop import events
    lo = T.day_start_ms(a.day)
    ex = T.fetch_day(a.coin, a.day)
    mine = events.read_bars(a.csv, lo, lo + G.DAY)
    cmp = T.compare(ex, mine)
    ok = cmp['only_a'] == 0 and cmp['only_b'] == 0 and all((cmp[f'max_rel_{c}'] or 0.0) <= 1e-9 for c in T.COLS[1:])
    emit('topcheck', {'coin': a.coin, 'day': a.day, 'ok': ok, **cmp})
    if not ok:
        sys.exit(1)


def cmd_topup(a) -> None:
    """The FINAL days' minute files (two warm-up days before the first Monday, the day after the last Sunday), written in the sweep's own layout."""
    os.makedirs(a.out, exist_ok=True)
    if a.freeze:
        with open(a.freeze) as f:
            win = FIN.window(json.load(f))
        a.first, a.last = win['grid_first'], win['grid_last']
    if not (a.first and a.last):
        sys.exit('give --freeze, or --first and --last')
    rep = {}
    for coin in ('BTC', 'ETH'):
        df = T.fetch_range(coin, a.first, a.last)
        T.write_csv(df, os.path.join(a.out, f'{coin}.csv'))
        rows = df.attrs['rows_per_day']
        rep[coin] = {'rows': int(len(df)), 'days': len(rows), 'days_not_1440': {d: n for d, n in rows.items() if n != 1440}}
    emit('topup', {'first': a.first, 'last': a.last, **rep})


def cmd_final(a) -> None:
    """The FINAL, or with --plumbing the same code path on search weeks (never a minute at or after 2026-11-01)."""
    with open(a.freeze) as f:
        fz = json.load(f)
    if a.plumbing:
        fz = dict(fz, first_day=a.first_day, last_day=a.last_day, weeks=len(T.days(a.first_day, a.last_day)) // 7)
    win = FIN.window(fz)
    if not a.plumbing:
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        ready = dt.datetime.fromisoformat(win['last_day']).replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=2)
        if now < ready:
            sys.exit(f"the FINAL weeks are not over: not before {ready.isoformat()}")
        if not a.commit_date:
            sys.exit('the FINAL needs --commit-date, the date of the commit that added the freeze file')
        if dt.datetime.fromisoformat(a.commit_date) > dt.datetime.fromisoformat(fz['freeze_deadline_utc'].replace('Z', '+00:00')):
            sys.exit('the freeze was committed after its own deadline; the FINAL start has to be set again')
    grids = {c: FIN.load_final(p, win, plumbing=a.plumbing) for c, p in (('BTC', a.btc), ('ETH', a.eth))}
    res = FIN.score(grids, fz, win)
    res['plumbing'] = bool(a.plumbing)
    emit('final-plumbing' if a.plumbing else 'final', res)
    save(a.out, 'final-plumbing.json' if a.plumbing else 'final-result.json', res)


def cmd_freezefile(a) -> None:
    import datetime as dt
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    with open(a.data) as f:
        data = json.load(f)
    with open(a.choose) as f:
        choose = json.load(f)
    fz = FIN.assemble(data, choose, a.first_day, root, dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    with open(a.out, 'w') as f:
        json.dump(clean(fz), f, sort_keys=True, indent=1)
        f.write('\n')
    emit('freezefile', {k: fz[k] for k in ('floor', 'weeks', 'first_day', 'last_day', 'freeze_deadline_utc', 'expected_decided')})


def cmd_verify(a) -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    with open(a.freeze) as f:
        fz = json.load(f)
    res = FIN.verify(fz, root)
    emit('verify', res)
    if not res['ok']:
        sys.exit(1)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog='dirsweep.stage')
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--btc', required=True)
    r.add_argument('--eth', required=True)
    r.add_argument('--twin', type=int, default=0, choices=[0, 1, 2, 3])
    r.add_argument('--out', default='')
    c = sub.add_parser('causal')
    c.add_argument('--coin', required=True)
    c.add_argument('--csv', required=True)
    c.add_argument('--cuts', type=int, default=12)
    f = sub.add_parser('floors')
    f.add_argument('--btc', required=True)
    f.add_argument('--eth', required=True)
    f.add_argument('--twin', type=int, default=0, choices=[0, 1, 2, 3])
    f.add_argument('--out', default='')
    h = sub.add_parser('choose')
    h.add_argument('--dir', required=True)
    h.add_argument('--out', default='')
    z = sub.add_parser('freeze')
    z.add_argument('--btc', required=True)
    z.add_argument('--eth', required=True)
    z.add_argument('--floor', type=int, required=True)
    z.add_argument('--expect-rid', type=int, default=None)
    z.add_argument('--out', default='')
    k = sub.add_parser('topcheck')
    k.add_argument('--coin', required=True, choices=['BTC', 'ETH'])
    k.add_argument('--csv', required=True)
    k.add_argument('--day', required=True)
    u = sub.add_parser('topup')
    u.add_argument('--first', default='')
    u.add_argument('--last', default='')
    u.add_argument('--freeze', default='')
    u.add_argument('--out', required=True)
    ff = sub.add_parser('freezefile')
    ff.add_argument('--data', required=True)
    ff.add_argument('--choose', required=True)
    ff.add_argument('--first-day', required=True)
    ff.add_argument('--out', required=True)
    vv = sub.add_parser('verify')
    vv.add_argument('--freeze', required=True)
    n = sub.add_parser('final')
    n.add_argument('--freeze', required=True)
    n.add_argument('--btc', required=True)
    n.add_argument('--eth', required=True)
    n.add_argument('--out', default='')
    n.add_argument('--plumbing', action='store_true')
    n.add_argument('--first-day', default='')
    n.add_argument('--last-day', default='')
    n.add_argument('--commit-date', default='')
    a = ap.parse_args(argv)
    if getattr(a, 'coin', None) == 'DOGE':
        sys.exit('NEVER DOGE')
    {'run': cmd_run, 'causal': cmd_causal, 'floors': cmd_floors, 'choose': cmd_choose, 'freeze': cmd_freeze, 'topcheck': cmd_topcheck,
     'topup': cmd_topup, 'final': cmd_final, 'freezefile': cmd_freezefile, 'verify': cmd_verify}[a.cmd](a)


if __name__ == '__main__':
    main()
