# OR-HM1 heat map: league (coin price, discovery only)

Coins: BTC, ETH, SOL, XRP. No-signal twins: BTC~twin1, BTC~twin2, BTC~twin3, ETH~twin1, ETH~twin2, ETH~twin3, SOL~twin1, SOL~twin2, SOL~twin3, XRP~twin1, XRP~twin2, XRP~twin3.
Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute's open. A map, not a validated rule.

## Hot spots against chance

Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent's other events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest set, a higher replicate share and the BHY column are evidence.

| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |
|---|---|---|---|---|---|---|---|---|---|---|
| real | single | 360 | 1 | 1 | 1.0 | 1 | 80 | 33 | 0.4125 | 15 |
| real | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| real | pair | 2,055 | 2 | 0 | 0.0 | 0 | 14 | 0 | 0.0 | 0 |
| real | triple | 80 | 0 | 0 |  | 0 | 0 | 0 |  | 0 |
| twin (median of 3) | single | 360 | 0 (0 to 1) | 0 |  | 0 | 1 (0 to 2) | 0 |  | 0 |
| twin (median of 3) | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| twin (median of 3) | pair | 2,070 | 1 (0 to 1) | 0 |  | 0 | 4 (4 to 5) | 0 | 0.0 | 0 |
| twin (median of 3) | triple | 35 | 0 | 0 |  | 0 | 0 (0 to 1) | 0 |  | 0 |

Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): move_heat None, move_edge None, odds_edge None, odds_heat None.

## Direction: every event level, nothing cut (Amendment 3)

