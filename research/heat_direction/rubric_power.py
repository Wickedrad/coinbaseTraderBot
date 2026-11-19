"""How often would the ten-check rubric in PREREG.md pass a candidate, by simulation?

Research only. Plain numpy, no market data, no network. It answers three questions before any real candidate is
scored: (1) with NO direction edge, how often does a candidate still clear the bar (checks 1, 2, 3 plus nine of ten),
per held-out look and over the 6 looks the loop allows; (2) with a real edge of a given size, how often does it pass;
(3) the same for the single FINAL window.

    python3 research/heat_direction/rubric_power.py [--sims 4000] [--seed 7]

What the model has: calendar days, ISO weeks (Monday start) and calendar months; a day effect on the true hit rate;
BTC and ETH outcomes that share the hour; a 93% overlap between on-time and one-minute-late outcomes; ten naive
side rules; the required checks; the FINAL window (equal fourths as blocks). What it does not have: the real call
count (round 0 measures it) or real tails. Check 2 uses the ratio-estimator standard error over days; the real
evaluator uses the day-cluster bootstrap, which is close.
Scenario columns: hit rate of unconfirmed calls, of TA-confirmed calls, of the calls the TA layer invalidates
(scored as if made).
"""
import argparse
import datetime as dt
import numpy as np

COINS = 2
CONF_SHARE = 0.35    # share of calls the TA layer confirms
INV_SHARE = 0.25     # invalidated calls, as a share of the calls made (scored as if made)
LATE_SHARE = 0.93    # share of a call's outcome kept when entry is one minute later
LATE_DECAY = 0.01    # edge lost to the delay
DAY_SD = 0.03        # day-to-day shift of the true hit rate
HOUR_SHARE = 0.80    # share of outcomes drawn from a draw shared by every call in the same hour (BTC/ETH outcome correlation about 0.6)
FLOOR = dict(pooled=800, coin=300, side=150, ta=150, block=150, week_calls=20)

SCEN = {  # name: (unconfirmed, confirmed, invalidated)
    'A no edge':                    (0.50, 0.50, 0.50),
    'B edge .53, TA adds nothing':  (0.53, 0.53, 0.53),
    'C edge .55, TA adds nothing':  (0.55, 0.55, 0.55),
    'D edge .55, TA adds':          (0.53, 0.59, 0.46),
    'E edge .57, TA adds':          (0.55, 0.62, 0.45),
}
WINDOWS = {  # name: (first day, number of days, calls per coin per day, blocks)
    'VAL 2026-07-01..10-31': (dt.date(2026, 7, 1), 123, 4.0, 'month'),
    'FINAL 16 weeks':        (dt.date(2027, 1, 4), 112, 4.0, 4),
}


def cse(h, day, ndays, n_all):
    """Ratio-estimator standard error of a hit rate over days (n_all = decided calls in the group)."""
    dh = np.bincount(day, weights=h, minlength=ndays)
    dn = np.bincount(day, minlength=ndays)
    return np.sqrt(np.sum((dh - h.mean() * dn) ** 2)) / max(n_all, 1)


