// Oracle setups OR-H2: the reversal-specific spot features (python/oracle/prereg/OR-H2.md "Features"). Built from the grid's
// spot bars (1m / 5m / 15m, research/perpTaSweep.ts aggregate: complete bars only) with the bot's own indicator math
// (bot/ta/indicators.ts: rsi, bollinger, stochastic, williamsR, atr; the CCI is the textbook one, defined here).
//
// Every reading is a function of its bar and EARLIER bars of the same timeframe, and is read at the end of minute i from
// the last bar CLOSED by then (bar k of an m-minute timeframe is closed at the end of minute (k + 1) m - 1), exactly as
// buildPrims' primitives are read (stateAt). Nothing computed from a later bar can reach a row (tests/oracleExport.test.ts
// perturbs every value after a decision and compares).
//
// Sign convention of the state features: +1 = a bullish reversal is signalled (price was pushed down / oversold), -1 = a
// bearish one (pushed up / overbought), 0 = nothing / NA. Buckets: 0..5 with -1 = NA.
//
// Names: rev:<reading>@<m>m. Per timeframe m in {1, 5, 15}:
//   rev:rsi70_30       RSI(14) beyond 30 / 70                  rev:rsi_back70_30  RSI back inside 30 / 70 after a bar beyond it
//   rev:rsi80_20       RSI(14) beyond 20 / 80                  rev:rsi_back80_20  RSI back inside 20 / 80 after a bar beyond it
//   rev:pctb_out       Bollinger(20, 2) %B outside 0 / 1       rev:pctb_back      the close back inside the band after a bar outside it
//   rev:stoch_out      slow Stochastic 14/3/3 %K crossing out of 20 (up) / 80 (down)
//   rev:stoch_cross    %K crossing %D inside the 20 / 80 zone
//   rev:willr          Williams %R(14) beyond -80 / -20        rev:willr_back     back inside -80 / -20
//   rev:cci100, rev:cci200  CCI(14) beyond -+100 / -+200       rev:cci_back100    CCI back inside -+100
//   rev:engulf, rev:pin, rev:key   candle reversal patterns (engulfing, hammer / shooting star, key reversal bar)
//   rev:tflow_spike    volume spike with a one-sided taker flow at the 12-bar high (-1) / low (+1)
//   rev:dist_hi12, dist_lo12, dist_hi48, dist_lo48   (12 / 48-bar high - close) / ATR(14), (close - low) / ATR(14), buckets
//                      <0.5, 0.5-1, 1-2, 2-3, 3-4, >=4
//   rev:vwap_dist60@1m, rev:vwap_distday@1m   bucket of (close - VWAP) / close in bps (rolling 60-minute VWAP; UTC-day-anchored VWAP), 1m bars,
//                      typical price x volume: <-50, -50..-15, -15..15, 15..50, >50; -1 = NA (no volume yet)
//   rev:ma_stack@5m    state on 5m closes: +1 if SMA9 > SMA50 > SMA100 > SMA200, -1 if SMA9 < SMA50 < SMA100 < SMA200, else 0
//   rev:since_hi12, since_lo12, since_hi48, since_lo48   bars since that window's high / low: 0, 1, 2, 3-5, 6-11, >=12

import { aggregate, type Grid } from '../perpTaSweep';
import { atr, bollinger, rsi, sma, stochastic, williamsR, type Candle } from '../../bot/ta/indicators';

const fin = Number.isFinite;
export const REV_TFS = [1, 5, 15] as const;
export const REV_WINDOWS = [12, 48] as const;
export const DIST_EDGES = [0.5, 1, 2, 3, 4];
export const DIST_NAMES = ['<0.5', '0.5-1', '1-2', '2-3', '3-4', '>=4'];
export const VWAP_EDGES = [-50, -15, 15, 50];
export const VWAP_NAMES = ['<-50', '-50..-15', '-15..15', '15..50', '>50'];
export const SINCE_NAMES = ['0', '1', '2', '3-5', '6-11', '>=12'];

export interface RevFeature { name: string; kind: 'state' | 'bucket'; levels: number[]; desc: string; level_names?: string[]; at: (i: number) => number }

/** Commodity Channel Index (n = 14): (typical price - SMA) / (0.015 x mean absolute deviation). NaN until n bars; 0 when flat. */
export function cci(cs: Candle[], n = 14): number[] {
  const tp = cs.map((c) => (c.h + c.l + c.c) / 3), m = sma(tp, n);
  return tp.map((x, i) => {
    if (i < n - 1 || !fin(m[i])) return NaN;
    let d = 0;
    for (let j = i - n + 1; j <= i; j++) d += Math.abs(tp[j] - m[i]);
    d /= n;
    return d > 0 ? (x - m[i]) / (0.015 * d) : 0;
  });
}

