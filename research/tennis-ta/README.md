# Tennis TA sweep requests

A counting run of the tennis TA rulebook trial starts only when a commit changes
`research/tennis-ta/sweep-request.json` on `claude/project-thread-7817be`
(`.github/workflows/tennis-ta-sweep.yml`). Every run is therefore a deliberate, logged commit, and every cell it scores
joins N_raw (pre-registration Amendment 1, A1). Do not commit a request to try something out: a test run counts too. Run
`node --import tsx research/tennisTaSweep.ts prep --request <file> --units models/tennis-ta/state/units.json` locally to
validate a request and print its plan without starting anything. A stage hold request also needs `--openings <file>`:
the openings ledger copied from Drive (`rclone cat gdrive:kalshi-bot-archive/models/tennis-ta/state/openings.jsonl`), or
an empty file to check the batch alone.

The project's held-out standard HO-1 (registry README, "Held-out standard HO-1") governs every run: settings are chosen
only on H-DEV (pool `disc`, matches closing before 2026-07-31 00:00 UTC) and a frozen choice is scored once on H-HOLD
(pool `hold`, 2026-08-01 to the cutoff, in 6 consecutive folds). Under Amendment 4 the frozen choice is a batch of hot
spots and the score is the one test (below).

The pre-registration and its amendments are in `/mnt/project-files/tennis-ta/preregistration.md` (thread "Build a
profitable tennis TA rulebook", Nov 5 2026). Amendment 4 is the contract of the one test.

## The one test (Amendment 4)

Steven's one test for tennis: can a hot spot detect direction, sustaining long enough for an exit to take place in
profit? No other statistical bar exists anywhere in the trial; everything that is not the one test is information.

- A **hot spot** (family A) is one config of the gradient matrix (a stage 1 grid config, or a stage 2 spec) and one leg,
  `underdog` (the underdog entry) or `fav` (the favourite re-entry); the report pools the two into a `both` row. Family
  B hot spots are one TA-Lib reading and its direction, on the 1 m or 5 m bars.
- A **signal instance** is the first decision at which production's `decideMatch` emits the leg's entry plan for a flat
  market, taken as a taker buy of the called market at its ask then, `C = max(1, floor($10 / ask))` contracts. No order
  rests; the fill models play no part. The sim runs it as the config's **window arm** (`|window`, `window: true`, fill
  F1 by convention): virtual positions, released once their window is resolved, with no profit exit, pacer or risk cap
  acting on them. Its coin placebo is the `|coinwindow` arm.
- The **level** `L` is the smallest whole cent with `L x C - takerFee(C, L) >= ask x C + takerFee(C, ask) + 0.01 x C`
  (entry, both taker fees, one cent a contract). The **window** is the first one-minute Kalshi candle of the called
  market that starts at or after the entry (a full minute after the buy: the entry's own minute never counts,
  Amendment 4a), ending at or before the end rule (production's latched progress reaching `1 - 0.30`, else the
  close), whose lowest YES bid is at or above `L` on a two-sided book.
- Every instance gets three **twins**: entries at random eligible minutes of the same match in the same UTC clock hour
  (the whole eligible span when that hour holds fewer than 5), on the instance's own called market (the same contract,
  Amendment 4a: a coin-flip side would let any rule that buys favourites beat random from price level alone), bought at
  the candle's close ask, judged by the same rule. Seed `hash32(event | config | leg | entry minute)` with
  `PLACEBO_SEED 20261105`.
- `gap = window rate - random rate`, with a cluster-robust (by match) standard error; `PASS = gap >= 2 x SE`; the
  **league** ranks hot spots by `z = gap / SE`, ties by gap. SE 0 (one contributing match, or identical per-match
  differences) gives no z and no pass (Amendment 4a). The league runs on H-DEV only (a disc run's report writes
  `league.md`, `league.csv`, `league.json`).
- The **read**: the 10 hottest family A hot spots (measuring sticks excepted: reported beside the league, never read; `prep`
  and the report both refuse one in the batch) go into `research/tennis-ta/hold-batch.json` with the league run id,
  are listed in the registry and in the project calendar (`/mnt/project-files/registry/edge-pipeline/calendar.md`)
  BEFORE the push that starts the hold run, and stage hold runs their `|window` and `|F1` arms once on H-HOLD. A hot
  spot that passes on the read is "direction found" for tennis. Stage hold scores pool `hold` and nothing else, ever.
- **Reported, never judged** (item 8): minutes to the window, window length, the wrong-way dip, minutes held at the
  level, the share resolved by the end rule without a window, by phase and by tour; the after-fee P&L of the production
  exits (F1, F2, the sticks), the HO-1 fold table and the coin placebo. Nothing in that list cuts a hot spot.

