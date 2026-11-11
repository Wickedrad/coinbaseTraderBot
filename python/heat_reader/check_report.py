"""The check job's report (.github/workflows/heat-reader-check.yml): one markdown text from what the job measured.

  python3 -m heat_reader.check_report --dir <folder the job filled> [--oracle SHA] [--note TEXT] [--python VER]
                                      [--venv-mb N] [--run-id ID]

Files it looks for in --dir (a missing one becomes a "not measured" line, never an error):
  once-status.json   the reader's status.json after the single pass (which downloads the window)
  once-time.txt      /usr/bin/time -v of that pass
  loop-status.json   status.json after the 4-minute loop
  loop.log           the loop's own log (one line per pass: "<COIN> <n> fired in <s> s | ... (<s> s)")
  rss.txt            one line per sample of the loop's memory: "<seconds since start> <RSS in kB>"
  calls/loop/        the files the loop wrote: heat_calls-*.jsonl (one line each) and heat_calls.status.json
  calls/once/        the same for the single pass
  parity.json        heat_reader.replay's result, when the parity replay ran

The per-coin table counts the h15 and h60 rows (the main packs). The perp packs' rows (h240 and h1440) get their own
lines: whether the packs were found, and how many rows the loop published at each horizon. Neither fails the job.
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys

KINDS = ('single', 'pair', 'triple')
PERP_H = (240, 1440)           # the perp packs' horizons; every other horizon is a main pack's


def _json(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _text(path: str) -> str:
    try:
        with open(path, errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def time_v(text: str) -> dict:
    """Peak memory (MB) and wall seconds from /usr/bin/time -v."""
    out = {}
    m = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', text)
    if m:
        out['peakMb'] = round(int(m.group(1)) / 1024.0, 1)
    m = re.search(r'Elapsed \(wall clock\) time[^\n]*?:\s*((?:\d+:)?\d+:\d+(?:\.\d+)?)\s*$', text, re.M)
    if m:
        sec = 0.0
        for part in m.group(1).split(':'):
            sec = sec * 60 + float(part)
        out['wallSec'] = round(sec, 1)
    return out


def pass_seconds(log: str) -> list:
    return [float(x) for x in re.findall(r'^heat-reader pass .*\(([0-9.]+) s\)\s*$', log, re.M)]


def coin_seconds(log: str) -> dict:
    """Per coin, the seconds of each pass the coin was read in (fetch and engine), from the loop's log."""
    out = {}
    for line in re.findall(r'^heat-reader pass (.*)$', log, re.M):
        for coin, sec in re.findall(r'(?:^|\| )([A-Z0-9]{2,10}) \d+ fired in ([0-9.]+) s', line):
            out.setdefault(coin, []).append(float(sec))
    return out


def rss_samples(text: str) -> list:
    out = []
    for line in text.splitlines():
        p = line.split()
        if len(p) == 2 and p[1].isdigit() and int(p[1]) > 0:
            out.append(int(p[1]) / 1024.0)
    return out


def fired(lines: list) -> dict:
    """Per coin, over every written file: files, files with the coin ok, and the rows fired: of the main packs by kind
    and key (kinds, keys), of the perp packs by horizon and kind (perp: {h: {kind: n}}) and by key (perpKeys)."""
    out = {}
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        for coin, c in (obj.get('coins') or {}).items():
            o = out.setdefault(coin, {'files': 0, 'ok': 0, 'rows': 0, 'kinds': dict.fromkeys(KINDS, 0), 'keys': {},
                                      'perp': {h: dict.fromkeys(KINDS, 0) for h in PERP_H}, 'perpKeys': {}})
            o['files'] += 1
            o['ok'] += bool(c.get('ok'))
            for row in c.get('calls') or []:
                o['rows'] += 1
                kind = row.get('kind', 'single')
                if row.get('h') in PERP_H:
                    o['perp'][row['h']][kind] = o['perp'][row['h']].get(kind, 0) + 1
                    o['perpKeys'][row.get('key')] = o['perpKeys'].get(row.get('key'), 0) + 1
                    continue
                o['kinds'][kind] = o['kinds'].get(kind, 0) + 1
                o['keys'][row.get('key')] = o['keys'].get(row.get('key'), 0) + 1
    return out


def perp_line(side: dict, fr: dict) -> str:
    """Whether the perp packs were found and used, and how many h240 and h1440 rows the loop published."""
    packs = side.get('packs') or {}
    n = {h: sum(sum(f.get('perp', {}).get(h, {}).values()) for f in fr.values()) for h in PERP_H}
    kinds = {h: ' / '.join(str(sum(f.get('perp', {}).get(h, {}).get(k, 0) for f in fr.values())) for k in KINDS) for h in PERP_H}
    published = (f'the loop published {n[240]} rows at h240 and {n[1440]} at h1440 (single / pair / triple: {kinds[240]} and '
                 f'{kinds[1440]}).')
    if 'perpPacks' not in side:
        return 'Perp packs (h240 and h1440): not reported (no status file, or a reader from before them).'
    if not side.get('perpPacks'):
        return f'Perp packs (h240 and h1440): off (HEAT_PERP_PACKS=false); {published}'
    if 'perp_pack.json' in packs and 'perp_pair_pack.json' in packs:
        return (f'Perp packs (h240 and h1440): found, perp {_short(packs["perp_pack.json"].get("sha256"))}, perp pairs '
                f'{_short(packs["perp_pair_pack.json"].get("sha256"))}; {published}')
    return f'Perp packs (h240 and h1440): **not used**: {side.get("perpProblem") or "not found"}; {published}'


