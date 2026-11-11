"""Shared pieces of the reader's tests: synthetic minutes, a canned Binance, and the real oracle engine.

Binance is not reachable from the test machine, so every answer is canned: FakeBinance serves kline pages cut from a
synthetic random walk, in Binance's own row format, the still-open minute included. The engine is the real one
(python/oracle on the oracle branch): tests that need it skip themselves when TA-Lib or the oracle code is not there.
"""
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.parse

import numpy as np
import pytest

TESTS = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.dirname(TESTS)
PYTHON_DIR = os.path.dirname(PACKAGE)
REPO = os.path.dirname(PYTHON_DIR)
if PYTHON_DIR not in sys.path:
    sys.path.insert(0, PYTHON_DIR)

from heat_reader import MIN  # noqa: E402
from heat_reader.binance import FetchError  # noqa: E402

T0 = 1_794_009_600_000          # 2026-11-07 00:00 UTC, a midnight: synthetic minutes are placed around it
ORACLE_BRANCH = 'origin/claude/project-thread-nvd096'


def walk(n: int, end_open_ms: int, step: float = 0.01, price: float = 60_000.0, seed: int = 0) -> np.ndarray:
    """n one-minute bars ending with the minute that opens at end_open_ms: a fat-tailed random walk on a price step,
    as (n, 7) rows ts, o, h, l, c, v, tb."""
    rng = np.random.default_rng(seed)
    ts = end_open_ms - (n - 1 - np.arange(n)) * MIN
    c = np.round(price * np.exp(np.cumsum(rng.standard_t(4, n) * 5e-4)) / step) * step
    o = np.r_[c[0], c[:-1]]
    w = np.abs(rng.normal(0, 3e-4, n))
    h = np.round(np.maximum(o, c) * (1 + w) / step + 0.5) * step
    l = np.round(np.minimum(o, c) * (1 - w) / step - 0.5) * step
    v = rng.uniform(1, 2, n)
    # eight decimals, as Binance prints them: what the reader parses back is then the same number, bit for bit
    return np.c_[ts.astype(float), np.round(np.c_[o, h, l, c, v, v * rng.uniform(0.3, 0.7, n)], 8)]


def kline(row) -> list:
    """One (ts, o, h, l, c, v, tb) row as Binance sends it: numbers as strings, closeTime = open + 59,999 ms."""
    ts = int(row[0])
    return [ts, f'{row[1]:.8f}', f'{row[2]:.8f}', f'{row[3]:.8f}', f'{row[4]:.8f}', f'{row[5]:.8f}', ts + MIN - 1,
            f'{row[4] * row[5]:.8f}', 100, f'{row[6]:.8f}', f'{row[4] * row[6]:.8f}', '0']


class FakeBinance:
    """Canned answers for binance.Binance(get=...). data: {coin: rows}. `now` is Binance's clock in ms: a minute
    whose open time is at or before it is served, so the last row of an answer can be a minute that is still open,
    as on the real API. `fail` holds answers to give first: (status, headers) or a FetchError to raise."""

    def __init__(self, data: dict, now: float, skew_ms: float = 0.0):
        self.data, self.now, self.skew_ms = data, float(now), skew_ms
        self.urls, self.fail = [], []

    def clock(self) -> float:
        """This machine's clock: Binance's minus the skew."""
        return self.now - self.skew_ms

    def __call__(self, url: str, timeout: float) -> tuple:
        self.urls.append(url)
        if self.fail:
            f = self.fail.pop(0)
            if isinstance(f, Exception):
                raise f
            return f[0], f[1], b''
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path.endswith('/time'):
            return 200, {}, json.dumps({'serverTime': int(self.now)}).encode()
        if not u.path.endswith('/klines') or q.get('interval') != '1m' or not q.get('symbol', '').endswith('USDT'):
            return 404, {}, b''
        rows = self.data.get(q['symbol'][:-4])
        if rows is None:
            return 400, {}, b''
        keep = (rows[:, 0] >= int(q.get('startTime', 0))) & (rows[:, 0] <= self.now)
        if 'endTime' in q:
            keep &= rows[:, 0] <= int(q['endTime'])
        out = [kline(r) for r in rows[keep][:int(q.get('limit', 500))]]
        return 200, {}, json.dumps(out).encode()

    def klines(self) -> list:
        return [u for u in self.urls if '/klines' in u]


