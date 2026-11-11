"""The pair pack of the OR-HM1 heat tables: the matrix side of the map (one reading while another, or the clock, is
at a level) in a form a bot lane can act on (python/oracle/prereg/OR-HM1.md, Amendment 5).

  python3 -m oracle.heat_pairs --tables <dir of <COIN>[-twinN]/{heat.csv.gz,meta.json}> --pack <traded_pack.json>
                               --out <pair_pack.json> [--all <dir for pairs_<COIN>.csv.gz>] [--horizons 15,60]
                               [--top 40] [--top-lift 20] [--per-trigger 3] [--parity <dir>] [--metas <dir> --live-meta <file>]

A pair cell of the tables: a trigger event (a single event level, e.g. `1m:RSI2=low (falling in)`) at whose close a
second reading holds a level (its state at the last CLOSED bar of its own timeframe, heat.read_state); a triple adds a
third reading. The clock (UTC 4-hour block) and the dominance states are readings like any other.

Every pair and triple cell with a sample on both periods is scored (30 events on 30 / 20 days, and as many of the
trigger's other events); NO pass mark removes a row. The direction is the one the cell's odds showed on A (2020-2024);
every B (2025) number is signed in it. Only relationships the tables stored exist here: those with a cell that was hot
on A, per coin at most the heat.N_REL_WRITE strongest by lift on A.

  oheat_B   windows per day x odds points of the cell on B (how often x how sure): the cell as a call of its own
  lift_B    odds points of the cell over the trigger's OTHER events on B: what the second reading adds
  lheat_B   windows per day x lift_B: how often x how much the second reading adds
  lift2_B   odds points over the condition level's own effect (all minutes at that level)

Per coin and horizon the pack keeps the `top` cells by oheat_B and the `top-lift` by lheat_B, at most `per-trigger`
rows of one trigger in each list. Cells that are the same event under two names (identical sample and numbers on both
periods) are one row with `aliases`. `chance`: the same counts on the no-signal twins. A MAP on coin price
(2020-2025), not a Kalshi-price result. NEVER DOGE.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

from oracle import heat, heat_pack

NUM = ['share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B', 't_A', 't_B', 'oheat_B', 'lift_A', 'lift_B', 't_lift_A', 't_lift_B', 'lheat_B',
       'lift2_A', 'lift2_B', 't_lift2_A', 't_lift2_B', 'move_B', 'hold_B', 'hold_over_B', 'dip_B', 'wd_B', 'tick_B']
SAME = ['coin', 'h', 'dir', 'n_A', 'n_B', 'days_B', 'share_A', 'share_B', 'odds_A', 'odds_B', 't_A', 't_B', 'lift_A', 'lift_B', 'hold_B', 'dip_B']
SEP = '\x1f'


def view(j: pd.DataFrame, horizons) -> pd.DataFrame:
    """Every pair and triple cell of one coin's judged table (heat._judge) with a sample on both periods, each number
    signed in the direction of the cell's odds on A."""
    x = j[j.kind.isin(['pair', 'triple']) & j.h.isin(list(horizons)) & j.okA & (j.n_B >= heat.MIN_EVENTS) & (j.days_B >= heat.MIN_DAYS_B)
          & (j.rest_n_B >= heat.MIN_EVENTS) & (j.d_odds != 0)]
    d = x.d_odds.astype(float)
    up = (d > 0).to_numpy()
    v = x[['coin', 'kind', 'key', 'h', 'trig', 'cond', 'lv', 'n_A', 'n_B', 'days_B', 'tick_B']].copy()
    v['dir'] = d.astype(int)
    v['wd_B'] = x.wd_B.fillna(x.per_day_B)
    v['share_A'], v['share_B'] = np.where(up, x.p_up_A, x.p_dn_A) * 100, np.where(up, x.p_up_B, x.p_dn_B) * 100
    v['share_over_B'] = v.share_B - np.where(up, x.bp_up_B, x.bp_dn_B) * 100
    v['odds_A'], v['odds_B'] = x.edge_p_A * d * 100, x.edge_p_B * d * 100
    v['t_A'], v['t_B'] = x.t_p_A * d, x.t_p_B * d
    v['oheat_B'] = v.wd_B * v.odds_B
    v['lift_A'], v['lift_B'] = x.liftp_A * d * 100, x.liftp_B * d * 100                  # over the trigger's other events
    v['t_lift_A'], v['t_lift_B'] = x.t_liftp_A * d, x.t_liftp_B * d
    v['lheat_B'] = v.wd_B * v.lift_B
    v['lift2_A'], v['lift2_B'] = x.liftp2_A * d * 100, x.liftp2_B * d * 100              # over the condition level's own effect
    v['t_lift2_A'], v['t_lift2_B'] = x.t_liftp2_A * d, x.t_liftp2_B * d
    v['move_B'] = x.excess_B * d
    v['hold_B'] = np.where(up, x.hold_up_B, x.hold_dn_B)
    v['hold_over_B'] = v.hold_B - np.where(up, x.bh_up_B, x.bh_dn_B)
    v['dip_B'] = np.where(up, x.dip_up_B, -x.dip_dn_B)
    v['hot'], v['rep'] = x.hot_odds.to_numpy(bool), x.rep_odds.to_numpy(bool)
    return v


