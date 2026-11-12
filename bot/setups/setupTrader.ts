// Live setup trader: the fast and slow lanes on perpetual futures (same interface as PerpTrader, so
// the perps executor turns its targets into orders and keeps the exchange-side stop in place).
//
// Every executor tick:
//   1. manage open trades on the spot price (stop, half off at the first target with the stop to
//      break-even, final target; trail and time stop at each close of the trade's timeframe)
//   2. on every newly closed 15m / 1h / daily candle: run the detectors, score each setup with the
//      model, queue it in its lane (bot/setups/lanes.ts)
//   3. when a lane has room: re-check the best candidates on fresh data (re-scored, still tradable,
//      not chased) and open them
//   4. targets for the executor: contracts per perp = side x remaining share x size; the exchange stop
//      is the trade's stop converted from spot to the perp's price.
// Levels come from spot candles and are checked against the spot price; orders go to the perp.
// The book (queues and open trades) is saved to disk, so a restart resumes managing the trades.
// Inputs from the rest of the bot: the TA network's forecast at the last closed hour (a model input
// when the setup model kept that group, and its vol forecast scales fast-lane trails when the model was
// trained with VOL_ADAPT on) and the perps SNN's direction calls (journaled with every setup, see
// bot/setups/journal.ts, so their value can be measured as recordings grow).
// Guards: kill switch / halts flatten urgently; the perp daily loss stop flattens and halts for the
// day; an unvalidated lane trades at pilot size (or not at all with PERP_REQUIRE_VALIDATION).
//
// The direction curves (the heat lane, bot/heat) reach this trader only through the `heat` dependency, and only as far
// as its mode allows (HEAT_PERPS, with HEAT_LANE on):
//   log    the hour's, the 4 hours' and the day's direction for the coin are written to the journal beside every
//          signal and every open
//   gate   also: a 1h setup whose side is against a live hour direction does not enter (no direction: it passes;
//          15m and daily setups are never gated, and the day's direction gates nothing in this mode)
//   entry  also: a coin's decided 60-minute call is offered as a fast-lane setup of kind `heat` on 1h, and its decided
//          240-minute call as one on 4h (HEAT_PERP_HORIZONS). At most one heat offer per coin per clock hour across
//          both (both in the same minute: the hotter weight, a tie to 4h), never while the coin has an open trade, and
//          (HEAT_PERPS_DAILY=context) never against the coin's live daily call. A heat setup is scored by the heat
//          weight, is dropped at the re-check unless its own horizon's direction (the hour, or the 4 hours) still
//          points the same way and the day does not point against it, ends at the next close of its timeframe, and is
//          carried through that close (not closed and opened again) while its horizon's direction still has its side.
//          The daily call is never an entry of its own: no daily curve row is above the no-signal twin's best.
// Sizing, caps, the liquidation rule, the exchange stop and flatten are the same for a heat trade as for any other.

import { drawdownScale, optimalF, recencyWeight, type OptimalFReport, type WeightedTrade } from '../strategy/optimalF';
import type { OptimalFConfig } from '../config';
import { marketContext } from '../ta/marketContext';
import fs from 'fs';
import type { BreakEven } from '../risk/equityGuard';
import type { StreakScaler } from '../risk/streakScaler';
import type { AuditLog } from '../audit/auditLog';
import type { CandleSet } from '../ta/candleStore';
import type { Candle } from '../ta/indicators';
import type { Timeframe } from '../ta/knowledge';
import type { DirTarget, DirectionalContext, DirectionalGuards, PerpPacer } from '../perps/hedger';
import type { PerpHub } from '../perps/perpData';
import type { PerpGateway } from '../perps/perpRest';
import { adaptToVol, applyRatchet, applyScaleOut, atr4hAt, detectLast, heatSignal, FAST_TFS, SLOW_TFS, SETUP_MIN_BARS, TF_MS, type Lane, type SetupSignal } from './detectors';
import { applyPerpCut, DEFAULT_COSTS, exitTrade, openTrade, stepTrade, tradeResult, type CostModel, type OpenTrade } from './exits';
import { quotaCall, type PacerFloorMode } from '../risk/quotaPacer';
import { activeCrossLead, crossLeadSetupReading, crossLeadSum, type CrossLeadReading } from '../ta/crossLead';
import type { LibrarianReading } from '../ta/librarian';
import type { XgReading } from '../ta/crossGraph';
import { setupFeatureMap, setupVector, type SetupBars, type TaNetReading } from './features';
import type { SnnContext } from '../model/featureEngine';
import { playbook } from '../strategy/playbook';
import { compensator } from '../strategy/compensator';
import { DEFAULT_LANES, kindKey, LaneBook, type Candidate, type LaneBookParams } from './lanes';
import { SetupModel } from './setupModel';
import { maintenanceRate, maxSafeNotional, reservedFor, safeShare } from '../risk/liquidation';
import { macro } from '../macro/macroService';
import { gatePasses, probation } from '../risk/probation';
import type { PerpRiskPosition } from '../perps/perpRest';
import { heatWeight } from '../heat/heatLane';
import type { HeatContext, HeatDecided, HeatDirection } from '../heat/types';
import { logger } from '../util/log';

const log = logger('setups');

export interface SetupTraderParams {
  book: LaneBookParams;
  costs: CostModel;
  dailyLossFrac: number;
  minEquityUsd: number;
  pilotMaxNotionalUsd: number;
  requireValidation: boolean;
  dailyGoalUsd: number;
  /** Liquidation beyond the stop (bot/risk/liquidation.ts): buffer, and the maintenance margin rate (0 / unset =
   *  half the initial margin implied by the exchange's leverage estimate). */
  liqBuffer?: number;
  maintMargin?: number;
  /** PERP_LOSER_CUT_C as dollars a contract (Steven, Nov 12: 15c): a trade's stop is the nearer of its own and this far against
   *  the entry on the perp's price (bot/setups/exits.ts applyPerpCut). 0 / unset: off. */
  loserCut?: number;
}

/** How far the direction curves act on the perps (HEAT_PERPS; 'off' whenever HEAT_LANE is off). */
export type HeatPerpsMode = 'off' | 'log' | 'gate' | 'entry';

/** The direction curves as the setup trader is handed them. */
export interface SetupHeatDeps {
  /** The heat lane's view of the curves: the hour's, the 4 hours' and the day's direction per coin and the call that just fired. */
  dir: HeatDirection;
  mode: HeatPerpsMode;
  /** HEAT_PERP_HORIZONS: the horizons whose calls open a heat setup in entry mode, 60 (on 1h) and 240 (on 4h). Default both. */
  horizons?: number[];
  /** HEAT_PERPS_DAILY: 'context' (default) keeps a heat entry against the coin's live daily call out; 'off' ignores the day. */
  daily?: 'context' | 'off';
  /** HEAT_TOP_N: the batch the heat weight is measured over (0 = every row the pack lists). Default 10. */
  topN?: number;
  /** The smallest heat weight (0..1) a heat setup needs to queue and to enter. Default 0: every decided call. */
  minWeight?: number;
  /** The perp stop rule for a heat setup: stopAtrMult x the 1h ATR from the entry, at least minStopBps
   *  (PERP_STOP_ATR_MULT, PERP_MIN_STOP_BPS). Defaults 2 and 50. */
  stopAtrMult?: number;
  minStopBps?: number;
}

