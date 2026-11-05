# Tennis TA sweep requests

A counting run of the tennis TA rulebook trial starts only when a commit changes
`research/tennis-ta/sweep-request.json` on `claude/project-thread-7817be`
(`.github/workflows/tennis-ta-sweep.yml`). Every run is therefore a deliberate, logged commit, and every cell it scores
joins N_raw (pre-registration Amendment 1, A1). Do not commit a request to try something out: a test run counts too. Run
`node --import tsx research/tennisTaSweep.ts prep --request <file> --units models/tennis-ta/state/units.json` locally to
validate a request and print its plan without starting anything.

The pre-registration and its amendments are in the thread "Build a profitable tennis TA rulebook" (Nov 5 2026).

## The request file

```json
{
  "stage": "1",
  "pool": "disc",
  "from": "2024-12-23",
  "to": "2026-03-31",
  "shards": 8,
  "familyB": false,
  "note": "stage 1, whole dev-discovery pool"
}
```

| key | required | default | meaning |
|---|---|---|---|
| `stage` | yes | | `"1"` or `"2"` (a number is accepted too). Stage 1 is the 245-spec H grid built in code (`stage1Specs()`). Stage 2 reads its specs from `research/tennis-ta/stage2-specs.json` (below). |
| `pool` | no | `"disc"` | Only `"disc"` (dev-discovery: unsealed, not embargoed units starting before 2026-04-01) can be requested. `"check"` and sealed units need an entry in the openings ledger naming their units, written before the read (A3). That ledger does not exist yet, so prep refuses them. |
| `from`, `to` | no | the whole pool (`2024-12-23` to `2026-03-31` for disc) | UTC days, inclusive. Each disc unit whose start falls in `[from, to]` is swept whole, so the plan can run past `to` to that unit's end. prep fails if `from` falls inside a disc unit, because that unit's start would not be covered and the unit would be swept only in part. |
| `shards` | no | `8` | Shard jobs, from 1 to 16 (8 run in parallel). Keep the count fixed across rounds: cross-match state restarts at each shard and sub-slice edge (below). |
| `familyB` | no | `false` | When true, each sub-slice also runs family B (TA-Lib event study, `research/tennisTaSignals.ts` `SignalStudy`, $15 orders, 1 s latency, seed 20261105, bars 1 m and 5 m on H) on the same matches. Its cells go into the shard files as `familyB`. |
| `note` | no | | Free text, kept in the request's hash only. |

Any other key is refused, so a typo fails instead of being ignored. prep also checks the committed unit table
(`models/tennis-ta/state/units.json`): sorted, contiguous Monday 05:00 UTC edges, every seal flag as the seal hash gives
it, and every unit as the calendar gives it (`buildUnits`: each Grand Slam in `SLAMS` is one unit, never split into
weeks or merged with a neighbour).

## Stage 2 spec file

`research/tennis-ta/stage2-specs.json` is a JSON array. Each element is one config arm:

```json
[
  { "id": "A|s2|gatePre0|F1", "overrides": { "TENNIS_ENTRY_MIN_SIGNALS_PRE": 0 }, "fill": "F1" },
  { "id": "A|s2|gatePre0|coin", "overrides": { "TENNIS_ENTRY_MIN_SIGNALS_PRE": 0 }, "fill": "F1", "placebo": "coin" }
]
```

- `id` is required, unique, and starts with `A|s2|`.
- `overrides` holds env-style `TENNIS_*`, `PACER_*` and `HARNESS_*` keys, with string, number or boolean values. Each
  key is checked, because production's `loadConfig` ignores a key it does not read, and a misspelt key would run as
  the production default and still count:
  - Every `TENNIS_*` / `PACER_*` key must be one that `loadConfig` (`bot/config.ts`) reads, with a value it accepts.
    Together these keys must change the simulated config (tennis and pacer). A list that leaves every value at its
    default is refused; write `overrides: {}` for the production arm.
  - `HARNESS_*` keys are the sim's own rules: `HARNESS_PACER` (`"tennis"` or `"off"`), `HARNESS_LOSER_STOP` (0 to 1,
    a fraction of the open lot's cost, 0 = off), `HARNESS_BANKROLL` (above 0, default 200), `HARNESS_FEE_MULT` (0 to
    10) and `HARNESS_LATENCY_MS` (0 to 60000). Any other `HARNESS_*` key is refused. `HARNESS_LOSER_CUT` no longer
    exists. The settle-hold arm is `TENNIS_END_LOSER_CUT: false`.
  - An empty value is refused, because `loadConfig` reads it as unset.
- Two arms that would run identically are refused: same simulated config, harness rules, fill and `offsetMs`. Coin
  placebo arms are the exception, since each one's stream is seeded by its id.
- `fill` is `F0`, `F1` or `F2`. `placebo` may be `"coin"`.
- Optional: `stick: true` marks a measuring stick (reported, never screened or counted as a hypothesis), and `offsetMs`
  (an integer from 0 to 4999) sets the decision-clock phase for noise-floor arms.
- On H every spec runs with `TENNIS_TRAIL_RATCHET: false` (section 4: H has a one-level synthetic book with no walls).
  The sweep adds this when it is unset and refuses a spec that turns the ratchet on.

If the file is missing or invalid, prep fails and lists every problem.

## What a run does

