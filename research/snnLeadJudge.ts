/**
 * Judge for failure diagnosis SNN-H1-lead-info and the shared mid-lag test H-B
 * (/mnt/project-files/institutional-methods/failure-diagnoses.md; pre-registration /mnt/project-files/snn-lead/H1-preregistration.md).
 *
 * Reads the per-row output of research/snnHistoryTrain.ts --rows true (one folder per arm and seed, any number of
 * chained runs inside) and reports, on liquid contracts (spread <= --max-spread) only:
 *   1. each arm's Brier vs the mid, and vs an FLB-corrected mid (y ~ a + b logit(mid), fitted on earlier folds only);
 *   2. each arm paired against the control of the same seed: mean, day-block CI, seed SD, folds won (6 x 16 days
 *      from Aug 1), RV terciles won, slope b, and the gain by |gap| quintile (is it concentrated in the top one?);
 *   3. a logistic probe (no SNN): does the gap add to logit(mid), and does the 1-minute stale gap do as well?
 *   4. the recorded tier: per recorded day paired gain, days won, worst day, leave-one-day-out range;
 *   5. H-B: the signed Kalshi mid response at +1 and +5 min to the fair-value gap and to the lagged 1-minute BTC
 *      return, clustered by market, the gap still open after 60 s against fee plus half-spread by state, and the
 *      24 h-shifted gap placebo.
 *
 *   node --import tsx research/snnLeadJudge.ts --arms "C:11=dir,C:22=dir,G:11=dir,..." [--control C] [--from 2026-08-07]
 *     [--to 2026-11-04] [--hb-from 2026-09-12] [--max-spread 0.1] [--out research/out/snn-h1-judge.md]
 */
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { dayBlockBootstrap } from '../bot/snn/blender';

export interface LRow { t: number; k: string; e: string; c: string; kd: string; p: number; m: number; f: number; y: 0 | 1; s?: number; g?: number; x?: number; v?: number; rec: boolean }

const DAY = 86_400_000;
const day = (t: number) => new Date(t).toISOString().slice(0, 10);
const logit = (p: number) => { const q = Math.min(1 - 1e-4, Math.max(1e-4, p)); return Math.log(q / (1 - q)); };
const sig = (z: number) => 1 / (1 + Math.exp(-z));
const brier = (p: number, y: number) => (p - y) * (p - y);
const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : NaN);
const sd = (a: number[]) => { const m = mean(a); return a.length > 1 ? Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)) : NaN; };
const f5 = (x: number) => (Number.isFinite(x) ? (x >= 0 ? '+' : '') + x.toFixed(5) : 'n/a');
const f2 = (x: number) => (Number.isFinite(x) ? x.toFixed(2) : 'n/a');

/** Every rows-*.jsonl.gz under a folder (chained runs in subfolders). A row seen twice (a resumed day) keeps the last. */
export function loadRows(dir: string): Map<string, LRow> {
  const out = new Map<string, LRow>();
  const files: string[] = [];
  const walk = (d: string) => { for (const f of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, f.name); if (f.isDirectory()) walk(p); else if (/^rows-[hr]-.*\.jsonl\.gz$/.test(f.name)) files.push(p); } };
  if (fs.existsSync(dir)) walk(dir);
  for (const f of files.sort()) {
    const rec = path.basename(f).startsWith('rows-r-');
    for (const line of zlib.gunzipSync(fs.readFileSync(f)).toString('utf8').split('\n')) {
      if (!line) continue;
      const r = JSON.parse(line) as Omit<LRow, 'rec'>;
      out.set(`${r.k}|${r.t}`, { ...r, rec });
    }
  }
  return out;
}

/** 6 folds of 16 days from Aug 1 2026 (HO-1 history tier). */
export function foldOf(t: number): number { return Math.floor((t - Date.parse('2026-08-01T00:00:00Z')) / (16 * DAY)); }

