# OR-HM1 heat map: league (coin price, discovery only)

Coins: BTC, ETH, SOL, XRP. No-signal twins: BTC~twin1, BTC~twin2, BTC~twin3, ETH~twin1, ETH~twin2, ETH~twin3, SOL~twin1, SOL~twin2, SOL~twin3, XRP~twin1, XRP~twin2, XRP~twin3.
Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute's open. A map, not a validated rule.

## Hot spots against chance

Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent's other events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest set, a higher replicate share and the BHY column are evidence.

| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |
|---|---|---|---|---|---|---|---|---|---|---|
| real | single | 1,760 | 41 | 2 | 0.0488 | 1 | 276 | 110 | 0.3986 | 68 |
| real | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| real | pair | 34,400 | 85 | 1 | 0.0118 | 0 | 565 | 21 | 0.0372 | 0 |
| real | triple | 22,370 | 66 | 0 | 0.0 | 0 | 475 | 17 | 0.0358 | 0 |
| twin (median of 3) | single | 1,760 | 1 (0 to 6) | 0 |  | 0 | 4 (1 to 4) | 0 (0 to 1) | 0.0 | 0 (0 to 1) |
| twin (median of 3) | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| twin (median of 3) | pair | 32,545 | 18 (10 to 20) | 0 | 0.0 | 0 | 71 (69 to 95) | 0 (0 to 2) | 0.0 | 0 |
| twin (median of 3) | triple | 4,135 | 3 (2 to 6) | 0 | 0.0 | 0 | 21 (17 to 21) | 0 | 0.0 | 0 |

Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): move_heat None, move_edge None, odds_edge 5.404, odds_heat 13.772.

## Direction: every event level, nothing cut (Amendment 3)

The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods (30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.

| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |
|---|---|---|---|---|---|---|---|---|
| 1 | real | 334 | 0.5838 | 0.1497 | 0.409 | 77.092 | 178.568 | 0.404 |
| 1 | twin | 1,002 | 0.494 | 0.023 | -0.01 | 21.769 | 75.988 | 0.213 |
| 5 | real | 334 | 0.6766 | 0.1527 | 0.621 | 70.023 | 101.445 | 0.382 |
| 5 | twin | 1,002 | 0.497 | 0.019 | -0.015 | 18.842 | 27.508 | 0.218 |
| 15 | real | 334 | 0.6437 | 0.1617 | 0.734 | 48.847 | 59.636 | 0.387 |
| 15 | twin | 1,002 | 0.511 | 0.015 | 0.027 | 17.397 | 35.196 | 0.221 |
| 30 | real | 334 | 0.5868 | 0.1437 | 0.555 | 36.932 | 51.251 | 0.353 |
| 30 | twin | 1,002 | 0.49 | 0.022 | -0.033 | 15.366 | 26.549 | 0.232 |
| 60 | real | 334 | 0.6048 | 0.1377 | 0.466 | 25.5 | 36.136 | 0.35 |
| 60 | twin | 1,002 | 0.512 | 0.017 | 0.041 | 12.311 | 24.085 | 0.222 |

Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.

Top 12 at 1 minute by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | WHALEP:Sweep=buy sweep | down | 134.45 | 50.1 | 50.4 | +1.6 | +1.3 | +5.7 | 178.6 | 7.9 | +0.4 | +5.8 | -5.8 | none |
| ETH | WHALEP:Sweep=sell sweep | up | 140.90 | 49.9 | 50.6 | +1.3 | +0.9 | +4.4 | 131.9 | 8.1 | +0.3 | +5.8 | -5.9 | none |
| XRP | WHALEP:Sweep=sell sweep | up | 24.32 | 48.5 | 51.2 | +5.0 | +3.3 | +6.5 | 79.6 | 8.6 | +1.5 | +11.7 | -11.3 | none |
| ETH | WHALE:Sweep=sell sweep | up | 25.73 | 50.7 | 52.9 | +3.6 | +3.1 | +6.5 | 78.6 | 9.1 | +1.3 | +8.9 | -9.3 | hot, replicates, BHY |
| ETH | WHALE:Sweep=buy sweep | down | 24.06 | 50.5 | 52.4 | +3.7 | +3.1 | +5.5 | 74.0 | 9.1 | +1.6 | +8.4 | -8.9 | none |
| BTC | WHALE:Sweep=buy sweep | down | 36.40 | 51.2 | 50.6 | +4.1 | +1.8 | +4.2 | 65.8 | 8.6 | +1.2 | +4.9 | -4.8 | hot, replicates, BHY |
| ETH | BOOKP:Imb1=low (falling in) | down | 27.51 | 49.8 | 51.2 | +2.4 | +2.2 | +4.3 | 60.9 | 8.4 | +0.9 | +5.6 | -5.5 | none |
| ETH | CVDP:PxDiv60=high (rising in) | down | 39.71 | 48.1 | 50.1 | +1.3 | +1.4 | +3.4 | 55.6 | 7.8 | +0.3 | +5.3 | -5.3 | none |
| ETH | BOOKP:Imb1=high (rising in) | up | 28.36 | 50.0 | 51.5 | +2.2 | +1.9 | +3.7 | 54.9 | 8.7 | +0.9 | +6.2 | -6.6 | hot |
| ETH | LIQMAP:Skew=high (rising in) | down | 12.10 | 51.1 | 53.6 | +4.8 | +4.3 | +5.6 | 52.4 | 9.6 | +2.1 | +7.6 | -7.9 | hot, replicates, BHY |
| SOL | WHALEP:Sweep=sell sweep | up | 56.92 | 47.4 | 47.3 | +2.3 | +0.8 | +2.3 | 44.8 | 7.5 | +0.6 | +9.2 | -9.3 | none |
| BTC | WHALE:Sweep=sell sweep | up | 39.03 | 51.5 | 50.0 | +3.4 | +1.1 | +2.8 | 44.2 | 8.4 | +0.9 | +5.0 | -4.9 | hot, replicates, BHY |

Top 8 at 1 minute by share right over base on B (at least 0.2 windows per day; the best twin level reaches 12.92 points, the 99th percentile 6.95):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | LS:Global z=very low | up | 0.45 | 166 | 59.0 | +14.0 | +3.4 | 11.0 | +4.1 | -8.4 | none |
| BTC | LS:TopAcc z=very low | up | 0.41 | 149 | 60.4 | +13.8 | +3.4 | 11.4 | +3.9 | -4.1 | hot, replicates, BHY |
| BTC | PREM:PredMinusLast=high (cooling) | down | 0.36 | 130 | 60.0 | +13.5 | +2.8 | 10.2 | +2.7 | -3.8 | none |
| BTC | LS:Global z=very low | up | 0.50 | 184 | 59.8 | +13.2 | +3.3 | 10.2 | +2.7 | -3.9 | hot, replicates, BHY |
| BTC | LS:Global z=very high | down | 0.50 | 181 | 59.1 | +12.6 | +2.6 | 10.5 | +3.0 | -3.4 | hot, replicates |
| SOL | LS:TopAcc z=low (falling in) | up | 1.34 | 489 | 54.8 | +9.8 | +3.6 | 8.0 | +1.2 | -8.2 | none |
| BTC | PREM:PredFund=very low | down | 0.35 | 127 | 55.9 | +9.4 | +1.5 | 9.9 | +2.5 | -5.8 | none |
| BTC | LS:TopAcc z=very high | down | 0.41 | 151 | 55.6 | +9.2 | +1.9 | 8.7 | +1.3 | -4.9 | hot |

Top 12 at 5 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | WHALEP:Sweep=sell sweep | up | 128.29 | 51.1 | 50.8 | +0.8 | +0.8 | +4.2 | 101.4 | 8.1 | +0.3 | +14.6 | -7.3 | hot, replicates, BHY |
| ETH | WHALEP:Sweep=buy sweep | down | 122.75 | 50.8 | 50.4 | +0.8 | +0.8 | +3.9 | 93.3 | 7.9 | +0.4 | +14.7 | -7.1 | hot, replicates, BHY |
| BTC | WHALE:Sweep=buy sweep | down | 35.83 | 51.6 | 52.1 | +2.2 | +2.1 | +4.7 | 73.8 | 8.6 | +1.2 | +11.8 | -5.8 | hot, replicates, BHY |
| ETH | BOOKP:Imb1=low (falling in) | down | 24.15 | 52.4 | 52.5 | +2.9 | +2.9 | +5.5 | 70.5 | 8.4 | +0.9 | +13.7 | -6.9 | hot, replicates, BHY |
| ETH | BOOKP:Imb1=high (rising in) | up | 24.77 | 53.2 | 52.8 | +2.8 | +2.8 | +5.4 | 69.0 | 8.7 | +0.9 | +14.9 | -8.1 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=high (rising in) | down | 11.05 | 53.1 | 54.7 | +5.1 | +5.0 | +6.7 | 55.1 | 9.6 | +2.1 | +17.5 | -9.7 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=low (falling in) | up | 13.55 | 48.3 | 52.6 | +4.4 | +4.0 | +6.1 | 54.9 | 8.1 | +1.1 | +21.5 | -11.9 | none |
| ETH | WHALE:Sweep=buy sweep | down | 23.74 | 50.4 | 52.0 | +2.3 | +2.3 | +4.3 | 53.9 | 9.1 | +1.6 | +19.5 | -10.6 | none |
| SOL | WHALEP:Sweep=buy sweep | down | 50.24 | 49.2 | 49.2 | +1.5 | +1.0 | +2.8 | 48.3 | 7.5 | +0.7 | +21.6 | -11.2 | none |
| BTC | WHALE:Sweep=sell sweep | up | 38.36 | 52.3 | 51.0 | +1.5 | +1.2 | +3.2 | 47.3 | 8.4 | +0.9 | +11.9 | -6.0 | hot, replicates, BHY |
| XRP | WHALEP:Sweep=sell sweep | up | 24.00 | 50.5 | 50.4 | +2.2 | +1.7 | +3.4 | 39.9 | 8.6 | +1.5 | +26.3 | -13.5 | hot, replicates, BHY |
| SOL | BOOKP:Imb1=high (rising in) | up | 24.93 | 45.6 | 49.8 | +1.9 | +1.6 | +3.2 | 39.7 | 7.7 | +0.8 | +21.1 | -10.8 | none |

Top 8 at 5 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 12.93 points, the 99th percentile 5.82):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | PREM:PredMinusLast=high (cooling) | down | 0.33 | 130 | 63.8 | +14.0 | +3.2 | 10.2 | +2.7 | -4.7 | none |
| SOL | LS:Global z=low (recovering) | down | 0.43 | 158 | 58.2 | +10.5 | +2.2 | 10.8 | +4.0 | -10.7 | none |
| BTC | LS:Global z=very high | down | 0.50 | 181 | 59.7 | +9.8 | +2.6 | 10.5 | +3.0 | -4.4 | none |
| BTC | LS:TopPos z=high (cooling) | down | 0.58 | 213 | 59.6 | +9.8 | +3.1 | 9.9 | +2.4 | -4.6 | none |
| BTC | LS:TopAcc z=very low | up | 0.41 | 149 | 59.1 | +9.5 | +2.4 | 11.4 | +3.9 | -4.8 | none |
| ETH | PREM:PredFund=very low | up | 0.61 | 234 | 59.0 | +9.0 | +2.6 | 8.6 | +0.8 | -15.4 | none |
| ETH | LS:Global z=high (cooling) | up | 0.48 | 176 | 58.0 | +8.0 | +2.1 | 8.0 | +0.2 | -7.5 | none |
| BTC | LS:Global z=low (recovering) | down | 0.50 | 184 | 57.6 | +7.7 | +2.0 | 10.8 | +3.4 | -4.8 | hot |

