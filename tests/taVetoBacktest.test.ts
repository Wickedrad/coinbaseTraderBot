import assert from 'node:assert/strict';
import path from 'path';
import { test } from 'node:test';
import { loadConfig } from '../bot/config';
import { MetaModel } from '../bot/model/metaModel';
import { runBacktest } from '../research/backtest';
import { writeSyntheticRecordings } from '../research/synthetic';
import { tmpDir } from './helpers';

// The veto lives in bot/engine.ts; the backtester must apply it too, or replays of TA_VETO_* settings equal the baseline.
test('backtester applies the TA veto as the engine does', async () => {
  const dir = path.join(tmpDir(), 'rec');
  writeSyntheticRecordings(dir, { windows: 8, seed: 9, marketNoise: 0.05 });
  const env = { DASHBOARD_TOKEN: 'x'.repeat(32), STRATEGY_STYLE: 'both', STRATEGY_CADENCE: 'continuous', PROFIT_MANDATE: 'false', PACER: 'false' };
  const base = loadConfig(env);
  const veto = loadConfig({ ...env, TA_VETO_RANDOM: '1' });
  const a = await runBacktest(dir, MetaModel.identity(), base.strategy, base.risk, 200);
  const b = await runBacktest(dir, MetaModel.identity(), veto.strategy, veto.risk, 200);
  const skips = Object.entries(b.funnel ?? {}).filter(([k]) => k.endsWith('TA veto skips')).reduce((s, [, v]) => s + v, 0);
  assert.ok(skips > 0, 'the veto fired');
  assert.ok(!Object.keys(a.funnel ?? {}).some((k) => k.endsWith('TA veto skips')), 'off by default');
  assert.notDeepEqual([b.fills, b.contracts, b.pnl], [a.fills, a.contracts, a.pnl]);
});
