import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { gzipSync, gunzipSync } from 'node:zlib';
import { researchOnly } from '../deploy/deploy-scope';

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

test('archive export is exclusive, reads only fixed market files and keeps the copy on the runner', () => {
  const yaml = fs.readFileSync('.github/workflows/diagnose.yml', 'utf8');
  const job = yaml.split('  atlas-archive-export:')[1].split('  atlas-drive-inventory:')[0];
  assert.match(job, /gdrive:kalshi-bot-archive\/raw\/history/);
  assert.match(job, /--files-from/); assert.match(job, /archiveAudit\.py/);
  assert.match(job, /RCLONE_CONFIG="\$cfg\/rclone.conf"/);
  // Nov 11, 2026 (8:05 AM EST / 13:05 UTC): the repository is public, so the copied Drive archive is never an artifact.
  assert.doesNotMatch(job, /name: atlas-history-archive|path: .*atlas-history-archive/);
  assert.doesNotMatch(job, /LIGHTSAIL|ssh |pipeline|rclone (?:sync|move|delete|purge)/);
  assert.match(job, /if: inputs\.atlas_offline_history_study == 'true'/, 'fitting is a separate explicit runner-only opt-in');
});

test('archive audit can explicitly select a TV source and asset set without silently requiring another source', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-audit-source-'));
  try {
    const dir = path.join(root, 'tvdatafeed-coinbase/BTC'); fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, '1m.csv'), header + bar(0) + bar(60000));
    const out = path.join(root, 'audit.json');
    const run = spawnSync('python3', ['-B', 'research/opportunity/archiveAudit.py', root, '--source', 'tvdatafeed-coinbase', '--assets', 'BTC', '--out', out], { encoding: 'utf8' });
    assert.equal(run.status, 0, run.stderr);
    const r = JSON.parse(fs.readFileSync(out, 'utf8'));
    assert.equal(r.ready, true); assert.deepEqual(r.required_assets, ['BTC']);
    assert.equal(r.files[0].source, 'tvdatafeed-coinbase'); assert.equal(r.required_source, 'tvdatafeed-coinbase');
    assert.ok(r.missing.every((name: string) => !name.startsWith('binance')));
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('off-grid quarantine preserves input bytes, excludes rather than shifts rows, and records real gaps', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-quarantine-')); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const input = path.join(root, 'raw'), history = path.join(input, 'history'), output = path.join(root, 'derived');
  const rows = header + bar(0) + bar(60017) + bar(120000);
  for (const asset of ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']) {
    const file = path.join(history, 'binance-1m', asset, '1m.csv'); fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, rows);
  }
  const a = spawnSync('python3', ['-B', 'research/opportunity/archiveAudit.py', history, '--out', path.join(input, 'archive-validation.json')], { encoding: 'utf8' });
  assert.equal(a.status, 1, 'original misalignment must fail the audit');
  const d = spawnSync('python3', ['-B', 'research/opportunity/quarantineArchive.py', input, '--out', output], { encoding: 'utf8' });
  assert.equal(d.status, 0, d.stderr);
  const derived = JSON.parse(fs.readFileSync(path.join(output, 'archive-validation.json'), 'utf8'));
  assert.equal(derived.ready, true); assert.equal(derived.files[0].missing_bars, 1);
  assert.equal(fs.readFileSync(path.join(history, 'binance-1m/BTC/1m.csv'), 'utf8'), rows);
  assert.equal(fs.readFileSync(path.join(output, 'history/archive-binance-1m-quarantined-v1/BTC/1m.csv'), 'utf8'), header + bar(0) + bar(120000));
  const metadata = JSON.parse(fs.readFileSync(path.join(output, 'derivation.json'), 'utf8'));
  assert.equal(metadata.files[0].quarantined, 1);
  assert.equal(spawnSync('python3', ['-B', 'research/opportunity/quarantineArchive.py', input, '--out', output]).status, 1);
});

test('Atlas research workflow has no server credentials or deployment path', () => {
  const yaml = fs.readFileSync('.github/workflows/atlas-research-results.yml', 'utf8');
  assert.match(yaml, /runs-on: ubuntu-latest/); assert.match(yaml, /workflow_dispatch/);
  assert.doesNotMatch(yaml, /LIGHTSAIL|ssh-action|deploy\/activate|deploy\/install|TRADING_MODE/);
  const deploy = fs.readFileSync('.github/workflows/deploy.yml', 'utf8');
  // Approved research merges avoid a server restart by what they change (deploy/deploy-scope.ts), not by "[skip deploy]".
  assert.match(deploy, /needs\.scope\.outputs\.deploy != 'false'/, 'approved research merges can avoid a server restart');
  for (const f of ['.github/workflows/atlas-research.yml', 'docs/OPPORTUNITY_ATLAS_OPERATIONS.md', 'research/opportunity/archiveAudit.py', 'research/opportunity/atlas.ts', 'tests/opportunityArchive.test.ts']) {
    assert.equal(researchOnly(f, new Set(['bot/main.ts'])), true, f);
  }
});

