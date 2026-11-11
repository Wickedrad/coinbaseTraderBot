import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { FileHeatSource, MemoryHeatSource, ReplayHeatSource, parseHeatCalls, toSnapshot } from '../bot/heat/heatSource';
import type { HeatCallRow, HeatCallsFile, HeatCoinCalls } from '../bot/heat/types';

// A bar close on a minute boundary, in ms (Nov 11 2026 16:00 UTC), and the engine's clock a few seconds after it.
const T0 = Date.UTC(2026, 10, 11, 16, 0, 0);
const NOW = T0 + 5_000;
// File modification times the tests set by hand: whole seconds, so every filesystem stores them exactly.
const M0 = 1_700_000_000_000;

const row = (over: Partial<HeatCallRow> = {}): HeatCallRow => ({
  key: '15m:RSI14=very low', kind: 'single', tf: 15, h: 15, dir: 1, rank: 3, of: 40, heat: 120.5, share: 0.52, odds: 2.1, barClose: T0, ...over,
});
const coin = (over: Partial<HeatCoinCalls> = {}): HeatCoinCalls => ({ asOf: T0, tableSha: 'a'.repeat(64), ok: true, calls: [row()], ...over });
const file = (over: Partial<HeatCallsFile> = {}): HeatCallsFile => ({
  v: 1, source: 'oracle-heat', run: '43030435253', packSha: 'b'.repeat(64), writtenAt: T0 + 2_000, coins: { BTC: coin(), ETH: coin() }, ...over,
});

function tmp(t: { after: (fn: () => void) => void }): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'heat-source-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return dir;
}
/** Write the calls file the way the reader does (a temp file renamed over it) and pin its modification time. */
function put(p: string, body: unknown, mtimeMs: number): void {
  const text = typeof body === 'string' ? body : JSON.stringify(body);
  fs.writeFileSync(`${p}.tmp`, text);
  fs.utimesSync(`${p}.tmp`, new Date(mtimeMs), new Date(mtimeMs));
  fs.renameSync(`${p}.tmp`, p);
}

test('parseHeatCalls: a good file becomes a snapshot with the coins in a map and clean rows', () => {
  const f = file({ coins: { BTC: coin({ calls: [row({ aliases: ['15m:CMO14=very low'], hold: 8.2, dip: -6.5, move: 0.5 }), row({ key: '15m:RSI14=very low+1h:ADX14=high', kind: 'pair', trig: '15m:RSI14=very low', rank: 1, dir: -1 })] }) } });
  const r = parseHeatCalls(JSON.stringify(f));
  assert.equal(r.error, undefined);
  const s = r.snapshot!;
  assert.deepEqual({ source: s.source, run: s.run, packSha: s.packSha, writtenAt: s.writtenAt }, { source: 'oracle-heat', run: '43030435253', packSha: 'b'.repeat(64), writtenAt: T0 + 2_000 });
  assert.ok(s.coins instanceof Map);
  assert.deepEqual([...s.coins.keys()], ['BTC']);
  assert.deepEqual(s.coins.get('BTC'), f.coins.BTC);
});

test('parseHeatCalls: fields the contract does not name are left out, null means an optional field is absent, an empty trig is none', () => {
  const raw = { ...file(), extra: 1, coins: { BTC: { ...coin(), why: null, note: 'x', calls: [{ ...row(), aliases: null, trig: '', hold: null, n_B: 33719 }] } } };
  const c = parseHeatCalls(JSON.stringify(raw)).snapshot!.coins.get('BTC')!;
  assert.deepEqual(c, coin());
  assert.ok(!('trig' in c.calls[0]) && !('aliases' in c.calls[0]) && !('why' in c));
});

test('parseHeatCalls: text that is not a calls file gives an error and never throws', () => {
  for (const text of ['', '   ', '{"v":1,', 'null', '[]', '5', '"x"', 'not json at all']) {
    const r = parseHeatCalls(text);
    assert.equal(r.snapshot, undefined, text);
    assert.equal(typeof r.error, 'string', text);
  }
  assert.match(parseHeatCalls('{"v":1,').error!, /bad JSON/);
  assert.match(parseHeatCalls('').error!, /bad JSON/);
  assert.match(parseHeatCalls('[]').error!, /not a JSON object/);
  // Not text at all (a caller's mistake) is still an answer, not an exception.
  assert.equal(typeof parseHeatCalls(undefined as unknown as string).error, 'string');
});

