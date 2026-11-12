# OR-HM2 league: confluence across all data (coin price, discovery only)

Run: series of run 43030435253; HM2 league job 43221480254 at commit 3cafcd195d60a773bfe2fc636fec88802b0925f9.
Coins: BTC, ETH, SOL, XRP. No-signal twins: BTC~twin1, BTC~twin2, BTC~twin3, ETH~twin1, ETH~twin2, ETH~twin3, SOL~twin1, SOL~twin2, SOL~twin3, XRP~twin1, XRP~twin2, XRP~twin3.
Build on A = 2020-01-01 to 2024-12-31, check on B = 2025 (the data stop at 2026-01-01 00:00 UTC, Dec 31, 2025 7:00 PM EST; no minute of 2026 is read). The decision is a minute close; the entry is the next minute's open. Times are Eastern (ET: EST in winter, EDT in summer) and UTC. A map on coin price, not a validated rule and not a Kalshi-price result.

## How to read this

A cell is two readings (a pair) or three (a triple) each at a level at the same minute, for example "15m RSI14 very high while BTC's last 5 minutes are very low". Odds: half the shift in P(up) - P(down) over the base rate, in points. Windows per day: distinct H-minute clock windows that hold the state. oheat = windows per day x odds (how often x how sure). iheat = windows per day x how much the joint state beats what its two parts give on both the odds scale and the probability scale (iota_robust): confluence that the parts alone do not show. lheat = how often the second reading changes the call x by how much (lift over the weaker part). The direction of every row comes from A; every B number is signed in it, so a cell with no information scores about zero. The no-signal twins are the same pipeline on each coin with every minute's direction replaced by a coin flip (one joint flip for all coins): what chance alone produces. Marks (hot on A, replicated on B, BHY, above the twins' max) are columns; no mark removes a row.

## 1. Chance scale: the coins against their no-signal twins

Per kind and horizon, the coins pooled against the twin sets (each set = one twin of every coin): the median and, in brackets, the lowest and highest set. There are millions of correlated cells, so the twins' maximum is the yardstick, not t. Kept: the share of cells whose B sign equals the A sign (a coin flip gives a little under one half: a B value of exactly 0 counts as not kept).

### Pairs

| minutes | set | cells | under floor | kept direction | kept lift | kept iota | kept iota_add | kept iota_robust | t iota_robust B >= 2 | 99th pct oheat | max oheat | 99th pct iheat | max iheat | max iheat unseen | 99th pct lheat | max lheat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | coins | 24,412,643 | 5,576,626 | 0.701 | 0.451 | 0.543 | 0.544 | 0.542 | 0.030 | 281.84 | 880.99 | 39.81 | 337.38 | 337.38 | 141.25 | 906.08 |
| 1 | twins (3) | 24183428 (24160447 to 24205437) | 5820500 (5798049 to 5821433) | 0.501 (0.485 to 0.503) | 0.405 (0.391 to 0.408) | 0.499 (0.499 to 0.505) | 0.500 (0.499 to 0.505) | 0.499 (0.498 to 0.504) | 0.011 (0.011 to 0.011) | 50.12 (44.67 to 50.12) | 245.70 (195.61 to 246.79) | 28.18 (28.18 to 31.62) | 104.84 (104.06 to 109.47) | 97.55 (96.61 to 109.47) | 44.67 (39.81 to 44.67) | 293.46 (281.52 to 296.52) |
| 5 | coins | 24,412,643 | 5,576,626 | 0.779 | 0.478 | 0.552 | 0.553 | 0.552 | 0.027 | 158.49 | 390.08 | 22.39 | 130.00 | 130.00 | 70.80 | 402.90 |
| 5 | twins (3) | 24183428 (24160447 to 24205437) | 5820500 (5798049 to 5821433) | 0.500 (0.495 to 0.507) | 0.398 (0.394 to 0.406) | 0.500 (0.499 to 0.502) | 0.500 (0.499 to 0.502) | 0.499 (0.499 to 0.501) | 0.011 (0.010 to 0.011) | 25.12 (22.39 to 25.12) | 95.72 (82.86 to 96.09) | 15.85 | 54.77 (52.46 to 64.19) | 54.77 (52.46 to 64.19) | 22.39 (19.95 to 22.39) | 117.55 (105.66 to 126.25) |
| 15 | coins | 24,412,643 | 5,576,626 | 0.781 | 0.479 | 0.549 | 0.549 | 0.549 | 0.020 | 100.00 | 217.02 | 15.85 | 89.79 | 89.79 | 50.12 | 226.13 |
| 15 | twins (3) | 24183428 (24160447 to 24205437) | 5820500 (5798049 to 5821433) | 0.504 (0.498 to 0.508) | 0.394 (0.385 to 0.400) | 0.501 (0.500 to 0.502) | 0.501 (0.500 to 0.502) | 0.501 (0.500 to 0.502) | 0.009 (0.009 to 0.010) | 17.78 (17.78 to 19.95) | 66.87 (61.33 to 72.69) | 11.22 | 42.19 (42.16 to 47.02) | 42.16 (38.14 to 47.02) | 15.85 | 73.05 (68.91 to 84.51) |
| 30 | coins | 24,412,643 | 5,576,626 | 0.761 | 0.477 | 0.542 | 0.543 | 0.542 | 0.016 | 70.80 | 142.66 | 12.59 | 71.71 | 71.71 | 39.81 | 127.34 |
| 30 | twins (3) | 24183428 (24160447 to 24205437) | 5820500 (5798049 to 5821433) | 0.498 (0.497 to 0.504) | 0.389 (0.377 to 0.390) | 0.502 (0.499 to 0.503) | 0.502 (0.500 to 0.503) | 0.502 (0.499 to 0.503) | 0.009 (0.009 to 0.009) | 15.85 (14.12 to 15.85) | 57.26 (53.54 to 59.72) | 8.91 (8.91 to 10.00) | 37.59 (35.49 to 42.62) | 37.59 (35.49 to 42.62) | 12.59 (11.22 to 12.59) | 54.69 (52.22 to 62.84) |
| 60 | coins | 24,412,643 | 5,576,626 | 0.731 | 0.473 | 0.532 | 0.533 | 0.532 | 0.012 | 35.48 | 77.02 | 8.91 | 37.23 | 37.23 | 22.39 | 62.78 |
| 60 | twins (3) | 24183428 (24160447 to 24205437) | 5820500 (5798049 to 5821433) | 0.499 (0.488 to 0.514) | 0.379 (0.362 to 0.384) | 0.498 (0.497 to 0.502) | 0.498 (0.497 to 0.502) | 0.498 (0.497 to 0.502) | 0.008 (0.008 to 0.008) | 12.59 (11.22 to 12.59) | 36.66 (36.09 to 45.40) | 7.08 | 30.87 (27.32 to 31.70) | 27.32 (26.05 to 28.91) | 10.00 (8.91 to 10.00) | 37.89 (37.05 to 42.04) |
| 240 | coins | 24,409,537 | 5,578,026 | 0.654 | 0.429 | 0.525 | 0.525 | 0.524 | 0.009 | 12.59 | 26.58 | 5.62 | 18.41 | 17.36 | 7.94 | 24.91 |
| 240 | twins (3) | 24182196 (24158639 to 24203457) | 5820775 (5798782 to 5822004) | 0.506 (0.504 to 0.509) | 0.367 (0.363 to 0.372) | 0.500 (0.498 to 0.500) | 0.500 (0.498 to 0.501) | 0.500 (0.498 to 0.500) | 0.007 (0.006 to 0.007) | 7.94 (7.08 to 7.94) | 20.80 (20.38 to 21.77) | 5.01 | 16.31 (15.66 to 19.61) | 16.31 (15.66 to 19.61) | 6.31 (5.62 to 6.31) | 21.24 (20.82 to 21.34) |

Rows above the max of the coin's own three twins (over each coin's candidate pool, the 1,000 best per list; "1,000+" = the pool is full):

| minutes | all oheat | unseen oheat | all iheat | unseen iheat | all lheat | unseen lheat |
|---|---|---|---|---|---|---|
| 1 | 5,826+ | 4,000+ | 4,175+ | 3,065+ | 4,530+ | 3,306+ |
| 5 | 6,025+ | 4,000+ | 4,929+ | 3,511+ | 5,531+ | 4,000+ |
| 15 | 5,894+ | 4,000+ | 3,323+ | 2,408+ | 5,417+ | 4,000+ |
| 30 | 6,978+ | 4,000+ | 1,748 | 1,274 | 5,412+ | 3,601+ |
| 60 | 5,341+ | 3,087+ | 116 | 101 | 3,811+ | 2,076+ |
| 240 | 2,490+ | 1,560+ | 12 | 16 | 69 | 23 |

Persistence: the kept share of iota_robust by its A |t| (0-1, 1-2, 2-3, 3-4, 4 and over), for all cells and by how strong the parts are alone (part_tmax: the larger |t| on A of the two parts; a stratum, never a filter):

| minutes | stratum | set | 0-1 | 1-2 | 2-3 | 3-4 | 4+ |
|---|---|---|---|---|---|---|---|
| 15 | all | coins | 0.525 | 0.584 | 0.658 | 0.762 | 0.923 |
| 15 | all | twins | 0.501 (0.501 to 0.502) | 0.503 (0.498 to 0.503) | 0.500 (0.498 to 0.505) | 0.501 (0.490 to 0.507) | 0.473 (0.466 to 0.495) |
| 15 | ptmax<2 | coins | 0.509 | 0.527 | 0.555 | 0.604 | 0.801 |
| 15 | ptmax<2 | twins | 0.501 (0.500 to 0.502) | 0.502 (0.498 to 0.503) | 0.501 (0.497 to 0.504) | 0.500 (0.489 to 0.504) | 0.473 (0.460 to 0.488) |
| 15 | ptmax2-3 | coins | 0.515 | 0.545 | 0.595 | 0.665 | 0.823 |
| 15 | ptmax2-3 | twins | 0.503 (0.502 to 0.504) | 0.505 (0.499 to 0.513) | 0.501 (0.500 to 0.507) | 0.510 (0.505 to 0.533) | 0.550 (0.396 to 0.618) |
| 15 | ptmax>=3 | coins | 0.527 | 0.589 | 0.664 | 0.767 | 0.924 |
| 15 | ptmax>=3 | twins | 0.499 (0.499 to 0.500) | 0.505 (0.504 to 0.508) | 0.519 (0.479 to 0.529) | 0.487 (0.429 to 0.549) | 0.333 (0.250 to 0.625) |
| 60 | all | coins | 0.517 | 0.557 | 0.620 | 0.734 | 0.904 |
| 60 | all | twins | 0.497 (0.497 to 0.502) | 0.499 (0.497 to 0.505) | 0.495 (0.495 to 0.505) | 0.489 (0.482 to 0.508) | 0.485 (0.471 to 0.486) |
| 60 | ptmax<2 | coins | 0.509 | 0.527 | 0.561 | 0.669 | 0.850 |
| 60 | ptmax<2 | twins | 0.497 (0.497 to 0.502) | 0.499 (0.497 to 0.505) | 0.495 (0.494 to 0.505) | 0.490 (0.481 to 0.511) | 0.491 (0.470 to 0.491) |
| 60 | ptmax2-3 | coins | 0.512 | 0.537 | 0.580 | 0.669 | 0.872 |
| 60 | ptmax2-3 | twins | 0.499 (0.498 to 0.499) | 0.497 (0.496 to 0.504) | 0.496 (0.492 to 0.506) | 0.479 (0.469 to 0.480) | 0.431 (0.405 to 0.452) |
| 60 | ptmax>=3 | coins | 0.518 | 0.561 | 0.625 | 0.738 | 0.906 |
| 60 | ptmax>=3 | twins | 0.507 (0.498 to 0.513) | 0.511 (0.508 to 0.517) | 0.515 (0.492 to 0.542) | 0.515 (0.514 to 0.582) | 0.833 (0.667 to 1.000) |
| 240 | all | coins | 0.514 | 0.548 | 0.593 | 0.696 | 0.859 |
| 240 | all | twins | 0.499 (0.498 to 0.500) | 0.502 (0.499 to 0.503) | 0.504 (0.497 to 0.505) | 0.499 (0.496 to 0.502) | 0.466 (0.454 to 0.530) |
| 240 | ptmax<2 | coins | 0.507 | 0.522 | 0.553 | 0.655 | 0.857 |
| 240 | ptmax<2 | twins | 0.499 (0.498 to 0.500) | 0.502 (0.499 to 0.503) | 0.503 (0.498 to 0.505) | 0.496 (0.495 to 0.500) | 0.449 (0.438 to 0.531) |
| 240 | ptmax2-3 | coins | 0.511 | 0.532 | 0.562 | 0.633 | 0.846 |
| 240 | ptmax2-3 | twins | 0.499 (0.497 to 0.500) | 0.504 (0.496 to 0.505) | 0.514 (0.492 to 0.516) | 0.524 (0.502 to 0.535) | 0.574 (0.500 to 0.667) |
| 240 | ptmax>=3 | coins | 0.516 | 0.555 | 0.604 | 0.706 | 0.860 |
| 240 | ptmax>=3 | twins | 0.506 (0.489 to 0.509) | 0.495 (0.481 to 0.505) | 0.480 (0.471 to 0.494) | 0.464 (0.462 to 0.515) | 0.667 (0.556 to 1.000) |

### Triples

| minutes | set | cells | under floor | kept direction | kept lift | kept iota | kept iota_add | kept iota_robust | t iota_robust B >= 2 | 99th pct oheat | max oheat | 99th pct iheat | max iheat | max iheat unseen | 99th pct lheat | max lheat |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | coins | 1,308,116 | 194,781 | 0.720 | 0.462 | 0.545 | 0.545 | 0.543 | 0.033 | 199.53 | 919.13 | 39.81 | 269.07 | 254.92 | 100.00 | 836.57 |
| 1 | twins (3) | 968519 (919190 to 1003559) | 806679 (778113 to 855511) | 0.500 (0.499 to 0.504) | 0.420 (0.418 to 0.420) | 0.501 (0.498 to 0.503) | 0.501 (0.499 to 0.503) | 0.500 (0.498 to 0.502) | 0.015 (0.015 to 0.015) | 15.85 | 145.81 (134.05 to 152.33) | 11.22 (10.00 to 11.22) | 69.85 (67.84 to 73.66) | 67.84 (61.20 to 69.85) | 12.59 | 184.28 (171.34 to 214.12) |
| 5 | coins | 1,308,116 | 194,781 | 0.783 | 0.486 | 0.566 | 0.566 | 0.566 | 0.036 | 112.20 | 346.66 | 22.39 | 118.63 | 107.87 | 56.23 | 341.65 |
| 5 | twins (3) | 968519 (919190 to 1003559) | 806679 (778113 to 855511) | 0.503 (0.500 to 0.510) | 0.412 (0.406 to 0.421) | 0.502 (0.499 to 0.502) | 0.502 (0.499 to 0.502) | 0.501 (0.499 to 0.501) | 0.015 (0.014 to 0.015) | 10.00 | 68.87 (61.27 to 81.42) | 7.08 (6.31 to 7.08) | 44.57 (43.41 to 48.52) | 43.41 (35.40 to 44.57) | 7.94 (7.08 to 7.94) | 95.15 (90.93 to 95.37) |
| 15 | coins | 1,308,116 | 194,781 | 0.775 | 0.488 | 0.558 | 0.558 | 0.558 | 0.028 | 79.43 | 192.16 | 15.85 | 83.40 | 83.40 | 39.81 | 179.84 |
| 15 | twins (3) | 968519 (919190 to 1003559) | 806679 (778113 to 855511) | 0.505 (0.504 to 0.513) | 0.406 (0.404 to 0.414) | 0.503 (0.502 to 0.503) | 0.503 (0.502 to 0.503) | 0.503 (0.502 to 0.503) | 0.014 (0.013 to 0.014) | 8.91 | 50.38 (45.85 to 51.77) | 5.62 | 29.34 (26.56 to 30.75) | 28.81 (26.56 to 29.34) | 6.31 (6.31 to 7.08) | 56.92 (46.55 to 67.31) |
| 30 | coins | 1,308,116 | 194,781 | 0.759 | 0.485 | 0.554 | 0.554 | 0.554 | 0.022 | 63.10 | 127.78 | 12.59 | 66.30 | 66.30 | 31.62 | 106.52 |
| 30 | twins (3) | 968519 (919190 to 1003559) | 806679 (778113 to 855511) | 0.502 (0.498 to 0.517) | 0.398 (0.397 to 0.411) | 0.501 (0.499 to 0.503) | 0.501 (0.499 to 0.504) | 0.501 (0.499 to 0.503) | 0.013 (0.013 to 0.013) | 7.94 (7.08 to 8.91) | 34.90 (29.94 to 46.54) | 5.01 (5.01 to 5.62) | 24.27 (24.08 to 25.81) | 24.27 (24.08 to 25.81) | 5.62 (5.62 to 6.31) | 36.58 (36.26 to 45.32) |
| 60 | coins | 1,308,116 | 194,781 | 0.726 | 0.484 | 0.538 | 0.539 | 0.538 | 0.016 | 35.48 | 75.58 | 8.91 | 32.27 | 31.46 | 22.39 | 65.29 |
| 60 | twins (3) | 968519 (919190 to 1003559) | 806679 (778113 to 855511) | 0.505 (0.499 to 0.506) | 0.392 (0.391 to 0.398) | 0.502 (0.499 to 0.504) | 0.502 (0.499 to 0.504) | 0.502 (0.499 to 0.504) | 0.012 (0.012 to 0.012) | 7.08 (7.08 to 7.94) | 27.01 (26.39 to 30.89) | 4.47 (4.47 to 5.01) | 17.41 (17.12 to 21.49) | 17.41 (17.12 to 17.91) | 5.62 | 28.12 (23.62 to 30.13) |
| 240 | coins | 1,307,898 | 194,961 | 0.658 | 0.444 | 0.530 | 0.530 | 0.530 | 0.011 | 14.12 | 24.18 | 6.31 | 16.79 | 16.79 | 8.91 | 25.03 |
| 240 | twins (3) | 968353 (919085 to 1003403) | 806743 (778149 to 855527) | 0.491 (0.488 to 0.506) | 0.379 (0.372 to 0.384) | 0.500 (0.500 to 0.502) | 0.500 (0.500 to 0.502) | 0.500 (0.500 to 0.502) | 0.011 (0.011 to 0.011) | 5.62 (5.62 to 6.31) | 15.70 (15.69 to 17.30) | 3.98 | 12.70 (11.58 to 13.30) | 11.29 (10.88 to 12.70) | 4.47 (4.47 to 5.01) | 14.84 (14.42 to 16.08) |

Rows above the max of the coin's own three twins (over each coin's candidate pool, the 1,000 best per list; "1,000+" = the pool is full):

| minutes | all oheat | unseen oheat | all iheat | unseen iheat | all lheat | unseen lheat |
|---|---|---|---|---|---|---|
| 1 | 6,308+ | 4,000+ | 1,678 | 770 | 2,139+ | 1,640+ |
| 5 | 6,747+ | 4,000+ | 1,314 | 1,166 | 3,279+ | 2,295+ |
| 15 | 6,878+ | 4,000+ | 1,996 | 975 | 3,765+ | 1,837+ |
| 30 | 6,610+ | 4,000+ | 1,394 | 696 | 4,632+ | 3,022+ |
| 60 | 6,733+ | 4,000+ | 601 | 238 | 2,679+ | 2,058+ |
| 240 | 3,105+ | 2,207+ | 107 | 120 | 325 | 511 |

Persistence: the kept share of iota_robust by its A |t| (0-1, 1-2, 2-3, 3-4, 4 and over), for all cells and by how strong the parts are alone (part_tmax: the larger |t| on A of the two parts; a stratum, never a filter):

| minutes | stratum | set | 0-1 | 1-2 | 2-3 | 3-4 | 4+ |
|---|---|---|---|---|---|---|---|
| 15 | all | coins | 0.531 | 0.591 | 0.660 | 0.755 | 0.896 |
| 15 | all | twins | 0.503 (0.501 to 0.503) | 0.505 (0.503 to 0.505) | 0.507 (0.504 to 0.508) | 0.495 (0.483 to 0.519) | 0.465 (0.398 to 0.657) |
| 15 | ptmax<2 | coins | 0.520 | 0.545 | 0.608 | 0.721 | 0.766 |
| 15 | ptmax<2 | twins | 0.506 (0.505 to 0.507) | 0.510 (0.505 to 0.520) | 0.509 (0.508 to 0.511) | 0.490 (0.458 to 0.493) | 0.480 (0.421 to 0.529) |
| 15 | ptmax2-3 | coins | 0.511 | 0.544 | 0.556 | 0.634 | 0.867 |
| 15 | ptmax2-3 | twins | 0.502 (0.496 to 0.503) | 0.509 (0.501 to 0.512) | 0.507 (0.499 to 0.528) | 0.525 (0.404 to 0.545) | 0.625 (0.273 to 0.643) |
| 15 | ptmax>=3 | coins | 0.531 | 0.593 | 0.663 | 0.758 | 0.900 |
| 15 | ptmax>=3 | twins | 0.502 (0.498 to 0.502) | 0.501 (0.494 to 0.503) | 0.501 (0.499 to 0.510) | 0.503 (0.496 to 0.537) | 0.421 (0.385 to 0.806) |
| 60 | all | coins | 0.521 | 0.557 | 0.618 | 0.709 | 0.872 |
| 60 | all | twins | 0.501 (0.498 to 0.503) | 0.502 (0.502 to 0.507) | 0.504 (0.498 to 0.516) | 0.515 (0.474 to 0.519) | 0.525 (0.493 to 0.557) |
| 60 | ptmax<2 | coins | 0.513 | 0.530 | 0.560 | 0.669 | 0.679 |
| 60 | ptmax<2 | twins | 0.500 (0.496 to 0.500) | 0.504 (0.498 to 0.506) | 0.505 (0.500 to 0.516) | 0.511 (0.470 to 0.534) | 0.462 (0.444 to 0.571) |
| 60 | ptmax2-3 | coins | 0.504 | 0.507 | 0.517 | 0.500 | 0.556 |
| 60 | ptmax2-3 | twins | 0.500 (0.498 to 0.508) | 0.504 (0.498 to 0.520) | 0.494 (0.480 to 0.529) | 0.495 (0.470 to 0.534) | 0.462 (0.400 to 0.500) |
| 60 | ptmax>=3 | coins | 0.522 | 0.560 | 0.621 | 0.713 | 0.878 |
| 60 | ptmax>=3 | twins | 0.504 (0.503 to 0.504) | 0.501 (0.498 to 0.514) | 0.507 (0.505 to 0.509) | 0.510 (0.466 to 0.524) | 0.609 (0.469 to 0.809) |
| 240 | all | coins | 0.518 | 0.551 | 0.591 | 0.658 | 0.798 |
| 240 | all | twins | 0.500 (0.500 to 0.501) | 0.501 (0.499 to 0.507) | 0.508 (0.505 to 0.509) | 0.497 (0.494 to 0.514) | 0.468 (0.450 to 0.565) |
| 240 | ptmax<2 | coins | 0.509 | 0.518 | 0.531 | 0.601 | 0.738 |
| 240 | ptmax<2 | twins | 0.501 (0.497 to 0.502) | 0.502 (0.494 to 0.510) | 0.508 (0.504 to 0.508) | 0.493 (0.482 to 0.508) | 0.467 (0.429 to 0.565) |
| 240 | ptmax2-3 | coins | 0.506 | 0.509 | 0.541 | 0.608 | 0.696 |
| 240 | ptmax2-3 | twins | 0.498 (0.493 to 0.507) | 0.502 (0.487 to 0.513) | 0.511 (0.506 to 0.517) | 0.540 (0.538 to 0.571) | 0.467 (0.400 to 0.545) |
| 240 | ptmax>=3 | coins | 0.520 | 0.557 | 0.598 | 0.662 | 0.801 |
| 240 | ptmax>=3 | twins | 0.498 (0.493 to 0.517) | 0.509 (0.487 to 0.518) | 0.510 (0.473 to 0.532) | 0.473 (0.472 to 0.523) | 0.533 (0.500 to 0.600) |

## 2. The unseen slice

The same lists over the cells whose readings are not in a pack the bot loads and were not stored together in HM1 (seen_in_league = none: provenance only; how strong the parts are alone stays a column). Each sentence gives the twins' best row of the same list.

- **BTC, pairs, 15 minutes, by iheat:**
  - 1m C-TRIMA20 above 0 while 1m HT_TRENDMODE trend: down, 53% right on 2025, 60.5 windows a day, +1.2 odds points beyond what the parts give (twins' best: 51%, 34.7 windows).
  - 1m C-CKSPmid below 0 while 1m HT_TRENDMODE trend: up, 52% right on 2025, 59.4 windows a day, +1.2 odds points beyond what the parts give (twins' best: 51%, 34.7 windows).
  - 1m DX14 high while 5m C-HMA20 above 0: down, 56% right on 2025, 16.3 windows a day, +4.3 odds points beyond what the parts give (twins' best: 51%, 34.7 windows).
- **BTC, pairs, 15 minutes, by oheat:**
  - 1m C-FRAMA16 above 0 while 1m CMF20 above 0: down, 52% right on 2025, 69.7 windows a day (twins' best: 51%, 48.2 windows).
  - 1m ASI above 0 while 1m CMF20 above 0: down, 52% right on 2025, 67.4 windows a day (twins' best: 51%, 48.2 windows).
  - 1m CMF20 above 0 while 1m HAbody above 0: down, 52% right on 2025, 71.5 windows a day (twins' best: 51%, 48.2 windows).
- **BTC, pairs, 60 minutes, by iheat:**
  - 1m RVOL20 very high while 1m SWAK_2PHP20 below 0: up, 53% right on 2025, 13.5 windows a day, +2.6 odds points beyond what the parts give (twins' best: 53%, 8.6 windows).
  - 1m BOP above 0 while 1m RVOL20 very high: down, 52% right on 2025, 12.9 windows a day, +2.6 odds points beyond what the parts give (twins' best: 53%, 8.6 windows).
  - 1m FOSC5 above 0 while 1m RVOL20 very high: down, 52% right on 2025, 13.3 windows a day, +2.5 odds points beyond what the parts give (twins' best: 53%, 8.6 windows).
- **BTC, pairs, 60 minutes, by oheat:**
  - 1m CCI20 below 0 while 1m CMF20 low: up, 54% right on 2025, 18.3 windows a day (twins' best: 52%, 14.6 windows).
  - 1m COPPOCK below 0 while FLOW:TB5 low: up, 53% right on 2025, 21.3 windows a day (twins' best: 52%, 14.6 windows).
  - the other coins' breadth over 15 minutes 3 down while FLOW:TB5 low: up, 54% right on 2025, 19.6 windows a day (twins' best: 52%, 14.6 windows).
- **BTC, pairs, 240 minutes, by iheat:**
  - 1m DX14 high while 1m KVO high: down, 53% right on 2025, 3.5 windows a day, +4.9 odds points beyond what the parts give (twins' best: 55%, 3.4 windows).
  - 1m KVO high while 1m PVO12/26 high: down, 53% right on 2025, 4.1 windows a day, +4.2 odds points beyond what the parts give (twins' best: 55%, 3.4 windows).
  - 1m C-HT_TRENDLINE high while 1m MASSI low: down, 45% right on 2025, 3.2 windows a day, +5.2 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 3.4 windows).
- **BTC, pairs, 240 minutes, by oheat:**
  - 1m CCI20 above 0 while 1m NVI low: down, 54% right on 2025, 5.0 windows a day (twins' best: 55%, 4.7 windows).
  - 1m TRANGE high while FLOW:TB15 high: down, 54% right on 2025, 5.2 windows a day (twins' best: 55%, 4.7 windows).
  - FLOW:Stretch15 low while OI:PxQuad60 long liquidation: up, 57% right on 2025, 4.5 windows a day (twins' best: 55%, 4.7 windows).
- **BTC, triples, 15 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m QSTICK10 above 0: down, 50% right on 2025, 47.4 windows a day, +1.5 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 23.4 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m C-TRIMA20 above 0: down, 50% right on 2025, 45.9 windows a day, +1.4 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 23.4 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m WAD above 0: down, 50% right on 2025, 47.8 windows a day, +1.3 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 23.4 windows).
- **BTC, triples, 15 minutes, by oheat:**
  - 15m CHOP14 very low or 15m CHOP14 low or 15m CHOP14 mid or 15m CHOP14 NA while 1m AROONOSC14 above 0 and 1m IBS very low or 1m IBS low or 1m IBS mid or 1m IBS NA: down, 52% right on 2025, 74.8 windows a day (twins' best: 51%, 62.0 windows).
  - 1m BOP mid or 1m BOP high or 1m BOP very high while 1m SWAK_HP20 below 0 and 5m AVGDEV14 mid or 5m AVGDEV14 high or 5m AVGDEV14 very high or 5m AVGDEV14 NA: up, 51% right on 2025, 83.5 windows a day (twins' best: 51%, 62.0 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m C-FRAMA16 above 0: down, 54% right on 2025, 34.0 windows a day (twins' best: 51%, 62.0 windows).
- **BTC, triples, 60 minutes, by iheat:**
  - 1m WAD above 0 while 1m CVI10 high and 1m CDL:DOJI fires: down, 46% right on 2025, 4.6 windows a day, +5.2 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 53%, 6.4 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m ASI above 0: down, 50% right on 2025, 22.5 windows a day, +1.0 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 53%, 6.4 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m HT_INPHASE above 0: up, 51% right on 2025, 22.7 windows a day, +1.0 odds points beyond what the parts give (twins' best: 53%, 6.4 windows).
- **BTC, triples, 60 minutes, by oheat:**
  - 1m PSO below 0 or 1m PSO NA while 1m QSTICK10 below 0 or 1m QSTICK10 NA and 1m SI very low or 1m SI low or 1m SI NA: up, 53% right on 2025, 21.0 windows a day (twins' best: 52%, 20.5 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m C-TEMA21 above 0: down, 53% right on 2025, 15.6 windows a day (twins' best: 52%, 20.5 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 1m WT1>WT2 below: up, 53% right on 2025, 17.3 windows a day (twins' best: 52%, 20.5 windows).
- **BTC, triples, 240 minutes, by iheat:**
  - 1m VHF28 high while 5m C-TSF14 below 0 and 1m KVO above 0: up, 47% right on 2025, 3.1 windows a day, +5.2 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 53%, 2.4 windows).
  - 1m VHF28 high while 5m C-LINEARREG14 below 0 and 1m KVO above 0: up, 47% right on 2025, 2.7 windows a day, +5.3 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 53%, 2.4 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m MASSI low: down, 46% right on 2025, 3.8 windows a day, +3.8 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 53%, 2.4 windows).
- **BTC, triples, 240 minutes, by oheat:**
  - 5m MACDh12/26/9 above 0 while 5m CVI10 above 0 and FLOW:TB5 very high: down, 55% right on 2025, 4.1 windows a day (twins' best: 53%, 3.6 windows).
  - 1m C-TEMA21 above 0 while 1m RVOL20 very high and 15m HT_INPHASE above 0: down, 54% right on 2025, 4.2 windows a day (twins' best: 53%, 3.6 windows).
  - 1m C-TEMA21 above 0 while 1m RVOL20 very high and 15m DPO20 below 0: down, 54% right on 2025, 4.3 windows a day (twins' best: 53%, 3.6 windows).
- **ETH, pairs, 15 minutes, by iheat:**
  - 1m C-TEMA21 above 0 while 1m TRANGE high: down, 52% right on 2025, 38.7 windows a day, +2.3 odds points beyond what the parts give (twins' best: 50%, 47.8 windows).
  - 1m C-TEMA21 below 0 while 1m TRANGE high: up, 52% right on 2025, 40.5 windows a day, +2.2 odds points beyond what the parts give (twins' best: 50%, 47.8 windows).
  - 1m C-TSF14 below 0 while the entry minute is in minutes 00-04 of the quarter hour (ET and UTC alike): down, 51% right on 2025, 79.2 windows a day, +1.1 odds points beyond what the parts give (twins' best: 50%, 47.8 windows).
- **ETH, pairs, 15 minutes, by oheat:**
  - 1m C-FRAMA16 above 0 while 5m MOM10 above 0: down, 53% right on 2025, 58.0 windows a day (twins' best: 51%, 44.1 windows).
  - 1m C-EMA21 above 0 while 1m HT_TRENDMODE trend: down, 53% right on 2025, 59.0 windows a day (twins' best: 51%, 44.1 windows).
  - 1m C-FRAMA16 above 0 while 5m C-WMA20 above 0: down, 53% right on 2025, 60.2 windows a day (twins' best: 51%, 44.1 windows).
- **ETH, pairs, 60 minutes, by iheat:**
  - 1m STOCHRSI14 very high while 1m RVOL20 high: down, 53% right on 2025, 15.1 windows a day, +2.5 odds points beyond what the parts give (twins' best: 48%, 15.2 windows).
  - 1m TRANGE high while 1m SWAK_2PHP20 below 0: up, 52% right on 2025, 21.4 windows a day, +1.6 odds points beyond what the parts give (twins' best: 48%, 15.2 windows).
  - 1m RVOL20 high while 1m KVO>sig above: down, 51% right on 2025, 20.6 windows a day, +1.6 odds points beyond what the parts give (twins' best: 48%, 15.2 windows).
- **ETH, pairs, 60 minutes, by oheat:**
  - 1m CCI20 high while 5m KDJ K>D above: down, 52% right on 2025, 19.3 windows a day (twins' best: 52%, 17.8 windows).
  - 1m CCI20 high while 1m KST above 0: down, 52% right on 2025, 17.6 windows a day (twins' best: 52%, 17.8 windows).
  - 1m STOCHRSI14 very high while 1m TRIX15 above 0: down, 52% right on 2025, 17.9 windows a day (twins' best: 52%, 17.8 windows).
- **ETH, pairs, 240 minutes, by iheat:**
  - 1m DX14 high while 1m C-SAR high: down, 54% right on 2025, 4.0 windows a day, +4.3 odds points beyond what the parts give (twins' best: 55%, 3.0 windows).
  - 1m C-HMA20 high while 5m Runs 3-4 up: down, 54% right on 2025, 3.1 windows a day, +5.3 odds points beyond what the parts give (twins' best: 55%, 3.0 windows).
  - 1m DIdiff14 above 0 while 1m C-SAR low: down, 54% right on 2025, 3.8 windows a day, +4.2 odds points beyond what the parts give (twins' best: 55%, 3.0 windows).
- **ETH, pairs, 240 minutes, by oheat:**
  - 60m C-CKSPmid below 0 while SOL's 1m taker buying low: up, 58% right on 2025, 3.4 windows a day (twins' best: 55%, 3.0 windows).
  - 1m HT_DCPHASE low while SOL's last 15 minutes low: up, 56% right on 2025, 4.8 windows a day (twins' best: 55%, 3.0 windows).
  - 1m BOP very high while 60m C-CKSPmid below 0: up, 59% right on 2025, 3.2 windows a day (twins' best: 55%, 3.0 windows).
- **ETH, triples, 15 minutes, by iheat:**
  - 1m MACDh12/26/9 below 0 while 1m CVI10 above 0 and 1m PVO12/26 below 0: up, 51% right on 2025, 43.9 windows a day, +1.6 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 27.4 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m LRSLOPE14 above 0: down, 50% right on 2025, 39.1 windows a day, +1.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 27.4 windows).
  - 1m MACDh12/26/9 below 0 while 1m CVI10 above 0 and 1m DX14 high: up, 56% right on 2025, 14.3 windows a day, +4.6 odds points beyond what the parts give (twins' best: 51%, 27.4 windows).
- **ETH, triples, 15 minutes, by oheat:**
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 1m ASI above 0: down, 52% right on 2025, 56.6 windows a day (twins' best: 51%, 27.4 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m HAbody above 0: down, 54% right on 2025, 34.8 windows a day (twins' best: 51%, 27.4 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m SWAK_HP20 above 0: down, 54% right on 2025, 35.1 windows a day (twins' best: 51%, 27.4 windows).
- **ETH, triples, 60 minutes, by iheat:**
  - 1m CVI10 above 0 while 1m KST>sig above and 1m LRSLOPE14 below 0: up, 54% right on 2025, 14.0 windows a day, +2.2 odds points beyond what the parts give (twins' best: 48%, 7.1 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and 1m QSTICK10 below 0: up, 53% right on 2025, 17.3 windows a day, +1.8 odds points beyond what the parts give (twins' best: 48%, 7.1 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and 1m EMV14 below 0: up, 53% right on 2025, 17.2 windows a day, +1.8 odds points beyond what the parts give (twins' best: 48%, 7.1 windows).
- **ETH, triples, 60 minutes, by oheat:**
  - 1m CVI10 above 0 while 1m KST>sig above and 1m STOCHRSI14 very high: down, 52% right on 2025, 19.8 windows a day (twins' best: 52%, 19.2 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m C-TEMA21 above 0: down, 53% right on 2025, 15.9 windows a day (twins' best: 52%, 19.2 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 1m CCI20 high: down, 52% right on 2025, 17.8 windows a day (twins' best: 52%, 19.2 windows).
- **ETH, triples, 240 minutes, by iheat:**
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m C-TSF14 very low: down, 54% right on 2025, 3.4 windows a day, +4.8 odds points beyond what the parts give (twins' best: 52%, 3.3 windows).
  - 1m PVO12/26 high while 5m C-TSF14 above 0 and 1m C-VWMA20 below 0: up, 54% right on 2025, 4.2 windows a day, +3.3 odds points beyond what the parts give (twins' best: 52%, 3.3 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and OI:Chg15 low: down, 54% right on 2025, 3.1 windows a day, +4.5 odds points beyond what the parts give (twins' best: 52%, 3.3 windows).
- **ETH, triples, 240 minutes, by oheat:**
  - 1m DOSC below 0 while 1m ER10 high and the gap to SOL over 15 minutes low: up, 56% right on 2025, 3.9 windows a day (twins' best: 55%, 2.3 windows).
  - 1m CVI10 high while 1m KST>sig above and 1m C-SWAK_BUTTER20 very high: down, 55% right on 2025, 3.0 windows a day (twins' best: 55%, 2.3 windows).
  - 1m DX14 high while 1m KVO below 0 and 15m MARKETFI above 0: up, 56% right on 2025, 3.7 windows a day (twins' best: 55%, 2.3 windows).
- **SOL, pairs, 15 minutes, by iheat:**
  - 1m ERIbear13 below 0 while the entry minute is minute 0 of the Kalshi quarter hour (ET and UTC alike): up, 51% right on 2025, 61.6 windows a day, +0.9 odds points beyond what the parts give (twins' best: 50%, 48.2 windows).
  - 1m HT_INPHASE above 0 while the entry minute is in minutes 05-09 of the quarter hour (ET and UTC alike): down, 49% right on 2025, 75.6 windows a day, +0.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 50%, 48.2 windows).
  - 1m HT_INPHASE below 0 while the entry minute is in minutes 05-09 of the quarter hour (ET and UTC alike): up, 49% right on 2025, 76.0 windows a day, +0.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 50%, 48.2 windows).
- **SOL, pairs, 15 minutes, by oheat:**
  - 1m AROONOSC25 above 0 while 1m C-FRAMA16 above 0: down, 51% right on 2025, 62.5 windows a day (twins' best: 50%, 41.7 windows).
  - 1m AROONOSC25 above 0 while 1m FISHER>trig above: down, 51% right on 2025, 62.5 windows a day (twins' best: 50%, 41.7 windows).
  - 1m AROONOSC25 above 0 while 1m CCI14 above 0: down, 51% right on 2025, 61.9 windows a day (twins' best: 50%, 41.7 windows).
- **SOL, pairs, 60 minutes, by iheat:**
  - 1m DOSC above 0 while 1m HT_INPHASE low: up, 52% right on 2025, 12.9 windows a day, +2.2 odds points beyond what the parts give (twins' best: 53%, 9.3 windows).
  - 1m QSTICK10 high while 1m PVO12/26 below 0: down, 48% right on 2025, 16.3 windows a day, +1.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 53%, 9.3 windows).
  - 1m KDJ K>D below while ETH's last 5 minutes high: down, 53% right on 2025, 7.7 windows a day, +3.5 odds points beyond what the parts give (twins' best: 53%, 9.3 windows).
- **SOL, pairs, 60 minutes, by oheat:**
  - 1m C-TEMA21 above 0 while FLOW:TB5 high: down, 51% right on 2025, 18.6 windows a day (twins' best: 53%, 13.7 windows).
  - 5m NVI above 0 while FLOW:TB5 low: up, 54% right on 2025, 11.9 windows a day (twins' best: 53%, 13.7 windows).
  - 1m C-TEMA21 below 0 while FLOW:TB15 low: up, 54% right on 2025, 12.9 windows a day (twins' best: 53%, 13.7 windows).
- **SOL, pairs, 240 minutes, by iheat:**
  - 5m FISHER10 below 0 while OI:PxQuad60 short covering: down, 52% right on 2025, 4.5 windows a day, +3.8 odds points beyond what the parts give (twins' best: 55%, 2.5 windows).
  - 1m FISHER10 low while 1m OBVdiv10 bull div: up, 47% right on 2025, 3.3 windows a day, +4.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 2.5 windows).
  - 5m C-VWAP20 below 0 while OI:PxQuad60 short covering: down, 51% right on 2025, 4.5 windows a day, +3.4 odds points beyond what the parts give (twins' best: 55%, 2.5 windows).
- **SOL, pairs, 240 minutes, by oheat:**
  - 5m C-LINEARREG14 low while 5m PVO12/26 below 0: up, 54% right on 2025, 4.7 windows a day (twins' best: 56%, 3.1 windows).
  - 1m ERIbull13 low while BTC's last 15 minutes low: up, 54% right on 2025, 5.1 windows a day (twins' best: 56%, 3.1 windows).
  - 1m C-SMA50 low while 5m SWAK_BP20 above 0: up, 55% right on 2025, 4.1 windows a day (twins' best: 56%, 3.1 windows).
- **SOL, triples, 15 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m HT_INPHASE above 0: up, 50% right on 2025, 48.6 windows a day, +1.1 odds points beyond what the parts give (twins' best: 49%, 40.5 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE cycle and 1m CCI20 below 0: up, 49% right on 2025, 43.7 windows a day, +1.1 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 49%, 40.5 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m C-WMA20 above 0: down, 48% right on 2025, 50.6 windows a day, +1.0 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 49%, 40.5 windows).
- **SOL, triples, 15 minutes, by oheat:**
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 1m C-SMA50 above 0: down, 51% right on 2025, 47.5 windows a day (twins' best: 49%, 51.1 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 1m OBV above 0: down, 51% right on 2025, 53.0 windows a day (twins' best: 49%, 51.1 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 1m AD above 0: down, 51% right on 2025, 53.8 windows a day (twins' best: 49%, 51.1 windows).
- **SOL, triples, 60 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 5m C-MIDPOINT14 above 0: down, 45% right on 2025, 7.5 windows a day, +3.4 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 17.6 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 5m FOSC5 above 0: up, 51% right on 2025, 21.8 windows a day, +1.1 odds points beyond what the parts give (twins' best: 51%, 17.6 windows).
  - 60m HT_TRENDMODE cycle or 60m HT_TRENDMODE NA while the entry minute is in minutes 15-29 of the hour (ET and UTC alike) or the entry minute is in minutes 30-44 of the hour (ET and UTC alike) or the entry minute is in minutes A of the hour (ET and UTC alike) and BTC's 1m RSI14 very low or BTC's 1m RSI14 low or BTC's 1m RSI14 NA: up, 45% right on 2025, 4.7 windows a day, +5.1 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 17.6 windows).
- **SOL, triples, 60 minutes, by oheat:**
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 15m FOSC5 above 0: down, 51% right on 2025, 19.3 windows a day (twins' best: 51%, 19.2 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 5m DPO20 below 0: down, 51% right on 2025, 19.5 windows a day (twins' best: 51%, 19.2 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE cycle and FLOW:TB5 high: down, 52% right on 2025, 13.8 windows a day (twins' best: 51%, 19.2 windows).
- **SOL, triples, 240 minutes, by iheat:**
  - 5m Tenkan>Kijun above while 5m HT_TRENDMODE trend and XRP's 1m RSI14 low: down, 52% right on 2025, 3.3 windows a day, +4.8 odds points beyond what the parts give (twins' best: 47%, 4.2 windows).
  - 1m LRSLOPE14 below 0 while the entry minute is in minutes 00-14 of the hour (ET and UTC alike) and 1m C-TEMA21 very high: up, 57% right on 2025, 1.8 windows a day, +7.2 odds points beyond what the parts give (twins' best: 47%, 4.2 windows).
  - 1m LRSLOPE14 below 0 while the entry minute is in minutes 00-14 of the hour (ET and UTC alike) and 1m ADOSC low: up, 48% right on 2025, 4.6 windows a day, +2.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 47%, 4.2 windows).
- **SOL, triples, 240 minutes, by oheat:**
  - 5m FOSC5 below 0 while the entry minute is in minutes 10-14 of the quarter hour (ET and UTC alike) and 1m RVI14 low: up, 54% right on 2025, 5.3 windows a day (twins' best: 54%, 3.7 windows).
  - 5m FOSC5 below 0 while the entry minute is in minutes 10-14 of the quarter hour (ET and UTC alike) and 1m MASSI low: up, 55% right on 2025, 3.1 windows a day (twins' best: 54%, 3.7 windows).
  - 1m VHF28 high while 5m C-TSF14 above 0 and 5m OBV below 0: up, 56% right on 2025, 3.1 windows a day (twins' best: 54%, 3.7 windows).
- **XRP, pairs, 15 minutes, by iheat:**
  - 1m ERIbull13 below 0 while 1m HT_TRENDMODE cycle: up, 49% right on 2025, 60.7 windows a day, +1.2 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 50%, 47.9 windows).
  - 1m C-LINEARREG14 above 0 while the entry minute is in minutes 00-04 of the quarter hour (ET and UTC alike): down, 48% right on 2025, 79.9 windows a day, +0.9 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 50%, 47.9 windows).
  - 1m ERIbear13 above 0 while 1m HT_TRENDMODE cycle: down, 50% right on 2025, 61.9 windows a day, +1.1 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 50%, 47.9 windows).
- **XRP, pairs, 15 minutes, by oheat:**
  - 1m C-EMA50 above 0 while 1m PVT above 0: down, 52% right on 2025, 69.6 windows a day (twins' best: 51%, 41.6 windows).
  - 1m ERIbull13 below 0 while the other coins' breadth over 15 minutes 3 down: up, 52% right on 2025, 57.4 windows a day (twins' best: 51%, 41.6 windows).
  - 1m HAbody above 0 while 5m C-SWAK_GAUSS20 above 0: down, 52% right on 2025, 65.2 windows a day (twins' best: 51%, 41.6 windows).
- **XRP, pairs, 60 minutes, by iheat:**
  - 1m ER10 low while 1m MACDh5/35/5 above 0: up, 50% right on 2025, 21.3 windows a day, +1.4 odds points beyond what the parts give (twins' best: 52%, 14.7 windows).
  - 1m ER10 low while 1m MACDh5/35/5 below 0: down, 51% right on 2025, 21.2 windows a day, +1.4 odds points beyond what the parts give (twins' best: 52%, 14.7 windows).
  - 1m C-TSF14 low while the entry minute is in minutes 05-09 of the quarter hour (ET and UTC alike): up, 51% right on 2025, 17.1 windows a day, +1.7 odds points beyond what the parts give (twins' best: 52%, 14.7 windows).
- **XRP, pairs, 60 minutes, by oheat:**
  - 1m ERIbear13 above 0 while 5m C-TSF14 below 0: down, 52% right on 2025, 19.1 windows a day (twins' best: 52%, 13.6 windows).
  - 1m STOCHFK5 low while the other coins' breadth over 15 minutes 3 down: up, 52% right on 2025, 19.6 windows a day (twins' best: 52%, 13.6 windows).
  - 1m CCI14 high while 1m MARKETFI below 0: down, 52% right on 2025, 21.2 windows a day (twins' best: 52%, 13.6 windows).
- **XRP, pairs, 240 minutes, by iheat:**
  - 1m PSO low while 5m MACDh5/35/5 above 0: up, 54% right on 2025, 4.8 windows a day, +3.6 odds points beyond what the parts give (twins' best: 55%, 3.3 windows).
  - 1m LRSLOPE14 low while 5m C-LINEARREG14 above 0: up, 57% right on 2025, 2.8 windows a day, +6.1 odds points beyond what the parts give (twins' best: 55%, 3.3 windows).
  - 1m CMOU14 above 0 while SOL's last 15 minutes low: down, 56% right on 2025, 2.7 windows a day, +6.2 odds points beyond what the parts give (twins' best: 55%, 3.3 windows).
- **XRP, pairs, 240 minutes, by oheat:**
  - the gap to BTC over 15 minutes low while SOL's 1m RSI14 low: up, 55% right on 2025, 4.2 windows a day (twins' best: 56%, 3.9 windows).
  - 1m AROONdn25 very low while 5m CDL:BELTHOLD bull: down, 55% right on 2025, 4.4 windows a day (twins' best: 56%, 3.9 windows).
  - 1m PSO low while 5m MACDh5/35/5 above 0: up, 54% right on 2025, 4.8 windows a day (twins' best: 56%, 3.9 windows).
- **XRP, triples, 15 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m LRSLOPE14 above 0: up, 49% right on 2025, 38.3 windows a day, +2.2 odds points beyond what the parts give (twins' best: 48%, 43.5 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m CMOU14 above 0: down, 50% right on 2025, 41.3 windows a day, +1.8 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 48%, 43.5 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m QSTICK10 above 0: up, 49% right on 2025, 47.5 windows a day, +1.5 odds points beyond what the parts give (twins' best: 48%, 43.5 windows).
- **XRP, triples, 15 minutes, by oheat:**
  - 1m C-EMA200 above 0 while 1m PVI very low or 1m PVI low or 1m PVI mid or 1m PVI NA and the other coins' breadth over 15 minutes 1 down or the other coins' breadth over 15 minutes mid or the other coins' breadth over 15 minutes 1 up or the other coins' breadth over 15 minutes 2 up or the other coins' breadth over 15 minutes 3 up or the other coins' breadth over 15 minutes NA: down, 52% right on 2025, 59.7 windows a day (twins' best: 50%, 37.5 windows).
  - 1m ERIbull13 below 0 or 1m ERIbull13 NA while 5m BBW20 mid or 5m BBW20 high or 5m BBW20 very high or 5m BBW20 NA and the half hour 12:00 AM-12:30 AM ET (05:00 UTC in winter, 04:00 UTC in summer) or the half hour 12:30 AM-1:00 AM ET (05:30 UTC in winter, 04:30 UTC in summer) or the half hour 1:00 AM-1:30 AM ET (06:00 UTC in winter, 05:00 UTC in summer) or the half hour 1:30 AM-2:00 AM ET (06:30 UTC in winter, 05:30 UTC in summer) or the half hour 2:30 AM-3:00 AM ET (07:30 UTC in winter, 06:30 UTC in summer) or the half hour 3:00 AM-3:30 AM ET (08:00 UTC in winter, 07:00 UTC in summer) or the half hour 3:30 AM-4:00 AM ET (08:30 UTC in winter, 07:30 UTC in summer) or the half hour 4:00 AM-4:30 AM ET (09:00 UTC in winter, 08:00 UTC in summer) or the half hour 4:30 AM-5:00 AM ET (09:30 UTC in winter, 08:30 UTC in summer) or the half hour 5:00 AM-5:30 AM ET (10:00 UTC in winter, 09:00 UTC in summer) or the half hour 5:30 AM-6:00 AM ET (10:30 UTC in winter, 09:30 UTC in summer) or the half hour 6:00 AM-6:30 AM ET (11:00 UTC in winter, 10:00 UTC in summer) or the half hour 6:30 AM-7:00 AM ET (11:30 UTC in winter, 10:30 UTC in summer) or the half hour 7:00 AM-7:30 AM ET (12:00 UTC in winter, 11:00 UTC in summer) or the half hour 7:30 AM-8:00 AM ET (12:30 UTC in winter, 11:30 UTC in summer) or the half hour 8:00 AM-8:30 AM ET (13:00 UTC in winter, 12:00 UTC in summer) or the half hour 8:30 AM-9:00 AM ET (13:30 UTC in winter, 12:30 UTC in summer) or the half hour 9:00 AM-9:30 AM ET (14:00 UTC in winter, 13:00 UTC in summer) or the half hour 9:30 AM-10:00 AM ET (14:30 UTC in winter, 13:30 UTC in summer) or the half hour 10:00 AM-10:30 AM ET (15:00 UTC in winter, 14:00 UTC in summer) or the half hour 10:30 AM-11:00 AM ET (15:30 UTC in winter, 14:30 UTC in summer) or the half hour 11:30 AM-12:00 PM ET (16:30 UTC in winter, 15:30 UTC in summer) or the half hour 12:00 PM-12:30 PM ET (17:00 UTC in winter, 16:00 UTC in summer) or the half hour 12:30 PM-1:00 PM ET (17:30 UTC in winter, 16:30 UTC in summer) or the half hour 1:00 PM-1:30 PM ET (18:00 UTC in winter, 17:00 UTC in summer) or the half hour 1:30 PM-2:00 PM ET (18:30 UTC in winter, 17:30 UTC in summer) or the half hour 2:00 PM-2:30 PM ET (19:00 UTC in winter, 18:00 UTC in summer) or the half hour 2:30 PM-3:00 PM ET (19:30 UTC in winter, 18:30 UTC in summer) or the half hour 3:00 PM-3:30 PM ET (20:00 UTC in winter, 19:00 UTC in summer) or the half hour 3:30 PM-4:00 PM ET (20:30 UTC in winter, 19:30 UTC in summer) or the half hour 4:00 PM-4:30 PM ET (21:00 UTC in winter, 20:00 UTC in summer) or the half hour 4:30 PM-5:00 PM ET (21:30 UTC in winter, 20:30 UTC in summer) or the half hour 5:00 PM-5:30 PM ET (22:00 UTC in winter, 21:00 UTC in summer) or the half hour 5:30 PM-6:00 PM ET (22:30 UTC in winter, 21:30 UTC in summer) or the half hour 6:00 PM-6:30 PM ET (23:00 UTC in winter, 22:00 UTC in summer) or the half hour 6:30 PM-7:00 PM ET (23:30 UTC in winter, 22:30 UTC in summer) or the half hour 7:00 PM-7:30 PM ET (00:00 UTC in winter, 23:00 UTC in summer) or the half hour 9:00 PM-9:30 PM ET (02:00 UTC in winter, 01:00 UTC in summer) or the half hour 10:00 PM-10:30 PM ET (03:00 UTC in winter, 02:00 UTC in summer) or the half hour 10:30 PM-11:00 PM ET (03:30 UTC in winter, 02:30 UTC in summer) or the half hour 11:00 PM-11:30 PM ET (04:00 UTC in winter, 03:00 UTC in summer) or the half hour 11:30 PM-12:00 AM ET (04:30 UTC in winter, 03:30 UTC in summer) or NY30m NA: up, 51% right on 2025, 61.5 windows a day (twins' best: 50%, 37.5 windows).
  - 1m ERIbull13 below 0 or 1m ERIbull13 NA while 1m PVI very low or 1m PVI low or 1m PVI mid and the half hour 12:00 AM-12:30 AM ET (05:00 UTC in winter, 04:00 UTC in summer) or the half hour 12:30 AM-1:00 AM ET (05:30 UTC in winter, 04:30 UTC in summer) or the half hour 1:00 AM-1:30 AM ET (06:00 UTC in winter, 05:00 UTC in summer) or the half hour 1:30 AM-2:00 AM ET (06:30 UTC in winter, 05:30 UTC in summer) or the half hour 2:30 AM-3:00 AM ET (07:30 UTC in winter, 06:30 UTC in summer) or the half hour 3:00 AM-3:30 AM ET (08:00 UTC in winter, 07:00 UTC in summer) or the half hour 3:30 AM-4:00 AM ET (08:30 UTC in winter, 07:30 UTC in summer) or the half hour 5:00 AM-5:30 AM ET (10:00 UTC in winter, 09:00 UTC in summer) or the half hour 5:30 AM-6:00 AM ET (10:30 UTC in winter, 09:30 UTC in summer) or the half hour 6:30 AM-7:00 AM ET (11:30 UTC in winter, 10:30 UTC in summer) or the half hour 7:00 AM-7:30 AM ET (12:00 UTC in winter, 11:00 UTC in summer) or the half hour 7:30 AM-8:00 AM ET (12:30 UTC in winter, 11:30 UTC in summer) or the half hour 8:00 AM-8:30 AM ET (13:00 UTC in winter, 12:00 UTC in summer) or the half hour 8:30 AM-9:00 AM ET (13:30 UTC in winter, 12:30 UTC in summer) or the half hour 9:00 AM-9:30 AM ET (14:00 UTC in winter, 13:00 UTC in summer) or the half hour 9:30 AM-10:00 AM ET (14:30 UTC in winter, 13:30 UTC in summer) or the half hour 10:00 AM-10:30 AM ET (15:00 UTC in winter, 14:00 UTC in summer) or the half hour 10:30 AM-11:00 AM ET (15:30 UTC in winter, 14:30 UTC in summer) or the half hour 11:30 AM-12:00 PM ET (16:30 UTC in winter, 15:30 UTC in summer) or the half hour 12:00 PM-12:30 PM ET (17:00 UTC in winter, 16:00 UTC in summer) or the half hour 12:30 PM-1:00 PM ET (17:30 UTC in winter, 16:30 UTC in summer) or the half hour 1:00 PM-1:30 PM ET (18:00 UTC in winter, 17:00 UTC in summer) or the half hour 1:30 PM-2:00 PM ET (18:30 UTC in winter, 17:30 UTC in summer) or the half hour 2:00 PM-2:30 PM ET (19:00 UTC in winter, 18:00 UTC in summer) or the half hour 2:30 PM-3:00 PM ET (19:30 UTC in winter, 18:30 UTC in summer) or the half hour 3:00 PM-3:30 PM ET (20:00 UTC in winter, 19:00 UTC in summer) or the half hour 3:30 PM-4:00 PM ET (20:30 UTC in winter, 19:30 UTC in summer) or the half hour 4:00 PM-4:30 PM ET (21:00 UTC in winter, 20:00 UTC in summer) or the half hour 4:30 PM-5:00 PM ET (21:30 UTC in winter, 20:30 UTC in summer) or the half hour 5:00 PM-5:30 PM ET (22:00 UTC in winter, 21:00 UTC in summer) or the half hour 5:30 PM-6:00 PM ET (22:30 UTC in winter, 21:30 UTC in summer) or the half hour 6:00 PM-6:30 PM ET (23:00 UTC in winter, 22:00 UTC in summer) or the half hour 6:30 PM-7:00 PM ET (23:30 UTC in winter, 22:30 UTC in summer) or the half hour 7:30 PM-8:00 PM ET (00:30 UTC in winter, 23:30 UTC in summer) or the half hour 9:00 PM-9:30 PM ET (02:00 UTC in winter, 01:00 UTC in summer) or the half hour 9:30 PM-10:00 PM ET (02:30 UTC in winter, 01:30 UTC in summer) or the half hour 10:00 PM-10:30 PM ET (03:00 UTC in winter, 02:00 UTC in summer) or the half hour 10:30 PM-11:00 PM ET (03:30 UTC in winter, 02:30 UTC in summer) or the half hour 11:00 PM-11:30 PM ET (04:00 UTC in winter, 03:00 UTC in summer) or the half hour 11:30 PM-12:00 AM ET (04:30 UTC in winter, 03:30 UTC in summer) or NY30m NA: up, 51% right on 2025, 63.9 windows a day (twins' best: 50%, 37.5 windows).
- **XRP, triples, 60 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m SQZMOM above 0: down, 50% right on 2025, 19.2 windows a day, +1.2 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 45%, 3.9 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m CMOU14 above 0: down, 50% right on 2025, 21.6 windows a day, +1.0 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 45%, 3.9 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 5m C-ZLEMA21 above 0: up, 50% right on 2025, 18.9 windows a day, +1.1 odds points beyond what the parts give (twins' best: 45%, 3.9 windows).
- **XRP, triples, 60 minutes, by oheat:**
  - 5m PVI above 0 while FLOW:Stretch15 mid or FLOW:Stretch15 high or FLOW:Stretch15 very high or FLOW:Stretch15 NA and FLOW:Stretch5 high or FLOW:Stretch5 very high or FLOW:Stretch5 NA: down, 53% right on 2025, 13.9 windows a day (twins' best: 52%, 12.2 windows).
  - 15m SI above 0 or 15m SI NA while 1m CRSI mid or 1m CRSI high or 1m CRSI very high or 1m CRSI NA and 5m CORRELcv30 above 0: down, 53% right on 2025, 13.3 windows a day (twins' best: 52%, 12.2 windows).
  - 15m C-KAMA30 above 0 while 1m VORTEXdiff14 above 0 or 1m VORTEXdiff14 NA and 5m MASSI mid or 5m MASSI high or 5m MASSI very high or 5m MASSI NA: down, 53% right on 2025, 13.8 windows a day (twins' best: 52%, 12.2 windows).
- **XRP, triples, 240 minutes, by iheat:**
  - 1m DOSC below 0 while 1m ER10 high and 5m C-HMA20 above 0: up, 57% right on 2025, 2.9 windows a day, +5.8 odds points beyond what the parts give (twins' best: 47%, 4.1 windows).
  - 1m DOSC below 0 while 1m ER10 high and 5m KDJ K>D above: up, 54% right on 2025, 3.9 windows a day, +3.2 odds points beyond what the parts give (twins' best: 47%, 4.1 windows).
  - 1m DOSC below 0 while 1m ER10 high and 5m C-ZLEMA21 above 0: up, 54% right on 2025, 3.1 windows a day, +3.8 odds points beyond what the parts give (twins' best: 47%, 4.1 windows).
- **XRP, triples, 240 minutes, by oheat:**
  - 1m DOSC above 0 while 1m ER10 high and 15m FISHER>trig above: down, 54% right on 2025, 4.9 windows a day (twins' best: 57%, 1.8 windows).
  - 1m DOSC above 0 while 1m ER10 high and 15m HT_QUADRATURE above 0: down, 54% right on 2025, 5.2 windows a day (twins' best: 57%, 1.8 windows).
  - 1m DOSC above 0 while 1m ER10 high and 5m AC above 0: down, 54% right on 2025, 5.5 windows a day (twins' best: 57%, 1.8 windows).

## 3. The model call (GBM)

Shallow boosted trees fit on A only (TA: the engine's TA-Lib readings; ALL: every reading of this design). Their score at every minute in five zones at A's quantiles; each zone's direction is its own A odds. Hit B: the share of 2025 calls that went the called way among the moves beyond the dead band. Held: every minute the zone holds; onset: the minute it enters the zone.

| coin | model | minutes | zone | dir | B entries | odds B | t B | twins' odds B | held windows/day | held share right B % | onset windows/day | onset odds B | hit B | twins' hit B |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTC | ALL | 15 | very low | down | 12,940 | +6.86 | +7.9 | 0.42 (0.05 to 1.35) | 7.82 | 56.9 | 7.39 | +6.74 | 0.550 | 0.498 (0.497 to 0.499) |
| BTC | ALL | 15 | low | down | 46,293 | +4.92 | +10.2 | -0.02 (-0.17 to 0.49) | 23.69 | 55.0 |  |  | 0.550 | 0.498 (0.497 to 0.499) |
| BTC | ALL | 15 | high | up | 49,026 | +4.33 | +8.5 | -0.91 (-1.15 to 0.23) | 25.90 | 54.2 |  |  | 0.550 | 0.498 (0.497 to 0.499) |
| BTC | ALL | 15 | very high | up | 15,194 | +6.01 | +6.5 | -0.54 (-2.09 to -0.41) | 9.45 | 55.9 | 8.93 | +5.25 | 0.550 | 0.498 (0.497 to 0.499) |
| BTC | ALL | 60 | very low | down | 12,357 | +4.80 | +2.7 | 1.12 (-1.07 to 4.79) | 2.22 | 54.3 | 2.17 | +4.58 | 0.545 | 0.498 (0.492 to 0.506) |
| BTC | ALL | 60 | low | down | 46,895 | +3.85 | +4.3 | -0.54 (-1.22 to 0.22) | 7.56 | 53.3 |  |  | 0.545 | 0.498 (0.492 to 0.506) |
| BTC | ALL | 60 | high | up | 47,495 | +3.87 | +4.3 | 0.33 (-1.39 to 1.00) | 8.31 | 54.4 |  |  | 0.545 | 0.498 (0.492 to 0.506) |
| BTC | ALL | 60 | very high | up | 14,811 | +8.27 | +4.6 | -1.71 (-2.66 to 2.48) | 2.99 | 58.8 | 2.89 | +6.20 | 0.545 | 0.498 (0.492 to 0.506) |
| BTC | ALL | 240 | very low | down | 8,297 | +7.21 | +2.0 | -4.62 (-6.42 to 2.84) | 0.57 | 56.2 | 0.57 | +8.41 | 0.557 | 0.501 (0.501 to 0.510) |
| BTC | ALL | 240 | low | down | 40,754 | +5.64 | +3.2 | 1.56 (0.90 to 3.98) | 2.02 | 54.7 |  |  | 0.557 | 0.501 (0.501 to 0.510) |
| BTC | ALL | 240 | high | up | 47,822 | +4.52 | +2.8 | -0.40 (-2.54 to -0.34) | 2.75 | 55.5 |  |  | 0.557 | 0.501 (0.501 to 0.510) |
| BTC | ALL | 240 | very high | up | 17,533 | +7.38 | +2.3 | 2.50 (-1.81 to 2.85) | 1.23 | 58.3 | 1.21 | +9.37 | 0.557 | 0.501 (0.501 to 0.510) |
| BTC | TA | 15 | very low | down | 13,646 | +8.27 | +10.1 | 0.32 (-0.78 to 1.12) | 8.93 | 58.3 | 8.42 | +7.52 | 0.549 | 0.501 (0.498 to 0.503) |
| BTC | TA | 15 | low | down | 47,370 | +4.64 | +9.8 | -0.10 (-0.19 to 0.96) | 24.52 | 54.7 |  |  | 0.549 | 0.501 (0.498 to 0.503) |
| BTC | TA | 15 | high | up | 49,930 | +4.25 | +8.6 | 0.08 (-0.39 to 0.29) | 26.16 | 54.1 |  |  | 0.549 | 0.501 (0.498 to 0.503) |
| BTC | TA | 15 | very high | up | 15,141 | +4.45 | +4.5 | -0.46 (-0.77 to 0.31) | 9.56 | 54.3 | 9.08 | +4.95 | 0.549 | 0.501 (0.498 to 0.503) |
| BTC | TA | 60 | very low | down | 15,397 | +5.78 | +3.4 | 0.45 (-3.36 to 1.43) | 2.89 | 55.2 | 2.81 | +4.26 | 0.544 | 0.502 (0.496 to 0.503) |
| BTC | TA | 60 | low | down | 48,928 | +4.07 | +4.7 | 1.01 (0.35 to 1.17) | 8.26 | 53.5 |  |  | 0.544 | 0.502 (0.496 to 0.503) |
| BTC | TA | 60 | high | up | 46,947 | +3.58 | +4.2 | -0.15 (-1.20 to 1.11) | 8.31 | 54.1 |  |  | 0.544 | 0.502 (0.496 to 0.503) |
| BTC | TA | 60 | very high | up | 16,453 | +6.55 | +3.9 | -2.44 (-2.63 to -2.21) | 3.30 | 57.1 | 3.26 | +5.75 | 0.544 | 0.502 (0.496 to 0.503) |
| BTC | TA | 240 | very low | down | 10,355 | +6.47 | +1.8 | 2.12 (0.95 to 4.70) | 0.68 | 55.5 | 0.67 | +5.77 | 0.553 | 0.495 (0.484 to 0.498) |
| BTC | TA | 240 | low | down | 40,461 | +4.54 | +2.6 | 1.01 (0.56 to 1.72) | 2.12 | 53.6 |  |  | 0.553 | 0.495 (0.484 to 0.498) |
| BTC | TA | 240 | high | up | 45,595 | +3.60 | +2.2 | -2.65 (-4.24 to -1.23) | 2.61 | 54.6 |  |  | 0.553 | 0.495 (0.484 to 0.498) |
| BTC | TA | 240 | very high | up | 16,681 | +10.36 | +3.8 | -2.54 (-5.78 to -1.69) | 1.07 | 61.3 | 1.05 | +6.82 | 0.553 | 0.495 (0.484 to 0.498) |
| ETH | ALL | 15 | very low | down | 13,317 | +8.95 | +9.9 | -0.33 (-0.44 to -0.08) | 7.81 | 58.4 | 7.42 | +8.17 | 0.558 | 0.503 (0.498 to 0.507) |
| ETH | ALL | 15 | low | down | 49,884 | +5.49 | +11.5 | 0.49 (0.13 to 1.05) | 23.97 | 54.9 |  |  | 0.558 | 0.503 (0.498 to 0.507) |
| ETH | ALL | 15 | high | up | 41,030 | +4.92 | +9.0 | 0.31 (-0.31 to 0.95) | 21.10 | 55.3 |  |  | 0.558 | 0.503 (0.498 to 0.507) |
| ETH | ALL | 15 | very high | up | 10,089 | +7.39 | +6.8 | -1.57 (-1.63 to -0.51) | 6.49 | 57.8 | 6.19 | +6.61 | 0.558 | 0.503 (0.498 to 0.507) |
| ETH | ALL | 60 | very low | down | 13,726 | +5.13 | +2.8 | -1.63 (-2.79 to 2.66) | 2.17 | 53.8 | 2.10 | +5.42 | 0.553 | 0.504 (0.493 to 0.506) |
| ETH | ALL | 60 | low | down | 51,794 | +4.92 | +5.3 | -0.11 (-0.86 to 1.16) | 7.32 | 53.6 |  |  | 0.553 | 0.504 (0.493 to 0.506) |
| ETH | ALL | 60 | high | up | 38,677 | +5.38 | +5.4 | -0.25 (-0.73 to 0.53) | 7.72 | 56.6 |  |  | 0.553 | 0.504 (0.493 to 0.506) |
| ETH | ALL | 60 | very high | up | 8,669 | +10.05 | +5.4 | 2.46 (0.59 to 2.64) | 2.20 | 61.3 | 2.17 | +8.11 | 0.553 | 0.504 (0.493 to 0.506) |
| ETH | ALL | 240 | very low | down | 11,295 | +1.25 | +0.3 | 2.47 (-0.04 to 4.71) | 0.55 | 50.1 | 0.54 | +4.26 | 0.550 | 0.509 (0.487 to 0.528) |
| ETH | ALL | 240 | low | down | 53,102 | +4.85 | +2.8 | 0.44 (-0.54 to 3.29) | 2.34 | 53.6 |  |  | 0.550 | 0.509 (0.487 to 0.528) |
| ETH | ALL | 240 | high | up | 32,758 | +6.99 | +3.0 | -0.62 (-3.62 to 0.87) | 1.94 | 58.1 |  |  | 0.550 | 0.509 (0.487 to 0.528) |
| ETH | ALL | 240 | very high | up | 6,988 | +6.38 | +1.2 | 5.97 (0.33 to 12.82) | 0.58 | 57.5 | 0.58 | +10.79 | 0.550 | 0.509 (0.487 to 0.528) |
| ETH | TA | 15 | very low | down | 12,538 | +8.73 | +8.8 | 0.89 (0.86 to 1.22) | 7.06 | 58.2 | 6.75 | +9.03 | 0.560 | 0.499 (0.495 to 0.506) |
| ETH | TA | 15 | low | down | 48,380 | +5.96 | +12.3 | -0.14 (-0.22 to 0.01) | 22.72 | 55.4 |  |  | 0.560 | 0.499 (0.495 to 0.506) |
| ETH | TA | 15 | high | up | 42,866 | +5.38 | +10.2 | -0.27 (-1.01 to 0.97) | 21.08 | 55.7 |  |  | 0.560 | 0.499 (0.495 to 0.506) |
| ETH | TA | 15 | very high | up | 11,647 | +6.08 | +5.6 | -0.92 (-1.03 to 2.62) | 7.08 | 56.5 | 6.67 | +5.17 | 0.560 | 0.499 (0.495 to 0.506) |
| ETH | TA | 60 | very low | down | 13,393 | +5.83 | +3.4 | 0.63 (-1.78 to 1.01) | 2.09 | 54.5 | 2.05 | +4.99 | 0.551 | 0.500 (0.492 to 0.507) |
| ETH | TA | 60 | low | down | 47,859 | +4.75 | +4.6 | -0.06 (-0.36 to 0.43) | 7.00 | 53.4 |  |  | 0.551 | 0.500 (0.492 to 0.507) |
| ETH | TA | 60 | high | up | 41,807 | +5.14 | +5.7 | -0.99 (-1.17 to 0.94) | 8.38 | 56.4 |  |  | 0.551 | 0.500 (0.492 to 0.507) |
| ETH | TA | 60 | very high | up | 9,883 | +7.28 | +3.7 | 0.00 (-1.03 to 6.89) | 2.69 | 58.5 | 2.65 | +5.76 | 0.551 | 0.500 (0.492 to 0.507) |
| ETH | TA | 240 | very low | down | 11,137 | +1.89 | +0.4 | 1.82 (-0.20 to 1.92) | 0.55 | 50.7 | 0.55 | +1.74 | 0.544 | 0.508 (0.495 to 0.508) |
| ETH | TA | 240 | low | down | 46,613 | +4.17 | +2.3 | 1.46 (-1.46 to 2.61) | 2.10 | 53.0 |  |  | 0.544 | 0.508 (0.495 to 0.508) |
| ETH | TA | 240 | high | up | 39,239 | +4.84 | +2.5 | -0.61 (-1.84 to 0.37) | 2.21 | 56.0 |  |  | 0.544 | 0.508 (0.495 to 0.508) |
| ETH | TA | 240 | very high | up | 9,712 | +7.24 | +1.6 | -0.22 (-3.63 to 11.46) | 0.73 | 58.4 | 0.72 | +10.96 | 0.544 | 0.508 (0.495 to 0.508) |
| SOL | ALL | 15 | very low | down | 15,248 | +6.66 | +7.3 | 1.10 (-0.02 to 2.23) | 7.92 | 55.5 | 7.50 | +5.87 | 0.538 | 0.501 (0.496 to 0.505) |
| SOL | ALL | 15 | low | down | 54,395 | +3.26 | +7.1 | 0.26 (-0.88 to 0.27) | 26.59 | 52.0 |  |  | 0.538 | 0.501 (0.496 to 0.505) |
| SOL | ALL | 15 | high | up | 48,973 | +3.22 | +6.5 | -0.07 (-0.18 to 0.34) | 25.04 | 52.3 |  |  | 0.538 | 0.501 (0.496 to 0.505) |
| SOL | ALL | 15 | very high | up | 13,741 | +4.42 | +4.6 | 0.03 (-1.09 to 0.42) | 7.71 | 53.7 | 7.11 | +4.99 | 0.538 | 0.501 (0.496 to 0.505) |
| SOL | ALL | 60 | very low | down | 15,714 | +1.68 | +1.0 | -1.87 (-2.83 to -1.33) | 1.92 | 50.5 | 1.82 | +1.32 | 0.533 | 0.489 (0.487 to 0.494) |
| SOL | ALL | 60 | low | down | 50,163 | +3.42 | +3.5 | -0.81 (-0.93 to -0.42) | 6.62 | 52.2 |  |  | 0.533 | 0.489 (0.487 to 0.494) |
| SOL | ALL | 60 | high | up | 47,665 | +2.87 | +2.8 | -1.62 (-1.77 to 0.02) | 6.86 | 53.0 |  |  | 0.533 | 0.489 (0.487 to 0.494) |
| SOL | ALL | 60 | very high | up | 12,935 | +6.54 | +3.5 | -0.52 (-1.80 to 0.97) | 2.10 | 56.7 | 2.01 | +5.39 | 0.533 | 0.489 (0.487 to 0.494) |
| SOL | ALL | 240 | very low | down | 11,905 | -1.15 | -0.3 | -0.09 (-4.03 to 5.94) | 0.55 | 48.1 | 0.54 | +3.42 | 0.520 | 0.499 (0.497 to 0.514) |
| SOL | ALL | 240 | low | down | 42,034 | +4.58 | +2.6 | 0.15 (-0.33 to 1.18) | 1.86 | 53.8 |  |  | 0.520 | 0.499 (0.497 to 0.514) |
| SOL | ALL | 240 | high | up | 45,446 | -0.37 | -0.2 | -1.52 (-2.19 to 1.38) | 2.03 | 49.9 |  |  | 0.520 | 0.499 (0.497 to 0.514) |
| SOL | ALL | 240 | very high | up | 13,324 | +4.22 | +1.1 | 1.20 (1.02 to 7.10) | 0.57 | 54.4 | 0.52 | +2.83 | 0.520 | 0.499 (0.497 to 0.514) |
| SOL | TA | 15 | very low | down | 12,591 | +6.25 | +6.2 | 0.91 (0.61 to 2.06) | 6.06 | 55.2 | 5.64 | +6.33 | 0.541 | 0.500 (0.498 to 0.505) |
| SOL | TA | 15 | low | down | 47,311 | +4.04 | +8.5 | 0.39 (-0.55 to 0.62) | 24.30 | 52.8 |  |  | 0.541 | 0.500 (0.498 to 0.505) |
| SOL | TA | 15 | high | up | 49,438 | +3.41 | +6.5 | -0.40 (-0.49 to -0.09) | 24.21 | 52.5 |  |  | 0.541 | 0.500 (0.498 to 0.505) |
| SOL | TA | 15 | very high | up | 12,505 | +4.10 | +4.2 | 1.12 (-1.04 to 1.51) | 6.45 | 53.4 | 5.96 | +4.91 | 0.541 | 0.500 (0.498 to 0.505) |
| SOL | TA | 60 | very low | down | 13,340 | +2.65 | +1.4 | -0.39 (-2.82 to 2.18) | 1.66 | 51.5 | 1.58 | +3.58 | 0.530 | 0.495 (0.478 to 0.498) |
| SOL | TA | 60 | low | down | 51,169 | +2.69 | +2.8 | -0.46 (-2.36 to 0.41) | 6.12 | 51.4 |  |  | 0.530 | 0.495 (0.478 to 0.498) |
| SOL | TA | 60 | high | up | 47,640 | +2.37 | +2.4 | -0.29 (-3.90 to -0.08) | 6.17 | 52.5 |  |  | 0.530 | 0.495 (0.478 to 0.498) |
| SOL | TA | 60 | very high | up | 13,484 | +6.31 | +2.9 | 0.23 (-4.88 to 2.30) | 1.97 | 56.5 | 1.89 | +6.01 | 0.530 | 0.495 (0.478 to 0.498) |
| SOL | TA | 240 | very low | down | 12,069 | -2.32 | -0.7 | -0.27 (-2.32 to -0.18) | 0.55 | 47.0 | 0.54 | +0.69 | 0.513 | 0.498 (0.495 to 0.498) |
| SOL | TA | 240 | low | down | 47,442 | +2.54 | +1.5 | 1.75 (-4.01 to 2.17) | 1.99 | 51.8 |  |  | 0.513 | 0.498 (0.495 to 0.498) |
| SOL | TA | 240 | high | up | 46,010 | +0.36 | +0.2 | -0.30 (-2.24 to 1.05) | 1.86 | 50.6 |  |  | 0.513 | 0.498 (0.495 to 0.498) |
| SOL | TA | 240 | very high | up | 13,729 | +3.04 | +0.8 | -0.41 (-4.70 to 3.43) | 0.60 | 53.2 | 0.55 | +4.24 | 0.513 | 0.498 (0.495 to 0.498) |
| XRP | ALL | 15 | very low | down | 13,292 | +6.25 | +5.8 | 1.58 (0.56 to 2.14) | 6.59 | 55.5 | 6.11 | +7.41 | 0.544 | 0.507 (0.500 to 0.510) |
| XRP | ALL | 15 | low | down | 46,546 | +4.60 | +8.5 | 0.80 (0.19 to 1.05) | 20.89 | 53.8 |  |  | 0.544 | 0.507 (0.500 to 0.510) |
| XRP | ALL | 15 | high | up | 50,568 | +2.79 | +5.5 | -0.12 (-0.39 to 0.90) | 24.36 | 51.9 |  |  | 0.544 | 0.507 (0.500 to 0.510) |
| XRP | ALL | 15 | very high | up | 13,350 | +7.52 | +8.9 | 0.27 (-0.36 to 1.85) | 8.16 | 56.8 | 7.69 | +4.27 | 0.544 | 0.507 (0.500 to 0.510) |
| XRP | ALL | 60 | very low | down | 12,102 | +5.22 | +2.9 | 1.85 (-0.65 to 2.63) | 2.17 | 54.9 | 2.10 | +6.00 | 0.542 | 0.510 (0.496 to 0.510) |
| XRP | ALL | 60 | low | down | 45,818 | +3.92 | +4.1 | 0.70 (-0.78 to 2.03) | 6.68 | 53.5 |  |  | 0.542 | 0.510 (0.496 to 0.510) |
| XRP | ALL | 60 | high | up | 48,007 | +3.25 | +3.4 | 0.10 (-0.90 to 0.46) | 7.31 | 52.8 |  |  | 0.542 | 0.510 (0.496 to 0.510) |
| XRP | ALL | 60 | very high | up | 16,397 | +7.10 | +4.7 | 0.50 (-0.40 to 3.76) | 2.45 | 56.7 | 2.34 | +4.21 | 0.542 | 0.510 (0.496 to 0.510) |
| XRP | ALL | 240 | very low | down | 13,623 | +6.89 | +2.4 | 1.75 (-0.24 to 3.18) | 0.79 | 56.7 | 0.77 | +3.56 | 0.535 | 0.500 (0.493 to 0.519) |
| XRP | ALL | 240 | low | down | 48,371 | +1.94 | +1.2 | 0.31 (-1.48 to 1.38) | 2.17 | 51.8 |  |  | 0.535 | 0.500 (0.493 to 0.519) |
| XRP | ALL | 240 | high | up | 43,187 | +5.03 | +2.8 | 2.37 (-1.91 to 3.28) | 2.15 | 54.7 |  |  | 0.535 | 0.500 (0.493 to 0.519) |
| XRP | ALL | 240 | very high | up | 9,317 | -0.58 | -0.2 | -0.96 (-4.79 to -0.55) | 0.59 | 49.1 | 0.58 | +7.53 | 0.535 | 0.500 (0.493 to 0.519) |
| XRP | TA | 15 | very low | down | 13,262 | +6.46 | +6.2 | 1.03 (0.30 to 2.18) | 7.15 | 55.7 | 6.76 | +6.43 | 0.548 | 0.505 (0.500 to 0.506) |
| XRP | TA | 15 | low | down | 48,184 | +4.68 | +8.9 | 0.49 (-0.09 to 0.65) | 22.16 | 53.9 |  |  | 0.548 | 0.505 (0.500 to 0.506) |
| XRP | TA | 15 | high | up | 49,614 | +3.62 | +7.5 | 0.34 (-0.30 to 0.36) | 24.95 | 52.7 |  |  | 0.548 | 0.505 (0.500 to 0.506) |
| XRP | TA | 15 | very high | up | 11,651 | +7.14 | +7.6 | 1.45 (-0.97 to 1.96) | 7.78 | 56.4 | 7.41 | +5.45 | 0.548 | 0.505 (0.500 to 0.506) |
| XRP | TA | 60 | very low | down | 14,665 | +5.01 | +2.9 | 1.10 (-0.47 to 1.35) | 2.44 | 54.7 | 2.34 | +6.39 | 0.544 | 0.507 (0.501 to 0.509) |
| XRP | TA | 60 | low | down | 46,900 | +4.20 | +4.6 | 0.74 (0.58 to 1.31) | 7.05 | 53.8 |  |  | 0.544 | 0.507 (0.501 to 0.509) |
| XRP | TA | 60 | high | up | 51,587 | +3.48 | +3.9 | 0.32 (-0.17 to 0.61) | 7.56 | 53.0 |  |  | 0.544 | 0.507 (0.501 to 0.509) |
| XRP | TA | 60 | very high | up | 16,915 | +7.22 | +4.4 | 0.37 (-3.04 to 1.76) | 2.57 | 56.8 | 2.44 | +4.62 | 0.544 | 0.507 (0.501 to 0.509) |
| XRP | TA | 240 | very low | down | 12,593 | +8.34 | +2.9 | 0.19 (-3.91 to 7.65) | 0.75 | 58.2 | 0.75 | -0.82 | 0.541 | 0.498 (0.489 to 0.510) |
| XRP | TA | 240 | low | down | 44,543 | +1.26 | +0.7 | -0.84 (-1.03 to 0.53) | 2.03 | 51.1 |  |  | 0.541 | 0.498 (0.489 to 0.510) |
| XRP | TA | 240 | high | up | 46,728 | +5.24 | +3.3 | -0.45 (-1.77 to 2.08) | 2.19 | 54.9 |  |  | 0.541 | 0.498 (0.489 to 0.510) |
| XRP | TA | 240 | very high | up | 11,683 | +5.31 | +1.5 | 0.06 (-0.14 to 1.17) | 0.64 | 55.1 | 0.62 | +13.44 | 0.541 | 0.498 (0.489 to 0.510) |

Baselines. Last candle faded: bet against the decision minute's candle (what bid-ask bounce alone gives; a coin-flip twin cannot rule it out). Best single: HM1's best event level by heat at that horizon, and the best by odds among levels firing half to twice as often as the ALL model's extreme zones (matched windows per day).

| coin | minutes | last candle faded odds B | windows/day | twins | best single | odds B | windows/day | matched single | odds B | windows/day |
|---|---|---|---|---|---|---|---|---|---|---|
| BTC | 15 | +0.24 | 192.0 | 0.01 (-0.05 to 0.04) | 1m:AROONdn14=very high | +2.12 | 58.38 | 1m:TSI=very low | +8.85 | 4.55 |
| BTC | 60 | +0.25 | 48.0 | -0.05 (-0.09 to 0.04) | 1m:DONCHIAN20pos=low (falling in) | +2.38 | 20.88 | 15m:PERCENTRANK100=low (falling in) | +7.98 | 2.01 |
| BTC | 240 | +0.20 | 12.0 | 0.03 (0.02 to 0.06) |  |  |  |  |  |  |
| ETH | 15 | +0.45 | 192.0 | 0.03 (-0.02 to 0.11) | 1m:AROONup14=very high | +2.78 | 58.61 | 15m:C-SWAK_BUTTER20=high (rising in) | +10.08 | 3.69 |
| ETH | 60 | +0.45 | 48.0 | 0.02 (-0.03 to 0.06) | 1m:AROONup25=very high | +3.09 | 21.14 | 60m:C-ALMA9=low (falling in) | +8.84 | 1.18 |
| ETH | 240 | +0.15 | 12.0 | -0.03 (-0.17 to 0.05) |  |  |  |  |  |  |
| SOL | 15 | +0.31 | 192.0 | -0.08 (-0.13 to 0.09) | 1m:AROONup25=very high | +3.00 | 43.92 | 60m:SWAK_2PHP20 sign=above 0 | +6.60 | 4.66 |
| SOL | 60 | +0.23 | 48.0 | -0.08 (-0.10 to 0.00) | 1m:TakerBuy=low (falling in) | +2.17 | 20.29 | 15m:C-SUPERTREND10/3=very high | +7.07 | 1.41 |
| SOL | 240 | +0.21 | 12.0 | 0.01 (-0.04 to 0.02) |  |  |  |  |  |  |
| XRP | 15 | +0.29 | 192.0 | -0.03 (-0.12 to 0.06) | 1m:AROONdn14=very high | +2.03 | 59.24 | 5m:DONCHIAN55pos=low (recovering) | +7.18 | 4.20 |
| XRP | 60 | +0.32 | 48.0 | -0.01 (-0.04 to 0.05) | 1m:C-SUPERTREND10/3=very low | +3.16 | 14.80 | 5m:PVI=very low | +10.63 | 1.16 |
| XRP | 240 | +0.31 | 12.0 | -0.00 (-0.01 to 0.11) |  |  |  |  |  |  |

ALL against TA (what cross-referencing the other data adds to the call):

| coin | minutes | hit B ALL | hit B TA | ALL - TA | extreme zones odds B ALL | TA |
|---|---|---|---|---|---|---|
| BTC | 1 | 0.564 | 0.549 | +0.015 | +9.13 | +6.30 |
| BTC | 5 | 0.547 | 0.545 | +0.002 | +6.57 | +6.42 |
| BTC | 15 | 0.550 | 0.549 | +0.002 | +6.43 | +6.36 |
| BTC | 60 | 0.545 | 0.544 | +0.001 | +6.54 | +6.16 |
| BTC | 240 | 0.557 | 0.553 | +0.004 | +7.29 | +8.42 |
| ETH | 1 | 0.543 | 0.537 | +0.006 | +7.12 | +6.47 |
| ETH | 5 | 0.554 | 0.555 | -0.001 | +8.02 | +7.30 |
| ETH | 15 | 0.558 | 0.560 | -0.002 | +8.17 | +7.41 |
| ETH | 60 | 0.553 | 0.551 | +0.002 | +7.59 | +6.56 |
| ETH | 240 | 0.550 | 0.544 | +0.006 | +3.81 | +4.56 |
| SOL | 1 | 0.519 | 0.515 | +0.005 | +4.27 | +2.12 |
| SOL | 5 | 0.531 | 0.530 | +0.001 | +3.73 | +3.88 |
| SOL | 15 | 0.538 | 0.541 | -0.003 | +5.54 | +5.18 |
| SOL | 60 | 0.533 | 0.530 | +0.004 | +4.11 | +4.48 |
| SOL | 240 | 0.520 | 0.513 | +0.007 | +1.54 | +0.36 |
| XRP | 1 | 0.532 | 0.530 | +0.002 | +4.99 | +4.82 |
| XRP | 5 | 0.544 | 0.542 | +0.001 | +7.21 | +6.74 |
| XRP | 15 | 0.544 | 0.548 | -0.003 | +6.88 | +6.80 |
| XRP | 60 | 0.542 | 0.544 | -0.002 | +6.16 | +6.11 |
| XRP | 240 | 0.535 | 0.541 | -0.005 | +3.16 | +6.82 |

## 4. Lessons: how to use TA-Lib for direction

### Family table

Per pair of data families: confluence cells with a sample and the share whose interaction (iota_robust) kept its sign on 2025, minus the twins' median share. A positive gap that stands clear of the twins' range is evidence that the two families together say more than each alone.

| minutes | families | cells | kept iota_robust | twins | minus twins |
|---|---|---|---|---|---|
| 15 | dist x osc | 3,411,459 | 0.566 | 0.501 (0.501 to 0.504) | +0.064 |
| 15 | osc x osc | 2,253,484 | 0.554 | 0.499 (0.498 to 0.503) | +0.055 |
| 15 | atr x osc | 1,951,346 | 0.551 | 0.501 (0.501 to 0.503) | +0.050 |
| 15 | atr x dist | 1,461,445 | 0.549 | 0.502 (0.502 to 0.504) | +0.047 |
| 15 | dist x dist | 1,254,375 | 0.560 | 0.503 (0.500 to 0.507) | +0.057 |
| 15 | osc x pattern | 701,553 | 0.531 | 0.500 (0.498 to 0.500) | +0.031 |
| 15 | cum x osc | 667,941 | 0.544 | 0.501 (0.500 to 0.501) | +0.043 |
| 15 | osc x state | 663,844 | 0.560 | 0.506 (0.502 to 0.506) | +0.054 |
| 15 | osc x pct | 574,343 | 0.544 | 0.502 (0.499 to 0.504) | +0.042 |
| 15 | dist x pattern | 558,534 | 0.541 | 0.497 (0.496 to 0.502) | +0.043 |
| 15 | cum x dist | 504,973 | 0.543 | 0.498 (0.498 to 0.506) | +0.044 |
| 15 | osc x z | 487,596 | 0.556 | 0.500 (0.497 to 0.501) | +0.056 |
| 15 | dist x state | 485,675 | 0.545 | 0.508 (0.506 to 0.510) | +0.037 |
| 15 | dist x pct | 435,602 | 0.551 | 0.504 (0.503 to 0.506) | +0.047 |
| 15 | cross x osc | 430,010 | 0.544 | 0.497 (0.494 to 0.501) | +0.048 |
| 15 | atr x atr | 413,547 | 0.542 | 0.504 (0.502 to 0.504) | +0.038 |
| 15 | dist x z | 366,648 | 0.559 | 0.500 (0.497 to 0.500) | +0.059 |
| 15 | osc x regime | 340,792 | 0.563 | 0.499 (0.492 to 0.504) | +0.064 |
| 15 | cross x dist | 315,355 | 0.547 | 0.502 (0.490 to 0.502) | +0.045 |
| 15 | atr x pattern | 315,227 | 0.536 | 0.497 (0.497 to 0.503) | +0.038 |
| 15 | clock x osc | 289,711 | 0.526 | 0.502 (0.502 to 0.503) | +0.024 |
| 15 | atr x cum | 285,826 | 0.535 | 0.502 (0.500 to 0.507) | +0.033 |
| 15 | atr x state | 275,823 | 0.547 | 0.509 (0.504 to 0.510) | +0.038 |
| 15 | dist x regime | 266,330 | 0.608 | 0.497 (0.489 to 0.506) | +0.111 |
| 15 | atr x pct | 248,770 | 0.538 | 0.502 (0.501 to 0.504) | +0.036 |
| 15 | clock x dist | 228,383 | 0.547 | 0.508 (0.508 to 0.509) | +0.039 |
| 15 | dmkt x osc | 223,337 | 0.515 | 0.495 (0.495 to 0.499) | +0.019 |
| 15 | atr x z | 208,256 | 0.550 | 0.502 (0.501 to 0.502) | +0.048 |
| 15 | atr x cross | 179,581 | 0.541 | 0.500 (0.495 to 0.501) | +0.041 |
| 15 | osc x vol | 172,976 | 0.536 | 0.499 (0.498 to 0.500) | +0.038 |
| 15 | dist x dmkt | 172,023 | 0.517 | 0.493 (0.492 to 0.495) | +0.023 |
| 15 | atr x regime | 148,313 | 0.582 | 0.493 (0.492 to 0.508) | +0.089 |
| 15 | dist x vol | 132,496 | 0.531 | 0.498 (0.493 to 0.499) | +0.033 |
| 15 | atr x clock | 126,507 | 0.530 | 0.505 (0.505 to 0.506) | +0.024 |
| 15 | pattern x state | 119,792 | 0.540 | 0.502 (0.498 to 0.503) | +0.038 |
| 15 | flow x osc | 117,097 | 0.550 | 0.496 (0.495 to 0.504) | +0.054 |
| 15 | cum x pattern | 107,736 | 0.535 | 0.497 (0.497 to 0.504) | +0.037 |
| 15 | context x osc | 107,694 | 0.528 | 0.496 (0.494 to 0.498) | +0.032 |
| 15 | osc x position | 103,914 | 0.530 | 0.503 (0.495 to 0.504) | +0.027 |
| 15 | atr x dmkt | 96,864 | 0.516 | 0.495 (0.492 to 0.498) | +0.021 |
| 15 | cum x state | 94,626 | 0.533 | 0.507 (0.503 to 0.511) | +0.026 |
| 15 | pattern x pct | 93,823 | 0.527 | 0.500 (0.497 to 0.501) | +0.027 |
| 15 | dist x flow | 86,478 | 0.560 | 0.504 (0.493 to 0.505) | +0.056 |
| 15 | cum x pct | 84,638 | 0.531 | 0.505 (0.501 to 0.508) | +0.026 |
| 15 | pct x state | 83,662 | 0.538 | 0.507 (0.502 to 0.515) | +0.031 |
| 15 | context x dist | 81,642 | 0.538 | 0.500 (0.488 to 0.508) | +0.038 |
| 15 | pattern x z | 77,296 | 0.533 | 0.500 (0.499 to 0.501) | +0.033 |
| 15 | dist x position | 75,768 | 0.560 | 0.501 (0.495 to 0.503) | +0.059 |
| 15 | atr x vol | 74,972 | 0.521 | 0.500 (0.498 to 0.500) | +0.021 |
| 15 | cum x z | 71,548 | 0.544 | 0.498 (0.498 to 0.504) | +0.046 |
| 15 | state x z | 68,667 | 0.557 | 0.500 (0.500 to 0.500) | +0.057 |
| 15 | cross x pattern | 63,994 | 0.518 | 0.499 (0.493 to 0.500) | +0.020 |
| 15 | pct x z | 61,973 | 0.548 | 0.501 (0.500 to 0.502) | +0.048 |
| 15 | cross x cum | 61,763 | 0.532 | 0.495 (0.494 to 0.497) | +0.037 |
| 15 | osc x perp | 61,225 | 0.527 | 0.500 (0.494 to 0.509) | +0.027 |
| 15 | cross x state | 56,090 | 0.556 | 0.495 (0.493 to 0.498) | +0.061 |
| 15 | cross x pct | 55,347 | 0.545 | 0.499 (0.499 to 0.500) | +0.045 |
| 15 | oi x osc | 53,514 | 0.546 | 0.504 (0.502 to 0.505) | +0.042 |
| 15 | regime x state | 52,404 | 0.580 | 0.492 (0.486 to 0.510) | +0.087 |
| 15 | dist x perp | 50,750 | 0.543 | 0.510 (0.492 to 0.512) | +0.033 |
| 15 | pattern x regime | 50,265 | 0.526 | 0.498 (0.493 to 0.503) | +0.028 |
| 15 | atr x flow | 49,796 | 0.545 | 0.498 (0.495 to 0.506) | +0.047 |
| 15 | cum x regime | 48,136 | 0.577 | 0.494 (0.493 to 0.503) | +0.083 |
| 15 | cum x cum | 47,159 | 0.519 | 0.502 (0.488 to 0.504) | +0.016 |
| 15 | atr x context | 45,832 | 0.527 | 0.500 (0.489 to 0.506) | +0.027 |
| 15 | clock x state | 45,700 | 0.537 | 0.500 (0.499 to 0.513) | +0.036 |
| 15 | pattern x pattern | 45,083 | 0.516 | 0.499 (0.495 to 0.503) | +0.017 |
| 15 | cross x z | 44,362 | 0.545 | 0.497 (0.492 to 0.499) | +0.048 |
| 15 | state x state | 42,887 | 0.530 | 0.504 (0.503 to 0.532) | +0.026 |
| 15 | atr x position | 42,724 | 0.544 | 0.502 (0.499 to 0.502) | +0.043 |
| 15 | pct x regime | 42,476 | 0.568 | 0.495 (0.488 to 0.498) | +0.073 |
| 15 | clock x cum | 41,007 | 0.538 | 0.511 (0.505 to 0.511) | +0.028 |
| 15 | dist x oi | 40,262 | 0.557 | 0.507 (0.501 to 0.516) | +0.050 |
| 15 | clock x pattern | 39,486 | 0.505 | 0.501 (0.498 to 0.506) | +0.004 |
| 15 | dmkt x pattern | 39,042 | 0.494 | 0.503 (0.501 to 0.504) | -0.009 |
| 15 | clock x pct | 36,796 | 0.531 | 0.505 (0.498 to 0.507) | +0.026 |
| 15 | regime x z | 35,333 | 0.584 | 0.503 (0.501 to 0.506) | +0.081 |
| 15 | pct x pct | 35,326 | 0.529 | 0.502 (0.498 to 0.506) | +0.027 |
| 15 | dmkt x state | 32,863 | 0.518 | 0.488 (0.486 to 0.498) | +0.030 |
| 15 | cross x regime | 32,347 | 0.551 | 0.498 (0.497 to 0.498) | +0.053 |
| 15 | cum x dmkt | 31,427 | 0.514 | 0.499 (0.496 to 0.503) | +0.015 |
| 15 | clock x z | 30,410 | 0.527 | 0.504 (0.503 to 0.508) | +0.023 |
| 15 | clock x cross | 29,728 | 0.515 | 0.499 (0.495 to 0.506) | +0.016 |
| 15 | atr x perp | 27,392 | 0.531 | 0.500 (0.490 to 0.501) | +0.031 |
| 15 | dmkt x pct | 26,781 | 0.511 | 0.489 (0.488 to 0.491) | +0.022 |
| 15 | pattern x vol | 26,487 | 0.527 | 0.501 (0.496 to 0.504) | +0.026 |
| 15 | state x vol | 26,158 | 0.526 | 0.497 (0.495 to 0.500) | +0.029 |
| 15 | cum x vol | 24,876 | 0.511 | 0.495 (0.491 to 0.499) | +0.016 |
| 15 | z x z | 24,785 | 0.562 | 0.500 (0.498 to 0.503) | +0.061 |
| 15 | dmkt x z | 23,185 | 0.511 | 0.500 (0.492 to 0.503) | +0.011 |
| 15 | atr x oi | 22,519 | 0.547 | 0.504 (0.501 to 0.508) | +0.042 |
| 15 | pct x vol | 21,686 | 0.518 | 0.505 (0.505 to 0.506) | +0.013 |
| 15 | cross x dmkt | 21,194 | 0.508 | 0.492 (0.492 to 0.504) | +0.017 |
| 15 | context x pattern | 18,573 | 0.506 | 0.506 (0.499 to 0.506) | +0.000 |
| 15 | vol x z | 18,313 | 0.526 | 0.493 (0.491 to 0.502) | +0.033 |
| 15 | pattern x position | 17,641 | 0.515 | 0.501 (0.495 to 0.503) | +0.014 |
| 15 | flow x pattern | 17,624 | 0.528 | 0.502 (0.492 to 0.507) | +0.026 |
| 15 | clock x regime | 17,137 | 0.503 | 0.500 (0.496 to 0.514) | +0.003 |
| 15 | cum x flow | 16,900 | 0.540 | 0.499 (0.494 to 0.503) | +0.041 |
| 15 | flow x state | 16,378 | 0.551 | 0.508 (0.495 to 0.508) | +0.043 |
| 15 | clock x dmkt | 16,324 | 0.501 | 0.496 (0.491 to 0.500) | +0.004 |
| 15 | cross x vol | 15,953 | 0.531 | 0.494 (0.493 to 0.503) | +0.037 |
| 15 | cross x cross | 15,700 | 0.540 | 0.499 (0.496 to 0.501) | +0.041 |
| 15 | flow x pct | 15,203 | 0.548 | 0.503 (0.497 to 0.504) | +0.045 |
| 15 | context x state | 15,092 | 0.531 | 0.486 (0.485 to 0.513) | +0.045 |
| 15 | context x cum | 15,021 | 0.519 | 0.501 (0.488 to 0.511) | +0.018 |
| 15 | cum x position | 14,608 | 0.543 | 0.501 (0.491 to 0.503) | +0.042 |
| 15 | dmkt x regime | 14,163 | 0.481 | 0.494 (0.486 to 0.509) | -0.012 |
| 15 | pct x position | 13,200 | 0.529 | 0.504 (0.500 to 0.508) | +0.025 |
| 15 | position x state | 13,024 | 0.550 | 0.492 (0.491 to 0.525) | +0.058 |
| 15 | context x pct | 13,017 | 0.520 | 0.495 (0.482 to 0.507) | +0.026 |
| 15 | regime x vol | 12,433 | 0.557 | 0.497 (0.487 to 0.507) | +0.060 |
| 15 | flow x z | 12,210 | 0.558 | 0.495 (0.494 to 0.511) | +0.063 |
| 15 | context x z | 11,079 | 0.513 | 0.507 (0.491 to 0.515) | +0.006 |
| 15 | position x z | 10,560 | 0.533 | 0.495 (0.494 to 0.507) | +0.038 |
| 15 | clock x vol | 10,339 | 0.522 | 0.502 (0.501 to 0.505) | +0.021 |
| 15 | regime x regime | 10,233 | 0.507 | 0.498 (0.491 to 0.507) | +0.009 |
| 15 | perp x state | 9,887 | 0.540 | 0.512 (0.510 to 0.518) | +0.028 |
| 15 | context x cross | 9,849 | 0.504 | 0.505 (0.498 to 0.514) | -0.001 |
| 15 | cross x flow | 9,793 | 0.536 | 0.491 (0.489 to 0.505) | +0.045 |
| 15 | cum x perp | 9,712 | 0.543 | 0.499 (0.496 to 0.505) | +0.044 |
| 15 | flow x regime | 8,475 | 0.545 | 0.494 (0.490 to 0.506) | +0.051 |
| 15 | cross x position | 8,340 | 0.521 | 0.497 (0.496 to 0.508) | +0.024 |
| 15 | clock x flow | 8,123 | 0.505 | 0.505 (0.503 to 0.508) | +0.000 |
| 15 | position x regime | 8,096 | 0.500 | 0.508 (0.501 to 0.512) | -0.008 |
| 15 | dmkt x vol | 8,004 | 0.502 | 0.491 (0.479 to 0.506) | +0.012 |
| 15 | pct x perp | 7,890 | 0.529 | 0.508 (0.498 to 0.512) | +0.021 |
| 15 | cum x oi | 7,701 | 0.548 | 0.508 (0.504 to 0.510) | +0.040 |
| 15 | dist x macro | 7,676 | 0.515 | 0.504 (0.453 to 0.527) | +0.011 |
| 15 | oi x pattern | 7,632 | 0.525 | 0.501 (0.498 to 0.508) | +0.024 |
| 15 | macro x osc | 7,559 | 0.520 | 0.502 (0.486 to 0.513) | +0.018 |
| 15 | pattern x perp | 7,465 | 0.513 | 0.493 (0.492 to 0.494) | +0.020 |
| 15 | context x regime | 7,151 | 0.493 | 0.496 (0.495 to 0.512) | -0.003 |
| 15 | oi x state | 7,078 | 0.554 | 0.503 (0.490 to 0.517) | +0.051 |
| 15 | perp x z | 6,952 | 0.539 | 0.508 (0.500 to 0.510) | +0.030 |
| 15 | oi x pct | 6,749 | 0.531 | 0.502 (0.489 to 0.506) | +0.029 |
| 15 | clock x position | 6,568 | 0.498 | 0.502 (0.500 to 0.504) | -0.004 |
| 15 | clock x context | 6,376 | 0.489 | 0.489 (0.487 to 0.491) | +0.000 |
| 15 | dmkt x flow | 5,893 | 0.490 | 0.507 (0.481 to 0.508) | -0.017 |
| 15 | oi x z | 5,541 | 0.541 | 0.503 (0.498 to 0.513) | +0.038 |
| 15 | cross x perp | 5,520 | 0.544 | 0.503 (0.486 to 0.510) | +0.040 |
| 15 | dmkt x position | 5,104 | 0.490 | 0.495 (0.488 to 0.500) | -0.005 |
| 15 | cross x oi | 4,529 | 0.515 | 0.505 (0.486 to 0.518) | +0.010 |
| 15 | flow x vol | 4,326 | 0.531 | 0.495 (0.481 to 0.509) | +0.036 |
| 15 | perp x regime | 4,232 | 0.542 | 0.498 (0.479 to 0.503) | +0.044 |
| 15 | atr x macro | 4,138 | 0.522 | 0.505 (0.467 to 0.510) | +0.018 |
| 15 | position x vol | 4,032 | 0.540 | 0.495 (0.485 to 0.505) | +0.045 |
| 15 | context x vol | 3,934 | 0.524 | 0.502 (0.494 to 0.510) | +0.022 |
| 15 | oi x regime | 3,676 | 0.530 | 0.514 (0.512 to 0.524) | +0.016 |
| 15 | context x dmkt | 3,320 | 0.530 | 0.484 (0.483 to 0.508) | +0.045 |
| 15 | clock x oi | 3,220 | 0.512 | 0.508 (0.498 to 0.514) | +0.004 |
| 15 | vol x vol | 2,966 | 0.522 | 0.492 (0.483 to 0.502) | +0.030 |
| 15 | dmkt x perp | 2,922 | 0.486 | 0.495 (0.479 to 0.502) | -0.009 |
| 15 | context x flow | 2,815 | 0.504 | 0.508 (0.507 to 0.515) | -0.004 |
| 15 | dmkt x dmkt | 2,560 | 0.497 | 0.490 (0.483 to 0.493) | +0.007 |
| 15 | dmkt x oi | 2,487 | 0.517 | 0.506 (0.497 to 0.514) | +0.011 |
| 15 | flow x position | 2,464 | 0.511 | 0.499 (0.495 to 0.500) | +0.012 |
| 15 | clock x perp | 2,410 | 0.525 | 0.484 (0.478 to 0.526) | +0.041 |
| 15 | clock x clock | 2,400 | 0.511 | 0.520 (0.514 to 0.529) | -0.009 |
| 15 | perp x vol | 2,364 | 0.546 | 0.501 (0.476 to 0.521) | +0.045 |
| 15 | context x position | 2,288 | 0.480 | 0.499 (0.473 to 0.503) | -0.018 |
| 15 | oi x vol | 1,952 | 0.523 | 0.513 (0.486 to 0.513) | +0.011 |
| 15 | macro x state | 1,900 | 0.564 | 0.472 (0.454 to 0.533) | +0.092 |
| 15 | flow x perp | 1,525 | 0.531 | 0.487 (0.479 to 0.495) | +0.045 |
| 15 | cum x macro | 1,418 | 0.480 | 0.495 (0.488 to 0.502) | -0.015 |
| 15 | context x perp | 1,395 | 0.502 | 0.501 (0.484 to 0.517) | +0.001 |
| 15 | flow x oi | 1,243 | 0.569 | 0.501 (0.499 to 0.518) | +0.068 |
| 15 | perp x position | 1,226 | 0.497 | 0.484 (0.479 to 0.488) | +0.013 |
| 15 | context x oi | 1,209 | 0.497 | 0.521 (0.467 to 0.529) | -0.025 |
| 15 | cross x macro | 1,200 | 0.531 | 0.513 (0.507 to 0.522) | +0.018 |
| 15 | macro x pattern | 1,185 | 0.483 | 0.493 (0.481 to 0.494) | -0.011 |
| 15 | flow x flow | 1,162 | 0.532 | 0.489 (0.486 to 0.494) | +0.043 |
| 15 | macro x z | 1,093 | 0.474 | 0.505 (0.495 to 0.524) | -0.031 |
| 15 | oi x position | 1,056 | 0.515 | 0.532 (0.496 to 0.539) | -0.018 |
| 15 | macro x pct | 938 | 0.500 | 0.499 (0.464 to 0.534) | +0.001 |
| 15 | context x context | 748 | 0.502 | 0.503 (0.498 to 0.521) | -0.001 |
| 15 | oi x perp | 703 | 0.494 | 0.504 (0.484 to 0.550) | -0.011 |
| 15 | macro x regime | 389 | 0.488 | 0.532 (0.519 to 0.538) | -0.044 |
| 15 | clock x macro | 364 | 0.476 | 0.525 (0.489 to 0.539) | -0.049 |
| 15 | macro x position | 364 | 0.547 | 0.510 (0.474 to 0.539) | +0.037 |
| 15 | position x position | 348 | 0.531 | 0.470 (0.442 to 0.483) | +0.061 |
| 15 | perp x perp | 347 | 0.499 | 0.527 (0.496 to 0.534) | -0.028 |
| 15 | macro x vol | 264 | 0.517 | 0.480 (0.426 to 0.508) | +0.037 |
| 15 | flow x macro | 243 | 0.481 | 0.489 (0.472 to 0.493) | -0.008 |
| 15 | oi x oi | 151 | 0.642 | 0.464 (0.437 to 0.523) | +0.179 |
| 15 | dmkt x macro | 128 | 0.523 | 0.508 (0.445 to 0.602) | +0.016 |
| 15 | macro x perp | 102 | 0.464 | 0.490 (0.430 to 0.543) | -0.026 |
| 15 | macro x oi | 92 | 0.413 | 0.545 (0.540 to 0.553) | -0.133 |
| 15 | context x macro | 72 | 0.387 | 0.492 (0.484 to 0.569) | -0.105 |
| 15 | macro x macro | 16 | 1.000 | 0.250 (0.250 to 0.500) | +0.750 |
| 60 | dist x osc | 3,411,459 | 0.543 | 0.496 (0.496 to 0.502) | +0.047 |
| 60 | osc x osc | 2,253,484 | 0.539 | 0.497 (0.496 to 0.502) | +0.043 |
| 60 | atr x osc | 1,951,346 | 0.536 | 0.497 (0.496 to 0.501) | +0.038 |
| 60 | atr x dist | 1,461,445 | 0.527 | 0.496 (0.493 to 0.501) | +0.031 |
| 60 | dist x dist | 1,254,375 | 0.531 | 0.493 (0.491 to 0.501) | +0.037 |
| 60 | osc x pattern | 701,553 | 0.515 | 0.500 (0.499 to 0.502) | +0.015 |
| 60 | cum x osc | 667,941 | 0.535 | 0.498 (0.496 to 0.509) | +0.037 |
| 60 | osc x state | 663,844 | 0.541 | 0.498 (0.496 to 0.503) | +0.043 |
| 60 | osc x pct | 574,343 | 0.532 | 0.500 (0.495 to 0.503) | +0.032 |
| 60 | dist x pattern | 558,534 | 0.518 | 0.500 (0.498 to 0.504) | +0.018 |
| 60 | cum x dist | 504,973 | 0.527 | 0.496 (0.495 to 0.509) | +0.030 |
| 60 | osc x z | 487,596 | 0.543 | 0.500 (0.497 to 0.500) | +0.043 |
| 60 | dist x state | 485,675 | 0.519 | 0.497 (0.492 to 0.498) | +0.022 |
| 60 | dist x pct | 435,602 | 0.528 | 0.502 (0.493 to 0.507) | +0.026 |
| 60 | cross x osc | 430,010 | 0.534 | 0.499 (0.499 to 0.502) | +0.035 |
| 60 | atr x atr | 413,547 | 0.523 | 0.499 (0.492 to 0.500) | +0.025 |
| 60 | dist x z | 366,648 | 0.544 | 0.501 (0.491 to 0.501) | +0.043 |
| 60 | osc x regime | 340,792 | 0.550 | 0.498 (0.492 to 0.503) | +0.052 |
| 60 | cross x dist | 315,355 | 0.538 | 0.499 (0.495 to 0.501) | +0.040 |
| 60 | atr x pattern | 315,227 | 0.517 | 0.501 (0.499 to 0.502) | +0.017 |
| 60 | clock x osc | 289,711 | 0.522 | 0.502 (0.500 to 0.507) | +0.020 |
| 60 | atr x cum | 285,826 | 0.525 | 0.499 (0.493 to 0.511) | +0.026 |
| 60 | atr x state | 275,823 | 0.525 | 0.497 (0.497 to 0.507) | +0.028 |
| 60 | dist x regime | 266,330 | 0.572 | 0.494 (0.491 to 0.507) | +0.079 |
| 60 | atr x pct | 248,770 | 0.523 | 0.500 (0.492 to 0.507) | +0.024 |
| 60 | clock x dist | 228,383 | 0.538 | 0.505 (0.503 to 0.510) | +0.033 |
| 60 | dmkt x osc | 223,337 | 0.511 | 0.502 (0.498 to 0.504) | +0.009 |
| 60 | atr x z | 208,256 | 0.541 | 0.500 (0.494 to 0.503) | +0.041 |
| 60 | atr x cross | 179,581 | 0.537 | 0.497 (0.497 to 0.498) | +0.040 |
| 60 | osc x vol | 172,976 | 0.525 | 0.497 (0.494 to 0.501) | +0.028 |
| 60 | dist x dmkt | 172,023 | 0.509 | 0.500 (0.495 to 0.509) | +0.009 |
| 60 | atr x regime | 148,313 | 0.562 | 0.495 (0.495 to 0.507) | +0.067 |
| 60 | dist x vol | 132,496 | 0.517 | 0.493 (0.484 to 0.503) | +0.025 |
| 60 | atr x clock | 126,507 | 0.528 | 0.504 (0.503 to 0.507) | +0.025 |
| 60 | pattern x state | 119,792 | 0.519 | 0.499 (0.498 to 0.500) | +0.020 |
| 60 | flow x osc | 117,097 | 0.539 | 0.499 (0.498 to 0.500) | +0.040 |
| 60 | cum x pattern | 107,736 | 0.514 | 0.497 (0.496 to 0.504) | +0.017 |
| 60 | context x osc | 107,694 | 0.504 | 0.498 (0.497 to 0.505) | +0.006 |
| 60 | osc x position | 103,914 | 0.519 | 0.502 (0.499 to 0.508) | +0.017 |
| 60 | atr x dmkt | 96,864 | 0.509 | 0.498 (0.497 to 0.509) | +0.010 |
| 60 | cum x state | 94,626 | 0.528 | 0.498 (0.489 to 0.513) | +0.030 |
| 60 | pattern x pct | 93,823 | 0.512 | 0.501 (0.501 to 0.503) | +0.011 |
| 60 | dist x flow | 86,478 | 0.550 | 0.498 (0.494 to 0.500) | +0.052 |
| 60 | cum x pct | 84,638 | 0.523 | 0.508 (0.491 to 0.509) | +0.015 |
| 60 | pct x state | 83,662 | 0.526 | 0.500 (0.496 to 0.507) | +0.025 |
| 60 | context x dist | 81,642 | 0.509 | 0.496 (0.490 to 0.513) | +0.013 |
| 60 | pattern x z | 77,296 | 0.520 | 0.502 (0.499 to 0.502) | +0.018 |
| 60 | dist x position | 75,768 | 0.536 | 0.501 (0.499 to 0.511) | +0.035 |
| 60 | atr x vol | 74,972 | 0.517 | 0.496 (0.491 to 0.501) | +0.021 |
| 60 | cum x z | 71,548 | 0.533 | 0.502 (0.499 to 0.510) | +0.031 |
| 60 | state x z | 68,667 | 0.545 | 0.502 (0.495 to 0.504) | +0.043 |
| 60 | cross x pattern | 63,994 | 0.514 | 0.498 (0.496 to 0.500) | +0.016 |
| 60 | pct x z | 61,973 | 0.534 | 0.500 (0.487 to 0.505) | +0.033 |
| 60 | cross x cum | 61,763 | 0.531 | 0.501 (0.497 to 0.502) | +0.029 |
| 60 | osc x perp | 61,225 | 0.517 | 0.503 (0.501 to 0.504) | +0.014 |
| 60 | cross x state | 56,090 | 0.544 | 0.500 (0.490 to 0.504) | +0.044 |
| 60 | cross x pct | 55,347 | 0.532 | 0.492 (0.490 to 0.501) | +0.041 |
| 60 | oi x osc | 53,514 | 0.524 | 0.506 (0.503 to 0.508) | +0.018 |
| 60 | regime x state | 52,404 | 0.562 | 0.496 (0.491 to 0.508) | +0.066 |
| 60 | dist x perp | 50,750 | 0.531 | 0.513 (0.492 to 0.516) | +0.018 |
| 60 | pattern x regime | 50,265 | 0.511 | 0.495 (0.491 to 0.503) | +0.016 |
| 60 | atr x flow | 49,796 | 0.543 | 0.499 (0.495 to 0.500) | +0.044 |
| 60 | cum x regime | 48,136 | 0.557 | 0.497 (0.495 to 0.505) | +0.060 |
| 60 | cum x cum | 47,159 | 0.522 | 0.496 (0.496 to 0.507) | +0.026 |
| 60 | atr x context | 45,832 | 0.507 | 0.501 (0.501 to 0.510) | +0.006 |
| 60 | clock x state | 45,700 | 0.524 | 0.503 (0.494 to 0.511) | +0.021 |
| 60 | pattern x pattern | 45,083 | 0.505 | 0.500 (0.499 to 0.500) | +0.005 |
| 60 | cross x z | 44,362 | 0.539 | 0.501 (0.499 to 0.507) | +0.039 |
| 60 | state x state | 42,887 | 0.514 | 0.496 (0.488 to 0.506) | +0.018 |
| 60 | atr x position | 42,724 | 0.531 | 0.503 (0.499 to 0.512) | +0.027 |
| 60 | pct x regime | 42,476 | 0.561 | 0.497 (0.497 to 0.503) | +0.064 |
| 60 | clock x cum | 41,007 | 0.531 | 0.506 (0.498 to 0.510) | +0.025 |
| 60 | dist x oi | 40,262 | 0.528 | 0.516 (0.503 to 0.517) | +0.012 |
| 60 | clock x pattern | 39,486 | 0.503 | 0.500 (0.498 to 0.502) | +0.003 |
| 60 | dmkt x pattern | 39,042 | 0.503 | 0.503 (0.498 to 0.503) | +0.000 |
| 60 | clock x pct | 36,796 | 0.535 | 0.500 (0.499 to 0.505) | +0.035 |
| 60 | regime x z | 35,333 | 0.556 | 0.503 (0.503 to 0.503) | +0.053 |
| 60 | pct x pct | 35,326 | 0.523 | 0.493 (0.485 to 0.514) | +0.029 |
| 60 | dmkt x state | 32,863 | 0.511 | 0.498 (0.491 to 0.511) | +0.013 |
| 60 | cross x regime | 32,347 | 0.542 | 0.503 (0.500 to 0.504) | +0.039 |
| 60 | cum x dmkt | 31,427 | 0.512 | 0.499 (0.492 to 0.510) | +0.012 |
| 60 | clock x z | 30,410 | 0.517 | 0.507 (0.501 to 0.508) | +0.010 |
| 60 | clock x cross | 29,728 | 0.513 | 0.506 (0.501 to 0.507) | +0.007 |
| 60 | atr x perp | 27,392 | 0.522 | 0.507 (0.498 to 0.511) | +0.015 |
| 60 | dmkt x pct | 26,781 | 0.515 | 0.496 (0.492 to 0.502) | +0.019 |
| 60 | pattern x vol | 26,487 | 0.510 | 0.502 (0.494 to 0.505) | +0.009 |
| 60 | state x vol | 26,158 | 0.514 | 0.497 (0.482 to 0.505) | +0.017 |
| 60 | cum x vol | 24,876 | 0.504 | 0.495 (0.487 to 0.506) | +0.010 |
| 60 | z x z | 24,785 | 0.551 | 0.500 (0.494 to 0.508) | +0.051 |
| 60 | dmkt x z | 23,185 | 0.513 | 0.508 (0.491 to 0.510) | +0.005 |
| 60 | atr x oi | 22,519 | 0.524 | 0.504 (0.503 to 0.513) | +0.020 |
| 60 | pct x vol | 21,686 | 0.521 | 0.498 (0.493 to 0.503) | +0.023 |
| 60 | cross x dmkt | 21,194 | 0.501 | 0.509 (0.491 to 0.515) | -0.008 |
| 60 | context x pattern | 18,573 | 0.496 | 0.501 (0.496 to 0.503) | -0.005 |
| 60 | vol x z | 18,313 | 0.518 | 0.491 (0.491 to 0.498) | +0.027 |
| 60 | pattern x position | 17,641 | 0.514 | 0.499 (0.492 to 0.502) | +0.015 |
| 60 | flow x pattern | 17,624 | 0.516 | 0.498 (0.491 to 0.502) | +0.018 |
| 60 | clock x regime | 17,137 | 0.498 | 0.504 (0.490 to 0.512) | -0.005 |
| 60 | cum x flow | 16,900 | 0.548 | 0.501 (0.498 to 0.502) | +0.047 |
| 60 | flow x state | 16,378 | 0.558 | 0.491 (0.483 to 0.499) | +0.068 |
| 60 | clock x dmkt | 16,324 | 0.501 | 0.499 (0.499 to 0.500) | +0.002 |
| 60 | cross x vol | 15,953 | 0.535 | 0.497 (0.494 to 0.498) | +0.038 |
| 60 | cross x cross | 15,700 | 0.543 | 0.500 (0.498 to 0.506) | +0.043 |
| 60 | flow x pct | 15,203 | 0.540 | 0.496 (0.489 to 0.504) | +0.045 |
| 60 | context x state | 15,092 | 0.497 | 0.495 (0.490 to 0.515) | +0.002 |
| 60 | context x cum | 15,021 | 0.516 | 0.510 (0.502 to 0.518) | +0.006 |
| 60 | cum x position | 14,608 | 0.529 | 0.501 (0.500 to 0.508) | +0.029 |
| 60 | dmkt x regime | 14,163 | 0.487 | 0.504 (0.479 to 0.506) | -0.018 |
| 60 | pct x position | 13,200 | 0.515 | 0.505 (0.482 to 0.514) | +0.009 |
| 60 | position x state | 13,024 | 0.552 | 0.505 (0.484 to 0.512) | +0.048 |
| 60 | context x pct | 13,017 | 0.503 | 0.492 (0.489 to 0.514) | +0.011 |
| 60 | regime x vol | 12,433 | 0.531 | 0.495 (0.492 to 0.506) | +0.036 |
| 60 | flow x z | 12,210 | 0.556 | 0.503 (0.494 to 0.509) | +0.053 |
| 60 | context x z | 11,079 | 0.507 | 0.512 (0.502 to 0.512) | -0.005 |
| 60 | position x z | 10,560 | 0.492 | 0.507 (0.501 to 0.508) | -0.015 |
| 60 | clock x vol | 10,339 | 0.519 | 0.510 (0.498 to 0.516) | +0.009 |
| 60 | regime x regime | 10,233 | 0.530 | 0.494 (0.493 to 0.496) | +0.037 |
| 60 | perp x state | 9,887 | 0.506 | 0.510 (0.508 to 0.515) | -0.004 |
| 60 | context x cross | 9,849 | 0.512 | 0.503 (0.500 to 0.510) | +0.009 |
| 60 | cross x flow | 9,793 | 0.541 | 0.494 (0.487 to 0.501) | +0.047 |
| 60 | cum x perp | 9,712 | 0.528 | 0.503 (0.500 to 0.521) | +0.025 |
| 60 | flow x regime | 8,475 | 0.560 | 0.500 (0.491 to 0.509) | +0.060 |
| 60 | cross x position | 8,340 | 0.509 | 0.496 (0.486 to 0.506) | +0.013 |
| 60 | clock x flow | 8,123 | 0.512 | 0.493 (0.491 to 0.500) | +0.019 |
| 60 | position x regime | 8,096 | 0.491 | 0.504 (0.502 to 0.513) | -0.013 |
| 60 | dmkt x vol | 8,004 | 0.507 | 0.501 (0.492 to 0.511) | +0.006 |
| 60 | pct x perp | 7,890 | 0.521 | 0.513 (0.504 to 0.514) | +0.009 |
| 60 | cum x oi | 7,701 | 0.534 | 0.514 (0.504 to 0.524) | +0.020 |
| 60 | dist x macro | 7,676 | 0.460 | 0.508 (0.476 to 0.513) | -0.049 |
| 60 | oi x pattern | 7,632 | 0.508 | 0.497 (0.484 to 0.501) | +0.011 |
| 60 | macro x osc | 7,559 | 0.473 | 0.491 (0.481 to 0.504) | -0.018 |
| 60 | pattern x perp | 7,465 | 0.496 | 0.492 (0.490 to 0.498) | +0.004 |
| 60 | context x regime | 7,151 | 0.499 | 0.509 (0.501 to 0.512) | -0.010 |
| 60 | oi x state | 7,078 | 0.519 | 0.518 (0.515 to 0.524) | +0.001 |
| 60 | perp x z | 6,952 | 0.532 | 0.500 (0.493 to 0.508) | +0.032 |
| 60 | oi x pct | 6,749 | 0.520 | 0.501 (0.491 to 0.514) | +0.019 |
| 60 | clock x position | 6,568 | 0.509 | 0.505 (0.504 to 0.514) | +0.004 |
| 60 | clock x context | 6,376 | 0.499 | 0.493 (0.485 to 0.512) | +0.006 |
| 60 | dmkt x flow | 5,893 | 0.503 | 0.500 (0.499 to 0.507) | +0.002 |
| 60 | oi x z | 5,541 | 0.527 | 0.501 (0.497 to 0.521) | +0.026 |
| 60 | cross x perp | 5,520 | 0.517 | 0.503 (0.483 to 0.503) | +0.014 |
| 60 | dmkt x position | 5,104 | 0.503 | 0.511 (0.507 to 0.513) | -0.008 |
| 60 | cross x oi | 4,529 | 0.511 | 0.503 (0.497 to 0.512) | +0.008 |
| 60 | flow x vol | 4,326 | 0.547 | 0.495 (0.486 to 0.504) | +0.051 |
| 60 | perp x regime | 4,232 | 0.542 | 0.508 (0.503 to 0.514) | +0.034 |
| 60 | atr x macro | 4,138 | 0.463 | 0.488 (0.476 to 0.491) | -0.024 |
| 60 | position x vol | 4,032 | 0.509 | 0.501 (0.499 to 0.522) | +0.007 |
| 60 | context x vol | 3,934 | 0.502 | 0.510 (0.496 to 0.521) | -0.009 |
| 60 | oi x regime | 3,676 | 0.540 | 0.506 (0.496 to 0.516) | +0.034 |
| 60 | context x dmkt | 3,320 | 0.542 | 0.480 (0.478 to 0.511) | +0.062 |
| 60 | clock x oi | 3,220 | 0.506 | 0.496 (0.486 to 0.509) | +0.011 |
| 60 | vol x vol | 2,966 | 0.503 | 0.500 (0.483 to 0.512) | +0.002 |
| 60 | dmkt x perp | 2,922 | 0.492 | 0.492 (0.483 to 0.516) | -0.000 |
| 60 | context x flow | 2,815 | 0.524 | 0.505 (0.492 to 0.507) | +0.019 |
| 60 | dmkt x dmkt | 2,560 | 0.515 | 0.498 (0.487 to 0.504) | +0.017 |
| 60 | dmkt x oi | 2,487 | 0.520 | 0.506 (0.495 to 0.512) | +0.014 |
| 60 | flow x position | 2,464 | 0.500 | 0.512 (0.506 to 0.533) | -0.011 |
| 60 | clock x perp | 2,410 | 0.486 | 0.510 (0.504 to 0.520) | -0.023 |
| 60 | clock x clock | 2,400 | 0.492 | 0.517 (0.509 to 0.523) | -0.025 |
| 60 | perp x vol | 2,364 | 0.527 | 0.501 (0.500 to 0.516) | +0.026 |
| 60 | context x position | 2,288 | 0.492 | 0.508 (0.494 to 0.510) | -0.016 |
| 60 | oi x vol | 1,952 | 0.525 | 0.506 (0.494 to 0.507) | +0.019 |
| 60 | macro x state | 1,900 | 0.450 | 0.481 (0.476 to 0.521) | -0.031 |
| 60 | flow x perp | 1,525 | 0.521 | 0.504 (0.500 to 0.534) | +0.018 |
| 60 | cum x macro | 1,418 | 0.449 | 0.503 (0.484 to 0.541) | -0.054 |
| 60 | context x perp | 1,395 | 0.493 | 0.514 (0.483 to 0.521) | -0.021 |
| 60 | flow x oi | 1,243 | 0.547 | 0.490 (0.480 to 0.508) | +0.058 |
| 60 | perp x position | 1,226 | 0.484 | 0.498 (0.497 to 0.513) | -0.013 |
| 60 | context x oi | 1,209 | 0.499 | 0.512 (0.493 to 0.524) | -0.014 |
| 60 | cross x macro | 1,200 | 0.469 | 0.502 (0.494 to 0.535) | -0.033 |
| 60 | macro x pattern | 1,185 | 0.497 | 0.485 (0.473 to 0.517) | +0.012 |
| 60 | flow x flow | 1,162 | 0.560 | 0.474 (0.469 to 0.514) | +0.086 |
| 60 | macro x z | 1,093 | 0.475 | 0.485 (0.457 to 0.499) | -0.010 |
| 60 | oi x position | 1,056 | 0.483 | 0.476 (0.464 to 0.518) | +0.008 |
| 60 | macro x pct | 938 | 0.440 | 0.499 (0.464 to 0.517) | -0.059 |
| 60 | context x context | 748 | 0.517 | 0.504 (0.496 to 0.518) | +0.013 |
| 60 | oi x perp | 703 | 0.494 | 0.515 (0.484 to 0.515) | -0.022 |
| 60 | macro x regime | 389 | 0.544 | 0.502 (0.480 to 0.542) | +0.041 |
| 60 | clock x macro | 364 | 0.550 | 0.511 (0.482 to 0.591) | +0.039 |
| 60 | macro x position | 364 | 0.448 | 0.523 (0.471 to 0.528) | -0.076 |
| 60 | position x position | 348 | 0.515 | 0.480 (0.439 to 0.492) | +0.036 |
| 60 | perp x perp | 347 | 0.548 | 0.472 (0.464 to 0.517) | +0.076 |
| 60 | macro x vol | 264 | 0.424 | 0.556 (0.461 to 0.566) | -0.132 |
| 60 | flow x macro | 243 | 0.481 | 0.511 (0.479 to 0.549) | -0.029 |
| 60 | oi x oi | 151 | 0.457 | 0.493 (0.424 to 0.503) | -0.036 |
| 60 | dmkt x macro | 128 | 0.492 | 0.562 (0.500 to 0.578) | -0.070 |
| 60 | macro x perp | 102 | 0.592 | 0.548 (0.430 to 0.583) | +0.043 |
| 60 | macro x oi | 92 | 0.407 | 0.517 (0.432 to 0.535) | -0.111 |
| 60 | context x macro | 72 | 0.364 | 0.508 (0.484 to 0.508) | -0.144 |
| 60 | macro x macro | 16 | 1.000 | 0.500 (0.000 to 0.750) | +0.500 |
| 240 | dist x osc | 3,411,187 | 0.533 | 0.501 (0.498 to 0.503) | +0.032 |
| 240 | osc x osc | 2,253,189 | 0.525 | 0.500 (0.497 to 0.501) | +0.025 |
| 240 | atr x osc | 1,951,135 | 0.527 | 0.498 (0.496 to 0.499) | +0.029 |
| 240 | atr x dist | 1,461,333 | 0.529 | 0.499 (0.497 to 0.500) | +0.030 |
| 240 | dist x dist | 1,254,291 | 0.533 | 0.500 (0.499 to 0.506) | +0.033 |
| 240 | osc x pattern | 701,415 | 0.511 | 0.500 (0.499 to 0.500) | +0.010 |
| 240 | cum x osc | 667,856 | 0.526 | 0.500 (0.496 to 0.502) | +0.026 |
| 240 | osc x state | 663,810 | 0.525 | 0.500 (0.500 to 0.502) | +0.025 |
| 240 | osc x pct | 574,294 | 0.525 | 0.498 (0.498 to 0.504) | +0.027 |
| 240 | dist x pattern | 558,460 | 0.516 | 0.501 (0.499 to 0.504) | +0.015 |
| 240 | cum x dist | 504,920 | 0.527 | 0.495 (0.493 to 0.502) | +0.032 |
| 240 | osc x z | 487,524 | 0.529 | 0.500 (0.495 to 0.503) | +0.029 |
| 240 | dist x state | 485,667 | 0.517 | 0.503 (0.494 to 0.505) | +0.013 |
| 240 | dist x pct | 435,571 | 0.530 | 0.502 (0.497 to 0.503) | +0.028 |
| 240 | cross x osc | 429,979 | 0.516 | 0.501 (0.501 to 0.507) | +0.014 |
| 240 | atr x atr | 413,505 | 0.526 | 0.497 (0.496 to 0.498) | +0.029 |
| 240 | dist x z | 366,618 | 0.538 | 0.501 (0.488 to 0.502) | +0.036 |
| 240 | osc x regime | 340,539 | 0.523 | 0.497 (0.492 to 0.502) | +0.026 |
| 240 | cross x dist | 315,343 | 0.517 | 0.502 (0.498 to 0.507) | +0.016 |
| 240 | atr x pattern | 315,185 | 0.512 | 0.500 (0.500 to 0.502) | +0.013 |
| 240 | clock x osc | 289,677 | 0.519 | 0.498 (0.497 to 0.501) | +0.021 |
| 240 | atr x cum | 285,792 | 0.525 | 0.498 (0.494 to 0.501) | +0.027 |
| 240 | atr x state | 275,813 | 0.524 | 0.496 (0.494 to 0.501) | +0.028 |
| 240 | dist x regime | 266,103 | 0.537 | 0.494 (0.487 to 0.506) | +0.043 |
| 240 | atr x pct | 248,753 | 0.525 | 0.498 (0.495 to 0.503) | +0.028 |
| 240 | clock x dist | 228,359 | 0.526 | 0.497 (0.496 to 0.499) | +0.029 |
| 240 | dmkt x osc | 223,319 | 0.512 | 0.497 (0.488 to 0.505) | +0.015 |
| 240 | atr x z | 208,230 | 0.529 | 0.500 (0.492 to 0.500) | +0.029 |
| 240 | atr x cross | 179,572 | 0.516 | 0.498 (0.498 to 0.503) | +0.017 |
| 240 | osc x vol | 172,942 | 0.516 | 0.500 (0.496 to 0.502) | +0.015 |
| 240 | dist x dmkt | 172,021 | 0.518 | 0.493 (0.477 to 0.506) | +0.025 |
| 240 | atr x regime | 148,177 | 0.527 | 0.498 (0.492 to 0.505) | +0.029 |
| 240 | dist x vol | 132,479 | 0.515 | 0.499 (0.497 to 0.501) | +0.016 |
| 240 | atr x clock | 126,500 | 0.515 | 0.496 (0.496 to 0.498) | +0.018 |
| 240 | pattern x state | 119,778 | 0.516 | 0.501 (0.500 to 0.507) | +0.015 |
| 240 | flow x osc | 117,081 | 0.517 | 0.500 (0.494 to 0.512) | +0.017 |
| 240 | cum x pattern | 107,715 | 0.508 | 0.501 (0.497 to 0.502) | +0.006 |
| 240 | context x osc | 107,688 | 0.527 | 0.502 (0.498 to 0.511) | +0.025 |
| 240 | osc x position | 103,914 | 0.508 | 0.503 (0.494 to 0.507) | +0.005 |
| 240 | atr x dmkt | 96,862 | 0.511 | 0.492 (0.480 to 0.500) | +0.019 |
| 240 | cum x state | 94,623 | 0.523 | 0.499 (0.495 to 0.502) | +0.024 |
| 240 | pattern x pct | 93,814 | 0.511 | 0.500 (0.500 to 0.504) | +0.011 |
| 240 | dist x flow | 86,476 | 0.513 | 0.499 (0.495 to 0.512) | +0.013 |
| 240 | cum x pct | 84,632 | 0.519 | 0.502 (0.498 to 0.502) | +0.017 |
| 240 | pct x state | 83,660 | 0.522 | 0.500 (0.500 to 0.503) | +0.021 |
| 240 | context x dist | 81,642 | 0.534 | 0.516 (0.492 to 0.521) | +0.019 |
| 240 | pattern x z | 77,269 | 0.514 | 0.500 (0.496 to 0.503) | +0.014 |
| 240 | dist x position | 75,768 | 0.519 | 0.500 (0.497 to 0.500) | +0.019 |
| 240 | atr x vol | 74,967 | 0.511 | 0.501 (0.498 to 0.503) | +0.010 |
| 240 | cum x z | 71,540 | 0.526 | 0.498 (0.493 to 0.505) | +0.028 |
| 240 | state x z | 68,665 | 0.533 | 0.495 (0.494 to 0.499) | +0.038 |
| 240 | cross x pattern | 63,974 | 0.510 | 0.501 (0.500 to 0.505) | +0.009 |
| 240 | pct x z | 61,965 | 0.526 | 0.501 (0.495 to 0.505) | +0.025 |
| 240 | cross x cum | 61,763 | 0.511 | 0.507 (0.499 to 0.509) | +0.003 |
| 240 | osc x perp | 61,221 | 0.523 | 0.505 (0.503 to 0.507) | +0.018 |
| 240 | cross x state | 56,087 | 0.527 | 0.498 (0.492 to 0.506) | +0.029 |
| 240 | cross x pct | 55,346 | 0.514 | 0.496 (0.495 to 0.510) | +0.018 |
| 240 | oi x osc | 53,513 | 0.510 | 0.498 (0.483 to 0.498) | +0.013 |
| 240 | regime x state | 52,340 | 0.537 | 0.501 (0.495 to 0.503) | +0.036 |
| 240 | dist x perp | 50,744 | 0.527 | 0.510 (0.506 to 0.515) | +0.017 |
| 240 | pattern x regime | 50,221 | 0.503 | 0.499 (0.495 to 0.500) | +0.004 |
| 240 | atr x flow | 49,793 | 0.511 | 0.498 (0.495 to 0.510) | +0.013 |
| 240 | cum x regime | 48,095 | 0.526 | 0.495 (0.493 to 0.502) | +0.031 |
| 240 | cum x cum | 47,151 | 0.519 | 0.503 (0.488 to 0.506) | +0.016 |
| 240 | atr x context | 45,831 | 0.529 | 0.509 (0.497 to 0.513) | +0.020 |
| 240 | clock x state | 45,700 | 0.517 | 0.490 (0.490 to 0.507) | +0.027 |
| 240 | pattern x pattern | 45,073 | 0.505 | 0.499 (0.497 to 0.507) | +0.006 |
| 240 | cross x z | 44,355 | 0.513 | 0.503 (0.499 to 0.510) | +0.010 |
| 240 | state x state | 42,887 | 0.504 | 0.494 (0.484 to 0.510) | +0.010 |
| 240 | atr x position | 42,724 | 0.525 | 0.503 (0.499 to 0.505) | +0.022 |
| 240 | pct x regime | 42,453 | 0.532 | 0.499 (0.492 to 0.505) | +0.032 |
| 240 | clock x cum | 41,001 | 0.522 | 0.498 (0.493 to 0.509) | +0.024 |
| 240 | dist x oi | 40,260 | 0.509 | 0.487 (0.480 to 0.501) | +0.022 |
| 240 | clock x pattern | 39,481 | 0.500 | 0.501 (0.497 to 0.503) | -0.000 |
| 240 | dmkt x pattern | 39,041 | 0.495 | 0.500 (0.497 to 0.507) | -0.005 |
| 240 | clock x pct | 36,791 | 0.522 | 0.489 (0.488 to 0.505) | +0.033 |
| 240 | pct x pct | 35,322 | 0.522 | 0.500 (0.492 to 0.512) | +0.022 |
| 240 | regime x z | 35,305 | 0.529 | 0.501 (0.501 to 0.502) | +0.028 |
| 240 | dmkt x state | 32,863 | 0.522 | 0.498 (0.490 to 0.500) | +0.024 |
| 240 | cross x regime | 32,306 | 0.511 | 0.500 (0.499 to 0.500) | +0.011 |
| 240 | cum x dmkt | 31,426 | 0.511 | 0.489 (0.482 to 0.519) | +0.022 |
| 240 | clock x z | 30,408 | 0.506 | 0.498 (0.494 to 0.504) | +0.008 |
| 240 | clock x cross | 29,728 | 0.510 | 0.504 (0.497 to 0.504) | +0.006 |
| 240 | atr x perp | 27,389 | 0.526 | 0.503 (0.499 to 0.512) | +0.023 |
| 240 | dmkt x pct | 26,781 | 0.522 | 0.490 (0.488 to 0.496) | +0.032 |
| 240 | pattern x vol | 26,479 | 0.505 | 0.499 (0.493 to 0.500) | +0.006 |
| 240 | state x vol | 26,158 | 0.500 | 0.497 (0.492 to 0.505) | +0.003 |
| 240 | cum x vol | 24,866 | 0.509 | 0.501 (0.489 to 0.506) | +0.008 |
| 240 | z x z | 24,782 | 0.530 | 0.492 (0.489 to 0.500) | +0.038 |
| 240 | dmkt x z | 23,185 | 0.503 | 0.502 (0.487 to 0.513) | +0.001 |
| 240 | atr x oi | 22,519 | 0.515 | 0.490 (0.482 to 0.509) | +0.025 |
| 240 | pct x vol | 21,686 | 0.505 | 0.502 (0.501 to 0.503) | +0.003 |
| 240 | cross x dmkt | 21,194 | 0.515 | 0.503 (0.490 to 0.510) | +0.012 |
| 240 | context x pattern | 18,572 | 0.500 | 0.499 (0.496 to 0.512) | +0.001 |
| 240 | vol x z | 18,307 | 0.511 | 0.502 (0.499 to 0.505) | +0.009 |
| 240 | pattern x position | 17,639 | 0.508 | 0.497 (0.496 to 0.499) | +0.011 |
| 240 | flow x pattern | 17,619 | 0.510 | 0.502 (0.496 to 0.503) | +0.008 |
| 240 | clock x regime | 17,136 | 0.497 | 0.501 (0.493 to 0.512) | -0.004 |
| 240 | cum x flow | 16,898 | 0.498 | 0.508 (0.503 to 0.519) | -0.011 |
| 240 | flow x state | 16,378 | 0.519 | 0.488 (0.487 to 0.514) | +0.031 |
| 240 | clock x dmkt | 16,324 | 0.503 | 0.502 (0.475 to 0.505) | +0.001 |
| 240 | cross x vol | 15,951 | 0.512 | 0.505 (0.502 to 0.510) | +0.006 |
| 240 | cross x cross | 15,699 | 0.530 | 0.505 (0.501 to 0.506) | +0.024 |
| 240 | flow x pct | 15,202 | 0.518 | 0.499 (0.497 to 0.515) | +0.020 |
| 240 | context x state | 15,091 | 0.524 | 0.510 (0.491 to 0.525) | +0.014 |
| 240 | context x cum | 15,020 | 0.518 | 0.508 (0.498 to 0.510) | +0.010 |
| 240 | cum x position | 14,608 | 0.521 | 0.495 (0.493 to 0.499) | +0.026 |
| 240 | dmkt x regime | 14,159 | 0.496 | 0.507 (0.487 to 0.510) | -0.010 |
| 240 | pct x position | 13,200 | 0.504 | 0.502 (0.488 to 0.508) | +0.002 |
| 240 | position x state | 13,024 | 0.528 | 0.502 (0.490 to 0.519) | +0.026 |
| 240 | context x pct | 13,017 | 0.529 | 0.507 (0.503 to 0.508) | +0.022 |
| 240 | regime x vol | 12,421 | 0.520 | 0.510 (0.498 to 0.521) | +0.011 |
| 240 | flow x z | 12,207 | 0.514 | 0.507 (0.497 to 0.512) | +0.006 |
| 240 | context x z | 11,078 | 0.515 | 0.502 (0.484 to 0.504) | +0.013 |
| 240 | position x z | 10,560 | 0.512 | 0.496 (0.496 to 0.501) | +0.016 |
| 240 | clock x vol | 10,336 | 0.502 | 0.494 (0.486 to 0.503) | +0.007 |
| 240 | regime x regime | 10,226 | 0.516 | 0.504 (0.489 to 0.509) | +0.012 |
| 240 | perp x state | 9,887 | 0.540 | 0.512 (0.508 to 0.514) | +0.028 |
| 240 | context x cross | 9,849 | 0.528 | 0.500 (0.490 to 0.526) | +0.029 |
| 240 | cross x flow | 9,793 | 0.497 | 0.508 (0.502 to 0.510) | -0.011 |
| 240 | cum x perp | 9,712 | 0.518 | 0.511 (0.505 to 0.512) | +0.007 |
| 240 | flow x regime | 8,469 | 0.527 | 0.503 (0.501 to 0.508) | +0.025 |
| 240 | cross x position | 8,340 | 0.518 | 0.502 (0.492 to 0.511) | +0.016 |
| 240 | clock x flow | 8,123 | 0.508 | 0.498 (0.492 to 0.504) | +0.010 |
| 240 | position x regime | 8,074 | 0.504 | 0.504 (0.495 to 0.505) | -0.000 |
| 240 | dmkt x vol | 8,004 | 0.493 | 0.493 (0.481 to 0.512) | -0.001 |
| 240 | pct x perp | 7,890 | 0.522 | 0.501 (0.491 to 0.511) | +0.021 |
| 240 | cum x oi | 7,700 | 0.518 | 0.490 (0.486 to 0.503) | +0.027 |
| 240 | dist x macro | 7,676 | 0.475 | 0.474 (0.467 to 0.560) | +0.001 |
| 240 | oi x pattern | 7,632 | 0.498 | 0.504 (0.494 to 0.504) | -0.006 |
| 240 | macro x osc | 7,559 | 0.496 | 0.501 (0.487 to 0.527) | -0.005 |
| 240 | pattern x perp | 7,462 | 0.500 | 0.507 (0.503 to 0.519) | -0.006 |
| 240 | context x regime | 7,147 | 0.485 | 0.507 (0.483 to 0.509) | -0.022 |
| 240 | oi x state | 7,078 | 0.500 | 0.485 (0.483 to 0.502) | +0.015 |
| 240 | perp x z | 6,952 | 0.511 | 0.509 (0.498 to 0.513) | +0.002 |
| 240 | oi x pct | 6,749 | 0.495 | 0.505 (0.477 to 0.507) | -0.010 |
| 240 | clock x position | 6,568 | 0.512 | 0.488 (0.485 to 0.504) | +0.024 |
| 240 | clock x context | 6,376 | 0.493 | 0.493 (0.479 to 0.524) | +0.001 |
| 240 | dmkt x flow | 5,893 | 0.513 | 0.504 (0.488 to 0.506) | +0.009 |
| 240 | oi x z | 5,540 | 0.520 | 0.489 (0.473 to 0.497) | +0.030 |
| 240 | cross x perp | 5,520 | 0.515 | 0.520 (0.500 to 0.528) | -0.005 |
| 240 | dmkt x position | 5,104 | 0.505 | 0.492 (0.490 to 0.496) | +0.013 |
| 240 | cross x oi | 4,529 | 0.520 | 0.495 (0.494 to 0.515) | +0.025 |
| 240 | flow x vol | 4,326 | 0.512 | 0.511 (0.505 to 0.515) | +0.002 |
| 240 | perp x regime | 4,231 | 0.509 | 0.497 (0.487 to 0.507) | +0.013 |
| 240 | atr x macro | 4,138 | 0.508 | 0.514 (0.473 to 0.536) | -0.006 |
| 240 | position x vol | 4,032 | 0.510 | 0.497 (0.482 to 0.515) | +0.013 |
| 240 | context x vol | 3,934 | 0.495 | 0.504 (0.500 to 0.511) | -0.010 |
| 240 | oi x regime | 3,676 | 0.514 | 0.503 (0.479 to 0.520) | +0.010 |
| 240 | context x dmkt | 3,320 | 0.542 | 0.487 (0.463 to 0.508) | +0.055 |
| 240 | clock x oi | 3,219 | 0.492 | 0.504 (0.494 to 0.510) | -0.011 |
| 240 | vol x vol | 2,965 | 0.508 | 0.508 (0.508 to 0.512) | -0.000 |
| 240 | dmkt x perp | 2,922 | 0.523 | 0.501 (0.482 to 0.530) | +0.023 |
| 240 | context x flow | 2,815 | 0.520 | 0.500 (0.494 to 0.503) | +0.019 |
| 240 | dmkt x dmkt | 2,560 | 0.486 | 0.497 (0.489 to 0.500) | -0.011 |
| 240 | dmkt x oi | 2,487 | 0.480 | 0.502 (0.475 to 0.504) | -0.022 |
| 240 | flow x position | 2,464 | 0.503 | 0.493 (0.492 to 0.503) | +0.010 |
| 240 | clock x perp | 2,410 | 0.527 | 0.493 (0.480 to 0.506) | +0.034 |
| 240 | clock x clock | 2,400 | 0.463 | 0.522 (0.471 to 0.529) | -0.059 |
| 240 | perp x vol | 2,363 | 0.493 | 0.502 (0.495 to 0.505) | -0.008 |
| 240 | context x position | 2,288 | 0.506 | 0.500 (0.482 to 0.503) | +0.006 |
| 240 | oi x vol | 1,952 | 0.509 | 0.492 (0.473 to 0.494) | +0.017 |
| 240 | macro x state | 1,900 | 0.530 | 0.508 (0.471 to 0.553) | +0.023 |
| 240 | flow x perp | 1,525 | 0.495 | 0.517 (0.514 to 0.533) | -0.021 |
| 240 | cum x macro | 1,418 | 0.508 | 0.506 (0.497 to 0.550) | +0.001 |
| 240 | context x perp | 1,395 | 0.516 | 0.514 (0.468 to 0.543) | +0.001 |
| 240 | flow x oi | 1,243 | 0.497 | 0.499 (0.478 to 0.510) | -0.002 |
| 240 | perp x position | 1,226 | 0.519 | 0.490 (0.479 to 0.527) | +0.029 |
| 240 | context x oi | 1,209 | 0.501 | 0.505 (0.476 to 0.515) | -0.005 |
| 240 | cross x macro | 1,199 | 0.510 | 0.510 (0.468 to 0.513) | +0.000 |
| 240 | macro x pattern | 1,185 | 0.491 | 0.490 (0.478 to 0.505) | +0.001 |
| 240 | flow x flow | 1,162 | 0.520 | 0.499 (0.496 to 0.525) | +0.021 |
| 240 | macro x z | 1,093 | 0.461 | 0.497 (0.480 to 0.541) | -0.037 |
| 240 | oi x position | 1,056 | 0.540 | 0.500 (0.490 to 0.507) | +0.039 |
| 240 | macro x pct | 938 | 0.514 | 0.525 (0.469 to 0.567) | -0.011 |
| 240 | context x context | 748 | 0.477 | 0.524 (0.465 to 0.539) | -0.048 |
| 240 | oi x perp | 703 | 0.484 | 0.496 (0.487 to 0.502) | -0.013 |
| 240 | macro x regime | 389 | 0.501 | 0.523 (0.516 to 0.530) | -0.021 |
| 240 | clock x macro | 364 | 0.608 | 0.489 (0.466 to 0.561) | +0.119 |
| 240 | macro x position | 362 | 0.482 | 0.453 (0.447 to 0.486) | +0.029 |
| 240 | position x position | 348 | 0.497 | 0.463 (0.452 to 0.522) | +0.033 |
| 240 | perp x perp | 347 | 0.493 | 0.508 (0.489 to 0.559) | -0.016 |
| 240 | macro x vol | 264 | 0.458 | 0.498 (0.496 to 0.559) | -0.040 |
| 240 | flow x macro | 243 | 0.496 | 0.528 (0.470 to 0.551) | -0.032 |
| 240 | oi x oi | 151 | 0.490 | 0.517 (0.437 to 0.536) | -0.026 |
| 240 | dmkt x macro | 128 | 0.496 | 0.531 (0.516 to 0.586) | -0.035 |
| 240 | macro x perp | 102 | 0.490 | 0.490 (0.372 to 0.533) | +0.000 |
| 240 | macro x oi | 92 | 0.489 | 0.477 (0.460 to 0.488) | +0.012 |
| 240 | context x macro | 72 | 0.548 | 0.483 (0.460 to 0.565) | +0.065 |
| 240 | macro x macro | 16 | 1.000 | 0.250 (0.250 to 0.750) | +0.750 |

### TA-Lib usage cards

One card per TA-Lib function (211 cards, in usage.md and usage_cards.json): a grid of its settings x timeframes (each square: the horizon where it is strongest on A, each zone's B odds in its A direction there, whether the extreme zones fade or follow), its own call by level, the model's mean contribution, its best partner in each data family (and whether that partner strengthens the call or flips it: a stand-aside lesson), and its family's kept-interaction share; each beside the twins.

The functions whose best partner has the most iheat on 2025 (the full cards are in usage.md):

| function | minutes | partner family | coin | reading | partner | dir | strengthens the call | iheat B | twins' best |
|---|---|---|---|---|---|---|---|---|---|
| C-TEMA | 15 | TA | ETH | 1m:C-TEMA21 sign=above 0 | 1m:TRANGE=high | down | yes | 89.79 | 27.81 (23.92 to 32.03) |
| TRANGE | 15 | TA | ETH | 1m:TRANGE=high | 1m:C-TEMA21 sign=above 0 | down | yes | 89.79 | 25.31 (21.99 to 34.91) |
| C-TSF | 15 | position and clock | ETH | 1m:C-TSF14 sign=above 0 | POS:QPhase=m00-04 | up | yes | 87.03 | 23.35 (-18.77 to 34.33) |
| C-LINEARREG | 15 | TA | ETH | 1m:C-LINEARREG14 sign=above 0 | 1m:TRANGE=high | down | yes | 85.54 | 27.29 (23.34 to 38.24) |
| SWAK_2PHP | 15 | TA | ETH | 1m:SWAK_2PHP20 sign=above 0 | 1m:TRANGE=high | down | yes | 85.04 | 27.95 (24.11 to 36.36) |
| DOSC | 15 | TA | ETH | 1m:DOSC sign=above 0 | 1m:ER10=low | up | yes | 83.11 | 26.96 (23.38 to 35.19) |
| ER | 15 | TA | ETH | 1m:ER10=low | 1m:DOSC sign=above 0 | up | yes | 83.11 | 25.78 (19.45 to 36.95) |
| C-HMA | 15 | TA | ETH | 1m:C-HMA20 sign=above 0 | 1m:TRANGE=high | down | yes | 83.11 | 27.32 (25.02 to 36.44) |
| C-ZLEMA | 15 | TA | ETH | 1m:C-ZLEMA21 sign=above 0 | 1m:TRANGE=high | down | yes | 81.88 | 28.92 (22.60 to 34.50) |
| C-MIDPOINT | 15 | TA | XRP | 1m:C-MIDPOINT14 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 80.34 | 27.46 (24.34 to 30.11) |
| HT_TRENDMODE | 15 | TA | XRP | 1m:HT_TRENDMODE=trend | 1m:C-MIDPOINT14 sign=above 0 | down | yes | 80.34 | 24.16 (15.94 to 30.73) |
| C-VWAP | 15 | TA | XRP | 1m:C-VWAP20 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 80.22 | 27.84 (22.09 to 33.28) |
| C-TRIMA | 15 | TA | XRP | 1m:C-TRIMA20 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 80.09 | 27.68 (22.32 to 36.59) |
| C-MIDPRICE | 15 | TA | XRP | 1m:C-MIDPRICE14 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 79.07 | 28.91 (23.70 to 40.92) |
| DX | 15 | TA | ETH | 1m:DX14=high | 1m:HAbody sign=above 0 | down | yes | 79.05 | 24.64 (18.62 to 30.96) |
| HAbody | 15 | TA | ETH | 1m:HAbody sign=above 0 | 1m:DX14=high | down | yes | 79.05 | 30.29 (24.08 to 37.00) |
| C-CKSPmid | 15 | TA | XRP | 1m:C-CKSPmid sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 78.93 | 26.66 (23.68 to 36.20) |
| C-DEMA | 15 | TA | ETH | 1m:C-DEMA21 sign=above 0 | 1m:DX14=high | down | yes | 78.73 | 27.83 (25.26 to 36.00) |
| SWAK_HP | 15 | TA | ETH | 1m:SWAK_HP20 sign=above 0 | 1m:DX14=high | down | yes | 78.65 | 28.97 (23.96 to 38.14) |
| C-SMA | 15 | TA | XRP | 1m:C-SMA20 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 78.50 | 30.64 (25.89 to 34.35) |
| ZSCORE | 15 | TA | XRP | 1m:C-SMA20 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 78.50 | 27.98 (23.07 to 34.35) |
| MACDh | 15 | TA | ETH | 1m:MACDh12/26/9 sign=above 0 | 1m:DX14=high | down | yes | 78.36 | 30.34 (24.93 to 39.29) |
| C-ALMA | 15 | TA | ETH | 1m:C-ALMA9 sign=above 0 | 1m:DX14=high | down | yes | 78.33 | 26.88 (22.23 to 38.16) |
| CCI | 15 | TA | XRP | 1m:CCI14 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 78.33 | 28.54 (24.27 to 38.16) |
| C-VWMA | 15 | TA | XRP | 1m:C-VWMA20 sign=above 0 | 1m:HT_TRENDMODE=trend | down | yes | 77.95 | 27.16 (20.96 to 35.01) |

### Each coin's top rows in words

- **BTC, pairs, 15 minutes, by oheat:**
  - 1m ADOSC above 0 while 1m CORRELcv30 above 0: down, 53% right on 2025, 55.6 windows a day (twins' best: 51%, 47.1 windows).
  - 1m AD above 0 while 1m CORRELcv30 above 0: down, 53% right on 2025, 57.3 windows a day (twins' best: 51%, 47.1 windows).
  - 1m CMF20 above 0 while 1m PVI above 0: down, 53% right on 2025, 66.3 windows a day (twins' best: 51%, 47.1 windows).
- **BTC, pairs, 15 minutes, by iheat:**
  - 1m C-TSF14 above 0 while the entry minute is in minutes 00-04 of the quarter hour (ET and UTC alike): up, 51% right on 2025, 77.5 windows a day, +1.0 odds points beyond what the parts give (twins' best: 52%, 22.1 windows).
  - 1m C-TSF14 below 0 while the entry minute is in minutes 00-04 of the quarter hour (ET and UTC alike): down, 51% right on 2025, 78.3 windows a day, +1.0 odds points beyond what the parts give (twins' best: 52%, 22.1 windows).
  - 1m C-TRIMA20 above 0 while 1m HT_TRENDMODE trend: down, 53% right on 2025, 60.5 windows a day, +1.2 odds points beyond what the parts give (twins' best: 52%, 22.1 windows).
- **BTC, pairs, 15 minutes, by lheat:**
  - 1m ADOSC above 0 while 1m CORRELcv30 above 0: down, 53% right on 2025, 55.6 windows a day (twins' best: 51%, 44.4 windows).
  - 1m WAD above 0 while 15m ERIbull13 above 0: down, 52% right on 2025, 62.2 windows a day (twins' best: 51%, 44.4 windows).
  - 1m ERIbull13 above 0 while 1m CORRELcv30 above 0: down, 52% right on 2025, 62.1 windows a day (twins' best: 51%, 44.4 windows).
- **BTC, triples, 15 minutes, by oheat:**
  - 1m CDL:HIKKAKE none or 1m CDL:HIKKAKE bear while 1m IBS very low or 1m IBS low or 1m IBS mid or 1m IBS NA and 1m PVT above 0 or 1m PVT NA: down, 52% right on 2025, 84.9 windows a day (twins' best: 51%, 62.0 windows).
  - 1m ADX28 mid or 1m ADX28 high or 1m ADX28 very high or 1m ADX28 NA while 1m AROONOSC14 below 0 or 1m AROONOSC14 NA and 1m C-T3_5 below 0 or 1m C-T3_5 NA: up, 52% right on 2025, 67.8 windows a day (twins' best: 51%, 62.0 windows).
  - 1m C-CKSPmid above 0 while 1m PVO12/26 above 0 and 60m C-EMA200 low or 60m C-EMA200 mid or 60m C-EMA200 high or 60m C-EMA200 very high or 60m C-EMA200 NA: down, 53% right on 2025, 53.2 windows a day (twins' best: 51%, 62.0 windows).
- **BTC, triples, 15 minutes, by iheat:**
  - 1m CVI10 below 0 while 1m LRSLOPE14 below 0 and 1m WAD above 0: up, 51% right on 2025, 38.6 windows a day, +2.0 odds points beyond what the parts give (twins' best: 51%, 23.4 windows).
  - 1m CVI10 below 0 while 1m LRSLOPE14 below 0 and 1m ASI above 0: up, 51% right on 2025, 36.0 windows a day, +2.0 odds points beyond what the parts give (twins' best: 51%, 23.4 windows).
  - 1m CVI10 below 0 while 1m LRSLOPE14 below 0 and 1m QSTICK10 above 0: up, 51% right on 2025, 38.4 windows a day, +1.8 odds points beyond what the parts give (twins' best: 51%, 23.4 windows).
- **BTC, triples, 15 minutes, by lheat:**
  - 1m PVO12/26 above 0 while 5m C-TEMA21 above 0 and 1m C-FRAMA16 above 0: down, 54% right on 2025, 39.2 windows a day (twins' best: 51%, 41.2 windows).
  - 1m PVO12/26 above 0 while 1m KST>sig below and 1m C-T3_5 below 0: up, 53% right on 2025, 43.0 windows a day (twins' best: 51%, 41.2 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 1m C-SAR below 0: up, 54% right on 2025, 34.7 windows a day (twins' best: 51%, 41.2 windows).
- **BTC, pairs, 60 minutes, by oheat:**
  - 1m ULTOSC high while 1m CORRELcv30 above 0: down, 53% right on 2025, 16.3 windows a day (twins' best: 51%, 20.2 windows).
  - 1m AROONup25 very high while 1m CVI10 above 0: down, 53% right on 2025, 18.9 windows a day (twins' best: 51%, 20.2 windows).
  - 1m CTI20 below 0 while FLOW:TB5 low: up, 53% right on 2025, 21.3 windows a day (twins' best: 51%, 20.2 windows).
- **BTC, pairs, 60 minutes, by iheat:**
  - 1m RVOL20 very high while 1m SWAK_2PHP20 above 0: down, 52% right on 2025, 13.1 windows a day, +2.7 odds points beyond what the parts give (twins' best: 53%, 8.8 windows).
  - 1m RVOL20 very high while 1m SWAK_2PHP20 below 0: up, 53% right on 2025, 13.5 windows a day, +2.6 odds points beyond what the parts give (twins' best: 53%, 8.8 windows).
  - 1m C-LINEARREG14 above 0 while 1m RVOL20 high: down, 51% right on 2025, 22.0 windows a day, +1.5 odds points beyond what the parts give (twins' best: 53%, 8.8 windows).
- **BTC, pairs, 60 minutes, by lheat:**
  - 1m MACDh12/26/9 high while 1m CVI10 above 0: down, 53% right on 2025, 17.6 windows a day (twins' best: 53%, 11.1 windows).
  - 1m ADOSC above 0 while 15m ASI above 0: down, 53% right on 2025, 15.5 windows a day (twins' best: 53%, 11.1 windows).
  - 1m CMF20 low while 5m C-ZLEMA21 below 0: up, 54% right on 2025, 17.5 windows a day (twins' best: 53%, 11.1 windows).
- **BTC, triples, 60 minutes, by oheat:**
  - 1m CVI10 above 0 while 1m KST>sig above and 1m AROONup25 very high: down, 53% right on 2025, 18.1 windows a day (twins' best: 52%, 20.5 windows).
  - 1m PVO12/26 above 0 while 5m C-TEMA21 below 0 and FLOW:TB5 low: up, 54% right on 2025, 15.6 windows a day (twins' best: 52%, 20.5 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and 1m STOCHK14 high: down, 53% right on 2025, 16.6 windows a day (twins' best: 52%, 20.5 windows).
- **BTC, triples, 60 minutes, by iheat:**
  - 1m CVI10 below 0 while 1m LRSLOPE14 below 0 and 1m ASI above 0: down, 49% right on 2025, 20.8 windows a day, +1.6 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 48%, 11.9 windows).
  - 1m CVI10 below 0 while 1m LRSLOPE14 below 0 and 1m MOM10 above 0: down, 49% right on 2025, 21.3 windows a day, +1.4 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 48%, 11.9 windows).
  - 1m CVI10 below 0 while 1m LRSLOPE14 below 0 and 1m FISHER10 above 0: up, 51% right on 2025, 16.0 windows a day, +1.7 odds points beyond what the parts give (twins' best: 48%, 11.9 windows).
- **BTC, triples, 60 minutes, by lheat:**
  - 15m RVIR14 mid or 15m RVIR14 high or 15m RVIR14 very high or 15m RVIR14 NA while 15m WT1 mid or 15m WT1 high or 15m WT1 very high or 15m WT1 NA and 1m PVT above 0 or 1m PVT NA: down, 52% right on 2025, 21.0 windows a day (twins' best: 52%, 11.4 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and 1m AROONup25 very high: down, 53% right on 2025, 18.1 windows a day (twins' best: 52%, 11.4 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and 5m AD above 0: down, 53% right on 2025, 17.8 windows a day (twins' best: 52%, 11.4 windows).
- **BTC, pairs, 240 minutes, by oheat:**
  - 1m CCI20 above 0 while 1m NVI low: down, 54% right on 2025, 5.0 windows a day (twins' best: 57%, 2.7 windows).
  - 1m TRANGE high while FLOW:TB15 high: down, 54% right on 2025, 5.2 windows a day (twins' best: 57%, 2.7 windows).
  - 1m PDI14 high while FLOW:TB15 high: down, 54% right on 2025, 5.3 windows a day (twins' best: 57%, 2.7 windows).
- **BTC, pairs, 240 minutes, by iheat:**
  - 1m EFI13 above 0 while 1m KVO low: up, 46% right on 2025, 2.7 windows a day, +6.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 3.4 windows).
  - 1m C-VIDYA12 high while 1m MASSI low: down, 45% right on 2025, 3.4 windows a day, +5.2 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 3.4 windows).
  - 1m DX14 high while 1m KVO high: down, 53% right on 2025, 3.5 windows a day, +4.9 odds points beyond what the parts give (twins' best: 55%, 3.4 windows).
- **BTC, pairs, 240 minutes, by lheat:**
  - 1m CCI20 above 0 while 1m NVI low: down, 54% right on 2025, 5.0 windows a day (twins' best: 56%, 2.6 windows).
  - 5m LRSLOPE14 above 0 while FLOW:TB15 high: down, 53% right on 2025, 5.7 windows a day (twins' best: 56%, 2.6 windows).
  - 1m C-VIDYA12 above 0 while 1m NVI low: down, 54% right on 2025, 5.0 windows a day (twins' best: 56%, 2.6 windows).
- **BTC, triples, 240 minutes, by oheat:**
  - 5m MACDh12/26/9 above 0 while 5m CVI10 above 0 and FLOW:TB5 very high: down, 55% right on 2025, 4.1 windows a day (twins' best: 55%, 3.0 windows).
  - 1m PVO12/26 above 0 while 5m C-TEMA21 above 0 and 1m Runs 5+ up: down, 54% right on 2025, 4.5 windows a day (twins' best: 55%, 3.0 windows).
  - 1m PVO12/26 above 0 while 5m C-TEMA21 below 0 and OI:PxQuad60 long liquidation: up, 55% right on 2025, 5.3 windows a day (twins' best: 55%, 3.0 windows).
- **BTC, triples, 240 minutes, by iheat:**
  - 5m CVI10 above 0 while 15m C-LINEARREG14 above 0 and 5m KST>sig below: down, 45% right on 2025, 4.0 windows a day, +4.1 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 2.0 windows).
  - 1m VHF28 high while 5m C-TSF14 below 0 and 1m KVO above 0: up, 47% right on 2025, 3.1 windows a day, +5.2 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 2.0 windows).
  - 1m VHF28 high while 5m C-LINEARREG14 below 0 and 1m KVO above 0: up, 47% right on 2025, 2.7 windows a day, +5.3 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 2.0 windows).
- **BTC, triples, 240 minutes, by lheat:**
  - 15m TRIX30 low or 15m TRIX30 mid or 15m TRIX30 high or 15m TRIX30 very high or 15m TRIX30 NA while 60m Tenkan>Kijun above and PERP:FundZ very low or PERP:FundZ low or PERP:FundZ mid or PERP:FundZ high: down, 52% right on 2025, 3.6 windows a day (twins' best: 55%, 3.0 windows).
  - 1m ADX7 high while 5m C-LINEARREG14 below 0 and 5m HT_TRENDMODE cycle: up, 56% right on 2025, 4.4 windows a day (twins' best: 55%, 3.0 windows).
  - 1m C-ZLEMA21 above 0 while 1m RVOL20 very high and 15m HT_INPHASE above 0: down, 54% right on 2025, 4.2 windows a day (twins' best: 55%, 3.0 windows).
- **ETH, pairs, 15 minutes, by oheat:**
  - 1m ERIbear13 above 0 while 1m PVI above 0: down, 52% right on 2025, 71.2 windows a day (twins' best: 51%, 62.0 windows).
  - 1m ERIbear13 above 0 while 1m MARKETFI below 0: down, 52% right on 2025, 72.9 windows a day (twins' best: 51%, 62.0 windows).
  - 1m ERIbear13 above 0 while 5m C-FRAMA16 above 0: down, 53% right on 2025, 60.0 windows a day (twins' best: 51%, 62.0 windows).
- **ETH, pairs, 15 minutes, by iheat:**
  - 1m C-TEMA21 above 0 while 1m TRANGE high: down, 52% right on 2025, 38.7 windows a day, +2.3 odds points beyond what the parts give (twins' best: 50%, 47.8 windows).
  - 1m C-TEMA21 below 0 while 1m TRANGE high: up, 52% right on 2025, 40.5 windows a day, +2.2 odds points beyond what the parts give (twins' best: 50%, 47.8 windows).
  - 1m C-TSF14 above 0 while the entry minute is in minutes 00-04 of the quarter hour (ET and UTC alike): up, 52% right on 2025, 77.9 windows a day, +1.1 odds points beyond what the parts give (twins' best: 50%, 47.8 windows).
- **ETH, pairs, 15 minutes, by lheat:**
  - 1m ERIbear13 above 0 while 5m ERIbull13 above 0: down, 53% right on 2025, 64.6 windows a day (twins' best: 52%, 31.5 windows).
  - 1m C-FRAMA16 above 0 while 5m ERIbull13 above 0: down, 52% right on 2025, 72.2 windows a day (twins' best: 52%, 31.5 windows).
  - 1m C-VWMA20 above 0 while 1m CORRELcv30 above 0: down, 53% right on 2025, 55.4 windows a day (twins' best: 52%, 31.5 windows).
- **ETH, triples, 15 minutes, by oheat:**
  - 1m PVI above 0 or 1m PVI NA while 5m C-KAMA30 above 0 or 5m C-KAMA30 NA and the entry minute is minute 0 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 1 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 2 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 3 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 4 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 5 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 7 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 8 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 12 of the Kalshi quarter hour (ET and UTC alike) or POS:QPos NA: down, 53% right on 2025, 51.8 windows a day (twins' best: 51%, 51.1 windows).
  - 1m ADX28 mid or 1m ADX28 high or 1m ADX28 very high while 1m C-T3_5 above 0 and 1m KST above 0: down, 53% right on 2025, 55.0 windows a day (twins' best: 51%, 51.1 windows).
  - 1m ADX28 mid or 1m ADX28 high or 1m ADX28 very high or 1m ADX28 NA while 1m C-ALMA9 above 0 or 1m C-ALMA9 NA and 1m CORRELcv30 above 0 or 1m CORRELcv30 NA: down, 53% right on 2025, 57.4 windows a day (twins' best: 51%, 51.1 windows).
- **ETH, triples, 15 minutes, by iheat:**
  - 1m PERCENTB20/2 very low or 1m PERCENTB20/2 low or 1m PERCENTB20/2 high or 1m PERCENTB20/2 very high while 1m STOCHFK5 very low or 1m STOCHFK5 low or 1m STOCHFK5 mid or 1m STOCHFK5 NA and 5m C-FRAMA16 below 0 or 5m C-FRAMA16 NA: up, 54% right on 2025, 42.7 windows a day, +1.6 odds points beyond what the parts give (twins' best: 49%, 27.8 windows).
  - 1m MACDh12/26/9 below 0 while 1m CVI10 above 0 and 1m PVO12/26 below 0: up, 51% right on 2025, 43.9 windows a day, +1.6 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 49%, 27.8 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m LRSLOPE14 above 0: down, 50% right on 2025, 39.1 windows a day, +1.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 49%, 27.8 windows).
- **ETH, triples, 15 minutes, by lheat:**
  - 1m ADX28 mid or 1m ADX28 high or 1m ADX28 very high or 1m ADX28 NA while 1m C-ALMA9 above 0 or 1m C-ALMA9 NA and 1m CORRELcv30 above 0 or 1m CORRELcv30 NA: down, 53% right on 2025, 57.4 windows a day (twins' best: 50%, 37.0 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m ERIbull13 above 0: down, 53% right on 2025, 40.3 windows a day (twins' best: 50%, 37.0 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m QSTICK10 above 0: down, 54% right on 2025, 35.9 windows a day (twins' best: 50%, 37.0 windows).
- **ETH, pairs, 60 minutes, by oheat:**
  - 1m AROONup25 very high while 1m C-TSF14 above 0: down, 52% right on 2025, 20.4 windows a day (twins' best: 52%, 17.8 windows).
  - 1m AROONup14 very high while 1m CVI10 above 0: down, 52% right on 2025, 21.0 windows a day (twins' best: 52%, 17.8 windows).
  - 1m AROONup25 very high while 1m C-AVGPRICE above 0: down, 52% right on 2025, 20.5 windows a day (twins' best: 52%, 17.8 windows).
- **ETH, pairs, 60 minutes, by iheat:**
  - 1m STOCHRSI14 very high while 1m RVOL20 high: down, 53% right on 2025, 15.1 windows a day, +2.5 odds points beyond what the parts give (twins' best: 48%, 15.9 windows).
  - 1m DX14 low while 1m ERIbear13 above 0: up, 52% right on 2025, 12.1 windows a day, +3.0 odds points beyond what the parts give (twins' best: 48%, 15.9 windows).
  - 1m TRANGE high while 1m SWAK_2PHP20 above 0: down, 51% right on 2025, 21.2 windows a day, +1.7 odds points beyond what the parts give (twins' best: 48%, 15.9 windows).
- **ETH, pairs, 60 minutes, by lheat:**
  - 1m C-TSF14 above 0 while 1m PERCENTB20/2 very high: down, 53% right on 2025, 13.0 windows a day (twins' best: 52%, 17.8 windows).
  - 1m C-LINEARREG14 above 0 while 1m C-VWAP20 high: down, 52% right on 2025, 19.1 windows a day (twins' best: 52%, 17.8 windows).
  - 1m C-KAMA30 below 0 while 60m MAMA>FAMA below: up, 56% right on 2025, 11.8 windows a day (twins' best: 52%, 17.8 windows).
- **ETH, triples, 60 minutes, by oheat:**
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 1m AROONup14 very high: down, 52% right on 2025, 20.9 windows a day (twins' best: 52%, 19.2 windows).
  - 1m AROONup25 high or 1m AROONup25 very high while 1m C-SUPERTREND10/3 high or 1m C-SUPERTREND10/3 very high and 1m TRIX15 very low or 1m TRIX15 low or 1m TRIX15 mid or 1m TRIX15 NA: down, 53% right on 2025, 18.7 windows a day (twins' best: 52%, 19.2 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 1m AROONup25 very high: down, 53% right on 2025, 18.4 windows a day (twins' best: 52%, 19.2 windows).
- **ETH, triples, 60 minutes, by iheat:**
  - 1m CVI10 above 0 while 1m KST>sig above and 1m LRSLOPE14 below 0: up, 54% right on 2025, 14.0 windows a day, +2.2 odds points beyond what the parts give (twins' best: 48%, 7.1 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and 1m MOM10 below 0: up, 53% right on 2025, 17.3 windows a day, +1.8 odds points beyond what the parts give (twins' best: 48%, 7.1 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and 1m EMV14 below 0: up, 53% right on 2025, 17.2 windows a day, +1.8 odds points beyond what the parts give (twins' best: 48%, 7.1 windows).
- **ETH, triples, 60 minutes, by lheat:**
  - 1m CVI10 above 0 while 1m KST>sig above and 1m SWAK_BP20 above 0: down, 51% right on 2025, 22.5 windows a day (twins' best: 51%, 17.3 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 5m ERIbull13 above 0: down, 51% right on 2025, 21.4 windows a day (twins' best: 51%, 17.3 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 5m WAD above 0: down, 52% right on 2025, 19.0 windows a day (twins' best: 51%, 17.3 windows).
- **ETH, pairs, 240 minutes, by oheat:**
  - 1m CMF20 low while 60m CTI20 below 0: up, 60% right on 2025, 3.1 windows a day (twins' best: 55%, 3.2 windows).
  - 1m C-ALMA9 very high while 60m C-SMA20 above 0: down, 56% right on 2025, 3.3 windows a day (twins' best: 55%, 3.2 windows).
  - 1m C-ALMA9 very high while 5m STOCH14 K>D above: down, 54% right on 2025, 4.8 windows a day (twins' best: 55%, 3.2 windows).
- **ETH, pairs, 240 minutes, by iheat:**
  - 1m DX14 high while 1m C-SAR high: down, 54% right on 2025, 4.0 windows a day, +4.3 odds points beyond what the parts give (twins' best: 55%, 3.0 windows).
  - 1m C-HMA20 high while 5m Runs 3-4 up: down, 54% right on 2025, 3.1 windows a day, +5.3 odds points beyond what the parts give (twins' best: 55%, 3.0 windows).
  - 1m DX14 low while 1m WILLR14 low: down, 53% right on 2025, 3.4 windows a day, +4.8 odds points beyond what the parts give (twins' best: 55%, 3.0 windows).
- **ETH, pairs, 240 minutes, by lheat:**
  - 1m C-ALMA9 very high while 5m STOCH14 K>D above: down, 54% right on 2025, 4.8 windows a day (twins' best: 55%, 3.0 windows).
  - 1m C-ALMA9 very high while 5m FISHER>trig above: down, 54% right on 2025, 4.7 windows a day (twins' best: 55%, 3.0 windows).
  - 1m SWAK_HP20 very high while 5m STOCH14 K>D above: down, 54% right on 2025, 4.8 windows a day (twins' best: 55%, 3.0 windows).
- **ETH, triples, 240 minutes, by oheat:**
  - 1m PVO12/26 above 0 while 5m C-HMA20 above 0 and 1m C-ALMA9 very high: down, 54% right on 2025, 4.6 windows a day (twins' best: 59%, 1.7 windows).
  - 1m PVO12/26 above 0 while 5m C-HMA20 above 0 and 1m SWAK_HP20 very high: down, 53% right on 2025, 4.7 windows a day (twins' best: 59%, 1.7 windows).
  - 1m PVO12/26 above 0 while 5m C-HMA20 above 0 and 1m ACCBANDS20pos very high: down, 54% right on 2025, 3.9 windows a day (twins' best: 59%, 1.7 windows).
- **ETH, triples, 240 minutes, by iheat:**
  - 1m SINE>LEAD above while 1m HT_TRENDMODE trend and 1m C-TSF14 very low: down, 54% right on 2025, 3.4 windows a day, +4.8 odds points beyond what the parts give (twins' best: 44%, 3.0 windows).
  - 1m PVO12/26 high while 5m C-TSF14 above 0 and 1m C-VWMA20 below 0: up, 54% right on 2025, 4.2 windows a day, +3.3 odds points beyond what the parts give (twins' best: 44%, 3.0 windows).
  - 1m CVI10 above 0 while 1m KST>sig above and OI:Chg15 low: down, 54% right on 2025, 3.1 windows a day, +4.5 odds points beyond what the parts give (twins' best: 44%, 3.0 windows).
- **ETH, triples, 240 minutes, by lheat:**
  - 1m PVI mid or 1m PVI high or 1m PVI very high or 1m PVI NA while 60m PVT very low or 60m PVT low or 60m PVT mid or 60m PVT high or 60m PVT NA and 60m SQZMOM above 0 or 60m SQZMOM NA: down, 53% right on 2025, 3.6 windows a day (twins' best: 54%, 3.2 windows).
  - 15m C-KAMA30 below 0 while 60m SMI very low or 60m SMI low or 60m SMI mid and the half hour 12:00 AM-12:30 AM ET (05:00 UTC in winter, 04:00 UTC in summer) or the half hour 12:30 AM-1:00 AM ET (05:30 UTC in winter, 04:30 UTC in summer) or the half hour 1:00 AM-1:30 AM ET (06:00 UTC in winter, 05:00 UTC in summer) or the half hour 1:30 AM-2:00 AM ET (06:30 UTC in winter, 05:30 UTC in summer) or the half hour 3:00 AM-3:30 AM ET (08:00 UTC in winter, 07:00 UTC in summer) or the half hour 3:30 AM-4:00 AM ET (08:30 UTC in winter, 07:30 UTC in summer) or the half hour 4:30 AM-5:00 AM ET (09:30 UTC in winter, 08:30 UTC in summer) or the half hour 5:30 AM-6:00 AM ET (10:30 UTC in winter, 09:30 UTC in summer) or the half hour 6:00 AM-6:30 AM ET (11:00 UTC in winter, 10:00 UTC in summer) or the half hour 6:30 AM-7:00 AM ET (11:30 UTC in winter, 10:30 UTC in summer) or the half hour 7:00 AM-7:30 AM ET (12:00 UTC in winter, 11:00 UTC in summer) or the half hour 7:30 AM-8:00 AM ET (12:30 UTC in winter, 11:30 UTC in summer) or the half hour 8:00 AM-8:30 AM ET (13:00 UTC in winter, 12:00 UTC in summer) or the half hour 9:30 AM-10:00 AM ET (14:30 UTC in winter, 13:30 UTC in summer) or the half hour 10:00 AM-10:30 AM ET (15:00 UTC in winter, 14:00 UTC in summer) or the half hour 11:30 AM-12:00 PM ET (16:30 UTC in winter, 15:30 UTC in summer) or the half hour 12:00 PM-12:30 PM ET (17:00 UTC in winter, 16:00 UTC in summer) or the half hour 12:30 PM-1:00 PM ET (17:30 UTC in winter, 16:30 UTC in summer) or the half hour 1:00 PM-1:30 PM ET (18:00 UTC in winter, 17:00 UTC in summer) or the half hour 1:30 PM-2:00 PM ET (18:30 UTC in winter, 17:30 UTC in summer) or the half hour 2:00 PM-2:30 PM ET (19:00 UTC in winter, 18:00 UTC in summer) or the half hour 2:30 PM-3:00 PM ET (19:30 UTC in winter, 18:30 UTC in summer) or the half hour 3:00 PM-3:30 PM ET (20:00 UTC in winter, 19:00 UTC in summer) or the half hour 3:30 PM-4:00 PM ET (20:30 UTC in winter, 19:30 UTC in summer) or the half hour 4:00 PM-4:30 PM ET (21:00 UTC in winter, 20:00 UTC in summer) or the half hour 4:30 PM-5:00 PM ET (21:30 UTC in winter, 20:30 UTC in summer) or the half hour 5:00 PM-5:30 PM ET (22:00 UTC in winter, 21:00 UTC in summer) or the half hour 5:30 PM-6:00 PM ET (22:30 UTC in winter, 21:30 UTC in summer) or the half hour 6:00 PM-6:30 PM ET (23:00 UTC in winter, 22:00 UTC in summer) or the half hour 6:30 PM-7:00 PM ET (23:30 UTC in winter, 22:30 UTC in summer) or the half hour 7:00 PM-7:30 PM ET (00:00 UTC in winter, 23:00 UTC in summer) or the half hour 7:30 PM-8:00 PM ET (00:30 UTC in winter, 23:30 UTC in summer) or the half hour 8:00 PM-8:30 PM ET (01:00 UTC in winter, 00:00 UTC in summer) or the half hour 8:30 PM-9:00 PM ET (01:30 UTC in winter, 00:30 UTC in summer) or the half hour 9:00 PM-9:30 PM ET (02:00 UTC in winter, 01:00 UTC in summer) or the half hour 9:30 PM-10:00 PM ET (02:30 UTC in winter, 01:30 UTC in summer) or the half hour 10:00 PM-10:30 PM ET (03:00 UTC in winter, 02:00 UTC in summer) or the half hour 10:30 PM-11:00 PM ET (03:30 UTC in winter, 02:30 UTC in summer) or the half hour 11:00 PM-11:30 PM ET (04:00 UTC in winter, 03:00 UTC in summer) or the half hour 11:30 PM-12:00 AM ET (04:30 UTC in winter, 03:30 UTC in summer) or NY30m NA: up, 55% right on 2025, 4.3 windows a day (twins' best: 54%, 3.2 windows).
  - 5m MACDh12/26/9 above 0 while 5m CVI10 above 0 and 5m KST>sig above: down, 51% right on 2025, 5.4 windows a day (twins' best: 54%, 3.2 windows).
- **SOL, pairs, 15 minutes, by oheat:**
  - 1m AROONOSC25 above 0 while 1m C-FRAMA16 above 0: down, 51% right on 2025, 62.5 windows a day (twins' best: 51%, 31.0 windows).
  - 1m AROONOSC25 above 0 while 1m FISHER>trig above: down, 51% right on 2025, 62.5 windows a day (twins' best: 51%, 31.0 windows).
  - 1m AROONOSC25 above 0 while 1m ERIbear13 above 0: down, 51% right on 2025, 57.7 windows a day (twins' best: 51%, 31.0 windows).
- **SOL, pairs, 15 minutes, by iheat:**
  - 1m C-SWAK_GAUSS20 low while 5m WAD above 0: up, 51% right on 2025, 25.8 windows a day, +2.1 odds points beyond what the parts give (twins' best: 50%, 48.2 windows).
  - 1m ERIbear13 above 0 while the entry minute is minute 0 of the Kalshi quarter hour (ET and UTC alike): down, 52% right on 2025, 34.4 windows a day, +1.6 odds points beyond what the parts give (twins' best: 50%, 48.2 windows).
  - 1m ERIbear13 below 0 while the entry minute is minute 0 of the Kalshi quarter hour (ET and UTC alike): up, 51% right on 2025, 61.6 windows a day, +0.9 odds points beyond what the parts give (twins' best: 50%, 48.2 windows).
- **SOL, pairs, 15 minutes, by lheat:**
  - 1m ERIbull13 above 0 while 1m ERIbear13 above 0: down, 50% right on 2025, 77.1 windows a day (twins' best: 49%, 72.5 windows).
  - 1m TRIX30 above 0 while 1m C-FRAMA16 above 0: down, 51% right on 2025, 52.2 windows a day (twins' best: 49%, 72.5 windows).
  - 1m ERIbear13 above 0 while 5m WAD above 0: down, 51% right on 2025, 52.2 windows a day (twins' best: 49%, 72.5 windows).
- **SOL, triples, 15 minutes, by oheat:**
  - 15m C-DEMA21 mid or 15m C-DEMA21 high or 15m C-DEMA21 very high or 15m C-DEMA21 NA while 1m AROONup25 very high and 1m C-EMA9 mid or 1m C-EMA9 high or 1m C-EMA9 very high or 1m C-EMA9 NA: down, 51% right on 2025, 43.5 windows a day (twins' best: 50%, 43.2 windows).
  - 1m PVT above 0 while 5m WAD mid or 5m WAD high or 5m WAD very high and PERP:Basis very low or PERP:Basis low or PERP:Basis mid: down, 50% right on 2025, 82.3 windows a day (twins' best: 50%, 43.2 windows).
  - 1m C-AVGPRICE above 0 while 1m MACD5/35 above 0 and the entry minute is minute 0 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 4 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 10 of the Kalshi quarter hour (ET and UTC alike) or the entry minute is minute 13 of the Kalshi quarter hour (ET and UTC alike): down, 51% right on 2025, 56.1 windows a day (twins' best: 50%, 43.2 windows).
- **SOL, triples, 15 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m HT_INPHASE above 0: up, 50% right on 2025, 48.6 windows a day, +1.1 odds points beyond what the parts give (twins' best: 49%, 40.5 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE cycle and 1m CCI20 below 0: up, 49% right on 2025, 43.7 windows a day, +1.1 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 49%, 40.5 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m C-WMA20 above 0: down, 48% right on 2025, 50.6 windows a day, +1.0 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 49%, 40.5 windows).
- **SOL, triples, 15 minutes, by lheat:**
  - 1m PVT above 0 while 5m WAD mid or 5m WAD high or 5m WAD very high and PERP:Basis very low or PERP:Basis low or PERP:Basis mid: down, 50% right on 2025, 82.3 windows a day (twins' best: 50%, 35.2 windows).
  - 1m KVO above 0 while 1m PVO12/26 above 0 and 5m CMF20 above 0: down, 52% right on 2025, 30.3 windows a day (twins' best: 50%, 35.2 windows).
  - 1m KVO above 0 while 1m PVO12/26 above 0 and 1m EFI13 above 0: down, 51% right on 2025, 40.9 windows a day (twins' best: 50%, 35.2 windows).
- **SOL, pairs, 60 minutes, by oheat:**
  - 1m TakerBuy low while 5m NVI above 0: up, 54% right on 2025, 14.3 windows a day (twins' best: 54%, 11.1 windows).
  - 1m C-TEMA21 above 0 while FLOW:TB5 high: down, 51% right on 2025, 18.6 windows a day (twins' best: 54%, 11.1 windows).
  - 1m FISHER10 below 0 while 1m TakerBuy low: up, 53% right on 2025, 16.9 windows a day (twins' best: 54%, 11.1 windows).
- **SOL, pairs, 60 minutes, by iheat:**
  - 1m DOSC above 0 while 1m HT_INPHASE low: up, 52% right on 2025, 12.9 windows a day, +2.2 odds points beyond what the parts give (twins' best: 53%, 9.3 windows).
  - 1m QSTICK10 high while 1m PVO12/26 below 0: down, 48% right on 2025, 16.3 windows a day, +1.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 53%, 9.3 windows).
  - 1m KDJ K>D below while ETH's last 5 minutes high: down, 53% right on 2025, 7.7 windows a day, +3.5 odds points beyond what the parts give (twins' best: 53%, 9.3 windows).
- **SOL, pairs, 60 minutes, by lheat:**
  - 1m C-SMA50 below 0 while 5m NVI above 0: up, 53% right on 2025, 17.5 windows a day (twins' best: 51%, 17.1 windows).
  - 1m DIdiff14 below 0 while 5m NVI above 0: up, 52% right on 2025, 18.7 windows a day (twins' best: 51%, 17.1 windows).
  - 1m RSI7 low while 60m HT_TRENDMODE trend: up, 54% right on 2025, 12.8 windows a day (twins' best: 51%, 17.1 windows).
- **SOL, triples, 60 minutes, by oheat:**
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 15m FOSC5 above 0: down, 51% right on 2025, 19.3 windows a day (twins' best: 52%, 8.6 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 5m DPO20 below 0: down, 51% right on 2025, 19.5 windows a day (twins' best: 52%, 8.6 windows).
  - 1m SINE>LEAD above while 1m HT_TRENDMODE cycle and FLOW:TB5 high: down, 52% right on 2025, 13.8 windows a day (twins' best: 52%, 8.6 windows).
- **SOL, triples, 60 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 5m C-MIDPOINT14 above 0: down, 45% right on 2025, 7.5 windows a day, +3.4 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 51%, 17.6 windows).
  - 1m KVO below 0 while 1m PVO12/26 above 0 and the entry minute is in minutes 45-59 of the hour (ET and UTC alike): up, 53% right on 2025, 12.3 windows a day, +2.0 odds points beyond what the parts give (twins' best: 51%, 17.6 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 5m FOSC5 above 0: up, 51% right on 2025, 21.8 windows a day, +1.1 odds points beyond what the parts give (twins' best: 51%, 17.6 windows).
- **SOL, triples, 60 minutes, by lheat:**
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 15m FOSC5 above 0: down, 51% right on 2025, 19.3 windows a day (twins' best: 51%, 13.7 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 5m QSTICK10 above 0: down, 51% right on 2025, 18.3 windows a day (twins' best: 51%, 13.7 windows).
  - 1m MACDh12/26/9 above 0 while 1m CVI10 above 0 and 5m ERIbull13 above 0: down, 51% right on 2025, 21.4 windows a day (twins' best: 51%, 13.7 windows).
- **SOL, pairs, 240 minutes, by oheat:**
  - 1m AROONOSC25 very low while 60m HT_TRENDMODE trend: up, 56% right on 2025, 4.0 windows a day (twins' best: 56%, 3.1 windows).
  - 1m PDI14 low while 60m HT_TRENDMODE trend: up, 56% right on 2025, 3.9 windows a day (twins' best: 56%, 3.1 windows).
  - 1m FISHER10 low while 1m CDL:HIKKAKE bull: up, 56% right on 2025, 3.4 windows a day (twins' best: 56%, 3.1 windows).
- **SOL, pairs, 240 minutes, by iheat:**
  - 5m FISHER10 below 0 while OI:PxQuad60 short covering: down, 52% right on 2025, 4.5 windows a day, +3.8 odds points beyond what the parts give (twins' best: 55%, 2.5 windows).
  - 1m FISHER10 low while 1m OBVdiv10 bull div: up, 47% right on 2025, 3.3 windows a day, +4.7 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 55%, 2.5 windows).
  - 5m C-VWAP20 below 0 while OI:PxQuad60 short covering: down, 51% right on 2025, 4.5 windows a day, +3.4 odds points beyond what the parts give (twins' best: 55%, 2.5 windows).
- **SOL, pairs, 240 minutes, by lheat:**
  - 1m PDI14 low while 60m HT_TRENDMODE trend: up, 56% right on 2025, 3.9 windows a day (twins' best: 56%, 3.1 windows).
  - 1m ERIbear13 high while 5m C-FRAMA16 below 0: down, 53% right on 2025, 4.9 windows a day (twins' best: 56%, 3.1 windows).
  - 5m C-LINEARREG14 low while 5m PVO12/26 below 0: up, 54% right on 2025, 4.7 windows a day (twins' best: 56%, 3.1 windows).
- **SOL, triples, 240 minutes, by oheat:**
  - 5m FOSC5 below 0 while the entry minute is in minutes 10-14 of the quarter hour (ET and UTC alike) and 1m RVI14 low: up, 54% right on 2025, 5.3 windows a day (twins' best: 54%, 3.7 windows).
  - 5m FOSC5 below 0 while the entry minute is in minutes 10-14 of the quarter hour (ET and UTC alike) and 1m AROONOSC25 low: up, 54% right on 2025, 4.7 windows a day (twins' best: 54%, 3.7 windows).
  - 5m FOSC5 below 0 while the entry minute is in minutes 10-14 of the quarter hour (ET and UTC alike) and 1m MASSI low: up, 55% right on 2025, 3.1 windows a day (twins' best: 54%, 3.7 windows).
- **SOL, triples, 240 minutes, by iheat:**
  - 5m Tenkan>Kijun above while 5m HT_TRENDMODE trend and XRP's 1m RSI14 low: down, 52% right on 2025, 3.3 windows a day, +4.8 odds points beyond what the parts give (twins' best: 55%, 2.7 windows).
  - 5m CMOU14 above 0 while 5m HT_TRENDMODE trend and XRP's 1m RSI14 low: down, 53% right on 2025, 3.1 windows a day, +5.1 odds points beyond what the parts give (twins' best: 55%, 2.7 windows).
  - 1m C-MAMA high while the entry minute is in minutes 00-04 of the quarter hour (ET and UTC alike) and 1m C-LINEARREG14 below 0: down, 54% right on 2025, 3.3 windows a day, +4.1 odds points beyond what the parts give (twins' best: 55%, 2.7 windows).
- **SOL, triples, 240 minutes, by lheat:**
  - 5m FOSC5 below 0 while the entry minute is in minutes 10-14 of the quarter hour (ET and UTC alike) and 1m AROONOSC25 low: up, 54% right on 2025, 4.7 windows a day (twins' best: 54%, 4.0 windows).
  - 1m C-MAMA high while the entry minute is in minutes 00-04 of the quarter hour (ET and UTC alike) and 1m C-LINEARREG14 below 0: down, 54% right on 2025, 3.3 windows a day (twins' best: 54%, 4.0 windows).
  - 1m VHF28 high while 5m C-TSF14 above 0 and 5m OBV below 0: up, 56% right on 2025, 3.1 windows a day (twins' best: 54%, 4.0 windows).
- **XRP, pairs, 15 minutes, by oheat:**
  - 1m C-SMA20 below 0 while 1m HT_TRENDMODE trend: up, 52% right on 2025, 59.8 windows a day (twins' best: 51%, 41.6 windows).
  - 1m ERIbull13 below 0 while 1m HT_TRENDMODE trend: up, 53% right on 2025, 47.7 windows a day (twins' best: 51%, 41.6 windows).
  - 1m QSTICK10 below 0 while 1m HT_TRENDMODE trend: up, 52% right on 2025, 63.9 windows a day (twins' best: 51%, 41.6 windows).
- **XRP, pairs, 15 minutes, by iheat:**
  - 1m C-MIDPOINT14 above 0 while 1m HT_TRENDMODE trend: down, 51% right on 2025, 63.3 windows a day, +1.3 odds points beyond what the parts give (twins' best: 50%, 47.9 windows).
  - 1m C-VWAP20 below 0 while 1m HT_TRENDMODE trend: up, 52% right on 2025, 60.7 windows a day, +1.3 odds points beyond what the parts give (twins' best: 50%, 47.9 windows).
  - 1m CCI20 above 0 while 1m HT_TRENDMODE trend: down, 52% right on 2025, 57.7 windows a day, +1.3 odds points beyond what the parts give (twins' best: 50%, 47.9 windows).
- **XRP, pairs, 15 minutes, by lheat:**
  - 1m C-MIDPOINT14 below 0 while 1m HT_TRENDMODE trend: up, 52% right on 2025, 63.7 windows a day (twins' best: 50%, 49.2 windows).
  - 1m PVT above 0 while 15m ERIbull13 above 0: down, 51% right on 2025, 61.7 windows a day (twins' best: 50%, 49.2 windows).
  - 1m QSTICK10 below 0 while 1m HT_TRENDMODE trend: up, 52% right on 2025, 63.9 windows a day (twins' best: 50%, 49.2 windows).
- **XRP, triples, 15 minutes, by oheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 1m C-FRAMA16 below 0: up, 53% right on 2025, 35.2 windows a day (twins' best: 51%, 35.1 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 1m C-SAR below 0: up, 53% right on 2025, 34.3 windows a day (twins' best: 51%, 35.1 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 1m C-SMA20 below 0: up, 53% right on 2025, 38.5 windows a day (twins' best: 51%, 35.1 windows).
- **XRP, triples, 15 minutes, by iheat:**
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m LRSLOPE14 above 0: up, 49% right on 2025, 38.3 windows a day, +2.2 odds points beyond what the parts give (twins' best: 48%, 43.5 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m CMOU14 above 0: down, 50% right on 2025, 41.3 windows a day, +1.8 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 48%, 43.5 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE cycle and 1m QSTICK10 above 0: up, 49% right on 2025, 47.5 windows a day, +1.5 odds points beyond what the parts give (twins' best: 48%, 43.5 windows).
- **XRP, triples, 15 minutes, by lheat:**
  - 15m C-FRAMA16 below 0 while 1m EFI13 very low or 1m EFI13 low or 1m EFI13 mid or 1m EFI13 NA and 1m PVI very low or 1m PVI low or 1m PVI mid or 1m PVI NA: up, 51% right on 2025, 47.2 windows a day (twins' best: 50%, 43.3 windows).
  - 1m SINE>LEAD below while 1m HT_TRENDMODE trend and 5m ERIbear13 below 0: up, 52% right on 2025, 41.8 windows a day (twins' best: 50%, 43.3 windows).
  - 15m VORTEXdiff14 mid or 15m VORTEXdiff14 high or 15m VORTEXdiff14 very high while 1m HAbody above 0 or 1m HAbody NA and 5m AVGDEV14 mid or 5m AVGDEV14 high or 5m AVGDEV14 very high: down, 50% right on 2025, 78.6 windows a day (twins' best: 50%, 43.3 windows).
- **XRP, pairs, 60 minutes, by oheat:**
  - 1m KST above 0 while 1m C-FRAMA16 high: down, 53% right on 2025, 16.8 windows a day (twins' best: 52%, 13.6 windows).
  - 1m ERIbear13 above 0 while 5m C-TSF14 below 0: down, 52% right on 2025, 19.1 windows a day (twins' best: 52%, 13.6 windows).
  - 1m C-FRAMA16 high while 15m C-ALMA9 above 0: down, 53% right on 2025, 14.5 windows a day (twins' best: 52%, 13.6 windows).
- **XRP, pairs, 60 minutes, by iheat:**
  - 1m MACDh12/26/9 above 0 while 1m PVO12/26 high: down, 52% right on 2025, 13.9 windows a day, +2.3 odds points beyond what the parts give (twins' best: 54%, 6.4 windows).
  - 1m WILLR14 low while 5m HAbody above 0: up, 52% right on 2025, 15.0 windows a day, +2.1 odds points beyond what the parts give (twins' best: 54%, 6.4 windows).
  - 1m ERIbull13 low while 1m PVO12/26 below 0: up, 49% right on 2025, 16.6 windows a day, +1.8 odds points beyond what the parts give (the pair holds the call back: a stand-aside lesson) (twins' best: 54%, 6.4 windows).
- **XRP, pairs, 60 minutes, by lheat:**
  - 1m CCI14 high while 1m C-TEMA21 above 0: down, 52% right on 2025, 22.5 windows a day (twins' best: 51%, 13.6 windows).
  - 1m C-TEMA21 below 0 while 1m C-SUPERTREND10/3 very low: up, 53% right on 2025, 14.8 windows a day (twins' best: 51%, 13.6 windows).
  - 1m AROONdn25 very high while 1m C-DEMA21 below 0: up, 52% right on 2025, 21.2 windows a day (twins' best: 51%, 13.6 windows).
- **XRP, triples, 60 minutes, by oheat:**
  - 15m BOP below 0 while 1m C-EMA21 very low or 1m C-EMA21 low and 1m SI very low or 1m SI low or 1m SI high or 1m SI NA: up, 54% right on 2025, 13.5 windows a day (twins' best: 52%, 12.2 windows).
  - 15m BOP below 0 while 1m CG10 very low or 1m CG10 low and 1m ERIbull13 below 0 or 1m ERIbull13 NA: up, 55% right on 2025, 10.6 windows a day (twins' best: 52%, 12.2 windows).
  - 1m MACDh12/26/9 above 0 while 1m PVO12/26 above 0 and 5m CMF20 above 0: down, 53% right on 2025, 15.7 windows a day (twins' best: 52%, 12.2 windows).
- **XRP, triples, 60 minutes, by iheat:**
  - 1m MACDh12/26/9 above 0 while 1m PVO12/26 above 0 and 1m ER10 low: up, 50% right on 2025, 11.2 windows a day, +2.3 odds points beyond what the parts give (twins' best: 45%, 3.9 windows).
  - 1m CVI10 above 0 while 5m SWAK_2PHP20 above 0 and 1m ERIbull13 below 0: up, 52% right on 2025, 13.8 windows a day, +1.9 odds points beyond what the parts give (twins' best: 45%, 3.9 windows).
  - 1m CVI10 above 0 while 5m SWAK_2PHP20 below 0 and 1m VORTEXdiff14 above 0: down, 52% right on 2025, 18.0 windows a day, +1.4 odds points beyond what the parts give (twins' best: 45%, 3.9 windows).
- **XRP, triples, 60 minutes, by lheat:**
  - 1m CMF20 very low or 1m CMF20 low or 1m CMF20 mid or 1m CMF20 NA while 1m PERCENTB20/2 very low or 1m PERCENTB20/2 low or 1m PERCENTB20/2 NA and 1m PVI very low or 1m PVI low or 1m PVI mid: up, 52% right on 2025, 21.9 windows a day (twins' best: 51%, 19.4 windows).
  - 1m MACDh12/26/9 above 0 while 1m PVO12/26 above 0 and 5m C-TEMA21 above 0: down, 52% right on 2025, 19.7 windows a day (twins' best: 51%, 19.4 windows).
  - 1m PVO12/26 above 0 while 5m C-LINEARREG14 below 0 and 1m HT_TRENDMODE trend: up, 52% right on 2025, 17.8 windows a day (twins' best: 51%, 19.4 windows).
- **XRP, pairs, 240 minutes, by oheat:**
  - 1m CG10 low while the entry minute is in minutes 10-14 of the quarter hour (ET and UTC alike): up, 55% right on 2025, 4.5 windows a day (twins' best: 56%, 3.9 windows).
  - 1m C-MAMA low while SOL's 1m RSI14 low: up, 54% right on 2025, 5.6 windows a day (twins' best: 56%, 3.9 windows).
  - 1m CG10 low while 1m CDL:LONGLINE bear: up, 56% right on 2025, 3.9 windows a day (twins' best: 56%, 3.9 windows).
- **XRP, pairs, 240 minutes, by iheat:**
  - 1m LRSLOPE14 low while 5m FISHER>trig above: up, 54% right on 2025, 4.4 windows a day, +3.9 odds points beyond what the parts give (twins' best: 54%, 4.5 windows).
  - 1m PSO low while 5m MACDh5/35/5 above 0: up, 54% right on 2025, 4.8 windows a day, +3.6 odds points beyond what the parts give (twins' best: 54%, 4.5 windows).
  - 1m LRSLOPE14 low while 5m C-LINEARREG14 above 0: up, 57% right on 2025, 2.8 windows a day, +6.1 odds points beyond what the parts give (twins' best: 54%, 4.5 windows).
- **XRP, pairs, 240 minutes, by lheat:**
  - 1m IMI14 very high while 15m C-ZLEMA21 above 0: down, 57% right on 2025, 2.9 windows a day (twins' best: 55%, 5.1 windows).
  - 1m CMOU14 very high while 15m C-ZLEMA21 above 0: down, 55% right on 2025, 3.7 windows a day (twins' best: 55%, 5.1 windows).
  - 1m CCI14 very high while 5m HT_SINE below 0: down, 54% right on 2025, 4.6 windows a day (twins' best: 55%, 5.1 windows).
- **XRP, triples, 240 minutes, by oheat:**
  - 1m DOSC above 0 while 1m ER10 high and 15m FISHER>trig above: down, 54% right on 2025, 4.9 windows a day (twins' best: 56%, 2.8 windows).
  - 1m DOSC above 0 while 1m ER10 high and 15m HT_QUADRATURE above 0: down, 54% right on 2025, 5.2 windows a day (twins' best: 56%, 2.8 windows).
  - 15m BOP below 0 while 1m CG10 very low or 1m CG10 low and 5m EMV14 mid or 5m EMV14 high or 5m EMV14 very high: up, 55% right on 2025, 4.5 windows a day (twins' best: 56%, 2.8 windows).
- **XRP, triples, 240 minutes, by iheat:**
  - 1m DOSC below 0 while 1m ER10 high and 5m C-HMA20 above 0: up, 57% right on 2025, 2.9 windows a day, +5.8 odds points beyond what the parts give (twins' best: 48%, 4.0 windows).
  - 1m MACDh12/26/9 above 0 while 1m PVO12/26 above 0 and 1m ER10 very high: down, 57% right on 2025, 2.7 windows a day, +5.2 odds points beyond what the parts give (twins' best: 48%, 4.0 windows).
  - 1m C-SMA20 very low or 1m C-SMA20 low or 1m C-SMA20 mid or 1m C-SMA20 NA while 1m IMI14 high or 1m IMI14 very high and FLOW:Stretch15 very low or FLOW:Stretch15 low or FLOW:Stretch15 mid or FLOW:Stretch15 NA: down, 54% right on 2025, 4.2 windows a day, +3.3 odds points beyond what the parts give (twins' best: 48%, 4.0 windows).
- **XRP, triples, 240 minutes, by lheat:**
  - 1m DOSC above 0 while 1m ER10 high and 15m HT_QUADRATURE above 0: down, 54% right on 2025, 5.2 windows a day (twins' best: 57%, 1.8 windows).
  - 1m DOSC above 0 while 1m ER10 high and 15m FISHER>trig above: down, 54% right on 2025, 4.9 windows a day (twins' best: 57%, 1.8 windows).
  - 1m DOSC above 0 while 1m ER10 high and 5m AC above 0: down, 54% right on 2025, 5.5 windows a day (twins' best: 57%, 1.8 windows).

## 5. The lists

The top 10 of each list at 15, 60 and 240 minutes; lists.csv.gz holds every list at all six horizons (1, 5, 15, 30, 60, 240), the twins' too. Numbers in the row's A direction. Onset: the same state measured at the minute it starts to hold, on every minute (what the bot's fire gives); late = that move entered one minute later (the bid-ask bounce check); steps = the move in price steps.

**BTC, pairs, 15 minutes, by iheat** (twins' max 42.19):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-TSF14 sign=above 0 & POS:QPhase=m00-04 | up | 77.52 | 51.0 | +1.11 | +1.04 | +1.34 | 80.9 | pack | 2.3 | 77.52 | +0.49 | +0.1 | +0.1 | +121.7 | > twins | 1 |
| 2 | 1m:C-TSF14 sign=below 0 & POS:QPhase=m00-04 | down | 78.30 | 51.4 | +1.39 | -1.03 | +1.77 | 80.3 | pack | 1.8 | 78.30 | +0.69 | +0.2 | +0.2 | +183.5 | > twins | 1 |
| 3 | 1m:C-TRIMA20 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 60.53 | 52.5 | +2.48 | -1.20 | +2.03 | 72.5 | none | 25.2 | 50.55 | +0.68 | +0.2 | +0.3 | +255.5 | hot, rep, > twins | 12 |
| 4 | 1m:C-CKSPmid sign=below 0 & 1m:HT_TRENDMODE=trend | up | 59.44 | 52.4 | +2.53 | +1.21 | +2.08 | 71.8 | none | 24.3 | 49.18 | +0.91 | +0.2 | +0.2 | +169.9 | hot, rep, > twins | 9 |
| 5 | 1m:C-LINEARREG14 sign=above 0 & 1m:RVOL20=high | down | 43.82 | 51.9 | +1.87 | -1.60 | +1.96 | 70.1 | pack | 3.5 | 43.55 | +1.59 | +0.6 | +0.6 | +589.8 | hot, rep, > twins | 0 |
| 6 | 1m:DX14=high & 5m:C-HMA20 sign=above 0 | down | 16.30 | 55.5 | +5.48 | -4.27 | +4.67 | 69.6 | none | 19.1 | 14.55 | +4.28 | +0.9 | +0.8 | +889.4 | hot, rep, BHY, > twins | 17 |
| 7 | 1m:DX14=high & 5m:C-TEMA21 sign=below 0 | up | 16.69 | 55.2 | +5.31 | +4.16 | +4.53 | 69.5 | none | 16.8 | 14.98 | +4.59 | +0.7 | +0.7 | +717.7 | hot, rep, BHY, > twins | 17 |
| 8 | 1m:C-LINEARREG14 sign=below 0 & 1m:RVOL20=high | up | 45.55 | 51.3 | +1.43 | +1.52 | +1.48 | 69.1 | none | 4.1 | 45.25 | +1.23 | +0.3 | +0.2 | +338.8 | hot, rep, > twins | 1 |
| 9 | 1m:C-DEMA21 sign=above 0 & 1m:PVO12/26 sign=above 0 | down | 60.80 | 51.8 | +1.78 | -1.13 | +2.00 | 68.6 | pack | 10.1 | 55.10 | +1.00 | +0.3 | +0.3 | +267.1 | hot, rep, > twins | 0 |
| 10 | 1m:VORTEXdiff14 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 55.42 | 52.7 | +2.68 | -1.23 | +2.09 | 68.2 | pack | 26.6 | 44.16 | +1.45 | +0.3 | +0.2 | +295.9 | hot, rep, > twins | 0 |

**BTC, pairs, 15 minutes, by lheat** (twins' max 64.23):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ADOSC sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 55.56 | 53.2 | +3.12 | -0.49 | +3.60 | 171.5 | pack | 19.9 | 43.06 | +1.64 | +0.4 | +0.5 | +449.0 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:WAD sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 62.19 | 52.0 | +1.99 | -0.17 | +2.69 | 167.4 | none | 21.2 | 49.74 | +0.48 | +0.0 | +0.1 | +36.8 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:ERIbull13 sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 62.10 | 52.4 | +2.36 | -0.11 | +2.79 | 157.1 | pack | 22.2 | 49.31 | +0.73 | +0.1 | +0.1 | +120.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:AD sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 57.33 | 53.0 | +2.94 | -0.34 | +3.22 | 156.5 | pack | 19.9 | 47.04 | +1.40 | +0.3 | +0.3 | +262.4 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:AD sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 68.22 | 52.2 | +2.15 | -0.12 | +2.65 | 153.6 | pack | 25.1 | 54.21 | +0.75 | +0.0 | +0.1 | +33.1 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-EMA9 sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 64.39 | 51.9 | +1.82 | -0.09 | +2.37 | 152.3 | none | 20.4 | 57.20 | +0.44 | +0.0 | +0.1 | +14.3 | hot, rep, BHY, > twins | 4 |
| 7 | 1m:C-FRAMA16 sign=above 0 & 5m:HT_INPHASE sign=above 0 | down | 58.11 | 52.5 | +2.47 | -0.23 | +2.61 | 151.9 | none | 18.6 | 52.41 | +0.80 | +0.2 | +0.3 | +182.1 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:ADOSC sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 65.69 | 52.2 | +2.18 | -0.12 | +2.74 | 150.4 | pack | 25.1 | 48.00 | +0.90 | +0.1 | +0.3 | +139.6 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:C-MAMA sign=above 0 & 5m:HT_INPHASE sign=above 0 | down | 57.10 | 52.4 | +2.38 | -0.27 | +2.59 | 147.9 | pack | 19.5 | 50.69 | +1.12 | +0.3 | +0.4 | +287.7 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:AD sign=above 0 & 5m:PSO sign=above 0 | down | 49.38 | 53.0 | +2.98 | -0.28 | +3.18 | 147.7 | pack | 22.0 | 39.29 | +1.36 | +0.1 | +0.2 | +151.9 | hot, rep, BHY, > twins | 0 |

**BTC, pairs, 15 minutes, by oheat** (twins' max 59.45):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ADOSC sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 55.56 | 53.2 | +3.12 | -0.49 | +3.60 | 173.1 | pack | 19.9 | 43.06 | +1.64 | +0.4 | +0.5 | +449.0 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:AD sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 57.33 | 53.0 | +2.94 | -0.34 | +3.22 | 168.7 | pack | 19.9 | 47.04 | +1.40 | +0.3 | +0.3 | +262.4 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:CMF20 sign=above 0 & 1m:PVI sign=above 0 | down | 66.28 | 52.6 | +2.54 | -0.17 | +2.77 | 168.3 | pack | 24.0 | 50.96 | +0.63 | +0.1 | +0.3 | +94.9 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:C-FRAMA16 sign=above 0 & 1m:CMF20 sign=above 0 | down | 69.66 | 52.5 | +2.41 | -0.17 | +2.11 | 168.0 | none | 18.6 | 63.38 | +1.22 | +0.3 | +0.4 | +275.7 | hot, rep, BHY, > twins | 3 |
| 5 | 1m:C-FRAMA16 sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 59.83 | 52.8 | +2.77 | -0.23 | +2.66 | 165.5 | pack | 19.9 | 54.36 | +1.37 | +0.2 | +0.3 | +179.9 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:ASI sign=above 0 & 1m:CMF20 sign=above 0 | down | 67.36 | 52.5 | +2.40 | -0.11 | +2.35 | 161.9 | none | 23.8 | 53.35 | +1.08 | +0.2 | +0.4 | +252.8 | hot, rep, BHY, > twins | 1 |
| 7 | 1m:C-FRAMA16 sign=above 0 & 1m:PVI sign=above 0 | down | 79.18 | 52.1 | +2.04 | -0.12 | +1.66 | 161.3 | pack | 24.0 | 70.30 | +0.86 | +0.2 | +0.4 | +255.5 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:ADOSC sign=above 0 & 1m:PVI sign=above 0 | down | 74.31 | 52.2 | +2.14 | -0.06 | +2.08 | 159.0 | pack | 24.0 | 57.63 | +0.58 | +0.2 | +0.3 | +193.8 | hot, rep, BHY, > twins | 1 |
| 9 | 1m:ERIbull13 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 50.42 | 53.0 | +3.13 | +1.34 | +2.31 | 157.9 | none | 25.6 | 44.19 | +1.67 | +0.5 | +0.5 | +517.5 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:C-EMA50 sign=above 0 & 1m:ADOSC sign=above 0 | down | 67.51 | 52.4 | +2.30 | -0.22 | +2.65 | 155.6 | none | 29.6 | 50.78 | +0.66 | +0.1 | +0.3 | +133.5 | hot, rep, BHY, > twins | 1 |

**BTC, pairs, 15 minutes, unseen, by iheat** (twins' max 39.29):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-TRIMA20 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 60.53 | 52.5 | +2.48 | -1.20 | +2.03 | 72.5 | none | 25.2 | 50.55 | +0.68 | +0.2 | +0.3 | +255.5 | hot, rep, > twins | 12 |
| 2 | 1m:C-CKSPmid sign=below 0 & 1m:HT_TRENDMODE=trend | up | 59.44 | 52.4 | +2.53 | +1.21 | +2.08 | 71.8 | none | 24.3 | 49.18 | +0.91 | +0.2 | +0.2 | +169.9 | hot, rep, > twins | 8 |
| 3 | 1m:DX14=high & 5m:C-HMA20 sign=above 0 | down | 16.30 | 55.5 | +5.48 | -4.27 | +4.67 | 69.6 | none | 19.1 | 14.55 | +4.28 | +0.9 | +0.8 | +889.4 | hot, rep, BHY, > twins | 16 |
| 4 | 1m:DX14=high & 5m:C-TEMA21 sign=below 0 | up | 16.69 | 55.2 | +5.31 | +4.16 | +4.53 | 69.5 | none | 16.8 | 14.98 | +4.59 | +0.7 | +0.7 | +717.7 | hot, rep, BHY, > twins | 13 |
| 5 | 1m:C-LINEARREG14 sign=below 0 & 1m:RVOL20=high | up | 45.55 | 51.3 | +1.43 | +1.52 | +1.48 | 69.1 | none | 4.1 | 45.25 | +1.23 | +0.3 | +0.2 | +338.8 | hot, rep, > twins | 1 |
| 6 | 1m:C-LINEARREG14 sign=below 0 & POS:QPhase=m00-04 | up | 80.22 | 48.9 | -0.91 | -0.85 | -1.54 | 68.3 | none | 4.1 | 80.22 | -0.38 | -0.0 | -0.0 | -30.0 | > twins | 0 |
| 7 | 1m:ERIbear13 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 50.30 | 53.1 | +3.01 | -1.35 | +2.28 | 67.8 | none | 24.0 | 44.21 | +1.60 | +0.4 | +0.4 | +454.0 | hot, rep, > twins | 0 |
| 8 | 1m:DX14=high & 5m:DOSC sign=below 0 | up | 16.80 | 55.0 | +5.15 | +3.95 | +4.31 | 66.5 | none | 18.0 | 15.23 | +4.55 | +0.5 | +0.6 | +473.9 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high | down | 42.25 | 51.8 | +1.78 | -1.56 | +1.92 | 66.0 | none | 2.6 | 41.95 | +1.63 | +0.5 | +0.5 | +542.9 | hot, rep, > twins | 1 |
| 10 | 1m:HT_INPHASE sign=above 0 & POS:QPhase=m05-09 | down | 75.32 | 50.0 | -0.02 | +0.87 | -1.24 | 65.6 | none | 15.6 | 75.32 | +0.40 | +0.1 | -0.0 | +76.7 | > twins | 0 |

**BTC, pairs, 15 minutes, unseen, by lheat** (twins' max 62.43):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:WAD sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 62.19 | 52.0 | +1.99 | -0.17 | +2.69 | 167.4 | none | 21.2 | 49.74 | +0.48 | +0.0 | +0.1 | +36.8 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:C-EMA9 sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 64.39 | 51.9 | +1.82 | -0.09 | +2.37 | 152.3 | none | 20.4 | 57.20 | +0.44 | +0.0 | +0.1 | +14.3 | hot, rep, BHY, > twins | 3 |
| 3 | 1m:C-FRAMA16 sign=above 0 & 5m:HT_INPHASE sign=above 0 | down | 58.11 | 52.5 | +2.47 | -0.23 | +2.61 | 151.9 | none | 18.6 | 52.41 | +0.80 | +0.2 | +0.3 | +182.1 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:ERIbull13 sign=above 0 & 5m:HT_INPHASE sign=above 0 | down | 58.58 | 52.4 | +2.31 | -0.18 | +2.52 | 147.4 | none | 22.2 | 46.43 | +0.63 | +0.2 | +0.2 | +194.2 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:C-EMA9 sign=above 0 & 5m:HT_INPHASE sign=above 0 | down | 56.71 | 52.5 | +2.40 | -0.22 | +2.59 | 146.8 | none | 20.4 | 50.44 | +1.03 | +0.3 | +0.4 | +287.0 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-FRAMA16 sign=above 0 & 5m:DIdiff14 sign=above 0 | down | 52.69 | 52.7 | +2.67 | -0.36 | +2.92 | 142.4 | none | 24.0 | 47.60 | +1.12 | -0.0 | +0.1 | -12.9 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:SWAK_HP20 sign=above 0 & 5m:HT_QUADRATURE sign=above 0 | down | 62.70 | 52.2 | +2.14 | -0.15 | +2.25 | 141.1 | none | 17.8 | 57.61 | +0.96 | +0.1 | +0.3 | +151.9 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:C-FRAMA16 sign=above 0 & 5m:HT_QUADRATURE sign=above 0 | down | 62.00 | 52.4 | +2.31 | -0.15 | +2.27 | 140.9 | none | 18.6 | 56.17 | +1.05 | +0.2 | +0.3 | +195.5 | hot, rep, BHY, > twins | 0 |
| 9 | 5m:C-MEDPRICE sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 59.35 | 51.9 | +1.83 | -0.08 | +2.37 | 140.7 | none | 16.1 | 48.10 | +1.13 | +0.1 | +0.3 | +117.0 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:AD sign=above 0 & 15m:HAbody sign=above 0 | down | 44.81 | 53.0 | +2.95 | -0.26 | +3.19 | 140.5 | none | 23.8 | 36.81 | +1.69 | +0.1 | +0.2 | +149.5 | hot, rep, BHY, > twins | 0 |

**BTC, pairs, 15 minutes, unseen, by oheat** (twins' max 57.67):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-FRAMA16 sign=above 0 & 1m:CMF20 sign=above 0 | down | 69.66 | 52.5 | +2.41 | -0.17 | +2.11 | 168.0 | none | 18.6 | 63.38 | +1.22 | +0.3 | +0.4 | +275.7 | hot, rep, BHY, > twins | 3 |
| 2 | 1m:ASI sign=above 0 & 1m:CMF20 sign=above 0 | down | 67.36 | 52.5 | +2.40 | -0.11 | +2.35 | 161.9 | none | 23.8 | 53.35 | +1.08 | +0.2 | +0.4 | +252.8 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:CMF20 sign=above 0 & 1m:HAbody sign=above 0 | down | 71.45 | 52.3 | +2.23 | -0.12 | +1.60 | 159.6 | none | 18.6 | 66.94 | +1.48 | +0.3 | +0.5 | +352.7 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:ERIbull13 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 50.42 | 53.0 | +3.13 | +1.34 | +2.31 | 157.9 | none | 25.6 | 44.19 | +1.67 | +0.5 | +0.5 | +517.5 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:C-EMA50 sign=above 0 & 1m:ADOSC sign=above 0 | down | 67.51 | 52.4 | +2.30 | -0.22 | +2.65 | 155.6 | none | 29.6 | 50.78 | +0.66 | +0.1 | +0.3 | +133.5 | hot, rep, BHY, > twins | 1 |
| 6 | 1m:C-FRAMA16 sign=above 0 & 1m:AD sign=above 0 | down | 81.11 | 52.0 | +1.91 | -0.07 | +1.66 | 155.0 | none | 18.6 | 73.35 | +0.58 | +0.2 | +0.3 | +155.4 | hot, rep, BHY, > twins | 1 |
| 7 | 1m:C-FRAMA16 sign=above 0 & 5m:C-KAMA30 sign=above 0 | down | 55.38 | 52.8 | +2.76 | -0.32 | +2.73 | 152.9 | none | 27.7 | 50.20 | +1.07 | +0.0 | +0.2 | +18.5 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:CCI20 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 57.39 | 52.7 | +2.66 | -1.24 | +2.11 | 152.7 | none | 26.1 | 46.19 | +1.29 | +0.3 | +0.3 | +308.6 | hot, rep, BHY, > twins | 7 |
| 9 | 1m:ERIbear13 sign=above 0 & 1m:ADOSC sign=above 0 | down | 71.27 | 52.2 | +2.14 | -0.04 | +1.71 | 152.5 | none | 24.0 | 60.22 | +1.36 | +0.3 | +0.4 | +267.2 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:CCI20 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 57.49 | 52.5 | +2.65 | +1.22 | +2.11 | 152.1 | none | 26.2 | 46.05 | +0.96 | +0.2 | +0.2 | +223.8 | hot, rep, BHY, > twins | 3 |

**BTC, triples, 15 minutes, by iheat** (twins' max 27.02):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=below 0 & 1m:LRSLOPE14 sign=below 0 & 1m:WAD sign=above 0 | up | 38.59 | 51.1 | +1.19 | +1.98 | +0.23 | 76.3 | pack | 21.2 | 37.21 | +1.05 | +0.2 | +0.1 | +158.1 | hot, rep, > twins | 0 |
| 2 | 1m:CVI10 sign=below 0 & 1m:LRSLOPE14 sign=below 0 & 1m:ASI sign=above 0 | up | 36.04 | 50.5 | +0.68 | +2.00 | -0.38 | 72.2 | pack | 23.8 | 35.01 | +0.48 | -0.1 | -0.2 | -78.6 | hot, rep, > twins | 0 |
| 3 | 1m:CVI10 sign=below 0 & 1m:LRSLOPE14 sign=below 0 & 1m:QSTICK10 sign=above 0 | up | 38.40 | 50.5 | +0.65 | +1.81 | -0.42 | 69.5 | pack | 23.6 | 37.39 | +0.67 | -0.1 | -0.2 | -67.7 | hot, rep, > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:QSTICK10 sign=above 0 | down | 47.44 | 50.2 | +0.14 | +1.45 | -1.42 | 69.0 | none | 23.6 | 44.48 | -0.24 | -0.1 | -0.0 | -107.8 | hot, rep, > twins | 2 |
| 5 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:C-TRIMA20 sign=above 0 | down | 45.92 | 50.2 | +0.11 | +1.42 | -1.43 | 65.1 | none | 25.2 | 42.67 | +0.05 | -0.0 | +0.0 | -18.9 | hot, rep, > twins | 1 |
| 6 | 1m:C-CKSPmid sign=above 0 & 1m:PVO12/26 sign=above 0 & 60m:C-EMA200=low/mid/high/very high/NA | down | 53.25 | 52.7 | +2.67 | -1.21 | +2.16 | 64.2 | pack | 23.8 | 45.79 | +1.75 | +0.4 | +0.4 | +421.9 | hot, rep, > twins | 0 |
| 7 | 1m:KDJ K>D=above & 5m:C-SWAK_GAUSS20=very low/low/high/very high/NA & 5m:C-SWAK_GAUSS20 sign=above 0 | down | 21.02 | 54.9 | +4.85 | -3.03 | +2.56 | 63.6 | pack | 29.3 | 19.56 | +4.53 | +0.7 | +0.7 | +721.8 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:WAD sign=above 0 | down | 47.77 | 50.1 | +0.01 | +1.32 | -1.41 | 62.9 | none | 21.2 | 44.72 | -0.25 | -0.1 | +0.1 | -51.9 | hot, rep, > twins | 0 |
| 9 | 1m:C-DEMA21 sign=above 0 & 5m:C-ALMA9=very low/low/high/very high/NA & X.SOL:R1z=mid/high/very high/NA | down | 41.00 | 52.0 | +1.93 | -1.47 | +0.39 | 60.2 | none | 10.1 | 38.65 | +0.76 | +0.1 | +0.1 | +142.8 | hot, rep, > twins | 0 |
| 10 | 1m:PVO12/26 sign=above 0 & 1m:KST>sig=below & 1m:C-CKSPmid sign=above 0 | down | 23.42 | 53.1 | +2.99 | -2.52 | +1.82 | 59.1 | pack | 23.8 | 22.28 | +1.97 | +0.5 | +0.5 | +560.0 | hot, rep, > twins | 0 |

**BTC, triples, 15 minutes, by lheat** (twins' max 67.31):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 39.16 | 53.6 | +3.58 | -0.44 | +3.19 | 125.0 | pack | 18.6 | 36.42 | +2.88 | +0.5 | +0.6 | +511.0 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:PVO12/26 sign=above 0 & 1m:KST>sig=below & 1m:C-T3_5 sign=below 0 | up | 42.96 | 52.6 | +2.74 | +0.77 | +2.71 | 116.3 | pack | 15.8 | 39.83 | +1.82 | +0.2 | +0.2 | +218.8 | hot, rep, BHY, > twins | 3 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-SAR sign=below 0 | up | 34.65 | 53.6 | +3.70 | +0.49 | +3.34 | 115.9 | pack | 22.3 | 26.49 | +2.39 | +0.5 | +0.5 | +507.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:C-CKSPmid sign=above 0 & 1m:PVO12/26 sign=above 0 & 60m:C-EMA200=low/mid/high/very high/NA | down | 53.25 | 52.7 | +2.67 | -1.21 | +2.16 | 115.1 | pack | 23.8 | 45.79 | +1.75 | +0.4 | +0.4 | +421.9 | > twins | 0 |
| 5 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:HAbody sign=above 0 | down | 49.89 | 52.6 | +2.59 | -0.37 | +2.26 | 113.0 | pack | 15.2 | 46.45 | +1.59 | +0.3 | +0.4 | +318.3 | hot, rep, BHY, > twins | 5 |
| 6 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:WAD sign=above 0 | down | 35.12 | 53.4 | +3.38 | -0.36 | +3.14 | 110.1 | none | 22.6 | 28.12 | +1.93 | +0.4 | +0.4 | +430.0 | hot, rep, BHY, > twins | 4 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:EFI13 sign=below 0 | up | 33.30 | 53.3 | +3.43 | +0.43 | +3.24 | 108.0 | none | 22.3 | 25.07 | +2.73 | +0.4 | +0.3 | +375.0 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:PERCENTB20/2=mid/high/very high/NA & 1m:SWAK_HP20 sign=above 0 & 5m:SWAK_HP20=very low/high/very high | down | 27.64 | 54.1 | +4.02 | -1.30 | +3.80 | 105.0 | pack | 17.8 | 24.99 | +2.32 | +0.4 | +0.3 | +405.2 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:MACDh12/26/9 sign=above 0 | down | 54.86 | 52.0 | +1.93 | -0.22 | +1.89 | 103.6 | pack | 13.8 | 47.27 | +1.03 | +0.2 | +0.2 | +213.6 | hot, rep, BHY, > twins | 0 |
| 10 | 15m:C-AVGPRICE sign=above 0 & 1m:DONCHIAN55pos=high/very high & 5m:C-KAMA30 sign=above 0/NA | down | 24.40 | 55.5 | +5.43 | -0.79 | +3.99 | 97.3 | pack | 29.4 | 21.77 | +4.50 | +0.6 | +0.6 | +567.8 | hot, rep, BHY, > twins | 0 |

**BTC, triples, 15 minutes, by oheat** (twins' max 41.73):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CDL:HIKKAKE=none/bear & 1m:IBS=very low/low/mid/NA & 1m:PVT sign=above 0/NA | down | 84.85 | 51.8 | +1.74 | -0.06 | +0.55 | 147.5 | pack | 24.1 | 81.31 | +1.55 | +0.4 | +0.2 | +377.0 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:ADX28=mid/high/very high/NA & 1m:AROONOSC14 sign=below 0/NA & 1m:C-T3_5 sign=below 0/NA | up | 67.77 | 52.0 | +2.11 | +0.21 | +1.12 | 143.2 | pack | 26.9 | 62.40 | +1.04 | +0.1 | +0.2 | +118.6 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:C-CKSPmid sign=above 0 & 1m:PVO12/26 sign=above 0 & 60m:C-EMA200=low/mid/high/very high/NA | down | 53.25 | 52.7 | +2.67 | -1.21 | +2.16 | 142.4 | pack | 23.8 | 45.79 | +1.75 | +0.4 | +0.4 | +421.9 | hot, rep, BHY, > twins | 0 |
| 4 | 15m:SI sign=above 0 & 1m:C-FRAMA16 sign=above 0 & 5m:C-KAMA30 sign=above 0 | down | 35.99 | 54.0 | +3.93 | -0.61 | +3.06 | 141.4 | stored | 29.5 | 33.18 | +2.39 | +0.3 | +0.4 | +290.3 | hot, rep, BHY, > twins | 2 |
| 5 | 1m:CMO14=very low/low & 1m:MAMA>FAMA=below/NA & POS:QPos=m00/m01/m02/m03/m05/m06/m07/m10/m11/m12/m13/m14/NA | up | 34.26 | 54.0 | +4.12 | +0.23 | +1.15 | 141.0 | pack | 30.6 | 31.04 | +3.31 | +0.7 | +0.5 | +705.6 | hot, rep, BHY, > twins | 0 |
| 6 | 15m:C-AVGPRICE sign=above 0/NA & 1m:C-VIDYA12=high/very high & 1m:EFI13 sign=above 0/NA | down | 29.00 | 54.9 | +4.86 | -0.36 | +1.68 | 141.0 | pack | 29.4 | 25.63 | +3.30 | +0.4 | +0.6 | +421.6 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=above 0 & 1m:HAbody sign=above 0 | down | 39.19 | 53.6 | +3.57 | -0.53 | +2.98 | 140.1 | pack | 16.3 | 36.52 | +2.46 | +0.4 | +0.4 | +377.4 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 39.16 | 53.6 | +3.58 | -0.44 | +3.19 | 140.0 | pack | 18.6 | 36.42 | +2.88 | +0.5 | +0.6 | +511.0 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:C-SUPERTREND10/3 sign=above 0/NA & 1m:CMO14=high/very high/NA & 1m:ULTOSC=very low/low/mid/high | down | 30.83 | 54.6 | +4.54 | -0.22 | +2.78 | 140.0 | pack | 25.7 | 28.11 | +3.82 | +0.3 | +0.3 | +330.7 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:C-KAMA30 sign=below 0 & 1m:RSI21=very low/low/NA & POS:QPos=m00/m01/m02/m03/m05/m10/m12/m13/m14/NA | up | 29.04 | 54.6 | +4.74 | +0.64 | -2.80 | 137.6 | pack | 30.6 | 25.96 | +4.04 | +0.5 | +0.4 | +541.9 | hot, rep, BHY, > twins | 0 |

**BTC, triples, 15 minutes, unseen, by iheat** (twins' max 27.02):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:QSTICK10 sign=above 0 | down | 47.44 | 50.2 | +0.14 | +1.45 | -1.42 | 69.0 | none | 23.6 | 44.48 | -0.24 | -0.1 | -0.0 | -107.8 | hot, rep, > twins | 2 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:C-TRIMA20 sign=above 0 | down | 45.92 | 50.2 | +0.11 | +1.42 | -1.43 | 65.1 | none | 25.2 | 42.67 | +0.05 | -0.0 | +0.0 | -18.9 | hot, rep, > twins | 1 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:WAD sign=above 0 | down | 47.77 | 50.1 | +0.01 | +1.32 | -1.41 | 62.9 | none | 21.2 | 44.72 | -0.25 | -0.1 | +0.1 | -51.9 | hot, rep, > twins | 0 |
| 4 | 1m:C-DEMA21 sign=above 0 & 5m:C-ALMA9=very low/low/high/very high/NA & X.SOL:R1z=mid/high/very high/NA | down | 41.00 | 52.0 | +1.93 | -1.47 | +0.39 | 60.2 | none | 10.1 | 38.65 | +0.76 | +0.1 | +0.1 | +142.8 | hot, rep, > twins | 0 |
| 5 | 1m:C-TRIMA20 sign=below 0 & 1m:HT_SINE=low/high/very high/NA & NY30m=00:30/01:30/02:00/02:30/03:00/03:30/04:00/04:30/05:00/05:30/06:00/07:00/09:00/09:30/10:00/10:30/11:00/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:30/19:00/19:30/20:00/20:30/21:00/21:30/22:30/23:00/23:30/NA | up | 39.91 | 49.8 | +0.00 | -1.36 | -1.45 | 54.2 | none | 25.5 | 38.56 | -0.45 | -0.2 | -0.1 | -245.9 | hot, rep, > twins | 0 |
| 6 | 1m:FISHER10=very low/low/high/very high/NA & 1m:KST>sig=above & 5m:ADX28=mid/high/very high/NA | down | 31.76 | 51.8 | +1.75 | -1.53 | -1.64 | 48.7 | none | 11.9 | 24.73 | +1.14 | +0.2 | +0.2 | +246.9 | hot, rep, > twins | 0 |
| 7 | 1m:STOCHFK5=mid/high/very high/NA & X.ETH:RSI14=low/high/very high & X.SOL:R1z=high/very high/NA | down | 21.64 | 53.2 | +3.13 | -2.19 | -1.05 | 47.4 | none | 0.0 | 21.56 | +2.75 | +0.6 | +0.8 | +631.3 | > twins | 0 |
| 8 | 1m:SI=very low/low/mid/NA & 1m:STOCHFK5=high/very high & POS:QPos=m00/m09/m10/m12 | down | 30.70 | 51.1 | +1.04 | -1.12 | -1.41 | 34.2 | none | 0.0 | 30.70 | +1.08 | -0.2 | +0.1 | -164.0 | > twins | 0 |
| 9 | 1m:IBS=low/high/very high & 1m:SI=very low/low/mid/NA & X:Breadth5=3 down/2 down/1 down | up | 73.60 | 50.5 | +0.63 | -0.44 | -0.07 | 32.5 | none | 0.0 | 72.95 | +0.80 | +0.1 | +0.0 | +66.1 | > twins | 0 |
| 10 | 1m:DPO20=high/very high & 5m:AO sign=below 0 & POS:QPos=m00/m06/m09/m10/m11/m12 | up | 23.73 | 50.8 | +0.97 | -1.37 | -1.51 | 32.4 | none | 21.4 | 23.73 | +0.91 | -0.2 | -0.3 | -226.6 | hot, rep, > twins | 0 |

**BTC, triples, 15 minutes, unseen, by lheat** (twins' max 67.31):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:WAD sign=above 0 | down | 35.12 | 53.4 | +3.38 | -0.36 | +3.14 | 110.1 | none | 22.6 | 28.12 | +1.93 | +0.4 | +0.4 | +430.0 | hot, rep, BHY, > twins | 4 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:EFI13 sign=below 0 | up | 33.30 | 53.3 | +3.43 | +0.43 | +3.24 | 108.0 | none | 22.3 | 25.07 | +2.73 | +0.4 | +0.3 | +375.0 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:ERIbull13 sign=above 0 | down | 39.39 | 53.0 | +2.96 | -0.21 | +2.71 | 106.7 | none | 22.6 | 29.74 | +1.81 | +0.3 | +0.2 | +320.0 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:SI=very low/low & 1m:TakerBuy=very low/low/mid/high/NA & X:Breadth5=3 down/2 down/1 down/mid | up | 61.69 | 51.6 | +1.75 | +0.19 | +1.33 | 82.2 | none | 0.0 | 61.45 | +1.44 | +0.3 | +0.3 | +259.0 | > twins | 0 |
| 5 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 1m:SWAK_HP20 sign=above 0 | down | 26.19 | 53.4 | +3.31 | -0.56 | +2.98 | 78.0 | none | 17.8 | 24.30 | +2.10 | +0.3 | +0.4 | +323.3 | hot, rep, BHY, > twins | 2 |
| 6 | 1m:DX14=high & 5m:C-TEMA21 sign=above 0 & 5m:ADOSC sign=above 0 | down | 13.60 | 56.6 | +6.55 | -0.75 | +5.68 | 77.2 | none | 18.4 | 12.16 | +5.26 | +1.1 | +1.1 | +1159.0 | > twins | 34 |
| 7 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 25.57 | 53.5 | +3.40 | -0.47 | +2.89 | 73.8 | none | 18.6 | 23.43 | +2.24 | +0.3 | +0.4 | +288.1 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:DX14=high & 5m:C-TEMA21 sign=above 0 & 5m:AC sign=above 0 | down | 13.87 | 56.3 | +6.25 | -0.46 | +5.21 | 72.3 | none | 15.5 | 12.36 | +4.64 | +1.0 | +0.9 | +1002.8 | > twins | 1 |
| 9 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 1m:HAbody sign=above 0 | down | 26.62 | 53.3 | +3.26 | -0.52 | +2.89 | 72.0 | none | 15.2 | 25.22 | +2.51 | +0.5 | +0.5 | +474.1 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:DX14=high & 1m:MACDh12/26/9 sign=above 0 & 1m:SMI>sig=above | down | 16.01 | 55.1 | +5.06 | -0.25 | +4.49 | 71.8 | none | 12.3 | 14.20 | +4.08 | +1.1 | +1.0 | +1112.2 | > twins | 3 |

**BTC, triples, 15 minutes, unseen, by oheat** (twins' max 41.73):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:CHOP14=very low/low/mid/NA & 1m:AROONOSC14 sign=above 0 & 1m:IBS=very low/low/mid/NA | down | 74.77 | 51.8 | +1.78 | -0.11 | +0.60 | 132.8 | none | 26.5 | 67.74 | +1.84 | +0.5 | +0.3 | +515.2 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:BOP=mid/high/very high & 1m:SWAK_HP20 sign=below 0 & 5m:AVGDEV14=mid/high/very high/NA | up | 83.52 | 51.4 | +1.58 | +0.08 | +1.17 | 131.6 | none | 18.3 | 81.51 | +1.17 | +0.2 | +0.2 | +215.8 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-FRAMA16 sign=above 0 | down | 33.96 | 53.9 | +3.83 | -0.54 | +3.40 | 130.0 | none | 22.6 | 30.27 | +2.73 | +0.5 | +0.5 | +488.3 | hot, rep, BHY, > twins | 4 |
| 4 | 1m:SWAK_HP20 sign=above 0/NA & 5m:ERIbear13 sign=above 0 & POS:QPos=m00/m01/m02/m05/m14 | down | 37.06 | 53.4 | +3.39 | -0.64 | +0.35 | 125.5 | none | 26.4 | 32.98 | +2.75 | +0.4 | +0.4 | +410.6 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:HAbody sign=above 0 | down | 34.29 | 53.7 | +3.64 | -0.41 | +2.64 | 124.7 | none | 22.6 | 31.49 | +2.77 | +0.6 | +0.6 | +667.9 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:PSO sign=below 0/NA & 1m:QSTICK10 sign=below 0/NA & 1m:SI=very low/low/NA | up | 44.00 | 52.7 | +2.81 | +0.43 | +1.44 | 123.5 | none | 23.9 | 43.78 | +2.50 | +0.7 | +0.6 | +679.4 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-FRAMA16 sign=below 0 | up | 34.58 | 53.4 | +3.51 | +0.28 | +2.73 | 121.5 | none | 22.3 | 30.67 | +2.16 | +0.2 | +0.3 | +231.0 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:APO12/26 sign=above 0 & 1m:WT1=high/very high & POS:QPos=m00/m01/m02/m03/m04/m05/m07/m13/m14/NA | down | 23.28 | 55.2 | +5.17 | -0.46 | +1.36 | 120.3 | none | 29.2 | 18.51 | +4.38 | +0.8 | +0.8 | +851.4 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:BOP=very low/low & 1m:MAMA>FAMA=above/NA & 1m:STOCHFK5=very low/low/mid/NA | down | 54.38 | 52.2 | +2.20 | -0.21 | -2.55 | 119.6 | none | 30.0 | 53.66 | +2.03 | +0.4 | +0.2 | +440.2 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:IBS=very low/low/mid/NA & 5m:C-EMA9 sign=above 0 & POS:QPos=m01/m02/m03/m05/m06/m07/m10/m12/NA | down | 65.29 | 51.9 | +1.81 | -0.05 | +0.17 | 118.3 | none | 29.4 | 65.29 | +1.90 | +0.3 | +0.2 | +328.0 | hot, rep, BHY, > twins | 0 |

**BTC, pairs, 60 minutes, by iheat** (twins' max 26.13):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:RVOL20=very high & 1m:SWAK_2PHP20 sign=above 0 | down | 13.08 | 52.3 | +2.91 | -2.69 | +2.96 | 35.2 | pack | 3.0 | 13.06 | +2.48 | +0.5 | +0.6 | +548.7 | hot, rep, > twins | 2 |
| 2 | 1m:RVOL20=very high & 1m:SWAK_2PHP20 sign=below 0 | up | 13.49 | 52.9 | +2.40 | +2.55 | +2.44 | 34.4 | none | 1.9 | 13.46 | +2.59 | +0.6 | +0.3 | +572.4 | hot, rep, > twins | 1 |
| 3 | 1m:C-LINEARREG14 sign=above 0 & 1m:RVOL20=high | down | 21.96 | 51.2 | +1.78 | -1.48 | +1.64 | 32.5 | pack | 5.8 | 21.94 | +1.58 | +0.5 | +0.5 | +543.6 | hot, rep, > twins | 0 |
| 4 | 1m:WAD sign=below 0 & 1m:OBVdiv10=bear div | down | 14.57 | 50.0 | +0.53 | -2.15 | +0.57 | 31.2 | none | 18.1 | 14.51 | +0.35 | +0.2 | +0.2 | +251.3 | hot, rep, > twins | 0 |
| 5 | 1m:PVO12/26=high & 1m:KVO>sig=above | down | 16.72 | 51.5 | +2.08 | -1.85 | +1.90 | 30.9 | none | 6.1 | 16.51 | +2.04 | +0.5 | +0.6 | +480.6 | hot, rep, > twins | 0 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:OBVdiv10=bull div | up | 13.91 | 51.7 | +1.14 | +2.13 | +1.13 | 29.6 | none | 13.4 | 13.82 | +0.99 | +0.2 | +0.3 | +256.3 | hot, rep, > twins | 0 |
| 7 | 1m:PVO12/26=high & 1m:KVO>sig=below | up | 16.79 | 52.8 | +2.24 | +1.76 | +2.08 | 29.5 | none | 4.9 | 16.61 | +2.12 | +1.2 | +1.1 | +1278.0 | hot, rep, > twins | 0 |
| 8 | 1m:RSI2=low & POS:QPhase=m00-04 | up | 17.73 | 49.8 | -0.68 | -1.64 | -2.52 | 29.0 | none | 7.4 | 17.73 | -0.06 | -0.7 | -0.9 | -754.2 | > twins | 0 |
| 9 | 1m:AROONup14=very high & 1m:ERIbear13 sign=below 0 | down | 13.41 | 51.5 | +2.02 | -2.14 | +0.48 | 28.8 | pack | 16.6 | 13.41 | +2.21 | +1.6 | +1.6 | +1636.5 | > twins | 0 |
| 10 | 1m:CCI14 sign=below 0 & 1m:OBVdiv10=bear div | down | 14.94 | 49.3 | -0.11 | -1.91 | -0.25 | 28.5 | none | 19.0 | 14.90 | -0.48 | +0.2 | +0.2 | +163.4 | hot, rep, > twins | 0 |

**BTC, pairs, 60 minutes, by lheat** (twins' max 37.89):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9=high & 1m:CVI10 sign=above 0 | down | 17.63 | 52.6 | +3.16 | -1.57 | +3.37 | 59.4 | pack | 5.9 | 17.46 | +2.40 | +0.3 | +0.3 | +285.4 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:ADOSC sign=above 0 & 15m:ASI sign=above 0 | down | 15.47 | 52.6 | +3.12 | -0.52 | +3.58 | 55.0 | none | 16.0 | 15.09 | +1.78 | +0.3 | +0.4 | +284.5 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:CMF20=low & 5m:C-ZLEMA21 sign=below 0 | up | 17.50 | 54.0 | +3.43 | +0.46 | +3.03 | 53.0 | pack | 9.9 | 17.18 | +2.96 | +2.0 | +2.1 | +2092.4 | hot, rep, BHY, > twins | 3 |
| 4 | 1m:ADOSC sign=above 0 & 15m:C-KAMA30 sign=above 0 | down | 14.92 | 52.8 | +3.38 | -0.50 | +3.53 | 52.6 | none | 19.3 | 14.64 | +1.92 | +0.3 | +0.4 | +267.1 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:ADOSC sign=above 0 & 5m:PVI sign=above 0 | down | 19.19 | 52.3 | +2.86 | -0.53 | +3.45 | 52.2 | pack | 17.7 | 18.46 | +1.43 | +0.6 | +0.7 | +627.1 | hot, rep, BHY, > twins | 0 |
| 6 | 5m:C-LINEARREG14 sign=below 0 & FLOW:TB5=low | up | 21.74 | 53.2 | +2.66 | +0.59 | +2.39 | 52.1 | none | 8.1 | 21.58 | +1.87 | +1.0 | +0.9 | +1024.2 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:ULTOSC=high & 1m:CORRELcv30 sign=above 0 | down | 16.28 | 53.4 | +3.91 | -0.75 | +3.17 | 51.6 | pack | 18.6 | 16.16 | +3.25 | +0.2 | +0.2 | +219.1 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:WILLR14=high & 1m:STOCH14 K>D=above | down | 22.22 | 51.7 | +2.23 | -0.48 | +2.31 | 51.3 | pack | 8.9 | 22.17 | +2.09 | +0.6 | +0.7 | +667.7 | > twins | 0 |
| 9 | 1m:SMI>sig=above & 5m:PVI sign=above 0 | down | 19.04 | 52.1 | +2.67 | -0.42 | +2.68 | 51.0 | pack | 17.7 | 18.10 | +1.75 | +0.4 | +0.4 | +443.0 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:C-TSF14 sign=above 0 & 1m:DONCHIAN20pos=very high | down | 16.53 | 52.4 | +2.96 | -0.13 | +3.09 | 51.0 | pack | 6.5 | 16.50 | +2.62 | +0.2 | +0.4 | +242.3 | hot, rep, BHY, > twins | 2 |

**BTC, pairs, 60 minutes, by oheat** (twins' max 35.18):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ULTOSC=high & 1m:CORRELcv30 sign=above 0 | down | 16.28 | 53.4 | +3.91 | -0.75 | +3.17 | 63.6 | pack | 18.6 | 16.16 | +3.25 | +0.2 | +0.2 | +219.1 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:AROONup25=very high & 1m:CVI10 sign=above 0 | down | 18.88 | 52.7 | +3.27 | -1.12 | +2.65 | 61.8 | pack | 16.1 | 18.78 | +3.24 | +0.8 | +0.8 | +843.0 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:CTI20 sign=below 0 & FLOW:TB5=low | up | 21.31 | 53.4 | +2.89 | +0.49 | +2.11 | 61.6 | pack | 19.4 | 21.17 | +2.13 | +1.0 | +0.9 | +1007.5 | hot, rep, BHY, > twins | 8 |
| 4 | 1m:CCI20 sign=below 0 & 1m:CMF20=low | up | 18.29 | 53.9 | +3.37 | +0.27 | +2.51 | 61.6 | none | 20.2 | 18.01 | +2.65 | +1.7 | +1.7 | +1728.1 | hot, rep, BHY, > twins | 16 |
| 5 | 1m:SI=high & 15m:BOP sign=above 0 | down | 18.72 | 52.7 | +3.25 | -0.79 | +2.21 | 60.9 | pack | 18.0 | 18.72 | +3.00 | +1.7 | +1.8 | +1712.2 | hot, rep, BHY, > twins | 1 |
| 6 | X:Breadth15=3 down & FLOW:TB5=low | up | 19.61 | 53.6 | +3.10 | +0.58 | +2.22 | 60.7 | none | 12.6 | 19.45 | +2.22 | +0.8 | +0.8 | +874.8 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:C-SUPERTREND10/3=high & 1m:CORRELcv30 sign=above 0 | down | 16.93 | 53.0 | +3.56 | -0.78 | +2.71 | 60.2 | pack | 18.6 | 16.89 | +3.09 | +0.3 | +0.4 | +263.5 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-SWAK_BUTTER20 sign=below 0 & 1m:CMF20=low | up | 18.22 | 53.8 | +3.29 | +0.11 | +1.68 | 60.0 | none | 16.5 | 18.03 | +2.58 | +1.7 | +1.7 | +1745.2 | hot, rep, BHY, > twins | 3 |
| 9 | 1m:CMF20=low & 5m:C-ZLEMA21 sign=below 0 | up | 17.50 | 54.0 | +3.43 | +0.46 | +3.03 | 60.0 | pack | 9.9 | 17.18 | +2.96 | +2.0 | +2.1 | +2092.4 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:HAbody=high & 15m:BOP sign=above 0 | down | 19.13 | 52.6 | +3.13 | -0.44 | +2.16 | 59.9 | pack | 18.0 | 19.08 | +2.81 | +1.0 | +1.1 | +1002.4 | hot, rep, BHY, > twins | 0 |

**BTC, pairs, 60 minutes, unseen, by iheat** (twins' max 26.05):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:RVOL20=very high & 1m:SWAK_2PHP20 sign=below 0 | up | 13.49 | 52.9 | +2.40 | +2.55 | +2.44 | 34.4 | none | 1.9 | 13.46 | +2.59 | +0.6 | +0.3 | +572.4 | hot, rep, > twins | 0 |
| 2 | 1m:BOP sign=above 0 & 1m:RVOL20=very high | down | 12.86 | 52.5 | +3.06 | -2.65 | +2.92 | 34.0 | none | 6.9 | 12.84 | +2.83 | +0.5 | +0.6 | +556.0 | hot, rep, > twins | 0 |
| 3 | 1m:FOSC5 sign=above 0 & 1m:RVOL20=very high | down | 13.28 | 52.2 | +2.76 | -2.49 | +2.76 | 33.1 | none | 1.8 | 13.26 | +2.52 | +0.3 | +0.3 | +320.7 | hot, rep, > twins | 0 |
| 4 | 1m:WAD sign=below 0 & 1m:OBVdiv10=bear div | down | 14.57 | 50.0 | +0.53 | -2.15 | +0.57 | 31.2 | none | 18.1 | 14.51 | +0.35 | +0.2 | +0.2 | +251.3 | hot, rep, > twins | 0 |
| 5 | 1m:PVO12/26=high & 1m:KVO>sig=above | down | 16.72 | 51.5 | +2.08 | -1.85 | +1.90 | 30.9 | none | 6.1 | 16.51 | +2.04 | +0.5 | +0.6 | +480.6 | hot, rep, > twins | 0 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:OBVdiv10=bull div | up | 13.91 | 51.7 | +1.14 | +2.13 | +1.13 | 29.6 | none | 13.4 | 13.82 | +0.99 | +0.2 | +0.3 | +256.3 | hot, rep, > twins | 0 |
| 7 | 1m:PVO12/26=high & 1m:KVO>sig=below | up | 16.79 | 52.8 | +2.24 | +1.76 | +2.08 | 29.5 | none | 4.9 | 16.61 | +2.12 | +1.2 | +1.1 | +1278.0 | hot, rep, > twins | 0 |
| 8 | 1m:RSI2=low & POS:QPhase=m00-04 | up | 17.73 | 49.8 | -0.68 | -1.64 | -2.52 | 29.0 | none | 7.4 | 17.73 | -0.06 | -0.7 | -0.9 | -754.2 | > twins | 0 |
| 9 | 1m:CCI14 sign=below 0 & 1m:OBVdiv10=bear div | down | 14.94 | 49.3 | -0.11 | -1.91 | -0.25 | 28.5 | none | 19.0 | 14.90 | -0.48 | +0.2 | +0.2 | +163.4 | hot, rep, > twins | 0 |
| 10 | 1m:CRSI=high & 1m:PVO12/26=high | down | 9.07 | 53.7 | +4.20 | -3.10 | +3.39 | 28.1 | none | 6.4 | 9.06 | +3.90 | +0.9 | +0.9 | +945.6 | > twins | 0 |

**BTC, pairs, 60 minutes, unseen, by lheat** (twins' max 37.89):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ADOSC sign=above 0 & 15m:ASI sign=above 0 | down | 15.47 | 52.6 | +3.12 | -0.52 | +3.58 | 55.0 | none | 16.0 | 15.09 | +1.78 | +0.3 | +0.4 | +284.5 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:ADOSC sign=above 0 & 15m:C-KAMA30 sign=above 0 | down | 14.92 | 52.8 | +3.38 | -0.50 | +3.53 | 52.6 | none | 19.3 | 14.64 | +1.92 | +0.3 | +0.4 | +267.1 | hot, rep, BHY, > twins | 0 |
| 3 | 5m:C-LINEARREG14 sign=below 0 & FLOW:TB5=low | up | 21.74 | 53.2 | +2.66 | +0.59 | +2.39 | 52.1 | none | 8.1 | 21.58 | +1.87 | +1.0 | +0.9 | +1024.2 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:ADOSC sign=above 0 & 15m:ADOSC sign=above 0 | down | 15.49 | 52.6 | +3.10 | -0.50 | +3.50 | 51.2 | none | 14.7 | 15.14 | +1.93 | +1.3 | +1.4 | +1359.6 | hot, rep, BHY, > twins | 0 |
| 5 | 5m:C-AVGPRICE sign=below 0 & FLOW:TB5=low | up | 22.57 | 53.0 | +2.48 | +0.50 | +2.17 | 49.1 | none | 12.9 | 22.48 | +1.71 | +1.0 | +0.9 | +1007.9 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:PVI=low & 15m:C-MEDPRICE sign=below 0 | up | 13.82 | 54.7 | +4.17 | +0.73 | +3.51 | 48.5 | none | 13.7 | 13.60 | +3.19 | +1.7 | +1.7 | +1711.8 | > twins | 0 |
| 7 | 1m:MACDh5/35/5 sign=below 0 & 15m:SWAK_2PHP20 sign=below 0 | up | 21.44 | 52.6 | +2.06 | +0.35 | +2.24 | 48.1 | none | 10.6 | 21.03 | +1.77 | +0.8 | +0.9 | +867.7 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:SMI>sig=above & 5m:OBV sign=above 0 | down | 19.70 | 51.7 | +2.22 | -0.32 | +2.42 | 47.7 | none | 15.4 | 18.83 | +1.22 | +0.3 | +0.3 | +344.5 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:AD sign=above 0 & 5m:MAMA>FAMA=above | down | 16.78 | 52.0 | +2.57 | -0.34 | +2.93 | 47.5 | none | 18.7 | 16.42 | +1.34 | +0.3 | +0.3 | +328.9 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:C-HT_TRENDLINE sign=below 0 & 1m:CMF20=low | up | 18.32 | 53.8 | +3.28 | +0.27 | +2.58 | 47.3 | none | 19.5 | 18.04 | +2.67 | +1.6 | +1.7 | +1699.4 | hot, rep, BHY, > twins | 3 |

**BTC, pairs, 60 minutes, unseen, by oheat** (twins' max 34.97):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI20 sign=below 0 & 1m:CMF20=low | up | 18.29 | 53.9 | +3.37 | +0.27 | +2.51 | 61.6 | none | 20.2 | 18.01 | +2.65 | +1.7 | +1.7 | +1728.1 | hot, rep, BHY, > twins | 13 |
| 2 | 1m:COPPOCK sign=below 0 & FLOW:TB5=low | up | 21.31 | 53.4 | +2.87 | +0.49 | +2.10 | 61.1 | none | 19.7 | 21.17 | +2.07 | +0.9 | +0.9 | +953.8 | hot, rep, BHY, > twins | 4 |
| 3 | X:Breadth15=3 down & FLOW:TB5=low | up | 19.61 | 53.6 | +3.10 | +0.58 | +2.22 | 60.7 | none | 12.6 | 19.45 | +2.22 | +0.8 | +0.8 | +874.8 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:C-SWAK_BUTTER20 sign=below 0 & 1m:CMF20=low | up | 18.22 | 53.8 | +3.29 | +0.11 | +1.68 | 60.0 | none | 16.5 | 18.03 | +2.58 | +1.7 | +1.7 | +1745.2 | hot, rep, BHY, > twins | 3 |
| 5 | 1m:ASI sign=below 0 & FLOW:TB5=low | up | 22.58 | 53.1 | +2.61 | +0.46 | +1.90 | 59.0 | none | 19.3 | 22.47 | +2.22 | +1.1 | +1.1 | +1143.1 | hot, rep, BHY, > twins | 1 |
| 6 | 1m:CMF20=low & 5m:C-TEMA21 sign=below 0 | up | 17.31 | 53.9 | +3.40 | +0.53 | +2.87 | 58.9 | none | 8.6 | 17.03 | +3.01 | +2.0 | +2.1 | +2055.5 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:PVI=low & 15m:C-MEDPRICE sign=below 0 | up | 13.82 | 54.7 | +4.17 | +0.73 | +3.51 | 57.6 | none | 13.7 | 13.60 | +3.19 | +1.7 | +1.7 | +1711.8 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:SI=high & 5m:HAbody sign=above 0 | down | 18.92 | 52.5 | +3.04 | -0.59 | +1.97 | 57.4 | none | 20.5 | 18.92 | +2.85 | +1.0 | +1.1 | +1029.8 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:SI=high & 5m:C-SWAK_BUTTER20 sign=above 0 | down | 18.22 | 52.5 | +3.05 | -0.62 | +1.99 | 55.6 | none | 21.6 | 18.21 | +2.80 | +0.9 | +1.0 | +912.0 | hot, rep, BHY, > twins | 3 |
| 10 | 1m:C-T3_5=high & 5m:HAbody sign=above 0 | down | 19.42 | 52.3 | +2.84 | -0.56 | +1.81 | 55.1 | none | 20.5 | 19.39 | +2.83 | +0.9 | +1.0 | +902.0 | hot, rep, BHY, > twins | 0 |

**BTC, triples, 60 minutes, by iheat** (twins' max 21.49):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=below 0 & 1m:LRSLOPE14 sign=below 0 & 1m:ASI sign=above 0 | down | 20.78 | 48.8 | -0.60 | +1.55 | -1.92 | 32.3 | pack | 20.6 | 20.71 | -0.38 | -0.2 | -0.1 | -172.9 | hot, rep, > twins | 0 |
| 2 | 1m:CVI10 sign=below 0 & 1m:LRSLOPE14 sign=below 0 & 1m:MOM10 sign=above 0 | down | 21.34 | 49.0 | -0.47 | +1.40 | -1.78 | 29.8 | pack | 20.8 | 21.31 | -0.44 | -0.1 | +0.0 | -85.0 | hot, rep, > twins | 1 |
| 3 | 1m:CVI10 sign=below 0 & 1m:LRSLOPE14 sign=below 0 & 1m:FISHER10 sign=above 0 | up | 15.98 | 51.0 | +0.53 | +1.67 | -0.45 | 26.7 | pack | 20.7 | 15.92 | +0.49 | -0.1 | -0.0 | -126.7 | hot, rep, > twins | 0 |
| 4 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & 1m:PVT sign=above 0 | down | 14.89 | 52.0 | +2.51 | -1.72 | +1.23 | 25.7 | pack | 21.2 | 14.78 | +1.42 | +1.2 | +1.2 | +1258.3 | hot, rep, > twins | 0 |
| 5 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & 1m:EFI13 sign=above 0 | up | 14.55 | 49.5 | -1.01 | -1.67 | -3.14 | 24.3 | pack | 13.5 | 14.44 | -0.15 | -0.6 | -0.6 | -606.3 | hot, rep, > twins | 0 |
| 6 | 1m:WAD sign=above 0 & 1m:CVI10=high & 1m:CDL:DOJI=fires | down | 4.63 | 46.5 | -2.95 | +5.22 | -5.90 | 24.2 | none | 10.0 | 4.63 | -2.07 | -1.9 | -1.9 | -2075.8 | > twins | 0 |
| 7 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & 1m:C-HT_TRENDLINE sign=above 0 | down | 13.29 | 51.8 | +2.35 | -1.73 | +1.25 | 23.0 | pack | 20.6 | 13.22 | +1.12 | +0.8 | +0.7 | +800.3 | hot, rep, > twins | 0 |
| 8 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:FISHER10 sign=above 0 | down | 21.88 | 49.8 | +0.36 | +1.04 | -0.91 | 22.7 | pack | 20.7 | 21.72 | +0.66 | +0.5 | +0.5 | +536.5 | hot, rep, > twins | 0 |
| 9 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:ASI sign=above 0 | down | 22.55 | 49.7 | +0.25 | +1.00 | -1.09 | 22.6 | none | 20.6 | 22.44 | +0.43 | +0.3 | +0.4 | +350.3 | > twins | 0 |
| 10 | 15m:C-FRAMA16 sign=above 0 & 1m:DONCHIAN20pos=very low/low/NA & 5m:C-TRIMA20 sign=above 0/NA | up | 11.53 | 53.3 | +2.73 | +1.95 | +1.25 | 22.5 | pack | 22.2 | 11.50 | +2.32 | +2.7 | +2.9 | +2797.9 | > twins | 0 |

**BTC, triples, 60 minutes, by lheat** (twins' max 28.12):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:RVIR14=mid/high/very high/NA & 15m:WT1=mid/high/very high/NA & 1m:PVT sign=above 0/NA | down | 21.02 | 51.5 | +2.06 | -0.10 | +2.63 | 55.3 | pack | 21.2 | 20.93 | +1.23 | +0.6 | +0.7 | +613.3 | > twins | 0 |
| 2 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:AROONup25=very high | down | 18.10 | 53.0 | +3.54 | -0.63 | +2.77 | 50.1 | pack | 16.1 | 18.00 | +3.51 | +0.8 | +0.9 | +872.3 | > twins | 1 |
| 3 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 5m:AD sign=above 0 | down | 17.83 | 52.5 | +3.06 | -0.70 | +2.71 | 48.3 | pack | 14.4 | 17.50 | +2.27 | +1.2 | +1.2 | +1233.9 | hot, rep, BHY, > twins | 0 |
| 4 | 15m:TRIX30=low/mid/high/very high/NA & 60m:Tenkan>Kijun=above & PERP:FundZ=very low/low/mid/high | down | 12.64 | 51.5 | +2.06 | -0.01 | +4.23 | 45.9 | none | 6.0 | 0.60 | -0.38 | -2.1 | -0.7 | -2133.3 | > twins | 0 |
| 5 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 5m:PSO sign=above 0 | down | 15.56 | 52.9 | +3.45 | -0.65 | +2.84 | 44.2 | pack | 16.3 | 15.15 | +3.09 | +1.3 | +1.3 | +1391.8 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & 1m:EFI13 sign=below 0 | up | 18.90 | 52.7 | +2.13 | +0.71 | +2.29 | 43.2 | pack | 13.5 | 18.34 | +1.76 | +0.6 | +0.6 | +636.7 | hot, rep, > twins | 0 |
| 7 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & 1m:C-T3_5 sign=below 0 | up | 20.04 | 52.9 | +2.33 | +0.60 | +2.15 | 43.1 | pack | 13.5 | 19.83 | +1.53 | +0.2 | +0.2 | +190.6 | hot, rep, > twins | 1 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & FLOW:TB5=low | up | 15.61 | 54.2 | +3.63 | +1.20 | +2.70 | 42.1 | pack | 13.5 | 15.49 | +2.62 | +1.3 | +1.3 | +1381.6 | hot, rep, > twins | 0 |
| 9 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26=high & 1m:KVO>sig=above | down | 13.75 | 52.5 | +3.05 | -0.64 | +2.90 | 39.9 | none | 12.2 | 13.58 | +3.36 | +1.1 | +1.2 | +1187.3 | hot, rep, > twins | 0 |
| 10 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26=high & 1m:C-ALMA9 sign=above 0 | down | 13.83 | 52.8 | +3.36 | -0.71 | +2.86 | 39.6 | stored | 13.3 | 13.71 | +3.09 | +1.5 | +1.6 | +1554.2 | > twins | 2 |

**BTC, triples, 60 minutes, by oheat** (twins' max 27.01):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:AROONup25=very high | down | 18.10 | 53.0 | +3.54 | -0.63 | +2.77 | 64.1 | pack | 16.1 | 18.00 | +3.51 | +0.8 | +0.9 | +872.3 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & FLOW:TB5=low | up | 15.61 | 54.2 | +3.63 | +1.20 | +2.70 | 56.6 | pack | 13.5 | 15.49 | +2.62 | +1.3 | +1.3 | +1381.6 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:STOCHK14=high | down | 16.65 | 52.8 | +3.32 | -0.67 | +2.27 | 55.3 | pack | 14.4 | 16.54 | +3.01 | +0.5 | +0.4 | +492.9 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:HAbody=high | down | 18.87 | 52.4 | +2.92 | -0.33 | +1.78 | 55.1 | pack | 14.4 | 18.82 | +2.54 | +0.4 | +0.4 | +404.8 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:C-MEDIAN30=very low/low/NA & 1m:C-MIDPOINT14 sign=below 0/NA & 1m:SI=very low/low | up | 15.47 | 54.1 | +3.56 | +1.28 | +1.83 | 55.0 | pack | 18.1 | 15.45 | +3.46 | +1.2 | +1.0 | +1275.4 | hot, rep, BHY, > twins | 0 |
| 6 | 15m:C-AVGPRICE sign=above 0 & 1m:C-FRAMA16 sign=above 0 & 5m:C-KAMA30 sign=above 0 | down | 17.18 | 52.6 | +3.14 | -0.26 | +1.79 | 53.9 | pack | 23.6 | 16.93 | +2.17 | +0.8 | +0.9 | +811.6 | hot, rep, BHY, > twins | 2 |
| 7 | 1m:PSO sign=below 0/NA & 1m:QSTICK10 sign=below 0/NA & 1m:SI=very low/low/NA | up | 20.99 | 53.1 | +2.54 | +0.48 | +1.31 | 53.3 | none | 19.7 | 20.98 | +2.40 | +1.0 | +1.0 | +1016.6 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:FISHER10 sign=below 0/NA & 1m:KST sign=below 0/NA & 1m:SI=very low/low | up | 16.07 | 53.8 | +3.28 | +0.62 | +1.62 | 52.8 | pack | 19.6 | 16.05 | +3.26 | +1.2 | +1.1 | +1231.9 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:C-CKSPmid sign=above 0 & 1m:PVO12/26 sign=above 0 & 60m:C-EMA200=low/mid/high/very high/NA | down | 22.35 | 51.8 | +2.34 | -0.73 | +1.56 | 52.4 | pack | 20.5 | 21.98 | +1.48 | +0.7 | +0.7 | +718.6 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:CDL:LONGLINE=none/bull/NA & 1m:PVI=high/very high/NA & NY30m=00:30/01:00/02:00/03:00/04:00/04:30/05:00/05:30/06:00/06:30/07:00/07:30/08:00/08:30/09:00/10:30/11:00/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/19:30/20:00/20:30/21:00/22:00/23:00/23:30/NA | down | 15.25 | 52.8 | +3.39 | -0.24 | +1.02 | 51.7 | pack | 0.0 | 15.00 | +2.40 | +0.3 | +0.2 | +319.0 | hot, rep, BHY, > twins | 0 |

**BTC, triples, 60 minutes, unseen, by iheat** (twins' max 17.91):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:WAD sign=above 0 & 1m:CVI10=high & 1m:CDL:DOJI=fires | down | 4.63 | 46.5 | -2.95 | +5.22 | -5.90 | 24.2 | none | 10.0 | 4.63 | -2.07 | -1.9 | -1.9 | -2075.8 | > twins | 0 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:ASI sign=above 0 | down | 22.55 | 49.7 | +0.25 | +1.00 | -1.09 | 22.6 | none | 20.6 | 22.44 | +0.43 | +0.3 | +0.4 | +350.3 | > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:HT_INPHASE sign=above 0 | up | 22.68 | 51.0 | +0.45 | +0.97 | +0.02 | 22.0 | none | 13.7 | 22.59 | +0.12 | -0.2 | -0.2 | -196.7 | > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:KST>sig=above | up | 18.67 | 50.8 | +0.31 | +1.17 | -0.16 | 21.9 | none | 12.7 | 18.41 | +0.29 | -0.6 | -0.7 | -638.0 | hot, rep, > twins | 0 |
| 5 | 5m:CVI10 sign=above 0 & 5m:SMI>sig=above & 1m:C-ZLEMA21=high | down | 8.08 | 54.0 | +4.61 | -2.69 | +4.11 | 21.7 | none | 12.4 | 8.03 | +3.71 | +1.7 | +1.7 | +1748.7 | > twins | 0 |
| 6 | 1m:ER10=high & 1m:KVO>sig=above & 1m:FISHER>trig=below | up | 6.33 | 53.2 | +2.68 | +3.39 | +2.19 | 21.5 | none | 9.4 | 6.30 | +2.33 | +2.7 | +2.5 | +2810.1 | > twins | 0 |
| 7 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 1m:TRANGE=high | down | 9.69 | 52.7 | +3.28 | -2.21 | +2.88 | 21.4 | none | 12.8 | 9.69 | +2.77 | +0.6 | +0.6 | +662.2 | > twins | 0 |
| 8 | 1m:KVO sign=above 0 & 1m:CVI10=high & 1m:CDL:DOJI=fires | down | 4.74 | 46.6 | -2.82 | +4.51 | -5.13 | 21.4 | none | 7.5 | 4.73 | -1.56 | -1.2 | -1.3 | -1277.6 | > twins | 0 |
| 9 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 1m:C-ZLEMA21=high | down | 8.23 | 53.6 | +4.21 | -2.48 | +3.84 | 20.4 | none | 12.8 | 8.20 | +3.65 | +1.5 | +1.4 | +1570.1 | > twins | 0 |
| 10 | 1m:C-TRIMA20 sign=above 0/NA & 1m:SI=very low/low & 1m:STC=very low/low/mid/high/NA | down | 16.57 | 51.6 | +2.10 | -1.22 | +0.85 | 20.2 | none | 20.5 | 16.56 | +2.16 | +0.9 | +0.8 | +903.8 | > twins | 0 |

**BTC, triples, 60 minutes, unseen, by lheat** (twins' max 28.12):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:TRIX30=low/mid/high/very high/NA & 60m:Tenkan>Kijun=above & PERP:FundZ=very low/low/mid/high | down | 12.64 | 51.5 | +2.06 | -0.01 | +4.23 | 45.9 | none | 6.0 | 0.60 | -0.38 | -2.1 | -0.7 | -2133.3 | > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26=high & 1m:KVO>sig=above | down | 13.75 | 52.5 | +3.05 | -0.64 | +2.90 | 39.9 | none | 12.2 | 13.58 | +3.36 | +1.1 | +1.2 | +1187.3 | hot, rep, > twins | 0 |
| 3 | 1m:PVO12/26=high & 1m:KVO>sig=above & 5m:FOSC5 sign=above 0 | down | 13.28 | 52.6 | +3.14 | -0.80 | +2.86 | 37.9 | none | 9.3 | 13.16 | +3.13 | +1.3 | +1.4 | +1336.4 | hot, rep, > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-FRAMA16 sign=below 0 | up | 18.14 | 53.2 | +2.64 | +0.16 | +2.08 | 37.8 | none | 15.0 | 17.71 | +1.74 | +0.6 | +0.6 | +577.8 | hot, rep, > twins | 1 |
| 5 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26=high & 1m:HAbody sign=above 0 | down | 13.95 | 52.7 | +3.29 | -0.65 | +2.70 | 37.6 | none | 13.6 | 13.81 | +3.20 | +1.4 | +1.4 | +1405.0 | > twins | 0 |
| 6 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:C-DEMA21 sign=below 0 | up | 19.05 | 52.5 | +1.94 | +0.14 | +1.88 | 35.8 | none | 15.0 | 17.90 | +1.59 | +0.5 | +0.5 | +559.9 | > twins | 0 |
| 7 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:SMI>sig=above | down | 18.65 | 51.7 | +2.28 | -0.15 | +1.90 | 35.4 | none | 15.2 | 17.68 | +1.12 | +0.6 | +0.5 | +571.1 | hot, rep, > twins | 0 |
| 8 | 1m:WAD sign=above 0 & 1m:CVI10=high & 60m:ERIbull13 sign=above 0 | down | 10.64 | 53.2 | +3.74 | -0.86 | +3.27 | 34.9 | none | 10.6 | 10.55 | +3.37 | +0.8 | +0.9 | +844.8 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:ER10=high & 1m:KVO>sig=above & 1m:BOP sign=above 0 | down | 15.78 | 51.7 | +2.26 | -0.62 | +2.18 | 34.4 | none | 6.9 | 15.69 | +1.60 | -0.4 | -0.4 | -409.5 | > twins | 0 |
| 10 | 5m:CVI10 sign=above 0 & 5m:SMI>sig=above & 1m:AC=high | down | 7.72 | 54.3 | +4.89 | -2.67 | +4.35 | 33.6 | none | 12.4 | 7.61 | +3.54 | +1.4 | +1.4 | +1435.2 | > twins | 0 |

**BTC, triples, 60 minutes, unseen, by oheat** (twins' max 27.01):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PSO sign=below 0/NA & 1m:QSTICK10 sign=below 0/NA & 1m:SI=very low/low/NA | up | 20.99 | 53.1 | +2.54 | +0.48 | +1.31 | 53.3 | none | 19.7 | 20.98 | +2.40 | +1.0 | +1.0 | +1016.6 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TEMA21 sign=above 0 | down | 15.60 | 52.6 | +3.14 | -0.84 | +2.26 | 49.0 | none | 15.2 | 15.39 | +2.49 | +1.0 | +1.1 | +1074.7 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:WT1>WT2=below | up | 17.26 | 53.3 | +2.81 | +0.39 | +2.04 | 48.6 | none | 15.0 | 16.84 | +2.10 | +1.0 | +1.0 | +1072.1 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-FRAMA16 sign=below 0 | up | 18.14 | 53.2 | +2.64 | +0.16 | +2.08 | 47.8 | none | 15.0 | 17.71 | +1.74 | +0.6 | +0.6 | +577.8 | hot, rep, BHY, > twins | 1 |
| 5 | 15m:C-MEDPRICE sign=above 0 & 1m:MOM10 sign=above 0 & 5m:C-KAMA30 sign=above 0 | down | 17.21 | 52.2 | +2.75 | -0.14 | +1.53 | 47.3 | none | 23.6 | 16.76 | +2.41 | +0.7 | +0.7 | +692.1 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26=high & 1m:STOCH5 K>D=above | down | 11.92 | 53.4 | +3.95 | -1.52 | +3.01 | 47.0 | none | 12.2 | 11.86 | +3.51 | +1.0 | +1.0 | +1008.1 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:APO12/26 sign=above 0 & 1m:WT1=high/very high & POS:QPos=m00/m01/m02/m03/m04/m05/m07/m13/m14/NA | down | 12.94 | 53.1 | +3.62 | -0.33 | +0.80 | 46.8 | none | 21.7 | 12.19 | +3.53 | +1.0 | +1.0 | +1083.6 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:HT_INPHASE=very low/low/mid/NA & 1m:MAMA>FAMA=above/NA & 1m:WT1=high/very high | down | 12.84 | 53.0 | +3.60 | -0.18 | +0.76 | 46.2 | none | 22.1 | 12.46 | +3.51 | +0.8 | +0.8 | +854.7 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26=high & 1m:HAbody sign=above 0 | down | 13.95 | 52.7 | +3.29 | -0.65 | +2.70 | 45.9 | none | 13.6 | 13.81 | +3.20 | +1.4 | +1.4 | +1405.0 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:AO sign=above 0/NA & 1m:SI=high/very high & 1m:STOCHFK5=high/very high | down | 15.97 | 52.3 | +2.86 | -0.29 | -0.15 | 45.6 | none | 22.0 | 15.97 | +2.73 | +0.4 | +0.7 | +445.3 | hot, rep, BHY, > twins | 1 |

**BTC, pairs, 240 minutes, by iheat** (twins' max 16.31):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:EFI13 sign=above 0 & 1m:KVO=low | up | 2.74 | 46.0 | -4.96 | -6.71 | -6.93 | 18.4 | pack | 2.2 | 2.74 | -1.61 | -1.1 | -1.3 | -1148.3 | > twins | 0 |
| 2 | 1m:C-VIDYA12=high & 1m:MASSI=low | down | 3.42 | 45.5 | -3.54 | +5.18 | -5.94 | 17.7 | pack | 8.1 | 3.42 | -1.22 | -3.6 | -3.4 | -3830.5 | > twins | 0 |
| 3 | 1m:DX14=high & 1m:KVO=high | down | 3.54 | 53.2 | +4.14 | -4.91 | +5.24 | 17.4 | none | 1.8 | 3.53 | +3.71 | +1.8 | +1.4 | +1904.2 | hot, rep, > twins | 0 |
| 4 | 1m:KVO=high & 1m:PVO12/26=high | down | 4.13 | 52.7 | +3.69 | -4.20 | +4.40 | 17.3 | none | 1.8 | 4.12 | +3.56 | +3.0 | +2.9 | +3081.3 | hot, rep, > twins | 0 |
| 5 | 1m:C-HT_TRENDLINE=high & 1m:MASSI=low | down | 3.21 | 44.6 | -4.37 | +5.15 | -5.86 | 16.5 | none | 6.9 | 3.20 | -3.07 | -3.5 | -3.3 | -3669.7 | > twins | 0 |
| 6 | 1m:DIdiff14=high & 1m:SMI sign=below 0 | down | 3.15 | 55.5 | +6.43 | -5.13 | +4.77 | 16.2 | pack | 10.9 | 3.14 | +4.71 | +1.4 | +1.5 | +1469.2 | none | 0 |
| 7 | 1m:EMV14 sign=below 0 & X.SOL:R15z=high | down | 3.36 | 53.5 | +4.45 | -4.78 | +4.68 | 16.1 | none | 6.9 | 3.36 | +3.52 | +2.6 | +2.6 | +2736.1 | none | 0 |
| 8 | 1m:C-ALMA9=low & 1m:OBVdiv10=bear div | down | 3.83 | 51.9 | +2.87 | -4.04 | +3.40 | 15.5 | pack | 6.5 | 3.83 | +2.60 | +2.1 | +2.0 | +2191.9 | none | 0 |
| 9 | 1m:PVO12/26=very high & X.XRP:Gap15=high | down | 2.10 | 57.3 | +8.31 | -7.37 | +8.12 | 15.5 | none | 6.5 | 2.10 | +5.47 | +5.2 | +5.1 | +5455.9 | none | 0 |
| 10 | 1m:CHOP14=low & 1m:NVI=high | down | 4.26 | 52.5 | +3.53 | -3.59 | +3.93 | 15.3 | none | 0.7 | 4.26 | +2.12 | +2.6 | +2.4 | +2700.0 | none | 0 |

**BTC, pairs, 240 minutes, by lheat** (twins' max 21.24):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI20 sign=above 0 & 1m:NVI=low | down | 4.98 | 54.4 | +5.34 | -2.73 | +4.71 | 23.4 | none | 11.4 | 4.97 | +4.78 | +4.1 | +4.2 | +4258.7 | > twins | 2 |
| 2 | 5m:LRSLOPE14 sign=above 0 & FLOW:TB15=high | down | 5.68 | 53.2 | +4.16 | -1.11 | +3.99 | 22.6 | none | 10.9 | 5.67 | +3.40 | +2.4 | +2.3 | +2477.8 | hot, rep, > twins | 2 |
| 3 | 1m:C-VIDYA12 sign=above 0 & 1m:NVI=low | down | 4.96 | 54.1 | +5.12 | -2.63 | +4.53 | 22.5 | pack | 11.5 | 4.95 | +4.32 | +2.3 | +2.3 | +2367.0 | > twins | 0 |
| 4 | 1m:C-EMA21 sign=above 0 & 1m:NVI=low | down | 4.98 | 54.1 | +5.03 | -2.49 | +4.43 | 22.1 | none | 12.2 | 4.97 | +4.40 | +3.3 | +3.4 | +3408.6 | > twins | 2 |
| 5 | 15m:PVO12/26 sign=below 0 & FLOW:TB15=very high | down | 4.33 | 54.5 | +5.52 | -1.30 | +4.99 | 21.6 | none | 1.7 | 4.30 | +5.65 | +5.7 | +5.7 | +5970.5 | > twins | 0 |
| 6 | 5m:C-HMA20 sign=below 0 & FLOW:Stretch15=low | up | 5.60 | 54.7 | +3.70 | +0.28 | +3.83 | 21.5 | pack | 7.9 | 5.60 | +3.36 | +2.2 | +2.2 | +2298.8 | > twins | 2 |
| 7 | 5m:COPPOCK sign=above 0 & FLOW:TB15=high | down | 5.46 | 53.4 | +4.38 | -0.94 | +3.81 | 20.8 | none | 11.3 | 5.45 | +3.80 | +2.9 | +2.9 | +3062.2 | hot, rep | 0 |
| 8 | 1m:PVO12/26 sign=above 0 & 1m:Runs=5+ up | down | 4.96 | 53.3 | +4.26 | -2.69 | +4.18 | 20.7 | pack | 1.9 | 4.96 | +3.05 | +0.3 | +0.1 | +330.1 | hot, rep | 0 |
| 9 | 1m:C-SUPERTREND10/3 sign=below 0 & X.ETH:R15z=low | up | 5.62 | 54.7 | +3.73 | +0.54 | +3.63 | 20.4 | pack | 9.7 | 5.62 | +2.77 | +1.4 | +1.4 | +1438.8 | hot, rep | 2 |
| 10 | 1m:RVIR14=very high & 5m:CVI10 sign=above 0 | down | 3.48 | 54.7 | +5.63 | -3.45 | +5.78 | 20.1 | pack | 3.8 | 3.46 | +4.08 | +3.4 | +3.3 | +3612.9 | none | 0 |

**BTC, pairs, 240 minutes, by oheat** (twins' max 19.33):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI20 sign=above 0 & 1m:NVI=low | down | 4.98 | 54.4 | +5.34 | -2.73 | +4.71 | 26.6 | none | 11.4 | 4.97 | +4.78 | +4.1 | +4.2 | +4258.7 | hot, rep, BHY, > twins | 2 |
| 2 | 1m:TRANGE=high & FLOW:TB15=high | down | 5.22 | 54.0 | +4.99 | -1.39 | +2.56 | 26.1 | none | 6.6 | 5.22 | +4.80 | +4.8 | +5.0 | +5053.6 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:PDI14=high & FLOW:TB15=high | down | 5.35 | 53.9 | +4.85 | -0.98 | +3.04 | 25.9 | pack | 6.6 | 5.34 | +3.88 | +2.4 | +2.3 | +2482.7 | hot, rep, BHY, > twins | 0 |
| 4 | FLOW:Stretch15=low & OI:PxQuad60=long liquidation | up | 4.48 | 56.7 | +5.78 | +0.34 | +3.70 | 25.9 | none | 7.9 | 4.48 | +5.09 | +4.3 | +4.1 | +4500.1 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:ULTOSC=low & X.ETH:R15z=low | up | 5.04 | 56.0 | +5.09 | +1.16 | +2.67 | 25.6 | pack | 6.3 | 5.04 | +4.48 | +3.9 | +3.9 | +4044.2 | > twins | 0 |
| 6 | 1m:C-VIDYA12 sign=above 0 & 1m:NVI=low | down | 4.96 | 54.1 | +5.12 | -2.63 | +4.53 | 25.4 | pack | 11.5 | 4.95 | +4.32 | +2.3 | +2.3 | +2367.0 | hot, rep, BHY, > twins | 0 |
| 7 | 5m:CCI20=high & FLOW:TB15=high | down | 4.09 | 55.2 | +6.18 | -1.82 | +4.24 | 25.3 | none | 11.4 | 4.08 | +5.58 | +4.6 | +4.4 | +4758.6 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:STOCHK14=low & X.ETH:R15z=low | up | 5.15 | 55.9 | +4.89 | +1.03 | +2.53 | 25.2 | pack | 7.8 | 5.14 | +4.37 | +4.2 | +4.0 | +4312.7 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:VORTEXdiff14=low & X.ETH:R15z=low | up | 5.16 | 55.8 | +4.86 | +1.46 | +2.75 | 25.1 | pack | 7.1 | 5.16 | +4.45 | +3.9 | +3.7 | +4020.2 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:CMF20=low & FLOW:Stretch15=low | up | 4.82 | 56.2 | +5.20 | +0.20 | +2.46 | 25.1 | none | 7.9 | 4.82 | +5.18 | +5.1 | +4.9 | +5226.1 | hot, rep, BHY, > twins | 0 |

**BTC, pairs, 240 minutes, unseen, by iheat** (twins' max 16.31):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DX14=high & 1m:KVO=high | down | 3.54 | 53.2 | +4.14 | -4.91 | +5.24 | 17.4 | none | 1.8 | 3.53 | +3.71 | +1.8 | +1.4 | +1904.2 | hot, rep, > twins | 0 |
| 2 | 1m:KVO=high & 1m:PVO12/26=high | down | 4.13 | 52.7 | +3.69 | -4.20 | +4.40 | 17.3 | none | 1.8 | 4.12 | +3.56 | +3.0 | +2.9 | +3081.3 | hot, rep, > twins | 0 |
| 3 | 1m:C-HT_TRENDLINE=high & 1m:MASSI=low | down | 3.21 | 44.6 | -4.37 | +5.15 | -5.86 | 16.5 | none | 6.9 | 3.20 | -3.07 | -3.5 | -3.3 | -3669.7 | > twins | 0 |
| 4 | 1m:EMV14 sign=below 0 & X.SOL:R15z=high | down | 3.36 | 53.5 | +4.45 | -4.78 | +4.68 | 16.1 | none | 6.9 | 3.36 | +3.52 | +2.6 | +2.6 | +2736.1 | none | 0 |
| 5 | 1m:KVO=high & 1m:CVI10=high | down | 3.40 | 53.8 | +4.80 | -4.68 | +4.65 | 15.9 | none | 1.8 | 3.40 | +4.76 | +4.2 | +4.0 | +4401.1 | hot, rep | 0 |
| 6 | 1m:PVO12/26=very high & X.XRP:Gap15=high | down | 2.10 | 57.3 | +8.31 | -7.37 | +8.12 | 15.5 | none | 6.5 | 2.10 | +5.47 | +5.2 | +5.1 | +5455.9 | none | 0 |
| 7 | 1m:CHOP14=low & 1m:NVI=high | down | 4.26 | 52.5 | +3.53 | -3.59 | +3.93 | 15.3 | none | 0.7 | 4.26 | +2.12 | +2.6 | +2.4 | +2700.0 | none | 0 |
| 8 | 1m:C-LINEARREG14=very high & 1m:EMV14=high | down | 2.79 | 54.5 | +5.53 | -5.46 | +5.34 | 15.2 | none | 2.3 | 2.79 | +5.12 | +6.4 | +6.6 | +6822.3 | none | 0 |
| 9 | 1m:MACDh5/35/5=high & 1m:RVOL20=very high | down | 3.65 | 54.2 | +5.15 | -4.15 | +5.02 | 15.1 | none | 3.1 | 3.65 | +4.77 | +1.8 | +2.0 | +1813.3 | none | 0 |
| 10 | 1m:PVO12/26=high & 1m:Runs=3-4 down | up | 5.02 | 54.8 | +3.78 | +3.00 | +3.51 | 15.0 | none | 2.2 | 5.02 | +3.18 | +0.3 | +0.1 | +335.6 | none | 0 |

**BTC, pairs, 240 minutes, unseen, by lheat** (twins' max 21.24):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI20 sign=above 0 & 1m:NVI=low | down | 4.98 | 54.4 | +5.34 | -2.73 | +4.71 | 23.4 | none | 11.4 | 4.97 | +4.78 | +4.1 | +4.2 | +4258.7 | > twins | 2 |
| 2 | 5m:LRSLOPE14 sign=above 0 & FLOW:TB15=high | down | 5.68 | 53.2 | +4.16 | -1.11 | +3.99 | 22.6 | none | 10.9 | 5.67 | +3.40 | +2.4 | +2.3 | +2477.8 | hot, rep, > twins | 1 |
| 3 | 1m:C-EMA21 sign=above 0 & 1m:NVI=low | down | 4.98 | 54.1 | +5.03 | -2.49 | +4.43 | 22.1 | none | 12.2 | 4.97 | +4.40 | +3.3 | +3.4 | +3408.6 | > twins | 2 |
| 4 | 1m:C-VWAP20 sign=above 0 & 1m:NVI=low | down | 4.89 | 54.0 | +4.98 | -2.54 | +4.49 | 21.9 | none | 10.4 | 4.88 | +4.47 | +3.4 | +3.5 | +3498.9 | > twins | 2 |
| 5 | 15m:PVO12/26 sign=below 0 & FLOW:TB15=very high | down | 4.33 | 54.5 | +5.52 | -1.30 | +4.99 | 21.6 | none | 1.7 | 4.30 | +5.65 | +5.7 | +5.7 | +5970.5 | > twins | 0 |
| 6 | 5m:COPPOCK sign=above 0 & FLOW:TB15=high | down | 5.46 | 53.4 | +4.38 | -0.94 | +3.81 | 20.8 | none | 11.3 | 5.45 | +3.80 | +2.9 | +2.9 | +3062.2 | hot, rep | 0 |
| 7 | 1m:RVI14=very high & 5m:CVI10 sign=above 0 | down | 3.43 | 54.7 | +5.68 | -3.04 | +5.80 | 19.9 | none | 3.9 | 3.42 | +3.76 | +1.5 | +1.2 | +1581.0 | none | 0 |
| 8 | 1m:ASI=high & 15m:STOCH14 K>D=above | down | 5.66 | 52.6 | +3.57 | -1.67 | +3.50 | 19.8 | none | 6.6 | 5.66 | +3.11 | +2.2 | +2.2 | +2312.3 | hot, rep | 0 |
| 9 | 1m:CCI50=high & 5m:DPO20 sign=below 0 | down | 5.63 | 52.4 | +3.41 | -1.31 | +3.49 | 19.6 | none | 11.1 | 5.62 | +2.52 | +0.8 | +0.8 | +833.4 | none | 0 |
| 10 | 5m:CCI20=high & 15m:STOCH14 K>D=above | down | 4.82 | 52.9 | +3.89 | -0.73 | +4.07 | 19.6 | none | 11.4 | 4.77 | +3.08 | +0.8 | +0.3 | +825.5 | none | 2 |

**BTC, pairs, 240 minutes, unseen, by oheat** (twins' max 19.16):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI20 sign=above 0 & 1m:NVI=low | down | 4.98 | 54.4 | +5.34 | -2.73 | +4.71 | 26.6 | none | 11.4 | 4.97 | +4.78 | +4.1 | +4.2 | +4258.7 | hot, rep, BHY, > twins | 2 |
| 2 | 1m:TRANGE=high & FLOW:TB15=high | down | 5.22 | 54.0 | +4.99 | -1.39 | +2.56 | 26.1 | none | 6.6 | 5.22 | +4.80 | +4.8 | +5.0 | +5053.6 | hot, rep, BHY, > twins | 0 |
| 3 | FLOW:Stretch15=low & OI:PxQuad60=long liquidation | up | 4.48 | 56.7 | +5.78 | +0.34 | +3.70 | 25.9 | none | 7.9 | 4.48 | +5.09 | +4.3 | +4.1 | +4500.1 | hot, rep, BHY, > twins | 0 |
| 4 | 5m:CCI20=high & FLOW:TB15=high | down | 4.09 | 55.2 | +6.18 | -1.82 | +4.24 | 25.3 | none | 11.4 | 4.08 | +5.58 | +4.6 | +4.4 | +4758.6 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:CMF20=low & FLOW:Stretch15=low | up | 4.82 | 56.2 | +5.20 | +0.20 | +2.46 | 25.1 | none | 7.9 | 4.82 | +5.18 | +5.1 | +4.9 | +5226.1 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-EMA21 sign=above 0 & 1m:NVI=low | down | 4.98 | 54.1 | +5.03 | -2.49 | +4.43 | 25.0 | none | 12.2 | 4.97 | +4.40 | +3.3 | +3.4 | +3408.6 | hot, rep, BHY, > twins | 2 |
| 7 | 1m:CHOP14=low & X.ETH:R15z=low | up | 4.36 | 56.7 | +5.71 | +2.73 | +3.32 | 24.9 | none | 6.3 | 4.35 | +3.49 | +3.6 | +3.3 | +3757.2 | hot, rep, BHY, > twins | 0 |
| 8 | 15m:CORRELcv30 sign=above 0 & FLOW:TB15=high | down | 3.75 | 55.6 | +6.62 | -1.53 | +4.78 | 24.8 | none | 6.6 | 3.74 | +6.10 | +4.5 | +4.4 | +4750.8 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:C-VWAP20=low & X.ETH:R15z=low | up | 5.16 | 55.8 | +4.80 | +1.01 | +2.52 | 24.8 | none | 7.5 | 5.16 | +4.22 | +3.7 | +3.7 | +3867.8 | hot, rep, BHY, > twins | 0 |
| 10 | FLOW:Stretch5=low & OI:PxQuad60=long liquidation | up | 4.79 | 56.1 | +5.18 | +0.45 | +2.91 | 24.8 | none | 6.1 | 4.78 | +5.49 | +3.6 | +3.6 | +3775.6 | hot, rep, BHY, > twins | 0 |

**BTC, triples, 240 minutes, by iheat** (twins' max 12.21):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:CVI10 sign=above 0 & 15m:C-LINEARREG14 sign=above 0 & 5m:KST>sig=below | down | 4.01 | 45.1 | -3.89 | +4.10 | -6.23 | 16.5 | pack | 8.8 | 4.00 | -2.16 | -1.9 | -1.7 | -1932.5 | hot, rep, > twins | 0 |
| 2 | 1m:VHF28=high & 5m:C-TSF14 sign=below 0 & 1m:KVO sign=above 0 | up | 3.08 | 47.0 | -3.95 | -5.23 | -7.06 | 16.1 | none | 4.7 | 3.06 | -2.78 | -1.2 | -1.2 | -1307.9 | > twins | 0 |
| 3 | 1m:VHF28=high & 5m:C-LINEARREG14 sign=below 0 & 1m:KVO sign=above 0 | up | 2.73 | 47.2 | -3.71 | -5.32 | -6.90 | 14.5 | none | 5.0 | 2.71 | -2.33 | -1.5 | -1.5 | -1554.0 | > twins | 0 |
| 4 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:MASSI=low | down | 3.83 | 46.1 | -2.94 | +3.77 | -4.38 | 14.4 | none | 10.0 | 3.79 | -2.11 | -1.6 | -1.7 | -1723.1 | > twins | 0 |
| 5 | 1m:DX14=high & 1m:MACDh12/26/9 sign=above 0 & 1m:C-MAMA sign=below 0 | down | 2.05 | 42.7 | -6.26 | +6.99 | -8.68 | 14.4 | none | 10.0 | 2.04 | -2.27 | -2.4 | -2.5 | -2505.8 | > twins | 0 |
| 6 | 1m:DX14=high & 1m:MACDh12/26/9 sign=above 0 & 5m:DOSC sign=below 0 | down | 2.83 | 45.3 | -3.76 | +4.96 | -6.64 | 14.0 | none | 7.6 | 2.82 | -1.35 | -1.8 | -2.0 | -1894.8 | > twins | 0 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:DX14=low | down | 3.14 | 52.5 | +3.46 | -4.47 | +4.33 | 14.0 | none | 9.8 | 3.12 | +0.89 | -2.2 | -2.0 | -2264.5 | hot, rep, > twins | 0 |
| 8 | 5m:CVI10 sign=above 0 & 15m:C-LINEARREG14 sign=above 0 & 5m:MACDh12/26/9 sign=below 0 | up | 3.31 | 54.3 | +3.35 | +4.22 | +3.24 | 14.0 | pack | 8.8 | 3.31 | +2.38 | +2.7 | +2.3 | +2804.7 | hot, rep, > twins | 0 |
| 9 | 1m:DX14=high & 1m:MACDh12/26/9 sign=above 0 & 5m:FISHER>trig=below | down | 2.14 | 43.7 | -5.30 | +6.48 | -7.84 | 13.9 | pack | 7.6 | 2.14 | -2.15 | -1.2 | -1.1 | -1224.2 | > twins | 0 |
| 10 | 1m:ER10=high & 1m:KVO>sig=below & 1m:NVI sign=above 0 | up | 4.24 | 50.0 | -0.93 | -3.23 | -3.25 | 13.7 | none | 5.7 | 4.24 | -0.78 | -1.9 | -1.9 | -1989.5 | > twins | 0 |

**BTC, triples, 240 minutes, by lheat** (twins' max 16.08):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:TRIX30=low/mid/high/very high/NA & 60m:Tenkan>Kijun=above & PERP:FundZ=very low/low/mid/high | down | 3.60 | 52.5 | +3.44 | -0.02 | +7.14 | 22.0 | none | 7.0 | 0.60 | +0.05 | +1.1 | +2.4 | +1126.7 | > twins | 0 |
| 2 | 1m:ADX7=high & 5m:C-LINEARREG14 sign=below 0 & 5m:HT_TRENDMODE=cycle | up | 4.36 | 55.5 | +4.57 | +1.42 | +4.45 | 19.4 | none | 6.2 | 4.34 | +3.81 | +4.8 | +4.6 | +5010.1 | > twins | 0 |
| 3 | 1m:C-ZLEMA21 sign=above 0 & 1m:RVOL20=very high & 15m:HT_INPHASE sign=above 0 | down | 4.17 | 54.2 | +5.19 | -1.58 | +4.62 | 19.3 | none | 8.7 | 4.16 | +3.99 | +3.0 | +3.2 | +3148.5 | > twins | 0 |
| 4 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 1m:MARKETFI sign=below 0 | down | 5.53 | 52.5 | +3.47 | -0.17 | +3.38 | 18.7 | none | 4.2 | 5.53 | +2.89 | +0.8 | +0.8 | +796.3 | > twins | 0 |
| 5 | 1m:C-ZLEMA21 sign=above 0 & 1m:RVOL20=very high & 1m:DOSC sign=above 0 | down | 5.22 | 52.9 | +3.86 | -0.71 | +3.57 | 18.6 | none | 6.1 | 5.22 | +3.19 | +0.3 | +0.4 | +281.6 | > twins | 1 |
| 6 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:NVI=low | down | 4.34 | 54.0 | +5.01 | -2.70 | +4.29 | 18.6 | none | 10.0 | 4.34 | +3.71 | +2.5 | +2.4 | +2560.1 | > twins | 0 |
| 7 | 1m:MACDh12/26/9 sign=below 0 & 1m:PVO12/26=high & 5m:NVI sign=above 0 | up | 4.91 | 55.0 | +4.08 | +1.97 | +3.77 | 18.5 | pack | 7.9 | 4.90 | +3.38 | +1.5 | +1.4 | +1503.7 | > twins | 0 |
| 8 | 1m:DOSC sign=below 0 & 1m:ER10=high & 1m:NVI sign=below 0 | up | 5.92 | 53.3 | +2.40 | +0.54 | +3.02 | 17.8 | none | 6.4 | 5.92 | +1.64 | +2.1 | +2.0 | +2203.4 | > twins | 1 |
| 9 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & FLOW:TB5=very high | down | 4.08 | 54.9 | +5.92 | -1.86 | +4.25 | 17.4 | none | 10.0 | 4.07 | +3.37 | +1.9 | +2.0 | +2023.5 | > twins | 1 |
| 10 | 1m:VHF28=high & 5m:C-LINEARREG14 sign=below 0 & 5m:NVI sign=above 0 | up | 3.34 | 56.4 | +5.45 | +3.10 | +4.99 | 16.7 | none | 5.0 | 3.33 | +4.21 | +2.5 | +2.2 | +2660.9 | > twins | 0 |

**BTC, triples, 240 minutes, by oheat** (twins' max 15.91):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & FLOW:TB5=very high | down | 4.08 | 54.9 | +5.92 | -1.86 | +4.25 | 24.2 | none | 10.0 | 4.07 | +3.37 | +1.9 | +2.0 | +2023.5 | > twins | 1 |
| 2 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=above 0 & 1m:Runs=5+ up | down | 4.50 | 54.2 | +5.20 | -2.55 | +3.69 | 23.4 | pack | 12.5 | 4.50 | +3.49 | -0.2 | -0.3 | -194.7 | hot, rep, > twins | 0 |
| 3 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & OI:PxQuad60=long liquidation | up | 5.26 | 55.4 | +4.41 | +1.07 | +2.54 | 23.2 | pack | 11.1 | 5.24 | +3.05 | +2.5 | +2.5 | +2581.4 | hot, rep, > twins | 0 |
| 4 | 5m:CVI10 sign=above 0 & 15m:C-LINEARREG14 sign=above 0 & FLOW:TB5=very high | down | 4.00 | 54.7 | +5.72 | -2.11 | +3.90 | 22.9 | pack | 8.8 | 3.98 | +3.41 | +2.7 | +2.8 | +2855.0 | > twins | 0 |
| 5 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 15m:HT_INPHASE sign=above 0 | down | 4.21 | 54.3 | +5.33 | -1.45 | +4.43 | 22.4 | none | 8.7 | 4.20 | +4.06 | +3.2 | +3.4 | +3381.6 | hot, rep, > twins | 1 |
| 6 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & FLOW:Stretch15=low | up | 5.26 | 55.2 | +4.25 | +0.39 | +1.76 | 22.3 | pack | 11.1 | 5.26 | +3.44 | +1.8 | +1.8 | +1860.3 | hot, rep, > twins | 0 |
| 7 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 15m:DPO20 sign=below 0 | down | 4.31 | 54.1 | +5.10 | -1.04 | +3.89 | 22.0 | none | 8.1 | 4.31 | +4.54 | +2.4 | +2.6 | +2483.3 | hot, rep, > twins | 0 |
| 8 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:NVI=low | down | 4.34 | 54.0 | +5.01 | -2.70 | +4.29 | 21.8 | none | 10.0 | 4.34 | +3.71 | +2.5 | +2.4 | +2560.1 | hot, rep, > twins | 0 |
| 9 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 1m:HT_SINE sign=above 0 | down | 5.03 | 53.4 | +4.32 | -0.97 | +3.12 | 21.7 | none | 4.2 | 5.02 | +3.60 | +1.5 | +1.7 | +1617.4 | hot, rep, > twins | 0 |
| 10 | 1m:CVI10 sign=above 0 & 1m:KST>sig=below & FLOW:Stretch15=low | up | 5.35 | 55.0 | +4.04 | +0.33 | +1.44 | 21.6 | pack | 11.3 | 5.34 | +3.61 | +1.4 | +1.3 | +1450.4 | hot, rep, > twins | 0 |

**BTC, triples, 240 minutes, unseen, by iheat** (twins' max 11.66):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:VHF28=high & 5m:C-TSF14 sign=below 0 & 1m:KVO sign=above 0 | up | 3.08 | 47.0 | -3.95 | -5.23 | -7.06 | 16.1 | none | 4.7 | 3.06 | -2.78 | -1.2 | -1.2 | -1307.9 | > twins | 0 |
| 2 | 1m:VHF28=high & 5m:C-LINEARREG14 sign=below 0 & 1m:KVO sign=above 0 | up | 2.73 | 47.2 | -3.71 | -5.32 | -6.90 | 14.5 | none | 5.0 | 2.71 | -2.33 | -1.5 | -1.5 | -1554.0 | > twins | 0 |
| 3 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:MASSI=low | down | 3.83 | 46.1 | -2.94 | +3.77 | -4.38 | 14.4 | none | 10.0 | 3.79 | -2.11 | -1.6 | -1.7 | -1723.1 | > twins | 0 |
| 4 | 1m:DX14=high & 1m:MACDh12/26/9 sign=above 0 & 1m:C-MAMA sign=below 0 | down | 2.05 | 42.7 | -6.26 | +6.99 | -8.68 | 14.4 | none | 10.0 | 2.04 | -2.27 | -2.4 | -2.5 | -2505.8 | > twins | 0 |
| 5 | 1m:DX14=high & 1m:MACDh12/26/9 sign=above 0 & 5m:DOSC sign=below 0 | down | 2.83 | 45.3 | -3.76 | +4.96 | -6.64 | 14.0 | none | 7.6 | 2.82 | -1.35 | -1.8 | -2.0 | -1894.8 | > twins | 0 |
| 6 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:DX14=low | down | 3.14 | 52.5 | +3.46 | -4.47 | +4.33 | 14.0 | none | 9.8 | 3.12 | +0.89 | -2.2 | -2.0 | -2264.5 | hot, rep, > twins | 0 |
| 7 | 1m:DX14=high & 1m:MACDh12/26/9 sign=above 0 & 15m:SWAK_2PHP20 sign=below 0 | down | 2.89 | 45.5 | -3.57 | +4.75 | -6.63 | 13.7 | none | 7.6 | 2.88 | -1.47 | -0.9 | -0.9 | -949.5 | > twins | 0 |
| 8 | 1m:ER10=high & 1m:KVO>sig=below & 1m:NVI sign=above 0 | up | 4.24 | 50.0 | -0.93 | -3.23 | -3.25 | 13.7 | none | 5.7 | 4.24 | -0.78 | -1.9 | -1.9 | -1989.5 | > twins | 0 |
| 9 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 5m:KST>sig=below | down | 4.03 | 46.7 | -2.34 | +3.25 | -4.79 | 13.1 | none | 10.0 | 4.01 | -2.13 | -3.7 | -3.8 | -3853.0 | hot, rep, > twins | 0 |
| 10 | 1m:WAD sign=above 0 & 1m:CVI10=high & 1m:NATR14=low | down | 1.42 | 42.4 | -6.64 | +8.76 | -9.54 | 12.4 | none | 8.4 | 1.41 | -6.77 | -7.6 | -7.6 | -8184.4 | > twins | 0 |

**BTC, triples, 240 minutes, unseen, by lheat** (twins' max 11.77):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:TRIX30=low/mid/high/very high/NA & 60m:Tenkan>Kijun=above & PERP:FundZ=very low/low/mid/high | down | 3.60 | 52.5 | +3.44 | -0.02 | +7.14 | 22.0 | none | 7.0 | 0.60 | +0.05 | +1.1 | +2.4 | +1126.7 | > twins | 0 |
| 2 | 1m:ADX7=high & 5m:C-LINEARREG14 sign=below 0 & 5m:HT_TRENDMODE=cycle | up | 4.36 | 55.5 | +4.57 | +1.42 | +4.45 | 19.4 | none | 6.2 | 4.34 | +3.81 | +4.8 | +4.6 | +5010.1 | > twins | 0 |
| 3 | 1m:C-ZLEMA21 sign=above 0 & 1m:RVOL20=very high & 15m:HT_INPHASE sign=above 0 | down | 4.17 | 54.2 | +5.19 | -1.58 | +4.62 | 19.3 | none | 8.7 | 4.16 | +3.99 | +3.0 | +3.2 | +3148.5 | > twins | 0 |
| 4 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 1m:MARKETFI sign=below 0 | down | 5.53 | 52.5 | +3.47 | -0.17 | +3.38 | 18.7 | none | 4.2 | 5.53 | +2.89 | +0.8 | +0.8 | +796.3 | > twins | 0 |
| 5 | 1m:C-ZLEMA21 sign=above 0 & 1m:RVOL20=very high & 1m:DOSC sign=above 0 | down | 5.22 | 52.9 | +3.86 | -0.71 | +3.57 | 18.6 | none | 6.1 | 5.22 | +3.19 | +0.3 | +0.4 | +281.6 | > twins | 1 |
| 6 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:NVI=low | down | 4.34 | 54.0 | +5.01 | -2.70 | +4.29 | 18.6 | none | 10.0 | 4.34 | +3.71 | +2.5 | +2.4 | +2560.1 | > twins | 0 |
| 7 | 1m:DOSC sign=below 0 & 1m:ER10=high & 1m:NVI sign=below 0 | up | 5.92 | 53.3 | +2.40 | +0.54 | +3.02 | 17.8 | none | 6.4 | 5.92 | +1.64 | +2.1 | +2.0 | +2203.4 | > twins | 1 |
| 8 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & FLOW:TB5=very high | down | 4.08 | 54.9 | +5.92 | -1.86 | +4.25 | 17.4 | none | 10.0 | 4.07 | +3.37 | +1.9 | +2.0 | +2023.5 | > twins | 1 |
| 9 | 1m:VHF28=high & 5m:C-LINEARREG14 sign=below 0 & 5m:NVI sign=above 0 | up | 3.34 | 56.4 | +5.45 | +3.10 | +4.99 | 16.7 | none | 5.0 | 3.33 | +4.21 | +2.5 | +2.2 | +2660.9 | > twins | 0 |
| 10 | 1m:DX14=high & 1m:EMV14 sign=above 0 & 5m:HT_SINE sign=above 0 | down | 4.61 | 52.2 | +3.21 | -1.34 | +3.52 | 16.2 | none | 6.9 | 4.58 | +3.66 | +1.4 | +1.3 | +1431.1 | > twins | 0 |

**BTC, triples, 240 minutes, unseen, by oheat** (twins' max 13.89):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & FLOW:TB5=very high | down | 4.08 | 54.9 | +5.92 | -1.86 | +4.25 | 24.2 | none | 10.0 | 4.07 | +3.37 | +1.9 | +2.0 | +2023.5 | > twins | 1 |
| 2 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 15m:HT_INPHASE sign=above 0 | down | 4.21 | 54.3 | +5.33 | -1.45 | +4.43 | 22.4 | none | 8.7 | 4.20 | +4.06 | +3.2 | +3.4 | +3381.6 | hot, rep, > twins | 0 |
| 3 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 15m:DPO20 sign=below 0 | down | 4.31 | 54.1 | +5.10 | -1.04 | +3.89 | 22.0 | none | 8.1 | 4.31 | +4.54 | +2.4 | +2.6 | +2483.3 | hot, rep, > twins | 0 |
| 4 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:NVI=low | down | 4.34 | 54.0 | +5.01 | -2.70 | +4.29 | 21.8 | none | 10.0 | 4.34 | +3.71 | +2.5 | +2.4 | +2560.1 | hot, rep, > twins | 0 |
| 5 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=very high & 1m:HT_SINE sign=above 0 | down | 5.03 | 53.4 | +4.32 | -0.97 | +3.12 | 21.7 | none | 4.2 | 5.02 | +3.60 | +1.5 | +1.7 | +1617.4 | hot, rep, > twins | 0 |
| 6 | 5m:CVI10 sign=above 0 & 5m:SMI>sig=above & 1m:AC=high | down | 4.75 | 53.4 | +4.42 | -2.12 | +2.81 | 21.0 | none | 9.3 | 4.75 | +3.82 | +3.0 | +3.0 | +3104.2 | hot, rep, > twins | 0 |
| 7 | 5m:CVI10 sign=above 0 & 5m:SMI>sig=above & FLOW:TB15=high | down | 4.87 | 53.2 | +4.19 | -0.32 | +2.17 | 20.4 | none | 9.3 | 4.86 | +3.69 | +2.4 | +2.2 | +2509.0 | hot, rep, > twins | 0 |
| 8 | 1m:DOSC sign=below 0 & 1m:ER10=high & X.ETH:R15z=low | up | 4.39 | 55.5 | +4.58 | +0.26 | +1.75 | 20.1 | none | 6.4 | 4.39 | +3.66 | +3.7 | +3.3 | +3816.2 | hot, rep, > twins | 1 |
| 9 | 1m:ADX7=high & 5m:C-LINEARREG14 sign=below 0 & 5m:HT_TRENDMODE=cycle | up | 4.36 | 55.5 | +4.57 | +1.42 | +4.45 | 19.9 | none | 6.2 | 4.34 | +3.81 | +4.8 | +4.6 | +5010.1 | hot, rep, > twins | 0 |
| 10 | 5m:C-HMA20 sign=above 0 & 5m:TRANGE=high & 1m:MFI14=high | down | 3.38 | 54.8 | +5.81 | -3.11 | +4.75 | 19.6 | none | 9.3 | 3.38 | +4.99 | +4.7 | +4.8 | +4929.4 | hot, rep, > twins | 1 |

**ETH, pairs, 15 minutes, by iheat** (twins' max 42.06):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-TEMA21 sign=above 0 & 1m:TRANGE=high | down | 38.73 | 52.4 | +2.96 | -2.32 | +2.94 | 89.8 | none | 1.9 | 38.62 | +2.78 | +0.9 | +0.9 | +26.6 | hot, rep, BHY, > twins | 8 |
| 2 | 1m:C-TEMA21 sign=below 0 & 1m:TRANGE=high | up | 40.54 | 52.4 | +2.00 | +2.15 | +1.92 | 87.3 | none | 1.2 | 40.40 | +1.87 | -0.2 | -0.3 | -6.4 | hot, rep, BHY, > twins | 5 |
| 3 | 1m:C-TSF14 sign=above 0 & POS:QPhase=m00-04 | up | 77.86 | 51.6 | +1.22 | +1.12 | +1.54 | 87.0 | pack | 0.7 | 77.86 | +0.71 | +0.1 | +0.1 | +3.9 | > twins | 0 |
| 4 | 1m:C-TSF14 sign=below 0 & POS:QPhase=m00-04 | down | 79.17 | 50.8 | +1.35 | -1.08 | +1.76 | 85.9 | none | 1.4 | 79.17 | +0.42 | +0.0 | +0.1 | +1.4 | > twins | 0 |
| 5 | 1m:DOSC sign=above 0 & 1m:ER10=low | up | 36.08 | 51.8 | +1.39 | +2.30 | +2.40 | 83.1 | none | 6.6 | 35.71 | +1.47 | -0.3 | -0.3 | -8.0 | hot, rep, > twins | 0 |
| 6 | 1m:DOSC sign=below 0 & 1m:ER10=low | down | 37.38 | 50.9 | +1.47 | -2.20 | +2.49 | 82.1 | none | 5.8 | 37.04 | +1.49 | +0.1 | +0.1 | +2.8 | hot, rep, > twins | 0 |
| 7 | 1m:C-TSF14 sign=above 0 & 1m:TRANGE=high | down | 40.20 | 51.7 | +2.24 | -2.04 | +2.62 | 81.9 | pack | 1.2 | 40.08 | +2.10 | +0.8 | +0.8 | +24.0 | hot, rep, > twins | 0 |
| 8 | 1m:DX14=high & 1m:HAbody sign=above 0 | down | 17.87 | 55.5 | +6.04 | -4.42 | +5.34 | 79.0 | none | 13.4 | 16.48 | +5.06 | +1.6 | +1.5 | +47.7 | hot, rep, BHY, > twins | 4 |
| 9 | 1m:DX14=high & 1m:C-DEMA21 sign=above 0 | down | 17.53 | 55.2 | +5.78 | -4.49 | +5.39 | 78.7 | none | 7.3 | 16.10 | +4.79 | +1.9 | +1.9 | +57.5 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:HT_INPHASE sign=above 0 & POS:QPhase=m05-09 | down | 75.84 | 49.5 | +0.12 | +1.01 | -1.43 | 76.4 | none | 12.7 | 75.84 | +0.38 | -0.1 | -0.2 | -2.3 | > twins | 0 |

**ETH, pairs, 15 minutes, by lheat** (twins' max 69.77):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ERIbear13 sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 64.61 | 52.7 | +3.29 | -0.20 | +3.50 | 226.1 | pack | 23.3 | 55.78 | +1.68 | -0.1 | -0.0 | -1.5 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:C-FRAMA16 sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 72.19 | 52.2 | +2.78 | -0.15 | +3.19 | 213.1 | pack | 23.3 | 65.03 | +0.93 | -0.2 | +0.0 | -4.6 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:C-VWMA20 sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 55.44 | 53.0 | +3.61 | -0.35 | +3.96 | 211.7 | pack | 21.8 | 44.58 | +2.18 | +0.3 | +0.4 | +9.1 | hot, rep, BHY, > twins | 10 |
| 4 | 1m:PVI sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 69.32 | 52.3 | +2.86 | -0.19 | +3.73 | 197.7 | pack | 23.3 | 49.88 | +0.74 | -0.2 | -0.1 | -6.3 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:ERIbear13 sign=above 0 & 5m:QSTICK10 sign=above 0 | down | 52.71 | 53.4 | +4.03 | -0.35 | +3.74 | 197.0 | pack | 22.7 | 45.79 | +2.73 | +0.2 | +0.2 | +7.2 | hot, rep, BHY, > twins | 3 |
| 6 | 1m:ERIbear13 sign=above 0 & 1m:C-EMA200 sign=above 0 | down | 55.38 | 53.0 | +3.62 | -0.24 | +3.54 | 196.0 | pack | 27.1 | 47.65 | +2.30 | -0.1 | -0.1 | -3.0 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:TRIX30 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 53.29 | 52.7 | +3.33 | -0.28 | +3.67 | 195.4 | pack | 23.0 | 48.08 | +1.57 | -0.2 | -0.0 | -6.8 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-FRAMA16 sign=above 0 & 5m:PSO sign=above 0 | down | 54.37 | 52.8 | +3.36 | -0.27 | +3.59 | 192.2 | none | 20.8 | 49.28 | +1.69 | +0.1 | +0.3 | +1.7 | hot, rep, BHY, > twins | 1 |
| 9 | 1m:ERIbull13 sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 62.69 | 52.2 | +2.80 | -0.19 | +3.42 | 190.5 | pack | 21.8 | 49.11 | +1.04 | -0.0 | -0.0 | -1.0 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:TRIX30 sign=above 0 & 1m:C-SWAK_BUTTER20 sign=above 0 | down | 53.16 | 52.7 | +3.26 | -0.35 | +3.57 | 189.8 | pack | 23.0 | 48.26 | +1.59 | -0.3 | -0.1 | -8.2 | hot, rep, BHY, > twins | 7 |

**ETH, pairs, 15 minutes, by oheat** (twins' max 66.87):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ERIbear13 sign=above 0 & 1m:PVI sign=above 0 | down | 71.22 | 52.5 | +3.05 | -0.04 | +2.49 | 217.0 | pack | 21.3 | 60.20 | +1.35 | +0.1 | +0.2 | +3.9 | hot, rep, BHY, > twins | 5 |
| 2 | 1m:ERIbear13 sign=above 0 & 1m:MARKETFI sign=below 0 | down | 72.92 | 52.4 | +2.95 | -0.38 | +1.29 | 215.4 | pack | 21.3 | 68.60 | +1.60 | +0.0 | +0.0 | +1.3 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:ERIbear13 sign=above 0 & 5m:C-FRAMA16 sign=above 0 | down | 60.01 | 53.0 | +3.57 | -0.25 | +2.96 | 214.4 | pack | 25.7 | 51.75 | +2.14 | +0.0 | +0.1 | +1.2 | hot, rep, BHY, > twins | 5 |
| 4 | 1m:C-VIDYA12 sign=above 0 & 1m:PVI sign=above 0 | down | 73.51 | 52.2 | +2.82 | -0.06 | +2.58 | 207.0 | pack | 26.3 | 55.59 | +0.91 | +0.1 | +0.2 | +2.5 | hot, rep, BHY, > twins | 12 |
| 5 | 1m:C-ALMA9 sign=above 0 & 5m:C-EMA9 sign=above 0 | down | 64.73 | 52.6 | +3.19 | -0.21 | +2.08 | 206.3 | stored | 27.0 | 61.86 | +1.93 | -0.2 | +0.1 | -4.5 | hot, rep, BHY, > twins | 10 |
| 6 | 1m:C-FRAMA16 sign=above 0 & 5m:MOM10 sign=above 0 | down | 57.97 | 53.0 | +3.56 | -0.35 | +3.49 | 206.1 | none | 22.9 | 52.34 | +2.11 | +0.1 | +0.3 | +2.7 | hot, rep, BHY, > twins | 6 |
| 7 | 1m:C-EMA21 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 58.99 | 52.9 | +3.49 | -1.15 | +2.59 | 205.8 | none | 23.9 | 49.25 | +0.90 | +0.1 | +0.2 | +4.3 | hot, rep, BHY, > twins | 5 |
| 8 | 1m:C-FRAMA16 sign=above 0 & 5m:C-WMA20 sign=above 0 | down | 60.18 | 52.8 | +3.40 | -0.20 | +2.80 | 204.5 | none | 26.8 | 53.84 | +1.84 | -0.1 | +0.2 | -1.5 | hot, rep, BHY, > twins | 9 |
| 9 | 1m:AROONOSC14 sign=above 0 & 1m:PVI sign=above 0 | down | 74.68 | 52.1 | +2.73 | -0.14 | +3.10 | 203.7 | pack | 21.1 | 52.23 | +1.27 | +0.1 | +0.2 | +3.8 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:KST sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 58.49 | 52.9 | +3.48 | -0.21 | +3.15 | 203.7 | none | 25.0 | 51.95 | +2.09 | -0.1 | +0.1 | -2.0 | hot, rep, BHY, > twins | 3 |

**ETH, pairs, 15 minutes, unseen, by iheat** (twins' max 42.06):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-TEMA21 sign=above 0 & 1m:TRANGE=high | down | 38.73 | 52.4 | +2.96 | -2.32 | +2.94 | 89.8 | none | 1.9 | 38.62 | +2.78 | +0.9 | +0.9 | +26.6 | hot, rep, BHY, > twins | 2 |
| 2 | 1m:C-TEMA21 sign=below 0 & 1m:TRANGE=high | up | 40.54 | 52.4 | +2.00 | +2.15 | +1.92 | 87.3 | none | 1.2 | 40.40 | +1.87 | -0.2 | -0.3 | -6.4 | hot, rep, BHY, > twins | 5 |
| 3 | 1m:C-TSF14 sign=below 0 & POS:QPhase=m00-04 | down | 79.17 | 50.8 | +1.35 | -1.08 | +1.76 | 85.9 | none | 1.4 | 79.17 | +0.42 | +0.0 | +0.1 | +1.4 | > twins | 0 |
| 4 | 1m:DOSC sign=above 0 & 1m:ER10=low | up | 36.08 | 51.8 | +1.39 | +2.30 | +2.40 | 83.1 | none | 6.6 | 35.71 | +1.47 | -0.3 | -0.3 | -8.0 | hot, rep, > twins | 0 |
| 5 | 1m:DOSC sign=below 0 & 1m:ER10=low | down | 37.38 | 50.9 | +1.47 | -2.20 | +2.49 | 82.1 | none | 5.8 | 37.04 | +1.49 | +0.1 | +0.1 | +2.8 | hot, rep, > twins | 0 |
| 6 | 1m:DX14=high & 1m:HAbody sign=above 0 | down | 17.87 | 55.5 | +6.04 | -4.42 | +5.34 | 79.0 | none | 13.4 | 16.48 | +5.06 | +1.6 | +1.5 | +47.7 | hot, rep, BHY, > twins | 2 |
| 7 | 1m:DX14=high & 1m:C-DEMA21 sign=above 0 | down | 17.53 | 55.2 | +5.78 | -4.49 | +5.39 | 78.7 | none | 7.3 | 16.10 | +4.79 | +1.9 | +1.9 | +57.5 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:HT_INPHASE sign=above 0 & POS:QPhase=m05-09 | down | 75.84 | 49.5 | +0.12 | +1.01 | -1.43 | 76.4 | none | 12.7 | 75.84 | +0.38 | -0.1 | -0.2 | -2.3 | > twins | 0 |
| 9 | 1m:DX14=high & 1m:MACDh12/26/9 sign=below 0 | up | 16.94 | 55.4 | +4.99 | +4.50 | +4.36 | 76.3 | none | 7.7 | 15.23 | +4.83 | +0.7 | +0.6 | +21.7 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:HT_INPHASE sign=below 0 & POS:QPhase=m05-09 | up | 76.31 | 50.4 | +0.04 | -1.00 | -1.57 | 76.0 | none | 12.0 | 76.31 | +0.36 | -0.2 | -0.3 | -5.8 | > twins | 0 |

**ETH, pairs, 15 minutes, unseen, by lheat** (twins' max 69.77):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-FRAMA16 sign=above 0 & 5m:PSO sign=above 0 | down | 54.37 | 52.8 | +3.36 | -0.27 | +3.59 | 192.2 | none | 20.8 | 49.28 | +1.69 | +0.1 | +0.3 | +1.7 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:C-SAR sign=above 0 & 5m:PSO sign=above 0 | down | 50.41 | 52.9 | +3.46 | -0.28 | +3.77 | 189.2 | none | 20.8 | 34.80 | +2.24 | +0.1 | +0.3 | +4.1 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:C-SWAK_BUTTER20 sign=above 0 & 5m:FISHER10 sign=above 0 | down | 53.03 | 52.7 | +3.26 | -0.26 | +3.43 | 181.7 | none | 20.9 | 48.48 | +1.93 | +0.1 | +0.3 | +4.4 | hot, rep, BHY, > twins | 5 |
| 4 | 1m:C-SWAK_BUTTER20 sign=above 0 & 5m:WT1 sign=above 0 | down | 51.45 | 52.6 | +3.15 | -0.36 | +3.59 | 181.4 | none | 23.8 | 46.76 | +1.38 | -0.5 | -0.3 | -15.4 | hot, rep, BHY, > twins | 3 |
| 5 | 1m:C-FRAMA16 sign=above 0 & 15m:C-MCGD14 sign=above 0 | down | 49.75 | 52.7 | +3.25 | -0.28 | +3.65 | 181.4 | none | 20.4 | 45.24 | +1.65 | -0.2 | -0.0 | -7.1 | hot, rep, BHY, > twins | 1 |
| 6 | 1m:C-MIDPRICE14 sign=above 0 & 5m:PSO sign=above 0 | down | 51.53 | 52.8 | +3.42 | -0.36 | +3.90 | 181.2 | none | 20.8 | 40.66 | +1.24 | -0.1 | +0.1 | -2.7 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:C-FRAMA16 sign=above 0 & 5m:LRSLOPE14 sign=above 0 | down | 52.96 | 52.7 | +3.27 | -0.31 | +3.60 | 180.8 | none | 21.1 | 47.81 | +1.54 | -0.1 | +0.1 | -3.1 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-MIDPRICE14 sign=above 0 & 15m:C-CKSPmid sign=above 0 | down | 47.36 | 52.8 | +3.42 | -0.30 | +3.86 | 175.5 | none | 21.8 | 37.19 | +1.25 | -0.4 | -0.2 | -10.8 | hot, rep, BHY, > twins | 2 |
| 9 | 1m:C-MAMA sign=above 0 & 5m:LRSLOPE14 sign=above 0 | down | 52.80 | 52.6 | +3.14 | -0.35 | +3.53 | 174.5 | none | 21.1 | 47.73 | +1.42 | -0.1 | +0.1 | -1.9 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:HT_INPHASE sign=above 0 & 1m:HAbody sign=above 0 | down | 80.23 | 51.6 | +2.19 | -0.06 | +2.25 | 172.5 | none | 13.4 | 75.82 | +1.08 | -0.1 | -0.1 | -4.2 | hot, rep, BHY, > twins | 0 |

**ETH, pairs, 15 minutes, unseen, by oheat** (twins' max 61.21):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-FRAMA16 sign=above 0 & 5m:MOM10 sign=above 0 | down | 57.97 | 53.0 | +3.56 | -0.35 | +3.49 | 206.1 | none | 22.9 | 52.34 | +2.11 | +0.1 | +0.3 | +2.7 | hot, rep, BHY, > twins | 5 |
| 2 | 1m:C-EMA21 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 58.99 | 52.9 | +3.49 | -1.15 | +2.59 | 205.8 | none | 23.9 | 49.25 | +0.90 | +0.1 | +0.2 | +4.3 | hot, rep, BHY, > twins | 3 |
| 3 | 1m:C-FRAMA16 sign=above 0 & 5m:C-WMA20 sign=above 0 | down | 60.18 | 52.8 | +3.40 | -0.20 | +2.80 | 204.5 | none | 26.8 | 53.84 | +1.84 | -0.1 | +0.2 | -1.5 | hot, rep, BHY, > twins | 7 |
| 4 | 1m:KST sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 58.49 | 52.9 | +3.48 | -0.21 | +3.15 | 203.7 | none | 25.0 | 51.95 | +2.09 | -0.1 | +0.1 | -2.0 | hot, rep, BHY, > twins | 3 |
| 5 | 1m:SWAK_HP20 sign=above 0 & 5m:C-EMA9 sign=above 0 | down | 64.82 | 52.5 | +3.14 | -0.19 | +2.28 | 203.5 | none | 27.0 | 59.89 | +1.67 | -0.2 | +0.0 | -7.1 | hot, rep, BHY, > twins | 22 |
| 6 | 1m:C-EMA21 sign=above 0 & 1m:MARKETFI sign=below 0 | down | 78.25 | 52.0 | +2.59 | -0.43 | +1.61 | 202.9 | none | 23.9 | 74.01 | +1.37 | +0.1 | +0.1 | +2.1 | hot, rep, BHY, > twins | 7 |
| 7 | 1m:ASI sign=above 0 & 1m:HT_TRENDMODE=trend | down | 61.91 | 52.7 | +3.25 | -1.04 | +2.39 | 201.4 | none | 18.6 | 52.31 | +0.75 | +0.5 | +0.6 | +14.0 | hot, rep, BHY, > twins | 2 |
| 8 | 1m:C-WMA20 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 64.02 | 52.5 | +3.13 | -1.07 | +2.45 | 200.7 | none | 19.8 | 55.78 | +0.68 | +0.0 | +0.1 | +1.0 | hot, rep, BHY, > twins | 2 |
| 9 | 1m:DIdiff14 sign=above 0 & 1m:MARKETFI sign=below 0 | down | 72.68 | 52.2 | +2.76 | -0.36 | +1.39 | 200.6 | none | 25.5 | 68.13 | +1.56 | -0.1 | -0.1 | -3.3 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:ASI sign=above 0 & 1m:C-SMA50 sign=above 0 | down | 69.51 | 52.3 | +2.87 | -0.14 | +2.50 | 199.3 | none | 25.9 | 52.71 | +0.69 | -0.2 | -0.0 | -4.5 | hot, rep, BHY, > twins | 39 |

**ETH, triples, 15 minutes, by iheat** (twins' max 30.75):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PERCENTB20/2=very low/low/high/very high & 1m:STOCHFK5=very low/low/mid/NA & 5m:C-FRAMA16 sign=below 0/NA | up | 42.74 | 53.8 | +3.46 | +1.65 | +1.38 | 70.3 | pack | 24.5 | 41.06 | +2.62 | +0.2 | +0.2 | +6.1 | hot, rep, > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=below 0 & 1m:CVI10 sign=above 0 & 1m:PVO12/26 sign=below 0 | up | 43.94 | 51.4 | +1.07 | -1.58 | -1.21 | 69.3 | none | 12.5 | 41.69 | +0.88 | +0.1 | +0.1 | +1.5 | hot, rep, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:LRSLOPE14 sign=above 0 | down | 39.09 | 49.7 | +0.31 | +1.71 | -1.69 | 66.8 | none | 19.6 | 36.75 | +0.42 | +0.3 | +0.2 | +7.7 | hot, rep, > twins | 0 |
| 4 | 1m:MACDh12/26/9 sign=below 0 & 1m:CVI10 sign=above 0 & 1m:DX14=high | up | 14.32 | 56.0 | +5.65 | +4.64 | +4.45 | 66.4 | none | 12.5 | 13.14 | +5.75 | +1.0 | +0.7 | +28.7 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:HT_INPHASE sign=above 0 | down | 48.74 | 48.5 | -0.88 | +1.35 | -2.31 | 65.8 | none | 12.7 | 46.51 | -0.88 | -0.0 | -0.1 | -0.7 | > twins | 0 |
| 6 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:KST>sig=above | up | 32.52 | 52.2 | +1.84 | +1.99 | +1.09 | 64.7 | none | 8.7 | 30.32 | +1.04 | -0.0 | +0.0 | -0.4 | hot, rep, > twins | 0 |
| 7 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:DX14=high | down | 12.78 | 56.8 | +7.37 | -5.02 | +5.79 | 64.1 | none | 12.8 | 11.73 | +7.64 | +2.4 | +2.1 | +69.9 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:DX14=high | down | 13.50 | 56.1 | +6.72 | -4.23 | +4.84 | 57.1 | pack | 12.8 | 12.35 | +6.79 | +2.2 | +2.0 | +65.7 | hot, rep, > twins | 0 |
| 9 | 1m:C-SWAK_BUTTER20=low/high/very high/NA & NY30m=00:30/01:00/02:00/02:30/03:00/03:30/04:00/04:30/05:00/05:30/06:00/06:30/07:00/07:30/08:30/09:00/10:00/10:30/11:00/11:30/12:00/12:30/13:30/14:00/14:30/15:00/15:30/17:00/17:30/18:00/18:30/19:00/19:30/20:00/20:30/21:00/21:30/22:30/23:00/23:30/NA & X:Breadth5=mid/1 up/2 up/3 up | down | 41.74 | 52.9 | +3.50 | -1.32 | -0.22 | 55.1 | pack | 0.0 | 39.88 | +2.73 | +0.6 | +0.7 | +18.5 | hot, rep, > twins | 0 |
| 10 | 1m:C-KAMA30 sign=below 0/NA & POS:QPos=m00/m01/m14 & X.BTC:RSI14=very low/low | up | 21.60 | 56.8 | +6.47 | +2.33 | +2.98 | 50.2 | none | 25.9 | 15.14 | +5.68 | +0.7 | +0.6 | +22.1 | > twins | 0 |

**ETH, triples, 15 minutes, by lheat** (twins' max 48.31):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ADX28=mid/high/very high/NA & 1m:C-ALMA9 sign=above 0/NA & 1m:CORRELcv30 sign=above 0/NA | down | 57.44 | 52.7 | +3.29 | -0.60 | +2.87 | 156.2 | pack | 21.8 | 54.99 | +1.96 | +0.0 | +0.1 | +1.0 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:ERIbull13 sign=above 0 | down | 40.30 | 53.3 | +3.88 | -0.20 | +3.74 | 150.6 | none | 19.6 | 30.43 | +2.19 | +0.1 | +0.2 | +3.3 | hot, rep, BHY, > twins | 24 |
| 3 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:QSTICK10 sign=above 0 | down | 35.86 | 54.0 | +4.58 | -0.41 | +4.06 | 145.4 | none | 19.4 | 28.67 | +2.58 | +0.1 | +0.2 | +1.8 | hot, rep, BHY, > twins | 3 |
| 4 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:MACDh12/26/9 sign=above 0 | down | 42.42 | 52.9 | +3.44 | -0.48 | +3.43 | 145.4 | pack | 12.8 | 35.25 | +2.77 | +0.3 | +0.3 | +9.0 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:OBV sign=above 0 | down | 52.65 | 52.6 | +3.20 | -0.34 | +2.70 | 142.1 | none | 17.2 | 46.32 | +2.42 | +0.5 | +0.6 | +15.7 | hot, rep, BHY, > twins | 1 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:ADOSC sign=above 0 | down | 53.46 | 52.4 | +2.99 | -0.20 | +2.64 | 141.2 | pack | 13.1 | 47.45 | +2.31 | +0.5 | +0.5 | +13.5 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:SWAK_HP20 sign=above 0 | down | 44.54 | 53.0 | +3.63 | -0.34 | +3.10 | 138.1 | pack | 16.0 | 40.60 | +2.43 | +0.1 | +0.0 | +2.6 | hot, rep, BHY, > twins | 2 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:ERIbull13 sign=above 0 | down | 42.18 | 53.0 | +3.60 | -0.13 | +3.20 | 134.9 | pack | 19.6 | 35.81 | +2.49 | +0.2 | +0.2 | +4.7 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:AD sign=above 0 | down | 48.86 | 52.4 | +3.00 | -0.39 | +2.75 | 134.6 | pack | 12.8 | 43.15 | +2.56 | +0.6 | +0.6 | +17.9 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:AROONup25=mid/high/very high/NA & 1m:WILLR14=high/very high & 5m:PVT=very low/low/mid/high/NA | down | 47.99 | 52.2 | +2.76 | -0.24 | +2.80 | 134.4 | pack | 0.0 | 46.62 | +2.67 | +0.3 | +0.4 | +8.4 | > twins | 0 |

**ETH, triples, 15 minutes, by oheat** (twins' max 41.76):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PVI sign=above 0/NA & 5m:C-KAMA30 sign=above 0/NA & POS:QPos=m00/m01/m02/m03/m04/m05/m07/m08/m12/NA | down | 51.83 | 53.1 | +3.71 | -0.34 | +0.67 | 192.2 | pack | 29.3 | 51.83 | +3.26 | +0.1 | +0.0 | +2.4 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:ADX28=mid/high/very high & 1m:C-T3_5 sign=above 0 & 1m:KST sign=above 0 | down | 55.04 | 52.9 | +3.44 | -0.42 | +2.00 | 189.6 | pack | 25.0 | 52.15 | +1.94 | -0.2 | -0.0 | -6.7 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:ADX28=mid/high/very high/NA & 1m:C-ALMA9 sign=above 0/NA & 1m:CORRELcv30 sign=above 0/NA | down | 57.44 | 52.7 | +3.29 | -0.60 | +2.87 | 188.9 | pack | 21.8 | 54.99 | +1.96 | +0.0 | +0.1 | +1.0 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:ERIbear13 sign=above 0 | down | 50.47 | 53.1 | +3.69 | -0.24 | +1.99 | 186.0 | pack | 21.3 | 45.37 | +2.52 | +0.5 | +0.6 | +16.3 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:C-SWAK_GAUSS20 sign=above 0 & 5m:PVI sign=above 0 & POS:QPos=m00/m01/m02/m04/m06/m08/m09/m10/m13/m14/NA | down | 53.69 | 52.8 | +3.42 | -0.51 | +0.49 | 183.8 | pack | 23.0 | 51.51 | +2.80 | +0.2 | +0.3 | +5.3 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-SWAK_BUTTER20 sign=above 0 & 1m:CCI50 sign=above 0 & 5m:ERIbear13 sign=above 0/NA | down | 39.80 | 53.9 | +4.49 | -0.54 | +3.11 | 178.7 | stored | 26.6 | 36.24 | +3.17 | -0.1 | +0.0 | -4.3 | hot, rep, BHY, > twins | 0 |
| 7 | 15m:C-AVGPRICE sign=above 0/NA & 1m:ERIbear13 sign=above 0 & 5m:C-VIDYA12 sign=above 0 | down | 35.25 | 54.4 | +5.04 | -0.62 | +3.19 | 177.5 | pack | 28.3 | 30.99 | +3.91 | +0.3 | +0.4 | +8.3 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:C-KAMA30 sign=above 0 | down | 51.16 | 52.9 | +3.47 | -0.28 | +2.06 | 177.4 | pack | 26.7 | 44.49 | +2.88 | +0.5 | +0.6 | +16.4 | hot, rep, BHY, > twins | 0 |
| 9 | 15m:SI sign=above 0/NA & 1m:ERIbear13 sign=above 0 & 5m:C-KAMA30 sign=above 0 | down | 34.56 | 54.5 | +5.10 | -0.49 | +3.16 | 176.3 | pack | 29.3 | 30.33 | +4.08 | +0.1 | +0.1 | +3.1 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:AROONOSC25 sign=above 0 & 1m:C-SUPERTREND10/3=very low/high/very high & 60m:C-MEDPRICE=very low/low/mid/NA | down | 39.88 | 53.8 | +4.42 | -0.69 | -1.80 | 176.3 | pack | 24.6 | 39.32 | +3.93 | +0.8 | +0.9 | +25.1 | hot, rep, BHY, > twins | 0 |

**ETH, triples, 15 minutes, unseen, by iheat** (twins' max 28.81):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=below 0 & 1m:CVI10 sign=above 0 & 1m:PVO12/26 sign=below 0 | up | 43.94 | 51.4 | +1.07 | -1.58 | -1.21 | 69.3 | none | 12.5 | 41.69 | +0.88 | +0.1 | +0.1 | +1.5 | hot, rep, > twins | 0 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:LRSLOPE14 sign=above 0 | down | 39.09 | 49.7 | +0.31 | +1.71 | -1.69 | 66.8 | none | 19.6 | 36.75 | +0.42 | +0.3 | +0.2 | +7.7 | hot, rep, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=below 0 & 1m:CVI10 sign=above 0 & 1m:DX14=high | up | 14.32 | 56.0 | +5.65 | +4.64 | +4.45 | 66.4 | none | 12.5 | 13.14 | +5.75 | +1.0 | +0.7 | +28.7 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:HT_INPHASE sign=above 0 | down | 48.74 | 48.5 | -0.88 | +1.35 | -2.31 | 65.8 | none | 12.7 | 46.51 | -0.88 | -0.0 | -0.1 | -0.7 | > twins | 0 |
| 5 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:KST>sig=above | up | 32.52 | 52.2 | +1.84 | +1.99 | +1.09 | 64.7 | none | 8.7 | 30.32 | +1.04 | -0.0 | +0.0 | -0.4 | hot, rep, > twins | 0 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:DX14=high | down | 12.78 | 56.8 | +7.37 | -5.02 | +5.79 | 64.1 | none | 12.8 | 11.73 | +7.64 | +2.4 | +2.1 | +69.9 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:C-KAMA30 sign=below 0/NA & POS:QPos=m00/m01/m14 & X.BTC:RSI14=very low/low | up | 21.60 | 56.8 | +6.47 | +2.33 | +2.98 | 50.2 | none | 25.9 | 15.14 | +5.68 | +0.7 | +0.6 | +22.1 | > twins | 0 |
| 8 | 1m:SI=very low/low & 1m:STDDEV20=very low/low/mid/NA & 1m:TRANGE=high/very high | up | 33.59 | 52.7 | +2.40 | +1.46 | -1.04 | 49.1 | none | 0.0 | 33.50 | +2.32 | +0.0 | +0.0 | +0.9 | > twins | 0 |
| 9 | 1m:SI=very low/low & 1m:STDDEV20=very low/low/mid/NA & 1m:TRANGE=very low/low/mid/NA | up | 46.83 | 51.4 | +1.07 | -1.00 | -1.34 | 46.7 | none | 0.0 | 46.73 | +0.91 | +0.1 | +0.1 | +2.4 | > twins | 0 |
| 10 | 1m:SWAK_HP20 sign=above 0 & 5m:SI=very low/low/high/very high & POS:QPos=m00/m01/m02/m03/m05/m10/m12/m14/NA | down | 30.73 | 52.7 | +3.32 | -1.40 | +1.17 | 42.9 | none | 16.0 | 29.60 | +2.69 | +0.6 | +0.4 | +17.5 | hot, rep, > twins | 0 |

**ETH, triples, 15 minutes, unseen, by lheat** (twins' max 30.20):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:ERIbull13 sign=above 0 | down | 40.30 | 53.3 | +3.88 | -0.20 | +3.74 | 150.6 | none | 19.6 | 30.43 | +2.19 | +0.1 | +0.2 | +3.3 | hot, rep, BHY, > twins | 22 |
| 2 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:QSTICK10 sign=above 0 | down | 35.86 | 54.0 | +4.58 | -0.41 | +4.06 | 145.4 | none | 19.4 | 28.67 | +2.58 | +0.1 | +0.2 | +1.8 | hot, rep, BHY, > twins | 2 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:OBV sign=above 0 | down | 52.65 | 52.6 | +3.20 | -0.34 | +2.70 | 142.1 | none | 17.2 | 46.32 | +2.42 | +0.5 | +0.6 | +15.7 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:MACDh12/26/9 sign=above 0 | down | 53.67 | 52.0 | +2.61 | -0.30 | +2.53 | 135.8 | none | 12.8 | 46.49 | +2.03 | +0.4 | +0.5 | +10.8 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:SWAK_HP20 sign=above 0 | down | 58.52 | 52.3 | +2.87 | -0.06 | +2.30 | 134.7 | none | 16.0 | 54.02 | +1.73 | +0.1 | +0.2 | +1.9 | hot, rep, BHY, > twins | 4 |
| 6 | 15m:PVT=very low/low/mid/high/NA & 5m:CMF20 sign=above 0 & PERP:FundZ=very low/low/mid/high/NA | down | 57.75 | 50.5 | +1.10 | -0.00 | +2.10 | 112.7 | none | 14.0 | 15.74 | +1.64 | +0.2 | +0.2 | +6.2 | > twins | 0 |
| 7 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 5m:ASI sign=above 0 | down | 33.83 | 53.5 | +4.04 | -0.06 | +3.27 | 110.6 | none | 23.1 | 24.33 | +2.87 | +0.2 | +0.3 | +7.3 | hot, rep, BHY, > twins | 2 |
| 8 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:KVO>sig=above | down | 30.44 | 52.8 | +3.40 | -0.53 | +3.28 | 99.9 | none | 6.6 | 30.22 | +3.21 | +0.4 | +0.3 | +11.1 | > twins | 3 |
| 9 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:FISHER>trig=above | down | 32.63 | 52.7 | +3.29 | -0.36 | +2.85 | 93.1 | none | 7.6 | 32.37 | +3.13 | +0.5 | +0.5 | +14.7 | > twins | 0 |
| 10 | 1m:DX14=high & 1m:KVO sign=above 0 & 1m:SMI>sig=above | down | 13.78 | 56.7 | +7.25 | -0.93 | +6.66 | 91.7 | none | 9.6 | 12.43 | +7.17 | +2.4 | +2.2 | +71.6 | hot, rep, BHY, > twins | 9 |

**ETH, triples, 15 minutes, unseen, by oheat** (twins' max 39.79):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:ASI sign=above 0 | down | 56.58 | 52.5 | +3.09 | -0.33 | +2.01 | 174.7 | none | 18.6 | 49.41 | +2.37 | +0.6 | +0.7 | +16.9 | hot, rep, BHY, > twins | 22 |
| 2 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:HAbody sign=above 0 | down | 34.77 | 54.3 | +4.93 | -0.64 | +3.45 | 171.5 | none | 19.4 | 32.32 | +3.39 | +0.2 | +0.4 | +4.8 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:SWAK_HP20 sign=above 0 | down | 35.12 | 54.3 | +4.88 | -0.55 | +3.78 | 171.3 | none | 19.4 | 32.12 | +3.07 | +0.0 | +0.2 | +0.7 | hot, rep, BHY, > twins | 5 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:OBV sign=above 0 | down | 52.65 | 52.6 | +3.20 | -0.34 | +2.70 | 168.7 | none | 17.2 | 46.32 | +2.42 | +0.5 | +0.6 | +15.7 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:SWAK_HP20 sign=above 0 | down | 58.52 | 52.3 | +2.87 | -0.06 | +2.30 | 168.2 | none | 16.0 | 54.02 | +1.73 | +0.1 | +0.2 | +1.9 | hot, rep, BHY, > twins | 1 |
| 6 | 15m:ULTOSC=mid/high/very high/NA & 1m:C-MEDIAN30 sign=above 0/NA & 1m:CHOP14=very low/low/mid/NA | down | 72.88 | 51.7 | +2.27 | -0.11 | +1.92 | 165.7 | none | 24.3 | 52.94 | -0.11 | -0.3 | -0.1 | -8.1 | hot, rep, BHY, > twins | 0 |
| 7 | 5m:C-EMA9 sign=below 0/NA & 5m:C-MEDPRICE sign=below 0 & POS:QPos=m00/m01/m03/m06/m10 | up | 57.55 | 53.2 | +2.87 | +0.20 | +0.33 | 164.9 | none | 26.3 | 57.55 | +2.75 | +0.1 | +0.1 | +2.4 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:CCI14 sign=above 0 | down | 35.68 | 54.0 | +4.61 | -0.43 | +4.08 | 164.6 | none | 19.4 | 27.67 | +2.68 | -0.1 | +0.1 | -2.4 | hot, rep, BHY, > twins | 15 |
| 9 | 1m:C-EMA50 sign=below 0/NA & 5m:BBW20=mid/high/very high/NA & 5m:BOP sign=below 0/NA | up | 58.11 | 53.1 | +2.73 | -0.03 | +0.99 | 158.8 | none | 27.2 | 47.04 | +1.71 | +0.2 | +0.5 | +6.2 | hot, rep, BHY, > twins | 0 |
| 10 | 15m:C-KAMA30 sign=above 0/NA & 1m:C-MIDPRICE14 sign=above 0 & 5m:C-KAMA30 sign=above 0 | down | 39.82 | 53.3 | +3.87 | -0.34 | +1.75 | 154.0 | none | 29.3 | 31.18 | +1.49 | -0.8 | -0.7 | -24.0 | hot, rep, BHY, > twins | 1 |

**ETH, pairs, 60 minutes, by iheat** (twins' max 30.69):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:STOCHRSI14=very high & 1m:RVOL20=high | down | 15.14 | 52.7 | +4.05 | -2.46 | +3.03 | 37.2 | none | 4.4 | 15.12 | +4.05 | +1.1 | +1.0 | +33.3 | hot, rep, > twins | 0 |
| 2 | 1m:DX14=low & 1m:ERIbear13 sign=above 0 | up | 12.11 | 52.3 | +1.08 | +2.98 | +1.37 | 36.1 | pack | 17.0 | 12.03 | +0.98 | -0.2 | -0.2 | -6.9 | hot, rep, > twins | 0 |
| 3 | 1m:TRANGE=high & 1m:SWAK_2PHP20 sign=above 0 | down | 21.23 | 51.1 | +2.39 | -1.69 | +2.40 | 35.8 | pack | 1.8 | 21.22 | +2.18 | +0.7 | +0.7 | +21.1 | > twins | 8 |
| 4 | 1m:C-TSF14=high & 1m:RVOL20=high | down | 9.31 | 53.1 | +4.40 | -3.84 | +4.46 | 35.7 | pack | 1.5 | 9.31 | +4.57 | +2.9 | +2.8 | +86.0 | hot, rep, > twins | 0 |
| 5 | 1m:C-LINEARREG14 sign=above 0 & 1m:RVOL20=high | down | 20.93 | 50.9 | +2.28 | -1.65 | +2.02 | 34.5 | pack | 5.7 | 20.92 | +2.04 | +0.4 | +0.4 | +10.9 | hot, rep, > twins | 0 |
| 6 | 1m:TRANGE=high & 1m:SWAK_2PHP20 sign=below 0 | up | 21.36 | 52.4 | +1.22 | +1.59 | +1.15 | 33.9 | none | 0.7 | 21.34 | +1.21 | +0.4 | +0.2 | +10.6 | > twins | 2 |
| 7 | 1m:DX14=low & 1m:ERIbull13 sign=below 0 | down | 11.55 | 49.5 | +0.77 | -2.82 | +1.03 | 32.6 | none | 17.6 | 11.47 | +0.85 | -1.2 | -1.1 | -34.7 | hot, rep, > twins | 0 |
| 8 | 1m:ER10=low & 1m:ERIbull13 sign=below 0 | up | 13.80 | 50.9 | -0.35 | -2.30 | -2.13 | 31.7 | none | 17.6 | 13.78 | -0.26 | -1.8 | -1.9 | -54.5 | > twins | 0 |
| 9 | 1m:STOCHRSI14=very high & 1m:OBVdiv10=bear div | up | 14.22 | 51.8 | +0.60 | +2.17 | +1.18 | 30.8 | none | 4.4 | 14.18 | +0.29 | -1.0 | -1.4 | -28.4 | > twins | 0 |
| 10 | 1m:DX14=low & 1m:DIdiff14 sign=below 0 | down | 19.42 | 48.6 | -0.05 | -1.57 | -0.02 | 30.6 | none | 17.4 | 19.37 | +0.23 | +1.0 | +1.1 | +29.8 | hot, rep | 0 |

**ETH, pairs, 60 minutes, by lheat** (twins' max 42.04):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-TSF14 sign=above 0 & 1m:PERCENTB20/2=very high | down | 13.04 | 53.5 | +4.80 | +0.00 | +4.81 | 62.8 | pack | 6.1 | 13.00 | +4.58 | +2.3 | +2.3 | +68.7 | hot, rep, BHY, > twins | 21 |
| 2 | 1m:C-LINEARREG14 sign=above 0 & 1m:C-VWAP20=high | down | 19.08 | 52.0 | +3.33 | -0.90 | +3.29 | 62.8 | pack | 8.0 | 18.99 | +2.96 | +0.6 | +0.7 | +17.1 | > twins | 1 |
| 3 | 1m:C-KAMA30 sign=below 0 & 60m:MAMA>FAMA=below | up | 11.75 | 55.9 | +4.73 | +1.01 | +5.27 | 61.9 | pack | 15.0 | 11.29 | +3.09 | +1.7 | +1.8 | +49.7 | hot, rep, BHY, > twins | 3 |
| 4 | 1m:C-FRAMA16=high & 5m:ERIbull13 sign=above 0 | down | 19.36 | 52.2 | +3.57 | -0.61 | +3.13 | 60.6 | pack | 17.8 | 19.25 | +3.22 | +0.8 | +1.0 | +25.1 | hot, rep, BHY, > twins | 6 |
| 5 | 1m:MACDh5/35/5=high & 1m:CVI10 sign=above 0 | down | 18.98 | 51.7 | +3.01 | -1.43 | +3.19 | 60.6 | none | 3.2 | 18.89 | +3.00 | +0.7 | +0.7 | +21.6 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-KAMA30=high & 1m:C-ZLEMA21 sign=above 0 | down | 16.01 | 52.5 | +3.84 | -0.69 | +3.77 | 60.3 | pack | 10.8 | 15.85 | +3.75 | -0.4 | -0.3 | -10.8 | > twins | 2 |
| 7 | 1m:CCI50 sign=below 0 & 60m:MAMA>FAMA=below | up | 11.48 | 55.9 | +4.67 | +1.05 | +5.24 | 60.1 | pack | 17.3 | 10.09 | +2.96 | +0.2 | +0.3 | +5.3 | hot, rep, BHY, > twins | 6 |
| 8 | 1m:C-SMA50 sign=below 0 & 60m:AO sign=below 0 | up | 11.42 | 55.6 | +4.36 | +1.08 | +5.25 | 60.0 | pack | 17.3 | 10.34 | +2.63 | -0.5 | -0.3 | -14.3 | hot, rep, BHY, > twins | 5 |
| 9 | 1m:CCI14=very high & 1m:C-TSF14 sign=above 0 | down | 13.40 | 53.1 | +4.45 | -0.01 | +4.45 | 59.7 | pack | 5.2 | 13.37 | +3.91 | +1.4 | +1.1 | +41.5 | hot, rep, BHY, > twins | 2 |
| 10 | 1m:C-KAMA30 sign=below 0 & 60m:DIdiff14 sign=below 0 | up | 12.99 | 55.1 | +3.92 | +0.67 | +4.58 | 59.5 | none | 15.0 | 12.50 | +2.59 | +0.6 | +0.7 | +17.1 | hot, rep, BHY, > twins | 3 |

**ETH, pairs, 60 minutes, by oheat** (twins' max 39.51):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:AROONup25=very high & 1m:C-TSF14 sign=above 0 | down | 20.45 | 52.4 | +3.77 | -0.62 | +2.07 | 77.0 | pack | 9.8 | 20.37 | +3.46 | +1.0 | +1.1 | +28.5 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:AROONup14=very high & 1m:CVI10 sign=above 0 | down | 21.01 | 52.2 | +3.56 | -1.11 | +2.45 | 74.7 | pack | 9.4 | 20.97 | +3.23 | +0.3 | +0.4 | +10.3 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:AROONup25=very high & 1m:C-AVGPRICE sign=above 0 | down | 20.53 | 52.2 | +3.58 | -0.30 | +1.61 | 73.4 | pack | 9.8 | 20.45 | +3.48 | +0.8 | +0.9 | +24.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:AROONup25=very high & 1m:CVI10 sign=above 0 | down | 18.60 | 52.6 | +3.91 | -0.78 | +1.92 | 72.8 | pack | 9.8 | 18.52 | +3.55 | +0.0 | +0.1 | +1.4 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:C-SUPERTREND10/3=high & 1m:CVI10 sign=above 0 | down | 18.51 | 52.6 | +3.90 | -1.22 | +2.93 | 72.3 | pack | 9.8 | 18.48 | +4.17 | +0.9 | +0.9 | +25.5 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:KST sign=above 0 & 1m:C-FRAMA16=high | down | 16.95 | 52.8 | +4.17 | -0.65 | +3.12 | 70.8 | pack | 17.2 | 16.81 | +3.74 | +0.9 | +1.0 | +27.0 | hot, rep, BHY, > twins | 1 |
| 7 | 1m:AROONOSC25 sign=above 0 & 1m:C-SWAK_GAUSS20=high | down | 19.23 | 52.3 | +3.67 | -0.36 | +2.60 | 70.6 | pack | 17.6 | 19.16 | +3.70 | +0.7 | +0.9 | +19.7 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:KST sign=above 0 & 1m:C-MAMA=high | down | 17.34 | 52.7 | +4.07 | -0.65 | +3.02 | 70.5 | pack | 17.2 | 17.26 | +3.99 | +0.2 | +0.2 | +7.0 | hot, rep, BHY, > twins | 3 |
| 9 | 1m:KST sign=above 0 & 1m:C-SWAK_GAUSS20=high | down | 17.22 | 52.7 | +4.07 | -0.50 | +3.01 | 70.1 | pack | 17.2 | 17.17 | +3.80 | +0.0 | +0.3 | +1.1 | hot, rep, BHY, > twins | 2 |
| 10 | 1m:AROONOSC25 sign=above 0 & 1m:HAbody=high | down | 19.39 | 52.3 | +3.61 | -0.50 | +2.49 | 69.9 | pack | 17.6 | 19.33 | +3.64 | +0.7 | +0.8 | +21.9 | hot, rep, BHY, > twins | 1 |

**ETH, pairs, 60 minutes, unseen, by iheat** (twins' max 28.91):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:STOCHRSI14=very high & 1m:RVOL20=high | down | 15.14 | 52.7 | +4.05 | -2.46 | +3.03 | 37.2 | none | 4.4 | 15.12 | +4.05 | +1.1 | +1.0 | +33.3 | hot, rep, > twins | 0 |
| 2 | 1m:TRANGE=high & 1m:SWAK_2PHP20 sign=below 0 | up | 21.36 | 52.4 | +1.22 | +1.59 | +1.15 | 33.9 | none | 0.7 | 21.34 | +1.21 | +0.4 | +0.2 | +10.6 | > twins | 1 |
| 3 | 1m:RVOL20=high & 1m:KVO>sig=above | down | 20.56 | 50.9 | +2.28 | -1.64 | +2.01 | 33.8 | none | 3.9 | 20.55 | +2.07 | +0.0 | -0.0 | +0.2 | hot, rep, > twins | 0 |
| 4 | 1m:C-DEMA21 sign=above 0 & 1m:RVOL20=high | down | 20.11 | 51.4 | +2.69 | -1.66 | +2.04 | 33.5 | none | 8.1 | 20.10 | +2.60 | +0.1 | +0.1 | +3.6 | hot, rep, > twins | 0 |
| 5 | 1m:FOSC5 sign=above 0 & 1m:TRANGE=high | down | 21.33 | 50.9 | +2.22 | -1.54 | +2.24 | 32.8 | none | 1.6 | 21.33 | +2.11 | +0.8 | +0.8 | +22.9 | > twins | 0 |
| 6 | 1m:DX14=low & 1m:ERIbull13 sign=below 0 | down | 11.55 | 49.5 | +0.77 | -2.82 | +1.03 | 32.6 | none | 17.6 | 11.47 | +0.85 | -1.2 | -1.1 | -34.7 | hot, rep, > twins | 0 |
| 7 | 1m:ER10=low & 1m:ERIbull13 sign=below 0 | up | 13.80 | 50.9 | -0.35 | -2.30 | -2.13 | 31.7 | none | 17.6 | 13.78 | -0.26 | -1.8 | -1.9 | -54.5 | > twins | 0 |
| 8 | 1m:C-TEMA21 sign=above 0 & 1m:TRANGE=high | down | 20.91 | 51.2 | +2.52 | -1.50 | +2.22 | 31.4 | none | 5.9 | 20.91 | +2.43 | +1.0 | +1.0 | +29.8 | > twins | 0 |
| 9 | 1m:STOCHRSI14=very high & 1m:OBVdiv10=bear div | up | 14.22 | 51.8 | +0.60 | +2.17 | +1.18 | 30.8 | none | 4.4 | 14.18 | +0.29 | -1.0 | -1.4 | -28.4 | > twins | 0 |
| 10 | 1m:DX14=low & 1m:DIdiff14 sign=below 0 | down | 19.42 | 48.6 | -0.05 | -1.57 | -0.02 | 30.6 | none | 17.4 | 19.37 | +0.23 | +1.0 | +1.1 | +29.8 | hot, rep, > twins | 0 |

**ETH, pairs, 60 minutes, unseen, by lheat** (twins' max 42.04):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh5/35/5=high & 1m:CVI10 sign=above 0 | down | 18.98 | 51.7 | +3.01 | -1.43 | +3.19 | 60.6 | none | 3.2 | 18.89 | +3.00 | +0.7 | +0.7 | +21.6 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:C-KAMA30 sign=below 0 & 60m:DIdiff14 sign=below 0 | up | 12.99 | 55.1 | +3.92 | +0.67 | +4.58 | 59.5 | none | 15.0 | 12.50 | +2.59 | +0.6 | +0.7 | +17.1 | hot, rep, BHY, > twins | 3 |
| 3 | 1m:CCI50 sign=below 0 & 60m:Tenkan>Kijun=below | up | 10.99 | 55.8 | +4.54 | +1.15 | +5.41 | 59.5 | none | 17.3 | 9.69 | +3.11 | -0.5 | -0.4 | -15.6 | hot, rep, BHY, > twins | 5 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 5m:MOM10 sign=above 0 | down | 20.46 | 51.2 | +2.55 | -0.42 | +2.87 | 58.6 | none | 17.5 | 19.79 | +1.88 | +0.6 | +0.8 | +17.9 | hot, rep, BHY, > twins | 4 |
| 5 | 1m:MACDh12/26/9 sign=above 0 & 5m:LRSLOPE14 sign=above 0 | down | 18.39 | 51.5 | +2.79 | -0.42 | +3.10 | 57.0 | none | 16.8 | 17.69 | +1.70 | -0.1 | +0.1 | -2.7 | hot, rep, > twins | 0 |
| 6 | 1m:C-MCGD14 sign=below 0 & 60m:Tenkan>Kijun=below | up | 11.40 | 55.5 | +4.31 | +0.97 | +4.99 | 56.9 | none | 17.6 | 11.20 | +2.65 | +0.8 | +0.9 | +22.6 | hot, rep, BHY, > twins | 1 |
| 7 | 1m:EMA9>EMA21=below & 60m:DIdiff14 sign=below 0 | up | 12.87 | 55.0 | +3.78 | +0.68 | +4.41 | 56.7 | none | 16.9 | 11.37 | +2.46 | -1.6 | -1.4 | -46.8 | hot, rep, BHY, > twins | 6 |
| 8 | 1m:MACDh5/35/5 sign=above 0 & 5m:LRSLOPE14 sign=above 0 | down | 19.24 | 51.3 | +2.63 | -0.51 | +2.92 | 56.1 | none | 16.8 | 18.88 | +1.61 | -0.5 | -0.4 | -15.0 | hot, rep, BHY, > twins | 1 |
| 9 | 1m:CCI20=high & 5m:C-HMA20 sign=above 0 | down | 20.11 | 52.0 | +3.37 | -0.31 | +2.78 | 55.9 | none | 10.4 | 19.98 | +3.26 | +1.2 | +1.4 | +34.7 | > twins | 5 |
| 10 | 1m:MACDh5/35/5 sign=above 0 & 5m:PVT sign=above 0 | down | 20.23 | 51.1 | +2.41 | -0.48 | +2.74 | 55.4 | none | 18.0 | 19.85 | +1.60 | -0.5 | -0.4 | -14.5 | hot, rep, BHY, > twins | 1 |

**ETH, pairs, 60 minutes, unseen, by oheat** (twins' max 39.51):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI20=high & 5m:KDJ K>D=above | down | 19.28 | 52.3 | +3.60 | -0.36 | +2.83 | 69.3 | none | 9.4 | 19.14 | +3.43 | +1.2 | +1.4 | +36.0 | hot, rep, BHY, > twins | 4 |
| 2 | 1m:CCI20=high & 1m:KST sign=above 0 | down | 17.58 | 52.5 | +3.80 | -0.29 | +2.76 | 66.9 | none | 17.2 | 17.44 | +3.93 | +0.6 | +0.9 | +18.3 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:STOCHRSI14=very high & 1m:TRIX15 sign=above 0 | down | 17.92 | 52.3 | +3.67 | -0.55 | +2.69 | 65.8 | none | 17.4 | 17.82 | +3.44 | +0.1 | +0.3 | +1.7 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:CCI20=high & 5m:C-TSF14 sign=above 0 | down | 19.91 | 52.0 | +3.30 | -0.29 | +2.13 | 65.7 | none | 9.4 | 19.78 | +3.20 | +1.5 | +1.7 | +44.6 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:CCI14=low & X:Breadth15=3 down | up | 19.46 | 54.6 | +3.35 | +0.46 | +1.95 | 65.2 | none | 11.7 | 19.37 | +3.03 | +1.0 | +1.0 | +30.5 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:KST sign=above 0 & 1m:WAD=high | down | 15.30 | 52.9 | +4.19 | -0.67 | +3.19 | 64.2 | none | 17.2 | 15.11 | +4.60 | +1.0 | +1.0 | +31.1 | hot, rep, BHY, > twins | 1 |
| 7 | 1m:SQZMOM sign=above 0 & 1m:C-T3_5=high | down | 19.49 | 52.0 | +3.29 | -0.48 | +2.25 | 64.2 | none | 17.6 | 19.44 | +3.30 | +0.8 | +0.9 | +25.1 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-LINEARREG14=high & 1m:SINE>LEAD=above | down | 14.36 | 53.1 | +4.44 | -1.53 | +3.46 | 63.8 | none | 17.2 | 14.33 | +4.14 | +0.7 | +0.7 | +19.7 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:KST sign=above 0 & 1m:C-SAR=high | down | 15.38 | 52.8 | +4.14 | -1.01 | +3.06 | 63.7 | none | 17.2 | 15.22 | +3.77 | +0.1 | +0.2 | +3.3 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:TRIX15 sign=above 0 & 1m:C-T3_5=high | down | 16.02 | 52.6 | +3.92 | -0.80 | +2.84 | 62.7 | none | 17.4 | 16.00 | +3.95 | +0.0 | +0.1 | +1.3 | hot, rep, BHY, > twins | 0 |

**ETH, triples, 60 minutes, by iheat** (twins' max 15.86):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:LRSLOPE14 sign=below 0 | up | 14.04 | 53.6 | +2.39 | +2.24 | +1.21 | 31.5 | none | 15.4 | 13.94 | +1.21 | -0.6 | -0.6 | -19.2 | hot, rep, > twins | 0 |
| 2 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:MOM10 sign=below 0 | up | 17.34 | 53.2 | +1.91 | +1.79 | +0.69 | 31.1 | pack | 15.5 | 17.27 | +1.15 | +0.1 | +0.2 | +2.6 | hot, rep, > twins | 2 |
| 3 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:EMV14 sign=below 0 | up | 17.20 | 52.5 | +1.32 | +1.78 | +0.40 | 30.6 | none | 13.1 | 17.09 | +0.69 | +1.3 | +1.3 | +38.7 | hot, rep, > twins | 0 |
| 4 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=below 0 & 1m:DX14=high | up | 9.65 | 54.8 | +3.52 | +2.83 | +3.04 | 27.3 | pack | 14.9 | 9.45 | +3.39 | +0.8 | +0.6 | +23.9 | hot, rep, > twins | 0 |
| 5 | 1m:SI=very low/low & 1m:STDDEV20=very low/low/mid/NA & 1m:TRANGE=high/very high | up | 19.30 | 53.1 | +1.86 | +1.40 | +0.06 | 27.1 | none | 0.0 | 19.29 | +1.76 | +0.3 | +0.3 | +8.9 | > twins | 0 |
| 6 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:ADOSC sign=below 0 | down | 15.20 | 47.4 | -1.32 | +1.70 | -4.57 | 25.9 | pack | 11.5 | 15.01 | -0.72 | -0.8 | -0.9 | -24.5 | > twins | 0 |
| 7 | 1m:PERCENTB20/2=very low/low/high/very high & 1m:STOCHFK5=very low/low/mid/NA & 5m:C-FRAMA16 sign=below 0/NA | up | 20.00 | 53.9 | +2.64 | +1.24 | +1.24 | 24.9 | pack | 15.9 | 19.93 | +2.40 | +0.4 | +0.4 | +12.6 | hot, rep, > twins | 0 |
| 8 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:CCI14=low | up | 17.97 | 52.8 | +1.59 | -1.36 | -1.34 | 24.5 | none | 10.9 | 17.89 | +1.81 | +0.7 | +0.7 | +21.0 | > twins | 0 |
| 9 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:AD sign=below 0 | down | 15.62 | 47.7 | -1.01 | +1.54 | -4.16 | 24.0 | pack | 11.5 | 15.46 | -0.21 | -0.6 | -0.7 | -16.7 | > twins | 0 |
| 10 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:C-FRAMA16=low | up | 17.69 | 52.8 | +1.61 | -1.35 | -1.29 | 23.9 | pack | 7.1 | 17.56 | +1.86 | +0.6 | +0.5 | +17.9 | > twins | 0 |

**ETH, triples, 60 minutes, by lheat** (twins' max 21.02):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:SWAK_BP20 sign=above 0 | down | 22.49 | 51.4 | +2.73 | -0.69 | +2.90 | 65.3 | none | 13.1 | 22.25 | +2.20 | +0.7 | +0.7 | +22.2 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 21.44 | 51.5 | +2.79 | -0.27 | +2.72 | 58.4 | pack | 17.8 | 21.22 | +2.09 | +0.2 | +0.3 | +4.9 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:WAD sign=above 0 | down | 18.95 | 51.9 | +3.28 | -0.49 | +3.05 | 57.7 | pack | 16.0 | 18.62 | +2.85 | +0.7 | +0.9 | +22.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:AROONup25=mid/high/very high/NA & 1m:WILLR14=high/very high & 5m:PVT=very low/low/mid/high/NA | down | 22.05 | 51.1 | +2.47 | -0.22 | +2.55 | 56.1 | pack | 0.0 | 22.00 | +2.57 | +0.7 | +0.8 | +21.4 | > twins | 0 |
| 5 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:ADOSC sign=above 0 | down | 20.29 | 51.9 | +3.25 | -0.64 | +2.72 | 55.2 | pack | 11.5 | 19.79 | +2.64 | +1.0 | +0.9 | +30.6 | hot, rep, BHY, > twins | 2 |
| 6 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:ADOSC sign=above 0 | down | 19.22 | 52.0 | +3.33 | -0.37 | +2.79 | 53.5 | pack | 15.0 | 18.73 | +2.78 | +0.6 | +0.5 | +18.0 | hot, rep, BHY, > twins | 1 |
| 7 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:SI sign=above 0 | down | 19.46 | 51.5 | +2.79 | -0.40 | +2.58 | 50.2 | stored | 5.0 | 19.45 | +2.68 | +0.4 | +0.5 | +12.0 | > twins | 1 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:ERIbull13 sign=above 0 | down | 20.70 | 51.3 | +2.65 | -0.15 | +2.40 | 49.7 | pack | 17.7 | 20.13 | +1.75 | +0.3 | +0.3 | +8.8 | hot, rep, BHY, > twins | 2 |
| 9 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TEMA21 sign=above 0 | down | 15.94 | 52.9 | +4.27 | -1.13 | +3.05 | 48.6 | none | 12.6 | 15.76 | +3.62 | +0.4 | +0.6 | +13.0 | hot, rep, BHY, > twins | 0 |
| 10 | 15m:ADX14=low/mid/high/very high/NA & 1m:OBV sign=below 0 & 60m:Runs=none/3-4 down/5+ down/NA | up | 20.83 | 52.8 | +1.55 | +0.05 | +2.34 | 48.5 | none | 13.9 | 20.79 | +0.83 | +0.4 | +0.4 | +10.6 | hot, rep, BHY, > twins | 0 |

**ETH, triples, 60 minutes, by oheat** (twins' max 30.89):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:AROONup14=very high | down | 20.87 | 52.3 | +3.62 | -0.21 | +2.35 | 75.6 | pack | 14.8 | 20.82 | +3.29 | +0.5 | +0.5 | +13.5 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:AROONup25=high/very high & 1m:C-SUPERTREND10/3=high/very high & 1m:TRIX15=very low/low/mid/NA | down | 18.69 | 52.6 | +3.92 | -0.22 | +0.05 | 73.2 | pack | 0.0 | 18.65 | +3.91 | +1.3 | +1.3 | +38.3 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:AROONup25=very high | down | 18.42 | 52.6 | +3.96 | +0.06 | +1.94 | 72.9 | pack | 14.8 | 18.33 | +3.60 | +0.1 | +0.2 | +4.2 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:C-SUPERTREND10/3=high | down | 18.29 | 52.5 | +3.88 | -0.39 | +2.30 | 71.0 | pack | 14.8 | 18.26 | +4.20 | +0.9 | +1.0 | +27.7 | hot, rep, BHY, > twins | 1 |
| 5 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:C-TSF14 sign=above 0 | down | 19.10 | 52.2 | +3.57 | -0.90 | +2.03 | 68.1 | pack | 15.0 | 18.98 | +2.79 | +0.3 | +0.3 | +9.0 | hot, rep, BHY, > twins | 1 |
| 6 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TEMA21 sign=above 0 | down | 15.94 | 52.9 | +4.27 | -1.13 | +3.05 | 68.0 | none | 12.6 | 15.76 | +3.62 | +0.4 | +0.6 | +13.0 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:AROONup14=very high | down | 17.38 | 52.5 | +3.85 | -0.06 | +2.23 | 67.0 | pack | 15.0 | 17.31 | +3.37 | -0.1 | -0.1 | -1.8 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:ADOSC sign=above 0 | down | 20.29 | 51.9 | +3.25 | -0.64 | +2.72 | 66.0 | pack | 11.5 | 19.79 | +2.64 | +1.0 | +0.9 | +30.6 | hot, rep, BHY, > twins | 2 |
| 9 | 1m:COPPOCK sign=above 0 & 1m:PVI sign=above 0/NA & 1m:SI=very low/low/high | down | 20.78 | 51.8 | +3.15 | -0.86 | +1.23 | 65.5 | pack | 17.7 | 20.77 | +2.60 | +0.3 | +0.3 | +8.4 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-ZLEMA21 sign=above 0 | down | 16.57 | 52.6 | +3.90 | -0.81 | +2.79 | 64.6 | pack | 12.6 | 16.27 | +2.78 | -0.2 | -0.0 | -7.4 | hot, rep, BHY, > twins | 0 |

**ETH, triples, 60 minutes, unseen, by iheat** (twins' max 15.86):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:LRSLOPE14 sign=below 0 | up | 14.04 | 53.6 | +2.39 | +2.24 | +1.21 | 31.5 | none | 15.4 | 13.94 | +1.21 | -0.6 | -0.6 | -19.2 | hot, rep, > twins | 0 |
| 2 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:QSTICK10 sign=below 0 | up | 17.34 | 53.1 | +1.90 | +1.78 | +0.68 | 31.0 | none | 15.4 | 17.26 | +1.19 | +0.2 | +0.3 | +5.8 | hot, rep, > twins | 0 |
| 3 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:EMV14 sign=below 0 | up | 17.20 | 52.5 | +1.32 | +1.78 | +0.40 | 30.6 | none | 13.1 | 17.09 | +0.69 | +1.3 | +1.3 | +38.7 | hot, rep, > twins | 0 |
| 4 | 1m:SI=very low/low & 1m:STDDEV20=very low/low/mid/NA & 1m:TRANGE=high/very high | up | 19.30 | 53.1 | +1.86 | +1.40 | +0.06 | 27.1 | none | 0.0 | 19.29 | +1.76 | +0.3 | +0.3 | +8.9 | > twins | 0 |
| 5 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:CCI14=low | up | 17.97 | 52.8 | +1.59 | -1.36 | -1.34 | 24.5 | none | 10.9 | 17.89 | +1.81 | +0.7 | +0.7 | +21.0 | > twins | 0 |
| 6 | 1m:C-TEMA21 sign=below 0 & 1m:RVOL20=high & 1m:DX14=high | up | 6.68 | 56.2 | +5.00 | +3.38 | +3.98 | 22.6 | none | 6.5 | 6.67 | +4.34 | +2.2 | +2.1 | +67.0 | hot, rep, > twins | 0 |
| 7 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:AD sign=below 0 | up | 8.97 | 53.1 | +1.91 | +2.43 | +0.74 | 21.8 | none | 8.6 | 8.97 | +1.93 | +1.8 | +1.9 | +54.8 | > twins | 0 |
| 8 | 15m:C-HT_TRENDLINE sign=below 0 & POS:HourQ=h45-59 & 1m:CVI10=high | up | 2.66 | 60.6 | +9.38 | +8.13 | +8.04 | 21.6 | none | 10.4 | 2.66 | +8.57 | +4.7 | +4.3 | +141.0 | > twins | 0 |
| 9 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-LINEARREG14=high | down | 7.27 | 55.1 | +6.49 | -2.91 | +4.49 | 21.2 | none | 12.6 | 7.26 | +6.19 | +2.4 | +2.3 | +71.3 | > twins | 0 |
| 10 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:LRSLOPE14 sign=above 0 | down | 21.72 | 48.7 | +0.01 | +0.96 | -1.39 | 20.9 | none | 17.1 | 21.64 | -0.02 | -0.7 | -0.7 | -20.2 | hot, rep, > twins | 0 |

**ETH, triples, 60 minutes, unseen, by lheat** (twins' max 21.02):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:SWAK_BP20 sign=above 0 | down | 22.49 | 51.4 | +2.73 | -0.69 | +2.90 | 65.3 | none | 13.1 | 22.25 | +2.20 | +0.7 | +0.7 | +22.2 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:EMV14 sign=above 0 | down | 23.03 | 51.2 | +2.57 | -0.27 | +2.49 | 57.3 | none | 14.8 | 22.83 | +1.52 | +0.4 | +0.5 | +11.8 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:QSTICK10 sign=above 0 | down | 18.60 | 51.9 | +3.29 | -0.47 | +3.02 | 56.1 | none | 17.7 | 18.28 | +2.95 | +0.4 | +0.6 | +12.5 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TEMA21 sign=above 0 | down | 15.94 | 52.9 | +4.27 | -1.13 | +3.05 | 48.6 | none | 12.6 | 15.76 | +3.62 | +0.4 | +0.6 | +13.0 | hot, rep, BHY, > twins | 0 |
| 5 | 15m:ADX14=low/mid/high/very high/NA & 1m:OBV sign=below 0 & 60m:Runs=none/3-4 down/5+ down/NA | up | 20.83 | 52.8 | +1.55 | +0.05 | +2.34 | 48.5 | none | 13.9 | 20.79 | +0.83 | +0.4 | +0.4 | +10.6 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:KVO>sig=above | down | 18.84 | 51.5 | +2.80 | -0.39 | +2.53 | 47.7 | none | 5.0 | 18.82 | +2.73 | +0.2 | +0.1 | +4.5 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 60m:ERIbull13 sign=above 0 | down | 14.49 | 52.1 | +3.44 | -0.30 | +3.19 | 46.2 | none | 12.6 | 13.83 | +2.75 | -0.0 | +0.1 | -0.7 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:STOCHRSI14=very high | down | 15.11 | 52.7 | +4.07 | -1.15 | +3.05 | 46.1 | none | 5.0 | 15.10 | +4.07 | +1.1 | +1.0 | +34.4 | > twins | 0 |
| 9 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-MIDPRICE14 sign=above 0 | down | 18.66 | 51.6 | +2.95 | -0.17 | +2.45 | 45.8 | none | 16.5 | 17.88 | +1.68 | -0.3 | -0.2 | -10.0 | hot, rep, > twins | 0 |
| 10 | 1m:PVI=mid/high/very high/NA & 60m:PVT=very low/low/mid/high/NA & 60m:SQZMOM sign=above 0/NA | down | 12.06 | 50.6 | +1.93 | -0.02 | +3.88 | 44.4 | none | 5.8 | 0.71 | -2.78 | -5.6 | -4.1 | -166.0 | hot, rep, BHY, > twins | 0 |

**ETH, triples, 60 minutes, unseen, by oheat** (twins' max 30.89):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:STOCHRSI14=very high | down | 19.85 | 52.2 | +3.48 | -0.76 | +2.32 | 69.1 | none | 13.1 | 19.80 | +3.14 | +1.1 | +1.2 | +33.1 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TEMA21 sign=above 0 | down | 15.94 | 52.9 | +4.27 | -1.13 | +3.05 | 68.0 | none | 12.6 | 15.76 | +3.62 | +0.4 | +0.6 | +13.0 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:CCI20=high | down | 17.76 | 52.4 | +3.71 | -0.14 | +2.03 | 65.9 | none | 14.8 | 17.67 | +3.83 | +1.4 | +1.5 | +40.8 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:C-EMA50 sign=above 0 | down | 21.34 | 51.7 | +3.08 | -0.35 | +2.25 | 65.7 | none | 19.7 | 21.07 | +2.46 | +0.5 | +0.7 | +15.4 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:FISHER>trig=above | down | 16.99 | 52.3 | +3.67 | -0.59 | +2.55 | 62.4 | none | 12.6 | 16.63 | +3.19 | -0.1 | -0.0 | -3.2 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:STOCHRSI14=very high | down | 15.11 | 52.7 | +4.07 | -1.15 | +3.05 | 61.5 | none | 5.0 | 15.10 | +4.07 | +1.1 | +1.0 | +34.4 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:HAbody sign=above 0 | down | 18.40 | 51.9 | +3.25 | -0.30 | +2.39 | 59.8 | none | 12.6 | 18.08 | +2.44 | -0.0 | +0.2 | -0.2 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-TEMA21 sign=above 0 & 1m:RVOL20=high & 1m:C-SAR sign=above 0 | down | 18.28 | 51.8 | +3.17 | -0.49 | +2.18 | 58.0 | none | 14.5 | 18.27 | +3.17 | +0.3 | +0.3 | +8.7 | hot, rep, BHY, > twins | 0 |
| 9 | 15m:C-AVGPRICE sign=above 0 & 1m:WT1>WT2=above/NA & 5m:C-KAMA30 sign=above 0 | down | 17.02 | 51.9 | +3.19 | -0.23 | +1.68 | 54.3 | none | 22.2 | 16.80 | +2.54 | -0.6 | -0.5 | -17.6 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:C-HT_TRENDLINE sign=above 0 & 1m:SI=very low/low/high/NA & X.SOL:R1z=mid/high/very high/NA | down | 22.22 | 51.1 | +2.42 | -0.56 | +0.83 | 53.7 | none | 18.1 | 22.22 | +2.23 | +0.2 | +0.3 | +5.6 | hot, rep, BHY, > twins | 0 |

**ETH, pairs, 240 minutes, by iheat** (twins' max 19.61):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DX14=high & 1m:C-SAR=high | down | 4.03 | 53.8 | +5.04 | -4.26 | +4.60 | 17.2 | none | 3.2 | 4.03 | +4.27 | -0.5 | -0.7 | -15.5 | none | 0 |
| 2 | 1m:C-HMA20=high & 5m:Runs=3-4 up | down | 3.12 | 54.5 | +5.65 | -5.35 | +5.56 | 16.7 | none | 3.5 | 3.12 | +5.50 | +6.5 | +6.6 | +194.0 | hot, rep | 0 |
| 3 | 1m:DX14=low & 1m:WILLR14=low | down | 3.39 | 53.3 | +4.53 | -4.76 | +4.18 | 16.2 | pack | 3.7 | 3.39 | +3.54 | +5.0 | +5.1 | +147.8 | none | 0 |
| 4 | 1m:DIdiff14 sign=above 0 & 1m:C-SAR=low | down | 3.83 | 54.0 | +5.16 | -4.21 | +4.58 | 16.1 | none | 7.6 | 3.83 | +3.45 | +1.0 | +0.9 | +28.7 | none | 0 |
| 5 | 1m:RVOL20=very high & 1m:LRSLOPE14=high | down | 2.78 | 55.6 | +6.76 | -5.76 | +6.46 | 16.0 | none | 5.5 | 2.78 | +6.31 | +6.0 | +5.9 | +180.7 | none | 0 |
| 6 | 1m:ERIbull13=high & 5m:KDJ K>D=below | down | 4.99 | 46.7 | -2.05 | +3.16 | -3.81 | 15.7 | pack | 8.1 | 4.98 | -1.59 | -8.0 | -8.0 | -239.3 | none | 0 |
| 7 | 1m:DX14=high & 5m:C-AVGPRICE=low | up | 3.68 | 55.4 | +4.21 | +4.28 | +4.79 | 15.7 | none | 1.9 | 3.68 | +2.91 | -3.6 | -3.4 | -105.5 | none | 0 |
| 8 | 1m:C-VIDYA12 sign=above 0 & 5m:BarBody=low | down | 3.64 | 53.9 | +5.08 | -4.32 | +4.68 | 15.7 | none | 7.6 | 3.64 | +3.39 | +2.4 | +2.4 | +71.3 | none | 0 |
| 9 | 1m:CCI20 sign=above 0 & 5m:CDL:BELTHOLD=bear | down | 4.20 | 54.0 | +5.20 | -3.72 | +4.81 | 15.6 | pack | 8.5 | 4.20 | +4.56 | +5.8 | +5.9 | +173.5 | none | 0 |
| 10 | 1m:TRANGE=very high & 1m:LRSLOPE14=high | down | 2.08 | 57.2 | +8.33 | -7.49 | +7.99 | 15.6 | none | 5.5 | 2.08 | +7.20 | +7.8 | +7.2 | +231.1 | none | 0 |

**ETH, pairs, 240 minutes, by lheat** (twins' max 19.81):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-ALMA9=very high & 5m:STOCH14 K>D=above | down | 4.85 | 54.0 | +5.17 | -1.88 | +5.14 | 24.9 | pack | 4.3 | 4.85 | +4.12 | +2.9 | +2.8 | +86.4 | > twins | 0 |
| 2 | 1m:C-ALMA9=very high & 5m:FISHER>trig=above | down | 4.68 | 54.0 | +5.24 | -1.90 | +5.15 | 24.1 | pack | 4.9 | 4.68 | +4.45 | +2.2 | +2.1 | +66.3 | > twins | 1 |
| 3 | 1m:SWAK_HP20=very high & 5m:STOCH14 K>D=above | down | 4.78 | 53.6 | +4.83 | -1.65 | +4.80 | 23.0 | pack | 5.0 | 4.78 | +4.04 | +1.4 | +1.1 | +42.9 | > twins | 0 |
| 4 | 1m:CCI50=very high & 5m:STOCH14 K>D=above | down | 4.29 | 54.1 | +5.32 | -0.80 | +5.35 | 22.9 | pack | 7.1 | 4.28 | +4.14 | +1.9 | +1.1 | +57.0 | > twins | 5 |
| 5 | 15m:KVO>sig=above & OI:PxQuad60=long liquidation | up | 4.06 | 56.7 | +5.55 | +2.35 | +5.57 | 22.7 | none | 3.5 | 4.01 | +4.19 | +6.6 | +6.4 | +195.1 | > twins | 0 |
| 6 | 1m:CCI50=very high & 15m:SI sign=above 0 | down | 4.03 | 54.6 | +5.81 | -1.17 | +5.55 | 22.4 | pack | 7.1 | 4.03 | +4.66 | +2.8 | +2.1 | +81.1 | > twins | 2 |
| 7 | 1m:C-ALMA9=very high & 15m:SI sign=above 0 | down | 4.62 | 53.9 | +5.08 | -1.55 | +4.76 | 22.0 | pack | 7.1 | 4.62 | +4.13 | +0.9 | +1.0 | +27.7 | > twins | 0 |
| 8 | 1m:RSI7=very high & 1m:EFI13 sign=above 0 | down | 4.73 | 52.7 | +3.95 | -0.34 | +4.58 | 21.7 | pack | 5.3 | 4.73 | +3.17 | -1.6 | -2.0 | -48.8 | hot, rep, > twins | 2 |
| 9 | 1m:SWAK_HP20=very high & 5m:FISHER>trig=above | down | 4.65 | 53.5 | +4.73 | -1.50 | +4.64 | 21.6 | pack | 5.0 | 4.65 | +4.27 | +1.2 | +0.9 | +37.0 | > twins | 0 |
| 10 | 1m:C-EMA9=very high & 5m:FISHER>trig=above | down | 4.54 | 53.6 | +4.75 | -1.26 | +4.67 | 21.2 | pack | 5.2 | 4.54 | +4.00 | -0.7 | -1.1 | -20.9 | > twins | 1 |

**ETH, pairs, 240 minutes, by oheat** (twins' max 19.64):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CMF20=low & 60m:CTI20 sign=below 0 | up | 3.11 | 59.7 | +8.52 | +2.86 | +4.97 | 26.5 | pack | 3.4 | 3.11 | +7.54 | +13.2 | +13.1 | +403.3 | hot, rep, BHY, > twins | 3 |
| 2 | 1m:C-ALMA9=very high & 60m:C-SMA20 sign=above 0 | down | 3.33 | 56.4 | +7.68 | -1.68 | +4.58 | 25.6 | pack | 5.7 | 3.33 | +7.12 | +4.3 | +4.4 | +130.6 | hot, rep, BHY, > twins | 6 |
| 3 | 1m:C-ALMA9=very high & 5m:STOCH14 K>D=above | down | 4.85 | 54.0 | +5.17 | -1.88 | +5.14 | 25.1 | pack | 4.3 | 4.85 | +4.12 | +2.9 | +2.8 | +86.4 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:SWAK_2PHP20=very high & 60m:C-CKSPmid sign=above 0 | down | 3.72 | 55.5 | +6.69 | -1.90 | +3.53 | 24.9 | pack | 5.7 | 3.72 | +6.80 | +5.0 | +5.3 | +151.3 | hot, rep, BHY, > twins | 4 |
| 5 | 1m:SWAK_2PHP20=very high & 5m:C-EMA200 sign=above 0 | down | 3.74 | 55.4 | +6.59 | -2.40 | +4.13 | 24.6 | pack | 7.5 | 3.74 | +6.72 | +3.2 | +3.5 | +97.2 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-ALMA9=very high & 5m:FISHER>trig=above | down | 4.68 | 54.0 | +5.24 | -1.90 | +5.15 | 24.5 | pack | 4.9 | 4.68 | +4.45 | +2.2 | +2.1 | +66.3 | hot, rep, BHY, > twins | 1 |
| 7 | 1m:C-TEMA21=high & 1m:SWAK_HP20=very high | down | 3.92 | 55.0 | +6.25 | -2.05 | +4.89 | 24.5 | pack | 5.0 | 3.92 | +5.59 | +3.7 | +3.8 | +109.7 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:CMF20=low & 60m:CCI20 sign=below 0 | up | 3.28 | 58.5 | +7.37 | +1.75 | +3.93 | 24.2 | pack | 5.1 | 3.28 | +7.16 | +9.4 | +9.3 | +289.0 | hot, rep, BHY, > twins | 1 |
| 9 | 60m:C-CKSPmid sign=below 0 & X.SOL:TakerBuy=low | up | 3.45 | 58.1 | +6.99 | +1.46 | +3.42 | 24.1 | none | 4.9 | 3.45 | +7.02 | +9.3 | +9.3 | +275.0 | > twins | 4 |
| 10 | 1m:HT_DCPHASE=low & X.SOL:R15z=low | up | 4.81 | 56.1 | +4.98 | +1.91 | +3.48 | 24.0 | none | 3.0 | 4.81 | +3.14 | +2.0 | +2.0 | +61.1 | > twins | 0 |

**ETH, pairs, 240 minutes, unseen, by iheat** (twins' max 19.61):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DX14=high & 1m:C-SAR=high | down | 4.03 | 53.8 | +5.04 | -4.26 | +4.60 | 17.2 | none | 3.2 | 4.03 | +4.27 | -0.5 | -0.7 | -15.5 | none | 0 |
| 2 | 1m:C-HMA20=high & 5m:Runs=3-4 up | down | 3.12 | 54.5 | +5.65 | -5.35 | +5.56 | 16.7 | none | 3.5 | 3.12 | +5.50 | +6.5 | +6.6 | +194.0 | hot, rep | 0 |
| 3 | 1m:DIdiff14 sign=above 0 & 1m:C-SAR=low | down | 3.83 | 54.0 | +5.16 | -4.21 | +4.58 | 16.1 | none | 7.6 | 3.83 | +3.45 | +1.0 | +0.9 | +28.7 | none | 0 |
| 4 | 1m:RVOL20=very high & 1m:LRSLOPE14=high | down | 2.78 | 55.6 | +6.76 | -5.76 | +6.46 | 16.0 | none | 5.5 | 2.78 | +6.31 | +6.0 | +5.9 | +180.7 | none | 0 |
| 5 | 1m:DX14=high & 5m:C-AVGPRICE=low | up | 3.68 | 55.4 | +4.21 | +4.28 | +4.79 | 15.7 | none | 1.9 | 3.68 | +2.91 | -3.6 | -3.4 | -105.5 | none | 0 |
| 6 | 1m:C-VIDYA12 sign=above 0 & 5m:BarBody=low | down | 3.64 | 53.9 | +5.08 | -4.32 | +4.68 | 15.7 | none | 7.6 | 3.64 | +3.39 | +2.4 | +2.4 | +71.3 | none | 0 |
| 7 | 1m:TRANGE=very high & 1m:LRSLOPE14=high | down | 2.08 | 57.2 | +8.33 | -7.49 | +7.99 | 15.6 | none | 5.5 | 2.08 | +7.20 | +7.8 | +7.2 | +231.1 | none | 0 |
| 8 | 1m:DX14=high & 1m:MACDh5/35/5=low | up | 4.19 | 55.2 | +4.09 | +3.63 | +4.33 | 15.2 | none | 1.7 | 4.18 | +3.34 | -0.2 | -0.7 | -6.6 | hot, rep | 0 |
| 9 | 5m:AC=low & X.SOL:Gap5=high | up | 3.35 | 54.5 | +3.42 | +4.53 | +4.35 | 15.2 | none | 1.7 | 3.35 | +2.88 | +2.6 | +2.6 | +79.2 | none | 0 |
| 10 | 1m:FISHER10=high & 1m:RVOL20=very high | down | 2.62 | 55.8 | +7.01 | -5.78 | +6.47 | 15.1 | none | 4.3 | 2.62 | +6.32 | +5.5 | +5.5 | +166.5 | none | 0 |

**ETH, pairs, 240 minutes, unseen, by lheat** (twins' max 19.81):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:KVO>sig=above & OI:PxQuad60=long liquidation | up | 4.06 | 56.7 | +5.55 | +2.35 | +5.57 | 22.7 | none | 3.5 | 4.01 | +4.19 | +6.6 | +6.4 | +195.1 | > twins | 0 |
| 2 | 1m:C-SWAK_BUTTER20=very high & 5m:STOCH14 K>D=above | down | 4.62 | 53.6 | +4.75 | -1.61 | +4.73 | 21.8 | none | 5.0 | 4.62 | +3.44 | +0.0 | -0.3 | +0.3 | > twins | 1 |
| 3 | 60m:C-LINEARREG14 sign=above 0 & X.BTC:RSI14=very low | up | 2.62 | 59.0 | +7.87 | +4.18 | +7.84 | 20.5 | none | 6.2 | 2.61 | +5.40 | +12.3 | +11.6 | +363.7 | > twins | 1 |
| 4 | 1m:C-SWAK_BUTTER20=very high & 5m:FISHER>trig=above | down | 4.43 | 53.5 | +4.71 | -1.52 | +4.62 | 20.5 | none | 5.0 | 4.43 | +3.78 | +0.3 | -0.1 | +7.5 | > twins | 0 |
| 5 | 1m:SWAK_2PHP20=very high & 5m:STOCH14 K>D=above | down | 4.74 | 53.1 | +4.31 | -2.44 | +4.23 | 20.1 | none | 3.1 | 4.74 | +4.15 | +4.5 | +4.7 | +135.9 | > twins | 0 |
| 6 | 1m:C-T3_5=very high & 5m:STOCH14 K>D=above | down | 4.66 | 53.2 | +4.35 | -1.64 | +4.30 | 20.0 | none | 4.2 | 4.65 | +3.21 | +3.2 | +3.0 | +94.8 | > twins | 0 |
| 7 | 1m:WAD=high & 5m:KDJ_J=high | down | 4.04 | 54.4 | +5.64 | -3.49 | +4.95 | 20.0 | none | 5.9 | 4.04 | +4.05 | +4.7 | +4.3 | +145.3 | > twins | 0 |
| 8 | 1m:C-SWAK_BUTTER20=very high & 15m:C-AVGPRICE sign=above 0 | down | 4.23 | 53.5 | +4.73 | -1.47 | +4.57 | 19.4 | none | 7.0 | 4.23 | +3.48 | +0.3 | +0.1 | +10.3 | none | 0 |
| 9 | 1m:PDI14=very high & 60m:LRSLOPE14 sign=above 0 | down | 1.83 | 61.3 | +12.49 | -5.62 | +10.49 | 19.2 | none | 4.4 | 1.83 | +9.64 | +3.0 | +3.2 | +87.7 | none | 1 |
| 10 | 1m:DIdiff14=very high & 5m:STOCH5 K>D=above | down | 3.26 | 54.7 | +5.92 | -1.27 | +5.90 | 19.2 | none | 5.6 | 3.25 | +4.51 | -3.2 | -3.7 | -94.5 | none | 0 |

**ETH, pairs, 240 minutes, unseen, by oheat** (twins' max 18.32):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 60m:C-CKSPmid sign=below 0 & X.SOL:TakerBuy=low | up | 3.45 | 58.1 | +6.99 | +1.46 | +3.42 | 24.1 | none | 4.9 | 3.45 | +7.02 | +9.3 | +9.3 | +275.0 | > twins | 3 |
| 2 | 1m:HT_DCPHASE=low & X.SOL:R15z=low | up | 4.81 | 56.1 | +4.98 | +1.91 | +3.48 | 24.0 | none | 3.0 | 4.81 | +3.14 | +2.0 | +2.0 | +61.1 | > twins | 0 |
| 3 | 1m:BOP=very high & 60m:C-CKSPmid sign=below 0 | up | 3.20 | 58.6 | +7.47 | +3.64 | +3.82 | 23.9 | none | 4.9 | 3.20 | +7.16 | +7.7 | +7.3 | +230.7 | > twins | 3 |
| 4 | 1m:SWAK_2PHP20=very high & 60m:CTI20 sign=above 0 | down | 3.36 | 55.8 | +6.98 | -1.79 | +3.48 | 23.5 | none | 4.2 | 3.36 | +7.22 | +7.7 | +7.9 | +235.3 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:SWAK_2PHP20=very high & 15m:C-EMA50 sign=above 0 | down | 3.85 | 54.8 | +5.97 | -2.04 | +3.72 | 23.0 | none | 7.7 | 3.85 | +6.07 | +2.0 | +2.3 | +59.4 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:PDI14=very high & 60m:LRSLOPE14 sign=above 0 | down | 1.83 | 61.3 | +12.49 | -5.62 | +10.49 | 22.9 | none | 4.4 | 1.83 | +9.64 | +3.0 | +3.2 | +87.7 | hot, rep, > twins | 1 |
| 7 | 1m:WAD=high & 5m:KDJ_J=high | down | 4.04 | 54.4 | +5.64 | -3.49 | +4.95 | 22.8 | none | 5.9 | 4.04 | +4.05 | +4.7 | +4.3 | +145.3 | hot, rep, > twins | 0 |
| 8 | 1m:ADOSC=low & 60m:C-CKSPmid sign=below 0 | up | 3.43 | 57.8 | +6.61 | +0.88 | +3.10 | 22.7 | none | 4.9 | 3.42 | +6.00 | +6.1 | +6.2 | +184.0 | hot, rep, BHY, > twins | 3 |
| 9 | 15m:KVO>sig=above & OI:PxQuad60=long liquidation | up | 4.06 | 56.7 | +5.55 | +2.35 | +5.57 | 22.6 | none | 3.5 | 4.01 | +4.19 | +6.6 | +6.4 | +195.1 | > twins | 0 |
| 10 | 1m:CHOP14=low & 15m:C-EMA50 sign=below 0 | up | 3.96 | 56.8 | +5.69 | +2.77 | +3.47 | 22.5 | none | 7.6 | 3.96 | +4.89 | +2.6 | +2.4 | +77.6 | hot, rep, > twins | 1 |

**ETH, triples, 240 minutes, by iheat** (twins' max 11.35):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TSF14=very low | down | 3.36 | 53.7 | +4.89 | -4.80 | +4.64 | 16.1 | none | 5.6 | 3.35 | +3.28 | +2.8 | +2.8 | +86.4 | > twins | 0 |
| 2 | 1m:PVO12/26=high & 5m:C-TSF14 sign=above 0 & 1m:C-VWMA20 sign=below 0 | up | 4.20 | 53.8 | +2.69 | +3.31 | +2.41 | 13.9 | none | 7.8 | 4.20 | +2.56 | +3.3 | +3.5 | +98.5 | > twins | 2 |
| 3 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & OI:Chg15=low | down | 3.10 | 54.1 | +5.33 | -4.46 | +4.96 | 13.8 | none | 9.0 | 3.09 | +3.65 | +8.8 | +7.9 | +263.6 | > twins | 0 |
| 4 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & X.XRP:R15z=low | down | 1.77 | 54.6 | +5.78 | -7.66 | +5.49 | 13.6 | none | 5.6 | 1.77 | +4.63 | +9.0 | +8.6 | +276.3 | > twins | 0 |
| 5 | 1m:PVO12/26=high & 5m:C-TSF14 sign=above 0 & 1m:C-MIDPOINT14 sign=below 0 | up | 4.08 | 53.9 | +2.73 | +3.30 | +2.43 | 13.5 | none | 8.5 | 4.08 | +2.21 | +2.6 | +2.5 | +77.2 | > twins | 1 |
| 6 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 5m:KST>sig=below | down | 3.96 | 47.7 | -1.16 | +3.40 | -3.78 | 13.5 | none | 9.1 | 3.91 | -0.84 | +0.1 | +0.2 | +3.4 | > twins | 0 |
| 7 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:BBW20=low | up | 3.46 | 55.9 | +4.75 | +3.76 | +4.08 | 13.0 | none | 5.6 | 3.43 | +1.93 | +2.1 | +2.1 | +62.2 | > twins | 0 |
| 8 | 1m:MACDh12/26/9 sign=below 0 & 1m:AVGDEV14=high & 1m:KDJ_J=low | up | 3.29 | 48.5 | -2.69 | -3.93 | -4.51 | 12.9 | none | 5.1 | 3.29 | -1.82 | -6.1 | -6.5 | -188.8 | > twins | 1 |
| 9 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & OI:Chg15=low | down | 2.70 | 54.8 | +6.02 | -4.71 | +5.26 | 12.7 | pack | 10.1 | 2.69 | +4.86 | +6.4 | +5.9 | +191.1 | > twins | 0 |
| 10 | 1m:PVO12/26=high & 5m:C-TSF14 sign=above 0 & 1m:CCI14 sign=below 0 | up | 3.81 | 54.0 | +2.86 | +3.33 | +2.50 | 12.7 | none | 8.1 | 3.81 | +2.64 | +1.2 | +1.6 | +36.8 | hot, rep, > twins | 1 |

**ETH, triples, 240 minutes, by lheat** (twins' max 12.98):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PVI=mid/high/very high/NA & 60m:PVT=very low/low/mid/high/NA & 60m:SQZMOM sign=above 0/NA | down | 3.56 | 52.5 | +3.71 | +0.00 | +7.43 | 25.0 | none | 4.4 | 0.71 | -3.85 | -13.7 | -12.2 | -407.7 | hot, rep, > twins | 0 |
| 2 | 15m:C-KAMA30 sign=below 0 & 60m:SMI=very low/low/mid & NY30m=00:00/00:30/01:00/01:30/03:00/03:30/04:30/05:30/06:00/06:30/07:00/07:30/08:00/09:30/10:00/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/19:30/20:00/20:30/21:00/21:30/22:00/22:30/23:00/23:30/NA | up | 4.26 | 54.6 | +3.46 | +1.09 | +5.17 | 22.0 | none | 10.7 | 3.35 | +0.65 | -3.4 | -3.0 | -101.9 | hot, rep, > twins | 0 |
| 3 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 5m:KST>sig=above | down | 5.39 | 51.4 | +2.62 | -0.76 | +3.74 | 20.1 | none | 9.1 | 5.22 | +1.24 | +0.2 | +0.0 | +4.5 | > twins | 5 |
| 4 | 5m:CVI10 sign=above 0 & 15m:FISHER>trig=above & 15m:C-HMA20 sign=above 0 | down | 5.53 | 51.4 | +2.60 | -0.61 | +3.60 | 19.9 | none | 9.3 | 5.38 | +1.48 | +0.5 | +0.3 | +14.8 | > twins | 2 |
| 5 | 15m:C-KAMA30 sign=below 0/NA & OI:Chg60=very low/low/mid/high/very high & UTC1h=00/03/04/17/18/19/20/21 | up | 2.73 | 57.5 | +6.36 | +2.28 | +6.91 | 18.9 | pack | 10.7 | 1.97 | +5.36 | +2.7 | +2.5 | +80.2 | hot, rep, > twins | 0 |
| 6 | 15m:C-KAMA30 sign=below 0 & 60m:SMI=very low/low/mid & UTC4h=00-04/16-20/20-24 | up | 2.18 | 58.5 | +7.38 | +2.96 | +8.81 | 18.5 | pack | 10.7 | 1.70 | +5.93 | -4.4 | -4.2 | -130.9 | > twins | 0 |
| 7 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TEMA21=high | down | 3.82 | 53.8 | +4.99 | -4.14 | +4.77 | 18.2 | pack | 5.6 | 3.82 | +3.49 | +1.4 | +1.4 | +40.8 | > twins | 0 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:ACCBANDS20pos=very high | down | 3.85 | 54.4 | +5.54 | -0.74 | +4.71 | 18.2 | pack | 10.1 | 3.85 | +4.52 | -1.8 | -2.2 | -55.3 | > twins | 2 |
| 9 | 5m:CVI10 sign=above 0 & 15m:FISHER>trig=above & 5m:WAD sign=above 0 | down | 5.30 | 51.6 | +2.81 | -0.69 | +3.39 | 18.0 | pack | 9.3 | 5.17 | +1.73 | +0.4 | +0.2 | +11.9 | hot, rep, > twins | 0 |
| 10 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:C-ALMA9=very high | down | 4.60 | 53.6 | +4.85 | -1.10 | +3.89 | 17.9 | pack | 10.1 | 4.60 | +4.31 | +1.5 | +1.4 | +44.7 | > twins | 0 |

**ETH, triples, 240 minutes, by oheat** (twins' max 13.67):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:C-ALMA9=very high | down | 4.60 | 53.6 | +4.85 | -1.10 | +3.89 | 22.3 | pack | 10.1 | 4.60 | +4.31 | +1.5 | +1.4 | +44.7 | hot, rep, > twins | 0 |
| 2 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:SWAK_HP20=very high | down | 4.65 | 53.4 | +4.64 | -1.13 | +3.71 | 21.6 | pack | 10.1 | 4.65 | +4.36 | +1.8 | +1.5 | +54.9 | hot, rep, > twins | 1 |
| 3 | 1m:PVO12/26 sign=above 0 & 5m:C-HMA20 sign=above 0 & 1m:ACCBANDS20pos=very high | down | 3.85 | 54.4 | +5.54 | -0.74 | +4.71 | 21.4 | pack | 10.1 | 3.85 | +4.52 | -1.8 | -2.2 | -55.3 | hot, rep, > twins | 2 |
| 4 | 1m:ER10=high & 1m:KVO>sig=below & 60m:CTI20 sign=below 0 | up | 3.18 | 57.7 | +6.51 | +1.07 | +2.67 | 20.7 | pack | 4.8 | 3.18 | +6.08 | +4.9 | +4.7 | +145.7 | hot, rep, > twins | 3 |
| 5 | 1m:CVI10=high & 5m:C-LINEARREG14 sign=above 0 & 60m:C-CKSPmid sign=above 0 | down | 3.48 | 54.7 | +5.91 | -1.06 | +2.79 | 20.6 | pack | 7.6 | 3.48 | +5.07 | +1.6 | +1.7 | +49.2 | hot, rep, > twins | 4 |
| 6 | 5m:C-DEMA21 sign=above 0 & 5m:RVOL20=high & 60m:C-CKSPmid sign=above 0 | down | 2.78 | 56.0 | +7.21 | -1.61 | +4.17 | 20.1 | pack | 7.7 | 2.77 | +7.42 | +4.5 | +4.1 | +136.2 | hot, rep, > twins | 4 |
| 7 | 1m:DOSC sign=below 0 & 1m:ER10=high & X.SOL:Gap15=low | up | 3.91 | 56.2 | +5.08 | +2.09 | +3.69 | 19.8 | none | 5.2 | 3.91 | +4.31 | +6.9 | +6.4 | +208.4 | > twins | 1 |
| 8 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 60m:C-CKSPmid sign=above 0 | down | 3.61 | 54.3 | +5.49 | -0.68 | +2.90 | 19.8 | pack | 9.1 | 3.51 | +4.95 | +3.0 | +3.0 | +91.0 | hot, rep, > twins | 2 |
| 9 | 1m:CVI10=high & 1m:KST>sig=above & 1m:C-WMA20=very high | down | 2.88 | 55.7 | +6.86 | -1.84 | +4.36 | 19.7 | pack | 8.0 | 2.88 | +6.33 | -0.0 | -1.1 | -1.3 | hot, rep, > twins | 1 |
| 10 | 1m:CVI10=high & 1m:KST>sig=above & 1m:C-SWAK_BUTTER20=very high | down | 3.04 | 55.3 | +6.49 | -2.01 | +4.69 | 19.7 | none | 8.0 | 3.04 | +5.59 | +0.8 | +0.1 | +25.2 | hot, rep, > twins | 2 |

**ETH, triples, 240 minutes, unseen, by iheat** (twins' max 10.06):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-TSF14=very low | down | 3.36 | 53.7 | +4.89 | -4.80 | +4.64 | 16.1 | none | 5.6 | 3.35 | +3.28 | +2.8 | +2.8 | +86.4 | > twins | 0 |
| 2 | 1m:PVO12/26=high & 5m:C-TSF14 sign=above 0 & 1m:C-VWMA20 sign=below 0 | up | 4.20 | 53.8 | +2.69 | +3.31 | +2.41 | 13.9 | none | 7.8 | 4.20 | +2.56 | +3.3 | +3.5 | +98.5 | > twins | 2 |
| 3 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & OI:Chg15=low | down | 3.10 | 54.1 | +5.33 | -4.46 | +4.96 | 13.8 | none | 9.0 | 3.09 | +3.65 | +8.8 | +7.9 | +263.6 | > twins | 0 |
| 4 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & X.XRP:R15z=low | down | 1.77 | 54.6 | +5.78 | -7.66 | +5.49 | 13.6 | none | 5.6 | 1.77 | +4.63 | +9.0 | +8.6 | +276.3 | > twins | 0 |
| 5 | 1m:PVO12/26=high & 5m:C-TSF14 sign=above 0 & 1m:C-MIDPOINT14 sign=below 0 | up | 4.08 | 53.9 | +2.73 | +3.30 | +2.43 | 13.5 | none | 8.5 | 4.08 | +2.21 | +2.6 | +2.5 | +77.2 | > twins | 1 |
| 6 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 5m:KST>sig=below | down | 3.96 | 47.7 | -1.16 | +3.40 | -3.78 | 13.5 | none | 9.1 | 3.91 | -0.84 | +0.1 | +0.2 | +3.4 | > twins | 0 |
| 7 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:BBW20=low | up | 3.46 | 55.9 | +4.75 | +3.76 | +4.08 | 13.0 | none | 5.6 | 3.43 | +1.93 | +2.1 | +2.1 | +62.2 | > twins | 0 |
| 8 | 1m:MACDh12/26/9 sign=below 0 & 1m:AVGDEV14=high & 1m:KDJ_J=low | up | 3.29 | 48.5 | -2.69 | -3.93 | -4.51 | 12.9 | none | 5.1 | 3.29 | -1.82 | -6.1 | -6.5 | -188.8 | > twins | 1 |
| 9 | 1m:PVO12/26=high & 5m:C-TSF14 sign=above 0 & 1m:CCI14 sign=below 0 | up | 3.81 | 54.0 | +2.86 | +3.33 | +2.50 | 12.7 | none | 8.1 | 3.81 | +2.64 | +1.2 | +1.6 | +36.8 | hot, rep, > twins | 1 |
| 10 | 1m:ER10=high & 1m:KVO>sig=below & 1m:HT_DCPERIOD=low | up | 2.00 | 57.2 | +6.07 | +6.11 | +4.97 | 12.2 | none | 4.8 | 2.00 | +3.94 | -4.2 | -4.7 | -123.6 | > twins | 1 |

**ETH, triples, 240 minutes, unseen, by lheat** (twins' max 12.98):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PVI=mid/high/very high/NA & 60m:PVT=very low/low/mid/high/NA & 60m:SQZMOM sign=above 0/NA | down | 3.56 | 52.5 | +3.71 | +0.00 | +7.43 | 25.0 | none | 4.4 | 0.71 | -3.85 | -13.7 | -12.2 | -407.7 | hot, rep, > twins | 0 |
| 2 | 15m:C-KAMA30 sign=below 0 & 60m:SMI=very low/low/mid & NY30m=00:00/00:30/01:00/01:30/03:00/03:30/04:30/05:30/06:00/06:30/07:00/07:30/08:00/09:30/10:00/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/19:30/20:00/20:30/21:00/21:30/22:00/22:30/23:00/23:30/NA | up | 4.26 | 54.6 | +3.46 | +1.09 | +5.17 | 22.0 | none | 10.7 | 3.35 | +0.65 | -3.4 | -3.0 | -101.9 | hot, rep, > twins | 0 |
| 3 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 5m:KST>sig=above | down | 5.39 | 51.4 | +2.62 | -0.76 | +3.74 | 20.1 | none | 9.1 | 5.22 | +1.24 | +0.2 | +0.0 | +4.5 | > twins | 4 |
| 4 | 5m:CVI10 sign=above 0 & 15m:FISHER>trig=above & 15m:C-HMA20 sign=above 0 | down | 5.53 | 51.4 | +2.60 | -0.61 | +3.60 | 19.9 | none | 9.3 | 5.38 | +1.48 | +0.5 | +0.3 | +14.8 | > twins | 1 |
| 5 | 1m:DX14=high & 1m:KVO sign=below 0 & 15m:MARKETFI sign=above 0 | up | 3.75 | 56.3 | +5.19 | +1.97 | +4.63 | 17.4 | none | 6.1 | 3.75 | +3.74 | +2.6 | +2.3 | +78.1 | > twins | 0 |
| 6 | 1m:CVI10=high & 5m:C-LINEARREG14 sign=above 0 & 5m:STOCH5 K>D=above | down | 5.21 | 52.1 | +3.29 | -1.15 | +3.29 | 17.1 | none | 7.6 | 5.21 | +2.44 | -1.6 | -1.6 | -46.3 | > twins | 1 |
| 7 | 1m:DX14=high & 1m:KVO sign=below 0 & 5m:SWAK_2PHP20 sign=below 0 | up | 5.21 | 54.3 | +3.13 | +0.61 | +3.16 | 16.5 | none | 6.1 | 5.20 | +2.26 | -2.5 | -2.7 | -74.1 | > twins | 0 |
| 8 | 1m:DX14=high & 1m:KVO sign=below 0 & 5m:DOSC sign=below 0 | up | 5.06 | 54.4 | +3.26 | +0.71 | +3.19 | 16.1 | none | 6.1 | 5.04 | +2.53 | -1.6 | -1.7 | -49.0 | > twins | 0 |
| 9 | 1m:CVI10=high & 1m:KST>sig=above & 5m:KDJ K>D=above | down | 5.06 | 52.0 | +3.18 | -0.80 | +3.17 | 16.0 | none | 8.0 | 5.05 | +2.57 | -1.1 | -1.3 | -33.8 | > twins | 1 |
| 10 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 15m:CMF20 sign=above 0 | down | 4.40 | 52.1 | +3.31 | -0.98 | +3.59 | 15.8 | none | 9.1 | 4.29 | +1.22 | +0.5 | +0.5 | +13.5 | hot, rep, > twins | 0 |

**ETH, triples, 240 minutes, unseen, by oheat** (twins' max 13.13):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=below 0 & 1m:ER10=high & X.SOL:Gap15=low | up | 3.91 | 56.2 | +5.08 | +2.09 | +3.69 | 19.8 | none | 5.2 | 3.91 | +4.31 | +6.9 | +6.4 | +208.4 | > twins | 1 |
| 2 | 1m:CVI10=high & 1m:KST>sig=above & 1m:C-SWAK_BUTTER20=very high | down | 3.04 | 55.3 | +6.49 | -2.01 | +4.69 | 19.7 | none | 8.0 | 3.04 | +5.59 | +0.8 | +0.1 | +25.2 | hot, rep, > twins | 1 |
| 3 | 1m:DX14=high & 1m:KVO sign=below 0 & 15m:MARKETFI sign=above 0 | up | 3.75 | 56.3 | +5.19 | +1.97 | +4.63 | 19.5 | none | 6.1 | 3.75 | +3.74 | +2.6 | +2.3 | +78.1 | hot, rep, > twins | 0 |
| 4 | 1m:DX14=high & 1m:KVO sign=above 0 & 1m:C-SAR=high | down | 3.92 | 53.8 | +4.97 | -1.94 | +3.34 | 19.5 | none | 7.9 | 3.91 | +4.44 | -0.8 | -1.0 | -23.4 | hot, rep, > twins | 0 |
| 5 | 1m:DX14=high & 1m:KVO sign=below 0 & X.BTC:R15z=low | up | 3.77 | 56.3 | +5.13 | +0.77 | +2.84 | 19.4 | none | 6.4 | 3.75 | +4.83 | +0.8 | +0.5 | +23.1 | hot, rep, > twins | 0 |
| 6 | 1m:C-TEMA21 sign=below 0 & 1m:RVOL20=high & 60m:CMF20 sign=below 0 | up | 3.45 | 56.8 | +5.59 | +1.52 | +2.78 | 19.3 | none | 3.5 | 3.45 | +5.63 | +8.1 | +7.7 | +236.2 | > twins | 0 |
| 7 | 5m:MACDh12/26/9 sign=above 0 & 5m:CVI10 sign=above 0 & 1m:AD=high | down | 4.37 | 53.2 | +4.36 | -0.75 | +2.79 | 19.0 | none | 9.1 | 4.36 | +3.87 | -2.3 | -2.2 | -67.5 | hot, rep, > twins | 0 |
| 8 | 1m:DOSC sign=below 0 & 1m:ER10=high & FLOW:Stretch15=low | up | 4.70 | 55.2 | +4.03 | +0.89 | +1.84 | 18.9 | none | 6.0 | 4.70 | +3.76 | +2.3 | +2.2 | +69.1 | > twins | 0 |
| 9 | 5m:CVI10 sign=above 0 & 15m:FISHER>trig=above & 60m:C-VIDYA12 sign=above 0 | down | 3.38 | 54.3 | +5.52 | -1.01 | +3.26 | 18.7 | none | 9.3 | 3.31 | +3.90 | +1.0 | +1.0 | +30.7 | hot, rep, > twins | 0 |
| 10 | 5m:CVI10 sign=above 0 & 15m:FISHER>trig=above & 60m:SQZMOM sign=above 0 | down | 3.25 | 54.5 | +5.73 | -0.55 | +2.98 | 18.6 | none | 9.3 | 3.18 | +4.50 | +2.6 | +2.4 | +76.7 | hot, rep, > twins | 0 |

**SOL, pairs, 15 minutes, by iheat** (twins' max 42.16):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-SWAK_GAUSS20=low & 5m:WAD sign=above 0 | up | 25.82 | 51.1 | +2.05 | +2.13 | +1.07 | 55.0 | pack | 11.1 | 25.42 | +1.73 | +1.1 | +1.0 | +1.8 | > twins | 1 |
| 2 | 1m:ERIbear13 sign=above 0 & POS:QPos=m00 | down | 34.43 | 51.7 | +3.08 | -1.59 | +1.49 | 54.8 | pack | 10.4 | 34.43 | +3.08 | +1.1 | +0.7 | +1.8 | > twins | 0 |
| 3 | 1m:ERIbear13 sign=below 0 & POS:QPos=m00 | up | 61.57 | 51.0 | +1.96 | +0.89 | +1.19 | 54.8 | none | 8.5 | 61.57 | +1.96 | +0.6 | +0.5 | +1.0 | > twins | 0 |
| 4 | 1m:AROONdn14=very low & 1m:C-TSF14 sign=above 0 | down | 38.32 | 50.8 | +2.16 | -1.42 | +1.51 | 54.5 | pack | 5.5 | 37.46 | +1.99 | +0.4 | +0.4 | +0.6 | > twins | 1 |
| 5 | 1m:HT_INPHASE sign=above 0 & POS:QPhase=m05-09 | down | 75.62 | 48.6 | -0.02 | +0.71 | -1.02 | 53.9 | none | 7.4 | 75.62 | +0.39 | +0.2 | +0.0 | +0.3 | > twins | 0 |
| 6 | 1m:HT_INPHASE sign=below 0 & POS:QPhase=m05-09 | up | 76.00 | 48.9 | -0.08 | -0.70 | -1.11 | 53.4 | none | 6.7 | 76.00 | +0.09 | -0.3 | -0.4 | -0.4 | > twins | 0 |
| 7 | 1m:DPO20 sign=above 0 & POS:QPos=m01 | up | 47.44 | 50.4 | +1.44 | +1.12 | +1.11 | 53.3 | none | 3.3 | 47.44 | +1.44 | +0.9 | +0.9 | +1.6 | > twins | 0 |
| 8 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 | down | 53.33 | 50.5 | +1.86 | -0.97 | +2.08 | 51.9 | pack | 4.0 | 44.67 | +0.77 | +0.2 | +0.3 | +0.3 | hot, rep, > twins | 0 |
| 9 | 1m:DX14=low & 1m:DIdiff14 sign=below 0 | up | 34.73 | 49.5 | +0.47 | -1.46 | -0.96 | 50.8 | pack | 13.4 | 33.87 | +0.45 | -0.0 | -0.0 | -0.0 | > twins | 0 |
| 10 | 1m:KDJ_J=low & 5m:EMV14 sign=above 0 | down | 29.04 | 47.0 | -1.66 | +1.75 | -2.97 | 50.8 | none | 10.1 | 28.01 | -1.40 | -1.7 | -1.6 | -2.8 | > twins | 0 |

**SOL, pairs, 15 minutes, by lheat** (twins' max 73.05):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ERIbull13 sign=above 0 & 1m:ERIbear13 sign=above 0 | down | 77.12 | 50.3 | +1.70 | -0.00 | +2.00 | 154.4 | pack | 10.7 | 66.39 | +0.44 | +0.3 | +0.3 | +0.5 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:TRIX30 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 52.22 | 51.1 | +2.54 | -0.40 | +2.87 | 149.7 | pack | 12.6 | 46.89 | +1.08 | -0.1 | +0.1 | -0.2 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:ERIbear13 sign=above 0 & 5m:WAD sign=above 0 | down | 52.21 | 51.5 | +2.85 | -0.45 | +2.81 | 146.9 | pack | 11.1 | 45.25 | +2.06 | +0.8 | +0.9 | +1.4 | hot, rep, BHY, > twins | 3 |
| 4 | 1m:C-FRAMA16 sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 70.65 | 50.4 | +1.81 | -0.16 | +2.25 | 144.6 | none | 13.2 | 63.22 | +0.23 | -0.3 | -0.1 | -0.5 | hot, rep, BHY, > twins | 1 |
| 5 | 1m:C-SAR sign=above 0 & 15m:QSTICK10 sign=above 0 | down | 44.95 | 51.3 | +2.73 | -0.48 | +3.15 | 141.6 | pack | 10.6 | 31.79 | +1.73 | +0.3 | +0.3 | +0.5 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:TRIX30 sign=above 0 & 1m:C-SAR sign=above 0 | down | 48.92 | 51.1 | +2.55 | -0.34 | +2.87 | 140.3 | pack | 12.6 | 33.79 | +1.93 | +0.5 | +0.7 | +0.8 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:C-SAR sign=above 0 & 15m:WAD sign=above 0 | down | 45.94 | 51.2 | +2.65 | -0.44 | +3.07 | 140.2 | pack | 10.7 | 32.45 | +1.68 | +0.7 | +0.6 | +1.1 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-MIDPOINT14 sign=above 0 & 15m:QSTICK10 sign=above 0 | down | 45.10 | 51.4 | +2.73 | -0.56 | +3.27 | 140.0 | pack | 10.6 | 35.74 | +1.33 | +0.1 | +0.1 | +0.1 | hot, rep, BHY, > twins | 15 |
| 9 | 1m:C-FRAMA16 sign=above 0 & 5m:EMV14 sign=above 0 | down | 53.76 | 51.0 | +2.41 | -0.44 | +2.88 | 140.0 | none | 10.1 | 48.22 | +0.87 | -0.1 | -0.0 | -0.2 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:ERIbear13 sign=above 0 & 5m:WT1>WT2=above | down | 52.94 | 51.1 | +2.46 | -0.30 | +2.61 | 138.2 | pack | 10.4 | 45.33 | +1.45 | +0.6 | +0.6 | +1.0 | > twins | 2 |

**SOL, pairs, 15 minutes, by oheat** (twins' max 66.71):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:AROONOSC25 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 62.47 | 51.2 | +2.55 | -0.50 | +2.80 | 159.0 | none | 12.2 | 54.61 | +1.10 | -0.0 | +0.1 | -0.0 | hot, rep, BHY, > twins | 8 |
| 2 | 1m:AROONOSC25 sign=above 0 & 1m:FISHER>trig=above | down | 62.49 | 51.0 | +2.40 | -0.48 | +1.85 | 150.1 | none | 12.2 | 56.91 | +1.74 | +0.3 | +0.4 | +0.6 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:AROONOSC25 sign=above 0 & 1m:ERIbear13 sign=above 0 | down | 57.74 | 51.2 | +2.60 | -0.35 | +2.37 | 150.1 | pack | 12.2 | 48.78 | +1.86 | +0.7 | +0.7 | +1.1 | hot, rep, BHY, > twins | 5 |
| 4 | 1m:KST sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 58.12 | 51.2 | +2.56 | -0.47 | +2.85 | 148.7 | none | 12.5 | 51.20 | +1.02 | -0.0 | +0.0 | -0.1 | hot, rep, BHY, > twins | 3 |
| 5 | 1m:ERIbear13 sign=above 0 & 5m:WAD sign=above 0 | down | 52.21 | 51.5 | +2.85 | -0.45 | +2.81 | 148.6 | pack | 11.1 | 45.25 | +2.06 | +0.8 | +0.9 | +1.4 | hot, rep, BHY, > twins | 3 |
| 6 | 1m:CTI20 sign=above 0 & 1m:HAbody sign=above 0 | down | 69.54 | 50.7 | +2.11 | -0.27 | +1.66 | 146.6 | pack | 10.6 | 64.42 | +1.45 | +0.3 | +0.3 | +0.5 | hot, rep, BHY, > twins | 11 |
| 7 | 1m:COPPOCK sign=above 0 & 1m:FISHER>trig=above | down | 66.48 | 50.8 | +2.20 | -0.32 | +1.49 | 146.3 | none | 10.2 | 59.82 | +1.69 | +0.4 | +0.4 | +0.7 | hot, rep, BHY, > twins | 3 |
| 8 | 1m:COPPOCK sign=above 0 & 1m:C-T3_5 sign=above 0 | down | 68.20 | 50.7 | +2.12 | -0.23 | +1.45 | 144.9 | none | 10.2 | 63.53 | +1.19 | +0.1 | +0.4 | +0.2 | hot, rep, BHY, > twins | 7 |
| 9 | 1m:C-FRAMA16 sign=above 0 & 5m:WAD sign=above 0 | down | 58.04 | 51.1 | +2.50 | -0.43 | +2.76 | 144.8 | none | 11.1 | 52.04 | +1.34 | +0.3 | +0.5 | +0.5 | hot, rep, BHY, > twins | 3 |
| 10 | 1m:COPPOCK sign=above 0 & 1m:STOCH14 K>D=above | down | 66.63 | 50.8 | +2.17 | -0.34 | +1.25 | 144.5 | none | 10.2 | 63.16 | +1.67 | +0.3 | +0.4 | +0.5 | hot, rep, BHY, > twins | 2 |

**SOL, pairs, 15 minutes, unseen, by iheat** (twins' max 42.16):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ERIbear13 sign=below 0 & POS:QPos=m00 | up | 61.57 | 51.0 | +1.96 | +0.89 | +1.19 | 54.8 | none | 8.5 | 61.57 | +1.96 | +0.6 | +0.5 | +1.0 | > twins | 0 |
| 2 | 1m:HT_INPHASE sign=above 0 & POS:QPhase=m05-09 | down | 75.62 | 48.6 | -0.02 | +0.71 | -1.02 | 53.9 | none | 7.4 | 75.62 | +0.39 | +0.2 | +0.0 | +0.3 | > twins | 0 |
| 3 | 1m:HT_INPHASE sign=below 0 & POS:QPhase=m05-09 | up | 76.00 | 48.9 | -0.08 | -0.70 | -1.11 | 53.4 | none | 6.7 | 76.00 | +0.09 | -0.3 | -0.4 | -0.4 | > twins | 0 |
| 4 | 1m:DPO20 sign=above 0 & POS:QPos=m01 | up | 47.44 | 50.4 | +1.44 | +1.12 | +1.11 | 53.3 | none | 3.3 | 47.44 | +1.44 | +0.9 | +0.9 | +1.6 | > twins | 0 |
| 5 | 1m:C-TEMA21 sign=above 0 & POS:QPos=m03 | up | 46.82 | 49.8 | +0.81 | +1.13 | +0.94 | 52.9 | none | 1.0 | 46.82 | +0.81 | -0.0 | -0.1 | -0.0 | > twins | 0 |
| 6 | 1m:KDJ_J=low & 5m:EMV14 sign=above 0 | down | 29.04 | 47.0 | -1.66 | +1.75 | -2.97 | 50.8 | none | 10.1 | 28.01 | -1.40 | -1.7 | -1.6 | -2.8 | > twins | 0 |
| 7 | 1m:C-TSF14=low & POS:QPhase=m00-04 | down | 28.83 | 50.6 | +2.05 | -1.76 | +2.17 | 50.7 | none | 3.6 | 28.83 | +2.27 | +0.8 | +0.5 | +1.3 | > twins | 0 |
| 8 | 1m:DX14=low & 1m:DIdiff14 sign=above 0 | down | 34.74 | 47.9 | -0.66 | +1.44 | -2.19 | 50.2 | none | 13.9 | 34.06 | -0.66 | -0.3 | -0.2 | -0.6 | > twins | 0 |
| 9 | 1m:ERIbull13 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 47.06 | 51.2 | +2.18 | +1.06 | +1.34 | 49.8 | none | 11.3 | 41.73 | +1.05 | +0.4 | +0.4 | +0.7 | hot, rep, > twins | 0 |
| 10 | 1m:AROONOSC25 sign=below 0 & 1m:C-SMA20 sign=above 0 | up | 49.20 | 50.4 | +1.39 | +1.01 | -0.07 | 49.7 | none | 11.7 | 41.48 | +1.66 | +0.3 | +0.1 | +0.5 | > twins | 0 |

**SOL, pairs, 15 minutes, unseen, by lheat** (twins' max 73.05):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-FRAMA16 sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 70.65 | 50.4 | +1.81 | -0.16 | +2.25 | 144.6 | none | 13.2 | 63.22 | +0.23 | -0.3 | -0.1 | -0.5 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:C-FRAMA16 sign=above 0 & 5m:AROONOSC14 sign=above 0 | down | 51.40 | 51.0 | +2.42 | -0.36 | +2.78 | 142.4 | none | 11.6 | 46.08 | +0.92 | -0.2 | -0.1 | -0.4 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:C-FRAMA16 sign=above 0 & 5m:EMV14 sign=above 0 | down | 53.76 | 51.0 | +2.41 | -0.44 | +2.88 | 140.0 | none | 10.1 | 48.22 | +0.87 | -0.1 | -0.0 | -0.2 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:C-MIDPOINT14 sign=above 0 & 15m:MOM10 sign=above 0 | down | 45.16 | 51.3 | +2.68 | -0.53 | +3.20 | 137.1 | none | 10.9 | 35.76 | +1.30 | +0.0 | +0.0 | +0.0 | hot, rep, BHY, > twins | 8 |
| 5 | 1m:C-MIDPRICE14 sign=above 0 & 15m:WAD sign=above 0 | down | 45.76 | 51.2 | +2.61 | -0.49 | +3.09 | 132.0 | none | 10.7 | 35.65 | +1.61 | +0.5 | +0.6 | +0.9 | hot, rep, BHY, > twins | 6 |
| 6 | 1m:C-MIDPRICE14 sign=above 0 & 15m:C-MIDPRICE14 sign=above 0 | down | 46.21 | 51.3 | +2.69 | -0.47 | +3.04 | 130.3 | none | 12.2 | 35.93 | +1.40 | +0.2 | +0.3 | +0.3 | hot, rep, BHY, > twins | 9 |
| 7 | 1m:C-VWMA20 sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 55.80 | 51.0 | +2.30 | -0.35 | +2.51 | 129.8 | none | 12.2 | 44.88 | +0.80 | +0.1 | +0.3 | +0.2 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:C-MIDPRICE14 sign=above 0 & 5m:AROONOSC14 sign=above 0 | down | 48.92 | 51.1 | +2.44 | -0.42 | +2.90 | 129.2 | none | 11.6 | 37.95 | +1.39 | +0.3 | +0.4 | +0.4 | hot, rep, BHY, > twins | 2 |
| 9 | 1m:CCI14 sign=above 0 & 15m:C-CKSPmid sign=above 0 | down | 45.90 | 51.2 | +2.64 | -0.34 | +2.96 | 126.4 | none | 12.7 | 34.77 | +1.32 | +0.3 | +0.3 | +0.5 | hot, rep, BHY, > twins | 3 |
| 10 | 1m:C-T3_5 sign=above 0 & 1m:HT_INPHASE sign=above 0 | down | 79.56 | 50.1 | +1.49 | -0.21 | +1.57 | 124.8 | none | 7.4 | 75.21 | +0.81 | +0.3 | +0.3 | +0.4 | hot, rep, BHY, > twins | 0 |

**SOL, pairs, 15 minutes, unseen, by oheat** (twins' max 58.27):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:AROONOSC25 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 62.47 | 51.2 | +2.55 | -0.50 | +2.80 | 159.0 | none | 12.2 | 54.61 | +1.10 | -0.0 | +0.1 | -0.0 | hot, rep, BHY, > twins | 7 |
| 2 | 1m:AROONOSC25 sign=above 0 & 1m:FISHER>trig=above | down | 62.49 | 51.0 | +2.40 | -0.48 | +1.85 | 150.1 | none | 12.2 | 56.91 | +1.74 | +0.3 | +0.4 | +0.6 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:AROONOSC25 sign=above 0 & 1m:CCI14 sign=above 0 | down | 61.93 | 51.0 | +2.41 | -0.43 | +2.86 | 149.0 | none | 12.2 | 45.87 | +1.37 | +0.3 | +0.5 | +0.5 | hot, rep, BHY, > twins | 7 |
| 4 | 1m:KST sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 58.12 | 51.2 | +2.56 | -0.47 | +2.85 | 148.7 | none | 12.5 | 51.20 | +1.02 | -0.0 | +0.0 | -0.1 | hot, rep, BHY, > twins | 3 |
| 5 | 1m:COPPOCK sign=above 0 & 1m:FISHER>trig=above | down | 66.48 | 50.8 | +2.20 | -0.32 | +1.49 | 146.3 | none | 10.2 | 59.82 | +1.69 | +0.4 | +0.4 | +0.7 | hot, rep, BHY, > twins | 3 |
| 6 | 1m:COPPOCK sign=above 0 & 1m:C-T3_5 sign=above 0 | down | 68.20 | 50.7 | +2.12 | -0.23 | +1.45 | 144.9 | none | 10.2 | 63.53 | +1.19 | +0.1 | +0.4 | +0.2 | hot, rep, BHY, > twins | 7 |
| 7 | 1m:C-FRAMA16 sign=above 0 & 5m:WAD sign=above 0 | down | 58.04 | 51.1 | +2.50 | -0.43 | +2.76 | 144.8 | none | 11.1 | 52.04 | +1.34 | +0.3 | +0.5 | +0.5 | hot, rep, BHY, > twins | 3 |
| 8 | 1m:COPPOCK sign=above 0 & 1m:STOCH14 K>D=above | down | 66.63 | 50.8 | +2.17 | -0.34 | +1.25 | 144.5 | none | 10.2 | 63.16 | +1.67 | +0.3 | +0.4 | +0.5 | hot, rep, BHY, > twins | 2 |
| 9 | 1m:FISHER>trig=above & 1m:Tenkan>Kijun=above | down | 60.96 | 51.0 | +2.34 | -0.40 | +1.83 | 142.9 | none | 10.9 | 55.77 | +1.62 | +0.3 | +0.3 | +0.5 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:CTI20 sign=above 0 & 1m:KDJ K>D=above | down | 65.34 | 50.8 | +2.17 | -0.37 | +1.43 | 141.8 | none | 10.6 | 58.49 | +1.45 | +0.4 | +0.5 | +0.7 | hot, rep, BHY, > twins | 1 |

**SOL, triples, 15 minutes, by iheat** (twins' max 29.34):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:HT_INPHASE sign=above 0 | up | 48.61 | 50.2 | +1.26 | +1.13 | +0.46 | 54.7 | none | 7.4 | 46.38 | +1.04 | +0.3 | +0.5 | +0.5 | > twins | 0 |
| 2 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=cycle & 1m:CCI20 sign=below 0 | up | 43.73 | 49.2 | +0.19 | -1.13 | -1.27 | 49.3 | none | 10.2 | 40.76 | +0.47 | -0.1 | -0.0 | -0.2 | hot, rep, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:C-WMA20 sign=above 0 | down | 50.55 | 48.1 | -0.55 | +0.96 | -2.03 | 48.7 | none | 10.3 | 47.01 | -0.95 | -0.2 | -0.1 | -0.3 | > twins | 0 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:PVO12/26 sign=below 0 | down | 43.93 | 48.6 | +0.02 | +1.07 | -2.12 | 47.1 | none | 5.5 | 41.71 | +0.06 | +0.3 | +0.2 | +0.4 | hot, rep, > twins | 0 |
| 5 | 1m:C-EMA21=very low/low/high/NA & 1m:C-SWAK_BUTTER20=very low/low/high/very high/NA & 5m:FOSC5 sign=above 0/NA | down | 37.48 | 50.4 | +1.86 | -1.16 | +0.78 | 43.4 | pack | 2.5 | 36.58 | +1.65 | +0.5 | +0.7 | +0.8 | hot, rep, > twins | 0 |
| 6 | 1m:DONCHIAN55pos=very low/low/high & 5m:C-AVGPRICE sign=above 0/NA & 5m:CMOU14=very low/low/mid/high/NA | down | 38.22 | 51.3 | +2.68 | -1.13 | -5.78 | 43.2 | pack | 9.2 | 36.98 | +2.52 | +1.0 | +1.1 | +1.6 | hot, rep, > twins | 0 |
| 7 | 1m:DONCHIAN55pos=very low/low/high & 5m:C-AVGPRICE sign=below 0 & 5m:CMOU14=very low/low/mid/high/NA | up | 38.94 | 50.5 | +1.44 | +1.03 | +0.48 | 40.1 | pack | 8.5 | 36.41 | +0.71 | -0.2 | -0.2 | -0.3 | hot, rep, > twins | 0 |
| 8 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:PVO12/26 sign=below 0 | down | 41.51 | 48.5 | -0.03 | +0.94 | -1.92 | 39.1 | none | 5.4 | 39.28 | -0.02 | +0.3 | +0.2 | +0.4 | hot, rep, > twins | 0 |
| 9 | 1m:HAbody sign=below 0/NA & 1m:HT_SINE=low/high/very high/NA & 5m:C-HMA20 sign=below 0 | down | 34.35 | 48.0 | -0.65 | -1.12 | -0.09 | 38.5 | none | 6.0 | 33.48 | -0.48 | +0.0 | -0.1 | +0.1 | > twins | 0 |
| 10 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:OBVdiv10=bear div | down | 19.01 | 48.2 | -0.37 | +1.99 | -1.68 | 37.8 | none | 5.4 | 18.28 | -0.52 | +0.2 | +0.0 | +0.4 | > twins | 0 |

**SOL, triples, 15 minutes, by lheat** (twins' max 47.90):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PVT sign=above 0 & 5m:WAD=mid/high/very high & PERP:Basis=very low/low/mid | down | 82.34 | 50.0 | +1.41 | -0.08 | +2.31 | 179.8 | pack | 12.1 | 62.47 | +0.18 | +0.2 | +0.3 | +0.3 | > twins | 0 |
| 2 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 5m:CMF20 sign=above 0 | down | 30.25 | 52.0 | +3.32 | -0.97 | +3.35 | 101.3 | pack | 8.6 | 25.33 | +3.01 | +0.7 | +0.8 | +1.1 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:EFI13 sign=above 0 | down | 40.93 | 51.1 | +2.45 | -0.37 | +2.44 | 99.7 | pack | 7.0 | 34.63 | +1.79 | +0.3 | +0.5 | +0.5 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:C-MAMA sign=above 0 | down | 44.75 | 51.2 | +2.49 | -0.27 | +2.19 | 98.1 | pack | 9.1 | 40.12 | +2.10 | +0.5 | +0.7 | +0.9 | > twins | 14 |
| 5 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:AD sign=above 0 | down | 53.83 | 50.5 | +1.88 | -0.28 | +1.57 | 84.8 | none | 7.8 | 48.10 | +1.26 | +0.6 | +0.8 | +1.0 | hot, rep, > twins | 0 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:HT_INPHASE sign=above 0 | down | 55.15 | 50.4 | +1.71 | -0.15 | +1.53 | 84.6 | none | 7.4 | 49.96 | +1.15 | +0.5 | +0.5 | +0.9 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:OBV sign=above 0 | down | 52.99 | 50.6 | +1.94 | -0.32 | +1.59 | 84.3 | none | 10.1 | 47.15 | +1.22 | +0.6 | +0.8 | +1.0 | hot, rep, > twins | 0 |
| 8 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:C-MIDPRICE14 sign=above 0 | down | 21.60 | 52.6 | +3.85 | -0.76 | +3.56 | 77.0 | none | 9.2 | 17.22 | +2.53 | +0.1 | +0.1 | +0.1 | > twins | 11 |
| 9 | 15m:TakerBuy=mid/high/very high/NA & 1m:C-EMA50=mid/high/very high/NA & 5m:C-VIDYA12 sign=above 0 | down | 53.35 | 50.0 | +1.40 | -0.08 | +2.05 | 75.3 | pack | 15.2 | 16.99 | +0.19 | -0.2 | -0.0 | -0.3 | hot, rep, BHY, > twins | 1 |
| 10 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:PVI sign=above 0 | down | 21.35 | 52.4 | +3.69 | -0.66 | +3.36 | 71.7 | none | 11.3 | 15.98 | +2.83 | +0.9 | +1.1 | +1.5 | hot, rep, BHY, > twins | 0 |

**SOL, triples, 15 minutes, by oheat** (twins' max 50.38):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:C-DEMA21=mid/high/very high/NA & 1m:AROONup25=very high & 1m:C-EMA9=mid/high/very high/NA | down | 43.50 | 51.3 | +2.68 | +0.11 | -0.62 | 116.7 | pack | 7.5 | 41.48 | +3.01 | +1.1 | +1.1 | +1.8 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:PVT sign=above 0 & 5m:WAD=mid/high/very high & PERP:Basis=very low/low/mid | down | 82.34 | 50.0 | +1.41 | -0.08 | +2.31 | 116.4 | pack | 12.1 | 62.47 | +0.18 | +0.2 | +0.3 | +0.3 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:C-AVGPRICE sign=above 0 & 1m:MACD5/35 sign=above 0 & POS:QPos=m00/m04/m10/m13 | down | 56.12 | 50.7 | +2.07 | -0.51 | +0.33 | 116.2 | pack | 12.8 | 56.12 | +2.07 | +0.4 | +0.3 | +0.7 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 44.12 | 51.2 | +2.56 | -0.22 | +2.10 | 113.1 | pack | 6.8 | 40.37 | +2.20 | +0.5 | +0.6 | +0.8 | hot, rep, BHY, > twins | 11 |
| 5 | 15m:SWAK_HP20 sign=above 0 & 1m:PVT sign=above 0 & 5m:ROGERSSATCHELL10=mid/high/very high/NA | down | 41.60 | 51.3 | +2.69 | -0.43 | +1.90 | 111.9 | pack | 15.2 | 32.87 | +1.46 | -0.2 | -0.1 | -0.4 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:VORTEXdiff14 sign=above 0 | down | 41.62 | 51.3 | +2.65 | -0.37 | +1.95 | 110.2 | pack | 10.8 | 34.65 | +1.78 | +0.3 | +0.5 | +0.5 | hot, rep, BHY, > twins | 8 |
| 7 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:ERIbear13 sign=above 0 | down | 49.98 | 50.8 | +2.18 | -0.08 | +0.83 | 108.8 | pack | 10.4 | 45.13 | +1.29 | +0.4 | +0.4 | +0.6 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:C-ALMA9 sign=above 0 | down | 45.25 | 51.1 | +2.39 | -0.23 | +1.64 | 108.0 | pack | 6.3 | 42.39 | +1.89 | +0.5 | +0.7 | +0.9 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:C-SMA50 sign=above 0 | down | 47.48 | 50.8 | +2.23 | -0.25 | +1.27 | 105.7 | none | 12.5 | 41.59 | +1.47 | +0.4 | +0.5 | +0.7 | hot, rep, BHY, > twins | 8 |
| 10 | 1m:C-VIDYA12 sign=above 0 & PERP:Lead1=very low/low/mid & POS:QPos=m00/m01/m02/m03/m05/m10/m12/m14/NA | down | 76.84 | 50.0 | +1.37 | -0.14 | -5.46 | 105.6 | pack | 13.4 | 71.91 | +0.85 | +0.0 | +0.0 | +0.0 | hot, rep, BHY, > twins | 0 |

**SOL, triples, 15 minutes, unseen, by iheat** (twins' max 29.34):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:HT_INPHASE sign=above 0 | up | 48.61 | 50.2 | +1.26 | +1.13 | +0.46 | 54.7 | none | 7.4 | 46.38 | +1.04 | +0.3 | +0.5 | +0.5 | > twins | 0 |
| 2 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=cycle & 1m:CCI20 sign=below 0 | up | 43.73 | 49.2 | +0.19 | -1.13 | -1.27 | 49.3 | none | 10.2 | 40.76 | +0.47 | -0.1 | -0.0 | -0.2 | hot, rep, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:C-WMA20 sign=above 0 | down | 50.55 | 48.1 | -0.55 | +0.96 | -2.03 | 48.7 | none | 10.3 | 47.01 | -0.95 | -0.2 | -0.1 | -0.3 | > twins | 0 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:PVO12/26 sign=below 0 | down | 43.93 | 48.6 | +0.02 | +1.07 | -2.12 | 47.1 | none | 5.5 | 41.71 | +0.06 | +0.3 | +0.2 | +0.4 | hot, rep, > twins | 0 |
| 5 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:PVO12/26 sign=below 0 | down | 41.51 | 48.5 | -0.03 | +0.94 | -1.92 | 39.1 | none | 5.4 | 39.28 | -0.02 | +0.3 | +0.2 | +0.4 | hot, rep, > twins | 0 |
| 6 | 1m:HAbody sign=below 0/NA & 1m:HT_SINE=low/high/very high/NA & 5m:C-HMA20 sign=below 0 | down | 34.35 | 48.0 | -0.65 | -1.12 | -0.09 | 38.5 | none | 6.0 | 33.48 | -0.48 | +0.0 | -0.1 | +0.1 | > twins | 0 |
| 7 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:OBVdiv10=bear div | down | 19.01 | 48.2 | -0.37 | +1.99 | -1.68 | 37.8 | none | 5.4 | 18.28 | -0.52 | +0.2 | +0.0 | +0.4 | > twins | 0 |
| 8 | PERP:Basis=very low/low/mid & POS:QPos=m00/m01/m12/m14 & X.BTC:RSI14=very low/low/NA | up | 25.47 | 52.2 | +3.07 | +1.40 | +2.06 | 35.6 | none | 0.0 | 19.26 | +2.63 | +0.1 | -0.0 | +0.2 | > twins | 0 |
| 9 | 1m:IBS=very low/low/NA & 5m:ADOSC sign=above 0/NA & 5m:TRANGE=mid/high/very high/NA | down | 36.51 | 48.6 | +0.15 | +0.83 | -0.88 | 30.2 | none | 7.9 | 36.40 | +0.30 | -0.4 | -0.8 | -0.6 | > twins | 0 |
| 10 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:C-TSF14=high | down | 15.56 | 49.5 | +0.88 | -1.83 | +1.24 | 28.4 | none | 3.2 | 15.56 | +0.19 | +0.6 | +0.8 | +1.0 | none | 0 |

**SOL, triples, 15 minutes, unseen, by lheat** (twins' max 46.55):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:AD sign=above 0 | down | 53.83 | 50.5 | +1.88 | -0.28 | +1.57 | 84.8 | none | 7.8 | 48.10 | +1.26 | +0.6 | +0.8 | +1.0 | hot, rep, > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:HT_INPHASE sign=above 0 | down | 55.15 | 50.4 | +1.71 | -0.15 | +1.53 | 84.6 | none | 7.4 | 49.96 | +1.15 | +0.5 | +0.5 | +0.9 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:OBV sign=above 0 | down | 52.99 | 50.6 | +1.94 | -0.32 | +1.59 | 84.3 | none | 10.1 | 47.15 | +1.22 | +0.6 | +0.8 | +1.0 | hot, rep, > twins | 0 |
| 4 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:C-MIDPRICE14 sign=above 0 | down | 21.60 | 52.6 | +3.85 | -0.76 | +3.56 | 77.0 | none | 9.2 | 17.22 | +2.53 | +0.1 | +0.1 | +0.1 | > twins | 10 |
| 5 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:PVI sign=above 0 | down | 21.35 | 52.4 | +3.69 | -0.66 | +3.36 | 71.7 | none | 11.3 | 15.98 | +2.83 | +0.9 | +1.1 | +1.5 | hot, rep, BHY, > twins | 0 |
| 6 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:ERIbull13 sign=above 0 | down | 23.42 | 51.7 | +2.95 | -0.27 | +2.88 | 67.6 | none | 10.7 | 17.59 | +1.47 | -0.2 | -0.3 | -0.3 | hot, rep, BHY, > twins | 1 |
| 7 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:C-T3_5 sign=below 0 | up | 43.84 | 50.7 | +1.77 | +0.45 | +1.52 | 66.8 | none | 5.4 | 43.84 | +0.79 | +0.3 | +0.5 | +0.5 | > twins | 1 |
| 8 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=cycle & 1m:KDJ K>D=above | down | 53.03 | 49.7 | +1.16 | -0.34 | +1.21 | 64.3 | none | 3.1 | 46.84 | +0.73 | +0.4 | +0.6 | +0.7 | > twins | 0 |
| 9 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 15m:ERIbear13 sign=below 0 | up | 48.78 | 50.6 | +1.56 | -0.17 | +1.19 | 58.1 | none | 9.4 | 41.24 | +1.24 | -0.1 | -0.0 | -0.2 | > twins | 0 |
| 10 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 60m:STOCH5 K>D=below | up | 35.83 | 50.8 | +1.75 | +0.21 | +1.60 | 57.4 | none | 3.3 | 30.06 | +1.49 | +0.8 | +0.9 | +1.3 | > twins | 0 |

**SOL, triples, 15 minutes, unseen, by oheat** (twins' max 37.38):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:C-SMA50 sign=above 0 | down | 47.48 | 50.8 | +2.23 | -0.25 | +1.27 | 105.7 | none | 12.5 | 41.59 | +1.47 | +0.4 | +0.5 | +0.7 | hot, rep, BHY, > twins | 8 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:OBV sign=above 0 | down | 52.99 | 50.6 | +1.94 | -0.32 | +1.59 | 102.8 | none | 10.1 | 47.15 | +1.22 | +0.6 | +0.8 | +1.0 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:AD sign=above 0 | down | 53.83 | 50.5 | +1.88 | -0.28 | +1.57 | 101.2 | none | 7.8 | 48.10 | +1.26 | +0.6 | +0.8 | +1.0 | hot, rep, BHY, > twins | 0 |
| 4 | 15m:CORRELcv30=mid/high/very high/NA & 1m:SINE>LEAD=above & OI:PxQuad60=new longs/short covering/new shorts/NA | down | 60.81 | 50.2 | +1.56 | -0.19 | -0.53 | 95.0 | none | 9.2 | 35.74 | +0.20 | -0.0 | +0.3 | -0.0 | hot, rep, BHY, > twins | 0 |
| 5 | 15m:SI sign=below 0/NA & 1m:IBS=high/very high & 1m:QSTICK10=mid/high/very high | up | 35.07 | 51.3 | +2.54 | +0.16 | -1.47 | 89.0 | none | 15.5 | 35.02 | +2.35 | +0.9 | +0.5 | +1.5 | hot, rep, BHY, > twins | 0 |
| 6 | 15m:KURTOSIS30=very low/low/mid/NA & 1m:ADOSC=very low/low/mid/NA & 5m:C-AVGPRICE sign=below 0 | up | 76.21 | 50.1 | +1.14 | -0.00 | +0.64 | 86.8 | none | 8.5 | 61.36 | +0.48 | -0.1 | +0.4 | -0.1 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:C-SMA20 sign=below 0 & 5m:CMOU14=very low/low/mid/NA & 60m:HT_DCPERIOD=very low/low/mid/NA | up | 69.65 | 50.2 | +1.22 | -0.02 | -0.73 | 85.2 | none | 11.0 | 49.94 | +0.20 | -0.2 | -0.0 | -0.3 | hot, rep, BHY, > twins | 0 |
| 8 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 22.17 | 52.5 | +3.77 | -0.56 | +3.18 | 83.7 | none | 7.6 | 20.10 | +2.77 | +0.2 | +0.3 | +0.3 | hot, rep, BHY, > twins | 0 |
| 9 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:C-MIDPRICE14 sign=above 0 | down | 21.60 | 52.6 | +3.85 | -0.76 | +3.56 | 83.1 | none | 9.2 | 17.22 | +2.53 | +0.1 | +0.1 | +0.1 | hot, rep, BHY, > twins | 10 |
| 10 | 5m:MACDh12/26/9 sign=above 0 & 5m:PVO12/26 sign=above 0 & 1m:C-MAMA sign=above 0 | down | 22.35 | 52.5 | +3.71 | -0.69 | +3.27 | 83.0 | none | 9.1 | 20.15 | +2.64 | +0.2 | +0.3 | +0.3 | hot, rep, BHY, > twins | 0 |

**SOL, pairs, 60 minutes, by iheat** (twins' max 27.17):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=above 0 & 1m:HT_INPHASE=low | up | 12.94 | 52.4 | +2.26 | +2.17 | +1.77 | 28.1 | none | 4.0 | 12.89 | +1.36 | +0.6 | +0.3 | +1.0 | > twins | 0 |
| 2 | 1m:QSTICK10=high & 1m:PVO12/26 sign=below 0 | down | 16.34 | 48.0 | -0.69 | +1.68 | -3.37 | 27.5 | none | 3.7 | 16.14 | -0.06 | -0.6 | -0.8 | -1.0 | > twins | 0 |
| 3 | 1m:KDJ K>D=below & X.ETH:R5z=high | down | 7.70 | 52.8 | +4.04 | -3.47 | +3.57 | 26.7 | none | 2.3 | 7.67 | +3.05 | +1.4 | +1.4 | +2.3 | none | 0 |
| 4 | 1m:C-SMA20=high & 1m:PVO12/26 sign=below 0 | down | 14.64 | 47.7 | -0.97 | +1.82 | -3.51 | 26.6 | pack | 6.2 | 14.44 | -0.38 | -1.0 | -1.1 | -1.7 | none | 0 |
| 5 | 1m:PVO12/26 sign=below 0 & 1m:LRSLOPE14=high | down | 14.30 | 47.9 | -0.83 | +1.86 | -3.74 | 26.6 | none | 5.2 | 13.96 | -0.05 | -1.5 | -1.4 | -2.5 | none | 0 |
| 6 | 1m:KDJ_J=low & 1m:MAMA>FAMA=above | down | 16.21 | 46.9 | -1.84 | +1.64 | -2.59 | 26.6 | none | 10.0 | 16.15 | -1.22 | -3.1 | -3.0 | -5.2 | none | 0 |
| 7 | 1m:CMOU14 sign=above 0 & 1m:OBVdiv10=bull div | down | 17.21 | 48.4 | -0.33 | +1.52 | -1.16 | 26.1 | none | 9.9 | 17.12 | -0.09 | +0.1 | -0.1 | +0.1 | none | 0 |
| 8 | 1m:AROONup14=very high & 1m:CTI20 sign=below 0 | down | 17.85 | 50.1 | +1.31 | -1.45 | +0.28 | 25.9 | pack | 7.4 | 17.82 | +0.98 | +0.7 | +0.8 | +1.1 | none | 1 |
| 9 | 1m:MACDh12/26/9=low & 5m:C-HMA20 sign=above 0 | up | 8.37 | 53.3 | +3.32 | +3.05 | +2.52 | 25.5 | none | 4.0 | 8.29 | +2.33 | +3.8 | +3.4 | +6.4 | none | 0 |
| 10 | 1m:AROONOSC14 sign=above 0 & 1m:OBVdiv10=bull div | down | 17.59 | 48.5 | -0.26 | +1.44 | -1.12 | 25.3 | none | 9.4 | 17.47 | +0.12 | +0.1 | -0.2 | +0.1 | none | 0 |

**SOL, pairs, 60 minutes, by lheat** (twins' max 40.38):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-SMA50 sign=below 0 & 5m:NVI sign=above 0 | up | 17.46 | 52.6 | +2.57 | +0.49 | +2.78 | 48.6 | none | 8.8 | 16.66 | +1.26 | +1.3 | +1.2 | +2.1 | hot, rep, > twins | 1 |
| 2 | 1m:DIdiff14 sign=below 0 & 5m:NVI sign=above 0 | up | 18.74 | 52.4 | +2.36 | +0.43 | +2.57 | 48.1 | pack | 10.0 | 18.08 | +1.07 | +0.7 | +0.7 | +1.1 | hot, rep, > twins | 0 |
| 3 | 1m:RSI7=low & 60m:HT_TRENDMODE=trend | up | 12.83 | 53.5 | +3.39 | +1.90 | +3.68 | 47.2 | pack | 6.4 | 12.73 | +3.03 | +4.3 | +4.1 | +7.2 | > twins | 0 |
| 4 | 1m:C-EMA21=low & 60m:HT_TRENDMODE=trend | up | 11.79 | 53.7 | +3.60 | +1.99 | +3.94 | 46.5 | pack | 6.9 | 11.68 | +3.35 | +4.6 | +4.4 | +7.7 | > twins | 1 |
| 5 | 1m:C-MIDPOINT14=high & 1m:PVO12/26 sign=above 0 | down | 15.55 | 51.5 | +2.76 | -1.46 | +2.98 | 46.4 | pack | 5.4 | 15.42 | +2.42 | +1.3 | +1.6 | +2.2 | > twins | 0 |
| 6 | 1m:C-TRIMA20=low & 60m:HT_TRENDMODE=trend | up | 12.37 | 53.5 | +3.42 | +1.77 | +3.74 | 46.3 | pack | 6.1 | 12.22 | +3.45 | +5.1 | +4.8 | +8.6 | > twins | 0 |
| 7 | 1m:WT1 sign=below 0 & 5m:NVI sign=above 0 | up | 17.68 | 52.5 | +2.45 | +0.37 | +2.61 | 46.1 | pack | 8.2 | 16.63 | +1.05 | +0.9 | +1.0 | +1.6 | hot, rep, > twins | 0 |
| 8 | 1m:C-TRIMA20=high & 1m:PVO12/26 sign=above 0 | down | 15.08 | 51.4 | +2.69 | -1.33 | +2.93 | 44.2 | pack | 5.6 | 14.89 | +2.29 | +0.1 | +0.3 | +0.1 | > twins | 0 |
| 9 | 1m:PVO12/26 sign=above 0 & 1m:LRSLOPE14=high | down | 13.81 | 51.7 | +2.92 | -1.57 | +3.18 | 43.9 | pack | 5.2 | 13.51 | +1.92 | +0.2 | +0.2 | +0.3 | > twins | 0 |
| 10 | 1m:ASI=high & 15m:SWAK_HP20 sign=above 0 | down | 11.98 | 52.4 | +3.64 | -1.46 | +3.57 | 42.8 | pack | 11.1 | 11.82 | +3.38 | +2.1 | +2.2 | +3.5 | > twins | 5 |

**SOL, pairs, 60 minutes, by oheat** (twins' max 45.40):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:TakerBuy=low & 5m:NVI sign=above 0 | up | 14.28 | 53.6 | +3.70 | +0.52 | +2.82 | 52.8 | pack | 1.8 | 14.27 | +3.47 | +3.8 | +3.9 | +6.0 | > twins | 0 |
| 2 | 1m:C-TEMA21 sign=above 0 & FLOW:TB5=high | down | 18.57 | 51.4 | +2.79 | -0.53 | +2.20 | 51.8 | none | 4.9 | 18.46 | +2.20 | +2.7 | +2.5 | +4.5 | hot, rep, BHY, > twins | 2 |
| 3 | 1m:FISHER10 sign=below 0 & 1m:TakerBuy=low | up | 16.90 | 52.9 | +2.98 | +0.07 | +1.46 | 50.3 | pack | 7.1 | 16.89 | +2.86 | +0.9 | +0.9 | +1.4 | > twins | 0 |
| 4 | 1m:TakerBuy=low & 15m:HT_QUADRATURE sign=below 0 | up | 13.67 | 53.6 | +3.63 | +1.20 | +2.59 | 49.7 | pack | 1.7 | 13.66 | +3.38 | +2.7 | +2.8 | +4.2 | > twins | 0 |
| 5 | 1m:DPO20 sign=below 0 & FLOW:TB5=high | down | 17.60 | 51.4 | +2.76 | -0.37 | +1.67 | 48.6 | pack | 5.1 | 17.49 | +2.44 | +2.7 | +2.6 | +4.5 | hot, rep, BHY, > twins | 0 |
| 6 | 5m:NVI sign=above 0 & FLOW:TB5=low | up | 11.89 | 54.1 | +4.09 | +1.04 | +3.55 | 48.6 | none | 3.2 | 11.71 | +3.77 | +4.2 | +4.2 | +6.6 | > twins | 0 |
| 7 | 1m:C-TEMA21 sign=below 0 & FLOW:TB15=low | up | 12.87 | 53.7 | +3.77 | +0.93 | +2.57 | 48.5 | none | 4.0 | 12.68 | +2.89 | +1.4 | +1.2 | +2.3 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:STOCHK5=low & 5m:NVI sign=above 0 | up | 15.97 | 53.0 | +2.98 | +0.74 | +2.32 | 47.5 | pack | 1.9 | 15.92 | +2.46 | +3.7 | +3.7 | +6.2 | > twins | 0 |
| 9 | 1m:C-DEMA21 sign=below 0 & FLOW:TB15=low | up | 13.35 | 53.5 | +3.51 | +0.73 | +2.79 | 46.8 | none | 4.0 | 13.05 | +2.61 | +1.2 | +1.1 | +1.9 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:ASI=high & 15m:C-MIDPOINT14 sign=above 0 | down | 11.00 | 52.9 | +4.15 | -1.56 | +3.66 | 45.6 | pack | 10.0 | 10.84 | +4.11 | +2.4 | +2.6 | +4.0 | hot, rep, BHY, > twins | 8 |

**SOL, pairs, 60 minutes, unseen, by iheat** (twins' max 27.17):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=above 0 & 1m:HT_INPHASE=low | up | 12.94 | 52.4 | +2.26 | +2.17 | +1.77 | 28.1 | none | 4.0 | 12.89 | +1.36 | +0.6 | +0.3 | +1.0 | > twins | 0 |
| 2 | 1m:QSTICK10=high & 1m:PVO12/26 sign=below 0 | down | 16.34 | 48.0 | -0.69 | +1.68 | -3.37 | 27.5 | none | 3.7 | 16.14 | -0.06 | -0.6 | -0.8 | -1.0 | > twins | 0 |
| 3 | 1m:KDJ K>D=below & X.ETH:R5z=high | down | 7.70 | 52.8 | +4.04 | -3.47 | +3.57 | 26.7 | none | 2.3 | 7.67 | +3.05 | +1.4 | +1.4 | +2.3 | none | 0 |
| 4 | 1m:PVO12/26 sign=below 0 & 1m:LRSLOPE14=high | down | 14.30 | 47.9 | -0.83 | +1.86 | -3.74 | 26.6 | none | 5.2 | 13.96 | -0.05 | -1.5 | -1.4 | -2.5 | none | 0 |
| 5 | 1m:KDJ_J=low & 1m:MAMA>FAMA=above | down | 16.21 | 46.9 | -1.84 | +1.64 | -2.59 | 26.6 | none | 10.0 | 16.15 | -1.22 | -3.1 | -3.0 | -5.2 | none | 0 |
| 6 | 1m:C-MIDPOINT14=high & 1m:PVO12/26 sign=below 0 | down | 16.53 | 48.1 | -0.56 | +1.58 | -3.31 | 26.2 | none | 5.4 | 16.35 | -0.29 | -0.6 | -0.6 | -1.0 | none | 0 |
| 7 | 1m:CMOU14 sign=above 0 & 1m:OBVdiv10=bull div | down | 17.21 | 48.4 | -0.33 | +1.52 | -1.16 | 26.1 | none | 9.9 | 17.12 | -0.09 | +0.1 | -0.1 | +0.1 | none | 0 |
| 8 | 1m:MACDh12/26/9=low & 5m:C-HMA20 sign=above 0 | up | 8.37 | 53.3 | +3.32 | +3.05 | +2.52 | 25.5 | none | 4.0 | 8.29 | +2.33 | +3.8 | +3.4 | +6.4 | none | 0 |
| 9 | 1m:AROONOSC14 sign=above 0 & 1m:OBVdiv10=bull div | down | 17.59 | 48.5 | -0.26 | +1.44 | -1.12 | 25.3 | none | 9.4 | 17.47 | +0.12 | +0.1 | -0.2 | +0.1 | none | 0 |
| 10 | 1m:AROONdn25=very low & POS:HourQ=h45-59 | down | 12.47 | 50.9 | +2.12 | -1.98 | +2.47 | 24.7 | none | 5.5 | 12.47 | +2.25 | +3.6 | +3.6 | +5.9 | none | 0 |

**SOL, pairs, 60 minutes, unseen, by lheat** (twins' max 38.64):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-SMA50 sign=below 0 & 5m:NVI sign=above 0 | up | 17.46 | 52.6 | +2.57 | +0.49 | +2.78 | 48.6 | none | 8.8 | 16.66 | +1.26 | +1.3 | +1.2 | +2.1 | hot, rep, > twins | 0 |
| 2 | 1m:C-MCGD14 sign=below 0 & 5m:NVI sign=above 0 | up | 19.20 | 52.3 | +2.28 | +0.28 | +2.37 | 45.5 | none | 9.2 | 18.77 | +1.38 | +1.3 | +1.4 | +2.2 | hot, rep, > twins | 0 |
| 3 | 1m:AROONOSC14 sign=below 0 & 5m:NVI sign=above 0 | up | 19.50 | 52.2 | +2.20 | +0.22 | +2.33 | 45.4 | none | 7.9 | 18.79 | +1.10 | +1.1 | +1.1 | +1.9 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:C-WMA20=high & 1m:CVI10 sign=above 0 | down | 17.81 | 50.9 | +2.20 | -0.94 | +2.35 | 41.8 | none | 6.0 | 17.71 | +1.86 | -0.2 | -0.0 | -0.3 | > twins | 0 |
| 5 | 1m:ROC10=high & 1m:CVI10 sign=above 0 | down | 16.65 | 51.0 | +2.31 | -1.03 | +2.47 | 41.1 | none | 3.8 | 16.51 | +2.16 | +0.7 | +0.8 | +1.2 | > twins | 0 |
| 6 | 5m:QSTICK10 sign=above 0 & 5m:STOCH5 K>D=above | down | 19.50 | 50.3 | +1.58 | -0.55 | +2.10 | 41.0 | none | 10.1 | 18.64 | +0.87 | +0.7 | +0.8 | +1.2 | > twins | 2 |
| 7 | 1m:ERIbull13 sign=above 0 & FLOW:TB15=high | down | 14.68 | 51.5 | +2.85 | -0.37 | +2.79 | 41.0 | none | 9.1 | 14.24 | +1.81 | +0.7 | +0.8 | +1.2 | > twins | 0 |
| 8 | 1m:C-TRIMA20=high & 1m:CVI10 sign=above 0 | down | 16.33 | 51.0 | +2.34 | -1.00 | +2.51 | 40.9 | none | 5.6 | 16.19 | +2.22 | +0.1 | +0.3 | +0.2 | > twins | 0 |
| 9 | 1m:ROC10=high & 5m:DPO20 sign=below 0 | down | 14.84 | 51.5 | +2.72 | -1.32 | +2.72 | 40.4 | none | 6.1 | 14.67 | +2.14 | +1.3 | +1.3 | +2.1 | > twins | 2 |
| 10 | 1m:AC sign=below 0 & X.ETH:TakerBuy=low | up | 21.94 | 52.1 | +2.04 | +0.36 | +1.73 | 38.0 | none | 2.7 | 21.93 | +1.70 | +1.3 | +1.4 | +2.1 | none | 0 |

**SOL, pairs, 60 minutes, unseen, by oheat** (twins' max 42.52):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-TEMA21 sign=above 0 & FLOW:TB5=high | down | 18.57 | 51.4 | +2.79 | -0.53 | +2.20 | 51.8 | none | 4.9 | 18.46 | +2.20 | +2.7 | +2.5 | +4.5 | hot, rep, BHY, > twins | 2 |
| 2 | 5m:NVI sign=above 0 & FLOW:TB5=low | up | 11.89 | 54.1 | +4.09 | +1.04 | +3.55 | 48.6 | none | 3.2 | 11.71 | +3.77 | +4.2 | +4.2 | +6.6 | > twins | 0 |
| 3 | 1m:C-TEMA21 sign=below 0 & FLOW:TB15=low | up | 12.87 | 53.7 | +3.77 | +0.93 | +2.57 | 48.5 | none | 4.0 | 12.68 | +2.89 | +1.4 | +1.2 | +2.3 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:CMF20 sign=below 0 & FLOW:TB5=low | up | 15.89 | 53.0 | +3.02 | +0.78 | +2.94 | 48.0 | none | 5.2 | 15.67 | +3.01 | +2.0 | +2.0 | +3.3 | hot, rep, BHY, > twins | 0 |
| 5 | 5m:NVI sign=above 0 & X:Breadth15=3 down | up | 17.85 | 52.7 | +2.66 | +0.29 | +2.49 | 47.4 | none | 8.2 | 17.43 | +2.35 | +2.6 | +2.9 | +4.3 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:KDJ_J=low & 5m:NVI sign=above 0 | up | 16.16 | 53.0 | +2.92 | +0.94 | +2.26 | 47.2 | none | 2.2 | 16.08 | +2.43 | +4.2 | +4.1 | +7.0 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:C-DEMA21 sign=below 0 & FLOW:TB15=low | up | 13.35 | 53.5 | +3.51 | +0.73 | +2.79 | 46.8 | none | 4.0 | 13.05 | +2.61 | +1.2 | +1.1 | +1.9 | hot, rep, BHY, > twins | 1 |
| 8 | 15m:HT_INPHASE sign=below 0 & X.ETH:TakerBuy=low | up | 15.51 | 53.0 | +2.93 | +0.67 | +2.19 | 45.4 | none | 4.4 | 15.51 | +2.54 | +1.5 | +1.6 | +2.5 | > twins | 0 |
| 9 | 1m:DOSC sign=below 0 & FLOW:TB15=low | up | 13.01 | 53.4 | +3.44 | +0.71 | +2.62 | 44.8 | none | 4.0 | 12.58 | +2.34 | +1.2 | +0.8 | +1.9 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:AC sign=below 0 & X.ETH:TakerBuy=low | up | 21.94 | 52.1 | +2.04 | +0.36 | +1.73 | 44.7 | none | 2.7 | 21.93 | +1.70 | +1.3 | +1.4 | +2.1 | > twins | 0 |

**SOL, triples, 60 minutes, by iheat** (twins' max 17.41):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:C-MIDPOINT14 sign=above 0 | down | 7.46 | 45.0 | -3.74 | +3.41 | -4.40 | 25.4 | none | 9.8 | 7.34 | -1.70 | -1.7 | -1.5 | -2.8 | > twins | 0 |
| 2 | 1m:KVO sign=below 0 & 1m:PVO12/26 sign=above 0 & POS:HourQ=h45-59 | up | 12.28 | 52.8 | +2.81 | +2.03 | +2.71 | 24.9 | pack | 5.9 | 12.28 | +2.47 | +2.8 | +2.7 | +4.6 | > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 5m:FOSC5 sign=above 0 | up | 21.79 | 51.2 | +1.13 | +1.12 | +1.00 | 24.4 | none | 3.7 | 21.71 | +0.64 | +0.6 | +0.3 | +0.9 | > twins | 0 |
| 4 | 60m:HT_TRENDMODE=cycle/NA & POS:HourQ=h15-29/h30-44/NA & X.BTC:RSI14=very low/low/NA | up | 4.74 | 44.9 | -5.04 | -5.10 | -6.70 | 24.2 | none | 1.9 | 4.74 | -2.24 | -7.7 | -7.7 | -12.5 | > twins | 0 |
| 5 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:C-TRIMA20 sign=above 0 | down | 8.15 | 46.1 | -2.69 | +2.63 | -3.48 | 21.5 | none | 10.6 | 7.95 | -1.64 | -2.4 | -2.2 | -4.0 | > twins | 0 |
| 6 | 1m:AROONdn25=very high & 1m:MARKETFI=low & 60m:HT_TRENDMODE=trend | up | 8.13 | 54.0 | +3.81 | +2.59 | +3.88 | 21.0 | pack | 6.4 | 8.09 | +3.66 | +5.5 | +5.1 | +9.2 | > twins | 1 |
| 7 | 1m:C-MAMA=high & POS:QPhase=m00-04 & 1m:MACDh5/35/5=high | down | 10.10 | 48.4 | -0.43 | +2.08 | -2.92 | 21.0 | pack | 3.1 | 10.10 | +0.17 | -1.5 | -1.7 | -2.5 | > twins | 0 |
| 8 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:CCI14=low | up | 7.00 | 53.2 | +3.22 | +2.92 | +2.08 | 20.5 | pack | 6.5 | 6.99 | +2.55 | +5.3 | +5.1 | +8.8 | > twins | 0 |
| 9 | 1m:KVO sign=below 0 & 1m:PVO12/26 sign=above 0 & 5m:SI sign=above 0 | down | 15.91 | 49.8 | +1.13 | -1.27 | +0.74 | 20.2 | pack | 7.8 | 15.85 | +0.36 | +0.4 | +0.7 | +0.7 | > twins | 0 |
| 10 | 1m:AROONdn25=very high & 1m:MARKETFI=low & 60m:HT_TRENDMODE=cycle | up | 4.76 | 47.0 | -3.02 | -4.19 | -6.83 | 19.9 | pack | 6.4 | 4.75 | -3.08 | -8.2 | -8.2 | -13.2 | > twins | 0 |

**SOL, triples, 60 minutes, by lheat** (twins' max 28.25):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 15m:FOSC5 sign=above 0 | down | 19.33 | 51.2 | +2.40 | -0.65 | +2.42 | 46.9 | none | 6.7 | 18.88 | +1.49 | +1.6 | +1.7 | +2.7 | > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:QSTICK10 sign=above 0 | down | 18.33 | 51.0 | +2.29 | -0.63 | +2.38 | 43.7 | none | 10.1 | 18.02 | +1.57 | +1.1 | +1.4 | +1.8 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 21.42 | 50.5 | +1.77 | -0.28 | +1.91 | 41.0 | none | 11.0 | 21.19 | +0.93 | +0.8 | +0.9 | +1.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 60m:HT_TRENDMODE=trend | up | 12.77 | 52.3 | +2.17 | +1.20 | +2.71 | 34.6 | pack | 6.8 | 12.15 | +2.03 | +1.9 | +2.2 | +3.1 | > twins | 0 |
| 5 | 15m:BOP sign=below 0 & 5m:NVI sign=above 0 & PERP:Lead5=mid/high/very high/NA | up | 16.43 | 52.1 | +2.08 | +0.15 | +2.09 | 34.3 | pack | 7.8 | 15.72 | +1.70 | +1.4 | +1.7 | +2.4 | > twins | 0 |
| 6 | 1m:KVO sign=below 0 & 1m:PVO12/26 sign=above 0 & POS:HourQ=h45-59 | up | 12.28 | 52.8 | +2.81 | +2.03 | +2.71 | 33.2 | pack | 5.9 | 12.28 | +2.47 | +2.8 | +2.7 | +4.6 | > twins | 0 |
| 7 | 1m:C-MAMA=high & POS:QPhase=m00-04 & 5m:MARKETFI sign=below 0 | down | 11.74 | 51.5 | +2.97 | -1.27 | +2.75 | 32.3 | pack | 3.1 | 11.74 | +3.06 | +1.2 | +1.0 | +2.1 | > twins | 0 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=below 0 & 60m:HT_TRENDMODE=trend | up | 13.32 | 52.0 | +1.94 | +1.08 | +2.38 | 31.7 | pack | 6.2 | 12.94 | +1.32 | +1.7 | +1.8 | +2.9 | > twins | 0 |
| 9 | 1m:AROONdn25=very high & 1m:MARKETFI=low & 60m:HT_TRENDMODE=trend | up | 8.13 | 54.0 | +3.81 | +2.59 | +3.88 | 31.5 | pack | 6.4 | 8.09 | +3.66 | +5.5 | +5.1 | +9.2 | hot, rep, > twins | 1 |
| 10 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:CMF20 sign=above 0 | down | 19.45 | 50.3 | +1.55 | -0.33 | +1.61 | 31.4 | pack | 6.6 | 18.88 | +1.33 | +1.0 | +1.3 | +1.7 | > twins | 0 |

**SOL, triples, 60 minutes, by oheat** (twins' max 25.36):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 15m:FOSC5 sign=above 0 | down | 19.33 | 51.2 | +2.40 | -0.65 | +2.42 | 46.4 | none | 6.7 | 18.88 | +1.49 | +1.6 | +1.7 | +2.7 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:DPO20 sign=below 0 | down | 19.47 | 51.1 | +2.35 | -0.80 | +2.05 | 45.8 | none | 6.7 | 19.23 | +1.44 | +1.2 | +1.1 | +1.9 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=cycle & FLOW:TB5=high | down | 13.82 | 51.7 | +3.08 | -0.41 | +1.48 | 42.5 | none | 4.9 | 13.66 | +2.72 | +2.8 | +2.9 | +4.6 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 15m:PVT sign=above 0 | down | 14.20 | 51.7 | +2.99 | -0.54 | +2.30 | 42.4 | none | 10.0 | 14.08 | +1.86 | +1.2 | +1.4 | +2.0 | hot, rep, BHY, > twins | 0 |
| 5 | 15m:CHOP14=mid/high/very high/NA & 1m:DIdiff14 sign=below 0 & 5m:NVI sign=above 0 | up | 17.30 | 52.4 | +2.36 | +0.49 | -0.03 | 40.8 | pack | 10.0 | 16.66 | +1.15 | +0.7 | +0.6 | +1.2 | hot, rep, BHY, > twins | 1 |
| 6 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:C-MIDPOINT14=high | down | 14.88 | 51.4 | +2.65 | -0.95 | +2.08 | 39.4 | pack | 6.6 | 14.74 | +2.42 | +1.5 | +1.9 | +2.6 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:ASI=high | down | 13.22 | 51.7 | +2.94 | -0.74 | +2.20 | 38.9 | pack | 6.6 | 13.02 | +2.93 | +2.6 | +2.7 | +4.4 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:CCI14=high | down | 15.81 | 51.2 | +2.45 | -0.32 | +1.54 | 38.8 | pack | 6.6 | 15.75 | +2.42 | +1.4 | +1.6 | +2.3 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & FLOW:TB5=low | up | 13.02 | 52.9 | +2.92 | +0.56 | +1.32 | 37.9 | none | 3.2 | 12.85 | +2.88 | +2.2 | +2.1 | +3.5 | > twins | 0 |
| 10 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:C-DEMA21=low | up | 15.42 | 52.5 | +2.44 | +0.75 | +1.66 | 37.6 | pack | 1.4 | 15.42 | +2.07 | +3.5 | +3.6 | +5.9 | > twins | 0 |

**SOL, triples, 60 minutes, unseen, by iheat** (twins' max 17.41):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:C-MIDPOINT14 sign=above 0 | down | 7.46 | 45.0 | -3.74 | +3.41 | -4.40 | 25.4 | none | 9.8 | 7.34 | -1.70 | -1.7 | -1.5 | -2.8 | > twins | 0 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 5m:FOSC5 sign=above 0 | up | 21.79 | 51.2 | +1.13 | +1.12 | +1.00 | 24.4 | none | 3.7 | 21.71 | +0.64 | +0.6 | +0.3 | +0.9 | > twins | 0 |
| 3 | 60m:HT_TRENDMODE=cycle/NA & POS:HourQ=h15-29/h30-44/NA & X.BTC:RSI14=very low/low/NA | up | 4.74 | 44.9 | -5.04 | -5.10 | -6.70 | 24.2 | none | 1.9 | 4.74 | -2.24 | -7.7 | -7.7 | -12.5 | > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:C-TRIMA20 sign=above 0 | down | 8.15 | 46.1 | -2.69 | +2.63 | -3.48 | 21.5 | none | 10.6 | 7.95 | -1.64 | -2.4 | -2.2 | -4.0 | > twins | 0 |
| 5 | 1m:MACDh12/26/9 sign=below 0 & 1m:CVI10 sign=above 0 & POS:HourQ=h45-59 | up | 15.41 | 52.4 | +2.31 | +1.28 | +1.73 | 19.8 | none | 6.5 | 15.41 | +0.65 | +0.1 | +0.3 | +0.2 | > twins | 0 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:KDJ_J=high | down | 18.16 | 49.1 | +0.44 | +0.97 | -0.97 | 17.6 | none | 6.7 | 18.12 | +0.66 | -0.6 | -0.5 | -1.1 | > twins | 0 |
| 7 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 1m:HT_INPHASE=low | up | 7.54 | 51.9 | +1.74 | +2.32 | +1.00 | 17.5 | none | 6.7 | 7.52 | +1.58 | +1.4 | +0.9 | +2.3 | > twins | 0 |
| 8 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & POS:QPos=m00 | up | 11.93 | 52.1 | +2.00 | +1.46 | +1.59 | 17.4 | none | 5.3 | 11.93 | +2.00 | +0.5 | -0.2 | +0.8 | none | 0 |
| 9 | 5m:FOSC5 sign=above 0 & POS:QPhase=m10-14 & 1m:DPO20 sign=above 0 | up | 20.03 | 51.1 | +0.96 | +0.85 | +0.57 | 17.1 | none | 3.1 | 20.03 | +0.33 | -0.2 | -0.3 | -0.3 | none | 0 |
| 10 | 15m:MARKETFI sign=above 0 & 1m:FOSC5=high/very high & 5m:BarBody=mid/high/very high/NA | down | 15.89 | 49.9 | +1.24 | -0.97 | +1.19 | 15.4 | none | 1.4 | 15.89 | +1.20 | +1.9 | +2.0 | +3.1 | none | 0 |

**SOL, triples, 60 minutes, unseen, by lheat** (twins' max 18.81):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 15m:FOSC5 sign=above 0 | down | 19.33 | 51.2 | +2.40 | -0.65 | +2.42 | 46.9 | none | 6.7 | 18.88 | +1.49 | +1.6 | +1.7 | +2.7 | > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:QSTICK10 sign=above 0 | down | 18.33 | 51.0 | +2.29 | -0.63 | +2.38 | 43.7 | none | 10.1 | 18.02 | +1.57 | +1.1 | +1.4 | +1.8 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:ERIbull13 sign=above 0 | down | 21.42 | 50.5 | +1.77 | -0.28 | +1.91 | 41.0 | none | 11.0 | 21.19 | +0.93 | +0.8 | +0.9 | +1.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:MACDh5/35/5 sign=below 0 | up | 16.74 | 52.0 | +1.92 | +0.39 | +1.73 | 28.9 | none | 6.8 | 16.24 | +1.33 | +1.1 | +1.3 | +1.8 | > twins | 0 |
| 5 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-ZLEMA21 sign=below 0 | up | 16.25 | 52.1 | +2.00 | +0.41 | +1.74 | 28.3 | none | 6.8 | 15.99 | +1.55 | +0.5 | +0.7 | +0.9 | hot, rep, > twins | 0 |
| 6 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 60m:EMA9>EMA21=below | up | 10.38 | 53.5 | +3.36 | +1.21 | +2.72 | 28.3 | none | 6.8 | 9.84 | +3.17 | +1.7 | +2.0 | +2.8 | hot, rep, > twins | 0 |
| 7 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:AC=low | up | 15.22 | 52.2 | +2.17 | +0.75 | +1.71 | 26.1 | none | 1.0 | 15.22 | +1.35 | +2.7 | +2.7 | +4.5 | > twins | 0 |
| 8 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:ERIbull13=low | up | 14.10 | 52.6 | +2.46 | +0.84 | +1.73 | 24.4 | none | 6.3 | 14.10 | +2.81 | +3.6 | +3.6 | +6.0 | > twins | 0 |
| 9 | 1m:AC sign=below 0 & 1m:PVO12/26=high & 5m:FOSC5 sign=below 0 | up | 12.05 | 52.2 | +2.19 | +0.60 | +1.98 | 23.9 | none | 6.7 | 11.95 | +1.70 | +0.2 | +0.0 | +0.3 | > twins | 0 |
| 10 | 1m:DX14=high & 5m:C-TEMA21 sign=above 0 & 15m:KVO sign=above 0 | down | 5.61 | 52.7 | +4.05 | -2.21 | +4.24 | 23.8 | none | 6.7 | 5.52 | +2.71 | +1.1 | +0.8 | +1.8 | hot, rep, > twins | 0 |

**SOL, triples, 60 minutes, unseen, by oheat** (twins' max 24.82):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 15m:FOSC5 sign=above 0 | down | 19.33 | 51.2 | +2.40 | -0.65 | +2.42 | 46.4 | none | 6.7 | 18.88 | +1.49 | +1.6 | +1.7 | +2.7 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 5m:DPO20 sign=below 0 | down | 19.47 | 51.1 | +2.35 | -0.80 | +2.05 | 45.8 | none | 6.7 | 19.23 | +1.44 | +1.2 | +1.1 | +1.9 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=cycle & FLOW:TB5=high | down | 13.82 | 51.7 | +3.08 | -0.41 | +1.48 | 42.5 | none | 4.9 | 13.66 | +2.72 | +2.8 | +2.9 | +4.6 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:MACDh12/26/9 sign=above 0 & 1m:CVI10 sign=above 0 & 15m:PVT sign=above 0 | down | 14.20 | 51.7 | +2.99 | -0.54 | +2.30 | 42.4 | none | 10.0 | 14.08 | +1.86 | +1.2 | +1.4 | +2.0 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & FLOW:TB5=low | up | 13.02 | 52.9 | +2.92 | +0.56 | +1.32 | 37.9 | none | 3.2 | 12.85 | +2.88 | +2.2 | +2.1 | +3.5 | > twins | 0 |
| 6 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 60m:C-SUPERTREND10/3 sign=below 0 | up | 10.78 | 53.4 | +3.32 | +1.07 | +2.54 | 35.9 | none | 6.8 | 10.20 | +3.28 | +1.8 | +2.2 | +2.9 | hot, rep, BHY, > twins | 0 |
| 7 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:ERIbull13=low | up | 14.10 | 52.6 | +2.46 | +0.84 | +1.73 | 34.7 | none | 6.3 | 14.10 | +2.81 | +3.6 | +3.6 | +6.0 | hot, rep, BHY, > twins | 0 |
| 8 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & X:Breadth15=3 down | up | 19.89 | 51.8 | +1.73 | +0.22 | +0.72 | 34.4 | none | 8.2 | 19.89 | +2.02 | +1.6 | +1.6 | +2.6 | hot, rep, BHY, > twins | 0 |
| 9 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:C-FRAMA16=low | up | 13.79 | 52.5 | +2.46 | +0.83 | +1.70 | 34.0 | none | 3.5 | 13.79 | +2.07 | +2.5 | +2.7 | +4.1 | > twins | 0 |
| 10 | 1m:C-MAMA=very low/low & PERP:BasisChg15=very low/low/mid & POS:QPos=m00/m03/m05/m07/m08/m10/m12/m14 | up | 21.00 | 51.5 | +1.48 | +0.16 | +0.38 | 31.0 | none | 0.0 | 20.91 | +1.55 | +1.1 | +1.0 | +1.8 | hot, rep, BHY, > twins | 0 |

**SOL, pairs, 240 minutes, by iheat** (twins' max 17.72):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:FISHER10 sign=below 0 & OI:PxQuad60=short covering | down | 4.48 | 51.7 | +2.51 | -3.76 | +2.86 | 16.9 | none | 4.6 | 4.37 | +1.85 | +6.6 | +6.9 | +11.0 | none | 0 |
| 2 | 1m:FISHER10=low & 1m:OBVdiv10=bull div | up | 3.27 | 46.6 | -3.70 | -4.69 | -5.36 | 15.3 | none | 3.5 | 3.26 | -2.24 | -9.6 | -9.8 | -15.4 | none | 1 |
| 3 | 5m:C-VWAP20 sign=below 0 & OI:PxQuad60=short covering | down | 4.47 | 51.2 | +2.11 | -3.36 | +2.40 | 15.0 | none | 3.8 | 4.35 | +1.68 | +2.3 | +2.3 | +3.8 | none | 1 |
| 4 | 1m:C-MCGD14 sign=below 0 & 15m:BarBody=high | down | 3.10 | 53.1 | +3.88 | -4.82 | +4.38 | 15.0 | none | 4.4 | 3.10 | +2.22 | +3.2 | +3.2 | +5.3 | none | 0 |
| 5 | 1m:STOCHK5=low & 5m:CDL:DOJI=fires | down | 3.96 | 52.1 | +2.89 | -3.73 | +3.20 | 14.8 | pack | 2.4 | 3.96 | +2.40 | +3.5 | +3.4 | +5.8 | none | 1 |
| 6 | 1m:C-RMA14=low & 15m:SWAK_HP20 sign=above 0 | up | 5.05 | 49.4 | -0.82 | -2.86 | -3.09 | 14.5 | pack | 5.2 | 5.05 | -0.73 | -5.0 | -5.1 | -8.4 | none | 4 |
| 7 | 15m:HAbody sign=below 0 & OI:PxQuad60=short covering | down | 4.62 | 51.8 | +2.63 | -3.12 | +2.78 | 14.4 | none | 4.4 | 4.50 | +2.27 | +10.5 | +10.8 | +17.6 | none | 0 |
| 8 | 1m:C-SMA50=high & 5m:PVI sign=below 0 | up | 3.47 | 55.5 | +5.33 | +4.08 | +5.07 | 14.2 | pack | 4.8 | 3.46 | +3.11 | +6.2 | +6.1 | +10.4 | none | 0 |
| 9 | 1m:C-EMA50 sign=above 0 & 5m:AROONdn14=very high | down | 2.71 | 54.0 | +4.67 | -5.21 | +4.45 | 14.1 | stored | 4.6 | 2.71 | +4.14 | +18.8 | +19.2 | +30.6 | none | 0 |
| 10 | 1m:ASI sign=above 0 & X.BTC:RSI14=low | down | 3.87 | 52.7 | +3.44 | -3.63 | +3.11 | 14.1 | none | 5.2 | 3.86 | +3.40 | +12.9 | +12.5 | +22.2 | none | 0 |

**SOL, pairs, 240 minutes, by lheat** (twins' max 21.34):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PDI14=low & 60m:HT_TRENDMODE=trend | up | 3.85 | 55.8 | +5.52 | +2.40 | +4.90 | 18.9 | pack | 2.2 | 3.84 | +4.25 | +12.5 | +12.0 | +21.1 | hot, rep | 0 |
| 2 | 1m:ERIbear13=high & 5m:C-FRAMA16 sign=below 0 | down | 4.88 | 53.1 | +4.00 | -2.86 | +3.84 | 18.8 | pack | 4.0 | 4.88 | +2.99 | +4.7 | +4.6 | +7.7 | none | 0 |
| 3 | 5m:C-LINEARREG14=low & 5m:PVO12/26 sign=below 0 | up | 4.70 | 54.2 | +4.00 | +1.96 | +3.94 | 18.5 | none | 1.2 | 4.68 | +2.53 | +5.5 | +5.4 | +9.1 | none | 0 |
| 4 | 1m:AROONOSC25=very low & 60m:HT_TRENDMODE=trend | up | 4.01 | 55.5 | +5.30 | +2.58 | +4.56 | 18.3 | pack | 3.7 | 4.01 | +5.02 | +16.7 | +16.1 | +27.8 | hot, rep | 0 |
| 5 | 1m:WT1=low & 1m:RVI14=low | up | 5.00 | 54.3 | +4.13 | +1.70 | +3.58 | 17.9 | pack | 5.2 | 4.99 | +3.33 | +8.8 | +8.7 | +14.6 | none | 0 |
| 6 | 1m:STOCH5 K>D=above & 1m:CDL:HIKKAKE=bull | up | 5.56 | 53.5 | +3.20 | +2.16 | +3.20 | 17.8 | pack | 1.9 | 5.56 | +3.20 | +8.9 | +8.6 | +14.8 | none | 0 |
| 7 | 5m:CHOP14=high & 15m:SWAK_BP20 sign=below 0 | down | 2.85 | 54.5 | +5.35 | -3.52 | +6.21 | 17.7 | none | 3.2 | 2.79 | +3.78 | +8.3 | +8.2 | +14.0 | none | 1 |
| 8 | 1m:C-SMA50=high & 5m:PVI sign=below 0 | up | 3.47 | 55.5 | +5.33 | +4.08 | +5.07 | 17.6 | pack | 4.8 | 3.46 | +3.11 | +6.2 | +6.1 | +10.4 | none | 0 |
| 9 | 1m:FISHER10=low & 1m:CDL:HIKKAKE=bull | up | 3.41 | 56.5 | +6.17 | +4.01 | +5.15 | 17.6 | pack | 3.5 | 3.41 | +6.17 | +14.4 | +14.0 | +23.8 | none | 0 |
| 10 | 1m:FISHER10=low & 5m:IMI14=low | up | 3.15 | 56.0 | +5.80 | +3.51 | +5.38 | 16.9 | none | 4.7 | 3.14 | +4.48 | +11.2 | +11.0 | +18.8 | none | 1 |

**SOL, pairs, 240 minutes, by oheat** (twins' max 19.69):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:AROONOSC25=very low & 60m:HT_TRENDMODE=trend | up | 4.01 | 55.5 | +5.30 | +2.58 | +4.56 | 21.3 | pack | 3.7 | 4.01 | +5.02 | +16.7 | +16.1 | +27.8 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:PDI14=low & 60m:HT_TRENDMODE=trend | up | 3.85 | 55.8 | +5.52 | +2.40 | +4.90 | 21.3 | pack | 2.2 | 3.84 | +4.25 | +12.5 | +12.0 | +21.1 | hot, rep, > twins | 0 |
| 3 | 1m:FISHER10=low & 1m:CDL:HIKKAKE=bull | up | 3.41 | 56.5 | +6.17 | +4.01 | +5.15 | 21.1 | pack | 3.5 | 3.41 | +6.17 | +14.4 | +14.0 | +23.8 | > twins | 0 |
| 4 | 1m:FISHER10=low & 5m:WAD=low | up | 3.36 | 56.4 | +6.16 | +3.05 | +4.77 | 20.7 | pack | 3.5 | 3.35 | +4.16 | +15.5 | +15.6 | +25.7 | > twins | 0 |
| 5 | 1m:WT1=low & 1m:RVI14=low | up | 5.00 | 54.3 | +4.13 | +1.70 | +3.58 | 20.6 | pack | 5.2 | 4.99 | +3.33 | +8.8 | +8.7 | +14.6 | > twins | 0 |
| 6 | 1m:PDI14=low & 5m:WAD=low | up | 3.30 | 56.5 | +6.21 | +2.52 | +5.07 | 20.5 | pack | 3.4 | 3.28 | +3.95 | +13.4 | +12.9 | +22.1 | > twins | 0 |
| 7 | 1m:ERIbear13=high & 5m:C-FRAMA16 sign=below 0 | down | 4.88 | 53.1 | +4.00 | -2.86 | +3.84 | 19.5 | pack | 4.0 | 4.88 | +2.99 | +4.7 | +4.6 | +7.7 | none | 0 |
| 8 | 1m:AO=low & 1m:RVI14=low | up | 5.04 | 54.0 | +3.81 | +1.22 | +2.99 | 19.2 | pack | 4.0 | 5.03 | +2.71 | +9.5 | +9.6 | +15.9 | none | 0 |
| 9 | 1m:DIdiff14=low & 60m:HT_TRENDMODE=trend | up | 4.14 | 54.8 | +4.62 | +1.75 | +4.05 | 19.1 | pack | 5.8 | 4.13 | +3.78 | +9.9 | +9.5 | +16.6 | hot, rep | 0 |
| 10 | 5m:C-LINEARREG14=low & 5m:PVO12/26 sign=below 0 | up | 4.70 | 54.2 | +4.00 | +1.96 | +3.94 | 18.8 | none | 1.2 | 4.68 | +2.53 | +5.5 | +5.4 | +9.1 | none | 0 |

**SOL, pairs, 240 minutes, unseen, by iheat** (twins' max 17.72):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:FISHER10 sign=below 0 & OI:PxQuad60=short covering | down | 4.48 | 51.7 | +2.51 | -3.76 | +2.86 | 16.9 | none | 4.6 | 4.37 | +1.85 | +6.6 | +6.9 | +11.0 | none | 0 |
| 2 | 1m:FISHER10=low & 1m:OBVdiv10=bull div | up | 3.27 | 46.6 | -3.70 | -4.69 | -5.36 | 15.3 | none | 3.5 | 3.26 | -2.24 | -9.6 | -9.8 | -15.4 | none | 1 |
| 3 | 5m:C-VWAP20 sign=below 0 & OI:PxQuad60=short covering | down | 4.47 | 51.2 | +2.11 | -3.36 | +2.40 | 15.0 | none | 3.8 | 4.35 | +1.68 | +2.3 | +2.3 | +3.8 | none | 1 |
| 4 | 1m:C-MCGD14 sign=below 0 & 15m:BarBody=high | down | 3.10 | 53.1 | +3.88 | -4.82 | +4.38 | 15.0 | none | 4.4 | 3.10 | +2.22 | +3.2 | +3.2 | +5.3 | none | 0 |
| 5 | 15m:HAbody sign=below 0 & OI:PxQuad60=short covering | down | 4.62 | 51.8 | +2.63 | -3.12 | +2.78 | 14.4 | none | 4.4 | 4.50 | +2.27 | +10.5 | +10.8 | +17.6 | none | 0 |
| 6 | 1m:ASI sign=above 0 & X.BTC:RSI14=low | down | 3.87 | 52.7 | +3.44 | -3.63 | +3.11 | 14.1 | none | 5.2 | 3.86 | +3.40 | +12.9 | +12.5 | +22.2 | none | 0 |
| 7 | 1m:KDJ_J=high & 5m:HT_QUADRATURE=high | down | 3.63 | 53.3 | +4.06 | -3.81 | +3.67 | 13.8 | none | 0.7 | 3.63 | +3.39 | +2.0 | +1.8 | +3.4 | none | 0 |
| 8 | 1m:EMV14=low & 1m:OBVdiv10=bull div | down | 4.50 | 52.2 | +3.05 | -3.06 | +3.16 | 13.8 | none | 2.0 | 4.49 | +2.11 | +11.5 | +11.5 | +19.0 | none | 0 |
| 9 | 1m:MACDh12/26/9=very low & X.ETH:Gap5=low | up | 3.51 | 46.8 | -3.30 | -3.92 | -4.79 | 13.7 | none | 2.1 | 3.50 | -2.54 | -5.5 | -5.9 | -9.2 | none | 0 |
| 10 | 1m:AROONdn25=very low & 5m:CDL:SPINNINGTOP=bull | down | 4.40 | 46.9 | -2.17 | +3.12 | -3.84 | 13.7 | none | 2.1 | 4.40 | -1.35 | -5.1 | -5.2 | -8.5 | none | 0 |

**SOL, pairs, 240 minutes, unseen, by lheat** (twins' max 21.34):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:C-LINEARREG14=low & 5m:PVO12/26 sign=below 0 | up | 4.70 | 54.2 | +4.00 | +1.96 | +3.94 | 18.5 | none | 1.2 | 4.68 | +2.53 | +5.5 | +5.4 | +9.1 | none | 0 |
| 2 | 5m:CHOP14=high & 15m:SWAK_BP20 sign=below 0 | down | 2.85 | 54.5 | +5.35 | -3.52 | +6.21 | 17.7 | none | 3.2 | 2.79 | +3.78 | +8.3 | +8.2 | +14.0 | none | 1 |
| 3 | 1m:FISHER10=low & 5m:IMI14=low | up | 3.15 | 56.0 | +5.80 | +3.51 | +5.38 | 16.9 | none | 4.7 | 3.14 | +4.48 | +11.2 | +11.0 | +18.8 | none | 1 |
| 4 | 5m:MOM10 sign=below 0 & 5m:OBVdiv10=bull div | down | 5.27 | 51.7 | +2.49 | +0.00 | +3.16 | 16.7 | none | 4.7 | 5.25 | +1.20 | +3.4 | +3.6 | +5.7 | none | 0 |
| 5 | 5m:C-ZLEMA21=low & 5m:PVO12/26 sign=below 0 | up | 4.33 | 54.1 | +3.84 | +1.54 | +3.77 | 16.3 | none | 0.9 | 4.31 | +2.81 | +7.6 | +7.3 | +12.7 | none | 0 |
| 6 | 5m:OBVdiv10=bear div & X:Breadth15=3 down | up | 4.34 | 54.3 | +4.13 | +1.99 | +3.71 | 16.1 | none | 5.4 | 4.33 | +1.74 | +5.3 | +5.4 | +8.6 | none | 0 |
| 7 | 5m:C-TSF14=low & 5m:PVO12/26 sign=below 0 | up | 4.60 | 53.8 | +3.58 | +2.12 | +3.49 | 16.0 | none | 1.1 | 4.57 | +2.12 | +6.0 | +6.0 | +10.0 | none | 0 |
| 8 | 1m:VHF28=high & 5m:HT_INPHASE sign=below 0 | up | 5.14 | 53.2 | +2.95 | +1.51 | +3.12 | 16.0 | none | 2.9 | 5.13 | +1.77 | +8.7 | +8.5 | +14.3 | none | 0 |
| 9 | 15m:MACDh5/35/5 sign=below 0 & X.XRP:RSI14=very low | up | 3.24 | 54.9 | +4.55 | +1.98 | +4.87 | 15.8 | none | 3.6 | 3.23 | +2.53 | +8.1 | +7.4 | +13.1 | none | 1 |
| 10 | 1m:SQZMOM=low & 15m:FISHER>trig=below | up | 5.21 | 52.8 | +2.60 | +1.53 | +3.02 | 15.7 | none | 3.3 | 5.17 | +1.26 | +3.0 | +3.1 | +4.9 | hot, rep | 0 |

**SOL, pairs, 240 minutes, unseen, by oheat** (twins' max 19.59):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:C-LINEARREG14=low & 5m:PVO12/26 sign=below 0 | up | 4.70 | 54.2 | +4.00 | +1.96 | +3.94 | 18.8 | none | 1.2 | 4.68 | +2.53 | +5.5 | +5.4 | +9.1 | none | 0 |
| 2 | 1m:ERIbull13=low & X.BTC:R15z=low | up | 5.07 | 53.9 | +3.63 | +1.25 | +2.80 | 18.4 | none | 4.1 | 5.07 | +3.27 | +6.2 | +5.8 | +10.3 | hot, rep | 0 |
| 3 | 1m:C-SMA50=low & 5m:SWAK_BP20 sign=above 0 | up | 4.07 | 54.8 | +4.52 | +2.84 | +3.70 | 18.4 | none | 4.5 | 4.05 | +3.86 | +7.8 | +7.4 | +12.9 | none | 0 |
| 4 | 60m:CMF20 sign=above 0 & FLOW:TB15=high | down | 3.47 | 54.5 | +5.28 | -1.60 | +2.99 | 18.3 | none | 2.1 | 3.46 | +4.56 | +5.9 | +6.2 | +10.3 | none | 0 |
| 5 | 1m:FISHER10=low & 5m:IMI14=low | up | 3.15 | 56.0 | +5.80 | +3.51 | +5.38 | 18.2 | none | 4.7 | 3.14 | +4.48 | +11.2 | +11.0 | +18.8 | none | 1 |
| 6 | 1m:RVI14=low & POS:QPos=m14 | up | 3.97 | 54.7 | +4.59 | +2.93 | +3.12 | 18.2 | none | 2.9 | 3.97 | +4.59 | +15.3 | +15.1 | +25.4 | none | 0 |
| 7 | 1m:TRIX30=low & 1m:VHF28=high | up | 2.34 | 58.0 | +7.78 | +4.61 | +6.48 | 18.2 | none | 3.5 | 2.32 | +5.90 | +22.5 | +22.7 | +36.4 | none | 0 |
| 8 | 5m:OBVdiv10=bear div & X:Breadth15=3 down | up | 4.34 | 54.3 | +4.13 | +1.99 | +3.71 | 17.9 | none | 5.4 | 4.33 | +1.74 | +5.3 | +5.4 | +8.6 | none | 0 |
| 9 | 1m:TRIX30=low & X.BTC:TakerBuy=very low | up | 2.57 | 57.0 | +6.88 | +3.82 | +5.28 | 17.7 | none | 3.5 | 2.57 | +6.13 | +18.5 | +18.3 | +30.9 | none | 0 |
| 10 | 1m:SQZMOM=low & 1m:RVI14=low | up | 5.11 | 53.6 | +3.46 | +1.08 | +2.48 | 17.7 | none | 3.3 | 5.10 | +2.22 | +7.9 | +8.1 | +13.1 | none | 0 |

**SOL, triples, 240 minutes, by iheat** (twins' max 13.30):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:Tenkan>Kijun=above & 5m:HT_TRENDMODE=trend & X.XRP:RSI14=low | down | 3.35 | 52.5 | +3.30 | -4.77 | +4.17 | 16.0 | none | 4.2 | 3.34 | +1.43 | +8.0 | +7.8 | +13.5 | > twins | 1 |
| 2 | 5m:CMOU14 sign=above 0 & 5m:HT_TRENDMODE=trend & X.XRP:RSI14=low | down | 3.05 | 52.6 | +3.39 | -5.11 | +4.31 | 15.6 | pack | 4.3 | 3.05 | +1.99 | +8.1 | +7.8 | +13.9 | > twins | 0 |
| 3 | 1m:C-MAMA=high & POS:QPhase=m00-04 & 1m:C-LINEARREG14 sign=below 0 | down | 3.35 | 53.5 | +4.28 | -4.12 | +4.47 | 13.8 | pack | 1.3 | 3.35 | +3.24 | +5.7 | +5.4 | +9.8 | > twins | 0 |
| 4 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:C-TEMA21=very high | up | 1.83 | 57.2 | +6.91 | +7.16 | +7.23 | 13.1 | none | 1.5 | 1.83 | +6.28 | +17.3 | +17.2 | +28.2 | none | 0 |
| 5 | 1m:C-MAMA=high & POS:QPhase=m00-04 & X.BTC:R5z=high | up | 4.15 | 53.2 | +2.88 | +3.11 | +3.08 | 12.9 | pack | 1.3 | 4.15 | +2.59 | +6.9 | +7.5 | +11.3 | none | 0 |
| 6 | 5m:SWAK_2PHP20 sign=below 0 & 5m:CDL:DOJI=fires & 1m:STOCHK5=low | down | 2.58 | 52.5 | +3.31 | -5.00 | +4.15 | 12.9 | pack | 2.4 | 2.58 | +2.95 | +10.2 | +10.0 | +17.1 | none | 1 |
| 7 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:RSI2=high | up | 3.77 | 52.9 | +2.69 | +3.40 | +3.03 | 12.8 | pack | 1.5 | 3.77 | +2.41 | +5.2 | +4.9 | +8.5 | none | 0 |
| 8 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:ADOSC=low | up | 4.59 | 47.9 | -2.37 | -2.69 | -3.91 | 12.3 | none | 2.4 | 4.59 | -1.19 | -0.3 | -0.6 | -0.4 | none | 0 |
| 9 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:PSO=high | down | 3.72 | 51.4 | +2.11 | -3.25 | +2.17 | 12.1 | none | 0.9 | 3.72 | +0.46 | -2.7 | -2.8 | -4.6 | none | 0 |
| 10 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:AROONup14=very high | up | 4.99 | 48.4 | -1.72 | -2.37 | -2.82 | 11.8 | pack | 5.2 | 4.99 | -0.79 | -4.1 | -4.2 | -6.8 | none | 0 |

**SOL, triples, 240 minutes, by lheat** (twins' max 15.63):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:AROONOSC25=low | up | 4.66 | 54.1 | +3.89 | +2.31 | +3.48 | 16.2 | pack | 1.9 | 4.66 | +4.76 | +14.5 | +14.5 | +23.8 | > twins | 0 |
| 2 | 1m:C-MAMA=high & POS:QPhase=m00-04 & 1m:C-LINEARREG14 sign=below 0 | down | 3.35 | 53.5 | +4.28 | -4.12 | +4.47 | 15.0 | pack | 1.3 | 3.35 | +3.24 | +5.7 | +5.4 | +9.8 | none | 0 |
| 3 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 5m:OBV sign=below 0 | up | 3.12 | 55.6 | +5.37 | +2.78 | +4.70 | 14.7 | none | 4.5 | 3.11 | +3.94 | +14.5 | +14.5 | +24.0 | none | 0 |
| 4 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:C-MIDPRICE14 sign=below 0 | up | 3.06 | 55.4 | +5.21 | +3.00 | +4.57 | 14.0 | none | 3.3 | 3.06 | +4.02 | +11.1 | +11.2 | +18.1 | none | 0 |
| 5 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 15m:C-MEDPRICE sign=below 0 | up | 5.68 | 52.7 | +2.52 | +1.22 | +2.46 | 14.0 | none | 1.5 | 5.68 | +2.49 | +5.8 | +5.7 | +9.5 | none | 0 |
| 6 | 1m:PVO12/26=high & X.BTC:Gap5=low & 5m:DPO20 sign=above 0 | up | 3.37 | 54.3 | +3.99 | +1.92 | +4.13 | 13.9 | none | 2.5 | 3.37 | +2.03 | +4.4 | +4.8 | +7.3 | none | 0 |
| 7 | 5m:Tenkan>Kijun=above & 5m:HT_TRENDMODE=trend & X.XRP:RSI14=low | down | 3.35 | 52.5 | +3.30 | -4.77 | +4.17 | 13.9 | none | 4.2 | 3.34 | +1.43 | +8.0 | +7.8 | +13.5 | none | 1 |
| 8 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:HT_INPHASE sign=below 0 | up | 3.60 | 54.8 | +4.49 | +2.65 | +3.87 | 13.9 | none | 3.3 | 3.59 | +3.86 | +13.1 | +12.6 | +21.9 | none | 0 |
| 9 | 1m:KVO sign=above 0 & 1m:PVO12/26 sign=above 0 & FLOW:TB15=high | down | 5.02 | 52.1 | +2.92 | -1.16 | +2.72 | 13.6 | pack | 4.6 | 4.99 | +2.47 | +3.3 | +3.5 | +5.5 | none | 0 |
| 10 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:C-TEMA21=very high | up | 1.83 | 57.2 | +6.91 | +7.16 | +7.23 | 13.2 | none | 1.5 | 1.83 | +6.28 | +17.3 | +17.2 | +28.2 | none | 0 |

**SOL, triples, 240 minutes, by oheat** (twins' max 17.30):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:RVI14=low | up | 5.27 | 53.7 | +3.50 | +1.17 | +2.39 | 18.4 | none | 2.9 | 5.27 | +3.28 | +8.4 | +8.4 | +14.0 | > twins | 0 |
| 2 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:AROONOSC25=low | up | 4.66 | 54.1 | +3.89 | +2.31 | +3.48 | 18.1 | pack | 1.9 | 4.66 | +4.76 | +14.5 | +14.5 | +23.8 | hot, rep, > twins | 0 |
| 3 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:MASSI=low | up | 3.12 | 55.4 | +5.38 | +2.70 | +4.11 | 16.8 | none | 0.7 | 3.12 | +4.83 | +15.4 | +15.3 | +25.2 | none | 0 |
| 4 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 5m:OBV sign=below 0 | up | 3.12 | 55.6 | +5.37 | +2.78 | +4.70 | 16.7 | none | 4.5 | 3.11 | +3.94 | +14.5 | +14.5 | +24.0 | none | 0 |
| 5 | 1m:AC sign=below 0 & 1m:PVO12/26=high & 60m:PVI sign=below 0 | up | 3.58 | 54.8 | +4.55 | +1.66 | +2.83 | 16.3 | pack | 4.3 | 3.58 | +3.17 | +6.0 | +5.6 | +9.9 | hot, rep | 0 |
| 6 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:HT_INPHASE sign=below 0 | up | 3.60 | 54.8 | +4.49 | +2.65 | +3.87 | 16.2 | none | 3.3 | 3.59 | +3.86 | +13.1 | +12.6 | +21.9 | none | 0 |
| 7 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:C-MIDPRICE14 sign=below 0 | up | 3.06 | 55.4 | +5.21 | +3.00 | +4.57 | 16.0 | none | 3.3 | 3.06 | +4.02 | +11.1 | +11.2 | +18.1 | none | 0 |
| 8 | 1m:MASSI=low & 5m:WT1>WT2=below & 60m:C-KAMA30 sign=below 0 | up | 1.93 | 58.4 | +8.26 | +1.51 | +6.28 | 15.9 | pack | 4.8 | 1.90 | +6.28 | +17.8 | +17.7 | +27.8 | none | 0 |
| 9 | 1m:AROONdn14=very high & 1m:MARKETFI=low & 5m:WAD=low | up | 2.63 | 56.4 | +6.05 | +3.12 | +4.11 | 15.9 | pack | 4.3 | 2.63 | +5.38 | +10.9 | +10.3 | +18.3 | hot, rep | 1 |
| 10 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:RVI14=low | up | 5.24 | 53.2 | +3.03 | +0.83 | +2.51 | 15.9 | none | 5.2 | 5.22 | +2.65 | +6.8 | +6.9 | +11.3 | hot, rep | 0 |

**SOL, triples, 240 minutes, unseen, by iheat** (twins' max 12.70):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:Tenkan>Kijun=above & 5m:HT_TRENDMODE=trend & X.XRP:RSI14=low | down | 3.35 | 52.5 | +3.30 | -4.77 | +4.17 | 16.0 | none | 4.2 | 3.34 | +1.43 | +8.0 | +7.8 | +13.5 | > twins | 1 |
| 2 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:C-TEMA21=very high | up | 1.83 | 57.2 | +6.91 | +7.16 | +7.23 | 13.1 | none | 1.5 | 1.83 | +6.28 | +17.3 | +17.2 | +28.2 | > twins | 0 |
| 3 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:ADOSC=low | up | 4.59 | 47.9 | -2.37 | -2.69 | -3.91 | 12.3 | none | 2.4 | 4.59 | -1.19 | -0.3 | -0.6 | -0.4 | none | 0 |
| 4 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:C-ZLEMA21=very high | up | 1.55 | 57.7 | +7.50 | +7.94 | +7.81 | 12.3 | none | 1.5 | 1.55 | +6.41 | +18.5 | +18.8 | +29.8 | none | 0 |
| 5 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:PSO=high | down | 3.72 | 51.4 | +2.11 | -3.25 | +2.17 | 12.1 | none | 0.9 | 3.72 | +0.46 | -2.7 | -2.8 | -4.6 | none | 0 |
| 6 | 5m:Tenkan>Kijun=above & 5m:HT_TRENDMODE=trend & 15m:C-HT_TRENDLINE sign=below 0 | down | 1.75 | 55.2 | +5.97 | -6.63 | +6.17 | 11.6 | none | 4.6 | 1.69 | +2.19 | +8.6 | +8.0 | +14.4 | none | 0 |
| 7 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 15m:FOSC5=low | up | 3.11 | 54.2 | +3.97 | +3.57 | +3.70 | 11.1 | none | 3.5 | 3.11 | +2.90 | +14.5 | +13.9 | +23.9 | none | 0 |
| 8 | 5m:SWAK_2PHP20 sign=above 0 & 5m:CDL:DOJI=fires & 1m:C-TSF14=high | up | 2.16 | 54.7 | +4.41 | +5.10 | +4.51 | 11.0 | none | 2.4 | 2.16 | +3.89 | +17.5 | +16.7 | +28.6 | none | 0 |
| 9 | 5m:Tenkan>Kijun=above & 5m:HT_TRENDMODE=trend & 1m:C-SMA200 sign=below 0 | up | 2.51 | 47.1 | -3.14 | -4.29 | -3.95 | 10.8 | none | 5.0 | 2.49 | -1.20 | -3.5 | -3.9 | -5.9 | none | 0 |
| 10 | 1m:C-EMA50 sign=below 0 & 1m:NATR14=low & OI:PxQuad60=new longs | up | 1.32 | 59.8 | +9.59 | +8.00 | +8.51 | 10.6 | none | 2.1 | 1.29 | +7.79 | +10.2 | +10.0 | +16.7 | none | 0 |

**SOL, triples, 240 minutes, unseen, by lheat** (twins' max 14.00):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 5m:OBV sign=below 0 | up | 3.12 | 55.6 | +5.37 | +2.78 | +4.70 | 14.7 | none | 4.5 | 3.11 | +3.94 | +14.5 | +14.5 | +24.0 | > twins | 0 |
| 2 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:C-MIDPRICE14 sign=below 0 | up | 3.06 | 55.4 | +5.21 | +3.00 | +4.57 | 14.0 | none | 3.3 | 3.06 | +4.02 | +11.1 | +11.2 | +18.1 | > twins | 0 |
| 3 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 15m:C-MEDPRICE sign=below 0 | up | 5.68 | 52.7 | +2.52 | +1.22 | +2.46 | 14.0 | none | 1.5 | 5.68 | +2.49 | +5.8 | +5.7 | +9.5 | none | 0 |
| 4 | 1m:PVO12/26=high & X.BTC:Gap5=low & 5m:DPO20 sign=above 0 | up | 3.37 | 54.3 | +3.99 | +1.92 | +4.13 | 13.9 | none | 2.5 | 3.37 | +2.03 | +4.4 | +4.8 | +7.3 | none | 0 |
| 5 | 5m:Tenkan>Kijun=above & 5m:HT_TRENDMODE=trend & X.XRP:RSI14=low | down | 3.35 | 52.5 | +3.30 | -4.77 | +4.17 | 13.9 | none | 4.2 | 3.34 | +1.43 | +8.0 | +7.8 | +13.5 | none | 1 |
| 6 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:HT_INPHASE sign=below 0 | up | 3.60 | 54.8 | +4.49 | +2.65 | +3.87 | 13.9 | none | 3.3 | 3.59 | +3.86 | +13.1 | +12.6 | +21.9 | none | 0 |
| 7 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & 1m:C-TEMA21=very high | up | 1.83 | 57.2 | +6.91 | +7.16 | +7.23 | 13.2 | none | 1.5 | 1.83 | +6.28 | +17.3 | +17.2 | +28.2 | none | 0 |
| 8 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:RVI14=low | up | 5.24 | 53.2 | +3.03 | +0.83 | +2.51 | 13.2 | none | 5.2 | 5.22 | +2.65 | +6.8 | +6.9 | +11.3 | none | 0 |
| 9 | 1m:C-EMA50 sign=below 0 & 1m:NATR14=low & 60m:STOCH5 K>D=above | up | 2.18 | 56.2 | +6.01 | +3.56 | +6.01 | 13.1 | none | 1.6 | 2.14 | +5.18 | +10.6 | +10.7 | +16.9 | none | 0 |
| 10 | 1m:LRSLOPE14 sign=below 0 & POS:HourQ=h00-14 & FLOW:TB5=low | down | 4.52 | 51.9 | +2.71 | -2.42 | +2.89 | 13.1 | none | 1.5 | 4.52 | +2.29 | +6.4 | +6.7 | +10.3 | none | 0 |

**SOL, triples, 240 minutes, unseen, by oheat** (twins' max 17.30):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:RVI14=low | up | 5.27 | 53.7 | +3.50 | +1.17 | +2.39 | 18.4 | none | 2.9 | 5.27 | +3.28 | +8.4 | +8.4 | +14.0 | > twins | 0 |
| 2 | 5m:FOSC5 sign=below 0 & POS:QPhase=m10-14 & 1m:MASSI=low | up | 3.12 | 55.4 | +5.38 | +2.70 | +4.11 | 16.8 | none | 0.7 | 3.12 | +4.83 | +15.4 | +15.3 | +25.2 | none | 0 |
| 3 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 5m:OBV sign=below 0 | up | 3.12 | 55.6 | +5.37 | +2.78 | +4.70 | 16.7 | none | 4.5 | 3.11 | +3.94 | +14.5 | +14.5 | +24.0 | none | 0 |
| 4 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:HT_INPHASE sign=below 0 | up | 3.60 | 54.8 | +4.49 | +2.65 | +3.87 | 16.2 | none | 3.3 | 3.59 | +3.86 | +13.1 | +12.6 | +21.9 | none | 0 |
| 5 | 1m:VHF28=high & 5m:C-TSF14 sign=above 0 & 1m:C-MIDPRICE14 sign=below 0 | up | 3.06 | 55.4 | +5.21 | +3.00 | +4.57 | 16.0 | none | 3.3 | 3.06 | +4.02 | +11.1 | +11.2 | +18.1 | none | 0 |
| 6 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:RVI14=low | up | 5.24 | 53.2 | +3.03 | +0.83 | +2.51 | 15.9 | none | 5.2 | 5.22 | +2.65 | +6.8 | +6.9 | +11.3 | hot, rep | 0 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 5m:OBVdiv10=bull div | down | 4.60 | 52.5 | +3.32 | -0.81 | +1.29 | 15.3 | none | 1.6 | 4.59 | +2.55 | +5.8 | +6.0 | +9.6 | none | 0 |
| 8 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=cycle & 5m:CDL:SPINNINGTOP=bull | down | 5.34 | 52.0 | +2.84 | -1.15 | +2.37 | 15.2 | none | 1.9 | 5.34 | +2.15 | +5.3 | +5.0 | +8.7 | none | 0 |
| 9 | 1m:AC sign=below 0 & 1m:PVO12/26=high & 60m:DIdiff14 sign=below 0 | up | 3.50 | 54.6 | +4.30 | +1.88 | +3.09 | 15.1 | none | 3.4 | 3.50 | +2.78 | +6.8 | +6.6 | +11.0 | hot, rep | 0 |
| 10 | 1m:STC=very low/low & 1m:SWAK_BP20 sign=above 0 & 60m:NVI sign=above 0 | up | 3.80 | 54.2 | +3.95 | +2.40 | +2.05 | 15.0 | none | 0.9 | 3.79 | +3.46 | +7.2 | +7.3 | +11.9 | none | 0 |

**XRP, pairs, 15 minutes, by iheat** (twins' max 47.01):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-MIDPOINT14 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 63.26 | 51.3 | +2.02 | -1.27 | +1.44 | 80.3 | pack | 15.4 | 54.61 | +0.31 | +0.0 | +0.3 | +0.1 | hot, rep, > twins | 8 |
| 2 | 1m:C-VWAP20 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 60.69 | 52.0 | +3.03 | +1.31 | +2.99 | 79.8 | pack | 16.0 | 50.84 | +1.30 | +0.8 | +0.8 | +2.0 | hot, rep, > twins | 12 |
| 3 | 1m:CCI20 sign=above 0 & 1m:HT_TRENDMODE=trend | down | 57.68 | 51.6 | +2.32 | -1.31 | +1.52 | 75.5 | pack | 18.0 | 46.39 | +0.88 | -0.0 | +0.2 | -0.0 | hot, rep, > twins | 1 |
| 4 | 1m:C-LINEARREG14 sign=above 0 & POS:QPhase=m00-04 | down | 79.87 | 48.4 | -0.86 | +0.88 | -1.83 | 70.4 | none | 1.7 | 79.87 | -0.17 | -0.0 | +0.1 | -0.0 | > twins | 1 |
| 5 | 1m:C-LINEARREG14 sign=below 0 & POS:QPhase=m00-04 | up | 80.67 | 48.1 | -0.97 | -0.86 | -1.83 | 69.4 | none | 2.4 | 80.67 | -0.46 | -0.3 | -0.1 | -0.6 | > twins | 1 |
| 6 | 1m:ER10=low & 1m:C-SWAK_GAUSS20 sign=above 0 | down | 44.08 | 48.7 | -0.57 | +1.55 | -1.53 | 68.3 | none | 13.2 | 43.57 | -0.53 | +0.2 | +0.4 | +0.5 | > twins | 0 |
| 7 | 1m:ER10=low & 1m:C-SWAK_GAUSS20 sign=below 0 | down | 43.43 | 50.2 | +0.92 | -1.57 | +1.49 | 68.3 | none | 13.8 | 42.96 | +0.98 | +0.9 | +0.7 | +2.1 | > twins | 0 |
| 8 | 1m:ER10=low & 1m:MACDh5/35/5 sign=above 0 | up | 41.05 | 50.2 | +1.21 | +1.66 | +1.64 | 68.2 | none | 4.3 | 40.54 | +1.07 | -0.3 | -0.4 | -0.6 | hot, rep, > twins | 0 |
| 9 | 1m:HT_SINE=low & 1m:SINE>LEAD=above | down | 18.93 | 48.9 | -0.28 | +3.28 | -1.82 | 62.1 | none | 17.5 | 18.84 | -0.50 | +0.2 | +0.3 | +0.6 | hot, rep, > twins | 0 |
| 10 | 1m:HT_INPHASE sign=above 0 & POS:QPhase=m05-09 | down | 75.16 | 49.3 | +0.06 | +0.82 | -1.16 | 61.7 | none | 11.1 | 75.16 | +0.17 | -0.0 | -0.1 | -0.0 | > twins | 0 |

**XRP, pairs, 15 minutes, by lheat** (twins' max 84.51):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-MIDPOINT14 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 63.68 | 51.8 | +2.84 | +1.25 | +2.88 | 183.7 | pack | 16.0 | 54.59 | +0.81 | +0.2 | +0.3 | +0.5 | hot, rep, BHY, > twins | 9 |
| 2 | 1m:PVT sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 61.73 | 51.5 | +2.25 | -0.14 | +2.89 | 178.5 | pack | 16.8 | 48.18 | +0.82 | +0.6 | +0.8 | +1.5 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:QSTICK10 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 63.88 | 51.8 | +2.80 | +1.17 | +2.73 | 174.5 | pack | 13.6 | 54.79 | +0.62 | +0.2 | +0.3 | +0.4 | hot, rep, BHY, > twins | 3 |
| 4 | 1m:CCI20 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 58.05 | 52.1 | +3.14 | +1.29 | +2.94 | 170.7 | pack | 18.7 | 46.23 | +1.19 | +0.6 | +0.6 | +1.4 | hot, rep, BHY, > twins | 4 |
| 5 | 1m:PSO sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 58.52 | 51.4 | +2.19 | -0.04 | +2.78 | 162.6 | pack | 16.8 | 37.87 | +0.78 | +0.3 | +0.4 | +0.7 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-VWAP20 sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 59.49 | 51.4 | +2.17 | -0.04 | +2.73 | 162.2 | pack | 16.8 | 44.88 | +0.78 | +0.4 | +0.5 | +0.9 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:ERIbear13 sign=below 0 & X:Breadth15=3 down | up | 67.23 | 51.1 | +2.11 | +0.09 | +2.33 | 156.9 | none | 16.1 | 53.41 | +0.57 | -0.0 | +0.3 | -0.0 | hot, rep, BHY, > twins | 2 |
| 8 | 1m:ERIbull13 sign=below 0 & 1m:ERIbear13 sign=below 0 | up | 76.84 | 50.8 | +1.87 | -0.00 | +2.04 | 156.4 | none | 19.7 | 66.46 | +0.73 | +0.3 | +0.4 | +0.7 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:ERIbull13 sign=above 0 & 5m:Ichimoku=above cloud | down | 45.74 | 51.9 | +2.63 | -0.29 | +3.21 | 146.9 | none | 20.2 | 32.55 | +0.95 | -0.3 | -0.2 | -0.6 | hot, rep, BHY, > twins | 1 |
| 10 | 1m:PVT sign=above 0 & 5m:SMI sign=above 0 | down | 48.41 | 52.1 | +2.84 | -0.28 | +3.14 | 146.0 | none | 16.7 | 37.07 | +1.17 | +0.5 | +0.6 | +1.1 | hot, rep, BHY, > twins | 4 |

**XRP, pairs, 15 minutes, by oheat** (twins' max 72.69):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-SMA20 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 59.78 | 52.1 | +3.12 | +1.30 | +2.96 | 186.6 | pack | 18.1 | 49.23 | +1.16 | +0.6 | +0.7 | +1.5 | hot, rep, BHY, > twins | 12 |
| 2 | 1m:ERIbull13 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 47.69 | 52.8 | +3.82 | +1.55 | +3.41 | 182.3 | pack | 19.7 | 42.27 | +2.31 | +1.2 | +1.3 | +2.9 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:QSTICK10 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 63.88 | 51.8 | +2.80 | +1.17 | +2.73 | 179.0 | pack | 13.6 | 54.79 | +0.62 | +0.2 | +0.3 | +0.4 | hot, rep, BHY, > twins | 3 |
| 4 | 1m:C-EMA50 sign=above 0 & 1m:PVT sign=above 0 | down | 69.61 | 51.5 | +2.28 | -0.20 | +2.11 | 158.8 | none | 23.2 | 54.16 | +0.64 | +0.3 | +0.5 | +0.8 | hot, rep, BHY, > twins | 9 |
| 5 | 1m:ERIbull13 sign=below 0 & X:Breadth15=3 down | up | 57.41 | 51.8 | +2.75 | +0.20 | +2.31 | 157.9 | none | 19.7 | 49.30 | +1.76 | +0.6 | +0.7 | +1.3 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:HAbody sign=above 0 & 5m:C-SWAK_GAUSS20 sign=above 0 | down | 65.17 | 51.6 | +2.41 | -0.17 | +1.36 | 157.2 | none | 20.8 | 60.97 | +1.59 | +0.6 | +0.8 | +1.4 | hot, rep, BHY, > twins | 10 |
| 7 | 1m:AROONOSC25 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 62.26 | 51.7 | +2.50 | -0.15 | +1.99 | 155.8 | none | 21.7 | 54.44 | +1.25 | +0.4 | +0.5 | +1.0 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-FRAMA16 sign=above 0 & 5m:C-SWAK_GAUSS20 sign=above 0 | down | 65.11 | 51.6 | +2.37 | -0.12 | +1.54 | 154.4 | none | 20.8 | 57.08 | +1.15 | +0.4 | +0.6 | +0.8 | hot, rep, BHY, > twins | 11 |
| 9 | 1m:COPPOCK sign=above 0 & 1m:HAbody sign=above 0 | down | 69.17 | 51.4 | +2.23 | -0.10 | +1.25 | 154.3 | none | 19.1 | 63.93 | +1.32 | +0.6 | +0.7 | +1.5 | hot, rep, BHY, > twins | 4 |
| 10 | 1m:C-EMA50 sign=above 0 & 1m:ADOSC sign=above 0 | down | 67.33 | 51.5 | +2.29 | -0.23 | +1.84 | 153.9 | none | 23.2 | 51.22 | +0.74 | +0.2 | +0.5 | +0.4 | hot, rep, BHY, > twins | 17 |

**XRP, pairs, 15 minutes, unseen, by iheat** (twins' max 47.01):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ERIbull13 sign=below 0 & 1m:HT_TRENDMODE=cycle | up | 60.74 | 49.4 | +0.41 | -1.16 | -3.41 | 70.5 | none | 19.7 | 52.96 | -0.02 | -0.1 | +0.0 | -0.2 | hot, rep, > twins | 0 |
| 2 | 1m:C-LINEARREG14 sign=above 0 & POS:QPhase=m00-04 | down | 79.87 | 48.4 | -0.86 | +0.88 | -1.83 | 70.4 | none | 1.7 | 79.87 | -0.17 | -0.0 | +0.1 | -0.0 | > twins | 1 |
| 3 | 1m:ERIbear13 sign=above 0 & 1m:HT_TRENDMODE=cycle | down | 61.89 | 50.1 | +0.88 | +1.13 | -1.98 | 70.2 | none | 17.2 | 53.51 | +0.48 | +0.2 | +0.2 | +0.6 | hot, rep, > twins | 0 |
| 4 | 1m:C-LINEARREG14 sign=below 0 & POS:QPhase=m00-04 | up | 80.67 | 48.1 | -0.97 | -0.86 | -1.83 | 69.4 | none | 2.4 | 80.67 | -0.46 | -0.3 | -0.1 | -0.6 | > twins | 1 |
| 5 | 1m:ER10=low & 1m:C-SWAK_GAUSS20 sign=above 0 | down | 44.08 | 48.7 | -0.57 | +1.55 | -1.53 | 68.3 | none | 13.2 | 43.57 | -0.53 | +0.2 | +0.4 | +0.5 | > twins | 0 |
| 6 | 1m:ER10=low & 1m:C-SWAK_GAUSS20 sign=below 0 | down | 43.43 | 50.2 | +0.92 | -1.57 | +1.49 | 68.3 | none | 13.8 | 42.96 | +0.98 | +0.9 | +0.7 | +2.1 | > twins | 0 |
| 7 | 1m:ER10=low & 1m:MACDh5/35/5 sign=above 0 | up | 41.05 | 50.2 | +1.21 | +1.66 | +1.64 | 68.2 | none | 4.3 | 40.54 | +1.07 | -0.3 | -0.4 | -0.6 | hot, rep, > twins | 0 |
| 8 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle | up | 72.42 | 49.2 | +0.24 | -0.93 | -2.92 | 67.0 | none | 18.7 | 59.37 | -0.19 | -0.3 | -0.3 | -0.8 | hot, rep, > twins | 0 |
| 9 | 1m:HT_SINE=low & 1m:SINE>LEAD=above | down | 18.93 | 48.9 | -0.28 | +3.28 | -1.82 | 62.1 | none | 17.5 | 18.84 | -0.50 | +0.2 | +0.3 | +0.6 | hot, rep, > twins | 0 |
| 10 | 1m:HT_INPHASE sign=above 0 & POS:QPhase=m05-09 | down | 75.16 | 49.3 | +0.06 | +0.82 | -1.16 | 61.7 | none | 11.1 | 75.16 | +0.17 | -0.0 | -0.1 | -0.0 | > twins | 0 |

**XRP, pairs, 15 minutes, unseen, by lheat** (twins' max 84.51):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ERIbear13 sign=below 0 & X:Breadth15=3 down | up | 67.23 | 51.1 | +2.11 | +0.09 | +2.33 | 156.9 | none | 16.1 | 53.41 | +0.57 | -0.0 | +0.3 | -0.0 | hot, rep, BHY, > twins | 2 |
| 2 | 1m:ERIbull13 sign=below 0 & 1m:ERIbear13 sign=below 0 | up | 76.84 | 50.8 | +1.87 | -0.00 | +2.04 | 156.4 | none | 19.7 | 66.46 | +0.73 | +0.3 | +0.4 | +0.7 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:ERIbull13 sign=above 0 & 5m:Ichimoku=above cloud | down | 45.74 | 51.9 | +2.63 | -0.29 | +3.21 | 146.9 | none | 20.2 | 32.55 | +0.95 | -0.3 | -0.2 | -0.6 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:PVT sign=above 0 & 5m:SMI sign=above 0 | down | 48.41 | 52.1 | +2.84 | -0.28 | +3.14 | 146.0 | none | 16.7 | 37.07 | +1.17 | +0.5 | +0.6 | +1.1 | hot, rep, BHY, > twins | 4 |
| 5 | 1m:TRIX30 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 51.60 | 52.0 | +2.75 | -0.29 | +2.80 | 144.4 | none | 19.4 | 46.28 | +1.57 | +0.7 | +0.7 | +1.7 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:ERIbull13 sign=above 0 & 5m:CORRELcv30 sign=above 0 | down | 46.95 | 51.8 | +2.56 | -0.24 | +3.05 | 143.1 | none | 16.7 | 34.68 | +0.67 | +0.1 | -0.0 | +0.2 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:ADOSC sign=above 0 & 5m:AO sign=above 0 | down | 44.91 | 52.1 | +2.87 | -0.44 | +3.10 | 139.3 | none | 18.8 | 33.02 | +1.13 | +0.3 | +0.5 | +0.7 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:C-FRAMA16 sign=above 0 & 15m:C-MCGD14 sign=above 0 | down | 48.03 | 52.0 | +2.75 | -0.34 | +2.89 | 138.8 | none | 20.5 | 43.25 | +1.24 | +0.3 | +0.4 | +0.7 | hot, rep, BHY, > twins | 1 |
| 9 | 1m:CCI20 sign=above 0 & 5m:Ichimoku=above cloud | down | 41.63 | 52.3 | +3.09 | -0.37 | +3.31 | 138.0 | none | 20.2 | 27.82 | +1.75 | +0.6 | +0.7 | +1.3 | hot, rep, BHY, > twins | 3 |
| 10 | 1m:TRIX30 sign=above 0 & 1m:PVT sign=above 0 | down | 49.04 | 52.0 | +2.80 | -0.28 | +3.09 | 137.9 | none | 19.4 | 37.66 | +1.31 | +0.4 | +0.5 | +1.1 | hot, rep, BHY, > twins | 0 |

**XRP, pairs, 15 minutes, unseen, by oheat** (twins' max 72.69):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-EMA50 sign=above 0 & 1m:PVT sign=above 0 | down | 69.61 | 51.5 | +2.28 | -0.20 | +2.11 | 158.8 | none | 23.2 | 54.16 | +0.64 | +0.3 | +0.5 | +0.8 | hot, rep, BHY, > twins | 9 |
| 2 | 1m:ERIbull13 sign=below 0 & X:Breadth15=3 down | up | 57.41 | 51.8 | +2.75 | +0.20 | +2.31 | 157.9 | none | 19.7 | 49.30 | +1.76 | +0.6 | +0.7 | +1.3 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:HAbody sign=above 0 & 5m:C-SWAK_GAUSS20 sign=above 0 | down | 65.17 | 51.6 | +2.41 | -0.17 | +1.36 | 157.2 | none | 20.8 | 60.97 | +1.59 | +0.6 | +0.8 | +1.4 | hot, rep, BHY, > twins | 8 |
| 4 | 1m:AROONOSC25 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 62.26 | 51.7 | +2.50 | -0.15 | +1.99 | 155.8 | none | 21.7 | 54.44 | +1.25 | +0.4 | +0.5 | +1.0 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:C-FRAMA16 sign=above 0 & 5m:C-SWAK_GAUSS20 sign=above 0 | down | 65.11 | 51.6 | +2.37 | -0.12 | +1.54 | 154.4 | none | 20.8 | 57.08 | +1.15 | +0.4 | +0.6 | +0.8 | hot, rep, BHY, > twins | 11 |
| 6 | 1m:COPPOCK sign=above 0 & 1m:HAbody sign=above 0 | down | 69.17 | 51.4 | +2.23 | -0.10 | +1.25 | 154.3 | none | 19.1 | 63.93 | +1.32 | +0.6 | +0.7 | +1.5 | hot, rep, BHY, > twins | 3 |
| 7 | 1m:C-EMA50 sign=above 0 & 1m:ADOSC sign=above 0 | down | 67.33 | 51.5 | +2.29 | -0.23 | +1.84 | 153.9 | none | 23.2 | 51.22 | +0.74 | +0.2 | +0.5 | +0.4 | hot, rep, BHY, > twins | 17 |
| 8 | 1m:ERIbull13 sign=below 0 & 1m:LRSLOPE14 sign=below 0 | up | 71.49 | 51.1 | +2.15 | +0.08 | +1.73 | 153.8 | none | 19.7 | 59.88 | +1.23 | +0.6 | +0.7 | +1.3 | hot, rep, BHY, > twins | 10 |
| 9 | 1m:C-FRAMA16 sign=below 0 & X:Breadth15=3 down | up | 63.55 | 51.4 | +2.40 | +0.14 | +1.87 | 152.6 | none | 15.1 | 57.24 | +0.96 | -0.1 | +0.2 | -0.2 | hot, rep, BHY, > twins | 2 |
| 10 | 1m:AROONOSC25 sign=above 0 & 1m:PVT sign=above 0 | down | 61.98 | 51.7 | +2.45 | -0.13 | +2.16 | 152.0 | none | 21.7 | 46.82 | +1.02 | +0.5 | +0.5 | +1.3 | hot, rep, BHY, > twins | 0 |

**XRP, triples, 15 minutes, by iheat** (twins' max 26.62):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:LRSLOPE14 sign=above 0 | up | 38.33 | 48.7 | -0.26 | +2.18 | -0.62 | 83.4 | none | 17.0 | 35.92 | +0.07 | -0.3 | -0.3 | -0.7 | hot, rep, > twins | 0 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:CMOU14 sign=above 0 | down | 41.34 | 49.7 | +0.41 | +1.81 | -1.21 | 74.7 | none | 17.4 | 39.33 | +0.36 | +0.5 | +0.5 | +1.2 | hot, rep, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:QSTICK10 sign=above 0 | up | 47.51 | 49.0 | -0.03 | +1.55 | -0.38 | 73.6 | none | 12.7 | 44.32 | +0.07 | -0.4 | -0.4 | -0.9 | hot, rep, > twins | 0 |
| 4 | 15m:C-HT_TRENDLINE sign=above 0 & 1m:C-SUPERTREND10/3=low/high/NA & 1m:KVO sign=below 0 | up | 26.72 | 50.3 | +1.37 | +1.86 | -1.20 | 49.7 | pack | 20.1 | 26.50 | +0.89 | +1.1 | +1.0 | +2.6 | hot, rep, > twins | 0 |
| 5 | 1m:C-T3_5=very low/low & 1m:DX14=very low/low/mid/NA & 1m:ERIbull13 sign=below 0/NA | up | 44.27 | 49.7 | +0.76 | -1.05 | -3.38 | 46.5 | pack | 19.7 | 43.01 | +0.86 | +0.0 | +0.0 | +0.1 | hot, rep, > twins | 0 |
| 6 | 15m:C-SMA200=very low/low/mid & 1m:C-MAMA=very low/low/high/very high/NA & 1m:HAbody sign=below 0 | up | 46.94 | 50.7 | +1.74 | +0.98 | -1.59 | 46.0 | pack | 12.6 | 45.16 | +2.04 | +0.9 | +0.8 | +2.2 | hot, rep, > twins | 0 |
| 7 | 1m:DX14=high/very high & 1m:EMV14=mid/high/very high & 1m:ERIbull13 sign=below 0/NA | up | 10.83 | 54.8 | +5.81 | +4.19 | +2.45 | 45.4 | pack | 19.7 | 9.69 | +4.63 | +2.7 | +2.4 | +6.5 | hot, rep, > twins | 0 |
| 8 | 1m:CVI10 sign=above 0 & 5m:SWAK_2PHP20 sign=below 0 & 1m:ASI sign=above 0 | down | 30.88 | 51.5 | +2.21 | -1.41 | +1.07 | 43.6 | pack | 16.1 | 30.73 | +1.40 | +0.6 | +0.5 | +1.4 | hot, rep, > twins | 2 |
| 9 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 1m:DX14=high | up | 13.94 | 53.6 | +4.56 | +3.07 | +3.61 | 42.8 | pack | 10.1 | 12.83 | +3.71 | +1.9 | +1.6 | +4.4 | hot, rep, > twins | 0 |
| 10 | 1m:C-SWAK_BUTTER20 sign=below 0/NA & POS:QPos=m00/m09/m10/m13/m14 & Weekday=Wed/Thu/Sat/Sun/NA | up | 48.90 | 50.9 | +1.93 | +0.86 | +0.99 | 42.0 | pack | 14.3 | 43.80 | +1.32 | +0.6 | +0.5 | +1.3 | > twins | 0 |

**XRP, triples, 15 minutes, by lheat** (twins' max 56.92):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:C-FRAMA16 sign=below 0 & 1m:EFI13=very low/low/mid/NA & 1m:PVI=very low/low/mid/NA | up | 47.22 | 50.9 | +1.95 | -0.04 | +3.06 | 139.9 | stored | 22.7 | 17.20 | +1.64 | +0.4 | +0.4 | +0.9 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:ERIbear13 sign=below 0 | up | 41.81 | 52.2 | +3.25 | +0.04 | +3.11 | 130.0 | pack | 21.1 | 29.05 | +1.65 | +0.8 | +0.8 | +1.8 | hot, rep, BHY, > twins | 17 |
| 3 | 15m:VORTEXdiff14=mid/high/very high & 1m:HAbody sign=above 0/NA & 5m:AVGDEV14=mid/high/very high | down | 78.55 | 50.5 | +1.26 | -0.09 | +1.64 | 129.2 | none | 12.0 | 75.42 | +0.48 | +0.5 | +0.6 | +1.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 29.88 | 52.7 | +3.67 | +1.84 | +4.27 | 127.6 | pack | 10.1 | 25.57 | +1.57 | +1.2 | +1.1 | +2.8 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:C-SMA50=very low/low/very high & 1m:CMF20=very low/low/mid/NA & X.BTC:RSI14=very low/low/mid | up | 32.24 | 52.5 | +3.52 | +0.55 | +3.63 | 117.0 | pack | 0.0 | 26.15 | +2.19 | +0.9 | +0.9 | +2.1 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:C-MIDPRICE14 sign=above 0 | down | 35.68 | 52.6 | +3.33 | -0.46 | +3.12 | 111.5 | pack | 17.4 | 28.30 | +2.25 | +0.8 | +0.8 | +1.9 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 1m:C-ALMA9 sign=below 0 | up | 41.96 | 51.6 | +2.62 | +0.61 | +2.58 | 108.1 | pack | 11.1 | 39.64 | +1.62 | +0.6 | +0.6 | +1.4 | hot, rep, BHY, > twins | 1 |
| 8 | 1m:EMV14 sign=below 0/NA & 5m:Runs=none/3-4 down/5+ down/NA & 5m:STOCHFK5=very low/low/mid/high/NA | up | 82.58 | 50.0 | +1.03 | +0.04 | +1.66 | 106.4 | stored | 9.6 | 55.23 | -0.37 | -0.2 | -0.0 | -0.5 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:CMF20=very low/low/mid/NA & 1m:WILLR14=low/very high & 5m:FISHER10=very low/low/mid/high/NA | up | 66.15 | 50.6 | +1.61 | +0.02 | +1.59 | 105.1 | pack | 0.0 | 64.89 | +1.45 | +1.0 | +0.9 | +2.3 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:HAbody sign=above 0 | down | 48.88 | 51.4 | +2.17 | -0.23 | +1.94 | 95.0 | pack | 13.3 | 45.02 | +1.25 | +0.8 | +1.0 | +1.8 | hot, rep, BHY, > twins | 0 |

**XRP, triples, 15 minutes, by oheat** (twins' max 51.77):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-FRAMA16 sign=below 0 | up | 35.22 | 53.1 | +4.13 | +0.31 | +2.63 | 145.3 | pack | 18.1 | 30.87 | +2.42 | +0.7 | +1.0 | +1.6 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-SAR sign=below 0 | up | 34.25 | 53.1 | +4.14 | +0.33 | +2.78 | 141.7 | pack | 18.1 | 26.54 | +2.41 | +0.8 | +1.0 | +1.9 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:C-SMA20 sign=below 0 | up | 38.46 | 52.7 | +3.68 | +0.17 | +2.91 | 141.4 | pack | 18.1 | 28.73 | +2.18 | +0.5 | +0.7 | +1.1 | hot, rep, BHY, > twins | 1 |
| 4 | 1m:C-EMA200 sign=above 0 & 1m:PVI=very low/low/mid/NA & X:Breadth15=1 down/mid/1 up/2 up/3 up/NA | down | 59.66 | 51.6 | +2.37 | -0.24 | +3.15 | 141.3 | none | 23.5 | 38.85 | +0.77 | -0.1 | +0.0 | -0.1 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:ERIbull13 sign=below 0/NA & 5m:BBW20=mid/high/very high/NA & NY30m=00:00/00:30/01:00/01:30/02:30/03:00/03:30/04:00/04:30/05:00/05:30/06:00/06:30/07:00/07:30/08:00/08:30/09:00/09:30/10:00/10:30/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/21:00/22:00/22:30/23:00/23:30/NA | up | 61.48 | 51.1 | +2.14 | +0.12 | +0.39 | 131.4 | none | 19.7 | 53.71 | +0.81 | +0.5 | +0.6 | +1.3 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:CCI20 sign=below 0 & 5m:CHOP14=very low/low/mid/NA & 60m:IMI14=very low/low/mid/high/NA | up | 75.35 | 50.7 | +1.73 | +0.17 | +1.23 | 130.7 | pack | 18.7 | 50.68 | -0.37 | -0.2 | -0.1 | -0.6 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:ERIbull13 sign=below 0/NA & 1m:PVI=very low/low/mid & NY30m=00:00/00:30/01:00/01:30/02:30/03:00/03:30/05:00/05:30/06:30/07:00/07:30/08:00/08:30/09:00/09:30/10:00/10:30/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:30/21:00/21:30/22:00/22:30/23:00/23:30/NA | up | 63.92 | 51.0 | +2.04 | +0.10 | +0.97 | 130.2 | none | 19.7 | 56.00 | +0.71 | +0.5 | +0.6 | +1.2 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:AROONup25=mid/high/very high/NA & 1m:ERIbull13 sign=above 0/NA & 5m:CORRELcv30 sign=above 0/NA | down | 46.46 | 52.1 | +2.80 | -0.28 | +2.50 | 129.9 | pack | 16.7 | 37.12 | +1.26 | +0.4 | +0.3 | +0.9 | hot, rep, BHY, > twins | 0 |
| 9 | 15m:SWAK_HP20 sign=above 0/NA & 1m:CORRELcv30 sign=above 0 & 1m:SQZMOM sign=above 0 | down | 35.94 | 52.6 | +3.37 | -0.24 | +1.15 | 121.2 | stored | 23.5 | 22.92 | +3.05 | +1.1 | +1.3 | +2.7 | hot, rep, BHY, > twins | 0 |
| 10 | 15m:AROONOSC25=mid/high/very high/NA & 1m:C-EMA21 sign=above 0/NA & 60m:C-SUPERTREND10/3=mid/high/very high/NA | down | 66.86 | 51.0 | +1.81 | +0.12 | +0.16 | 121.0 | none | 19.4 | 50.30 | +0.19 | +0.1 | +0.3 | +0.1 | hot, rep, BHY, > twins | 1 |

**XRP, triples, 15 minutes, unseen, by iheat** (twins' max 26.62):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:LRSLOPE14 sign=above 0 | up | 38.33 | 48.7 | -0.26 | +2.18 | -0.62 | 83.4 | none | 17.0 | 35.92 | +0.07 | -0.3 | -0.3 | -0.7 | hot, rep, > twins | 0 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:CMOU14 sign=above 0 | down | 41.34 | 49.7 | +0.41 | +1.81 | -1.21 | 74.7 | none | 17.4 | 39.33 | +0.36 | +0.5 | +0.5 | +1.2 | hot, rep, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:QSTICK10 sign=above 0 | up | 47.51 | 49.0 | -0.03 | +1.55 | -0.38 | 73.6 | none | 12.7 | 44.32 | +0.07 | -0.4 | -0.4 | -0.9 | hot, rep, > twins | 0 |
| 4 | 15m:C-FRAMA16 sign=above 0/NA & 1m:C-SMA50=mid/high/very high/NA & 1m:C-ZLEMA21=very low/low | down | 30.64 | 49.0 | -0.22 | +1.36 | -2.30 | 41.6 | none | 21.4 | 29.39 | +0.28 | -0.6 | -0.4 | -1.4 | > twins | 0 |
| 5 | 1m:HT_QUADRATURE sign=below 0/NA & FLOW:Stretch5=low/high/very high & POS:QPos=m00/m01/m02/m04/m05/m07/m09/m11/m13/m14/NA | up | 50.33 | 49.6 | +0.46 | +0.72 | +0.43 | 36.4 | none | 2.1 | 48.95 | +0.61 | +0.6 | +0.5 | +1.4 | > twins | 0 |
| 6 | 1m:KDJ K>D=below/NA & 5m:C-ALMA9=low/high & 5m:OBVdiv10=none | up | 29.54 | 51.2 | +2.17 | +1.16 | +2.06 | 34.3 | none | 2.9 | 28.59 | +2.11 | +1.6 | +1.5 | +3.9 | > twins | 0 |
| 7 | 1m:C-T3_5 sign=below 0/NA & 5m:C-ALMA9=low/high & UTC1h=00/01/02/04/05/06/08/10/13/14/16/17/18/19/20/21/NA | up | 24.35 | 51.6 | +2.53 | +1.39 | +0.59 | 33.8 | none | 9.6 | 23.70 | +1.92 | +1.4 | +1.2 | +3.4 | > twins | 0 |
| 8 | 1m:KDJ K>D=below/NA & 5m:ADX7=very low/low/mid/NA & 5m:ERIbear13 sign=above 0 | down | 39.02 | 50.6 | +1.33 | +0.85 | -2.29 | 33.2 | none | 22.7 | 34.49 | +2.32 | +0.6 | +0.5 | +1.4 | hot, rep, > twins | 0 |
| 9 | 15m:FISHER>trig=above/NA & 1m:C-HMA20=very low/low & 1m:IBS=very low/low/mid/NA | up | 32.22 | 49.5 | +0.53 | +1.00 | -0.01 | 32.3 | none | 11.8 | 31.08 | +0.41 | +0.8 | +0.7 | +2.0 | > twins | 0 |
| 10 | 1m:HT_QUADRATURE sign=above 0 & FLOW:Stretch5=low/high/very high & POS:QPos=m00/m01/m02/m04/m05/m07/m09/m11/m13/m14/NA | down | 50.56 | 50.5 | +1.10 | -0.63 | +0.52 | 32.0 | none | 1.4 | 48.68 | +0.84 | +0.2 | +0.2 | +0.4 | > twins | 0 |

**XRP, triples, 15 minutes, unseen, by lheat** (twins' max 56.92):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:VORTEXdiff14=mid/high/very high & 1m:HAbody sign=above 0/NA & 5m:AVGDEV14=mid/high/very high | down | 78.55 | 50.5 | +1.26 | -0.09 | +1.64 | 129.2 | none | 12.0 | 75.42 | +0.48 | +0.5 | +0.6 | +1.3 | hot, rep, BHY, > twins | 0 |
| 2 | 15m:C-VIDYA12 sign=above 0 & 1m:C-VIDYA12 sign=above 0 & 1m:PVI=very low/low/mid/NA | down | 42.69 | 52.0 | +2.80 | -0.12 | +2.87 | 90.0 | none | 22.0 | 29.06 | +1.20 | +0.5 | +0.8 | +1.2 | hot, rep, BHY, > twins | 0 |
| 3 | 15m:DIdiff14 sign=above 0 & 1m:SMI sign=above 0 & 60m:ADX28=very low/low/mid/NA | down | 31.72 | 52.2 | +2.95 | -0.32 | +2.66 | 82.9 | none | 18.2 | 13.14 | +2.57 | +0.0 | +0.1 | +0.0 | hot, rep, BHY, > twins | 0 |
| 4 | 5m:PVO12/26 sign=above 0 & 15m:C-HMA20 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 20.34 | 53.4 | +4.05 | -0.88 | +3.62 | 73.7 | none | 16.4 | 18.63 | +2.57 | +0.3 | +0.4 | +0.7 | hot, rep, BHY, > twins | 1 |
| 5 | 15m:AROONOSC25 sign=above 0/NA & 1m:SMI sign=above 0/NA & NY30m=00:00/00:30/01:00/01:30/02:00/02:30/03:00/03:30/04:00/05:00/05:30/06:00/06:30/07:00/07:30/08:00/08:30/09:00/09:30/10:00/11:30/12:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/19:30/20:00/20:30/21:00/21:30/22:00/22:30/23:00/NA | down | 29.12 | 52.2 | +2.98 | -0.68 | +2.42 | 70.5 | none | 18.2 | 12.93 | +2.47 | +0.2 | -0.0 | +0.5 | hot, rep, > twins | 0 |
| 6 | 5m:PVO12/26 sign=above 0 & 15m:C-ZLEMA21 sign=above 0 & 1m:C-SWAK_BUTTER20 sign=above 0 | down | 20.24 | 53.0 | +3.73 | -0.89 | +3.48 | 70.4 | none | 16.4 | 18.66 | +2.54 | +0.1 | +0.2 | +0.2 | hot, rep, BHY, > twins | 0 |
| 7 | 5m:PVO12/26 sign=above 0 & 15m:C-HMA20 sign=above 0 & 1m:AD sign=above 0 | down | 19.07 | 53.3 | +3.95 | -0.98 | +3.69 | 70.3 | none | 16.4 | 15.92 | +2.65 | -0.1 | +0.1 | -0.1 | hot, rep, BHY, > twins | 0 |
| 8 | 5m:CVI10 sign=above 0 & 5m:KST>sig=above & 1m:C-FRAMA16 sign=above 0 | down | 24.27 | 52.6 | +3.35 | -0.82 | +2.84 | 68.9 | none | 11.9 | 22.18 | +2.00 | +0.6 | +0.7 | +1.5 | hot, rep, BHY, > twins | 0 |
| 9 | 5m:CVI10 sign=above 0 & 5m:KST>sig=above & 1m:C-SWAK_BUTTER20 sign=above 0 | down | 24.51 | 52.3 | +3.09 | -0.78 | +2.77 | 67.9 | none | 13.9 | 22.44 | +1.85 | +0.2 | +0.3 | +0.5 | hot, rep, BHY, > twins | 1 |
| 10 | 5m:CVI10 sign=above 0 & 5m:KST>sig=above & 1m:AD sign=above 0 | down | 23.09 | 52.5 | +3.25 | -0.89 | +2.88 | 66.6 | none | 11.7 | 19.37 | +1.91 | +0.7 | +0.9 | +1.7 | hot, rep, BHY, > twins | 0 |

**XRP, triples, 15 minutes, unseen, by oheat** (twins' max 46.79):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:C-EMA200 sign=above 0 & 1m:PVI=very low/low/mid/NA & X:Breadth15=1 down/mid/1 up/2 up/3 up/NA | down | 59.66 | 51.6 | +2.37 | -0.24 | +3.15 | 141.3 | none | 23.5 | 38.85 | +0.77 | -0.1 | +0.0 | -0.1 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:ERIbull13 sign=below 0/NA & 5m:BBW20=mid/high/very high/NA & NY30m=00:00/00:30/01:00/01:30/02:30/03:00/03:30/04:00/04:30/05:00/05:30/06:00/06:30/07:00/07:30/08:00/08:30/09:00/09:30/10:00/10:30/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/21:00/22:00/22:30/23:00/23:30/NA | up | 61.48 | 51.1 | +2.14 | +0.12 | +0.39 | 131.4 | none | 19.7 | 53.71 | +0.81 | +0.5 | +0.6 | +1.3 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:ERIbull13 sign=below 0/NA & 1m:PVI=very low/low/mid & NY30m=00:00/00:30/01:00/01:30/02:30/03:00/03:30/05:00/05:30/06:30/07:00/07:30/08:00/08:30/09:00/09:30/10:00/10:30/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:30/21:00/21:30/22:00/22:30/23:00/23:30/NA | up | 63.92 | 51.0 | +2.04 | +0.10 | +0.97 | 130.2 | none | 19.7 | 56.00 | +0.71 | +0.5 | +0.6 | +1.2 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:EMV14 sign=below 0/NA & 1m:ERIbull13 sign=below 0 & X.ETH:Gap15=low/mid/high/very high | up | 70.35 | 50.7 | +1.78 | -0.08 | -2.83 | 125.1 | none | 19.7 | 61.25 | +1.05 | +0.4 | +0.5 | +1.1 | hot, rep, BHY, > twins | 0 |
| 5 | 15m:AROONOSC25=mid/high/very high/NA & 1m:C-EMA21 sign=above 0/NA & 60m:C-SUPERTREND10/3=mid/high/very high/NA | down | 66.86 | 51.0 | +1.81 | +0.12 | +0.16 | 121.0 | none | 19.4 | 50.30 | +0.19 | +0.1 | +0.3 | +0.1 | hot, rep, BHY, > twins | 1 |
| 6 | 15m:C-AVGPRICE sign=above 0/NA & 1m:C-TEMA21=mid/high/very high & 1m:IBS=very low/low/mid/NA | down | 48.23 | 51.8 | +2.50 | -0.22 | +1.22 | 120.7 | none | 18.9 | 46.71 | +1.66 | +0.6 | +0.6 | +1.3 | hot, rep, BHY, > twins | 0 |
| 7 | 15m:C-VIDYA12 sign=above 0 & 1m:C-VIDYA12 sign=above 0 & 1m:PVI=very low/low/mid/NA | down | 42.69 | 52.0 | +2.80 | -0.12 | +2.87 | 119.5 | none | 22.0 | 29.06 | +1.20 | +0.5 | +0.8 | +1.2 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-SUPERTREND10/3 sign=above 0/NA & 1m:CORRELcv30 sign=above 0/NA & POS:QPos=m00/m01/m02/m03/m09/m12/m13/m14/NA | down | 47.10 | 51.8 | +2.51 | -0.11 | +0.47 | 118.1 | none | 19.1 | 38.43 | +1.94 | +0.8 | +0.8 | +1.9 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:C-TSF14=very low/low/mid & 1m:CMF20=very low/low/mid/NA & 1m:Tenkan>Kijun=below/NA | up | 71.12 | 50.6 | +1.65 | +0.05 | +0.86 | 117.5 | none | 20.0 | 58.32 | +0.50 | +0.1 | +0.2 | +0.2 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:AROONOSC25 sign=above 0 & 1m:CMF20=very low/low/mid/NA & X.BTC:RSI14=mid/high/very high/NA | down | 69.38 | 50.9 | +1.67 | +0.00 | -0.80 | 115.9 | none | 21.7 | 40.07 | +0.86 | +0.2 | +0.1 | +0.4 | hot, rep, BHY, > twins | 0 |

**XRP, pairs, 60 minutes, by iheat** (twins' max 31.70):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26=high | down | 13.86 | 52.1 | +2.57 | -2.32 | +2.24 | 32.2 | pack | 8.0 | 13.68 | +1.99 | +0.3 | +0.4 | +0.7 | hot, rep, > twins | 0 |
| 2 | 1m:WILLR14=low & 5m:HAbody sign=above 0 | up | 15.01 | 51.6 | +2.12 | +2.06 | +0.38 | 31.0 | pack | 17.3 | 15.01 | +1.88 | -0.1 | -0.0 | -0.2 | none | 0 |
| 3 | 1m:ERIbull13=low & 1m:PVO12/26 sign=below 0 | up | 16.63 | 49.3 | -0.16 | -1.83 | -3.26 | 30.4 | pack | 12.3 | 16.51 | +0.30 | +0.0 | +0.0 | +0.0 | none | 0 |
| 4 | 1m:MACDh12/26/9 sign=below 0 & 1m:PVO12/26=high | up | 14.67 | 52.4 | +2.82 | +2.06 | +2.55 | 30.2 | pack | 7.1 | 14.52 | +2.45 | +3.8 | +3.9 | +9.0 | hot, rep | 0 |
| 5 | 1m:AROONup14=very high & 1m:KST>sig=below | down | 13.69 | 52.5 | +3.08 | -2.16 | +2.14 | 29.6 | pack | 12.6 | 13.61 | +2.60 | +2.9 | +2.9 | +7.0 | none | 0 |
| 6 | 1m:KVO sign=above 0 & 1m:PVO12/26=high | down | 13.48 | 51.7 | +2.17 | -2.20 | +2.08 | 29.6 | pack | 3.2 | 13.27 | +1.49 | -0.5 | -0.7 | -1.3 | hot, rep | 0 |
| 7 | 1m:DONCHIAN20pos=high & 1m:KST>sig=below | down | 6.95 | 54.5 | +5.16 | -4.25 | +4.36 | 29.5 | pack | 9.7 | 6.92 | +5.21 | +7.1 | +7.2 | +17.0 | none | 0 |
| 8 | 1m:WILLR14=low & 5m:SI sign=above 0 | up | 10.49 | 53.3 | +3.70 | +2.80 | +2.16 | 29.3 | pack | 11.7 | 10.49 | +3.80 | +4.8 | +5.0 | +11.3 | none | 0 |
| 9 | 1m:ER10=low & 1m:MACDh5/35/5 sign=above 0 | up | 21.33 | 50.4 | +0.94 | +1.37 | +1.43 | 29.3 | none | 7.3 | 21.31 | +1.03 | +0.4 | +0.2 | +0.9 | none | 0 |
| 10 | 1m:AC sign=above 0 & 1m:DX14=high | down | 11.51 | 52.0 | +2.38 | -2.49 | +2.20 | 28.7 | pack | 7.9 | 11.31 | +2.16 | -1.6 | -1.6 | -3.8 | hot, rep | 0 |

**XRP, pairs, 60 minutes, by lheat** (twins' max 37.47):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI14=high & 1m:C-TEMA21 sign=above 0 | down | 22.47 | 51.7 | +2.14 | -0.13 | +2.38 | 53.5 | none | 9.9 | 22.42 | +1.74 | +1.7 | +1.6 | +4.1 | > twins | 3 |
| 2 | 1m:C-TEMA21 sign=below 0 & 1m:C-SUPERTREND10/3=very low | up | 14.80 | 53.0 | +3.44 | -0.03 | +3.45 | 51.1 | pack | 6.4 | 14.79 | +3.14 | +3.3 | +2.9 | +7.9 | hot, rep, BHY, > twins | 8 |
| 3 | 1m:AROONdn25=very high & 1m:C-DEMA21 sign=below 0 | up | 21.24 | 51.7 | +2.17 | +0.09 | +2.29 | 48.5 | pack | 12.0 | 21.12 | +1.82 | +2.3 | +2.2 | +5.4 | > twins | 2 |
| 4 | 1m:MACD5/35 sign=below 0 & 60m:ERIbear13 sign=below 0 | up | 16.29 | 51.7 | +2.25 | +0.10 | +2.95 | 48.1 | pack | 19.2 | 14.29 | +1.28 | -0.9 | -1.0 | -2.2 | hot, rep, BHY, > twins | 5 |
| 5 | 1m:C-TEMA21 sign=below 0 & 1m:DONCHIAN55pos=very low | up | 12.37 | 53.4 | +3.84 | +0.05 | +3.88 | 48.0 | pack | 8.7 | 12.34 | +3.22 | +5.0 | +4.6 | +11.7 | > twins | 6 |
| 6 | 1m:CCI20 sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 19.50 | 51.7 | +2.13 | -0.08 | +2.48 | 48.0 | pack | 18.4 | 19.07 | +0.59 | +0.2 | +0.4 | +0.4 | hot, rep, BHY, > twins | 3 |
| 7 | 5m:C-MAMA sign=below 0 & 15m:HT_INPHASE sign=below 0 | up | 15.00 | 52.7 | +3.21 | +0.06 | +3.11 | 46.7 | none | 17.8 | 13.13 | +1.77 | -0.4 | -0.1 | -0.9 | hot, rep, > twins | 0 |
| 8 | 1m:CMF20 sign=below 0 & 15m:HT_INPHASE sign=below 0 | up | 16.53 | 52.5 | +3.05 | +0.35 | +2.82 | 46.6 | pack | 8.3 | 15.59 | +2.12 | +0.9 | +0.9 | +2.0 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:PVT sign=above 0 & 15m:ERIbull13 sign=above 0 | down | 19.90 | 51.6 | +2.08 | -0.05 | +2.34 | 46.5 | pack | 18.1 | 19.77 | +1.05 | +1.1 | +1.3 | +2.7 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:AROONdn14=very high & 1m:C-DEMA21 sign=below 0 | up | 23.50 | 51.3 | +1.76 | +0.07 | +1.96 | 46.1 | pack | 11.5 | 23.45 | +1.60 | +2.1 | +2.1 | +5.0 | > twins | 0 |

**XRP, pairs, 60 minutes, by oheat** (twins' max 36.09):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:KST sign=above 0 & 1m:C-FRAMA16=high | down | 16.80 | 53.0 | +3.44 | -0.85 | +2.37 | 57.7 | pack | 17.7 | 16.64 | +3.25 | +2.9 | +2.9 | +7.1 | hot, rep, BHY, > twins | 1 |
| 2 | 1m:ERIbear13 sign=above 0 & 5m:C-TSF14 sign=below 0 | down | 19.06 | 52.5 | +2.93 | -1.07 | +2.10 | 55.8 | none | 16.5 | 18.98 | +1.77 | +2.4 | +2.4 | +5.9 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:C-FRAMA16=high & 15m:C-ALMA9 sign=above 0 | down | 14.49 | 53.3 | +3.82 | -1.12 | +2.88 | 55.4 | pack | 17.7 | 14.35 | +3.33 | +3.0 | +3.0 | +7.3 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:C-FRAMA16=high & 5m:CCI14 sign=above 0 | down | 16.13 | 52.9 | +3.42 | -0.89 | +2.42 | 55.1 | pack | 18.2 | 16.01 | +3.03 | +2.1 | +2.0 | +4.9 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:CG10=low & 1m:STOCH5 K>D=below | up | 11.84 | 54.3 | +4.64 | +0.93 | +2.04 | 54.9 | pack | 9.3 | 11.79 | +4.27 | +5.9 | +5.8 | +14.1 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:STOCHFK5=low & X:Breadth15=3 down | up | 19.57 | 52.4 | +2.79 | +0.37 | +1.56 | 54.6 | none | 12.4 | 19.54 | +2.84 | +3.1 | +3.2 | +7.4 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:CCI14=high & 1m:MARKETFI sign=below 0 | down | 21.16 | 52.1 | +2.57 | -0.41 | +1.83 | 54.4 | none | 9.9 | 21.11 | +2.16 | +1.8 | +1.7 | +4.3 | hot, rep, BHY, > twins | 0 |
| 8 | 5m:CMF20 sign=below 0 & X.SOL:TakerBuy=low | up | 12.97 | 53.5 | +4.19 | +0.69 | +2.67 | 54.4 | pack | 8.4 | 12.97 | +3.97 | +2.9 | +3.0 | +6.7 | hot, rep, BHY, > twins | 0 |
| 9 | 15m:DPO20 sign=above 0 & X:Breadth15=3 down | up | 16.76 | 52.8 | +3.24 | +0.20 | +2.44 | 54.4 | none | 12.4 | 16.39 | +2.41 | +2.3 | +2.5 | +5.3 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:CCI14=low & X:Breadth15=3 down | up | 19.73 | 52.3 | +2.75 | +0.40 | +1.59 | 54.4 | pack | 12.4 | 19.66 | +2.62 | +4.1 | +4.0 | +9.7 | hot, rep, BHY, > twins | 0 |

**XRP, pairs, 60 minutes, unseen, by iheat** (twins' max 26.90):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ER10=low & 1m:MACDh5/35/5 sign=above 0 | up | 21.33 | 50.4 | +0.94 | +1.37 | +1.43 | 29.3 | none | 7.3 | 21.31 | +1.03 | +0.4 | +0.2 | +0.9 | > twins | 0 |
| 2 | 1m:ER10=low & 1m:MACDh5/35/5 sign=below 0 | down | 21.19 | 50.7 | +1.08 | -1.35 | +1.57 | 28.7 | none | 6.3 | 21.16 | +1.09 | +1.2 | +1.1 | +2.9 | > twins | 0 |
| 3 | 1m:C-TSF14=low & POS:QPhase=m05-09 | up | 17.05 | 51.3 | +1.77 | +1.68 | +1.98 | 28.6 | none | 0.9 | 17.05 | +1.62 | +3.1 | +2.9 | +7.5 | > twins | 0 |
| 4 | 1m:ER10=low & 1m:C-EMA9 sign=below 0 | up | 21.91 | 49.0 | -0.50 | -1.26 | -1.46 | 27.6 | none | 15.5 | 21.90 | -0.52 | -1.3 | -1.1 | -3.0 | > twins | 0 |
| 5 | 1m:DX14=low & 1m:DIdiff14 sign=below 0 | down | 19.66 | 49.0 | -0.57 | -1.38 | +0.27 | 27.1 | none | 18.5 | 19.60 | -0.45 | +0.1 | +0.3 | +0.4 | hot, rep, > twins | 0 |
| 6 | 1m:TakerBuy=low & 5m:STOCHRSI14=very low | up | 7.90 | 47.3 | -2.08 | -3.42 | -4.01 | 27.0 | none | 9.6 | 7.89 | -1.59 | -1.1 | -1.1 | -2.6 | > twins | 0 |
| 7 | 1m:DX14=low & 1m:DIdiff14 sign=above 0 | down | 19.73 | 48.8 | -0.84 | +1.37 | -2.28 | 27.0 | none | 19.1 | 19.65 | -0.65 | +0.1 | +0.3 | +0.3 | hot, rep, > twins | 0 |
| 8 | 1m:AROONOSC14=high & 1m:C-TSF14 sign=above 0 | down | 14.68 | 52.0 | +2.46 | -1.82 | +2.50 | 26.8 | none | 9.1 | 14.62 | +2.39 | +2.8 | +3.0 | +6.8 | none | 0 |
| 9 | 1m:C-TEMA21 sign=above 0 & POS:QPos=m01 | down | 22.90 | 48.4 | -1.15 | +1.16 | -2.01 | 26.6 | none | 4.3 | 22.90 | -1.15 | -1.3 | -1.5 | -3.1 | none | 1 |
| 10 | 1m:CTI20=low & 1m:PVO12/26 sign=below 0 | up | 12.95 | 49.0 | -0.56 | -2.05 | -3.53 | 26.6 | none | 8.9 | 12.57 | +0.15 | +0.8 | +0.9 | +2.0 | hot, rep | 0 |

**XRP, pairs, 60 minutes, unseen, by lheat** (twins' max 37.47):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CCI14=high & 1m:C-TEMA21 sign=above 0 | down | 22.47 | 51.7 | +2.14 | -0.13 | +2.38 | 53.5 | none | 9.9 | 22.42 | +1.74 | +1.7 | +1.6 | +4.1 | > twins | 2 |
| 2 | 5m:C-MAMA sign=below 0 & 15m:HT_INPHASE sign=below 0 | up | 15.00 | 52.7 | +3.21 | +0.06 | +3.11 | 46.7 | none | 17.8 | 13.13 | +1.77 | -0.4 | -0.1 | -0.9 | hot, rep, > twins | 0 |
| 3 | 1m:MACD5/35 sign=above 0 & 15m:DPO20 sign=below 0 | down | 16.05 | 52.8 | +3.17 | -0.22 | +3.09 | 45.9 | none | 19.6 | 14.53 | +2.17 | +2.6 | +2.6 | +6.1 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:DIdiff14 sign=above 0 & 15m:DPO20 sign=below 0 | down | 16.92 | 52.6 | +3.05 | -0.17 | +2.76 | 45.8 | none | 19.1 | 16.23 | +1.12 | +1.2 | +1.2 | +2.9 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:MAMA>FAMA=below & 15m:HT_INPHASE sign=below 0 | up | 15.92 | 52.6 | +3.09 | +0.10 | +2.85 | 45.4 | none | 18.5 | 14.17 | +1.11 | -0.2 | -0.2 | -0.6 | hot, rep, > twins | 0 |
| 6 | 1m:CCI14=high & 5m:SWAK_BP20 sign=above 0 | down | 15.79 | 53.0 | +3.40 | -0.62 | +2.84 | 44.9 | none | 9.9 | 15.71 | +3.16 | +3.4 | +3.2 | +8.1 | > twins | 0 |
| 7 | 1m:C-MEDIAN30 sign=below 0 & 15m:HT_INPHASE sign=below 0 | up | 16.67 | 52.5 | +2.98 | +0.09 | +2.66 | 44.3 | none | 18.5 | 15.88 | +1.45 | -0.4 | -0.2 | -0.9 | hot, rep, BHY, > twins | 0 |
| 8 | 5m:C-MAMA sign=above 0 & 15m:DPO20 sign=below 0 | down | 15.50 | 52.8 | +3.16 | -0.12 | +3.09 | 44.1 | none | 18.6 | 13.87 | +1.62 | +2.1 | +2.2 | +4.9 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:C-SWAK_BUTTER20 sign=above 0 & 5m:HT_INPHASE sign=above 0 | down | 22.47 | 51.3 | +1.76 | -0.24 | +1.95 | 43.8 | none | 15.4 | 22.30 | +0.98 | +1.7 | +1.7 | +4.0 | hot, rep, > twins | 3 |
| 10 | 1m:C-VWAP20 sign=above 0 & 1m:CORRELcv30 sign=above 0 | down | 20.79 | 51.9 | +2.31 | -0.24 | +2.38 | 43.4 | none | 16.6 | 20.37 | +1.46 | +1.5 | +1.6 | +3.6 | hot, rep, BHY, > twins | 4 |

**XRP, pairs, 60 minutes, unseen, by oheat** (twins' max 36.09):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:ERIbear13 sign=above 0 & 5m:C-TSF14 sign=below 0 | down | 19.06 | 52.5 | +2.93 | -1.07 | +2.10 | 55.8 | none | 16.5 | 18.98 | +1.77 | +2.4 | +2.4 | +5.9 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:STOCHFK5=low & X:Breadth15=3 down | up | 19.57 | 52.4 | +2.79 | +0.37 | +1.56 | 54.6 | none | 12.4 | 19.54 | +2.84 | +3.1 | +3.2 | +7.4 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:CCI14=high & 1m:MARKETFI sign=below 0 | down | 21.16 | 52.1 | +2.57 | -0.41 | +1.83 | 54.4 | none | 9.9 | 21.11 | +2.16 | +1.8 | +1.7 | +4.3 | hot, rep, BHY, > twins | 0 |
| 4 | 15m:DPO20 sign=above 0 & X:Breadth15=3 down | up | 16.76 | 52.8 | +3.24 | +0.20 | +2.44 | 54.4 | none | 12.4 | 16.39 | +2.41 | +2.3 | +2.5 | +5.3 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:CCI14=high & 1m:SMI sign=above 0 | down | 19.51 | 52.4 | +2.79 | -0.22 | +1.88 | 54.4 | none | 15.8 | 19.43 | +2.56 | +2.3 | +2.2 | +5.6 | hot, rep, BHY, > twins | 2 |
| 6 | 1m:CCI14=high & 5m:C-MAMA sign=above 0 | down | 19.32 | 52.4 | +2.81 | -0.09 | +1.51 | 54.2 | none | 18.6 | 19.27 | +2.37 | +1.9 | +1.9 | +4.6 | hot, rep, BHY, > twins | 0 |
| 7 | 1m:STOCHFK5=low & 5m:C-MAMA sign=below 0 | up | 19.02 | 52.4 | +2.82 | +0.14 | +1.48 | 53.7 | none | 17.8 | 19.00 | +2.53 | +2.8 | +3.0 | +6.6 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:ERIbear13 sign=above 0 & 15m:PVT sign=above 0 | down | 14.82 | 53.1 | +3.59 | -0.23 | +2.29 | 53.2 | none | 16.5 | 14.66 | +3.26 | +1.5 | +1.5 | +3.5 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:ERIbear13 sign=above 0 & 15m:DPO20 sign=below 0 | down | 17.09 | 52.6 | +3.08 | -0.03 | +2.09 | 52.7 | none | 16.5 | 16.91 | +2.41 | +3.2 | +3.3 | +7.8 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:PVT sign=above 0 & 15m:PVT sign=above 0 | down | 15.29 | 53.0 | +3.44 | -0.29 | +2.75 | 52.7 | none | 15.6 | 15.04 | +2.46 | +0.7 | +0.9 | +1.6 | hot, rep, BHY, > twins | 0 |

**XRP, triples, 60 minutes, by iheat** (twins' max 17.12):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:ER10=low | up | 11.17 | 50.1 | +0.66 | +2.31 | +0.86 | 25.8 | pack | 13.5 | 11.16 | +0.42 | -0.6 | -0.6 | -1.4 | hot, rep, > twins | 0 |
| 2 | 1m:CVI10 sign=above 0 & 5m:SWAK_2PHP20 sign=above 0 & 1m:ERIbull13 sign=below 0 | up | 13.79 | 52.3 | +2.79 | +1.86 | +1.52 | 25.6 | pack | 18.6 | 13.78 | +2.03 | +2.6 | +2.8 | +6.2 | hot, rep, > twins | 0 |
| 3 | 1m:CVI10 sign=above 0 & 5m:SWAK_2PHP20 sign=below 0 & 1m:VORTEXdiff14 sign=above 0 | down | 18.03 | 52.1 | +2.58 | -1.41 | +1.58 | 25.4 | pack | 17.9 | 17.99 | +1.97 | +1.8 | +1.6 | +4.3 | hot, rep, > twins | 0 |
| 4 | 5m:DPO20 sign=above 0 & 5m:CVI10 sign=below 0 & 15m:C-ZLEMA21 sign=above 0 | down | 11.60 | 48.6 | -0.99 | +2.18 | -2.34 | 25.2 | pack | 9.5 | 10.91 | +1.11 | +1.2 | +1.2 | +2.8 | hot, rep, > twins | 0 |
| 5 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:CDL:MARUBOZU=bull | down | 13.05 | 49.0 | -0.56 | +1.88 | -1.71 | 24.6 | pack | 13.6 | 13.05 | -0.58 | -1.2 | -0.9 | -2.9 | > twins | 0 |
| 6 | 5m:DPO20 sign=above 0 & 5m:CVI10 sign=below 0 & 5m:KST>sig=above | up | 11.26 | 50.6 | +1.16 | +2.14 | +2.25 | 24.1 | pack | 7.6 | 10.40 | -0.04 | +0.5 | +0.4 | +1.1 | hot, rep, > twins | 0 |
| 7 | 1m:C-SMA20=very low/low/mid/NA & 1m:IMI14=high/very high & FLOW:Stretch15=very low/low/mid/NA | down | 6.53 | 51.6 | +2.17 | -3.64 | +1.39 | 23.8 | pack | 0.0 | 6.47 | +1.18 | +0.9 | +0.9 | +2.3 | > twins | 0 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 1m:HT_SINE=low | up | 10.72 | 48.7 | -0.82 | -2.18 | -2.40 | 23.4 | pack | 11.2 | 10.70 | -0.75 | -3.2 | -3.1 | -7.7 | > twins | 0 |
| 9 | 5m:DPO20 sign=above 0 & 5m:CVI10 sign=below 0 & 5m:LRSLOPE14 sign=above 0 | down | 10.89 | 49.3 | -0.25 | +2.13 | -1.59 | 23.2 | pack | 17.1 | 10.49 | +1.50 | +0.4 | +0.4 | +0.9 | hot, rep, > twins | 0 |
| 10 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 5m:FISHER>trig=above | up | 19.39 | 50.0 | +0.49 | +1.20 | +0.13 | 23.2 | pack | 9.8 | 19.06 | +0.09 | -0.5 | -0.5 | -1.2 | hot, rep, > twins | 0 |

**XRP, triples, 60 minutes, by lheat** (twins' max 30.13):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CMF20=very low/low/mid/NA & 1m:PERCENTB20/2=very low/low/NA & 1m:PVI=very low/low/mid | up | 21.91 | 51.5 | +1.98 | +0.01 | +2.13 | 46.8 | pack | 0.0 | 21.78 | +2.07 | +2.3 | +2.3 | +5.5 | > twins | 0 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 5m:C-TEMA21 sign=above 0 | down | 19.73 | 51.7 | +2.12 | -0.50 | +2.35 | 46.3 | pack | 13.5 | 19.16 | +1.26 | +0.8 | +1.2 | +2.0 | hot, rep, BHY, > twins | 1 |
| 3 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 1m:HT_TRENDMODE=trend | up | 17.85 | 52.2 | +2.65 | +1.12 | +2.56 | 44.6 | pack | 11.2 | 17.34 | +0.18 | +1.5 | +1.4 | +3.6 | hot, rep, > twins | 0 |
| 4 | 15m:VHF28=low/mid/high/very high/NA & 1m:C-SWAK_BUTTER20=very low/low & NY30m=00:00/00:30/01:00/03:00/03:30/04:00/04:30/05:00/05:30/06:00/06:30/07:00/07:30/08:30/09:30/10:00/10:30/11:30/12:00/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/20:30/21:00/21:30/22:00/22:30/23:00/23:30/NA | up | 20.39 | 51.9 | +2.36 | -0.04 | +2.05 | 41.8 | pack | 0.0 | 20.32 | +2.13 | +2.3 | +2.2 | +5.4 | > twins | 0 |
| 5 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 5m:C-TEMA21 sign=below 0 | up | 20.49 | 51.3 | +1.76 | +0.31 | +2.03 | 41.7 | pack | 11.2 | 19.91 | +0.18 | +0.6 | +0.5 | +1.4 | hot, rep, > twins | 0 |
| 6 | 1m:SINE>LEAD=above & 1m:HT_TRENDMODE=trend & 1m:AD sign=above 0 | down | 17.85 | 52.1 | +2.56 | -0.48 | +2.33 | 41.6 | pack | 13.3 | 17.12 | +1.62 | +1.4 | +1.6 | +3.4 | > twins | 0 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:CVI10 sign=above 0 | up | 12.94 | 53.2 | +3.65 | +1.32 | +3.14 | 40.6 | pack | 14.3 | 12.24 | +1.93 | +1.5 | +1.3 | +3.5 | > twins | 0 |
| 8 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:DPO20 sign=below 0 | down | 23.17 | 51.2 | +1.59 | -0.36 | +1.69 | 39.1 | pack | 13.6 | 23.07 | +0.95 | +1.0 | +1.1 | +2.4 | hot, rep, > twins | 0 |
| 9 | 1m:C-SMA50=very low/low/very high & 1m:CMF20=very low/low/mid/NA & X.BTC:RSI14=very low/low/mid | up | 16.23 | 51.7 | +2.25 | +0.36 | +2.32 | 37.6 | pack | 0.0 | 15.53 | +1.42 | +1.5 | +1.4 | +3.5 | hot, rep, > twins | 0 |
| 10 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 1m:HT_INPHASE sign=above 0 | down | 23.29 | 51.2 | +1.65 | -0.36 | +1.58 | 36.7 | pack | 13.6 | 23.14 | +1.06 | +1.2 | +1.3 | +2.9 | hot, rep, > twins | 0 |

**XRP, triples, 60 minutes, by oheat** (twins' max 24.22):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15m:BOP sign=below 0 & 1m:C-EMA21=very low/low & 1m:SI=very low/low/high/NA | up | 13.52 | 53.8 | +4.23 | +1.33 | +1.83 | 57.2 | pack | 15.5 | 13.51 | +3.97 | +6.2 | +5.9 | +14.8 | hot, rep, BHY, > twins | 0 |
| 2 | 15m:BOP sign=below 0 & 1m:CG10=very low/low & 1m:ERIbull13 sign=below 0/NA | up | 10.62 | 55.0 | +5.34 | +0.54 | -0.78 | 56.8 | pack | 18.6 | 10.38 | +4.80 | +8.1 | +8.2 | +19.5 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 5m:CMF20 sign=above 0 | down | 15.69 | 52.8 | +3.25 | -0.45 | +2.05 | 51.1 | pack | 13.5 | 15.27 | +2.46 | +2.0 | +2.1 | +4.8 | hot, rep, BHY, > twins | 0 |
| 4 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 5m:CMF20 sign=below 0 | up | 14.36 | 53.0 | +3.54 | +0.50 | +2.59 | 50.9 | pack | 14.3 | 13.52 | +2.29 | +3.2 | +3.2 | +7.5 | hot, rep, BHY, > twins | 0 |
| 5 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 1m:DONCHIAN55pos=very low | up | 9.92 | 54.6 | +5.06 | +1.00 | +4.00 | 50.2 | pack | 11.2 | 9.90 | +4.22 | +6.4 | +6.1 | +15.2 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 15m:WAD sign=below 0 | up | 13.34 | 53.2 | +3.74 | +0.38 | +2.37 | 49.9 | pack | 14.3 | 12.65 | +2.86 | +2.5 | +2.6 | +5.9 | hot, rep, BHY, > twins | 0 |
| 7 | 5m:PVI sign=above 0 & FLOW:Stretch15=mid/high/very high/NA & FLOW:Stretch5=high/very high/NA | down | 13.85 | 53.2 | +3.60 | -1.08 | +2.13 | 49.9 | none | 17.3 | 13.77 | +2.99 | +1.3 | +1.3 | +3.2 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:PVO12/26 sign=above 0 & 5m:C-LINEARREG14 sign=below 0 & 1m:CCI14=low | up | 15.76 | 52.7 | +3.16 | +0.52 | +2.15 | 49.8 | pack | 11.2 | 15.71 | +2.60 | +4.6 | +4.4 | +11.0 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:CVI10 sign=above 0 & 5m:SWAK_2PHP20 sign=below 0 & 1m:AROONdn25=very high | up | 18.39 | 52.2 | +2.69 | +0.40 | +1.29 | 49.4 | pack | 12.0 | 18.32 | +2.55 | +2.9 | +2.7 | +7.0 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:CVI10 sign=above 0 & 1m:KST>sig=above & 5m:CMF20 sign=above 0 | down | 16.54 | 52.6 | +2.97 | -0.44 | +1.74 | 49.1 | pack | 13.6 | 16.27 | +2.74 | +2.2 | +2.4 | +5.3 | hot, rep, BHY, > twins | 0 |

**XRP, triples, 60 minutes, unseen, by iheat** (twins' max 17.12):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:SQZMOM sign=above 0 | down | 19.17 | 50.0 | +0.41 | +1.18 | -0.81 | 22.6 | none | 18.1 | 18.97 | +0.58 | +1.3 | +1.2 | +3.2 | hot, rep, > twins | 0 |
| 2 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 1m:CMOU14 sign=above 0 | down | 21.65 | 49.9 | +0.37 | +1.01 | -0.85 | 21.9 | none | 17.9 | 21.57 | +0.38 | +1.2 | +1.1 | +2.8 | hot, rep, > twins | 0 |
| 3 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 5m:C-ZLEMA21 sign=above 0 | up | 18.93 | 50.0 | +0.53 | +1.08 | +0.20 | 20.5 | none | 8.8 | 18.63 | +0.02 | -1.2 | -1.3 | -2.8 | hot, rep, > twins | 0 |
| 4 | 1m:SI=very low/low & 1m:WT1 sign=above 0 & 5m:STOCHRSI14=mid/high/very high | down | 20.44 | 51.2 | +1.55 | -0.89 | +0.27 | 18.3 | none | 18.4 | 20.43 | +1.48 | +1.6 | +1.5 | +3.8 | > twins | 0 |
| 5 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:FISHER>trig=below | down | 9.52 | 48.5 | -1.05 | +1.89 | -5.01 | 18.0 | none | 8.1 | 9.41 | -1.03 | -1.3 | -1.2 | -3.1 | > twins | 0 |
| 6 | 5m:PVO12/26 sign=above 0 & 15m:C-HMA20 sign=above 0 & 1m:SWAK_HP20=high | down | 6.98 | 55.6 | +6.10 | -2.56 | +3.85 | 17.8 | none | 13.8 | 6.97 | +5.41 | +1.5 | +1.9 | +3.7 | > twins | 2 |
| 7 | 1m:ADOSC sign=above 0 & 1m:MARKETFI=high & POS:QPos=m03/m04/m05/m06/m07/m10/m14 | up | 13.81 | 50.2 | +0.68 | +1.28 | +0.00 | 17.7 | none | 7.3 | 13.81 | +0.95 | +0.3 | +0.1 | +0.6 | > twins | 0 |
| 8 | 5m:PVO12/26 sign=above 0 & 15m:C-LINEARREG14 sign=above 0 & X.SOL:R5z=high | down | 6.76 | 55.0 | +5.35 | -2.57 | +3.34 | 17.4 | none | 12.3 | 6.73 | +4.32 | +1.1 | +1.2 | +2.6 | > twins | 1 |
| 9 | 1m:ER10=high & 1m:C-DEMA21 sign=below 0 & 1m:BOP=low | up | 7.12 | 53.7 | +4.41 | +2.33 | +3.01 | 16.6 | none | 7.7 | 7.12 | +4.29 | +6.7 | +5.4 | +15.9 | none | 1 |
| 10 | 1m:VHF28=high & 5m:C-TSF14 sign=below 0 & 1m:FISHER10 sign=above 0 | down | 2.97 | 54.2 | +4.84 | -5.45 | +3.86 | 16.2 | none | 16.4 | 2.94 | +4.37 | +3.1 | +2.5 | +7.5 | none | 0 |

**XRP, triples, 60 minutes, unseen, by lheat** (twins' max 30.13):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:STDDEV20=high & 5m:C-DEMA21 sign=above 0 & 1m:BBW20=high | down | 6.28 | 52.2 | +2.64 | -0.04 | +5.77 | 36.3 | none | 9.1 | 5.87 | +3.41 | -0.4 | +0.2 | -0.9 | > twins | 1 |
| 2 | 5m:PVO12/26 sign=above 0 & 15m:C-ZLEMA21 sign=above 0 & 1m:C-SMA20 sign=above 0 | down | 9.62 | 53.6 | +4.03 | -0.64 | +3.67 | 35.3 | none | 18.0 | 9.26 | +2.40 | -0.2 | +0.0 | -0.6 | hot, rep, > twins | 0 |
| 3 | 5m:PVO12/26 sign=above 0 & 15m:C-ZLEMA21 sign=above 0 & 1m:ERIbull13 sign=above 0 | down | 10.15 | 53.1 | +3.44 | -0.42 | +3.45 | 35.1 | none | 17.7 | 9.87 | +1.66 | -0.7 | -0.6 | -1.7 | hot, rep, > twins | 0 |
| 4 | 5m:PVO12/26 sign=above 0 & 15m:C-LINEARREG14 sign=above 0 & 1m:PVT sign=above 0 | down | 10.30 | 53.4 | +3.78 | -0.52 | +3.33 | 34.3 | none | 15.6 | 9.95 | +2.56 | -0.0 | +0.1 | -0.1 | hot, rep, > twins | 0 |
| 5 | 1m:FISHER10 sign=above 0 & 1m:CVI10=high & 1m:HT_SINE sign=above 0 | down | 9.92 | 52.5 | +2.85 | -1.00 | +3.17 | 31.5 | none | 9.5 | 9.83 | +2.27 | +0.3 | +0.3 | +0.7 | > twins | 0 |
| 6 | PERP:FundClock=15-60m/1-4h/4-8h/NA & X.BTC:R15z=mid/high/very high/NA & X.ETH:Gap5=high/very high/NA | down | 20.91 | 51.2 | +1.54 | -0.05 | +1.51 | 31.5 | none | 0.0 | 20.85 | +1.42 | +1.1 | +1.3 | +2.7 | > twins | 0 |
| 7 | 5m:HT_TRENDMODE=trend & 15m:AC sign=below 0 & 15m:WT1>WT2=below | up | 9.35 | 52.4 | +2.87 | +0.30 | +3.35 | 31.3 | none | 11.5 | 6.28 | +1.94 | +0.9 | +0.2 | +2.1 | hot, rep, > twins | 0 |
| 8 | 5m:CVI10 sign=above 0 & 5m:KST>sig=above & 1m:AD sign=above 0 | down | 11.32 | 52.6 | +2.98 | -0.60 | +2.73 | 30.9 | none | 11.6 | 10.97 | +2.35 | +2.4 | +2.5 | +5.7 | hot, rep, > twins | 0 |
| 9 | 1m:STC=very low/low/mid/NA & 60m:VORTEXdiff14=very low/low/mid/NA & X.SOL:RSI14=very low/low/very high | up | 17.16 | 51.4 | +1.87 | +0.39 | +1.80 | 30.8 | none | 0.0 | 16.83 | +1.76 | +0.9 | +0.9 | +2.2 | > twins | 0 |
| 10 | 5m:HT_TRENDMODE=trend & 15m:AC sign=below 0 & 5m:SWAK_HP20 sign=below 0 | up | 8.37 | 53.5 | +4.00 | +0.58 | +3.64 | 30.5 | none | 17.5 | 7.53 | +3.29 | +1.4 | +1.0 | +3.3 | hot, rep, > twins | 4 |

**XRP, triples, 60 minutes, unseen, by oheat** (twins' max 24.22):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5m:PVI sign=above 0 & FLOW:Stretch15=mid/high/very high/NA & FLOW:Stretch5=high/very high/NA | down | 13.85 | 53.2 | +3.60 | -1.08 | +2.13 | 49.9 | none | 17.3 | 13.77 | +2.99 | +1.3 | +1.3 | +3.2 | hot, rep, BHY, > twins | 0 |
| 2 | 15m:SI sign=above 0/NA & 1m:CRSI=mid/high/very high/NA & 5m:CORRELcv30 sign=above 0 | down | 13.26 | 53.1 | +3.50 | -0.20 | +1.14 | 46.4 | none | 15.6 | 13.11 | +3.08 | +1.9 | +2.0 | +4.5 | hot, rep, BHY, > twins | 0 |
| 3 | 15m:C-KAMA30 sign=above 0 & 1m:VORTEXdiff14 sign=above 0/NA & 5m:MASSI=mid/high/very high/NA | down | 13.75 | 52.8 | +3.24 | -0.41 | +2.45 | 44.5 | none | 19.2 | 13.33 | +2.50 | +0.8 | +0.7 | +1.9 | hot, rep, BHY, > twins | 0 |
| 4 | 5m:PVO12/26 sign=above 0 & 15m:C-HMA20 sign=above 0 & 1m:C-ZLEMA21 sign=above 0 | down | 10.23 | 53.9 | +4.28 | -1.18 | +2.78 | 43.8 | none | 13.8 | 10.16 | +2.97 | +0.9 | +1.2 | +2.2 | hot, rep, BHY, > twins | 0 |
| 5 | 5m:PVO12/26 sign=above 0 & 15m:C-HMA20 sign=above 0 & 1m:C-FRAMA16 sign=above 0 | down | 10.33 | 53.8 | +4.22 | -0.73 | +3.20 | 43.6 | none | 13.8 | 10.19 | +2.66 | +0.8 | +1.0 | +2.0 | hot, rep, BHY, > twins | 0 |
| 6 | 1m:C-SUPERTREND10/3 sign=above 0/NA & 1m:CORRELcv30 sign=above 0/NA & POS:QPos=m00/m01/m02/m03/m09/m12/m13/m14/NA | down | 19.21 | 51.8 | +2.26 | -0.38 | +0.36 | 43.4 | none | 16.6 | 18.30 | +2.07 | +0.7 | +0.6 | +1.6 | hot, rep, BHY, > twins | 0 |
| 7 | 5m:PVO12/26 sign=above 0 & 15m:C-HMA20 sign=above 0 & 1m:HAbody sign=above 0 | down | 10.57 | 53.7 | +4.09 | -0.85 | +2.94 | 43.2 | none | 13.8 | 10.49 | +2.82 | +1.0 | +1.1 | +2.4 | hot, rep, BHY, > twins | 0 |
| 8 | 1m:C-EMA50 sign=below 0/NA & 1m:IBS=mid/high/very high & 1m:SWAK_2PHP20=very low/low/NA | up | 19.85 | 51.7 | +2.14 | +0.39 | +0.68 | 42.4 | none | 19.5 | 19.83 | +2.04 | +1.1 | +1.0 | +2.6 | hot, rep, BHY, > twins | 0 |
| 9 | 15m:C-VIDYA12 sign=above 0 & 1m:C-VIDYA12 sign=above 0 & 1m:PVI=very low/low/mid/NA | down | 14.74 | 52.4 | +2.83 | -0.05 | +2.03 | 41.8 | none | 19.9 | 14.14 | +1.65 | +0.6 | +0.9 | +1.4 | hot, rep, BHY, > twins | 0 |
| 10 | 1m:C-EMA50=high/very high & 1m:C-MCGD14 sign=above 0 & NY30m=00:00/01:00/02:00/02:30/03:30/04:00/04:30/05:00/05:30/06:00/07:00/07:30/08:00/08:30/09:00/09:30/10:00/10:30/11:00/11:30/12:00/12:30/13:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/18:30/19:00/19:30/20:00/20:30/21:00/22:00/22:30/23:30/NA | down | 12.57 | 52.9 | +3.31 | -0.13 | +1.68 | 41.5 | none | 19.2 | 12.16 | +2.64 | +0.5 | +0.5 | +1.3 | hot, rep, BHY, > twins | 0 |

**XRP, pairs, 240 minutes, by iheat** (twins' max 16.00):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:LRSLOPE14=low & 5m:FISHER>trig=above | up | 4.39 | 54.1 | +4.41 | +3.94 | +3.53 | 17.3 | pack | 8.5 | 4.38 | +4.23 | +6.6 | +6.7 | +15.5 | > twins | 0 |
| 2 | 1m:PSO=low & 5m:MACDh5/35/5 sign=above 0 | up | 4.77 | 54.2 | +4.60 | +3.60 | +3.53 | 17.2 | none | 6.4 | 4.77 | +3.55 | +6.1 | +6.0 | +14.4 | > twins | 0 |
| 3 | 1m:LRSLOPE14=low & 5m:C-LINEARREG14 sign=above 0 | up | 2.77 | 56.9 | +7.25 | +6.13 | +6.29 | 17.0 | none | 8.5 | 2.77 | +6.94 | +15.2 | +15.4 | +36.2 | > twins | 0 |
| 4 | 1m:CMOU14 sign=above 0 & X.SOL:R15z=low | down | 2.72 | 55.8 | +5.80 | -6.17 | +5.00 | 16.8 | none | 11.0 | 2.72 | +4.35 | +10.7 | +10.4 | +26.3 | hot, rep, > twins | 0 |
| 5 | 1m:CDL:MARUBOZU=bear & POS:QPos=m00 | down | 3.46 | 54.4 | +4.50 | -4.83 | +4.82 | 16.7 | none | 1.0 | 3.46 | +4.50 | +12.1 | +12.7 | +29.1 | > twins | 0 |
| 6 | 1m:FISHER10=low & 5m:MACDh5/35/5 sign=above 0 | up | 4.21 | 54.5 | +4.94 | +3.87 | +3.66 | 16.3 | pack | 7.9 | 4.20 | +4.60 | +8.8 | +8.4 | +20.7 | > twins | 0 |
| 7 | 1m:CDL:CLOSINGMARUBOZU=bear & POS:QPos=m00 | down | 4.48 | 53.2 | +3.32 | -3.58 | +3.70 | 16.0 | none | 1.0 | 4.48 | +3.32 | +7.1 | +7.9 | +17.0 | > twins | 0 |
| 8 | 1m:CCI14 sign=above 0 & X.SOL:R5z=low | down | 4.42 | 53.4 | +3.47 | -3.62 | +2.76 | 16.0 | none | 10.3 | 4.41 | +2.61 | +7.7 | +7.6 | +18.7 | none | 0 |
| 9 | 1m:C-TSF14=high & POS:QPos=m01 | up | 4.70 | 53.0 | +3.33 | +3.39 | +3.60 | 15.9 | none | 1.0 | 4.70 | +3.33 | +5.8 | +6.0 | +13.7 | none | 0 |
| 10 | 5m:DPO20=high & X.BTC:RSI14=high | up | 2.41 | 54.8 | +5.26 | +6.56 | +5.19 | 15.8 | none | 6.3 | 2.41 | +4.10 | +8.0 | +8.3 | +19.3 | none | 0 |

**XRP, pairs, 240 minutes, by lheat** (twins' max 20.82):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:IMI14=very high & 15m:C-ZLEMA21 sign=above 0 | down | 2.85 | 57.0 | +7.20 | -2.86 | +7.19 | 20.5 | none | 5.9 | 2.85 | +4.74 | +9.5 | +9.2 | +22.8 | hot, rep | 1 |
| 2 | 1m:CMOU14=very high & 15m:C-ZLEMA21 sign=above 0 | down | 3.67 | 55.3 | +5.47 | -2.50 | +5.49 | 20.2 | none | 5.6 | 3.67 | +3.21 | +8.3 | +8.7 | +20.0 | hot, rep | 4 |
| 3 | 1m:CCI14=very high & 5m:HT_SINE sign=below 0 | down | 4.62 | 54.1 | +4.37 | -2.38 | +4.19 | 19.4 | none | 5.0 | 4.62 | +3.48 | +4.8 | +5.5 | +11.5 | none | 0 |
| 4 | 1m:RSI2=very high & 5m:STOCH5 K>D=above | down | 4.68 | 54.3 | +4.46 | -0.85 | +4.13 | 19.3 | pack | 4.1 | 4.68 | +3.77 | +4.8 | +4.6 | +11.5 | none | 0 |
| 5 | 1m:IMI14=very high & 5m:EFI13 sign=above 0 | down | 3.03 | 55.7 | +5.82 | -1.75 | +6.37 | 19.3 | none | 5.9 | 3.02 | +3.38 | +4.4 | +4.2 | +10.6 | none | 0 |
| 6 | 1m:CMOU14=very high & 15m:FISHER>trig=above | down | 3.26 | 55.9 | +6.15 | -2.89 | +5.91 | 19.2 | none | 5.9 | 3.25 | +4.49 | +9.7 | +10.6 | +23.5 | hot, rep | 0 |
| 7 | 1m:IMI14=very high & 15m:FISHER>trig=above | down | 2.49 | 57.6 | +7.90 | -3.28 | +7.62 | 19.0 | none | 5.9 | 2.48 | +5.38 | +9.4 | +9.3 | +22.6 | hot, rep | 0 |
| 8 | 1m:CMOU14=very high & 15m:C-TSF14 sign=above 0 | down | 3.82 | 54.6 | +4.77 | -1.92 | +4.97 | 19.0 | none | 5.6 | 3.82 | +2.79 | +7.4 | +7.9 | +17.9 | none | 0 |
| 9 | 1m:RVI14=high & 15m:SWAK_BP20 sign=above 0 | down | 5.02 | 53.8 | +3.95 | -1.38 | +3.73 | 18.7 | none | 5.5 | 5.02 | +2.80 | +5.3 | +5.2 | +12.6 | none | 0 |
| 10 | 15m:HT_TRENDMODE=cycle & X.BTC:RSI14=very low | up | 3.09 | 55.3 | +5.61 | +3.13 | +6.05 | 18.7 | none | 6.0 | 3.08 | +2.74 | +7.3 | +6.8 | +17.4 | none | 0 |

**XRP, pairs, 240 minutes, by oheat** (twins' max 21.77):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:CG10=low & POS:QPhase=m10-14 | up | 4.52 | 55.3 | +5.58 | +1.84 | +2.81 | 25.2 | pack | 6.6 | 4.52 | +5.24 | +14.9 | +14.7 | +35.6 | hot, rep, BHY, > twins | 0 |
| 2 | 1m:C-MAMA=low & X.SOL:RSI14=low | up | 5.56 | 54.0 | +4.31 | +1.16 | +2.67 | 24.0 | pack | 5.4 | 5.56 | +4.32 | +9.8 | +9.8 | +23.4 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:CG10=low & 1m:CDL:LONGLINE=bear | up | 3.94 | 55.6 | +5.82 | +1.73 | +2.38 | 23.0 | pack | 6.6 | 3.94 | +5.46 | +12.0 | +11.2 | +28.8 | > twins | 0 |
| 4 | 1m:C-VWAP20=low & X.SOL:RSI14=low | up | 5.53 | 53.8 | +4.15 | +1.46 | +2.63 | 22.9 | pack | 6.3 | 5.53 | +3.88 | +8.7 | +8.5 | +20.8 | hot, rep, BHY, > twins | 1 |
| 5 | 1m:C-MAMA=low & X.SOL:R15z=low | up | 5.18 | 54.1 | +4.40 | +1.54 | +3.34 | 22.8 | pack | 5.4 | 5.17 | +4.43 | +8.0 | +8.1 | +19.1 | hot, rep, BHY, > twins | 0 |
| 6 | X.BTC:Gap15=low & X.SOL:RSI14=low | up | 4.21 | 55.0 | +5.32 | +2.09 | +3.55 | 22.4 | none | 4.4 | 4.20 | +4.32 | +9.5 | +9.3 | +22.8 | > twins | 0 |
| 7 | 1m:QSTICK10=very low & 60m:NVI sign=above 0 | up | 3.16 | 56.7 | +7.07 | +1.43 | +5.07 | 22.4 | pack | 6.7 | 3.16 | +5.31 | +12.7 | +12.1 | +30.2 | hot, rep, BHY, > twins | 2 |
| 8 | 1m:C-MIDPOINT14=low & X.SOL:R15z=low | up | 5.16 | 54.0 | +4.33 | +1.63 | +3.39 | 22.3 | pack | 6.8 | 5.16 | +4.04 | +8.4 | +8.3 | +20.1 | hot, rep, BHY, > twins | 0 |
| 9 | 1m:RSI2=very high & 60m:NVI sign=below 0 | down | 2.72 | 58.0 | +8.21 | -2.14 | +5.75 | 22.3 | pack | 4.1 | 2.71 | +6.37 | +10.4 | +10.6 | +24.7 | > twins | 0 |
| 10 | 1m:AROONdn25=very low & 5m:CDL:BELTHOLD=bull | down | 4.45 | 54.8 | +4.98 | -2.74 | +3.95 | 22.2 | none | 6.8 | 4.45 | +3.93 | +10.9 | +10.3 | +26.2 | hot, rep, BHY, > twins | 0 |

**XRP, pairs, 240 minutes, unseen, by iheat** (twins' max 15.44):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:PSO=low & 5m:MACDh5/35/5 sign=above 0 | up | 4.77 | 54.2 | +4.60 | +3.60 | +3.53 | 17.2 | none | 6.4 | 4.77 | +3.55 | +6.1 | +6.0 | +14.4 | > twins | 0 |
| 2 | 1m:LRSLOPE14=low & 5m:C-LINEARREG14 sign=above 0 | up | 2.77 | 56.9 | +7.25 | +6.13 | +6.29 | 17.0 | none | 8.5 | 2.77 | +6.94 | +15.2 | +15.4 | +36.2 | > twins | 0 |
| 3 | 1m:CMOU14 sign=above 0 & X.SOL:R15z=low | down | 2.72 | 55.8 | +5.80 | -6.17 | +5.00 | 16.8 | none | 11.0 | 2.72 | +4.35 | +10.7 | +10.4 | +26.3 | hot, rep, > twins | 0 |
| 4 | 1m:CDL:MARUBOZU=bear & POS:QPos=m00 | down | 3.46 | 54.4 | +4.50 | -4.83 | +4.82 | 16.7 | none | 1.0 | 3.46 | +4.50 | +12.1 | +12.7 | +29.1 | > twins | 0 |
| 5 | 1m:CDL:CLOSINGMARUBOZU=bear & POS:QPos=m00 | down | 4.48 | 53.2 | +3.32 | -3.58 | +3.70 | 16.0 | none | 1.0 | 4.48 | +3.32 | +7.1 | +7.9 | +17.0 | > twins | 0 |
| 6 | 1m:CCI14 sign=above 0 & X.SOL:R5z=low | down | 4.42 | 53.4 | +3.47 | -3.62 | +2.76 | 16.0 | none | 10.3 | 4.41 | +2.61 | +7.7 | +7.6 | +18.7 | > twins | 0 |
| 7 | 1m:C-TSF14=high & POS:QPos=m01 | up | 4.70 | 53.0 | +3.33 | +3.39 | +3.60 | 15.9 | none | 1.0 | 4.70 | +3.33 | +5.8 | +6.0 | +13.7 | > twins | 0 |
| 8 | 5m:DPO20=high & X.BTC:RSI14=high | up | 2.41 | 54.8 | +5.26 | +6.56 | +5.19 | 15.8 | none | 6.3 | 2.41 | +4.10 | +8.0 | +8.3 | +19.3 | > twins | 0 |
| 9 | 1m:ER10=very high & 1m:SWAK_BP20=high | down | 2.16 | 58.8 | +8.91 | -7.23 | +8.36 | 15.6 | none | 3.9 | 2.15 | +6.36 | +8.8 | +8.7 | +20.9 | > twins | 0 |
| 10 | 1m:MOM10=low & 5m:KDJ K>D=above | up | 5.36 | 53.2 | +3.58 | +2.91 | +2.99 | 15.6 | none | 7.0 | 5.36 | +3.11 | +7.5 | +7.4 | +17.7 | > twins | 1 |

**XRP, pairs, 240 minutes, unseen, by lheat** (twins' max 19.39):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:IMI14=very high & 15m:C-ZLEMA21 sign=above 0 | down | 2.85 | 57.0 | +7.20 | -2.86 | +7.19 | 20.5 | none | 5.9 | 2.85 | +4.74 | +9.5 | +9.2 | +22.8 | hot, rep, > twins | 1 |
| 2 | 1m:CMOU14=very high & 15m:C-ZLEMA21 sign=above 0 | down | 3.67 | 55.3 | +5.47 | -2.50 | +5.49 | 20.2 | none | 5.6 | 3.67 | +3.21 | +8.3 | +8.7 | +20.0 | hot, rep, > twins | 4 |
| 3 | 1m:CCI14=very high & 5m:HT_SINE sign=below 0 | down | 4.62 | 54.1 | +4.37 | -2.38 | +4.19 | 19.4 | none | 5.0 | 4.62 | +3.48 | +4.8 | +5.5 | +11.5 | none | 0 |
| 4 | 1m:IMI14=very high & 5m:EFI13 sign=above 0 | down | 3.03 | 55.7 | +5.82 | -1.75 | +6.37 | 19.3 | none | 5.9 | 3.02 | +3.38 | +4.4 | +4.2 | +10.6 | none | 0 |
| 5 | 1m:CMOU14=very high & 15m:FISHER>trig=above | down | 3.26 | 55.9 | +6.15 | -2.89 | +5.91 | 19.2 | none | 5.9 | 3.25 | +4.49 | +9.7 | +10.6 | +23.5 | hot, rep | 0 |
| 6 | 1m:IMI14=very high & 15m:FISHER>trig=above | down | 2.49 | 57.6 | +7.90 | -3.28 | +7.62 | 19.0 | none | 5.9 | 2.48 | +5.38 | +9.4 | +9.3 | +22.6 | hot, rep | 0 |
| 7 | 1m:CMOU14=very high & 15m:C-TSF14 sign=above 0 | down | 3.82 | 54.6 | +4.77 | -1.92 | +4.97 | 19.0 | none | 5.6 | 3.82 | +2.79 | +7.4 | +7.9 | +17.9 | none | 0 |
| 8 | 1m:RVI14=high & 15m:SWAK_BP20 sign=above 0 | down | 5.02 | 53.8 | +3.95 | -1.38 | +3.73 | 18.7 | none | 5.5 | 5.02 | +2.80 | +5.3 | +5.2 | +12.6 | none | 0 |
| 9 | 15m:HT_TRENDMODE=cycle & X.BTC:RSI14=very low | up | 3.09 | 55.3 | +5.61 | +3.13 | +6.05 | 18.7 | none | 6.0 | 3.08 | +2.74 | +7.3 | +6.8 | +17.4 | none | 0 |
| 10 | 5m:DPO20 sign=below 0 & X.BTC:RSI14=high | down | 5.63 | 52.9 | +3.04 | -1.37 | +3.24 | 18.2 | none | 9.0 | 5.62 | +2.41 | +3.6 | +3.7 | +8.6 | none | 0 |

**XRP, pairs, 240 minutes, unseen, by oheat** (twins' max 21.77):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | X.BTC:Gap15=low & X.SOL:RSI14=low | up | 4.21 | 55.0 | +5.32 | +2.09 | +3.55 | 22.4 | none | 4.4 | 4.20 | +4.32 | +9.5 | +9.3 | +22.8 | > twins | 0 |
| 2 | 1m:AROONdn25=very low & 5m:CDL:BELTHOLD=bull | down | 4.45 | 54.8 | +4.98 | -2.74 | +3.95 | 22.2 | none | 6.8 | 4.45 | +3.93 | +10.9 | +10.3 | +26.2 | hot, rep, BHY, > twins | 0 |
| 3 | 1m:PSO=low & 5m:MACDh5/35/5 sign=above 0 | up | 4.77 | 54.2 | +4.60 | +3.60 | +3.53 | 22.0 | none | 6.4 | 4.77 | +3.55 | +6.1 | +6.0 | +14.4 | > twins | 0 |
| 4 | 1m:PSO=low & 5m:KDJ K>D=above | up | 4.26 | 54.8 | +5.14 | +3.90 | +3.99 | 21.9 | none | 6.4 | 4.25 | +4.77 | +11.8 | +11.8 | +27.7 | > twins | 0 |
| 5 | 1m:PSO=low & X.SOL:RSI14=low | up | 5.25 | 53.8 | +4.12 | +1.00 | +2.39 | 21.6 | none | 6.4 | 5.24 | +4.20 | +7.3 | +6.6 | +17.3 | hot, rep, BHY | 0 |
| 6 | 5m:C-AVGPRICE=low & X.SOL:R15z=low | up | 4.32 | 54.6 | +4.89 | +1.99 | +3.86 | 21.1 | none | 4.9 | 4.32 | +3.92 | +8.8 | +8.5 | +21.2 | hot, rep | 0 |
| 7 | 1m:CMF20=low & X.SOL:R15z=low | up | 4.34 | 54.5 | +4.82 | +2.03 | +3.80 | 20.9 | none | 4.1 | 4.34 | +3.88 | +8.6 | +8.3 | +20.5 | hot, rep | 0 |
| 8 | 1m:OBV=low & X.SOL:R15z=low | up | 4.41 | 54.4 | +4.72 | +1.85 | +3.68 | 20.8 | none | 6.7 | 4.41 | +4.36 | +11.1 | +11.0 | +26.6 | hot, rep | 0 |
| 9 | 1m:IMI14=very high & 15m:C-ZLEMA21 sign=above 0 | down | 2.85 | 57.0 | +7.20 | -2.86 | +7.19 | 20.5 | none | 5.9 | 2.85 | +4.74 | +9.5 | +9.2 | +22.8 | hot, rep | 1 |
| 10 | 1m:CTI20=high & 1m:WAD=high | down | 5.10 | 53.9 | +3.99 | -1.58 | +2.97 | 20.3 | none | 5.9 | 5.10 | +3.62 | +6.7 | +7.0 | +16.2 | hot, rep | 0 |

**XRP, triples, 240 minutes, by iheat** (twins' max 11.73):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=below 0 & 1m:ER10=high & 5m:C-HMA20 sign=above 0 | up | 2.87 | 56.5 | +6.93 | +5.85 | +5.53 | 16.8 | none | 6.0 | 2.87 | +5.41 | +13.7 | +13.3 | +32.5 | > twins | 1 |
| 2 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:ER10=very high | down | 2.74 | 57.4 | +7.41 | -5.21 | +6.28 | 14.3 | pack | 10.2 | 2.73 | +5.08 | +6.8 | +6.9 | +16.4 | hot, rep, > twins | 1 |
| 3 | 1m:C-SMA20=very low/low/mid/NA & 1m:IMI14=high/very high & FLOW:Stretch15=very low/low/mid/NA | down | 4.21 | 53.7 | +3.73 | -3.27 | +3.09 | 13.8 | pack | 0.0 | 4.20 | +2.13 | +6.6 | +6.5 | +15.8 | > twins | 0 |
| 4 | 1m:CVI10 sign=above 0 & 5m:SWAK_2PHP20 sign=below 0 & 1m:C-SWAK_BUTTER20=very high | down | 2.21 | 45.8 | -4.04 | +6.01 | -6.91 | 13.3 | pack | 7.9 | 2.21 | -2.55 | -7.7 | -7.6 | -18.0 | > twins | 0 |
| 5 | 1m:CVI10 sign=above 0 & 5m:SWAK_2PHP20 sign=below 0 & 1m:SWAK_HP20=very high | down | 2.66 | 46.6 | -3.26 | +4.97 | -5.99 | 13.2 | pack | 7.3 | 2.66 | -2.37 | -7.7 | -7.7 | -18.1 | > twins | 0 |
| 6 | 1m:PVO12/26 sign=above 0 & 1m:KST>sig=above & 1m:BOP=very high | down | 3.28 | 46.5 | -3.10 | +3.96 | -4.62 | 13.0 | pack | 10.5 | 3.28 | -2.81 | -7.6 | -7.1 | -17.6 | > twins | 0 |
| 7 | 1m:DOSC sign=below 0 & 1m:ER10=high & 5m:KDJ K>D=above | up | 3.88 | 54.1 | +4.40 | +3.22 | +2.97 | 12.5 | none | 4.9 | 3.88 | +4.10 | +10.9 | +10.5 | +25.9 | > twins | 1 |
| 8 | 1m:CVI10 sign=above 0 & 5m:SWAK_2PHP20 sign=below 0 & 1m:C-EMA9=very high | down | 1.95 | 45.8 | -4.14 | +6.34 | -7.04 | 12.4 | pack | 7.5 | 1.95 | -2.50 | -8.9 | -8.9 | -21.0 | > twins | 0 |
| 9 | 1m:EFI13 sign=below 0 & 1m:AVGDEV14=high & 5m:SWAK_2PHP20=high | down | 0.99 | 62.1 | +12.04 | -12.22 | +11.46 | 12.1 | pack | 6.0 | 0.99 | +9.32 | +31.4 | +32.2 | +74.0 | > twins | 0 |
| 10 | 1m:ADX7=high & 5m:C-TSF14 sign=above 0 & 1m:C-EMA9 sign=below 0 | up | 3.00 | 54.0 | +4.30 | +3.97 | +3.66 | 11.9 | pack | 10.0 | 3.00 | +2.80 | +10.2 | +10.0 | +24.2 | > twins | 0 |

**XRP, triples, 240 minutes, by lheat** (twins' max 14.32):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:HT_QUADRATURE sign=above 0 | down | 5.18 | 54.2 | +4.31 | -1.95 | +4.25 | 22.0 | none | 4.5 | 5.18 | +2.68 | +6.1 | +6.2 | +14.7 | > twins | 0 |
| 2 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:FISHER>trig=above | down | 4.94 | 54.4 | +4.52 | -2.03 | +4.34 | 21.4 | none | 5.9 | 4.93 | +2.99 | +8.0 | +8.5 | +19.2 | hot, rep, > twins | 0 |
| 3 | 1m:DOSC sign=above 0 & 1m:ER10=high & 5m:AC sign=above 0 | down | 5.48 | 53.5 | +3.64 | -1.28 | +3.51 | 19.2 | none | 4.5 | 5.48 | +2.85 | +6.2 | +6.7 | +14.9 | > twins | 0 |
| 4 | 15m:Runs=none/3-4 up/5+ up/NA & 5m:STOCHFK5=very low/low/mid/high/NA & NY30m=08:00/10:30/14:30/15:00/16:00/16:30/17:30/23:30 | down | 3.89 | 53.6 | +3.79 | -0.56 | +4.44 | 17.3 | stored | 0.0 | 3.89 | +1.96 | +8.6 | +8.1 | +20.5 | > twins | 0 |
| 5 | 1m:CVI10=high & 5m:SWAK_2PHP20 sign=above 0 & POS:QPhase=m10-14 | down | 4.43 | 53.9 | +4.03 | -2.52 | +3.85 | 17.1 | none | 5.8 | 4.43 | +2.79 | +3.7 | +4.0 | +8.8 | > twins | 0 |
| 6 | 1m:PVO12/26 sign=above 0 & 1m:KST>sig=above & 15m:DPO20 sign=below 0 | down | 5.84 | 52.9 | +3.00 | -0.94 | +2.87 | 16.8 | pack | 10.5 | 5.83 | +2.06 | +3.6 | +3.9 | +8.5 | hot, rep, > twins | 0 |
| 7 | 5m:DOSC sign=above 0 & 5m:ER10=high & 1m:C-HT_TRENDLINE=high | down | 2.57 | 57.5 | +7.65 | -3.67 | +6.05 | 15.6 | pack | 7.0 | 2.57 | +5.86 | +13.7 | +14.0 | +33.1 | > twins | 0 |
| 8 | 5m:DOSC sign=above 0 & 5m:ER10=high & 5m:C-LINEARREG14 sign=above 0 | down | 3.16 | 54.9 | +5.03 | -1.70 | +4.87 | 15.4 | none | 6.6 | 3.14 | +4.05 | +3.0 | +3.0 | +7.2 | hot, rep, > twins | 0 |
| 9 | 1m:FISHER10 sign=above 0 & 1m:CVI10=high & 15m:CVI10 sign=above 0 | down | 3.34 | 54.3 | +4.43 | -3.04 | +4.60 | 15.4 | none | 7.6 | 3.32 | +3.99 | +2.6 | +3.2 | +6.3 | > twins | 0 |
| 10 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:IMI14=very high | down | 2.91 | 56.1 | +6.34 | -1.65 | +5.22 | 15.2 | pack | 10.2 | 2.89 | +3.53 | +1.9 | +2.1 | +4.5 | hot, rep, > twins | 1 |

**XRP, triples, 240 minutes, by oheat** (twins' max 15.70):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:FISHER>trig=above | down | 4.94 | 54.4 | +4.52 | -2.03 | +4.34 | 22.3 | none | 5.9 | 4.93 | +2.99 | +8.0 | +8.5 | +19.2 | hot, rep, > twins | 0 |
| 2 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:HT_QUADRATURE sign=above 0 | down | 5.18 | 54.2 | +4.31 | -1.95 | +4.25 | 22.3 | none | 4.5 | 5.18 | +2.68 | +6.1 | +6.2 | +14.7 | hot, rep, > twins | 0 |
| 3 | 15m:BOP sign=below 0 & 1m:CG10=very low/low & 5m:EMV14=mid/high/very high | up | 4.48 | 54.7 | +4.94 | +0.20 | +0.63 | 22.1 | pack | 8.9 | 4.48 | +4.72 | +12.8 | +12.7 | +30.5 | hot, rep, > twins | 0 |
| 4 | 15m:BOP sign=below 0 & 1m:CG10=very low/low & 1m:ERIbull13 sign=below 0/NA | up | 4.69 | 54.3 | +4.55 | -0.18 | -2.84 | 21.4 | pack | 10.6 | 4.68 | +4.63 | +14.1 | +14.2 | +33.8 | hot, rep, > twins | 0 |
| 5 | 1m:MFI14=high/very high & NY30m=00:00/00:30/01:00/01:30/02:30/03:00/03:30/04:00/04:30/05:00/05:30/06:00/07:00/07:30/08:30/09:00/09:30/10:00/10:30/11:00/11:30/12:30/13:00/13:30/14:00/14:30/15:00/15:30/16:00/16:30/17:00/17:30/18:00/19:00/21:00/21:30/22:00/22:30/23:00/23:30/NA & X.SOL:Gap5=high/very high/NA | down | 4.90 | 54.2 | +4.30 | -1.54 | +2.23 | 21.0 | pack | 0.0 | 4.89 | +3.45 | +2.0 | +2.2 | +4.8 | hot, rep, > twins | 0 |
| 6 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:ER10=very high | down | 2.74 | 57.4 | +7.41 | -5.21 | +6.28 | 20.3 | pack | 10.2 | 2.73 | +5.08 | +6.8 | +6.9 | +16.4 | hot, rep, > twins | 1 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=trend & 1m:CG10=low | up | 3.84 | 55.0 | +5.26 | +0.55 | +2.33 | 20.2 | pack | 11.7 | 3.83 | +5.35 | +18.6 | +18.4 | +44.4 | hot, rep, > twins | 0 |
| 8 | 5m:DOSC sign=above 0 & 5m:ER10=high & 1m:C-HT_TRENDLINE=high | down | 2.57 | 57.5 | +7.65 | -3.67 | +6.05 | 19.7 | pack | 7.0 | 2.57 | +5.86 | +13.7 | +14.0 | +33.1 | hot, rep, > twins | 0 |
| 9 | 1m:MACDh12/26/9 sign=above 0 & 1m:PVO12/26 sign=above 0 & 1m:RSI2=very high | down | 4.05 | 54.6 | +4.82 | -0.82 | +3.41 | 19.5 | pack | 10.2 | 4.04 | +3.78 | +4.6 | +4.4 | +11.1 | hot, rep, > twins | 1 |
| 10 | 1m:C-EMA200 sign=above 0 & 1m:C-VIDYA12=very low/low/mid/NA & UTC1h=03/04/10/15/18/19/20/21 | down | 4.80 | 53.9 | +4.00 | -1.14 | +0.34 | 19.2 | pack | 14.0 | 4.77 | +3.42 | +3.5 | +3.4 | +8.3 | hot, rep, > twins | 0 |

**XRP, triples, 240 minutes, unseen, by iheat** (twins' max 11.29):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=below 0 & 1m:ER10=high & 5m:C-HMA20 sign=above 0 | up | 2.87 | 56.5 | +6.93 | +5.85 | +5.53 | 16.8 | none | 6.0 | 2.87 | +5.41 | +13.7 | +13.3 | +32.5 | > twins | 1 |
| 2 | 1m:DOSC sign=below 0 & 1m:ER10=high & 5m:KDJ K>D=above | up | 3.88 | 54.1 | +4.40 | +3.22 | +2.97 | 12.5 | none | 4.9 | 3.88 | +4.10 | +10.9 | +10.5 | +25.9 | > twins | 1 |
| 3 | 1m:DOSC sign=below 0 & 1m:ER10=high & 5m:C-ZLEMA21 sign=above 0 | up | 3.12 | 54.3 | +4.68 | +3.79 | +3.08 | 11.8 | none | 4.9 | 3.12 | +3.31 | +5.0 | +4.4 | +11.8 | > twins | 0 |
| 4 | 1m:VHF28=high & 5m:C-TSF14 sign=below 0 & 5m:PVT sign=above 0 | down | 2.83 | 53.4 | +3.65 | -4.15 | +3.10 | 11.8 | none | 12.6 | 2.83 | +2.77 | +5.5 | +5.6 | +13.1 | > twins | 0 |
| 5 | 1m:CVI10=high & 5m:SWAK_2PHP20 sign=above 0 & POS:QPos=m12 | down | 2.38 | 56.4 | +6.33 | -4.83 | +5.14 | 11.5 | none | 5.8 | 2.38 | +6.33 | +12.8 | +12.6 | +30.2 | > twins | 0 |
| 6 | 1m:CVI10=high & 5m:SWAK_2PHP20 sign=above 0 & POS:QPhase=m10-14 | down | 4.43 | 53.9 | +4.03 | -2.52 | +3.85 | 11.2 | none | 5.8 | 4.43 | +2.79 | +3.7 | +4.0 | +8.8 | none | 0 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & 5m:AC=low | down | 4.40 | 51.5 | +1.67 | -2.49 | +2.10 | 10.9 | none | 2.6 | 4.38 | +0.35 | -0.4 | -0.2 | -1.0 | none | 0 |
| 8 | 1m:C-DEMA21 sign=above 0 & 1m:RVOL20=very high & X.ETH:Gap5=high | down | 2.51 | 48.7 | -1.26 | +4.18 | -5.07 | 10.5 | none | 6.0 | 2.51 | -0.95 | -2.7 | -3.0 | -6.3 | none | 1 |
| 9 | 1m:FISHER10 sign=above 0 & 1m:CVI10=high & 1m:ADR14=high | down | 2.11 | 56.2 | +6.20 | -4.94 | +5.48 | 10.4 | none | 7.6 | 2.09 | +5.77 | +10.0 | +10.0 | +23.7 | none | 0 |
| 10 | 1m:VHF28=high & 5m:C-TSF14 sign=below 0 & 5m:PVI sign=above 0 | down | 2.97 | 52.7 | +2.98 | -3.45 | +2.39 | 10.3 | none | 12.0 | 2.97 | +2.60 | +3.4 | +3.4 | +8.2 | none | 0 |

**XRP, triples, 240 minutes, unseen, by lheat** (twins' max 14.32):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:HT_QUADRATURE sign=above 0 | down | 5.18 | 54.2 | +4.31 | -1.95 | +4.25 | 22.0 | none | 4.5 | 5.18 | +2.68 | +6.1 | +6.2 | +14.7 | > twins | 0 |
| 2 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:FISHER>trig=above | down | 4.94 | 54.4 | +4.52 | -2.03 | +4.34 | 21.4 | none | 5.9 | 4.93 | +2.99 | +8.0 | +8.5 | +19.2 | hot, rep, > twins | 0 |
| 3 | 1m:DOSC sign=above 0 & 1m:ER10=high & 5m:AC sign=above 0 | down | 5.48 | 53.5 | +3.64 | -1.28 | +3.51 | 19.2 | none | 4.5 | 5.48 | +2.85 | +6.2 | +6.7 | +14.9 | > twins | 0 |
| 4 | 1m:CVI10=high & 5m:SWAK_2PHP20 sign=above 0 & POS:QPhase=m10-14 | down | 4.43 | 53.9 | +4.03 | -2.52 | +3.85 | 17.1 | none | 5.8 | 4.43 | +2.79 | +3.7 | +4.0 | +8.8 | > twins | 0 |
| 5 | 5m:DOSC sign=above 0 & 5m:ER10=high & 5m:C-LINEARREG14 sign=above 0 | down | 3.16 | 54.9 | +5.03 | -1.70 | +4.87 | 15.4 | none | 6.6 | 3.14 | +4.05 | +3.0 | +3.0 | +7.2 | hot, rep, > twins | 0 |
| 6 | 1m:FISHER10 sign=above 0 & 1m:CVI10=high & 15m:CVI10 sign=above 0 | down | 3.34 | 54.3 | +4.43 | -3.04 | +4.60 | 15.4 | none | 7.6 | 3.32 | +3.99 | +2.6 | +3.2 | +6.3 | > twins | 0 |
| 7 | 1m:CVI10=high & 5m:SWAK_2PHP20 sign=above 0 & 15m:DPO20 sign=below 0 | down | 4.41 | 53.8 | +3.92 | -1.77 | +3.36 | 14.8 | none | 7.6 | 4.40 | +2.25 | +3.5 | +3.7 | +8.2 | > twins | 0 |
| 8 | 1m:STDDEV20=high & 5m:C-DEMA21 sign=above 0 & 1m:BBW20=high | down | 4.05 | 52.1 | +2.22 | -0.05 | +3.65 | 14.8 | none | 6.1 | 3.99 | +2.84 | -0.4 | +0.1 | -1.0 | > twins | 1 |
| 9 | 1m:STC=very low/low/mid/NA & 60m:VORTEXdiff14=very low/low/mid/NA & X.SOL:RSI14=very low/low/very high | up | 5.60 | 52.1 | +2.40 | +0.53 | +2.59 | 14.5 | none | 0.0 | 5.60 | +1.71 | -1.5 | -1.5 | -3.6 | hot, rep, > twins | 0 |
| 10 | 5m:DOSC sign=above 0 & 5m:ER10=high & 15m:AD sign=above 0 | down | 2.97 | 54.9 | +5.07 | -1.79 | +4.80 | 14.3 | none | 6.7 | 2.91 | +3.24 | +4.3 | +4.1 | +10.4 | none | 0 |

**XRP, triples, 240 minutes, unseen, by oheat** (twins' max 14.55):

| # | cell | dir | windows/day B | share right B % | odds B | iota_robust B | lift B | heat | seen | part t | onset windows/day | onset odds B | onset move bps | late | steps | marks | aliases |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:FISHER>trig=above | down | 4.94 | 54.4 | +4.52 | -2.03 | +4.34 | 22.3 | none | 5.9 | 4.93 | +2.99 | +8.0 | +8.5 | +19.2 | hot, rep, > twins | 0 |
| 2 | 1m:DOSC sign=above 0 & 1m:ER10=high & 15m:HT_QUADRATURE sign=above 0 | down | 5.18 | 54.2 | +4.31 | -1.95 | +4.25 | 22.3 | none | 4.5 | 5.18 | +2.68 | +6.1 | +6.2 | +14.7 | hot, rep, > twins | 0 |
| 3 | 1m:DOSC sign=above 0 & 1m:ER10=high & 5m:AC sign=above 0 | down | 5.48 | 53.5 | +3.64 | -1.28 | +3.51 | 20.0 | none | 4.5 | 5.48 | +2.85 | +6.2 | +6.7 | +14.9 | hot, rep, > twins | 0 |
| 4 | 1m:CVI10=high & 5m:SWAK_2PHP20 sign=above 0 & POS:QPhase=m10-14 | down | 4.43 | 53.9 | +4.03 | -2.52 | +3.85 | 17.9 | none | 5.8 | 4.43 | +2.79 | +3.7 | +4.0 | +8.8 | hot, rep, > twins | 0 |
| 5 | 1m:STOCHFK5=very low/high/NA & 5m:AD sign=above 0/NA & 60m:NVI sign=below 0/NA | down | 3.55 | 54.8 | +4.90 | -1.28 | +1.53 | 17.4 | none | 7.0 | 3.55 | +4.91 | +11.9 | +11.7 | +28.6 | > twins | 0 |
| 6 | 1m:CVI10=high & 5m:SWAK_2PHP20 sign=above 0 & 15m:DPO20 sign=below 0 | down | 4.41 | 53.8 | +3.92 | -1.77 | +3.36 | 17.3 | none | 7.6 | 4.40 | +2.25 | +3.5 | +3.7 | +8.2 | hot, rep, > twins | 0 |
| 7 | 1m:SINE>LEAD=below & 1m:HT_TRENDMODE=cycle & X.SOL:RSI14=low | up | 5.54 | 52.8 | +3.12 | +0.56 | +1.18 | 17.3 | none | 3.0 | 5.54 | +2.91 | +4.5 | +4.6 | +10.8 | > twins | 0 |
| 8 | 1m:FISHER10 sign=above 0 & 1m:CVI10=high & 15m:DPO20 sign=below 0 | down | 4.16 | 54.0 | +4.10 | -1.80 | +3.54 | 17.1 | none | 7.6 | 4.15 | +3.02 | +4.9 | +5.1 | +11.6 | hot, rep, > twins | 0 |
| 9 | 5m:CVI10 sign=above 0 & 5m:KST>sig=above & X.BTC:RSI14=high | down | 4.22 | 53.8 | +4.01 | -1.24 | +2.98 | 16.9 | none | 8.7 | 4.22 | +3.78 | +5.5 | +5.3 | +13.0 | hot, rep, > twins | 0 |
| 10 | 5m:DOSC sign=above 0 & 5m:ER10=high & 1m:LRSLOPE14=high | down | 2.27 | 57.1 | +7.28 | -3.63 | +5.29 | 16.5 | none | 6.6 | 2.26 | +5.49 | +12.2 | +12.0 | +29.5 | hot, rep, > twins | 0 |

## 6. The pack for the bot

hm2_pack.json (published to research/oracle_heat/latest/): 3,668 rows (2,365 from the unseen lists' cells, 0 Part 3 gate rows), 0 live ready. A row fires at the first minute close at which every condition holds; the entry is the next minute's open. live_ready needs the live reader's parity on Dec 29-31, 2025 (at least 99.5% of minutes) for every reading of the row and the feed the bot needs for it. The bot loads the pack behind its own switch, default off (the bot lane's work).

| coin | minutes | kind | rows |
|---|---|---|---|
| BTC | 15 | model | 8 |
| BTC | 15 | pair | 154 |
| BTC | 15 | triple | 166 |
| BTC | 240 | model | 8 |
| BTC | 240 | pair | 139 |
| BTC | 240 | triple | 138 |
| BTC | 60 | model | 8 |
| BTC | 60 | pair | 158 |
| BTC | 60 | triple | 153 |
| ETH | 15 | model | 8 |
| ETH | 15 | pair | 151 |
| ETH | 15 | triple | 169 |
| ETH | 240 | model | 8 |
| ETH | 240 | pair | 148 |
| ETH | 240 | triple | 134 |
| ETH | 60 | model | 8 |
| ETH | 60 | pair | 165 |
| ETH | 60 | triple | 146 |
| SOL | 15 | model | 8 |
| SOL | 15 | pair | 146 |
| SOL | 15 | triple | 145 |
| SOL | 240 | model | 8 |
| SOL | 240 | pair | 141 |
| SOL | 240 | triple | 128 |
| SOL | 60 | model | 8 |
| SOL | 60 | pair | 150 |
| SOL | 60 | triple | 147 |
| XRP | 15 | model | 8 |
| XRP | 15 | pair | 131 |
| XRP | 15 | triple | 159 |
| XRP | 240 | model | 8 |
| XRP | 240 | pair | 132 |
| XRP | 240 | triple | 139 |
| XRP | 60 | model | 8 |
| XRP | 60 | pair | 165 |
| XRP | 60 | triple | 168 |

<!-- hm2:section:part3 -->
## Part 3: what separates the winners

Part 3 (python/oracle/heat_hm2_drill.py) has not merged its gate rows yet. Its league writes research/oracle_heat/hm2/part3/league.md, puts its gate rows into hm2_pack.json (kind gate / gate2) and fills this section (upsert_section(..., "part3", ...)).
<!-- /hm2:section:part3 -->

<!-- hm2:section:part4 -->
## Chart patterns (Part 4)

Schema oracle-heat-chart-league-1; coins BTC, ETH, SOL, XRP.

series of run 43030435253; HM2 league job 43221480254 at commit 3cafcd195d60a773bfe2fc636fec88802b0925f9

Series: BTC~twin1, BTC~twin2, BTC~twin3, BTC, ETH~twin1, ETH~twin2, ETH~twin3, ETH, SOL~twin1, SOL~twin2, SOL~twin3, SOL, XRP~twin1, XRP~twin2, XRP~twin3, XRP.

### Chance table

Instances per day on each split, the real coin against its twins (median, range).

| coin | frame | pattern | split | per day | twins | tbi - p_rw |
|---|---|---|---|---|---|---|
| BTC | 15m:K | LMW.BBOT | A | 0.519 | 0.866 (0.857-0.882) | -0.005 |
| BTC | 15m:K | LMW.BBOT | B | 0.655 | 0.866 (0.838-0.871) | +0.026 |
| BTC | 15m:K | LMW.BTOP | A | 0.56 | 0.855 (0.843-0.857) | -0.001 |
| BTC | 15m:K | LMW.BTOP | B | 0.743 | 0.869 (0.773-0.869) | -0.013 |
| BTC | 15m:K | LMW.DBOT | A | 0.411 | 0.473 (0.437-0.481) | -0.057 |
| BTC | 15m:K | LMW.DBOT | B | 0.518 | 0.529 (0.507-0.564) | +0.036 |
| BTC | 15m:K | LMW.DTOP | A | 0.461 | 0.444 (0.443-0.466) | -0.024 |
| BTC | 15m:K | LMW.DTOP | B | 0.482 | 0.586 (0.499-0.636) | -0.030 |
| BTC | 15m:K | LMW.HS | A | 5.32 | 4.93 (4.92-4.94) | -0.040 |
| BTC | 15m:K | LMW.HS | B | 5.14 | 5.02 (5.01-5.12) | -0.042 |
| BTC | 15m:K | LMW.HS.SWZ | A | 0.00547 | 0.00493 (0.00383-0.00547) | -0.173 |
| BTC | 15m:K | LMW.HS.SWZ | B | 0 | 0 (0-0) |  |
| BTC | 15m:K | LMW.IHS | A | 5.37 | 4.91 (4.87-4.95) | -0.031 |
| BTC | 15m:K | LMW.IHS | B | 5.14 | 4.98 (4.94-5.02) | -0.030 |
| BTC | 15m:K | LMW.IHS.SWZ | A | 0.00602 | 0.00383 (0.00328-0.00602) | -0.230 |
| BTC | 15m:K | LMW.IHS.SWZ | B | 0 | 0 (0-0.00274) |  |
| BTC | 15m:K | LMW.RBOT | A | 18.7 | 16.7 (16.7-16.7) | -0.009 |
| BTC | 15m:K | LMW.RBOT | B | 19.5 | 18.2 (18.1-18.2) | -0.003 |
| BTC | 15m:K | LMW.RTOP | A | 19 | 16.7 (16.7-16.8) | -0.010 |
| BTC | 15m:K | LMW.RTOP | B | 19.7 | 18.2 (18.1-18.2) | -0.004 |
| BTC | 15m:K | LMW.TBOT | A | 1.6 | 1.08 (1.07-1.08) | -0.350 |
| BTC | 15m:K | LMW.TBOT | B | 1.43 | 1.05 (1.03-1.07) | -0.354 |
| BTC | 15m:K | LMW.TTOP | A | 1.58 | 1.08 (1.06-1.11) | -0.373 |
| BTC | 15m:K | LMW.TTOP | B | 1.4 | 1.03 (0.997-1.1) | -0.329 |
| BTC | 15m:z2 | ABCD.BEAR | A | 0.184 | 0.232 (0.217-0.234) | -0.028 |
| BTC | 15m:z2 | ABCD.BEAR | B | 0.233 | 0.244 (0.222-0.274) | -0.036 |
| BTC | 15m:z2 | ABCD.BULL | A | 0.201 | 0.219 (0.209-0.256) | -0.012 |
| BTC | 15m:z2 | ABCD.BULL | B | 0.233 | 0.285 (0.274-0.301) | -0.023 |
| BTC | 15m:z2 | ASCTRI | A | 0.524 | 0.539 (0.506-0.54) | +0.022 |
| BTC | 15m:z2 | ASCTRI | B | 0.6 | 0.603 (0.545-0.606) | -0.040 |
| BTC | 15m:z2 | BEARFLAG | A | 0.344 | 0.411 (0.4-0.419) | -0.009 |
| BTC | 15m:z2 | BEARFLAG | B | 0.334 | 0.395 (0.362-0.397) | +0.049 |
| BTC | 15m:z2 | BEARPEN | A | 0.171 | 0.155 (0.131-0.164) | +0.017 |
| BTC | 15m:z2 | BEARPEN | B | 0.189 | 0.129 (0.123-0.142) | +0.079 |
| BTC | 15m:z2 | BROADBOT | A | 0.0794 | 0.102 (0.0969-0.127) | -0.021 |
| BTC | 15m:z2 | BROADBOT | B | 0.107 | 0.129 (0.0904-0.132) | +0.007 |
| BTC | 15m:z2 | BROADTOP | A | 0.0827 | 0.113 (0.0991-0.118) | +0.145 |
| BTC | 15m:z2 | BROADTOP | B | 0.0986 | 0.11 (0.0849-0.145) | +0.094 |
| BTC | 15m:z2 | BULLFLAG | A | 0.417 | 0.371 (0.369-0.373) | +0.003 |
| BTC | 15m:z2 | BULLFLAG | B | 0.419 | 0.411 (0.373-0.46) | +0.048 |
| BTC | 15m:z2 | BULLPEN | A | 0.192 | 0.141 (0.138-0.146) | +0.011 |
| BTC | 15m:z2 | BULLPEN | B | 0.167 | 0.14 (0.107-0.153) | +0.105 |
| BTC | 15m:z2 | CUP | A | 0.0504 | 0.0766 (0.0662-0.0777) | -0.010 |
| BTC | 15m:z2 | CUP | B | 0.0603 | 0.0986 (0.0575-0.107) | +0.011 |
| BTC | 15m:z2 | DBOT | A | 1.47 | 1.58 (1.56-1.59) | -0.039 |
| BTC | 15m:z2 | DBOT | B | 1.63 | 1.59 (1.56-1.62) | +0.023 |
| BTC | 15m:z2 | DESCTRI | A | 0.501 | 0.556 (0.541-0.558) | +0.034 |
| BTC | 15m:z2 | DESCTRI | B | 0.488 | 0.592 (0.564-0.592) | +0.034 |
| BTC | 15m:z2 | DTOP | A | 1.64 | 1.55 (1.54-1.56) | -0.022 |
| BTC | 15m:z2 | DTOP | B | 1.7 | 1.65 (1.58-1.68) | -0.007 |
| BTC | 15m:z2 | FALWEDGE | A | 0.753 | 0.772 (0.74-0.785) | +0.013 |
| BTC | 15m:z2 | FALWEDGE | B | 0.855 | 0.819 (0.775-0.841) | -0.011 |
| BTC | 15m:z2 | HARM.BEAR | A | 0.0421 | 0.0383 (0.0345-0.0394) | -0.054 |
| BTC | 15m:z2 | HARM.BEAR | B | 0.0384 | 0.0384 (0.0247-0.0521) | -0.122 |
| BTC | 15m:z2 | HARM.BULL | A | 0.0465 | 0.0411 (0.0345-0.0421) | +0.052 |
| BTC | 15m:z2 | HARM.BULL | B | 0.0603 | 0.0438 (0.0411-0.0466) | -0.163 |
| BTC | 15m:z2 | HS | A | 0.287 | 0.273 (0.254-0.274) | +0.016 |
| BTC | 15m:z2 | HS | B | 0.258 | 0.296 (0.279-0.301) | +0.015 |
| BTC | 15m:z2 | IHS | A | 0.273 | 0.275 (0.267-0.275) | +0.071 |
| BTC | 15m:z2 | IHS | B | 0.258 | 0.293 (0.255-0.332) | +0.110 |
| BTC | 15m:z2 | INVCUP | A | 0.0608 | 0.0673 (0.0668-0.075) | +0.077 |
| BTC | 15m:z2 | INVCUP | B | 0.0658 | 0.0795 (0.0685-0.0877) | +0.058 |
| BTC | 15m:z2 | RECT | A | 0.113 | 0.146 (0.137-0.17) | -0.006 |
| BTC | 15m:z2 | RECT | B | 0.0932 | 0.145 (0.14-0.148) | -0.056 |
| BTC | 15m:z2 | RISWEDGE | A | 0.744 | 0.765 (0.758-0.784) | +0.006 |
| BTC | 15m:z2 | RISWEDGE | B | 0.825 | 0.869 (0.833-0.91) | -0.007 |
| BTC | 15m:z2 | ROUNDBOT | A | 0.0985 | 0.244 (0.232-0.248) | -0.135 |
| BTC | 15m:z2 | ROUNDBOT | B | 0.134 | 0.241 (0.238-0.241) | +0.011 |
| BTC | 15m:z2 | ROUNDTOP | A | 0.169 | 0.209 (0.208-0.221) | -0.149 |
| BTC | 15m:z2 | ROUNDTOP | B | 0.211 | 0.208 (0.203-0.279) | -0.095 |
| BTC | 15m:z2 | SYMTRI | A | 0.739 | 0.655 (0.654-0.657) | +0.036 |
| BTC | 15m:z2 | SYMTRI | B | 0.756 | 0.751 (0.69-0.77) | +0.032 |
| BTC | 15m:z2 | TRIBOT | A | 0.16 | 0.219 (0.203-0.242) | -0.051 |
| BTC | 15m:z2 | TRIBOT | B | 0.153 | 0.203 (0.186-0.247) | -0.042 |
| BTC | 15m:z2 | TRITOP | A | 0.191 | 0.217 (0.203-0.235) | -0.055 |
| BTC | 15m:z2 | TRITOP | B | 0.249 | 0.236 (0.214-0.252) | +0.059 |
| BTC | 15m:z4 | ABCD.BEAR | A | 0.0624 | 0.0805 (0.0799-0.0865) | +0.049 |
| BTC | 15m:z4 | ABCD.BEAR | B | 0.0877 | 0.0932 (0.074-0.11) | +0.020 |
| BTC | 15m:z4 | ABCD.BULL | A | 0.069 | 0.0772 (0.075-0.0816) | +0.008 |
| BTC | 15m:z4 | ABCD.BULL | B | 0.0795 | 0.0904 (0.0849-0.0932) | +0.092 |
| BTC | 15m:z4 | ASCTRI | A | 0.203 | 0.2 (0.184-0.218) | +0.023 |
| BTC | 15m:z4 | ASCTRI | B | 0.214 | 0.214 (0.211-0.227) | +0.077 |
| BTC | 15m:z4 | BEARFLAG | A | 0.0608 | 0.0755 (0.0755-0.0859) | -0.028 |
| BTC | 15m:z4 | BEARFLAG | B | 0.0685 | 0.0849 (0.0548-0.0986) | -0.102 |
| BTC | 15m:z4 | BEARPEN | A | 0.0334 | 0.0328 (0.0241-0.0334) | +0.106 |
| BTC | 15m:z4 | BEARPEN | B | 0.0521 | 0.0301 (0.0247-0.0384) | -0.059 |
| BTC | 15m:z4 | BROADBOT | A | 0.0219 | 0.0356 (0.035-0.0361) | +0.019 |
| BTC | 15m:z4 | BROADBOT | B | 0.0301 | 0.0438 (0.0329-0.0493) | -0.554 |
| BTC | 15m:z4 | BROADTOP | A | 0.0257 | 0.0356 (0.0356-0.0361) | +0.221 |
| BTC | 15m:z4 | BROADTOP | B | 0.0247 | 0.0466 (0.0356-0.0493) | +0.370 |
| BTC | 15m:z4 | BULLFLAG | A | 0.0662 | 0.0744 (0.0646-0.0821) | +0.029 |
| BTC | 15m:z4 | BULLFLAG | B | 0.0603 | 0.0932 (0.0685-0.11) | +0.031 |
| BTC | 15m:z4 | BULLPEN | A | 0.0394 | 0.0312 (0.0257-0.0356) | -0.015 |
| BTC | 15m:z4 | BULLPEN | B | 0.0274 | 0.0411 (0.0329-0.0521) | -0.003 |
| BTC | 15m:z4 | CUP | A | 0.0197 | 0.0285 (0.0279-0.0454) | -0.043 |
| BTC | 15m:z4 | CUP | B | 0.0219 | 0.0301 (0.0274-0.0438) | +0.375 |
| BTC | 15m:z4 | DBOT | A | 0.57 | 0.672 (0.654-0.672) | -0.033 |
| BTC | 15m:z4 | DBOT | B | 0.666 | 0.748 (0.729-0.754) | +0.059 |
| BTC | 15m:z4 | DESCTRI | A | 0.153 | 0.204 (0.197-0.219) | +0.108 |
| BTC | 15m:z4 | DESCTRI | B | 0.233 | 0.233 (0.233-0.247) | +0.122 |
| BTC | 15m:z4 | DTOP | A | 0.634 | 0.679 (0.648-0.685) | -0.005 |
| BTC | 15m:z4 | DTOP | B | 0.677 | 0.751 (0.712-0.792) | +0.030 |
| BTC | 15m:z4 | FALWEDGE | A | 0.219 | 0.279 (0.256-0.294) | -0.008 |
| BTC | 15m:z4 | FALWEDGE | B | 0.244 | 0.304 (0.285-0.362) | -0.092 |
| BTC | 15m:z4 | HARM.BEAR | A | 0.0131 | 0.0131 (0.0115-0.0148) | +0.173 |
| BTC | 15m:z4 | HARM.BEAR | B | 0.00822 | 0.0137 (0.011-0.0274) | +0.495 |
| BTC | 15m:z4 | HARM.BULL | A | 0.0208 | 0.0159 (0.00985-0.0159) | +0.050 |
| BTC | 15m:z4 | HARM.BULL | B | 0.0192 | 0.0219 (0.0137-0.0274) | -0.027 |
| BTC | 15m:z4 | HS | A | 0.0887 | 0.0985 (0.0865-0.102) | +0.060 |
| BTC | 15m:z4 | HS | B | 0.123 | 0.101 (0.0986-0.129) | -0.100 |
| BTC | 15m:z4 | IHS | A | 0.0952 | 0.0996 (0.0832-0.101) | -0.039 |
| BTC | 15m:z4 | IHS | B | 0.0795 | 0.107 (0.0877-0.121) | +0.239 |
| BTC | 15m:z4 | INVCUP | A | 0.0241 | 0.0323 (0.0317-0.0367) | -0.007 |
| BTC | 15m:z4 | INVCUP | B | 0.0384 | 0.0301 (0.0164-0.0301) | +0.166 |
| BTC | 15m:z4 | RECT | A | 0.0378 | 0.0608 (0.0547-0.0613) | -0.135 |
| BTC | 15m:z4 | RECT | B | 0.0438 | 0.063 (0.0548-0.0822) | -0.023 |
| BTC | 15m:z4 | RISWEDGE | A | 0.279 | 0.278 (0.252-0.278) | +0.022 |
| BTC | 15m:z4 | RISWEDGE | B | 0.277 | 0.37 (0.282-0.375) | -0.049 |
| BTC | 15m:z4 | ROUNDBOT | A | 0.105 | 0.185 (0.179-0.188) | -0.172 |
| BTC | 15m:z4 | ROUNDBOT | B | 0.167 | 0.178 (0.164-0.189) | +0.414 |
| BTC | 15m:z4 | ROUNDTOP | A | 0.125 | 0.17 (0.163-0.175) | +0.171 |
| BTC | 15m:z4 | ROUNDTOP | B | 0.173 | 0.214 (0.206-0.214) | +0.379 |
| BTC | 15m:z4 | SYMTRI | A | 0.293 | 0.267 (0.259-0.274) | +0.096 |
| BTC | 15m:z4 | SYMTRI | B | 0.318 | 0.285 (0.258-0.348) | +0.055 |
| BTC | 15m:z4 | TRIBOT | A | 0.0443 | 0.087 (0.0832-0.0958) | -0.108 |
| BTC | 15m:z4 | TRIBOT | B | 0.0795 | 0.11 (0.0849-0.132) | -0.144 |
| BTC | 15m:z4 | TRITOP | A | 0.0564 | 0.0854 (0.0805-0.0881) | -0.027 |
| BTC | 15m:z4 | TRITOP | B | 0.0712 | 0.0932 (0.0904-0.0959) | -0.321 |
| BTC | 15m:z8 | ABCD.BEAR | A | 0.0219 | 0.0241 (0.0235-0.0257) | +0.176 |
| BTC | 15m:z8 | ABCD.BEAR | B | 0.0301 | 0.0247 (0.0247-0.0356) | +0.082 |
| BTC | 15m:z8 | ABCD.BULL | A | 0.0192 | 0.0235 (0.023-0.0252) | -0.106 |
| BTC | 15m:z8 | ABCD.BULL | B | 0.0192 | 0.0274 (0.0247-0.0384) | -0.063 |
| BTC | 15m:z8 | ASCTRI | A | 0.0673 | 0.0542 (0.0531-0.0553) | +0.051 |
| BTC | 15m:z8 | ASCTRI | B | 0.0767 | 0.0712 (0.0548-0.0849) | -0.112 |
| BTC | 15m:z8 | BEARFLAG | A | 0.00438 | 0.00438 (0.00328-0.00657) | +0.069 |
| BTC | 15m:z8 | BEARFLAG | B | 0.00274 | 0.00548 (0.00274-0.00548) | -0.066 |
| BTC | 15m:z8 | BEARPEN | A | 0.00164 | 0.000547 (0-0.00383) | +0.271 |
| BTC | 15m:z8 | BEARPEN | B | 0.00274 | 0.00274 (0-0.00274) |  |
| BTC | 15m:z8 | BROADBOT | A | 0.00547 | 0.00931 (0.00438-0.0109) |  |
| BTC | 15m:z8 | BROADBOT | B | 0.00822 | 0.00274 (0.00274-0.00548) | -0.067 |
| BTC | 15m:z8 | BROADTOP | A | 0.00766 | 0.00712 (0.00657-0.0104) | -0.207 |
| BTC | 15m:z8 | BROADTOP | B | 0.011 | 0.00548 (0.00274-0.00548) |  |
| BTC | 15m:z8 | BULLFLAG | A | 0.00219 | 0.00602 (0.00438-0.00876) | -0.076 |
| BTC | 15m:z8 | BULLFLAG | B | 0.00548 | 0.00548 (0.00548-0.011) | -0.055 |
| BTC | 15m:z8 | BULLPEN | A | 0.00164 | 0.00219 (0.00164-0.00219) | -0.085 |
| BTC | 15m:z8 | BULLPEN | B | 0.00548 | 0 (0-0.00822) | -0.113 |
| BTC | 15m:z8 | CUP | A | 0.00821 | 0.00931 (0.00547-0.0104) | +0.240 |
| BTC | 15m:z8 | CUP | B | 0.011 | 0.0164 (0.00822-0.0164) | +0.327 |
| BTC | 15m:z8 | DBOT | A | 0.172 | 0.215 (0.198-0.219) | -0.024 |
| BTC | 15m:z8 | DBOT | B | 0.244 | 0.219 (0.216-0.227) | +0.022 |
| BTC | 15m:z8 | DESCTRI | A | 0.0602 | 0.0635 (0.0613-0.069) | +0.116 |
| BTC | 15m:z8 | DESCTRI | B | 0.0767 | 0.0712 (0.0603-0.0822) | -0.031 |
| BTC | 15m:z8 | DTOP | A | 0.199 | 0.2 (0.193-0.232) | +0.077 |
| BTC | 15m:z8 | DTOP | B | 0.249 | 0.225 (0.203-0.247) | -0.089 |
| BTC | 15m:z8 | FALWEDGE | A | 0.0624 | 0.0854 (0.0728-0.0865) | +0.153 |
| BTC | 15m:z8 | FALWEDGE | B | 0.0603 | 0.0877 (0.0849-0.101) | +0.068 |
| BTC | 15m:z8 | HARM.BEAR | A | 0.00657 | 0.00383 (0.00328-0.00602) | +0.087 |
| BTC | 15m:z8 | HARM.BEAR | B | 0.00274 | 0.00274 (0.00274-0.00822) | -0.190 |
| BTC | 15m:z8 | HARM.BULL | A | 0.00493 | 0.00493 (0.00438-0.00602) | +0.105 |
| BTC | 15m:z8 | HARM.BULL | B | 0.00548 | 0.00548 (0-0.00822) | +0.618 |
| BTC | 15m:z8 | HS | A | 0.0268 | 0.0301 (0.0296-0.035) | -0.049 |
| BTC | 15m:z8 | HS | B | 0.0575 | 0.0301 (0.0219-0.0411) | +0.174 |
| BTC | 15m:z8 | IHS | A | 0.0296 | 0.0257 (0.0252-0.0285) | +0.031 |
| BTC | 15m:z8 | IHS | B | 0.0274 | 0.0329 (0.0219-0.0466) | -0.112 |
| BTC | 15m:z8 | INVCUP | A | 0.00657 | 0.00985 (0.00931-0.0142) | -0.194 |
| BTC | 15m:z8 | INVCUP | B | 0.00822 | 0.00822 (0.00822-0.0137) | +0.663 |
| BTC | 15m:z8 | RECT | A | 0.00985 | 0.017 (0.0148-0.0192) | -0.044 |
| BTC | 15m:z8 | RECT | B | 0.00548 | 0.00822 (0.00822-0.0137) | -0.045 |
| BTC | 15m:z8 | RISWEDGE | A | 0.0712 | 0.075 (0.0717-0.0837) | -0.072 |
| BTC | 15m:z8 | RISWEDGE | B | 0.0822 | 0.0712 (0.0521-0.104) | -0.004 |
| BTC | 15m:z8 | ROUNDBOT | A | 0.0328 | 0.0504 (0.0416-0.0515) | +0.027 |
| BTC | 15m:z8 | ROUNDBOT | B | 0.0603 | 0.0575 (0.0438-0.0658) | +0.647 |
| BTC | 15m:z8 | ROUNDTOP | A | 0.0449 | 0.0465 (0.0465-0.052) | +0.090 |
| BTC | 15m:z8 | ROUNDTOP | B | 0.0521 | 0.0575 (0.0466-0.0658) |  |
| BTC | 15m:z8 | SYMTRI | A | 0.0925 | 0.0898 (0.0816-0.0903) | +0.116 |
| BTC | 15m:z8 | SYMTRI | B | 0.101 | 0.0959 (0.0932-0.101) | +0.011 |
| BTC | 15m:z8 | TRIBOT | A | 0.0159 | 0.023 (0.0192-0.0317) | -0.156 |
| BTC | 15m:z8 | TRIBOT | B | 0.0329 | 0.0192 (0.0192-0.0329) | +0.163 |
| BTC | 15m:z8 | TRITOP | A | 0.0192 | 0.017 (0.017-0.0274) | +0.040 |
| BTC | 15m:z8 | TRITOP | B | 0.0219 | 0.0192 (0.0192-0.0247) | -0.341 |
| BTC | 240m:K | LMW.BBOT | A | 0.029 | 0.0476 (0.0432-0.0482) | -0.055 |
| BTC | 240m:K | LMW.BBOT | B | 0.0548 | 0.0548 (0.0521-0.0575) | -0.209 |
| BTC | 240m:K | LMW.BTOP | A | 0.0345 | 0.0493 (0.0427-0.0493) | +0.096 |
| BTC | 240m:K | LMW.BTOP | B | 0.0575 | 0.0521 (0.0384-0.074) | +0.024 |
| BTC | 240m:K | LMW.DBOT | A | 0.00547 | 0.00438 (0.00438-0.00493) | -0.314 |
| BTC | 240m:K | LMW.DBOT | B | 0.00822 | 0.011 (0.00274-0.0137) | -0.033 |
| BTC | 240m:K | LMW.DTOP | A | 0.00547 | 0.00438 (0.00219-0.00712) | +0.405 |
| BTC | 240m:K | LMW.DTOP | B | 0.00548 | 0.00822 (0.00274-0.011) | +0.428 |
| BTC | 240m:K | LMW.HS | A | 0.218 | 0.189 (0.181-0.197) | -0.076 |
| BTC | 240m:K | LMW.HS | B | 0.29 | 0.263 (0.247-0.263) | -0.048 |
| BTC | 240m:K | LMW.HS.SWZ | A | 0.00493 | 0.00383 (0.00328-0.00602) | +0.112 |
| BTC | 240m:K | LMW.HS.SWZ | B | 0.00548 | 0.00548 (0.00548-0.011) | -0.560 |
| BTC | 240m:K | LMW.IHS | A | 0.216 | 0.195 (0.179-0.198) | -0.043 |
| BTC | 240m:K | LMW.IHS | B | 0.288 | 0.271 (0.266-0.282) | -0.055 |
| BTC | 240m:K | LMW.IHS.SWZ | A | 0.00438 | 0.00328 (0.00219-0.00438) | +0.017 |
| BTC | 240m:K | LMW.IHS.SWZ | B | 0 | 0.00274 (0.00274-0.00822) |  |
| BTC | 240m:K | LMW.RBOT | A | 0.368 | 0.292 (0.283-0.301) | -0.002 |
| BTC | 240m:K | LMW.RBOT | B | 0.534 | 0.543 (0.496-0.548) | -0.035 |
| BTC | 240m:K | LMW.RTOP | A | 0.383 | 0.3 (0.277-0.303) | -0.003 |
| BTC | 240m:K | LMW.RTOP | B | 0.559 | 0.526 (0.493-0.57) | -0.053 |
| BTC | 240m:K | LMW.TBOT | A | 0.092 | 0.0613 (0.0575-0.064) | -0.386 |
| BTC | 240m:K | LMW.TBOT | B | 0.101 | 0.0822 (0.0658-0.0822) | -0.315 |
| BTC | 240m:K | LMW.TTOP | A | 0.0892 | 0.0542 (0.052-0.0558) | -0.400 |
| BTC | 240m:K | LMW.TTOP | B | 0.0959 | 0.0849 (0.0822-0.0959) | -0.400 |
| BTC | 240m:z2 | ABCD.BEAR | A | 0.012 | 0.0131 (0.00931-0.0148) | +0.015 |
| BTC | 240m:z2 | ABCD.BEAR | B | 0.00822 | 0.011 (0.00822-0.0164) | +0.045 |
| BTC | 240m:z2 | ABCD.BULL | A | 0.00985 | 0.00766 (0.00602-0.0126) | +0.098 |
| BTC | 240m:z2 | ABCD.BULL | B | 0.0192 | 0.0137 (0.00548-0.0164) | -0.009 |
| BTC | 240m:z2 | ASCTRI | A | 0.0334 | 0.0235 (0.0192-0.0317) | -0.009 |
| BTC | 240m:z2 | ASCTRI | B | 0.0356 | 0.0301 (0.0274-0.0438) | +0.053 |
| BTC | 240m:z2 | BEARFLAG | A | 0.0257 | 0.0186 (0.0142-0.0263) | -0.003 |
| BTC | 240m:z2 | BEARFLAG | B | 0.0274 | 0.0274 (0.0219-0.0301) | +0.212 |
| BTC | 240m:z2 | BEARPEN | A | 0.0164 | 0.00876 (0.00328-0.00985) | +0.026 |
| BTC | 240m:z2 | BEARPEN | B | 0.0192 | 0.011 (0.00274-0.0164) | -0.019 |
| BTC | 240m:z2 | BROADBOT | A | 0.00438 | 0.00602 (0.00438-0.00712) |  |
| BTC | 240m:z2 | BROADBOT | B | 0.011 | 0.00274 (0.00274-0.00548) | +0.408 |
| BTC | 240m:z2 | BROADTOP | A | 0.00602 | 0.00493 (0.00493-0.00547) | -0.044 |
| BTC | 240m:z2 | BROADTOP | B | 0.00822 | 0.00822 (0.00822-0.011) | +0.388 |
| BTC | 240m:z2 | BULLFLAG | A | 0.0263 | 0.0203 (0.0192-0.0219) | -0.149 |
| BTC | 240m:z2 | BULLFLAG | B | 0.0274 | 0.0329 (0.0164-0.0329) | -0.046 |
| BTC | 240m:z2 | BULLPEN | A | 0.0159 | 0.00547 (0.00493-0.00876) | -0.031 |
| BTC | 240m:z2 | BULLPEN | B | 0.0137 | 0.011 (0.00822-0.0164) | +0.037 |
| BTC | 240m:z2 | CUP | A | 0.00164 | 0.00383 (0.00328-0.00547) | +0.663 |
| BTC | 240m:z2 | CUP | B | 0.00548 | 0.00548 (0.00274-0.00822) | +0.551 |
| BTC | 240m:z2 | DBOT | A | 0.0766 | 0.0898 (0.0832-0.0903) | -0.084 |
| BTC | 240m:z2 | DBOT | B | 0.0904 | 0.104 (0.0959-0.104) | +0.023 |
| BTC | 240m:z2 | DESCTRI | A | 0.0274 | 0.0296 (0.0246-0.0307) | +0.011 |
| BTC | 240m:z2 | DESCTRI | B | 0.0411 | 0.0329 (0.0219-0.0521) | -0.118 |
| BTC | 240m:z2 | DTOP | A | 0.0848 | 0.0794 (0.0706-0.0914) | +0.011 |
| BTC | 240m:z2 | DTOP | B | 0.11 | 0.0904 (0.0849-0.0959) | -0.072 |
| BTC | 240m:z2 | FALWEDGE | A | 0.0383 | 0.0405 (0.0389-0.0427) | +0.081 |
| BTC | 240m:z2 | FALWEDGE | B | 0.0521 | 0.0575 (0.0493-0.0603) | -0.196 |
| BTC | 240m:z2 | HARM.BEAR | A | 0.00219 | 0.00164 (0.00164-0.00219) | +0.164 |
| BTC | 240m:z2 | HARM.BEAR | B | 0 | 0.00274 (0-0.00274) |  |
| BTC | 240m:z2 | HARM.BULL | A | 0.00164 | 0.00164 (0.00109-0.00274) | +0.195 |
| BTC | 240m:z2 | HARM.BULL | B | 0.00548 | 0 (0-0.00274) | +0.012 |
| BTC | 240m:z2 | HS | A | 0.0175 | 0.0131 (0.0126-0.0192) | +0.089 |
| BTC | 240m:z2 | HS | B | 0.0192 | 0.0164 (0.00822-0.0219) | +0.591 |
| BTC | 240m:z2 | IHS | A | 0.0104 | 0.0131 (0.00821-0.0137) | +0.276 |
| BTC | 240m:z2 | IHS | B | 0.011 | 0.0247 (0.0164-0.0329) | +0.189 |
| BTC | 240m:z2 | INVCUP | A | 0.00383 | 0.00383 (0.00383-0.00438) | -0.053 |
| BTC | 240m:z2 | INVCUP | B | 0.00548 | 0.00548 (0-0.00822) | +0.687 |
| BTC | 240m:z2 | RECT | A | 0.00602 | 0.00821 (0.00383-0.0109) | -0.500 |
| BTC | 240m:z2 | RECT | B | 0.00274 | 0.011 (0.00822-0.0164) | +0.437 |
| BTC | 240m:z2 | RISWEDGE | A | 0.0405 | 0.0389 (0.0345-0.0389) | -0.172 |
| BTC | 240m:z2 | RISWEDGE | B | 0.0493 | 0.0575 (0.0575-0.063) | +0.206 |
| BTC | 240m:z2 | ROUNDBOT | A | 0.00821 | 0.012 (0.00985-0.0153) | +0.019 |
| BTC | 240m:z2 | ROUNDBOT | B | 0.011 | 0.0137 (0.011-0.0137) | +0.626 |
| BTC | 240m:z2 | ROUNDTOP | A | 0.0104 | 0.0104 (0.00985-0.012) | -0.407 |
| BTC | 240m:z2 | ROUNDTOP | B | 0.0219 | 0.0137 (0.011-0.0192) | +0.136 |
| BTC | 240m:z2 | SYMTRI | A | 0.0405 | 0.029 (0.0257-0.0356) | -0.015 |
| BTC | 240m:z2 | SYMTRI | B | 0.0466 | 0.0411 (0.0329-0.0493) | -0.197 |
| BTC | 240m:z2 | TRIBOT | A | 0.00821 | 0.0131 (0.00712-0.0181) | +0.104 |
| BTC | 240m:z2 | TRIBOT | B | 0.0164 | 0.0164 (0.00822-0.0247) | +0.052 |
| BTC | 240m:z2 | TRITOP | A | 0.012 | 0.00876 (0.00712-0.0159) | -0.032 |
| BTC | 240m:z2 | TRITOP | B | 0.0137 | 0.0137 (0.00548-0.0164) | +0.297 |
| BTC | 240m:z4 | ABCD.BEAR | A | 0.00438 | 0.00274 (0.00219-0.00547) | +0.261 |
| BTC | 240m:z4 | ABCD.BEAR | B | 0 | 0.00548 (0.00274-0.00548) |  |
| BTC | 240m:z4 | ABCD.BULL | A | 0.00219 | 0.00438 (0.00383-0.00602) | +0.621 |
| BTC | 240m:z4 | ABCD.BULL | B | 0.00822 | 0.00274 (0.00274-0.00548) | -0.386 |
| BTC | 240m:z4 | ASCTRI | A | 0.012 | 0.00821 (0.00547-0.00876) | -0.056 |
| BTC | 240m:z4 | ASCTRI | B | 0.00822 | 0.0137 (0.00548-0.0219) | +0.551 |
| BTC | 240m:z4 | BEARFLAG | A | 0.00383 | 0.00328 (0.00219-0.00438) | -0.194 |
| BTC | 240m:z4 | BEARFLAG | B | 0 | 0.00548 (0.00274-0.011) |  |
| BTC | 240m:z4 | BEARPEN | A | 0.00493 | 0.000547 (0.000547-0.00164) | -0.129 |
| BTC | 240m:z4 | BEARPEN | B | 0 | 0.00274 (0-0.00548) |  |
| BTC | 240m:z4 | BROADBOT | A | 0.00274 | 0.00164 (0.00109-0.00164) | +0.111 |
| BTC | 240m:z4 | BROADBOT | B | 0.00274 | 0.00274 (0.00274-0.00548) | -0.545 |
| BTC | 240m:z4 | BROADTOP | A | 0.00164 | 0.00164 (0.000547-0.00219) | +0.448 |
| BTC | 240m:z4 | BROADTOP | B | 0.00274 | 0.00274 (0-0.00548) |  |
| BTC | 240m:z4 | BULLFLAG | A | 0.000547 | 0.00274 (0.00219-0.00328) |  |
| BTC | 240m:z4 | BULLFLAG | B | 0 | 0.00274 (0-0.00274) |  |
| BTC | 240m:z4 | BULLPEN | A | 0.000547 | 0.00219 (0.000547-0.00219) | +0.913 |
| BTC | 240m:z4 | BULLPEN | B | 0.00548 | 0 (0-0.00548) | -0.122 |
| BTC | 240m:z4 | CUP | A | 0.00109 | 0.000547 (0.000547-0.00219) | -0.345 |
| BTC | 240m:z4 | CUP | B | 0.00274 | 0.00274 (0-0.00548) | -0.353 |
| BTC | 240m:z4 | DBOT | A | 0.0312 | 0.0334 (0.0301-0.0378) | +0.073 |
| BTC | 240m:z4 | DBOT | B | 0.0411 | 0.0438 (0.0274-0.0548) | -0.241 |
| BTC | 240m:z4 | DESCTRI | A | 0.00821 | 0.00766 (0.00602-0.0109) | -0.043 |
| BTC | 240m:z4 | DESCTRI | B | 0.0164 | 0.0137 (0.00822-0.0164) | -0.065 |
| BTC | 240m:z4 | DTOP | A | 0.0356 | 0.0328 (0.0307-0.035) | +0.062 |
| BTC | 240m:z4 | DTOP | B | 0.0301 | 0.0384 (0.0301-0.0438) | -0.332 |
| BTC | 240m:z4 | FALWEDGE | A | 0.00766 | 0.0131 (0.0131-0.0164) | -0.070 |
| BTC | 240m:z4 | FALWEDGE | B | 0.011 | 0.0247 (0.011-0.0301) | -0.037 |
| BTC | 240m:z4 | HARM.BEAR | A | 0.000547 | 0.000547 (0-0.00164) |  |
| BTC | 240m:z4 | HARM.BEAR | B | 0 | 0 (0-0.00822) |  |
| BTC | 240m:z4 | HARM.BULL | A | 0.000547 | 0.000547 (0-0.00109) | -0.718 |
| BTC | 240m:z4 | HARM.BULL | B | 0.00274 | 0 (0-0) |  |
| BTC | 240m:z4 | HS | A | 0.00547 | 0.00383 (0.00328-0.00493) | -0.192 |
| BTC | 240m:z4 | HS | B | 0.00548 | 0.00274 (0.00274-0.00548) | -0.447 |
| BTC | 240m:z4 | IHS | A | 0.00219 | 0.00219 (0.000547-0.00438) | -0.386 |
| BTC | 240m:z4 | IHS | B | 0.011 | 0 (0-0.00548) | -0.373 |
| BTC | 240m:z4 | INVCUP | A | 0.00109 | 0.000547 (0.000547-0.00164) | +0.679 |
| BTC | 240m:z4 | INVCUP | B | 0.00548 | 0.00274 (0.00274-0.00548) | +0.152 |
| BTC | 240m:z4 | RECT | A | 0.00383 | 0.00219 (0.00109-0.00493) | -0.529 |
| BTC | 240m:z4 | RECT | B | 0.00274 | 0.00548 (0.00274-0.00548) | +0.451 |
| BTC | 240m:z4 | RISWEDGE | A | 0.0131 | 0.0126 (0.012-0.0164) | +0.279 |
| BTC | 240m:z4 | RISWEDGE | B | 0.00822 | 0.0192 (0.0164-0.0192) | +0.558 |
| BTC | 240m:z4 | ROUNDBOT | A | 0.00493 | 0.00876 (0.00766-0.00931) |  |
| BTC | 240m:z4 | ROUNDBOT | B | 0.00274 | 0.011 (0.00822-0.0164) |  |
| BTC | 240m:z4 | ROUNDTOP | A | 0.00657 | 0.00766 (0.00657-0.00876) | -0.344 |
| BTC | 240m:z4 | ROUNDTOP | B | 0.00822 | 0.00548 (0.00274-0.0137) |  |
| BTC | 240m:z4 | SYMTRI | A | 0.0131 | 0.012 (0.00766-0.012) | +0.134 |
| BTC | 240m:z4 | SYMTRI | B | 0.0329 | 0.0192 (0.011-0.0274) | -0.088 |
| BTC | 240m:z4 | TRIBOT | A | 0.00383 | 0.00493 (0.00274-0.00876) |  |
| BTC | 240m:z4 | TRIBOT | B | 0.00548 | 0.00548 (0.00274-0.00822) | +0.454 |
| BTC | 240m:z4 | TRITOP | A | 0.00493 | 0.00438 (0.00274-0.00547) | +0.033 |
| BTC | 240m:z4 | TRITOP | B | 0.00274 | 0.00274 (0-0.00822) | -0.561 |
| BTC | 240m:z8 | ABCD.BEAR | A | 0.00164 | 0.00109 (0.00109-0.00109) | +0.701 |
| BTC | 240m:z8 | ABCD.BEAR | B | 0 | 0.00274 (0.00274-0.00548) |  |
| BTC | 240m:z8 | ABCD.BULL | A | 0.000547 | 0.00164 (0.00109-0.00328) | -0.334 |
| BTC | 240m:z8 | ABCD.BULL | B | 0.00274 | 0.00274 (0-0.00274) | +0.000 |
| BTC | 240m:z8 | ASCTRI | A | 0.00164 | 0.00164 (0.00164-0.00219) | -0.321 |
| BTC | 240m:z8 | ASCTRI | B | 0.00274 | 0.00274 (0-0.00548) |  |
| BTC | 240m:z8 | BEARFLAG | A | 0 | 0 (0-0.000547) |  |
| BTC | 240m:z8 | BEARFLAG | B | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | BEARPEN | A | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | BEARPEN | B | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | BROADBOT | A | 0 | 0 (0-0.00164) |  |
| BTC | 240m:z8 | BROADBOT | B | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | BROADTOP | A | 0.000547 | 0 (0-0.000547) |  |
| BTC | 240m:z8 | BROADTOP | B | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | BULLFLAG | A | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | BULLFLAG | B | 0 | 0 (0-0.00274) |  |
| BTC | 240m:z8 | BULLPEN | A | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | BULLPEN | B | 0 | 0 (0-0.00274) |  |
| BTC | 240m:z8 | CUP | A | 0 | 0.000547 (0.000547-0.00109) |  |
| BTC | 240m:z8 | CUP | B | 0 | 0 (0-0.00274) |  |
| BTC | 240m:z8 | DBOT | A | 0.00931 | 0.00931 (0.00931-0.012) | +0.056 |
| BTC | 240m:z8 | DBOT | B | 0.0219 | 0.011 (0.00822-0.0137) | -0.159 |
| BTC | 240m:z8 | DESCTRI | A | 0.00328 | 0.00328 (0.00164-0.00438) | +0.388 |
| BTC | 240m:z8 | DESCTRI | B | 0.00822 | 0 (0-0.00274) | -0.354 |
| BTC | 240m:z8 | DTOP | A | 0.00766 | 0.00712 (0.00657-0.00712) | +0.306 |
| BTC | 240m:z8 | DTOP | B | 0.0164 | 0.011 (0.00548-0.0164) | -0.357 |
| BTC | 240m:z8 | FALWEDGE | A | 0.00274 | 0.00602 (0.00328-0.00657) | +0.318 |
| BTC | 240m:z8 | FALWEDGE | B | 0.0192 | 0.00548 (0-0.00548) | +0.362 |
| BTC | 240m:z8 | HARM.BEAR | A | 0 | 0.000547 (0-0.00109) |  |
| BTC | 240m:z8 | HARM.BEAR | B | 0.00274 | 0 (0-0.00274) | -0.197 |
| BTC | 240m:z8 | HARM.BULL | A | 0 | 0.000547 (0-0.000547) |  |
| BTC | 240m:z8 | HARM.BULL | B | 0 | 0 (0-0.00274) |  |
| BTC | 240m:z8 | HS | A | 0.00109 | 0.00164 (0.00109-0.00164) | +0.109 |
| BTC | 240m:z8 | HS | B | 0.00274 | 0 (0-0.00274) |  |
| BTC | 240m:z8 | IHS | A | 0 | 0.000547 (0.000547-0.000547) |  |
| BTC | 240m:z8 | IHS | B | 0 | 0 (0-0.00274) |  |
| BTC | 240m:z8 | INVCUP | A | 0 | 0.000547 (0.000547-0.00219) |  |
| BTC | 240m:z8 | INVCUP | B | 0 | 0.00274 (0-0.00274) |  |
| BTC | 240m:z8 | RECT | A | 0 | 0.000547 (0-0.000547) |  |
| BTC | 240m:z8 | RECT | B | 0 | 0 (0-0.00274) |  |
| BTC | 240m:z8 | RISWEDGE | A | 0.00328 | 0.00328 (0.00109-0.00383) | +0.546 |
| BTC | 240m:z8 | RISWEDGE | B | 0 | 0.00274 (0.00274-0.00274) |  |
| BTC | 240m:z8 | ROUNDBOT | A | 0.00109 | 0.00274 (0.00109-0.00274) |  |
| BTC | 240m:z8 | ROUNDBOT | B | 0.00274 | 0.00548 (0-0.00822) |  |
| BTC | 240m:z8 | ROUNDTOP | A | 0.00219 | 0.00219 (0.00109-0.00274) | +0.139 |
| BTC | 240m:z8 | ROUNDTOP | B | 0 | 0.00274 (0.00274-0.00548) |  |
| BTC | 240m:z8 | SYMTRI | A | 0.00109 | 0.00274 (0.00219-0.00328) | +0.732 |
| BTC | 240m:z8 | SYMTRI | B | 0.00822 | 0 (0-0.011) | -0.210 |
| BTC | 240m:z8 | TRIBOT | A | 0 | 0.00109 (0.000547-0.00109) |  |
| BTC | 240m:z8 | TRIBOT | B | 0 | 0 (0-0) |  |
| BTC | 240m:z8 | TRITOP | A | 0.000547 | 0.00109 (0-0.00109) |  |
| BTC | 240m:z8 | TRITOP | B | 0.00274 | 0 (0-0) | +0.442 |
| BTC | 5m:z2 | ABCD.BEAR | A | 0.728 | 0.732 (0.707-0.741) | -0.020 |
| BTC | 5m:z2 | ABCD.BEAR | B | 0.926 | 0.855 (0.797-0.921) | -0.034 |
| BTC | 5m:z2 | ABCD.BULL | A | 0.756 | 0.756 (0.755-0.799) | -0.040 |
| BTC | 5m:z2 | ABCD.BULL | B | 0.918 | 0.915 (0.871-0.926) | -0.038 |
| BTC | 5m:z2 | ASCTRI | A | 1.8 | 1.68 (1.67-1.72) | +0.028 |
| BTC | 5m:z2 | ASCTRI | B | 1.98 | 1.88 (1.87-1.91) | +0.041 |
| BTC | 5m:z2 | BEARFLAG | A | 0.912 | 1.09 (1.08-1.13) | -0.002 |
| BTC | 5m:z2 | BEARFLAG | B | 0.896 | 1.23 (1.21-1.24) | +0.015 |
| BTC | 5m:z2 | BEARPEN | A | 0.412 | 0.42 (0.388-0.426) | +0.023 |
| BTC | 5m:z2 | BEARPEN | B | 0.455 | 0.466 (0.395-0.466) | -0.056 |
| BTC | 5m:z2 | BROADBOT | A | 0.28 | 0.341 (0.328-0.349) | -0.050 |
| BTC | 5m:z2 | BROADBOT | B | 0.381 | 0.375 (0.367-0.375) | -0.033 |
| BTC | 5m:z2 | BROADTOP | A | 0.282 | 0.334 (0.33-0.344) | +0.016 |
| BTC | 5m:z2 | BROADTOP | B | 0.326 | 0.362 (0.334-0.375) | -0.015 |
| BTC | 5m:z2 | BULLFLAG | A | 1.25 | 1.08 (1.08-1.12) | +0.001 |
| BTC | 5m:z2 | BULLFLAG | B | 1.14 | 1.11 (1.01-1.17) | -0.024 |
| BTC | 5m:z2 | BULLPEN | A | 0.531 | 0.404 (0.394-0.419) | -0.010 |
| BTC | 5m:z2 | BULLPEN | B | 0.392 | 0.438 (0.381-0.447) | -0.023 |
| BTC | 5m:z2 | CUP | A | 0.183 | 0.226 (0.226-0.244) | -0.021 |
| BTC | 5m:z2 | CUP | B | 0.249 | 0.277 (0.26-0.301) | +0.050 |
| BTC | 5m:z2 | DBOT | A | 4.84 | 4.8 (4.77-4.87) | -0.023 |
| BTC | 5m:z2 | DBOT | B | 5.21 | 5.01 (4.95-5.11) | -0.020 |
| BTC | 5m:z2 | DESCTRI | A | 1.79 | 1.7 (1.65-1.75) | +0.001 |
| BTC | 5m:z2 | DESCTRI | B | 1.96 | 1.89 (1.73-1.91) | -0.029 |
| BTC | 5m:z2 | DTOP | A | 5.16 | 4.75 (4.74-4.76) | -0.032 |
| BTC | 5m:z2 | DTOP | B | 5.35 | 4.93 (4.85-4.96) | -0.032 |
| BTC | 5m:z2 | FALWEDGE | A | 2.65 | 2.49 (2.48-2.52) | +0.012 |
| BTC | 5m:z2 | FALWEDGE | B | 2.99 | 2.84 (2.64-2.96) | -0.005 |
| BTC | 5m:z2 | HARM.BEAR | A | 0.113 | 0.123 (0.12-0.124) | -0.092 |
| BTC | 5m:z2 | HARM.BEAR | B | 0.164 | 0.129 (0.101-0.178) | -0.099 |
| BTC | 5m:z2 | HARM.BULL | A | 0.12 | 0.129 (0.112-0.13) | -0.063 |
| BTC | 5m:z2 | HARM.BULL | B | 0.129 | 0.148 (0.134-0.164) | +0.061 |
| BTC | 5m:z2 | HS | A | 0.974 | 0.849 (0.837-0.874) | +0.021 |
| BTC | 5m:z2 | HS | B | 1.1 | 1.02 (0.964-1.05) | +0.043 |
| BTC | 5m:z2 | IHS | A | 0.974 | 0.863 (0.829-0.87) | +0.026 |
| BTC | 5m:z2 | IHS | B | 1.14 | 1.02 (0.959-1.03) | -0.058 |
| BTC | 5m:z2 | INVCUP | A | 0.228 | 0.241 (0.233-0.244) | +0.026 |
| BTC | 5m:z2 | INVCUP | B | 0.249 | 0.255 (0.23-0.271) | +0.023 |
| BTC | 5m:z2 | RECT | A | 0.413 | 0.485 (0.464-0.492) | -0.007 |
| BTC | 5m:z2 | RECT | B | 0.411 | 0.532 (0.496-0.581) | -0.028 |
| BTC | 5m:z2 | RISWEDGE | A | 2.64 | 2.42 (2.38-2.44) | +0.003 |
| BTC | 5m:z2 | RISWEDGE | B | 2.98 | 2.76 (2.73-2.85) | +0.013 |
| BTC | 5m:z2 | ROUNDBOT | A | 0.31 | 0.652 (0.651-0.658) | -0.001 |
| BTC | 5m:z2 | ROUNDBOT | B | 0.343 | 0.597 (0.551-0.649) | +0.096 |
| BTC | 5m:z2 | ROUNDTOP | A | 0.544 | 0.639 (0.625-0.66) | -0.033 |
| BTC | 5m:z2 | ROUNDTOP | B | 0.666 | 0.597 (0.562-0.617) | +0.031 |
| BTC | 5m:z2 | SYMTRI | A | 2.55 | 2.08 (2.04-2.1) | +0.041 |
| BTC | 5m:z2 | SYMTRI | B | 2.82 | 2.31 (2.26-2.44) | +0.020 |
| BTC | 5m:z2 | TRIBOT | A | 0.608 | 0.721 (0.693-0.734) | -0.077 |
| BTC | 5m:z2 | TRIBOT | B | 0.721 | 0.748 (0.729-0.77) | -0.017 |
| BTC | 5m:z2 | TRITOP | A | 0.662 | 0.707 (0.7-0.735) | -0.042 |
| BTC | 5m:z2 | TRITOP | B | 0.775 | 0.795 (0.666-0.893) | +0.006 |
| BTC | 5m:z4 | ABCD.BEAR | A | 0.233 | 0.27 (0.259-0.271) | +0.002 |
| BTC | 5m:z4 | ABCD.BEAR | B | 0.241 | 0.299 (0.279-0.326) | -0.024 |
| BTC | 5m:z4 | ABCD.BULL | A | 0.232 | 0.256 (0.246-0.267) | -0.011 |
| BTC | 5m:z4 | ABCD.BULL | B | 0.364 | 0.31 (0.31-0.359) | -0.035 |
| BTC | 5m:z4 | ASCTRI | A | 0.71 | 0.645 (0.62-0.656) | -0.001 |
| BTC | 5m:z4 | ASCTRI | B | 0.841 | 0.756 (0.707-0.767) | -0.018 |
| BTC | 5m:z4 | BEARFLAG | A | 0.136 | 0.226 (0.206-0.234) | +0.025 |
| BTC | 5m:z4 | BEARFLAG | B | 0.148 | 0.258 (0.255-0.301) | +0.019 |
| BTC | 5m:z4 | BEARPEN | A | 0.0827 | 0.0733 (0.069-0.1) | +0.064 |
| BTC | 5m:z4 | BEARPEN | B | 0.0904 | 0.0959 (0.0712-0.104) | +0.106 |
| BTC | 5m:z4 | BROADBOT | A | 0.075 | 0.102 (0.0991-0.108) | -0.056 |
| BTC | 5m:z4 | BROADBOT | B | 0.0986 | 0.101 (0.0986-0.11) | -0.038 |
| BTC | 5m:z4 | BROADTOP | A | 0.0865 | 0.107 (0.0898-0.12) | +0.051 |
| BTC | 5m:z4 | BROADTOP | B | 0.0986 | 0.129 (0.121-0.142) | +0.004 |
| BTC | 5m:z4 | BULLFLAG | A | 0.198 | 0.219 (0.199-0.22) | +0.011 |
| BTC | 5m:z4 | BULLFLAG | B | 0.195 | 0.255 (0.23-0.255) | -0.011 |
| BTC | 5m:z4 | BULLPEN | A | 0.0854 | 0.0805 (0.0772-0.0887) | -0.013 |
| BTC | 5m:z4 | BULLPEN | B | 0.101 | 0.0849 (0.0822-0.0904) | +0.090 |
| BTC | 5m:z4 | CUP | A | 0.0783 | 0.101 (0.0898-0.107) | -0.049 |
| BTC | 5m:z4 | CUP | B | 0.0904 | 0.121 (0.0986-0.164) | -0.031 |
| BTC | 5m:z4 | DBOT | A | 1.97 | 2.14 (2.07-2.16) | -0.032 |
| BTC | 5m:z4 | DBOT | B | 2.42 | 2.41 (2.36-2.41) | -0.010 |
| BTC | 5m:z4 | DESCTRI | A | 0.602 | 0.65 (0.637-0.666) | +0.049 |
| BTC | 5m:z4 | DESCTRI | B | 0.633 | 0.726 (0.712-0.764) | +0.058 |
| BTC | 5m:z4 | DTOP | A | 2.11 | 2.11 (2.1-2.13) | -0.034 |
| BTC | 5m:z4 | DTOP | B | 2.51 | 2.38 (2.34-2.49) | -0.003 |
| BTC | 5m:z4 | FALWEDGE | A | 0.806 | 0.898 (0.889-0.928) | +0.030 |
| BTC | 5m:z4 | FALWEDGE | B | 1.01 | 0.981 (0.915-1.08) | +0.064 |
| BTC | 5m:z4 | HARM.BEAR | A | 0.0536 | 0.0454 (0.0378-0.046) | -0.039 |
| BTC | 5m:z4 | HARM.BEAR | B | 0.0603 | 0.063 (0.0575-0.0822) | -0.057 |
| BTC | 5m:z4 | HARM.BULL | A | 0.0651 | 0.0405 (0.04-0.0443) | +0.029 |
| BTC | 5m:z4 | HARM.BULL | B | 0.0658 | 0.0493 (0.0466-0.0521) | -0.217 |
| BTC | 5m:z4 | HS | A | 0.305 | 0.291 (0.288-0.297) | +0.016 |
| BTC | 5m:z4 | HS | B | 0.293 | 0.34 (0.315-0.384) | +0.037 |
| BTC | 5m:z4 | IHS | A | 0.32 | 0.288 (0.273-0.294) | +0.060 |
| BTC | 5m:z4 | IHS | B | 0.321 | 0.343 (0.323-0.348) | +0.049 |
| BTC | 5m:z4 | INVCUP | A | 0.0805 | 0.102 (0.101-0.105) | -0.002 |
| BTC | 5m:z4 | INVCUP | B | 0.0932 | 0.107 (0.0904-0.14) | +0.228 |
| BTC | 5m:z4 | RECT | A | 0.12 | 0.19 (0.18-0.193) | -0.059 |
| BTC | 5m:z4 | RECT | B | 0.167 | 0.208 (0.197-0.216) | +0.100 |
| BTC | 5m:z4 | RISWEDGE | A | 0.863 | 0.902 (0.891-0.917) | +0.035 |
| BTC | 5m:z4 | RISWEDGE | B | 1.07 | 0.992 (0.962-1.02) | -0.035 |
| BTC | 5m:z4 | ROUNDBOT | A | 0.307 | 0.57 (0.55-0.571) | -0.031 |
| BTC | 5m:z4 | ROUNDBOT | B | 0.425 | 0.63 (0.611-0.671) | +0.265 |
| BTC | 5m:z4 | ROUNDTOP | A | 0.403 | 0.536 (0.525-0.537) | -0.118 |
| BTC | 5m:z4 | ROUNDTOP | B | 0.512 | 0.578 (0.573-0.69) | +0.037 |
| BTC | 5m:z4 | SYMTRI | A | 1.06 | 0.858 (0.844-0.877) | +0.024 |
| BTC | 5m:z4 | SYMTRI | B | 1.07 | 1.04 (0.978-1.15) | +0.008 |
| BTC | 5m:z4 | TRIBOT | A | 0.186 | 0.263 (0.258-0.273) | -0.033 |
| BTC | 5m:z4 | TRIBOT | B | 0.233 | 0.271 (0.26-0.323) | +0.016 |
| BTC | 5m:z4 | TRITOP | A | 0.228 | 0.268 (0.253-0.281) | -0.016 |
| BTC | 5m:z4 | TRITOP | B | 0.296 | 0.29 (0.288-0.31) | +0.018 |
| BTC | 5m:z8 | ABCD.BEAR | A | 0.0755 | 0.0854 (0.0848-0.0854) | +0.048 |
| BTC | 5m:z8 | ABCD.BEAR | B | 0.104 | 0.0986 (0.0986-0.112) | -0.045 |
| BTC | 5m:z8 | ABCD.BULL | A | 0.0712 | 0.0843 (0.0706-0.0909) | +0.077 |
| BTC | 5m:z8 | ABCD.BULL | B | 0.0877 | 0.0986 (0.0712-0.101) | -0.049 |
| BTC | 5m:z8 | ASCTRI | A | 0.212 | 0.196 (0.181-0.204) | +0.012 |
| BTC | 5m:z8 | ASCTRI | B | 0.222 | 0.238 (0.236-0.252) | +0.033 |
| BTC | 5m:z8 | BEARFLAG | A | 0.00493 | 0.0137 (0.0109-0.0137) | +0.152 |
| BTC | 5m:z8 | BEARFLAG | B | 0.00822 | 0.0247 (0.0164-0.0301) | +0.134 |
| BTC | 5m:z8 | BEARPEN | A | 0.00383 | 0.00438 (0.00328-0.00602) | +0.213 |
| BTC | 5m:z8 | BEARPEN | B | 0.00548 | 0.00274 (0-0.011) | -0.085 |
| BTC | 5m:z8 | BROADBOT | A | 0.0192 | 0.0268 (0.0246-0.0307) | +0.097 |
| BTC | 5m:z8 | BROADBOT | B | 0.0192 | 0.0274 (0.0192-0.0466) | -0.521 |
| BTC | 5m:z8 | BROADTOP | A | 0.0219 | 0.0268 (0.0246-0.0296) | +0.028 |
| BTC | 5m:z8 | BROADTOP | B | 0.0247 | 0.0438 (0.0247-0.0438) | -0.513 |
| BTC | 5m:z8 | BULLFLAG | A | 0.00657 | 0.0137 (0.0131-0.0142) | +0.105 |
| BTC | 5m:z8 | BULLFLAG | B | 0.00822 | 0.0247 (0.011-0.0301) | -0.137 |
| BTC | 5m:z8 | BULLPEN | A | 0.00493 | 0.00602 (0.00493-0.00821) | +0.243 |
| BTC | 5m:z8 | BULLPEN | B | 0.00548 | 0.011 (0.00548-0.011) | -0.045 |
| BTC | 5m:z8 | CUP | A | 0.0192 | 0.0367 (0.0241-0.0367) | -0.031 |
| BTC | 5m:z8 | CUP | B | 0.0274 | 0.0411 (0.0301-0.0575) | +0.075 |
| BTC | 5m:z8 | DBOT | A | 0.596 | 0.673 (0.665-0.683) | -0.014 |
| BTC | 5m:z8 | DBOT | B | 0.732 | 0.803 (0.784-0.849) | +0.041 |
| BTC | 5m:z8 | DESCTRI | A | 0.174 | 0.195 (0.19-0.204) | +0.124 |
| BTC | 5m:z8 | DESCTRI | B | 0.219 | 0.23 (0.214-0.293) | +0.075 |
| BTC | 5m:z8 | DTOP | A | 0.664 | 0.679 (0.651-0.691) | +0.015 |
| BTC | 5m:z8 | DTOP | B | 0.775 | 0.817 (0.803-0.852) | +0.026 |
| BTC | 5m:z8 | FALWEDGE | A | 0.203 | 0.265 (0.25-0.286) | +0.090 |
| BTC | 5m:z8 | FALWEDGE | B | 0.197 | 0.282 (0.26-0.381) | -0.035 |
| BTC | 5m:z8 | HARM.BEAR | A | 0.0235 | 0.0137 (0.0137-0.0186) | +0.030 |
| BTC | 5m:z8 | HARM.BEAR | B | 0.0137 | 0.0301 (0.011-0.0384) | -0.204 |
| BTC | 5m:z8 | HARM.BULL | A | 0.0192 | 0.0148 (0.012-0.0192) | -0.027 |
| BTC | 5m:z8 | HARM.BULL | B | 0.0329 | 0.0164 (0.0137-0.0247) | -0.191 |
| BTC | 5m:z8 | HS | A | 0.1 | 0.0969 (0.0947-0.0991) | +0.059 |
| BTC | 5m:z8 | HS | B | 0.14 | 0.11 (0.0932-0.118) | -0.118 |
| BTC | 5m:z8 | IHS | A | 0.0931 | 0.101 (0.081-0.106) | -0.055 |
| BTC | 5m:z8 | IHS | B | 0.101 | 0.11 (0.0986-0.126) | +0.225 |
| BTC | 5m:z8 | INVCUP | A | 0.0213 | 0.0334 (0.0296-0.0443) | -0.128 |
| BTC | 5m:z8 | INVCUP | B | 0.0301 | 0.0438 (0.0329-0.0466) | +0.418 |
| BTC | 5m:z8 | RECT | A | 0.0328 | 0.0536 (0.0476-0.0575) | -0.157 |
| BTC | 5m:z8 | RECT | B | 0.0411 | 0.0575 (0.0521-0.0658) | +0.108 |
| BTC | 5m:z8 | RISWEDGE | A | 0.247 | 0.246 (0.236-0.271) | -0.016 |
| BTC | 5m:z8 | RISWEDGE | B | 0.285 | 0.334 (0.279-0.356) | -0.052 |
| BTC | 5m:z8 | ROUNDBOT | A | 0.108 | 0.178 (0.167-0.182) | -0.163 |
| BTC | 5m:z8 | ROUNDBOT | B | 0.156 | 0.192 (0.151-0.214) | +0.010 |
| BTC | 5m:z8 | ROUNDTOP | A | 0.137 | 0.151 (0.148-0.162) | +0.233 |
| BTC | 5m:z8 | ROUNDTOP | B | 0.175 | 0.189 (0.175-0.206) | -0.173 |
| BTC | 5m:z8 | SYMTRI | A | 0.366 | 0.286 (0.28-0.296) | +0.085 |
| BTC | 5m:z8 | SYMTRI | B | 0.392 | 0.329 (0.321-0.411) | +0.041 |
| BTC | 5m:z8 | TRIBOT | A | 0.0569 | 0.0761 (0.0684-0.0898) | +0.004 |
| BTC | 5m:z8 | TRIBOT | B | 0.0959 | 0.0986 (0.0986-0.121) | +0.074 |
| BTC | 5m:z8 | TRITOP | A | 0.0608 | 0.0761 (0.0712-0.0777) | +0.002 |
| BTC | 5m:z8 | TRITOP | B | 0.0877 | 0.0959 (0.0877-0.0986) | -0.221 |
| BTC | 60m:K | LMW.BBOT | A | 0.151 | 0.207 (0.204-0.225) | -0.013 |
| BTC | 60m:K | LMW.BBOT | B | 0.178 | 0.241 (0.233-0.247) | -0.062 |
| BTC | 60m:K | LMW.BTOP | A | 0.152 | 0.232 (0.197-0.241) | +0.006 |
| BTC | 60m:K | LMW.BTOP | B | 0.175 | 0.258 (0.249-0.263) | -0.034 |
| BTC | 60m:K | LMW.DBOT | A | 0.0608 | 0.0569 (0.0569-0.0591) | +0.024 |
| BTC | 60m:K | LMW.DBOT | B | 0.0822 | 0.0849 (0.0795-0.0932) | +0.016 |
| BTC | 60m:K | LMW.DTOP | A | 0.0733 | 0.0509 (0.0498-0.0558) | +0.045 |
| BTC | 60m:K | LMW.DTOP | B | 0.107 | 0.0904 (0.0685-0.0932) | -0.053 |
| BTC | 60m:K | LMW.HS | A | 1.24 | 1.07 (1.07-1.08) | -0.036 |
| BTC | 60m:K | LMW.HS | B | 1.31 | 1.22 (1.15-1.23) | -0.031 |
| BTC | 60m:K | LMW.HS.SWZ | A | 0.00766 | 0.00657 (0.00602-0.00766) | -0.107 |
| BTC | 60m:K | LMW.HS.SWZ | B | 0.00274 | 0.00548 (0.00274-0.00822) |  |
| BTC | 60m:K | LMW.IHS | A | 1.21 | 1.11 (1.09-1.12) | -0.036 |
| BTC | 60m:K | LMW.IHS | B | 1.27 | 1.23 (1.19-1.24) | +0.004 |
| BTC | 60m:K | LMW.IHS.SWZ | A | 0.00985 | 0.00712 (0.00602-0.00766) | +0.055 |
| BTC | 60m:K | LMW.IHS.SWZ | B | 0.00274 | 0.00548 (0.00274-0.00822) | -0.478 |
| BTC | 60m:K | LMW.RBOT | A | 3.37 | 2.89 (2.83-2.89) | -0.003 |
| BTC | 60m:K | LMW.RBOT | B | 3.93 | 3.69 (3.66-3.72) | +0.002 |
| BTC | 60m:K | LMW.RTOP | A | 3.5 | 2.88 (2.82-2.9) | -0.011 |
| BTC | 60m:K | LMW.RTOP | B | 4.03 | 3.75 (3.74-3.77) | -0.004 |
| BTC | 60m:K | LMW.TBOT | A | 0.48 | 0.259 (0.255-0.259) | -0.380 |
| BTC | 60m:K | LMW.TBOT | B | 0.43 | 0.285 (0.282-0.343) | -0.333 |
| BTC | 60m:K | LMW.TTOP | A | 0.45 | 0.28 (0.255-0.286) | -0.376 |
| BTC | 60m:K | LMW.TTOP | B | 0.406 | 0.312 (0.269-0.364) | -0.342 |
| BTC | 60m:z2 | ABCD.BEAR | A | 0.0411 | 0.0542 (0.0531-0.0547) | +0.084 |
| BTC | 60m:z2 | ABCD.BEAR | B | 0.0411 | 0.0548 (0.0466-0.0685) | -0.009 |
| BTC | 60m:z2 | ABCD.BULL | A | 0.0421 | 0.0525 (0.0493-0.0619) | +0.074 |
| BTC | 60m:z2 | ABCD.BULL | B | 0.0493 | 0.0685 (0.0575-0.0795) | -0.052 |
| BTC | 60m:z2 | ASCTRI | A | 0.102 | 0.123 (0.111-0.136) | +0.050 |
| BTC | 60m:z2 | ASCTRI | B | 0.137 | 0.118 (0.107-0.134) | +0.016 |
| BTC | 60m:z2 | BEARFLAG | A | 0.115 | 0.103 (0.0996-0.109) | +0.005 |
| BTC | 60m:z2 | BEARFLAG | B | 0.104 | 0.118 (0.11-0.132) | -0.009 |
| BTC | 60m:z2 | BEARPEN | A | 0.0602 | 0.0394 (0.0345-0.0411) | -0.023 |
| BTC | 60m:z2 | BEARPEN | B | 0.0438 | 0.0521 (0.0438-0.0575) | -0.007 |
| BTC | 60m:z2 | BROADBOT | A | 0.0197 | 0.0307 (0.029-0.0312) | +0.146 |
| BTC | 60m:z2 | BROADBOT | B | 0.0164 | 0.0274 (0.0219-0.0301) | -0.621 |
| BTC | 60m:z2 | BROADTOP | A | 0.0159 | 0.0257 (0.0235-0.0334) | +0.255 |
| BTC | 60m:z2 | BROADTOP | B | 0.0137 | 0.0356 (0.0192-0.0384) | -0.058 |
| BTC | 60m:z2 | BULLFLAG | A | 0.108 | 0.0898 (0.0892-0.0974) | +0.003 |
| BTC | 60m:z2 | BULLFLAG | B | 0.145 | 0.104 (0.0986-0.118) | -0.008 |
| BTC | 60m:z2 | BULLPEN | A | 0.0684 | 0.0367 (0.0285-0.0383) | -0.045 |
| BTC | 60m:z2 | BULLPEN | B | 0.0493 | 0.0438 (0.0329-0.0466) | +0.270 |
| BTC | 60m:z2 | CUP | A | 0.0104 | 0.0153 (0.012-0.017) | -0.112 |
| BTC | 60m:z2 | CUP | B | 0.0164 | 0.0192 (0.011-0.0219) | +0.345 |
| BTC | 60m:z2 | DBOT | A | 0.35 | 0.385 (0.381-0.4) | -0.007 |
| BTC | 60m:z2 | DBOT | B | 0.397 | 0.408 (0.4-0.444) | +0.083 |
| BTC | 60m:z2 | DESCTRI | A | 0.113 | 0.132 (0.131-0.133) | +0.001 |
| BTC | 60m:z2 | DESCTRI | B | 0.153 | 0.159 (0.145-0.167) | -0.080 |
| BTC | 60m:z2 | DTOP | A | 0.381 | 0.38 (0.36-0.384) | +0.006 |
| BTC | 60m:z2 | DTOP | B | 0.414 | 0.397 (0.384-0.43) | +0.037 |
| BTC | 60m:z2 | FALWEDGE | A | 0.175 | 0.183 (0.177-0.195) | +0.005 |
| BTC | 60m:z2 | FALWEDGE | B | 0.197 | 0.225 (0.175-0.247) | -0.151 |
| BTC | 60m:z2 | HARM.BEAR | A | 0.00602 | 0.00985 (0.00438-0.0115) | +0.067 |
| BTC | 60m:z2 | HARM.BEAR | B | 0.00822 | 0.00548 (0.00548-0.011) |  |
| BTC | 60m:z2 | HARM.BULL | A | 0.0104 | 0.00985 (0.00712-0.012) | -0.077 |
| BTC | 60m:z2 | HARM.BULL | B | 0.00822 | 0.011 (0.00822-0.0164) | -0.120 |
| BTC | 60m:z2 | HS | A | 0.0701 | 0.0662 (0.0569-0.0668) | -0.107 |
| BTC | 60m:z2 | HS | B | 0.0849 | 0.0658 (0.063-0.0795) | -0.201 |
| BTC | 60m:z2 | IHS | A | 0.0547 | 0.0673 (0.0536-0.0723) | +0.031 |
| BTC | 60m:z2 | IHS | B | 0.0658 | 0.0795 (0.0685-0.0795) | +0.311 |
| BTC | 60m:z2 | INVCUP | A | 0.0175 | 0.0181 (0.0153-0.0181) | -0.117 |
| BTC | 60m:z2 | INVCUP | B | 0.00822 | 0.0219 (0.0164-0.0247) |  |
| BTC | 60m:z2 | RECT | A | 0.0186 | 0.0389 (0.0383-0.0449) | -0.286 |
| BTC | 60m:z2 | RECT | B | 0.0274 | 0.0356 (0.0247-0.0466) | -0.015 |
| BTC | 60m:z2 | RISWEDGE | A | 0.172 | 0.187 (0.172-0.198) | +0.002 |
| BTC | 60m:z2 | RISWEDGE | B | 0.178 | 0.238 (0.227-0.285) | -0.053 |
| BTC | 60m:z2 | ROUNDBOT | A | 0.0307 | 0.0575 (0.0558-0.0619) | -0.333 |
| BTC | 60m:z2 | ROUNDBOT | B | 0.0274 | 0.0411 (0.0329-0.0438) | +0.029 |
| BTC | 60m:z2 | ROUNDTOP | A | 0.0411 | 0.0498 (0.0471-0.0515) | +0.188 |
| BTC | 60m:z2 | ROUNDTOP | B | 0.0658 | 0.0521 (0.0493-0.0575) | -0.393 |
| BTC | 60m:z2 | SYMTRI | A | 0.142 | 0.159 (0.158-0.162) | +0.057 |
| BTC | 60m:z2 | SYMTRI | B | 0.137 | 0.17 (0.156-0.203) | +0.105 |
| BTC | 60m:z2 | TRIBOT | A | 0.0317 | 0.058 (0.0575-0.0619) | -0.062 |
| BTC | 60m:z2 | TRIBOT | B | 0.0521 | 0.0521 (0.0466-0.0712) | +0.018 |
| BTC | 60m:z2 | TRITOP | A | 0.0372 | 0.0493 (0.0465-0.0564) | +0.027 |
| BTC | 60m:z2 | TRITOP | B | 0.0438 | 0.0603 (0.0438-0.063) | -0.221 |
| BTC | 60m:z4 | ABCD.BEAR | A | 0.0142 | 0.0192 (0.0164-0.0252) | +0.174 |
| BTC | 60m:z4 | ABCD.BEAR | B | 0.0247 | 0.0192 (0.0192-0.0247) | -0.072 |
| BTC | 60m:z4 | ABCD.BULL | A | 0.0109 | 0.0175 (0.0142-0.0181) | -0.010 |
| BTC | 60m:z4 | ABCD.BULL | B | 0.0192 | 0.0192 (0.0164-0.0219) | +0.107 |
| BTC | 60m:z4 | ASCTRI | A | 0.0493 | 0.0389 (0.0339-0.0449) | -0.019 |
| BTC | 60m:z4 | ASCTRI | B | 0.063 | 0.0493 (0.0384-0.0548) | +0.017 |
| BTC | 60m:z4 | BEARFLAG | A | 0.0241 | 0.0159 (0.0148-0.0186) | +0.161 |
| BTC | 60m:z4 | BEARFLAG | B | 0.0219 | 0.0192 (0.0137-0.0247) | +0.040 |
| BTC | 60m:z4 | BEARPEN | A | 0.0126 | 0.00547 (0.00493-0.00602) | +0.015 |
| BTC | 60m:z4 | BEARPEN | B | 0.011 | 0.00548 (0.00274-0.00822) | +0.091 |
| BTC | 60m:z4 | BROADBOT | A | 0.00493 | 0.00876 (0.00712-0.0104) |  |
| BTC | 60m:z4 | BROADBOT | B | 0.011 | 0.00822 (0.00274-0.00822) | +0.439 |
| BTC | 60m:z4 | BROADTOP | A | 0.00821 | 0.00712 (0.00712-0.00876) | +0.125 |
| BTC | 60m:z4 | BROADTOP | B | 0.011 | 0.00548 (0.00548-0.011) | +0.375 |
| BTC | 60m:z4 | BULLFLAG | A | 0.0164 | 0.0159 (0.0137-0.0181) | +0.009 |
| BTC | 60m:z4 | BULLFLAG | B | 0.011 | 0.0219 (0.011-0.0274) | +0.363 |
| BTC | 60m:z4 | BULLPEN | A | 0.00931 | 0.00438 (0.00328-0.00712) | -0.009 |
| BTC | 60m:z4 | BULLPEN | B | 0.00548 | 0.00548 (0.00548-0.0137) | +0.347 |
| BTC | 60m:z4 | CUP | A | 0.00493 | 0.00438 (0.00383-0.00493) | +0.467 |
| BTC | 60m:z4 | CUP | B | 0.00822 | 0.011 (0.00274-0.0164) | +0.614 |
| BTC | 60m:z4 | DBOT | A | 0.137 | 0.17 (0.16-0.175) | -0.000 |
| BTC | 60m:z4 | DBOT | B | 0.167 | 0.178 (0.164-0.189) | +0.013 |
| BTC | 60m:z4 | DESCTRI | A | 0.0493 | 0.0525 (0.0509-0.0536) | +0.149 |
| BTC | 60m:z4 | DESCTRI | B | 0.0384 | 0.0548 (0.0493-0.0849) | -0.122 |
| BTC | 60m:z4 | DTOP | A | 0.149 | 0.155 (0.152-0.176) | +0.094 |
| BTC | 60m:z4 | DTOP | B | 0.189 | 0.164 (0.153-0.17) | +0.002 |
| BTC | 60m:z4 | FALWEDGE | A | 0.0569 | 0.0744 (0.0597-0.0772) | +0.104 |
| BTC | 60m:z4 | FALWEDGE | B | 0.0658 | 0.0877 (0.0822-0.0986) | -0.206 |
| BTC | 60m:z4 | HARM.BEAR | A | 0.00274 | 0.00274 (0.00219-0.00328) | -0.084 |
| BTC | 60m:z4 | HARM.BEAR | B | 0.00548 | 0 (0-0.00274) | -0.340 |
| BTC | 60m:z4 | HARM.BULL | A | 0.00219 | 0.00274 (0.00219-0.00328) | -0.325 |
| BTC | 60m:z4 | HARM.BULL | B | 0.00548 | 0 (0-0.00548) | -0.256 |
| BTC | 60m:z4 | HS | A | 0.0219 | 0.0235 (0.0213-0.0241) | -0.034 |
| BTC | 60m:z4 | HS | B | 0.0164 | 0.0219 (0.011-0.0301) | +0.027 |
| BTC | 60m:z4 | IHS | A | 0.0208 | 0.0203 (0.0192-0.0246) | +0.076 |
| BTC | 60m:z4 | IHS | B | 0.0247 | 0.0192 (0.0137-0.0466) | -0.232 |
| BTC | 60m:z4 | INVCUP | A | 0.00547 | 0.00766 (0.00657-0.00876) | -0.015 |
| BTC | 60m:z4 | INVCUP | B | 0.00274 | 0.00548 (0-0.0137) | +0.575 |
| BTC | 60m:z4 | RECT | A | 0.00766 | 0.0164 (0.012-0.0197) | -0.283 |
| BTC | 60m:z4 | RECT | B | 0.00822 | 0.0164 (0.0164-0.0247) | -0.062 |
| BTC | 60m:z4 | RISWEDGE | A | 0.0608 | 0.0668 (0.0613-0.0684) | +0.055 |
| BTC | 60m:z4 | RISWEDGE | B | 0.0712 | 0.0685 (0.0658-0.0767) | +0.082 |
| BTC | 60m:z4 | ROUNDBOT | A | 0.035 | 0.04 (0.0339-0.0476) | +0.302 |
| BTC | 60m:z4 | ROUNDBOT | B | 0.0438 | 0.0493 (0.0329-0.0521) | +0.641 |
| BTC | 60m:z4 | ROUNDTOP | A | 0.0394 | 0.0411 (0.0339-0.0438) | +0.072 |
| BTC | 60m:z4 | ROUNDTOP | B | 0.0411 | 0.0466 (0.0411-0.0521) | +0.635 |
| BTC | 60m:z4 | SYMTRI | A | 0.0679 | 0.064 (0.0629-0.0668) | +0.038 |
| BTC | 60m:z4 | SYMTRI | B | 0.0904 | 0.0658 (0.0603-0.0658) | +0.087 |
| BTC | 60m:z4 | TRIBOT | A | 0.012 | 0.0213 (0.0192-0.0279) | -0.132 |
| BTC | 60m:z4 | TRIBOT | B | 0.0301 | 0.0274 (0.0137-0.0301) | +0.085 |
| BTC | 60m:z4 | TRITOP | A | 0.0159 | 0.0159 (0.0142-0.0252) | +0.057 |
| BTC | 60m:z4 | TRITOP | B | 0.0247 | 0.0192 (0.0192-0.0274) | -0.262 |
| BTC | 60m:z8 | ABCD.BEAR | A | 0.00821 | 0.00602 (0.00602-0.00657) | +0.031 |
| BTC | 60m:z8 | ABCD.BEAR | B | 0.00274 | 0.00548 (0.00274-0.00822) | +0.187 |
| BTC | 60m:z8 | ABCD.BULL | A | 0.00328 | 0.00602 (0.00602-0.00766) | +0.491 |
| BTC | 60m:z8 | ABCD.BULL | B | 0.011 | 0.00548 (0.00548-0.00548) | -0.084 |
| BTC | 60m:z8 | ASCTRI | A | 0.0164 | 0.012 (0.00985-0.0153) | -0.100 |
| BTC | 60m:z8 | ASCTRI | B | 0.0192 | 0.0137 (0.00548-0.0164) | +0.038 |
| BTC | 60m:z8 | BEARFLAG | A | 0.00109 | 0.000547 (0-0.00109) | +0.352 |
| BTC | 60m:z8 | BEARFLAG | B | 0 | 0.00274 (0-0.00548) |  |
| BTC | 60m:z8 | BEARPEN | A | 0 | 0.000547 (0-0.00109) |  |
| BTC | 60m:z8 | BEARPEN | B | 0 | 0 (0-0.00274) |  |
| BTC | 60m:z8 | BROADBOT | A | 0.000547 | 0.00164 (0.00109-0.00164) |  |
| BTC | 60m:z8 | BROADBOT | B | 0.00274 | 0.00274 (0-0.00548) |  |
| BTC | 60m:z8 | BROADTOP | A | 0.00164 | 0.00164 (0.00109-0.00164) | +0.442 |
| BTC | 60m:z8 | BROADTOP | B | 0.00274 | 0.00548 (0-0.00822) |  |
| BTC | 60m:z8 | BULLFLAG | A | 0 | 0.00109 (0.000547-0.00274) |  |
| BTC | 60m:z8 | BULLFLAG | B | 0 | 0 (0-0.00274) |  |
| BTC | 60m:z8 | BULLPEN | A | 0 | 0.000547 (0.000547-0.00109) |  |
| BTC | 60m:z8 | BULLPEN | B | 0 | 0 (0-0.00274) |  |
| BTC | 60m:z8 | CUP | A | 0.00164 | 0.00219 (0.00219-0.00219) | -0.374 |
| BTC | 60m:z8 | CUP | B | 0.00274 | 0.00548 (0-0.00822) | -0.334 |
| BTC | 60m:z8 | DBOT | A | 0.0411 | 0.0487 (0.0449-0.052) | -0.067 |
| BTC | 60m:z8 | DBOT | B | 0.0466 | 0.0575 (0.0575-0.0603) | -0.221 |
| BTC | 60m:z8 | DESCTRI | A | 0.0131 | 0.0148 (0.0109-0.0159) | +0.064 |
| BTC | 60m:z8 | DESCTRI | B | 0.0164 | 0.0247 (0.0219-0.0274) | +0.146 |
| BTC | 60m:z8 | DTOP | A | 0.0443 | 0.0465 (0.0438-0.0471) | -0.005 |
| BTC | 60m:z8 | DTOP | B | 0.0493 | 0.0521 (0.0438-0.063) | -0.301 |
| BTC | 60m:z8 | FALWEDGE | A | 0.0148 | 0.0241 (0.0203-0.0246) | +0.240 |
| BTC | 60m:z8 | FALWEDGE | B | 0.0192 | 0.0192 (0.011-0.0301) | +0.072 |
| BTC | 60m:z8 | HARM.BEAR | A | 0.00219 | 0.000547 (0-0.00164) | -0.327 |
| BTC | 60m:z8 | HARM.BEAR | B | 0 | 0 (0-0) |  |
| BTC | 60m:z8 | HARM.BULL | A | 0.00164 | 0.000547 (0-0.00219) | -0.095 |
| BTC | 60m:z8 | HARM.BULL | B | 0.00274 | 0.00274 (0-0.00548) |  |
| BTC | 60m:z8 | HS | A | 0.00766 | 0.00712 (0.00602-0.00766) | +0.072 |
| BTC | 60m:z8 | HS | B | 0.00548 | 0.00274 (0-0.00548) | -0.446 |
| BTC | 60m:z8 | IHS | A | 0.00274 | 0.00547 (0.00493-0.00766) | -0.351 |
| BTC | 60m:z8 | IHS | B | 0.0137 | 0.00822 (0.00822-0.011) | -0.132 |
| BTC | 60m:z8 | INVCUP | A | 0.000547 | 0.00274 (0.00219-0.00274) | +0.679 |
| BTC | 60m:z8 | INVCUP | B | 0.00274 | 0.00548 (0.00274-0.00548) |  |
| BTC | 60m:z8 | RECT | A | 0.00274 | 0.00438 (0.00383-0.00438) |  |
| BTC | 60m:z8 | RECT | B | 0 | 0.00274 (0-0.00274) |  |
| BTC | 60m:z8 | RISWEDGE | A | 0.0197 | 0.0148 (0.0142-0.0159) | +0.221 |
| BTC | 60m:z8 | RISWEDGE | B | 0.0219 | 0.0219 (0.0192-0.0301) | -0.142 |
| BTC | 60m:z8 | ROUNDBOT | A | 0.00766 | 0.00985 (0.00985-0.0126) |  |
| BTC | 60m:z8 | ROUNDBOT | B | 0.00274 | 0.0137 (0.011-0.0137) |  |
| BTC | 60m:z8 | ROUNDTOP | A | 0.0115 | 0.0109 (0.00931-0.012) | -0.381 |
| BTC | 60m:z8 | ROUNDTOP | B | 0.011 | 0.00822 (0.00822-0.011) | +0.627 |
| BTC | 60m:z8 | SYMTRI | A | 0.0241 | 0.0181 (0.0115-0.0213) | +0.030 |
| BTC | 60m:z8 | SYMTRI | B | 0.0356 | 0.0192 (0.00548-0.0301) | -0.115 |
| BTC | 60m:z8 | TRIBOT | A | 0.00602 | 0.00493 (0.00274-0.00493) | -0.010 |
| BTC | 60m:z8 | TRIBOT | B | 0.00274 | 0.00548 (0-0.011) |  |
| BTC | 60m:z8 | TRITOP | A | 0.00493 | 0.00493 (0.00438-0.00547) | -0.321 |
| BTC | 60m:z8 | TRITOP | B | 0.00822 | 0.00548 (0.00274-0.011) | -0.551 |
| ETH | 15m:K | LMW.BBOT | A | 0.521 | 0.85 (0.833-0.868) | -0.033 |
| ETH | 15m:K | LMW.BBOT | B | 0.507 | 0.896 (0.814-0.926) | -0.031 |
| ETH | 15m:K | LMW.BTOP | A | 0.577 | 0.853 (0.825-0.876) | +0.008 |
| ETH | 15m:K | LMW.BTOP | B | 0.54 | 0.855 (0.822-0.904) | +0.011 |
| ETH | 15m:K | LMW.DBOT | A | 0.33 | 0.404 (0.395-0.406) | -0.049 |
| ETH | 15m:K | LMW.DBOT | B | 0.378 | 0.392 (0.359-0.395) | +0.009 |
| ETH | 15m:K | LMW.DTOP | A | 0.397 | 0.4 (0.378-0.411) | -0.008 |
| ETH | 15m:K | LMW.DTOP | B | 0.378 | 0.414 (0.403-0.433) | +0.086 |
| ETH | 15m:K | LMW.HS | A | 5.17 | 4.86 (4.82-4.88) | -0.043 |
| ETH | 15m:K | LMW.HS | B | 5.36 | 4.99 (4.87-5) | -0.033 |
| ETH | 15m:K | LMW.HS.SWZ | A | 0.00876 | 0.00602 (0.00493-0.00657) | -0.158 |
| ETH | 15m:K | LMW.HS.SWZ | B | 0 | 0.00548 (0.00274-0.00822) |  |
| ETH | 15m:K | LMW.IHS | A | 5.25 | 4.82 (4.82-4.88) | -0.029 |
| ETH | 15m:K | LMW.IHS | B | 5.31 | 5 (4.96-5.03) | -0.030 |
| ETH | 15m:K | LMW.IHS.SWZ | A | 0.0131 | 0.00876 (0.00657-0.00876) | -0.076 |
| ETH | 15m:K | LMW.IHS.SWZ | B | 0.011 | 0.00274 (0.00274-0.00548) | +0.129 |
| ETH | 15m:K | LMW.RBOT | A | 17 | 15.7 (15.6-15.7) | -0.007 |
| ETH | 15m:K | LMW.RBOT | B | 18.2 | 16.4 (16.3-16.7) | -0.004 |
| ETH | 15m:K | LMW.RTOP | A | 17.4 | 15.7 (15.5-15.7) | -0.006 |
| ETH | 15m:K | LMW.RTOP | B | 18.5 | 16.5 (16.4-16.7) | -0.004 |
| ETH | 15m:K | LMW.TBOT | A | 1.56 | 1.08 (1.05-1.08) | -0.347 |
| ETH | 15m:K | LMW.TBOT | B | 1.69 | 1.05 (0.981-1.12) | -0.323 |
| ETH | 15m:K | LMW.TTOP | A | 1.52 | 1.06 (1.03-1.06) | -0.356 |
| ETH | 15m:K | LMW.TTOP | B | 1.61 | 1.11 (1.03-1.2) | -0.330 |
| ETH | 15m:z2 | ABCD.BEAR | A | 0.211 | 0.226 (0.222-0.229) | +0.045 |
| ETH | 15m:z2 | ABCD.BEAR | B | 0.216 | 0.222 (0.211-0.263) | -0.048 |
| ETH | 15m:z2 | ABCD.BULL | A | 0.204 | 0.242 (0.24-0.256) | -0.024 |
| ETH | 15m:z2 | ABCD.BULL | B | 0.208 | 0.233 (0.219-0.258) | -0.014 |
| ETH | 15m:z2 | ASCTRI | A | 0.481 | 0.514 (0.512-0.553) | +0.035 |
| ETH | 15m:z2 | ASCTRI | B | 0.466 | 0.529 (0.526-0.592) | +0.033 |
| ETH | 15m:z2 | BEARFLAG | A | 0.382 | 0.394 (0.393-0.402) | +0.043 |
| ETH | 15m:z2 | BEARFLAG | B | 0.4 | 0.403 (0.386-0.416) | +0.030 |
| ETH | 15m:z2 | BEARPEN | A | 0.177 | 0.146 (0.136-0.161) | +0.013 |
| ETH | 15m:z2 | BEARPEN | B | 0.17 | 0.14 (0.134-0.164) | -0.012 |
| ETH | 15m:z2 | BROADBOT | A | 0.0777 | 0.122 (0.11-0.123) | -0.090 |
| ETH | 15m:z2 | BROADBOT | B | 0.0795 | 0.115 (0.0932-0.123) | +0.098 |
| ETH | 15m:z2 | BROADTOP | A | 0.0783 | 0.114 (0.1-0.12) | -0.005 |
| ETH | 15m:z2 | BROADTOP | B | 0.0822 | 0.115 (0.107-0.123) | +0.193 |
| ETH | 15m:z2 | BULLFLAG | A | 0.449 | 0.369 (0.355-0.378) | +0.039 |
| ETH | 15m:z2 | BULLFLAG | B | 0.348 | 0.375 (0.353-0.411) | +0.072 |
| ETH | 15m:z2 | BULLPEN | A | 0.199 | 0.14 (0.134-0.151) | +0.007 |
| ETH | 15m:z2 | BULLPEN | B | 0.178 | 0.121 (0.112-0.123) | -0.008 |
| ETH | 15m:z2 | CUP | A | 0.0635 | 0.0728 (0.0706-0.0794) | -0.052 |
| ETH | 15m:z2 | CUP | B | 0.0466 | 0.0767 (0.0685-0.0822) | -0.307 |
| ETH | 15m:z2 | DBOT | A | 1.48 | 1.63 (1.6-1.63) | -0.002 |
| ETH | 15m:z2 | DBOT | B | 1.45 | 1.63 (1.53-1.65) | +0.004 |
| ETH | 15m:z2 | DESCTRI | A | 0.522 | 0.562 (0.543-0.566) | +0.019 |
| ETH | 15m:z2 | DESCTRI | B | 0.493 | 0.581 (0.523-0.592) | +0.092 |
| ETH | 15m:z2 | DTOP | A | 1.65 | 1.59 (1.57-1.64) | -0.015 |
| ETH | 15m:z2 | DTOP | B | 1.59 | 1.62 (1.61-1.65) | +0.010 |
| ETH | 15m:z2 | FALWEDGE | A | 0.749 | 0.789 (0.78-0.815) | +0.038 |
| ETH | 15m:z2 | FALWEDGE | B | 0.847 | 0.77 (0.729-0.825) | +0.002 |
| ETH | 15m:z2 | HARM.BEAR | A | 0.0438 | 0.0405 (0.0312-0.0427) | -0.025 |
| ETH | 15m:z2 | HARM.BEAR | B | 0.0384 | 0.0329 (0.0247-0.0466) | -0.181 |
| ETH | 15m:z2 | HARM.BULL | A | 0.0405 | 0.0361 (0.035-0.0361) | +0.062 |
| ETH | 15m:z2 | HARM.BULL | B | 0.0685 | 0.0301 (0.0301-0.0384) | -0.005 |
| ETH | 15m:z2 | HS | A | 0.287 | 0.284 (0.279-0.287) | -0.004 |
| ETH | 15m:z2 | HS | B | 0.244 | 0.293 (0.271-0.301) | +0.129 |
| ETH | 15m:z2 | IHS | A | 0.279 | 0.275 (0.274-0.278) | -0.017 |
| ETH | 15m:z2 | IHS | B | 0.233 | 0.271 (0.266-0.282) | -0.035 |
| ETH | 15m:z2 | INVCUP | A | 0.0744 | 0.0772 (0.0766-0.0848) | -0.022 |
| ETH | 15m:z2 | INVCUP | B | 0.063 | 0.0849 (0.063-0.0877) | +0.215 |
| ETH | 15m:z2 | RECT | A | 0.114 | 0.152 (0.147-0.172) | +0.007 |
| ETH | 15m:z2 | RECT | B | 0.137 | 0.145 (0.129-0.148) | +0.161 |
| ETH | 15m:z2 | RISWEDGE | A | 0.772 | 0.761 (0.747-0.762) | +0.039 |
| ETH | 15m:z2 | RISWEDGE | B | 0.833 | 0.811 (0.808-0.852) | -0.055 |
| ETH | 15m:z2 | ROUNDBOT | A | 0.102 | 0.236 (0.225-0.25) | +0.216 |
| ETH | 15m:z2 | ROUNDBOT | B | 0.115 | 0.227 (0.175-0.238) | -0.388 |
| ETH | 15m:z2 | ROUNDTOP | A | 0.197 | 0.207 (0.203-0.215) | -0.015 |
| ETH | 15m:z2 | ROUNDTOP | B | 0.263 | 0.23 (0.214-0.244) | +0.009 |
| ETH | 15m:z2 | SYMTRI | A | 0.782 | 0.655 (0.653-0.664) | +0.056 |
| ETH | 15m:z2 | SYMTRI | B | 0.68 | 0.677 (0.649-0.693) | +0.077 |
| ETH | 15m:z2 | TRIBOT | A | 0.171 | 0.23 (0.224-0.253) | -0.086 |
| ETH | 15m:z2 | TRIBOT | B | 0.175 | 0.233 (0.222-0.238) | +0.176 |
| ETH | 15m:z2 | TRITOP | A | 0.182 | 0.235 (0.222-0.239) | +0.023 |
| ETH | 15m:z2 | TRITOP | B | 0.175 | 0.216 (0.216-0.236) | +0.150 |
| ETH | 15m:z4 | ABCD.BEAR | A | 0.0717 | 0.0848 (0.0837-0.0892) | +0.051 |
| ETH | 15m:z4 | ABCD.BEAR | B | 0.063 | 0.0986 (0.0932-0.107) | -0.038 |
| ETH | 15m:z4 | ABCD.BULL | A | 0.0706 | 0.0755 (0.075-0.0783) | +0.075 |
| ETH | 15m:z4 | ABCD.BULL | B | 0.0822 | 0.0712 (0.0685-0.0795) | +0.084 |
| ETH | 15m:z4 | ASCTRI | A | 0.196 | 0.201 (0.194-0.211) | +0.022 |
| ETH | 15m:z4 | ASCTRI | B | 0.184 | 0.206 (0.162-0.211) | -0.087 |
| ETH | 15m:z4 | BEARFLAG | A | 0.0591 | 0.0717 (0.0706-0.0821) | +0.036 |
| ETH | 15m:z4 | BEARFLAG | B | 0.074 | 0.063 (0.0603-0.0795) | +0.034 |
| ETH | 15m:z4 | BEARPEN | A | 0.0334 | 0.0274 (0.0197-0.029) | +0.032 |
| ETH | 15m:z4 | BEARPEN | B | 0.0493 | 0.0219 (0.0164-0.0438) | +0.080 |
| ETH | 15m:z4 | BROADBOT | A | 0.0181 | 0.0367 (0.0367-0.04) | -0.037 |
| ETH | 15m:z4 | BROADBOT | B | 0.0356 | 0.0411 (0.0164-0.0712) | -0.059 |
| ETH | 15m:z4 | BROADTOP | A | 0.0197 | 0.029 (0.029-0.0328) | +0.240 |
| ETH | 15m:z4 | BROADTOP | B | 0.0247 | 0.0384 (0.0356-0.0411) | -0.035 |
| ETH | 15m:z4 | BULLFLAG | A | 0.0668 | 0.0608 (0.0531-0.0695) | +0.027 |
| ETH | 15m:z4 | BULLFLAG | B | 0.0521 | 0.063 (0.0521-0.0658) | +0.036 |
| ETH | 15m:z4 | BULLPEN | A | 0.0345 | 0.0241 (0.0235-0.0252) | +0.044 |
| ETH | 15m:z4 | BULLPEN | B | 0.0356 | 0.0164 (0.011-0.0247) | -0.063 |
| ETH | 15m:z4 | CUP | A | 0.0213 | 0.0317 (0.029-0.0405) | +0.049 |
| ETH | 15m:z4 | CUP | B | 0.0247 | 0.0329 (0.0247-0.0384) | -0.107 |
| ETH | 15m:z4 | DBOT | A | 0.581 | 0.678 (0.669-0.68) | -0.033 |
| ETH | 15m:z4 | DBOT | B | 0.6 | 0.663 (0.622-0.721) | +0.033 |
| ETH | 15m:z4 | DESCTRI | A | 0.191 | 0.217 (0.192-0.218) | +0.015 |
| ETH | 15m:z4 | DESCTRI | B | 0.17 | 0.2 (0.2-0.219) | -0.073 |
| ETH | 15m:z4 | DTOP | A | 0.642 | 0.669 (0.649-0.669) | -0.013 |
| ETH | 15m:z4 | DTOP | B | 0.625 | 0.707 (0.644-0.723) | +0.047 |
| ETH | 15m:z4 | FALWEDGE | A | 0.232 | 0.286 (0.272-0.297) | +0.051 |
| ETH | 15m:z4 | FALWEDGE | B | 0.222 | 0.301 (0.23-0.304) | -0.046 |
| ETH | 15m:z4 | HARM.BEAR | A | 0.0208 | 0.0142 (0.0131-0.0213) | +0.032 |
| ETH | 15m:z4 | HARM.BEAR | B | 0.00274 | 0.0137 (0.0137-0.0164) | +0.256 |
| ETH | 15m:z4 | HARM.BULL | A | 0.0159 | 0.0137 (0.0115-0.0142) | -0.162 |
| ETH | 15m:z4 | HARM.BULL | B | 0.0137 | 0.011 (0.011-0.0219) | +0.415 |
| ETH | 15m:z4 | HS | A | 0.0985 | 0.0996 (0.0914-0.103) | -0.059 |
| ETH | 15m:z4 | HS | B | 0.0904 | 0.0904 (0.0712-0.0959) | +0.010 |
| ETH | 15m:z4 | IHS | A | 0.0925 | 0.103 (0.0985-0.108) | +0.060 |
| ETH | 15m:z4 | IHS | B | 0.0822 | 0.0877 (0.0822-0.121) | +0.064 |
| ETH | 15m:z4 | INVCUP | A | 0.0361 | 0.035 (0.0339-0.035) | +0.011 |
| ETH | 15m:z4 | INVCUP | B | 0.0329 | 0.0219 (0.0164-0.0301) | -0.383 |
| ETH | 15m:z4 | RECT | A | 0.0361 | 0.0602 (0.0531-0.0635) | -0.146 |
| ETH | 15m:z4 | RECT | B | 0.0521 | 0.0603 (0.0521-0.0795) | +0.236 |
| ETH | 15m:z4 | RISWEDGE | A | 0.277 | 0.274 (0.273-0.281) | +0.020 |
| ETH | 15m:z4 | RISWEDGE | B | 0.307 | 0.277 (0.263-0.351) | -0.008 |
| ETH | 15m:z4 | ROUNDBOT | A | 0.115 | 0.184 (0.174-0.193) | +0.036 |
| ETH | 15m:z4 | ROUNDBOT | B | 0.142 | 0.153 (0.134-0.203) | -0.081 |
| ETH | 15m:z4 | ROUNDTOP | A | 0.136 | 0.16 (0.16-0.176) | +0.103 |
| ETH | 15m:z4 | ROUNDTOP | B | 0.184 | 0.164 (0.159-0.206) | -0.018 |
| ETH | 15m:z4 | SYMTRI | A | 0.299 | 0.26 (0.255-0.268) | +0.085 |
| ETH | 15m:z4 | SYMTRI | B | 0.31 | 0.279 (0.252-0.299) | -0.010 |
| ETH | 15m:z4 | TRIBOT | A | 0.0493 | 0.0903 (0.0848-0.0925) | -0.051 |
| ETH | 15m:z4 | TRIBOT | B | 0.0658 | 0.0767 (0.0658-0.0986) | +0.233 |
| ETH | 15m:z4 | TRITOP | A | 0.069 | 0.0859 (0.0712-0.0887) | +0.033 |
| ETH | 15m:z4 | TRITOP | B | 0.0904 | 0.0932 (0.0767-0.107) | +0.035 |
| ETH | 15m:z8 | ABCD.BEAR | A | 0.0312 | 0.0279 (0.0257-0.0307) | +0.138 |
| ETH | 15m:z8 | ABCD.BEAR | B | 0.0164 | 0.0301 (0.0274-0.0356) | +0.709 |
| ETH | 15m:z8 | ABCD.BULL | A | 0.0246 | 0.023 (0.0213-0.023) | +0.016 |
| ETH | 15m:z8 | ABCD.BULL | B | 0.0247 | 0.0219 (0.0192-0.0329) | -0.226 |
| ETH | 15m:z8 | ASCTRI | A | 0.0586 | 0.0542 (0.0531-0.0558) | +0.086 |
| ETH | 15m:z8 | ASCTRI | B | 0.0822 | 0.0548 (0.0438-0.0658) | -0.112 |
| ETH | 15m:z8 | BEARFLAG | A | 0.00219 | 0.00438 (0.00219-0.00493) | +0.292 |
| ETH | 15m:z8 | BEARFLAG | B | 0 | 0.00274 (0-0.00548) |  |
| ETH | 15m:z8 | BEARPEN | A | 0.000547 | 0.00109 (0-0.00274) |  |
| ETH | 15m:z8 | BEARPEN | B | 0 | 0.00548 (0-0.00548) |  |
| ETH | 15m:z8 | BROADBOT | A | 0.00493 | 0.00931 (0.00657-0.0104) | -0.031 |
| ETH | 15m:z8 | BROADBOT | B | 0.00822 | 0.00822 (0.00822-0.011) | -0.020 |
| ETH | 15m:z8 | BROADTOP | A | 0.00876 | 0.00547 (0.00438-0.00821) | -0.507 |
| ETH | 15m:z8 | BROADTOP | B | 0.00274 | 0.00822 (0.00548-0.00822) |  |
| ETH | 15m:z8 | BULLFLAG | A | 0.00219 | 0.00328 (0.00164-0.00821) | -0.077 |
| ETH | 15m:z8 | BULLFLAG | B | 0.00274 | 0.00274 (0-0.00548) | -0.023 |
| ETH | 15m:z8 | BULLPEN | A | 0.00109 | 0.00164 (0.00109-0.00164) | -0.056 |
| ETH | 15m:z8 | BULLPEN | B | 0.00274 | 0.00274 (0-0.00274) | -0.096 |
| ETH | 15m:z8 | CUP | A | 0.00985 | 0.00985 (0.00712-0.0109) | -0.089 |
| ETH | 15m:z8 | CUP | B | 0.00822 | 0.00822 (0.00822-0.0164) | -0.340 |
| ETH | 15m:z8 | DBOT | A | 0.172 | 0.213 (0.205-0.218) | +0.018 |
| ETH | 15m:z8 | DBOT | B | 0.208 | 0.211 (0.2-0.214) | +0.124 |
| ETH | 15m:z8 | DESCTRI | A | 0.0487 | 0.0651 (0.0575-0.0728) | +0.012 |
| ETH | 15m:z8 | DESCTRI | B | 0.0575 | 0.074 (0.0548-0.11) | +0.240 |
| ETH | 15m:z8 | DTOP | A | 0.197 | 0.199 (0.184-0.212) | +0.024 |
| ETH | 15m:z8 | DTOP | B | 0.195 | 0.195 (0.173-0.203) | -0.077 |
| ETH | 15m:z8 | FALWEDGE | A | 0.058 | 0.0887 (0.0816-0.0914) | +0.055 |
| ETH | 15m:z8 | FALWEDGE | B | 0.0767 | 0.101 (0.0822-0.104) | +0.036 |
| ETH | 15m:z8 | HARM.BEAR | A | 0.00438 | 0.00547 (0.00383-0.00602) | -0.312 |
| ETH | 15m:z8 | HARM.BEAR | B | 0.0137 | 0.00548 (0.00274-0.011) | +0.145 |
| ETH | 15m:z8 | HARM.BULL | A | 0.00766 | 0.00493 (0.00274-0.00766) | -0.212 |
| ETH | 15m:z8 | HARM.BULL | B | 0.00548 | 0.00548 (0.00548-0.00822) | -0.150 |
| ETH | 15m:z8 | HS | A | 0.0241 | 0.0301 (0.0279-0.0328) | +0.106 |
| ETH | 15m:z8 | HS | B | 0.0466 | 0.0356 (0.0274-0.0493) | +0.118 |
| ETH | 15m:z8 | IHS | A | 0.0279 | 0.0301 (0.0257-0.0307) | -0.010 |
| ETH | 15m:z8 | IHS | B | 0.0137 | 0.0274 (0.0137-0.0466) | +0.043 |
| ETH | 15m:z8 | INVCUP | A | 0.00602 | 0.0115 (0.00931-0.0148) | -0.325 |
| ETH | 15m:z8 | INVCUP | B | 0.00822 | 0.00822 (0.00274-0.0192) | -0.397 |
| ETH | 15m:z8 | RECT | A | 0.0148 | 0.0153 (0.0109-0.0208) | -0.023 |
| ETH | 15m:z8 | RECT | B | 0.0301 | 0.0164 (0.0137-0.0164) | +0.468 |
| ETH | 15m:z8 | RISWEDGE | A | 0.081 | 0.0761 (0.0679-0.081) | +0.095 |
| ETH | 15m:z8 | RISWEDGE | B | 0.0466 | 0.0822 (0.0712-0.0822) | +0.183 |
| ETH | 15m:z8 | ROUNDBOT | A | 0.0339 | 0.0504 (0.0487-0.0542) | +0.137 |
| ETH | 15m:z8 | ROUNDBOT | B | 0.0466 | 0.0521 (0.0466-0.0712) | +0.115 |
| ETH | 15m:z8 | ROUNDTOP | A | 0.046 | 0.0443 (0.0378-0.0443) | -0.127 |
| ETH | 15m:z8 | ROUNDTOP | B | 0.0493 | 0.0548 (0.0356-0.063) | -0.373 |
| ETH | 15m:z8 | SYMTRI | A | 0.0991 | 0.0843 (0.0783-0.0914) | +0.027 |
| ETH | 15m:z8 | SYMTRI | B | 0.115 | 0.0712 (0.0603-0.0904) | +0.139 |
| ETH | 15m:z8 | TRIBOT | A | 0.0208 | 0.0312 (0.0257-0.0328) | -0.019 |
| ETH | 15m:z8 | TRIBOT | B | 0.0329 | 0.0301 (0.0219-0.0356) | +0.081 |
| ETH | 15m:z8 | TRITOP | A | 0.0219 | 0.0274 (0.0208-0.0317) | -0.012 |
| ETH | 15m:z8 | TRITOP | B | 0.0384 | 0.0247 (0.0219-0.0247) | +0.240 |
| ETH | 240m:K | LMW.BBOT | A | 0.0241 | 0.04 (0.0389-0.0427) | -0.024 |
| ETH | 240m:K | LMW.BBOT | B | 0.0466 | 0.0438 (0.0384-0.0658) | -0.117 |
| ETH | 240m:K | LMW.BTOP | A | 0.0224 | 0.04 (0.0378-0.0465) | +0.261 |
| ETH | 240m:K | LMW.BTOP | B | 0.0521 | 0.0548 (0.0274-0.0603) | +0.021 |
| ETH | 240m:K | LMW.DBOT | A | 0.00219 | 0.00383 (0.00274-0.00438) | -0.516 |
| ETH | 240m:K | LMW.DBOT | B | 0.00548 | 0.00548 (0.00274-0.0137) | -0.548 |
| ETH | 240m:K | LMW.DTOP | A | 0.00328 | 0.00493 (0.00328-0.00547) | -0.302 |
| ETH | 240m:K | LMW.DTOP | B | 0.00822 | 0.00822 (0.00274-0.00822) | -0.041 |
| ETH | 240m:K | LMW.HS | A | 0.208 | 0.175 (0.175-0.178) | -0.049 |
| ETH | 240m:K | LMW.HS | B | 0.197 | 0.203 (0.181-0.211) | -0.060 |
| ETH | 240m:K | LMW.HS.SWZ | A | 0.00438 | 0.00328 (0.00219-0.00383) | +0.137 |
| ETH | 240m:K | LMW.HS.SWZ | B | 0.00822 | 0.00822 (0.00274-0.00822) | +0.000 |
| ETH | 240m:K | LMW.IHS | A | 0.193 | 0.187 (0.171-0.197) | -0.031 |
| ETH | 240m:K | LMW.IHS | B | 0.214 | 0.225 (0.175-0.23) | -0.033 |
| ETH | 240m:K | LMW.IHS.SWZ | A | 0.00438 | 0.00438 (0.00328-0.00547) | +0.297 |
| ETH | 240m:K | LMW.IHS.SWZ | B | 0.00822 | 0.00548 (0-0.00548) | -0.286 |
| ETH | 240m:K | LMW.RBOT | A | 0.257 | 0.226 (0.212-0.227) | -0.008 |
| ETH | 240m:K | LMW.RBOT | B | 0.263 | 0.233 (0.208-0.271) | +0.034 |
| ETH | 240m:K | LMW.RTOP | A | 0.265 | 0.228 (0.213-0.232) | -0.016 |
| ETH | 240m:K | LMW.RTOP | B | 0.269 | 0.238 (0.236-0.29) | -0.008 |
| ETH | 240m:K | LMW.TBOT | A | 0.0816 | 0.0487 (0.0471-0.0536) | -0.311 |
| ETH | 240m:K | LMW.TBOT | B | 0.121 | 0.0712 (0.0493-0.0767) | -0.348 |
| ETH | 240m:K | LMW.TTOP | A | 0.0816 | 0.058 (0.0509-0.0624) | -0.350 |
| ETH | 240m:K | LMW.TTOP | B | 0.0959 | 0.074 (0.0685-0.0904) | -0.429 |
| ETH | 240m:z2 | ABCD.BEAR | A | 0.0175 | 0.0142 (0.0137-0.0164) | -0.002 |
| ETH | 240m:z2 | ABCD.BEAR | B | 0.011 | 0.0164 (0.00822-0.0247) | +0.309 |
| ETH | 240m:z2 | ABCD.BULL | A | 0.00985 | 0.00931 (0.00821-0.0109) | +0.111 |
| ETH | 240m:z2 | ABCD.BULL | B | 0.0192 | 0.0164 (0.0164-0.0192) | +0.201 |
| ETH | 240m:z2 | ASCTRI | A | 0.0279 | 0.0252 (0.0181-0.0339) | -0.035 |
| ETH | 240m:z2 | ASCTRI | B | 0.0329 | 0.0192 (0.0192-0.0274) | -0.007 |
| ETH | 240m:z2 | BEARFLAG | A | 0.0252 | 0.0197 (0.0186-0.0235) | -0.032 |
| ETH | 240m:z2 | BEARFLAG | B | 0.0384 | 0.0247 (0.0219-0.0329) | +0.157 |
| ETH | 240m:z2 | BEARPEN | A | 0.00657 | 0.00657 (0.00547-0.00876) | +0.189 |
| ETH | 240m:z2 | BEARPEN | B | 0.0137 | 0.0137 (0.00274-0.0192) | -0.144 |
| ETH | 240m:z2 | BROADBOT | A | 0.00547 | 0.00821 (0.00657-0.0109) | -0.293 |
| ETH | 240m:z2 | BROADBOT | B | 0 | 0.00822 (0.00548-0.011) |  |
| ETH | 240m:z2 | BROADTOP | A | 0.00931 | 0.00493 (0.00274-0.00657) | +0.105 |
| ETH | 240m:z2 | BROADTOP | B | 0 | 0.011 (0.011-0.011) |  |
| ETH | 240m:z2 | BULLFLAG | A | 0.0235 | 0.0186 (0.0181-0.0192) | -0.070 |
| ETH | 240m:z2 | BULLFLAG | B | 0.0192 | 0.0247 (0.0192-0.0274) | -0.155 |
| ETH | 240m:z2 | BULLPEN | A | 0.0148 | 0.00712 (0.00657-0.00876) | -0.032 |
| ETH | 240m:z2 | BULLPEN | B | 0.00822 | 0.011 (0.00274-0.0192) | +0.044 |
| ETH | 240m:z2 | CUP | A | 0.00493 | 0.00328 (0.00274-0.00438) | +0.605 |
| ETH | 240m:z2 | CUP | B | 0.00274 | 0.00274 (0.00274-0.00548) | +0.616 |
| ETH | 240m:z2 | DBOT | A | 0.0788 | 0.0876 (0.087-0.0892) | -0.028 |
| ETH | 240m:z2 | DBOT | B | 0.0904 | 0.11 (0.101-0.129) | +0.075 |
| ETH | 240m:z2 | DESCTRI | A | 0.0213 | 0.0301 (0.0246-0.0317) | +0.061 |
| ETH | 240m:z2 | DESCTRI | B | 0.0274 | 0.0356 (0.0301-0.0466) | -0.072 |
| ETH | 240m:z2 | DTOP | A | 0.092 | 0.0876 (0.0772-0.0936) | +0.018 |
| ETH | 240m:z2 | DTOP | B | 0.0877 | 0.0877 (0.0795-0.0932) | -0.075 |
| ETH | 240m:z2 | FALWEDGE | A | 0.0372 | 0.0432 (0.0383-0.0432) | +0.053 |
| ETH | 240m:z2 | FALWEDGE | B | 0.0603 | 0.0548 (0.0548-0.063) | -0.083 |
| ETH | 240m:z2 | HARM.BEAR | A | 0.00164 | 0.00164 (0.00109-0.00219) | -0.311 |
| ETH | 240m:z2 | HARM.BEAR | B | 0 | 0 (0-0.00274) |  |
| ETH | 240m:z2 | HARM.BULL | A | 0.00109 | 0.00109 (0.00109-0.00164) | +0.057 |
| ETH | 240m:z2 | HARM.BULL | B | 0 | 0.00274 (0-0.00274) |  |
| ETH | 240m:z2 | HS | A | 0.0148 | 0.017 (0.0115-0.0241) | +0.051 |
| ETH | 240m:z2 | HS | B | 0.0192 | 0.0164 (0.0137-0.0301) | +0.034 |
| ETH | 240m:z2 | IHS | A | 0.0148 | 0.0126 (0.012-0.0175) | -0.074 |
| ETH | 240m:z2 | IHS | B | 0.0137 | 0.011 (0.00548-0.0301) | +0.569 |
| ETH | 240m:z2 | INVCUP | A | 0.00328 | 0.00383 (0.00328-0.00876) | -0.058 |
| ETH | 240m:z2 | INVCUP | B | 0.00822 | 0.00274 (0.00274-0.00548) | +0.077 |
| ETH | 240m:z2 | RECT | A | 0.00547 | 0.00876 (0.00438-0.0115) | -0.009 |
| ETH | 240m:z2 | RECT | B | 0.0164 | 0.00822 (0.00822-0.011) | +0.119 |
| ETH | 240m:z2 | RISWEDGE | A | 0.0471 | 0.0361 (0.035-0.0405) | -0.123 |
| ETH | 240m:z2 | RISWEDGE | B | 0.0411 | 0.0521 (0.0219-0.0521) | +0.207 |
| ETH | 240m:z2 | ROUNDBOT | A | 0.00931 | 0.0175 (0.0131-0.0175) | +0.065 |
| ETH | 240m:z2 | ROUNDBOT | B | 0.00822 | 0.0164 (0.011-0.0219) |  |
| ETH | 240m:z2 | ROUNDTOP | A | 0.0153 | 0.00821 (0.00712-0.00821) | -0.208 |
| ETH | 240m:z2 | ROUNDTOP | B | 0.00822 | 0.011 (0.00822-0.0219) | -0.374 |
| ETH | 240m:z2 | SYMTRI | A | 0.0405 | 0.0345 (0.0339-0.0345) | +0.059 |
| ETH | 240m:z2 | SYMTRI | B | 0.0466 | 0.0356 (0.0301-0.0411) | +0.137 |
| ETH | 240m:z2 | TRIBOT | A | 0.0115 | 0.0159 (0.0115-0.0164) | +0.025 |
| ETH | 240m:z2 | TRIBOT | B | 0.011 | 0.0192 (0.0192-0.0247) | +0.392 |
| ETH | 240m:z2 | TRITOP | A | 0.0164 | 0.0126 (0.00657-0.0131) | -0.104 |
| ETH | 240m:z2 | TRITOP | B | 0.0164 | 0.0137 (0.011-0.0164) | +0.297 |
| ETH | 240m:z4 | ABCD.BEAR | A | 0.00712 | 0.00383 (0.00219-0.00712) | +0.134 |
| ETH | 240m:z4 | ABCD.BEAR | B | 0.00274 | 0.0137 (0.00548-0.0137) | +0.231 |
| ETH | 240m:z4 | ABCD.BULL | A | 0.00383 | 0.00383 (0.00109-0.00602) | +0.260 |
| ETH | 240m:z4 | ABCD.BULL | B | 0.00548 | 0.011 (0.00822-0.0137) | -0.256 |
| ETH | 240m:z4 | ASCTRI | A | 0.00821 | 0.00766 (0.00766-0.0109) | +0.218 |
| ETH | 240m:z4 | ASCTRI | B | 0.00822 | 0.0137 (0.00822-0.0192) | +0.371 |
| ETH | 240m:z4 | BEARFLAG | A | 0.000547 | 0.00328 (0.00219-0.00547) | -0.043 |
| ETH | 240m:z4 | BEARFLAG | B | 0.00822 | 0.00274 (0-0.0137) | -0.181 |
| ETH | 240m:z4 | BEARPEN | A | 0.00164 | 0.00109 (0.000547-0.00219) | -0.222 |
| ETH | 240m:z4 | BEARPEN | B | 0.00274 | 0 (0-0.00274) | -0.089 |
| ETH | 240m:z4 | BROADBOT | A | 0.00274 | 0.00109 (0.000547-0.00219) | +0.451 |
| ETH | 240m:z4 | BROADBOT | B | 0 | 0.00274 (0-0.00274) |  |
| ETH | 240m:z4 | BROADTOP | A | 0.00109 | 0.00109 (0.000547-0.00109) | +0.487 |
| ETH | 240m:z4 | BROADTOP | B | 0 | 0.00274 (0-0.00822) |  |
| ETH | 240m:z4 | BULLFLAG | A | 0.00109 | 0.00164 (0.00164-0.00219) | +0.323 |
| ETH | 240m:z4 | BULLFLAG | B | 0 | 0.00548 (0-0.00822) |  |
| ETH | 240m:z4 | BULLPEN | A | 0.00219 | 0.000547 (0-0.00109) | -0.067 |
| ETH | 240m:z4 | BULLPEN | B | 0 | 0.00274 (0-0.00274) |  |
| ETH | 240m:z4 | CUP | A | 0.00219 | 0.00109 (0.000547-0.00219) | -0.074 |
| ETH | 240m:z4 | CUP | B | 0.00274 | 0.00274 (0-0.00548) |  |
| ETH | 240m:z4 | DBOT | A | 0.0323 | 0.0367 (0.0317-0.0389) | -0.078 |
| ETH | 240m:z4 | DBOT | B | 0.0466 | 0.0438 (0.0356-0.0438) | +0.240 |
| ETH | 240m:z4 | DESCTRI | A | 0.012 | 0.00931 (0.00383-0.0137) | +0.243 |
| ETH | 240m:z4 | DESCTRI | B | 0.0192 | 0.0164 (0.0137-0.0192) | -0.237 |
| ETH | 240m:z4 | DTOP | A | 0.0334 | 0.0323 (0.0317-0.0339) | +0.023 |
| ETH | 240m:z4 | DTOP | B | 0.0356 | 0.0411 (0.0329-0.0438) | +0.430 |
| ETH | 240m:z4 | FALWEDGE | A | 0.0104 | 0.0192 (0.0148-0.0203) | -0.165 |
| ETH | 240m:z4 | FALWEDGE | B | 0.0274 | 0.0247 (0.0192-0.0274) | -0.234 |
| ETH | 240m:z4 | HARM.BEAR | A | 0.00109 | 0 (0-0.000547) | +0.047 |
| ETH | 240m:z4 | HARM.BEAR | B | 0 | 0 (0-0.00548) |  |
| ETH | 240m:z4 | HARM.BULL | A | 0.00109 | 0.00109 (0-0.00109) | +0.288 |
| ETH | 240m:z4 | HARM.BULL | B | 0.00274 | 0 (0-0) | -0.185 |
| ETH | 240m:z4 | HS | A | 0.00712 | 0.00383 (0.00164-0.00438) | +0.100 |
| ETH | 240m:z4 | HS | B | 0.00548 | 0.00548 (0.00274-0.00822) |  |
| ETH | 240m:z4 | IHS | A | 0.00383 | 0.00438 (0.00274-0.00547) | -0.158 |
| ETH | 240m:z4 | IHS | B | 0.00274 | 0.00548 (0.00274-0.0137) | +0.554 |
| ETH | 240m:z4 | INVCUP | A | 0.00274 | 0.00219 (0.00109-0.00328) | +0.672 |
| ETH | 240m:z4 | INVCUP | B | 0.00274 | 0 (0-0) |  |
| ETH | 240m:z4 | RECT | A | 0.00164 | 0.00219 (0.00164-0.00493) | +0.037 |
| ETH | 240m:z4 | RECT | B | 0 | 0.00274 (0-0.00548) |  |
| ETH | 240m:z4 | RISWEDGE | A | 0.0115 | 0.0104 (0.0104-0.0131) | -0.099 |
| ETH | 240m:z4 | RISWEDGE | B | 0.00822 | 0.0247 (0.0137-0.0301) | +0.526 |
| ETH | 240m:z4 | ROUNDBOT | A | 0.00657 | 0.0104 (0.00821-0.0115) | +0.429 |
| ETH | 240m:z4 | ROUNDBOT | B | 0.0137 | 0.0192 (0.00822-0.0192) | -0.335 |
| ETH | 240m:z4 | ROUNDTOP | A | 0.00383 | 0.00657 (0.00493-0.00821) | -0.398 |
| ETH | 240m:z4 | ROUNDTOP | B | 0.00548 | 0.00274 (0.00274-0.0164) |  |
| ETH | 240m:z4 | SYMTRI | A | 0.00931 | 0.00766 (0.00712-0.0137) | +0.436 |
| ETH | 240m:z4 | SYMTRI | B | 0.011 | 0.00822 (0.00822-0.011) | +0.359 |
| ETH | 240m:z4 | TRIBOT | A | 0.00438 | 0.00274 (0.00274-0.00493) | +0.366 |
| ETH | 240m:z4 | TRIBOT | B | 0 | 0.00274 (0.00274-0.00822) |  |
| ETH | 240m:z4 | TRITOP | A | 0.00438 | 0.00383 (0.00219-0.00602) | -0.096 |
| ETH | 240m:z4 | TRITOP | B | 0.00274 | 0.00822 (0.00274-0.00822) |  |
| ETH | 240m:z8 | ABCD.BEAR | A | 0.00164 | 0.000547 (0-0.00164) |  |
| ETH | 240m:z8 | ABCD.BEAR | B | 0 | 0 (0-0.00274) |  |
| ETH | 240m:z8 | ABCD.BULL | A | 0.000547 | 0.00109 (0.000547-0.00164) |  |
| ETH | 240m:z8 | ABCD.BULL | B | 0 | 0.00274 (0-0.00274) |  |
| ETH | 240m:z8 | ASCTRI | A | 0.000547 | 0.00164 (0.000547-0.00274) | -0.292 |
| ETH | 240m:z8 | ASCTRI | B | 0.00274 | 0.00548 (0.00274-0.00548) |  |
| ETH | 240m:z8 | BEARFLAG | A | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | BEARFLAG | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | BEARPEN | A | 0 | 0 (0-0.000547) |  |
| ETH | 240m:z8 | BEARPEN | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | BROADBOT | A | 0.00109 | 0.00109 (0.000547-0.00109) |  |
| ETH | 240m:z8 | BROADBOT | B | 0 | 0.00274 (0-0.00274) |  |
| ETH | 240m:z8 | BROADTOP | A | 0 | 0.000547 (0-0.00109) |  |
| ETH | 240m:z8 | BROADTOP | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | BULLFLAG | A | 0 | 0 (0-0.000547) |  |
| ETH | 240m:z8 | BULLFLAG | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | BULLPEN | A | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | BULLPEN | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | CUP | A | 0 | 0.000547 (0-0.00219) |  |
| ETH | 240m:z8 | CUP | B | 0.00274 | 0 (0-0.00274) |  |
| ETH | 240m:z8 | DBOT | A | 0.00985 | 0.0104 (0.00931-0.0131) | +0.033 |
| ETH | 240m:z8 | DBOT | B | 0.011 | 0.011 (0.011-0.0137) | -0.573 |
| ETH | 240m:z8 | DESCTRI | A | 0.00383 | 0.00109 (0-0.00383) | +0.298 |
| ETH | 240m:z8 | DESCTRI | B | 0.00274 | 0.00274 (0.00274-0.00274) |  |
| ETH | 240m:z8 | DTOP | A | 0.00712 | 0.00766 (0.00547-0.00931) | +0.053 |
| ETH | 240m:z8 | DTOP | B | 0.00822 | 0.00822 (0.00822-0.011) | +0.466 |
| ETH | 240m:z8 | FALWEDGE | A | 0.00274 | 0.00493 (0.00328-0.00657) | -0.094 |
| ETH | 240m:z8 | FALWEDGE | B | 0.00822 | 0.011 (0.00274-0.0137) | +0.510 |
| ETH | 240m:z8 | HARM.BEAR | A | 0.000547 | 0.000547 (0-0.000547) | -0.171 |
| ETH | 240m:z8 | HARM.BEAR | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | HARM.BULL | A | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | HARM.BULL | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | HS | A | 0.00109 | 0.000547 (0.000547-0.00164) | -0.326 |
| ETH | 240m:z8 | HS | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | IHS | A | 0.00109 | 0.00109 (0.000547-0.00164) |  |
| ETH | 240m:z8 | IHS | B | 0.00274 | 0.00274 (0-0.00274) | +0.631 |
| ETH | 240m:z8 | INVCUP | A | 0.000547 | 0.000547 (0-0.00109) |  |
| ETH | 240m:z8 | INVCUP | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | RECT | A | 0.00164 | 0.00109 (0.00109-0.00219) | +0.428 |
| ETH | 240m:z8 | RECT | B | 0 | 0 (0-0.00274) |  |
| ETH | 240m:z8 | RISWEDGE | A | 0.00219 | 0.00219 (0.00109-0.00274) | +0.203 |
| ETH | 240m:z8 | RISWEDGE | B | 0.00274 | 0.00274 (0.00274-0.00548) |  |
| ETH | 240m:z8 | ROUNDBOT | A | 0.00219 | 0.00274 (0.00219-0.00493) |  |
| ETH | 240m:z8 | ROUNDBOT | B | 0 | 0.00548 (0.00274-0.00822) |  |
| ETH | 240m:z8 | ROUNDTOP | A | 0.00109 | 0.00219 (0.00109-0.00328) |  |
| ETH | 240m:z8 | ROUNDTOP | B | 0 | 0 (0-0) |  |
| ETH | 240m:z8 | SYMTRI | A | 0.00383 | 0.00164 (0.00109-0.00328) | +0.196 |
| ETH | 240m:z8 | SYMTRI | B | 0.00548 | 0.00548 (0.00274-0.00548) | -0.081 |
| ETH | 240m:z8 | TRIBOT | A | 0.00109 | 0.00109 (0.000547-0.00219) | +0.450 |
| ETH | 240m:z8 | TRIBOT | B | 0 | 0 (0-0.00274) |  |
| ETH | 240m:z8 | TRITOP | A | 0.00219 | 0.00164 (0.000547-0.00383) | +0.422 |
| ETH | 240m:z8 | TRITOP | B | 0 | 0 (0-0) |  |
| ETH | 5m:z2 | ABCD.BEAR | A | 0.704 | 0.76 (0.749-0.782) | -0.010 |
| ETH | 5m:z2 | ABCD.BEAR | B | 0.743 | 0.781 (0.764-0.866) | +0.005 |
| ETH | 5m:z2 | ABCD.BULL | A | 0.75 | 0.767 (0.754-0.77) | -0.007 |
| ETH | 5m:z2 | ABCD.BULL | B | 0.817 | 0.811 (0.797-0.852) | -0.057 |
| ETH | 5m:z2 | ASCTRI | A | 1.8 | 1.71 (1.66-1.74) | +0.023 |
| ETH | 5m:z2 | ASCTRI | B | 1.72 | 1.8 (1.72-1.89) | +0.031 |
| ETH | 5m:z2 | BEARFLAG | A | 0.976 | 1.15 (1.15-1.15) | +0.007 |
| ETH | 5m:z2 | BEARFLAG | B | 1.15 | 1.15 (1.04-1.18) | +0.018 |
| ETH | 5m:z2 | BEARPEN | A | 0.385 | 0.43 (0.413-0.436) | -0.003 |
| ETH | 5m:z2 | BEARPEN | B | 0.403 | 0.389 (0.375-0.438) | +0.047 |
| ETH | 5m:z2 | BROADBOT | A | 0.254 | 0.326 (0.325-0.337) | -0.002 |
| ETH | 5m:z2 | BROADBOT | B | 0.277 | 0.329 (0.329-0.397) | -0.001 |
| ETH | 5m:z2 | BROADTOP | A | 0.279 | 0.338 (0.316-0.338) | -0.044 |
| ETH | 5m:z2 | BROADTOP | B | 0.299 | 0.334 (0.334-0.356) | -0.008 |
| ETH | 5m:z2 | BULLFLAG | A | 1.36 | 1.11 (1.08-1.12) | -0.010 |
| ETH | 5m:z2 | BULLFLAG | B | 1.23 | 1.13 (1.02-1.15) | +0.079 |
| ETH | 5m:z2 | BULLPEN | A | 0.531 | 0.417 (0.408-0.423) | +0.005 |
| ETH | 5m:z2 | BULLPEN | B | 0.553 | 0.384 (0.345-0.455) | -0.019 |
| ETH | 5m:z2 | CUP | A | 0.229 | 0.246 (0.232-0.256) | +0.023 |
| ETH | 5m:z2 | CUP | B | 0.227 | 0.222 (0.222-0.227) | +0.133 |
| ETH | 5m:z2 | DBOT | A | 4.78 | 4.86 (4.85-4.93) | -0.023 |
| ETH | 5m:z2 | DBOT | B | 5 | 4.89 (4.89-5.16) | -0.020 |
| ETH | 5m:z2 | DESCTRI | A | 1.74 | 1.74 (1.68-1.75) | +0.019 |
| ETH | 5m:z2 | DESCTRI | B | 1.62 | 1.81 (1.75-1.81) | +0.011 |
| ETH | 5m:z2 | DTOP | A | 5.22 | 4.83 (4.81-4.87) | -0.017 |
| ETH | 5m:z2 | DTOP | B | 5.3 | 4.92 (4.9-4.98) | -0.015 |
| ETH | 5m:z2 | FALWEDGE | A | 2.53 | 2.48 (2.47-2.49) | +0.031 |
| ETH | 5m:z2 | FALWEDGE | B | 2.66 | 2.59 (2.42-2.66) | +0.026 |
| ETH | 5m:z2 | HARM.BEAR | A | 0.126 | 0.121 (0.117-0.13) | +0.013 |
| ETH | 5m:z2 | HARM.BEAR | B | 0.142 | 0.115 (0.0877-0.14) | -0.025 |
| ETH | 5m:z2 | HARM.BULL | A | 0.138 | 0.111 (0.109-0.118) | -0.033 |
| ETH | 5m:z2 | HARM.BULL | B | 0.173 | 0.112 (0.0959-0.145) | +0.069 |
| ETH | 5m:z2 | HS | A | 1.01 | 0.895 (0.881-0.9) | +0.032 |
| ETH | 5m:z2 | HS | B | 0.967 | 0.882 (0.88-0.973) | -0.004 |
| ETH | 5m:z2 | IHS | A | 1 | 0.883 (0.881-0.903) | +0.017 |
| ETH | 5m:z2 | IHS | B | 0.945 | 0.912 (0.871-0.943) | +0.051 |
| ETH | 5m:z2 | INVCUP | A | 0.241 | 0.248 (0.247-0.265) | +0.046 |
| ETH | 5m:z2 | INVCUP | B | 0.236 | 0.236 (0.219-0.269) | +0.009 |
| ETH | 5m:z2 | RECT | A | 0.42 | 0.49 (0.483-0.515) | -0.039 |
| ETH | 5m:z2 | RECT | B | 0.452 | 0.532 (0.447-0.559) | +0.076 |
| ETH | 5m:z2 | RISWEDGE | A | 2.64 | 2.4 (2.39-2.47) | +0.008 |
| ETH | 5m:z2 | RISWEDGE | B | 2.72 | 2.54 (2.43-2.78) | -0.004 |
| ETH | 5m:z2 | ROUNDBOT | A | 0.327 | 0.66 (0.621-0.692) | -0.023 |
| ETH | 5m:z2 | ROUNDBOT | B | 0.343 | 0.669 (0.586-0.704) | -0.008 |
| ETH | 5m:z2 | ROUNDTOP | A | 0.6 | 0.632 (0.603-0.638) | +0.016 |
| ETH | 5m:z2 | ROUNDTOP | B | 0.638 | 0.578 (0.54-0.627) | +0.050 |
| ETH | 5m:z2 | SYMTRI | A | 2.58 | 2.1 (2.06-2.15) | +0.038 |
| ETH | 5m:z2 | SYMTRI | B | 2.58 | 2.09 (2.05-2.24) | +0.021 |
| ETH | 5m:z2 | TRIBOT | A | 0.629 | 0.737 (0.733-0.741) | -0.018 |
| ETH | 5m:z2 | TRIBOT | B | 0.578 | 0.86 (0.734-0.871) | -0.116 |
| ETH | 5m:z2 | TRITOP | A | 0.698 | 0.741 (0.729-0.75) | -0.023 |
| ETH | 5m:z2 | TRITOP | B | 0.641 | 0.773 (0.721-0.773) | -0.015 |
| ETH | 5m:z4 | ABCD.BEAR | A | 0.236 | 0.261 (0.252-0.268) | -0.023 |
| ETH | 5m:z4 | ABCD.BEAR | B | 0.227 | 0.266 (0.252-0.269) | +0.040 |
| ETH | 5m:z4 | ABCD.BULL | A | 0.252 | 0.269 (0.257-0.289) | +0.002 |
| ETH | 5m:z4 | ABCD.BULL | B | 0.238 | 0.288 (0.227-0.293) | -0.017 |
| ETH | 5m:z4 | ASCTRI | A | 0.657 | 0.638 (0.63-0.642) | +0.013 |
| ETH | 5m:z4 | ASCTRI | B | 0.6 | 0.644 (0.641-0.68) | +0.029 |
| ETH | 5m:z4 | BEARFLAG | A | 0.127 | 0.217 (0.209-0.23) | -0.002 |
| ETH | 5m:z4 | BEARFLAG | B | 0.148 | 0.195 (0.175-0.236) | -0.012 |
| ETH | 5m:z4 | BEARPEN | A | 0.0712 | 0.075 (0.0739-0.0887) | +0.021 |
| ETH | 5m:z4 | BEARPEN | B | 0.0712 | 0.0795 (0.0603-0.0877) | -0.010 |
| ETH | 5m:z4 | BROADBOT | A | 0.0717 | 0.104 (0.101-0.105) | +0.011 |
| ETH | 5m:z4 | BROADBOT | B | 0.0603 | 0.107 (0.0822-0.112) | +0.013 |
| ETH | 5m:z4 | BROADTOP | A | 0.0766 | 0.103 (0.0936-0.105) | -0.051 |
| ETH | 5m:z4 | BROADTOP | B | 0.0685 | 0.101 (0.0986-0.104) | +0.009 |
| ETH | 5m:z4 | BULLFLAG | A | 0.204 | 0.184 (0.183-0.193) | +0.011 |
| ETH | 5m:z4 | BULLFLAG | B | 0.192 | 0.197 (0.189-0.197) | +0.120 |
| ETH | 5m:z4 | BULLPEN | A | 0.098 | 0.0783 (0.0717-0.0865) | +0.038 |
| ETH | 5m:z4 | BULLPEN | B | 0.121 | 0.0712 (0.0685-0.0795) | -0.105 |
| ETH | 5m:z4 | CUP | A | 0.0985 | 0.109 (0.102-0.111) | -0.045 |
| ETH | 5m:z4 | CUP | B | 0.0795 | 0.11 (0.101-0.129) | -0.230 |
| ETH | 5m:z4 | DBOT | A | 1.93 | 2.15 (2.11-2.17) | +0.008 |
| ETH | 5m:z4 | DBOT | B | 2.04 | 2.16 (2.16-2.18) | +0.033 |
| ETH | 5m:z4 | DESCTRI | A | 0.608 | 0.655 (0.649-0.657) | +0.060 |
| ETH | 5m:z4 | DESCTRI | B | 0.57 | 0.66 (0.611-0.704) | +0.018 |
| ETH | 5m:z4 | DTOP | A | 2.12 | 2.1 (2.08-2.12) | -0.003 |
| ETH | 5m:z4 | DTOP | B | 2.07 | 2.21 (2.13-2.21) | -0.016 |
| ETH | 5m:z4 | FALWEDGE | A | 0.764 | 0.947 (0.919-0.953) | +0.033 |
| ETH | 5m:z4 | FALWEDGE | B | 0.882 | 0.882 (0.874-0.964) | +0.024 |
| ETH | 5m:z4 | HARM.BEAR | A | 0.0454 | 0.0465 (0.0411-0.0558) | -0.016 |
| ETH | 5m:z4 | HARM.BEAR | B | 0.0356 | 0.0493 (0.0411-0.0575) | -0.093 |
| ETH | 5m:z4 | HARM.BULL | A | 0.0536 | 0.0421 (0.0416-0.0493) | -0.062 |
| ETH | 5m:z4 | HARM.BULL | B | 0.0575 | 0.0493 (0.0411-0.0493) | +0.012 |
| ETH | 5m:z4 | HS | A | 0.319 | 0.305 (0.299-0.308) | +0.027 |
| ETH | 5m:z4 | HS | B | 0.274 | 0.318 (0.288-0.34) | +0.073 |
| ETH | 5m:z4 | IHS | A | 0.331 | 0.302 (0.299-0.316) | +0.043 |
| ETH | 5m:z4 | IHS | B | 0.299 | 0.323 (0.285-0.334) | -0.011 |
| ETH | 5m:z4 | INVCUP | A | 0.092 | 0.0958 (0.0941-0.113) | +0.023 |
| ETH | 5m:z4 | INVCUP | B | 0.074 | 0.112 (0.0986-0.115) | +0.059 |
| ETH | 5m:z4 | RECT | A | 0.134 | 0.188 (0.181-0.203) | +0.010 |
| ETH | 5m:z4 | RECT | B | 0.175 | 0.219 (0.206-0.225) | +0.092 |
| ETH | 5m:z4 | RISWEDGE | A | 0.927 | 0.881 (0.859-0.889) | +0.041 |
| ETH | 5m:z4 | RISWEDGE | B | 0.981 | 0.888 (0.885-0.915) | -0.052 |
| ETH | 5m:z4 | ROUNDBOT | A | 0.323 | 0.559 (0.544-0.562) | -0.086 |
| ETH | 5m:z4 | ROUNDBOT | B | 0.384 | 0.545 (0.512-0.559) | +0.109 |
| ETH | 5m:z4 | ROUNDTOP | A | 0.422 | 0.531 (0.495-0.533) | +0.059 |
| ETH | 5m:z4 | ROUNDTOP | B | 0.493 | 0.573 (0.537-0.578) | +0.039 |
| ETH | 5m:z4 | SYMTRI | A | 1.01 | 0.847 (0.841-0.847) | +0.043 |
| ETH | 5m:z4 | SYMTRI | B | 0.934 | 0.836 (0.797-0.885) | +0.052 |
| ETH | 5m:z4 | TRIBOT | A | 0.2 | 0.265 (0.257-0.287) | +0.016 |
| ETH | 5m:z4 | TRIBOT | B | 0.206 | 0.271 (0.255-0.277) | +0.096 |
| ETH | 5m:z4 | TRITOP | A | 0.226 | 0.275 (0.264-0.28) | +0.041 |
| ETH | 5m:z4 | TRITOP | B | 0.233 | 0.274 (0.252-0.274) | +0.078 |
| ETH | 5m:z8 | ABCD.BEAR | A | 0.0848 | 0.0898 (0.0794-0.0903) | +0.036 |
| ETH | 5m:z8 | ABCD.BEAR | B | 0.0767 | 0.0932 (0.0685-0.104) | -0.182 |
| ETH | 5m:z8 | ABCD.BULL | A | 0.0744 | 0.0816 (0.0805-0.0931) | +0.060 |
| ETH | 5m:z8 | ABCD.BULL | B | 0.0712 | 0.0849 (0.0712-0.0904) | -0.074 |
| ETH | 5m:z8 | ASCTRI | A | 0.207 | 0.193 (0.189-0.195) | +0.004 |
| ETH | 5m:z8 | ASCTRI | B | 0.219 | 0.206 (0.192-0.211) | +0.027 |
| ETH | 5m:z8 | BEARFLAG | A | 0.00274 | 0.0181 (0.0148-0.0213) | -0.095 |
| ETH | 5m:z8 | BEARFLAG | B | 0.00548 | 0.00548 (0-0.0192) | -0.088 |
| ETH | 5m:z8 | BEARPEN | A | 0.00328 | 0.00602 (0.00547-0.00821) | +0.194 |
| ETH | 5m:z8 | BEARPEN | B | 0.00274 | 0.00274 (0-0.00822) | -0.159 |
| ETH | 5m:z8 | BROADBOT | A | 0.017 | 0.0268 (0.0257-0.029) | +0.188 |
| ETH | 5m:z8 | BROADBOT | B | 0.011 | 0.0219 (0.011-0.0274) | +0.482 |
| ETH | 5m:z8 | BROADTOP | A | 0.0257 | 0.0235 (0.0203-0.0257) | +0.023 |
| ETH | 5m:z8 | BROADTOP | B | 0.0247 | 0.0301 (0.0247-0.0384) | -0.039 |
| ETH | 5m:z8 | BULLFLAG | A | 0.00438 | 0.0126 (0.0109-0.0131) | -0.101 |
| ETH | 5m:z8 | BULLFLAG | B | 0.00822 | 0.00548 (0.00274-0.0192) | +0.287 |
| ETH | 5m:z8 | BULLPEN | A | 0.00438 | 0.00493 (0.00438-0.00547) | +0.073 |
| ETH | 5m:z8 | BULLPEN | B | 0.0137 | 0.00274 (0-0.00548) | -0.151 |
| ETH | 5m:z8 | CUP | A | 0.0263 | 0.0378 (0.0312-0.0383) | -0.028 |
| ETH | 5m:z8 | CUP | B | 0.0411 | 0.0411 (0.0384-0.0466) | +0.174 |
| ETH | 5m:z8 | DBOT | A | 0.604 | 0.663 (0.657-0.675) | -0.034 |
| ETH | 5m:z8 | DBOT | B | 0.606 | 0.663 (0.649-0.696) | +0.015 |
| ETH | 5m:z8 | DESCTRI | A | 0.194 | 0.21 (0.193-0.215) | +0.030 |
| ETH | 5m:z8 | DESCTRI | B | 0.178 | 0.186 (0.184-0.214) | -0.080 |
| ETH | 5m:z8 | DTOP | A | 0.668 | 0.649 (0.638-0.649) | -0.021 |
| ETH | 5m:z8 | DTOP | B | 0.658 | 0.712 (0.649-0.715) | -0.002 |
| ETH | 5m:z8 | FALWEDGE | A | 0.195 | 0.259 (0.257-0.275) | +0.025 |
| ETH | 5m:z8 | FALWEDGE | B | 0.181 | 0.266 (0.255-0.31) | -0.027 |
| ETH | 5m:z8 | HARM.BEAR | A | 0.023 | 0.0197 (0.0181-0.0203) | +0.021 |
| ETH | 5m:z8 | HARM.BEAR | B | 0.011 | 0.0192 (0.011-0.0247) | -0.240 |
| ETH | 5m:z8 | HARM.BULL | A | 0.0203 | 0.0175 (0.0153-0.0181) | -0.153 |
| ETH | 5m:z8 | HARM.BULL | B | 0.0164 | 0.0219 (0.0137-0.0219) | +0.343 |
| ETH | 5m:z8 | HS | A | 0.102 | 0.0914 (0.0898-0.102) | +0.015 |
| ETH | 5m:z8 | HS | B | 0.0904 | 0.0932 (0.0932-0.101) | +0.185 |
| ETH | 5m:z8 | IHS | A | 0.108 | 0.0892 (0.0859-0.0952) | +0.034 |
| ETH | 5m:z8 | IHS | B | 0.104 | 0.0986 (0.0849-0.112) | +0.088 |
| ETH | 5m:z8 | INVCUP | A | 0.0334 | 0.0411 (0.0323-0.0443) | +0.030 |
| ETH | 5m:z8 | INVCUP | B | 0.0247 | 0.0274 (0.0247-0.0384) | -0.344 |
| ETH | 5m:z8 | RECT | A | 0.0383 | 0.0432 (0.0421-0.0515) | +0.066 |
| ETH | 5m:z8 | RECT | B | 0.0575 | 0.0575 (0.0521-0.0712) | -0.227 |
| ETH | 5m:z8 | RISWEDGE | A | 0.251 | 0.248 (0.247-0.252) | +0.015 |
| ETH | 5m:z8 | RISWEDGE | B | 0.244 | 0.258 (0.244-0.367) | +0.040 |
| ETH | 5m:z8 | ROUNDBOT | A | 0.114 | 0.171 (0.163-0.172) | +0.068 |
| ETH | 5m:z8 | ROUNDBOT | B | 0.14 | 0.156 (0.134-0.195) | -0.401 |
| ETH | 5m:z8 | ROUNDTOP | A | 0.137 | 0.15 (0.144-0.172) | +0.115 |
| ETH | 5m:z8 | ROUNDTOP | B | 0.159 | 0.156 (0.153-0.214) | +0.151 |
| ETH | 5m:z8 | SYMTRI | A | 0.369 | 0.274 (0.264-0.288) | +0.061 |
| ETH | 5m:z8 | SYMTRI | B | 0.356 | 0.293 (0.279-0.312) | +0.045 |
| ETH | 5m:z8 | TRIBOT | A | 0.0575 | 0.0761 (0.0712-0.081) | -0.074 |
| ETH | 5m:z8 | TRIBOT | B | 0.0603 | 0.0795 (0.0712-0.0822) | -0.011 |
| ETH | 5m:z8 | TRITOP | A | 0.0695 | 0.0805 (0.0619-0.0816) | -0.018 |
| ETH | 5m:z8 | TRITOP | B | 0.0712 | 0.0822 (0.0767-0.0877) | +0.334 |
| ETH | 60m:K | LMW.BBOT | A | 0.125 | 0.209 (0.198-0.225) | +0.000 |
| ETH | 60m:K | LMW.BBOT | B | 0.14 | 0.222 (0.219-0.247) | -0.012 |
| ETH | 60m:K | LMW.BTOP | A | 0.145 | 0.207 (0.205-0.208) | +0.063 |
| ETH | 60m:K | LMW.BTOP | B | 0.189 | 0.249 (0.206-0.258) | +0.103 |
| ETH | 60m:K | LMW.DBOT | A | 0.0504 | 0.0487 (0.0438-0.0498) | +0.007 |
| ETH | 60m:K | LMW.DBOT | B | 0.0438 | 0.0493 (0.0247-0.0493) | -0.211 |
| ETH | 60m:K | LMW.DTOP | A | 0.0515 | 0.046 (0.0394-0.052) | -0.043 |
| ETH | 60m:K | LMW.DTOP | B | 0.0575 | 0.0411 (0.0384-0.0603) | +0.086 |
| ETH | 60m:K | LMW.HS | A | 1.14 | 1.04 (1.03-1.05) | -0.027 |
| ETH | 60m:K | LMW.HS | B | 1.2 | 1.1 (1.07-1.12) | -0.033 |
| ETH | 60m:K | LMW.HS.SWZ | A | 0.00931 | 0.0109 (0.00876-0.0126) | +0.033 |
| ETH | 60m:K | LMW.HS.SWZ | B | 0.0137 | 0.00822 (0.00274-0.00822) | -0.134 |
| ETH | 60m:K | LMW.IHS | A | 1.18 | 1.06 (1.04-1.07) | -0.040 |
| ETH | 60m:K | LMW.IHS | B | 1.18 | 1.14 (1.13-1.15) | -0.051 |
| ETH | 60m:K | LMW.IHS.SWZ | A | 0.012 | 0.00876 (0.00712-0.0126) | -0.084 |
| ETH | 60m:K | LMW.IHS.SWZ | B | 0.0219 | 0.00548 (0.00274-0.0219) | +0.005 |
| ETH | 60m:K | LMW.RBOT | A | 2.75 | 2.41 (2.4-2.43) | -0.007 |
| ETH | 60m:K | LMW.RBOT | B | 2.77 | 2.63 (2.58-2.63) | -0.013 |
| ETH | 60m:K | LMW.RTOP | A | 2.89 | 2.38 (2.35-2.43) | -0.008 |
| ETH | 60m:K | LMW.RTOP | B | 2.9 | 2.67 (2.54-2.72) | -0.030 |
| ETH | 60m:K | LMW.TBOT | A | 0.452 | 0.256 (0.242-0.283) | -0.343 |
| ETH | 60m:K | LMW.TBOT | B | 0.444 | 0.282 (0.26-0.282) | -0.348 |
| ETH | 60m:K | LMW.TTOP | A | 0.452 | 0.269 (0.265-0.286) | -0.350 |
| ETH | 60m:K | LMW.TTOP | B | 0.389 | 0.271 (0.269-0.312) | -0.395 |
| ETH | 60m:z2 | ABCD.BEAR | A | 0.0454 | 0.0591 (0.0553-0.0668) | +0.072 |
| ETH | 60m:z2 | ABCD.BEAR | B | 0.0521 | 0.074 (0.0575-0.0795) | +0.038 |
| ETH | 60m:z2 | ABCD.BULL | A | 0.0493 | 0.0542 (0.0454-0.0597) | +0.055 |
| ETH | 60m:z2 | ABCD.BULL | B | 0.0603 | 0.0493 (0.0356-0.0575) | +0.090 |
| ETH | 60m:z2 | ASCTRI | A | 0.124 | 0.13 (0.128-0.151) | -0.016 |
| ETH | 60m:z2 | ASCTRI | B | 0.134 | 0.132 (0.0986-0.14) | -0.046 |
| ETH | 60m:z2 | BEARFLAG | A | 0.113 | 0.103 (0.103-0.111) | -0.041 |
| ETH | 60m:z2 | BEARFLAG | B | 0.126 | 0.107 (0.101-0.132) | -0.048 |
| ETH | 60m:z2 | BEARPEN | A | 0.0509 | 0.035 (0.0296-0.04) | -0.068 |
| ETH | 60m:z2 | BEARPEN | B | 0.063 | 0.0411 (0.0329-0.0466) | -0.041 |
| ETH | 60m:z2 | BROADBOT | A | 0.0181 | 0.0279 (0.0224-0.0285) | -0.020 |
| ETH | 60m:z2 | BROADBOT | B | 0.00822 | 0.0301 (0.0301-0.0438) | -0.523 |
| ETH | 60m:z2 | BROADTOP | A | 0.017 | 0.0241 (0.023-0.0296) | +0.267 |
| ETH | 60m:z2 | BROADTOP | B | 0.0192 | 0.0301 (0.0219-0.0356) | -0.053 |
| ETH | 60m:z2 | BULLFLAG | A | 0.115 | 0.0925 (0.0876-0.0958) | +0.017 |
| ETH | 60m:z2 | BULLFLAG | B | 0.0877 | 0.0959 (0.0959-0.0986) | -0.022 |
| ETH | 60m:z2 | BULLPEN | A | 0.0657 | 0.0339 (0.029-0.0361) | -0.045 |
| ETH | 60m:z2 | BULLPEN | B | 0.063 | 0.0356 (0.0301-0.0466) | +0.091 |
| ETH | 60m:z2 | CUP | A | 0.0142 | 0.0175 (0.0175-0.0203) | -0.129 |
| ETH | 60m:z2 | CUP | B | 0.0164 | 0.0137 (0.0137-0.0219) | +0.072 |
| ETH | 60m:z2 | DBOT | A | 0.349 | 0.386 (0.386-0.395) | -0.039 |
| ETH | 60m:z2 | DBOT | B | 0.378 | 0.425 (0.403-0.43) | +0.051 |
| ETH | 60m:z2 | DESCTRI | A | 0.113 | 0.132 (0.128-0.134) | -0.063 |
| ETH | 60m:z2 | DESCTRI | B | 0.112 | 0.132 (0.0932-0.145) | +0.155 |
| ETH | 60m:z2 | DTOP | A | 0.387 | 0.371 (0.368-0.379) | -0.023 |
| ETH | 60m:z2 | DTOP | B | 0.406 | 0.4 (0.373-0.416) | +0.042 |
| ETH | 60m:z2 | FALWEDGE | A | 0.181 | 0.171 (0.167-0.189) | +0.010 |
| ETH | 60m:z2 | FALWEDGE | B | 0.197 | 0.184 (0.17-0.203) | -0.016 |
| ETH | 60m:z2 | HARM.BEAR | A | 0.0109 | 0.00985 (0.00766-0.0131) | -0.293 |
| ETH | 60m:z2 | HARM.BEAR | B | 0.00822 | 0.011 (0.00822-0.0192) | +0.291 |
| ETH | 60m:z2 | HARM.BULL | A | 0.00876 | 0.0104 (0.00821-0.0137) | +0.065 |
| ETH | 60m:z2 | HARM.BULL | B | 0.011 | 0.00548 (0.00274-0.00548) | +0.039 |
| ETH | 60m:z2 | HS | A | 0.0629 | 0.0673 (0.0673-0.0772) | -0.038 |
| ETH | 60m:z2 | HS | B | 0.063 | 0.0685 (0.0603-0.0685) | +0.020 |
| ETH | 60m:z2 | IHS | A | 0.0619 | 0.0679 (0.0597-0.0723) | -0.068 |
| ETH | 60m:z2 | IHS | B | 0.0767 | 0.0658 (0.0575-0.0767) | +0.445 |
| ETH | 60m:z2 | INVCUP | A | 0.023 | 0.0186 (0.0148-0.0203) | +0.087 |
| ETH | 60m:z2 | INVCUP | B | 0.00548 | 0.0219 (0.0192-0.0274) |  |
| ETH | 60m:z2 | RECT | A | 0.0285 | 0.0383 (0.0307-0.0389) | -0.170 |
| ETH | 60m:z2 | RECT | B | 0.0603 | 0.0356 (0.0247-0.0466) | -0.072 |
| ETH | 60m:z2 | RISWEDGE | A | 0.169 | 0.184 (0.179-0.186) | -0.006 |
| ETH | 60m:z2 | RISWEDGE | B | 0.184 | 0.184 (0.173-0.26) | +0.012 |
| ETH | 60m:z2 | ROUNDBOT | A | 0.0192 | 0.0602 (0.0575-0.0608) | -0.421 |
| ETH | 60m:z2 | ROUNDBOT | B | 0.0438 | 0.0521 (0.0384-0.063) | -0.109 |
| ETH | 60m:z2 | ROUNDTOP | A | 0.0438 | 0.0432 (0.0405-0.0482) | +0.007 |
| ETH | 60m:z2 | ROUNDTOP | B | 0.0575 | 0.0493 (0.0438-0.0658) |  |
| ETH | 60m:z2 | SYMTRI | A | 0.163 | 0.168 (0.15-0.181) | +0.045 |
| ETH | 60m:z2 | SYMTRI | B | 0.186 | 0.153 (0.145-0.173) | -0.075 |
| ETH | 60m:z2 | TRIBOT | A | 0.0345 | 0.0586 (0.0525-0.0619) | -0.085 |
| ETH | 60m:z2 | TRIBOT | B | 0.0521 | 0.0521 (0.0493-0.0658) | +0.233 |
| ETH | 60m:z2 | TRITOP | A | 0.0509 | 0.0553 (0.0509-0.0591) | +0.010 |
| ETH | 60m:z2 | TRITOP | B | 0.0466 | 0.0603 (0.0466-0.063) | +0.067 |
| ETH | 60m:z4 | ABCD.BEAR | A | 0.029 | 0.0246 (0.0213-0.0252) | +0.057 |
| ETH | 60m:z4 | ABCD.BEAR | B | 0.00822 | 0.0247 (0.0137-0.0247) | +0.610 |
| ETH | 60m:z4 | ABCD.BULL | A | 0.0153 | 0.017 (0.017-0.0175) | +0.140 |
| ETH | 60m:z4 | ABCD.BULL | B | 0.0192 | 0.0247 (0.0247-0.0356) | -0.053 |
| ETH | 60m:z4 | ASCTRI | A | 0.0427 | 0.0416 (0.0389-0.0493) | -0.084 |
| ETH | 60m:z4 | ASCTRI | B | 0.0658 | 0.0329 (0.0329-0.0438) | -0.031 |
| ETH | 60m:z4 | BEARFLAG | A | 0.0142 | 0.0153 (0.0142-0.0192) | +0.029 |
| ETH | 60m:z4 | BEARFLAG | B | 0.0301 | 0.0137 (0.00822-0.0137) | -0.157 |
| ETH | 60m:z4 | BEARPEN | A | 0.00766 | 0.00438 (0.00164-0.00657) | +0.018 |
| ETH | 60m:z4 | BEARPEN | B | 0.00822 | 0.00822 (0.00822-0.011) | -0.153 |
| ETH | 60m:z4 | BROADBOT | A | 0.00438 | 0.00876 (0.00657-0.0104) | +0.132 |
| ETH | 60m:z4 | BROADBOT | B | 0.00274 | 0.011 (0.00548-0.0219) | +0.484 |
| ETH | 60m:z4 | BROADTOP | A | 0.00931 | 0.00547 (0.00383-0.00821) | +0.194 |
| ETH | 60m:z4 | BROADTOP | B | 0.00822 | 0.011 (0.00274-0.0164) | +0.459 |
| ETH | 60m:z4 | BULLFLAG | A | 0.012 | 0.0115 (0.0109-0.0153) | -0.013 |
| ETH | 60m:z4 | BULLFLAG | B | 0.00822 | 0.0192 (0.0164-0.0219) | +0.374 |
| ETH | 60m:z4 | BULLPEN | A | 0.00821 | 0.00493 (0.00274-0.00657) | +0.044 |
| ETH | 60m:z4 | BULLPEN | B | 0.011 | 0.00548 (0.00274-0.011) | +0.177 |
| ETH | 60m:z4 | CUP | A | 0.00657 | 0.00657 (0.00602-0.00931) | +0.137 |
| ETH | 60m:z4 | CUP | B | 0.00822 | 0.011 (0.00822-0.011) | +0.309 |
| ETH | 60m:z4 | DBOT | A | 0.139 | 0.16 (0.155-0.169) | +0.009 |
| ETH | 60m:z4 | DBOT | B | 0.162 | 0.184 (0.178-0.197) | +0.070 |
| ETH | 60m:z4 | DESCTRI | A | 0.04 | 0.0525 (0.0449-0.0531) | +0.054 |
| ETH | 60m:z4 | DESCTRI | B | 0.0438 | 0.0575 (0.0493-0.0685) | +0.147 |
| ETH | 60m:z4 | DTOP | A | 0.156 | 0.158 (0.149-0.159) | +0.028 |
| ETH | 60m:z4 | DTOP | B | 0.153 | 0.145 (0.145-0.153) | -0.088 |
| ETH | 60m:z4 | FALWEDGE | A | 0.0553 | 0.069 (0.0657-0.0695) | +0.017 |
| ETH | 60m:z4 | FALWEDGE | B | 0.0575 | 0.0877 (0.0849-0.0959) | -0.084 |
| ETH | 60m:z4 | HARM.BEAR | A | 0.00274 | 0.00383 (0.00383-0.00438) | -0.032 |
| ETH | 60m:z4 | HARM.BEAR | B | 0.00822 | 0.00274 (0.00274-0.00548) | +0.543 |
| ETH | 60m:z4 | HARM.BULL | A | 0.000547 | 0.00328 (0.00164-0.00493) | +0.602 |
| ETH | 60m:z4 | HARM.BULL | B | 0.00274 | 0 (0-0.00548) | -0.237 |
| ETH | 60m:z4 | HS | A | 0.0241 | 0.0263 (0.0235-0.0268) | +0.078 |
| ETH | 60m:z4 | HS | B | 0.0274 | 0.0301 (0.0219-0.0384) | +0.095 |
| ETH | 60m:z4 | IHS | A | 0.0224 | 0.0219 (0.0186-0.0257) | +0.030 |
| ETH | 60m:z4 | IHS | B | 0.0164 | 0.0164 (0.0164-0.0329) | +0.309 |
| ETH | 60m:z4 | INVCUP | A | 0.0104 | 0.00657 (0.00602-0.00712) | -0.071 |
| ETH | 60m:z4 | INVCUP | B | 0.00274 | 0.00822 (0-0.0137) | +0.690 |
| ETH | 60m:z4 | RECT | A | 0.0109 | 0.0142 (0.0104-0.0164) | +0.053 |
| ETH | 60m:z4 | RECT | B | 0.0192 | 0.011 (0.00548-0.0164) | +0.120 |
| ETH | 60m:z4 | RISWEDGE | A | 0.0723 | 0.0602 (0.0569-0.0608) | +0.028 |
| ETH | 60m:z4 | RISWEDGE | B | 0.0438 | 0.0521 (0.0521-0.0548) | +0.121 |
| ETH | 60m:z4 | ROUNDBOT | A | 0.0268 | 0.0421 (0.0411-0.0476) | -0.059 |
| ETH | 60m:z4 | ROUNDBOT | B | 0.0329 | 0.0466 (0.0384-0.0685) |  |
| ETH | 60m:z4 | ROUNDTOP | A | 0.0389 | 0.0356 (0.0356-0.0361) | -0.271 |
| ETH | 60m:z4 | ROUNDTOP | B | 0.0329 | 0.0356 (0.0301-0.0466) | +0.366 |
| ETH | 60m:z4 | SYMTRI | A | 0.0657 | 0.0613 (0.0591-0.069) | +0.099 |
| ETH | 60m:z4 | SYMTRI | B | 0.0712 | 0.0575 (0.0575-0.063) | +0.064 |
| ETH | 60m:z4 | TRIBOT | A | 0.0153 | 0.0263 (0.0192-0.0268) | -0.106 |
| ETH | 60m:z4 | TRIBOT | B | 0.0164 | 0.0192 (0.0164-0.0219) | +0.400 |
| ETH | 60m:z4 | TRITOP | A | 0.0192 | 0.0208 (0.0153-0.0279) | -0.007 |
| ETH | 60m:z4 | TRITOP | B | 0.0247 | 0.0192 (0.00822-0.0219) | +0.376 |
| ETH | 60m:z8 | ABCD.BEAR | A | 0.00985 | 0.00493 (0.00383-0.00712) | +0.053 |
| ETH | 60m:z8 | ABCD.BEAR | B | 0.00274 | 0.011 (0.00274-0.0219) | +0.000 |
| ETH | 60m:z8 | ABCD.BULL | A | 0.00657 | 0.00547 (0.00274-0.00657) | +0.054 |
| ETH | 60m:z8 | ABCD.BULL | B | 0.00822 | 0.00822 (0.00274-0.011) | +0.035 |
| ETH | 60m:z8 | ASCTRI | A | 0.0137 | 0.0137 (0.00876-0.0142) | +0.050 |
| ETH | 60m:z8 | ASCTRI | B | 0.0164 | 0.0137 (0.00822-0.0219) | -0.216 |
| ETH | 60m:z8 | BEARFLAG | A | 0 | 0.000547 (0-0.00219) |  |
| ETH | 60m:z8 | BEARFLAG | B | 0 | 0 (0-0) |  |
| ETH | 60m:z8 | BEARPEN | A | 0 | 0 (0-0.000547) |  |
| ETH | 60m:z8 | BEARPEN | B | 0 | 0 (0-0) |  |
| ETH | 60m:z8 | BROADBOT | A | 0.000547 | 0.00109 (0.00109-0.00109) | -0.511 |
| ETH | 60m:z8 | BROADBOT | B | 0.00274 | 0 (0-0.00274) |  |
| ETH | 60m:z8 | BROADTOP | A | 0 | 0.00109 (0-0.00164) |  |
| ETH | 60m:z8 | BROADTOP | B | 0 | 0.00548 (0-0.00822) |  |
| ETH | 60m:z8 | BULLFLAG | A | 0.00109 | 0.000547 (0-0.00164) | -0.134 |
| ETH | 60m:z8 | BULLFLAG | B | 0 | 0 (0-0.00274) |  |
| ETH | 60m:z8 | BULLPEN | A | 0.000547 | 0 (0-0.000547) | +0.853 |
| ETH | 60m:z8 | BULLPEN | B | 0 | 0 (0-0) |  |
| ETH | 60m:z8 | CUP | A | 0.00164 | 0.00164 (0.00109-0.00219) | +0.019 |
| ETH | 60m:z8 | CUP | B | 0.00274 | 0.00274 (0-0.00548) | +0.661 |
| ETH | 60m:z8 | DBOT | A | 0.0421 | 0.0493 (0.0416-0.0504) | +0.039 |
| ETH | 60m:z8 | DBOT | B | 0.0466 | 0.0438 (0.0411-0.0521) | +0.237 |
| ETH | 60m:z8 | DESCTRI | A | 0.0148 | 0.0131 (0.00766-0.0175) | +0.237 |
| ETH | 60m:z8 | DESCTRI | B | 0.0219 | 0.0192 (0.0137-0.0219) | -0.163 |
| ETH | 60m:z8 | DTOP | A | 0.0438 | 0.0449 (0.0394-0.0449) | -0.021 |
| ETH | 60m:z8 | DTOP | B | 0.0411 | 0.0493 (0.0411-0.0521) | +0.048 |
| ETH | 60m:z8 | FALWEDGE | A | 0.012 | 0.0241 (0.0181-0.029) | -0.077 |
| ETH | 60m:z8 | FALWEDGE | B | 0.0247 | 0.0356 (0.0137-0.0356) | -0.096 |
| ETH | 60m:z8 | HARM.BEAR | A | 0.00547 | 0.000547 (0-0.00109) | +0.147 |
| ETH | 60m:z8 | HARM.BEAR | B | 0 | 0 (0-0.00822) |  |
| ETH | 60m:z8 | HARM.BULL | A | 0.00164 | 0.000547 (0.000547-0.00109) | +0.167 |
| ETH | 60m:z8 | HARM.BULL | B | 0 | 0 (0-0.00548) |  |
| ETH | 60m:z8 | HS | A | 0.00931 | 0.00657 (0.00164-0.00821) | -0.135 |
| ETH | 60m:z8 | HS | B | 0.00822 | 0.00274 (0-0.00822) | -0.331 |
| ETH | 60m:z8 | IHS | A | 0.00712 | 0.00493 (0.00493-0.00821) | -0.365 |
| ETH | 60m:z8 | IHS | B | 0.00548 | 0.00822 (0.00548-0.0137) | +0.593 |
| ETH | 60m:z8 | INVCUP | A | 0.00438 | 0.00274 (0.00164-0.00438) | +0.152 |
| ETH | 60m:z8 | INVCUP | B | 0 | 0 (0-0) |  |
| ETH | 60m:z8 | RECT | A | 0.00274 | 0.00438 (0.00383-0.00438) | +0.112 |
| ETH | 60m:z8 | RECT | B | 0.00274 | 0.00274 (0.00274-0.00274) | +0.469 |
| ETH | 60m:z8 | RISWEDGE | A | 0.0115 | 0.0142 (0.00876-0.0181) | -0.291 |
| ETH | 60m:z8 | RISWEDGE | B | 0.0137 | 0.0219 (0.011-0.0329) | +0.532 |
| ETH | 60m:z8 | ROUNDBOT | A | 0.00931 | 0.0142 (0.0115-0.0148) | +0.286 |
| ETH | 60m:z8 | ROUNDBOT | B | 0.0137 | 0.0137 (0.00274-0.0164) |  |
| ETH | 60m:z8 | ROUNDTOP | A | 0.0104 | 0.00985 (0.00766-0.0109) | -0.447 |
| ETH | 60m:z8 | ROUNDTOP | B | 0.00822 | 0.011 (0.00548-0.0164) |  |
| ETH | 60m:z8 | SYMTRI | A | 0.0252 | 0.0159 (0.0115-0.0186) | +0.170 |
| ETH | 60m:z8 | SYMTRI | B | 0.0329 | 0.0247 (0.0164-0.0247) | +0.193 |
| ETH | 60m:z8 | TRIBOT | A | 0.00438 | 0.00493 (0.00493-0.00602) | +0.422 |
| ETH | 60m:z8 | TRIBOT | B | 0.00822 | 0.00822 (0.00548-0.00822) | +0.420 |
| ETH | 60m:z8 | TRITOP | A | 0.00493 | 0.00602 (0.00493-0.00766) | +0.307 |
| ETH | 60m:z8 | TRITOP | B | 0.00548 | 0.00548 (0-0.00822) |  |
| SOL | 15m:K | LMW.BBOT | A | 0.48 | 0.813 (0.79-0.833) | -0.039 |
| SOL | 15m:K | LMW.BBOT | B | 0.575 | 0.827 (0.778-0.858) | +0.006 |
| SOL | 15m:K | LMW.BTOP | A | 0.502 | 0.817 (0.813-0.841) | -0.033 |
| SOL | 15m:K | LMW.BTOP | B | 0.603 | 0.847 (0.748-0.882) | -0.019 |
| SOL | 15m:K | LMW.DBOT | A | 0.261 | 0.245 (0.231-0.267) | -0.025 |
| SOL | 15m:K | LMW.DBOT | B | 0.343 | 0.364 (0.296-0.37) | -0.036 |
| SOL | 15m:K | LMW.DTOP | A | 0.246 | 0.265 (0.263-0.272) | -0.001 |
| SOL | 15m:K | LMW.DTOP | B | 0.375 | 0.389 (0.348-0.425) | -0.050 |
| SOL | 15m:K | LMW.HS | A | 4.56 | 4.59 (4.58-4.6) | -0.033 |
| SOL | 15m:K | LMW.HS | B | 5.04 | 4.81 (4.81-4.96) | -0.029 |
| SOL | 15m:K | LMW.HS.SWZ | A | 0.0243 | 0.025 (0.0231-0.0287) | +0.030 |
| SOL | 15m:K | LMW.HS.SWZ | B | 0.00274 | 0.00548 (0.00548-0.0137) | -1.000 |
| SOL | 15m:K | LMW.IHS | A | 4.66 | 4.59 (4.58-4.61) | -0.032 |
| SOL | 15m:K | LMW.IHS | B | 5.04 | 4.87 (4.76-4.9) | -0.037 |
| SOL | 15m:K | LMW.IHS.SWZ | A | 0.0212 | 0.0218 (0.0212-0.0324) | -0.073 |
| SOL | 15m:K | LMW.IHS.SWZ | B | 0.00822 | 0.00548 (0.00548-0.0137) | +0.000 |
| SOL | 15m:K | LMW.RBOT | A | 12.8 | 12.3 (12.3-12.4) | -0.002 |
| SOL | 15m:K | LMW.RBOT | B | 16.5 | 15.5 (15.3-15.7) | +0.012 |
| SOL | 15m:K | LMW.RTOP | A | 13 | 12.3 (12.2-12.4) | -0.000 |
| SOL | 15m:K | LMW.RTOP | B | 16.8 | 15.6 (15.2-15.6) | +0.011 |
| SOL | 15m:K | LMW.TBOT | A | 1.31 | 1.01 (0.992-1.03) | -0.322 |
| SOL | 15m:K | LMW.TBOT | B | 1.24 | 0.948 (0.943-0.989) | -0.289 |
| SOL | 15m:K | LMW.TTOP | A | 1.32 | 1 (1-1.03) | -0.349 |
| SOL | 15m:K | LMW.TTOP | B | 1.21 | 0.964 (0.94-0.978) | -0.297 |
| SOL | 15m:z2 | ABCD.BEAR | A | 0.208 | 0.271 (0.255-0.273) | -0.054 |
| SOL | 15m:z2 | ABCD.BEAR | B | 0.249 | 0.277 (0.236-0.293) | +0.026 |
| SOL | 15m:z2 | ABCD.BULL | A | 0.226 | 0.254 (0.246-0.265) | -0.030 |
| SOL | 15m:z2 | ABCD.BULL | B | 0.241 | 0.238 (0.219-0.274) | -0.017 |
| SOL | 15m:z2 | ASCTRI | A | 0.519 | 0.55 (0.528-0.558) | +0.009 |
| SOL | 15m:z2 | ASCTRI | B | 0.54 | 0.603 (0.562-0.638) | +0.017 |
| SOL | 15m:z2 | BEARFLAG | A | 0.371 | 0.355 (0.348-0.366) | +0.023 |
| SOL | 15m:z2 | BEARFLAG | B | 0.373 | 0.334 (0.321-0.375) | +0.058 |
| SOL | 15m:z2 | BEARPEN | A | 0.165 | 0.119 (0.112-0.13) | -0.031 |
| SOL | 15m:z2 | BEARPEN | B | 0.145 | 0.148 (0.123-0.151) | +0.087 |
| SOL | 15m:z2 | BROADBOT | A | 0.0817 | 0.104 (0.0942-0.106) | -0.152 |
| SOL | 15m:z2 | BROADBOT | B | 0.0795 | 0.0932 (0.0877-0.0986) | -0.068 |
| SOL | 15m:z2 | BROADTOP | A | 0.111 | 0.117 (0.0967-0.119) | +0.030 |
| SOL | 15m:z2 | BROADTOP | B | 0.0822 | 0.0986 (0.0849-0.121) | -0.186 |
| SOL | 15m:z2 | BULLFLAG | A | 0.382 | 0.331 (0.325-0.333) | +0.007 |
| SOL | 15m:z2 | BULLFLAG | B | 0.362 | 0.343 (0.332-0.367) | -0.041 |
| SOL | 15m:z2 | BULLPEN | A | 0.153 | 0.117 (0.115-0.128) | +0.009 |
| SOL | 15m:z2 | BULLPEN | B | 0.156 | 0.137 (0.121-0.142) | -0.035 |
| SOL | 15m:z2 | CUP | A | 0.0711 | 0.0836 (0.078-0.0842) | +0.057 |
| SOL | 15m:z2 | CUP | B | 0.0575 | 0.0904 (0.0822-0.0959) | -0.016 |
| SOL | 15m:z2 | DBOT | A | 1.61 | 1.63 (1.61-1.68) | -0.017 |
| SOL | 15m:z2 | DBOT | B | 1.62 | 1.59 (1.59-1.66) | +0.001 |
| SOL | 15m:z2 | DESCTRI | A | 0.503 | 0.546 (0.526-0.576) | +0.012 |
| SOL | 15m:z2 | DESCTRI | B | 0.482 | 0.504 (0.474-0.507) | +0.014 |
| SOL | 15m:z2 | DTOP | A | 1.65 | 1.61 (1.61-1.64) | +0.002 |
| SOL | 15m:z2 | DTOP | B | 1.62 | 1.67 (1.65-1.73) | -0.009 |
| SOL | 15m:z2 | FALWEDGE | A | 0.81 | 0.755 (0.739-0.8) | +0.023 |
| SOL | 15m:z2 | FALWEDGE | B | 0.789 | 0.745 (0.682-0.849) | -0.003 |
| SOL | 15m:z2 | HARM.BEAR | A | 0.0349 | 0.0343 (0.0312-0.0399) | +0.101 |
| SOL | 15m:z2 | HARM.BEAR | B | 0.0466 | 0.0274 (0.0219-0.0438) | -0.069 |
| SOL | 15m:z2 | HARM.BULL | A | 0.0331 | 0.0356 (0.0337-0.0393) | +0.030 |
| SOL | 15m:z2 | HARM.BULL | B | 0.0438 | 0.0466 (0.0329-0.063) | +0.164 |
| SOL | 15m:z2 | HS | A | 0.288 | 0.271 (0.27-0.294) | +0.029 |
| SOL | 15m:z2 | HS | B | 0.258 | 0.282 (0.26-0.304) | +0.064 |
| SOL | 15m:z2 | IHS | A | 0.284 | 0.279 (0.271-0.285) | -0.001 |
| SOL | 15m:z2 | IHS | B | 0.236 | 0.252 (0.252-0.31) | +0.095 |
| SOL | 15m:z2 | INVCUP | A | 0.0742 | 0.0911 (0.083-0.0917) | +0.040 |
| SOL | 15m:z2 | INVCUP | B | 0.0904 | 0.0603 (0.0548-0.0795) | -0.073 |
| SOL | 15m:z2 | RECT | A | 0.134 | 0.165 (0.15-0.171) | +0.019 |
| SOL | 15m:z2 | RECT | B | 0.14 | 0.159 (0.153-0.173) | +0.025 |
| SOL | 15m:z2 | RISWEDGE | A | 0.805 | 0.79 (0.785-0.797) | +0.036 |
| SOL | 15m:z2 | RISWEDGE | B | 0.838 | 0.781 (0.781-0.844) | -0.062 |
| SOL | 15m:z2 | ROUNDBOT | A | 0.166 | 0.238 (0.223-0.242) | -0.004 |
| SOL | 15m:z2 | ROUNDBOT | B | 0.162 | 0.247 (0.225-0.301) | -0.140 |
| SOL | 15m:z2 | ROUNDTOP | A | 0.175 | 0.192 (0.188-0.214) | +0.096 |
| SOL | 15m:z2 | ROUNDTOP | B | 0.269 | 0.222 (0.2-0.227) | +0.131 |
| SOL | 15m:z2 | SYMTRI | A | 0.687 | 0.63 (0.626-0.636) | +0.066 |
| SOL | 15m:z2 | SYMTRI | B | 0.622 | 0.638 (0.638-0.693) | +0.026 |
| SOL | 15m:z2 | TRIBOT | A | 0.2 | 0.253 (0.236-0.254) | +0.008 |
| SOL | 15m:z2 | TRIBOT | B | 0.175 | 0.236 (0.2-0.238) | +0.072 |
| SOL | 15m:z2 | TRITOP | A | 0.235 | 0.244 (0.231-0.281) | +0.063 |
| SOL | 15m:z2 | TRITOP | B | 0.252 | 0.266 (0.247-0.277) | -0.071 |
| SOL | 15m:z4 | ABCD.BEAR | A | 0.0705 | 0.0861 (0.0855-0.0867) | -0.005 |
| SOL | 15m:z4 | ABCD.BEAR | B | 0.0712 | 0.0904 (0.0712-0.101) | +0.121 |
| SOL | 15m:z4 | ABCD.BULL | A | 0.0736 | 0.0817 (0.0786-0.093) | -0.021 |
| SOL | 15m:z4 | ABCD.BULL | B | 0.0822 | 0.074 (0.074-0.0877) | +0.017 |
| SOL | 15m:z4 | ASCTRI | A | 0.182 | 0.202 (0.192-0.206) | +0.056 |
| SOL | 15m:z4 | ASCTRI | B | 0.206 | 0.23 (0.17-0.233) | +0.095 |
| SOL | 15m:z4 | BEARFLAG | A | 0.0331 | 0.0474 (0.0399-0.0505) | +0.207 |
| SOL | 15m:z4 | BEARFLAG | B | 0.0521 | 0.063 (0.0493-0.0767) | -0.010 |
| SOL | 15m:z4 | BEARPEN | A | 0.0175 | 0.0168 (0.0168-0.0168) | -0.041 |
| SOL | 15m:z4 | BEARPEN | B | 0.0356 | 0.0219 (0.0164-0.0219) | -0.047 |
| SOL | 15m:z4 | BROADBOT | A | 0.0256 | 0.0324 (0.0287-0.0331) | -0.150 |
| SOL | 15m:z4 | BROADBOT | B | 0.0247 | 0.0219 (0.0192-0.0493) | +0.051 |
| SOL | 15m:z4 | BROADTOP | A | 0.0299 | 0.0349 (0.0268-0.0393) | +0.108 |
| SOL | 15m:z4 | BROADTOP | B | 0.0274 | 0.0219 (0.0192-0.0438) | -0.209 |
| SOL | 15m:z4 | BULLFLAG | A | 0.0537 | 0.0424 (0.0393-0.0424) | -0.067 |
| SOL | 15m:z4 | BULLFLAG | B | 0.0603 | 0.0575 (0.0548-0.0658) | +0.027 |
| SOL | 15m:z4 | BULLPEN | A | 0.02 | 0.0162 (0.0162-0.0225) | +0.190 |
| SOL | 15m:z4 | BULLPEN | B | 0.0301 | 0.0219 (0.0219-0.0274) | -0.031 |
| SOL | 15m:z4 | CUP | A | 0.0299 | 0.0337 (0.0324-0.0387) | +0.050 |
| SOL | 15m:z4 | CUP | B | 0.0356 | 0.0301 (0.0247-0.0329) | -0.340 |
| SOL | 15m:z4 | DBOT | A | 0.639 | 0.649 (0.639-0.655) | +0.025 |
| SOL | 15m:z4 | DBOT | B | 0.608 | 0.669 (0.647-0.71) | -0.018 |
| SOL | 15m:z4 | DESCTRI | A | 0.184 | 0.187 (0.186-0.204) | +0.077 |
| SOL | 15m:z4 | DESCTRI | B | 0.137 | 0.195 (0.153-0.195) | -0.066 |
| SOL | 15m:z4 | DTOP | A | 0.64 | 0.652 (0.649-0.672) | +0.017 |
| SOL | 15m:z4 | DTOP | B | 0.611 | 0.663 (0.652-0.723) | -0.031 |
| SOL | 15m:z4 | FALWEDGE | A | 0.27 | 0.27 (0.251-0.276) | +0.038 |
| SOL | 15m:z4 | FALWEDGE | B | 0.296 | 0.271 (0.255-0.304) | +0.033 |
| SOL | 15m:z4 | HARM.BEAR | A | 0.0137 | 0.015 (0.0131-0.0162) | -0.003 |
| SOL | 15m:z4 | HARM.BEAR | B | 0.0164 | 0.00822 (0.00822-0.011) | -0.058 |
| SOL | 15m:z4 | HARM.BULL | A | 0.0168 | 0.0156 (0.0125-0.0168) | -0.037 |
| SOL | 15m:z4 | HARM.BULL | B | 0.0219 | 0.0164 (0.011-0.0247) | +0.269 |
| SOL | 15m:z4 | HS | A | 0.0979 | 0.0998 (0.0892-0.101) | +0.123 |
| SOL | 15m:z4 | HS | B | 0.107 | 0.107 (0.101-0.126) | +0.016 |
| SOL | 15m:z4 | IHS | A | 0.101 | 0.0817 (0.0811-0.0923) | +0.068 |
| SOL | 15m:z4 | IHS | B | 0.104 | 0.0795 (0.063-0.0959) | +0.017 |
| SOL | 15m:z4 | INVCUP | A | 0.0256 | 0.0393 (0.0356-0.0406) | -0.014 |
| SOL | 15m:z4 | INVCUP | B | 0.0493 | 0.0356 (0.0329-0.0411) | -0.088 |
| SOL | 15m:z4 | RECT | A | 0.0368 | 0.0605 (0.0499-0.0699) | +0.020 |
| SOL | 15m:z4 | RECT | B | 0.0384 | 0.0795 (0.0603-0.0795) | +0.221 |
| SOL | 15m:z4 | RISWEDGE | A | 0.261 | 0.263 (0.251-0.265) | +0.036 |
| SOL | 15m:z4 | RISWEDGE | B | 0.282 | 0.29 (0.277-0.301) | +0.003 |
| SOL | 15m:z4 | ROUNDBOT | A | 0.124 | 0.174 (0.171-0.183) | +0.138 |
| SOL | 15m:z4 | ROUNDBOT | B | 0.197 | 0.195 (0.184-0.2) | +0.095 |
| SOL | 15m:z4 | ROUNDTOP | A | 0.132 | 0.15 (0.143-0.156) | -0.147 |
| SOL | 15m:z4 | ROUNDTOP | B | 0.151 | 0.181 (0.175-0.186) | +0.401 |
| SOL | 15m:z4 | SYMTRI | A | 0.264 | 0.241 (0.241-0.255) | +0.084 |
| SOL | 15m:z4 | SYMTRI | B | 0.26 | 0.244 (0.241-0.258) | +0.133 |
| SOL | 15m:z4 | TRIBOT | A | 0.0605 | 0.0954 (0.0761-0.0967) | +0.062 |
| SOL | 15m:z4 | TRIBOT | B | 0.0493 | 0.0767 (0.0767-0.0904) | -0.321 |
| SOL | 15m:z4 | TRITOP | A | 0.073 | 0.0873 (0.0861-0.0967) | +0.026 |
| SOL | 15m:z4 | TRITOP | B | 0.0822 | 0.0849 (0.0795-0.0932) | +0.070 |
| SOL | 15m:z8 | ABCD.BEAR | A | 0.0324 | 0.0287 (0.0268-0.0306) | -0.018 |
| SOL | 15m:z8 | ABCD.BEAR | B | 0.0411 | 0.0274 (0.0219-0.0411) | -0.146 |
| SOL | 15m:z8 | ABCD.BULL | A | 0.0237 | 0.0231 (0.0225-0.025) | -0.035 |
| SOL | 15m:z8 | ABCD.BULL | B | 0.0329 | 0.0192 (0.0192-0.0274) | +0.159 |
| SOL | 15m:z8 | ASCTRI | A | 0.053 | 0.0555 (0.0524-0.0574) | +0.008 |
| SOL | 15m:z8 | ASCTRI | B | 0.0603 | 0.063 (0.0493-0.107) | +0.306 |
| SOL | 15m:z8 | BEARFLAG | A | 0 | 0.00312 (0.00125-0.00374) |  |
| SOL | 15m:z8 | BEARFLAG | B | 0.00274 | 0.00274 (0.00274-0.00822) | +0.941 |
| SOL | 15m:z8 | BEARPEN | A | 0.000624 | 0 (0-0) | -0.164 |
| SOL | 15m:z8 | BEARPEN | B | 0 | 0.00274 (0.00274-0.00274) |  |
| SOL | 15m:z8 | BROADBOT | A | 0.00624 | 0.00749 (0.00749-0.00936) | +0.469 |
| SOL | 15m:z8 | BROADBOT | B | 0.00822 | 0.00822 (0.00274-0.00822) | +0.429 |
| SOL | 15m:z8 | BROADTOP | A | 0.00686 | 0.00624 (0.00437-0.00811) | -0.557 |
| SOL | 15m:z8 | BROADTOP | B | 0.011 | 0.00548 (0.00548-0.00822) |  |
| SOL | 15m:z8 | BULLFLAG | A | 0.00125 | 0.00125 (0-0.00312) |  |
| SOL | 15m:z8 | BULLFLAG | B | 0.011 | 0.00274 (0-0.00548) | -0.081 |
| SOL | 15m:z8 | BULLPEN | A | 0 | 0.00125 (0-0.00125) |  |
| SOL | 15m:z8 | BULLPEN | B | 0.00274 | 0 (0-0.00274) | -0.077 |
| SOL | 15m:z8 | CUP | A | 0.00374 | 0.00936 (0.00686-0.0106) | +0.694 |
| SOL | 15m:z8 | CUP | B | 0.00548 | 0.0219 (0.0137-0.0274) | +0.173 |
| SOL | 15m:z8 | DBOT | A | 0.181 | 0.197 (0.189-0.2) | +0.032 |
| SOL | 15m:z8 | DBOT | B | 0.225 | 0.2 (0.192-0.208) | +0.039 |
| SOL | 15m:z8 | DESCTRI | A | 0.0586 | 0.0636 (0.058-0.0661) | +0.102 |
| SOL | 15m:z8 | DESCTRI | B | 0.0658 | 0.0603 (0.0548-0.063) | +0.189 |
| SOL | 15m:z8 | DTOP | A | 0.185 | 0.185 (0.185-0.19) | +0.023 |
| SOL | 15m:z8 | DTOP | B | 0.195 | 0.203 (0.197-0.219) | +0.023 |
| SOL | 15m:z8 | FALWEDGE | A | 0.0805 | 0.0873 (0.0786-0.0911) | +0.091 |
| SOL | 15m:z8 | FALWEDGE | B | 0.0685 | 0.0877 (0.0658-0.101) | +0.145 |
| SOL | 15m:z8 | HARM.BEAR | A | 0.00499 | 0.00312 (0.00312-0.00998) | -0.100 |
| SOL | 15m:z8 | HARM.BEAR | B | 0.00822 | 0.00274 (0.00274-0.00548) | -0.155 |
| SOL | 15m:z8 | HARM.BULL | A | 0.00374 | 0.00312 (0.00187-0.00374) | -0.311 |
| SOL | 15m:z8 | HARM.BULL | B | 0.00548 | 0.00274 (0-0.00548) | +0.533 |
| SOL | 15m:z8 | HS | A | 0.0287 | 0.0299 (0.0256-0.0368) | +0.128 |
| SOL | 15m:z8 | HS | B | 0.0438 | 0.0301 (0.0247-0.0301) | +0.115 |
| SOL | 15m:z8 | IHS | A | 0.0262 | 0.0256 (0.0237-0.0274) | +0.121 |
| SOL | 15m:z8 | IHS | B | 0.0274 | 0.0329 (0.0329-0.0329) | +0.396 |
| SOL | 15m:z8 | INVCUP | A | 0.00936 | 0.0106 (0.00873-0.015) | -0.046 |
| SOL | 15m:z8 | INVCUP | B | 0.0219 | 0.00822 (0.00548-0.0164) | -0.059 |
| SOL | 15m:z8 | RECT | A | 0.0112 | 0.0143 (0.0143-0.0193) | -0.109 |
| SOL | 15m:z8 | RECT | B | 0.0164 | 0.0247 (0.0219-0.0247) | +0.459 |
| SOL | 15m:z8 | RISWEDGE | A | 0.068 | 0.0655 (0.0605-0.0692) | +0.052 |
| SOL | 15m:z8 | RISWEDGE | B | 0.0986 | 0.0849 (0.074-0.115) | +0.057 |
| SOL | 15m:z8 | ROUNDBOT | A | 0.0374 | 0.0437 (0.043-0.0518) | +0.249 |
| SOL | 15m:z8 | ROUNDBOT | B | 0.0575 | 0.0466 (0.0438-0.0521) | +0.381 |
| SOL | 15m:z8 | ROUNDTOP | A | 0.043 | 0.0399 (0.0337-0.0418) | -0.186 |
| SOL | 15m:z8 | ROUNDTOP | B | 0.0466 | 0.0411 (0.0384-0.063) | -0.338 |
| SOL | 15m:z8 | SYMTRI | A | 0.102 | 0.0792 (0.0661-0.0811) | +0.093 |
| SOL | 15m:z8 | SYMTRI | B | 0.118 | 0.0658 (0.0548-0.0795) | +0.107 |
| SOL | 15m:z8 | TRIBOT | A | 0.0206 | 0.0262 (0.025-0.0281) | +0.122 |
| SOL | 15m:z8 | TRIBOT | B | 0.0164 | 0.0192 (0.0164-0.0219) | -0.061 |
| SOL | 15m:z8 | TRITOP | A | 0.0162 | 0.0243 (0.0237-0.0256) | -0.035 |
| SOL | 15m:z8 | TRITOP | B | 0.0356 | 0.0247 (0.0219-0.0301) | -0.056 |
| SOL | 240m:K | LMW.BBOT | A | 0.0268 | 0.0437 (0.0399-0.0455) | -0.182 |
| SOL | 240m:K | LMW.BBOT | B | 0.0438 | 0.0493 (0.0356-0.0521) | +0.059 |
| SOL | 240m:K | LMW.BTOP | A | 0.0299 | 0.0399 (0.0374-0.0449) | -0.001 |
| SOL | 240m:K | LMW.BTOP | B | 0.0548 | 0.0548 (0.0411-0.0575) | -0.039 |
| SOL | 240m:K | LMW.DBOT | A | 0.00312 | 0.0025 (0.000624-0.00437) | +0.449 |
| SOL | 240m:K | LMW.DBOT | B | 0.00548 | 0.00274 (0-0.00274) | +0.475 |
| SOL | 240m:K | LMW.DTOP | A | 0.00312 | 0.00374 (0.00125-0.00499) | +0.127 |
| SOL | 240m:K | LMW.DTOP | B | 0.00822 | 0.00274 (0-0.00274) |  |
| SOL | 240m:K | LMW.HS | A | 0.127 | 0.126 (0.115-0.128) | -0.011 |
| SOL | 240m:K | LMW.HS | B | 0.173 | 0.189 (0.178-0.214) | -0.056 |
| SOL | 240m:K | LMW.HS.SWZ | A | 0.00873 | 0.00374 (0.00312-0.00499) | -0.140 |
| SOL | 240m:K | LMW.HS.SWZ | B | 0.011 | 0.011 (0-0.0137) | -0.310 |
| SOL | 240m:K | LMW.IHS | A | 0.141 | 0.122 (0.117-0.136) | -0.021 |
| SOL | 240m:K | LMW.IHS | B | 0.164 | 0.17 (0.17-0.175) | +0.048 |
| SOL | 240m:K | LMW.IHS.SWZ | A | 0.0025 | 0.00187 (0.00187-0.00437) | -0.039 |
| SOL | 240m:K | LMW.IHS.SWZ | B | 0.00822 | 0.011 (0.00274-0.0137) | -0.064 |
| SOL | 240m:K | LMW.RBOT | A | 0.107 | 0.0886 (0.0873-0.0992) | -0.029 |
| SOL | 240m:K | LMW.RBOT | B | 0.14 | 0.164 (0.156-0.181) | +0.046 |
| SOL | 240m:K | LMW.RTOP | A | 0.11 | 0.0998 (0.0855-0.107) | -0.010 |
| SOL | 240m:K | LMW.RTOP | B | 0.17 | 0.162 (0.142-0.184) | -0.014 |
| SOL | 240m:K | LMW.TBOT | A | 0.0742 | 0.0555 (0.0493-0.0599) | -0.305 |
| SOL | 240m:K | LMW.TBOT | B | 0.0959 | 0.0767 (0.0548-0.0904) | -0.311 |
| SOL | 240m:K | LMW.TTOP | A | 0.0817 | 0.053 (0.0462-0.0593) | -0.286 |
| SOL | 240m:K | LMW.TTOP | B | 0.0877 | 0.0603 (0.0493-0.0658) | -0.451 |
| SOL | 240m:z2 | ABCD.BEAR | A | 0.02 | 0.0156 (0.0125-0.0156) | +0.080 |
| SOL | 240m:z2 | ABCD.BEAR | B | 0.0274 | 0.0219 (0.0164-0.0247) | -0.114 |
| SOL | 240m:z2 | ABCD.BULL | A | 0.00811 | 0.0137 (0.0112-0.0162) | +0.037 |
| SOL | 240m:z2 | ABCD.BULL | B | 0.0219 | 0.00548 (0.00274-0.011) | +0.145 |
| SOL | 240m:z2 | ASCTRI | A | 0.025 | 0.0312 (0.0293-0.0356) | +0.030 |
| SOL | 240m:z2 | ASCTRI | B | 0.0301 | 0.0466 (0.0411-0.063) | -0.071 |
| SOL | 240m:z2 | BEARFLAG | A | 0.0125 | 0.0237 (0.02-0.0262) | +0.045 |
| SOL | 240m:z2 | BEARFLAG | B | 0.0301 | 0.0247 (0.0192-0.0301) | -0.158 |
| SOL | 240m:z2 | BEARPEN | A | 0.00561 | 0.00936 (0.00561-0.00998) | -0.098 |
| SOL | 240m:z2 | BEARPEN | B | 0.00274 | 0.011 (0.00274-0.0137) | -0.170 |
| SOL | 240m:z2 | BROADBOT | A | 0.00437 | 0.00499 (0.00499-0.00686) | +0.444 |
| SOL | 240m:z2 | BROADBOT | B | 0.00548 | 0.00822 (0.00822-0.00822) | -0.557 |
| SOL | 240m:z2 | BROADTOP | A | 0.00686 | 0.00499 (0.0025-0.00624) | +0.014 |
| SOL | 240m:z2 | BROADTOP | B | 0.00274 | 0.00822 (0.00274-0.0137) |  |
| SOL | 240m:z2 | BULLFLAG | A | 0.0193 | 0.0162 (0.0131-0.0175) | -0.102 |
| SOL | 240m:z2 | BULLFLAG | B | 0.0192 | 0.0274 (0.0247-0.0301) | -0.199 |
| SOL | 240m:z2 | BULLPEN | A | 0.0125 | 0.00686 (0.00312-0.00873) | +0.083 |
| SOL | 240m:z2 | BULLPEN | B | 0.011 | 0.011 (0.00548-0.0219) | +0.046 |
| SOL | 240m:z2 | CUP | A | 0.00374 | 0.00374 (0.00312-0.00499) | +0.469 |
| SOL | 240m:z2 | CUP | B | 0 | 0.00548 (0.00274-0.00548) |  |
| SOL | 240m:z2 | DBOT | A | 0.0867 | 0.0886 (0.0873-0.0898) | +0.057 |
| SOL | 240m:z2 | DBOT | B | 0.104 | 0.101 (0.074-0.104) | -0.047 |
| SOL | 240m:z2 | DESCTRI | A | 0.0256 | 0.0299 (0.0256-0.0331) | -0.107 |
| SOL | 240m:z2 | DESCTRI | B | 0.0411 | 0.0301 (0.0274-0.0329) | -0.144 |
| SOL | 240m:z2 | DTOP | A | 0.0861 | 0.0867 (0.083-0.0873) | +0.135 |
| SOL | 240m:z2 | DTOP | B | 0.0795 | 0.101 (0.0932-0.121) | -0.032 |
| SOL | 240m:z2 | FALWEDGE | A | 0.0374 | 0.0374 (0.0362-0.0424) | +0.002 |
| SOL | 240m:z2 | FALWEDGE | B | 0.0521 | 0.0384 (0.0247-0.0384) | +0.179 |
| SOL | 240m:z2 | HARM.BEAR | A | 0.00125 | 0.00187 (0.000624-0.00187) | -0.368 |
| SOL | 240m:z2 | HARM.BEAR | B | 0.00548 | 0.00274 (0-0.00274) |  |
| SOL | 240m:z2 | HARM.BULL | A | 0.000624 | 0.00187 (0.00187-0.00312) |  |
| SOL | 240m:z2 | HARM.BULL | B | 0.00274 | 0.00274 (0-0.00274) |  |
| SOL | 240m:z2 | HS | A | 0.0168 | 0.0168 (0.00936-0.0175) | +0.247 |
| SOL | 240m:z2 | HS | B | 0.0192 | 0.0247 (0.0219-0.0411) | -0.075 |
| SOL | 240m:z2 | IHS | A | 0.0112 | 0.0143 (0.0137-0.0187) | +0.090 |
| SOL | 240m:z2 | IHS | B | 0.00822 | 0.0164 (0.011-0.0219) | -0.437 |
| SOL | 240m:z2 | INVCUP | A | 0.00561 | 0.00374 (0.00125-0.00499) | +0.237 |
| SOL | 240m:z2 | INVCUP | B | 0.00548 | 0.00822 (0.00548-0.00822) | +0.191 |
| SOL | 240m:z2 | RECT | A | 0.00437 | 0.0119 (0.00561-0.015) | -0.210 |
| SOL | 240m:z2 | RECT | B | 0.011 | 0.0192 (0.0137-0.0247) | +0.287 |
| SOL | 240m:z2 | RISWEDGE | A | 0.0586 | 0.0462 (0.0455-0.0499) | +0.021 |
| SOL | 240m:z2 | RISWEDGE | B | 0.0384 | 0.0603 (0.0548-0.0685) | -0.133 |
| SOL | 240m:z2 | ROUNDBOT | A | 0.00998 | 0.0187 (0.0162-0.0243) | +0.046 |
| SOL | 240m:z2 | ROUNDBOT | B | 0.0164 | 0.011 (0.00274-0.0219) |  |
| SOL | 240m:z2 | ROUNDTOP | A | 0.0106 | 0.00749 (0.00624-0.00936) |  |
| SOL | 240m:z2 | ROUNDTOP | B | 0.011 | 0.011 (0.011-0.0137) | +0.662 |
| SOL | 240m:z2 | SYMTRI | A | 0.0356 | 0.0306 (0.0268-0.0331) | +0.052 |
| SOL | 240m:z2 | SYMTRI | B | 0.0548 | 0.0493 (0.0301-0.0521) | +0.160 |
| SOL | 240m:z2 | TRIBOT | A | 0.00686 | 0.0156 (0.0143-0.0168) | -0.227 |
| SOL | 240m:z2 | TRIBOT | B | 0.011 | 0.0137 (0.011-0.0219) | -0.558 |
| SOL | 240m:z2 | TRITOP | A | 0.0112 | 0.0119 (0.0119-0.0175) | -0.032 |
| SOL | 240m:z2 | TRITOP | B | 0.0164 | 0.0164 (0.0164-0.0164) | +0.364 |
| SOL | 240m:z4 | ABCD.BEAR | A | 0.00561 | 0.00499 (0.00125-0.00749) | -0.073 |
| SOL | 240m:z4 | ABCD.BEAR | B | 0.00274 | 0.00548 (0.00548-0.00822) |  |
| SOL | 240m:z4 | ABCD.BULL | A | 0.00125 | 0.00312 (0.00187-0.00561) | -0.414 |
| SOL | 240m:z4 | ABCD.BULL | B | 0.00822 | 0.00548 (0-0.00822) | +0.458 |
| SOL | 240m:z4 | ASCTRI | A | 0.00686 | 0.00873 (0.00811-0.00873) | -0.001 |
| SOL | 240m:z4 | ASCTRI | B | 0.0137 | 0.00822 (0.00548-0.0274) | +0.305 |
| SOL | 240m:z4 | BEARFLAG | A | 0.00125 | 0.00561 (0.00561-0.00686) |  |
| SOL | 240m:z4 | BEARFLAG | B | 0.00274 | 0 (0-0.00822) | -0.098 |
| SOL | 240m:z4 | BEARPEN | A | 0.00187 | 0.000624 (0.000624-0.0025) | -0.147 |
| SOL | 240m:z4 | BEARPEN | B | 0 | 0 (0-0.00274) |  |
| SOL | 240m:z4 | BROADBOT | A | 0 | 0.00125 (0.00125-0.0025) |  |
| SOL | 240m:z4 | BROADBOT | B | 0.00274 | 0.00274 (0.00274-0.00548) |  |
| SOL | 240m:z4 | BROADTOP | A | 0.00125 | 0.00187 (0.000624-0.00187) |  |
| SOL | 240m:z4 | BROADTOP | B | 0 | 0.00822 (0.00274-0.011) |  |
| SOL | 240m:z4 | BULLFLAG | A | 0.000624 | 0.00125 (0.00125-0.00187) | +0.403 |
| SOL | 240m:z4 | BULLFLAG | B | 0 | 0.00548 (0.00274-0.00822) |  |
| SOL | 240m:z4 | BULLPEN | A | 0.00312 | 0.00125 (0.000624-0.00187) | -0.154 |
| SOL | 240m:z4 | BULLPEN | B | 0.00274 | 0 (0-0.00548) | +0.788 |
| SOL | 240m:z4 | CUP | A | 0.000624 | 0.00125 (0.000624-0.00125) |  |
| SOL | 240m:z4 | CUP | B | 0.00548 | 0 (0-0) | +0.152 |
| SOL | 240m:z4 | DBOT | A | 0.0343 | 0.0349 (0.0306-0.0406) | +0.192 |
| SOL | 240m:z4 | DBOT | B | 0.0411 | 0.0493 (0.0329-0.0521) | +0.218 |
| SOL | 240m:z4 | DESCTRI | A | 0.0119 | 0.0119 (0.00811-0.0125) | -0.165 |
| SOL | 240m:z4 | DESCTRI | B | 0.0164 | 0.011 (0.00822-0.011) | -0.242 |
| SOL | 240m:z4 | DTOP | A | 0.0293 | 0.0368 (0.0293-0.0381) | -0.014 |
| SOL | 240m:z4 | DTOP | B | 0.0411 | 0.0438 (0.0438-0.0575) | +0.439 |
| SOL | 240m:z4 | FALWEDGE | A | 0.0137 | 0.0156 (0.00998-0.0162) | +0.246 |
| SOL | 240m:z4 | FALWEDGE | B | 0.0274 | 0.0137 (0.00822-0.0192) | +0.208 |
| SOL | 240m:z4 | HARM.BEAR | A | 0.00187 | 0.00125 (0-0.00125) | -0.101 |
| SOL | 240m:z4 | HARM.BEAR | B | 0 | 0 (0-0.00274) |  |
| SOL | 240m:z4 | HARM.BULL | A | 0.000624 | 0.00125 (0.000624-0.00187) | +0.614 |
| SOL | 240m:z4 | HARM.BULL | B | 0 | 0 (0-0) |  |
| SOL | 240m:z4 | HS | A | 0.00561 | 0.00437 (0.0025-0.00437) | -0.125 |
| SOL | 240m:z4 | HS | B | 0 | 0.00548 (0.00274-0.00548) |  |
| SOL | 240m:z4 | IHS | A | 0.0025 | 0.00312 (0.00187-0.00437) | +0.378 |
| SOL | 240m:z4 | IHS | B | 0.011 | 0.00274 (0.00274-0.00548) | +0.200 |
| SOL | 240m:z4 | INVCUP | A | 0.00187 | 0.00125 (0-0.00187) | +0.141 |
| SOL | 240m:z4 | INVCUP | B | 0 | 0 (0-0) |  |
| SOL | 240m:z4 | RECT | A | 0.0025 | 0.0025 (0.00187-0.00499) | -0.039 |
| SOL | 240m:z4 | RECT | B | 0 | 0 (0-0.00548) |  |
| SOL | 240m:z4 | RISWEDGE | A | 0.015 | 0.0131 (0.0112-0.0143) | +0.017 |
| SOL | 240m:z4 | RISWEDGE | B | 0.0356 | 0.0329 (0.0219-0.0384) | -0.065 |
| SOL | 240m:z4 | ROUNDBOT | A | 0.00561 | 0.0125 (0.0125-0.0137) |  |
| SOL | 240m:z4 | ROUNDBOT | B | 0.0164 | 0.0137 (0.011-0.0164) |  |
| SOL | 240m:z4 | ROUNDTOP | A | 0.00873 | 0.00811 (0.00437-0.00811) | +0.055 |
| SOL | 240m:z4 | ROUNDTOP | B | 0 | 0.011 (0.00822-0.0137) |  |
| SOL | 240m:z4 | SYMTRI | A | 0.0125 | 0.0131 (0.0106-0.0156) | +0.114 |
| SOL | 240m:z4 | SYMTRI | B | 0.0137 | 0.0164 (0.0137-0.0192) | +0.171 |
| SOL | 240m:z4 | TRIBOT | A | 0.00187 | 0.00437 (0.00374-0.00561) | +0.447 |
| SOL | 240m:z4 | TRIBOT | B | 0.00274 | 0.00548 (0.00274-0.00548) |  |
| SOL | 240m:z4 | TRITOP | A | 0.00374 | 0.00374 (0.00312-0.00561) | -0.193 |
| SOL | 240m:z4 | TRITOP | B | 0.00548 | 0.00274 (0-0.0137) | +0.437 |
| SOL | 240m:z8 | ABCD.BEAR | A | 0.00125 | 0.000624 (0.000624-0.00125) | -0.259 |
| SOL | 240m:z8 | ABCD.BEAR | B | 0.00274 | 0 (0-0.00548) | -0.266 |
| SOL | 240m:z8 | ABCD.BULL | A | 0.00125 | 0.00125 (0.000624-0.00312) | -0.171 |
| SOL | 240m:z8 | ABCD.BULL | B | 0 | 0 (0-0.00274) |  |
| SOL | 240m:z8 | ASCTRI | A | 0.000624 | 0.0025 (0-0.00312) |  |
| SOL | 240m:z8 | ASCTRI | B | 0.00274 | 0.00274 (0-0.00822) | -0.286 |
| SOL | 240m:z8 | BEARFLAG | A | 0 | 0 (0-0.000624) |  |
| SOL | 240m:z8 | BEARFLAG | B | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | BEARPEN | A | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | BEARPEN | B | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | BROADBOT | A | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | BROADBOT | B | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | BROADTOP | A | 0 | 0 (0-0.00125) |  |
| SOL | 240m:z8 | BROADTOP | B | 0 | 0 (0-0.00274) |  |
| SOL | 240m:z8 | BULLFLAG | A | 0 | 0 (0-0.000624) |  |
| SOL | 240m:z8 | BULLFLAG | B | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | BULLPEN | A | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | BULLPEN | B | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | CUP | A | 0 | 0.000624 (0.000624-0.00125) |  |
| SOL | 240m:z8 | CUP | B | 0 | 0 (0-0.00274) |  |
| SOL | 240m:z8 | DBOT | A | 0.00811 | 0.0137 (0.0131-0.0143) | +0.461 |
| SOL | 240m:z8 | DBOT | B | 0.011 | 0.0137 (0.011-0.0137) | +0.393 |
| SOL | 240m:z8 | DESCTRI | A | 0.00437 | 0.00499 (0.00499-0.00561) | +0.477 |
| SOL | 240m:z8 | DESCTRI | B | 0.00548 | 0.00548 (0.00274-0.00548) |  |
| SOL | 240m:z8 | DTOP | A | 0.00624 | 0.00998 (0.00686-0.0119) | +0.225 |
| SOL | 240m:z8 | DTOP | B | 0.011 | 0.0137 (0.011-0.0219) | +0.462 |
| SOL | 240m:z8 | FALWEDGE | A | 0.00437 | 0.00437 (0.00437-0.00561) | +0.291 |
| SOL | 240m:z8 | FALWEDGE | B | 0.0137 | 0.00274 (0-0.00548) | +0.646 |
| SOL | 240m:z8 | HARM.BEAR | A | 0.00125 | 0 (0-0.000624) | -0.164 |
| SOL | 240m:z8 | HARM.BEAR | B | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | HARM.BULL | A | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | HARM.BULL | B | 0 | 0 (0-0) |  |
| SOL | 240m:z8 | HS | A | 0.00125 | 0.00187 (0.00187-0.0025) | +0.620 |
| SOL | 240m:z8 | HS | B | 0 | 0.00274 (0-0.00548) |  |
| SOL | 240m:z8 | IHS | A | 0 | 0.00125 (0.000624-0.00125) |  |
| SOL | 240m:z8 | IHS | B | 0 | 0 (0-0.00274) |  |
| SOL | 240m:z8 | INVCUP | A | 0.000624 | 0.000624 (0-0.00125) |  |
| SOL | 240m:z8 | INVCUP | B | 0 | 0.00274 (0-0.00548) |  |
| SOL | 240m:z8 | RECT | A | 0 | 0.00125 (0.00125-0.00187) |  |
| SOL | 240m:z8 | RECT | B | 0 | 0.00274 (0-0.00548) |  |
| SOL | 240m:z8 | RISWEDGE | A | 0.000624 | 0.00187 (0.00125-0.00312) | +0.544 |
| SOL | 240m:z8 | RISWEDGE | B | 0.00822 | 0.00274 (0-0.0137) | +0.537 |
| SOL | 240m:z8 | ROUNDBOT | A | 0.00312 | 0.00312 (0.00312-0.00499) |  |
| SOL | 240m:z8 | ROUNDBOT | B | 0 | 0.00274 (0-0.00548) |  |
| SOL | 240m:z8 | ROUNDTOP | A | 0.000624 | 0.00125 (0.00125-0.0025) |  |
| SOL | 240m:z8 | ROUNDTOP | B | 0.00274 | 0.00274 (0-0.00274) |  |
| SOL | 240m:z8 | SYMTRI | A | 0.0025 | 0.00312 (0.00187-0.00437) | -0.186 |
| SOL | 240m:z8 | SYMTRI | B | 0.00548 | 0.00274 (0-0.00548) | -0.147 |
| SOL | 240m:z8 | TRIBOT | A | 0.000624 | 0.00187 (0.00125-0.00374) |  |
| SOL | 240m:z8 | TRIBOT | B | 0 | 0 (0-0.00548) |  |
| SOL | 240m:z8 | TRITOP | A | 0 | 0.00125 (0.00125-0.0025) |  |
| SOL | 240m:z8 | TRITOP | B | 0 | 0 (0-0.00274) |  |
| SOL | 5m:z2 | ABCD.BEAR | A | 0.772 | 0.794 (0.794-0.843) | +0.009 |
| SOL | 5m:z2 | ABCD.BEAR | B | 0.784 | 0.871 (0.847-0.929) | -0.022 |
| SOL | 5m:z2 | ABCD.BULL | A | 0.762 | 0.769 (0.757-0.797) | -0.033 |
| SOL | 5m:z2 | ABCD.BULL | B | 0.825 | 0.833 (0.789-0.858) | -0.003 |
| SOL | 5m:z2 | ASCTRI | A | 1.73 | 1.7 (1.68-1.74) | +0.028 |
| SOL | 5m:z2 | ASCTRI | B | 1.76 | 1.8 (1.79-1.81) | +0.002 |
| SOL | 5m:z2 | BEARFLAG | A | 0.953 | 1.02 (1.02-1.06) | +0.027 |
| SOL | 5m:z2 | BEARFLAG | B | 0.97 | 0.995 (0.893-1.07) | +0.050 |
| SOL | 5m:z2 | BEARPEN | A | 0.386 | 0.382 (0.376-0.389) | +0.054 |
| SOL | 5m:z2 | BEARPEN | B | 0.351 | 0.318 (0.269-0.403) | +0.062 |
| SOL | 5m:z2 | BROADBOT | A | 0.283 | 0.342 (0.339-0.346) | +0.032 |
| SOL | 5m:z2 | BROADBOT | B | 0.323 | 0.329 (0.329-0.406) | -0.010 |
| SOL | 5m:z2 | BROADTOP | A | 0.268 | 0.328 (0.326-0.367) | -0.001 |
| SOL | 5m:z2 | BROADTOP | B | 0.277 | 0.392 (0.367-0.406) | +0.043 |
| SOL | 5m:z2 | BULLFLAG | A | 1.07 | 1.01 (0.974-1.01) | +0.023 |
| SOL | 5m:z2 | BULLFLAG | B | 1.03 | 0.981 (0.951-0.984) | +0.069 |
| SOL | 5m:z2 | BULLPEN | A | 0.417 | 0.369 (0.369-0.371) | +0.016 |
| SOL | 5m:z2 | BULLPEN | B | 0.389 | 0.348 (0.312-0.356) | -0.025 |
| SOL | 5m:z2 | CUP | A | 0.261 | 0.265 (0.265-0.281) | +0.031 |
| SOL | 5m:z2 | CUP | B | 0.285 | 0.269 (0.263-0.269) | -0.054 |
| SOL | 5m:z2 | DBOT | A | 4.95 | 5.01 (5.01-5.01) | -0.016 |
| SOL | 5m:z2 | DBOT | B | 5.09 | 5 (4.94-5.1) | -0.024 |
| SOL | 5m:z2 | DESCTRI | A | 1.61 | 1.7 (1.66-1.72) | +0.018 |
| SOL | 5m:z2 | DESCTRI | B | 1.71 | 1.65 (1.62-1.78) | +0.045 |
| SOL | 5m:z2 | DTOP | A | 5.02 | 4.97 (4.97-5.01) | -0.009 |
| SOL | 5m:z2 | DTOP | B | 5.26 | 5.02 (4.93-5.14) | -0.016 |
| SOL | 5m:z2 | FALWEDGE | A | 2.49 | 2.45 (2.39-2.45) | +0.004 |
| SOL | 5m:z2 | FALWEDGE | B | 2.63 | 2.51 (2.44-2.53) | +0.012 |
| SOL | 5m:z2 | HARM.BEAR | A | 0.117 | 0.117 (0.117-0.12) | +0.035 |
| SOL | 5m:z2 | HARM.BEAR | B | 0.107 | 0.115 (0.11-0.159) | -0.104 |
| SOL | 5m:z2 | HARM.BULL | A | 0.122 | 0.115 (0.103-0.121) | -0.061 |
| SOL | 5m:z2 | HARM.BULL | B | 0.148 | 0.121 (0.118-0.159) | -0.011 |
| SOL | 5m:z2 | HS | A | 0.903 | 0.893 (0.891-0.91) | +0.001 |
| SOL | 5m:z2 | HS | B | 0.934 | 0.921 (0.907-0.945) | +0.054 |
| SOL | 5m:z2 | IHS | A | 0.917 | 0.884 (0.843-0.906) | +0.056 |
| SOL | 5m:z2 | IHS | B | 0.904 | 0.904 (0.849-0.962) | -0.039 |
| SOL | 5m:z2 | INVCUP | A | 0.226 | 0.277 (0.259-0.278) | +0.009 |
| SOL | 5m:z2 | INVCUP | B | 0.258 | 0.274 (0.266-0.31) | +0.082 |
| SOL | 5m:z2 | RECT | A | 0.437 | 0.519 (0.511-0.533) | -0.028 |
| SOL | 5m:z2 | RECT | B | 0.534 | 0.48 (0.436-0.559) | +0.001 |
| SOL | 5m:z2 | RISWEDGE | A | 2.49 | 2.43 (2.39-2.47) | +0.036 |
| SOL | 5m:z2 | RISWEDGE | B | 2.65 | 2.6 (2.57-2.74) | +0.017 |
| SOL | 5m:z2 | ROUNDBOT | A | 0.456 | 0.678 (0.649-0.681) | +0.074 |
| SOL | 5m:z2 | ROUNDBOT | B | 0.397 | 0.663 (0.655-0.69) | +0.308 |
| SOL | 5m:z2 | ROUNDTOP | A | 0.569 | 0.606 (0.592-0.614) | -0.038 |
| SOL | 5m:z2 | ROUNDTOP | B | 0.649 | 0.619 (0.614-0.622) | -0.004 |
| SOL | 5m:z2 | SYMTRI | A | 2.33 | 2.03 (2.01-2.03) | +0.050 |
| SOL | 5m:z2 | SYMTRI | B | 2.15 | 2.1 (2.05-2.14) | +0.037 |
| SOL | 5m:z2 | TRIBOT | A | 0.679 | 0.822 (0.809-0.826) | -0.010 |
| SOL | 5m:z2 | TRIBOT | B | 0.764 | 0.77 (0.743-0.877) | +0.007 |
| SOL | 5m:z2 | TRITOP | A | 0.71 | 0.782 (0.77-0.791) | +0.005 |
| SOL | 5m:z2 | TRITOP | B | 0.825 | 0.822 (0.8-0.825) | +0.031 |
| SOL | 5m:z4 | ABCD.BEAR | A | 0.223 | 0.288 (0.272-0.302) | -0.074 |
| SOL | 5m:z4 | ABCD.BEAR | B | 0.269 | 0.279 (0.263-0.296) | -0.036 |
| SOL | 5m:z4 | ABCD.BULL | A | 0.255 | 0.261 (0.247-0.263) | -0.059 |
| SOL | 5m:z4 | ABCD.BULL | B | 0.288 | 0.258 (0.244-0.285) | -0.066 |
| SOL | 5m:z4 | ASCTRI | A | 0.595 | 0.609 (0.6-0.631) | +0.026 |
| SOL | 5m:z4 | ASCTRI | B | 0.707 | 0.66 (0.617-0.666) | -0.038 |
| SOL | 5m:z4 | BEARFLAG | A | 0.112 | 0.152 (0.147-0.167) | -0.017 |
| SOL | 5m:z4 | BEARFLAG | B | 0.123 | 0.142 (0.14-0.145) | +0.045 |
| SOL | 5m:z4 | BEARPEN | A | 0.0524 | 0.0643 (0.0474-0.0692) | +0.029 |
| SOL | 5m:z4 | BEARPEN | B | 0.0438 | 0.0521 (0.0301-0.0658) | +0.003 |
| SOL | 5m:z4 | BROADBOT | A | 0.0842 | 0.103 (0.0923-0.115) | -0.134 |
| SOL | 5m:z4 | BROADBOT | B | 0.0877 | 0.0849 (0.0822-0.0904) | -0.256 |
| SOL | 5m:z4 | BROADTOP | A | 0.0998 | 0.102 (0.0979-0.114) | +0.003 |
| SOL | 5m:z4 | BROADTOP | B | 0.0795 | 0.0959 (0.0849-0.112) | -0.145 |
| SOL | 5m:z4 | BULLFLAG | A | 0.122 | 0.142 (0.132-0.145) | -0.048 |
| SOL | 5m:z4 | BULLFLAG | B | 0.129 | 0.137 (0.134-0.142) | +0.124 |
| SOL | 5m:z4 | BULLPEN | A | 0.0586 | 0.0561 (0.0512-0.0618) | +0.063 |
| SOL | 5m:z4 | BULLPEN | B | 0.063 | 0.0466 (0.0329-0.0603) | +0.058 |
| SOL | 5m:z4 | CUP | A | 0.0954 | 0.0967 (0.0942-0.104) | +0.054 |
| SOL | 5m:z4 | CUP | B | 0.0849 | 0.101 (0.0959-0.115) | -0.203 |
| SOL | 5m:z4 | DBOT | A | 1.98 | 2.01 (2-2.05) | -0.005 |
| SOL | 5m:z4 | DBOT | B | 2.06 | 2.07 (2.04-2.09) | +0.016 |
| SOL | 5m:z4 | DESCTRI | A | 0.596 | 0.601 (0.588-0.642) | +0.018 |
| SOL | 5m:z4 | DESCTRI | B | 0.553 | 0.611 (0.589-0.63) | +0.028 |
| SOL | 5m:z4 | DTOP | A | 2.02 | 2.02 (2.01-2.04) | -0.005 |
| SOL | 5m:z4 | DTOP | B | 2.05 | 2.15 (2.05-2.16) | -0.023 |
| SOL | 5m:z4 | FALWEDGE | A | 0.867 | 0.862 (0.84-0.9) | +0.017 |
| SOL | 5m:z4 | FALWEDGE | B | 0.855 | 0.904 (0.781-0.943) | -0.000 |
| SOL | 5m:z4 | HARM.BEAR | A | 0.0406 | 0.0487 (0.0462-0.0543) | +0.046 |
| SOL | 5m:z4 | HARM.BEAR | B | 0.0438 | 0.0356 (0.0274-0.0411) | -0.099 |
| SOL | 5m:z4 | HARM.BULL | A | 0.0474 | 0.0443 (0.0418-0.0543) | -0.014 |
| SOL | 5m:z4 | HARM.BULL | B | 0.0575 | 0.0548 (0.0411-0.0712) | +0.366 |
| SOL | 5m:z4 | HS | A | 0.309 | 0.311 (0.278-0.313) | +0.049 |
| SOL | 5m:z4 | HS | B | 0.282 | 0.279 (0.271-0.307) | -0.002 |
| SOL | 5m:z4 | IHS | A | 0.303 | 0.283 (0.276-0.284) | +0.030 |
| SOL | 5m:z4 | IHS | B | 0.277 | 0.274 (0.258-0.301) | +0.027 |
| SOL | 5m:z4 | INVCUP | A | 0.102 | 0.107 (0.102-0.109) | +0.023 |
| SOL | 5m:z4 | INVCUP | B | 0.0877 | 0.0849 (0.0822-0.118) | -0.044 |
| SOL | 5m:z4 | RECT | A | 0.155 | 0.183 (0.179-0.203) | +0.079 |
| SOL | 5m:z4 | RECT | B | 0.145 | 0.2 (0.189-0.214) | +0.237 |
| SOL | 5m:z4 | RISWEDGE | A | 0.869 | 0.832 (0.829-0.839) | +0.048 |
| SOL | 5m:z4 | RISWEDGE | B | 0.929 | 0.852 (0.836-0.855) | -0.065 |
| SOL | 5m:z4 | ROUNDBOT | A | 0.397 | 0.525 (0.524-0.54) | -0.010 |
| SOL | 5m:z4 | ROUNDBOT | B | 0.485 | 0.592 (0.507-0.619) | -0.125 |
| SOL | 5m:z4 | ROUNDTOP | A | 0.419 | 0.484 (0.48-0.49) | +0.023 |
| SOL | 5m:z4 | ROUNDTOP | B | 0.556 | 0.559 (0.521-0.589) | +0.075 |
| SOL | 5m:z4 | SYMTRI | A | 0.83 | 0.77 (0.737-0.8) | +0.056 |
| SOL | 5m:z4 | SYMTRI | B | 0.827 | 0.773 (0.764-0.836) | +0.043 |
| SOL | 5m:z4 | TRIBOT | A | 0.218 | 0.282 (0.275-0.289) | +0.038 |
| SOL | 5m:z4 | TRIBOT | B | 0.197 | 0.255 (0.252-0.269) | +0.038 |
| SOL | 5m:z4 | TRITOP | A | 0.253 | 0.281 (0.252-0.294) | +0.020 |
| SOL | 5m:z4 | TRITOP | B | 0.266 | 0.282 (0.255-0.312) | -0.051 |
| SOL | 5m:z8 | ABCD.BEAR | A | 0.0774 | 0.0867 (0.0823-0.0873) | +0.017 |
| SOL | 5m:z8 | ABCD.BEAR | B | 0.0685 | 0.0986 (0.0959-0.101) | +0.084 |
| SOL | 5m:z8 | ABCD.BULL | A | 0.0786 | 0.0817 (0.0811-0.0873) | -0.119 |
| SOL | 5m:z8 | ABCD.BULL | B | 0.063 | 0.0877 (0.0767-0.101) | +0.047 |
| SOL | 5m:z8 | ASCTRI | A | 0.187 | 0.179 (0.166-0.18) | +0.031 |
| SOL | 5m:z8 | ASCTRI | B | 0.23 | 0.189 (0.142-0.197) | +0.123 |
| SOL | 5m:z8 | BEARFLAG | A | 0.0025 | 0.00561 (0.00312-0.00998) | -0.109 |
| SOL | 5m:z8 | BEARFLAG | B | 0.00822 | 0.00548 (0.00548-0.011) | -0.104 |
| SOL | 5m:z8 | BEARPEN | A | 0.0025 | 0.0025 (0.000624-0.00312) | -0.091 |
| SOL | 5m:z8 | BEARPEN | B | 0.00274 | 0.00274 (0.00274-0.00274) | -0.104 |
| SOL | 5m:z8 | BROADBOT | A | 0.015 | 0.0225 (0.0206-0.0274) | +0.152 |
| SOL | 5m:z8 | BROADBOT | B | 0.0164 | 0.0192 (0.0137-0.0466) | -0.509 |
| SOL | 5m:z8 | BROADTOP | A | 0.02 | 0.025 (0.0193-0.0268) | +0.125 |
| SOL | 5m:z8 | BROADTOP | B | 0.0329 | 0.0192 (0.0192-0.0247) | +0.476 |
| SOL | 5m:z8 | BULLFLAG | A | 0.00312 | 0.00749 (0.0025-0.00998) | +0.083 |
| SOL | 5m:z8 | BULLFLAG | B | 0.00548 | 0.00822 (0.00548-0.0164) |  |
| SOL | 5m:z8 | BULLPEN | A | 0.00187 | 0.00312 (0.00187-0.00374) | +0.237 |
| SOL | 5m:z8 | BULLPEN | B | 0.00274 | 0.00548 (0.00274-0.00822) | -0.093 |
| SOL | 5m:z8 | CUP | A | 0.0274 | 0.0324 (0.0274-0.0343) | +0.032 |
| SOL | 5m:z8 | CUP | B | 0.0658 | 0.0274 (0.0247-0.0329) | -0.141 |
| SOL | 5m:z8 | DBOT | A | 0.601 | 0.603 (0.583-0.613) | +0.036 |
| SOL | 5m:z8 | DBOT | B | 0.6 | 0.63 (0.627-0.641) | -0.015 |
| SOL | 5m:z8 | DESCTRI | A | 0.19 | 0.185 (0.182-0.203) | +0.032 |
| SOL | 5m:z8 | DESCTRI | B | 0.156 | 0.173 (0.173-0.2) | -0.021 |
| SOL | 5m:z8 | DTOP | A | 0.599 | 0.592 (0.587-0.606) | +0.009 |
| SOL | 5m:z8 | DTOP | B | 0.617 | 0.641 (0.603-0.671) | +0.014 |
| SOL | 5m:z8 | FALWEDGE | A | 0.23 | 0.26 (0.24-0.284) | +0.012 |
| SOL | 5m:z8 | FALWEDGE | B | 0.238 | 0.266 (0.263-0.279) | +0.017 |
| SOL | 5m:z8 | HARM.BEAR | A | 0.0193 | 0.015 (0.0137-0.0156) | +0.097 |
| SOL | 5m:z8 | HARM.BEAR | B | 0.011 | 0.011 (0.00548-0.0164) | -0.373 |
| SOL | 5m:z8 | HARM.BULL | A | 0.0137 | 0.0112 (0.00998-0.0156) | -0.027 |
| SOL | 5m:z8 | HARM.BULL | B | 0.0274 | 0.0219 (0.0164-0.0247) | +0.004 |
| SOL | 5m:z8 | HS | A | 0.0948 | 0.0923 (0.088-0.106) | +0.012 |
| SOL | 5m:z8 | HS | B | 0.0932 | 0.11 (0.0959-0.123) | -0.041 |
| SOL | 5m:z8 | IHS | A | 0.102 | 0.0805 (0.0767-0.0842) | -0.017 |
| SOL | 5m:z8 | IHS | B | 0.118 | 0.0795 (0.0685-0.0849) | +0.118 |
| SOL | 5m:z8 | INVCUP | A | 0.0337 | 0.0424 (0.0424-0.0493) | -0.113 |
| SOL | 5m:z8 | INVCUP | B | 0.0247 | 0.0384 (0.0219-0.0438) | +0.072 |
| SOL | 5m:z8 | RECT | A | 0.0324 | 0.0537 (0.043-0.0655) | -0.019 |
| SOL | 5m:z8 | RECT | B | 0.0521 | 0.0603 (0.0329-0.0795) | -0.177 |
| SOL | 5m:z8 | RISWEDGE | A | 0.23 | 0.233 (0.227-0.238) | +0.041 |
| SOL | 5m:z8 | RISWEDGE | B | 0.266 | 0.26 (0.222-0.293) | +0.079 |
| SOL | 5m:z8 | ROUNDBOT | A | 0.119 | 0.155 (0.142-0.155) | +0.047 |
| SOL | 5m:z8 | ROUNDBOT | B | 0.195 | 0.156 (0.148-0.167) | -0.041 |
| SOL | 5m:z8 | ROUNDTOP | A | 0.119 | 0.124 (0.124-0.134) | +0.215 |
| SOL | 5m:z8 | ROUNDTOP | B | 0.153 | 0.173 (0.137-0.186) | -0.065 |
| SOL | 5m:z8 | SYMTRI | A | 0.299 | 0.243 (0.239-0.248) | +0.090 |
| SOL | 5m:z8 | SYMTRI | B | 0.238 | 0.244 (0.241-0.252) | +0.140 |
| SOL | 5m:z8 | TRIBOT | A | 0.0493 | 0.0867 (0.0705-0.0911) | +0.033 |
| SOL | 5m:z8 | TRIBOT | B | 0.0575 | 0.0795 (0.0712-0.0822) | -0.075 |
| SOL | 5m:z8 | TRITOP | A | 0.0699 | 0.0699 (0.0668-0.0805) | +0.072 |
| SOL | 5m:z8 | TRITOP | B | 0.101 | 0.0849 (0.0603-0.0849) | +0.212 |
| SOL | 60m:K | LMW.BBOT | A | 0.138 | 0.219 (0.192-0.225) | +0.012 |
| SOL | 60m:K | LMW.BBOT | B | 0.175 | 0.216 (0.2-0.236) | -0.044 |
| SOL | 60m:K | LMW.BTOP | A | 0.132 | 0.204 (0.187-0.231) | -0.017 |
| SOL | 60m:K | LMW.BTOP | B | 0.203 | 0.258 (0.197-0.274) | +0.059 |
| SOL | 60m:K | LMW.DBOT | A | 0.0225 | 0.0237 (0.0218-0.0274) | -0.052 |
| SOL | 60m:K | LMW.DBOT | B | 0.0384 | 0.0329 (0.0274-0.0411) | +0.133 |
| SOL | 60m:K | LMW.DTOP | A | 0.0225 | 0.0262 (0.0256-0.0268) | +0.015 |
| SOL | 60m:K | LMW.DTOP | B | 0.0493 | 0.0274 (0.0219-0.0411) | +0.106 |
| SOL | 60m:K | LMW.HS | A | 0.923 | 0.88 (0.866-0.9) | +0.001 |
| SOL | 60m:K | LMW.HS | B | 1.09 | 1.05 (1.04-1.13) | -0.052 |
| SOL | 60m:K | LMW.HS.SWZ | A | 0.02 | 0.0175 (0.015-0.0181) | -0.024 |
| SOL | 60m:K | LMW.HS.SWZ | B | 0.011 | 0.0137 (0.011-0.0192) | +0.000 |
| SOL | 60m:K | LMW.IHS | A | 0.931 | 0.888 (0.881-0.912) | -0.035 |
| SOL | 60m:K | LMW.IHS | B | 1.12 | 1.08 (1.03-1.13) | -0.035 |
| SOL | 60m:K | LMW.IHS.SWZ | A | 0.02 | 0.0212 (0.0181-0.0231) | -0.042 |
| SOL | 60m:K | LMW.IHS.SWZ | B | 0.00822 | 0.0137 (0.00274-0.0164) | -0.169 |
| SOL | 60m:K | LMW.RBOT | A | 1.6 | 1.45 (1.4-1.47) | -0.016 |
| SOL | 60m:K | LMW.RBOT | B | 2.24 | 2.16 (2.03-2.28) | +0.007 |
| SOL | 60m:K | LMW.RTOP | A | 1.61 | 1.44 (1.41-1.46) | +0.001 |
| SOL | 60m:K | LMW.RTOP | B | 2.32 | 2.2 (2.01-2.25) | -0.001 |
| SOL | 60m:K | LMW.TBOT | A | 0.354 | 0.23 (0.23-0.28) | -0.368 |
| SOL | 60m:K | LMW.TBOT | B | 0.329 | 0.255 (0.244-0.274) | -0.295 |
| SOL | 60m:K | LMW.TTOP | A | 0.372 | 0.258 (0.236-0.258) | -0.345 |
| SOL | 60m:K | LMW.TTOP | B | 0.312 | 0.258 (0.233-0.279) | -0.307 |
| SOL | 60m:z2 | ABCD.BEAR | A | 0.0574 | 0.0605 (0.0549-0.0674) | +0.024 |
| SOL | 60m:z2 | ABCD.BEAR | B | 0.0493 | 0.0685 (0.0548-0.074) | -0.068 |
| SOL | 60m:z2 | ABCD.BULL | A | 0.0462 | 0.0561 (0.0505-0.0611) | +0.030 |
| SOL | 60m:z2 | ABCD.BULL | B | 0.063 | 0.0685 (0.0575-0.0767) | -0.031 |
| SOL | 60m:z2 | ASCTRI | A | 0.115 | 0.141 (0.132-0.153) | +0.023 |
| SOL | 60m:z2 | ASCTRI | B | 0.175 | 0.156 (0.115-0.156) | -0.003 |
| SOL | 60m:z2 | BEARFLAG | A | 0.0917 | 0.0799 (0.078-0.0855) | +0.026 |
| SOL | 60m:z2 | BEARFLAG | B | 0.11 | 0.107 (0.0932-0.121) | -0.109 |
| SOL | 60m:z2 | BEARPEN | A | 0.0443 | 0.0293 (0.0287-0.0306) | +0.056 |
| SOL | 60m:z2 | BEARPEN | B | 0.0603 | 0.0411 (0.0329-0.0521) | -0.068 |
| SOL | 60m:z2 | BROADBOT | A | 0.0225 | 0.0268 (0.0256-0.0268) | -0.110 |
| SOL | 60m:z2 | BROADBOT | B | 0.0164 | 0.0192 (0.011-0.0329) | +0.157 |
| SOL | 60m:z2 | BROADTOP | A | 0.0225 | 0.0281 (0.0268-0.0281) | +0.150 |
| SOL | 60m:z2 | BROADTOP | B | 0.0137 | 0.0192 (0.011-0.0329) | -0.057 |
| SOL | 60m:z2 | BULLFLAG | A | 0.112 | 0.0786 (0.0767-0.0805) | +0.009 |
| SOL | 60m:z2 | BULLFLAG | B | 0.101 | 0.11 (0.0932-0.115) | -0.008 |
| SOL | 60m:z2 | BULLPEN | A | 0.0437 | 0.0293 (0.0268-0.0362) | -0.002 |
| SOL | 60m:z2 | BULLPEN | B | 0.0521 | 0.0356 (0.0301-0.0548) | +0.207 |
| SOL | 60m:z2 | CUP | A | 0.0168 | 0.0225 (0.0225-0.0231) | +0.038 |
| SOL | 60m:z2 | CUP | B | 0.0192 | 0.0274 (0.0192-0.0329) | +0.078 |
| SOL | 60m:z2 | DBOT | A | 0.394 | 0.392 (0.383-0.398) | -0.026 |
| SOL | 60m:z2 | DBOT | B | 0.419 | 0.392 (0.386-0.408) | -0.079 |
| SOL | 60m:z2 | DESCTRI | A | 0.118 | 0.136 (0.135-0.145) | +0.051 |
| SOL | 60m:z2 | DESCTRI | B | 0.112 | 0.145 (0.104-0.151) | -0.200 |
| SOL | 60m:z2 | DTOP | A | 0.389 | 0.392 (0.392-0.4) | -0.036 |
| SOL | 60m:z2 | DTOP | B | 0.381 | 0.403 (0.403-0.441) | -0.026 |
| SOL | 60m:z2 | FALWEDGE | A | 0.189 | 0.17 (0.166-0.187) | -0.003 |
| SOL | 60m:z2 | FALWEDGE | B | 0.236 | 0.189 (0.178-0.197) | +0.026 |
| SOL | 60m:z2 | HARM.BEAR | A | 0.00873 | 0.00811 (0.00686-0.00873) | -0.307 |
| SOL | 60m:z2 | HARM.BEAR | B | 0.0137 | 0.011 (0.00822-0.011) | -0.179 |
| SOL | 60m:z2 | HARM.BULL | A | 0.0143 | 0.00998 (0.00437-0.0125) | +0.236 |
| SOL | 60m:z2 | HARM.BULL | B | 0.00274 | 0.0164 (0.011-0.0219) | +0.503 |
| SOL | 60m:z2 | HS | A | 0.0661 | 0.0661 (0.0661-0.0761) | +0.066 |
| SOL | 60m:z2 | HS | B | 0.0932 | 0.0849 (0.0767-0.0877) | -0.000 |
| SOL | 60m:z2 | IHS | A | 0.0717 | 0.0649 (0.0586-0.073) | +0.056 |
| SOL | 60m:z2 | IHS | B | 0.0959 | 0.074 (0.0603-0.0767) | +0.126 |
| SOL | 60m:z2 | INVCUP | A | 0.02 | 0.0256 (0.0218-0.0262) | -0.003 |
| SOL | 60m:z2 | INVCUP | B | 0.0329 | 0.0192 (0.0164-0.0192) | -0.123 |
| SOL | 60m:z2 | RECT | A | 0.025 | 0.0449 (0.0368-0.0462) | -0.137 |
| SOL | 60m:z2 | RECT | B | 0.0356 | 0.0548 (0.0438-0.0603) | +0.071 |
| SOL | 60m:z2 | RISWEDGE | A | 0.198 | 0.188 (0.171-0.196) | +0.027 |
| SOL | 60m:z2 | RISWEDGE | B | 0.2 | 0.211 (0.178-0.227) | -0.033 |
| SOL | 60m:z2 | ROUNDBOT | A | 0.0443 | 0.0593 (0.0593-0.0661) | +0.343 |
| SOL | 60m:z2 | ROUNDBOT | B | 0.0822 | 0.063 (0.0575-0.0658) | -0.292 |
| SOL | 60m:z2 | ROUNDTOP | A | 0.0443 | 0.048 (0.0437-0.0512) | -0.055 |
| SOL | 60m:z2 | ROUNDTOP | B | 0.0411 | 0.0548 (0.0438-0.074) | -0.403 |
| SOL | 60m:z2 | SYMTRI | A | 0.16 | 0.15 (0.147-0.173) | +0.101 |
| SOL | 60m:z2 | SYMTRI | B | 0.132 | 0.153 (0.148-0.167) | +0.068 |
| SOL | 60m:z2 | TRIBOT | A | 0.0406 | 0.0643 (0.053-0.0742) | +0.064 |
| SOL | 60m:z2 | TRIBOT | B | 0.0411 | 0.0466 (0.0384-0.074) | -0.391 |
| SOL | 60m:z2 | TRITOP | A | 0.0493 | 0.0574 (0.0518-0.0661) | +0.070 |
| SOL | 60m:z2 | TRITOP | B | 0.074 | 0.0603 (0.0575-0.0822) | -0.187 |
| SOL | 60m:z4 | ABCD.BEAR | A | 0.0268 | 0.0218 (0.0193-0.0225) | +0.116 |
| SOL | 60m:z4 | ABCD.BEAR | B | 0.0274 | 0.0247 (0.0247-0.0274) | -0.057 |
| SOL | 60m:z4 | ABCD.BULL | A | 0.0137 | 0.0193 (0.0193-0.0206) | +0.067 |
| SOL | 60m:z4 | ABCD.BULL | B | 0.0274 | 0.011 (0.011-0.0137) | +0.044 |
| SOL | 60m:z4 | ASCTRI | A | 0.0412 | 0.048 (0.0412-0.0518) | -0.055 |
| SOL | 60m:z4 | ASCTRI | B | 0.0411 | 0.0521 (0.0521-0.0849) | +0.317 |
| SOL | 60m:z4 | BEARFLAG | A | 0.0112 | 0.0119 (0.00624-0.0137) | +0.028 |
| SOL | 60m:z4 | BEARFLAG | B | 0.0137 | 0.0164 (0.0164-0.0219) | -0.115 |
| SOL | 60m:z4 | BEARPEN | A | 0.00998 | 0.00437 (0.00437-0.00499) | +0.100 |
| SOL | 60m:z4 | BEARPEN | B | 0.00548 | 0.00274 (0.00274-0.0137) | -0.118 |
| SOL | 60m:z4 | BROADBOT | A | 0.00499 | 0.00873 (0.00499-0.00998) | +0.237 |
| SOL | 60m:z4 | BROADBOT | B | 0.00274 | 0.00548 (0-0.0137) | +0.411 |
| SOL | 60m:z4 | BROADTOP | A | 0.00437 | 0.00561 (0.00499-0.00686) | +0.394 |
| SOL | 60m:z4 | BROADTOP | B | 0.011 | 0.00822 (0.00274-0.00822) | +0.475 |
| SOL | 60m:z4 | BULLFLAG | A | 0.0131 | 0.0106 (0.00749-0.0119) | +0.014 |
| SOL | 60m:z4 | BULLFLAG | B | 0.00822 | 0.011 (0.011-0.0164) | +0.111 |
| SOL | 60m:z4 | BULLPEN | A | 0.00811 | 0.00312 (0.00187-0.00561) | -0.066 |
| SOL | 60m:z4 | BULLPEN | B | 0 | 0.00822 (0.00822-0.0137) |  |
| SOL | 60m:z4 | CUP | A | 0.00499 | 0.00749 (0.00624-0.00811) | -0.158 |
| SOL | 60m:z4 | CUP | B | 0.00274 | 0.00822 (0.00274-0.011) | -0.357 |
| SOL | 60m:z4 | DBOT | A | 0.148 | 0.16 (0.157-0.162) | -0.008 |
| SOL | 60m:z4 | DBOT | B | 0.173 | 0.156 (0.148-0.167) | +0.103 |
| SOL | 60m:z4 | DESCTRI | A | 0.0474 | 0.0474 (0.0455-0.0493) | +0.009 |
| SOL | 60m:z4 | DESCTRI | B | 0.0438 | 0.0438 (0.0329-0.0521) | +0.228 |
| SOL | 60m:z4 | DTOP | A | 0.153 | 0.162 (0.156-0.163) | +0.041 |
| SOL | 60m:z4 | DTOP | B | 0.14 | 0.162 (0.159-0.186) | -0.086 |
| SOL | 60m:z4 | FALWEDGE | A | 0.0705 | 0.0705 (0.0668-0.0774) | -0.004 |
| SOL | 60m:z4 | FALWEDGE | B | 0.0904 | 0.0658 (0.0521-0.0685) | -0.047 |
| SOL | 60m:z4 | HARM.BEAR | A | 0.00312 | 0.00312 (0.00125-0.00561) | +0.456 |
| SOL | 60m:z4 | HARM.BEAR | B | 0.00822 | 0.00822 (0-0.0137) | -0.155 |
| SOL | 60m:z4 | HARM.BULL | A | 0.00125 | 0.00437 (0.00125-0.00499) | -0.373 |
| SOL | 60m:z4 | HARM.BULL | B | 0.00274 | 0.00274 (0-0.00548) |  |
| SOL | 60m:z4 | HS | A | 0.0231 | 0.0206 (0.0193-0.0231) | +0.162 |
| SOL | 60m:z4 | HS | B | 0.0164 | 0.0274 (0.0247-0.0301) | -0.383 |
| SOL | 60m:z4 | IHS | A | 0.0193 | 0.0193 (0.0181-0.0218) | +0.008 |
| SOL | 60m:z4 | IHS | B | 0.0192 | 0.0219 (0.0192-0.0301) | +0.081 |
| SOL | 60m:z4 | INVCUP | A | 0.00873 | 0.00749 (0.00624-0.00811) | -0.180 |
| SOL | 60m:z4 | INVCUP | B | 0.00274 | 0.00822 (0.00274-0.0164) | -0.454 |
| SOL | 60m:z4 | RECT | A | 0.00686 | 0.0156 (0.0143-0.02) | -0.165 |
| SOL | 60m:z4 | RECT | B | 0.0137 | 0.0219 (0.0164-0.0247) | +0.388 |
| SOL | 60m:z4 | RISWEDGE | A | 0.0699 | 0.0624 (0.058-0.0749) | +0.027 |
| SOL | 60m:z4 | RISWEDGE | B | 0.0904 | 0.0685 (0.0521-0.0904) | +0.285 |
| SOL | 60m:z4 | ROUNDBOT | A | 0.0318 | 0.0418 (0.0399-0.0518) | +0.383 |
| SOL | 60m:z4 | ROUNDBOT | B | 0.0521 | 0.0493 (0.0438-0.0603) | -0.351 |
| SOL | 60m:z4 | ROUNDTOP | A | 0.0406 | 0.0374 (0.0293-0.0387) | +0.220 |
| SOL | 60m:z4 | ROUNDTOP | B | 0.0411 | 0.0411 (0.0329-0.063) | +0.144 |
| SOL | 60m:z4 | SYMTRI | A | 0.0661 | 0.0543 (0.0518-0.058) | +0.118 |
| SOL | 60m:z4 | SYMTRI | B | 0.0822 | 0.0767 (0.063-0.0849) | +0.181 |
| SOL | 60m:z4 | TRIBOT | A | 0.0131 | 0.0225 (0.0218-0.0231) | +0.131 |
| SOL | 60m:z4 | TRIBOT | B | 0.011 | 0.0137 (0.011-0.0164) | -0.604 |
| SOL | 60m:z4 | TRITOP | A | 0.0119 | 0.0225 (0.0162-0.0231) | -0.001 |
| SOL | 60m:z4 | TRITOP | B | 0.0301 | 0.0247 (0.0164-0.0247) | -0.001 |
| SOL | 60m:z8 | ABCD.BEAR | A | 0.00749 | 0.00374 (0.00312-0.00811) | +0.155 |
| SOL | 60m:z8 | ABCD.BEAR | B | 0.011 | 0.00548 (0.00548-0.0137) | -0.064 |
| SOL | 60m:z8 | ABCD.BULL | A | 0.00437 | 0.00374 (0.00312-0.00499) | -0.259 |
| SOL | 60m:z8 | ABCD.BULL | B | 0.00548 | 0.00274 (0-0.00548) | +0.464 |
| SOL | 60m:z8 | ASCTRI | A | 0.00873 | 0.00873 (0.00873-0.0131) | +0.201 |
| SOL | 60m:z8 | ASCTRI | B | 0.0164 | 0.011 (0.00822-0.0219) | -0.256 |
| SOL | 60m:z8 | BEARFLAG | A | 0 | 0.000624 (0-0.00187) |  |
| SOL | 60m:z8 | BEARFLAG | B | 0 | 0 (0-0.00274) |  |
| SOL | 60m:z8 | BEARPEN | A | 0 | 0 (0-0.00125) |  |
| SOL | 60m:z8 | BEARPEN | B | 0 | 0 (0-0.00274) |  |
| SOL | 60m:z8 | BROADBOT | A | 0 | 0.00187 (0.00125-0.00312) |  |
| SOL | 60m:z8 | BROADBOT | B | 0 | 0.00548 (0-0.00548) |  |
| SOL | 60m:z8 | BROADTOP | A | 0.000624 | 0.00125 (0.000624-0.0025) | +0.479 |
| SOL | 60m:z8 | BROADTOP | B | 0 | 0.00274 (0-0.00274) |  |
| SOL | 60m:z8 | BULLFLAG | A | 0 | 0 (0-0.000624) |  |
| SOL | 60m:z8 | BULLFLAG | B | 0 | 0 (0-0) |  |
| SOL | 60m:z8 | BULLPEN | A | 0 | 0 (0-0) |  |
| SOL | 60m:z8 | BULLPEN | B | 0 | 0 (0-0.00274) |  |
| SOL | 60m:z8 | CUP | A | 0.0025 | 0.000624 (0.000624-0.00125) | +0.670 |
| SOL | 60m:z8 | CUP | B | 0.00274 | 0.00274 (0-0.00274) |  |
| SOL | 60m:z8 | DBOT | A | 0.0374 | 0.043 (0.0412-0.0518) | +0.148 |
| SOL | 60m:z8 | DBOT | B | 0.0466 | 0.0521 (0.0466-0.0603) | -0.035 |
| SOL | 60m:z8 | DESCTRI | A | 0.0137 | 0.015 (0.0112-0.0156) | -0.119 |
| SOL | 60m:z8 | DESCTRI | B | 0.0192 | 0.011 (0.00822-0.0137) | -0.205 |
| SOL | 60m:z8 | DTOP | A | 0.0368 | 0.0437 (0.0393-0.048) | +0.184 |
| SOL | 60m:z8 | DTOP | B | 0.0411 | 0.0521 (0.0493-0.0685) | +0.296 |
| SOL | 60m:z8 | FALWEDGE | A | 0.0175 | 0.0181 (0.015-0.0206) | +0.200 |
| SOL | 60m:z8 | FALWEDGE | B | 0.0274 | 0.0219 (0.0192-0.0219) | -0.042 |
| SOL | 60m:z8 | HARM.BEAR | A | 0.0025 | 0.00125 (0.00125-0.0025) |  |
| SOL | 60m:z8 | HARM.BEAR | B | 0.00274 | 0.00274 (0-0.00822) | +0.000 |
| SOL | 60m:z8 | HARM.BULL | A | 0.00187 | 0.000624 (0-0.00125) | +0.158 |
| SOL | 60m:z8 | HARM.BULL | B | 0 | 0 (0-0.00274) |  |
| SOL | 60m:z8 | HS | A | 0.00561 | 0.00561 (0.00561-0.00811) | +0.166 |
| SOL | 60m:z8 | HS | B | 0.00274 | 0.011 (0.00274-0.0164) | +0.559 |
| SOL | 60m:z8 | IHS | A | 0.00561 | 0.00437 (0.00437-0.00499) | +0.103 |
| SOL | 60m:z8 | IHS | B | 0.011 | 0.00548 (0.00274-0.00822) | -0.059 |
| SOL | 60m:z8 | INVCUP | A | 0.000624 | 0.00374 (0.00125-0.00624) |  |
| SOL | 60m:z8 | INVCUP | B | 0.00274 | 0 (0-0.00822) |  |
| SOL | 60m:z8 | RECT | A | 0.00437 | 0.0025 (0.0025-0.00499) | -0.222 |
| SOL | 60m:z8 | RECT | B | 0.00274 | 0 (0-0.00822) |  |
| SOL | 60m:z8 | RISWEDGE | A | 0.00998 | 0.0156 (0.0125-0.0162) | +0.342 |
| SOL | 60m:z8 | RISWEDGE | B | 0.0274 | 0.0219 (0.011-0.0356) | -0.203 |
| SOL | 60m:z8 | ROUNDBOT | A | 0.00873 | 0.0143 (0.0125-0.0193) |  |
| SOL | 60m:z8 | ROUNDBOT | B | 0.011 | 0.011 (0.00548-0.0164) |  |
| SOL | 60m:z8 | ROUNDTOP | A | 0.00936 | 0.00811 (0.00437-0.0112) |  |
| SOL | 60m:z8 | ROUNDTOP | B | 0.00548 | 0.011 (0.00548-0.011) |  |
| SOL | 60m:z8 | SYMTRI | A | 0.02 | 0.0143 (0.0131-0.0212) | -0.020 |
| SOL | 60m:z8 | SYMTRI | B | 0.0274 | 0.0274 (0.0219-0.0329) | -0.110 |
| SOL | 60m:z8 | TRIBOT | A | 0.00374 | 0.00499 (0.00374-0.00624) | +0.376 |
| SOL | 60m:z8 | TRIBOT | B | 0.00548 | 0.00548 (0.00274-0.00822) | +0.364 |
| SOL | 60m:z8 | TRITOP | A | 0.00374 | 0.00561 (0.00437-0.00561) | +0.041 |
| SOL | 60m:z8 | TRITOP | B | 0.00822 | 0.00274 (0-0.00822) | +0.456 |
| XRP | 15m:K | LMW.BBOT | A | 0.489 | 0.839 (0.801-0.843) | -0.019 |
| XRP | 15m:K | LMW.BBOT | B | 0.581 | 0.825 (0.806-0.904) | -0.023 |
| XRP | 15m:K | LMW.BTOP | A | 0.557 | 0.875 (0.833-0.877) | -0.007 |
| XRP | 15m:K | LMW.BTOP | B | 0.526 | 0.858 (0.778-0.912) | -0.051 |
| XRP | 15m:K | LMW.DBOT | A | 0.317 | 0.337 (0.336-0.362) | -0.019 |
| XRP | 15m:K | LMW.DBOT | B | 0.381 | 0.359 (0.323-0.381) | +0.029 |
| XRP | 15m:K | LMW.DTOP | A | 0.353 | 0.349 (0.344-0.351) | +0.035 |
| XRP | 15m:K | LMW.DTOP | B | 0.378 | 0.389 (0.356-0.392) | +0.029 |
| XRP | 15m:K | LMW.HS | A | 4.86 | 4.73 (4.69-4.73) | -0.039 |
| XRP | 15m:K | LMW.HS | B | 5.11 | 4.91 (4.9-5.08) | -0.051 |
| XRP | 15m:K | LMW.HS.SWZ | A | 0.0142 | 0.0153 (0.0137-0.0159) | -0.007 |
| XRP | 15m:K | LMW.HS.SWZ | B | 0.00822 | 0.00822 (0.00548-0.011) | -0.333 |
| XRP | 15m:K | LMW.IHS | A | 4.97 | 4.72 (4.7-4.76) | -0.028 |
| XRP | 15m:K | LMW.IHS | B | 5.12 | 4.79 (4.78-4.94) | -0.033 |
| XRP | 15m:K | LMW.IHS.SWZ | A | 0.017 | 0.0148 (0.012-0.0186) | -0.037 |
| XRP | 15m:K | LMW.IHS.SWZ | B | 0.0219 | 0.00548 (0.00274-0.00548) | -0.110 |
| XRP | 15m:K | LMW.RBOT | A | 15.5 | 14.6 (14.6-14.7) | -0.015 |
| XRP | 15m:K | LMW.RBOT | B | 17.3 | 15.7 (15.5-16.1) | -0.001 |
| XRP | 15m:K | LMW.RTOP | A | 15.9 | 14.6 (14.6-14.7) | -0.015 |
| XRP | 15m:K | LMW.RTOP | B | 17.5 | 15.7 (15.6-16) | -0.006 |
| XRP | 15m:K | LMW.TBOT | A | 1.43 | 1.07 (1.07-1.1) | -0.357 |
| XRP | 15m:K | LMW.TBOT | B | 1.35 | 0.975 (0.964-1.02) | -0.310 |
| XRP | 15m:K | LMW.TTOP | A | 1.39 | 1.05 (1.04-1.11) | -0.384 |
| XRP | 15m:K | LMW.TTOP | B | 1.36 | 0.967 (0.912-0.984) | -0.302 |
| XRP | 15m:z2 | ABCD.BEAR | A | 0.21 | 0.25 (0.225-0.251) | -0.017 |
| XRP | 15m:z2 | ABCD.BEAR | B | 0.178 | 0.258 (0.236-0.258) | +0.049 |
| XRP | 15m:z2 | ABCD.BULL | A | 0.212 | 0.224 (0.216-0.225) | -0.002 |
| XRP | 15m:z2 | ABCD.BULL | B | 0.244 | 0.263 (0.258-0.271) | -0.006 |
| XRP | 15m:z2 | ASCTRI | A | 0.52 | 0.519 (0.518-0.548) | +0.036 |
| XRP | 15m:z2 | ASCTRI | B | 0.51 | 0.573 (0.532-0.575) | +0.065 |
| XRP | 15m:z2 | BEARFLAG | A | 0.383 | 0.379 (0.377-0.396) | -0.015 |
| XRP | 15m:z2 | BEARFLAG | B | 0.307 | 0.375 (0.34-0.392) | +0.048 |
| XRP | 15m:z2 | BEARPEN | A | 0.142 | 0.152 (0.125-0.162) | -0.026 |
| XRP | 15m:z2 | BEARPEN | B | 0.134 | 0.129 (0.123-0.129) | +0.081 |
| XRP | 15m:z2 | BROADBOT | A | 0.0777 | 0.103 (0.0936-0.114) | +0.021 |
| XRP | 15m:z2 | BROADBOT | B | 0.0932 | 0.104 (0.0849-0.112) | +0.081 |
| XRP | 15m:z2 | BROADTOP | A | 0.0881 | 0.105 (0.102-0.105) | +0.040 |
| XRP | 15m:z2 | BROADTOP | B | 0.0932 | 0.11 (0.0932-0.129) | -0.179 |
| XRP | 15m:z2 | BULLFLAG | A | 0.407 | 0.365 (0.362-0.382) | -0.039 |
| XRP | 15m:z2 | BULLFLAG | B | 0.345 | 0.353 (0.315-0.384) | +0.086 |
| XRP | 15m:z2 | BULLPEN | A | 0.171 | 0.136 (0.126-0.138) | -0.007 |
| XRP | 15m:z2 | BULLPEN | B | 0.173 | 0.129 (0.126-0.132) | -0.003 |
| XRP | 15m:z2 | CUP | A | 0.064 | 0.0848 (0.0799-0.0876) | -0.039 |
| XRP | 15m:z2 | CUP | B | 0.0603 | 0.0849 (0.0822-0.0986) | -0.233 |
| XRP | 15m:z2 | DBOT | A | 1.53 | 1.61 (1.58-1.62) | -0.003 |
| XRP | 15m:z2 | DBOT | B | 1.68 | 1.63 (1.56-1.63) | -0.000 |
| XRP | 15m:z2 | DESCTRI | A | 0.535 | 0.543 (0.533-0.561) | +0.015 |
| XRP | 15m:z2 | DESCTRI | B | 0.617 | 0.548 (0.545-0.567) | -0.092 |
| XRP | 15m:z2 | DTOP | A | 1.66 | 1.6 (1.59-1.61) | -0.015 |
| XRP | 15m:z2 | DTOP | B | 1.64 | 1.65 (1.56-1.69) | +0.007 |
| XRP | 15m:z2 | FALWEDGE | A | 0.78 | 0.758 (0.736-0.758) | -0.023 |
| XRP | 15m:z2 | FALWEDGE | B | 0.844 | 0.77 (0.726-0.773) | -0.056 |
| XRP | 15m:z2 | HARM.BEAR | A | 0.046 | 0.04 (0.0389-0.0416) | -0.070 |
| XRP | 15m:z2 | HARM.BEAR | B | 0.0329 | 0.0548 (0.0384-0.0548) | -0.190 |
| XRP | 15m:z2 | HARM.BULL | A | 0.0301 | 0.0361 (0.0323-0.0367) | -0.064 |
| XRP | 15m:z2 | HARM.BULL | B | 0.0356 | 0.0301 (0.0219-0.0301) | +0.232 |
| XRP | 15m:z2 | HS | A | 0.297 | 0.268 (0.251-0.269) | +0.043 |
| XRP | 15m:z2 | HS | B | 0.244 | 0.26 (0.244-0.296) | -0.011 |
| XRP | 15m:z2 | IHS | A | 0.299 | 0.271 (0.265-0.278) | +0.011 |
| XRP | 15m:z2 | IHS | B | 0.266 | 0.263 (0.258-0.31) | +0.085 |
| XRP | 15m:z2 | INVCUP | A | 0.081 | 0.0706 (0.0679-0.0821) | +0.007 |
| XRP | 15m:z2 | INVCUP | B | 0.0795 | 0.0767 (0.0685-0.0795) | +0.138 |
| XRP | 15m:z2 | RECT | A | 0.134 | 0.159 (0.142-0.175) | -0.007 |
| XRP | 15m:z2 | RECT | B | 0.156 | 0.173 (0.156-0.178) | -0.011 |
| XRP | 15m:z2 | RISWEDGE | A | 0.747 | 0.77 (0.768-0.783) | +0.012 |
| XRP | 15m:z2 | RISWEDGE | B | 0.707 | 0.756 (0.754-0.775) | +0.025 |
| XRP | 15m:z2 | ROUNDBOT | A | 0.102 | 0.238 (0.233-0.24) | +0.030 |
| XRP | 15m:z2 | ROUNDBOT | B | 0.164 | 0.241 (0.211-0.249) | -0.282 |
| XRP | 15m:z2 | ROUNDTOP | A | 0.185 | 0.218 (0.213-0.222) | +0.025 |
| XRP | 15m:z2 | ROUNDTOP | B | 0.214 | 0.219 (0.184-0.241) | -0.069 |
| XRP | 15m:z2 | SYMTRI | A | 0.794 | 0.653 (0.64-0.668) | +0.068 |
| XRP | 15m:z2 | SYMTRI | B | 0.704 | 0.666 (0.636-0.701) | +0.060 |
| XRP | 15m:z2 | TRIBOT | A | 0.176 | 0.237 (0.215-0.256) | -0.020 |
| XRP | 15m:z2 | TRIBOT | B | 0.233 | 0.252 (0.219-0.252) | -0.051 |
| XRP | 15m:z2 | TRITOP | A | 0.207 | 0.228 (0.215-0.241) | +0.024 |
| XRP | 15m:z2 | TRITOP | B | 0.23 | 0.269 (0.206-0.277) | +0.158 |
| XRP | 15m:z4 | ABCD.BEAR | A | 0.0761 | 0.0832 (0.0799-0.0843) | -0.034 |
| XRP | 15m:z4 | ABCD.BEAR | B | 0.0822 | 0.0904 (0.0575-0.0959) | -0.036 |
| XRP | 15m:z4 | ABCD.BULL | A | 0.0695 | 0.0744 (0.0744-0.0805) | -0.026 |
| XRP | 15m:z4 | ABCD.BULL | B | 0.0932 | 0.0849 (0.074-0.0959) | +0.021 |
| XRP | 15m:z4 | ASCTRI | A | 0.192 | 0.195 (0.186-0.212) | -0.025 |
| XRP | 15m:z4 | ASCTRI | B | 0.186 | 0.184 (0.156-0.192) | +0.075 |
| XRP | 15m:z4 | BEARFLAG | A | 0.0569 | 0.0712 (0.069-0.075) | +0.036 |
| XRP | 15m:z4 | BEARFLAG | B | 0.0356 | 0.0575 (0.0548-0.0795) | +0.239 |
| XRP | 15m:z4 | BEARPEN | A | 0.0252 | 0.0257 (0.0252-0.0378) | -0.053 |
| XRP | 15m:z4 | BEARPEN | B | 0.0164 | 0.0164 (0.0137-0.0274) | +0.049 |
| XRP | 15m:z4 | BROADBOT | A | 0.0192 | 0.029 (0.0268-0.0356) | -0.287 |
| XRP | 15m:z4 | BROADBOT | B | 0.0274 | 0.0384 (0.0247-0.0493) | -0.042 |
| XRP | 15m:z4 | BROADTOP | A | 0.023 | 0.0334 (0.0285-0.0372) | -0.044 |
| XRP | 15m:z4 | BROADTOP | B | 0.0274 | 0.0356 (0.0329-0.0438) | -0.037 |
| XRP | 15m:z4 | BULLFLAG | A | 0.052 | 0.0608 (0.0602-0.0651) | -0.004 |
| XRP | 15m:z4 | BULLFLAG | B | 0.0356 | 0.0658 (0.0548-0.0795) | +0.103 |
| XRP | 15m:z4 | BULLPEN | A | 0.0307 | 0.0257 (0.0252-0.029) | -0.077 |
| XRP | 15m:z4 | BULLPEN | B | 0.0247 | 0.0274 (0.0219-0.0274) | +0.156 |
| XRP | 15m:z4 | CUP | A | 0.0219 | 0.0307 (0.0285-0.0378) | -0.044 |
| XRP | 15m:z4 | CUP | B | 0.0329 | 0.0274 (0.0192-0.0329) | +0.368 |
| XRP | 15m:z4 | DBOT | A | 0.591 | 0.666 (0.655-0.693) | -0.001 |
| XRP | 15m:z4 | DBOT | B | 0.66 | 0.663 (0.641-0.674) | -0.039 |
| XRP | 15m:z4 | DESCTRI | A | 0.183 | 0.199 (0.195-0.221) | +0.020 |
| XRP | 15m:z4 | DESCTRI | B | 0.173 | 0.23 (0.186-0.233) | +0.071 |
| XRP | 15m:z4 | DTOP | A | 0.621 | 0.654 (0.646-0.677) | -0.028 |
| XRP | 15m:z4 | DTOP | B | 0.627 | 0.658 (0.636-0.707) | +0.081 |
| XRP | 15m:z4 | FALWEDGE | A | 0.258 | 0.276 (0.256-0.326) | -0.013 |
| XRP | 15m:z4 | FALWEDGE | B | 0.323 | 0.279 (0.255-0.296) | -0.056 |
| XRP | 15m:z4 | HARM.BEAR | A | 0.0164 | 0.0181 (0.0181-0.0192) | -0.075 |
| XRP | 15m:z4 | HARM.BEAR | B | 0.0192 | 0.011 (0.00548-0.0164) | -0.232 |
| XRP | 15m:z4 | HARM.BULL | A | 0.0164 | 0.00985 (0.00931-0.0104) | -0.058 |
| XRP | 15m:z4 | HARM.BULL | B | 0.0137 | 0.0192 (0.00822-0.0247) | +0.321 |
| XRP | 15m:z4 | HS | A | 0.0909 | 0.0941 (0.0941-0.105) | +0.052 |
| XRP | 15m:z4 | HS | B | 0.0986 | 0.0904 (0.0767-0.0986) | +0.069 |
| XRP | 15m:z4 | IHS | A | 0.0931 | 0.0909 (0.0909-0.0914) | -0.056 |
| XRP | 15m:z4 | IHS | B | 0.115 | 0.0849 (0.0822-0.0877) | +0.130 |
| XRP | 15m:z4 | INVCUP | A | 0.0307 | 0.035 (0.0339-0.0372) | +0.096 |
| XRP | 15m:z4 | INVCUP | B | 0.0247 | 0.0192 (0.011-0.0411) | -0.143 |
| XRP | 15m:z4 | RECT | A | 0.0372 | 0.0597 (0.0542-0.0629) | +0.005 |
| XRP | 15m:z4 | RECT | B | 0.0356 | 0.0712 (0.0575-0.0712) | +0.118 |
| XRP | 15m:z4 | RISWEDGE | A | 0.272 | 0.278 (0.261-0.285) | +0.058 |
| XRP | 15m:z4 | RISWEDGE | B | 0.269 | 0.277 (0.233-0.304) | -0.009 |
| XRP | 15m:z4 | ROUNDBOT | A | 0.0903 | 0.187 (0.177-0.191) | +0.289 |
| XRP | 15m:z4 | ROUNDBOT | B | 0.126 | 0.186 (0.151-0.192) | +0.403 |
| XRP | 15m:z4 | ROUNDTOP | A | 0.122 | 0.161 (0.144-0.175) | -0.166 |
| XRP | 15m:z4 | ROUNDTOP | B | 0.118 | 0.153 (0.151-0.173) | -0.022 |
| XRP | 15m:z4 | SYMTRI | A | 0.31 | 0.245 (0.23-0.259) | +0.060 |
| XRP | 15m:z4 | SYMTRI | B | 0.285 | 0.266 (0.252-0.293) | +0.144 |
| XRP | 15m:z4 | TRIBOT | A | 0.0586 | 0.0816 (0.0816-0.0958) | +0.003 |
| XRP | 15m:z4 | TRIBOT | B | 0.0603 | 0.118 (0.115-0.126) | +0.074 |
| XRP | 15m:z4 | TRITOP | A | 0.0608 | 0.0843 (0.0783-0.103) | -0.006 |
| XRP | 15m:z4 | TRITOP | B | 0.0658 | 0.0904 (0.0658-0.0986) | +0.014 |
| XRP | 15m:z8 | ABCD.BEAR | A | 0.0334 | 0.0241 (0.0241-0.0317) | -0.003 |
| XRP | 15m:z8 | ABCD.BEAR | B | 0.0384 | 0.0274 (0.0219-0.0301) | -0.087 |
| XRP | 15m:z8 | ABCD.BULL | A | 0.0203 | 0.0224 (0.0186-0.0224) | -0.092 |
| XRP | 15m:z8 | ABCD.BULL | B | 0.0356 | 0.0356 (0.0356-0.0411) | +0.039 |
| XRP | 15m:z8 | ASCTRI | A | 0.0525 | 0.0602 (0.0438-0.0624) | +0.004 |
| XRP | 15m:z8 | ASCTRI | B | 0.0685 | 0.0575 (0.0384-0.0603) | +0.242 |
| XRP | 15m:z8 | BEARFLAG | A | 0.000547 | 0.00712 (0.00438-0.00821) | -0.068 |
| XRP | 15m:z8 | BEARFLAG | B | 0 | 0 (0-0) |  |
| XRP | 15m:z8 | BEARPEN | A | 0.000547 | 0.00109 (0.00109-0.00328) | -0.052 |
| XRP | 15m:z8 | BEARPEN | B | 0 | 0 (0-0) |  |
| XRP | 15m:z8 | BROADBOT | A | 0.00109 | 0.00931 (0.00821-0.00985) | -0.670 |
| XRP | 15m:z8 | BROADBOT | B | 0.00274 | 0.00548 (0-0.0164) |  |
| XRP | 15m:z8 | BROADTOP | A | 0.00493 | 0.00821 (0.00821-0.00931) | -0.546 |
| XRP | 15m:z8 | BROADTOP | B | 0.00274 | 0.00822 (0.00548-0.00822) |  |
| XRP | 15m:z8 | BULLFLAG | A | 0.00164 | 0.00383 (0.00383-0.00493) | +0.612 |
| XRP | 15m:z8 | BULLFLAG | B | 0.011 | 0.00822 (0.00822-0.0137) | -0.063 |
| XRP | 15m:z8 | BULLPEN | A | 0.00219 | 0.00109 (0.000547-0.00164) | +0.117 |
| XRP | 15m:z8 | BULLPEN | B | 0 | 0.00274 (0.00274-0.00548) |  |
| XRP | 15m:z8 | CUP | A | 0.00931 | 0.0131 (0.012-0.0137) | +0.080 |
| XRP | 15m:z8 | CUP | B | 0.011 | 0.0137 (0.0137-0.0164) | -0.309 |
| XRP | 15m:z8 | DBOT | A | 0.18 | 0.195 (0.192-0.207) | -0.040 |
| XRP | 15m:z8 | DBOT | B | 0.2 | 0.208 (0.178-0.211) | +0.151 |
| XRP | 15m:z8 | DESCTRI | A | 0.0553 | 0.0586 (0.0542-0.0662) | +0.093 |
| XRP | 15m:z8 | DESCTRI | B | 0.0575 | 0.0685 (0.0575-0.0712) | -0.047 |
| XRP | 15m:z8 | DTOP | A | 0.18 | 0.2 (0.182-0.212) | +0.009 |
| XRP | 15m:z8 | DTOP | B | 0.186 | 0.186 (0.17-0.203) | +0.205 |
| XRP | 15m:z8 | FALWEDGE | A | 0.0723 | 0.0854 (0.0679-0.0903) | +0.064 |
| XRP | 15m:z8 | FALWEDGE | B | 0.104 | 0.0877 (0.0822-0.0959) | +0.014 |
| XRP | 15m:z8 | HARM.BEAR | A | 0.00876 | 0.00274 (0.00164-0.00493) | +0.018 |
| XRP | 15m:z8 | HARM.BEAR | B | 0.00274 | 0.00822 (0.00548-0.00822) | +0.046 |
| XRP | 15m:z8 | HARM.BULL | A | 0.00712 | 0.00328 (0.00328-0.00438) | +0.132 |
| XRP | 15m:z8 | HARM.BULL | B | 0.00822 | 0.011 (0.00274-0.0137) | +0.400 |
| XRP | 15m:z8 | HS | A | 0.0323 | 0.0301 (0.0279-0.0328) | +0.037 |
| XRP | 15m:z8 | HS | B | 0.0301 | 0.0247 (0.0164-0.0329) | +0.050 |
| XRP | 15m:z8 | IHS | A | 0.0328 | 0.0301 (0.0246-0.0317) | +0.017 |
| XRP | 15m:z8 | IHS | B | 0.0384 | 0.0247 (0.0247-0.0274) | -0.042 |
| XRP | 15m:z8 | INVCUP | A | 0.00657 | 0.012 (0.00876-0.0148) | -0.084 |
| XRP | 15m:z8 | INVCUP | B | 0.0137 | 0.00822 (0.00548-0.0137) | -0.127 |
| XRP | 15m:z8 | RECT | A | 0.0131 | 0.0181 (0.012-0.023) | -0.088 |
| XRP | 15m:z8 | RECT | B | 0.0164 | 0.00822 (0.00274-0.0164) | +0.474 |
| XRP | 15m:z8 | RISWEDGE | A | 0.0504 | 0.0684 (0.0673-0.075) | +0.102 |
| XRP | 15m:z8 | RISWEDGE | B | 0.0466 | 0.0685 (0.0658-0.0767) | -0.256 |
| XRP | 15m:z8 | ROUNDBOT | A | 0.023 | 0.0498 (0.0487-0.0547) |  |
| XRP | 15m:z8 | ROUNDBOT | B | 0.0493 | 0.0466 (0.0329-0.0603) | -0.377 |
| XRP | 15m:z8 | ROUNDTOP | A | 0.029 | 0.0454 (0.0438-0.0525) | +0.273 |
| XRP | 15m:z8 | ROUNDTOP | B | 0.0466 | 0.0466 (0.0411-0.0521) | +0.633 |
| XRP | 15m:z8 | SYMTRI | A | 0.11 | 0.0794 (0.0777-0.0821) | +0.101 |
| XRP | 15m:z8 | SYMTRI | B | 0.123 | 0.0849 (0.0658-0.107) | +0.053 |
| XRP | 15m:z8 | TRIBOT | A | 0.0142 | 0.0279 (0.017-0.0285) | -0.122 |
| XRP | 15m:z8 | TRIBOT | B | 0.0164 | 0.0192 (0.0192-0.0329) | +0.402 |
| XRP | 15m:z8 | TRITOP | A | 0.017 | 0.0263 (0.0159-0.0307) | -0.300 |
| XRP | 15m:z8 | TRITOP | B | 0.0164 | 0.0192 (0.011-0.0192) | +0.400 |
| XRP | 240m:K | LMW.BBOT | A | 0.0213 | 0.0427 (0.04-0.0438) | -0.023 |
| XRP | 240m:K | LMW.BBOT | B | 0.0521 | 0.0493 (0.0384-0.063) | +0.013 |
| XRP | 240m:K | LMW.BTOP | A | 0.0296 | 0.0367 (0.0339-0.0443) | +0.027 |
| XRP | 240m:K | LMW.BTOP | B | 0.0274 | 0.0493 (0.0493-0.0767) | +0.175 |
| XRP | 240m:K | LMW.DBOT | A | 0.00328 | 0.00274 (0.00164-0.00328) | -0.547 |
| XRP | 240m:K | LMW.DBOT | B | 0.00274 | 0.00274 (0-0.00548) |  |
| XRP | 240m:K | LMW.DTOP | A | 0.00328 | 0.00438 (0.00274-0.00602) | -0.058 |
| XRP | 240m:K | LMW.DTOP | B | 0.00274 | 0 (0-0.00274) |  |
| XRP | 240m:K | LMW.HS | A | 0.172 | 0.155 (0.145-0.16) | -0.037 |
| XRP | 240m:K | LMW.HS | B | 0.2 | 0.175 (0.142-0.189) | +0.026 |
| XRP | 240m:K | LMW.HS.SWZ | A | 0.00876 | 0.00219 (0.00164-0.00493) | -0.064 |
| XRP | 240m:K | LMW.HS.SWZ | B | 0.00274 | 0.00822 (0.00274-0.00822) | +0.000 |
| XRP | 240m:K | LMW.IHS | A | 0.181 | 0.147 (0.147-0.165) | -0.032 |
| XRP | 240m:K | LMW.IHS | B | 0.211 | 0.178 (0.173-0.219) | -0.009 |
| XRP | 240m:K | LMW.IHS.SWZ | A | 0.00328 | 0.00547 (0.00493-0.00657) | +0.265 |
| XRP | 240m:K | LMW.IHS.SWZ | B | 0.00548 | 0.00822 (0-0.0164) | +0.000 |
| XRP | 240m:K | LMW.RBOT | A | 0.214 | 0.183 (0.163-0.195) | +0.009 |
| XRP | 240m:K | LMW.RBOT | B | 0.225 | 0.211 (0.184-0.222) | +0.013 |
| XRP | 240m:K | LMW.RTOP | A | 0.247 | 0.174 (0.157-0.198) | -0.010 |
| XRP | 240m:K | LMW.RTOP | B | 0.236 | 0.195 (0.192-0.2) | -0.013 |
| XRP | 240m:K | LMW.TBOT | A | 0.103 | 0.0509 (0.0482-0.052) | -0.350 |
| XRP | 240m:K | LMW.TBOT | B | 0.0904 | 0.063 (0.0548-0.0822) | -0.400 |
| XRP | 240m:K | LMW.TTOP | A | 0.0963 | 0.0591 (0.0504-0.0629) | -0.401 |
| XRP | 240m:K | LMW.TTOP | B | 0.112 | 0.0712 (0.0712-0.0986) | -0.230 |
| XRP | 240m:z2 | ABCD.BEAR | A | 0.012 | 0.0137 (0.0126-0.0159) | +0.207 |
| XRP | 240m:z2 | ABCD.BEAR | B | 0.0164 | 0.011 (0.00548-0.011) | +0.423 |
| XRP | 240m:z2 | ABCD.BULL | A | 0.00931 | 0.00931 (0.00876-0.0109) | +0.063 |
| XRP | 240m:z2 | ABCD.BULL | B | 0.0164 | 0.0192 (0.011-0.0219) | +0.069 |
| XRP | 240m:z2 | ASCTRI | A | 0.0257 | 0.0301 (0.023-0.0394) | +0.043 |
| XRP | 240m:z2 | ASCTRI | B | 0.0247 | 0.0384 (0.0301-0.0384) | -0.028 |
| XRP | 240m:z2 | BEARFLAG | A | 0.0186 | 0.0197 (0.0137-0.0208) | -0.062 |
| XRP | 240m:z2 | BEARFLAG | B | 0.0247 | 0.0219 (0.0137-0.0301) | -0.141 |
| XRP | 240m:z2 | BEARPEN | A | 0.0109 | 0.00876 (0.00493-0.0104) | +0.022 |
| XRP | 240m:z2 | BEARPEN | B | 0.00822 | 0.00822 (0.00548-0.0137) | +0.030 |
| XRP | 240m:z2 | BROADBOT | A | 0.00328 | 0.00328 (0.00328-0.00547) |  |
| XRP | 240m:z2 | BROADBOT | B | 0.011 | 0.00274 (0-0.00548) |  |
| XRP | 240m:z2 | BROADTOP | A | 0.00383 | 0.00493 (0.00383-0.00657) | -0.052 |
| XRP | 240m:z2 | BROADTOP | B | 0 | 0.00548 (0.00274-0.00822) |  |
| XRP | 240m:z2 | BULLFLAG | A | 0.0192 | 0.0192 (0.0153-0.0203) | -0.101 |
| XRP | 240m:z2 | BULLFLAG | B | 0.0219 | 0.0164 (0.011-0.0274) | -0.142 |
| XRP | 240m:z2 | BULLPEN | A | 0.00931 | 0.00712 (0.00547-0.0109) | -0.163 |
| XRP | 240m:z2 | BULLPEN | B | 0.0192 | 0.00822 (0-0.011) | -0.048 |
| XRP | 240m:z2 | CUP | A | 0.00274 | 0.00328 (0.00328-0.00328) | -0.257 |
| XRP | 240m:z2 | CUP | B | 0.00274 | 0.00548 (0.00274-0.00548) |  |
| XRP | 240m:z2 | DBOT | A | 0.081 | 0.0799 (0.0783-0.0854) | -0.075 |
| XRP | 240m:z2 | DBOT | B | 0.0849 | 0.0932 (0.0904-0.107) | +0.102 |
| XRP | 240m:z2 | DESCTRI | A | 0.0219 | 0.0241 (0.0241-0.0307) | +0.241 |
| XRP | 240m:z2 | DESCTRI | B | 0.0301 | 0.0274 (0.0274-0.0329) | +0.103 |
| XRP | 240m:z2 | DTOP | A | 0.0766 | 0.0887 (0.0777-0.0903) | +0.065 |
| XRP | 240m:z2 | DTOP | B | 0.0959 | 0.101 (0.0932-0.104) | +0.133 |
| XRP | 240m:z2 | FALWEDGE | A | 0.0383 | 0.0323 (0.0268-0.0411) | +0.116 |
| XRP | 240m:z2 | FALWEDGE | B | 0.0521 | 0.0548 (0.0466-0.0575) | -0.182 |
| XRP | 240m:z2 | HARM.BEAR | A | 0.00164 | 0.00219 (0.00219-0.00438) | -0.037 |
| XRP | 240m:z2 | HARM.BEAR | B | 0.00548 | 0 (0-0.00274) | +0.003 |
| XRP | 240m:z2 | HARM.BULL | A | 0.00274 | 0.00109 (0.00109-0.00383) | +0.082 |
| XRP | 240m:z2 | HARM.BULL | B | 0.00822 | 0.00548 (0.00274-0.00822) | +0.046 |
| XRP | 240m:z2 | HS | A | 0.0164 | 0.0153 (0.0115-0.0181) | +0.021 |
| XRP | 240m:z2 | HS | B | 0.0192 | 0.0164 (0.0137-0.0219) | -0.404 |
| XRP | 240m:z2 | IHS | A | 0.0148 | 0.0164 (0.012-0.017) | -0.151 |
| XRP | 240m:z2 | IHS | B | 0.00548 | 0.0137 (0.011-0.0219) | -0.301 |
| XRP | 240m:z2 | INVCUP | A | 0.00547 | 0.00328 (0.00274-0.00383) | -0.028 |
| XRP | 240m:z2 | INVCUP | B | 0.00548 | 0.00548 (0.00274-0.00548) |  |
| XRP | 240m:z2 | RECT | A | 0.00547 | 0.00766 (0.00657-0.0126) | +0.138 |
| XRP | 240m:z2 | RECT | B | 0 | 0.00548 (0.00548-0.011) |  |
| XRP | 240m:z2 | RISWEDGE | A | 0.04 | 0.0372 (0.0296-0.0454) | -0.001 |
| XRP | 240m:z2 | RISWEDGE | B | 0.0356 | 0.0521 (0.0493-0.0548) | +0.030 |
| XRP | 240m:z2 | ROUNDBOT | A | 0.00766 | 0.012 (0.0109-0.0131) | +0.517 |
| XRP | 240m:z2 | ROUNDBOT | B | 0.011 | 0.0192 (0.0164-0.0274) |  |
| XRP | 240m:z2 | ROUNDTOP | A | 0.00821 | 0.00985 (0.00876-0.012) | -0.417 |
| XRP | 240m:z2 | ROUNDTOP | B | 0.0192 | 0.0137 (0.011-0.0192) | -0.426 |
| XRP | 240m:z2 | SYMTRI | A | 0.0411 | 0.0307 (0.0263-0.0339) | +0.148 |
| XRP | 240m:z2 | SYMTRI | B | 0.063 | 0.0356 (0.0301-0.0603) | -0.048 |
| XRP | 240m:z2 | TRIBOT | A | 0.00821 | 0.0126 (0.00931-0.0159) | -0.007 |
| XRP | 240m:z2 | TRIBOT | B | 0.0137 | 0.0137 (0.00822-0.0137) | -0.563 |
| XRP | 240m:z2 | TRITOP | A | 0.00931 | 0.0175 (0.00876-0.0186) | +0.007 |
| XRP | 240m:z2 | TRITOP | B | 0 | 0.0137 (0.00274-0.0164) |  |
| XRP | 240m:z4 | ABCD.BEAR | A | 0.00547 | 0.00438 (0.00438-0.00547) | -0.030 |
| XRP | 240m:z4 | ABCD.BEAR | B | 0.00548 | 0.00274 (0-0.00548) | +0.712 |
| XRP | 240m:z4 | ABCD.BULL | A | 0.00274 | 0.00274 (0.00274-0.00328) | -0.090 |
| XRP | 240m:z4 | ABCD.BULL | B | 0.00548 | 0.00822 (0.00274-0.011) | -0.514 |
| XRP | 240m:z4 | ASCTRI | A | 0.00657 | 0.012 (0.00985-0.0148) | -0.062 |
| XRP | 240m:z4 | ASCTRI | B | 0.011 | 0.011 (0.00548-0.011) | +0.081 |
| XRP | 240m:z4 | BEARFLAG | A | 0.00328 | 0.00493 (0.00438-0.00547) | -0.116 |
| XRP | 240m:z4 | BEARFLAG | B | 0 | 0 (0-0.00822) |  |
| XRP | 240m:z4 | BEARPEN | A | 0.00274 | 0.00164 (0.00109-0.00274) | -0.229 |
| XRP | 240m:z4 | BEARPEN | B | 0 | 0.00274 (0-0.00274) |  |
| XRP | 240m:z4 | BROADBOT | A | 0.000547 | 0.00219 (0.00109-0.00274) | -0.562 |
| XRP | 240m:z4 | BROADBOT | B | 0.00274 | 0 (0-0) | +0.374 |
| XRP | 240m:z4 | BROADTOP | A | 0.00328 | 0.00219 (0.00164-0.00438) | +0.434 |
| XRP | 240m:z4 | BROADTOP | B | 0.00274 | 0.00274 (0-0.00548) |  |
| XRP | 240m:z4 | BULLFLAG | A | 0.00328 | 0.00164 (0.00164-0.00493) | +0.001 |
| XRP | 240m:z4 | BULLFLAG | B | 0.00274 | 0.00274 (0.00274-0.00548) | -0.062 |
| XRP | 240m:z4 | BULLPEN | A | 0.00109 | 0.00164 (0.00109-0.00164) | -0.158 |
| XRP | 240m:z4 | BULLPEN | B | 0.00548 | 0 (0-0.00274) | -0.214 |
| XRP | 240m:z4 | CUP | A | 0.000547 | 0.00219 (0.00219-0.00274) |  |
| XRP | 240m:z4 | CUP | B | 0 | 0.00274 (0.00274-0.00274) |  |
| XRP | 240m:z4 | DBOT | A | 0.0307 | 0.0345 (0.0334-0.035) | -0.035 |
| XRP | 240m:z4 | DBOT | B | 0.0411 | 0.0411 (0.0301-0.0438) | -0.115 |
| XRP | 240m:z4 | DESCTRI | A | 0.0115 | 0.012 (0.00602-0.0126) | +0.234 |
| XRP | 240m:z4 | DESCTRI | B | 0.0219 | 0.011 (0.00822-0.0219) | -0.267 |
| XRP | 240m:z4 | DTOP | A | 0.0296 | 0.0405 (0.0312-0.0405) | +0.033 |
| XRP | 240m:z4 | DTOP | B | 0.0384 | 0.0384 (0.0329-0.0438) | +0.107 |
| XRP | 240m:z4 | FALWEDGE | A | 0.0137 | 0.0115 (0.0109-0.0142) | +0.348 |
| XRP | 240m:z4 | FALWEDGE | B | 0.0137 | 0.0192 (0.011-0.0247) | +0.692 |
| XRP | 240m:z4 | HARM.BEAR | A | 0.00164 | 0.00109 (0-0.00164) | +0.492 |
| XRP | 240m:z4 | HARM.BEAR | B | 0 | 0 (0-0) |  |
| XRP | 240m:z4 | HARM.BULL | A | 0.00109 | 0.000547 (0-0.000547) | -0.169 |
| XRP | 240m:z4 | HARM.BULL | B | 0 | 0 (0-0.00274) |  |
| XRP | 240m:z4 | HS | A | 0.00493 | 0.00493 (0.00274-0.00712) | +0.011 |
| XRP | 240m:z4 | HS | B | 0.00548 | 0.00822 (0.00548-0.00822) | -0.268 |
| XRP | 240m:z4 | IHS | A | 0.00438 | 0.00602 (0.00328-0.00602) | +0.129 |
| XRP | 240m:z4 | IHS | B | 0.00548 | 0.00548 (0.00274-0.00548) | +0.681 |
| XRP | 240m:z4 | INVCUP | A | 0.00164 | 0.00219 (0.00219-0.00274) | +0.146 |
| XRP | 240m:z4 | INVCUP | B | 0.00274 | 0.00274 (0-0.0137) | -0.423 |
| XRP | 240m:z4 | RECT | A | 0.00109 | 0.00274 (0.00219-0.00274) |  |
| XRP | 240m:z4 | RECT | B | 0.00274 | 0.00274 (0-0.00274) |  |
| XRP | 240m:z4 | RISWEDGE | A | 0.00985 | 0.0148 (0.00931-0.017) | +0.020 |
| XRP | 240m:z4 | RISWEDGE | B | 0.011 | 0.0137 (0.0137-0.0164) | +0.573 |
| XRP | 240m:z4 | ROUNDBOT | A | 0.00712 | 0.00931 (0.00931-0.0137) |  |
| XRP | 240m:z4 | ROUNDBOT | B | 0.00274 | 0.0219 (0.00822-0.0274) |  |
| XRP | 240m:z4 | ROUNDTOP | A | 0.00274 | 0.00547 (0.00328-0.00985) | -0.401 |
| XRP | 240m:z4 | ROUNDTOP | B | 0.00822 | 0.00548 (0.00274-0.00822) |  |
| XRP | 240m:z4 | SYMTRI | A | 0.0164 | 0.0109 (0.00985-0.0126) | +0.000 |
| XRP | 240m:z4 | SYMTRI | B | 0.0274 | 0.011 (0-0.0137) | +0.278 |
| XRP | 240m:z4 | TRIBOT | A | 0.00164 | 0.00383 (0.00274-0.00547) |  |
| XRP | 240m:z4 | TRIBOT | B | 0.00822 | 0.00274 (0-0.00548) | -0.607 |
| XRP | 240m:z4 | TRITOP | A | 0.00274 | 0.00328 (0.00328-0.00766) | -0.140 |
| XRP | 240m:z4 | TRITOP | B | 0 | 0.00274 (0-0.00822) |  |
| XRP | 240m:z8 | ABCD.BEAR | A | 0.000547 | 0.00109 (0-0.00109) |  |
| XRP | 240m:z8 | ABCD.BEAR | B | 0.00274 | 0.00274 (0-0.00274) | -0.236 |
| XRP | 240m:z8 | ABCD.BULL | A | 0 | 0.00109 (0.000547-0.00164) |  |
| XRP | 240m:z8 | ABCD.BULL | B | 0.00548 | 0 (0-0.00274) | +0.246 |
| XRP | 240m:z8 | ASCTRI | A | 0.00383 | 0.00109 (0.000547-0.00328) | +0.333 |
| XRP | 240m:z8 | ASCTRI | B | 0.00274 | 0 (0-0.00822) | -0.434 |
| XRP | 240m:z8 | BEARFLAG | A | 0.000547 | 0.000547 (0-0.000547) | -0.067 |
| XRP | 240m:z8 | BEARFLAG | B | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | BEARPEN | A | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | BEARPEN | B | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | BROADBOT | A | 0.000547 | 0 (0-0) |  |
| XRP | 240m:z8 | BROADBOT | B | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | BROADTOP | A | 0.000547 | 0 (0-0.000547) |  |
| XRP | 240m:z8 | BROADTOP | B | 0 | 0 (0-0.00274) |  |
| XRP | 240m:z8 | BULLFLAG | A | 0 | 0 (0-0.000547) |  |
| XRP | 240m:z8 | BULLFLAG | B | 0.00274 | 0 (0-0.00274) | -0.062 |
| XRP | 240m:z8 | BULLPEN | A | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | BULLPEN | B | 0 | 0.00274 (0-0.00274) |  |
| XRP | 240m:z8 | CUP | A | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | CUP | B | 0 | 0 (0-0.00274) |  |
| XRP | 240m:z8 | DBOT | A | 0.00876 | 0.00985 (0.00876-0.0126) | +0.039 |
| XRP | 240m:z8 | DBOT | B | 0.0192 | 0.00822 (0.00822-0.0219) | -0.563 |
| XRP | 240m:z8 | DESCTRI | A | 0.00274 | 0.00493 (0.00328-0.00547) | -0.262 |
| XRP | 240m:z8 | DESCTRI | B | 0.0164 | 0 (0-0.00822) | -0.064 |
| XRP | 240m:z8 | DTOP | A | 0.00821 | 0.00985 (0.00931-0.0115) | +0.024 |
| XRP | 240m:z8 | DTOP | B | 0.0137 | 0.0137 (0.0137-0.0137) | +0.455 |
| XRP | 240m:z8 | FALWEDGE | A | 0.00274 | 0.00328 (0.00164-0.00383) | +0.040 |
| XRP | 240m:z8 | FALWEDGE | B | 0.00548 | 0.011 (0.00822-0.0137) | +0.537 |
| XRP | 240m:z8 | HARM.BEAR | A | 0.000547 | 0 (0-0) |  |
| XRP | 240m:z8 | HARM.BEAR | B | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | HARM.BULL | A | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | HARM.BULL | B | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | HS | A | 0.000547 | 0.00164 (0.000547-0.00219) |  |
| XRP | 240m:z8 | HS | B | 0.00274 | 0 (0-0.00274) | -0.420 |
| XRP | 240m:z8 | IHS | A | 0.000547 | 0 (0-0.00164) |  |
| XRP | 240m:z8 | IHS | B | 0.00548 | 0 (0-0.00274) | -0.352 |
| XRP | 240m:z8 | INVCUP | A | 0.000547 | 0.00109 (0.000547-0.00164) |  |
| XRP | 240m:z8 | INVCUP | B | 0 | 0 (0-0.00274) |  |
| XRP | 240m:z8 | RECT | A | 0.000547 | 0.00109 (0.000547-0.00109) |  |
| XRP | 240m:z8 | RECT | B | 0 | 0 (0-0) |  |
| XRP | 240m:z8 | RISWEDGE | A | 0.000547 | 0.00219 (0.00219-0.00274) |  |
| XRP | 240m:z8 | RISWEDGE | B | 0 | 0.00548 (0-0.00822) |  |
| XRP | 240m:z8 | ROUNDBOT | A | 0.00109 | 0.00438 (0.00328-0.00438) |  |
| XRP | 240m:z8 | ROUNDBOT | B | 0 | 0.00548 (0-0.011) |  |
| XRP | 240m:z8 | ROUNDTOP | A | 0.00164 | 0.00109 (0.000547-0.00109) |  |
| XRP | 240m:z8 | ROUNDTOP | B | 0 | 0.00274 (0.00274-0.00274) |  |
| XRP | 240m:z8 | SYMTRI | A | 0.00547 | 0.00328 (0.00328-0.00493) | +0.350 |
| XRP | 240m:z8 | SYMTRI | B | 0.0219 | 0 (0-0) | -0.219 |
| XRP | 240m:z8 | TRIBOT | A | 0.000547 | 0.00109 (0.000547-0.00164) |  |
| XRP | 240m:z8 | TRIBOT | B | 0.00822 | 0 (0-0.00274) | +0.027 |
| XRP | 240m:z8 | TRITOP | A | 0.000547 | 0.000547 (0-0.00164) |  |
| XRP | 240m:z8 | TRITOP | B | 0.00548 | 0 (0-0) | -0.063 |
| XRP | 5m:z2 | ABCD.BEAR | A | 0.709 | 0.764 (0.753-0.766) | -0.041 |
| XRP | 5m:z2 | ABCD.BEAR | B | 0.784 | 0.825 (0.819-0.838) | -0.044 |
| XRP | 5m:z2 | ABCD.BULL | A | 0.748 | 0.766 (0.759-0.787) | -0.038 |
| XRP | 5m:z2 | ABCD.BULL | B | 0.975 | 0.849 (0.806-0.904) | -0.057 |
| XRP | 5m:z2 | ASCTRI | A | 1.79 | 1.66 (1.66-1.71) | +0.018 |
| XRP | 5m:z2 | ASCTRI | B | 1.76 | 1.74 (1.72-1.85) | +0.021 |
| XRP | 5m:z2 | BEARFLAG | A | 0.983 | 1.14 (1.12-1.16) | +0.010 |
| XRP | 5m:z2 | BEARFLAG | B | 0.877 | 1.1 (1.02-1.15) | -0.003 |
| XRP | 5m:z2 | BEARPEN | A | 0.377 | 0.408 (0.407-0.417) | -0.012 |
| XRP | 5m:z2 | BEARPEN | B | 0.244 | 0.389 (0.381-0.403) | -0.049 |
| XRP | 5m:z2 | BROADBOT | A | 0.263 | 0.317 (0.29-0.321) | -0.069 |
| XRP | 5m:z2 | BROADBOT | B | 0.329 | 0.334 (0.323-0.381) | +0.029 |
| XRP | 5m:z2 | BROADTOP | A | 0.295 | 0.327 (0.32-0.333) | -0.035 |
| XRP | 5m:z2 | BROADTOP | B | 0.301 | 0.34 (0.301-0.37) | +0.061 |
| XRP | 5m:z2 | BULLFLAG | A | 1.19 | 1.11 (1.04-1.11) | +0.006 |
| XRP | 5m:z2 | BULLFLAG | B | 1.06 | 0.959 (0.926-0.964) | +0.044 |
| XRP | 5m:z2 | BULLPEN | A | 0.461 | 0.391 (0.372-0.41) | -0.013 |
| XRP | 5m:z2 | BULLPEN | B | 0.392 | 0.356 (0.348-0.4) | +0.115 |
| XRP | 5m:z2 | CUP | A | 0.221 | 0.262 (0.262-0.262) | -0.027 |
| XRP | 5m:z2 | CUP | B | 0.263 | 0.274 (0.255-0.279) | -0.134 |
| XRP | 5m:z2 | DBOT | A | 4.83 | 4.86 (4.8-4.88) | -0.004 |
| XRP | 5m:z2 | DBOT | B | 5.13 | 5.1 (5.09-5.18) | -0.005 |
| XRP | 5m:z2 | DESCTRI | A | 1.73 | 1.66 (1.62-1.67) | +0.022 |
| XRP | 5m:z2 | DESCTRI | B | 1.81 | 1.78 (1.6-1.78) | -0.013 |
| XRP | 5m:z2 | DTOP | A | 5.22 | 4.84 (4.83-4.87) | -0.011 |
| XRP | 5m:z2 | DTOP | B | 5.18 | 4.97 (4.94-5.05) | -0.005 |
| XRP | 5m:z2 | FALWEDGE | A | 2.46 | 2.34 (2.31-2.35) | +0.001 |
| XRP | 5m:z2 | FALWEDGE | B | 2.75 | 2.61 (2.33-2.69) | -0.007 |
| XRP | 5m:z2 | HARM.BEAR | A | 0.14 | 0.123 (0.117-0.123) | +0.000 |
| XRP | 5m:z2 | HARM.BEAR | B | 0.173 | 0.156 (0.101-0.178) | +0.033 |
| XRP | 5m:z2 | HARM.BULL | A | 0.128 | 0.114 (0.113-0.128) | -0.032 |
| XRP | 5m:z2 | HARM.BULL | B | 0.148 | 0.118 (0.115-0.123) | -0.063 |
| XRP | 5m:z2 | HS | A | 0.897 | 0.854 (0.85-0.87) | +0.027 |
| XRP | 5m:z2 | HS | B | 0.945 | 0.877 (0.871-0.962) | +0.009 |
| XRP | 5m:z2 | IHS | A | 0.961 | 0.85 (0.831-0.858) | +0.023 |
| XRP | 5m:z2 | IHS | B | 1.04 | 0.932 (0.907-0.94) | +0.042 |
| XRP | 5m:z2 | INVCUP | A | 0.235 | 0.252 (0.242-0.259) | -0.060 |
| XRP | 5m:z2 | INVCUP | B | 0.271 | 0.252 (0.238-0.296) | +0.109 |
| XRP | 5m:z2 | RECT | A | 0.436 | 0.49 (0.47-0.512) | -0.018 |
| XRP | 5m:z2 | RECT | B | 0.447 | 0.532 (0.51-0.578) | +0.031 |
| XRP | 5m:z2 | RISWEDGE | A | 2.5 | 2.39 (2.38-2.43) | +0.034 |
| XRP | 5m:z2 | RISWEDGE | B | 2.41 | 2.42 (2.37-2.58) | -0.018 |
| XRP | 5m:z2 | ROUNDBOT | A | 0.349 | 0.684 (0.681-0.699) | -0.032 |
| XRP | 5m:z2 | ROUNDBOT | B | 0.384 | 0.696 (0.597-0.732) | +0.256 |
| XRP | 5m:z2 | ROUNDTOP | A | 0.655 | 0.652 (0.637-0.663) | -0.026 |
| XRP | 5m:z2 | ROUNDTOP | B | 0.584 | 0.622 (0.589-0.633) | -0.134 |
| XRP | 5m:z2 | SYMTRI | A | 2.52 | 2.06 (2.02-2.06) | +0.043 |
| XRP | 5m:z2 | SYMTRI | B | 2.49 | 2.07 (2.07-2.14) | +0.028 |
| XRP | 5m:z2 | TRIBOT | A | 0.656 | 0.7 (0.7-0.719) | +0.003 |
| XRP | 5m:z2 | TRIBOT | B | 0.767 | 0.797 (0.74-0.838) | +0.010 |
| XRP | 5m:z2 | TRITOP | A | 0.714 | 0.737 (0.731-0.751) | -0.001 |
| XRP | 5m:z2 | TRITOP | B | 0.696 | 0.827 (0.762-0.871) | +0.036 |
| XRP | 5m:z4 | ABCD.BEAR | A | 0.239 | 0.274 (0.257-0.279) | -0.025 |
| XRP | 5m:z4 | ABCD.BEAR | B | 0.23 | 0.279 (0.252-0.29) | -0.012 |
| XRP | 5m:z4 | ABCD.BULL | A | 0.246 | 0.249 (0.239-0.26) | -0.040 |
| XRP | 5m:z4 | ABCD.BULL | B | 0.301 | 0.285 (0.271-0.296) | -0.009 |
| XRP | 5m:z4 | ASCTRI | A | 0.663 | 0.642 (0.629-0.662) | +0.030 |
| XRP | 5m:z4 | ASCTRI | B | 0.652 | 0.671 (0.647-0.701) | -0.016 |
| XRP | 5m:z4 | BEARFLAG | A | 0.145 | 0.201 (0.188-0.219) | -0.002 |
| XRP | 5m:z4 | BEARFLAG | B | 0.0959 | 0.2 (0.184-0.2) | +0.121 |
| XRP | 5m:z4 | BEARPEN | A | 0.0575 | 0.0777 (0.0712-0.0892) | -0.075 |
| XRP | 5m:z4 | BEARPEN | B | 0.0192 | 0.0493 (0.0384-0.063) | +0.015 |
| XRP | 5m:z4 | BROADBOT | A | 0.075 | 0.102 (0.0958-0.11) | +0.024 |
| XRP | 5m:z4 | BROADBOT | B | 0.0986 | 0.11 (0.0603-0.118) | +0.108 |
| XRP | 5m:z4 | BROADTOP | A | 0.0941 | 0.1 (0.0974-0.108) | +0.065 |
| XRP | 5m:z4 | BROADTOP | B | 0.0603 | 0.104 (0.101-0.137) | -0.172 |
| XRP | 5m:z4 | BULLFLAG | A | 0.172 | 0.183 (0.169-0.187) | -0.008 |
| XRP | 5m:z4 | BULLFLAG | B | 0.14 | 0.137 (0.137-0.156) | +0.058 |
| XRP | 5m:z4 | BULLPEN | A | 0.0772 | 0.069 (0.0635-0.075) | +0.027 |
| XRP | 5m:z4 | BULLPEN | B | 0.0548 | 0.0575 (0.0356-0.0658) | +0.013 |
| XRP | 5m:z4 | CUP | A | 0.0865 | 0.102 (0.1-0.109) | +0.079 |
| XRP | 5m:z4 | CUP | B | 0.0959 | 0.118 (0.115-0.123) | +0.118 |
| XRP | 5m:z4 | DBOT | A | 1.93 | 2.06 (2.03-2.08) | +0.026 |
| XRP | 5m:z4 | DBOT | B | 2.1 | 2.11 (2.07-2.15) | +0.006 |
| XRP | 5m:z4 | DESCTRI | A | 0.623 | 0.638 (0.628-0.667) | +0.002 |
| XRP | 5m:z4 | DESCTRI | B | 0.696 | 0.663 (0.6-0.677) | -0.036 |
| XRP | 5m:z4 | DTOP | A | 2.04 | 2.07 (2.05-2.08) | +0.004 |
| XRP | 5m:z4 | DTOP | B | 2.1 | 2.16 (2.08-2.19) | +0.005 |
| XRP | 5m:z4 | FALWEDGE | A | 0.818 | 0.885 (0.848-0.902) | -0.019 |
| XRP | 5m:z4 | FALWEDGE | B | 0.918 | 0.866 (0.844-0.932) | -0.097 |
| XRP | 5m:z4 | HARM.BEAR | A | 0.0443 | 0.0476 (0.0432-0.0558) | -0.070 |
| XRP | 5m:z4 | HARM.BEAR | B | 0.0575 | 0.0438 (0.0411-0.0493) | -0.067 |
| XRP | 5m:z4 | HARM.BULL | A | 0.0498 | 0.0454 (0.0405-0.0509) | -0.060 |
| XRP | 5m:z4 | HARM.BULL | B | 0.0384 | 0.0438 (0.0411-0.0493) | -0.020 |
| XRP | 5m:z4 | HS | A | 0.29 | 0.286 (0.279-0.295) | +0.053 |
| XRP | 5m:z4 | HS | B | 0.274 | 0.29 (0.255-0.304) | -0.046 |
| XRP | 5m:z4 | IHS | A | 0.323 | 0.3 (0.285-0.305) | +0.057 |
| XRP | 5m:z4 | IHS | B | 0.307 | 0.301 (0.282-0.318) | +0.162 |
| XRP | 5m:z4 | INVCUP | A | 0.0909 | 0.0952 (0.0854-0.117) | +0.047 |
| XRP | 5m:z4 | INVCUP | B | 0.074 | 0.112 (0.0712-0.115) | -0.054 |
| XRP | 5m:z4 | RECT | A | 0.157 | 0.184 (0.178-0.197) | -0.041 |
| XRP | 5m:z4 | RECT | B | 0.178 | 0.211 (0.186-0.214) | +0.110 |
| XRP | 5m:z4 | RISWEDGE | A | 0.845 | 0.869 (0.866-0.878) | +0.033 |
| XRP | 5m:z4 | RISWEDGE | B | 0.833 | 0.86 (0.797-0.88) | +0.034 |
| XRP | 5m:z4 | ROUNDBOT | A | 0.323 | 0.552 (0.522-0.553) | +0.071 |
| XRP | 5m:z4 | ROUNDBOT | B | 0.359 | 0.559 (0.548-0.592) | -0.062 |
| XRP | 5m:z4 | ROUNDTOP | A | 0.378 | 0.528 (0.511-0.528) | +0.032 |
| XRP | 5m:z4 | ROUNDTOP | B | 0.458 | 0.543 (0.515-0.586) | +0.063 |
| XRP | 5m:z4 | SYMTRI | A | 1.02 | 0.789 (0.781-0.807) | +0.075 |
| XRP | 5m:z4 | SYMTRI | B | 0.91 | 0.871 (0.811-0.893) | -0.004 |
| XRP | 5m:z4 | TRIBOT | A | 0.193 | 0.279 (0.253-0.281) | -0.057 |
| XRP | 5m:z4 | TRIBOT | B | 0.26 | 0.323 (0.296-0.329) | +0.064 |
| XRP | 5m:z4 | TRITOP | A | 0.243 | 0.269 (0.267-0.273) | +0.003 |
| XRP | 5m:z4 | TRITOP | B | 0.288 | 0.312 (0.288-0.334) | +0.082 |
| XRP | 5m:z8 | ABCD.BEAR | A | 0.0881 | 0.0783 (0.0777-0.0876) | +0.067 |
| XRP | 5m:z8 | ABCD.BEAR | B | 0.0712 | 0.0849 (0.0548-0.0932) | +0.042 |
| XRP | 5m:z8 | ABCD.BULL | A | 0.0777 | 0.0816 (0.0794-0.0821) | -0.026 |
| XRP | 5m:z8 | ABCD.BULL | B | 0.107 | 0.0877 (0.0767-0.0904) | +0.076 |
| XRP | 5m:z8 | ASCTRI | A | 0.219 | 0.184 (0.178-0.194) | +0.027 |
| XRP | 5m:z8 | ASCTRI | B | 0.195 | 0.17 (0.167-0.189) | +0.061 |
| XRP | 5m:z8 | BEARFLAG | A | 0.00274 | 0.0148 (0.012-0.0159) | +0.226 |
| XRP | 5m:z8 | BEARFLAG | B | 0.00274 | 0.00548 (0.00274-0.011) |  |
| XRP | 5m:z8 | BEARPEN | A | 0.00219 | 0.00602 (0.00493-0.00657) | -0.131 |
| XRP | 5m:z8 | BEARPEN | B | 0 | 0.00274 (0-0.00274) |  |
| XRP | 5m:z8 | BROADBOT | A | 0.0148 | 0.0208 (0.0175-0.0268) | +0.103 |
| XRP | 5m:z8 | BROADBOT | B | 0.0274 | 0.0247 (0.0192-0.0301) | -0.035 |
| XRP | 5m:z8 | BROADTOP | A | 0.0181 | 0.0203 (0.0186-0.0252) | -0.066 |
| XRP | 5m:z8 | BROADTOP | B | 0.0192 | 0.0274 (0.0164-0.0301) | -0.201 |
| XRP | 5m:z8 | BULLFLAG | A | 0.00493 | 0.0104 (0.00876-0.0131) | -0.043 |
| XRP | 5m:z8 | BULLFLAG | B | 0 | 0.011 (0.00822-0.011) |  |
| XRP | 5m:z8 | BULLPEN | A | 0.00109 | 0.00274 (0.00274-0.00602) | -0.033 |
| XRP | 5m:z8 | BULLPEN | B | 0.00274 | 0.00274 (0.00274-0.00822) | -0.097 |
| XRP | 5m:z8 | CUP | A | 0.0317 | 0.0334 (0.0307-0.0394) | +0.005 |
| XRP | 5m:z8 | CUP | B | 0.0411 | 0.0247 (0.0247-0.0301) | +0.088 |
| XRP | 5m:z8 | DBOT | A | 0.573 | 0.653 (0.634-0.66) | -0.011 |
| XRP | 5m:z8 | DBOT | B | 0.636 | 0.633 (0.625-0.636) | -0.008 |
| XRP | 5m:z8 | DESCTRI | A | 0.19 | 0.193 (0.188-0.21) | +0.072 |
| XRP | 5m:z8 | DESCTRI | B | 0.181 | 0.216 (0.145-0.222) | +0.033 |
| XRP | 5m:z8 | DTOP | A | 0.624 | 0.638 (0.626-0.658) | +0.026 |
| XRP | 5m:z8 | DTOP | B | 0.584 | 0.625 (0.589-0.663) | +0.006 |
| XRP | 5m:z8 | FALWEDGE | A | 0.212 | 0.264 (0.248-0.29) | +0.052 |
| XRP | 5m:z8 | FALWEDGE | B | 0.255 | 0.258 (0.249-0.269) | -0.078 |
| XRP | 5m:z8 | HARM.BEAR | A | 0.029 | 0.0164 (0.0148-0.0186) | +0.078 |
| XRP | 5m:z8 | HARM.BEAR | B | 0.011 | 0.011 (0.00822-0.011) | +0.148 |
| XRP | 5m:z8 | HARM.BULL | A | 0.0148 | 0.0131 (0.012-0.0148) | -0.088 |
| XRP | 5m:z8 | HARM.BULL | B | 0.0356 | 0.0192 (0.0192-0.0219) | +0.119 |
| XRP | 5m:z8 | HS | A | 0.0958 | 0.0898 (0.0854-0.107) | +0.147 |
| XRP | 5m:z8 | HS | B | 0.0822 | 0.0795 (0.0603-0.101) | +0.015 |
| XRP | 5m:z8 | IHS | A | 0.101 | 0.0876 (0.087-0.0985) | -0.027 |
| XRP | 5m:z8 | IHS | B | 0.107 | 0.0877 (0.0795-0.101) | +0.035 |
| XRP | 5m:z8 | INVCUP | A | 0.0268 | 0.0367 (0.035-0.0394) | +0.008 |
| XRP | 5m:z8 | INVCUP | B | 0.0219 | 0.0329 (0.0274-0.0329) | +0.128 |
| XRP | 5m:z8 | RECT | A | 0.0367 | 0.0564 (0.0454-0.0591) | -0.020 |
| XRP | 5m:z8 | RECT | B | 0.0329 | 0.0603 (0.0301-0.0658) | -0.139 |
| XRP | 5m:z8 | RISWEDGE | A | 0.23 | 0.263 (0.234-0.269) | +0.065 |
| XRP | 5m:z8 | RISWEDGE | B | 0.197 | 0.211 (0.2-0.252) | +0.007 |
| XRP | 5m:z8 | ROUNDBOT | A | 0.092 | 0.162 (0.159-0.163) | +0.144 |
| XRP | 5m:z8 | ROUNDBOT | B | 0.137 | 0.148 (0.137-0.164) | -0.261 |
| XRP | 5m:z8 | ROUNDTOP | A | 0.113 | 0.142 (0.136-0.143) | +0.039 |
| XRP | 5m:z8 | ROUNDTOP | B | 0.118 | 0.148 (0.121-0.167) | -0.014 |
| XRP | 5m:z8 | SYMTRI | A | 0.369 | 0.251 (0.249-0.256) | +0.093 |
| XRP | 5m:z8 | SYMTRI | B | 0.337 | 0.269 (0.263-0.279) | +0.107 |
| XRP | 5m:z8 | TRIBOT | A | 0.0597 | 0.0788 (0.0777-0.087) | -0.003 |
| XRP | 5m:z8 | TRIBOT | B | 0.063 | 0.0795 (0.0767-0.104) | -0.075 |
| XRP | 5m:z8 | TRITOP | A | 0.0569 | 0.0766 (0.0755-0.0903) | -0.042 |
| XRP | 5m:z8 | TRITOP | B | 0.0658 | 0.0822 (0.0603-0.0849) | -0.105 |
| XRP | 60m:K | LMW.BBOT | A | 0.114 | 0.216 (0.2-0.221) | +0.012 |
| XRP | 60m:K | LMW.BBOT | B | 0.145 | 0.203 (0.175-0.211) | +0.011 |
| XRP | 60m:K | LMW.BTOP | A | 0.135 | 0.212 (0.203-0.223) | -0.005 |
| XRP | 60m:K | LMW.BTOP | B | 0.153 | 0.233 (0.225-0.266) | +0.018 |
| XRP | 60m:K | LMW.DBOT | A | 0.0389 | 0.0438 (0.0268-0.0454) | -0.050 |
| XRP | 60m:K | LMW.DBOT | B | 0.0356 | 0.0438 (0.0247-0.0466) | -0.059 |
| XRP | 60m:K | LMW.DTOP | A | 0.0509 | 0.0383 (0.0367-0.0427) | +0.047 |
| XRP | 60m:K | LMW.DTOP | B | 0.0192 | 0.0247 (0.0219-0.0411) | -0.151 |
| XRP | 60m:K | LMW.HS | A | 1.11 | 0.98 (0.978-1.03) | -0.039 |
| XRP | 60m:K | LMW.HS | B | 1.15 | 1.07 (1.05-1.09) | -0.034 |
| XRP | 60m:K | LMW.HS.SWZ | A | 0.0115 | 0.0115 (0.00821-0.0153) | -0.067 |
| XRP | 60m:K | LMW.HS.SWZ | B | 0.0219 | 0.0137 (0.0137-0.0219) | -0.091 |
| XRP | 60m:K | LMW.IHS | A | 1.16 | 0.992 (0.986-0.999) | -0.026 |
| XRP | 60m:K | LMW.IHS | B | 1.18 | 1.13 (1.05-1.15) | -0.040 |
| XRP | 60m:K | LMW.IHS.SWZ | A | 0.0159 | 0.0142 (0.0126-0.0142) | +0.052 |
| XRP | 60m:K | LMW.IHS.SWZ | B | 0.00548 | 0.011 (0.00822-0.0137) | -0.609 |
| XRP | 60m:K | LMW.RBOT | A | 2.46 | 2.14 (2.12-2.15) | -0.004 |
| XRP | 60m:K | LMW.RBOT | B | 2.69 | 2.42 (2.37-2.45) | -0.013 |
| XRP | 60m:K | LMW.RTOP | A | 2.6 | 2.13 (2.09-2.15) | -0.003 |
| XRP | 60m:K | LMW.RTOP | B | 2.7 | 2.4 (2.35-2.58) | +0.003 |
| XRP | 60m:K | LMW.TBOT | A | 0.412 | 0.274 (0.269-0.29) | -0.371 |
| XRP | 60m:K | LMW.TBOT | B | 0.392 | 0.299 (0.282-0.299) | -0.389 |
| XRP | 60m:K | LMW.TTOP | A | 0.418 | 0.277 (0.255-0.278) | -0.383 |
| XRP | 60m:K | LMW.TTOP | B | 0.378 | 0.277 (0.274-0.282) | -0.360 |
| XRP | 60m:z2 | ABCD.BEAR | A | 0.0542 | 0.0542 (0.0427-0.0586) | -0.048 |
| XRP | 60m:z2 | ABCD.BEAR | B | 0.0466 | 0.0548 (0.0438-0.0685) | -0.023 |
| XRP | 60m:z2 | ABCD.BULL | A | 0.046 | 0.0558 (0.0509-0.0629) | -0.112 |
| XRP | 60m:z2 | ABCD.BULL | B | 0.074 | 0.0658 (0.063-0.0795) | +0.101 |
| XRP | 60m:z2 | ASCTRI | A | 0.127 | 0.125 (0.118-0.158) | -0.036 |
| XRP | 60m:z2 | ASCTRI | B | 0.0986 | 0.101 (0.101-0.123) | -0.085 |
| XRP | 60m:z2 | BEARFLAG | A | 0.102 | 0.0974 (0.0931-0.11) | +0.005 |
| XRP | 60m:z2 | BEARFLAG | B | 0.0932 | 0.101 (0.0767-0.112) | +0.020 |
| XRP | 60m:z2 | BEARPEN | A | 0.0361 | 0.0383 (0.0361-0.0389) | -0.049 |
| XRP | 60m:z2 | BEARPEN | B | 0.0301 | 0.0329 (0.0301-0.0384) | +0.142 |
| XRP | 60m:z2 | BROADBOT | A | 0.0186 | 0.0268 (0.0252-0.0285) | +0.190 |
| XRP | 60m:z2 | BROADBOT | B | 0.0274 | 0.0192 (0.0192-0.0329) | -0.052 |
| XRP | 60m:z2 | BROADTOP | A | 0.0186 | 0.0263 (0.0208-0.0312) | +0.162 |
| XRP | 60m:z2 | BROADTOP | B | 0.0164 | 0.0329 (0.0247-0.0384) | +0.456 |
| XRP | 60m:z2 | BULLFLAG | A | 0.0969 | 0.0903 (0.081-0.0974) | -0.003 |
| XRP | 60m:z2 | BULLFLAG | B | 0.0932 | 0.0795 (0.0795-0.0877) | +0.046 |
| XRP | 60m:z2 | BULLPEN | A | 0.046 | 0.029 (0.0279-0.0323) | -0.045 |
| XRP | 60m:z2 | BULLPEN | B | 0.0411 | 0.0274 (0.0247-0.0329) | -0.077 |
| XRP | 60m:z2 | CUP | A | 0.0142 | 0.0219 (0.0164-0.0252) | +0.086 |
| XRP | 60m:z2 | CUP | B | 0.0164 | 0.00822 (0.00274-0.0137) | -0.436 |
| XRP | 60m:z2 | DBOT | A | 0.351 | 0.388 (0.383-0.401) | -0.005 |
| XRP | 60m:z2 | DBOT | B | 0.4 | 0.392 (0.356-0.406) | -0.046 |
| XRP | 60m:z2 | DESCTRI | A | 0.117 | 0.136 (0.125-0.143) | +0.020 |
| XRP | 60m:z2 | DESCTRI | B | 0.0986 | 0.153 (0.129-0.162) | +0.036 |
| XRP | 60m:z2 | DTOP | A | 0.388 | 0.38 (0.364-0.414) | -0.025 |
| XRP | 60m:z2 | DTOP | B | 0.359 | 0.373 (0.329-0.406) | -0.095 |
| XRP | 60m:z2 | FALWEDGE | A | 0.163 | 0.167 (0.159-0.186) | -0.003 |
| XRP | 60m:z2 | FALWEDGE | B | 0.263 | 0.189 (0.178-0.189) | -0.003 |
| XRP | 60m:z2 | HARM.BEAR | A | 0.0115 | 0.00931 (0.00876-0.0104) | +0.047 |
| XRP | 60m:z2 | HARM.BEAR | B | 0.0164 | 0.00548 (0-0.0192) | +0.001 |
| XRP | 60m:z2 | HARM.BULL | A | 0.0104 | 0.0109 (0.00876-0.0109) | -0.148 |
| XRP | 60m:z2 | HARM.BULL | B | 0.00548 | 0.00548 (0.00274-0.011) | -0.382 |
| XRP | 60m:z2 | HS | A | 0.0701 | 0.0651 (0.0608-0.0706) | +0.080 |
| XRP | 60m:z2 | HS | B | 0.0685 | 0.0521 (0.0466-0.0685) | +0.090 |
| XRP | 60m:z2 | IHS | A | 0.0684 | 0.0635 (0.0635-0.069) | -0.002 |
| XRP | 60m:z2 | IHS | B | 0.0712 | 0.074 (0.0603-0.0767) | -0.017 |
| XRP | 60m:z2 | INVCUP | A | 0.0164 | 0.017 (0.0159-0.0181) | +0.098 |
| XRP | 60m:z2 | INVCUP | B | 0.0137 | 0.0137 (0.011-0.0192) | -0.054 |
| XRP | 60m:z2 | RECT | A | 0.0203 | 0.0443 (0.04-0.0454) | +0.214 |
| XRP | 60m:z2 | RECT | B | 0.0247 | 0.0521 (0.0356-0.0575) | -0.273 |
| XRP | 60m:z2 | RISWEDGE | A | 0.171 | 0.188 (0.166-0.195) | +0.037 |
| XRP | 60m:z2 | RISWEDGE | B | 0.173 | 0.178 (0.142-0.227) | +0.055 |
| XRP | 60m:z2 | ROUNDBOT | A | 0.0208 | 0.0602 (0.0564-0.0608) | -0.048 |
| XRP | 60m:z2 | ROUNDBOT | B | 0.0493 | 0.0384 (0.0356-0.0548) | +0.163 |
| XRP | 60m:z2 | ROUNDTOP | A | 0.0367 | 0.0449 (0.0411-0.046) | +0.039 |
| XRP | 60m:z2 | ROUNDTOP | B | 0.0767 | 0.0411 (0.0301-0.0685) | +0.034 |
| XRP | 60m:z2 | SYMTRI | A | 0.192 | 0.152 (0.148-0.159) | +0.093 |
| XRP | 60m:z2 | SYMTRI | B | 0.148 | 0.14 (0.137-0.156) | +0.025 |
| XRP | 60m:z2 | TRIBOT | A | 0.0372 | 0.0629 (0.0613-0.0635) | +0.094 |
| XRP | 60m:z2 | TRIBOT | B | 0.0411 | 0.0767 (0.074-0.0904) | -0.002 |
| XRP | 60m:z2 | TRITOP | A | 0.0432 | 0.0569 (0.0476-0.069) | +0.072 |
| XRP | 60m:z2 | TRITOP | B | 0.0411 | 0.063 (0.0521-0.074) | -0.221 |
| XRP | 60m:z4 | ABCD.BEAR | A | 0.0219 | 0.0219 (0.0203-0.023) | -0.068 |
| XRP | 60m:z4 | ABCD.BEAR | B | 0.0192 | 0.0192 (0.011-0.0301) | -0.068 |
| XRP | 60m:z4 | ABCD.BULL | A | 0.012 | 0.0175 (0.0153-0.0219) | +0.073 |
| XRP | 60m:z4 | ABCD.BULL | B | 0.0274 | 0.0274 (0.011-0.0356) | +0.396 |
| XRP | 60m:z4 | ASCTRI | A | 0.0421 | 0.0476 (0.0378-0.0547) | +0.024 |
| XRP | 60m:z4 | ASCTRI | B | 0.0548 | 0.0466 (0.0466-0.0548) | +0.070 |
| XRP | 60m:z4 | BEARFLAG | A | 0.0148 | 0.0181 (0.017-0.0203) | +0.018 |
| XRP | 60m:z4 | BEARFLAG | B | 0 | 0.0164 (0.00822-0.0274) |  |
| XRP | 60m:z4 | BEARPEN | A | 0.00931 | 0.00547 (0.00438-0.00876) | +0.028 |
| XRP | 60m:z4 | BEARPEN | B | 0 | 0.00548 (0.00548-0.0137) |  |
| XRP | 60m:z4 | BROADBOT | A | 0.00328 | 0.00766 (0.00547-0.0104) | +0.408 |
| XRP | 60m:z4 | BROADBOT | B | 0.00548 | 0.00822 (0.00274-0.00822) | +0.466 |
| XRP | 60m:z4 | BROADTOP | A | 0.00547 | 0.00602 (0.00547-0.0115) | -0.275 |
| XRP | 60m:z4 | BROADTOP | B | 0.00548 | 0.00548 (0.00274-0.011) | -0.519 |
| XRP | 60m:z4 | BULLFLAG | A | 0.0109 | 0.0159 (0.0148-0.0164) | -0.060 |
| XRP | 60m:z4 | BULLFLAG | B | 0.0247 | 0.0192 (0.0137-0.0192) | +0.001 |
| XRP | 60m:z4 | BULLPEN | A | 0.00876 | 0.00602 (0.00328-0.00602) | -0.100 |
| XRP | 60m:z4 | BULLPEN | B | 0.011 | 0.00548 (0.00274-0.00822) | -0.183 |
| XRP | 60m:z4 | CUP | A | 0.00712 | 0.00766 (0.00602-0.00821) | -0.027 |
| XRP | 60m:z4 | CUP | B | 0.011 | 0.011 (0.00548-0.0137) | -0.323 |
| XRP | 60m:z4 | DBOT | A | 0.145 | 0.158 (0.143-0.162) | +0.032 |
| XRP | 60m:z4 | DBOT | B | 0.148 | 0.153 (0.153-0.186) | +0.146 |
| XRP | 60m:z4 | DESCTRI | A | 0.0416 | 0.0438 (0.0416-0.0536) | +0.146 |
| XRP | 60m:z4 | DESCTRI | B | 0.0411 | 0.0548 (0.0438-0.0575) | -0.145 |
| XRP | 60m:z4 | DTOP | A | 0.146 | 0.164 (0.149-0.166) | +0.014 |
| XRP | 60m:z4 | DTOP | B | 0.137 | 0.164 (0.164-0.164) | +0.098 |
| XRP | 60m:z4 | FALWEDGE | A | 0.0553 | 0.0695 (0.0432-0.0706) | -0.018 |
| XRP | 60m:z4 | FALWEDGE | B | 0.0822 | 0.0795 (0.0548-0.0932) | -0.013 |
| XRP | 60m:z4 | HARM.BEAR | A | 0.00219 | 0.00328 (0.00274-0.00547) | +0.104 |
| XRP | 60m:z4 | HARM.BEAR | B | 0.00274 | 0.00822 (0-0.011) | +0.600 |
| XRP | 60m:z4 | HARM.BULL | A | 0.00438 | 0.00328 (0.00164-0.00657) | +0.027 |
| XRP | 60m:z4 | HARM.BULL | B | 0.00548 | 0.00822 (0.00274-0.00822) | +0.827 |
| XRP | 60m:z4 | HS | A | 0.0235 | 0.0257 (0.0192-0.0263) | +0.068 |
| XRP | 60m:z4 | HS | B | 0.0219 | 0.0192 (0.0164-0.0329) | -0.387 |
| XRP | 60m:z4 | IHS | A | 0.0213 | 0.0203 (0.0159-0.0268) | +0.061 |
| XRP | 60m:z4 | IHS | B | 0.0192 | 0.0192 (0.0164-0.0219) | +0.142 |
| XRP | 60m:z4 | INVCUP | A | 0.00657 | 0.00657 (0.00493-0.00766) | -0.315 |
| XRP | 60m:z4 | INVCUP | B | 0.00548 | 0.00548 (0.00274-0.011) | -0.383 |
| XRP | 60m:z4 | RECT | A | 0.0115 | 0.0192 (0.00876-0.0203) | +0.197 |
| XRP | 60m:z4 | RECT | B | 0.00548 | 0.0137 (0.011-0.0192) |  |
| XRP | 60m:z4 | RISWEDGE | A | 0.0619 | 0.0635 (0.0591-0.069) | +0.067 |
| XRP | 60m:z4 | RISWEDGE | B | 0.0493 | 0.0548 (0.0548-0.0712) | -0.136 |
| XRP | 60m:z4 | ROUNDBOT | A | 0.0246 | 0.0416 (0.0361-0.0465) | +0.115 |
| XRP | 60m:z4 | ROUNDBOT | B | 0.0438 | 0.0411 (0.0301-0.0658) | -0.358 |
| XRP | 60m:z4 | ROUNDTOP | A | 0.0274 | 0.0421 (0.04-0.0443) | -0.291 |
| XRP | 60m:z4 | ROUNDTOP | B | 0.0329 | 0.0356 (0.0356-0.0493) |  |
| XRP | 60m:z4 | SYMTRI | A | 0.0733 | 0.0575 (0.0558-0.0586) | +0.065 |
| XRP | 60m:z4 | SYMTRI | B | 0.0767 | 0.0603 (0.0466-0.063) | +0.151 |
| XRP | 60m:z4 | TRIBOT | A | 0.00876 | 0.0197 (0.0164-0.0252) | +0.202 |
| XRP | 60m:z4 | TRIBOT | B | 0.0137 | 0.0219 (0.0192-0.0247) | +0.098 |
| XRP | 60m:z4 | TRITOP | A | 0.0153 | 0.0197 (0.0153-0.0312) | -0.148 |
| XRP | 60m:z4 | TRITOP | B | 0.011 | 0.0137 (0.00822-0.0164) | -0.155 |
| XRP | 60m:z8 | ABCD.BEAR | A | 0.00766 | 0.00602 (0.00547-0.00657) | +0.284 |
| XRP | 60m:z8 | ABCD.BEAR | B | 0.00822 | 0.00274 (0-0.00548) | +0.480 |
| XRP | 60m:z8 | ABCD.BULL | A | 0.00602 | 0.00438 (0.00219-0.00547) | +0.120 |
| XRP | 60m:z8 | ABCD.BULL | B | 0.00822 | 0.00822 (0.00822-0.011) | +0.707 |
| XRP | 60m:z8 | ASCTRI | A | 0.00931 | 0.0126 (0.0126-0.0153) | -0.115 |
| XRP | 60m:z8 | ASCTRI | B | 0.011 | 0.011 (0.00548-0.0219) | -0.345 |
| XRP | 60m:z8 | BEARFLAG | A | 0 | 0.00109 (0.000547-0.00219) |  |
| XRP | 60m:z8 | BEARFLAG | B | 0 | 0 (0-0.00274) |  |
| XRP | 60m:z8 | BEARPEN | A | 0.000547 | 0.000547 (0-0.00109) | -0.155 |
| XRP | 60m:z8 | BEARPEN | B | 0 | 0 (0-0) |  |
| XRP | 60m:z8 | BROADBOT | A | 0.00164 | 0.00109 (0.00109-0.00274) | -0.563 |
| XRP | 60m:z8 | BROADBOT | B | 0.00548 | 0 (0-0.00274) |  |
| XRP | 60m:z8 | BROADTOP | A | 0.000547 | 0.00164 (0.00109-0.00164) |  |
| XRP | 60m:z8 | BROADTOP | B | 0.00548 | 0.00274 (0-0.00548) |  |
| XRP | 60m:z8 | BULLFLAG | A | 0.00109 | 0.000547 (0-0.00164) | -0.076 |
| XRP | 60m:z8 | BULLFLAG | B | 0.00822 | 0.00274 (0-0.00274) | -0.041 |
| XRP | 60m:z8 | BULLPEN | A | 0.000547 | 0.000547 (0-0.000547) | -0.196 |
| XRP | 60m:z8 | BULLPEN | B | 0.00274 | 0 (0-0) | -0.032 |
| XRP | 60m:z8 | CUP | A | 0.00164 | 0.00274 (0.00219-0.00328) | +0.175 |
| XRP | 60m:z8 | CUP | B | 0 | 0.00274 (0-0.00548) |  |
| XRP | 60m:z8 | DBOT | A | 0.0421 | 0.0498 (0.0487-0.0542) | -0.064 |
| XRP | 60m:z8 | DBOT | B | 0.0548 | 0.0521 (0.0466-0.063) | -0.145 |
| XRP | 60m:z8 | DESCTRI | A | 0.017 | 0.012 (0.0115-0.0126) | +0.201 |
| XRP | 60m:z8 | DESCTRI | B | 0.0247 | 0.00822 (0.00548-0.011) | -0.287 |
| XRP | 60m:z8 | DTOP | A | 0.0389 | 0.0493 (0.0476-0.0558) | -0.082 |
| XRP | 60m:z8 | DTOP | B | 0.0466 | 0.0438 (0.0438-0.063) | -0.042 |
| XRP | 60m:z8 | FALWEDGE | A | 0.017 | 0.0213 (0.0153-0.0235) | +0.358 |
| XRP | 60m:z8 | FALWEDGE | B | 0.0164 | 0.0301 (0.0192-0.0329) | +0.015 |
| XRP | 60m:z8 | HARM.BEAR | A | 0.00164 | 0.000547 (0.000547-0.00164) | -0.320 |
| XRP | 60m:z8 | HARM.BEAR | B | 0 | 0 (0-0.00274) |  |
| XRP | 60m:z8 | HARM.BULL | A | 0.00219 | 0.000547 (0.000547-0.00109) | -0.112 |
| XRP | 60m:z8 | HARM.BULL | B | 0 | 0.00274 (0-0.00548) |  |
| XRP | 60m:z8 | HS | A | 0.00876 | 0.00657 (0.00602-0.00876) | +0.110 |
| XRP | 60m:z8 | HS | B | 0.011 | 0.011 (0.00822-0.011) | +0.298 |
| XRP | 60m:z8 | IHS | A | 0.00602 | 0.00602 (0.00547-0.00766) | +0.161 |
| XRP | 60m:z8 | IHS | B | 0.0164 | 0.00274 (0.00274-0.00822) | +0.261 |
| XRP | 60m:z8 | INVCUP | A | 0.00274 | 0.00383 (0.00164-0.00602) | +0.677 |
| XRP | 60m:z8 | INVCUP | B | 0.00274 | 0.00548 (0-0.00822) |  |
| XRP | 60m:z8 | RECT | A | 0.00164 | 0.00219 (0.00164-0.00602) | -0.341 |
| XRP | 60m:z8 | RECT | B | 0.00274 | 0.00274 (0.00274-0.00274) |  |
| XRP | 60m:z8 | RISWEDGE | A | 0.0104 | 0.0148 (0.0137-0.0181) | -0.206 |
| XRP | 60m:z8 | RISWEDGE | B | 0.00822 | 0.0137 (0.0137-0.0219) | +0.150 |
| XRP | 60m:z8 | ROUNDBOT | A | 0.0104 | 0.0131 (0.012-0.0175) |  |
| XRP | 60m:z8 | ROUNDBOT | B | 0.00274 | 0.0164 (0.011-0.0192) |  |
| XRP | 60m:z8 | ROUNDTOP | A | 0.00493 | 0.0109 (0.00766-0.0115) | +0.582 |
| XRP | 60m:z8 | ROUNDTOP | B | 0.0164 | 0.00274 (0-0.011) | -0.389 |
| XRP | 60m:z8 | SYMTRI | A | 0.0246 | 0.0192 (0.0126-0.0197) | -0.120 |
| XRP | 60m:z8 | SYMTRI | B | 0.0301 | 0.0137 (0.00548-0.0247) | -0.195 |
| XRP | 60m:z8 | TRIBOT | A | 0.00493 | 0.00493 (0.00328-0.00712) | +0.038 |
| XRP | 60m:z8 | TRIBOT | B | 0.011 | 0.00274 (0-0.00274) |  |
| XRP | 60m:z8 | TRITOP | A | 0.00328 | 0.00602 (0.00328-0.00985) | -0.346 |
| XRP | 60m:z8 | TRITOP | B | 0 | 0.00548 (0-0.00548) |  |

### Singles lists (B heat, at most 3 rows per pattern)

#### BTC, 1 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:C-MEDPRICE sign=above 0 & 240m:CHART.z2.STRUCT=up | 0.36 | 1.70 | 241 | 409 |  | rep |
| 1m:C-MEDPRICE sign=below 0 & 240m:CHART.z8.STRUCT=expanding | -1.10 | -1.93 | 203 | 393 |  | hot,rep |
| 1m:C-AVGPRICE sign=below 0 & 240m:CHART.z8.STRUCT=expanding | -1.11 | -1.88 | 204 | 382 |  | hot,rep |
| 1m:BOP sign=above 0 & 240m:CHART.z4.STRUCT=down | 0.01 | 1.57 | 243 | 382 |  | rep |
| 1m:IBS=very high & 60m:CHART.z8.STRUCT=down | 2.50 | 4.05 | 94.1 | 381 |  | hot,rep |
| 1m:IBS=very high & 240m:CHART.z8.STRUCT=down | 2.01 | 3.32 | 114 | 380 |  | hot,rep |
| 1m:C-AVGPRICE sign=above 0 & 240m:CHART.z2.STRUCT=up | 0.47 | 1.55 | 240 | 372 |  | hot,rep |
| 1m:C-AVGPRICE sign=below 0 & 5m:CHART.z8.STRUCT=up | -0.05 | -1.59 | 230 | 365 |  | rep |
| 1m:C-MEDPRICE sign=above 0 & 15m:CHART.K.BIAS=mixed | 0.17 | 1.54 | 236 | 362 |  | rep |
| 1m:IBS=very high & 240m:CHART.z4.STRUCT=down | 2.49 | 4.39 | 81.7 | 359 |  | hot,rep |
| 1m:BOP sign=below 0 & 240m:CHART.z8.STRUCT=expanding | -1.12 | -1.60 | 204 | 326 |  | hot,rep |
| 1m:CORRELcv30 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.87 | 0.80 | 387 | 311 |  | hot,rep |
| 1m:BOP sign=below 0 & 5m:CHART.z8.STRUCT=up | -0.12 | -1.34 | 231 | 310 |  | rep |
| 15m:C-MEDPRICE sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.02 | 0.75 | 371 | 279 |  | hot,rep |
| 15m:C-AVGPRICE sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.95 | 0.75 | 371 | 277 |  | hot,rep |
| 1m:SWAK_2PHP20 sign=below 0 & 60m:CHART.z8.STRUCT=down | -0.33 | -0.92 | 290 | 268 |  | hot,rep |
| 1m:SI sign=above 0 & 240m:CHART.z2.STRUCT=up | 0.46 | 1.10 | 240 | 263 |  | hot,rep |
| 1m:SWAK_2PHP20 sign=above 0 & 15m:CHART.z2.STRUCT=down | 0.25 | 1.17 | 223 | 260 |  | rep |
| 1m:SWAK_2PHP20 sign=below 0 & 5m:CHART.z8.STRUCT=up | -0.21 | -1.11 | 230 | 256 |  | rep |
| 1m:SI sign=above 0 & 15m:CHART.z2.STRUCT=down | 0.01 | 1.09 | 232 | 253 |  | rep |
| 1m:CDL:CLOSINGMARUBOZU=bull & 240m:CHART.z2.STRUCT=up | 1.88 | 3.55 | 69.3 | 246 |  | hot,rep |
| 1m:SI sign=above 0 & 15m:CHART.K.BIAS=mixed | 0.16 | 0.99 | 235 | 233 |  | rep |
| 1m:AD sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.76 | 0.61 | 378 | 232 |  | hot,rep |
| 1m:CDL:MARUBOZU=bull & 240m:CHART.z4.STRUCT=down | 1.63 | 4.23 | 54.5 | 230 |  | hot,rep |
| 1m:OBV sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.95 | 0.61 | 374 | 229 |  | hot,rep |
| 1m:DIdiff14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.26 | 0.62 | 369 | 228 |  | hot,rep |
| 1m:BOP=low & 60m:CHART.z8.STRUCT=down | -1.69 | -2.91 | 77.7 | 226 |  | hot,rep |
| 1m:C-EMA200 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.12 | 0.62 | 361 | 225 |  | hot,rep |
| 1m:CDL:CLOSINGMARUBOZU=bull & 15m:CHART.K.BIAS=mixed | 1.71 | 3.19 | 70 | 223 |  | hot,rep |
| 1m:FOSC5 sign=above 0 & 240m:CHART.z4.STRUCT=down | 0.13 | 0.90 | 243 | 220 |  | rep |
| 1m:BOP=high & 240m:CHART.z2.STRUCT=up | 3.13 | 3.24 | 67.8 | 220 |  | hot,rep |
| 1m:CCI20 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.04 | 0.58 | 371 | 217 |  | hot,rep |
| 1m:CORRELcv30 sign=below 0 & 15m:CHART.z2.STRUCT=down | 0.70 | 0.89 | 243 | 217 |  | hot,rep |
| 15m:C-MIDPRICE14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.72 | 0.62 | 350 | 216 |  | hot,rep |
| 1m:CORRELcv30 sign=below 0 & 5m:CHART.z4.STRUCT=down | 0.61 | 0.83 | 258 | 214 |  | hot,rep |
| 1m:HT_INPHASE sign=below 0 & 15m:CHART.z2.STRUCT=down | 0.89 | 0.96 | 222 | 214 |  | hot,rep |
| 1m:BOP=low & 60m:CHART.z2.STRUCT=up | -1.98 | -3.24 | 65.5 | 212 |  | hot,rep |
| 1m:CDL:CLOSINGMARUBOZU=bull & 240m:CHART.z2.STRUCT=up | 1.75 | 3.60 | 58.2 | 209 |  | hot,rep |
| 1m:C-LINEARREG14 sign=above 0 & 15m:CHART.z2.STRUCT=down | 0.11 | 0.91 | 221 | 200 |  | rep |
| 1m:CDL:MARUBOZU=bull & 15m:CHART.K.BIAS=mixed | 2.71 | 3.54 | 56.1 | 198 |  | hot,rep |

#### BTC, 15 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.98 | 2.07 | 40.8 | 84.7 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -6.12 | -3.75 | 21.3 | 79.8 |  | hot,rep |
| 1m:AROONdn14=very high & 240m:CHART.z8.STRUCT=down | 3.43 | 2.33 | 31.9 | 74.4 |  | hot,rep |
| 1m:C-MCGD14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.62 | 1.77 | 41.2 | 72.9 |  | hot,rep |
| 1m:C-MIDPOINT14=low & 240m:CHART.z8.STRUCT=down | 3.57 | 2.80 | 25.8 | 72.3 |  | hot,rep |
| 1m:AD sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.90 | -2.34 | 30.5 | 71.3 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z2.STRUCT=up | 2.97 | 2.67 | 26.5 | 70.8 |  | hot,rep |
| 1m:ADOSC sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.07 | -2.42 | 29.3 | 70.8 |  | hot,rep |
| 1m:CCI20 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.45 | 1.67 | 42.3 | 70.7 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.15 | 2.66 | 26.4 | 70.3 |  | hot,rep |
| 1m:AROONOSC14 sign=above 0 & 15m:CHART.z2.STRUCT=up | -2.79 | -2.52 | 27.9 | 70.3 |  | hot,rep |
| 1m:OBV sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.92 | 1.55 | 45.4 | 70.2 |  | hot,rep |
| 1m:PVT sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.72 | -2.25 | 30.4 | 68.5 |  | hot,rep |
| 1m:PVT sign=below 0 & 5m:CHART.z4.STRUCT=down | 2.20 | 2.28 | 29.7 | 67.8 |  | hot,rep |
| 1m:ASI sign=above 0 & 15m:CHART.z2.STRUCT=up | -2.40 | -2.25 | 29.8 | 67.2 |  | hot,rep |
| 1m:PVT sign=below 0 & 60m:CHART.z8.STRUCT=down | 1.69 | 1.87 | 35.7 | 66.7 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 15m:CHART.z2.STRUCT=up | -3.31 | -2.47 | 26.9 | 66.7 |  | hot,rep |
| 1m:PVI sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.47 | -2.45 | 27 | 66 |  | hot,rep |
| 1m:PVI sign=below 0 & 60m:CHART.z8.STRUCT=down | 1.75 | 1.89 | 34.8 | 65.9 |  | hot,rep |
| 1m:PVI sign=below 0 & 5m:CHART.z2.STRUCT=down | 3.41 | 2.27 | 28.9 | 65.5 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.21 | -2.62 | 25 | 65.5 |  | hot,rep |
| 1m:STOCHK14=low & 240m:CHART.z8.STRUCT=down | 3.36 | 2.65 | 24.7 | 65.3 |  | hot,rep |
| FLOW:TB15=low & 240m:CHART.z8.STRUCT=down | 2.90 | 2.73 | 23.9 | 65.3 |  | hot,rep |
| 1m:ASI sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.30 | -2.36 | 27.6 | 65.2 |  | hot,rep |
| 1m:AD sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.53 | 1.42 | 45.7 | 65.1 |  | hot,rep |
| 1m:CMOU14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.92 | -2.22 | 29.3 | 65.1 |  | hot,rep |
| 1m:OBV sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.77 | 2.19 | 29.7 | 64.8 |  | hot,rep |
| 1m:ASI sign=below 0 & 5m:CHART.z4.STRUCT=down | 2.19 | 2.18 | 29.5 | 64.3 |  | hot,rep |
| 1m:AROONOSC14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.97 | -2.25 | 28.5 | 64 |  | hot,rep |
| 1m:AROONdn14=very high & 240m:CHART.z8.STRUCT=down | 3.24 | 2.12 | 30.1 | 63.9 |  | hot,rep |
| 1m:WT1 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.61 | 1.71 | 37.3 | 63.8 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.13 | -2.61 | 24.3 | 63.5 |  | hot,rep |
| FLOW:TB5=low & 240m:CHART.z8.STRUCT=down | 1.93 | 1.88 | 33.7 | 63.4 |  | hot,rep |
| 1m:EMA9>EMA21=below & 240m:CHART.z8.STRUCT=down | 2.64 | 1.74 | 36.4 | 63.4 |  | hot,rep |
| 1m:ADOSC sign=below 0 & 60m:CHART.z8.STRUCT=down | 1.19 | 1.83 | 34.6 | 63.3 |  | hot,rep |
| 1m:CCI14=low & 240m:CHART.z8.STRUCT=down | 3.48 | 2.50 | 25.3 | 63.2 |  | hot,rep |
| 1m:VORTEXdiff14=low & 240m:CHART.z8.STRUCT=down | 3.17 | 2.79 | 22.6 | 63 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 15m:CHART.z2.STRUCT=up | -2.11 | -2.40 | 26.1 | 62.8 |  | hot,rep |
| 1m:CCI20 sign=above 0 & 15m:CHART.z2.STRUCT=up | -2.84 | -2.24 | 27.9 | 62.6 |  | hot,rep |
| 1m:SQZMOM sign=above 0 & 15m:CHART.z2.STRUCT=up | -2.86 | -2.40 | 26 | 62.4 |  | hot,rep |

#### BTC, 240 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| FLOW:TB5=very high & 15m:CHART.z2.STRUCT=up | -4.47 | -9.22 | 2.57 | 23.7 |  | hot,rep |
| FLOW:TB15=high & 5m:CHART.z4.STRUCT=up | -5.01 | -8.77 | 2.62 | 23 |  | hot,rep |
| FLOW:TB5=very high & 5m:CHART.z4.STRUCT=up | -3.37 | -9.27 | 2.47 | 22.9 |  | rep |
| 1m:PDI14=high & 5m:CHART.z4.STRUCT=up | -3.01 | -8.53 | 2.56 | 21.9 |  | hot,rep |
| FLOW:TB15=very high & 15m:CHART.z2.STRUCT=up | -4.54 | -9.89 | 2.2 | 21.8 |  | hot,rep |
| OI:PxQuad60=long liquidation & 5m:CHART.z4.STRUCT=down | 3.67 | 8.60 | 2.53 | 21.7 |  | hot,rep |
| FLOW:TB15=high & 5m:CHART.z4.STRUCT=up | -3.81 | -8.22 | 2.61 | 21.5 |  | hot,rep |
| FLOW:TB5=very high & 5m:CHART.z4.STRUCT=up | -2.59 | -8.49 | 2.46 | 20.9 |  | rep |
| 1m:PERCENTB20/2=high & 5m:CHART.z4.STRUCT=up | -3.80 | -7.65 | 2.72 | 20.8 |  | hot,rep |
| 1m:PDI14=high & 5m:CHART.z4.STRUCT=up | -3.34 | -7.93 | 2.55 | 20.2 |  | hot,rep |
| 1m:SWAK_HP20=high & 5m:CHART.z4.STRUCT=up | -3.59 | -7.02 | 2.8 | 19.6 |  | hot,rep |
| 1m:CCI14=high & 5m:CHART.z4.STRUCT=up | -3.59 | -7.00 | 2.75 | 19.3 |  | hot,rep |
| 15m:C-FRAMA16 sign=below 0 & 5m:CHART.z4.STRUCT=down | 5.45 | 6.91 | 2.74 | 18.9 |  | hot,rep |
| 1m:HAbody=high & 5m:CHART.z4.STRUCT=up | -3.12 | -6.65 | 2.82 | 18.7 |  | hot,rep |
| 1m:PERCENTB20/2=high & 5m:CHART.z4.STRUCT=up | -3.58 | -6.90 | 2.71 | 18.7 |  | hot,rep |
| 5m:PVI sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.31 | -7.15 | 2.58 | 18.5 |  | hot,rep |
| 1m:CCI14=high & 5m:CHART.z4.STRUCT=up | -3.44 | -6.69 | 2.75 | 18.4 |  | hot,rep |
| 1m:TakerBuy=very high & 15m:CHART.z2.STRUCT=up | -3.03 | -6.73 | 2.71 | 18.3 | 0.0276 | rep,>twins |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.09 | -6.20 | 2.87 | 17.8 |  | hot,rep |
| 1m:SWAK_HP20=high & 5m:CHART.z4.STRUCT=up | -3.39 | -6.35 | 2.8 | 17.7 |  | hot,rep |
| 5m:PVI sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.34 | -6.51 | 2.7 | 17.6 |  | hot,rep |
| 1m:WILLR14=high & 5m:CHART.z4.STRUCT=up | -2.96 | -6.41 | 2.73 | 17.5 |  | hot,rep |
| 1m:AROONdn25=very high & 5m:CHART.z4.STRUCT=down | 4.35 | 6.02 | 2.89 | 17.4 |  | hot,rep |
| 1m:TakerBuy=very high & 15m:CHART.z2.STRUCT=up | -3.20 | -6.41 | 2.71 | 17.4 | -0.00302 | hot,rep,>twins |
| 1m:MAMA>FAMA=above & 5m:CHART.z4.STRUCT=up | -3.07 | -6.17 | 2.81 | 17.3 |  | hot,rep |
| 1m:CORRELcv30 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.68 | 5.72 | 3.03 | 17.3 |  | hot,rep |
| 1m:PVI sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.01 | -5.99 | 2.89 | 17.3 |  | hot,rep |
| 1m:EMA9>EMA21=above & 5m:CHART.z4.STRUCT=up | -3.18 | -6.15 | 2.81 | 17.3 |  | hot,rep |
| 1m:WILLR14=high & 5m:CHART.z4.STRUCT=up | -3.01 | -6.30 | 2.73 | 17.2 |  | hot,rep |
| 1m:HAbody=high & 5m:CHART.z4.STRUCT=up | -3.02 | -6.07 | 2.81 | 17.1 |  | hot,rep |
| 1m:ASI sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.69 | -5.90 | 2.89 | 17 |  | hot,rep |
| 5m:C-TEMA21 sign=below 0 & 5m:CHART.z2.BIAS=down 2+ | 4.18 | 6.41 | 2.62 | 16.8 |  | hot,rep |
| 1m:AROONdn25=very high & 5m:CHART.z4.STRUCT=down | 4.08 | 5.80 | 2.88 | 16.7 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.82 | -5.86 | 2.85 | 16.7 |  | hot,rep |
| 5m:C-EMA200 sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.97 | -6.69 | 2.49 | 16.7 |  | hot,rep |
| 15m:C-EMA50 sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.08 | -6.66 | 2.5 | 16.7 |  | hot,rep |
| 1m:KVO sign=below 0 & 5m:CHART.z2.BIAS=down 2+ | 4.50 | 6.29 | 2.64 | 16.6 |  | hot,rep |
| 1m:TRANGE=high & 5m:CHART.z4.STRUCT=up | -1.99 | -5.79 | 2.86 | 16.6 |  | hot,rep |
| 1m:DIdiff14=very low & 240m:CHART.z8.STRUCT=down | 4.71 | 7.33 | 2.24 | 16.4 |  | rep |
| 1m:EMA9>EMA21=below & 5m:CHART.z4.STRUCT=down | 3.13 | 5.43 | 3 | 16.3 |  | hot,rep |

#### BTC, 30 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:PERCENTB20/2=low & 240m:CHART.z8.STRUCT=down | 3.69 | 3.35 | 16.8 | 56.5 |  | hot,rep |
| 1m:STOCHK14=low & 240m:CHART.z8.STRUCT=down | 2.49 | 3.08 | 17.7 | 54.6 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.55 | 2.30 | 23.6 | 54.2 |  | hot,rep |
| 1m:AROONdn14=very high & 240m:CHART.z8.STRUCT=down | 2.78 | 2.53 | 21.2 | 53.7 |  | hot,rep |
| 1m:STOCHK14=low & 60m:CHART.z8.STRUCT=down | 2.72 | 3.79 | 14.1 | 53.2 |  | hot,rep |
| FLOW:TB15=low & 240m:CHART.z8.STRUCT=down | 3.27 | 3.23 | 16.4 | 53 |  | hot,rep |
| 1m:ADOSC sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.79 | -3.00 | 17.5 | 52.7 |  | hot,rep |
| 1m:PERCENTB20/2=low & 240m:CHART.z8.STRUCT=down | 3.36 | 3.18 | 16.5 | 52.6 |  | hot,rep |
| 1m:CCI14=high & 5m:CHART.z4.STRUCT=up | -4.61 | -4.59 | 11.4 | 52.3 |  | hot,rep |
| FLOW:TB5=low & 240m:CHART.z8.STRUCT=down | 1.89 | 2.46 | 21.2 | 52.2 |  | hot,rep |
| 1m:CCI14=low & 240m:CHART.z8.STRUCT=down | 2.92 | 2.79 | 18.7 | 52.1 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.88 | -3.08 | 16.7 | 51.5 |  | hot,rep |
| 1m:VORTEXdiff14=low & 240m:CHART.z8.STRUCT=down | 2.61 | 3.15 | 16.2 | 51.1 |  | hot,rep |
| X:Breadth15=3 down & 5m:CHART.z4.STRUCT=down | 2.86 | 3.50 | 14.5 | 50.9 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.39 | -3.52 | 14.4 | 50.8 |  | hot,rep |
| 1m:AD sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.64 | -2.83 | 17.9 | 50.6 |  | hot,rep |
| 1m:PVT sign=below 0 & 5m:CHART.z4.STRUCT=down | 2.46 | 3.09 | 16.4 | 50.5 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.43 | 3.23 | 15.6 | 50.3 |  | hot,rep |
| 1m:AROONup25=very high & 15m:CHART.z2.STRUCT=up | -5.90 | -4.52 | 11.1 | 50 | 1.83 | hot,rep,>twins |
| FLOW:TB5=low & 5m:CHART.z2.STRUCT=down | 4.67 | 3.48 | 14.3 | 49.6 |  | hot,rep |
| 1m:PVT sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.34 | -2.78 | 17.9 | 49.6 |  | hot,rep |
| 1m:VORTEXdiff14=low & 240m:CHART.z8.STRUCT=down | 2.82 | 3.18 | 15.5 | 49.4 |  | hot,rep |
| 1m:AROONdn25=very high & 5m:CHART.z4.STRUCT=down | 5.33 | 4.53 | 10.8 | 49.1 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 15m:CHART.z2.STRUCT=up | -2.42 | -3.17 | 15.5 | 49.1 |  | hot,rep |
| 1m:CCI14=low & 240m:CHART.z8.STRUCT=down | 2.86 | 2.66 | 18.4 | 49.1 |  | hot,rep |
| 1m:AROONup14=very high & 15m:CHART.z2.STRUCT=up | -4.14 | -3.52 | 13.9 | 48.9 | 14.1 | hot,rep,>twins |
| 1m:AROONup14=very high & 15m:CHART.z2.STRUCT=up | -4.56 | -3.44 | 14.1 | 48.6 | -6.36 | hot,rep,>twins |
| 1m:HAbody=high & 5m:CHART.z4.STRUCT=up | -3.80 | -3.55 | 13.5 | 48.2 |  | hot,rep |
| 1m:WT1 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.30 | 2.19 | 21.9 | 48.1 |  | hot,rep |
| 1m:PDI14=high & 5m:CHART.z4.STRUCT=up | -4.22 | -5.21 | 9.22 | 48.1 |  | hot,rep |
| 1m:OBV sign=below 0 & 5m:CHART.z4.STRUCT=down | 2.02 | 2.92 | 16.4 | 48 |  | hot,rep |
| 1m:SQZMOM sign=above 0 & 15m:CHART.z2.STRUCT=up | -3.00 | -3.07 | 15.6 | 47.8 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.69 | -3.24 | 14.8 | 47.8 |  | hot,rep |
| 1m:SWAK_HP20=high & 5m:CHART.z4.STRUCT=up | -4.34 | -3.70 | 12.9 | 47.7 |  | hot,rep |
| 1m:CCI20 sign=above 0 & 15m:CHART.z2.STRUCT=up | -3.35 | -2.94 | 16.2 | 47.6 |  | hot,rep |
| 1m:AROONOSC14 sign=above 0 & 15m:CHART.z2.STRUCT=up | -3.06 | -2.94 | 16.1 | 47.5 |  | hot,rep |
| 1m:C-MCGD14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.46 | 2.05 | 23.2 | 47.5 |  | hot,rep |
| 1m:WILLR14=high & 15m:CHART.z2.STRUCT=up | -4.50 | -3.85 | 12.3 | 47.4 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 15m:CHART.z2.STRUCT=up | -3.86 | -2.98 | 15.9 | 47.3 |  | hot,rep |
| 1m:STOCHK5=low & 60m:CHART.z8.STRUCT=down | 1.78 | 2.88 | 16.4 | 47.1 |  | hot,rep |

#### BTC, 5 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:IBS=very high & 5m:CHART.z4.STRUCT=down | 1.08 | 2.56 | 51 | 131 |  | hot,rep |
| 15m:C-MEDPRICE sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.16 | 1.62 | 74.3 | 120 |  | hot,rep |
| 1m:IBS=very low & 60m:CHART.z2.STRUCT=up | -1.09 | -2.34 | 50.6 | 119 |  | hot,rep |
| 15m:C-AVGPRICE sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.15 | 1.58 | 74.2 | 117 |  | hot,rep |
| 1m:IBS=very high & 5m:CHART.z4.STRUCT=down | 0.87 | 2.38 | 49.2 | 117 |  | hot,rep |
| 1m:CORRELcv30 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.52 | 1.28 | 91.6 | 117 |  | hot,rep |
| 1m:OBV sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.63 | 1.09 | 104 | 114 |  | hot,rep |
| 1m:DIdiff14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.36 | 1.16 | 94.2 | 109 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.83 | 1.26 | 86.2 | 108 |  | hot,rep |
| 1m:PVI sign=below 0 & 60m:CHART.z8.STRUCT=down | 1.83 | 1.34 | 79.5 | 107 |  | hot,rep |
| 1m:AROONdn14=very high & 240m:CHART.z8.STRUCT=down | 3.57 | 1.98 | 53.3 | 106 |  | hot,rep |
| 1m:FISHER10 sign=below 0 & 15m:CHART.z2.STRUCT=down | 1.96 | 1.84 | 57 | 105 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z4.STRUCT=down | 2.50 | 1.91 | 54.7 | 104 |  | hot,rep |
| 1m:HT_INPHASE sign=below 0 & 15m:CHART.z2.STRUCT=down | 1.21 | 1.50 | 68.9 | 103 |  | hot,rep |
| 1m:FISHER10 sign=below 0 & 60m:CHART.z8.STRUCT=down | 1.77 | 1.37 | 74.8 | 103 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 15m:CHART.z2.STRUCT=down | 2.85 | 2.00 | 51.1 | 102 |  | hot,rep |
| 1m:PSO sign=below 0 & 15m:CHART.z2.STRUCT=down | 1.85 | 1.78 | 56.6 | 101 |  | hot,rep |
| 1m:EMA9>EMA21=below & 240m:CHART.z8.STRUCT=down | 2.20 | 1.16 | 86.2 | 99.7 |  | hot,rep |
| 1m:PVT sign=below 0 & 60m:CHART.z8.STRUCT=down | 1.86 | 1.22 | 81.7 | 99.7 |  | hot,rep |
| 1m:ASI sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.57 | 1.52 | 65.7 | 99.6 |  | hot,rep |
| 1m:AD sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.24 | 0.94 | 106 | 99.3 |  | hot,rep |
| 1m:PVI sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.31 | 1.55 | 63.2 | 98 |  | hot,rep |
| 1m:DONCHIAN20pos=low & 60m:CHART.z8.STRUCT=down | 4.65 | 3.13 | 31.3 | 97.9 |  | hot,rep |
| 1m:C-MCGD14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.22 | 1.00 | 97.4 | 97.9 |  | hot,rep |
| 1m:PVT sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.65 | 1.44 | 67 | 96.8 |  | hot,rep |
| 1m:WT1 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.24 | 1.10 | 87.4 | 96.2 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -5.61 | -2.51 | 38.2 | 95.9 |  | hot,rep |
| 15m:C-MEDPRICE sign=below 0 & 240m:CHART.z2.STRUCT=up | 2.06 | 2.03 | 47.1 | 95.8 |  | hot,rep |
| 1m:AD sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.72 | -1.42 | 66.5 | 94.4 |  | hot,rep |
| 1m:C-EMA200 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.21 | 1.15 | 81.5 | 93.6 |  | hot,rep |
| 1m:PSO sign=below 0 & 60m:CHART.z8.STRUCT=down | 1.72 | 1.25 | 74.6 | 93.5 |  | hot,rep |
| 1m:CCI20 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.05 | 0.96 | 96.9 | 92.6 |  | hot,rep |
| 1m:MAMA>FAMA=below & 240m:CHART.z8.STRUCT=down | 2.16 | 1.06 | 86.7 | 91.8 |  | hot,rep |
| 1m:HT_INPHASE sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.80 | -1.23 | 74.2 | 91.5 |  | hot,rep |
| 1m:PVT sign=above 0 & 15m:CHART.z4.STRUCT=up | -1.70 | -1.48 | 61.6 | 90.9 |  | hot,rep |
| 1m:C-SAR sign=below 0 & 60m:CHART.z2.STRUCT=down | 1.00 | 1.44 | 62.8 | 90.6 |  | hot,rep |
| 1m:OBV sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.34 | 1.34 | 67.3 | 90.3 |  | hot,rep |
| 1m:AROONOSC14 sign=below 0 & 60m:CHART.z2.STRUCT=down | 1.36 | 1.50 | 60.3 | 90.1 |  | hot,rep |
| 5m:PVI sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.47 | 1.85 | 48.7 | 90 |  | hot,rep |
| 1m:CORRELcv30 sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.12 | 1.48 | 60.8 | 89.7 |  | hot,rep |

#### BTC, 60 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| FLOW:TB5=very high & 15m:CHART.z2.STRUCT=up | -3.36 | -6.23 | 6.15 | 38.3 |  | hot,rep |
| FLOW:Stretch5=low & 5m:CHART.z2.STRUCT=down | 5.48 | 4.68 | 8.14 | 38.1 |  | hot,rep |
| 1m:WILLR14=high & 5m:CHART.z4.STRUCT=up | -3.61 | -5.02 | 7.41 | 37.2 |  | hot,rep |
| 1m:WILLR14=high & 5m:CHART.z4.STRUCT=up | -3.54 | -5.03 | 7.38 | 37.1 |  | hot,rep |
| 1m:HAbody=high & 5m:CHART.z4.STRUCT=up | -3.50 | -4.63 | 7.96 | 36.9 |  | hot,rep |
| 1m:AROONdn25=very high & 5m:CHART.z4.STRUCT=down | 4.78 | 4.93 | 7.47 | 36.8 |  | hot,rep |
| FLOW:TB15=high & 5m:CHART.z4.STRUCT=up | -4.64 | -5.67 | 6.39 | 36.3 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z2.STRUCT=down | 5.90 | 4.18 | 8.64 | 36.1 |  | hot,rep |
| 1m:SWAK_HP20=high & 5m:CHART.z4.STRUCT=up | -4.10 | -4.58 | 7.82 | 35.8 |  | hot,rep |
| 1m:PERCENTB20/2=high & 5m:CHART.z4.STRUCT=up | -4.72 | -5.09 | 7.03 | 35.8 |  | hot,rep |
| FLOW:TB15=high & 15m:CHART.z2.STRUCT=up | -3.54 | -5.30 | 6.72 | 35.6 |  | hot,rep |
| 1m:EFI13=low & 240m:CHART.z8.STRUCT=down | 3.63 | 4.99 | 7.08 | 35.3 |  | hot,rep |
| 1m:PDI14=high & 5m:CHART.z4.STRUCT=up | -4.23 | -5.74 | 6.15 | 35.3 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z2.STRUCT=down | 6.14 | 4.01 | 8.66 | 34.8 |  | hot,rep |
| X.XRP:R5z=low & 5m:CHART.z2.STRUCT=down | 4.58 | 4.18 | 8.25 | 34.5 | 4.42 | hot,rep,>twins |
| 1m:WILLR14=high & 15m:CHART.z2.STRUCT=up | -4.01 | -4.31 | 7.95 | 34.3 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.45 | -4.17 | 8.16 | 34 |  | hot,rep |
| 1m:C-VWAP20=low & 5m:CHART.z2.STRUCT=down | 6.23 | 4.25 | 7.99 | 33.9 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.54 | -4.13 | 8.22 | 33.9 |  | hot,rep |
| FLOW:TB15=high & 5m:CHART.z4.STRUCT=up | -3.65 | -5.40 | 6.27 | 33.8 |  | hot,rep |
| 1m:AROONdn25=very high & 5m:CHART.z4.STRUCT=down | 4.69 | 4.57 | 7.4 | 33.8 |  | hot,rep |
| 1m:CCI14=low & 240m:CHART.z8.STRUCT=down | 2.55 | 2.90 | 11.7 | 33.8 |  | hot,rep |
| 1m:CCI14=high & 5m:CHART.z4.STRUCT=up | -4.09 | -4.53 | 7.43 | 33.7 |  | hot,rep |
| 1m:PVI sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.95 | -4.05 | 8.3 | 33.6 |  | hot,rep |
| 1m:PVI=low & 240m:CHART.z8.STRUCT=down | 3.31 | 3.82 | 8.74 | 33.4 |  | hot,rep |
| 1m:TakerBuy=very high & 15m:CHART.z2.STRUCT=up | -1.66 | -4.53 | 7.33 | 33.2 | -9.56 | rep,>twins |
| 1m:VORTEXdiff14=low & 240m:CHART.z8.STRUCT=down | 2.62 | 3.08 | 10.7 | 33.1 |  | hot,rep |
| 5m:PVI sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.54 | -4.78 | 6.92 | 33 |  | hot,rep |
| 1m:CCI14=low & 240m:CHART.z8.STRUCT=down | 2.55 | 2.84 | 11.6 | 33 |  | hot,rep |
| X:Breadth15=3 down & 5m:CHART.z4.STRUCT=down | 3.10 | 3.85 | 8.55 | 32.9 |  | hot,rep |
| 1m:PERCENTB20/2=low & 240m:CHART.z8.STRUCT=down | 3.11 | 2.95 | 11.2 | 32.9 |  | hot,rep |
| FLOW:Stretch5=low & 5m:CHART.z2.STRUCT=down | 5.33 | 4.04 | 8.11 | 32.7 |  | hot,rep |
| 1m:EMA9>EMA21=above & 5m:CHART.z4.STRUCT=up | -3.54 | -4.13 | 7.92 | 32.7 |  | hot,rep |
| 1m:STOCHK14=high & 15m:CHART.z2.STRUCT=up | -3.78 | -4.25 | 7.69 | 32.7 |  | hot,rep |
| 1m:STOCHK14=low & 240m:CHART.z8.STRUCT=down | 2.20 | 2.87 | 11.3 | 32.6 |  | hot,rep |
| 1m:MAMA>FAMA=above & 5m:CHART.z4.STRUCT=up | -3.43 | -4.08 | 7.97 | 32.5 |  | hot,rep |
| FLOW:TB5=very high & 5m:CHART.z4.STRUCT=up | -3.00 | -5.69 | 5.7 | 32.4 |  | hot,rep |
| 1m:PDI14=high & 5m:CHART.z4.STRUCT=up | -4.64 | -5.37 | 6.04 | 32.4 |  | hot,rep |
| FLOW:TB5=low & 5m:CHART.z2.STRUCT=down | 5.10 | 3.50 | 9.25 | 32.4 |  | hot,rep |
| 1m:PERCENTB20/2=low & 240m:CHART.z8.STRUCT=down | 3.08 | 2.92 | 11.1 | 32.3 |  | hot,rep |

#### ETH, 1 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:DIdiff14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.08 | 1.47 | 485 | 712 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.05 | -1.46 | 486 | 711 |  | hot,rep |
| 1m:C-VIDYA12 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.11 | 1.49 | 475 | 706 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.05 | -1.42 | 496 | 705 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.91 | -1.34 | 495 | 665 |  | hot,rep |
| 1m:Ichimoku=above cloud & 240m:CHART.z8.STRUCT=down | -1.13 | -1.51 | 429 | 649 |  | hot,rep |
| 1m:C-SMA50 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.09 | 1.34 | 476 | 639 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.02 | -1.29 | 495 | 638 |  | hot,rep |
| 1m:C-MEDIAN30 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.84 | 1.31 | 482 | 633 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.79 | -1.29 | 489 | 632 |  | hot,rep |
| 1m:CCI50 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.13 | 1.32 | 476 | 630 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.06 | -1.27 | 495 | 629 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.08 | -1.89 | 333 | 629 |  | hot,rep |
| 1m:C-EMA21 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.85 | 1.31 | 480 | 627 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.80 | -1.27 | 491 | 626 |  | hot,rep |
| 1m:MACD5/35 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.15 | 1.31 | 476 | 625 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.08 | -1.26 | 495 | 624 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.97 | 1.28 | 485 | 620 |  | hot,rep |
| 1m:C-EMA50 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.16 | 1.31 | 473 | 619 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.94 | -1.27 | 486 | 619 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.08 | -1.24 | 498 | 618 |  | hot,rep |
| 1m:C-SMA20 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.76 | 1.28 | 483 | 618 |  | hot,rep |
| 1m:C-SMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.71 | -1.26 | 488 | 617 |  | hot,rep |
| 1m:CCI14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.72 | -1.25 | 488 | 612 |  | hot,rep |
| 1m:PVT sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.84 | -1.27 | 480 | 610 |  | hot,rep |
| 1m:WT1 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.07 | 1.26 | 481 | 606 |  | hot,rep |
| 1m:WT1 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.01 | -1.23 | 490 | 605 |  | hot,rep |
| 1m:C-WMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.65 | -1.23 | 489 | 600 |  | hot,rep |
| 1m:C-TRIMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.64 | -1.22 | 488 | 594 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.42 | 1.81 | 326 | 589 |  | hot,rep |
| 1m:C-HT_TRENDLINE sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.74 | -1.21 | 489 | 589 |  | hot,rep |
| 1m:ERIbull13 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.72 | -0.91 | 645 | 588 |  | hot,rep |
| 1m:ASI sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.67 | -1.21 | 485 | 585 |  | hot,rep |
| 1m:LRSLOPE14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.85 | -1.17 | 486 | 570 |  | hot,rep |
| 1m:QSTICK10 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.72 | 1.18 | 485 | 570 |  | hot,rep |
| 1m:QSTICK10 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.67 | -1.17 | 486 | 569 |  | hot,rep |
| 1m:MOM10 sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.72 | 1.16 | 484 | 563 |  | hot,rep |
| 1m:MOM10 sign=above 0 & 240m:CHART.z8.STRUCT=down | -0.67 | -1.15 | 487 | 562 |  | hot,rep |
| 5m:C-WMA20 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.17 | 1.19 | 471 | 561 |  | hot,rep |
| 5m:C-WMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.09 | -1.12 | 500 | 560 |  | hot,rep |

#### ETH, 15 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.62 | -3.06 | 53 | 162 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -6.70 | -6.66 | 21.9 | 146 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.42 | -2.63 | 53.9 | 142 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.14 | -2.43 | 56.9 | 138 |  | hot,rep |
| 1m:C-SMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.92 | -2.41 | 57 | 138 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.23 | -2.47 | 55.2 | 137 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z8.STRUCT=down | -5.30 | -4.66 | 29.2 | 136 |  | hot,rep |
| 1m:C-TRIMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.84 | -2.35 | 57.9 | 136 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.33 | -2.60 | 51.8 | 135 |  | hot,rep |
| 1m:CCI14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.69 | -2.26 | 59.4 | 134 |  | hot,rep |
| 1m:ASI sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.61 | -2.23 | 59.5 | 133 |  | hot,rep |
| 1m:C-WMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.69 | -2.20 | 60.1 | 133 |  | hot,rep |
| 1m:PVT sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.68 | -2.24 | 59.1 | 132 |  | hot,rep |
| 1m:QSTICK10 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.58 | -2.19 | 60.1 | 132 |  | hot,rep |
| 1m:MOM10 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.56 | -2.19 | 60.2 | 131 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -6.10 | -6.31 | 20.8 | 131 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.09 | -2.38 | 54.4 | 129 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.42 | -2.63 | 49 | 129 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.53 | -2.55 | 50.5 | 129 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.43 | -2.66 | 48.1 | 128 |  | hot,rep |
| 1m:WT1 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.21 | -2.57 | 49.6 | 127 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.43 | -2.61 | 48.2 | 126 |  | hot,rep |
| 1m:Ichimoku=above cloud & 240m:CHART.z8.STRUCT=down | -3.73 | -2.98 | 41.5 | 123 |  | hot,rep |
| 1m:C-HT_TRENDLINE sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.98 | -2.24 | 55.1 | 123 |  | hot,rep |
| 1m:LRSLOPE14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.72 | -2.18 | 56.5 | 123 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z8.STRUCT=down | -4.99 | -4.31 | 28.2 | 121 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.83 | 2.28 | 52.9 | 121 |  | hot,rep |
| 1m:C-KAMA30=high & 240m:CHART.z8.STRUCT=down | -5.94 | -5.68 | 21.1 | 120 |  | hot,rep |
| X:Breadth15=3 up & 240m:CHART.z8.STRUCT=down | -3.65 | -2.57 | 46.4 | 119 |  | hot,rep |
| 1m:AO sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.09 | -2.43 | 48.4 | 118 |  | hot,rep |
| 1m:CCI20=high & 240m:CHART.z8.STRUCT=down | -4.62 | -4.23 | 27.8 | 117 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.05 | -2.51 | 46.6 | 117 |  | hot,rep |
| 1m:CTI20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.03 | -2.25 | 52 | 117 |  | hot,rep |
| 1m:C-VIDYA12 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.72 | 2.17 | 53 | 115 |  | hot,rep |
| X.BTC:RSI14=high & 240m:CHART.z8.STRUCT=down | -6.60 | -5.14 | 22.2 | 114 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.90 | -4.17 | 27.3 | 114 |  | hot,rep |
| 1m:SQZMOM sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.81 | -2.17 | 52.3 | 113 |  | hot,rep |
| 5m:C-WMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.35 | -2.64 | 42.7 | 113 |  | hot,rep |
| 1m:C-KAMA30=high & 240m:CHART.z8.STRUCT=down | -5.72 | -5.67 | 19.7 | 112 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.72 | -3.78 | 29.5 | 111 |  | hot,rep |

#### ETH, 240 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 60m:C-CKSPmid sign=above 0 & 15m:CHART.K.BIAS=mixed | -2.12 | -6.68 | 2.76 | 18.4 |  | hot,rep |
| 1m:CMF20=low & 15m:CHART.z2.STRUCT=down | 3.27 | 7.61 | 2.4 | 18.2 |  | hot,rep |
| X:Breadth15=1 up & 15m:CHART.K.BIAS=mixed | -1.26 | -4.47 | 4.05 | 18.1 |  | rep |
| 60m:CTI20 sign=above 0 & 15m:CHART.K.BIAS=mixed | -2.28 | -7.07 | 2.45 | 17.3 |  | hot,rep |
| 1m:CCI50=very high & 240m:CHART.z8.STRUCT=down | -6.12 | -5.78 | 2.99 | 17.3 |  | hot,rep |
| 60m:CMF20 sign=above 0 & 15m:CHART.K.BIAS=mixed | -0.99 | -6.38 | 2.63 | 16.8 |  | rep |
| 1m:C-SUPERTREND10/3=very low & 5m:CHART.z2.STRUCT=down | 3.55 | 5.99 | 2.81 | 16.8 |  | hot,rep |
| FLOW:TB5=high & 15m:CHART.K.BIAS=mixed | -1.43 | -4.57 | 3.67 | 16.8 |  | rep |
| 1m:ACCBANDS20pos=very high & 240m:CHART.z8.STRUCT=down | -5.15 | -6.22 | 2.7 | 16.8 |  | hot,rep |
| X.SOL:TakerBuy=low & 15m:CHART.z2.STRUCT=down | 1.68 | 6.62 | 2.52 | 16.7 |  | rep |
| 1m:ADOSC=low & 15m:CHART.z2.STRUCT=down | 3.69 | 6.53 | 2.55 | 16.7 |  | hot,rep |
| 15m:C-SUPERTREND10/3 sign=above 0 & 15m:CHART.K.BIAS=mixed | -1.41 | -6.73 | 2.44 | 16.4 |  | rep |
| 1m:CMF20=very low & 15m:CHART.z2.STRUCT=down | 4.23 | 11.71 | 1.4 | 16.4 |  | hot,rep |
| 5m:CORRELcv30 sign=above 0 & 15m:CHART.K.BIAS=mixed | -3.10 | -5.02 | 3.23 | 16.2 |  | hot,rep |
| 1m:CMF20=very low & 15m:CHART.z2.STRUCT=down | 5.77 | 11.30 | 1.4 | 15.9 |  | hot,rep |
| X.SOL:Gap15=low & 5m:CHART.z2.STRUCT=down | 3.91 | 4.88 | 3.24 | 15.8 |  | hot,rep |
| 1m:C-SUPERTREND10/3=very low & 5m:CHART.z2.STRUCT=down | 3.21 | 5.63 | 2.81 | 15.8 |  | hot,rep |
| X:Breadth15=1 up & 15m:CHART.K.BIAS=mixed | -1.36 | -3.89 | 4.04 | 15.7 |  | rep |
| 1m:C-MEDIAN30=very high & 240m:CHART.z8.STRUCT=down | -5.90 | -6.99 | 2.24 | 15.6 |  | hot,rep |
| X.SOL:TakerBuy=low & 15m:CHART.z2.STRUCT=down | 1.61 | 6.17 | 2.52 | 15.6 |  | rep |
| FLOW:TB5=very high & 15m:CHART.z2.STRUCT=up | -2.63 | -8.30 | 1.86 | 15.4 |  | rep |
| FLOW:TB5=very high & 15m:CHART.z2.STRUCT=up | -2.78 | -8.27 | 1.86 | 15.4 |  | rep |
| X.XRP:RSI14=low & 5m:CHART.z2.BIAS=down 1 | 4.00 | 5.48 | 2.79 | 15.3 | 1.96 | hot,rep,>twins |
| 1m:C-TEMA21=very low & 5m:CHART.z2.STRUCT=down | 2.51 | 5.87 | 2.56 | 15 |  | rep |
| FLOW:TB15=very high & 15m:CHART.z2.STRUCT=up | -3.12 | -10.34 | 1.45 | 15 |  | rep |
| 1m:ADOSC=low & 15m:CHART.z2.STRUCT=down | 3.57 | 5.90 | 2.54 | 15 |  | hot,rep |
| X.SOL:Gap15=low & 5m:CHART.z2.STRUCT=down | 3.75 | 4.61 | 3.23 | 14.9 |  | hot,rep |
| 1m:C-SMA20=very high & 240m:CHART.z8.STRUCT=down | -5.91 | -5.51 | 2.65 | 14.6 |  | hot,rep |
| OI:PxQuad60=new shorts & 15m:CHART.K.BIAS=mixed | -1.05 | -4.69 | 3.01 | 14.1 |  | rep |
| 1m:C-MIDPOINT14=low & 15m:CHART.z2.STRUCT=down | 3.28 | 5.37 | 2.6 | 14 |  | hot,rep |
| 1m:C-MIDPOINT14=low & 15m:CHART.z2.STRUCT=down | 3.65 | 5.34 | 2.61 | 13.9 |  | hot,rep |
| 1m:C-TEMA21=very low & 5m:CHART.z2.STRUCT=down | 2.94 | 5.39 | 2.56 | 13.8 |  | hot,rep |
| 1m:C-MIDPRICE14=low & 15m:CHART.z2.STRUCT=down | 3.12 | 5.28 | 2.61 | 13.8 | -1.39 | hot,rep,>twins |
| 1m:ADOSC=very low & 5m:CHART.z4.STRUCT=down | 3.44 | 7.90 | 1.74 | 13.7 |  | hot,rep |
| 1m:STOCHK14=very low & 15m:CHART.z2.STRUCT=down | 2.56 | 7.00 | 1.96 | 13.7 |  | rep |
| X.BTC:RSI14=low & 5m:CHART.z2.BIAS=down 1 | 3.77 | 4.74 | 2.89 | 13.7 | 5.29 | hot,rep,>twins |
| 1m:C-VIDYA12=very high & 240m:CHART.z8.STRUCT=down | -5.50 | -4.80 | 2.85 | 13.7 |  | hot,rep |
| 15m:C-EMA200 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.87 | -5.45 | 2.5 | 13.6 |  | hot,rep |
| 1m:C-FRAMA16=low & 15m:CHART.z2.STRUCT=down | 2.84 | 5.11 | 2.66 | 13.6 |  | hot,rep |
| 1m:C-SUPERTREND10/3=very low & 5m:CHART.z2.BIAS=down 1 | 4.48 | 6.60 | 2.06 | 13.6 |  | hot,rep |

#### ETH, 30 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -5.48 | -6.16 | 15.6 | 96.1 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z8.STRUCT=down | -4.54 | -4.42 | 21.5 | 95 |  | hot,rep |
| 1m:C-KAMA30=high & 240m:CHART.z8.STRUCT=down | -4.76 | -6.02 | 15.2 | 91.4 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z8.STRUCT=down | -4.68 | -4.12 | 21.2 | 87.1 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -5.33 | -5.73 | 15.2 | 87.1 |  | hot,rep |
| 1m:C-KAMA30=high & 240m:CHART.z8.STRUCT=down | -4.82 | -5.66 | 14.7 | 83.1 |  | hot,rep |
| 1m:CCI20=high & 240m:CHART.z8.STRUCT=down | -4.25 | -3.92 | 21.1 | 82.8 |  | hot,rep |
| 1m:CCI20=high & 240m:CHART.z8.STRUCT=down | -4.00 | -3.96 | 20.7 | 82.2 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.07 | -2.69 | 30.6 | 82.2 |  | hot,rep |
| X.BTC:RSI14=high & 240m:CHART.z8.STRUCT=down | -5.27 | -4.98 | 16 | 79.9 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.77 | -4.63 | 16.7 | 77.5 |  | hot,rep |
| 1m:AROONup25=very high & 5m:CHART.z2.STRUCT=up | -5.72 | -6.77 | 11.3 | 76.3 |  | hot,rep |
| 1m:AROONup14=very high & 5m:CHART.z2.STRUCT=up | -4.77 | -5.07 | 14.5 | 73.7 |  | hot,rep |
| 1m:AO sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.52 | -2.56 | 28.6 | 73 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.96 | -2.49 | 29.3 | 72.9 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.83 | -2.38 | 30.6 | 72.8 |  | hot,rep |
| X:Breadth15=3 up & 240m:CHART.z8.STRUCT=down | -2.85 | -2.55 | 28.5 | 72.7 |  | hot,rep |
| 1m:WT1 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.63 | -2.52 | 28.8 | 72.7 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.01 | -2.43 | 29.9 | 72.7 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.69 | -2.36 | 30.8 | 72.6 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.89 | -2.59 | 27.9 | 72.3 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.88 | -2.59 | 27.7 | 71.7 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.74 | -2.29 | 31.2 | 71.5 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.91 | -2.55 | 28 | 71.4 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -3.18 | -2.51 | 28.4 | 71.2 |  | hot,rep |
| 1m:C-SMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.54 | -2.25 | 31.5 | 71.1 |  | hot,rep |
| 1m:DONCHIAN55pos=very high & 240m:CHART.z8.STRUCT=down | -6.84 | -7.57 | 9.22 | 69.9 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.62 | -4.13 | 16.9 | 69.8 |  | hot,rep |
| 1m:DONCHIAN55pos=very high & 240m:CHART.z8.STRUCT=down | -6.99 | -7.45 | 9.25 | 68.9 |  | hot,rep |
| 1m:CTI20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.37 | -2.27 | 30.2 | 68.6 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.71 | -4.03 | 17 | 68.3 |  | hot,rep |
| X.BTC:RSI14=high & 240m:CHART.z8.STRUCT=down | -4.50 | -4.38 | 15.5 | 68 |  | hot,rep |
| 5m:STOCHRSI14=very high & 240m:CHART.z8.STRUCT=down | -3.79 | -5.66 | 12 | 68 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.60 | -3.93 | 17.2 | 67.9 |  | hot,rep |
| 1m:Ichimoku=above cloud & 240m:CHART.z8.STRUCT=down | -3.07 | -2.79 | 24.3 | 67.8 |  | hot,rep |
| 1m:AROONup14=very high & 5m:CHART.z2.STRUCT=up | -4.85 | -4.67 | 14.4 | 67.1 |  | hot,rep |
| 1m:PVT sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.26 | -2.10 | 32 | 67.1 |  | hot,rep |
| 1m:C-SMA20 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.39 | -3.88 | 17.3 | 67 |  | hot,rep |
| 1m:C-TRIMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.47 | -2.11 | 31.8 | 66.9 |  | hot,rep |
| 1m:VORTEXdiff14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.25 | -3.89 | 17.2 | 66.7 |  | hot,rep |

#### ETH, 5 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.51 | -2.52 | 110 | 276 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.36 | -2.12 | 130 | 274 |  | hot,rep |
| 1m:Ichimoku=above cloud & 240m:CHART.z8.STRUCT=down | -2.61 | -2.60 | 102 | 266 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.43 | -2.06 | 124 | 256 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.21 | -2.06 | 124 | 255 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.22 | -1.92 | 132 | 253 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.35 | -2.14 | 118 | 253 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.36 | -2.08 | 121 | 251 |  | hot,rep |
| 1m:PVT sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.77 | -1.86 | 134 | 248 |  | hot,rep |
| 1m:C-VIDYA12 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.25 | 1.98 | 126 | 248 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.17 | -1.84 | 135 | 248 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.33 | -2.12 | 116 | 246 |  | hot,rep |
| 1m:MOM10 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.64 | -1.75 | 138 | 241 |  | hot,rep |
| 1m:QSTICK10 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.65 | -1.74 | 138 | 240 |  | hot,rep |
| 1m:ASI sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.68 | -1.77 | 135 | 239 |  | hot,rep |
| 1m:C-SMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.97 | -1.78 | 132 | 235 |  | hot,rep |
| 1m:WT1 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.14 | -2.02 | 116 | 235 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.18 | -2.11 | 111 | 234 |  | hot,rep |
| 1m:LRSLOPE14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.75 | -1.87 | 124 | 232 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.58 | 2.13 | 109 | 232 |  | hot,rep |
| 1m:C-EMA50 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.36 | 1.94 | 119 | 231 |  | hot,rep |
| 1m:C-TRIMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.90 | -1.74 | 132 | 230 |  | hot,rep |
| 1m:CCI50 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.27 | 1.99 | 114 | 228 |  | hot,rep |
| 1m:DIdiff14 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.05 | 1.84 | 124 | 227 |  | hot,rep |
| 1m:AO sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.10 | -1.98 | 115 | 227 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.11 | -1.75 | 129 | 226 |  | hot,rep |
| 1m:C-SMA50 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.28 | 1.93 | 117 | 226 |  | hot,rep |
| 1m:C-WMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.82 | -1.60 | 141 | 224 |  | hot,rep |
| 1m:MACD5/35 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.24 | 1.97 | 112 | 221 |  | hot,rep |
| 1m:C-EMA21 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.06 | 1.66 | 133 | 220 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -4.61 | -5.88 | 37.4 | 220 |  | hot,rep |
| 1m:CCI14 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.79 | -1.62 | 135 | 219 |  | hot,rep |
| 1m:C-HT_TRENDLINE sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.01 | -1.69 | 129 | 218 |  | hot,rep |
| 5m:C-WMA20 sign=above 0 & 240m:CHART.z8.STRUCT=down | -2.31 | -2.17 | 100 | 218 |  | hot,rep |
| 1m:MOM10 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.52 | 1.53 | 137 | 210 |  | hot,rep |
| 1m:QSTICK10 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.53 | 1.52 | 137 | 209 |  | hot,rep |
| 1m:WT1 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.03 | 1.83 | 114 | 209 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.01 | 1.89 | 111 | 209 |  | hot,rep |
| 1m:ERIbull13 sign=above 0 & 240m:CHART.z8.STRUCT=down | -1.48 | -1.25 | 166 | 207 |  | hot,rep |
| 1m:C-SMA20 sign=below 0 & 240m:CHART.z8.STRUCT=down | 1.85 | 1.57 | 131 | 206 |  | hot,rep |

#### ETH, 60 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:AROONup25=very high & 240m:CHART.z8.STRUCT=down | -3.14 | -3.81 | 14.3 | 54.5 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z8.STRUCT=down | -3.07 | -3.65 | 14.2 | 51.9 |  | hot,rep |
| 1m:PERCENTB20/2=very high & 240m:CHART.z8.STRUCT=down | -4.63 | -5.75 | 8.89 | 51.1 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -4.30 | -4.52 | 11 | 49.6 |  | hot,rep |
| 1m:DONCHIAN55pos=very high & 240m:CHART.z8.STRUCT=down | -5.24 | -6.39 | 7.73 | 49.4 |  | hot,rep |
| 1m:DONCHIAN55pos=very high & 240m:CHART.z8.STRUCT=down | -5.67 | -6.37 | 7.75 | 49.4 |  | hot,rep |
| X.BTC:RSI14=high & 240m:CHART.z8.STRUCT=down | -4.90 | -4.24 | 11.4 | 48.6 |  | hot,rep |
| 1m:C-VIDYA12=high & 240m:CHART.z8.STRUCT=down | -4.21 | -4.39 | 10.9 | 47.7 |  | hot,rep |
| 1m:CCI20=high & 240m:CHART.z8.STRUCT=down | -2.65 | -3.28 | 14.2 | 46.7 |  | hot,rep |
| 1m:C-KAMA30=high & 240m:CHART.z8.STRUCT=down | -4.05 | -4.38 | 10.6 | 46.4 |  | hot,rep |
| 1m:PERCENTB20/2=very high & 240m:CHART.z8.STRUCT=down | -4.36 | -5.20 | 8.86 | 46 |  | hot,rep |
| 1m:CCI20=high & 240m:CHART.z8.STRUCT=down | -2.68 | -3.24 | 14.2 | 45.8 |  | hot,rep |
| 1m:AROONup25=very high & 5m:CHART.z2.STRUCT=up | -5.71 | -5.68 | 8.01 | 45.5 |  | hot,rep |
| X.BTC:RSI14=high & 240m:CHART.z8.STRUCT=down | -4.65 | -3.89 | 11.3 | 43.9 |  | hot,rep |
| 1m:CRSI=very high & 240m:CHART.z8.STRUCT=down | -3.54 | -4.54 | 9.62 | 43.7 |  | hot,rep |
| 1m:C-KAMA30 sign=below 0 & 5m:CHART.z2.STRUCT=down | 4.74 | 4.43 | 9.55 | 42.4 |  | hot,rep |
| 1m:C-KAMA30=high & 240m:CHART.z8.STRUCT=down | -4.11 | -3.92 | 10.8 | 42.2 |  | hot,rep |
| 1m:AROONup14=very high & 5m:CHART.z2.STRUCT=up | -5.23 | -4.47 | 9.33 | 41.7 |  | hot,rep |
| 1m:PERCENTB20/2=high & 15m:CHART.K.BIAS=mixed | -2.67 | -5.35 | 7.58 | 40.6 |  | hot,rep |
| 1m:WILLR14=high & 5m:CHART.z2.STRUCT=up | -4.86 | -4.78 | 8.48 | 40.5 |  | hot,rep |
| 1m:WILLR14=high & 5m:CHART.z2.STRUCT=up | -4.78 | -4.75 | 8.51 | 40.4 |  | hot,rep |
| FLOW:TB5=low & 240m:CHART.z8.STRUCT=down | 1.33 | 2.77 | 14.5 | 40.1 | 5.68 | rep,>twins |
| 1m:AROONup14=very high & 5m:CHART.z2.STRUCT=up | -5.03 | -4.28 | 9.36 | 40.1 |  | hot,rep |
| FLOW:TB5=low & 240m:CHART.z8.STRUCT=down | 1.53 | 2.78 | 14.4 | 40 | 7.16 | rep,>twins |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -5.24 | -3.93 | 10.1 | 39.8 |  | hot,rep |
| 1m:AROONup14=very high & 15m:CHART.K.BIAS=mixed | -2.13 | -4.58 | 8.71 | 39.8 |  | hot,rep |
| 1m:CCI14=low & 5m:CHART.z2.STRUCT=down | 4.98 | 4.87 | 8.15 | 39.7 |  | hot,rep |
| 1m:AROONOSC25 sign=below 0 & 5m:CHART.z2.STRUCT=down | 4.66 | 4.21 | 9.4 | 39.6 |  | hot,rep |
| 1m:C-MIDPRICE14=high & 240m:CHART.z8.STRUCT=down | -3.05 | -3.00 | 13.2 | 39.6 |  | hot,rep |
| 1m:C-MIDPRICE14=high & 240m:CHART.z8.STRUCT=down | -2.96 | -2.95 | 13.1 | 38.6 |  | hot,rep |
| 1m:CCI20=high & 15m:CHART.K.BIAS=mixed | -2.73 | -5.23 | 7.31 | 38.2 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -5.28 | -3.71 | 10.2 | 38 |  | hot,rep |
| 1m:WT1 sign=below 0 & 5m:CHART.z2.STRUCT=down | 4.63 | 4.05 | 9.36 | 37.9 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 5m:CHART.z2.STRUCT=up | -5.17 | -3.66 | 10.3 | 37.8 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -5.16 | -3.71 | 10.2 | 37.8 |  | hot,rep |
| X:Breadth15=3 up & 5m:CHART.z2.STRUCT=up | -4.91 | -3.92 | 9.62 | 37.8 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 5m:CHART.z2.STRUCT=up | -5.29 | -3.72 | 10.1 | 37.7 |  | hot,rep |
| 1m:C-HT_TRENDLINE sign=above 0 & 5m:CHART.z2.STRUCT=up | -5.05 | -3.70 | 10.2 | 37.7 | -0.893 | hot,rep,>twins |
| 5m:KDJ K>D=above & 5m:CHART.z2.STRUCT=up | -4.19 | -4.04 | 9.28 | 37.5 |  | hot,rep |
| 1m:C-SMA20 sign=above 0 & 5m:CHART.z2.STRUCT=up | -5.02 | -3.63 | 10.3 | 37.5 |  | hot,rep |

#### SOL, 1 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.32 | -1.00 | 339 | 340 |  | rep |
| 1m:MACD5/35 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.43 | -0.98 | 338 | 333 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.34 | -0.99 | 335 | 333 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.36 | -0.97 | 339 | 330 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.42 | -0.97 | 339 | 330 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.36 | -0.97 | 339 | 329 |  | hot,rep |
| 1m:PVT sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.31 | -1.00 | 328 | 326 |  | rep |
| 1m:ERIbull13 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.34 | -0.72 | 450 | 322 |  | hot,rep |
| 1m:HAbody sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.07 | -0.96 | 337 | 322 |  | rep |
| 1m:WT1 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.41 | -0.95 | 336 | 320 |  | hot,rep |
| 1m:EMA9>EMA21=above & 240m:CHART.z4.STRUCT=down | -0.40 | -0.94 | 337 | 318 |  | hot,rep |
| 1m:VORTEXdiff14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.38 | -0.94 | 335 | 315 |  | hot,rep |
| 1m:C-KAMA30 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.38 | -0.92 | 341 | 314 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.30 | -0.92 | 336 | 310 |  | rep |
| 1m:C-MCGD14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.30 | -0.91 | 340 | 309 |  | rep |
| 1m:OBV sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.35 | -0.95 | 327 | 309 |  | hot,rep |
| 1m:C-MIDPOINT14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.21 | -0.89 | 336 | 300 |  | rep |
| 1m:CMOU14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.37 | -0.90 | 335 | 300 |  | hot,rep |
| 1m:MAMA>FAMA=above & 240m:CHART.z4.STRUCT=down | -0.40 | -0.89 | 336 | 300 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.25 | -0.88 | 337 | 297 |  | rep |
| 1m:CCI14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.26 | -0.87 | 336 | 293 |  | rep |
| 1m:QSTICK10 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.05 | -0.84 | 335 | 281 |  | rep |
| 1m:AD sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.05 | -0.83 | 333 | 277 |  | rep |
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.45 | -1.25 | 222 | 277 |  | hot,rep |
| 1m:C-MIDPRICE14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.17 | -0.81 | 336 | 272 |  | rep |
| 1m:Tenkan>Kijun=above & 240m:CHART.z4.STRUCT=down | -0.38 | -0.81 | 336 | 271 |  | hot,rep |
| 1m:C-SWAK_BUTTER20 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.07 | -0.81 | 335 | 270 |  | rep |
| 1m:EFI13 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.19 | -0.78 | 348 | 270 |  | rep |
| 1m:PVT sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.43 | -1.07 | 245 | 263 |  | hot,rep |
| 5m:C-DEMA21 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.29 | -0.77 | 337 | 260 |  | rep |
| 1m:OBV sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.34 | -1.05 | 243 | 257 |  | rep |
| 1m:ERIbull13 sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.36 | -0.75 | 335 | 252 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.35 | -0.97 | 251 | 244 |  | rep |
| 1m:C-SUPERTREND10/3 sign=below 0 & 5m:CHART.z2.STRUCT=down | 0.40 | 1.02 | 233 | 238 |  | hot,rep |
| 1m:QSTICK10 sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.20 | -0.93 | 249 | 232 |  | rep |
| 1m:C-MAMA sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.16 | -0.92 | 250 | 230 |  | rep |
| 1m:ERIbear13 sign=below 0 & 5m:CHART.z2.STRUCT=down | 0.25 | 0.73 | 314 | 230 |  | hot,rep |
| 5m:C-ZLEMA21 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.29 | -0.68 | 335 | 228 |  | rep |
| 1m:C-SWAK_GAUSS20 sign=below 0 & 240m:CHART.z8.STRUCT=contracting | 0.17 | 1.30 | 175 | 228 |  | rep |
| 1m:C-MIDPOINT14 sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.33 | -0.91 | 250 | 227 |  | rep |

#### SOL, 15 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.99 | -2.38 | 35.9 | 85.3 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z4.STRUCT=down | -2.17 | -4.16 | 20.3 | 84.7 |  | hot,rep |
| 1m:AROONup14=very high & 240m:CHART.z4.STRUCT=down | -1.89 | -2.92 | 28.9 | 84.5 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z4.STRUCT=down | -2.53 | -3.90 | 21.3 | 82.9 |  | hot,rep |
| 1m:AROONup14=very high & 240m:CHART.z4.STRUCT=down | -1.71 | -3.00 | 27.6 | 82.8 |  | hot,rep |
| 1m:CMOU14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.42 | -1.99 | 39.1 | 77.6 |  | hot,rep |
| 1m:CCI14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.47 | -1.86 | 41 | 76.4 |  | hot,rep |
| X:Breadth15=3 up & 240m:CHART.z4.STRUCT=down | -1.85 | -2.32 | 32.8 | 76 |  | hot,rep |
| 1m:VORTEXdiff14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.51 | -1.97 | 38.5 | 76 |  | hot,rep |
| 1m:C-MIDPOINT14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.40 | -1.83 | 41.2 | 75.4 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.59 | -1.99 | 37.4 | 74.4 |  | hot,rep |
| 1m:C-MIDPRICE14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.30 | -1.77 | 41 | 72.8 |  | hot,rep |
| 1m:C-SWAK_BUTTER20 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.27 | -1.66 | 43.8 | 72.6 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.71 | -1.92 | 37.9 | 72.6 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.62 | -1.85 | 39.1 | 72.5 |  | hot,rep |
| 1m:QSTICK10 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.37 | -1.75 | 41.5 | 72.4 |  | hot,rep |
| 1m:CMO14=high & 240m:CHART.z4.STRUCT=down | -3.69 | -4.93 | 14.7 | 72.4 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.80 | -1.96 | 36.5 | 71.4 |  | hot,rep |
| 1m:WT1 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.66 | -2.08 | 34 | 70.7 |  | hot,rep |
| 1m:C-FRAMA16 sign=below 0 & 5m:CHART.z2.STRUCT=down | 1.96 | 2.20 | 32.1 | 70.5 |  | hot,rep |
| 1m:PVT sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.63 | -1.72 | 40.8 | 70 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.82 | -2.07 | 33.7 | 69.7 |  | hot,rep |
| 1m:CMOU14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.36 | 2.43 | 28.5 | 69.4 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.96 | -2.00 | 34.6 | 69.3 |  | hot,rep |
| 1m:C-FRAMA16 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.84 | -2.20 | 31.5 | 69.1 |  | hot,rep |
| 1m:MAMA>FAMA=above & 240m:CHART.z4.STRUCT=down | -1.64 | -2.02 | 33.8 | 68.2 |  | hot,rep |
| 1m:VORTEXdiff14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.40 | 2.43 | 28 | 68.1 |  | hot,rep |
| 1m:EMA9>EMA21=above & 240m:CHART.z4.STRUCT=down | -1.70 | -2.04 | 33.4 | 68 |  | hot,rep |
| 1m:CCI20=high & 240m:CHART.z4.STRUCT=down | -2.15 | -3.47 | 19.5 | 67.9 |  | hot,rep |
| 1m:CCI14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.07 | -2.29 | 29.4 | 67.1 |  | hot,rep |
| X:Breadth5=3 up & 240m:CHART.z4.STRUCT=down | -1.16 | -1.61 | 41.3 | 66.4 |  | hot,rep |
| 1m:C-KAMA30 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.77 | -1.85 | 35.8 | 66 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.82 | -1.99 | 33.2 | 65.9 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.87 | -2.00 | 33 | 65.9 |  | hot,rep |
| 1m:C-MIDPRICE14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.04 | -2.24 | 29.3 | 65.8 |  | hot,rep |
| 1m:HAbody sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.13 | -1.47 | 44.7 | 65.6 |  | hot,rep |
| 1m:CCI14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.26 | 2.19 | 29.9 | 65.6 |  | hot,rep |
| 1m:PVI sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.19 | -2.28 | 28.7 | 65.3 |  | hot,rep |
| 1m:ADOSC sign=below 0 & 5m:CHART.z2.STRUCT=down | 1.98 | 2.29 | 28.5 | 65.3 |  | hot,rep |
| 1m:C-MIDPOINT14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.02 | -2.21 | 29.5 | 65.2 |  | hot,rep |

#### SOL, 240 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| X.ETH:Gap15=low & 5m:CHART.z2.STRUCT=down | 3.00 | 4.54 | 3.46 | 15.7 | -7.97 | hot,rep,>twins |
| 1m:RVI14=low & 5m:CHART.z4.STRUCT=down | 2.29 | 5.59 | 2.46 | 13.8 |  | hot,rep |
| 1m:C-SMA20=low & 15m:CHART.z2.STRUCT=down | 2.64 | 5.33 | 2.53 | 13.5 |  | hot,rep |
| 1m:C-DEMA21=low & 15m:CHART.z2.STRUCT=down | 1.48 | 5.06 | 2.62 | 13.3 |  | rep |
| 1m:MACDh12/26/9=low & 15m:CHART.z2.STRUCT=down | 1.82 | 5.29 | 2.51 | 13.3 |  | rep |
| 1m:ROGERSSATCHELL10=low & 15m:CHART.z2.STRUCT=down | 1.91 | 6.99 | 1.87 | 13.1 |  | rep |
| 1m:C-VWMA20=low & 5m:CHART.z4.STRUCT=down | 1.93 | 4.99 | 2.63 | 13.1 |  | hot,rep |
| 1m:C-CKSPmid=low & 5m:CHART.z4.STRUCT=down | 2.49 | 5.00 | 2.61 | 13.1 |  | hot,rep |
| X.ETH:Gap5=low & 5m:CHART.z2.STRUCT=down | 2.34 | 3.30 | 3.87 | 12.8 | -7.57 | hot,rep,>twins |
| 1m:ROGERSSATCHELL10=low & 15m:CHART.z2.STRUCT=down | 1.21 | 6.93 | 1.84 | 12.7 |  | rep |
| 1m:MACDh12/26/9=low & 15m:CHART.z2.STRUCT=down | 1.77 | 5.07 | 2.51 | 12.7 |  | rep |
| 1m:C-DEMA21=low & 15m:CHART.z2.STRUCT=down | 1.56 | 4.83 | 2.62 | 12.7 |  | rep |
| 5m:C-ZLEMA21=low & 5m:CHART.z4.STRUCT=down | 1.27 | 5.65 | 2.22 | 12.5 |  | rep |
| 1m:MARKETFI=low & 5m:CHART.z2.BIAS=mixed | 0.43 | 5.39 | 2.29 | 12.3 |  | rep |
| 1m:C-DEMA21=low & 5m:CHART.z4.STRUCT=down | 1.50 | 4.56 | 2.7 | 12.3 |  | rep |
| 1m:C-SMA20=low & 5m:CHART.z4.STRUCT=down | 2.81 | 4.75 | 2.57 | 12.2 |  | hot,rep |
| 1m:C-SMA20=low & 15m:CHART.z2.STRUCT=down | 2.36 | 4.81 | 2.53 | 12.2 |  | hot,rep |
| 1m:C-MAMA=low & 15m:CHART.z2.STRUCT=down | 2.18 | 4.62 | 2.62 | 12.1 |  | hot,rep |
| 1m:C-SAR=low & 15m:CHART.z2.STRUCT=down | 1.74 | 4.65 | 2.59 | 12.1 |  | rep |
| 1m:C-MAMA=low & 15m:CHART.z2.STRUCT=down | 2.28 | 4.59 | 2.63 | 12 |  | hot,rep |
| FLOW:TB15=high & 15m:CHART.z2.STRUCT=up | -2.17 | -5.04 | 2.39 | 12 |  | rep |
| 1m:TakerBuy=low & 15m:CHART.z2.STRUCT=down | 0.36 | 4.87 | 2.46 | 12 |  | rep |
| X.BTC:TakerBuy=low & 15m:CHART.z2.STRUCT=down | 1.03 | 4.41 | 2.7 | 11.9 |  | rep |
| 5m:C-LINEARREG14=low & 5m:CHART.z4.STRUCT=down | 1.44 | 5.14 | 2.3 | 11.8 |  | rep |
| X.BTC:TakerBuy=low & 15m:CHART.z2.STRUCT=down | 1.17 | 4.37 | 2.7 | 11.8 |  | rep |
| 1m:C-VWMA20=low & 5m:CHART.z4.STRUCT=down | 1.95 | 4.48 | 2.62 | 11.8 |  | hot,rep |
| 1m:RVI14=low & 5m:CHART.z4.STRUCT=down | 2.25 | 4.71 | 2.46 | 11.6 |  | hot,rep |
| 1m:MARKETFI=low & 5m:CHART.z2.BIAS=mixed | 0.31 | 5.04 | 2.29 | 11.5 |  | rep |
| 1m:C-EMA9=low & 15m:CHART.z2.STRUCT=down | 2.56 | 4.35 | 2.63 | 11.4 |  | hot,rep |
| 1m:TakerBuy=low & 15m:CHART.z2.STRUCT=down | 0.39 | 4.64 | 2.46 | 11.4 |  | rep |
| DMKT:DXY1d=flat & 15m:CHART.z2.STRUCT=down | 0.84 | 8.98 | 1.27 | 11.4 |  | rep |
| 5m:MACDh5/35/5 sign=below 0 & 15m:CHART.z2.STRUCT=down | 1.19 | 4.50 | 2.53 | 11.4 |  | rep |
| 1m:C-HMA20=low & 15m:CHART.z2.STRUCT=down | 0.86 | 4.22 | 2.68 | 11.3 |  | rep |
| 1m:MARKETFI=very high & 15m:CHART.z2.STRUCT=up | -0.94 | -5.46 | 2.06 | 11.2 |  | rep |
| 60m:MARKETFI sign=above 0 & 15m:CHART.z2.STRUCT=down | 1.93 | 8.13 | 1.38 | 11.2 |  | rep |
| 1m:C-MEDPRICE=low & 15m:CHART.z2.STRUCT=down | 1.38 | 4.18 | 2.68 | 11.2 |  | rep |
| 1m:MASSI=low & 15m:CHART.z4.STRUCT=down | 2.27 | 6.34 | 1.76 | 11.2 | -5.23 | rep,>twins |
| 1m:C-SAR=low & 15m:CHART.z2.STRUCT=down | 1.60 | 4.30 | 2.59 | 11.1 |  | rep |
| 1m:KURTOSIS30=high & 5m:CHART.z2.BIAS=mixed | 0.87 | 6.65 | 1.67 | 11.1 |  | rep |
| 1m:C-ALMA9=low & 15m:CHART.z2.STRUCT=down | 1.84 | 4.15 | 2.67 | 11.1 |  | hot,rep |

#### SOL, 30 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:ADOSC sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.37 | 3.12 | 17.1 | 53.5 |  | hot,rep |
| 1m:STOCHK5=low & 5m:CHART.z2.STRUCT=down | 3.23 | 3.87 | 13.3 | 51.5 |  | hot,rep |
| 1m:C-FRAMA16 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.52 | 2.78 | 18 | 50 |  | hot,rep |
| 1m:SI=low & 5m:CHART.z2.STRUCT=down | 2.93 | 3.30 | 15.1 | 49.8 |  | hot,rep |
| 1m:AD sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.31 | 2.83 | 17.5 | 49.6 |  | hot,rep |
| 1m:C-MIDPRICE14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.72 | 2.83 | 17.4 | 49.2 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.60 | 3.12 | 15.7 | 49.1 |  | hot,rep |
| FLOW:TB5=high & 240m:CHART.z4.STRUCT=down | -1.55 | -3.60 | 13.6 | 48.8 |  | hot,rep |
| 1m:C-MIDPOINT14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.81 | 2.79 | 17.5 | 48.7 |  | hot,rep |
| 1m:DIdiff14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 1.80 | 3.61 | 13.5 | 48.7 |  | hot,rep |
| 1m:KDJ_J=low & 5m:CHART.z2.STRUCT=down | 2.77 | 3.67 | 13.2 | 48.3 |  | hot,rep |
| 1m:C-WMA20 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.88 | 2.74 | 17.5 | 48 |  | hot,rep |
| 1m:WILLR14=low & 5m:CHART.z2.STRUCT=down | 3.68 | 3.79 | 12.6 | 47.9 | -7.41 | hot,rep,>twins |
| 1m:STOCHK5=low & 5m:CHART.z2.STRUCT=down | 2.85 | 3.65 | 13.1 | 47.8 |  | hot,rep |
| 1m:CCI14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.85 | 2.74 | 17.4 | 47.8 |  | hot,rep |
| 1m:C-SMA20 sign=below 0 & 5m:CHART.z2.STRUCT=down | 3.03 | 2.79 | 17.1 | 47.7 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z2.STRUCT=down | 3.37 | 2.90 | 16.4 | 47.4 |  | hot,rep |
| 1m:C-SAR sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.43 | 2.70 | 17.6 | 47.4 |  | hot,rep |
| 1m:CCI14=high & 240m:CHART.z4.STRUCT=down | -1.76 | -2.80 | 16.8 | 47 |  | hot,rep |
| 1m:SI=low & 5m:CHART.z2.STRUCT=down | 2.82 | 3.11 | 15.1 | 46.8 |  | hot,rep |
| 1m:CMOU14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.95 | 2.74 | 17 | 46.7 |  | hot,rep |
| 1m:SWAK_HP20 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.51 | 2.59 | 18 | 46.7 |  | hot,rep |
| 1m:WILLR14=low & 5m:CHART.z2.STRUCT=down | 3.61 | 3.67 | 12.5 | 45.8 | -5.91 | hot,rep,>twins |
| 1m:KDJ_J=low & 5m:CHART.z2.STRUCT=down | 3.01 | 3.43 | 13.3 | 45.7 |  | hot,rep |
| 1m:AC=low & 5m:CHART.z2.STRUCT=down | 2.28 | 3.75 | 12.2 | 45.7 |  | hot,rep |
| 1m:VORTEXdiff14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 3.00 | 2.70 | 16.9 | 45.6 |  | hot,rep |
| 1m:AROONup14=very high & 240m:CHART.z4.STRUCT=down | -1.88 | -2.38 | 19 | 45.1 |  | hot,rep |
| 1m:C-DEMA21=low & 5m:CHART.z2.STRUCT=down | 2.40 | 3.57 | 12.6 | 45 |  | hot,rep |
| 1m:ERIbear13 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.51 | 2.48 | 18 | 44.8 |  | hot,rep |
| 1m:PVT sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.90 | 2.53 | 17.6 | 44.5 |  | hot,rep |
| 1m:MACDh5/35/5=low & 5m:CHART.z2.STRUCT=down | 2.19 | 3.60 | 12.3 | 44.3 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z4.STRUCT=down | -2.75 | -2.88 | 15.2 | 44 |  | hot,rep |
| 1m:MACDh5/35/5=low & 5m:CHART.z2.STRUCT=down | 2.01 | 3.62 | 12.1 | 43.7 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z4.STRUCT=down | -2.03 | -2.08 | 21 | 43.6 |  | hot,rep |
| 1m:CCI20=high & 240m:CHART.z4.STRUCT=down | -2.30 | -2.94 | 14.8 | 43.4 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z4.STRUCT=down | -2.52 | -2.90 | 15 | 43.3 |  | hot,rep |
| 1m:AROONup14=very high & 240m:CHART.z4.STRUCT=down | -2.07 | -2.25 | 19.3 | 43.3 |  | hot,rep |
| 1m:CCI14=high & 240m:CHART.z4.STRUCT=down | -2.36 | -2.55 | 17 | 43.2 |  | hot,rep |
| 1m:DIdiff14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 3.41 | 2.62 | 16.4 | 43 |  | hot,rep |
| 1m:CMO14=high & 240m:CHART.z4.STRUCT=down | -3.70 | -3.98 | 10.7 | 42.4 |  | hot,rep |

#### SOL, 5 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:C-MEDIAN30 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.09 | -1.68 | 88.3 | 148 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.33 | -1.68 | 84.7 | 143 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.19 | -1.57 | 90.8 | 142 |  | hot,rep |
| 1m:PVT sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.17 | -1.55 | 91.9 | 142 |  | hot,rep |
| 1m:QSTICK10 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.93 | -1.47 | 94.7 | 140 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.20 | -1.68 | 82.9 | 140 |  | hot,rep |
| 1m:OBV sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.11 | -1.50 | 92.7 | 139 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.14 | -1.49 | 93.1 | 139 |  | hot,rep |
| 1m:WT1 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.20 | -1.74 | 79.7 | 138 |  | hot,rep |
| 1m:CMOU14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.91 | -1.53 | 89.8 | 138 |  | hot,rep |
| 1m:EMA9>EMA21=above & 240m:CHART.z4.STRUCT=down | -1.19 | -1.74 | 79.2 | 138 |  | hot,rep |
| 1m:VORTEXdiff14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.99 | -1.56 | 87.7 | 137 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.19 | -1.68 | 81.3 | 136 |  | hot,rep |
| 1m:MAMA>FAMA=above & 240m:CHART.z4.STRUCT=down | -1.15 | -1.71 | 79.3 | 135 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.22 | -1.55 | 87 | 135 |  | hot,rep |
| 1m:ERIbull13 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.94 | -1.17 | 116 | 135 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.51 | -1.81 | 74 | 134 |  | hot,rep |
| 1m:C-KAMA30 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.21 | -1.55 | 86.2 | 134 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.25 | -1.63 | 79.5 | 130 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.05 | -1.69 | 76.1 | 128 |  | hot,rep |
| 1m:CCI14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.06 | -1.37 | 93.3 | 128 |  | hot,rep |
| 1m:Tenkan>Kijun=above & 240m:CHART.z4.STRUCT=down | -1.07 | -1.61 | 78.9 | 127 |  | hot,rep |
| 1m:AD sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.71 | -1.34 | 94 | 126 |  | hot,rep |
| 1m:C-MIDPRICE14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.96 | -1.30 | 94.2 | 122 |  | hot,rep |
| 1m:C-MIDPOINT14 sign=above 0 & 240m:CHART.z4.STRUCT=down | -1.00 | -1.29 | 94.7 | 122 |  | hot,rep |
| 1m:C-SWAK_BUTTER20 sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.92 | -1.15 | 106 | 122 |  | hot,rep |
| 1m:HAbody sign=above 0 & 240m:CHART.z4.STRUCT=down | -0.83 | -1.04 | 114 | 119 |  | hot,rep |
| 1m:PVI sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.27 | -1.90 | 62.4 | 118 |  | hot,rep |
| 1m:C-VIDYA12 sign=below 0 & 15m:CHART.z4.STRUCT=up | 0.78 | 1.76 | 66.3 | 116 |  | hot,rep |
| 1m:AROONup25=very high & 240m:CHART.z4.STRUCT=down | -1.61 | -3.30 | 35.3 | 116 |  | hot,rep |
| 1m:HAbody sign=above 0 & 60m:CHART.z8.STRUCT=down | -0.91 | -1.36 | 85.1 | 115 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z2.STRUCT=down | 1.99 | 2.23 | 51.5 | 115 |  | hot,rep |
| X:Breadth15=3 up & 240m:CHART.z4.STRUCT=down | -0.89 | -1.70 | 67.5 | 115 |  | hot,rep |
| 1m:PVT sign=below 0 & 5m:CHART.z2.STRUCT=down | 1.31 | 1.71 | 66.9 | 115 |  | hot,rep |
| 1m:C-EMA9 sign=above 0 & 240m:CHART.z8.STRUCT=contracting | -0.27 | -2.12 | 54 | 114 |  | rep |
| 1m:AROONup14=very high & 240m:CHART.z4.STRUCT=down | -1.28 | -2.35 | 48.4 | 114 |  | hot,rep |
| 1m:C-MAMA sign=above 0 & 240m:CHART.z8.STRUCT=contracting | -0.31 | -2.10 | 54.1 | 113 |  | rep |
| 1m:C-FRAMA16 sign=above 0 & 240m:CHART.z8.STRUCT=contracting | -0.16 | -2.13 | 53.1 | 113 |  | rep |
| 1m:C-MAMA sign=above 0 & 60m:CHART.z8.STRUCT=down | -1.06 | -1.45 | 77.6 | 113 |  | hot,rep |
| 1m:C-SWAK_GAUSS20 sign=above 0 & 240m:CHART.z8.STRUCT=contracting | -0.22 | -2.00 | 56.1 | 112 |  | rep |

#### SOL, 60 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:MACDh5/35/5=low & 5m:CHART.z2.STRUCT=down | 2.12 | 3.94 | 8.75 | 34.5 |  | hot,rep |
| 1m:MACDh5/35/5=low & 5m:CHART.z2.STRUCT=down | 2.41 | 3.88 | 8.7 | 33.8 |  | hot,rep |
| FLOW:TB5=high & 240m:CHART.z4.STRUCT=down | -1.84 | -3.75 | 8.85 | 33.2 |  | hot,rep |
| 1m:C-DEMA21=low & 5m:CHART.z2.STRUCT=down | 2.14 | 3.68 | 8.81 | 32.4 |  | hot,rep |
| 1m:AC=low & 5m:CHART.z2.STRUCT=down | 2.11 | 3.71 | 8.67 | 32.2 |  | hot,rep |
| 1m:STOCHK5=low & 5m:CHART.z2.STRUCT=down | 2.96 | 3.61 | 8.91 | 32.1 |  | hot,rep |
| 1m:KDJ_J=low & 5m:CHART.z2.STRUCT=down | 3.06 | 3.56 | 8.98 | 31.9 |  | hot,rep |
| X.ETH:TakerBuy=high & 5m:CHART.z2.STRUCT=up | -1.95 | -3.49 | 9.12 | 31.8 |  | hot,rep |
| 1m:WILLR14=low & 5m:CHART.z2.STRUCT=down | 3.76 | 3.60 | 8.63 | 31.1 | 4.72 | hot,rep,>twins |
| FLOW:TB5=high & 15m:CHART.z8.STRUCT=up | -1.32 | -4.65 | 6.6 | 30.7 |  | rep |
| 1m:KDJ_J=low & 5m:CHART.z2.STRUCT=down | 2.54 | 3.43 | 8.95 | 30.7 |  | hot,rep |
| 1m:C-SMA20=low & 5m:CHART.z2.STRUCT=down | 4.16 | 4.15 | 7.29 | 30.2 |  | hot,rep |
| 1m:STOCHK5=low & 5m:CHART.z2.STRUCT=down | 2.78 | 3.36 | 8.87 | 29.8 |  | hot,rep |
| 1m:C-DEMA21=low & 5m:CHART.z2.STRUCT=down | 2.41 | 3.39 | 8.77 | 29.7 |  | hot,rep |
| X.ETH:TakerBuy=high & 5m:CHART.z2.STRUCT=up | -2.00 | -3.24 | 9.12 | 29.5 |  | hot,rep |
| 1m:CCI14=high & 240m:CHART.z4.STRUCT=down | -1.47 | -2.75 | 10.5 | 29 |  | hot,rep |
| 1m:PVI=low & 15m:CHART.z2.STRUCT=down | 3.30 | 5.17 | 5.57 | 28.8 | 0.934 | hot,rep,>twins |
| 1m:C-MAMA=low & 15m:CHART.z2.STRUCT=down | 2.89 | 3.88 | 7.34 | 28.5 |  | hot,rep |
| 1m:C-EMA9=low & 15m:CHART.z2.STRUCT=down | 2.55 | 3.93 | 7.23 | 28.4 |  | hot,rep |
| 1m:C-SMA20=low & 5m:CHART.z2.STRUCT=down | 4.01 | 3.91 | 7.21 | 28.1 |  | hot,rep |
| 1m:TakerBuy=low & 15m:CHART.z2.STRUCT=down | 0.78 | 4.28 | 6.53 | 27.9 |  | rep |
| 1m:WILLR14=low & 5m:CHART.z2.STRUCT=down | 3.67 | 3.24 | 8.59 | 27.8 | 3.42 | hot,rep,>twins |
| 1m:C-FRAMA16 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.77 | 2.65 | 10.5 | 27.7 |  | hot,rep |
| 1m:C-EMA9=low & 15m:CHART.z2.STRUCT=down | 2.83 | 3.79 | 7.27 | 27.6 |  | hot,rep |
| 1m:C-SMA20=low & 15m:CHART.z2.STRUCT=down | 2.85 | 4.43 | 6.22 | 27.5 |  | hot,rep |
| 1m:C-RMA14=low & 15m:CHART.z4.STRUCT=up | 2.68 | 4.35 | 6.32 | 27.5 |  | hot,rep |
| 1m:C-MCGD14=low & 15m:CHART.z4.STRUCT=up | 2.63 | 4.29 | 6.35 | 27.3 |  | hot,rep |
| 1m:C-EMA21=low & 15m:CHART.z4.STRUCT=up | 2.21 | 4.03 | 6.75 | 27.2 |  | hot,rep |
| 1m:C-MAMA=low & 15m:CHART.z2.STRUCT=down | 2.96 | 3.70 | 7.36 | 27.2 |  | hot,rep |
| FLOW:TB15=high & 15m:CHART.z8.STRUCT=up | -1.96 | -5.34 | 5.09 | 27.2 |  | hot,rep |
| 1m:AC=low & 5m:CHART.z2.STRUCT=down | 2.15 | 3.15 | 8.6 | 27.1 |  | hot,rep |
| 1m:MACDh12/26/9=low & 15m:CHART.z2.STRUCT=down | 1.33 | 4.12 | 6.53 | 26.9 |  | rep |
| 1m:PVI=low & 15m:CHART.z2.STRUCT=down | 2.84 | 4.89 | 5.49 | 26.8 | 0.537 | hot,rep,>twins |
| 1m:C-DEMA21=low & 15m:CHART.z2.STRUCT=down | 1.48 | 3.57 | 7.51 | 26.8 |  | hot,rep |
| 1m:CMOU14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 3.21 | 2.63 | 10.2 | 26.7 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.88 | 2.72 | 9.84 | 26.7 |  | hot,rep |
| X.ETH:Gap5=low & 5m:CHART.z2.STRUCT=down | 2.79 | 3.15 | 8.46 | 26.7 | -16.3 | hot,rep,>twins |
| 1m:CCI14=high & 240m:CHART.z4.STRUCT=down | -1.76 | -2.52 | 10.6 | 26.6 |  | hot,rep |
| 1m:C-FRAMA16=low & 15m:CHART.z2.STRUCT=down | 2.26 | 3.62 | 7.32 | 26.5 |  | hot,rep |
| 1m:PVT sign=below 0 & 5m:CHART.z2.STRUCT=down | 2.15 | 2.64 | 10 | 26.4 |  | hot,rep |

#### XRP, 1 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:C-KAMA30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.11 | -1.31 | 236 | 308 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.03 | -1.27 | 237 | 300 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.12 | -1.27 | 235 | 298 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.04 | -1.21 | 245 | 297 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.01 | -1.24 | 237 | 295 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.11 | -1.24 | 235 | 290 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.10 | -1.23 | 235 | 288 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.94 | -1.26 | 228 | 286 |  | hot,rep |
| 1m:ERIbull13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.97 | -0.92 | 305 | 282 |  | hot,rep |
| 5m:C-MAMA sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.92 | -1.15 | 240 | 277 |  | hot,rep |
| 1m:C-SMA200 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.71 | -0.90 | 305 | 274 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.06 | -1.19 | 231 | 273 |  | hot,rep |
| 1m:C-EMA200 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.76 | -0.88 | 310 | 271 |  | hot,rep |
| 1m:EMA9>EMA21=above & 5m:CHART.z2.STRUCT=up | -0.96 | -1.14 | 234 | 267 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.00 | -1.16 | 230 | 267 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.98 | -1.11 | 239 | 266 |  | hot,rep |
| 1m:WT1 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.93 | -1.11 | 232 | 256 |  | hot,rep |
| 1m:AROONOSC25 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.90 | -1.10 | 233 | 256 | -51.7 | hot,rep,>twins |
| 1m:C-KAMA30 sign=below 0 & 15m:CHART.z2.STRUCT=down | 0.81 | 1.07 | 240 | 256 |  | hot,rep |
| 1m:APO12/26 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.91 | -1.07 | 239 | 256 | -57 | hot,rep,>twins |
| 1m:HAbody sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.94 | -1.11 | 227 | 252 |  | hot,rep |
| 1m:C-MIDPRICE14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.91 | -1.11 | 226 | 251 |  | hot,rep |
| 5m:C-VIDYA12 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.71 | -0.82 | 306 | 251 |  | hot,rep |
| 1m:C-EMA200 sign=below 0 & 15m:CHART.z2.STRUCT=down | 0.75 | 0.93 | 263 | 245 |  | hot,rep |
| 1m:DIdiff14 sign=below 0 & 15m:CHART.z2.STRUCT=down | 0.76 | 0.97 | 251 | 244 |  | hot,rep |
| 5m:C-EMA21 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.79 | -0.88 | 277 | 244 |  | hot,rep |
| 1m:MAMA>FAMA=above & 5m:CHART.z2.STRUCT=up | -0.96 | -1.05 | 232 | 244 |  | hot,rep |
| 1m:COPPOCK sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.83 | -1.05 | 228 | 241 |  | hot,rep |
| 1m:PVT sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.04 | -1.05 | 227 | 239 |  | hot,rep |
| 15m:C-AVGPRICE sign=below 0 & 240m:CHART.z8.STRUCT=down | 0.79 | 0.96 | 248 | 239 |  | hot,rep |
| 5m:C-VIDYA12 sign=below 0 & 5m:CHART.z2.STRUCT=down | 0.78 | 0.78 | 306 | 237 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 15m:CHART.z4.STRUCT=down | -0.57 | -0.91 | 261 | 237 |  | hot,rep |
| 1m:AROONOSC14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.92 | -1.03 | 228 | 235 |  | hot,rep |
| 1m:ERIbull13 sign=above 0 & 240m:CHART.z2.STRUCT=contracting | -0.32 | -0.80 | 295 | 235 |  | rep |
| 1m:C-SAR sign=above 0 & 5m:CHART.z2.STRUCT=up | -0.81 | -1.04 | 225 | 234 |  | hot,rep |
| 1m:ERIbull13 sign=above 0 & 60m:CHART.z4.STRUCT=down | -0.57 | -0.71 | 329 | 233 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 240m:CHART.z2.STRUCT=contracting | -0.50 | -1.07 | 217 | 232 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.32 | -1.53 | 151 | 231 |  | hot,rep |
| 5m:C-VIDYA12 sign=below 0 & 15m:CHART.z2.STRUCT=down | 0.73 | 0.90 | 255 | 230 |  | hot,rep |
| 1m:HAbody sign=above 0 & 240m:CHART.z2.STRUCT=contracting | -0.39 | -1.03 | 221 | 229 |  | rep |

#### XRP, 15 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:C-KAMA30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.94 | -2.84 | 25.7 | 73 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.93 | -2.71 | 26.7 | 72.3 |  | hot,rep |
| 1m:COPPOCK sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.75 | -2.84 | 25.3 | 71.8 |  | hot,rep |
| 1m:C-FRAMA16 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.94 | -2.31 | 31 | 71.8 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.80 | -2.70 | 26.6 | 71.8 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.86 | -2.62 | 27.3 | 71.3 |  | hot,rep |
| 1m:AROONOSC14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.49 | -2.63 | 27.1 | 71.2 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.34 | -2.79 | 25.5 | 71 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.95 | -2.92 | 24.1 | 70.6 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.98 | -2.75 | 25.6 | 70.5 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.77 | -2.51 | 27.9 | 70 |  | hot,rep |
| 5m:C-MAMA sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.79 | -3.12 | 22.4 | 69.9 |  | hot,rep |
| 1m:EMA9>EMA21=above & 5m:CHART.z2.STRUCT=up | -3.90 | -2.89 | 24.1 | 69.5 |  | hot,rep |
| 1m:AROONOSC25 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.99 | -2.91 | 23.9 | 69.4 | -16.5 | hot,rep,>twins |
| 1m:MAMA>FAMA=above & 5m:CHART.z2.STRUCT=up | -3.95 | -2.85 | 24.3 | 69.3 |  | hot,rep |
| 1m:PVT sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.34 | -2.38 | 29.2 | 69.3 |  | hot,rep |
| 1m:WT1 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.93 | -2.82 | 24.4 | 68.7 |  | hot,rep |
| 1m:C-SAR sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.98 | -2.35 | 29.2 | 68.6 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.93 | -2.80 | 24.5 | 68.5 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.92 | -2.85 | 24 | 68.5 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 15m:CHART.z8.STRUCT=up | 2.38 | 2.80 | 24.3 | 68.1 |  | hot,rep |
| X:Breadth15=3 down & 15m:CHART.z8.STRUCT=up | 2.08 | 3.13 | 21.8 | 68.1 |  | hot,rep |
| 1m:C-MIDPRICE14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.17 | -2.32 | 29 | 67.4 |  | hot,rep |
| 1m:APO12/26 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.95 | -2.91 | 23.1 | 67.1 | -16.6 | hot,rep,>twins |
| 1m:C-SUPERTREND10/3 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.66 | -2.90 | 22.9 | 66.5 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z8.STRUCT=up | 2.91 | 4.90 | 13.5 | 66.2 |  | hot,rep |
| X:Breadth15=3 down & 240m:CHART.z8.STRUCT=down | 2.99 | 2.68 | 24.4 | 65.4 | 45.8 | hot,rep,>twins |
| 1m:ERIbull13 sign=below 0 & 240m:CHART.z8.STRUCT=down | 2.77 | 2.46 | 26.6 | 65.2 |  | hot,rep |
| 1m:C-MAMA sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.18 | -2.11 | 30.8 | 64.9 |  | hot,rep |
| 1m:C-SWAK_BUTTER20 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.07 | -2.06 | 31.1 | 64.1 |  | hot,rep |
| 1m:C-VIDYA12 sign=below 0 & 15m:CHART.z8.STRUCT=up | 2.30 | 2.55 | 25 | 63.8 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.97 | -2.42 | 26.2 | 63.2 |  | hot,rep |
| 1m:KST sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.83 | -2.81 | 22.4 | 62.8 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z8.STRUCT=up | 2.36 | 2.93 | 21.4 | 62.6 |  | hot,rep |
| 1m:AROONOSC14 sign=below 0 & 5m:CHART.z2.STRUCT=down | 3.31 | 2.19 | 28.4 | 62.2 |  | hot,rep |
| 1m:VORTEXdiff14 sign=above 0 & 60m:CHART.z4.STRUCT=down | -1.67 | -2.19 | 28.1 | 61.6 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z8.STRUCT=up | 2.81 | 4.60 | 13.3 | 61.4 |  | hot,rep |
| 1m:C-SWAK_GAUSS20 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.02 | -1.95 | 31.4 | 61.4 |  | hot,rep |
| 1m:C-KAMA30 sign=below 0 & 15m:CHART.z2.STRUCT=down | 3.21 | 2.37 | 25.9 | 61.3 |  | hot,rep |
| 1m:KC20pos=low & 5m:CHART.z8.STRUCT=up | 3.42 | 5.60 | 10.9 | 61.1 |  | hot,rep |

#### XRP, 240 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:STOCHK5=very low & 5m:CHART.z4.STRUCT=down | 3.47 | 6.58 | 2.57 | 16.9 |  | hot,rep |
| 1m:AROONOSC14=very low & 5m:CHART.z4.STRUCT=down | 4.20 | 5.98 | 2.74 | 16.4 |  | hot,rep |
| 1m:STOCHK14=very low & 5m:CHART.z4.STRUCT=down | 4.12 | 6.45 | 2.5 | 16.1 |  | hot,rep |
| 1m:TakerBuy=low & 5m:CHART.z4.STRUCT=up | -2.93 | -6.51 | 2.47 | 16.1 |  | hot,rep |
| 1m:STOCHK14=very low & 5m:CHART.z4.STRUCT=down | 3.48 | 6.25 | 2.5 | 15.6 |  | hot,rep |
| 1m:STOCHK5=very low & 5m:CHART.z4.STRUCT=down | 3.29 | 6.05 | 2.57 | 15.5 |  | hot,rep |
| 1m:IMI14=low & 5m:CHART.z4.STRUCT=down | 4.26 | 5.43 | 2.86 | 15.5 | -1.85 | hot,rep,>twins |
| 60m:NVI sign=below 0 & 5m:CHART.z4.STRUCT=up | -1.57 | -9.43 | 1.62 | 15.2 |  | rep |
| 1m:CG10=high & 15m:CHART.K.BIAS=up 2+ | -2.06 | -8.42 | 1.8 | 15.1 |  | rep |
| 1m:WILLR14=very low & 5m:CHART.z4.STRUCT=up | -2.09 | -6.86 | 2.19 | 15 |  | rep |
| 1m:AROONOSC14=very low & 5m:CHART.z4.STRUCT=down | 4.00 | 5.49 | 2.74 | 15 |  | hot,rep |
| 1m:CG10=low & 5m:CHART.z2.BIAS=down 2+ | 5.07 | 9.03 | 1.64 | 14.8 |  | hot,rep |
| 1m:TakerBuy=low & 5m:CHART.z4.STRUCT=up | -2.94 | -5.95 | 2.47 | 14.7 |  | hot,rep |
| 1m:CG10=low & 5m:CHART.z2.STRUCT=down | 6.50 | 4.92 | 2.93 | 14.4 |  | hot,rep |
| 1m:AROONOSC14=very low & 15m:CHART.z2.STRUCT=down | 4.17 | 5.38 | 2.68 | 14.4 |  | hot,rep |
| FLOW:TB15=very low & 5m:CHART.z4.STRUCT=up | -3.80 | -11.11 | 1.27 | 14.2 |  | rep |
| 1m:MACDh5/35/5=low & 5m:CHART.z2.BIAS=down 2+ | 3.82 | 7.33 | 1.93 | 14.1 |  | hot,rep |
| 1m:C-KAMA30 sign=above 0 & 5m:CHART.z4.STRUCT=up | -2.49 | -5.48 | 2.58 | 14.1 |  | hot,rep |
| FLOW:TB5=high & 5m:CHART.z4.STRUCT=up | -2.92 | -5.77 | 2.42 | 14 |  | hot,rep |
| 1m:WILLR14=very low & 5m:CHART.z4.STRUCT=up | -2.05 | -6.35 | 2.19 | 13.9 |  | rep |
| 1m:PSO=low & 5m:CHART.z4.STRUCT=down | 4.10 | 4.92 | 2.83 | 13.9 |  | hot,rep |
| 1m:PSO=low & 5m:CHART.z4.STRUCT=down | 3.52 | 4.88 | 2.82 | 13.8 |  | hot,rep |
| X.SOL:RSI14=low & 15m:CHART.z2.STRUCT=down | 3.09 | 5.15 | 2.63 | 13.5 | -1.81 | hot,rep,>twins |
| FLOW:Stretch5=high & 15m:CHART.K.BIAS=up 2+ | -3.63 | -5.57 | 2.43 | 13.5 |  | hot,rep |
| 1m:EFI13=high & 15m:CHART.K.BIAS=up 2+ | -4.34 | -7.26 | 1.86 | 13.5 |  | hot,rep |
| X.SOL:RSI14=low & 15m:CHART.z2.STRUCT=down | 2.82 | 5.09 | 2.62 | 13.3 | -1.64 | hot,rep,>twins |
| 1m:MFI14=very low & 5m:CHART.z4.STRUCT=contracting | 3.87 | 11.74 | 1.13 | 13.3 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 5m:CHART.z4.STRUCT=up | -3.10 | -5.16 | 2.56 | 13.2 |  | hot,rep |
| 1m:SQZMOM=low & 5m:CHART.z4.STRUCT=down | 4.17 | 4.82 | 2.74 | 13.2 |  | hot,rep |
| 1m:Ichimoku=below cloud & 5m:CHART.z4.STRUCT=down | 2.51 | 4.70 | 2.8 | 13.2 |  | hot,rep |
| FLOW:TB15=high & 5m:CHART.z4.STRUCT=up | -2.94 | -6.18 | 2.13 | 13.2 |  | hot,rep |
| X.BTC:R5z=high & 15m:CHART.K.BIAS=up 2+ | -2.29 | -5.44 | 2.41 | 13.1 |  | rep |
| 1m:C-EMA21=low & 15m:CHART.z2.STRUCT=down | 4.76 | 4.75 | 2.75 | 13.1 |  | hot,rep |
| 1m:KC20pos=low & 15m:CHART.z2.STRUCT=down | 4.67 | 4.72 | 2.77 | 13.1 |  | hot,rep |
| 1m:RVOL20=very high & 15m:CHART.K.BIAS=mixed | -0.45 | -4.12 | 3.17 | 13.1 |  | rep |
| 5m:SMI>sig=below & 5m:CHART.z2.BOS=BOS down | 5.76 | 4.93 | 2.65 | 13 |  | hot,rep |
| 1m:AROONdn25=very high & 15m:CHART.z2.STRUCT=down | 3.80 | 4.60 | 2.83 | 13 |  | hot,rep |
| 1m:HT_QUADRATURE=low & 5m:CHART.z2.BIAS=down 2+ | 2.37 | 6.34 | 2.05 | 13 |  | rep |
| 1m:RVOL20=very high & 15m:CHART.K.BIAS=mixed | -0.47 | -4.10 | 3.17 | 13 |  | rep |
| X.ETH:RSI14=high & 15m:CHART.K.BIAS=up 2+ | -4.09 | -6.06 | 2.12 | 12.8 |  | hot,rep |

#### XRP, 30 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z8.STRUCT=up | 3.57 | 5.54 | 9.59 | 53.1 |  | hot,rep |
| 1m:AROONup14=very low & 5m:CHART.z4.STRUCT=down | 3.32 | 3.41 | 15.3 | 52.1 | -16.3 | hot,rep,>twins |
| 1m:C-EMA21=low & 5m:CHART.z2.STRUCT=down | 5.99 | 4.99 | 10 | 50 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z8.STRUCT=up | 3.29 | 5.18 | 9.54 | 49.4 |  | hot,rep |
| 1m:C-EMA21=low & 15m:CHART.z2.STRUCT=down | 5.10 | 4.98 | 9.71 | 48.4 |  | hot,rep |
| 1m:AROONdn14=very high & 5m:CHART.z8.STRUCT=up | 2.70 | 4.19 | 11.5 | 48.3 |  | hot,rep |
| 1m:AROONup14=very low & 5m:CHART.z4.STRUCT=down | 3.08 | 3.20 | 15.1 | 48.3 | -7.95 | hot,rep,>twins |
| 1m:KC20pos=low & 15m:CHART.z2.STRUCT=down | 5.13 | 4.78 | 10.1 | 48.2 |  | hot,rep |
| 1m:AROONOSC14=very low & 5m:CHART.z4.STRUCT=down | 3.89 | 5.89 | 8.16 | 48.1 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.61 | 2.89 | 16.5 | 47.9 | 4.49 | hot,rep,>twins |
| 1m:KC20pos=low & 5m:CHART.z2.STRUCT=down | 5.80 | 4.67 | 10.2 | 47.9 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 60m:CHART.z2.STRUCT=up | 3.55 | 4.95 | 9.63 | 47.7 |  | hot,rep |
| 1m:C-RMA14=low & 15m:CHART.z2.STRUCT=down | 5.36 | 5.26 | 8.96 | 47.2 |  | hot,rep |
| 1m:C-SMA20=low & 60m:CHART.z2.STRUCT=up | 3.85 | 6.01 | 7.81 | 46.9 |  | hot,rep |
| 1m:C-MCGD14=low & 15m:CHART.z2.STRUCT=down | 5.33 | 5.22 | 8.99 | 46.9 |  | hot,rep |
| 1m:C-EMA21=low & 60m:CHART.z2.STRUCT=up | 4.21 | 5.98 | 7.75 | 46.4 |  | hot,rep |
| 1m:C-SWAK_BUTTER20=low & 5m:CHART.z8.STRUCT=up | 3.25 | 4.54 | 10.2 | 46.3 |  | hot,rep |
| 1m:C-EMA9=low & 15m:CHART.z2.STRUCT=down | 4.38 | 3.73 | 12.4 | 46.3 |  | hot,rep |
| 1m:ACCBANDS20pos=low & 60m:CHART.z2.STRUCT=up | 3.75 | 5.96 | 7.74 | 46.1 |  | hot,rep |
| 1m:C-RMA14=low & 5m:CHART.z2.STRUCT=down | 6.36 | 4.95 | 9.29 | 46 |  | hot,rep |
| 1m:C-SMA20=low & 5m:CHART.z2.STRUCT=down | 5.79 | 4.60 | 9.99 | 46 |  | hot,rep |
| 1m:AROONup14=very low & 15m:CHART.z2.STRUCT=down | 3.40 | 3.11 | 14.8 | 45.9 | 12.7 | hot,rep,>twins |
| 1m:C-WMA20=low & 60m:CHART.z2.STRUCT=up | 3.57 | 5.13 | 8.93 | 45.8 |  | hot,rep |
| 1m:C-TRIMA20=low & 60m:CHART.z2.STRUCT=up | 3.81 | 5.72 | 8.01 | 45.8 |  | hot,rep |
| 1m:C-EMA9=low & 5m:CHART.z8.STRUCT=up | 3.44 | 4.66 | 9.81 | 45.7 |  | hot,rep |
| 1m:ERIbull13=low & 15m:CHART.z2.STRUCT=down | 4.97 | 4.13 | 11 | 45.6 |  | hot,rep |
| 1m:C-EMA9=low & 15m:CHART.z2.STRUCT=down | 4.33 | 3.71 | 12.3 | 45.6 |  | hot,rep |
| 1m:AROONOSC14=very low & 15m:CHART.z2.STRUCT=down | 4.22 | 5.85 | 7.77 | 45.5 |  | hot,rep |
| 1m:C-SWAK_GAUSS20=low & 5m:CHART.z8.STRUCT=up | 3.24 | 4.26 | 10.6 | 45.1 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -4.48 | -2.76 | 16.1 | 44.6 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 15m:CHART.z2.STRUCT=down | 3.79 | 2.79 | 15.9 | 44.4 |  | hot,rep |
| 1m:KC20pos=low & 5m:CHART.z8.STRUCT=up | 4.46 | 5.55 | 7.96 | 44.2 |  | hot,rep |
| 1m:PERCENTB20/2=low & 5m:CHART.z8.STRUCT=up | 3.67 | 4.75 | 9.25 | 43.9 |  | hot,rep |
| 1m:PERCENTB20/2=high & 240m:CHART.z2.STRUCT=contracting | -3.64 | -4.38 | 10 | 43.8 |  | hot,rep |
| 1m:IMI14=low & 5m:CHART.z4.STRUCT=down | 4.35 | 4.29 | 10.2 | 43.7 | 9.31 | hot,rep,>twins |
| 1m:PSO=low & 5m:CHART.z4.STRUCT=down | 3.95 | 4.23 | 10.2 | 43.1 |  | hot,rep |
| 1m:C-KAMA30 sign=below 0 & 15m:CHART.z2.STRUCT=down | 3.85 | 2.81 | 15.3 | 43 |  | hot,rep |
| 1m:CCI50=low & 15m:CHART.z2.STRUCT=down | 5.13 | 5.56 | 7.72 | 42.9 |  | hot,rep |
| 15m:BOP sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.32 | 3.21 | 13.4 | 42.9 |  | hot,rep |
| 1m:COPPOCK sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.30 | 2.62 | 16.4 | 42.9 |  | hot,rep |

#### XRP, 5 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| 1m:C-KAMA30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.53 | -2.12 | 59.5 | 126 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.49 | -2.15 | 57.9 | 125 |  | hot,rep |
| 1m:CCI50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.49 | -2.18 | 56.7 | 124 |  | hot,rep |
| 1m:C-EMA50 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.49 | -2.00 | 60.5 | 121 |  | hot,rep |
| 1m:MACD5/35 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.41 | -2.16 | 55.9 | 121 |  | hot,rep |
| 1m:AROONOSC25 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.41 | -2.24 | 53.8 | 121 | -12.1 | hot,rep,>twins |
| 1m:EMA9>EMA21=above & 5m:CHART.z2.STRUCT=up | -2.36 | -2.17 | 54.8 | 119 |  | hot,rep |
| 1m:C-VIDYA12 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.55 | -1.94 | 61.3 | 119 |  | hot,rep |
| 1m:APO12/26 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.40 | -2.17 | 54.1 | 118 | -15.4 | hot,rep,>twins |
| 1m:MAMA>FAMA=above & 5m:CHART.z2.STRUCT=up | -2.33 | -2.14 | 54.7 | 117 |  | hot,rep |
| 1m:WT1 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.37 | -2.12 | 54.8 | 116 |  | hot,rep |
| 1m:C-SUPERTREND10/3 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.33 | -2.22 | 52.1 | 116 |  | hot,rep |
| 1m:ERIbull13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.00 | -1.46 | 78.4 | 114 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 5m:CHART.z2.STRUCT=up | -3.05 | -2.26 | 50.5 | 114 |  | hot,rep |
| 1m:DIdiff14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.61 | -1.89 | 60.1 | 114 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.48 | -1.81 | 62.5 | 113 |  | hot,rep |
| 1m:C-KAMA30 sign=above 0 & 240m:CHART.z8.STRUCT=contracting | -0.54 | -2.11 | 53.1 | 112 |  | rep |
| 1m:AROONOSC25 sign=above 0 & 60m:CHART.z4.STRUCT=down | -1.48 | -1.96 | 57.1 | 112 |  | hot,rep |
| 1m:C-KAMA30 sign=below 0 & 15m:CHART.z2.STRUCT=down | 2.03 | 1.81 | 61.6 | 112 |  | hot,rep |
| 1m:PVT sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.34 | -1.74 | 63.6 | 110 |  | hot,rep |
| 1m:COPPOCK sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.13 | -2.01 | 54.6 | 110 |  | hot,rep |
| 5m:C-MAMA sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.37 | -2.29 | 48 | 110 |  | hot,rep |
| 1m:ERIbear13 sign=above 0 & 240m:CHART.z8.STRUCT=contracting | -0.51 | -2.41 | 45.6 | 110 |  | rep |
| 1m:C-VIDYA12 sign=above 0 & 240m:CHART.z8.STRUCT=contracting | -0.54 | -2.00 | 54.5 | 109 |  | rep |
| 1m:PVT sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.35 | 1.49 | 73 | 109 |  | hot,rep |
| 1m:C-MEDIAN30 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.41 | -1.79 | 60.3 | 108 |  | hot,rep |
| 1m:C-SAR sign=above 0 & 5m:CHART.z2.STRUCT=up | -1.91 | -1.78 | 60.6 | 108 |  | hot,rep |
| 1m:AROONOSC14 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.07 | -1.85 | 57.7 | 107 |  | hot,rep |
| 1m:C-EMA21 sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.47 | -1.68 | 63.6 | 107 |  | hot,rep |
| 1m:C-VIDYA12 sign=below 0 & 5m:CHART.z8.STRUCT=up | 1.62 | 2.04 | 52.1 | 106 |  | hot,rep |
| 1m:PVT sign=below 0 & 15m:CHART.z2.STRUCT=down | 1.46 | 1.47 | 71.5 | 105 |  | hot,rep |
| 1m:OBV sign=below 0 & 15m:CHART.z2.STRUCT=down | 1.30 | 1.46 | 71.9 | 105 |  | hot,rep |
| 1m:KST sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.35 | -1.98 | 52.8 | 105 |  | hot,rep |
| 1m:C-MAMA sign=above 0 & 5m:CHART.z2.STRUCT=up | -2.18 | -1.47 | 70.5 | 104 |  | hot,rep |
| 1m:C-EMA50 sign=below 0 & 5m:CHART.z8.STRUCT=up | 1.63 | 2.09 | 49.5 | 103 |  | hot,rep |
| 1m:C-SMA50 sign=above 0 & 60m:CHART.z4.STRUCT=down | -1.42 | -1.71 | 60.5 | 103 |  | hot,rep |
| 1m:AROONOSC14 sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.30 | 1.60 | 64.4 | 103 |  | hot,rep |
| 1m:CMF20 sign=above 0 & 60m:CHART.z4.STRUCT=down | -0.51 | -1.64 | 62.5 | 103 |  | hot,rep |
| 1m:ADOSC sign=above 0 & 60m:CHART.z4.STRUCT=down | -0.41 | -1.54 | 66.1 | 102 |  | rep |
| 1m:OBV sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.16 | 1.38 | 73.5 | 101 |  | hot,rep |

#### XRP, 60 minutes

| key | odds A | odds B | windows/day B | heat B | twins max | marks |
|---|---|---|---|---|---|---|
| FLOW:TB5=high & 5m:CHART.z4.STRUCT=up | -3.42 | -5.29 | 6.15 | 32.5 |  | hot,rep |
| 1m:AROONup25=very low & 5m:CHART.z4.STRUCT=down | 4.15 | 3.86 | 8.23 | 31.7 | -13.4 | hot,rep,>twins |
| 1m:IMI14=low & 5m:CHART.z4.STRUCT=down | 4.38 | 4.32 | 7.31 | 31.6 | -3.46 | hot,rep,>twins |
| 1m:STOCHK14=low & 5m:CHART.z2.STRUCT=down | 4.55 | 3.73 | 8.27 | 30.8 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z8.STRUCT=up | 2.61 | 4.86 | 6.19 | 30.1 |  | hot,rep |
| FLOW:TB15=high & 5m:CHART.z4.STRUCT=up | -3.18 | -6.55 | 4.6 | 30.1 |  | hot,rep |
| X.ETH:TakerBuy=high & 15m:CHART.z2.STRUCT=up | -2.62 | -3.87 | 7.69 | 29.7 |  | hot,rep |
| 1m:CCI14=high & 15m:CHART.z2.STRUCT=up | -4.81 | -3.99 | 7.34 | 29.3 |  | hot,rep |
| 1m:CCI14=low & 5m:CHART.z2.STRUCT=down | 5.00 | 3.28 | 8.92 | 29.3 |  | hot,rep |
| 1m:WT1 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.46 | 3.24 | 9 | 29.2 |  | hot,rep |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z2.STRUCT=down | 5.61 | 3.49 | 8.35 | 29.1 |  | hot,rep |
| 1m:AROONup14=very low & 5m:CHART.z4.STRUCT=down | 3.38 | 3.22 | 9.03 | 29.1 | -12.6 | hot,rep,>twins |
| 15m:BOP sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.19 | 3.33 | 8.71 | 29 |  | hot,rep |
| 1m:DIdiff14 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.57 | 3.17 | 9.14 | 29 |  | hot,rep |
| 15m:SI sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.21 | 3.40 | 8.47 | 28.8 |  | hot,rep |
| 1m:CG10=low & 5m:CHART.z2.STRUCT=down | 5.86 | 5.22 | 5.49 | 28.6 |  | hot,rep |
| 1m:CRSI=very low & 60m:CHART.z2.STRUCT=up | 2.95 | 7.34 | 3.88 | 28.5 |  | hot,rep |
| 1m:ERIbull13 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.53 | 3.09 | 9.21 | 28.5 | -0.753 | hot,rep,>twins |
| 1m:PERCENTB20/2=low & 5m:CHART.z8.STRUCT=up | 3.11 | 4.62 | 6.15 | 28.4 |  | hot,rep |
| X.ETH:TakerBuy=high & 15m:CHART.z2.STRUCT=up | -2.58 | -3.68 | 7.69 | 28.3 |  | hot,rep |
| 1m:PSO=low & 5m:CHART.z4.STRUCT=down | 3.49 | 3.89 | 7.25 | 28.2 |  | hot,rep |
| 1m:AROONup25=very high & 15m:CHART.z2.STRUCT=up | -5.48 | -4.04 | 6.97 | 28.2 |  | hot,rep |
| 1m:AROONup25=very high & 15m:CHART.z2.STRUCT=up | -5.13 | -4.08 | 6.9 | 28.2 |  | hot,rep |
| 1m:EFI13 sign=below 0 & 5m:CHART.z4.STRUCT=down | 1.97 | 3.41 | 8.24 | 28.1 |  | hot,rep |
| 1m:ADOSC=low & 5m:CHART.z8.STRUCT=up | 1.84 | 5.19 | 5.4 | 28 |  | hot,rep |
| 1m:Tenkan>Kijun=below & 5m:CHART.z4.STRUCT=down | 3.07 | 3.08 | 9.1 | 28 | 3.07 | hot,rep,>twins |
| FLOW:TB5=high & 5m:CHART.z4.STRUCT=up | -3.16 | -4.58 | 6.1 | 28 |  | hot,rep |
| 5m:C-MAMA sign=above 0 & 15m:CHART.z2.STRUCT=up | -4.54 | -3.72 | 7.49 | 27.9 |  | hot,rep |
| X.SOL:RSI14=low & 15m:CHART.z2.STRUCT=down | 3.98 | 4.75 | 5.86 | 27.8 | -0.686 | hot,rep,>twins |
| 1m:CCI14=low & 5m:CHART.z2.STRUCT=down | 4.89 | 3.12 | 8.9 | 27.8 |  | hot,rep |
| 1m:AO sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.37 | 3.09 | 8.97 | 27.7 |  | hot,rep |
| 1m:AROONOSC14=very low & 5m:CHART.z4.STRUCT=down | 4.32 | 4.37 | 6.32 | 27.6 |  | hot,rep |
| 1m:COPPOCK sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.23 | 3.01 | 9.19 | 27.6 |  | hot,rep |
| 1m:MACD5/35 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.86 | 3.12 | 8.76 | 27.4 |  | hot,rep |
| 1m:DONCHIAN55pos=very low & 15m:CHART.z8.STRUCT=up | 5.89 | 6.90 | 3.94 | 27.2 |  | hot,rep |
| 1m:AROONOSC14 sign=below 0 & 5m:CHART.z4.STRUCT=down | 3.15 | 2.92 | 9.3 | 27.2 |  | hot,rep |
| 1m:MFI14=high & 15m:CHART.z2.STRUCT=up | -5.82 | -4.58 | 5.92 | 27.1 |  | hot,rep |
| 1m:C-MCGD14 sign=above 0 & 15m:CHART.z2.STRUCT=up | -4.36 | -3.35 | 8.06 | 27 |  | hot,rep |
| 1m:AROONup14=very low & 5m:CHART.z4.STRUCT=down | 3.08 | 2.98 | 9 | 26.9 | -9.98 | hot,rep,>twins |
| 1m:C-SUPERTREND10/3=low & 5m:CHART.z2.STRUCT=down | 5.25 | 3.20 | 8.33 | 26.7 |  | hot,rep |
<!-- /hm2:section:part4 -->

## Series

One series per coin and twin; the hash is the sha256 of heat.csv.gz unzipped (the re-measured rows).

| series | minutes | readings | A entries | B entries | complete | seconds | peak MB | table sha256 |
|---|---|---|---|---|---|---|---|---|
| BTC | 3,156,480 | 1349 | 375,370 | 525,540 | yes | 6839.6 | 10356.4 | 313164b48b034b63e57d1e76af806c9ee303dd113ae1d3660cd51cc33c657df7 |
| BTC~twin1 | 3,156,480 | 1349 | 375,370 | 525,540 | yes | 4504.9 | 10418.2 | bc0d557bc9c10aa2c7e778ebe0fd1aec783345eeebdf37156457432de4d603c0 |
| BTC~twin2 | 3,156,480 | 1349 | 375,370 | 525,540 | yes | 6229.2 | 10340.9 | fb8f6480a688d4ed547e34d44b05c04907aeb0eaff685fbc261ac744c7e3cd1d |
| BTC~twin3 | 3,156,480 | 1349 | 375,370 | 525,540 | yes | 5260.3 | 10464.9 | 8c48ca26c40835e49d6eb99dec3100c53885974a5cabae622d591f2d3f91711f |
| ETH | 3,156,480 | 1351 | 375,370 | 525,540 | yes | 7653.9 | 10548.0 | 892c3f2ea72bb5e5853b208025ee6fb5069b74dc347ca30b7276e89e24887496 |
| ETH~twin1 | 3,156,480 | 1351 | 375,370 | 525,540 | yes | 5019.9 | 10487.4 | a333daa26ff56d72d1613b943e4d556568cd041e49b413fe593d28cd5754e68e |
| ETH~twin2 | 3,156,480 | 1350 | 375,370 | 525,540 | yes | 4519.2 | 10372.0 | ab4d06344e56611913d5de818576a11ccd718cba453af54332e3700827ce6cbb |
| ETH~twin3 | 3,156,480 | 1351 | 375,370 | 525,540 | yes | 6557.3 | 10451.5 | 2dcc42eb3209ed7dda8c07d4f03406a9d2927ca479aab02bb738250fdbc0533a |
| SOL | 2,833,920 | 1355 | 329,452 | 525,540 | yes | 5411.2 | 9616.2 | 2848b8789e3bdc683ca833797a33d965305e12b95be222768b38e68593f0e080 |
| SOL~twin1 | 2,833,920 | 1355 | 329,452 | 525,540 | yes | 4748.1 | 9587.6 | a2e21825405cec91f4e8b423aca43550828009bb889f6f971dd5f0b2a4806659 |
| SOL~twin2 | 2,833,920 | 1355 | 329,452 | 525,540 | yes | 5953.2 | 9717.7 | e91000b395d8991885e803a86b420736cca2858756fc80b64b72f6cc2ea75642 |
| SOL~twin3 | 2,833,920 | 1355 | 329,452 | 525,540 | yes | 3863.2 | 9592.5 | ed75aad40f3411e721c7b78155826254e9ed8a9faba77c1e2352f4e7bd2320d0 |
| XRP | 3,156,480 | 1354 | 375,370 | 525,540 | yes | 6332.9 | 10515.1 | 9017acbc56322b017c9d6f274c68cdbad464934394549ec055e5c0087d449b0c |
| XRP~twin1 | 3,156,480 | 1353 | 375,370 | 525,540 | yes | 6340.2 | 10436.1 | 468a99ec22ff8ea1bef20bf97c8ae91a9ad27a568228da87fcaf668832970baf |
| XRP~twin2 | 3,156,480 | 1353 | 375,370 | 525,540 | yes | 5244.3 | 10381.4 | 2d8c151a76968ebb1ae486b6ed136bbae165a1ea081ec1479837a4c6a5364865 |
| XRP~twin3 | 3,156,480 | 1353 | 375,370 | 525,540 | yes | 4303.5 | 10418.4 | a89563bd3f8c964d5b54678bbd434ef679540deef1ec2c444b76a1045e23f603 |
