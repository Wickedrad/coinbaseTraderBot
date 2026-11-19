"""Closed vocabularies and validators for the review layer: the LLM proposes, this code decides.

Cheap LLM steps (run elsewhere) tag losing trips, propose a hypothesis about what made a class of losers lose, and
argue against it. Everything they return is JSON that passes through the validators here; anything outside the closed
lists is rejected, never repaired. No model is called from this package.

Hard rules enforced here:
  1. A hypothesis cites only ex-ante columns (known at order time or earlier). Outcome columns are context for a
     reviewer, never a feature, a neighbor or a cite, and never a word of the mechanism text.
  2. A column in schema.CURVE_COLUMNS belongs to the protected heat curves: the hypothesis is flagged 'curve_edit'
     (never auto-promoted; it needs the owner's explicit word).
  3. One lever per hypothesis, from LEVERS. Priority when levers compete: dial, then maker = strike, then exit, then skip.
  4. At most MAX_THRESHOLDS thresholds and MAX_NEIGHBORS neighbor features.
  5. Per-trade data stays private: the identifier columns (ticker, entry_utc and the raw epoch times) are never
     features or cites, and a mechanism text must not carry a ticker.
"""
import json
import math
import re

from . import schema, triage

# Tags: what a cheap model may say about a trip, each measured by ex-ante columns (a test checks that every column
# named exists and is ex-ante). A tag describes; it never carries dollars and never decides anything.
TAGS = {
    'late_entry': ('frac_elapsed_at_entry', 'left_at_entry_s'),
    'early_window_entry': ('frac_elapsed_at_entry', 'left_at_entry_s'),
    'cheap_side': ('entry_px', 'entry_px_plan', 'plan_price'),
    'rich_side': ('entry_px', 'entry_px_plan', 'plan_price'),
    'fee_heavy_small_edge': ('entry_px', 'stake', 'stake_plan'),
    'hourly_far_strike': ('kind', 'strike', 'spot_vs_strike_bps_pre'),
    'hourly_near_strike': ('kind', 'strike', 'spot_vs_strike_bps_pre'),
    'hourly_market': ('kind',),
    'fifteen_minute_market': ('kind',),
    'pair_call': ('call_kind',),
    'single_call': ('call_kind',),
    'no_side': ('side',),
    'yes_side': ('side',),
    'big_count': ('count', 'count_plan', 'stake'),
    'small_stake': ('stake', 'stake_plan'),
    'stale_call': ('call_age_s',),
    'stale_spot': ('spot_pre_age_s',),
    'spot_on_wrong_side': ('spot_vs_strike_bps_pre', 'side'),
    'hour_disagrees': ('context',),                # a curve column: a hypothesis built on it is flagged curve_edit
    'low_rank_in_batch': ('rank', 'of'),           # curve columns too
}

TAG_HELP = {
    'late_entry': 'entered after half of the window had passed',
    'early_window_entry': 'entered in the first fifth of the window',
    'cheap_side': 'side bought under 25c',
    'rich_side': 'side bought at 75c or more',
    'fee_heavy_small_edge': 'price near 50c, where the fee per dollar staked is highest, on a small stake',
    'hourly_far_strike': 'hourly market whose strike was far from the last spot',
    'hourly_near_strike': 'hourly market whose strike was within a few bps of the last spot',
    'hourly_market': 'an hourly market',
    'fifteen_minute_market': 'a 15 minute market',
    'pair_call': 'the call came from a pair of signals',
    'single_call': 'the call came from a single signal',
    'no_side': 'bought the NO side',
    'yes_side': 'bought the YES side',
    'big_count': 'a large contract count (60 or more)',
    'small_stake': 'a small stake',
    'stale_call': 'the call was old when the order went out',
    'stale_spot': 'the last closed spot minute was old when the order went out',
    'spot_on_wrong_side': 'the last spot already sat on the unfavourable side of the strike for the side bought',
    'hour_disagrees': 'the hour context disagreed with the call',
    'low_rank_in_batch': 'the call ranked low in its batch',
}

