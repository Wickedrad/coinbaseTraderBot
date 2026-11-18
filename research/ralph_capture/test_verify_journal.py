"""Tests for verify_journal.py. The journal builder here is written independently of rawTap.ts (same line format only),
so a bug in one is not hidden by the other. Run: python3 -I -m unittest research.ralph_capture.test_verify_journal -q
(or from this directory: python3 -I -m unittest test_verify_journal -q)."""
import hashlib
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_journal as vj  # noqa: E402

GEN = '0' * 64


def sha(s):
    return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()


class J:
    """Builds a journal the way the writer does: line = sha256(prev + LF + body) TAB body."""
    def __init__(self, config=None):
        self.prev, self.n, self.lines, self.t, self.epoch, self.frames = GEN, 0, [], 1_000_000, -1, 0
        cj = json.dumps(config or {'url_host': 'x', 'mode': 'paper'})
        self.put({'kind': 'header', 'schema': 1, 'tool': 't', 'source': 'kalshi-ws-unattested', 'exchange_authenticated': False,
                  'started_wall_ms': self.t, 'started_mono_ns': str(self.t * 1_000_000), 'config_json': cj, 'config_sha256': sha(cj)})

    def put(self, rec, raw_body=None):
        body = raw_body if raw_body is not None else json.dumps({'n': self.n, **rec})
        h = sha(self.prev + '\n' + body)
        self.lines.append(h + '\t' + body)
        self.prev, self.n = h, self.n + 1

    def stamp(self, dt=10):
        self.t += dt
        return {'wall_ms': self.t, 'mono_ns': str(self.t * 1_000_000)}

    def tr(self, ev, **kw):
        if ev == 'connecting':
            self.epoch += 1
        self.put({'kind': 'transport', 'event': ev, 'epoch': self.epoch, **self.stamp(), **kw})

    def out(self, text='{"id":1,"cmd":"subscribe"}'):
        self.put({'kind': 'outbound', 'epoch': self.epoch, **self.stamp(), 'text': text})

    def fr(self, raw, **over):
        env_type = None
        try:
            env_type = json.loads(raw).get('type')
        except Exception:
            pass
        rec = {'kind': 'frame', 'epoch': self.epoch, **self.stamp(), 'bytes': len(raw.encode()), 'binary': False,
               'sha256': sha(raw), 'type': env_type, 'raw': raw}
        rec.update(over)
        self.frames += 1
        self.put(rec)

    def snap(self, sid=1, seq=1, ticker='T1'):
        self.fr(json.dumps({'type': 'orderbook_snapshot', 'sid': sid, 'seq': seq, 'msg': {'market_ticker': ticker}}))

    def delta(self, sid=1, seq=2, ticker='T1'):
        self.fr(json.dumps({'type': 'orderbook_delta', 'sid': sid, 'seq': seq, 'msg': {'market_ticker': ticker}}))

    def end(self, **kw):
        rec = {'kind': 'end', 'records': self.n, 'frames': self.frames, 'dropped_total': 0, 'failed': None}
        rec.update(kw)
        self.put(rec)

    def anchor(self, count=None):
        c = count or self.n
        return [json.dumps({'count': c, 'head': self.lines[c - 1].split('\t')[0], 'wall_ms': self.t})]


def good():
    j = J()
    j.tr('connecting'); j.tr('open'); j.out(); j.snap(); j.delta(); j.tr('close'); j.end()
    return j


def run(j, **kw):
    return vj.verify(j.lines, **kw)


