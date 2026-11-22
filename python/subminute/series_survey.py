"""Round 5b (recorded days only, public endpoints, read only): which Kalshi series other than the crypto ones are hourly or daily, and do they pay a maker fee?

The crypto 15-minute and hourly series are not in the fee schedule's non-standard table, so a resting buy pays no maker fee (allpairs.fees). The same holds for
any other series that is not in that table (bot/kalshi/feeScheduleSnapshot.json). This lists the series Kalshi publishes by category and frequency, marks those
that are free to rest in, and samples the settled markets of the shortest-lived ones (how many a day, how long they live, spread of the last candle is NOT read).
Aggregates only; no key is used.
"""
import argparse
import collections
import json
import time
import urllib.parse
import urllib.request

BASE = 'https://api.elections.kalshi.com/trade-api/v2'


def get(path, params=None, tries=4):
    url = BASE + path + ('?' + urllib.parse.urlencode(params) if params else '')
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'research-survey', 'Accept': 'application/json'}), timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1:
                return {'error': str(e)[:120]}
            time.sleep(1 + 2 * i)


def main(snapshot: str, sample_days: int):
    ns = set(json.load(open(snapshot))['nonStandard'])
    r = get('/series')
    series = r.get('series') or []
    print('HEATLOOP survey series total', len(series), 'error', r.get('error'))
    by = collections.Counter((s.get('category') or '?', s.get('frequency') or '?') for s in series)
    print('HEATLOOP survey category x frequency ' + json.dumps({f'{k[0]}|{k[1]}': v for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:40]}, sort_keys=True))
    short = [s for s in series if (s.get('frequency') or '').lower() in ('hourly', 'daily', 'fifteen_min', '15min', 'minutely', 'custom') and s['ticker'] not in ns]
    print('HEATLOOP survey short-lived series with standard fees', len(short))
    rows = []
    for s in short:
        t = s['ticker']
        m = get('/markets', {'series_ticker': t, 'status': 'settled', 'limit': 200})
        ms = m.get('markets') or []
        if not ms:
            continue
        life = sorted((_ts(x.get('close_time')) - _ts(x.get('open_time'))) / 3600.0 for x in ms if x.get('close_time') and x.get('open_time'))
        vol = sorted(float(x.get('volume_fp') or x.get('volume') or 0) for x in ms)
        days = {str(x.get('close_time'))[:10] for x in ms}
        rows.append({'series': t, 'category': s.get('category'), 'frequency': s.get('frequency'), 'title': (s.get('title') or '')[:48], 'markets_in_page': len(ms), 'close_days_in_page': len(days),
                     'median_life_h': round(life[len(life) // 2], 2) if life else None, 'median_volume': vol[len(vol) // 2], 'p90_volume': vol[int(len(vol) * 0.9)], 'more': bool(m.get('cursor'))})
    rows.sort(key=lambda x: -(x['median_volume'] or 0))
    print('HEATLOOP survey top ' + json.dumps(rows[:60], sort_keys=True))


def _ts(s):
    import datetime as dt
    return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--snapshot', default='../bot/kalshi/feeScheduleSnapshot.json')
    ap.add_argument('--sample-days', type=int, default=3)
    a = ap.parse_args()
    main(a.snapshot, a.sample_days)
