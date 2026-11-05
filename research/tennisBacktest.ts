// Backtest the ATP tennis rules on recorded Kalshi books and trades, through
// the same decision code production uses (bot/tennis/tennisStrategy.ts) and
// the queue-aware paper exchange (maker orders fill only when trades reach
// them). Reports P&L per leg (underdog bounce, favorite re-entry), hit rates
// and a bootstrap CI per match, so the rules can be judged before real money.
// Steven's profit rules apply as in the engine (bot/engine.ts, decideMatch's rules): the quota snipe with the pacer's need
// and floors, and the last 30% of the match riding in profit. The pacer here sees tennis P&L only (in the bot it is shared
// with every contract type), so main() reports the run with and without it. Not modelled: the live score feed (progress
// uses the time and information clocks), the tennis fair model and the exit curve filter.
//   npm run research:tennis -- --recordings data/recordings [--bankroll 200]

import path from 'path';
import { loadConfig, paperEnv, type TennisConfig } from '../bot/config';
import { openEntryFee, openSidePrice, PositionBook } from '../bot/oms/positions';
import { PaperExchange } from '../bot/paper/paperExchange';
import { marketWorstLoss } from '../bot/risk/exposure';
import { HourlyQuotaPacer, QuotaFloors, type PacerConfig, type PacerFloorMode } from '../bot/risk/quotaPacer';
import { breakEvenExit, positionNetAtBid } from '../bot/strategy/fairValueStrategy';
import { decideMatch, MatchTracker, type MatchMarket, type TennisPlan } from '../bot/tennis/tennisStrategy';
import { readRecordings, ReplayState } from './replay';
import { bootstrapMeanCi } from './stats';

const FEES = { takerMultiplier: 1, makerMultiplier: 1 };

/** The profit rules the engine passes decideMatch. Unset: none (the strategy's own legs only). */
export interface TennisBacktestRules {
  /** The hourly quota pacer (STRATEGY_PACER_*); off when unset or disabled. */
  pacer?: PacerConfig;
  /** TENNIS_NO_EXIT_BEFORE_END_FRAC: the last share of the match in which a position in profit after fees rides. */
  settleFrac?: number;
  /** TENNIS_END_LOSER_CUT and TENNIS_END_ENTRY_MARGIN: in that share a position not in profit after fees is sold at the bid,
   *  and no entry is placed from the margin before it. */
  endLoserCut?: boolean;
  endEntryMargin?: number;
  /** PACER_FLOOR and PACER_FLOOR_TICKS. */
  floorMode?: PacerFloorMode;
  floorTicks?: number;
}

/** The rules as the engine reads them from the config. */
export function engineTennisRules(cfg: { tennis: TennisConfig; strategy: { pacer: PacerConfig } }, pacer = true): TennisBacktestRules {
  return { pacer: pacer ? cfg.strategy.pacer : undefined, settleFrac: cfg.tennis.settleFrac, endLoserCut: cfg.tennis.endLoserCut, endEntryMargin: cfg.tennis.endEntryMargin, floorMode: cfg.strategy.pacer.floor, floorTicks: cfg.strategy.pacer.floorTicks };
}

export interface TennisBacktest {
  matches: number;
  byLeg: Record<string, { fills: number; contracts: number }>;
  perMatchPnl: number[];
  pnl: number;
  fees: number;
  maxTennisRisk: number;
}

/** Signed taker flow over the last minute, as the engine computes it. */
function flowOf(st: ReplayState, ticker: string, windowSec = 60): number | undefined {
  const tr = st.features.micro.get(ticker)?.tradesIn(st.now, windowSec * 1000) ?? [];
  const tot = tr.reduce((x, y) => x + y.count, 0);
  return tot > 0 ? tr.reduce((x, y) => x + y.signed, 0) / tot : undefined;
}

