/** All-minute, fixed-quarter importance iteration on the existing terminal-direction teacher. */
import fs from 'node:fs';
import path from 'node:path';
import { OpportunityLabeler, type MinuteCandle } from './atlas';
import { bars, fitEarlierBlock, verifiedInputs, type Block } from './oracleBlocksCli';
import { ORACLE_EMBARGO_MS, ORACLE_HORIZONS, ORACLE_LAYOUT_ID, ORACLE_SCHEMA, OracleFeatures, OracleMatrix,
  oracleAnswer, oracleCoordinates, oracleEntry, oracleQuarter, type OracleAnswer, type OracleEntry } from './oracleMatrix';
import { IMPORTANCE_EXPERTS, IMPORTANCE_POLICY, OracleImportance, importanceMixture, oracleComponents } from './oracleImportance';
import { digest } from './contractDataset';
import { atomicDirectory, codeHashes, unchanged } from './productCli';
import { sha256File } from './jointPathData';
import { ORACLE_BLOCK_STUDY_ID, studyPolicy } from './studyPolicy';

interface Pending extends OracleEntry { importance?: Record<number, { components: Float64Array; uniform: number[]; weighted: number[]; modelThrough: number; weightsThrough: number }> }
interface Score { rows: number; correct: number; loss: number; priorLoss: number; brier: number; directionalAbove60: number; directionalAbove60Correct: number }
const fresh = (): Score => ({ rows: 0, correct: 0, loss: 0, priorLoss: 0, brier: 0, directionalAbove60: 0, directionalAbove60Correct: 0 });
function add(s: Score, y: OracleAnswer, p: number[], prior: Float64Array) {
  const chosen = p.indexOf(Math.max(...p)), correct = Number(chosen === y.category);
  s.rows++; s.correct += correct; s.loss -= Math.log(Math.max(1e-12, p[y.category])); s.priorLoss -= Math.log(Math.max(1e-12, prior[y.category]));
  s.brier += p.reduce((n, v, i) => n + (v - Number(y.category === i)) ** 2, 0);
  if (chosen !== 1 && p[chosen] >= 0.6) { s.directionalAbove60++; s.directionalAbove60Correct += correct; }
}
const result = (s: Score) => ({ ...s, accuracy: s.rows ? s.correct / s.rows : null, logLoss: s.rows ? s.loss / s.rows : null,
  priorLogLoss: s.rows ? s.priorLoss / s.rows : null, gain: s.rows ? (s.priorLoss - s.loss) / s.rows : null,
  meanBrier: s.rows ? s.brier / s.rows : null, directionalAbove60Accuracy: s.directionalAbove60 ? s.directionalAbove60Correct / s.directionalAbove60 : null });
