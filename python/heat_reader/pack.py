"""The traded pack and the coins' metas: what the reader joins the engine's fired keys with.

The pack (schema oracle-heat-pack-1, python/oracle/heat_pack.py) lists, per coin and horizon, the event levels a
lane may act on, ranked by heat. A coin's meta (meta.json, or its slim copy inside live_meta.json) holds the zone
edges that place a live reading in a level, the price step and the hash of the frozen table. Pack and meta must be
of the same table: the hash is compared and a coin whose two hashes differ is refused.

call_row() is the ONE place a pack row becomes a row of the calls file (HeatCallRow in bot/heat/types.ts).
"""
import hashlib
import json
import math
import os
import re

from heat_reader.config import is_doge

PACK_SCHEMA = 'oracle-heat-pack-1'
SOURCE = 'oracle-heat'
MAX_PACK_BYTES = 32 * 1024 * 1024
MAX_META_BYTES = 64 * 1024 * 1024


def tf_minutes(tf) -> int:
    """A pack timeframe in minutes: '1m' 1, '5m' 5, '15m' 15, '60m' or '1h' 60."""
    m = re.fullmatch(r'(\d+)([mh])', str(tf))
    if not m or int(m.group(1)) <= 0:
        raise ValueError(f'timeframe {tf!r} is not minutes or hours')
    return int(m.group(1)) * (60 if m.group(2) == 'h' else 1)


def _num(v, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f'{name} is not a finite number')
    return v


def call_row(row: dict, top: int, bar_close: int) -> dict:
    """A row of the traded pack as the bot's HeatCallRow. Raises ValueError with a plain reason for a row the bot
    must not trade from (a missing number, a share that is not a percent, a side that is neither up nor down).

    rank = the pack's rank inside the coin and horizon, of = how many the pack lists (its `top`), share = share_B as
    a fraction (the pack stores a percent), odds, heat, hold, dip and move = the check-period numbers. Every pack row
    is a single event level. aliases are other names of the same event: one row, one bet."""
    key = row.get('key')
    if not isinstance(key, str) or not key:
        raise ValueError('key is missing')
    tf = tf_minutes(row.get('tf'))
    if not key.startswith(f'{tf}m:'):
        raise ValueError(f'key is not on its timeframe {row.get("tf")!r}')
    h = _num(row.get('h'), 'h')
    if h <= 0 or h != int(h):
        raise ValueError('h is not a whole number of minutes')
    d = row.get('dir')
    if isinstance(d, bool) or d not in (1, -1):
        raise ValueError('dir is neither 1 nor -1')
    rank = _num(row.get('rank_coin'), 'rank_coin')
    if rank < 1:
        raise ValueError('rank_coin is below 1')
    share = _num(row.get('share_B'), 'share_B')
    if not 0 <= share <= 100:
        raise ValueError('share_B is not a percent')
    aliases = row.get('aliases') or []
    if not isinstance(aliases, list) or not all(isinstance(a, str) and a for a in aliases):
        raise ValueError('aliases is not a list of keys')
    if isinstance(top, bool) or not isinstance(top, int) or top < 1:
        raise ValueError('the pack has no `top`')
    out = {'key': key, 'kind': 'single', 'aliases': list(aliases), 'tf': tf, 'h': int(h), 'dir': int(d), 'rank': rank, 'of': top,
           'heat': _num(row.get('oheat_B'), 'oheat_B'), 'share': round(share / 100.0, 6), 'odds': _num(row.get('odds_B'), 'odds_B')}
    for name, src in (('hold', 'hold_B'), ('dip', 'dip_B'), ('move', 'move_B')):
        if row.get(src) is not None:
            out[name] = _num(row[src], src)
    out['barClose'] = int(bar_close)
    return out


def base_of(key: str) -> str:
    """The reading behind an event key: '1m:RSI14=very low' gives '1m:RSI14'; a sign reading's value series is the
    reading without ' sign'."""
    b = key.rsplit('=', 1)[0]
    return b[:-5] if b.endswith(' sign') else b


def _read(path: str, cap: int) -> bytes:
    if os.path.getsize(path) > cap:
        raise ValueError(f'{os.path.basename(path)} is too large to be this file')
    with open(path, 'rb') as f:
        return f.read()


def meta_paths(meta_dir: str, coin: str) -> list:
    """Where a coin's meta may be, in the order tried: its own meta.json, then the slim live_meta.json keyed by coin.
    HEAT_META_DIR may also name a live_meta.json file directly."""
    if os.path.isfile(meta_dir):
        return [meta_dir]
    return [os.path.join(meta_dir, coin, 'meta.json'), os.path.join(meta_dir, 'live_meta.json')]


def load_meta(meta_dir: str, coin: str) -> dict:
    """The coin's meta as the engine takes it (edges, price_step) with its table_sha256. Raises ValueError with a
    plain reason when there is none."""
    for i, p in enumerate(meta_paths(meta_dir, coin)):
        if not os.path.isfile(p):
            continue
        try:
            data = json.loads(_read(p, MAX_META_BYTES))
        except (OSError, ValueError) as e:
            raise ValueError(f'{os.path.basename(p)} cannot be read ({str(e)[:80]})') from None
        keyed = os.path.isfile(meta_dir) or i == 1                 # live_meta.json: one object per coin
        if keyed:
            data = data.get(coin) if isinstance(data, dict) else None
            if data is None:
                continue
        if not isinstance(data, dict) or not isinstance(data.get('edges'), dict):
            raise ValueError(f'{os.path.basename(p)} has no zone edges for {coin}')
        return data
    raise ValueError(f'no meta.json for {coin} under {meta_dir}')


