# OR-HM1 heat map: league (coin price, discovery only)

Coins: BTC, ETH, SOL, XRP. No-signal twins: BTC~twin1, ETH~twin1, SOL~twin1, XRP~twin1.
Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute's open. A map, not a validated rule.

## Hot spots against chance

Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent's other events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest set, a higher replicate share and the BHY column are evidence.

| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |
|---|---|---|---|---|---|---|---|---|---|---|
| real | single | 39,450 | 709 | 26 | 0.0367 | 0 | 8,949 | 2,136 | 0.2387 | 81 |
| real | curve | 78,366 | 1,003 | 65 | 0.0648 |  | 18,512 | 3,541 | 0.1913 |  |
| real | pair | 4,722,274 | 29,488 | 172 | 0.0058 | 0 | 221,820 | 5,310 | 0.0239 | 0 |
| real | triple | 1,126,476 | 15,687 | 86 | 0.0055 | 0 | 82,478 | 3,209 | 0.0389 | 0 |
| twin | single | 39,400 | 27 | 1 | 0.037 | 0 | 43 | 1 | 0.0233 | 0 |
| twin | curve | 78,234 | 104 | 0 | 0.0 |  | 133 | 4 | 0.0301 |  |
| twin | pair | 4,611,836 | 6,675 | 23 | 0.0034 | 0 | 13,977 | 75 | 0.0054 | 0 |
| twin | triple | 263,590 | 1,249 | 1 | 0.0008 | 0 | 3,115 | 4 | 0.0013 | 0 |

Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): move_heat 46.379, move_edge 83.456, odds_edge 15.111, odds_heat 12.875.

## Direction: every event level, nothing cut (Amendment 3)

The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods (30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.

| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |
|---|---|---|---|---|---|---|---|---|
| 240 | real | 19,055 | 0.6963 | 0.1319 | 0.74 | 12.577 | 18.325 | 7.87 |
| 240 | twin | 19,033 | 0.5114 | 0.0201 | 0.026 | 7.488 | 12.643 | 2.264 |
| 1440 | real | 19,055 | 0.6652 | 0.0846 | 0.598 | 4.086 | 6.947 | 7.374 |
| 1440 | twin | 19,033 | 0.5095 | 0.0277 | 0.026 | 3.264 | 9.344 | 2.208 |

Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.

Top 12 at 240 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | 1m:C-MIDPRICE14=very low | up | 5.21 | 52.4 | 53.2 | +3.5 | +3.5 | +4.8 | 18.3 | 51.1 | +14.3 | +115.9 | -47.5 | hot, replicates, BHY |
| BTC | 1m:MFI14=very low | up | 5.18 | 55.2 | 54.4 | +3.5 | +3.5 | +4.4 | 18.0 | 49.5 | +9.1 | +61.9 | -25.3 | hot, replicates, BHY |
| XRP | 1m:C-CKSPmid=very low | up | 5.03 | 52.8 | 53.1 | +3.5 | +3.5 | +4.4 | 17.6 | 47.9 | +11.1 | +117.3 | -48.2 | hot, replicates, BHY |
| BTC | 5m:WAD=low (falling in) | up | 4.09 | 54.4 | 55.2 | +4.3 | +4.3 | +4.3 | 17.4 | 53.3 | +12.9 | +71.5 | -28.6 | hot, replicates, BHY |
| XRP | 1m:CG10=low (falling in) | up | 5.10 | 52.4 | 53.1 | +3.5 | +3.4 | +4.7 | 17.3 | 49.2 | +12.4 | +157.9 | -65.7 | hot, replicates, BHY |
| BTC | 15m:C-T3_5=low (falling in) | up | 3.71 | 56.0 | 55.6 | +4.6 | +4.6 | +4.3 | 17.0 | 61.9 | +21.5 | +64.9 | -26.7 | hot, replicates, BHY |
| XRP | 1m:C-EMA9=very low | up | 5.38 | 52.5 | 52.8 | +3.2 | +3.1 | +4.7 | 16.8 | 58.9 | +22.1 | +116.5 | -48.2 | hot, replicates, BHY |
| XRP | 1m:C-KAMA30=very low | up | 4.87 | 53.1 | 53.1 | +3.4 | +3.4 | +4.1 | 16.7 | 51.8 | +14.9 | +117.4 | -47.4 | hot, replicates, BHY |
| ETH | 1m:C-MCGD14=very high | down | 3.95 | 51.7 | 53.0 | +4.2 | +4.2 | +3.7 | 16.6 | 68.7 | +28.8 | +102.3 | -39.6 | hot, replicates |
| XRP | 5m:MDI14=high (rising in) | up | 3.14 | 54.9 | 54.9 | +5.2 | +5.2 | +4.4 | 16.5 | 51.4 | +14.6 | +128.0 | -50.5 | hot, replicates, BHY |
| BTC | 1m:MFI14=low (recovering) | up | 5.06 | 54.7 | 54.2 | +3.2 | +3.2 | +3.9 | 16.4 | 43.8 | +3.4 | +62.7 | -26.1 | hot, replicates, BHY |
| XRP | 1m:MDI14=very high | up | 4.08 | 54.4 | 53.7 | +4.0 | +4.0 | +4.3 | 16.3 | 50.1 | +13.3 | +109.4 | -43.5 | hot, replicates, BHY |

Top 8 at 240 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 19.91 points, the 99th percentile 7.19):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ETH | 60m:STOCHK14=very high | down | 0.27 | 100 | 66.0 | +17.2 | +3.6 | 100.0 | +60.1 | -45.3 | none |
| BTC | 60m:ER10=very high | down | 0.22 | 83 | 65.1 | +16.0 | +3.0 | 56.7 | +18.1 | -30.4 | none |
| BTC | 60m:C-MIDPRICE14=very high | down | 0.21 | 83 | 63.9 | +14.8 | +2.6 | 93.7 | +55.0 | -27.1 | none |
| BTC | 60m:WILLR14=high (cooling) | down | 0.32 | 125 | 63.2 | +14.2 | +3.2 | 39.9 | +1.3 | -23.1 | none |
| BTC | 5m:ADXR14=very high | down | 0.23 | 84 | 63.1 | +14.1 | +2.5 | 118.7 | +80.1 | -31.8 | none |
| XRP | 60m:C-ALMA9=low (recovering) | up | 0.22 | 81 | 63.0 | +13.3 | +2.5 | 72.6 | +35.8 | -61.4 | none |
| SOL | 60m:MARKETFI=very high | up | 0.23 | 92 | 63.0 | +12.8 | +2.4 | 27.7 | -9.4 | -40.5 | none |
| XRP | 60m:C-FRAMA16=very low | up | 0.38 | 143 | 62.2 | +12.6 | +3.0 | 105.2 | +68.4 | -67.8 | hot, replicates |

Top 12 at 1440 minutes by heat on B:

| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 15m:ASI=high (rising in) | down | 0.84 | 49.4 | 56.7 | +8.3 | +8.3 | +4.1 | 6.9 | 60.7 | +22.1 | +182.9 | -67.3 | none |
| ETH | 5m:CCI50=low (recovering) | up | 0.80 | 54.0 | 58.7 | +7.9 | +7.9 | +3.6 | 6.3 | 55.8 | +13.5 | +301.0 | -119.3 | none |
| ETH | 5m:CCI50=very low | up | 0.80 | 53.7 | 58.4 | +7.6 | +7.6 | +3.5 | 6.1 | 95.6 | +53.3 | +299.4 | -126.7 | none |
| ETH | 15m:CCI14=low (recovering) | up | 0.65 | 55.7 | 60.0 | +9.2 | +9.2 | +3.7 | 6.0 | 48.9 | +6.6 | +316.6 | -132.1 | none |
| BTC | 5m:C-EMA21=low (recovering) | up | 0.89 | 56.6 | 58.3 | +6.8 | +6.8 | +3.7 | 6.0 | 56.0 | +15.6 | +169.3 | -69.3 | hot, replicates |
| BTC | 5m:ERIbull13=low (recovering) | up | 0.95 | 56.0 | 57.8 | +6.3 | +6.3 | +3.9 | 6.0 | 51.7 | +11.3 | +161.9 | -68.4 | hot, replicates, BHY |
| XRP | 1m:CG10=low (recovering) | up | 0.65 | 53.2 | 57.4 | +9.1 | +9.0 | +3.3 | 5.9 | 55.4 | +18.6 | +506.6 | -260.2 | none |
| XRP | 1m:CG10=very low | up | 0.65 | 53.5 | 57.3 | +9.0 | +9.0 | +3.3 | 5.9 | 78.1 | +41.2 | +523.5 | -270.9 | none |
| SOL | 5m:WILLR14=low (recovering) | up | 0.88 | 51.7 | 55.3 | +6.5 | +6.7 | +3.3 | 5.8 | 47.0 | +9.8 | +357.5 | -125.8 | none |
| ETH | 15m:OBV=high (rising in) | down | 0.77 | 48.9 | 56.7 | +7.5 | +7.5 | +3.5 | 5.8 | 50.0 | +10.1 | +297.2 | -108.4 | none |
| BTC | 15m:EFI13=low (falling in) | up | 0.61 | 54.9 | 61.0 | +9.4 | +9.4 | +3.6 | 5.7 | 44.2 | +3.8 | +195.0 | -79.0 | none |
| BTC | 1m:CDL:MORNINGDOJISTAR=bull | up | 0.61 | 54.2 | 60.8 | +9.2 | +9.2 | +3.4 | 5.6 | 54.1 | +13.7 | +178.8 | -65.1 | none |

