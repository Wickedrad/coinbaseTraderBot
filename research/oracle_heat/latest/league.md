# OR-HM1 heat map: league (coin price, discovery only)

Coins: BTC, ETH, SOL, XRP. No-signal twins: BTC~twin1, BTC~twin2, BTC~twin3, ETH~twin1, ETH~twin2, ETH~twin3, SOL~twin1, SOL~twin2, SOL~twin3, XRP~twin1, XRP~twin2, XRP~twin3.
Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute's open. A map, not a validated rule.

## Hot spots against chance

Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent's other events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest set, a higher replicate share and the BHY column are evidence.

| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |
|---|---|---|---|---|---|---|---|---|---|---|
| real | single | 98,630 | 10,551 | 2,204 | 0.2089 | 437 | 37,753 | 17,703 | 0.4689 | 12,421 |
| real | curve | 195,915 | 19,645 | 3,408 | 0.1735 |  | 64,827 | 29,806 | 0.4598 |  |
| real | pair | 12,371,530 | 461,004 | 34,402 | 0.0746 | 0 | 1,364,921 | 173,889 | 0.1274 | 1,015 |
| real | triple | 3,625,605 | 200,467 | 15,009 | 0.0749 | 0 | 551,147 | 79,897 | 0.145 | 66 |
| twin (median of 3) | single | 98,500 | 93 (76 to 175) | 1 (0 to 4) | 0.0132 | 0 | 218 (181 to 219) | 4 (2 to 7) | 0.0183 | 0 |
| twin (median of 3) | curve | 195,585 | 167 (143 to 395) | 6 (3 to 9) | 0.0228 |  | 312 (298 to 367) | 7 (5 to 11) | 0.0224 |  |
| twin (median of 3) | pair | 11,044,755 | 16,514 (12,605 to 16,844) | 69 (51 to 73) | 0.0042 | 0 | 35,754 (33,700 to 35,769) | 240 (208 to 351) | 0.0071 | 0 |
| twin (median of 3) | triple | 758,565 | 1,726 (1,090 to 2,187) | 1 (1 to 2) | 0.0009 | 0 | 5,389 (4,174 to 6,020) | 20 (5 to 26) | 0.0037 | 0 |

Not every hot relationship was written (the weakest by lift were left out); they are counted in the BHY family as failures: 0:pair 8,369.

Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): move_heat 41.661, move_edge 30.564, odds_edge 18.315, odds_heat 34.778.

## Direction: every event level, nothing cut (Amendment 3)

The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods (30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.

| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |
|---|---|---|---|---|---|---|---|---|
| 1 | real | 19,055 | 0.7015 | 0.2834 | 1.202 | 139.951 | 649.423 | 0.836 |
| 1 | twin | 57,046 | 0.5015 | 0.0232 | 0.003 | 27.671 | 84.809 | 0.314 |
| 5 | real | 19,055 | 0.7685 | 0.3496 | 1.725 | 103.052 | 222.867 | 1.046 |
| 5 | twin | 57,046 | 0.4977 | 0.0214 | -0.007 | 25.754 | 75.216 | 0.316 |
| 15 | real | 19,055 | 0.792 | 0.3791 | 2.052 | 88.039 | 162.974 | 1.018 |
| 15 | twin | 57,046 | 0.5038 | 0.0225 | 0.008 | 20.988 | 57.783 | 0.313 |
| 30 | real | 19,055 | 0.7775 | 0.3272 | 1.689 | 68.692 | 120.813 | 1.024 |
| 30 | twin | 57,046 | 0.4992 | 0.022 | -0.002 | 16.514 | 43.287 | 0.314 |
| 60 | real | 19,055 | 0.7586 | 0.2459 | 1.286 | 40.824 | 65.295 | 1.012 |
| 60 | twin | 57,046 | 0.4967 | 0.0232 | -0.007 | 13.27 | 30.881 | 0.315 |

Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.

Top 12 at 1 minute by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 1m:IBS=very high | up | 177.69 | 47.6 | 48.2 | +1.6 | +3.7 | +17.9 | 649.4 | 7.9 | +0.4 | +2.5 | -1.9 | hot, replicates, BHY |
| BTC | 1m:IBS=very low | down | 173.46 | 47.8 | 47.7 | +1.3 | +3.5 | +17.6 | 613.8 | 7.8 | +0.3 | +2.4 | -1.9 | hot, replicates, BHY |
| BTC | 1m:C-AVGPRICE sign=below 0 | down | 351.66 | 49.2 | 48.3 | +1.8 | +1.7 | +11.6 | 607.4 | 7.8 | +0.3 | +3.1 | -2.9 | hot, replicates, BHY |
| BTC | 1m:C-WCLPRICE sign=below 0 | down | 352.44 | 48.9 | 48.3 | +1.8 | +1.7 | +10.9 | 591.2 | 7.8 | +0.3 | +3.1 | -2.9 | hot, replicates, BHY |
| BTC | 1m:C-MEDPRICE sign=below 0 | down | 352.44 | 48.9 | 48.3 | +1.8 | +1.7 | +10.9 | 591.2 | 7.8 | +0.3 | +3.1 | -2.9 | hot, replicates, BHY |
| BTC | 1m:C-TYPPRICE sign=below 0 | down | 352.44 | 48.9 | 48.3 | +1.8 | +1.7 | +10.9 | 591.2 | 7.8 | +0.3 | +3.1 | -2.9 | hot, replicates, BHY |
| BTC | 1m:CDL:CLOSINGMARUBOZU=bull | up | 203.81 | 48.6 | 49.4 | +2.8 | +2.7 | +12.3 | 554.8 | 8.1 | +0.6 | +3.0 | -2.5 | hot, replicates, BHY |
| BTC | 1m:C-TYPPRICE sign=above 0 | up | 352.44 | 48.5 | 48.2 | +1.6 | +1.5 | +9.5 | 521.0 | 7.8 | +0.3 | +3.1 | -2.9 | none |
| BTC | 1m:C-WCLPRICE sign=above 0 | up | 352.44 | 48.5 | 48.2 | +1.6 | +1.5 | +9.5 | 521.0 | 7.8 | +0.3 | +3.1 | -2.9 | none |
| BTC | 1m:C-MEDPRICE sign=above 0 | up | 352.44 | 48.5 | 48.2 | +1.6 | +1.5 | +9.5 | 521.0 | 7.8 | +0.3 | +3.1 | -2.9 | none |
| BTC | 1m:C-AVGPRICE sign=above 0 | up | 351.66 | 48.8 | 48.2 | +1.6 | +1.5 | +9.3 | 517.5 | 7.8 | +0.3 | +3.1 | -2.9 | hot, replicates, BHY |
| BTC | 1m:BOP sign=below 0 | down | 340.44 | 49.7 | 48.6 | +2.1 | +1.5 | +10.1 | 516.2 | 7.8 | +0.3 | +3.2 | -2.9 | hot, replicates, BHY |

Top 8 at 1 minute by share right over base on B (at least 0.2 windows per day; the best twin level reaches 21.79 points, the 99th percentile 8.33):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | 60m:C-SMA20=high (cooling) | up | 0.21 | 75 | 69.3 | +23.1 | +3.9 | 11.8 | +4.8 | -8.2 | hot, replicates, BHY |
| XRP | 60m:C-TRIMA20=high (cooling) | up | 0.20 | 74 | 68.9 | +22.7 | +3.7 | 13.3 | +6.2 | -7.0 | hot, replicates, BHY |
| XRP | 60m:IMI14=high (cooling) | up | 0.20 | 74 | 68.9 | +22.7 | +4.5 | 10.6 | +3.5 | -5.8 | hot, replicates, BHY |
| XRP | 60m:CMOU14=high (cooling) | up | 0.20 | 74 | 68.9 | +22.7 | +4.6 | 10.9 | +3.8 | -5.8 | hot, replicates, BHY |
| BTC | 60m:ERIbull13=very high | up | 0.20 | 73 | 68.5 | +21.9 | +3.2 | 14.4 | +6.9 | -3.4 | hot, replicates, BHY |
| SOL | 60m:PSO=low (recovering) | down | 0.22 | 79 | 65.8 | +21.1 | +3.4 | 12.5 | +5.7 | -5.7 | none |
| XRP | 60m:C-MIDPRICE14=high (cooling) | up | 0.22 | 79 | 67.1 | +20.9 | +3.3 | 12.7 | +5.7 | -6.9 | hot, replicates, BHY |
| BTC | 60m:CCI14=very low | down | 0.30 | 108 | 66.7 | +20.2 | +3.7 | 11.5 | +4.0 | -4.8 | hot, replicates, BHY |

Top 12 at 5 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 1m:IBS=very high | up | 148.30 | 50.5 | 50.8 | +1.3 | +1.5 | +8.7 | 222.9 | 7.9 | +0.4 | +6.5 | -2.5 | hot, replicates, BHY |
| ETH | 1m:AROONdn14=very high | up | 83.90 | 51.9 | 52.5 | +2.6 | +2.6 | +10.0 | 214.9 | 8.7 | +1.0 | +14.2 | -8.0 | hot, replicates, BHY |
| BTC | 1m:C-TYPPRICE sign=below 0 | down | 254.30 | 49.9 | 50.7 | +0.9 | +0.8 | +8.1 | 211.6 | 7.8 | +0.3 | +8.2 | -3.6 | hot, replicates, BHY |
| BTC | 1m:C-MEDPRICE sign=below 0 | down | 254.30 | 49.9 | 50.7 | +0.9 | +0.8 | +8.1 | 211.6 | 7.8 | +0.3 | +8.2 | -3.6 | hot, replicates, BHY |
| BTC | 1m:C-WCLPRICE sign=below 0 | down | 254.30 | 49.9 | 50.7 | +0.9 | +0.8 | +8.1 | 211.6 | 7.8 | +0.3 | +8.2 | -3.6 | hot, replicates, BHY |
| BTC | 1m:C-AVGPRICE sign=below 0 | down | 254.16 | 49.9 | 50.7 | +0.8 | +0.8 | +8.1 | 207.8 | 7.8 | +0.3 | +8.2 | -3.6 | hot, replicates, BHY |
| BTC | 1m:IBS=very low | down | 144.44 | 50.3 | 51.0 | +1.1 | +1.4 | +7.3 | 198.8 | 7.8 | +0.3 | +6.3 | -2.4 | hot, replicates, BHY |
| ETH | 1m:C-SUPERTREND10/3=low (falling in) | up | 63.74 | 52.6 | 52.9 | +3.0 | +3.0 | +9.6 | 190.8 | 8.8 | +1.0 | +13.9 | -8.0 | hot, replicates, BHY |
| BTC | 1m:BOP sign=below 0 | down | 249.33 | 50.0 | 50.7 | +0.8 | +0.8 | +7.2 | 188.3 | 7.8 | +0.3 | +8.3 | -3.7 | hot, replicates, BHY |
| BTC | 1m:BarBody sign=below 0 | down | 249.33 | 50.0 | 50.7 | +0.8 | +0.8 | +7.2 | 188.3 | 7.8 | +0.3 | +8.3 | -3.7 | hot, replicates, BHY |
| ETH | 1m:AROONdn25=very high | up | 59.30 | 52.9 | 53.0 | +3.1 | +3.1 | +10.2 | 183.8 | 9.0 | +1.2 | +14.9 | -8.7 | hot, replicates, BHY |
| ETH | 1m:AROONup25=very high | down | 60.83 | 52.3 | 52.6 | +2.9 | +2.9 | +9.5 | 178.2 | 8.8 | +1.3 | +13.6 | -7.8 | none |

Top 8 at 5 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 21.57 points, the 99th percentile 7.25):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | 60m:AROONOSC25=low (falling in) | up | 0.23 | 84 | 72.6 | +22.7 | +4.5 | 11.5 | +3.7 | -11.5 | none |
| XRP | 60m:C-RMA14=very low | up | 0.26 | 96 | 68.8 | +20.5 | +3.9 | 16.9 | +9.8 | -18.6 | none |
| XRP | 60m:C-MEDIAN30=very low | up | 0.21 | 75 | 68.0 | +19.8 | +3.3 | 16.6 | +9.5 | -20.3 | hot, replicates, BHY |
| XRP | 60m:C-VIDYA12=very low | up | 0.33 | 119 | 67.2 | +19.0 | +4.1 | 14.8 | +7.8 | -18.6 | hot, replicates, BHY |
| XRP | 15m:TSI=low (recovering) | down | 0.27 | 97 | 67.0 | +18.5 | +3.6 | 10.0 | +3.0 | -13.2 | none |
| XRP | 60m:C-TRIMA20=very low | up | 0.22 | 81 | 66.7 | +18.4 | +3.1 | 17.0 | +9.9 | -21.1 | none |
| XRP | 60m:C-EMA9=very low | up | 0.33 | 120 | 65.8 | +17.6 | +3.6 | 16.1 | +9.1 | -18.8 | none |
| XRP | 60m:C-SWAK_BUTTER20=very low | up | 0.32 | 117 | 65.8 | +17.6 | +3.8 | 15.9 | +8.9 | -21.7 | none |

