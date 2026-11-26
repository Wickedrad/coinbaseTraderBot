# Typed rules: edge saved only for the day or trade type where it held

Steven's rule (Nov 22 2026, 8:04 AM EST / 13:04 UTC): if edge shows on some days or trades but not others, find the difference, check whether it still performs on the same type of day or trade, and if it does, save it only for that type.

How a rule gets in (daytypes.py, recorded days only, paper only, day-cluster intervals): positive lower bound in the build block (at least 300 fills), positive lower bound in the check block (at least 150 fills), positive mean in the clean block (at least 100 fills), and better than the same rule on the other days by at least 0.25c in both check and clean. Day labels use only what is known before the day opens. Entry is not proof of edge: it means the pocket survived the tests written in advance. Read the flags.

Nothing here is an order, a bot change, or a heat-curve edit. Using any of it needs Steven's word and a logged deploy.

## Registry

### T1. BTC and ETH 15-minute, YES buy 90 to 97c after a low-YES-share day (RETIRED Nov 25 2026: contradicted on the 21 fresh days; kept here as a record)

- Rule: resting YES buy at the best bid, price 90 to 97 cents, placed in minutes 6 to 9 of the quarter hour, cancelled at minute 14, held to settlement. No maker fee on these series. Applies to BTC and ETH 15-minute markets only.
- Type: the previous UTC day's share of YES settlements was 47.5% or lower (bottom third of the build days; the middle cut is 51.0%).
- Found: Round EA-5c, run 45026190707 and 45030594167. Re-read unchanged in run 45031919616.

| Block (typed days) | Typed days: net c per fill (day-cluster lower bound), fills | Same rule on other days |
|---|---|---|
| Build, Apr 13 to Jul 24 (34) | +1.72c (+0.06), 759 | not used |
| Check, Jul 25 to Sep 13 (15) | +3.19c (+0.40), 389 | +0.09c (-1.73), 882 |
| Clean, Sep 14 to Nov 4 (16) | +1.31c (-1.19), 358 | -1.60c (-3.61), 873 |
| Fresh, Nov 5 to Nov 25 (9 of 21 days; round EA-6, read once, job dtfresh, run 45734547381) | -0.87c (-4.91), 180 | -1.79c (-6.11), 272 |

Fresh-days read (written down before the days were read, PREREG-EA6.md): the same pipeline re-read the three original blocks and reproduced +1.72c, +3.19c and +1.31c, so the plumbing is the same. On the 21 days recorded after the last day the rule was found on, the typed days lost 0.87c a fill (9 days, 180 fills, day-cluster lower bound -4.91c). Pre-registered verdict: CONTRADICTED (mean at or below zero). The typed days still beat the other fresh days by 0.92c, and a random pick of 9 fresh days does as well or better 39% of the time (BTC alone -4.13c, 90 fills; ETH alone +2.39c, 90 fills, lower bound -3.43c). Nine days is a short block, so this does not prove the rule has no edge; it means the rule did not hold on days it never saw, and it is retired as a saved rule.

Transfer read (fixed in advance, no re-search): BTC alone +1.17 / +3.65 / +0.15c; ETH alone +2.33 / +2.78 / +2.35c (build / check / clean); same sign in both coins in every block. Does not carry to oil, silver, gas, FX, alt coins, Brent, platinum or yields (check or clean negative in each, few days of the type: 2 to 6 per block).

Flags, all of them still open:
- The clean lower bound is below zero (-1.19c). Only the clean mean is positive.
- The label-shift placebo finds one typed rule by chance in about 6% of runs of this data set (p = 0.06; 0.035 with the first labels, before the volume and spread fix, which did not touch this rule's label).
- It is one of about 40,000 typed tests across ten data sets.
- Same 90 to 97 cent bucket as round 3's weak survivors, so it is probably one effect seen twice, not two.
- Size: about 22 fills on a typed day at about 13c a fill, on roughly a third of days, which is well under $0.10 an hour. It is not the $2.60 an hour Steven said he would take.
- Held to settlement: needs the same exception to the no-hold rule that the NO-hold arm needed, and it would only be a paper arm.

Status: RETIRED on Nov 25 2026 (round EA-6). It was kept for its type only and flagged preliminary; the one read it had on unseen days came back negative, as the pre-registered verdict said it would retire it. Do not describe it as an edge and do not use it. One loose end that is not a rescue: ETH alone has been positive in all four blocks (+2.33, +2.78, +2.35, +2.39c) with every interval except build crossing zero; picking ETH after seeing the fresh days would be a new, post-hoc rule, so it needs its own pre-registered read on other recorded days and is not saved here.

## Not saved (checked and failed)

- The mean rule on weekends is worse than on weekdays in BTC and ETH, oil, silver, gas, FX, Brent, platinum and yields. That is a type to avoid, not an edge.
- Previous-day surprise, volume, spread and YES share do not separate the mean rule on any data set.
- No typed rule on the hourly ladders, oil, silver, gas, FX, alt coins, Brent, platinum, yields, or the four daily bracket groups; their placebos also found none.
