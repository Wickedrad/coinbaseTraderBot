import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';

function audit(rows: string, extra?: (root: string) => void) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-audit-'));
  try {
    for (const asset of ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']) {
      const file = path.join(root, `binance-1m/${asset}/1m.csv`);
      fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, rows);
    }
    extra?.(root);
    const out = path.join(root, 'audit.json');
    const result = spawnSync('python3', ['-B', 'research/opportunity/archiveAudit.py', root, '--out', out], { encoding: 'utf8', timeout: 10000 });
    return { status: result.status, report: JSON.parse(fs.readFileSync(out, 'utf8')) };
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const header = 'ts,o,h,l,c,v,tb\n';
const bar = (ts: number, tb = '0.4') => `${ts},100,102,99,101,1,${tb}\n`;

test('archive audit hashes exact bytes and requires every asset without claiming provider authentication', () => {
  const input = header + bar(0) + bar(60000);
  const { status, report } = audit(input);
  assert.equal(status, 0); assert.equal(report.ready, true); assert.equal(report.context_ready, false);
  const file = report.files[0];
  assert.equal(file.rows, 2); assert.equal(file.continuous, true);
  assert.equal(file.sha256, createHash('sha256').update(input).digest('hex'));
  assert.equal(file.source, 'binance-1m'); assert.match(file.provider_identity, /not independently authenticated/);
  const missing = audit(input, (root) => fs.rmSync(path.join(root, 'binance-1m/ETH/1m.csv')));
  assert.equal(missing.status, 1); assert.equal(missing.report.ready, false);
});

test('full archive audit exposes interior gaps and rejects duplicated, reversed or off-grid timestamps', () => {
  const gaps = audit(header + bar(0) + bar(180000));
  assert.equal(gaps.status, 0); assert.equal(gaps.report.files[0].continuous, false);
  assert.equal(gaps.report.files[0].missing_bars, 2);
  for (const rows of [bar(0) + bar(0), bar(60000) + bar(0), bar(1) + bar(60001)]) {
    const invalid = audit(header + rows);
    assert.equal(invalid.status, 1); assert.equal(invalid.report.ready, false);
  }
});

test('archive audit fails closed on malformed OHLCV and optional taker volume without rewriting inputs', () => {
  for (const row of [bar(0, 'NaN'), bar(0, '2'), '0,100,99,101,100,1,\n', '0,100,102,99,101,-1,\n', '0,NaN,102,99,101,1,\n']) {
    const invalid = audit(header + row);
    assert.equal(invalid.status, 1);
    assert.equal(invalid.report.files[0].sha256, createHash('sha256').update(header + row).digest('hex'));
  }
  assert.equal(audit(header + bar(0, '')).status, 0, 'missing optional taker volume is distinct from zero');
});

test('archive export is exclusive, reads only fixed market files and keeps credentials out of its artifact', () => {
  const yaml = fs.readFileSync('.github/workflows/diagnose.yml', 'utf8');
  const job = yaml.split('  atlas-archive-export:')[1].split('  atlas-drive-inventory:')[0];
  assert.match(job, /gdrive:kalshi-bot-archive\/raw\/history/);
  assert.match(job, /--files-from/); assert.match(job, /archiveAudit\.py/);
  assert.match(job, /RCLONE_CONFIG="\$cfg\/rclone.conf"/);
  assert.match(job, /path: \$\{\{ runner.temp \}\}\/atlas-history-archive\//);
  assert.doesNotMatch(job, /LIGHTSAIL|ssh |npm |pipeline|rclone (?:sync|move|delete|purge)/);
});
