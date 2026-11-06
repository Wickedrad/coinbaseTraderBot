// Oracle setups, perp exporter (research/oracle/oracleExport.ts; python/oracle/SPEC.md 2a): the NPY writer round-trips
// (and numpy loads it, when python3 + numpy are installed), the labels of a hand-built grid match hand-computed take-profit /
// time exits / funding / latency / cost stress, nothing after a decision changes its feature row (modulePrims runs on a
// 12-day synthetic grid: analyzer, TA-Lib, character, ta_net), t / label alignment, the Nov 5 cap, and DOGE is refused.

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import fs from 'fs';
import path from 'path';
import { COLS, writeGrid, type Grid } from '../research/perpTaSweep';
import { readNpy, writeNpy, NpyWriter, typed, type Dtype } from '../research/oracle/npy';
import { synthGrid, writeGridTmp, writeOthers1h, tmpDir } from '../research/oracle/fixtures';
import { exportAsset, assertAsset, readGridCapped, tpBps, costsFor, HOLD_TO, DEV_END, MIN, DAY } from '../research/oracle/oracleExport';

const python = ['python3', 'python'].find((p) => spawnSync(p, ['-c', 'import numpy'], { encoding: 'utf8' }).status === 0);
const near = (a: number, b: number, tol = 1e-4, what = '') => assert.ok(Math.abs(a - b) <= tol, `${what} ${a} vs ${b}`);
const load = (dir: string, name: string) => readNpy(path.join(dir, `${name}.npy`)).data;
const num = (dir: string, name: string) => Array.from(load(dir, name) as ArrayLike<number | bigint>, Number);
const quiet = () => undefined;