/** `st`: the replay's state (a test reads what it holds at the end). */
export async function runTennisBacktest(dir: string, cfg: TennisConfig, bankroll0: number, st = new ReplayState(), rules: TennisBacktestRules = {}): Promise<TennisBacktest> {
  const pos = new PositionBook();
  let pacer: HourlyQuotaPacer | undefined;
  const pacerAt = (now: number) => (rules.pacer?.enabled ? (pacer ??= new HourlyQuotaPacer(rules.pacer, now)) : undefined);
  const floors = new QuotaFloors();
  const ex = new PaperExchange(undefined, bankroll0, (t) => st.books.get(t), () => FEES, () => st.now);
  const trackers = new Map<string, MatchTracker>();
  const legOf = new Map<string, string>();
  const res: TennisBacktest = { matches: 0, byLeg: {}, perMatchPnl: [], pnl: 0, fees: 0, maxTennisRisk: 0 };
  const eventOf = (t: string) => st.markets.get(t)?.event ?? t.slice(0, t.lastIndexOf('-'));
  ex.on('fill', (f) => {
    const after = pos.applyFill({ ticker: f.ticker, side: f.side, count: f.count, price: f.price, fee: f.fee ?? 0 }, { closeTs: st.markets.get(f.ticker)?.closeTime });
    pacerAt(st.now)?.onFill(f, f.fee ?? 0, after, st.now);
    res.fees += f.fee ?? 0;
    const leg = legOf.get(f.clientOrderId ?? '') ?? 'unknown';
    const b = (res.byLeg[leg] ??= { fills: 0, contracts: 0 });
    b.fills++; b.contracts += f.count;
  });
  let last = 0;
  for await (const e of readRecordings(dir)) {
    st.apply(e);
    if (e.k === 'trade') ex.onTrade(e.ticker, e.price, e.count, e.takerSide, e.ts);
    if (st.now - last < 5000) continue;
    last = st.now;
    // The other markets the recordings carry (every crypto contract) go once over; the matches are settled below.
    st.forgetClosed(90_000, (m) => m.kind === 'match');
    const byEvent = new Map<string, string[]>();
    for (const m of st.markets.values()) if (m.kind === 'match') byEvent.set(eventOf(m.ticker), [...(byEvent.get(eventOf(m.ticker)) ?? []), m.ticker]);
    const open = await ex.getOpenOrders();
    const tennisRisk = () => [...new Set([...pos.unsettled().map((p) => p.ticker), ...open.map((o) => o.ticker)])]
      .reduce((s, t) => s + marketWorstLoss(pos.get(t), open.filter((o) => o.ticker === t).map((o) => ({ ticker: t, side: o.side, price: o.price, remaining: o.remainingCount, isTaker: false })), FEES), 0);
    const bankroll = Math.max(0, (await ex.getBalance()) + pos.open().reduce((s, p) => s + PositionBook.maxLoss(p), 0));
    for (const [event, tickers] of byEvent) {
      tickers.sort();
      const ms = tickers.map((t) => st.markets.get(t)!);
      // Settle.
      const closed = ms.every((m) => st.now >= m.closeTime + 60_000 || st.results.has(m.ticker));
      if (closed) {
        let pnl = 0;
        for (const m of ms) {
          const r = st.results.get(m.ticker);
          if (!r) continue;
          for (const o of open.filter((x) => x.ticker === m.ticker)) await ex.cancelOrder(o.orderId);
          ex.settle(m.ticker, r);
          const p = pos.get(m.ticker);
          if (p && !p.settled) { pos.settle(m.ticker, r, st.now); pnl += p.realized ?? 0; pacer?.onSettled(m.ticker, p.realized ?? 0, st.now); }
          floors.forget(m.ticker);
          st.forget(m.ticker);
        }
        if (trackers.has(event)) { res.matches++; res.perMatchPnl.push(pnl); res.pnl += pnl; }
        trackers.delete(event);
        continue;
      }
      let tr = trackers.get(event);
      if (!tr) { tr = new MatchTracker(event, cfg); trackers.set(event, tr); }
      const markets: MatchMarket[] = ms.map((m) => {
        const b = st.books.get(m.ticker);
        const p = pos.get(m.ticker);
        const usable = b?.isUsable(st.now, 10_000);
        return { ticker: m.ticker, title: m.title, position: p?.yes ?? 0, avgEntry: p && p.yes > 0 ? openSidePrice(p) : undefined, breakEven: p && p.yes > 0 ? breakEvenExit(p.yes, openSidePrice(p)! + openEntryFee(p)!, FEES) : undefined, quote: { bid: usable ? b!.bestBid()?.price : undefined, ask: usable ? b!.bestAsk()?.price : undefined }, book: usable ? b : undefined, flow: flowOf(st, m.ticker, cfg.confWindowSec) };
      });
      // The quota snipe's measure, as the engine gives it: the whole position's profit after fees at the bid, the cost basis
      // with the entry fee in.
      for (const x of markets) {
        const p = pos.get(x.ticker);
        // As the engine: the open contracts' own cost, entry fee in (bot/oms/positions.ts).
        if (p && p.yes > 0) x.netAtBid = positionNetAtBid(p.yes, openSidePrice(p)! + openEntryFee(p)!, x.quote.bid !== undefined ? { price: x.quote.bid } : undefined, x.quote.ask !== undefined ? { price: x.quote.ask } : undefined, FEES);
      }
      const risk = tennisRisk();
      res.maxTennisRisk = Math.max(res.maxTennisRisk, risk);
      const matchRisk = tickers.reduce((s, t) => s + marketWorstLoss(pos.get(t), [], FEES), 0);
      const out = decideMatch(tr, { event, now: st.now, startTime: ms.find((m) => m.startTime)?.startTime, markets, closeTime: Math.min(...ms.map((m) => m.closeTime)) }, cfg, { bankroll, tennisRisk: risk, matchRisk }, ms[0].tickSize,
        { pacerUsd: pacerAt(st.now)?.neededUsd(st.now), settleFrac: rules.settleFrac, endLoserCut: rules.endLoserCut, endEntryMargin: rules.endEntryMargin, floorMode: rules.floorMode, floors, floorTicks: rules.floorTicks });
      const mine = open.filter((o) => tickers.includes(o.ticker));
      const same = (p: TennisPlan, o: typeof mine[number]) => p.ticker === o.ticker && p.side === o.side && Math.abs(p.price - o.price) < 1e-9 && Math.abs(p.count - o.remainingCount) < 0.02;
      for (const o of mine) if (!out.plans.some((p) => same(p, o))) await ex.cancelOrder(o.orderId);
      for (const p of out.plans) {
        if (mine.some((o) => same(p, o))) continue;
        const id = `${p.ticker}-${st.now}-${p.leg}`;
        legOf.set(id, p.leg);
        try {
          await ex.createOrder({ ticker: p.ticker, side: p.side, count: p.count, price: p.price, timeInForce: p.timeInForce, postOnly: p.postOnly, reduceOnly: p.reduceOnly, selfTradePrevention: 'taker_at_cross', clientOrderId: id });
        } catch { /* rejected like the exchange would */ }
      }
    }
  }
  return res;
}

