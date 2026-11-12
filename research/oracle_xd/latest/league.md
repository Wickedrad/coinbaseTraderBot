# OR-HM1 heat map: league (coin price, discovery only)

Coins: BTC. No-signal twins: BTC~twin1, BTC~twin2, BTC~twin3.
Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute's open. A map, not a validated rule.
**WARNING: expected BTC, ETH, SOL, XRP; this league is partial.**

## Hot spots against chance

Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent's other events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest set, a higher replicate share and the BHY column are evidence.

| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |
|---|---|---|---|---|---|---|---|---|---|---|
| real | single | 90 | 2 | 0 | 0.0 | 0 | 39 | 8 | 0.2051 | 0 |
| real | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| real | pair | 650 | 1 | 0 | 0.0 | 0 | 11 | 0 | 0.0 | 0 |
| real | triple | 65 | 0 | 0 |  | 0 | 2 | 1 | 0.5 | 1 |
| twin (median of 3) | single | 90 | 0 (0 to 3) | 0 |  | 0 | 0 | 0 |  | 0 |
| twin (median of 3) | curve | 0 | 0 | 0 |  |  | 0 | 0 |  |  |
| twin (median of 3) | pair | 660 | 0 (0 to 1) | 0 |  | 0 | 4 (2 to 4) | 0 | 0.0 | 0 |
| twin (median of 3) | triple | 30 | 0 | 0 |  | 0 | 0 | 0 |  | 0 |

Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): move_heat None, move_edge None, odds_edge None, odds_heat None.

## Direction: every event level, nothing cut (Amendment 3)

