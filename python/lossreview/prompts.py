"""Prompt builders and the deterministic helpers around the review LLMs. No model is called from this package.

The steps themselves run elsewhere (a Claude routine); this module supplies what surrounds them:
  - TEMPLATES / MODEL_FOR / prompt_hash: the instruction text of each step, the model it runs on, and a stable hash of
    the text (logged with every call, so a changed prompt is visible in the usage log);
  - trip_view and the build_*_prompt functions: what a model is shown. Ex-ante and outcome columns go in separate
    blocks; tickers and times never leave (a trade is shown by an index); the adversary and the audit see aggregates only;
  - matches / control_stats: the blind control. A hypothesis is tested on the losers and on the winners with the same
    rule; a rule that hits winners as often as losers explains nothing;
  - canary_trip / canary_hypotheses / run_canary: known-good and known-bad inputs that must keep passing and failing;
  - usage_record / budget_check: the usage log and the token allowance.
The LLM proposes, code decides: every reply goes through forms.py before anything acts on it.
"""
import datetime
import hashlib
import json
import math

from . import forms, schema, triage

MODEL_FOR = {'tag': 'claude-haiku-5-5', 'hypothesize': 'claude-sonnet-5-5', 'adversary': 'claude-sonnet-5-5', 'audit': 'claude-opus-5-5'}

MAX_TAG_ROWS = 25
MAX_HYPOTHESIS_ROWS = 12
MAX_REGISTERED_SHOWN = 60
# Identifiers and times that would let a reader find the trade again. Never shown to a model, never a key of a prompt input.
PRIVATE_KEYS = forms.IDENTIFIER_COLUMNS | {'closed_utc', 'closed_t'}

CLASS_HELP = {
    'FEE_ONLY': 'gross before fees was at or above zero; the fees made it a loss',
    'CUT_THEN_WON': 'a loser cut sold the side, and the side then settled as the winner',
    'SOLD_THEN_WON': 'another sale (ratchet, pacer, end rule) of a side that then settled as the winner',
    'RIGHT_THEN_REVERSED': 'the side lost at settlement but a profitable exit was reachable on the way',
    'WRONG_SIDE': 'the side lost at settlement and no profitable exit was reachable',
}
REASON_HELP = {
    'confounded_by_price': 'the feature only stands in for the entry price',
    'confounded_by_coin': 'the feature only stands in for which coin it is',
    'clustered_in_time': 'the hits sit in a few hours or one day, not spread out',
    'too_few_trips': 'too few trips hit the rule to say anything',
    'winner_control_matches': 'winners hit the rule about as often as losers (lift near 1)',
    'hindsight_feature': 'the feature or the mechanism leans on something known only after the order',
    'overlaps_curve': 'the feature restates a protected heat-curve value (rank, heat, weight, ...)',
    'fee_artifact': 'the loss is the fee schedule, not the call',
    'other': 'none of these; say what in the note',
}


def _fill(text, **kw):
    for k, v in kw.items():
        text = text.replace('<<%s>>' % k, v)
    if '<<' in text:
        raise ValueError('unfilled placeholder in a template')
    return text


_TAG_LINES = '\n'.join('  %s: %s [%s]' % (t, forms.TAG_HELP[t], ', '.join(cols)) for t, cols in forms.TAGS.items())
_LEVER_LINES = '\n'.join('  %s: %s' % (lv, forms.LEVER_HELP[lv]) for lv in forms.LEVERS)
_REASON_LINES = '\n'.join('  %s: %s' % (r, REASON_HELP[r]) for r in forms.ADVERSARY_REASONS)
_FEATURE_LIST = ', '.join(c + (' (curve)' if c in schema.CURVE_COLUMNS else '') for c in forms.FEATURE_COLUMNS)
_OUTCOME_LIST = ', '.join(forms.OUTCOME_COLUMNS)
_CLASSES = ', '.join(forms.HYPOTHESIS_CLASSES)
_LABELS = ', '.join(sorted(forms.CATEGORICAL_COLUMNS))