async function main() {
  const arg = (n: string, d: string) => { const i = process.argv.indexOf(`--${n}`); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
  const cfg = loadConfig(paperEnv(process.env));
  const dir = arg('recordings', 'data/recordings'), bankroll = Number(arg('bankroll', String(cfg.paperBankrollUsd)));
  // The pacer here sees tennis alone (in the bot it is shared with every contract type): both runs are shown.
  for (const [name, pacer] of [['pacer on (tennis P&L only)', true], ['pacer off', false]] as const) {
    if (pacer && !cfg.strategy.pacer.enabled) continue;
    const r = await runTennisBacktest(dir, cfg.tennis, bankroll, new ReplayState(), engineTennisRules(cfg, pacer));
    const ci = bootstrapMeanCi(r.perMatchPnl);
    console.log(name);
    console.table([{ matches: r.matches, pnl: +r.pnl.toFixed(2), fees: +r.fees.toFixed(2), pnlPerMatch: ci.mean, ciLo: ci.lo, ciHi: ci.hi, maxTennisRisk: +r.maxTennisRisk.toFixed(2) }]);
    console.table(r.byLeg);
  }
  console.log('Enable real-money tennis (TENNIS_LIVE=true) only if the per-match CI lower bound is above 0 over at least ~200 matches.');
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) void main();
