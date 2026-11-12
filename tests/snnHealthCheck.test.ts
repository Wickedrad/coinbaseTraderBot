import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { aggregate, buildHistoryReplay } from '../research/history/historyReplay';
import {
  auc, brierSkill, chanName, classifyDead, HealthSampler, momentumSign, overall, phiZeroByDesign, prequentialBase, prequentialMomentum,
  reportCmd, RULE, signMomentumAccuracy, slopeB, spreadStats, unrelaxWf, verdict, withinSd, type ArmStats, type Ci, type DirRow, type PxMap, type SampleRow,
} from '../research/snnHealthCheck';
import { trainParams } from '../research/snnHistoryTrain';
import { replaySnn } from '../research/snnReplay';
import { logit, twoSpeedStep } from '../bot/snn/formulas';
import { l0Width } from '../bot/snn/inputs';
import { SnnNetwork } from '../bot/snn/network';
import { rng } from '../research/stats';
import { tmpDir } from './helpers';

const MIN = 60_000;

test('health check: slope with intercept and fixed effects, b0.5, spread stats, AUC and Brier skill', () => {
  const r = rng(11), n = 50_000;
  const p: number[] = [], y: number[] = [], yi: number[] = [], day: string[] = [];
  for (let i = 0; i < n; i++) {
    const q = 0.3 + 0.4 * r();
    p.push(q); y.push(r() < q ? 1 : 0); yi.push(r() < 0.5 ? 1 : 0); day.push(`d${i % 50}`);
  }
  const fe = slopeB(p, y, { day, group: day });
  assert.ok(Math.abs(fe.est - 1) < 0.1, `calibrated slope ${fe.est}`);
  assert.ok(fe.lo < 1 && fe.hi > 1, `the CI [${fe.lo}, ${fe.hi}] contains the truth`);
  const b05 = slopeB(p.map((x) => x - 0.5), y.map((x) => x - 0.5), { day, intercept: false });
  assert.ok(Math.abs(b05.est - 1) < 0.1, `b0.5 ${b05.est}`);
  const ind = slopeB(p, yi, { day, group: day });
  assert.ok(Math.abs(ind.est) < 0.1 && ind.lo < 0 && ind.hi > 0, `independent label: slope ${ind.est} [${ind.lo}, ${ind.hi}]`);

  // A head that learned only its bias (critique #1): p sits at the up-rate with noise unrelated to y. Through the origin
  // b0.5 is ~1 and the spread passes; the fixed-effects slope and the AUC see nothing.
  const pb: number[] = [], yb: number[] = [];
  for (let i = 0; i < n; i++) { pb.push(0.56 + 0.002 * (r() - 0.5)); yb.push(r() < 0.56 ? 1 : 0); }
  const bb = slopeB(pb.map((x) => x - 0.5), yb.map((x) => x - 0.5), { day, intercept: false });
  assert.ok(Math.abs(bb.est - 1) < 0.1, `bias-only b0.5 ${bb.est}`);
  const bfe = slopeB(pb, yb, { day, group: day });
  assert.ok(bfe.lo < 0.7, `bias-only FE slope CI lower ${bfe.lo}`);
  assert.ok(auc(pb, yb, { day, group: day }).lo < 0.5);

  const s = spreadStats([0.4, 0.5, 0.6, 0.7, 0.3]);
  assert.ok(Math.abs(s.meanAbsPp - 12) < 1e-9);
  assert.ok(Math.abs(s.sd - Math.sqrt(0.1 / 4)) < 1e-12);
  assert.ok(Math.abs(s.p10 - 0.34) < 1e-12 && Math.abs(s.p50 - 0.5) < 1e-12 && Math.abs(s.p90 - 0.66) < 1e-12);
  assert.ok(Math.abs(s.a10 - 4) < 1e-9 && Math.abs(s.a50 - 10) < 1e-9 && Math.abs(s.a90 - 20) < 1e-9);
  assert.ok(Number.isNaN(spreadStats([]).meanAbsPp));

  // AUC: perfect ranking 1, ties count half, a per-group offset carries no credit when stratified.
  assert.equal(auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]).est, 1);
  assert.equal(auc([0.5, 0.5], [0, 1]).est, 0.5);
  const pg: number[] = [], yg: number[] = [], g: string[] = [];
  for (let i = 0; i < 20_000; i++) { const hi = i % 2; pg.push(hi ? 0.7 + 0.01 * r() : 0.3 + 0.01 * r()); yg.push(r() < (hi ? 0.7 : 0.3) ? 1 : 0); g.push(hi ? 'a' : 'b'); }
  assert.ok(auc(pg, yg).est > 0.65, 'pooled: the offset ranks');
  assert.ok(Math.abs(auc(pg, yg, { group: g }).est - 0.5) < 0.03, 'stratified: no within-group signal');
  // Within-group sd ignores the offsets.
  assert.ok(withinSd(pg, g) < 0.01 && withinSd(pg) > 0.15);
  // Brier skill: the reference itself is 0; the truth beats a coin flip.
  assert.equal(brierSkill(p, p, y).est, 0);
  const sk = brierSkill(p, p.map(() => 0.5), y, { day });
  assert.ok(sk.est > 0 && sk.lo > 0, `skill vs 0.5 ${sk.est} [${sk.lo}, ${sk.hi}]`);
});

