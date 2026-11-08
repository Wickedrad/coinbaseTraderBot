import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';

const script = path.resolve('research/opportunity/archiveInventory.py');
const openAt = Date.UTC(2017, 7, 17, 4);
function fixture(base: string, relative: string, unit = 1): string {
  const file = path.join(base, relative);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `ts,o,h,l,c,v\n${openAt / unit},100,101,99,100,1\n${(openAt + 60000) / unit},101,102,100,101,1\n`);
  return file;
}
function invoke(root: string, incoming: string) {
  const r = spawnSync('python3', ['-B', script, '--root', root, '--incoming', incoming], { encoding: 'utf8', timeout: 10000 });
  return { ...r, report: r.stdout ? JSON.parse(r.stdout) : null };
}

test('archive inventory distinguishes TradingView-layout candidates from native exchange minute files', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-inventory-'));
  try {
    fixture(root, 'tvspot/BTC/1m.csv'); fixture(root, 'tradingview/BTC.D/1d.csv');
    fixture(root, 'binance-1m/BTC/1m.csv');
    const r = invoke(root, path.join(root, 'missing'));
    assert.equal(r.status, 0, r.stderr); assert.equal(r.report.read_only, true);
    assert.equal(r.report.files.length, 3);
    assert.deepEqual(r.report.tv_minute_candidates, ['tvspot/BTC/1m.csv']);
    const f = r.report.files.find((f: { source: string }) => f.source === 'tvspot');
    assert.equal(f.first_open_utc, new Date(openAt).toISOString().replace('.000Z', 'Z'));
    assert.equal(f.provenance_verified, false, 'directory names must not masquerade as verified provenance');
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('inventory recognizes second/millisecond stamps, raw exports and declared provenance without dumping rows', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-inventory-'));
  try {
    const root = path.join(base, 'history'), incoming = path.join(base, 'incoming');
    const file = fixture(root, 'tvdatafeed-coinbase/ETH/1m.csv');
    fs.writeFileSync(`${file}.provenance.json`, JSON.stringify({ provider: 'tvdatafeed', token: 'NEVER_PRINT_THIS' }));
    fixture(incoming, 'tvspot__BTC__1m__COINBASE-BTCUSD.csv', 1000);
    const before = fs.readFileSync(file, 'utf8');
    const r = invoke(root, incoming);
    assert.equal(r.status, 0, r.stderr); assert.equal(r.report.tv_minute_candidates.length, 2);
    assert.ok(r.report.files.some((f: { tv_evidence: string }) => f.tv_evidence === 'sidecar-declaration'));
    assert.ok(r.report.files.every((f: { first_open_utc: string }) => f.first_open_utc === new Date(openAt).toISOString().replace('.000Z', 'Z')));
    assert.ok(!r.stdout.includes('NEVER_PRINT_THIS')); assert.ok(!r.stdout.includes(',100,101,99'));
    assert.equal(fs.readFileSync(file, 'utf8'), before);
  } finally { fs.rmSync(base, { recursive: true, force: true }); }
});

test('inventory skips symlinks escaping its root and never echoes unknown headers or credential-like content', () => {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-inventory-'));
  try {
    const root = path.join(base, 'history'), outside = fixture(base, 'outside.csv');
    const unknown = fixture(root, 'tvspot/BTC/1m.csv');
    fs.writeFileSync(unknown, 'PRIVATE_TOKEN_CONTENT\nNEVER_ECHO_ME\n');
    const link = path.join(root, 'tvspot/ETH/1m.csv');
    fs.mkdirSync(path.dirname(link), { recursive: true }); fs.symlinkSync(outside, link);
    fs.writeFileSync(path.join(root, 'bot.env'), 'SECRET=ALSO_NEVER_ECHO_ME');
    const r = invoke(root, path.join(base, 'missing'));
    assert.equal(r.status, 0, r.stderr);
    assert.ok(!r.stdout.includes('PRIVATE_TOKEN_CONTENT')); assert.ok(!r.stdout.includes('NEVER_ECHO_ME'));
    assert.ok(r.report.files.some((f: { status: string }) => f.status === 'symlink-outside-root'));
    assert.deepEqual(r.report.tv_minute_candidates, []);
  } finally { fs.rmSync(base, { recursive: true, force: true }); }
});

test('inventory samples only the header/tail of large files and fails clearly when the root is missing', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-inventory-'));
  try {
    const file = fixture(root, 'tvspot/BTC/1m.csv');
    fs.appendFileSync(file, `${openAt + 120000},101,102,100,101,1\n`.repeat(50000));
    const r = invoke(root, path.join(root, 'missing'));
    assert.equal(r.status, 0, r.stderr);
    assert.equal(r.report.files[0].sampled_bytes, 32768);
    assert.ok(r.report.files[0].size_bytes > 1000000);
    const missing = invoke(path.join(root, 'missing'), path.join(root, 'missing'));
    assert.equal(missing.status, 1); assert.equal(missing.report.root_exists, false);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('server inventory includes coarser Yahoo and exchange history and retains each source namespace', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-inventory-'));
  try {
    fixture(root, 'yahoo/BTC/1d.csv'); fixture(root, 'yahoo/ETH/1d.csv');
    fixture(root, 'binance/BTC/15m.csv'); fixture(root, 'coinbase/BTC/1h.csv');
    const r = invoke(root, path.join(root, 'missing'));
    assert.equal(r.status, 0, r.stderr); assert.equal(r.report.files.length, 4);
    assert.deepEqual(r.report.files.filter((f: { source: string }) => f.source === 'yahoo').map((f: { asset: string }) => f.asset), ['BTC', 'ETH']);
    assert.ok(r.report.files.every((f: { tv_evidence: string }) => f.tv_evidence === 'non-tv-layout'));
    assert.deepEqual(r.report.tv_minute_candidates, []);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('inventory mode excludes every existing diagnostics/repair/study job for all flag combinations', () => {
  const yaml = fs.readFileSync('.github/workflows/diagnose.yml', 'utf8');
  const jobs = new Map([...yaml.matchAll(/^  ([a-z-]+):\n    if: (.+)$/gm)].map((m) => [m[1], m[2]]));
  assert.deepEqual([...jobs.keys()].sort(), ['adversary', 'atlas-drive-inventory', 'atlas-inventory', 'diagnose', 'kalshi-repair', 'ta-study']);
  for (let flags = 0; flags < 32; flags++) {
    const values: Record<string, string> = { atlas_drive_inventory: flags & 16 ? 'true' : 'false', atlas_inventory: 'true', adversary: flags & 1 ? 'true' : 'false',
      kalshi_repair: flags & 2 ? 'true' : 'false', ta_study: flags & 4 ? 'true' : 'false', pnl: flags & 8 ? 'true' : 'false' };
    const evaluate = (expr: string) => Function(`return (${expr.replace(/inputs\.(\w+)/g, (_, key: string) => JSON.stringify(values[key] ?? ''))})`)();
    for (const [name, expr] of jobs) assert.equal(evaluate(expr), name === (values.atlas_drive_inventory === 'true' ? 'atlas-drive-inventory' : 'atlas-inventory'), name);
    values.atlas_drive_inventory = 'false';
    values.atlas_inventory = '';
    assert.equal(evaluate(jobs.get('atlas-inventory')!), false);
    assert.equal(evaluate(jobs.get('diagnose')!), values.kalshi_repair !== 'true' && values.ta_study !== 'true');
    assert.equal(evaluate(jobs.get('adversary')!), values.adversary === 'true');
    assert.equal(evaluate(jobs.get('kalshi-repair')!), values.kalshi_repair === 'true');
    assert.equal(evaluate(jobs.get('ta-study')!), values.ta_study === 'true');
  }
});
