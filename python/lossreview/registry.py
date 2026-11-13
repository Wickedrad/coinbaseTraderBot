"""The candidate registry ("our TA list"): an append-only event log of every hypothesis and rule the loop has tried.

Every registered hypothesis is a trial, tested or not: the count only goes up, and the multiple-comparison corrections
read it. The 56 variants of the earlier levers study count as the first trials (PRIOR_TRIALS), and the day-0 backfill
classes are marked post hoc (found by reading the losses they would explain, so never evidence for a rule: a rule that
came from them is scored only on days after those losses, which the sweep enforces through `generating_days`).

Statuses and the moves between them (anything else is refused):
  proposed -> swept            a sweep scored it on days after its generating losses (the verdict is on the event)
  swept    -> shadow           a candidate verdict: its frozen rule is flagged offline every night
  shadow   -> proposal         enough shadow days; a promotion PR (off / log / on) is drafted for the owner
  proposal -> live | retired   the owner merged it (and later relaxed or retired it) / declined
  swept, shadow -> retired     refuted, or the effect faded
  proposed -> retired          dropped without a sweep
A curve edit never leaves `swept` on its own: it waits for the owner's explicit word (event 'owner_ok').
"""
import hashlib
import json
import os
import time

PRIOR_TRIALS = 56
FAMILY = 'loss-rules'
MOVES = {
    'proposed': ('swept', 'retired'),
    'swept': ('shadow', 'retired'),
    'shadow': ('proposal', 'retired'),
    'proposal': ('live', 'retired'),
    'live': ('retired',),
    'retired': (),
}


class RegistryError(Exception):
    pass