Top 12 at 15 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | 1m:AROONup14=very high | down | 58.61 | 51.8 | 52.2 | +2.8 | +2.8 | +9.9 | 163.0 | 8.4 | +0.9 | +24.1 | -10.7 | hot, replicates, BHY |
| ETH | 1m:AROONup25=very high | down | 42.47 | 52.9 | 53.1 | +3.7 | +3.7 | +10.5 | 158.9 | 8.8 | +1.3 | +24.1 | -11.1 | hot, replicates, BHY |
| ETH | 1m:C-VIDYA12=high (rising in) | down | 30.05 | 54.0 | 54.4 | +5.0 | +5.0 | +11.2 | 150.1 | 9.1 | +1.6 | +22.8 | -10.6 | none |
| ETH | 1m:C-SUPERTREND10/3=high (rising in) | down | 45.13 | 52.3 | 52.7 | +3.3 | +3.3 | +10.1 | 149.7 | 8.4 | +0.9 | +23.3 | -10.4 | hot, replicates, BHY |
| ETH | 1m:AROONdn14=very high | up | 57.75 | 52.8 | 52.8 | +2.5 | +2.5 | +8.6 | 143.1 | 8.7 | +1.0 | +25.3 | -11.5 | hot, replicates, BHY |
| ETH | 1m:RSI7=high (rising in) | down | 36.78 | 52.8 | 53.2 | +3.8 | +3.8 | +9.4 | 138.9 | 9.0 | +1.5 | +24.0 | -11.1 | hot, replicates, BHY |
| ETH | 1m:RSI14=high (rising in) | down | 27.47 | 54.0 | 54.5 | +5.1 | +5.0 | +10.5 | 138.5 | 9.3 | +1.7 | +24.1 | -11.3 | hot, replicates, BHY |
| ETH | 1m:CMO14=high (rising in) | down | 27.47 | 54.0 | 54.5 | +5.1 | +5.0 | +10.5 | 138.5 | 9.3 | +1.7 | +24.1 | -11.3 | hot, replicates, BHY |
| ETH | 1m:C-RMA14=high (rising in) | down | 28.38 | 53.9 | 54.2 | +4.8 | +4.8 | +10.3 | 136.3 | 9.0 | +1.5 | +22.7 | -10.6 | hot, replicates, BHY |
| ETH | 1m:C-MCGD14=high (rising in) | down | 28.17 | 54.0 | 54.1 | +4.7 | +4.7 | +10.0 | 132.9 | 9.1 | +1.6 | +22.6 | -10.6 | hot, replicates, BHY |
| SOL | 1m:AROONup25=very high | down | 43.93 | 47.7 | 51.7 | +3.0 | +3.0 | +9.0 | 131.9 | 7.6 | +0.8 | +30.2 | -13.0 | hot, replicates, BHY |
| ETH | 1m:AROONup14=very low | up | 62.32 | 52.2 | 52.5 | +2.1 | +2.1 | +8.8 | 131.8 | 8.4 | +0.6 | +25.0 | -10.9 | hot, replicates, BHY |

Top 8 at 15 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 22.19 points, the 99th percentile 7.0):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | 60m:ACCBANDS20pos=very low | up | 0.26 | 96 | 69.8 | +20.8 | +4.5 | 12.5 | +5.7 | -29.3 | none |
| BTC | 60m:C-EMA50=very low | up | 0.20 | 73 | 69.9 | +20.0 | +3.3 | 12.2 | +4.7 | -17.7 | hot, replicates, BHY |
| SOL | 60m:RSI21=very low | up | 0.20 | 74 | 68.9 | +20.0 | +3.5 | 13.3 | +6.4 | -35.0 | none |
| ETH | 60m:STOCHK14=very high | down | 0.27 | 100 | 69.0 | +19.6 | +4.1 | 14.2 | +6.7 | -10.8 | none |
| ETH | 60m:CCI20=very low | up | 0.26 | 94 | 69.1 | +18.8 | +3.9 | 12.0 | +4.2 | -26.1 | none |
| XRP | 60m:IBS=very high | down | 0.35 | 128 | 68.0 | +18.7 | +4.2 | 16.6 | +9.6 | -10.7 | none |
| ETH | 60m:C-VIDYA12=very low | up | 0.23 | 84 | 69.0 | +18.7 | +3.5 | 9.8 | +2.0 | -31.7 | none |
| ETH | 60m:C-MCGD14=very low | up | 0.22 | 80 | 68.8 | +18.4 | +3.5 | 13.3 | +5.6 | -26.4 | none |

Top 12 at 30 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | 1m:AROONup25=very high | down | 31.67 | 53.1 | 52.9 | +3.8 | +3.8 | +10.0 | 120.8 | 8.8 | +1.3 | +34.8 | -14.6 | hot, replicates, BHY |
| ETH | 1m:RSI14=high (rising in) | down | 21.53 | 53.9 | 54.2 | +5.1 | +5.1 | +9.9 | 109.3 | 9.3 | +1.7 | +34.8 | -14.8 | hot, replicates, BHY |
| ETH | 1m:CMO14=high (rising in) | down | 21.53 | 53.9 | 54.2 | +5.1 | +5.1 | +9.9 | 109.3 | 9.3 | +1.7 | +34.8 | -14.8 | hot, replicates, BHY |
| ETH | 1m:ERIbull13=high (rising in) | down | 27.10 | 53.0 | 53.1 | +4.0 | +4.0 | +9.4 | 108.1 | 8.9 | +1.4 | +33.3 | -13.9 | hot, replicates, BHY |
| ETH | 1m:KC20pos=high (rising in) | down | 24.90 | 53.4 | 53.4 | +4.3 | +4.3 | +9.6 | 105.9 | 8.8 | +1.3 | +32.7 | -13.7 | hot, replicates, BHY |
| ETH | 1m:C-VIDYA12=high (rising in) | down | 22.45 | 54.0 | 53.8 | +4.7 | +4.7 | +9.5 | 105.6 | 9.1 | +1.6 | +33.0 | -14.2 | hot, replicates, BHY |
| ETH | 1m:RSI7=high (rising in) | down | 28.51 | 52.9 | 52.8 | +3.6 | +3.6 | +8.8 | 103.4 | 9.0 | +1.5 | +34.6 | -14.6 | hot, replicates, BHY |
| ETH | 1m:AROONup14=very high | down | 40.48 | 51.9 | 51.7 | +2.5 | +2.5 | +9.3 | 102.2 | 8.4 | +0.9 | +35.0 | -14.2 | hot, replicates, BHY |
| ETH | 1m:C-SMA50=high (rising in) | down | 16.26 | 54.6 | 55.4 | +6.2 | +6.2 | +9.3 | 100.9 | 9.2 | +1.7 | +33.8 | -14.4 | hot, replicates, BHY |
| ETH | 1m:AROONdn14=very high | up | 40.11 | 53.3 | 53.2 | +2.5 | +2.5 | +8.8 | 100.9 | 8.7 | +1.0 | +36.4 | -15.5 | hot, replicates, BHY |
| ETH | 1m:CCI20=high (rising in) | down | 28.06 | 52.4 | 52.7 | +3.6 | +3.6 | +9.1 | 100.7 | 8.4 | +0.9 | +34.6 | -14.6 | hot, replicates, BHY |
| ETH | 1m:C-RMA14=high (rising in) | down | 22.05 | 54.0 | 53.7 | +4.6 | +4.5 | +9.0 | 100.3 | 9.0 | +1.5 | +32.8 | -14.0 | hot, replicates, BHY |

