// Probation: models that have not passed their validation trade anyway (VALIDATION_GATES=monitor), and their
// book's realized results are scored.
//
// A validation gate normally keeps a model out of trading until its backtest proves it (the Kalshi MLP's go-live
// gates, the take/skip head, the fill model, hunt mode in live, the perps model's full size, the setup types the
// setup model has not proven, the tennis model, the GP signals in live). In monitor mode each of those is used as
// soon as it exists, on probation: every settled Kalshi market, closed setup trade, closed perps position and settled
// tennis market of its book is one result. The book would bench when its results are unacceptable:
//   - a net loss beyond the loss limit at any time: PROBATION_MAX_LOSS_USD, or PROBATION_MAX_LOSS_PCT of the book's
//     break-even (its starting cash, moved by deposits and refills) when that is smaller, so the limit follows the
//     size of the account ($25, or 15% of a $41 account: $6.18), or
//   - after PROBATION_MIN_TRADES results, a negative net with t = mean / (sd / sqrt(n)) at or below -PROBATION_T
//     (losing by more than luck explains).
// By default (PROBATION_BENCH=false, the same in paper and live) probation only scores: a book that would bench raises
// an "iterate this book" alert and nothing is turned off, so a book's own P&L never decides which of its parts run.
// PROBATION_BENCH=true is the owner's emergency gate: the book is benched (its unvalidated parts go back behind their
// gates, validated parts keep trading). Either way the verdict is checked again at every result and at start, and it
// clears once the window recovers: the net back above half the loss limit and t above -PROBATION_T/2 (the gap keeps
// a book near the limit from flapping). Alerts go out only when the verdict changes, at most one per book per 6
// hours. A new model for the book (the trainer's next promotion) or the dashboard also starts a fresh probation. Only
// the most recent PROBATION_WINDOW results count. Inputs to other models (TA heads, Librarian, cross-asset graph and
// leads) are not gated here: the models that read them were trained with those gates.

import { readJson, writeJsonAtomic } from '../util/persist';

export type ProbationBook = 'kalshi' | 'perps' | 'setups' | 'tennis';
export const PROBATION_BOOKS: ProbationBook[] = ['kalshi', 'perps', 'setups', 'tennis'];

export interface ProbationParams {
  mode: 'monitor' | 'enforce';
  minTrades: number;
  /** Would bench when losing with t at or below -this. */
  t: number;
  maxLossUsd: number;
  /** ...or this fraction of the book's break-even, when smaller. 0 = the dollar limit alone. */
  maxLossPct: number;
  window: number;
  /** PROBATION_BENCH: a book that would bench is benched (its unvalidated parts stop). false: scored and alerted only. */
  bench: boolean;
}

export const DEFAULT_PROBATION: ProbationParams = { mode: 'monitor', minTrades: 20, t: 1, maxLossUsd: 25, maxLossPct: 0.15, window: 200, bench: false };

/** At most one alert per book in this long. */
export const PROBATION_ALERT_MS = 6 * 3600_000;

// benched is the stored verdict, under the key older files carry: the book would bench, and is benched while
// PROBATION_BENCH is on.
interface BookState { results: number[]; since: number; benched?: { at: number; reason: string } }
type State = Record<ProbationBook, BookState>;

export interface ProbationBookStatus {
  trades: number; netUsd: number; t: number | null; since: number;
  /** The stored verdict, set while the book would bench, whether or not PROBATION_BENCH is on. */
  benched: { at: number; reason: string } | null;
  /** The book's results are past a limit and have not recovered. */
  wouldBench: boolean;
  /** It would bench and PROBATION_BENCH is on: its unvalidated parts are off. */
  benchActive: boolean;
  open: boolean; maxLossUsd: number;
}

/** A change of a book's verdict. alert is false when the book already had an alert in the last 6 hours. */
export interface ProbationEvent { book: ProbationBook; event: 'bench' | 'clear'; reason: string; active: boolean; alert: boolean }

export class Probation {
  private st: State;
  private breakEvenOf?: (book: ProbationBook) => number | undefined;
  private readonly alertedAt = new Map<ProbationBook, number>();

  constructor(readonly p: ProbationParams = DEFAULT_PROBATION, private readonly file?: string, private readonly onChange?: (e: ProbationEvent) => void, now = Date.now()) {
    const saved = file ? readJson<Partial<State>>(file, { quarantine: true }) : undefined;
    this.st = Object.fromEntries(PROBATION_BOOKS.map((b) => [b, saved?.[b] ?? { results: [], since: now }])) as State;
  }

  /** Each book's break-even (main.ts: the Kalshi pool for kalshi and tennis, the perps margin for perps and setups). */
  setBreakEven(fn: (book: ProbationBook) => number | undefined): void { this.breakEvenOf = fn; }

  /** The net loss at which the book would bench: PROBATION_MAX_LOSS_USD, or PROBATION_MAX_LOSS_PCT of its break-even if smaller. */
  maxLoss(book: ProbationBook): number {
    const be = this.breakEvenOf?.(book);
    return this.p.maxLossPct > 0 && be !== undefined && be > 0 ? Math.min(this.p.maxLossUsd, this.p.maxLossPct * be) : this.p.maxLossUsd;
  }