class Registry:
    def __init__(self, path=None):
        self.path = path
        self.events = []
        if path and os.path.exists(path):
            with open(path, encoding='utf-8') as fh:
                self.events = [json.loads(l) for l in fh if l.strip()]
        self.state = {}
        self.trials = PRIOR_TRIALS
        for e in self.events:
            self._apply(e)

    def _apply(self, e):
        k = e['event']
        if k == 'register':
            self.state[e['id']] = {'status': 'proposed', 'rule': e['rule'], 'hash': e['hash'], 'post_hoc': bool(e.get('post_hoc')),
                                   'generating_days': list(e.get('generating_days') or []), 'registered_day': e['day'],
                                   'curve_edit': bool(e.get('curve_edit')), 'owner_ok': False, 'owner_ok_hash': None, 'scores': [], 'shadow': [],
                                   'kind': e.get('kind', 'rule'), 'frozen': e['rule'] if e.get('kind', 'rule') == 'rule' else None,
                                   'frozen_hash': e['hash'] if e.get('kind', 'rule') == 'rule' else None,
                                   'frozen_day': e['day'] if e.get('kind', 'rule') == 'rule' else None}
            self.trials += int(e.get('trials', 1))
        elif k == 'transition':
            self.state[e['id']]['status'] = e['to']
        elif k == 'freeze':
            st = self.state[e['id']]
            st['frozen'], st['frozen_hash'], st['curve_edit'] = e['frozen'], e['frozen_hash'], bool(e.get('curve_edit'))
            st['frozen_day'] = e.get('day')   # shadow counts only days after this one: the sweep already used it
        elif k == 'score':
            self.state[e['id']]['scores'].append(e['verdict'])
        elif k == 'shadow':
            self.state[e['id']]['shadow'].append(e['result'])
        elif k == 'owner_ok':
            self.state[e['id']]['owner_ok'] = True
            self.state[e['id']]['owner_ok_hash'] = e.get('hash')

    def _write(self, e):
        e = dict(e, ts=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        self._apply(e)
        self.events.append(e)
        if self.path:
            with open(self.path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(e, separators=(',', ':'), default=str) + '\n')

    def register(self, spec, day, generating_days, post_hoc=False, trials=1, kind='rule'):
        """Add a rule (kind 'rule', a frozen spec) or a hypothesis (kind 'hypothesis', validated by forms.validate_hypothesis)
        as new trials. `trials` is how many thresholds / variants it stands for (each counts)."""
        from . import rules
        if spec.get('id') in self.state:
            raise RegistryError('already registered: %s' % spec.get('id'))
        if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
            raise RegistryError('trials must be a whole number of at least 1: every candidate tried counts')
        if not generating_days:
            raise RegistryError('generating_days is required: scoring must start after the losses that produced the idea')
        if kind == 'rule':
            ok, errs = rules.validate_rule(spec)
            if not ok:
                raise RegistryError('invalid rule: %s' % '; '.join(errs))
            h, curve = rules.rule_hash(spec), rules.curve_edit(spec)
        else:
            from . import schema
            h = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()[:16]
            curve = any(c in schema.CURVE_COLUMNS for c in [spec.get('feature')] + list(spec.get('neighbor_features') or []))
        self._write({'event': 'register', 'id': spec['id'], 'kind': kind, 'rule': spec, 'hash': h, 'day': day,
                     'generating_days': sorted(generating_days), 'post_hoc': post_hoc, 'trials': int(trials),
                     'curve_edit': curve, 'family': FAMILY})
        return self.trials

    def freeze(self, rid, rule, day):
        """Fix the rule a hypothesis' sweep chose (its best candidate): shadow runs this spec and nothing else. Once, from
        `swept`: a rule that changes is a new trial under a new id. `day` is the last day the sweep's window used."""
        from . import rules
        s = self._need(rid)
        if s['status'] != 'swept':
            raise RegistryError('%s: only a swept hypothesis can be frozen (it is %s)' % (rid, s['status']))
        if s.get('frozen'):
            raise RegistryError('%s is already frozen: a changed rule is a new trial under a new id' % rid)
        ok, errs = rules.validate_rule(rule)
        if not ok:
            raise RegistryError('invalid rule: %s' % '; '.join(errs))
        self._write({'event': 'freeze', 'id': rid, 'frozen': rule, 'frozen_hash': rules.rule_hash(rule), 'day': day,
                     'curve_edit': s['curve_edit'] or rules.curve_edit(rule)})

    def score(self, rid, verdict):
        self._need(rid)
        self._write({'event': 'score', 'id': rid, 'verdict': verdict})

    def shadow(self, rid, result):
        s = self._need(rid)
        if s['status'] != 'shadow':
            raise RegistryError('%s is %s, not in shadow' % (rid, s['status']))
        if result.get('hash') != s.get('frozen_hash'):
            raise RegistryError('%s: a shadow result for another rule hash is refused' % rid)
        if s.get('frozen_day') and not (result.get('day') and result['day'] > s['frozen_day']):
            raise RegistryError('%s: shadow counts only days after the sweep window (%s)' % (rid, s['frozen_day']))
        self._write({'event': 'shadow', 'id': rid, 'result': result})

    def owner_ok(self, rid):
        """Record the owner's explicit word for THIS frozen rule (called only from a message of theirs). It covers the rule's
        hash: a rule that changes needs the word again."""
        s = self._need(rid)
        if not s.get('frozen'):
            raise RegistryError('%s has no frozen rule to approve' % rid)
        self._write({'event': 'owner_ok', 'id': rid, 'hash': s['frozen_hash']})

    def move(self, rid, to, why=''):
        s = self._need(rid)
        if to not in MOVES.get(s['status'], ()):
            raise RegistryError('%s: %s -> %s is not a move' % (rid, s['status'], to))
        if to == 'swept' and not s['scores']:
            raise RegistryError('%s: nothing has been scored yet' % rid)
        if to == 'shadow':
            if not s.get('frozen'):
                raise RegistryError('%s has no frozen rule: freeze the sweep\'s best candidate first' % rid)
            best = ((s['scores'][-1] if s['scores'] else {}).get('best') or {})
            if best.get('verdict') != 'candidate' or best.get('rule', {}).get('id') != s['frozen'].get('id'):
                raise RegistryError('%s: the latest sweep did not name the frozen rule a candidate' % rid)
            if s['curve_edit'] and not (s['owner_ok'] and s['owner_ok_hash'] == s['frozen_hash']):
                raise RegistryError('%s reads a curve column: a curve edit needs the owner\'s explicit word for this rule' % rid)
        if to == 'proposal':
            from . import shadow
            v = shadow.shadow_verdict(s['shadow'], s['frozen_hash'], s.get('frozen_day'), s['frozen']['lever'])
            if v['status'] != 'ready':
                raise RegistryError('%s: shadow is %s, not ready' % (rid, v['status']))
        self._write({'event': 'transition', 'id': rid, 'from': s['status'], 'to': to, 'why': why})

    def _need(self, rid):
        if rid not in self.state:
            raise RegistryError('unknown rule %s' % rid)
        return self.state[rid]

    def family_size(self):
        """The number of tests the registry-wide BH correction stands for: the prior study's variants plus every hypothesis or
        rule registered since. A hypothesis' own p already pays for its candidates and looks, so they are not counted twice."""
        return PRIOR_TRIALS + len(self.state)

    def by_status(self, status):
        return [rid for rid, s in self.state.items() if s['status'] == status]