class CoinTable:
    """One coin's part of the pack with its meta, or the reason the coin cannot be read."""

    def __init__(self, coin: str):
        self.coin = coin
        self.rows = []            # the coin's pack rows, as in the file
        self.want = set()         # every key and alias: what the engine is asked for
        self.tfs = []             # timeframes (minutes) those rows use
        self.table_sha = ''
        self.meta = None          # {'edges', 'price_step', 'table_sha256'}: only the readings the rows need
        self.problem = None

    def check_edges(self, zone_levels: set) -> None:
        """A row on a zone level whose reading has no edges in the meta could never fire, and the lane would then
        trade a colder row in its place without anyone knowing. That is a pack and a meta that do not belong
        together: the coin is refused. zone_levels: the engine's names of the zone events."""
        if self.problem or self.meta is None:
            return
        missing = [r['key'] for r in self.rows if r['key'].rsplit('=', 1)[-1] in zone_levels and base_of(r['key']) not in self.meta['edges']]
        if missing:
            self.problem = f'meta.json has no zone edges for {len(missing)} pack row(s), first {missing[0]}'


class Tables:
    """The pack and metas on disk, reloaded when a file changes (a new pack or meta needs no restart)."""

    def __init__(self, pack_file: str, meta_dir: str, assets: list, run: str = ''):
        self.pack_file, self.meta_dir, self.assets, self.run_override = pack_file, meta_dir, list(assets), run
        self.problem = 'tables not loaded yet'     # a reason no coin can be read (the pack itself), else None
        self.pack_sha, self.run, self.top = '', run or 'unknown', 0
        self.coins = {}
        self._seen = None

    def _signature(self) -> tuple:
        sig = []
        paths = [self.pack_file] + [p for c in self.assets for p in meta_paths(self.meta_dir, c)]
        for p in dict.fromkeys(paths):
            try:
                st = os.stat(p)
                sig.append((p, st.st_mtime_ns, st.st_size, st.st_ino))
            except OSError:
                sig.append((p, None))
        return tuple(sig)

    def refresh(self) -> bool:
        """Load the tables again when a file changed since the last look. True when they were loaded."""
        sig = self._signature()
        if sig == self._seen:
            return False
        self._seen = sig
        self._load()
        return True

    def _load(self) -> None:
        self.coins, self.pack_sha, self.top = {}, '', 0
        self.run = self.run_override or 'unknown'
        try:
            raw = _read(self.pack_file, MAX_PACK_BYTES)
        except (OSError, ValueError) as e:
            self.problem = f'the traded pack cannot be read: {os.path.basename(self.pack_file)} ({type(e).__name__})'
            return
        self.pack_sha = hashlib.sha256(raw).hexdigest()
        try:
            pack = json.loads(raw)
        except ValueError:
            self.problem = 'the traded pack is not JSON'
            return
        if not isinstance(pack, dict) or pack.get('schema') != PACK_SCHEMA or not isinstance(pack.get('rows'), list):
            self.problem = f'the traded pack is not of schema {PACK_SCHEMA}'
            return
        top = pack.get('top')
        if isinstance(top, bool) or not isinstance(top, int) or top < 1:
            self.problem = 'the traded pack has no `top`'
            return
        self.top = top
        if not self.run_override:
            m = re.search(r'run (\d{6,})', f"{pack.get('run', '')} {pack.get('stamp', '')}")
            self.run = m.group(1) if m else 'unknown'
        self.problem = None
        shas = pack.get('table_sha256') if isinstance(pack.get('table_sha256'), dict) else {}
        for coin in self.assets:
            if is_doge(coin):
                continue
            t = CoinTable(coin)
            self.coins[coin] = t
            t.rows = [r for r in pack['rows'] if isinstance(r, dict) and r.get('coin') == coin]
            if not t.rows:
                t.problem = 'the traded pack has no rows for this coin'
                continue
            sha = shas.get(coin)
            if not isinstance(sha, str) or not sha:
                t.problem = 'the traded pack has no table hash for this coin'
                continue
            t.table_sha = sha
            tfs = set()
            for i, r in enumerate(t.rows):
                try:
                    call_row(r, top, 0)
                    if r.get('table_sha256') not in (None, sha):
                        raise ValueError('its table hash is not the coin\'s')
                    tfs.add(tf_minutes(r['tf']))
                except ValueError as e:
                    t.problem = f'pack row {i + 1} of this coin ({str(r.get("key"))[:60]}): {e}'
                    break
                t.want.add(r['key'])
                t.want.update(r.get('aliases') or [])
            if t.problem:
                continue
            t.tfs = sorted(tfs)
            try:
                meta = load_meta(self.meta_dir, coin)
            except ValueError as e:
                t.problem = str(e)
                continue
            if meta.get('table_sha256') != sha:
                t.problem = (f'table hash differs: the pack is of table {sha[:12]}, the meta of table '
                             f'{str(meta.get("table_sha256"))[:12]}')
                continue
            bases = {base_of(k) for k in t.want}
            t.meta = {'edges': {b: meta['edges'][b] for b in bases if b in meta['edges']}, 'price_step': meta.get('price_step'),
                      'table_sha256': sha}
