# OR-H3: a loser cut for Price Prediction entries (pre-registration)

Written 2026-11-06 ~17:05 UTC (12:05 PM EST), after the OR-AMEND-1 loser study and before any OR-H3 label or result exists.
Thread "Find $5 trade setups with a perfect-hindsight oracle". Registry thread `oracle-setups`, families `oracle-pp15-cut-v1`
and `oracle-pp60-cut-v1`. Never compared to paper trading. NEVER DOGE. Nothing from the lockbox (2026-11-06T05:00Z on) is read
before 2026-11-14T05:00Z.

## Why (the loser study, OR-AMEND-1 section 3)
Price Prediction 15m, every confirmed OR-H1 setup on HO-1: 68% of trades win, avg +$7.59; 32% lose, avg -$18.56 on a $20
stake. 69% of losers are sold at the final candle's bid and 31% ride to settlement; nothing cuts them earlier. Only 5% of
losers ever reached +$5, so a smaller take-profit makes things worse. Losers cluster in cheap sides (k_price 0-1), entries
right after the side's mid fell (k_dmid3/5 = -1), and spot near the strike (k_z 0-1). Discovery B looks the same.

## Hypothesis (one, falsifiable)
For Price Prediction (15-minute and hourly, separately), a loser cut (sell the side at the bid as soon as it falls a fixed
amount below the entry price), with the OR-H1 +$5 take-profit kept and optional entry filters, makes **matched random
entries** net positive after fees and beats the same entries without the cut. Falsified for a type if its frozen arm fails HO-1.
This tests an exit / filter rule applied to all entries, not a mined setup, so HO-1 is unseen for it (OR-AMEND-1 scored setups,
whose entries are a selected subset; the rule here is chosen on discovery data only).

## Arms (per type; 10 cut levels x 8 filter sets = 80 arms, plus the control)
- Cut: at decision minutes j = k+1 .. while tau_j > 60 s (the live bot cannot exit in the last 60 s), sell at the side's bid at
  the first j where bid_j <= entry ask - D. D (absolute) in {0.03, 0.05, 0.08, 0.10, 0.15, 0.20}; D (relative to the entry ask)
  in {15%, 25%, 40%}; plus "none" (the OR-H1 primary exit) = 10 levels. A take-profit check at the same minute comes first.
  After the cut window, the OR-H1 rule holds (ride if in profit, else sell at the final bid; reported also with settle).
- Filters (on the entry's own side, before entry): F1 skip k_price buckets 0-1 (side ask < 0.30); F2 skip k_dmid3 = -1;
  F3 skip k_z in {0, 1} (spot within about one sigma of the strike); all 8 subsets of {F1, F2, F3}.
- Entries: every tradable OR-H1 decision (both sides, k inside the entry window), one position at a time per asset and window,
  the first tradable decision after the previous exit. Same sizes, fees (taker both legs), books and spot features as OR-H1.

## Splits and selection
Discovery A 2026-04-18..06-14 (choose), discovery B 06-15..07-31 (confirm), HO-1 Aug 1 - Nov 4 (score once), lockbox L1
Nov 6-13 (read once after 2026-11-14T05:00Z). On A, rank the 80 arms by $/day (by-day, zeros included, pooled over assets);
keep the top 5 per type. On B, each kept arm: stationary bootstrap of daily $ (block 5 days, 2,000 draws), p_ev for mean daily
$ > 0 and p_up for (arm - control) > 0, p = max. BHY at q 0.10 over the kept arms of both types (m = 10). Freeze the best
surviving arm per type (by B $/day). No survivor = that type is falsified at discovery and nothing opens.

## HO-1 (once per type)
The frozen arm vs (a) the control (same entries, no cut, no filter) and (b) a matched placebo (8 seeds) that keeps the
arm's amount of intervention but not its information: every trade the arm cuts is instead exited at a random minute drawn
from the arm's cut-minute distribution in the same stratum (so "exit earlier" alone is not credited), and the filter set is
replaced by skipping the same number of entries at random within the same stratum and day. Registry ho1_pass: >= 90
days, >= 4 of 6 16-day folds won, worst fold >= -$0.50/h, >= 2 of 3 RV terciles with >= 100 h won, worst tercile >= -$0.50/h,
beats the placebo. Also reported (never selected on): the frozen cut applied to the 20 OR-AMEND-1 lockbox candidates, the
settle-at-close variant, +1 minute latency, +1c entry cost.

## Lockbox
A type whose frozen arm passes HO-1 is read once on L1 under OR-AMEND-1 section 2's rules (>= 4 of 7 days won, beats its
placebo). Only then may it go into the Price Prediction rulebook, with exactly this exit.

## Known limits
Kalshi history is top-of-book, 1-minute candles: a cut fills at the candle's bid, not intra-minute. A cut is a taker sale (fee
and spread paid). Live exit pacing / take-profit floors must not pre-empt this exit (tagged exit, as OR-H1 notes).
