// Oracle setups, hourly-ladder backfill (research/oracle/hourlyBackfill.ts; python/oracle/SPEC.md 2d). A mocked Kalshi
// API (both tiers, cursor pages, a close-range filter the live tier honours and the historical tier refuses with a 400)
// and a synthetic perpta1 grid check the following. Per event, the 4 greater-than strikes nearest the Binance close at
// close - 60 min are kept: not the ones nearest at the close, and no range buckets or 'less' markets. Candles cover the
// last 70 minutes, from each market's own tier, also for a strike that never traded (its volume is future information). A rerun asks for nothing. The budget stops a run and the next run
// resumes it. A listing cut short selects only events newer than where it stopped. python/allpairs/data.py load_kalshi
// reads the files (when python3 + numpy are installed). DOGE and XRP are refused, and so is anything at or after
// 2026-11-05.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawnSync } from 'child_process';
import { COLS, writeGrid, type Col } from '../research/perpTaSweep';
import { hourlyBackfill, hourlySeries, isLadder, type HourlyMarket } from '../research/oracle/hourlyBackfill';

const MIN = 60_000;
const T0 = Date.UTC(2026, 5, 1);                       // grid start; spot close of bar i = 100000 + 10 i
const FROM = Date.UTC(2026, 5, 1), TO = Date.UTC(2026, 5, 3);
const CUTOFF = Date.UTC(2026, 5, 1, 18);               // markets settled before it live in /historical
const iso = (t: number) => new Date(t).toISOString();
const spotOpen = (close: number) => 100000 + 10 * ((close - 60 * MIN - T0) / MIN - 1); // the bar ENDING at close - 60 min

function gridDir(asset = 'BTC', t0 = T0, n = 3 * 1440): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hb-grid-'));
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Record<Col, Float32Array>;
  for (let i = 0; i < n; i++) { const p = 100000 + 10 * i; c.so[i] = c.sh[i] = c.sl[i] = c.sc[i] = p; c.po[i] = c.ph[i] = c.pl[i] = c.pc[i] = p; c.valid[i] = 1; }
  writeGrid({ asset, t0, n, c, fundRaw: new Float32Array(n) }, path.join(dir, `${asset}.bin`));
  return dir;
}

interface Raw { ticker: string; event_ticker: string; open_time: string; close_time: string; floor_strike?: number; cap_strike?: number; strike_type: string; result: string; volume_fp: string }
/** One hourly event: strikes at spot-at-open + offset - 0.01 ('greater', as KXBTCD's -T<strike> tickers). */
function event(name: string, close: number, offsets: number[], o: { listedMin?: number; dead?: number } = {}): Raw[] {
  const s0 = spotOpen(close), sClose = 100000 + 10 * ((close - T0) / MIN - 1);
  return offsets.map((off) => {
    const k = s0 + off - 0.01;
    return { ticker: `KXBTCD-${name}-T${k.toFixed(2)}`, event_ticker: `KXBTCD-${name}`, open_time: iso(close - (o.listedMin ?? 60) * MIN), close_time: iso(close), floor_strike: k, strike_type: 'greater', result: sClose > k ? 'yes' : 'no', volume_fp: off === o.dead ? '0.00' : '120.00' };
  });
}
const OFFS = [-1100, -800, -550, -300, -60, 40, 260, 700, 1200, 2000];
const C_OLD = Date.UTC(2026, 4, 31, 23), C1 = Date.UTC(2026, 5, 1, 12), C2 = Date.UTC(2026, 5, 2, 3), C3 = Date.UTC(2026, 5, 2, 20), C_LATE = TO;
const E1 = [
  ...event('26JUN0108', C1, OFFS, { listedMin: 180 }), // listed 3 h before its close: candles from close - 70 min only
  { ticker: `KXBTCD-26JUN0108-B${spotOpen(C1) + 50}`, event_ticker: 'KXBTCD-26JUN0108', open_time: iso(C1 - 60 * MIN), close_time: iso(C1), floor_strike: spotOpen(C1), cap_strike: spotOpen(C1) + 100, strike_type: 'between', result: 'yes', volume_fp: '9' },
  { ticker: 'KXBTCD-26JUN0108-L1', event_ticker: 'KXBTCD-26JUN0108', open_time: iso(C1 - 60 * MIN), close_time: iso(C1), cap_strike: spotOpen(C1) + 5, strike_type: 'less', result: 'no', volume_fp: '9' },
];
const E2 = event('26JUN0123', C2, OFFS, { dead: 40 });  // its nearest strike never traded
const E3 = event('26JUN0216', C3, [-500, 100, 900]);    // a short ladder: all kept
const HIST = [...E1, ...event('26MAY3119', C_OLD, [0, 100])].sort((a, b) => Date.parse(b.close_time) - Date.parse(a.close_time) || (a.ticker < b.ticker ? 1 : -1));
const LIVE = [...event('26JUN0220', C_LATE, [0, 100]), ...E3, ...E2].sort((a, b) => Date.parse(b.close_time) - Date.parse(a.close_time) || (a.ticker < b.ticker ? 1 : -1));
const nearest4 = (raws: Raw[]) => raws.filter((r) => [-300, -60, 40, 260].some((off) => Math.abs(r.floor_strike! - (spotOpen(Date.parse(r.close_time)) + off - 0.01)) < 1e-6)).map((r) => r.ticker);

