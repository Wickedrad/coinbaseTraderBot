"""OR-HM2 section 5: the league, the lessons (TA-Lib usage cards), the pack for the bot and the parity
(python/oracle/prereg/OR-HM2.md: "What is reported", "Chance scale", "Pack for the bot"; build plan section 5). It reads
only the small files each series job writes (oracle.heat_hm2.run_series) and changes no line of oracle.heat, no stored
table and no HM1 pack.

  python3 -m oracle.heat_hm2_league league --inputs <dir of the series outputs <COIN>[-twinN]/> --hm1 <dir> --out <dir>
               [--packs research/oracle_heat/latest] [--main-metas <dir of <COIN>/meta.json of run 43030435253>]
               [--gates research/oracle_heat/hm2/part3/gate_rows.json] [--patterns <dir of Part 4's chart_league.md>]
               [--pack <hm2_pack.json>] [--live-meta <hm2_live_meta.json>] [--feeds spot,others,...] [--stamp <text>]
  python3 -m oracle.heat_hm2_league parity --asset BTC --csv <1m.csv> --others ETH=<csv>,SOL=<csv>,XRP=<csv> --perp <csv>
               --fund <csv> --oi <csv> --cal <csv> --dom <dir> [--found <json>] --series <the coin's HM2 series dir>
               --main-meta <COIN/meta.json> --other-metas <dir> --live-meta <hm2_live_meta.json> [--pack <hm2_pack.json>]
               --out <dir> [--days 3] [--procs 4]
  python3 -m oracle.heat_hm2_league live-ready --pack <hm2_pack.json> --parity <dir of <COIN>/parity.json> [--feeds a,b]
  python3 -m oracle.heat_hm2_league merge-gates --pack <hm2_pack.json> --gates <gate_rows.json>
(python3 -m oracle.heat_hm2 league / parity hand over to this module.)

What the league does, over every series (a coin or one of its no-signal twins, the identical pipeline):
  series      each <dir>/meta.json of schema oracle-heat-hm2-1. A whole job (part 0/1, or the finish job of a --part
              split) is used as it is; a series with --part files only is merged here (summary counts and candidate
              pools add up exactly; it has no triples and no re-measure, and the league says so).
  lists       per coin, kind (pair, triple) and horizon (all six): the 40 best by oheat_B, the 40 best by iheat_B, the 20
              best by lheat_B; at most 3 rows per reading in each list; exact copies (identical numbers on both periods)
              and near copies (B entry sets overlapping 80% or more, Jaccard, from the re-measure) collapse into the
              best row's aliases. The same on every twin. The only floor is the engine's sample (the candidates carry it).
  unseen      every list again over the cells with seen_in_league = none (provenance: no part in a pack the bot loads
              and the pair not stored in HM1), ranked the same way. No significance mark filters it: part_tmax and
              parts_hot stay columns, and the chance table splits its counts by part_tmax bin instead.
  marks       columns only: hot on A (|t_A| at the engine's t = 3 bar), replicated on B (one-sided p <= 0.023 in the A
              direction), BHY q (from the log-binned histogram of every cell's B p in the summary counts, pooled over
              the coins, within kind, horizon and measure), above the max of the coin's three twins (same list, slice,
              kind and horizon), and move_steps_B (the onset's B move / the price step).
  chance      per kind and horizon, the coins (pooled) against the twin sets' median and range: cells with a sample and
              under the floor, kept direction, kept lift, kept interaction (iota, iota_add, iota_robust), t_B >= 2, the
              persistence curve by A |t| bin (all cells and by part_tmax stratum), the 99th percentile and max of each
              heat, and the rows above the twins' max. A warning names any missing twin set.
  model       the GBM zones of both models (TA, ALL) beside the twins' zones, the last-candle baseline (faded: what
              bid-ask bounce alone gives), the league's best single level at that horizon (HM1's direction_all; also at
              matched windows per day), and ALL against TA.
  lessons     the family table (kept iota_robust share minus the twins', per family pair at 15/60/240), one usage card
              per TA-Lib function (settings x timeframe grid: B odds of each zone in its A direction, fade or follow of
              the extreme zones, the strongest horizon on A; its own call by level from HM1's direction league; the
              model's mean contribution by level on 2025 minutes; its best partner per data family by iheat_B, with
              iota_with_call (False: a stand-aside lesson); the kept-interaction share of its pair cells, from the
              scan's per-reading tally in cards.json.gz), each number beside the twins' median and range; and each
              coin's top rows in words (Eastern and UTC).
  pack        hm2_pack.json (oracle-heat-hm2-pack-1, allow_nan False): the lists at 15, 60 and 240 minutes (pairs and
              triples, the unseen lists included) and the GBM zone rows; fire = 'onset' (the first minute close at which
              every condition holds; entry at the next minute's open), the held numbers as columns. hm2_live_meta.json:
              per coin the price step, the edges of every reading behind a row, the norm tables and the other coins'
              edges a cross-coin reading needs. live_ready stays False until the parity step sets it.
  parity      Dec 29-31, 2025: heat_xdata.levels_at on a window against the history codes of every new reading, the
              pack's engine readings from heat_live.active_keys on the live reader's window against the whole grid, and
              the GBM zones of the pack's model rows from the window's features (tree_eval, the trees' stored zone edges)
              against the series' own gbm_codes.npz. live-ready sets a
              row's live_ready when every reading behind it agrees on at least 99.5% of the checked minutes and the bot
              has its feed (perp, funding and open interest need a Binance perpetual feed, macro a 2026 calendar, daily
              markets their closes, Coinbase readings a Coinbase minute feed).
  hooks       Part 3 (OR-HM2-part3.md): gate rows live in their own file (gate_rows.json) and are merged into the pack
              (merge_gate_rows; every other row stays byte-identical, non_gate_sha) and into the pack view of league.md;
              a league run with --gates puts them back (and gate_rows.json's `live` block as hm2_live_meta.json's
              part3). Part 4 (OR-HM2-part4.md): a "Chart patterns" section of league.md from chart_summary.json /
              chart_league.md (--patterns), and upsert_section for a later run of either part.
Coin minutes 2020-01-01 to 2025-12-31 only. A MAP on coin price, not a Kalshi-price result. NEVER DOGE.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import re
import time

import numpy as np
import pandas as pd

from oracle import heat
from oracle import heat_hm2 as hm
from oracle.common import DAY, MIN

SCHEMA_SUMMARY = 'oracle-heat-hm2-league-1'
SCHEMA_PACK = 'oracle-heat-hm2-pack-1'
SCHEMA_LIVE = 'oracle-heat-hm2-live-meta-1'
SCHEMA_PARITY = 'oracle-heat-hm2-parity-1'
SCHEMA_CARDS = 'oracle-heat-hm2-usage-cards-1'
COINS = ['BTC', 'ETH', 'SOL', 'XRP']            # never DOGE
TWIN_SEEDS = [1, 2, 3]
KINDS = ('pair', 'triple')
MEASURES = hm.MEASURES                            # oheat, iheat, lheat
SLICES = ('all', 'unseen')
TOP = hm.TOP                                      # 40 / 40 / 20
PER_READING = hm.PER_READING                      # 3
NEAR_COPY = hm.NEAR_COPY                          # 0.8
BHY_Q = 0.10
LIVE_MIN = 0.995                                  # parity share a reading needs on Dec 29-31, 2025
MD_TOP = 10                                       # rows per list in league.md (every row is in lists.csv.gz)
WORDS_TOP = 3                                     # rows in words per coin, list and pack horizon
HM1_PACKS = ('traded_pack.json', 'pair_pack.json', 'clock_pack.json', 'perp_pack.json', 'perp_pair_pack.json')
GATE_KINDS = ('gate', 'gate2')                    # Part 3's rows (OR-HM2-part3.md, Outputs 4)
PACK_KINDS = ('pair', 'triple', 'model')
MEASURE_T = {'oheat': ('t', 'dir'), 'iheat': ('t_robust', 'd_iota'), 'lheat': ('t_lift', 'dir')}
P_KIND = {'oheat': 0, 'iheat': 1, 'lheat': 2}    # SummaryCounts.p kinds: odds, iota_robust, lift
RM_KIND = {'pair': (('xstate', 'state'), ('xonset', 'onset')), 'triple': (('xtriple', 'state'), ('xtriple', 'onset'))}
RM_COLS = ['n', 'per_day', 'days', 'wd', 'tick', 'hold_up', 'hold_dn', 'excess', 'se', 't', 'edge_p', 't_p', 'deff_p', 'p_up', 'p_dn',
           'best_up', 'best_dn', 'dip_up', 'dip_dn', 'excessL', 'bx_up25', 'bx_dn25', 'move_steps']
SAME = hm.LIST_SAME                 # exact copies: identical numbers on both periods
EXTREME = ('very low', 'very high')
# the feed each family needs live (OR-HM2, Pack for the bot); 'spot' = the coin's own 1-minute bars
FAMILY_FEED = {'cross-coin': 'other coins', 'perp': 'binance perp', 'open interest': 'binance perp', 'daily markets': 'daily markets',
               'macro': 'calendar 2026', 'coinbase': 'coinbase minutes', 'btcdom': 'btcdom', 'book': 'order book',
               'cvdp': 'perp taker flow', 'liqmap': 'open interest history', 'ls': 'long-short ratio history', 'prem': 'premium index history',
               'whale': 'spot trade tape', 'whalep': 'perp trade tape', 'bookp': 'order book'}      # OR-XD readings (--outside): research only, the bot has neither feed
DEFAULT_FEEDS = ('spot', 'other coins', 'dominance')
CONTEXT_FEED = {'BTC.D': 'dominance', 'USDT.D': 'dominance', 'Dom': 'dominance'}
SECTION = '<!-- hm2:section:{} -->'
SECTION_END = '<!-- /hm2:section:{} -->'


def _log_none(*a, **k):
    pass


def _refuse_doge(*xs):
    for x in xs:
        if x and 'DOGE' in str(x).upper():
            raise SystemExit('NEVER DOGE')


def _f(x, nd: int = 4):
    """A JSON number (None for NaN / inf / missing)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def _i(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return int(v) if math.isfinite(v) else None


def _read_json(p: str):
    if not p or not os.path.isfile(p):
        return None
    with open(p) as f:
        return json.load(f)


def _read_csv(p: str) -> pd.DataFrame:
    if not p or not os.path.isfile(p):
        return pd.DataFrame()
    try:
        return pd.read_csv(p, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _dump(obj, path: str, indent=1) -> str:
    """JSON with allow_nan False; returns the sha256 of the text written."""
    txt = json.dumps(hm._clean(obj), indent=indent, allow_nan=False)
    with open(path, 'w') as f:
        f.write(txt)
    return hashlib.sha256(txt.encode()).hexdigest()


def _conds(c) -> list:
    return json.loads(c) if isinstance(c, str) else list(c or [])


def _cond_names(c) -> list:
    return [r for r, _ in _conds(c)]


# ------------------------------------------------------------------------------------------------------- the series
class Series:
    """One series' small files: meta, summary counts {'pair', 'triple'} (heat_hm2.SummaryCounts), candidates, the
    re-measured rows (heat.csv.gz), near copies, usage.json, the usage-card inputs (cards.json.gz) and the GBM zones
    (series_gbm: meta.json learner.trees and the calls in usage.json); `complete` False for a series with --part files
    only."""

    def __init__(self, d: str, meta: dict):
        self.dir, self.meta = d, meta
        self.label, self.asset, self.twin = str(meta['label']), str(meta['asset']), int(meta.get('twin', 0))
        _refuse_doge(self.label, self.asset)
        self.complete, self.notes = True, []
        self.summ, self.cands, self.heat, self.jac = {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        self.usage, self.cards, self.gbm = {}, None, {}
        self.amap = {r['name']: [r['name']] + list(r.get('aliases', [])) for r in meta.get('readings', [])}
        self.rfam = {}
        for r in meta.get('readings', []):
            for n in [r['name']] + list(r.get('aliases', [])):
                self.rfam[n] = r.get('family')

    @property
    def real(self) -> bool:
        return self.twin == 0


def _read_cards(d: str):
    """The usage cards' raw inputs of a series (heat_hm2_learn.write_cards: cards.json.gz; cards.json also read)."""
    p = os.path.join(d, 'cards.json.gz')
    if os.path.isfile(p):
        with gzip.open(p, 'rt') as f:
            return json.load(f)
    return _read_json(os.path.join(d, 'cards.json'))


def _summ(sj: dict) -> dict:
    return {k: hm.SummaryCounts.from_json(sj[k]) for k in KINDS if sj and k in sj}


def find_series(inputs: str, depth: int = 4) -> dict:
    """{label: [(dir, meta), ...]} of every meta.json of schema oracle-heat-hm2-1 under `inputs` (shards, trees and
    pattern folders are skipped). A label or asset naming DOGE stops the league."""
    out = {}
    base = os.path.abspath(inputs)
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in ('shards', 'trees', 'patterns', 'league', 'part3'))
        if root[len(base):].count(os.sep) >= depth:
            dirs[:] = []
        if 'meta.json' not in files:
            continue
        mt = _read_json(os.path.join(root, 'meta.json'))
        if not isinstance(mt, dict) or mt.get('schema') != 'oracle-heat-hm2-1':
            continue
        _refuse_doge(mt.get('label'), mt.get('asset'), root)
        out.setdefault(str(mt['label']), []).append((root, mt))
    return out


def load_series(group: list, log=_log_none) -> Series:
    """One series from its directories: a whole job (part 0/1, or the finish job after a --part split, preferred) as
    it is; --part files only: their summary counts and candidate pools merged (exact), flagged incomplete."""
    full = [(d, m) for d, m in group if int((m.get('part') or [0, 1])[1]) == 1]
    if full:
        full.sort(key=lambda x: ('merged_parts' not in (x[1].get('pairs') or {}), x[0]))
        d, mt = full[0]
        s = Series(d, mt)
        if len(full) > 1:
            s.notes.append(f'{len(full)} whole jobs found; used {d}')
        sj = _read_json(os.path.join(d, 'summary_counts.json'))
        s.summ = _summ(sj)
        s.cands = _read_csv(os.path.join(d, 'candidates.csv.gz'))
        s.heat = _read_csv(os.path.join(d, 'heat.csv.gz'))
        s.jac = _read_csv(os.path.join(d, 'near_copies.csv.gz'))
    else:
        parts = sorted(group, key=lambda x: int(x[1]['part'][0]))
        S = int(parts[0][1]['part'][1])
        s = Series(parts[0][0], parts[0][1])
        s.complete = False
        have = sorted({int(m['part'][0]) for _, m in parts})
        if have != list(range(S)):
            s.notes.append(f'--part files {have} of {S} (missing parts)')
        s.notes.append('only --part files: no triples, no re-measure, no learner (the finish job did not run)')
        cands = hm.Candidates()
        for d, m in parts:
            sj = _read_json(os.path.join(d, 'summary_counts.json'))
            for k, v in _summ(sj).items():
                s.summ[k] = v if k not in s.summ else s.summ[k].merge(v)
            cands.add(_read_csv(os.path.join(d, 'candidates.csv.gz')))
        s.cands = cands.frame()
    u = _read_json(os.path.join(s.dir, 'usage.json')) or {}
    s.usage = {k: v for k, v in u.items() if isinstance(v, dict)}
    s.cards = _read_cards(s.dir)
    s.gbm = series_gbm(s.meta, s.usage)
    if len(s.cands):
        s.cands = s.cands.assign(key=s.cands['key'].astype(str), seen_in_league=s.cands['seen_in_league'].astype(str))
    log(f'  {s.label}: {len(s.cands):,} candidate rows, {len(s.heat):,} re-measured rows{"; " + "; ".join(s.notes) if s.notes else ""}')
    return s


def series_gbm(meta: dict, usage: dict) -> dict:
    """The GBM zone readings of one series from its own files: per GBM.<model><H> the zone edges on the raw score, the
    used readings and the tree file (meta.json learner.trees, written by heat_hm2_learn.run_learner; the tree's hm2.zone
    block holds the same edges) and the call (usage.json <model><H>.call, heat_hm2_learn.call_stats)."""
    g = {}
    for k, t in ((meta.get('learner') or {}).get('trees') or {}).items():
        m = re.match(r'^(TA|ALL)_h(\d+)$', str(k))
        if not m or not isinstance(t, dict):
            continue
        nm = f'GBM.{m.group(1)}{m.group(2)}'
        g[nm] = {'model': m.group(1), 'h': int(m.group(2)), 'edges': t.get('edges'), 'used': list(t.get('used') or []), 'file': t.get('file'),
                 'sha256': t.get('sha256'), 'call': None}
    for k, u in (usage or {}).items():
        c = u.get('call') if isinstance(u, dict) else None
        if isinstance(c, dict) and c.get('name'):
            m = re.match(r'^GBM\.(TA|ALL)(\d+)$', c['name'])
            if m:
                g.setdefault(c['name'], {'model': m.group(1), 'h': int(m.group(2)), 'edges': None, 'used': [], 'file': None, 'sha256': None})['call'] = c
    return {'readings': g}


# ---------------------------------------------------------------------------------------------------- HM1 inputs
def hm1_inputs(hm1_dir: str = '', packs_dir: str = '', main_metas: str = '') -> dict:
    """Where the HM1 files are: the packs the bot loads (HM1_PACKS; --packs, or <hm1>/, <hm1>/latest/), the stored pair
    tables pairs_<COIN>.csv.gz, direction_all.csv.gz and HM1's summary.json (<hm1>/, <hm1>/pairs/, <hm1>/league/), and
    the main run's metas <COIN>/meta.json (--main-metas, <hm1>/metas/, <hm1>/)."""
    def first(*ps):
        return next((p for p in ps if p and os.path.exists(p)), '')
    h = hm1_dir or ''
    roots = [r for r in (packs_dir, h, os.path.join(h, 'latest') if h else '', os.path.join(h, 'packs') if h else '') if r]
    packs = [p for p in (first(*[os.path.join(r, nm) for r in roots]) for nm in HM1_PACKS) if p]
    j = lambda *a: os.path.join(h, *a) if h else ''
    pairs = {C: first(j('pairs', f'pairs_{C}.csv.gz'), j(f'pairs_{C}.csv.gz'), j('league', 'pairs', f'pairs_{C}.csv.gz')) for C in COINS}
    mm = main_metas or ''
    metas = {C: first(os.path.join(mm, C, 'meta.json') if mm else '', j('metas', C, 'meta.json'), j(C, 'meta.json')) for C in COINS}
    return {'packs': packs, 'pairs': pairs, 'direction_all': first(j('direction_all.csv.gz'), j('league', 'direction_all.csv.gz')),
            'summary': first(j('summary.json'), j('league', 'summary.json')), 'metas': metas,
            'metas_dir': mm or (j('metas') if j('metas') and os.path.isdir(j('metas')) else h)}


def seen_in_league(conds_list, hm1, amap: dict = None) -> list:
    """(review) Provenance by reading names, the series' rule (heat_hm2.provenance): 'pack' when a part's level (or
    an alias's) is in a pack the bot loads (traded, pair, clock, perp, perp pair; an HM1 event key matches the state
    level it names: 'low (falling in)' -> 'low'), 'stored' when two of the readings were stored together as an HM1
    relationship (pairs_<COIN>.csv.gz), 'none' otherwise. direction_all is never read: it lists every level.
    hm1: heat_hm2.load_hm1(...) or a directory (all its packs and pair tables). amap: name -> [name, aliases]."""
    if isinstance(hm1, str):
        p = hm1_inputs(hm1)
        hm1 = hm.load_hm1(p['packs'], '')
        for f in p['pairs'].values():
            if f:
                hm1['stored'] |= hm.load_hm1((), f)['stored']
    lv, st = hm1.get('levels', {}), hm1.get('stored', set())
    names = lambda n: (amap or {}).get(n, [n])
    out = []
    for c in conds_list:
        cs = _conds(c)
        pk = False
        for r, lvs in cs:
            have = set()
            for n in names(r):
                have |= lv.get(n, set())
            if any(hm.EVENT_SUFFIX.sub('', str(x)) in have for x in lvs if x != 'NA'):
                pk = True
        stored = any(frozenset((x, y)) in st for i, (a, _) in enumerate(cs) for b, _ in cs[i + 1:] for x in names(a) for y in names(b) if x != y)
        out.append('pack' if pk else 'stored' if stored else 'none')
    return out


def check_provenance(series: list, hp: dict, log=_log_none) -> dict:
    """The league's check of the series' provenance labels: recomputed from the reading names (seen_in_league) for
    every candidate row, and a twin's labels against its coin's for the same keys (labels go by names)."""
    out = {}
    if not hp['packs'] and not any(hp['pairs'].values()):
        return {'checked': False, 'note': 'no HM1 packs or pair tables given: the series labels are used as they are'}
    by_coin = {}
    for s in series:
        if not len(s.cands):
            continue
        if s.asset not in by_coin:                  # (review fix) pack levels of this coin's rows only, as the series job
            by_coin[s.asset] = {'levels': hm.load_hm1(hp['packs'], '', coin=s.asset)['levels'],
                                'stored': hm.load_hm1((), hp['pairs'].get(s.asset, ''))['stored']}
        u = s.cands.drop_duplicates('key')
        lab = seen_in_league(u.conds.tolist(), by_coin[s.asset], s.amap)
        bad = u.seen_in_league.to_numpy() != np.array(lab, object)
        out[s.label] = {'rows': int(len(u)), 'mismatched': int(bad.sum()), 'examples': u.key[bad].head(3).tolist()}
    reals = {s.asset: s for s in series if s.real and len(s.cands)}
    for s in series:
        if s.real or s.asset not in reals or not len(s.cands):
            continue
        a = reals[s.asset].cands.drop_duplicates('key').set_index('key').seen_in_league
        b = s.cands.drop_duplicates('key').set_index('key').seen_in_league
        k = a.index.intersection(b.index)
        out.setdefault(s.label, {})['same_keys_as_coin'] = int(len(k))
        out[s.label]['labels_differ_from_coin'] = int((a.loc[k] != b.loc[k]).sum())
    bad = sum(v.get('mismatched', 0) + v.get('labels_differ_from_coin', 0) for v in out.values())
    log(f'  provenance check: {bad} labels differ from the names rule')
    return {'checked': True, 'series': out, 'differ': int(bad)}


# ---------------------------------------------------------------------------------------------- the re-measure view
def remeasure_view(df: pd.DataFrame) -> pd.DataFrame:
    """heat.csv.gz with split A beside split B, one row per (kind, key, h, form)."""
    KEY = ['kind', 'key', 'h', 'form']
    if df is None or not len(df):
        return pd.DataFrame(columns=KEY + [f'{c}_{s}' for c in RM_COLS for s in 'AB']).set_index(KEY)
    df = df.assign(key=df['key'].astype(str), form=df['form'].astype(str) if 'form' in df else 'state')
    cols = [c for c in RM_COLS if c in df.columns]
    A = df[df.split == 'A'].drop_duplicates(KEY).set_index(KEY)[cols]
    B = df[df.split == 'B'].drop_duplicates(KEY).set_index(KEY)[cols]
    j = A.join(B, lsuffix='_A', rsuffix='_B', how='outer')
    for c in RM_COLS:
        for s in 'AB':
            if f'{c}_{s}' not in j.columns:
                j[f'{c}_{s}'] = np.nan
    return j


def _base_B(meta: dict, h: int) -> dict:
    b = (meta.get('base') or {}).get('B') or {}
    i = hm.H_SCAN.index(int(h))
    g = lambda k: (b.get(k) or [np.nan] * len(hm.H_SCAN))[i] if isinstance(b.get(k), list) else np.nan
    return {'p_up': g('p_up'), 'p_dn': g('p_dn'), 'hold_up': b.get('hold_up'), 'hold_dn': b.get('hold_dn')}


def signed_rm(j: pd.DataFrame, d: np.ndarray, base: list) -> pd.DataFrame:
    """The re-measured numbers of rows j (remeasure_view columns) signed in direction d (+1 up / -1 down): the league's
    units (heat._view and heat._direction). base: per row the B base {'p_up', 'p_dn', 'hold_up', 'hold_dn'}."""
    d = np.asarray(d, float)
    up = d > 0
    col = lambda c: j[c].to_numpy(float)
    pick = lambda a, b: np.where(up, col(a), col(b))
    bpu = np.array([b['p_up'] if b['p_up'] is not None else np.nan for b in base], float)
    bpd = np.array([b['p_dn'] if b['p_dn'] is not None else np.nan for b in base], float)
    bhu = np.array([b['hold_up'] if b['hold_up'] is not None else np.nan for b in base], float)
    bhd = np.array([b['hold_dn'] if b['hold_dn'] is not None else np.nan for b in base], float)
    wd = np.where(np.isfinite(col('wd_B')), col('wd_B'), col('per_day_B'))
    o = {'n_A': col('n_A'), 'n_B': col('n_B'), 'days_B': col('days_B'), 'wd_B': wd,
         'share_A': 100 * pick('p_up_A', 'p_dn_A'), 'share_B': 100 * pick('p_up_B', 'p_dn_B')}
    o['share_over_B'] = o['share_B'] - 100 * np.where(up, bpu, bpd)
    o['odds_A'], o['odds_B'] = col('edge_p_A') * 100 * d, col('edge_p_B') * 100 * d
    o['t_A'], o['t_B'] = col('t_p_A') * d, col('t_p_B') * d
    o['oheat_B'] = wd * o['odds_B']
    o['move_B'] = col('excess_B') * d
    o['best_B'] = np.where(up, col('best_up_B'), -col('best_dn_B'))
    o['dip_B'] = np.where(up, col('dip_up_B'), -col('dip_dn_B'))
    o['hold_B'] = pick('hold_up_B', 'hold_dn_B')
    o['hold_over_B'] = o['hold_B'] - np.where(up, bhu, bhd)
    o['retL_B'] = col('excessL_B') * d                     # entered one minute later (report s11: the bid-ask bounce check)
    o['touch25_B'] = pick('bx_up25_B', 'bx_dn25_B')
    o['move_steps_B'] = col('move_steps_B') * d
    o['tick_B'] = col('tick_B')
    return pd.DataFrame(o, index=j.index)


def attach_remeasure(L: pd.DataFrame, rmv: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Adds the held (xstate / xtriple state) and onset (xonset / xtriple onset) numbers of each list row, signed in
    the row's direction, as held_* and onset_* columns (NaN where the row was not re-measured: the series job measures
    every row its lists can show, heat_hm2.remeasure, so a NaN here means a series of an older build)."""
    if not len(L):
        return L
    out = L.copy()
    for form_i, pre in ((0, 'held_'), (1, 'onset_')):
        keys = [(RM_KIND[k][form_i][0], key, int(h), RM_KIND[k][form_i][1]) for k, key, h in zip(L['kind'], L['key'], L['h'])]
        j = rmv.reindex(pd.MultiIndex.from_tuples(keys, names=rmv.index.names)) if len(rmv) else None
        if j is None:
            continue
        s = signed_rm(j.reset_index(drop=True), L['dir'].to_numpy(float), [_base_B(meta, h) for h in L['h']])
        for c in s.columns:
            out[pre + c] = s[c].to_numpy()
    out['remeasured'] = out['onset_n_B'].notna() if 'onset_n_B' in out else False
    out['move_steps_B'] = out['onset_move_steps_B'] if 'onset_move_steps_B' in out else np.nan
    out['retL_B'] = out['onset_retL_B'] if 'onset_retL_B' in out else np.nan
    return out


# ------------------------------------------------------------------------------------------------------- the lists
def _rows_readings(c) -> list:
    return list(dict.fromkeys(_cond_names(c)))


def make_list(pool: pd.DataFrame, measure: str, n: int, jac: pd.DataFrame = None, per_reading: int = PER_READING) -> pd.DataFrame:
    """One list: pool rows ranked by <measure>_B (ties by key), exact copies (identical numbers on both periods: the
    same event under two names) and near copies (B entry Jaccard >= NEAR_COPY with a better row, heat_hm2's
    near_copy_clusters) collapsed into the kept row's `aliases`, then at most per_reading rows per reading, the first n.
    A display rule only: no count changes. The rule is heat_hm2.list_rows, which the series job also uses to choose
    what it re-measures (every row a list can show is re-measured)."""
    return hm.list_rows(pool, measure, n, jac, per_reading)


def _pool(s: Series, kind: str, h: int, slice_: str) -> pd.DataFrame:
    c = s.cands
    if not len(c):
        return c
    x = c[(c['kind'] == kind) & (c['h'] == int(h))]
    if slice_ == 'unseen':
        x = x[x['seen_in_league'] == 'none']
    return x.drop_duplicates('key')


def _jac(s: Series, kind: str, h: int) -> pd.DataFrame:
    j = s.jac
    if not len(j):
        return j
    return j[(j['kind'] == kind) & (j['h'] == int(h))].drop_duplicates(['key1', 'key2'])


# ------------------------------------------------------------------------------------------------------ the marks
def bhy_from_hist(p, hist, edges=hm.SummaryCounts.P_EDGES) -> np.ndarray:
    """BHY q of p values against the family of every cell, given only its log-binned histogram (SummaryCounts.p: bin b
    holds log10 p in (edges[b-1], edges[b]]). Conservative: a cell's rank counts only the bins below its own (every
    cell of its own bin is taken as larger), and the step-up minimum runs over the upper edges of the bins at or above
    its own. The q is therefore never below the exact BHY q of the same family."""
    p = np.clip(np.nan_to_num(np.asarray(p, float), nan=1.0), 1e-300, 1.0)
    hist = np.asarray(hist, float)
    m = float(hist.sum())
    if m <= 0:
        return np.ones(len(p))
    c = float(np.sum(1.0 / np.arange(1, int(m) + 1))) if m < 1e6 else math.log(m) + 0.5772156649 + 1 / (2 * m)
    cum = np.cumsum(hist)
    up = np.r_[10.0 ** np.asarray(edges, float), 1.0][:len(hist)]                 # each bin's largest p
    with np.errstate(divide='ignore', invalid='ignore'):
        tail = np.where(cum > 0, up * m * c / cum, np.inf)
    suf = np.minimum.accumulate(tail[::-1])[::-1]
    b = np.clip(np.searchsorted(edges, np.log10(p), side='left'), 0, len(hist) - 1)
    below = np.where(b > 0, cum[np.maximum(b - 1, 0)], 0.0)
    own = p * m * c / (below + 1.0)
    return np.minimum(1.0, np.minimum(own, suf[b]))


def add_marks(L: pd.DataFrame, measure: str, phist=None) -> pd.DataFrame:
    """Marks as columns (no filter): hot_A (the measure's |t| on A at the engine's hot bar, t = 3 two-sided, with the
    effective days), p_B (one-sided in the A direction, effective days - 1 df, as the summary counts compute it),
    rep_B (hot_A and p_B <= 0.023), q (BHY from the pooled p histogram of the kind, horizon and measure) and bhy
    (rep_B and q <= 0.10)."""
    from scipy.stats import t as tdist
    if not len(L):
        return L.assign(hot_A=[], p_B=[], rep_B=[], q=[], bhy=[])
    tc, dc = MEASURE_T[measure]
    d = L[dc].to_numpy(float)
    deffA = L['deff_A'].fillna(L['days_A']).to_numpy(float)
    tA = np.nan_to_num(L[f'{tc}_A'].to_numpy(float))
    hot = (np.abs(tA) >= heat.tcrit(deffA, heat.HOT_P / 2)) & (d != 0)
    df = np.maximum(np.floor(np.nan_to_num(L['deff_B'].to_numpy(float))) - 1, 1)
    tB = L[f'{tc}_B'].to_numpy(float) * d
    p = np.where((d != 0) & np.isfinite(tB), tdist.sf(np.nan_to_num(tB), df), 1.0)
    q = bhy_from_hist(p, phist) if phist is not None else np.full(len(L), np.nan)
    rep = hot & (p <= heat.REP_P)
    return L.assign(hot_A=hot, p_B=p, rep_B=rep, q=q, bhy=rep & (np.nan_to_num(q, nan=1.0) <= BHY_Q))


# ------------------------------------------------------------------------------------------------ the chance scale
class Pool:
    """SummaryCounts of several series added up by stratum name (the coins' family sets may differ)."""

    def __init__(self, summs: list):
        summs = [s for s in summs if s is not None]
        self.n = len(summs)
        self.strata = []
        for s in summs:
            for x in s.strata:
                if x not in self.strata:
                    self.strata.append(x)
        nH, K = len(hm.H_SCAN), len(hm.SummaryCounts.COUNTS)
        self.c = np.zeros((nH, len(self.strata), K), np.int64)
        self.persist = np.zeros((nH, len(self.strata), 3, len(hm.T_BINS) + 1, 2), np.int64)
        self.heat = np.zeros((nH, 7, len(MEASURES), len(hm.SummaryCounts.HEAT_EDGES) + 1), np.int64)
        self.p = np.zeros((nH, 7, 3, len(hm.SummaryCounts.P_EDGES) + 1), np.int64)
        self.top = {}
        for s in summs:
            idx = [self.strata.index(x) for x in s.strata]
            self.c[:, idx] += s.c
            self.persist[:, idx] += s.persist
            self.heat += s.heat
            self.p += s.p
            for k, v in s.top.items():
                self.top[k] = np.r_[self.top.get(k, np.zeros(0)), v]
        for k in self.top:
            self.top[k] = -np.sort(-self.top[k])[:hm.SummaryCounts.TOPN]

    def g(self, h: int, stratum: str = 'all') -> dict:
        if stratum not in self.strata:
            return {k: 0 for k in hm.SummaryCounts.COUNTS}
        return dict(zip(hm.SummaryCounts.COUNTS, self.c[hm.H_SCAN.index(h), self.strata.index(stratum)].tolist()))

    def quantile(self, h: int, measure: str, q: float, stratum: str = 'all') -> float:
        """heat_hm2.SummaryCounts.quantile over the pooled histogram and top values."""
        hi = hm.H_SCAN.index(h)
        si = ['all', 'ptmax<2', 'ptmax2-3', 'ptmax>=3', 'prov:none', 'prov:stored', 'prov:pack'].index(stratum)
        hist = self.heat[hi, si, MEASURES.index(measure)]
        n = int(hist.sum())
        if n == 0:
            return float('nan')
        k = int(math.ceil((1 - q) * n))
        top = self.top.get((hi, measure, stratum))
        if top is not None and 0 < k <= len(top):
            return float(top[k - 1])
        cum = np.cumsum(hist[::-1])
        b = len(hist) - 1 - int(np.searchsorted(cum, k))
        e = hm.SummaryCounts.HEAT_EDGES
        return float(e[min(b, len(e) - 1)])

    def max(self, h: int, measure: str, stratum: str = 'all') -> float:
        top = self.top.get((hm.H_SCAN.index(h), measure, stratum))
        return float(top[0]) if top is not None and len(top) else float('nan')

    def phist(self, h: int, measure: str) -> np.ndarray:
        return self.p[hm.H_SCAN.index(h), 0, P_KIND[measure]]


def _share(a, b):
    return round(a / b, 4) if b else None


def chance_metrics(P: Pool, h: int) -> dict:
    """One set's chance numbers at one horizon (the coins of the set pooled)."""
    g = P.g(h)
    o = {'cells': g['cells'], 'under_floor': g['under_floor'], 'kept_direction': _share(g['dir_kept'], g['dir_n']),
         'kept_lift': _share(g['lift_kept'], g['lift_n']), 'kept_iota': _share(g['iota_kept'], g['iota_n']),
         'kept_iota_add': _share(g['iota_add_kept'], g['iota_add_n']), 'kept_iota_robust': _share(g['robust_kept'], g['robust_n']),
         't_iota_B2': _share(g['t_iota_B2'], g['iota_n']), 't_robust_B2': _share(g['t_robust_B2'], g['robust_n']),
         'robust_with_call': _share(g['robust_with_call'], g['robust_n'])}
    for me in MEASURES:
        o[f'p99_{me}'], o[f'max_{me}'] = _f(P.quantile(h, me, 0.99), 3), _f(P.max(h, me), 3)
        o[f'max_{me}_unseen'] = _f(P.max(h, me, 'prov:none'), 3)
    hi = hm.H_SCAN.index(h)
    pc = {}
    for st in ('all', 'ptmax<2', 'ptmax2-3', 'ptmax>=3'):
        if st in P.strata:
            x = P.persist[hi, P.strata.index(st), 2]                      # iota_robust: (t bin, [n, kept])
            pc[st] = [_share(int(k), int(n)) for n, k in x]
    o['persistence_robust'] = pc
    o['kept_robust_by_provenance'] = {st[5:]: _share(P.g(h, st)['robust_kept'], P.g(h, st)['robust_n']) for st in ('prov:none', 'prov:stored', 'prov:pack')}
    return o


def _median_range(vals: list):
    v = [x for x in vals if x is not None and not (isinstance(x, float) and not math.isfinite(x))]
    if not v:
        return None, None
    med = float(np.median(v))
    return (int(med) if float(med).is_integer() and all(isinstance(x, (int, np.integer)) for x in v) else round(med, 4)), [min(v), max(v)]


def twin_scale(per_set: list) -> dict:
    """{metric: {'median', 'range'}} over the twin sets' metric dicts (nested dicts per key)."""
    out = {}
    if not per_set:
        return out
    for k in per_set[0]:
        vals = [x.get(k) for x in per_set]
        if isinstance(vals[0], dict):
            out[k] = twin_scale(vals)
        elif isinstance(vals[0], list):
            out[k] = [twin_scale([{'v': v[i] if i < len(v) else None} for v in vals]).get('v') for i in range(len(vals[0]))]
        else:
            med, rg = _median_range(vals)
            out[k] = {'median': med, 'range': rg}
    return out


# ---------------------------------------------------------------------------------------------------- the time words
def _h12(h: int, m: int = 0) -> str:
    h %= 24
    return f'{h % 12 or 12}:{m:02d} {"AM" if h < 12 else "PM"}'


def level_words(name: str, level: str) -> str:
    """One condition in plain words, with clock and position levels in Eastern and UTC."""
    lv = str(level)
    if name == 'UTC1h' and lv.isdigit():
        H = int(lv)
        return (f'the hour {H:02d}:00-{(H + 1) % 24:02d}:00 UTC ({_h12(H - 5)}-{_h12(H - 4)} EST, {_h12(H - 4)}-{_h12(H - 3)} EDT)')
    if name == 'UTC4h' and re.match(r'^\d\d-\d\d$', lv):
        a, b = (int(x) for x in lv.split('-'))
        return f'the 4-hour block {a:02d}:00-{b % 24:02d}:00 UTC ({_h12(a - 5)}-{_h12(b - 5)} EST, {_h12(a - 4)}-{_h12(b - 4)} EDT)'
    if name == 'NY30m' and re.match(r'^\d\d:\d\d$', lv):
        H, M = (int(x) for x in lv.split(':'))
        e = H * 60 + M + 30
        return (f'the half hour {_h12(H, M)}-{_h12(e // 60, e % 60)} ET ({(H + 5) % 24:02d}:{M:02d} UTC in winter, '
                f'{(H + 4) % 24:02d}:{M:02d} UTC in summer)')
    if name == 'Weekday':
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        full = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        if lv in days:
            i = days.index(lv)
            return f'{full[i]} UTC (from {full[i - 1]} 7:00 PM EST / 8:00 PM EDT)'
    if name == 'POS:QPos' and re.match(r'^m\d\d$', lv):
        q = int(lv[1:])
        tail = ' (the last minute before :00, :15, :30 or :45, ET and UTC alike)' if q == 14 else ' (ET and UTC alike)'
        return f'the entry minute is minute {q} of the Kalshi quarter hour{tail}'
    if name == 'POS:QPhase':
        return f'the entry minute is in minutes {lv[1:]} of the quarter hour (ET and UTC alike)'
    if name == 'POS:HourQ':
        return f'the entry minute is in minutes {lv[1:]} of the hour (ET and UTC alike)'
    if name in ('MACRO:R830', 'MACRO:FOMC'):
        ev = ('an 8:30 AM ET CPI, jobs or PPI release (13:30 UTC in winter, 12:30 UTC in summer)' if name == 'MACRO:R830' else
              'a 2:00 PM ET FOMC statement (19:00 UTC in winter, 18:00 UTC in summer)')
        w = {'30-1 before': '30 to 1 minutes before', '0-14 after': '0-14 minutes after', '15-59 after': '15-59 minutes after',
             '60-239 after': '1-4 hours after'}.get(lv)
        return f'{w} {ev}' if w else f'no release window ({name})'
    if name == 'MACRO:ReleaseDay':
        return 'an ET day with an 8:30 AM release or an FOMC statement' if lv == 'release day' else 'an ET day without a release'
    if name == 'PERP:FundClock':
        return f'{lv} to the next funding (usually 00:00, 08:00, 16:00 UTC = 7:00 PM, 3:00 AM, 11:00 AM EST)'
    m = re.match(r'^X\.([A-Z]+):(R1z|R5z|R15z|Gap5|Gap15|RSI14|TakerBuy)$', name)
    if m:
        O, r = m.groups()
        what = {'R1z': f"{O}'s last minute", 'R5z': f"{O}'s last 5 minutes", 'R15z': f"{O}'s last 15 minutes",
                'Gap5': f'the gap to {O} over 5 minutes', 'Gap15': f'the gap to {O} over 15 minutes', 'RSI14': f"{O}'s 1m RSI14",
                'TakerBuy': f"{O}'s 1m taker buying"}[r]
        return f'{what} {lv}'
    m = re.match(r'^X:Breadth(\d+)$', name)
    if m:
        return f"the other coins' breadth over {m.group(1)} minutes {lv}"
    m = re.match(r'^GBM\.(TA|ALL)(\d+)$', name)
    if m:
        return f"the {m.group(1)} model's {m.group(2)}-minute call {lv}"
    m = re.match(r'^(\d+)m:(.*)$', name)
    if m:
        return f'{m.group(1)}m {m.group(2).removesuffix(" sign")} {lv}'
    return f'{name} {lv}'


def cond_words(conds) -> str:
    parts = [' or '.join(level_words(r, x) for x in lvs) if len(lvs) > 1 else level_words(r, lvs[0]) for r, lvs in _conds(conds)]
    if len(parts) <= 1:
        return ''.join(parts)
    return parts[0] + ' while ' + ' and '.join(parts[1:])


def in_words(row, twin_best=None) -> str:
    """One sentence for a listed row, e.g. "15m RSI14 very high while BTC's last 5 minutes very low: down, 57% right on
    2025, 6 windows a day (twins' best: 53%, 4 windows)." twin_best: the twins' best row of the same list."""
    g = row.get if isinstance(row, dict) else (lambda k, d=None: getattr(row, k, d))
    d = g('dir')
    s = cond_words(g('conds'))
    sh, wd = g('share_B'), g('wd_B')
    txt = f"{s}: {'up' if (d or 0) > 0 else 'down'}, {sh:.0f}% right on 2025, {wd:.1f} windows a day" if sh is not None and wd is not None \
        and math.isfinite(float(sh)) and math.isfinite(float(wd)) else f"{s}: {'up' if (d or 0) > 0 else 'down'}"
    ir = g('iota_robust_B')
    if g('measure') == 'iheat' and ir is not None and math.isfinite(float(ir)):
        txt += f', {float(ir) * (g("d_iota") or 1):+.1f} odds points beyond what the parts give'
        if g('iota_with_call') is False or g('iota_with_call') == 0:
            txt += ' (the pair holds the call back: a stand-aside lesson)'
    if twin_best is not None:
        tg = twin_best.get if isinstance(twin_best, dict) else (lambda k, dd=None: getattr(twin_best, k, dd))
        if tg('share_B') is not None and math.isfinite(float(tg('share_B'))):
            txt += f" (twins' best: {float(tg('share_B')):.0f}%, {float(tg('wd_B')):.1f} windows)"
    elif twin_best is None:
        txt += " (no twin in this league)"
    return txt + '.'


# ------------------------------------------------------------------------------------------------ the model call
def model_rows(s: Series, rmv: pd.DataFrame) -> list:
    """The GBM zone rows of one series: per model, horizon and non-neutral zone, the call (heat_hm2_learn.call_stats on
    the scan's entries: direction from the zone's own A odds, B numbers in that direction) and the re-measured held
    numbers (every minute the zone holds) and onsets (the zone's events), signed in the call's direction."""
    calls = {}
    for k, u in s.usage.items():
        if isinstance(u, dict) and isinstance(u.get('call'), dict):
            calls[u['call']['name']] = u['call']
    for nm, g in (s.gbm.get('readings') or {}).items():
        if isinstance(g, dict) and isinstance(g.get('call'), dict):
            calls.setdefault(nm, g['call'])
    out = []
    for nm, c in sorted(calls.items()):
        m = re.match(r'^GBM\.(TA|ALL)(\d+)$', nm)
        if not m:
            continue
        model, H = m.group(1), int(m.group(2))
        if H not in hm.H_SCAN:
            continue
        for li, lv in enumerate(c.get('levels') or []):
            if lv in heat.NEUTRAL:
                continue
            d = int((c.get('dir_A') or [0] * (li + 1))[li] or 0)
            row = {'coin': s.label, 'asset': s.asset, 'twin': s.twin, 'kind': 'model', 'model': model, 'h': H, 'key': f'{nm}={lv}', 'level': lv,
                   'conds': json.dumps([[nm, [lv]]]), 'dir': d, 'hit_A': c.get('hit_A'), 'hit_B': c.get('hit_B'), 'n_call_B': c.get('n_call_B'),
                   'n_A': (c.get('n_A') or [None] * (li + 1))[li], 'n_B': (c.get('n_B') or [None] * (li + 1))[li],
                   'odds_A': (c.get('odds_A_dir') or [None] * (li + 1))[li], 'odds_B': (c.get('odds_B_dir') or [None] * (li + 1))[li],
                   't_A': (c.get('t_A_dir') or [None] * (li + 1))[li], 't_B': (c.get('t_B_dir') or [None] * (li + 1))[li]}
            for form, kd, key, pre in (('state', 'xstate', f'{nm}={lv}', 'held_'), ('onset', 'single', f'{nm}={lv}', 'onset_')):
                ix = (kd, key, H, form)
                if len(rmv) and ix in rmv.index and d != 0:
                    sr = signed_rm(rmv.loc[[ix]].reset_index(drop=True), np.array([d]), [_base_B(s.meta, H)]).iloc[0].to_dict()
                    row.update({pre + k: v for k, v in sr.items()})
            if 'held_wd_B' in row and row.get('odds_B') is not None:
                row['oheat_B'] = row['held_wd_B'] * float(row['odds_B'])
            sides = {}
            for side in ('falling in', 'recovering', 'rising in', 'cooling'):
                ix = ('single', f'{nm}={lv} ({side})', H, 'onset')
                if len(rmv) and ix in rmv.index and d != 0:
                    sides[side] = signed_rm(rmv.loc[[ix]].reset_index(drop=True), np.array([d]), [_base_B(s.meta, H)]).iloc[0].to_dict()
            if sides:
                row['onset_sides'] = sides
            out.append(row)
    return out


def baseline_rows(s: Series, rmv: pd.DataFrame) -> list:
    """The last-candle baseline, faded (bet against the decision minute's candle: what bid-ask bounce alone gives, which
    a coin-flip twin cannot rule out), per horizon: each side and the two sides together (n-weighted)."""
    out = []
    if not len(rmv):
        return out
    for H in hm.H_SCAN:
        sides = []
        for lv, d in (('candle up', -1), ('candle down', 1)):
            ix = ('baseline', f'BASE:LastCandle={lv}', H, 'state')
            if ix in rmv.index:
                r = signed_rm(rmv.loc[[ix]].reset_index(drop=True), np.array([d]), [_base_B(s.meta, H)]).iloc[0].to_dict()
                sides.append(dict(r, level=lv, dir=d))
        if not sides:
            continue
        nB = np.array([x['n_B'] or 0 for x in sides], float)
        w = nB / nB.sum() if nB.sum() else np.full(len(sides), 1 / len(sides))
        both = {k: float(np.nansum([x[k] * wi for x, wi in zip(sides, w)])) for k in ('odds_B', 'share_B', 'share_over_B', 'move_B', 'retL_B')}
        both['wd_B'] = float(np.nansum([x['wd_B'] for x in sides]))
        out.append({'coin': s.label, 'asset': s.asset, 'twin': s.twin, 'h': H, 'sides': sides, 'faded': both})
    return out


def best_single(direction: pd.DataFrame, coin: str, h: int, target_wd: float = None) -> dict:
    """The league's best single level at a horizon (HM1's direction_all: every event level with a sample, B numbers in
    the A direction) by heat on B, and at matched windows per day: the best odds_B among the levels firing at least
    half and at most twice as often as target_wd."""
    if direction is None or not len(direction):
        return None
    x = direction[(direction['coin'].astype(str) == coin) & (direction['h'] == int(h))]
    if not len(x):
        return None
    pick = lambda r: {'key': r['key'], 'dir': _i(r['dir']), 'odds_B': _f(r['odds_B']), 'share_B': _f(r.get('share_B')), 'wd_B': _f(r['wd_B']),
                      'oheat_B': _f(r['oheat_B'])}
    out = {'by_heat': pick(x.loc[x['oheat_B'].idxmax()])}
    if target_wd is not None and math.isfinite(target_wd) and target_wd > 0:
        y = x[(x['wd_B'] >= 0.5 * target_wd) & (x['wd_B'] <= 2 * target_wd)]
        out['matched'] = pick(y.loc[y['odds_B'].idxmax()]) if len(y) else None
        out['target_wd'] = _f(target_wd, 3)
    return out


# --------------------------------------------------------------------------------------------------- usage cards
def _fn_of(name: str):
    from oracle import heat_hm2_learn as hl
    return hl.ta_function(name)


def usage_cards(series: list, direction: pd.DataFrame = None, pools: dict = None, hm1_summary: dict = None) -> dict:
    """One card per TA-Lib function (OR-HM2, Lessons; review: how to read it):
      grid      per setting x timeframe square (cards.json.gz grid of every coin): the A-chosen strongest horizon (the mode
                over the coins of best_h_A), each zone's B odds in its A direction there (median over the coins), the
                extreme zones' fade or follow (count of coins), beside the twins' median and range of the same numbers;
      call      its own call by level in HM1's direction league (direction_all: median B odds and share over base, the
                hottest level), beside HM1's twin scale for that horizon;
      model     the ALL and TA models' mean |contribution| of the function on 2025 minutes and the mean contribution by
                level (usage.json), beside the twins' median and range;
      partners  the best partner in each data family by iheat_B (cards.json.gz partners; the coin, reading, level, direction
                and iota_with_call: False = the partner flips or holds back the call, a stand-aside lesson), beside the
                twins' best iheat_B for the same function and family (median and range);
      kept      the kept-interaction share (iota_robust; iota beside it) of its pair cells at 15/60/240 (the scan's
                per-reading tally, cards.json.gz kept), the coins pooled, against each twin set's (median and range); a
                series without that tally falls back to its family's pairs (the fam: strata of the summary counts)."""
    reals = [s for s in series if s.real]
    twins = [s for s in series if not s.real]
    fns = set()
    for s in reals:
        fns |= set(((s.cards or {}).get('grid') or {}).keys())
        for u in s.usage.values():
            fns |= set((u.get('by_function') or {}).keys())
    cards = {}
    for fn in sorted(fns):
        card = {'function': fn, 'grid': [], 'call': [], 'model': {}, 'partners': [], 'kept': {}}
        # ---- the settings x timeframe grid
        sq = {}
        for grp, ss in (('real', reals), ('twin', twins)):
            for s in ss:
                for r in ((s.cards or {}).get('grid') or {}).get(fn, []):
                    if r.get('alias_of'):
                        continue
                    k = (r.get('setting', ''), r.get('tf', ''), bool(r.get('sign_reading')))
                    sq.setdefault(k, {'real': [], 'twin': []})[grp].append((s, r))
        for (setting, tf, sign), v in sorted(sq.items(), key=lambda kv: (kv[0][2], kv[0][0], int(re.sub(r'\D', '', kv[0][1]) or 0))):
            if not v['real']:
                continue
            hs = [r.get('best_h_A') for _, r in v['real'] if r.get('best_h_A')]
            bh = int(pd.Series(hs).mode().min()) if hs else 15
            hi = hm.H_SCAN.index(bh)
            levels = v['real'][0][1]['levels']

            def zone_odds(rows):
                out = {}
                for _, r in rows:
                    for li, lv in enumerate(r['levels']):
                        ob = r.get('odds_B_dir') or []
                        if li < len(ob) and hi < len(ob[li]) and ob[li][hi] is not None:
                            out.setdefault(lv, []).append(float(ob[li][hi]))
                return out
            zr, zt = zone_odds(v['real']), zone_odds(v['twin'])
            ff = {}
            for _, r in v['real']:
                for lv, arr in (r.get('fade_follow') or {}).items():
                    x = arr[hi] if hi < len(arr) else None
                    if x:
                        ff.setdefault(lv, {}).setdefault(x, 0)
                        ff[lv][x] += 1
            card['grid'].append({'setting': setting, 'tf': tf, 'sign_reading': sign, 'kind': v['real'][0][1].get('kind'),
                                 'readings': sorted({r['reading'] for _, r in v['real']}),
                                 'best_h': bh, 'best_h_by_coin': {s.label: r.get('best_h_A') for s, r in v['real']},
                                 'best_h_B_by_coin': {s.label: r.get('best_h_B') for s, r in v['real']},
                                 'odds_B': {lv: _f(np.median(zr[lv]), 3) if lv in zr else None for lv in levels},
                                 'twin_odds_B': {lv: dict(zip(('median', 'range'), _median_range(zt.get(lv, [])))) for lv in levels},
                                 'fade_follow': ff, 'coins': len(v['real']), 'twins': len(v['twin'])})
        # ---- its own call by level (HM1's direction league)
        if direction is not None and len(direction):
            x = direction[direction['fn'] == fn]
            for (lvl, h), y in x.groupby(['level', 'h'], sort=True):
                if int(h) not in (15, 60):
                    continue
                tw = ((hm1_summary or {}).get('direction') or {}).get(str(int(h)), {}).get('twin') or {}
                top = y.loc[y['oheat_B'].idxmax()]
                card['call'].append({'level': lvl, 'h': int(h), 'rows': int(len(y)), 'median_odds_B': _f(y['odds_B'].median(), 3),
                                     'kept_direction_B': _f((y['odds_B'] > 0).mean(), 3), 'median_share_over_B': _f(y['share_over_B'].median(), 3),
                                     'best': {'coin': top['coin'], 'key': top['key'], 'odds_B': _f(top['odds_B'], 3), 'wd_B': _f(top['wd_B'], 3)},
                                     'twin_median_odds_B': tw.get('median_odds_B'), 'twin_kept_direction_B': tw.get('kept_direction_on_B')})
        # ---- the model's view (2025 minutes)
        for grp, ss in (('real', reals), ('twin', twins)):
            for s in ss:
                for key, u in s.usage.items():
                    bf = (u.get('by_function') or {}).get(fn)
                    if not bf:
                        continue
                    mm = card['model'].setdefault(key, {'real': {}, 'twin': [], 'by_level': {}})
                    if grp == 'real':
                        mm['real'][s.label] = _f(bf.get('mean_abs'), 4)
                        for rd, lvd in (u.get('by_level') or {}).items():
                            if _fn_of(rd) != fn and _fn_of(rd.removeprefix('ZS:')) != fn:
                                continue
                            for lv, st in lvd.items():
                                mm['by_level'].setdefault(lv, []).append(float(st.get('mean', 0.0)))
                    else:
                        mm['twin'].append(float(bf.get('mean_abs') or 0.0))
        for key, mm in card['model'].items():
            mm['real_median'] = _f(np.median(list(mm['real'].values())), 4) if mm['real'] else None
            med, rg = _median_range(mm.pop('twin'))
            mm['twin_median'], mm['twin_range'] = med, rg
            mm['by_level'] = {lv: _f(np.mean(v), 4) for lv, v in sorted(mm['by_level'].items())}
        # ---- the best partner per data family
        best, tw = {}, {}
        for grp, ss in (('real', reals), ('twin', twins)):
            for s in ss:
                parts = (s.cards or {}).get('partners')
                if parts is None:
                    parts = partners_from_cands(s)
                for p in parts:
                    if p.get('func') != fn or p.get('iheat_B') is None:
                        continue
                    k = (p['group'], int(p['h']))
                    if grp == 'real':
                        if k not in best or p['iheat_B'] > best[k]['iheat_B']:
                            best[k] = dict(p, coin=s.label)
                    else:
                        cur = tw.setdefault(k, {})
                        cur[s.label] = max(cur.get(s.label, -np.inf), float(p['iheat_B']))
        for (grp_, h), p in sorted(best.items(), key=lambda kv: (kv[0][1], -kv[1]['iheat_B'])):
            med, rg = _median_range(list(tw.get((grp_, h), {}).values()))
            card['partners'].append({'group': grp_, 'h': h, 'coin': p['coin'], 'reading': p.get('reading'), 'level': p.get('level'),
                                     'partner': p.get('partner'), 'partner_level': p.get('partner_level'), 'dir': p.get('dir'),
                                     'iota_with_call': p.get('iota_with_call'), 'stand_aside': p.get('iota_with_call') is False,
                                     'iheat_B': _f(p['iheat_B'], 3), 'iota_robust_B': _f(p.get('iota_robust_B'), 3), 'odds_B': _f(p.get('odds_B'), 3),
                                     'wd_B': _f(p.get('wd_B'), 3), 'key': p.get('key'), 'seen_in_league': p.get('seen_in_league'),
                                     'twin_best_iheat_B': {'median': med, 'range': rg}})
        # ---- the kept-interaction share of its pairs: per function from the scan's per-reading tally (cards.json.gz kept,
        # heat_hm2_learn.card_kept), the coins pooled, beside each twin set's share; else its family's pairs (fam: strata)
        real_k = _kept_tot([s for s in reals], fn)
        if real_k is not None:
            cols, tot = real_k
            for h in hm.PACK_H:
                hi = hm.H_SCAN.index(h)
                g = dict(zip(cols, tot[hi]))
                tv, tvi = [], []
                for t in sorted({s.twin for s in twins}):
                    x = _kept_tot([s for s in twins if s.twin == t], fn)
                    if x is not None:
                        gt = dict(zip(x[0], x[1][hi]))
                        if gt.get('robust_n'):
                            tv.append(gt['robust_kept'] / gt['robust_n'])
                        if gt.get('iota_n'):
                            tvi.append(gt['iota_kept'] / gt['iota_n'])
                med, rg = _median_range(tv)
                medi, rgi = _median_range(tvi)
                card['kept'][str(h)] = {'level': 'function', 'cells': int(g.get('cells', 0)), 'robust_n': int(g.get('robust_n', 0)),
                                        'kept': _share(g.get('robust_kept', 0), g.get('robust_n', 0)), 'twin_median': med, 'twin_range': rg,
                                        'kept_iota': _share(g.get('iota_kept', 0), g.get('iota_n', 0)), 'twin_iota_median': medi, 'twin_iota_range': rgi,
                                        'with_call': _share(g.get('robust_with_call', 0), g.get('robust_n', 0))}
        fams = sorted({s.rfam.get(r['reading']) for s in reals for r in ((s.cards or {}).get('grid') or {}).get(fn, []) if s.rfam.get(r['reading'])})
        if real_k is None and pools and fams:
            for h in hm.PACK_H:
                real = pools.get(('real', 'pair'))
                if real is None:
                    continue
                rk = rn = 0
                for st in real.strata:
                    if st.startswith('fam:') and any(f in st[4:].split('|') for f in fams):
                        g = real.g(h, st)
                        rk, rn = rk + g['robust_kept'], rn + g['robust_n']
                tv = []
                for P in pools.get(('twins', 'pair'), []):
                    k_ = n_ = 0
                    for st in P.strata:
                        if st.startswith('fam:') and any(f in st[4:].split('|') for f in fams):
                            g = P.g(h, st)
                            k_, n_ = k_ + g['robust_kept'], n_ + g['robust_n']
                    if n_:
                        tv.append(k_ / n_)
                med, rg = _median_range(tv)
                card['kept'][str(h)] = {'level': 'family', 'families': fams, 'cells': int(rn), 'kept': _share(rk, rn), 'twin_median': med,
                                        'twin_range': rg}
        cards[fn] = card
    return cards


def _kept_tot(series: list, fn: str):
    """(columns, int [horizons, columns]) of a TA function's pair-cell tally summed over series (cards.json.gz kept
    by_function counts), or None when no series has it."""
    cols, tot = None, None
    for s in series:
        k = (s.cards or {}).get('kept') or {}
        e = (k.get('by_function') or {}).get(fn)
        if not e or e.get('counts') is None:
            continue
        c = np.asarray(e['counts'], np.int64)
        if cols is None:
            cols, tot = list(k.get('columns') or []), c.copy()
        elif list(k.get('columns') or []) == cols and c.shape == tot.shape:
            tot = tot + c
    return None if cols is None else (cols, tot)


def partners_from_cands(s: Series) -> list:
    """heat_hm2_learn.card_partners from the candidate pool and the meta's reading list (a series without cards.json.gz):
    per (function, partner group, horizon) the pair cell with the largest iheat_B."""
    from oracle import heat_hm2_learn as hl
    c = s.cands
    if not len(c):
        return []
    c = c[c['kind'] == 'pair'].drop_duplicates(['key', 'h'])
    rd = s.meta.get('readings') or []
    best = {}
    for r in c.itertuples(index=False):
        v = float(r.iheat_B)
        if not math.isfinite(v) or r.ia >= len(rd) or r.ib >= len(rd):
            continue
        for me, la, ot, lo in ((int(r.ia), int(r.la), int(r.ib), int(r.lb)), (int(r.ib), int(r.lb), int(r.ia), int(r.la))):
            R, P = rd[me], rd[ot]
            fns = sorted({f for f in map(hl.ta_function, [R['name']] + list(R.get('aliases', []))) if f})
            grp = 'TA' if hl.ta_function(P['name']) else hl.CARD_GROUP.get(P.get('family'), P.get('family'))
            for fn in fns:
                k = (fn, grp, int(r.h))
                if k not in best or v > best[k]['iheat_B']:
                    best[k] = {'func': fn, 'group': grp, 'h': int(r.h), 'reading': R['name'], 'level': R['levels'][la], 'partner': P['name'],
                               'partner_level': P['levels'][lo], 'partner_family': P.get('family'), 'dir': int(r.dir),
                               'iota_with_call': bool(r.iota_with_call), 'iheat_B': v, 'iota_robust_B': float(r.iota_robust_B),
                               'odds_B': float(r.odds_B), 'wd_B': float(r.wd_B), 'n_B': int(r.n_B), 'key': r.key, 'seen_in_league': r.seen_in_league}
    return [best[k] for k in sorted(best)]


def _direction_with_fn(direction: pd.DataFrame) -> pd.DataFrame:
    """HM1's direction_all with each key's TA function and level (an event label)."""
    if direction is None or not len(direction):
        return direction
    d = direction[~direction['coin'].astype(str).str.contains('twin')].copy()
    nm = d['key'].astype(str).str.rsplit('=', n=1)
    d['reading'] = nm.str[0]
    d['level'] = nm.str[1]
    fmap = {r: _fn_of(r) for r in d['reading'].unique()}
    d['fn'] = d['reading'].map(fmap)
    return d[d['fn'].notna()]


# ---------------------------------------------------------------------------------------------------- the league
def league(inputs: str, hm1_dir: str = '', out: str = '.', stamp: str = '', packs_dir: str = '', main_metas: str = '', gates: str = '',
           patterns: str = '', pack_out: str = '', live_meta_out: str = '', feeds=DEFAULT_FEEDS, log=print) -> dict:
    """The HM2 league from every series' small files (build plan section 5). Writes into out: league.md, usage.md,
    summary.json (oracle-heat-hm2-league-1), lists.csv.gz (every list row, real and twin, all six horizons),
    usage_cards.json, model.csv.gz, and the pack hm2_pack.json with hm2_live_meta.json (pack_out / live_meta_out, default
    in out). Returns the summary."""
    t0 = time.time()
    os.makedirs(out, exist_ok=True)
    found = find_series(inputs)
    if not found:
        raise SystemExit(f'{inputs}: no HM2 series outputs (meta.json of schema oracle-heat-hm2-1)')
    series = [load_series(g, log) for _, g in sorted(found.items())]
    reals = sorted([s for s in series if s.real], key=lambda s: s.label)
    twins = sorted([s for s in series if not s.real], key=lambda s: (s.asset, s.twin))
    warnings = []
    coins = [s.label for s in reals]
    if sorted(coins) != COINS:
        warnings.append(f'expected the coins {", ".join(COINS)}; this league has {", ".join(coins) or "none"}: it is partial')
    for s in reals:
        have = sorted(t.twin for t in twins if t.asset == s.asset)
        if have != TWIN_SEEDS:
            warnings.append(f'{s.label}: twin sets {have or "none"} of {TWIN_SEEDS}: its chance scale has fewer sets')
    for s in series:
        warnings += [f'{s.label}: {n}' for n in s.notes]
    hp = hm1_inputs(hm1_dir, packs_dir, main_metas)
    prov = check_provenance(series, hp, log)
    direction = _read_csv(hp['direction_all'])
    hm1_summary = _read_json(hp['summary'])
    rmv = {s.label: remeasure_view(s.heat) for s in series}
    # ------------------------------------------------------------------------------------------ the chance scale
    pools = {}
    for kind in KINDS:
        pools[('real', kind)] = Pool([s.summ.get(kind) for s in reals])
        sets = sorted({s.twin for s in twins})
        pools[('twins', kind)] = [Pool([s.summ.get(kind) for s in twins if s.twin == t]) for t in sets]
        pools[('twin_sets', kind)] = sets
        for t in sets:
            miss = sorted({s.asset for s in reals} - {s.asset for s in twins if s.twin == t})
            if miss:
                warnings.append(f'twin set {t} lacks {", ".join(miss)}')
    # ------------------------------------------------------------------------------------------------ the lists
    log('lists ...')
    rows, best_twin, tmax = [], {}, {}
    for s in series:
        for kind in KINDS:
            for h in hm.H_SCAN:
                jac = _jac(s, kind, h)
                for sl in SLICES:
                    pool = _pool(s, kind, h, sl)
                    for me in MEASURES:
                        L = make_list(pool, me, TOP[me], jac)
                        if not len(L):
                            continue
                        L = L.assign(coin=s.label, asset=s.asset, twin=s.twin, measure=me, slice=sl, list=f'{sl}:{me}')
                        rows.append(L)
    lists = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['coin', 'asset', 'twin', 'kind', 'h', 'measure', 'slice', 'key'])
    if len(lists):
        parts_ = []
        for lab, x in lists.groupby('coin', sort=False):
            s = next(q for q in series if q.label == lab)
            parts_.append(attach_remeasure(x, rmv[lab], s.meta))
        lists = pd.concat(parts_, ignore_index=True)
        mk = []
        for (kind, h, me), x in lists.groupby(['kind', 'h', 'measure'], sort=False):
            ph = None
            if pools[('real', kind)].n:
                ph = pools[('real', kind)].phist(int(h), me)
            mk.append(add_marks(x, me, ph))
        lists = pd.concat(mk, ignore_index=True)
        # the coin's three twins: their max over every cell of the same kind, horizon, measure and slice (summary tops)
        for s in reals:
            for kind in KINDS:
                for h in hm.H_SCAN:
                    for me in MEASURES:
                        for sl, st in (('all', 'all'), ('unseen', 'prov:none')):
                            vals = [Pool([t.summ.get(kind)]).max(h, me, st) for t in twins if t.asset == s.asset and t.summ.get(kind)]
                            vals = [v for v in vals if math.isfinite(v)]
                            tmax[(s.label, kind, h, me, sl)] = max(vals) if vals else np.nan
        key4 = list(zip(lists['coin'], lists['kind'], lists['h'].astype(int), lists['measure'], lists['slice']))
        lists['twin_max'] = [tmax.get(k, np.nan) for k in key4]
        v = np.array([r[f'{m}_B'] for r, m in zip(lists[[f'{m}_B' for m in MEASURES]].to_dict('records'), lists['measure'])], float)
        lists['value'] = v
        lists['above_twin_max'] = np.where(np.isfinite(lists['twin_max']), v > lists['twin_max'].to_numpy(float), False)
        for s in twins:
            x = lists[lists['coin'] == s.label]
            for (kind, h, me, sl), y in x.groupby(['kind', 'h', 'measure', 'slice']):
                b = y.iloc[0]
                k = (s.asset, kind, int(h), me, sl)
                if k not in best_twin or b['value'] > best_twin[k]['value']:
                    best_twin[k] = b.to_dict()
    # rows above the coin's twins' max, over the coin's whole candidate pool (top CAND_POOL per list)
    above = {}
    for s in reals:
        c = s.cands
        if not len(c):
            continue
        for (kind, h, me), x in c.groupby(['kind', 'h', 'measure']):
            for sl in SLICES:
                y = x if sl == 'all' else x[x['seen_in_league'] == 'none']
                t = tmax.get((s.label, kind, int(h), me, sl), np.nan)
                n = int((y['value'].to_numpy(float) > t).sum()) if math.isfinite(t) else None
                kk = (kind, int(h), me, sl)
                if n is not None:
                    above.setdefault(kk, {'rows': 0, 'capped': False})
                    above[kk]['rows'] += n
                    above[kk]['capped'] |= n >= hm.CAND_POOL
    chance = {}
    for kind in KINDS:
        for h in hm.H_SCAN:
            r = chance_metrics(pools[('real', kind)], h) if pools[('real', kind)].n else {}
            tw = [chance_metrics(P, h) for P in pools[('twins', kind)] if P.n]
            r['above_twin_max'] = {f'{sl}:{me}': above.get((kind, h, me, sl)) for me in MEASURES for sl in SLICES}
            chance.setdefault(kind, {})[str(h)] = {'real': r, 'twin': twin_scale(tw), 'twin_sets': len(tw)}
    # --------------------------------------------------------------------------------------------- family table
    fam_rows = []
    real_p = pools[('real', 'pair')]
    for h in hm.PACK_H:
        for st in real_p.strata:
            if not st.startswith('fam:'):
                continue
            g = real_p.g(h, st)
            if not g['cells']:
                continue
            tv = []
            for P in pools[('twins', 'pair')]:
                gt = P.g(h, st)
                if gt['robust_n']:
                    tv.append(gt['robust_kept'] / gt['robust_n'])
            med, rg = _median_range(tv)
            ks = _share(g['robust_kept'], g['robust_n'])
            fam_rows.append({'families': st[4:], 'h': h, 'cells': g['cells'], 'kept_iota_robust': ks, 'twin_median': med, 'twin_range': rg,
                             'minus_twins': _f(ks - med, 4) if ks is not None and med is not None else None})
    fam = pd.DataFrame(fam_rows)
    # ------------------------------------------------------------------------------------------------ the model
    mrows, brows = [], []
    for s in series:
        mrows += model_rows(s, rmv[s.label])
        brows += baseline_rows(s, rmv[s.label])
    model = pd.DataFrame(mrows)
    model_sum = model_summary(model, brows, direction, reals)
    # ------------------------------------------------------------------------------------------------ the lessons
    dfn = _direction_with_fn(direction)
    cards = usage_cards(series, dfn, pools, hm1_summary)
    # ------------------------------------------------------------------------------------------------ the files
    if len(lists):
        lc = lists.copy()
        for c in ('aliases', 'copies', 'near'):
            lc[c] = [json.dumps(list(x)) for x in lc[c]]
        lc.to_csv(os.path.join(out, 'lists.csv.gz'), index=False, compression='gzip', float_format='%.6g')
    if len(model):
        mc = model.copy()
        if 'onset_sides' in mc:
            mc['onset_sides'] = [json.dumps(hm._clean(x)) if isinstance(x, dict) else '' for x in mc['onset_sides']]
        mc.to_csv(os.path.join(out, 'model.csv.gz'), index=False, compression='gzip', float_format='%.6g')
    _dump({'schema': SCHEMA_CARDS, 'cards': cards}, os.path.join(out, 'usage_cards.json'), indent=None)
    metas = {s.label: s.meta for s in series}
    pack = build_pack(lists, {'chance': chance, 'model': model_sum, 'warnings': warnings, 'stamp': stamp}, metas, model, feeds=feeds)
    gd = (_read_json(gates) if isinstance(gates, str) else gates) if gates else None
    if gd is not None:
        pack = merge_gate_rows(pack, gd)
    lm = live_meta(pack, metas, {C: _read_json(p) for C, p in hp['metas'].items() if p}, {s.label: s.gbm for s in reals})
    if isinstance(gd, dict) and gd.get('live') and gates_merged(pack):
        lm['part3'] = gd['live']        # Part 3's live block (own parameters of the gate rows) returns with its rows
    pack_out = pack_out or os.path.join(out, 'hm2_pack.json')
    live_meta_out = live_meta_out or os.path.join(out, 'hm2_live_meta.json')
    pack['live_meta_sha256'] = None
    lsha = _dump(lm, live_meta_out, indent=None)
    pack['live_meta_sha256'] = lsha
    _dump(pack, pack_out)
    summary = {'schema': SCHEMA_SUMMARY, 'stamp': stamp, 'coins': coins, 'twins': [s.label for s in twins],
               'twin_sets': {str(t): sorted(s.asset for s in twins if s.twin == t) for t in sorted({s.twin for s in twins})},
               'warnings': warnings, 'provenance_check': prov, 'chance': chance, 'family': hm._clean(fam.to_dict('records')),
               'model': model_sum, 'lists': _list_counts(lists), 'top': _top_rows(lists, best_twin), 'pack': pack_summary(pack),
               'cards': {fn: {'squares': len(c['grid']), 'partners': len(c['partners'])} for fn, c in cards.items()},
               'metas': {s.label: {k: s.meta.get(k) for k in ('asset', 'twin', 'minutes', 'from', 'entries', 'table_sha256', 'seconds_total',
                                                              'peak_rss_mb', 'price_step', 'missing')} | {'readings': len(s.meta.get('readings', [])),
                                                                                                          'complete': s.complete}
                         for s in series},
               'inputs': {'hm1_packs': [os.path.basename(p) for p in hp['packs']], 'direction_all': bool(hp['direction_all']),
                          'gates': bool(gates), 'patterns': bool(patterns)},
               'seconds': round(time.time() - t0, 1)}
    _dump(summary, os.path.join(out, 'summary.json'))
    with open(os.path.join(out, 'league.md'), 'w') as f:
        f.write(league_md(summary, lists, fam, model, cards, pack, best_twin, patterns=patterns))
    with open(os.path.join(out, 'usage.md'), 'w') as f:
        f.write(usage_md(cards, summary))
    log(f'league: {len(reals)} coins, {len(twins)} twins, {len(lists):,} list rows, {len(pack["rows"]):,} pack rows ({summary["seconds"]}s)')
    return summary


def _list_counts(lists: pd.DataFrame) -> dict:
    if not len(lists):
        return {}
    g = lists.groupby(['coin', 'kind', 'slice', 'measure']).size()
    out = {}
    for (c, k, sl, me), n in g.items():
        out.setdefault(c, {}).setdefault(k, {})[f'{sl}:{me}'] = int(n)
    return out


TOP_COLS = ['key', 'dir', 'rank', 'value', 'share_B', 'wd_B', 'odds_B', 'iota_robust_B', 'lift_min_B', 'seen_in_league', 'part_tmax', 'rep_B', 'q',
            'above_twin_max', 'aliases', 'onset_wd_B', 'onset_odds_B', 'onset_move_B', 'retL_B', 'move_steps_B']


def _top_rows(lists: pd.DataFrame, best_twin: dict, n: int = MD_TOP) -> dict:
    """summary.json: the real lists at the pack horizons, top n rows each, with the twins' best row of the same list."""
    out = {}
    if not len(lists):
        return out
    x = lists[(lists['twin'] == 0) & lists['h'].isin(hm.PACK_H)]
    for (c, kind, h, sl, me), y in x.groupby(['coin', 'kind', 'h', 'slice', 'measure'], sort=True):
        asset = y['asset'].iloc[0]
        tb = best_twin.get((asset, kind, int(h), me, sl))
        rec = [{k: (r.get(k) if not isinstance(r.get(k), float) else _f(r.get(k))) for k in TOP_COLS if k in r} | {'words': in_words(r, tb)}
               for r in y.sort_values('rank').head(n).to_dict('records')]
        out.setdefault(c, {}).setdefault(kind, {}).setdefault(str(int(h)), {})[f'{sl}:{me}'] = {
            'rows': rec, 'twin_best': None if tb is None else {k: _f(tb.get(k)) if isinstance(tb.get(k), float) else tb.get(k)
                                                             for k in ('coin', 'key', 'value', 'share_B', 'wd_B')}}
    return out


def model_summary(model: pd.DataFrame, brows: list, direction: pd.DataFrame, reals: list) -> dict:
    """Per coin, model and horizon: the GBM zones against the twins' (median and range of the twin series of the coin),
    the baselines (last candle faded; the best single level, also at matched windows per day) and ALL against TA."""
    out = {'zones': [], 'baselines': [], 'all_vs_ta': []}
    if not len(model):
        out['note'] = 'no GBM rows (the learner did not run in these series)'
    for (asset, mdl, h), x in (model.groupby(['asset', 'model', 'h']) if len(model) else []):
        r = x[x['twin'] == 0]
        t = x[x['twin'] != 0]
        for lv, y in r.groupby('level', sort=False):
            ty = t[t['level'] == lv]
            row = y.iloc[0].to_dict()
            med, rg = _median_range([float(v) for v in ty['odds_B'] if v is not None and math.isfinite(float(v))])
            hm_, hr = _median_range([float(v) for v in ty.drop_duplicates('coin')['hit_B'] if v is not None and math.isfinite(float(v))])
            out['zones'].append({'coin': row['coin'], 'model': mdl, 'h': int(h), 'level': lv, 'dir': row['dir'], 'n_B': _i(row.get('n_B')),
                                 'odds_B': _f(row.get('odds_B'), 3), 't_B': _f(row.get('t_B'), 3), 'held_wd_B': _f(row.get('held_wd_B'), 3),
                                 'held_share_B': _f(row.get('held_share_B'), 3), 'onset_wd_B': _f(row.get('onset_wd_B'), 3),
                                 'onset_odds_B': _f(row.get('onset_odds_B'), 3), 'oheat_B': _f(row.get('oheat_B'), 3),
                                 'hit_B': _f(row.get('hit_B'), 4), 'twin_odds_B': {'median': med, 'range': rg},
                                 'twin_hit_B': {'median': hm_, 'range': hr}})
    for s in reals:
        for b in [b for b in brows if b['coin'] == s.label and b['h'] in hm.PACK_H]:
            tb = [x['faded']['odds_B'] for x in brows if x['asset'] == s.asset and x['twin'] != 0 and x['h'] == b['h']]
            med, rg = _median_range(tb)
            wd = None
            if len(model):
                z = model[(model['coin'] == s.label) & (model['model'] == 'ALL') & (model['h'] == b['h']) & model['level'].isin(EXTREME)]
                if len(z) and 'held_wd_B' in z:
                    wd = float(np.nanmedian(z['held_wd_B'].to_numpy(float))) if np.isfinite(z['held_wd_B'].to_numpy(float)).any() else None
            out['baselines'].append({'coin': s.label, 'h': b['h'], 'last_candle_faded': hm._clean(b['faded']),
                                     'last_candle_twins': {'median': med, 'range': rg},
                                     'best_single': best_single(direction, s.label, b['h'], wd)})
        if len(model):
            for h in sorted(set(model['h'])):
                a = model[(model['coin'] == s.label) & (model['h'] == h)]
                hit = {m: a[a['model'] == m]['hit_B'].dropna().astype(float) for m in ('ALL', 'TA')}
                ext = {m: a[(a['model'] == m) & a['level'].isin(EXTREME)]['odds_B'].dropna().astype(float) for m in ('ALL', 'TA')}
                if len(hit['ALL']) and len(hit['TA']):
                    out['all_vs_ta'].append({'coin': s.label, 'h': int(h), 'hit_B_ALL': _f(hit['ALL'].iloc[0]), 'hit_B_TA': _f(hit['TA'].iloc[0]),
                                             'hit_B_ALL_minus_TA': _f(hit['ALL'].iloc[0] - hit['TA'].iloc[0]),
                                             'extreme_odds_B_ALL': _f(ext['ALL'].mean(), 3) if len(ext['ALL']) else None,
                                             'extreme_odds_B_TA': _f(ext['TA'].mean(), 3) if len(ext['TA']) else None})
    return hm._clean(out)


# ------------------------------------------------------------------------------------------------------- the pack
PACK_NUM = ['share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B', 't_A', 't_B', 'oheat_B', 'wd_B', 'hold_B', 'hold_over_B', 'lift_min_A',
            'lift_min_B', 't_lift_A', 't_lift_B', 'rest_wd_B', 'lheat_B', 'iota_A', 'iota_B', 'iota_add_A', 'iota_add_B', 'iota_robust_A',
            'iota_robust_B', 't_iota_A', 't_iota_B', 't_robust_A', 't_robust_B', 'iota_naive_B', 'odds_fit_B', 'iheat_B', 'move_steps_B',
            'retL_B', 'part_tmax', 'assoc']
RM_PACK = ['n_A', 'n_B', 'days_B', 'wd_B', 'share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B', 't_A', 't_B', 'oheat_B', 'move_B', 'best_B',
           'dip_B', 'hold_B', 'hold_over_B', 'retL_B', 'touch25_B', 'move_steps_B', 'tick_B']


# (review fix) a row fires at onset, so its headline numbers (pair_pack.json's fields) are the onset block's (every minute
# of 2025 the fire rule gave, signed in dir); the scan's held-state numbers at the entries, which rank the lists, stay
# in `scan`, and the held block in `held`
HEAD_ONSET = ['n_A', 'n_B', 'days_B', 'wd_B', 'share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B', 't_A', 't_B', 'oheat_B', 'hold_B',
              'hold_over_B']


def _sign_row(r: dict) -> dict:
    """A list row's scan numbers in the pack's units: odds, t and lift signed in the cell's A direction (dir); iota
    kept raw (positive = more up than the parts give; d_iota is its A sign)."""
    d = float(r.get('dir') or 0)
    o = {}
    for k in ('odds_A', 'odds_B', 't_A', 't_B', 'lift_min_A', 'lift_min_B', 't_lift_A', 't_lift_B'):
        v = r.get(k)
        o[k] = None if v is None or not math.isfinite(float(v)) else float(v) * d
    return o


def build_pack(lists: pd.DataFrame, summary: dict, metas: dict, model: pd.DataFrame = None, feeds=DEFAULT_FEEDS) -> dict:
    """hm2_pack.json (schema oracle-heat-hm2-pack-1). Rows: per real coin and pack horizon (15, 60, 240) the union of
    its lists (pairs and triples; oheat / iheat / lheat; the unseen lists too), one row per cell with the lists it is
    in, and the GBM zone rows of both models (kind 'model'). fire = 'onset': the first minute close at which every
    condition holds (each reading at the last closed bar of its own timeframe), entry at the next minute's open; the
    scan's numbers (held state at the entries) rank the row and stay in `scan`; the headline numbers (HEAD_ONSET) are
    the onset block's, what that fire gave (A and B, signed in dir); the held block is every minute the state held.
    onset_dir_A is the onset's own A direction and onset_agrees_A whether it is dir (a column, not a filter: a row
    whose onset opposes its held-state call keeps its row and says so). live_ready False until the parity step.
    Research-only readings (meta.json readings flagged 'research_only': the OR-XD readings of a --outside series) are never in the
    pack: a pair or triple row with one of them in its conds, and a GBM zone row of a model whose trees use one, are left out
    (counted in the pack's `research_only` block, which exists only when a series carries such readings); a near-copy alias
    string of a kept row that names one is dropped from the row's `aliases` (live_meta reads those names)."""
    rows = []
    ro = {k: v for k, v in ((k, hm.research_only_names(mt)) for k, mt in metas.items()) if v}
    left = {'rows': 0, 'models': []}

    def _uses_ro(label, mdl, h):
        used = ((((metas.get(label) or {}).get('learner') or {}).get('trees') or {}).get(f'{mdl}_h{h}') or {}).get('used') or []
        return any(u.removeprefix('ZS:') in ro.get(label, ()) for u in used)

    x = lists[(lists['twin'] == 0) & lists['h'].isin(hm.PACK_H)] if len(lists) else lists
    sha = {k: v.get('table_sha256') for k, v in metas.items() if not int(v.get('twin', 0))}
    twin_max = {}                                   # the coin's twins' max of each measure over all cells (slice all)
    if len(x) and 'twin_max' in x:
        for (coin, kind, h, me), z in x[x['slice'] == 'all'].groupby(['coin', 'kind', 'h', 'measure']):
            twin_max[(coin, kind, int(h), me)] = float(z['twin_max'].iloc[0])
    for (coin, h, kind, key), y in (x.groupby(['coin', 'h', 'kind', 'key'], sort=True) if len(x) else []):
        y = y.sort_values(['measure', 'slice'])
        r = y.iloc[0].to_dict()
        conds = _conds(r['conds'])
        if ro.get(coin) and any(n in ro[coin] for n, _ in conds):
            left['rows'] += 1
            continue
        held = {k: _f(r.get('held_' + k)) for k in RM_PACK}
        onset = {k: _f(r.get('onset_' + k)) for k in RM_PACK}
        sg = _sign_row(r)
        aliases = sorted({a for al in y['aliases'] for a in al})
        if ro.get(coin):                            # a near-copy cond string that names a research-only reading would carry it into the live meta
            aliases = [a for a in aliases if not any(n.rsplit('=', 1)[0].removeprefix('ZS:') in ro[coin] for n in a.split(' & '))]
        row = {'coin': coin, 'h': int(h), 'kind': kind, 'key': key, 'aliases': aliases, 'conds': conds,
               'readings': list(dict.fromkeys(n for n, _ in conds)), 'fire': 'onset', 'dir': int(r['dir']), 'call': 'up' if r['dir'] > 0 else 'down',
               'lists': sorted(set(y['list'])), 'ranks': {l_: int(k_) for l_, k_ in zip(y['list'], y['rank'])},
               'source': r.get('source'), 'n_A': _i(r.get('n_A')), 'n_B': _i(r.get('n_B')), 'days_B': _i(r.get('days_B')),
               **{k: _f(sg.get(k, r.get(k))) for k in PACK_NUM}, 'd_iota': _i(r.get('d_iota')), 'iota_with_call': bool(r.get('iota_with_call')),
               'parts': [{'reading': n, 'levels': lv, 'odds_A': _f(r.get(f'odds_{ab}_A')), 't_A': _f(r.get(f't_{ab}_A'))}
                         for (n, lv), ab in zip(conds, ('a', 'b'))] if kind == 'pair' else [{'reading': n, 'levels': lv} for n, lv in conds],
               'parts_hot': _i(r.get('parts_hot')), 'seen_in_league': r.get('seen_in_league'), 'families': str(r.get('families') or '').split('|'),
               'learner_path': bool(r.get('learner_path')), 'onset': onset, 'held': held, 'remeasured': bool(r.get('remeasured')),
               'move_B': onset['move_B'], 'best_B': onset['best_B'], 'dip_B': onset['dip_B'],
               'marks': {l_: {'hot_A': bool(a), 'replicated_B': bool(b), 'q': _f(q_), 'bhy': bool(c_)}
                         for l_, a, b, q_, c_ in zip(y['list'], y['hot_A'], y['rep_B'], y['q'], y['bhy'])},
               'hot_A': bool(y['hot_A'].any()), 'replicated_B': bool(y['rep_B'].any()), 'bhy': bool(y['bhy'].any()),
               'above_twin_max': None, 'iota_above_twin_max': None, 'lift_above_twin_max': None,
               'live_ready': False, 'live_ready_why': ['parity not run'], 'table_sha256': sha.get(coin)}
        for me, fld in (('oheat', 'above_twin_max'), ('iheat', 'iota_above_twin_max'), ('lheat', 'lift_above_twin_max')):
            tm = twin_max.get((coin, kind, int(h), me), np.nan)
            v = r.get(f'{me}_B')
            row[fld] = None if not math.isfinite(float(tm)) or v is None else bool(float(v) > float(tm))
        row['scan'] = {k: row.get(k) for k in HEAD_ONSET}
        for k in HEAD_ONSET:
            v = onset.get(k)
            row[k] = int(v) if v is not None and k in ('n_A', 'n_B', 'days_B') else v
        oa = onset.get('odds_A')
        row['onset_dir_A'] = None if oa is None else int(np.sign(oa) * int(r['dir']))
        row['onset_agrees_A'] = None if oa is None else bool(oa > 0)
        rows.append(row)
    if model is not None and len(model):
        mm = model[(model['twin'] == 0) & model['h'].isin(hm.PACK_H)]
        zt = {}
        for _, z in model[model['twin'] != 0].iterrows():
            v = z.get('oheat_B')
            if v is not None and math.isfinite(float(v)):
                k = (z['asset'], z['model'], int(z['h']))
                zt[k] = max(zt.get(k, -np.inf), float(v))
        for _, z in mm.iterrows():
            if ro and _uses_ro(z['coin'], z['model'], int(z['h'])):
                left['models'].append(f'{z["coin"]}:{z["model"]}:{int(z["h"])}')
                continue
            onset = {k: _f(z.get('onset_' + k)) for k in RM_PACK}
            held = {k: _f(z.get('held_' + k)) for k in RM_PACK}
            tmx = zt.get((z['asset'], z['model'], int(z['h'])))
            ohB = z.get('oheat_B')
            rows.append({'coin': z['coin'], 'h': int(z['h']), 'kind': 'model', 'key': z['key'], 'aliases': [], 'conds': _conds(z['conds']),
                         'readings': [z['key'].rsplit('=', 1)[0]], 'fire': 'onset', 'model': z['model'], 'dir': int(z['dir']),
                         'call': 'up' if z['dir'] > 0 else 'down' if z['dir'] < 0 else 'none', 'lists': ['model'], 'ranks': {},
                         'n_A': _i(z.get('n_A')), 'n_B': _i(z.get('n_B')), 'odds_A': _f(z.get('odds_A')), 'odds_B': _f(z.get('odds_B')),
                         't_A': _f(z.get('t_A')), 't_B': _f(z.get('t_B')), 'hit_A': _f(z.get('hit_A')), 'hit_B': _f(z.get('hit_B')),
                         'wd_B': held['wd_B'], 'oheat_B': _f(ohB), 'onset': onset, 'held': held,
                         'onset_sides': hm._clean(z.get('onset_sides')) if isinstance(z.get('onset_sides'), dict) else None,
                         'move_B': onset['move_B'], 'dip_B': onset['dip_B'], 'retL_B': onset['retL_B'], 'move_steps_B': onset['move_steps_B'],
                         'seen_in_league': 'none', 'families': ['model'], 'learner_path': False,
                         'above_twin_max': None if tmx is None or ohB is None or not math.isfinite(float(ohB)) else bool(float(ohB) > tmx),
                         'live_ready': False, 'live_ready_why': ['parity not run'], 'table_sha256': sha.get(z['coin'])})
    models = {}
    for k, mt in metas.items():
        if int(mt.get('twin', 0)):
            continue
        for nm, tr in ((mt.get('learner') or {}).get('trees') or {}).items():
            mdl, hh = nm.split('_h')
            if ro and _uses_ro(k, mdl, hh):
                continue
            models.setdefault(k, {}).setdefault(mdl, {})[hh] = {'file': tr.get('file'), 'sha256': tr.get('sha256'), 'used': tr.get('used')}
    chance = {}
    for kind, byh in (summary.get('chance') or {}).items():
        for h in hm.PACK_H:
            c = byh.get(str(h))
            if c is None:
                continue
            keep = ('cells', 'kept_direction', 'kept_lift', 'kept_iota_robust', 't_robust_B2', 'p99_oheat', 'max_oheat', 'p99_iheat', 'max_iheat',
                    'p99_lheat', 'max_lheat', 'max_oheat_unseen', 'max_iheat_unseen', 'max_lheat_unseen')
            chance.setdefault(str(h), {})[kind] = {'real': {k: c['real'].get(k) for k in keep}, 'twin': {k: c['twin'].get(k) for k in keep},
                                                   'twin_sets': c.get('twin_sets'), 'above_twin_max': c['real'].get('above_twin_max')}
    pack = hm._clean({
        'schema': SCHEMA_PACK, 'stamp': summary.get('stamp'), 'horizons': list(hm.PACK_H), 'kinds': list(PACK_KINDS),
        'data': 'Binance spot 1-minute bars of BTC, ETH, SOL and XRP and the extra data of OR-HM2, 2020-01-01 to 2025-12-31 UTC. A = 2020-2024 '
                '(the direction and every choice come from A), B = 2025 (every *_B number).',
        'fire': 'onset: a row fires at the first minute close at which every condition in `conds` holds one of its levels (each reading at the '
                'last CLOSED bar of its own timeframe; a position or clock level is that of the entry minute) after a close at which they did not '
                'all hold; the entry is the open of the next minute. A model row fires when the GBM score enters its zone. A pair or triple '
                'row\'s headline numbers (n, share, odds, t, wd, oheat, hold; A and B) are what that fire gave (its onset block); `scan` holds the '
                'scan\'s held-state numbers that ranked it, `held` every minute the state held; onset_agrees_A says whether the onset\'s own A '
                'direction is dir.',
        'rule': 'Per coin, kind and horizon: the 40 best cells by oheat_B, the 40 best by iheat_B and the 20 best by lheat_B, and the same lists '
                'over the cells no HM1 pack or stored pair holds (seen_in_league none); at most 3 rows per reading in a list; exact and near '
                'copies (80% of B entries shared) are one row with aliases. No pass mark filters a row: hot_A, replicated_B, bhy and the '
                'above-twin-max flags are columns. Unknown kinds (Part 3 gate rows: gate, gate2) must be skipped by a loader that does not know them.',
        'units': {'odds_*': 'odds points (50 x the mean-sign shift over the base) in the row direction', 'oheat_B': 'windows per day x odds_B (scan)',
                  'iota_*': 'odds points the joint state gives beyond its parts (raw: positive = up; d_iota = its A sign; iota_robust: the '
                            'two scales agree)', 'iheat_B': 'windows per day x iota_robust_B in its A direction',
                  'lift_min_*': 'odds points over the weaker part, in the row direction', 'lheat_B': 'min(wd_B, rest_wd_B) x lift_min_B',
                  'share_*': '% of entries beyond the entry price by more than 1.5 price steps on the called side', 'wd_B': 'windows per day',
                  'onset': 'g.full on the onset minutes of every 2025 minute (the fire): move, best move and usual dip in bps, hold in minutes, '
                           'retL = the move entered one minute later, move_steps = move / the price step',
                  'held': 'the same on every minute the state holds', 'n_*': 'scan entries (A: every 7th valid minute; B: every valid minute)',
                  'parts': 'each part alone on A (the scan\'s part effects): odds_A and t_A raw (positive = up)',
                  'share_* / hold_*': 'in the row direction (share_over_B / hold_over_B: over the B base of that direction)'},
        'feeds': list(feeds), 'feed_rule': 'perp, funding and open interest need a Binance perpetual feed; macro needs a 2026 calendar; daily '
                                           'markets need their daily closes; Coinbase readings need a Coinbase minute feed',
        'chance': chance, 'baselines': (summary.get('model') or {}).get('baselines'), 'models': models, 'table_sha256': sha,
        'warnings': summary.get('warnings', []), 'live_reader_parity': None, 'rows': rows})
    if ro:
        pack['research_only'] = hm._clean({'readings': sorted(set().union(*ro.values())), 'rows_left_out': left['rows'], 'models_left_out': left['models'],
                                           'why': 'research-only readings (OR-XD, --outside) have no live computation: the bot has neither a perpetual '
                                                  'taker-flow feed nor an open-interest feed, and the Binance Vision terms forbid live use of the data'})
    return pack


def pack_summary(pack: dict) -> dict:
    df = pd.DataFrame([{k: r.get(k) for k in ('coin', 'h', 'kind', 'live_ready', 'seen_in_league')} for r in pack.get('rows', [])])
    if not len(df):
        return {'rows': 0}
    return {**({'research_only_rows_left_out': pack['research_only']['rows_left_out']} if pack.get('research_only') else {}),
            'rows': int(len(df)), 'by_coin_h_kind': {f'{c}|{h}|{k}': int(n) for (c, h, k), n in df.groupby(['coin', 'h', 'kind']).size().items()},
            'unseen': int((df['seen_in_league'] == 'none').sum()), 'live_ready': int(df['live_ready'].fillna(False).astype(bool).sum()),
            'gate_rows': int(df['kind'].isin(GATE_KINDS).sum())}


def _base_name(n: str) -> str:
    return n.removesuffix(' sign')


def live_meta(pack: dict, metas: dict, main_metas: dict = None, gbm: dict = None) -> dict:
    """hm2_live_meta.json: per coin the price step, the zone edges of every reading behind a row (engine readings from
    the main run's meta.json, new readings from this run's series meta, GBM zones from the series' trees: gbm =
    {coin: series_gbm(...)}, else the meta's learner.trees),
    the norm tables (VOL:RVclock, VOL:Busy) and, for cross-coin readings, the other coins' edges and price step
    (heat_xdata.levels_at reads {'edges', 'norms', 'other_metas'})."""
    main_metas = {k: v for k, v in (main_metas or {}).items() if v}
    out = {'schema': SCHEMA_LIVE, 'coins': {}}
    for coin in sorted({r['coin'] for r in pack.get('rows', []) if r.get('kind') in PACK_KINDS}):
        mt = metas.get(coin) or {}
        asset = mt.get('asset', coin)
        mm = main_metas.get(asset) or {}
        names = set()
        for r in pack['rows']:
            if r.get('coin') != coin or r.get('kind') not in PACK_KINDS:
                continue
            for n in r.get('readings', []):
                names.add(n)
            for a in r.get('aliases', []):
                for c in a.split(' & '):
                    names.add(c.rsplit('=', 1)[0])
        rd = {x['name']: x for x in mt.get('readings', [])}
        gz = {}
        gr = ((gbm or {}).get(coin) or series_gbm(mt, {}))['readings']
        for n in sorted(names):
            if n in gr:
                g = gr[n]
                gz[n] = {'edges': g.get('edges'), 'tree': g.get('file'), 'sha256': g.get('sha256'), 'used': list(g.get('used') or []),
                         'levels': list(heat.ZONES), 'score': 'raw (heat_hm2_learn.tree_eval with_init=False)'}
                names |= set(g.get('used') or [])
        names = {x.removeprefix('ZS:') for x in names} - hm.research_only_names(mt)       # (a research-only reading has no live computation, whatever carried it in)
        en, ee = mt.get('edges_new') or {}, mm.get('edges') or {}
        edges, engine, none = {}, {}, []
        for n in sorted(names):
            if n.startswith('GBM.'):
                continue
            al = [n] + list((rd.get(n) or {}).get('aliases', []))
            if n in en:
                edges[n] = en[n]
            elif any(_base_name(a) in ee for a in al):
                b = next(_base_name(a) for a in al if _base_name(a) in ee)
                engine[_base_name(n)] = ee[b]
            elif (rd.get(n) or {}).get('levels') == list(heat.ZONES) and n not in en:
                none.append(n)
        others = {}
        for n in names:
            m = re.match(r'^X\.([A-Z]+):', n)
            if m:
                O = m.group(1)
                _refuse_doge(O)
                om = main_metas.get(O) or {}
                others[O] = {'edges': {f'1m:{r}': en.get(f'X.{O}:{r}', (om.get('edges') or {}).get(f'1m:{r}')) for r in ('RSI14', 'TakerBuy')},
                             'price_step': om.get('price_step')}
        out['coins'][coin] = {'asset': asset, 'price_step': mt.get('price_step') if mt.get('price_step') is not None else mm.get('price_step'),
                              'table_sha256': mt.get('table_sha256'), 'edges': edges, 'engine_edges': engine, 'norms': mt.get('norms') or {},
                              'other_metas': others, 'gbm': gz, 'readings': sorted(names), 'no_edges': sorted(none)}
    return hm._clean(out)


# ------------------------------------------------------------------------------------------- Part 3 and Part 4 hooks
def _rows_sha(rows: list) -> str:
    return hashlib.sha256(json.dumps(hm._clean(rows), sort_keys=True, allow_nan=False).encode()).hexdigest()


def non_gate_sha(pack: dict) -> str:
    """sha256 of the pack's rows other than Part 3's gate rows (sorted-key JSON): merge_gate_rows asserts with it that
    every other row stays byte-identical."""
    return _rows_sha([r for r in pack.get('rows', []) if r.get('kind') not in GATE_KINDS])


LIVE_FIELDS = ('live_ready', 'live_ready_why')


def tier2_sha(pack: dict) -> str:
    """(build note) sha256 of the pack's non-gate rows without the fields parity sets (LIVE_FIELDS): the calls Part 3's
    tier 2 is built from. drill-units records it, the drill league stops if it changed (tier 2 would be stale), and
    merge_gate_rows drops gate rows built on another tier 2. A parity run or a league rerun on the same series files
    changes live_ready only, so it leaves this sha (and the gate rows) alone."""
    return _rows_sha([{k: v for k, v in r.items() if k not in LIVE_FIELDS} for r in pack.get('rows', []) if r.get('kind') not in GATE_KINDS])


def merge_gate_rows(pack: dict, gates, part3: dict = None, log=print) -> dict:
    """Part 3's gate rows (kind 'gate' / 'gate2', their own file gate_rows.json: a list of rows or {'rows': [...],
    'part3': {...}}) into the pack: earlier gate rows are replaced, every other row stays byte-identical (asserted by
    non_gate_sha), and the pack gets the `part3` block. (review fix) When the part3 block records the tier-2 sha its
    units were built on (hm2_tier2_sha256) and the pack's non-gate rows now give another, the gate rows are stale (their
    `when` calls and numbers belong to another HM2 pack): they are dropped with a warning, the pack keeps no gate rows,
    and its `part3` block says why (pack['part3']['stale']). Returns the pack."""
    g = _read_json(gates) if isinstance(gates, str) else gates
    if g is None:
        return pack
    rows = g.get('rows', []) if isinstance(g, dict) else list(g)
    blk = part3 or (g.get('part3') if isinstance(g, dict) else None)
    bad = [r.get('kind') for r in rows if r.get('kind') not in GATE_KINDS]
    if bad:
        raise SystemExit(f'merge_gate_rows: rows of kind {sorted(set(map(str, bad)))} are not gate rows')
    before = non_gate_sha(pack)
    want, have = (blk or {}).get('hm2_tier2_sha256'), tier2_sha(pack)
    pack = dict(pack)
    if want and want != have:
        log(f'::warning::Part 3 gate rows not merged: they were built on another HM2 pack (tier-2 sha {want[:12]}, this pack {have[:12]}); '
            'rerun the drill (units, drill jobs, drill league) on this pack')
        pack['rows'] = [r for r in pack.get('rows', []) if r.get('kind') not in GATE_KINDS]
        pack['part3'] = {'stale': True, 'gate_rows_dropped': len(rows), 'hm2_tier2_sha256_units': want, 'hm2_tier2_sha256_pack': have,
                         'units_sha256': (blk or {}).get('units_sha256'), 'stamp': (blk or {}).get('stamp')}
        pack['non_gate_sha256'] = before
        return pack
    pack['rows'] = [r for r in pack.get('rows', []) if r.get('kind') not in GATE_KINDS] + [dict(r) for r in rows]
    if non_gate_sha(pack) != before:
        raise SystemExit('merge_gate_rows: a non-gate row changed')
    if blk is not None:
        pack['part3'] = blk
    pack['non_gate_sha256'] = before
    return pack


def gates_merged(pack: dict) -> bool:
    """The pack holds Part 3's gate rows (merge_gate_rows did not drop them as stale)."""
    return not (pack.get('part3') or {}).get('stale') and any(r.get('kind') in GATE_KINDS for r in pack.get('rows', []))


def upsert_section(md_path: str, name: str, text: str) -> None:
    """Puts `text` between the section markers of `name` in league.md (replacing what is there, or appending): how Part
    3 ('part3') and Part 4 ('part4') add their sections after this league has run."""
    with open(md_path) as f:
        md = f.read()
    a, b = SECTION.format(name), SECTION_END.format(name)
    block = f'{a}\n{text.rstrip()}\n{b}'
    if a in md and b in md:
        md = md[:md.index(a)] + block + md[md.index(b) + len(b):]
    else:
        md = md.rstrip('\n') + '\n\n' + block + '\n'
    with open(md_path, 'w') as f:
        f.write(md)


def chart_section(patterns: str) -> str:
    """The "Chart patterns" section (OR-HM2-part4.md, Lists and the league section) from Part 4's league files in
    `patterns` (chart_summary.json, chart_league.md): its headings one level down, or a line saying it has not run."""
    lines = ['## Chart patterns (Part 4)', '']
    md = os.path.join(patterns, 'chart_league.md') if patterns else ''
    sj = _read_json(os.path.join(patterns, 'chart_summary.json')) if patterns else None
    if md and os.path.isfile(md):
        with open(md) as f:
            body = f.read()
        t = re.match(r'\s*# ([^\n]*)\n', body)                     # Part 4's own title becomes the section's heading (once)
        if t:
            lines, body = [f'## {t.group(1).strip()}'], body[t.end():]
        else:
            lines = lines[:1]
        body = re.sub(r'^(#+) ', lambda m: '#' + m.group(1) + ' ', body, flags=re.M)
        if sj:
            lines += ['', f"Schema {sj.get('schema')}; coins {', '.join(map(str, sj.get('coins', [])))}."]
        lines += ['', body.strip()]
    else:
        lines.append('Part 4 (structural chart patterns, python/oracle/heat_patterns.py) has not written its league yet. Its league step fills '
                     'this section (upsert_section(..., "part4", ...)): the chance table, the scale map, the singles and pair lists, the '
                     'parameter curves, the loser tables and the rows in words.')
    return '\n'.join(lines)


def part3_section(pack: dict) -> str:
    rows = [r for r in pack.get('rows', []) if r.get('kind') in GATE_KINDS]
    lines = ['## Part 3: what separates the winners', '']
    if not rows:
        lines.append('Part 3 (python/oracle/heat_hm2_drill.py) has not merged its gate rows yet. Its league writes '
                     'research/oracle_heat/hm2/part3/league.md, puts its gate rows into hm2_pack.json (kind gate / gate2) and fills this '
                     'section (upsert_section(..., "part3", ...)).')
    else:
        df = pd.DataFrame([{k: r.get(k) for k in ('coin', 'h', 'kind', 'mode', 'track', 'live_ready')} for r in rows])
        p3 = pack.get('part3') or {}
        if p3.get('partial'):                       # (Part 3 pre-run audit W1) a league run with --allow-partial says so
            ms = p3.get('missing') or []
            lines += [f'**PARTIAL: the drill league ran on an incomplete set of series ({len(ms)} gaps: '
                      + '; '.join(f"{m.get('label') or 'all series'}: {m.get('what')}" for m in ms[:10]) + (' ...' if len(ms) > 10 else '')
                      + '); see part3.missing in hm2_pack.json.**', '']
        lines += [f'{len(rows):,} gate rows are merged into hm2_pack.json (see research/oracle_heat/hm2/part3/league.md).', '',
                  '| coin | minutes | kind | rows | live ready |', '|---|---|---|---|---|']
        for (c, h, k), y in df.groupby(['coin', 'h', 'kind'], dropna=False):
            lines.append(f'| {c} | {h} | {k} | {len(y)} | {int(y["live_ready"].fillna(False).astype(bool).sum())} |')
    return '\n'.join(lines)


# ------------------------------------------------------------------------------------------------------ markdown
def _fmt(x, p=1, plus=False):
    if x is None:
        return ''
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not math.isfinite(v):
        return ''
    return f'{v:+.{p}f}' if plus else f'{v:.{p}f}'


def _mr(sc, p=3):
    """'median (low to high)' of a twin_scale entry."""
    if not sc or sc.get('median') is None:
        return 'n/a'
    rg = sc.get('range') or []
    if rg and rg[0] != rg[1]:
        return f'{_fmt(sc["median"], p)} ({_fmt(rg[0], p)} to {_fmt(rg[1], p)})'
    return _fmt(sc['median'], p)


def _key(k) -> str:
    return str(k).replace('|', '/')


def league_md(summary: dict, lists: pd.DataFrame, fam: pd.DataFrame, model: pd.DataFrame, cards: dict, pack: dict, best_twin: dict,
              patterns: str = '') -> str:
    md = ['# OR-HM2 league: confluence across all data (coin price, discovery only)', '']
    if summary.get('stamp'):
        md.append(f"Run: {summary['stamp']}.")
    md += [f"Coins: {', '.join(summary['coins']) or 'none'}. No-signal twins: {', '.join(summary['twins']) or 'none'}.",
           'Build on A = 2020-01-01 to 2024-12-31, check on B = 2025 (the data stop at 2026-01-01 00:00 UTC, Dec 31, 2025 7:00 PM EST; no '
           'minute of 2026 is read). The decision is a minute close; the entry is the next minute\'s open. Times are Eastern (ET: EST in winter, '
           'EDT in summer) and UTC. A map on coin price, not a validated rule and not a Kalshi-price result.']
    for w in summary.get('warnings', []):
        md.append(f'**WARNING: {w}.**')
    md += ['', '## How to read this', '',
           'A cell is two readings (a pair) or three (a triple) each at a level at the same minute, for example "15m RSI14 very high while '
           "BTC's last 5 minutes are very low\". Odds: half the shift in P(up) - P(down) over the base rate, in points. Windows per day: distinct "
           'H-minute clock windows that hold the state. oheat = windows per day x odds (how often x how sure). iheat = windows per day x how much '
           'the joint state beats what its two parts give on both the odds scale and the probability scale (iota_robust): confluence that the '
           'parts alone do not show. lheat = how often the second reading changes the call x by how much (lift over the weaker part). The '
           'direction of every row comes from A; every B number is signed in it, so a cell with no information scores about zero. The no-signal '
           'twins are the same pipeline on each coin with every minute\'s direction replaced by a coin flip (one joint flip for all coins): '
           'what chance alone produces. Marks (hot on A, replicated on B, BHY, above the twins\' max) are columns; no mark removes a row.', '']
    # ---------------------------------------------------------------------------------------------- 1. chance
    md += ['## 1. Chance scale: the coins against their no-signal twins', '',
           'Per kind and horizon, the coins pooled against the twin sets (each set = one twin of every coin): the median and, in brackets, the '
           'lowest and highest set. There are millions of correlated cells, so the twins\' maximum is the yardstick, not t. Kept: the share of '
           'cells whose B sign equals the A sign (a coin flip gives a little under one half: a B value of exactly 0 counts as not kept).', '']
    for kind in KINDS:
        ch = summary['chance'].get(kind) or {}
        md += [f'### {kind.capitalize()}s', '',
               '| minutes | set | cells | under floor | kept direction | kept lift | kept iota | kept iota_add | kept iota_robust | t iota_robust B >= 2 '
               '| 99th pct oheat | max oheat | 99th pct iheat | max iheat | max iheat unseen | 99th pct lheat | max lheat |',
               '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for h in hm.H_SCAN:
            c = ch.get(str(h))
            if not c:
                continue
            r, t = c['real'], c['twin']
            if r:
                md.append(f"| {h} | coins | {r.get('cells', 0):,} | {r.get('under_floor', 0):,} | " + ' | '.join(
                    _fmt(r.get(k), 3) for k in ('kept_direction', 'kept_lift', 'kept_iota', 'kept_iota_add', 'kept_iota_robust', 't_robust_B2')) + ' | ' +
                    ' | '.join(_fmt(r.get(k), 2) for k in ('p99_oheat', 'max_oheat', 'p99_iheat', 'max_iheat', 'max_iheat_unseen', 'p99_lheat', 'max_lheat')) + ' |')
            if t:
                md.append(f"| {h} | twins ({c.get('twin_sets')}) | {_mr(t.get('cells'), 0)} | {_mr(t.get('under_floor'), 0)} | {_mr(t.get('kept_direction'))} | "
                          f"{_mr(t.get('kept_lift'))} | {_mr(t.get('kept_iota'))} | {_mr(t.get('kept_iota_add'))} | {_mr(t.get('kept_iota_robust'))} | "
                          f"{_mr(t.get('t_robust_B2'))} | {_mr(t.get('p99_oheat'), 2)} | {_mr(t.get('max_oheat'), 2)} | {_mr(t.get('p99_iheat'), 2)} | "
                          f"{_mr(t.get('max_iheat'), 2)} | {_mr(t.get('max_iheat_unseen'), 2)} | {_mr(t.get('p99_lheat'), 2)} | {_mr(t.get('max_lheat'), 2)} |")
        md += ['', 'Rows above the max of the coin\'s own three twins (over each coin\'s candidate pool, the 1,000 best per list; "1,000+" = the '
               'pool is full):', '', '| minutes | ' + ' | '.join(f'{sl} {me}' for me in MEASURES for sl in SLICES) + ' |',
               '|---|' + '---|' * (len(MEASURES) * len(SLICES))]
        for h in hm.H_SCAN:
            c = (ch.get(str(h)) or {}).get('real', {}).get('above_twin_max') or {}
            cells = []
            for me in MEASURES:
                for sl in SLICES:
                    v = c.get(f'{sl}:{me}')
                    cells.append('' if not v else f"{v['rows']:,}{'+' if v.get('capped') else ''}")
            md.append(f'| {h} | ' + ' | '.join(cells) + ' |')
        md += ['', 'Persistence: the kept share of iota_robust by its A |t| (0-1, 1-2, 2-3, 3-4, 4 and over), for all cells and by how strong '
               'the parts are alone (part_tmax: the larger |t| on A of the two parts; a stratum, never a filter):', '',
               '| minutes | stratum | set | 0-1 | 1-2 | 2-3 | 3-4 | 4+ |', '|---|---|---|---|---|---|---|---|']
        for h in hm.PACK_H:
            c = ch.get(str(h))
            if not c:
                continue
            for st in ('all', 'ptmax<2', 'ptmax2-3', 'ptmax>=3'):
                r = (c['real'].get('persistence_robust') or {}).get(st)
                t = (c['twin'].get('persistence_robust') or {}).get(st)
                if r:
                    md.append(f'| {h} | {st} | coins | ' + ' | '.join(_fmt(x, 3) for x in r) + ' |')
                if t:
                    md.append(f'| {h} | {st} | twins | ' + ' | '.join(_mr(x) for x in t) + ' |')
        md.append('')
    # ------------------------------------------------------------------------------------------- 2. unseen
    md += ['## 2. The unseen slice', '',
           'The same lists over the cells whose readings are not in a pack the bot loads and were not stored together in HM1 '
           '(seen_in_league = none: provenance only; how strong the parts are alone stays a column). Each sentence gives the twins\' best row '
           'of the same list.', '']
    top = summary.get('top') or {}
    for c in summary.get('coins', []):
        for kind in KINDS:
            for h in hm.PACK_H:
                for me in ('iheat', 'oheat'):
                    blk = (((top.get(c) or {}).get(kind) or {}).get(str(h)) or {}).get(f'unseen:{me}')
                    if not blk or not blk['rows']:
                        continue
                    md.append(f'- **{c}, {kind}s, {h} minutes, by {me}:**')
                    for r in blk['rows'][:WORDS_TOP]:
                        md.append(f'  - {r["words"]}')
    md.append('')
    # ----------------------------------------------------------------------------------------- 3. the model call
    ms = summary.get('model') or {}
    md += ['## 3. The model call (GBM)', '',
           'Shallow boosted trees fit on A only (TA: the engine\'s TA-Lib readings; ALL: every reading of this design). Their score at every '
           'minute in five zones at A\'s quantiles; each zone\'s direction is its own A odds. Hit B: the share of 2025 calls that went the called '
           'way among the moves beyond the dead band. Held: every minute the zone holds; onset: the minute it enters the zone.', '']
    if ms.get('note'):
        md.append(ms['note'] + '.')
    if ms.get('zones'):
        md += ['| coin | model | minutes | zone | dir | B entries | odds B | t B | twins\' odds B | held windows/day | held share right B % | '
               'onset windows/day | onset odds B | hit B | twins\' hit B |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for z in ms['zones']:
            if z['h'] not in hm.PACK_H:
                continue
            md.append(f"| {z['coin']} | {z['model']} | {z['h']} | {z['level']} | {'up' if (z['dir'] or 0) > 0 else 'down' if (z['dir'] or 0) < 0 else 'none'} | "
                      f"{z['n_B'] or 0:,} | {_fmt(z['odds_B'], 2, True)} | {_fmt(z['t_B'], 1, True)} | {_mr(z['twin_odds_B'], 2)} | {_fmt(z['held_wd_B'], 2)} | "
                      f"{_fmt(z['held_share_B'], 1)} | {_fmt(z['onset_wd_B'], 2)} | {_fmt(z['onset_odds_B'], 2, True)} | {_fmt(z['hit_B'], 3)} | "
                      f"{_mr(z['twin_hit_B'], 3)} |")
        md.append('')
    if ms.get('baselines'):
        md += ['Baselines. Last candle faded: bet against the decision minute\'s candle (what bid-ask bounce alone gives; a coin-flip twin '
               'cannot rule it out). Best single: HM1\'s best event level by heat at that horizon, and the best by odds among levels firing '
               'half to twice as often as the ALL model\'s extreme zones (matched windows per day).', '',
               '| coin | minutes | last candle faded odds B | windows/day | twins | best single | odds B | windows/day | matched single | odds B | windows/day |',
               '|---|---|---|---|---|---|---|---|---|---|---|']
        for b in ms['baselines']:
            bs = b.get('best_single') or {}
            bh, bm = bs.get('by_heat') or {}, bs.get('matched') or {}
            md.append(f"| {b['coin']} | {b['h']} | {_fmt(b['last_candle_faded'].get('odds_B'), 2, True)} | {_fmt(b['last_candle_faded'].get('wd_B'), 1)} | "
                      f"{_mr(b.get('last_candle_twins'), 2)} | {_key(bh.get('key', ''))} | {_fmt(bh.get('odds_B'), 2, True)} | {_fmt(bh.get('wd_B'), 2)} | "
                      f"{_key(bm.get('key', ''))} | {_fmt(bm.get('odds_B'), 2, True)} | {_fmt(bm.get('wd_B'), 2)} |")
        md.append('')
    if ms.get('all_vs_ta'):
        md += ['ALL against TA (what cross-referencing the other data adds to the call):', '',
               '| coin | minutes | hit B ALL | hit B TA | ALL - TA | extreme zones odds B ALL | TA |', '|---|---|---|---|---|---|---|']
        for a in ms['all_vs_ta']:
            md.append(f"| {a['coin']} | {a['h']} | {_fmt(a['hit_B_ALL'], 3)} | {_fmt(a['hit_B_TA'], 3)} | {_fmt(a['hit_B_ALL_minus_TA'], 3, True)} | "
                      f"{_fmt(a['extreme_odds_B_ALL'], 2, True)} | {_fmt(a['extreme_odds_B_TA'], 2, True)} |")
        md.append('')
    # --------------------------------------------------------------------------------------------- 4. lessons
    md += ['## 4. Lessons: how to use TA-Lib for direction', '', '### Family table', '',
           'Per pair of data families: confluence cells with a sample and the share whose interaction (iota_robust) kept its sign on 2025, '
           'minus the twins\' median share. A positive gap that stands clear of the twins\' range is evidence that the two families together '
           'say more than each alone.', '', '| minutes | families | cells | kept iota_robust | twins | minus twins |', '|---|---|---|---|---|---|']
    if len(fam):
        for r in fam.sort_values(['h', 'cells'], ascending=[True, False]).itertuples():
            md.append(f"| {r.h} | {r.families.replace('|', ' x ')} | {r.cells:,} | {_fmt(r.kept_iota_robust, 3)} | "
                      f"{_mr({'median': r.twin_median, 'range': r.twin_range})} | {_fmt(r.minus_twins, 3, True)} |")
    md += ['', '### TA-Lib usage cards', '',
           f'One card per TA-Lib function ({len(cards)} cards, in usage.md and usage_cards.json): a grid of its settings x timeframes (each '
           'square: the horizon where it is strongest on A, each zone\'s B odds in its A direction there, whether the extreme zones fade or '
           'follow), its own call by level, the model\'s mean contribution, its best partner in each data family (and whether that partner '
           'strengthens the call or flips it: a stand-aside lesson), and its family\'s kept-interaction share; each beside the twins.', '']
    ranked = []
    for fn, c in cards.items():
        best = max((p for p in c['partners'] if p['h'] in hm.PACK_H), key=lambda p: p['iheat_B'] or -np.inf, default=None)
        if best is not None and best['iheat_B'] is not None:
            ranked.append((best['iheat_B'], fn, best))
    if ranked:
        md += ['The functions whose best partner has the most iheat on 2025 (the full cards are in usage.md):', '',
               '| function | minutes | partner family | coin | reading | partner | dir | strengthens the call | iheat B | twins\' best |',
               '|---|---|---|---|---|---|---|---|---|---|']
        for v, fn, p in sorted(ranked, key=lambda x: -x[0])[:25]:
            md.append(f"| {fn} | {p['h']} | {p['group']} | {p['coin']} | {p['reading']}={p['level']} | {p['partner']}={p['partner_level']} | "
                      f"{'up' if (p['dir'] or 0) > 0 else 'down'} | {'yes' if p['iota_with_call'] else 'no: stand aside'} | {_fmt(v, 2)} | "
                      f"{_mr(p['twin_best_iheat_B'], 2)} |")
    md += ['', '### Each coin\'s top rows in words', '']
    for c in summary.get('coins', []):
        for h in hm.PACK_H:
            for kind in KINDS:
                for me in MEASURES:
                    blk = (((top.get(c) or {}).get(kind) or {}).get(str(h)) or {}).get(f'all:{me}')
                    if not blk or not blk['rows']:
                        continue
                    md.append(f'- **{c}, {kind}s, {h} minutes, by {me}:**')
                    for r in blk['rows'][:WORDS_TOP]:
                        md.append(f'  - {r["words"]}')
    md.append('')
    # ---------------------------------------------------------------------------------------------- 5. lists
    md += ['## 5. The lists', '',
           f'The top {MD_TOP} of each list at 15, 60 and 240 minutes; lists.csv.gz holds every list at all six horizons (1, 5, 15, 30, 60, 240), '
           'the twins\' too. Numbers in the row\'s A direction. Onset: the same state measured at the minute it starts to hold, on every minute '
           '(what the bot\'s fire gives); late = that move entered one minute later (the bid-ask bounce check); steps = the move in price steps.', '']
    if len(lists):
        x = lists[(lists['twin'] == 0) & lists['h'].isin(hm.PACK_H)]
        for (c, h, kind, sl, me), y in x.groupby(['coin', 'h', 'kind', 'slice', 'measure'], sort=True):
            y = y.sort_values('rank').head(MD_TOP)
            md += [f'**{c}, {kind}s, {h} minutes, {"unseen, " if sl == "unseen" else ""}by {me}** (twins\' max {_fmt(y["twin_max"].iloc[0], 2)}):', '',
                   '| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | '
                   'onset move bps | late | steps | marks | aliases |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
            for r in y.to_dict('records'):
                marks = ', '.join(nm for nm, on in (('hot', r['hot_A']), ('rep', r['rep_B']), ('BHY', r['bhy']), ('> twins', r['above_twin_max'])) if on) or 'none'
                d = r['dir']
                md.append(f"| {r['rank']} | {_key(r['key'])} | {'up' if d > 0 else 'down'} | {_fmt(r['wd_B'], 2)} | {_fmt(r['share_B'], 1)} | "
                          f"{_fmt(r['odds_B'] * d, 2, True)} | {_fmt(r['iota_robust_B'], 2, True)} | {_fmt(r['lift_min_B'] * d, 2, True)} | {_fmt(r['value'], 1)} | "
                          f"{r['seen_in_league']} | {_fmt(r['part_tmax'], 1)} | {_fmt(r.get('onset_wd_B'), 2)} | {_fmt(r.get('onset_odds_B'), 2, True)} | "
                          f"{_fmt(r.get('onset_move_B'), 1, True)} | {_fmt(r.get('retL_B'), 1, True)} | {_fmt(r.get('move_steps_B'), 1, True)} | {marks} | "
                          f"{len(r['aliases'])} |")
            md.append('')
    # ---------------------------------------------------------------------------------------------- 6. pack
    ps = summary.get('pack') or {}
    md += ['## 6. The pack for the bot', '',
           f"hm2_pack.json (published to research/oracle_heat/latest/): {ps.get('rows', 0):,} rows ({ps.get('unseen', 0):,} from the unseen lists' cells, "
           f"{ps.get('gate_rows', 0):,} Part 3 gate rows), {ps.get('live_ready', 0):,} live ready. A row fires at the first minute close at which "
           'every condition holds; the entry is the next minute\'s open. live_ready needs the live reader\'s parity on Dec 29-31, 2025 (at '
           'least 99.5% of minutes) for every reading of the row and the feed the bot needs for it. The bot loads the pack behind its own '
           'switch, default off (the bot lane\'s work).', '', '| coin | minutes | kind | rows |', '|---|---|---|---|']
    for k, n in sorted((ps.get('by_coin_h_kind') or {}).items()):
        c, h, kd = k.split('|')
        md.append(f'| {c} | {h} | {kd} | {n:,} |')
    md.append('')
    md += [SECTION.format('part3'), part3_section(pack), SECTION_END.format('part3'), '']
    md += [SECTION.format('part4'), chart_section(patterns), SECTION_END.format('part4'), '']
    # ---------------------------------------------------------------------------------------------- tables
    md += ['## Series', '', 'One series per coin and twin; the hash is the sha256 of heat.csv.gz unzipped (the re-measured rows).', '',
           '| series | minutes | readings | A entries | B entries | complete | seconds | peak MB | table sha256 |', '|---|---|---|---|---|---|---|---|---|']
    for k in sorted(summary.get('metas', {})):
        v = summary['metas'][k]
        e = v.get('entries') or {}
        md.append(f"| {k} | {v.get('minutes') or 0:,} | {v.get('readings')} | {e.get('A', 0):,} | {e.get('B', 0):,} | {'yes' if v.get('complete') else 'no'} | "
                  f"{v.get('seconds_total')} | {v.get('peak_rss_mb')} | {v.get('table_sha256')} |")
    return '\n'.join(md) + '\n'


def usage_md(cards: dict, summary: dict) -> str:
    md = ['# OR-HM2 TA-Lib usage cards', '',
          'One card per TA-Lib function, from every coin (2025 numbers in the A direction) beside the no-signal twins (median and range). The '
          'model\'s contributions are its view, not evidence. Coin price, not a Kalshi-price result.', '']
    for fn, c in cards.items():
        md += [f'## {fn}', '']
        if c['grid']:
            md += ['How to read it (each square: the horizon where it is strongest on A; each level\'s B odds in its A direction there, the twins\' '
                   'median in brackets; fade or follow of the extreme zones, coins counted):', '',
                   '| setting | timeframe | kind | best minutes | B odds by level (twins) | extremes |', '|---|---|---|---|---|---|']
            for g in c['grid']:
                od, to = g['odds_B'], g['twin_odds_B']
                lvc = '; '.join(f"{lv} {_fmt(v, 2, True)} ({_fmt((to.get(lv) or {}).get('median'), 2, True) or 'n/a'})" for lv, v in od.items() if v is not None)
                ff = '; '.join(f"{lv} {', '.join(f'{k} {n}' for k, n in v.items())}" for lv, v in g['fade_follow'].items())
                kd = 'sign' if g['sign_reading'] else (g.get('kind') or 'zone')
                md.append(f"| {g['setting'] or '-'} | {g['tf']} | {kd} | {g['best_h']} | {lvc} | {ff} |")
            md.append('')
        if c['call']:
            md += ['Its own call by level (HM1\'s direction league; twins: HM1\'s twin scale at that horizon):', '',
                   '| level | minutes | levels | median odds B | kept direction | twins | best |', '|---|---|---|---|---|---|---|']
            for r in c['call']:
                md.append(f"| {r['level']} | {r['h']} | {r['rows']} | {_fmt(r['median_odds_B'], 2, True)} | {_fmt(r['kept_direction_B'], 3)} | "
                          f"{_fmt(r['twin_median_odds_B'], 2, True) or 'n/a'} / {_fmt(r['twin_kept_direction_B'], 3) or 'n/a'} | {r['best']['coin']} {_key(r['best']['key'])} "
                          f"{_fmt(r['best']['odds_B'], 2, True)} |")
            md.append('')
        if c['model']:
            md += ['The model\'s mean |contribution| on 2025 minutes (odds points) and by level:', '', '| model | coins (median) | twins | by level |', '|---|---|---|---|']
            for k, mm in sorted(c['model'].items()):
                bl = ', '.join(f'{lv} {_fmt(v, 2, True)}' for lv, v in mm['by_level'].items())
                md.append(f"| {k} | {_fmt(mm['real_median'], 3)} | {_mr({'median': mm['twin_median'], 'range': mm['twin_range']})} | {bl} |")
            md.append('')
        if c['partners']:
            md += ['Its best partner in each data family (by iheat on 2025):', '',
                   '| minutes | family | coin | reading | partner | dir | the partner | iheat B | twins\' best |', '|---|---|---|---|---|---|---|---|---|']
            for p in c['partners']:
                md.append(f"| {p['h']} | {p['group']} | {p['coin']} | {p['reading']}={p['level']} | {p['partner']}={p['partner_level']} | "
                          f"{'up' if (p['dir'] or 0) > 0 else 'down'} | {'strengthens the call' if p['iota_with_call'] else 'holds it back: stand aside'} | "
                          f"{_fmt(p['iheat_B'], 2)} | {_mr(p['twin_best_iheat_B'], 2)} |")
            md.append('')
        if c['kept']:
            lvl = next(iter(c['kept'].values())).get('level')
            md += [('Kept interaction (iota_robust kept its sign on 2025) of its pair cells: ' if lvl == 'function' else
                    'Kept interaction of its family\'s pairs: ') + '; '.join(
                f"{h} min {_fmt(k['kept'], 3)} (twins {_mr({'median': k['twin_median'], 'range': k['twin_range']})})" for h, k in c['kept'].items()) + '.', '']
    return '\n'.join(md) + '\n'


# ------------------------------------------------------------------------------------------------------- parity
_PW = {}


def _sample_rows(n: int, days: int, every=(5, 7)) -> np.ndarray:
    lo = max(0, n - days * 1440)
    r = np.arange(lo, n)
    return r[((r + 1) % every[0] == 0) | (r % every[1] == 0)]


def _cut(df: pd.DataFrame, lo: int, end: int) -> pd.DataFrame:
    return df[(df['ts'] >= lo) & (df['ts'] < end)]


def _window(row: int) -> tuple:
    """The live inputs of one minute close: the coin's and the other coins' minute grids over the window days before
    it (heat_live.grid), the perp and Coinbase minutes on that grid, and the extra frames as the bot would hold them."""
    from oracle import heat_live
    from oracle import heat_xdata as xd
    W = _PW
    m = W['m']
    end = int(m['t0']) + (row + 1) * MIN
    lo = end - W['window_days'] * DAY
    win = heat_live.grid(_cut(W['spot'][W['asset']], lo, end), end)
    oth = {o: heat_live.grid(_cut(df, lo, end), end) for o, df in W['spot'].items() if o != W['asset'] and len(_cut(df, lo, end))}
    pg = xd.on_grid(win, _cut(W['perp'], lo, end)) if W.get('perp') is not None else None
    fd = dict(W.get('found') or {})
    if W.get('cb') is not None:
        fd['cb'] = xd.on_grid(win, _cut(W['cb'], lo, end))
    return win, oth, pg, fd


def _parity_new(row: int) -> tuple:
    """heat_xdata.levels_at on the window ending at the row's close."""
    from oracle import heat_xdata as xd
    W = _PW
    win, oth, pg, fd = _window(row)
    got = xd.levels_at(win, W['lm'], W['names'], others=oth, perp=pg, fund=W['fund'], oi=W['oi'], daily=W['dom'], found=fd or None, cal=W['cal'])
    return row, got


ENGINE_CTX = ('BTC.D 1d', 'BTC.D 5d', 'USDT.D 1d', 'USDT.D 5d', 'Dom 1d', 'UTC4h')


def _is_engine(n: str) -> bool:
    """An engine reading (a TA-Lib timeframe reading or a context state of oracle.heat), as the main run builds it."""
    return bool(re.match(r'^\d+m:', n)) or n in ENGINE_CTX


def _tfs(names) -> dict:
    out = {}
    for n in names:
        g = re.match(r'^(\d+)m:', n)
        if g:
            out.setdefault(int(g.group(1)), set()).add(_base_name(n))
    return out


def _engine_readings(m: dict, names, edges: dict, step, dom: str, window=None) -> dict:
    """Engine readings of `names` on the minutes m, the live reader's way (heat_live.tf_codes with the stored edges and
    price step; window None: the whole grid, else the last `window` bars of each timeframe, the codes padded with -1 so
    bar i of the dict is bar i of m) and the context states (heat.context_readings). {name: reading dict}."""
    from oracle import heat_live
    names = set(names)
    out = {}
    for k, bases in sorted(_tfs(names).items()):
        R, _, s = heat_live.tf_codes(m, k, edges=edges, step=step, window=window, want_bases=bases)
        for r in R:
            if r['name'] in names:
                out[r['name']] = dict(r, codes=np.r_[np.full(s, -1, np.int8), np.asarray(r['codes'], np.int8)]) if s else r
    if names & set(ENGINE_CTX):
        for r in heat.context_readings(m, dom or ''):
            if r['name'] in names:
                out[r['name']] = r
    return out


def _dom_frames(dom: str) -> dict:
    """The daily dominance closes heat_live.dominance_levels reads ({'BTC.D', 'USDT.D'}: frames of ts, c)."""
    out = {}
    for sym in ('BTC.D', 'USDT.D'):
        p = os.path.join(dom, f'{sym}_1d.csv') if dom else ''
        if p and os.path.isfile(p):
            out[sym] = pd.read_csv(p)
    return out


def _engine_sub(row: int, kmax: int) -> dict:
    """The minutes the live reader holds at the close of `row`: from a UTC midnight at least WINDOW_BARS + 2 bars of
    the longest timeframe back, to the row's close."""
    from oracle import heat_live
    m = _PW['m']
    a = max(0, (row + 1 - (heat_live.WINDOW_BARS + 2) * kmax) // 1440 * 1440)
    sub = {x: (None if m.get(x) is None else m[x][a:row + 1]) for x in ('o', 'h', 'l', 'c', 'v', 'tb', 'gap')}
    sub['t0'], sub['n'] = int(m['t0']) + a * MIN, row + 1 - a
    return sub


def _parity_engine(row: int) -> tuple:
    """At one close: the pack's engine readings from heat_live.active_keys (states: each at the last closed bar of its
    own timeframe, the stored edges) and the GBM zone of each pack model from windows (_gbm_zone)."""
    from oracle import heat_live
    from oracle import heat_xdata as xd
    W = _PW
    sub = _engine_sub(row, W['kmax'])
    meta = {'edges': W['engine_edges'], 'price_step': W['step']}
    levels = {}
    if W['engine_names']:
        st = heat_live.active_keys(sub, meta, want=set(), dom=W['dom_frames'], tfs=sorted(_tfs(W['engine_names'])) or [15],
                                   states=set(W['engine_names']))['states']
        levels = {n: st.get(n) for n in W['engine_names']}
    gz = {}
    if W['trees']:
        feats = {F['zs_of'] or F['name'] for tj, _ in W['trees'].values() for F in tj['hm2']['features']}
        Re = _engine_readings(sub, {n for n in feats if _is_engine(n)}, W['engine_edges'], W['step'], W['dom'], window=heat_live.WINDOW_BARS)
        win, oth, pg, fd = _window(row)
        XR, _, _, _ = xd.extra_readings(win, 0, others=oth, other_metas=W['lm'].get('other_metas'), perp=pg, fund=W['fund'], oi=W['oi'],
                                        cal=W['cal'], dom_dir=W['dom'], found=fd or None, edges=W['lm'].get('edges', {}),
                                        norms=W['lm'].get('norms', {}), log=_log_none)
        new = {r['name']: r for r in XR}

        def reading_of(n):
            if n in Re:
                return Re[n], sub['n'] - 1
            if n in new:
                return new[n], win['n'] - 1
            return None, None
        for nm, (tj, edges) in W['trees'].items():
            gz[nm] = _gbm_zone(tj, edges, reading_of, gap=bool(W['m']['gap'][row]))
    return row, levels, gz


def _feature_reading(F: dict, reading_of):
    R, r = reading_of(F['zs_of'] or F['name'])
    if R is None:
        for al in F.get('aliases') or []:
            R, r = reading_of(al)
            if R is not None:
                break
    return R, r


def _gbm_zone(tj: dict, edges, reading_of, gap: bool):
    """The GBM zone (level index) at one close: heat_hm2_learn.tree_eval of the used features' level codes (reading_of(name)
    -> (reading dict, the row of the close in its grid)), bucketed with the stored edges on the raw score. None where a
    used feature's reading is missing; -1 (unknown) on a forward-filled minute or when every used reading is unknown."""
    from oracle import heat_hm2_learn as hl
    feats = tj['hm2']['features']
    X = np.full((1, len(feats)), -1, np.int8)
    used = hl.used_features(tj)
    for i in used:
        R, r = _feature_reading(feats[i], reading_of)
        if R is None:
            return None
        X[0, i] = hl.feature_codes({'R': R, 'zs': bool(feats[i]['zs_of'])}, np.array([r]))[0]
    if gap or edges is None or (len(used) and (X[0, used] < 0).all()):
        return -1
    return int(heat.bucket(np.asarray(hl.tree_eval(tj, X), float), edges)[0])


def _gbm_history(tj: dict, edges, reading_of, rows: np.ndarray, gap: np.ndarray):
    """The GBM zones at `rows` from whole-history readings (reading_of(name) -> reading dict or None), as _gbm_zone."""
    from oracle import heat_hm2_learn as hl
    feats = tj['hm2']['features']
    used = hl.used_features(tj)
    X = np.full((len(rows), len(feats)), -1, np.int8)
    for i in used:
        R, _ = _feature_reading(feats[i], lambda n: (reading_of(n), None))
        if R is None:
            return None
        X[:, i] = hl.feature_codes({'R': R, 'zs': bool(feats[i]['zs_of'])}, rows)
    if edges is None:
        return np.full(len(rows), -1, np.int64)
    z = np.asarray(heat.bucket(np.asarray(hl.tree_eval(tj, X), float), edges), np.int64)
    z[gap[rows] | ((X[:, used] < 0).all(1) if len(used) else np.zeros(len(rows), bool))] = -1
    return z


def _stored_gbm(series_dir: str, m: dict) -> dict:
    """The series' own GBM codes (heat_hm2_learn.write_gbm_codes, gbm_codes.npz) when they are of this grid."""
    p = os.path.join(series_dir, 'gbm_codes.npz')
    if not os.path.isfile(p):
        return {}
    z = np.load(p)
    if int(z['t0']) != int(m['t0']) or int(z['n']) != int(m['n']):
        return {}
    return {k: z[k] for k in z.files if k.startswith('GBM.')}


def parity(asset: str, csv: str, series_dir: str, out: str, live_meta_path: str = '', main_meta: str = '', other_csvs: dict = None, perp_csv: str = '',
           fund_csv: str = '', oi_csv: str = '', cal_csv: str = '', dom: str = '', found: dict = None, other_metas: str = '', pack_path: str = '',
           days: int = 3, every=(5, 7), engine_every: int = 15, window_days: int = 14, procs: int = 0, log=print) -> dict:
    """Dec 29-31, 2025 (the last `days` days of the grid), on the coin (never a twin):
      new readings  every sampled close (rows r with (r + 1) % every[0] == 0 or r % every[1] == 0): heat_xdata.levels_at on a
                    window of `window_days` days ending at the close (the live meta's edges and norm tables) against the
                    history's level (heat_xdata.extra_readings on the whole grid, edges from A; also compared with the series
                    meta's edges);
      engine        every engine_every-th sampled close: the pack's engine readings from heat_live.active_keys on the live
                    reader's window (WINDOW_BARS bars, the main meta's edges) against heat_live.tf_codes / heat.context_readings
                    on the whole grid;
      GBM           the same closes: the zone of each pack model from the window's features (tree_eval, the stored edges)
                    against the series' own codes (gbm_codes.npz; else the trees on the history's features).
    Writes <out>/parity.json (schema oracle-heat-hm2-parity-1); live-ready reads it."""
    from oracle import heat_parity
    from oracle import heat_xdata as xd
    _refuse_doge(asset, csv, perp_csv, fund_csv, oi_csv, *((other_csvs or {}).keys()))
    t_start = time.time()
    os.makedirs(out, exist_ok=True)
    smeta = _read_json(os.path.join(series_dir, 'meta.json')) or {}
    if smeta and int(smeta.get('twin', 0)):
        raise SystemExit('parity runs on a coin, never on a twin')
    m = heat.load_minutes(csv)
    a_hi = heat_parity.split_rows(m, 'A')[1]
    li = xd.load_inputs(asset, m, 0, other_csvs or {}, perp_csv or None, fund_csv or None, oi_csv or None, cal_csv or None, dict(found or {}), log=log)
    kw = li['kwargs']
    om = hm._other_metas(other_metas, kw['others'], 0, m) if other_metas else {O: None for O in kw['others']}
    R0, e0, n0, miss = xd.extra_readings(m, a_hi, kw['others'], om, kw['perp'], kw['fund'], kw['oi'], kw['cal'], dom or None, kw['found'], kw['real'],
                                         _log_none, asset=asset)
    lmall = _read_json(live_meta_path) or {}
    lm = ((lmall.get('coins') or {}).get(asset)) if lmall else None
    if lm is None:                                                  # no live meta: the series meta's tables, else the history's
        lm = {'norms': smeta.get('norms') or n0,
              'other_metas': {O: {'edges': {f'1m:{r}': e0.get(f'X.{O}:{r}') for r in ('RSI14', 'TakerBuy')},
                                  'price_step': (om.get(O) or {}).get('price_step')} for O in kw['others']}}
    lm = {**lm, 'edges': {**e0, **(smeta.get('edges_new') or {}), **(lm.get('edges') or {})}}
    sme = smeta.get('edges_new') or {}
    same = sorted(k for k in sme if k in e0 and np.allclose(sme[k], e0[k], rtol=1e-9, atol=0))
    diff = sorted(k for k in set(sme) | set(e0) if k not in same)
    rows = _sample_rows(m['n'], days, every)
    spot = {asset: pd.read_csv(csv)}
    for O, p in (other_csvs or {}).items():
        spot[O] = pd.read_csv(p)
    names = sorted(r['name'] for r in R0)
    found_frames = {k: v for k, v in (kw.get('found') or {}).items() if k != 'cb'}
    _PW.clear()
    _PW.update(m=m, asset=asset, spot=spot, window_days=window_days, lm=lm, names=names, fund=kw['fund'], oi=kw['oi'], cal=kw['cal'], dom=dom or None,
               perp=xd.load_extra(perp_csv, 'perp1m') if perp_csv else None,
               cb=xd.load_extra(found['cb'], 'cb1m') if found and found.get('cb') else None, found=found_frames or None)
    procs = procs or min(4, os.cpu_count() or 1)
    got = dict(hm._imap(_parity_new, list(rows), procs))
    hist = {r['name']: r for r in R0}
    per = {}
    for nm in names:
        R = hist[nm]
        want = [R['levels'][x] if x >= 0 else None for x in heat.read_state(R, rows)]
        ok = sum(got[r].get(nm) == w for r, w in zip(rows, want))
        per[nm] = {'checked': int(len(rows)), 'same': int(ok), 'agreement': round(ok / len(rows), 5) if len(rows) else None}
    # ---- the pack's engine readings and GBM zones
    pk = _read_json(pack_path) or {}
    mm = _read_json(main_meta) or {}
    prow = [r for r in pk.get('rows', []) if r.get('coin') == asset and r.get('kind') in PACK_KINDS]
    eng = {n for r in prow for n in r.get('readings', []) if _is_engine(n)}
    trees = {}
    for r in prow:
        nm = r['readings'][0] if r.get('kind') == 'model' else ''
        g = re.match(r'^GBM\.(TA|ALL)(\d+)$', nm)
        if not g or nm in trees:
            continue
        tj = _read_json(os.path.join(series_dir, 'trees', f'{g.group(1)}_h{g.group(2)}.json'))
        if tj:
            trees[nm] = (tj, ((tj.get('hm2') or {}).get('zone') or {}).get('edges'))
    feats = {F['zs_of'] or F['name'] for tj, _ in trees.values() for F in tj['hm2']['features']}
    erows = rows[::max(1, engine_every)] if (eng or trees) else np.zeros(0, np.int64)
    eng_res, gbm_res = {}, {}
    if len(erows):
        edges, step = mm.get('edges') or {}, mm.get('price_step')
        Rh = _engine_readings(m, eng | {n for n in feats if _is_engine(n)}, edges, step, dom or None)
        _PW.update(engine_names=sorted(eng), engine_edges=edges, step=step, trees=trees, dom_frames=_dom_frames(dom),
                   kmax=max([60] + list(_tfs(eng | feats))))
        live = {r: (lv, gz) for r, lv, gz in hm._imap(_parity_engine, list(erows), procs)}
        for n in sorted(eng):
            if n not in Rh:
                eng_res[n] = {'checked': 0, 'same': 0, 'agreement': None, 'note': 'not built on the history (no edges in the main meta)'}
                continue
            want = [Rh[n]['levels'][x] if x >= 0 else None for x in heat.read_state(Rh[n], erows)]
            ok = sum(live[r][0].get(n) == w for r, w in zip(erows, want))
            eng_res[n] = {'checked': int(len(erows)), 'same': int(ok), 'agreement': round(ok / len(erows), 5)}
        stored = _stored_gbm(series_dir, m)
        for nm, (tj, ed) in trees.items():
            if nm in stored:
                zh, src = np.asarray(stored[nm], np.int64)[erows], 'gbm_codes.npz'
            else:
                zh, src = _gbm_history(tj, ed, lambda n: Rh.get(n) if n in Rh else hist.get(n), erows, m['gap']), 'trees on the history'
            if zh is None:
                gbm_res[nm] = {'checked': 0, 'same': 0, 'agreement': None, 'note': 'a feature reading is missing'}
                continue
            ok = sum(int(a) == b for a, b in zip(zh.tolist(), [live[r][1].get(nm) for r in erows]))
            gbm_res[nm] = {'checked': int(len(erows)), 'same': int(ok), 'agreement': round(ok / len(erows), 5), 'against': src}
    allr = {**per, **eng_res, **gbm_res}
    differ = sorted(n for n, v in allr.items() if v.get('agreement') is None or v['agreement'] < LIVE_MIN)
    res = {'schema': SCHEMA_PARITY, 'asset': asset, 'days': days, 'window_days': window_days, 'rows_checked': int(len(rows)),
           'engine_rows_checked': int(len(erows)), 'from': str(pd.Timestamp(int(m['t0']) + int(rows[0]) * MIN, unit='ms')) if len(rows) else None,
           'to': str(pd.Timestamp(int(m['t0']) + int(rows[-1] + 1) * MIN, unit='ms')) if len(rows) else None,
           'edges': {'same_as_series_meta': len(same), 'different': diff}, 'missing_inputs': miss,
           'readings': per, 'engine': eng_res, 'gbm': gbm_res, 'live_min': LIVE_MIN, 'readings_that_differ': differ,
           'table_sha256': smeta.get('table_sha256'), 'seconds': round(time.time() - t_start, 1)}
    _dump(res, os.path.join(out, 'parity.json'))
    log(f'{asset}: parity on {len(rows):,} closes ({len(erows):,} with the engine and GBM): {len(differ)} readings under {LIVE_MIN:.1%}')
    _PW.clear()
    return res


def _family(name: str) -> str:
    for p, f in hm.FAMILY_PREFIX:
        if name.startswith(p):
            return f
    if name in hm.CLOCK:
        return 'clock'
    if name.split(' ')[0] in CONTEXT_FEED:
        return 'dominance'
    return 'TA'


def needed_feeds(names, gbm_used: dict = None) -> set:
    """The feeds a row needs live: 'spot' always; a family's feed (FAMILY_FEED); dominance for the dominance states; a
    GBM reading needs the feeds of every reading its trees use."""
    out = {'spot'}
    for n in names:
        if n.startswith('GBM.'):
            out |= needed_feeds((gbm_used or {}).get(n, []))
            continue
        n = n.removeprefix('ZS:')
        f = _family(n)
        if f in FAMILY_FEED:
            out.add(FAMILY_FEED[f])
        if f == 'dominance':
            out.add('dominance')
    return out


def set_live_ready(pack: dict, parities: dict, feeds=DEFAULT_FEEDS, live_min: float = LIVE_MIN) -> dict:
    """live_ready per row (kinds pair, triple and model; other kinds, as Part 3's gate rows, are left as they are): every
    reading behind the row (its conds, or a GBM zone) reached live_min on its coin's parity.json, and the bot has the
    feeds it needs (needed_feeds). live_ready_why lists what is missing."""
    feeds = set(feeds or ())
    pack = dict(pack)
    for c, p in parities.items():
        if p.get('table_sha256') and pack.get('table_sha256', {}).get(c) and p['table_sha256'] != pack['table_sha256'][c]:
            raise SystemExit(f'{c}: the parity summary is of another series table than the pack')
    gbm_used = {}
    for c, mm in (pack.get('models') or {}).items():
        for mdl, byh in mm.items():
            for h, t in byh.items():
                gbm_used[f'GBM.{mdl}{h}'] = list(t.get('used') or [])
    rows = []
    for r in pack.get('rows', []):
        if r.get('kind') not in PACK_KINDS:
            rows.append(r)
            continue
        r = dict(r)
        why = []
        p = parities.get(r['coin'])
        if p is None:
            why.append('no parity for this coin')
        else:
            allr = {**(p.get('readings') or {}), **(p.get('engine') or {}), **(p.get('gbm') or {})}
            for n in r.get('readings', []):
                a = (allr.get(n) or {}).get('agreement')
                if a is None:
                    why.append(f'{n}: not checked')
                elif a < live_min:
                    why.append(f'{n}: parity {a:.4f}')
        need = needed_feeds(r.get('readings', []), gbm_used)
        lack = sorted(need - feeds)
        why += [f'no {x} feed' for x in lack]
        r['live_ready'], r['live_ready_why'] = not why, why
        rows.append(r)
    pack['rows'] = rows
    pack['live_reader_parity'] = {'live_min': live_min, 'feeds': sorted(feeds),
                                  'coins': {c: {'rows_checked': p.get('rows_checked'), 'engine_rows_checked': p.get('engine_rows_checked'),
                                                'readings_that_differ': p.get('readings_that_differ', []), 'edges': p.get('edges'),
                                                'from': p.get('from'), 'to': p.get('to')} for c, p in sorted(parities.items())}}
    return pack


# ----------------------------------------------------------------------------------------------------------- CLI
def _coin_files(d: str, name: str) -> dict:
    out = {}
    for c in sorted(os.listdir(d)) if d and os.path.isdir(d) else []:
        p = os.path.join(d, c, name)
        if os.path.isfile(p) and 'twin' not in c:
            _refuse_doge(c)
            out[c] = _read_json(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog='oracle.heat_hm2_league')
    sub = ap.add_subparsers(dest='cmd', required=True)
    lg = sub.add_parser('league')
    lg.add_argument('--inputs', required=True)
    lg.add_argument('--hm1', default='')
    lg.add_argument('--out', required=True)
    lg.add_argument('--stamp', default='')
    lg.add_argument('--packs', default='')
    lg.add_argument('--main-metas', default='')
    lg.add_argument('--gates', default='')
    lg.add_argument('--patterns', default='')
    lg.add_argument('--pack', default='')
    lg.add_argument('--live-meta', default='')
    lg.add_argument('--feeds', default=','.join(DEFAULT_FEEDS))
    pr = sub.add_parser('parity')
    for a in ('--asset', '--csv', '--series', '--out'):
        pr.add_argument(a, required=True)
    for a in ('--others', '--perp', '--fund', '--oi', '--cal', '--dom', '--found', '--main-meta', '--other-metas', '--live-meta', '--pack'):
        pr.add_argument(a, default='')
    pr.add_argument('--days', type=int, default=3)
    pr.add_argument('--engine-every', type=int, default=15)
    pr.add_argument('--window-days', type=int, default=14)
    pr.add_argument('--procs', type=int, default=0)
    lr = sub.add_parser('live-ready')
    lr.add_argument('--pack', required=True)
    lr.add_argument('--parity', required=True)
    lr.add_argument('--feeds', default=','.join(DEFAULT_FEEDS))
    lr.add_argument('--out', default='')
    mg = sub.add_parser('merge-gates')
    mg.add_argument('--pack', required=True)
    mg.add_argument('--gates', required=True)
    mg.add_argument('--out', default='')
    a = ap.parse_args(argv)
    if a.cmd == 'league':
        s = league(a.inputs, a.hm1, a.out, a.stamp, packs_dir=a.packs, main_metas=a.main_metas, gates=a.gates, patterns=a.patterns,
                   pack_out=a.pack, live_meta_out=a.live_meta, feeds=tuple(x for x in a.feeds.split(',') if x))
        print(json.dumps({k: s[k] for k in ('coins', 'twins', 'warnings', 'pack')}, indent=1))
    elif a.cmd == 'parity':
        others = dict(x.split('=', 1) for x in a.others.split(',') if x)
        found = (_read_json(a.found) if os.path.isfile(a.found) else json.loads(a.found)) if a.found else {}
        r = parity(a.asset, a.csv, a.series, a.out, a.live_meta, a.main_meta, others, a.perp, a.fund, a.oi, a.cal, a.dom, found, a.other_metas,
                   a.pack, a.days, engine_every=a.engine_every, window_days=a.window_days, procs=a.procs)
        print(json.dumps({k: r[k] for k in ('asset', 'rows_checked', 'engine_rows_checked', 'readings_that_differ', 'edges')}, indent=1))
    elif a.cmd == 'live-ready':
        pack = _read_json(a.pack)
        pack = set_live_ready(pack, _coin_files(a.parity, 'parity.json'), tuple(x for x in a.feeds.split(',') if x))
        _dump(pack, a.out or a.pack)
        n = sum(bool(r.get('live_ready')) for r in pack['rows'])
        print(f'{a.out or a.pack}: {n:,} of {len(pack["rows"]):,} rows live ready')
    else:
        pack = merge_gate_rows(_read_json(a.pack), a.gates)
        _dump(pack, a.out or a.pack)
        print(f'{a.out or a.pack}: {sum(r.get("kind") in GATE_KINDS for r in pack["rows"]):,} gate rows merged')


if __name__ == '__main__':
    main()
