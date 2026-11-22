# Round 16: the BTC.D structure dates laid over BTC, alts and ETH/BTC

Asked Nov 21, 2026, 8:50 PM EST (Nov 22, 01:50 UTC): map the key BTC.D structures in time onto the
other charts and say whether the market's current fall is a stretched small feature of the parent,
noise, or something new. Data through the Nov 21, 2026 daily bar.

## Method

Matched structure dates (round 14 anchors plus the tops):

| structure | parent | child |
|---|---|---|
| waterfall start | 2016-06-19 | 2017-12-10 |
| waterfall low | 2016-07-24 | 2018-01-14 |
| hump | 2016-11-20 | 2019-09-08 |
| mid-structure fall low | 2016-12-18 | 2021-05-16 |
| top | 2017-02-26 | 2025-06-22 |

Time between two structures is mapped in a straight line (paces 1.0, 5.1, 22.0 and 21.4 child weeks
per parent week). After the top the plateau's pace (21.4) is carried on, which is an assumption.
`structure_map.py` then measures BTC price, alts without stablecoins (TradingView index-step days
taken out), ETH/BTC and the whole market between the same dates, finds each chart's biggest fall and
rise inside every stretch, scores how well the child follows the parent on the mapped clock against
2,000 random clocks of two kinds, and lists the order of events after the top. `charts.py` draws
the two figures.

## Results

1. Inside the plateau the biggest fall sits in the same part of the stretch in both eras. BTC price:
   parent Jan 4 to Jan 11, 2017, -30.2% (24% to 34% of the way through); child Nov 8, 2021 to
   Nov 21, 2022, -76.7% (12% to 37%). BTC.D: parent Dec 23, 2016 to Jan 11, 2017, -1.4% (7% to 34%);
   child Jul 30, 2021 to Sep 8, 2022, -20.2% (5% to 32%). So the parent's small pre-top feature
   already has a counterpart, the 2022 bear market. It is one event and the child's fall covers a
   quarter of the stretch, so this is a description, not a test. The insides of the other three
   stretches mostly do not line up (for example BTC's biggest fall in the rise to the hump ends 8% of
   the way in for the parent and 56% for the child).
2. Only BTC.D itself clearly follows the mapped clock (trend-removed 0.68; a random clock does as
   well 0.4% of the time, a clock with the chosen dates moved by up to a year 3.8%; weekly changes
   0.54, 0.7% and 0.3%). It is also the chart the dates were chosen on. BTC price looks close on
   levels (0.84) but a nearby clock does as well 12% of the time and weekly changes give 0.36 (37%).
   Alts (0.01) and ETH/BTC (-0.32) do not follow it. With the hump at Jan 3, 2021 everything weakens.
3. After the top. Parent: BTC close high Mar 3, 2017 ($1,285; Mar 6 was within 0.5%), alt leg starts
   Mar 10 to 11 (ETH/BTC 0.0148 to 0.0172, BTC.D breaks down), BTC low Mar 24 (-27.7%; during the
   fall BTC.D x0.94, ETH/BTC x3.8, alts x1.7). Child: BTC.D low Sep 13, 2025 (x0.875 of the top),
   ETH/BTC x1.9 by Aug 24, alts x1.78 by Oct 6, BTC close high Oct 6, 2025 ($124,728), then BTC
   -53.1% to the Jun 30, 2026 close low and -51.8% now, with BTC.D flat (x0.99), ETH/BTC x0.71 and
   alts x0.39 through the fall. On the plateau's clock the parent's BTC high lands on Oct 7, 2025,
   its alt-leg start on Mar 6, 2026 (37 weeks ago), today on Mar 22, 2017 and its BTC low on
   Dec 30, 2026. One parent day is 21.4 child days, so each of these has about six weeks of slack
   either way, more if the pace changes, as it has at every structure so far.