LEVERS = ('dial', 'maker', 'strike', 'exit', 'skip')
LEVER_HELP = {
    'dial': 'stake size multiplier (shrink the stake), or the fee paid per dollar staked',
    'maker': 'rest the entry as a maker order instead of crossing the spread',
    'strike': 'take a cheaper strike on hourly ladders',
    'exit': 'an exit-rule setting',
    'skip': 'decline the entry',
}
# Priority when two levers could fix the same loss: lower number first (dial > maker = strike > exit > skip).
LEVER_ORDER = {'dial': 0, 'maker': 1, 'strike': 1, 'exit': 2, 'skip': 3}

OPS = ('lt', 'gt', 'between', 'eq')   # between is lo <= x <= hi (inclusive); lt and gt are strict
VERDICTS = ('survives', 'refuted', 'unclear')
ADVERSARY_REASONS = ('confounded_by_price', 'confounded_by_coin', 'clustered_in_time', 'too_few_trips',
                     'winner_control_matches', 'hindsight_feature', 'overlaps_curve', 'fee_artifact', 'other')

# Loser classes a hypothesis may explain: hindsight-free enough to be worth a rule. The rest are bookkeeping classes.
NOT_REVIEWED = ('FIDELITY', 'OTHER_LANE', 'UNKNOWN_DATA', 'UNEXPLAINED')
HYPOTHESIS_CLASSES = tuple(c for c in triage.LOSER_CLASSES if c not in NOT_REVIEWED)

MAX_THRESHOLDS = 12
MAX_NEIGHBORS = 2
MAX_MECHANISM = 240
MAX_NOTE = 300
MAX_EQ_LEN = 40
HYPOTHESIS_KEYS = ('id', 'loss_class', 'lever', 'feature', 'op', 'thresholds', 'neighbor_features', 'mechanism', 'cites')
REQUIRED_KEYS = ('id', 'loss_class', 'lever', 'feature', 'op', 'thresholds', 'mechanism')  # the other two default to []
ADVERSARY_KEYS = ('hypothesis_id', 'verdict', 'reasons', 'note')

# Per-trade identifiers and raw clock times: ex-ante in the registry, but a rule keyed on one is a per-trade rule, and
# citing one carries the trade into the hypothesis record. (The time left in the window is left_at_entry_s.)
IDENTIFIER_COLUMNS = frozenset({'ticker', 'entry_utc', 'entry_t', 'window_close_t', 'order_t'})
# Columns that hold a label, not a number: lt, gt and between make no sense on them.
CATEGORICAL_COLUMNS = frozenset({'kind', 'coin', 'side', 'call_kind', 'call_key', 'dir', 'context', 'era', 'lane'})

# Columns a hypothesis may use as feature, neighbor or cite (curve columns included: they are flagged, not forbidden).
FEATURE_COLUMNS = tuple(c for c in schema.COLUMNS if schema.ex_ante(c) and c not in IDENTIFIER_COLUMNS)
# Columns known only after the order: shown to a reviewer apart from the ex-ante block, never features.
OUTCOME_COLUMNS = tuple(c for c in schema.COLUMNS if not schema.ex_ante(c))

ID_RE = re.compile(r'[a-z0-9_-]{3,40}')
_WORD = r'(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])'
_OUTCOME_WORD_RE = re.compile(_WORD % '|'.join(re.escape(c) for c in sorted(OUTCOME_COLUMNS, key=len, reverse=True)), re.I)
# Kalshi heat tickers, e.g. KXBTC15M-26NOV121015-15 or KXETHD-26NOV1210: a mechanism text never carries one.
TICKER_RE = re.compile(r'KX[A-Z0-9]+-\d\d[A-Z]{3}\d', re.I)


def outcome_words(text):
    """Outcome column names that `text` uses as whole words (case-insensitive; underscores count as word characters)."""
    return sorted({m.group(0).lower() for m in _OUTCOME_WORD_RE.finditer(text or '')})