1. **prep** validates the request and writes `prep/plan.json`. This holds the request and its sha256, the unit table's
   sha256, the shard plan, each shard's sub-slices, the expected shard file names and the pool's wall-clock intervals per
   unit (`poolSpans`: each unit's span cut at the hard cutoff, minus the 24 h embargo windows of sealed units). Both cuts
   fall on unit edges only (Monday 05:00 UTC weeks; a Slam is one unit). Each plan entry is `{k, from, to, units}`, where
   `from` is the first unit's start day and `to` is the day after the last unit's end. A slice owns the matches whose
   start is in `[from 00:00, to 00:00)` UTC and whose unit is in `units`. The cuts are balanced by unit length.
2. **shard** jobs (8 at most in parallel): each downloads both history tarballs and records their sha256 as the data
   version. It fails if either tarball is missing. It then checks that the history is complete over the shard
   (`tennisTaSweep.ts coverage`, below) and fails before sweeping if it is not. It builds replay days from 8 days
   before the shard to 2 days after it and runs 4 processes, one per sub-slice. The sim reads market lines 1 day before
   a slice on H, because history lists a match 30 min before its start. On R it reads 7 days back
   (`LOOKBACK_DAYS`), because the bot lists a match up to 36 h early. The 8-day margin covers both. Each process
   writes `a-s<stage>-<k>-<j>.json.gz` to `gdrive:kalshi-bot-archive/models/tennis-ta/runs/<run>/shards/`.
3. **report** runs only when prep and every shard leg succeeded. It then checks the shard set before scoring: every
   planned file must be on Drive exactly once with nothing extra, and every file must carry the same run, request
   sha256, unit-table sha256, stage, pool, families, sim version and data version. Each file must also match its planned
   slice (from, to, units), and every planned unit must be swept by exactly one file. The history must also be
   complete over every slice (below). If any check fails, nothing is scored or appended. When the check passes, `research/tennis_ta_report.py` scores the pool, and the run's registry rows
   are appended to `models/tennis-ta/state/trials.jsonl` once per run id. A re-run of the same run id appends nothing.
   A ledger read error fails the job and never counts as an empty ledger. The report is posted once as a commit comment
   with a "Run mechanics" section covering shards, units, data version and coverage.

### History completeness

The history download (`.github/workflows/tennis-ta-data.yml`) lists settled markets newest first and can stop at its
time budget. Only a download run that listed every settled market and stored each one writes its close-time range to
`<SERIES>/.index.json` as `listed` (`research/history/kalshiHistory.ts`). The tape download has no such record, but it
writes a tape line (empty if the market never traded) for every market it has fetched. Over every slice, for each
series in the data version, the sweep requires two things:

- `listed` covers every close time the slice reads: from the slice's `from` minus the sim's lookback (1 day on H)
  to its `to` plus 2 days, cut at the hard cutoff. A day in that span without a market file is then a day on which no market closed, and its
  hours count as pool hours.
- Every traded market closing in that span has a tape line. Otherwise its match would be dropped as "no tape" (A5)
  only because the download had not reached it.

The shard job checks this before sweeping, and the report job checks it again from each shard file's
`meta.coverage`. To recover, run the data workflow until a download finishes, then use "Re-run all jobs" (a run that
was never scored can be re-run).

### Re-runs

A failed shard leg can be re-run ("Re-run failed jobs"). It rewrites that leg's files under the same run id, and the
report then runs once. Once a run id is scored (its registry is in `runs/<run>/report/`), nothing under it is
overwritten. "Re-run all jobs" fetches fees and history again, so it fails in prep. A shard job re-run on its own fails
before it sweeps. A re-run report job (after a later step failed) keeps the Drive report and registry, uses them for
the ledger rows and the commit comment, and fails if its own registry differs. A new measurement is a new commit of
the request.

Cross-match state (the tennis-only pacer, the 25% / 10% caps, the coin-placebo stream and family B's placebo reservoir)
restarts at each slice's first unit, so it restarts only at unit edges. The result depends on the shard count, which is
why the count should stay fixed across rounds.

## Shard file (gzip JSON)

```
{ meta: { simVersion: 'tennis-ta-sim/2', stage, pool, run, k, j, shards, subShards, from, to, units, dataVersion,
          coverage, requestSha, families: ['A'] | ['A','B'], ...bookkeeping (sha, unitsSha, stratum, evidence,
          lookbackDays (1 on H, 7 on R), configs, sticks, poolSpans, episodeCols, timings) },
  matchList: [MatchInfo + pool + unit],
  runs: [SimRun + stick?: true],
  familyB?: FamilyBExport }
```

- `meta` comes first in the file, so `readShardMeta` can read it without inflating the rest.
- `coverage` has, per series, the history's first and last day files, the file count, and the swept span's days with
  and without a market file (missing days are listed) and with a trade tape. It also has the download's complete
  listing (`listed`), the close times the slice reads (`need`), the market lines closing then, how many of those
  were untraded, and the traded ones without a tape (`tapesMissing`). It also counts owned matches without a
  published start. Those matches keep the earliest market-line time for their unit and pool, and they are counted and
  listed rather than dropped.
- Measuring sticks have ids `A|s1|prod|<name>|<fill>` and carry `stick: true`. Stage 1 has two:
  `A|s1|prod|settlehold|F1` (`TENNIS_END_LOSER_CUT=false`) and `A|s1|prod|nopacer|F1` (`HARNESS_PACER=off`).

## Pools (A3)

- A match is in a pool only if both its start and its close are before the hard cutoff, Nov 5 02:00 UTC.
- Lockbox weeks are keyed by id from a `[start, end)` table anchored at Nov 6 05:00 UTC in 7-day steps: L1 is Nov 6 to
  Nov 13, L2 is Nov 13 to Nov 20, and so on. A match that reaches an unopened lockbox week is out.
- A match belongs to the unit that holds its start.
- Matches starting within 24 h of a sealed unit are embargoed.
- `node --import tsx research/tennisTaSweep.ts pool-hours --units models/tennis-ta/state/units.json` prints each disc
  unit's countable intervals.