test('parseHeatCalls: a wrong version or a bad file-level field keeps nothing', () => {
  const bad: Array<[Record<string, unknown>, RegExp]> = [
    [{ v: 2 }, /version/],
    [{ v: '1' }, /version/],
    [{ v: undefined }, /version/],
    [{ source: '' }, /source/],
    [{ source: 7 }, /source/],
    [{ run: 43030435253 }, /run/],
    [{ run: '' }, /run/],
    [{ packSha: null }, /packSha/],
    [{ writtenAt: Math.floor(T0 / 1000) }, /writtenAt must be a time in ms/],
    [{ writtenAt: T0 * 1000 }, /writtenAt must be a time in ms/],
    [{ writtenAt: String(T0) }, /writtenAt/],
    [{ coins: [] }, /coins/],
    [{ coins: null }, /coins/],
    [{ coins: undefined }, /coins/],
  ];
  for (const [over, re] of bad) {
    const r = parseHeatCalls(JSON.stringify({ ...file(), ...over }));
    assert.equal(r.snapshot, undefined, JSON.stringify(over));
    assert.match(r.error!, re, JSON.stringify(over));
  }
});

test('parseHeatCalls: a malformed row drops that coin only, and the coin says why', () => {
  const f = file({ coins: { BTC: coin(), ETH: coin({ calls: [row(), row({ key: '1m:AROONdn14=very high', share: 51.985 })] }), SOL: coin({ calls: [] }) } });
  const s = parseHeatCalls(JSON.stringify(f)).snapshot!;
  assert.deepEqual(s.coins.get('BTC'), coin());
  assert.deepEqual(s.coins.get('SOL'), coin({ calls: [] }));
  const eth = s.coins.get('ETH')!;
  assert.equal(eth.ok, false);
  assert.deepEqual(eth.calls, [], 'the good row of a dropped coin goes too');
  assert.equal(eth.asOf, T0);
  assert.match(eth.why!, /^malformed: call 2 \(1m:AROONdn14=very high\): share must be within 0\.\.1/);
});

test('parseHeatCalls: every row field the lane relies on is checked', () => {
  const bad: Array<[Record<string, unknown>, RegExp]> = [
    [{ key: '' }, /key/],
    [{ key: 5 }, /key/],
    [{ kind: 'quad' }, /kind/],
    [{ kind: undefined }, /kind/],
    [{ tf: '1m' }, /tf/],
    [{ tf: 0 }, /tf/],
    [{ h: '15' }, /\bh must/],
    [{ h: -15 }, /\bh must/],
    [{ dir: 0 }, /dir must be 1 or -1/],
    [{ dir: 'up' }, /dir must be 1 or -1/],
    [{ dir: 2 }, /dir must be 1 or -1/],
    [{ rank: 0 }, /rank must be 1 or more/],
    [{ rank: null }, /rank/],
    [{ rank: '3' }, /rank/],
    [{ of: 0 }, /of must be 1 or more/],
    [{ of: undefined }, /of must/],
    [{ heat: null }, /heat/],
    [{ heat: '120' }, /heat/],
    [{ share: 52 }, /share must be within 0\.\.1/],
    [{ share: -0.1 }, /share/],
    [{ share: 1.0001 }, /share/],
    [{ share: undefined }, /share/],
    [{ odds: 'x' }, /odds/],
    [{ barClose: Math.floor(T0 / 1000) }, /barClose must be a time in ms/],
    [{ barClose: 0 }, /barClose/],
    [{ barClose: new Date(T0).toISOString() }, /barClose/],
    [{ aliases: 'x' }, /aliases must be an array of strings/],
    [{ aliases: ['a', 5] }, /aliases must be an array of strings/],
    [{ trig: 7 }, /trig/],
    [{ hold: 'x' }, /hold/],
    [{ dip: [] }, /dip/],
    [{ move: {} }, /move/],
  ];
  for (const [over, re] of bad) {
    const raw = { ...file(), coins: { BTC: coin(), ETH: { ...coin(), calls: [{ ...row(), ...over }] } } };
    const r = parseHeatCalls(JSON.stringify(raw));
    assert.ok(r.snapshot, `the file survives: ${JSON.stringify(over)}`);
    assert.equal(r.snapshot.coins.get('BTC')!.ok, true);
    const eth = r.snapshot.coins.get('ETH')!;
    assert.equal(eth.ok, false, JSON.stringify(over));
    assert.equal(eth.calls.length, 0, JSON.stringify(over));
    assert.match(eth.why!, re, JSON.stringify(over));
  }
  // Numbers JSON cannot carry (NaN, Infinity) arrive as null and are refused like any other non-number.
  assert.equal(parseHeatCalls(JSON.stringify(file({ coins: { BTC: coin({ calls: [row({ odds: NaN })] }) } }))).snapshot!.coins.get('BTC')!.ok, false);
  // A rank past `of` (a row listed for its share right) and a tied half rank are fine; so are the edges of the share.
  const ok = parseHeatCalls(JSON.stringify(file({ coins: { BTC: coin({ calls: [row({ rank: 227 }), row({ rank: 2.5, share: 0 }), row({ rank: 1, share: 1, odds: -1.5, heat: 0 })] }) } }))).snapshot!;
  assert.equal(ok.coins.get('BTC')!.ok, true);
  assert.equal(ok.coins.get('BTC')!.calls.length, 3);
});

