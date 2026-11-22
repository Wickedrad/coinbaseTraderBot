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


KEEP = ('financ', 'econom', 'climate', 'weather', 'commod', 'crypto', 'energy', 'world', 'science', 'tech', 'mention')
FREQ = ('hourly', 'daily', 'fifteen_min', '15min', 'minutely')


def probe(s):
    t = s['ticker']
    m = get('/markets', {'series_ticker': t, 'status': 'settled', 'limit': 200}, tries=2)
    ms = m.get('markets') or []
    if not ms:
        return None
    life = sorted((_ts(x.get('close_time')) - _ts(x.get('open_time'))) / 3600.0 for x in ms if x.get('close_time') and x.get('open_time'))
    vol = sorted(float(x.get('volume_fp') or x.get('volume') or 0) for x in ms)
    days = {str(x.get('close_time'))[:10] for x in ms}
    return {'series': t, 'category': s.get('category'), 'frequency': s.get('frequency'), 'title': (s.get('title') or '')[:48], 'markets_in_page': len(ms), 'close_days_in_page': len(days),
            'median_life_h': round(life[len(life) // 2], 2) if life else None, 'median_volume': vol[len(vol) // 2], 'p90_volume': vol[int(len(vol) * 0.9)], 'more': bool(m.get('cursor'))}


def main(snapshot: str, budget_s: int):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    t0 = time.time()
    ns = set(json.load(open(snapshot))['nonStandard'])
    r = get('/series')
    series = r.get('series') or []
    print('HEATLOOP survey series total', len(series), 'error', r.get('error'), flush=True)
    by = collections.Counter((s.get('category') or '?', s.get('frequency') or '?') for s in series)
    print('HEATLOOP survey category x frequency ' + json.dumps({f'{k[0]}|{k[1]}': v for k, v in sorted(by.items(), key=lambda kv: -kv[1])[:40]}, sort_keys=True), flush=True)
    short = [s for s in series if (s.get('frequency') or '').lower() in FREQ and s['ticker'] not in ns and any(k in (s.get('category') or '').lower() for k in KEEP)]
    crypto = [s['ticker'] for s in short if any(a in s['ticker'] for a in ('KXBTC', 'KXETH', 'KXSOL', 'KXXRP'))]
    short = [s for s in short if s['ticker'] not in set(crypto)]
    print('HEATLOOP survey candidates (hourly or daily, standard fees, finance-like categories, crypto four excluded)', len(short), 'crypto four skipped', len(crypto), flush=True)
    rows = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(probe, s) for s in short]
        for f in as_completed(futs):
            if time.time() - t0 > budget_s:
                for g in futs:
                    g.cancel()
                print('HEATLOOP survey stopped at the time budget; probed', len(rows), 'of', len(short), flush=True)
                break
            try:
                x = f.result()
            except Exception:
                x = None
            if x:
                rows.append(x)
    rows.sort(key=lambda x: -(x['median_volume'] or 0))
    print('HEATLOOP survey probed', len(rows), 'series with settled markets; top by median volume ' + json.dumps(rows[:45], sort_keys=True), flush=True)


def _ts(s):
    import datetime as dt
    return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--snapshot', default='../bot/kalshi/feeScheduleSnapshot.json')
    ap.add_argument('--budget-s', type=int, default=600)
    a = ap.parse_args()
    main(a.snapshot, a.budget_s)