def validate_tags(tags):
    """(ok, errors) for the tags of one trip: a list of distinct names from TAGS (an empty list is fine)."""
    if not isinstance(tags, (list, tuple)):
        return False, ['tags must be a list']
    errors, seen = [], set()
    for t in tags:
        if not isinstance(t, str) or t not in TAGS:
            errors.append('unknown tag %r' % (t,))
        elif t in seen:
            errors.append('duplicate tag %r' % t)
        else:
            seen.add(t)
    return not errors, errors


def _column(col, what, errors, flags):
    """Check one column mention; add 'curve_edit' to flags for a curve column. True when the column is usable."""
    if not isinstance(col, str):
        errors.append('%s must be a column name (a string)' % what)
        return False
    if col in IDENTIFIER_COLUMNS:
        errors.append('%s %r is a per-trade identifier, not a feature' % (what, col))
        return False
    ok, why = schema.validate_feature(col)
    if not ok:
        errors.append('%s: %s' % (what, why))
        return False
    if col in schema.CURVE_COLUMNS:
        flags.add('curve_edit')
    return True


def _column_list(h, key, errors, flags, feature=None, cap=None):
    v = h.get(key, [])
    if not isinstance(v, list):
        errors.append('%s must be a list' % key)
        return
    if cap is not None and len(v) > cap:
        errors.append('%s has %d items, at most %d allowed' % (key, len(v), cap))
    seen = set()
    for c in v:
        ok = _column(c, '%s item %r' % (key, c), errors, flags)
        if ok and c == feature:
            errors.append('%s item %r repeats the feature' % (key, c))
        elif ok and c in seen:
            errors.append('%s item %r is listed twice' % (key, c))
        seen.add(c if isinstance(c, str) else None)


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _norm(x):
    """A comparable key for duplicate detection."""
    if isinstance(x, bool):
        return ('b', x)
    if isinstance(x, str):
        return ('s', x.strip().lower())
    return ('n', float(x))


def _check_thresholds(h, errors):
    thr, op = h.get('thresholds'), h.get('op')
    if not isinstance(thr, list):
        errors.append('thresholds must be a list')
        return
    if not 1 <= len(thr) <= MAX_THRESHOLDS:
        errors.append('thresholds has %d items, need 1 to %d' % (len(thr), MAX_THRESHOLDS))
        return
    if op == 'eq':
        for t in thr:
            if isinstance(t, bool):
                continue
            if not isinstance(t, str) or not t.strip() or len(t) > MAX_EQ_LEN:
                errors.append('eq thresholds must be non-empty strings (at most %d chars) or booleans: got %r' % (MAX_EQ_LEN, t))
                return
    elif op in ('lt', 'gt', 'between'):
        for t in thr:
            if not _is_num(t):
                errors.append('%s thresholds must be finite numbers: got %r' % (op, t))
                return
        if op == 'between':
            if len(thr) != 2:
                errors.append('between needs exactly 2 thresholds [lo, hi]')
                return
            if not thr[0] < thr[1]:
                errors.append('between needs lo < hi: got %r, %r' % (thr[0], thr[1]))
                return
    else:
        return  # the op error is already reported
    if len({_norm(t) for t in thr}) != len(thr):
        errors.append('thresholds repeat a value')