test('parseHeatCalls: a malformed coin is dropped alone; a coin the reader gave up on keeps the reader\'s reason', () => {
  const bad: Array<[unknown, RegExp]> = [
    [5, /coin is not an object/],
    [null, /coin is not an object/],
    [{ ...coin(), asOf: Math.floor(T0 / 1000) }, /asOf must be a time in ms/],
    [{ ...coin(), tableSha: 1 }, /tableSha/],
    [{ ...coin(), ok: 'yes' }, /ok must be true or false/],
    [{ ...coin(), why: 3 }, /why/],
    [{ ...coin(), calls: {} }, /calls must be an array/],
    [{ ...coin(), calls: ['row'] }, /call 1: not an object/],
  ];
  for (const [c, re] of bad) {
    const s = parseHeatCalls(JSON.stringify({ ...file(), coins: { BTC: coin(), XRP: c } })).snapshot!;
    assert.equal(s.coins.get('BTC')!.ok, true);
    const x = s.coins.get('XRP')!;
    assert.equal(x.ok, false, JSON.stringify(c));
    assert.deepEqual(x.calls, []);
    assert.match(x.why!, /^malformed: /);
    assert.match(x.why!, re);
  }
  // The reader's own not-ok coin passes through as it is.
  const gap = coin({ ok: false, why: 'minute gap', calls: [] });
  assert.deepEqual(parseHeatCalls(JSON.stringify(file({ coins: { SOL: gap } }))).snapshot!.coins.get('SOL'), gap);
  // A coin the reader gave up on before it had a bar (no time yet) still says what the reader said.
  const none = parseHeatCalls(JSON.stringify({ ...file(), coins: { SOL: { asOf: 0, tableSha: '', ok: false, why: 'fetch failed', calls: [] } } })).snapshot!.coins.get('SOL')!;
  assert.equal(none.ok, false);
  assert.equal(none.asOf, 0);
  assert.match(none.why!, /^fetch failed; malformed: asOf/);
});

test('DOGE is dropped at parse time, whatever else the file holds, and in toSnapshot too', () => {
  const raw = { ...file(), coins: { BTC: coin(), DOGE: coin(), doge: coin(), DOGEUSDT: 'not even a coin object' } };
  const r = parseHeatCalls(JSON.stringify(raw));
  assert.deepEqual([...r.snapshot!.coins.keys()], ['BTC']);
  assert.deepEqual([...toSnapshot(file({ coins: { DOGE: coin(), ETH: coin(), 'DOGE-USD': coin() } })).coins.keys()], ['ETH']);
});

test('toSnapshot: a file object becomes the snapshot the lane reads', () => {
  const f = file();
  const s = toSnapshot(f);
  assert.deepEqual({ source: s.source, run: s.run, packSha: s.packSha, writtenAt: s.writtenAt }, { source: f.source, run: f.run, packSha: f.packSha, writtenAt: f.writtenAt });
  assert.deepEqual([...s.coins.keys()], ['BTC', 'ETH']);
  assert.equal(s.coins.get('BTC'), f.coins.BTC);
});

test('file source: a missing file gives nothing and says so; the file is picked up once it appears', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  const src = new FileHeatSource(p);
  assert.equal(src.read(NOW), undefined);
  const st = src.status(NOW);
  assert.equal(st.ok, false);
  assert.match(st.why!, /missing/);
  assert.equal(st.writtenAt, undefined);
  put(p, file(), M0);
  assert.equal(src.read(NOW + 1_000)!.run, '43030435253');
  assert.equal(src.status(NOW + 1_000).ok, true);
  // Gone again: the last good snapshot is not kept.
  fs.rmSync(p);
  assert.equal(src.read(NOW + 2_000), undefined);
  assert.match(src.status(NOW + 2_000).why!, /missing/);
});

