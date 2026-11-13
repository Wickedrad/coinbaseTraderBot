"""The daily loop's mechanical stages, one command each, over a work folder W (pulled from and put back to Drive).

    W/days/trips-DAY.jsonl     the nightly trip files (per-trade, private)
    W/registry.jsonl           the candidate registry (append-only events; hypothesis and rule specs, verdicts, shadow days)
    W/usage.jsonl              one line per model step: model, prompt hash, tokens, items (the token log)
    W/work/DAY/                prompts written for the model steps and the responses it left (private)

Stages (the model steps sit between them; docs/LOSS_REVIEW_ROUTINE.md has the routine):
    prepare-tags DAY      -> work/DAY/tag-NN.prompt.txt (+ tag-index.json)         [Haiku writes tag-NN.response.json]
    apply-tags DAY        -> work/DAY/tags.json, per-class counts
    prepare-hyp DAY       -> work/DAY/hyp-CLASS.prompt.txt                         [Sonnet writes hyp-CLASS.response.json]
    apply-hyp DAY         -> validated hypotheses, adversary prompts adv-ID.prompt.txt with the blind winner control
                                                                                   [Sonnet writes adv-ID.response.json]
    apply-adv DAY         -> registers survivors (every threshold and neighbor candidate a trial); refuted ones are registered and retired
    sweep DAY             -> scores every open hypothesis on the days after its generating losses; freezes a candidate that survives BH
    shadow DAY            -> flags DAY's trips with every frozen rule; pools the shadow days; drafts nothing, only reports 'ready'
    status                -> counts by state, trials, token use (aggregates only)
    usage DAY --step S --tokens-in N --tokens-out N --items K   -> logs one model step, prints what is left of the allowance
    budget DAY [--daily N] [--weekly N]                         -> the allowance check the routine makes before each model step
    pending               -> the days that have a trip file and have not been marked done, oldest first (the routine takes them in order)
    window DAY [--since HH:MM[:SS]] [--until HH:MM[:SS]]  -> aggregates of the trips closed in that UTC window to work/DAY/window-*.json (log: count only)
    responses DAY         -> writes the model steps' replies (a JSON object {name: reply} in $LR_RESPONSES) to work/DAY/NAME.response.json
    canary                -> the validators' known-good and known-bad inputs; exit 1 if a guard rail broke (the script runs it before every stage)
    done DAY              -> marks DAY finished (work/DAY/done.json) once the stages above have run
Printed output is aggregates only; every per-trade file stays in W.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

from . import forms, ledger, nightly, prompts, registry, rules, shadow, stats, sweep, triage

REVIEW_CAP = 75          # losers a day get a model review (worst dollars first)
TAG_BATCH = 25
HYP_MIN_LOSERS = 3       # a class needs this many reviewed losers before a hypothesis is asked for
HYP_ROWS = 12
HYP_PER_CLASS = 3        # the prompt asks for at most 3 a class; the code enforces it
HYP_PER_DAY = 6          # adversary calls a day (docs/LOSS_REVIEW_ROUTINE.md)
REVIEW_CLASSES = forms.HYPOTHESIS_CLASSES


def trip_id(r):
    return hashlib.sha256(('%s|%s' % (r.get('ticker'), r.get('entry_t'))).encode()).hexdigest()[:10]


def load_days(w, scoring=False):
    """{day: rows}. scoring=True keeps out of the evidence every trip the builder could not vouch for (fidelity_flag: orphan or
    duplicate fills, a P&L the fills do not explain, a remainder whose result is unknown) and any trip with no P&L, as
    docs/LOSS_REVIEW.md promises; a day with nothing left still appears (as a day without trips)."""
    out = {}
    for p in sorted(glob.glob(os.path.join(w, 'days', 'trips-*.jsonl'))):
        day = os.path.basename(p)[len('trips-'):-len('.jsonl')]
        with open(p, encoding='utf-8') as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
        out[day] = [r for r in rows if not r.get('fidelity_flag') and r.get('pnl') is not None] if scoring else rows
    return out


def all_rows(days):
    return [r for d in sorted(days) for r in days[d]]


def reviewable(rows):
    ls = [r for r in rows if r.get('class') in REVIEW_CLASSES and not r.get('fidelity_flag')]
    return sorted(ls, key=lambda r: r.get('pnl') or 0)[:REVIEW_CAP]


def workdir(w, day):
    p = os.path.join(w, 'work', day)
    os.makedirs(p, exist_ok=True)
    return p


def _dump(path, obj):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, indent=1, default=str)


def _read_json(path):
    with open(path, encoding='utf-8') as fh:
        return forms.parse_json(fh.read())


DAILY_TOKENS = 600_000     # the routine's allowance (docs/LOSS_REVIEW_ROUTINE.md: about 0.4 to 0.6 million tokens a day)


def log_usage(w, rec):
    with open(os.path.join(w, 'usage.jsonl'), 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(rec) + '\n')


def read_usage(w):
    """The usage log as dicts; a blank, torn or non-object line is skipped (budget_check skips unreadable records the same way)."""
    p = os.path.join(w, 'usage.jsonl')
    out = []
    if os.path.exists(p):
        with open(p, encoding='utf-8') as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    out.append(r)
    return out


def usage(w, day, step, tokens_in, tokens_out, items):
    """Log one model step (the model and the prompt hash come from the step) and return what is left of the allowance."""
    if step not in prompts.MODEL_FOR:
        raise ValueError('unknown step %r; steps are %s' % (step, sorted(prompts.MODEL_FOR)))
    rec = prompts.usage_record(step, prompts.MODEL_FOR[step], prompts.prompt_hash(step), tokens_in, tokens_out, items, day)
    log_usage(w, rec)
    return budget(w, day)


def budget(w, day, daily=DAILY_TOKENS, weekly=None):
    return prompts.budget_check(read_usage(w), day, daily, weekly)


def prepare_tags(w, day):
    days = load_days(w)
    rows = reviewable(days.get(day, []))
    wd = workdir(w, day)
    index = {}
    for b in range(0, len(rows), TAG_BATCH):
        batch = rows[b:b + TAG_BATCH]
        name = 'tag-%02d' % (b // TAG_BATCH)
        with open(os.path.join(wd, name + '.prompt.txt'), 'w', encoding='utf-8') as fh:
            fh.write(prompts.build_tag_prompt(batch))
        index[name] = {str(i): trip_id(r) for i, r in enumerate(batch)}
    _dump(os.path.join(wd, 'tag-index.json'), index)
    return {'reviewable': len(rows), 'batches': len(index)}


def apply_tags(w, day):
    wd = workdir(w, day)
    index = _read_json(os.path.join(wd, 'tag-index.json')) or {}
    tags, bad = {}, 0
    for name, ids in index.items():
        p = os.path.join(wd, name + '.response.json')
        resp = _read_json(p) if os.path.exists(p) else None
        items = resp if isinstance(resp, list) else (resp or {}).get('trips') if isinstance(resp, dict) else None
        for it in items or []:
            tid = ids.get(str(it.get('i'))) if isinstance(it, dict) else None
            ok, _errs = forms.validate_tags(it.get('tags')) if tid else (False, None)
            if ok:
                tags[tid] = it['tags']
            else:
                bad += 1
    _dump(os.path.join(wd, 'tags.json'), tags)
    return {'tagged': len(tags), 'rejected': bad}


def prepare_hyp(w, day):
    days = load_days(w)
    rows = reviewable(days.get(day, []))
    wd = workdir(w, day)
    tags = _read_json(os.path.join(wd, 'tags.json')) if os.path.exists(os.path.join(wd, 'tags.json')) else {}
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    known = ['%s: %s %s %s (%s)' % (i, s['rule'].get('feature'), s['rule'].get('op'), s['rule'].get('thresholds'), s['status'])
             for i, s in reg.state.items()][-40:]
    written = []
    for cls in REVIEW_CLASSES:
        cr = [r for r in rows if r.get('class') == cls]
        if len(cr) < HYP_MIN_LOSERS:
            continue
        counts = {}
        for r in cr:
            for t in (tags or {}).get(trip_id(r), []):
                counts[t] = counts.get(t, 0) + 1
        agg = {'losers': len(cr), 'dollars': round(sum(r['pnl'] for r in cr), 2), 'tag_counts': counts}
        with open(os.path.join(wd, 'hyp-%s.prompt.txt' % cls), 'w', encoding='utf-8') as fh:
            fh.write(prompts.build_hypothesis_prompt(cls, cr[:HYP_ROWS], agg, known))
        written.append(cls)
    return {'classes': written}


def _spec_key(h):
    """The idea, not its name: a hypothesis that repeats a registered one under a new id is the same trial."""
    return (h.get('loss_class'), h.get('lever'), h.get('feature'), h.get('op'))


def apply_hyp(w, day):
    days = load_days(w, scoring=True)
    rows = all_rows({d: v for d, v in days.items() if d <= day})
    losers = [r for r in rows if r['pnl'] < 0]
    winners = [r for r in rows if r['pnl'] >= 0]
    wd = workdir(w, day)
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    seen_ids = set(reg.state)
    seen_specs = {_spec_key(s['rule']) for s in reg.state.values() if s['kind'] == 'hypothesis'}
    ok_h, bad, curve = [], 0, 0
    for cls in REVIEW_CLASSES:
        p = os.path.join(wd, 'hyp-%s.response.json' % cls)
        resp = _read_json(p) if os.path.exists(p) else None
        items = resp if isinstance(resp, list) else (resp or {}).get('hypotheses') if isinstance(resp, dict) else None
        n_cls = 0
        for h in items or []:
            ok, errs, flags = forms.validate_hypothesis(h) if isinstance(h, dict) else (False, ['not an object'], [])
            if not ok:
                bad += 1
                continue
            if h.get('loss_class') != cls:
                bad += 1
                continue
            # What the model may ask for is capped here, not trusted: a few hypotheses a class and a day (each one is a trial
            # that raises the registry's family for every honest candidate), unique ids (the adversary prompt and its verdict are
            # keyed by id) and no re-run of an idea already registered, refuted ones included.
            if n_cls >= HYP_PER_CLASS or len(ok_h) >= HYP_PER_DAY or h['id'] in seen_ids or _spec_key(h) in seen_specs:
                bad += 1
                continue
            n_cls += 1
            seen_ids.add(h['id'])
            seen_specs.add(_spec_key(h))
            h = dict(h, neighbor_features=h.get('neighbor_features') or [], cites=h.get('cites') or [])
            curve += 1 if 'curve_edit' in flags else 0
            cls_losers = [r for r in losers if r.get('class') == cls]
            stats_ = prompts.control_stats(h, cls_losers, winners)
            with open(os.path.join(wd, 'adv-%s.prompt.txt' % h['id']), 'w', encoding='utf-8') as fh:
                fh.write(prompts.build_adversary_prompt(h, stats_))
            ok_h.append(h)
    _dump(os.path.join(wd, 'hypotheses.json'), ok_h)
    return {'valid': len(ok_h), 'rejected': bad, 'curve_edits': curve}


def n_candidates(h):
    thresholds = 1 if h['op'] == 'between' else len(h['thresholds'])
    return thresholds + (len(h.get('neighbor_features') or []) * len(sweep.QUARTILES) if h['op'] in ('lt', 'gt') else 0)


def apply_adv(w, day):
    wd = workdir(w, day)
    hs = _read_json(os.path.join(wd, 'hypotheses.json')) or []
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    kept = refuted = 0
    for h in hs:
        if h['id'] in reg.state:
            continue
        p = os.path.join(wd, 'adv-%s.response.json' % h['id'])
        a = _read_json(p) if os.path.exists(p) else None
        ok, _ = forms.validate_adversary(a) if isinstance(a, dict) else (False, None)
        verdict = a['verdict'] if ok and a.get('hypothesis_id') == h['id'] else 'unclear'
        reg.register(h, day, [day], trials=n_candidates(h), kind='hypothesis')
        if verdict == 'refuted':
            reg.move(h['id'], 'retired', 'adversary refuted: %s' % ','.join(a.get('reasons') or []))
            refuted += 1
        else:
            kept += 1
    return {'registered_open': kept, 'registered_refuted': refuted}


def _hyp_of(state):
    return state['rule']


def run_sweep(w, day):
    """One fixed look for every open hypothesis that has enough scoring days for its next look (sweep.SWEEP_LOOKS), on exactly
    that look's first days. A hypothesis is not re-scored between looks. A candidate that survives BH over the registry is
    frozen; the last look without one retires it. Levers the trip file cannot price get a replay request instead."""
    days = load_days(w, scoring=True)
    rows = all_rows(days)
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    best_p, results, windows = {}, {}, {}
    looked = replayed = retired = 0
    for rid in reg.by_status('proposed') + reg.by_status('swept'):
        s = reg.state[rid]
        if s['kind'] != 'hypothesis' or s.get('frozen'):
            continue
        h = s['rule']
        if h['lever'] not in rules.SCORED_LEVERS:
            if not s['scores']:
                reg.score(rid, {'day': day, 'replay': sweep.replay_request(h, s['generating_days']), 'best': None})
                reg.move(rid, 'swept', 'a replay prices this lever')
                replayed += 1
            continue
        done = sum(1 for v in s['scores'] if v.get('look') is not None)
        if done >= len(sweep.SWEEP_LOOKS):
            continue
        need = sweep.SWEEP_LOOKS[done]
        scoring_days = sorted({sweep.day_of(r) for r in sweep.scoring_rows(rows, s['generating_days'])})
        if len(scoring_days) < need:
            continue
        res = sweep.sweep(h, rows, s['generating_days'], max_days=need)
        results[rid] = res
        windows[rid] = scoring_days[need - 1]
        b = res['best']
        reg.score(rid, {'day': day, 'look': done, 'look_days': need, 'k': res['k'], 'dropped': res['dropped'], 'best': None if not b else {
            'rule': b['rule'], 'verdict': b['verdict'], 'p_adj': b['p_adj'], 'flagged': b['flagged'], 'days': b['pooled']['days'],
            'gap_sum': round(b['pooled']['sum'], 2), 'gain_sum': round(b['gain_sum'], 2), 'retention': round(b['retention'], 3)}})
        looked += 1
        if s['status'] == 'proposed':
            reg.move(rid, 'swept', 'first look')
        if b and b['verdict'] == 'candidate' and b['p_adj'] is not None:
            best_p[rid] = b['p_adj']
    survivors = set(sweep.registry_fdr(best_p, reg.family_size()))
    moved = []
    for rid, res in results.items():
        st = reg.state[rid]
        if rid in survivors:
            reg.freeze(rid, res['best']['rule'], windows[rid])
            if not reg.state[rid]['curve_edit'] or (reg.state[rid]['owner_ok'] and reg.state[rid]['owner_ok_hash'] == reg.state[rid]['frozen_hash']):
                reg.move(rid, 'shadow', 'candidate that survives BH over the registry')
                moved.append(rid)
        elif sum(1 for v in st['scores'] if v.get('look') is not None) >= len(sweep.SWEEP_LOOKS):
            reg.move(rid, 'retired', 'no candidate at the last look')
            retired += 1
    return {'looked': looked, 'replay_requests': replayed, 'candidates': len(best_p), 'survived_fdr': len(survivors),
            'to_shadow': len(moved), 'retired': retired, 'trials': reg.trials}


def run_shadow(w, day):
    """Flag every available day after a shadow rule's sweep window, up to `day`, that it has not seen yet (a night missed is
    caught up; a day re-run replaces itself). Reads the verdict at the fixed looks; 'ready' moves the rule to `proposal`
    (a promotion PR for the owner, never merged by the routine) and 'faded' retires it.

    The floor is a gate on the SET of skip rules, not on one rule at a time: rules already in proposal or live count first, then
    the rules that are ready now, best gain first, and a ready rule that would push the union of flagged trips past 15% of the
    trips on the pooled shadow days stays in shadow ('held_by_floor') until the set fits."""
    days = load_days(w, scoring=True)
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    ready, faded = [], []
    verdicts = {}
    for rid in reg.by_status('shadow'):
        s = reg.state[rid]
        have = {r['day'] for r in s['shadow']}
        for d in sorted(days):
            if (s.get('frozen_day') and d <= s['frozen_day']) or d > day or d in have:
                continue
            reg.shadow(rid, shadow.shadow_day(s['frozen'], s['frozen_hash'], d, days[d]))
        v = shadow.shadow_verdict(reg.state[rid]['shadow'], s['frozen_hash'], s.get('frozen_day'), s['frozen']['lever'])
        if v['status'] == 'ready':
            verdicts[rid] = v
        elif v['status'] == 'faded':
            reg.move(rid, 'retired', 'shadow: not ready at the last look')
            faded.append(rid)
    held = []
    if verdicts:
        committed = [reg.state[r]['frozen'] for st in ('proposal', 'live') for r in reg.by_status(st)
                     if reg.state[r].get('frozen') and reg.state[r]['frozen']['lever'] == 'skip']
        cands = sorted(verdicts, key=lambda r: -verdicts[r]['gain_sum'])
        starts = [reg.state[r]['frozen_day'] for r in cands if reg.state[r].get('frozen_day')]
        pool = all_rows({d: v for d, v in days.items() if d <= day and (not starts or d > min(starts))})
        skip_cands = [reg.state[r]['frozen'] for r in cands if reg.state[r]['frozen']['lever'] == 'skip']
        _kept, held_ids, _ret = shadow.ruleset_floor(committed + skip_cands, pool) if skip_cands else ([], [], 1.0)
        held = [r for r in cands if reg.state[r]['frozen']['id'] in held_ids and reg.state[r]['frozen']['lever'] == 'skip']
        for rid in cands:
            if rid in held:
                continue
            v = verdicts[rid]
            reg.move(rid, 'proposal', 'shadow look %s: %d days, gap %.2f' % (v['look'], v['days'], v['gap_sum']))
            ready.append(rid)
    return {'shadow_rules': len(reg.by_status('shadow')), 'ready_for_pr': ready, 'faded': faded, 'held_by_floor': held}


def status(w):
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    by = {}
    for rid, s in reg.state.items():
        by.setdefault(s['status'], []).append(rid)
    used = 0
    for r in read_usage(w):
        try:
            used += int(r.get('tokens_in', 0)) + int(r.get('tokens_out', 0))
        except (TypeError, ValueError):
            continue
    return {'trials': reg.trials, 'by_status': {k: len(v) for k, v in by.items()}, 'ids': by, 'tokens_logged': used,
            'curve_edits_waiting': [r for r, s in reg.state.items() if s['curve_edit'] and not s['owner_ok'] and s['status'] in ('swept', 'proposed')]}


def pending(w):
    """Days with a trip file and no done marker, oldest first. The archive reaches Drive at a time GitHub's scheduler picks (hours
    after its 07:20 UTC cron), so the routine takes whatever is pending instead of assuming one day."""
    days = sorted(os.path.basename(p)[len('trips-'):-len('.jsonl')] for p in glob.glob(os.path.join(w, 'days', 'trips-*.jsonl')))
    return {'days': [d for d in days if not os.path.exists(os.path.join(w, 'work', d, 'done.json'))]}


def mark_done(w, day):
    if not os.path.exists(os.path.join(w, 'days', 'trips-%s.jsonl' % day)):
        raise SystemExit('no trip file for %s: refusing to mark it done' % day)
    _dump(os.path.join(workdir(w, day), 'done.json'), {'day': day})
    return {'day': day, 'done': True}


def _clock(txt):
    """'HH:MM[:SS]' -> seconds into the UTC day (24:00:00 allowed as the end)."""
    parts = txt.split(':')
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        raise SystemExit('bad time %r: use HH:MM or HH:MM:SS (UTC)' % txt)
    sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + (int(parts[2]) if len(parts) == 3 else 0)
    if sec > 86400:
        raise SystemExit('bad time %r: past the end of the day' % txt)
    return sec


def window(w, day, since='00:00:00', until='24:00:00'):
    """The aggregates of the day's trips that closed in [since, until) UTC, to answer "does this day agree with that study window".
    The full summary goes to work/DAY/window-<since>-<until>.json (private Drive); the job log gets only the trip count, because two
    windows printed with dollars could be subtracted down to a single trade."""
    p = os.path.join(w, 'days', 'trips-%s.jsonl' % day)
    if not os.path.exists(p):
        raise SystemExit('no trip file for %s' % day)
    t0 = nightly.day_bounds(day)[0]
    a, b = _clock(since), _clock(until)
    with open(p, encoding='utf-8') as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    rows = [r for r in rows if r.get('closed_t') is not None and t0 + a <= r['closed_t'] < t0 + b]
    summ = ledger.summarize(rows, [triage.classify(r) for r in rows]) if rows else {'trips': 0}
    summ.update({'day': day, 'since': since, 'until': until, 'rows_in_window': len(rows),
                 'fidelity_flagged': sum(1 for r in rows if r.get('fidelity_flag')),
                 'defect_sales': sum(1 for r in rows if r.get('defect_sale')),
                 'defect_dollars': round(sum(r.get('defect_dollars') or 0 for r in rows), 2)})
    name = 'window-%s-%s.json' % (since.replace(':', ''), until.replace(':', ''))
    _dump(os.path.join(workdir(w, day), name), summ)
    return {'day': day, 'since': since, 'until': until, 'trips': len(rows), 'file': name}


RESPONSE_NAME = re.compile(r'^(tag-[0-9]{2}|hyp-[A-Z][A-Z_]{2,30}|adv-[a-z0-9][a-z0-9_-]{1,38}[a-z0-9])$')
MAX_RESPONSES_BYTES = 60_000     # a workflow_dispatch payload is capped at 65,535 characters in all


def save_responses(w, day, payload):
    """Writes the model steps' replies into work/DAY/NAME.response.json. payload is a JSON object {name: reply}: the reply is the
    model's text or its parsed JSON. The routine cannot put files where the runner's Drive token sees them (that token reaches only
    the files it made itself), so the replies travel in the workflow input: they hold tags by index, hypothesis specs and adversary
    verdicts, never a ticker or a time (the prompts that made them show a trade by index only). A name that is not one of the
    step's own prompts is refused, so a reply cannot create a file nobody asked for."""
    if isinstance(payload, str):
        if len(payload.encode('utf-8')) > MAX_RESPONSES_BYTES:
            raise SystemExit('responses are %d bytes: over the %d a dispatch can carry; send them in two runs' % (len(payload.encode('utf-8')), MAX_RESPONSES_BYTES))
        try:
            payload = json.loads(payload)
        except ValueError:
            raise SystemExit('responses: not JSON (an empty value too); the stage needs {name: reply}')
    if not isinstance(payload, dict):
        raise SystemExit('responses must be a JSON object {name: reply}')
    wd = workdir(w, day)
    saved = []
    for name, reply in sorted(payload.items()):
        if not RESPONSE_NAME.match(name):
            raise SystemExit('bad response name %r' % name)
        if not os.path.exists(os.path.join(wd, name + '.prompt.txt')):
            raise SystemExit('no prompt %s.prompt.txt for %s: not saving a reply to a prompt that was never made' % (name, day))
        with open(os.path.join(wd, name + '.response.json'), 'w', encoding='utf-8') as fh:
            fh.write(reply if isinstance(reply, str) else json.dumps(reply))
        saved.append(name)
    return {'day': day, 'saved': saved}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('stage', choices=['prepare-tags', 'apply-tags', 'prepare-hyp', 'apply-hyp', 'apply-adv', 'sweep', 'shadow', 'status', 'pending', 'done', 'usage', 'budget', 'window', 'responses', 'canary'])
    ap.add_argument('day', nargs='?')
    ap.add_argument('--w', required=True)
    ap.add_argument('--step', choices=sorted(prompts.MODEL_FOR))
    ap.add_argument('--tokens-in', type=int, default=0)
    ap.add_argument('--tokens-out', type=int, default=0)
    ap.add_argument('--items', type=int, default=0)
    ap.add_argument('--since', default='00:00:00')
    ap.add_argument('--until', default='24:00:00')
    ap.add_argument('--from-env', default='LR_RESPONSES', help='responses: the environment variable that holds the JSON object')
    ap.add_argument('--daily', type=int, default=DAILY_TOKENS)
    ap.add_argument('--weekly', type=int, default=None)
    a = ap.parse_args(argv)
    fn = {'prepare-tags': prepare_tags, 'apply-tags': apply_tags, 'prepare-hyp': prepare_hyp, 'apply-hyp': apply_hyp,
          'apply-adv': apply_adv, 'sweep': run_sweep, 'shadow': run_shadow, 'done': mark_done}.get(a.stage)
    if a.stage == 'canary':
        ok, fails = prompts.run_canary()
        print('LOSSLOOP canary %s' % json.dumps({'ok': ok, 'failures': fails}))
        return 0 if ok else 1
    if a.stage in ('status', 'pending'):
        out = (status if a.stage == 'status' else pending)(a.w)
    else:
        if not a.day:
            ap.error('%s needs a DAY' % a.stage)
        if a.stage == 'usage':
            if not a.step:
                ap.error('usage needs --step')
            out = usage(a.w, a.day, a.step, a.tokens_in, a.tokens_out, a.items)
        elif a.stage == 'responses':
            out = save_responses(a.w, a.day, os.environ.get(a.from_env, ''))
        elif a.stage == 'window':
            out = window(a.w, a.day, a.since, a.until)
        elif a.stage == 'budget':
            out = budget(a.w, a.day, a.daily, a.weekly)
        else:
            out = fn(a.w, a.day)
    print('LOSSLOOP %s %s' % (a.stage, json.dumps(out, default=str)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