4. Size. The child's BTC.D moves are 18, 32, 26 and 53 times the parent's in log terms for the four
   stretches. The child's June to September 2025 drop (x0.875) equals the parent's first leg as
   TradingView draws it (x0.872 on Apr 2, 2017, of which x0.929 to x0.872 is a one-day index step)
   and is 17 times the parent's slip in the week between its top and its BTC high (x0.994). Both
   readings are open: "the first leg already happened" fits the size as drawn, a visible alt move
   (ETH/BTC x1.8, alts x1.8 against the parent's x3.7, x2.7) and the flat range since; "the first leg
   is still ahead" fits the order (the child's move came before BTC's high, the parent's leg after)
   and the usual magnification, but applying a magnification measured on long stretches to a
   one-week slip is an assumption.
5. BTC scaling (one matched pair, loose): the crash inside the plateau was 4.05 times larger in log
   terms in the child. Scaled the same way the parent's Mar 3 to Mar 10 dip (-13.1%) is -43% and its
   Mar 3 to Mar 24 fall (-27.7%) is -73% (about $33,500). The child is between the two.

## What it means

Today's fall is not the small pre-top feature; that place is taken by 2022. It comes after the top
and after a new BTC high, which is where the parent has BTC's March 2017 drop. The part with no
counterpart is alts falling through it: the parent's alt leg began a week after BTC's high. The
mapped clock is supported on BTC.D only, so it gives an order of events, not a date.

An independent check re-computed the numbers and weakened results 1 to 4 to the wording above
(location match loose by construction; BTC price agreement mostly shared trend; post-top dates
carry weeks of slack; the first-leg reading is not forced).

## Files

`structure_map.py`, `structure_map.json`, `charts.py`,
`structures_through_top.png`, `after_top_day_by_day.png`, `steven_anchors.py`, `steven_anchors.json`,
`structures_steven_anchors.png`.

## Addendum: the same map on Steven's anchors (Nov 21, 2026, 9:30 PM EST / Nov 22, 02:30 UTC)

Steven's correction: the grey box on the parent is the mid hump (low Dec 18, high Dec 25, 2016, low
Jan 15, 2017), the match for the child's 2020-21 hump (low Sep 13, 2020, high Jan 3, 2021, low
May 16, 2021). The dilation is dynamic and the parent's top is today, not Jun 22, 2025.
`steven_anchors.py` reruns the map on those seven anchors; `charts.py` draws
`structures_steven_anchors.png`.

- Paces 1.0, 5.1, 13.2, 16.0, 6.3 and 48.0 child weeks per parent week; BTC.D moves 18, 32, 10, 21,
  49 and 34 times the parent's in log terms.
- Better than the first anchors: the parent's mid-structure fall is a market move, not the Dec 16
  index step; ETH/BTC x1.49 and alts x1.17 in it (child's 2021 fall x2.61 and x5.08); BTC's crash
  sits at the end of the fall in both (parent Jan 4 to 11, 2017, -30.2%, BTC.D low Jan 11; child
  from Apr 13, 2021, -42% by May 19, BTC.D low May 18, -53% by Jul 20). The small feature before the
  top is therefore the spring 2021 crash, not 2022.
- Clock test, 1,000 nearby clocks (first anchors / Steven's): BTC.D levels 0.68 (2.9%) / 0.67 (5.1%),
  weekly changes 0.54 (0.1%) / 0.37 (1.4%); BTC 0.84 (8.6%) / 0.83 (6.7%) and 0.36 (37%) / 0.31 (11%);
  alts 0.01 / 0.09; ETH/BTC -0.32 / -0.04. Only BTC.D clears chance on either set.
- Not fitting: BTC's price in the last stretch (parent +43% with one 6.3% dip; child -76.7% in 2022
  and -51.8% now). The parent dipped 95.67 to 95.39 (Feb 8 to 15, 2017), pushed to 96.09 (Feb 24)
  and rolled over; the child's June to September 2025 drop is 46 times that dip and it has not
  pushed back up (59.2 against 65.72).
- Past falls took 5, 12, 5, 19 and 12 weeks (about 11 on average), in line with Steven's three months.
  (Superseded: only the two 5-week falls, July 2016 and 2017-18, are waterfalls; see the timing section below.)
- The dates taken from the plateau's fixed pace after the top do not apply on these anchors.

## Correction: the child's hump is the whole 2018 to 2021 hump (Nov 21, 2026, 10:00 PM EST / Nov 22, 03:00 UTC)

Steven's second correction: the grey box on the parent is right (low Dec 18 2016, high Dec 25, low
Jan 15 2017), but its match in the child is the whole hump from the bottom of the 2017-18 waterfall
(Jan 14 2018) through the Sep 8 2019 high to the 2021 fall (low May 16 2021), not only the 2020-21
part. He also rules out one more push up in BTC dominance (it would break the head and shoulders).
`hump_2018_2021.py` reruns the map; `charts.py` draws `structures_hump_2018_2021.png`.

- Pace: fall into the hump's low 1.2 child weeks per parent week, hump up 86, hump down 29 (whole
  hump 43.5), rise to the top 48.0 to today (35.7 to the Jun 22 2025 high). The first addendum's
  pairing ran 13.2, 16.0, 6.3, 48.0 over the same ground.
