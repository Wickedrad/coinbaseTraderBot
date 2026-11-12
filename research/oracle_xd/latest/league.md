# OR-HM1 heat map: league (coin price, discovery only)

Coins: BTC, ETH, SOL, XRP. No-signal twins: BTC~twin1, BTC~twin2, BTC~twin3, ETH~twin1, ETH~twin2, ETH~twin3, SOL~twin1, SOL~twin2, SOL~twin3, XRP~twin1, XRP~twin2, XRP~twin3.
Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute's open. A map, not a validated rule.

## Hot spots against chance

Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent's other events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest set, a higher replicate share and the BHY column are evidence.

| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |
|---|---|---|---|---|---|---|---|---|---|---|
| real | single | 360 | 7 | 1 | 0.1429 | 1 | 87 | 22 | 0.2529 | 12 |
| real | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| real | pair | 2,045 | 8 | 0 | 0.0 | 0 | 31 | 1 | 0.0323 | 0 |
| real | triple | 205 | 0 | 0 |  | 0 | 5 | 0 | 0.0 | 0 |
| twin (median of 3) | single | 360 | 1 (0 to 2) | 0 |  | 0 | 0 | 0 |  | 0 |
| twin (median of 3) | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| twin (median of 3) | pair | 1,995 | 3 (1 to 4) | 0 | 0.0 | 0 | 3 (1 to 10) | 0 | 0.0 | 0 |
| twin (median of 3) | triple | 20 | 0 | 0 |  | 0 | 0 | 0 |  | 0 |

Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): move_heat None, move_edge None, odds_edge None, odds_heat None.

## Direction: every event level, nothing cut (Amendment 3)