function api(o: { livePage?: number; histPage?: number; tick?: () => void; strictLive?: boolean } = {}) {
  const calls: string[] = [];
  const json = (body: unknown, status = 200) => ({ ok: status === 200, status, json: async () => body, text: async () => JSON.stringify(body) }) as unknown as Response;
  const page = (list: Raw[], q: URLSearchParams, size: number) => {
    const at = Number(q.get('cursor') || 0);
    return json({ markets: list.slice(at, at + size), cursor: at + size < list.length ? String(at + size) : '' });
  };
  const fetchImpl = (async (url: string) => {
    calls.push(url);
    o.tick?.();
    await new Promise((r) => setImmediate(r));
    const u = new URL(url), p = u.pathname, q = u.searchParams;
    if (p.endsWith('/historical/cutoff')) return json({ market_settled_ts: iso(CUTOFF) });
    if (p.endsWith('/candlesticks')) {
      const s = Number(q.get('start_ts')), e = Number(q.get('end_ts'));
      const candlesticks = Array.from({ length: (e - s) / 60 }, (_, i) => {
        const b = 0.3 + 0.005 * (i + 1);
        return { end_period_ts: s + 60 * (i + 1), yes_bid: { open_dollars: b.toFixed(4), high_dollars: b.toFixed(4), low_dollars: b.toFixed(4), close_dollars: b.toFixed(4) }, yes_ask: { open_dollars: (b + 0.02).toFixed(4), high_dollars: (b + 0.02).toFixed(4), low_dollars: (b + 0.02).toFixed(4), close_dollars: (b + 0.02).toFixed(4) }, price: { close_dollars: b.toFixed(4) }, volume_fp: '5.00', open_interest_fp: '50.00' };
      });
      return json({ candlesticks });
    }
    if (p.endsWith('/historical/markets')) {
      if (q.has('min_close_ts')) return json({ error: { code: 'invalid_parameters' } }, 400); // the archive refuses the filter
      return page(HIST, q, o.histPage ?? 50);
    }
    if (p.endsWith('/markets')) {
      // Kalshi's documented rule: close-time filters go with status 'closed' or none.
      if (o.strictLive && q.has('min_close_ts') && q.get('status') === 'settled') return json({ error: { code: 'invalid_parameters' } }, 400);
      const lo = Number(q.get('min_close_ts') ?? -Infinity) * 1000, hi = Number(q.get('max_close_ts') ?? Infinity) * 1000;
      return page(LIVE.filter((m) => Date.parse(m.close_time) >= lo && Date.parse(m.close_time) <= hi), q, o.livePage ?? 4);
    }
    return json({}, 404);
  }) as unknown as typeof fetch;
  return { calls, fetchImpl, candleCalls: () => calls.filter((c) => c.includes('/candlesticks')) };
}

const readOut = (out: string): HourlyMarket[] => {
  const dir = path.join(out, 'KXBTCD');
  return fs.readdirSync(dir).filter((f) => f.endsWith('.jsonl')).sort().flatMap((f) => fs.readFileSync(path.join(dir, f), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)));
};
const python = spawnSync('python3', ['-c', 'import numpy'], { encoding: 'utf8' }).status === 0 ? 'python3' : undefined;

