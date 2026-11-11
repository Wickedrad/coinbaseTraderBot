// The settlement index's volatility estimate carried over a restart (E06, bot/marketdata/volState.ts): a fresh tracker
// continues a recent saved estimate instead of warming up for 120 one-second returns; an old one, or a tracker that already
// has returns of its own, is left alone.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';
import { IndexTracker } from '../bot/marketdata/indexTracker';
import { loadVolState, saveVolState, VOL_STATE_FILE, VOL_STATE_MAX_AGE_MS } from '../bot/marketdata/volState';
import { tmpDir } from './helpers';

/** `seconds` of one-second prints ending at `end`, a small random walk. */
function fed(seconds: number, end: number, asset = 'BTC'): IndexTracker {
  const t = new IndexTracker(asset);
  let seed = 7, x = Math.log(60000);
  for (let s = seconds; s >= 0; s--) {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    x += 0.0002 * (seed / 4294967296 - 0.5);
    t.add(Math.exp(x), end - s * 1000);
  }
  return t;
}

test('index volatility over a restart: a recent saved estimate is continued at once, an old one warms up again', () => {
  const now = Date.UTC(2026, 10, 11, 15, 0); // Nov 11 10:00 AM EST (15:00 UTC)
  const file = path.join(tmpDir(), VOL_STATE_FILE);
  const before = fed(600, now);
  const sigma = before.vol()!.sigmaPerSqrtSec;
  assert.ok(sigma > 0);
  saveVolState(file, new Map([['BTC', before], ['ETH', new IndexTracker('ETH')]]), now);
  assert.deepEqual(Object.keys(JSON.parse(fs.readFileSync(file, 'utf8')).assets), ['BTC'], 'a tracker with no estimate is not written');

  // Restarted 90 s later: the new tracker has no print yet and would need 120 returns; it continues the saved estimate.
  const after = new IndexTracker('BTC');
  assert.equal(after.vol(), undefined);
  assert.deepEqual(loadVolState(file, new Map([['BTC', after]]), now + 90_000), ['BTC']);
  assert.equal(after.vol()!.sigmaPerSqrtSec, sigma);
  // The return chain starts again at the next print: the estimate keeps updating from there.
  after.add(60000, now + 91_000);
  after.add(60060, now + 92_000);
  assert.ok(after.vol()!.sigmaPerSqrtSec > sigma, 'a 0.1% return moves it');

  // Down longer than two half-lives: warm up again.
  const late = new IndexTracker('BTC');
  assert.deepEqual(loadVolState(file, new Map([['BTC', late]]), now + VOL_STATE_MAX_AGE_MS + 1_000), []);
  assert.equal(late.vol(), undefined);
  // A tracker with returns of its own keeps them.
  const own = fed(30, now + 60_000);
  assert.deepEqual(loadVolState(file, new Map([['BTC', own]]), now + 60_000), []);
  assert.equal(own.vol(), undefined, '30 returns: still warming up on its own data');
  // Nothing to save (a fresh start before any return): the good file is kept.
  saveVolState(file, new Map([['BTC', new IndexTracker('BTC')]]), now + 120_000);
  assert.equal(JSON.parse(fs.readFileSync(file, 'utf8')).savedAt, now);
  // A restored estimate saved again keeps the time of its last return, so a feed that never comes back cannot keep it alive.
  const idle = new IndexTracker('BTC');
  loadVolState(file, new Map([['BTC', idle]]), now + 60_000);
  saveVolState(file, new Map([['BTC', idle]]), now + 9 * 60_000);
  assert.deepEqual(loadVolState(file, new Map([['BTC', new IndexTracker('BTC')]]), now + VOL_STATE_MAX_AGE_MS + 1_000), []);
});
