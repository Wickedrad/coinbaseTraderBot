// The settlement index's volatility estimate carried over a restart (E06). IndexTracker's EWMA needs 120 one-second returns
// before a contract can be priced, so after every restart or deploy each coin went about 2 minutes without a price (and,
// before the engine's exit-only lane, without any exit). main.ts saves each coin's EWMA state here every 30 s and on
// shutdown; the next start continues an estimate whose last return is at most VOL_STATE_MAX_AGE_MS old (two of the
// EWMA's 5-minute half-lives) and warms up from nothing otherwise. The same estimator on the same series: no outside price
// (Coinbase candles, Binance) enters the settlement index's pricing. Paper and live alike; replays and backtests never
// load it.

import { readJson, writeJsonAtomic } from '../util/persist';
import type { IndexTracker } from './indexTracker';

export const VOL_STATE_FILE = 'index_vol_state.json';
export const VOL_STATE_MAX_AGE_MS = 10 * 60_000;

interface Saved { savedAt: number; assets: Record<string, { ewmaVar: number; samples: number; ts: number }> }

/** Writes every tracker's estimate (nothing when none has one yet, so a fresh start does not wipe a good file). */
export function saveVolState(file: string, trackers: Map<string, IndexTracker>, now: number): void {
  const assets: Saved['assets'] = {};
  for (const [asset, t] of trackers) {
    const s = t.volState();
    if (s) assets[asset] = s;
  }
  if (!Object.keys(assets).length) return;
  writeJsonAtomic(file, { savedAt: now, assets } satisfies Saved, { compact: true });
}

/** Restores the saved estimates whose last return is recent (not from the future either); returns the assets restored. */
export function loadVolState(file: string, trackers: Map<string, IndexTracker>, now: number, maxAgeMs = VOL_STATE_MAX_AGE_MS): string[] {
  const saved = readJson<Saved>(file, { quarantine: true });
  const out: string[] = [];
  for (const [asset, s] of Object.entries(saved?.assets ?? {})) {
    if (!s || !(now - s.ts <= maxAgeMs) || s.ts > now + 60_000) continue;
    if (trackers.get(asset)?.restoreVol(s)) out.push(asset);
  }
  return out;
}