Top 8 at 1440 minutes by share right over base on B (at least 0.2 windows per day; the best twin level reaches 17.49 points, the 99th percentile 7.41):

| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 15m:CRSI=high (cooling) | down | 0.24 | 98 | 67.3 | +18.9 | +3.6 | 107.6 | +68.9 | -61.3 | none |
| BTC | 60m:AROONOSC14=high (cooling) | up | 0.26 | 137 | 67.2 | +15.6 | +3.5 | 69.4 | +29.0 | -64.9 | none |
| ETH | 60m:PERCENTRANK100=low (falling in) | up | 0.27 | 157 | 66.2 | +15.5 | +3.3 | 45.6 | +3.3 | -146.8 | none |
| XRP | 60m:PVT=low (falling in) | up | 0.24 | 125 | 62.4 | +14.1 | +3.0 | 62.5 | +25.6 | -156.7 | hot, replicates |
| ETH | 15m:BBW20=low (recovering) | up | 0.29 | 161 | 64.6 | +13.8 | +3.5 | 28.9 | -13.4 | -82.2 | none |
| SOL | 60m:CORRELcv30=high (rising in) | up | 0.23 | 104 | 62.5 | +13.7 | +2.7 | 65.9 | +28.7 | -123.2 | none |
| ETH | 15m:STDDEV20=low (recovering) | up | 0.30 | 166 | 64.5 | +13.7 | +3.5 | 27.5 | -14.8 | -85.4 | none |
| ETH | 15m:C-MIDPOINT14=high (cooling) | down | 0.32 | 193 | 62.7 | +13.5 | +2.8 | 37.1 | -2.8 | -92.6 | none |

## Every TA by heat

Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the direction the reading's current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). The horizon is the one with the most heat on A; the B columns score A's directions on B, so a reading with no information scores about zero.

| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |
|---|---|---|---|---|---|---|---|---|
| real | curve | 2,496 | 0.5581 | 0.1458 | 0.0613 | 0.581 | 13.919 | 50.342 |
| twin | curve | 2,496 | 0.4708 | 0.0361 | 0.0036 | -0.274 | 12.073 | 46.207 |
| real | events | 3,352 | 0.5674 | 0.1002 | 0.0263 | 2.656 | 74.601 | 298.89 |
| twin | events | 3,365 | 0.5037 | 0.0386 | 0.0071 | 0.183 | 45.901 | 235.692 |

Top 40 readings by curve heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| XRP | 60m:MACD12/26 | 240 | 21.5 | +50.3 | +3.6 |
| XRP | 60m:APO12/26 | 240 | 21.5 | +50.3 | +3.6 |
| XRP | 15m:C-EMA200 | 240 | 20.7 | +43.0 | +4.5 |
| XRP | 60m:SQZMOM | 240 | 47.4 | +42.6 | +3.0 |
| XRP | 60m:CMOU14 | 240 | 31.1 | +41.2 | +3.2 |
| XRP | 60m:FISHER10 | 240 | 32.7 | +41.1 | +3.0 |
| XRP | 60m:PPO12/26 | 240 | 27.2 | +40.7 | +2.6 |
| XRP | 60m:C-MIDPOINT14 | 240 | 15.3 | +40.6 | +3.7 |
| XRP | 60m:WT1 | 240 | 34.7 | +39.8 | +2.7 |
| XRP | 60m:IMI14 | 240 | 31.4 | +38.6 | +3.1 |
| XRP | 60m:C-CKSPmid | 240 | 30.1 | +37.8 | +3.0 |
| XRP | 60m:C-SMA20 | 240 | 32.5 | +34.5 | +2.7 |
| XRP | 60m:KVO | 240 | 31.0 | +34.4 | +2.5 |
| XRP | 60m:MFI14 | 240 | 33.0 | +34.1 | +2.5 |
| XRP | 60m:KURTOSIS30 | 240 | 30.1 | +33.8 | +2.7 |
| XRP | 60m:COPPOCK | 240 | 36.4 | +33.8 | +2.5 |
| ETH | 15m:C-SMA50 | 240 | 14.8 | +32.9 | +3.6 |
| XRP | 15m:ADX14 | 240 | 21.8 | +32.3 | +3.2 |
| XRP | 60m:VHF28 | 240 | 30.3 | +31.7 | +2.2 |
| XRP | 15m:TRIX30 | 240 | 35.8 | +29.9 | +2.1 |
| XRP | 60m:TSI | 240 | 21.7 | +29.4 | +2.1 |
| XRP | 60m:CTI20 | 240 | 39.3 | +29.3 | +2.0 |
| XRP | 15m:ADXR14 | 240 | 33.7 | +28.8 | +2.2 |
| XRP | 60m:AROONdn14 | 240 | 29.0 | +28.7 | +2.6 |
| XRP | 60m:DONCHIAN20pos | 240 | 38.2 | +28.5 | +2.3 |
| ETH | 15m:MACD5/35 | 240 | 14.7 | +28.4 | +2.7 |
| XRP | 60m:WILLR14 | 240 | 21.8 | +28.1 | +2.7 |
| XRP | 60m:IBS | 240 | 25.7 | +27.0 | +2.8 |
| ETH | 60m:CG10 | 240 | 24.2 | +26.9 | +2.2 |
| XRP | 60m:VORTEXdiff14 | 240 | 32.0 | +26.7 | +2.3 |
| XRP | 60m:MARKETFI | 240 | 19.6 | +26.5 | +3.0 |
| XRP | 60m:C-SAR | 240 | 21.0 | +26.3 | +2.2 |
| XRP | 60m:STOCHK14 | 240 | 25.0 | +26.2 | +2.2 |
| ETH | 15m:KST | 240 | 17.5 | +26.0 | +2.4 |
| XRP | 15m:MACD12/26 | 240 | 19.4 | +25.6 | +2.4 |
| XRP | 15m:APO12/26 | 240 | 19.4 | +25.6 | +2.4 |
| XRP | 60m:C-VWMA20 | 240 | 35.5 | +25.4 | +2.1 |
| XRP | 15m:PPO12/26 | 240 | 17.6 | +25.3 | +2.5 |
| XRP | 60m:C-TRIMA20 | 240 | 25.4 | +25.0 | +2.0 |
| ETH | 60m:MOM10 | 240 | 28.6 | +25.0 | +2.1 |

Top 40 readings by events heat on B:

| coin | reading | minutes | heat A | heat B | t B |
|---|---|---|---|---|---|
| XRP | 1m:CG10 | 1440 | 248.9 | +298.9 | +5.1 |
| XRP | 5m:CG10 | 1440 | 157.8 | +164.9 | +3.8 |
| XRP | 5m:OBV | 1440 | 81.0 | +158.4 | +4.2 |
| ETH | 1m:CG10 | 1440 | 100.8 | +147.9 | +4.0 |
| XRP | 60m:CMO14 | 1440 | 59.7 | +142.6 | +4.3 |
| XRP | 1m:RVIR14 | 240 | 91.1 | +132.9 | +4.2 |
| SOL | 1m:KVO | 240 | 167.9 | +132.4 | +3.0 |
| XRP | 1m:STOCHK14 | 240 | 82.7 | +132.2 | +4.5 |
| XRP | 1m:AROONOSC25 | 240 | 133.0 | +131.4 | +4.1 |
| SOL | 1m:COPPOCK | 240 | 106.4 | +131.3 | +4.0 |
| SOL | 1m:C-SMA50 | 240 | 112.4 | +130.4 | +3.4 |
| SOL | 5m:DPO20 | 240 | 108.0 | +128.4 | +3.9 |
| XRP | 15m:C-KAMA30 | 1440 | 68.8 | +128.3 | +3.2 |
| XRP | 1m:PSO | 240 | 57.3 | +127.2 | +4.4 |
| SOL | 1m:MACD5/35 | 240 | 109.5 | +127.0 | +3.7 |
| XRP | 1m:RSI21 | 240 | 122.6 | +126.6 | +3.6 |
| XRP | 15m:WT1 | 1440 | 74.1 | +125.2 | +3.6 |
| SOL | 1m:VORTEXdiff14 | 240 | 65.9 | +123.4 | +3.9 |
| XRP | 60m:C-VIDYA12 | 1440 | 62.2 | +121.0 | +3.9 |
| XRP | 1m:C-EMA50 | 240 | 123.8 | +120.8 | +3.5 |
| XRP | 60m:MARKETFI | 1440 | 51.6 | +120.1 | +3.4 |
| XRP | 60m:VORTEXdiff14 | 1440 | 78.0 | +119.7 | +3.7 |
| SOL | 1m:TSI | 240 | 149.1 | +119.6 | +3.3 |
| XRP | 15m:C-SMA50 | 1440 | 97.1 | +118.8 | +3.1 |
| XRP | 60m:CMOU14 | 1440 | 65.3 | +118.8 | +3.4 |
| SOL | 1m:C-HT_TRENDLINE | 240 | 105.2 | +117.6 | +3.3 |
| XRP | 15m:CG10 | 1440 | 116.9 | +116.8 | +3.2 |
| XRP | 5m:C-TRIMA20 | 240 | 90.6 | +116.7 | +3.7 |
| SOL | 1m:KST | 240 | 135.3 | +116.6 | +3.5 |
| XRP | 1m:FISHER10 | 240 | 55.0 | +116.5 | +5.1 |
| XRP | 1m:AROONOSC14 | 240 | 92.7 | +112.2 | +4.2 |
| XRP | 5m:PVT | 1440 | 81.6 | +111.3 | +3.0 |
| XRP | 5m:STOCHK14 | 240 | 98.0 | +110.9 | +3.3 |
| XRP | 1m:CMO14 | 240 | 102.5 | +109.9 | +3.2 |
| XRP | 1m:RSI14 | 240 | 102.5 | +109.9 | +3.2 |
| XRP | 60m:C-RMA14 | 1440 | 65.6 | +109.8 | +3.2 |
| XRP | 1m:EFI13 | 240 | 189.8 | +109.7 | +2.5 |
| XRP | 15m:KVO | 1440 | 96.8 | +109.2 | +2.8 |
| XRP | 5m:C-DEMA21 | 240 | 90.6 | +108.9 | +3.8 |
| SOL | 1m:CG10 | 1440 | 374.2 | +108.5 | +1.6 |

## Top 40 replicating by heat on B (windows per day x move, bps per day)

