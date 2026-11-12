# OR-HM1 heat map: league (coin price, discovery only)

Coins: BTC, ETH, SOL, XRP. No-signal twins: BTC~twin1, BTC~twin2, BTC~twin3, ETH~twin1, ETH~twin2, ETH~twin3, SOL~twin1, SOL~twin2, SOL~twin3, XRP~twin1, XRP~twin2, XRP~twin3.
Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute's open. A map, not a validated rule.

## Hot spots against chance

Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent's other events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest set, a higher replicate share and the BHY column are evidence.

| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |
|---|---|---|---|---|---|---|---|---|---|---|
| real | single | 495 | 4 | 0 | 0.0 | 0 | 84 | 28 | 0.3333 | 12 |
| real | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| real | pair | 2,400 | 4 | 0 | 0.0 | 0 | 31 | 3 | 0.0968 | 0 |
| real | triple | 145 | 0 | 0 |  | 0 | 2 | 1 | 0.5 | 1 |
| twin (median of 3) | single | 430 | 1 (0 to 3) | 0 |  | 0 | 0 (0 to 1) | 0 (0 to 1) |  | 0 (0 to 1) |
| twin (median of 3) | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| twin (median of 3) | pair | 2,140 | 1 | 0 | 0.0 | 0 | 9 (5 to 9) | 0 | 0.0 | 0 |
| twin (median of 3) | triple | 30 | 0 | 0 |  | 0 | 0 | 0 |  | 0 |

Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): move_heat None, move_edge None, odds_edge 4.816, odds_heat 9.66.

## Direction: every event level, nothing cut (Amendment 3)

