// Strike-selection spread cap (decision 1, Nov 5): the live catalog's picks with CATALOG_PICK_MAX_SPREAD at 0 (legacy),
// 0.05, 0.10, 0.15 and 0.20 on the same Kalshi history days (ladders and ranges; never the L1 lockbox days).
//
// Every minute, per event, the catalog is refreshed as live does (bot/marketdata/marketData.ts nearestStrikes, the
// listing read from the minute candle: bid, ask, and the last price for the legacy fallback; contracts closing within the
// 90 min horizon; tracked stays tracked). The history has no index here, so the index tier falls back to the ladder's
// middle for every cap alike (a floor on the capped picks; live has a fresh index).
// Reported per cap:
//   miss       share of minutes where the money contract was not tracked (ladder: tight <= 5c quote nearest 50c with
//              |mid - 0.5| <= 0.25; range: the richest tight bucket), and the delay from its first minute at the money
//              to being tracked (p50 / p90, minutes; never tracked counts as the time to close)
//   dead       share of picks that were wide (> 10c) or one-sided at pick time, and of those, how many tightened later
//   paths      share of event refreshes decided by the tight quotes (mid), the index, or the ladder's middle (median)
// Plus near-money spreads (contracts quoted between 30c and 70c): p50, p90, p99.
//
//   node --import tsx research/strikeCapStudy.ts --history DIR --series KXBTCD,KXBTC,... --from 2026-10-21 --to 2026-11-05 [--out f.json]

import fs from 'fs';
import path from 'path';
import { nearestStrikes } from '../bot/marketdata/marketData';
import { contractKind } from '../bot/model/fairValue';
import { listingPickMid } from '../bot/kalshi/wire';
import { loadKalshiHistory, type KalshiHistMarket } from './history/kalshiHistory';

const MIN = 60_000, HORIZON = 90 * MIN, N = 4;
const CAPS = [0, 0.05, 0.1, 0.15, 0.2];

function q(xs: number[], p: number): number { if (!xs.length) return NaN; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; }

interface Acc { truthMin: number; missMin: number; delays: number[]; picks: number; dead: number; deadTightened: number; paths: { mid: number; index: number; median: number } }

export function studyEvent(ms: KalshiHistMarket[], series: string, accs: Map<number, Acc>, spreads: number[]): void {
  const kind = contractKind(series, ms[0].strikeType, ms[0].ticker);
  if (kind === 'updown' || kind === 'match') return;
  const between = kind === 'between';
  const from = Math.min(...ms.map((m) => m.openTime)), to = Math.max(...ms.map((m) => m.closeTime));
  const idx = new Map<string, number>();
  const tracked = new Map<number, Map<string, number>>(CAPS.map((c) => [c, new Map()]));
  const firstTruth = new Map<string, number>();
  for (let t = Math.ceil(from / MIN) * MIN; t < to; t += MIN) {
    const live = ms.filter((m) => m.openTime <= t && m.closeTime > t && m.closeTime <= t + HORIZON);
    if (!live.length) continue;
    const listed = live.map((m) => {
      let i = idx.get(m.ticker) ?? -1;
      while (i + 1 < m.candles.length && m.candles[i + 1].ts <= t) i++;
      idx.set(m.ticker, i);
      const c = i >= 0 ? m.candles[i] : undefined;
      const b = c?.bidC ?? undefined, k = c?.askC ?? undefined, l = c?.last ?? undefined;
      const yesMid = b !== undefined && k !== undefined && b > 0 && k > b && k < 1 ? (b + k) / 2 : l !== undefined && l > 0 && l < 1 ? l : undefined;
      return { m, ticker: m.ticker, eventTicker: m.event, strikeType: m.strikeType, floorStrike: m.strike ?? undefined, capStrike: m.cap ?? undefined, yesBid: b, yesAsk: k, yesMid };
    });
    for (const x of listed) if (x.yesBid !== undefined && x.yesAsk !== undefined && x.yesBid > 0 && x.yesAsk > x.yesBid && x.yesAsk < 1) { const mid = (x.yesBid + x.yesAsk) / 2; if (mid >= 0.3 && mid <= 0.7) spreads.push(x.yesAsk - x.yesBid); }
    // The money contract by tight (<= 5c) quotes.
    const tight = listed.map((x) => ({ x, v: listingPickMid(x.yesBid, x.yesAsk, 0.05) })).filter((y) => y.v !== undefined) as Array<{ x: typeof listed[number]; v: number }>;
    let truth: string | undefined;
    if (between) { const best = tight.sort((a, b) => b.v - a.v)[0]; if (best && best.v >= 0.15) truth = best.x.ticker; }
    else { const best = tight.sort((a, b) => Math.abs(a.v - 0.5) - Math.abs(b.v - 0.5))[0]; if (best && Math.abs(best.v - 0.5) <= 0.25) truth = best.x.ticker; }
    if (truth && !firstTruth.has(truth)) firstTruth.set(truth, t);
    for (const cap of CAPS) {
      const tr = tracked.get(cap)!, acc = accs.get(cap)!;
      const picked = nearestStrikes(listed, (s, st) => contractKind(s, st), series, undefined, N, new Set(tr.keys()), { maxSpread: cap, paths: acc.paths });
      for (const p of picked) {
        if (tr.has(p.ticker)) continue;
        tr.set(p.ticker, t);
        acc.picks++;
        const wide = !(p.yesBid !== undefined && p.yesAsk !== undefined && p.yesBid > 0 && p.yesAsk > p.yesBid && p.yesAsk < 1 && p.yesAsk - p.yesBid <= 0.1);
        if (wide) {
          acc.dead++;
          if (p.m.candles.some((c) => c.ts > t && c.ts <= p.m.closeTime && c.bidC !== null && c.askC !== null && c.bidC > 0 && c.askC > c.bidC && c.askC - c.bidC <= 0.1)) acc.deadTightened++;
        }
      }
      if (truth) { acc.truthMin++; if (!tr.has(truth)) acc.missMin++; }
    }
  }
  for (const [tk, t0] of firstTruth) {
    const m = ms.find((x) => x.ticker === tk)!;
    for (const cap of CAPS) { const at = tracked.get(cap)!.get(tk); accs.get(cap)!.delays.push(at === undefined ? (m.closeTime - t0) / MIN : Math.max(0, (at - t0) / MIN)); }
  }
}

