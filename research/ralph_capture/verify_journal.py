#!/usr/bin/env python3
"""Offline verifier for raw-tap journals (schema 1, written by rawTap.ts). RESEARCH ONLY.

Reads files only: no network, no credentials, no bot code. It checks that a journal is internally consistent and
reports where the market-data continuity breaks. It can NEVER say a journal is exchange-authenticated or eligible for
Phase B: those two report fields are constants (False) with no code path that sets them. A chain that matches only shows
the file was not edited after it was written; an anchor file that matches shows it only if the anchor was kept somewhere
the capturing process could not touch, which this script cannot check.

Usage: verify_journal.py JOURNAL [--anchor ANCHOR_FILE] [--max-gap-ms N]   (exit 0 = locally consistent, 1 = not)
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


def verify(lines, anchor_lines=None, max_gap_ms=60_000):
    reasons = set()
    notes = {'frames': 0, 'redacted': 0, 'outbound': 0, 'transport': 0, 'dropped_frames': 0, 'epochs': 0,
             'unparsable_public_frames': 0, 'non_public_frames': 0, 'gaps': [], 'invalidations': [],
             'clock_regressions': 0, 'long_silences': 0}
    prev = GENESIS
    hashes = []
    ended = False
    header = None
    n_expected = 0
    last_wall = last_mono = None
    epoch = -1
    state = 'idle'            # idle | connecting | open | closed
    seq_of = {}               # (epoch, sid) -> last seq seen
    valid = {}                # (epoch, sid) -> bool: a snapshot was seen and no gap/drop since
    ticker_of = {}            # (epoch, sid) -> ticker (from snapshots)
    invalid_why = {}          # (epoch, sid) -> why it is not valid

    def invalidate_epoch(why, n):
        for key in list(valid):
            if key[0] == epoch and valid[key]:
                valid[key] = False
                invalid_why[key] = why
                notes['invalidations'].append({'n': n, 'epoch': epoch, 'sid': key[1], 'why': why})

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
            if rec.get('n') != n_expected or not is_int(rec.get('n')):
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
                notes['footer'] = {'dropped_total': rec.get('dropped_total'), 'failed': rec.get('failed')}
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
            if rec.get('epoch') != epoch and kind != 'transport':
                reasons.add('epoch_mismatch')
            if kind == 'transport':
                notes['transport'] += 1
                ev = rec.get('event')
                if ev == 'connecting':
                    if state in ('connecting', 'open'):
                        reasons.add('connecting_without_close')
                    epoch += 1
                    notes['epochs'] = epoch + 1
                    state = 'connecting'
                    if rec.get('epoch') != epoch:
                        reasons.add('epoch_mismatch')
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
                    invalidate_epoch('transport_closed', n)
                else:
                    raise ValueError('unknown transport event')
                if ev != 'connecting' and rec.get('epoch') != epoch:
                    reasons.add('epoch_mismatch')
            elif kind == 'outbound':
                notes['outbound'] += 1
                if state != 'open':
                    reasons.add('outbound_outside_open_epoch')
                if not isinstance(rec.get('text'), str):
                    raise ValueError('outbound text')
            elif kind == 'dropped':
                cnt = rec.get('count')
                if not is_int(cnt) or cnt < 1:
                    raise ValueError('drop count')
                notes['dropped_frames'] += cnt
                reasons.add('frames_dropped')
                invalidate_epoch('frames_dropped', n)
            elif kind == 'frame':
                notes['frames'] += 1
                if state != 'open':
                    reasons.add('frame_outside_open_epoch')
                _frame(rec, n, epoch, seq_of, valid, ticker_of, invalid_why, notes, reasons)
            else:
                raise ValueError('unknown record kind')
        except (ValueError, TypeError, KeyError, IndexError):
            reasons.add('malformed_record')
            break
    if not ended:
        reasons.add('missing_valid_footer')
    if header is None:
        reasons.add('missing_or_bad_header')
    if not notes['frames']:
        reasons.add('no_frames')
    anchor_status = 'none'
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
            except Exception:
                anchor_status = 'mismatch'
                break
        if count == 0 and anchor_status == 'matched':
            anchor_status = 'empty'
        if anchor_status in ('mismatch', 'empty'):
            reasons.add('anchor_' + anchor_status)
    # Only these reasons break the chain's meaning; the others describe market-data quality.
    structural = {'hash_chain_invalid', 'record_number_gap', 'missing_or_bad_header', 'config_hash_mismatch', 'config_not_json',
                  'header_claims_authentication', 'second_header', 'bad_footer', 'trailing_data', 'malformed_record',
                  'missing_valid_footer', 'no_frames', 'anchor_mismatch', 'anchor_empty', 'epoch_mismatch',
                  'connecting_without_close', 'open_without_connecting', 'close_without_connecting',
                  'frame_outside_open_epoch', 'outbound_outside_open_epoch', 'monotonic_clock_regressed',
                  'wall_clock_went_backwards', 'wall_clock_stepped', 'frame_sha256_mismatch', 'declared_type_mismatch',
                  'capture_reported_failure', 'frame_text_missing', 'frame_field_mismatch'}
    return {
        'locally_consistent': not (reasons & structural),
        'reasons': sorted(reasons),
        'records': n_expected,
        'head': hashes[-1] if hashes else None,
        'anchor': anchor_status,
        'notes': {k: v for k, v in notes.items()},
        # Constants. Nothing in this file assigns anything else to these two.
        'exchange_authenticated': False,
        'phase_b_eligible': False,
    }


def _frame(rec, n, epoch, seq_of, valid, ticker_of, invalid_why, notes, reasons):
    sha_declared = rec.get('sha256')
    bytes_len = rec.get('bytes')
    if not is_int(bytes_len) or not isinstance(sha_declared, str):
        raise ValueError('frame fields')
    declared_type = rec.get('type')
    if rec.get('redacted'):
        notes['redacted'] += 1
        if declared_type in PUBLIC_TYPES and rec.get('binary') is False:
            reasons.add('redacted_public_frame')   # a public frame must be kept as text
        sid, seq = rec.get('sid'), rec.get('seq')
        _track(epoch, sid, seq, declared_type, n, seq_of, valid, ticker_of, invalid_why, notes, None)
        return
    raw = rec.get('raw')
    if not isinstance(raw, str):
        reasons.add('frame_text_missing')
        return
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
        return
    if env['type'] != declared_type:
        reasons.add('declared_type_mismatch')
    sid, seq = env.get('sid'), env.get('seq')
    if (sid is not None and not is_int(sid)) or (seq is not None and not is_int(seq)):
        reasons.add('frame_field_mismatch')
        return
    msg = env.get('msg') if isinstance(env.get('msg'), dict) else {}
    _track(epoch, sid, seq, env['type'], n, seq_of, valid, ticker_of, invalid_why, notes, msg.get('market_ticker'))


def _track(epoch, sid, seq, typ, n, seq_of, valid, ticker_of, invalid_why, notes, ticker):
    """Same rule as bot/kalshi/ws.ts onMessage, made stricter: a snapshot sets the baseline; any later frame on the
    subscription must be exactly previous+1; after a gap the subscription stays invalid until the next snapshot (the bot
    would go on applying deltas once its baseline is dropped; this verifier does not trust them)."""
    if sid is None or seq is None:
        return
    key = (epoch, sid)
    if typ == 'orderbook_snapshot':
        seq_of[key] = seq
        valid[key] = True
        invalid_why.pop(key, None)
        if isinstance(ticker, str):
            ticker_of[key] = ticker
        return
    prev = seq_of.get(key)
    if prev is not None and seq != prev + 1:
        notes['gaps'].append({'n': n, 'epoch': epoch, 'sid': sid, 'expected': prev + 1, 'got': seq})
        valid[key] = False
        invalid_why[key] = 'sequence_gap'
        notes['invalidations'].append({'n': n, 'epoch': epoch, 'sid': sid, 'why': 'sequence_gap'})
    elif prev is None and typ == 'orderbook_delta':
        valid[key] = False
        invalid_why[key] = 'delta_before_snapshot'
        notes['invalidations'].append({'n': n, 'epoch': epoch, 'sid': sid, 'why': 'delta_before_snapshot'})
    seq_of[key] = seq


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
    # Summaries only: the gap and invalidation lists can be long.
    for k in ('gaps', 'invalidations'):
        report['notes'][k + '_count'] = len(report['notes'][k])
        report['notes'][k] = report['notes'][k][:20]
    json.dump(report, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write('\n')
    return 0 if report['locally_consistent'] else 1


if __name__ == '__main__':
    sys.exit(main())
