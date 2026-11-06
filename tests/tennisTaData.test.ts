import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { recordingFiles, recordingLines } from '../bot/marketdata/recordingFiles';
import { buildHistoryReplay } from '../research/history/historyReplay';
import {
  BEAT_KIND, BEAT_MS, BEAT_PAUSE_MS, CUT_VERSION, SOCKET_BEAT, inventory, matchSeriesTest, matchTime, recordedTennis, startEraWeek,
  weekEdge, weekOf, type WeekRow,
} from '../research/tennisTaData';
import { FEED_SILENCE_MS, HEARTBEAT_KIND, SOCKET_BEAT_KIND, feedTimeline } from '../research/tennisTaSim';
import { CHECK_FROM, HISTORY_FROM, LOCKBOX_FROM, START_ERA_FROM, mondayEdge } from '../research/tennisTaSweep';

const DAY = 86_400_000, H = 3_600_000, MIN = 60_000;
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'tta-data-'));

const TEN = 'KXATPMATCH-26NOV04SINALC-SIN'; // listed the day before: no market line in this day's file
const TEN2 = 'KXATPMATCH-26NOV04SINALC-ALC';
const NEW = 'KXATPMATCH-26NOV05DJOMED-DJO'; // listed today
const BTC = 'KXBTCD-26NOV0517-T97000';
const T0 = Date.parse('2026-11-05T00:00:00Z');

/** A recorded day as the bot's Recorder writes it: {"t":..,"k":..,...data} lines, gzipped. */
function writeDay(dir: string, day: string, lines: Array<Record<string, unknown>>): string {
  fs.mkdirSync(dir, { recursive: true });
  const f = path.join(dir, `md-${day}.jsonl.gz`);
  fs.writeFileSync(f, zlib.gzipSync(lines.map((l) => JSON.stringify(l)).join('\n') + '\n'));
  return f;
}
async function readAll(file: string): Promise<any[]> {
  const out: any[] = [];
  for await (const l of recordingLines(file)) if (l) out.push(JSON.parse(l));
  return out;
}

