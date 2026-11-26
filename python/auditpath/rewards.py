"""Part 3 of the audit path (research/audit_path/PREREG-AP.md): Kalshi's live reward (incentive) programs, read once
from the public API. Read only: no account, no key, no order. Prints aggregates and the crypto rows (public data).

    cd python && python3 -m auditpath.rewards [--out out.json] [--pool 200] [--from-file saved.json]

--from-file reads a saved {"programs": [...], "schedules": [...]} instead of the API (tests, re-reads of a kept copy).
The test is fixed in the pre-registration: best-case share = min(1, s / target size) for size s on both sides, a
market's program pays nothing under $1.00, CLOSED when no crypto 15-minute or hourly market is in a liquidity program,
when the smallest target size is more than the pool can post, or when the summed ceiling is under $1 an hour. NEVER DOGE.
"""
import argparse
import collections
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASES = ('https://api.elections.kalshi.com/trade-api/v2', 'https://external-api.kalshi.com/trade-api/v2')
COINS = ('BTC', 'ETH', 'SOL', 'XRP')            # DOGE is excluded from all research
CENTICENTS = 10000.0                            # period_reward and max_reward_per_account are in centi-cents
MIN_PAYOUT = 1.00                               # a market's program pays nothing under $1.00 (help article 13823851)
PAIR_COST = 1.00                                # dollars to rest one contract on each side near 50c (ceiling on size)
PASS_PER_HOUR = 1.00                            # the audit thread's own line


def http_json(path: str, params: dict, tries: int = 4, pause: float = 2.0) -> dict:
    """GET path on the first base that answers; a generic client name, no account."""
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})
    last = None
    for base in BASES:
        url = f'{base}{path}' + (f'?{q}' if q else '')
        for i in range(tries):
            try:
                req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'research-reader/1.0'})
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode('utf-8'))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:   # HTTPError is a URLError
                last = e
                code = getattr(e, 'code', None)
                if code in (400, 401, 403, 404):
                    break                       # this base will not answer differently: try the next one
                time.sleep(pause * (i + 1))
    raise RuntimeError(f'{path}: no base answered ({last})')


def fetch_programs(status: str, limit: int = 1000, max_pages: int = 200) -> list:
    rows, cursor = [], None
    for _ in range(max_pages):
        d = http_json('/incentive_programs', {'status': status, 'limit': limit, 'cursor': cursor})
        rows.extend(d.get('incentive_programs') or [])
        cursor = d.get('next_cursor')
        if not cursor:
            break
    return rows


def fetch_schedules() -> list:
    return http_json('/incentive_schedules', {}).get('schedules') or []


def series_of(row: dict) -> str:
    s = row.get('series_ticker') or ''
    if s:
        return s
    return (row.get('market_ticker') or row.get('event_ticker') or '').split('-')[0]


def coin_of(series: str):
    """BTC | ETH | SOL | XRP for a crypto series of those coins, else None. DOGE never matches."""
    s = series.upper()
    if not s.startswith('KX'):
        return None
    for c in COINS:
        if s[2:].startswith(c):
            return c
    return None


def kind_of(series: str) -> str:
    s = series.upper()
    if s.endswith('15M'):
        return '15-minute'
    for c in COINS:
        if s == f'KX{c}D':
            return 'hourly ladder'
        if s == f'KX{c}':
            return 'range ladder'
    return 'other crypto'


def parse_ts(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace('Z', '+00:00')).astimezone(timezone.utc)
    except ValueError:
        return None