Top 12 at 15 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | WHALE:Sweep=buy sweep | down | 30.74 | 51.7 | 52.0 | +2.0 | +1.9 | +4.5 | 59.6 | 8.6 | +1.2 | +21.0 | -8.5 | hot, replicates, BHY |
| ETH | WHALEP:Sweep=buy sweep | down | 78.24 | 50.5 | 50.2 | +0.8 | +0.7 | +3.9 | 58.1 | 7.9 | +0.4 | +27.0 | -10.5 | hot, replicates, BHY |
| ETH | BOOKP:Imb1=high (rising in) | up | 16.94 | 55.2 | 53.3 | +3.0 | +2.9 | +4.8 | 49.8 | 8.7 | +0.9 | +25.8 | -12.0 | hot, replicates, BHY |
| ETH | WHALE:Sweep=buy sweep | down | 21.20 | 50.7 | 51.8 | +2.4 | +2.3 | +4.6 | 49.6 | 9.1 | +1.6 | +34.1 | -14.7 | hot, replicates, BHY |
| ETH | WHALE:Net15=high (rising in) | down | 22.71 | 50.2 | 51.5 | +2.1 | +2.1 | +4.2 | 47.3 | 8.2 | +0.7 | +23.3 | -9.4 | none |
| ETH | WHALEP:Sweep=sell sweep | up | 79.93 | 51.3 | 50.9 | +0.6 | +0.6 | +3.0 | 46.7 | 8.1 | +0.3 | +26.5 | -10.9 | hot, replicates, BHY |
| XRP | WHALEP:Sweep=sell sweep | up | 21.18 | 51.8 | 51.4 | +2.5 | +2.2 | +4.6 | 46.2 | 8.6 | +1.5 | +44.8 | -19.1 | hot, replicates, BHY |
| BTC | WHALE:Net15=high (rising in) | down | 26.05 | 51.2 | 51.7 | +1.6 | +1.6 | +3.5 | 41.6 | 8.1 | +0.6 | +13.6 | -5.4 | hot, replicates, BHY |
| ETH | BOOKP:Imb1=low (falling in) | down | 16.30 | 53.9 | 51.8 | +2.4 | +2.4 | +3.8 | 39.1 | 8.4 | +0.9 | +24.3 | -10.0 | hot, replicates, BHY |
| ETH | CVDP:PxDiv60=high (rising in) | down | 27.07 | 49.9 | 50.9 | +1.4 | +1.4 | +3.3 | 38.8 | 7.8 | +0.3 | +24.2 | -9.7 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=high (rising in) | down | 8.49 | 55.0 | 54.0 | +4.6 | +4.5 | +4.6 | 38.3 | 9.6 | +2.1 | +30.4 | -13.6 | hot, replicates, BHY |
| BTC | WHALE:Sweep=sell sweep | up | 32.87 | 52.7 | 51.0 | +1.2 | +1.1 | +3.0 | 37.8 | 8.4 | +0.9 | +20.7 | -8.8 | hot, replicates, BHY |