The shared core is `research/tennisTaWindow.ts` (the candle view, the level, the window rule, the twins, the per-row
aggregate and `gapStats`); the sweep feeds the sim the slice's minute candles (`candleIndex`, `SweepOpts.candlesOf`)
and writes the per-row aggregates into each shard file's `window` block (contract C12, below).

## The request file

```json
{
  "stage": "1",
  "pool": "disc",
  "from": "2026-04-27",
  "to": "2026-07-30",
  "shards": 8,
  "familyB": false,
  "note": "stage 1, the whole of H-DEV"
}
```

A hold run is `{ "stage": "hold", "shards": 8 }`: pool, from and to take their defaults (the whole hold block).

| key | required | default | meaning |
|---|---|---|---|
| `stage` | yes | | `"1"`, `"2"` or `"hold"` (1 and 2 may be numbers). Stage 1 is the 409-spec H grid built in code (`stage1Specs()`: 81 configs x F1, F2, coin, window, coinwindow + 2 sticks x F1, window). Stage 2 reads its specs from `research/tennis-ta/stage2-specs.json`, stage hold its batch from `research/tennis-ta/hold-batch.json` (both below). |
| `pool` | no | `"disc"` (`"hold"` at stage hold) | `"disc"` (H-DEV, stages 1 and 2: every setting is chosen here, and the league runs here), `"old"` at stage 2 only (stratum H0: units before the start era, a stress test for finalists) or `"hold"` at stage hold only (H-HOLD; stage hold scores nothing else). `"nostart"`, `"embargo"`, `"out"` and `"practice"` are never scored and are refused. `"check"` and `"sealed"` no longer exist (C9: the hold block replaced them). |
| `from`, `to` | no | the whole pool (`2026-04-27` to `2026-07-30` for disc; `2025-06-16` to `2026-04-26` for old; `2026-07-27` to `2026-11-04` for hold) | UTC days, inclusive. Each pool unit (a unit holding time of the pool) whose start falls in `[from, to]` is swept whole, so the plan can run past `to` to that unit's end. prep fails if `from` falls inside a pool unit, because that unit's start would not be covered and the unit would be swept only in part. A hold run scores the whole of H-HOLD once, so for hold they must be left out (or set to the defaults). |
| `shards` | no | `8` | Shard jobs, from 1 to 16 (8 run in parallel). Keep the count fixed across rounds: cross-match state restarts at each shard and sub-slice edge (below). |
| `familyB` | no | `false` | When true, each sub-slice also runs family B (TA-Lib event study, `research/tennisTaSignals.ts` `SignalStudy`, $15 orders, 1 s latency, seed 20261105, bars 1 m and 5 m on H) on the same matches. Its cells go into the shard files as `familyB`, and its one-test rows (`SignalStudy.exportWindow`) as `familyBWindow`. Matches labelled `nostart` are left out of it. Refused at stage hold: family B is a discovery design (every cell is a hypothesis), so it runs on disc, and Amendment 4 does not read family B hot spots on H-HOLD. |
| `note` | no | | Free text, kept in the request's hash only. |

Any other key is refused, so a typo fails instead of being ignored. prep also checks the committed unit table
(`models/tennis-ta/state/units.json`): sorted, contiguous Monday 05:00 UTC edges, every unit as the calendar gives it
(`buildUnits`), and each Grand Slam placed as `SLAMS` gives it. A Slam unit must be a `SLAMS` entry's whole span, no week
unit may overlap a Slam, and every Slam the table's span reaches must be in the table as one unit, so a table that
starts or ends inside a Slam is refused. The table's `sealed` flags are the retired A3 seal and are ignored.

## Stage 2 spec file

`research/tennis-ta/stage2-specs.json` is a JSON array. Each element is one config arm:

```json
[
  { "id": "A|s2|gatePre0|F1", "overrides": { "TENNIS_ENTRY_MIN_SIGNALS_PRE": 0 }, "fill": "F1" },
  { "id": "A|s2|gatePre0|F2", "overrides": { "TENNIS_ENTRY_MIN_SIGNALS_PRE": 0 }, "fill": "F2" },
  { "id": "A|s2|gatePre0|coin", "overrides": { "TENNIS_ENTRY_MIN_SIGNALS_PRE": 0 }, "fill": "F1", "placebo": "coin" },
  { "id": "A|s2|gatePre0|window", "overrides": { "TENNIS_ENTRY_MIN_SIGNALS_PRE": 0 }, "fill": "F1", "window": true },
  { "id": "A|s2|gatePre0|coinwindow", "overrides": { "TENNIS_ENTRY_MIN_SIGNALS_PRE": 0 }, "fill": "F1", "placebo": "coin", "window": true },
  { "id": "A|s2|prod|settlehold|F1", "overrides": { "TENNIS_END_LOSER_CUT": false }, "fill": "F1", "stick": true }
]
```