The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods (30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.

| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |
|---|---|---|---|---|---|---|---|---|
| 1 | real | 72 | 0.5417 | 0.1111 | 0.099 | 38.156 | 41.143 | 0.177 |
| 1 | twin | 216 | 0.5278 | 0.0093 | 0.063 | 20.042 | 26.69 | 0.036 |
| 5 | real | 72 | 0.7361 | 0.1944 | 0.679 | 47.315 | 59.541 | 0.328 |
| 5 | twin | 216 | 0.4769 | 0.0185 | -0.061 | 30.057 | 33.633 | 0.01 |
| 15 | real | 72 | 0.8056 | 0.2917 | 1.165 | 44.971 | 51.953 | 0.264 |
| 15 | twin | 216 | 0.5278 | 0.0324 | 0.071 | 22.873 | 30.612 | 0.021 |
| 30 | real | 72 | 0.7778 | 0.4028 | 1.367 | 32.38 | 33.583 | 0.321 |
| 30 | twin | 216 | 0.5093 | 0.0278 | 0.017 | 16.999 | 30.247 | 0.012 |
| 60 | real | 72 | 0.75 | 0.375 | 1.436 | 30.884 | 35.084 | 0.328 |
| 60 | twin | 216 | 0.463 | 0.0185 | -0.126 | 15.505 | 16.874 | 0.018 |

Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.

Top 12 at 1 minute by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | CVDP:Div15=high (rising in) | up | 34.44 | 33.6 | 45.7 | +0.7 | +1.2 | +3.1 | 41.1 | 7.2 | +0.4 | +6.2 | -6.3 | none |
| XRP | CVDP:Div15=high (rising in) | up | 34.04 | 34.9 | 46.7 | +0.5 | +1.1 | +2.6 | 36.9 | 7.1 | +0.1 | +5.3 | -5.4 | none |
| SOL | CVDP:Div15=low (falling in) | down | 33.12 | 35.9 | 45.0 | +0.3 | +1.0 | +2.2 | 32.3 | 7.0 | +0.2 | +5.9 | -5.9 | none |
| ETH | CVDP:Div15=very high | up | 12.69 | 44.7 | 50.5 | +1.2 | +2.0 | +2.8 | 25.6 | 8.4 | +0.6 | +3.9 | -4.1 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 12.49 | 51.6 | 51.7 | +2.4 | +1.9 | +2.5 | 23.2 | 9.2 | +1.4 | +7.9 | -8.2 | hot, replicates |
| SOL | LIQMAP:Skew=high (rising in) | down | 14.43 | 40.2 | 47.0 | +2.3 | +1.4 | +2.2 | 20.5 | 7.5 | +0.7 | +8.1 | -8.4 | none |
| ETH | CVDP:Div15=high (cooling) | up | 11.34 | 46.1 | 50.2 | +0.9 | +1.6 | +2.1 | 18.0 | 8.3 | +0.5 | +3.9 | -4.0 | hot, replicates |
| ETH | CVDP:PxDiv60=low (falling in) | down | 25.73 | 47.7 | 49.4 | +0.6 | +0.7 | +1.5 | 18.0 | 7.7 | +0.2 | +5.2 | -5.0 | none |
| XRP | LIQMAP:Skew=very high | down | 5.24 | 39.1 | 50.7 | +4.7 | +3.3 | +2.8 | 17.3 | 8.4 | +1.4 | +10.4 | -10.2 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 13.89 | 38.5 | 48.3 | +2.1 | +1.1 | +1.7 | 15.1 | 8.1 | +1.0 | +9.1 | -9.3 | none |
| BTC | CVDP:Div15=high (cooling) | up | 20.52 | 45.8 | 45.4 | -1.2 | +0.6 | +1.2 | 13.2 | 7.9 | +0.3 | +2.1 | -2.1 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 9.06 | 50.5 | 50.1 | +3.6 | +1.2 | +1.3 | 11.0 | 8.1 | +0.7 | +4.1 | -4.0 | none |

Top 8 at 1 minute by share right over base on B (at least 0.2 windows per day; the best twin level reaches 5.79 points, the 99th percentile 3.78):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=very high | down | 5.24 | 1,912 | 50.7 | +4.7 | +2.8 | 8.4 | +1.4 | -10.2 | none |
| BTC | LIQMAP:Skew=high (cooling) | down | 2.64 | 965 | 50.5 | +4.0 | +0.6 | 8.6 | +1.2 | -5.3 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 4.19 | 1,529 | 50.5 | +3.9 | +0.4 | 8.8 | +1.2 | -6.4 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 9.06 | 3,307 | 50.1 | +3.6 | +1.3 | 8.1 | +0.7 | -4.0 | none |
| XRP | LIQMAP:Skew=very low | up | 5.27 | 1,922 | 49.4 | +3.2 | +1.3 | 8.6 | +1.5 | -11.2 | none |
| SOL | LIQMAP:Skew=low (recovering) | down | 4.48 | 1,635 | 47.8 | +3.1 | +0.4 | 7.7 | +0.9 | -11.3 | none |
| XRP | CVDP:PxDiv60=low (recovering) | down | 3.34 | 1,219 | 49.1 | +3.1 | +1.6 | 8.0 | +1.0 | -7.3 | none |
| BTC | LIQMAP:Skew=very high | down | 2.69 | 981 | 49.4 | +3.0 | +0.1 | 8.3 | +0.9 | -5.6 | none |

Top 12 at 5 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | CVDP:Div15=high (rising in) | up | 32.16 | 42.4 | 49.6 | +1.7 | +1.9 | +4.4 | 59.5 | 7.2 | +0.4 | +15.2 | -7.8 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 11.76 | 53.3 | 53.3 | +3.7 | +3.6 | +5.0 | 42.3 | 8.6 | +1.1 | +16.4 | -8.5 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=low (falling in) | up | 11.38 | 54.0 | 53.2 | +3.3 | +3.2 | +4.1 | 36.4 | 9.2 | +1.4 | +18.7 | -10.0 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=low (falling in) | up | 12.74 | 47.4 | 51.4 | +3.1 | +2.8 | +3.7 | 35.5 | 8.1 | +1.0 | +21.2 | -11.3 | none |
| ETH | CVDP:Div15=low (falling in) | down | 33.38 | 49.4 | 50.6 | +1.0 | +1.0 | +2.4 | 34.3 | 7.8 | +0.3 | +12.1 | -6.1 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 13.57 | 44.2 | 51.4 | +2.9 | +2.4 | +3.3 | 32.9 | 7.9 | +0.9 | +20.5 | -10.4 | none |
| ETH | CVDP:Div15=high (rising in) | up | 37.15 | 49.7 | 50.7 | +0.8 | +0.8 | +2.1 | 31.4 | 8.2 | +0.4 | +12.0 | -6.1 | none |
| BTC | CVDP:Div15=low (falling in) | down | 41.94 | 49.6 | 50.5 | +0.6 | +0.7 | +1.7 | 28.8 | 7.7 | +0.2 | +7.2 | -3.5 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 13.25 | 47.4 | 49.8 | +2.0 | +1.9 | +2.6 | 25.2 | 7.5 | +0.7 | +19.3 | -10.5 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 12.36 | 46.5 | 50.1 | +2.1 | +1.8 | +2.6 | 22.8 | 8.0 | +1.1 | +22.6 | -12.1 | none |
| XRP | CVDP:Div15=high (rising in) | up | 31.60 | 43.8 | 48.6 | +0.3 | +0.6 | +1.4 | 19.7 | 7.1 | +0.1 | +13.2 | -6.6 | none |
| BTC | CVDP:Div15=high (cooling) | up | 19.22 | 50.1 | 50.3 | +0.8 | +1.0 | +1.7 | 19.0 | 7.9 | +0.3 | +5.9 | -2.7 | none |

Top 8 at 5 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 3.18 points, the 99th percentile 2.87):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=high (cooling) | down | 4.61 | 1,854 | 53.1 | +4.6 | +3.1 | 8.1 | +1.1 | -11.8 | none |
| XRP | LIQMAP:Skew=very high | down | 4.83 | 1,912 | 52.3 | +3.8 | +2.5 | 8.4 | +1.4 | -12.4 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 11.76 | 4,714 | 53.3 | +3.7 | +5.0 | 8.6 | +1.1 | -8.5 | hot, replicates, BHY |
| ETH | LIQMAP:Skew=low (falling in) | up | 11.38 | 4,559 | 53.2 | +3.3 | +4.1 | 9.2 | +1.4 | -10.0 | hot, replicates, BHY |
| SOL | LIQMAP:Skew=low (recovering) | up | 4.02 | 1,635 | 51.2 | +3.2 | +1.9 | 6.9 | -0.0 | -14.2 | none |
| XRP | LIQMAP:Skew=very low | up | 4.82 | 1,922 | 51.5 | +3.2 | +2.0 | 8.6 | +1.5 | -13.6 | none |
| ETH | LIQMAP:Skew=low (recovering) | up | 4.26 | 1,708 | 53.1 | +3.2 | +2.3 | 8.3 | +0.6 | -13.2 | hot, replicates |
| XRP | LIQMAP:Skew=low (falling in) | up | 12.74 | 5,069 | 51.4 | +3.1 | +3.7 | 8.1 | +1.0 | -11.3 | none |