Top 8 at 15 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 7.54 points, the 99th percentile 5.41):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LS:Global z=low (recovering) | down | 0.50 | 184 | 58.2 | +8.1 | +2.2 | 10.8 | +3.4 | -6.6 | none |
| BTC | LS:TopAcc z=very high | down | 0.41 | 151 | 57.6 | +7.6 | +1.9 | 8.7 | +1.3 | -9.1 | none |
| BTC | WHALEP:Count60=high (cooling) | up | 0.98 | 436 | 57.1 | +7.3 | +2.7 | 7.5 | -0.1 | -8.9 | none |
| SOL | LS:TopPos z=low (recovering) | up | 0.65 | 241 | 56.0 | +7.1 | +2.4 | 9.3 | +2.4 | -15.2 | none |
| SOL | PREM:PredMinusLast=very low | up | 0.50 | 234 | 56.0 | +7.0 | +1.6 | 8.4 | +1.5 | -20.7 | none |
| BTC | LS:Global z=very high | down | 0.49 | 181 | 56.9 | +6.9 | +1.8 | 10.5 | +3.0 | -6.2 | none |
| XRP | LIQMAP:Skew=very high | down | 3.29 | 1,696 | 55.5 | +6.2 | +3.6 | 9.1 | +2.1 | -20.8 | hot |
| XRP | LS:TopAcc z=very low | down | 0.46 | 172 | 54.7 | +5.4 | +1.3 | 10.2 | +3.1 | -19.5 | none |

Top 12 at 30 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | WHALE:Net15=high (rising in) | down | 19.53 | 50.4 | 51.8 | +2.7 | +2.6 | +4.8 | 51.3 | 8.2 | +0.7 | +33.8 | -12.8 | hot, replicates, BHY |
| BTC | WHALE:Sweep=buy sweep | down | 24.12 | 51.5 | 51.7 | +1.9 | +1.9 | +4.3 | 46.1 | 8.6 | +1.2 | +29.8 | -11.1 | hot, replicates, BHY |
| BTC | WHALE:Sweep=sell sweep | up | 25.62 | 52.8 | 51.7 | +1.6 | +1.6 | +3.7 | 40.2 | 8.4 | +0.9 | +29.2 | -11.8 | hot, replicates, BHY |
| ETH | WHALE:Sweep=buy sweep | down | 17.52 | 50.4 | 51.3 | +2.2 | +2.1 | +3.9 | 37.0 | 9.1 | +1.6 | +48.0 | -19.0 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 6.66 | 55.9 | 54.7 | +5.6 | +5.5 | +5.0 | 36.8 | 9.6 | +2.1 | +42.1 | -18.0 | hot, replicates, BHY |
| XRP | WHALEP:Sweep=sell sweep | up | 17.33 | 52.5 | 51.6 | +2.2 | +2.1 | +4.0 | 35.8 | 8.6 | +1.5 | +62.1 | -25.5 | hot, replicates, BHY |
| ETH | CVDP:Div15=low (falling in) | down | 16.89 | 49.2 | 51.1 | +2.0 | +2.0 | +3.4 | 33.6 | 7.6 | +0.0 | +32.0 | -11.8 | none |
| ETH | BOOKP:Imb1=low (falling in) | down | 11.55 | 54.0 | 51.8 | +2.7 | +2.7 | +3.2 | 30.7 | 8.4 | +0.9 | +34.7 | -13.6 | hot, replicates, BHY |
| SOL | WHALE:Net15=high (rising in) | down | 15.26 | 50.2 | 50.7 | +2.0 | +2.0 | +3.2 | 30.6 | 7.1 | +0.4 | +43.9 | -17.0 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=high (rising in) | down | 7.48 | 51.2 | 53.5 | +4.1 | +4.0 | +4.2 | 29.8 | 8.7 | +1.7 | +50.9 | -21.5 | none |
| BTC | BOOKP:Imb1=high (rising in) | up | 8.48 | 54.9 | 53.6 | +3.5 | +3.5 | +4.1 | 29.3 | 8.2 | +0.7 | +27.3 | -11.7 | hot, replicates, BHY |
| BTC | WHALE:Net15=low (falling in) | up | 24.35 | 51.8 | 51.3 | +1.2 | +1.2 | +2.6 | 28.7 | 8.0 | +0.5 | +20.0 | -7.8 | hot, replicates |

Top 8 at 30 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 12.43 points, the 99th percentile 6.07):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | LS:TopAcc z=very high | up | 0.43 | 164 | 62.8 | +13.2 | +3.1 | 7.0 | +0.2 | -23.2 | none |
| ETH | LS:TopAcc z=low (recovering) | down | 0.41 | 162 | 59.3 | +10.1 | +2.6 | 6.7 | -0.8 | -16.8 | none |
| BTC | PREM:PredMinusLast=very high | down | 0.27 | 142 | 57.7 | +8.0 | +1.4 | 7.1 | -0.3 | -12.8 | none |
| XRP | LS:TopAcc z=very low | down | 0.44 | 172 | 57.0 | +7.6 | +2.2 | 10.2 | +3.1 | -26.3 | hot, replicates |
| BTC | LS:TopAcc z=very high | down | 0.39 | 151 | 57.0 | +7.2 | +1.8 | 8.7 | +1.3 | -12.1 | none |
| ETH | LS:Global z=low (recovering) | down | 0.46 | 179 | 55.9 | +6.7 | +2.0 | 9.6 | +2.1 | -14.4 | none |
| XRP | LIQMAP:Skew=low (recovering) | up | 3.04 | 1,955 | 55.6 | +6.2 | +3.7 | 8.5 | +1.4 | -26.8 | none |
| ETH | BOOKP:Imb1=very high | up | 3.92 | 2,916 | 56.9 | +6.2 | +4.6 | 9.8 | +2.0 | -17.7 | hot, replicates, BHY |