def judged(d: str) -> tuple:
    """(meta, judged table) of one coin directory, with the base rates of B the league uses."""
    with open(os.path.join(d, 'meta.json')) as f:
        mt = json.load(f)
    j = heat._judge(heat._join(pd.read_csv(os.path.join(d, 'heat.csv.gz'), low_memory=False)))
    bB = mt.get('base', {}).get('B', {})
    j['bp_up_B'] = j.h.map(lambda H: bB.get(str(int(H)), {}).get('p_up', np.nan))
    j['bp_dn_B'] = j.h.map(lambda H: bB.get(str(int(H)), {}).get('p_dn', np.nan))
    j['bh_up_B'], j['bh_dn_B'] = bB.get('hold_up') or np.nan, bB.get('hold_dn') or np.nan
    j['twin'], j['tw'] = int(mt['twin']) > 0, int(mt['twin'])
    return mt, j


def _f(x, nd: int = 4):
    return None if x is None or pd.isna(x) else round(float(x), nd)


def parts(trig: str, cond: str, lv: str) -> tuple:
    """(the trigger event key, [[reading, level], ...]): a triple's trig is `trigger | reading=level`."""
    when, *more = trig.split(' | ')
    return when, [m.rsplit('=', 1) for m in more] + [[cond, lv]]


def base_of(reading: str) -> str:
    """The reading whose zone edges a name needs: '5m:MOM10 sign' -> '5m:MOM10'."""
    return reading.removesuffix(' sign')


def stats(v: pd.DataFrame, h: int) -> dict:
    x = v[v.h == h]
    if not len(x):
        return {'cells': 0}
    q = lambda s, p: round(float(s.quantile(p)), 2)
    return {'cells': int(len(x)), 'kept_direction_on_B': round(float((x.odds_B > 0).mean()), 4), 'lift_kept_on_B': round(float((x.lift_B > 0).mean()), 4),
            't_B_2_or_more': round(float((x.t_B >= 2).mean()), 4), 't_lift_B_2_or_more': round(float((x.t_lift_B >= 2).mean()), 4),
            'p99_oheat_B': q(x.oheat_B, 0.99), 'max_oheat_B': round(float(x.oheat_B.max()), 2), 'p99_lheat_B': q(x.lheat_B, 0.99), 'max_lheat_B': round(float(x.lheat_B.max()), 2)}


def collapse(v: pd.DataFrame) -> pd.DataFrame:
    """One row per event: cells with identical samples and numbers on both periods are the same event."""
    v = v.sort_values(['h', 'oheat_B', 'key'], ascending=[True, False, True])
    grp = v.groupby([v[c].round(6) if c in NUM else v[c] for c in SAME], sort=False, dropna=False)
    v = v.assign(aliases=grp['key'].transform(lambda s: SEP.join(sorted(s))))
    return v[v.key == v.aliases.str.split(SEP).str[0]].copy()


def capped(c: pd.DataFrame, by: str, n: int, per_trigger: int) -> list:
    """The keys of the first n rows by `by` with at most per_trigger rows of one trigger."""
    out, seen = [], {}
    for r in c.sort_values([by, 'key'], ascending=[False, True]).itertuples():
        if seen.get(r.when, 0) < per_trigger:
            seen[r.when] = seen.get(r.when, 0) + 1
            out.append(r.key)
            if len(out) >= n:
                break
    return out