def _lines(d: str, which: str) -> list:
    paths = sorted(glob.glob(os.path.join(d, 'calls', which, 'heat_calls-*.jsonl')))
    out = []
    for p in paths:
        out += _text(p).splitlines()
    return out


def _pct(x) -> str:
    return 'n/a' if x is None else f'{100 * float(x):.2f}%'


def _short(sha) -> str:
    return str(sha)[:12] if sha else 'n/a'


def build(d: str, oracle: str = '', note: str = '', python: str = '', venv_mb: str = '', run_id: str = '') -> str:
    once, loop = _json(os.path.join(d, 'once-status.json')), _json(os.path.join(d, 'loop-status.json'))
    side = _json(os.path.join(d, 'calls', 'loop', 'heat_calls.status.json')) or _json(os.path.join(d, 'calls', 'once', 'heat_calls.status.json')) or {}
    tv = time_v(_text(os.path.join(d, 'once-time.txt')))
    log = _text(os.path.join(d, 'loop.log'))
    secs, per_coin = pass_seconds(log), coin_seconds(log)
    rss = rss_samples(_text(os.path.join(d, 'rss.txt')))
    fr = fired(_lines(d, 'loop'))
    par = _json(os.path.join(d, 'parity.json')) or {}
    last = loop or once or {}
    st = last.get('coins') or {}
    packs = side.get('packs') or {}

    md = [f'Heat reader check{f" (run {run_id})" if run_id else ""}', '']
    md.append(f'Oracle code and packs at `{oracle or "unknown"}`. {note}'.strip())
    md.append(f'Packs (SHA-256): traded {_short((packs.get("traded_pack.json") or {}).get("sha256"))}, pairs '
              f'{_short((packs.get("pair_pack.json") or {}).get("sha256"))}, live_meta {_short((packs.get("live_meta.json") or {}).get("sha256"))}'
              f'{", clock " + _short(packs["clock_pack.json"]["sha256"]) if "clock_pack.json" in packs else ""}; run {side.get("run", "unknown")}; '
              f'HEAT_READER_MAX_RANK {side.get("maxRank", "n/a")}, clock pack {"on" if side.get("clockPack") else "off"}.')
    md.append(f'Python {python or "unknown"}, venv {venv_mb or "not measured"} MB on disk.')
    md.append(perp_line(side, fr))
    if side.get('problem'):
        md.append(f'**The packs could not be used:** {side["problem"]}')
    md += ['', '| coin | read ok (loop files) | minutes loaded | rows wanted: single / pair / triple / clock | rows skipped, by reason | '
               'fired in the loop: single / pair / triple | s per pass: median / max | parity: singles / pair triggers |',
           '|---|---|---|---|---|---|---|---|']
    coins = sorted(set(fr) | set(st) | set((par.get('coins') or {})))
    for c in coins:
        s, f = st.get(c, {}), fr.get(c, {'files': 0, 'ok': 0, 'kinds': dict.fromkeys(KINDS, 0)})
        rows = s.get('rows') or (side.get('coins') or {}).get(c, {}).get('rows') or {}
        w = rows.get('wanted') or {}
        wanted = ' / '.join(str(w.get(k, 'n/a')) for k in ('single', 'pair', 'triple', 'clock')) if w else 'n/a'
        skipped = ', '.join(f'{k} {v}' for k, v in sorted((rows.get('skipped') or {}).items())) or ('none' if rows else 'n/a')
        cs = per_coin.get(c, [])
        sec = f'{round(statistics.median(cs), 3)} / {max(cs)}' if cs else 'n/a'
        p = (par.get('coins') or {}).get(c, {})
        parity = f'{_pct(p.get("share"))} / {_pct(p.get("triggers_share"))}' if 'share' in p else (f'skipped: {p["skipped"]}' if p.get('skipped') else 'n/a')
        md.append(f'| {c} | {f["ok"]} of {f["files"]} | {s.get("cached", "n/a")} | {wanted} | {skipped} | '
                  f'{" / ".join(str(f["kinds"].get(k, 0)) for k in KINDS)} | {sec} | {parity} |')
    if not coins:
        md.append('| none | the reader wrote no file | | | | | | |')
    md.append('')
    for c in coins:
        keys = sorted(fr.get(c, {}).get('keys', {}).items(), key=lambda kv: (-kv[1], str(kv[0])))
        if keys:
            shown = ', '.join(f'`{k}` x{n}' for k, n in keys[:8])
            md.append(f'- {c} fired: {shown}{f" and {len(keys) - 8} more" if len(keys) > 8 else ""}')
        rows = st.get(c, {}).get('rows') or (side.get('coins') or {}).get(c, {}).get('rows') or {}
        pr = rows.get('perp')
        if pr:
            skipped = ', '.join(f'{k} {v}' for k, v in sorted((pr.get('skipped') or {}).items())) or 'none'
            md.append(f'- {c} perp rows wanted (single / pair / triple): {" / ".join(str((pr.get("wanted") or {}).get(k, 0)) for k in KINDS)}; '
                      f'skipped: {skipped}{"; not used: " + pr["problem"] if pr.get("problem") else ""}')
        keys = sorted(fr.get(c, {}).get('perpKeys', {}).items(), key=lambda kv: (-kv[1], str(kv[0])))
        if keys:
            shown = ', '.join(f'`{k}` x{n}' for k, n in keys[:5])
            md.append(f'- {c} fired at h240 or h1440: {shown}{f" and {len(keys) - 5} more" if len(keys) > 5 else ""}')
        why = st.get(c, {}).get('why')
        if why:
            md.append(f'- {c} last file: {why}')
    md.append('')
    if once:
        wall = f'{tv["wallSec"]} s wall' if 'wallSec' in tv else 'wall time not measured'
        md.append(f'- First pass (downloads the window, reads the 60-minute timeframe): {once.get("seconds", "n/a")} s inside the reader, '
                  f'{wall}, peak RSS {tv.get("peakMb", once.get("peakRssMb", "n/a"))} MB.')
    else:
        md.append('- First pass: not measured (the reader left no status file).')
    if secs:
        md.append(f'- Loop: {len(secs)} passes, seconds per pass median {round(statistics.median(secs), 3)}, max {max(secs)} '
                  f'(the first pass of a fresh process reads the 60-minute timeframe of every coin).')
    else:
        md.append('- Loop: no pass was logged.')
    if rss:
        md.append(f'- Loop memory: peak RSS {(loop or {}).get("peakRssMb", round(max(rss), 1))} MB (the kernel\'s high mark), '
                  f'idle RSS {round(statistics.median(rss), 1)} MB (median of {len(rss)} samples, highest sample {round(max(rss), 1)} MB). '
                  f'The unit allows MemoryHigh 180M and MemoryMax 220M.')
    else:
        md.append('- Loop memory: not measured.')
    counts = last.get('counts')
    if counts:
        md.append('- Reader counters: ' + ', '.join(f'{k} {v}' for k, v in counts.items()) + '.')
    md.append('')
    if par.get('coins'):
        md.append(f'Parity with the full engine (Dec 29 to 31, 2025, window {par.get("window_bars")} bars), through the reader\'s own code path: '
                  f'**{_pct(par.get("share"))}** of published single keys agree ({par.get("keys_both")} both, {par.get("engine_only")} engine only, '
                  f'{par.get("reader_only")} reader only); pair triggers {_pct(par.get("triggers_share"))} ({par.get("triggers_both")} both, '
                  f'{par.get("triggers_engine_only")} engine only, {par.get("triggers_reader_only")} reader only). The fixture holds events only, '
                  f'so a pair\'s conditions are not compared.')
        md += ['', '| coin | minutes replayed | minutes loaded | singles agree | both | engine only | reader only | triggers agree | '
                   'pairs and triples fired | not ok minutes | s |', '|---|---|---|---|---|---|---|---|---|---|---|']
        for c, r in sorted(par['coins'].items()):
            if 'share' not in r:
                md.append(f'| {c} | skipped: {r.get("skipped")} | | | | | | | | | |')
                continue
            fd = r.get('fired') or {}
            md.append(f'| {c} | {r["minutes"]} | {r.get("minutes_loaded", "n/a")} | {_pct(r["share"])} | {r["keys_both"]} | {r["engine_only"]} | '
                      f'{r["reader_only"]} | {_pct(r.get("triggers_share"))} | {fd.get("pair", 0) + fd.get("triple", 0)} | '
                      f'{r["not_ok_minutes"] + r["missing_minutes"]} | {r["seconds"]} |')
            if r.get('keys_that_differ'):
                md.append(f'| | differ most: {", ".join(f"`{k}` x{n}" for k, n in r["keys_that_differ"][:5])} | | | | | | | | | |')
    else:
        md.append('Parity replay: not run (the oracle commit holds no research/oracle_heat/parity fixtures, or the replay failed).')
    return '\n'.join(md) + '\n'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python3 -m heat_reader.check_report')
    ap.add_argument('--dir', required=True)
    for name in ('oracle', 'note', 'python', 'venv-mb', 'run-id'):
        ap.add_argument(f'--{name}', default='')
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    sys.stdout.write(build(a.dir, a.oracle, a.note, a.python, a.venv_mb, a.run_id))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
