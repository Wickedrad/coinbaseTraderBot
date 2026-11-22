"""One recorded day (md-DAY.jsonl.gz, the bot's own market-data recording) reduced to 1-second grids, aggregates only.

Steven, Nov 21 2026: recorded days only. The 1-minute candles say Kalshi's quote already holds what the spot knows at one-minute resolution; the question
earlier threads left open is whether the book lags the spot by seconds. This keeps, per 15-minute window and per second, the best YES bid and ask with their
sizes, the taker volume by side, and, per asset and per second, the last index value the bot received and how late it was. Nothing is kept per trade or per
level, so a day is a few megabytes and every later question runs in seconds instead of re-reading 1.7 GB.

Recording lines are {"t": receive ms, "k": kind, ...}: book {ticker, bids, asks: [{price, size}] in YES terms}, delta {ticker, side: bid|ask, price, delta},
trade {ticker, price, count, takerSide}, market {ticker, series, asset, openTime, closeTime, strike} (arrives about 40 seconds after the window opens),
lifecycle {ticker, event: created|metadata_updated|determined|settled, result: yes|no|scalar on determined, about a second after the close},
index {asset, value, ts (whole second), src: kalshi} (the settlement index, about 6 a second), spot {asset, value, ts (ms)} (about 5 a second),
perp {ticker, asset, ts, bid, ask, last, mark, contractSize} (price per unit = mid / contractSize).
"""
import json
import re
import subprocess
import sys

import numpy as np

SEC = 1000
WIN = 900                                      # seconds in a 15-minute window
DAY = 86400
SERIES = re.compile(r'^KX(BTC|ETH|SOL|XRP)15M$')
HOURLY = dict(series=re.compile(r'^KX(BTC|ETH|SOL|XRP)D$'), win=3600, tags=(b'BTCD-', b'ETHD-', b'SOLD-', b'XRPD-'), max_life_ms=3900 * 1000)   # the hourly ladders: P(coin >= strike) at the top of the hour
KINDS = (b'book', b'delta', b'trade', b'market', b'result', b'lifecycle', b'index', b'spot', b'perp')
BOOKISH = (b'book', b'delta', b'trade', b'result', b'lifecycle')


def _loads():
    try:
        import orjson
        return orjson.loads
    except Exception:
        return json.loads


def kind_of(line: bytes):
    i = line.find(b'"k":"', 0, 80)
    if i < 0:
        return None
    j = line.find(b'"', i + 5, i + 40)
    return line[i + 5:j] if j > 0 else None


class Book:
    """Best YES bid and ask of one market, kept from a snapshot and deltas."""
    __slots__ = ('bids', 'asks', 'bb', 'ba')

    def __init__(self):
        self.bids, self.asks, self.bb, self.ba = {}, {}, None, None

    def _best(self):
        self.bb = max(self.bids) if self.bids else None
        self.ba = min(self.asks) if self.asks else None

    def snapshot(self, bids, asks):
        self.bids = {round(float(l['price']), 4): float(l['size']) for l in bids if float(l['size']) > 0}
        self.asks = {round(float(l['price']), 4): float(l['size']) for l in asks if float(l['size']) > 0}
        self._best()

    def delta(self, side, price, d):
        book = self.bids if side == 'bid' else self.asks
        p = round(float(price), 4)
        n = book.get(p, 0.0) + float(d)
        if n > 1e-9:
            book[p] = n
            if side == 'bid' and (self.bb is None or p > self.bb):
                self.bb = p
            elif side == 'ask' and (self.ba is None or p < self.ba):
                self.ba = p
        else:
            book.pop(p, None)
            if side == 'bid' and p == self.bb:
                self.bb = max(self.bids) if self.bids else None
            elif side == 'ask' and p == self.ba:
                self.ba = min(self.asks) if self.asks else None

    def top(self):
        return (self.bb, self.bids.get(self.bb, 0.0) if self.bb is not None else 0.0,
                self.ba, self.asks.get(self.ba, 0.0) if self.ba is not None else 0.0)


