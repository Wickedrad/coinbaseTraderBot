#!/usr/bin/env python3
"""Offline verifier for raw-tap journals (schema 1, written by rawTap.ts). RESEARCH ONLY.

Reads files only: no network, no credentials, no bot code. It CHECKS that a journal is internally consistent and reports
where order-book continuity breaks, per ticker. It can NEVER say a journal is exchange-authenticated or eligible for
Phase B: those two report fields are constants (False) with no code path that sets them.

What a passing result means: no line was edited without re-hashing every later line, the header/config hash, footer
counts, epochs and clocks are consistent. A forger who re-hashes the whole file passes; only an anchor file kept somewhere
the capturing process could not touch, and covering the whole journal (anchor == 'matched'), narrows that. This script
cannot check where the anchor was kept.

What it cannot see: loss or duplication of frames that carry no seq (trades, lifecycle, index values); a frame the tap was
never handed. Book frames (orderbook_snapshot / orderbook_delta) are sequenced and checked.

Usage: verify_journal.py JOURNAL [--anchor ANCHOR_FILE] [--max-gap-ms N]   (exit 0 = consistent, 1 = not)
"""
import argparse
import hashlib
import json
import sys

GENESIS = '0' * 64
PUBLIC_TYPES = {
    'orderbook_snapshot', 'orderbook_delta', 'trade', 'ticker', 'ticker_v2', 'market_lifecycle', 'market_lifecycle_v2',
    'event_lifecycle', 'subscribed', 'ok', 'unsubscribed', 'error',
    'cfbenchmarks_value', 'cfbenchmarks_value_5hz', 'cfbenchmarks_value_indexlist', 'cfbenchmarks_value_5hz_indexlist',
}
BOOK_TYPES = {'orderbook_snapshot', 'orderbook_delta'}
PRIVATE_MSG_FIELDS = {'client_order_id', 'order_id', 'subaccount', 'subaccount_number', 'user_id'}

# Reasons that make the journal itself untrustworthy. Everything else describes the market data inside it.
STRUCTURAL = {
    'hash_chain_invalid', 'record_number_gap', 'missing_or_bad_header', 'config_hash_mismatch', 'config_not_json',
    'header_claims_authentication', 'second_header', 'bad_footer', 'trailing_data', 'malformed_record',
    'missing_valid_footer', 'no_frames', 'anchor_mismatch', 'anchor_empty', 'epoch_mismatch',
    'connecting_without_close', 'open_without_connecting', 'close_without_connecting',
    'frame_outside_open_epoch', 'outbound_outside_open_epoch', 'monotonic_clock_regressed',
    'wall_clock_went_backwards', 'wall_clock_stepped', 'frame_sha256_mismatch', 'declared_type_mismatch',
    'capture_reported_failure', 'frame_text_missing', 'frame_field_mismatch', 'unparsable_public_frame',
    'redacted_public_frame', 'dropped_total_mismatch', 'private_field_in_stored_frame',
}


def _bad_const(_):
    raise ValueError('non-finite number')


def strict_json(text):
    """json.loads that rejects duplicate keys at any depth and NaN/Infinity."""
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('duplicate key')
            out[k] = v
        return out
    return json.loads(text, object_pairs_hook=pairs, parse_constant=_bad_const)


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode('utf-8')).hexdigest()


def is_int(v):
    return type(v) is int