0 of 284 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | triple | 1m:PERCENTRANK100=low (recovering) / 5m:CORRELcv30 sign=below 0 / 60m:HT_TRENDMODE=trend | 240 | up | no | 2.47 | +26.5 | +5.7 | 55.3 | +5.7 | 56.5 | -63.8 | +3.8 | 65.4 | +26.0 |  | +37.3 | +21.8 | 1.000 |
| SOL | pair | 1m:DONCHIAN55pos=very low / 5m:HAbody=low | 240 | up | no | 3.68 | +16.7 | +3.8 | 54.0 | +3.8 | 56.5 | -54.1 | +3.7 | 61.3 | +15.8 |  | +18.4 | +12.1 | 1.000 |
| SOL | pair | 1m:CMO14=very low / 5m:LRSLOPE14 sign=below 0 | 240 | up | no | 3.68 | +14.7 | +3.1 | 53.4 | +3.2 | 51.5 | -55.1 | +2.9 | 54.3 | +13.8 |  | +23.2 | +16.0 | 1.000 |
| SOL | pair | 1m:RSI14=very low / 5m:LRSLOPE14 sign=below 0 | 240 | up | no | 3.68 | +14.7 | +3.1 | 53.4 | +3.2 | 51.5 | -55.1 | +2.9 | 54.3 | +13.8 |  | +23.2 | +16.0 | 1.000 |
| SOL | pair | 1m:DONCHIAN55pos=low (recovering) / 60m:HT_TRENDMODE=trend | 240 | up | no | 3.49 | +15.3 | +3.4 | 53.7 | +3.5 | 47.2 | -58.3 | +3.0 | 53.2 | +14.9 |  | +26.8 | +13.5 | 1.000 |
| SOL | pair | 1m:DONCHIAN55pos=very low / 60m:HT_TRENDMODE=trend | 240 | up | no | 3.90 | +13.6 | +3.7 | 53.8 | +3.6 | 54.4 | -58.1 | +3.2 | 52.9 | +12.7 |  | +26.0 | +11.8 | 1.000 |
| SOL | pair | 1m:CMO14=very low / 1m:TRIX30 sign=below 0 | 240 | up | no | 3.61 | +14.4 | +2.7 | 52.9 | +2.7 | 52.1 | -54.8 | +2.8 | 52.1 | +13.5 |  | +19.8 | +16.0 | 1.000 |
| SOL | pair | 1m:RSI14=very low / 1m:TRIX30 sign=below 0 | 240 | up | no | 3.61 | +14.4 | +2.7 | 52.9 | +2.7 | 52.1 | -54.8 | +2.8 | 52.1 | +13.5 |  | +19.8 | +16.0 | 1.000 |
| SOL | pair | 1m:RSI21=very low / 60m:HT_TRENDMODE=trend | 240 | up | no | 2.37 | +21.7 | +5.2 | 55.3 | +5.1 | 58.0 | -57.7 | +3.2 | 51.5 | +20.9 |  | +28.3 | +19.9 | 1.000 |
| SOL | pair | 1m:DONCHIAN55pos=very low / 1m:KST=low | 240 | up | no | 3.41 | +14.8 | +3.2 | 53.4 | +3.2 | 51.8 | -52.5 | +3.1 | 50.6 | +13.7 |  | +15.2 | +10.4 | 1.000 |
| XRP | pair | 1m:TSI=low (falling in) / 5m:FISHER10 sign=below 0 | 240 | up | no | 4.60 | +10.9 | +2.7 | 52.4 | +2.8 | 52.1 | -53.0 | +3.0 | 50.3 | +10.8 |  | +16.4 | +10.4 | 1.000 |
| SOL | triple | 1m:CORRELcv30=very low / 60m:ERIbull13 sign=below 0 / 5m:C-EMA200=low | 1440 | up | no | 0.38 | +130.8 | +11.8 | 60.6 | +11.9 | 60.4 | -151.6 | +3.8 | 50.0 | +128.7 |  | +95.0 | +122.3 | 1.000 |
| XRP | triple | 1m:PERCENTRANK100=low (recovering) / 5m:CORRELcv30 sign=below 0 / 1m:STOCH14 K>D=above | 240 | up | no | 3.35 | +14.8 | +4.4 | 54.1 | +4.4 | 54.5 | -56.5 | +3.4 | 49.6 | +14.1 |  | +8.5 | +14.9 | 1.000 |
| XRP | pair | 1m:AROONdn25=very high / 15m:HT_QUADRATURE sign=below 0 | 240 | up | no | 5.82 | +8.5 | +2.0 | 51.7 | +2.0 | 42.9 | -50.4 | +3.5 | 49.5 | +8.6 |  | +10.0 | +7.5 | 1.000 |
| XRP | triple | 1m:AROONdn14=very high / 1m:DX14=high / 15m:AC sign=below 0 | 240 | up | no | 2.71 | +18.3 | +4.0 | 53.7 | +4.0 | 57.9 | -55.2 | +3.2 | 49.5 | +17.9 |  | +22.6 | +17.6 | 1.000 |
| SOL | pair | 1m:RSI21=very low / 5m:ERIbull13 sign=below 0 | 240 | up | no | 3.32 | +14.8 | +2.8 | 53.0 | +2.8 | 51.6 | -52.8 | +2.6 | 49.3 | +14.1 |  | +39.4 | +14.4 | 1.000 |
| SOL | pair | 1m:RSI21=low (recovering) / 60m:HT_TRENDMODE=trend | 240 | up | no | 2.26 | +21.9 | +4.5 | 54.7 | +4.5 | 53.5 | -57.7 | +3.2 | 49.3 | +21.5 |  | +28.8 | +20.1 | 1.000 |
| SOL | pair | 1m:DONCHIAN55pos=low (recovering) / 1m:CMF20=low | 240 | up | no | 3.01 | +16.2 | +3.4 | 53.6 | +3.4 | 43.6 | -55.2 | +3.0 | 48.9 | +16.3 |  | +16.5 | +12.2 | 1.000 |
| XRP | pair | 1m:DONCHIAN55pos=very low / 15m:HT_QUADRATURE sign=below 0 | 240 | up | no | 4.62 | +10.6 | +2.4 | 52.1 | +2.4 | 53.0 | -52.8 | +2.7 | 48.9 | +9.9 |  | +15.3 | +9.6 | 1.000 |
| XRP | pair | 1m:RSI21=very low / 60m:KDJ K>D=below | 240 | up | no | 2.15 | +22.7 | +5.5 | 55.4 | +5.7 | 57.8 | -54.6 | +3.3 | 48.8 | +22.0 |  | +34.6 | +20.1 | 1.000 |
| SOL | pair | 1m:CMO14=very low / 1m:ERIbear13=low | 240 | up | no | 2.70 | +18.0 | +2.8 | 53.1 | +2.9 | 48.2 | -55.8 | +2.9 | 48.5 | +17.4 |  | +13.6 | +15.5 | 1.000 |
| SOL | pair | 1m:RSI14=very low / 1m:ERIbear13=low | 240 | up | no | 2.70 | +18.0 | +2.8 | 53.1 | +2.9 | 48.2 | -55.8 | +2.9 | 48.5 | +17.4 |  | +13.6 | +15.5 | 1.000 |
| XRP | pair | 1m:RSI21=very low / 60m:HT_TRENDMODE=trend | 240 | up | no | 2.15 | +22.5 | +5.9 | 55.5 | +5.8 | 59.4 | -64.4 | +3.0 | 48.4 | +22.0 |  | +32.9 | +17.8 | 1.000 |
| XRP | pair | 1m:ERIbull13=low (falling in) / 5m:AROONup14=very low | 240 | up | no | 4.02 | +11.8 | +3.1 | 52.8 | +3.2 | 51.3 | -50.3 | +2.8 | 47.4 | +11.6 |  | +11.1 | +11.5 | 1.000 |
| SOL | pair | 1m:RSI21=low (recovering) / 1m:HT_TRENDMODE=trend | 240 | up | no | 3.09 | +15.3 | +2.8 | 52.9 | +2.7 | 46.5 | -55.0 | +2.5 | 47.3 | +15.7 |  | +24.8 | +14.2 | 1.000 |
| XRP | pair | 1m:ACCBANDS20pos=low (falling in) / 5m:AROONup14=very low | 240 | up | no | 3.61 | +13.1 | +4.2 | 53.9 | +4.2 | 49.7 | -51.9 | +3.1 | 47.3 | +12.7 |  | +12.0 | +12.8 | 1.000 |
| XRP | triple | 1m:AROONdn25=very high / 1m:DX14=high / 1m:C-SMA20=low | 240 | up | no | 2.87 | +16.3 | +3.7 | 53.4 | +3.7 | 50.5 | -55.9 | +3.3 | 46.6 | +16.5 |  | +13.5 | +12.3 | 1.000 |
| XRP | pair | 15m:C-SMA20=low (falling in) / 60m:HT_TRENDMODE=trend | 240 | up | no | 1.33 | +34.6 | +7.8 | 57.7 | +8.0 | 67.8 | -60.0 | +4.3 | 46.1 | +32.9 |  | +53.1 | +29.9 | 1.000 |
| XRP | triple | 1m:RSI21=very low / 15m:SINE>LEAD=below / 60m:HT_TRENDMODE=trend | 240 | up | no | 1.35 | +34.2 | +9.1 | 59.0 | +9.3 | 68.7 | -67.7 | +3.4 | 46.0 | +33.8 |  | +49.2 | +29.5 | 1.000 |
| XRP | pair | 1m:RSI21=low (recovering) / 60m:KDJ K>D=below | 240 | up | no | 2.08 | +22.1 | +4.7 | 54.4 | +4.7 | 48.9 | -55.2 | +3.2 | 46.0 | +21.5 |  | +37.4 | +19.5 | 1.000 |
| SOL | pair | 1m:RSI21=very low / 15m:C-MAMA sign=below 0 | 240 | up | no | 3.39 | +13.5 | +2.5 | 52.7 | +2.5 | 52.3 | -52.9 | +2.4 | 45.9 | +12.7 |  | +35.2 | +13.6 | 1.000 |
| XRP | pair | 1m:PERCENTRANK100=high (cooling) / 60m:KST>sig=below | 240 | down | no | 2.84 | +16.0 | +3.3 | 53.2 | +3.3 | 42.4 | -45.8 | +3.5 | 45.6 | +15.7 |  | +24.0 | +10.2 | 1.000 |
| SOL | pair | 1m:RSI21=very low / 5m:PVT sign=below 0 | 240 | up | no | 3.54 | +12.8 | +2.8 | 52.9 | +2.8 | 52.0 | -53.1 | +2.4 | 45.4 | +12.1 |  | +54.6 | +13.8 | 1.000 |
| XRP | pair | 1m:PERCENTRANK100=high (cooling) / 60m:CTI20 sign=below 0 | 240 | down | no | 2.81 | +16.1 | +3.0 | 52.9 | +3.0 | 42.4 | -43.7 | +3.5 | 45.3 | +15.8 |  | +24.2 | +11.5 | 1.000 |
| XRP | single | 5m:STOCHK5=low (falling in) | 240 | up | no | 5.48 | +8.3 | +2.0 | 51.6 | +2.0 | 50.0 | -49.3 | +3.6 | 45.3 | +8.2 | +1.1 |  |  | 1.000 |
| XRP | triple | 1m:CMO14=very low / 15m:SINE>LEAD=below / 60m:HT_TRENDMODE=trend | 240 | up | no | 1.52 | +29.7 | +8.0 | 57.9 | +8.2 | 64.0 | -69.7 | +2.9 | 45.2 | +29.9 |  | +45.5 | +24.9 | 1.000 |
| XRP | triple | 1m:RSI14=very low / 15m:SINE>LEAD=below / 60m:HT_TRENDMODE=trend | 240 | up | no | 1.52 | +29.7 | +8.0 | 57.9 | +8.2 | 64.0 | -69.7 | +2.9 | 45.2 | +29.9 |  | +45.5 | +24.9 | 1.000 |
| XRP | pair | 1m:DONCHIAN55pos=very low / 15m:DOSC sign=below 0 | 240 | up | no | 4.30 | +10.5 | +2.9 | 52.6 | +2.9 | 54.0 | -54.2 | +2.9 | 45.0 | +10.2 |  | +18.0 | +8.9 | 1.000 |
| XRP | pair | 1m:CCI14=low (falling in) / 1m:HT_TRENDMODE=trend | 240 | up | no | 5.79 | +7.7 | +2.6 | 52.3 | +2.7 | 45.8 | -50.8 | +3.4 | 44.5 | +7.7 |  | +6.4 | +5.4 | 1.000 |
| XRP | pair | 1m:RSI7=low (falling in) / 5m:AROONup14=very low | 240 | up | no | 3.98 | +11.2 | +3.7 | 53.4 | +3.7 | 53.5 | -53.7 | +2.5 | 44.5 | +11.1 |  | +10.3 | +10.9 | 1.000 |

## Top 40 replicating by move per event on B (bps; at least 0.2 windows per day)

