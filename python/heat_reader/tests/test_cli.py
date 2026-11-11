"""The command line, run as the service runs it (python3 -m heat_reader), against a local server that answers like
Binance: the real HTTP code, the real engine, a real file on disk. Also the parity replay's command line."""
import gzip
import http.server
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from conftest import PACKAGE, assert_contract
from heat_reader import MIN
from heat_reader.reader import day_of
from test_reader import build

PYTHON_DIR = os.path.dirname(PACKAGE)


@pytest.fixture
def server(world):
    """Binance on 127.0.0.1: the fake's answers over real HTTP. Its clock starts 3 s after world.end and runs on."""
    fake = world.fake()
    base, t0 = fake.now, time.time()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            fake.now = base + (time.time() - t0) * 1000.0
            status, headers, body = fake(f'http://127.0.0.1{self.path}', 5)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{srv.server_address[1]}/api/v3', fake
    srv.shutdown()
    srv.server_close()


def run(module, args, env=None):
    """The module in a fresh interpreter, from the python/ folder, with nothing of this machine's environment but the
    path (no proxy between it and the local server)."""
    e = {'PATH': os.environ.get('PATH', ''), 'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'}
    e.update(env or {})
    return subprocess.run([sys.executable, '-m', module] + [str(a) for a in args], cwd=PYTHON_DIR, env=e, capture_output=True, text=True, timeout=300)


