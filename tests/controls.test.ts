// Dashboard controls: PLAY / STOP (persisted, blocks new entries, cancels resting orders) and the
// PAPER / LIVE switch (validated, rewrites bot.env, restarts); the env-file editor; the latency registry.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { AddressInfo } from 'node:net';
import { createApi, type ApiDeps } from '../bot/api/server';
import { loadConfig } from '../bot/config';
import { RunControl } from '../bot/control';
import { updateEnvFile } from '../bot/util/envFile';
import { latencySnapshot, recordLatency } from '../bot/util/latency';

async function serve(env: Record<string, string>, extra: Partial<ApiDeps> = {}) {
  const cfg = loadConfig(env);
  const base0 = { cfg, startedAt: Date.now(), audit: { write: () => undefined }, ...extra } as unknown as ApiDeps;
  const deps = new Proxy(base0, { get: (t, k) => (k in t ? (t as any)[k] : undefined) });
  const srv = createApi(deps).listen(0);
  await new Promise((r) => srv.once('listening', r));
  const url = `http://127.0.0.1:${(srv.address() as AddressInfo).port}/api`;
  const post = async (p: string, body: unknown) => { const r = await fetch(url + p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); return { status: r.status, json: await r.json() as any }; };
  return { post, close: () => srv.close() };
}

test('env file editor: rewrites keys in place, appends new ones, keeps comments and permissions', () => {
  const f = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'env-')), 'bot.env');
  fs.writeFileSync(f, '# comment\nTRADING_MODE=paper\nPORT=3000\n', { mode: 0o600 });
  updateEnvFile(f, { TRADING_MODE: 'live', KALSHI_ENV: 'prod' });
  assert.equal(fs.readFileSync(f, 'utf8'), '# comment\nTRADING_MODE=live\nPORT=3000\nKALSHI_ENV=prod\n');
  assert.equal(fs.statSync(f).mode & 0o777, 0o600);
});

test('PLAY / STOP: persisted, stopping cancels resting orders', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ctl-'));
  const control = new RunControl(path.join(dir, 'control.json'));
  let cancelled = 0;
  const s = await serve({}, { control, oms: { cancelAll: async () => { cancelled++; } } as never });
  try {
    const r = await s.post('/run', { active: false });
    assert.equal(r.json.run.active, false);
    assert.equal(cancelled, 1);
    assert.equal(new RunControl(path.join(dir, 'control.json')).active, false, 'survives a restart');
    assert.equal((await s.post('/run', { active: true })).json.run.active, true);
  } finally { s.close(); }
});

test('PAPER / LIVE: live needs the confirmation and settings that would start; then bot.env is rewritten and the bot restarts', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mode-'));
  const envFile = path.join(dir, 'bot.env');
  fs.writeFileSync(envFile, 'TRADING_MODE=paper\n', { mode: 0o600 });
  let restarts = 0;
  const s = await serve({ BOT_ENV_FILE: envFile }, { restart: () => { restarts++; } });
  const saved = { ...process.env };
  try {
    assert.equal((await s.post('/mode', { mode: 'live' })).status, 400, 'no double-tap confirmation');
    const noKeys = await s.post('/mode', { mode: 'live', confirm: 'LIVE' });
    assert.equal(noKeys.status, 400);
    assert.match(noKeys.json.error, /KALSHI_KEY_ID/);
    assert.equal(fs.readFileSync(envFile, 'utf8'), 'TRADING_MODE=paper\n', 'nothing written when the switch would fail');
    const key = path.join(dir, 'key.pem');
    fs.writeFileSync(key, 'x', { mode: 0o600 });
    process.env.KALSHI_KEY_ID = 'k'; process.env.KALSHI_PRIVATE_KEY_PATH = key;
    const ok = await s.post('/mode', { mode: 'live', confirm: 'LIVE' });
    assert.equal(ok.status, 200);
    const text = fs.readFileSync(envFile, 'utf8');
    assert.match(text, /TRADING_MODE=live/); assert.match(text, /KALSHI_ENV=prod/); assert.match(text, /LIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK/);
    const again = await s.post('/mode', { mode: 'live', confirm: 'LIVE' });
    assert.equal(again.status, 409, 'a second switch before the restart is refused');
    assert.equal(fs.readFileSync(envFile, 'utf8'), text, 'and writes nothing');
    await new Promise((r) => setTimeout(r, 700));
    assert.equal(restarts, 1);
  } finally { process.env = saved; s.close(); }
});