test('file source: status reports the file and each coin', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  put(p, file({ coins: { BTC: coin(), ETH: coin({ calls: [row({ dir: 0 as unknown as 1 })] }), SOL: coin({ ok: false, why: 'minute gap', calls: [] }) } }), M0);
  const src = new FileHeatSource(p);
  assert.deepEqual(src.status(NOW), {
    ok: true, writtenAt: T0 + 2_000, ageMs: 3_000,
    coins: {
      BTC: { ok: true, asOf: T0, calls: 1 },
      ETH: { ok: false, asOf: T0, calls: 0, why: 'malformed: call 1 (15m:RSI14=very low): dir must be 1 or -1' },
      SOL: { ok: false, asOf: T0, calls: 0, why: 'minute gap' },
    },
  });
  const s = src.read(NOW)!;
  assert.equal(s.coins.get('BTC')!.calls.length, 1);
  assert.equal(s.coins.get('ETH')!.ok, false);
});

test('file source: bad JSON keeps nothing, not even the last good file, and recovers with the next good one', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  const src = new FileHeatSource(p);
  put(p, file(), M0);
  assert.ok(src.read(NOW));
  put(p, '{"v":1,"source":"oracle-heat",', M0 + 60_000);
  assert.equal(src.read(NOW + 60_000), undefined);
  const st = src.status(NOW + 60_000);
  assert.equal(st.ok, false);
  assert.match(st.why!, /bad JSON/);
  assert.equal(st.coins, undefined);
  put(p, '', M0 + 90_000);
  assert.equal(src.read(NOW + 90_000), undefined);
  assert.match(src.status(NOW + 90_000).why!, /bad JSON/);
  put(p, file({ run: 'next' }), M0 + 120_000);
  assert.equal(src.read(NOW + 120_000)!.run, 'next');
  assert.equal(src.status(NOW + 120_000).why, undefined);
});

test('file source: a wrong version keeps nothing and says so', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  put(p, { ...file(), v: 2 }, M0);
  const src = new FileHeatSource(p);
  assert.equal(src.read(NOW), undefined);
  assert.match(src.status(NOW).why!, /unsupported version: v is 2/);
});

test('file source: a new modification time picks up the new file; an unchanged one is not read again', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  put(p, file({ run: 'run-A' }), M0);
  const src = new FileHeatSource(p);
  const a = src.read(NOW)!;
  assert.equal(a.run, 'run-A');
  // Other content of the same length under the same modification time: the source has no reason to read it.
  put(p, file({ run: 'run-B' }), M0);
  assert.equal(fs.statSync(p).mtimeMs, M0);
  for (const dt of [1_000, 2_000, 30_000]) assert.equal(src.read(NOW + dt), a, 'the very same snapshot object is served');
  assert.equal(src.status(NOW + 31_000).ok, true);
  assert.equal(src.read(NOW + 32_000)!.run, 'run-A');
  // The modification time moves: read again.
  fs.utimesSync(p, new Date(M0 + 60_000), new Date(M0 + 60_000));
  const b = src.read(NOW + 60_000)!;
  assert.equal(b.run, 'run-B');
  assert.notEqual(b, a);
});

test('file source: a new size under the same modification time is read again', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  put(p, file({ run: 'short' }), M0);
  const src = new FileHeatSource(p);
  assert.equal(src.read(NOW)!.run, 'short');
  put(p, file({ run: 'a-longer-run-id' }), M0);
  assert.equal(src.read(NOW + 1_000)!.run, 'a-longer-run-id');
});

test('file source: the file is looked at no more than once a second', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  put(p, file({ run: 'first' }), M0);
  const src = new FileHeatSource(p);
  assert.equal(src.read(NOW)!.run, 'first');
  put(p, file({ run: 'second' }), M0 + 60_000);
  assert.equal(src.read(NOW + 1)!.run, 'first');
  assert.equal(src.status(NOW + 500).ok, true);
  assert.equal(src.read(NOW + 999)!.run, 'first');
  assert.equal(src.read(NOW + 1_000)!.run, 'second');
  // A clock that steps back does not freeze the source.
  put(p, file({ run: 'third' }), M0 + 120_000);
  assert.equal(src.read(NOW - 5_000)!.run, 'third');
  // The interval can be set (0 = look on every call).
  const eager = new FileHeatSource(p, { statEveryMs: 0 });
  assert.equal(eager.read(NOW)!.run, 'third');
  put(p, file({ run: 'fourth' }), M0 + 180_000);
  assert.equal(eager.read(NOW)!.run, 'fourth');
});