test('health check: prequential baselines admit a label only once it matured (tag + H <= now)', () => {
  const k = 'BTC-15m', H = 900_000;
  // Tag 0 is down; every later tag is up. At t = 900 s only tag 0 has matured.
  const rows = [{ k, t: 0, y: 0 }, ...Array.from({ length: 14 }, (_, i) => ({ k, t: (i + 1) * MIN, y: 1 })), { k, t: H, y: 1 }];
  const base = prequentialBase(rows);
  assert.equal(base[0], 0.5, 'no data: 0.5');
  assert.equal(base[1], 0.5, 'tag 0 not matured yet at 60 s');
  assert.equal(base[15], 1 / 3, 'at 900 s: the prior plus tag 0 only (the 14 immature ups would make it > 0.5)');
  assert.ok(base[15] < 0.5);
  // Row order does not matter (sorted by column and time inside).
  assert.deepEqual(prequentialBase([...rows].reverse()).reverse(), base);
  // Other columns are separate counts, with their own horizon.
  assert.equal(prequentialBase([{ k: 'ETH-60m', t: 0, y: 1 }, { k: 'ETH-60m', t: H, y: 1 }])[1], 0.5, '60m: not matured at 900 s');

  // Momentum: every tag sees an up move over 5 min.
  const px: PxMap = new Map([['BTC', new Map<number, number>()]]);
  for (let t = -10 * MIN; t <= H; t += MIN) px.get('BTC')!.set(t, 100 + t / MIN);
  const mom = prequentialMomentum(rows, px, 5);
  assert.equal(mom[0], 0.5, 'no matured data for s = +1: (0 + 1) / (0 + 2)');
  assert.equal(mom[14], 0.5, 'still nothing matured at 840 s');
  assert.equal(mom[15], 1 / 3, 'at 900 s: tag 0 (s = +1, down) only');
});

test('health check: momentum signs, the fallback to the base rate, and plain sign momentum', () => {
  const px: PxMap = new Map([['BTC', new Map<number, number>([[0, 100], [5 * MIN, 101], [10 * MIN, 100], [15 * MIN, 100]])]]);
  assert.equal(momentumSign(px, 'BTC', 5 * MIN, 5), 1);
  assert.equal(momentumSign(px, 'BTC', 10 * MIN, 5), -1);
  assert.equal(momentumSign(px, 'BTC', 15 * MIN, 5), 0, 'equal prices');
  assert.equal(momentumSign(px, 'BTC', 0, 5), 0, 'missing px[T - L]');
  assert.equal(momentumSign(px, 'ETH', 5 * MIN, 5), 0, 'missing coin');
  const k = 'BTC-15m';
  // Tags at 0 (missing past) and 15 min (flat): both fall back to the base rate; tag 5 min (s = +1) uses its own count.
  const rows = [{ k, t: 0, y: 1 }, { k, t: 5 * MIN, y: 1 }, { k, t: 15 * MIN, y: 0 }, { k, t: 30 * MIN, y: 1 }];
  px.get('BTC')!.set(25 * MIN, 99); px.get('BTC')!.set(30 * MIN, 100);
  const base = prequentialBase(rows), mom = prequentialMomentum(rows, px, 5);
  assert.equal(mom[0], base[0]);
  assert.equal(mom[2], base[2]);
  assert.equal(mom[2], 2 / 3, 'flat: base rate with tag 0 (up) matured at 15 min');
  assert.equal(mom[3], 2 / 3, 'at 30 min: the matured s = +1 label (tag 5 min, up)');
  const acc = signMomentumAccuracy(rows, px, 5);
  assert.deepEqual(acc, { acc: 1, n: 2 }, 'ties and missing prices excluded');
});