export function strikeCapStudy(dir: string, series: string[], from: number, to: number) {
  const accs = new Map<number, Acc>(CAPS.map((c) => [c, { truthMin: 0, missMin: 0, delays: [], picks: 0, dead: 0, deadTightened: 0, paths: { mid: 0, index: 0, median: 0 } }]));
  const spreads: number[] = [];
  let events = 0, markets = 0;
  for (const s of series) {
    const byEvent = new Map<string, KalshiHistMarket[]>();
    for (const m of loadKalshiHistory(dir, s)) {
      if (m.closeTime < from || m.closeTime >= to || !m.candles?.length || /DOGE/.test(m.ticker)) continue;
      const e = m.event ?? m.ticker.split('-').slice(0, -1).join('-');
      (byEvent.get(e) ?? byEvent.set(e, []).get(e)!).push(m);
    }
    for (const ms of byEvent.values()) { events++; markets += ms.length; studyEvent(ms, s, accs, spreads); }
  }
  const caps = Object.fromEntries([...accs].map(([c, a]) => {
    const tot = a.paths.mid + a.paths.index + a.paths.median || 1;
    return [c === 0 ? 'legacy' : `${Math.round(c * 100)}c`, {
      missShare: a.missMin / Math.max(1, a.truthMin), moneyMinutes: a.truthMin,
      delayMin: { p50: q(a.delays, 0.5), p90: q(a.delays, 0.9), mean: a.delays.reduce((x, y) => x + y, 0) / Math.max(1, a.delays.length) },
      picks: a.picks, deadAtPickShare: a.dead / Math.max(1, a.picks), deadLaterTightened: a.deadTightened,
      paths: { mid: a.paths.mid / tot, index: a.paths.index / tot, median: a.paths.median / tot },
    }];
  }));
  const legacy = caps.legacy, ten = caps['10c'];
  return {
    label: 'history days only (no L1 lockbox days); index tier = ladder middle for every cap',
    span: { from: new Date(from).toISOString(), to: new Date(to).toISOString() }, series, events, markets,
    nearMoneySpread: { p50: q(spreads, 0.5), p90: q(spreads, 0.9), p99: q(spreads, 0.99), n: spreads.length },
    caps,
    pass10c: ten.missShare <= legacy.missShare + 1e-9 && ten.delayMin.mean <= legacy.delayMin.mean + 1e-9,
  };
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) {
  const arg = (k: string, d: string) => { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
  const r = strikeCapStudy(arg('history', 'data/history/kalshi'), arg('series', '').split(',').filter(Boolean), Date.parse(`${arg('from', '2026-10-21')}T00:00:00Z`), Date.parse(`${arg('to', '2026-11-05')}T00:00:00Z`));
  const out = arg('out', '');
  if (out) fs.writeFileSync(out, JSON.stringify(r, null, 2));
  console.log(JSON.stringify(r, null, 2));
}