- `id` is required and unique, with the form `A|s2|<config>|<arm>`. The arm suffix must agree with the spec: `|coin`
  for the coin placebo, `|window` for a window arm (`window: true`), `|coinwindow` for a window arm's coin placebo
  (`placebo: "coin"`, `window: true`), otherwise `|F0`, `|F1` or `|F2` as its `fill` (`ARMS`). The report and the
  registry read the config and the arm from the id; `configOf` strips the arm, `armOf` names it from the fields.
- A window arm is the one test's arm (Amendment 4): the sim takes the config's entry decisions as virtual taker buys
  and reports them as instances with their twins. It runs `fill: "F1"` (the fill models play no part in it; a window
  arm with another fill is refused). A config's `|F1` and `|window` arms are two arms, never twins.
- Every arm of one config (`|F0`, `|F1`, `|F2`, `|coin`, `|window`, `|coinwindow`) runs the same overrides, written
  the same way, at one `offsetMs`. The report compares a config's arms as written, so `0.4` and `"0.4"` count as
  different there. An `|F2` or `|coin` arm also needs its config's `|F1` arm, and a `|coinwindow` arm its config's
  `|window` arm. The registry rows pair the F0 and F2 neighbours and the coin placebo with that F1 row as their
  control, and the coinwindow placebo with the window row.
- `stick: true` marks a measuring stick (reported, never screened or counted as a hypothesis). A stick's id is
  `A|s2|prod|<name>|<arm>`, every id of that form must be a stick, and a stick has no placebo arm (a stick may run as a
  window arm: `A|s2|prod|<name>|window`).
- The stress adversaries and measuring settings are `HARNESS_FEE_MULT`, `HARNESS_LATENCY_MS`, `HARNESS_PACER`,
  `HARNESS_BANKROLL` and `TENNIS_END_LOSER_CUT` (`STICK_KEYS`, the report's list; the tests hold the two together).
  They are never hypotheses, so only a stick may move one off its default. A stick, in turn, runs production with
  only those settings, `HARNESS_LOSER_STOP` and `offsetMs` changed (on H, the ratchet is also off, as for every
  spec). A rulebook change is a config arm, which is screened and counted.
- `overrides` holds env-style `TENNIS_*`, `PACER_*` and `HARNESS_*` keys, with string, number or boolean values. Each
  key is checked, because production's `loadConfig` ignores a key it does not read, and a misspelt key would run as
  the production default and still count. Every unknown key is listed, whatever else is wrong with the spec:
  - Every `TENNIS_*` / `PACER_*` key must be one that `loadConfig` (`bot/config.ts`) reads, with a value it accepts.
    The tests hold this key list to `bot/config.ts` itself. Each key must also change the simulated config (tennis
    and pacer) given the spec's other keys. A key set to its default, or one read into a part of the config the sim
    does not run, is refused. A list that leaves every value at its default is refused; write `overrides: {}` for the
    production arm.
  - `HARNESS_*` keys are the sim's own rules, exactly the list `SimSpec` documents in `research/tennisTaSim.ts` (the
    tests hold the two together): `HARNESS_PACER` (`"tennis"` or `"off"`), `HARNESS_LOSER_STOP` (0 to 1, a fraction of
    the open lot's cost, 0 = off), `HARNESS_BANKROLL` (above 0, default 200), `HARNESS_FEE_MULT` (0 to 10) and
    `HARNESS_LATENCY_MS` (0 to 60000). Any other `HARNESS_*` key is refused. `HARNESS_LOSER_CUT` no longer exists. The
    settle-hold arm is `TENNIS_END_LOSER_CUT: false`.
  - An empty value is refused, because `loadConfig` reads it as unset.
- Two arms that would run identically are refused: same simulated config, harness rules, fill, window flag and
  `offsetMs`. Two non-stick arms that differ only in `offsetMs` are refused too. That pair is a hypothesis and its
  noise floor (section 7), so the noise floor runs as sticks at production, for example `A|s2|prod|phase1000|F1` with
  `"offsetMs": 1000`. Coin placebo arms are the exception, since each one's stream is seeded by its id.
- `fill` is `F0`, `F1` or `F2`. `placebo` may be `"coin"`. `window` may be `true`. `offsetMs` (an integer from 0 to
  4999) sets the decision-clock phase for noise-floor arms. Each shard file's `runs[]` entry carries its spec's
  `offsetMs`, `stick` and `window` tags.
- On H every spec runs with `TENNIS_TRAIL_RATCHET: false` (section 4: H has a one-level synthetic book with no walls).
  The sweep writes it as the boolean `false` when it is unset or spelt `"false"` or `"0"`, so a config's arms carry
  it the same way. It refuses a spec that turns the ratchet on.

If the file is missing or invalid, prep fails and lists every problem. Every list that prep accepts also passes the
report's `check_runs` gate (the tests pipe accepted lists through it). A list the report would refuse therefore fails
at prep, before any shard runs.

## Stage hold: the one read (Amendment 4 item 7) and the openings ledger

`research/tennis-ta/hold-batch.json` is the batch stage hold reads once on H-HOLD: the 10 hottest family A hot spots
by z on the league (ties by gap; a measuring stick is never one, `prep` refuses it), with the league run id. Write it from the league of a disc run, list it in the
registry and in the project calendar (`/mnt/project-files/registry/edge-pipeline/calendar.md`) BEFORE the push that
starts the hold run, and push it once: H-HOLD is read once per batch.

```json
{
  "league_run": "19876543210",
  "batch": [
    { "id": "A|s1|m0.01|f0.2|o0.01|w60", "leg": "underdog" },
    { "id": "A|s1|m0.02|f0.4|o0.02|w300", "leg": "both" },
    { "id": "A|s2|gatePre0", "leg": "fav" }
  ]
}
```

- `league_run` is the GitHub run id of the league the batch was read off (a non-empty string without spaces).
- `batch` holds at most 10 members, each `{ id, leg }`: a config id without its arm (`A|s1|...`, a stage 1 grid
  config or measuring stick; or `A|s2|<config>`, a stage 2 spec resolved against `stage2-specs.json` by its `|F1`
  arm, with its own `|window` arm when the list has one) and a leg `underdog`, `fav` or `both`. No `(id, leg)` twice;
  a config named with two legs runs once. Any other key, an id ending in an arm, or an id that resolves to nothing is
  refused (`validateHoldBatch`).
- A hold run executes each batch config's `|window` arm and `|F1` arm, and nothing else (`prep`'s `specIds`). The
  window arm is the one test's read, the F1 arm the production P&L reported beside it. No control, neighbour or
  placebo arm runs on H-HOLD.