Top 8 at 30 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 19.11 points, the 99th percentile 6.93):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 15m:BarBody=high (cooling) | down | 0.25 | 92 | 70.7 | +20.9 | +4.4 | 10.1 | +2.7 | -15.3 | none |
| XRP | 60m:C-SWAK_BUTTER20=very low | up | 0.32 | 117 | 69.2 | +19.9 | +4.2 | 15.9 | +8.9 | -44.4 | hot, replicates, BHY |
| XRP | 60m:C-TRIMA20=very low | up | 0.22 | 81 | 69.1 | +19.8 | +3.6 | 17.0 | +9.9 | -48.5 | none |
| XRP | 60m:C-SAR=very low | up | 0.23 | 84 | 69.0 | +19.7 | +3.9 | 16.5 | +9.5 | -33.9 | hot, replicates, BHY |
| XRP | 60m:CCI14=very low | up | 0.32 | 116 | 69.0 | +19.6 | +4.5 | 11.0 | +3.9 | -42.0 | hot, replicates, BHY |
| XRP | 60m:ACCBANDS20pos=very low | up | 0.23 | 85 | 68.2 | +18.9 | +3.2 | 14.2 | +7.1 | -27.9 | hot, replicates, BHY |
| XRP | 60m:C-MEDIAN30=very low | up | 0.21 | 75 | 68.0 | +18.6 | +3.2 | 16.6 | +9.5 | -28.7 | hot, replicates, BHY |
| SOL | 60m:C-MEDIAN30=very low | up | 0.21 | 75 | 68.0 | +18.4 | +3.7 | 11.3 | +4.4 | -36.9 | none |

Top 12 at 60 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | 1m:AROONup25=very high | down | 21.14 | 51.7 | 51.8 | +3.1 | +3.1 | +8.4 | 65.3 | 8.8 | +1.3 | +51.0 | -19.9 | hot, replicates, BHY |
| ETH | 1m:ERIbull13=high (rising in) | down | 19.22 | 51.8 | 52.0 | +3.3 | +3.3 | +7.4 | 64.0 | 8.9 | +1.4 | +48.8 | -19.0 | hot, replicates, BHY |
| ETH | 1m:RSI14=high (rising in) | down | 15.99 | 52.4 | 52.5 | +3.9 | +3.9 | +7.0 | 62.0 | 9.3 | +1.7 | +50.1 | -20.0 | hot, replicates, BHY |
| ETH | 1m:CMO14=high (rising in) | down | 15.99 | 52.4 | 52.5 | +3.9 | +3.9 | +7.0 | 62.0 | 9.3 | +1.7 | +50.1 | -20.0 | hot, replicates, BHY |
| ETH | 1m:KC20pos=high (rising in) | down | 17.94 | 52.0 | 52.1 | +3.4 | +3.4 | +7.4 | 60.7 | 8.8 | +1.3 | +47.6 | -19.0 | hot, replicates, BHY |
| ETH | 1m:PERCENTB20/2=low (falling in) | up | 20.25 | 53.4 | 54.2 | +3.0 | +3.0 | +7.3 | 60.3 | 8.5 | +0.7 | +52.5 | -22.5 | hot, replicates, BHY |
| ETH | 1m:PERCENTB20/2.5=low (falling in) | up | 20.25 | 53.4 | 54.2 | +3.0 | +3.0 | +7.3 | 60.3 | 8.5 | +0.7 | +52.5 | -22.5 | hot, replicates, BHY |
| ETH | 1m:ZSCORE20=low (falling in) | up | 20.25 | 53.4 | 54.2 | +3.0 | +3.0 | +7.3 | 60.3 | 8.5 | +0.7 | +52.5 | -22.5 | hot, replicates, BHY |
| ETH | 1m:ZSCORE20=very high | down | 13.00 | 52.1 | 53.3 | +4.6 | +4.6 | +7.4 | 59.6 | 10.1 | +2.6 | +53.6 | -22.1 | hot, replicates, BHY |
| ETH | 1m:PERCENTB20/2=very high | down | 13.00 | 52.1 | 53.3 | +4.6 | +4.6 | +7.4 | 59.6 | 10.1 | +2.6 | +53.6 | -22.1 | hot, replicates, BHY |
| ETH | 1m:PERCENTB20/2.5=very high | down | 13.00 | 52.1 | 53.3 | +4.6 | +4.6 | +7.4 | 59.6 | 10.1 | +2.6 | +53.6 | -22.1 | hot, replicates, BHY |
| ETH | 1m:DONCHIAN20pos=very high | down | 15.00 | 51.9 | 52.6 | +3.9 | +4.0 | +7.4 | 59.3 | 10.1 | +2.6 | +51.1 | -21.0 | hot, replicates, BHY |

Top 8 at 60 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 17.21 points, the 99th percentile 7.15):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 60m:WILLR14=high (cooling) | down | 0.34 | 125 | 68.0 | +18.6 | +4.5 | 9.8 | +2.3 | -13.5 | hot, replicates, BHY |
| XRP | 15m:COPPOCK=very high | down | 0.30 | 111 | 64.9 | +15.3 | +3.7 | 10.5 | +3.5 | -31.3 | hot, replicates, BHY |
| ETH | 60m:STOCHK5=high (cooling) | down | 0.26 | 94 | 63.8 | +15.2 | +3.1 | 8.6 | +1.1 | -18.7 | none |
| ETH | 60m:C-SAR=low (recovering) | down | 0.20 | 74 | 63.5 | +14.8 | +2.6 | 13.5 | +6.0 | -24.5 | none |
| XRP | 60m:STOCHK5=high (cooling) | down | 0.25 | 92 | 64.1 | +14.5 | +3.0 | 10.6 | +3.6 | -20.0 | none |
| BTC | 60m:AO=high (rising in) | down | 0.24 | 86 | 64.0 | +14.5 | +2.9 | 9.8 | +2.3 | -15.0 | none |
| BTC | 15m:TRIX15=low (recovering) | down | 0.22 | 83 | 63.9 | +14.4 | +2.6 | 9.2 | +1.7 | -14.5 | none |
| BTC | 1m:CDL:RISEFALL3METHODS=bull | down | 0.21 | 80 | 63.7 | +14.3 | +2.3 | 9.5 | +2.0 | -15.0 | none |

## Every TA by heat

Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the direction the reading's current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). The horizon is the one with the most heat on A; the B columns score A's directions on B, so a reading with no information scores about zero.

| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |
|---|---|---|---|---|---|---|---|---|
| real | curve | 2,480 | 0.6859 | 0.2302 | 0.125 | 4.748 | 33.745 | 188.993 |
| twin | curve | 7,259 | 0.5381 | 0.0343 | 0.0037 | 0.521 | 21.007 | 54.404 |
| real | events | 3,235 | 0.6665 | 0.1641 | 0.0689 | 4.14 | 58.528 | 185.895 |
| twin | events | 9,413 | 0.5451 | 0.0411 | 0.0038 | 0.822 | 33.398 | 117.711 |

Top 40 readings by curve heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| BTC | 1m:IBS | 1 | 148.0 | +189.0 | +16.0 |
| BTC | 1m:C-TYPPRICE | 1 | 148.3 | +174.7 | +14.7 |
| BTC | 1m:C-MEDPRICE | 1 | 148.3 | +174.7 | +14.7 |
| BTC | 1m:C-WCLPRICE | 1 | 148.3 | +174.7 | +14.7 |
| BTC | 1m:C-AVGPRICE | 1 | 154.5 | +162.3 | +13.1 |
| BTC | 1m:BOP | 1 | 145.1 | +145.4 | +12.1 |
| BTC | 1m:CRSI | 1 | 172.9 | +144.2 | +11.9 |
| BTC | 1m:SI | 1 | 112.4 | +137.6 | +11.8 |
| ETH | 1m:IBS | 1 | 103.7 | +134.7 | +13.4 |
| BTC | 1m:BarBody | 1 | 123.9 | +132.7 | +10.8 |
| BTC | 1m:STOCHFK5 | 1 | 100.6 | +122.4 | +10.6 |
| BTC | 1m:SWAK_2PHP20 | 1 | 134.5 | +121.9 | +10.2 |
| BTC | 1m:RSI2 | 1 | 135.4 | +99.6 | +8.0 |
| ETH | 1m:RSI2 | 1 | 92.2 | +98.0 | +8.0 |
| ETH | 1m:CRSI | 1 | 108.4 | +98.0 | +7.6 |
| BTC | 1m:WILLR14 | 1 | 85.3 | +81.9 | +6.9 |
| ETH | 1m:C-AVGPRICE | 1 | 106.7 | +78.2 | +6.0 |
| BTC | 1m:TakerBuy | 1 | 70.8 | +74.4 | +6.0 |
| BTC | 1m:HT_INPHASE | 1 | 135.7 | +72.4 | +6.1 |
| ETH | 1m:BOP | 1 | 87.4 | +70.2 | +6.3 |
| BTC | 1m:C-SUPERTREND10/3 | 1 | 109.3 | +68.2 | +6.1 |
| BTC | 1m:FOSC5 | 1 | 127.7 | +67.3 | +5.7 |
| ETH | 1m:C-VWMA20 | 1 | 69.5 | +66.5 | +5.4 |
| ETH | 1m:C-VWAP20 | 1 | 69.2 | +65.8 | +5.4 |
| ETH | 1m:SI | 1 | 84.0 | +61.5 | +5.1 |
| ETH | 1m:C-MIDPOINT14 | 1 | 62.1 | +60.2 | +5.6 |
| BTC | 5m:AC | 1 | 91.6 | +56.8 | +9.3 |
| ETH | 1m:SWAK_2PHP20 | 1 | 96.8 | +54.8 | +4.0 |
| BTC | 1m:DONCHIAN20pos | 1 | 78.0 | +53.1 | +4.5 |
| ETH | 1m:FOSC5 | 1 | 72.0 | +50.5 | +4.3 |
| BTC | 1m:PSO | 1 | 70.8 | +49.4 | +4.8 |
| BTC | 1m:RSI7 | 1 | 89.9 | +49.3 | +4.2 |
| ETH | 1m:HT_INPHASE | 1 | 73.1 | +49.0 | +4.0 |
| BTC | 1m:ER10 | 1 | 62.1 | +48.9 | +4.2 |
| ETH | 60m:RSI2 | 60 | 37.2 | +48.4 | +2.7 |
| ETH | 60m:PVI | 60 | 37.4 | +48.4 | +2.6 |
| ETH | 60m:LRSLOPE14 | 60 | 36.3 | +47.9 | +2.4 |
| ETH | 5m:AC | 1 | 115.0 | +47.7 | +5.1 |
| BTC | 1m:FISHER10 | 1 | 84.3 | +47.7 | +4.4 |
| ETH | 1m:C-MIDPRICE14 | 1 | 44.5 | +47.4 | +5.3 |