The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods (30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.

| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |
|---|---|---|---|---|---|---|---|---|
| 1 | real | 72 | 0.6944 | 0.1111 | 0.427 | 39.079 | 45.055 | 0.159 |
| 1 | twin | 216 | 0.4537 | 0.0185 | -0.078 | 24.083 | 27.729 | 0.061 |
| 5 | real | 72 | 0.7639 | 0.2222 | 1.009 | 44.868 | 47.805 | 0.284 |
| 5 | twin | 216 | 0.4907 | 0.037 | -0.018 | 28.494 | 41.584 | 0.071 |
| 15 | real | 72 | 0.7639 | 0.2639 | 1.22 | 41.609 | 46.384 | 0.263 |
| 15 | twin | 216 | 0.5093 | 0.0139 | 0.03 | 22.606 | 27.883 | 0.092 |
| 30 | real | 72 | 0.7361 | 0.2222 | 1.36 | 40.861 | 43.499 | 0.284 |
| 30 | twin | 216 | 0.4722 | 0.0231 | -0.032 | 21.669 | 24.348 | 0.042 |
| 60 | real | 72 | 0.7639 | 0.2778 | 1.3 | 33.695 | 40.731 | 0.306 |
| 60 | twin | 216 | 0.5093 | 0.0093 | 0.028 | 12.536 | 17.097 | 0.051 |

Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.

Top 12 at 1 minute by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=high (rising in) | down | 14.23 | 36.3 | 50.1 | +4.1 | +3.2 | +4.7 | 45.1 | 8.2 | +1.1 | +9.2 | -8.8 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 12.86 | 50.8 | 52.7 | +3.4 | +2.8 | +3.8 | 36.6 | 9.3 | +1.6 | +8.1 | -8.8 | hot, replicates, BHY |
| XRP | CVDP:PxDiv60=high (rising in) | up | 40.30 | 37.5 | 47.1 | +0.9 | +0.9 | +2.2 | 35.3 | 7.1 | +0.1 | +6.4 | -6.3 | none |
| BTC | CVDP:Div15=very low | up | 22.82 | 48.3 | 46.7 | +0.1 | +1.2 | +2.1 | 26.6 | 7.4 | -0.1 | +2.4 | -2.2 | hot, replicates |
| BTC | CVDP:Div15=very high | down | 24.89 | 46.7 | 45.1 | -1.4 | +0.9 | +1.7 | 21.8 | 7.3 | -0.2 | +2.0 | -2.0 | hot |
| ETH | LIQMAP:Skew=high (rising in) | down | 11.95 | 52.2 | 51.2 | +2.4 | +1.8 | +2.6 | 21.4 | 9.1 | +1.6 | +7.2 | -7.7 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 14.57 | 40.2 | 48.7 | +2.5 | +1.5 | +2.3 | 21.4 | 8.5 | +1.5 | +9.1 | -9.4 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 14.02 | 39.1 | 47.8 | +2.7 | +1.3 | +1.9 | 17.7 | 7.9 | +1.1 | +9.3 | -10.0 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 13.85 | 40.7 | 46.6 | +1.9 | +1.0 | +1.6 | 14.5 | 7.7 | +0.9 | +8.4 | -8.8 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 8.86 | 52.3 | 50.4 | +4.0 | +1.5 | +1.6 | 13.7 | 8.6 | +1.1 | +4.3 | -4.6 | hot |
| BTC | CVDP:PxDiv60=high (rising in) | down | 36.17 | 48.5 | 46.9 | +0.4 | +0.4 | +0.8 | 13.0 | 7.8 | +0.3 | +2.9 | -2.8 | none |
| SOL | LIQMAP:Skew=very high | down | 4.43 | 43.4 | 49.8 | +5.1 | +2.9 | +2.6 | 12.8 | 8.5 | +1.7 | +10.3 | -10.7 | none |

Top 8 at 1 minute by share right over base on B (at least 0.2 windows per day; the best twin level reaches 6.08 points, the 99th percentile 4.69):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | LIQMAP:Skew=very high | down | 4.43 | 1,617 | 49.8 | +5.1 | +2.6 | 8.5 | +1.7 | -10.7 | none |
| XRP | LIQMAP:Skew=very high | down | 4.73 | 1,727 | 50.3 | +4.3 | +2.1 | 8.9 | +1.9 | -11.6 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 14.23 | 5,192 | 50.1 | +4.1 | +4.7 | 8.2 | +1.1 | -8.8 | none |
| BTC | LIQMAP:Skew=very low | up | 4.15 | 1,516 | 50.7 | +4.1 | +0.6 | 9.2 | +1.7 | -7.6 | hot |
| BTC | LIQMAP:Skew=very high | down | 2.63 | 960 | 50.5 | +4.1 | +0.7 | 8.7 | +1.2 | -6.1 | hot |
| BTC | LIQMAP:Skew=high (rising in) | down | 8.86 | 3,233 | 50.4 | +4.0 | +1.6 | 8.6 | +1.1 | -4.6 | hot |
| SOL | CVDP:PxDiv60=low (recovering) | up | 1.39 | 507 | 48.9 | +3.9 | +1.3 | 8.0 | +1.1 | -8.3 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 4.11 | 1,500 | 50.4 | +3.8 | +0.6 | 9.1 | +1.6 | -6.6 | none |

Top 12 at 5 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=high (rising in) | down | 12.92 | 45.2 | 52.6 | +4.0 | +3.7 | +5.3 | 47.8 | 8.2 | +1.1 | +21.6 | -10.7 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 11.79 | 52.6 | 53.7 | +3.7 | +3.7 | +4.8 | 43.7 | 9.3 | +1.6 | +19.2 | -10.5 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=high (rising in) | down | 10.87 | 53.6 | 53.5 | +3.9 | +3.8 | +4.4 | 41.7 | 9.1 | +1.6 | +16.9 | -9.4 | none |
| ETH | CVDP:Div15=low (falling in) | down | 32.56 | 49.3 | 50.9 | +1.2 | +1.2 | +2.7 | 40.6 | 7.8 | +0.3 | +12.0 | -5.9 | none |
| SOL | CVDP:Div15=high (rising in) | up | 31.32 | 42.2 | 48.9 | +1.0 | +1.3 | +2.8 | 40.0 | 7.1 | +0.3 | +14.7 | -7.5 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 13.25 | 48.1 | 51.2 | +2.9 | +2.7 | +3.9 | 36.3 | 8.5 | +1.5 | +21.6 | -11.4 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 12.59 | 47.3 | 50.8 | +3.0 | +2.8 | +3.8 | 34.9 | 7.7 | +0.9 | +19.8 | -10.7 | none |
| XRP | CVDP:Div15=low (falling in) | down | 26.93 | 41.9 | 49.6 | +1.1 | +1.2 | +2.7 | 33.4 | 7.4 | +0.4 | +12.9 | -6.2 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 12.79 | 47.1 | 50.5 | +2.6 | +2.3 | +3.5 | 29.8 | 7.9 | +1.1 | +22.5 | -12.2 | none |
| ETH | CVDP:PxDiv60=high (rising in) | down | 36.30 | 49.7 | 50.4 | +0.8 | +0.8 | +1.8 | 27.4 | 7.8 | +0.3 | +13.1 | -6.6 | none |
| ETH | CVDP:PxDiv60=low (falling in) | down | 23.44 | 49.2 | 50.7 | +1.1 | +1.1 | +2.2 | 26.4 | 7.6 | +0.1 | +12.9 | -6.3 | none |
| SOL | LIQMAP:Skew=very high | down | 4.09 | 49.0 | 53.5 | +5.7 | +4.9 | +3.9 | 20.0 | 8.5 | +1.7 | +23.8 | -12.7 | none |

Top 8 at 5 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 3.39 points, the 99th percentile 2.85):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | LIQMAP:Skew=very high | down | 4.09 | 1,617 | 53.5 | +5.7 | +3.9 | 8.5 | +1.7 | -12.7 | none |
| XRP | LIQMAP:Skew=very high | down | 4.36 | 1,727 | 53.2 | +4.6 | +3.1 | 8.9 | +1.9 | -14.0 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=very low | up | 4.41 | 1,775 | 54.0 | +4.1 | +3.3 | 9.1 | +1.3 | -15.4 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=high (rising in) | down | 12.92 | 5,192 | 52.6 | +4.0 | +5.3 | 8.2 | +1.1 | -10.7 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 10.87 | 4,361 | 53.5 | +3.9 | +4.4 | 9.1 | +1.6 | -9.4 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 11.79 | 4,695 | 53.7 | +3.7 | +4.8 | 9.3 | +1.6 | -10.5 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=low (recovering) | up | 4.87 | 1,957 | 51.6 | +3.3 | +2.4 | 8.8 | +1.8 | -13.2 | none |
| XRP | LIQMAP:Skew=very low | up | 4.99 | 1,990 | 51.3 | +3.0 | +2.0 | 8.7 | +1.6 | -14.2 | none |

