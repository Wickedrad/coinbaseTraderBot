"""Part 2 of the audit path (research/audit_path/PREREG-AP.md): the last three minutes of the 15-minute window.

The 15-minute contract settles YES when the 60-second average of Kalshi's index before the close is at or above the strike. In the last minute part of that
average is already known. This reads the one-second grids (grid-YYYY-MM-DD.npz from subminute.grid: per coin the best YES bid and ask with sizes per window
and second, the strike, Kalshi's own result, and the day's per-second settlement index idx) and asks whether a buyer who works out the odds second by second
beats the recorded ask after the taker fee. Recorded days only; nothing is ordered; the output is aggregates only (no per-trade row is printed or written).

The odds at second s (720 to 897 of 900): the known seconds of the final minute (840 to s), the latest index x at s, a driftless walk for the seconds still to
come with a one-second step size sigma (the standard deviation of the one-second index changes of the 600 seconds ending at s, at least 300 valid), the exact
variance of the mean of the seconds still to come, and the normal probability that the average is at or above the strike.

Run, from the python directory:

    python3 -m auditpath.last3 choose --grids DIR --from 2026-11-11 --to 2026-11-18 --out FREEZE.json
    python3 -m auditpath.last3 score  --grids DIR --freeze FREEZE.json --from 2026-11-19 --out RESULT.json

choose reads only the grids of the days --from to --to (never a later day), prints the settlement-rule check (the share of windows where the mean of idx over
seconds 840 to 899 at or above the strike matches Kalshi's result; under 97% it stops with exit code 2 and trades nothing), then for each margin of 0, 1, 2, 3,
5, 8 and 12 cents the fills and net, picks the margin (most net dollars among those with at least 100 fills, else the most fills) and writes the freeze file.
The freeze file holds the margin, the table, the days used and a sha256 of every grid read. It is committed before the scoring days are read, so the margin
cannot be changed after seeing them. score reads the margin from the freeze file only, refuses any day at or before the last choosing day, and scores once.

Definitions. Net cents per contract is contract-weighted (net dollars over contracts, times 100). The entry price bands are 0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8
and 0.8-1.0 of the price paid. A locked book (bid equal to ask) is allowed; a one-sided or crossed book is skipped. A book is stale, and skipped, when its age
(seconds since it last changed, measured at the second of the book actually used: s+1 for the main read, s or s+3 for the information reads) is 120 or more.
The favourite twin takes the side that costs more than the other; when both sides cost the same it takes YES. A window that opens before 00:00 UTC or closes
after 24:00 UTC of its grid day is skipped, because its index lies in the neighbouring day's file; the count is printed as windows_skipped_at_day_edge. Split
cells with fewer than 5 fills print the count only. choose accepts only 2026-11-11 to 2026-11-18, as fixed by the pre-registration.

Workflow (.github/workflows/audit-path-last3.yml). It starts on a push that changes research/audit_path/RUN-LAST3; the last non-empty line of that file is the
command: "grids DAY DAY ..." (builds missing grids on Drive, prints day, window counts and hash only), "choose" (Nov 11 to 18) or "score". The freeze file
written by choose must be committed as research/audit_path/FREEZE-LAST3.json before score is run; score fails without it.

Every result line is "AUDITPATH last3 <json>" with aggregates only; the full JSON goes to --out.
"""
import argparse
import datetime as dt
import glob
import hashlib
import json
import math
import os
import re
import sys

import numpy as np

from lossreview.fees import taker_fee
from subminute.ladder_arb import ages