Top 40 readings by events heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| XRP | 1m:AROONOSC25 | 30 | 149.5 | +185.9 | +6.9 |
| BTC | 1m:BOP | 1 | 190.3 | +182.9 | +18.1 |
| BTC | 1m:C-TYPPRICE | 1 | 169.9 | +157.8 | +14.6 |
| BTC | 1m:C-MEDPRICE | 1 | 169.9 | +157.8 | +14.6 |
| BTC | 1m:C-WCLPRICE | 1 | 169.9 | +157.8 | +14.6 |
| BTC | 1m:ADOSC | 30 | 101.1 | +151.9 | +8.7 |
| XRP | 1m:AROONOSC14 | 30 | 136.4 | +145.0 | +6.2 |
| BTC | 1m:C-AVGPRICE | 1 | 187.7 | +141.8 | +13.0 |
| XRP | 1m:STOCHK14 | 60 | 69.1 | +141.7 | +5.2 |
| ETH | 1m:C-AVGPRICE | 1 | 173.9 | +134.6 | +7.7 |
| BTC | 1m:CMF20 | 60 | 73.8 | +134.5 | +7.3 |
| XRP | 1m:SI | 30 | 104.8 | +127.5 | +3.3 |
| ETH | 1m:BOP | 1 | 159.0 | +124.8 | +8.1 |
| XRP | 1m:CCI20 | 30 | 111.8 | +119.9 | +5.5 |
| BTC | 1m:BarBody | 1 | 192.1 | +119.6 | +11.3 |
| SOL | 1m:C-VWMA20 | 60 | 132.6 | +119.4 | +3.3 |
| ETH | 1m:SI | 1 | 165.4 | +117.9 | +6.4 |
| BTC | 1m:IBS | 5 | 75.4 | +117.4 | +10.1 |
| SOL | 1m:C-TRIMA20 | 60 | 147.6 | +114.9 | +3.4 |
| BTC | 1m:SI | 1 | 169.6 | +109.7 | +10.2 |
| XRP | 1m:RSI7 | 30 | 90.3 | +104.1 | +4.2 |
| XRP | 1m:DONCHIAN20pos | 30 | 107.7 | +103.4 | +3.1 |
| XRP | 1m:EFI13 | 60 | 98.1 | +102.3 | +3.4 |
| XRP | 1m:AD | 60 | 60.4 | +99.8 | +4.5 |
| BTC | 1m:ZSCORE20 | 30 | 162.8 | +99.7 | +5.0 |
| ETH | 1m:BarBody | 1 | 175.6 | +97.3 | +5.4 |
| XRP | 1m:ERIbear13 | 30 | 90.5 | +94.7 | +3.9 |
| XRP | 1m:PERCENTRANK100 | 60 | 92.7 | +94.6 | +3.7 |
| ETH | 1m:ADOSC | 30 | 94.9 | +93.4 | +3.2 |
| BTC | 1m:CDL:CLOSINGMARUBOZU | 1 | 35.0 | +92.8 | +14.8 |
| XRP | 5m:OBV | 60 | 75.0 | +92.1 | +4.3 |
| XRP | 1m:DONCHIAN55pos | 30 | 94.9 | +91.9 | +4.1 |
| BTC | 1m:SWAK_2PHP20 | 1 | 150.5 | +91.3 | +9.5 |
| XRP | 1m:C-EMA9 | 30 | 75.5 | +89.4 | +3.9 |
| BTC | 1m:ULTOSC | 30 | 68.1 | +88.9 | +6.0 |
| BTC | 1m:STOCHK14 | 30 | 106.1 | +88.7 | +5.8 |
| ETH | 1m:IBS | 5 | 95.2 | +87.9 | +5.7 |
| XRP | 1m:PERCENTB20/2.5 | 30 | 116.0 | +87.6 | +3.5 |
| XRP | 1m:ZSCORE20 | 30 | 116.0 | +87.6 | +3.5 |
| XRP | 1m:PERCENTB20/2 | 30 | 116.0 | +87.6 | +3.5 |

## Top 40 replicating by heat on B (windows per day x move, bps per day)