test('the cut keeps a tennis match\'s lines on a day without its market line and drops crypto, prices and SNN lines', async () => {
  const d = tmp();
  const src: Array<Record<string, unknown>> = [
    { t: T0 + 1000, k: 'market', ticker: BTC, series: 'KXBTCD', asset: 'BTC', kind: 'greater', event: 'KXBTCD-26NOV0517' },
    { t: T0 + 1100, k: 'book', ticker: TEN, bids: [[0.55, 10]], asks: [[0.57, 12]], ts: T0 + 1100 },
    { t: T0 + 1200, k: 'book', ticker: BTC, bids: [[0.4, 5]], asks: [[0.42, 5]], ts: T0 + 1200 },
    { t: T0 + 1300, k: 'delta', ticker: TEN, side: 'yes', price: 0.55, delta: -3, ts: T0 + 1300 },
    { t: T0 + 1400, k: 'trade', ticker: TEN2, price: 0.44, count: 2, takerSide: 'no', ts: T0 + 1400 },
    { t: T0 + 1500, k: 'spot', asset: 'BTC', price: 97_100 },
    { t: T0 + 1600, k: 'snn', ticker: BTC, p: 0.4 },
    { t: T0 + 1700, k: 'tennis_score', event: 'KXATPMATCH-26NOV04SINALC', sets: [6, 4] },
    { t: T0 + 1800, k: 'alive', tickers: [BTC, TEN] },
    { t: T0 + 1900, k: 'alive', tickers: [BTC] },
    { t: T0 + 2000, k: 'market', ticker: NEW, series: 'KXATPMATCH', asset: 'TENNIS', kind: 'match', event: 'KXATPMATCH-26NOV05DJOMED', startTime: T0 + 6 * H },
    { t: T0 + 2100, k: 'book', ticker: NEW, bids: [[0.6, 1]], asks: [[0.62, 1]], ts: T0 + 2100 },
    { t: T0 + 2200, k: 'delta', ticker: BTC, side: 'no', price: 0.58, delta: 4, ts: T0 + 2200 },
    { t: T0 + 2300, k: 'lifecycle', ticker: TEN, event: 'determined', result: 'yes', ts: T0 + 2300 },
    { t: T0 + 2400, k: 'result', ticker: TEN, result: 'yes' },
    { t: T0 + 2500, k: 'result', ticker: BTC, result: 'no' },
  ];
  const inF = writeDay(path.join(d, 'rec'), '2026-11-05', src);
  const outF = path.join(d, 'cut', 'md-2026-11-05.jsonl.gz');
  const r = await recordedTennis(inF, outF);
  const got = await readAll(outF);
  const data = got.filter((l) => l.k !== HEARTBEAT_KIND && l.k !== SOCKET_BEAT_KIND);
  assert.deepEqual(data.map((l) => `${l.k}:${l.ticker ?? l.event ?? (l.tickers ?? []).join('+')}`), [
    `book:${TEN}`, `delta:${TEN}`, `trade:${TEN2}`, 'tennis_score:KXATPMATCH-26NOV04SINALC', `alive:${BTC}+${TEN}`,
    `market:${NEW}`, `book:${NEW}`, `lifecycle:${TEN}`, `result:${TEN}`,
  ]);
  // Lines are copied byte for byte.
  assert.deepEqual(data[0], src[1]);
  assert.ok(!got.some((l) => l.ticker === BTC || l.k === 'spot' || l.k === 'snn'), 'crypto, price and SNN lines dropped');
  // Beats: the first source line (a crypto market line) and the file's last line. No ws_beat: every crypto socket line
  // comes within 5 s of a tennis one and right before the next (the tennis socket lines mark the socket themselves).
  assert.deepEqual(r, { cut: CUT_VERSION, lines: src.length, kept: got.length, beats: 2, sockBeats: 0, matches: 3, carried: 2, markets: 1, scores: 1 });
  assert.deepEqual(got[0], { t: T0 + 1000, k: 'beat' }, 'the first source line (a crypto market line) starts the beat');
  assert.deepEqual(got[got.length - 1], { t: T0 + 2500, k: 'beat' }, 'the last source line is marked');
});

test('the beat kinds are the ones the sim reads', () => {
  assert.equal(BEAT_KIND, HEARTBEAT_KIND);
  assert.equal(SOCKET_BEAT, SOCKET_BEAT_KIND);
});

/** Consecutive gaps over `min` of a sorted list of times, as [from, to] relative to T0. */
const longGaps = (ts: number[], min: number) => ts.slice(1).map((t, i) => [ts[i] - T0, t - T0]).filter(([a, b]) => b - a > min);
/** Every beat gap is under BEAT_MS + BEAT_PAUSE_MS, or the gap between two consecutive source times. */
function assertBeatGaps(beats: number[], source: number[], what: string): void {
  const src = [...new Set(source)].sort((a, b) => a - b);
  const next = new Map(src.map((t, i) => [t, src[i + 1]]));
  for (let i = 1; i < beats.length; i++) {
    const a = beats[i - 1], b = beats[i];
    if (b - a < BEAT_MS + BEAT_PAUSE_MS) continue;
    assert.equal(next.get(a), b, `${what} beats ${a - T0} and ${b - T0} are ${b - a} ms apart, not two consecutive source lines`);
  }
}