def test_once_writes_the_file_and_exits_zero(world, oracle_path, server, tmp_path):
    api, fake = server
    pack, want = build(world, tmp_path)
    data = tmp_path / 'data'
    env = {'DATA_DIR': str(data), 'HEAT_PACK_FILE': pack, 'HEAT_META_DIR': str(tmp_path / 'tables'), 'HEAT_ORACLE_PATH': oracle_path,
           'HEAT_ASSETS': 'BTC,ETH,DOGE', 'HEAT_WINDOW_BARS': str(world.window), 'HEAT_BINANCE_API': api}
    p = run('heat_reader', ['--once'], env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'DOGE is in HEAT_ASSETS and is refused (never DOGE)' in p.stdout
    assert 'heat-reader pass BTC 5 fired | ETH 5 fired' in p.stdout
    obj = json.load(open(data / 'heat_calls.json'))                           # HEAT_CALLS_FILE defaults to <DATA_DIR>/heat_calls.json
    assert_contract(obj)
    assert list(obj['coins']) == ['BTC', 'ETH']
    for c in ('BTC', 'ETH'):
        assert obj['coins'][c]['ok'] and obj['coins'][c]['asOf'] == world.end
        assert [(x['h'], x['rank'], x['key']) for x in obj['coins'][c]['calls']] == want[c]
    # the day of the log is the day the file was written on this machine's clock
    assert sorted(os.listdir(data)) == [f'heat_calls-{day_of(obj["writtenAt"])}.jsonl', 'heat_calls.json', 'heat_reader']
    assert abs(obj['writtenAt'] - time.time() * 1000) < 120_000
    assert sorted(os.listdir(data / 'heat_reader')) == ['minutes', 'status.json']          # HEAT_READER_DIR defaults to <DATA_DIR>/heat_reader
    assert any('/time' in u for u in fake.urls) and len(fake.klines()) == 16
    # a flag wins over the environment, and the second run finds its minutes in the cache
    fake.urls.clear()
    p = run('heat_reader', ['--once', '--assets', 'ETH', '--calls-file', tmp_path / 'other.json'], env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert list(json.load(open(tmp_path / 'other.json'))['coins']) == ['ETH'] and len(fake.klines()) == 1


def test_exit_codes(world, oracle_path, server, tmp_path):
    api, _ = server
    pack, _ = build(world, tmp_path)
    flags = ['--once', '--pack-file', pack, '--meta-dir', tmp_path / 'tables', '--binance-api', api, '--window-bars', world.window,
             '--calls-file', tmp_path / 'c.json', '--reader-dir', tmp_path / 'rd', '--assets', 'BTC']
    p = run('heat_reader', flags + ['--oracle-path', tmp_path / 'nothing-here'])
    assert p.returncode == 1 and 'BTC NOT OK: no oracle/heat_live.py under' in p.stdout      # no coin could be read
    assert json.load(open(tmp_path / 'c.json'))['coins']['BTC']['ok'] is False               # and the file says so
    for bad, text in ((['--window-bars', '10'], 'HEAT_WINDOW_BARS: 10 is below 300'), (['--assets', 'DOGE'], 'names no coin'),
                      (['--binance-api', 'file:///etc/passwd'], 'must be an http or https address')):
        p = run('heat_reader', flags + ['--oracle-path', oracle_path] + bad)
        assert p.returncode == 2 and text in p.stdout                                         # a setting it cannot run with


def test_parity_replay_command(world, oracle_path, server, tmp_path):
    """A fixture made the way the oracle's parity job makes it (every key the engine fires, per minute close), then
    replayed through the reader's own path: all pack keys agree. One key added to the engine's side shows up."""
    api, _ = server
    pack, _ = build(world, tmp_path)
    lo, hi = world.end - 15 * MIN, world.end
    for c in ('BTC', 'ETH'):
        minutes = {str(t): world.events(c, t)['events'] for t in range(lo + MIN, hi + MIN, MIN)}
        os.makedirs(tmp_path / 'parity' / c)
        with gzip.open(tmp_path / 'parity' / c / 'fixture.json.gz', 'wt') as f:
            json.dump({'coin': c, 'from_ms': lo, 'to_ms': hi, 'table_sha256': f'sha-{c}', 'minutes': minutes}, f)
    flags = ['--fixtures', tmp_path / 'parity', '--out', tmp_path / 'parity.json', '--all', '--pack-file', pack, '--meta-dir', tmp_path / 'tables',
             '--oracle-path', oracle_path, '--binance-api', api, '--window-bars', world.window, '--reader-dir', tmp_path / 'rd',
             '--calls-file', tmp_path / 'unused.json', '--assets', 'BTC,ETH,SOL']
    p = run('heat_reader.replay', flags)
    assert p.returncode == 0, p.stdout + p.stderr
    par = json.load(open(tmp_path / 'parity.json'))
    assert par['share'] == 1.0 and par['engine_only'] == 0 and par['reader_only'] == 0 and par['keys_both'] >= 6
    for c in ('BTC', 'ETH'):
        r = par['coins'][c]
        assert r['minutes'] == 15 and r['share'] == 1.0 and r['keys_both'] >= 3 and r['not_ok_minutes'] == 0 and r['missing_minutes'] == 0 and r['rows_left_out'] == 1
    assert par['coins']['SOL'] == {'skipped': 'the traded pack has no rows for this coin'}
    assert not os.path.exists(tmp_path / 'unused.json')                       # the replay writes no calls file
    # the engine's side gets a pack key the reader does not fire at that minute: counted as engine only
    fx = json.load(gzip.open(tmp_path / 'parity' / 'BTC' / 'fixture.json.gz', 'rt'))
    quiet = json.load(open(pack))['rows'][5]['key']
    fx['minutes'][str(hi - 2 * MIN)] = fx['minutes'].get(str(hi - 2 * MIN), []) + [quiet]
    with gzip.open(tmp_path / 'parity' / 'BTC' / 'fixture.json.gz', 'wt') as f:
        json.dump(fx, f)
    p = run('heat_reader.replay', flags)
    par = json.load(open(tmp_path / 'parity.json'))
    assert par['coins']['BTC']['engine_only'] == 1 and par['coins']['BTC']['share'] < 1.0 and par['coins']['BTC']['keys_that_differ'] == [[quiet, 1]]
    assert par['coins']['ETH']['share'] == 1.0 and par['share'] < 1.0