test('health check: channel names, the data-driven dead classifier and the zero-by-design head features', () => {
  assert.equal(l0Width('crypto'), 200);
  assert.equal(chanName(0), 'delta0');
  assert.equal(chanName(7), 'delta7');
  assert.equal(chanName(8), 'dAtm:b0');
  assert.equal(chanName(199), 'usdtd_ret_15m_z:b7');
  const active = new Array(200).fill(5);
  active[0] = 0; // a dead price delta: unexpected
  active[6] = 0; // a mid delta with no mid: absent
  for (let b = 0; b < 8; b++) active[8 + b] = 0; // dAtm: absent
  const prem = 8 + 8 * 20; // perp_premium_bps
  for (let b = 1; b < 8; b++) active[prem + b] = 0; // a flat input: only band 0 fires
  const rsi = 8 + 8 * 7; // ta_rsi_a: varies, band 7 never fires
  active[rsi + 7] = 0;
  const d = classifyDead(active, { mid: { n: 0, mean: 0, m2: 0 }, ta_rsi_a: { n: 100, mean: 0.1, m2: 3 }, perp_premium_bps: { n: 100, mean: 0, m2: 0 } });
  assert.deepEqual(d.absent, ['delta6', ...Array.from({ length: 8 }, (_, b) => `dAtm:b${b}`)]);
  assert.deepEqual(d.flatInput, Array.from({ length: 7 }, (_, b) => `perp_premium_bps:b${b + 1}`));
  assert.deepEqual(d.unusedBand, ['ta_rsi_a:b7']);
  assert.deepEqual(d.unexpected, ['delta0', ...d.flatInput]);
  assert.equal(d.live, 200 - 1 - 1 - 8 - 7 - 1);
  assert.ok(d.deadInputs.absent.includes('dAtm') && d.deadInputs.absent.includes('mid') && d.deadInputs.flat.includes('perp_premium_bps'));
  const p = trainParams('S5'), c = new SnnNetwork(p).column('BTC-15m', 'BTC')!;
  assert.equal(c.nFeat, 206);
  const z = phiZeroByDesign(p.nE, p.nL1, c.nFeat);
  assert.ok(!z.has(0) && z.has(1) && z.has(5) && !z.has(6) && !z.has(181) && z.has(182) && z.has(205));
  assert.equal(z.size, 5 + (206 - 182));
  // With d = 0 and no extras, every by-design entry is exactly zero.
  const phi = c.features(0, 0, [0, 0, 0]);
  for (const i of z) assert.equal(phi[i], 0, `phi[${i}]`);
  assert.equal(phi[0], 1);
});

/** Synthetic Binance spot history for BTC: 1-minute bars from two days before D0 to the end of D0, with the stored
 *  higher timeframes aggregated from them. With `divergeAt`, bars from that minute on follow another random stream
 *  (bar divergeAt opens at the same price: its open is the previous close). */