def validate_hypothesis(h):
    """(ok, errors, flags) for one hypothesis dict from a model.

    Fields: id, loss_class, lever, feature, op, thresholds, neighbor_features (optional), mechanism, cites (optional).
    ok is True when errors is empty. flags are advisory facts the caller must act on; 'curve_edit' means a feature,
    neighbor or cite is a heat-curve column (never auto-promoted, needs the owner's explicit word).
    """
    if not isinstance(h, dict):
        return False, ['a hypothesis must be a JSON object'], []
    errors, flags = [], set()
    for k in sorted(h, key=str):
        if k not in HYPOTHESIS_KEYS:
            errors.append('unknown key %r' % (k,))
    for k in REQUIRED_KEYS:
        if k not in h:
            errors.append('missing key %r' % k)

    if 'id' in h and not (isinstance(h['id'], str) and ID_RE.fullmatch(h['id'])):
        errors.append('id must be 3 to 40 characters from a-z 0-9 _ -')
    if 'loss_class' in h:
        lc = h['loss_class']
        if not isinstance(lc, str) or lc not in triage.LOSER_CLASSES:
            errors.append('loss_class must be one of %s' % (HYPOTHESIS_CLASSES,))
        elif lc in NOT_REVIEWED:
            errors.append('loss_class %s is not reviewed for rules; use one of %s' % (lc, HYPOTHESIS_CLASSES))
    if 'lever' in h and (not isinstance(h['lever'], str) or h['lever'] not in LEVERS):
        errors.append('lever must be exactly one of %s' % (LEVERS,))
    if 'op' in h and (not isinstance(h['op'], str) or h['op'] not in OPS):
        errors.append('op must be one of %s' % (OPS,))

    feature = h.get('feature')
    if 'feature' in h:
        ok = _column(feature, 'feature', errors, flags)
        if ok and feature in CATEGORICAL_COLUMNS and h.get('op') in ('lt', 'gt', 'between'):
            errors.append('feature %r is a label: use op eq' % feature)
    if 'thresholds' in h:
        _check_thresholds(h, errors)
    _column_list(h, 'neighbor_features', errors, flags, feature=feature, cap=MAX_NEIGHBORS)
    _column_list(h, 'cites', errors, flags)

    if 'mechanism' in h:
        m = h['mechanism']
        if not isinstance(m, str) or not m.strip():
            errors.append('mechanism must be a non-empty string')
        else:
            if len(m) > MAX_MECHANISM:
                errors.append('mechanism has %d characters, at most %d allowed' % (len(m), MAX_MECHANISM))
            leaks = outcome_words(m)
            if leaks:
                errors.append('mechanism names outcome columns %s: hindsight leak' % leaks)
            if TICKER_RE.search(m):
                errors.append('mechanism carries a ticker: per-trade data stays private')
    return not errors, errors, sorted(flags)


def validate_adversary(a):
    """(ok, errors) for an adversary verdict: hypothesis_id, verdict, reasons (non-empty unless 'survives'), note."""
    if not isinstance(a, dict):
        return False, ['a verdict must be a JSON object']
    errors = []
    for k in sorted(a, key=str):
        if k not in ADVERSARY_KEYS:
            errors.append('unknown key %r' % (k,))
    hid = a.get('hypothesis_id')
    if not (isinstance(hid, str) and ID_RE.fullmatch(hid)):
        errors.append('hypothesis_id must be a hypothesis id (3 to 40 characters from a-z 0-9 _ -)')
    verdict = a.get('verdict')
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        errors.append('verdict must be one of %s' % (VERDICTS,))
    reasons = a.get('reasons')
    if not isinstance(reasons, list):
        errors.append('reasons must be a list')
    else:
        bad = [r for r in reasons if not isinstance(r, str) or r not in ADVERSARY_REASONS]
        if bad:
            errors.append('unknown reasons %r; use only %s' % (bad, ADVERSARY_REASONS))
        if len(set(r for r in reasons if isinstance(r, str))) != len(reasons):
            errors.append('reasons repeat a value')
        if not reasons and verdict != 'survives':
            errors.append('a %s verdict needs at least one reason' % (verdict,))
    note = a.get('note', '')
    if not isinstance(note, str):
        errors.append('note must be a string')
    elif len(note) > MAX_NOTE:
        errors.append('note has %d characters, at most %d allowed' % (len(note), MAX_NOTE))
    return not errors, errors


def parse_json(text):
    """The outermost JSON object or array in a model reply, or None. Never raises.

    Tolerates markdown code fences and prose before and after: every '{' or '[' that starts a valid JSON value is a
    candidate, a candidate nested in an earlier one is skipped, and the longest one wins. Bare scalars give None.
    """
    if not isinstance(text, str):
        return None
    dec = json.JSONDecoder()
    best, best_len, i, n = None, 0, 0, len(text)
    try:
        while i < n:
            if text[i] not in '{[':
                i += 1
                continue
            try:
                val, end = dec.raw_decode(text, i)
            except ValueError:
                i += 1
                continue
            if end - i > best_len:
                best, best_len = val, end - i
            i = end
    except (RecursionError, MemoryError):
        return None
    return best if isinstance(best, (dict, list)) else None
