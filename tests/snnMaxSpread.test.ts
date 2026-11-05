import { test } from 'node:test';
import assert from 'node:assert/strict';
import { trainParams } from '../research/snnHistoryTrain';
import { versionHash } from '../bot/snn/params';

test('maxSpread: off by default (hash unchanged), set by the history trainer flag', () => {
  assert.equal(trainParams('S5').maxSpread, undefined);
  assert.equal(trainParams('S5', undefined, false, 0.1).maxSpread, 0.1);
  assert.equal(versionHash(trainParams('S5')), versionHash(trainParams('S5', undefined, false, undefined)));
});
