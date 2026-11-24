#!/usr/bin/env python3
"""Where does the depth twin's extra trading come from? A REPORT: compares the backtest legs' per-position files (R3a).

    twin-positions.py WINDOWS_DIR RUN [--split NAME] [--judged D1,D2,...] [--dates]

  WINDOWS_DIR  where drive_lab.sh get put simulated/history-twin/RUN/windows: twin-HOW-pPART/positions-HOW-pPART-DAY.json, written
               by `research/historyTwin.ts --stage backtest --positions` beside twin-windows.py's windows-HOW-pPART-DAY.json
  RUN          the run id, for the messages only
  --split      the split's name; 'confirm' prints one line and reads nothing (the confirm days are blind)
  --judged     the judged days (comma list): only those days' files count. Without it every day found counts
  --dates      print the dates (for a run by hand). By default a day is its number among the judged days, in date order:
               the repository is public and the jobs print counts only, never a date

For each of requote, depth and placebo against real it prints, per judged day and over all days, and per asset: positions, windows
traded (distinct close times), positions per 1,000 entry evaluations of the leg's run, losers (P&L below -$5), and the overlap of the
windows (both / real only / twin only); then the same over all days by hourly strike or 15-minute and by 6-hour UTC close-hour bucket
(a line where neither side has a position is left out).
Counts only: no ticker, no time and no per-window or per-position number.

The rate: x and y divide the positions by each source's OWN run-wide entry evaluations (one cadence-triggered entry check of one ticker,
all assets and strike kinds together, the leg's warm-up day included: the engine cannot split them by day). They differ by source: depth
sees about 30% fewer than real, so the rate gap is larger than the count gap (P2b: 2.1x the positions, about 3x the rate). Per-asset,
per-bucket and per-strike lines use the same all-asset denominator (the engine does not split evaluations by asset), so the asset rates add
up to the all-assets rate and are not an asset's own conversion rate. Each `all assets` line is followed by a line with the two evaluation
counts, so the 30% can be checked from the report alone.

Exit 0 ALWAYS: it is a report, never part of the pass or fail. A run made before this round has no per-position files: it prints
`[twin] no per-position files on Drive for run RUN` and stops. A source with no file, a day with no file or a file it cannot read is
named in a line and left out (the others still print); an unexpected error is one line, not a failed job.

Reads the same tree as twin-windows.py and never writes anywhere. It globs `positions-*` only; twin-windows.py globs `windows-*` only,
so neither sees the other's files.
"""
import glob
import json
import re
import sys

HOWS = ("real", "placebo", "requote", "depth")
TWINS = ("requote", "depth", "placebo")
ASSETS = ("BTC", "ETH", "SOL", "XRP", "other")
BUCKETS = ("00-05", "06-11", "12-17", "18-23")
LOSER_CENTS = -500
VERSION = 1


def usage():
    print("usage: twin-positions.py WINDOWS_DIR RUN [--split NAME] [--judged D1,D2,...] [--dates]", file=sys.stderr)


def parse(argv):
    """(src, run, split, judged list or None, dates flag), or None for wrong arguments."""
    pos, split, judged, dates = [], "", None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dates":
            dates = True
        elif a in ("--split", "--judged") and i + 1 < len(argv):
            i += 1
            if a == "--split":
                split = argv[i]
            else:
                judged = [d for d in argv[i].split(",") if d]
        elif a.startswith("--"):
            return None
        else:
            pos.append(a)
        i += 1
    if len(pos) != 2:
        return None
    return pos[0], pos[1], split, judged, dates


def good_row(r):
    return (
        isinstance(r, dict)
        and isinstance(r.get("asset"), str)
        and isinstance(r.get("closeTs"), (int, float))
        and not isinstance(r.get("closeTs"), bool)
        and isinstance(r.get("pnl"), (int, float))
        and not isinstance(r.get("pnl"), bool)
        and isinstance(r.get("hourly"), bool)
    )


def load(src, how, want):
    """{day: {"rows": [...], "evals": N}} for the judged days (every day found when `want` is None); a file that cannot be read is left out."""
    out = {}
    for f in sorted(glob.glob(f"{src}/twin-{how}-p*/positions-{how}-p*.json")):
        m = re.search(r"(\d{4}-\d\d-\d\d)\.json$", f)
        if not m or (want is not None and m.group(1) not in want):
            continue
        try:
            with open(f) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict) or d.get("version") != VERSION or not isinstance(d.get("positions"), list):
            continue
        tot = d.get("totals")
        ev = tot.get("entryEvaluations") if isinstance(tot, dict) else None
        if not all(good_row(r) for r in d["positions"]) or not isinstance(ev, (int, float)) or isinstance(ev, bool):
            continue
        out[m.group(1)] = {"rows": d["positions"], "evals": ev}
    return out


