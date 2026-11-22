"""Round 4b (Nov 22 2026, recorded days only): the hourly ladders (KXBTCD, KXETHD, KXSOLD, KXXRPD: "will the coin be at or above K at the top of the hour") through
the same questions as the 15-minute series, coin by coin.

The bot's own recording holds them with books and taker trades (the series inventory of Nov 18: KXBTCD about 218 markets, 57 million book deltas and 486 thousand
trades a day, KXETHD 180, KXSOLD 180, KXXRPD 128). grid.py --hourly reduces each tracked ladder market to 1-second grids over the last hour before its close
(hgrid-DAY.npz, same keys as the 15-minute grids). This module points the lag and maker code at a 3,600-second window and runs coins.run on them:
  1. is the ladder's book late by seconds behind the index, the fast spot or the perpetual (information R^2 and the follow/flip trade cells)?
  2. do resting buys at the best bid of a side (the crypto hourly series are not in Kalshi's non-standard fee table: maker fee 0), queue-aware fills from the recorded
     trades, held to settlement, earn after the build days pick and the check days judge? A pick made on three coins, judged on the fourth.
Several strikes of one hour move together, so the day-cluster intervals are the honest ones and the sample is hours, not markets. Nothing is ordered.
"""
import argparse
import json

from subminute import coins as CN
from subminute import lag as LG
from subminute import maker as MK

SETTINGS = {'LG.WIN': 3600, 'MK.WIN': 3600, 'LG.RANGES': ((60, 600), (600, 1800), (1800, 3300)), 'LG.INFO_HI': 3540,
            'MK.PLACE': ((60, 600), (600, 1800), (1800, 3000)), 'MK.CANCEL': (2400, 3300, 3540)}


def configure() -> dict:
    """Point the 15-minute code at hourly windows; returns the values it replaced so that restore() can put them back."""
    old = {}
    for key, v in SETTINGS.items():
        mod, name = key.split('.')
        m = LG if mod == 'LG' else MK
        old[key] = getattr(m, name)
        setattr(m, name, v)
    return old


def restore(old: dict) -> None:
    for key, v in old.items():
        mod, name = key.split('.')
        setattr(LG if mod == 'LG' else MK, name, v)


def run(grids_dir: str, build_last: str, out_dir: str) -> dict:
    old = configure()
    try:
        return CN.run(grids_dir, build_last, out_dir)
    finally:
        restore(old)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--grids', required=True, help='the hgrid-DAY.npz files (grid.py --hourly), named grid-DAY.npz in this directory')
    ap.add_argument('--build-last', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    r = run(a.grids, a.build_last, a.out)
    print('HEATLOOP hrcoin-digest ' + json.dumps(CN.digest(r), sort_keys=True, default=float)[:14000], flush=True)
