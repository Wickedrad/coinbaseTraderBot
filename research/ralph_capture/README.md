# Ralph raw-frame capture (research only)

Iteration 0047 of Ralph Phase A. Status: **built and tested against a local scripted server only. No real Kalshi frame has
been captured, so nothing here is market evidence yet.** Ralph STOP stays in force: no orders, no deploy, no curve, grader,
pin or ledger change.

## What is here

| File | Purpose |
|---|---|
| `bot/kalshi/ws.ts` (small seam) | `RawFrameSink` interface and `setRawSink()`. Nothing in the bot calls `setRawSink`, so by default the sink is undefined and every hook is a no-op. A sink that throws is detached. |
| `rawTap.ts` | The sink: a create-only, SHA-256 hash-chained journal of transport events (connecting, open, error, close), commands sent, and every frame exactly as received (bytes hashed, text kept), with wall and monotonic receipt times and a connection epoch. Frozen capture config and its hash in line 1. Chain-head checkpoints go to a separate anchor file. |
| `verify_journal.py` | Offline checker (stdlib, no network). Re-derives type, sid and seq from the raw text, checks the chain, footer, config hash, epoch and clock rules, and per-subscription sequence continuity (gap, delta before snapshot, disconnect, dropped frames each invalidate until a new snapshot). |
| `captureCli.ts` | Read-only capture runner for the owner to use with a key. Refuses to start without `--authorized-by-owner`. Not run by the bot or CI. |
| `test_verify_journal.py`, `tests/ralphRawTap.test.ts` | 35 + 8 tests. |

## What the journal does and does not prove

* Proves: bytes were hashed on receipt; order, epochs and times are consistent; the file was not edited after writing
  (only if the anchor was kept somewhere this process could not reach); where sequence continuity breaks.
* Does **not** prove: that Kalshi sent the bytes. `exchange_authenticated` and `phase_b_eligible` are constants `false` in
  the verifier. Authentic frames need a real, authorized connection.
* Private channels (`fill`, `user_orders`, anything not in `PUBLIC_TYPES`, anything unparsable) are stored as length and
  SHA-256 only, with sid and seq kept so continuity stays checkable. Headers and keys never reach the sink.

## Not done yet (honest list)

1. A real capture. Needs the owner's go-ahead and either a Kalshi key for `captureCli.ts` or the tap attached inside the
   paper bot (a one-line `ws.setRawSink(...)` in `bot/main.ts`, which is a bot-code change and a deploy).
2. Off-box anchor retention (the operator must copy the anchor file elsewhere).
3. `decideHeat` receipts. `decideHeat` is pure (inputs: now, cfg, snapshot, markets, state), so the missing piece is a
   record of those inputs and outputs at each `HeatLane.decide` call, tied to the journal by time and head hash. That is a
   second production seam and was not attempted here.
4. Existing server recordings (`md-*.jsonl`) hold only normalized events with no sid or seq; they cannot be upgraded.
