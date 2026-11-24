#!/usr/bin/env python3
"""Assembles the backtest legs' per-window P&L into the four files the verdict stage reads (history-twin.yml).

Used by BOTH the verdict job (right after its legs finished) and the re-verdict job (a later re-read of the same run's
windows from Drive), so there is ONE copy of this logic and of the completeness guard:

    twin-windows.py WINDOWS_DIR OUT_DIR SPLIT JUDGED LEGS_FILE

  WINDOWS_DIR  where drive_lab.sh get put simulated/history-twin/RUN/windows: twin-HOW-pPART/windows-HOW-pPART-DAY.json
  OUT_DIR      where windows-real.json, windows-placebo.json, windows-requote.json and windows-depth.json are written
  SPLIT        the split's name; 'confirm' prints day-file counts only (a window count per source is check 4's own quantity)
  JUDGED       the judged days, comma list (the verdict job: the build's output; the re-verdict: split.json's judge list)
  LEGS_FILE    gets 'a/b/c/d of N' (the day files found per source: real/placebo/requote/depth, of N judged days)

Exit 0: all four sources hold a readable per-window file for EVERY judged day, and the four files are written.
Exit 3: anything else. NOTHING is written to OUT_DIR then (a verdict stage that finds a windows file counts a missing window as
P&L 0, so a lost twin or real part would read as a simulator defect and a lost placebo part would loosen check 3): only the
lines and LEGS_FILE. Exit 2: wrong arguments.

Only the files of the judged days count, never a file of another day: the windows of a day outside JUDGED are not read into
the four files. Counts only are printed (the repository is public).
"""
import glob
import json
import os
import re
import sys

HOWS = ("real", "placebo", "requote", "depth")


def main(argv):
    if len(argv) != 5:
        print("usage: twin-windows.py WINDOWS_DIR OUT_DIR SPLIT JUDGED LEGS_FILE", file=sys.stderr)
        return 2
    src, out, split, judged, legs = argv
    want = {d for d in judged.split(",") if d}
    got = []
    assembled = {}
    for how in HOWS:
        files = sorted(glob.glob(f"{src}/twin-{how}-p*/windows-{how}-p*.json"))
        days = set()
        w = []
        for f in files:
            m = re.search(r"(\d{4}-\d\d-\d\d)\.json$", f)
            if not m or m.group(1) not in want:
                continue
            try:
                with open(f) as fh:
                    rows = json.load(fh)
            except (OSError, ValueError):
                continue
            if not isinstance(rows, list):
                continue
            days.add(m.group(1))
            w.extend(rows)
        assembled[how] = w
        print(f"[twin] backtest legs {how}: {len(days)} of {len(want)} judged day(s) have a per-window file" + ("" if split == "confirm" else f", {len(w)} window(s)"))
        got.append(len(days))
    with open(legs, "w") as fh:
        fh.write("/".join(str(g) for g in got) + " of " + str(len(want)))
    complete = bool(want) and all(g == len(want) for g in got)
    if complete:
        os.makedirs(out, exist_ok=True)
        for how in HOWS:
            with open(f"{out}/windows-{how}.json", "w") as fh:
                json.dump(assembled[how], fh)
    return 0 if complete else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