The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods (30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.

| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |
|---|---|---|---|---|---|---|---|---|
| 1 | real | 72 | 0.6389 | 0.1528 | 0.427 | 53.296 | 55.593 | 0.273 |
| 1 | twin | 216 | 0.5556 | 0.0231 | 0.128 | 24.272 | 34.742 | 0.121 |
| 5 | real | 72 | 0.6389 | 0.1806 | 0.429 | 54.927 | 55.077 | 0.185 |
| 5 | twin | 216 | 0.4676 | 0.0139 | -0.066 | 21.301 | 27.508 | 0.115 |
| 15 | real | 72 | 0.6806 | 0.2639 | 1.159 | 38.458 | 38.811 | 0.263 |
| 15 | twin | 216 | 0.5185 | 0.0231 | 0.039 | 19.65 | 25.029 | 0.12 |
| 30 | real | 72 | 0.6667 | 0.1667 | 1.029 | 34.534 | 36.768 | 0.21 |
| 30 | twin | 216 | 0.5 | 0.0324 | 0.001 | 21.679 | 23.74 | 0.135 |
| 60 | real | 72 | 0.7639 | 0.2639 | 0.916 | 24.118 | 29.153 | 0.231 |
| 60 | twin | 216 | 0.5093 | 0.0185 | 0.059 | 13.89 | 24.085 | 0.103 |

Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.

Top 12 at 1 minute by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | CVDP:PxDiv60=high (rising in) | down | 39.71 | 48.1 | 50.1 | +1.3 | +1.4 | +3.4 | 55.6 | 7.8 | +0.3 | +5.3 | -5.3 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 12.10 | 51.1 | 53.6 | +4.8 | +4.3 | +5.6 | 52.4 | 9.6 | +2.1 | +7.6 | -7.9 | hot, replicates, BHY |
| ETH | CVDP:Div15=high (rising in) | up | 28.85 | 46.6 | 49.9 | +0.6 | +0.9 | +1.9 | 27.3 | 7.9 | +0.2 | +4.7 | -4.4 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 13.98 | 39.1 | 48.4 | +3.3 | +1.9 | +2.8 | 26.1 | 8.0 | +1.2 | +9.7 | -10.1 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 13.42 | 39.8 | 47.3 | +2.6 | +1.9 | +2.8 | 25.1 | 7.9 | +1.1 | +8.7 | -9.1 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 13.10 | 51.4 | 51.6 | +2.3 | +1.8 | +2.4 | 24.0 | 9.1 | +1.4 | +8.1 | -9.4 | hot, replicates |
| ETH | LIQMAP:Skew=very low | up | 4.89 | 53.6 | 54.9 | +5.6 | +4.7 | +4.1 | 23.0 | 10.3 | +2.6 | +12.6 | -13.2 | hot, replicates, BHY |
| XRP | CVDP:Div15=low (falling in) | up | 23.69 | 35.3 | 46.4 | +0.2 | +0.9 | +1.7 | 21.3 | 6.7 | -0.3 | +5.0 | -4.9 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 13.61 | 35.1 | 48.7 | +2.7 | +1.4 | +2.0 | 19.1 | 8.7 | +1.7 | +8.9 | -9.7 | none |
| ETH | CVDP:Div15=low (recovering) | down | 6.36 | 45.5 | 50.9 | +2.2 | +2.9 | +2.9 | 18.2 | 8.3 | +0.8 | +4.0 | -4.0 | none |
| BTC | CVDP:PxDiv60=very low | up | 9.70 | 48.9 | 49.3 | +2.7 | +1.6 | +2.0 | 15.3 | 8.1 | +0.6 | +3.6 | -3.3 | none |
| BTC | CVDP:Div15=low (falling in) | up | 33.97 | 48.3 | 46.5 | -0.1 | +0.4 | +1.0 | 14.1 | 7.6 | +0.1 | +2.7 | -2.6 | none |

Top 8 at 1 minute by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.73 points, the 99th percentile 4.36):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=very low | up | 4.08 | 1,488 | 52.4 | +5.8 | +2.1 | 8.8 | +1.3 | -7.7 | hot, replicates |
| ETH | LIQMAP:Skew=very low | up | 4.89 | 1,783 | 54.9 | +5.6 | +4.1 | 10.3 | +2.6 | -13.2 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=high (rising in) | down | 12.10 | 4,415 | 53.6 | +4.8 | +5.6 | 9.6 | +2.1 | -7.9 | hot, replicates, BHY |
| SOL | LIQMAP:Skew=very low | up | 5.06 | 1,846 | 49.2 | +4.2 | +1.8 | 7.7 | +0.9 | -12.9 | none |
| ETH | LIQMAP:Skew=very high | down | 3.95 | 1,443 | 52.9 | +4.1 | +2.5 | 9.3 | +1.8 | -11.8 | hot, replicates |
| BTC | LIQMAP:Skew=low (falling in) | up | 8.66 | 3,160 | 50.7 | +4.1 | +1.9 | 9.0 | +1.5 | -5.4 | none |
| XRP | LIQMAP:Skew=very high | down | 4.65 | 1,696 | 50.1 | +4.1 | +2.2 | 9.1 | +2.1 | -12.0 | none |
| BTC | LIQMAP:Skew=very high | down | 2.62 | 957 | 50.4 | +3.9 | +0.6 | 9.3 | +1.8 | -6.2 | hot |

Top 12 at 5 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | LIQMAP:Skew=high (rising in) | down | 11.05 | 53.1 | 54.7 | +5.1 | +5.0 | +6.7 | 55.1 | 9.6 | +2.1 | +17.5 | -9.7 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=low (falling in) | up | 13.55 | 48.3 | 52.6 | +4.4 | +4.0 | +6.1 | 54.9 | 8.1 | +1.1 | +21.5 | -11.9 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 12.38 | 45.4 | 51.8 | +3.2 | +2.9 | +3.9 | 35.5 | 8.7 | +1.7 | +21.4 | -11.7 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 11.92 | 52.7 | 52.7 | +2.8 | +2.7 | +3.5 | 32.4 | 9.1 | +1.4 | +18.9 | -11.3 | hot, replicates, BHY |
| SOL | CVDP:Div15=high (rising in) | up | 24.09 | 42.0 | 49.0 | +1.1 | +1.2 | +2.3 | 27.8 | 7.1 | +0.2 | +14.5 | -7.4 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 12.32 | 47.0 | 50.4 | +2.7 | +2.2 | +3.0 | 26.6 | 7.9 | +1.1 | +20.0 | -11.0 | none |
| BTC | CVDP:Div15=low (falling in) | up | 31.73 | 50.5 | 50.3 | +0.8 | +0.8 | +1.8 | 24.7 | 7.6 | +0.1 | +7.3 | -3.3 | none |
| SOL | CVDP:Div15=low (falling in) | down | 23.40 | 43.2 | 48.5 | +0.8 | +1.0 | +1.9 | 23.5 | 6.9 | +0.1 | +14.7 | -7.2 | none |
| ETH | CVDP:PxDiv60=high (rising in) | down | 36.14 | 49.9 | 50.3 | +0.6 | +0.6 | +1.5 | 22.7 | 7.8 | +0.3 | +13.2 | -6.6 | hot |
| ETH | CVDP:PxDiv60=low (falling in) | down | 23.53 | 49.2 | 50.5 | +0.9 | +0.9 | +1.7 | 21.0 | 7.5 | +0.0 | +12.8 | -6.3 | none |
| BTC | CVDP:PxDiv60=high (rising in) | down | 32.98 | 50.2 | 50.5 | +0.6 | +0.6 | +1.4 | 20.4 | 7.8 | +0.4 | +7.6 | -3.5 | none |
| SOL | LIQMAP:Skew=very low | up | 4.61 | 50.8 | 52.8 | +4.9 | +3.9 | +3.4 | 18.2 | 7.7 | +0.9 | +28.9 | -15.6 | none |