function writeSpot(dir: string, D0: number, divergeAt?: number) {
  let x = 60000, s1 = 7, s2 = 99;
  const rnd = (alt: boolean) => { if (alt) { s2 = (s2 * 1664525 + 1013904223) % 4294967296; return s2 / 4294967296 - 0.5; } s1 = (s1 * 1664525 + 1013904223) % 4294967296; return s1 / 4294967296 - 0.5; };
  const bars: Array<{ ts: number; o: number; h: number; l: number; c: number; v: number }> = [];
  for (let t = D0 - 2 * 86_400_000; t < D0 + 86_400_000; t += MIN) {
    const o = x; x *= Math.exp(0.0012 * rnd(divergeAt !== undefined && t >= divergeAt)); const c = x;
    bars.push({ ts: t, o, h: Math.max(o, c) * 1.0002, l: Math.min(o, c) * 0.9998, c, v: 1 });
  }
  const put = (src: string, tf: string, rows: typeof bars) => {
    fs.mkdirSync(path.join(dir, src, 'BTC'), { recursive: true });
    fs.writeFileSync(path.join(dir, src, 'BTC', `${tf}.csv`), ['ts,o,h,l,c,v', ...rows.map((b) => `${b.ts},${b.o},${b.h},${b.l},${b.c},${b.v}`)].join('\n') + '\n');
  };
  put('binance-1m', '1m', bars);
  for (const [tf, ms] of [['15m', 15 * MIN], ['1h', 60 * MIN], ['1d', 86_400_000]] as const) put('binance', tf, aggregate(bars, ms));
}

test('health check: through a built replay, the head\'s calls before a divergence are identical (no look-ahead), labels are the index move, and the prodShadow reproduces the head', async () => {
  const D0 = Date.parse('2026-03-01T00:00:00Z'), Tstar = D0 + 12 * 3_600_000, from = D0 + 10 * 3_600_000, to = D0 + 14 * 3_600_000;
  const run = async (divergeAt?: number) => {
    const hist = tmpDir(), out = path.join(tmpDir(), 'replay');
    writeSpot(hist, D0, divergeAt);
    await buildHistoryReplay({ historyDir: hist, outDir: out, assets: ['BTC'], fromDay: '2026-02-28', toDay: '2026-03-01', synthetic: false, log: () => {} });
    const params = trainParams('S5');
    const sampler = new HealthSampler(params);
    const tagP = new Map<string, number>(), px = new Map<number, number>();
    let nets = 0;
    const res = await replaySnn(out, {
      params, from, to, fromDay: '2026-02-28', toDay: '2026-03-01', domain: 'crypto', skipModel: true, skipAssets: ['DOGE'],
      onProgress: (ts, net) => {
        // The hook hands over the network (snnReplay onProgress(ts, net)).
        if (net instanceof SnnNetwork) nets++;
        sampler.sample(ts, net);
        for (const c of net.columns.values()) {
          px.set(ts, c.lastSpot);
          const tags = net.dirTags.get(c.key)!, t = tags[tags.length - 1];
          if (t?.ts === ts) tagP.set(`${c.key}|${ts}`, t.p);
        }
      },
    });
    sampler.drain(res.net);
    return { res, sampler, tagP, px, nets, rows: sampler.take() };
  };
  const a = await run(), b = await run(Tstar);
  assert.ok(a.nets >= 4 * 60 - 1, `onProgress got the network every minute (${a.nets})`);
  assert.deepEqual([...a.res.net.columns.keys()].sort(), ['BTC-15m', 'BTC-60m']);
  const logA = a.res.net.dirLog!, logB = b.res.net.dirLog!;
  assert.ok(logA.length > 200, `labels ${logA.length}`);
  // Labels: y = [index(T + H) > index(T)] on the minute-mark prints; p = the head's call at T.
  for (const d of logA) {
    const H = d.key.endsWith('-15m') ? 900_000 : 3_600_000, p0 = a.px.get(d.ts), p1 = a.px.get(d.ts + H);
    assert.ok(p0 && p1 && p0 !== p1, `prices at ${d.ts} and +H`);
    assert.equal(d.y, p1! > p0! ? 1 : 0, `${d.key} ${new Date(d.ts).toISOString()}`);
    assert.equal(d.p, a.tagP.get(`${d.key}|${d.ts}`));
  }
  // No look-ahead: every call tagged at or before T* is the same on both paths, through the replay's bridge fill and
  // catch-up steps, its candle release and its TA bars.
  const before = (log: typeof logA) => new Map(log.filter((d) => d.ts <= Tstar).map((d) => [`${d.key}|${d.ts}`, d.p]));
  const pa = before(logA), pb = before(logB);
  assert.ok(pa.size >= 2 * 100, `calls before T*: ${pa.size}`);
  assert.deepEqual(pb, pa);
  for (const [k, p] of a.tagP) if (Number(k.split('|')[1]) <= Tstar) assert.equal(b.tagP.get(k), p, k);
  // ... and the paths do diverge after it.
  // ... and the paths diverge right after it, so a leak of even a few minutes would show.
  const firstDiff = Math.min(...[...a.tagP].filter(([k, p]) => b.tagP.get(k) !== p).map(([k]) => Number(k.split('|')[1])));
  assert.ok(firstDiff > Tstar && firstDiff <= Tstar + 2 * MIN, `first differing call at T* + ${(firstDiff - Tstar) / MIN} min`);
  // The prodShadow (production settings on the same features, same relaxation schedule) reproduces the head.
  assert.ok(a.sampler.diff.n > 400 && a.sampler.diff.max < 1e-6, `prodShadow vs head: max ${a.sampler.diff.max} over ${a.sampler.diff.n}`);
  // Every head label joins a sampled minute; the control's label is the move over the last H, fixed at the tag.
  const rows = new Map(a.rows.rows.filter((r) => r.p !== undefined).map((r) => [`${r.k}|${r.t}`, r]));
  assert.equal(a.rows.dir.length, logA.length);
  for (const d of a.rows.dir) assert.ok(rows.has(`${d.k}|${d.t}`));
  let nc = 0;
  for (const r of rows.values()) {
    const H = r.k.endsWith('-15m') ? 900_000 : 3_600_000, p0 = a.px.get(r.t - H);
    if (r.yc === undefined) { assert.ok(!p0 || p0 === r.x); continue; }
    nc++;
    assert.equal(r.yc, r.x! > p0! ? 1 : 0);
    assert.ok(Number.isFinite(r.s! + r.n! + r.c! + r.b! + r.nb! + r.cb! + r.w0));
  }
  assert.ok(nc > 150, `control labels ${nc}`);
  // The head's own bias at the call (the relaxation after T's tag undone) is the prodShadow's, and no label was skipped.
  let hbMax = 0;
  for (const r of rows.values()) hbMax = Math.max(hbMax, Math.abs(r.hb! - r.b!));
  assert.ok(hbMax < 1e-6, `head bias vs prodShadow bias: max ${hbMax}`);
  // In this replay the minute-mark step is never a relaxation step (net.steps % 60 = 1 at every tag), so hb = wf[0];
  // unrelaxWf (tested below) covers a phase where the head relaxes right after its tag.
  assert.ok([...rows.values()].some((r) => r.rz !== undefined), 'ret_h_z logged at the tag');
  assert.equal(a.sampler.skipped, 0);
});

