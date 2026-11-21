"""Coverage of one coin's Binance 1-minute CSV (Amendment 1 needs the first and last day on file). Reads the `ts` column only:
no price is loaded, so this cannot leak an outcome. Prints one line, aggregates only:

    HEATLOOP coverage {"coin": "BTC", "rows": ..., "first": "...", "last": "...", "months": {"2026-07": [rows, missing minutes]}}

    python3 -m heatloop.coverage --coin BTC --csv data/hist/binance-1m/BTC/1m.csv
"""
import argparse
import datetime as dt
import json

import pandas as pd

MIN = 60_000


def report(ts, coin: str, since: str = '2025-07-01') -> dict:
    ts = pd.Series(ts, dtype='int64').drop_duplicates().sort_values()
    if ts.empty:
        return {'coin': coin, 'rows': 0}
    s = int(dt.datetime.strptime(since, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    out = {'coin': coin, 'rows': int(len(ts)), 'first': _iso(int(ts.iloc[0])), 'last': _iso(int(ts.iloc[-1])), 'since': since, 'months': {}}
    t = ts[ts >= s]
    if t.empty:
        return out
    last = int(t.iloc[-1])
    month = pd.to_datetime(t, unit='ms', utc=True).dt.strftime('%Y-%m')
    for m, g in t.groupby(month):
        lo = int(g.iloc[0])
        first_of_month = int(dt.datetime.strptime(m + '-01', '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        nxt = (dt.datetime.strptime(m + '-01', '%Y-%m-%d') + dt.timedelta(days=32)).replace(day=1, tzinfo=dt.timezone.utc)
        hi = min(int(nxt.timestamp() * 1000) - MIN, last)
        want = (hi - max(first_of_month, s)) // MIN + 1
        out['months'][m] = [int(len(g)), int(max(0, want - len(g)))]
    return out


def _iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime('%Y-%m-%d %H:%M')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--coin', required=True)
    ap.add_argument('--csv', required=True)
    ap.add_argument('--since', default='2025-07-01')
    a = ap.parse_args()
    if a.coin.upper() == 'DOGE':
        raise SystemExit('NEVER DOGE')
    df = pd.read_csv(a.csv, usecols=['ts'])
    print('HEATLOOP coverage ' + json.dumps(report(df['ts'].to_numpy(), a.coin.upper(), a.since), sort_keys=True))


if __name__ == '__main__':
    main()