class Books:
    """Order-book continuity, per (epoch, ticker). Mirrors bot/kalshi/ws.ts onMessage for sequencing (a snapshot sets a
    subscription's baseline; any later frame on it must be exactly previous+1) and is stricter where the bot is lenient: a
    gap invalidates EVERY ticker served by that sid, and only that ticker's own next snapshot restores it."""

    def __init__(self):
        self.seq_of = {}       # (epoch, sid) -> last seq
        self.tickers = {}      # (epoch, ticker) -> {'valid', 'sid', 'windows', 'why'}
        self.sid_tickers = {}  # (epoch, sid) -> set(ticker)
        self.gaps = []
        self.anomalies = []    # things that break or taint continuity
        self.restored = 0
        self.ended_by_disconnect = 0

    def _kill(self, key, why, n, sid=None, count_as_anomaly=True):
        st = self.tickers[key]
        if st['valid']:
            st['valid'], st['why'] = False, why
            if count_as_anomaly:
                self.anomalies.append({'n': n, 'epoch': key[0], 'ticker': key[1], 'sid': sid, 'why': why})
            else:
                self.ended_by_disconnect += 1

    def kill_sid(self, epoch, sid, why, n):
        ts = self.sid_tickers.get((epoch, sid), set())
        if not ts:
            self.anomalies.append({'n': n, 'epoch': epoch, 'ticker': None, 'sid': sid, 'why': why})
        for t in ts:
            self._kill((epoch, t), why, n, sid)

    def kill_epoch(self, epoch, why, n, anomaly=True):
        any_valid = False
        for key in list(self.tickers):
            if key[0] == epoch and self.tickers[key]['valid']:
                any_valid = True
                self._kill(key, why, n, self.tickers[key]['sid'], anomaly)
        if anomaly and not any_valid:
            self.anomalies.append({'n': n, 'epoch': epoch, 'ticker': None, 'sid': None, 'why': why})

    def sequence(self, epoch, sid, seq, n):
        """Returns True when the frame continues its subscription (or starts it)."""
        prev = self.seq_of.get((epoch, sid))
        self.seq_of[(epoch, sid)] = seq
        if prev is not None and seq != prev + 1:
            self.gaps.append({'n': n, 'epoch': epoch, 'sid': sid, 'expected': prev + 1, 'got': seq})
            self.kill_sid(epoch, sid, 'sequence_gap', n)
            return False
        return True

    def snapshot(self, epoch, sid, seq, ticker, n):
        prev = self.seq_of.get((epoch, sid))
        self.seq_of[(epoch, sid)] = seq
        if prev is not None and seq != prev + 1:
            # frames were skipped on this subscription before this snapshot: every book it serves is suspect except the
            # one this snapshot rebuilds (seq is per subscription, as ws.ts assumes by keying lastSeq on sid alone)
            self.gaps.append({'n': n, 'epoch': epoch, 'sid': sid, 'expected': prev + 1, 'got': seq, 'on': 'snapshot'})
            self.kill_sid(epoch, sid, 'sequence_gap', n)
        key = (epoch, ticker)
        st = self.tickers.setdefault(key, {'valid': False, 'sid': sid, 'windows': 0, 'why': None})
        if not st['valid']:
            st['windows'] += 1
            if st['why'] is not None:
                self.restored += 1
        st['valid'], st['sid'], st['why'] = True, sid, None
        self.sid_tickers.setdefault((epoch, sid), set()).add(ticker)

    def delta(self, epoch, sid, seq, ticker, n):
        if not self.sequence(epoch, sid, seq, n):
            return
        key = (epoch, ticker)
        st = self.tickers.get(key)
        if st is None:
            self.tickers[key] = {'valid': False, 'sid': sid, 'windows': 0, 'why': 'delta_before_snapshot'}
            self.sid_tickers.setdefault((epoch, sid), set()).add(ticker)
            self.anomalies.append({'n': n, 'epoch': epoch, 'ticker': ticker, 'sid': sid, 'why': 'delta_before_snapshot'})
        elif st['valid'] and st['sid'] != sid:
            self._kill(key, 'delta_from_unexpected_sid', n, sid)

    def summary(self, limit=50):
        out = {}
        for (epoch, ticker), st in sorted(self.tickers.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))[:limit]:
            out[f'{epoch}:{ticker}'] = {'valid_windows': st['windows'], 'valid_at_end': st['valid'], 'last_invalid_why': st['why']}
        return out


