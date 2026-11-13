"""Reader for the bot's audit log: one JSON object a line, {seq, ts, kind, data}, ts an ISO UTC string.

Only the kinds the trip builder needs are parsed (the rest are skipped on a substring test before any JSON work).
The audit files are per-trade data: this module reads them on a runner or the server and never prints a row.
"""
import calendar
import glob
import gzip
import hashlib
import json
import os
import time

KINDS = ('heat', 'plan', 'fill', 'order_new', 'settlement')
_WANT = tuple('"kind":"%s"' % k for k in KINDS)


def iso_s(ts):
    """An audit time ('2026-11-12T01:40:45.854Z', UTC) in seconds since the epoch, milliseconds kept."""
    ms = int(ts[20:23]) if len(ts) >= 23 and ts[20:23].isdigit() else 0
    return calendar.timegm(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')) + ms / 1000.0


def utc(t, fmt='%m-%d %H:%M:%S'):
    return time.strftime(fmt, time.gmtime(t))


def read_files(paths, since=None, until=None):
    """Records of the wanted kinds from the audit files, sorted by time: [(t, kind, data, seq)].

    since/until are epoch seconds (None = no bound). Unreadable lines are skipped and counted in the second value.
    """
    out, bad, seen = [], 0, set()
    for p in paths:
        with (gzip.open(p, 'rt', encoding='utf-8', errors='replace') if p.endswith('.gz') else open(p, 'r', encoding='utf-8', errors='replace')) as fh:
            for line in fh:
                if not any(w in line[:240] for w in _WANT):
                    continue
                key = hashlib.md5(line.encode('utf-8', 'replace')).digest()
                if key in seen:       # the same day present twice (plain and gzipped, or a copy of a part): counted once
                    continue
                seen.add(key)
                try:
                    r = json.loads(line)
                except ValueError:
                    bad += 1
                    continue
                k = r.get('kind')
                if k not in KINDS:
                    continue
                try:
                    t = iso_s(r.get('ts') or '1970-01-01T00:00:00')
                except (ValueError, TypeError):
                    bad += 1
                    continue
                if (since is not None and t < since) or (until is not None and t > until):
                    continue
                out.append((t, k, r.get('data') or {}, r.get('seq') or 0))
    out.sort(key=lambda x: (x[0], x[3]))
    return out, bad


def files_for_days(data_dir, days):
    """audit-<day>*.jsonl files under data_dir/audit (a day is 'YYYY-MM-DD')."""
    out = []
    for d in days:
        out.extend(sorted(glob.glob(os.path.join(data_dir, 'audit', 'audit-%s*.jsonl' % d))))
        out.extend(sorted(glob.glob(os.path.join(data_dir, 'audit', 'audit-%s*.jsonl.gz' % d))))
    return out
