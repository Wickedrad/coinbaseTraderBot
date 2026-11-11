# The heat curve reader

`python/heat_reader` is a small Python service that runs beside the bot on the server. Once a minute, for each coin, it brings the coin's Binance spot 1-minute bars up to date, asks the oracle engine (`python/oracle/heat_live.py`, the same code that built the heat tables) which event keys fire at the last closed minute, joins them with the oracle run's packs and writes one file: the calls file the bot reads (`HeatCallsFile` in `bot/heat/types.ts`). The bot never runs this code and this code never talks to Kalshi or Coinbase: the file is the whole contract. How the bot trades on the file is in `docs/HEAT_LANE.md`.

It holds no secret, reads no secret and needs no API key: Binance's public market data address (`data-api.binance.vision`) is all it calls. It never reads DOGE, whatever the settings say.

## What it reads each minute

The oracle run's packs, from `HEAT_PACK_DIR`:

| File | Schema | What the reader takes from it |
|---|---|---|
| `traded_pack.json` | `oracle-heat-pack-1` | The single rows. Only rows with `rank_coin` up to `HEAT_READER_MAX_RANK` (default 40, the heat ladder) are asked for; the share-only rows beyond it are never published. Rows with `live_parity` false are skipped. |
| `pair_pack.json` | `oracle-heat-pairs-1` | Pair and triple rows. A row fires when its `when` event fires at this minute close (the same rule as a single, aliases included) and every `conds` reading holds its level at the last closed bar of its own timeframe. Rows with `dominance` true are skipped: the reader has no dominance feed yet. |
| `clock_pack.json` | `oracle-heat-clock-pack-1` | Only when `HEAT_CLOCK_PACK=true`, and then only rows with `lift_above_twin_max` true (30 of 377 at fd88805): the oracle thread found the rest no better than chance. |
| `live_meta.json` | keyed by coin | Each coin's zone edges, price step and `table_sha256`. A pack row whose table hash differs from the coin's meta is skipped, so a reading is never compared against edges of another table. |

A pair or triple row is published with the rank it would have on the coin's single ladder at that horizon (1 plus the number of the coin's singles with `rank_coin` up to the top and a higher `oheat_B`), because a pair row's own `rank_coin` counts among every pair event of the coin and is not a ladder rank.

