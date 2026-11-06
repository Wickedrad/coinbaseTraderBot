import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { aggregate, barPath, buildHistoryReplay, gkVariance, niceStep, normals, PERP_CONTRACT_SIZE, replayPerpTick, synthQuote, windowAverage } from '../research/history/historyReplay';
import { readRecordings, ReplayState, type RecEvent } from '../research/replay';
import { replaySnn } from '../research/snnReplay';
import { snnInteractions } from '../research/snnPbt';
import { buildPerpDataset } from '../research/trainPerpModel';
import { assetFeatureMap } from '../bot/model/featureEngine';
import { DEFAULT_SNN, domainParams, stageFlags, withFlags } from '../bot/snn/params';
import { tmpDir } from './helpers';

const D0 = Date.parse('2026-03-01T00:00:00Z');
const MIN = 60_000;

/** Synthetic history: 1-minute spot and perp bars for 4 days (plus 2 days before), stored higher timeframes,
 *  funding, and one Kalshi 15-minute contract per hour on the replayed days. */
function writeHistory(dir: string) {
  let x = 60000, seed = 7;
  const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296 - 0.5; };
  const spot: string[] = ['ts,o,h,l,c,v'], perp: string[] = ['ts,o,h,l,c,v'];
  const bars: Array<{ ts: number; o: number; h: number; l: number; c: number; v: number }> = [];
  for (let t = D0 - 2 * 86_400_000; t < D0 + 4 * 86_400_000; t += MIN) {
    const o = x; x *= Math.exp(0.0008 * rnd()); const c = x; const h = Math.max(o, c) * 1.0002, l = Math.min(o, c) * 0.9998;
    bars.push({ ts: t, o, h, l, c, v: 1 });
    spot.push(`${t},${o},${h},${l},${c},1`); perp.push(`${t},${o * 1.0003},${h * 1.0003},${l * 1.0003},${c * 1.0003},1`);
  }
  const put = (src: string, tf: string, lines: string[]) => { fs.mkdirSync(path.join(dir, src, 'BTC'), { recursive: true }); fs.writeFileSync(path.join(dir, src, 'BTC', `${tf}.csv`), lines.join('\n') + '\n'); };
  put('binance-1m', '1m', spot); put('binance-um', '1m', perp);
  for (const [tf, ms] of [['15m', 15 * MIN], ['1h', 60 * MIN], ['1d', 86_400_000]] as const) put('binance', tf, ['ts,o,h,l,c,v', ...aggregate(bars, ms).map((c) => `${c.ts},${c.o},${c.h},${c.l},${c.c},${c.v}`)]);
  fs.mkdirSync(path.join(dir, 'binance-funding', 'BTC'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'binance-funding', 'BTC', 'funding.csv'), `ts,rate\n${D0 - 8 * 3_600_000},0.0001\n${D0 + 8 * 3_600_000},-0.0002\n`);
  fs.mkdirSync(path.join(dir, 'kalshi', 'KXBTC15M'), { recursive: true });
  const ms: string[] = [];
  for (let h = 0; h < 24; h++) {
    const open = D0 + h * 3_600_000, close = open + 15 * MIN;
    const at = (t: number) => bars.find((b) => b.ts === t)!;
    const strike = at(open - MIN).c * 1.0004; // Kalshi's index runs 4 bp above Binance
    const candles = Array.from({ length: 15 }, (_, i) => ({ ts: open + (i + 1) * MIN, bidC: 0.45, askC: 0.48, last: 0.46, volume: 3 }));
    ms.push(JSON.stringify({ ticker: `KXBTC15M-T${h}`, series: 'KXBTC15M', openTime: open, closeTime: close, strike, cap: null, result: at(close - MIN).c * 1.0004 >= strike ? 'yes' : 'no', candles }));
  }
  fs.writeFileSync(path.join(dir, 'kalshi', 'KXBTC15M', '2026-03-01.jsonl'), ms.join('\n') + '\n');
}