The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods (30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.

| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |
|---|---|---|---|---|---|---|---|---|
| 1 | real | 18 | 0.6667 | 0.1111 | 0.398 | 15.11 | 15.311 | 0.323 |
| 1 | twin | 54 | 0.5556 | 0.0 | 0.03 | 19.963 | 24.358 | 0.223 |
| 5 | real | 18 | 0.6111 | 0.0 | 0.208 | 23.957 | 24.684 | 0.163 |
| 5 | twin | 54 | 0.5185 | 0.0 | 0.1 | 17.903 | 22.301 | 0.202 |
| 15 | real | 18 | 0.5556 | 0.1667 | 0.145 | 13.614 | 13.646 | 0.19 |
| 15 | twin | 54 | 0.5 | 0.0 | 0.009 | 14.562 | 15.717 | 0.268 |
| 30 | real | 18 | 0.6111 | 0.1111 | 0.558 | 19.214 | 20.85 | 0.19 |
| 30 | twin | 54 | 0.4444 | 0.037 | -0.101 | 16.941 | 23.224 | 0.183 |
| 60 | real | 18 | 0.7778 | 0.3889 | 1.0 | 21.644 | 22.061 | 0.231 |
| 60 | twin | 54 | 0.537 | 0.0 | 0.105 | 14.547 | 14.975 | 0.171 |

Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.

Top 12 at 1 minute by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | CVDP:PxDiv60=very low | up | 9.70 | 48.9 | 49.3 | +2.7 | +1.6 | +2.0 | 15.3 | 8.1 | +0.6 | +3.6 | -3.3 | none |
| BTC | CVDP:Div15=low (falling in) | up | 33.97 | 48.3 | 46.5 | -0.1 | +0.4 | +1.0 | 14.1 | 7.6 | +0.1 | +2.7 | -2.6 | none |
| BTC | LIQMAP:Skew=low (falling in) | up | 8.66 | 50.8 | 50.7 | +4.1 | +1.6 | +1.9 | 13.5 | 9.0 | +1.5 | +5.5 | -5.4 | none |
| BTC | CVDP:Div15=very high | down | 17.81 | 46.0 | 44.8 | -1.7 | +0.7 | +1.1 | 12.2 | 7.2 | -0.2 | +2.0 | -1.9 | none |
| BTC | CVDP:PxDiv60=low (falling in) | up | 25.57 | 48.9 | 47.2 | +0.6 | +0.4 | +0.9 | 11.2 | 7.6 | +0.1 | +2.7 | -2.8 | hot |
| BTC | LIQMAP:Skew=very low | up | 4.08 | 53.6 | 52.4 | +5.8 | +2.7 | +2.1 | 11.0 | 8.8 | +1.3 | +7.8 | -7.7 | hot, replicates |
| BTC | CVDP:PxDiv60=high (rising in) | down | 36.17 | 49.0 | 46.9 | +0.5 | +0.3 | +0.6 | 9.2 | 7.8 | +0.4 | +2.9 | -2.9 | none |
| BTC | CVDP:Div15=very low | up | 16.22 | 48.2 | 46.0 | -0.6 | +0.4 | +0.6 | 6.2 | 7.3 | -0.3 | +2.2 | -2.2 | hot |
| BTC | CVDP:PxDiv60=high (cooling) | down | 9.24 | 48.9 | 47.6 | +1.1 | +0.4 | +0.5 | 4.1 | 7.7 | +0.3 | +3.5 | -3.3 | none |
| BTC | CVDP:Div15=low (recovering) | down | 14.14 | 47.5 | 45.4 | -1.0 | +0.3 | +0.4 | 3.6 | 7.7 | +0.3 | +2.3 | -2.4 | none |
| BTC | CVDP:PxDiv60=low (recovering) | down | 4.08 | 49.7 | 48.0 | +1.6 | +0.7 | +0.5 | 2.7 | 7.9 | +0.4 | +3.4 | -3.5 | none |
| BTC | LIQMAP:Skew=very high | down | 2.62 | 53.0 | 50.4 | +3.9 | +0.9 | +0.6 | 2.5 | 9.3 | +1.8 | +6.0 | -6.2 | hot |

Top 8 at 1 minute by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.73 points, the 99th percentile 4.66):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=very low | up | 4.08 | 1,488 | 52.4 | +5.8 | +2.1 | 8.8 | +1.3 | -7.7 | hot, replicates |
| BTC | LIQMAP:Skew=low (falling in) | up | 8.66 | 3,160 | 50.7 | +4.1 | +1.9 | 9.0 | +1.5 | -5.4 | none |
| BTC | LIQMAP:Skew=very high | down | 2.62 | 957 | 50.4 | +3.9 | +0.6 | 9.3 | +1.8 | -6.2 | hot |
| BTC | CVDP:PxDiv60=very low | up | 9.70 | 3,540 | 49.3 | +2.7 | +2.0 | 8.1 | +0.6 | -3.3 | none |
| BTC | LIQMAP:Skew=high (cooling) | down | 2.59 | 944 | 48.9 | +2.5 | -0.3 | 8.6 | +1.1 | -5.6 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 9.09 | 3,316 | 48.6 | +2.1 | -0.3 | 8.5 | +1.0 | -4.6 | hot |
| BTC | CVDP:PxDiv60=low (recovering) | down | 4.08 | 1,489 | 48.0 | +1.6 | +0.5 | 7.9 | +0.4 | -3.5 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 4.04 | 1,473 | 47.8 | +1.2 | -1.6 | 8.6 | +1.1 | -7.2 | none |