Top 8 at 5 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 3.17 points, the 99th percentile 2.85):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | LIQMAP:Skew=high (rising in) | down | 11.05 | 4,415 | 54.7 | +5.1 | +6.7 | 9.6 | +2.1 | -9.7 | hot, replicates, BHY |
| SOL | LIQMAP:Skew=very low | up | 4.61 | 1,846 | 52.8 | +4.9 | +3.4 | 7.7 | +0.9 | -15.6 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 13.55 | 5,430 | 52.6 | +4.4 | +6.1 | 8.1 | +1.1 | -11.9 | none |
| XRP | LIQMAP:Skew=very high | down | 4.28 | 1,696 | 52.8 | +4.3 | +2.6 | 9.1 | +2.1 | -14.5 | hot, replicates |
| ETH | LIQMAP:Skew=very low | up | 4.45 | 1,783 | 53.7 | +3.8 | +3.0 | 10.3 | +2.6 | -15.9 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=high (rising in) | down | 12.38 | 4,966 | 51.8 | +3.2 | +3.9 | 8.7 | +1.7 | -11.7 | none |
| XRP | LIQMAP:Skew=high (cooling) | down | 4.09 | 1,642 | 51.6 | +3.1 | +2.3 | 8.1 | +1.1 | -12.1 | none |
| ETH | LIQMAP:Skew=very high | down | 3.60 | 1,443 | 52.6 | +3.0 | +2.2 | 9.3 | +1.8 | -13.5 | hot, replicates |

Top 12 at 15 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | CVDP:PxDiv60=high (rising in) | down | 27.07 | 49.9 | 50.9 | +1.4 | +1.4 | +3.3 | 38.8 | 7.8 | +0.3 | +24.2 | -9.7 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=high (rising in) | down | 8.49 | 55.0 | 54.0 | +4.6 | +4.5 | +4.6 | 38.3 | 9.6 | +2.1 | +30.4 | -13.6 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=high (rising in) | down | 9.59 | 49.0 | 53.1 | +3.9 | +3.8 | +4.1 | 36.5 | 8.7 | +1.7 | +36.9 | -16.4 | none |
| XRP | CVDP:Div15=high (rising in) | up | 21.54 | 47.0 | 50.4 | +1.4 | +1.5 | +2.8 | 31.7 | 7.1 | +0.0 | +24.1 | -9.8 | none |
| SOL | CVDP:Div15=high (rising in) | up | 20.04 | 45.7 | 50.1 | +1.2 | +1.4 | +2.6 | 28.8 | 7.1 | +0.2 | +26.1 | -11.1 | none |
| SOL | CVDP:Div15=low (falling in) | down | 19.37 | 46.2 | 49.8 | +1.2 | +1.4 | +2.7 | 28.0 | 6.9 | +0.1 | +26.5 | -10.6 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 9.77 | 51.3 | 52.1 | +3.1 | +2.9 | +3.4 | 28.0 | 8.0 | +1.2 | +38.5 | -17.9 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 10.40 | 52.2 | 51.8 | +2.8 | +2.6 | +3.3 | 27.5 | 8.1 | +1.1 | +36.9 | -16.9 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 9.23 | 54.8 | 53.3 | +2.9 | +2.9 | +3.3 | 26.8 | 9.1 | +1.4 | +32.6 | -16.1 | hot, replicates, BHY |
| ETH | CVDP:Div15=low (falling in) | down | 19.89 | 49.5 | 50.7 | +1.3 | +1.3 | +2.3 | 24.9 | 7.6 | +0.0 | +22.0 | -8.5 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 9.49 | 50.6 | 51.2 | +2.6 | +2.3 | +2.6 | 21.6 | 7.9 | +1.1 | +34.5 | -15.7 | none |
| XRP | LIQMAP:Skew=very high | down | 3.29 | 52.6 | 55.5 | +6.2 | +5.8 | +3.6 | 19.2 | 9.1 | +2.1 | +41.7 | -20.8 | hot |

