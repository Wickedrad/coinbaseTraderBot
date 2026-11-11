// Heat entry lane: the book. What the lane has open, what its finished round trips made, and the few memories its
// rules need across a restart (the hour's direction per coin, calls already acted on, contracts left at a loss).
//
// The lane (heatLane.ts) decides; this file only keeps the record straight against the position book. Everything
// here works on a plain state object and takes the time as an input, so the tests need no files and no clock.

import { EPS } from '../util/num';
import { readJson } from '../util/persist';
import type { HeatBookState, HeatOpen } from './types';

/** An immediate-or-cancel entry the position book has not shown this long after it was sent filled nothing. */
export const HEAT_UNFILLED_DROP_MS = 30_000;
/** A call the lane acted on is forgotten after this long: its bar is long over, the key cannot come back. */
export const HEAT_ACTED_KEEP_MS = 2 * 3_600_000;

/** The saved file: the contract's book state plus one memory of the lane's own. */
export interface HeatLaneState extends HeatBookState {
  /** Contracts the lane traded and left, win or loss (ticker to close time). The re-entry rule needs it (a contract
   *  already traded is entered again only while more than half of its window is left) and lossTickers only keeps
   *  the losses. Pruned once the contract is over. */
  traded?: Record<string, number>;
}

/** What the lane needs from a market's row in the position book (bot/oms/positions.ts MarketPosition has this shape). */
export interface HeatPositionView {
  /** Signed YES contracts held. */
  yes: number;
  netCash: number;
  fees: number;
  settled?: boolean;
  /** The market's realized P&L once it settled, net of fees. */
  realized?: number;
}
export type HeatPositionLookup = (ticker: string) => HeatPositionView | undefined;

/** A finished heat round trip. */
export interface HeatClosed {
  ticker: string;
  asset: string;
  kind: '15m' | 'hourly';
  side: 'yes' | 'no';
  ruleId: string;
  h: number;
  /** What the round trip made, net of fees. */
  pnl: number;
  /** true = it ended at settlement, false = the position was sold. */
  settled: boolean;
}

export interface HeatSyncResult {
  /** Entries first seen as a position in this pass. */
  opened: string[];
  closed: HeatClosed[];
  /** Entries dropped as never opened (the order filled nothing): their tag must come off. */
  dropped: string[];
}

export function emptyHeatState(): HeatLaneState {
  return { v: 1, trips: 0, wins: 0, pnl: 0, open: [], lastExit: {}, lossTickers: {}, context: {}, acted: {}, traded: {} };
}

/** Load the saved state, or start empty when there is no file. A file that parses but is not a heat state stops the
 *  start instead of being reset: it holds the pilot budget's running loss, and guessing it away would hand the lane
 *  a fresh budget. */
export function loadHeatState(file: string | undefined): HeatLaneState {
  const saved = file ? readJson<Partial<HeatLaneState>>(file) : undefined;
  if (saved === undefined) return emptyHeatState();
  const num = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
  const rec = (x: unknown): x is Record<string, unknown> => typeof x === 'object' && x !== null && !Array.isArray(x);
  if (!rec(saved) || saved.v !== 1 || !num(saved.trips) || !num(saved.wins) || !num(saved.pnl) || !Array.isArray(saved.open)) {
    throw new Error(`${file} is not a heat lane state file (version 1 expected): move it aside to start the heat book empty`);
  }
  const e = emptyHeatState();
  return {
    v: 1, trips: saved.trips, wins: saved.wins, pnl: saved.pnl, open: saved.open,
    lastExit: rec(saved.lastExit) ? saved.lastExit : e.lastExit,
    lossTickers: rec(saved.lossTickers) ? saved.lossTickers : e.lossTickers,
    context: rec(saved.context) ? saved.context : e.context,
    acted: rec(saved.acted) ? saved.acted : e.acted,
    traded: rec(saved.traded) ? saved.traded : {},
  };
}

/** Forget what can no longer matter: old claims, contracts that are over, an hour's direction past its hour.
 *  Returns whether anything went, so the caller saves only then. */
export function pruneHeatState(st: HeatLaneState, now: number): boolean {
  let changed = false;
  const drop = <T>(map: Record<string, T> | undefined, gone: (v: T) => boolean) => {
    for (const [k, v] of Object.entries(map ?? {})) if (gone(v)) { delete map![k]; changed = true; }
  };
  drop(st.acted, (barClose) => now - barClose > HEAT_ACTED_KEEP_MS);
  drop(st.lossTickers, (closeTs) => closeTs <= now);
  drop(st.traded, (closeTs) => closeTs <= now);
  drop(st.context, (c) => c.until <= now);
  return changed;
}

/** Bring the open entries in line with the position book: an entry the book now shows is open; an open one that is
 *  flat again, or whose market settled, is a finished round trip; one never seen open 30 s after it was sent is
 *  dropped. Changes `st` in place; the result says what happened so the engine can untag and write its rows. */
export function syncHeatBook(st: HeatLaneState, now: number, lookup: HeatPositionLookup): HeatSyncResult {
  const res: HeatSyncResult = { opened: [], closed: [], dropped: [] };
  const keep: HeatOpen[] = [];
  for (const o of st.open) {
    const pos = lookup(o.ticker);
    if (pos && !pos.settled && Math.abs(pos.yes) > EPS) {
      if (o.openedAt === undefined) { o.openedAt = now; res.opened.push(o.ticker); }
      keep.push(o);
      continue;
    }
    // Flat, settled, or unknown to the book. The market was flat when the entry went out and the engine keeps every
    // other lane off it, so cash or fees that moved since then can only be this entry: it filled and was closed
    // between two looks. Counting that as a drop would lose the round trip's result (and the pilot budget's loss).
    const moved = !!pos && (Math.abs(pos.netCash - o.cash0) > EPS || Math.abs(pos.fees - o.fees0) > EPS);
    if (o.openedAt === undefined && !moved) {
      if (now - o.sentAt > HEAT_UNFILLED_DROP_MS) res.dropped.push(o.ticker); else keep.push(o);
      continue;
    }
    if (!pos) {
      // Seen open, and the book no longer knows the market (its record was pruned or reset). The result cannot be
      // known, so it is not counted as a round trip; the entry goes, and its tag with it.
      res.dropped.push(o.ticker);
      continue;
    }
    if (o.openedAt === undefined) res.opened.push(o.ticker);
    // The change in the market's cash and fees since the entry was sent. At settlement the book's realized figure
    // (cash plus payout less fees) replaces cash less fees; it is the same number once the payout is in the cash.
    const before = o.cash0 - o.fees0;
    const pnl = +((pos.settled && pos.realized !== undefined ? pos.realized : pos.netCash - pos.fees) - before).toFixed(6);
    st.trips++;
    st.pnl = +(st.pnl + pnl).toFixed(6);
    if (pnl > 0) st.wins++;
    st.lastExit[o.asset] = now;
    if (pnl < 0) st.lossTickers[o.ticker] = o.closeTs;
    (st.traded ??= {})[o.ticker] = o.closeTs;
    res.closed.push({ ticker: o.ticker, asset: o.asset, kind: o.kind, side: o.side, ruleId: o.ruleId, h: o.h, pnl, settled: !!pos.settled });
  }
  st.open = keep;
  return res;
}