def usd(cc) -> float:
    return (cc or 0) / CENTICENTS


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def program_row(p: dict) -> dict:
    a, b = parse_ts(p.get('start_date')), parse_ts(p.get('end_date'))
    hours = (b - a).total_seconds() / 3600.0 if a and b and b > a else None
    reward = usd(p.get('period_reward'))
    return {
        'series': series_of(p), 'market': p.get('market_ticker') or '', 'type': p.get('incentive_type') or '',
        'reward': reward, 'hours': hours, 'per_day': reward * 24.0 / hours if hours else None,
        'target': fnum(p.get('target_size_fp')), 'discount_bps': p.get('discount_factor_bps'),
        'cap': usd(p.get('max_reward_per_account')) if p.get('max_reward_per_account') is not None else None,
        'start': p.get('start_date'), 'end': p.get('end_date'), 'desc': (p.get('incentive_description') or '')[:120],
    }


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def span(xs, fmt='{:.2f}'):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return 'n/a'
    return ' / '.join(fmt.format(v) for v in (xs[0], statistics.median(xs), xs[-1]))


def ceiling(rows: list, size: float) -> float:
    """Best-case dollars for resting `size` contracts on both sides of every market in rows, for the whole period:
    share = min(1, size / target), a market's program under $1.00 pays nothing. Liquidity programs only."""
    total = 0.0
    for r in rows:
        if r['type'] != 'liquidity' or not r['target'] or r['target'] <= 0:
            continue
        got = min(1.0, size / r['target']) * r['reward']
        if got >= MIN_PAYOUT:
            total += got
    return total


def summarize(programs: list, schedules: list, pool: float, label: str) -> dict:
    rows = [program_row(p) for p in programs]
    out = {'label': label, 'n': len(rows)}
    by_type = collections.Counter(r['type'] for r in rows)
    usd_type = collections.defaultdict(float)
    for r in rows:
        usd_type[r['type']] += r['reward']
    print(f'\n== {label}: {len(rows)} programs')
    for t, n in by_type.most_common():
        print(f'   {t or "?":22s} {n:6d} programs   ${usd_type[t]:,.0f} in period rewards')
    by_series = collections.defaultdict(list)
    for r in rows:
        by_series[(r['series'], r['type'])].append(r)
    top = sorted(by_series.items(), key=lambda kv: -sum(r['reward'] for r in kv[1]))[:25]
    print('   largest series (series, type, markets, period rewards, median target size, median period hours):')
    for (s, t), rs in top:
        tg, hr = med([r['target'] for r in rs]), med([r['hours'] for r in rs])
        print(f'     {s:28s} {t:10s} {len(rs):5d}  ${sum(r["reward"] for r in rs):>10,.0f}  target {tg if tg is not None else "n/a"}  hours {round(hr, 1) if hr else "n/a"}')
    crypto = [r for r in rows if coin_of(r['series'])]
    out['crypto_n'] = len(crypto)
    print(f'   crypto rows (BTC, ETH, SOL, XRP series): {len(crypto)}')
    groups = collections.defaultdict(list)
    for r in crypto:
        groups[(r['series'], kind_of(r['series']), r['type'])].append(r)
    table = []
    for (s, k, t), rs in sorted(groups.items()):
        row = {
            'series': s, 'kind': k, 'type': t, 'markets': len(rs),
            'reward_min_med_max': span([r['reward'] for r in rs]), 'hours_min_med_max': span([r['hours'] for r in rs]),
            'per_day_med': med([r['per_day'] for r in rs]), 'target_min_med_max': span([r['target'] for r in rs], '{:.0f}'),
            'discount_bps': sorted({r['discount_bps'] for r in rs if r['discount_bps'] is not None}),
            'cap_med': med([r['cap'] for r in rs]), 'first_start': min((r['start'] or '') for r in rs), 'last_end': max((r['end'] or '') for r in rs),
            'sum_reward': sum(r['reward'] for r in rs), 'desc': rs[0]['desc'],
        }
        table.append(row)
        print(f'     {s} [{k}] {t}: {len(rs)} markets; reward $ min/med/max {row["reward_min_med_max"]}; period hours {row["hours_min_med_max"]}; '
              f'target size {row["target_min_med_max"]}; discount bps {row["discount_bps"]}; cap/account {row["cap_med"]}; '
              f'{row["first_start"]} .. {row["last_end"]}; "{row["desc"]}"')
    out['crypto_table'] = table
    liq = [r for r in crypto if r['type'] == 'liquidity' and kind_of(r['series']) in ('15-minute', 'hourly ladder')]
    out['liq_15m_hourly'] = len(liq)
    if liq:
        tmin = min((r['target'] for r in liq if r['target']), default=None)
        out['smallest_target'] = tmin
        each = pool / PAIR_COST
        print(f'   liquidity programs on crypto 15-minute and hourly markets: {len(liq)}; smallest target size {tmin}')
        for size, what in ((each, 'the whole pool on one market at a time'), (each / len(COINS), 'the pool split over four coins')):
            c = ceiling(liq, size)
            print(f'   best-case reward for {size:.0f} contracts a side ({what}), all listed markets, whole periods: ${c:,.2f}')
            out[f'ceiling_{int(size)}'] = c
    sch = [s for s in schedules if coin_of(s.get('series_ticker') or '')]
    out['crypto_schedules'] = len(sch)
    if schedules:
        print(f'   schedules: {len(schedules)} in all, {len(sch)} on crypto series')
        for s in sch:
            print(f'     {s.get("series_ticker")} {s.get("incentive_type")}: ${usd(s.get("reward")):.2f} per market per window of {s.get("window_days")} day(s); '
                  f'target {s.get("target_size_fp")}; discount bps {s.get("discount_factor_bps")}; all_markets {s.get("all_markets")}; ends {s.get("ends")}; '
                  f'"{(s.get("description") or "")[:160]}"')
    return out