test('history replay: bar paths, 60 s averages, quotes and aggregation', () => {
  // Without noise the bridge is the straight (log) line from the open toward the close at +60 s.
  assert.deepEqual(barPath({ o: 100, c: 100 }, 0, [0, 0, 0]).map((p) => p[1]), [100, 100, 100, 100]);
  const line = barPath({ o: 100, c: 110 }, 0, [0, 0, 0]);
  assert.deepEqual(line.map((p) => p[0]), [0, 15_000, 30_000, 45_000]);
  line.forEach(([t, v]) => assert.ok(Math.abs(v - 100 * Math.pow(1.1, t / 60_000)) < 1e-9));
  // On a random walk the bridge's 15 s returns add up to the real variance, and the +15 s print knows
  // the close exactly as well as a real price would (correlation sqrt(15 / 60) = 0.5), no better.
  const sigma = 1e-4;
  let seed = 3, qv = 0, gk = 0, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
  const N = 4000;
  for (let i = 0; i < N; i++) {
    const z = normals(seed++, 60);
    let x = 0, h = 0, l = 0;
    for (const w of z) { x += sigma * w; h = Math.max(h, x); l = Math.min(l, x); }
    const bar = { o: 1, h: Math.exp(h), l: Math.exp(l), c: Math.exp(x) };
    gk += gkVariance(bar);
    const p = barPath(bar, sigma * sigma, normals(1e6 + i, 3)).map((q) => Math.log(q[1]));
    p.push(x);
    for (let k = 1; k < p.length; k++) qv += (p[k] - p[k - 1]) ** 2;
    const a = p[1], b = x;
    sx += a; sy += b; sxx += a * a; syy += b * b; sxy += a * b;
  }
  const true60 = 60 * sigma * sigma;
  assert.ok(Math.abs(qv / N / true60 - 1) < 0.06, `bridge variance ${qv / N / true60}`);
  assert.ok(gk / N / true60 > 0.75 && gk / N / true60 < 1.05, `Garman-Klass ${gk / N / true60}`);
  const corr = (N * sxy - sx * sy) / Math.sqrt((N * sxx - sx * sx) * (N * syy - sy * sy));
  assert.ok(Math.abs(corr - 0.5) < 0.05, `+15 s print vs close: correlation ${corr}`);
  // Kalshi's 60 s average: one sample a second, each the last print at or before it.
  const prints: Array<[number, number]> = [[0, 10], [15_000, 11], [30_000, 12], [45_000, 13], [60_000, 14]];
  assert.ok(Math.abs(windowAverage(prints, 60_000)!.avg - (14 * 10 + 15 * 11 + 15 * 12 + 15 * 13 + 14) / 60) < 1e-12);
  assert.deepEqual(windowAverage(prints, 60_000, 30_000), { avg: (14 * 10 + 15 * 11 + 12) / 30, n: 30 }, 'observed so far');
  assert.equal(windowAverage([[0, 10]], 60_000), undefined, 'a print older than 20 s does not count');
  assert.deepEqual(synthQuote(0.5), [0.49, 0.51]);
  assert.deepEqual(synthQuote(0.995), [0.98, 0.99]);
  assert.deepEqual(synthQuote(0.0001), [0.01, 0.02]);
  assert.equal(niceStep(250), 250);
  assert.equal(niceStep(160), 200);
  assert.equal(niceStep(0.0005), 0.0005);
  const bars = Array.from({ length: 12 }, (_, i) => ({ ts: D0 + i * MIN, o: i, h: i + 1, l: i - 1, c: i + 0.5, v: 1 }));
  const five = aggregate(bars, 5 * MIN);
  assert.equal(five.length, 2, 'the incomplete third group is dropped');
  assert.deepEqual([five[0].o, five[0].h, five[0].l, five[0].c, five[0].v], [0, 5, -1, 4.5, 5]);
});