0 of 266 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SOL | triple | 1m:CORRELcv30=very low / 60m:ERIbull13 sign=below 0 / 5m:C-EMA200=low | 1440 | up | no | 0.38 | +130.8 | +11.8 | 60.6 | +11.9 | 60.4 | -151.6 | +3.8 | 50.0 | +128.7 |  | +95.0 | +122.3 | 1.000 |
| XRP | pair | 5m:PERCENTRANK100=very low / 60m:WT1=low | 1440 | up | no | 0.23 | +111.4 | +16.4 | 64.7 | +16.5 | 91.5 | -168.7 | +2.7 | 25.7 | +111.5 |  | +110.3 | +92.8 | 1.000 |
| SOL | pair | 15m:PVI=low (falling in) / 5m:SI=low | 1440 | up | no | 0.30 | +106.7 | +9.8 | 58.7 | +9.9 | 95.7 | -136.0 | +2.6 | 32.0 | +105.1 |  | +111.6 | +102.1 | 1.000 |
| SOL | pair | 60m:C-SWAK_BUTTER20=low (falling in) / 60m:CVI10 sign=below 0 | 1440 | up | no | 0.32 | +98.6 | +12.8 | 61.7 | +12.9 | 65.5 | -121.4 | +3.0 | 31.7 | +95.3 |  | +126.1 | +92.0 | 1.000 |
| SOL | pair | 15m:DONCHIAN55pos=very low / 5m:DPO20=high | 1440 | up | no | 0.24 | +96.2 | +11.1 | 60.0 | +11.2 | 70.7 | -135.7 | +2.3 | 23.5 | +95.9 |  | +107.9 | +93.3 | 1.000 |
| SOL | pair | 15m:C-VIDYA12=low (falling in) / 5m:KVO=low | 1440 | up | no | 0.36 | +95.7 | +12.5 | 61.4 | +12.6 | 65.5 | -146.0 | +2.6 | 34.5 | +93.6 |  | +105.0 | +87.4 | 1.000 |
| SOL | triple | 1m:RSI21=low (recovering) / 15m:HT_TRENDMODE=trend / 15m:C-RMA14=low | 1440 | up | no | 0.46 | +87.9 | +10.1 | 59.0 | +10.2 | 52.8 | -160.4 | +2.6 | 40.1 | +87.0 |  | +109.3 | +75.5 | 1.000 |
| SOL | triple | 1m:RSI21=low (recovering) / 15m:HT_TRENDMODE=trend / 15m:C-MCGD14=low | 1440 | up | no | 0.46 | +87.1 | +9.6 | 58.5 | +9.7 | 49.1 | -165.9 | +2.7 | 40.0 | +86.0 |  | +107.7 | +80.3 | 1.000 |
| SOL | triple | 1m:RSI21=low (recovering) / 15m:HT_TRENDMODE=trend / 15m:C-EMA21=low | 1440 | up | no | 0.48 | +82.2 | +9.6 | 58.5 | +9.7 | 39.9 | -159.8 | +2.6 | 39.5 | +81.6 |  | +103.2 | +75.6 | 1.000 |
| SOL | pair | 60m:C-SWAK_GAUSS20=low (falling in) / 60m:CVI10 sign=below 0 | 1440 | up | no | 0.36 | +72.5 | +11.0 | 59.9 | +11.1 | 64.7 | -128.9 | +2.3 | 25.9 | +70.7 |  | +97.5 | +65.9 | 1.000 |
| SOL | triple | 1m:CORRELcv30=very low / 60m:ERIbull13 sign=below 0 / 1m:TRIX15=low | 240 | up | no | 0.37 | +63.5 | +10.2 | 60.4 | +10.2 | 87.6 | -76.0 | +3.2 | 23.5 | +62.3 |  | +61.1 | +58.7 | 1.000 |
| BTC | pair | 60m:C-MEDPRICE=low (falling in) / 15m:AD=low | 1440 | up | no | 0.32 | +63.0 | +9.8 | 61.3 | +9.8 | 119.9 | -74.5 | +3.3 | 20.1 | +60.8 |  | +53.7 | +47.1 | 1.000 |
| BTC | pair | 60m:C-TYPPRICE=low (falling in) / 15m:AD=low | 1440 | up | no | 0.32 | +63.0 | +9.8 | 61.3 | +9.8 | 119.9 | -74.5 | +3.3 | 20.1 | +60.8 |  | +53.7 | +47.1 | 1.000 |
| BTC | pair | 60m:C-WCLPRICE=low (falling in) / 15m:AD=low | 1440 | up | no | 0.32 | +63.0 | +9.8 | 61.3 | +9.8 | 119.9 | -74.5 | +3.3 | 20.1 | +60.8 |  | +53.7 | +47.1 | 1.000 |
| XRP | pair | 15m:AROONdn14=very high / 5m:C-VWMA20 sign=above 0 | 240 | down | no | 0.31 | +56.4 | +11.6 | 61.2 | +11.4 | 60.3 | -48.7 | +3.9 | 17.5 | +58.2 |  | +59.9 | +55.3 | 1.000 |
| SOL | pair | 5m:C-EMA21=very low / 1m:MARKETFI sign=above 0 | 240 | up | no | 0.21 | +55.1 | +11.4 | 61.9 | +11.7 | 97.9 | -50.2 | +2.8 | 11.7 | +50.1 |  | +53.1 | +56.2 | 1.000 |
| XRP | pair | 15m:AROONdn14=very high / 5m:C-VWAP20 sign=above 0 | 240 | down | no | 0.32 | +53.6 | +10.5 | 60.2 | +10.3 | 48.0 | -47.6 | +3.6 | 17.1 | +55.4 |  | +56.9 | +52.4 | 1.000 |
| SOL | pair | 15m:C-SMA50=low (falling in) / 5m:HT_TRENDMODE=trend | 1440 | up | no | 0.61 | +53.4 | +5.6 | 54.5 | +5.7 | 43.5 | -152.0 | +2.3 | 32.6 | +53.4 |  | +103.2 | +51.0 | 1.000 |
| SOL | triple | 1m:CORRELcv30=very low / 60m:ERIbull13 sign=below 0 / 1m:PERCENTB20/2=low | 240 | up | no | 0.51 | +53.3 | +9.0 | 59.5 | +9.3 | 80.9 | -66.6 | +3.0 | 27.3 | +50.4 |  | +53.7 | +51.7 | 1.000 |
| SOL | triple | 1m:CORRELcv30=very low / 60m:ERIbull13 sign=below 0 / 1m:PERCENTB20/2.5=low | 240 | up | no | 0.51 | +53.3 | +9.0 | 59.5 | +9.3 | 80.9 | -66.6 | +3.0 | 27.3 | +50.4 |  | +53.7 | +51.7 | 1.000 |
| SOL | triple | 1m:CORRELcv30=very low / 60m:ERIbull13 sign=below 0 / 1m:ZSCORE20=low | 240 | up | no | 0.51 | +53.3 | +9.0 | 59.5 | +9.3 | 80.9 | -66.6 | +3.0 | 27.3 | +50.4 |  | +53.7 | +51.7 | 1.000 |
| XRP | pair | 1m:CMO14=very low / 5m:AROONdn14=very low | 1440 | down | no | 0.56 | +48.1 | +3.7 | 55.2 | +3.6 | 46.4 | -106.2 | +2.4 | 27.0 | +50.4 |  | +48.5 | +48.2 | 1.000 |
| XRP | pair | 1m:RSI14=very low / 5m:AROONdn14=very low | 1440 | down | no | 0.56 | +48.1 | +3.7 | 55.2 | +3.6 | 46.4 | -106.2 | +2.4 | 27.0 | +50.4 |  | +48.5 | +48.2 | 1.000 |
| XRP | pair | 15m:RSI7=high (rising in) / 60m:CTI20=low | 240 | down | no | 0.22 | +45.6 | +12.8 | 61.9 | +12.0 | 67.2 | -48.2 | +3.2 | 10.0 | +44.6 |  | +51.3 | +32.9 | 1.000 |
| XRP | pair | 15m:AROONdn14=very high / 15m:C-MAMA sign=above 0 | 240 | down | no | 0.23 | +45.3 | +6.9 | 57.0 | +7.1 | 58.0 | -48.8 | +2.4 | 10.3 | +46.2 |  | +47.5 | +46.6 | 1.000 |
| SOL | pair | 5m:KC20pos=very low / 1m:MARKETFI sign=above 0 | 240 | up | no | 0.23 | +44.7 | +10.3 | 60.2 | +10.0 | 66.0 | -48.0 | +2.7 | 10.4 | +41.4 |  | +43.5 | +45.8 | 1.000 |
| XRP | triple | 1m:RSI21=low (recovering) / 15m:SINE>LEAD=below / 5m:SMI=low | 240 | up | no | 0.93 | +44.4 | +6.5 | 56.2 | +6.5 | 60.0 | -56.7 | +3.2 | 41.2 | +42.9 |  | +45.7 | +43.8 | 1.000 |
| XRP | triple | 1m:AROONdn14=very high / 1m:DX14=high / 60m:ERIbull13=low | 240 | up | no | 0.47 | +44.2 | +14.7 | 64.5 | +14.8 | 45.3 | -77.5 | +3.1 | 20.9 | +45.6 |  | +38.6 | +44.0 | 1.000 |
| XRP | triple | 1m:KC20pos=high (rising in) / 1m:PVO12/26 sign=above 0 / 60m:C-DEMA21=very high | 240 | down | no | 0.21 | +43.7 | +13.5 | 63.5 | +13.7 | 85.4 | -60.8 | +3.2 | 9.2 | +45.0 |  | +42.7 | +33.8 | 1.000 |
| SOL | pair | 15m:C-VWMA20=low (falling in) / 60m:SWAK_BP20 sign=below 0 | 1440 | up | no | 0.80 | +43.7 | +6.9 | 55.7 | +7.0 | 54.8 | -146.4 | +2.3 | 35.0 | +41.9 |  | +67.1 | +45.1 | 1.000 |
| SOL | pair | 1m:CORRELcv30=very low / 15m:C-SMA50=low | 240 | up | no | 0.63 | +43.6 | +8.7 | 58.8 | +8.6 | 85.4 | -62.8 | +2.7 | 27.6 | +38.5 |  | +48.8 | +43.3 | 1.000 |
| SOL | triple | 1m:CORRELcv30=very low / 60m:ERIbull13 sign=below 0 / 1m:CCI20=low | 240 | up | no | 0.57 | +43.6 | +6.8 | 57.3 | +7.1 | 79.4 | -72.3 | +2.7 | 24.8 | +41.3 |  | +42.4 | +42.0 | 1.000 |
| BTC | pair | 60m:C-MEDPRICE=low (falling in) / 60m:WT1 sign=below 0 | 1440 | up | no | 0.53 | +43.5 | +7.2 | 58.8 | +7.2 | 97.7 | -71.4 | +3.5 | 23.1 | +42.4 |  | +44.7 | +39.3 | 1.000 |
| BTC | pair | 60m:C-TYPPRICE=low (falling in) / 60m:WT1 sign=below 0 | 1440 | up | no | 0.53 | +43.5 | +7.2 | 58.8 | +7.2 | 97.7 | -71.4 | +3.5 | 23.1 | +42.4 |  | +44.7 | +39.3 | 1.000 |
| BTC | pair | 60m:C-WCLPRICE=low (falling in) / 60m:WT1 sign=below 0 | 1440 | up | no | 0.53 | +43.5 | +7.2 | 58.8 | +7.2 | 97.7 | -71.4 | +3.5 | 23.1 | +42.4 |  | +44.7 | +39.3 | 1.000 |
| BTC | pair | 60m:C-MEDPRICE=low (falling in) / 60m:COPPOCK sign=below 0 | 1440 | up | no | 0.55 | +42.1 | +7.8 | 59.4 | +7.8 | 107.4 | -69.8 | +3.4 | 23.3 | +40.8 |  | +41.8 | +33.5 | 1.000 |
| BTC | pair | 60m:C-TYPPRICE=low (falling in) / 60m:COPPOCK sign=below 0 | 1440 | up | no | 0.55 | +42.1 | +7.8 | 59.4 | +7.8 | 107.4 | -69.8 | +3.4 | 23.3 | +40.8 |  | +41.8 | +33.5 | 1.000 |
| BTC | pair | 60m:C-WCLPRICE=low (falling in) / 60m:COPPOCK sign=below 0 | 1440 | up | no | 0.55 | +42.1 | +7.8 | 59.4 | +7.8 | 107.4 | -69.8 | +3.4 | 23.3 | +40.8 |  | +41.8 | +33.5 | 1.000 |
| XRP | pair | 15m:ERIbull13=low (falling in) / 1m:DX14=high | 240 | up | no | 0.37 | +41.6 | +13.0 | 62.6 | +12.9 | 69.0 | -56.7 | +2.8 | 15.4 | +37.6 |  | +39.0 | +37.7 | 1.000 |
| SOL | pair | 15m:SWAK_HP20=low (falling in) / 60m:PSO=low | 240 | up | no | 0.37 | +41.1 | +11.0 | 61.2 | +11.0 | 81.2 | -60.3 | +2.9 | 15.0 | +39.2 |  | +40.1 | +39.3 | 1.000 |