Top 12 at 5 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | CVDP:Div15=low (falling in) | up | 31.73 | 50.5 | 50.3 | +0.8 | +0.8 | +1.8 | 24.7 | 7.6 | +0.1 | +7.3 | -3.3 | none |
| BTC | CVDP:PxDiv60=high (rising in) | down | 32.98 | 50.2 | 50.5 | +0.6 | +0.6 | +1.4 | 20.4 | 7.8 | +0.4 | +7.6 | -3.5 | none |
| BTC | LIQMAP:Skew=low (falling in) | up | 7.94 | 53.0 | 51.6 | +2.1 | +1.9 | +1.9 | 15.2 | 9.0 | +1.5 | +13.2 | -6.8 | hot |
| BTC | CVDP:PxDiv60=very low | down | 8.94 | 50.5 | 50.3 | +0.5 | +0.4 | +0.4 | 3.3 | 7.7 | +0.2 | +8.6 | -4.4 | none |
| BTC | LIQMAP:Skew=very low | up | 3.71 | 54.0 | 50.7 | +1.1 | +0.9 | +0.6 | 3.2 | 8.8 | +1.3 | +17.4 | -9.5 | hot |
| BTC | LIQMAP:Skew=very high | down | 2.38 | 52.7 | 51.3 | +1.4 | +1.2 | +0.7 | 3.0 | 9.3 | +1.8 | +14.8 | -7.6 | hot |
| BTC | LIQMAP:Skew=high (rising in) | down | 8.36 | 52.4 | 50.4 | +0.6 | +0.3 | +0.4 | 2.9 | 8.5 | +1.0 | +10.4 | -5.6 | hot |
| BTC | CVDP:PxDiv60=high (cooling) | up | 8.55 | 50.9 | 49.8 | +0.3 | +0.2 | +0.2 | 1.8 | 7.0 | -0.5 | +8.6 | -4.2 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 3.60 | 52.2 | 50.2 | +0.7 | +0.4 | +0.3 | 1.5 | 8.6 | +1.1 | +16.3 | -8.6 | hot |
| BTC | LIQMAP:Skew=high (cooling) | down | 2.36 | 52.2 | 50.3 | +0.4 | +0.2 | +0.1 | 0.5 | 8.6 | +1.1 | +13.3 | -6.8 | hot |
| BTC | CVDP:PxDiv60=low (recovering) | down | 3.90 | 52.2 | 50.0 | +0.2 | +0.1 | +0.1 | 0.3 | 7.9 | +0.4 | +8.8 | -4.2 | hot |
| BTC | CVDP:Div15=low (recovering) | up | 13.27 | 50.4 | 49.2 | -0.3 | -0.1 | -0.2 | -1.7 | 7.1 | -0.5 | +6.6 | -2.9 | none |

Top 8 at 5 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 2.51 points, the 99th percentile 2.49):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=low (falling in) | up | 7.94 | 3,160 | 51.6 | +2.1 | +1.9 | 9.0 | +1.5 | -6.8 | hot |
| BTC | LIQMAP:Skew=very high | down | 2.38 | 957 | 51.3 | +1.4 | +0.7 | 9.3 | +1.8 | -7.6 | hot |
| BTC | LIQMAP:Skew=very low | up | 3.71 | 1,488 | 50.7 | +1.1 | +0.6 | 8.8 | +1.3 | -9.5 | hot |
| BTC | CVDP:Div15=low (falling in) | up | 31.73 | 12,399 | 50.3 | +0.8 | +1.8 | 7.6 | +0.1 | -3.3 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 3.60 | 1,473 | 50.2 | +0.7 | +0.3 | 8.6 | +1.1 | -8.6 | hot |
| BTC | CVDP:PxDiv60=high (rising in) | down | 32.98 | 13,202 | 50.5 | +0.6 | +1.4 | 7.8 | +0.4 | -3.5 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 8.36 | 3,316 | 50.4 | +0.6 | +0.4 | 8.5 | +1.0 | -5.6 | hot |
| BTC | CVDP:PxDiv60=very low | down | 8.94 | 3,540 | 50.3 | +0.5 | +0.4 | 7.7 | +0.2 | -4.4 | none |