// A scratch bot.env and a server started from it the way production starts: systemd loads the file into the server's
// environment (EnvironmentFile) and d.cfg comes from that. The file can then be edited before a switch, as an
// operator may do between restarts.
function modeHarness(prefix: string) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  const envFile = path.join(dir, 'bot.env');
  const key = path.join(dir, 'key.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  const keys = { KALSHI_KEY_ID: 'k', KALSHI_PRIVATE_KEY_PATH: key };
  const read = () => fs.readFileSync(envFile, 'utf8');
  const write = (text: string) => fs.writeFileSync(envFile, text, { mode: 0o600 });
  // bot.env as the restart would load it (plus the keys, which the server's environment carries).
  const fileEnv = () => ({ ...keys, BOT_ENV_FILE: envFile, ...Object.fromEntries(read().split('\n').filter((l) => l.includes('=')).map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)])) });
  const audits: { changes: string[] }[] = [];
  const audit = { write: (_kind: string, e: { changes: string[] }) => { audits.push(e); } };
  const saved = { ...process.env };
  const start = async (extra: Partial<ApiDeps> = {}) => { process.env = { ...saved, ...fileEnv() }; return serve(fileEnv(), { audit, ...extra } as never); };
  const switchTo = async (body: Record<string, string>, extra: Partial<ApiDeps> = {}) => {
    const s = await start(extra);
    try { return await s.post('/mode', body); } finally { s.close(); }
  };
  return { read, write, fileEnv, audits, start, switchTo, restore: () => { process.env = saved; } };
}

test('PAPER / LIVE: live writes only the mode, KALSHI_ENV and the acknowledgement (perps and tennis stay as configured); paper demotes live perps and tennis', async () => {
  const h = modeHarness('mode-scope-');
  try {
    // LIVE from the template's mode block: perps on paper, tennis tracking-only in live.
    h.write('TRADING_MODE=paper\nKALSHI_ENV=prod\nPERP_TRADING=paper\nPERP_HEDGE=paper\nTENNIS_LIVE=false\n');
    assert.equal((await h.switchTo({ mode: 'live', confirm: 'LIVE' })).status, 200);
    assert.equal(h.read(), 'TRADING_MODE=live\nKALSHI_ENV=prod\nPERP_TRADING=paper\nPERP_HEDGE=paper\nTENNIS_LIVE=false\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\n');
    assert.deepEqual([...h.audits.at(-1)!.changes].sort(), ['KALSHI_ENV', 'LIVE_TRADING_ACKNOWLEDGED', 'TRADING_MODE']);
    // The restart trades only the binaries live: paper perps read as off in live, tennis stays tracking-only.
    const live = loadConfig(h.fileEnv());
    assert.equal(live.mode, 'live');
    assert.deepEqual([live.perps.trading, live.perps.hedge, live.tennis.live], ['off', 'off', false]);

    // PAPER back from that live start: nothing was live to demote, and paper perps stay paper (not off).
    assert.equal((await h.switchTo({ mode: 'paper' })).status, 200);
    assert.equal(h.read(), 'TRADING_MODE=paper\nKALSHI_ENV=prod\nPERP_TRADING=paper\nPERP_HEDGE=paper\nTENNIS_LIVE=false\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\n');
    const paper = loadConfig(h.fileEnv());
    assert.deepEqual([paper.mode, paper.perps.trading, paper.perps.hedge], ['paper', 'paper', 'paper']);

    // PAPER from the documented live setup (perps trading and hedging live, tennis live), all set by hand: both perps
    // settings go back to paper and TENNIS_LIVE to false.
    h.write('TRADING_MODE=live\nKALSHI_ENV=prod\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\nPERP_TRADING=live\nPERP_HEDGE=live\nTENNIS_LIVE=true\n');
    assert.equal((await h.switchTo({ mode: 'paper' })).status, 200);
    assert.equal(h.read(), 'TRADING_MODE=paper\nKALSHI_ENV=prod\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\nPERP_TRADING=paper\nPERP_HEDGE=paper\nTENNIS_LIVE=false\n');
    const both = loadConfig(h.fileEnv());
    assert.deepEqual([both.mode, both.perps.trading, both.perps.hedge, both.tennis.live], ['paper', 'paper', 'paper', false]);

    // PAPER from a live start with only perps trading live: it goes back to paper, an off perps setting stays off.
    h.write('TRADING_MODE=live\nKALSHI_ENV=prod\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\nPERP_TRADING=live\nPERP_HEDGE=off\nTENNIS_LIVE=true\n');
    assert.equal((await h.switchTo({ mode: 'paper' })).status, 200);
    assert.equal(h.read(), 'TRADING_MODE=paper\nKALSHI_ENV=prod\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\nPERP_TRADING=paper\nPERP_HEDGE=off\nTENNIS_LIVE=false\n');
    const demoted = loadConfig(h.fileEnv());
    assert.deepEqual([demoted.mode, demoted.perps.trading, demoted.perps.hedge, demoted.tennis.live], ['paper', 'paper', 'off', false]);

    // PAPER after bot.env was edited since the start: the bot started live with paper perps (read as off), then the
    // operator set perps live in bot.env and has not restarted. The perps settings in the file go back to paper, so
    // the restart loads (a paper bot.env with PERP_*=live would exit with code 2 and stay down).
    h.write('TRADING_MODE=live\nKALSHI_ENV=prod\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\nPERP_TRADING=paper\nPERP_HEDGE=paper\nTENNIS_LIVE=false\n');
    const s = await h.start();
    try {
      h.write('TRADING_MODE=live\nKALSHI_ENV=prod\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\nPERP_TRADING=live\nPERP_HEDGE=live\nTENNIS_LIVE=false\n');
      assert.equal((await s.post('/mode', { mode: 'paper' })).status, 200);
    } finally { s.close(); }
    assert.equal(h.read(), 'TRADING_MODE=paper\nKALSHI_ENV=prod\nLIVE_TRADING_ACKNOWLEDGED=I_ACCEPT_REAL_MONEY_RISK\nPERP_TRADING=paper\nPERP_HEDGE=paper\nTENNIS_LIVE=false\n');
    const edited = loadConfig(h.fileEnv());
    assert.deepEqual([edited.mode, edited.perps.trading, edited.perps.hedge], ['paper', 'paper', 'paper']);
  } finally { h.restore(); }
});

