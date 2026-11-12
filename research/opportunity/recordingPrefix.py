"""Extract fixed public market fields from a bounded archived gzip prefix; exclude account/model events."""
import argparse
import collections
import hashlib
import gzip
import json
from pathlib import Path
import re
import zlib

FIELDS = {
    'index': ('asset', 'value', 'ts', 'src', 'hist'),
    'spot': ('asset', 'value', 'ts', 'hist'),
    'market': ('ticker', 'series', 'asset', 'openTime', 'closeTime', 'strike', 'cap', 'kind', 'event', 'tickSize', 'recordOnly', 'synth', 'hist'),
    'book': ('ticker', 'bids', 'asks', 'ts', 'hist'),
    'delta': ('ticker', 'side', 'price', 'delta', 'ts', 'hist'),
    'gap': ('ticker', 'ts'),
    'trade': ('ticker', 'price', 'count', 'takerSide', 'ts'),
    'candles': ('asset', 'tf', 'rows', 'ts'),
    'dominance': ('usdtd', 'btcd', 'btcdom', 'covered', 'ts', 'hist'),
    'result': ('ticker', 'result'),
    'perp': ('ticker', 'asset', 'ts', 'bid', 'ask', 'last', 'mark', 'openInterest', 'fundingRate', 'nextFundingTs',
             'contractSize', 'tickSize', 'fractional', 'leverage', 'liquidationMark', 'isOpen'),
}
ASSETS = {'BTC', 'ETH', 'SOL', 'XRP', 'DOGE'}


def file_hash(file):
    h = hashlib.sha256()
    with Path(file).open('rb') as stream:
        while data := stream.read(1024 * 1024): h.update(data)
    return h.hexdigest()


def extract(prefix, output, max_mib=512, book_every_ms=60000, observed_only=False):
    prefix, output = Path(prefix), Path(output)
    if not 1 <= max_mib <= 4096 or book_every_ms not in (0, 1000, 60000): raise ValueError('invalid public extraction bounds')
    if output.exists(): raise ValueError('new output required')
    output.parent.mkdir(parents=True, exist_ok=True)
    counts, sources, timeframes = collections.Counter(), collections.Counter(), collections.Counter()
    seen_books = set()
    report = {'schema': 'atlas-public-recording-prefix-v1', 'complete_original_archive': False,
              'source_basis': 'already archived bot recording; no fresh provider acquisition',
              'prefix_bytes': prefix.stat().st_size, 'prefix_sha256': file_hash(prefix),
              'first_arrival': None, 'last_arrival': None, 'malformed_lines': 0, 'hist_or_synth': 0, 'observed_only': observed_only,
              'proxy_or_synthetic_skipped': 0}
    decoder, pending, total = zlib.decompressobj(31), b'', 0
    open_output = (lambda: gzip.open(output, 'xt', compresslevel=1)) if output.suffix == '.gz' else (lambda: output.open('x'))
    with open_output() as writer, prefix.open('rb') as source:
        while block := source.read(1024 * 1024):
            while block:
                data = decoder.decompress(block, 8 * 1024 * 1024); total += len(data)
                pending += data
                lines = pending.split(b'\n'); pending = lines.pop()
                if len(pending) > 2 * 1024 * 1024: raise ValueError('recording line exceeds limit')
                for line in lines:
                    # Decline unknown/private event bodies before JSON parsing.
                    match = re.match(rb'\{"t":\d+,"k":"([a-z_]+)"', line)
                    if not match or match[1].decode() not in FIELDS: continue
                    try: e = json.loads(line)
                    except ValueError: report['malformed_lines'] += 1; continue
                    k = e['k']; t = e.get('t')
                    if not isinstance(t, int) or t < 0: continue
                    if observed_only and (e.get('hist') or e.get('synth') or (k == 'index' and e.get('src') != 'kalshi')):
                        report['proxy_or_synthetic_skipped'] += 1; continue
                    if 'asset' in e and e['asset'] not in ASSETS: continue
                    ticker = e.get('ticker')
                    ticker_pattern = r'(?:KX)?(?:BTC|ETH|SOL|XRP|DOGE)[A-Z0-9_.-]*' if k == 'perp' else r'KX(?:BTC|ETH|SOL|XRP|DOGE)[A-Z0-9_.-]*'
                    if ticker is not None and (not isinstance(ticker, str) or not re.fullmatch(ticker_pattern, ticker)): continue
                    if k == 'book' and book_every_ms:
                        key = (ticker, t // book_every_ms)
                        if key in seen_books: continue
                        seen_books.add(key)
                    out = {'t': t, 'k': k, **{key: e[key] for key in FIELDS[k] if key in e}}
                    if k == 'book':
                        for side in ('bids', 'asks'):
                            out[side] = [{key: level[key] for key in ('price', 'size') if key in level} for level in e.get(side, [])[:100]]
                    if k == 'candles':
                        out['rows'] = [row[:7] if isinstance(row, list) and len(row) in (6, 7) and all(isinstance(v, (int, float)) for v in row)
                                       else {key: row[key] for key in ('ts', 'o', 'h', 'l', 'c', 'v', 'tb') if key in row} if isinstance(row, dict)
                                       else {} for row in e.get('rows', [])[:10000]]
                        timeframes[str(e.get('tf', 'unknown'))] += 1
                    if k == 'index': sources[str(e.get('src', 'unknown')) if e.get('src') in ('kalshi', 'proxy') else 'unknown'] += 1
                    report['hist_or_synth'] += int(bool(e.get('hist') or e.get('synth')))
                    report['first_arrival'] = t if report['first_arrival'] is None else min(t, report['first_arrival'])
                    report['last_arrival'] = t if report['last_arrival'] is None else max(t, report['last_arrival'])
                    counts[k] += 1; writer.write(json.dumps(out, separators=(',', ':')) + '\n')
                if total >= max_mib * 1024 * 1024:
                    block = b''; break
                if decoder.eof:
                    block = decoder.unused_data; decoder = zlib.decompressobj(31)
                else:
                    block = decoder.unconsumed_tail
            if total >= max_mib * 1024 * 1024: break
    report.update(decompressed_bytes=total, event_counts=dict(counts), index_sources=dict(sources), candle_timeframes=dict(timeframes),
                  filtered_sha256=file_hash(output), maximum_decompressed_mib=max_mib, book_every_ms=book_every_ms,
                  snapshot_sampling=f'first public snapshot per ticker per {book_every_ms}ms; not full-book replay fidelity' if book_every_ms else 'all observed public snapshots/deltas inside a bounded prefix; upstream gap capture remains unverified')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix'); parser.add_argument('--out', required=True); parser.add_argument('--report', required=True)
    parser.add_argument('--max-decompressed-mib', type=int, default=512); parser.add_argument('--book-every-ms', type=int, default=60000)
    parser.add_argument('--observed-only', action='store_true')
    args = parser.parse_args()
    report = extract(args.prefix, args.out, args.max_decompressed_mib, args.book_every_ms, args.observed_only)
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