test('file source: staleness is the lane\'s job, the source serves an old file and only reports its age', (t) => {
  const p = path.join(tmp(t), 'heat_calls.json');
  put(p, file(), M0);
  const src = new FileHeatSource(p);
  const later = T0 + 2_000 + 6 * 3_600_000;
  const s = src.read(later)!;
  assert.equal(s.writtenAt, T0 + 2_000);
  assert.equal(s.coins.get('BTC')!.calls.length, 1);
  const st = src.status(later);
  assert.equal(st.ok, true);
  assert.equal(st.ageMs, 6 * 3_600_000);
});

test('file source: a folder or an unusable path is a reason, never a throw', (t) => {
  const dir = tmp(t);
  const asDir = new FileHeatSource(dir);
  assert.equal(asDir.read(NOW), undefined);
  assert.match(asDir.status(NOW).why!, /not a regular file/);
  for (const p of ['', path.join(dir, 'no', 'such', 'folder', 'heat_calls.json'), path.join(dir, 'nul\u0000byte')]) {
    const src = new FileHeatSource(p);
    assert.equal(src.read(NOW), undefined);
    const st = src.status(NOW);
    assert.equal(st.ok, false);
    assert.equal(typeof st.why, 'string');
  }
});

test('memory source: serves what was set, as a snapshot or as a file object', () => {
  const src = new MemoryHeatSource();
  assert.equal(src.read(), undefined);
  assert.deepEqual(src.status(NOW), { ok: false, why: 'no snapshot set' });
  const snap = toSnapshot(file());
  src.set(snap);
  assert.equal(src.read(), snap);
  assert.deepEqual(src.status(NOW), { ok: true, writtenAt: T0 + 2_000, ageMs: 3_000, coins: { BTC: { ok: true, asOf: T0, calls: 1 }, ETH: { ok: true, asOf: T0, calls: 1 } } });
  src.set(file({ run: 'from-file', coins: { XRP: coin(), DOGE: coin() } }));
  assert.equal(src.read()!.run, 'from-file');
  assert.deepEqual([...src.read()!.coins.keys()], ['XRP']);
  src.set(undefined, 'reader down');
  assert.equal(src.read(), undefined);
  assert.deepEqual(src.status(NOW), { ok: false, why: 'reader down' });
  assert.equal(new MemoryHeatSource(file({ run: 'ctor' })).read()!.run, 'ctor');
});

test('replay source: serves the newest line written at or before now', (t) => {
  const p = path.join(tmp(t), 'heat_calls.jsonl');
  const MIN = 60_000;
  const lines = [0, 1, 2].map((i) => file({ run: `r${i}`, writtenAt: T0 + i * MIN + 2_000 }));
  fs.writeFileSync(p, lines.map((l) => JSON.stringify(l)).join('\n') + '\n');
  const src = new ReplayHeatSource(p);
  assert.deepEqual(src.info(), { lines: 3, badLines: 0, from: T0 + 2_000, to: T0 + 2 * MIN + 2_000, errors: [] });
  assert.equal(src.read(T0 + 1_999), undefined, 'nothing was written yet');
  assert.deepEqual(src.status(T0 + 1_999), { ok: false, why: 'no recorded calls at or before this time' });
  assert.equal(src.read(T0 + 2_000)!.run, 'r0');
  assert.equal(src.read(T0 + MIN + 1_999)!.run, 'r0');
  assert.equal(src.read(T0 + MIN + 2_000)!.run, 'r1');
  assert.equal(src.read(T0 + 2 * MIN + 2_000)!.run, 'r2');
  // Past the end the last line stays served and only its age grows: the lane decides it is stale.
  const late = T0 + 2 * MIN + 2_000 + 3_600_000;
  assert.equal(src.read(late)!.run, 'r2');
  assert.equal(src.status(late).ageMs, 3_600_000);
  assert.equal(src.read(T0 + 2_000), src.read(T0 + 30_000), 'the same line is the same object');
  // A replay may also step back.
  assert.equal(src.read(T0 + 2_000)!.run, 'r0');
});