COINS = ('BTC', 'ETH', 'SOL', 'XRP')            # DOGE is excluded from all research
WIN, DAY = 900, 86400
S_LO, S_HI = 720, 897                           # the seconds at which a decision may be taken (inclusive)
FINAL = 840                                     # the final minute is seconds 840 to 899
VOL_SECONDS, VOL_MIN_VALID = 600, 300
STALE_SECONDS = 120                             # a book unchanged for this long is skipped
BUDGET = 20.0                                   # dollars an order may cost
MARGINS = (0, 1, 2, 3, 5, 8, 12)                # cents
MIN_FILLS_CHOOSE = 100
MIN_FILLS_PASS = 200
PASS_PER_HOUR = 1.0
RULE_MIN_MATCH = 0.97
BOOT_DRAWS, BOOT_SEED = 2000, 20261125
Z95 = 1.959963984540054
MIN_CELL_FILLS = 5                              # a split cell with fewer fills prints its count only
TWIN_SEEDS = 20
DELAYS_INFO = (0, 1, 3)
CHOOSE_FIRST, CHOOSE_LAST = '2026-11-11', '2026-11-18'     # the choosing days fixed by the pre-registration
PRELIMINARY_DAYS = ('2026-11-19', '2026-11-20')
SEC_BINS = (('180_121', 720, 779), ('120_61', 780, 839), ('60_0', 840, 899))      # seconds left at s = 900 - s
PRICE_BANDS = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0001))
GRID_RE = re.compile(r'grid-(\d{4}-\d{2}-\d{2})\.npz$')
_ERF = np.frompyfunc(math.erf, 1, 1)


class Stop(Exception):
    """A rule of the pre-registration forbids going on (a wrong settlement rule, a day that may not be read)."""


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# days and files

def day_ms_of(day: str) -> int:
    return int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def days_between(a: str, b: str) -> list:
    d0 = dt.date.fromisoformat(a)
    d1 = dt.date.fromisoformat(b)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def ffill(x: np.ndarray) -> np.ndarray:
    i = np.maximum.accumulate(np.where(np.isfinite(x), np.arange(len(x)), -1))
    return np.where(i >= 0, x[np.maximum(i, 0)], np.nan)


def load_day(path: str, day: str) -> list:
    """One block per coin of one grid file: the per-window book arrays (windows, 900), open second of the day, strike, result and the day's idx."""
    z = np.load(path)
    dms = day_ms_of(day)
    blocks = []
    for ci, c in enumerate(COINS):
        if f'{c}__bid' not in z.files:
            continue
        om = np.asarray(z[f'{c}__open_ms'], np.int64)
        blocks.append({'coin': ci, 'day': day, 'open_ms': om, 'open_s': (om - dms) // 1000,
                       'strike': np.asarray(z[f'{c}__strike'], float), 'result': np.asarray(z[f'{c}__result'], float),
                       'bid': np.asarray(z[f'{c}__bid'], float), 'ask': np.asarray(z[f'{c}__ask'], float),
                       'bsz': np.asarray(z[f'{c}__bsz'], float), 'asz': np.asarray(z[f'{c}__asz'], float),
                       'idx': np.asarray(z[f'{c}__idx'], float)})
    return blocks


def load_days(grids: str, days: list) -> tuple:
    """Reads exactly the grid files of the listed days. Returns (blocks, days read, missing days, {file name: sha256})."""
    blocks, read, missing, sha = [], [], [], {}
    for d in days:
        p = os.path.join(grids, f'grid-{d}.npz')
        if not os.path.isfile(p):
            missing.append(d)
            continue
        sha[os.path.basename(p)] = sha256_file(p)
        blocks += load_day(p, d)
        read.append(d)
    return blocks, read, missing, sha


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# the odds

def pair_min_sum(dists) -> float:
    """Sum over all ordered pairs (i, j), i = j included, of min(d_i, d_j): the covariance weight of a driftless walk's values at the given distances from s."""
    d = sorted(dists)
    m = len(d)
    return float(sum(v * (2 * (m - k) + 1) for k, v in enumerate(d, start=1)))


def future_seconds(s: int) -> list:
    """The seconds of the final minute still to come after second s."""
    return list(range(max(FINAL, s + 1), WIN))


def variance_factor(s: int) -> float:
    """Variance of the average of the final minute, in units of sigma squared: the sum over pairs of the seconds still to come of the smaller of their two
    distances from s, divided by 3,600."""
    return pair_min_sum([j - s for j in future_seconds(s)]) / 3600.0


def norm_sf(z):
    """P(Z >= z) for a standard normal, from math.erf."""
    z = np.asarray(z, float)
    return 0.5 * (1.0 - np.asarray(_ERF(z / math.sqrt(2.0)), dtype=float))