Top 12 at 15 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=high (rising in) | down | 6.49 | 53.4 | 52.2 | +2.1 | +2.1 | +1.9 | 13.6 | 8.5 | +1.0 | +18.4 | -8.2 | hot |
| BTC | LIQMAP:Skew=low (falling in) | up | 6.19 | 54.7 | 52.0 | +2.2 | +2.2 | +1.8 | 13.5 | 9.0 | +1.5 | +23.0 | -10.0 | hot |
| BTC | CVDP:PxDiv60=very low | down | 7.01 | 50.4 | 51.9 | +1.9 | +1.9 | +2.0 | 13.2 | 7.7 | +0.2 | +16.3 | -6.6 | none |
| BTC | CVDP:PxDiv60=low (recovering) | down | 3.48 | 52.7 | 53.4 | +3.3 | +3.3 | +2.3 | 11.4 | 7.9 | +0.4 | +16.9 | -6.7 | hot, replicates |
| BTC | LIQMAP:Skew=very low | up | 2.82 | 55.4 | 53.6 | +3.7 | +3.7 | +2.3 | 10.3 | 8.8 | +1.3 | +29.8 | -13.8 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.85 | 53.9 | 53.1 | +3.0 | +3.0 | +1.5 | 5.6 | 9.3 | +1.8 | +24.7 | -10.8 | hot |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.78 | 53.3 | 52.2 | +2.2 | +2.1 | +1.1 | 3.8 | 8.6 | +1.1 | +23.3 | -10.0 | hot |
| BTC | CVDP:PxDiv60=high (cooling) | up | 6.56 | 51.2 | 50.0 | +0.2 | +0.2 | +0.2 | 1.1 | 7.0 | -0.5 | +16.1 | -6.3 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 2.79 | 53.7 | 50.3 | +0.5 | +0.4 | +0.2 | 1.1 | 8.6 | +1.1 | +27.8 | -12.4 | hot |
| BTC | CVDP:PxDiv60=very high | up | 6.53 | 51.5 | 50.0 | +0.1 | +0.1 | +0.1 | 0.8 | 7.5 | +0.0 | +16.2 | -6.5 | none |
| BTC | CVDP:PxDiv60=high (rising in) | down | 25.04 | 50.6 | 49.8 | -0.3 | -0.3 | -0.6 | -7.0 | 7.8 | +0.4 | +14.1 | -5.3 | hot |
| BTC | CVDP:Div15=high (cooling) | down | 12.64 | 49.6 | 48.7 | -1.4 | -1.3 | -1.8 | -17.0 | 7.1 | -0.3 | +10.6 | -4.0 | none |

Top 8 at 15 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 3.42 points, the 99th percentile 3.29):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=very low | up | 2.82 | 1,488 | 53.6 | +3.7 | +2.3 | 8.8 | +1.3 | -13.8 | hot, replicates |
| BTC | CVDP:PxDiv60=low (recovering) | down | 3.48 | 1,489 | 53.4 | +3.3 | +2.3 | 7.9 | +0.4 | -6.7 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.85 | 957 | 53.1 | +3.0 | +1.5 | 9.3 | +1.8 | -10.8 | hot |
| BTC | LIQMAP:Skew=low (falling in) | up | 6.19 | 3,160 | 52.0 | +2.2 | +1.8 | 9.0 | +1.5 | -10.0 | hot |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.78 | 944 | 52.2 | +2.2 | +1.1 | 8.6 | +1.1 | -10.0 | hot |
| BTC | LIQMAP:Skew=high (rising in) | down | 6.49 | 3,316 | 52.2 | +2.1 | +1.9 | 8.5 | +1.0 | -8.2 | hot |
| BTC | CVDP:PxDiv60=very low | down | 7.01 | 3,540 | 51.9 | +1.9 | +2.0 | 7.7 | +0.2 | -6.6 | none |
| BTC | LIQMAP:Skew=low (recovering) | up | 2.79 | 1,473 | 50.3 | +0.5 | +0.2 | 8.6 | +1.1 | -12.4 | hot |

