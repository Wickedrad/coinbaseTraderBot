"""The educated sweep: score a hypothesis' thresholds on days AFTER the losses that generated it, against a placebo.

For each candidate rule (a threshold of the hypothesis' feature, plus tail or quartile cuts of its neighbor features) and each
scoring day: the rule's gain (rules.gain summed over the trips it flags) minus the expected gain of a placebo that applies the
same lever to the same number of trips drawn at random from the same price bucket on that day (exact mean, not a draw). That is
one control per lever: for a skip, a random skip of the same count; for a dial, the same multiplier on trips matched on price
bucket. The verdict is the day-pooled gap with its own standard error (days are the independent windows), and it needs BOTH a
positive gap over the placebo and a positive absolute gain (beating a random draw is not helping when the draw loses more).
It is corrected by Bonferroni over every candidate that could pass the floor and over the fixed looks, and then BH over the
registry's trials.

Looks are fixed (SWEEP_LOOKS scoring days: 4, 8, 12): a hypothesis is scored once at each, on exactly its first N scoring days,
never re-tested nightly. Candidates that would flag more of the trips than the floor allows are dropped before scoring: that
filter reads only the feature, never an outcome, so it selects nothing.

Levers the trip file cannot price (maker, strike, exit) are not scored here: `replay_request` writes the spec a replay owner
needs. Nothing is tuned on a day that generated the hypothesis, and nothing here touches the bot.
"""
import math
import time

from . import ledger, rules, stats

MIN_DAYS = 4           # independent windows before a standard error means anything
MIN_FLAGGED = 100      # flagged trips over the scoring days (2-3c effect, clustered: the plan's N)
ALPHA = 0.05
RETENTION_FLOOR = 0.85  # trips/h kept: skip rules may not remove more than 15% of the lane's trips
DIAL_MULTIPLIER = 0.5
QUARTILES = (0.25, 0.5, 0.75)
TAILS_LOW = (0.05, 0.10, 0.15)      # neighbor cuts for a skip: a tail that can fit under the floor
SWEEP_LOOKS = (4, 8, 12)            # scoring days at each look; the correction pays for all of them


def day_of(row):
    t = row.get('closed_t')
    if isinstance(t, (int, float)):
        return time.strftime('%Y-%m-%d', time.gmtime(t))
    return row.get('day')


def scoring_rows(rows, generating_days):
    """Rows on days strictly after the last day that generated the hypothesis. No generating days is an error: an empty
    list would score every day, the generating ones included."""
    if not generating_days:
        raise ValueError('a hypothesis needs its generating days: scoring must start after them')
    last = max(generating_days)
    return [r for r in rows if day_of(r) and day_of(r) > last]


def first_days(rows, n):
    """Rows of the first n distinct days (the fixed window of a look)."""
    days = sorted({day_of(r) for r in rows})[:n]
    keep = set(days)
    return [r for r in rows if day_of(r) in keep]


def _stratum(row):
    px = row.get('entry_px')
    try:
        return ledger.bucket(float(px)) if px not in (None, '') else 'other'
    except (TypeError, ValueError):
        return 'other'


def score_rule(rule, rows):
    """Score one frozen rule on `rows` (already restricted to scoring days). Returns the per-day table and the pooled test."""
    days = {}
    for r in rows:
        days.setdefault(day_of(r), []).append(r)
    per_day, gaps = [], []
    n_flag = n_tot = 0
    gain_sum = 0.0
    for d in sorted(days):
        rs = days[d]
        flagged = [r for r in rs if rules.hit(rule, r)]
        gain = sum(rules.gain(rule, r) for r in flagged)
        by_s, n_by_s = {}, {}
        for r in rs:
            by_s.setdefault(_stratum(r), []).append(rules.gain(rule, r))
        for r in flagged:
            n_by_s[_stratum(r)] = n_by_s.get(_stratum(r), 0) + 1
        pmean, pvar = stats.placebo_moments(n_by_s, by_s)
        gaps.append(gain - pmean)
        gain_sum += gain
        per_day.append({'day': d, 'trips': len(rs), 'flagged': len(flagged), 'gain': round(gain, 4), 'placebo': round(pmean, 4),
                        'placebo_sd': round(math.sqrt(pvar), 4), 'gap': round(gain - pmean, 4)})
        n_flag += len(flagged)
        n_tot += len(rs)
    pooled = stats.pooled_gap(gaps)
    return {'rule': rule, 'hash': rules.rule_hash(rule), 'days': per_day, 'flagged': n_flag, 'trips': n_tot, 'pooled': pooled,
            'gain_sum': gain_sum, 'retention': (1.0 - n_flag / n_tot) if (n_tot and rule['lever'] == 'skip') else 1.0}