Top 12 at 15 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=high (rising in) | down | 10.00 | 49.5 | 54.0 | +4.8 | +4.6 | +5.7 | 46.4 | 8.2 | +1.1 | +37.7 | -15.4 | none |
| SOL | CVDP:Div15=high (rising in) | up | 24.19 | 46.0 | 50.4 | +1.5 | +1.6 | +3.3 | 39.7 | 7.1 | +0.3 | +26.5 | -11.3 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 9.16 | 55.3 | 54.3 | +3.9 | +3.9 | +4.6 | 35.9 | 9.3 | +1.6 | +33.2 | -15.3 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=high (rising in) | down | 8.46 | 54.9 | 53.6 | +4.2 | +4.2 | +4.4 | 35.3 | 9.1 | +1.6 | +29.6 | -13.4 | hot |
| SOL | LIQMAP:Skew=high (rising in) | down | 9.69 | 51.3 | 51.9 | +3.3 | +3.2 | +4.1 | 31.1 | 7.7 | +0.9 | +34.3 | -15.4 | none |
| ETH | CVDP:PxDiv60=high (rising in) | down | 27.12 | 49.9 | 50.5 | +1.0 | +1.0 | +2.4 | 28.4 | 7.8 | +0.3 | +24.2 | -9.7 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 9.82 | 50.9 | 52.0 | +3.0 | +2.8 | +3.5 | 27.5 | 7.9 | +1.1 | +38.9 | -17.8 | none |
| BTC | CVDP:Div15=high (cooling) | up | 14.88 | 50.4 | 51.5 | +1.6 | +1.6 | +2.4 | 24.3 | 7.7 | +0.2 | +11.2 | -4.2 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 10.20 | 51.5 | 51.4 | +2.4 | +2.3 | +2.6 | 23.2 | 8.5 | +1.5 | +36.9 | -16.7 | none |
| SOL | CVDP:Div15=low (falling in) | down | 23.54 | 46.4 | 49.3 | +0.7 | +0.8 | +1.5 | 18.0 | 6.8 | +0.0 | +26.1 | -10.6 | none |
| ETH | CVDP:PxDiv60=very high | up | 5.34 | 50.7 | 53.5 | +3.1 | +3.0 | +2.7 | 16.2 | 8.5 | +0.8 | +25.4 | -10.5 | none |
| XRP | LIQMAP:Skew=very high | down | 3.35 | 52.5 | 54.4 | +5.2 | +4.8 | +3.3 | 16.1 | 8.9 | +1.9 | +41.3 | -20.1 | hot, replicates, BHY |