test('the cut writes a beat at most once per 5 s of any source line, so the sim reads the feed\'s silences and not tennis lulls', async () => {
  const d = tmp();
  const src: Array<Record<string, unknown>> = [];
  // 0..60 s: crypto deltas every 700 ms, tennis quiet after its first book (a lull inside a live feed: no outage).
  src.push({ t: T0, k: 'market', ticker: TEN, series: 'KXATPMATCH', kind: 'match', event: 'KXATPMATCH-26NOV04SINALC' });
  src.push({ t: T0 + 10, k: 'book', ticker: TEN, bids: [[0.5, 1]], asks: [[0.52, 1]] });
  for (let t = T0 + 700; t <= T0 + 60_000; t += 700) src.push({ t, k: 'delta', ticker: BTC, side: 'yes', price: 0.4, delta: 1 });
  // 60..90 s: nothing at all (the socket fell silent), then crypto and Coinbase spot lines again to 120 s.
  for (let t = T0 + 90_000, i = 0; t <= T0 + 120_000; t += 900, i++) src.push(i % 2 ? { t, k: 'spot', asset: 'BTC', price: 97_000 } : { t, k: 'delta', ticker: BTC, side: 'no', price: 0.6, delta: 1 });
  src.push({ t: T0 + 120_500, k: 'trade', ticker: TEN, price: 0.5, count: 1, takerSide: 'yes' });
  const rec = path.join(d, 'rec'), cut = path.join(d, 'cut');
  const r = await recordedTennis(writeDay(rec, '2026-11-05', src), path.join(cut, 'md-2026-11-05.jsonl.gz'));
  const got = await readAll(path.join(cut, 'md-2026-11-05.jsonl.gz'));
  const beats = got.filter((l) => l.k === HEARTBEAT_KIND).map((l) => l.t);
  const sockBeats = got.filter((l) => l.k === SOCKET_BEAT_KIND).map((l) => l.t);
  assert.equal(r.beats, beats.length);
  assert.equal(r.sockBeats, sockBeats.length);
  assert.ok(got.every((l, i) => !i || l.t >= got[i - 1].t), 'the cut is in time order');
  // At most two beats per BEAT_MS (the due one and the line before a pause), each at a source line's time.
  for (let i = 2; i < beats.length; i++) assert.ok(beats[i] - beats[i - 2] >= BEAT_MS, `three beats within ${BEAT_MS} ms at ${beats[i] - T0}`);
  assert.ok(beats.every((t) => src.some((l) => l.t === t)), 'each beat is stamped with a source line\'s time');
  const sock = src.filter((l) => ['book', 'delta', 'trade', 'lifecycle'].includes(l.k as string)).map((l) => l.t as number);
  assert.ok(sockBeats.every((t) => sock.includes(t)), 'each ws_beat is stamped with a socket line\'s time');
  assertBeatGaps(beats, src.map((l) => l.t as number), 'source');
  // The socket's marks: its kept (tennis) lines and the ws_beats.
  const marks = got.filter((l) => l.k === SOCKET_BEAT_KIND || (l.k !== HEARTBEAT_KIND && sock.includes(l.t))).map((l) => l.t);
  assertBeatGaps(marks, sock, 'socket');
  // The 30.5 s silence is in both clocks exactly as in the source: from its last line (59.5 s) to its next (90 s).
  assert.deepEqual(longGaps(beats, FEED_SILENCE_MS), [[59_500, 90_000]]);
  assert.deepEqual(longGaps(marks, FEED_SILENCE_MS), [[59_500, 90_000]]);
  // The sim's pre-pass on the cut: a day that shows liveness, one outage (the silence), dated as on the raw file, and no
  // outage in the tennis lull.
  const tl = await feedTimeline(cut, '2026-11-05', '2026-11-05');
  assert.deepEqual(tl.liveDays, ['2026-11-05']);
  assert.deepEqual(tl.blindDays, []);
  assert.deepEqual(tl.gaps.map((g) => [g.from - T0, g.to - T0, g.blind]), [[59_500, 90_000, false]]);
  assert.deepEqual(tl.gaps, (await feedTimeline(rec, '2026-11-05', '2026-11-05')).gaps);
});

