"""The oracle run's packs and live_meta.json: what the reader joins the engine's answer with.

Four files from one oracle commit (HEAT_PACK_DIR, research/oracle_heat/latest):
  traded_pack.json  schema oracle-heat-pack-1: per coin and horizon the single event levels by heat (rank_coin 1..40)
                    and by share. Only rows with rank_coin <= HEAT_READER_MAX_RANK are published: the share-only rows
                    are not above chance, and their 60-minute readings would need a 125-day window.
  pair_pack.json    schema oracle-heat-pairs-1: pairs and triples. A row fires when its `when` event fires at this
                    minute close AND every `conds` reading holds its level at the last closed bar of its own timeframe.
  clock_pack.json   schema oracle-heat-clock-pack-1: the same row format with clock conditions (UTC1h, NY30m,
                    Weekday). Loaded only with HEAT_CLOCK_PACK=true, and then only its rows whose lift is above the
                    no-signal twin's best (lift_above_twin_max): the rest add nothing over chance (spec Addendum 3).
  live_meta.json    {COIN: {price_step, table_sha256, edges, no_edges}}: what places a live reading in a level. A coin
                    whose table hash differs from the traded pack's is refused: its edges belong to another table.

Rows the parity check marked (live_parity false) and rows that need a dominance feed (the reader has none yet) are
never published; they are counted per coin with the reason, so the bot's status can show what was left out.
call_row() and pair_call() are the ONLY places a pack row becomes a row of the calls file (HeatCallRow in
bot/heat/types.ts).
"""
import hashlib
import json
import math
import os
import re

from heat_reader.config import is_doge

PACK_SCHEMA = 'oracle-heat-pack-1'
PAIR_SCHEMA = 'oracle-heat-pairs-1'
CLOCK_SCHEMA = 'oracle-heat-clock-pack-1'
TRADED, PAIRS, CLOCK, META = 'traded_pack.json', 'pair_pack.json', 'clock_pack.json', 'live_meta.json'
SOURCE = 'oracle-heat'
MAX_PACK_BYTES = 32 * 1024 * 1024
MAX_META_BYTES = 64 * 1024 * 1024
CONTEXT_TF = 15                # the engine's context states (UTC4h, dominance) fire at every 15-minute close while they hold
LONG_TF = 60                   # readings of this timeframe need the long window: their states are cached per coin

# Why a row is not published. Fixed texts: the status sidecar and the check job's report show them as they are.
SKIP_RANK = 'rank beyond HEAT_READER_MAX_RANK'
SKIP_PARITY = 'live_parity false'
SKIP_DOMINANCE = 'dominance (no feed)'
SKIP_HASH = 'table hash differs'
SKIP_RUN = 'clock pack of another run'
SKIP_TWIN = 'clock row not above the twin'


def tf_minutes(tf) -> int:
    """A pack timeframe in minutes: '1m' 1, '5m' 5, '15m' 15, '60m' or '1h' 60."""
    m = re.fullmatch(r'(\d+)([mh])', str(tf))
    if not m or int(m.group(1)) <= 0:
        raise ValueError(f'timeframe {tf!r} is not minutes or hours')
    return int(m.group(1)) * (60 if m.group(2) == 'h' else 1)


def key_tf(name: str):
    """Timeframe in minutes of a key or reading name ('5m:RSI7=low' 5), or None for a context or clock state
    ('UTC4h', 'BTC.D 1d', 'Weekday')."""
    m = re.match(r'^(\d+)m:', str(name))
    return int(m.group(1)) if m else None


def _num(v, name: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f'{name} is not a finite number')
    return v