Top 8 at 15 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.39 points, the 99th percentile 3.28):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=very high | down | 3.35 | 1,727 | 54.4 | +5.2 | +3.3 | 8.9 | +1.9 | -20.1 | hot, replicates, BHY |
| BTC | LIQMAP:Skew=very high | down | 1.86 | 960 | 54.9 | +4.8 | +2.5 | 8.7 | +1.2 | -10.9 | hot, replicates |
| XRP | LIQMAP:Skew=high (rising in) | down | 10.00 | 5,192 | 54.0 | +4.8 | +5.7 | 8.2 | +1.1 | -15.4 | none |
| XRP | LIQMAP:Skew=high (cooling) | down | 3.23 | 1,681 | 53.5 | +4.2 | +2.5 | 8.8 | +1.8 | -17.9 | none |
| ETH | LIQMAP:Skew=very low | up | 3.32 | 1,775 | 54.5 | +4.2 | +2.6 | 9.1 | +1.3 | -22.0 | hot, replicates |
| ETH | LIQMAP:Skew=high (rising in) | down | 8.46 | 4,361 | 53.6 | +4.2 | +4.4 | 9.1 | +1.6 | -13.4 | hot |
| XRP | LIQMAP:Skew=very low | up | 3.88 | 1,990 | 53.0 | +4.0 | +3.1 | 8.7 | +1.6 | -21.0 | hot |
| ETH | LIQMAP:Skew=low (falling in) | up | 9.16 | 4,695 | 54.3 | +3.9 | +4.6 | 9.3 | +1.6 | -15.3 | hot, replicates, BHY |

Top 12 at 30 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | CVDP:Div15=low (recovering) | down | 11.34 | 49.9 | 53.6 | +3.8 | +3.8 | +5.3 | 43.5 | 7.7 | +0.2 | +18.4 | -6.7 | none |
| BTC | CVDP:Div15=very low | down | 13.77 | 49.5 | 52.7 | +2.9 | +2.9 | +4.5 | 39.8 | 7.5 | +0.0 | +17.6 | -6.5 | none |
| SOL | CVDP:Div15=high (rising in) | up | 19.58 | 47.6 | 51.2 | +1.7 | +1.7 | +3.3 | 34.1 | 7.1 | +0.3 | +38.4 | -15.6 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 7.73 | 51.3 | 53.2 | +3.9 | +3.8 | +4.2 | 29.1 | 8.2 | +1.1 | +52.3 | -20.7 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 6.66 | 56.8 | 53.3 | +4.2 | +4.1 | +3.9 | 27.6 | 9.1 | +1.6 | +41.2 | -17.8 | hot, replicates, BHY |
| ETH | CVDP:Div15=low (falling in) | down | 20.07 | 49.3 | 50.5 | +1.3 | +1.3 | +2.3 | 26.4 | 7.8 | +0.3 | +32.0 | -11.9 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 7.16 | 56.4 | 54.2 | +3.5 | +3.5 | +3.6 | 25.2 | 9.3 | +1.6 | +45.9 | -20.2 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=low (falling in) | up | 8.00 | 53.5 | 52.5 | +3.2 | +3.1 | +3.2 | 24.7 | 8.5 | +1.5 | +51.5 | -22.6 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 7.59 | 51.8 | 52.6 | +3.0 | +2.9 | +3.2 | 22.1 | 7.9 | +1.1 | +54.5 | -24.1 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 5.04 | 54.8 | 54.1 | +4.4 | +4.3 | +3.3 | 21.8 | 8.6 | +1.1 | +27.0 | -11.5 | hot, replicates, BHY |
| BTC | CVDP:Div15=low (falling in) | down | 25.19 | 49.5 | 50.5 | +0.7 | +0.8 | +1.7 | 19.0 | 7.6 | +0.2 | +19.7 | -7.3 | none |
| XRP | LIQMAP:Skew=low (recovering) | up | 3.04 | 54.8 | 55.3 | +5.9 | +5.6 | +3.3 | 17.2 | 8.8 | +1.8 | +57.2 | -26.6 | hot, replicates, BHY |

