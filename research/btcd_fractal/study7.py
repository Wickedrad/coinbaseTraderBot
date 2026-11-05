#!/usr/bin/env python3
"""Round 7: the oracle trial. Build our own BTC.D-waterfall predictor from the top signals, rapid-fire, and break it.

Blocks of weekly, point-in-time signals (2016-06 to now):
  btcd     BTC.D trend, distance from its 52-week high, the fractal's doorstep flag (round 6 walk-forward track)
  usdtd    USDT.D 13-week change, distance from its 30-week mean, fractal doorstep flag
  total3   TOTAL3 13-week change, vs 30-week mean, TOTAL3 against BTC (13-week), fractal doorstep flag
  ethbtc   ETH/BTC 13-week change, vs 30-week mean, distance from its 52-week high, fractal doorstep flag
  btc      BTC distance from its high, 13-week return, vs 30-week mean
  macro    M2 year on year, DXY 13-week, US 10-year 13-week, SPX vs 30-week mean
  clock    days since the halving, fractal confluence count (round 6)
Targets: the next 13 weeks' BTC.D change in logit (regression), and a 5+ point fall within 13 and within 26 weeks (binary).

1. Oracle ceiling (in sample, whole history): the best single signal per block and the best 3-signal ridge per block.
   This is what a predictor that already knew the answers could extract. Nothing here is tradeable; it is the bar.
2. Rapid-fire build, out of sample: expanding window, refit every 13 weeks from Jan 2019. At each refit, R random-
   restart rounds of greedy add/drop over the signals (at most 2 per block, at most K in all), each round scored on
   the last 3 years of the training window as validation; the best set is fitted by ridge (regression) and logistic
   (binary) and used for the next 13 weeks. Pooled out-of-sample IC, hit rate and AUC, by era.
3. Adversary: the whole build repeated on circularly shifted targets (26+ weeks), N times; and 7 random-walk decoy
   signals offered to the selector, counting how often it picks them.
4. Today: the current model's reading, its signals, and what would move it.
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study4  # noqa: E402

H = 13
ERAS = [("2019-2020", "2019-01-01", "2021-01-01"), ("2021-2022", "2021-01-01", "2023-01-01"), ("2023-2026", "2023-01-01", "2100-01-01")]


def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 20 or np.std(a[m]) == 0 or np.std(b[m]) == 0:
        return 0.0
    return float(pd.Series(a[m]).rank().corr(pd.Series(b[m]).rank()))


def auc(score, y):
    m = np.isfinite(score) & np.isfinite(y)
    s, t = score[m], y[m] > 0.5
    if t.sum() == 0 or (~t).sum() == 0:
        return None
    r = pd.Series(s).rank().values
    return float((r[t].sum() - t.sum() * (t.sum() + 1) / 2) / (t.sum() * (~t).sum()))


def build_features(data, door):
    F, b, _ = study4.features(data)
    W = {}
    for n in ["TOTAL3", "ETHBTC", "USDT.D", "BTCUSD", "ETH.D"]:
        s = study4.load(data, n)
        if s is not None:
            W[n] = study4.weekly(s).reindex(F.index).ffill()
    X = pd.DataFrame(index=F.index)
    blocks = {}

    def add(block, name, s):
        X[name] = s
        blocks.setdefault(block, []).append(name)
    add("btcd", "btcd_13w", F["btcd_13w"])
    add("btcd", "btcd_from52wHigh", F["btcd_from52wHigh"])
    add("usdtd", "usdtd_13w", F["usdtd_13w"])
    u = np.log(W["USDT.D"])
    add("usdtd", "usdtd_vs30w", u - u.rolling(30).mean())
    t3 = np.log(W["TOTAL3"])
    add("total3", "total3_13w", t3.diff(13))
    add("total3", "total3_vs30w", t3 - t3.rolling(30).mean())
    add("total3", "total3_vs_btc_13w", (t3 - np.log(W["BTCUSD"])).diff(13))
    add("ethbtc", "ethbtc_13w", F["ethbtc_13w"])
    add("ethbtc", "ethbtc_vs30w", F["ethbtc_vs30w"])
    e = np.log(W["ETHBTC"])
    add("ethbtc", "ethbtc_from52wHigh", e - e.rolling(52).max())
    add("btc", "btc_dd", F["btc_dd"])
    add("btc", "btc_13w", F["btc_13w"])
    add("btc", "btc_vs30w", F["btc_vs30w"])
    add("macro", "m2_yoy", F["m2_yoy"])
    add("macro", "dxy_13w", F["dxy_13w"])
    add("macro", "us10y_13w", F["us10y_13w"])
    add("macro", "spx_vs30w", F["spx_vs30w"])
    add("clock", "days_since_halving", F["days_since_halving"])
    if door:
        D = pd.DataFrame({pd.Timestamp(k): v for k, v in door.items()}).T.astype(float).reindex(F.index)
        for n, col in [("BTC.D", "btcd"), ("USDT.D", "usdtd"), ("TOTAL3", "total3"), ("ETHBTC", "ethbtc")]:
            if n in D:
                add(col, f"door_{col}", D[n].fillna(0.0))
        add("clock", "confluence_count", D.sum(axis=1).where(D.notna().any(axis=1)).fillna(0.0))
    lb = study4.logit(b)
    Y = pd.DataFrame(index=F.index)
    Y["y13"] = lb.shift(-H) - lb
    fut13 = pd.concat([b.shift(-k) for k in range(1, 14)], axis=1).min(axis=1) - b
    fut26 = pd.concat([b.shift(-k) for k in range(1, 27)], axis=1).min(axis=1) - b
    Y["fall5_13w"] = (fut13 <= -5).astype(float).where(fut13.notna())
    Y["fall5_26w"] = (fut26 <= -5).astype(float).where(fut26.notna())
    X = X[X.index >= pd.Timestamp("2016-06-01")]
    return X, Y.reindex(X.index), b.reindex(X.index), blocks


def zfit(Xtr):
    mu, sd = np.nanmean(Xtr, 0), np.nanstd(Xtr, 0) + 1e-9
    return mu, sd


def z(X, mu, sd):
    return np.clip(np.nan_to_num((X - mu) / sd), -3, 3)


def ridge(Xz, y, lam=1.0):
    A = np.c_[np.ones(len(Xz)), Xz]
    I = np.eye(A.shape[1]) * lam
    I[0, 0] = 0
    return np.linalg.solve(A.T @ A + I, A.T @ y)


def logistic(Xz, y, lam=1.0, it=25):
    A = np.c_[np.ones(len(Xz)), Xz]
    w = np.zeros(A.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (p - y) + lam * np.r_[0, w[1:]]
        Hs = (A * (p * (1 - p))[:, None]).T @ A + lam * np.diag(np.r_[0, np.ones(A.shape[1] - 1)])
        w -= np.linalg.solve(Hs + 1e-6 * np.eye(len(w)), g)
    return w


def predict(A, w):
    return np.c_[np.ones(len(A)), A] @ w


def greedy(Xtr, ytr, Xva, yva, cols, blocks, K, rng, rounds, metric):
    """Random-restart greedy add/drop; score = metric on the validation slice. Returns the best column set."""
    bl = {c: b for b, cs in blocks.items() for c in cs}
    best_set, best_s = [], -9

    def score(cs):
        if not cs:
            return -9
        ii = [cols.index(c) for c in cs]
        mu, sd = zfit(Xtr[:, ii])
        w = ridge(z(Xtr[:, ii], mu, sd), ytr) if metric == "ic" else logistic(z(Xtr[:, ii], mu, sd), ytr)
        p = predict(z(Xva[:, ii], mu, sd), w)
        return spearman(p, yva) if metric == "ic" else ((auc(p, yva) or 0.5) - 0.5)

    for _ in range(rounds):
        cur = list(rng.choice(cols, size=int(rng.integers(1, 4)), replace=False))
        cur = [c for i, c in enumerate(cur) if sum(bl[d] == bl[c] for d in cur[:i]) < 2][:K]
        s = score(cur)
        improved = True
        while improved:
            improved = False
            moves = []
            for c in cols:
                if c not in cur and len(cur) < K and sum(bl[d] == bl[c] for d in cur) < 2:
                    moves.append(cur + [c])
            for c in cur:
                if len(cur) > 1:
                    moves.append([d for d in cur if d != c])
            for m in moves:
                sm = score(m)
                if sm > s + 1e-4:
                    cur, s, improved = m, sm, True
        if s > best_s:
            best_set, best_s = cur, s
    return best_set, best_s


def walk(X, Y, cols, blocks, target, K, rounds, rng, start="2019-01-06", step=13, va_weeks=156):
    metric = "ic" if target == "y13" else "auc"
    idx = X.index
    pred = pd.Series(np.nan, index=idx)
    chosen = []
    Xv = X[cols].values.astype(float)
    yv = Y[target].values.astype(float)
    t = int(np.searchsorted(idx, pd.Timestamp(start)))
    last_w = None
    while t < len(idx):
        # training rows: targets known by t (label needs H or 26 weeks of future)
        lag = H if target == "y13" else (13 if target.endswith("13w") else 26)
        tr = np.arange(0, t - lag)
        tr = tr[np.isfinite(yv[tr]) & np.isfinite(Xv[tr]).all(1)]
        if len(tr) < 60:
            t += step
            continue
        va = tr[tr >= t - lag - va_weeks]
        trn = tr[tr < t - lag - va_weeks] if len(tr) - len(va) >= 40 else tr
        cs, s = greedy(Xv[trn], yv[trn], Xv[va], yv[va], cols, blocks, K, rng, rounds, metric)
        ii = [cols.index(c) for c in cs]
        mu, sd = zfit(Xv[tr][:, ii])
        w = ridge(z(Xv[tr][:, ii], mu, sd), yv[tr]) if metric == "ic" else logistic(z(Xv[tr][:, ii], mu, sd), yv[tr])
        te = np.arange(t, min(t + step, len(idx)))
        pred.iloc[te] = predict(z(Xv[te][:, ii], mu, sd), w)
        chosen.append({"t": str(idx[t].date()), "signals": cs, "valScore": round(s, 3)})
        last_w = (cs, mu, sd, w)
        t += step
    return pred, chosen, last_w


def evaluate(pred, Y, target):
    y = Y[target]
    out = {}
    for name, fr, to in ERAS + [("pooled", "2000-01-01", "2100-01-01")]:
        m = (pred.index >= pd.Timestamp(fr)) & (pred.index < pd.Timestamp(to)) & pred.notna() & y.notna()
        if m.sum() < 20:
            continue
        p, yy = pred[m].values, y[m].values
        if target == "y13":
            mm = np.abs(yy) > 0.02
            out[name] = {"n": int(m.sum()), "ic": round(spearman(p, yy), 3), "hit": round(float(np.mean(np.sign(p[mm]) == np.sign(yy[mm]))), 3) if mm.any() else None}
        else:
            out[name] = {"n": int(m.sum()), "auc": (None if auc(p, yy) is None else round(auc(p, yy), 3)), "base": round(float(yy.mean()), 3)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--round6", default=None, help="results6.json for the fractal doorstep flags")
    ap.add_argument("--rounds", type=int, default=12, help="random restarts per refit")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--nulls", type=int, default=40, help="shifted-target rebuilds")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    door = None
    if a.round6 and os.path.exists(a.round6):
        door = json.load(open(a.round6)).get("doorstep")
    X, Y, b, blocks = build_features(a.data, door)
    cols = list(X.columns)
    res = {"now": str(X.index[-1].date()), "btcd": round(float(b.iloc[-1]), 2), "signals": blocks, "horizonWeeks": H}
    print("signals:", json.dumps(blocks))

    # 1. oracle ceiling, in sample
    ceiling = {}
    Xv, y = X.values.astype(float), Y["y13"].values.astype(float)
    ok = np.isfinite(y) & np.isfinite(Xv).all(1)
    f5 = Y["fall5_26w"].values.astype(float)
    for bname, cs in blocks.items():
        single = {c: round(float(np.nan_to_num(spearman(Xv[ok][:, cols.index(c)], y[ok]))), 3) for c in cs}
        ii = [cols.index(c) for c in cs][:3]
        mu, sd = zfit(Xv[ok][:, ii])
        w = ridge(z(Xv[ok][:, ii], mu, sd), y[ok])
        p = predict(z(Xv[ok][:, ii], mu, sd), w)
        wl = logistic(z(Xv[ok][:, ii], mu, sd), np.nan_to_num(f5[ok]))
        ceiling[bname] = {"single": single, "ridge3_ic": round(spearman(p, y[ok]), 3), "logit3_auc_fall5_26w": round(auc(predict(z(Xv[ok][:, ii], mu, sd), wl), f5[ok]) or 0.5, 3)}
    ii = list(range(len(cols)))
    mu, sd = zfit(Xv[ok])
    p = predict(z(Xv[ok], mu, sd), ridge(z(Xv[ok], mu, sd), y[ok]))
    ceiling["all_ridge_ic"] = round(spearman(p, y[ok]), 3)
    res["oracleCeiling"] = ceiling
    print("oracle ceiling (in sample):", json.dumps(ceiling))

    # 2. the build, out of sample
    build = {}
    for target in ["y13", "fall5_13w", "fall5_26w"]:
        pred, chosen, last = walk(X, Y, cols, blocks, target, a.k, a.rounds, rng)
        ev = evaluate(pred, Y, target)
        picks = {}
        for ch in chosen:
            for c in ch["signals"]:
                picks[c] = picks.get(c, 0) + 1
        build[target] = {"oos": ev, "pickCounts": dict(sorted(picks.items(), key=lambda kv: -kv[1])), "refits": len(chosen), "lastSignals": chosen[-1] if chosen else None}
        if last is not None:
            cs, mu_, sd_, w = last
            xnow = z(X[cs].values[-1:].astype(float), mu_, sd_)
            pn = float(predict(xnow, w)[0])
            contrib = {c: round(float(xnow[0, i] * w[i + 1]), 3) for i, c in enumerate(cs)}
            if target == "y13":
                lb = study4.logit(b.iloc[-1:]).values[0]
                build[target]["today"] = {"predLogit": round(pn, 3), "btcdIn13w": round(float(100 / (1 + np.exp(-(lb + pn)))), 2), "contrib": contrib,
                                          "signalValues": {c: round(float(X[c].iloc[-1]), 4) for c in cs}}
            else:
                build[target]["today"] = {"prob": round(float(1 / (1 + np.exp(-pn))), 3), "contrib": contrib, "signalValues": {c: round(float(X[c].iloc[-1]), 4) for c in cs}}
        build[target]["predSeries"] = [{"t": str(t.date()), "p": round(float(v), 3)} for t, v in pred.dropna().items()][::2]
        print(f"build {target}: oos {json.dumps(ev)} picks {json.dumps(build[target]['pickCounts'])} today {json.dumps(build[target].get('today'))}")
    res["build"] = build

    # 3. adversary: shifted targets through the same build (regression + fall5_26w), decoy signals
    null = {"y13": [], "fall5_26w": []}
    yv = Y.copy()
    for i in range(a.nulls):
        k = int(rng.integers(26, len(Y) - 26))
        Ys = Y.copy()
        for c in Y.columns:
            v = Y[c].values
            Ys[c] = np.roll(v, k)
        for target in null:
            pr, _, _ = walk(X, Ys, cols, blocks, target, a.k, max(3, a.rounds // 3), rng)
            ev = evaluate(pr, Ys, target).get("pooled", {})
            null[target].append(ev.get("ic") if target == "y13" else ev.get("auc"))
    advr = {}
    for target in null:
        v = np.array([x for x in null[target] if x is not None], dtype=float)
        real = build[target]["oos"].get("pooled", {}).get("ic" if target == "y13" else "auc")
        advr[target] = {"n": len(v), "real": real, "nullMedian": round(float(np.median(v)), 3) if len(v) else None,
                        "nullP95": round(float(np.quantile(v, 0.95)), 3) if len(v) else None,
                        "p": round(float((v >= (real if real is not None else 9)).mean()), 3) if len(v) else None}
    # decoys
    Xd = X.copy()
    bd = dict(blocks)
    bd["decoy"] = []
    for i in range(7):
        Xd[f"decoy{i}"] = pd.Series(np.cumsum(rng.standard_normal(len(X))), index=X.index).diff(13)
        bd["decoy"].append(f"decoy{i}")
    pr, chosen, _ = walk(Xd, Y, list(Xd.columns), bd, "y13", a.k, a.rounds, rng)
    nd = sum(1 for ch in chosen for c in ch["signals"] if c.startswith("decoy"))
    nt = sum(len(ch["signals"]) for ch in chosen)
    advr["decoys"] = {"picked": nd, "ofPicks": nt, "share": round(nd / max(nt, 1), 3), "oosWithDecoys": evaluate(pr, Y, "y13").get("pooled")}
    res["adversary"] = advr
    print("adversary:", json.dumps(advr))
    with open(os.path.join(a.out, "results7.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    chart(a.out, b, build)


def chart(out, b, build):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, ax = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    ax[0].plot(b.index, b.values, color="#3b6fb6", lw=1.2)
    ax[0].set_ylabel("BTC.D %")
    s = build["y13"]["predSeries"]
    ax[1].plot([pd.Timestamp(x["t"]) for x in s], [-x["p"] for x in s], color="#4f8a3c", lw=1)
    ax[1].axhline(0, color="#888", lw=0.6)
    ax[1].set_ylabel("predicted 13w\nBTC.D fall (logit)")
    s = build["fall5_26w"]["predSeries"]
    ax[2].plot([pd.Timestamp(x["t"]) for x in s], [1 / (1 + np.exp(-x["p"])) for x in s], color="#8064a2", lw=1)
    ax[2].set_ylabel("P(5+ pt fall\nwithin 26w)")
    ax[2].set_ylim(0, 1)
    ax[0].set_title("Our own predictor, out of sample from Jan 2019 (refit every 13 weeks)")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "9_oracle.png"), dpi=110)


if __name__ == "__main__":
    main()
