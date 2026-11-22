#!/usr/bin/env python3
"""Round 16 charts: the child's charts drawn on the parent's clock (structure_map.py's time map)."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import structure_map as m

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
PAR, CHI = "#2a78d6", "#eb6834"                       # parent, child (validated pair)
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.facecolor": SURF, "figure.facecolor": SURF, "savefig.facecolor": SURF, "axes.spines.top": False, "axes.spines.right": False})
S = m.all_series()
TODAY = S["BTC"].index[-1]
num = mdates.date2num


def style(ax):
    ax.grid(axis="y", color=GRID, lw=0.6); ax.set_axisbelow(True); ax.tick_params(length=0)


def child_on_parent_clock(name, p_from, p_to):
    """the child's daily closes placed at their parent-clock date (inverse of the time map)"""
    c0, c1 = m.to_child([p_from])[0], min(m.to_child([p_to])[0], TODAY)
    s = S[name].loc[c0:c1].dropna()
    x = m.day(s.index); xp, fp = m.day(m.C), m.day(m.P)
    y = np.interp(x, xp, fp)
    pace = (xp[-1] - xp[-2]) / (fp[-1] - fp[-2])
    y = np.where(x > xp[-1], fp[-1] + (x - xp[-1]) / pace, y)
    t = pd.Timestamp("2010-01-01") + pd.to_timedelta(y, unit="D")
    return pd.Series(s.values, index=t)


def fig_through_top():
    p0, p1 = m.P[0], pd.Timestamp("2017-04-02")
    rows = [("BTC.D", "BTC dominance, %", False), ("BTC", "BTC price, $ (log)", True), ("ETH/BTC", "ETH/BTC (log)", True)]
    fig, axs = plt.subplots(6, 1, figsize=(10, 12.6), sharex=True, gridspec_kw={"hspace": 0.3})
    today_p = m.to_parent([TODAY])[0]
    for r, (name, lab, log) in enumerate(rows):
        for k, (era, col) in enumerate((("parent", PAR), ("child", CHI))):
            ax = axs[2 * r + k]; style(ax)
            s = S[name].loc[p0:p1].dropna() if era == "parent" else child_on_parent_clock(name, p0, p1)
            ax.plot(s.index, s.values, color=col, lw=1.6, solid_capstyle="round")
            if log:
                ax.set_yscale("log"); ax.yaxis.set_major_locator(matplotlib.ticker.LogLocator(base=10, subs=(1, 2, 5)))
                ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 10 else f"{v:.3g}"))
                ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
            who = "Parent, 2016-17" if era == "parent" else "Child, 2017-26, on the parent's clock"
            ax.set_title(f"{lab}  |  {who}", loc="left", color=INK, fontsize=9, fontweight="bold", pad=3)
            for a in m.P:
                ax.axvline(a, color=MUTED, lw=0.7, ls=(0, (2, 3)))
            ax.axvline(today_p, color=INK2, lw=0.9)
            if era == "child":
                ax.plot([s.index[-1]], [s.values[-1]], "o", ms=5, color=col, mec=SURF, mew=1.2)
    # the crash inside the plateau, on BTC price
    for ax, a, b, txt in ((axs[2], "2017-01-04", "2017-01-11", "-30% in a week\n(Jan 2017)"),
                          (axs[3], str(m.to_parent([pd.Timestamp("2021-11-08")])[0].date()), str(m.to_parent([pd.Timestamp("2022-11-21")])[0].date()), "-77%\n(Nov 2021 to Nov 2022)")):
        ax.axvspan(pd.Timestamp(a), pd.Timestamp(b), color=MUTED, alpha=0.16, lw=0)
        ax.annotate(txt, (pd.Timestamp(b), 0.10), xycoords=("data", "axes fraction"), xytext=(5, 0), textcoords="offset points", color=INK2, fontsize=8, va="bottom")
    for ax, a, b, txt in ((axs[0], "2016-12-23", "2017-01-11", "dip, 7% to 34%\nof the stretch"),
                          (axs[1], str(m.to_parent([pd.Timestamp("2021-07-30")])[0].date()), str(m.to_parent([pd.Timestamp("2022-09-08")])[0].date()), "dip, 5% to 32%\nof the stretch")):
        ax.axvspan(pd.Timestamp(a), pd.Timestamp(b), color=MUTED, alpha=0.16, lw=0)
        yy, va = (0.10, "bottom") if ax is axs[0] else (0.95, "top")
        ax.annotate(txt, (pd.Timestamp(b), yy), xycoords=("data", "axes fraction"), xytext=(5, 0), textcoords="offset points", color=INK2, fontsize=8, va=va)
    axs[0].set_xlim(p0 - pd.Timedelta(days=4), p1 + pd.Timedelta(days=3))
    # bottom labels: the parent's dates at the structures; top labels: the child's dates at the same places
    names = ["waterfall\nstart", "waterfall\nlow", "hump", "fall\nlow", "top"]
    axs[-1].set_xticks(list(m.P) + [today_p]); axs[-1].set_xticklabels([d.strftime("%b %-d\n%Y") for d in m.P] + [today_p.strftime("%b %-d\n%Y")], color=INK2)
    axs[-1].set_xlabel("Parent's date at each structure (bottom)   |   child's date at the same place (top)", color=INK2)
    top = axs[0].secondary_xaxis("top"); top.set_xticks(list(m.P) + [today_p])
    top.set_xticklabels([f"{n}\n{d.strftime('%b %-d, %Y')}" for n, d in zip(names, m.C)] + [f"today\n{TODAY.strftime('%b %-d, %Y')}"], color=INK2, fontsize=8)
    top.tick_params(length=0); top.spines["top"].set_visible(False)
    fig.suptitle("The matched BTC.D structures laid over BTC price and ETH/BTC", x=0.065, y=0.985, ha="left", color=INK, fontsize=13, fontweight="bold")
    fig.text(0.065, 0.962, "Each pair of panels shows the parent (blue) and the child (orange) stretched onto the parent's clock. Dotted lines are the matched structures;\n"
             "after the top the child keeps the plateau's pace (1 parent day = 21 child days). Shaded bands mark the biggest fall inside the plateau.", color=INK2, fontsize=8.5, va="top")
    fig.subplots_adjust(left=0.065, right=0.985, top=0.885, bottom=0.07)
    fig.savefig(OUT / "structures_through_top.png", dpi=200)


