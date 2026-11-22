import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { depthStudy } from '../research/depthStudy';
import { tmpDir } from './helpers';

const D0 = Date.UTC(2026, 9, 20);
const MIN = 60_000;

test('the depth study splits the trade flow by where the mid goes over each quarter-minute', async () => {
  const dir = tmpDir();
  const lines: object[] = [{ t: D0 - MIN, k: 'market', ticker: 'KXBTC15M-A', series: 'KXBTC15M', kind: 'updown', closeTime: D0 + 60 * MIN }];
  const book = (t: number, bid: number) => ({ t, k: 'book', ticker: 'KXBTC15M-A', bids: [{ price: +bid.toFixed(2), size: 50 }], asks: [{ price: +(bid + 0.02).toFixed(2), size: 50 }] });
  // Quarter-minutes in fours: a rise with three YES takers, a still one with one trade a side, a fall with three NO
  // takers, a still one again (the quote moves late in its quarter-minute, after the trades that move it).
  lines.push(book(D0 - 1000, 0.45));
  for (let q = 0; q < 48; q++) {
    const t = D0 + q * 15_000, phase = q % 4, bid = phase === 0 || phase === 3 ? 0.45 : 0.46;
    if (phase === 0 || phase === 2) {
      const yes = phase === 0;
      for (let i = 1; i <= 3; i++) lines.push({ t: t + i * 3000, k: 'trade', ticker: 'KXBTC15M-A', price: 0.46, count: 2, takerSide: yes ? 'yes' : 'no', ts: t + i * 3000 });
      lines.push(book(t + 12_000, yes ? 0.46 : 0.45));
    } else for (const side of ['yes', 'no']) lines.push({ t: t + 5000, k: 'trade', ticker: 'KXBTC15M-A', price: bid, count: 1, takerSide: side, ts: t + 5000 });
  }
  lines.push({ t: D0 + 60 * MIN + 1, k: 'result', ticker: 'KXBTC15M-A', result: 'yes' });
  const file = path.join(dir, 'md-2026-10-20.jsonl.gz');
  fs.writeFileSync(file, zlib.gzipSync(lines.map((e) => JSON.stringify(e)).join('\n') + '\n'));
  const r = await depthStudy([file]);
  const sum = (k: number) => r.shape.reduce((a, c) => ({ segs: a.segs + c.byMove[k].segs, trades: a.trades + c.byMove[k].tradesPerSec * c.byMove[k].segs * 15, yes: a.yes + (c.byMove[k].takerYesShare ?? 0) * c.byMove[k].tradesPerSec * c.byMove[k].segs * 15 }), { segs: 0, trades: 0, yes: 0 });
  const up = sum(2), flat = sum(1), down = sum(0);
  assert.ok(up.segs >= 10 && down.segs >= 10 && flat.segs >= 20, `${up.segs} up, ${flat.segs} flat, ${down.segs} down`);
  assert.ok(Math.abs(up.yes / up.trades - 1) < 1e-6, 'the rises were all YES takers');
  assert.ok(Math.abs(down.yes / down.trades) < 1e-6, 'the falls were all NO takers');
  assert.ok(Math.abs(flat.yes / flat.trades - 0.5) < 0.01, 'the still quarter-minutes, one of each');
  assert.ok(up.trades / up.segs > flat.trades / flat.segs);
});

// ---------------------------------------------------------------------------------------------------------------
// Round R1 (Nov 22): the study per asset and per causal stress bucket (schema 2 of the model file).
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { assetLines, stressTerciles } from '../research/depthStudy';
import { DEPTH_MODEL_SCHEMA } from '../research/history/depthModelVersion';
import { minuteStress, stressBucket, STRESS_GRID, stressBin, type DepthModel } from '../research/history/depthSim';
import { CLASSES, synthRecording, writeRecording, MINUTE, SYNTH_OPEN, type SynthClass } from './depthStudySynth';