test('a source silence under 12 s that starts up to 5 s after a beat is no outage on the cut (the line before it is marked)', async () => {
  for (const pause of [9_000, 10_000, 11_000, 11_900]) {
    const d = tmp();
    const src: Array<Record<string, unknown>> = [{ t: T0, k: 'book', ticker: TEN, bids: [[0.5, 1]], asks: [[0.52, 1]] }];
    // Crypto deltas and spot lines every 100 ms; the beats fall at 0, 5, 10, 15 s, ...; the last line before the pause
    // comes 4.9 s after the beat at 15 s, so the next beat would come 4.9 s + pause after it.
    const stop = T0 + 19_900;
    for (let t = T0 + 100; t <= T0 + 60_000; t += 100) {
      if (t > stop && t < stop + pause) continue;
      src.push(t % 200 ? { t, k: 'spot', asset: 'BTC', price: 97_000 } : { t, k: 'delta', ticker: BTC, side: 'yes', price: 0.4, delta: 1 });
    }
    // The socket line before the pause is the delta at 19.8 s; its silence is pause + 100 ms (at most 12 s: no outage).
    const rec = path.join(d, 'rec'), cut = path.join(d, 'cut');
    await recordedTennis(writeDay(rec, '2026-11-05', src), path.join(cut, 'md-2026-11-05.jsonl.gz'));
    const got = await readAll(path.join(cut, 'md-2026-11-05.jsonl.gz'));
    const beats = got.filter((l) => l.k === HEARTBEAT_KIND).map((l) => l.t);
    assert.ok(beats.includes(stop), `pause ${pause}: the line before the pause is marked`);
    assert.deepEqual(longGaps(beats, BEAT_MS + BEAT_PAUSE_MS), [[stop - T0, stop + pause - T0]], `pause ${pause}`);
    const tl = await feedTimeline(cut, '2026-11-05', '2026-11-05');
    assert.deepEqual(tl.gaps, [], `pause ${pause}: no outage on the cut`);
    assert.deepEqual((await feedTimeline(rec, '2026-11-05', '2026-11-05')).gaps, [], `pause ${pause}: none on the raw file`);
  }
});

test('a Kalshi socket silence while Coinbase goes on is an outage on the cut as on the raw file, dated from the socket\'s last line', async () => {
  const d = tmp();
  const BTC2 = 'KXBTCD-26NOV0517-T98000';
  const src: Array<Record<string, unknown>> = [];
  // The tennis books are snapshotted an hour before; then only crypto socket lines and spot lines until the reconnect.
  src.push({ t: T0, k: 'book', ticker: BTC, bids: [[0.4, 1]], asks: [[0.42, 1]] }, { t: T0 + 10, k: 'book', ticker: BTC2, bids: [[0.3, 1]], asks: [[0.32, 1]] });
  src.push({ t: T0 + 20, k: 'book', ticker: TEN, bids: [[0.5, 1]], asks: [[0.52, 1]] }, { t: T0 + 30, k: 'book', ticker: TEN2, bids: [[0.48, 1]], asks: [[0.5, 1]] });
  const down = T0 + H, up = down + 15_000;
  for (let t = T0 + 700; t < up + 60_000; t += 700) if (t < down || t >= up) src.push({ t, k: 'delta', ticker: BTC, side: 'yes', price: 0.4, delta: 1 });
  for (let t = T0 + 350; t < up + 60_000; t += 1000) src.push({ t, k: 'spot', asset: 'BTC', price: 97_000 });
  // The resubscribe re-snapshots every book.
  for (const [i, tk] of [BTC, BTC2, TEN, TEN2].entries()) src.push({ t: up + 1 + i * 50, k: 'book', ticker: tk, bids: [[0.45, 1]], asks: [[0.47, 1]] });
  src.sort((a, b) => (a.t as number) - (b.t as number));
  const lastSock = Math.max(...src.filter((l) => l.k === 'delta' && (l.t as number) < down).map((l) => l.t as number));
  const firstSock = Math.min(...src.filter((l) => (l.k === 'delta' || l.k === 'book') && (l.t as number) >= up).map((l) => l.t as number));
  const rec = path.join(d, 'rec'), cut = path.join(d, 'cut');
  await recordedTennis(writeDay(rec, '2026-11-05', src), path.join(cut, 'md-2026-11-05.jsonl.gz'));
  const raw = await feedTimeline(rec, '2026-11-05', '2026-11-05');
  assert.deepEqual(raw.gaps.map((g) => [g.from - T0, g.to - T0, g.blind]), [[lastSock - T0, firstSock - T0, false]]);
  const tl = await feedTimeline(cut, '2026-11-05', '2026-11-05');
  assert.deepEqual(tl.gaps, raw.gaps, 'the cut shows the socket silence itself (not a blind outage back to the last tennis line)');
});