359 of 46,385 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | single | 1m:CCI20=low (falling in) | 30/60 | up | yes | 29.22 | +2.4 | +2.6 | 51.9 | +2.6 | 7.8 | -18.0 | +4.7 | 70.8 | +2.5 | -0.1 |  |  | 0.005 |
| XRP | single | 1m:AROONOSC14=very low | 15/30/60 | up | yes | 22.27 | +3.0 | +3.7 | 53.0 | +3.6 | 7.8 | -18.5 | +4.6 | 67.2 | +3.0 | +0.1 |  |  | 0.005 |
| XRP | single | 1m:STOCHK14=low (falling in) | 30/60 | up | yes | 30.14 | +2.2 | +2.3 | 51.7 | +2.3 | 7.7 | -17.8 | +4.6 | 65.8 | +2.0 | -0.2 |  |  | 0.010 |
| XRP | single | 1m:AROONOSC25=very low | 15/30/60 | up | yes | 14.96 | +4.1 | +5.0 | 54.4 | +5.1 | 8.0 | -19.3 | +4.7 | 61.5 | +3.8 | -0.1 |  |  | 0.010 |
| XRP | single | 1m:DONCHIAN55pos=very low | 15/30/60 | up | yes | 12.37 | +4.9 | +3.2 | 52.7 | +3.2 | 8.6 | -28.9 | +3.9 | 61.0 | +4.5 | -0.4 |  |  | 0.078 |
| XRP | single | 1m:ERIbull13=low (falling in) | 30/60 | up | yes | 29.72 | +2.0 | +2.7 | 52.0 | +2.6 | 7.6 | -17.4 | +4.5 | 60.5 | +1.9 | -0.3 |  |  | 0.017 |
| BTC | single | 1m:IBS=very high | 1/5/15 | up | yes | 177.69 | +0.3 | +3.7 | 48.2 | +1.6 | 7.9 | -1.9 | +16.6 | 60.3 | +0.0 | +0.0 |  |  | 0.000 |
| ETH | single | 1m:C-AVGPRICE sign=below 0 | 1/5 | down | yes | 363.22 | +0.2 | +0.6 | 49.5 | +0.7 | 7.6 | -5.3 | +6.0 | 60.3 | -0.0 | -0.0 |  |  | 0.000 |
| ETH | single | 1m:BOP sign=below 0 | 1/5 | down | yes | 359.83 | +0.2 | +0.7 | 49.6 | +0.8 | 7.6 | -5.3 | +6.0 | 58.9 | -0.0 | +0.0 |  |  | 0.000 |
| ETH | single | 1m:BarBody sign=below 0 | 1/5 | down | yes | 359.83 | +0.2 | +0.7 | 49.6 | +0.8 | 7.6 | -5.3 | +6.0 | 58.9 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:CDL:CLOSINGMARUBOZU=bull | 1/5 | up | yes | 203.81 | +0.3 | +2.7 | 49.4 | +2.8 | 8.1 | -2.5 | +13.4 | 58.8 | +0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-AVGPRICE sign=below 0 | 1/5/15/30 | down | yes | 351.66 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +9.6 | 58.4 | -0.0 | -0.0 |  |  | 0.000 |
| ETH | single | 1m:C-MEDPRICE sign=below 0 | 1/5 | down | yes | 363.45 | +0.2 | +0.5 | 49.3 | +0.6 | 7.6 | -5.3 | +5.7 | 58.4 | -0.0 | -0.0 |  |  | 0.000 |
| ETH | single | 1m:C-TYPPRICE sign=below 0 | 1/5 | down | yes | 363.45 | +0.2 | +0.5 | 49.3 | +0.6 | 7.6 | -5.3 | +5.7 | 58.4 | -0.0 | -0.0 |  |  | 0.000 |
| ETH | single | 1m:C-WCLPRICE sign=below 0 | 1/5 | down | yes | 363.45 | +0.2 | +0.5 | 49.3 | +0.6 | 7.6 | -5.3 | +5.7 | 58.4 | -0.0 | +0.0 |  |  | 0.000 |
| XRP | single | 1m:PERCENTB20/2=low (falling in) | 30 | up | yes | 30.44 | +1.9 | +2.3 | 51.7 | +2.3 | 7.7 | -18.0 | +4.0 | 57.4 | +2.0 | +0.0 |  |  | 0.029 |
| XRP | single | 1m:PERCENTB20/2.5=low (falling in) | 30 | up | yes | 30.44 | +1.9 | +2.3 | 51.7 | +2.3 | 7.7 | -18.0 | +4.0 | 57.4 | +2.0 | +0.1 |  |  | 0.029 |
| XRP | single | 1m:ZSCORE20=low (falling in) | 30 | up | yes | 30.44 | +1.9 | +2.3 | 51.7 | +2.3 | 7.7 | -18.0 | +4.0 | 57.4 | +2.0 | +0.1 |  |  | 0.029 |
| BTC | single | 1m:IBS=very low | 1/5/15 | down | yes | 173.46 | +0.3 | +3.5 | 47.7 | +1.3 | 7.8 | -1.9 | +15.5 | 56.7 | -0.0 | -0.0 |  |  | 0.000 |
| XRP | single | 1m:AROONOSC14=low (falling in) | 30/60 | up | yes | 17.08 | +3.3 | +2.0 | 51.6 | +2.2 | 7.6 | -24.5 | +4.0 | 56.4 | +3.2 | +0.0 |  |  | 0.042 |
| XRP | single | 1m:FISHER10=low (falling in) | 30 | up | yes | 23.57 | +2.4 | +2.7 | 52.0 | +2.6 | 7.9 | -18.4 | +4.3 | 55.6 | +2.1 | +0.0 |  |  | 0.016 |
| ETH | single | 1m:SI sign=below 0 | 1/5/15 | down | yes | 323.36 | +0.2 | +0.6 | 49.4 | +0.6 | 7.6 | -5.3 | +5.9 | 55.5 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-MEDPRICE sign=below 0 | 1/5/15 | down | yes | 352.44 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +8.7 | 55.4 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:C-TYPPRICE sign=below 0 | 1/5/15 | down | yes | 352.44 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +8.7 | 55.4 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-WCLPRICE sign=below 0 | 1/5/15 | down | yes | 352.44 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +8.7 | 55.4 | -0.0 | +0.0 |  |  | 0.000 |
| XRP | single | 5m:OBV=low (falling in) | 60 | up | yes | 5.39 | +9.6 | +4.7 | 54.1 | +4.7 | 8.7 | -28.4 | +4.4 | 51.9 | +9.1 | +1.3 |  |  | 0.020 |
| BTC | single | 1m:BOP sign=below 0 | 1/5/15/30 | down | yes | 340.44 | +0.2 | +1.5 | 48.6 | +2.1 | 7.8 | -2.9 | +8.7 | 51.5 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:BarBody sign=below 0 | 1/5/15/30 | down | yes | 340.44 | +0.2 | +1.5 | 48.6 | +2.1 | 7.8 | -2.9 | +8.7 | 51.5 | -0.0 | -0.0 |  |  | 0.000 |
| XRP | single | 1m:PERCENTRANK100=low (recovering) | 15/30/60 | up | yes | 13.36 | +3.7 | +4.3 | 53.7 | +4.4 | 7.9 | -21.5 | +3.7 | 48.8 | +3.4 | -0.0 |  |  | 0.084 |
| ETH | single | 1m:C-MEDPRICE sign=above 0 | 1/5 | up | yes | 363.45 | +0.1 | +0.6 | 49.9 | +0.6 | 7.8 | -5.3 | +4.9 | 48.6 | +0.0 | -0.0 |  |  | 0.002 |
| ETH | single | 1m:C-TYPPRICE sign=above 0 | 1/5 | up | yes | 363.45 | +0.1 | +0.6 | 49.9 | +0.6 | 7.8 | -5.3 | +4.9 | 48.6 | +0.0 | +0.0 |  |  | 0.002 |
| ETH | single | 1m:C-WCLPRICE sign=above 0 | 1/5 | up | yes | 363.45 | +0.1 | +0.6 | 49.9 | +0.6 | 7.8 | -5.3 | +4.9 | 48.6 | +0.0 | +0.0 |  |  | 0.002 |
| ETH | single | 1m:IBS=very high | 1/5/15 | up | yes | 123.92 | +0.4 | +1.7 | 50.5 | +1.2 | 8.0 | -3.8 | +9.5 | 46.6 | +0.0 | +0.0 |  |  | 0.000 |
| ETH | single | 1m:IBS=very low | 1/5/15 | down | yes | 117.39 | +0.4 | +1.7 | 49.9 | +1.1 | 7.6 | -3.9 | +10.1 | 46.5 | -0.0 | +0.0 |  |  | 0.000 |
| ETH | single | 1m:C-AVGPRICE sign=above 0 | 1/5 | up | yes | 363.22 | +0.1 | +0.7 | 50.0 | +0.7 | 7.9 | -5.3 | +4.5 | 46.1 | +0.0 | +0.0 |  |  | 0.008 |
| XRP | single | 5m:Runs=3-4 down | 30/60 | up | yes | 17.54 | +2.6 | +3.2 | 52.6 | +3.2 | 8.1 | -18.1 | +3.9 | 45.6 | +2.8 | -0.2 |  |  | 0.076 |
| BTC | single | 1m:SI sign=below 0 | 1/5/15/30 | down | yes | 313.53 | +0.1 | +1.3 | 48.2 | +1.7 | 7.7 | -2.9 | +8.1 | 45.3 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:C-MEDPRICE sign=above 0 | 1/5 | up | yes | 352.44 | +0.1 | +1.5 | 48.2 | +1.6 | 7.8 | -2.9 | +7.5 | 43.6 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:C-TYPPRICE sign=above 0 | 1/5 | up | yes | 352.44 | +0.1 | +1.5 | 48.2 | +1.6 | 7.8 | -2.9 | +7.5 | 43.6 | +0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-WCLPRICE sign=above 0 | 1/5 | up | yes | 352.44 | +0.1 | +1.5 | 48.2 | +1.6 | 7.8 | -2.9 | +7.5 | 43.6 | +0.0 | +0.0 |  |  | 0.000 |

## Top 40 replicating by move per event on B (bps; at least 0.2 windows per day)

