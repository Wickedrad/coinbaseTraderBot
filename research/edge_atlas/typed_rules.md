# Typed rules: edge saved only for the day or trade type where it held

Steven's rule (Nov 22 2026, 8:04 AM EST / 13:04 UTC): if edge shows on some days or trades but not others, find the difference, check whether it still performs on the same type of day or trade, and if it does, save it only for that type.

How a rule gets in (daytypes.py, recorded days only, paper only, day-cluster intervals): positive lower bound in the build block (at least 300 fills), positive lower bound in the check block (at least 150 fills), positive mean in the clean block (at least 100 fills), and better than the same rule on the other days by at least 0.25c in both check and clean. Day labels use only what is known before the day opens. Entry is not proof of edge: it means the pocket survived the tests written in advance. Read the flags.

Nothing here is an order, a bot change, or a heat-curve edit. Using any of it needs Steven's word and a logged deploy.

## Registry

### T1. BTC and ETH 15-minute, YES buy 90 to 97c after a low-YES-share day (PRELIMINARY; retired Nov 25 8:35 PM EST on the fresh days, put back at 9:36 PM EST by the pre-registered pooled read of all unseen days; see the flags)

- Rule: resting YES buy at the best bid, price 90 to 97 cents, placed in minutes 6 to 9 of the quarter hour, cancelled at minute 14, held to settlement. No maker fee on these series. Applies to BTC and ETH 15-minute markets only.
- Type: the previous UTC day's share of YES settlements was 47.5% or lower (bottom third of the build days; the middle cut is 51.0%).
- Found: Round EA-5c, run 45026190707 and 45030594167. Re-read unchanged in run 45031919616.

| Block (typed days) | Typed days: net c per fill (day-cluster lower bound), fills | Same rule on other days |
|---|---|---|
| Build, Apr 13 to Jul 24 (34) | +1.72c (+0.06), 759 | not used |
| Check, Jul 25 to Sep 13 (15) | +3.19c (+0.40), 389 | +0.09c (-1.73), 882 |
| Clean, Sep 14 to Nov 4 (16) | +1.31c (-1.19), 358 | -1.60c (-3.61), 873 |
| Fresh, Nov 5 to Nov 25 (9 of 21 days; round EA-6, read once, job dtfresh, run 45734547381) | -0.87c (-4.91), 180 | -1.79c (-6.11), 272 |
| Back, Mar 1 to Apr 12 (7 of 43 days; round EA-6, read once, job dtback, run 45743157839) | +2.01c (-1.17), 101 | -0.64c (-2.53), 624 |
| **Pooled unseen (fresh + back, 16 of 64 days)** | **+0.17c (-2.62), 281** | -0.99c (-2.84), 896 |

Unseen-days reads (round EA-6, written down before the days were read, PREREG-EA6.md). Nothing was searched or tuned; the rule and the three verdicts were fixed in advance.
- Fresh days, Nov 5 to Nov 25 (the 21 days recorded after the rule was found): typed days -0.87c a fill (9 days, 180 fills). Verdict CONTRADICTED (mean at or below zero). Permutation p 0.40 (BTC -4.13c, 90 fills; ETH +2.39c, 90 fills). The same run reproduced the check, clean and fresh numbers exactly.
- Back days, Mar 1 to Apr 12 (43 recorded days before the first day the rule was built on; the 40-minute download reached back that far and no further): typed days +2.01c (7 days, 101 fills, lower bound -1.17c), other days -0.64c. Verdict SUPPORTED, but only just: the fill floor is 100, the permutation p is 0.12, and BTC alone is +0.56c (55 fills), ETH alone +3.76c (46 fills, below its own floor).
- Pooled unseen (fresh + back, 64 days, 16 typed): typed +0.17c (lower bound -2.62c, 281 fills), other days -0.99c, a gap of 1.16c. Pre-registered rule: put T1 back to PRELIMINARY only if the typed mean is above zero with at least 250 fills and at least 0.25c above the other unseen days. All three hold, so the status goes back to PRELIMINARY.
- Plumbing: adding the back days gives April 13 a previous day, so the build block now has 35 typed days (+1.86c, 782 fills, lower bound +0.23c) instead of 34 (+1.72c, 759), and the build tercile cut moves from 0.4754 to 0.4740 (no check, clean, fresh or back day changes type; days have 192 or so markets so the shares move in steps of about 0.005). Check, clean and fresh reproduce exactly.

What the unseen days say, plainly: the day type is real in the sense that typed days beat the other days in every block (build +2.4c, check +3.1c, clean +2.9c, fresh +0.9c, back +2.7c, pooled unseen +1.2c), but the typed days' own level on days the rule never saw is about zero (+0.17c a fill, interval wide: lower bound -2.6c), not a profit. The rule trims the loss; it does not clearly turn it into a gain.

Transfer read (fixed in advance, no re-search): BTC alone +1.17 / +3.65 / +0.15c; ETH alone +2.33 / +2.78 / +2.35c (build / check / clean); same sign in both coins in every block. Does not carry to oil, silver, gas, FX, alt coins, Brent, platinum or yields (check or clean negative in each, few days of the type: 2 to 6 per block), nor to SOL and XRP (round EA-6, 89 days Aug 30 to Nov 26, pre-registered: typed +0.60c / +0.04c / -2.22c against +1.65c / +0.25c / -1.79c on the other days, 9 to 15 typed days a block; 0 typed rules in 3,024 tests there). Scope stays BTC and ETH 15-minute only.

Flags, all of them still open:
- The clean lower bound is below zero (-1.19c). Only the clean mean is positive.
- The label-shift placebo finds one typed rule by chance in about 6% of runs of this data set (p = 0.06; 0.035 with the first labels, before the volume and spread fix, which did not touch this rule's label).
- It is one of about 40,000 typed tests across ten data sets.
- Same 90 to 97 cent bucket as round 3's weak survivors, so it is probably one effect seen twice, not two.
- Size: about 22 fills on a typed day at about 13c a fill, on roughly a third of days, which is well under $0.10 an hour. It is not the $2.60 an hour Steven said he would take.
- Held to settlement: needs the same exception to the no-hold rule that the NO-hold arm needed, and it would only be a paper arm.

Status: PRELIMINARY, and weaker than it looked after round 5c. Nothing here is an order, and no part of it is in the bot. Do not describe it as an edge and do not use it on other days, other coins or other families. Open flags on top of the ones above: the fresh block alone contradicted it (retired at 8:35 PM EST) and only the pooled read with 43 older days put it back; the back verdict clears its fill floor by one fill; typed days on unseen days average +0.17c a fill, which is about 3c per typed day (17 fills a typed day), nowhere near the $2.60 an hour Steven said he would take. ETH alone has been positive in all five blocks (build +2.47c, check +2.78c, clean +2.35c, fresh +2.39c, back +3.76c; unseen pooled +2.85c, lower bound -1.12c, 136 fills) while BTC alone is not (unseen -2.35c, 145 fills). ETH was picked after the fresh read, so it is reported here and not saved; it would need a pre-registered read on days it never touched. The recorded days from Dec 16 2025 to Feb 28 2026 (about 74 days, BTC and ETH) are listed by Kalshi but not downloaded yet (6,700 markets each are left for a later run).