def p_yes(known_sum: float, x: float, s: int, sigma: float, strike: float) -> float:
    """P(the average of the final minute is at or above the strike) at second s. known_sum = sum of the index at seconds 840 to s (0 when s < 840); x = the
    latest index at s."""
    m = len(future_seconds(s))
    mean = (known_sum + x * m) / 60.0
    sd = sigma * math.sqrt(variance_factor(s))
    if sd <= 0.0:
        return 1.0 if mean >= strike else 0.0
    return float(norm_sf((strike - mean) / sd))


def window_odds(blk: dict) -> dict:
    """P(YES) for every window of a block at every second S_LO..S_HI. ok = False where the odds cannot be formed (no strike, result or index, or sigma from
    fewer than 300 valid seconds). Uses nothing after second s."""
    nw = len(blk['open_s'])
    ns = S_HI - S_LO + 1
    ss = np.arange(S_LO, S_HI + 1)
    raw = blk['idx']
    ff = ffill(raw)
    T = blk['open_s'][:, None] + np.arange(WIN)[None, :]
    inr = (T >= 0) & (T < DAY)
    X = np.where(inr, ff[np.clip(T, 0, DAY - 1)], np.nan)                       # the latest index at each second of each window
    # sigma from the valid one-second changes of the 600 seconds ending at s
    dd = np.full(DAY, np.nan)
    dd[1:] = raw[1:] - raw[:-1]
    v = np.isfinite(dd)
    z0 = np.where(v, dd, 0.0)
    pn = np.concatenate(([0], np.cumsum(v)))
    p1 = np.concatenate(([0.0], np.cumsum(z0)))
    p2 = np.concatenate(([0.0], np.cumsum(z0 * z0)))
    t_hi = blk['open_s'][:, None] + ss[None, :]
    t_lo = t_hi - (VOL_SECONDS - 1)
    good_t = (t_lo >= 1) & (t_hi < DAY)
    hi = np.clip(t_hi + 1, 0, DAY)
    lo = np.clip(t_lo, 0, DAY)
    cnt = pn[hi] - pn[lo]
    with np.errstate(divide='ignore', invalid='ignore'):
        var = (p2[hi] - p2[lo] - (p1[hi] - p1[lo]) ** 2 / cnt) / (cnt - 1)
    sigma = np.sqrt(np.maximum(var, 0.0))
    ok_sigma = good_t & (cnt >= VOL_MIN_VALID) & np.isfinite(sigma)
    # known part and latest value
    known_cum = np.cumsum(X[:, FINAL:], axis=1)                                  # NaN once any known second has no index
    known = np.where(ss[None, :] >= FINAL, known_cum[:, np.clip(ss - FINAL, 0, WIN - FINAL - 1)], 0.0)
    x = X[:, S_LO:S_HI + 1]
    m = np.array([len(future_seconds(int(s))) for s in ss], float)[None, :]
    vf = np.array([variance_factor(int(s)) for s in ss])[None, :]
    mean = (known + x * m) / 60.0
    sd = sigma * np.sqrt(vf)
    strike = blk['strike'][:, None]
    with np.errstate(divide='ignore', invalid='ignore'):
        zz = (strike - mean) / sd
    prob = np.where(sd > 0, norm_sf(np.where(sd > 0, zz, 0.0)), (mean >= strike).astype(float))
    ok = (ok_sigma & np.isfinite(prob) & np.isfinite(strike) & np.isfinite(blk['result'])[:, None] & np.isfinite(x) & np.isfinite(known))
    prob = np.where(ok, prob, np.nan)
    return {'prob': prob, 'ok': ok, 'nw': nw, 'ns': ns}


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# settlement-rule check

def settlement_check(blocks: list) -> dict:
    """How often "the mean of idx over seconds 840 to 899 at or above the strike" matches Kalshi's own result."""
    n = match = 0
    for blk in blocks:
        ff = ffill(blk['idx'])
        for w in range(len(blk['open_s'])):
            t0 = int(blk['open_s'][w]) + FINAL
            if t0 < 0 or t0 + 60 > DAY or not np.isfinite(blk['strike'][w]) or not np.isfinite(blk['result'][w]):
                continue
            seg = ff[t0:t0 + 60]
            if not np.isfinite(seg).all():
                continue
            n += 1
            match += int((float(seg.mean()) >= blk['strike'][w]) == (blk['result'][w] == 1.0))
    return {'windows': n, 'matches': match, 'share': (match / n) if n else None}


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# the trade rule

