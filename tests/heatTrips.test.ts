// .github/scripts/heat_trips.py (Server diagnostics, on the server): heat round trips, plan sales and re-entries after a
// loss, read from an audit log written by the bot's own AuditLog and from the bot's "[heat] round trip closed" log lines.
// Skipped without a python3.
import assert from 'node:assert/strict';
import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { test } from 'node:test';
import { AuditLog } from '../bot/audit/auditLog';
import { tmpDir } from './helpers';

const python = ['python3', 'python'].find((p) => spawnSync(p, ['-c', 'import json'], { encoding: 'utf8' }).status === 0);
const SCRIPT = path.join('.github', 'scripts', 'heat_trips.py');

/** An audit log as the engine writes it (bot/engine.ts heatTick / auditPlan), over the last hours. */
function fixture(): { dir: string; journal: string } {
  const dir = tmpDir();
  const base = Date.now() - 3 * 3600_000;
  let t = base - 30 * 3600_000; // one record from before the window
  const audit = new AuditLog(path.join(dir, 'audit'), 500, () => t);
  const at = (min: number) => { t = base + min * 60_000; };
  const BTC = 'KXBTC15M-26NOV120245-45';
  audit.write('heat', { event: 'closed', ticker: 'KXSOL15M-OLD', asset: 'SOL', kind: '15m', side: 'yes', ruleId: 'old', h: 15, pnl: -9, settled: true, trips: 1, wins: 0 });
  at(0);
  audit.write('heat', { asset: 'BTC', h: 15, key: 'AROONup14=very low', dir: 'up', plan: { ticker: BTC, side: 'yes', price: 0.5, count: 20, stakeUsd: 10 }, entry: 'sent' });
  at(3);
  audit.write('plan', { event: 'plan_loser_cut_sell', ticker: BTC, side: 'yes', ruleId: 'heat:1:BTC:h15', count: 20, bid: 0.39, net: -2.5, limit: 0.37, entry: 0.5, loserCut: 0.1, sent: true });
  // The engine's closed record: the trip's fields, then the book's trips, wins and running total under pnl.
  audit.write('heat', { event: 'closed', ticker: BTC, asset: 'BTC', kind: '15m', side: 'yes', ruleId: 'heat:1:BTC:h15', h: 15, pnl: -11.5, settled: false, trips: 2, wins: 0 });
  at(4);
  audit.write('heat', { asset: 'BTC', h: 15, key: 'AROONup14=very low', dir: 'up', skip: 'the call\'s bar closed before the lane\'s last loss in this window: a re-entry needs a call made after it' });
  audit.write('heat', { asset: 'ETH', h: 15, key: 'x', dir: 'up', skip: 'no edge after fees 3c' });
  at(5);
  audit.write('heat', { asset: 'BTC', h: 15, key: 'MACD flip', dir: 'down', plan: { ticker: BTC, side: 'no', price: 0.62, count: 16, stakeUsd: 10 }, entry: 'sent' });
  at(9);
  audit.write('heat', { event: 'closed', ticker: BTC, asset: 'BTC', kind: '15m', side: 'no', ruleId: 'heat:2:BTC:h15', h: 15, pnl: -10, settled: false, trips: 3, wins: 1 });
  // An hourly window: a loss on one strike, then an entry on another strike of the same window.
  at(20);
  audit.write('heat', { event: 'closed', ticker: 'KXETHD-26NOV1203-T2044.99', asset: 'ETH', kind: 'hourly', side: 'yes', ruleId: 'heat:3:ETH:h60', h: 60, pnl: -14, settled: true, trips: 4, wins: 1 });
  at(25);
  audit.write('heat', { asset: 'ETH', h: 60, key: 'k', dir: 'up', plan: { ticker: 'KXETHD-26NOV1203-T2049.99', side: 'yes', price: 0.4, count: 25, stakeUsd: 10 }, entry: 'sent' });
  const iso = (min: number) => new Date(base + min * 60_000).toISOString();
  const journal = path.join(dir, 'trips.log');
  fs.writeFileSync(journal, [
    `Nov 12 00:03:00 ip node[1]: ${iso(3)} INFO  [heat] round trip closed ${BTC} yes pnl -2.50 (sold); book 2 trips, 0 wins, pnl -11.50`,
    `Nov 12 00:09:00 ip node[1]: ${iso(9)} INFO  [heat] round trip closed ${BTC} no pnl 1.50 (sold); book 3 trips, 1 wins, pnl -10.00`,
    `Nov 12 00:20:00 ip node[1]: ${iso(20)} INFO  [heat] round trip closed KXETHD-26NOV1203-T2044.99 yes pnl -4.00 (settled); book 4 trips, 1 wins, pnl -14.00`,
    'Nov 12 00:21:00 ip node[1]: some other line',
  ].join('\n') + '\n');
  return { dir, journal };
}

const run = (args: string[]) => {
  const r = spawnSync(python!, ['-I', SCRIPT, ...args], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  return r.stdout;
};

test('heat trips: round trips from the bot log, the loser cut, re-entries by window and the re-entry rules\' refusals', { skip: !python && 'no python' }, () => {
  const { dir, journal } = fixture();
  const out = run([dir, '24', '--journal', journal]);
  assert.match(out, /round trip results from the bot log \(3 lines\)/);
  assert.match(out, /round trips closed: 3, 1 won, net -\$5\.00 \| sold 2 \(-\$1\.00\) \| settled 1 \(-\$4\.00\), 1 of them at a loss \(-\$4\.00\)/);
  assert.match(out, /loser_cut_sell\s+KXBTC15M-26NOV120245-45\s+yes entry 0\.50\s+bid 0\.39\s+count 20\s+net\s+-\$2\.50 limit 0\.37\s+sent/);
  // The BTC contract: the NO entry after the loss is a re-entry; the ETH entry on another strike of the window is one too.
  assert.match(out, /windows left at a loss: 2 \| re-entries sent after a loss: 2 in 2 window\(s\)/);
  assert.match(out, /re-entry \S+ \S+ KXBTC15M-26NOV120245-45\s+no\s+at 0\.62 x16 \(\$10\) call down MACD flip -> sent/);
  assert.match(out, /KXETHD-26NOV1203\s+losses 1 \(-\$4\.00\)/);
  assert.match(out, /re-entry \S+ \S+ KXETHD-26NOV1203-T2049\.99/);
  // The re-entry rules' refusals are listed first.
  const lines = out.split('\n');
  const i = lines.findIndex((l) => l.startsWith('calls not entered: 2'));
  assert.ok(i >= 0, out);
  assert.match(lines[i + 1], /^\s+1\s+re-entry: the call's bar closed before/);
  assert.doesNotMatch(out, /KXSOL15M-OLD/, 'a record from before the window is left out');
});

test('heat trips: without the bot log a trip\'s result is the change in the book total', { skip: !python && 'no python' }, () => {
  const { dir } = fixture();
  const out = run([dir, '24']);
  assert.match(out, /round trip results from the audit/);
  // The first trip in the window follows the old record's total (-9): -11.5 - -9 = -2.5; then +1.5 and -4.
  assert.match(out, /KXBTC15M-26NOV120245-45\s+yes\s+-\$2\.50 sold/);
  assert.match(out, /KXBTC15M-26NOV120245-45\s+no\s+\+\$1\.50 sold/);
  assert.match(out, /KXETHD-26NOV1203-T2044\.99\s+yes\s+-\$4\.00 settled/);
});