Top 12 at 60 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | WHALE:Sweep=sell sweep | up | 17.52 | 52.7 | 52.6 | +2.1 | +2.1 | +4.5 | 36.1 | 8.4 | +0.9 | +40.7 | -16.4 | hot, replicates, BHY |
| ETH | CVDP:Div15=high (rising in) | up | 14.30 | 50.9 | 53.2 | +2.0 | +2.0 | +3.7 | 29.2 | 7.9 | +0.2 | +46.1 | -17.6 | none |
| XRP | WHALEP:Sweep=sell sweep | up | 13.05 | 53.1 | 51.6 | +2.1 | +2.0 | +3.4 | 25.7 | 8.6 | +1.5 | +84.7 | -34.2 | hot, replicates, BHY |
| ETH | WHALE:Net15=high (rising in) | down | 15.06 | 50.2 | 50.4 | +1.7 | +1.7 | +3.0 | 25.7 | 8.2 | +0.7 | +49.0 | -17.8 | hot, replicates, BHY |
| BTC | BOOKP:Imb1=high (rising in) | up | 6.25 | 55.9 | 54.5 | +4.0 | +4.0 | +3.8 | 25.1 | 8.2 | +0.7 | +38.4 | -16.2 | hot, replicates, BHY |
| BTC | CVDP:Div15=very low | down | 9.32 | 49.6 | 51.8 | +2.4 | +2.4 | +2.9 | 22.1 | 7.4 | -0.0 | +26.5 | -9.2 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 5.04 | 56.1 | 52.9 | +4.2 | +4.3 | +3.4 | 21.5 | 9.6 | +2.1 | +57.7 | -24.0 | hot, replicates, BHY |
| SOL | LIQMAP:Skew=high (rising in) | down | 5.57 | 52.7 | 52.5 | +3.7 | +3.7 | +3.2 | 20.6 | 7.9 | +1.1 | +69.1 | -30.1 | none |
| SOL | CVDP:Div15=high (rising in) | up | 13.00 | 48.3 | 51.6 | +1.6 | +1.6 | +2.7 | 20.4 | 7.1 | +0.2 | +55.0 | -21.6 | hot |
| ETH | WHALE:Sweep=buy sweep | down | 13.11 | 50.7 | 50.2 | +1.5 | +1.5 | +2.5 | 19.6 | 9.1 | +1.6 | +67.0 | -25.2 | hot, replicates |
| BTC | CVDP:Div15=low (recovering) | down | 8.39 | 50.2 | 51.8 | +2.3 | +2.3 | +2.6 | 19.6 | 7.7 | +0.3 | +27.2 | -9.5 | none |
| ETH | BOOKP:Imb1=low (falling in) | down | 8.00 | 53.5 | 50.9 | +2.3 | +2.3 | +2.4 | 18.1 | 8.4 | +0.9 | +49.9 | -18.9 | hot, replicates |

Top 8 at 60 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 11.32 points, the 99th percentile 6.27):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LS:TopAcc z=very high | down | 0.37 | 151 | 60.9 | +11.5 | +2.8 | 8.7 | +1.3 | -16.5 | none |
| XRP | LS:TopAcc z=very low | down | 0.40 | 172 | 58.7 | +9.1 | +2.3 | 10.2 | +3.1 | -32.4 | hot, replicates |
| ETH | LS:Global z=high (cooling) | down | 0.40 | 176 | 57.4 | +8.7 | +2.1 | 4.8 | -2.7 | -28.7 | none |
| BTC | LS:Global z=low (recovering) | down | 0.46 | 184 | 57.6 | +8.2 | +2.1 | 10.8 | +3.4 | -11.6 | none |
| XRP | PREM:PredMinusLast=very low | up | 0.62 | 376 | 57.2 | +7.7 | +2.1 | 7.6 | +0.6 | -45.1 | none |
| BTC | PREM:PredMinusLast=very high | down | 0.23 | 142 | 57.0 | +7.6 | +1.3 | 7.1 | -0.3 | -15.7 | none |
| BTC | PREM:PredMinusLast=high (cooling) | down | 0.23 | 130 | 56.2 | +6.7 | +1.0 | 10.2 | +2.7 | -11.1 | none |
| SOL | LS:TopPos z=very high | up | 0.55 | 232 | 56.5 | +6.4 | +1.6 | 7.3 | +0.4 | -35.5 | none |

## Every TA by heat

Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the direction the reading's current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). The horizon is the one with the most heat on A; the B columns score A's directions on B, so a reading with no information scores about zero.

| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |
|---|---|---|---|---|---|---|---|---|
| real | events | 62 | 0.7581 | 0.129 | 0.0484 | 6.113 | 57.104 | 70.754 |
| twin | events | 185 | 0.5297 | 0.0378 | 0.0054 | 1.3 | 39.732 | 165.025 |

Top 40 readings by events heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| XRP | WHALEP:Sweep | 60 | 34.4 | +70.8 | +2.4 |
| ETH | WHALEP:Sweep | 5 | 22.6 | +68.4 | +4.7 |
| XRP | BOOKP:Imb1 | 60 | 68.7 | +65.3 | +2.2 |
| BTC | CVDP:Div15 | 60 | 20.7 | +57.6 | +3.5 |
| ETH | WHALEP:Net15 | 60 | 34.5 | +47.3 | +1.9 |
| BTC | WHALEP:Net15 | 60 | 28.3 | +47.1 | +3.0 |
| SOL | WHALEP:Net15 | 60 | 13.3 | +39.6 | +2.3 |
| SOL | CVDP:PxDiv60 | 60 | 77.1 | +36.2 | +1.3 |
| ETH | LIQMAP:Skew | 60 | 16.1 | +33.6 | +1.5 |
| XRP | LS:TopPosChg60 | 60 | 14.7 | +33.3 | +1.8 |
| ETH | WHALEP:Count60 | 60 | 20.7 | +30.9 | +1.7 |
| ETH | LS:TopAcc z | 60 | 6.1 | +28.7 | +3.1 |
| XRP | WHALE:Count60 | 60 | 47.4 | +27.6 | +1.6 |
| ETH | CVDP:PxDiv60 | 60 | 25.2 | +26.7 | +1.1 |
| SOL | CVDP:Div15 | 30 | 63.5 | +23.3 | +1.3 |
| BTC | LS:TopPosChg60 | 30 | 14.2 | +22.0 | +2.6 |
| SOL | LS:TopPos z | 60 | 14.9 | +20.5 | +1.5 |
| SOL | WHALE:Count60 | 60 | 85.9 | +15.5 | +0.7 |
| XRP | WHALE:Sweep | 15 | 9.3 | +15.5 | +1.1 |
| XRP | LIQMAP:Skew | 60 | 15.6 | +14.3 | +0.8 |
| SOL | LIQMAP:Skew | 30 | 11.0 | +13.3 | +1.2 |
| SOL | WHALE:Sweep | 30 | 15.8 | +12.6 | +0.7 |
| BTC | CVDP:PxDiv60 | 15 | 19.7 | +11.7 | +1.0 |
| SOL | LS:TopPosChg60 | 60 | 6.4 | +10.9 | +0.8 |
| XRP | LS:Global z | 30 | 5.6 | +10.5 | +1.3 |
| XRP | PREM:PredMinusLast | 60 | 23.2 | +10.4 | +0.7 |
| SOL | BOOKP:Imb1 | 60 | 54.8 | +9.3 | +0.4 |
| BTC | PREM:PredFund | 30 | 13.6 | +8.4 | +1.9 |
| BTC | LS:TopAcc z | 60 | 17.9 | +8.4 | +1.5 |
| XRP | PREM:PredFund | 60 | 16.8 | +7.2 | +1.0 |
| BTC | PREM:PredMinusLast | 60 | 12.3 | +6.6 | +0.7 |
| ETH | LS:Global z | 60 | 14.4 | +5.6 | +0.5 |
| BTC | BOOKP:Imb1 | 30 | 9.7 | +5.6 | +0.5 |
| ETH | CVDP:Div15 | 60 | 14.9 | +5.4 | +0.2 |
| BTC | LS:Global z | 30 | 16.4 | +5.2 | +1.3 |
| BTC | LS:TopPos z | 60 | 8.0 | +5.1 | +0.7 |
| XRP | WHALEP:Net15 | 60 | 11.1 | +5.1 | +0.5 |
| BTC | WHALE:Net15 | 60 | 12.3 | +5.0 | +0.3 |
| XRP | WHALE:Net15 | 60 | 4.0 | +4.7 | +0.6 |
| ETH | LS:TopPosChg60 | 60 | 10.1 | +4.1 | +0.3 |