def pack_row(coin: str, key: str, h: int = 15, rank: int = 1, aliases=(), direction: int = 1, sha: str = 'sha-' + 'x' * 8, **over) -> dict:
    """A traded pack row with the fields python/oracle/heat_pack.py writes."""
    tf, rest = key.split(':', 1)
    reading, level = rest.rsplit('=', 1)
    row = {'coin': coin, 'h': h, 'key': key, 'aliases': list(aliases), 'tf': tf, 'reading': reading, 'level': level, 'dir': direction,
           'call': 'up' if direction > 0 else 'down', 'rank_coin': rank, 'rank_all': rank, 'batch10': False, 'rank_share_coin': rank,
           'above_twin_max': True, 'n_A': 1000, 'n_B': 200, 'days_B': 365, 'share_A': 54.0, 'share_B': 53.25, 'share_over_B': 3.2,
           'odds_A': 5.0, 'odds_B': 3.25, 't_A': 9.0, 't_B': 4.0, 'oheat_B': 94.5, 'move_B': 0.31, 'hold_B': 8.2, 'hold_over_B': 0.7,
           'best_B': 14.3, 'dip_B': -6.2, 'wd_B': 28.9, 'tick_B': 0.001, 'table_sha256': sha}
    row.update(over)
    return row


def write_pack(path, rows: list, shas: dict, top: int = 40, stamp: str = 'run 43030435253, test pack') -> str:
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, 'w') as f:
        json.dump({'schema': 'oracle-heat-pack-1', 'horizons': [15, 60], 'top': top, 'table_sha256': shas, 'rows': rows, 'stamp': stamp}, f)
    return str(path)


def write_meta(meta_dir, coin: str, meta: dict) -> None:
    os.makedirs(os.path.join(meta_dir, coin), exist_ok=True)
    with open(os.path.join(meta_dir, coin, 'meta.json'), 'w') as f:
        json.dump(meta, f)


def settings(tmp_path, pack: str, meta_dir: str, oracle: str, assets: str = 'BTC,ETH', window: int = 600, **flags):
    """The reader's settings for a test: everything under tmp_path, nothing from the real environment."""
    from heat_reader import config
    argv = ['--calls-file', str(tmp_path / 'data' / 'heat_calls.json'), '--reader-dir', str(tmp_path / 'data' / 'heat_reader'), '--pack-file', str(pack),
            '--meta-dir', str(meta_dir), '--oracle-path', str(oracle), '--assets', assets, '--window-bars', str(window)]
    for k, v in flags.items():
        argv += [f'--{k.replace("_", "-")}', str(v)]
    return config.load(argv, env={})


def reader_for(s, fake: 'FakeBinance'):
    """A Reader on canned Binance answers, on the fake's clock, that never really sleeps."""
    from heat_reader.binance import Binance
    from heat_reader.reader import Reader
    src = Binance(s.binance_api, get=fake, now_ms=fake.clock, sleep=lambda sec: None, pace=0)
    return Reader(s, source=src, now_ms=fake.clock, log=lambda text: None, sleep=lambda sec: None)


def contract() -> dict:
    """Field names of the bot's contract, read from bot/heat/types.ts: {interface: (required, optional)}."""
    with open(os.path.join(REPO, 'bot', 'heat', 'types.ts')) as f:
        src = f.read()
    out = {}
    for name in ('HeatCallRow', 'HeatCoinCalls', 'HeatCallsFile'):
        m = re.search(r'export interface %s \{\n(.*?)\n\}' % name, src, re.S)
        assert m, f'bot/heat/types.ts has no interface {name}'
        fields = re.findall(r'^  (\w+)(\??):', m.group(1), re.M)
        out[name] = ({f for f, q in fields if not q}, {f for f, q in fields if q})
    return out


