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
Printed output is aggregates only; every per-trade file stays in W.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

from . import forms, prompts, registry, rules, shadow, stats, sweep

REVIEW_CAP = 75          # losers a day get a model review (worst dollars first)
TAG_BATCH = 25
HYP_MIN_LOSERS = 3       # a class needs this many reviewed losers before a hypothesis is asked for
HYP_ROWS = 12
REVIEW_CLASSES = forms.HYPOTHESIS_CLASSES


def trip_id(r):
    return hashlib.sha256(('%s|%s' % (r.get('ticker'), r.get('entry_t'))).encode()).hexdigest()[:10]


def load_days(w):
    out = {}
    for p in sorted(glob.glob(os.path.join(w, 'days', 'trips-*.jsonl'))):
        day = os.path.basename(p)[len('trips-'):-len('.jsonl')]
        with open(p, encoding='utf-8') as fh:
            out[day] = [json.loads(l) for l in fh if l.strip()]
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


def log_usage(w, rec):
    with open(os.path.join(w, 'usage.jsonl'), 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(rec) + '\n')


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


def apply_hyp(w, day):
    days = load_days(w)
    rows = all_rows({d: v for d, v in days.items() if d <= day})
    losers = [r for r in rows if r.get('pnl') is not None and r['pnl'] < 0]
    winners = [r for r in rows if r.get('pnl') is not None and r['pnl'] >= 0]
    wd = workdir(w, day)
    ok_h, bad, curve = [], 0, 0
    for cls in REVIEW_CLASSES:
        p = os.path.join(wd, 'hyp-%s.response.json' % cls)
        resp = _read_json(p) if os.path.exists(p) else None
        items = resp if isinstance(resp, list) else (resp or {}).get('hypotheses') if isinstance(resp, dict) else None
        for h in items or []:
            ok, errs, flags = forms.validate_hypothesis(h) if isinstance(h, dict) else (False, ['not an object'], [])
            if not ok:
                bad += 1
                continue
            if h.get('loss_class') != cls:
                bad += 1
                continue
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
    days = load_days(w)
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
    (a promotion PR for the owner, never merged by the routine) and 'faded' retires it."""
    days = load_days(w)
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    ready, faded = [], []
    for rid in reg.by_status('shadow'):
        s = reg.state[rid]
        have = {r['day'] for r in s['shadow']}
        for d in sorted(days):
            if (s.get('frozen_day') and d <= s['frozen_day']) or d > day or d in have:
                continue
            reg.shadow(rid, shadow.shadow_day(s['frozen'], s['frozen_hash'], d, days[d]))
        v = shadow.shadow_verdict(reg.state[rid]['shadow'], s['frozen_hash'], s.get('frozen_day'), s['frozen']['lever'])
        if v['status'] == 'ready':
            reg.move(rid, 'proposal', 'shadow look %s: %d days, gap %.2f' % (v['look'], v['days'], v['gap_sum']))
            ready.append(rid)
        elif v['status'] == 'faded':
            reg.move(rid, 'retired', 'shadow: not ready at the last look')
            faded.append(rid)
    held = []
    skip_rules = [reg.state[r]['frozen'] for r in reg.by_status('shadow') if reg.state[r]['frozen']['lever'] == 'skip']
    if skip_rules and days.get(day):
        _kept, held, _ret = shadow.ruleset_floor(skip_rules, days[day])
    return {'shadow_rules': len(reg.by_status('shadow')), 'ready_for_pr': ready, 'faded': faded, 'held_by_floor': held}


def status(w):
    reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
    by = {}
    for rid, s in reg.state.items():
        by.setdefault(s['status'], []).append(rid)
    used = 0
    p = os.path.join(w, 'usage.jsonl')
    if os.path.exists(p):
        used = sum(r.get('tokens_in', 0) + r.get('tokens_out', 0) for r in map(json.loads, open(p)) if r)
    return {'trials': reg.trials, 'by_status': {k: len(v) for k, v in by.items()}, 'ids': by, 'tokens_logged': used,
            'curve_edits_waiting': [r for r, s in reg.state.items() if s['curve_edit'] and not s['owner_ok'] and s['status'] in ('swept', 'proposed')]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('stage', choices=['prepare-tags', 'apply-tags', 'prepare-hyp', 'apply-hyp', 'apply-adv', 'sweep', 'shadow', 'status'])
    ap.add_argument('day', nargs='?')
    ap.add_argument('--w', required=True)
    a = ap.parse_args(argv)
    fn = {'prepare-tags': prepare_tags, 'apply-tags': apply_tags, 'prepare-hyp': prepare_hyp, 'apply-hyp': apply_hyp,
          'apply-adv': apply_adv, 'sweep': run_sweep, 'shadow': run_shadow}.get(a.stage)
    out = status(a.w) if a.stage == 'status' else fn(a.w, a.day)
    print('LOSSLOOP %s %s' % (a.stage, json.dumps(out, default=str)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