const inputsIdentity = (inputs: Record<string, string>) => digest(Object.entries(inputs).map(([f, h]) => [f.includes('/history/') ? f.split('/history/').at(-1)! : path.basename(f), h]).sort(([a], [b]) => a.localeCompare(b)));
export async function runOracleImportance(o: { archive: string; asset: string; oracle: string; out: string; minimumTrainingDays?: number }) {
  const verified = await verifiedInputs(o.archive, o.asset), code = await codeHashes(), root = fs.realpathSync(o.oracle);
  const reportFile = path.join(root, 'report.json'), reportSha256 = await sha256File(reportFile), original = JSON.parse(fs.readFileSync(reportFile, 'utf8'));
  const policy = studyPolicy(ORACLE_BLOCK_STUDY_ID), minimumDays = o.minimumTrainingDays ?? 365;
  if (original.schema !== ORACLE_SCHEMA || original.layoutId !== ORACLE_LAYOUT_ID || original.asset !== o.asset ||
      inputsIdentity(original.inputs) !== inputsIdentity(verified.inputs) || !Number.isInteger(minimumDays) || minimumDays < 1 || minimumDays > 3650) throw new Error('importance source registration/input differs');
  const blocks: Block[] = [];
  for (const b of original.blocks) {
    if (!/^\d{4}-Q[1-4]$/.test(b.quarter.id)) throw new Error('invalid importance source quarter');
    const file = path.join(root, b.quarter.id, 'manifest.json');
    if (await sha256File(file) !== original.blockManifestHashes[b.quarter.id]) throw new Error('changed source quarter');
    blocks.push(JSON.parse(fs.readFileSync(file, 'utf8')));
  }
  if (!blocks.length || blocks.some((b, i) => b.asset !== o.asset || (i && b.quarter.from <= blocks[i - 1].quarter.from))) throw new Error('importance source order differs');
  return atomicDirectory(o.out, async (dir) => {
    const registration = { schema: 'opportunity-oracle-importance-v1', asset: o.asset, layoutId: ORACLE_LAYOUT_ID, policy: IMPORTANCE_POLICY,
      originalOracleReportSha256: reportSha256, studyPolicy: policy, minimumDays, experts: IMPORTANCE_EXPERTS,
      target: 'Original terminal close up/sideways/down with ATR-scaled neutral band; not the new sustained-move target',
      design: 'Same earlier-quarter empirical curves; compare uniform averaging against weights learned from complete earlier-quarter predictions',
      declaredBeforeReadingLabels: true, researchOnly: true, liveEntryAllowed: false, autoPromote: false, inputs: verified.inputs, codeHashes: code };
    fs.writeFileSync(path.join(dir, 'registration.json'), JSON.stringify(registration, null, 2) + '\n');
    const matrix = new OracleMatrix(), features = new OracleFeatures(), labeler = new OpportunityLabeler(ORACLE_HORIZONS);
    const importance = { 15: new OracleImportance(), 60: new OracleImportance() }, uniform = IMPORTANCE_EXPERTS.map(() => 0);
    const scores = new Map<string, Record<number, { uniform: Score; weighted: Score }>>(), checkpoints: Record<string, unknown>[] = [];
    let q: ReturnType<typeof oracleQuarter> | undefined, nextBlock = 0, observedMinutes = 0, crossingLabelsNotScored = 0;
    let deferred: Block['boundaryTail'] = [];
    for await (const b of bars(verified.spot)) {
      const at = b.ts + 60000; if (at >= policy.finalFrom) break;
      const current = oracleQuarter(at);
      if (q?.id !== current.id) {
        if (q) for (const h of ORACLE_HORIZONS) importance[h].closeQuarter(current.from);
        const waiting: Block['boundaryTail'] = [];
        for (const e of deferred) {
          if (e.answer.knownAt + ORACLE_EMBARGO_MS <= current.from) matrix.add(e.answer, oracleCoordinates(e.raw.map((x) => x ?? NaN)));
          else waiting.push(e);
        } deferred = waiting;
        while (nextBlock < blocks.length && blocks[nextBlock].quarter.through <= current.from) {
          const block = blocks[nextBlock++]; matrix.merge(await fitEarlierBlock(root, block, current.from));
          deferred.push(...block.boundaryTail.filter((e) => e.answer.knownAt < policy.trainBefore && e.answer.knownAt + ORACLE_EMBARGO_MS > current.from));
        }
        q = current; scores.set(q.id, { 15: { uniform: fresh(), weighted: fresh() }, 60: { uniform: fresh(), weighted: fresh() } });
        checkpoints.push({ quarter: q.id, matrixTrainedThrough: matrix.trainedThrough, priorBlocks: nextBlock,
          horizons: ORACLE_HORIZONS.map((h) => ({ horizon: h, importanceTrainedThrough: importance[h].weightsTrainedThrough,
            logWeights: [...importance[h].logWeights], importanceSha256: digest(importance[h].logWeights) })) });
        console.log(`${o.asset} importance ${q.id}: frozen ${nextBlock} earlier quarters`);
      }
      observedMinutes++;
      const f = features.push(b, verified.dominance.map((d) => d.changeAt(at - 86400000)) as [number, number]), entry = oracleEntry(o.asset, b, f) as Pending | undefined;
      if (entry && current.from - blocks[0].firstAsOf >= minimumDays * 86400000 && matrix.rows(15) > 100) entry.importance = Object.fromEntries(ORACLE_HORIZONS.map((h) => {
        const components = oracleComponents(matrix, h, entry.coordinates, at);
        return [h, { components, uniform: importanceMixture(components, uniform), weighted: importanceMixture(components, importance[h].logWeights),
          modelThrough: matrix.trainedThrough, weightsThrough: importance[h].weightsTrainedThrough }];
      }));
      for (const outcome of labeler.push(b, entry)) {
        const y = oracleAnswer(outcome), e = outcome.entry as Pending, p = e.importance?.[y.horizon]; if (!p) continue;
        if (oracleQuarter(y.at).id !== current.id) { crossingLabelsNotScored++; continue; }
        if (Math.max(p.modelThrough, p.weightsThrough) + ORACLE_EMBARGO_MS > y.at) throw new Error('future importance or matrix');
        const s = scores.get(current.id)![y.horizon]; add(s.uniform, y, p.uniform, p.components); add(s.weighted, y, p.weighted, p.components);
        if (y.knownAt + ORACLE_EMBARGO_MS <= current.through) importance[y.horizon].observe(p.components, y.category, y.knownAt);
      }
    }
    if (q) for (const h of ORACLE_HORIZONS) importance[h].closeQuarter(q.through);
    const quarterReports = [...scores].map(([quarter, hs]) => ({ quarter, horizons: ORACLE_HORIZONS.map((h) => ({ horizon: h, uniform: result(hs[h].uniform), weighted: result(hs[h].weighted) })) }));
    const pooled = ORACLE_HORIZONS.map((h) => {
      const u = fresh(), w = fresh(); for (const hs of scores.values()) for (const k of Object.keys(u) as Array<keyof Score>) { u[k] += hs[h].uniform[k]; w[k] += hs[h].weighted[k]; }
      return { horizon: h, uniform: result(u), weighted: result(w), weightedGainOverUniform: u.rows ? (u.loss - w.loss) / u.rows : null };
    });
    const finalWeights = ORACLE_HORIZONS.map((h) => {
      const total = importance[h].logWeights.reduce((n, w) => n + Math.exp(w), 0);
      return { horizon: h, importanceTrainedThrough: importance[h].trainedThrough, curves: IMPORTANCE_EXPERTS.map((name, i) => ({ name,
        logWeight: importance[h].logWeights[i], fullVocabularyImportance: Math.exp(importance[h].logWeights[i]) / total })) };
    });
    const weights = { ...registration, checkpoints, finalWeights, originalModelIdentity: JSON.parse(fs.readFileSync(path.join(root, '../walk/model.json'), 'utf8')).id };
    fs.writeFileSync(path.join(dir, 'importance.json'), JSON.stringify({ ...weights, id: digest(weights) }) + '\n');
    const report = { ...registration, observedMinutes, crossingLabelsNotScored, quarters: quarterReports, pooled,
      finalWeights: finalWeights.map((h) => ({ horizon: h.horizon, importanceTrainedThrough: h.importanceTrainedThrough,
        changedCurves: h.curves.filter((c) => Math.abs(c.logWeight) > 1e-12).length,
        top: [...h.curves].sort((a, b) => b.fullVocabularyImportance - a.fullVocabularyImportance).slice(0, 12) })),
      relationshipCountUnchanged: 406, learnedImportance: true, freshFinalUsed: false, executableContractProfitVerified: false };
    await unchanged(verified.inputs, code); fs.writeFileSync(path.join(dir, 'report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
  });
}
const arg = (name: string) => process.argv[process.argv.indexOf(`--${name}`) + 1];
if (process.argv[1] && /(^|[/\\])oracleImportanceCli\.(ts|js)$/.test(process.argv[1])) void runOracleImportance({
  archive: arg('archive'), asset: arg('asset'), oracle: arg('oracle'), out: arg('out') })
  .then((r) => console.log(JSON.stringify(r.pooled))).catch((e) => { console.error(e instanceof Error ? e.stack : e); process.exitCode = 1; });
