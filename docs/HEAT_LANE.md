# Heat entry lane

The heat lane trades the oracle's weighted direction curves (the "heat maps") on Kalshi's crypto contracts, in paper and live alike. A curve row says which way a coin tended to move over the next 15 or 60 minutes after a TA reading closed at a given level, how often it went that way (share) and how hot the row is (its rank among the coin's rows). When a row fires, the lane buys the called side of the matching contract with one immediate-or-cancel order at the touch. It opens entries only: the plan positions' exits (the cleanup thread's PLAN_RULES) manage every heat position from the moment it is sent.

Steven's brief (Nov 11 2026, 10:23 to 10:49 AM EST / 15:23 to 15:49 UTC): today's weighted heat maps in both live and paper; the curves inform entry and direction for the 15-minute and 1-hour price prediction contracts; a curve for the hour is context for a 15-minute contract inside that hour; on the perps they inform direction and entry on the hourly and daily timeframe (since Nov 11 1:09 PM EST / 18:09 UTC: entries on the hour and on 4 hours, the day as direction context; see the perps section below). The curves are this project's oracle direction curves, not the Atlas maps.

Code: `bot/heat/` (types, the file source, the lane and its book), the engine hook (`bot/engine.ts`, `heatTick` and the methods after it at the end of the class), the perps hook (`bot/setups/setupTrader.ts`), the wiring (`bot/main.ts`) and the settings (`bot/config.ts`, `heat`). Tests: `tests/heatLane.test.ts`, `tests/heatSource.test.ts`, `tests/heatEngine.test.ts`, `tests/heatPerps.test.ts`.

## How a call becomes an entry

1. **The reader** (`python/heat_reader`, outside the bot) runs the oracle's own reading code once a minute on Binance spot minutes and writes `HEAT_CALLS_FILE` atomically: per coin, the curve rows that fired at the last closed minute.
2. **The source** (`FileHeatSource`) re-reads the file when it changes and checks it. A missing or malformed file gives no snapshot; nothing throws.
3. **The engine** calls the lane once a second, after the old lane's evaluations and before the perps run. When no call waits to be ruled on, that is all it does.
4. **The lane** decides, per coin and horizon, one call and at most one plan (below). Every call it rules on gets exactly one plan or one skip with a plain reason, and is claimed under `asset:horizon:barClose`, so a call is acted on once however often the engine ticks.
5. **The entry**, for each plan: the engine takes the market's busy lock, cancels every resting order of ours on that market (on a flat market these are old-lane quotes: one that crosses would make live Kalshi's self-trade prevention cancel the entry, which paper does not simulate, and one that does not could fill later and stack on or flip the position), writes the decision record, tags the position with the exits' owner, records the entry in the lane's book, and sends the order through `placeChecked`, the same path and risk checks as every other entry. Rejected, refused, or filled nothing: the lane lets go of the market at once and the tag comes off. From the moment the entry is sent until the round trip closes the lane holds the market, and the old lane adds nothing there: the evaluation passes `entries: false` to `decide()` for it, and `placeChecked` refuses any other order that adds risk on it (the gateway's reason: "the heat lane holds this market"), so a `decide()` call that misses the flag still cannot add to or flip the position. Exits go out as usual.
6. **The book** follows the position book every second: an entry is open once a position shows; it closes when the position is flat again or the market settles (P&L = the change in the market's cash less the change in its fees since the entry was sent; at settlement, the position book's realized figure). An entry never seen open 30 s after it was sent is dropped and its tag comes off.

The order: immediate-or-cancel, not post-only, not reduce-only, `purpose: 'entry'`. UP buys YES at the YES ask; DOWN buys NO by selling YES at the YES bid. `modelId` is `heat:<run>`, `why` starts with `heat ` (for example `heat BTC 15m up 1m:RSI14=very low rank 3/10 ctx agree`), and the order's fair value is the YES mid moved by the row's odds toward the called side, kept inside 1c to 99c. For heat orders the gateway skips the fee-net edge collar (unless `HEAT_FEE_NET_CHECK=true`) and the old model's live validation gate; every other check applies (halts, kill switch, book and index freshness, touch collar, side price band, 15 s to close, free cash, open orders, rate limit, waterfall).

## Which contract a curve trades

| Curve | Contract | How |
|---|---|---|
| 15-minute (h=15) | the coin's 15-minute contract (`KX<COIN>15M`) | the one inside the 15-minute entry window (`ENTRY_WINDOW_15M`, 840 to 300 s before close by default) |
| 60-minute (h=60) | the coin's hourly strike (`KX<COIN>D`, YES above the strike) | among the strikes inside the hourly entry window (`ENTRY_WINDOW_HOURLY`, 3300 to 600 s) with a two-sided book and a YES mid inside `HOURLY_MID_BAND` (10c to 90c), the one whose mid is nearest 50c (ties: the nearer close, then the ticker) |
| 60-minute, as context | the 15-minute contract inside that hour | every decided 60-minute call is the coin's hour direction until its hour is over, traded or not. With `HEAT_CONTEXT=size` a 15-minute entry the hour agrees with gets weight + `HEAT_CONTEXT_BOOST` (at most 1), one it disagrees with goes at `ORDER_USD_MIN`; `block` makes no entry against the hour; `off` ignores it |
| 60-minute, perps | the coin's perp, 1h (`HEAT_PERPS`) | `log` journals the hour's direction beside every setup; `gate` also keeps a 1-hour setup against it out; `entry` also opens a setup of kind `heat` on 1h when a 60-minute call fires (below) |
| 240-minute (perp pack) | the coin's perp, 4h, never a Kalshi contract | `entry` opens a setup of kind `heat` on 4h when a 240-minute call fires (below) |
| 1440-minute (perp pack) | none: direction context for the perps only | a heat perp entry against the coin's live daily call is not made (`HEAT_PERPS_DAILY=context`, below) |

A market qualifies only with a two-sided book, the called side costing between `RISK_MIN_SIDE_PRICE` and one minus it, a spread under the plan's loser cut (`PLAN_LOSER_CUT_C`, 10c: bought at the ask with the bid already that far under, the cut would sell at the first look), no position of any lane (no adds, no flips), its fee schedule verified, the re-entry rule after a loss (below), and, for a contract the lane already traded, more than half of its window left.

**Re-entry after a loss** (Steven, Nov 11 6:59 PM EST / 23:59 UTC: the loser cut's 10c "doesn't invalidate a signal"; his card at 7:05 PM EST / 00:05 UTC chose the loss stop, and at 8:08 PM EST / 01:08 UTC he raised the counts to 3 and 6). A contract window the lane left at a loss (the loser cut, mostly) is entered again only on a call whose bar closed after that loss: the TA is judged again, and the call's side is the side bought, so a call that turned buys the other side and no call means no entry. Every other check applies as for a first entry (the cooldown, the price band, the spread). More than half of the window must be left; at most `HEAT_REENTRIES_15M` (3) re-entries on a 15-minute contract and `HEAT_REENTRIES_HOURLY` (6) in an hourly window, whose strikes count together, counting every entry sent into the window after its first loss whatever it made (finished or still open); and none once the window's losses reach `HEAT_REENTRY_LOSS_STOP` (0.5) of one order (the largest stake the lane lost there: about $5 on a $10 order, where one 10c cut on a 50c contract costs about $2.70 with fees). The book keeps the count per window (`losses` in `heat_state.json`: first loss, re-entries, losses, dollars), pruned once the window is over. A loss recorded by the build before the count (a file with `lossTickers` and no `losses`) is read into `noReentry`: that contract keeps the old rule, no re-entry, until it closes, and its loss is not in its window's count.

**The loser cut** is the plan exits' (`bot/plan/planRatchet.ts`, E05; Steven, Nov 11 6:56 PM EST / 23:56 UTC: "10c a contract"): a heat position whose held-side bid is `PLAN_LOSER_CUT_C` (10c) or more under its entry price is sold the way the ratchet sells (an immediate-or-cancel at the bid less 2 ticks, retried, 3 ticks after 3 failed tries). `PLAN_LOSER_CUT_USD` cuts on dollars of the trade's net instead or as well (off by default; the entry guard above covers the cents cut only, so set it above a heat order's spread plus round-trip fees). A try that failed is called off once the position is back at or above break-even after fees (a dollar cut only once the trade, what partial sales banked included, is also back over its line). The end rule stays as it was.

## The perps: entries on the hour and on 4 hours, the day as context

Steven wants the curves to inform the perpetuals on the hourly and daily timeframe. The oracle thread measured the long horizons in its perp packs (`research/oracle_heat/latest/perp_pack.json` and `perp_pair_pack.json`, oracle commit 52edf4c on `claude/project-thread-nvd096`; the perp packs first landed at b097ee2), each against a no-signal twin on the check year (2025):

| Horizon | Kept its direction (curve / twin) | Top heat (curve / twin's best) | Role on the perps |
|---|---|---|---|
| 60 minutes (traded and pair packs) | see the traded pack | see the traded pack | entry on 1h |
| 240 minutes | 69.6% / 51.1% | 18.3 / 12.6 (123 of 240 single rows above the twin's best) | entry on 4h |
| 1440 minutes | 66.5% / 51.0% | 6.9 / 9.3 (no single row above the twin's best) | direction context only |

The decision (adopted Nov 11 1:09 PM EST / 18:09 UTC, `SPEC.md` Addendum 4): the perps enter on the hour and on 4 hours, and the daily curve is direction context only. A daily row keeps its direction more often than chance, but none is hotter than the best the no-signal twin reaches by luck, so a daily call is never a trigger of its own; it only keeps a heat entry from going against the day.

**The lane** decides the 240- and 1440-minute calls like the others (the hottest firing row per coin and horizon inside `HEAT_TOP_N`, a refining pair or triple replacing its single, a pair against its single giving no direction) and keeps each coin's latest one: `four(asset, now)` is the latest decided 240-minute call while its bar close plus 240 minutes is ahead, `day(asset, now)` the latest decided 1440-minute call while its bar close plus 1440 minutes is ahead (nothing with `HEAT_PERPS_DAILY=off`), and `fired(asset, 240, now)` serves the call that just fired, as it does for 60. Both directions are saved in the lane's state file with the hour's; a state file written before them loads with both empty. Neither call ever opens a Kalshi contract: the lane rules on each once and records it as "perps context" (the audit row's `skip` starts with `perps context:`), and `HEAT_HORIZONS` refuses 240 and 1440 at start. These calls fire again minute after minute, so the engine writes their audit row only when a coin's call at that horizon is new, changes key or side, or comes back after the last one ran out, and the status's last calls leave them out (the status shows them as each coin's 4-hour and daily direction instead).

**The heat setups** (`HEAT_PERPS=entry`, `bot/setups/setupTrader.ts`), both in the fast lane, scored by the heat weight (not by the setup model), with the perp stop rule (`PERP_STOP_ATR_MULT` x the timeframe's ATR from the entry, at least `PERP_MIN_STOP_BPS`), no target and no trail:

| | 1h heat setup | 4h heat setup |
|---|---|---|
| Call | a decided 60-minute call | a decided 240-minute call |
| Stop | the 1h ATR | the 4h ATR (the candle store's 4h bars, built from complete groups of four 1h bars aligned to 00/04/08/12/16/20 UTC) |
| Ends | at the next hourly close | at the next 4-hour close |
| Carried through that close | while the latest 60-minute call has the trade's side and reaches at least 30 minutes past the close | while the latest 240-minute call has the trade's side and reaches at least 2 hours past the close |

The same five rules for both: each call is ruled on once; none is offered while the coin has an open trade; a weight under the minimum does not queue (and leaves the clock hour free); at entry the call's own horizon must still point the trade's way (the hour for 1h, the 4 hours for 4h), else the candidate is dropped; and a trade is carried through its close instead of being closed and opened again. A close is ruled on 90 s after it, so the reading taken at the close is part of the decision.

**One heat perp entry per coin per clock hour across both horizons.** When a 60-minute and a 240-minute call fire in the same minute, the hotter weight is offered and a tie goes to 4h; the other is journaled with the reason. A call refused for a reason that leaves the hour free (against the day, under the minimum, no ATR) leaves room for the other horizon's call. A candidate that waits in the queue past its clock hour is dropped.

**The day** (`HEAT_PERPS_DAILY=context`): a heat perp offer, 1h or 4h, against the coin's live daily call is not made (journal `why`: "against the day's direction (<key>)"); a queued heat candidate is dropped at the re-check when a live daily call now points against it; and a heat trade is not carried through a close against it (a carry stands for a new entry). No daily call: no effect. `off`: the lane reads no daily rows and the trader never asks for the day. In `gate` mode the chart setups are gated as before (the hour gates 1h setups) and the day gates nothing.

The setup trader itself is described in `docs/SETUPS.md`; its status shows the heat mode, the horizons that enter and the day's role under `inputs.heat`.

**The journal** (`bot/setups/journal.ts`) carries, beside the hour's `heat_*` fields, `heat_four_dir`, `heat_four_agree`, `heat_four_key`, `heat_day_dir`, `heat_day_agree` and `heat_day_key`, and a heat signal says which horizon called it (`call_h`), so the 4-hour and daily curves can be measured on real perp trades.

## The decided call, pairs and relatives

Per coin and horizon, from a fresh snapshot only (the coin's reader says ok and its last closed minute is at most `HEAT_MAX_AGE_SEC` old), rows that fired within `HEAT_ENTRY_LAG_SEC` of their bar close:

- **The decided single** is the hottest firing single (lowest rank) inside the batch, `rank <= HEAT_TOP_N`.
- **Pairs and triples** (rows of the pair pack: the trigger event plus conditions on other readings) that refine it, their trigger being the single's key or one of its aliases, replace it, even when their own rank is beyond `HEAT_TOP_N`. A triple before a pair, then the higher heat. The replacement keeps the hotter of the two ranks (it sizes at least as the single would).
- **A pair against its single**: with `HEAT_PAIR_CONFLICT=skip` (default) there is no entry ("pair against single"), no hour context and nothing for the perps; with `pair` the pair's side trades.
- **A pair on another trigger** (one that is not the decided single) trades on its own only inside the batch. The hottest of all these candidates is the call. Nothing is averaged.
- **Relatives**: a row's aliases are the same event under another reading's name. They are one bet, never a second row and never counted against. The hottest rows of a coin are often close relatives that fire together; the lane still takes one call per coin and horizon.

## Size and how many

- **Weight (E07)**: with `N` the batch (`HEAT_TOP_N`, never more than the pack lists) and `peak = max(1, ceil(N / 10))`, the weight is 1 for the hottest tenth and falls in a straight line to 0 at rank `N`.
- **Stake**: `ORDER_USD_MIN + weight x (ORDER_USD_MAX - ORDER_USD_MIN)` for the hottest slot once the flat phase is over (`HEAT_SIZING=true`), else `ORDER_USD_MIN`. Whole contracts at the touch, at least one.
- **One entry per coin a minute** (the higher weight of its 15-minute and hourly candidates, the 15-minute one on a tie) and at most `HEAT_MAX_PER_COIN` open heat positions per coin.
- **Decision 8** (`HEAT_MAX_OPEN=2`): with no heat position open the hottest plan is slot 1 at heat size and the next slot 2 at `ORDER_USD_MIN`; with one open, the only plan is slot 2; with two open, none. Hourly positions count.
- **Decision 11** (`HEAT_FLAT_TRIPS=30`): until the book has that many finished heat round trips, one heat position at a time and every stake `ORDER_USD_MIN`. Paper and live each count their own book.
- **Cooldown**: no new heat entry on a coin within `HEAT_COOLDOWN_SEC` of its last heat exit.

## The one difference between paper and live

The pilot budget (decision 6, `HEAT_PILOT_LOSS_USD=15`): in live, no new heat entries once the live book's realized heat P&L reaches minus this amount, with one alert. Paper counts and reports it in the status but never stops on it. This is deliberate: the budget is a live-money limit. Everything else, settings and code path alike, is the same in both modes, and each book keeps its own lane state (`heat_lane_state.json` in `DATA_DIR` for paper, `DATA_DIR/live` for live).

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `HEAT_LANE` | `false` | Master switch. Off: no heat entries (and the perps hook is off). New behaviour is off until it is approved. |
| `HEAT_CALLS_FILE` | `<DATA_DIR>/heat_calls.json` | The reader's file. |
| `HEAT_ASSETS` | `BTC,ETH,SOL,XRP` | Coins the lane trades. DOGE is dropped whatever the list says. |
| `HEAT_HORIZONS` | `15,60` | Horizons that open contracts: 15 the 15-minute contract, 60 the hourly. The 60-minute call is always read as context. 240 and 1440 are refused at start: they are perps horizons. |
| `HEAT_TOP_N` | `10` | The batch: only rows ranked this hot or hotter trade (refining pairs excepted); 0 = every row. |
| `HEAT_MAX_AGE_SEC` | `90` | A coin whose last closed minute is older gives no entries; a file written more than twice this long ago is ignored altogether. |
| `HEAT_ENTRY_LAG_SEC` | `45` | A fired row opens an entry only this long after its bar closed. |
| `HEAT_SIZING` | `true` | Heat size for slot 1 after the flat phase; false = flat `ORDER_USD_MIN`. |
| `HEAT_CONTEXT` | `size` | The hour's call on a 15-minute entry: `size`, `block` or `off`. |
| `HEAT_CONTEXT_BOOST` | `0.25` | Weight added when the hour agrees. |
| `HEAT_MAX_OPEN` | `2` | Open heat positions across all coins (decision 8). |
| `HEAT_MAX_PER_COIN` | `1` | Open heat positions per coin, 15-minute and hourly together. |
| `HEAT_COOLDOWN_SEC` | `60` | Wait after a heat exit before the next heat entry on the coin. |
| `HEAT_REENTRIES_15M` | `3` | Re-entries after a loss on one 15-minute contract (above); 0 = never. |
| `HEAT_REENTRIES_HOURLY` | `6` | Re-entries after a loss in one hourly window, its strikes together; 0 = never. |
| `HEAT_REENTRY_LOSS_STOP` | `0.5` | No re-entry once the window's losses reach this share of one order; 0 = off. `HEAT_REENTER_AFTER_LOSS` is retired (the bot refuses to start with it; ensure-env drops the line). |
| `HEAT_FLAT_TRIPS` | `30` | Decision 11's flat phase, in round trips per book. |
| `HEAT_PILOT_LOSS_USD` | `15` | Live only: the heat loss budget; 0 = off. |
| `HEAT_FEE_NET_CHECK` | `false` | Also apply the gateway's fee-net edge collar to the heat value. Off: the proof standard is the one test, not a cost bar. |
| `HEAT_PERPS` | `entry` | Perps: `off`, `log`, `gate` or `entry` (above). Acts only with `HEAT_LANE` on. With `off` the lane reads no 240- or 1440-minute rows. |
| `HEAT_PERP_HORIZONS` | `60,240` | The horizons whose calls open a perps heat setup (with `HEAT_PERPS=entry`): 60 on 1h, 240 on 4h. Only these two values. |
| `HEAT_PERPS_DAILY` | `context` | The daily call on the perps: `context` keeps a heat perp entry against the coin's live daily call out; `off` reads no daily rows. There is no `entry` value. |
| `HEAT_PAIR_CONFLICT` | `skip` | A refining pair against its single: `skip` or `pair`. |

Settings it reuses: `ORDER_USD_MIN` and `ORDER_USD_MAX` (the stake band; `HEAT_LANE=true` refuses to start with `ORDER_USD_MIN=0`), `RISK_MIN_SIDE_PRICE`, `ENTRY_WINDOW_15M`, `ENTRY_WINDOW_HOURLY`, `HOURLY_MID_BAND`, and for the perps `PERP_STOP_ATR_MULT` and `PERP_MIN_STOP_BPS`. The reader has its own (`HEAT_READER_MAX_RANK`, `HEAT_CLOCK_PACK` and the ones in `docs/HEAT_READER.md`).

## What the operator sees

- **Status**: `guards.heat` in the dashboard's status JSON: whether the lane is on and has an exits' owner, the reader's file (age, coins, rows), open heat positions, trips, wins, P&L, the flat phase, the pilot budget left, each coin's hour, 4-hour and daily direction, the last calls ruled on (15 and 60 minutes only) and why the file or a coin gave nothing.
- **Audit**: kind `heat`, one compact row per call ruled on (coin, horizon, key, side, rank, rows fired and against, the single a pair replaced, context, and the plan with what became of it, or the skip reason), plus rows for entries seen open, round trips closed and the reader's file going stale or coming back. Each entry also writes a `decision` row with `lane: 'heat'` and a `heat` object (the call, weight, slot, stake, count, fair value, rule id, run and pack hash).

## Before it is switched on

All of these must be true before `HEAT_LANE=true` goes into the server's `bot.env` (Steven's approval):

1. **The oracle branch is merged** (`python/oracle`, branch `claude/project-thread-nvd096`, pinned at fd88805), so the reader runs the same reading code the curves were measured with. The perps' 4-hour and daily calls need the reader on the perp packs (oracle commit b097ee2 or later, 52edf4c adds only notes); without them the perps trade the hour only and the day has no say.
2. **The plan exits are on** (`PLAN_RULES=true`; merged with #326). Without them the old model's exit would sell a heat position on its next tick, so `HEAT_LANE=true` refuses to start without them (`heatStartCheck(cfg, cfg.plan.enabled)` in `bot/main.ts`). With them, `bot/main.ts` hands the lane `engine.planPositions.tag` (before the order) and `forget` (an entry that filled nothing), and the engine applies the hold exits' re-entry rule (`holdExits.reentryBlock`) to every heat market. Both `decide()` objects carry `&& !this.d.heat?.lane.holds(m.ticker)` on `entries:` (a filled heat position is a plan position, so the plan branch is the one it takes), and `placeChecked` refuses any other risk-adding order on a heat-held market as a backstop. `tests/heatEngine.test.ts` checks it end to end: with `PLAN_RULES=true` a heat fill is a plan position, no other order goes on its market, and the plan's ratchet arms at +$1.50.
3. **The reader is running**: `deploy/heat_reader_install.sh` installs and starts `heat-reader.service` only while `HEAT_LANE=true`, and the status shows the calls file fresh with every coin ok.
4. `ORDER_USD_MIN` is above 0.

Live additionally needs the usual live conditions (`docs/DEPLOY.md`): cash on the crypto shard for the stakes (two positions at most), the waterfall not armed at a small bankroll, and the kill override or the soft pause in place.
