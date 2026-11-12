#!/usr/bin/env python3
"""Price paths for the heat lane's round trips (loser study, Nov 12 2026). Runs on a GitHub runner, never on the server.

    python3 paths.py research/heat-losers/trips.json

For each traded Kalshi market in trips.json: the market (open/close time, result) and its 1-minute candlesticks from
Kalshi's public API; for each coin, Coinbase 1-minute spot candles over the trips' span. Prints one compact JSON line per
item (PATHMKT, PATHC, SPOT) for the study to parse from the job log. Read-only public endpoints, standard library only.
"""
import json
import sys
import time
import urllib.error
import urllib.request

KALSHI = 'https://api.elections.kalshi.com/trade-api/v2'
COINBASE = 'https://api.exchange.coinbase.com'
KEEP = ('open', 'low', 'high', 'close', 'open_dollars', 'low_dollars', 'high_dollars', 'close_dollars')


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'heat-loser-study/1.0', 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i + 1 < tries:
                time.sleep(2 ** i)
                continue
            return {'error': 'HTTP %d' % e.code}
        except Exception as e:  # noqa: BLE001 - report and go on
            if i + 1 < tries:
                time.sleep(2 ** i)
                continue
            return {'error': str(e)[:200]}
    return {'error': 'no reply'}


def iso_s(ts):
    return int(time.mktime(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')) - time.timezone)


def slim(c):
    out = {'t': c.get('end_period_ts'), 'v': c.get('volume'), 'oi': c.get('open_interest')}
    for k in ('yes_bid', 'yes_ask', 'price'):
        sub = c.get(k) or {}
        if isinstance(sub, dict):
            out[k] = {x: sub[x] for x in KEEP if x in sub and sub[x] is not None}
    return out


def main():
    trips = json.load(open(sys.argv[1]))
    tickers = sorted({t['ticker'] for t in trips})
    print('PATHINFO %s' % json.dumps({'trips': len(trips), 'tickers': len(tickers)}))
    for tk in tickers:
        m = get('%s/markets/%s' % (KALSHI, tk))
        mk = m.get('market') or {}
        keep = {k: mk.get(k) for k in ('ticker', 'event_ticker', 'open_time', 'close_time', 'expiration_time', 'status', 'result',
                                       'floor_strike', 'cap_strike', 'strike_type', 'expiration_value', 'settlement_value', 'settlement_value_dollars')}
        if 'error' in m:
            keep['error'] = m['error']
        print('PATHMKT %s' % json.dumps(keep, separators=(',', ':')))
        if not mk.get('open_time') or not mk.get('close_time'):
            continue
        series = tk.split('-')[0]
        a, b = iso_s(mk['open_time']), iso_s(mk['close_time'])
        c = get('%s/series/%s/markets/%s/candlesticks?start_ts=%d&end_ts=%d&period_interval=1' % (KALSHI, series, tk, a, b + 60))
        rows = [slim(x) for x in (c.get('candlesticks') or [])]
        print('PATHC %s %s' % (tk, json.dumps({'error': c.get('error'), 'rows': rows}, separators=(',', ':'))))
        time.sleep(0.12)
    # Coinbase spot, 1-minute, over the trips' span (300 candles a request).
    t0 = min(iso_s(t['closed']) for t in trips) - 3 * 3600
    t1 = max(iso_s(t['closed']) for t in trips) + 600
    for coin in ('BTC', 'ETH', 'SOL', 'XRP'):
        rows, s = [], t0
        while s < t1:
            e = min(t1, s + 300 * 60)
            r = get('%s/products/%s-USD/candles?granularity=60&start=%s&end=%s' % (
                COINBASE, coin, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(s)), time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(e))))
            if isinstance(r, list):
                rows.extend(r)
            else:
                print('SPOTERR %s %s' % (coin, json.dumps(r)))
            s = e
            time.sleep(0.3)
        rows = sorted({int(x[0]): x for x in rows}.values())
        print('SPOT %s %s' % (coin, json.dumps(rows, separators=(',', ':'))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