Top 8 at 15 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 5.41 points, the 99th percentile 3.38):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=very high | down | 3.29 | 1,696 | 55.5 | +6.2 | +3.6 | 9.1 | +2.1 | -20.8 | hot |
| ETH | LIQMAP:Skew=high (rising in) | down | 8.49 | 4,415 | 54.0 | +4.6 | +4.6 | 9.6 | +2.1 | -13.6 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=high (cooling) | down | 3.18 | 1,642 | 53.5 | +4.2 | +2.5 | 8.1 | +1.1 | -18.0 | none |
| ETH | LIQMAP:Skew=very high | down | 2.84 | 1,443 | 53.5 | +4.1 | +2.5 | 9.3 | +1.8 | -18.7 | hot, replicates |
| XRP | LIQMAP:Skew=high (rising in) | down | 9.59 | 4,966 | 53.1 | +3.9 | +4.1 | 8.7 | +1.7 | -16.4 | none |
| BTC | LIQMAP:Skew=very low | up | 2.82 | 1,488 | 53.6 | +3.7 | +2.3 | 8.8 | +1.3 | -13.8 | hot, replicates |
| XRP | LIQMAP:Skew=very low | up | 3.92 | 2,009 | 52.4 | +3.4 | +2.3 | 9.3 | +2.2 | -21.9 | hot, replicates |
| BTC | CVDP:PxDiv60=low (recovering) | down | 3.48 | 1,489 | 53.4 | +3.3 | +2.3 | 7.9 | +0.4 | -6.7 | hot, replicates |

Top 12 at 30 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | LIQMAP:Skew=high (rising in) | down | 6.66 | 55.9 | 54.7 | +5.6 | +5.5 | +5.0 | 36.8 | 9.6 | +2.1 | +42.1 | -18.0 | hot, replicates, BHY |
| ETH | CVDP:Div15=low (falling in) | down | 16.89 | 49.2 | 51.1 | +2.0 | +2.0 | +3.4 | 33.6 | 7.6 | +0.0 | +32.0 | -11.8 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 7.48 | 51.2 | 53.5 | +4.1 | +4.0 | +4.2 | 29.8 | 8.7 | +1.7 | +50.9 | -21.5 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 7.37 | 52.1 | 52.3 | +3.6 | +3.5 | +3.5 | 25.8 | 7.9 | +1.1 | +49.0 | -21.6 | none |
| SOL | CVDP:Div15=high (rising in) | up | 17.00 | 47.6 | 51.0 | +1.4 | +1.4 | +2.5 | 24.3 | 7.1 | +0.2 | +37.9 | -15.3 | hot |
| SOL | LIQMAP:Skew=low (falling in) | up | 7.57 | 52.2 | 52.8 | +3.2 | +3.0 | +3.2 | 22.5 | 8.0 | +1.2 | +54.2 | -24.3 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 8.14 | 53.5 | 52.0 | +2.7 | +2.6 | +2.7 | 21.3 | 8.1 | +1.1 | +51.5 | -22.5 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 5.14 | 54.3 | 53.9 | +4.1 | +4.1 | +3.2 | 20.8 | 8.5 | +1.0 | +26.8 | -11.5 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=low (falling in) | up | 7.23 | 55.7 | 53.5 | +2.8 | +2.8 | +2.9 | 20.0 | 9.1 | +1.4 | +45.3 | -21.4 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=low (recovering) | up | 3.04 | 54.5 | 55.6 | +6.2 | +6.0 | +3.7 | 18.3 | 8.5 | +1.4 | +59.1 | -26.8 | none |
| SOL | CVDP:Div15=low (falling in) | down | 16.28 | 48.1 | 49.7 | +1.0 | +1.1 | +1.9 | 18.3 | 6.9 | +0.1 | +38.4 | -14.6 | hot |
| ETH | CVDP:PxDiv60=low (falling in) | down | 14.22 | 49.7 | 50.3 | +1.1 | +1.1 | +1.6 | 15.5 | 7.5 | +0.0 | +35.7 | -13.1 | none |