def assert_contract(obj: dict) -> None:
    """A written calls file has exactly the bot's fields, with the kinds of values the bot's reader accepts."""
    c = contract()

    def fields(o, name):
        req, opt = c[name]
        assert req <= set(o) <= req | opt, (name, sorted(set(o) ^ req))

    fields(obj, 'HeatCallsFile')
    assert obj['v'] == 1 and obj['source'] == 'oracle-heat' and isinstance(obj['run'], str) and obj['run']
    assert isinstance(obj['packSha'], str) and isinstance(obj['writtenAt'], int) and 1e11 <= obj['writtenAt'] < 1e14
    assert isinstance(obj['coins'], dict)
    for coin, cc in obj['coins'].items():
        assert not coin.upper().startswith('DOGE')
        fields(cc, 'HeatCoinCalls')
        assert isinstance(cc['asOf'], int) and isinstance(cc['tableSha'], str) and isinstance(cc['ok'], bool) and isinstance(cc['calls'], list)
        assert cc['ok'] or (isinstance(cc.get('why'), str) and cc['why'] and cc['calls'] == [])
        for row in cc['calls']:
            fields(row, 'HeatCallRow')
            assert row['kind'] == 'single' and row['dir'] in (1, -1) and row['tf'] in (1, 5, 15, 60) and 0 <= row['share'] <= 1
            assert isinstance(row['key'], str) and row['key'].startswith(f"{row['tf']}m:") and isinstance(row['aliases'], list)
            assert row['barClose'] == cc['asOf'] and row['rank'] >= 1 and row['of'] >= 1 and isinstance(row['h'], int)
            assert all(isinstance(row[k], (int, float)) and not isinstance(row[k], bool) for k in ('heat', 'odds', 'rank', 'of'))


def bot_parse(text: str):
    """The same text through the bot's own reader (bot/heat/heatSource.ts parseHeatCalls), when node and that file
    are there: {'error': ...} or {'coins': {coin: {ok, why, calls}}}. None when it cannot be run here."""
    if not os.path.isfile(os.path.join(REPO, 'bot', 'heat', 'heatSource.ts')) or not os.path.isdir(os.path.join(REPO, 'node_modules', 'tsx')):
        return None
    js = ("import { parseHeatCalls } from './bot/heat/heatSource.ts';"
          "let s = ''; process.stdin.on('data', (d) => { s += d; }); process.stdin.on('end', () => {"
          " const r = parseHeatCalls(s);"
          " const out = r.snapshot ? { coins: Object.fromEntries([...r.snapshot.coins].map(([k, c]) => [k, { ok: c.ok, why: c.why, calls: c.calls.length, asOf: c.asOf }])),"
          " run: r.snapshot.run } : { error: r.error };"
          " console.log('HEATPARSE ' + JSON.stringify(out)); });")
    try:
        p = subprocess.run(['node', '--import', 'tsx', '--input-type=module', '-e', js], input=text, capture_output=True, text=True, cwd=REPO, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r'^HEATPARSE (.*)$', p.stdout, re.M)
    return json.loads(m.group(1)) if m else None


def _oracle_ref() -> str:
    """The oracle commit the check job is pinned to (python/heat_reader/CHECK_RUN), else the oracle branch."""
    try:
        with open(os.path.join(PACKAGE, 'CHECK_RUN')) as f:
            m = re.search(r'^oracle=([0-9a-f]{7,40})\s*$', f.read(), re.M)
            if m:
                return m.group(1)
    except OSError:
        pass
    return ORACLE_BRANCH


