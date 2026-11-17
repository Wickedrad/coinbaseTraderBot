# Resting-exit fill probe (python/exitfill)

Research only. Nothing here touches the bot, the heat curves, the heat reader or the all-pairs guardrails
(`allpairs.fees` is imported read-only). Information only: no pass bar, no threshold, no verdict.

## Question

The heat lane exits with a reduce-only IOC at the bid minus two ticks, so both legs pay the taker fee (headroom report:
$101.24 of exit fees on 203 paper trips, at most $63.17 recoverable on the 105 non-urgent exits). If a **resting sell**
had been placed at the decision moment instead, would it have filled, how fast, at what price, and what would the
fallback IOC have cost?

## Data

* Heat shadow capture books (public Kalshi YES books, top 3 levels, about every 10 s), six 3-hour segments, rows kept
  for 2026-11-11T22:55Z to 2026-11-12T13:00Z. Only `books.jsonl.gz` and `markets.jsonl.gz` are opened.
* `exits.csv`: the 105 non-urgent paper exits (74 `plan_ratchet_sell`, 31 `other_sale`). Columns: ticker, held
  side, exit event, decision time, contracts, the bid the bot logged and its IOC limit (ratchet only). **No entry price,
  profit or strike**, so no per-trip profit can be rebuilt from it. Built offline by `build_exits.py`.
* Floor 2026-11-10T03:44Z (`guard.py` aborts before any download). DOGE is never read.

## Frozen rules (changing any of these means a new rules hash and a new read-log row)

* Decision time t0: the plan sale event time (ratchet) or the closed record time (other_sale, shifts -2/-1/0 s shown).
* Placement book s0: the last sample whose response ended at or before t0. Placement time tp = t0 + 1 s (a modelling
  slack, not a measured latency). Evidence samples: requested at or after tp and finished by tp + H, H in 30/60/120 s.
* Variants (held-side prices): `JOIN_ASK` rests at the best ask (queue ahead = the displayed size), `INSIDE` one tick
  under the best ask, `BID_PLUS_1C` one cent over the best bid. n/a when not strictly inside the spread, or when the
  price is at or below the bid the bot logged (it would have been a taker).
* Fill, book-implied, stricter: a held-side bid at or above q + 1 tick is displayed; filled min(N, displayed size at or
  above q + 1 tick) at q. Looser: best bid at or above q; filled min(N, displayed size at or above q). Maker fee 0
  (published) with a stress column at the full rate; a fill already visible in the very first evidence sample is priced
  as a taker fill. An ask level that disappears while the bid never reaches q is counted as ambiguous, not credited.
* Fallback at tp + H: cancel and one IOC for the unfilled remainder at the held bid minus two ticks on the last book
  known at that moment, walking the 3 stored levels, with the taker fee charged per level fill (as the paper exchange
  does). Contracts the levels cannot absorb, or that meet no bid, earn **zero in every arm** and are counted.
* Controls: `IOC_NOW` (model sell at t0 on s0) and `WAIT` (no order, same fallback IOC at tp + H, the pure price
  drift). Resting minus WAIT isolates what resting adds.
* Event-horizon drops are identical for every arm: sample older than 25 s at t0 or at the fallback, a hole over 25 s,
  no held-side bid at s0, or the horizon ending within 5 s of contract close.
* **Headline cell, declared before the first run: ratchet, INSIDE, 60 s, strict.** Everything else is a descriptive
  grid on correlated events (extremes of a noisy grid are selected). other_sale is its own block ("type unknown") and is
  never pooled with ratchet. Dollar means carry a 15-minute-block bootstrap SE; they are below the resolution of one
  overnight unless the interval clearly excludes zero, and the fill-count tables are the sturdier output.

## Running it

A push to `claude/project-thread-eqduzm` that changes `python/exitfill/**` runs the unit tests only. The study runs only
when the pushed commit changes `python/exitfill/RUN`, which must carry `readlog=<id>` (the read-log row in the
edge-pipeline calendar, written first) and `run=<n>`:

```
artifacts=heat-shadow-43051376882-9,heat-shadow-43051376882-10,heat-shadow-43138942198-1,heat-shadow-43138942198-2,heat-shadow-43138942198-3,heat-shadow-43138942198-4
from=2026-11-11T22:55:00Z
to=2026-11-12T13:00:00Z
readlog=<id>
run=1
```

The job posts one commit comment with the card (aggregates only: no ticker, no per-event time, no per-event row).
A rerun with the same window and artifacts is a deliberate new push of RUN (`run=2`); a different window, artifact
or file gets a new read-log row first. Do not push RUN within about 10 minutes of a :25 UTC capture handoff.