def reduce_day(lines, day_ms: int, assets=('BTC', 'ETH', 'SOL', 'XRP'), series=None, win: int = None, tags=None, max_life_ms: int = None) -> dict:
    """lines: an iterable of bytes lines of one recorded UTC day starting at `day_ms`. Returns the grids (see module doc) and a counts summary.
    The defaults read the 15-minute series. series (a compiled regex with the asset in group 1), win (seconds a market is read for before its close), tags (bytes that a
    market-data line of those series carries in its first 200 bytes) and max_life_ms (skip a market listed for longer than this, from its open to its close) read
    another family, e.g. HOURLY below."""
    series = SERIES if series is None else series
    win = WIN if win is None else win
    tags = (b'15M-',) if tags is None else tags
    prefilter = win != WIN                                   # a family with many unregistered markets: skip a line whose ticker the bot never registered
    known = set()
    loads = _loads()
    meta, books, wins = {}, {}, {}
    idx_val = {a: np.full(DAY, np.nan) for a in assets}
    idx_n = {a: np.zeros(DAY, np.int32) for a in assets}
    idx_lag = {a: np.full(DAY, np.nan) for a in assets}
    spot_val = {a: np.full(DAY, np.nan) for a in assets}
    spot_n = {a: np.zeros(DAY, np.int32) for a in assets}
    spot_lag = {a: np.full(DAY, np.nan) for a in assets}
    perp_mid = {a: np.full(DAY, np.nan) for a in assets}
    perp_last = {a: np.full(DAY, np.nan) for a in assets}
    counts, all_kinds, src, first = {}, {}, {}, {}
    for line in lines:
        k = kind_of(line)
        if k is None:
            continue
        all_kinds[k] = all_kinds.get(k, 0) + 1
        if k not in KINDS:
            continue
        if k in BOOKISH:
            head = line[:200]
            if not any(t in head for t in tags):             # other series and other markets: no need to parse
                continue
            if prefilter:
                i = head.find(b'"ticker":"')
                j = head.find(b'"', i + 10) if i >= 0 else -1
                if j < 0 or head[i + 10:j] not in known:
                    continue
        ks = k.decode()
        counts[ks] = counts.get(ks, 0) + 1
        if ks not in first:
            first[ks] = line[:300].decode('utf8', 'replace')
        try:
            e = loads(line)
        except Exception:
            counts['bad'] = counts.get('bad', 0) + 1
            continue
        t = e['t']
        if ks == 'index':
            a = e.get('asset')
            sk = f'{a}/{e.get("src")}'
            src[sk] = src.get(sk, 0) + 1
            if a in idx_val:
                s = (t - day_ms) // SEC
                if 0 <= s < DAY:
                    idx_val[a][s] = float(e['value'])
                    idx_n[a][s] += 1
                    if isinstance(e.get('ts'), (int, float)):
                        idx_lag[a][s] = t - float(e['ts'])
            continue
        if ks == 'spot':
            a = e.get('asset')
            if a in spot_val:
                sec = (t - day_ms) // SEC
                if 0 <= sec < DAY and e.get('value') is not None:
                    spot_val[a][sec] = float(e['value'])
                    spot_n[a][sec] += 1
                    if isinstance(e.get('ts'), (int, float)):
                        spot_lag[a][sec] = t - float(e['ts'])
            continue
        if ks == 'perp':
            a = e.get('asset')
            cs = e.get('contractSize')
            if a in perp_mid and cs:
                sec = (t - day_ms) // SEC
                if 0 <= sec < DAY:
                    if e.get('bid') is not None and e.get('ask') is not None and e['bid'] > 0 and e['ask'] > 0:
                        perp_mid[a][sec] = 0.5 * (float(e['bid']) + float(e['ask'])) / float(cs)
                    if e.get('last') is not None and e['last'] > 0:
                        perp_last[a][sec] = float(e['last']) / float(cs)
            continue
        if ks == 'market':
            m = series.match(str(e.get('series') or ''))
            if m and m.group(1) in assets and e.get('closeTime') and e.get('openTime') is not None \
                    and (max_life_ms is None or int(e['closeTime']) - int(e['openTime']) <= max_life_ms):
                meta[e['ticker']] = {'asset': m.group(1), 'open': int(e['closeTime']) - win * SEC, 'close': int(e['closeTime']), 'strike': e.get('strike')}
                known.add(e['ticker'].encode())
            continue
        tk = e.get('ticker')
        mt = meta.get(tk)
        if mt is None:
            continue
        if ks == 'lifecycle':
            if e.get('event') == 'determined':                  # the result, about a second after the close
                mt['result'] = 1.0 if e.get('result') == 'yes' else 0.0 if e.get('result') == 'no' else None
            continue
        if ks == 'result':
            mt['result'] = 1.0 if e.get('result') == 'yes' else 0.0 if e.get('result') == 'no' else None
            continue
        w = wins.get(tk)
        if w is None:
            w = wins[tk] = {'bid': np.full(win, np.nan), 'ask': np.full(win, np.nan), 'bsz': np.zeros(win), 'asz': np.zeros(win),
                            'ty': np.zeros(win), 'tn': np.zeros(win), 'seen': np.zeros(win, bool), 'pre': None, 'tr': []}
        s = (t - mt['open']) // SEC
        if not 0 <= s < win:
            if ks in ('book', 'delta'):                      # keep the book current even outside the window
                b = books.setdefault(tk, Book())
                if ks == 'book':
                    b.snapshot(e['bids'], e['asks'])
                else:
                    b.delta(e['side'], e['price'], e['delta'])
                if s < 0:
                    w['pre'] = b.top()                      # the book as the window opens
            continue
        if ks == 'trade':
            c = float(e.get('count') or 0)
            if e.get('takerSide') == 'yes':
                w['ty'][s] += c
                w['tr'].append((t - mt['open'], float(e['price']), c, 1))
            elif e.get('takerSide') == 'no':
                w['tn'][s] += c
                w['tr'].append((t - mt['open'], float(e['price']), c, -1))
            continue
        b = books.setdefault(tk, Book())
        if ks == 'book':
            b.snapshot(e['bids'], e['asks'])
        else:
            b.delta(e['side'], e['price'], e['delta'])
        bb, bs, ba, as_ = b.top()
        w['bid'][s] = np.nan if bb is None else bb
        w['ask'][s] = np.nan if ba is None else ba
        w['bsz'][s], w['asz'][s] = bs, as_
        w['seen'][s] = True
    out = {'counts': counts, 'all_kinds': {k.decode(): v for k, v in sorted(all_kinds.items())}, 'index_src': dict(sorted(src.items())), 'first': first,
           'assets': list(assets)}
    for a in assets:
        tickers = sorted((tk for tk, m in meta.items() if m['asset'] == a and tk in wins and wins[tk]['seen'].any()), key=lambda x: meta[x]['open'])
        n = len(tickers)
        g = {k: np.full((n, win), np.nan) for k in ('bid', 'ask')}
        g.update({k: np.zeros((n, win)) for k in ('bsz', 'asz', 'ty', 'tn')})
        for i, tk in enumerate(tickers):
            w = wins[tk]
            seen = w['seen']
            pre = w['pre']
            for key, pi in (('bid', 0), ('bsz', 1), ('ask', 2), ('asz', 3)):
                arr = w[key].copy()
                # an unseen second keeps the book of the second before it; the first seconds keep the book as the window opened
                last = None if pre is None else (np.nan if pre[pi] is None else pre[pi])
                for s in range(win):
                    if seen[s]:
                        last = arr[s]
                    elif last is not None:
                        arr[s] = last
                if key in ('bsz', 'asz'):
                    arr[~np.isfinite(arr)] = 0.0
                g[key][i] = arr
            g['ty'][i], g['tn'][i] = w['ty'], w['tn']
        trs = [(i, *r) for i, tk in enumerate(tickers) for r in wins[tk]['tr']]
        tr = np.array(trs, dtype=np.float64).reshape(-1, 5)
        out[a] = {'tr_w': tr[:, 0].astype(np.int32), 'tr_ms': tr[:, 1].astype(np.int32), 'tr_p': tr[:, 2].astype(np.float32), 'tr_c': tr[:, 3].astype(np.float32),
                  'tr_side': tr[:, 4].astype(np.int8), 'tickers': tickers, 'open_ms': np.array([meta[x]['open'] for x in tickers], np.int64),
                  'strike': np.array([float(meta[x]['strike']) if meta[x].get('strike') not in (None, '') else np.nan for x in tickers]),
                  'result': np.array([meta[x].get('result') if meta[x].get('result') is not None else np.nan for x in tickers]),
                  'bid': g['bid'], 'ask': g['ask'], 'bsz': g['bsz'], 'asz': g['asz'], 'ty': g['ty'], 'tn': g['tn'],
                  'idx': idx_val[a], 'idx_n': idx_n[a], 'idx_lag_ms': idx_lag[a], 'spot': spot_val[a], 'spot_n': spot_n[a], 'spot_lag_ms': spot_lag[a],
                  'perp_mid': perp_mid[a], 'perp_last': perp_last[a]}
    return out