def _common(row: dict, top: int) -> dict:
    """The fields singles and pairs share: h, dir, heat, share (a fraction: the pack stores a percent), odds, and
    hold, dip and move when the pack has them."""
    h = _num(row.get('h'), 'h')
    if h <= 0 or h != int(h):
        raise ValueError('h is not a whole number of minutes')
    d = row.get('dir')
    if isinstance(d, bool) or d not in (1, -1):
        raise ValueError('dir is neither 1 nor -1')
    share = _num(row.get('share_B'), 'share_B')
    if not 0 <= share <= 100:
        raise ValueError('share_B is not a percent')
    aliases = row.get('aliases') or []
    if not isinstance(aliases, list) or not all(isinstance(a, str) and a for a in aliases):
        raise ValueError('aliases is not a list of keys')
    if isinstance(top, bool) or not isinstance(top, int) or top < 1:
        raise ValueError('the pack has no `top`')
    out = {'h': int(h), 'dir': int(d), 'heat': _num(row.get('oheat_B'), 'oheat_B'), 'share': round(share / 100.0, 6),
           'odds': _num(row.get('odds_B'), 'odds_B')}
    for name, src in (('hold', 'hold_B'), ('dip', 'dip_B'), ('move', 'move_B')):
        if row.get(src) is not None:
            out[name] = _num(row[src], src)
    return out, list(aliases)


def call_row(row: dict, top: int, bar_close: int) -> dict:
    """A single of the traded pack as the bot's HeatCallRow. Raises ValueError with a plain reason for a row the bot
    must not trade from (a missing number, a share that is not a percent, a side that is neither up nor down).

    rank = the pack's rank_coin, of = the pack's `top`, share = share_B as a fraction, odds, heat, hold, dip and move
    = the check-period numbers. aliases are other names of the same event: one row, one bet."""
    key = row.get('key')
    if not isinstance(key, str) or not key:
        raise ValueError('key is missing')
    tf = tf_minutes(row.get('tf'))
    if not key.startswith(f'{tf}m:'):
        raise ValueError(f'key is not on its timeframe {row.get("tf")!r}')
    rank = _num(row.get('rank_coin'), 'rank_coin')
    if rank < 1:
        raise ValueError('rank_coin is below 1')
    common, aliases = _common(row, top)
    out = {'key': key, 'kind': 'single', 'aliases': aliases, 'tf': tf, 'h': common.pop('h'), 'dir': common.pop('dir'), 'rank': rank,
           'of': top}
    out.update(common)
    out['barClose'] = int(bar_close)
    return out


def check_pair(row: dict, top: int, schema: str) -> dict:
    """A pair or triple row of the pair or clock pack, checked and prepared for the join: {'kind', 'key', 'when',
    'conds' [(reading, level)], 'tf' (the trigger's bars: a context trigger fires at 15-minute closes), 'h', 'heat',
    'row'}. Raises ValueError with a plain reason."""
    key, when = row.get('key'), row.get('when')
    if not isinstance(key, str) or not key:
        raise ValueError('key is missing')
    if not isinstance(when, str) or '=' not in when:
        raise ValueError('when is not an event key')
    kind = row.get('kind')
    conds = row.get('conds')
    if kind not in ('pair', 'triple') or not isinstance(conds, list) or len(conds) != (1 if kind == 'pair' else 2):
        raise ValueError('kind is neither a pair with one condition nor a triple with two')
    if not all(isinstance(c, list) and len(c) == 2 and all(isinstance(x, str) and x for x in c) for c in conds):
        raise ValueError('conds is not a list of [reading, level]')
    if schema == CLOCK_SCHEMA and not all(c[0] in ('UTC1h', 'NY30m', 'Weekday', 'UTC4h') for c in conds):
        raise ValueError('a clock row conditions on something other than the clock')
    common, _ = _common(row, top)
    tf = key_tf(when) or CONTEXT_TF
    return {'kind': kind, 'key': key, 'when': when, 'conds': [(c[0], c[1]) for c in conds], 'tf': tf, 'h': common['h'],
            'heat': common['heat'], 'row': row}


def pair_call(p: dict, rank: float, top: int, bar_close: int) -> dict:
    """A firing pair or triple as the bot's HeatCallRow: trig = its `when` (the single it refines, in the traded
    pack's spelling), rank = its effective rank on the coin's single ladder, of = the traded pack's `top`."""
    common, aliases = _common(p['row'], top)
    out = {'key': p['key'], 'kind': p['kind'], 'aliases': aliases, 'trig': p['when'], 'tf': p['tf'], 'h': common.pop('h'),
           'dir': common.pop('dir'), 'rank': rank, 'of': top}
    out.update(common)
    out['barClose'] = int(bar_close)
    return out


