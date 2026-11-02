#!/usr/bin/env python3
"""Round 8 shared harness: data, point-in-time features, targets, walk-forward, metrics, nulls.

Every round-8 module (study8_<name>.py) judges itself through this file so the models are comparable.
See ROUND8_BRIEF.md for the rules. Nothing here looks at the future except the target construction, which is
what a target is; the walk-forward keeps labels out of training until their horizon has passed.

Scales: freq "W" (weekly, Sunday close), "3D" or "D" (daily). Horizons are given in weeks and converted to bars
with bars_per_week(freq), so a module written for weekly bars runs unchanged at daily scale.
"""
import json
import os

import numpy as np
import pandas as pd

PCT = ["BTC.D", "USDT.D", "OTHERS.D", "ETH.D"]
CAPS = ["TOTAL", "TOTAL2", "TOTAL3", "BTCUSD", "ETHBTC", "DXY", "SPX", "M2"]
LEVEL = ["US10Y"]
ALL = PCT + CAPS + LEVEL
HALVINGS = [pd.Timestamp(x) for x in ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20", "2028-04-15"]]
ERAS = [("2019-2020", "2019-01-01", "2021-01-01"), ("2021-2022", "2021-01-01", "2023-01-01"), ("2023-2026", "2023-01-01", "2100-01-01")]
BIG_EVENTS = ["2016-11-20", "2017-12-10", "2021-01-03"]  # weekly peak weeks of the three 10+ point waterfalls
M2_LAG_DAYS = 42


# ------------------------------------------------------------------------------------------------- data
def load_daily(data_dir):
    """Daily closes on BTC.D's calendar (every calendar day), forward-filled; M2 lagged 6 weeks for publication."""
    out = {}
    for n in ALL:
        f = os.path.join(data_dir, f"{n}_1d.csv")
        if not os.path.exists(f):
            continue
        d = pd.read_csv(f)
        s = pd.Series(d["c"].values.astype(float), index=pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms")).normalize())
        s = s[~s.index.duplicated()].sort_index()
        if n == "M2":
            s.index = s.index + pd.Timedelta(days=M2_LAG_DAYS)
        out[n] = s
    idx = pd.date_range(out["BTC.D"].index[0], out["BTC.D"].index[-1], freq="D")
    D = pd.DataFrame({n: s.reindex(idx).ffill() for n, s in out.items()}, index=idx)
    return D


def bars_per_week(freq):
    return {"W": 1.0, "W-SUN": 1.0, "3D": 7 / 3, "D": 7.0}[freq]


def panel(daily, freq):
    if freq in ("W", "W-SUN"):
        return daily.resample("W-SUN").last().ffill()
    if freq == "3D":
        return daily.resample("3D").last().ffill()
    return daily.copy()


def bars(weeks, freq):
    return max(1, int(round(weeks * bars_per_week(freq))))


def logit(p):
    p = np.clip(np.asarray(p, float) / 100.0, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def level(P, n):
    """The series in the space where moves are comparable: logit for shares, log for caps and prices."""
    if n in PCT:
        return pd.Series(logit(P[n].values), index=P.index)
    if n in CAPS:
        return np.log(P[n].clip(lower=1e-9))
    return P[n].astype(float)


# ------------------------------------------------------------------------------------------------- features
def features(P, freq, series=("BTC.D", "USDT.D", "TOTAL3", "ETHBTC", "OTHERS.D", "BTCUSD", "DXY", "US10Y", "SPX"),
             rets=(4, 13, 26), ma=30, hi=52, vol=13):
    """Point-in-time features per series, horizons in weeks. Returns (X, blocks)."""
    X = pd.DataFrame(index=P.index)
    blocks = {}

    def add(block, name, s):
        X[name] = s.astype(float)
        blocks.setdefault(block, []).append(name)
    for n in series:
        if n not in P:
            continue
        x = level(P, n)
        key = n.lower().replace(".", "")
        for h in rets:
            add(key, f"{key}_ret{h}w", x.diff(bars(h, freq)))
        add(key, f"{key}_vsma{ma}w", x - x.rolling(bars(ma, freq)).mean())
        add(key, f"{key}_fromhi{hi}w", x - x.rolling(bars(hi, freq)).max())
        add(key, f"{key}_vol{vol}w", x.diff().rolling(bars(vol, freq)).std() * np.sqrt(bars_per_week(freq) * 52))
    if "BTCUSD" in P:
        b = np.log(P["BTCUSD"])
        add("btcusd", "btc_dd_ath", b - b.cummax())
    if "M2" in P:
        add("macro", "m2_yoy", np.log(P["M2"]).diff(bars(52, freq)))
    if "TOTAL3" in P and "BTCUSD" in P:
        add("total3", "total3_vs_btc_ret13w", (np.log(P["TOTAL3"]) - np.log(P["BTCUSD"])).diff(bars(13, freq)))
    add("clock", "days_since_halving", pd.Series([min((t - h).days for h in HALVINGS if h <= t) for t in P.index], index=P.index))
    return X, blocks


# ------------------------------------------------------------------------------------------------- targets
def targets(P, freq, falls=(5.0, 10.0), horizons=(13, 26), tte_max_weeks=104):
    """BTC.D targets. y{h}: logit change over h weeks. fall{k}_{h}w: a k+ point fall from today's level within h
    weeks. maxfall{h}w: the deepest point of the next h weeks relative to today (negative = fall). tte{k}: bars until
    the first k+ point fall (NaN if none within tte_max_weeks, i.e. censored), with cens{k} = 1 when censored."""
    b = P["BTC.D"].astype(float)
    lb = pd.Series(logit(b.values), index=b.index)
    Y = pd.DataFrame(index=P.index)
    for h in horizons:
        hb = bars(h, freq)
        Y[f"y{h}"] = lb.shift(-hb) - lb
        fut = pd.concat([b.shift(-k) for k in range(1, hb + 1)], axis=1)
        mn = fut.min(axis=1).where(fut.notna().all(axis=1))
        Y[f"maxfall{h}w"] = mn - b
        for k in falls:
            Y[f"fall{int(k)}_{h}w"] = ((mn - b) <= -k).astype(float).where(mn.notna())
    hb = bars(tte_max_weeks, freq)
    vals = b.values
    n = len(vals)
    for k in falls:
        tte = np.full(n, np.nan)
        cens = np.full(n, np.nan)
        for i in range(n):
            end = min(n, i + hb + 1)
            if end - i < 2:
                continue
            w = vals[i + 1:end]
            hit = np.where(w <= vals[i] - k)[0]
            if len(hit):
                tte[i], cens[i] = hit[0] + 1, 0.0
            elif end == i + hb + 1:
                tte[i], cens[i] = hb, 1.0
        Y[f"tte{int(k)}"] = tte
        Y[f"cens{int(k)}"] = cens
    return Y


def events(b, min_pts, peak_w=13, within_w=26, freq="W"):
    """Falls of min_pts+ from a local high (peak_w each side) within within_w weeks; non-overlapping. Returns a
    list of dicts (peak, trough, from, to, days)."""
    pw, ww = bars(peak_w, freq), bars(within_w, freq)
    vals = b.values.astype(float)
    out = []
    last_trough = None
    for i in range(len(b)):
        lo, hi = max(0, i - pw), min(len(b), i + pw + 1)
        if vals[i] < vals[lo:hi].max():
            continue
        w = vals[i:i + ww + 1]
        j = int(np.argmin(w))
        if vals[i] - w[j] >= min_pts:
            if last_trough is not None and b.index[i] <= last_trough:
                continue
            out.append({"peak": b.index[i], "trough": b.index[i + j], "from": float(vals[i]), "to": float(w[j]), "days": int((b.index[i + j] - b.index[i]).days)})
            last_trough = b.index[i + j]
    return out


# ------------------------------------------------------------------------------------------------- walk-forward
def walk_forward(X, y, fit, predict, freq="W", start="2019-01-06", refit_weeks=13, label_lag_weeks=26, min_train=60):
    """Expanding-window walk-forward.
      fit(Xtr, ytr) -> model             Xtr, ytr: numpy arrays of the training rows (labels already known at t)
      predict(model, Xhist, te) -> scores for rows te (positions into Xhist). Xhist is the feature matrix up to the END
        of the test block (so a sequential filter can run forward); a prediction for row i must use rows <= i only.
    Returns (pred Series, refits list of dicts {t, nTrain}).
    """
    idx = X.index
    Xv = X.values.astype(float)
    yv = np.asarray(y, float)
    pred = pd.Series(np.nan, index=idx)
    step, lag = bars(refit_weeks, freq), bars(label_lag_weeks, freq)
    t = int(np.searchsorted(idx, pd.Timestamp(start)))
    refits = []
    while t < len(idx):
        tr = np.arange(0, max(0, t - lag))
        tr = tr[np.isfinite(yv[tr]) & np.isfinite(Xv[tr]).all(1)]
        te_end = min(t + step, len(idx))
        if len(tr) >= min_train:
            model = fit(Xv[tr], yv[tr])
            te = np.arange(t, te_end)
            ok = te[np.isfinite(Xv[te]).all(1)]
            if len(ok):
                p = np.asarray(predict(model, Xv[:te_end], ok), float)
                pred.iloc[ok] = p
            refits.append({"t": str(idx[t].date()), "nTrain": int(len(tr))})
        t = te_end
    return pred, refits


# ------------------------------------------------------------------------------------------------- metrics
def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 20 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return 0.0
    return float(pd.Series(a[m]).rank().corr(pd.Series(b[m]).rank()))


def auc(score, y):
    score, y = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(score) & np.isfinite(y)
    s, t = score[m], y[m] > 0.5
    if t.sum() == 0 or (~t).sum() == 0:
        return None
    r = pd.Series(s).rank().values
    return float((r[t].sum() - t.sum() * (t.sum() + 1) / 2) / (t.sum() * (~t).sum()))


def brier(prob, y):
    prob, y = np.asarray(prob, float), np.asarray(y, float)
    m = np.isfinite(prob) & np.isfinite(y)
    if m.sum() == 0:
        return None
    return float(np.mean((np.clip(prob[m], 0, 1) - y[m]) ** 2))


def metrics(pred, y, binary, eras=ERAS, is_prob=False):
    """Per era and pooled. Binary: auc, base rate, brier (if is_prob). Continuous: rank IC, direction hit rate."""
    out = {}
    y = pd.Series(np.asarray(y, float), index=pred.index)
    for name, fr, to in list(eras) + [("pooled", "2000-01-01", "2100-01-01")]:
        m = (pred.index >= pd.Timestamp(fr)) & (pred.index < pd.Timestamp(to)) & pred.notna() & y.notna()
        if m.sum() < 20:
            continue
        p, yy = pred[m].values, y[m].values
        if binary:
            row = {"n": int(m.sum()), "auc": (None if auc(p, yy) is None else round(auc(p, yy), 3)), "base": round(float(yy.mean()), 3)}
            if is_prob:
                row["brier"] = round(brier(p, yy), 4)
                row["brierBase"] = round(float(np.mean((yy.mean() - yy) ** 2)), 4)
        else:
            mm = np.abs(yy) > 0.02
            row = {"n": int(m.sum()), "ic": round(spearman(p, yy), 3), "hit": (round(float(np.mean(np.sign(p[mm]) == np.sign(yy[mm]))), 3) if mm.any() else None)}
        out[name] = row
    return out


def shift_targets(Y, k):
    """Circularly shift every target column together by k bars (keeps each target's own structure, breaks timing)."""
    Ys = Y.copy()
    for c in Y.columns:
        Ys[c] = np.roll(Y[c].values, k)
    return Ys


def shift_null(run, Y, n, rng, freq="W", min_shift_weeks=26):
    """run(Y_shifted) -> headline metric (float or None). Returns the list of null values."""
    lo = bars(min_shift_weeks, freq)
    vals = []
    for _ in range(n):
        k = int(rng.integers(lo, len(Y) - lo))
        v = run(shift_targets(Y, k))
        if v is not None:
            vals.append(float(v))
    return vals


def null_summary(real, null, higher_is_better=True):
    v = np.array(null, float)
    if real is None or len(v) == 0:
        return {"n": len(v), "real": real}
    p = float((v >= real).mean()) if higher_is_better else float((v <= real).mean())
    return {"n": len(v), "real": round(real, 4), "nullMedian": round(float(np.median(v)), 4), "nullP95": round(float(np.quantile(v, 0.95)), 4),
            "nullP05": round(float(np.quantile(v, 0.05)), 4), "p": round(p, 3)}


def thin(series, every=2, digits=4):
    s = series.dropna()
    return [{"t": str(t.date()), "v": round(float(v), digits)} for t, v in s.items()][::every]


def write_results(out_dir, res):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=str)


def zfit(Xtr):
    return np.nanmean(Xtr, 0), np.nanstd(Xtr, 0) + 1e-9


def zapply(X, mu, sd, clip=3.0):
    return np.clip(np.nan_to_num((X - mu) / sd), -clip, clip)


def logistic_fit(Xz, y, lam=1.0, it=25):
    A = np.c_[np.ones(len(Xz)), Xz]
    w = np.zeros(A.shape[1])
    reg = lam * np.diag(np.r_[0, np.ones(A.shape[1] - 1)])
    for _ in range(it):
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (p - y) + reg @ w
        Hs = (A * (p * (1 - p))[:, None]).T @ A + reg
        w -= np.linalg.solve(Hs + 1e-6 * np.eye(len(w)), g)
    return w


def logistic_predict(Xz, w):
    return 1 / (1 + np.exp(-(np.c_[np.ones(len(Xz)), Xz] @ w)))


def ridge_fit(Xz, y, lam=1.0):
    A = np.c_[np.ones(len(Xz)), Xz]
    I = np.eye(A.shape[1]) * lam
    I[0, 0] = 0
    return np.linalg.solve(A.T @ A + I, A.T @ y)


def ridge_predict(Xz, w):
    return np.c_[np.ones(len(Xz)), Xz] @ w


if __name__ == "__main__":
    import sys
    D = load_daily(sys.argv[1] if len(sys.argv) > 1 else "research/btcd_fractal/data")
    for freq in ("W", "D"):
        P = panel(D, freq)
        X, blocks = features(P, freq)
        Y = targets(P, freq)
        ev = events(P["BTC.D"], 5.0, freq=freq)
        print(freq, P.shape, X.shape, Y.shape, "events5:", len(ev), "fall5_26w base (2019+):", round(float(Y.loc["2019":, "fall5_26w"].mean()), 3))