359 of 45,302 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | single | 5m:SMI=very low | 30/60 | up | yes | 1.37 | +14.5 | +8.4 | 58.0 | +8.6 | 10.6 | -23.1 | +4.1 | 19.9 | +13.6 | -1.3 |  |  | 0.043 |
| XRP | single | 5m:OBV=low (falling in) | 60 | up | yes | 5.39 | +9.6 | +4.7 | 54.1 | +4.7 | 8.7 | -28.4 | +4.4 | 51.9 | +9.1 | +1.3 |  |  | 0.020 |
| XRP | single | 5m:QSTICK10=very low | 15/30/60 | up | yes | 2.97 | +8.0 | +6.1 | 55.0 | +6.0 | 10.9 | -19.1 | +4.3 | 23.8 | +5.8 | -0.1 |  |  | 0.036 |
| XRP | single | 5m:MOM10=very low | 15/30/60 | up | yes | 2.84 | +7.6 | +5.4 | 54.3 | +5.3 | 10.8 | -18.9 | +3.9 | 21.6 | +4.9 | -0.0 |  |  | 0.084 |
| XRP | single | 15m:WILLR14=very low | 30/60 | up | yes | 2.45 | +7.2 | +7.0 | 56.3 | +7.0 | 10.2 | -19.8 | +3.6 | 17.5 | +4.0 | -0.5 |  |  | 0.095 |
| SOL | single | 60m:CDL:TAKURI=fires | 5 | down | yes | 0.44 | +7.0 | +11.4 | 57.9 | +10.1 | 8.6 | -6.2 | +4.3 | 3.1 | +5.5 | +0.7 |  |  | 0.030 |
| XRP | single | 15m:CRSI=very low | 1/5 | up | yes | 1.56 | +6.3 | +9.3 | 58.5 | +10.2 | 11.4 | -14.7 | +3.9 | 9.9 | +3.3 | -0.1 |  |  | 0.052 |
| XRP | single | 1m:DONCHIAN55pos=very low | 15/30/60 | up | yes | 12.37 | +4.9 | +3.2 | 52.7 | +3.2 | 8.6 | -28.9 | +3.9 | 61.0 | +4.5 | -0.4 |  |  | 0.078 |
| XRP | single | 5m:ROC10=very low | 5/15/60 | up | yes | 2.93 | +4.9 | +7.8 | 56.2 | +7.9 | 10.9 | -12.2 | +3.9 | 14.4 | +2.0 | +0.3 |  |  | 0.081 |
| XRP | single | 60m:CDL:CLOSINGMARUBOZU=bear | 1/5/15/30 | up | yes | 1.17 | +4.7 | +15.0 | 62.8 | +16.5 | 13.8 | -6.1 | +6.2 | 5.5 | +0.0 | -0.3 |  |  | 0.003 |
| SOL | single | 60m:IBS=high (rising in) | 1/5 | down | yes | 1.82 | +4.5 | +10.1 | 58.8 | +11.0 | 11.2 | -9.5 | +3.8 | 8.1 | +2.4 | +0.8 |  |  | 0.070 |
| XRP | single | 1m:AROONOSC25=very low | 15/30/60 | up | yes | 14.96 | +4.1 | +5.0 | 54.4 | +5.1 | 8.0 | -19.3 | +4.7 | 61.5 | +3.8 | -0.1 |  |  | 0.010 |
| XRP | single | 1m:AROONOSC14=very low | 15/30/60 | up | yes | 16.86 | +3.7 | +2.1 | 51.7 | +2.2 | 7.8 | -25.6 | +4.0 | 63.1 | +3.7 | -0.1 |  |  | 0.051 |
| XRP | single | 1m:PERCENTRANK100=low (recovering) | 15/30/60 | up | yes | 13.36 | +3.7 | +4.3 | 53.7 | +4.4 | 7.9 | -21.5 | +3.7 | 48.8 | +3.4 | -0.0 |  |  | 0.084 |
| XRP | single | 1m:CCI20=low (falling in) | 30/60 | up | yes | 20.47 | +3.3 | +2.2 | 51.7 | +2.2 | 7.8 | -24.9 | +5.0 | 67.6 | +3.4 | +0.1 |  |  | 0.003 |
| XRP | single | 1m:AROONOSC14=low (falling in) | 30/60 | up | yes | 17.08 | +3.3 | +2.0 | 51.6 | +2.2 | 7.6 | -24.5 | +4.0 | 56.4 | +3.2 | +0.0 |  |  | 0.042 |
| XRP | single | 5m:MACDh5/35/5=very low | 1/15/60 | up | yes | 2.52 | +3.0 | +11.7 | 59.3 | +13.0 | 10.3 | -10.8 | +4.4 | 7.6 | +0.0 | +0.1 |  |  | 0.029 |
| XRP | single | 5m:C-SAR=very low | 1/15/60 | up | yes | 2.52 | +3.0 | +7.5 | 54.9 | +8.7 | 10.8 | -11.1 | +4.3 | 7.6 | +0.0 | -0.0 |  |  | 0.028 |
| BTC | single | 60m:FOSC5=low (falling in) | 1/5/15 | up | yes | 1.61 | +2.8 | +8.3 | 57.9 | +8.4 | 10.6 | -4.8 | +4.3 | 4.5 | +1.2 | +0.7 |  |  | 0.018 |
| XRP | single | 5m:C-ZLEMA21=very low | 1 | up | yes | 3.36 | +2.8 | +9.0 | 56.6 | +10.4 | 10.2 | -10.3 | +4.5 | 9.3 | +0.0 | +0.1 |  |  | 0.081 |
| ETH | single | 15m:STOCHFK5=very low | 1 | up | yes | 1.47 | +2.7 | +11.4 | 61.2 | +11.9 | 11.8 | -7.2 | +4.1 | 3.9 | +0.0 | -0.2 |  |  | 0.059 |
| XRP | single | 1m:STOCHK14=low (falling in) | 30/60 | up | yes | 20.73 | +2.6 | +1.8 | 51.4 | +1.9 | 7.7 | -25.0 | +4.2 | 54.7 | +2.5 | -0.1 |  |  | 0.019 |
| XRP | single | 60m:CDL:CLOSINGMARUBOZU=bull | 1/5 | down | yes | 1.47 | +2.6 | +10.5 | 57.6 | +11.6 | 13.7 | -7.1 | +4.4 | 3.8 | -0.0 | -0.2 |  |  | 0.013 |
| XRP | single | 5m:Runs=3-4 down | 30/60 | up | yes | 17.54 | +2.6 | +3.2 | 52.6 | +3.2 | 8.1 | -18.1 | +3.9 | 45.6 | +2.8 | -0.2 |  |  | 0.076 |
| SOL | single | 60m:C-AVGPRICE=low (falling in) | 1/5 | up | yes | 1.79 | +2.5 | +6.0 | 52.1 | +7.1 | 11.1 | -8.7 | +4.1 | 4.5 | +0.0 | +0.1 |  |  | 0.042 |
| SOL | single | 60m:FOSC5=low (falling in) | 1 | up | yes | 1.49 | +2.5 | +7.6 | 52.9 | +7.8 | 9.6 | -7.7 | +3.8 | 3.7 | +0.0 | +0.0 |  |  | 0.079 |
| XRP | single | 1m:FISHER10=low (falling in) | 30 | up | yes | 23.57 | +2.4 | +2.7 | 52.0 | +2.6 | 7.9 | -18.4 | +4.3 | 55.6 | +2.1 | +0.0 |  |  | 0.016 |
| BTC | single | 5m:C-TSF14=low (falling in) | 1/15/30/60 | up | yes | 12.38 | +2.3 | +2.9 | 53.4 | +2.9 | 8.5 | -11.9 | +4.0 | 28.8 | +2.1 | +0.0 |  |  | 0.031 |
| SOL | single | 60m:BarBody=low (falling in) | 1/5 | up | yes | 1.82 | +2.3 | +4.6 | 51.1 | +6.1 | 10.3 | -8.7 | +4.0 | 4.2 | +0.0 | +0.4 |  |  | 0.038 |
| XRP | single | 60m:CDL:LONGLINE=bear | 1 | up | yes | 2.02 | +2.2 | +4.8 | 52.3 | +6.1 | 10.5 | -6.7 | +4.3 | 4.4 | +0.0 | -0.3 |  |  | 0.020 |
| XRP | single | 1m:ERIbull13=low (falling in) | 30/60 | up | yes | 20.28 | +2.2 | +1.8 | 51.3 | +1.8 | 7.6 | -24.3 | +3.6 | 44.4 | +2.1 | -0.4 |  |  | 0.083 |
| ETH | single | 1m:RSI7=very low | 1/5 | up | yes | 12.07 | +2.2 | +6.8 | 56.7 | +6.8 | 11.1 | -11.3 | +4.3 | 26.3 | +0.6 | +0.1 |  |  | 0.026 |
| XRP | single | 15m:CDL:CLOSINGMARUBOZU=bear | 1/5 | up | yes | 6.39 | +2.1 | +5.7 | 54.1 | +5.9 | 9.3 | -8.1 | +4.0 | 13.2 | +0.8 | -0.3 |  |  | 0.030 |
| XRP | single | 15m:MACDh5/35/5=low (falling in) | 1 | up | yes | 3.12 | +2.1 | +6.8 | 54.2 | +8.0 | 10.0 | -8.4 | +4.3 | 6.4 | +0.0 | -0.1 |  |  | 0.025 |
| SOL | single | 60m:CDL:LONGLINE=bear | 1/5 | up | yes | 2.13 | +2.0 | +6.1 | 51.2 | +6.1 | 9.8 | -7.7 | +3.7 | 4.3 | +0.0 | -0.2 |  |  | 0.082 |
| XRP | single | 60m:IBS=high (rising in) | 1 | down | yes | 1.73 | +2.0 | +8.7 | 55.9 | +9.9 | 11.5 | -7.3 | +3.9 | 3.5 | -0.0 | -0.1 |  |  | 0.045 |
| SOL | single | 60m:C-FRAMA16 sign=below 0 | 1 | up | yes | 2.16 | +2.0 | +3.5 | 49.3 | +4.3 | 9.5 | -7.8 | +3.7 | 4.2 | +0.0 | +0.1 |  |  | 0.068 |
| BTC | single | 5m:C-LINEARREG14=low (falling in) | 1/15/30/60 | up | yes | 12.83 | +1.9 | +3.2 | 53.7 | +3.2 | 8.5 | -12.1 | +3.6 | 24.8 | +1.7 | +0.4 |  |  | 0.086 |
| BTC | single | 60m:WT1 sign=above 0 | 1 | up | yes | 0.59 | +1.9 | +10.4 | 57.7 | +11.1 | 7.7 | -2.2 | +4.2 | 1.1 | +0.0 | +0.1 |  |  | 0.035 |
| XRP | single | 1m:PERCENTB20/2=low (falling in) | 30 | up | yes | 30.44 | +1.9 | +2.3 | 51.7 | +2.3 | 7.7 | -18.0 | +4.0 | 57.4 | +2.0 | +0.0 |  |  | 0.029 |

## Top 40 replicating by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)