const BTC = { name: 'BTC', size: 4000, trades: 30 }, ETH = { name: 'ETH', size: 200, trades: 3 };
const studyOf = async (events: readonly object[]) => {
  const file = path.join(tmpDir(), 'md-2026-11-11.jsonl.gz');
  writeRecording(file, events);
  return depthStudy([file], '15m');
};
type Row = { ti: number; mi: number; si?: number; samples: number; depth10: { p50: number }; tradesPerMin: { mean: number }; tradeSize: { p50: number }; gapShare?: number };
const rowsOf = (r: Awaited<ReturnType<typeof studyOf>>, a: string): Row[] => r.byAsset[a].shape as unknown as Row[];

test('two assets of very different scale give different asset blocks, and the model file says its schema', async () => {
  const r = await studyOf(synthRecording([BTC, ETH]).events);
  assert.equal(r.schema, DEPTH_MODEL_SCHEMA);
  assert.deepEqual(Object.keys(r.byAsset).sort(), ['BTC', 'ETH']);
  const own = (a: string, ti: number) => rowsOf(r, a).find((x) => x.ti === ti && x.mi === 3 && x.si === undefined)!;
  for (const ti of [1, 2, 3, 4]) {
    const b = own('BTC', ti), e = own('ETH', ti);
    assert.ok(b.samples >= 20 && e.samples >= 20);
    // the books are 20x deeper in BTC (4000 against 200 contracts a level) and the trade rate 10x
    assert.ok(b.depth10.p50 / e.depth10.p50 > 15 && b.depth10.p50 / e.depth10.p50 < 25, `depth10 ratio ${b.depth10.p50 / e.depth10.p50}`);
    assert.ok(Math.abs(b.tradesPerMin.mean / e.tradesPerMin.mean - 10) < 0.5, `trades ratio ${b.tradesPerMin.mean / e.tradesPerMin.mean}`);
  }
  // the pooled rows are the mixture of the two: between them, and nothing like either
  const pooled = r.shape.find((x) => x.ti === 3 && x.mi === 3)!;
  assert.ok(pooled.depth10.p50 > own('ETH', 3).depth10.p50 && pooled.depth10.p50 < own('BTC', 3).depth10.p50 * 1.01);
  // the model's rows read back as a model, and the per-asset summary lines are short and carry numbers only
  const model = { days: ['2026-11-11'], ...r } as unknown as DepthModel;
  assert.ok(model.byAsset!.BTC.stress!.edges.length === 2);
  const lines = assetLines(r);
  assert.equal(lines.length, 2);
  for (const l of lines) { assert.ok(l.length < 300, `${l.length} characters`); assert.match(l, /^\[depth\] asset (BTC|ETH): \d+ samples; rows \d+ \+ \d+ stress \(flow \d+ \+ \d+\); stress edges [\d./]+c; back off to pooled \d+, stress to asset \d+; trades\/min p50 [\d.]+, depth10 p50 [\d.]+; first quote [\d.]+ slots after open; empty-side share [\d.]+%; real unquoted [\d.]+% of a life$/); }
  assert.match(lines[0], /trades\/min p50 240, depth10 p50 34802/);
  assert.match(lines[1], /trades\/min p50 24, depth10 p50 1742/);
});