test('PAPER / LIVE: live is refused when the restart would refuse to start (unvalidated model, closed kalshi gate, no other live book)', async () => {
  const h = modeHarness('mode-exit3-');
  const model = { id: 'm1', liveBlockers: () => ['validation.passed is false'] };
  const blocked = 'TRADING_MODE=paper\nLIVE_ALLOW_UNVALIDATED_MODEL=false\nVALIDATION_GATES=enforce\nTENNIS_LIVE=false\n';
  try {
    // main.ts would exit with code 3 (systemd does not restart it): refused, nothing written.
    h.write(blocked);
    const r = await h.switchTo({ mode: 'live', confirm: 'LIVE' }, { model } as never);
    assert.equal(r.status, 400);
    assert.match(r.json.error, /exit code 3/);
    assert.match(r.json.error, /LIVE_ALLOW_UNVALIDATED_MODEL/);
    assert.equal(h.read(), blocked, 'nothing written when the restart would not start');

    // Another book live (here tennis, set in bot.env after the start): main.ts starts, so the switch goes through.
    const s = await h.start({ model } as never);
    try {
      h.write(blocked.replace('TENNIS_LIVE=false', 'TENNIS_LIVE=true'));
      assert.equal((await s.post('/mode', { mode: 'live', confirm: 'LIVE' })).status, 200);
    } finally { s.close(); }
    assert.match(h.read(), /^TRADING_MODE=live$/m);

    // An open kalshi gate (VALIDATION_GATES=monitor, the default) or LIVE_ALLOW_UNVALIDATED_MODEL=true (the default):
    // the binary model does not block the start.
    h.write('TRADING_MODE=paper\nLIVE_ALLOW_UNVALIDATED_MODEL=false\nTENNIS_LIVE=false\n');
    assert.equal((await h.switchTo({ mode: 'live', confirm: 'LIVE' }, { model } as never)).status, 200);
    h.write('TRADING_MODE=paper\nVALIDATION_GATES=enforce\nTENNIS_LIVE=false\n');
    assert.equal((await h.switchTo({ mode: 'live', confirm: 'LIVE' }, { model } as never)).status, 200);
  } finally { h.restore(); }
});

test('latency registry: smoothed per channel, null when stale', () => {
  recordLatency('kalshiWs', 100, 1000); recordLatency('kalshiWs', 200, 2000);
  assert.equal(latencySnapshot(3000).kalshiWs, 120);
  assert.equal(latencySnapshot(1000 + 400_000).kalshiWs, null);
});

test('reconciliation breaks: the kill-switch reset says how to resolve them; Resolve adopts Kalshi\'s positions and the reset then goes through', async () => {
  const runs: Array<{ trigger: string; adopt?: boolean }> = [];
  const recon = {
    halted: true, busy: false, lastResult: { ok: false, breaks: ['position mismatch T: internal 0 vs exchange 2 (Kalshi\'s position is adopted if this persists)'] },
    async run(trigger: string, opts: { adopt?: boolean } = {}) {
      runs.push({ trigger, ...opts });
      if (opts.adopt) this.halted = false;
      return { ok: !!opts.adopt, breaks: [], adopted: ['T: internal 0 vs exchange 2: adopted Kalshi\'s 2 at 0.50 (operator)'], externalOrders: [], repairedFills: 0, orphanOrdersCanceled: 0, ts: 1 };
    },
  };
  let resets = 0;
  const kill = { reset: () => { resets++; }, status: () => ({ engaged: resets === 0 }) };
  const s = await serve({}, { recon: recon as never, kill: kill as never });
  try {
    const blocked = await s.post('/kill/reset', { confirm: 'RESET KILL SWITCH' });
    assert.equal(blocked.status, 409);
    assert.match(blocked.json.error, /reconciliation is not clean/);
    assert.equal(blocked.json.resolve, '/api/recon/resolve');
    assert.equal((await s.post('/recon/resolve', {})).status, 400, 'needs the confirm phrase');
    const resolved = await s.post('/recon/resolve', { confirm: 'ADOPT KALSHI POSITIONS' });
    assert.equal(resolved.status, 200);
    assert.deepEqual(runs, [{ trigger: 'operator', adopt: true }]);
    assert.equal(resolved.json.halted, false);
    assert.equal((await s.post('/kill/reset', { confirm: 'RESET KILL SWITCH' })).status, 200);
    assert.equal(resets, 1);
  } finally { s.close(); }
});