Top 12 at 15 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | CVDP:Div15=high (rising in) | up | 37.45 | 50.4 | 51.2 | +1.4 | +1.4 | +3.7 | 52.0 | 7.6 | +0.1 | +12.9 | -5.2 | none |
| SOL | CVDP:Div15=high (rising in) | up | 26.48 | 46.1 | 50.4 | +1.5 | +1.6 | +3.4 | 42.1 | 7.2 | +0.4 | +27.0 | -11.4 | none |
| ETH | CVDP:Div15=high (rising in) | up | 30.49 | 50.1 | 51.5 | +1.2 | +1.2 | +2.8 | 37.2 | 8.2 | +0.4 | +22.3 | -9.1 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 8.89 | 54.7 | 53.3 | +3.9 | +3.9 | +4.5 | 34.2 | 8.6 | +1.1 | +29.1 | -12.3 | hot, replicates, BHY |
| BTC | CVDP:Div15=high (cooling) | up | 16.36 | 50.4 | 51.8 | +1.9 | +2.0 | +3.1 | 33.0 | 7.9 | +0.3 | +11.3 | -4.3 | none |
| XRP | CVDP:Div15=low (falling in) | down | 21.97 | 45.0 | 50.5 | +1.3 | +1.5 | +3.1 | 32.9 | 7.3 | +0.3 | +23.3 | -9.6 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 10.24 | 49.0 | 52.6 | +3.3 | +3.2 | +3.7 | 32.5 | 7.9 | +0.9 | +35.3 | -15.6 | none |
| BTC | CVDP:Div15=low (recovering) | down | 14.84 | 50.3 | 52.2 | +2.2 | +2.2 | +3.4 | 32.4 | 7.4 | -0.0 | +12.0 | -4.6 | none |
| XRP | LIQMAP:Skew=low (falling in) | up | 9.80 | 52.0 | 52.4 | +3.4 | +3.3 | +4.0 | 32.3 | 8.1 | +1.0 | +37.3 | -16.3 | none |
| BTC | CVDP:Div15=very low | down | 17.46 | 50.1 | 51.8 | +1.8 | +1.8 | +2.9 | 31.8 | 7.8 | +0.4 | +11.6 | -4.6 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 8.72 | 55.7 | 54.0 | +3.6 | +3.6 | +4.0 | 31.4 | 9.2 | +1.4 | +32.9 | -14.6 | hot, replicates, BHY |
| ETH | CVDP:Div15=low (falling in) | down | 27.53 | 49.4 | 50.5 | +1.1 | +1.1 | +2.5 | 30.7 | 7.8 | +0.3 | +22.1 | -8.8 | none |

