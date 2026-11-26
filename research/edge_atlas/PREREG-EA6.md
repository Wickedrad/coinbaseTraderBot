# Round EA-6 pre-registration (written Wed Nov 25 2026, about 8:15 PM EST / 01:15 UTC Nov 26, before any of these days is read)

Steven (8:11 PM EST / 01:11 UTC, via the coordinator): "Resume and Continue until 10:30 PM". Recorded days only, paper only, no order, no bot change, nothing waits for a future day. Both reads below use days that have been recorded since the earlier rounds and were never read.

## 1. Fresh-days read of the saved typed rule T1 (job dtfresh, python/subminute/fresh.py)

Rule, fixed in advance and not tuned: BTC and ETH 15-minute, resting YES buy at the best bid, price 90 to 97 cents, placed in minutes 6 to 9, cancelled at minute 14, held to settlement, only on a day after a day whose YES share was at or below the build cut (0.4754, from the Apr 13 to Jul 24 days).

Days read: Nov 5 to Nov 25 2026 (21 UTC days after the last day T1 was found on, Nov 4). Nothing else is searched. The same run re-reads the three original blocks (build, check, clean), so the table must reproduce +1.72c, +3.19c and +1.31c on the ALL scope; if it does not, the plumbing differs and the fresh read is not used.

Verdict, written before the read (ALL scope, typed days of the fresh block, net cents per fill):
- SUPPORTED: mean above zero, at least 100 fills, and at least 0.25c above the same rule on the other fresh days.
- CONTRADICTED: mean at or below zero, or below the other days' mean.
- TOO THIN: under 100 fills, or positive but under 0.25c above the other days.
Also printed: BTC and ETH separately, a permutation check (the same number of fresh days drawn at random from the fresh days: how often does a random pick do as well), and the mean rule by weekend and previous-day YES share in the clean and fresh blocks.

What each outcome changes: only the status line of T1 in typed_rules.md. SUPPORTED keeps it preliminary (about 21 fresh days cannot lift a placebo p of 0.06; the interval stays wide) and says it held on days it never saw. CONTRADICTED retires it. TOO THIN leaves it as it is. No outcome starts anything beyond paper.

## 2. Second unseen block for the hourly lean (loss-review-stages.yml on main, zero model tokens)

Days Nov 23 to Nov 25 (the 0056 read stopped at Nov 22): ladder, marketbase and anatomy with days=3, day=2026-11-25. Hypotheses unchanged from 0056: H6 (hourly YES edge below zero, NO mid net above +1c), H7a (lane hourly YES edge below -3c), H7b (lane NO side above +2c on a majority of days), H7c (lane 15m NO above the market's 15m NO by 2c). Three days are a sign check, not a pass. The Nov 12-18 lean failed to repeat on Nov 19-22; this block asks whether it comes back. No ask to Steven unless the stated condition (hourly YES negative and NO positive, H7a to c passing) holds.