def verdict(res, k, looks=1):
    """'candidate' | 'no_effect' | 'insufficient_days' | 'insufficient_flags' | 'floor' for one scored rule. k is how many
    candidates the hypothesis could pass with and `looks` how many fixed looks it gets: the p value pays for both."""
    p = res['pooled']
    if p['days'] < MIN_DAYS:
        return 'insufficient_days', None
    padj = None if p['p'] is None else min(1.0, p['p'] * k * looks)
    if res['flagged'] < MIN_FLAGGED:
        return 'insufficient_flags', padj
    if res['retention'] < RETENTION_FLOOR:
        return 'floor', padj
    if p['mean'] is not None and p['mean'] > 0 and res['gain_sum'] > 0 and padj is not None and padj < ALPHA:
        return 'candidate', padj
    return 'no_effect', padj


def _quantile(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))] if s else None


def expand(h, rows):
    """The candidate rules of a validated hypothesis (forms.validate_hypothesis said ok): one per threshold of its feature,
    and for each neighbor feature cuts of its values in `rows` with the hypothesis' op (quartiles for a dial; the tail that can
    fit under the floor for a skip). Dial rules use DIAL_MULTIPLIER (one lever setting: the multiplicity is the thresholds, not
    the size). A skip candidate that flags more of `rows` than the floor allows is dropped (feature only, no outcome read).
    Returns (candidates, dropped_for_floor)."""
    base = {'lever': h['lever'], 'loss_class': h.get('loss_class')}
    if h['lever'] == 'dial':
        base['multiplier'] = DIAL_MULTIPLIER
    cands = []
    ths = h['thresholds'] if h['op'] != 'between' else [h['thresholds']]
    for t in ths:
        cands.append(dict(base, id='%s@%s' % (h['id'], t), feature=h['feature'], op=h['op'], threshold=t))
    if h['op'] in ('lt', 'gt'):
        cuts = QUARTILES if h['lever'] == 'dial' else (TAILS_LOW if h['op'] == 'lt' else tuple(1 - q for q in TAILS_LOW))
        for nf in h.get('neighbor_features') or []:
            vals = []
            for r in rows:
                v = r.get(nf)
                try:
                    if v not in (None, '') and not isinstance(v, bool) and math.isfinite(float(v)):
                        vals.append(float(v))
                except (TypeError, ValueError):
                    pass
            for q in cuts:
                t = _quantile(vals, q)
                if t is not None:
                    cands.append(dict(base, id='%s+%s@q%d' % (h['id'], nf, round(q * 100)), feature=nf, op=h['op'], threshold=round(t, 6)))
    if h['lever'] != 'skip' or not rows:
        return cands, 0
    keep = [c for c in cands if sum(1 for r in rows if rules.hit(c, r)) / len(rows) <= 1 - RETENTION_FLOOR]
    return keep, len(cands) - len(keep)


def sweep(h, rows, generating_days, max_days=None, looks=len(SWEEP_LOOKS)):
    """Sweep one hypothesis on its first `max_days` scoring days (all of them when None). Returns {'scored', 'best', 'k',
    'dropped', 'days', 'replay'}. Levers the trip file cannot price return a replay request instead of a score."""
    if h['lever'] not in rules.SCORED_LEVERS:
        return {'scored': [], 'best': None, 'k': 0, 'dropped': 0, 'days': 0, 'replay': replay_request(h, generating_days)}
    sc = scoring_rows(rows, generating_days)
    if max_days is not None:
        sc = first_days(sc, max_days)
    cands, dropped = expand(h, sc)
    k = len(cands)
    scored = []
    for rule in cands:
        res = score_rule(rule, sc)
        v, padj = verdict(res, k, looks)
        scored.append(dict(res, verdict=v, p_adj=padj, k=k))
    # The best candidate is the lowest corrected p among those that pass every gate (floor included); with none passing,
    # the lowest overall, so the report can say how close it came.
    ranked = sorted([s for s in scored if s['p_adj'] is not None], key=lambda s: (s['verdict'] != 'candidate', s['p_adj']))
    best = ranked[0] if ranked else None
    return {'scored': scored, 'best': best, 'k': k, 'dropped': dropped, 'days': len({day_of(r) for r in sc}), 'replay': None}


def replay_request(h, generating_days):
    """The spec a replay owner needs for a lever priced by replay (maker entries, cheaper strike, exit settings)."""
    return {'hypothesis': h['id'], 'lever': h['lever'], 'feature': h['feature'], 'op': h['op'], 'thresholds': h['thresholds'],
            'score_days_after': max(generating_days) if generating_days else None,
            'control': 'a perturbed-setting replay on the same days (one control per lever)'}


def registry_fdr(best_p_adj_by_id, total_trials, q=0.1):
    """BH over the registry: ids whose best corrected p survive at false discovery rate q, the untested trials counting as p = 1."""
    ids = sorted(best_p_adj_by_id)
    keep = stats.bh([best_p_adj_by_id[i] for i in ids], q=q, total=total_trials)
    return [ids[i] for i in keep]
