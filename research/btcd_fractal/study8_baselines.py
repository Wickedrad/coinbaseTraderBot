#!/usr/bin/env python3
"""Round 8 baselines through the shared harness: base rates, the readiness rule, and a fixed-signal logistic/ridge
(round 7's most-picked signals, no selection). Every other round-8 module is judged against this file's numbers.

  python3 research/btcd_fractal/study8_baselines.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/baselines
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study8_common as C  # noqa: E402

SIGNALS = ["usdtd_vsma30w", "ethbtc_fromhi52w", "btc_dd_ath", "btcusd_ret13w", "m2_yoy"]


def run_fixed(X, Y, target, freq, binary, cols=None):
    cols = cols or SIGNALS

    def fit(Xtr, ytr):
        mu, sd = C.zfit(Xtr)
        w = C.logistic_fit(C.zapply(Xtr, mu, sd), ytr) if binary else C.ridge_fit(C.zapply(Xtr, mu, sd), ytr)
        return (mu, sd, w)

    def predict(model, Xh, te):
        mu, sd, w = model
        Z = C.zapply(Xh[te], mu, sd)
        return C.logistic_predict(Z, w) if binary else C.ridge_predict(Z, w)
    lag = 26 if "26w" in target else 13
    pred, refits = C.walk_forward(X[cols], Y[target], fit, predict, freq=freq, label_lag_weeks=lag)
    return pred, refits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=200)
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    if a.fast:
        a.nulls = 20
    rng = np.random.default_rng(8)
    D = C.load_daily(a.data)
    res = {"notes": []}
    for freq in ("W", "D"):
        P = C.panel(D, freq)
        X, blocks = C.features(P, freq)
        Y = C.targets(P, freq)
        X = X[X.index >= pd.Timestamp("2016-06-01")]
        Y, P = Y.reindex(X.index), P.reindex(X.index)
        r = {"nRows": int(len(X)), "base": {}}
        post = X.index >= pd.Timestamp("2019-01-01")
        for tg in ("fall5_13w", "fall5_26w", "fall10_26w"):
            r["base"][tg] = round(float(Y.loc[post, tg].mean()), 3)
        # readiness rule: BTC within 5% of its all-time high and M2 growing
        rule = ((X["btc_dd_ath"] >= np.log(0.95)) & (X["m2_yoy"] > 0)).astype(float)
        r["readinessRule"] = {}
        for tg in ("fall5_26w", "fall10_26w"):
            m = post & Y[tg].notna()
            on = rule[m] > 0
            r["readinessRule"][tg] = {"weeksOn": int(on.sum()), "precisionOn": round(float(Y.loc[m & (rule > 0), tg].mean()), 3) if on.sum() else None,
                                      "precisionOff": round(float(Y.loc[m & (rule == 0), tg].mean()), 3), "auc": (None if C.auc(rule[m].values, Y.loc[m, tg].values) is None else round(C.auc(rule[m].values, Y.loc[m, tg].values), 3))}
        r["readinessRule"]["onNow"] = bool(rule.iloc[-1] > 0)
        r["readinessRule"]["firedBeforeBigEvents"] = {e: bool(rule.get(pd.Timestamp(e), 0) > 0) for e in C.BIG_EVENTS} if freq == "W" else None
        # fixed-signal models: the five most-picked round-7 signals, M2 alone, and every feature (no selection)
        r["fixed"] = {}
        for setname, cols in (("fixed5", SIGNALS), ("m2only", ["m2_yoy"]), ("all", list(X.columns))):
            for tg, binary in (("fall5_26w", True), ("fall10_26w", True), ("y13", False)):
                pred, refits = run_fixed(X, Y, tg, freq, binary, cols)
                met = C.metrics(pred, Y[tg], binary, is_prob=binary)
                head = "auc" if binary else "ic"
                real = met.get("pooled", {}).get(head)
                nn = (a.nulls if setname != "all" else max(10, a.nulls // 5)) if freq == "W" else max(10, a.nulls // 10)

                def one(Ys, tg=tg, binary=binary, cols=cols):
                    p, _ = run_fixed(X, Ys, tg, freq, binary, cols)
                    return C.metrics(p, Ys[tg], binary).get("pooled", {}).get(head)
                null = C.shift_null(one, Y, nn, rng, freq=freq)
                r["fixed"][f"{setname}:{tg}"] = {"oos": met, "null": C.null_summary(real, null), "today": round(float(pred.iloc[-1]), 4) if np.isfinite(pred.iloc[-1]) else None,
                                                 "refits": len(refits), "series": C.thin(pred, every=(2 if freq == "W" else 14)) if setname != "all" else None}
                print(f"{freq} {setname} {tg}: pooled {met.get('pooled')} null {r['fixed'][f'{setname}:{tg}']['null']} today {r['fixed'][f'{setname}:{tg}']['today']}")
        # single-signal direction ICs (to show which signals invert out of sample)
        r["singles_y13"] = {}
        for c in X.columns:
            pred, _ = run_fixed(X, Y, "y13", freq, False, [c])
            r["singles_y13"][c] = C.metrics(pred, Y["y13"], False).get("pooled", {}).get("ic")
        print(f"{freq} base {r['base']} readiness {r['readinessRule']}")
        res[freq] = r
    res["signals"] = SIGNALS
    res["notes"].append("Readiness rule = BTC within 5% of its all-time high AND M2 y/y > 0 (6-week publication lag).")
    C.write_results(a.out, res)


if __name__ == "__main__":
    main()
