"""The replay's minute sample and the check job's report text."""
import json
import os

from heat_reader import MIN
from heat_reader import check_report as cr
from heat_reader.replay import sample


def test_the_replay_sample_is_the_parity_jobs():
    lo, hi = 1_766_966_400_000, 1_767_225_600_000           # Dec 29 to 31, 2025: the fixture's range
    s = sample(lo, hi)
    assert len(s) == 1358 and s[0] == lo + MIN and s[-1] == hi                # as many minutes as the oracle's parity job checked
    assert sum(t % (5 * MIN) == 0 for t in s) == 864 and all(lo < t <= hi and t % MIN == 0 for t in s)
    assert len(sample(lo, hi, every=True)) == 4320
    capped = sample(lo, hi, cap=200)
    assert 150 < len(capped) <= 200 and capped[0] == s[0] and capped == sorted(capped)


def test_report_text(tmp_path):
    d = tmp_path
    os.makedirs(d / 'calls' / 'loop')
    rows = {'wanted': {'single': 80, 'pair': 89, 'triple': 8, 'clock': 0},
            'skipped': {'dominance (no feed)': 14, 'live_parity false': 5, 'rank beyond HEAT_READER_MAX_RANK': 40}}
    status = {'seconds': 61.2, 'peakRssMb': 141.5, 'rssMb': 96.0, 'counts': {'passes': 1, 'goodPasses': 1, 'networkErrors': 0},
              'coins': {'BTC': {'ok': True, 'cached': 218520, 'minutes': 217000, 'fetchSec': 14.2, 'engineSec': 0.11, 'fired': 2, 'rows': rows},
                        'ETH': {'ok': False, 'cached': 100, 'why': 'table hash differs: x'}}}
    json.dump(status, open(d / 'once-status.json', 'w'))
    json.dump(dict(status, seconds=0.31, peakRssMb=139.0), open(d / 'loop-status.json', 'w'))
    side = {'v': 1, 'run': '43030435253', 'maxRank': 40, 'clockPack': False, 'coins': {},
            'packs': {'traded_pack.json': {'sha256': 'e6cb06b5cb97b38bb2'}, 'pair_pack.json': {'sha256': 'e505f679efcafa89a4'},
                      'live_meta.json': {'sha256': '1cf29ebed28b17bb56'}}}
    json.dump(side, open(d / 'calls' / 'loop' / 'heat_calls.status.json', 'w'))
    open(d / 'once-time.txt', 'w').write('\tCommand being timed: "python -m heat_reader --once"\n\tElapsed (wall clock) time (h:mm:ss or m:ss): 1:02.50\n'
                                         '\tMaximum resident set size (kbytes): 145408\n\tExit status: 0\n')
    open(d / 'loop.log', 'w').write('heat-reader: coins BTC\nheat-reader pass BTC 2 fired in 1.25 s | ETH NOT OK: table hash differs: x (1.412 s)\n'
                                    'heat-reader pass BTC 0 fired in 0.21 s | ETH NOT OK: table hash differs: x (0.298 s)\n'
                                    'heat-reader pass BTC 3 fired in 0.25 s | ETH NOT OK: table hash differs: x (0.305 s)\n')
    open(d / 'rss.txt', 'w').write('0 98304\n5 100352\n10 0\n15 131072\nbroken line\n20 99328\n')
    row = lambda k, kind='single': {'key': k, 'kind': kind}
    files = [{'coins': {'BTC': {'ok': True, 'calls': [row('1m:RSI7=very low'), row('1m:WILLR14=very low'), row('1m:RSI7=very low | 1m:AD sign=below 0', 'pair')]},
                        'ETH': {'ok': False, 'calls': []}}},
             {'coins': {'BTC': {'ok': True, 'calls': [row('1m:RSI7=very low')]}, 'ETH': {'ok': False, 'calls': []}}}]
    open(d / 'calls' / 'loop' / 'heat_calls-2026-11-11.jsonl', 'w').write('\n'.join(json.dumps(f) for f in files) + '\nnot json\n')
    json.dump({'window_bars': 3000, 'share': 0.99812, 'keys_both': 5310, 'engine_only': 6, 'reader_only': 4, 'triggers_share': 0.995,
               'triggers_both': 995, 'triggers_engine_only': 3, 'triggers_reader_only': 2,
               'coins': {'BTC': {'minutes': 1358, 'missing_minutes': 0, 'not_ok_minutes': 2, 'keys_both': 2650, 'engine_only': 0, 'reader_only': 0,
                                 'share': 1.0, 'triggers_share': 1.0, 'fired': {'single': 900, 'pair': 300, 'triple': 12}, 'minutes_loaded': 222840,
                                 'keys_that_differ': [], 'seconds': 140.2},
                         'SOL': {'minutes': 1358, 'missing_minutes': 0, 'not_ok_minutes': 0, 'keys_both': 2660, 'engine_only': 6, 'reader_only': 4,
                                 'share': 0.99625, 'triggers_share': 0.99, 'fired': {'single': 800}, 'keys_that_differ': [['1m:PVI=high (rising in)', 7]],
                                 'seconds': 150.0},
                         'XRP': {'skipped': 'no fixture for this coin'}}}, open(d / 'parity.json', 'w'))
    md = cr.build(str(d), oracle='fd88805', note='first check', python='3.12.3', venv_mb='187', run_id='99')
    assert md.startswith('Heat reader check (run 99)\n')
    assert 'Oracle code and packs at `fd88805`. first check' in md and 'Python 3.12.3, venv 187 MB on disk.' in md
    assert 'traded e6cb06b5cb97, pairs e505f679efca, live_meta 1cf29ebed28b; run 43030435253; HEAT_READER_MAX_RANK 40, clock pack off.' in md
    assert ('| BTC | 2 of 2 | 218520 | 80 / 89 / 8 / 0 | dominance (no feed) 14, live_parity false 5, rank beyond HEAT_READER_MAX_RANK 40 | '
            '3 / 1 / 0 | 0.25 / 1.25 | 100.00% / 100.00% |') in md
    assert '| ETH | 0 of 2 | 100 | n/a | n/a | 0 / 0 / 0 | n/a | n/a |' in md
    assert '| SOL | 0 of 0 | n/a | n/a | n/a | 0 / 0 / 0 | n/a | 99.62% / 99.00% |' in md and '| XRP | 0 of 0 | n/a | n/a | n/a | 0 / 0 / 0 | n/a | skipped: no fixture for this coin |' in md
    assert '- BTC fired: `1m:RSI7=very low` x2, `1m:RSI7=very low | 1m:AD sign=below 0` x1, `1m:WILLR14=very low` x1' in md
    assert '- ETH last file: table hash differs: x' in md
    assert '- First pass (downloads the window, reads the 60-minute timeframe): 61.2 s inside the reader, 62.5 s wall, peak RSS 142.0 MB.' in md
    assert '- Loop: 3 passes, seconds per pass median 0.305, max 1.412' in md
    assert 'peak RSS 139.0 MB' in md and 'idle RSS 97.5 MB (median of 4 samples, highest sample 128.0 MB)' in md
    assert 'MemoryHigh 180M and MemoryMax 220M' in md
    assert '**99.81%** of published single keys agree (5310 both, 6 engine only, 4 reader only); pair triggers 99.50% (995 both' in md
    assert '| BTC | 1358 | 222840 | 100.00% | 2650 | 0 | 0 | 100.00% | 312 | 2 | 140.2 |' in md
    assert '| SOL | 1358 | n/a | 99.62% | 2660 | 6 | 4 | 99.00% | 0 | 0 | 150.0 |' in md
    assert 'differ most: `1m:PVI=high (rising in)` x7' in md and '| XRP | skipped: no fixture for this coin |' in md
    assert cr.main(['--dir', str(d)]) == 0


def test_report_with_nothing_measured(tmp_path):
    md = cr.build(str(tmp_path))
    assert 'the reader wrote no file' in md and 'First pass: not measured' in md and 'Loop: no pass was logged' in md
    assert 'Loop memory: not measured' in md and 'Parity replay: not run' in md and 'traded n/a, pairs n/a' in md