def effective_rank(heat: float, ladder: list) -> int:
    """A pair's place on the coin's single ladder at its horizon: 1 + the heat-ranked singles (rank_coin 1..top)
    with a higher oheat_B. pair_pack's own rank_coin counts every pair event of the coin and is no ladder rank."""
    return 1 + sum(1 for x in ladder if x > heat)


def base_of(key: str) -> str:
    """The reading behind an event key or state name: '1m:RSI14=very low' gives '1m:RSI14'; a sign reading's value
    series is the reading without ' sign'."""
    b = key.rsplit('=', 1)[0]
    return b[:-5] if b.endswith(' sign') else b


def run_of(pack: dict) -> str:
    m = re.search(r'run (\d{6,})', f"{pack.get('run', '')} {pack.get('stamp', '')}")
    return m.group(1) if m else ''


def _read(path: str, cap: int) -> bytes:
    if os.path.getsize(path) > cap:
        raise ValueError(f'{os.path.basename(path)} is too large to be this file')
    with open(path, 'rb') as f:
        return f.read()


def load_meta(meta: dict, coin: str) -> dict:
    """The coin's part of live_meta.json. Raises ValueError with a plain reason when it has none."""
    data = meta.get(coin) if isinstance(meta, dict) else None
    if data is None:
        raise ValueError(f'{META} has no entry for {coin}')
    if not isinstance(data, dict) or not isinstance(data.get('edges'), dict):
        raise ValueError(f'{META} has no zone edges for {coin}')
    return data


class CoinTable:
    """One coin's part of the packs with its meta, or the reason the coin cannot be read."""

    def __init__(self, coin: str):
        self.coin = coin
        self.rows = []            # singles that are published when they fire, as in the traded pack
        self.pairs = []           # pairs and triples that are published when they fire (check_pair, plus 'rank')
        self.aliases = {}         # traded pack key: its aliases (every traded row of the coin, published or not)
        self.want = set()         # every key the engine is asked for: singles, their aliases, pair triggers
        self.states = set()       # readings whose level at their own last closed bar the pairs condition on
        self.tfs = []             # timeframes (minutes) all of that uses
        self.table_sha = ''
        self.meta = None          # {'edges', 'price_step', 'table_sha256'}: only the readings the rows need
        self.problem = None
        self.wanted = {'single': 0, 'pair': 0, 'triple': 0, 'clock': 0}
        self.skipped = {}         # reason: rows of the packs not published for it

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def counts(self) -> dict:
        return {'wanted': dict(self.wanted), 'skipped': dict(sorted(self.skipped.items()))}

    @property
    def long_states(self) -> set:
        return {s for s in self.states if key_tf(s) == LONG_TF}

    def check_edges(self, zone_events: set, zone_states: set) -> None:
        """A row whose reading has no zone edges in the meta could never fire, and the lane would then trade a colder
        row in its place without anyone knowing. That is a pack and a meta that do not belong together: the coin is
        refused. zone_events, zone_states: the engine's names of the zone events and of the zone levels."""
        if self.problem or self.meta is None:
            return
        no_edges = set(self.meta.get('no_edges') or [])
        need = []
        for r in self.rows:
            need += [(k, k.rsplit('=', 1)[-1], zone_events) for k in [r['key']] + list(r.get('aliases') or [])]
        for p in self.pairs:
            need.append((p['when'], p['when'].rsplit('=', 1)[-1], zone_events))
            need += [(f'{rd}={lv}', lv, zone_states) for rd, lv in p['conds']]
        missing = []
        for name, level, zone in need:
            b = name.rsplit('=', 1)[0]
            if key_tf(b) is None or b.endswith(' sign') or level not in zone or b in no_edges:
                continue
            if b not in self.meta['edges']:
                missing.append(name)
        if missing:
            self.problem = f'{META} has no zone edges for {len(missing)} row(s), first {missing[0]}'