def fig_after_top():
    p0, p1 = m.P[-1], pd.Timestamp("2017-04-02")
    rows = [("BTC", "BTC price", False), ("BTC.D", "BTC dominance", False), ("ETH/BTC", "ETH/BTC (log scale)", True), ("alts (index steps out)", "Alts without stablecoins (log scale)", True)]
    fig, axs = plt.subplots(4, 1, figsize=(10, 10.6), sharex=True, gridspec_kw={"hspace": 0.26})
    today_p = m.to_parent([TODAY])[0]
    marks = [(pd.Timestamp("2017-03-03"), "parent's BTC high"), (pd.Timestamp("2017-03-10"), "parent's alt leg starts"), (pd.Timestamp("2017-03-24"), "parent's BTC low")]
    for ax, (name, lab, log) in zip(axs, rows):
        style(ax)
        p = S[name].loc[p0:p1]; p = p / p.iloc[0]
        c = child_on_parent_clock(name, p0, p1); c = c / c.iloc[0]
        ax.plot(p.index, p.values, color=PAR, lw=2, label="Parent, Feb 26 to Apr 2, 2017", solid_capstyle="round")
        ax.plot(c.index, c.values, color=CHI, lw=2, label="Child, Jun 22, 2025 to today, on the parent's clock", solid_capstyle="round")
        ax.plot([c.index[-1]], [c.values[-1]], "o", ms=6, color=CHI, mec=SURF, mew=1.5)
        if log:
            ax.set_yscale("log"); ax.set_yticks([0.5, 0.7, 1, 1.5, 2, 3, 4]); ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"x{v:g}"))
        ax.axhline(1, color=AXIS, lw=0.9)
        ax.set_title(f"{lab}, top = 1", loc="left", color=INK, fontsize=9.5, fontweight="bold", pad=4)
        for d, _ in marks:
            ax.axvline(d, color=MUTED, lw=0.7, ls=(0, (2, 3)))
        ax.axvline(today_p, color=INK2, lw=0.9)
        ax.annotate(f"x{p.values[-1]:.2f}", (p.index[-1], p.values[-1]), xytext=(4, 0), textcoords="offset points", color=INK2, fontsize=8, va="center")
        ax.annotate(f"x{c.values[-1]:.2f}", (c.index[-1], c.values[-1]), xytext=(6, -3), textcoords="offset points", color=INK2, fontsize=8, va="top")
    axs[0].legend(loc="upper center", bbox_to_anchor=(0.5, 1.66), ncol=2, frameon=False, fontsize=9, labelcolor=INK2)
    axs[0].set_xlim(p0 - pd.Timedelta(hours=12), p1 + pd.Timedelta(days=1.6))
    ticks = pd.date_range(p0, p1, freq="5D")
    axs[-1].set_xticks(ticks); axs[-1].set_xticklabels([d.strftime("%b %-d") for d in ticks], color=INK2)
    axs[-1].set_xlabel("Parent's date, 2017 (bottom)   |   child's date at the same place on the plateau's clock (top)", color=INK2)
    top = axs[0].secondary_xaxis("top")
    tt = [d for d, _ in marks] + [p0]
    axs[0].annotate(f"today\n{TODAY.strftime('%b %-d, %Y')}", (today_p, 0.97), xycoords=("data", "axes fraction"), xytext=(-5, 0), textcoords="offset points", color=INK2, fontsize=8, va="top", ha="right")
    axs[1].annotate("Apr 2: TradingView\nindex step", (pd.Timestamp("2017-04-01"), 0.30), xycoords=("data", "axes fraction"), xytext=(-6, 0), textcoords="offset points", color=INK2, fontsize=8, va="center", ha="right")
    lab = {marks[0][0]: "parent's BTC high", marks[1][0]: "parent's alt\nleg starts", marks[2][0]: "parent's\nBTC low", p0: "top"}
    top.set_xticks(tt)
    top.set_xticklabels([f"{lab[d]}\n{m.to_child([d])[0].strftime('%b %-d, %Y')}" for d in tt], color=INK2, fontsize=8)
    top.tick_params(length=0); top.spines["top"].set_visible(False)
    fig.suptitle("After the top: the child against the parent, day for day on the plateau's clock", x=0.065, y=0.985, ha="left", color=INK, fontsize=13, fontweight="bold")
    fig.text(0.065, 0.962, "One parent day is about 21 child days, so every date here has weeks of slack. BTC's high came about where this clock put it, and BTC has fallen since,\n"
             "deeper than the parent. The parent's alt leg (ETH/BTC and alts up, BTC.D down) started a week after its BTC high. The child's alt gains came before\n"
             "BTC's high and have been given back.", color=INK2, fontsize=8.5, va="top")
    fig.subplots_adjust(left=0.065, right=0.955, top=0.825, bottom=0.07)
    fig.savefig(OUT / "after_top_day_by_day.png", dpi=200)