test('recording prefix extraction handles gzip members and strips account, model and private nested fields', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-public-prefix-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const secret = 'MUST_NOT_LEAVE_THE_RAW_PREFIX';
  const a = [{ t: 0, k: 'index', asset: 'BTC', ts: 0, value: 100, src: 'kalshi', secret }, { t: 1, k: 'account', balance: 100, token: secret }];
  const b = [{ t: 2, k: 'candles', asset: 'BTC', tf: '1m', rows: [{ ts: 0, o: 100, h: 101, l: 99, c: 100, v: 1, secret }, [0, 99, 101, 100, 100, 1, 0.4]] },
    { t: 3, k: 'book', ticker: 'KXBTC-TEST', bids: [{ price: 0.4, size: 2, secret }], asks: [{ price: 0.5, size: 2 }], secret },
    { t: 4, k: 'snn', weights: secret }];
  const prefix = path.join(dir, 'prefix.gz'), out = path.join(dir, 'public.jsonl'), report = path.join(dir, 'report.json');
  fs.writeFileSync(prefix, Buffer.concat([gzipSync(a.map((x) => JSON.stringify(x)).join('\n') + '\n'), gzipSync(b.map((x) => JSON.stringify(x)).join('\n') + '\n').subarray(0, -5)]));
  const r = spawnSync('python3', ['-B', 'research/opportunity/recordingPrefix.py', prefix, '--out', out, '--report', report], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr); assert.ok(!fs.readFileSync(out, 'utf8').includes(secret));
  const m = JSON.parse(fs.readFileSync(report, 'utf8')); assert.equal(m.complete_original_archive, false); assert.equal(m.index_sources.kalshi, 1);
  assert.equal(m.candle_timeframes['1m'], 1); assert.deepEqual(m.event_counts, { index: 1, candles: 1, book: 1 });
  const candles = fs.readFileSync(out, 'utf8').trim().split('\n').map((s) => JSON.parse(s)).find((e) => e.k === 'candles');
  assert.deepEqual(candles.rows[1], [0, 99, 101, 100, 100, 1, 0.4], 'native Coinbase tuples retain their wire format');
});

test('observed-prefix studies keep every public book update and reject proxy and fabricated replay inputs', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-observed-prefix-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const prefix = path.join(dir, 'prefix.gz'), out = path.join(dir, 'public.jsonl.gz'), report = path.join(dir, 'report.json');
  const events = [
    { t: 1, k: 'index', asset: 'BTC', value: 100, src: 'proxy' },
    { t: 2, k: 'index', asset: 'BTC', value: 100, src: 'kalshi', hist: true },
    { t: 3, k: 'market', ticker: 'KXBTC-TEST', synth: true },
    { t: 4, k: 'index', asset: 'BTC', value: 100, src: 'kalshi' },
    { t: 5, k: 'book', ticker: 'KXBTC-TEST', bids: [{ price: 0.4, size: 2 }], asks: [] },
    { t: 6, k: 'book', ticker: 'KXBTC-TEST', bids: [{ price: 0.41, size: 2 }], asks: [] },
    { t: 7, k: 'delta', ticker: 'KXBTC-TEST', side: 'yes', price: 0.41, delta: -1, token: 'PRIVATE_VALUE' },
    { t: 8, k: 'perp', ticker: 'KXBTCPERP', asset: 'BTC', mark: 100, fundingRate: 0.0001, account: 'PRIVATE_VALUE' },
  ];
  fs.writeFileSync(prefix, gzipSync(events.map((e) => JSON.stringify(e)).join('\n') + '\n'));
  const r = spawnSync('python3', ['-B', 'research/opportunity/recordingPrefix.py', prefix, '--out', out, '--report', report, '--observed-only', '--book-every-ms', '0'], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const text = gunzipSync(fs.readFileSync(out)).toString(); assert.ok(!text.includes('PRIVATE_VALUE'));
  const rows = text.trim().split('\n').map((s) => JSON.parse(s));
  assert.deepEqual(rows.map((e) => e.k), ['index', 'book', 'book', 'delta', 'perp']);
  assert.equal(rows[3].delta, -1); assert.equal(rows[4].fundingRate, 0.0001);
  const m = JSON.parse(fs.readFileSync(report, 'utf8')); assert.equal(m.proxy_or_synthetic_skipped, 3); assert.equal(m.book_every_ms, 0);
  assert.equal(m.filtered_sha256, createHash('sha256').update(fs.readFileSync(out)).digest('hex'));
});