const dist = (x: number) => { if (!fin(x)) return -1; let l = 0; for (const e of DIST_EDGES) if (x >= e) l++; return l; };
const sinceLevel = (b: number) => (b <= 2 ? b : b <= 5 ? 3 : b <= 11 ? 4 : 5);

/** A bar-level array read at the end of minute i: the last bar of an m-minute timeframe closed by then (na outside). */
function reader(arr: Int8Array, m: number, na: number): (i: number) => number {
  return (i) => { const k = Math.floor((i + 1) / m) - 1; return k >= 0 && k < arr.length ? arr[k] : na; };
}

export function revFeatures(g: Grid, nMax: number, log: (m: string) => void = () => undefined): RevFeature[] {
  const out: RevFeature[] = [];
  const seen = new Set<string>();
  const add = (f: RevFeature) => { if (seen.has(f.name)) throw new Error(`duplicate feature ${f.name}`); seen.add(f.name); out.push(f); };
  for (const m of REV_TFS) {
    const t0 = Date.now();
    const cs = aggregate(g, m, nMax), K = cs.length, c = cs.map((x) => x.c);
    const state = (name: string, desc: string, f: (k: number) => number) => {
      const s = new Int8Array(K);
      for (let k = 0; k < K; k++) { const v = f(k); s[k] = v > 0 ? 1 : v < 0 ? -1 : 0; }
      add({ name: `rev:${name}@${m}m`, kind: 'state', levels: [-1, 0, 1], desc: `${desc} on ${m}m spot bars (last closed bar; +1 bullish reversal signalled, -1 bearish)`, at: reader(s, m, 0) });
    };
    const bucket = (name: string, desc: string, names: string[], f: (k: number) => number) => {
      const s = new Int8Array(K);
      for (let k = 0; k < K; k++) s[k] = f(k);
      add({ name: `rev:${name}@${m}m`, kind: 'bucket', levels: names.map((_, j) => j), level_names: names, desc: `${desc} on ${m}m spot bars (last closed bar; -1 = NA)`, at: reader(s, m, -1) });
    };
    const rs = rsi(c, 14), bb = bollinger(c, 20, 2), st = stochastic(cs, 14, 3), sk = st.d, sd = sma(sk, 3), wr = williamsR(cs, 14), cc = cci(cs, 14), a = atr(cs, 14);
    const prev = (x: number[], k: number) => (k > 0 ? x[k - 1] : NaN);
    state('rsi70_30', 'RSI(14) < 30 (+1) / > 70 (-1)', (k) => (rs[k] < 30 ? 1 : rs[k] > 70 ? -1 : 0));
    state('rsi80_20', 'RSI(14) < 20 (+1) / > 80 (-1)', (k) => (rs[k] < 20 ? 1 : rs[k] > 80 ? -1 : 0));
    state('rsi_back70_30', 'RSI(14) back above 30 (+1) / below 70 (-1) after a bar beyond it', (k) => (prev(rs, k) < 30 && rs[k] >= 30 ? 1 : prev(rs, k) > 70 && rs[k] <= 70 ? -1 : 0));
    state('rsi_back80_20', 'RSI(14) back above 20 (+1) / below 80 (-1) after a bar beyond it', (k) => (prev(rs, k) < 20 && rs[k] >= 20 ? 1 : prev(rs, k) > 80 && rs[k] <= 80 ? -1 : 0));
    state('pctb_out', 'Bollinger(20, 2) %B < 0 (+1) / > 1 (-1)', (k) => (bb.pctB[k] < 0 ? 1 : bb.pctB[k] > 1 ? -1 : 0));
    state('pctb_back', 'close back inside the Bollinger(20, 2) band (%B >= 0 (+1) / <= 1 (-1)) after a bar outside it', (k) => (prev(bb.pctB, k) < 0 && bb.pctB[k] >= 0 ? 1 : prev(bb.pctB, k) > 1 && bb.pctB[k] <= 1 ? -1 : 0));
    state('stoch_out', 'slow Stochastic 14/3/3 %K crossing up through 20 (+1) / down through 80 (-1)', (k) => (prev(sk, k) < 20 && sk[k] >= 20 ? 1 : prev(sk, k) > 80 && sk[k] <= 80 ? -1 : 0));
    state('stoch_cross', 'slow Stochastic 14/3/3 %K crossing above %D inside the 20 zone (+1) / below it inside the 80 zone (-1)', (k) => {
      const pk = prev(sk, k), pd = prev(sd, k);
      return pk <= pd && sk[k] > sd[k] && Math.min(pk, sk[k]) < 20 ? 1 : pk >= pd && sk[k] < sd[k] && Math.max(pk, sk[k]) > 80 ? -1 : 0;
    });
    state('willr', 'Williams %R(14) < -80 (+1) / > -20 (-1)', (k) => (wr[k] < -80 ? 1 : wr[k] > -20 ? -1 : 0));
    state('willr_back', 'Williams %R(14) back above -80 (+1) / below -20 (-1) after a bar beyond it', (k) => (prev(wr, k) < -80 && wr[k] >= -80 ? 1 : prev(wr, k) > -20 && wr[k] <= -20 ? -1 : 0));
    state('cci100', 'CCI(14) < -100 (+1) / > 100 (-1)', (k) => (cc[k] < -100 ? 1 : cc[k] > 100 ? -1 : 0));
    state('cci200', 'CCI(14) < -200 (+1) / > 200 (-1)', (k) => (cc[k] < -200 ? 1 : cc[k] > 200 ? -1 : 0));
    state('cci_back100', 'CCI(14) back above -100 (+1) / below 100 (-1) after a bar beyond it', (k) => (prev(cc, k) < -100 && cc[k] >= -100 ? 1 : prev(cc, k) > 100 && cc[k] <= 100 ? -1 : 0));
    // Candle reversal patterns (the bar and the one before it).
    state('engulf', 'engulfing candle', (k) => {
      if (k < 1) return 0; const p = cs[k - 1], b = cs[k];
      if (p.c < p.o && b.c > b.o && b.c >= p.o && b.o <= p.c && b.c - b.o > p.o - p.c) return 1;
      if (p.c > p.o && b.c < b.o && b.c <= p.o && b.o >= p.c && b.o - b.c > p.c - p.o) return -1;
      return 0;
    });
    state('pin', 'hammer (+1) / shooting star (-1) candle', (k) => {
      const b = cs[k], r = b.h - b.l; if (!(r > 0)) return 0;
      const body = Math.abs(b.c - b.o), lw = Math.min(b.o, b.c) - b.l, uw = b.h - Math.max(b.o, b.c);
      if (lw >= 2 * body && lw >= 0.6 * r && b.c >= b.l + (2 / 3) * r) return 1;
      if (uw >= 2 * body && uw >= 0.6 * r && b.c <= b.l + (1 / 3) * r) return -1;
      return 0;
    });
    state('key', 'key reversal bar: a new low below the previous low that closes above the previous close and its open (+1) / the mirror (-1)', (k) => {
      if (k < 1) return 0; const p = cs[k - 1], b = cs[k];
      if (b.l < p.l && b.c > p.c && b.c > b.o) return 1;
      if (b.h > p.h && b.c < p.c && b.c < b.o) return -1;
      return 0;
    });
    // Windows: 12 / 48-bar high and low (the bar itself included), distance in ATR units, bars since the extreme.
    const hi: Record<number, Float64Array> = {}, lo: Record<number, Float64Array> = {}, sh: Record<number, Int16Array> = {}, sl: Record<number, Int16Array> = {};
    for (const w of REV_WINDOWS) {
      const H = new Float64Array(K).fill(NaN), L = new Float64Array(K).fill(NaN), SH = new Int16Array(K).fill(-1), SL = new Int16Array(K).fill(-1);
      for (let k = w - 1; k < K; k++) {
        let mx = -Infinity, mn = Infinity, jh = k, jl = k;
        for (let j = k - w + 1; j <= k; j++) { if (cs[j].h >= mx) { mx = cs[j].h; jh = j; } if (cs[j].l <= mn) { mn = cs[j].l; jl = j; } }
        H[k] = mx; L[k] = mn; SH[k] = k - jh; SL[k] = k - jl;
      }
      hi[w] = H; lo[w] = L; sh[w] = SH; sl[w] = SL;
    }
    for (const w of REV_WINDOWS) {
      bucket(`dist_hi${w}`, `(${w}-bar high - close) / ATR(14): distance below the ${w}-bar high in ATR units`, DIST_NAMES, (k) => (fin(a[k]) && a[k] > 0 && fin(hi[w][k]) ? dist((hi[w][k] - c[k]) / a[k]) : -1));
      bucket(`dist_lo${w}`, `(close - ${w}-bar low) / ATR(14): distance above the ${w}-bar low in ATR units`, DIST_NAMES, (k) => (fin(a[k]) && a[k] > 0 && fin(lo[w][k]) ? dist((c[k] - lo[w][k]) / a[k]) : -1));
      bucket(`since_hi${w}`, `bars since the ${w}-bar high`, SINCE_NAMES, (k) => (sh[w][k] >= 0 ? sinceLevel(sh[w][k]) : -1));
      bucket(`since_lo${w}`, `bars since the ${w}-bar low`, SINCE_NAMES, (k) => (sl[w][k] >= 0 ? sinceLevel(sl[w][k]) : -1));
    }
    // Taker-flow spike at the extreme: volume > 2.5 x the 20-bar average of the bars before it, the bar at the 12-bar high
    // with the taker buys > 60% of its volume (-1: a buying climax) or at the 12-bar low with them < 40% (+1: a selling climax).
    const va = sma(cs.map((x) => x.v), 20);
    state('tflow_spike', 'volume spike (> 2.5 x the 20-bar average) with one-sided taker flow at the 12-bar high (-1) / low (+1)', (k) => {
      const b = cs[k]; if (k < 12 || k < 1 || b.tb === undefined || !fin(b.tb) || !(b.v > 0) || !fin(va[k - 1]) || !(b.v > 2.5 * va[k - 1])) return 0;
      const share = b.tb / b.v;
      if (b.h >= hi[12][k] && share > 0.6) return -1;
      if (b.l <= lo[12][k] && share < 0.4) return 1;
      return 0;
    });
    log(`reversal features @${m}m: ${K} bars in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  }
  // VWAP distance on 1m bars (a bar's typical price x volume; the bar itself is closed).
  {
    const t0 = Date.now(), cs = aggregate(g, 1, nMax), K = cs.length;
    const roll = new Int8Array(K).fill(-1), day = new Int8Array(K).fill(-1);
    const lvl = (x: number) => { let l = 0; for (const e of VWAP_EDGES) if (x >= e) l++; return l; };
    const vol = (b: Candle) => (fin(b.v) && b.v > 0 ? b.v : 0);
    let pv = 0, vv = 0, dpv = 0, dvv = 0, curDay = -1;
    for (let k = 0; k < K; k++) {
      const b = cs[k], tp = (b.h + b.l + b.c) / 3, v = vol(b);
      pv += tp * v; vv += v;
      if (k >= 60) { const o = cs[k - 60]; pv -= ((o.h + o.l + o.c) / 3) * vol(o); vv -= vol(o); }
      const d = Math.floor(b.ts / 86_400_000);
      if (d !== curDay) { curDay = d; dpv = 0; dvv = 0; }
      dpv += tp * v; dvv += v;
      if (k >= 59 && vv > 1e-9 && b.c > 0) roll[k] = lvl(((b.c - pv / vv) / b.c) * 1e4);
      if (dvv > 0 && b.c > 0) day[k] = lvl(((b.c - dpv / dvv) / b.c) * 1e4);
    }
    add({ name: 'rev:vwap_dist60@1m', kind: 'bucket', levels: [0, 1, 2, 3, 4], level_names: VWAP_NAMES, desc: 'rev: (close - rolling 60-minute VWAP) / close in bps on 1m spot bars (last closed bar; -1 = NA)', at: reader(roll, 1, -1) });
    add({ name: 'rev:vwap_distday@1m', kind: 'bucket', levels: [0, 1, 2, 3, 4], level_names: VWAP_NAMES, desc: 'rev: (close - UTC-day-anchored VWAP) / close in bps on 1m spot bars (last closed bar; -1 = NA)', at: reader(day, 1, -1) });
    log(`reversal features vwap: ${K} bars in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
  }
  // MA stack on 5m closes.
  {
    const cs = aggregate(g, 5, nMax), c = cs.map((x) => x.c), m9 = sma(c, 9), m50 = sma(c, 50), m100 = sma(c, 100), m200 = sma(c, 200);
    const st = new Int8Array(cs.length);
    for (let k = 0; k < cs.length; k++) {
      if (!fin(m200[k])) continue;
      st[k] = m9[k] > m50[k] && m50[k] > m100[k] && m100[k] > m200[k] ? 1 : m9[k] < m50[k] && m50[k] < m100[k] && m100[k] < m200[k] ? -1 : 0;
    }
    add({ name: 'rev:ma_stack@5m', kind: 'state', levels: [-1, 0, 1], desc: 'rev: SMA9 > SMA50 > SMA100 > SMA200 (+1) / the reverse stack (-1) on 5m spot closes (last closed bar)', at: reader(st, 5, 0) });
  }
  return out;
}