Top 8 at 30 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.59 points, the 99th percentile 3.15):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=low (recovering) | up | 3.04 | 1,955 | 55.6 | +6.2 | +3.7 | 8.5 | +1.4 | -26.8 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 6.66 | 4,415 | 54.7 | +5.6 | +5.0 | 9.6 | +2.1 | -18.0 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=very low | up | 3.09 | 2,009 | 54.6 | +5.2 | +2.9 | 9.3 | +2.2 | -29.0 | hot, replicates |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.41 | 944 | 55.0 | +5.2 | +1.9 | 8.6 | +1.1 | -13.3 | hot |
| BTC | LIQMAP:Skew=very low | up | 2.21 | 1,488 | 55.2 | +5.1 | +2.8 | 8.8 | +1.3 | -18.3 | hot, replicates |
| XRP | LIQMAP:Skew=high (rising in) | down | 7.48 | 4,966 | 53.5 | +4.1 | +4.2 | 8.7 | +1.7 | -21.5 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 5.14 | 3,316 | 53.9 | +4.1 | +3.2 | 8.5 | +1.0 | -11.5 | hot, replicates, BHY |
| BTC | LIQMAP:Skew=very high | down | 1.47 | 957 | 53.8 | +4.0 | +1.5 | 9.3 | +1.8 | -13.9 | hot |

Top 12 at 60 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | CVDP:Div15=high (rising in) | up | 14.30 | 50.9 | 53.2 | +2.0 | +2.0 | +3.7 | 29.2 | 7.9 | +0.2 | +46.1 | -17.6 | none |
| BTC | CVDP:Div15=very low | down | 9.32 | 49.6 | 51.8 | +2.4 | +2.4 | +2.9 | 22.1 | 7.4 | -0.0 | +26.5 | -9.2 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 5.04 | 56.1 | 52.9 | +4.2 | +4.3 | +3.4 | 21.5 | 9.6 | +2.1 | +57.7 | -24.0 | hot, replicates, BHY |
| SOL | LIQMAP:Skew=high (rising in) | down | 5.57 | 52.7 | 52.5 | +3.7 | +3.7 | +3.2 | 20.6 | 7.9 | +1.1 | +69.1 | -30.1 | none |
| SOL | CVDP:Div15=high (rising in) | up | 13.00 | 48.3 | 51.6 | +1.6 | +1.6 | +2.7 | 20.4 | 7.1 | +0.2 | +55.0 | -21.6 | hot |
| BTC | CVDP:Div15=low (recovering) | down | 8.39 | 50.2 | 51.8 | +2.3 | +2.3 | +2.6 | 19.6 | 7.7 | +0.3 | +27.2 | -9.5 | none |
| BTC | CVDP:Div15=low (falling in) | down | 16.05 | 49.2 | 50.6 | +1.1 | +1.1 | +2.1 | 18.0 | 7.5 | +0.0 | +28.8 | -10.3 | none |
| SOL | CVDP:Div15=low (falling in) | down | 12.54 | 48.4 | 50.0 | +1.3 | +1.4 | +2.3 | 17.8 | 6.9 | +0.1 | +56.0 | -20.5 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 5.61 | 52.3 | 52.8 | +3.2 | +3.1 | +2.8 | 17.3 | 8.7 | +1.7 | +71.6 | -28.8 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 6.11 | 54.4 | 52.3 | +2.8 | +2.8 | +2.4 | 17.0 | 8.1 | +1.1 | +71.1 | -30.9 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 5.64 | 52.7 | 53.1 | +3.1 | +3.0 | +2.7 | 16.8 | 8.0 | +1.2 | +74.9 | -33.2 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 5.43 | 56.4 | 54.3 | +3.1 | +3.1 | +2.6 | 16.7 | 9.1 | +1.4 | +62.7 | -29.2 | hot, replicates |

