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

Two more files for perpetuals (spec Addendum 4), loaded only with HEAT_PERP_PACKS=true (the default):
  perp_pack.json       schema oracle-heat-pack-1 with horizons 240 and 1440: singles as in the traded pack, on the long
                       tables of the same run. Their hash is not the coin's main table hash; they are read with the main
                       edges because the oracle checked that the long tables' edges equal them (edges_as_main).
  perp_pair_pack.json  schema oracle-heat-pairs-1 at 240 and 1440, with the pair pack's fire rule.
Their rows go into the calls file like the main rows, with h 240 or 1440, of = perp_pack's `top`, and a pair's rank on
the perp singles' ladder of its horizon. They carry no live_parity: a perp row that stands on an indicator the main
packs mark live_parity false (PVI at fd88805) is skipped. Missing or unusable perp files, or a bad perp row of a coin,
never touch the main rows: the perp rows are left out and the status says why.

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
PERP, PERP_PAIRS = 'perp_pack.json', 'perp_pair_pack.json'
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
SKIP_PERP_RUN = 'perp pack of another run'
SKIP_PERP_EDGES = 'perp edges not those of live_meta'
SKIP_PERP_H = 'perp row on a main horizon'
DOMINANCE = ('BTC.D', 'USDT.D', 'Dom')


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


def indicator_of(name: str) -> str:
    """The indicator behind a key or reading name, without timeframe, level or ' sign': '5m:PVI sign=above 0', '1m:PVI'
    and 'PVI' all give 'PVI'. A context or clock state keeps its name ('UTC4h')."""
    b = re.sub(r'^\d+m:', '', str(name).rsplit('=', 1)[0])
    return b[:-5] if b.endswith(' sign') else b


def row_names(row: dict) -> list:
    """Every key and reading name a pack row stands on: its key and aliases (a pair key split at ' | '), `when`,
    the `conds` readings, `readings` and `reading`."""
    names = []
    for k in [row.get('key'), row.get('when'), row.get('reading')] + list(row.get('aliases') or []) + list(row.get('readings') or []):
        if isinstance(k, str) and k:
            names += k.split(' | ')
    for c in row.get('conds') or []:
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], str):
            names.append(c[0])
    return names


def parity_off(pack: dict, pairs: dict) -> set:
    """The indicators the main packs say the live reader does not reproduce exactly (live_parity false: PVI at
    fd88805): the traded pack's live_reader_parity.indicators_that_differ, the pair pack's indicators_that_differ_live,
    and the indicator of every traded row marked live_parity false. The perp packs carry no live_parity, so a perp row
    on one of these indicators is skipped by this set."""
    out = set()
    lrp = pack.get('live_reader_parity')
    for src in ((lrp.get('indicators_that_differ') if isinstance(lrp, dict) else None), pairs.get('indicators_that_differ_live')):
        if isinstance(src, list):
            out.update(indicator_of(x) for x in src if isinstance(x, str) and x)
    for r in pack.get('rows') or []:
        if isinstance(r, dict) and r.get('live_parity') is False and isinstance(r.get('key'), str):
            out.add(indicator_of(r['key']))
    return out


def _dominance(row: dict, p: dict) -> bool:
    """A row that needs the dominance feed the reader does not have yet."""
    return row.get('dominance') is True or any(rd.split(' ')[0] in DOMINANCE for rd, _ in p['conds']) or p['when'].split(' ')[0] in DOMINANCE