The 60-minute timeframe needs about 150 days of minutes (3,000 hourly bars plus the engine's look-back), which is the slow and memory-hungry read. Its readings change only when an hourly bar closes, so the reader keeps each coin's 60-minute states and reads the long window again only at the first pass, when an hourly bar closes, or when the packs change. Every other minute it reads the shorter window of the other timeframes. A coin whose packs need no 60-minute reading (XRP at fd88805) never reads the long window.

Every row the reader leaves out is counted by reason in the status file beside the calls file, so the bot's status shows what is not traded and why: `rank beyond HEAT_READER_MAX_RANK`, `live_parity false`, `dominance (no feed)`, `table hash differs`, `clock pack of another run`, `clock row not above the twin`.

## Settings

All optional. The service gets them from `~/bot/heat-reader.env`, which `deploy/heat_reader_install.sh` writes from the same names in `~/bot/bot.env`; flags of the same name (for example `--max-rank 30`) override them when run by hand.

| Name | Default | What it does |
|---|---|---|
| `HEAT_CALLS_FILE` | `<DATA_DIR>/heat_calls.json` | The file the bot reads. On the server it must be under `~/bot/data/` (the only folder the unit may write). |
| `HEAT_READER_DIR` | `<DATA_DIR>/heat_reader` | The minute cache and `status.json`. |
| `HEAT_PACK_DIR` | `research/oracle_heat/latest` inside the release | The four pack files above. |
| `HEAT_ORACLE_PATH` | the release's `python/` folder | The folder that holds the `oracle` package. |
| `HEAT_ASSETS` | `BTC,ETH,SOL,XRP` | Coins to read. DOGE is refused even when listed. |
| `HEAT_WINDOW_BARS` | `3000` | Bars per timeframe the engine reads (the tables were built on 3,000). At least 300. |
| `HEAT_READER_MAX_RANK` | `40` | Traded pack rows with a higher `rank_coin` are never published. |
| `HEAT_CLOCK_PACK` | `false` | Also load `clock_pack.json` (the rows above the twin only). |
| `HEAT_BINANCE_API` | `https://data-api.binance.vision/api/v3` | The public market data address. Tests point it at a local server. |
| `HEAT_RUN` | read from the pack's stamp | Overrides the oracle run id written into the calls file. |
| `DATA_DIR` | `./data` | Only used for the two defaults above (the bot's own default, so both sides agree on the file). |

The defaults need no path setting on the server: the unit runs the reader from `~/bot/current/python`, and the release holds the oracle package and the packs beside it, so a deploy moves code and curves together. A setting the reader cannot run with (a window below 300, a rank below 1, `HEAT_CLOCK_PACK=maybe`) makes it exit with code 2 and the reason in the log.

## Files

| File | Written | What is in it |
|---|---|---|
| `HEAT_CALLS_FILE` | every minute, atomically (written beside it, then renamed) | One JSON object: `v`, `source`, `run`, `packSha` (SHA-256 of `traded_pack.json`), `writtenAt`, and per coin `ok`, `why` when not ok, and the rows that fired at the last closed minute (`kind` single, pair or triple). The shape is `HeatCallsFile` in `bot/heat/types.ts`. |
| `heat_calls-YYYY-MM-DD.jsonl` beside it | every minute, one line appended | The same object, one line per minute, for replays. Kept 14 days. |
| `heat_calls.status.json` beside it (the calls file's name with `.status.json` for `.json`) | every minute | For the bot's status: `run`, `packSha`, `maxRank`, `clockPack`, `packs` (each file's SHA-256, rows and schema), `problem` when the packs cannot be used, and per coin `ok`, `fired` (rows fired this minute, by kind), `rows` (`wanted` by kind: single, pair, triple, clock; `skipped` by reason) and `why` when not ok. |
| `HEAT_READER_DIR/status.json` | every minute | The reader's own measurements: seconds per pass and per coin, minutes cached, whether the 60-minute states were read or kept, counters (passes, network errors, engine errors), RSS and peak RSS in MB. |
| `HEAT_READER_DIR/minutes/<COIN>.min` | appended every minute | The minute cache, so a restart does not download 150 days again. A file that does not read back whole is removed and downloaded again. |

## Memory, and why the unit limits it

The server is small and the bot comes first. Measured on 4 coins with the real packs at fd88805: the reader idles near 90 MB and peaks near 150 MB, at its first pass and then once an hour per coin when a coin's 60-minute timeframe is read on 150 days of minutes. `deploy/heat-reader.service` therefore sets `MemoryHigh=180M` (above it the kernel squeezes the reader), `MemoryMax=220M` (above it the reader is killed and restarted), `OOMScoreAdjust=900` (when the whole server runs out of memory the reader goes first, never the bot), `Nice=10` and `CPUQuota=50%`. The numeric libraries run one thread each, and freed memory is handed back after each coin, so the idle reader stays small. The check job below measures these numbers again on a GitHub runner.

If the reader dies or falls behind, the bot sees a stale or missing calls file and the heat lane opens nothing; nothing else in the bot changes.

## Running it by hand

From the repo's `python/` folder, with a Python 3.11 to 3.14 venv built from the pinned wheels:

```
python3 -m venv /tmp/heat-venv
/tmp/heat-venv/bin/pip install --require-hashes --only-binary=:all: -r heat_reader/requirements.txt
HEAT_PACK_DIR=<folder with the packs> HEAT_ORACLE_PATH=<folder holding oracle/> DATA_DIR=/tmp/heat-data \
  /tmp/heat-venv/bin/python -m heat_reader --once
```

`--once` reads one minute and exits: 0 when at least one coin was read, 1 when none was. Without `--once` it runs until stopped (SIGTERM or Ctrl-C). The first pass downloads about 150 days of minutes per coin, which takes a few minutes. Each pass logs one line, for example `heat-reader pass BTC 2 fired in 0.16 s | ETH 0 fired in 0.17 s | SOL 1 fired in 0.16 s | XRP 0 fired in 0.15 s (0.74 s)`.

On the server: `sudo journalctl -u heat-reader -n 20 --no-pager` and `cat ~/bot/data/heat_calls.status.json`.

The parity replay runs the reader's own code path on minutes the full engine has already answered:

```
/tmp/heat-venv/bin/python -m heat_reader.replay --fixtures <research/oracle_heat/parity> --out /tmp/parity.json
```

Tests, from `python/`: `python -m pytest heat_reader/tests -q -p no:cacheprovider`.

## The check job

`.github/workflows/heat-reader-check.yml` runs the reader the way the server runs it, on real Binance minutes, against the oracle's code and packs at a pinned commit. It is started by a push to `claude/project-thread-rvpht4` that changes `python/heat_reader/CHECK_RUN`:

```
oracle=fd88805
note=first check
```

`oracle` is the commit whose `python/oracle` and `research/oracle_heat` are used (the reader itself is the pushed commit's); `note` is free text shown in the comment. To run it again, change the note (or the oracle commit) and push.

What it does, in order:

1. Builds the reader's venv on Python 3.12 from `python/heat_reader/requirements.txt` with `--require-hashes --only-binary=:all:`, as the install script does, and records its size.
2. Runs `--once` for BTC, ETH, SOL and XRP on a fresh folder under `/usr/bin/time -v`: the download, the first read and the peak memory.
3. Runs the loop for 4 minutes on the same minute cache, sampling its RSS every 5 seconds.
4. Replays Dec 29 to 31, 2025 from `data-api.binance.vision` through the reader's own code path and compares with `research/oracle_heat/parity/<COIN>/fixture.json.gz` from the oracle commit.
5. Uploads the calls files, the status files, the logs and the report as the artifact `heat-reader-check-<run id>` (kept 90 days).
6. Posts one commit comment on the pushed commit with the report, and also puts it in the run's summary. The run shows red when a measuring step failed, but the comment is posted anyway with what was measured.

How to read the comment:

- **The per-coin table.** `read ok` counts the loop's files where the coin was ok (it should be all of them). `minutes loaded` is the minute cache (218,520 for a coin that needs the 60-minute timeframe at a 3,000-bar window, fewer for one that does not). `rows wanted` and `rows skipped, by reason` are the pack rows the reader asks for and leaves out (at fd88805 with the default settings: BTC 80 / 89 / 8, ETH 80 / 97 / 2, SOL 77 / 85 / 0, XRP 80 / 103 / 4 singles / pairs / triples). `fired in the loop` counts rows over the 4 minutes, by kind. `s per pass` is that coin's fetch and engine time. `parity` is the coin's share of agreeing single keys and pair triggers.
- **Memory.** The first pass's peak RSS (from `/usr/bin/time`, the download included), the loop's peak (the kernel's high mark for the process) and its idle RSS (the median of the samples). Both peaks must stay well under the unit's `MemoryHigh` of 180 MB.
- **Parity.** The share of published single keys (and of the pair rows' trigger events) both the full engine and the reader fire, out of all keys either fires. The fixture holds events only, so a pair's conditions are not compared. A coin is skipped with a reason when its fixture is of another table than the pack.

## What the deploy needs

The deploy workflow and the scope check are not changed by the reader's branch; to run the reader on the server they need, once the oracle branch (with `python/oracle` and `research/oracle_heat/latest`) is merged:

1. The release must ship, beside what it ships today: `python/heat_reader`, `python/oracle`, and from `research/oracle_heat/latest` the files `traded_pack.json`, `pair_pack.json`, `clock_pack.json` and `live_meta.json` (and `RUN`, for the record). In `.github/workflows/deploy.yml` that is the upload step's `source` list. The rest of `research/oracle_heat` (the league tables, the viewer, the parity fixtures) is not needed on the server.
2. `deploy/deploy-scope.ts` counts `python/` and research data as research-only, so a push that changes only the reader or the packs would not deploy. Those paths must count as bot code.
3. After `bash deploy/activate.sh ...`, run `bash deploy/heat_reader_install.sh`, and let it fail without failing the deploy (it exits 1 when `HEAT_LANE=true` and the reader cannot start; the bot is not affected). It stops and disables the reader when `HEAT_LANE` is not true.
4. The server needs Python 3.11 to 3.14 with the venv module (the deploy already installs `python3-venv`). The venv lives at `~/bot/.venv-heat-reader` and is rebuilt only when the pins or the Python change.

The install script refuses to start the reader when the release lacks any of these files, with a message that names the missing file and points here.