test('health check: unrelaxWf inverts one two-speed relaxation', () => {
  for (const [wf, ws] of [[0.3, 0.01], [-1.2, 0.4], [0, 0]]) {
    const p = trainParams('S5'), r = twoSpeedStep(wf, ws, p.tauC, p.eps, p.slowEverySec);
    assert.ok(Math.abs(unrelaxWf(r.wf, r.ws, p.tauC, p.eps, p.slowEverySec) - wf) < 1e-12);
  }
});

test('health check: the prodShadow still matches the head across a checkpoint boundary (two chunks)', async () => {
  const D0 = Date.parse('2026-03-01T00:00:00Z');
  const hist = tmpDir(), out = path.join(tmpDir(), 'replay');
  writeSpot(hist, D0);
  await buildHistoryReplay({ historyDir: hist, outDir: out, assets: ['BTC'], fromDay: '2026-02-28', toDay: '2026-03-01', synthetic: false, log: () => {} });
  const params = trainParams('S5'), sampler = new HealthSampler(params);
  let cp: ReturnType<SnnNetwork['serialize']> | undefined;
  const n: number[] = [];
  for (const [a, b] of [[D0 + 8 * 3_600_000, D0 + 12 * 3_600_000 - 1000], [D0 + 12 * 3_600_000, D0 + 16 * 3_600_000 - 1000]]) {
    const res = await replaySnn(out, { params, from: a, to: b, fromDay: '2026-02-28', toDay: '2026-03-01', domain: 'crypto', skipModel: true, skipAssets: ['DOGE'], checkpoint: cp, onProgress: (ts, net) => sampler.sample(ts, net) });
    sampler.drain(res.net);
    cp = res.net.serialize();
    n.push(sampler.diff.n);
    const { rows } = sampler.take();
    for (const r of rows) if (r.hb !== undefined) assert.ok(Math.abs(r.hb - r.b!) < 1e-6, `bias at ${new Date(r.t).toISOString()}`);
    for (const [k, ro] of res.net.dirReadouts) assert.equal(sampler.shadows.get(k)!.ps.updates, ro.updates, `${k} updates`);
  }
  assert.ok(n[1] - n[0] > 400, `second-chunk tags compared: ${n[1] - n[0]}`);
  assert.ok(sampler.diff.max < 1e-6, `prodShadow vs head across the checkpoint: max ${sampler.diff.max}`);
  assert.equal(sampler.skipped, 0);
});