test('npy: every dtype, 1-D and 2-D, streamed in blocks, reads back; data starts on 64 bytes; numpy loads it', (t) => {
  const dir = tmpDir('oracle-npy-');
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const cases: Array<[Dtype, number[]]> = [
    ['int8', [-128, -1, 0, 1, 127]], ['uint8', [0, 1, 255]], ['int16', [-32768, -5, 0, 32767]], ['uint16', [0, 65535, 7]],
    ['int32', [-2147483648, 0, 2147483647]], ['int64', [Date.UTC(2026, 7, 1), -3, 0, 2 ** 53 - 1]], ['float32', [1.5, -2.25, NaN, 0]], ['float64', [Math.PI, -1e300, NaN, 0]],
  ];
  for (const [dt, xs] of cases) {
    const f = path.join(dir, `${dt}.npy`);
    writeNpy(f, typed(dt, xs));
    const r = readNpy(f);
    assert.equal(r.dtype, dt);
    assert.deepEqual(r.shape, [xs.length]);
    assert.equal(r.fortran, false);
    assert.equal(r.dataOffset % 64, 0, `${dt}: data offset ${r.dataOffset}`);
    assert.deepEqual(Array.from(r.data as ArrayLike<number | bigint>, Number).map((v) => (Number.isNaN(v) ? 'nan' : v)), xs.map((v) => (Number.isNaN(v) ? 'nan' : dt === 'float32' ? Math.fround(v) : v)));
  }
  // 2-D, C order, written in row blocks through one reused buffer.
  const w = new NpyWriter(path.join(dir, 'X.npy'), 'int8', [5, 3]);
  const buf = new Int8Array(2 * 3);
  for (let r0 = 0; r0 < 5; r0 += 2) {
    const nb = Math.min(5, r0 + 2) - r0;
    for (let r = 0; r < nb; r++) for (let c = 0; c < 3; c++) buf[r * 3 + c] = (r0 + r) * 10 + c - 20;
    w.write(buf.subarray(0, nb * 3));
  }
  w.close();
  const X = readNpy(path.join(dir, 'X.npy'));
  assert.deepEqual(X.shape, [5, 3]);
  assert.deepEqual(Array.from(X.data as Int8Array), [-20, -19, -18, -10, -9, -8, 0, 1, 2, 10, 11, 12, 20, 21, 22]);
  // A short stream fails and leaves nothing under the final name.
  const bad = new NpyWriter(path.join(dir, 'short.npy'), 'float32', [4]);
  bad.write(new Float32Array(3));
  assert.throws(() => bad.close(), /missing/);
  assert.equal(fs.existsSync(path.join(dir, 'short.npy')), false);
  assert.throws(() => new NpyWriter(path.join(dir, 'x.npy'), 'int8', [2]).write(new Int16Array(2)), /int16 != int8/);
  if (python) {
    const r = spawnSync(python, ['-c', [
      'import numpy as np, sys, json, glob, os',
      'out = {}',
      'for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.npy"))):',
      '    a = np.load(f, allow_pickle=False)',
      '    out[os.path.basename(f)] = [a.dtype.str, list(a.shape), bool(a.flags["C_CONTIGUOUS"]), float(np.nansum(a.astype(np.float64)))]',
      'print(json.dumps(out))',
    ].join('\n'), dir], { encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    const got = JSON.parse(r.stdout) as Record<string, [string, number[], boolean, number]>;
    assert.deepEqual(got['X.npy'].slice(0, 3), ['|i1', [5, 3], true]);
    assert.equal(got['X.npy'][3], [-20, -19, -18, -10, -9, -8, 0, 1, 2, 10, 11, 12, 20, 21, 22].reduce((a, b) => a + b, 0));
    for (const [dt, xs] of cases) {
      const [descr, shape, , sum] = got[`${dt}.npy`];
      assert.equal(descr.slice(1), { int8: 'i1', uint8: 'u1', int16: 'i2', uint16: 'u2', int32: 'i4', int64: 'i8', float32: 'f4', float64: 'f8' }[dt], dt);
      assert.deepEqual(shape, [xs.length]);
      near(sum, xs.filter((v) => !Number.isNaN(v)).reduce((a, b) => a + (dt === 'float32' ? Math.fround(b) : b), 0), Math.abs(sum) * 1e-12 + 1e-9, dt);
    }
  }
});

// A flat perp at 100 (every minute valid); the label test then moves single bars.
function flatGrid(asset: string, t0: number, n: number): Grid {
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Grid['c'];
  for (const k of ['so', 'sh', 'sl', 'sc', 'po', 'ph', 'pl', 'pc'] as const) c[k].fill(100);
  c.sv.fill(10); c.stb.fill(5); c.oi.fill(1e5); c.valid.fill(1);
  return { asset, t0, n, c, fundRaw: new Float32Array(n) };
}

test('labels: hand-computed take-profit, time exit, funding, best, latency, cost stress, $1,000 size and gaps', async (tc) => {
  const dir = tmpDir('oracle-lab-');
  tc.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const t0 = Date.UTC(2021, 0, 4), g = flatGrid('BTC', t0, 3 * 1440);
  g.c.ph[1008] = 102.5;                       // decision 1004: the long take-profit fills in minute 1008
  g.c.pc[2019] = 100.5; g.c.ph[2019] = 100.5; // decision 2004: the 15-minute time exit closes at 100.5
  g.c.fund[2010] = 0.0002;                    // a funding instant inside decision 2004's hold (+ BTC's 1.66 bps offset)
  g.c.valid[3010] = 0;                        // a missing minute
  const file = path.join(dir, 'BTC.bin');
  writeGrid(g, file);
  const r = await exportAsset({ grid: file, out: path.join(dir, 'parts'), modules: false, log: quiet });
  const P = r.perp;
  const t = num(P, 't'), rowOf = (i: number) => t.indexOf(t0 + (i + 1) * MIN);
  const c = costsFor('BTC'), A = Math.fround(1e-4);
  const tp = tpBps(300, c), tp2 = tpBps(1000, c);
  near(tp, 5e4 / 300 + 12 + 0.19 + 5 + 2, 1e-9, 'TP(300)');
  const taker = 12 + 0.19, fund = (0.0002 + 1.66e-4) * 1e4;
  const v = (name: string, i: number) => num(P, name)[rowOf(i)];

  // Decision 1004: long take-profit in minute 1008 (hold 4), net = TP - taker in - maker out = +$5.06 at $300.
  assert.ok(rowOf(1004) >= 0);
  assert.equal(v('hit_L15', 1004), 1); assert.equal(v('hold_L15', 1004), 4);
  near(v('trade_L15', 1004), ((tp * A * 1e4 - taker - 5) / 1e4) * 300, 1e-4, 'trade_L15');
  near(v('trade_L15', 1004), 5.06, 1e-4);
  assert.equal(v('hit_L60', 1004), 1); near(v('trade_L60', 1004), 5.06, 1e-4);
  // The short side times out flat at the close of minute 1019: both legs taker.
  assert.equal(v('hit_S15', 1004), 0); assert.equal(v('hold_S15', 1004), 15);
  near(v('trade_S15', 1004), (-2 * taker / 1e4) * 300, 1e-4, 'trade_S15');
  near(v('bestbps_L15', 1004), (102.5 / 1.0001 / 100 - 1) * 1e4 - taker - 5, 1e-3, 'bestbps_L15');
  near(v('best_L15', 1004), (((102.5 / 1.0001 / 100 - 1) * 1e4 - taker - 5) / 1e4) * 300, 1e-4);
  near(v('bestbps_S15', 1004), -(100 * 1.0001 / 100 - 1) * 1e4 - taker - 5, 1e-3, 'bestbps_S15');
  // $1,000: TP 69.19 bps, still filled at 1008: +$5.20; latency (decided at 1005, entry at 1006's open): same fill.
  near(tp2, 50 + 19.19, 1e-9);
  assert.equal(v('hit2_L15', 1004), 1); near(v('trade2_L15', 1004), ((tp2 - taker - 5) / 1e4) * 1000, 1e-3, 'trade2_L15');
  near(v('tradeLat_L15', 1004), 5.06, 1e-4, 'tradeLat_L15');
  // Cost stress: taker 17, maker 10, TP re-derived (195.86 bps; 102.5 still trades through it): +$5.06 again.
  near(v('tradeCost_L15', 1004), (((tp + 10) * A * 1e4 - (taker + 5) - 10) / 1e4) * 300, 1e-4, 'tradeCost_L15');

  // Decision 2004: no take-profit; 15-minute time exit at 100.5 (+50 bps), funding 3.66 bps paid by the long.
  assert.equal(v('hit_L15', 2004), 0); assert.equal(v('hold_L15', 2004), 15); assert.equal(v('hold_L60', 2004), 60);
  near(v('trade_L15', 2004), ((50 - 2 * taker - fund) / 1e4) * 300, 1e-4, 'trade_L15 2004');
  near(v('trade_S15', 2004), ((-50 - 2 * taker + fund) / 1e4) * 300, 1e-4, 'trade_S15 2004');
  near(v('trade_L60', 2004), ((-2 * taker - fund) / 1e4) * 300, 1e-4, 'trade_L60 2004');
  near(v('trade2_L15', 2004), ((50 - 2 * taker - fund) / 1e4) * 1000, 1e-3, 'trade2_L15 2004');
  near(v('tradeLat_L15', 2004), ((-2 * taker - fund) / 1e4) * 300, 1e-4, 'tradeLat_L15 2004'); // out at 2020 (flat)
  near(v('tradeCost_L15', 2004), ((50 - 2 * (taker + 5) - fund) / 1e4) * 300, 1e-4, 'tradeCost_L15 2004');
  near(v('bestbps_L15', 2004), (100.5 / 1.0001 / 100 - 1) * 1e4 - taker - 5, 1e-3);
  // t / hour / group / strata of that row (RV needs 7 days of labels: NA here, so no stratum).
  const tt = t0 + 2005 * MIN;
  assert.equal(v('hour', 2004), new Date(tt).getUTCHours());
  assert.equal(v('group', 2004), Math.floor(tt / DAY));
  assert.equal(v('rv', 2004), -1); assert.equal(v('stratum_L', 2004), -1);
  // The missing minute 3010: decisions entering at or holding across it are not tradable.
  assert.equal(rowOf(3009), -1, 'entry minute invalid: no row');
  assert.equal(rowOf(3004), -1, 'hold window crosses the gap at both horizons: no row');
  assert.equal(v('ok_L15', 2994), 1); assert.equal(v('ok_L60', 2994), 0);
  assert.ok(Number.isNaN(v('trade_L60', 2994))); assert.ok(Number.isNaN(v('best_L60', 2994))); assert.equal(v('hit_L60', 2994), 0);
  // Every row is a 5-minute close, sorted, and has the full label set.
  assert.ok(t.every((x, k) => ((x - t0) / MIN - 1) % 5 === 4 && (k === 0 || x > t[k - 1])));
  const meta = JSON.parse(fs.readFileSync(path.join(P, 'meta.json'), 'utf8'));
  assert.equal(meta.schema, 'oracle-part-1'); assert.equal(meta.ct, 'perp'); assert.equal(meta.n, t.length);
  assert.deepEqual(readNpy(path.join(P, 'X.npy')).shape, [t.length, meta.features.length]);
  for (const s of ['L', 'S']) for (const h of [15, 60]) for (const k of ['ok', 'hit', 'trade', 'best', 'hold', 'hit2', 'trade2', 'tradeLat', 'tradeCost', 'bestbps']) assert.ok(fs.existsSync(path.join(P, `${k}_${s}${h}.npy`)), `${k}_${s}${h}`);
});

test('no lookahead: perturbing every grid value after decision i leaves its feature row (perp and spot) unchanged; labels read i+1 on', async (t) => {
  const dir = tmpDir('oracle-nla-');
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const t0 = Date.UTC(2026, 6, 24), n = 12 * 1440; // Jul 24 - Aug 5 2026: ta_net's threshold sees Jul 24 - Jul 31 only
  const g = synthGrid('SOL', t0, n, 11);
  const hist = writeOthers1h(path.join(dir, 'hist'), ['BTC', 'ETH', 'XRP'], t0 - 10 * DAY, t0 + n * MIN, 5);
  const f0 = writeGridTmp(g, path.join(dir, 'a'));
  const iStar = (Date.UTC(2026, 7, 3, 12, 4) - t0) / MIN; // the minute opening 12:04 on Aug 3 ends on a 5-minute close
  assert.equal(iStar % 5, 4);
  const p = synthGrid('SOL', t0, n, 11);
  for (let j = iStar + 1; j < n; j++) {
    const f = 1 + 0.03 * Math.sin(j / 7), q = 1 - 0.02 * Math.cos(j / 3);
    for (const k of ['so', 'sh', 'sl', 'sc'] as const) p.c[k][j] *= f;
    for (const k of ['po', 'ph', 'pl', 'pc'] as const) p.c[k][j] *= q;
    p.c.sv[j] *= 3; p.c.stb[j] *= 0.2; p.c.oi[j] *= 2; if (p.c.fund[j]) p.c.fund[j] = 0.003;
  }
  const f1 = writeGridTmp(p, path.join(dir, 'b'));
  const ra = await exportAsset({ grid: f0, history: hist, out: path.join(dir, 'pa'), spotFrom: t0, log: quiet });
  const rb = await exportAsset({ grid: f1, history: hist, out: path.join(dir, 'pb'), spotFrom: t0, log: quiet });
  const meta = JSON.parse(fs.readFileSync(path.join(ra.perp, 'meta.json'), 'utf8')) as { features: Array<{ name: string; kind: string }> };
  const names = meta.features.map((x) => x.name);
  // The column list depends on data before DEV_END only (analyzer readings that never fire there are left out).
  assert.deepEqual(rb.features, ra.features);
  // The modules ran: analyzer, TA-Lib, ta_net, character and HT buckets; no forecast reading.
  for (const want of [/^ta:/, /^conf:/, /^cdl_/, /^tl_/, /^ta_net$/, /^ctx:char$/, /^ctx:ht_mode$/, /^ctx:rv$/, /^ctx:trend60$/]) assert.ok(names.some((x) => want.test(x)), `missing ${want}`);
  assert.ok(!names.some((x) => /^(tanet|lib_|xg_)/.test(x)));
  const F = names.length;
  const ta = num(ra.perp, 't'), tb = num(rb.perp, 't');
  assert.deepEqual(tb, ta, 'valid flags unchanged: the same rows');
  const XA = load(ra.perp, 'X') as Int8Array, XB = load(rb.perp, 'X') as Int8Array;
  const tStar = t0 + (iStar + 1) * MIN, rStar = ta.indexOf(tStar);
  assert.ok(rStar > 0);
  for (let r = 0; r <= rStar; r++) for (let f = 0; f < F; f++) if (XA[r * F + f] !== XB[r * F + f]) assert.fail(`row ${r} (t ${new Date(ta[r]).toISOString()}) feature ${names[f]}: ${XA[r * F + f]} vs ${XB[r * F + f]}`);
  let later = 0;
  for (let r = rStar + 1; r < ta.length; r++) for (let f = 0; f < F; f++) if (XA[r * F + f] !== XB[r * F + f]) later++;
  assert.ok(later > 0, 'the perturbation reaches later feature rows');
  // Bucket readings at the decision are live (not all NA) on this grid.
  const col = (name: string) => names.indexOf(name);
  for (const b of ['ctx:char', 'ctx:ht_mode', 'ctx:rv', 'ctx:trend60']) assert.ok(XA[rStar * F + col(b)] >= 0, `${b} NA at the decision`);
  // Labels: a decision whose window (and latency window) ends by minute i* is unchanged; decision i* itself reads i*+1 on.
  for (const name of ['trade_L15', 'trade_S60', 'best_L60', 'hold_S15', 'hit_L60', 'tradeLat_L15', 'tradeCost_S60', 'bestbps_S15']) {
    const a = num(ra.perp, name), b = num(rb.perp, name), h = Number(name.slice(-2));
    const lat = name.startsWith('tradeLat') ? 1 : 0;
    for (let r = 0; r < ta.length; r++) {
      const i = (ta[r] - t0) / MIN - 1;
      if (i + h + lat <= iStar) assert.ok(Object.is(a[r], b[r]) || (Number.isNaN(a[r]) && Number.isNaN(b[r])), `${name} row ${r} changed`);
    }
  }
  assert.notEqual(num(ra.perp, 'trade_L15')[rStar], num(rb.perp, 'trade_L15')[rStar], 'the label of decision i* is its future');
  // The spot part: rows of minutes <= i* unchanged; the spot row of minute i equals the perp row of decision i.
  const sa = num(ra.spot, 't_end'), mStar = sa.indexOf(tStar);
  assert.equal(sa[0], t0 + MIN); assert.equal(mStar, iStar);
  const SA = load(ra.spot, 'X') as Int8Array, SB = load(rb.spot, 'X') as Int8Array;
  for (let m = 0; m <= mStar; m++) for (let f = 0; f < F; f++) if (SA[m * F + f] !== SB[m * F + f]) assert.fail(`spot minute ${m} feature ${names[f]} changed`);
  for (const name of ['close', 'rv60', 'rv']) { const a = num(ra.spot, name), b = num(rb.spot, name); for (let m = 0; m <= mStar; m++) assert.ok(Object.is(a[m], b[m]), `spot ${name} minute ${m}`); }
  for (const r of [rStar, rStar - 7, 300]) {
    const i = (ta[r] - t0) / MIN - 1;
    for (let f = 0; f < F; f++) assert.equal(SA[i * F + f], XA[r * F + f], `spot minute ${i} vs perp row ${r}: ${names[f]}`);
  }
  // RV60 is the regime v1 definition at the end of the minute: sqrt of the sum of the last 60 squared log returns.
  const rv = num(ra.spot, 'rv60'), m = mStar;
  let ss = 0; for (let j = m - 59; j <= m; j++) { const x = Math.log(g.c.sc[j] / g.c.sc[j - 1]); ss += x * x; }
  near(rv[m], Math.sqrt(ss), 1e-6, 'rv60');
});

test('nothing at or after 2026-11-05 is read; DOGE and unknown coins are refused', async (tc) => {
  const dir = tmpDir('oracle-cap-');
  tc.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const t0 = Date.UTC(2026, 9, 30), g = synthGrid('XRP', t0, 9 * 1440, 3); // Oct 30 - Nov 8
  for (let j = (HOLD_TO - t0) / MIN; j < g.n; j++) for (const k of COLS) g.c[k][j] = NaN; // a lockbox that must never show up
  const file = writeGridTmp(g, dir);
  assert.equal(readGridCapped(file).n, (HOLD_TO - t0) / MIN);
  const r = await exportAsset({ grid: file, out: path.join(dir, 'parts'), modules: false, spotFrom: t0, log: quiet });
  const t = num(r.perp, 't'), te = num(r.spot, 't_end');
  assert.ok(Math.max(...t) + 15 * MIN <= HOLD_TO && te[te.length - 1] === HOLD_TO && te.length === (HOLD_TO - t0) / MIN);
  for (const name of ['trade_L15', 'best_S15', 'tradeLat_L15', 'tradeCost_S15']) { const ok = num(r.perp, 'ok_' + name.slice(-3)); assert.ok(num(r.perp, name).every((x, k) => Number.isNaN(x) || ok[k] === 1), name); }
  assert.ok(Array.from(load(r.spot, 'close') as Float64Array).every(Number.isFinite));
  assert.ok(t.every((x) => x >= DEV_END)); // all HO-1 rows here: written, never summarised in the log
  // DOGE: by name, by grid header, and in the fixtures.
  assert.throws(() => assertAsset('DOGE'), /DOGE refused/);
  assert.throws(() => assertAsset('ADA'), /not one of/);
  const d = synthGrid('DOGE', t0, 3 * 1440, 1);
  const df = writeGridTmp(d, path.join(dir, 'doge'));
  await assert.rejects(exportAsset({ grid: df, out: path.join(dir, 'parts'), modules: false, log: quiet }), /DOGE refused/);
  const hidden = path.join(dir, 'hidden.bin');
  fs.copyFileSync(df, hidden);
  assert.throws(() => readGridCapped(hidden), /DOGE refused/);
  await assert.rejects(exportAsset({ grid: hidden, out: path.join(dir, 'parts'), modules: false, log: quiet }), /DOGE refused/);
  assert.throws(() => writeOthers1h(path.join(dir, 'h'), ['DOGE'], t0, t0 + DAY, 1), /DOGE refused/);
  assert.ok(!fs.existsSync(path.join(dir, 'parts', 'perp-DOGE')) && !fs.existsSync(path.join(dir, 'parts', 'spot-DOGE')));
});

// regime.ts against regime.py itself (origin/claude/project-thread-79ntof research/regime.py, read with git show): RV60,
// tercile, z60 and the trend bucket on a fixture CSV with holes. Skipped without python3 or that branch.
const regimePy = (() => { const r = spawnSync('git', ['show', 'origin/claude/project-thread-79ntof:research/regime.py'], { encoding: 'utf8', maxBuffer: 1 << 24 }); return r.status === 0 ? r.stdout : undefined; })();
test('regime v1: research/oracle/regime.ts matches research/regime.py minute by minute', { skip: !python || !regimePy ? 'python3 or regime.py not available' : false }, async (t) => {
  const { rv60, tercilesFromRv, z60, trendBucket, spotFromCsv } = await import('../research/oracle/regime');
  const dir = tmpDir('oracle-reg-');
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const t0 = Date.UTC(2026, 3, 1), n = 10 * 1440, g = synthGrid('ETH', t0, n, 9);
  const hole = (i: number) => (i >= 3000 && i < 3030) || i === 9000 || (i >= 12000 && i < 12100);
  const lines = ['ts,o,h,l,c,v'];
  for (let i = 0; i < n; i++) if (!hole(i)) lines.push(`${t0 + i * MIN},${g.c.so[i]},${g.c.sh[i]},${g.c.sl[i]},${g.c.sc[i]},${g.c.sv[i]}`);
  fs.mkdirSync(path.join(dir, 'csv', 'ETH'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'csv', 'ETH', '1m.csv'), lines.join('\n') + '\n');
  fs.writeFileSync(path.join(dir, 'regime.py'), regimePy!);
  const r = spawnSync(python!, [path.join(dir, 'regime.py'), 'label', path.join(dir, 'csv'), path.join(dir, 'ref.csv'), '--assets', 'ETH'], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const sp = (await spotFromCsv(path.join(dir, 'csv', 'ETH', '1m.csv'), t0, n))!;
  const bar = (i: number) => i < n && sp.has[i] === 1, close = (i: number) => sp.close[i];
  const rv = rv60(n + 1, bar, close), ter = tercilesFromRv(t0, rv), z = z60(rv, bar, close);
  const TER: Record<string, number> = { LOW: 0, MID: 1, HIGH: 2, NA: -1 };
  let k = 0, labelled = 0;
  for (const line of fs.readFileSync(path.join(dir, 'ref.csv'), 'utf8').trim().split(/\r?\n/).slice(1)) {
    const [ts, , rvS, , , terS, zS, trend] = line.split(',');
    const i = (Date.parse(ts) - t0) / MIN;
    k++;
    const rr = rvS === '' ? NaN : Number(rvS), zz = zS === '' ? NaN : Number(zS);
    assert.ok(Number.isNaN(rr) ? Number.isNaN(rv[i]) : Math.abs(rv[i] - rr) <= 1e-9 * Math.max(1, rr), `rv60 ${ts}`);
    assert.equal(ter[i], TER[terS], `tercile ${ts}`);
    assert.ok(Number.isNaN(zz) ? Number.isNaN(z[i]) : Math.abs(z[i] - zz) <= 1e-6 * Math.max(1, Math.abs(zz)), `z60 ${ts}`);
    const b = trendBucket(z[i]);
    assert.equal(trend === 'NA' ? -1 : trend === 'FLAT' ? 2 : trend === 'TREND' ? (zz > 0 ? 3 : 1) : (zz > 0 ? 4 : 0), b, `trend ${ts}`);
    if (ter[i] >= 0) labelled++;
  }
  assert.ok(k > 0.98 * n && labelled > 1000, `${k} minutes compared, ${labelled} with a tercile`);
});

// The cross-language interface (SPEC.md 1, 2a -> 2b, 3): the exporter's parts load in python/oracle, pp.py builds a pp15
// and a pp60 part from Kalshi markets priced on the exporter's own spot part (oracle.fixtures_pp make_aligned) with every
// decision joined to the spot minute that ENDS at it, and the miner's load_dev cuts the perp part at DEV_END. Skipped
// without python3 + numpy, scipy and numba (the CI test job installs python/oracle/requirements.txt first).
const pyStack = python && spawnSync(python, ['-c', 'import numpy, scipy, numba'], { encoding: 'utf8' }).status === 0;
test('the parts feed the Python pieces: Part, pp.py (15 and 60) on the spot part, mine.load_dev at DEV_END', { skip: pyStack ? false : 'python3 with numpy, scipy and numba not available' }, async (t) => {
  const dir = tmpDir('oracle-py-');
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const t0 = Date.UTC(2026, 6, 28), n = 8 * 1440; // Jul 28 - Aug 5: rows on both sides of DEV_END
  const file = writeGridTmp(synthGrid('BTC', t0, n, 21), path.join(dir, 'g'));
  const r = await exportAsset({ grid: file, out: path.join(dir, 'parts'), modules: false, spotFrom: t0 + DAY, log: quiet });
  const script = [
    'import json, sys, numpy as np',
    'from oracle.common import Part, DEV_END, MIN, split_of',
    'from oracle.fixtures_pp import make_aligned',
    'from oracle import pp',
    'from oracle.mine import load_dev',
    'root, perp, spot = sys.argv[1:4]',
    'sp = Part(spot)',
    "out = {'spot_n': sp.n, 'spot_F': int(sp['X'].shape[1]), 'spot_ct': sp.ct}",
    "fx = make_aligned(root, spot, 'BTC', '2026-07-30', 3)",
    'for kind in (15, 60):',
    "    q = Part(pp.build(kind, fx['history'], spot, 'BTC', root + '/parts', code_sha='test', log=lambda m: None))",
    "    t, te = np.asarray(q['t']), np.asarray(sp['t_end'])",
    '    i = np.searchsorted(te, t)',
    "    F = sp['X'].shape[1]",
    "    joined = bool(np.all(te[i] == t) and np.array_equal(np.asarray(q['X'])[:, :F], np.asarray(sp['X'])[i]) and np.array_equal(np.asarray(q['rv']), np.asarray(sp['rv'])[i]))",
    "    s = split_of(t, kind, q.ct)",
    "    out[q.ct] = {'n': q.n, 'joined': joined, 'B': int((s == 'B').sum()), 'H': int((s == 'H').sum()), 'names_ok': [f['name'] for f in q.features[:F]] == [f['name'] for f in sp.features]}",
    "v = load_dev(perp, 'perp')",
    "out['perp'] = {'rows_total': v.meta['rows_total'], 'dev_rows': v.meta['dev_rows'], 'dev_ok': bool(np.all(np.asarray(v['t']) + 15 * MIN <= DEV_END))}",
    'print(json.dumps(out))',
  ].join('\n');
  const py = spawnSync(python!, ['-c', script, dir, r.perp, r.spot], { cwd: path.join(process.cwd(), 'python'), encoding: 'utf8', maxBuffer: 1 << 24 });
  assert.equal(py.status, 0, py.stderr);
  const o = JSON.parse(py.stdout.trim().split('\n').pop()!);
  assert.equal(o.spot_ct, 'spot'); assert.equal(o.spot_n, r.nSpot); assert.equal(o.spot_F, r.features.length);
  for (const ct of ['pp15', 'pp60']) {
    assert.ok(o[ct].n > 0 && o[ct].joined && o[ct].names_ok, `${ct}: ${JSON.stringify(o[ct])}`);
    assert.ok(o[ct].B > 0 && o[ct].H > 0, `${ct}: rows in B and in HO-1`);
  }
  assert.ok(o.perp.dev_ok && o.perp.dev_rows > 0 && o.perp.dev_rows < o.perp.rows_total, JSON.stringify(o.perp));
});

// ---------------------------------------------------------------------------------------------------------------
// OR-H2 reversal export (python/oracle/prereg/OR-H2.md): triple-barrier labels, sizing, parts per (coin, M), features.
import { revFeatures, REV_TFS } from '../research/oracle/reversalFeatures';
import { revPlan, revNotional, revTpBps } from '../research/oracle/oracleExport';

test('reversal plan: S = M/2, 5 minutes only for M <= 60, notional min($300, $5/(M/1e4)), refusals', () => {
  const p = revPlan('BTC', [30, 60, 100, 170]);
  assert.deepEqual(p.map((x) => x.dir), ['perp-rev-BTC-m30', 'perp-rev-BTC-m60', 'perp-rev-BTC-m100', 'perp-rev-BTC-m170']);
  assert.deepEqual(p.map((x) => x.S), [15, 30, 50, 85]);
  assert.deepEqual(p.map((x) => x.horizons), [[5, 15, 60], [5, 15, 60], [15, 60], [15, 60]]);
  near(p[0].notional, 300, 1e-9); near(p[2].notional, 300, 1e-9); near(p[3].notional, 5e4 / 170, 1e-9); near(revNotional(40), 300, 1e-9);
  assert.equal(revPlan('ETH', [60], [20], [15, 5])[0].S, 20);
  assert.deepEqual(revPlan('ETH', [60], undefined, [60, 5, 15, 5])[0].horizons, [5, 15, 60]);
  assert.throws(() => revPlan('BTC', [60, 100], [10, 20, 30]), /one value or one per target/);
  assert.throws(() => revPlan('BTC', [0]), /positive/);
  assert.throws(() => revPlan('BTC', [60, 60]), /duplicate/);
  assert.throws(() => revPlan('BTC', [100], undefined, [5]), /no horizon left/);
  near(revTpBps(60, costsFor('BTC')), 60 + 12 + 0.19 + 5 + 2, 1e-9);
});

test('reversal labels: hand-computed triple barrier (take-profit, stop, both in one bar, time exit), sizing, part layout', async (tc) => {
  const dir = tmpDir('oracle-rev-');
  tc.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const t0 = Date.UTC(2021, 0, 4), g = flatGrid('BTC', t0, 3 * 1440);
  g.c.ph[1008] = 101;                                   // decision 1004: long take-profit (79.19 bps) in minute 1008; the short's 30 bps stop is hit there
  g.c.ph[2007] = 100.4;                                 // decision 2004: short stopped in 2007; the long neither fills nor stops (time exit)
  g.c.ph[3006] = 101; g.c.pl[3006] = 99.5;              // decision 3004: one bar reaches both the long take-profit and the long stop: the stop
  const file = path.join(dir, 'BTC.bin');
  writeGrid(g, file);
  const r = await exportAsset({ grid: file, out: path.join(dir, 'parts'), modules: false, targetBps: [60, 170], log: quiet });
  assert.deepEqual(r.parts.map((p) => path.basename(p)), ['perp-rev-BTC-m60', 'perp-rev-BTC-m170']);
  assert.ok(!fs.existsSync(path.join(dir, 'parts', 'perp-BTC')) && !fs.existsSync(path.join(dir, 'parts', 'spot-BTC')), 'no perp or spot part in reversal mode');
  const P = r.parts[0], P2 = r.parts[1];
  const t = num(P, 't'), rowOf = (i: number) => t.indexOf(t0 + (i + 1) * MIN), v = (name: string, i: number) => num(P, name)[rowOf(i)];
  const taker = 12 + 0.19, N = 300, usd = (bps: number) => (bps / 1e4) * N;
  // (a) 1004: long TP nets M + 2 = 62 bps (tp 79.19 - taker 12.19 - maker 5); short stopped at -30 bps price: -30 - 2 x 12.19.
  assert.equal(v('hit_L5', 1004), 1); assert.equal(v('hold_L5', 1004), 4);
  near(v('trade_L5', 1004), usd(62), 1e-3, 'trade_L5'); near(v('trade_L15', 1004), usd(62), 1e-3); near(v('trade_L60', 1004), usd(62), 1e-3);
  assert.equal(v('hit_S5', 1004), 0); assert.equal(v('hold_S5', 1004), 4);
  near(v('trade_S5', 1004), usd(-30 - 2 * taker), 1e-3, 'trade_S5 stop');
  // cost stress: taker 17 / maker 10, TP re-derived (still +62 bps), the stop costs 30 + 2 x 17.19.
  near(v('tradeCost_L5', 1004), usd(62), 1e-3, 'tradeCost_L5'); near(v('tradeCost_S5', 1004), usd(-30 - 2 * (taker + 5)), 1e-3, 'tradeCost_S5');
  // (b) 2004: the long times out flat at the close of minute 2009 (both legs taker); the short is stopped in 2007 (hold 3).
  assert.equal(v('hit_L5', 2004), 0); assert.equal(v('hold_L5', 2004), 5);
  near(v('trade_L5', 2004), usd(-2 * taker), 1e-3, 'time exit'); near(v('trade_L60', 2004), usd(-2 * taker), 1e-3);
  assert.equal(v('hold_S5', 2004), 3); near(v('trade_S5', 2004), usd(-30 - 2 * taker), 1e-3);
  // (c) 3004: a bar that reaches both the take-profit and the stop is the stop (hit 0), for the long and (ph 101 >= 100.3) the short.
  assert.equal(v('hit_L5', 3004), 0); near(v('trade_L5', 3004), usd(-30 - 2 * taker), 1e-3, 'both in one bar');
  assert.equal(v('hit_L15', 3004), 0); near(v('trade_L15', 3004), usd(-30 - 2 * taker), 1e-3);
  // notional per row, meta, layout.
  const meta = JSON.parse(fs.readFileSync(path.join(P, 'meta.json'), 'utf8'));
  assert.equal(meta.ct, 'perp-rev'); assert.equal(meta.scope, 'BTC-m60'); assert.equal(meta.target_bps, 60); assert.equal(meta.stop_bps, 30);
  assert.deepEqual(meta.horizons, [5, 15, 60]); assert.deepEqual(meta.sides, ['L', 'S']); assert.equal(meta.n, t.length); assert.equal(meta.step_min, 5);
  assert.ok(num(P, 'notional').every((x) => x === 300));
  for (const f of ['vwap_dist60@1m', 'vwap_distday@1m', 'ma_stack@5m', 'rsi70_30@5m', 'dist_hi12@15m', 'since_lo48@1m', 'tflow_spike@5m']) assert.ok(meta.features.some((x: { name: string }) => x.name === `rev:${f}`), f);
  assert.ok(meta.features.every((x: { desc: string }) => x.desc.length > 10));
  assert.ok(fs.existsSync(path.join(P, 'trade_L5.npy')) && !fs.existsSync(path.join(P, 'hit2_L5.npy')) && !fs.existsSync(path.join(P, 'trade2_L15.npy')));
  assert.ok(t.every((x, k) => ((x - t0) / MIN - 1) % 5 === 4 && (k === 0 || x > t[k - 1])));
  const meta2 = JSON.parse(fs.readFileSync(path.join(P2, 'meta.json'), 'utf8'));
  assert.equal(meta2.scope, 'BTC-m170'); assert.deepEqual(meta2.horizons, [15, 60]); near(meta2.notional_usd, 5e4 / 170, 1e-3);
  assert.ok(!fs.existsSync(path.join(P2, 'trade_L5.npy')));
  // M = 170: take-profit 189.19 bps never reached here, stop 85: the 1008 spike (+100 bps) is below the TP: long times out; the short is stopped (> 85 bps).
  const t2 = num(P2, 't'), row2 = t2.indexOf(t0 + 1005 * MIN), N2 = 5e4 / 170;
  near(num(P2, 'trade_L15')[row2], ((-2 * taker) / 1e4) * N2, 1e-3, 'M170 long time exit');
  near(num(P2, 'trade_S15')[row2], ((-85 - 2 * taker) / 1e4) * N2, 1e-3, 'M170 short stop');
  if (python) {
    const q = spawnSync(python, ['-c', 'import sys, json\nfrom oracle.common import Part, list_parts, group_of\nr = sys.argv[1]\nprint(json.dumps([[Part(p).scope, group_of(Part(p).meta), Part(p).n] for p in list_parts(r, "perp-rev")]))', path.join(dir, 'parts')], { cwd: path.join(process.cwd(), 'python'), encoding: 'utf8' });
    if (q.status === 0) assert.deepEqual(JSON.parse(q.stdout.trim()).map((x: unknown[]) => [x[0], x[1]]), [['BTC-m170', 'm170'], ['BTC-m60', 'm60']]);
  }
});

function rampGrid(n: number, f: (i: number) => number): Grid {
  const g = flatGrid('BTC', Date.UTC(2021, 0, 4), n);
  for (let i = 0; i < n; i++) for (const k of ['so', 'sh', 'sl', 'sc', 'po', 'ph', 'pl', 'pc'] as const) g.c[k][i] = f(i);
  return g;
}

test('reversal features: vwap_dist buckets and ma_stack by hand; every reading is closed-bar and causal', () => {
  const at = (fs_: ReturnType<typeof revFeatures>, name: string) => fs_.find((x) => x.name === name)!.at;
  // VWAP: flat 100, minute 200 closes at 100.3 (30 bps): rolling 60 = 100 + 0.3/60, day-anchored = 100 + 0.3/201.
  const g = flatGrid('BTC', Date.UTC(2021, 0, 4), 1000);
  g.c.sc[200] = 100.3; g.c.sh[200] = 100.3;
  let f = revFeatures(g, g.n);
  const roll = at(f, 'rev:vwap_dist60@1m'), day = at(f, 'rev:vwap_distday@1m');
  const c3 = Math.fround(100.3);
  near(((c3 - (100 + (c3 - 100) / 60)) / c3) * 1e4, 29.4, 0.1, 'hand value of the rolling distance (bps)'); // bucket 3 is 15..50
  assert.equal(roll(200), 3); assert.equal(day(200), 3); assert.equal(roll(201), 2, 'back to ~0 next minute');
  assert.equal(roll(30), -1, 'rolling VWAP needs 60 bars'); assert.equal(day(30), 2, 'the day-anchored one exists from the first bar');
  g.c.sc[500] = 100.6; g.c.sh[500] = 100.6;                   // 60 bps: > 50
  f = revFeatures(g, g.n);
  assert.equal(at(f, 'rev:vwap_dist60@1m')(500), 4); assert.equal(at(f, 'rev:vwap_distday@1m')(500), 4);
  g.c.sc[700] = 99.4; g.c.sl[700] = 99.4;                     // -60 bps
  f = revFeatures(g, g.n);
  assert.equal(at(f, 'rev:vwap_dist60@1m')(700), 0);
  // MA stack on 5m closes: a rising ramp stacks +1 once 200 five-minute bars exist (minute 999), falling -1, flat 0.
  const up = revFeatures(rampGrid(3000, (i) => 100 + 0.01 * i), 3000), dn = revFeatures(rampGrid(3000, (i) => 200 - 0.01 * i), 3000), fl = revFeatures(rampGrid(3000, () => 100), 3000);
  assert.equal(at(up, 'rev:ma_stack@5m')(2999), 1); assert.equal(at(dn, 'rev:ma_stack@5m')(2999), -1); assert.equal(at(fl, 'rev:ma_stack@5m')(2999), 0);
  assert.equal(at(up, 'rev:ma_stack@5m')(900), 0, 'fewer than 200 five-minute bars: no reading');
  assert.equal(at(up, 'rev:ma_stack@5m')(1003), 1);
  assert.equal(at(up, 'rev:ma_stack@5m')(1003), at(up, 'rev:ma_stack@5m')(1004 - 1)); // the bar closed at minute 1004 is not readable at 1003
  const kinds = new Set(up.map((x) => x.kind));
  assert.ok(kinds.has('state') && kinds.has('bucket') && REV_TFS.length === 3);
  assert.ok(up.every((x) => x.name.startsWith('rev:') && x.desc.length > 10));
});

test('reversal features: no lookahead (every value after minute i* perturbed leaves every reading at <= i* unchanged)', () => {
  const t0 = Date.UTC(2026, 6, 24), n = 6 * 1440, a = synthGrid('SOL', t0, n, 5), b = synthGrid('SOL', t0, n, 5);
  const iStar = 3 * 1440 + 12 * 60 + 4;
  for (let j = iStar + 1; j < n; j++) {
    const f = 1 + 0.04 * Math.sin(j / 5);
    for (const k of ['so', 'sh', 'sl', 'sc'] as const) b.c[k][j] *= f;
    b.c.sv[j] *= 4; b.c.stb[j] *= 0.1;
  }
  const fa = revFeatures(a, n), fb = revFeatures(b, n);
  assert.deepEqual(fa.map((x) => x.name), fb.map((x) => x.name));
  assert.ok(fa.length >= 75, `${fa.length} reversal features`);
  let live = 0, later = 0;
  for (let k = 0; k < fa.length; k++) {
    for (let i = 0; i <= iStar; i += 1) if (fa[k].at(i) !== fb[k].at(i)) assert.fail(`${fa[k].name} at minute ${i} (<= i*) changed`);
    for (let i = iStar + 1; i < n; i += 7) if (fa[k].at(i) !== fb[k].at(i)) { later++; break; }
    if (Array.from({ length: 400 }, (_, q) => fa[k].at(1000 + q * 7)).some((x) => x !== fa[k].at(1000))) live++;
  }
  assert.ok(later > 20, `the perturbation reaches later readings (${later} features)`);
  assert.ok(live > 40, `${live} features vary on the synthetic grid`);
});