test('the stress terciles are cut at the asset\'s own samples, and the study buckets every sample with the same definition the simulator uses', async () => {
  const r = await studyOf(synthRecording([BTC, ETH]).events);
  for (const a of ['BTC', 'ETH']) {
    const b = r.byAsset[a];
    assert.deepEqual(b.stress!.edges, [0, 1], `${a}: calm is 0c, normal up to 1c`);
    // every row of a stress bucket is a bucket 0, 1 or 2 row of an asset row; the thinner, busier books are the active ones
    const at = (ti: number, si?: number) => rowsOf(r, a).find((x) => x.ti === ti && x.mi === 3 && x.si === si)!;
    for (const ti of [2, 3, 4]) {
      assert.ok(at(ti, 0).depth10.p50 > at(ti, 1).depth10.p50 && at(ti, 1).depth10.p50 > at(ti, 2).depth10.p50, `${a} ti ${ti}: depth falls with stress`);
      assert.ok(at(ti, 0).tradesPerMin.mean < at(ti, 1).tradesPerMin.mean && at(ti, 1).tradesPerMin.mean < at(ti, 2).tradesPerMin.mean, `${a} ti ${ti}: trades rise with stress`);
    }
  }
  // An independent count: the stress of each 15 s sample of each synthetic contract, from the formula that made its quotes, with the
  // model's edges. The sample at a minute stamp sees the quote of the minute before (it is taken before the stamp's own records).
  const mid: Record<SynthClass, (m: number) => number> = { calm: () => 50, normal: (m) => 50 + (m % 2), active: (m) => 50 + 4 * (m % 2) };
  const expected = new Map<string, number>();
  const tauBucket = (tau: number) => [1, 3, 6, 10, 15, 60].findIndex((e) => tau < e);
  for (const a of ['BTC', 'ETH']) for (const cls of CLASSES) for (let q = 0; q < 60; q++) {
    const m = Math.floor(q / 4), M = (k: number) => (k < 0 || k > m ? undefined : k === 0 ? mid[cls](0) : mid[cls](k - 1));
    const v = minuteStress(M, m);
    if (v === undefined) continue;
    const key = `${a}|${tauBucket(15 - q / 4)}|${stressBucket(r.byAsset[a].stress!.edges, v)}`;
    expected.set(key, (expected.get(key) ?? 0) + 8);
  }
  let checked = 0;
  for (const a of ['BTC', 'ETH']) for (const x of rowsOf(r, a)) if (x.si !== undefined) { assert.equal(x.samples, expected.get(`${a}|${x.ti}|${x.si}`), `${a} ti ${x.ti} si ${x.si}`); checked++; }
  for (const [k, n] of expected) if (n >= 20) { const [a, ti, si] = k.split('|'); assert.ok(rowsOf(r, a).some((x) => x.ti === +ti && x.si === +si), `a row for ${k}`); }
  assert.ok(checked >= 20);
  // the grid the edges come from, and the tercile rule on its own
  assert.equal(stressBin(0), 0); assert.equal(stressBin(0.2), 4); assert.equal(stressBin(0.2000001), 5); assert.equal(stressBin(99), STRESS_GRID.length);
  const hist = new Array(STRESS_GRID.length + 1).fill(0); hist[0] = 100; hist[10] = 100; hist[14] = 100;
  assert.deepEqual(stressTerciles(hist), { edges: [0, 1], bins: [0, 10], n: 300 }, 'a third each: the edges are the grid values the first and second third end at');
  const skew = new Array(STRESS_GRID.length + 1).fill(0); skew[0] = 250; skew[4] = 30; skew[8] = 20;
  assert.deepEqual(stressTerciles(skew)!.edges, [0, 0], 'most of the samples at 0: both edges are 0, bucket 1 is empty and its contracts use the asset row');
  assert.equal(stressTerciles(new Array(STRESS_GRID.length + 1).fill(0).map((_, i) => (i === 3 ? 50 : 0))), undefined, 'too few samples: no stress buckets');
});