Top 8 at 60 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.88 points, the 99th percentile 3.53):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=high (cooling) | down | 1.12 | 944 | 55.8 | +6.4 | +2.3 | 8.6 | +1.1 | -17.1 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.15 | 957 | 55.6 | +6.1 | +2.2 | 9.3 | +1.8 | -17.6 | hot |
| BTC | LIQMAP:Skew=very low | up | 1.71 | 1,488 | 56.5 | +6.0 | +2.5 | 8.8 | +1.3 | -23.7 | hot, replicates |
| XRP | LIQMAP:Skew=low (recovering) | up | 2.34 | 1,955 | 55.0 | +5.6 | +3.1 | 8.5 | +1.4 | -35.5 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 5.04 | 4,415 | 52.9 | +4.2 | +3.4 | 9.6 | +2.1 | -24.0 | hot, replicates, BHY |
| SOL | LIQMAP:Skew=very high | down | 1.86 | 1,594 | 52.9 | +4.1 | +1.8 | 8.2 | +1.4 | -33.1 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 1.71 | 1,473 | 54.7 | +4.1 | +1.9 | 8.6 | +1.1 | -22.9 | hot |
| XRP | LIQMAP:Skew=very low | up | 2.40 | 2,009 | 53.5 | +4.0 | +2.2 | 9.3 | +2.2 | -38.7 | hot, replicates |

## Every TA by heat

Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the direction the reading's current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). The horizon is the one with the most heat on A; the B columns score A's directions on B, so a reading with no information scores about zero.

| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |
|---|---|---|---|---|---|---|---|---|
| real | events | 11 | 0.9091 | 0.0909 | 0.0909 | 14.344 | 46.917 | 57.622 |
| twin | events | 33 | 0.5758 | 0.0303 | 0.0 | 4.319 | 34.374 | 50.865 |

Top 11 readings by events heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| BTC | CVDP:Div15 | 60 | 20.7 | +57.6 | +3.5 |
| SOL | CVDP:PxDiv60 | 60 | 77.1 | +36.2 | +1.3 |
| ETH | LIQMAP:Skew | 60 | 16.1 | +33.6 | +1.5 |
| ETH | CVDP:PxDiv60 | 60 | 25.2 | +26.7 | +1.1 |
| SOL | CVDP:Div15 | 30 | 63.5 | +23.3 | +1.3 |
| XRP | LIQMAP:Skew | 60 | 15.6 | +14.3 | +0.8 |
| SOL | LIQMAP:Skew | 30 | 11.0 | +13.3 | +1.2 |
| BTC | CVDP:PxDiv60 | 15 | 19.7 | +11.7 | +1.0 |
| ETH | CVDP:Div15 | 60 | 14.9 | +5.4 | +0.2 |
| XRP | CVDP:PxDiv60 | 60 | 24.5 | +2.0 | +0.1 |
| BTC | LIQMAP:Skew | 60 | 23.0 | -10.3 | -0.7 |

## Top 0 replicating by heat on B (windows per day x move, bps per day)

0 of 0 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Top 0 replicating by move per event on B (bps; at least 0.2 windows per day)

0 of 0 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Top 12 replicating by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)

