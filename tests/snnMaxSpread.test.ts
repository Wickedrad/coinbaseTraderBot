import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trainParams } from '../research/snnHistoryTrain';
import { versionHash } from '../bot/snn/params';

test('maxSpread: off by default (hash unchanged), set by the history trainer flag', () => {
  assert.equal(trainParams('S5').maxSpread, undefined);
  assert.equal(trainParams('S5', undefined, false, 0.1).maxSpread, 0.1);
  assert.equal(versionHash(trainParams('S5')), versionHash(trainParams('S5', undefined, false, undefined)));
});

test('SNN_MAX_SPREAD: off by default; when set it reaches the crypto network only (paper and live alike)', async () => {
  const { loadConfig, paperEnv } = await import('../bot/config');
  const { snnParams } = await import('../bot/snn/index');
  const off = loadConfig(paperEnv({} as NodeJS.ProcessEnv));
  assert.equal(off.snn.maxSpread, undefined);
  const on = loadConfig(paperEnv({ SNN_MAX_SPREAD: '0.1' } as NodeJS.ProcessEnv));
  assert.equal(on.snn.maxSpread, 0.1);
  assert.equal(snnParams(on.snn, 'crypto').maxSpread, 0.1);
  assert.equal(snnParams(on.snn, 'perps').maxSpread, undefined);
});