Top 12 at 30 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=high (rising in) | down | 5.14 | 54.3 | 53.9 | +4.1 | +4.1 | +3.2 | 20.8 | 8.5 | +1.0 | +26.8 | -11.5 | hot, replicates |
| BTC | LIQMAP:Skew=very low | up | 2.21 | 56.4 | 55.2 | +5.1 | +5.1 | +2.8 | 11.2 | 8.8 | +1.3 | +40.2 | -18.3 | hot, replicates |
| BTC | CVDP:PxDiv60=high (rising in) | down | 19.26 | 50.7 | 50.3 | +0.6 | +0.6 | +1.1 | 10.7 | 7.8 | +0.4 | +20.8 | -7.6 | hot |
| BTC | CVDP:PxDiv60=very low | down | 5.75 | 50.8 | 51.2 | +1.4 | +1.4 | +1.3 | 8.2 | 7.7 | +0.2 | +23.9 | -9.1 | none |
| BTC | CVDP:PxDiv60=low (falling in) | down | 14.60 | 50.1 | 50.3 | +0.6 | +0.6 | +0.8 | 8.1 | 7.6 | +0.2 | +20.1 | -7.4 | none |
| BTC | LIQMAP:Skew=low (falling in) | up | 4.86 | 55.5 | 51.8 | +1.7 | +1.6 | +1.2 | 8.0 | 9.0 | +1.5 | +31.7 | -14.1 | hot |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.41 | 52.8 | 55.0 | +5.2 | +5.2 | +1.9 | 7.3 | 8.6 | +1.1 | +32.8 | -13.3 | hot |
| BTC | LIQMAP:Skew=low (recovering) | up | 2.20 | 54.5 | 53.4 | +3.2 | +3.2 | +1.8 | 7.1 | 8.6 | +1.1 | +37.8 | -16.6 | hot |
| BTC | LIQMAP:Skew=very high | down | 1.47 | 54.3 | 53.8 | +4.0 | +4.0 | +1.5 | 5.9 | 9.3 | +1.8 | +34.4 | -13.9 | hot |
| BTC | CVDP:PxDiv60=low (recovering) | down | 3.16 | 52.9 | 50.6 | +0.9 | +0.9 | +0.6 | 2.7 | 7.9 | +0.4 | +24.7 | -9.0 | hot |
| BTC | CVDP:PxDiv60=very high | up | 5.30 | 51.2 | 50.3 | +0.2 | +0.2 | +0.2 | 1.1 | 7.5 | +0.0 | +23.2 | -9.2 | none |
| BTC | CVDP:PxDiv60=high (cooling) | up | 5.35 | 51.3 | 49.3 | -0.9 | -0.9 | -0.8 | -4.7 | 7.0 | -0.5 | +23.0 | -9.1 | none |

Top 8 at 30 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 3.96 points, the 99th percentile 3.17):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=high (cooling) | down | 1.41 | 944 | 55.0 | +5.2 | +1.9 | 8.6 | +1.1 | -13.3 | hot |
| BTC | LIQMAP:Skew=very low | up | 2.21 | 1,488 | 55.2 | +5.1 | +2.8 | 8.8 | +1.3 | -18.3 | hot, replicates |
| BTC | LIQMAP:Skew=high (rising in) | down | 5.14 | 3,316 | 53.9 | +4.1 | +3.2 | 8.5 | +1.0 | -11.5 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.47 | 957 | 53.8 | +4.0 | +1.5 | 9.3 | +1.8 | -13.9 | hot |
| BTC | LIQMAP:Skew=low (recovering) | up | 2.20 | 1,473 | 53.4 | +3.2 | +1.8 | 8.6 | +1.1 | -16.6 | hot |
| BTC | LIQMAP:Skew=low (falling in) | up | 4.86 | 3,160 | 51.8 | +1.7 | +1.2 | 9.0 | +1.5 | -14.1 | hot |
| BTC | CVDP:PxDiv60=very low | down | 5.75 | 3,540 | 51.2 | +1.4 | +1.3 | 7.7 | +0.2 | -9.1 | none |
| BTC | CVDP:PxDiv60=low (recovering) | down | 3.16 | 1,489 | 50.6 | +0.9 | +0.6 | 7.9 | +0.4 | -9.0 | hot |