def build(tables: str, pack: dict, horizons=(15, 60), top: int = 40, top_lift: int = 20, per_trigger: int = 3, all_dir: str = '', log=print) -> dict:
    dirs = [d for d in sorted(os.listdir(tables)) if os.path.exists(os.path.join(tables, d, 'heat.csv.gz'))]
    if not dirs:
        raise SystemExit('no coin tables')
    if any('DOGE' in d.upper() for d in dirs):
        raise SystemExit('never DOGE')
    single_rank = {}
    for r in pack.get('rows', []):
        for k in [r['key']] + r.get('aliases', []):
            single_rank[(r['coin'], r['h'], k)] = r['rank_coin']
    rows, sha, tw_stats, real_stats, counts = [], {}, {}, {}, {}
    for d in dirs:
        mt, j = judged(os.path.join(tables, d))
        twi, coin = int(mt['twin']), mt['asset']
        v = view(j, horizons)
        if twi:
            for h in horizons:
                tw_stats.setdefault(h, []).append(dict(stats(v, h), set=mt['label']))
            log(f'{mt["label"]}: {len(v):,} cells (twin)')
            del j, v
            continue
        if mt.get('table_sha256') != pack.get('table_sha256', {}).get(coin):
            raise SystemExit(f'{coin}: the table is not the one the traded pack was built from')
        sha[coin] = mt.get('table_sha256')
        s = heat._direction(j)                                      # the triggers on their own (every single event level)
        s = s[s.h.isin(list(horizons))].set_index(['key', 'h'])[['dir', 'odds_B', 'wd_B', 'oheat_B']]
        del j
        for h in horizons:
            real_stats.setdefault(h, []).append(stats(v, h))
        if all_dir:
            os.makedirs(all_dir, exist_ok=True)
            v.to_csv(os.path.join(all_dir, f'pairs_{coin}.csv.gz'), index=False, compression='gzip', float_format='%.5g')
        c = collapse(v)
        counts[coin] = {'cells': int(len(v)), 'events': int(len(c)), 'pairs': int((c.kind == 'pair').sum()), 'triples': int((c.kind == 'triple').sum())}
        log(f'{coin}: {len(v):,} cells, {len(c):,} distinct events')
        del v
        pp = [parts(t, cd, lv) for t, cd, lv in zip(c.trig, c.cond.astype(str), c.lv.astype(str))]
        c['when'] = [p[0] for p in pp]
        c['conds'] = [p[1] for p in pp]
        for h in horizons:
            x = c[c.h == h].copy()
            x['rank_coin'] = x.oheat_B.rank(ascending=False, method='first').astype(int)
            x['rank_lift_coin'] = x.lheat_B.rank(ascending=False, method='first').astype(int)
            keep = set(capped(x, 'oheat_B', top, per_trigger)) | set(capped(x, 'lheat_B', top_lift, per_trigger))
            for r in x[x.key.isin(keep)].sort_values('rank_coin').itertuples():
                names = [r.when.rsplit('=', 1)[0]] + [cd for cd, _ in r.conds]
                al = [a for a in r.aliases.split(SEP) if a != r.key]
                for a in al:                                         # the readings an alias would need, for the edges file
                    t, rest = a.split(' | ', 1) if ' | ' in a else (a, '')
                    names += [t.rsplit('=', 1)[0]] + [m.rsplit('=', 1)[0] for m in rest.split(' | ') if m]
                tr = s.loc[(r.when, h)] if (r.when, h) in s.index else None
                rows.append({'coin': coin, 'h': int(h), 'kind': r.kind, 'key': r.key, 'aliases': al, 'when': r.when, 'conds': r.conds,
                             'dir': int(r.dir), 'call': 'up' if r.dir > 0 else 'down', 'rank_coin': int(r.rank_coin), 'rank_lift_coin': int(r.rank_lift_coin),
                             'n_A': int(r.n_A), 'n_B': int(r.n_B), 'days_B': int(r.days_B),
                             **{k: _f(getattr(r, k)) for k in NUM},
                             'hot_A': bool(r.hot), 'replicated_B': bool(r.rep),
                             'trigger': None if tr is None else {'dir': int(tr.dir), 'odds_B': _f(tr.odds_B), 'wd_B': _f(tr.wd_B), 'oheat_B': _f(tr.oheat_B),
                                                                 'rank_coin': single_rank.get((coin, int(h), r.when))},
                             'clock': any(n == 'UTC4h' for n in names), 'dominance': any(not n[:1].isdigit() and n != 'UTC4h' for n in names),
                             'readings': sorted({base_of(n) for n in names}), 'table_sha256': sha[coin]})
    chance = {}
    for h in horizons:
        rs, ts = [x for x in real_stats.get(h, []) if x['cells']], [x for x in tw_stats.get(h, []) if x['cells']]
        agg = lambda L, k, f: None if not L else round(float(f([x[k] for x in L])), 4)
        wavg = lambda L, k: None if not L else round(float(np.average([x[k] for x in L], weights=[x['cells'] for x in L])), 4)
        chance[str(h)] = {nm: {'cells': int(sum(x['cells'] for x in L)), 'kept_direction_on_B': wavg(L, 'kept_direction_on_B'), 'lift_kept_on_B': wavg(L, 'lift_kept_on_B'),
                               't_B_2_or_more': wavg(L, 't_B_2_or_more'), 't_lift_B_2_or_more': wavg(L, 't_lift_B_2_or_more'),
                               'p99_oheat_B': agg(L, 'p99_oheat_B', np.max), 'max_oheat_B': agg(L, 'max_oheat_B', np.max),
                               'p99_lheat_B': agg(L, 'p99_lheat_B', np.max), 'max_lheat_B': agg(L, 'max_lheat_B', np.max)}
                          for nm, L in (('real', rs), ('twin', ts)) if L}
        tmax, lmax = (chance[str(h)].get('twin') or {}).get('max_oheat_B'), (chance[str(h)].get('twin') or {}).get('max_lheat_B')
        for r in rows:
            if r['h'] == h:
                r['above_twin_max'] = None if tmax is None or r['oheat_B'] is None else bool(r['oheat_B'] > tmax)
                r['lift_above_twin_max'] = None if lmax is None or r['lheat_B'] is None else bool(r['lheat_B'] > lmax)
    return {'schema': 'oracle-heat-pairs-1', 'horizons': list(horizons), 'top': top, 'top_lift': top_lift, 'per_trigger': per_trigger,
            'data': 'Binance spot 1-minute bars, 2020-01-01 to 2025-12-31 UTC. A = 2020-2024 (the direction comes from A), B = 2025 (every *_B number).',
            'fires': 'A row fires at a minute close when its `when` event fires at that close (as in the traded pack) AND every reading in `conds` holds the '
                     'given level at the last CLOSED bar of its own timeframe (oracle.heat_live.active_keys(..., states=...)). UTC4h is the 4-hour UTC block of '
                     'the entry minute. The measured entry is the open of the next minute.',
            'rule': 'Every pair and triple cell the tables stored, with a sample on both periods; no pass mark is used as a filter. Per coin and horizon: the top '
                    f'{top} by oheat_B and the top {top_lift} by lheat_B, at most {per_trigger} rows of one trigger in each list. rank_coin / rank_lift_coin: among '
                    'all distinct pair and triple events of the coin at that horizon. Identical events are one row (aliases).',
            'units': {'oheat_B': 'windows per day x odds points', 'lift_B': 'odds points over the trigger\'s other events', 'lheat_B': 'windows per day x lift_B',
                      'lift2_B': 'odds points over the condition level\'s own effect', 'share_B': '% of events beyond the entry on the called side at the horizon',
                      'odds_B': 'points (half the shift in P(up) - P(down))', 'hold_B': 'minutes on the called side', 'dip_B': 'bps', 'wd_B': 'windows per day',
                      'trigger': 'the `when` event on its own at the same horizon (rank_coin: its rank in the traded pack, when it is in it)',
                      'hot_A / replicated_B': 'the league\'s own marks (information, not a filter)'},
            'limits': 'Only relationships with a cell that was hot on A were stored (per coin at most the strongest by lift on A), and the 170 strongest triggers per '
                      'coin were crossed with every reading; every other event level only with the clock and dominance states. Rows of one trigger are close relatives.',
            'chance': chance, 'counts': counts, 'table_sha256': sha, 'rows': rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tables', required=True)
    ap.add_argument('--pack', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--all', default='')
    ap.add_argument('--horizons', default='15,60')
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--top-lift', type=int, default=20)
    ap.add_argument('--per-trigger', type=int, default=3)
    ap.add_argument('--parity', default='')
    ap.add_argument('--metas', default='')
    ap.add_argument('--live-meta', default='')
    ap.add_argument('--stamp', default='')
    a = ap.parse_args()
    with open(a.pack) as f:
        pack = json.load(f)
    pp = build(a.tables, pack, tuple(int(x) for x in a.horizons.split(',')), a.top, a.top_lift, a.per_trigger, a.all)
    if a.stamp:
        pp['stamp'] = a.stamp
    if a.parity:
        par = heat_pack._coin_files(a.parity, 'parity.json')
        differ = sorted({heat_pack.indicator(n) for p in par.values() for n, _ in p.get('readings_that_differ', [])})
        pp['indicators_that_differ_live'] = differ
        for r in pp['rows']:
            r['live_parity'] = (not any(heat_pack.indicator(n) in differ for n in r['readings'])) if r['coin'] in par else None
    with open(a.out, 'w') as f:
        json.dump(pp, f, indent=1, allow_nan=False)
    n = pd.DataFrame(pp['rows']).groupby(['coin', 'h']).size() if pp['rows'] else {}
    print(f'{a.out}: {len(pp["rows"])} rows; per coin and horizon: {dict(n)}')
    print('chance:', json.dumps(pp['chance']))
    if a.live_meta:
        more = {}
        for r in pp['rows']:
            more.setdefault(r['coin'], set()).update(r['readings'])
        lm = heat_pack.live_meta(pack, heat_pack._coin_files(a.metas, 'meta.json'), more=more)
        with open(a.live_meta, 'w') as f:
            json.dump(lm, f, separators=(',', ':'), allow_nan=False)
        print(f'{a.live_meta}: ' + ', '.join(f'{c} {len(v["edges"])} readings with edges, {len(v["no_edges"])} without' for c, v in lm.items()))


if __name__ == '__main__':
    main()