- The batch's identity is `batchHash`, the sha256 of the file as pushed (the file the registry and the calendar list).
  Re-spacing the file is a new batch, though the same arms run; `specsHash` (the canonical form of the arms run) is
  still in every shard meta for the completeness check.
- The openings ledger is `gdrive:kalshi-bot-archive/models/tennis-ta/state/openings.jsonl`, one JSON line
  `{hash, run, ts, ids, pool: "hold"}` per batch read on H-HOLD (`hash` = `batchHash`, `ids` = the arms run). prep
  reads it level by level, so a Drive listing error fails the job, and a ledger that does not exist yet reads as
  empty. prep refuses a hold request whose `batchHash` is in the ledger, and refuses a damaged ledger instead of
  reading it as "not opened". (Rows of the retired frozen-list mechanism, keyed by a spec hash, stay in the ledger and
  match no batch.)
- The report job appends the run's line once the completeness check (every file's `window` block included, below)
  has passed and before the report computes anything (the blind-open), so every hold run that is scored at all is in
  the ledger, and a run whose files carry a broken or incomplete block fails before the batch's read is spent. A re-run of the report job
  keeps the run's line (the append is idempotent by run id). The job fails if the ledger holds the same batch under
  another run, or this run with another batch, and it never overwrites a damaged ledger. A report that fails after the
  append has spent the batch: re-run the report job under the same run id ("Re-run failed jobs"). A new commit of the
  same file is refused.
- A hot spot that passes the one test on the read is "direction found" for tennis. A changed hot spot is never read
  there again. Family B hot spots are not read on H-HOLD in this amendment.

## What a run does

1. **prep** first reads the openings ledger from Drive (above). It then validates the request and writes
   `prep/plan.json`. This holds the request and its sha256, the unit table's sha256, the sim version, the history
   replay's `REPLAY_VERSION` (`replayVersion`), the era edges it used (`era`: `historyFrom`, `startEraFrom`, `devTo`,
   `holdFrom`, `cutoff`), HO-1's six folds (`holdFolds`), the stratum label (`H`, or `H0` for pool old), the unit
   count of every pool over the table (`poolUnits`; a unit holding time of several pools counts in each), the spec
   list's `specsHash` and `specIds`, the one test's `windowVersion`, at stage hold the batch (`batchHash`, `leagueRun`,
   `batch`), the shard plan, each shard's sub-slices, the expected shard file names and the pool's wall-clock
   intervals per unit (`poolSpans`, below). Both cuts fall on unit edges only (Monday 05:00 UTC weeks; a Slam is one
   unit). Each plan entry is `{k, from, to, units}`, where `from` is the first unit's start day and `to` is the day
   after the last unit's end. A slice owns the matches whose start is in `[from 00:00, to 00:00)` UTC, whose unit is
   in `units` and whose pool is the run's. The cuts are balanced by unit length.
