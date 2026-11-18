"""Tests for verify_journal.py. The journal builder here is written independently of rawTap.ts (same line format only),
so a bug in one is not hidden by the other. Run: python3 -I -m unittest research.ralph_capture.test_verify_journal -q
(or from this directory: python3 -I -m unittest test_verify_journal -q)."""
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_journal as vj  # noqa: E402

GEN = '0' * 64


def sha(s):
    return hashlib.sha256(s.encode() if isinstance(s, str) else s).hexdigest()


class J:
    """Builds a journal the way the writer does: line = sha256(prev + LF + body) TAB body."""
    def __init__(self, config=None):
        self.prev, self.n, self.lines, self.t, self.epoch, self.frames, self.decisions, self.unrecorded = GEN, 0, [], 1_000_000, -1, 0, 0, 0
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

    def dec(self, inp=None, res=None, dt=10, **over):
        """A heat decision receipt as the tap writes it (text plus the SHA-256 of that text)."""
        it = json.dumps(inp if inp is not None else {'now': 1, 'markets': []})
        rt = json.dumps(res if res is not None else {'decided': [], 'plans': []})
        rec = {'kind': 'decision', 'epoch': self.epoch, **self.stamp(dt), 'seq': self.decisions,
               'input_sha256': sha(it), 'result_sha256': sha(rt), 'input_json': it, 'result_json': rt}
        rec.update(over)
        self.decisions += 1
        self.put(rec)

    def end(self, **kw):
        rec = {'kind': 'end', 'records': self.n, 'frames': self.frames, 'dropped_total': 0, 'failed': None}
        if self.decisions:
            rec.update({'decisions': self.decisions, 'decisions_unrecorded': self.unrecorded})
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
        self.assertTrue(r['continuity_intact'])
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
        j2.prev, j2.n, j2.lines, j2.t, j2.epoch, j2.frames, j2.decisions, j2.unrecorded = GEN, 0, [], 1_000_000, -1, 0, 0, 0
        j2.put({'kind': 'header', 'schema': 1, 'exchange_authenticated': False, 'started_wall_ms': 1, 'started_mono_ns': '1',
                'config_json': '{"a":1}', 'config_sha256': sha('{"a":2}')})
        j2.tr('connecting'); j2.tr('open'); j2.snap(); j2.tr('close'); j2.end()
        self.assertIn('config_hash_mismatch', run(j2)['reasons'])

    def test_header_claiming_authentication(self):
        j = J.__new__(J)
        j.prev, j.n, j.lines, j.t, j.epoch, j.frames, j.decisions, j.unrecorded = GEN, 0, [], 1_000_000, -1, 0, 0, 0
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
        self.assertIn('unparsable_public_frame', r['reasons'])
        self.assertFalse(r['locally_consistent'])

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
        self.assertEqual(len([i for i in r['notes']['anomalies'] if i['why'] == 'sequence_gap']), 1)
        self.assertFalse(r['continuity_intact'])

    def test_snapshot_after_gap_restores(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.snap(seq=1); j.delta(seq=3); j.snap(seq=4); j.delta(seq=5)
        j.tr('close'); j.end()
        r = run(j)
        self.assertEqual(len(r['notes']['gaps']), 1)  # the second delta is continuous after the new snapshot

    def test_delta_before_snapshot(self):
        j = J(); j.tr('connecting'); j.tr('open')
        j.delta(seq=5)
        j.tr('close'); j.end()
        self.assertEqual(run(j)['notes']['anomalies'][0]['why'], 'delta_before_snapshot')

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
        r = run(j)
        self.assertEqual(r['notes']['windows_ended_by_disconnect'], 1)   # a normal end of a window, not an anomaly
        self.assertEqual(r['notes']['anomalies'], [])

    def test_dropped_marker_invalidates_epoch(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap()
        j.put({'kind': 'dropped', 'epoch': j.epoch, **j.stamp(), 'count': 3, 'cause': 'backpressure'})
        j.delta(seq=2); j.tr('close'); j.end(dropped_total=3)
        r = run(j)
        self.assertIn('frames_dropped', r['reasons'])
        self.assertEqual(r['notes']['dropped_frames'], 3)
        self.assertTrue(any(i['why'] == 'frames_dropped' for i in r['notes']['anomalies']))
        self.assertFalse(r['continuity_intact'])
        self.assertTrue(r['locally_consistent'])

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
        self.assertTrue(r['locally_consistent'], r['reasons'])

    def test_footer_count_mismatch(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end(frames=99)
        self.assertIn('bad_footer', run(j)['reasons'])

    def test_capture_reported_failure(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end(failed='write: ENOSPC')
        self.assertIn('capture_reported_failure', run(j)['reasons'])

    def test_unknown_record_kind(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.put({'kind': 'mystery'})
        self.assertIn('malformed_record', run(j)['reasons'])

    # ---- critic round 1 additions ----
    def test_anchor_must_cover_the_whole_journal(self):
        j = good()
        r = run(j, anchor_lines=j.anchor(count=3))
        self.assertEqual(r['anchor'], 'partial')
        self.assertEqual(r['anchored_records'], 3)
        self.assertIn('anchor_partial', r['reasons'])

    def test_rewritten_tail_passes_locally_and_a_prefix_anchor_but_not_a_covering_anchor(self):
        def build(tail_seq):
            j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap(); j.delta(seq=2)
            j.delta(seq=tail_seq); j.tr('close'); j.end()
            return j
        honest, forged = build(3), build(4)           # same first records, different tail, both re-hashed
        self.assertTrue(run(forged)['locally_consistent'])
        early = honest.anchor(count=5)                 # a checkpoint taken mid-capture
        r = run(forged, anchor_lines=early)
        self.assertEqual(r['anchor'], 'partial')       # prefix matches, tail unprotected
        full = run(forged, anchor_lines=honest.anchor())
        self.assertEqual(full['anchor'], 'mismatch')   # a covering anchor catches the rewrite
        self.assertFalse(full['locally_consistent'])

    def test_multi_ticker_sid_gap_is_per_ticker(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out()
        j.snap(sid=1, seq=1, ticker='T1'); j.snap(sid=1, seq=2, ticker='T2')
        j.delta(sid=1, seq=3, ticker='T1'); j.delta(sid=1, seq=5, ticker='T2')       # gap on the shared sid
        j.snap(sid=1, seq=6, ticker='T2')                                            # restores T2 only
        j.delta(sid=1, seq=7, ticker='T1')                                           # T1 still has no new snapshot
        j.tr('close'); j.end()
        r = run(j)
        books = r['notes']['books']
        self.assertEqual(books['0:T1']['valid_at_end'], False)
        self.assertEqual(books['0:T1']['last_invalid_why'], 'sequence_gap')
        self.assertEqual(r['notes']['snapshots_restoring_a_ticker'], 1)

    def test_delta_from_a_different_sid_invalidates_the_ticker(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out()
        j.snap(sid=1, seq=1, ticker='T1'); j.delta(sid=2, seq=1, ticker='T1')
        j.tr('close'); j.end()
        self.assertTrue(any(i['why'] == 'delta_from_unexpected_sid' for i in run(j)['notes']['anomalies']))

    def test_book_frame_without_seq_fails_closed(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        j.fr(json.dumps({'type': 'orderbook_delta', 'sid': 1, 'msg': {'market_ticker': 'T1'}}))
        j.tr('close'); j.end()
        r = run(j)
        self.assertTrue(any(i['why'] == 'unsequenced_book_frame' for i in r['notes']['anomalies']))
        self.assertFalse(r['continuity_intact'])

    def test_book_frame_without_ticker_fails_closed(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        j.fr(json.dumps({'type': 'orderbook_delta', 'sid': 1, 'seq': 2, 'msg': {}}))
        j.tr('close'); j.end()
        self.assertTrue(any(i['why'] == 'unsequenced_book_frame' for i in run(j)['notes']['anomalies']))

    def test_redacted_book_frame_cannot_restore_or_hide(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap(); j.delta(seq=3)      # gap
        j.put({'kind': 'frame', 'epoch': j.epoch, **j.stamp(), 'bytes': 9, 'binary': False, 'sha256': sha('x'), 'type': 'orderbook_snapshot',
               'redacted': True, 'redacted_reason': 'not_lossless_text', 'sid': 1, 'seq': 4})
        j.frames += 1
        j.tr('close'); j.end()
        r = run(j)
        self.assertIn('redacted_public_frame', r['reasons'])
        self.assertFalse(r['locally_consistent'])
        self.assertFalse(r['notes']['books']['0:T1']['valid_at_end'])

    def test_duplicate_key_book_frame_invalidates_the_epoch(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        j.fr('{"type":"orderbook_delta","sid":1,"seq":2,"seq":3,"msg":{"market_ticker":"T1"}}')
        j.tr('close'); j.end()
        r = run(j)
        self.assertTrue(any(i['why'] == 'unparsable_frame' for i in r['notes']['anomalies']))
        self.assertFalse(r['locally_consistent'])

    def test_footer_dropped_total_must_match_markers(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap(); j.tr('close'); j.end(dropped_total=500)
        self.assertIn('dropped_total_mismatch', run(j)['reasons'])

    def test_journal_that_ends_connected_is_reported(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap(); j.end()
        r = run(j)
        self.assertIn('ended_while_connected', r['reasons'])
        self.assertTrue(r['locally_consistent'])

    def test_frames_without_a_subscribe_command_are_reported(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.snap(); j.tr('close'); j.end()
        self.assertIn('epoch_without_subscribe_command', run(j)['reasons'])

    def test_scrubbed_frame_is_accepted_but_reported(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        raw = json.dumps({'type': 'orderbook_delta', 'sid': 1, 'seq': 2, 'msg': {'market_ticker': 'T1'}})
        j.fr(raw, scrubbed=['client_order_id'], stored_sha256=sha(raw), sha256='0' * 64, bytes=77)
        j.tr('close'); j.end()
        r = run(j)
        self.assertTrue(r['locally_consistent'], r['reasons'])
        self.assertEqual(r['notes']['scrubbed'], 1)
        self.assertIn('frames_scrubbed', r['reasons'])
        self.assertTrue(r['continuity_intact'])

    def _scrubbed(self, **over):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        raw = json.dumps({'type': 'orderbook_delta', 'sid': 1, 'seq': 2, 'msg': {'market_ticker': 'T1'}})
        rec = {'scrubbed': ['client_order_id'], 'stored_sha256': sha(raw), 'sha256': '0' * 64, 'bytes': 77}
        rec.update(over)
        j.fr(raw, **rec)
        j.tr('close'); j.end()
        return run(j)

    def test_scrubbed_marker_needs_a_valid_list_and_stored_hash(self):
        self.assertTrue(self._scrubbed()['locally_consistent'])
        self.assertFalse(self._scrubbed(scrubbed=[])['locally_consistent'])                 # empty marker would skip every check
        self.assertFalse(self._scrubbed(scrubbed=['market_ticker'])['locally_consistent'])  # not an own-order field
        self.assertFalse(self._scrubbed(stored_sha256='0' * 64)['locally_consistent'])      # altered stored text
        self.assertFalse(self._scrubbed(scrubbed='client_order_id')['locally_consistent'])  # wrong type

    def test_snapshot_after_skipped_seqs_invalidates_the_other_books_on_the_sid(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out()
        j.snap(sid=1, seq=1, ticker='T1'); j.delta(sid=1, seq=2, ticker='T1')
        j.snap(sid=1, seq=9, ticker='T2')                      # seq 3-8 never seen: T1 may have lost deltas
        j.tr('close'); j.end()
        r = run(j)
        self.assertEqual(r['notes']['gaps'][0]['on'], 'snapshot')
        self.assertFalse(r['continuity_intact'])
        self.assertEqual(r['notes']['books']['0:T1']['last_invalid_why'], 'sequence_gap')

    def test_only_a_subscribe_command_counts_for_the_epoch(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out('{"id":2,"cmd":"ping"}'); j.snap(); j.tr('close'); j.end()
        self.assertIn('epoch_without_subscribe_command', run(j)['reasons'])

    def test_private_field_left_in_a_stored_frame_is_rejected(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        j.fr(json.dumps({'type': 'orderbook_delta', 'sid': 1, 'seq': 2, 'msg': {'market_ticker': 'T1', 'client_order_id': 'abc'}}))
        j.tr('close'); j.end()
        self.assertIn('private_field_in_stored_frame', run(j)['reasons'])

    def test_seqless_frames_are_not_checked_and_the_report_says_so(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        j.fr('{"type":"trade","msg":{"market_ticker":"T1"}}'); j.fr('{"type":"trade","msg":{"market_ticker":"T1"}}')
        j.tr('close'); j.end()
        r = run(j)
        self.assertTrue(r['continuity_intact'])
        self.assertIn('cannot be detected', r['unchecked'])


class Decisions(unittest.TestCase):
    """Heat decision receipts (kind 'decision') sit in the same chain as the frames."""
    def journal(self, make):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap()
        make(j)
        j.tr('close'); j.end()
        return j

    def test_receipts_are_counted_and_the_journal_stays_consistent(self):
        r = run(self.journal(lambda j: (j.dec(), j.dec())))
        self.assertTrue(r['locally_consistent'], r['reasons'])
        self.assertEqual(r['notes']['decisions'], 2)
        self.assertEqual(r['notes']['decisions_unrecorded'], 0)
        self.assertFalse(r['decision_replay_checked_here'])

    def test_an_edited_receipt_breaks_the_chain(self):
        j = self.journal(lambda j: j.dec())
        i = next(k for k, l in enumerate(j.lines) if '"decision"' in l)
        j.lines[i] = j.lines[i].replace('markets', 'marketz')
        self.assertIn('hash_chain_invalid', run(j)['reasons'])

    def test_a_rechained_receipt_whose_text_does_not_match_its_hash_is_flagged(self):
        r = run(self.journal(lambda j: j.dec(input_sha256='0' * 64)))
        self.assertIn('decision_sha256_mismatch', r['reasons'])
        self.assertFalse(r['locally_consistent'])

    def test_receipt_numbering_must_run_from_zero_without_gaps(self):
        r = run(self.journal(lambda j: (j.dec(), j.dec(seq=5))))
        self.assertIn('malformed_record', r['reasons'])

    def test_footer_must_count_the_receipts(self):
        j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap(); j.dec(); j.tr('close'); j.end(decisions=0)
        self.assertIn('bad_footer', run(j)['reasons'])
        k = J(); k.tr('connecting'); k.tr('open'); k.out(); k.snap(); k.dec(); k.tr('close')
        k.put({'kind': 'end', 'records': k.n, 'frames': k.frames, 'dropped_total': 0, 'failed': None})   # an old-style footer with receipts present
        self.assertIn('bad_footer', run(k)['reasons'])

    def test_an_own_order_identifier_in_a_receipt_is_rejected(self):
        r = run(self.journal(lambda j: j.dec(inp={'now': 1, 'msg': {'client_order_id': 'abc'}})))
        self.assertIn('private_field_in_decision', r['reasons'])
        self.assertFalse(r['locally_consistent'])

    def test_a_receipt_kept_as_hashes_only_is_a_coverage_gap_not_a_broken_journal(self):
        def make(j):
            j.dec()
            j.put({'kind': 'decision', 'epoch': j.epoch, **j.stamp(), 'seq': j.decisions, 'input_sha256': '1' * 64, 'result_sha256': '2' * 64, 'withheld': 'oversized'})
            j.decisions += 1; j.unrecorded += 1
        j = self.journal(make)
        r = run(j)
        self.assertIn('decision_not_recorded', r['reasons'])
        self.assertTrue(r['locally_consistent'], r['reasons'])
        self.assertEqual(r['notes']['decisions_unrecorded'], 1)

    def test_a_receipt_that_could_not_be_serialized_carries_no_hashes(self):
        def make(j):
            j.put({'kind': 'decision', 'epoch': j.epoch, **j.stamp(), 'seq': j.decisions, 'withheld': 'serialize_error', 'detail': 'x'}); j.decisions += 1; j.unrecorded += 1
        r = run(self.journal(make))
        self.assertIn('decision_not_recorded', r['reasons'])
        self.assertTrue(r['locally_consistent'], r['reasons'])

    def test_a_receipt_with_text_and_a_withheld_reason_is_malformed(self):
        r = run(self.journal(lambda j: j.dec(withheld='oversized')))
        self.assertIn('malformed_record', r['reasons'])

    def test_a_receipt_that_is_not_a_json_object_is_malformed(self):
        r = run(self.journal(lambda j: j.dec(input_json='[1]', input_sha256=sha('[1]'))))
        self.assertIn('malformed_record', r['reasons'])

    def test_duplicate_keys_in_a_receipt_are_rejected(self):
        t = '{"now":1,"now":2}'
        r = run(self.journal(lambda j: j.dec(input_json=t, input_sha256=sha(t))))
        self.assertIn('malformed_record', r['reasons'])

    def test_receipts_do_not_hide_a_silent_socket(self):
        # ten minutes with no frame at all, a receipt every 30 s: the silence is measured from the feed, not from the last receipt
        def make(j):
            for _ in range(20):
                j.dec(dt=30_000)
        r = run(self.journal(make))
        self.assertGreaterEqual(r['notes']['long_silences'], 1)

    def test_footer_counts_must_be_integers(self):
        for bad in (True, 1.0, '1'):
            j = J(); j.tr('connecting'); j.tr('open'); j.out(); j.snap(); j.dec(); j.tr('close'); j.end(decisions=bad)
            self.assertIn('bad_footer', run(j)['reasons'], repr(bad))

    def test_a_receipt_dropped_for_backpressure_carries_no_hashes_and_is_a_coverage_gap(self):
        def make(j):
            j.put({'kind': 'decision', 'epoch': j.epoch, **j.stamp(), 'seq': j.decisions, 'withheld': 'backpressure'}); j.decisions += 1; j.unrecorded += 1
        r = run(self.journal(make))
        self.assertIn('decision_not_recorded', r['reasons'])
        self.assertTrue(r['locally_consistent'], r['reasons'])

    def test_an_unknown_withheld_reason_is_malformed(self):
        r = run(self.journal(lambda j: j.put({'kind': 'decision', 'epoch': j.epoch, **j.stamp(), 'seq': j.decisions, 'withheld': 'because'})))
        self.assertIn('malformed_record', r['reasons'])

    def test_one_silence_is_counted_once_however_many_receipts_fall_inside_it(self):
        def make(j):
            for _ in range(20):
                j.dec(dt=30_000)
        r = run(self.journal(make))
        self.assertLessEqual(r['notes']['long_silences'], 2)   # the receipts' stretch once, and the close that ends it

    def test_the_declared_size_of_a_receipt_must_be_its_real_size(self):
        r = run(self.journal(lambda j: j.dec(input_bytes=3)))
        self.assertIn('decision_size_mismatch', r['reasons'])
        self.assertFalse(r['locally_consistent'])

    def test_a_decision_on_a_non_finite_number_is_flagged_but_does_not_break_the_journal(self):
        r = run(self.journal(lambda j: j.dec(inp={'now': 1, 'markets': [{'position': {'$num': 'NaN'}}]})))
        self.assertIn('decision_on_non_finite_number', r['reasons'])
        self.assertEqual(r['notes']['decisions_on_non_finite_number'], 1)
        self.assertTrue(r['locally_consistent'], r['reasons'])

    def test_a_receipt_over_its_budget_is_a_coverage_gap_with_hashes(self):
        def make(j):
            j.put({'kind': 'decision', 'epoch': j.epoch, **j.stamp(), 'seq': j.decisions, 'input_sha256': '1' * 64, 'result_sha256': '2' * 64, 'withheld': 'budget'})
            j.decisions += 1; j.unrecorded += 1
        r = run(self.journal(make))
        self.assertIn('decision_not_recorded', r['reasons'])
        self.assertTrue(r['locally_consistent'], r['reasons'])


class FileStreaming(unittest.TestCase):
    """The CLI reads the journal line by line (a capture can reach hundreds of MB; the old code held it all in RAM)."""
    def write(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, 'f%d' % len(os.listdir(tmp.name)))
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        return path

    def cli(self, path, *extra):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'verify_journal.py')
        p = subprocess.run([sys.executable, '-I', script, path, *extra], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout)

    def test_reader_is_lazy(self):
        self.assertTrue(inspect.isgenerator(vj.iter_journal_lines(self.write('a\nb\n'))))

    def test_same_lines_as_a_whole_file_split(self):
        for text in ('a\nb\n', 'a\nb', 'a\n\n', '', '\n', 'a\r\nb\rc\n'):
            whole = text.split('\n')
            if whole and whole[-1] == '':
                whole.pop()
            got = [x.rstrip('\n') for x in vj.iter_journal_lines(self.write(text))]
            self.assertEqual(got, whole, repr(text))

    def test_cli_report_matches_in_memory_report_with_and_without_final_lf(self):
        j = good()
        want = vj.verify(j.lines, j.anchor())
        for tail in ('\n', ''):
            path = self.write('\n'.join(j.lines) + tail)
            apath = self.write('\n'.join(j.anchor()) + '\n')
            code, rep = self.cli(path, '--anchor', apath)
            self.assertEqual(code, 0, rep['reasons'])
            self.assertEqual(rep['locally_consistent'], want['locally_consistent'])
            self.assertEqual(rep['notes']['frames'], want['notes']['frames'])
            self.assertEqual(rep['reasons'], want['reasons'])

    def test_cli_exit_code_is_nonzero_for_a_tampered_file(self):
        j = good()
        lines = list(j.lines)
        lines[3] = lines[3] + 'x'
        code, rep = self.cli(self.write('\n'.join(lines) + '\n'))
        self.assertEqual(code, 1)
        self.assertIn('hash_chain_invalid', rep['reasons'])


if __name__ == '__main__':
    unittest.main()