def read_gz(path: str):
    """Lines of a gzipped recording through the system gunzip (much faster than gzip.open)."""
    p = subprocess.Popen(['gzip', '-dc', path], stdout=subprocess.PIPE, bufsize=1 << 22)
    yield from p.stdout
    p.wait()


def save(out: dict, path: str) -> None:
    flat = {}
    for a in out['assets']:
        for k, v in out[a].items():
            flat[f'{a}__{k}'] = np.array(v) if k == 'tickers' else v
    np.savez_compressed(path, **flat)


def summary(out: dict) -> dict:
    s = {'counts': out['counts']}
    for a in out['assets']:
        d = out[a]
        n = len(d['tickers'])
        s[a] = {'windows': n, 'with_result': int(np.isfinite(d['result']).sum()),
                'index_seconds': int((d['idx_n'] > 0).sum()), 'index_updates': int(d['idx_n'].sum()),
                'index_lag_ms_median': None if not np.isfinite(d['idx_lag_ms']).any() else float(np.nanmedian(d['idx_lag_ms'])),
                'spot_seconds': int((d['spot_n'] > 0).sum()), 'spot_updates': int(d['spot_n'].sum()),
                'spot_lag_ms_median': None if not np.isfinite(d['spot_lag_ms']).any() else float(np.nanmedian(d['spot_lag_ms'])),
                'perp_seconds': int(np.isfinite(d['perp_mid']).sum()),
                'book_seconds_with_two_sides': int((np.isfinite(d['bid']) & np.isfinite(d['ask'])).sum())}
    return s


if __name__ == '__main__':
    import datetime as dt
    path, day, dest = sys.argv[1], sys.argv[2], sys.argv[3]
    day_ms = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    hourly = len(sys.argv) > 4 and sys.argv[4] == 'hourly'
    out = reduce_day(read_gz(path), day_ms, **(HOURLY if hourly else {}))
    save(out, dest)
    print('HEATLOOP md ' + json.dumps({'day': day, 'part': 'hgrid' if hourly else 'grid', **summary(out), 'all_kinds': out['all_kinds'], 'index_src': out['index_src'], 'first': out['first']}, sort_keys=True, default=float), flush=True)