_FEE = {}


def fee_total(n: int, p: float) -> float:
    k = (int(n), round(float(p), 6))
    if k not in _FEE:
        _FEE[k] = taker_fee(int(n), k[1])
    return _FEE[k]


def contracts(p: float, size: float, stake: float) -> int:
    """The smaller of floor(stake / p) and the size shown at the price; 0 means no trade (needs at least 1)."""
    if not (0.0 < p < 1.0) or not np.isfinite(size):
        return 0
    return int(min(math.floor(stake / p + 1e-9), math.floor(size + 1e-9)))


def book_tables(blk: dict, odds: dict, delay: int, stake: float) -> dict:
    """Per window and decision second: the price, contracts, fee per contract and edge of each side from the book at second s + delay, and whether the
    second may be traded at all (odds formed, book fresh, two-sided and not crossed)."""
    nw, ns = odds['nw'], odds['ns']
    ss = np.arange(S_LO, S_HI + 1)
    e = ss + delay
    inb = e < WIN
    ec = np.minimum(e, WIN - 1)
    ag = ages(blk['bid'], blk['ask'], blk['bsz'], blk['asz'])[:, ec] if nw else np.zeros((0, ns))
    bid, ask = blk['bid'][:, ec], blk['ask'][:, ec]
    bsz, asz = blk['bsz'][:, ec], blk['asz'][:, ec]
    with np.errstate(invalid='ignore'):
        book = inb[None, :] & np.isfinite(bid) & np.isfinite(ask) & (bid <= ask) & (ag < STALE_SECONDS)
    use = odds['ok'] & book
    t = {k: np.zeros((nw, ns)) for k in ('py', 'pn', 'fy', 'fn', 'ey', 'en')}
    t['ny'] = np.zeros((nw, ns), int)
    t['nn'] = np.zeros((nw, ns), int)
    ey = np.full((nw, ns), -np.inf)
    en = np.full((nw, ns), -np.inf)
    for w, j in zip(*np.nonzero(use)):
        pr = float(odds['prob'][w, j])
        py = round(float(ask[w, j]), 6)
        pn = round(1.0 - float(bid[w, j]), 6)
        ny, nn = contracts(py, asz[w, j], stake), contracts(pn, bsz[w, j], stake)
        t['py'][w, j], t['pn'][w, j], t['ny'][w, j], t['nn'][w, j] = py, pn, ny, nn
        if ny >= 1:
            t['fy'][w, j] = fee_total(ny, py)
            ey[w, j] = pr - py - t['fy'][w, j] / ny
        if nn >= 1:
            t['fn'][w, j] = fee_total(nn, pn)
            en[w, j] = (1.0 - pr) - pn - t['fn'][w, j] / nn
    side = np.where(ey >= en, 1, -1)
    t['edge'] = np.maximum(ey, en)
    t['side'] = side
    t['ey'], t['en'] = ey, en
    t['use'] = use
    t['ss'] = ss
    return t


def fills_of(blk: dict, odds: dict, tab: dict, margin_cents: float) -> dict:
    """The trade of each window: the first second where the better side's edge is at least the margin; one trade per window; held to settlement."""
    cond = tab['use'] & np.isfinite(tab['edge']) & (tab['edge'] >= margin_cents / 100.0 - 1e-12)
    rows = np.flatnonzero(cond.any(1))
    j = cond.argmax(1)[rows]
    side = tab['side'][rows, j]
    yes = side > 0
    p = np.where(yes, tab['py'][rows, j], tab['pn'][rows, j])
    n = np.where(yes, tab['ny'][rows, j], tab['nn'][rows, j])
    fee = np.where(yes, tab['fy'][rows, j], tab['fn'][rows, j])
    res = blk['result'][rows]
    won = np.where(yes, res, 1.0 - res)
    return {'coin': np.full(len(rows), blk['coin']), 'day': np.array([blk['day']] * len(rows), dtype=object),
            'slot': blk['open_ms'][rows] + WIN * 1000, 's': tab['ss'][j], 'side': side, 'p': p, 'n': n, 'fee': fee, 'won': won,
            'net': n * (won - p) - fee, 'edge': tab['edge'][rows, j],
            'py': tab['py'][rows, j], 'pn': tab['pn'][rows, j], 'ny': tab['ny'][rows, j], 'nn': tab['nn'][rows, j],
            'fy': tab['fy'][rows, j], 'fn': tab['fn'][rows, j], 'res': res}