test('the asset blocks hold the pooled rows\' meaning: the pooled shape, flow and informed blocks equal the base commit\'s study on the same recording (when the base commit is in this checkout)', async (t) => {
  const BASE = 'afa80e8', ROOT = process.cwd();
  const show = (f: string) => spawnSync('git', ['show', `${BASE}:${f}`], { cwd: ROOT, encoding: 'utf8', maxBuffer: 16 << 20 });
  const study = show('research/depthStudy.ts'), sim = show('research/history/depthSim.ts');
  if (study.status !== 0 || sim.status !== 0 || !study.stdout.includes('INFORMED_MS')) { t.skip(`commit ${BASE} is not in this checkout (a shallow clone)`); return; }
  const dir = path.join(tmpDir(), 'base'), at = (f: string) => path.join(ROOT, f).split(path.sep).join('/');
  fs.mkdirSync(path.join(dir, 'research/history'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'research/depthStudy.ts'), study.stdout.replace("'../bot/marketdata/orderBook'", `'${at('bot/marketdata/orderBook')}'`).replace("'../bot/marketdata/recordingFiles'", `'${at('bot/marketdata/recordingFiles')}'`));
  fs.writeFileSync(path.join(dir, 'research/history/depthSim.ts'), sim.stdout.replace("from './historyReplay'", `from '${at('research/history/historyReplay')}'`));
  const base = await import(pathToFileURL(path.join(dir, 'research/depthStudy.ts')).href) as { depthStudy: typeof depthStudy };
  const events = synthRecording([BTC, ETH]).events;
  const file = path.join(tmpDir(), 'md-2026-11-11.jsonl.gz');
  writeRecording(file, events);
  const was = await base.depthStudy([file], '15m'), now = await depthStudy([file], '15m');
  const key = (x: { ti?: number; mi?: number; offset?: number; queue?: string }) => `${String(x.ti ?? x.offset).padStart(3)}|${x.mi ?? x.queue}`;
  // the new rows add `gapShare` (the study's new measurement); everything the old rows said is the same, number for number
  const strip = (rows: Array<Record<string, unknown>>) => rows.map(({ gapShare: _g, ...rest }) => rest).sort((x, y) => key(x as never).localeCompare(key(y as never)));
  assert.ok(was.shape.length >= 5 && was.flow.length >= 20);
  assert.deepEqual(strip(now.shape as never), strip(was.shape as never));
  assert.deepEqual(strip(now.flow as never), strip(was.flow as never));
  assert.deepEqual(now.informed, was.informed);
});

test('the study measures the 15 s instants a book had an empty side (gapShare) and how long after its open a contract was first quoted', async () => {
  // ETH calm contracts lose their ask side in every fifth quarter-minute (the ask delta of that quarter is not sent either)
  const { events } = synthRecording([ETH], { perClass: 8 });
  const q = (e: Record<string, any>) => Math.floor((e.t - SYNTH_OPEN) / 15_000);
  const gap = (e: Record<string, any>) => /-C\d$/.test(String(e.ticker)) && q(e) % 5 === 4;
  const cut = events.filter((e) => !(gap(e) && e.k === 'delta' && e.side === 'ask')).map((e) => (gap(e) && e.k === 'book' ? { ...e, asks: [] } : e));
  const r = await studyOf(cut);
  const rows = rowsOf(r, 'ETH');
  const calm = rows.filter((x) => x.si === 0 && x.mi === 3 && x.ti >= 1 && x.ti <= 4), other = rows.filter((x) => (x.si === 1 || x.si === 2) && x.mi === 3);
  assert.ok(calm.length >= 3);
  // a gap quarter's book is one-sided for the whole quarter, so the next sample (taken just before the next quarter's snapshot) sees it:
  // 11 of a calm contract's 60 instants (the calm class is bucket 0, with the first minutes of the others, which never gap); a row's
  // own share moves with the instants it holds (the last minute holds 4, one of them a gap)
  let sam = 0, gaps = 0;
  for (const x of calm) { assert.ok(x.gapShare! > 0.05 && x.gapShare! < 0.4, `calm gapShare ${x.gapShare}`); sam += x.samples; gaps += x.gapShare! * x.samples / (1 - x.gapShare!); }
  assert.ok(gaps / (sam + gaps) > 0.12 && gaps / (sam + gaps) < 0.24, `calm instants with an empty side ${(gaps / (sam + gaps)).toFixed(3)}`);
  for (const x of other) assert.equal(x.gapShare, 0, 'the contracts that kept both sides have none');
  // the pooled rows say it too, as the shape rows' new field
  assert.ok(r.shape.every((x) => typeof (x as { gapShare?: number }).gapShare === 'number'));
  // every contract was quoted at its open: the first quote is 0 slots after it (ETH block's fit summary)
  assert.equal(r.byAsset.ETH.fit.firstQuoteSlotsP50, 0);
  // a contract whose book is empty until 45 s after its open is first quoted 3 slots late
  const late = synthRecording([ETH], { perClass: 8 }).events.filter((e) => !(e.t >= SYNTH_OPEN && e.t < SYNTH_OPEN + 45_000 && (e.k === 'book' || e.k === 'delta' || e.k === 'trade')));
  assert.equal((await studyOf(late)).byAsset.ETH.fit.firstQuoteSlotsP50, 3);
});

