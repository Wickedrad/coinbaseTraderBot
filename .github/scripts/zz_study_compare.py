"""TEMPORARY (never merged): trip-by-trip comparison of the loss-review trip files with the Nov 12 hand study's trips.json.
Prints aggregates only (cells of 5 or more; no ticker, no per-trade value)."""
import calendar, collections, datetime, json, sys, os, time

W, STUDY = sys.argv[1], sys.argv[2]
study = json.load(open(STUDY))
def ts(s):
    return calendar.timegm(time.strptime(s, '%Y-%m-%dT%H:%M:%SZ'))
for r in study:
    r['t'] = ts(r['closed'])
lo, hi = min(r['t'] for r in study), max(r['t'] for r in study)
ours = []
for d in ('2026-11-11', '2026-11-12'):
    p = os.path.join(W, 'days', 'trips-%s.jsonl' % d)
    ours += [json.loads(l) for l in open(p) if l.strip()]
ours = [r for r in ours if lo <= r['closed_t'] <= hi]
print('study rows %d, ours in the same span %d' % (len(study), len(ours)))
print('study net %.2f, ours (logged pnl) %.2f, ours (pnl_fills) %.2f' % (sum(r['pnl'] for r in study), sum(r['pnl'] for r in ours),
      sum(r['pnl_fills'] for r in ours if r.get('pnl_fills') is not None)))
by_t = collections.defaultdict(list)
for r in ours:
    by_t[r['ticker']].append(r)
for v in by_t.values():
    v.sort(key=lambda r: r['closed_t'])
pairs, only_study = [], []
used = collections.defaultdict(int)
for s in sorted(study, key=lambda r: r['t']):
    k = used[s['ticker']]
    cand = by_t.get(s['ticker'], [])
    if k < len(cand):
        pairs.append((s, cand[k]))
        used[s['ticker']] += 1
    else:
        only_study.append(s)
only_ours = sum(len(v) for v in by_t.values()) - len(pairs)
print('matched %d, only in study %d, only in ours %d' % (len(pairs), len(only_study), only_ours))
def cell(label, items):
    items = list(items)
    if len(items) < 5:
        return None
    return '%s: n=%d sum_diff=%.2f' % (label, len(items), sum(o['pnl'] - s['pnl'] for s, o in items))
diff = [(s, o) for s, o in pairs if abs(o['pnl'] - s['pnl']) > 0.005]
print('matched trips whose pnl differs: %d, sum of (ours - study) = %.2f; pnl_fills vs study differs: %d' % (
    len(diff), sum(o['pnl'] - s['pnl'] for s, o in diff),
    sum(1 for s, o in pairs if o.get('pnl_fills') is not None and abs(o['pnl_fills'] - s['pnl']) > 0.005)))
small = 0
for label, key in (('our exit_event', lambda s, o: o.get('exit_event') or 'none'), ('study how', lambda s, o: s['how']),
                   ('our pnl_source', lambda s, o: o.get('pnl_source')), ('our settled', lambda s, o: str(o.get('settled'))),
                   ('sign of diff', lambda s, o: 'ours lower' if o['pnl'] < s['pnl'] else 'ours higher')):
    g = collections.defaultdict(list)
    for s, o in diff:
        g[key(s, o)].append((s, o))
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        line = cell('%s=%s' % (label, k), v)
        print(line if line else '%s=%s: fewer than 5' % (label, k))
cdiff = sum(1 for s, o in pairs if abs(o['closed_t'] - s['t']) > 60)
print('matched trips whose close time differs by more than 60 s: %d' % cdiff)
mag = sorted(abs(o['pnl'] - s['pnl']) for s, o in diff)
if len(mag) >= 5:
    print('size of the differences (abs): median %.2f, 90th pct %.2f, max %.2f' % (mag[len(mag) // 2], mag[int(len(mag) * 0.9)], mag[-1]))
print('unmatched in study by how: %s' % dict(collections.Counter(s['how'] for s in only_study)) if len(only_study) >= 5 else 'unmatched in study: %d (small cell)' % len(only_study))