test('hourly backfill: the 4 strikes nearest the Binance close at the window open, both tiers, 70-minute candles, resumable, read by load_kalshi', async () => {
  const grid = path.join(gridDir(), '{A}.bin');
  const hist = fs.mkdtempSync(path.join(os.tmpdir(), 'hb-hist-'));
  const out = path.join(hist, 'kalshi');
  const a = api();
  const r = await hourlyBackfill({ assets: ['btc'], from: FROM, to: TO, grid, out, fetchImpl: a.fetchImpl, ratePerSec: 1000, log: () => {} });
  const st = r.series.KXBTCD;
  assert.deepEqual([r.markets, r.noVolume, r.skipped, r.rejected, r.failed, r.remaining, r.deferred, r.budgetHit], [11, 1, 0, 0, 0, 0, 0, false]);
  assert.deepEqual([st.events, st.kept, st.notLadder, st.noSpot, st.listed], [3, 11, 2, 0, E1.length + E2.length + E3.length]);
  assert.match(st.tiers.historical, /unfiltered/, 'the archive refused the close-range filter: listed plainly, filtered here');
  assert.match(st.tiers.live, /settled \+ close-range filter/);
  const stored = readOut(out);
  const want = [...nearest4(E1), ...nearest4(E2), ...E3.map((m) => m.ticker)].sort();
  assert.deepEqual(stored.map((m) => m.ticker).sort(), want, 'nearest 4 at the open per event (the short ladder whole); no range bucket, no less, nothing outside [from, to)');
  // At the close the spot is 600 higher: the nearest 4 there would be +700/+260/+40/+1200, a different set.
  assert.ok(!stored.some((m) => m.ticker.endsWith(`T${(spotOpen(C1) + 700 - 0.01).toFixed(2)}`)));
  const e1 = stored.filter((m) => m.event === 'KXBTCD-26JUN0108').sort((x, y) => x.pick!.rank - y.pick!.rank);
  assert.deepEqual(e1.map((m) => Math.round(m.strike! + 0.01 - spotOpen(C1))), [40, -60, 260, -300], 'ranked nearest first');
  assert.ok(e1.every((m) => m.pick!.spot === spotOpen(C1) && m.pick!.strikes === 10 && m.strikeType === 'greater' && m.cap === null));
  // The strike that never traded is fetched like the others (review fix, Nov 6): its lifetime volume is known only
  // after it settled, so skipping it would pick the catalog's strikes on future information.
  const deadTicker = nearest4(E2).find((t) => t.endsWith(`T${(spotOpen(C2) + 40 - 0.01).toFixed(2)}`))!;
  const dead = stored.find((m) => m.ticker === deadTicker)!;
  assert.ok(dead.candles.length > 0 && !dead.noVolume && dead.volume === 0);
  // Candle requests: one per kept market, the last 70 minutes (or the whole life when shorter), from its tier.
  const cc = a.candleCalls();
  assert.equal(cc.length, 11);
  assert.ok(cc.some((c) => c.includes(dead.ticker)), 'a market that never traded is asked for too');
  for (const c of cc) {
    const u = new URL(c), t = decodeURIComponent(u.pathname.split('/').at(-2)!);
    const m = stored.find((x) => x.ticker === t)!;
    assert.equal(Number(u.searchParams.get('end_ts')) * 1000, m.closeTime);
    assert.equal(m.closeTime - Number(u.searchParams.get('start_ts')) * 1000, (m.event === 'KXBTCD-26JUN0108' ? 70 : 60) * MIN);
    assert.equal(u.searchParams.get('period_interval'), '1');
    assert.equal(u.pathname.includes('/historical/markets/'), m.closeTime < CUTOFF, 'historical tier before the cutoff, live after');
  }
  assert.ok(!a.calls.some((c) => c.includes('26JUN0220') || c.includes('26MAY3119')), 'nothing outside [from, to) asked for');
  assert.deepEqual(fs.readdirSync(path.join(out, 'KXBTCD')).sort(), ['.index.json', '2026-06-01.jsonl', '2026-06-02.jsonl']);
  // Resume: a second run lists again and asks for no candles.
  const b = api();
  const r2 = await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out, fetchImpl: b.fetchImpl, ratePerSec: 1000, log: () => {} });
  assert.deepEqual([r2.markets, r2.skipped, r2.noVolume, b.candleCalls().length], [0, 11, 0, 0]);
  assert.equal(readOut(out).length, 11, 'nothing stored twice');
  // load_kalshi reads it: 11 windows (the untraded strike too: its book is in its candles), strike = floor strike, settle = result,
  // window open = close - 60 min, quote k = candle k's close.
  if (!python) return;
  const code = [
    'import json, sys', 'from allpairs.data import load_kalshi',
    "w = load_kalshi(sys.argv[1], ['BTC'], n=60, series_fmt='KX{asset}D', log=lambda m: None)",
    "print(json.dumps({'tickers': w.tickers, 'strike': w.strike.tolist(), 'settle': w.settle.tolist(), 'open': w.open_ms.tolist(), 'bid5': w.bid[:, 5].tolist(), 'ask5': w.ask[:, 5].tolist(), 'bid0': [None if x != x else x for x in w.bid[:, 0].tolist()]}))",
  ].join('\n');
  const py = spawnSync(python, ['-c', code, hist], { cwd: path.resolve('python'), encoding: 'utf8' });
  assert.equal(py.status, 0, py.stderr);
  const w = JSON.parse(py.stdout.trim().split('\n').at(-1)!);
  assert.equal(w.tickers.length, 11);
  w.tickers.forEach((t: string, i: number) => {
    const m = stored.find((x) => x.ticker === t)!;
    assert.ok(Math.abs(w.strike[i] - m.strike!) < 1e-6);
    assert.equal(w.settle[i], m.result === 'yes' ? 1 : 0);
    assert.equal(w.open[i], m.closeTime - 60 * MIN);
    // Candle j of the request ends at start + j min; window minute 5 is candle 15 of a 70-minute request, 5 of a 60-minute one.
    const j = m.event === 'KXBTCD-26JUN0108' ? 15 : 5;
    assert.ok(Math.abs(w.bid5[i] - (0.3 + 0.005 * j)) < 1e-9 && Math.abs(w.ask5[i] - (0.32 + 0.005 * j)) < 1e-9, `${t}: ${w.bid5[i]} / ${w.ask5[i]}`);
    assert.equal(w.bid0[i], null, 'minute 0 (the listing quote) is never a quote');
  });
  assert.ok(w.settle.some((x: number) => x === 1) && w.settle.some((x: number) => x === 0));
});