test('a study run does not carry the informed-flow and trade counts of an earlier run in the same process', async () => {
  const events = synthRecording([ETH], { perClass: 2 }).events;
  const a = await studyOf(events), b = await studyOf(events);
  assert.deepEqual(b.informed, a.informed);
});

test('the CLI writes the model file with its schema, the days and the asset blocks, and the workflow\'s log filter keeps the per-asset lines as short `[twin] depth model:` lines', () => {
  const dir = tmpDir(), out = path.join(dir, 'models', 'depth_model.json');
  writeRecording(path.join(dir, 'md-2026-11-11.jsonl.gz'), synthRecording([BTC, ETH]).events);
  const r = spawnSync(process.execPath, ['--import', 'tsx', 'research/depthStudy.ts', '--recordings', dir, '--days', '2026-11-11', '--series', '15m', '--out', out], { encoding: 'utf8', maxBuffer: 16 << 20 });
  assert.equal(r.status, 0, r.stderr);
  const model = JSON.parse(fs.readFileSync(out, 'utf8')) as DepthModel & { days: string[] };
  assert.deepEqual(model.days, ['2026-11-11']);
  assert.equal(model.schema, DEPTH_MODEL_SCHEMA);
  assert.deepEqual(Object.keys(model.byAsset!), ['BTC', 'ETH']);
  assert.ok(model.shape.length >= 5 && model.byAsset!.BTC.shape.some((x) => x.si === 2));
  // the build step's own filter (history-twin.yml, "The depth model, fitted on the FIT days only")
  const f = spawnSync('bash', ['-c', "grep -E '^\\[depth\\]| n=' | sed -E 's/^\\[depth\\]/[twin] depth model:/; s/^  /[twin] depth cell: /' | cut -c1-420 | head -70"], { input: r.stdout, encoding: 'utf8' });
  const lines = f.stdout.split('\n').filter(Boolean);
  const asset = lines.filter((l) => l.startsWith('[twin] depth model: asset '));
  assert.equal(asset.length, 2);
  assert.ok(asset.every((l) => l.length < 300));
  assert.ok(lines.findIndex((l) => l.includes('asset BTC')) < 6, 'the asset lines come first, where the sweep\'s head -5 keeps them');
  assert.match(lines[0], /^\[twin\] depth model: 1 day\(s\): 2026-11-11\.\.2026-11-11, contracts: 15-minute only, schema 3$/);
  assert.ok(lines.length <= 70);
});

// ---------------------------------------------------------------------------------------------------------------
// R1 fix round 1 (Nov 22): the study measures the unquoted share of a WHOLE life (the lead before the first quote and every empty or crossed
// instant, over the judge's slots), per asset and pooled: what the simulator nets its empty-side draw against.
import { rowBuilder } from '../research/historyTwin';