export interface SetupTraderDeps {
  params: SetupTraderParams;
  hub: PerpHub;
  gateway: PerpGateway;
  /** Model file; a function so a model the pipeline promotes later is picked up (hot reload on change). */
  modelPath: string | (() => string);
  statePath: string;
  candles: (asset: string) => CandleSet | undefined;
  /** Current spot price of an asset (the level the setups were drawn on). */
  spot: (asset: string, now: number) => number | undefined;
  audit?: AuditLog;
  /** TA network forecast for an asset at its last closed hour (the walking network, ungated). */
  taNet?: (asset: string, now: number) => TaNetReading | undefined;
  /** The Librarian's reading for an asset at its last closed hour (ungated: the model's "librarian" group decides). */
  librarian?: (asset: string, now: number) => Pick<LibrarianReading, 'w' | 'net' | 'vsBook' | 'transition'> | undefined;
  /** The cross-asset graph network's forecast for an asset at its last closed hour (ungated: the "xgraph" group decides). */
  crossGraph?: (asset: string, now: number) => Pick<XgReading, 'rel4' | 'rel24' | 'rank'> | undefined;
  /** Perps SNN's calls for an asset. */
  snn?: (asset: string) => SnnContext | undefined;
  /** Journal of every setup with these readings and its outcome (bot/setups/journal.ts). */
  journal?: { signal(rec: Record<string, unknown>): void; trade(rec: Record<string, unknown>): void };
  /** SNN gate file written by the pipeline (research/setupSnnStudy.ts) once the journal proves the SNN
   *  helps: enter only when the SNN's call agrees with the trade by at least minAgree. */
  snnGatePath?: () => string;
  /** Kill-switch override (bot/control.ts): the perp daily loss halt is advisory (shown), not a halt. */
  trainingOverride?: () => boolean;
  /** Results vs expectation (diagnostic), fed with each closed trade's R multiple. */
  streak?: StreakScaler;
  /** Break-even reference of the margin account: new entries' risk budget shrinks with net losses and
   *  returns to full once wins recoup them (the same rule as the Kalshi pool). */
  breakEven?: BreakEven;
  /** Net loss (fraction of break-even) at which the size reaches its floor. */
  lossAt?: number;
  /** TA conviction for a trade direction on an asset (bot/strategy/taConviction.ts): size multiplier
   *  (TA / confluence breadth, altcoin risk-on rule), selection priority, and why. */
  conviction?: (asset: string, dir: number, now: number) => { mult: number; priority: number; why: string } | undefined;
  /** Optimal f cap per lane (bot/strategy/optimalF.ts) from the model's out-of-sample trades and this
   *  trader's own closed trades; `paper` floors the cap at paperFloor x the lane's risk. */
  optimalF?: OptimalFConfig & { paper: boolean };
  /** The direction curves (bot/heat), wired beside the SNN: journal, gate and hourly entries by `mode`. Unset = off. */
  heat?: SetupHeatDeps;
}

const HOUR_MS = 3_600_000;
/** The perps heat setups: the curve horizon (minutes) each timeframe trades, and the setup type keys (lanes.ts kindKey). */
type HeatTf = '1h' | '4h';
const HEAT_H: Record<HeatTf, number> = { '1h': 60, '4h': 240 };
const HEAT_TF: Record<number, HeatTf | undefined> = { 60: '1h', 240: '4h' };
const HEAT_KINDS = [kindKey({ tf: '1h', kind: 'heat' }), kindKey({ tf: '4h', kind: 'heat' })];
/** Which saved mark says a coin's call at a horizon was ruled on (the hourly one keeps the name it had before 4h existed). */
const heatCallMark = (asset: string, h: number): string => (h === 60 ? `heatcall|${asset}` : `heatcall${h}|${asset}`);
/** A heat trade's close (hourly or 4-hour) is ruled on this long after the close at the earliest, so the reading taken at
 *  the close itself (the reader publishes it some seconds later) is part of the decision to carry the trade or end it. */
const HEAT_CLOSE_WAIT_MS = 90_000;
/** DOGE is not traded on the curves anywhere in this project. */
const isDoge = (asset: string): boolean => asset.trim().toUpperCase().startsWith('DOGE');
const sideName = (dir: number): string => (dir > 0 ? 'up' : 'down');
/** A direction the provider handed back, if it is one: a side of +1 or -1, still live now. */
const live = (c: HeatContext | undefined, now: number): HeatContext | undefined => (c && (c.dir === 1 || c.dir === -1) && c.until > now ? c : undefined);

/** Typical spread of a setup trade's result in R (stop = -1 R, targets at +1..3 R): standardises R for the streak scaler. */
const R_SD = 1.2;

interface SnnGateFile { enabled: boolean; minAgree?: { fast: number; slow: number }; reason?: string; trades?: number; needed?: number }

interface SavedBook { positions: OpenTrade[]; queues: Record<Lane, Candidate[]>; seen: Record<string, number>; day?: { key: string; start: number; realized: number }; history: ClosedRecord[] }
export interface ClosedRecord { asset: string; lane: Lane; kind: string; tf: string; dir: number; entry: number; exit: number; entryTs: number; exitTs: number; reason: string; r: number; ret: number; usd: number; score?: number }

const TFS: Timeframe[] = [...FAST_TFS, ...SLOW_TFS];

export class SetupTrader {
  readonly book: LaneBook;
  private model?: SetupModel;
  private modelMtime = 0;
  modelError?: string;
  private seen = new Map<string, number>();
  private lastPx = new Map<string, number>();
  private equity?: { value: number; ts: number };
  private day?: { key: string; start: number; realized: number };
  private dayHalt?: string;
  private history: ClosedRecord[] = [];
  readonly lastDecisions = new Map<string, { target: number; reason: string; stop?: number }>();
  lastError?: string;
  private gate?: { file: string; mtime: number; g?: SnnGateFile };
  private capsKey = '';
  /** The quota pacer for the running targets() call (the engine's, bot/risk/quotaPacer.ts). */
  private pacer?: PerpPacer;
  private readonly ddCut: Partial<Record<Lane, boolean>> = {};
  readonly capReports: Partial<Record<Lane, OptimalFReport & { liveTrades: number; liveDdR: number }>> = {};
  /** The curve provider's last exception and how many there were (status); the first one is also logged. */
  private heatError?: string;
  private heatThrows = 0;

  constructor(private readonly d: SetupTraderDeps) {
    this.book = new LaneBook(d.params.book);
    this.reloadModel();
    this.restore();
  }

  /** Load (or hot-reload when the file changed) the setup model; lane settings come from it, risk limits from config. */
  reloadModel(): void {
    try {
      const file = typeof this.d.modelPath === 'function' ? this.d.modelPath() : this.d.modelPath;
      if (!fs.existsSync(file)) { this.model = undefined; this.modelError = `no setup model at ${file} (research:setups)`; return; }
      const m = fs.statSync(file).mtimeMs + file.length;
      if (m === this.modelMtime) return;
      this.model = SetupModel.load(file);
      // A new model (not the one loaded at startup) starts a fresh probation for the setups book.
      if (this.modelMtime !== 0 && probation()?.status().setups.benched) { probation()!.reset('setups'); this.d.audit?.write('probation', { event: 'reset', book: 'setups', reason: `new setup model ${this.model?.params.version}` }); }
      this.modelMtime = m;
      this.modelError = undefined;
      const P = this.d.params.book, M = this.model?.params.book;
      if (M) for (const lane of ['fast', 'slow'] as const) this.book.params[lane] = { ...P[lane], minScore: M[lane].minScore, refScore: M[lane].refScore, ttlBars: M[lane].ttlBars, maxChaseR: M[lane].maxChaseR, minScoreByKind: M[lane].minScoreByKind };
      this.d.audit?.write('setup_model', { version: this.model?.params.version, fast: this.model?.validated('fast'), slow: this.model?.validated('slow') });
    } catch (e) {
      this.model = undefined;
      this.modelError = String(e);
    }
  }

  private restore(): void {
    try {
      if (!fs.existsSync(this.d.statePath)) return;
      const s = JSON.parse(fs.readFileSync(this.d.statePath, 'utf8')) as SavedBook;
      for (const t of s.positions ?? []) this.book.add(t);
      this.book.queues.fast = s.queues?.fast ?? [];
      this.book.queues.slow = s.queues?.slow ?? [];
      this.seen = new Map(Object.entries(s.seen ?? {}));
      this.day = s.day;
      this.history = s.history ?? [];
    } catch (e) { this.lastError = `restore: ${String(e)}`; }
  }