test('replay source: gzipped input reads the same, in one member or several', (t) => {
  const dir = tmp(t);
  const MIN = 60_000;
  const lines = [0, 1, 2, 3].map((i) => JSON.stringify(file({ run: `r${i}`, writtenAt: T0 + i * MIN })) + '\n');
  const one = path.join(dir, 'calls.jsonl.gz'), many = path.join(dir, 'members.jsonl.gz'), plain = path.join(dir, 'calls.jsonl');
  fs.writeFileSync(plain, lines.join(''));
  fs.writeFileSync(one, zlib.gzipSync(lines.join('')));
  // A recording written as it goes is one gzip member per flush.
  fs.writeFileSync(many, Buffer.concat([zlib.gzipSync(lines[0] + lines[1]), zlib.gzipSync(lines[2]), zlib.gzipSync(lines[3])]));
  for (const f of [plain, one, many]) {
    const src = new ReplayHeatSource(f);
    assert.equal(src.info().lines, 4, f);
    for (let i = 0; i < 4; i++) assert.equal(src.read(T0 + i * MIN + 30_000)!.run, `r${i}`, f);
    assert.deepEqual(src.read(T0 + MIN)!.coins.get('BTC'), coin(), f);
  }
  // A gzip file cut short (still being written) is read up to where it stops.
  const whole = zlib.gzipSync(lines.join(''));
  const cut = path.join(dir, 'cut.jsonl.gz');
  fs.writeFileSync(cut, Buffer.concat([zlib.gzipSync(lines[0]), whole.subarray(0, whole.length - 12)]));
  const src = new ReplayHeatSource(cut);
  assert.ok(src.info().lines >= 1);
  assert.equal(src.read(T0)!.run, 'r0');
});

test('replay source: bad lines are skipped and counted, DOGE is dropped, lines out of order are put in order', () => {
  const MIN = 60_000;
  const text = [
    JSON.stringify(file({ run: 'r2', writtenAt: T0 + 2 * MIN })),
    '',
    '{"v":1, cut short',
    JSON.stringify(file({ run: 'r0', writtenAt: T0, coins: { BTC: coin(), DOGE: coin() } })),
    JSON.stringify({ ...file({ run: 'old-version', writtenAt: T0 + MIN }), v: 0 }),
    JSON.stringify(file({ run: 'r1', writtenAt: T0 + MIN })),
    JSON.stringify(file({ run: 'r1-again', writtenAt: T0 + MIN })),
  ].join('\r\n');
  const src = ReplayHeatSource.fromText(text);
  assert.deepEqual(src.info(), { lines: 4, badLines: 2, from: T0, to: T0 + 2 * MIN, errors: [] });
  assert.equal(src.read(T0)!.run, 'r0');
  assert.deepEqual([...src.read(T0)!.coins.keys()], ['BTC']);
  assert.equal(src.read(T0 + MIN)!.run, 'r1-again', 'of two lines written at the same time the later one is served');
  assert.equal(src.read(T0 + 2 * MIN)!.run, 'r2');
});

test('replay source: several files, and a missing or empty one is a reason, never a throw', (t) => {
  const dir = tmp(t);
  const day1 = path.join(dir, 'd1.jsonl'), day2 = path.join(dir, 'd2.jsonl.gz'), none = path.join(dir, 'none.jsonl'), empty = path.join(dir, 'empty.jsonl');
  fs.writeFileSync(day1, JSON.stringify(file({ run: 'd1', writtenAt: T0 })) + '\n');
  fs.writeFileSync(day2, zlib.gzipSync(JSON.stringify(file({ run: 'd2', writtenAt: T0 + 86_400_000 })) + '\n'));
  fs.writeFileSync(empty, '');
  const both = new ReplayHeatSource([day2, day1, none]);
  assert.equal(both.read(T0)!.run, 'd1');
  assert.equal(both.read(T0 + 86_400_000)!.run, 'd2');
  assert.equal(both.info().errors.length, 1);
  assert.match(both.info().errors[0], /ENOENT/);
  const missing = new ReplayHeatSource(none);
  assert.equal(missing.read(NOW), undefined);
  assert.equal(missing.status(NOW).ok, false);
  assert.match(missing.status(NOW).why!, /cannot be read \(ENOENT\)/);
  assert.deepEqual(new ReplayHeatSource(empty).status(NOW), { ok: false, why: 'the replay is empty' });
  assert.deepEqual(new ReplayHeatSource().status(NOW), { ok: false, why: 'the replay is empty' });
  assert.deepEqual(ReplayHeatSource.fromText('nope\n{}\n').status(NOW), { ok: false, why: 'no usable line in the replay (2 bad)' });
});
