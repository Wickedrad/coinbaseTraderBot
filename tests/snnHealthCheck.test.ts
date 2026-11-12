import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { aggregate, buildHistoryReplay } from '../research/history/historyReplay';
import {
  ARM_KEYS, ArmBank, auc, brierSkill, chanName, classifyDead, EwStandardizer, HealthSampler, momentumSign, newtonRidge, overall, phiZeroByDesign, prequentialBase, prequentialMomentum,
  reportCmd, RIDGE, RidgeLogistic, RULE, selectReadout, signMomentumAccuracy, slopeB, spreadStats, unrelaxWf, verdict, withinSd, type ArmKey, type ArmStats, type Ci, type DirRow, type PxMap, type SampleRow,
} from '../research/snnHealthCheck';
import { popSpec } from '../bot/snn/inputs';
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
  // A learning pause (as a health freeze sets it) from P0 to P1, the same on both paths.
  const P0 = D0 + 10 * 3_600_000 + 40 * MIN, P1 = D0 + 11 * 3_600_000 + 10 * MIN;
  type Snap = { head: number; ps: number; ctl: number; nfD: number; nfC: number; nlD: number; nlC: number; rwD: number; plD: number; frozen: boolean };
  const run = async (divergeAt?: number) => {
    const hist = tmpDir(), out = path.join(tmpDir(), 'replay');
    writeSpot(hist, D0, divergeAt);
    await buildHistoryReplay({ historyDir: hist, outDir: out, assets: ['BTC'], fromDay: '2026-02-28', toDay: '2026-03-01', synthetic: false, log: () => {} });
    const params = trainParams('S5');
    // The ridge learners refit hourly here (daily in the run) so the replay covers refits, before and after T*.
    const sampler = new HealthSampler(params, { ridge: { refitMs: 3_600_000, minRows: 20, stride: 1 } });
    const tagP = new Map<string, number>(), px = new Map<number, number>(), snaps = new Map<number, Snap>();
    let nets = 0;
    const res = await replaySnn(out, {
      params, from, to, fromDay: '2026-02-28', toDay: '2026-03-01', domain: 'crypto', skipModel: true, skipAssets: ['DOGE'],
      onProgress: (ts, net) => {
        // The hook hands over the network (snnReplay onProgress(ts, net)).
        if (net instanceof SnnNetwork) nets++;
        sampler.sample(ts, net);
        const sh = sampler.shadows.get('BTC-15m'), bk = sh?.bank;
        if (sh && bk) snaps.set(ts, { head: net.dirReadouts.get('BTC-15m')!.updates, ps: sh.ps.updates, ctl: sh.ctl.updates, nfD: bk.nofreeze.dir.updates, nfC: bk.nofreeze.ctl.updates, nlD: bk.nlms.dir.updates, nlC: bk.nlms.ctl.updates, rwD: bk.raw.dir.updates, plD: bk.plain.dir.updates, frozen: net.learningFrozen });
        net.pauseLearning = ts >= P0 && ts < P1;
        for (const c of net.columns.values()) {
          px.set(ts, c.lastSpot);
          const tags = net.dirTags.get(c.key)!, t = tags[tags.length - 1];
          if (t?.ts === ts) tagP.set(`${c.key}|${ts}`, t.p);
        }
      },
    });
    sampler.drain(res.net);
    return { res, sampler, tagP, px, nets, snaps, rows: sampler.take() };
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
  // Readout-fix arms: every tagged minute carries all four arms' [p dir, bias, p ctl, bias], finite, p in (0, 1); the
  // arms are identical before T* on both paths (no look-ahead through the standardizers or the learners).
  for (const r of rows.values()) for (const k of ARM_KEYS) {
    const v = r.xa?.[k];
    assert.ok(v && v.length === 4 && v.every(Number.isFinite) && v[0] > 0 && v[0] < 1 && v[2] > 0 && v[2] < 1, `${k} at ${r.t}`);
  }
  const armsBefore = (rs: SampleRow[]) => new Map(rs.filter((r) => r.xa && r.t <= Tstar).map((r) => [`${r.k}|${r.t}`, JSON.stringify(r.xa)]));
  const xa = armsBefore(a.rows.rows), xb = armsBefore(b.rows.rows);
  assert.ok(xa.size >= 200);
  assert.deepEqual(xb, xa);
  // Each arm took every head label on the direction readout and every matured control label on the control readout.
  for (const k of ['BTC-15m', 'BTC-60m']) {
    const bank = a.sampler.shadows.get(k)!.bank!, nDir = logA.filter((d) => d.key === k).length;
    for (const arm of ['nlms', 'raw', 'plain'] as const) assert.equal(bank[arm].dir.updates, nDir, `${k} ${arm} dir`);
    assert.equal(bank.nofreeze.dir.updates, nDir, `${k} nofreeze dir (never frozen)`);
    assert.ok(bank.nlms.ctl.updates > 50 && bank.nlms.ctl.updates === bank.raw.ctl.updates && bank.raw.ctl.updates === bank.plain.ctl.updates);
    // The hourly refits ran (direction labels mature from 10:15 for 15m and 11:00 for 60m, control labels one H later:
    // y' needs the price at T - H), and moved the weights off zero.
    const nr = k.endsWith('-15m') ? 3 : 2; // 60m labels mature from 11:00
    assert.ok(bank.nlms.dir.refits >= nr && bank.raw.dir.refits >= nr && bank.plain.dir.refits >= nr && bank.nlms.ctl.refits >= nr - 1, `${k} refits ${bank.nlms.dir.refits} ${bank.raw.dir.refits} ${bank.plain.dir.refits} ${bank.nlms.ctl.refits}`);
    assert.ok(bank.nlms.ctl.w.some((x) => x !== 0));
  }
  // The learning pause: the head and the production-settings shadows (prodShadow, control) take no label in it; the
  // readout-fix arms (nofreeze included) keep taking one per matured label, on both labels.
  const s0 = a.snaps.get(P0)!, s1 = a.snaps.get(P1)!, mins = (P1 - P0) / MIN;
  assert.ok(s0 && s1 && [...a.snaps].filter(([t]) => t > P0 && t < P1).every(([, v]) => v.frozen), 'frozen through the pause');
  assert.equal(s1.head, s0.head, 'the head is paused');
  assert.equal(s1.ps, s0.ps, 'the prodShadow follows the pause');
  assert.equal(s1.ctl, s0.ctl, 'the production-settings control follows the pause');
  for (const [name, d] of [['nofreeze dir', s1.nfD - s0.nfD], ['nofreeze ctl', s1.nfC - s0.nfC], ['nlms dir', s1.nlD - s0.nlD], ['nlms ctl', s1.nlC - s0.nlC], ['raw dir', s1.rwD - s0.rwD], ['plain dir', s1.plD - s0.plD]] as const)
    assert.ok(Math.abs(d - mins) <= 1, `${name} took ${d} labels in the ${mins}-minute pause`);
  // ... and after it the head and the prodShadow learn again, in step.
  assert.ok(a.snaps.get(Tstar)!.head > s1.head && a.snaps.get(Tstar)!.ps - s1.ps === a.snaps.get(Tstar)!.head - s1.head);
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

test('health check: report end to end (join, unmatched, window by tag time, coverage, the head\'s own bias, 3 public lines, readout-fix arms)', () => {
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
      // Arms: nlms and plain carry the calibrated p and c (pass the control); raw is noise around 0.5 (fails); nofreeze's
      // bias is its whole logit (no state part: fails rule 1).
      const q = () => 0.5 + 0.02 * (r() - 0.5);
      const xa = { nlms: [p, 0, c, 0], plain: [p, 0, c, 0], raw: [q(), 0, q(), 0], nofreeze: [p, logit(p), c, logit(c)] };
      rows.push({ k, t, x, p, s: p, n: p, c, yc, hb, b: 0, nb: 0, cb: 0, rz: yc ? 0.5 : -0.5, xa, ...zero });
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
  // Readout-fix arms: both labels for every arm, the selection rule, the tables.
  assert.equal(J.arms.nlms.control.pass, true, J.arms.nlms.control.fails.join('; '));
  assert.equal(J.arms.plain.control.pass, true);
  assert.equal(J.arms.raw.control.pass, false);
  assert.ok(J.arms.nofreeze.control.fails.some((f: string) => f.startsWith('state sd')));
  for (const k of ARM_KEYS) assert.equal(J.arms[k].direction.stats.n, 2 * 33 * 48, `${k} direction rows`);
  assert.equal(J.arms.nofade.control, undefined);
  assert.deepEqual(J.selection.fit, ['prod', 'nlms', 'plain']);
  assert.equal(J.selection.selected, 'prod');
  assert.equal(J.noArms, 0);
  const lines = fs.readFileSync(pub, 'utf8').split('\n').filter(Boolean);
  assert.equal(lines.length, 3);
  assert.ok(lines.every((l) => l.startsWith('[health] ') && l.length < 260));
  assert.ok(lines[0] === '[health] VERDICT: CAN LEARN, DIRECTION NOT PREDICTABLE');
  assert.equal(lines[2], '[health] READOUT: FIT READOUT (prod); readouts passing the control 3/5, the direction 2/5');
  const report = fs.readFileSync(md, 'utf8');
  assert.ok(report.includes('BTC-15m (stage S5)') && report.includes('unmatched dropped: 3'));
  assert.ok(report.includes('### Direction label') && report.includes("### Control label") && report.includes('| nlms coin BTC |') && report.includes('| raw | ') && report.includes('- plain: CONTROL PASS'));
  assert.ok(report.includes('**Readout fix (ADDENDUM 2026-11-12, pre-registered): FIT READOUT: prod'));
  assert.ok(report.includes('- nofreeze: CONTROL FAIL') && report.includes('removes the hard health freeze only'));
  assert.ok(J.selectionCoverage.length === 2 * 6 && J.selectionCoverage.every((c: { days: number }) => c.days === 33));
  // An output dir from before the arms (no xa) at full coverage: the pre-registered verdict is unchanged, every arm is
  // n/a (never FAIL), and the selection is INCONCLUSIVE.
  const old = path.join(tmpDir(), 'BTC');
  fs.mkdirSync(old, { recursive: true });
  fs.writeFileSync(path.join(old, 'rows-2026-05-25.jsonl.gz'), gz(rows.map(({ xa: _xa, ...o }) => o)));
  for (const f of ['dir-2026-05-25.jsonl.gz', 'meta.json', 'cum.json']) fs.copyFileSync(path.join(proc, f), path.join(old, f));
  console.log = () => {};
  try { reportCmd(['node', 'x', 'report', '--in', path.dirname(old), '--out', md, '--json', js, '--public', pub, '--assets', 'BTC', '--decide-from', '2026-06-01', '--decide-to', '2026-07-03']); }
  finally { console.log = log; }
  const O = JSON.parse(fs.readFileSync(js, 'utf8'));
  assert.equal(O.verdict, 'CAN LEARN, DIRECTION NOT PREDICTABLE');
  assert.equal(O.selection.outcome, 'INCONCLUSIVE');
  assert.equal(O.noArms, 2 * 40 * 48);
  for (const k of ARM_KEYS) assert.deepEqual(O.arms[k], {}, `${k} n/a`);
  const ol = fs.readFileSync(pub, 'utf8').split('\n').filter(Boolean);
  assert.deepEqual(ol.slice(0, 2), lines.slice(0, 2), 'the verdict and counts lines as before');
  assert.equal(ol[2], '[health] READOUT: INCONCLUSIVE; readouts passing the control 1/1, the direction 0/1');
  assert.ok(fs.readFileSync(md, 'utf8').includes('- nlms: CONTROL n/a; DIRECTION n/a'));
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

test('health check: the causal EW standardizer (z from the values before, half-life, missing values, clip)', () => {
  const r = rng(21), n = 3000;
  const xs = Array.from({ length: n }, () => [3 + 2 * (r() - 0.5), r() < 0.1 ? NaN : -1 + r(), 7]);
  const run = (rows: number[][], hl = 100) => { const s = new EwStandardizer(3, hl); return rows.map((x) => Array.from(s.push(x, new Float64Array(3)))); };
  const z = run(xs);
  // Causality: perturbing the future leaves every earlier z unchanged; z(T) itself moves only with x(T).
  const cut = 1700, ys = xs.map((x, i) => (i > cut ? [x[0] * 5 + 9, x[1] - 3, 100] : x));
  const zy = run(ys);
  for (let i = 0; i <= cut; i++) assert.deepEqual(zy[i], z[i], `z at ${i}`);
  assert.notDeepEqual(zy[cut + 1], z[cut + 1]);
  // z(T) uses the statistics BEFORE x(T): the first value and the second (one point, no variance) give 0.
  assert.deepEqual(z[0], [0, 0, 0]);
  assert.equal(z[1][0], 0);
  // A constant feature stays 0; a missing value gives 0 and leaves the statistics alone.
  assert.ok(z.every((v) => v[2] === 0));
  const s = new EwStandardizer(1, 100), o = new Float64Array(1);
  for (let i = 0; i < 50; i++) s.push([i % 2], o);
  const m = s.mean[0], v = s.v[0], c = s.cnt[0];
  s.push([NaN], o);
  assert.equal(o[0], 0); assert.equal(s.mean[0], m); assert.equal(s.v[0], v); assert.equal(s.cnt[0], c);
  // Early on (1/n above the EW weight) the statistics are the plain mean and the population variance.
  const e = new EwStandardizer(1, 1e6);
  for (const x of [1, 2, 3, 4]) e.push([x], o);
  assert.ok(Math.abs(e.mean[0] - 2.5) < 1e-12 && Math.abs(e.v[0] - 1.25) < 1e-12);
  e.push([5], o);
  assert.ok(Math.abs(o[0] - 2.5 / Math.sqrt(1.25)) < 1e-12, 'z of 5 against mean 2.5, var 1.25');
  // Standardized: mean ~0 and sd ~1 after warm-up; a level shift is absorbed within a few half-lives; the clip holds.
  const zz = z.slice(500).map((v) => v[0]), mz = zz.reduce((a, b) => a + b, 0) / zz.length, sz = Math.sqrt(zz.reduce((a, b) => a + (b - mz) ** 2, 0) / zz.length);
  assert.ok(Math.abs(mz) < 0.1 && Math.abs(sz - 1) < 0.1, `mean ${mz} sd ${sz}`);
  const after = zy.slice(cut + 1 + 1000).map((v) => v[0]);
  assert.ok(Math.abs(after.reduce((a, b) => a + b, 0) / after.length) < 0.2, 'shift absorbed');
  assert.equal(zy[cut + 1][0], RIDGE.zClip, 'the shift itself is clipped');
});

test('health check: the ridge learner (Newton optimum, daily refit on matured rows only, window, stride, prequential strength)', () => {
  // newtonRidge reaches the penalized optimum: gradient X'(p - y) + lambda w (bias unpenalized) ~ 0.
  const r = rng(4), m = 400, a = 4, X = new Float64Array(m * a), Y = new Float64Array(m);
  for (let i = 0; i < m; i++) { X[i * a] = 1; for (let j = 1; j < a; j++) X[i * a + j] = r() - 0.5; Y[i] = r() < 1 / (1 + Math.exp(-(0.3 + 4 * X[i * a + 1]))) ? 1 : 0; }
  for (const lam of [0.1, 10, 1000]) {
    const w = new Float64Array(a);
    newtonRidge(X, Y, m, a, w, lam, 50, 1e-12);
    const g = new Float64Array(a);
    for (let i = 0; i < m; i++) { let s = 0; for (let j = 0; j < a; j++) s += X[i * a + j] * w[j]; const e = 1 / (1 + Math.exp(-s)) - Y[i]; for (let j = 0; j < a; j++) g[j] += e * X[i * a + j]; }
    for (let j = 1; j < a; j++) g[j] += lam * w[j];
    assert.ok(g.every((x) => Math.abs(x) < 1e-8), `lambda ${lam}: gradient ${Array.from(g)}`);
    if (lam === 0.1) assert.ok(w[1] > 2.5 && w[1] < 6, `w1 ${w[1]}`);
    if (lam === 1000) assert.ok(Math.abs(w[1]) < 0.3, 'heavy ridge shrinks');
  }
  // Refit: only at the first call of a new period, on stored labels only; learn() never moves the weights; rows outside
  // the trailing window are dropped; one tag in `stride` minutes is kept.
  const D = 86_400_000, L = new RidgeLogistic(2, { stride: 2, windowDays: 1, minRows: 5, lambdas: [1, 100] });
  assert.equal(L.refit(0), false, 'no rows yet');
  for (let t = 0; t < 600; t++) L.learn(Float64Array.of(1, (t >> 1) % 2 ? 1 : -1), (t >> 1) % 2, t * MIN);
  assert.equal(L.rows, 300, 'stride 2: every other tag minute');
  assert.ok(L.W.every((w) => w.every((x) => x === 0)), 'learn() stores and scores only');
  assert.equal(L.refit(30 * MIN), false, 'same day: no refit');
  assert.equal(L.refit(D), true, 'a new day: refit');
  assert.equal(L.refits, 1);
  assert.equal(L.rows, 300, 'all inside the 1-day window');
  const p = L.predict([1, 1]);
  assert.ok(p > 0.65, `fitted ${p}`);
  for (let t = 0; t < 10; t++) L.learn(Float64Array.of(1, 1), 0, D + t * MIN);
  assert.equal(L.predict([1, 1]), p, 'fixed between refits');
  assert.equal(L.refit(D + 5 * 3_600_000), false);
  L.refit(2 * D);
  assert.equal(L.rows, 5, 'rows tagged before T - window dropped');
  // Prequential strength: scored on labels after the fit; a separable target prefers the weak ridge.
  const M = new RidgeLogistic(2, { minRows: 5, lambdas: [1, 1e5], stride: 1 });
  for (let day = 0; day < 4; day++) { M.refit(day * D); for (let t = 0; t < 200; t++) M.learn(Float64Array.of(1, t % 2 ? 1 : -1), t % 2, day * D + t * MIN); }
  assert.ok(M.score[0] < M.score[1] && M.lambda === 1, `scores ${Array.from(M.score)}`);
  // Delayed overlapping labels (H = 15), standardized inputs: calibrated (slope ~1) whether 5 or 80 inputs, where a
  // normalized step was not (its speed falls with the dimension).
  for (const d of [5, 80]) {
    const q = rng(8), std = new EwStandardizer(d), R = new RidgeLogistic(d + 1, { windowDays: 7, stride: 5 });
    const pend: { z: Float64Array; y: number; t: number }[] = [], px = [100];
    const P: number[] = [], Y: number[] = [], G: string[] = [];
    const ar = new Float64Array(d), gauss = () => Math.sqrt(-2 * Math.log(q() + 1e-12)) * Math.cos(2 * Math.PI * q());
    for (let t = 1; t < 12 * 1440; t++) {
      px.push(px[t - 1] * Math.exp(0.0005 * gauss()));
      if (t < 15) continue;
      const x = new Float64Array(d);
      for (let i = 0; i < d; i++) { ar[i] = 0.98 * ar[i] + 0.2 * gauss(); x[i] = ar[i]; }
      x[0] = Math.log(px[t] / px[t - 15]) / (0.0005 * Math.sqrt(15)) + gauss();
      const z = std.push(x, new Float64Array(d + 1), 1); z[0] = 1;
      while (pend.length && pend[0].t + 15 <= t) { const o = pend.shift()!; R.learn(o.z, o.y, o.t * MIN); }
      R.refit(t * MIN);
      pend.push({ z, y: px[t] > px[t - 15] ? 1 : 0, t });
      if (t >= 8 * 1440) { P.push(R.predict(z)); Y.push(px[t] > px[t - 15] ? 1 : 0); G.push(String(Math.floor(t / 1440))); }
    }
    const sl = slopeB(P, Y, { group: G, day: G, iters: 50 }), au = auc(P, Y).est;
    assert.ok(sl.est > 0.8 && sl.est < 1.2 && au > 0.75, `d ${d}: slope ${sl.est}, AUC ${au}`);
  }
});

test('health check: every readout-fix arm learns a synthetic separable target on both labels', () => {
  const p = trainParams('S5'), names = popSpec('crypto', p.leadInputs).map((x) => x.name), nF = 206, nL0 = 200;
  const ro = { eta: p.dirEta, cap: p.dirCap, tauC: p.tauC, eps: p.eps, tagsPerContract: 1, maxTagged: 1, traceTauSec: p.traceTauSec, useTags: true };
  // Small ridge settings (refit every 2 days on a 3-day window, one tag in 10 minutes, three strengths) keep the
  // refits cheap in a test.
  const bank = new ArmBank(nF, nL0, names, ro, { ridge: { refitMs: 2 * 86_400_000, windowDays: 3, stride: 10, minRows: 100, lambdas: [10, 100, 1000] } });
  const r = rng(9), H = 15, n = 40 * 1440;
  const pend: { f: ReturnType<ArmBank['features']>; phi: Float64Array; xp: ReturnType<ArmBank['predict']>; y: 0 | 1; yc: 0 | 1; t: number }[] = [];
  const P = Object.fromEntries(ARM_KEYS.map((k) => [k, { d: [] as number[], c: [] as number[] }])) as Record<ArmKey, { d: number[]; c: number[] }>;
  const Y: number[] = [], YC: number[] = [];
  for (let t = 0; t < n; t++) {
    // One latent signal s and an independent second one u: the direction label reads s, the control label u. Each feature
    // space carries both (head features in the E block, L0 rates in two bands, the plain inputs in ret_h_z / ret_5m_z).
    const s = r() - 0.5, u = r() - 0.5, y: 0 | 1 = s > 0 ? 1 : 0, yc: 0 | 1 = u > 0 ? 1 : 0;
    const phi = new Float64Array(nF);
    phi[0] = 1;
    for (let i = 6; i < 182; i++) phi[i] = 0.02 * r();
    // O(1) on the head features so the production learning rate (nofreeze) can move within the test's 40 days.
    phi[10] += s + 0.5; phi[20] += u + 0.5;
    const rate0 = Float64Array.from({ length: nL0 }, () => 0.002 * r());
    rate0[50] += 0.02 * (s + 0.5); rate0[90] += 0.02 * (u + 0.5);
    const vals: Record<string, number | undefined> = Object.fromEntries(names.map((k) => [k, r() - 0.5]));
    vals.ret_h_z = 3 * s; vals.ret_5m_z = 3 * u; vals.dAtm = undefined;
    const f = bank.features(phi, rate0, vals);
    for (; pend.length && pend[0].t + H <= t; pend.shift()) {
      const q = pend[0];
      bank.learn('dir', q.f, q.phi, q.xp.nofreeze[0], q.t * MIN, q.y, t * MIN, 1);
      bank.learn('ctl', q.f, q.phi, q.xp.nofreeze[2], q.t * MIN, q.yc, t * MIN, 1);
    }
    bank.refit(t * MIN);
    const xp = bank.predict(f, phi);
    pend.push({ f, phi, xp, y, yc, t });
    if (t % p.slowEverySec === 0) bank.relax(p.slowEverySec);
    if (t > n - 5 * 1440) { for (const k of ARM_KEYS) { P[k].d.push(xp[k][0]); P[k].c.push(xp[k][2]); } Y.push(y); YC.push(yc); }
  }
  for (const k of ARM_KEYS) {
    const ad = auc(P[k].d, Y).est, ac = auc(P[k].c, YC).est, cross = auc(P[k].d, YC).est;
    assert.ok(ad > 0.9 && ac > 0.9, `${k}: direction AUC ${ad}, control AUC ${ac}`);
    // The standardized arms keep the labels apart; nofreeze's uncentered features let the label rate leak a little.
    assert.ok(Math.abs(cross - 0.5) < (k === 'nofreeze' ? 0.1 : 0.05), `${k}: the direction readout does not learn the control label (${cross})`);
  }
  assert.equal(bank.nofreeze.dir.updates, bank.nlms.dir.updates);
});

test('health check: readout selection (ADDENDUM): control decides, spiking before raw, plain never selected, information vs calibration, missing arms', () => {
  const cov = [{ column: 'c0', days: 61 }, { column: 'c1', days: 40 }];
  // A failing readout that does not rank the control (AUC CI lower <= 0.5), one that ranks it but fails calibration.
  const P = { pass: true, aucLo: 0.55 }, F = { pass: false, aucLo: 0.49 }, Fr = { pass: false, aucLo: 0.52 };
  const all = (o: Record<string, { pass: boolean; aucLo: number }>) => ({ prod: F, nofreeze: F, nlms: F, raw: F, plain: F, ...o });
  assert.deepEqual(selectReadout(all({ nlms: P, nofreeze: P, raw: P, plain: P }), cov), { outcome: 'FIT READOUT', fit: ['nofreeze', 'nlms', 'raw', 'plain'], selected: 'nofreeze', line: 'FIT READOUT: nofreeze (control passes: nofreeze, nlms, raw, plain)' });
  assert.equal(selectReadout(all({ nlms: P, raw: P }), cov).selected, 'nlms', 'a spiking arm before raw');
  assert.equal(selectReadout(all({ prod: P, nlms: P }), cov).selected, 'prod');
  const raw = selectReadout(all({ raw: P, plain: P }), cov);
  assert.equal(raw.outcome, 'SPIKING LAYERS LOSE THE INFORMATION');
  assert.equal(raw.selected, 'raw');
  const plain = selectReadout(all({ plain: P }), cov);
  assert.equal(plain.outcome, 'SPIKING LAYERS LOSE THE INFORMATION');
  assert.equal(plain.selected, undefined, 'plain is never selected');
  assert.deepEqual(plain.fit, ['plain']);
  // A spiking readout that ranks the control but fails its spread / slope / skill parts: miscalibrated, not lost.
  const mis = selectReadout(all({ nlms: Fr, raw: P }), cov);
  assert.equal(mis.outcome, 'SPIKING READOUTS MISCALIBRATED');
  assert.equal(mis.selected, 'raw', 'raw is still the fit readout');
  assert.ok(mis.line.includes('nlms'));
  assert.equal(selectReadout(all({ prod: Fr, plain: P }), cov).outcome, 'SPIKING READOUTS MISCALIBRATED');
  assert.equal(selectReadout(all({ prod: { pass: false, aucLo: NaN }, plain: P }), cov).outcome, 'SPIKING LAYERS LOSE THE INFORMATION', 'NaN does not rank');
  const none = selectReadout(all({ nlms: Fr }), cov);
  assert.equal(none.outcome, 'NO READOUT LEARNS THE CONTROL');
  assert.equal(none.selected, undefined);
  // Direction pass/fail plays no part; coverage and missing arms: INCONCLUSIVE.
  assert.equal(selectReadout(all({ nlms: P }), [{ column: 'c0', days: 27 }]).outcome, 'INCONCLUSIVE');
  assert.equal(selectReadout(all({ nlms: P }), []).outcome, 'INCONCLUSIVE');
  assert.equal(selectReadout(all({ nlms: P }), cov).selected, 'nlms');
  const miss = selectReadout({ prod: F, nlms: P }, cov);
  assert.equal(miss.outcome, 'INCONCLUSIVE');
  assert.equal(miss.line, 'INCONCLUSIVE (readout arms missing: nofreeze, raw, plain)');
  assert.equal(selectReadout(all({ nlms: P }), cov, 3).line, 'INCONCLUSIVE (readout arms missing: 3 joined calls without them)');
});