Top 8 at 30 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 5.51 points, the 99th percentile 2.98):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=low (recovering) | up | 3.04 | 1,957 | 55.3 | +5.9 | +3.3 | 8.8 | +1.8 | -26.6 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=very low | up | 3.04 | 1,990 | 54.6 | +5.2 | +3.0 | 8.7 | +1.6 | -27.7 | hot, replicates, BHY |
| BTC | LIQMAP:Skew=very low | up | 2.22 | 1,516 | 55.0 | +4.8 | +2.7 | 9.2 | +1.7 | -18.0 | hot, replicates |
| BTC | LIQMAP:Skew=high (rising in) | down | 5.04 | 3,233 | 54.1 | +4.4 | +3.3 | 8.6 | +1.1 | -11.5 | hot, replicates, BHY |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.40 | 942 | 54.0 | +4.3 | +1.5 | 8.7 | +1.3 | -13.6 | hot |
| BTC | LIQMAP:Skew=low (recovering) | up | 2.21 | 1,500 | 54.4 | +4.2 | +2.3 | 9.1 | +1.6 | -16.1 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.49 | 960 | 54.0 | +4.2 | +1.5 | 8.7 | +1.2 | -14.4 | hot |
| ETH | LIQMAP:Skew=high (rising in) | down | 6.66 | 4,361 | 53.3 | +4.2 | +3.9 | 9.1 | +1.6 | -17.8 | hot, replicates, BHY |

Top 12 at 60 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | CVDP:Div15=high (rising in) | up | 16.03 | 50.8 | 53.8 | +2.5 | +2.5 | +5.1 | 40.7 | 8.2 | +0.4 | +45.9 | -17.8 | none |
| BTC | CVDP:Div15=very low | down | 10.80 | 50.0 | 52.3 | +2.8 | +2.9 | +4.0 | 30.8 | 7.5 | +0.0 | +26.4 | -9.3 | none |
| BTC | CVDP:Div15=low (falling in) | down | 17.76 | 49.3 | 51.1 | +1.7 | +1.6 | +3.5 | 29.3 | 7.6 | +0.2 | +28.8 | -10.4 | none |
| BTC | CVDP:Div15=low (recovering) | down | 9.24 | 50.3 | 52.4 | +3.0 | +3.0 | +3.7 | 27.5 | 7.7 | +0.2 | +27.7 | -9.5 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 5.73 | 52.4 | 53.3 | +3.7 | +3.6 | +3.5 | 20.5 | 8.2 | +1.1 | +73.1 | -28.7 | none |
| SOL | CVDP:Div15=high (rising in) | up | 14.45 | 48.4 | 51.3 | +1.3 | +1.3 | +2.3 | 19.2 | 7.1 | +0.3 | +55.4 | -21.7 | none |
| ETH | CVDP:PxDiv60=low (falling in) | down | 11.06 | 49.6 | 50.4 | +1.7 | +1.7 | +2.4 | 18.6 | 7.6 | +0.1 | +53.5 | -18.7 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 5.98 | 54.5 | 52.5 | +3.0 | +2.9 | +2.6 | 17.3 | 8.5 | +1.5 | +72.6 | -30.4 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 5.66 | 53.3 | 51.8 | +3.1 | +3.0 | +2.7 | 16.7 | 7.7 | +0.9 | +68.8 | -29.3 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 5.07 | 56.8 | 52.0 | +3.3 | +3.3 | +2.7 | 16.7 | 9.1 | +1.6 | +57.1 | -23.9 | hot, replicates |
| BTC | CVDP:Div15=high (cooling) | up | 9.91 | 51.6 | 52.0 | +1.4 | +1.4 | +1.8 | 14.3 | 7.7 | +0.2 | +23.8 | -8.9 | none |
| BTC | CVDP:Div15=very high | up | 11.20 | 51.3 | 51.7 | +1.2 | +1.2 | +1.7 | 13.9 | 7.4 | -0.1 | +23.2 | -8.8 | none |

