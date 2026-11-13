"""A loss-prevention rule as data: one ex-ante feature test, one lever, frozen and hashed.

    {'id': 'late-cheap-dial', 'lever': 'dial', 'feature': 'entry_px_plan', 'op': 'lt', 'threshold': 0.25,
     'also': [{'feature': 'frac_elapsed_at_entry', 'op': 'gt', 'threshold': 0.5}], 'multiplier': 0.5}

`hit(rule, row)` is the single place that decides whether a trip is flagged: the sweep, the shadow flagger and the review
layer's winner control all call it. A row that lacks a feature is never flagged. `also` is an AND of further tests
(at most 2: the neighbor features). The hash covers everything that changes what the rule does.
"""
import hashlib
import json

from . import schema

OPS = ('lt', 'gt', 'between', 'eq')
LEVERS = ('dial', 'maker', 'strike', 'exit', 'skip')
SCORED_LEVERS = ('skip', 'dial')          # the sweep prices these from the trip file; the others need a replay
MAX_ALSO = 2
RULE_KEYS = ('id', 'lever', 'feature', 'op', 'threshold', 'also', 'multiplier', 'loss_class')


def _num(v):
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def test_one(feature, op, threshold, row):
    """True / False, or None when the row has no usable value for the feature."""
    v = row.get(feature)
    if v is None or v == '':
        return None
    if op == 'eq':
        return str(v).strip().lower() in (str(t).strip().lower() for t in (threshold if isinstance(threshold, (list, tuple)) else [threshold]))
    x = _num(v)
    if x is None:
        return None
    if op == 'lt':
        return x < float(threshold)
    if op == 'gt':
        return x > float(threshold)
    if op == 'between':
        lo, hi = float(threshold[0]), float(threshold[1])
        return lo <= x <= hi
    return None


def hit(rule, row):
    """Is the trip flagged by the rule (its main test and every `also` test)? Missing data: not flagged."""
    r = test_one(rule['feature'], rule['op'], rule['threshold'], row)
    if r is not True:
        return False
    for a in rule.get('also') or []:
        if test_one(a['feature'], a['op'], a['threshold'], row) is not True:
            return False
    return True


def validate_rule(rule):
    """(ok, errors): ex-ante features only, closed lever set, well-formed thresholds, at most MAX_ALSO extra tests."""
    errs = []
    unknown = set(rule) - set(RULE_KEYS)
    if unknown:
        errs.append('unknown keys %s' % sorted(unknown))
    if rule.get('lever') not in LEVERS:
        errs.append('lever must be one of %s' % (LEVERS,))
    tests = [rule] + list(rule.get('also') or [])
    if len(tests) - 1 > MAX_ALSO:
        errs.append('at most %d extra tests' % MAX_ALSO)
    for t in tests:
        ok, why = schema.validate_feature(t.get('feature'))
        if not ok:
            errs.append(why)
        if t.get('op') not in OPS:
            errs.append('op must be one of %s' % (OPS,))
        elif t['op'] == 'between':
            th = t.get('threshold')
            if not (isinstance(th, (list, tuple)) and len(th) == 2 and _num(th[0]) is not None and _num(th[1]) is not None and float(th[0]) < float(th[1])):
                errs.append('between needs [lo, hi] with lo < hi')
        elif t['op'] != 'eq' and _num(t.get('threshold')) is None:
            errs.append('threshold must be a number')
    if rule.get('lever') == 'dial':
        m = _num(rule.get('multiplier'))
        if m is None or not (0.0 < m < 1.0):
            errs.append('a dial rule needs a multiplier between 0 and 1 (it only shrinks)')
    return (not errs), errs


def curve_edit(rule):
    """True when any test of the rule reads a curve column: it needs the owner's explicit word."""
    return any(t.get('feature') in schema.CURVE_COLUMNS for t in [rule] + list(rule.get('also') or []))


def canonical(rule):
    return json.dumps({k: rule.get(k) for k in RULE_KEYS if k in rule}, sort_keys=True, separators=(',', ':'))


def rule_hash(rule):
    return hashlib.sha256(canonical(rule).encode()).hexdigest()[:16]


def gain(rule, row):
    """First-order change in a trip's dollars if the rule had applied: a skip removes the trip (its P&L and its fees go),
    a dial scales it. Positive means the rule helped. Integer contract counts and the fee's cent rounding are ignored;
    shadow and the promotion's own differential test are what check that."""
    pnl = _num(row.get('pnl'))
    if pnl is None:
        return 0.0
    if rule['lever'] == 'skip':
        return -pnl
    if rule['lever'] == 'dial':
        return (float(rule['multiplier']) - 1.0) * pnl
    return 0.0
