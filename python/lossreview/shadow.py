"""Offline shadow: a frozen rule flags the nightly trips as if it were live, and the days pile up as unseen-day evidence.

Nothing here reaches the bot. A rule enters shadow with its hash and the last day its sweep used; a night's flags are only
computed for a rule whose spec still hashes to the registered value, and only days AFTER the sweep's window count. Shadow gets
two fixed looks (LOOK_DAYS), each on exactly its first days and each paying half of the alpha: a rule is not re-tested every
night, so waiting for a lucky night does not work. The floor (85% of the un-ruled trips/h) is checked on the pooled flags and
on the union of the skip rules.
"""
from . import rules, stats, sweep

LOOK_DAYS = (5, 10)      # shadow days at each look; a rule that is not ready at the last one has faded
PROMOTE_ALPHA = 0.05     # one rule, confirmatory: split over the looks, nothing else left to pay for


class ShadowError(Exception):
    pass


def check_frozen(rule, registered_hash):
    if rules.rule_hash(rule) != registered_hash:
        raise ShadowError('rule %s no longer hashes to the registered %s: a changed rule is a new trial' % (rule.get('id'), registered_hash))


def shadow_day(rule, registered_hash, day, day_rows):
    """One night's shadow result for one rule: only `day`'s trips count. A night without trips returns trips = 0 and is not a day."""
    check_frozen(rule, registered_hash)
    rows = [r for r in day_rows if sweep.day_of(r) == day]
    if not rows:
        return {'day': day, 'trips': 0, 'flagged': 0, 'gain': 0.0, 'placebo': 0.0, 'gap': 0.0, 'hash': registered_hash}
    d = sweep.score_rule(rule, rows)['days'][0]
    return {'day': day, 'trips': d['trips'], 'flagged': d['flagged'], 'gain': d['gain'], 'placebo': d['placebo'], 'gap': d['gap'],
            'hash': registered_hash}


def usable(results, frozen_hash, after_day):
    """The results that count: this rule's hash, a day after the sweep's window, with trips; one per day (a re-run replaces)."""
    days = {}
    for r in results:
        if r.get('hash') == frozen_hash and r.get('day') and (after_day is None or r['day'] > after_day) and r.get('trips', 0) > 0:
            days[r['day']] = r
    return [days[d] for d in sorted(days)]


def shadow_verdict(results, frozen_hash, after_day, lever='skip'):
    """Pool the nightly results of one rule. 'ready' for a promotion PR when, at a fixed look, enough unseen days show a positive
    gap over the placebo AND a positive absolute gain, with enough flagged trips and the floor kept; 'faded' when the last look
    is reached without that; otherwise 'collecting'."""
    ordered = usable(results, frozen_hash, after_day)
    n = len(ordered)
    out = {'days': n, 'status': 'collecting', 'look': None}
    for look in LOOK_DAYS:
        if n < look:
            break
        w = ordered[:look]
        p = stats.pooled_gap([r['gap'] for r in w])
        flagged = sum(r['flagged'] for r in w)
        trips = sum(r['trips'] for r in w)
        gain = sum(r['gain'] for r in w)
        retention = (1.0 - flagged / trips) if (trips and lever == 'skip') else 1.0
        out.update({'look': look, 'flagged': flagged, 'gap_sum': round(p['sum'], 4), 'gap_mean': p['mean'], 'gain_sum': round(gain, 4),
                    'p': p['p'], 'retention': round(retention, 4)})
        ready = (flagged >= sweep.MIN_FLAGGED and p['mean'] is not None and p['mean'] > 0 and gain > 0 and p['p'] is not None
                 and p['p'] < PROMOTE_ALPHA / len(LOOK_DAYS) and retention >= sweep.RETENTION_FLOOR)
        if ready:
            out['status'] = 'ready'
            return out
    if n >= LOOK_DAYS[-1]:
        out['status'] = 'faded'
    return out


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