Top 8 at 15 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 3.49 points, the 99th percentile 3.24):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=very high | down | 3.73 | 1,912 | 54.8 | +5.6 | +3.9 | 8.4 | +1.4 | -18.0 | none |
| XRP | LIQMAP:Skew=very low | up | 3.68 | 1,922 | 52.9 | +3.9 | +3.0 | 8.6 | +1.5 | -20.1 | hot |
| ETH | LIQMAP:Skew=high (rising in) | down | 8.89 | 4,714 | 53.3 | +3.9 | +4.5 | 8.6 | +1.1 | -12.3 | hot, replicates, BHY |
| BTC | LIQMAP:Skew=very low | up | 2.86 | 1,550 | 53.6 | +3.8 | +2.4 | 8.3 | +0.8 | -13.1 | hot, replicates |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.82 | 965 | 53.7 | +3.6 | +1.8 | 8.6 | +1.2 | -9.9 | hot |
| ETH | LIQMAP:Skew=low (falling in) | up | 8.72 | 4,559 | 54.0 | +3.6 | +4.0 | 9.2 | +1.4 | -14.6 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=low (falling in) | up | 9.80 | 5,069 | 52.4 | +3.4 | +4.0 | 8.1 | +1.0 | -16.3 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 10.24 | 5,416 | 52.6 | +3.3 | +3.7 | 7.9 | +0.9 | -15.6 | none |

Top 12 at 30 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | CVDP:Div15=high (rising in) | up | 21.47 | 47.5 | 51.0 | +1.4 | +1.6 | +3.2 | 33.6 | 7.2 | +0.4 | +38.9 | -15.8 | hot |
| ETH | CVDP:Div15=high (rising in) | up | 24.72 | 50.8 | 52.0 | +1.3 | +1.3 | +2.8 | 31.9 | 8.2 | +0.4 | +32.2 | -12.6 | none |
| BTC | CVDP:Div15=low (falling in) | down | 27.23 | 49.9 | 50.9 | +1.1 | +1.1 | +2.8 | 30.5 | 7.7 | +0.2 | +20.0 | -7.5 | none |
| BTC | CVDP:Div15=very low | down | 15.04 | 50.7 | 51.7 | +2.0 | +1.9 | +3.2 | 29.2 | 7.8 | +0.4 | +17.1 | -6.5 | none |
| BTC | CVDP:Div15=very high | up | 15.89 | 50.9 | 51.9 | +1.7 | +1.7 | +2.7 | 27.3 | 7.6 | +0.1 | +16.1 | -6.0 | none |
| ETH | LIQMAP:Skew=high (rising in) | down | 7.00 | 55.3 | 53.1 | +3.9 | +3.9 | +4.0 | 27.2 | 8.6 | +1.1 | +40.5 | -16.2 | hot, replicates, BHY |
| ETH | CVDP:Div15=low (falling in) | down | 22.49 | 49.6 | 50.3 | +1.2 | +1.2 | +2.6 | 27.0 | 7.8 | +0.3 | +32.3 | -12.1 | none |
| XRP | LIQMAP:Skew=high (rising in) | down | 8.00 | 50.9 | 52.6 | +3.3 | +3.1 | +3.5 | 24.5 | 7.9 | +0.9 | +49.1 | -20.9 | none |
| SOL | CVDP:Div15=low (falling in) | down | 20.84 | 48.1 | 49.7 | +1.0 | +1.2 | +2.5 | 24.4 | 7.0 | +0.2 | +38.4 | -14.8 | hot, replicates |
| XRP | LIQMAP:Skew=low (falling in) | up | 7.71 | 52.8 | 52.6 | +3.2 | +3.0 | +3.2 | 23.5 | 8.1 | +1.0 | +52.8 | -22.7 | none |
| SOL | LIQMAP:Skew=low (falling in) | up | 7.33 | 51.8 | 52.9 | +3.3 | +3.1 | +3.5 | 23.0 | 8.0 | +1.1 | +55.1 | -24.1 | none |
| ETH | CVDP:PxDiv60=low (falling in) | down | 14.15 | 50.1 | 50.7 | +1.6 | +1.6 | +2.4 | 22.2 | 7.7 | +0.2 | +36.5 | -12.9 | hot, replicates |

Top 8 at 30 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.5 points, the 99th percentile 4.08):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | LIQMAP:Skew=low (recovering) | up | 2.85 | 1,878 | 56.3 | +7.0 | +3.9 | 7.8 | +0.7 | -27.4 | hot, replicates, BHY |
| XRP | LIQMAP:Skew=very low | up | 2.89 | 1,922 | 55.3 | +5.9 | +3.6 | 8.6 | +1.5 | -28.7 | hot, replicates, BHY |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.45 | 965 | 55.0 | +5.3 | +2.2 | 8.6 | +1.2 | -13.1 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.50 | 981 | 54.5 | +4.8 | +2.1 | 8.3 | +0.9 | -14.4 | hot |
| BTC | LIQMAP:Skew=very low | up | 2.27 | 1,550 | 54.3 | +4.2 | +2.4 | 8.3 | +0.8 | -17.8 | hot, replicates |
| SOL | LIQMAP:Skew=high (cooling) | down | 2.63 | 1,791 | 52.7 | +4.0 | +2.3 | 7.6 | +0.8 | -22.2 | none |
| ETH | LIQMAP:Skew=low (recovering) | up | 2.54 | 1,708 | 54.6 | +3.9 | +2.2 | 8.3 | +0.6 | -25.9 | hot, replicates |
| ETH | LIQMAP:Skew=high (rising in) | down | 7.00 | 4,714 | 53.1 | +3.9 | +4.0 | 8.6 | +1.1 | -16.2 | hot, replicates, BHY |