/** A seeded random feed: crypto socket lines (dense or sparse), Coinbase spot each second, tennis socket and score lines,
 *  stalls of the whole recorder (3-17 s) and of the Kalshi socket alone (3-28 s). */
function randomFeed(seed: number, from: number, hours: number): Array<Record<string, unknown>> {
  let s = seed;
  const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  const end = from + hours * H, out: Array<Record<string, unknown>> = [];
  const all: Array<[number, number]> = [], sockOnly: Array<[number, number]> = [];
  for (let t = from; t < end; t += 20_000 + rnd() * 200_000) all.push([t, t + 3000 + rnd() * 14_000]);
  for (let t = from; t < end; t += 60_000 + rnd() * 600_000) sockOnly.push([t, t + 3000 + rnd() * 25_000]);
  const off = (t: number, xs: Array<[number, number]>) => xs.some(([a, b]) => t >= a && t < b);
  const step = rnd() < 0.5 ? 150 : 1200;
  for (let t = from + rnd() * 500; t < end; t += rnd() * step) if (!off(t, all) && !off(t, sockOnly)) out.push({ t: Math.round(t), k: 'delta', ticker: BTC, side: 'yes', price: 0.4, delta: 1 });
  for (let t = from + 300; t < end; t += 900 + rnd() * 200) if (!off(t, all)) out.push({ t: Math.round(t), k: 'spot', asset: 'BTC', price: 97_000 });
  for (let t = from + 50; t < end; t += rnd() * 20_000) if (!off(t, all) && !off(t, sockOnly)) out.push({ t: Math.round(t), k: rnd() < 0.5 ? 'delta' : 'trade', ticker: TEN, price: 0.5 });
  for (let t = from + 70; t < end; t += rnd() * 30_000) if (!off(t, all)) out.push({ t: Math.round(t), k: 'tennis_score', event: 'KXATPMATCH-26NOV04SINALC' });
  return out.sort((a, b) => (a.t as number) - (b.t as number));
}

test('on random feeds across midnight the sim finds the same outages on the cut as on the raw file', async () => {
  for (const seed of [1, 7, 42, 20261105]) {
    const d = tmp(), rec = path.join(d, 'rec'), cut = path.join(d, 'cut');
    const src = randomFeed(seed, Date.parse('2026-11-04T23:00:00Z'), 2);
    for (const day of ['2026-11-04', '2026-11-05']) {
      const f = writeDay(rec, day, src.filter((l) => new Date(l.t as number).toISOString().slice(0, 10) === day));
      await recordedTennis(f, path.join(cut, path.basename(f)));
      const got = await readAll(path.join(cut, path.basename(f)));
      assert.ok(got.every((l, i) => !i || l.t >= got[i - 1].t), `seed ${seed} ${day}: the cut is in time order`);
    }
    const raw = await feedTimeline(rec, '2026-11-04', '2026-11-05');
    const tl = await feedTimeline(cut, '2026-11-04', '2026-11-05');
    assert.ok(raw.gaps.length > 5, `seed ${seed}: the feed has outages (${raw.gaps.length})`);
    assert.deepEqual(tl.gaps, raw.gaps, `seed ${seed}`);
  }
});

test('the cut rejects when its file cannot be written (the CLI then exits 1, not 0 with a truncated cut)', async () => {
  const d = tmp();
  const src: Array<Record<string, unknown>> = [];
  for (let i = 0; i < 40_000; i++) src.push({ t: T0 + i * 100, k: 'delta', ticker: TEN, side: 'yes', price: (i * 7919) % 97 / 100, delta: (i * 104729) % 1013 });
  const inF = writeDay(path.join(d, 'rec'), '2026-11-05', src);
  const outDir = path.join(d, 'cut', 'md-2026-11-05.jsonl.gz');
  fs.mkdirSync(outDir, { recursive: true }); // a directory where the file should go: the write stream fails (EISDIR)
  await assert.rejects(recordedTennis(inF, outDir), /EISDIR/);
});