test('hourly backfill: the time budget stops a run, the next run fetches the rest, no market asked twice', async () => {
  const grid = path.join(gridDir(), '{A}.bin');
  const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'hb-b-')), 'kalshi');
  let t = 0;
  const a = api({ tick: () => { t += 10; } });
  // Listing costs 7 requests (cutoff, 4 live pages, the refused filter, 1 archive page): 70 ms of the fake clock.
  const r1 = await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out, fetchImpl: a.fetchImpl, ratePerSec: 1000, log: () => {}, clock: () => t, budgetMs: 120, concurrency: 2 });
  assert.ok(r1.budgetHit && r1.remaining > 0 && r1.markets > 0, JSON.stringify(r1));
  const r2 = await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out, fetchImpl: a.fetchImpl, ratePerSec: 1000, log: () => {} });
  assert.equal(r2.remaining, 0);
  assert.equal(r1.markets + r2.markets, 11);
  const cc = a.candleCalls().map((c) => new URL(c).pathname);
  assert.equal(new Set(cc).size, cc.length, 'no market asked twice');
  assert.equal(readOut(out).length, 11);
  // A probe run: at most N candle requests.
  const out3 = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'hb-p-')), 'kalshi');
  const r3 = await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out: out3, fetchImpl: api().fetchImpl, ratePerSec: 1000, log: () => {}, maxMarkets: 3 });
  assert.deepEqual([r3.markets, r3.remaining], [3, 8]);
});

test('hourly backfill: a listing cut short selects only the events newer than where it stopped; list-only writes nothing', async () => {
  const grid = path.join(gridDir(), '{A}.bin');
  const out = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'hb-c-')), 'kalshi');
  // One page per tier: the live page holds E3's 3 markets and the first E2 market, so E3 is complete and E2 is not.
  const a = api();
  const r = await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out, fetchImpl: a.fetchImpl, ratePerSec: 1000, log: () => {}, maxPages: 1 });
  assert.match(r.series.KXBTCD.tiers.live, /incomplete/);
  assert.equal(r.markets, 3);
  assert.deepEqual(readOut(out).map((m) => m.ticker).sort(), E3.map((m) => m.ticker).sort());
  assert.equal(r.deferred, 2, 'E2 (cut by the page) and E1 (older than where the live listing stopped) wait for the next run');
  const out2 = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'hb-l-')), 'kalshi');
  const b = api({ strictLive: true });
  const l = await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out: out2, fetchImpl: b.fetchImpl, ratePerSec: 1000, log: () => {}, listOnly: true });
  assert.deepEqual([l.markets, l.remaining, l.noVolume, b.candleCalls().length, fs.existsSync(out2)], [0, 11, 1, 0, false]);
  assert.match(l.series.KXBTCD.tiers.live, /page\(s\), close-range filter$/, 'settled + close range refused: the close range alone');
});