def verdict(active: dict, upcoming: dict, pool: float) -> str:
    n = active.get('liq_15m_hourly', 0) + upcoming.get('liq_15m_hourly', 0)
    if n == 0 and not (active.get('crypto_schedules') or upcoming.get('crypto_schedules')):
        return 'CLOSED: no crypto 15-minute or hourly market is in a liquidity program (active, upcoming or scheduled)'
    targets = [d['smallest_target'] for d in (active, upcoming) if d.get('smallest_target')]
    if targets and min(targets) > pool / PAIR_COST:
        return f'CLOSED: the smallest target size ({min(targets):.0f} contracts a side) is more than a ${pool:.0f} pool can post'
    return 'NOT CLOSED BY THE LIST ALONE: see the ceiling in dollars an hour below against the $1 an hour line'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='')
    ap.add_argument('--pool', type=float, default=200.0)
    ap.add_argument('--from-file', default='')
    a = ap.parse_args(argv)
    if a.from_file:
        d = json.load(open(a.from_file))
        act, upc, sch = d.get('programs') or [], d.get('upcoming') or [], d.get('schedules') or []
    else:
        act = fetch_programs('active')
        upc = fetch_programs('upcoming')
        try:
            sch = fetch_schedules()
        except RuntimeError as e:
            print(f'schedules not readable: {e}')
            sch = []
    print(f'read at {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}: {len(act)} active, {len(upc)} upcoming, {len(sch)} schedules')
    ra = summarize(act, sch, a.pool, 'ACTIVE')
    ru = summarize(upc, [], a.pool, 'UPCOMING')
    print('\nfirst raw crypto rows (public data, for the field meanings):')
    shown = 0
    for p in act + upc:
        if coin_of(series_of(p)) and shown < 6:
            print('   ' + json.dumps(p, sort_keys=True)[:700])
            shown += 1
    if not shown:
        for p in (act + upc)[:3]:
            print('   (no crypto row; a sample row) ' + json.dumps(p, sort_keys=True)[:700])
    v = verdict(ra, ru, a.pool)
    print('\nVERDICT (list alone): ' + v)
    if a.out:
        json.dump({'active': ra, 'upcoming': ru, 'verdict': v, 'n_schedules': len(sch)}, open(a.out, 'w'), indent=1, default=str)
    return 0


if __name__ == '__main__':
    sys.exit(main())