test('the cut restarts the beat clock after a clock step back, reads plain day files, and keeps no beat lines it is given', async () => {
  const d = tmp();
  const f = path.join(d, 'md-2026-11-05.jsonl');
  const ls = [
    { t: T0 + 100_000, k: 'delta', ticker: BTC },
    { t: T0 + 100_000, k: 'beat' },
    { t: T0 + 102_000, k: 'delta', ticker: BTC },
    { t: T0 + 40_000, k: 'delta', ticker: BTC }, // the clock stepped back a minute
    { t: T0 + 41_000, k: 'book', ticker: TEN },
    { t: T0 + 46_000, k: 'delta', ticker: BTC },
  ];
  fs.writeFileSync(f, ls.map((l) => JSON.stringify(l)).join('\n') + '\n{"t":12,"k":"bo');
  const r = await recordedTennis(f, path.join(d, 'out', 'md-2026-11-05.jsonl.gz'));
  const got = await readAll(path.join(d, 'out', 'md-2026-11-05.jsonl.gz'));
  // The step back restarts both clocks (a beat and a ws_beat at 40 s); at 46 s the beat comes due after a 5 s pause of
  // the source, so its line before (the tennis book at 41 s) is marked too; the tennis book marks the socket itself.
  assert.deepEqual(got.map((l) => [l.k, l.t - T0]), [
    ['beat', 100_000], ['ws_beat', 100_000], ['beat', 40_000], ['ws_beat', 40_000], ['book', 41_000], ['beat', 41_000], ['beat', 46_000], ['ws_beat', 46_000],
  ]);
  assert.equal(r.lines, ls.length + 1);
  assert.equal(r.carried, 1);
});

test('tennis match series are the prefix before the first dash with contractKind match', () => {
  const m = matchSeriesTest();
  assert.equal(m(TEN), true);
  assert.equal(m('KXATPMATCH'), false, 'a bare series is no ticker');
  assert.equal(m(BTC), false);
  assert.equal(m('KXBTC15M-26NOV0517-17'), false);
  assert.equal(m(''), false);
});

// ---------------------------------------------------------------------------------------------------------------------
// Weekly inventory

test('unit weeks start Monday 05:00 UTC, as the sweep\'s units do', () => {
  const mon = Date.parse('2026-04-27T05:00:00Z');
  assert.equal(weekOf(mon), '2026-04-27');
  assert.equal(weekOf(mon - 1), '2026-04-20');
  assert.equal(weekOf(mon - 5 * H), '2026-04-20', 'Monday 00:00 UTC is still the week before');
  assert.equal(weekOf(mon + 7 * DAY - 1), '2026-04-27');
  assert.equal(weekOf(mon + 7 * DAY), '2026-05-04');
  assert.equal(weekEdge(START_ERA_FROM), START_ERA_FROM, 'START_ERA_FROM is a week edge');
  assert.equal(weekEdge(CHECK_FROM), CHECK_FROM, 'CHECK_FROM is a week edge');
  // The same edge as research/tennisTaSweep.ts mondayEdge, everywhere over the history.
  for (let t = HISTORY_FROM - 9 * DAY, i = 0; t < LOCKBOX_FROM + 30 * DAY; t += 3 * H + 17 * MIN + 1234, i++) assert.equal(weekEdge(t), mondayEdge(t), new Date(t).toISOString());
});

type Mk = { ticker: string; event?: string; openTime: number; closeTime: number; startTime?: number; candles: Array<Record<string, unknown>>; volume?: number; result?: string };
const candle = (ts: number) => ({ ts, bidO: 0.5, bidH: 0.5, bidL: 0.5, bidC: 0.5, askO: 0.52, askH: 0.52, askL: 0.52, askC: 0.52, last: 0.51, volume: 10, oi: 10 });
function writeHist(dir: string, series: string, markets: Mk[], trades: Array<{ ticker: string; closeTime: number; n: number }> = []): void {
  fs.mkdirSync(path.join(dir, series, 'trades'), { recursive: true });
  for (const m of markets) fs.appendFileSync(path.join(dir, series, `${new Date(m.closeTime).toISOString().slice(0, 10)}.jsonl`), JSON.stringify({ series, strike: null, cap: null, result: 'yes', volume: 100, ...m }) + '\n');
  for (const t of trades) fs.appendFileSync(path.join(dir, series, 'trades', `${new Date(t.closeTime).toISOString().slice(0, 10)}.jsonl`), JSON.stringify({ ticker: t.ticker, trades: Array.from({ length: t.n }, (_, i) => ({ ts: t.closeTime - i * 1000, price: 0.5, count: 1 })) }) + '\n');
}