test('hourly backfill: a strike stored without candles as never traded (an earlier run) is fetched again on resume', async () => {
  const grid = path.join(gridDir(), '{A}.bin');
  const hist = fs.mkdtempSync(path.join(os.tmpdir(), 'hb-nv-'));
  const out = path.join(hist, 'kalshi');
  await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out, fetchImpl: api().fetchImpl, ratePerSec: 1000, log: () => {} });
  // Rewrite the untraded strike's line as the old code stored it: no candles, noVolume.
  const deadTicker = nearest4(E2).find((t) => t.endsWith(`T${(spotOpen(C2) + 40 - 0.01).toFixed(2)}`))!;
  const dir = path.join(out, 'KXBTCD');
  for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.jsonl'))) {
    const lines = fs.readFileSync(path.join(dir, f), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as HourlyMarket);
    fs.writeFileSync(path.join(dir, f), lines.map((m) => JSON.stringify(m.ticker === deadTicker ? { ...m, candles: [], noVolume: true } : m)).join('\n') + '\n');
  }
  const b = api();
  const r = await hourlyBackfill({ assets: ['BTC'], from: FROM, to: TO, grid, out, fetchImpl: b.fetchImpl, ratePerSec: 1000, log: () => {} });
  assert.deepEqual([r.markets, r.skipped, b.candleCalls().length], [1, 10, 1]);
  assert.ok(b.candleCalls()[0].includes(deadTicker));
  const lines = readOut(out).filter((m) => m.ticker === deadTicker);
  assert.equal(lines.length, 2, 'the old empty line stays (rclone never deletes); load_kalshi skips it, the new one has candles');
  assert.ok(lines.some((m) => m.candles.length > 0));
});

test('hourly backfill: DOGE and XRP refused, nothing at or after 2026-11-05, strike semantics', async () => {
  assert.deepEqual(hourlySeries(['BTC', 'eth', 'SOL']), ['KXBTCD', 'KXETHD', 'KXSOLD']);
  assert.throws(() => hourlySeries(['BTC', 'DOGE']), /DOGE/);
  assert.throws(() => hourlySeries(['XRP']), /XRP/);
  const grid = path.join(gridDir(), '{A}.bin');
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'hb-r-'));
  const a = api();
  const base = { from: FROM, to: TO, grid, out, fetchImpl: a.fetchImpl, ratePerSec: 1000, log: () => {} };
  await assert.rejects(hourlyBackfill({ ...base, assets: ['DOGE'] }), /DOGE/);
  await assert.rejects(hourlyBackfill({ ...base, assets: ['XRP'] }), /XRP/);
  await assert.rejects(hourlyBackfill({ ...base, assets: ['BTC'], to: Date.UTC(2026, 10, 6) }), /2026-11-05/);
  // A grid reaching past Nov 5 is refused before it is read.
  const late = path.join(gridDir('BTC', Date.UTC(2026, 10, 4), 2 * 1440), '{A}.bin');
  await assert.rejects(hourlyBackfill({ ...base, assets: ['BTC'], grid: late, from: Date.UTC(2026, 10, 4), to: Date.UTC(2026, 10, 5) }), /2026-11-05/);
  // The wrong coin's grid is refused.
  await assert.rejects(hourlyBackfill({ ...base, assets: ['ETH'], grid: path.join(path.dirname(grid), 'BTC.bin') }), /not ETH/);
  assert.equal(a.calls.length, 0, 'refused before any request');
  // Strike semantics: only the greater-than ladder (YES iff the index settles above floor_strike).
  const m = { ticker: 'KXBTCD-26JUN0108-T100249.99', series: 'KXBTCD', strike: 100249.99, cap: null, strikeType: 'greater' };
  assert.ok(isLadder(m) && isLadder({ ...m, strikeType: 'greater_or_equal' }));
  assert.ok(isLadder({ ...m, cap: 0 }), 'a zero cap is no cap');
  assert.ok(!isLadder({ ...m, strikeType: 'between', cap: 100499.99 }) && !isLadder({ ...m, strikeType: 'less' }) && !isLadder({ ...m, ticker: 'KXBTCD-26JUN0108-B100250' }) && !isLadder({ ...m, strike: null }));
});
