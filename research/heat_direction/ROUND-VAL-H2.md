# H2 unseen-day looks, 2026-11-19 (research only: no order, no bot change)

Run 44625838263 (commit f908f7ea, 5:09 PM EST / 22:09 UTC). Frozen rules: PREREG-2.md (sha256 6662a8e09589b49c04de9a44cb9a612de49601cbf10ba596a0099e6e7efb1e6b),
PREREG.md and AMENDMENT-1.md. Unseen days (VAL) = 2026-07-01 to 2026-10-31 (123 days), BTC and ETH, 15-minute direction. No VAL minute had been read for H1 or H2 before this run.
Rounds file `data/rounds/rounds.json` sha256 0ccadb3e7c6a7923676dacf81ecd5f5fbede2815f8f214362efd970d90f8ce02. Both specs were rebuilt from the file and their hashes matched the DEV rounds.
The per-check tables stayed in a private Drive file until the looks stopped and were read once, after the stop. Aggregates only.

## Result: neither candidate passed (both bits 0), the looks stopped with 2 of 3 used

| look | candidate (round best) | hit | decided calls | checks passed | check 1-8 passed | primary bit | core bit | gates |
|---|---|---|---|---|---|---|---|---|
| 1 | round 1 best, hash 46d2e5a43eb8 (side fade 15) | 54.46% | 6,469 (BTC 3,402, ETH 3,067) | 7 of 10 | 7 of 8 | 0 | 0 | twin and random-side both ok |
| 2 | round 2 best, hash 1c623c9b431f (side fade 1) | 54.01% | 4,336 (BTC 2,065, ETH 2,271) | 8 of 10 | 6 of 8 | 0 | 0 | twin and random-side both ok |

No third round qualified, so the third look was not used. Looks are deterministic: re-running the same candidates repeats the same bits.
The two candidates share the same heat events and admission rules and differ only in the side rule (fade of the last 15 minutes versus the last 1 minute), so these are not two independent reads.

## Ten checks on the unseen days

| check | needs | round 1 best | round 2 best |
|---|---|---|---|
| 1 level | >= 55.0% | **54.46% fail** | **54.01% fail** |
| 2 lower bound (day-cluster bootstrap) | > 50% | 53.07% pass | 52.41% pass |
| 3 beats the best naive rule at every minute | >= +2.0 pt | +2.02 pt over fade60 (52.44%) pass | **+1.57 pt over fade60 fail** |
| 4 each coin | >= 53% | BTC 54.82 / ETH 54.06 pass | BTC 54.29 / ETH 53.76 pass |
| 5 ISO weeks above 50% | >= 65% | 93.75% (15 of 16) pass | 87.5% (14 of 16) pass |
| 6 every block (Jul, Aug, Sep, Oct) | > 50% | 54.78 / 54.48 / 54.11 / 54.47 pass | 53.86 / 54.64 / 53.34 / 54.19 pass |
| 7 UP and DOWN | >= 52% each | 54.70 / 54.37 pass | 53.03 / 54.34 pass |
| 8 one minute late | >= 53% | 54.25% pass | 53.54% pass |
| 9 TA confirms | >= +3 pt, 90% bound > 0 | **-2.77 pt fail** | +11.55 pt pass |
| 10 TA invalidates | >= +3 pt, invalidated hit <= 50% | **+2.85 pt fail** | +6.14 pt pass |

Flat share 0.37% and 0.34%. Every-minute rates on the unseen days, both coins pooled: fade1 50.53%, fade5 51.32%, fade15 51.87%, fade60 52.44%, follow1 49.47%, follow5 48.68%, follow15 48.13%, follow60 47.56%, always UP 49.87%, always DOWN 50.13%.
The bar for check 3 was fade60 at 52.44% + 2.0 = 54.44% (on DEV it had been fade15 at 52.49%).

Gates (a failure would have used no look; neither failed):
- Twins (3 per coin, no-signal copies of the same bars): hit 49.3% to 51.2%, every |z| <= 1.17, all six within bounds for both candidates.
- Random side (200 draws, same calls): 99.0% and 98.5% of draws passed at most 2 checks; mean 0.25 and 0.26 checks, max 3.

## What it says

1. H2 does not meet its own bar on unseen days. Round 1 misses check 1 (level) by 0.54 pt and also fails both TA checks; round 2 misses check 1 by 0.99 pt and check 3 by 0.43 pt. The pre-registered pass needed 9 of 10 with checks 1 to 3, or all of checks 1 to 8.
2. There is a small real timing edge. Both candidates are above 50% with day-cluster lower bounds of 52.4% to 53.1%, in both coins, both sides, 14 or 15 of 16 weeks and every month, and still 53.5% to 54.3% one minute late. The no-signal twins sit at 50%.
3. It is thinner than DEV said. Round 1 went from 55.56% on DEV to 54.46% (-1.1 pt) and round 2 from 56.06% to 54.01% (-2.1 pt). The more heavily tuned candidate lost more.
4. The edge over always fading is only about 2 points. At every minute the best naive rule scored 52.44% (fade60); the candidates beat it by +2.02 and +1.57 pt. On the same calls fade15 hits 54.46% and fade60 54.90% (round 1 calls), and fade1 54.01% and fade60 55.08% (round 2 calls): timing is what passes, the side rule adds nothing, as in H1 and on DEV. This was read after the looks stopped and was not used to choose anything.
5. The TA layer is mixed. With the fade-1 side it confirmed (+11.55 pt) and invalidated (+6.14 pt) on unseen days; with the fade-15 side it did not (-2.77, +2.85). Two candidates on the same events do not settle it either way.
6. This is direction only, on Binance bars, before any fee or contract price. Nothing here says a 54.5% call makes money on Kalshi; that is phase 2 and has not been started.

## Spent and next

The unseen days are now read for both candidates. PREREG-2.md allows no further looks (looks only for qualifying DEV rounds, at most 3, one per candidate). Any new candidate needs a new frozen pre-registration and days nobody has read: the FINAL window of whole ISO weeks after a freeze.
Steven's open question "does 8 of 8 on the core checks, with TA adding nothing, count as a pass for phase 2" did not come up: round 1 got 7 of 8 and round 2 got 6 of 8.
Note for the record: the `nondefault` tie-break counts fields that differ from the H2 start spec (Amendment 1 section 9 says round-0 spec); it only matters on exact ties.
