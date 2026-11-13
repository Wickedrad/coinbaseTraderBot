"""What may leave the routine in a public workflow input.

The routine's model replies travel in the `responses` input of loss-review-stages.yml, and a dispatch input is public the moment
it is sent (the run record and the job's env block show it), before any stage can look at it. The prompts show a reviewer up to
12 losers with their dollars, stakes, strikes and spot levels (never a ticker or a clock time), so a reply that quotes those
numbers would publish them. This module makes a reply safe to send: it keeps only the fields of the step's own form, drops
prose, rounds a threshold to 3 significant figures (an exact spot level or strike finds its minute on the public tape) and removes
digits, dollar signs and percent signs from free text (a mechanism or a note names a pattern, it quotes no figure).

    python3 -m lossreview.screen tag-00|hyp-CLASS|adv-ID  < reply.txt   > screened.json

The routine runs this on every reply before it is put in a dispatch. The `responses` stage accepts only a reply that screening
leaves unchanged (the screened form is a fixed point), so an unscreened reply is refused instead of being stored.
"""
import json
import math
import re
import sys

from . import forms, prompts

SIG = 3
TEXT_CAP = 240
MAX_HYP_ITEMS = 6
_JUNK = re.compile(r'[0-9$%]+')
# an eq threshold names a category (BTC, 15m, hourly, yes): a short word, at most 3 digits, nothing that could be an id or a level
_EQ_WORD = re.compile(r'^(?!(?:.*\d){4})[A-Za-z0-9_]{1,16}$')


def clean_text(s, cap=TEXT_CAP):
    s = _JUNK.sub('', s if isinstance(s, str) else '')
    s = ' '.join(s.split())[:cap].strip()
    return s if re.search('[A-Za-z]', s) else ''


def sig(x):
    """x to SIG significant figures; an integer below 1000 stays as it is."""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return x
    if isinstance(x, int) and abs(x) < 10 ** SIG:
        return x
    y = float('%.*g' % (SIG, x))
    return int(y) if y == int(y) and abs(y) < 1e15 else y


def _items(obj, key):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and isinstance(obj.get(key), list):
        return obj[key]
    return None


def screen_tags(obj):
    out = []
    for it in _items(obj, 'trips') or []:
        if not isinstance(it, dict):
            continue
        i = it.get('i')
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < prompts.MAX_TAG_ROWS:
            continue
        if forms.validate_tags(it.get('tags'))[0]:
            out.append({'i': i, 'tags': list(it['tags'])})
    return out


def _thresholds(h):
    thr = h.get('thresholds')
    if not isinstance(thr, list):
        return thr
    if h.get('op') == 'eq':
        return [t for t in thr if isinstance(t, bool) or (isinstance(t, str) and _EQ_WORD.match(t))]
    seen, out = set(), []
    for t in thr:
        t = sig(t)
        if isinstance(t, (int, float)) and not isinstance(t, bool):
            if t in seen:
                continue
            seen.add(t)
        out.append(t)
    return out


def screen_hyp(obj):
    out = []
    for h in _items(obj, 'hypotheses') or []:
        if not isinstance(h, dict) or len(out) >= MAX_HYP_ITEMS:
            continue
        c = {k: h[k] for k in forms.HYPOTHESIS_KEYS if k in h}
        c['mechanism'] = clean_text(c.get('mechanism')) or 'not stated'
        c['thresholds'] = _thresholds(c)
        if c.get('op') == 'between' and isinstance(c['thresholds'], list):
            c['thresholds'] = sorted(c['thresholds']) if all(isinstance(t, (int, float)) for t in c['thresholds']) else c['thresholds']
        if forms.validate_hypothesis(c)[0]:
            out.append(c)
    return out


def screen_adv(obj):
    if not isinstance(obj, dict):
        return None
    c = {k: obj[k] for k in forms.ADVERSARY_KEYS if k in obj}
    if 'note' in c:
        c['note'] = clean_text(c['note'], forms.MAX_NOTE)
    return c if forms.validate_adversary(c)[0] else None


def screen_reply(name, obj):
    """The screened form of a reply (parsed JSON) to the prompt `name` (tag-NN, hyp-CLASS, adv-ID). Raises ValueError for a reply
    with nothing usable in it."""
    if name.startswith('tag-'):
        out = screen_tags(obj)
    elif name.startswith('hyp-'):
        out = screen_hyp(obj)
    elif name.startswith('adv-'):
        out = screen_adv(obj)
    else:
        raise ValueError('unknown reply name %r' % name)
    if out is None or out == []:
        raise ValueError('nothing usable in the reply to %s after screening' % name)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print('usage: python3 -m lossreview.screen NAME < reply.txt  (NAME: tag-NN, hyp-CLASS or adv-ID)', file=sys.stderr)
        return 2
    obj = forms.parse_json(sys.stdin.read())     # prose and code fences around the JSON are tolerated here, and only here
    if obj is None:
        print('no JSON object or array in the reply', file=sys.stderr)
        return 1
    try:
        out = screen_reply(argv[0], obj)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(out, separators=(',', ':'), sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