test('history replay: day files the replay reads like live recordings; the perps dataset trains on them', async () => {
  const hist = tmpDir(), out = path.join(tmpDir(), 'replay');
  writeHistory(hist);
  const r = await buildHistoryReplay({ historyDir: hist, outDir: out, assets: ['BTC', 'ETH'], fromDay: '2026-03-01', toDay: '2026-03-04', perpSpecs: { BTC: { ticker: 'KXBTCPERP', tickSize: 0.001, halfSpreadBps: 2 } }, log: () => {} });
  assert.equal(r.written, 4);
  assert.match(r.notes.join(' '), /ETH: no 1-minute spot history/);
  const again = await buildHistoryReplay({ historyDir: hist, outDir: out, assets: ['BTC'], fromDay: '2026-03-01', toDay: '2026-03-04', log: () => {} });
  assert.equal(again.skipped, 4, 'built days are not rebuilt');

  const st = new ReplayState();
  let last = 0, perps = 0, results = 0, books = 0, aliveOk = 0;
  let firstPerp: any, prev: RecEvent | undefined;
  const prints: Array<[number, number]> = [];
  const synth = new Map<string, { strike: number; openTime: number; closeTime: number; kind: string; open?: number }>();
  const synthResults: Array<{ ticker: string; result: string }> = [];
  for await (const e of readRecordings(out)) {
    assert.ok(e.t >= last, 'time order across days');
    if (prev) assert.equal(Boolean(prev.tie), prev.t === e.t, 'tie: another record of the same instant follows');
    prev = e;
    last = e.t;
    st.apply(e);
    if (e.k === 'perp') { perps++; firstPerp ??= e; }
    if (e.k === 'result' && !e.synth) results++;
    if (e.k === 'book' && !e.ticker.includes('-SYN')) books++;
    if (e.k === 'index' && e.asset === 'BTC') prints.push([e.t, e.value]);
    if (e.k === 'market' && e.synth) synth.set(e.ticker, { strike: e.strike, openTime: e.openTime, closeTime: e.closeTime, kind: e.kind });
    if (e.k === 'book' && synth.has(e.ticker) && synth.get(e.ticker)!.open === undefined) synth.get(e.ticker)!.open = (e.bids[0].price + e.asks[0].price) / 2;
    if (e.k === 'result' && e.synth) synthResults.push({ ticker: e.ticker, result: e.result });
    if (e.k === 'alive' && st.books.get(e.tickers[0])?.isUsable(e.t, 5000)) aliveOk++;
  }
  assert.equal(results, 24);
  assert.ok(books >= 24 * 14);
  assert.ok(aliveOk > 24 * 14 * 2, 'real minute quotes stand at the prints in between');
  // Synthetic contracts wherever Kalshi's history has none: every quarter hour and hourly ladders, settled by the replayed index.
  const m15 = [...synth.values()].filter((m) => m.kind === 'updown'), ladder = [...synth.values()].filter((m) => m.kind === 'greater');
  assert.equal(m15.filter((m) => m.openTime < D0 + 86_400_000).length, 96 - 24, 'day 1: the 15-minute windows Kalshi\'s history lacks');
  assert.ok(m15.length >= 96 * 4 - 24 - 1);
  assert.ok(ladder.length >= 4 * 24 * 4 - 4, `hourly ladder contracts ${ladder.length}`);
  for (const m of m15) assert.ok(Math.abs(m.strike - windowAverage(prints, m.openTime)!.avg) < 1e-6 * m.strike, 'strike: the 60 s average before the open');
  assert.ok(m15.every((m) => m.open !== undefined && m.open > 0.3 && m.open < 0.7), 'an Up/Down opens near 50c');
  assert.ok(synthResults.length > 700, `synthetic results ${synthResults.length}`);
  for (const r of synthResults) {
    const m = synth.get(r.ticker)!;
    assert.equal(r.result, windowAverage(prints, m.closeTime)!.avg >= m.strike ? 'yes' : 'no', 'settled by the real price path');
  }
  assert.equal(firstPerp.ticker, 'KXBTCPERP');
  assert.ok(firstPerp.ask > firstPerp.bid && Math.abs(firstPerp.bid / 0.001 - Math.round(firstPerp.bid / 0.001)) < 1e-6, 'quoted at the spread, on the tick');
  // Per contract, as Kalshi quotes live: BTC's contract is 0.0001 BTC (the spec carries no size: the default), the bars ~60k.
  assert.equal(firstPerp.contractSize, 0.0001);
  assert.deepEqual(PERP_CONTRACT_SIZE, { BTC: 0.0001, ETH: 0.001, SOL: 0.1, XRP: 1 }, 'the sizes the recordings show (quote over spot)');
  // The recorded tick on today's quotes; a finer one on an old day's small per-contract quote (ETH 2019, $0.15 a contract).
  assert.equal(replayPerpTick(0.001, 10, 2e-4), 0.001);
  assert.equal(replayPerpTick(0.001, 0.15, 1e-4), 1e-5);
  assert.equal(replayPerpTick(undefined, 0.15, 1e-4), undefined);
  assert.ok(firstPerp.last > 3 && firstPerp.last < 12, `per-contract quote ${firstPerp.last}`);
  assert.equal(firstPerp.fundingRate, 0.0001);
  assert.ok(st.index.get('BTC')!.vol(), 'four prints a minute: the index volatility estimator runs');
  const tfs = st.features.candles.get('BTC');
  assert.ok(tfs, 'candles reach the feature hub');
  // The basis: index prints sit ~4 bp above Binance once a contract has opened.
  const idx = st.index.get('BTC')!.latest()!.value, spot = st.spot.get('BTC')!.latest()!.value;
  assert.ok(Math.abs(idx / spot - 1.0004) < 1e-6, `basis ${idx / spot}`);
  // The perp premium reads the quote per coin: the bars sit 3 bp over spot, so about -1 bp against the index (4 bp over spot).
  const af = assetFeatureMap('BTC', st.now, { index: st.index.get('BTC'), spot: st.spot.get('BTC'), bars: st.features.bars.get('BTC'), candles: st.features.candles.get('BTC'), perp: st.features.perps.get('BTC') });
  assert.ok(Math.abs(af.perp_premium_coin_bps) < 20, `perp premium per coin ${af.perp_premium_coin_bps}`);
  assert.equal(af.perp_premium_bps, -100, 'the legacy premium reads the per-contract quote, as in live');

  const rows = await buildPerpDataset(out, { everySec: 600, horizonMin: 60 });
  assert.ok(rows.length > 300, `perp rows ${rows.length}`);
  assert.ok(rows.every((x) => Number.isFinite(x.y)));
});

