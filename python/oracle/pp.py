"""Price Prediction part builder: Kalshi 15-minute and hourly crypto contracts -> parts/pp15-<A>/ or parts/pp60-<A>/.

Implements SPEC.md 2b and the OR-H1 prereg sections "Decision times, entries, labels, exits" (Price Prediction),
"Features" (contract state; spot TA joined from the spot part) and "Mining" (the matched-baseline strata).

    cd python && python3 -m oracle.pp --kind 15|60 --history <dir with kalshi/KX<A>15M or KX<A>D> \
        --spot parts/spot-<A> --asset BTC --out parts [--code-sha <sha>]

Decisions. A window of N minutes (15, or the last 60 of an hourly ladder market) has decision instants
t_k = open + 60 s x k; the YES quote at t_k is candle k's close (python/allpairs/data.py: minute 0 dropped, two-sided
books only, legacy cents repaired). Entry window: 15-minute k = 1..10 (840..300 s before close); hourly k = 5..50
(3300..600 s) with the YES mid in [0.10, 0.90]. Sides: YES at the ask, NO at 1 - YES bid (allpairs side_quotes); the
side's ask must lie in [0.10, 0.90]. C = min(floor(stake / ask), 250), taker fee on both legs (allpairs fees, the exact
bot/fees.ts port), no settlement fee. A row is a decision where at least one side is tradable and the spot part has the
minute whose END equals t_k.

Primary exit (per side, at the entry's own C): for j = k+1 .. N-1 with tau_j > 10% of the window, sell at the bid at the
first j whose net is >= $5 (take-profit, hit). Otherwise, at the final decision minute N-1: ride to settlement if the net
at that bid is > 0 (hit if the settlement net is >= $5), else sell at that bid. A final minute with no two-sided book
cannot be sold into, so the position settles (as allpairs/snell.py does). best = max(net of every bid sale in
(k, N-1], settlement net). hold = minutes from t_k to the exit (settlement counts as the close).
Adversaries: tradeLat = the same trade entered at k+1 (its ask and C); tradeCost = entry price + 1c (C and fee at it).
Sensitivity: tradeSettle = the primary trade with every non-take-profit exit settled. The prereg's sale at the final
candle N-1 is 60 s before the close, where the live bot cannot exit (relaxed cadence: STRATEGY_NO_EXIT_BEFORE_CLOSE_SEC
60, engine.ts exitWindowOpen = tau > 60 s), so live a loser settles; it is reported beside HO-1, never selected on.
Prices are rounded to 4 decimals before sizing and fees (the bot rounds NO prices so; review fix, Nov 6).

Contract features (bucket / state, int8). Same for both sides: k_tau, k_spread, k_vol5. Side-relative, one column per side
named <feature>@Y / <feature>@N and listed in meta.side_features: k_price (the side's ask), k_dmid1/3/5 (the side's mid
change), k_z (z for YES, -z for NO), k_fair (fair - side mid with fair = Phi(z) for YES, 1 - Phi(z) for NO).
Spot features: the spot part's X row at t_end == t_k, copied column for column (they apply to both sides).
Strata per side: (price bucket x 3 + tau bucket) x 4 + RV slot (RV tercile 0..2, or 3 when the spot RV is NA).
NEVER DOGE. No day file dated 2026-11-05 or later is opened; no window closing after HOLD_TO is kept.
"""
from __future__ import annotations

import argparse
import os
import subprocess

import numpy as np
from scipy.special import ndtr

from allpairs import EXCLUDED_ASSETS
from allpairs.data import _file_day, load_kalshi
from allpairs.features import side_quotes
from allpairs.fees import contracts_for_stake, taker_fee

from .common import (ASSETS, DAY, DEV_END, HOLD_TO, HORIZONS, MAX_CONTRACTS, MIN, SIDES, SIZE, SIZE2, STEP_MIN, TARGET_USD,
                     Part, dev_rows, key, write_part)