def bucket(r):
    # the hour the window's contract closed in (a close at midnight belongs to the hour before it, as the day filter does)
    return int(((r["closeTs"] - 1) // 3_600_000) % 24) // 6


def agg(rows, evals):
    n = len(rows)
    return {
        "n": n,
        "w": len({r["closeTs"] for r in rows}),
        "l": sum(1 for r in rows if r["pnl"] < LOSER_CENTS),
        "rate": (n * 1000.0 / evals) if evals > 0 else None,
    }


def rate(x):
    return "n/a" if x is None else f"{x:.2f}"


def thousands(n):
    return f"{int(round(n)):,}"


def compare(label, how, real_rows, real_ev, tw_rows, tw_ev):
    """One line: twin against real over the same rows' sets."""
    a, b = agg(real_rows, real_ev), agg(tw_rows, tw_ev)
    rw, tw = {r["closeTs"] for r in real_rows}, {r["closeTs"] for r in tw_rows}
    return (
        f"[twin] positions {how} vs real, {label}: positions {b['n']} vs {a['n']}, windows {b['w']} vs {a['w']}, "
        f"per 1,000 entry evaluations {rate(b['rate'])} vs {rate(a['rate'])}, losers {b['l']} vs {a['l']}; "
        f"windows both {len(rw & tw)}, real only {len(rw - tw)}, {how} only {len(tw - rw)}"
    )


def evals_line(label, how, real_ev, tw_ev):
    """The two denominators of the rates above: each source's own run-wide entry evaluations (they differ by source)."""
    return (
        f"[twin] positions {how} vs real, {label}: entry evaluations {thousands(tw_ev)} vs {thousands(real_ev)} "
        f"(each source's own run-wide count, warm-up day included; the rates above divide by these)"
    )


def report(src, run, split, judged, dates):
    if split == "confirm":
        print("[twin] per-position report skipped: the confirm split is blind")
        return
    want = set(judged) if judged else None
    got = {how: load(src, how, want) for how in HOWS}
    if not any(got.values()):
        print(f"[twin] no per-position files on Drive for run {run}")
        return
    days = sorted(set(judged) if judged else {d for how in HOWS for d in got[how]})
    name = {d: (d if dates else f"day {i + 1}") for i, d in enumerate(days)}
    print(f"[twin] positions report, run {run}: {len(days)} judged day(s) in date order; the legs' per-position files, counts only")
    for how in HOWS:
        print(f"[twin] positions {how}: {len(got[how])} of {len(days)} judged day(s) have a per-position file")
    real = got["real"]
    if not real:
        print("[twin] positions: no real per-position files, so there is nothing to compare against")
        return
    for how in TWINS:
        tw = got[how]
        if not tw:
            print(f"[twin] positions {how} vs real: no per-position files for {how}, left out")
            continue
        both = [d for d in days if d in real and d in tw]
        if not both:
            print(f"[twin] positions {how} vs real: no judged day has both files, left out")
            continue
        for d in both:
            print(compare(f"{name[d]}, all assets", how, real[d]["rows"], real[d]["evals"], tw[d]["rows"], tw[d]["evals"]))
            print(evals_line(f"{name[d]}, all assets", how, real[d]["evals"], tw[d]["evals"]))
            for a in ASSETS:
                r_rows = [r for r in real[d]["rows"] if r["asset"] == a]
                t_rows = [r for r in tw[d]["rows"] if r["asset"] == a]
                if r_rows or t_rows:
                    print(compare(f"{name[d]}, {a}", how, r_rows, real[d]["evals"], t_rows, tw[d]["evals"]))
        # over the days both have: windows are keyed by close time, so days never collide
        r_all = [r for d in both for r in real[d]["rows"]]
        t_all = [r for d in both for r in tw[d]["rows"]]
        r_ev, t_ev = sum(real[d]["evals"] for d in both), sum(tw[d]["evals"] for d in both)
        print(compare(f"{len(both)} day(s), all assets", how, r_all, r_ev, t_all, t_ev))
        print(evals_line(f"{len(both)} day(s), all assets", how, r_ev, t_ev))
        for a in ASSETS:
            r_rows = [r for r in r_all if r["asset"] == a]
            t_rows = [r for r in t_all if r["asset"] == a]
            if r_rows or t_rows:
                print(compare(f"{len(both)} day(s), {a}", how, r_rows, r_ev, t_rows, t_ev))
        for kind, flag in (("hourly strikes", True), ("15-minute", False)):
            r_rows = [r for r in r_all if r["hourly"] is flag]
            t_rows = [r for r in t_all if r["hourly"] is flag]
            if r_rows or t_rows:
                print(compare(f"{len(both)} day(s), {kind}", how, r_rows, r_ev, t_rows, t_ev))
        for i, b in enumerate(BUCKETS):
            r_rows = [r for r in r_all if bucket(r) == i]
            t_rows = [r for r in t_all if bucket(r) == i]
            if r_rows or t_rows:
                print(compare(f"{len(both)} day(s), UTC close hours {b}", how, r_rows, r_ev, t_rows, t_ev))


def main(argv):
    parsed = parse(argv)
    if parsed is None:
        usage()
        return 0
    try:
        report(*parsed)
    except Exception as e:  # a report must never be what fails a job
        print(f"[twin] positions report stopped: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