test('history replay: with requote, a real contract\'s quote follows the index between its minute candles', async () => {
  const hist = tmpDir(), plain = path.join(tmpDir(), 'replay'), out = path.join(tmpDir(), 'replay');
  writeHistory(hist);
  const opts = { historyDir: hist, assets: ['BTC'], fromDay: '2026-03-01', toDay: '2026-03-01', synthetic: false, log: () => {} };
  await buildHistoryReplay({ ...opts, outDir: plain });
  await buildHistoryReplay({ ...opts, outDir: out, requote: true });
  const read = async (dir: string) => {
    const books: Array<{ t: number; ticker: string; bid: number; ask: number }> = [], ix = new Map<number, number>();
    for await (const e of readRecordings(dir)) {
      if (e.k === 'book') books.push({ t: e.t, ticker: e.ticker, bid: e.bids[0].price, ask: e.asks[0].price });
      if (e.k === 'index') ix.set(e.t, e.value);
    }
    return { books, ix };
  };
  const a = await read(plain), b = await read(out);
  const onMinute = (x: { t: number }) => x.t % MIN === 0;
  assert.ok(a.books.length >= 24 * 14 && a.books.every(onMinute), 'without requote: the candles\' quotes only');
  assert.deepEqual(b.books.filter(onMinute), a.books, 'the candles stay as they were');
  const between = b.books.filter((x) => !onMinute(x));
  assert.ok(between.length >= 24 * 14 * 3 * 0.9, `quotes between the candles: ${between.length}`);
  assert.ok(between.every((x) => Math.round((x.ask - x.bid) * 100) === 3), 'at the candle\'s spread');
  // The quote moves with the index since the candle (the candles here all quote 45c / 48c).
  let moved = 0, withIndex = 0;
  for (const x of between) {
    const t0 = Math.floor(x.t / MIN) * MIN, d = b.ix.get(x.t)! - b.ix.get(t0)!, m = (x.bid + x.ask) / 2 - 0.465;
    if (Math.abs(m) < 0.005) continue;
    moved++;
    if (Math.sign(m) === Math.sign(d)) withIndex++;
  }
  assert.ok(moved > 100 && withIndex / moved > 0.9, `moved ${moved}, with the index ${withIndex}`);
});

