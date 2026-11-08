import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { CausalAtlasFeatures } from '../research/opportunity/features';
import { buildDecisionDataset, referenceWindows, type DecisionObservation, type DecisionPathEntry, type DecisionDatasetOptions } from '../research/opportunity/decisionDataset';
import { exportDecisionDataset } from '../research/opportunity/decisionDatasetCli';
import { defaultPathConfig, PathLabeler, type PathLabel } from '../research/opportunity/pathLabels';
import type { Candle } from '../bot/ta/indicators';

const MIN = 60000, start = Date.UTC(2024, 5, 3, 12);
const digest = (s: string) => createHash('sha256').update(s).digest('hex');
function candles(n = 90, from = start): Candle[] {
  return Array.from({ length: n }, (_, i) => {
    const c = 100 + i * 0.01 + Math.sin(i / 7) * 0.1;
    return { ts: from + i * MIN, o: c, h: c + 0.2, l: c - 0.3, c, v: 2 };
  });
}
function archive(bars = candles(), assets = ['BTC']) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-decisions-'));
  const files = assets.map((asset) => {
    const name = `binance-1m/${asset}/1m.csv`, file = path.join(root, 'history', name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const contents = 'ts,o,h,l,c,v\n' + bars.map((c) => [c.ts, c.o, c.h, c.l, c.c, c.v].join(',') + '\n').join('');
    fs.writeFileSync(file, contents);
    return { path: name, ready: true, source: 'binance-1m', sha256: digest(contents), rows: bars.length };
  });
  fs.writeFileSync(path.join(root, 'archive-validation.json'), JSON.stringify({ schema: 'atlas-archive-audit-v1', files }));
  return root;
}
async function collect(bars = candles(), patch: Partial<DecisionDatasetOptions> = {}, assets = ['BTC']) {
  const root = archive(bars, assets), decisions: DecisionObservation[] = [], labels: PathLabel<DecisionPathEntry>[] = [];
  try {
    const report = await buildDecisionDataset({ archiveDir: root, assets, path: { horizonsMin: [1, 3], targetsAtr: [3], stopsAtr: [3] }, ...patch,
      onDecision(row) { decisions.push(row); }, onLabels(rows) { labels.push(...rows); } });
    return { report, decisions, labels };
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

test('minute observations join full features to exact remaining-time spot labels without detector gating', async () => {
  const bars = candles(), { decisions, labels, report } = await collect(bars);
  assert.equal(decisions.length, 90);
  assert.equal(report.featureInputAudit.everyMinutes, 1);
  assert.equal(new Set(decisions.map((d) => d.decisionId)).size, 90);
  const d = decisions.find((d) => d.frame.decisionAt === start + 21 * MIN)!;
  assert.deepEqual(d.referenceWindows.map((c) => c.remainingMinutes), [9, 39]);
  assert.deepEqual(d.horizonsMin, [1, 3, 9, 39]);
  assert.equal(d.labelStatus, 'scheduled');
  const label = labels.find((l) => l.entry.decisionId === d.decisionId && l.horizonMin === 9 && l.side === 'long')!;
  assert.equal(label.entry.ts, d.frame.decisionAt); assert.equal(label.entry.price, bars[20].c);
  assert.equal(label.provenance.labelKnownAt, start + 30 * MIN);
  assert.equal(label.observedMinutes, 9); assert.equal(label.censorReason, null);
  assert.equal(label.exitPrice, bars[29].c, 'the nine future minutes end at the reference close');
  const future = bars.slice(21, 30);
  assert.ok(Math.abs(label.mfeBps - (Math.max(...future.map((b) => b.h)) / bars[20].c - 1) * 10000) < 1e-9);
  assert.ok(!('rsi' in label.entry.f), 'full features live in the observation, not a legacy narrow entry vector');
  assert.equal(label.entry.inputSha256, d.frame.groups.spot_1m.sha256);
  assert.equal(d.frame.groups.yahoo_daily.status, 'missing');
  assert.ok(report.unavailableInputs.includes('SNN temporal state'));
  assert.equal(report.liveEntryAllowed, false);
  assert.throws(() => (d.horizonsMin as number[]).push(999), TypeError);
});

test('sparse decision sampling still observes every intervening minute for target horizons', async () => {
  const { decisions, labels } = await collect(candles(), { everyMinutes: 5 });
  assert.equal(decisions.length, 18);
  const d = decisions.find((d) => d.frame.decisionAt === start + 20 * MIN)!;
  const label = labels.find((l) => l.entry.decisionId === d.decisionId && l.horizonMin === 3)!;
  assert.equal(label.observedMinutes, 3);
  assert.equal(label.provenance.labelKnownAt, start + 23 * MIN, 'three actual minutes, not three sampled frames');
  assert.equal(label.censorReason, null);
});

test('held-out prices never enter targets, including pending development labels crossing the final boundary', async () => {
  const from = Date.UTC(2025, 11, 31, 23, 10), boundary = Date.parse('2026-01-01');
  const a = candles(80, from), b = a.map((c) => c.ts < boundary ? c : { ...c, o: 500, h: 501, l: 499, c: 500 });
  const x = await collect(a), y = await collect(b);
  for (const d of x.decisions.filter((d) => d.frame.decisionAt >= boundary)) assert.equal(d.labelStatus, 'reserved-final');
  assert.ok(x.labels.some((l) => l.partition === 'purged'));
  assert.ok(x.labels.every((l) => l.entry.ts < boundary && l.provenance.observedThrough <= boundary && l.provenance.labelKnownAt <= boundary));
  const target = (l: PathLabel<DecisionPathEntry>) => ({ ts: l.entry.ts, h: l.horizonMin, side: l.side,
    known: l.provenance.labelKnownAt, censor: l.censorReason, partition: l.partition, hit: l.firstHit,
    mfe: l.mfeBps, mae: l.maeBps, exit: l.exitPrice, reversals: l.reversals });
  assert.deepEqual(x.labels.map(target), y.labels.map(target), 'changing final prices cannot change any exported target');
  assert.equal(x.report.assets[0].partitions.final, 0);
  const allFinal = await collect(candles(40, boundary));
  assert.equal(allFinal.labels.length, 0); assert.equal(allFinal.report.assets[0].reservedFinal, 40);
  const partialMinute = await collect(candles(40), { trainBefore: start + 20 * MIN, finalFrom: start + 25.5 * MIN });
  assert.ok(partialMinute.labels.every((l) => l.provenance.observedThrough <= start + 25 * MIN), 'a minute straddling the cut is not consumed');
});

test('gaps censor pending labels and restart the label scale without inventing feature rows', async () => {
  const bars = candles(75).filter((_, i) => i !== 25), { decisions, labels } = await collect(bars);
  assert.equal(decisions.length, 74); assert.ok(labels.some((l) => l.censorReason === 'gap'));
  assert.ok(!decisions.some((d) => d.frame.decisionAt === start + 26 * MIN));
  const after = decisions.find((d) => d.frame.decisionAt === start + 27 * MIN)!;
  assert.equal(after.labelStatus, 'unavailable-scale'); assert.equal(after.anchor.atrBps, null);
  assert.equal(after.frame.gapsSeen, 1);
  assert.ok(labels.filter((l) => l.censorReason === 'gap').every((l) => l.provenance.labelKnownAt === start + 27 * MIN));
});

test('processing caps, asset boundaries and zero volatility remain explicit', async () => {
  const limited = await collect(candles(80), { maxMinutes: 25 }, ['BTC', 'ETH']);
  assert.equal(limited.decisions.length, 50); assert.equal(limited.report.assets.length, 2);
  assert.equal(new Set(limited.decisions.map((d) => d.decisionId)).size, 50);
  assert.ok(limited.labels.some((l) => l.censorReason === 'processing-limit'));
  for (const l of limited.labels) {
    const d = limited.decisions.find((d) => d.decisionId === l.entry.decisionId)!;
    assert.equal(l.entry.asset, d.frame.asset);
  }
  const flat = await collect(candles(30).map((b) => ({ ...b, o: 100, h: 100, l: 100, c: 100 })));
  assert.equal(flat.decisions.length, 30); assert.equal(flat.labels.length, 0);
  assert.equal(flat.report.assets[0].unavailableScale, 30);
});

test('raw entry ATR is causal, resets after gaps and does not invert clipped TA features', () => {
  const p = new CausalAtlasFeatures('BTC', { source: 'test', sha256: null });
  for (const b of candles(13)) p.push(b);
  assert.equal(p.entryAnchor().atrBps, null);
  p.push(candles(14).at(-1)!); assert.ok(p.entryAnchor().atrBps! > 0);
  const known = p.entryAnchor();
  p.push(candles(16).at(-1)!); assert.equal(p.entryAnchor().atrBps, null);
  assert.equal(known.knownAt, start + 14 * MIN);
  const tiny = new CausalAtlasFeatures('BTC', { source: 'test', sha256: null });
  for (const b of candles(40)) tiny.push({ ...b, o: 100, h: 100 + 1e-12, l: 100 - 1e-12, c: 100 });
  assert.equal(tiny.snapshot().groups.spot_1m.values.log_atr_pct, -15);
  assert.ok(tiny.entryAnchor().atrBps! < 1e-5, 'label ATR must retain raw precision');
});

test('per-entry horizons preserve independent schedules, validate before mutation and snapshot caller arrays', () => {
  const L = new PathLabeler<DecisionPathEntry>({ ...defaultPathConfig('test', start + 1000 * MIN, start + 2000 * MIN), horizonsMin: [1, 10], targetsAtr: [1], stopsAtr: [1] });
  const bars = candles(5), e: DecisionPathEntry = { ts: bars[0].ts + MIN, price: bars[0].c, asset: 'BTC', f: { atrBps: 100, knownAt: bars[0].ts + MIN },
    decisionId: 'test', inputSha256: 'test', anchorDefinition: 'builtin-ATR14-over-last-1440-contiguous-1m-bars' };
  assert.throws(() => L.push(bars[0], e, [3, 2]), /horizons/);
  assert.throws(() => L.push(bars[0], e, [11]), /horizons/);
  const horizons = [2, 4]; L.push(bars[0], e, horizons); horizons[0] = 9;
  assert.deepEqual(L.push(bars[1]), []);
  assert.deepEqual(L.push(bars[2]).map((l) => l.horizonMin), [2, 2]);
  const e2 = { ...e, decisionId: 'second', ts: bars[3].ts + MIN, price: bars[3].c, f: { ...e.f, knownAt: bars[3].ts + MIN } };
  L.push(bars[3], e2, [1, 3]);
  assert.deepEqual(L.push(bars[4]).map((l) => [l.entry.decisionId, l.horizonMin]), [['test', 4], ['test', 4], ['second', 1], ['second', 1]]);
  assert.deepEqual(L.finish().map((l) => l.horizonMin), [3, 3]);
  assert.deepEqual(referenceWindows(start + 60 * MIN).map((w) => w.remainingMinutes), [15, 60]);
  assert.throws(() => referenceWindows(start + 1), /clock/);
});

test('transactional JSONL export binds streams and hashes, refuses overwrite and removes partial results on error', async () => {
  const root = archive(candles(25)), parent = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-export-'));
  try {
    const options = { archiveDir: root, assets: ['BTC'], referencePeriodsMin: [], path: { horizonsMin: [1, 3] } };
    const out = path.join(parent, 'good'), report = await exportDecisionDataset({ ...options, outDir: out });
    const decisionsRaw = fs.readFileSync(path.join(out, 'decisions.jsonl'), 'utf8'), pathsRaw = fs.readFileSync(path.join(out, 'paths.jsonl'), 'utf8');
    assert.equal(digest(decisionsRaw), report.outputs.decisions.sha256); assert.equal(digest(pathsRaw), report.outputs.paths.sha256);
    const decisions = decisionsRaw.trim().split('\n').map((s) => JSON.parse(s)), paths = pathsRaw.trim().split('\n').map((s) => JSON.parse(s));
    assert.equal(decisions[0].runId, paths[0].runId); assert.equal(paths[0].runId, report.runId);
    assert.equal(paths[0].labelsSchema, 'opportunity-decision-paths-v1');
    assert.ok(paths.slice(1).every((p) => p.schema === paths[0].labelsSchema));
    assert.equal(decisions.length - 1, report.outputs.decisions.rows); assert.equal(paths.length - 1, report.outputs.paths.rows);
    const ids = new Set(decisions.slice(1).map((d) => d.decisionId));
    assert.ok(paths.slice(1).every((p) => ids.has(p.entry.decisionId)));
    await assert.rejects(exportDecisionDataset({ ...options, outDir: out }), /already exists/);
    await assert.rejects(exportDecisionDataset({ ...options, outDir: path.join(parent, 'broken'), onDecision() { throw new Error('late callback failure'); } }), /callback failure/);
    assert.deepEqual(fs.readdirSync(parent), ['good']);
    const alias = path.join(parent, 'alias'); fs.symlinkSync(root, alias);
    await assert.rejects(exportDecisionDataset({ ...options, outDir: path.join(alias, 'nested-output') }), /outside/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); fs.rmSync(parent, { recursive: true, force: true }); }
});

test('explicit TV archive sources cannot bypass provider receipts by relabeling canonical CSVs', async () => {
  const root = archive(candles(25));
  try {
    fs.renameSync(path.join(root, 'history/binance-1m'), path.join(root, 'history/tvdatafeed-coinbase'));
    const audit = path.join(root, 'archive-validation.json');
    const manifest = JSON.parse(fs.readFileSync(audit, 'utf8'));
    manifest.files[0].path = 'tvdatafeed-coinbase/BTC/1m.csv'; manifest.files[0].source = 'tvdatafeed-coinbase';
    fs.writeFileSync(audit, JSON.stringify(manifest));
    await assert.rejects(buildDecisionDataset({ archiveDir: root, assets: ['BTC'], source: 'tvdatafeed-coinbase' }), /provenance|receipt/i);
    await assert.rejects(buildDecisionDataset({ archiveDir: root, assets: ['BTC'], source: '../tvdatafeed-coinbase' }), /invalid/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