## Top 3 replicating by heat on B (windows per day x move, bps per day)

1 of 3 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | single | WHALEP:Sweep=sell sweep | 5 | up | yes | 128.29 | +0.3 | +0.8 | 50.8 | +0.8 | 8.1 | -7.3 | +3.8 | 41.2 | +0.2 | +0.0 |  |  | 0.023 |
| SOL | pair | BOOKP:Imb1=very high / WHALE:Sweep=sell sweep | 5 | up | no | 0.64 | +9.9 | +5.5 | 54.7 | +6.8 | 9.6 | -24.1 | +2.9 | 6.3 | +5.2 |  | +8.9 | +9.4 | 1.000 |
| SOL | single | LS:Global z=low (falling in) | 1 | up | no | 1.55 | +2.0 | +6.1 | 51.9 | +6.8 | 7.9 | -8.1 | +3.1 | 3.1 | +0.0 | -0.1 |  |  | 0.185 |

## Top 3 replicating by move per event on B (bps; at least 0.2 windows per day)

1 of 3 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | single | WHALEP:Sweep=sell sweep | 5 | up | yes | 128.29 | +0.3 | +0.8 | 50.8 | +0.8 | 8.1 | -7.3 | +3.8 | 41.2 | +0.2 | +0.0 |  |  | 0.023 |
| SOL | pair | BOOKP:Imb1=very high / WHALE:Sweep=sell sweep | 5 | up | no | 0.64 | +9.9 | +5.5 | 54.7 | +6.8 | 9.6 | -24.1 | +2.9 | 6.3 | +5.2 |  | +8.9 | +9.4 | 1.000 |
| SOL | single | LS:Global z=low (falling in) | 1 | up | no | 1.55 | +2.0 | +6.1 | 51.9 | +6.8 | 7.9 | -8.1 | +3.1 | 3.1 | +0.0 | -0.1 |  |  | 0.185 |

## Top 40 replicating by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)

