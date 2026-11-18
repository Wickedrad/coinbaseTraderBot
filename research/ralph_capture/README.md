# Ralph raw-frame capture (research only)

Iterations 0047 to 0049 of Ralph Phase A. Status: the frame tap was merged and run once on the paper bot (2026-11-18, 6 minutes,
capped at 500 MB); the verifier, run on the server by the owner, reported it locally consistent (814,846 records, no sequence
gaps; the journal is private and not in this repo), but its frames are unauthenticated, so it is **not** exchange-authenticated evidence and Phase B stays blocked. Decision receipts (0049, below) are
built and tested on scripted data only; none has been captured from the real bot. Ralph STOP stays in force: no orders, no
curve, grader, pin or ledger change; the bot starts this code only when `RALPH_RAW_TAP=1`, which is off.

## What is here

| File | Purpose |
|---|---|
| `bot/kalshi/ws.ts` (small seam) | `RawFrameSink` interface and `setRawSink()`. Nothing in the bot calls `setRawSink`, so by default the sink is undefined and every hook is a no-op. A sink that throws is detached and the bot carries on. |
| `rawTap.ts` | The sink: a create-only (mode 0600), SHA-256 hash-chained journal of transport events (connecting, open, error, close), commands sent, and every frame handed to it (public frames as text, the rest as length and hash only, see Privacy), with wall and monotonic receipt times and a connection epoch. Frozen capture config and its hash in line 1. Chain-head checkpoints go to a separate anchor file. |
| `verify_journal.py` | Offline checker (stdlib, no network). Re-derives type, sid and seq from the stored text and checks the chain, footer, config hash, epoch and clock rules, and order-book continuity **per ticker**. |
| `attach.ts` | Starts the tap inside the bot from environment variables (see below). |
| `replayDecisions.ts`, `replayCli.ts` | Walks a journal, checks its chain and numbering itself, and feeds each stored decision receipt back through the bot's own `decideHeat`. See Decision receipts. |
| `captureCli.ts` | Read-only capture runner for the owner to use with a key. Refuses to start without `--authorized-by-owner`. Not run by the bot or CI. |
| `test_verify_journal.py`, `tests/ralphRawTap.test.ts`, `tests/ralphAttach.test.ts` | 75 + 18 + 4 + 24 tests (the last in `tests/ralphDecisions.test.ts`). The Python tests build journals independently of the TS writer. |

## What a passing journal does and does not show

* Shows: the file is internally consistent. A line edited without re-hashing every later line is detected. Receipt times,
  epochs and clocks are coherent. Where `orderbook_snapshot` / `orderbook_delta` sequence continuity breaks, per ticker:
  a gap or a snapshot that skips seqs invalidates every book on that sid; only that ticker's own next snapshot restores it;
  drops, unreadable or unsequenced book frames, and withheld book frames invalidate the connection's books.
* Does **not** show: that Kalshi sent the bytes (`exchange_authenticated` and `phase_b_eligible` are constants `false` in
  the verifier); that nothing was rewritten and re-hashed from the top (only an anchor kept somewhere the capturing process
  cannot reach, and covering the whole journal, i.e. `anchor: matched`, narrows that; `partial` protects the prefix only);
  loss or duplication of frames that carry no seq (trades, lifecycle, index values); frames the tap was never handed.
* Assumption taken from `ws.ts` (it keys its sequence state on sid alone): seq counts frames per subscription across all the
  tickers on it. Real captured data should confirm this before anything relies on it.

## Privacy

Headers and keys never reach the sink. `fill`, `user_orders`, anything not in `PUBLIC_TYPES`, anything unparsable, and any
frame still naming an own-order field after scrubbing are stored as length and SHA-256 only (sid and seq kept). On public
frames, own-order identifiers (`client_order_id`, `order_id`, `subaccount`, `user_id`) are removed from the stored text; the
record then carries `scrubbed`, `stored_sha256` (of the stored text), and `sha256`/`bytes` of the original frame.
Journals belong in a private folder, never in the public repo.

## Running it inside the paper bot (option chosen by the owner, Nov 17 2026)

`bot/main.ts` loads `attach.ts` only when `RALPH_RAW_TAP=1` (a dynamic import: otherwise the module is not executed, no file,
timer or socket hook exists). Settings, all environment variables in the bot's env file:

| Variable | Meaning |
|---|---|
| `RALPH_RAW_TAP=1` | switch on (anything else = off) |
| `RALPH_RAW_TAP_DIR=/absolute/path` | where `kalshi-ws-<time>.journal` and `.anchor` go (created 0700/0600); required, must be absolute |
| `RALPH_RAW_TAP_MAX_MB=500` | stop at this size (1-5000) |
| `RALPH_RAW_TAP_HOURS=24` | stop after this long (0.1-168) |
| `RALPH_RAW_TAP_ALLOW_LIVE=1` | only if ever wanted: without it, live mode refuses to start the tap |

