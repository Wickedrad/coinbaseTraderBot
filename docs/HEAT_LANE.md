# Heat entry lane

The heat lane trades the oracle's weighted direction curves (the "heat maps") on Kalshi's crypto contracts, in paper and live alike. A curve row says which way a coin tended to move over the next 15 or 60 minutes after a TA reading closed at a given level, how often it went that way (share) and how hot the row is (its rank among the coin's rows). When a row fires, the lane buys the called side of the matching contract with one immediate-or-cancel order at the touch. It opens entries only: the plan positions' exits (the cleanup thread's PLAN_RULES) manage every heat position from the moment it is sent.

Steven's brief (Nov 11 2026, 10:23 to 10:49 AM EST / 15:23 to 15:49 UTC): today's weighted heat maps in both live and paper; the curves inform entry and direction for the 15-minute and 1-hour price prediction contracts; a curve for the hour is context for a 15-minute contract inside that hour; on the perps they inform direction and entry on the hourly (and later daily) timeframe. The curves are this project's oracle direction curves, not the Atlas maps.

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
| 60-minute, perps | the coin's perp, hourly timeframe (`HEAT_PERPS`) | `log` journals the hour's direction beside every setup; `gate` also keeps a 1-hour setup against it out; `entry` also opens a setup of kind `heat` on the hourly timeframe when a 60-minute call fires, once per call, held to the next hourly close (extended when the next hour's call has the same side), stop 2 x the 1-hour ATR. See `docs/SETUPS.md` for the setup trader |
| daily | none yet | today's curves stop at 60 minutes; the daily timeframe waits for a daily curve (`day()` returns nothing) |

A market qualifies only with a two-sided book, the called side costing between `RISK_MIN_SIDE_PRICE` and one minus it, no position of any lane (no adds, no flips), its fee schedule verified, not just left at a loss by the lane (unless `HEAT_REENTER_AFTER_LOSS`), and, for a contract the lane already traded, more than half of its window left.

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
| `HEAT_HORIZONS` | `15,60` | Horizons that open contracts: 15 the 15-minute contract, 60 the hourly. The 60-minute call is always read as context. |
| `HEAT_TOP_N` | `10` | The batch: only rows ranked this hot or hotter trade (refining pairs excepted); 0 = every row. |
| `HEAT_MAX_AGE_SEC` | `90` | A coin whose last closed minute is older gives no entries; a file written more than twice this long ago is ignored altogether. |
| `HEAT_ENTRY_LAG_SEC` | `45` | A fired row opens an entry only this long after its bar closed. |
| `HEAT_SIZING` | `true` | Heat size for slot 1 after the flat phase; false = flat `ORDER_USD_MIN`. |
| `HEAT_CONTEXT` | `size` | The hour's call on a 15-minute entry: `size`, `block` or `off`. |
| `HEAT_CONTEXT_BOOST` | `0.25` | Weight added when the hour agrees. |
| `HEAT_MAX_OPEN` | `2` | Open heat positions across all coins (decision 8). |
| `HEAT_MAX_PER_COIN` | `1` | Open heat positions per coin, 15-minute and hourly together. |
| `HEAT_COOLDOWN_SEC` | `60` | Wait after a heat exit before the next heat entry on the coin. |
| `HEAT_REENTER_AFTER_LOSS` | `false` | May the lane re-enter a contract it left at a loss. |
| `HEAT_FLAT_TRIPS` | `30` | Decision 11's flat phase, in round trips per book. |
| `HEAT_PILOT_LOSS_USD` | `15` | Live only: the heat loss budget; 0 = off. |
| `HEAT_FEE_NET_CHECK` | `false` | Also apply the gateway's fee-net edge collar to the heat value. Off: the proof standard is the one test, not a cost bar. |
| `HEAT_PERPS` | `entry` | Perps: `off`, `log`, `gate` or `entry` (above). Acts only with `HEAT_LANE` on. |
| `HEAT_PAIR_CONFLICT` | `skip` | A refining pair against its single: `skip` or `pair`. |

Settings it reuses: `ORDER_USD_MIN` and `ORDER_USD_MAX` (the stake band; `HEAT_LANE=true` refuses to start with `ORDER_USD_MIN=0`), `RISK_MIN_SIDE_PRICE`, `ENTRY_WINDOW_15M`, `ENTRY_WINDOW_HOURLY`, `HOURLY_MID_BAND`, and for the perps `PERP_STOP_ATR_MULT` and `PERP_MIN_STOP_BPS`. The reader has its own (`HEAT_READER_MAX_RANK`, `HEAT_CLOCK_PACK` and the ones in `docs/HEAT_READER.md`).

## What the operator sees

- **Status**: `guards.heat` in the dashboard's status JSON: whether the lane is on and has an exits' owner, the reader's file (age, coins, rows), open heat positions, trips, wins, P&L, the flat phase, the pilot budget left, each coin's hour direction, the last calls ruled on and why the file or a coin gave nothing.
- **Audit**: kind `heat`, one compact row per call ruled on (coin, horizon, key, side, rank, rows fired and against, the single a pair replaced, context, and the plan with what became of it, or the skip reason), plus rows for entries seen open, round trips closed and the reader's file going stale or coming back. Each entry also writes a `decision` row with `lane: 'heat'` and a `heat` object (the call, weight, slot, stake, count, fair value, rule id, run and pack hash).

## Before it is switched on

All of these must be true before `HEAT_LANE=true` goes into the server's `bot.env` (Steven's approval):

1. **The oracle branch is merged** (`python/oracle`, branch `claude/project-thread-nvd096`, pinned at fd88805), so the reader runs the same reading code the curves were measured with.
2. **The cleanup thread's plan exits are merged and on** (`PLAN_RULES=true`). Without them the old model's exit would sell a heat position on its next tick. When that branch lands, `bot/main.ts` wires the seam: `tag` and `untag` become `engine.planPositions.tag` and `forget`, `reentryBlock` becomes `holdExits.reentryBlock`, and the second argument of `heatStartCheck` becomes `cfg.plan.enabled`. The merge has two conflicts in `bot/engine.ts`: take that branch's `decide(view, strat, planPos ? {...} : {...})` and put `&& !this.d.heat?.lane.holds(m.ticker)` on `entries:` in BOTH objects (a filled heat position is a plan position, so the plan branch is the one it takes; `placeChecked` refuses the old lane's orders there anyway, but the flag keeps `decide()` from building them); take its `placeChecked` line (returns `Promise<boolean>`) with `heat?: { modelId: string; edgeCollar: boolean }` added to `opts`. Then add a `tests/heatEngine.test.ts` case with `PLAN_RULES=true` and the tag hook on `engine.planPositions.tag` that finds no other order on the market after the heat fill. Until then `HEAT_LANE=true` refuses to start, and an engine without a tag hook enters nothing ("no exit owner").
3. **The reader is running**: `deploy/heat_reader_install.sh` installs and starts `heat-reader.service` only while `HEAT_LANE=true`, and the status shows the calls file fresh with every coin ok.
4. `ORDER_USD_MIN` is above 0.

Live additionally needs the usual live conditions (`docs/DEPLOY.md`): cash on the crypto shard for the stakes (two positions at most), the waterfall not armed at a small bankroll, and the kill override or the soft pause in place.