test('history replay: the crypto network trades the synthetic contracts', async () => {
  const hist = tmpDir(), out = path.join(tmpDir(), 'replay');
  writeHistory(hist);
  await buildHistoryReplay({ historyDir: hist, outDir: out, assets: ['BTC'], fromDay: '2026-03-01', toDay: '2026-03-02', log: () => {} });
  const params = domainParams('crypto', withFlags({ ...DEFAULT_SNN }, stageFlags('S5')));
  const from = D0 + 86_400_000 + 6 * 3_600_000;
  const r = await replaySnn(out, { params, domain: 'crypto', from, to: from + 2.5 * 3_600_000, fromDay: '2026-03-01', toDay: '2026-03-02', skipModel: true });
  const kinds = new Set(r.rows.map((x) => x.kind));
  assert.ok(kinds.has('updown') && kinds.has('greater'), `kinds ${[...kinds]}`);
  assert.ok(new Set(r.rows.map((x) => x.ticker)).size >= 8 + 4 * 2, 'every 15-minute and hourly contract of the window is scored');
  assert.ok(r.rows.every((x) => x.mid > 0 && x.mid < 1 && (x.y === 0 || x.y === 1)));
  assert.ok(r.rows.every((x) => x.pModel > 0 && x.pModel < 1), 'skipModel: p_model is the fair value');
  // The tournament's fitness: at most one bet per contract, each settled by the replayed price.
  const bets = snnInteractions(r.rows, 'crypto');
  assert.ok(bets.length <= new Set(r.rows.map((x) => x.ticker)).size);
});

test('history replay: a build that adds days continues from the saved state (same files as one build)', async () => {
  const hist = tmpDir(), a = path.join(tmpDir(), 'a'), b = path.join(tmpDir(), 'b');
  writeHistory(hist);
  const opts = { historyDir: hist, assets: ['BTC'], fromDay: '2026-03-01', log: () => {} };
  await buildHistoryReplay({ ...opts, outDir: a, toDay: '2026-03-02' });
  const more = await buildHistoryReplay({ ...opts, outDir: a, toDay: '2026-03-04' });
  assert.deepEqual([more.written, more.skipped], [2, 2]);
  await buildHistoryReplay({ ...opts, outDir: b, toDay: '2026-03-04' });
  const read = (dir: string, d: string) => zlib.gunzipSync(fs.readFileSync(path.join(dir, `md-${d}.jsonl.gz`))).toString();
  for (const d of ['2026-03-02', '2026-03-03', '2026-03-04']) assert.ok(read(a, d) === read(b, d), `${d}: identical`);
  // Kalshi data arriving later for a day rebuilds it and the day before (whose contracts can close on it),
  // from the kept end state of the day before that.
  const open = Date.parse('2026-03-03T23:45:00Z');
  fs.writeFileSync(path.join(hist, 'kalshi', 'KXBTC15M', '2026-03-04.jsonl'), JSON.stringify({ ticker: 'KXBTC15M-LATE', series: 'KXBTC15M', openTime: open, closeTime: open + 15 * MIN, strike: 60000, cap: null, result: 'yes', candles: [{ ts: open + MIN, bidC: 0.4, askC: 0.43, last: 0.41, volume: 2 }] }) + '\n');
  const late = await buildHistoryReplay({ ...opts, outDir: a, toDay: '2026-03-04' });
  assert.deepEqual([late.written, late.skipped], [2, 2], 'days 3 and 4 rebuilt, days 1 and 2 not');
  const c = path.join(tmpDir(), 'c');
  await buildHistoryReplay({ ...opts, outDir: c, toDay: '2026-03-04' });
  for (const d of ['2026-03-03', '2026-03-04']) assert.ok(read(a, d) === read(c, d), `${d}: identical after the late data`);
  assert.match(read(a, '2026-03-03'), /KXBTC15M-LATE/);
});

test('history replay: a walk block built in a new folder from the end state the walk carried matches one long build', async () => {
  const hist = tmpDir(), one = path.join(tmpDir(), 'one'), b1 = path.join(tmpDir(), 'b1'), b2 = path.join(tmpDir(), 'b2');
  writeHistory(hist);
  const opts = { historyDir: hist, assets: ['BTC'], log: () => {} };
  await buildHistoryReplay({ ...opts, outDir: one, fromDay: '2026-03-01', toDay: '2026-03-04' });
  // Block 1 (warm-up day 03-01, then 03-02 and 03-03) keeps every day's end state; walked to 03-04, the walk carries
  // only the end of 03-02 to the next block, which warms up on 03-03.
  await buildHistoryReplay({ ...opts, outDir: b1, fromDay: '2026-03-01', toDay: '2026-03-03', keepAllStates: true });
  assert.deepEqual(fs.readdirSync(path.join(b1, 'replay-states')).sort(), ['2026-03-01.json.gz', '2026-03-02.json.gz', '2026-03-03.json.gz']);
  fs.mkdirSync(path.join(b2, 'replay-states'), { recursive: true });
  fs.copyFileSync(path.join(b1, 'replay-states', '2026-03-02.json.gz'), path.join(b2, 'replay-states', '2026-03-02.json.gz'));
  const next = await buildHistoryReplay({ ...opts, outDir: b2, fromDay: '2026-03-03', toDay: '2026-03-04', keepAllStates: true });
  assert.deepEqual([next.resumed, next.written], ['2026-03-02', 2]);
  const read = (dir: string, d: string) => zlib.gunzipSync(fs.readFileSync(path.join(dir, `md-${d}.jsonl.gz`))).toString();
  for (const d of ['2026-03-03', '2026-03-04']) assert.ok(read(b2, d) === read(one, d), `${d}: the same day as in one build`);
});