Top 12 at 60 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | CVDP:Div15=high (rising in) | up | 17.50 | 51.3 | 53.2 | +2.0 | +2.0 | +4.1 | 35.1 | 8.2 | +0.4 | +47.0 | -18.2 | none |
| SOL | CVDP:Div15=low (falling in) | down | 15.23 | 48.6 | 50.6 | +1.8 | +1.9 | +3.8 | 29.2 | 7.0 | +0.2 | +56.3 | -21.0 | none |
| ETH | CVDP:Div15=low (falling in) | down | 16.37 | 49.4 | 50.3 | +1.7 | +1.7 | +3.2 | 27.2 | 7.8 | +0.3 | +47.8 | -17.2 | none |
| BTC | CVDP:Div15=low (falling in) | down | 18.80 | 49.8 | 50.8 | +1.3 | +1.3 | +3.1 | 24.9 | 7.7 | +0.2 | +29.6 | -10.5 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 5.89 | 52.6 | 52.8 | +4.1 | +4.0 | +3.8 | 23.5 | 7.5 | +0.7 | +69.0 | -29.4 | hot, replicates, BHY |
| SOL | CVDP:Div15=high (rising in) | up | 15.57 | 48.6 | 51.5 | +1.4 | +1.4 | +2.6 | 21.7 | 7.2 | +0.4 | +56.3 | -22.1 | hot, replicates |
| ETH | CVDP:PxDiv60=low (falling in) | down | 11.06 | 49.7 | 50.5 | +1.9 | +1.9 | +2.7 | 21.0 | 7.7 | +0.2 | +53.8 | -18.5 | none |
| BTC | CVDP:Div15=very low | down | 11.78 | 50.2 | 51.2 | +1.7 | +1.7 | +2.9 | 20.5 | 7.8 | +0.4 | +25.2 | -9.2 | none |
| ETH | LIQMAP:Skew=low (falling in) | up | 5.18 | 56.2 | 55.1 | +3.9 | +3.8 | +3.6 | 19.9 | 9.2 | +1.4 | +63.0 | -28.5 | hot, replicates, BHY |
| BTC | CVDP:Div15=high (rising in) | up | 19.63 | 51.4 | 51.5 | +1.0 | +1.0 | +2.6 | 19.9 | 7.6 | +0.1 | +27.2 | -10.5 | none |
| BTC | CVDP:Div15=very high | up | 12.24 | 51.8 | 52.1 | +1.6 | +1.6 | +2.3 | 19.1 | 7.6 | +0.1 | +23.8 | -8.9 | none |
| ETH | CVDP:Div15=very high | up | 7.49 | 51.5 | 53.8 | +2.5 | +2.5 | +2.8 | 19.1 | 8.4 | +0.6 | +40.2 | -15.3 | none |

Top 8 at 60 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.17 points, the 99th percentile 3.23):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=high (cooling) | down | 1.16 | 965 | 56.3 | +6.8 | +2.6 | 8.6 | +1.2 | -17.4 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.18 | 981 | 55.4 | +5.9 | +2.3 | 8.3 | +0.9 | -18.5 | hot, replicates |
| BTC | LIQMAP:Skew=very low | up | 1.77 | 1,550 | 55.2 | +4.7 | +2.3 | 8.3 | +0.8 | -23.4 | hot, replicates |
| XRP | LIQMAP:Skew=very low | up | 2.26 | 1,922 | 54.2 | +4.7 | +2.5 | 8.6 | +1.5 | -37.9 | hot, replicates |
| XRP | LIQMAP:Skew=low (recovering) | up | 2.21 | 1,878 | 53.9 | +4.4 | +2.4 | 7.8 | +0.7 | -35.8 | hot, replicates |
| SOL | LIQMAP:Skew=very high | down | 2.08 | 1,813 | 52.9 | +4.1 | +2.2 | 8.2 | +1.4 | -30.0 | none |
| SOL | LIQMAP:Skew=high (rising in) | down | 5.89 | 5,266 | 52.8 | +4.1 | +3.8 | 7.5 | +0.7 | -29.4 | hot, replicates, BHY |
| BTC | LIQMAP:Skew=high (rising in) | down | 3.87 | 3,307 | 53.3 | +3.9 | +2.8 | 8.1 | +0.7 | -14.6 | hot, replicates, BHY |

