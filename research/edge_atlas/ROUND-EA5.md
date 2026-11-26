# Round EA-5a: is an hourly ladder ever arbitrageable inside itself? (recorded days only)

Written Sun Nov 22 2026, about 4:03 AM EST / 09:03 UTC. Follows round 4 (ROUND-EA4.md). Same rules: recorded days only, nothing waits for a future day, paper only, no order, no bot change, day-cluster intervals. Steven's bar (1:35 AM EST / 06:35 UTC): $2.60 an hour counts as edge.

## Result

**No arbitrage inside the hourly ladders, and the one place it seemed to exist is a recording artifact.** The books of the ten full-depth days (Nov 11-20) show the ladder crossed (a higher strike's YES bid above a lower strike's YES ask) for 17,796 seconds in BTC, ETH and SOL, which would lock a gain before fees. In 98 to 100% of those seconds one of the two books had not changed for over two minutes, up to 49 minutes, while the rest of the ladder kept updating; taker volume printed through the displayed quote in 9 of the 55 BTC episodes, which a live book cannot allow. Taken when it opens, one second late, or only when both books had just changed, the crossing loses after both taker fees. The best arm anywhere is $0.0095 an hour, on a quote that was probably not there.

| Coin | Seconds crossed (share of seconds with two strikes quoted) | Episodes (median / p90 / max length) | Crossed seconds where the older book was unchanged for over 120 s | Seconds with both books fresh (changed within 2 s) | Taken at the first crossed second, after both taker fees | One second later | Only episodes with fresh books, at the first second |
|---|---|---|---|---|---|---|---|
| BTC | 9,347 (1.21% of 773,392) | 55 (6 s / 283 s / 2,175 s) | 9,223 (98.7%) | 76, of which 1 net positive | -$3.92, 10 of 55 positive | -$2.57, 11 of 44 | -$1.56, 1 of 22 |
| ETH | 2,159 (0.28% of 759,610) | 20 (14.5 s / 232 s / 1,335 s) | 2,121 (98.2%) | 30, 0 net positive | -$0.55, 5 of 20 | -$0.36, 5 of 17 | -$0.27, 0 of 6 |
| SOL | 6,290 (0.83% of 755,966) | 30 (22 s / 923 s / 1,089 s) | 6,290 (100%) | 0 | -$0.09, 15 of 30 | -$0.01, 15 of 29 | none |
| XRP | 0 (248,449 two-quote seconds) | 0 | | | | | |

Dollars are for a $10 stake an episode (about 11 contracts), one take per episode, summed over the ten days (240 hours). Gap when crossed: median 7c (BTC), 4c (ETH), 3c (SOL); largest 25c (BTC). Median size on the two legs 778 (BTC), 128 (ETH), 210 (SOL) contracts.

## How it was read (python/subminute/ladder_arb.py, stage ladarb)

- A market's strikes in one hour are one ladder (same open time). At every second, for every pair of strikes i < j with both quotes standing (at least 1 contract), the gap is bid_j - ask_i. Buying YES at strike i and NO at strike j (which is selling YES j at its bid) always pays at least 1, and pays 2 when K_i <= S < K_j: a locked gain of bid_j - ask_i before fees when positive. The largest gap per second is kept.
- Fees: the exact taker fee (allpairs.fees, 0.07 C P (1 - P), rounded up, then onto the cent grid) on both legs, at the contracts the quotes show, capped at a $10 stake. No book showed a market's own bid at or above its own ask (0 seconds in all coins), so the crossing is between two markets, not inside one.
- Episodes are runs of crossed seconds. They are taken once, L seconds after the first crossed second, at that second's quotes, if still crossed (L = 0, 1, 5, 30). The fresh arm takes only episodes whose two books had both changed within 2 s of the first crossed second.
- Staleness: seconds since each market's book (best bid and ask with sizes) last changed. A trade through the quote: a taker selling YES at a price below the displayed best bid, or a taker buying YES above the displayed best ask, while that quote was displayed unchanged. Price-time priority makes both impossible against a live book.

