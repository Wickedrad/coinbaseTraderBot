"""Small statistics the loop needs, standard library only: Student t tail, Benjamini-Hochberg, the exact placebo moments
of a random draw of n trips out of a stratum, and the day-pooled gap test.
"""
import math


def _betacf(a, b, x):
    tiny, fpmin = 1e-30, 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > fpmin else fpmin)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c
        c = c if abs(c) > fpmin else fpmin
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c
        c = c if abs(c) > fpmin else fpmin
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-14:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln_bt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    bt = math.exp(ln_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_sf(t, df):
    """P(T > t) for Student's t with df degrees of freedom."""
    if df <= 0:
        return float('nan')
    if math.isinf(t):
        return 0.0 if t > 0 else 1.0
    x = df / (df + t * t)
    tail = 0.5 * betainc(df / 2.0, 0.5, x)
    return tail if t > 0 else 1.0 - tail


def bh(pvals, q=0.1, total=None):
    """Benjamini-Hochberg: indexes (into pvals) rejected at false discovery rate q. `total` is the number of trials the
    family stands for when more were tried than scored: the untested ones count with p = 1."""
    m = max(total or 0, len(pvals))
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    cut = -1
    for rank, i in enumerate(order, 1):
        if pvals[i] <= q * rank / m:
            cut = rank
    return sorted(order[:cut]) if cut > 0 else []


def placebo_moments(n_flagged_by_stratum, gains_by_stratum):
    """Exact mean and variance of the summed gain of a random draw (no replacement) of n_s trips from each stratum s.

    gains_by_stratum: {s: [gain of every trip in the stratum]}; n_flagged_by_stratum: {s: n_s}. A stratum with fewer trips
    than n_s contributes all of them.
    """
    mean = var = 0.0
    for s, n in n_flagged_by_stratum.items():
        g = gains_by_stratum.get(s) or []
        N = len(g)
        if N == 0 or n == 0:
            continue
        n = min(n, N)
        mu = sum(g) / N
        mean += n * mu
        if N > 1:
            s2 = sum((x - mu) ** 2 for x in g) / (N - 1)
            var += n * s2 * (N - n) / N
    return mean, var


def pooled_gap(gaps):
    """Day-pooled test of a list of per-day gaps (rule gain minus its placebo's expected gain, dollars).

    Returns dict(days, sum, mean, se, t, p_one_sided). One-sided: the rule is claimed to help. The days are the
    independent windows; with fewer than 2 there is no standard error.
    """
    d = len(gaps)
    out = {'days': d, 'sum': sum(gaps), 'mean': (sum(gaps) / d) if d else None, 'se': None, 't': None, 'p': None}
    if d < 2:
        return out
    m = out['mean']
    sd = math.sqrt(sum((g - m) ** 2 for g in gaps) / (d - 1))
    se = sd / math.sqrt(d)
    out['se'] = se
    if se == 0:
        out['t'] = float('inf') if m > 0 else float('-inf') if m < 0 else 0.0
    else:
        out['t'] = m / se
    out['p'] = t_sf(out['t'], d - 1)
    return out