def fig_anchors(PS, CS, i0, p0, names, box, box_labels, title, sub, who, fname, stagger):
    """Parent and child on the parent's clock between matched anchors PS[i0:] and CS[i0:]; the grey box runs PS[box[0]] to PS[box[1]]."""
    base = pd.Timestamp("2010-01-01")
    p1 = pd.Timestamp("2017-03-12")
    def child(name):
        c0 = base + pd.to_timedelta(float(np.interp(m.day([p0])[0], m.day(PS), m.day(CS))), unit="D")
        s = S[name].loc[c0:TODAY].dropna()
        t = base + pd.to_timedelta(np.interp(m.day(s.index), m.day(CS), m.day(PS)), unit="D")
        return pd.Series(s.values, index=t)
    rows = [("BTC.D", "BTC dominance, %", False), ("BTC", "BTC price, $ (log)", True), ("ETH/BTC", "ETH/BTC (log)", True)]
    fig, axs = plt.subplots(6, 1, figsize=(10, 12.8), sharex=True, gridspec_kw={"hspace": 0.3})
    for r, (name, lab, log) in enumerate(rows):
        for k, (era, col) in enumerate((("parent", PAR), ("child", CHI))):
            ax = axs[2 * r + k]; style(ax)
            s = S[name].loc[p0:p1].dropna() if era == "parent" else child(name)
            ax.plot(s.index, s.values, color=col, lw=1.6, solid_capstyle="round")
            if log:
                ax.set_yscale("log"); ax.yaxis.set_major_locator(matplotlib.ticker.LogLocator(base=10, subs=(1, 2, 5)))
                ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 10 else f"{v:.3g}"))
                ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
            ax.set_title(f"{lab}  |  {who[k]}", loc="left", color=INK, fontsize=9, fontweight="bold", pad=3)
            ax.axvspan(PS[box[0]], PS[box[1]], color=MUTED, alpha=0.16, lw=0)
            for a in PS[i0:]:
                ax.axvline(a, color=MUTED, lw=0.7, ls=(0, (2, 3)))
            if era == "child":
                ax.plot([s.index[-1]], [s.values[-1]], "o", ms=5, color=col, mec=SURF, mew=1.2)
    axs[0].set_xlim(p0, p1 + pd.Timedelta(days=1))
    axs[-1].set_xticks(list(PS[i0:])); axs[-1].set_xticklabels([d.strftime("%b %-d\n%Y") for d in PS[i0:]], color=INK2, fontsize=8)
    axs[-1].set_xlabel("Parent's date at each structure (bottom)   |   child's date at the same place (top)", color=INK2)
    for i, (a, c, n) in enumerate(zip(PS[i0:], CS[i0:], names)):
        up, ha = stagger[i]
        axs[0].annotate(f"{n}\n{c.strftime('%b %-d, %Y')}", (a, 1.0), xycoords=("data", "axes fraction"), xytext=(0, 16 + up), textcoords="offset points",
                        ha=ha, va="bottom", color=INK2, fontsize=8)
    mid = PS[box[0]] + (PS[box[1]] - PS[box[0]]) / 2
    for k in (0, 1):
        axs[k].annotate(box_labels[k], (mid, 0.06), xycoords=("data", "axes fraction"), ha="center", va="bottom", color=INK2, fontsize=8)
    fig.suptitle(title, x=0.065, y=0.987, ha="left", color=INK, fontsize=13, fontweight="bold")
    fig.text(0.065, 0.966, sub, color=INK2, fontsize=8.5, va="top")
    fig.subplots_adjust(left=0.065, right=0.985, top=0.865, bottom=0.07)
    fig.savefig(OUT / fname, dpi=200)