6,011 of 188,198 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | pair | 60m:C-AVGPRICE=high (rising in) / 1m:C-FRAMA16=high | 1/5/15 | down | yes | 0.25 | +7.5 | +27.0 | 74.2 | +28.2 | 20.1 | -6.0 | +6.4 | 6.9 | -0.0 |  | +25.5 | +26.0 | 0.084 |
| ETH | pair | 5m:STOCHFK5=low (falling in) / 60m:C-ZLEMA21=very high | 1/15 | up | yes | 0.28 | +4.7 | +26.0 | 76.2 | +26.9 | 13.6 | -4.9 | +6.6 | 7.2 | +0.0 |  | +23.5 | +25.2 | 0.075 |
| ETH | pair | 60m:C-MEDPRICE sign=below 0 / 5m:C-TEMA21=very low | 1/5 | up | yes | 0.28 | +6.3 | +24.5 | 73.3 | +24.0 | 15.5 | -10.4 | +6.2 | 6.8 | +0.0 |  | +22.0 | +21.9 | 0.075 |
| ETH | pair | 60m:C-TYPPRICE sign=below 0 / 5m:C-TEMA21=very low | 1/5 | up | yes | 0.28 | +6.3 | +24.5 | 73.3 | +24.0 | 15.5 | -10.4 | +6.2 | 6.8 | +0.0 |  | +22.0 | +21.9 | 0.075 |
| ETH | pair | 60m:C-WCLPRICE sign=below 0 / 5m:C-TEMA21=very low | 1/5 | up | yes | 0.28 | +6.3 | +24.5 | 73.3 | +24.0 | 15.5 | -10.4 | +6.2 | 6.8 | +0.0 |  | +22.0 | +21.9 | 0.075 |
| XRP | pair | 15m:C-SAR=low (falling in) / 60m:C-SWAK_BUTTER20=low | 60 | up | yes | 0.40 | +25.0 | +23.7 | 73.3 | +23.9 | 14.0 | -33.0 | +6.8 | 9.5 | +22.9 |  | +20.1 | +19.8 | 0.083 |
| XRP | pair | 1m:C-EMA21=very low / 15m:C-SMA20=very low | 5/15/30/60 | up | yes | 0.44 | +42.8 | +23.6 | 72.9 | +23.5 | 13.9 | -47.2 | +7.3 | 10.3 | +42.9 |  | +19.9 | +18.0 | 0.074 |
| XRP | pair | 60m:CRSI=high (rising in) / 60m:MOM10 sign=below 0 | 1 | down | yes | 0.35 | +4.5 | +23.1 | 71.4 | +25.4 | 14.0 | -7.1 | +6.2 | 8.0 | -0.0 |  | +24.0 | +23.2 | 0.086 |
| XRP | pair | 60m:CRSI=high (rising in) / 60m:ROC10 sign=below 0 | 1 | down | yes | 0.35 | +4.5 | +23.1 | 71.4 | +25.4 | 14.0 | -7.1 | +6.2 | 8.0 | -0.0 |  | +24.0 | +23.2 | 0.086 |
| XRP | pair | 60m:CRSI=high (rising in) / 60m:QSTICK10 sign=below 0 | 1 | down | yes | 0.35 | +4.5 | +23.1 | 71.4 | +25.4 | 14.0 | -7.1 | +6.2 | 8.0 | -0.0 |  | +24.0 | +23.3 | 0.086 |
| XRP | pair | 15m:C-SAR=low (falling in) / 60m:C-SWAK_GAUSS20=low | 60 | up | yes | 0.44 | +28.3 | +23.0 | 72.3 | +22.8 | 12.5 | -33.3 | +6.8 | 10.1 | +26.5 |  | +19.6 | +19.3 | 0.081 |
| XRP | single | 60m:CMOU14=high (cooling) | 1 | up | yes | 0.20 | +7.4 | +22.9 | 68.9 | +22.7 | 10.9 | -5.8 | +4.6 | 4.6 | +0.0 | -2.3 |  |  | 0.013 |
| XRP | single | 60m:IMI14=high (cooling) | 1 | up | yes | 0.20 | +7.5 | +22.9 | 68.9 | +22.7 | 10.6 | -5.8 | +4.5 | 4.6 | +0.0 | -2.2 |  |  | 0.012 |
| XRP | pair | 15m:C-SAR=low (falling in) / 60m:SWAK_HP20=low | 60 | up | yes | 0.45 | +27.3 | +22.5 | 71.8 | +22.4 | 11.8 | -33.7 | +6.7 | 10.2 | +25.3 |  | +19.2 | +18.8 | 0.077 |
| XRP | pair | 60m:C-AVGPRICE=high (rising in) / 60m:C-MAMA sign=below 0 | 1 | down | yes | 0.40 | +4.9 | +21.8 | 70.3 | +24.4 | 15.5 | -7.5 | +5.8 | 8.7 | -0.0 |  | +21.5 | +22.1 | 0.097 |
| BTC | pair | 15m:SWAK_HP20=low (falling in) / 1m:DONCHIAN20pos=very low | 1/5 | up | yes | 0.47 | +3.5 | +21.1 | 70.6 | +21.1 | 14.4 | -4.4 | +6.2 | 9.8 | +1.6 |  | +17.8 | +18.3 | 0.084 |
| XRP | single | 60m:C-SMA20=high (cooling) | 1 | up | yes | 0.21 | +5.5 | +20.6 | 69.3 | +23.1 | 11.8 | -8.2 | +3.9 | 4.2 | +0.0 | +1.0 |  |  | 0.017 |
| XRP | pair | 5m:CCI14=high (rising in) / 60m:C-SAR=low | 1 | down | yes | 0.65 | +3.8 | +20.2 | 66.9 | +21.0 | 10.6 | -5.3 | +7.4 | 13.1 | -0.0 |  | +17.6 | +20.4 | 0.012 |
| XRP | single | 60m:C-TRIMA20=high (cooling) | 1 | up | yes | 0.20 | +4.4 | +20.2 | 68.9 | +22.7 | 13.3 | -7.0 | +3.7 | 4.1 | +0.0 | -2.1 |  |  | 0.017 |
| BTC | single | 60m:C-EMA50=very low | 15/30 | up | yes | 0.20 | +8.5 | +20.0 | 69.9 | +20.0 | 12.2 | -17.7 | +3.3 | 4.0 | +8.7 | +1.8 |  |  | 0.056 |
| XRP | pair | 60m:C-AVGPRICE=high (rising in) / 15m:CCI50 sign=below 0 | 1 | down | yes | 0.60 | +4.9 | +19.7 | 67.1 | +21.1 | 13.3 | -6.7 | +6.4 | 11.9 | -0.0 |  | +22.0 | +19.9 | 0.027 |
| XRP | single | 60m:C-SWAK_BUTTER20=very low | 15/30 | up | yes | 0.32 | +38.2 | +19.2 | 69.2 | +19.9 | 15.9 | -44.4 | +4.2 | 6.2 | +34.3 | -2.0 |  |  | 0.004 |
| XRP | pair | 60m:C-AVGPRICE=high (rising in) / 60m:C-WMA20 sign=below 0 | 1 | down | yes | 0.57 | +4.9 | +19.2 | 67.1 | +21.2 | 14.3 | -6.8 | +6.0 | 10.9 | -0.0 |  | +20.6 | +19.4 | 0.063 |
| XRP | single | 60m:C-SAR=very low | 15/30 | up | yes | 0.23 | +24.7 | +19.0 | 69.0 | +19.7 | 16.5 | -33.9 | +3.9 | 4.4 | +21.6 | -0.1 |  |  | 0.013 |
| XRP | single | 60m:CCI14=very low | 30/60 | up | yes | 0.32 | +9.0 | +19.0 | 69.0 | +19.6 | 11.0 | -42.0 | +4.5 | 6.0 | +8.9 | +2.3 |  |  | 0.001 |
| BTC | pair | 5m:C-WMA20=high (rising in) / 15m:RVIR14=low | 1/5 | down | yes | 0.64 | +2.9 | +18.7 | 66.5 | +20.1 | 12.6 | -2.9 | +6.2 | 12.0 | -0.0 |  | +16.7 | +18.7 | 0.083 |
| BTC | pair | 5m:RSI2=high (rising in) / 60m:STOCHK14=very low | 1 | down | yes | 0.76 | +2.2 | +18.7 | 67.4 | +20.9 | 10.9 | -3.0 | +7.2 | 14.3 | -0.0 |  | +15.8 | +18.7 | 0.027 |
| XRP | pair | 60m:C-AVGPRICE=high (rising in) / 15m:C-SMA50 sign=below 0 | 1 | down | yes | 0.57 | +4.8 | +18.6 | 66.3 | +20.4 | 13.5 | -7.0 | +5.8 | 10.6 | -0.0 |  | +19.9 | +18.9 | 0.085 |
| BTC | single | 60m:WILLR14=high (cooling) | 30/60 | down | yes | 0.34 | +16.0 | +18.5 | 68.0 | +18.6 | 9.8 | -13.5 | +4.5 | 6.3 | +16.5 | +1.8 |  |  | 0.002 |
| XRP | pair | 1m:C-EMA9=low (falling in) / 5m:DX14=very high | 15/30/60 | up | yes | 0.61 | +39.3 | +18.5 | 68.1 | +18.8 | 11.5 | -40.4 | +6.1 | 11.2 | +37.3 |  | +16.1 | +15.3 | 0.088 |
| ETH | pair | 5m:C-SWAK_GAUSS20=low (falling in) / 60m:CG10=high | 1/5 | up | yes | 0.81 | +4.2 | +18.4 | 68.4 | +19.1 | 12.6 | -6.3 | +7.2 | 15.0 | +0.0 |  | +14.5 | +18.5 | 0.066 |
| BTC | single | 60m:ERIbull13=very high | 1 | up | yes | 0.20 | +6.4 | +18.4 | 68.5 | +21.9 | 14.4 | -3.4 | +3.2 | 3.7 | +0.0 | +3.4 |  |  | 0.071 |
| SOL | single | 60m:KC20pos=high (cooling) | 1 | up | yes | 0.20 | +4.1 | +18.3 | 64.4 | +19.3 | 10.7 | -4.7 | +3.4 | 3.7 | +0.0 | +2.0 |  |  | 0.059 |
| BTC | pair | 5m:RSI2=high (rising in) / 60m:KDJ_J=very low | 1 | down | yes | 0.75 | +1.9 | +18.2 | 66.2 | +19.7 | 11.2 | -2.4 | +6.5 | 13.7 | -0.0 |  | +15.4 | +17.6 | 0.063 |
| XRP | single | 60m:ACCBANDS20pos=very low | 15/30 | up | yes | 0.23 | +33.8 | +18.2 | 68.2 | +18.9 | 14.2 | -27.9 | +3.2 | 4.2 | +29.6 | +2.0 |  |  | 0.067 |
| ETH | pair | 60m:C-MEDPRICE sign=below 0 / 15m:C-AVGPRICE=low | 1/5/15/60 | up | yes | 0.75 | +4.8 | +18.2 | 68.4 | +18.4 | 13.2 | -8.7 | +7.0 | 13.7 | +3.0 |  | +15.3 | +15.3 | 0.033 |
| ETH | pair | 60m:C-TYPPRICE sign=below 0 / 15m:C-AVGPRICE=low | 1/5/15/60 | up | yes | 0.75 | +4.8 | +18.2 | 68.4 | +18.4 | 13.2 | -8.7 | +7.0 | 13.7 | +3.0 |  | +15.3 | +15.3 | 0.033 |
| ETH | pair | 60m:C-WCLPRICE sign=below 0 / 15m:C-AVGPRICE=low | 1/5/15/60 | up | yes | 0.75 | +4.8 | +18.2 | 68.4 | +18.4 | 13.2 | -8.7 | +7.0 | 13.7 | +3.0 |  | +15.3 | +15.3 | 0.033 |
| XRP | pair | 1m:C-MIDPOINT14=low (falling in) / 5m:ER10=very high | 5/15/30/60 | up | yes | 0.69 | +19.6 | +18.2 | 67.2 | +18.2 | 10.5 | -20.3 | +6.1 | 12.4 | +18.0 |  | +15.8 | +15.4 | 0.063 |
| XRP | single | 15m:TSI=low (recovering) | 1 | down | yes | 0.27 | +3.9 | +18.2 | 63.9 | +17.9 | 10.0 | -8.3 | +3.9 | 4.8 | -0.0 | -1.4 |  |  | 0.010 |

## Top 40 replicating by odds heat on B (windows per day x odds points)