/** Weighted logistic regression by Newton steps (a few features): coefficients and standard errors. */
export function logistic(X: number[][], y: number[], iters = 25): { b: number[]; se: number[] } {
  const k = X[0]?.length ?? 0; let b = new Array(k).fill(0);
  let H: number[][] = [];
  for (let it = 0; it < iters; it++) {
    const g = new Array(k).fill(0); H = Array.from({ length: k }, () => new Array(k).fill(0));
    for (let i = 0; i < X.length; i++) {
      const p = sig(X[i].reduce((s, x, j) => s + x * b[j], 0)), w = p * (1 - p);
      for (let a = 0; a < k; a++) { g[a] += (y[i] - p) * X[i][a]; for (let c = 0; c < k; c++) H[a][c] += w * X[i][a] * X[i][c]; }
    }
    for (let a = 0; a < k; a++) H[a][a] += 1e-6;
    const step = solve(H, g);
    b = b.map((x, j) => x + step[j]);
    if (Math.max(...step.map(Math.abs)) < 1e-8) break;
  }
  const inv = invert(H);
  return { b, se: inv.map((r, j) => Math.sqrt(Math.max(0, r[j]))) };
}
function solve(A: number[][], v: number[]): number[] { const I = invert(A); return I.map((r) => r.reduce((s, x, j) => s + x * v[j], 0)); }
function invert(A: number[][]): number[][] {
  const n = A.length, M = A.map((r, i) => [...r, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
  for (let c = 0; c < n; c++) {
    let p = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    const d = M[c][c] || 1e-12;
    for (let j = 0; j < 2 * n; j++) M[c][j] /= d;
    for (let r = 0; r < n; r++) if (r !== c) { const f = M[r][c]; for (let j = 0; j < 2 * n; j++) M[r][j] -= f * M[c][j]; }
  }
  return M.map((r) => r.slice(n));
}

/** Event-clustered day-block CI of a per-row quantity. */
function evCi(rows: { e: string; t: number; x: number }[]) {
  const ev = new Map<string, { s: number; n: number; t: number }>();
  for (const r of rows) { const o = ev.get(r.e) ?? { s: 0, n: 0, t: r.t }; o.s += r.x; o.n++; ev.set(r.e, o); }
  const obs = [...ev.values()].map((o) => ({ day: day(o.t), x: o.s / o.n }));
  return obs.length ? dayBlockBootstrap(obs, 1000) : { mean: NaN, lo: NaN, hi: NaN, events: 0, days: 0 };
}

/** FLB-corrected mid, prequential: y ~ a + b logit(mid) fitted on every earlier fold (fold 0 uses the raw mid). */
function flbMid(rows: LRow[]): Map<LRow, number> {
  const out = new Map<LRow, number>();
  const byFold = new Map<number, LRow[]>();
  for (const r of rows) { const f = foldOf(r.t); byFold.set(f, [...(byFold.get(f) ?? []), r]); }
  const folds = [...byFold.keys()].sort((a, b) => a - b);
  const seen: LRow[] = [];
  for (const f of folds) {
    const fit = seen.length > 500 ? logistic(seen.map((r) => [1, logit(r.m)]), seen.map((r) => r.y)).b : undefined;
    for (const r of byFold.get(f)!) out.set(r, fit ? sig(fit[0] + fit[1] * logit(r.m)) : r.m);
    seen.push(...byFold.get(f)!);
  }
  return out;
}

const slope = (rows: LRow[]) => { let sxy = 0, sxx = 0; for (const r of rows) { const d = r.p - r.m; sxy += d * (r.y - r.m); sxx += d * d; } return sxx > 0 ? sxy / sxx : NaN; };
function quantiles(xs: number[], q: number[]): number[] { const s = [...xs].sort((a, b) => a - b); return q.map((p) => s[Math.min(s.length - 1, Math.floor(p * s.length))]); }

export interface ArmReport { name: string; arm: string; seed: string; n: number; vsMid: ReturnType<typeof evCi>; vsFlb: ReturnType<typeof evCi>; b: number }

export function judge(argv: string[]): string {
  const arg = (k: string, d = '') => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : d; };
  const from = Date.parse(`${arg('from', '2026-08-07')}T00:00:00Z`), to = Date.parse(`${arg('to', '2026-11-04')}T23:59:59Z`);
  const hbFrom = Date.parse(`${arg('hb-from', '2026-09-12')}T00:00:00Z`);
  const maxSpread = Number(arg('max-spread', '0.1'));
  const control = arg('control', 'C');
  const specs = arg('arms').split(',').filter(Boolean).map((s) => { const [name, dir] = s.split('='); const [arm, seed = '0'] = name.split(':'); return { name, arm, seed, dir }; });
  const L: string[] = [];
  L.push(`# SNN-H1 lead-info judge and H-B mid lag`, '', `Window ${day(from)} to ${day(to)} (history tier, prequential), liquid only (spread <= ${maxSpread}). Brier differences: negative is better.`, '');
  const data = new Map<string, Map<string, LRow>>();
  for (const s of specs) {
    const all = loadRows(s.dir);
    const keep = new Map<string, LRow>();
    for (const [k, r] of all) if (r.kd !== 'direction' && (r.s ?? 1) <= maxSpread + 1e-9 && r.t >= from && r.t <= to) keep.set(k, r);
    data.set(s.name, keep);
    L.push(`- ${s.name}: ${keep.size} liquid rows (${all.size} in all) from ${s.dir}`);
  }
  L.push('');

  // 1. Each arm vs the mid and vs the FLB-corrected mid (history rows; recorded days in section 4).
  const reports: ArmReport[] = [];
  L.push('## 1. Each arm vs the market', '', '| arm | rows | vs mid | vs FLB mid | b |', '|---|---|---|---|---|');
  for (const s of specs) {
    const rows = [...data.get(s.name)!.values()].filter((r) => !r.rec);
    const flb = flbMid(rows);
    const vsMid = evCi(rows.map((r) => ({ e: r.e, t: r.t, x: brier(r.p, r.y) - brier(r.m, r.y) })));
    const vsFlb = evCi(rows.map((r) => ({ e: r.e, t: r.t, x: brier(r.p, r.y) - brier(flb.get(r)!, r.y) })));
    const rep = { name: s.name, arm: s.arm, seed: s.seed, n: rows.length, vsMid, vsFlb, b: slope(rows) };
    reports.push(rep);
    L.push(`| ${s.name} | ${rows.length} | ${f5(vsMid.mean)} [${f5(vsMid.lo)}, ${f5(vsMid.hi)}] | ${f5(vsFlb.mean)} [${f5(vsFlb.lo)}, ${f5(vsFlb.hi)}] | ${f2(rep.b)} |`);
  }
  L.push('');

  // 2. Paired against the control of the same seed.
  L.push('## 2. Paired against the control (same seed)', '');
  const ctrlRows = specs.filter((s) => s.arm === control).flatMap((s) => [...data.get(s.name)!.values()].filter((r) => !r.rec));
  const rvCut = quantiles(ctrlRows.map((r) => r.v ?? 1), [1 / 3, 2 / 3]);
  const gapCut = quantiles(ctrlRows.map((r) => Math.abs(r.g ?? 0)), [0.2, 0.4, 0.6, 0.8]);
  const seedSd = (arm: string) => sd(reports.filter((r) => r.arm === arm).map((r) => r.vsMid.mean));
  L.push('| arm:seed | paired rows | dBrier vs control | folds won | RV terciles won | |gap| quintiles (low to high) | top quintile share | seed SD of arm vs mid |', '|---|---|---|---|---|---|---|---|');
  const pairedByArm = new Map<string, number[]>();
  for (const s of specs.filter((x) => x.arm !== control)) {
    const c = specs.find((x) => x.arm === control && x.seed === s.seed) ?? specs.find((x) => x.arm === control);
    if (!c) continue;
    const base = data.get(c.name)!;
    const pr: { e: string; t: number; x: number; v: number; g: number }[] = [];
    for (const [k, r] of data.get(s.name)!) { if (r.rec) continue; const o = base.get(k); if (o) pr.push({ e: r.e, t: r.t, x: brier(r.p, r.y) - brier(o.p, o.y), v: o.v ?? 1, g: Math.abs(o.g ?? 0) }); }
    const ci = evCi(pr);
    pairedByArm.set(s.arm, [...(pairedByArm.get(s.arm) ?? []), ci.mean]);
    const folds = new Map<number, number[]>(); for (const r of pr) folds.set(foldOf(r.t), [...(folds.get(foldOf(r.t)) ?? []), r.x]);
    const fw = [...folds.values()].filter((a) => mean(a) < 0).length;
    const rv = [0, 1, 2].map((i) => mean(pr.filter((r) => (r.v <= rvCut[0] ? 0 : r.v <= rvCut[1] ? 1 : 2) === i).map((r) => r.x)));
    const qOf = (g: number) => { const i = gapCut.findIndex((c2) => g <= c2); return i < 0 ? 4 : i; };
    const qn = [0, 1, 2, 3, 4].map((i) => pr.filter((r) => qOf(r.g) === i));
    const qm = qn.map((a) => (a.length ? a.reduce((x, r) => x + r.x, 0) : 0));
    const tot = qm.reduce((a, b) => a + b, 0);
    L.push(`| ${s.name} | ${pr.length} | ${f5(ci.mean)} [${f5(ci.lo)}, ${f5(ci.hi)}] | ${fw}/${folds.size} | ${rv.filter((x) => x < 0).length}/3 | ${qn.map((a) => f5(mean(a.map((r) => r.x)))).join(' ')} | ${tot < 0 ? f2(qm[4] / tot) : 'n/a'} | ${f5(seedSd(s.arm))} |`);
  }
  L.push('', 'Pass bar for G (pre-registered): paired dBrier <= -0.00015 with CI below 0, |gain| >= 2x the seed SD, >= 4 of 6 folds, >= 2 of 3 RV terciles, b in [0.7, 1.3], gain concentrated in the top |gap| quintile, and G beats both placebos. P is expected not to pass.', '');

  // 3. Logistic probe (no SNN): y ~ 1 + logit(mid) [+ gap/10] [+ stale gap/10], prequential log loss by fold.
  L.push('## 3. Logistic probe (no SNN)', '');
  const ctl0 = specs.find((s) => s.arm === control);
  if (ctl0) {
    const rows = [...data.get(ctl0.name)!.values()].filter((r) => !r.rec && r.g !== undefined).sort((a, b) => a.t - b.t);
    const byKT = new Map(rows.map((r) => [`${r.k}|${r.t}`, r]));
    const stale = (r: LRow) => byKT.get(`${r.k}|${r.t - 60_000}`)?.g;
    const usable = rows.filter((r) => stale(r) !== undefined);
    const feats = { mid: (r: LRow) => [1, logit(r.m)], gap: (r: LRow) => [1, logit(r.m), r.g! / 10], stale: (r: LRow) => [1, logit(r.m), stale(r)! / 10], both: (r: LRow) => [1, logit(r.m), r.g! / 10, stale(r)! / 10] };
    const ll = (p: number, y: number) => -(y * Math.log(Math.max(1e-9, p)) + (1 - y) * Math.log(Math.max(1e-9, 1 - p)));
    const folds = [...new Set(usable.map((r) => foldOf(r.t)))].sort((a, b) => a - b);
    const res: Record<string, number[]> = { mid: [], gap: [], stale: [], both: [] };
    const sub = (a: LRow[], n = 60_000) => (a.length > n ? a.filter((_, i) => i % Math.ceil(a.length / n) === 0) : a);
    for (const f of folds.slice(1)) {
      const train = sub(usable.filter((r) => foldOf(r.t) < f)), test = usable.filter((r) => foldOf(r.t) === f);
      for (const [name, fx] of Object.entries(feats)) {
        const { b } = logistic(train.map(fx), train.map((r) => r.y));
        res[name].push(mean(test.map((r) => ll(sig(fx(r).reduce((s, x, j) => s + x * b[j], 0)), r.y))));
      }
    }
    const full = logistic(sub(usable).map(feats.both), sub(usable).map((r) => r.y));
    L.push(`Rows with a 1-minute-earlier row of the same contract: ${usable.length}. Prequential log loss by fold (folds ${folds.slice(1).join(', ')}), minus the FLB-corrected mid's:`, '');
    for (const k of ['gap', 'stale', 'both']) L.push(`- ${k}: ${res[k].map((x, i) => f5(x - res.mid[i])).join(' ')} (mean ${f5(mean(res[k]) - mean(res.mid))})`);
    L.push(`- full-sample fit (subsampled): gap/10 coefficient ${f2(full.b[2])} (t ${f2(full.b[2] / full.se[2])}), stale gap/10 ${f2(full.b[3])} (t ${f2(full.b[3] / full.se[3])}). A speed edge shows as the current gap carrying weight the stale one does not.`, '');
  }

  // 4. Recorded tier: per recorded day, paired against the control.
  L.push('## 4. Recorded tier (leave-one-day-out)', '');
  for (const s of specs.filter((x) => x.arm !== control)) {
    const c = specs.find((x) => x.arm === control && x.seed === s.seed);
    if (!c) continue;
    const allS = loadRows(s.dir), allC = loadRows(c.dir);
    const byDay = new Map<string, number[]>();
    for (const [k, r] of allS) { if (!r.rec || (r.s ?? 1) > maxSpread + 1e-9) continue; const o = allC.get(k); if (o) byDay.set(day(r.t), [...(byDay.get(day(r.t)) ?? []), brier(r.p, r.y) - brier(o.p, o.y)]); }
    const days = [...byDay.keys()].sort();
    if (!days.length) { L.push(`- ${s.name}: no recorded days`); continue; }
    const dm = days.map((d) => mean(byDay.get(d)!));
    const all = days.flatMap((d) => byDay.get(d)!);
    const lodo = days.map((d) => mean(days.filter((x) => x !== d).flatMap((x) => byDay.get(x)!)));
    L.push(`- ${s.name}: ${days.length} days (${days[0]}..${days[days.length - 1]}), won ${dm.filter((x) => x < 0).length}/${days.length}, worst day ${f5(Math.max(...dm))}, pooled ${f5(mean(all))}, leave-one-day-out ${f5(Math.min(...lodo))}..${f5(Math.max(...lodo))}`);
  }
  L.push('');

  // 5. H-B: the Kalshi mid's response to the gap and to the lagged 1-minute BTC return (control rows; no SNN).
  if (ctl0) L.push(...hb([...data.get(ctl0.name)!.values()].filter((r) => !r.rec && r.t >= hbFrom), 'history tier'));
  return L.join('\n');
}

/** H-B on one set of rows (every row of one network: the market data are the same in every arm). */
export function hb(rows: LRow[], label: string): string[] {
  const L: string[] = [`## 5. H-B shared mid lag (${label}, ${rows.length} liquid rows)`, ''];
  const byKT = new Map(rows.map((r) => [`${r.k}|${r.t}`, r]));
  const btc = new Map<number, number>();
  for (const r of rows) if (r.c.startsWith('BTC-') && r.x) btc.set(Math.floor(r.t / 60_000), r.x);
  const colGap = new Map<string, number>();
  for (const r of rows) if (r.g !== undefined) colGap.set(`${r.c}|${Math.floor(r.t / 60_000)}`, r.g);
  const mono = (kd: string) => kd === 'updown' || kd === 'greater';
  const cluster = (xs: { k: string; x: number }[]) => {
    const m = new Map<string, number[]>(); for (const o of xs) m.set(o.k, [...(m.get(o.k) ?? []), o.x]);
    const per = [...m.values()].map(mean);
    return { n: xs.length, markets: per.length, mean: mean(xs.map((o) => o.x)), t: per.length > 1 ? (mean(per) / sd(per)) * Math.sqrt(per.length) : NaN };
  };
  const line = (name: string, c: ReturnType<typeof cluster>) => `| ${name} | ${c.n} | ${c.markets} | ${f2(c.mean)}c | ${f2(c.t)} |`;
  L.push('| signed mid change | rows | markets | mean | t (clustered by market) |', '|---|---|---|---|---|');
  for (const h of [60, 300]) {
    const gap: { k: string; x: number }[] = [], ret: { k: string; x: number }[] = [], plc: { k: string; x: number }[] = [], fair: { k: string; x: number }[] = [], bounce: { k: string; x: number }[] = [];
    for (const r of rows) {
      const n = byKT.get(`${r.k}|${r.t + h * 1000}`);
      if (!n || r.g === undefined) continue;
      const dm = (n.m - r.m) * 100;
      if (Math.abs(r.g) >= 0.5) gap.push({ k: r.k, x: Math.sign(r.g) * dm });
      const min = Math.floor(r.t / 60_000), b0 = btc.get(min), b1 = btc.get(min - 1);
      if (mono(r.kd) && b0 && b1 && b0 !== b1) ret.push({ k: r.k, x: Math.sign(b0 - b1) * dm });
      // Spot-only leg (all-pairs, Nov 6: the gap holds the mid's own quote noise, which reverts with no lag at all):
      // the fair value's own move over the last minute, and the quote-bounce null (the mid's own last-minute move).
      const p0 = byKT.get(`${r.k}|${r.t - 60_000}`);
      if (p0) {
        const df = (r.f - p0.f) * 100, dm0 = (r.m - p0.m) * 100;
        if (Math.abs(df) >= 0.25) fair.push({ k: r.k, x: Math.sign(df) * dm });
        if (dm0 !== 0) bounce.push({ k: r.k, x: -Math.sign(dm0) * dm });
      }
      const gp = colGap.get(`${r.c}|${Math.floor((r.t - DAY) / 60_000)}`);
      if (gp !== undefined && Math.abs(gp) >= 0.5) plc.push({ k: r.k, x: Math.sign(gp) * dm });
    }
    L.push(line(`+${h / 60} min, toward the gap (|gap| >= 0.5c)`, cluster(gap)), line(`+${h / 60} min, with the lagged 1-min BTC return`, cluster(ret)), line(`+${h / 60} min, toward the 24 h-shifted gap (placebo)`, cluster(plc)), line(`+${h / 60} min, with the fair value's own last-minute move (spot-only leg)`, cluster(fair)), line(`+${h / 60} min, against the mid's own last-minute move (quote-bounce null)`, cluster(bounce)));
  }
  L.push('', 'Gap still open after 60 s, in the gap\'s direction, minus fee plus half-spread (fee 7 p(1-p) c, half-spread 50 x spread c), by pre-registered state:', '', '| state | rows | markets | mean excess | t |', '|---|---|---|---|---|');
  const states: [string, (r: LRow, ret: number) => boolean][] = [
    ['all |gap| >= 0.5c', (r) => Math.abs(r.g!) >= 0.5], ['|gap| >= 3c', (r) => Math.abs(r.g!) >= 3], ['|gap| >= 5c', (r) => Math.abs(r.g!) >= 5],
    ['mid 0.3-0.7, |gap| >= 3c', (r) => Math.abs(r.g!) >= 3 && r.m >= 0.3 && r.m <= 0.7], ['|1-min BTC return| >= 10 bp, |gap| >= 1c', (r, ret) => Math.abs(r.g!) >= 1 && Math.abs(ret) >= 10],
  ];
  for (const [name, f] of states) {
    const xs: { k: string; x: number }[] = [];
    for (const r of rows) {
      if (r.g === undefined) continue;
      const n = byKT.get(`${r.k}|${r.t + 60_000}`);
      if (!n || n.g === undefined) continue;
      const min = Math.floor(r.t / 60_000), b0 = btc.get(min), b1 = btc.get(min - 1);
      const ret = b0 && b1 ? (b0 / b1 - 1) * 1e4 : 0;
      if (!f(r, ret)) continue;
      xs.push({ k: r.k, x: Math.sign(r.g) * n.g - (7 * n.m * (1 - n.m) + 50 * (n.s ?? 0)) });
    }
    L.push(line(name, cluster(xs)));
  }
  L.push('', 'Confirmed if the +1 and +5 min responses with the BTC return and with the fair value own move (spot-only legs) have t >= 3, the 24 h placebo does not, the toward-the-gap response is not explained by the quote-bounce row, and at least one state keeps a positive excess with t >= 3. History quotes are minute candles: the latency curve (0 to 2000 ms) needs the recorded books (research/midLagLatency.ts).', '');
  return L;
}

if (process.argv[1] && /snnLeadJudge\.ts$/.test(process.argv[1])) {
  const argv = process.argv.slice(2);
  const outArg = argv.indexOf('--out');
  const out = outArg >= 0 ? argv[outArg + 1] : 'research/out/snn-h1-judge.md';
  const text = judge(argv);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, text + '\n');
  console.log(text);
}