def fig_steven():
    """Steven's anchors, first pass (Nov 21, 2026): the grey box is the mid hump, drawn against the child's 2020-21 hump; the top is today."""
    PS = pd.DatetimeIndex(["2016-06-19", "2016-07-24", "2016-11-20", "2016-12-18", "2016-12-25", "2017-01-15", "2017-02-26"])
    CS = pd.DatetimeIndex(["2017-12-10", "2018-01-14", "2019-09-08", "2020-09-13", "2021-01-03", "2021-05-16", str(TODAY.date())])
    fig_anchors(PS, CS, 2, pd.Timestamp("2016-11-06"), ["first hump", "step low", "mid hump high", "fall low", "top = today"], (3, 5), ("mid hump", "2020-21 hump"),
                "Steven's anchors: the mid hump and the top",
                "The grey box is the mid hump: the parent's small hump after the December 2016 step, matched to the child's 2020-21 hump. Dotted lines are the\n"
                "matched structures, and the child is stretched between them. The child's line ends today, placed at the parent's top; the parent runs on two weeks.",
                ("Parent, Nov 2016 to Mar 2017", "Child, Jul 2019 to today, on the parent's clock"), "structures_steven_anchors.png",
                [(2, "center"), (26, "right"), (2, "left"), (26, "center"), (2, "center")])