32 of 77 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | single | LS:TopAcc z=very low | 1 | up | yes | 0.41 | +2.6 | +12.7 | 60.4 | +13.8 | 11.4 | -4.1 | +3.4 | 5.2 | +0.0 | +0.1 |  |  | 0.054 |
| BTC | single | LS:Global z=very low | 1 | up | yes | 0.50 | +1.4 | +11.1 | 59.8 | +13.2 | 10.2 | -3.9 | +3.3 | 5.6 | +0.0 | +1.4 |  |  | 0.036 |
| ETH | single | BOOKP:Imb1=very high | 5/15/30/60 | up | yes | 3.92 | +2.1 | +6.2 | 56.9 | +6.2 | 9.8 | -17.7 | +4.6 | 24.1 | +1.5 | +0.5 |  |  | 0.002 |
| SOL | single | LS:Global z=low (falling in) | 1 | up | yes | 1.55 | +2.0 | +6.1 | 51.9 | +6.8 | 7.9 | -8.1 | +2.9 | 9.5 | +0.0 | -0.9 |  |  | 0.070 |
| ETH | single | BOOKP:Imb1=high (cooling) | 5/15/30/60 | up | yes | 2.65 | +2.9 | +5.8 | 57.0 | +5.8 | 8.9 | -22.3 | +3.3 | 15.4 | +2.9 | -1.1 |  |  | 0.031 |
| ETH | single | BOOKP:Imb1=very low | 15/30/60 | down | yes | 4.16 | +2.2 | +5.7 | 54.9 | +5.7 | 8.6 | -13.6 | +4.7 | 23.9 | +1.7 | +0.5 |  |  | 0.001 |
| ETH | single | LIQMAP:Skew=high (rising in) | 1/5/15/30/60 | down | yes | 6.66 | -0.0 | +5.5 | 54.7 | +5.6 | 9.6 | -18.0 | +5.0 | 36.8 | -0.5 | +0.2 |  |  | 0.001 |
| XRP | single | LIQMAP:Skew=very low | 15/30/60 | up | yes | 3.09 | +2.8 | +4.9 | 54.6 | +5.2 | 9.3 | -29.0 | +2.9 | 15.1 | +3.1 | -0.6 |  |  | 0.095 |
| ETH | single | BOOKP:Imb1=low (recovering) | 15/30 | down | yes | 3.48 | +1.5 | +4.9 | 54.0 | +4.9 | 8.4 | -13.1 | +3.6 | 16.9 | +1.5 | -0.2 |  |  | 0.020 |
| ETH | single | LIQMAP:Skew=very low | 1/5 | up | yes | 4.89 | +1.1 | +4.7 | 54.9 | +5.6 | 10.3 | -13.2 | +4.1 | 23.0 | +0.0 | +0.1 |  |  | 0.005 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.14 | +0.7 | +4.1 | 53.9 | +4.1 | 8.5 | -11.5 | +3.2 | 20.8 | +0.9 | +0.4 |  |  | 0.031 |
| BTC | single | BOOKP:Imb1=high (rising in) | 15/30/60 | up | yes | 6.25 | +1.5 | +4.0 | 54.5 | +4.0 | 8.2 | -16.2 | +3.8 | 25.1 | +1.8 | -0.1 |  |  | 0.009 |
| SOL | single | BOOKP:Imb1=very high | 5/15/30 | up | yes | 5.79 | +2.0 | +3.5 | 52.2 | +4.3 | 8.1 | -13.3 | +3.6 | 20.5 | +1.8 | +0.1 |  |  | 0.016 |
| ETH | single | WHALE:Sweep=sell sweep | 1/30 | up | yes | 25.73 | +0.4 | +3.1 | 52.9 | +3.6 | 9.1 | -9.3 | +6.5 | 78.6 | +0.0 | -0.4 |  |  | 0.000 |
| ETH | single | BOOKP:Imb1=high (rising in) | 5/15/30 | up | yes | 16.94 | -0.4 | +2.9 | 53.3 | +3.0 | 8.7 | -12.0 | +4.8 | 49.8 | -0.5 | -0.0 |  |  | 0.001 |
| ETH | single | BOOKP:Imb1=low (falling in) | 5/15/30/60 | down | yes | 24.15 | +0.2 | +2.9 | 52.5 | +2.9 | 8.4 | -6.9 | +5.5 | 70.5 | +0.1 | -0.0 |  |  | 0.000 |
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 9.23 | -0.4 | +2.9 | 53.3 | +2.9 | 9.1 | -16.1 | +3.3 | 26.8 | -0.3 | -0.1 |  |  | 0.027 |
| BTC | single | BOOKP:Imb1=very low | 15 | down | yes | 6.33 | +0.4 | +2.8 | 52.8 | +2.8 | 8.5 | -6.5 | +2.9 | 17.6 | +0.4 | +0.4 |  |  | 0.079 |
| SOL | single | WHALE:Sweep=sell sweep | 1/15 | up | yes | 8.30 | +0.6 | +2.7 | 50.3 | +5.2 | 8.6 | -13.4 | +2.9 | 22.8 | +0.0 | -0.3 |  |  | 0.065 |
| ETH | single | WHALE:Net15=high (rising in) | 30/60 | down | yes | 19.53 | +0.5 | +2.6 | 51.8 | +2.7 | 8.2 | -12.8 | +4.8 | 51.3 | +0.4 | -0.1 |  |  | 0.001 |
| XRP | single | BOOKP:Imb1=high (rising in) | 30/60 | up | yes | 9.87 | +2.7 | +2.6 | 52.1 | +2.7 | 7.8 | -24.1 | +3.3 | 25.7 | +2.4 | +0.4 |  |  | 0.030 |
| ETH | single | WHALE:Sweep=buy sweep | 15/60 | down | yes | 21.20 | +0.2 | +2.3 | 51.8 | +2.4 | 9.1 | -14.7 | +4.6 | 49.6 | +0.2 | -0.0 |  |  | 0.001 |
| XRP | single | WHALEP:Sweep=sell sweep | 5/15/30/60 | up | yes | 21.18 | +2.0 | +2.2 | 51.4 | +2.5 | 8.6 | -19.1 | +4.6 | 46.2 | +1.3 | -0.0 |  |  | 0.001 |
| BTC | single | WHALE:Net15=very high | 15 | down | yes | 12.18 | +0.3 | +2.1 | 52.1 | +2.1 | 7.9 | -4.5 | +2.8 | 25.9 | +0.2 | +0.3 |  |  | 0.073 |
| BTC | single | WHALE:Sweep=sell sweep | 1/5/15/30/60 | up | yes | 17.52 | +1.0 | +2.1 | 52.6 | +2.1 | 8.4 | -16.4 | +4.5 | 36.1 | +0.8 | -0.2 |  |  | 0.001 |
| BTC | single | WHALE:Sweep=buy sweep | 1/5/15/30/60 | down | yes | 35.83 | +0.3 | +2.1 | 52.1 | +2.2 | 8.6 | -5.8 | +4.7 | 73.8 | +0.2 | +0.2 |  |  | 0.001 |
| SOL | single | WHALE:Net15=high (rising in) | 30 | down | yes | 15.26 | +0.8 | +2.0 | 50.7 | +2.0 | 7.1 | -17.0 | +3.2 | 30.6 | +0.8 | +0.1 |  |  | 0.031 |
| XRP | single | WHALEP:Sweep=buy sweep | 15 | down | yes | 18.14 | +0.5 | +1.7 | 51.3 | +2.1 | 8.3 | -19.7 | +3.0 | 31.3 | +0.6 | -0.4 |  |  | 0.054 |
| BTC | single | WHALE:Net15=high (rising in) | 5/15 | down | yes | 26.05 | +0.3 | +1.6 | 51.7 | +1.6 | 8.1 | -5.4 | +3.5 | 41.6 | +0.3 | +0.2 |  |  | 0.016 |
| ETH | single | CVDP:PxDiv60=high (rising in) | 15 | down | yes | 27.07 | +0.2 | +1.4 | 50.9 | +1.4 | 7.8 | -9.7 | +3.3 | 38.8 | +0.1 | -0.1 |  |  | 0.027 |
| ETH | single | WHALEP:Sweep=sell sweep | 5/15/30/60 | up | yes | 128.29 | +0.3 | +0.8 | 50.8 | +0.8 | 8.1 | -7.3 | +4.2 | 101.4 | +0.2 | +0.0 |  |  | 0.002 |
| ETH | single | WHALEP:Sweep=buy sweep | 5/15/30 | down | yes | 122.75 | +0.2 | +0.8 | 50.4 | +0.8 | 7.9 | -7.1 | +3.9 | 93.3 | +0.1 | +0.0 |  |  | 0.005 |
| XRP | triple | BOOKP:Imb1=high (rising in) / WHALEP:Count60=high / LIQMAP:Skew=low | 60 | up | no | 0.32 | +29.9 | +15.3 | 65.0 | +15.5 | 10.5 | -41.6 | +3.3 | 5.0 | +27.9 |  | +12.5 | +12.8 | 1.000 |
| BTC | triple | WHALE:Sweep=buy sweep / CVDP:Div15=low / LIQMAP:Skew=high | 30 | down | no | 0.89 | +5.4 | +11.9 | 61.7 | +11.9 | 10.9 | -10.8 | +4.9 | 10.6 | +5.7 |  | +10.0 | +8.3 | 1.000 |
| BTC | single | LS:Global z=very high | 1 | down | no | 0.50 | +1.9 | +10.0 | 59.1 | +12.6 | 10.5 | -3.4 | +2.6 | 5.0 | -0.0 | -0.1 |  |  | 0.149 |
| BTC | pair | BOOKP:Imb1=high (rising in) / WHALE:Count60=very high | 5 | up | no | 0.46 | +3.6 | +9.2 | 59.0 | +9.5 | 9.5 | -10.0 | +2.5 | 4.2 | +2.5 |  | +8.9 | +10.5 | 1.000 |
| XRP | single | LS:TopAcc z=very low | 30/60 | down | no | 0.40 | -11.4 | +8.9 | 58.7 | +9.1 | 10.2 | -32.4 | +2.3 | 3.6 | -11.5 | +0.4 |  |  | 0.267 |
| ETH | pair | WHALE:Sweep=sell sweep / WHALEP:Net15=very low | 15 | up | no | 0.87 | +2.4 | +8.9 | 59.4 | +9.1 | 10.5 | -16.1 | +3.3 | 7.8 | +2.6 |  | +8.6 | +7.2 | 1.000 |
| ETH | single | LS:Global z=very low | 1 | up | no | 0.51 | +3.6 | +8.6 | 58.3 | +9.0 | 9.9 | -6.1 | +2.3 | 4.4 | +0.0 | +0.3 |  |  | 0.245 |
| ETH | triple | WHALE:Sweep=sell sweep / CVDP:PxDiv60=high / WHALEP:Net15=very low | 15 | up | no | 0.76 | +1.1 | +8.5 | 58.9 | +8.6 | 10.9 | -17.2 | +2.9 | 6.4 | +1.3 |  | +7.7 | +6.8 | 1.000 |