test('health check: report end to end (join, unmatched, window by tag time, coverage, the head\'s own bias, 2 public lines)', () => {
  const dir = tmpDir(), proc = path.join(dir, 'BTC');
  fs.mkdirSync(proc, { recursive: true });
  const r = rng(5), rows: SampleRow[] = [], dirs: DirRow[] = [];
  const t0 = Date.parse('2026-05-25T00:00:00Z'), days = 40; // 7 learning days, then 33 window days (Jun 1 .. Jul 3)
  let x = 60000;
  const zero = { w0: 0, G: 0, fr: 0 as const, rc: 0 as const, eta: 1, fs: 0, rho: 0, ez: 0, db: 0, rE: 0, rL1: 0 };
  for (let t = t0; t < t0 + days * 86_400_000; t += 30 * MIN) {
    x *= Math.exp(0.001 * (r() - 0.5));
    for (const k of ['BTC-15m', 'BTC-60m']) {
      const p = 0.15 + 0.7 * r(), y: 0 | 1 = r() < p ? 1 : 0, c = 0.15 + 0.7 * r(), yc: 0 | 1 = r() < c ? 1 : 0;
      // The head's own bias equals logit(p) up to a column-day constant: its state part has no spread (rule 1 fails).
      // With the prodShadow's bias (b = 0) it would spread widely and the head would pass.
      const hb = logit(p) - 0.01 * new Date(t).getUTCDate();
      rows.push({ k, t, x, p, s: p, n: p, c, yc, hb, b: 0, nb: 0, cb: 0, rz: yc ? 0.5 : -0.5, ...zero });
      dirs.push({ k, t, p, y });
    }
  }
  for (let i = 1; i <= 3; i++) dirs.push({ k: 'BTC-60m', t: t0 + i * 61_000, p: 0.5, y: 1 }); // no sampled minute: unmatched
  const gz = (a: object[]) => zlib.gzipSync(a.map((o) => JSON.stringify(o)).join('\n') + '\n');
  fs.writeFileSync(path.join(proc, 'rows-2026-05-25.jsonl.gz'), gz(rows));
  fs.writeFileSync(path.join(proc, 'dir-2026-05-25.jsonl.gz'), gz(dirs));
  fs.writeFileSync(path.join(proc, 'meta.json'), JSON.stringify({ asset: 'BTC', stage: 'S5', leadInputs: null, diff: { max: 0, mean: 0, n: rows.length }, skippedLabels: 0, done: 1, of: 1 }));
  const nL0 = l0Width('crypto'), nF = 206;
  const cum = { minutes: 1, chanActive: new Array(nL0).fill(1), chanMean: new Array(nL0).fill(0), chanM2: new Array(nL0).fill(0), inputs: {}, phiN: 1, phiMean: new Array(nF).fill(0), phiM2: new Array(nF).fill(0), phiMax: new Array(nF).fill(0) };
  fs.writeFileSync(path.join(proc, 'cum.json'), JSON.stringify({ 'BTC-15m': cum, 'BTC-60m': cum }));
  const md = path.join(dir, 'r.md'), js = path.join(dir, 'r.json'), pub = path.join(dir, 'pub.md');
  const log = console.log;
  console.log = () => {};
  try { reportCmd(['node', 'x', 'report', '--in', dir, '--out', md, '--json', js, '--public', pub, '--assets', 'BTC', '--decide-from', '2026-06-01', '--decide-to', '2026-07-03']); }
  finally { console.log = log; }
  const J = JSON.parse(fs.readFileSync(js, 'utf8'));
  assert.equal(J.unmatched, 3);
  assert.deepEqual(J.coverage, [{ column: 'BTC-15m', days: 33 }, { column: 'BTC-60m', days: 33 }]);
  assert.equal(J.head.stats.n, 2 * 33 * 48, 'window by tag time');
  assert.equal(J.control.stats.n, 2 * 33 * 48);
  assert.ok(J.head.stats.sdState < 1e-6, `head state sd ${J.head.stats.sdState} (the head's own bias)`);
  assert.ok(J.head.fails.some((f: string) => f.startsWith('state sd')), J.head.fails.join('; '));
  assert.equal(J.control.pass, true, J.control.fails.join('; '));
  assert.equal(J.verdict, 'CAN LEARN, DIRECTION NOT PREDICTABLE');
  assert.equal(J.controlInputAgreement.rate, 1);
  const lines = fs.readFileSync(pub, 'utf8').split('\n').filter(Boolean);
  assert.equal(lines.length, 2);
  assert.ok(lines.every((l) => l.startsWith('[health] ')));
  assert.ok(lines[0] === '[health] VERDICT: CAN LEARN, DIRECTION NOT PREDICTABLE');
  const report = fs.readFileSync(md, 'utf8');
  assert.ok(report.includes('BTC-15m (stage S5)') && report.includes('unmatched dropped: 3'));
  // The same rows over a shorter window leave both columns under 28 days: INCONCLUSIVE.
  console.log = () => {};
  try { reportCmd(['node', 'x', 'report', '--in', dir, '--out', md, '--json', js, '--public', pub, '--assets', 'BTC', '--decide-from', '2026-06-10', '--decide-to', '2026-07-03']); }
  finally { console.log = log; }
  assert.equal(JSON.parse(fs.readFileSync(js, 'utf8')).verdict, 'INCONCLUSIVE');
});