6,023 of 194,455 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | single | 1m:IBS=very high | 1/5 | up | yes | 177.69 | +0.3 | +3.7 | 48.2 | +1.6 | 7.9 | -1.9 | +17.9 | 649.4 | +0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:IBS=very low | 1/5/15 | down | yes | 173.46 | +0.3 | +3.5 | 47.7 | +1.3 | 7.8 | -1.9 | +17.6 | 613.8 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-AVGPRICE sign=below 0 | 1/5 | down | yes | 351.66 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +11.6 | 607.4 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-MEDPRICE sign=below 0 | 1/5 | down | yes | 352.44 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +10.9 | 591.2 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:C-TYPPRICE sign=below 0 | 1/5 | down | yes | 352.44 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +10.9 | 591.2 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-WCLPRICE sign=below 0 | 1/5 | down | yes | 352.44 | +0.2 | +1.7 | 48.3 | +1.8 | 7.8 | -2.9 | +10.9 | 591.2 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:CDL:CLOSINGMARUBOZU=bull | 1/30/60 | up | yes | 203.81 | +0.3 | +2.7 | 49.4 | +2.8 | 8.1 | -2.5 | +12.3 | 554.8 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:C-AVGPRICE sign=above 0 | 1/5 | up | yes | 351.66 | +0.1 | +1.5 | 48.2 | +1.6 | 7.8 | -2.9 | +9.3 | 517.5 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:BOP sign=below 0 | 1/5/15/30 | down | yes | 340.44 | +0.2 | +1.5 | 48.6 | +2.1 | 7.8 | -2.9 | +10.1 | 516.2 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:BarBody sign=below 0 | 1/5/15/30 | down | yes | 340.44 | +0.2 | +1.5 | 48.6 | +2.1 | 7.8 | -2.9 | +10.1 | 516.2 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:SI sign=above 0 | 1/5 | up | yes | 313.54 | +0.1 | +1.5 | 48.4 | +1.8 | 7.8 | -2.9 | +9.0 | 468.1 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:BOP sign=above 0 | 1/5 | up | yes | 340.44 | +0.1 | +1.4 | 48.5 | +1.9 | 7.8 | -3.0 | +8.8 | 463.9 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:BarBody sign=above 0 | 1/5 | up | yes | 340.44 | +0.1 | +1.4 | 48.5 | +1.9 | 7.8 | -3.0 | +8.8 | 463.9 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:CDL:MARUBOZU=bull | 1 | up | yes | 155.73 | +0.3 | +3.0 | 48.9 | +2.3 | 8.1 | -2.2 | +11.6 | 462.9 | +0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:SI sign=below 0 | 1/5 | down | yes | 313.53 | +0.1 | +1.3 | 48.2 | +1.7 | 7.7 | -2.9 | +8.7 | 420.3 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:CDL:SHORTLINE=bear | 1 | down | yes | 159.27 | +0.2 | +2.6 | 46.5 | +0.0 | 7.6 | -2.0 | +12.4 | 419.2 | -0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:SWAK_2PHP20 sign=above 0 | 1/5 | up | yes | 273.66 | +0.1 | +1.3 | 48.4 | +1.8 | 7.8 | -3.0 | +7.7 | 366.0 | +0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:CDL:MARUBOZU=bear | 1 | down | yes | 152.54 | +0.2 | +2.4 | 48.4 | +1.9 | 7.7 | -2.2 | +9.1 | 363.2 | -0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:SWAK_2PHP20 sign=below 0 | 1/5 | down | yes | 273.66 | +0.1 | +1.3 | 48.3 | +1.9 | 7.7 | -3.0 | +8.1 | 358.1 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:CDL:SHORTLINE=bull | 1 | up | yes | 191.07 | +0.1 | +1.8 | 44.3 | -2.2 | 7.2 | -1.8 | +10.2 | 345.4 | +0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:BOP=high (rising in) | 1/60 | up | yes | 143.68 | +0.2 | +2.3 | 48.3 | +1.7 | 7.8 | -2.2 | +9.3 | 324.0 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:FOSC5 sign=below 0 | 1/5 | down | yes | 277.43 | +0.1 | +1.1 | 47.8 | +1.4 | 7.6 | -3.0 | +7.2 | 315.6 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:FOSC5 sign=above 0 | 1/5/30 | up | yes | 277.43 | +0.1 | +1.1 | 47.9 | +1.3 | 7.7 | -3.0 | +7.1 | 312.0 | +0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:C-ALMA9 sign=above 0 | 1/5 | up | yes | 187.05 | +0.2 | +1.6 | 48.8 | +2.2 | 7.9 | -2.9 | +8.1 | 297.2 | +0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:C-FRAMA16 sign=below 0 | 1/5/15 | down | yes | 144.49 | +0.2 | +2.0 | 48.8 | +2.4 | 7.9 | -2.8 | +8.4 | 291.3 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:BOP=low (falling in) | 1 | down | yes | 141.16 | +0.1 | +2.0 | 48.1 | +1.6 | 7.7 | -2.3 | +7.9 | 281.0 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:STOCHFK5=very high | 1 | up | yes | 72.75 | +0.4 | +3.8 | 48.4 | +1.8 | 8.2 | -2.0 | +11.9 | 276.6 | +0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:C-ALMA9 sign=below 0 | 1/5 | down | yes | 187.05 | +0.2 | +1.5 | 48.6 | +2.1 | 7.8 | -2.9 | +7.3 | 274.4 | -0.0 | -0.1 |  |  | 0.000 |
| BTC | single | 1m:BOP=very high | 1/5 | up | yes | 70.43 | +0.3 | +3.7 | 45.8 | -0.8 | 7.6 | -1.5 | +11.7 | 263.9 | +0.0 | -0.1 |  |  | 0.000 |
| ETH | single | 1m:BOP sign=below 0 | 1/5/15 | down | yes | 359.83 | +0.2 | +0.7 | 49.6 | +0.8 | 7.6 | -5.3 | +4.9 | 263.2 | -0.0 | +0.0 |  |  | 0.000 |
| ETH | single | 1m:BarBody sign=below 0 | 1/5/15 | down | yes | 359.83 | +0.2 | +0.7 | 49.6 | +0.8 | 7.6 | -5.3 | +4.9 | 263.2 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:BOP=very low | 1/5 | down | yes | 74.79 | +0.2 | +3.5 | 45.4 | -1.1 | 7.6 | -1.4 | +12.0 | 262.2 | -0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:STOCHFK5=very low | 1 | down | yes | 69.35 | +0.3 | +3.6 | 47.8 | +1.4 | 7.7 | -1.9 | +11.4 | 246.9 | -0.0 | +0.0 |  |  | 0.000 |
| BTC | single | 1m:TakerBuy=very low | 1/5 | down | yes | 85.06 | +0.2 | +2.8 | 47.0 | +0.5 | 7.6 | -1.6 | +8.9 | 241.4 | -0.0 | +0.1 |  |  | 0.000 |
| ETH | single | 1m:C-AVGPRICE sign=below 0 | 1/15 | down | yes | 363.22 | +0.2 | +0.6 | 49.5 | +0.7 | 7.6 | -5.3 | +4.5 | 234.5 | -0.0 | +0.0 |  |  | 0.001 |
| BTC | single | 1m:SWAK_HP20 sign=below 0 | 1/5 | down | yes | 161.01 | +0.2 | +1.5 | 48.8 | +2.3 | 7.8 | -2.9 | +6.6 | 234.5 | -0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:C-T3_5 sign=below 0 | 1/5 | down | yes | 170.80 | +0.1 | +1.4 | 48.4 | +1.9 | 7.8 | -2.9 | +6.3 | 231.2 | -0.0 | +0.1 |  |  | 0.000 |
| BTC | single | 1m:C-FRAMA16 sign=above 0 | 1/5 | up | yes | 144.49 | +0.2 | +1.6 | 48.5 | +1.9 | 7.9 | -2.9 | +6.9 | 230.5 | +0.0 | -0.1 |  |  | 0.000 |
| BTC | single | 1m:C-SWAK_GAUSS20 sign=below 0 | 1/5 | down | yes | 152.51 | +0.2 | +1.5 | 48.8 | +2.3 | 7.8 | -2.9 | +6.7 | 230.0 | -0.0 | -0.0 |  |  | 0.000 |
| BTC | single | 1m:C-SWAK_BUTTER20 sign=below 0 | 1/5 | down | yes | 136.91 | +0.2 | +1.7 | 49.0 | +2.5 | 7.8 | -2.8 | +7.0 | 229.5 | -0.0 | +0.0 |  |  | 0.000 |

## Tables

One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.

| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | 0.01 | 9d1ccb72747bc124153fc40e2fa9847351aaa08e7ef5285be4c6535c08d0f87d |
| BTC~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | b4937c5de30caa5ac248a3e6560746900048cc00782e162663b3fac9074f8f75 |
| BTC~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | a3b45b893447da34ac1722e73a360b07086343cca9f9e70bbe12f883d770b8d9 |
| BTC~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | c30b4afb1f96781cee9abcdb1f2677faf91e1d8f01c1a1659c4584062f5e2e9c |
| ETH | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | 0.01 | 9fe17794ba5fbbed13d787f1de81cf99f79c77604f28fb9526460adc074415d2 |
| ETH~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 8f0a2c8d6fbd438d290e33c3d41c18b51be914906427717dad7bcdc29d4e89ee |
| ETH~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 2a8b4cab14d32c90b2225ce0afb9c48fe531b8981a6c7ad782792259f591d666 |
| ETH~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | bc2119d54a90f90f57fd988353d536ce2277935e188419482f46917fab2ba088 |
| SOL | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | 0.0001 | a377481930b89890b819b9b8248d222e64978599d02d0e4176437f24de332aad |
| SOL~twin1 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 6404bf4ada7cd1dd6af3bf3c08d716af9c750c19fd4625e12b66674e6e07602d |
| SOL~twin2 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | d9b9b5f27e023a4cb75cde9f9d2447c722022750c45d5122de0e89f7da16833b |
| SOL~twin3 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 9164b2c2588891dac73f1f90cd3691f3a7eb5bd9c3120053033a0cd5da7676be |
| XRP | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | 1e-05 | 3699259117c03e54eed509802208a55d643748ee8b40fe2655a348fe7567fc75 |
| XRP~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | e339acec7d510050cd71a8ea044988352991121b788621ab774af59039db7f4c |
| XRP~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | e15a9eec9b69e1049d9eb927369d0e93abd98e8c1081783bd219d1ca1d9a5760 |
| XRP~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | c095147bb4efd57f47f203268f8b33b43abf6cd9cf433fd9303ada8e276dc418 |
