// Synthetic fixtures for the oracle-setups exporter tests (tests/oracleExport.test.ts; SPEC.md 2a). Nothing here is
// real market data: a seeded random walk shaped like a perp TA grid (research/perpTaSweep.ts, schema perpta1), with
// occasional +-3% bursts so the +$5 take-profit at $300 (about 186 bps gross) is hit now and then, every minute valid,
// a small Kalshi-model funding rate at the 00/08/16 New York instants, and Binance-style hourly CSVs for the other coins
// so research/perpTaModules.ts modulePrims (character classifier, breadth) runs on a few days.

import fs from 'fs';
import os from 'os';
import path from 'path';
import { COLS, kalshiFundingTimes, writeGrid, type Grid } from '../perpTaSweep';
import { writeSeries } from '../../bot/marketdata/historyStore';
import type { Candle } from '../../bot/ta/indicators';

const MIN = 60_000, H = 3_600_000;

/** mulberry32: a small deterministic PRNG in [0, 1). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gauss(r: () => number): number {
  const u = Math.max(1e-12, r()), v = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

const START: Record<string, number> = { BTC: 60_000, ETH: 3_000, SOL: 150, XRP: 0.6 };

/** A deterministic synthetic grid: n minutes from t0 (a UTC midnight), spot and perp OHLC from one random walk (perp =
 *  spot x (1 + a small basis)), a burst of +-3% over 10-30 minutes about once a day, volumes with a taker-buy share,
 *  open interest, Kalshi-model funding at each instant (zero-rate instants stored as 1e-12, as buildGrid does). */
export function synthGrid(asset: string, t0: number, n: number, seed: number): Grid {
  const r = rng(seed);
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Grid['c'];
  const fundRaw = new Float32Array(n);
  let px = START[asset] ?? 100, oi = 1e5, basis = 0, burstLeft = 0, burstStep = 0;
  for (let i = 0; i < n; i++) {
    if (burstLeft === 0 && r() < 1 / 1200) { burstLeft = 10 + Math.floor(r() * 21); burstStep = ((r() < 0.5 ? -1 : 1) * 0.03) / burstLeft; }
    const drift = burstLeft > 0 ? burstStep : 0;
    if (burstLeft > 0) burstLeft--;
    const o = px, ret = drift + 0.0007 * gauss(r);
    px = o * Math.exp(ret);
    const wick = () => Math.abs(gauss(r)) * 0.0003;
    const h = Math.max(o, px) * (1 + wick()), l = Math.min(o, px) * (1 - wick());
    const v = (5 + 20 * r()) * (drift ? 4 : 1), share = Math.min(0.95, Math.max(0.05, 0.5 + 0.15 * gauss(r) + (drift > 0 ? 0.2 : drift < 0 ? -0.2 : 0)));
    c.so[i] = o; c.sh[i] = h; c.sl[i] = l; c.sc[i] = px; c.sv[i] = v; c.stb[i] = v * share;
    basis = 0.9 * basis + 0.00005 * gauss(r);
    const b = 1 + basis;
    c.po[i] = o * b; c.ph[i] = h * b * (1 + wick() * 0.2); c.pl[i] = l * b * (1 - wick() * 0.2); c.pc[i] = px * b;
    oi *= Math.exp(0.001 * gauss(r));
    c.oi[i] = oi;
    c.valid[i] = 1;
  }
  for (const tf of kalshiFundingTimes(t0 + MIN, t0 + n * MIN)) {
    const i = (tf - t0) / MIN - 1;
    if (i < 0 || i >= n) continue;
    const u = r(), rate = u < 0.6 ? 0 : u < 0.85 ? 0.00015 : -0.00012;
    c.fund[i] = rate || 1e-12; fundRaw[i] = rate + 0.0001;
  }
  return { asset, t0, n, c, fundRaw };
}

/** A fresh temporary directory (under the OS temp dir). */
export function tmpDir(tag = 'oracle-'): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), tag));
}

/** Writes the grid as <dir>/<asset>.bin (perpta1, perpTaSweep.ts writeGrid) and returns the file. */
export function writeGridTmp(g: Grid, dir = tmpDir()): string {
  const file = path.join(dir, `${g.asset}.bin`);
  writeGrid(g, file);
  return file;
}

/** Binance-style hourly spot bars for the other coins (<dir>/binance-1h/<X>/1h.csv, ts = bar open) over
 *  [from, to), random walks; plus the grid's own coin from the grid itself when `g` is given. modulePrims reads them
 *  for the character classifier and the breadth rule. Returns dir. */
export function writeOthers1h(dir: string, assets: string[], from: number, to: number, seed: number, g?: Grid): string {
  assets.forEach((a, q) => {
    if (/DOGE/i.test(a)) throw new Error('DOGE refused');
    const r = rng(seed + 17 * (q + 1));
    const cs: Candle[] = [];
    let px = START[a] ?? 100;
    for (let t = Math.ceil(from / H) * H; t + H <= to; t += H) {
      const o = px;
      px = o * Math.exp(0.006 * gauss(r));
      cs.push({ ts: t, o, h: Math.max(o, px) * (1 + 0.002 * r()), l: Math.min(o, px) * (1 - 0.002 * r()), c: px, v: 100 + 50 * r(), tb: 50 + 25 * r() });
    }
    if (g && a === g.asset) {
      cs.length = 0;
      for (let k = 0; (k + 1) * 60 <= g.n; k++) {
        const a0 = k * 60, b0 = a0 + 60;
        let h = -Infinity, l = Infinity, v = 0;
        for (let i = a0; i < b0; i++) { h = Math.max(h, g.c.sh[i]); l = Math.min(l, g.c.sl[i]); v += g.c.sv[i]; }
        cs.push({ ts: g.t0 + a0 * MIN, o: g.c.so[a0], h, l, c: g.c.sc[b0 - 1], v });
      }
    }
    writeSeries(path.join(dir, 'binance-1h', a, '1h.csv'), cs);
  });
  return dir;
}
