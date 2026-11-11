"""Synthetic Price Prediction parts plus OR-H3 cut-label sidecars for the tests of oracle/cut.py. Nothing here is real data.

Windows: YES mid paths with momentum (a side that starts falling tends to keep falling, so a loser cut has something to
find), 1-2c spreads, settled on the final mid. Parts follow SPEC 1 / pp.py exactly where cut.py reads them (t sorted,
group / event / kmin, ok, stratum, X with the side-relative k_price / k_dmid3 / k_z columns and meta.side_features,
trade / hold / tradeSettle from oracle.pp.simulate); the sidecar is written by oracle.cut.write_sidecar (win = group).
Rows span discovery A and B and the whole HO-1 hold (Apr 18 - Nov 4 2026), so every split is populated.
"""
from __future__ import annotations

import os

import numpy as np
from scipy.special import ndtri

from .common import DAY, HORIZONS, MAX_CONTRACTS, MIN, SIZE, ms, write_part
from .cut import write_sidecar
from .common import Part
from .pp import KINDS, PRICE_BAND, Z_EDGES, dmid_state, edge_bucket, price_bucket, simulate, tau_bucket

START, END = ms('2026-04-18'), ms('2026-11-05')
FEATS_SPOT = [{'name': 'sx_dummy', 'kind': 'state', 'levels': [-1, 0, 1], 'desc': 'fixture'}]


def paths(rng, W: int, n: int, momentum: float, vol: float):
    """YES (bid, ask) (W, n) and YES settlement (W,)."""
    mid = np.empty((W, n))
    m = rng.uniform(0.25, 0.75, W)
    d = np.zeros(W)
    for j in range(n):
        d = momentum * d + rng.normal(0, vol, W)
        m = np.clip(m + d, 0.03, 0.97)
        mid[:, j] = m
    half = rng.choice([0.005, 0.01], size=(W, 1))
    bid = np.round(mid - half, 2)
    ask = np.round(mid + half + 0.001, 2)
    bid = np.clip(bid, 0.01, 0.98)
    ask = np.maximum(np.clip(ask, 0.02, 0.99), np.round(bid + 0.01, 2))
    gone = rng.random((W, n)) < 0.01
    bid[gone], ask[gone] = np.nan, np.nan
    settle = (mid[:, -1] + rng.normal(0, 0.02, W) > 0.5).astype(np.float64)
    return bid, ask, settle