Top 12 at 60 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | CVDP:Div15=very low | down | 9.32 | 49.6 | 51.8 | +2.4 | +2.4 | +2.9 | 22.1 | 7.4 | -0.0 | +26.5 | -9.2 | none |
| BTC | CVDP:Div15=low (recovering) | down | 8.39 | 50.2 | 51.8 | +2.3 | +2.3 | +2.6 | 19.6 | 7.7 | +0.3 | +27.2 | -9.5 | none |
| BTC | CVDP:Div15=low (falling in) | down | 16.05 | 49.2 | 50.6 | +1.1 | +1.1 | +2.1 | 18.0 | 7.5 | +0.0 | +28.8 | -10.3 | none |
| BTC | LIQMAP:Skew=high (rising in) | down | 3.91 | 54.2 | 52.5 | +3.1 | +3.1 | +2.2 | 11.9 | 8.5 | +1.0 | +37.6 | -15.6 | hot, replicates |
| BTC | LIQMAP:Skew=very low | up | 1.71 | 57.1 | 56.5 | +6.0 | +6.0 | +2.5 | 10.3 | 8.8 | +1.3 | +54.8 | -23.7 | hot, replicates |
| BTC | CVDP:Div15=high (cooling) | up | 9.01 | 51.7 | 51.4 | +0.9 | +0.9 | +1.0 | 7.9 | 7.5 | -0.0 | +23.5 | -8.8 | none |
| BTC | CVDP:Div15=very high | up | 9.69 | 51.3 | 51.3 | +0.8 | +0.8 | +1.0 | 7.3 | 7.4 | -0.1 | +23.1 | -8.6 | none |
| BTC | LIQMAP:Skew=high (cooling) | down | 1.12 | 52.3 | 55.8 | +6.4 | +6.4 | +2.3 | 7.1 | 8.6 | +1.1 | +44.4 | -17.1 | hot, replicates |
| BTC | LIQMAP:Skew=low (recovering) | up | 1.71 | 55.8 | 54.7 | +4.1 | +4.1 | +1.9 | 7.0 | 8.6 | +1.1 | +52.0 | -22.9 | hot |
| BTC | LIQMAP:Skew=very high | down | 1.15 | 53.4 | 55.6 | +6.1 | +6.1 | +2.2 | 7.0 | 9.3 | +1.8 | +46.1 | -17.6 | hot |
| BTC | CVDP:PxDiv60=low (recovering) | down | 2.87 | 52.3 | 50.8 | +1.4 | +1.4 | +0.8 | 3.9 | 7.9 | +0.4 | +35.5 | -12.5 | hot |
| BTC | LIQMAP:Skew=low (falling in) | up | 3.67 | 56.1 | 51.3 | +0.8 | +0.8 | +0.6 | 2.9 | 9.0 | +1.5 | +43.1 | -19.5 | hot |

Top 8 at 60 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 4.88 points, the 99th percentile 3.85):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | LIQMAP:Skew=high (cooling) | down | 1.12 | 944 | 55.8 | +6.4 | +2.3 | 8.6 | +1.1 | -17.1 | hot, replicates |
| BTC | LIQMAP:Skew=very high | down | 1.15 | 957 | 55.6 | +6.1 | +2.2 | 9.3 | +1.8 | -17.6 | hot |
| BTC | LIQMAP:Skew=very low | up | 1.71 | 1,488 | 56.5 | +6.0 | +2.5 | 8.8 | +1.3 | -23.7 | hot, replicates |
| BTC | LIQMAP:Skew=low (recovering) | up | 1.71 | 1,473 | 54.7 | +4.1 | +1.9 | 8.6 | +1.1 | -22.9 | hot |
| BTC | LIQMAP:Skew=high (rising in) | down | 3.91 | 3,316 | 52.5 | +3.1 | +2.2 | 8.5 | +1.0 | -15.6 | hot, replicates |
| BTC | CVDP:Div15=very low | down | 9.32 | 5,919 | 51.8 | +2.4 | +2.9 | 7.4 | -0.0 | -9.2 | none |
| BTC | CVDP:Div15=low (recovering) | down | 8.39 | 5,162 | 51.8 | +2.3 | +2.6 | 7.7 | +0.3 | -9.5 | none |
| BTC | CVDP:PxDiv60=low (recovering) | down | 2.87 | 1,489 | 50.8 | +1.4 | +0.8 | 7.9 | +0.4 | -12.5 | hot |

## Every TA by heat

Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the direction the reading's current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). The horizon is the one with the most heat on A; the B columns score A's directions on B, so a reading with no information scores about zero.

| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |
|---|---|---|---|---|---|---|---|---|
| real | events | 3 | 0.6667 | 0.3333 | 0.3333 | 11.703 | 53.03 | 57.622 |
| twin | events | 9 | 0.5556 | 0.0 | 0.0 | 4.319 | 23.795 | 24.293 |