def _edges_as_main(src: dict, coin: str) -> bool:
    """The perp file says the coin's long-table edges and price step are the main tables' (what live_meta.json holds)."""
    e = src.get('edges_as_main_tables') if isinstance(src.get('edges_as_main_tables'), dict) else {}
    e = e.get(coin)
    return isinstance(e, dict) and e.get('n_different') == 0 and e.get('price_step_same') is True


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
        # The perp packs (h240, h1440), kept apart so a problem with them never touches the rows above.
        self.perp = None          # None when the perp packs are not loaded, else {'wanted', 'skipped', 'problem'}
        self.perp_rows = []       # perp singles published when they fire
        self.perp_pairs = []      # perp pairs and triples (check_pair, plus 'rank' on the perp ladder)
        self.perp_aliases = {}    # the aliases a perp pair's trigger fires through: the main ones and the perp singles'
        self.perp_top = 0         # perp_pack's `top`: the `of` of every perp row

    def skip(self, reason: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def perp_skip(self, reason: str) -> None:
        self.perp['skipped'][reason] = self.perp['skipped'].get(reason, 0) + 1

    def drop_perp(self, why: str) -> None:
        """Leave out every perp row of the coin, say why, and ask the engine only for what the main rows need."""
        self.perp['problem'] = why
        self.perp_rows, self.perp_pairs = [], []
        self.perp['wanted'] = dict.fromkeys(self.perp['wanted'], 0)
        self.index()

    def counts(self) -> dict:
        out = {'wanted': dict(self.wanted), 'skipped': dict(sorted(self.skipped.items()))}
        if self.perp is not None:
            out['perp'] = {'wanted': dict(self.perp['wanted']), 'skipped': dict(sorted(self.perp['skipped'].items()))}
            if self.perp['problem']:
                out['perp']['problem'] = self.perp['problem']
        return out

    def index(self) -> set:
        """want, states and tfs from the rows the coin publishes. Returns the readings behind them (what the meta must
        hold edges for)."""
        want, states = set(), set()
        for r in self.rows + self.perp_rows:
            want.add(r['key'])
            want.update(r.get('aliases') or [])
        for pairs, aliases in ((self.pairs, self.aliases), (self.perp_pairs, self.perp_aliases)):
            for p in pairs:
                want.add(p['when'])
                want.update(aliases.get(p['when'], []))
                states.update(rd for rd, _ in p['conds'])
        self.want, self.states = want, states
        timed = [k for k in want | states if key_tf(k) is not None]    # a context trigger or state needs no timeframe of bars
        self.tfs = sorted({key_tf(k) for k in timed})
        return {base_of(k) for k in timed}

    @property
    def long_states(self) -> set:
        return {s for s in self.states if key_tf(s) == LONG_TF}

    def _missing_edges(self, rows: list, pairs: list, zone_events: set, zone_states: set) -> list:
        no_edges = set(self.meta.get('no_edges') or [])
        need = []
        for r in rows:
            need += [(k, k.rsplit('=', 1)[-1], zone_events) for k in [r['key']] + list(r.get('aliases') or [])]
        for p in pairs:
            need.append((p['when'], p['when'].rsplit('=', 1)[-1], zone_events))
            need += [(f'{rd}={lv}', lv, zone_states) for rd, lv in p['conds']]
        missing = []
        for name, level, zone in need:
            b = name.rsplit('=', 1)[0]
            if key_tf(b) is None or b.endswith(' sign') or level not in zone or b in no_edges:
                continue
            if b not in self.meta['edges']:
                missing.append(name)
        return missing

    def check_edges(self, zone_events: set, zone_states: set) -> None:
        """A row whose reading has no zone edges in the meta could never fire, and the lane would then trade a colder
        row in its place without anyone knowing. That is a pack and a meta that do not belong together: the coin is
        refused. A perp row without edges leaves out the coin's perp rows only (h15 and h60 go on). zone_events,
        zone_states: the engine's names of the zone events and of the zone levels."""
        if self.problem or self.meta is None:
            return
        missing = self._missing_edges(self.rows, self.pairs, zone_events, zone_states)
        if missing:
            self.problem = f'{META} has no zone edges for {len(missing)} row(s), first {missing[0]}'
            return
        if self.perp is not None and (self.perp_rows or self.perp_pairs):
            missing = self._missing_edges(self.perp_rows, self.perp_pairs, zone_events, zone_states)
            if missing:
                self.drop_perp(f'{META} has no zone edges for {len(missing)} perp row(s), first {missing[0]}')


class Tables:
    """The packs and live_meta.json on disk, reloaded when a file changes (a new pack needs no restart).

    perp: also load perp_pack.json and perp_pair_pack.json. The reader passes HEAT_PERP_PACKS (default true); the parity
    replay leaves them out, because its fixtures check h15 and h60 only."""

    def __init__(self, pack_dir: str, assets: list, run: str = '', max_rank: int = 40, clock: bool = False, perp: bool = False):
        self.pack_dir, self.assets, self.run_override = pack_dir, list(assets), run
        self.max_rank, self.clock, self.perp = int(max_rank), bool(clock), bool(perp)
        self.problem = 'tables not loaded yet'     # a reason no coin can be read (a pack itself), else None
        self.perp_problem = None                   # with perp on: why the perp packs are not used (the main rows go on)
        self.pack_sha, self.run, self.top = '', run or 'unknown', 0
        self.files = {}                            # pack name: {'sha256', 'rows', 'schema'} of what was loaded
        self.coins = {}
        self._seen = None

    def path(self, name: str) -> str:
        return os.path.join(self.pack_dir, name)

    def _signature(self) -> tuple:
        sig = []
        for name in (TRADED, PAIRS, META) + ((CLOCK,) if self.clock else ()) + ((PERP, PERP_PAIRS) if self.perp else ()):
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
        self.perp_problem = None
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
        perp = self._perp_files() if self.perp else None
        off = parity_off(pack, pairs) if perp else set()
        shas = pack.get('table_sha256') if isinstance(pack.get('table_sha256'), dict) else {}
        for coin in self.assets:
            if not is_doge(coin):
                self.coins[coin] = self._coin(coin, pack, pairs, clock, meta, shas.get(coin), perp, off)

    def _perp_files(self):
        """(perp_pack, perp_pair_pack), or None with perp_problem saying why. The two go together: a perp pair replaces
        the perp single it refines, so without the pair pack the perp singles would be another bet."""
        try:
            perp = self._file(PERP, PACK_SCHEMA)
            top = perp.get('top')
            if isinstance(top, bool) or not isinstance(top, int) or top < 1:
                raise ValueError(f'{PERP} has no `top`')
            return perp, self._file(PERP_PAIRS, PAIR_SCHEMA)
        except ValueError as e:
            self.perp_problem = str(e)
            self.files.pop(PERP, None)
            self.files.pop(PERP_PAIRS, None)
            return None

    def _coin(self, coin: str, pack: dict, pairs: dict, clock, meta: dict, sha, perp=None, off=frozenset()) -> CoinTable:
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
        ladder = {}
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
        for name, src in ((PAIRS, pairs), (CLOCK, clock)):
            if src is None:
                continue
            problem = self._pairs(t, name, src, pack, ladder)
            if problem:
                t.problem = problem
                return t
        if perp is not None:
            main_h = {int(r['h']) for r in mine} | {h for h in (pack.get('horizons') or []) if isinstance(h, int)}
            self._perp_coin(t, pack, perp[0], perp[1], off, main_h)
        bases = t.index()
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

    def _pairs(self, t: CoinTable, name: str, src: dict, pack: dict, ladder: dict):
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
            elif _dominance(r, p):
                t.skip(SKIP_DOMINANCE)
            elif r.get('live_parity') is False:
                t.skip(SKIP_PARITY)
            elif is_clock and r.get('lift_above_twin_max') is not True:
                t.skip(SKIP_TWIN)
            else:
                p['rank'] = effective_rank(p['heat'], ladder.get(p['h'], []))
                t.pairs.append(p)
                t.wanted['clock' if is_clock else p['kind']] += 1
        return None

    def _perp_coin(self, t: CoinTable, pack: dict, perp: dict, pairs: dict, off: set, main_h: set) -> None:
        """Add the coin's publishable rows of the perp packs to t (t.perp_rows, t.perp_pairs), with the same rules as the
        main packs: singles up to HEAT_READER_MAX_RANK, pairs ranked on the perp singles' ladder of their horizon,
        dominance rows skipped. Also skipped: rows on a main horizon (the main packs own h15 and h60), rows of another
        run than the traded pack, rows whose long-table edges are not live_meta's, and rows on an indicator in `off`
        (parity_off). A row the bot must not trade from leaves out all the coin's perp rows, never its main ones."""
        t.perp = {'wanted': {'single': 0, 'pair': 0, 'triple': 0}, 'skipped': {}, 'problem': None}
        t.perp_top = top = perp['top']
        t.perp_aliases = {k: list(v) for k, v in t.aliases.items()}

        def fail(why: str) -> None:
            t.perp.update(skipped={}, problem=why)

        mine = [r for r in perp['rows'] if isinstance(r, dict) and r.get('coin') == t.coin]
        shas = perp.get('table_sha256') if isinstance(perp.get('table_sha256'), dict) else {}
        sha = shas.get(t.coin)
        if not mine:
            return fail(f'{PERP} has no rows for this coin')
        if not isinstance(sha, str) or not sha:
            return fail(f'{PERP} has no table hash for this coin')
        other_run = run_of(perp) != run_of(pack)
        edges_ok = _edges_as_main(perp, t.coin)
        ladder, rows = {}, []
        for i, r in enumerate(mine):
            try:
                call_row(r, top, 0)
                if r.get('table_sha256') not in (None, sha):
                    raise ValueError(f'its table hash is not the coin\'s in {PERP}')
            except ValueError as e:
                return fail(f'{PERP} row {i + 1} of this coin ({str(r.get("key"))[:60]}): {e}')
            have = t.perp_aliases.setdefault(r['key'], [])
            have += [a for a in r.get('aliases') or [] if a not in have]
            if int(r['h']) in main_h:
                t.perp_skip(SKIP_PERP_H)
                continue
            if r['rank_coin'] <= top:
                ladder.setdefault(int(r['h']), []).append(r['oheat_B'])
            if r['rank_coin'] > self.max_rank:
                t.perp_skip(SKIP_RANK)
            elif other_run:
                t.perp_skip(SKIP_PERP_RUN)
            elif not edges_ok or r.get('edges_as_main') is not True:
                t.perp_skip(SKIP_PERP_EDGES)
            elif any(indicator_of(n) in off for n in row_names(r)):
                t.perp_skip(SKIP_PARITY)
            else:
                rows.append(r)
        file_sha = pairs.get('table_sha256').get(t.coin) if isinstance(pairs.get('table_sha256'), dict) else None
        other_run = run_of(pairs) != run_of(pack)
        edges_ok = _edges_as_main(pairs, t.coin)
        prs = []
        for i, r in enumerate(x for x in pairs['rows'] if isinstance(x, dict) and x.get('coin') == t.coin):
            try:
                p = check_pair(r, top, PAIR_SCHEMA)
            except ValueError as e:
                return fail(f'{PERP_PAIRS} row {i + 1} of this coin ({str(r.get("key"))[:60]}): {e}')
            if p['h'] in main_h:
                t.perp_skip(SKIP_PERP_H)
            elif other_run:
                t.perp_skip(SKIP_PERP_RUN)
            elif r.get('table_sha256') != sha or file_sha not in (None, sha):
                t.perp_skip(SKIP_HASH)
            elif _dominance(r, p):
                t.perp_skip(SKIP_DOMINANCE)
            elif not edges_ok or r.get('edges_as_main') is not True:
                t.perp_skip(SKIP_PERP_EDGES)
            elif any(indicator_of(n) in off for n in row_names(r) + t.perp_aliases.get(p['when'], [])):
                # the trigger fires through its aliases too (join), so a PVI alias of the trigger counts as PVI
                t.perp_skip(SKIP_PARITY)
            else:
                p['rank'] = effective_rank(p['heat'], ladder.get(p['h'], []))
                prs.append(p)
        t.perp_rows, t.perp_pairs = rows, prs
        t.perp['wanted']['single'] = len(rows)
        for p in prs:
            t.perp['wanted'][p['kind']] += 1