def one(rng, p_unc, p_conf, p_inv, w):
    d0, ndays, rate, blocks = w
    dates = np.array([d0 + dt.timedelta(days=i) for i in range(ndays)])
    n_call = rng.poisson(rate, size=(ndays, COINS))
    day = np.repeat(np.arange(ndays), n_call.sum(1))
    n = len(day)
    coin = np.concatenate([np.repeat(np.arange(COINS), n_call[d]) for d in range(ndays)])
    hour = rng.integers(0, 24, size=n)
    conf = rng.random(n) < CONF_SHARE
    eff = rng.normal(0, DAY_SD, size=ndays)[day]
    p = np.where(conf, p_conf, p_unc) + eff
    shared = rng.random((ndays, 24))[day, hour]
    u = np.where(rng.random(n) < HOUR_SHARE, shared, rng.random(n))
    hit = u < p
    side = rng.random(n) < 0.5
    late = np.where(rng.random(n) < LATE_SHARE, hit, rng.random(n) < p - LATE_DECAY)
    ni = int(INV_SHARE * n)
    inv_day = np.sort(rng.integers(0, ndays, size=ni))
    inv_hit = rng.random(ni) < (p_inv + rng.normal(0, DAY_SD, size=ndays)[inv_day])
    # ten naive side rules at the same call times, none with an edge of its own: follow/fade of the last 1, 5, 15 and
    # 60 minute move (a rule and its fade are complements) and always UP / always DOWN: five independent draws, each
    # clustered by hour and day like the candidate's own outcomes
    dev = []
    for _ in range(5):
        us = np.where(rng.random(n) < HOUR_SHARE, rng.random((ndays, 24))[day, hour], rng.random(n))
        pr = 0.5 + rng.normal(0, DAY_SD, size=ndays)[day]
        dev.append(abs((us < pr).mean() - 0.5))
    naive_best = 0.5 + max(dev)
    rate_hit = hit.mean()
    if blocks == 'month':
        blk = np.array([d.year * 12 + d.month for d in dates])[day]
    else:
        blk = np.minimum(day * blocks // ndays, blocks - 1)
    iso = np.array([(d - dt.timedelta(days=d.weekday())).toordinal() for d in dates])
    wk_of_day = iso
    last = dates[-1]
    full_week_ids = [w0 for w0 in np.unique(wk_of_day)
                     if (dt.date.fromordinal(int(w0)) >= dates[0]) and (dt.date.fromordinal(int(w0)) + dt.timedelta(days=6) <= last)]
    s = []
    # 1 level
    s.append(n >= FLOOR['pooled'] and rate_hit >= 0.55)
    # 2 not luck
    dh = np.bincount(day, weights=hit, minlength=ndays)
    dn = np.bincount(day, minlength=ndays)
    se = np.sqrt(np.sum((dh - rate_hit * dn) ** 2)) / max(n, 1)
    s.append(n >= FLOOR['pooled'] and rate_hit - 1.96 * se > 0.50)
    # 3 beats the best naive rule
    s.append(n >= FLOOR['pooled'] and rate_hit - naive_best >= 0.02)
    # 4 both coins
    s.append(all((coin == c).sum() >= FLOOR['coin'] and hit[coin == c].mean() >= 0.53 for c in range(COINS)))
    # 5 full ISO weeks; a quiet week fails
    ok = []
    wk_day = wk_of_day[day]
    for w0 in full_week_ids:
        m = wk_day == w0
        ok.append(m.sum() >= FLOOR['week_calls'] and hit[m].mean() > 0.5)
    s.append(len(ok) >= 8 and np.mean(ok) >= 0.65)
    # 6 blocks: a thin block scores 0 for the whole check
    ub = np.unique(blk)
    s.append(len(ub) >= (4 if blocks != 'month' else 3)
             and all((blk == b).sum() >= FLOOR['block'] and hit[blk == b].mean() > 0.5 for b in ub))
    # 7 both sides
    s.append(all((side == v).sum() >= FLOOR['side'] and hit[side == v].mean() >= 0.52 for v in (True, False)))
    # 8 one minute late
    s.append(n >= FLOOR['pooled'] and late.mean() >= 0.53)
    # 9 TA confirms: 3 points and a 90% one-sided day-cluster lower bound above zero
    if conf.sum() >= FLOOR['ta'] and (~conf).sum() >= FLOOR['ta']:
        d9 = hit[conf].mean() - hit[~conf].mean()
        se9 = np.hypot(cse(hit[conf].astype(float), day[conf], ndays, conf.sum()),
                       cse(hit[~conf].astype(float), day[~conf], ndays, (~conf).sum()))
        s.append(d9 >= 0.03 and d9 - 1.2816 * se9 > 0)
    else:
        s.append(False)
    # 10 TA invalidates: invalidated calls <= 50%, 3 points below the calls it keeps, same cluster lower bound
    if ni >= FLOOR['ta']:
        d10 = hit.mean() - inv_hit.mean()
        se10 = np.hypot(cse(hit.astype(float), day, ndays, n), cse(inv_hit.astype(float), inv_day, ndays, ni))
        s.append(inv_hit.mean() <= 0.50 and d10 >= 0.03 and d10 - 1.2816 * se10 > 0)
    else:
        s.append(False)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sims', type=int, default=4000)
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--rate', type=float, default=None, help='calls per coin per day (round 0 measured 77 to 82)')
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    for wname, w in WINDOWS.items():
        if a.rate is not None:
            w = (w[0], w[1], a.rate, w[3])
        print('\n%s: %d days, %.1f calls per coin per day, sims %d' % (wname, w[1], w[2], a.sims))
        print('%-30s %7s %6s %6s %8s %7s  per-check pass %% (1..10)' % ('scenario', 'PASS', '>=9', 'core8', '6 looks', 'mean'))
        for name, (u, c, i) in SCEN.items():
            r = np.array([one(rng, u, c, i, w) for _ in range(a.sims)], dtype=bool)
            tot = r.sum(1)
            gate = r[:, :3].all(1)
            ok = gate & (tot >= 9)
            print('%-30s %6.2f%% %5.1f%% %5.1f%% %7.2f%% %7.2f  %s' % (
                name, 100 * ok.mean(), 100 * (tot >= 9).mean(), 100 * r[:, :8].all(1).mean(),
                100 * (1 - (1 - ok.mean()) ** 6), tot.mean(),
                ' '.join('%3d' % round(100 * x) for x in r.mean(0))))


if __name__ == '__main__':
    main()