## Top 40 replicating by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)

81 of 9,873 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | single | 15m:PERCENTRANK100=low (falling in) | 240 | up | yes | 1.44 | +5.3 | +8.5 | 59.4 | +8.5 | 56.3 | -30.6 | +4.1 | 12.2 | +5.0 | -0.6 |  |  | 0.097 |
| BTC | single | 60m:C-MEDPRICE=low (falling in) | 240 | up | yes | 1.84 | +9.0 | +7.1 | 58.1 | +7.1 | 83.6 | -27.6 | +3.9 | 13.1 | +7.6 | -0.9 |  |  | 0.097 |
| BTC | single | 60m:C-TYPPRICE=low (falling in) | 240 | up | yes | 1.84 | +9.0 | +7.1 | 58.1 | +7.1 | 83.6 | -27.6 | +3.9 | 13.1 | +7.6 | -0.4 |  |  | 0.097 |
| BTC | single | 60m:C-WCLPRICE=low (falling in) | 240 | up | yes | 1.84 | +9.0 | +7.1 | 58.1 | +7.1 | 83.6 | -27.6 | +3.9 | 13.1 | +7.6 | -0.5 |  |  | 0.097 |
| BTC | single | 5m:ERIbull13=low (recovering) | 1440 | up | yes | 0.95 | +17.8 | +6.3 | 57.8 | +6.3 | 51.7 | -68.4 | +3.9 | 6.0 | +18.1 | -0.6 |  |  | 0.097 |
| BTC | single | 5m:C-EMA9=very high | 240 | down | yes | 2.49 | +2.5 | +5.9 | 54.9 | +5.9 | 69.9 | -25.3 | +3.9 | 14.8 | +1.8 | +0.3 |  |  | 0.097 |
| BTC | single | 5m:MACDh5/35/5=very high | 240 | down | yes | 2.59 | +2.7 | +5.6 | 54.7 | +5.6 | 65.2 | -25.1 | +3.9 | 14.6 | +1.7 | -0.4 |  |  | 0.097 |
| XRP | single | 5m:MDI14=high (rising in) | 240/1440 | up | yes | 3.14 | +13.4 | +5.2 | 54.9 | +5.2 | 51.4 | -50.5 | +4.4 | 16.5 | +12.7 | -0.0 |  |  | 0.063 |
| XRP | single | 1m:WT1=very high | 240 | down | yes | 3.00 | +9.6 | +5.1 | 55.0 | +5.2 | 52.6 | -51.3 | +4.0 | 15.4 | +10.0 | +0.0 |  |  | 0.097 |
| BTC | single | 5m:CCI50=low (falling in) | 240 | up | yes | 3.30 | +5.6 | +4.7 | 55.7 | +4.7 | 62.6 | -27.3 | +3.9 | 15.7 | +4.9 | -0.3 |  |  | 0.098 |
| BTC | single | 15m:C-T3_5=low (falling in) | 240 | up | yes | 3.71 | +3.5 | +4.6 | 55.6 | +4.6 | 61.9 | -26.7 | +4.3 | 17.0 | +2.9 | -0.7 |  |  | 0.063 |
| BTC | single | 5m:WAD=low (falling in) | 240 | up | yes | 4.09 | +4.5 | +4.3 | 55.2 | +4.3 | 53.3 | -28.6 | +4.3 | 17.4 | +4.1 | +0.7 |  |  | 0.063 |
| XRP | single | 1m:MDI14=very high | 240 | up | yes | 4.08 | +4.9 | +4.0 | 53.7 | +4.0 | 50.1 | -43.5 | +4.3 | 16.3 | +4.1 | -0.5 |  |  | 0.063 |
| XRP | single | 1m:C-MIDPRICE14=very low | 240 | up | yes | 5.21 | +6.4 | +3.5 | 53.2 | +3.5 | 51.1 | -47.5 | +4.8 | 18.3 | +5.7 | +0.3 |  |  | 0.027 |
| XRP | single | 1m:C-CKSPmid=very low | 240 | up | yes | 5.03 | +6.2 | +3.5 | 53.1 | +3.5 | 47.9 | -48.2 | +4.4 | 17.6 | +5.8 | -0.0 |  |  | 0.059 |
| BTC | single | 1m:MFI14=very low | 240 | up | yes | 5.18 | +1.3 | +3.5 | 54.4 | +3.5 | 49.5 | -25.3 | +4.4 | 18.0 | +1.1 | -0.5 |  |  | 0.059 |
| BTC | single | 1m:PERCENTRANK100=high (cooling) | 240/1440 | down | yes | 1.00 | +9.9 | +3.5 | 51.9 | +3.5 | 52.4 | -60.5 | +3.9 | 3.5 | +9.8 | +0.1 |  |  | 0.097 |
| XRP | single | 1m:C-KAMA30=very low | 240 | up | yes | 4.87 | +6.2 | +3.4 | 53.1 | +3.4 | 51.8 | -47.4 | +4.1 | 16.7 | +5.8 | -0.3 |  |  | 0.097 |
| XRP | single | 1m:CG10=low (falling in) | 240 | up | yes | 5.10 | +7.0 | +3.4 | 53.1 | +3.5 | 49.2 | -65.7 | +4.7 | 17.3 | +7.1 | -0.4 |  |  | 0.031 |
| XRP | single | 1m:ACCBANDS20pos=very low | 240 | up | yes | 4.66 | +4.7 | +3.4 | 53.1 | +3.4 | 55.3 | -50.2 | +4.0 | 15.7 | +3.5 | -0.1 |  |  | 0.097 |
| BTC | single | 1m:PERCENTRANK100=very high | 1440 | down | yes | 1.00 | +7.8 | +3.2 | 51.7 | +3.2 | 48.9 | -60.7 | +3.9 | 3.2 | +7.9 | +0.3 |  |  | 0.097 |
| BTC | single | 1m:MFI14=low (recovering) | 240 | up | yes | 5.06 | +1.3 | +3.2 | 54.2 | +3.2 | 43.8 | -26.1 | +3.9 | 16.4 | +1.4 | +0.2 |  |  | 0.097 |
| XRP | single | 1m:C-SMA20=very low | 240 | up | yes | 4.76 | +5.6 | +3.2 | 52.9 | +3.2 | 57.1 | -49.8 | +3.9 | 15.2 | +4.6 | +0.1 |  |  | 0.097 |
| XRP | single | 1m:C-EMA9=very low | 240 | up | yes | 5.38 | +5.2 | +3.1 | 52.8 | +3.2 | 58.9 | -48.2 | +4.7 | 16.8 | +4.1 | -0.2 |  |  | 0.031 |
| XRP | single | 1m:ERIbear13=very low | 240 | up | yes | 4.87 | +4.3 | +3.1 | 52.8 | +3.2 | 58.0 | -49.4 | +4.1 | 15.2 | +3.2 | -0.2 |  |  | 0.095 |
| XRP | single | 5m:C-MAMA=low (falling in) | 240 | up | yes | 5.20 | +5.0 | +3.1 | 52.8 | +3.1 | 42.5 | -50.8 | +4.1 | 15.9 | +4.8 | +0.3 |  |  | 0.095 |
| XRP | single | 1m:C-WMA20=very low | 240 | up | yes | 5.05 | +4.8 | +3.0 | 52.7 | +3.0 | 56.3 | -49.7 | +4.1 | 15.4 | +3.6 | -0.1 |  |  | 0.095 |
| XRP | single | 1m:KC20pos=very low | 240 | up | yes | 4.95 | +6.7 | +2.9 | 52.6 | +3.0 | 56.1 | -48.3 | +3.9 | 14.3 | +6.3 | +0.4 |  |  | 0.097 |
| ETH | single | 1m:C-ALMA9=very high | 240 | down | yes | 5.45 | +0.3 | +2.9 | 51.7 | +2.9 | 57.9 | -38.2 | +4.1 | 15.7 | +0.4 | +0.0 |  |  | 0.097 |
| XRP | single | 1m:QSTICK10=very low | 240 | up | yes | 5.11 | +6.1 | +2.9 | 52.5 | +2.8 | 47.3 | -48.5 | +4.0 | 14.7 | +5.5 | +0.1 |  |  | 0.097 |
| XRP | single | 5m:RSI2=low (falling in) | 240 | up | yes | 5.71 | +7.7 | +2.8 | 52.5 | +2.9 | 47.3 | -52.3 | +4.8 | 16.0 | +7.3 | +0.3 |  |  | 0.027 |
| XRP | single | 1m:AROONOSC25=very low | 240/1440 | up | yes | 5.66 | +5.4 | +2.7 | 52.4 | +2.7 | 45.9 | -51.9 | +4.3 | 15.1 | +5.1 | +0.3 |  |  | 0.063 |
| BTC | single | 1m:PDI14=high (rising in) | 240 | down | yes | 5.83 | +1.4 | +2.6 | 51.7 | +2.6 | 39.1 | -20.5 | +5.3 | 15.4 | +1.4 | +0.0 |  |  | 0.010 |
| XRP | single | 1m:C-SWAK_BUTTER20=very low | 240 | up | yes | 5.43 | +3.7 | +2.6 | 52.4 | +2.7 | 55.1 | -47.7 | +3.9 | 14.3 | +2.8 | -0.5 |  |  | 0.097 |
| BTC | single | 1m:DONCHIAN55pos=high (rising in) | 240/1440 | down | yes | 1.00 | +7.1 | +2.5 | 51.0 | +2.5 | 40.4 | -62.1 | +4.1 | 2.5 | +7.2 | +0.1 |  |  | 0.097 |
| BTC | single | 5m:STOCHFK5=low (falling in) | 240 | up | yes | 5.72 | +2.3 | +2.5 | 53.5 | +2.5 | 50.0 | -26.9 | +4.2 | 14.2 | +2.1 | +0.1 |  |  | 0.089 |
| BTC | single | 5m:SI=low (falling in) | 240 | up | yes | 5.54 | +1.5 | +2.5 | 53.4 | +2.5 | 51.4 | -28.0 | +3.9 | 13.7 | +1.5 | -0.1 |  |  | 0.097 |
| BTC | single | 1m:SMI=low (falling in) | 240/1440 | up | yes | 5.76 | +2.7 | +2.4 | 53.3 | +2.4 | 50.0 | -25.0 | +4.0 | 13.7 | +2.8 | +0.1 |  |  | 0.097 |
| XRP | single | 1m:WT1=low (falling in) | 240 | up | yes | 5.68 | +6.9 | +2.4 | 52.1 | +2.4 | 43.4 | -51.5 | +3.9 | 13.4 | +6.9 | +0.0 |  |  | 0.097 |
| BTC | single | 5m:CRSI=low (falling in) | 240 | up | yes | 5.78 | +1.2 | +2.1 | 53.1 | +2.1 | 49.4 | -26.4 | +4.0 | 12.3 | +0.9 | +0.3 |  |  | 0.097 |

