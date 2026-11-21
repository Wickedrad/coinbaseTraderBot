"""The direction rule's calls priced on Kalshi's own 15-minute quotes (Steven, Nov 21 2026: only recorded days, nothing waits for the future).

The rule (a frozen cell and side of the sweep) says up or down at the open of a minute. This module takes those calls with the 15-minute lockout, finds the
Kalshi 15-minute window each call falls in, and trades it the way a bot would: buy the called side at the ask of the first minute that has a two-sided book,
hold to the settlement the exchange recorded, pay the taker fee. It reports what that earns per contract, so the answer is dollars, not a coin direction.

  entry quote   the YES ask (called up) or 1 - the YES bid (called down) at decision time t_k, k = max(minute of the quarter hour, 1) + delay
                (k = 0 has no usable book: python/allpairs/data.py market_to_rows)
  settlement    the recorded result of the window (YES = 1)
  fee           the taker fee of bot/fees.ts on a $10 stake (python/allpairs/fees.py), per contract
  placebos      the same calls with the side flipped, and with a random side (the same call times)
"""
import numpy as np

from allpairs import data as KD
from allpairs import fees as KF
from dirsweep import grid as G
from dirsweep import replay as R

STAKE = 10.0
Z95 = 1.959963984540054


def calls(m: dict, coin: str, rid: int, lo: int, hi: int, minutes: int = 15) -> dict:
    """The calls of rule `rid` on one coin's grid over days [lo, hi), after the lockout: minute-open time, side (+1 up, -1 down), day, minute of the quarter."""
    rp = R.Replayer(m, G.STEP[coin], nd=hi)
    rows, sgn = rp.rows(rid)
    rows = R.lockout(rows, minutes)
    d = rp.day[rows]
    keep = (d >= lo) & (d < hi)
    rows, d = rows[keep], d[keep]
    side = np.where(sgn[rows] > 0, -1, 1)              # fade: against the last-k move
    if int(rid) % 2:
        side = -side                                    # odd rule ids follow it
    t = m['t0'] + rows.astype(np.int64) * G.MIN
    return {'t': t, 'side': side.astype(np.int8), 'day': d - lo, 'mq': ((t // G.MIN) % 15).astype(np.int64), 'e': rows.astype(np.int64)}


def index(w: KD.Windows) -> dict:
    """(asset name, window open ms) -> window row."""
    return {(w.assets[int(a)], int(o)): i for i, (a, o) in enumerate(zip(w.asset, w.open_ms))}


def price(w: KD.Windows, idx: dict, coin: str, cl: dict, delay: int = 0) -> dict:
    """Entry price, outcome and fee of each call. `ok` is False where no window or no two-sided book exists at the entry minute."""
    n = len(cl['t'])
    out = {'ok': np.zeros(n, bool), 'p': np.full(n, np.nan), 'win': np.zeros(n)}
    for i in range(n):
        mq = int(cl['mq'][i])
        j = idx.get((coin, int(cl['t'][i]) - mq * G.MIN))
        k = max(mq, 1) + delay
        if j is None or k >= w.n:
            continue
        bid, ask = w.bid[j, k], w.ask[j, k]
        if not (np.isfinite(bid) and np.isfinite(ask)):
            continue
        up = cl['side'][i] > 0
        p = ask if up else 1.0 - bid
        if not 0.0 < p < 1.0:
            continue
        out['ok'][i], out['p'][i] = True, p
        out['win'][i] = float(w.settle[j] == (1.0 if up else 0.0))
    return out


def net(pr: dict) -> np.ndarray:
    """Net dollars per contract after the taker fee, a $10 stake, whole contracts."""
    p = pr['p']
    cnt = np.floor(STAKE / np.where(np.isfinite(p) & (p > 0), p, 1.0))
    cnt = np.maximum(cnt, 1.0)
    fee = KF.taker_fee(cnt, np.where(np.isfinite(p), p, 0.5)) / cnt
    return pr['win'] - p - fee


def _cluster(x: np.ndarray, day: np.ndarray) -> tuple:
    """Mean of x with the day-cluster standard error (ratio estimator)."""
    N = len(x)
    if N == 0:
        return None, None, 0
    mean = x.mean()
    ds = np.unique(day)
    if len(ds) < 2:
        return float(mean), None, len(ds)
    s = np.array([x[day == d].sum() for d in ds])
    n = np.array([(day == d).sum() for d in ds], float)
    res = s - mean * n
    se = np.sqrt((res * res).sum() * len(ds) / (len(ds) - 1)) / N
    return float(mean), float(se), len(ds)


def summarize(cl: dict, pr: dict, extra_days: dict = None) -> dict:
    ok = pr['ok']
    out = {'calls': int(len(ok)), 'priced': int(ok.sum())}
    if not ok.any():
        return out
    x, day = net(pr)[ok], cl['day'][ok]
    mean, se, nd = _cluster(x, day)
    out.update({'hit': float(pr['win'][ok].mean()), 'price': float(pr['p'][ok].mean()),
                'net_c': None if mean is None else round(100 * mean, 3),
                'net_lo_c': None if se is None else round(100 * (mean - Z95 * se), 3),
                'net_hi_c': None if se is None else round(100 * (mean + Z95 * se), 3), 'days': nd,
                'net_per_trade_usd': round(float((x * np.floor(STAKE / pr['p'][ok])).mean()), 4)})
    return out


def run(grids: dict, windows: KD.Windows, rid: int, lo: int, hi: int, delays=(0, 1), seeds: int = 20, controls: dict = None,
        months: dict = None) -> dict:
    """Everything for one rule: its calls priced at each delay, split by coin and by half, the flipped side and the random side at the same times."""
    idx = index(windows)
    res = {'rid': int(rid), 'rule': G.describe(int(rid)), 'by_delay': {}}
    allcl = {c: calls(m, c, rid, lo, hi) for c, m in grids.items()}
    for dl in delays:
        pooled_cl, pooled_pr, per_coin = None, None, {}
        for c in grids:
            cl, pr = allcl[c], price(windows, idx, c, allcl[c], dl)
            per_coin[c] = summarize(cl, pr)
            pooled_cl = cl if pooled_cl is None else {k: np.concatenate([pooled_cl[k], cl[k]]) for k in cl}
            pooled_pr = pr if pooled_pr is None else {k: np.concatenate([pooled_pr[k], pr[k]]) for k in pr}
        o = {'pooled': summarize(pooled_cl, pooled_pr), 'by_coin': per_coin}
        ok = pooled_pr['ok']
        if ok.any():
            mid = int(np.median(pooled_cl['day'][ok]))
            for name, sel in (('first_half', pooled_cl['day'] <= mid), ('second_half', pooled_cl['day'] > mid)):
                o[name] = summarize({k: v[sel] for k, v in pooled_cl.items()}, {k: v[sel] for k, v in pooled_pr.items()})
            if months:
                for name, (a, b) in months.items():
                    sel = (pooled_cl['day'] >= a) & (pooled_cl['day'] < b)
                    if sel.any():
                        o.setdefault('by_month', {})[name] = summarize({k: v[sel] for k, v in pooled_cl.items()}, {k: v[sel] for k, v in pooled_pr.items()})
            # the same calls with the side flipped, and with a random side
            o['flipped'] = _priced(grids, windows, idx, allcl, dl, flip=True)
            rs = np.random.RandomState(1)
            rnd = []
            for _ in range(seeds):
                rnd.append(_priced(grids, windows, idx, allcl, dl, rand=rs)['net_c'])
            o['random_side_net_c'] = {'mean': round(float(np.mean([r for r in rnd if r is not None])), 3), 'min': min(r for r in rnd if r is not None),
                                      'max': max(r for r in rnd if r is not None)}
        res['by_delay'][str(dl)] = o
    return res


def _priced(grids, windows, idx, allcl, dl, flip=False, rand=None) -> dict:
    cls, prs = None, None
    for c in grids:
        cl = dict(allcl[c])
        if flip:
            cl['side'] = -cl['side']
        if rand is not None:
            cl['side'] = np.where(rand.rand(len(cl['side'])) < 0.5, -1, 1).astype(np.int8)
        pr = price(windows, idx, c, cl, dl)
        cls = cl if cls is None else {k: np.concatenate([cls[k], cl[k]]) for k in cl}
        prs = pr if prs is None else {k: np.concatenate([prs[k], pr[k]]) for k in pr}
    return summarize(cls, prs)


def basis(m: dict, w: KD.Windows, idx: dict, coin: str) -> dict:
    """How well does the coin's own 1-minute grid agree with Kalshi's recorded settlement? For every window of the coin: the sign of (open of minute 15 - open of
    minute 0) against YES/NO. A grid that is misaligned by a minute, or a settlement that does not follow the spot, shows up here before any rule is judged."""
    o = np.asarray(m['o'], float)
    js = [j for (c, _), j in idx.items() if c == coin]
    j = np.array(sorted(js), dtype=np.int64)
    e0 = (w.open_ms[j] - m['t0']) // G.MIN
    ok = (e0 >= 0) & (e0 + 15 < len(o))
    j, e0 = j[ok], e0[ok]
    mv = o[e0 + 15] - o[e0]
    dec = np.abs(mv) >= G.FLAT * G.STEP[coin]
    up = mv > 0
    agree = (up == (w.settle[j] == 1.0))
    # the strike against the spot at the open: how far apart, in the coin's own price steps
    gap = (w.strike[j] - o[e0]) / G.STEP[coin]
    return {'windows': int(len(j)), 'agree_open_to_close': float(agree[dec].mean()), 'decided': int(dec.sum()), 'strike_minus_spot_median_steps': float(np.median(gap)),
            'strike_minus_spot_abs_p90_steps': float(np.percentile(np.abs(gap), 90))}


def spot_and_contract(m: dict, w: KD.Windows, idx: dict, coin: str, cl: dict, pr: dict, horizon: int = 15) -> dict:
    """The same calls scored two ways: by the coin's move over the next 15 minutes from the call minute (what the sweep scored) and by the contract's recorded
    settlement (what the bot is paid). Where they disagree the sweep and the exchange are not measuring the same thing."""
    o = np.asarray(m['o'], float)
    e = cl['e']
    ok = pr['ok'] & (e + horizon < len(o))
    mv = (o[np.where(ok, e + horizon, 0)] - o[np.where(ok, e, 0)]) / G.STEP[coin]
    dec = ok & (np.abs(mv) >= G.FLAT)
    right_spot = np.sign(mv) == cl['side']
    out = {'priced': int(ok.sum()), 'spot_decided': int(dec.sum()),
           'spot_hit': float(right_spot[dec].mean()) if dec.any() else None,
           'contract_hit': float(pr['win'][ok].mean()) if ok.any() else None,
           'spot_and_contract_agree': float((right_spot[dec] == (pr['win'][dec] == 1.0)).mean()) if dec.any() else None}
    return out
