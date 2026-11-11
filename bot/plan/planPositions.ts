// Positions opened by the plan's rules (pipeline plan, Stage 0), keyed by market ticker: the side, the rule, when it opened,
// the position's own ratchet settings and the ratchet's state (bot/plan/planRatchet.ts). Saved to its own JSON file next to
// the other money state (the book folder: DATA_DIR in paper, DATA_DIR/live in live), written atomically on every change, so a
// restart or deploy resumes an armed ratchet at its stop. In memory only without a file (the replay).
//
// The plan's entry lane (E01, not built yet) tags a position as it opens it: tag(...). Nothing else tags; the tests tag
// directly. A second tag on a plan position already open on the same side keeps the first (its ratchet's stop is never
// lowered). A tag clears itself once the position is flat (a fill or the settlement that empties it, or an evaluation that finds
// it flat), with PLAN_RULES on or off, when the position turns to the other side, and when a tag never saw its position open
// within 5 minutes (an entry that did not fill).

import { logger } from '../util/log';
import { readJson, writeJsonAtomic } from '../util/persist';
import type { RatchetSettings } from '../strategy/profitRatchet';
import { freshPlanState, type PlanRatchetSettings, type PlanRatchetState } from './planRatchet';

const log = logger('plan');

export interface PlanPosition {
  ticker: string;
  side: 'yes' | 'no';
  ruleId: string;
  openedAt: number;
  settings: PlanRatchetSettings;
  state: PlanRatchetState;
  /** The position was seen open (a tag made before its entry fills waits for it). */
  seenOpen?: boolean;
}

export interface PlanTag {
  ticker: string;
  side: 'yes' | 'no';
  ruleId: string;
  openedAt?: number;
  /** The rule's tested ratchet settings (dollars for the whole position); what it leaves out comes from the profit ratchet's
   *  (RATCHET_ARM_USD, RATCHET_STOP_MIN_USD, RATCHET_TRAIL_USD) and the tick clock. */
  settings?: Partial<PlanRatchetSettings>;
}

/** A tag that never saw its position open is dropped after this long. */
export const PLAN_TAG_UNFILLED_MS = 5 * 60_000;

/** v2 since Nov 11 (one ratchet in dollars for the whole position); a v1 file's cents-a-contract ratchets are not read. */
interface Saved { v: 2; positions: PlanPosition[] }

export class PlanPositions {
  private readonly m = new Map<string, PlanPosition>();

  constructor(private readonly defaults: RatchetSettings, private readonly file?: string) {
    this.load();
  }

  /** The entry lane's call: `t.ticker` is now a plan position. A tag on a ticker whose plan position is already open on the
   *  same side (an add) keeps that position's tag as it is, its rule, settings and ratchet state: re-arming from scratch would
   *  lower an armed stop. Otherwise (none, the other side, or an entry never seen open) the new tag replaces the old. */
  tag(t: PlanTag, now: number): PlanPosition {
    const held = this.m.get(t.ticker);
    if (held && held.seenOpen && held.side === t.side) {
      log.info('plan tag on an open plan position: kept as it is', { ticker: t.ticker, ruleId: held.ruleId, newRuleId: t.ruleId, armed: held.state.armed });
      return held;
    }
    const p: PlanPosition = {
      ticker: t.ticker, side: t.side, ruleId: t.ruleId, openedAt: t.openedAt ?? now,
      settings: this.settingsOf(t.settings),
      state: freshPlanState(),
    };
    this.m.set(t.ticker, p);
    this.save();
    return p;
  }

  /** A rule's settings over the defaults (the profit ratchet's) and the tick clock. */
  private settingsOf(o: Partial<PlanRatchetSettings> | undefined): PlanRatchetSettings {
    const d = this.defaults;
    return { armUsd: o?.armUsd ?? d.armUsd, stopMinUsd: o?.stopMinUsd ?? d.stopMinUsd, trailUsd: o?.trailUsd ?? d.trailUsd, clock: o?.clock ?? 'tick' };
  }

  get(ticker: string): PlanPosition | undefined {
    return this.m.get(ticker);
  }

  all(): PlanPosition[] {
    return [...this.m.values()];
  }

  /** The market's position now (signed YES contracts): the tag when it still holds, else undefined (a flat, reversed or
   *  never-filled tag is cleared). */
  sync(ticker: string, position: number, now: number): PlanPosition | undefined {
    const p = this.m.get(ticker);
    if (!p) return undefined;
    if (Math.abs(position) < 1e-9) {
      if (p.seenOpen || now - p.openedAt > PLAN_TAG_UNFILLED_MS) this.forget(ticker);
      return undefined;
    }
    if ((position > 0) !== (p.side === 'yes')) { this.forget(ticker); return undefined; }
    if (!p.seenOpen) { p.seenOpen = true; this.save(); }
    return p;
  }

  /** The ratchet's new state (saved when it changed). */
  setState(ticker: string, state: PlanRatchetState): void {
    const p = this.m.get(ticker);
    if (!p || JSON.stringify(p.state) === JSON.stringify(state)) return;
    p.state = state;
    this.save();
  }

  /** A fill left the market flat: its tag is cleared when the position was open on the tag's side before the fill
   *  (`positionBefore`, signed YES contracts) or was seen open. A tag still waiting for its entry is kept. */
  flat(ticker: string, positionBefore?: number): void {
    const p = this.m.get(ticker);
    if (!p) return;
    const wasOpen = positionBefore !== undefined && Math.abs(positionBefore) > 1e-9 && (positionBefore > 0) === (p.side === 'yes');
    if (p.seenOpen || wasOpen) this.forget(ticker);
  }

  forget(ticker: string): void {
    if (this.m.delete(ticker)) this.save();
  }

  private save(): void {
    if (!this.file) return;
    try {
      writeJsonAtomic(this.file, { v: 2, positions: this.all() } satisfies Saved, { compact: true });
    } catch (e) {
      log.warn('plan positions not saved', { file: this.file, error: String(e) });
    }
  }

  private load(): void {
    if (!this.file) return;
    const s = readJson<{ v?: number; positions?: PlanPosition[] }>(this.file, { quarantine: true });
    // A v1 file (cents a contract, before Nov 11) keeps its tags with today's settings and a fresh ratchet: its floor was a
    // price, not a profit, and cannot be read as a stop.
    const v2 = s?.v === 2;
    for (const p of s?.positions ?? []) {
      if (!p || typeof p.ticker !== 'string' || (p.side !== 'yes' && p.side !== 'no')) continue;
      const state = v2 ? { ...freshPlanState(), ...p.state, gaps: Array.isArray(p.state?.gaps) ? p.state.gaps : [] } : freshPlanState();
      this.m.set(p.ticker, { ...p, settings: this.settingsOf(v2 ? p.settings : { clock: p.settings?.clock }), state });
    }
  }
}