test('health check: verdict and overall rule edge cases (pre-registered)', () => {
  const ci = (est: number, lo: number, hi: number): Ci => ({ est, lo, hi, n: 1000, days: 61 });
  const good: ArmStats = { n: 1000, sdState: 0.08, slope: ci(1, 0.4, 1.6), auc: ci(0.53, 0.51, 0.55), skill: ci(0.004, 0.001, 0.007) };
  assert.deepEqual(verdict(good), { pass: true, fails: [] });
  assert.equal(verdict({ ...good, sdState: 0.049 }).pass, false, 'tiny state spread');
  assert.equal(verdict({ ...good, sdState: RULE.sdState }).pass, true, 'at the threshold');
  assert.equal(verdict({ ...good, slope: ci(0.69, 0.2, 1.1) }).pass, false);
  assert.equal(verdict({ ...good, slope: ci(1.31, 0.2, 2) }).pass, false);
  assert.equal(verdict({ ...good, slope: ci(0.7, 0.2, 1.1) }).pass, true);
  assert.equal(verdict({ ...good, slope: ci(1, 0, 2) }).pass, false, 'slope CI lower must be > 0');
  assert.equal(verdict({ ...good, auc: ci(0.52, 0.5, 0.54) }).pass, false, 'AUC CI lower must be > 0.5');
  assert.equal(verdict({ ...good, skill: ci(0.002, 0, 0.004) }).pass, false, 'skill CI lower must be > 0');
  assert.equal(verdict({ ...good, slope: ci(NaN, NaN, NaN) }).pass, false, 'NaN fails');
  assert.equal(verdict({ ...good, n: 0 }).pass, false);
  const cov = (d: number[]) => d.map((days, i) => ({ column: `c${i}`, days }));
  const P = { pass: true }, F = { pass: false };
  assert.equal(overall(P, P, cov([61, 28])), 'HEAD LEARNS DIRECTION');
  assert.equal(overall(F, P, cov([61, 61])), 'CAN LEARN, DIRECTION NOT PREDICTABLE');
  assert.equal(overall(F, F, cov([61, 61])), 'LEARNING BROKEN');
  assert.equal(overall(P, F, cov([61, 61])), 'LEARNING BROKEN');
  assert.equal(overall(P, P, cov([61, 27])), 'INCONCLUSIVE', 'any column < 28 days');
  assert.equal(overall(P, P, []), 'INCONCLUSIVE');
});