## Top 40 replicating by odds heat on B (windows per day x odds points)

81 of 10,413 replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. For scale: an odds edge has to beat about 2.75 points to cover the fee and spread of a 50c contract held to settlement. Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). Share right: the share of events where price went the reading's way by more than 1.5 price steps; over base: against all minutes of the check period. Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.

| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| XRP | single | 1m:C-MIDPRICE14=very low | 240 | up | yes | 5.21 | +6.4 | +3.5 | 53.2 | +3.5 | 51.1 | -47.5 | +4.8 | 18.3 | +5.7 | +0.3 |  |  | 0.027 |
| BTC | single | 1m:MFI14=very low | 240 | up | yes | 5.18 | +1.3 | +3.5 | 54.4 | +3.5 | 49.5 | -25.3 | +4.4 | 18.0 | +1.1 | -0.5 |  |  | 0.059 |
| XRP | single | 1m:C-CKSPmid=very low | 240 | up | yes | 5.03 | +6.2 | +3.5 | 53.1 | +3.5 | 47.9 | -48.2 | +4.4 | 17.6 | +5.8 | -0.0 |  |  | 0.059 |
| BTC | single | 5m:WAD=low (falling in) | 240 | up | yes | 4.09 | +4.5 | +4.3 | 55.2 | +4.3 | 53.3 | -28.6 | +4.3 | 17.4 | +4.1 | +0.7 |  |  | 0.063 |
| XRP | single | 1m:CG10=low (falling in) | 240 | up | yes | 5.10 | +7.0 | +3.4 | 53.1 | +3.5 | 49.2 | -65.7 | +4.7 | 17.3 | +7.1 | -0.4 |  |  | 0.031 |
| BTC | single | 15m:C-T3_5=low (falling in) | 240 | up | yes | 3.71 | +3.5 | +4.6 | 55.6 | +4.6 | 61.9 | -26.7 | +4.3 | 17.0 | +2.9 | -0.7 |  |  | 0.063 |
| XRP | single | 1m:C-EMA9=very low | 240 | up | yes | 5.38 | +5.2 | +3.1 | 52.8 | +3.2 | 58.9 | -48.2 | +4.7 | 16.8 | +4.1 | -0.2 |  |  | 0.031 |
| XRP | single | 1m:C-KAMA30=very low | 240 | up | yes | 4.87 | +6.2 | +3.4 | 53.1 | +3.4 | 51.8 | -47.4 | +4.1 | 16.7 | +5.8 | -0.3 |  |  | 0.097 |
| XRP | single | 5m:MDI14=high (rising in) | 240/1440 | up | yes | 3.14 | +13.4 | +5.2 | 54.9 | +5.2 | 51.4 | -50.5 | +4.4 | 16.5 | +12.7 | -0.0 |  |  | 0.063 |
| BTC | single | 1m:MFI14=low (recovering) | 240 | up | yes | 5.06 | +1.3 | +3.2 | 54.2 | +3.2 | 43.8 | -26.1 | +3.9 | 16.4 | +1.4 | +0.2 |  |  | 0.097 |
| XRP | single | 1m:MDI14=very high | 240 | up | yes | 4.08 | +4.9 | +4.0 | 53.7 | +4.0 | 50.1 | -43.5 | +4.3 | 16.3 | +4.1 | -0.5 |  |  | 0.063 |
| XRP | single | 5m:RSI2=low (falling in) | 240 | up | yes | 5.71 | +7.7 | +2.8 | 52.5 | +2.9 | 47.3 | -52.3 | +4.8 | 16.0 | +7.3 | +0.3 |  |  | 0.027 |
| XRP | single | 5m:C-MAMA=low (falling in) | 240 | up | yes | 5.20 | +5.0 | +3.1 | 52.8 | +3.1 | 42.5 | -50.8 | +4.1 | 15.9 | +4.8 | +0.3 |  |  | 0.095 |
| ETH | single | 1m:C-ALMA9=very high | 240 | down | yes | 5.45 | +0.3 | +2.9 | 51.7 | +2.9 | 57.9 | -38.2 | +4.1 | 15.7 | +0.4 | +0.0 |  |  | 0.097 |
| XRP | single | 1m:ACCBANDS20pos=very low | 240 | up | yes | 4.66 | +4.7 | +3.4 | 53.1 | +3.4 | 55.3 | -50.2 | +4.0 | 15.7 | +3.5 | -0.1 |  |  | 0.097 |
| BTC | single | 5m:CCI50=low (falling in) | 240 | up | yes | 3.30 | +5.6 | +4.7 | 55.7 | +4.7 | 62.6 | -27.3 | +3.9 | 15.7 | +4.9 | -0.3 |  |  | 0.098 |
| XRP | single | 1m:C-WMA20=very low | 240 | up | yes | 5.05 | +4.8 | +3.0 | 52.7 | +3.0 | 56.3 | -49.7 | +4.1 | 15.4 | +3.6 | -0.1 |  |  | 0.095 |
| BTC | single | 1m:PDI14=high (rising in) | 240 | down | yes | 5.83 | +1.4 | +2.6 | 51.7 | +2.6 | 39.1 | -20.5 | +5.3 | 15.4 | +1.4 | +0.0 |  |  | 0.010 |
| XRP | single | 1m:WT1=very high | 240 | down | yes | 3.00 | +9.6 | +5.1 | 55.0 | +5.2 | 52.6 | -51.3 | +4.0 | 15.4 | +10.0 | +0.0 |  |  | 0.097 |
| XRP | single | 1m:C-SMA20=very low | 240 | up | yes | 4.76 | +5.6 | +3.2 | 52.9 | +3.2 | 57.1 | -49.8 | +3.9 | 15.2 | +4.6 | +0.1 |  |  | 0.097 |
| XRP | single | 1m:ERIbear13=very low | 240 | up | yes | 4.87 | +4.3 | +3.1 | 52.8 | +3.2 | 58.0 | -49.4 | +4.1 | 15.2 | +3.2 | -0.2 |  |  | 0.095 |
| XRP | single | 1m:AROONOSC25=very low | 240/1440 | up | yes | 5.66 | +5.4 | +2.7 | 52.4 | +2.7 | 45.9 | -51.9 | +4.3 | 15.1 | +5.1 | +0.3 |  |  | 0.063 |
| BTC | single | 5m:C-EMA9=very high | 240 | down | yes | 2.49 | +2.5 | +5.9 | 54.9 | +5.9 | 69.9 | -25.3 | +3.9 | 14.8 | +1.8 | +0.3 |  |  | 0.097 |
| XRP | single | 1m:QSTICK10=very low | 240 | up | yes | 5.11 | +6.1 | +2.9 | 52.5 | +2.8 | 47.3 | -48.5 | +4.0 | 14.7 | +5.5 | +0.1 |  |  | 0.097 |
| BTC | single | 5m:MACDh5/35/5=very high | 240 | down | yes | 2.59 | +2.7 | +5.6 | 54.7 | +5.6 | 65.2 | -25.1 | +3.9 | 14.6 | +1.7 | -0.4 |  |  | 0.097 |
| XRP | single | 1m:KC20pos=very low | 240 | up | yes | 4.95 | +6.7 | +2.9 | 52.6 | +3.0 | 56.1 | -48.3 | +3.9 | 14.3 | +6.3 | +0.4 |  |  | 0.097 |
| XRP | single | 1m:C-SWAK_BUTTER20=very low | 240 | up | yes | 5.43 | +3.7 | +2.6 | 52.4 | +2.7 | 55.1 | -47.7 | +3.9 | 14.3 | +2.8 | -0.5 |  |  | 0.097 |
| BTC | single | 5m:STOCHFK5=low (falling in) | 240 | up | yes | 5.72 | +2.3 | +2.5 | 53.5 | +2.5 | 50.0 | -26.9 | +4.2 | 14.2 | +2.1 | +0.1 |  |  | 0.089 |
| BTC | single | 5m:SI=low (falling in) | 240 | up | yes | 5.54 | +1.5 | +2.5 | 53.4 | +2.5 | 51.4 | -28.0 | +3.9 | 13.7 | +1.5 | -0.1 |  |  | 0.097 |
| BTC | single | 1m:SMI=low (falling in) | 240/1440 | up | yes | 5.76 | +2.7 | +2.4 | 53.3 | +2.4 | 50.0 | -25.0 | +4.0 | 13.7 | +2.8 | +0.1 |  |  | 0.097 |
| XRP | single | 1m:WT1=low (falling in) | 240 | up | yes | 5.68 | +6.9 | +2.4 | 52.1 | +2.4 | 43.4 | -51.5 | +3.9 | 13.4 | +6.9 | +0.0 |  |  | 0.097 |
| BTC | single | 60m:C-MEDPRICE=low (falling in) | 240 | up | yes | 1.84 | +9.0 | +7.1 | 58.1 | +7.1 | 83.6 | -27.6 | +3.9 | 13.1 | +7.6 | -0.9 |  |  | 0.097 |
| BTC | single | 60m:C-TYPPRICE=low (falling in) | 240 | up | yes | 1.84 | +9.0 | +7.1 | 58.1 | +7.1 | 83.6 | -27.6 | +3.9 | 13.1 | +7.6 | -0.4 |  |  | 0.097 |
| BTC | single | 60m:C-WCLPRICE=low (falling in) | 240 | up | yes | 1.84 | +9.0 | +7.1 | 58.1 | +7.1 | 83.6 | -27.6 | +3.9 | 13.1 | +7.6 | -0.5 |  |  | 0.097 |
| BTC | single | 1m:CMO14=low (falling in) | 240 | up | yes | 5.95 | +0.3 | +2.1 | 53.0 | +2.1 | 47.1 | -26.2 | +4.1 | 12.4 | +0.2 | +0.1 |  |  | 0.097 |
| BTC | single | 1m:RSI14=low (falling in) | 240 | up | yes | 5.95 | +0.3 | +2.1 | 53.0 | +2.1 | 47.1 | -26.2 | +4.1 | 12.4 | +0.2 | +0.1 |  |  | 0.097 |
| BTC | single | 5m:CRSI=low (falling in) | 240 | up | yes | 5.78 | +1.2 | +2.1 | 53.1 | +2.1 | 49.4 | -26.4 | +4.0 | 12.3 | +0.9 | +0.3 |  |  | 0.097 |
| BTC | single | 15m:PERCENTRANK100=low (falling in) | 240 | up | yes | 1.44 | +5.3 | +8.5 | 59.4 | +8.5 | 56.3 | -30.6 | +4.1 | 12.2 | +5.0 | -0.6 |  |  | 0.097 |
| XRP | single | 1m:WILLR14=low (falling in) | 240/1440 | up | yes | 6.00 | +4.2 | +2.0 | 51.7 | +2.0 | 42.6 | -50.3 | +5.8 | 12.0 | +4.3 | +0.4 |  |  | 0.001 |
| BTC | single | 1m:RVIR14=high (rising in) | 240 | down | yes | 5.95 | +1.7 | +1.9 | 51.0 | +1.9 | 45.0 | -23.1 | +3.9 | 11.6 | +1.8 | +0.0 |  |  | 0.097 |

