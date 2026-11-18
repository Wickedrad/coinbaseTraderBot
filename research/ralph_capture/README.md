# Ralph raw-frame capture (research only)

Iteration 0047 of Ralph Phase A. Status: **built and tested against a local scripted server only. No real Kalshi frame has
been captured, so nothing here is market evidence yet.** Ralph STOP stays in force: no orders, no deploy, no curve, grader,
pin or ledger change, and nothing in `bot/` starts this code.

## What is here

| File | Purpose |
|---|---|
| `bot/kalshi/ws.ts` (small seam) | `RawFrameSink` interface and `setRawSink()`. Nothing in the bot calls `setRawSink`, so by default the sink is undefined and every hook is a no-op. A sink that throws is detached and the bot carries on. |
| `rawTap.ts` | The sink: a create-only (mode 0600), SHA-256 hash-chained journal of transport events (connecting, open, error, close), commands sent, and every frame as received, with wall and monotonic receipt times and a connection epoch. Frozen capture config and its hash in line 1. Chain-head checkpoints go to a separate anchor file. |
| `verify_journal.py` | Offline checker (stdlib, no network). Re-derives type, sid and seq from the stored text and checks the chain, footer, config hash, epoch and clock rules, and order-book continuity **per ticker**. |
| `captureCli.ts` | Read-only capture runner for the owner to use with a key. Refuses to start without `--authorized-by-owner`. Not run by the bot or CI. |
| `test_verify_journal.py`, `tests/ralphRawTap.test.ts` | 52 + 18 tests. The Python tests build journals independently of the TS writer. |

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

## Not done yet (honest list)

1. **A real capture.** Needs the owner's go-ahead and either a Kalshi key for `captureCli.ts` or the tap attached inside the
   paper bot (a one-line `ws.setRawSink(...)` in `bot/main.ts`, which is a bot-code change and a deploy).
2. Off-box anchor retention: the operator has to copy the anchor file somewhere this machine cannot edit.
3. `decideHeat` receipts. `decideHeat` is pure (inputs: now, cfg, snapshot, markets, state), so what is missing is a record of
   those inputs and outputs at each `HeatLane.decide` call, tied to the journal by time and head hash. That is a second
   production seam and was not attempted here. The journal can already be replayed through the bot's own `onMessage` (see
   the replay test), which is the first half of binding books to decisions.
4. Existing server recordings (`md-*.jsonl`) hold only normalized events with no sid or seq; they cannot be upgraded.
5. The 0036-0046 Python validators from the earlier archive are not included here; this change does not depend on them.

## Run

```
python3 -I research/ralph_capture/test_verify_journal.py
node --import tsx --test tests/ralphRawTap.test.ts
python3 -I research/ralph_capture/verify_journal.py JOURNAL --anchor ANCHOR
```