_INTRO = ('You are one cheap step in a loss-review loop for a paper-trading bot (the "heat lane" on Kalshi crypto markets).\n'
          'You PROPOSE only. Code validates what you write, measures it against winning trades and decides what happens; '
          'nothing you say is acted on directly.\n'
          'Reply with JSON only: one JSON value, no prose, no markdown fences. Anything outside the closed lists below is '
          'rejected, not repaired.\n')

_TAG = _INTRO + """
TASK
Each losing trade below is shown by its EX_ANTE block: what was known when the order went out. Give each trade the tags
from the closed list that clearly apply, judged from the values shown. Give no tag when unsure. One unknown tag rejects
the whole reply. Never tag from a guess about how the trade ended.

TAGS (name: meaning [columns it is judged from])
<<TAGS>>

FORM
{"trips": [{"i": 0, "tags": ["late_entry", "no_side"]}, {"i": 1, "tags": []}]}
Answer once for every index shown, in order, each tag at most once per trade.
"""

_HYPOTHESIZE = _INTRO + """
Each trade is shown in two blocks. EX_ANTE columns were known when the order went out. OUTCOME columns say what happened
afterwards: they are context for you, never a feature, a cite or a word in a mechanism text.

TASK
You are shown a sample of losing trades that share one loss class, and aggregates over the whole class. Propose at most 3
hypotheses. Each says: trades with this ex-ante feature value lose more than winners do, and this ONE lever would have
helped. Winners are not shown to you; code tests every threshold of your rule on winners too (the blind control), and a
rule that hits winners as often as losers explains nothing. The loss class is a hindsight label: it describes the
trades, it is not a feature.

FORM (exactly this shape)
{"hypotheses": [{
  "id": "late-cheap-skip",
  "loss_class": "WRONG_SIDE",
  "lever": "skip",
  "feature": "frac_elapsed_at_entry",
  "op": "gt",
  "thresholds": [0.5, 0.6, 0.7],
  "neighbor_features": ["entry_px"],
  "mechanism": "Late entries leave too little time for a cheap side to recover.",
  "cites": ["entry_px", "left_at_entry_s"]
}]}

RULES
- id: 3 to 40 characters from a-z, 0-9, _ and -; not one already registered.
- loss_class: the class shown below, copied exactly (one of <<CLASSES>>).
- lever: exactly one string from this list. When two levers fit, prefer the earlier of: dial, then maker or strike, then
  exit, then skip.
<<LEVERS>>
- feature, neighbor_features, cites: columns from the EX_ANTE list below, nothing else. A column marked (curve) belongs to
  the protected heat curves; using one makes the hypothesis a curve edit that is never promoted without the owner's
  explicit word, so avoid them unless nothing else explains the losses.
- op: lt, gt, between or eq. lt and gt are strict. between takes exactly two numbers [lo, hi] with lo < hi, inclusive.
  eq takes strings or true/false and is the only op for label columns (<<LABELS>>).
- thresholds: 1 to 12 distinct values; code tests each one separately.
- neighbor_features: at most 2, each different from feature.
- mechanism: at most 240 characters of plain words: why this feature would cause these losses, judged at order time. Do
  not write any OUTCOME column name as a word (they are listed below) and never a ticker.
- cites: the EX_ANTE columns that support the hypothesis.
- Prices are dollars per contract. entry_px and entry_px_plan are the price of the side bought; plan_price is in YES terms.
- Do not repeat a hypothesis listed under ALREADY REGISTERED.

EX_ANTE columns you may use: <<FEATURES>>
OUTCOME columns (context only, never use): <<OUTCOME>>
"""

_ADVERSARY = _INTRO + """
TASK
You are the adversary. A hypothesis claims that a rule would have prevented losses. Try to refute it from the statistics
shown. You see aggregates only: judge from the numbers and do not guess at single trades. Statistics are given per
threshold: hit_rate_losers and hit_rate_winners are the shares of losers and of winners the rule hits (winners are the
blind control), lift is their ratio (null when undefined), n_* are counts of trips that had the feature.

FORM (exactly this shape)
{"hypothesis_id": "late-cheap-skip", "verdict": "refuted", "reasons": ["winner_control_matches"], "note": "At most 300 characters."}
hypothesis_id: copy the id of the hypothesis shown.

verdict: one of <<VERDICTS>>.
  survives: the numbers hold up and no reason below applies. reasons may then be empty.
  refuted: at least one reason clearly applies.
  unclear: the numbers cannot tell.
reasons: required unless the verdict is survives. Only from this list:
<<REASONS>>
Code makes the final call; your verdict is one input to it.
"""