Top 8 at 60 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.25 points, the 99th percentile 3.81):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=very low | up | 1.72 | 1,516 | 57.0 | +6.5 | +3.0 | 9.2 | +1.7 | -24.1 | hot, replicates |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.10 | 942 | 55.7 | +6.3 | +2.1 | 8.7 | +1.3 | -17.9 | hot |
| BTC | LIQMAP:Skew=very high | down | 1.15 | 960 | 55.6 | +6.2 | +2.1 | 8.7 | +1.2 | -17.9 | hot |
| SOL | CVDP:Div15=very high | up | 2.61 | 1,629 | 54.9 | +4.8 | +3.3 | 7.1 | +0.3 | -17.7 | none |
| SOL | CVDP:Div15=high (cooling) | up | 2.45 | 1,526 | 54.8 | +4.7 | +3.0 | 7.0 | +0.1 | -18.0 | none |
| SOL | LIQMAP:Skew=very high | down | 1.94 | 1,617 | 53.2 | +4.5 | +1.9 | 8.5 | +1.7 | -31.1 | hot |
| BTC | LIQMAP:Skew=low (recovering) | up | 1.72 | 1,500 | 55.0 | +4.5 | +2.0 | 9.1 | +1.6 | -22.8 | hot |
| XRP | LIQMAP:Skew=very low | up | 2.34 | 1,990 | 53.7 | +4.2 | +2.1 | 8.7 | +1.6 | -37.2 | hot, replicates |

## Every TA by heat

Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the direction the reading's current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). The horizon is the one with the most heat on A; the B columns score A's directions on B, so a reading with no information scores about zero.

| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |
|---|---|---|---|---|---|---|---|---|
| real | events | 12 | 0.6667 | 0.25 | 0.0833 | 12.223 | 64.391 | 74.535 |
| twin | events | 35 | 0.4571 | 0.0571 | 0.0 | -4.073 | 30.444 | 54.246 |

Top 12 readings by events heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| BTC | CVDP:Div15 | 60 | 20.4 | +74.5 | +4.4 |
| ETH | LIQMAP:Skew | 30 | 19.7 | +56.1 | +2.6 |
| SOL | CVDP:PxDiv60 | 60 | 74.7 | +37.0 | +1.3 |
| ETH | CVDP:PxDiv60 | 60 | 24.3 | +23.8 | +1.0 |
| XRP | CVDP:Div15 | 60 | 6.7 | +21.3 | +2.5 |
| XRP | LIQMAP:Skew | 60 | 16.3 | +14.8 | +0.8 |
| XRP | CVDP:PxDiv60 | 60 | 27.0 | +9.7 | +0.5 |
| SOL | CVDP:Div15 | 30 | 44.6 | +2.3 | +0.2 |
| BTC | LIQMAP:Skew | 60 | 27.9 | -7.4 | -0.5 |
| BTC | CVDP:PxDiv60 | 60 | 22.0 | -9.4 | -0.6 |
| SOL | LIQMAP:Skew | 60 | 12.4 | -18.6 | -1.1 |
| ETH | CVDP:Div15 | 30 | 23.9 | -30.2 | -1.5 |

## Top 1 replicating by heat on B (windows per day x move, bps per day)

1 of 1 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | single | CVDP:Div15=very low | 1 | up | yes | 22.82 | +0.2 | +1.2 | 46.7 | +0.1 | 7.4 | -2.2 | +3.0 | 3.7 | +0.0 | +0.0 |  |  | 0.033 |

## Top 1 replicating by move per event on B (bps; at least 0.2 windows per day)

1 of 1 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | single | CVDP:Div15=very low | 1 | up | yes | 22.82 | +0.2 | +1.2 | 46.7 | +0.1 | 7.4 | -2.2 | +3.0 | 3.7 | +0.0 | +0.0 |  |  | 0.033 |

## Top 13 replicating by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)

