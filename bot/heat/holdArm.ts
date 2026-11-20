// The NO hold-to-settlement arm (Steven, Nov 20 2026 12:03 PM EST / 17:03 UTC: "to help better gauge which side might get
// more relaxed stop losses"). Paper test, off in live: a share of the heat lane's NO entries is held to settlement (no
// ratchet, no loser cut, no end rule, no hold exit, no pacer snipe); the rest is the control and exits as every heat position
// does. Which NO entry is held is a fixed function of its ticker, so the same market always falls in the same arm and the
// analysis (python/lossreview) can recompute the arm from the ticker alone, with no new field in the trip schema:
//
//   hold = side === 'no' && fnv1a32(ticker) / 2^32 < share
//
// FNV-1a, 32 bit, over the ticker's UTF-8 bytes. The test vectors in tests/heatLane.test.ts pin the hash, so a python mirror
// can be checked against them.

/** FNV-1a, 32 bit, over the UTF-8 bytes of `s` (offset basis 0x811c9dc5, prime 0x01000193). Unsigned. */
export function fnv1a32(s: string): number {
  let h = 0x811c9dc5;
  for (const b of Buffer.from(s, 'utf8')) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/** Where a ticker falls in 0..1 (its hash over 2^32). */
export function armPosition(ticker: string): number {
  return fnv1a32(ticker) / 4294967296;
}

/** True when this entry is in the NO hold arm: a NO entry whose ticker falls below `share` (HEAT_NO_HOLD_SHARE). 0 = no
 *  entry is held (the arm is off), 1 = every NO entry is. A YES entry is never held. */
export function inNoHoldArm(ticker: string, side: 'yes' | 'no', share: number): boolean {
  return side === 'no' && share > 0 && armPosition(ticker) < share;
}