  private save(): void {
    try {
      const s: SavedBook = { positions: [...this.book.positions.values()], queues: this.book.queues, seen: Object.fromEntries(this.seen), day: this.day, history: this.history.slice(-500) };
      const tmp = `${this.d.statePath}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify(s));
      fs.renameSync(tmp, this.d.statePath);
    } catch (e) { this.lastError = `save: ${String(e)}`; }
  }

  /** The exchange's liquidation estimates per ticker (refreshed at most once a minute). */
  private risk?: { ts: number; byTicker: Map<string, PerpRiskPosition> };
  private async refreshRisk(now: number): Promise<Map<string, PerpRiskPosition> | undefined> {
    if (this.risk && now - this.risk.ts < 60_000) return this.risk.byTicker;
    if (!this.d.gateway.getRisk) return undefined;
    try {
      const r = await this.d.gateway.getRisk();
      this.risk = { ts: now, byTicker: new Map(r.map((p) => [p.ticker, p])) };
      return this.risk.byTicker;
    } catch (e) {
      this.lastError = `risk: ${String(e)}`;
      return this.risk?.byTicker;
    }
  }

  private mmrOf(asset: string): number { return maintenanceRate(this.d.hub.get(asset)?.latest?.leverage, this.d.params.maintMargin); }

  private async refreshEquity(now: number): Promise<number | undefined> {
    if (this.equity && now - this.equity.ts < 30_000) return this.equity.value;
    if (!this.d.gateway.getBalance) return undefined;
    try {
      const b = await this.d.gateway.getBalance();
      this.equity = { value: b.equity, ts: now };
      const key = new Date(now).toISOString().slice(0, 10);
      if (this.day?.key !== key) { this.day = { key, start: b.equity, realized: 0 }; this.dayHalt = undefined; }
      if (this.day.start > 0 && b.equity <= this.day.start * (1 - this.d.params.dailyLossFrac)) {
        this.dayHalt ??= `perp daily loss: equity $${b.equity.toFixed(2)} is ${((1 - b.equity / this.day.start) * 100).toFixed(1)}% below today's start`;
      }
      return b.equity;
    } catch (e) {
      this.lastError = `balance: ${String(e)}`;
      return this.equity?.value;
    }
  }

  private bars(asset: string): SetupBars | undefined {
    const c = this.d.candles(asset);
    if (!c?.bars['1h']) return undefined;
    return { m15: c.bars['15m'], h1: c.bars['1h'], d1: c.bars['1d'] };
  }

  private conviction(asset: string, dir: number, now: number): { mult: number; priority: number; why: string } | undefined {
    try { return this.d.conviction?.(asset, dir, now); } catch { return undefined; }
  }

  private reading(asset: string, now: number): TaNetReading | undefined {
    try { return this.d.taNet?.(asset, now); } catch { return undefined; }
  }

  private libReading(asset: string, now: number): Pick<LibrarianReading, 'w' | 'net' | 'vsBook' | 'transition'> | undefined {
    try { return this.model?.uses('librarian') ? this.d.librarian?.(asset, now) : undefined; } catch { return undefined; }
  }

  private xgReading(asset: string, now: number): Pick<XgReading, 'rel4' | 'rel24' | 'rank'> | undefined {
    try { return this.model?.uses('xgraph') ? this.d.crossGraph?.(asset, now) : undefined; } catch { return undefined; }
  }

  /** Cross-coin lead-lag for an asset now (the study's final fit, 15-minute bars of every coin): for the model's
   *  "crosslead" inputs, or (`forExit`) for the lead-lag exit the model was trained with. */
  private clReading(asset: string, now: number, forExit = false): CrossLeadReading | undefined {
    if (!(forExit ? this.model?.params.crossLeadExit : this.model?.uses('crosslead'))) return undefined;
    try { return crossLeadSetupReading(activeCrossLead(now), asset, now, (a) => this.d.candles(a)?.bars['15m'], true); } catch { return undefined; }
  }

  /** Model score of a setup as of `t` (fresh features), NaN without a model. */
  private score(sig: SetupSignal, t: number): number {
    if (!this.model) return NaN;
    const bars = this.bars(sig.asset);
    if (!bars) return NaN;
    return this.model.score(sig.lane, setupVector(setupFeatureMap(sig, bars, this.bars('BTC'), t, this.reading(sig.asset, t), marketContext()?.character(sig.asset), macro()?.inputs(), this.libReading(sig.asset, t), this.xgReading(sig.asset, t), this.clReading(sig.asset, t))));
  }

  /** The SNN gate (hot reload on change; off when missing). */
  private snnGate(): SnnGateFile | undefined {
    const file = this.d.snnGatePath?.();
    if (!file) return undefined;
    try {
      const m = fs.existsSync(file) ? fs.statSync(file).mtimeMs : 0;
      if (this.gate?.file !== file || this.gate.mtime !== m) this.gate = { file, mtime: m, g: m ? JSON.parse(fs.readFileSync(file, 'utf8')) as SnnGateFile : undefined };
    } catch { this.gate = { file, mtime: -1 }; }
    return this.gate.g;
  }

  /** Whether the SNN gate blocks this entry (only when the gate is on and the SNN has a call). */
  private snnBlocks(sig: SetupSignal): boolean {
    const g = this.snnGate();
    if (!g?.enabled || !g.minAgree) return false;
    const s = this.snnOf(sig.asset);
    const p = sig.lane === 'slow' ? s.snn_up4 ?? s.snn_up1 : s.snn_up1 ?? s.snn_up4;
    return p !== null && p !== undefined && sig.dir * (p - 0.5) < g.minAgree[sig.lane];
  }

  /** The perps SNN's calls in the journal's flat form. */
  private snnOf(asset: string): Record<string, number | null> {
    let c: SnnContext | undefined;
    try { c = this.d.snn?.(asset); } catch { c = undefined; }
    const v = (x: number | undefined) => (x !== undefined && Number.isFinite(x) ? +x.toFixed(4) : null);
    return { snn_up1: v(c?.up?.[60]), snn_up4: v(c?.up?.[240]), snn_skill1: v(c?.conf?.[60]?.skill), snn_skill4: v(c?.conf?.[240]?.skill) };
  }

  /** What the curves may do here: 'off' without the dependency or with a mode this code does not know. */
  private heatMode(): HeatPerpsMode {
    const m = this.d.heat?.mode;
    return m === 'log' || m === 'gate' || m === 'entry' ? m : 'off';
  }

  /** One call into the curve provider. It is meant never to throw, but an exception inside targets() would skip the
   *  whole perp executor tick (hedge orders and stop upkeep included), so every call goes through here: a throw is
   *  logged once, counted for the status, and read as "no call". */
  private heatAsk<T>(what: string, f: (h: HeatDirection) => T | undefined): T | undefined {
    const h = this.d.heat?.dir;
    if (!h) return undefined;
    try { return f(h) ?? undefined; } catch (e) {
      this.heatError = `${what}: ${String(e)}`;
      if (this.heatThrows++ === 0) log.warn(`heat provider threw in ${what} (read as no call; later throws are only counted): ${String(e)}`);
      return undefined;
    }
  }

  /** The hour's direction for a coin: its latest decided 60-minute call still inside its hour (never for DOGE). */
  private heatHour(asset: string, now: number): HeatContext | undefined {
    if (this.heatMode() === 'off' || isDoge(asset)) return undefined;
    return this.heatAsk('hour', (h) => live(h.hour(asset, now), now));
  }

  /** The 4 hours' direction for a coin: its latest decided 240-minute call until its bar close plus 4 hours (never DOGE). */
  private heatFour(asset: string, now: number): HeatContext | undefined {
    if (this.heatMode() === 'off' || isDoge(asset)) return undefined;
    return this.heatAsk('four', (h) => live(h.four(asset, now), now));
  }

  /** The day's direction for a coin: its latest decided 1440-minute call until its bar close plus a day (never DOGE, and
   *  nothing with HEAT_PERPS_DAILY=off). */
  private heatDay(asset: string, now: number): HeatContext | undefined {
    if (this.heatMode() === 'off' || this.d.heat?.daily === 'off' || isDoge(asset)) return undefined;
    return this.heatAsk('day', (h) => live(h.day(asset, now), now));
  }

  /** The direction a heat setup on `tf` stands on: the hour's for 1h, the 4 hours' for 4h. */
  private heatCtx(asset: string, tf: string, now: number): HeatContext | undefined {
    return tf === '4h' ? this.heatFour(asset, now) : this.heatHour(asset, now);
  }

  /** The coin's live daily call when it points against `dir` (HEAT_PERPS_DAILY=context), else undefined. No daily call: no effect. */
  private heatDayAgainst(asset: string, dir: number, now: number): HeatContext | undefined {
    const d = this.heatDay(asset, now);
    return d && d.dir !== dir ? d : undefined;
  }

  /** The horizons that open a heat setup (HEAT_PERP_HORIZONS): 60 and 240 only, both when the dependency names none. */
  private heatHorizons(): number[] {
    const hs = this.d.heat?.horizons ?? [60, 240];
    return [60, 240].filter((h) => hs.includes(h));
  }

  /** The coin's decided call at horizon `h` (60 or 240) that just fired (inside the lane's entry lag), never for DOGE. */
  private heatFired(asset: string, h: number, now: number): HeatDecided | undefined {
    if (this.heatMode() !== 'entry' || isDoge(asset)) return undefined;
    return this.heatAsk('fired', (p) => {
      const d = p.fired(asset, h, now);
      const r = d?.row;
      return d && r && r.h === h && (r.dir === 1 || r.dir === -1) && Number.isFinite(r.barClose) && Number.isFinite(r.rank) && Number.isFinite(r.of) ? d : undefined;
    });
  }

  /** Heat weight of a call by its rank (the lane's own formula, E07), measured over HEAT_TOP_N. */
  private heatWeightOf(rank: number, of: number): number {
    return heatWeight(rank, of, this.d.heat?.topN ?? 10);
  }

  /** The curves in the journal's flat form, for a setup or trade of side `dir`: the hour's direction, whether it is
   *  with the trade (1) or against it (-1), which row called it and how hot it is; the same, shorter, for the 4 hours'
   *  and the day's direction (null: none live, or HEAT_PERPS_DAILY=off for the day). Empty when HEAT_PERPS is off. */
  private heatOf(asset: string, now: number, dir: number): Record<string, number | string | null> {
    const mode = this.heatMode();
    if (mode === 'off') return {};
    const c = this.heatHour(asset, now), four = this.heatFour(asset, now), day = this.heatDay(asset, now);
    return {
      heat_mode: mode, heat_dir: c?.dir ?? null, heat_agree: c ? Math.sign(c.dir * dir) : null, heat_key: c?.key ?? null, heat_rank: c?.rank ?? null, heat_of: c?.of ?? null,
      heat_w: c ? +this.heatWeightOf(c.rank, c.of).toFixed(4) : null, heat_bar_close: c?.barClose ?? null, heat_until: c?.until ?? null,
      heat_four_dir: four?.dir ?? null, heat_four_agree: four ? Math.sign(four.dir * dir) : null, heat_four_key: four?.key ?? null,
      heat_day_dir: day?.dir ?? null, heat_day_agree: day ? Math.sign(day.dir * dir) : null, heat_day_key: day?.key ?? null,
    };
  }

  /** The curves' say when a candidate is re-checked. `drop`: why it does not enter. `weight`: a heat setup's fresh
   *  score. Gate (modes gate and entry): a 1h setup against a live hour direction does not enter; no direction passes;
   *  15m and daily setups are not gated, and the day gates no chart setup. A heat setup needs more: its own horizon's
   *  direction (the hour for 1h, the 4 hours for 4h) must still point its way, because its call is the only reason for
   *  the trade (a candidate can wait in the queue while the calls move on), and a live daily call must not point
   *  against it (HEAT_PERPS_DAILY=context). */
  private heatRecheck(sig: SetupSignal, now: number): { drop?: string; weight?: number } {
    const mode = this.heatMode();
    if (sig.kind === 'heat') {
      if (mode !== 'entry') return { drop: 'heat entries are off (HEAT_PERPS)' };
      if (!this.heatHorizons().includes(HEAT_H[sig.tf as HeatTf])) return { drop: `heat: ${sig.tf} heat entries are off (HEAT_PERP_HORIZONS)` };
      // A candidate that waited (lane full, entries paused) past the clock hour it was offered in would make a second
      // heat entry for the coin in the new hour, next to the new hour's own offer: one per coin per clock hour.
      if ((this.seen.get(`heat|${sig.asset}`) ?? 0) < Math.floor(now / HOUR_MS) * HOUR_MS) return { drop: "heat: the clock hour it was offered in has passed" };
      const four = sig.tf === '4h';
      const c = this.heatCtx(sig.asset, sig.tf, now);
      if (!c) return { drop: `heat: no live ${four ? '4-hour' : 'hour'} direction left for this call` };
      if (c.dir !== sig.dir) return { drop: `heat: ${four ? 'the 4-hour direction' : "the hour's direction"} turned ${sideName(c.dir)} (${c.key})` };
      const day = this.heatDayAgainst(sig.asset, sig.dir, now);
      if (day) return { drop: `heat: against the day's direction (${day.key})` };
      return { weight: this.heatWeightOf(c.rank, c.of) };
    }
    if ((mode !== 'gate' && mode !== 'entry') || sig.tf !== '1h') return {};
    const c = this.heatHour(sig.asset, now);
    return c && c.dir !== sig.dir ? { drop: `heat gate: the hour's direction is ${sideName(c.dir)} (${c.key}, rank ${c.rank}/${c.of}), against this ${sig.dir > 0 ? 'long' : 'short'}` } : {};
  }

  /** Rule on the coin's 60-minute and 240-minute calls that just fired (HEAT_PERPS=entry, HEAT_PERP_HORIZONS), each once:
   *  offer it as a heat setup on 1h or 4h, or journal why not. The calls come from 1-minute readings and can fire many
   *  times an hour, so a coin gets at most one heat offer per clock hour across both horizons. When both fire in the same
   *  minute the hotter weight is offered first, a tie to the 4-hour call; the other is ruled on too, with the reason.
   *  Returns whether the saved book changed. */
  private heatOffer(asset: string, now: number): boolean {
    const fresh: Array<{ call: HeatDecided; tf: HeatTf; weight: number }> = [];
    for (const h of this.heatHorizons()) {
      const call = this.heatFired(asset, h, now), tf = HEAT_TF[h];
      if (!call || !tf) continue;
      const mark = heatCallMark(asset, h);
      if ((this.seen.get(mark) ?? 0) >= call.row.barClose) continue; // ruled on already (the executor ticks every few seconds)
      this.seen.set(mark, call.row.barClose);
      fresh.push({ call, tf, weight: this.heatWeightOf(call.row.rank, call.row.of) });
    }
    if (!fresh.length) return false;
    // Hotter first; weights within a hair of each other are a tie, and a tie goes to 4h.
    const w = (x: { weight: number }) => (Number.isFinite(x.weight) ? x.weight : -1);
    fresh.sort((a, b) => (Math.abs(w(b) - w(a)) > 1e-9 ? w(b) - w(a) : HEAT_H[b.tf] - HEAT_H[a.tf]));
    let offered: HeatTf | undefined;
    for (const f of fresh) if (this.heatOfferOne(asset, f.call, f.tf, f.weight, now, offered)) offered = f.tf;
    return true;
  }

  /** One fired call: offer it as a heat setup on `tf`, or journal why not. A coin gets none while it has an open trade (a
   *  candidate waiting for the coin to free up would re-open the moment the trade closes), none once its clock hour is
   *  used (`offered`: the other horizon's call of this minute just took it), and none against its live daily call.
   *  Returns whether the offer queued. */
  private heatOfferOne(asset: string, call: HeatDecided, tf: HeatTf, weight: number, now: number, offered: HeatTf | undefined): boolean {
    const row = call.row, hourKey = `heat|${asset}`;
    const H = this.d.heat!;
    const hour = Math.floor(now / HOUR_MS) * HOUR_MS;
    const open = this.book.positions.get(asset);
    let sig: SetupSignal | undefined, why: string | undefined;
    const day = open ? undefined : this.heatDayAgainst(asset, row.dir, now);
    if (open) why = `the coin has an open ${open.tf} ${open.kind} trade`;
    else if (offered) why = `the ${offered} heat call of this minute was offered (the hotter weight, a tie to 4h): one heat entry per coin per clock hour`;
    else if ((this.seen.get(hourKey) ?? 0) >= hour) why = 'a heat entry was already offered for this coin this clock hour';
    else if (day) why = `against the day's direction (${day.key})`;
    else {
      // The 4h bars come from the candle store (bot/ta/candleStore.ts builds them from complete groups of four 1h bars
      // aligned to 00/04/08/12/16/20 UTC): the 4h ATR sets the stop and the 4-hour close ends the trade, as the 1h bars do
      // for the hourly setup.
      const px = this.d.spot(asset, now), cs = this.d.candles(asset)?.bars[tf];
      sig = px !== undefined && cs ? heatSignal(asset, row, weight, px, atrOf(cs), { atrMult: H.stopAtrMult ?? 2, minBps: H.minStopBps ?? 50 }, tf) : undefined;
      if (!sig) why = px !== undefined && px > 0 ? `no ${tf} ATR to set the stop` : 'no spot price';
    }
    const queued = sig !== undefined && Number.isFinite(weight) && this.book.offer(sig, weight, now);
    // The clock hour is used up only by an offer that queued: a call too cool to queue leaves room for a hotter one.
    if (queued) this.seen.set(hourKey, hour);
    else if (sig) why = `heat weight ${weight.toFixed(3)} is under the minimum ${H.minWeight ?? 0}`;
    if (sig) this.d.audit?.write('setup_signal', { asset, lane: 'fast', kind: 'heat', tf, dir: row.dir, ref: sig.ref, stop: sig.stop, score: weight, queued, heat: sig.heat });
    this.d.journal?.signal({
      ts: now, at: row.barClose, asset, lane: 'fast', kind: 'heat', tf, dir: row.dir, ref: sig?.ref ?? null, stop: sig?.stop ?? null, trailAtr: null,
      score: Number.isFinite(weight) ? +weight.toFixed(4) : null, queued, why: why ?? null, call_h: row.h, call_key: row.key, call_rank: row.rank, call_of: row.of, call_fired: call.fired, call_against: call.against,
      ...this.heatOf(asset, now, row.dir), ...this.snnOf(asset), model: null,
    });
    return queued;
  }

  /** A heat trade is due to end at the close `close` of its timeframe (hourly, or 4-hour). It is carried through that
   *  close instead (one more bar) when its horizon's direction still has its side: the latest decided call at that
   *  horizon (60 minutes for 1h, 240 for 4h) is live, points the trade's way and reaches at least half a bar past the
   *  close, so it covers most of the bar that starts. That is the next bar's call on the same side; closing and opening
   *  again would pay a round trip for the position already held. A carry stands for a new entry, so it is not made while
   *  the coin's live daily call points against the trade, nor once the trade's horizon is no longer in
   *  HEAT_PERP_HORIZONS. The carried bar counts as that clock hour's heat entry for the coin. */
  private heatExtend(t: OpenTrade, close: number, now: number): void {
    if (this.heatMode() !== 'entry' || !this.heatHorizons().includes(HEAT_H[t.tf as HeatTf])) return;
    const c = this.heatCtx(t.asset, t.tf, now);
    if (!c || c.dir !== t.dir || c.until < close + TF_MS[t.tf]! / 2) return;
    if (this.heatDayAgainst(t.asset, t.dir, now)) return;
    t.plan.maxBars = t.bars + 2;
    t.heat = { key: c.key, rank: c.rank, of: c.of, heat: c.heat, barClose: c.barClose, weight: this.heatWeightOf(c.rank, c.of), extended: (t.heat?.extended ?? 0) + 1 };
    this.seen.set(`heat|${t.asset}`, Math.floor(now / HOUR_MS) * HOUR_MS);
    this.d.audit?.write('setup_trade', { event: 'extended', asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entry: t.entry, stop: t.stop, close, heat: t.heat });
    this.d.journal?.trade({ ts: now, event: 'extended', asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entryTs: t.entryTs, entry: t.entry, close, extended: t.heat.extended, ...this.heatOf(t.asset, now, t.dir) });
  }

  private record(t: OpenTrade, now: number): void {
    const res = tradeResult(t);
    if (Number.isFinite(res.r)) this.d.streak?.observe(res.r / R_SD, res.r > 0, now);
    const tradeUsd = res.ret * (t.notional ?? 0);
    if (tradeUsd !== 0 && this.equity) {
      const raised = this.d.breakEven?.onTradeResult(tradeUsd > 0, this.equity.value + tradeUsd);
      if (raised) this.d.audit?.write('training', { event: 'break_even_raised', book: 'perps', ...raised });
    }
    const usd = res.ret * (t.notional ?? 0);
    if (this.day) this.day.realized += usd;
    probation()?.record('setups', usd, now);
    // The quota pacer counts every closed trade's result, net of its costs, toward the bot's hourly target.
    this.pacer?.credit(usd, this.d.hub.get(t.asset)?.latest?.ticker ?? t.asset);
    this.pacer?.floors?.forget(`${t.asset}|${t.entryTs}`);
    this.history.push({ asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entry: t.entry, exit: t.closed?.px ?? NaN, entryTs: t.entryTs, exitTs: t.closed?.ts ?? now, reason: t.closed?.reason ?? 'manual', r: res.r, ret: res.ret, usd, score: t.score });
    this.d.audit?.write('setup_trade', { event: 'closed', asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entry: t.entry, exit: t.closed?.px, reason: t.closed?.reason, r: res.r, usd, ...(t.heat ? { extended: t.heat.extended } : {}) });
    this.d.journal?.trade({ ts: now, event: 'closed', asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entryTs: t.entryTs, entry: t.entry, exit: t.closed?.px ?? null, reason: t.closed?.reason ?? 'manual', r: res.r, ret: res.ret, usd, score: t.score ?? null, ...(t.heat ? { extended: t.heat.extended } : {}) });
  }

  /** Directional targets for the executor (called after it synced positions). */
  async targets(c: DirectionalContext, guards: DirectionalGuards): Promise<DirTarget[]> {
    const now = c.now;
    this.pacer = guards.pacer;
    this.reloadModel();
    const equity = await this.refreshEquity(now);
    const assets = [...this.d.hub.byAsset.entries()].filter(([, s]) => s.latest?.ticker).map(([a]) => a);
    let changed = false;
    const exitNow = new Set<string>();

    // 1. Manage open trades on the spot price (a pseudo-bar from the last price to now), trail / time at candle closes.
    for (const [asset, t] of [...this.book.positions]) {
      const px = this.d.spot(asset, now);
      if (!(px && px > 0)) continue;
      const prev = this.lastPx.get(asset) ?? px;
      this.lastPx.set(asset, px);
      const cs = this.d.candles(asset)?.bars[t.tf];
      const lastBar = cs?.[cs.length - 1];
      const key = `trail|${asset}|${t.tf}`;
      let tfClose: { close: number; atr: number } | undefined;
      // A heat trade's close (hourly, or 4-hour) waits a moment (HEAT_CLOSE_WAIT_MS), so the reading taken at the close is in.
      const heatWait = t.kind === 'heat' && this.heatMode() === 'entry' && lastBar !== undefined && now < lastBar.ts + TF_MS[t.tf]! + HEAT_CLOSE_WAIT_MS;
      if (lastBar && !heatWait && lastBar.ts > t.entryTs - TF_MS[t.tf]! && (this.seen.get(key) ?? 0) < lastBar.ts) {
        this.seen.set(key, lastBar.ts);
        const atr = atrOf(cs!);
        if (atr > 0) tfClose = { close: lastBar.c, atr };
      }
      // A heat trade that would end at this close is carried through it while its horizon's direction still points its way.
      if (tfClose && lastBar && t.kind === 'heat' && t.bars + 1 >= t.plan.maxBars) this.heatExtend(t, lastBar.ts + TF_MS[t.tf]!, now);
      // The perp loser cut on a trade opened before it (a restart into a new release): set once, when nearer than its stop.
      if (t.cutStop === undefined && (this.d.params.loserCut ?? 0) > 0) {
        const q = this.d.hub.get(asset)?.latest;
        const perpMid = q?.bid !== undefined && q.ask !== undefined ? (q.bid + q.ask) / 2 : undefined;
        if (applyPerpCut(t, this.d.params.loserCut!, perpMid !== undefined ? perpMid / px : undefined)) {
          changed = true;
          this.d.audit?.write('setup_trade', { event: 'cut_set', asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entry: t.entry, stop: t.stop, ownStop: t.initialStop, cut: this.d.params.loserCut });
        }
      }
      const bar: Candle = { ts: now, o: prev, h: Math.max(prev, px), l: Math.min(prev, px), c: px, v: 0 };
      const was = t.partialDone, wasFrac = t.frac;
      if (stepTrade(t, bar, 0, this.d.params.costs, tfClose)) { this.record(t, now); this.book.remove(asset); changed = true; if (t.closed?.reason !== 'target') exitNow.add(asset); continue; }
      else if (t.partialDone !== was || t.frac !== wasFrac || tfClose) changed = true;
      // The cross-coin lead-lag exit (only when the model was trained with it): at each 15-minute close, the leaders'
      // expected pull on this coin against the trade by more than k of its volatility closes it.
      const ex = this.model?.params.crossLeadExit;
      const m15 = ex ? this.d.candles(asset)?.bars['15m'] : undefined;
      const last15 = m15?.[m15.length - 1];
      // From the close of the bar the trade entered in (as in training, which enters at a bar's open).
      if (ex && last15 && last15.ts + TF_MS['15m']! > t.entryTs && (this.seen.get(`cl|${asset}`) ?? 0) < last15.ts) {
        this.seen.set(`cl|${asset}`, last15.ts);
        const e = crossLeadSum(this.clReading(asset, now, true));
        if (e !== undefined && t.dir * e < -ex.k) { exitTrade(t, px, now, 'leadlag', this.d.params.costs); this.record(t, now); this.book.remove(asset); changed = true; exitNow.add(asset); }
      }
      // The quota snipe (Steven's profit rules apply to every contract type, Oct 30; bot/risk/quotaPacer.ts): a trade whose
      // whole result after costs, closed at the price now, covers what the clock hour needs is closed at once, whatever its
      // plan says. Perps never settle: the rule for the last share of a contract's window does not apply. Under PACER_FLOOR
      // (Steven, Oct 31) a plan aiming higher keeps the trade, the need it covered its floor, and the trade is closed once its
      // result falls below that floor (setupHigher).
      const need = this.pacer?.neededUsd;
      if (need !== undefined && !t.closed && t.notional) {
        const net = (tradeResult(t, px).ret - t.frac * this.d.params.costs.takerExit) * t.notional;
        const mode = this.pacer?.floorMode ?? 'off';
        const key = `${asset}|${t.entryTs}`;
        const floor = mode === 'off' ? undefined : this.pacer?.floors?.floor(key, t.dir * t.frac);
        const higher = setupHigher(t, px, mode);
        const call = quotaCall(net, need, floor, higher);
        if (call.arm !== undefined) this.pacer?.floors?.arm(key, t.dir * t.frac, call.arm);
        if (call.sell) {
          exitTrade(t, px, now, 'quota', this.d.params.costs);
          const what = `the ${t.lane} ${t.tf} ${t.kind} ${t.dir > 0 ? 'long' : 'short'} at ${px}`;
          this.pacer!.snipe(this.d.hub.get(asset)?.latest?.ticker ?? asset, call.sell === 'floor' ? `quota snipe (floor): +$${net.toFixed(2)} net on ${what} fell below its $${floor!.toFixed(2)} floor` : `quota snipe: +$${net.toFixed(2)} net on ${what} covers the $${need.toFixed(2)} the hour needs`);
          this.record(t, now); this.book.remove(asset); changed = true; exitNow.add(asset);
        }
      }
    }

    // 2. New setups on newly closed candles.
    // On probation the setup types the model has not proven are queued and traded too, at the lane's own minimum score.
    for (const lane of ['fast', 'slow'] as const) this.book.params[lane].unlistedMinScore = this.model && gatePasses('setups', false) ? this.d.params.book[lane].minScore : undefined;
    for (const asset of assets) {
      const set = this.d.candles(asset);
      if (!set) continue;
      for (const tf of TFS) {
        const cs = set.bars[tf];
        if (!cs || cs.length < SETUP_MIN_BARS) continue;
        const last = cs[cs.length - 1];
        const key = `${asset}|${tf}`;
        if ((this.seen.get(key) ?? 0) >= last.ts) continue;
        this.seen.set(key, last.ts); changed = true;
        if (now - (last.ts + TF_MS[tf]!) > TF_MS[tf]!) continue; // stale candles (feed catching up)
        const raw = detectLast(asset, tf, cs, set.bars['1d'], { spotPb: this.model?.params.spotPullback?.includes(asset) ?? false });
        if (!raw) continue;
        const at = last.ts + TF_MS[tf]!;
        const tn = this.reading(asset, at);
        const ratchet = this.model?.params.ratchet;
        const costs = this.d.params.costs;
        const sig0 = applyRatchet(adaptToVol(raw, tn?.vol, this.model?.params.volTrailK ?? 0), atr4hAt(set.bars['1h'], at), costs.entry + costs.takerExit, ratchet ?? { lanes: 'off', stopAtr: 0, beAtr: 0, trailStartAtr: 0, trailAtr: 0 }, tn?.vol);
        // Scale-out exits exactly as the model was trained with them (off unless it was).
        const sc = this.model?.params.scaleOut;
        const sig = sc ? applyScaleOut(sig0, sc) : sig0;
        const score = this.score(sig, at);
        const queued = Number.isFinite(score) && this.book.offer(sig, score, now);
        this.d.audit?.write('setup_signal', { asset, lane: sig.lane, kind: sig.kind, tf, dir: sig.dir, ref: sig.ref, stop: sig.stop, score, queued });
        this.d.journal?.signal({ ts: now, at, asset, lane: sig.lane, kind: sig.kind, tf, dir: sig.dir, ref: sig.ref, stop: sig.stop, trailAtr: sig.plan.trailAtr, score: Number.isFinite(score) ? +score.toFixed(4) : null, queued, tn_up1: tn?.up1 ?? null, tn_up4: tn?.up4 ?? null, tn_vol: tn?.vol ?? null, ...this.snnOf(asset), ...this.heatOf(asset, now, sig.dir), model: this.model?.params.version ?? null });
      }
    }
    // 2b. The heat setups (HEAT_PERPS=entry): a coin's decided 60-minute call on 1h and 240-minute call on 4h, offered to
    // the fast lane. Their minimum is their own in every validation mode: the model's per-type list does not know them, so
    // without this they would trade at any weight while unlisted types are on probation and never queue once they are not.
    const heatEntry = this.heatMode() === 'entry';
    if (heatEntry) this.book.params.fast.ownMinScore = Object.fromEntries(HEAT_KINDS.map((k) => [k, this.d.heat?.minWeight ?? 0]));
    else delete this.book.params.fast.ownMinScore;
    if (heatEntry) for (const asset of assets) if (this.heatOffer(asset, now)) changed = true;

    // 3. Entries (re-checked on fresh data), unless entries are blocked.
    // Paper training override: the daily loss halt is advisory (it still shows in the status), not a stop.
    const dayHalt = this.d.trainingOverride?.() ? undefined : this.dayHalt;
    const block = guards.halt ?? dayHalt ?? guards.noEntry
      ?? (equity === undefined ? 'margin equity unknown' : equity < this.d.params.minEquityUsd ? `margin equity $${equity.toFixed(2)} below $${this.d.params.minEquityUsd}` : undefined);
    // A missing setup model blocks the chart setups only: a heat setup (the oracle curves' call) is scored by the curves' heat
    // weight and never reads the setup model, so a model file that is missing or fails to load cannot switch heat trades off
    // (meta plan v2, D3, Steven Nov 12).
    const noModel = !this.model ? this.modelError ?? 'no setup model' : undefined;
    if (!block && equity) {
      // Break-even scale: the risk budget of new entries shrinks with net losses (never to zero) and is
      // back to full once wins recoup them.
      this.d.breakEven?.observe(equity);
      const raised = this.d.breakEven?.onEquity(equity, now, this.d.params.dailyGoalUsd);
      if (raised) this.d.audit?.write('training', { event: 'break_even_raised', book: 'perps', ...raised });
      const sizeScale = this.d.breakEven?.scale(equity, this.d.lossAt ?? 0.15) ?? 1;
      this.refreshRiskCaps(now);
      const entries = this.book.select(now, equity * sizeScale, (cand) => {
        if (!assets.includes(cand.sig.asset)) return undefined;
        const px = this.d.spot(cand.sig.asset, now);
        const q = this.d.hub.get(cand.sig.asset)?.latest;
        if (!(px && px > 0) || q?.bid === undefined || q.ask === undefined || q.isOpen === false) return undefined;
        // The setup model's three gates (the model file, its validation, the setup SNN's lean) rule on chart setups. A heat setup
        // skips all three: the curves are its only reason to trade, and a retrained model must not switch heat trades on or off
        // (meta plan v2, D3). The heat re-check below, the caps, the stop and the liquidation rule still apply to it.
        const isHeat = cand.sig.kind === 'heat';
        if (!isHeat && noModel) return noModel;
        if (!isHeat && this.d.params.requireValidation && !gatePasses('setups', Boolean(this.model?.validated(cand.sig.lane)))) return undefined;
        if (!isHeat && this.snnBlocks(cand.sig)) return undefined;
        // The direction curves: the hourly gate, and for a heat setup the re-read of its horizon's direction and the day's.
        const heat = this.heatRecheck(cand.sig, now);
        if (heat.drop) { this.d.audit?.write('setup_skip', { asset: cand.sig.asset, lane: cand.sig.lane, kind: cand.sig.kind, reason: heat.drop }); return heat.drop; }
        // Heat trades are sized by the heat weight alone: no trained conviction multiplier, priority or playbook weight (1x).
        const cv = isHeat ? undefined : this.conviction(cand.sig.asset, cand.sig.dir, now);
        // Strategy weight: the Compensator's ramp for this setup kind on the coin's Librarian reading
        // (bot/strategy/compensator.ts) when it is on, else the playbook's perps weight in this coin's confirmed regime
        // (bot/strategy/playbook.ts); waterfall mode (bot/macro/waterfall.ts) leans into alt longs, drops alt shorts and
        // lightens BTC. Together at most 2x; the lanes' notional caps and the liquidation cap still bind.
        const pbW = isHeat ? 1 : compensator()?.weight(cand.sig.asset, `setup:${cand.sig.kind}`, now)?.w ?? playbook()?.weights(marketContext()?.regimeOf(cand.sig.asset), now).perps;
        const wf = macro()?.policy();
        const wfW = wf ? wf.perpMult(cand.sig.asset, cand.sig.dir) : 1;
        const weight = Math.min(2, (pbW ?? 1) * wfW);
        const weightWhy = wfW === 0 ? `waterfall mode: ${wf!.why}` : undefined;
        // A heat setup is scored by the heat weight of its horizon's direction now, not by the setup model (which never saw the type).
        return { px, score: heat.weight ?? this.score(cand.sig, now), mult: cv?.mult, priority: cv?.priority, why: cv?.why, weight, weightWhy };
      }, (cand) => (cand.sig.kind === 'heat' ? 0 : this.conviction(cand.sig.asset, cand.sig.dir, now)?.priority ?? 0));
      for (const e of entries) {
        const t = openTrade(e.cand.sig, e.px, now, this.d.params.costs);
        if (!t) continue;
        // On probation (VALIDATION_GATES=monitor) an unvalidated lane trades at full size.
        // A heat trade is never pilot-capped: its size comes from the heat weight and the lane's caps, so a retrain that flips the setup
        // model's validation verdict cannot resize it. Chart setups keep the model-dependent pilot cap.
        const pilot = t.kind === 'heat' ? false : !gatePasses('setups', Boolean(this.model?.validated(t.lane)));
        // Liquidation beyond the stop (bot/risk/liquidation.ts): the equity left after the open trades' losses at
        // their stops and their maintenance margin must carry this one to its stop with the buffer to spare. Also at
        // most half the exchange's leverage for the market.
        const lev = this.d.hub.get(t.asset)?.latest?.leverage;
        const levCap = lev && lev > 0 ? equity * 0.5 * lev : Infinity;
        const reserved = [...this.book.positions.values()].reduce((sum, o) => sum + reservedFor({ notional: (o.notional ?? 0) * o.frac, entry: o.entry, stop: o.stop, dir: o.dir, mmr: this.mmrOf(o.asset) }), 0);
        const liqCap = maxSafeNotional({ equity, reserved, stopFrac: Math.abs(t.entry - t.stop) / t.entry, mmr: this.mmrOf(t.asset), buffer: this.d.params.liqBuffer ?? 0.2 });
        // The conviction multiplier widens the pilot cap with it (never the leverage or liquidation caps).
        t.notional = Math.min(pilot ? Math.min(e.notional, this.d.params.pilotMaxNotionalUsd * e.mult) : e.notional, levCap, liqCap);
        if (!(t.notional > 0)) {
          this.d.audit?.write('setup_skip', { asset: t.asset, lane: t.lane, kind: t.kind, reason: `liquidation would fall inside the stop (equity $${equity.toFixed(2)}, $${reserved.toFixed(2)} tied up by open trades)` });
          continue;
        }
        t.score = e.score;
        // The perp loser cut beside the trade's stop (the size and the liquidation check above keep the trade's own stop).
        const q = this.d.hub.get(t.asset)?.latest;
        const perpMid = q?.bid !== undefined && q.ask !== undefined ? (q.bid + q.ask) / 2 : undefined;
        const cutSet = applyPerpCut(t, this.d.params.loserCut ?? 0, perpMid !== undefined && e.px > 0 ? perpMid / e.px : undefined);
        this.book.add(t);
        this.lastPx.set(t.asset, e.px);
        changed = true;
        this.d.audit?.write('setup_trade', { event: 'opened', asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entry: t.entry, stop: t.stop, ...(cutSet ? { ownStop: t.initialStop, cut: this.d.params.loserCut } : {}), target1: t.plan.target1, target2: t.plan.target2, notional: t.notional, score: e.score, pilot, conviction: e.mult, convictionWhy: e.why ?? null, capped: e.capped ?? null, ...(t.heat ? { heat: t.heat } : {}) });
        const tnE = this.reading(t.asset, now);
        this.d.journal?.trade({ ts: now, event: 'opened', asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entryTs: t.entryTs, entry: t.entry, stop: t.stop, notional: t.notional, score: e.score, pilot, tn_up1: tnE?.up1 ?? null, tn_up4: tnE?.up4 ?? null, tn_vol: tnE?.vol ?? null, ...this.snnOf(t.asset), ...this.heatOf(t.asset, now, t.dir) });
      }
    }

    // 3b. Liquidation guard on open positions: when the exchange's liquidation estimate is not far enough beyond the
    // stop (other positions moved, funding, a thin account), cut the trade until it is. The estimate belongs to the
    // position the exchange holds, so the cut is a share of that, and nothing is judged while an earlier cut is
    // still on its way (the exchange holds more than the trade wants: the estimate predates the cut).
    const risk = this.book.positions.size ? await this.refreshRisk(now) : undefined;
    const guarded = new Set<string>();
    if (risk) for (const [asset, t] of this.book.positions) {
      const l = this.d.hub.get(asset)?.latest, r = l?.ticker ? risk.get(l.ticker) : undefined, spot = this.d.spot(asset, now);
      const perpPx = l?.bid !== undefined && l?.ask !== undefined ? (l.bid + l.ask) / 2 : undefined;
      if (!r?.liquidationPrice || !(perpPx && spot && spot > 0) || Math.sign(r.position) !== t.dir || !(t.frac > 0)) continue;
      const held = Math.abs(r.position) * perpPx, want = (t.notional ?? 0) * t.frac;
      if (held > want * 1.001 + (l!.fractional ? 0.01 : 1) * perpPx) continue;
      const ratio = perpPx / spot;
      const share = safeShare({ dir: t.dir, entry: t.entry * ratio, stop: t.stop * ratio, liquidation: r.liquidationPrice, mmr: this.mmrOf(asset), buffer: this.d.params.liqBuffer ?? 0.2 });
      if (share < 0.999) {
        const from = t.notional ?? 0;
        t.notional = Math.min(from, (held * share) / t.frac);
        guarded.add(asset); changed = true;
        this.d.audit?.write('liquidation_guard', { asset, ticker: l!.ticker, liquidation: r.liquidationPrice, stop: +(t.stop * ratio).toFixed(4), entry: +(t.entry * ratio).toFixed(4), notionalFrom: from, notionalTo: t.notional });
      }
    }

    // 4. Targets per perp market.
    const out: DirTarget[] = [];
    const flatten = guards.halt ?? dayHalt;
    for (const asset of assets) {
      const s = this.d.hub.get(asset)!, l = s.latest!;
      const t = this.book.positions.get(asset);
      const perpPx = l.bid !== undefined && l.ask !== undefined ? (l.bid + l.ask) / 2 : s.price(now, 60_000);
      const spotPx = this.d.spot(asset, now);
      const step = l.fractional ? 0.01 : 1;
      if (flatten) {
        if (t) { t.closed = { ts: now, px: spotPx ?? t.entry, reason: 'manual' }; this.record(t, now); this.book.remove(asset); changed = true; }
        out.push({ asset, ticker: l.ticker, target: 0, urgent: true, reason: `flatten: ${flatten}` });
        this.lastDecisions.set(l.ticker, { target: 0, reason: `flatten: ${flatten}` });
        continue;
      }
      if (!t || !(perpPx && perpPx > 0) || !(spotPx && spotPx > 0)) {
        const why = exitNow.has(asset) ? `exit: ${this.history[this.history.length - 1]?.reason ?? 'stop'}` : t ? 'no perp / spot price: hold' : 'no setup trade';
        if (t && !exitNow.has(asset)) { out.push({ asset, ticker: l.ticker, target: c.positions.get(l.ticker)?.position ?? 0, urgent: false, reason: why }); continue; }
        out.push({ asset, ticker: l.ticker, target: 0, urgent: exitNow.has(asset), reason: why });
        this.lastDecisions.set(l.ticker, { target: 0, reason: why });
        continue;
      }
      const ratio = perpPx / spotPx;
      const contracts = Math.sign(t.dir) * Math.floor(((t.notional ?? 0) * t.frac) / perpPx / step + 1e-9) * step;
      const stopPrice = +(t.stop * ratio).toFixed(4);
      const reason = `${t.lane} ${t.tf} ${t.kind} ${t.dir > 0 ? 'long' : 'short'} from ${t.entry.toFixed(4)}: stop ${t.stop.toFixed(4)}${t.partialDone ? (t.plan.scaleOut ? ` (${Math.round(100 * (1 - t.frac))}% taken off, stop at break-even or trailing)` : ' (half off, stop at break-even or trailing)') : ''}${t.plan.target1 !== undefined && !t.partialDone ? `, target ${t.plan.target1.toFixed(4)}` : ''}${t.plan.target2 !== undefined ? ` then ${t.plan.target2.toFixed(4)}` : t.kind === 'heat' ? (t.tf === '4h' ? ', until the 4-hour close' : ', until the hourly close') : ', trailing'}`;
      out.push({ asset, ticker: l.ticker, target: +contracts.toFixed(4), urgent: guarded.has(asset), reason: guarded.has(asset) ? `liquidation guard: cut so the liquidation sits beyond the stop; ${reason}` : reason, stopPrice });
      this.lastDecisions.set(l.ticker, { target: contracts, reason, stop: stopPrice });
    }
    if (changed) this.save();
    return out;
  }

  /** Optimal f per lane: the model's out-of-sample trades (weighted by age, development years at half)
   *  plus this trader's closed trades (liveMult each), recomputed hourly and whenever a trade closes or
   *  the model changes. The cap limits the Kelly-style size; a drawdown beyond the history's 95th
   *  percentile halves it until the drawdown is back under half that. */
  private refreshRiskCaps(now: number): void {
    const of = this.d.optimalF;
    if (!of?.enabled) { this.book.riskCaps = {}; return; }
    const key = `${this.model?.params.version ?? ''}|${this.history.length}|${this.history[this.history.length - 1]?.exitTs ?? 0}|${Math.floor(now / 3_600_000)}`;
    if (key === this.capsKey) return;
    this.capsKey = key;
    for (const lane of ['fast', 'slow'] as const) {
      const hist = this.model?.params.sizing?.[lane];
      const trades: WeightedTrade[] = (hist?.trades ?? []).map(([ts, r]) => ({ ts, r, w: recencyWeight(ts, now, of.halfLifeDays) * (ts < (hist?.devUntil ?? 0) ? 0.5 : 1) }));
      // Heat trades stay out: the lane's optimal f is measured on the setup model's trades, and a few curve-led
      // trades with their own exit rule would move the cap (to zero, in live) for every other setup in the lane.
      const live = this.history.filter((h) => h.lane === lane && h.kind !== 'heat' && Number.isFinite(h.r)).sort((a, b) => a.exitTs - b.exitTs);
      for (const h of live) trades.push({ ts: h.exitTs, r: h.r, w: recencyWeight(h.exitTs, now, of.halfLifeDays, of.liveMult) });
      const rep = optimalF(trades, { quantile: of.quantile, minTrades: of.minTradesSetups, horizon: 100 });
      let cum = 0, pk = 0;
      for (const h of live) { cum += h.r; pk = Math.max(pk, cum); }
      const liveDdR = pk - cum;
      const dd = drawdownScale(liveDdR, rep.ddP95R, this.ddCut[lane] ?? false);
      if (dd.cut !== (this.ddCut[lane] ?? false)) this.d.audit?.write('setup_sizing', { lane, event: dd.cut ? 'drawdown_cut' : 'drawdown_cleared', liveDdR, ddP95R: rep.ddP95R });
      this.ddCut[lane] = dd.cut;
      let cap = rep.cap;
      if (of.paper && Number.isFinite(cap)) cap = Math.max(cap, of.paperFloor * this.book.params[lane].riskFrac);
      this.book.riskCaps[lane] = { cap, scale: dd.scale, why: rep.note ?? `${rep.n} trades, mean R ${rep.meanR.toFixed(3)}` };
      this.capReports[lane] = { ...rep, liveTrades: live.length, liveDdR };
    }
  }

  status() {
    const m = this.model;
    const today = this.day ? this.day.realized : 0;
    const open = [...this.book.positions.values()].map((t) => ({ asset: t.asset, lane: t.lane, kind: t.kind, tf: t.tf, dir: t.dir, entry: t.entry, stop: t.stop, target1: t.plan.target1 ?? null, target2: t.plan.target2 ?? null, half_off: t.partialDone, left: +t.frac.toFixed(2), bars: t.bars, notional: t.notional ?? null, score: t.score ?? null, open_r: tradeResult(t, this.lastPx.get(t.asset)).r, usd_at_stop: -(t.notional ?? 0) * Math.abs(t.entry - t.initialStop) / t.entry, usd_at_target1: t.plan.target1 !== undefined ? (t.notional ?? 0) * Math.abs(t.plan.target1 - t.entry) / t.entry : null, open_usd: tradeResult(t, this.lastPx.get(t.asset)).ret * (t.notional ?? 0) }));
    const cand = (lane: Lane) => this.book.queues[lane].map((c) => ({ asset: c.sig.asset, kind: c.sig.kind, tf: c.sig.tf, dir: c.sig.dir, score: c.score, expires: c.expires }));
    return {
      strategy: 'setups',
      model: m ? { version: m.params.version, fast: { validated: m.validated('fast'), blockers: m.blockers('fast') }, slow: { validated: m.validated('slow'), blockers: m.blockers('slow') } } : null,
      modelError: this.modelError ?? null,
      // What the rest of the bot contributes: the TA network as model inputs (when the model kept them)
      // and as the volatility trail, the SNN gate (off until the journal proves it).
      inputs: { taNetFeatures: m?.uses('tanet') ?? false, taNetChoice: m?.params.groupChoice ?? null, volTrailK: m?.params.volTrailK ?? 0, snnGate: (() => { const g = this.snnGate(); return g ? { enabled: g.enabled, minAgree: g.minAgree ?? null, reason: g.reason ?? null } : null; })(),
        // The direction curves: the mode in force, the horizons that enter, the day's role, the heat setup's minimum
        // weight, and the provider's last exception.
        heat: this.d.heat ? { mode: this.heatMode(), horizons: this.heatHorizons(), daily: this.d.heat.daily === 'off' ? 'off' : 'context', minWeight: this.d.heat.minWeight ?? 0, topN: this.d.heat.topN ?? 10, throws: this.heatThrows, error: this.heatError ?? null } : null },
      equity: this.equity?.value ?? null, dayStartEquity: this.day?.start ?? null, dayHalt: this.dayHalt ?? null,
      dayHaltAdvisory: Boolean(this.dayHalt && this.d.trainingOverride?.()),
      breakEven: this.d.breakEven?.reference ?? null,
      // Optimal f per lane: the cap on risk per trade from the bootstrap of the trade history (model's
      // out-of-sample trades + live), the drawdown band, and whether the drawdown cut is on.
      optimalF: Object.fromEntries((['fast', 'slow'] as const).map((l) => { const r = this.capReports[l], c = this.book.riskCaps[l]; return [l, r ? { trades: r.n, liveTrades: r.liveTrades, meanR: +r.meanR.toFixed(4), gStar: +r.gStar.toFixed(4), gP25: Number.isFinite(r.gP25) ? +r.gP25.toFixed(4) : null, cap: c && Number.isFinite(c.cap) ? +c.cap.toFixed(4) : null, riskFrac: this.book.params[l].riskFrac, ddP95R: Number.isFinite(r.ddP95R) ? +r.ddP95R.toFixed(2) : null, liveDdR: +r.liveDdR.toFixed(2), ddScale: c?.scale ?? 1, note: r.note ?? null } : null]; })),
      sizeScale: this.equity && this.d.breakEven ? +this.d.breakEven.scale(this.equity.value, this.d.lossAt ?? 0.15).toFixed(3) : null,
      today: { realizedUsd: today, goalUsd: this.d.params.dailyGoalUsd, trades: this.history.filter((h) => this.day && new Date(h.exitTs).toISOString().slice(0, 10) === this.day.key).length },
      lanes: { fast: { open: open.filter((o) => o.lane === 'fast'), queue: cand('fast'), params: this.book.params.fast }, slow: { open: open.filter((o) => o.lane === 'slow'), queue: cand('slow'), params: this.book.params.slow } },
      recentSkips: this.book.lastSkips.slice(0, 20),
      recentTrades: this.history.slice(-20).reverse(),
      decisions: Object.fromEntries(this.lastDecisions),
      lastError: this.lastError ?? null,
    };
  }
}

