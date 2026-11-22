#!/usr/bin/env python3
"""Round 17 charts: the time map (anchors against the automatic alignment) and the speed of each leg."""
import json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import common as c, hmm, m2_align as m2

PAR, CHI = "#2a78d6", "#eb6834"                       # parent, child (validated pair, as in round 16)
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.facecolor": SURF, "figure.facecolor": SURF, "savefig.facecolor": SURF, "axes.spines.top": False, "axes.spines.right": False})


def style(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, lw=0.6); ax.set_axisbelow(True); ax.tick_params(length=0)


def fig_time_map():
    par, ch = m2.series()
    mod = hmm.Model(len(par)); end_min = par.index.get_loc(c.P[-1]) - m2.TOL
    r = hmm.fit_b(ch.values, par.values, 2.3, mod, end_min=end_min)
    F = hmm.first_passage(r["W"]); days = par.index; wk = ch.index
    # for each child week: the parent day the map has reached (median and 80% band of the position)
    cum = np.cumsum(r["W"], axis=1)
    pos = lambda q: days[np.minimum((cum < q).sum(axis=1), len(days) - 1)]
    fig, axs = plt.subplots(2, 1, figsize=(10, 9.2), sharex=True, gridspec_kw={"hspace": 0.12, "height_ratios": [1.25, 1]})
    ax = axs[0]; style(ax)
    ax.fill_between(wk, pos(0.1), pos(0.9), color=CHI, alpha=0.22, lw=0, label="automatic alignment, 80% band")
    ax.plot(wk, pos(0.5), color=CHI, lw=2, label="automatic alignment (no anchors given), middle")
    Ct, Cj = c.child_anchors("today", 1), c.child_anchors("Jun 22 2025 high", 1)
    ax.plot(Ct, c.P, color=INK, lw=1.2, marker="o", ms=6, mfc=SURF, mew=1.4, label="your anchors (top = today)")
    ax.plot([Cj[-2], Cj[-1]], [c.P[-2], c.P[-1]], color=INK, lw=1.0, ls=(0, (4, 3)), marker="o", ms=6, mfc=SURF, mew=1.4, label="the same with the top at the Jun 22 2025 high")
    rt = json.load(open(c.HERE / "m3_forward.json"))["rows"]
    ax.plot(pd.DatetimeIndex([x["week"] for x in rt]), pd.DatetimeIndex([x["amplitude2.3"]["parentDay"][1] for x in rt]), ls="none", marker="D", ms=4.5, mfc=SURF, mec=INK2, mew=1.1,
            label="the same model read in real time (refit each quarter on data to that week)")
    paces = [(Ct[i + 1] - Ct[i]).days / (c.P[i + 1] - c.P[i]).days for i in range(5)]
    lab = ["1.0", "5.1", "22", "20.5", "34 (22 to the\nJune 2025 high)"]
    off = [(-6, 16), (0, -34), (-30, 6), (-40, 10), (-64, 22)]
    for i in range(5):
        mx = Ct[i] + (Ct[i + 1] - Ct[i]) / 2; my = c.P[i] + (c.P[i + 1] - c.P[i]) / 2
        ax.annotate(lab[i], (mx, my), xytext=off[i], textcoords="offset points", color=INK, fontsize=9, fontweight="bold", ha="center")
    ax.axhline(c.P[-1], color=MUTED, lw=0.8, ls=(0, (2, 3)))
    ax.annotate("the parent's top, Feb 26 2017", (wk[4], c.P[-1]), xytext=(0, 5), textcoords="offset points", color=INK2, fontsize=8)
    ax.yaxis.set_major_formatter(mdates.DateFormatter("%b %Y")); ax.set_ylabel("where the child is on the parent (2016-17)")
    ax.set_ylim(c.P[0] - pd.Timedelta(days=8), par.index[-1])
    ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    ax.set_title("The time map: each child week placed on the parent.  Bold numbers = pace on your anchors (child weeks per parent week)", loc="left", fontsize=10.5, color=INK)
    ax = axs[1]; style(ax)
    d = c.btcd(); w = c.weekly(d)[pd.Timestamp("2017-12-10"):]
    ax.plot(w.index, w.values, color=CHI, lw=1.6)
    for i, t in enumerate(Ct[1:-1]):
        ax.axvline(t, color=MUTED, lw=0.8, ls=(0, (2, 3)))
    names = ["waterfall", "rise", "mid-structure fall", "sideways\nconsolidation", "rise to the top"]
    for i in range(5):
        mx = Ct[i] + (Ct[i + 1] - Ct[i]) / 2
        ax.annotate(names[i] if i else "", (mx, 75.5), ha="center", va="top", color=INK2, fontsize=8.5)
    ax.annotate("waterfall", (Ct[0], 75.5), xytext=(4, 0), textcoords="offset points", ha="left", va="top", color=INK2, fontsize=8.5)
    ax.set_ylim(33, 77); ax.set_ylabel("BTC dominance, % (weekly closes)")
    ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.text(0.125, 0.045, "Automatic alignment: hidden Markov model at amplitude 2.3 (the size ratio of your rise and fall legs), start pinned, end on the parent's top.\n"
             "It is sharp only where the parent moves fast (the falls). Inside flat parts the band is wide or the fit slides: there the pace is not pinned down by the data.\n"
             "Read in real time (diamonds), the model first put the child on the parent's top in July 2023, with BTC.D near 50%, and has kept it there ever since.\n"
             f"TradingView BTC.D, recorded days through {c.THROUGH.date()}.", color=MUTED, fontsize=8, va="top")
    fig.savefig(c.HERE / "time_map.png", dpi=170, bbox_inches="tight"); plt.close(fig)