- At the hump's pace six parent weeks after May 16 2021 land on about May 17 2026, two weeks after
  the right shoulder's weekly close (60.92, May 3 2026). One parent day is 6.2 child weeks, so this
  says "this zone", not a date.
- BTC.D size of the child's move against the parent's (logs): 28, 75, 51, 34 (43 to the 2025 high).
- Inside the hump: the sag gives back 39% of the rise in the parent and 31% in the child; the last
  bounce recovers 22% of the sag in the parent (0.09 point) and 91% in the child; the fall is 126%
  of the rise in the parent and 85% in the child.
- The parent's top came back to the hump's high (96.09 on Feb 24 2017 against 96.10); the child's
  Jun 22 2025 high regained 85% of the hump's fall (65.72 against 71.70); today 66%.
- Not fitting: BTC's price runs the other way inside the hump (parent +13% then -8%, child -24%
  then x4.5); ETH/BTC agrees in direction. The BTC.D weekly-change match (0.58, 0.6% of 1,000
  nearby clocks as good) is largely built in by the anchors; the level match is nil (0.04).
- Open: this pairing puts the 2017-18 waterfall against the Dec 16 2016 index step. Carried back
  one structure (not Steven's wording) the July 2016 waterfall sits against Feb 26 to Aug 27 2017.
- Everything from the 2021 fall low onward is as in the addendum above.

## Settled: reading 1 is the fractal, the corrected hump is an echo (Nov 21, 2026, 10:50 PM EST / Nov 22, 03:50 UTC)

Steven, after seeing both pairings side by side (`two_readings.png`, drawn by `charts.py`): "both
things are true at once". The overall fractal is reading 1 (his November 2 note): July 2016
waterfall = 2017-18 waterfall, rise and December 16 step = the 2018 to 2021 hump, grey box = the
2021-22 sideways consolidation (not a "bump"), then the rise to the top. The corrected hump above
is "a kind of fractal artifact": an echo, not a second set of anchors. Kept from tonight: the top
is now (the zone since June 2025), no more push up, the dilation moves.

- Echo on the parent itself: hump 95.19, 97.19, 95.11 over 21 weeks; grey box 95.11, 95.96, 94.91
  over 4 weeks. Each gives back a little more than it gained (104% and 124% of the rise); the grey
  box is 2.3 times smaller and 5 times shorter. Timing differs: 81% of the hump's time is the way
  up, 25% of the grey box's.
- Consolidation: parent weekly closes 94.91 to 95.96 for 4 weeks (about half the size of the fall
  before it, logs); child 39.36 to 48.03 from May 2021 to the end of 2022 (about a third).
- Pace on reading 1: 1.0, 5.1, 22.0, 19.5 to 21.5 for the consolidation, then 34 to 35 for the
  last rise to today (21 to 23 to the June 22 2025 high).
- Put back: the BTC crash inside the grey box (Jan 4 to 11 2017, -30.2%) pairs with the 2022 bear
  inside the consolidation (Nov 8 2021 to Nov 21 2022, -76.7%), not with spring 2021.

## Timing of the waterfall: what was in place each time (Nov 21, 2026, 11:30 PM EST / Nov 22, 04:30 UTC)

Corrected Nov 22, 2026, 8:22 AM EST / 13:22 UTC on Steven's word: there are only two waterfalls in
2016-18. Read with his Nov 2 note they are the mid-July 2016 waterfall (parent) and the 2017-18
waterfall (child). The first version counted the 2017 fall after the parent's top as a third.

`waterfall_starts.py` lists BTC, USDT.D and ETH/BTC around the two waterfalls, around the 2017 fall
after the parent's top (what the parent did next; not counted as a waterfall) and the same readings
today. No clock is used. On Steven's word the 2021 fall (the mid-structure fall) and the Jun-Sep
2025 drop (inside the top) are not waterfalls and are left out.

- BTC was at its 52-week high on weekly closes at the start of both waterfalls, after +85% and +248%
  over the prior 13 weeks, and also at the start of the 2017 fall after the top (+62%). Today it is
  38% below its 52-week high and -22% over 13 weeks.
- ETH/BTC gave no early warning: no data before the July 2016 waterfall; -59% and at its 26-week low
  before 2017-18, then x1.86 within three weeks of the BTC.D high. Before the 2017 fall after the
  top it was +1% over 13 weeks, then x3.41 within three weeks.
- USDT.D was under half a percent of the market each time, so it has no record here.
- Both waterfalls ran 5 weeks; the 2017 fall after the top ran 12. Two waterfalls and one more fall:
  a description, not a rule, and all of it from 2016-18 (round 17: not a template for today).