8 of 13 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | single | LIQMAP:Skew=low (recovering) | 30 | up | yes | 3.04 | +2.9 | +5.6 | 55.3 | +5.9 | 8.8 | -26.6 | +3.3 | 17.2 | +2.6 | +0.1 |  |  | 0.057 |
| XRP | single | LIQMAP:Skew=very low | 30/60 | up | yes | 3.04 | -0.5 | +4.9 | 54.6 | +5.2 | 8.7 | -27.7 | +3.0 | 14.8 | -0.3 | -0.5 |  |  | 0.089 |
| XRP | single | LIQMAP:Skew=very high | 5/15 | down | yes | 3.35 | -0.4 | +4.8 | 54.4 | +5.2 | 8.9 | -20.1 | +3.3 | 16.1 | +0.2 | -0.1 |  |  | 0.044 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.04 | +0.9 | +4.3 | 54.1 | +4.4 | 8.6 | -11.5 | +3.3 | 21.8 | +1.0 | +0.5 |  |  | 0.044 |
| ETH | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 6.66 | -1.4 | +4.1 | 53.3 | +4.2 | 9.1 | -17.8 | +3.9 | 27.6 | -1.3 | -0.4 |  |  | 0.012 |
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 9.16 | +0.5 | +3.9 | 54.3 | +3.9 | 9.3 | -15.3 | +4.6 | 35.9 | +0.4 | +0.0 |  |  | 0.002 |
| ETH | single | LIQMAP:Skew=very low | 5/15 | up | yes | 4.41 | -1.1 | +3.9 | 54.0 | +4.1 | 9.1 | -15.4 | +3.3 | 17.2 | -0.9 | -0.2 |  |  | 0.044 |
| BTC | single | CVDP:PxDiv60=low (recovering) | 15 | down | yes | 3.47 | +1.2 | +3.9 | 53.9 | +3.9 | 7.8 | -6.7 | +2.9 | 13.4 | +1.3 | +0.4 |  |  | 0.081 |
| BTC | pair | CVDP:PxDiv60=low (recovering) / LIQMAP:Skew=low | 5 | down | no | 0.28 | +2.7 | +14.0 | 64.2 | +14.3 | 6.8 | -4.6 | +3.2 | 3.9 | +3.6 |  | +13.9 | +14.8 | 0.312 |
| BTC | single | LIQMAP:Skew=very low | 30/60 | up | no | 1.72 | +2.0 | +6.5 | 57.0 | +6.5 | 9.2 | -24.1 | +3.0 | 11.1 | +2.2 | -0.5 |  |  | 0.102 |
| BTC | single | LIQMAP:Skew=very high | 15 | down | no | 1.86 | +1.0 | +4.8 | 54.9 | +4.8 | 8.7 | -10.9 | +2.5 | 8.9 | +0.8 | -0.8 |  |  | 0.206 |
| BTC | single | LIQMAP:Skew=low (recovering) | 30 | up | no | 2.21 | +0.4 | +4.2 | 54.4 | +4.2 | 9.1 | -16.1 | +2.3 | 9.4 | +0.2 | +0.6 |  |  | 0.259 |
| BTC | single | CVDP:Div15=very low | 1 | up | no | 22.82 | +0.2 | +1.2 | 46.7 | +0.1 | 7.4 | -2.2 | +2.1 | 26.6 | +0.0 | -0.1 |  |  | 0.328 |

## Top 13 replicating by odds heat on B (windows per day x odds points)