test('history replay: the catalog picks ladder strikes by the index without requote, and after midnight too', async () => {
  const hist = tmpDir(), out = path.join(tmpDir(), 'replay');
  writeHistory(hist);
  const open = new Map<number, number>();
  for (const l of fs.readFileSync(path.join(hist, 'binance-1m', 'BTC', '1m.csv'), 'utf8').split('\n').slice(1)) { const f = l.split(',').map(Number); if (f[0] > 0) open.set(f[0], f[1]); }
  const STEP = 250;
  // An event's ladder, centred off the index: strikes k = -2..9 steps from the index at `at`, wide (1c / 99c) quotes
  // except an optional lone tight in-band quote at strike `lone`.
  const ladder = (name: string, openT: number, closeT: number, at: number, lone?: number) => {
    const p0 = Math.round((open.get(at)! * 1.0004) / 10) * 10;
    return Array.from({ length: 12 }, (_, i) => {
      const k = i - 2, strike = p0 + k * STEP;
      const candles = [];
      for (let t = openT + MIN; t <= closeT; t += MIN) candles.push(k === lone ? { ts: t, bidC: 0.45, askC: 0.47, last: 0.46, volume: 1 } : { ts: t, bidC: 0.01, askC: 0.99, last: null, volume: 0 });
      return { k, line: JSON.stringify({ ticker: `${name}-T${strike}`, series: 'KXBTCD', event: name, openTime: openT, closeTime: closeT, strike, cap: null, strikeType: 'greater', result: 'no', candles }) };
    });
  };
  const H = 3_600_000;
  const day = ladder('KXBTCD-26MAR0112', D0 + 10 * H, D0 + 12 * H, D0 + 10.5 * H, 8);            // picked at 10:30 UTC
  const night = ladder('KXBTCD-26MAR0202', D0 + 23 * H, D0 + 26 * H, D0 + 24.5 * H);             // picked at 00:30 UTC the next day
  fs.mkdirSync(path.join(hist, 'kalshi', 'KXBTCD'), { recursive: true });
  fs.writeFileSync(path.join(hist, 'kalshi', 'KXBTCD', '2026-03-01.jsonl'), [...day, ...night].map((x) => x.line).join('\n') + '\n');
  await buildHistoryReplay({ historyDir: hist, outDir: out, assets: ['BTC'], fromDay: '2026-03-01', toDay: '2026-03-02', synthetic: false, log: () => {} });
  const first = new Map<string, number>();
  for await (const e of readRecordings(out)) if (e.k === 'market' && !(e as { recordOnly?: boolean }).recordOnly && /^KXBTCD/.test(e.ticker) && !first.has(e.ticker)) first.set(e.ticker, e.t);
  const pickedAt = (xs: typeof day, t0: number) => xs.filter((x) => first.get(JSON.parse(x.line).ticker) === Math.min(...xs.map((y) => first.get(JSON.parse(y.line).ticker) ?? Infinity)) && first.get(JSON.parse(x.line).ticker)! <= t0 + MIN).map((x) => x.k).sort((a, b) => a - b);
  // Same day: the index decides, not the lone tight quote eight steps up.
  const a = pickedAt(day, D0 + 10.5 * H);
  assert.ok(a.length === 4 && a.includes(0) && !a.includes(8), `same-day picks ${a}`);
  // After midnight: still the index (not the ladder's middle, three to four steps up).
  const b = pickedAt(night, D0 + 24.5 * H);
  assert.ok(b.length === 4 && b.includes(0) && !b.includes(5), `after-midnight picks ${b}`);
});
