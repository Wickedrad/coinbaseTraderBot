// python/lossreview (the loss-review trip builder, research only): its fee port must equal bot/fees.ts, its unit tests must
// pass, and it must read an audit log as the bot's own AuditLog writes it. Skipped without a python3.
import assert from 'node:assert/strict';
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { test } from 'node:test';
import { AuditLog } from '../bot/audit/auditLog';
import { takerFee } from '../bot/fees';
import { tmpDir } from './helpers';

const python = ['python3', 'python'].find((p) => spawnSync(p, ['-c', 'import json'], { encoding: 'utf8' }).status === 0);
const env = { ...process.env, PYTHONPATH: 'python' };

test('loss review: the Python taker fee equals bot/fees.ts on a grid of counts and prices', { skip: !python && 'no python' }, () => {
  const counts = [1, 2, 3, 7, 10, 13, 20, 33, 58, 64, 100, 250];
  const prices = Array.from({ length: 99 }, (_, i) => (i + 1) / 100);
  const r = spawnSync(python!, ['-I', '-c', `import json,sys; sys.path.insert(0,'python'); from lossreview.fees import taker_fee
print(json.dumps([[c, p, taker_fee(c, p)] for c in ${JSON.stringify(counts)} for p in ${JSON.stringify(prices)}]))`], { encoding: 'utf8', env });
  assert.equal(r.status, 0, r.stderr);
  const got = JSON.parse(r.stdout) as Array<[number, number, number]>;
  assert.equal(got.length, counts.length * prices.length);
  for (const [c, p, fee] of got) assert.ok(Math.abs(fee - takerFee(c, p)) < 1e-9, `fee ${c} @ ${p}: python ${fee}, bot ${takerFee(c, p)}`);
});

test('loss review: unit tests of the package pass', { skip: !python && 'no python' }, () => {
  const r = spawnSync(python!, ['-m', 'unittest', 'discover', '-s', 'python/lossreview/tests', '-t', 'python', '-q'], { encoding: 'utf8', env });
  assert.equal(r.status, 0, r.stderr.slice(-2000));
});

test('loss review: a trip is rebuilt from the audit log the bot writes (call, fills, plan sale, close)', { skip: !python && 'no python' }, () => {
  const dir = tmpDir();
  const base = Date.UTC(2026, 10, 12, 15, 5, 0);   // 10:05 EST: ten minutes before the window closes
  let t = base;
  const audit = new AuditLog(path.join(dir, 'audit'), 500, () => t);
  const at = (sec: number) => { t = base + sec * 1000; };
  const TK = 'KXBTC15M-26NOV121015-15';
  const fill = (book: 'bid' | 'ask', price: number, count: number, coid: string, fee: number) =>
    audit.write('fill', { fill: { ticker: TK, side: book, count, price, isTaker: true, ts: t }, fee, feeEstimated: false, clientOrderId: coid, orphan: false, position: count });
  at(0);
  audit.write('heat', { asset: 'BTC', h: 15, key: '1m:X=high | 15m:Y=low', kind: 'pair', dir: 1, rank: 8, of: 40, heat: 98.7, barClose: base - 31_000, fired: 3, against: 0, context: 'agree',
    plan: { ticker: TK, side: 'yes', price: 0.5, count: 20, stakeUsd: 10, weight: 0.47, slot: 1 }, entry: 'sent' });
  at(1);
  fill('bid', 0.5, 20, 'c1', 0.18);
  at(300);
  audit.write('plan', { event: 'plan_ratchet_sell', ticker: TK, side: 'yes', ruleId: 'r', count: 20, bid: 0.62, net: 1.0, limit: 0.62, sent: true });
  at(301);
  fill('ask', 0.62, 20, 'c2', 0.17);
  at(310);
  audit.write('heat', { event: 'closed', ticker: TK, asset: 'BTC', kind: '15m', side: 'yes', ruleId: 'r', h: 15, pnl: 2.05, settled: false, stakeUsd: 10, trips: 5, wins: 2, bookPnl: -3 });
  const r = spawnSync(python!, ['-B', '-m', 'lossreview.nightly', '--day', '2026-11-12', '--audit-dir', path.join(dir, 'audit'), '--out', path.join(dir, 'out'), '--no-net'], { encoding: 'utf8', env });
  assert.equal(r.status, 0, r.stderr.slice(-2000));
  const m = r.stdout.match(/^LOSSREVIEW (\{.*\})$/m);
  assert.ok(m, r.stdout);
  const s = JSON.parse(m![1]);
  assert.equal(s.trips, 1);
  assert.equal(s.defect_sales, 0);
  assert.equal(s.fidelity_flagged, 0);
  // one trip is a cell under five: the job log prints no dollar figure for it; the private aggregate file has them
  assert.equal(s.net, undefined, 'a cell of one trip prints no dollars');
  const agg = JSON.parse(fs.readFileSync(path.join(dir, 'out', 'agg-2026-11-12.json'), 'utf8'));
  assert.ok(Math.abs(agg.net - 2.05) < 1e-9, `net ${agg.net}`);
  assert.ok(Math.abs(agg.fees - 0.35) < 1e-9, `fees ${agg.fees}`);   // the fills' own fees, not an estimate
  assert.ok(!/KXBTC/.test(r.stdout), 'the job log prints no ticker');
});
