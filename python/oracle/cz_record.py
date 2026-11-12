"""Coinalyze forward recorder (research only): saves what Coinalyze still holds for the Binance perps of BTC, ETH, SOL, XRP.

Why: Coinalyze keeps 1-minute data for about 1.6 days (liquidations about 10 days) and Binance's own archive has no
liquidations at all, so anything not saved is lost. Parity with the Binance archive (Nov 11 2026, every minute, four coins):
1-minute perp bars incl. taker-buy volume identical to the um klines; open interest identical to metrics at S = create_time
+ 5 min; the long/short ratio is metrics' count_long_short_ratio. Note: /mnt/project-files/outside-data/coinalyze-check.md.

    python -m oracle.cz_record pull --out DIR [--hours 36]

The API key comes ONLY from the environment variable COINALYZE_API_KEY (a GitHub secret); it is never printed, logged or
written. Output: DIR/cz-<YYYYMMDDTHHMMZ>.json.gz (every endpoint, every coin, raw history rows) plus counts on stdout.
Overlapping pulls are fine: a reader de-duplicates on (symbol, endpoint, interval, t). Pacing: one call per 7 s (each call
covers four symbols, and Coinalyze counts 40 symbol-calls a minute); a 429 waits for Retry-After. NEVER DOGE.
Times: UTC (EST = UTC - 5 h).
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://api.coinalyze.net/v1/'
COINS = ('BTC', 'ETH', 'SOL', 'XRP')
SYMBOLS = tuple(f'{c}USDT_PERP.A' for c in COINS)          # .A = Binance on Coinalyze
PULLS = (('ohlcv-history', '1min'), ('open-interest-history', '1min'), ('liquidation-history', '1min'),
         ('long-short-ratio-history', '5min'), ('funding-rate-history', '1min'), ('predicted-funding-rate-history', '1min'))
PACE_S = 7.0


def _key() -> str:
    k = os.environ.get('COINALYZE_API_KEY', '').strip()
    if not k:
        raise SystemExit('COINALYZE_API_KEY is not set (add it as a repository secret)')
    return k


def call(endpoint: str, params: dict, key: str, opener=urllib.request.urlopen, sleep=time.sleep, tries: int = 5):
    url = BASE + endpoint + '?' + urllib.parse.urlencode(params)
    for i in range(tries):
        req = urllib.request.Request(url, headers={'api_key': key})
        try:
            with opener(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                sleep(float(e.headers.get('Retry-After', '10') or 10) + 1)
                continue
            if e.code in (500, 502, 503, 504) and i < tries - 1:
                sleep(5 * (i + 1))
                continue
            raise SystemExit(f'{endpoint}: HTTP {e.code}') from None
        except urllib.error.URLError:
            if i < tries - 1:
                sleep(5 * (i + 1))
                continue
            raise SystemExit(f'{endpoint}: network error') from None


def pull(out: str, hours: float = 36.0, now: float | None = None, opener=urllib.request.urlopen, sleep=time.sleep) -> str:
    key = _key()
    now = int(now if now is not None else time.time())
    frm = now - int(hours * 3600)
    stamp = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    res = {'pulled_at_utc': stamp.isoformat(timespec='seconds'), 'from': frm, 'to': now, 'symbols': list(SYMBOLS), 'data': {}}
    for j, (ep, iv) in enumerate(PULLS):
        if j:
            sleep(PACE_S)
        d = call(ep, {'symbols': ','.join(SYMBOLS), 'interval': iv, 'from': frm, 'to': now}, key, opener, sleep)
        got = {x['symbol']: x.get('history', []) for x in d if x.get('symbol') in SYMBOLS}
        res['data'][f'{ep}|{iv}'] = got
        print(ep, iv, ' '.join(f'{s.split("USDT")[0]}={len(h)}' for s, h in sorted(got.items())), flush=True)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, 'cz-' + stamp.strftime('%Y%m%dT%H%MZ') + '.json.gz')
    with gzip.open(path, 'wt') as f:
        json.dump(res, f)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='cz_record')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('pull')
    p.add_argument('--out', required=True)
    p.add_argument('--hours', type=float, default=36.0)
    a = ap.parse_args(argv)
    print('saved', os.path.basename(pull(a.out, a.hours)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