## Top 40 replicating by odds heat on B (windows per day x odds points)

32 of 80 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | single | WHALEP:Sweep=sell sweep | 5/15/30/60 | up | yes | 128.29 | +0.3 | +0.8 | 50.8 | +0.8 | 8.1 | -7.3 | +4.2 | 101.4 | +0.2 | +0.0 |  |  | 0.002 |
| ETH | single | WHALEP:Sweep=buy sweep | 5/15/30 | down | yes | 122.75 | +0.2 | +0.8 | 50.4 | +0.8 | 7.9 | -7.1 | +3.9 | 93.3 | +0.1 | +0.0 |  |  | 0.005 |
| ETH | single | WHALE:Sweep=sell sweep | 1/30 | up | yes | 25.73 | +0.4 | +3.1 | 52.9 | +3.6 | 9.1 | -9.3 | +6.5 | 78.6 | +0.0 | -0.4 |  |  | 0.000 |
| BTC | single | WHALE:Sweep=buy sweep | 1/5/15/30/60 | down | yes | 35.83 | +0.3 | +2.1 | 52.1 | +2.2 | 8.6 | -5.8 | +4.7 | 73.8 | +0.2 | +0.2 |  |  | 0.001 |
| ETH | single | BOOKP:Imb1=low (falling in) | 5/15/30/60 | down | yes | 24.15 | +0.2 | +2.9 | 52.5 | +2.9 | 8.4 | -6.9 | +5.5 | 70.5 | +0.1 | -0.0 |  |  | 0.000 |
| ETH | single | BOOKP:Imb1=high (rising in) | 5/15/30 | up | yes | 24.77 | -0.2 | +2.8 | 52.8 | +2.8 | 8.7 | -8.1 | +5.4 | 69.0 | -0.2 | +0.1 |  |  | 0.000 |
| ETH | single | LIQMAP:Skew=high (rising in) | 1/5/15/30/60 | down | yes | 11.05 | +0.8 | +5.0 | 54.7 | +5.1 | 9.6 | -9.7 | +6.7 | 55.1 | +0.3 | +0.1 |  |  | 0.000 |
| ETH | single | WHALE:Net15=high (rising in) | 30/60 | down | yes | 19.53 | +0.5 | +2.6 | 51.8 | +2.7 | 8.2 | -12.8 | +4.8 | 51.3 | +0.4 | -0.1 |  |  | 0.001 |
| ETH | single | WHALE:Sweep=buy sweep | 15/60 | down | yes | 21.20 | +0.2 | +2.3 | 51.8 | +2.4 | 9.1 | -14.7 | +4.6 | 49.6 | +0.2 | -0.0 |  |  | 0.001 |
| BTC | single | WHALE:Sweep=sell sweep | 1/5/15/30/60 | up | yes | 38.36 | +0.3 | +1.2 | 51.0 | +1.5 | 8.4 | -6.0 | +3.2 | 47.3 | +0.1 | -0.3 |  |  | 0.031 |
| XRP | single | WHALEP:Sweep=sell sweep | 5/15/30/60 | up | yes | 21.18 | +2.0 | +2.2 | 51.4 | +2.5 | 8.6 | -19.1 | +4.6 | 46.2 | +1.3 | -0.0 |  |  | 0.001 |
| BTC | single | WHALE:Net15=high (rising in) | 5/15 | down | yes | 26.05 | +0.3 | +1.6 | 51.7 | +1.6 | 8.1 | -5.4 | +3.5 | 41.6 | +0.3 | +0.2 |  |  | 0.016 |
| ETH | single | CVDP:PxDiv60=high (rising in) | 15 | down | yes | 27.07 | +0.2 | +1.4 | 50.9 | +1.4 | 7.8 | -9.7 | +3.3 | 38.8 | +0.1 | -0.1 |  |  | 0.027 |
| ETH | single | BOOKP:Imb1=very high | 5/15/30/60 | up | yes | 7.12 | +1.6 | +4.8 | 54.9 | +5.0 | 9.8 | -9.3 | +4.8 | 34.5 | +1.0 | -0.0 |  |  | 0.002 |
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 11.92 | -0.0 | +2.7 | 52.7 | +2.8 | 9.1 | -11.3 | +3.5 | 32.4 | +0.0 | +0.3 |  |  | 0.024 |
| BTC | single | BOOKP:Imb1=high (rising in) | 15/30/60 | up | yes | 11.38 | +0.8 | +2.8 | 52.7 | +2.8 | 8.2 | -8.6 | +3.7 | 31.8 | +1.0 | +0.0 |  |  | 0.009 |
| XRP | single | WHALEP:Sweep=buy sweep | 15 | down | yes | 18.14 | +0.5 | +1.7 | 51.3 | +2.1 | 8.3 | -19.7 | +3.0 | 31.3 | +0.6 | -0.4 |  |  | 0.054 |
| SOL | single | WHALE:Net15=high (rising in) | 30 | down | yes | 15.26 | +0.8 | +2.0 | 50.7 | +2.0 | 7.1 | -17.0 | +3.2 | 30.6 | +0.8 | +0.1 |  |  | 0.031 |
| BTC | single | WHALE:Net15=very high | 15 | down | yes | 12.18 | +0.3 | +2.1 | 52.1 | +2.1 | 7.9 | -4.5 | +2.8 | 25.9 | +0.2 | +0.3 |  |  | 0.073 |
| XRP | single | BOOKP:Imb1=high (rising in) | 30/60 | up | yes | 9.87 | +2.7 | +2.6 | 52.1 | +2.7 | 7.8 | -24.1 | +3.3 | 25.7 | +2.4 | +0.4 |  |  | 0.030 |
| ETH | single | BOOKP:Imb1=very low | 15/30/60 | down | yes | 5.37 | +1.7 | +4.6 | 54.0 | +4.6 | 8.6 | -10.3 | +4.9 | 24.7 | +1.2 | +0.6 |  |  | 0.001 |
| ETH | single | LIQMAP:Skew=very low | 1/5 | up | yes | 4.89 | +1.1 | +4.7 | 54.9 | +5.6 | 10.3 | -13.2 | +4.1 | 23.0 | +0.0 | +0.1 |  |  | 0.005 |
| SOL | single | WHALE:Sweep=sell sweep | 1/15 | up | yes | 8.30 | +0.6 | +2.7 | 50.3 | +5.2 | 8.6 | -13.4 | +2.9 | 22.8 | +0.0 | -0.3 |  |  | 0.065 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.14 | +0.7 | +4.1 | 53.9 | +4.1 | 8.5 | -11.5 | +3.2 | 20.8 | +0.9 | +0.4 |  |  | 0.031 |
| SOL | single | BOOKP:Imb1=very high | 5/15/30 | up | yes | 5.79 | +2.0 | +3.5 | 52.2 | +4.3 | 8.1 | -13.3 | +3.6 | 20.5 | +1.8 | +0.1 |  |  | 0.016 |
| ETH | single | BOOKP:Imb1=high (cooling) | 5/15/30/60 | up | yes | 6.23 | +0.4 | +3.3 | 53.3 | +3.4 | 8.9 | -8.2 | +2.9 | 20.4 | +0.5 | -0.1 |  |  | 0.082 |
| BTC | single | BOOKP:Imb1=very low | 15 | down | yes | 6.33 | +0.4 | +2.8 | 52.8 | +2.8 | 8.5 | -6.5 | +2.9 | 17.6 | +0.4 | +0.4 |  |  | 0.079 |
| ETH | single | BOOKP:Imb1=low (recovering) | 15/30 | down | yes | 3.48 | +1.5 | +4.9 | 54.0 | +4.9 | 8.4 | -13.1 | +3.6 | 16.9 | +1.5 | -0.2 |  |  | 0.020 |
| XRP | single | LIQMAP:Skew=very low | 15/30/60 | up | yes | 3.09 | +2.8 | +4.9 | 54.6 | +5.2 | 9.3 | -29.0 | +2.9 | 15.1 | +3.1 | -0.6 |  |  | 0.095 |
| SOL | single | LS:Global z=low (falling in) | 1 | up | yes | 1.55 | +2.0 | +6.1 | 51.9 | +6.8 | 7.9 | -8.1 | +2.9 | 9.5 | +0.0 | -0.9 |  |  | 0.070 |
| BTC | single | LS:Global z=very low | 1 | up | yes | 0.50 | +1.4 | +11.1 | 59.8 | +13.2 | 10.2 | -3.9 | +3.3 | 5.6 | +0.0 | +1.4 |  |  | 0.036 |
| BTC | single | LS:TopAcc z=very low | 1 | up | yes | 0.41 | +2.6 | +12.7 | 60.4 | +13.8 | 11.4 | -4.1 | +3.4 | 5.2 | +0.0 | +0.1 |  |  | 0.054 |
| ETH | pair | WHALEP:Sweep=sell sweep / CVDP:PxDiv60=high | 5/15/60 | up | no | 108.11 | +0.4 | +1.1 | 51.0 | +1.1 | 8.2 | -7.4 | +5.0 | 114.0 | +0.3 |  | +1.6 | +0.9 | 1.000 |
| XRP | pair | WHALEP:Sweep=sell sweep / CVDP:PxDiv60=high | 15/30/60 | up | no | 16.83 | +2.5 | +3.1 | 52.4 | +3.4 | 8.7 | -19.6 | +5.3 | 52.0 | +1.8 |  | +4.3 | +2.7 | 1.000 |
| ETH | triple | WHALEP:Sweep=sell sweep / CVDP:PxDiv60=high / BOOKP:Imb1=high | 5 | up | no | 10.70 | +0.7 | +4.5 | 54.6 | +4.6 | 8.3 | -7.2 | +5.9 | 48.5 | +0.4 |  | +3.9 | +1.9 | 1.000 |
| BTC | single | WHALE:Net15=low (falling in) | 15/30 | up | no | 28.66 | -0.0 | +1.2 | 51.0 | +1.2 | 8.0 | -5.6 | +2.5 | 33.8 | -0.1 | -0.3 |  |  | 0.134 |
| BTC | triple | WHALEP:Sweep=sell sweep / CVDP:PxDiv60=high / WHALEP:Net15=low | 15 | up | no | 12.08 | +0.8 | +2.8 | 52.6 | +2.8 | 7.8 | -5.7 | +4.0 | 33.5 | +0.9 |  | +2.8 | +1.6 | 1.000 |
| BTC | single | WHALEP:Net15=low (falling in) | 5/15 | up | no | 25.75 | -0.0 | +1.2 | 50.7 | +1.2 | 7.7 | -3.8 | +2.3 | 31.1 | -0.0 | -0.1 |  |  | 0.221 |
| BTC | pair | WHALE:Sweep=sell sweep / WHALE:Net15=low | 30 | up | no | 6.93 | +0.9 | +3.4 | 53.6 | +3.4 | 8.6 | -10.5 | +3.6 | 23.4 | +0.6 |  | +2.3 | +2.3 | 1.000 |
| BTC | pair | WHALE:Sweep=sell sweep / WHALEP:Net15=low | 15/30 | up | no | 4.40 | +0.5 | +5.1 | 54.9 | +5.1 | 9.1 | -8.9 | +4.1 | 22.3 | +0.3 |  | +4.5 | +3.9 | 1.000 |