def fig_hump():
    """Steven's correction (Nov 21, 2026, 9:45 PM EST): same grey box on the parent, but the child's hump is the whole one, Jan 2018 low to May 2021 low."""
    PS = pd.DatetimeIndex(["2016-11-20", "2016-12-18", "2016-12-25", "2017-01-15", "2017-02-26"])
    CS = pd.DatetimeIndex(["2017-12-10", "2018-01-14", "2019-09-08", "2021-05-16", str(TODAY.date())])
    fig_anchors(PS, CS, 0, PS[0], ["high before the fall", "hump low", "hump high", "hump end (2021 fall low)", "top = today"], (1, 3), ("mid hump", "2018 to 2021 hump"),
                "Steven's anchors, corrected: the child's hump runs from the 2018 low to the 2021 fall",
                "The grey box is the mid hump: the parent's small hump after the December 2016 step, matched to the child's whole hump from the January 2018 low to the\n"
                "May 2021 low. Dotted lines are the matched structures, and the child is stretched between them. The child's line ends today, at the parent's top.",
                ("Parent, Nov 20, 2016 to Mar 12, 2017", "Child, Dec 2017 to today, on the parent's clock"), "structures_hump_2018_2021.png",
                [(2, "left"), (26, "right"), (2, "left"), (26, "center"), (2, "center")])