/** PACER_FLOOR on a setup trade: why its plan aims higher than the quota (undefined: none). A set price: the first target not
 *  yet taken or the final target, beyond the price now; riding mode adds a trade riding its trailing stop. */
export function setupHigher(t: OpenTrade, px: number, mode: PacerFloorMode): string | undefined {
  if (mode === 'off') return undefined;
  const beyond = (x: number | undefined) => x !== undefined && t.dir * (x - px) > 1e-12;
  if (!t.partialDone && beyond(t.plan.target1)) return `the setup's first target ${t.plan.target1}`;
  if (beyond(t.plan.target2)) return `the setup's target ${t.plan.target2}`;
  return mode === 'riding' ? `the setup trade riding its stop ${t.stop}` : undefined;
}

/** Wilder ATR(14) at the last bar. */
function atrOf(cs: Candle[]): number {
  if (cs.length < 16) return NaN;
  let a = 0;
  const tr = (i: number) => Math.max(cs[i].h - cs[i].l, Math.abs(cs[i].h - cs[i - 1].c), Math.abs(cs[i].l - cs[i - 1].c));
  const from = Math.max(1, cs.length - 200);
  for (let i = from; i < from + 14; i++) a += tr(i);
  a /= 14;
  for (let i = from + 14; i < cs.length; i++) a = (a * 13 + tr(i)) / 14;
  return a;
}

export const defaultSetupParams = (o: Partial<SetupTraderParams> = {}): SetupTraderParams => ({
  book: DEFAULT_LANES, costs: DEFAULT_COSTS, dailyLossFrac: 0.05, minEquityUsd: 5, pilotMaxNotionalUsd: 25, requireValidation: false, dailyGoalUsd: 100, ...o,
});