2. **shard** jobs (8 at most in parallel): each downloads both history tarballs and records their sha256 as the data
   version. It fails if either tarball is missing. It then checks that the history is complete over the shard
   (`tennisTaSweep.ts coverage`, below) and fails before sweeping if it is not. It builds replay days from 1 day
   before the shard to 2 days after it and runs 4 processes, one per sub-slice. Each process first builds the one
   test's candle index from the same history day files (`candleIndex`: every market closing in the span the slice
   reads, parsed once, kept as `MinuteCandles` only) and hands it to the sim as `candlesOf`. The sim reads market
   lines from 1 day before a slice on H (`lookbackOf('H')`), because history lists a match 30 min before its start,
   and reads on so a slice's late matches finish within 2 days (`CLOSE_TAIL_DAYS`). The 7-day lookback
   (`LOOKBACK_DAYS`) belongs to the recorded stratum R only, where the bot lists a match up to 36 h early; this
   workflow does not run R. Each process writes `a-s<stage>-<k>-<j>.json.gz` (`a-shold-<k>-<j>.json.gz` at stage
   hold) to `gdrive:kalshi-bot-archive/models/tennis-ta/runs/<run>/shards/`. Compute: stage 1 runs 409 specs per
   sub-slice (245 before Amendment 4; the 164 window arms carry no resting orders or fills, so a sub-slice costs about
   1.5x the old grid, within the shard job's 350 min with 8 shards x 4 sub-slices over H-DEV); a hold run runs at most
   20 arms.
3. **report** runs only when prep and every shard leg succeeded. It first fetches the project's trial registry module
   (`research/registry.py` from `main`, or from the registry thread's branch `claude/project-thread-79ntof` until it
   lands on main) to `/tmp/registry.py`. It then runs the completeness check (`tennisTaSweep.ts check`): every planned
   file must be on Drive exactly once with nothing extra, and every file must carry the same run, request sha256,
   unit-table sha256, stage, pool, families, sim version, replay version, spec-list hash, window version (and at stage
   hold the batch hash) and data version. Each file must also match its planned slice (from, to, units), every planned
   unit must be swept by exactly one file, and the history must be complete over every slice (below). The check also
   reads every file's `window` block (`readShardParts` streams `runs` past; `windowBlockProblems`): the block at the
   plan's version with the one test's constants, its events the `matchList`'s in order, its rows exactly the plan's
   window arms x the two legs (at stage hold every batch member's `|window` rows), each row's arrays, `hist`,
   `byPhase`, `endNoWin` and `asks` well formed and `meta`'s window counts agreeing; a `familyBWindow` block, when
   there is one, the same. If any check fails, nothing is scored or uploaded, and at stage hold the batch's read is
   not spent (the ledger step comes after). When the check passes, a hold run's opening is first appended to the
   openings ledger (above). Then `research/tennis_ta_report.py --registry-py /tmp/registry.py --sha $GITHUB_SHA` scores the
   pool, runs the one test on every hot spot and, on a disc run, writes the league (`report/league.md`,
   `report/league.csv`, `report/league.json`; the job fails if a disc run's report leaves one out), and writes the
   run's trial rows to `report/registry-v1-<run>.jsonl` (below). The rows must pass `python3 -I /tmp/registry.py
   validate` with no errors, every row must carry `contract_type: "tennis"`, thread `tennis-ta` and the modules it
   changes, every row must have the same day set, and trial ids must be unique. Otherwise the job fails. The report
   directory, league included, goes to `runs/<run>/report/`, and the rows are uploaded once to
   `gdrive:kalshi-bot-archive/registry/shards/tennis-ta/<run>.jsonl`. The interim ledger
   `models/tennis-ta/state/trials.jsonl` is no longer written. The report is posted once as a commit comment with a
   "Run mechanics" section covering shards, units, data version, matches by pool and coverage.

### Registry rows (contracts C7, C11 and Amendment 4 item 10)

The report writes one row per family A config and arm, and one per family B signal and exit. Each row has
`contract_type: "tennis"` and the modules it changes: `["tennis-ta"]` for threshold configs and family B, `["exits"]`
for the settle-hold stick and `["pacer"]` for the no-pacer stick. Steven's rule (Nov 5 21:59 UTC) tracks $/h per
contract type, adding up the best validated module results. Each row's `by_day` holds $ after fees per UTC match day
of the pool, with 0 on pool days without a trade. `hours` are the pool hours behind the report's $/h, with the embargo
day left out. Every row also carries `base` (`tennis-ta@<sha>`), `base_defaults` (the overrides every spec of the run
shares that differ from production, such as `TENNIS_TRAIL_RATCHET: false` on history), `data.replay_version` (the
shard meta's `replayVersion`, 9 now) and `data.engine: "replay"`. Disc runs carry the flag `dev-choice` and `by_day`
before 2026-08-01 only, so the registry validator reads them as `DEV:choice-only`. Hold runs have no `dev-choice`
flag. Their rows' `by_day` spans every hold day, `by_tercile` holds ATP and WTA, and the HO-1 fields (`registry.py`'s
`ho1_fill`, `ho1_pass`) stand beside them as information. The production-default F1 config (on stage 1 the grid point
`A|s1|m0.01|f0.2|o0.01|w60|F1`) is the family A control of the P&L rows. Each family B row is a candidate against its
own placebo row (`<rule>|placebo`, role `placebo`, seed 20261105), whose `by_day` comes from the placebo columns of
the export's day rows (`familyB.cells[].days[day]` is `[entries, net, placebo entries, placebo net]`).

Each hot spot row (Amendment 4 item 10): `contract_type` tennis, family `tennis-ta-A` or `tennis-ta-B`, the arm
(`|window`), the leg, `by_day` and `by_tercile` (ATP / WTA) of its gap, and a `heldout` block only for rows of the
read, with the one test's standard, window rate, random rate, gap, SE and pass, beside the HO-1 fields as
information. `trial_id` is `make_id(thread, family, arm, code_sha, days, seed, [], env)` from `registry.py`. The
registry's shards are append-only: a re-run whose rows match the upload (their write time `ts` aside) uploads
nothing, and one whose rows differ fails.

### History completeness

The history download (`.github/workflows/tennis-ta-data.yml`) lists settled markets newest first and can stop at its
time budget. Only a download run that listed every settled market and stored each one writes its close-time range to
`<SERIES>/.index.json` as `listed` (`research/history/kalshiHistory.ts`). The tape download has no such record, but it
writes a tape line (empty if the market never traded) for every market it has fetched. Over every slice, for each
series in the data version, the sweep requires two things:

- `listed` covers every close time the slice reads: from the slice's `from` minus the sim's lookback (1 day on H)
  to its `to` plus 2 days, cut at the hard cutoff. A day in that span without a market file is then a day on which
  no market closed, and its hours count as pool hours.
- Every traded market closing in that span has a tape line. Otherwise its match would be dropped as "no tape" (A5)
  only because the download had not reached it.

The shard job checks this before sweeping, and the report job checks it again from each shard file's
`meta.coverage`. To recover, run the data workflow until a download finishes, then use "Re-run all jobs" (a run that
was never scored can be re-run).

### Re-runs

A failed shard leg can be re-run ("Re-run failed jobs"). It rewrites that leg's files under the same run id, and the
report then runs once. Once a run id is scored (its registry rows are in `runs/<run>/report/`), nothing under it is
overwritten. "Re-run all jobs" fetches fees and history again, so it fails in prep. A shard job re-run on its own fails
before it sweeps. A re-run report job (after a later step failed) keeps the Drive report and rows, uses them for the
registry upload and the commit comment, and fails if its own rows differ. A new measurement is a new commit of the
request.

Cross-match state (the tennis-only pacer, the 25% / 10% caps, the coin-placebo stream and family B's placebo reservoir)
restarts at each slice's first unit, so it restarts only at unit edges. The result depends on the shard count, which is
why the count should stay fixed across rounds.

## Shard file (gzip JSON)

```
{ meta: { simVersion: 'tennis-ta-sim/3', stage, pool, run, k, j, shards, subShards, from, to, units, dataVersion,
          coverage, requestSha, families: ['A'] | ['A','B'], replayVersion (REPLAY_VERSION of
          research/history/historyReplay.ts), specsHash (the spec list's canonical sha256), windowVersion
          ('tennis-ta-window/1', the window block's version), ...bookkeeping (sha, unitsSha, stratum, stratumLabel
          ('H', 'H0' for pool old, 'R'), era, holdFolds, evidence, lookbackDays (what the sim read: 1 on H, 7 on R),
          configs, sticks, poolSpans, windowArms / windowInstances / windowRows / candleMarkets, batchHash / leagueRun /
          batch at stage hold, familyBGrids / familyBStartMismatch / familyBNoStart / familyBWindowRows with family B,
          episodeCols, timings) },
  matchList: [MatchInfo + pool + unit + fold],
  runs: [SimRun + stick?: true + window?: true + offsetMs?],
  familyB?: FamilyBExport,
  window: { version: 'tennis-ta-window/1', settleFrac: 0.30, orderUsd: 10, twins: 3, seed: 20261105,
            events: [ { event, series, tour: 'ATP' | 'WTA', unit, day, start, close, endRule } ],
            rows: [ { id: '<config>|window' | '<config>|coinwindow', leg: 'underdog' | 'fav', n[], w[], tn[], tw[],
                      hist: { tWin[], lenWin[], dip[], held[] }, byPhase: { pre, e20, p1, p2, p3: [n, w] }, endNoWin,
                      asks: [n, sumAsk] } ] },
  familyBWindow?: { version, rows: [ { id: '<reading>|<bar>|<dir>', n[], w[], tn[], tw[], hist, byPhase, endNoWin, asks } ] } }
```

- `meta` comes first in the file, so `readShardMeta` can read it without inflating the rest; `readShardParts` reads
  any top-level members the same way (the completeness check reads `meta`, `matchList`, `window` and
  `familyBWindow`, streaming `runs` past).
- `matchList[].pool` is the match's pool by the rules below. Within a disc run it is `disc`, or `nostart` for a
  start-era match without a published start (within a hold run, `hold` or `nostart`). The report reads the pool names
  from here.
- `matchList[].fold` is a hold match's HO-1 fold, 1 to 6, from its UTC match day (`MatchInfo.day`, its start's day,
  the day `by_day` files it under), with exactly `registry.py`'s edges. Every other match has `null`. A hold match on
  2026-11-05 UTC (a start from 00:00 to the 02:00 cutoff, Nov 4 evening Eastern) is in pool hold but in no fold, because
  H-HOLD and `ho1_fill` end on Nov 4.
- `window` (contract C12) is the one test's block. `events` lists the slice's matches in `matchList` order, each with
  its tour and its end-rule time (`endRule`: the production-default clock's latched progress reaching `1 - 0.30` on
  the match grid, else the close; a one-legged or unresolved match has no grid and gets the close). The row arrays
  (`n` instances, `w` windows, `tn` twin entries, `tw` twin windows) index into `events`; `hist` counts per bin of
  `HIST_EDGES` (`research/tennisTaWindow.ts`); `byPhase` is `[instances, windows]` per phase; `endNoWin` counts the
  instances resolved by the end rule or the close without a window; `asks` gives the mean entry ask. Every window arm
  has its two leg rows, instances or none; the report pools them into the `both` row and adds rows across slices per
  event. `runs[]` entries carry no instances (the block holds them, aggregated).
- `familyBWindow` holds family B's rows of the same shape (`SignalStudy.exportWindow`), re-mapped by the sweep onto
  the `window.events` index; `leg` is omitted and `n[i]` may exceed 1.
- `coverage` has these fields:
  - `series`: per series, the history's first and last day files, the file count, and the swept span's days with and
    without a market file (missing days are listed) and with a trade tape. It also has the download's complete listing
    (`listed`), the close times the slice reads (`need`), the market lines closing then, how many of those were
    untraded, and the traded ones without a tape (`tapesMissing`).
  - `matches`, `noPublishedStart` and `noPublishedStartEvents` (first 50): owned matches, and those without a
    published start. Those matches keep the earliest market-line time for their unit and pool.
  - `pools`: owned matches per pool and the distinct units holding them, as `{ <pool>: { matches, units } }`. The
    requested pool and `nostart` are always present. The sim's `admit()` is not told whether a start was published, so
    a start-era match without one is admitted as its unit's pool would have it. It runs with the others, because
    production trades it too and the cross-match state stays production's. It is labelled `nostart`, and the report
    leaves it out and counts it.
  - `lostTickers`: tennis match tickers with book or trade lines but no market line in what the sim read (lost
    matches).
  - `feed`: the sim's feed bookkeeping, `{ gaps, gapMs, blindGaps, liveDays, blindDays, lateGrids }`. These are R
    feed outages (count, total ms, and those found only by a resubscribe: blind days, or reconnects the beats
    masked), day files that show or hide the feed's liveness, and grids not delivered to family B because their day
    had already been released. On H all but `lateGrids` are 0.
- `familyB.cells[]` (`FamilyBCell`, `research/tennisTaTypes.ts`): entries and the first four moments of net, breaches,
  gross, fees and stress per cell; `units[u]` and `days[d]` are `[entries, net, placebo entries, placebo net]`;
  `markets` and `placeboMarkets` count the distinct markets (match x side) the real and placebo arms entered. All of
  them add over slices.
- Measuring sticks have ids `A|s1|prod|<name>|<arm>` (stage 2: `A|s2|prod|<name>|<arm>`) and carry `stick: true`.
  Stage 1 has four: `A|s1|prod|settlehold|F1` (`TENNIS_END_LOSER_CUT=false`) and `A|s1|prod|nopacer|F1`
  (`HARNESS_PACER=off`), each also as a window arm (`A|s1|prod|settlehold|window`, `A|s1|prod|nopacer|window`).

## Pools (C9: the start era and HO-1; Amendment 4 item 9: practice)

Kalshi's tennis match history starts on 2025-06-18 (`HISTORY_FROM`). Before about April 2026, markets had no published
start time (`occurrence_datetime`) and settled on an older "advances past the round" rule. That is a different product,
so the history is split at `START_ERA_FROM` (a Monday 05:00 UTC unit start). It is a placeholder, 2026-04-27 05:00 UTC,
and is fixed from the weekly inventory before the first counting run. Each plan and shard file records the value it
used (`era`). In the start era, HO-1 splits the time into H-DEV and H-HOLD:

- `DEV_TO` is 2026-07-31 00:00 UTC. A disc match closes before it.
- `HOLD_FROM` is 2026-08-01 00:00 UTC. A hold match starts at or after it. H-HOLD runs from 2026-08-01 to 2026-11-04 in
  UTC days (`H_HOLD`, as `registry.py` has it), 96 days in 6 consecutive folds of 16 days. Fold edges are `registry.py`'s
  `ho1_fill` edges (day 0 + round(i x 96 / 6)): Aug 1, Aug 17, Sep 2, Sep 18, Oct 4 and Oct 20, with the last fold
  holding Nov 4.

A match takes the first pool below that applies:

| pool | rule |
|---|---|
| `practice` | Recorded stratum (R) only: a match of the bot's own recordings starting before `FULL_BOOK_FROM` (2026-11-10 03:44 UTC, Nov 9 10:44 PM EST). Those recordings sat on empty order-book reads and are practice data: never requestable, never scored, never pooled with later days (`recordedPoolOf`; the recorded cut labels whole days the same way, `CutStats.practice`). An R run never owns one: `run`'s admit labels a recorded match by `recordedPoolOf`, streams a practice match past like an out-of-pool match (no episode, day, window instance or grid of it reaches the shard file) and counts it in `coverage.pools.practice` when the requested pool would otherwise have held it. Kalshi's own history (H) is unaffected. |
| `out` | Its start is before the history, its start or its close is at or after the hard cutoff (Nov 5 02:00 UTC), it is outside the unit table, or (with a later cutoff) it reaches an unopened lockbox week. |
| `old` | Its unit starts before `START_ERA_FROM` (stratum H0). A published start does not matter here, because Kalshi published none then. It is a stress test for stage 2 finalists only. |
| `nostart` | A start-era match without a published start. It is excluded from scoring and counted. |
| `disc` | H-DEV: a start-era match that starts and closes before `DEV_TO`. Every setting is chosen here, and the league runs here. |
| `hold` | H-HOLD: a start-era match that starts (and closes) at or after `HOLD_FROM`, and before the cutoff. Only stage hold scores it, once per batch. |
| `embargo` | Any other start-era match: Jul 31 and the matches straddling `DEV_TO` or `HOLD_FROM`. Never scored. |

- The A3 hash seal and the dev-check pool are retired, because the contiguous hold block replaces them. The old era
  needs no seal, since nothing is chosen there. The `sealed` flags still in the committed unit table are ignored.
- Lockbox weeks are keyed by id from a `[start, end)` table anchored at Nov 6 05:00 UTC in 7-day steps: L1 is Nov 6 to
  Nov 13, L2 is Nov 13 to Nov 20, and so on. Under the Nov 5 02:00 UTC cutoff no pool match reaches one.
- A match belongs to the unit that holds its start (the published start, else its earliest market-line time). Units
  stay Monday 05:00 UTC weeks (Slams whole) for the bootstrap and the slicing. A unit can hold matches of several
  pools: `W-2026-07-27` holds disc, embargo and hold matches, and both disc and hold runs sweep it, each owning its own.
- On the committed unit table this gives 23 out units, 40 old (`W-2025-06-16` to `W-2026-04-20`), 11 disc
  (`W-2026-04-27` to `W-2026-07-27`) and 13 hold (`W-2026-07-27` to `W-2026-11-02`), with `W-2026-07-27` in both.
- Pool hours (`poolSpans`) count each pool unit's wall-clock part of the pool. That is the unit's span cut to the
  history (from 2025-06-18 to the hard cutoff), and in the start era cut to H-DEV (to Jul 31 00:00 UTC) or H-HOLD (from
  Aug 1 00:00 UTC). The embargo day is in no scored pool's hours. Disc has 2,275 h, hold has 2,306 h (96 days and 2 h),
  and `nostart` matches sit in disc or hold hours.
- `node --import tsx research/tennisTaSweep.ts pool-hours --units models/tennis-ta/state/units.json --pool disc` prints
  each unit's countable intervals (`--pool old` or `hold` for the others).