def fig_two_readings():
    """The two ways to pair the parent with the child, drawn on the same two charts (Nov 21, 2026, 10:35 PM EST / Nov 22, 03:35 UTC)."""
    T = pd.Timestamp
    par = S["BTC.D"].loc["2016-06-05":"2017-03-12"].dropna(); chi = S["BTC.D"].loc["2017-02-26":TODAY].dropna()
    # (start, end, number, kind, label); kind: fall = the piece matched to the 2017-18 waterfall, hump = the grey box and its match
    R1p = [("2016-06-19", "2016-07-24", "1", "fall", "July 2016\nwaterfall"), ("2016-07-24", "2016-12-18", "2", "", "rise, then the\nDecember 16 step"),
           ("2016-12-18", "2017-01-15", "3", "hump", "grey\nbox"), ("2017-01-15", "2017-02-26", "4", "", "rise to\nthe top")]
    R1c = [("2017-12-10", "2018-01-14", "1", "fall", "2017-18\nwaterfall"), ("2018-01-14", "2021-05-16", "2", "", "2018 to 2021 hump"),
           ("2021-05-16", "2023-01-08", "3", "hump", "2021-22\nbump"), ("2023-01-08", str(TODAY.date()), "4", "", "rise to the top")]
    R2p = [("2016-06-19", "2016-11-20", "0", "", "July 2016 waterfall\nand the rise after it"), ("2016-11-20", "2016-12-18", "1", "fall", "Dec 16\nstep"),
           ("2016-12-18", "2017-01-15", "2", "hump", "grey\nbox"), ("2017-01-15", "2017-02-26", "3", "", "rise to\nthe top")]
    R2c = [("2017-02-26", "2017-12-10", "0", "", "2017"), ("2017-12-10", "2018-01-14", "1", "fall", "2017-18\nwaterfall"),
           ("2018-01-14", "2021-05-16", "2", "hump", "2018 to 2021 hump"), ("2021-05-16", str(TODAY.date()), "3", "", "rise to the top")]
    fig, axs = plt.subplots(2, 2, figsize=(11, 9.4), gridspec_kw={"width_ratios": [1, 1.3], "hspace": 0.62, "wspace": 0.1})
    for r, (bp, bc) in enumerate(((R1p, R1c), (R2p, R2c))):
        for k, (ser, bands, col) in enumerate(((par, bp, PAR), (chi, bc, CHI))):
            ax = axs[r, k]; style(ax)
            ax.plot(ser.index, ser.values, color=col, lw=1.5, solid_capstyle="round")
            lo, hi = float(ser.min()), float(ser.max()); ax.set_ylim(lo - 0.2 * (hi - lo), hi + 0.04 * (hi - lo))
            for a, b_, num, kind, lab in bands:
                a, b_ = T(a), T(b_)
                if kind:
                    ax.axvspan(a, b_, color=MUTED if kind == "hump" else col, alpha=0.2, lw=0)
                ax.axvline(a, color=MUTED, lw=0.7, ls=(0, (2, 3)))
                mid = a + (b_ - a) / 2
                ax.annotate(num, (mid, 1.0), xycoords=("data", "axes fraction"), xytext=(0, 4), textcoords="offset points", ha="center", va="bottom",
                            color=INK, fontsize=10, fontweight="bold")
                thin = (b_ - a) / (ser.index[-1] - ser.index[0]) < 0.03
                ax.annotate(lab, (mid, 0.95 if thin else 0.03), xycoords=("data", "axes fraction"), xytext=(8 if thin else 0, 0), textcoords="offset points",
                            ha="left" if thin else "center", va="top" if thin else "bottom", color=INK if kind else INK2, fontsize=7.5, fontweight="bold" if kind else "normal")
            ax.axvline(T(bands[-1][1]), color=MUTED, lw=0.7, ls=(0, (2, 3)))
            ax.set_xlim(ser.index[0], ser.index[-1] + (ser.index[-1] - ser.index[0]) * 0.01)
            if k == 0:
                ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(7, 9, 11, 1, 3))); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
            else:
                ax.xaxis.set_major_locator(mdates.YearLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
            ax.tick_params(axis="x", labelsize=8, colors=INK2)
            ax.set_title(("Parent: BTC dominance, %, Jun 2016 to Mar 2017" if k == 0 else "Child: BTC dominance, %, Feb 2017 to today"), loc="left", color=INK, fontsize=9, fontweight="bold", pad=20)
    fig.suptitle("Two ways to pair the parent with the child: which one do you see?", x=0.055, y=0.985, ha="left", color=INK, fontsize=13, fontweight="bold")
    fig.text(0.055, 0.962, "Same two charts in both rows. The same number marks the pieces that are paired. Grey is the grey box on the parent and its match on the child.\n"
             "The tinted strip is the 2017-18 waterfall on the child and the piece of the parent it is paired with.", color=INK2, fontsize=8.5, va="top")
    rows = (("Reading 1: your November 2 note, used in rounds 14 to 16", "1 July 2016 waterfall = 2017-18 waterfall     2 rise and December step = 2018 to 2021 hump     3 grey box = 2021-22 bump     4 rise to the top"),
            ("Reading 2: tonight's correction", "0 earlier pieces, not looked at     1 December 16 step = 2017-18 waterfall     2 grey box = 2018 to 2021 hump     3 rise to the top"))
    fig.subplots_adjust(left=0.055, right=0.985, top=0.83, bottom=0.06)
    for r, (h, sub) in enumerate(rows):
        y = axs[r, 0].get_position().y1
        fig.text(0.055, y + 0.075, h, color=INK, fontsize=11, fontweight="bold", va="bottom")
        fig.text(0.055, y + 0.071, sub, color=INK2, fontsize=8.5, va="top")
    fig.savefig(OUT / "two_readings.png", dpi=200)


if __name__ == "__main__":
    fig_through_top(); fig_after_top(); fig_steven(); fig_hump(); fig_two_readings()
    print("ok")
