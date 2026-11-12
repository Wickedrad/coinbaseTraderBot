"""Seatbelt that runs BEFORE any download: the request must start at or after the floor, name only capture artifacts,
carry a read-log id, and contain no DOGE."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone

from . import FLOOR_ISO

ARTIFACT_RE = re.compile(r'^heat-shadow-\d+-\d+(-try[23])?$')
READLOG_RE = re.compile(r'^\d{1,3}[a-z]{1,3}$')
MAX_WINDOW_MS = 48 * 3600 * 1000


class FloorViolation(Exception):
    pass


def iso_ms(s: str) -> int:
    return int(datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp() * 1000)


FLOOR_MS = iso_ms(FLOOR_ISO)


def check_ts(ms: int, what: str = 'timestamp') -> None:
    if ms < FLOOR_MS:
        raise FloorViolation(f'{what} is before the floor {FLOOR_ISO}')


def check_ticker(ticker: str) -> None:
    if 'DOGE' in ticker.upper():
        raise FloorViolation('DOGE is never read in this probe')


def read_run(path: str) -> dict:
    out: dict = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                raise FloorViolation(f'RUN line without key=value: {line[:40]}')
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def check_request(req: dict) -> dict:
    for key in ('artifacts', 'from', 'to', 'readlog', 'run'):
        if not req.get(key):
            raise FloorViolation(f'RUN lacks {key} (the read-log row must be on disk before the push that starts the study)')
    if not READLOG_RE.match(req['readlog']):
        raise FloorViolation('readlog must be the read-log row id, e.g. 10ag')
    t_from, t_to = iso_ms(req['from']), iso_ms(req['to'])
    check_ts(t_from, 'RUN from')
    if t_to <= t_from:
        raise FloorViolation('RUN to must be after from')
    if t_to - t_from > MAX_WINDOW_MS:
        raise FloorViolation('RUN window is longer than 48 hours')
    names = [a for a in req['artifacts'].split(',') if a]
    if not names:
        raise FloorViolation('RUN names no artifacts')
    for n in names:
        if not ARTIFACT_RE.match(n):
            raise FloorViolation(f'not a capture artifact name: {n[:40]}')
    for v in req.values():
        check_ticker(v)
    return {'artifacts': names, 'from_ms': t_from, 'to_ms': t_to, 'readlog': req['readlog'], 'run': req['run']}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        check_request(read_run(argv[0]))
    except (FloorViolation, ValueError, OSError, IndexError) as e:
        print(f'::error::{type(e).__name__}: {e}')
        return 2
    print('guard: request ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