Each bot start writes a new file; a capped or failed capture ends with a footer and is not restarted until the next bot start.
Rollout, all outside this PR and each needing the owner: (1) merge the PR (a bot-code merge, so the Deploy workflow restarts the
paper bot with the flag still off); (2) set the variables in the server's bot env file and restart; (3) after the capture ends,
copy the journal and the anchor file somewhere off the server (private Drive, never the public repo) and run
`verify_journal.py JOURNAL --anchor ANCHOR`. Check free disk first: a capture can reach the size cap. The verifier reads the
journal line by line (peak memory about 45 MB on a 204 MB test journal, against about 417 MB when it read the whole file), so it is
safe to run on the small paper server, preferably under `nice`.

## Decision receipts (iteration 0049)

`HeatLane.decide` (bot/heat/heatLane.ts) hands an optional, read-only `receiptSink` the input it gave `decideHeat` and the result it
got back, after `decideHeat` has answered and before the lane changes its own book. `bot/main.ts` sets the sink only when the tap
is on and the mode is not live. A sink that throws, or returns a rejecting promise, is ignored; the decision is the same with or
without it (tests pin this, including the lane's saved state).

The tap writes each pass as a `decision` record **in the same hash chain as the frames**, so its position says which frames came
before it. The text is JSON with Maps, Sets, NaN, +-Infinity and -0 written as `$map`, `$set` and `$num` wrappers, plus the SHA-256
of each text. What goes in the file is what `decideHeat` can read: from `windows` only the three entry-window keys (the engine
passes its whole strategy settings), and not the reader's file path, a market's working-order count, or an entry's starting cash
and fees. What stays is account state the decision uses: each market's position, the lane's open entries, trips and P&L. The file
is private (mode 0600, never in the public repo) and receipts are never wired in live mode. A receipt that cannot be kept in full
(disk behind, over 8 MB, over the receipts' own 64 MB budget, naming an own order, not serializable) is written as a reason, with
hashes where it was serialized, and the verifier reports `decision_not_recorded` and counts it. The footer counts receipts and
unrecorded receipts. A decision whose input held a NaN, Infinity or -0 is kept as such and flagged
(`decision_on_non_finite_number`), not read as missing data.

* `verify_journal.py` checks the chain, numbering, hashes, strict JSON, own-order field names and the footer counts. It does not
  replay (`decision_replay_checked_here` is `false`).
* `node --import tsx research/ralph_capture/replayCli.ts JOURNAL` walks every line, checks the chain and numbering itself,
  replays each stored input through `decideHeat` and compares with the stored result. Exit 0 means: chain intact, footer present
  and agreeing, at least one receipt, every one reproduced. It does not check the footer's record and frame counts, clocks,
  epochs, the frames' sequence continuity or an anchor, so run `verify_journal.py` as well and ask for both to pass. It prints
  the commit of its own checkout, whether the files `decideHeat` depends on are modified, a SHA-256 of each of them, and the
  release folder the journal recorded; compare those with what was deployed (the deploy log has the commit).
* What a pass does not show: that the receipts are authentic (a writer who re-chains everything can store a consistent pair; only
  an anchor kept elsewhere narrows that, and the replay does not read one); that the server ran this code; that the stored
  bid and ask match the frames (above); or anything about decisions made while the tap was ended or failed.
* A receipt written while frames are being dropped sits before the drop marker, so a later book-binding step must treat the books around a drop as suspect.
* Size: a pass with a large reader file and many markets is on the order of 200 KB. At one pass a minute that is most of the
  default 500 MB cap in a day, and hitting the cap ends the whole tap, frames included; the receipts' own budget stops them from
  taking more than 64 MB of it. Plan a short capture, not a day.

## Not done yet (honest list)

1. **Authenticated real frames.** The first real capture exists and verifies locally; nothing proves Kalshi sent the bytes.
2. Off-box anchor retention: the operator has to copy the anchor file somewhere this machine cannot edit.
3. **Binding the books to the decisions.** Receipts record what `decideHeat` was given, including each market's best bid and ask
   as the engine saw them. Replaying the journal's frames through the bot's own `onMessage` and comparing that book with the
   receipt's bid and ask is the next step and is not built. Until then a receipt shows what the code computes from its
   recorded input, not that the input matched the frames.
4. Existing server recordings (`md-*.jsonl`) hold only normalized events with no sid or seq; they cannot be upgraded.
5. The 0036-0046 Python validators from the earlier archive are not included here; this change does not depend on them.

## Run

```
python3 -I research/ralph_capture/test_verify_journal.py
node --import tsx --test tests/ralphRawTap.test.ts
python3 -I research/ralph_capture/verify_journal.py JOURNAL --anchor ANCHOR
```
