"""The ten checks of research/heat_direction/PREREG.md section 3, as code. Pure numpy: calls in, a score out.

A `Calls` object is one row per call, already decided by a rule from bars up to t-1 (the causality rule is the caller's
job and the cut test proves it). Moves are in price steps (the engine's tick for the coin), so the 1.5 step flat band
needs no price. The thresholds below are the pre-registered ones; test_rubric checks they match the document.

    score(calls, inv, lo, hi, blocks)  ->  dict with `checks` (ten rows), `total`, `gate`, `pass`, `core8`, `voided`

`inv` holds the calls the TA layer invalidated, scored as if made (check 10). `calls.conf` is the TA-confirmed flag
(check 9); None means no TA layer, so checks 9 and 10 score 0.
"""
import dataclasses
import datetime as dt

import numpy as np

DAY = 86_400_000
FLAT_STEPS = 1.5                 # a move under 1.5 steps is flat: excluded and counted
SEED = 20261119                  # the day-cluster bootstrap
BOOT = 2000
Z90, Z975 = 1.2816, 1.96
NAIVE_KS = (1, 5, 15, 60)        # follow / fade of the last k minute move

T = dict(                        # pre-registered thresholds
    level=0.55, lower=0.50, naive_gap=0.02, coin=0.53, week_share=0.65, side=0.52, late=0.53, ta_lift=0.03, inv_max=0.50,
    flat_void=0.05)
FLOORS = dict(pooled=800, coin=300, week_calls=20, weeks=8, block=150, side=150, ta=150)
SCORED_COINS = ('BTC', 'ETH')
NAMES = ['level', 'not_luck', 'beats_naive', 'both_coins', 'weeks', 'blocks', 'both_sides', 'one_minute_late',
         'ta_confirms', 'ta_invalidates']


@dataclasses.dataclass
class Calls:
    ts: np.ndarray               # entry minute (ms, the open of minute t)
    coin: np.ndarray             # 'BTC' / 'ETH' ...
    side: np.ndarray             # +1 UP, -1 DOWN
    move: np.ndarray             # open[t+15] - open[t], in steps
    move_late: np.ndarray = None  # open[t+16] - open[t+1], in steps
    past: dict = None            # k -> sign of the move over the k minutes before t (+1, 0, -1), for the naive rules
    conf: np.ndarray = None      # TA-confirmed (bool) or None

    def __len__(self):
        return len(self.ts)

    @property
    def day(self):
        return (np.asarray(self.ts, np.int64) // DAY)

    def pick(self, m):
        f = lambda a: None if a is None else np.asarray(a)[m]
        return Calls(f(self.ts), f(self.coin), f(self.side), f(self.move), f(self.move_late),
                     None if self.past is None else {k: np.asarray(v)[m] for k, v in self.past.items()}, f(self.conf))


def right(side, move):
    """(decided, right): a call is right when the move agrees and is at least FLAT_STEPS, wrong when it disagrees at that size."""
    move = np.asarray(move, float)
    dec = np.abs(move) >= FLAT_STEPS
    return dec, dec & (np.sign(move) == np.asarray(side))


def _rate(h):
    return float(np.mean(h)) if len(h) else float('nan')


def cluster_se(h, day):
    """Ratio-estimator standard error of a hit rate when calls cluster by UTC day."""
    h = np.asarray(h, float)
    if len(h) == 0:
        return float('nan')
    u, inv = np.unique(day, return_inverse=True)
    dh = np.bincount(inv, weights=h)
    dn = np.bincount(inv).astype(float)
    p = h.mean()
    return float(np.sqrt(np.sum((dh - p * dn) ** 2)) / len(h))


def boot_lower(h, day, q=0.025, seed=SEED, reps=BOOT):
    """The q quantile of the pooled hit rate over `reps` resamples of whole UTC days."""
    h = np.asarray(h, float)
    u, inv = np.unique(day, return_inverse=True)
    dh = np.bincount(inv, weights=h)
    dn = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(u), size=(reps, len(u)))
    return float(np.quantile(dh[idx].sum(1) / dn[idx].sum(1), q))


def iso_week(day):
    """Monday-start ISO week id (days since the epoch of that Monday) of each epoch-day number."""
    d = np.asarray(day, np.int64)
    return d - ((d + 3) % 7)          # 1970-01-01 was a Thursday


def month_id(day):
    return np.array([(lambda x: x.year * 12 + x.month - 1)(dt.date.fromordinal(int(d) + 719163)) for d in day]) \
        if len(day) else np.array([], int)


def _naive(c, dec, hit_all_sides):
    """Hit rate of the ten naive rules on the candidate's decided calls: follow / fade of the last 1, 5, 15, 60 minute move
    (undefined where that move is 0, so those calls are left out for that rule), always UP and always DOWN."""
    if c.past is None or any(k not in c.past for k in NAIVE_KS):
        raise ValueError('calls need the sign of the last 1, 5, 15 and 60 minute move for the naive rules')
    out = {}
    move = np.asarray(c.move, float)
    for k in NAIVE_KS:
        p = np.asarray(c.past[k])[dec]
        m = move[dec]
        ok = p != 0
        for name, s in (('follow', 1), ('fade', -1)):
            out[f'{name}{k}'] = _rate(np.sign(m[ok]) == s * p[ok]) if ok.any() else float('nan')
    m = move[dec]
    out['up'] = _rate(m > 0)
    out['down'] = _rate(m < 0)
    return out


