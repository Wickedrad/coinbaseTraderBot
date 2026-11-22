#!/usr/bin/env python3
"""Round 17 shared pieces: data, the settled anchors (Reading 1), scales.

Recorded days only: every series is cut at THROUGH, the last complete daily bar when the round was run.
BTC.D is read on the logit scale, log(BTC value / value of everything else), the natural scale for a share.
"""
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
THROUGH = pd.Timestamp("2026-11-21")
STEP_DAYS = pd.to_datetime(["2016-10-09", "2016-12-16", "2017-04-02", "2017-05-07", "2017-05-09", "2017-07-14"])
# Reading 1 (Steven's Nov 2 note, settled Nov 21 2026 10:44 PM EST / Nov 22 03:44 UTC), weekly closes
P = pd.to_datetime(["2016-06-19", "2016-07-24", "2016-11-20", "2016-12-18", "2017-01-15", "2017-02-26"])
C_CONS_END = pd.to_datetime(["2022-11-13", "2022-12-11", "2023-01-08"])   # end of the 2021-22 sideways consolidation: range and midpoint
C_TOPS = {"Jun 22 2025 high": pd.Timestamp("2025-06-22"), "today": pd.Timestamp("2026-11-22")}  # week ending Nov 22 holds the Nov 21 close
SEG = ["waterfall", "rise", "mid-structure fall", "sideways consolidation", "rise to the top"]


def child_anchors(top="today", cons=1):
    return pd.to_datetime(["2017-12-10", "2018-01-14", "2019-09-08", "2021-05-16"]).append(pd.DatetimeIndex([C_CONS_END[cons], C_TOPS[top]]))


def load(n, col="c"):
    d = pd.read_csv(DATA / f"{n}_1d.csv")
    d.index = pd.to_datetime(d.ts, unit="ms")
    s = d[col].astype(float)
    s = s[~s.index.duplicated()].sort_index()
    return s[:THROUGH]


def weekly(s):
    """Weekly closes, weeks ending Sunday (the label is the Sunday)."""
    return s.resample("W-SUN").last().dropna()


def logit(pct):
    p = np.asarray(pct, float) / 100.0
    return np.log(p / (1 - p))


def inv_logit(x):
    return 100.0 / (1.0 + np.exp(-np.asarray(x, float)))


def btcd():
    return load("BTC.D")


def lbtcd(steps_out=False):
    """Daily logit BTC.D; with steps_out the TradingView index-step days are flattened (their change set to zero)."""
    s = pd.Series(logit(btcd().values), index=btcd().index)
    if steps_out:
        r = s.diff()
        r[r.index.isin(STEP_DAYS)] = 0.0
        s = s.iloc[0] + r.fillna(0).cumsum()
    return s