Top 3 readings by events heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| BTC | CVDP:Div15 | 60 | 20.7 | +57.6 | +3.5 |
| BTC | CVDP:PxDiv60 | 15 | 19.7 | +11.7 | +1.0 |
| BTC | LIQMAP:Skew | 60 | 23.0 | -10.3 | -0.7 |

## Top 0 replicating by heat on B (windows per day x move, bps per day)

0 of 0 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Top 0 replicating by move per event on B (bps; at least 0.2 windows per day)

0 of 0 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Top 5 replicating by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)

1 of 5 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | triple | CVDP:Div15=low (falling in) / CVDP:PxDiv60=high / LIQMAP:Skew=very low | 5 | up | yes | 0.39 | +2.6 | +10.6 | 60.4 | +10.9 | 11.4 | -6.2 | +2.7 | 4.1 | +1.5 |  | +9.8 | +9.1 | 0.050 |
| BTC | single | LIQMAP:Skew=high (cooling) | 60 | down | no | 1.12 | +1.5 | +6.4 | 55.8 | +6.4 | 8.6 | -17.1 | +2.3 | 7.1 | +1.6 | +1.4 |  |  | 0.421 |
| BTC | single | LIQMAP:Skew=very low | 1/15/30/60 | up | no | 1.71 | +0.9 | +6.0 | 56.5 | +6.0 | 8.8 | -23.7 | +2.5 | 10.3 | +0.9 | -0.3 |  |  | 0.421 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | no | 5.14 | +0.7 | +4.1 | 53.9 | +4.1 | 8.5 | -11.5 | +3.2 | 20.8 | +0.9 | +0.4 |  |  | 0.147 |
| BTC | single | CVDP:PxDiv60=low (recovering) | 15 | down | no | 3.48 | +0.8 | +3.3 | 53.4 | +3.3 | 7.9 | -6.7 | +2.3 | 11.4 | +0.9 | +0.2 |  |  | 0.421 |

## Top 5 replicating by odds heat on B (windows per day x odds points)

1 of 5 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | triple | CVDP:Div15=low (falling in) / CVDP:PxDiv60=high / LIQMAP:Skew=very low | 5 | up | yes | 0.39 | +2.6 | +10.6 | 60.4 | +10.9 | 11.4 | -6.2 | +2.7 | 4.1 | +1.5 |  | +9.8 | +9.1 | 0.050 |
| BTC | single | LIQMAP:Skew=high (rising in) | 30/60 | down | no | 5.14 | +0.7 | +4.1 | 53.9 | +4.1 | 8.5 | -11.5 | +3.2 | 20.8 | +0.9 | +0.4 |  |  | 0.147 |
| BTC | single | CVDP:PxDiv60=low (recovering) | 15 | down | no | 3.48 | +0.8 | +3.3 | 53.4 | +3.3 | 7.9 | -6.7 | +2.3 | 11.4 | +0.9 | +0.2 |  |  | 0.421 |
| BTC | single | LIQMAP:Skew=very low | 1/15/30/60 | up | no | 2.21 | +0.6 | +5.1 | 55.2 | +5.1 | 8.8 | -18.3 | +2.8 | 11.2 | +0.6 | -0.0 |  |  | 0.352 |
| BTC | single | LIQMAP:Skew=high (cooling) | 60 | down | no | 1.12 | +1.5 | +6.4 | 55.8 | +6.4 | 8.6 | -17.1 | +2.3 | 7.1 | +1.6 | +1.4 |  |  | 0.421 |

## Tables

One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.

| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 77a0d06cb1608891e5c5d9763a1ed8f96888e013ab98d012602bde5a5cb59f95 |
| BTC~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | 01a0eb112c4ed97ca4b96a396d6cdb79baf7e2290b3cd9bfce8427dd19e29601 |
| BTC~twin2 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | ea345a400af4c27f1c5729f6c008a0aaaee12f4cf198dbc0b15ffd81b1a43d88 |
| BTC~twin3 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | bfec835800710608d950e98dea495c08c2f55af04a88da7ac6f5d6cbe94803df |