6 of 12 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | triple | CVDP:Div15=low (falling in) / CVDP:PxDiv60=high / LIQMAP:Skew=very low | 5 | up | yes | 0.39 | +2.6 | +10.6 | 60.4 | +10.9 | 11.4 | -6.2 | +2.7 | 4.1 | +1.5 |  | +9.8 | +9.1 | 0.050 |
| ETH | single | LIQMAP:Skew=high (rising in) | 1/5/15/30/60 | down | yes | 6.66 | -0.0 | +5.5 | 54.7 | +5.6 | 9.6 | -18.0 | +5.0 | 36.8 | -0.5 | +0.2 |  |  | 0.000 |
| ETH | single | LIQMAP:Skew=very low | 1/5 | up | yes | 4.89 | +1.1 | +4.7 | 54.9 | +5.6 | 10.3 | -13.2 | +4.1 | 23.0 | +0.0 | +0.1 |  |  | 0.006 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.14 | +0.7 | +4.1 | 53.9 | +4.1 | 8.5 | -11.5 | +3.2 | 20.8 | +0.9 | +0.4 |  |  | 0.034 |
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 9.23 | -0.4 | +2.9 | 53.3 | +2.9 | 9.1 | -16.1 | +3.3 | 26.8 | -0.3 | -0.1 |  |  | 0.030 |
| ETH | single | CVDP:PxDiv60=high (rising in) | 15 | down | yes | 27.07 | +0.2 | +1.4 | 50.9 | +1.4 | 7.8 | -9.7 | +3.3 | 38.8 | +0.1 | -0.1 |  |  | 0.030 |
| BTC | single | LIQMAP:Skew=high (cooling) | 60 | down | no | 1.12 | +1.5 | +6.4 | 55.8 | +6.4 | 8.6 | -17.1 | +2.3 | 7.1 | +1.6 | +1.4 |  |  | 0.276 |
| BTC | single | LIQMAP:Skew=very low | 1/15/30/60 | up | no | 1.71 | +0.9 | +6.0 | 56.5 | +6.0 | 8.8 | -23.7 | +2.5 | 10.3 | +0.9 | -0.3 |  |  | 0.180 |
| XRP | single | LIQMAP:Skew=very low | 15/30/60 | up | no | 3.09 | +2.8 | +4.9 | 54.6 | +5.2 | 9.3 | -29.0 | +2.9 | 15.1 | +3.1 | -0.6 |  |  | 0.117 |
| ETH | single | LIQMAP:Skew=very high | 1/5/15 | down | no | 2.84 | -2.9 | +4.0 | 53.5 | +4.1 | 9.3 | -18.7 | +2.5 | 11.5 | -2.8 | +0.1 |  |  | 0.180 |
| XRP | single | LIQMAP:Skew=very high | 5 | down | no | 4.28 | -1.3 | +3.7 | 52.8 | +4.3 | 9.1 | -14.5 | +2.6 | 15.6 | -1.1 | -0.6 |  |  | 0.151 |
| BTC | single | CVDP:PxDiv60=low (recovering) | 15 | down | no | 3.48 | +0.8 | +3.3 | 53.4 | +3.3 | 7.9 | -6.7 | +2.3 | 11.4 | +0.9 | +0.2 |  |  | 0.207 |

## Top 13 replicating by odds heat on B (windows per day x odds points)