def score(calls: Calls, inv, lo: int, hi: int, blocks='month', floors=None, seed=SEED) -> dict:
    """Score `calls` on the window [lo, hi) (ms). blocks: 'month' (calendar months, VAL) or an int n (n equal parts by day, FINAL)."""
    F = dict(FLOORS if floors is None else floors)
    c = calls
    n_all = len(c)
    dec, hit = right(c.side, c.move)
    flat_share = float(1 - dec.mean()) if n_all else 1.0
    cd = c.pick(dec)
    h = hit[dec]
    n = len(h)
    day = cd.day
    rate = _rate(h)
    res = []

    def put(name, passed, value, floor_ok=True, **extra):
        res.append(dict(id=len(res) + 1, name=name, passed=bool(passed and floor_ok), floor_ok=bool(floor_ok), value=value, **extra))

    # 1 level, 2 not luck
    put('level', rate >= T['level'], rate, n >= F['pooled'])
    lb = boot_lower(h, day, seed=seed) if n else float('nan')
    put('not_luck', lb > T['lower'], lb, n >= F['pooled'])
    # 3 beats the best naive rule
    nv = _naive(c, dec, hit)
    best = max((v for v in nv.values() if v == v), default=float('nan'))
    put('beats_naive', (rate - best) >= T['naive_gap'], rate - best if best == best else float('nan'), n >= F['pooled'], best_rule=max(nv, key=lambda k: -1 if nv[k] != nv[k] else nv[k]))
    # 4 both coins
    cv = {k: _rate(h[cd.coin == k]) for k in SCORED_COINS}
    cn = {k: int((cd.coin == k).sum()) for k in SCORED_COINS}
    put('both_coins', all(v >= T['coin'] for v in cv.values()), cv, all(cn[k] >= F['coin'] for k in SCORED_COINS))
    # 5 full ISO weeks: a quiet week fails, never dropped
    wk = iso_week(day)
    d_lo, d_hi = lo // DAY, (hi + DAY - 1) // DAY               # days [d_lo, d_hi)
    first_mon = int(iso_week(np.array([d_lo]))[0])
    first_mon = first_mon if first_mon >= d_lo else first_mon + 7
    weeks = [w for w in range(first_mon, d_hi - 6, 7)]
    ok = [(wk == w).sum() >= F['week_calls'] and h[wk == w].mean() > 0.5 for w in weeks]
    share = float(np.mean(ok)) if ok else float('nan')
    put('weeks', share >= T['week_share'], share, len(weeks) >= F['weeks'], weeks=len(weeks))
    # 6 blocks
    if blocks == 'month':
        mid = month_id(day)
        ids = sorted(set(month_id(np.arange(d_lo, d_hi))))
        blk = mid
    else:
        n_b = int(blocks)
        blk = np.minimum((day - d_lo) * n_b // max(d_hi - d_lo, 1), n_b - 1)
        ids = list(range(n_b))
    bv = [(h[blk == b].mean() if (blk == b).sum() else float('nan'), int((blk == b).sum())) for b in ids]
    put('blocks', all(v == v and v > 0.5 for v, _ in bv), [round(v, 4) if v == v else None for v, _ in bv],
        all(k >= F['block'] for _, k in bv) and len(bv) >= (3 if blocks == 'month' else int(blocks)))
    # 7 both sides
    sv = {s: _rate(h[cd.side == s]) for s in (1, -1)}
    sn = {s: int((cd.side == s).sum()) for s in (1, -1)}
    put('both_sides', all(v >= T['side'] for v in sv.values()), {'up': sv[1], 'down': sv[-1]}, all(k >= F['side'] for k in sn.values()))
    # 8 one minute late (same calls, entry at t+1)
    if c.move_late is not None:
        dl, hl = right(c.side, c.move_late)
        put('one_minute_late', _rate(hl[dl]) >= T['late'], _rate(hl[dl]), int(dl.sum()) >= F['pooled'])
    else:
        put('one_minute_late', False, None, False)
    # 9 TA confirms
    if c.conf is not None:
        cf = np.asarray(cd.conf, bool)
        a, b = h[cf], h[~cf]
        if len(a) and len(b):
            d9 = _rate(a) - _rate(b)
            se = float(np.hypot(cluster_se(a, day[cf]), cluster_se(b, day[~cf])))
            put('ta_confirms', d9 >= T['ta_lift'] and d9 - Z90 * se > 0, d9, len(a) >= F['ta'] and len(b) >= F['ta'])
        else:
            put('ta_confirms', False, None, False)
    else:
        put('ta_confirms', False, None, False)
    # 10 TA invalidates
    if inv is not None and len(inv):
        di, hi_ = right(inv.side, inv.move)
        ih = hi_[di]
        iday = inv.day[di]
        if len(ih) and len(h):
            d10 = rate - _rate(ih)
            se = float(np.hypot(cluster_se(h, day), cluster_se(ih, iday)))
            put('ta_invalidates', _rate(ih) <= T['inv_max'] and d10 >= T['ta_lift'] and d10 - Z90 * se > 0, d10, len(ih) >= F['ta'])
        else:
            put('ta_invalidates', False, None, False)
    else:
        put('ta_invalidates', False, None, False)
    total = sum(r['passed'] for r in res)
    gate = all(r['passed'] for r in res[:3])
    return dict(checks=res, total=int(total), gate=bool(gate), passed=bool(gate and total >= 9),
                core8=int(sum(r['passed'] for r in res[:8])), n_decided=int(n), n_calls=int(n_all),
                flat_share=flat_share, voided=bool(flat_share > T['flat_void']), hit_rate=rate, naive=nv)