test('the weekly inventory counts markets, events, two-sided events and published starts per unit week, across close-day files', () => {
  const d = tmp();
  const edge = Date.parse('2026-04-27T05:00:00Z');
  // startB: the second market's start (null: none; left out: the first's).
  const two = (ev: string, start: number | undefined, first: number, close: number, startB?: number | null): Mk[] => {
    const b = startB === undefined ? start : startB ?? undefined;
    return [
      { ticker: `${ev}-AAA`, event: ev, openTime: first - DAY, closeTime: close, ...(start !== undefined ? { startTime: start } : {}), candles: [candle(first), candle(first + MIN)] },
      { ticker: `${ev}-BBB`, event: ev, openTime: first - DAY, closeTime: close, ...(b !== undefined ? { startTime: b } : {}), candles: [candle(first)] },
    ];
  };
  const ms: Mk[] = [
    // A: published start 1 s before the edge: the week before.
    ...two('KXATPMATCH-26APR27AAABBB', edge - 1000, edge - H, edge + 3 * H),
    // B: published start on the edge.
    ...two('KXATPMATCH-26APR27CCCDDD', edge, edge - H, edge + 3 * H),
    // C: no published start, first candle 20 min after the edge: listed 30 min before it, the week before.
    ...two('KXATPMATCH-26APR27EEEFFF', undefined, edge + 20 * MIN, edge + 4 * H),
    // D: one-sided, with a start.
    { ticker: 'KXATPMATCH-26APR28GGGHHH-GGG', event: 'KXATPMATCH-26APR28GGGHHH', openTime: edge, closeTime: edge + DAY + 3 * H, startTime: edge + DAY, candles: [candle(edge + DAY)] },
    // E: two-sided, one market without a start, the two closing on different days (two close-day files).
    ...two('KXATPMATCH-26APR29IIIJJJ', edge + 2 * DAY + 20 * H, edge + 2 * DAY + 19 * H, edge + 2 * DAY + 22 * H, null).map((m, i) => ({ ...m, closeTime: m.closeTime + i * 3 * H })),
    // No candles: left out.
    { ticker: 'KXATPMATCH-26APR29KKKLLL-KKK', event: 'KXATPMATCH-26APR29KKKLLL', openTime: edge, closeTime: edge + 2 * DAY, startTime: edge + DAY, candles: [] },
  ];
  writeHist(d, 'KXATPMATCH', ms, [{ ticker: 'KXATPMATCH-26APR27CCCDDD-AAA', closeTime: edge + 3 * H, n: 5 }]);
  writeHist(d, 'KXWTAMATCH', two('KXWTAMATCH-26MAY05MMMNNN', edge + 8 * DAY, edge + 8 * DAY - H, edge + 8 * DAY + 2 * H));
  const inv = inventory(d, ['KXATPMATCH', 'KXWTAMATCH', 'KXNOPE']);
  assert.deepEqual(inv.weeks, [
    { series: 'KXATPMATCH', week: '2026-04-20', markets: 4, events: 2, twoSided: 2, withStart: 1, noStart: 2 },
    { series: 'KXATPMATCH', week: '2026-04-27', markets: 5, events: 3, twoSided: 2, withStart: 1, noStart: 1 },
    { series: 'KXWTAMATCH', week: '2026-05-04', markets: 2, events: 1, twoSided: 1, withStart: 1, noStart: 0 },
  ] satisfies WeekRow[]);
  // The weeks and the months count the same markets, and the totals agree.
  for (const s of ['KXATPMATCH', 'KXWTAMATCH']) {
    const w = inv.weeks.filter((r) => r.series === s), m = inv.months.filter((r) => r.series === s);
    const sum = (xs: Array<{ markets: number; noStart: number }>, k: 'markets' | 'noStart') => xs.reduce((a, x) => a + x[k], 0);
    assert.equal(sum(w, 'markets'), inv.totals[s].markets);
    assert.equal(sum(m, 'markets'), inv.totals[s].markets);
    assert.equal(sum(w, 'noStart'), inv.totals[s].noStart);
    assert.equal(w.reduce((a, x) => a + x.events, 0), inv.totals[s].events);
  }
  assert.equal(inv.totals.KXATPMATCH.markets, 9);
  assert.equal(inv.totals.KXATPMATCH.startEraWeek, undefined, 'the last week falls short of 95%');
  assert.equal(inv.totals.KXWTAMATCH.startEraWeek, '2026-05-04');
  assert.deepEqual(inv.totals.KXNOPE, { markets: 0, events: 0, noStart: 0, first: undefined, last: undefined });
  assert.equal(inv.months.find((r) => r.series === 'KXATPMATCH' && r.month === '2026-04')!.trades, 5);
});

