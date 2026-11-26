# Heat map direction loop, phase 1, second test (H2): heat events as timing, the fade of the last move as the side

Written 2026-11-19, after Steven chose "Pre-register a timing plus fade test" on the decision card (21:09 UTC / 4:09 PM EST), before any H2 candidate is scored and before any VAL minute is read for H2. Research only: no bot change, no order, tap and live stay off. PREREG.md and AMENDMENT-1.md stay in force except where this file says otherwise.

## 1. What H1 found (DEV only, research/heat_direction/ROUND-DEV.md)

- H1 (the heat map's own side) stalled on DEV: best 8 of 10, 55.45% on 10,336 calls, but it fails required check 3 because on the same calls "fade the last 15-minute move" hits 55.16%. The heat side is the fade side on about 95% of admitted calls.
- Fading the last 15-minute move at ANY minute of DEV hits 52.2% (BTC) and 52.8% (ETH); month by month 50.6 to 53.5% in all 26 coin-months of 2025-06 to 2026-06 (warm-up months were read for this baseline only).
- The tuned admission (top 5 levels, cross-year shares >= 54) lifts the fade to 55.2 to 55.5%: about +3 points of timing over an arbitrary minute. TA that precedes the call confirmed it by 6 to 8 points; TA invalidation added 0.
- H1 was closed without the stall-time VAL read its stop rule allowed (PREREG.md section 6), at Steven's choice, so VAL stays unspent for H2. No H1 look was taken.

## 2. H2 and the call

H2: at the minutes when an admitted heat level fires, the next 15 minutes move AGAINST the last k-minute move more often than at an arbitrary minute, by at least 2.0 points, and at 55.0% or better on held-out days.

- Event, admission, lockout (15 min per coin), lag, TA layer, 15-minute move, flat band (1.5 steps), hit rate, coins (BTC and ETH): exactly as PREREG.md section 2 and AMENDMENT-1.md.
- New field `side` ('heat' = H1, or 'fade') and `fade_k` (1, 5, 15 or 60). With `side = fade` the call at entry row e = event row + lag has side = minus the sign of round((open[e] - open[e-k]) / step). A zero sign makes no call and starts no lockout. The combiner is 'hottest' (the events only time the call). Causality is unchanged: open[e] is the open of the entry minute and open[e-k] is older; the cut test is re-run with a fade spec.
- `follows` TA: the side is the fade side at the base event and is kept for the call made at the confirmation minute.

## 3. What changes from PREREG.md, and what does not

Same: the ten checks and thresholds, floors, bootstrap (2,000 resamples, seed 20261119), pass = 9 of 10 with checks 1, 2, 3 among them, flat-share guard, twin gate (seeds as in Amendment 1) and random-side gate, DEV folds, VAL blocks (calendar months), FINAL (one fixed window of whole ISO weeks from the first Monday after the freeze, at least 8 and at most 16 weeks, hashes verified, evaluated once), the eligibility floor (800 decided calls, 300 per coin), the selection order (most checks, larger check-2 bound, fewer non-default fields, smaller hash).

Changed:
1. Check 3 comparator (side = fade only). The naive rules are scored at EVERY minute of the scored window, both coins pooled: follow/fade of the last 1, 5, 15 and 60 minute move, always UP, always DOWN, each over every minute with a decided outcome (and a nonzero past move for the move rules). Pass when hit rate minus the best of the ten >= 2.0 points. Reason: on the same calls the side rule is compared with itself and the timing is invisible; H2 is about the timing. For `side = heat` the old comparator (same calls) stays.
2. Two bits per VAL look: primary = pass (9 or more including checks 1, 2, 3, and the twin and random-side gates); secondary = core 8 (checks 1 to 8 all pass, same gates), "a direction edge on unseen days with TA adding nothing". Steven's open question (does 8 of 8 core count?) stays open; both bits are reported, the primary is the pre-registered pass.
3. A round's best goes to VAL only if it is eligible, strictly better than the round's start, AND passes the core 8 on DEV (all of checks 1 to 8). Looks in round order, at most 3, one per candidate, stop at the first look where either bit is 1. If no round qualifies there is no look and H2 stalls on DEV. The per-check VAL table goes to a private Drive file and is read once, when the looks stop.
4. Budget: 602 DEV trials (below). Trials so far in the project: H1 604, H2 602, all printed beside any pass.

## 4. Search (scripted, DEV only, coordinate descent, same machinery as H1)

Start (calibration, never sent to VAL): the H1 round-6 best spec with `side = fade`, `fade_k = 15`: tfs 1m 5m 15m 60m, top_n 5, share A >= 54, share B >= 54, min_n_B 0, hottest, lag 2, TA precedes (conf 5, inv 5, pool 20), lockout 15.
Rounds: 1 admission (top_n {5,10,20,40,80} x min share A {0,52,53,54} x min share B {0,52,53,54} x min_n_B {0,5000,10000} = 240); 2 side rule (heat, fade 1, fade 5, fade 15, fade 60 = 5); 3 TA layer (the 55 of H1); 4 entry delay {0,1,2}; 5 reading bars (the 4 of H1); 6 admission then TA once more (240 + 55 = 295). Stall rule as in PREREG.md section 6.

## 5. Evidence limits stated now

- H2 was formed from DEV numbers and from baseline numbers of the warm-up months. No VAL minute (2026-07-01 to 2026-10-31) has been read for H2 or H1. The project has seen the Aug to Oct 2026 verdicts of other tests (PREREG.md section 4).
- 602 DEV trials select on DEV, so DEV hit rates are optimistic by an unknown amount (H1: 52.45 to 55.45 over its rounds).
- Power, in words: a pass needs the VAL fade at admitted events near 55% while the every-minute fade stays near 52.5%. If the DEV timing gain of +3 points shrinks by a third on VAL the gap is 2.0, the edge of check 3, so the core-8 bit is roughly a coin flip at best; the primary bit also needs TA invalidation to work, which DEV says it does not. A negative result is likely and will be reported as such.
- Passing is necessary for a profit, not sufficient: the Kalshi quote is the real competitor and fees and exits are phase 2.
