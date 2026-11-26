"""The level universe of Amendment 1 section 2: the league's direction rows for BTC and ETH at 15 minutes, aliases folded, ranked.

Same rule as oracle.heat_pack.build: rows that are the same event under two names (identical sample and numbers) are one row, the
first key (sorted) its name and the rest its aliases; rank_coin = rank by oheat_B inside the coin, ties by key. Never DOGE.
"""
import hashlib

import pandas as pd

NUM = ['share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B', 't_A', 't_B', 'oheat_B', 'move_B', 'hold_B', 'hold_over_B', 'best_B', 'dip_B', 'wd_B', 'tick_B']
SAME = ['coin', 'h', 'dir', 'n_A', 'n_B', 'days_B', 'share_A', 'share_B', 'odds_A', 'odds_B', 't_A', 't_B', 'hold_B', 'best_B', 'dip_B']


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load(path: str, coins=('BTC', 'ETH'), horizon: int = 15) -> list:
    df = pd.read_csv(path)
    if df.coin.astype(str).str.upper().str.contains('DOGE').any():
        raise SystemExit('never DOGE')
    d = df[df.coin.isin(list(coins)) & (df.h == horizon)].copy()
    d = d.sort_values(['coin', 'oheat_B', 'key'], ascending=[True, False, True])
    grp = d.groupby([d[c].round(6) if c in NUM else d[c] for c in SAME], sort=False, dropna=False)
    d['aliases'] = grp['key'].transform(lambda s: '\x1f'.join(sorted(s)))
    d = d[d.key == d.aliases.str.split('\x1f').str[0]].copy()
    rows = []
    for coin, c in d.groupby('coin', sort=True):
        c = c.sort_values(['oheat_B', 'key'], ascending=[False, True])
        for i, r in enumerate(c.itertuples(), 1):
            name = r.key.rsplit('=', 1)[0]
            tf = name.split(':', 1)[0] if ':' in name else ''
            rows.append({'coin': coin, 'h': int(r.h), 'key': r.key, 'aliases': [a for a in r.aliases.split('\x1f') if a != r.key], 'tf': tf,
                         'dir': int(r.dir), 'rank_coin': i, 'share_A': float(r.share_A), 'share_B': float(r.share_B),
                         'n_A': int(r.n_A), 'n_B': int(r.n_B), 'oheat_B': float(r.oheat_B)})
    return rows


def all_keys(rows: list, coin: str) -> list:
    """Every event key of the coin's rows, aliases included: what the engine has to compute."""
    out = []
    for r in rows:
        if r['coin'] == coin:
            out.append(r['key'])
            out.extend(r['aliases'])
    return sorted(set(out))
