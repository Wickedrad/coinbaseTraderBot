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
    os.makedirs(d / 'calls')
    status = {'seconds': 61.2, 'peakRssMb': 141.5, 'rssMb': 96.0, 'counts': {'passes': 1, 'goodPasses': 1, 'networkErrors': 0},
              'coins': {'BTC': {'ok': True, 'cached': 218520, 'minutes': 217000, 'fetchSec': 14.2, 'engineSec': 0.11, 'fired': 2},
                        'ETH': {'ok': False, 'cached': 100, 'why': 'table hash differs: x'}}}
    json.dump(status, open(d / 'once-status.json', 'w'))
    json.dump(dict(status, seconds=0.31, peakRssMb=139.0), open(d / 'loop-status.json', 'w'))
    open(d / 'once-time.txt', 'w').write('\tCommand being timed: "python -m heat_reader --once"\n\tElapsed (wall clock) time (h:mm:ss or m:ss): 1:02.50\n'
                                         '\tMaximum resident set size (kbytes): 145408\n\tExit status: 0\n')
    open(d / 'loop.log', 'w').write('heat-reader: coins BTC\nheat-reader pass BTC 2 fired | ETH NOT OK: table hash differs: x (0.412 s)\n'
                                    'heat-reader pass BTC 0 fired | ETH NOT OK: table hash differs: x (0.298 s)\n'
                                    'heat-reader pass BTC 1 fired | ETH NOT OK: table hash differs: x (0.305 s)\n')
    open(d / 'rss.txt', 'w').write('0 98304\n5 100352\n10 0\n15 131072\nbroken line\n20 99328\n')
    row = lambda k: {'key': k, 'kind': 'single'}
    files = [{'coins': {'BTC': {'ok': True, 'calls': [row('1m:RSI7=very low'), row('1m:WILLR14=very low')]}, 'ETH': {'ok': False, 'calls': []}}},
             {'coins': {'BTC': {'ok': True, 'calls': [row('1m:RSI7=very low')]}, 'ETH': {'ok': False, 'calls': []}}}]
    open(d / 'calls' / 'heat_calls-2026-11-11.jsonl', 'w').write('\n'.join(json.dumps(f) for f in files) + '\nnot json\n')
    json.dump({'window_bars': 3000, 'share': 0.99812, 'keys_both': 5310, 'engine_only': 6, 'reader_only': 4,
               'coins': {'BTC': {'minutes': 1358, 'missing_minutes': 0, 'not_ok_minutes': 2, 'keys_both': 2650, 'engine_only': 0, 'reader_only': 0,
                                 'share': 1.0, 'rows_left_out': 0, 'keys_that_differ': [], 'seconds': 140.2},
                         'SOL': {'minutes': 1358, 'missing_minutes': 0, 'not_ok_minutes': 0, 'keys_both': 2660, 'engine_only': 6, 'reader_only': 4,
                                 'share': 0.99625, 'rows_left_out': 3, 'keys_that_differ': [['1m:PVI=high (rising in)', 7]], 'seconds': 150.0},
                         'XRP': {'skipped': 'no fixture for this coin'}}}, open(d / 'parity.json', 'w'))
    md = cr.build(str(d), oracle='2328763', note='first check', python='3.12.3', venv_mb='187', meta_source='Drive run 43030435253', pack='first pack c85e26b1', run_id='99')
    assert md.startswith('Heat reader check (run 99)\n')
    assert 'Oracle code at `2328763`. first check' in md and 'Python 3.12.3, venv 187 MB on disk.' in md
    assert '| BTC | 2 of 2 files | 218520 | 217000 | 3 | 14.2 | 0.11 |' in md
    assert '| ETH | 0 of 2 files | 100 | n/a | 0 | n/a | n/a |' in md
    assert '- BTC keys fired: `1m:RSI7=very low` x2, `1m:WILLR14=very low` x1' in md and '- ETH keys fired: none' in md
    assert '- ETH last file not ok: table hash differs: x' in md
    assert '- First pass (with the download of the window): 61.2 s inside the reader, 62.5 s wall, peak RSS 142.0 MB.' in md
    assert '- Loop: 3 passes, seconds per pass median 0.305, max 0.412.' in md
    assert 'peak RSS 139.0 MB' in md and 'idle RSS 97.5 MB (median of 4 samples, highest sample 128.0 MB)' in md
    assert 'MemoryHigh 180M and MemoryMax 220M' in md
    assert '**99.81%** of pack keys agree (5310 both, 6 engine only, 4 reader only)' in md
    assert '| BTC | 1358 | 100.00% | 2650 | 0 | 0 | 2 | 0 | 140.2 |' in md and '| SOL | 1358 | 99.62% | 2660 | 6 | 4 | 0 | 3 | 150.0 |' in md
    assert 'differ most: `1m:PVI=high (rising in)` x7' in md and '| XRP | skipped: no fixture for this coin |' in md
    assert cr.main(['--dir', str(d)]) == 0


def test_report_with_nothing_measured(tmp_path):
    md = cr.build(str(tmp_path))
    assert 'the reader wrote no file' in md and 'First pass: not measured' in md and 'Loop: no pass was logged' in md
    assert 'Loop memory: not measured' in md and 'Parity replay: not run' in md
