"""Public price paths for the trips: the traded Kalshi markets (strike, result, 1-minute candles) and the coins' Coinbase
1-minute spot. Read-only public endpoints, standard library only; run on a GitHub runner, never on the server.

Everything is cached under one folder (private: the repository is public, so it never goes into a commit or a job log).
"""
import json
import os
import time
import urllib.error
import urllib.request

KALSHI = 'https://api.elections.kalshi.com/trade-api/v2'
COINBASE = 'https://api.exchange.coinbase.com'
MARKET_KEYS = ('ticker', 'open_time', 'close_time', 'status', 'result', 'floor_strike', 'cap_strike', 'strike_type',
               'expiration_value', 'settlement_value_dollars')


FETCH_ERRORS = 0     # requests that ended in an error (nightly.py reads the count: a day built on a failed join is not kept)


def get(url, tries=4):
    """JSON from a public endpoint; {'error': ...} after the retries (429 and 5xx back off)."""
    r = _get(url, tries)
    if isinstance(r, dict) and 'error' in r and len(r) == 1:
        global FETCH_ERRORS
        FETCH_ERRORS += 1
    return r


def _get(url, tries):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'loss-review/1.0', 'Accept': 'application/json'})
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


def iso_epoch(ts):
    import calendar
    return calendar.timegm(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S'))


def market_and_candles(ticker, cache):
    """({market fields}, [candles]) for one ticker; candles are the API's 1-minute rows (end_period_ts, yes_bid, yes_ask,
    price), cached as <cache>/k-<ticker>.json."""
    p = os.path.join(cache, 'k-%s.json' % ticker)
    if os.path.exists(p):
        d = json.load(open(p))
        return d['market'], d['candles']
    m = get('%s/markets/%s' % (KALSHI, ticker))
    mk = {k: (m.get('market') or {}).get(k) for k in MARKET_KEYS}
    candles = []
    if mk.get('open_time') and mk.get('close_time'):
        a, b = iso_epoch(mk['open_time']), iso_epoch(mk['close_time'])
        c = get('%s/series/%s/markets/%s/candlesticks?start_ts=%d&end_ts=%d&period_interval=1' % (KALSHI, ticker.split('-')[0], ticker, a, b + 60))
        candles = c.get('candlesticks') or []
        if 'error' in c or 'error' in m:
            return mk, candles  # not cached: try again next run
    if 'error' in m:
        return mk, candles
    json.dump({'market': mk, 'candles': candles}, open(p, 'w'))
    time.sleep(0.12)
    return mk, candles


def spot_minutes(coin, t0, t1, cache):
    """Coinbase 1-minute candles [start, low, high, open, close, volume] for COIN-USD between t0 and t1 (epoch seconds)."""
    p = os.path.join(cache, 's-%s-%d-%d.json' % (coin, t0 // 3600, t1 // 3600))
    if os.path.exists(p):
        return json.load(open(p))
    rows, s = [], int(t0)
    while s < t1:
        e = min(int(t1), s + 300 * 60)
        r = get('%s/products/%s-USD/candles?granularity=60&start=%s&end=%s' % (
            COINBASE, coin, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(s)), time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(e))))
        if isinstance(r, list):
            rows.extend(r)
        else:
            return []
        s = e
        time.sleep(0.3)
    rows = sorted({int(x[0]): x for x in rows}.values())
    json.dump(rows, open(p, 'w'))
    return rows
