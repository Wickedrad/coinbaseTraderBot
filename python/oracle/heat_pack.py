"""The traded pack of the OR-HM1 direction league: the calls a bot lane can act on, ranked, with nothing cut by a
pass mark (python/oracle/prereg/OR-HM1.md, Amendments 3 and 4).

  python3 -m oracle.heat_pack --direction <direction_all.csv.gz | league_direction.csv.gz> --summary <summary.json>
                              --out <traded_pack.json> [--horizons 15,60] [--top 40] [--top-share 20]

Per coin and horizon: the `top` event levels by heat on B (windows per day x odds points) and the `top-share` by share
right over the base rate (at least DIR_MIN_WD windows per day). Readings that are the same event under two names
(identical sample and identical numbers on both periods, e.g. RSI14 and CMO14) are one row with `aliases`.
rank_coin / rank_all: by heat inside the coin / across the coins at that horizon. batch10: the ten hottest across
the coins (one row per coin and event), the default batch of Amendment 3. `chance` holds the no-signal twins' scale
for the same horizon. A MAP on coin price (2020-2025), not a Kalshi-price result. NEVER DOGE.
"""
import argparse
import json

import pandas as pd

from oracle import heat

NUM = ['share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B', 't_A', 't_B', 'oheat_B', 'move_B', 'hold_B', 'hold_over_B', 'best_B', 'dip_B', 'wd_B', 'tick_B']
SAME = ['coin', 'h', 'dir', 'n_A', 'n_B', 'days_B', 'share_A', 'share_B', 'odds_A', 'odds_B', 't_A', 't_B', 'hold_B', 'best_B', 'dip_B']