def verify(lines, anchor_lines=None, max_gap_ms=60_000):
    reasons = set()
    notes = {'frames': 0, 'redacted': 0, 'scrubbed': 0, 'outbound': 0, 'transport': 0, 'dropped_frames': 0, 'epochs': 0,
             'unparsable_public_frames': 0, 'clock_regressions': 0, 'long_silences': 0}
    books = Books()
    prev = GENESIS
    hashes = []
    ended = False
    header = None
    n_expected = 0
    last_wall = last_mono = None
    epoch = -1
    state = 'idle'            # idle | connecting | open | closed
    epoch_frames, epoch_outbound = {}, {}
    marker_total = 0
    footer = None

    for raw_line in lines:
        line = raw_line.rstrip('\n')
        if ended:
            reasons.add('trailing_data')
            break
        try:
            h, body = line.split('\t', 1)
            if sha(prev + '\n' + body) != h:
                reasons.add('hash_chain_invalid')
                break
            rec = strict_json(body)
            if type(rec) is not dict:
                raise ValueError('record not an object')
            prev = h
            hashes.append(h)
            if not is_int(rec.get('n')) or rec['n'] != n_expected:
                reasons.add('record_number_gap')
                break
            n = n_expected
            n_expected += 1
            kind = rec.get('kind')
            if n == 0:
                if kind != 'header' or rec.get('schema') != 1:
                    reasons.add('missing_or_bad_header')
                    break
                cj = rec.get('config_json')
                if not isinstance(cj, str) or sha(cj) != rec.get('config_sha256'):
                    reasons.add('config_hash_mismatch')
                if rec.get('exchange_authenticated') is not False:
                    reasons.add('header_claims_authentication')
                try:
                    strict_json(cj)
                except Exception:
                    reasons.add('config_not_json')
                header = rec
                last_wall, last_mono = rec.get('started_wall_ms'), int(rec.get('started_mono_ns', '0'))
                continue
            if kind == 'header':
                reasons.add('second_header')
                break
            if kind == 'end':
                if rec.get('records') != n or rec.get('frames') != notes['frames']:
                    reasons.add('bad_footer')
                ended = True
                footer = {'dropped_total': rec.get('dropped_total'), 'failed': rec.get('failed'), 'reason': rec.get('reason')}
                if rec.get('failed'):
                    reasons.add('capture_reported_failure')
                continue
            # every other record carries a time on two clocks
            wall, mono = rec.get('wall_ms'), rec.get('mono_ns')
            if not is_int(wall) or not isinstance(mono, str) or not mono.isdigit():
                raise ValueError('bad stamp')
            mono = int(mono)
            if last_mono is not None and mono < last_mono:
                reasons.add('monotonic_clock_regressed')
            if last_wall is not None and wall < last_wall:
                notes['clock_regressions'] += 1
                reasons.add('wall_clock_went_backwards')
            if last_wall is not None and last_mono is not None:
                # wall time and the monotonic clock must advance together; a jump means the system clock was stepped
                if abs((wall - last_wall) - (mono - last_mono) / 1e6) > 2000:
                    reasons.add('wall_clock_stepped')
                if state == 'open' and wall - last_wall > max_gap_ms:
                    notes['long_silences'] += 1
            last_wall, last_mono = wall, mono
            if kind == 'transport':
                notes['transport'] += 1
                ev = rec.get('event')
                if ev == 'connecting':
                    if state in ('connecting', 'open'):
                        reasons.add('connecting_without_close')
                    epoch += 1
                    notes['epochs'] = epoch + 1
                    state = 'connecting'
                elif ev == 'open':
                    if state != 'connecting':
                        reasons.add('open_without_connecting')
                    state = 'open'
                elif ev == 'error':
                    pass
                elif ev == 'close':
                    if state == 'idle':
                        reasons.add('close_without_connecting')
                    state = 'closed'
                    books.kill_epoch(epoch, 'transport_closed', n, anomaly=False)
                else:
                    raise ValueError('unknown transport event')
                if rec.get('epoch') != epoch:
                    reasons.add('epoch_mismatch')
                continue
            if rec.get('epoch') != epoch:
                reasons.add('epoch_mismatch')
            if kind == 'outbound':
                notes['outbound'] += 1
                if '"cmd":"subscribe"' in rec.get('text', ''):
                    epoch_outbound[epoch] = epoch_outbound.get(epoch, 0) + 1
                if state != 'open':
                    reasons.add('outbound_outside_open_epoch')
                if not isinstance(rec.get('text'), str):
                    raise ValueError('outbound text')
            elif kind == 'dropped':
                cnt = rec.get('count')
                if not is_int(cnt) or cnt < 1:
                    raise ValueError('drop count')
                notes['dropped_frames'] += cnt
                marker_total += cnt
                reasons.add('frames_dropped')
                books.kill_epoch(epoch, 'frames_dropped', n)
            elif kind == 'frame':
                notes['frames'] += 1
                epoch_frames[epoch] = epoch_frames.get(epoch, 0) + 1
                if state != 'open':
                    reasons.add('frame_outside_open_epoch')
                _frame(rec, n, epoch, books, notes, reasons)
            else:
                raise ValueError('unknown record kind')
        except (ValueError, TypeError, KeyError, IndexError):
            reasons.add('malformed_record')
            break
    if not ended:
        reasons.add('missing_valid_footer')
    else:
        if state in ('connecting', 'open'):
            reasons.add('ended_while_connected')
        if footer and footer['dropped_total'] != marker_total:
            reasons.add('dropped_total_mismatch')
    for e, c in epoch_frames.items():
        if c and not epoch_outbound.get(e):
            reasons.add('epoch_without_subscribe_command')
    if header is None:
        reasons.add('missing_or_bad_header')
    if not notes['frames']:
        reasons.add('no_frames')
    if notes['scrubbed']:
        reasons.add('frames_scrubbed')
    anchor_status, anchored = 'none', 0
    if anchor_lines is not None:
        anchor_status = 'matched'
        count = 0
        for al in anchor_lines:
            try:
                a = strict_json(al)
                c = a['count']
                if not is_int(c) or c < 1 or c > len(hashes) or hashes[c - 1] != a['head']:
                    anchor_status = 'mismatch'
                    break
                count += 1
                anchored = max(anchored, c)
            except Exception:
                anchor_status = 'mismatch'
                break
        if anchor_status == 'matched':
            if count == 0:
                anchor_status = 'empty'
            elif anchored < len(hashes):
                anchor_status = 'partial'   # protects the prefix only; later records could be rewritten and re-hashed
        if anchor_status != 'matched':
            reasons.add('anchor_' + anchor_status)
    consistent = not (reasons & STRUCTURAL)
    notes['footer'] = footer
    notes['gaps'] = books.gaps
    notes['anomalies'] = books.anomalies
    notes['windows_ended_by_disconnect'] = books.ended_by_disconnect
    notes['snapshots_restoring_a_ticker'] = books.restored
    notes['books'] = books.summary()
    notes['books_not_listed'] = max(0, len(books.tickers) - len(notes['books']))
    return {
        'locally_consistent': consistent,
        # No gap, drop, unsequenced or unreadable book frame, and nothing withheld that the bot would have applied.
        'continuity_intact': consistent and not books.gaps and not books.anomalies and not notes['dropped_frames'],
        'reasons': sorted(reasons),
        'records': n_expected,
        'head': hashes[-1] if hashes else None,
        'anchor': anchor_status,
        'anchored_records': anchored,
        'notes': notes,
        'unchecked': 'loss or duplication of frames without a seq (trade, lifecycle, index) cannot be detected',
        # Constants. Nothing in this file assigns anything else to these two.
        'exchange_authenticated': False,
        'phase_b_eligible': False,
    }