_AUDIT = _INTRO + """
TASK
You audit the loop, not single trades. You are shown aggregates only: the registered hypotheses (short form), what the
sweep and the adversary found, and the usage so far. Look for: hypotheses that overlap each other or a protected heat
curve, verdicts that do not follow from the numbers, mechanisms that lean on hindsight in disguise, rules that look like
fee artifacts, and steps whose usage looks wasteful. Report only what you can support from what is shown.

FORM (exactly this shape)
{"findings": [{"hypothesis_id": "<id or null>", "issue": "At most 200 characters.", "severity": "low"}], "summary": "At most 300 characters."}

severity: one of low, medium, high. An empty findings list is a valid answer.
"""

TEMPLATES = {
    'tag': _fill(_TAG, TAGS=_TAG_LINES),
    'hypothesize': _fill(_HYPOTHESIZE, CLASSES=_CLASSES, LEVERS=_LEVER_LINES, LABELS=_LABELS, FEATURES=_FEATURE_LIST,
                         OUTCOME=_OUTCOME_LIST),
    'adversary': _fill(_ADVERSARY, VERDICTS=', '.join(forms.VERDICTS), REASONS=_REASON_LINES),
    'audit': _AUDIT,
}


def prompt_hash(step):
    """sha256 (hex) of the instruction text of a step; stable across runs and machines."""
    if step not in TEMPLATES:
        raise ValueError('unknown step %r; steps are %s' % (step, sorted(TEMPLATES)))
    return hashlib.sha256(TEMPLATES[step].encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------------------------------- what a model sees

def _clean(v):
    """A display value: floats to 4 places, None, '' and non-finite numbers dropped (as None), containers cleaned."""
    if v is None or isinstance(v, (bool, int)):
        return v
    if isinstance(v, float):
        return round(v, 4) if math.isfinite(v) else None
    if isinstance(v, str):
        return v if v.strip() else None
    if isinstance(v, dict):
        return {str(k): c for k, c in ((k, _clean(x)) for k, x in v.items()) if c is not None}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return str(v)


def _legs_summary(legs):
    """The sale legs as a short list of {rule, px, count, below_breakeven}; None when there is no legs value."""
    if isinstance(legs, str):
        legs = forms.parse_json(legs)
    if not isinstance(legs, (list, tuple)):
        return None
    return [{'rule': leg.get('rule'), 'px': _clean(leg.get('px')), 'count': _clean(leg.get('count')),
             'below_breakeven': leg.get('below_breakeven')} for leg in legs if isinstance(leg, dict)]


def trip_view(row):
    """{'ex_ante': {...}, 'outcome': {...}} for one trade row, split by schema.blocks.

    Columns without a value are dropped, floats are rounded to 4 places, the identifiers and times in PRIVATE_KEYS are
    never shown, and the raw legs list is replaced (in the outcome block) by a summary of each sale leg.
    """
    a, o = schema.blocks(row)
    legs = o.pop('legs', None)
    a.pop('legs', None)
    view = {}
    for name, block in (('ex_ante', a), ('outcome', o)):
        shown = {}
        for k in sorted(block, key=str):
            if k in PRIVATE_KEYS:
                continue
            c = _clean(block[k])
            if c is not None:
                shown[str(k)] = c
        view[name] = shown
    summary = _legs_summary(legs)
    if summary is not None:
        view['outcome']['legs'] = summary
    return view


def _key(k):
    if isinstance(k, str):
        return k
    if isinstance(k, bool):
        return 'true' if k else 'false'
    if isinstance(k, (int, float)):
        return '%g' % k
    if isinstance(k, (tuple, list)):
        return '..'.join(_key(x) for x in k)
    return str(k)


def _jsonable(o):
    if isinstance(o, dict):
        return {_key(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set, frozenset)):
        return [_jsonable(x) for x in (sorted(o, key=str) if isinstance(o, (set, frozenset)) else o)]
    if isinstance(o, float):
        return round(o, 4) if math.isfinite(o) else None
    if o is None or isinstance(o, (bool, int, str)):
        return o
    return str(o)


def _dumps(o):
    return json.dumps(_jsonable(o), sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _check_aggregate(o, what):
    """Refuse an input that carries a private key at any depth: aggregates never name a trade."""
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(k, str) and k.strip().lower() in PRIVATE_KEYS:
                raise ValueError('%s carries the private key %r: aggregates only' % (what, k))
            _check_aggregate(v, what)
    elif isinstance(o, (list, tuple, set, frozenset)):
        for x in o:
            _check_aggregate(x, what)


def _guard(text, rows=()):
    """Last check on a rendered prompt: no ticker pattern, and none of the tickers of `rows`."""
    if forms.TICKER_RE.search(text):
        raise ValueError('a ticker would be rendered in the prompt')
    for r in rows:
        t = r.get('ticker') if isinstance(r, dict) else None
        if isinstance(t, str) and len(t) >= 6 and t in text:
            raise ValueError('a ticker would be rendered in the prompt')
    return text


def build_tag_prompt(rows):
    """The tagging prompt for up to MAX_TAG_ROWS loser rows. Each trade is shown by its index (its ex-ante block only)."""
    rows = list(rows)
    if not 1 <= len(rows) <= MAX_TAG_ROWS:
        raise ValueError('the tag prompt takes 1 to %d rows, got %d' % (MAX_TAG_ROWS, len(rows)))
    lines = ['TRIPS (EX_ANTE block only, one per line; answer with the index "i")']
    for i, r in enumerate(rows):
        lines.append(_dumps({'i': i, 'ex_ante': trip_view(r)['ex_ante']}))
    return _guard(TEMPLATES['tag'] + '\n' + '\n'.join(lines) + '\n', rows)


def build_hypothesis_prompt(loss_class, rows, aggregates, registered):
    """The hypothesis prompt for one loss class: up to MAX_HYPOTHESIS_ROWS loser rows (both blocks, by index),
    aggregates over the class, and short strings of the hypotheses already registered (to avoid repeats)."""
    if loss_class not in forms.HYPOTHESIS_CLASSES:
        raise ValueError('loss_class must be one of %s' % (forms.HYPOTHESIS_CLASSES,))
    rows = list(rows)
    if not 1 <= len(rows) <= MAX_HYPOTHESIS_ROWS:
        raise ValueError('the hypothesis prompt takes 1 to %d rows, got %d' % (MAX_HYPOTHESIS_ROWS, len(rows)))
    aggregates = {} if aggregates is None else aggregates
    if not isinstance(aggregates, dict):
        raise ValueError('aggregates must be a dict')
    _check_aggregate(aggregates, 'aggregates')
    reg = [' '.join(str(s).split())[:200] for s in (registered or [])]
    shown = reg[-MAX_REGISTERED_SHOWN:]
    parts = [TEMPLATES['hypothesize'].rstrip(),
             'LOSS CLASS: %s (%s)' % (loss_class, CLASS_HELP[loss_class]),
             'AGGREGATES over the class (no single trades):\n' + _dumps(aggregates),
             'ALREADY REGISTERED (%d%s):\n%s' % (len(reg), '' if len(shown) == len(reg) else ', last %d shown' % len(shown),
                                                 '\n'.join('- ' + s for s in shown) if shown else '(none)'),
             'LOSERS (%d sampled; the index is only for this prompt):' % len(rows)]
    for i, r in enumerate(rows):
        v = trip_view(r)
        parts.append('TRIP %d\nEX_ANTE: %s\nOUTCOME: %s' % (i, _dumps(v['ex_ante']), _dumps(v['outcome'])))
    return _guard('\n\n'.join(parts) + '\n', rows)


def build_adversary_prompt(hypothesis, stats):
    """The adversary prompt: the hypothesis (its form fields only) and aggregate statistics, never a row or a ticker.
    A stats dict that carries a private key at any depth raises ValueError."""
    if not isinstance(hypothesis, dict) or not isinstance(stats, dict):
        raise ValueError('hypothesis and stats must be dicts')
    _check_aggregate(stats, 'stats')
    hyp = {k: hypothesis[k] for k in forms.HYPOTHESIS_KEYS if k in hypothesis}
    text = '\n\n'.join([TEMPLATES['adversary'].rstrip(),
                        'HYPOTHESIS:\n' + _dumps(hyp),
                        'STATISTICS (aggregates; winners are the blind control):\n' + _dumps(stats)]) + '\n'
    return _guard(text)


def build_audit_prompt(aggregates, registered):
    """The audit prompt (aggregates and short hypothesis strings only)."""
    if not isinstance(aggregates, dict):
        raise ValueError('aggregates must be a dict')
    _check_aggregate(aggregates, 'aggregates')
    reg = [' '.join(str(s).split())[:200] for s in (registered or [])]
    shown = reg[-MAX_REGISTERED_SHOWN:]
    text = '\n\n'.join([TEMPLATES['audit'].rstrip(), 'AGGREGATES:\n' + _dumps(aggregates),
                        'REGISTERED (%d, last %d shown):\n%s' % (len(reg), len(shown), '\n'.join('- ' + s for s in shown) or '(none)')]) + '\n'
    return _guard(text)


# ---------------------------------------------------------------------------------------------------- the blind control

def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
    elif isinstance(v, str):
        try:
            x = float(v.strip())
        except ValueError:
            return None
    else:
        return None
    return x if math.isfinite(x) else None


def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        return True if s in ('true', '1', 'yes') else False if s in ('false', '0', 'no') else None
    return None


def _text(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip().lower()


def matches(h, row, threshold):
    """Does `row` meet one threshold of hypothesis `h` (its feature and op)? True or False, or None when the row has no
    usable value for the feature or the threshold is malformed. No eval; a bad input gives None, never an exception.

    lt and gt are strict; between takes a pair [lo, hi] and is inclusive; eq compares text case-insensitively with a
    string threshold and as a boolean with a boolean threshold.
    """
    try:
        feature, op = h['feature'], h['op']
        v = row.get(feature)
    except (KeyError, TypeError, AttributeError):
        return None
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if op == 'eq':
        if isinstance(threshold, bool):
            b = _bool(v)
            return None if b is None else b == threshold
        if isinstance(threshold, str):
            return _text(v) == threshold.strip().lower()
        return None
    x = _num(v)
    if x is None:
        return None
    if op in ('lt', 'gt'):
        t = _num(threshold)
        if t is None:
            return None
        return x < t if op == 'lt' else x > t
    if op == 'between':
        if not isinstance(threshold, (list, tuple)) or len(threshold) != 2:
            return None
        lo, hi = _num(threshold[0]), _num(threshold[1])
        if lo is None or hi is None:
            return None
        return lo <= x <= hi
    return None


def _hits(h, rows, threshold):
    n = hit = 0
    for r in rows:
        m = matches(h, r, threshold)
        if m is not None:
            n += 1
            hit += bool(m)
    return n, hit


def control_stats(h, loser_rows, winner_rows):
    """The winner control of a hypothesis, per threshold: {threshold: {n_losers, n_winners, n_losers_hit, n_winners_hit,
    hit_rate_losers, hit_rate_winners, lift}}. For op 'between' the one key is the pair as a tuple (lo, hi).

    Rows without the feature are left out of every count. A rate is None with no rows to measure; lift is the loser rate
    over the winner rate, None when either is undefined or the winner rate is 0. A lift near 1 means the rule hits winners
    as often as losers and explains nothing.
    """
    try:
        thr = h['thresholds']
        keys = [tuple(thr)] if h['op'] == 'between' else list(thr)
    except (KeyError, TypeError):
        return {}
    out = {}
    for k in keys:
        try:
            hash(k)
        except TypeError:
            continue  # a malformed threshold: the validator rejects it, there is nothing to count
        nl, hl = _hits(h, loser_rows, k)
        nw, hw = _hits(h, winner_rows, k)
        rl = hl / nl if nl else None
        rw = hw / nw if nw else None
        lift = rl / rw if rl is not None and rw else None
        out[k] = {'n_losers': nl, 'n_winners': nw, 'n_losers_hit': hl, 'n_winners_hit': hw,
                  'hit_rate_losers': None if rl is None else round(rl, 4),
                  'hit_rate_winners': None if rw is None else round(rw, 4),
                  'lift': None if lift is None else round(lift, 4)}
    return out


# ---------------------------------------------------------------------------------------------------- the canary

def canary_trip():
    """A synthetic loser (ticker 'CANARY-0') with plausible values in every column the builder writes: a NO buy at 31c
    on an hourly market, cut at 12c; the side lost, but a profitable exit had been reachable (RIGHT_THEN_REVERSED)."""
    return {
        'ticker': 'CANARY-0', 'kind': 'hourly', 'coin': 'ETH', 'side': 'no', 'h': 60, 'call_key': '1m:RSI=high | 15m:BB=high',
        'call_kind': 'pair', 'dir': -1, 'rank': 3, 'of': 24, 'heat': 91.4, 'fired': 4, 'against': 1, 'context': 'agree',
        'weight': 0.35, 'slot': 2, 'era': 'e2', 'call_age_s': 41.5,
        'plan_price': 0.69, 'entry_px_plan': 0.31, 'count_plan': 32, 'stake_plan': 10.0,
        'entry_utc': '11-12 15:41:07', 'entry_t': 1794498067.0, 'window_close_t': 1794499200.0,
        'left_at_entry_s': 1133.0, 'frac_elapsed_at_entry': 0.6853, 'strike': 3200.0,
        'spot_pre_entry': 3224.8, 'spot_pre_age_s': 7.0, 'spot_vs_strike_bps_pre': 77.5,
        'lane': 'heat',
        # known one minute after the entry or later: the outcome block
        'bid_entry_min': 0.30, 'bid_1m': 0.33, 'bid_2m': 0.36, 'bid_5m': 0.12,
        'spot_entry': 3226.1, 'spot_vs_strike_bps': 81.5625, 'spot_bps_1m_for_side': -4.0, 'spot_bps_5m_for_side': -9.5,
        'spot_bps_15m_for_side': -12.0,
        'count': 32.0, 'entry_px': 0.31, 'stake': 9.92, 'entry_taker': True, 'entry_maker_any': False, 'entry_fee': 0.48,
        'closed_utc': '11-12 15:52:30', 'closed_t': 1794498750.0, 'hold_s': 683.0,
        'exit_event': 'loser_cut', 'exit_bid': 0.12, 'exit_px': 0.12, 'exit_fee': 0.24, 'fees': 0.72,
        'pnl': -6.8, 'won': False, 'pnl_fills': -6.8, 'pnl_gap': 0.0, 'pnl_source': 'logged', 'settled': False,
        'held_to_end': 0.0, 'result': 'yes', 'side_settles_win': False,
        'best_bid_held': 0.36, 'worst_bid_held': 0.12, 'best_bid_after_exit': 0.08, 'worst_bid_after_exit': 0.02,
        'n_sale_legs': 1,
        'legs': [{'t': 1794498740.2, 'rule': 'loser_cut', 'px': 0.12, 'count': 32.0, 'fee': 0.24, 'taker': True,
                  'net_vs_cost': -6.8, 'below_breakeven': True, 'bid_at_event': 0.12}],
        'defect_sale': False, 'defect_dollars': 0.0, 'fee_estimated': False, 'orphan_fill': False, 'fidelity_flag': False,
    }


def _clean_hypothesis():
    return {'id': 'canary-clean', 'loss_class': 'WRONG_SIDE', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'gt',
            'thresholds': [0.5, 0.6, 0.7], 'neighbor_features': ['entry_px'],
            'mechanism': 'Late entries leave too little time for a cheap side to recover.',
            'cites': ['entry_px', 'left_at_entry_s']}


# id -> (a substring the errors must contain for a hypothesis that must fail, the flags a passing one must return)
_CANARY_EXPECT = {
    'canary-curve-rank': (None, ['curve_edit']),
    'canary-cites-outcome': ('best_bid_held', []),
    'canary-feature-outcome': ('bid_5m', []),
    'canary-13-thresholds': ('thresholds', []),
    'canary-unknown-column': ('unknown column', []),
    'canary-mechanism-leak': ('mechanism names outcome', []),
    'canary-extra-key': ('unknown key', []),
    'canary-two-levers': ('lever', []),
    'canary-three-neighbors': ('neighbor_features', []),
    'canary-bad-class': ('loss_class', []),
    'canary-between-reversed': ('lo < hi', []),
    'canary-ticker-feature': ('identifier', []),
}


def canary_hypotheses():
    """[(hypothesis, should_pass)]: one clean hypothesis, one that passes with the 'curve_edit' flag, and bad ones that
    each break one rule (an outcome column cited, 13 thresholds, an unknown column, ...). run_canary checks all of them."""
    c = _clean_hypothesis
    return [
        (c(), True),
        (dict(c(), id='canary-curve-rank', feature='rank', thresholds=[1, 2, 3], neighbor_features=[],
              mechanism='Low-ranked calls in a batch carry less edge.', cites=['of']), True),
        (dict(c(), id='canary-cites-outcome', cites=['entry_px', 'best_bid_held']), False),
        (dict(c(), id='canary-feature-outcome', feature='bid_5m', op='lt', thresholds=[0.2]), False),
        (dict(c(), id='canary-13-thresholds', thresholds=[round(0.3 + 0.03 * i, 2) for i in range(13)]), False),
        (dict(c(), id='canary-unknown-column', feature='moon_phase'), False),
        (dict(c(), id='canary-mechanism-leak', mechanism='It loses because best_bid_held rose and then fell back.'), False),
        (dict(c(), id='canary-extra-key', confidence=0.9), False),
        (dict(c(), id='canary-two-levers', lever=['dial', 'skip']), False),
        (dict(c(), id='canary-three-neighbors', neighbor_features=['entry_px', 'stake', 'count']), False),
        (dict(c(), id='canary-bad-class', loss_class='UNEXPLAINED'), False),
        (dict(c(), id='canary-between-reversed', op='between', thresholds=[0.7, 0.4]), False),
        (dict(c(), id='canary-ticker-feature', feature='ticker', op='eq', thresholds=['CANARY-0']), False),
    ]


def run_canary():
    """(ok, failures): push the canary inputs through the validators and the views. A failure means a guard rail broke."""
    fails = []
    for h, should_pass in canary_hypotheses():
        ok, errors, flags = forms.validate_hypothesis(h)
        want_err, want_flags = _CANARY_EXPECT.get(h['id'], (None, []))
        if ok != should_pass:
            fails.append('%s: expected %s, got %s %s' % (h['id'], 'pass' if should_pass else 'fail', 'pass' if ok else 'fail', errors))
        elif should_pass and flags != want_flags:
            fails.append('%s: expected flags %s, got %s' % (h['id'], want_flags, flags))
        elif not should_pass and want_err and not any(want_err in e for e in errors):
            fails.append('%s: failed for another reason: %s' % (h['id'], errors))
    trip = canary_trip()
    v = trip_view(trip)
    leaked = sorted(c for c in v['ex_ante'] if not schema.ex_ante(c))
    if leaked:
        fails.append('trip_view: outcome columns in the ex-ante block: %s' % leaked)
    if any(c in v['ex_ante'] or c in v['outcome'] for c in PRIVATE_KEYS) or 'CANARY-0' in _dumps(v):
        fails.append('trip_view: a private column is shown')
    if any(set(leg) != {'rule', 'px', 'count', 'below_breakeven'} for leg in v['outcome'].get('legs', [])):
        fails.append('trip_view: legs are not summarised')
    if triage.classify(trip)['primary'] not in forms.HYPOTHESIS_CLASSES:
        fails.append('canary_trip is not a reviewable loser: %s' % triage.classify(trip)['primary'])
    if not forms.validate_tags(['late_entry', 'no_side'])[0] or forms.validate_tags(['late_entry', 'not_a_tag'])[0]:
        fails.append('validate_tags: the closed list is not enforced')
    if forms.parse_json('Here you go:\n```json\n{"a": [1, 2]}\n```\nDone.') != {'a': [1, 2]} or forms.parse_json('no json here') is not None:
        fails.append('parse_json: fence or prose handling broke')
    good = {'hypothesis_id': 'canary-clean', 'verdict': 'refuted', 'reasons': ['fee_artifact'], 'note': 'x'}
    if not forms.validate_adversary(good)[0] or forms.validate_adversary(dict(good, reasons=[]))[0] \
            or forms.validate_adversary(dict(good, reasons=['because']))[0]:
        fails.append('validate_adversary: the closed lists are not enforced')
    try:
        build_adversary_prompt(_clean_hypothesis(), {'by_trade': [{'ticker': 'CANARY-0'}]})
        fails.append('build_adversary_prompt: a ticker key was accepted')
    except ValueError:
        pass
    return not fails, fails


# ---------------------------------------------------------------------------------------------------- the usage log

def _date(d):
    if isinstance(d, datetime.datetime):
        return d.date()
    if isinstance(d, datetime.date):
        return d
    return datetime.date.fromisoformat(d)


def usage_record(step, model, prompt_hash_, tokens_in, tokens_out, items, day):
    """One line of the usage log: a step run on `items` items. day is a date or 'YYYY-MM-DD' and is stored as the latter."""
    if step not in MODEL_FOR:
        raise ValueError('unknown step %r; steps are %s' % (step, sorted(MODEL_FOR)))
    for name, v in (('tokens_in', tokens_in), ('tokens_out', tokens_out), ('items', items)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError('%s must be a non-negative integer' % name)
    return {'day': _date(day).isoformat(), 'step': step, 'model': model, 'prompt_hash': prompt_hash_,
            'tokens_in': tokens_in, 'tokens_out': tokens_out, 'items': items}


def budget_check(records, day, daily_allowance_tokens, week_allowance_tokens=None):
    """Tokens (in + out) used on `day` against the daily allowance, and, when week_allowance_tokens is given, in the 7 days
    ending at `day` (today included) against the weekly one.

    Returns {'used_today', 'remaining_today', 'ok', 'reason', 'used_week', 'remaining_week'}. remaining_today is the
    smaller of what is left of the daily and of the weekly allowance; ok is False when it is 0. used_week is always
    summed; remaining_week is None without a weekly allowance. Records of later days, and records that cannot be read
    (no usable day or token counts), are not counted.
    """
    for name, v in (('daily_allowance_tokens', daily_allowance_tokens), ('week_allowance_tokens', week_allowance_tokens)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
            raise ValueError('%s must be a non-negative number' % name)
    today = _date(day)
    start = today - datetime.timedelta(days=6)
    used_today = used_week = 0
    for r in records:
        try:
            d = _date(r['day'])
            t = int(r['tokens_in']) + int(r['tokens_out'])
        except (KeyError, TypeError, ValueError):
            continue
        if d == today:
            used_today += t
        if start <= d <= today:
            used_week += t
    left_day = max(0, daily_allowance_tokens - used_today)
    left_week = None if week_allowance_tokens is None else max(0, week_allowance_tokens - used_week)
    remaining = left_day if left_week is None else min(left_day, left_week)
    if left_day <= 0:
        reason = 'daily allowance of %d tokens is used' % daily_allowance_tokens
    elif left_week is not None and left_week <= 0:
        reason = 'weekly allowance of %d tokens is used' % week_allowance_tokens
    else:
        reason = 'within the allowance'
    return {'used_today': used_today, 'remaining_today': remaining, 'ok': remaining > 0, 'reason': reason,
            'used_week': used_week, 'remaining_week': left_week}