  /** Apply the rules to every book: at start, once the loss limits are known, a book already past them would bench
   *  now rather than at its next result, and one whose window has recovered clears. */
  review(now = Date.now()): void {
    if (this.p.mode !== 'monitor') return;
    let changed = false;
    for (const book of PROBATION_BOOKS) changed = this.evaluate(book, now) || changed;
    if (changed) this.save();
  }

  /** May an unvalidated part of this book trade? (A validated part always may.) Only PROBATION_BENCH closes it. */
  open(book: ProbationBook): boolean {
    return this.p.mode === 'monitor' && (!this.p.bench || !this.st[book].benched);
  }

  /** Validated, or unvalidated and on an open probation. */
  passes(book: ProbationBook, validated: boolean): boolean {
    return validated || this.open(book);
  }

  /** One realized result of the book, in dollars. */
  record(book: ProbationBook, usd: number, now = Date.now()): void {
    if (this.p.mode !== 'monitor' || !Number.isFinite(usd)) return;
    const b = this.st[book];
    b.results.push(+usd.toFixed(4));
    if (b.results.length > this.p.window) b.results.splice(0, b.results.length - this.p.window);
    this.evaluate(book, now);
    this.save();
  }

  /** A fresh probation for the book (a new model for it, or the dashboard). */
  reset(book: ProbationBook, now = Date.now()): void {
    this.st[book] = { results: [], since: now };
    this.save();
  }

  status(): Record<ProbationBook, ProbationBookStatus> & { mode: string } {
    const out = { mode: this.p.mode } as Record<ProbationBook, ProbationBookStatus> & { mode: string };
    for (const k of PROBATION_BOOKS) {
      const b = this.st[k], s = stats(b.results);
      out[k] = {
        trades: b.results.length, netUsd: +s.sum.toFixed(2), t: s.t === null ? null : +s.t.toFixed(2), since: b.since, benched: b.benched ?? null,
        wouldBench: Boolean(b.benched), benchActive: this.p.bench && Boolean(b.benched), open: this.open(k), maxLossUsd: +this.maxLoss(k).toFixed(2),
      };
    }
    return out;
  }

  /** Check the book's verdict against its window: set it past a limit, clear it once recovered. True when it changed. */
  private evaluate(book: ProbationBook, now: number): boolean {
    const b = this.st[book];
    const why = b.benched ? this.recovered(book, b.results) : this.verdict(book, b.results);
    if (!why) return false;
    if (b.benched) delete b.benched;
    else b.benched = { at: now, reason: why };
    this.emit(book, b.benched ? 'bench' : 'clear', why, now);
    return true;
  }

  private emit(book: ProbationBook, event: ProbationEvent['event'], reason: string, now: number): void {
    const last = this.alertedAt.get(book);
    const alert = last === undefined || now - last >= PROBATION_ALERT_MS;
    if (alert) this.alertedAt.set(book, now);
    this.onChange?.({ book, event, reason, active: this.p.bench, alert });
  }

  /** The window has recovered: the net above half the loss limit and t above -PROBATION_T/2 (or too few results for a t). */
  private recovered(book: ProbationBook, r: number[]): string | undefined {
    const s = stats(r);
    const cap = this.maxLoss(book);
    if (s.sum <= -0.5 * cap || (s.t !== null && s.t <= -this.p.t / 2)) return undefined;
    return `recovered: net $${s.sum.toFixed(2)} over ${r.length} results, above half the $${cap.toFixed(2)} loss limit${s.t !== null ? `, t ${s.t.toFixed(2)}` : ''}`;
  }

  private verdict(book: ProbationBook, r: number[]): string | undefined {
    const s = stats(r);
    const cap = this.maxLoss(book);
    const limit = cap < this.p.maxLossUsd
      ? `PROBATION_MAX_LOSS_PCT (${+(this.p.maxLossPct * 100).toFixed(1)}% of the $${this.breakEvenOf!(book)!.toFixed(2)} break-even: $${cap.toFixed(2)})`
      : `PROBATION_MAX_LOSS_USD ($${this.p.maxLossUsd})`;
    if (s.sum <= -cap) return `net loss $${(-s.sum).toFixed(2)} over ${r.length} results reached ${limit}`;
    if (r.length >= this.p.minTrades && s.sum < 0 && s.t !== null && s.t <= -this.p.t) return `losing beyond luck: net $${s.sum.toFixed(2)} over ${r.length} results, t ${s.t.toFixed(2)}`;
    return undefined;
  }

  private save(): void {
    if (this.file) writeJsonAtomic(this.file, this.st);
  }
}

function stats(r: number[]): { sum: number; t: number | null } {
  const n = r.length, sum = r.reduce((a, v) => a + v, 0);
  if (n < 2) return { sum, t: null };
  const m = sum / n, sd = Math.sqrt(r.reduce((a, v) => a + (v - m) ** 2, 0) / (n - 1));
  return { sum, t: sd > 0 ? m / (sd / Math.sqrt(n)) : m < 0 ? -Infinity : m > 0 ? Infinity : 0 };
}

// The process-wide probation (bot/main.ts sets it from the config). Unset (tests, research): enforce, the gates as before.
let active: Probation | undefined;
export function setProbation(p: Probation | undefined): void { active = p; }
export function probation(): Probation | undefined { return active; }
/** Validated, or unvalidated with this book on an open probation. */
export function gatePasses(book: ProbationBook, validated: boolean): boolean { return validated || Boolean(active?.open(book)); }