## What the crossings are

- Concentration: BTC 4,243 s on Nov 11 and 5,028 s on Nov 12; 76 s over Nov 13-15; none on Nov 16-20. ETH 403 and 1,718 s; SOL 2,247 and 4,043 s; nothing after Nov 12 in SOL. The share of quoted market-seconds whose book was unchanged for over 120 s follows (BTC: Nov 11 1.9%, Nov 12 4.6%, at most 0.3% on the other days). A crossing that needed a standing, unwanted quote of hundreds of contracts for up to 36 minutes in the busiest of the four ladders is not a market opportunity.
- The long examples are one frozen quote against a moving one. In the longest-running BTC example (strikes 100 apart, 1,778 s) the higher strike's bid stayed at 11c with 121 contracts displayed while the best lower-strike ask fell from 10c to 1c; the older of the two books had not changed for 2,414 s by the end. Trades printed 5,989 times on the legs involved meanwhile.
- Trades through the quote: 9 of 55 BTC episodes, 10,483 contracts sold below or bought above a displayed bid or ask that never changed. Those cases prove the book was not live. In the other episodes (and in all ETH and SOL ones, where the legs barely traded) no trade tested the quote, so staleness there rests on the age of the book, not on a print.
- I did not trace why a book stops updating (the recorder or the exchange feed); the bot's recorded snapshots are not fixed by this note.

## Taken late, the stale quotes look slightly positive and are tiny

- Taken 30 s after the first crossed second, if still crossed: BTC +$2.29 over 23 episodes (15 positive; day-cluster interval -$0.14 to +$0.60), $0.0095 an hour; SOL +$0.86 over 21 (0.0036 an hour); ETH +$0.27 over 7 ($0.0011 an hour). That arm trades quotes that were stale for over two minutes, so it is a measure of how big the artifact is, not of a trade. Even at face value it is about 1/270 of the $2.60 an hour bar.
- The fresh arm (both books changed within 2 s of the crossing) loses in every coin at every delay: BTC 22 episodes at -$1.56, 12 episodes taken one second later at -$1.06 (0 positive), 4 at five seconds -$0.17, 3 at thirty seconds -$0.26.

## What it means

- Static arbitrage inside one hourly ladder: none after fees on the recorded days. The gap between a lower strike's ask and a higher strike's bid is never open on live, fresh books; at the first second it loses after two taker fees, which is the same shape as the 15-minute and hourly maker and lag results (rounds 2 to 4).
- Not tested: the bracket sums and the bracket-against-ladder identity (a range bracket pays the ladder strike below minus the ladder strike above). The hourly grids hold only the KX{BTC,ETH,SOL,XRP}D ladders; the range brackets (KXBTC 221 markets, KXETH 190, KXXRP 125 on Nov 18, 33.8k trades for BTC) would need a new reducer over the raw recordings. Their books are thinner and a 3-leg take pays three taker fees, so I expect the same null, but I have not run it.
- For any later round that treats a recorded quote as live: the share of quoted market-seconds whose book had not changed for over two minutes is 0.58% (BTC), 0.61% (ETH), 1.76% (SOL) and 2.95% (XRP), with the worst single days at 4.6% (BTC, Nov 12) and 6.7% (XRP, Nov 11). Quotes that old should be dropped or flagged. The 15-minute grids behind rounds 2 to 4 were not re-read for this; a flat quote is also what a quiet, wide market looks like, so the effect on the maker and lag results is open, not assumed.

Code: `python/subminute/ladder_arb.py` (tests in `python/subminute/tests/test_ladder_arb.py`, 37 subminute tests pass), stage `ladarb` in `.github/workflows/heat-direction.yml`; table on Drive models/subminute/ladarb (ladder_arb.json). GitHub runs 45004468170 (first pass), 45005093294 (staleness, delayed taking, fresh arm), 45005439641 (trades through the quote).