def concat_fills(parts: list) -> dict:
    keys = ('coin', 'day', 'slot', 's', 'side', 'p', 'n', 'fee', 'won', 'net', 'edge', 'py', 'pn', 'ny', 'nn', 'fy', 'fn', 'res')
    if not parts:
        return {k: np.zeros(0, dtype=object if k == 'day' else float) for k in keys}
    return {k: np.concatenate([p[k] for p in parts]) for k in keys}


def run_blocks(blocks: list, odds: list, margins, delay: int = 1, stake: float = BUDGET) -> dict:
    """{margin: fills} over all blocks. The tables are built once and read for each margin."""
    parts = {m: [] for m in margins}
    for blk, od in zip(blocks, odds):
        tab = book_tables(blk, od, delay, stake)
        for m in margins:
            parts[m].append(fills_of(blk, od, tab, m))
    return {m: concat_fills(parts[m]) for m in margins}


def totals(f: dict) -> dict:
    n = int(len(f['net']))
    cc = float(np.sum(f['n']))
    nd = float(np.sum(f['net']))
    return {'fills': n, 'contracts': int(cc), 'net_dollars': round(nd, 4), 'net_cents_per_contract': (round(100.0 * nd / cc, 4) if cc else None)}


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# choosing the margin

def pick_margin(table: list) -> int:
    """The margin with the most net dollars among those with at least 100 fills; if none has 100, the one with the most fills. Ties go to the smaller margin."""
    big = [r for r in table if r['fills'] >= MIN_FILLS_CHOOSE]
    if big:
        best = max(big, key=lambda r: (r['net_dollars'], -r['margin_cents']))
    else:
        best = max(table, key=lambda r: (r['fills'], -r['margin_cents']))
    return best['margin_cents']


def emit(part: str, obj: dict) -> None:
    print('AUDITPATH last3 ' + json.dumps({'part': part, **obj}, sort_keys=True, default=float), flush=True)


def edge_windows(blocks: list) -> int:
    """Windows that open before 00:00 UTC or close after 24:00 UTC of their grid day. Their index lives in the neighbouring day's file, so they are skipped."""
    return int(sum(int(np.sum((b['open_s'] < 0) | (b['open_s'] + WIN > DAY))) for b in blocks))


def choose(grids: str, d_from: str, d_to: str, out: str) -> dict:
    if d_from < CHOOSE_FIRST or d_to > CHOOSE_LAST:
        raise Stop(f'choose reads only {CHOOSE_FIRST} to {CHOOSE_LAST} (asked {d_from} to {d_to}): stopped, nothing read')
    days = days_between(d_from, d_to)
    blocks, read, missing, sha = load_days(grids, days)
    chk = settlement_check(blocks)
    emit('settlement_rule', {'from': d_from, 'to': d_to, 'days_read': read, 'days_missing': missing, 'windows_skipped_at_day_edge': edge_windows(blocks), **chk})
    if chk['share'] is None or chk['share'] < RULE_MIN_MATCH:
        share = None if chk['share'] is None else round(chk['share'], 4)
        raise Stop(f"the settlement rule does not match Kalshi's result in at least 97% of windows (share {share} over {chk['windows']} windows): stopped, nothing traded")
    odds = [window_odds(b) for b in blocks]
    by_m = run_blocks(blocks, odds, MARGINS)
    table = [{'margin_cents': m, **totals(by_m[m])} for m in MARGINS]
    for r in table:
        emit('margin', r)
    margin = pick_margin(table)
    freeze = {'margin_cents': margin, 'table': table, 'days_used': read, 'days_missing': missing, 'last_day': d_to,
              'settlement_rule': chk, 'grid_sha256': sha, 'rule': 'most net dollars among margins with at least 100 fills, else the most fills'}
    emit('chosen', {'margin_cents': margin, 'days_used': read})
    with open(out, 'w') as f:
        json.dump(freeze, f, indent=1, sort_keys=True, default=float)
    return freeze


