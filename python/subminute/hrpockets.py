"""Round 4b (Nov 22 2026, recorded days only): do the resting buys that earned on the hourly ladders of the ten full-depth days hold on Kalshi's own history?

On the ten full-depth days (Nov 11 to 20) the hourly BTC ladder (KXBTCD, "will BTC be at or above K at the top of the hour") gave a resting NO buy at 70 to 90 cents,
placed from minute 30 to 50, a positive result on days it was not picked on. Ten days are one stretch of weather, so the same question is asked of Kalshi's own 1-minute
YES bid/ask candles of the hourly ladders on Drive (raw/kalshi-history, Apr 13 to Nov 6 2026, KXBTCD and KXETHD), in three recorded blocks, none used for two jobs:

  build   Apr 13 to Jul 31   the rules (side, price bucket, placement minutes, cancel minute, coin, six-hour block) are scored here
  check   Aug 1 to Oct 31    the rules with a positive build lower bound are judged here
  clean   Nov 1 to 6 on the candles, and the bot's own full-depth days Nov 11 to 20 replayed with the queue-aware simulation of maker.py

The scoring is pockets.py's, pointed at 60-minute windows: a resting buy at the best bid of its side, no maker fee on the crypto hourly series, held to settlement, a fill
read off the candles after the order ('thru' = the conservative reading). Placement minutes 1-10, 10-30, 30-50 (the same seconds as the hourly maker rules of coins.py),
cancel at minute 40, 55 or 59. The candles carry no index, so there is no index guard here.
Several strikes of one hour move together: the intervals are by day, as in pockets.py. Nothing is ordered; only aggregates are printed.
"""
import argparse
import json
import os

from subminute import hourly as HR
from subminute import pockets as PK

SETTINGS = {'PLACE': ((1, 10), (10, 30), (30, 50)), 'CANCEL': (40, 55, 59)}


def configure() -> dict:
    """Point pockets.py at hourly windows (and maker.py, lag.py at 3,600-second ones); returns what restore() needs."""
    old = {'pockets': {k: getattr(PK, k) for k in SETTINGS}, 'hourly': HR.configure()}
    for k, v in SETTINGS.items():
        setattr(PK, k, v)
    return old


def restore(old: dict) -> None:
    for k, v in old['pockets'].items():
        setattr(PK, k, v)
    HR.restore(old['hourly'])


def run(hist: str, grids: str, out_dir: str, first: str, last: str, split: str, clean: str, top: int = 30, n_clean: int = 30, assets=('BTC', 'ETH')) -> dict:
    old = configure()
    try:
        return PK.run(hist, grids, out_dir, first, last, split, clean, top, n_clean, assets, n=60, series_fmt='KX{asset}D')
    finally:
        restore(old)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--hist', required=True, help='a directory holding kalshi/KXBTCD/DAY.jsonl (and KXETHD)')
    ap.add_argument('--grids', default='', help='the hgrid-DAY.npz files of the full-depth days (named grid-DAY.npz), for the exact replay')
    ap.add_argument('--out', required=True)
    ap.add_argument('--first', default='2026-04-13')
    ap.add_argument('--last', default='2026-11-06')
    ap.add_argument('--split', default='2026-08-01')
    ap.add_argument('--clean', default='2026-11-01')
    ap.add_argument('--top', type=int, default=30)
    ap.add_argument('--n-clean', type=int, default=30)
    a = ap.parse_args()
    r = run(a.hist, a.grids, a.out, a.first, a.last, a.split, a.clean, a.top, a.n_clean)
    print('HEATLOOP hrpocket-summary ' + json.dumps({k: v for k, v in r.items() if k not in ('top_by_build', 'clean', 'map')}, sort_keys=True, default=float), flush=True)
    print('HEATLOOP hrpocket-map [side, bucket lo, place from minute, build net c, build fills, build gross if all filled c, check net c, lo, hi, check fills, check gross c, check $/h] '
          + json.dumps(r['map'], default=float), flush=True)
    print('HEATLOOP hrpocket-top ' + json.dumps(r['top_by_build'][:12], sort_keys=True, default=float)[:14000], flush=True)
    for i in range(0, len(r['clean']), 8):
        print(f'HEATLOOP hrpocket-clean{i // 8} ' + json.dumps(r['clean'][i:i + 8], sort_keys=True, default=float)[:14000], flush=True)