@pytest.fixture(scope='session')
def oracle_path(tmp_path_factory) -> str:
    """The folder that holds the oracle package: HEAT_ORACLE_PATH, else this checkout's python/, else the oracle
    branch's python/oracle taken out of git into a temporary folder (nothing in the checkout changes)."""
    for p in (os.environ.get('HEAT_ORACLE_PATH'), PYTHON_DIR):
        if p and os.path.isfile(os.path.join(p, 'oracle', 'heat_live.py')):
            return p
    out = tmp_path_factory.mktemp('oracle')
    for ref in dict.fromkeys((_oracle_ref(), ORACLE_BRANCH)):
        try:
            tar = subprocess.run(['git', '-C', REPO, 'archive', ref, 'python/oracle'], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            break
        if tar.returncode == 0:
            with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as t:
                try:
                    t.extractall(out, filter='data')
                except TypeError:                      # a Python from before the extraction filters
                    t.extractall(out)
            return str(out / 'python')
    pytest.skip('the oracle code is not in this checkout and not in git (set HEAT_ORACLE_PATH)')


@pytest.fixture(scope='session')
def engine(oracle_path):
    pytest.importorskip('talib')
    from heat_reader.engine import Engine
    return Engine(oracle_path)


class World:
    """Synthetic minutes for a few coins, a meta made by the engine itself, and the keys the engine fires."""

    def __init__(self, engine, coins=('BTC', 'ETH'), days: int = 8, window: int = 600, tfs=(1, 5), end_ms: int = None):
        from heat_reader.engine import frame
        self.engine, self.window, self.tfs = engine, window, list(tfs)
        self.end = T0 + 5 * 60 * MIN if end_ms is None else end_ms            # a 5-minute close, so both timeframes close
        self.steps = {'BTC': 0.01, 'ETH': 0.01, 'SOL': 0.0001, 'XRP': 0.00001}
        self.data, self.meta, self.frame = {}, {}, frame
        extra = 30                                                             # minutes after `end`, served as time moves on
        for i, c in enumerate(coins):
            self.data[c] = walk(days * 1440 + extra, self.end + (extra - 1) * MIN, step=self.steps.get(c, 0.01),
                                price=60_000.0 * self.steps.get(c, 0.01) / 0.01, seed=11 + i)
            m = self.grid(c, self.end)
            edges = {}
            for k in self.tfs:
                _, used, _ = engine.live.tf_codes(m, k, edges=None, step=self.steps.get(c, 0.01), window=None, a_rows=(0, m['n']))
                edges.update(used)
            self.meta[c] = {'edges': edges, 'price_step': self.steps.get(c, 0.01), 'table_sha256': f'sha-{c}'}

    def rows(self, coin: str, end_ms: int) -> np.ndarray:
        r = self.data[coin]
        return r[r[:, 0] < end_ms]

    def grid(self, coin: str, end_ms: int) -> dict:
        return self.engine.live.grid(self.frame(self.rows(coin, end_ms)), end_ms=end_ms)

    def events(self, coin: str, end_ms: int, tfs=None) -> dict:
        """The engine asked directly, with no reader in between: every key firing at end_ms."""
        need = self.engine.need_minutes(self.window, self.tfs) * MIN
        r = self.rows(coin, end_ms)
        m = self.engine.live.grid(self.frame(r[r[:, 0] >= end_ms - need]), end_ms=end_ms)
        return self.engine.live.active_keys(m, self.meta[coin], tfs=tfs or self.tfs, window=self.window, levels=True)

    def fake(self, now: float = None, skew_ms: float = 0.0) -> FakeBinance:
        return FakeBinance(self.data, self.end + 3000 if now is None else now, skew_ms)


@pytest.fixture(scope='session')
def world(engine):
    return World(engine)


__all__ = ['FakeBinance', 'FetchError', 'World', 'assert_contract', 'bot_parse', 'contract', 'kline', 'pack_row', 'reader_for', 'settings', 'walk',
           'write_meta', 'write_pack', 'T0', 'REPO', 'PACKAGE']
