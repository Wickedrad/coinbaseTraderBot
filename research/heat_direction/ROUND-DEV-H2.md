# H2 DEV rounds, 2026-11-19 (research only: no order, no bot change, VAL untouched)

Run 44617639923 (commit 23b1be9c, 4:19 PM EST / 21:19 UTC). Frozen rules: PREREG-2.md (sha256 6662a8e09589b49c04de9a44cb9a612de49601cbf10ba596a0099e6e7efb1e6b),
PREREG.md and AMENDMENT-1.md. Aggregates only; BTC and ETH, 15-minute direction, 2026-01-01 to 2026-06-30 (181 days), DEV folds Jan-Feb / Mar-Apr / May-Jun.
Check 3 compares with the ten naive rules at EVERY minute of DEV (every-minute rates below), not on the candidate's own calls.

Every-minute rates on DEV, both coins pooled (decided = move of at least 1.5 steps): fade1 50.59%, fade5 51.36%, fade15 52.49%, fade60 52.03%,
follow1 49.41%, follow5 48.64%, follow15 47.51%, follow60 47.97%, always UP 49.71%, always DOWN 50.29%. The bar for check 3 is fade15 at 52.49% + 2.0 = 54.49%.

## Cut test (causality), run 44617639923
Six specs per cut minute now (three H1 specs and three fade specs: the start spec, fade 60 with lag 0 and a `follows` TA layer, fade 1 with lag 1 and no TA).
BTC: 16 cuts, 0 mismatches. ETH: 16 cuts, 0 mismatches. Events equal at every cut, every call time and side equal before the cut.

## Rounds (303 trials of the 602 budget; round 4 stalled, rounds 5 and 6 did not run, stall rule of PREREG.md section 6)

| round | group | best | hit | decided calls | lower bound | checks (of 10) |
|---|---|---|---|---|---|---|
| start | H1 round-6 best, side fade 15 (calibration, never sent to VAL) | top 5, share A/B >= 54, lag 2, TA precedes 5/5 | 55.62% | 10,035 | 54.61% | 8 (checks 9, 10 fail) |
| 1 | admission (240) | start with min_n_B 10,000 | 55.56% | 9,097 | 54.47% | 9 (check 10 fails) |
| 2 | side rule (5) | start with min_n_B 10,000 and fade_k 1 | 56.06% | 5,890 | 54.78% | **10** |
| 3 | TA layer (55) | no change | 56.06% | 5,890 | 54.78% | 10 |
| 4 | entry delay (3), stalled | no change | 56.06% | 5,890 | 54.78% | 10 |

Round 2 best (hash 1c623c9b431f): all four bars (1m 5m 15m 60m), top_n 5, share A >= 54, share B >= 54, min_n_B 10,000, hottest, lag 2, side fade of the last 1 minute,
TA precedes (conf 5, inv 5, pool 20), lockout 15. About 33 calls a day.
Its ten checks on DEV: 1 level 56.06% pass; 2 lower bound 54.78% pass; **3 beats the best naive rule every minute: +3.57 pt over fade15 (52.49%), needs +2.0, pass**;
4 BTC 56.50% / ETH 55.65% pass; 5 weeks 92% pass; 6 folds 56.7 / 55.8 / 55.7 pass; 7 UP 55.1 / DOWN 56.4 pass; 8 one minute late 55.24% pass;
9 TA confirms +6.05 pt pass; 10 TA invalidates +9.11 pt pass. Flat share 0.14%.
Round 1 best (hash 46d2e5a43eb8): the start with min_n_B 10,000, fade 15. Checks 1 to 9 pass (check 3 +3.06 pt), check 10 fails (+1.8 pt, needs +3.0 and invalidated hit <= 50%).

## What it says
1. The timing is what passes. On the same calls fade15 hits 56.10% and fade1 56.06%: the side rule adds nothing over fading the last move, as in H1. Against the same rule at an arbitrary
   minute (52.49% for fade15, 50.59% for fade1) the admitted heat events are worth +3.6 to +5.5 points on DEV.
2. TA, which added nothing in H1, now confirms (+6.05 pt) and invalidates (+9.11 pt) on DEV, because the fade side is one the pool events can agree or disagree with. Both pass on the same
   calls the candidate was tuned on, so this is the most selection-exposed part of the result.
3. DEV is optimistic by an unknown amount: 303 trials selected on these 181 days (the start spec itself came from the H1 DEV search). Nothing here is a result on unseen days.
4. Per PREREG-2.md section 3 item 3 two rounds qualify for an unseen-day look (eligible, strictly better than the round's start, all of checks 1 to 8 on DEV): round 1's best, then
   round 2's best. Rounds 3 and 4 did not improve. Looks go in round order, stop at the first look where either bit is 1, at most 3.

## Next (no VAL minute has been read for H1 or H2)
Build the unseen-day event files (`vevents`, real coin and three twins per coin), then `looks`. The per-check VAL table goes to a private Drive file and is read once, when the looks stop.