# ---------------------------------------------------------------------------------------------------------------------------------------------------------
# scoring

def slot_bootstrap(slots_all: np.ndarray, f: dict, draws: int = BOOT_DRAWS, seed: int = BOOT_SEED) -> dict:
    """Bootstrap over time slots (the windows of all coins closing at one time are drawn together) of net cents per contract (sum net / sum contracts)."""
    u, inv = np.unique(np.concatenate([slots_all, f['slot']]), return_inverse=True)
    k = len(u)
    num = np.zeros(k)
    den = np.zeros(k)
    ii = inv[len(slots_all):]
    np.add.at(num, ii, f['net'])
    np.add.at(den, ii, f['n'])
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, k, size=(draws, k))
    sn, sd = num[pick].sum(1), den[pick].sum(1)
    with np.errstate(divide='ignore', invalid='ignore'):
        r = 100.0 * sn / sd
    r = r[np.isfinite(r)]
    mean = 100.0 * num.sum() / den.sum() if den.sum() > 0 else float('nan')
    se = float(np.std(r, ddof=1)) if len(r) > 1 else float('nan')
    return {'mean_cents': mean, 'se_cents': se, 'lo_cents': mean - Z95 * se, 'hi_cents': mean + Z95 * se, 'slots': int(k), 'draws': int(draws)}


def twin_pick(f: dict, side: np.ndarray) -> dict:
    """The same windows and seconds with another side chosen: net dollars and contracts of the fills whose chosen side can be bought (a size of at least 1)."""
    yes = side > 0
    n = np.where(yes, f['ny'], f['nn'])
    p = np.where(yes, f['py'], f['pn'])
    fee = np.where(yes, f['fy'], f['fn'])
    won = np.where(yes, f['res'], 1.0 - f['res'])
    okk = n >= 1
    net = np.where(okk, n * (won - p) - fee, 0.0)
    return {'fills': int(okk.sum()), 'contracts': float(np.where(okk, n, 0).sum()), 'net': float(net.sum())}


def twins(f: dict) -> dict:
    """Coin-flip side (the mean of 20 seeds) and the favourite (the side costing more; when both cost the same, YES), at the fills' own windows and seconds."""
    k = len(f['net'])
    rs = []
    for sd in range(1, TWIN_SEEDS + 1):
        rng = np.random.default_rng(sd)
        side = np.where(rng.random(k) < 0.5, 1, -1)
        rs.append(twin_pick(f, side))
    fav = twin_pick(f, np.where(f['py'] >= f['pn'], 1, -1))

    def fmt(parts):
        fills = float(np.mean([r['fills'] for r in parts]))
        cc = float(np.mean([r['contracts'] for r in parts]))
        nd = float(np.mean([r['net'] for r in parts]))
        return {'fills': round(fills, 2), 'contracts': round(cc, 2), 'net_dollars': round(nd, 4),
                'net_cents_per_contract': round(100.0 * nd / cc, 4) if cc else None}
    return {'coin_flip_mean_of_20_seeds': fmt(rs), 'favourite': fmt([fav])}


def splits(f: dict) -> dict:
    def part(mask):
        g = {key: v[mask] for key, v in f.items()}
        t = totals(g)
        if t['fills'] < MIN_CELL_FILLS:                # a cell of one to four trades would show those trades' own result
            t['net_dollars'] = t['net_cents_per_contract'] = None
        return t
    out = {'by_coin': {COINS[c]: part(f['coin'] == c) for c in range(len(COINS))},
           'by_day': {d: part(f['day'] == d) for d in sorted(set(f['day'].tolist()))},
           'by_seconds_left': {name: part((f['s'] >= lo) & (f['s'] <= hi)) for name, lo, hi in SEC_BINS},
           'by_entry_price': {f'{lo:.1f}_{min(hi, 1.0):.1f}': part((f['p'] >= lo) & (f['p'] < hi)) for lo, hi in PRICE_BANDS}}
    return out