KINDS = {
    15: {'ct': 'pp15', 'n': 15, 'series': 'KX{asset}15M', 'k': (1, 10), 'mid_band': None},
    60: {'ct': 'pp60', 'n': 60, 'series': 'KX{asset}D', 'k': (5, 50), 'mid_band': (0.10, 0.90)},
}
PRICE_BAND = (0.10, 0.90)        # RISK_MIN_SIDE_PRICE on the side's ask
END_FRAC = 0.10                  # no take-profit sale in the last 10% of the window
COST_STRESS = 0.01               # adversary: +1c on the entry price
EPS = 1e-9

# Bucket edges (fixed, chosen before any result; documented in meta.features[].desc).
Z_EDGES = (-1.5, -0.75, -0.25, 0.25, 0.75, 1.5)          # k_z: 7 levels, searchsorted side='right'
GAP_EDGES = (-0.10, -0.05, -0.02, 0.02, 0.05, 0.10)      # k_fair: 7 levels
SPREAD_EDGES = (0.01, 0.02, 0.05)                         # k_spread: <=1c, <=2c, <=5c, >5c
DMID_MIN = 0.01                                           # k_dmid*: a mid change of at least 1c
VOL_FALLBACK = (10.0, 100.0, 1000.0)                      # k_vol5 cut points when dev rows are too few to fit quartiles


def _code_sha() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=os.path.dirname(os.path.abspath(__file__)), capture_output=True,
                              text=True, timeout=10).stdout.strip() or 'unknown'
    except Exception:
        return 'unknown'


def check_asset(asset: str, kind: int) -> str:
    a = str(asset).strip().upper()
    if 'DOGE' in a or a in EXCLUDED_ASSETS:
        raise ValueError('DOGE refused (never DOGE)')
    if a not in ASSETS:
        raise ValueError(f'unknown asset {asset!r} (one of {ASSETS})')
    if kind == 60 and a == 'XRP':
        raise ValueError('no XRP hourly series exists (prereg Data)')
    return a


def forbidden_days() -> set:
    """UTC day numbers that are never read: 2026-11-05 onward (the embargo day, the lockbox and everything after)."""
    d0 = HOLD_TO // DAY
    return set(range(d0, d0 + 3660))


def prescan(history: str, series: str) -> None:
    """Refuse a series folder holding a .jsonl whose name is not a YYYY-MM-DD day (load_kalshi would read it, and its
    dates could not be checked against the 2026-11-05 cut)."""
    d = os.path.join(history, 'kalshi', series)
    if not os.path.isdir(d):
        raise SystemExit(f'no {d}')
    bad = [f for f in os.listdir(d) if f.endswith('.jsonl') and _file_day(f) is None]
    if bad:
        raise SystemExit(f'{d}: {len(bad)} .jsonl file(s) not named by UTC day, e.g. {bad[0]!r}: refused')


# ---------- the exit ----------

def tp_zone(n: int) -> np.ndarray:
    """(n,) bool: decision minute j may take profit, i.e. tau_j = n - j minutes > 10% of the window."""
    return (n - np.arange(n)) > END_FRAC * n + EPS