## Every TA by heat

Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the direction the reading's current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). The horizon is the one with the most heat on A; the B columns score A's directions on B, so a reading with no information scores about zero.

| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |
|---|---|---|---|---|---|---|---|---|
| real | events | 12 | 0.6667 | 0.1667 | 0.0833 | 15.57 | 55.451 | 64.907 |
| twin | events | 35 | 0.5143 | 0.0571 | 0.0 | 0.319 | 39.836 | 43.481 |

Top 12 readings by events heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| BTC | CVDP:Div15 | 60 | 25.2 | +64.9 | +4.0 |
| SOL | CVDP:Div15 | 60 | 49.6 | +47.7 | +2.1 |
| SOL | CVDP:PxDiv60 | 60 | 69.0 | +41.5 | +1.5 |
| ETH | LIQMAP:Skew | 60 | 19.5 | +38.2 | +1.6 |
| SOL | LIQMAP:Skew | 60 | 26.1 | +36.2 | +1.6 |
| ETH | CVDP:PxDiv60 | 60 | 24.6 | +18.3 | +0.7 |
| XRP | CVDP:Div15 | 60 | 9.8 | +12.9 | +1.4 |
| BTC | LIQMAP:Skew | 15 | 19.5 | +2.1 | +0.2 |
| BTC | CVDP:PxDiv60 | 30 | 18.6 | -1.5 | -0.1 |
| XRP | CVDP:PxDiv60 | 60 | 16.8 | -6.7 | -0.4 |
| ETH | CVDP:Div15 | 15 | 17.8 | -20.2 | -1.3 |
| XRP | LIQMAP:Skew | 60 | 18.4 | -25.1 | -1.2 |

## Top 1 replicating by heat on B (windows per day x move, bps per day)

1 of 1 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | single | CVDP:Div15=very low | 1 | up | yes | 21.89 | +0.1 | -0.0 | 45.4 | -1.2 | 7.4 | -2.2 | +2.1 | 2.6 | +0.0 | +0.0 |  |  | 0.018 |

## Top 1 replicating by move per event on B (bps; at least 0.2 windows per day)

1 of 1 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | single | CVDP:Div15=very low | 1 | up | yes | 21.89 | +0.1 | -0.0 | 45.4 | -1.2 | 7.4 | -2.2 | +2.1 | 2.6 | +0.0 | +0.0 |  |  | 0.018 |

## Top 18 replicating by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)