def pass_line(stats: dict, fills: int, per_hour: float, days: list) -> dict:
    lo = stats['lo_cents']
    c_range = bool(np.isfinite(lo) and lo > 0)
    c_fills = fills >= MIN_FILLS_PASS
    c_hour = per_hour >= PASS_PER_HOUR
    if not c_fills:
        verdict = 'too thin to decide'
    else:
        verdict = 'pass' if (c_range and c_hour) else 'no pass'
    return {'range_above_zero': c_range, 'at_least_200_fills': c_fills, 'at_least_1_dollar_an_hour': c_hour, 'verdict': verdict,
            'preliminary': bool(sorted(days) == list(PRELIMINARY_DAYS))}


def score(grids: str, freeze_path: str, d_from: str, out: str) -> dict:
    with open(freeze_path) as fh:
        fz = json.load(fh)
    margin = fz['margin_cents']
    last = fz['last_day']
    if d_from <= last:
        raise Stop(f'score refuses days at or before the last choosing day {last} (asked from {d_from})')
    days = sorted(m.group(1) for m in (GRID_RE.search(p) for p in glob.glob(os.path.join(grids, 'grid-*.npz'))) if m and m.group(1) >= d_from)
    blocks, read, missing, sha = load_days(grids, days)
    if not read:
        raise Stop('no grid of a scoring day found')
    odds = [window_odds(b) for b in blocks]
    slots_all = np.unique(np.concatenate([b['open_ms'] + WIN * 1000 for b in blocks])) if blocks else np.zeros(0, np.int64)
    hours = 24.0 * len(read)
    info = {}
    main = None
    for d in DELAYS_INFO:
        f = run_blocks(blocks, odds, [margin], delay=d)[margin]
        info[f'book_at_s_plus_{d}'] = {**totals(f), 'dollars_an_hour': round(float(np.sum(f['net'])) / hours, 4), **splits(f)}
        if d == 1:
            main = f
    f10 = run_blocks(blocks, odds, [margin], delay=1, stake=10.0)[margin]
    st = slot_bootstrap(slots_all, main)
    tot = totals(main)
    per_hour = tot['net_dollars'] / hours
    res = {'margin_cents': margin, 'freeze_last_day': last, 'days_scored': read, 'days_missing_from_list': missing, 'hours': hours,
           'windows': int(sum(len(b['open_s']) for b in blocks)), 'windows_skipped_at_day_edge': edge_windows(blocks), **tot,
           'se_cents': st['se_cents'], 'range_cents': [st['lo_cents'], st['hi_cents']], 'bootstrap': {'slots': st['slots'], 'draws': st['draws'], 'seed': BOOT_SEED},
           'dollars_an_hour': round(per_hour, 4), 'pass_line': pass_line(st, tot['fills'], per_hour, read),
           'twins': twins(main), 'information': info,
           'dollars_an_hour_at_10_dollar_orders': round(float(np.sum(f10['net'])) / hours, 4), 'fills_at_10_dollar_orders': int(len(f10['net'])),
           'grid_sha256': sha}
    emit('score', {k: v for k, v in res.items() if k not in ('information', 'twins')})
    emit('twins', res['twins'])
    for k, v in info.items():
        emit('information', {'book': k, **v})
    with open(out, 'w') as f:
        json.dump(res, f, indent=1, sort_keys=True, default=float)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='auditpath.last3', description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('choose', help='choose the margin on the building days and write the freeze file')
    c.add_argument('--grids', required=True)
    c.add_argument('--from', dest='d_from', required=True)
    c.add_argument('--to', dest='d_to', required=True)
    c.add_argument('--out', required=True)
    s = sub.add_parser('score', help='score the frozen margin once on the later days')
    s.add_argument('--grids', required=True)
    s.add_argument('--freeze', required=True)
    s.add_argument('--from', dest='d_from', required=True)
    s.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'choose':
            choose(a.grids, a.d_from, a.d_to, a.out)
        else:
            score(a.grids, a.freeze, a.d_from, a.out)
    except Stop as e:
        print('AUDITPATH last3 ' + json.dumps({'part': 'stopped', 'reason': str(e)}), flush=True)
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