class Tables:
    """The packs and live_meta.json on disk, reloaded when a file changes (a new pack needs no restart)."""

    def __init__(self, pack_dir: str, assets: list, run: str = '', max_rank: int = 40, clock: bool = False):
        self.pack_dir, self.assets, self.run_override = pack_dir, list(assets), run
        self.max_rank, self.clock = int(max_rank), bool(clock)
        self.problem = 'tables not loaded yet'     # a reason no coin can be read (a pack itself), else None
        self.pack_sha, self.run, self.top = '', run or 'unknown', 0
        self.files = {}                            # pack name: {'sha256', 'rows', 'schema'} of what was loaded
        self.coins = {}
        self._seen = None

    def path(self, name: str) -> str:
        return os.path.join(self.pack_dir, name)

    def _signature(self) -> tuple:
        sig = []
        for name in (TRADED, PAIRS, META) + ((CLOCK,) if self.clock else ()):
            try:
                st = os.stat(self.path(name))
                sig.append((name, st.st_mtime_ns, st.st_size, st.st_ino))
            except OSError:
                sig.append((name, None))
        return tuple(sig)

    def refresh(self) -> bool:
        """Load the tables again when a file changed since the last look. True when they were loaded."""
        sig = self._signature()
        if sig == self._seen:
            return False
        self._seen = sig
        self._load()
        return True

    def _file(self, name: str, schema: str, cap: int = MAX_PACK_BYTES) -> dict:
        """One pack, checked as a whole. Raises ValueError with the reason no coin can be read."""
        try:
            raw = _read(self.path(name), cap)
        except (OSError, ValueError) as e:
            raise ValueError(f'{name} cannot be read in {self.pack_dir} ({type(e).__name__})') from None
        try:
            data = json.loads(raw)
        except ValueError:
            raise ValueError(f'{name} is not JSON') from None
        if schema is not None:
            if not isinstance(data, dict) or data.get('schema') != schema or not isinstance(data.get('rows'), list):
                raise ValueError(f'{name} is not of schema {schema}')
            self.files[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'rows': len(data['rows']), 'schema': schema}
        elif not isinstance(data, dict):
            raise ValueError(f'{name} is not an object keyed by coin')
        else:
            self.files[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'coins': len(data)}
        return data

    def _load(self) -> None:
        self.coins, self.pack_sha, self.top, self.files = {}, '', 0, {}
        self.run = self.run_override or 'unknown'
        try:
            pack = self._file(TRADED, PACK_SCHEMA)
            top = pack.get('top')
            if isinstance(top, bool) or not isinstance(top, int) or top < 1:
                raise ValueError(f'{TRADED} has no `top`')
            pairs = self._file(PAIRS, PAIR_SCHEMA)
            clock = self._file(CLOCK, CLOCK_SCHEMA) if self.clock else None
            meta = self._file(META, None, MAX_META_BYTES)
        except ValueError as e:
            self.problem = str(e)
            return
        self.top = top
        self.pack_sha = self.files[TRADED]['sha256']
        if not self.run_override:
            self.run = run_of(pack) or 'unknown'
        self.problem = None
        shas = pack.get('table_sha256') if isinstance(pack.get('table_sha256'), dict) else {}
        for coin in self.assets:
            if not is_doge(coin):
                self.coins[coin] = self._coin(coin, pack, pairs, clock, meta, shas.get(coin))

    def _coin(self, coin: str, pack: dict, pairs: dict, clock, meta: dict, sha) -> CoinTable:
        t = CoinTable(coin)
        top = self.top
        mine = [r for r in pack['rows'] if isinstance(r, dict) and r.get('coin') == coin]
        if not mine:
            t.problem = f'{TRADED} has no rows for this coin'
            return t
        if not isinstance(sha, str) or not sha:
            t.problem = f'{TRADED} has no table hash for this coin'
            return t
        t.table_sha = sha
        tfs, bases, ladder = set(), set(), {}
        for i, r in enumerate(mine):
            try:
                call_row(r, top, 0)
                if r.get('table_sha256') not in (None, sha):
                    raise ValueError('its table hash is not the coin\'s')
            except ValueError as e:
                t.problem = f'{TRADED} row {i + 1} of this coin ({str(r.get("key"))[:60]}): {e}'
                return t
            t.aliases[r['key']] = list(r.get('aliases') or [])
            if r['rank_coin'] <= top:
                ladder.setdefault(int(r['h']), []).append(r['oheat_B'])
            if r['rank_coin'] > self.max_rank:
                t.skip(SKIP_RANK)
            elif r.get('live_parity') is False:
                t.skip(SKIP_PARITY)
            else:
                t.rows.append(r)
                t.wanted['single'] += 1
                t.want.add(r['key'])
                t.want.update(r.get('aliases') or [])
                tfs.add(tf_minutes(r['tf']))
        for name, src in ((PAIRS, pairs), (CLOCK, clock)):
            if src is None:
                continue
            problem = self._pairs(t, name, src, pack, ladder, tfs)
            if problem:
                t.problem = problem
                return t
        for k in t.want | t.states:                 # a context trigger or state needs no timeframe of bars
            if key_tf(k) is not None:
                tfs.add(key_tf(k))
                bases.add(base_of(k))
        t.tfs = sorted(tfs)
        try:
            m = load_meta(meta, coin)
        except ValueError as e:
            t.problem = str(e)
            return t
        if m.get('table_sha256') != sha:
            t.problem = (f'table hash differs: the pack is of table {sha[:12]}, {META} of table '
                         f'{str(m.get("table_sha256"))[:12]}')
            return t
        t.meta = {'edges': {b: m['edges'][b] for b in bases if b in m['edges']}, 'price_step': m.get('price_step'), 'table_sha256': sha,
                  'no_edges': [b for b in (m.get('no_edges') or []) if b in bases]}
        return t

    def _pairs(self, t: CoinTable, name: str, src: dict, pack: dict, ladder: dict, tfs: set):
        """Add the coin's publishable rows of the pair or clock pack to t. Returns a reason to refuse the coin (a row
        the bot must not trade from), else None."""
        is_clock = name == CLOCK
        file_sha = (src.get('table_sha256') or {}).get(t.coin) if isinstance(src.get('table_sha256'), dict) else None
        # The pair pack is of the traded pack's table; the clock pack is of the clock tables of the same run.
        expect = file_sha if is_clock else t.table_sha
        other_run = is_clock and run_of(src) != run_of(pack)
        for i, r in enumerate(x for x in src['rows'] if isinstance(x, dict) and x.get('coin') == t.coin):
            try:
                p = check_pair(r, self.top, src['schema'])
            except ValueError as e:
                return f'{name} row {i + 1} of this coin ({str(r.get("key"))[:60]}): {e}'
            if other_run:
                t.skip(SKIP_RUN)
            elif r.get('table_sha256') != expect or (not is_clock and file_sha not in (None, t.table_sha)):
                t.skip(SKIP_HASH)
            elif r.get('dominance') is True or any(rd.split(' ')[0] in ('BTC.D', 'USDT.D', 'Dom') for rd, _ in p['conds']) \
                    or p['when'].split(' ')[0] in ('BTC.D', 'USDT.D', 'Dom'):
                t.skip(SKIP_DOMINANCE)
            elif r.get('live_parity') is False:
                t.skip(SKIP_PARITY)
            elif is_clock and r.get('lift_above_twin_max') is not True:
                t.skip(SKIP_TWIN)
            else:
                p['rank'] = effective_rank(p['heat'], ladder.get(p['h'], []))
                t.pairs.append(p)
                t.wanted['clock' if is_clock else p['kind']] += 1
                t.want.add(p['when'])
                t.want.update(t.aliases.get(p['when'], []))
                t.states.update(rd for rd, _ in p['conds'])
        return None