## Tables

One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.

| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 9aec3253daadcbd56dc5ca5da9a91444428183f34189fccc61a6f59dcdd2cf5d |
| BTC~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | d23315c73c8c8d9a94df1f494fd2f99e13448dadf1b13e63016742c201dbe4b2 |
| BTC~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | d33176547f5f3618541d2d2ffc79263cf2de373aa4fbb2efb275a6c3f857f696 |
| BTC~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 4474ff028ab86c52375ed3f867dd886a1d98ca55e5840b2e8ba1994a93270c27 |
| ETH | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | acc19b560526a99bc6a73e56f657a7815f87b0112fe6a7139fecc398107d1322 |
| ETH~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | e3bb2fca28735b1e9519fa9eb8d87463bddd1dde6b6f33012a42c23548c1b54d |
| ETH~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 753ff56c3274c936a3b205bdbf8a112b0cac501eb7fe13f01353cba760f3030c |
| ETH~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 6f4907ece921f5e6d53a33f6a603c7d7d4902395a55a67a39b23b3cc30fb72ed |
| SOL | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 26c65086373f07f9e8749937e143818eddb8ded356fc892882f3445e59f3afac |
| SOL~twin1 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | a8033c8c1a383dc7b55f4919c23da67a7409decc684dd0f19e0dc3d9bde41982 |
| SOL~twin2 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | ee246039afe233f5acf2e1d03d5a8d202f0335765841eaa148463085004cbd26 |
| SOL~twin3 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 838ddb416d671dd426995c51f591d3828c7018331065619706938f29334a051b |
| XRP | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | b96a2cb18456d61d988246f52f7846bced15c8c39f3d2e4fbea4eed0fbb5e357 |
| XRP~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 76a0256035c4c7988c16bf9c41daa89f38823b6474e1c7545edee9cb88a8b106 |
| XRP~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | a39ff8cad49297882edc0943810af3b71f3089b0e3dd879e4264c2653bb89d66 |
| XRP~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 461403def646c555d580408445a2d3b9565438b13d26d610ed077a9e1d4e99f0 |