def simulate(bid: np.ndarray, settle: np.ndarray, k0: int, px: np.ndarray, stake: float, n: int,
             max_c: int = 250, target: float = TARGET_USD) -> dict:
    """The primary exit for M positions entered at minute k0 at price px (per contract, before the fee).

    bid (M, n): the side's bid at t_0..t_{n-1} (NaN = no two-sided book); settle (M,): 1 if the side won, else 0.
    Returns trade, best (net $), hit (bool), hold (minutes), C; NaN / 0 where px is not a valid price."""
    bid = np.asarray(bid, dtype=np.float64)
    M, N = bid.shape
    assert N == n, (N, n)
    px = np.asarray(px, dtype=np.float64)
    live = np.isfinite(px) & (px > 0) & (px < 1)
    # Prices on the 4-decimal grid before sizing and fees, as the bot rounds a NO price (engine.ts Math.round((1 - ask)
    # * 1e4) / 1e4): a NO ask 1 - 0.84 is 0.16000000000000003 in float, and floor(20 / it) would buy 124, not 125.
    pxs = np.round(np.where(live, px, 0.5), 4)
    C = np.where(live, np.minimum(contracts_for_stake(stake, pxs), max_c), 0.0)
    cost = C * pxs + taker_fee(C, pxs)
    j = np.arange(N)[None, :]
    can = np.isfinite(bid) & (bid > 0) & (bid < 1) & (j > k0)
    bs = np.round(np.where(can, bid, 0.5), 4)
    net = np.where(can, np.round(C[:, None] * bs - taker_fee(C[:, None], bs) - cost[:, None], 6), np.nan)
    tp = can & (tp_zone(n)[None, :]) & (net >= target)                # tau_j > 10% of the window, net >= $5
    has_tp = tp.any(axis=1)
    j_tp = np.argmax(tp, axis=1)
    rows = np.arange(M)
    net_tp = net[rows, j_tp]
    last = n - 1
    net_last = net[:, last]
    settle_net = np.round(C * np.asarray(settle, dtype=np.float64) - cost, 6)
    ride = ~has_tp & (~np.isfinite(net_last) | (net_last > 0))        # no book at the last minute: it settles
    trade = np.where(has_tp, net_tp, np.where(ride, settle_net, net_last))
    hit = has_tp | (ride & (settle_net >= target))
    hold = np.where(has_tp, j_tp - k0, np.where(ride, n - k0, last - k0))
    best = np.fmax(np.max(np.where(can, net, -np.inf), axis=1), settle_net)
    # Sensitivity (never selected on): the live bot cannot sell in the last 60 s (relaxed cadence, STRATEGY_NO_EXIT_
    # BEFORE_CLOSE_SEC 60; engine.ts exitWindowOpen = tau > 60 s), so a position without a take-profit settles there.
    trade_settle = np.where(has_tp, net_tp, settle_net)
    return {'trade': np.where(live, trade, np.nan), 'best': np.where(live, best, np.nan), 'hit': live & hit,
            'hold': np.where(live, hold, 0).astype(np.int64), 'C': C, 'trade_settle': np.where(live, trade_settle, np.nan)}


# ---------- features ----------

