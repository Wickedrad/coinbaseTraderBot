"""The check job's report (.github/workflows/heat-reader-check.yml): one markdown text from what the job measured.

  python3 -m heat_reader.check_report --dir <folder the job filled> [--oracle SHA] [--note TEXT] [--python VER]
                                      [--venv-mb N] [--meta-source TEXT] [--pack TEXT] [--run-id ID]

Files it looks for in --dir (a missing one becomes a "not measured" line, never an error):
  once-status.json   the reader's status.json after the single pass
  once-time.txt      /usr/bin/time -v of that pass
  loop-status.json   status.json after the 4-minute loop
  loop.log           the loop's own log (one line per pass, ending in "(<seconds> s)")
  rss.txt            one line per sample of the loop's memory: "<seconds since start> <RSS in kB>"
  calls/heat_calls-*.jsonl   every file the reader wrote (one line each)
  parity.json        heat_reader.replay's result, when the parity replay ran
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys


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


def rss_samples(text: str) -> list:
    out = []
    for line in text.splitlines():
        p = line.split()
        if len(p) == 2 and p[1].isdigit() and int(p[1]) > 0:
            out.append(int(p[1]) / 1024.0)
    return out


def fired(lines: list) -> dict:
    """Per coin, over every written file: files, files with the coin ok, rows fired, the keys fired."""
    out = {}
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        for coin, c in (obj.get('coins') or {}).items():
            o = out.setdefault(coin, {'files': 0, 'ok': 0, 'rows': 0, 'keys': {}})
            o['files'] += 1
            o['ok'] += bool(c.get('ok'))
            for row in c.get('calls') or []:
                o['rows'] += 1
                o['keys'][row.get('key')] = o['keys'].get(row.get('key'), 0) + 1
    return out


def build(d: str, oracle: str = '', note: str = '', python: str = '', venv_mb: str = '', meta_source: str = '', pack: str = '', run_id: str = '') -> str:
    once, loop = _json(os.path.join(d, 'once-status.json')), _json(os.path.join(d, 'loop-status.json'))
    tv = time_v(_text(os.path.join(d, 'once-time.txt')))
    secs = pass_seconds(_text(os.path.join(d, 'loop.log')))
    rss = rss_samples(_text(os.path.join(d, 'rss.txt')))
    lines = []
    for p in sorted(glob.glob(os.path.join(d, 'calls', 'heat_calls-*.jsonl'))):
        lines += _text(p).splitlines()
    fr = fired(lines)
    last = loop or once or {}
    md = [f'Heat reader check{f" (run {run_id})" if run_id else ""}', '']
    md.append(f'Oracle code at `{oracle or "unknown"}`. {note}'.strip())
    md.append(f'Pack: {pack or "unknown"}. Metas: {meta_source or "unknown"}. Python {python or "unknown"}, venv {venv_mb or "not measured"} MB on disk.')
    md += ['', '| coin | read ok | minutes loaded | bars in the grid | rows fired | fetch s | engine s |', '|---|---|---|---|---|---|---|']
    coins = sorted(set(fr) | set((last.get('coins') or {})))
    for c in coins:
        st, f = (last.get('coins') or {}).get(c, {}), fr.get(c, {'files': 0, 'ok': 0, 'rows': 0, 'keys': {}})
        md.append(f'| {c} | {f["ok"]} of {f["files"]} files | {st.get("cached", "n/a")} | {st.get("minutes", "n/a")} | {f["rows"]} | '
                  f'{st.get("fetchSec", "n/a")} | {st.get("engineSec", "n/a")} |')
    if not coins:
        md.append('| none | the reader wrote no file | | | | | |')
    md.append('')
    for c in coins:
        keys = sorted(fr.get(c, {}).get('keys', {}).items(), key=lambda kv: (-kv[1], str(kv[0])))
        shown = ', '.join(f'`{k}` x{n}' for k, n in keys[:12])
        md.append(f'- {c} keys fired: {shown or "none"}{f" and {len(keys) - 12} more" if len(keys) > 12 else ""}')
        why = (last.get('coins') or {}).get(c, {}).get('why')
        if why:
            md.append(f'- {c} last file not ok: {why}')
    md.append('')
    if once:
        md.append(f'- First pass (with the download of the window): {once.get("seconds", "n/a")} s inside the reader, '
                  f'{tv.get("wallSec", "n/a")} s wall, peak RSS {tv.get("peakMb", once.get("peakRssMb", "n/a"))} MB.')
    else:
        md.append('- First pass: not measured (the reader left no status file).')
    if secs:
        md.append(f'- Loop: {len(secs)} passes, seconds per pass median {round(statistics.median(secs), 3)}, max {max(secs)}.')
    else:
        md.append('- Loop: no pass was logged.')
    if rss:
        md.append(f'- Loop memory: peak RSS {(loop or {}).get("peakRssMb", round(max(rss), 1))} MB (the kernel\'s high mark), '
                  f'idle RSS {round(statistics.median(rss), 1)} MB (median of {len(rss)} samples, highest sample {round(max(rss), 1)} MB). '
                  f'The unit allows MemoryHigh 180M and MemoryMax 220M.')
    else:
        md.append('- Loop memory: not measured.')
    counts = (loop or once or {}).get('counts')
    if counts:
        md.append('- Reader counters: ' + ', '.join(f'{k} {v}' for k, v in counts.items()) + '.')
    par = _json(os.path.join(d, 'parity.json'))
    md.append('')
    if par:
        md.append(f'Parity with the full engine (Dec 29 to 31, 2025, window {par.get("window_bars")} bars): '
                  f'**{_pct(par.get("share"))}** of pack keys agree ({par.get("keys_both")} both, {par.get("engine_only")} engine only, '
                  f'{par.get("reader_only")} reader only).')
        md += ['', '| coin | minutes replayed | agree | both | engine only | reader only | not ok minutes | rows left out | s |', '|---|---|---|---|---|---|---|---|---|']
        for c, r in sorted((par.get('coins') or {}).items()):
            if 'share' not in r:
                md.append(f'| {c} | skipped: {r.get("skipped")} | | | | | | | |')
                continue
            md.append(f'| {c} | {r["minutes"]} | {_pct(r["share"])} | {r["keys_both"]} | {r["engine_only"]} | {r["reader_only"]} | '
                      f'{r["not_ok_minutes"] + r["missing_minutes"]} | {r["rows_left_out"]} | {r["seconds"]} |')
            if r.get('keys_that_differ'):
                md.append(f'| | differ most: {", ".join(f"`{k}` x{n}" for k, n in r["keys_that_differ"][:5])} | | | | | | | |')
    else:
        md.append('Parity replay: not run (the oracle commit holds no research/oracle_heat/parity fixtures, or the replay failed).')
    return '\n'.join(md) + '\n'


def _pct(x) -> str:
    return 'n/a' if x is None else f'{100 * float(x):.2f}%'


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python3 -m heat_reader.check_report')
    ap.add_argument('--dir', required=True)
    for name in ('oracle', 'note', 'python', 'venv-mb', 'meta-source', 'pack', 'run-id'):
        ap.add_argument(f'--{name}', default='')
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    sys.stdout.write(build(a.dir, a.oracle, a.note, a.python, a.venv_mb, a.meta_source, a.pack, a.run_id))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
