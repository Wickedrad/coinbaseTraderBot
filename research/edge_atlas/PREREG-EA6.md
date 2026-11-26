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

## 3. Transfer of T1 to SOL and XRP 15-minute (job dtsx; added 8:20 PM EST / 01:20 UTC, before the candles are fetched)

Round 5c read T1 on the BTC/ETH sister families (oil, FX, alt coins, ...) but never on SOL and XRP: those two had only the 10 recorded book days, not candle history. Their Kalshi 15-minute candles (since the series began, at most 150 days) are fetched read only and kept on Drive. The same rule, unchanged: YES buy 90 to 97c from minute 6, cancel 14, after a day whose YES share is in the bottom third of that coin pair's own first-half days. The day-type search is run as in round 5c (so the count of typed rules and its placebo are printed), but the verdict is on the fixed rule only: it CARRIES if, on SOL and XRP pooled (ALL), the typed days' mean is above zero and at least 0.25c above the other days in both the check and the clean block, with at least 100 fills in each; otherwise it DOES NOT CARRY. A result only changes the scope line of T1 in typed_rules.md.

## 4. Backward read of T1: the recorded days before Apr 13 2026 (job dtback; written about 8:40 PM EST / 01:40 UTC Nov 26, after the fresh read came back and before any of these days was fetched; committed together with the workflow that fetches them, in commit a56345c8)

Why: the fresh read (part 1, run 45734547381) came back CONTRADICTED: the typed days of Nov 5 to Nov 25 lost 0.87c a fill (9 days, 180 fills), and it reproduced +1.72c, +3.19c and +1.31c on the three original blocks, so the plumbing is the same. Nine typed days is a short block, and the ETH half of the rule had been positive in all four blocks (+2.33, +2.78, +2.35, +2.39c) while BTC had not. The only recorded days the rule has never touched are the ones before Apr 13 2026 (the first day the earlier rounds kept). The Kalshi API lists settled BTC and ETH 15-minute markets that far back if the series existed; whether it does is part of what the job finds out.

Data: KXBTC15M and KXETH15M settled markets before Apr 13, listed newest first (so Apr 12 backwards), BTC and ETH fetched at the same time, 40 minutes of fetching in all, read only, kept on Drive at raw/oracle-history/kalshi. Nothing else is searched. Days read: whatever the 40 minutes bring, at most the last 345 days.

Rule, unchanged and not tuned: the same T1 rule (resting YES buy at the best bid, 90 to 97 cents, placed in minutes 6 to 9, cancelled at minute 14, held to settlement, only after a day whose YES share was at or below the build cut 0.4754). The build block stays Apr 13 to Jul 24, so the cut stays the same. The first backward day has no previous day and is dropped.

Verdicts, fixed now:
- BACK, ALL scope: SUPPORTED, CONTRADICTED or TOO THIN by the part 1 rule (typed mean above zero, at least 100 fills, at least 0.25c above the other backward days; CONTRADICTED if the typed mean is at or below zero or below the other days').
- ETH alone, BACK: the one subgroup named in advance (it is the half that stayed positive; there is no BTC-alone rescue and no other subgroup). Same rule, at least 100 fills. It is reported and not saved: it was picked after the fresh read, so it can only point to something, never confirm itself.
- POOLED UNSEEN (the fresh Nov 5 to Nov 25 days plus the backward days), ALL scope: T1 goes back from RETIRED to PRELIMINARY only if the typed mean is above zero with at least 250 fills and at least 0.25c above the other unseen days. Otherwise it stays retired.
Also printed: the permutation check on the backward block, and the three original blocks again as the plumbing check (they must reproduce +1.72c, +3.19c, +1.31c on ALL).

What each outcome changes: only the status line of T1 in typed_rules.md and a note on ETH. No outcome starts anything beyond paper.

Implementation note to part 4 (written about 9:25 PM EST / 02:25 UTC, after the download finished and before the rule was read on any of these days): the 40 minutes of fetching worked (Kalshi lists these series back to Dec 16 2025; 4,193 new BTC and 4,137 new ETH markets came back, about 44 days before Apr 13 each; Kalshi slowed the requests down about 1,600 times each). The first run of the read step then stopped on a shell error (a pipe under pipefail) before any number was printed. The rerun reads the same days from Drive and fetches nothing more (fetch_min=0 in RUN-DTBACK). One thing is fixed here and not by looking at results: the block starts two days after the last day that did not come back whole for both coins (at least 85 markets a day), because the days the download never reached hold only the never-traded markets and would give a wrong "previous day" label. Nothing else changed.

Second implementation note to part 4 (written about 9:28 PM EST / 02:28 UTC, before the rule was read on any backward day): the rerun found only 2 whole days at the end of the window (the days the download never reached hold only the never-traded markets, so the "last short day plus two" start left no block). The backward block is now chosen from market counts only, never from any result: the longest run of consecutive days before Apr 13 on which both coins have at least 90% of their median markets a day on Apr 13 to Apr 30, with the run's first day dropped (its previous day is not whole), and at least 22 days. If no such run exists the backward read is reported as not possible. Nothing else changed.

Third implementation note to part 4 (written about 9:33 PM EST / 02:33 UTC, before the rule was read on any backward day): the run-length line of the third run showed the download reached every day from Mar 1 to Apr 12 (43 days) but that one day in seven (Mar 5, 12, 19, 26, Apr 2, 9, which are Thursdays) holds fewer than 90% of the usual 96 markets, which splits the window into runs of 6 days. That is a feature of the series (a weekly gap in the markets listed, probably Kalshi's Thursday maintenance), not a missing download, and the same Thursdays are in the build, check, clean and fresh blocks. The whole-day line is therefore set at 70% of the median instead of 90% (a day only the never-traded markets reached has 1 to 3 markets, so nothing else is affected). Still chosen from market counts only; the rule, the cuts and the verdicts are untouched.
