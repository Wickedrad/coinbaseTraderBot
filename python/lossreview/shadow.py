"""Offline shadow: a frozen rule flags the nightly trips as if it were live, and the days pile up as unseen-day evidence.

Nothing here reaches the bot. A rule enters shadow with its hash; a night's flags are only computed for a rule whose spec
still hashes to the registered value. The floor (85% of the un-ruled trips/h) is checked on the union of the skip rules.
"""
import math

from . import rules, stats, sweep

PROMOTE_MIN_DAYS = 5     # shadow days before a promotion PR is drafted
PROMOTE_ALPHA = 0.05     # one rule, confirmatory: no multiplicity left to pay for


class ShadowError(Exception):
    pass


def check_frozen(rule, registered_hash):
    if rules.rule_hash(rule) != registered_hash:
        raise ShadowError('rule %s no longer hashes to the registered %s: a changed rule is a new trial' % (rule.get('id'), registered_hash))


def shadow_day(rule, registered_hash, day_rows):
    """One night's shadow result for one rule over that day's trips (a list of trip rows closed that day)."""
    check_frozen(rule, registered_hash)
    r = sweep.score_rule(rule, day_rows)
    d = r['days'][0] if r['days'] else {'day': None, 'trips': 0, 'flagged': 0, 'gain': 0.0, 'placebo': 0.0, 'gap': 0.0}
    return {'day': d['day'], 'trips': d['trips'], 'flagged': d['flagged'], 'gain': d['gain'], 'placebo': d['placebo'], 'gap': d['gap'],
            'hash': registered_hash}


def shadow_verdict(results):
    """Pool the nightly results of one rule: ready for a promotion PR when enough unseen days show a positive gap over its placebo."""
    days = {}
    for r in results:
        days[r['day']] = r          # a day re-run replaces itself
    ordered = [days[d] for d in sorted(days)]
    gaps = [r['gap'] for r in ordered]
    p = stats.pooled_gap(gaps)
    flagged = sum(r['flagged'] for r in ordered)
    ready = (p['days'] >= PROMOTE_MIN_DAYS and flagged >= sweep.MIN_FLAGGED and p['mean'] is not None and p['mean'] > 0
             and p['p'] is not None and p['p'] < PROMOTE_ALPHA)
    faded = p['days'] >= PROMOTE_MIN_DAYS and p['mean'] is not None and p['mean'] <= 0
    return {'days': p['days'], 'flagged': flagged, 'gap_sum': round(p['sum'], 4), 'gap_mean': p['mean'], 'p': p['p'],
            'status': 'ready' if ready else 'faded' if faded else 'collecting'}


def ruleset_floor(skip_rules, rows, floor=sweep.RETENTION_FLOOR):
    """Which skip rules fit under the floor together. Rules go in the order given (best first); a rule that would push the
    union of flagged trips past 1 - floor of the trips is held back. Returns (kept ids, held-back ids, retention kept)."""
    n = len(rows)
    flagged = set()
    kept, held = [], []
    for rule in skip_rules:
        mine = {i for i, r in enumerate(rows) if rules.hit(rule, r)}
        if n and len(flagged | mine) / n > 1 - floor:
            held.append(rule['id'])
        else:
            flagged |= mine
            kept.append(rule['id'])
    return kept, held, (1.0 - len(flagged) / n) if n else 1.0