8 of 13 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 11.79 | +0.7 | +3.7 | 53.7 | +3.7 | 9.3 | -10.5 | +4.8 | 43.7 | +0.6 | -0.0 |  |  | 0.002 |
| ETH | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 6.66 | -1.4 | +4.1 | 53.3 | +4.2 | 9.1 | -17.8 | +3.9 | 27.6 | -1.3 | -0.4 |  |  | 0.012 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.04 | +0.9 | +4.3 | 54.1 | +4.4 | 8.6 | -11.5 | +3.3 | 21.8 | +1.0 | +0.5 |  |  | 0.044 |
| XRP | single | LIQMAP:Skew=very high | 5/15 | down | yes | 4.36 | -1.0 | +4.3 | 53.2 | +4.6 | 8.9 | -14.0 | +3.1 | 18.8 | -0.4 | -0.3 |  |  | 0.057 |
| ETH | single | LIQMAP:Skew=very low | 5/15 | up | yes | 4.41 | -1.1 | +3.9 | 54.0 | +4.1 | 9.1 | -15.4 | +3.3 | 17.2 | -0.9 | -0.2 |  |  | 0.044 |
| XRP | single | LIQMAP:Skew=low (recovering) | 30 | up | yes | 3.04 | +2.9 | +5.6 | 55.3 | +5.9 | 8.8 | -26.6 | +3.3 | 17.2 | +2.6 | +0.1 |  |  | 0.057 |
| XRP | single | LIQMAP:Skew=very low | 30/60 | up | yes | 3.04 | -0.5 | +4.9 | 54.6 | +5.2 | 8.7 | -27.7 | +3.0 | 14.8 | -0.3 | -0.5 |  |  | 0.089 |
| BTC | single | CVDP:PxDiv60=low (recovering) | 15 | down | yes | 3.47 | +1.2 | +3.9 | 53.9 | +3.9 | 7.8 | -6.7 | +2.9 | 13.4 | +1.3 | +0.4 |  |  | 0.081 |
| BTC | single | CVDP:Div15=very low | 1 | up | no | 22.82 | +0.2 | +1.2 | 46.7 | +0.1 | 7.4 | -2.2 | +2.1 | 26.6 | +0.0 | -0.1 |  |  | 0.328 |
| BTC | single | LIQMAP:Skew=very low | 30/60 | up | no | 1.72 | +2.0 | +6.5 | 57.0 | +6.5 | 9.2 | -24.1 | +3.0 | 11.1 | +2.2 | -0.5 |  |  | 0.102 |
| BTC | single | LIQMAP:Skew=low (recovering) | 30 | up | no | 2.21 | +0.4 | +4.2 | 54.4 | +4.2 | 9.1 | -16.1 | +2.3 | 9.4 | +0.2 | +0.6 |  |  | 0.259 |
| BTC | single | LIQMAP:Skew=very high | 15 | down | no | 1.86 | +1.0 | +4.8 | 54.9 | +4.8 | 8.7 | -10.9 | +2.5 | 8.9 | +0.8 | -0.8 |  |  | 0.206 |
| BTC | pair | CVDP:PxDiv60=low (recovering) / LIQMAP:Skew=low | 5 | down | no | 0.28 | +2.7 | +14.0 | 64.2 | +14.3 | 6.8 | -4.6 | +3.2 | 3.9 | +3.6 |  | +13.9 | +14.8 | 0.312 |

## Tables

One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.

| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 26d58d7304e4d122faf6c6ab90675bab933c931524feef91c926b967f481a2ce |
| BTC~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 7c31ca88e4e96a21456a6e48ca72b729ad8b6e3c0771586233095fbe335baba1 |
| BTC~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 334c0ba52d05ebfd4cf0b20ed329b70a4c090f78d101ae689fbc9d26e5687f91 |
| BTC~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 77640a94e356c716ffdd8dbb01019e07584e37ec0270723a789482b5eb388c44 |
| ETH | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | b6ad3d167d883f4ae6a0b1d94c753273ea60a6f9de3d6c9607d3901d1cec79eb |
| ETH~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 2f19ac681cfbd41efce201ef03bcb9fd326c7d96939f319309f78fb7a195127e |
| ETH~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | e0d6bd09c6a0756cc3d791e06dcb1af9476ea99ca882b3d567bab3498ea8a4e3 |
| ETH~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 3a30a7db3104a154c6350c2948dd56761bd91e5d97b1cc81fe4049a7c29457ef |
| SOL | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | e71407ec340dc5b3147e1dbd332a8db3bc5395122fbbb19f10ca5b0089263b76 |
| SOL~twin1 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 9a329004866986e82177e5d4d276cd0ec23e47f33aecd87aa60bf3246e3482a5 |
| SOL~twin2 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 061c431173bcdf6e087aeb2a859258b3901d64d30ba6eaadc2c8a1139baf6d72 |
| SOL~twin3 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 262b33fde47056d49a94d81ce91371302fe9a2ee5a8ef1b9da847d89fa055b7f |
| XRP | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 1c086f357dc77c7e6510f0acf40f8c21d2b73400ad89fcf1692af30ff6484b6d |
| XRP~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | a4993aff60600b39dfe543757d07d7cf18286157b1ea2e655c85b198a8114028 |
| XRP~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 8d211b43c3828302422667e39dc3c6a5db68ee537ab8043cc0d09317b05d25dc |
| XRP~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | a9c0ba3edca9f515c1fb42f7695e1ff16f24e1422e1ac35c75595977c715c098 |
