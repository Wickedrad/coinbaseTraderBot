"""What markets does one recorded day (md-DAY.jsonl.gz, the bot's own recording) hold, by series? Aggregates only.

Round 4 (Nov 22 2026, recorded days only): before the hourly ladders (KXBTCD, KXETHD, KXSOLD, KXXRPD) and range brackets (KXBTC, KXETH, ...) are added to the
1-second grids, count what the recording actually has of them: lines by kind and series, distinct markets, how long a market lives (close minus open from the
market line) and one sample market line per series. Nothing is kept per trade or per level.
"""
import json
import re
import subprocess
import sys

_TICKER = re.compile(rb'"ticker":"([A-Za-z0-9_]+)-?')
_KIND = re.compile(rb'"k":"([a-z_]+)"')


def series_of(line: bytes):
    """(kind, series) of a recording line: the kind from "k", the series from the leading part of "ticker" (before the first dash), None when there is none."""
    k = _KIND.search(line, 0, 80)
    if k is None:
        return None, None
    t = _TICKER.search(line, 0, 600)
    return k.group(1).decode(), (t.group(1).decode() if t else None)


_FULL = re.compile(rb'"ticker":"([^"]+)"')


def _ticker(line: bytes):
    m = _FULL.search(line, 0, 600)
    return m.group(1).decode() if m else None


def inventory(lines, sample_chars: int = 600) -> dict:
    kinds, by_series, tickers, sample, life = {}, {}, {}, {}, {}
    for line in lines:
        kind, ser = series_of(line)
        if kind is None:
            continue
        kinds[kind] = kinds.get(kind, 0) + 1
        if ser is None:
            continue
        d = by_series.setdefault(ser, {})
        d[kind] = d.get(kind, 0) + 1
        if kind in ('book', 'delta', 'trade', 'lifecycle', 'result', 'market'):
            tk = _ticker(line)
            if tk:
                tickers.setdefault(ser, set()).add(tk)
        if kind == 'market':
            if ser not in sample:
                sample[ser] = line[:sample_chars].decode('utf8', 'replace')
            try:
                e = json.loads(line)
                if e.get('closeTime') and e.get('openTime') is not None:
                    life.setdefault(ser, []).append(round((int(e['closeTime']) - int(e['openTime'])) / 60000.0, 1))
            except Exception:
                pass
    out = {'kinds': dict(sorted(kinds.items())), 'series': {}}
    for ser, d in sorted(by_series.items()):
        lf = sorted(life.get(ser, []))
        out['series'][ser] = {'lines_by_kind': dict(sorted(d.items())), 'distinct_markets': len(tickers.get(ser, ())),
                              'minutes_open_to_close': {'n': len(lf), 'min': lf[0] if lf else None, 'median': lf[len(lf) // 2] if lf else None, 'max': lf[-1] if lf else None},
                              'sample_market_line': sample.get(ser)}
    return out


def read_gz(path: str):
    p = subprocess.Popen(['gzip', '-dc', path], stdout=subprocess.PIPE, bufsize=1 << 22)
    yield from p.stdout
    p.wait()


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('path')
    ap.add_argument('--match', default=r'(BTC|ETH|SOL|XRP|DOGE)', help='series whose name matches are printed one by one, the rest are only counted')
    ap.add_argument('--samples', default='KXBTCD,KXBTC,KXETHD', help='series whose first market line is printed')
    a = ap.parse_args()
    r = inventory(read_gz(a.path))
    print('HEATLOOP mdinv-kinds ' + json.dumps(r['kinds'], sort_keys=True), flush=True)
    pat = re.compile(a.match)
    others = {k: v for k, v in r['series'].items() if not pat.search(k)}
    print('HEATLOOP mdinv-others ' + json.dumps({'series': len(others), 'lines': sum(sum(v['lines_by_kind'].values()) for v in others.values()),
                                                 'with_book_lines': sum(1 for v in others.values() if v['lines_by_kind'].get('book') or v['lines_by_kind'].get('delta')),
                                                 'with_trades': sum(1 for v in others.values() if v['lines_by_kind'].get('trade'))}, sort_keys=True), flush=True)
    keep = set(a.samples.split(','))
    for ser, v in r['series'].items():
        if pat.search(ser):
            v = {**v, 'sample_market_line': (v['sample_market_line'] or '')[:500] if ser in keep else None}
            print('HEATLOOP mdinv-series ' + json.dumps({'series': ser, **v}, sort_keys=True, default=str)[:1500], flush=True)