8 of 18 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | single | LIQMAP:Skew=low (recovering) | 30/60 | up | yes | 2.85 | +3.1 | +6.7 | 56.3 | +7.0 | 7.8 | -27.4 | +3.9 | 19.0 | +2.9 | +0.0 |  |  | 0.022 |
| XRP | single | LIQMAP:Skew=very low | 30/60 | up | yes | 2.89 | +0.9 | +5.8 | 55.3 | +5.9 | 8.6 | -28.7 | +3.6 | 16.7 | +0.7 | -0.8 |  |  | 0.018 |
| SOL | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.89 | +1.7 | +4.0 | 52.8 | +4.1 | 7.5 | -29.4 | +3.8 | 23.5 | +1.8 | +0.6 |  |  | 0.009 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 3.87 | -0.3 | +3.9 | 53.3 | +3.9 | 8.1 | -14.6 | +2.8 | 15.1 | -0.3 | -0.4 |  |  | 0.066 |
| ETH | single | LIQMAP:Skew=high (rising in) | 5/15/30/60 | down | yes | 7.00 | -0.1 | +3.9 | 53.1 | +3.9 | 8.6 | -16.2 | +4.0 | 27.2 | -0.1 | -0.6 |  |  | 0.009 |
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 5.18 | -0.5 | +3.8 | 55.1 | +3.9 | 9.2 | -28.5 | +3.6 | 19.9 | -0.8 | +0.4 |  |  | 0.018 |
| XRP | single | LIQMAP:Skew=low (falling in) | 60 | up | yes | 5.79 | +4.4 | +3.1 | 52.7 | +3.2 | 8.1 | -31.1 | +2.9 | 17.8 | +4.3 | +0.1 |  |  | 0.066 |
| ETH | single | CVDP:Div15=very low | 60 | down | yes | 6.66 | +0.0 | +2.6 | 51.3 | +2.6 | 8.0 | -15.6 | +2.8 | 17.4 | +0.1 | +0.3 |  |  | 0.066 |
| BTC | single | LIQMAP:Skew=high (cooling) | 30/60 | down | no | 1.16 | +3.9 | +6.8 | 56.3 | +6.8 | 8.6 | -17.4 | +2.6 | 7.9 | +3.6 | +1.3 |  |  | 0.132 |
| BTC | single | LIQMAP:Skew=very high | 60 | down | no | 1.18 | +2.1 | +5.9 | 55.4 | +5.9 | 8.3 | -18.5 | +2.3 | 7.0 | +2.1 | +0.6 |  |  | 0.197 |
| BTC | single | LIQMAP:Skew=very low | 15/30/60 | up | no | 1.77 | +2.9 | +4.7 | 55.2 | +4.7 | 8.3 | -23.4 | +2.3 | 8.3 | +2.9 | -0.5 |  |  | 0.169 |
| ETH | single | LIQMAP:Skew=low (recovering) | 5/30 | up | no | 2.54 | -2.3 | +3.9 | 54.6 | +3.9 | 8.3 | -25.9 | +2.2 | 9.9 | -2.2 | +0.4 |  |  | 0.197 |
| BTC | single | LIQMAP:Skew=low (recovering) | 30 | up | no | 2.20 | +0.6 | +3.9 | 54.1 | +3.9 | 8.8 | -16.6 | +2.2 | 8.5 | +1.0 | +0.0 |  |  | 0.197 |
| ETH | single | CVDP:Div15=high (cooling) | 1 | up | no | 11.34 | +0.1 | +1.6 | 50.2 | +0.9 | 8.3 | -4.0 | +2.1 | 18.0 | +0.0 | -0.1 |  |  | 0.199 |
| ETH | single | CVDP:PxDiv60=low (falling in) | 30 | down | no | 14.15 | +0.7 | +1.6 | 50.7 | +1.6 | 7.7 | -12.9 | +2.4 | 22.2 | +0.6 | +0.3 |  |  | 0.149 |
| BTC | single | CVDP:Div15=low (recovering) | 60 | down | no | 10.44 | +0.8 | +1.6 | 51.0 | +1.6 | 7.4 | -9.2 | +2.3 | 16.3 | +0.8 | +0.3 |  |  | 0.165 |
| SOL | single | CVDP:Div15=high (rising in) | 60 | up | no | 15.57 | +1.1 | +1.4 | 51.5 | +1.4 | 7.2 | -22.1 | +2.6 | 21.7 | +0.8 | -0.0 |  |  | 0.111 |
| SOL | single | CVDP:Div15=low (falling in) | 30 | down | no | 20.84 | +0.6 | +1.2 | 49.7 | +1.0 | 7.0 | -14.8 | +2.5 | 24.4 | +0.5 | -0.2 |  |  | 0.132 |

## Top 18 replicating by odds heat on B (windows per day x odds points)

