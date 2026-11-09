/** All-minute, bounded-memory Oracle first, then a separate causal walk-forward pass. */
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { gzipSync, gunzipSync, createGzip } from 'node:zlib';
import { once } from 'node:events';
import { finished } from 'node:stream/promises';
import { endianness } from 'node:os';
import { OpportunityLabeler, type MinuteCandle } from './atlas';
import { parseMinuteCsv } from './minuteCsv';
import { CompletedDailyIndex } from './train';
import { atomicDirectory, codeHashes, unchanged } from './productCli';
import { sha256File } from './jointPathData';
import { ORACLE_BLOCK_STUDY_ID, studyPolicy } from './studyPolicy';
import { digest } from './contractDataset';
import { ORACLE_AXES, ORACLE_EMBARGO_MS, ORACLE_HORIZONS, ORACLE_HORIZON_SIZE, ORACLE_KNOTS, ORACLE_LAYOUT_ID,
  ORACLE_SCHEMA, ORACLE_STATS, ORACLE_SURFACES, OracleFeatures, OracleMatrix, oracleAnswer, oracleCoordinates, oracleEntry,
  oracleQuarter, oracleRawCoordinate, type OracleAnswer, type OracleEntry, type OraclePrediction } from './oracleMatrix';

const MIN = 60000, DAY = 86400000;
const SOURCE = 'archive-binance-1m-quarantined-v1';
const logicalInputs = (inputs: Record<string, string>) => Object.fromEntries(Object.entries(inputs).map(([file, sha]) => [file.includes('/history/') ? file.split('/history/').at(-1)! : path.basename(file), sha]).sort(([a], [b]) => a.localeCompare(b)));
interface Tail { answer: OracleAnswer; raw: Array<number | null> }
interface Block {
  schema: typeof ORACLE_SCHEMA; layoutId: string; asset: string; quarter: ReturnType<typeof oracleQuarter>;
  observedMinutes: number; firstAsOf: number; lastAsOf: number; knownThrough: number; fitKnownThrough: number;
  boundaryTail: Tail[]; answers: Record<number, number>; featureRanges: Array<{ name: string; minimum: number | null; maximum: number | null; available: number }>;
  matrix: { file: string; sha256: string; encoding: 'float64-le-gzip' };
}
async function* bars(file: string) {
  const input = fs.createReadStream(file), reader = readline.createInterface({ input, crlfDelay: Infinity }); let previous = -1;
  try { for await (const line of reader) {
    if (line === 'ts,o,h,l,c,v' || line === 'ts,o,h,l,c,v,tb') continue;
    const b = parseMinuteCsv(line);
    if (!b || b.ts <= previous) throw new Error('invalid or unordered audited Oracle candles'); previous = b.ts; yield b;
  } } finally { reader.close(); input.destroy(); }
}
async function verifiedInputs(archive: string, asset: string) {
  const root = fs.realpathSync(archive), history = fs.realpathSync(path.join(root, 'history'));
  const auditFile = path.join(root, 'archive-validation.json'), auditHash = await sha256File(auditFile);
  const audit = JSON.parse(fs.readFileSync(auditFile, 'utf8'));
  if (audit.schema !== 'atlas-archive-audit-v1' || !['BTC', 'ETH', 'SOL', 'XRP', 'DOGE'].includes(asset)) throw new Error('audited asset/archive required');
  const inputs: Record<string, string> = { [auditFile]: auditHash };
  async function verify(relative: string, required: boolean) {
    const r = audit.files.find((f: { path: string }) => f.path === relative);
    if (!r) { if (required) throw new Error('missing audited Oracle input'); return; }
    const file = fs.realpathSync(path.join(history, relative));
    if (!file.startsWith(history + path.sep) || !r.ready || !/^[a-f0-9]{64}$/.test(r.sha256) || await sha256File(file) !== r.sha256) throw new Error('Oracle input path/hash differs');
    inputs[file] = r.sha256; return file;
  }
  const spot = (await verify(`${SOURCE}/${asset}/1m.csv`, true))!;
  const dominance: CompletedDailyIndex[] = [];
  for (const symbol of ['BTC.D', 'USDT.D']) {
    const file = await verify(`tradingview/${symbol}/1d.csv`, false), rows: MinuteCandle[] = [];
    if (file) for await (const b of bars(file)) rows.push(b);
    dominance.push(new CompletedDailyIndex(rows));
  }
  return { inputs, spot, dominance };
}
function matrixBytes(m: OracleMatrix) {
  if (endianness() !== 'LE') throw new Error('Oracle matrix encoding requires a little-endian runner');
  return gzipSync(Buffer.from(m.data.buffer), { level: 1 });
}
async function readBlock(root: string, block: Block) {
  const file = path.join(root, block.quarter.id, block.matrix.file);
  if (block.schema !== ORACLE_SCHEMA || block.layoutId !== ORACLE_LAYOUT_ID || block.matrix.file !== 'matrix.f64.gz' || await sha256File(file) !== block.matrix.sha256) throw new Error('Oracle block receipt differs');
  const data = new Float64Array(ORACLE_HORIZON_SIZE * 2), raw = gunzipSync(fs.readFileSync(file), { maxOutputLength: data.byteLength });
  if (raw.length !== data.byteLength) throw new Error('Oracle matrix size differs'); Buffer.from(data.buffer).set(raw);
  const m = new OracleMatrix(data); m.trainedThrough = block.knownThrough;
  return m;
}
/** Oracle contains all descriptive answers; the causal learner removes the embargo tail. */
async function fitEarlierBlock(root: string, block: Block, before: number) {
  if (block.quarter.through > before || block.fitKnownThrough + ORACLE_EMBARGO_MS > before) throw new Error('walk-forward attempted a future Oracle block');
  const m = await readBlock(root, block);
  for (const e of block.boundaryTail) m.add(e.answer, oracleCoordinates(e.raw.map((v) => v ?? NaN)), -1);
  m.trainedThrough = block.fitKnownThrough; return m;
}
export async function buildFullOracle(o: { archive: string; asset: string; out: string; onProgress?: (s: string) => void }) {
  const policy = studyPolicy(ORACLE_BLOCK_STUDY_ID), verified = await verifiedInputs(o.archive, o.asset), code = await codeHashes();
  const root = path.resolve(o.out), features = new OracleFeatures(), labeler = new OpportunityLabeler(ORACLE_HORIZONS);
  const registration = { schema: ORACLE_SCHEMA, studyPolicy: policy, asset: o.asset, layoutId: ORACLE_LAYOUT_ID,
    axes: ORACLE_AXES, knots: ORACLE_KNOTS, relationships: ORACLE_SURFACES, stats: ORACLE_STATS, horizons: ORACLE_HORIZONS,
    sampling: 'every valid observed minute; no sparse observation thinning', blocks: 'UTC quarters; feature and pending-label state continues across boundaries',
    neutralDefinition: 'max(1bp, 0.25 * current completed 15m ATRbps * sqrt(horizon/15))',
    inference: 'fixed equal mixture of continuous empirical single/pair responses; 100-observation shrinkage to the historical class prior',
    declaredBeforeLabels: true, inputs: verified.inputs, codeHashes: code, researchOnly: true, liveEntryAllowed: false, autoPromote: false,
    unavailable: ['Native subsecond SNN states', 'funding/open interest', 'full TA-Lib vocabulary', 'contract bid/ask/depth/fills'],
    dataPolicy: 'Existing archive provider identity retained; no fresh acquisition, price filling, source splice or simulated second ticks',
    futureHoldout: 'November 9 onward excluded, including crossing labels', dailyLagMs: DAY, embargoMs: ORACLE_EMBARGO_MS,
    interpretation: 'Descriptive historical answers are not guaranteed future laws or executable contract profits' };
  await atomicDirectory(root, async (dir) => { fs.writeFileSync(path.join(dir, 'registration.json'), JSON.stringify(registration, null, 2) + '\n'); });
  const blocks: Block[] = []; let q: ReturnType<typeof oracleQuarter> | undefined, m = new OracleMatrix(), minutes = 0, total = 0;
  let firstAsOf = 0, lastAsOf = 0, fitKnownThrough = 0, tail: Tail[] = [];
  let ranges = ORACLE_AXES.map((a) => ({ name: a.name, minimum: Infinity, maximum: -Infinity, available: 0 }));
  async function flush() {
    if (!q || !minutes) return;
    const quarter = q;
    const block = await atomicDirectory(path.join(root, q.id), async (dir) => {
      const file = path.join(dir, 'matrix.f64.gz'); fs.writeFileSync(file, matrixBytes(m));
      const b: Block = { schema: ORACLE_SCHEMA, layoutId: ORACLE_LAYOUT_ID, asset: o.asset, quarter, observedMinutes: minutes,
        firstAsOf, lastAsOf, knownThrough: m.trainedThrough, fitKnownThrough, boundaryTail: tail,
        answers: Object.fromEntries(ORACLE_HORIZONS.map((h) => [h, m.rows(h)])),
        featureRanges: ranges.map((r) => ({ ...r, minimum: r.available ? r.minimum : null, maximum: r.available ? r.maximum : null })),
        matrix: { file: 'matrix.f64.gz', sha256: await sha256File(file), encoding: 'float64-le-gzip' } };
      fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify(b) + '\n');
      fs.writeFileSync(path.join(dir, 'feature-checkpoint.json'), JSON.stringify(features.checkpoint()) + '\n');
      return b;
    });
    blocks.push(block); o.onProgress?.(`${o.asset} Oracle ${q.id}: ${minutes} minutes, ${m.rows(15)} / ${m.rows(60)} complete 15m / 60m answers`);
    m = new OracleMatrix(); minutes = 0; firstAsOf = lastAsOf = fitKnownThrough = 0; tail = [];
    ranges = ORACLE_AXES.map((a) => ({ name: a.name, minimum: Infinity, maximum: -Infinity, available: 0 }));
  }
  for await (const b of bars(verified.spot)) {
    const at = b.ts + MIN; if (at >= policy.finalFrom) break;
    const quarter = oracleQuarter(at);
    if (q && q.id !== quarter.id) await flush(); q = quarter; firstAsOf ||= at; lastAsOf = at; minutes++; total++;
    const f = features.push(b, verified.dominance.map((d) => d.changeAt(at - DAY)) as [number, number]);
    for (const [i, v] of f.raw.entries()) if (Number.isFinite(v)) { ranges[i].minimum = Math.min(ranges[i].minimum, v); ranges[i].maximum = Math.max(ranges[i].maximum, v); ranges[i].available++; }
    for (const outcome of labeler.push(b, oracleEntry(o.asset, b, f))) {
      const y = oracleAnswer(outcome), e = outcome.entry as OracleEntry;
      m.add(y, e.coordinates);
      if (y.knownAt + ORACLE_EMBARGO_MS <= quarter.through && y.knownAt < policy.trainBefore) fitKnownThrough = Math.max(fitKnownThrough, y.knownAt);
      else tail.push({ answer: y, raw: e.raw.map((v) => Number.isFinite(v) ? v : null) });
    }
  }
  await flush(); await unchanged(verified.inputs, code);
  const report = { ...registration, blocks: blocks.map(({ boundaryTail, ...b }) => ({ ...b, embargoedAnswers: boundaryTail.length })),
    observedMinutes: total, gaps: features.gaps, completedAnswers: Object.fromEntries(ORACLE_HORIZONS.map((h) => [h, blocks.reduce((n, b) => n + b.answers[h], 0)])),
    blockManifestHashes: Object.fromEntries(await Promise.all(blocks.map(async (b) => [b.quarter.id, await sha256File(path.join(root, b.quarter.id, 'manifest.json'))]))),
    oracleIsPredictor: false, pendingAtEndAreNotNegativeLabels: true };
  fs.writeFileSync(path.join(root, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
}
interface Score { rows: number; correct: number; loss: number; baselineLoss: number; brier: number; highConfidence: number; highConfidenceCorrect: number; confusion: number[][] }
const freshScore = (): Score => ({ rows: 0, correct: 0, loss: 0, baselineLoss: 0, brier: 0, highConfidence: 0, highConfidenceCorrect: 0, confusion: [[0, 0, 0], [0, 0, 0], [0, 0, 0]] });
function score(s: Score, y: OracleAnswer, p: OraclePrediction) {
  const chosen = p.p.indexOf(Math.max(...p.p)), correct = chosen === y.category;
  s.rows++; s.correct += Number(correct); s.loss -= Math.log(Math.max(1e-12, p.p[y.category])); s.baselineLoss -= Math.log(Math.max(1e-12, p.baseline[y.category]));
  s.brier += p.p.reduce((sum, v, i) => sum + (v - Number(i === y.category)) ** 2, 0); s.confusion[y.category][chosen]++;
  if (p.p[chosen] >= 0.6) { s.highConfidence++; s.highConfidenceCorrect += Number(correct); }
}
export async function walkFullOracle(o: { archive: string; asset: string; oracle: string; out: string; minimumTrainingDays?: number; onProgress?: (s: string) => void }) {
  const verified = await verifiedInputs(o.archive, o.asset), code = await codeHashes(), root = fs.realpathSync(o.oracle);
  const reportFile = path.join(root, 'report.json'), reportHash = await sha256File(reportFile), oracle = JSON.parse(fs.readFileSync(reportFile, 'utf8'));
  const policy = studyPolicy(ORACLE_BLOCK_STUDY_ID), minimumDays = o.minimumTrainingDays ?? 365;
  if (oracle.schema !== ORACLE_SCHEMA || oracle.layoutId !== ORACLE_LAYOUT_ID || oracle.asset !== o.asset || !Number.isSafeInteger(minimumDays) || minimumDays < 1 || minimumDays > 3650 ||
      digest(logicalInputs(oracle.inputs)) !== digest(logicalInputs(verified.inputs)) || JSON.stringify(oracle.codeHashes) !== JSON.stringify(code)) throw new Error('walk-forward Oracle/input/code registration differs');
  const blocks: Block[] = [];
  for (const r of oracle.blocks) {
    if (!/^\d{4}-Q[1-4]$/.test(r.quarter.id)) throw new Error('invalid Oracle quarter');
    const file = path.join(root, r.quarter.id, 'manifest.json');
    if (await sha256File(file) !== oracle.blockManifestHashes[r.quarter.id]) throw new Error('Oracle block changed');
    blocks.push(JSON.parse(fs.readFileSync(file, 'utf8')));
  }
  if (blocks.some((b, i) => b.asset !== o.asset || (i && b.quarter.from <= blocks[i - 1].quarter.from))) throw new Error('unordered Oracle blocks');
  return atomicDirectory(o.out, async (dir) => {
    fs.writeFileSync(path.join(dir, 'registration.json'), JSON.stringify({ schema: ORACLE_SCHEMA, asset: o.asset, oracleReportSha256: reportHash,
      minimumTrainingDays: minimumDays, predictionCutoff: 'Only complete prior-quarter tables with a one-hour label embargo; never the full-history matrix',
      historicalDevelopmentOnly: true, freshFinalUsed: false, researchOnly: true, liveEntryAllowed: false, inputs: verified.inputs, codeHashes: code }, null, 2) + '\n');
    const model = new OracleMatrix(), features = new OracleFeatures(), labeler = new OpportunityLabeler(ORACLE_HORIZONS);
    const scores = new Map<string, Record<number, Score>>(), snapshots: Array<Record<string, unknown>> = [];
    let q: ReturnType<typeof oracleQuarter> | undefined, nextBlock = 0, observedMinutes = 0, boundaryPurged = 0;
    for await (const b of bars(verified.spot)) {
      const at = b.ts + MIN; if (at >= policy.finalFrom) break;
      const current = oracleQuarter(at);
      if (q?.id !== current.id) {
        while (nextBlock < blocks.length && blocks[nextBlock].quarter.through <= current.from) {
          model.merge(await fitEarlierBlock(root, blocks[nextBlock++], current.from));
        }
        q = current; scores.set(q.id, { 15: freshScore(), 60: freshScore() });
        snapshots.push({ quarter: q.id, trainedThrough: model.trainedThrough, modelSha256: await hashMatrix(model), priorBlocks: nextBlock,
          rows15: model.rows(15), rows60: model.rows(60), embargoMs: ORACLE_EMBARGO_MS });
        o.onProgress?.(`${o.asset} forward ${q.id}: frozen ${nextBlock} earlier blocks; ${model.rows(15)} prior 15m answers`);
      }
      observedMinutes++;
      const f = features.push(b, verified.dominance.map((d) => d.changeAt(at - DAY)) as [number, number]);
      const entry = oracleEntry(o.asset, b, f);
      if (entry && blocks.length && current.from - blocks[0].firstAsOf >= minimumDays * DAY && model.rows(15) > 100) {
        entry.predictions = Object.fromEntries(ORACLE_HORIZONS.map((h) => [h, model.predict(h, entry.coordinates, at)]));
      }
      for (const outcome of labeler.push(b, entry)) {
        const e = outcome.entry as OracleEntry, p = e.predictions?.[outcome.horizonMin]; if (!p) continue;
        const y = oracleAnswer(outcome), decisionQuarter = oracleQuarter(y.at);
        if (decisionQuarter.id !== current.id) { boundaryPurged++; continue; }
        if (p.trainedThrough + ORACLE_EMBARGO_MS > y.at) throw new Error('walk-forward training lookahead');
        score(scores.get(decisionQuarter.id)![y.horizon], y, p);
      }
    }
    // Final fitted tables are a separate artifact, produced AFTER every fold forecast.
    for (const block of blocks.slice(nextBlock)) {
      const m = await readBlock(root, block);
      for (const e of block.boundaryTail) m.add(e.answer, oracleCoordinates(e.raw.map((v) => v ?? NaN)), -1);
      m.trainedThrough = block.fitKnownThrough; model.merge(m);
    }
    fs.writeFileSync(path.join(dir, 'full-history-model.f64.gz'), matrixBytes(model));
    const exported = { schema: ORACLE_SCHEMA, asset: o.asset, layoutId: ORACLE_LAYOUT_ID,
      trainedThrough: model.trainedThrough, file: 'full-history-model.f64.gz', sha256: await sha256File(path.join(dir, 'full-history-model.f64.gz')),
      axes: ORACLE_AXES, relationships: ORACLE_SURFACES, horizons: ORACLE_HORIZONS, source: SOURCE, researchOnly: true, liveEntryAllowed: false,
      notUsedForEarlierFoldForecasts: true, oracleReportSha256: reportHash, inputs: verified.inputs, codeHashes: code };
    fs.writeFileSync(path.join(dir, 'model.json'), JSON.stringify({ ...exported, id: digest(exported) }, null, 2) + '\n');
    await exportOracleSpectra(model, path.join(dir, 'relationship-spectra.csv.gz'));
    if (await sha256File(reportFile) !== reportHash) throw new Error('Oracle changed during walk'); await unchanged(verified.inputs, code);
    const result = { schema: ORACLE_SCHEMA, asset: o.asset, observedMinutes, boundaryPurged, oracleReportSha256: reportHash, frozenModels: snapshots,
      folds: [...scores].map(([quarter, targets]) => ({ quarter, targets: Object.fromEntries(Object.entries(targets).map(([h, s]) => [h, { ...s,
        accuracy: s.rows ? s.correct / s.rows : null, meanLogLoss: s.rows ? s.loss / s.rows : null, baselineMeanLogLoss: s.rows ? s.baselineLoss / s.rows : null,
        meanBrier: s.rows ? s.brier / s.rows : null, predictiveGain: s.rows ? (s.baselineLoss - s.loss) / s.rows : null }])) })),
      classes: ['up', 'sideways', 'down'], researchOnly: true, liveEntryAllowed: false, autoPromote: false, finalHoldoutUsed: false,
      contractProfitVerified: false, nativeSnnTrained: false, forwardPaperTrial: false,
      interpretation: 'Every-minute chronological development replay, unseen to each frozen fold model. Reused history is not a fresh prospective trial. Contract quotes/fills and native SNN inputs are unavailable in this minute archive.' };
    fs.writeFileSync(path.join(dir, 'report.json'), JSON.stringify(result, null, 2) + '\n'); return result;
  });
}
async function hashMatrix(m: OracleMatrix) {
  const { createHash } = await import('node:crypto'); return createHash('sha256').update(Buffer.from(m.data.buffer)).digest('hex');
}
export async function queryFullOracle(modelFile: string, request: { asset: string; source: string; asOf: number; featuresKnownAt: number; layoutId: string; horizon: 15 | 60; raw: number[] }) {
  const file = fs.realpathSync(modelFile), manifest = JSON.parse(fs.readFileSync(file, 'utf8'));
  const { id, ...identity } = manifest;
  if (digest(identity) !== id || manifest.schema !== ORACLE_SCHEMA || manifest.layoutId !== ORACLE_LAYOUT_ID || request.layoutId !== ORACLE_LAYOUT_ID ||
      request.asset !== manifest.asset || request.source !== manifest.source || manifest.researchOnly !== true || manifest.liveEntryAllowed !== false ||
      manifest.file !== 'full-history-model.f64.gz' || !Number.isSafeInteger(request.featuresKnownAt) || request.featuresKnownAt > request.asOf || request.featuresKnownAt < request.asOf - MIN ||
      !Number.isSafeInteger(manifest.trainedThrough) || manifest.trainedThrough >= studyPolicy(ORACLE_BLOCK_STUDY_ID).trainBefore) throw new Error('Oracle model/feature/source/clock differs');
  const data = new Float64Array(ORACLE_HORIZON_SIZE * 2), matrixFile = path.join(path.dirname(file), manifest.file);
  if (await sha256File(matrixFile) !== manifest.sha256) throw new Error('Oracle model hash differs');
  const bytes = gunzipSync(fs.readFileSync(matrixFile), { maxOutputLength: data.byteLength });
  if (bytes.length !== data.byteLength) throw new Error('Oracle model size differs'); Buffer.from(data.buffer).set(bytes);
  const m = new OracleMatrix(data); m.trainedThrough = manifest.trainedThrough;
  const p = m.predict(request.horizon, oracleCoordinates(request.raw), request.asOf);
  return { schema: ORACLE_SCHEMA, asset: request.asset, asOf: request.asOf, byAt: request.asOf + request.horizon * MIN,
    horizonMinutes: request.horizon, trainedThrough: p.trainedThrough, trainingRows: p.trainingRows,
    probabilities: { up: p.p[0], sideways: p.p[1], down: p.p[2] }, baseline: p.baseline,
    confidenceBasis: 'Interpolated historical class frequencies with fixed shrinkage; no independent probability-calibration claim',
    researchOnly: true, liveEntryAllowed: false, movementReliabilityQualified: false, contractProfitVerified: false };
}
export async function exportOracleSpectra(m: OracleMatrix, file: string) {
  const zip = createGzip({ level: 1 }), output = fs.createWriteStream(file, { flags: 'wx' }); zip.pipe(output);
  const completion = finished(output); let buffer = 'horizon_min,relationship,x_raw,y_raw,effective_weight,p_up,p_sideways,p_down,mean_return_bps,mean_max_up_bps,mean_max_down_bps\n';
  try {
    for (const [j, h] of ORACLE_HORIZONS.entries()) for (const s of ORACLE_SURFACES) for (let cell = 0; cell < s.cells; cell++) {
      const i = j * ORACLE_HORIZON_SIZE + s.offset + cell * ORACLE_STATS.length, n = m.data[i]; if (n < 1e-9) continue;
      const a = s.b === null ? cell : Math.floor(cell / ORACLE_KNOTS), b = s.b === null ? null : cell % ORACLE_KNOTS;
      const x = oracleRawCoordinate(a / (ORACLE_KNOTS - 1), ORACLE_AXES[s.a]), y = b === null ? '' : oracleRawCoordinate(b / (ORACLE_KNOTS - 1), ORACLE_AXES[s.b!]);
      buffer += [h, s.name, x, y, n, m.data[i + 1] / n, m.data[i + 2] / n, Math.max(0, n - m.data[i + 1] - m.data[i + 2]) / n,
        m.data[i + 3] / n, m.data[i + 5] / n, m.data[i + 6] / n].join(',') + '\n';
      if (buffer.length >= 1048576) { if (!zip.write(buffer)) await once(zip, 'drain'); buffer = ''; }
    }
    zip.end(buffer); await completion;
  } catch (e) { zip.destroy(); output.destroy(); await completion.catch(() => undefined); throw e; }
}
const arg = (name: string, fallback?: string) => { const i = process.argv.indexOf(`--${name}`), value = i < 0 ? fallback : process.argv[i + 1]; if (!value) throw new Error(`--${name} required`); return value; };
async function main() {
  if (process.argv[2] === 'query') {
    console.log(JSON.stringify(await queryFullOracle(arg('model'), JSON.parse(fs.readFileSync(arg('request'), 'utf8'))), null, 2)); return;
  }
  const o = { archive: arg('archive'), asset: arg('asset'), out: arg('out'), onProgress: console.log };
  if (process.argv[2] === 'oracle') await buildFullOracle(o);
  else if (process.argv[2] === 'walk') await walkFullOracle({ ...o, oracle: arg('oracle') });
  else throw new Error('Expected oracle, walk or query');
}
if (process.argv[1] && /(^|[/\\])oracleBlocksCli\.(ts|js)$/.test(process.argv[1])) void main().catch((e) => { console.error(e); process.exitCode = 1; });