def make_part(root: str, cut_root: str, ct: str, asset: str, per_day: int = 6, seed: int = 1, momentum: float = 0.55,
              vol: float = 0.025, strikes: int = 1) -> str:
    """parts/<ct>-<asset>/ and its sidecar <cut_root>/<ct>-<asset>/ over Apr 18 - Nov 4 2026."""
    kind = {'pp15': 15, 'pp60': 60}[ct]
    cfg = KINDS[kind]
    n = cfg['n']
    k_lo, k_hi = cfg['k']
    rng = np.random.default_rng(seed)
    days = (END - START) // DAY
    step = DAY // per_day
    opens = np.array([START + d * DAY + i * step for d in range(days) for i in range(per_day)], dtype=np.int64)
    ev = np.repeat(np.arange(len(opens)), strikes)
    opens = np.repeat(opens, strikes)
    W = len(opens)
    ybid, yask, yset = paths(rng, W, n, momentum, vol)
    bid = np.stack([ybid, 1 - yask], axis=1)
    ask = np.stack([yask, 1 - ybid], axis=1)
    settle = np.stack([yset, 1 - yset], axis=1)
    K = np.arange(k_lo, k_hi + 1)
    nk = len(K)
    side_ask = ask[:, :, K]
    book = np.isfinite(ybid[:, K]) & np.isfinite(yask[:, K])
    gate = book.copy()
    if cfg['mid_band'] is not None:
        mid = (ybid[:, K] + yask[:, K]) / 2
        gate &= (mid >= 0.10) & (mid <= 0.90)
    ok = np.isfinite(side_ask) & (side_ask >= PRICE_BAND[0] - 1e-9) & (side_ask <= PRICE_BAND[1] + 1e-9) & gate[:, None, :]
    row = ok.any(axis=1)
    h = HORIZONS[ct][0]
    stake, max_c = SIZE[ct], MAX_CONTRACTS[ct]
    out = {nm: np.full((W, 2, nk), np.nan) for nm in ('trade', 'hold', 'tradeSettle')}
    for s in (0, 1):
        for ki, k in enumerate(K):
            sel = np.nonzero(ok[:, s, ki])[0]
            if not len(sel):
                continue
            r = simulate(bid[sel, s, :], settle[sel, s], int(k), ask[sel, s, k], stake, n, max_c)
            out['trade'][sel, s, ki] = r['trade']; out['hold'][sel, s, ki] = r['hold']; out['tradeSettle'][sel, s, ki] = r['trade_settle']
    smid = (bid + ask) / 2
    wi, ki = np.nonzero(row)
    t = opens[wi] + MIN * K[ki]
    o = np.lexsort((wi, t))
    wi, ki, t = wi[o], ki[o], t[o]
    R = len(t)
    feats = list(FEATS_SPOT)
    cols = {'sx_dummy': rng.integers(-1, 2, R)}
    feats.append({'name': 'k_tau', 'kind': 'bucket', 'levels': [0, 1, 2], 'desc': 'fixture'})
    tb = tau_bucket(K[ki], k_lo, k_hi)
    cols['k_tau'] = tb
    for s, sl in ((0, 'Y'), (1, 'N')):
        cols[f'k_price@{sl}'] = price_bucket(ask[wi, s, K[ki]])
        prev = K[ki] - 3
        d = np.where(prev >= 1, smid[wi, s, K[ki]] - smid[wi, s, np.maximum(prev, 0)], np.nan)
        cols[f'k_dmid3@{sl}'] = dmid_state(d)
        z = ndtri(np.clip(smid[wi, s, K[ki]], 0.01, 0.99)) * 1.2 + rng.normal(0, 0.2, R)
        cols[f'k_z@{sl}'] = edge_bucket(z, Z_EDGES)
    for nm, kd, lv in (('k_price', 'bucket', list(range(8))), ('k_dmid3', 'state', [-1, 0, 1]), ('k_z', 'bucket', list(range(7)))):
        for sl in ('Y', 'N'):
            feats.append({'name': f'{nm}@{sl}', 'kind': kd, 'levels': lv, 'desc': 'fixture', 'side': sl, 'base': nm})
    X = np.stack([np.asarray(cols[f['name']], dtype=np.int8) for f in feats], axis=1)
    side_features = {sl: [j for j, f in enumerate(feats) if f.get('side') == sl] for sl in ('Y', 'N')}
    rv = rng.integers(0, 3, R).astype(np.int8)
    arrays = {'t': t.astype(np.int64), 'group': wi.astype(np.int64), 'event': ev[wi].astype(np.int64), 'asset': np.zeros(R, np.int8),
              'kmin': K[ki].astype(np.uint8), 'X': X, 'rv': rv, 'hour': ((t // 3_600_000) % 24).astype(np.int8)}
    for s, sl in enumerate(('Y', 'N')):
        oks = ok[wi, s, ki]
        pb = cols[f'k_price@{sl}'].astype(np.int16)
        arrays[f'stratum_{sl}'] = np.where(oks & (pb >= 0), (pb * 3 + tb) * 4 + rv, -1).astype(np.int16)
        arrays[f'ok_{sl}{h}'] = oks.astype(np.uint8)
        arrays[f'hit_{sl}{h}'] = (out['trade'][wi, s, ki] >= 5).astype(np.uint8)
        arrays[f'trade_{sl}{h}'] = out['trade'][wi, s, ki].astype(np.float32)
        arrays[f'hold_{sl}{h}'] = np.nan_to_num(out['hold'][wi, s, ki]).astype(np.uint16)
        arrays[f'tradeSettle_{sl}{h}'] = out['tradeSettle'][wi, s, ki].astype(np.float32)
    meta = {'ct': ct, 'scope': asset, 'assets': [asset], 'sides': ['Y', 'N'], 'horizons': [h], 'size_usd': stake, 'size2_usd': 10.0,
            'step_min': 1, 'code_sha': 'fixture', 'features': feats, 'side_features': side_features, 'window_min': n,
            'notes': 'synthetic (oracle/fixtures_cut.py), not real data'}
    path = os.path.join(root, f'{ct}-{asset}')
    write_part(path, meta, arrays)
    part = Part(path)
    write_sidecar(part, path, cut_root, opens, bid, ask, settle, np.asarray(part['group'], dtype=np.int64),
                  {'rows': R, 'direct': R, 'groups_rematched': 0, 'groups_unmatched': 0, 'rows_unmatched': 0}, n, 'fixture',
                  log=lambda m: None)
    return path


def make(root: str, per_day: int = 6, seed: int = 1) -> dict:
    """pp15 BTC / ETH and pp60 BTC (2 strikes per event) parts + sidecars under root/parts and root/cut."""
    parts, cut = os.path.join(root, 'parts'), os.path.join(root, 'cut')
    out = {'parts': parts, 'cut': cut, 'paths': []}
    for i, (ct, a, k) in enumerate((('pp15', 'BTC', 1), ('pp15', 'ETH', 1), ('pp60', 'BTC', 2))):
        out['paths'].append(make_part(parts, cut, ct, a, per_day=per_day if ct == 'pp15' else max(2, per_day // 2), seed=seed + i, strikes=k))
    return out
