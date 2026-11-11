/** Compact cross-asset evidence. Assets in the same quarter are one time block. */
import fs from 'node:fs';
import path from 'node:path';
import { bootstrapMeanCi } from '../stats';
import { ORACLE_AXES, ORACLE_SCHEMA, ORACLE_SURFACES } from './oracleMatrix';

export function summarizeOracle(root: string) {
  const assets = [], quarterly = new Map<string, { rows: number; gain: number }>();
  for (const asset of ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']) {
    const dir = path.join(root, `atlas-oracle-result-${asset}`), oracleFile = path.join(dir, 'oracle/report.json'), walkFile = path.join(dir, 'walk/report.json');
    if (!fs.existsSync(oracleFile) || !fs.existsSync(walkFile)) throw new Error(`Incomplete Oracle/walk artifacts for ${asset}`);
    const oracle = JSON.parse(fs.readFileSync(oracleFile, 'utf8')), walk = JSON.parse(fs.readFileSync(walkFile, 'utf8'));
    if (oracle.schema !== ORACLE_SCHEMA || walk.schema !== ORACLE_SCHEMA || walk.asset !== asset || walk.finalHoldoutUsed !== false || walk.contractProfitVerified !== false || walk.nativeSnnTrained !== false) throw new Error('Oracle summary source/claim differs');
    const targets = [15, 60].map((horizon) => {
      const rows = walk.folds.map((f: { quarter: string; targets: Record<number, { rows: number; loss: number; baselineLoss: number; correct: number; highConfidence: number; highConfidenceCorrect: number }> }) => ({ quarter: f.quarter, ...f.targets[horizon] }));
      const totals = rows.reduce((s: { rows: number; loss: number; baselineLoss: number; correct: number; highConfidence: number; highConfidenceCorrect: number }, r: typeof rows[number]) => ({ rows: s.rows + r.rows, loss: s.loss + r.loss,
        baselineLoss: s.baselineLoss + r.baselineLoss, correct: s.correct + r.correct, highConfidence: s.highConfidence + r.highConfidence, highConfidenceCorrect: s.highConfidenceCorrect + r.highConfidenceCorrect }),
      { rows: 0, loss: 0, baselineLoss: 0, correct: 0, highConfidence: 0, highConfidenceCorrect: 0 });
      for (const r of rows) if (r.rows) {
        const key = `${horizon}:${r.quarter}`, old = quarterly.get(key) ?? { rows: 0, gain: 0 };
        old.rows += r.rows; old.gain += r.baselineLoss - r.loss; quarterly.set(key, old);
      }
      return { horizonMinutes: horizon, rows: totals.rows, accuracy: totals.rows ? totals.correct / totals.rows : null,
        meanLogLoss: totals.rows ? totals.loss / totals.rows : null, baselineMeanLogLoss: totals.rows ? totals.baselineLoss / totals.rows : null,
        predictiveGain: totals.rows ? (totals.baselineLoss - totals.loss) / totals.rows : null,
        highConfidence: totals.highConfidence, highConfidenceAccuracy: totals.highConfidence ? totals.highConfidenceCorrect / totals.highConfidence : null };
    });
    assets.push({ asset, observedMinutes: oracle.observedMinutes, quarters: oracle.blocks.length, answers: oracle.completedAnswers, gaps: oracle.gaps,
      targets, model: path.join(`atlas-oracle-result-${asset}`, 'walk/model.json'), spectra: path.join(`atlas-oracle-result-${asset}`, 'walk/relationship-spectra.csv.gz') });
  }
  const evidence = [15, 60].map((h) => {
    const blocks = [...quarterly].filter(([k]) => k.startsWith(`${h}:`)).map(([key, v]) => ({ quarter: key.split(':')[1], gain: v.gain / v.rows, rows: v.rows }));
    return { horizonMinutes: h, blocks, exploratoryMeanQuarterGain: blocks.length >= 8 ? bootstrapMeanCi(blocks.map((b) => b.gain), 0.05, 2000, 17) : null,
      interpretation: 'Same-quarter assets pooled; quarter bootstrap is exploratory and assumes reasonably independent stable time blocks. Reused history remains development evidence.' };
  });
  return { schema: ORACLE_SCHEMA, assets, features: ORACLE_AXES.length, singleAndPairRelationships: ORACLE_SURFACES.length,
    observedMinutes: assets.reduce((s, a) => s + a.observedMinutes, 0), evidence, researchOnly: true, liveEntryAllowed: false,
    contractProfitVerified: false, nativeSnnTrained: false, freshFinalUsed: false };
}
if (process.argv[1] && /(^|[/\\])oracleSummary\.(ts|js)$/.test(process.argv[1])) {
  const result = summarizeOracle(process.argv[2]); fs.writeFileSync(process.argv[3], JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ observedMinutes: result.observedMinutes, features: result.features, relationships: result.singleAndPairRelationships,
    assets: result.assets.map((a) => ({ asset: a.asset, quarters: a.quarters, answers: a.answers, targets: a.targets })), evidence: result.evidence }, null, 2));
}