class Verify(unittest.TestCase):
    def test_valid(self):
        r = run(good())
        self.assertTrue(r['locally_consistent'], r['reasons'])
        self.assertEqual(r['notes']['frames'], 2)
        self.assertFalse(r['exchange_authenticated'])
        self.assertFalse(r['phase_b_eligible'])

    def test_flags_are_constants(self):
        for j in (good(), J()):
            r = run(j)
            self.assertIs(r['exchange_authenticated'], False)
            self.assertIs(r['phase_b_eligible'], False)

    def test_tampered_raw_breaks_chain(self):
        j = good()
        j.lines[4] = j.lines[4].replace('orderbook_snapshot', 'orderbook_snapshoT')
        self.assertIn('hash_chain_invalid', run(j)['reasons'])

    def test_rechained_edit_caught_by_anchor(self):
        # an editor who recomputes every hash after an edit is caught only by an anchor kept elsewhere
        j = good()
        anchor = j.anchor()
        k = J()
        k.tr('connecting'); k.tr('open'); k.out(); k.snap(sid=9); k.delta(sid=9); k.tr('close'); k.end()
        self.assertTrue(run(k)['locally_consistent'])
        r = run(k, anchor_lines=anchor)
        self.assertIn('anchor_mismatch', r['reasons'])
        self.assertFalse(r['locally_consistent'])

    def test_anchor_match(self):
        j = good()
        r = run(j, anchor_lines=j.anchor())
        self.assertEqual(r['anchor'], 'matched')
        self.assertTrue(r['locally_consistent'])

    def test_anchor_empty_fails(self):
        self.assertIn('anchor_empty', run(good(), anchor_lines=[])['reasons'])

    def test_truncated_no_footer(self):
        j = good()
        j.lines.pop()
        self.assertIn('missing_valid_footer', run(j)['reasons'])

    def test_trailing_after_footer(self):
        j = good()
        j.lines.append('x')
        self.assertIn('trailing_data', run(j)['reasons'])

    def test_reordered_lines(self):
        j = good()
        j.lines[3], j.lines[4] = j.lines[4], j.lines[3]
        self.assertFalse(run(j)['locally_consistent'])

    def test_empty_journal(self):
        r = vj.verify([])
        self.assertFalse(r['locally_consistent'])

    def test_no_frames(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.tr('close'); j.end()
        self.assertIn('no_frames', run(j)['reasons'])

    def test_config_hash_mismatch(self):
        j2 = J.__new__(J)
        j2.prev, j2.n, j2.lines, j2.t, j2.epoch, j2.frames = GEN, 0, [], 1_000_000, -1, 0
        j2.put({'kind': 'header', 'schema': 1, 'exchange_authenticated': False, 'started_wall_ms': 1, 'started_mono_ns': '1',
                'config_json': '{"a":1}', 'config_sha256': sha('{"a":2}')})
        j2.tr('connecting'); j2.tr('open'); j2.snap(); j2.tr('close'); j2.end()
        self.assertIn('config_hash_mismatch', run(j2)['reasons'])

    def test_header_claiming_authentication(self):
        j = J.__new__(J)
        j.prev, j.n, j.lines, j.t, j.epoch, j.frames = GEN, 0, [], 1_000_000, -1, 0
        j.put({'kind': 'header', 'schema': 1, 'exchange_authenticated': True, 'started_wall_ms': 1, 'started_mono_ns': '1',
               'config_json': '{}', 'config_sha256': sha('{}')})
        j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end()
        r = run(j)
        self.assertIn('header_claims_authentication', r['reasons'])
        self.assertFalse(r['exchange_authenticated'])

    def test_record_number_gap(self):
        j = J()
        j.n += 1
        j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end()
        self.assertIn('record_number_gap', run(j)['reasons'])

    def test_duplicate_key_in_body_rejected(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.put(None, raw_body='{"n":%d,"kind":"outbound","kind":"outbound"}' % j.n)
        self.assertIn('malformed_record', run(j)['reasons'])

    def test_frame_sha_mismatch(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.fr('{"type":"trade","sid":2,"seq":1}', sha256='0' * 64)
        j.tr('close'); j.end()
        self.assertIn('frame_sha256_mismatch', run(j)['reasons'])

    def test_declared_type_mismatch(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.fr('{"type":"trade","sid":2,"seq":1}', type='orderbook_delta')
        j.tr('close'); j.end()
        self.assertIn('declared_type_mismatch', run(j)['reasons'])

    def test_duplicate_key_in_raw_frame_flagged(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.fr('{"type":"trade","type":"x","sid":2,"seq":1}')
        j.tr('close'); j.end()
        r = run(j)
        self.assertEqual(r['notes']['unparsable_public_frames'], 1)

    def test_nan_in_raw_frame_flagged(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.fr('{"type":"trade","sid":2,"seq":1,"x":NaN}')
        j.tr('close'); j.end()
        self.assertEqual(run(j)['notes']['unparsable_public_frames'], 1)

    def test_sequence_gap_invalidates_until_snapshot(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.snap(seq=1); j.delta(seq=2); j.delta(seq=4); j.delta(seq=5)
        j.tr('close'); j.end()
        r = run(j)
        self.assertEqual(r['notes']['gaps'][0]['expected'], 3)
        self.assertEqual(r['notes']['gaps'][0]['got'], 4)
        self.assertTrue(r['locally_consistent'])  # the journal is intact; the market data is what is broken
        self.assertEqual(len([i for i in r['notes']['invalidations'] if i['why'] == 'sequence_gap']), 1)

    def test_snapshot_after_gap_restores(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.snap(seq=1); j.delta(seq=3); j.snap(seq=7); j.delta(seq=8)
        j.tr('close'); j.end()
        r = run(j)
        self.assertEqual(len(r['notes']['gaps']), 1)  # the second delta is continuous after the new snapshot

    def test_delta_before_snapshot(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.delta(seq=5)
        j.tr('close'); j.end()
        self.assertEqual(run(j)['notes']['invalidations'][0]['why'], 'delta_before_snapshot')

    def test_reconnect_resets_baseline_per_epoch(self):
        j = J()
        j.tr('connecting'); j.tr('open'); j.snap(seq=1); j.delta(seq=2); j.tr('close')
        j.tr('connecting'); j.tr('open'); j.snap(seq=1); j.delta(seq=2); j.tr('close'); j.end()
        r = run(j)
        self.assertEqual(r['notes']['epochs'], 2)
        self.assertEqual(len(r['notes']['gaps']), 0)
        self.assertTrue(r['locally_consistent'], r['reasons'])

    def test_disconnect_invalidates_open_subscriptions(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end()
        self.assertTrue(any(i['why'] == 'transport_closed' for i in run(j)['notes']['invalidations']))

    def test_dropped_marker_invalidates_epoch(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap()
        j.put({'kind': 'dropped', 'epoch': j.epoch, **j.stamp(), 'count': 3, 'cause': 'backpressure'})
        j.delta(seq=2); j.tr('close'); j.end()
        r = run(j)
        self.assertIn('frames_dropped', r['reasons'])
        self.assertEqual(r['notes']['dropped_frames'], 3)
        self.assertTrue(any(i['why'] == 'frames_dropped' for i in r['notes']['invalidations']))

    def test_frame_before_open(self):
        j = J(); j.tr('connecting'); j.snap(); j.tr('open'); j.tr('close'); j.end()
        self.assertIn('frame_outside_open_epoch', run(j)['reasons'])

    def test_epoch_mismatch(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.fr('{"type":"trade","sid":1,"seq":1}', epoch=5); j.tr('close'); j.end()
        self.assertIn('epoch_mismatch', run(j)['reasons'])

    def test_connecting_without_close(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end()
        self.assertIn('connecting_without_close', run(j)['reasons'])

    def test_wall_clock_backwards(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.put({'kind': 'outbound', 'epoch': j.epoch, 'wall_ms': j.t - 5000, 'mono_ns': str((j.t + 10) * 1_000_000), 'text': 'x'})
        j.snap(); j.tr('close'); j.end()
        self.assertIn('wall_clock_went_backwards', run(j)['reasons'])

    def test_wall_clock_stepped_forward(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.put({'kind': 'outbound', 'epoch': j.epoch, 'wall_ms': j.t + 600_000, 'mono_ns': str((j.t + 10) * 1_000_000), 'text': 'x'})
        j.snap(); j.tr('close'); j.end()
        self.assertIn('wall_clock_stepped', run(j)['reasons'])

    def test_monotonic_regression(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.put({'kind': 'outbound', 'epoch': j.epoch, 'wall_ms': j.t + 10, 'mono_ns': '1', 'text': 'x'})
        j.snap(); j.tr('close'); j.end()
        self.assertIn('monotonic_clock_regressed', run(j)['reasons'])

    def test_redacted_frame_keeps_continuity(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.put({'kind': 'frame', 'epoch': j.epoch, **j.stamp(), 'bytes': 40, 'binary': False, 'sha256': sha('p1'), 'type': 'fill', 'redacted': True, 'sid': 4, 'seq': 1})
        j.frames += 1
        j.put({'kind': 'frame', 'epoch': j.epoch, **j.stamp(), 'bytes': 40, 'binary': False, 'sha256': sha('p2'), 'type': 'fill', 'redacted': True, 'sid': 4, 'seq': 3})
        j.frames += 1
        j.tr('close'); j.end()
        r = run(j)
        self.assertEqual(r['notes']['redacted'], 2)
        self.assertEqual(len(r['notes']['gaps']), 1)

    def test_footer_count_mismatch(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end(frames=99)
        self.assertIn('bad_footer', run(j)['reasons'])

    def test_capture_reported_failure(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end(failed='write: ENOSPC')
        self.assertIn('capture_reported_failure', run(j)['reasons'])

    def test_unknown_record_kind(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.put({'kind': 'mystery'})
        self.assertIn('malformed_record', run(j)['reasons'])


if __name__ == '__main__':
    unittest.main()