6 of 13 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | single | LIQMAP:Skew=high (rising in) | 1/5/15/30/60 | down | yes | 11.05 | +0.8 | +5.0 | 54.7 | +5.1 | 9.6 | -9.7 | +6.7 | 55.1 | +0.3 | +0.1 |  |  | 0.000 |
| ETH | single | CVDP:PxDiv60=high (rising in) | 15 | down | yes | 27.07 | +0.2 | +1.4 | 50.9 | +1.4 | 7.8 | -9.7 | +3.3 | 38.8 | +0.1 | -0.1 |  |  | 0.030 |
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 11.92 | -0.0 | +2.7 | 52.7 | +2.8 | 9.1 | -11.3 | +3.5 | 32.4 | +0.0 | +0.3 |  |  | 0.030 |
| ETH | single | LIQMAP:Skew=very low | 1/5 | up | yes | 4.89 | +1.1 | +4.7 | 54.9 | +5.6 | 10.3 | -13.2 | +4.1 | 23.0 | +0.0 | +0.1 |  |  | 0.006 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.14 | +0.7 | +4.1 | 53.9 | +4.1 | 8.5 | -11.5 | +3.2 | 20.8 | +0.9 | +0.4 |  |  | 0.034 |
| BTC | triple | CVDP:Div15=low (falling in) / CVDP:PxDiv60=high / LIQMAP:Skew=very low | 5 | up | yes | 0.39 | +2.6 | +10.6 | 60.4 | +10.9 | 11.4 | -6.2 | +2.7 | 4.1 | +1.5 |  | +9.8 | +9.1 | 0.050 |
| XRP | single | LIQMAP:Skew=very high | 5 | down | no | 4.28 | -1.3 | +3.7 | 52.8 | +4.3 | 9.1 | -14.5 | +2.6 | 15.6 | -1.1 | -0.6 |  |  | 0.151 |
| XRP | single | LIQMAP:Skew=very low | 15/30/60 | up | no | 3.09 | +2.8 | +4.9 | 54.6 | +5.2 | 9.3 | -29.0 | +2.9 | 15.1 | +3.1 | -0.6 |  |  | 0.117 |
| ETH | single | LIQMAP:Skew=very high | 1/5/15 | down | no | 3.95 | -0.1 | +3.4 | 52.9 | +4.1 | 9.3 | -11.8 | +2.5 | 13.3 | -0.0 | -0.3 |  |  | 0.162 |
| BTC | single | CVDP:PxDiv60=low (recovering) | 15 | down | no | 3.48 | +0.8 | +3.3 | 53.4 | +3.3 | 7.9 | -6.7 | +2.3 | 11.4 | +0.9 | +0.2 |  |  | 0.207 |
| BTC | single | LIQMAP:Skew=very low | 1/15/30/60 | up | no | 2.21 | +0.6 | +5.1 | 55.2 | +5.1 | 8.8 | -18.3 | +2.8 | 11.2 | +0.6 | -0.0 |  |  | 0.119 |
| BTC | single | LIQMAP:Skew=high (cooling) | 60 | down | no | 1.12 | +1.5 | +6.4 | 55.8 | +6.4 | 8.6 | -17.1 | +2.3 | 7.1 | +1.6 | +1.4 |  |  | 0.276 |
| ETH | pair | CVDP:Div15=low (falling in) / LIQMAP:Skew=very low | 15/30/60 | up | no | 0.16 | +30.7 | +20.0 | 71.2 | +20.0 | 15.2 | -27.9 | +3.3 | 3.2 | +29.2 |  | +20.8 | +19.2 | 0.296 |

## Tables

One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.

| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 323601349e5b8383382ba69b7deed1522b7c164498575bb65a6110518ba86fc8 |
| BTC~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 34c5f9023800a843d07f800b4f63be8e027b42f3c6a9753b0e106d25cd446b76 |
| BTC~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 73dd9c6be63b2a11f89234ff35bc8fa5a018f5f060f8194d8904734e7aa198df |
| BTC~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 80255d815a0a66767f37732754fb295ed8a16420d4a5bfaa3a9af5a34e115f99 |
| ETH | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | a9ab4eb94f546840cae69a58adae625ddbf2b20b892004d41261515386617f6c |
| ETH~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | f78b4253cfb7d2ce4b64f92f2f6e0deb2e053ab15e8fa9ae49bb3fd3cb08f864 |
| ETH~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | dff0f06964fe565cf3e18708bcb10a220f959dcdaa8d1db90c3b77b19119e174 |
| ETH~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 06ea7c56d5b2d8422b762528d9860dab5b2d5d63dd72627248f97aa9402a1308 |
| SOL | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | d210d525ad6113e5da95857dd01001e6396cf7812942611d4bc33f80fdb57678 |
| SOL~twin1 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | d5d1619adc7eac0dbe0caf162aacf412c74ef011cf8d3995cc7c228b97460336 |
| SOL~twin2 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 33acbac4294ebb7c40f4aa555fffd08ff95a8dc01220aea0225b5674cdc49195 |
| SOL~twin3 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 0058cc1bf9ea8e4bcb01f8c60c497fd2a326fc5caba3682ce37f0edf3b1f0a45 |
| XRP | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | f308169242bf993bb9117d24f2d7bb9c418742b0df22885d6ff64f84abde3825 |
| XRP~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 93316061c2884c7be1bbf0aab40b694e5a5dfdab9e983986e9de90e8b0c316ce |
| XRP~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | d522f2e6e0ff1f3cf71ea3689ff7c141eb3322a670fd93e8a77acedb8e4d5461 |
| XRP~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | c820f35909550af1f801114ddcf73f2c37b01635b8db5e9e540a7f2b27a8226b |