def _frame(rec, n, epoch, books, notes, reasons):
    sha_declared, bytes_len, declared_type = rec.get('sha256'), rec.get('bytes'), rec.get('type')
    if not is_int(bytes_len) or not isinstance(sha_declared, str):
        raise ValueError('frame fields')
    if rec.get('redacted'):
        notes['redacted'] += 1
        sid, seq = rec.get('sid'), rec.get('seq')
        if (sid is not None and not is_int(sid)) or (seq is not None and not is_int(seq)):
            reasons.add('frame_field_mismatch')
            return
        if declared_type in PUBLIC_TYPES:
            # a frame the bot would apply, withheld: its effect cannot be reconstructed
            reasons.add('redacted_public_frame')
            if declared_type in BOOK_TYPES:
                books.kill_epoch(epoch, 'redacted_book_frame', n)
        if sid is not None and seq is not None:
            books.sequence(epoch, sid, seq, n)
        return
    raw = rec.get('raw')
    if not isinstance(raw, str):
        reasons.add('frame_text_missing')
        return
    scrubbed = rec.get('scrubbed')
    if scrubbed is not None:
        notes['scrubbed'] += 1   # stored text had own-order identifiers removed; sha256/bytes describe the original frame
        if (not isinstance(scrubbed, list) or not scrubbed or not set(scrubbed) <= PRIVATE_MSG_FIELDS
                or sha(raw.encode('utf-8')) != rec.get('stored_sha256')):
            reasons.add('frame_sha256_mismatch' if isinstance(scrubbed, list) and scrubbed else 'frame_field_mismatch')
    else:
        data = raw.encode('utf-8')
        if sha(data) != sha_declared or len(data) != bytes_len:
            reasons.add('frame_sha256_mismatch')
    try:
        env = strict_json(raw)
        if type(env) is not dict or type(env.get('type')) is not str:
            raise ValueError('envelope')
    except ValueError:
        notes['unparsable_public_frames'] += 1
        reasons.add('unparsable_public_frame')
        books.kill_epoch(epoch, 'unparsable_frame', n)   # the bot may have applied what we cannot read
        return
    if env['type'] != declared_type:
        reasons.add('declared_type_mismatch')
    sid, seq = env.get('sid'), env.get('seq')
    msg = env.get('msg') if isinstance(env.get('msg'), dict) else {}
    if PRIVATE_MSG_FIELDS & set(msg):
        reasons.add('private_field_in_stored_frame')
    if env['type'] in BOOK_TYPES:
        ticker = msg.get('market_ticker')
        if not is_int(sid) or not is_int(seq) or not isinstance(ticker, str) or not ticker:
            # cannot be sequenced or assigned to a book, yet the bot applies it: fail closed for the whole connection
            books.kill_epoch(epoch, 'unsequenced_book_frame', n)
            return
        if env['type'] == 'orderbook_snapshot':
            books.snapshot(epoch, sid, seq, ticker, n)
        else:
            books.delta(epoch, sid, seq, ticker, n)
        return
    if (sid is not None and not is_int(sid)) or (seq is not None and not is_int(seq)):
        reasons.add('frame_field_mismatch')
        return
    if sid is not None and seq is not None:
        books.sequence(epoch, sid, seq, n)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('journal')
    ap.add_argument('--anchor')
    ap.add_argument('--max-gap-ms', type=int, default=60_000)
    a = ap.parse_args()
    with open(a.journal, encoding='utf-8', newline='') as f:
        lines = f.read().split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    anchor = None
    if a.anchor:
        with open(a.anchor, encoding='utf-8') as f:
            anchor = [x for x in f.read().split('\n') if x]
    report = verify(lines, anchor, a.max_gap_ms)
    # Summaries only: the gap and anomaly lists can be long.
    for k in ('gaps', 'anomalies'):
        report['notes'][k + '_count'] = len(report['notes'][k])
        report['notes'][k] = report['notes'][k][:20]
    json.dump(report, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write('\n')
    return 0 if report['locally_consistent'] else 1


if __name__ == '__main__':
    sys.exit(main())