def price_bucket(ask: np.ndarray) -> np.ndarray:
    """0.1-wide bucket of the side's ask inside [0.10, 0.90]: 0 = [0.10, 0.20) .. 7 = [0.80, 0.90]; -1 outside."""
    ask = np.asarray(ask, dtype=np.float64)
    inb = np.isfinite(ask) & (ask >= PRICE_BAND[0] - EPS) & (ask <= PRICE_BAND[1] + EPS)
    cents = np.floor(np.where(inb, ask, 0.5) * 100 + 1e-6)
    return np.where(inb, np.clip((cents - 10) // 10, 0, 7), -1).astype(np.int8)


def tau_bucket(k: np.ndarray, k_lo: int, k_hi: int) -> np.ndarray:
    """Thirds of the entry window by decision minute: 0 = earliest (most time left) .. 2 = latest."""
    return ((3 * (np.asarray(k) - k_lo)) // (k_hi - k_lo + 1)).astype(np.int8)


def spread_bucket(spread: np.ndarray) -> np.ndarray:
    s = np.asarray(spread, dtype=np.float64)
    return np.where(np.isfinite(s), np.searchsorted(np.asarray(SPREAD_EDGES) + 1e-6, s, side='left'), -1).astype(np.int8)


def edge_bucket(x: np.ndarray, edges) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return np.where(np.isfinite(x), np.searchsorted(np.asarray(edges), x, side='right'), -1).astype(np.int8)


def dmid_state(d: np.ndarray) -> np.ndarray:
    d = np.asarray(d, dtype=np.float64)
    return np.where(np.isfinite(d) & (d >= DMID_MIN - EPS), 1, np.where(np.isfinite(d) & (d <= -DMID_MIN + EPS), -1, 0)).astype(np.int8)


def vol_edges(vol5: np.ndarray, dev: np.ndarray) -> tuple[list, str]:
    """Quartile cut points of the positive last-5-minute volumes on dev rows (before DEV_END); fixed fallback."""
    v = vol5[dev & (vol5 > 0)]
    if len(v) >= 40:
        q = np.quantile(v, [0.25, 0.5, 0.75])
        if np.all(np.diff(q) > 0):
            return [float(x) for x in q], f'quartiles of positive values on {len(v)} dev rows'
    return list(VOL_FALLBACK), 'fixed fallback (too few dev rows to fit quartiles)'


def vol_bucket(vol5: np.ndarray, edges) -> np.ndarray:
    v = np.asarray(vol5, dtype=np.float64)
    return np.where(v > 0, 1 + np.searchsorted(np.asarray(edges), v, side='right'), 0).astype(np.int8)


# ---------- spot join ----------

def join_spot(t: np.ndarray, t_end: np.ndarray) -> np.ndarray:
    """Index of the spot row whose t_end equals t (the spot minute that ENDS at the decision instant), -1 if none."""
    t = np.asarray(t, dtype=np.int64)
    t_end = np.asarray(t_end, dtype=np.int64)
    if len(t_end) > 1 and not np.all(np.diff(t_end) > 0):
        raise ValueError('spot t_end is not strictly increasing')
    i = np.searchsorted(t_end, t)
    ic = np.minimum(i, max(len(t_end) - 1, 0))
    found = (i < len(t_end)) & (t_end[ic] == t) if len(t_end) else np.zeros(t.shape, dtype=bool)
    idx = np.where(found, ic, -1)
    assert np.all(t_end[idx[found]] == t[found])
    return idx


# ---------- build ----------

def build(kind: int, history: str, spot_dir: str, asset: str, out_root: str, code_sha: str | None = None, log=print) -> str:
    kind = int(kind)
    if kind not in KINDS:
        raise ValueError('--kind must be 15 or 60')
    cfg = KINDS[kind]
    ct, n = cfg['ct'], cfg['n']
    k_lo, k_hi = cfg['k']
    asset = check_asset(asset, kind)
    if 'DOGE' in os.path.basename(os.path.normpath(spot_dir)).upper():
        raise ValueError('DOGE spot part refused')
    h = HORIZONS[ct][0]
    stake, stake2, max_c = SIZE[ct], SIZE2[ct], MAX_CONTRACTS[ct]

    sp = Part(spot_dir)
    if sp.meta.get('scope') not in (None, asset):
        raise ValueError(f'spot part scope {sp.meta.get("scope")!r} != {asset}')
    sp_t, sp_close, sp_rv60, sp_rv, sp_X = sp['t_end'], sp['close'], sp['rv60'], sp['rv'], sp['X']
    sp_feats = list(sp.meta.get('features') or [])
    if not len(sp_t):
        raise SystemExit(f'{spot_dir}: empty spot part')
    if sp_X.ndim != 2 or sp_X.shape[1] != len(sp_feats):
        raise ValueError(f'spot X {sp_X.shape} does not match {len(sp_feats)} meta features')

    series = cfg['series'].format(asset=asset)
    prescan(history, series)
    w = load_kalshi(history, [asset], n=n, series_fmt=cfg['series'], log=log, skip_days=forbidden_days())
    close_ms = w.open_ms + n * MIN
    keep = close_ms <= HOLD_TO
    seen: set = set()
    dup = np.zeros(len(w), dtype=bool)
    for i, tk in enumerate(w.tickers):
        if tk and tk in seen:
            dup[i] = True
        seen.add(tk)
    keep &= ~dup
    nonthr = np.zeros(len(w), dtype=bool)
    if kind == 60:   # greater-than ladder strikes only (ticker ...-T<strike>); a range bucket would break z and fair
        nonthr = np.array([bool(tk) and not tk.rsplit('-', 1)[-1].startswith('T') for tk in w.tickers], dtype=bool)
        keep &= ~nonthr
    log(f'{ct}-{asset}: {len(w)} windows loaded; dropped {int((close_ms > HOLD_TO).sum())} closing after HOLD_TO, '
        f'{int(dup.sum())} duplicate tickers, {int(nonthr.sum())} non-threshold tickers')
    w = w.subset(np.nonzero(keep)[0])
    W = len(w)
    if not W:
        raise SystemExit('no windows left')

    bid, ask, _, _, _, _, settle = side_quotes(w)          # (W, 2, n); NO bid = 1 - YES ask, NO ask = 1 - YES bid
    K = np.arange(k_lo, k_hi + 1)
    nk = len(K)
    t_grid = w.open_ms[:, None] + MIN * K[None, :]          # (W, nk)
    sidx = join_spot(t_grid.ravel(), sp_t).reshape(W, nk)
    found = sidx >= 0
    yb, ya = w.bid[:, K], w.ask[:, K]
    book = np.isfinite(yb) & np.isfinite(ya)
    gate = book & found
    if cfg['mid_band'] is not None:
        mid = (yb + ya) / 2
        lo, hi = cfg['mid_band']
        gate &= (mid >= lo - EPS) & (mid <= hi + EPS)
    side_ask = ask[:, :, K]                                  # (W, 2, nk)
    inband = np.isfinite(side_ask) & (side_ask >= PRICE_BAND[0] - EPS) & (side_ask <= PRICE_BAND[1] + EPS)
    ok = inband & gate[:, None, :]                           # (W, 2, nk)
    row = ok.any(axis=1)
    no_spot = int((book & ~found).sum())
    log(f'{ct}-{asset}: {int(book.sum())} decision minutes with a book, {no_spot} without a spot row (dropped), '
        f'{int(row.sum())} rows with a tradable side')

    sides = SIDES[ct]
    outs = {}
    shape = (W, 2, nk)
    for name, dt, fill in (('trade', np.float32, np.nan), ('best', np.float32, np.nan), ('hit', np.uint8, 0), ('hold', np.uint16, 0),
                           ('trade2', np.float32, np.nan), ('hit2', np.uint8, 0), ('tradeLat', np.float32, np.nan),
                           ('tradeCost', np.float32, np.nan), ('tradeSettle', np.float32, np.nan)):
        outs[name] = np.full(shape, fill, dtype=dt)
    for s in (0, 1):
        for ki, k in enumerate(K):
            sel = np.nonzero(ok[:, s, ki])[0]
            if not len(sel):
                continue
            b, st, a = bid[sel, s, :], settle[sel, s], ask[sel, s, k]
            r = simulate(b, st, int(k), a, stake, n, max_c)
            outs['trade'][sel, s, ki] = r['trade']; outs['best'][sel, s, ki] = r['best']
            outs['hit'][sel, s, ki] = r['hit']; outs['hold'][sel, s, ki] = r['hold']
            outs['tradeSettle'][sel, s, ki] = r['trade_settle']
            r2 = simulate(b, st, int(k), a, stake2, n, max_c)
            outs['trade2'][sel, s, ki] = r2['trade']; outs['hit2'][sel, s, ki] = r2['hit']
            if k + 1 <= n - 1:
                outs['tradeLat'][sel, s, ki] = simulate(b, st, int(k) + 1, ask[sel, s, k + 1], stake, n, max_c)['trade']
            outs['tradeCost'][sel, s, ki] = simulate(b, st, int(k), a + COST_STRESS, stake, n, max_c)['trade']

    # Contract features on the (W, nk) grid.
    smid = (bid + ask) / 2                                   # (W, 2, n) side mids
    feats: dict[str, np.ndarray] = {}
    feats['k_tau'] = np.broadcast_to(tau_bucket(K, k_lo, k_hi)[None, :], (W, nk))
    feats['k_spread'] = spread_bucket(ya - yb)
    kv = np.nan_to_num(w.kvol)
    vol5 = np.empty((W, nk))
    for ki, k in enumerate(K):
        a0 = max(1, k - 4)
        vol5[:, ki] = kv[:, a0:k + 1].sum(axis=1) * 5.0 / (k - a0 + 1)
    S = np.where(found, sp_close[np.where(found, sidx, 0)], np.nan)
    rv60 = np.where(found, np.asarray(sp_rv60, dtype=np.float64)[np.where(found, sidx, 0)], np.nan)
    sig = rv60 / np.sqrt(60.0)
    tau = (n - K)[None, :].astype(np.float64)
    with np.errstate(divide='ignore', invalid='ignore'):
        z = np.log(S / w.strike[:, None]) / (sig * np.sqrt(tau))
    z = np.where(np.isfinite(z), z, np.nan)
    fair = ndtr(z)
    for s, sl in ((0, 'Y'), (1, 'N')):
        feats[f'k_price@{sl}'] = price_bucket(side_ask[:, s, :])
        for m in (1, 3, 5):
            prev = K - m
            d = np.where(prev[None, :] >= 1, smid[:, s, K] - smid[:, s, np.maximum(prev, 0)], np.nan)
            feats[f'k_dmid{m}@{sl}'] = dmid_state(d)
        feats[f'k_z@{sl}'] = edge_bucket(z if s == 0 else -z, Z_EDGES)
        fs = fair if s == 0 else 1 - fair
        feats[f'k_fair@{sl}'] = edge_bucket(fs - smid[:, s, K], GAP_EDGES)

    # Rows: decisions with a tradable side, sorted by t (then market index).
    wi, ki = np.nonzero(row)
    t = t_grid[wi, ki]
    order = np.lexsort((wi, t))
    wi, ki, t = wi[order], ki[order], t[order]
    R = len(t)
    if not R:
        raise SystemExit('no decision rows')
    ridx = sidx[wi, ki]
    rv_t = np.asarray(sp_rv, dtype=np.int8)[ridx]

    v5 = vol5[wi, ki]
    vedges, vhow = vol_edges(v5, dev_rows(t, h))
    kfeat = {'k_tau': feats['k_tau'][wi, ki], 'k_spread': feats['k_spread'][wi, ki], 'k_vol5': vol_bucket(v5, vedges)}
    for name in ('k_price', 'k_dmid1', 'k_dmid3', 'k_dmid5', 'k_z', 'k_fair'):
        for sl in ('Y', 'N'):
            kfeat[f'{name}@{sl}'] = feats[f'{name}@{sl}'][wi, ki]
    kmeta = contract_feature_meta(kind, vedges, vhow)
    names = [f['name'] for f in kmeta]
    clash = set(names) & {f['name'] for f in sp_feats}
    if clash:
        raise ValueError(f'feature name clash with the spot part: {sorted(clash)}')
    Fs = len(sp_feats)
    X = np.empty((R, Fs + len(names)), dtype=np.int8)
    for c0 in range(0, R, 100_000):                         # chunked gather from the memory-mapped spot X
        c1 = min(R, c0 + 100_000)
        X[c0:c1, :Fs] = np.asarray(sp_X[ridx[c0:c1]], dtype=np.int8)
    for j, name in enumerate(names):
        X[:, Fs + j] = kfeat[name]
    side_features = {sl: [Fs + j for j, f in enumerate(kmeta) if f.get('side') == sl] for sl in ('Y', 'N')}

    tb = kfeat['k_tau'].astype(np.int16)
    rv_slot = np.where(rv_t >= 0, rv_t, 3).astype(np.int16)
    _, event = np.unique(w.open_ms, return_inverse=True)
    arrays = {'t': t.astype(np.int64), 'group': wi.astype(np.int64), 'event': event[wi].astype(np.int64),
              'asset': np.zeros(R, dtype=np.int8), 'kmin': K[ki].astype(np.uint8), 'X': X, 'rv': rv_t,
              'hour': ((t // 3_600_000) % 24).astype(np.int8)}
    for s, sl in enumerate(sides):
        oks = ok[wi, s, ki]
        pb = kfeat[f'k_price@{sl}'].astype(np.int16)
        arrays[f'stratum_{sl}'] = np.where(oks & (pb >= 0), (pb * 3 + tb) * 4 + rv_slot, -1).astype(np.int16)
        arrays[key('ok', sl, h)] = oks.astype(np.uint8)
        for name in outs:
            arrays[key(name, sl, h)] = outs[name][wi, s, ki]

    meta = {
        'ct': ct, 'scope': asset, 'assets': [asset], 'sides': sides, 'horizons': [h], 'size_usd': stake, 'size2_usd': stake2,
        'step_min': STEP_MIN[ct], 'code_sha': code_sha or _code_sha(), 'features': sp_feats + kmeta,
        'side_features': side_features,
        'strata_desc': 'stratum_<s> = (k_price@<s> x 3 + k_tau) x 4 + RV slot: 8 side-ask buckets x 3 tau buckets x '
                       '(RV tercile 0 LOW / 1 MID / 2 HIGH, or 3 when the spot part has no RV tercile); -1 = side not tradable',
        'notes': NOTES.format(n=n, k_lo=k_lo, k_hi=k_hi, band=('; hourly: YES mid in [0.10, 0.90]' if kind == 60 else ''),
                              last=int(np.argmin(tp_zone(n))), n1=n - 1),
        'window_min': n, 'entry_k': [k_lo, k_hi], 'price_band': list(PRICE_BAND), 'max_contracts': max_c,
        'cost_stress_usd': COST_STRESS, 'spot_part': os.path.basename(os.path.normpath(spot_dir)),
        'spot_code_sha': sp.meta.get('code_sha'), 'series': series,
        'extra_arrays': {'event': 'int64 event index (markets sharing an open time: the strikes of one hourly event)',
                         'kmin': 'uint8 decision minute k within the window'},
        'counts': {'windows': int(W), 'rows': int(R), 'decision_minutes_without_spot': no_spot},
    }
    path = os.path.join(out_root, f'{ct}-{asset}')
    write_part(path, meta, arrays)
    log(f'{ct}-{asset}: wrote {R} rows x {X.shape[1]} features to {path}')
    return path


NOTES = ('Decisions t_k = open + 60 s x k, k = {k_lo}..{k_hi} of a {n}-minute window (quote = candle k close, allpairs '
         'load_kalshi){band}. Sides Y (buy YES at the ask) and N (buy NO at 1 - YES bid); side ask in [0.10, 0.90]; '
         'C = min(floor(size / ask), 250); taker fee both legs (allpairs fees = bot/fees.ts), no settlement fee. '
         'Exit: take-profit at the bid at the first minute j > k with net >= $5 and tau_j > 10% of the window; otherwise at '
         'minute N-1 ride to settlement if the net at its bid is > 0, else sell there (no book at N-1: settles). Decision '
         'minutes {last}..{n1} never take profit. best = max(every bid sale j in (k, N-1], settlement). hold in '
         'minutes (settlement = to the close). tradeLat = entry at k+1 (NaN past N-1); tradeCost = entry price + 1c. '
         'Prices are rounded to 4 decimals before sizing and fees (the bot rounds NO prices so; 1 - 0.84 in float would '
         'buy one contract too few). KNOWN LIMIT (prereg vs live): the sale at the final candle N-1 is 60 s before the '
         'close, where the live bot (relaxed cadence, STRATEGY_NO_EXIT_BEFORE_CLOSE_SEC 60) cannot exit, so live a losing '
         'position settles; tradeSettle = the same trade with every non-take-profit exit settled (sensitivity only, never '
         'selected on). '
         'SIDE FEATURES: columns named <feature>@Y / <feature>@N are side-relative (the side\'s own ask bucket, mid change, '
         'z, fair - mid); meta.side_features lists per side the X columns that apply to it, and a column listed in neither '
         'applies to both sides (spot features, k_tau, k_spread, k_vol5). Mining side s reads the unlisted columns plus '
         'side_features[s], with the @s suffix stripped for a name shared across sides. Spot X columns are the spot part '
         'row whose t_end equals t (rows without one are dropped). group = market index (one per strike); event.npy groups '
         'the strikes of one event.')


def contract_feature_meta(kind: int, vedges, vhow: str) -> list:
    k_lo, k_hi = KINDS[kind]['k']
    lv = lambda L: list(range(L))
    both = [
        {'name': 'k_tau', 'kind': 'bucket', 'levels': lv(3),
         'desc': f'decision minute in thirds of the entry window k = {k_lo}..{k_hi}: floor(3 (k - {k_lo}) / {k_hi - k_lo + 1}); 0 = most time left'},
        {'name': 'k_spread', 'kind': 'bucket', 'levels': lv(4), 'desc': 'YES ask - YES bid (= the NO spread): <=1c, <=2c, <=5c, >5c'},
        {'name': 'k_vol5', 'kind': 'bucket', 'levels': lv(5),
         'desc': 'contracts traded over minutes max(1, k-4)..k scaled to 5 minutes: 0 = none, 1..4 split at '
                 f'{[round(x, 3) for x in vedges]} ({vhow})'},
    ]
    per = [
        ('k_price', 'bucket', lv(8), "the side's ask: 0 = [0.10, 0.20) .. 7 = [0.80, 0.90]; -1 outside the band"),
        ('k_dmid1', 'state', [-1, 0, 1], "the side's mid change over 1 minute: +1 >= +1c, -1 <= -1c, 0 otherwise or NA"),
        ('k_dmid3', 'state', [-1, 0, 1], "the side's mid change over 3 minutes (+-1c)"),
        ('k_dmid5', 'state', [-1, 0, 1], "the side's mid change over 5 minutes (+-1c)"),
        ('k_z', 'bucket', lv(7), 'side-relative z = ln(S/K) / (sigma sqrt(tau)) (YES z, NO -z), sigma per minute = spot rv60 / '
                                 f'sqrt(60), tau = minutes to close; split at {list(Z_EDGES)}'),
        ('k_fair', 'bucket', lv(7), f'fair - side mid, fair = Phi(z) for YES, 1 - Phi(z) for NO; split at {list(GAP_EDGES)}'),
    ]
    out = list(both)
    for name, kd, levels, desc in per:
        for sl in ('Y', 'N'):
            out.append({'name': f'{name}@{sl}', 'kind': kd, 'levels': levels, 'desc': desc, 'side': sl, 'base': name})
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description='Build parts/pp15-<A>/ or parts/pp60-<A>/ (oracle SPEC 2b).')
    ap.add_argument('--kind', type=int, required=True, choices=(15, 60))
    ap.add_argument('--history', required=True, help='directory holding kalshi/KX<A>15M or kalshi/KX<A>D day files')
    ap.add_argument('--spot', required=True, help='the spot part directory parts/spot-<A>')
    ap.add_argument('--asset', required=True)
    ap.add_argument('--out', required=True, help='parts root; writes <out>/pp15-<A>/ or <out>/pp60-<A>/')
    ap.add_argument('--code-sha', default=None)
    a = ap.parse_args(argv)
    build(a.kind, a.history, a.spot, a.asset, a.out, a.code_sha)


if __name__ == '__main__':
    main()