def fig_leg_speeds():
    L = json.load(open(c.HERE / "m6_leg_speeds.json"))
    legs = {r["leg"]: r for r in L["legs"]}
    # Steven, Nov 22 2026: only two waterfalls in 2016-18 (the mid-July 2016 waterfall and the 2017-18 waterfall).
    groups = [("the two waterfalls", [("July 2016 waterfall", "July 2016 waterfall (parent)"), ("2017-18 waterfall", "2017-18 waterfall (child)")]),
              ("after the parent's top (not counted as a waterfall)", [("2017 fall after the parent's top (not counted as a waterfall)", "2017 fall after the top, Feb to May (parent)")]),
              ("other falls", [("2021 fall, sharp part from the Jan 3 2021 high", "2021 fall, Jan to May (child)"), ("Jun-Sep 2025 drop (inside the top)", "Jun to Sep 2025 drop (child, inside the top)"),
                               (None, "last 4 weeks to Nov 21 2026 (child)")]),
              ("rises", [("rise after the July 2016 waterfall", "rise after the July 2016 waterfall (parent)"), ("rise to the top", "rise to the top, Jan to Feb 2017 (parent)"),
                         ("rise after the 2017-18 waterfall", "rise 2018 to 2019 (child)"), ("rise to the Jun 22 2025 high", "rise 2023 to Jun 2025 (child)")])]
    fig, ax = plt.subplots(figsize=(10, 6.1)); style(ax, "x")
    yy, ticks, labels = 0.0, [], []
    for title, items in groups:
        ax.annotate(title, (0, yy), xytext=(2, 0), textcoords="offset points", color=MUTED, fontsize=8.5, fontweight="bold", va="center")
        yy -= 0.72
        for key, label in items:
            if key is None:
                v, era, wks = abs(L["last4w"]) / 4, "child", 4
            else:
                r = legs[key]; v, era, wks = abs(r["speedLogitPerWeek"]), r["era"], r["weeks"]
            ax.barh(yy, v, height=0.62, color=PAR if era == "parent" else CHI)
            note = f"{v:.3f}  ({wks:.0f} weeks)" if title == "rises" else f"{v:.3f}  ({np.expm1(-v) * 100:+.0f}% a week for BTC against the rest, {wks:.0f} weeks)"
            ax.annotate(note, (v, yy), xytext=(5, 0), textcoords="offset points", va="center", color=INK2, fontsize=8.5)
            ticks.append(yy); labels.append(label); yy -= 1.0
        yy -= 0.35
    ax.set_yticks(ticks); ax.set_yticklabels(labels, color=INK, fontsize=8.8); ax.set_ylim(yy + 0.6, 0.55)
    ax.set_xlim(0, 0.44); ax.set_xlabel("speed of the leg: change in log(BTC value / value of everything else) per week, size only")
    ax.plot([], [], color=PAR, lw=6, label="parent (2016-17)"); ax.plot([], [], color=CHI, lw=6, label="child (2017-now)")
    ax.legend(loc="lower right", frameon=False, fontsize=8.5)
    ax.set_title("The two waterfalls, both in 2016-18, ran at one speed for five weeks each. No leg since January 2018 has come close", loc="left", fontsize=10.5, color=INK)
    fig.text(0.125, -0.02, "Both waterfalls, and the 2017 fall after the parent's top, happened in the volatile market of 2016-18. A waterfall in today's much quieter\n"
             "market has not been observed, so the old speed is a record of the past, not a template for the next one.\n"
             "The 2017 fall after the top includes three index-step days; with them taken out it ran at 0.168 a week.", color=MUTED, fontsize=8, va="top")
    fig.savefig(c.HERE / "leg_speeds.png", dpi=170, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    fig_time_map(); fig_leg_speeds()
