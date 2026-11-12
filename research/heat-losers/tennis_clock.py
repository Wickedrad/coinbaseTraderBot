#!/usr/bin/env python3
"""Tennis match clock check (Nov 12 2026). Runs on a GitHub runner, never on the server.

    python3 tennis_clock.py 2026-11-12T10:00:00

Every Kalshi tennis match market (KXATPMATCH, KXWTAMATCH) that closes after SINCE: its published times (the bot reads
occurrence_datetime, else expected_start_time, event_start_time, start_time) and a compact 1-minute candle path
[t, yes_bid, yes_ask, last, volume] from SINCE minus 6 hours, so the real start (when the price begins to move on volume)
and the end (price pinned near 0 or 1, trading stopped) can be read against the published start. Prints TNMKT, TNEVT and
TNC lines. Read-only public endpoints, standard library only.
"""
import json
import sys
import time
import urllib.error
import urllib.request

KALSHI = 'https://api.elections.kalshi.com/trade-api/v2'
SERIES = ('KXATPMATCH', 'KXWTAMATCH')


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'tennis-clock-check/1.0', 'Accept': 'application/json'})
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


def dol(sub):
    if not isinstance(sub, dict):
        return None
    v = sub.get('close_dollars')
    if v is None and sub.get('close') is not None:
        v = float(sub['close']) / 100
    return None if v is None else round(float(v), 4)


def main():
    since = iso_s(sys.argv[1] if len(sys.argv) > 1 else '2026-11-12T10:00:00')
    now = int(time.time())
    events = set()
    for series in SERIES:
        cursor, n = '', 0
        while True:
            r = get('%s/markets?series_ticker=%s&min_close_ts=%d&limit=1000%s' % (KALSHI, series, since, '&cursor=' + cursor if cursor else ''))
            ms = r.get('markets') or []
            for mk in ms:
                keep = {k: v for k, v in mk.items() if 'time' in k or 'date' in k or k in (
                    'ticker', 'event_ticker', 'title', 'subtitle', 'yes_sub_title', 'status', 'result', 'volume', 'volume_fp',
                    'last_price_dollars', 'settlement_ts')}
                print('TNMKT %s' % json.dumps(keep, separators=(',', ':')))
                events.add(mk.get('event_ticker'))
                n += 1
                o = iso_s(mk['open_time']) if mk.get('open_time') else None
                c = iso_s(mk['close_time']) if mk.get('close_time') else None
                if o is None or c is None or o > now:
                    continue
                a, b = max(o, since - 6 * 3600), min(c + 60, now)
                if b <= a:
                    continue
                rows = []
                s = a
                while s < b:
                    e = min(b, s + 4800 * 60)
                    cr = get('%s/series/%s/markets/%s/candlesticks?start_ts=%d&end_ts=%d&period_interval=1' % (KALSHI, series, mk['ticker'], s, e))
                    for x in cr.get('candlesticks') or []:
                        pr = x.get('price') or {}
                        rows.append([x.get('end_period_ts'), dol(x.get('yes_bid')), dol(x.get('yes_ask')), dol(pr), x.get('volume_fp', x.get('volume'))])
                    if cr.get('error'):
                        rows.append(['error', cr['error']])
                    s = e
                    time.sleep(0.1)
                print('TNC %s %s' % (mk['ticker'], json.dumps(rows, separators=(',', ':'))))
            cursor = r.get('cursor') or ''
            if not cursor or not ms:
                break
        print('TNINFO %s' % json.dumps({'series': series, 'markets': n, 'error': r.get('error')}))
    for ev in sorted(e for e in events if e):
        r = get('%s/events/%s' % (KALSHI, ev))
        e = r.get('event') or {}
        print('TNEVT %s' % json.dumps({k: v for k, v in e.items() if k != 'markets' and (isinstance(v, (str, int, float, bool)) or v is None)}, separators=(',', ':'))[:800])
        time.sleep(0.1)


if __name__ == '__main__':
    main()