test('matchTime: the published start, else the time the history replay lists the market (what the sim keys the match by)', async () => {
  const c = Date.parse('2026-05-01T12:00:00Z');
  assert.equal(matchTime({ openTime: 0, startTime: c, candles: [{ ts: c - H }] }), c);
  assert.equal(matchTime({ openTime: 0, candles: [{ ts: c }] }), c - 30 * MIN - 1000);
  assert.equal(matchTime({ openTime: c - 10 * MIN, candles: [{ ts: c }] }), c - 10 * MIN - 1000);
  // Against the replay itself: the market lines of a match without a published start are stamped matchTime.
  const d = tmp(), kal = path.join(d, 'kalshi');
  const ms: Mk[] = ['AAA', 'BBB'].map((p, i) => ({ ticker: `KXATPMATCH-26MAY01XXXYYY-${p}`, event: 'KXATPMATCH-26MAY01XXXYYY', openTime: c - DAY, closeTime: c + 3 * H, candles: [candle(c + i * MIN), candle(c + 2 * MIN)] }));
  writeHist(kal, 'KXATPMATCH', ms);
  const out = path.join(d, 'replay');
  await buildHistoryReplay({ historyDir: d, outDir: out, assets: [], fromDay: '2026-05-01', toDay: '2026-05-01', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const lines = (await Promise.all(recordingFiles(out).map((f) => readAll(f.file)))).flat().filter((l) => l.k === 'market');
  assert.equal(lines.length, 2);
  for (const m of ms) assert.equal(lines.find((l) => l.ticker === m.ticker)?.t, matchTime(m as any), m.ticker);
});

test('the start era week: the first week from which every week with two-sided events has enough of them with a start', () => {
  const row = (week: string, twoSided: number, withStart: number, series = 'KXATPMATCH'): WeekRow => ({ series, week, markets: 2 * twoSided, events: twoSided, twoSided, withStart, noStart: 0 });
  const rows = [row('2026-03-30', 40, 0), row('2026-04-06', 40, 20), row('2026-04-13', 40, 40), row('2026-04-20', 40, 30), row('2026-04-27', 40, 39), row('2026-05-04', 0, 0), row('2026-05-11', 40, 40)];
  assert.equal(startEraWeek(rows), '2026-04-27');
  assert.equal(startEraWeek(rows, 0.75), '2026-04-13');
  assert.equal(startEraWeek(rows, 1), '2026-05-11');
  // ATP and WTA summed per week: WTA's short week holds the boundary back.
  assert.equal(startEraWeek([...rows, row('2026-04-27', 40, 20, 'KXWTAMATCH')]), '2026-05-11');
  assert.equal(startEraWeek([row('2026-04-27', 10, 5)]), undefined);
  assert.equal(startEraWeek([]), undefined);
});