def build(direction: pd.DataFrame, summary: dict, horizons=(15, 60), top: int = 40, top_share: int = 20, source: str = '') -> dict:
    d = direction[~direction.coin.astype(str).str.contains('twin') & direction.h.isin(list(horizons))].copy()
    if d.coin.astype(str).str.upper().str.contains('DOGE').any():
        raise SystemExit('never DOGE')
    d = d.sort_values(['coin', 'h', 'oheat_B', 'key'], ascending=[True, True, False, True])
    # one row per event: names with identical samples and numbers are the same event
    grp = d.groupby([d[c].round(6) if c in NUM else d[c] for c in SAME], sort=False, dropna=False)
    d['aliases'] = grp['key'].transform(lambda s: '\x1f'.join(sorted(s)))
    d = d[d.key == d.aliases.str.split('\x1f').str[0]].copy()
    metas = summary.get('metas', {})
    sha = {k: v.get('table_sha256') for k, v in metas.items() if '~' not in k and 'twin' not in k}
    chance = {}
    for h in horizons:
        w = summary.get('direction', {}).get(str(h), {})
        chance[str(h)] = {nm: {k: w[nm].get(k) for k in ('levels', 'kept_direction_on_B', 't_B_2_or_more', 'median_odds_B', 'p99_odds_heat_B', 'max_odds_heat_B',
                                                         'p99_share_over_B', 'max_share_over_B')} for nm in ('real', 'twin') if nm in w}
    rows, literal, complete = [], {}, {}
    floor = float(direction.oheat_B.min()) if len(direction) else 0.0
    whole = 'direction_all' in source
    for h in horizons:
        x = direction[~direction.coin.astype(str).str.contains('twin') & (direction.h == h)].sort_values(['oheat_B', 'coin', 'key'], ascending=[False, True, True])
        literal[str(h)] = [{'coin': r.coin, 'key': r.key, 'oheat_B': round(float(r.oheat_B), 2)} for r in x.head(10).itertuples()]
        dh = d[d.h == h].copy()
        dh['rank_all'] = dh.oheat_B.rank(ascending=False, method='first').astype(int)
        tmax = (chance[str(h)].get('twin') or {}).get('max_odds_heat_B')
        for coin, c in dh.groupby('coin', sort=True):
            c = c.sort_values(['oheat_B', 'key'], ascending=[False, True]).copy()
            c['rank_coin'] = range(1, len(c) + 1)
            s = c[c.wd_B >= heat.DIR_MIN_WD].sort_values(['share_over_B', 'key'], ascending=[False, True])
            c['rank_share_coin'] = c.key.map({k: i + 1 for i, k in enumerate(s.key)})
            keep = c[(c.rank_coin <= top) | (c.rank_share_coin <= top_share)]
            complete[f'{coin}:{h}'] = bool(whole or len(c) > top)
            for r in keep.itertuples():
                tf, rest = r.key.split(':', 1)
                reading, level = rest.rsplit('=', 1)
                al = [a for a in r.aliases.split('\x1f') if a != r.key]
                rows.append({'coin': coin, 'h': int(h), 'key': r.key, 'aliases': al, 'tf': tf, 'reading': reading, 'level': level,
                             'dir': int(r.dir), 'call': 'up' if r.dir > 0 else 'down',
                             'rank_coin': int(r.rank_coin), 'rank_all': int(r.rank_all), 'batch10': bool(r.rank_all <= 10),
                             'rank_share_coin': None if pd.isna(r.rank_share_coin) else int(r.rank_share_coin),
                             'above_twin_max': None if tmax is None else bool(r.oheat_B > tmax),
                             'n_A': int(r.n_A), 'n_B': int(r.n_B), 'days_B': int(r.days_B),
                             **{k: round(float(getattr(r, k)), 4) for k in NUM},
                             'table_sha256': sha.get(coin)})
    return {'schema': 'oracle-heat-pack-1', 'source': source, 'horizons': list(horizons), 'top': top, 'top_share': top_share,
            'data': 'Binance spot 1-minute bars, 2020-01-01 to 2025-12-31 UTC. A = 2020-2024 (the direction comes from A), B = 2025 (every *_B number).',
            'entry': 'A reading is known at its bar close; the measured entry is the open of the next minute.',
            'rule': 'Per coin and horizon: the top event levels by oheat_B (windows per day x odds points on B) and by share_over_B (at least '
                    f'{heat.DIR_MIN_WD} windows per day). No pass mark is used as a filter. Names with identical samples and numbers are one row (aliases). '
                    'batch10 = the ten hottest across the coins at that horizon, one row per coin and event (OR-HM1 Amendment 3 default batch).',
            'units': {'share_B': '% of events beyond the entry on the called side at the horizon', 'share_over_B': 'points over the base rate',
                      'odds_B': 'points (half the shift in P(up) - P(down))', 'oheat_B': 'windows per day x odds points', 'hold_B': 'minutes on the called side',
                      'dip_B': 'bps, usual move against the call before the best point', 'best_B': 'bps', 'move_B': 'bps on the called side', 'wd_B': 'windows per day',
                      'tick_B': 'the coin price step in bps'},
            'chance': chance, 'table_sha256': sha, 'complete': complete, 'file_heat_floor': None if whole else round(floor, 2),
            'batch_amendment3_literal': literal, 'rows': rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--direction', required=True)
    ap.add_argument('--summary', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--horizons', default='15,60')
    ap.add_argument('--top', type=int, default=40)
    ap.add_argument('--top-share', type=int, default=20)
    ap.add_argument('--stamp', default='')
    a = ap.parse_args()
    d = pd.read_csv(a.direction)
    pack = build(d, json.load(open(a.summary)), tuple(int(x) for x in a.horizons.split(',')), a.top, a.top_share, source=a.direction.rsplit('/', 1)[-1])
    if a.stamp:
        pack['stamp'] = a.stamp
    with open(a.out, 'w') as f:
        json.dump(pack, f, indent=1, allow_nan=False)
    n = pd.DataFrame(pack['rows']).groupby(['coin', 'h']).size()
    print(f'{a.out}: {len(pack["rows"])} rows; per coin and horizon: {n.to_dict()}; complete: {pack["complete"]}')


if __name__ == '__main__':
    main()