8 of 18 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | single | LIQMAP:Skew=high (rising in) | 5/15/30/60 | down | yes | 11.76 | +0.6 | +3.6 | 53.3 | +3.7 | 8.6 | -8.5 | +5.0 | 42.3 | +0.7 | -0.4 |  |  | 0.001 |
| ETH | single | LIQMAP:Skew=low (falling in) | 1/5/15/30/60 | up | yes | 11.38 | +0.3 | +3.2 | 53.2 | +3.3 | 9.2 | -10.0 | +4.1 | 36.4 | +0.0 | +0.1 |  |  | 0.007 |
| SOL | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.89 | +1.7 | +4.0 | 52.8 | +4.1 | 7.5 | -29.4 | +3.8 | 23.5 | +1.8 | +0.6 |  |  | 0.009 |
| XRP | single | LIQMAP:Skew=low (recovering) | 30/60 | up | yes | 2.85 | +3.1 | +6.7 | 56.3 | +7.0 | 7.8 | -27.4 | +3.9 | 19.0 | +2.9 | +0.0 |  |  | 0.022 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | yes | 5.15 | +0.1 | +3.6 | 53.4 | +3.6 | 8.1 | -10.7 | +3.0 | 18.6 | -0.0 | +0.0 |  |  | 0.054 |
| XRP | single | LIQMAP:Skew=low (falling in) | 60 | up | yes | 5.79 | +4.4 | +3.1 | 52.7 | +3.2 | 8.1 | -31.1 | +2.9 | 17.8 | +4.3 | +0.1 |  |  | 0.066 |
| ETH | single | CVDP:Div15=very low | 60 | down | yes | 6.66 | +0.0 | +2.6 | 51.3 | +2.6 | 8.0 | -15.6 | +2.8 | 17.4 | +0.1 | +0.3 |  |  | 0.066 |
| XRP | single | LIQMAP:Skew=very low | 30/60 | up | yes | 2.89 | +0.9 | +5.8 | 55.3 | +5.9 | 8.6 | -28.7 | +3.6 | 16.7 | +0.7 | -0.8 |  |  | 0.018 |
| SOL | single | CVDP:Div15=low (falling in) | 30 | down | no | 20.84 | +0.6 | +1.2 | 49.7 | +1.0 | 7.0 | -14.8 | +2.5 | 24.4 | +0.5 | -0.2 |  |  | 0.132 |
| ETH | single | CVDP:PxDiv60=low (falling in) | 30 | down | no | 14.15 | +0.7 | +1.6 | 50.7 | +1.6 | 7.7 | -12.9 | +2.4 | 22.2 | +0.6 | +0.3 |  |  | 0.149 |
| SOL | single | CVDP:Div15=high (rising in) | 60 | up | no | 15.57 | +1.1 | +1.4 | 51.5 | +1.4 | 7.2 | -22.1 | +2.6 | 21.7 | +0.8 | -0.0 |  |  | 0.111 |
| ETH | single | CVDP:Div15=high (cooling) | 1 | up | no | 11.34 | +0.1 | +1.6 | 50.2 | +0.9 | 8.3 | -4.0 | +2.1 | 18.0 | +0.0 | -0.1 |  |  | 0.199 |
| BTC | single | CVDP:Div15=low (recovering) | 60 | down | no | 10.44 | +0.8 | +1.6 | 51.0 | +1.6 | 7.4 | -9.2 | +2.3 | 16.3 | +0.8 | +0.3 |  |  | 0.165 |
| ETH | single | LIQMAP:Skew=low (recovering) | 5/30 | up | no | 4.26 | +0.9 | +3.2 | 53.1 | +3.2 | 8.3 | -13.2 | +2.3 | 13.5 | +1.0 | +0.5 |  |  | 0.169 |
| BTC | single | LIQMAP:Skew=very low | 15/30/60 | up | no | 2.86 | +0.5 | +3.7 | 53.6 | +3.8 | 8.3 | -13.1 | +2.4 | 10.6 | +0.5 | +0.1 |  |  | 0.149 |
| BTC | single | LIQMAP:Skew=low (recovering) | 30 | up | no | 2.20 | +0.6 | +3.9 | 54.1 | +3.9 | 8.8 | -16.6 | +2.2 | 8.5 | +1.0 | +0.0 |  |  | 0.197 |
| BTC | single | LIQMAP:Skew=high (cooling) | 30/60 | down | no | 1.16 | +3.9 | +6.8 | 56.3 | +6.8 | 8.6 | -17.4 | +2.6 | 7.9 | +3.6 | +1.3 |  |  | 0.132 |
| BTC | single | LIQMAP:Skew=very high | 60 | down | no | 1.18 | +2.1 | +5.9 | 55.4 | +5.9 | 8.3 | -18.5 | +2.3 | 7.0 | +2.1 | +0.6 |  |  | 0.197 |

## Tables

One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.

| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 491e14b6e4cf571714b0e02c127c72bdf666cf498a5baa95bc7ddd92a3cf4b2b |
| BTC~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 35f99e5ede6f4cd037d73830eddb47a44349e4bc4bb24fe187283069bdab5b30 |
| BTC~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 6f6b305ce6f4b9a2906ed8f0c5fa6b0caa72c9c5ec1c26c80dca869196746b5e |
| BTC~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 7fc3b0ab480f3e8f5177ccbcc38aeac69abb65332eb54e438f0ce17fbb327c76 |
| ETH | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | f5dc9531ed55358c0958bc2355bc238f8975ac323437bc5726ffd6d7864cd5ea |
| ETH~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | ce4dec7344784ada7e7ef062e101603fc2326e831df176806fe1120ba8adbc7a |
| ETH~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 503c2d26b680a08cdf7160ba8d218efff4762e79913b0d84fdaf0091c21e6e31 |
| ETH~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | 3556a804c40cce88247d425f81dbda8335c7fff2b8daf9a930566a3adab492e5 |
| SOL | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 1930bb0b43c4bc2146520f0c0994f5a68996522994174773227793e91617aefc |
| SOL~twin1 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 67b49cf512b6ff79c39a01490c1357f5ffaabf73c5419cd63082c7ea7cfe7262 |
| SOL~twin2 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 878fa516615ac7e5d5094ea2a1470722102c7790bd4e5918c56b1c83b926cd92 |
| SOL~twin3 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 6eb96b36c3e2c1caea28d8474cef4a4dba09f1d936267ed328549213bb452ee0 |
| XRP | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | d9a1088bcf5b12b28cf595391c8bba9fcc0f6e9785a50f8a05cb6fe28c2b4291 |
| XRP~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 5b0be7b5a2f589fa2617202d37a4c4a0f1de0a23dbef3cec463198b1330127ef |
| XRP~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 963971c5fcff1dc05143507f910724a21101adc9f5ef145bdc97a6b571727f16 |
| XRP~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | f35c1702db8501a83fb8938affc4430da346e589baab0fd63d979b8bc1c97176 |