test('the study measures the real unquoted share of a whole life and the slots before the first quote, per asset and pooled', async () => {
  // every contract quoted at its open and never one-sided: nothing unquoted (the quote at the exact 15 s mark is the study's first sample)
  const r = await studyOf(synthRecording([BTC, ETH]).events);
  assert.deepEqual(r.byAsset.BTC.lives, { n: 24, unquotedShare: 0, leadSlots: 0 });
  assert.deepEqual(r.byAsset.ETH.lives, { n: 24, unquotedShare: 0, leadSlots: 0 });
  assert.deepEqual(r.lives, { n: 48, unquotedShare: 0, leadSlots: 0 }, 'the pooled stats are over every asset');
  assert.equal(r.byAsset.ETH.fit.unquotedShare, 0);
  // a contract with no book until 45 s after its open is unquoted for those 3 slots (and the fit summary says first quote 3 slots after open)
  const late = synthRecording([ETH], { perClass: 8 }).events.filter((e) => !(e.t >= SYNTH_OPEN && e.t < SYNTH_OPEN + 45_000 && (e.k === 'book' || e.k === 'delta' || e.k === 'trade')));
  const lr = await studyOf(late);
  assert.equal(lr.byAsset.ETH.lives!.leadSlots, 3);
  assert.ok(Math.abs(lr.byAsset.ETH.lives!.unquotedShare - 3 / 60) < 1e-4, `${lr.byAsset.ETH.lives!.unquotedShare}`);
  assert.equal(lr.byAsset.ETH.fit.firstQuoteSlotsP50, 3);
  // ETH calm contracts lose their ask side in every fifth quarter-minute: 11 of the calm contract's 60 sampled instants, and none of the others'
  const { events } = synthRecording([ETH], { perClass: 8 });
  const q = (e: Record<string, any>) => Math.floor((e.t - SYNTH_OPEN) / 15_000);
  const gap = (e: Record<string, any>) => /-C\d$/.test(String(e.ticker)) && q(e) % 5 === 4;
  const cut = events.filter((e) => !(gap(e) && e.k === 'delta' && e.side === 'ask')).map((e) => (gap(e) && e.k === 'book' ? { ...e, asks: [] } : e));
  const gr = await studyOf(cut);
  assert.ok(Math.abs(gr.byAsset.ETH.lives!.unquotedShare - (8 * (11 / 60)) / 24) < 1e-3, `${gr.byAsset.ETH.lives!.unquotedShare}`);
  assert.equal(gr.byAsset.ETH.lives!.leadSlots, 0, 'the gaps come after the first quote: no lead');
  // the line the fit step logs says it
  assert.match(assetLines(gr)[0], /empty-side share [\d.]+%; real unquoted 6\.11% of a life$/);
  // too few lives (3 of ETH): no stats of its own and none pooled; the simulator then plays the rows as measured
  const few = await studyOf(synthRecording([ETH], { perClass: 1 }).events);
  assert.equal(few.byAsset.ETH.lives, undefined);
  assert.equal(few.lives, undefined);
  assert.match(assetLines(few)[0], /real unquoted n\/a% of a life$/);
});

test('the study\'s unquoted share is the judge\'s: on one recording both count the same slots (the study from the recorded books, the judge from the records)', async () => {
  // the same recording with every record 0.5 s late, as a real recording's stamps are (a snapshot is never exactly on the 15 s mark)
  const { events } = synthRecording([ETH], { perClass: 8 });
  const q = (e: Record<string, any>) => Math.floor((e.t - SYNTH_OPEN) / 15_000);
  const gap = (e: Record<string, any>) => q(e) % 5 === 4 && q(e) >= 10;
  const shifted = events.filter((e) => !(gap(e) && e.k === 'delta' && e.side === 'ask')).map((e) => (e.k === 'market' || e.k === 'result' ? e : { ...e, t: e.t + 500, ...(gap(e) && e.k === 'book' ? { asks: [] } : {}) }));
  const r = await studyOf(shifted);
  const day = '2026-11-11';
  const rb = rowBuilder(day, 'real', new Map(), undefined, false);
  for (const e of shifted) rb.push(e);
  const rows = rb.finish();
  assert.equal(rows.length, 24);
  const judged = rows.reduce((s, x) => s + (1 - x.f[3]), 0) / rows.length;
  // 1 slot at the open (taken before the first snapshot) and the empty sides, in both; the slot at the close the study does not see
  assert.ok(Math.abs(r.byAsset.ETH.lives!.unquotedShare - judged) < 0.02, `study ${r.byAsset.ETH.lives!.unquotedShare}, judge ${judged.toFixed(4)}`);
  assert.equal(r.byAsset.ETH.lives!.leadSlots, 1, 'the slot at the open is before the first snapshot, as the judge counts it');
  assert.ok(judged > 0.15, 'there is something to count');
});