## Tables

One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.

| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |
|---|---|---|---|---|---|---|
| BTC | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | 0.01 | 2ab0e8405c31fabb8265f00728265b3fcdf13f36064d93528dfd23d218b678c5 |
| BTC~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | e1f9b6cc5e77b94058dbf42624c6b4c56680099f4a2e7458ad12084c6d1c32bd |
| ETH | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | 0.01 | bb244d7fe78e348d11c81e5aa684c0d1e8c0aa3e1aa60d50e20a10db7ef382ad |
| ETH~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,326 | not on a grid | f61e647015e52a81049ef56c7d0b22ee414ba2f7432b60d15c51dd4c4ddbc1ae |
| SOL | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | 0.0001 | 9864ca6d8c5b8af530a951c3c65f34cc76c046eb7024977c89905fc9bb9fda04 |
| SOL~twin1 | 2020-08-12 | 2026-01-01 | 2,833,920 | 1,425 | not on a grid | 8a702d81f5ed8a35759697079da2d3bf9c5975fe8dba687193fce21d62ac30f9 |
| XRP | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | 1e-05 | b7b6fce7f6854b42a8e95f465f8b622eba2774a19b532c47b4727478ddf226c0 |
| XRP~twin1 | 2020-01-01 | 2026-01-01 | 3,156,480 | 2,325 | not on a grid | f3299ccbd7ac143aecbd2a9d751be1917508a7bdb38c76c441f55eeeca696629 |
