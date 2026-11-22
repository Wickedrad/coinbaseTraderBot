# Typed rules: edge saved only for the day or trade type where it held

Steven's rule (Nov 22 2026, 8:04 AM EST / 13:04 UTC): if edge shows on some days or trades but not others, find the difference, check whether it still performs on the same type of day or trade, and if it does, save it only for that type.

How a rule gets in (daytypes.py, recorded days only, paper only, day-cluster intervals): positive lower bound in the build block (at least 300 fills), positive lower bound in the check block (at least 150 fills), positive mean in the clean block (at least 100 fills), and better than the same rule on the other days by at least 0.25c in both check and clean. Day labels use only what is known before the day opens. Entry is not proof of edge: it means the pocket survived the tests written in advance. Read the flags.

Nothing here is an order, a bot change, or a heat-curve edit. Using any of it needs Steven's word and a logged deploy.

## Registry

### T1. BTC and ETH 15-minute, YES buy 90 to 97c after a low-YES-share day (PRELIMINARY)

- Rule: resting YES buy at the best bid, price 90 to 97 cents, placed in minutes 6 to 9 of the quarter hour, cancelled at minute 14, held to settlement. No maker fee on these series. Applies to BTC and ETH 15-minute markets only.
- Type: the previous UTC day's share of YES settlements was 47.5% or lower (bottom third of the build days; the middle cut is 51.0%).
- Found: Round EA-5c, run 45026190707 and 45030594167. Re-read unchanged in run 45031919616.

| Block (typed days) | Typed days: net c per fill (day-cluster lower bound), fills | Same rule on other days |
|---|---|---|
| Build, Apr 13 to Jul 24 (34) | +1.72c (+0.06), 759 | not used |
| Check, Jul 25 to Sep 13 (15) | +3.19c (+0.40), 389 | +0.09c (-1.73), 882 |
| Clean, Sep 14 to Nov 4 (16) | +1.31c (-1.19), 358 | -1.60c (-3.61), 873 |

Transfer read (fixed in advance, no re-search): BTC alone +1.17 / +3.65 / +0.15c; ETH alone +2.33 / +2.78 / +2.35c (build / check / clean); same sign in both coins in every block. Does not carry to oil, silver, gas, FX, alt coins, Brent, platinum or yields (check or clean negative in each, few days of the type: 2 to 6 per block).

Flags, all of them still open:
- The clean lower bound is below zero (-1.19c). Only the clean mean is positive.
- The label-shift placebo finds one typed rule by chance in about 6% of runs of this data set (p = 0.06; 0.035 with the first labels, before the volume and spread fix, which did not touch this rule's label).
- It is one of about 40,000 typed tests across ten data sets.
- Same 90 to 97 cent bucket as round 3's weak survivors, so it is probably one effect seen twice, not two.
- Size: about 22 fills on a typed day at about 13c a fill, on roughly a third of days, which is well under $0.10 an hour. It is not the $2.60 an hour Steven said he would take.
- Held to settlement: needs the same exception to the no-hold rule that the NO-hold arm needed, and it would only be a paper arm.

Status: kept for its type only. Do not describe it as an edge, and do not apply it on other days, other coins, or other families.

## Not saved (checked and failed)

- The mean rule on weekends is worse than on weekdays in BTC and ETH, oil, silver, gas, FX, Brent, platinum and yields. That is a type to avoid, not an edge.
- Previous-day surprise, volume, spread and YES share do not separate the mean rule on any data set.
- No typed rule on the hourly ladders, oil, silver, gas, FX, alt coins, Brent, platinum, yields, or the four daily bracket groups; their placebos also found none.
