import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { test } from 'node:test';
import { ConfigError, loadConfig, paperEnv, publicConfig } from '../bot/config';

const token = 'x'.repeat(40);

test('paper defaults are safe: loopback, demo, frozen', () => {
  const c = loadConfig({ DASHBOARD_TOKEN: token });
  assert.equal(c.mode, 'paper');
  assert.equal(c.host, '127.0.0.1');
  assert.equal(c.kalshiEnv, 'demo');
  assert.throws(() => { (c as any).mode = 'live'; });
  assert.throws(() => { (c.risk as any).maxContractsPerOrder = 1e6; });
});

test('dashboard login is optional (DASHBOARD_PASSWORD); no token needed', () => {
  assert.equal(loadConfig({}).dashboardPassword, '');
  assert.equal(loadConfig({ DASHBOARD_PASSWORD: ' pw ' }).dashboardPassword, 'pw');
});

test('refuses public bind unless explicitly allowed', () => {
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: token, BIND_HOST: '0.0.0.0' }), /loopback/);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: token, BIND_HOST: '0.0.0.0', ALLOW_NON_LOOPBACK_BIND: 'true' }).host, '0.0.0.0');
});

test('live mode needs prod, credentials, a deploy-time acknowledgement, and no proxy index', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'key-'));
  const key = path.join(dir, 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  const base = { DASHBOARD_TOKEN: token, TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key };
  assert.throws(() => loadConfig(base), /KALSHI_ENV=prod/);
  assert.throws(() => loadConfig({ ...base, KALSHI_ENV: 'prod' }), /LIVE_TRADING_ACKNOWLEDGED/);
  const ok = { ...base, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' };
  assert.equal(loadConfig(ok).mode, 'live');
  // The paper pool never shows in live: its own books folder, and no simulated perps pool next to the real money.
  const live = loadConfig({ ...ok, DATA_DIR: dir });
  assert.equal(live.bookDir, path.join(path.resolve(dir), 'live'));
  assert.equal(loadConfig({ DASHBOARD_TOKEN: token, DATA_DIR: dir }).bookDir, path.resolve(dir), 'paper keeps its books in DATA_DIR');
  assert.equal(live.perps.trading, 'off', 'PERP_TRADING=paper (the default) is off in live');
  assert.equal(live.perps.hedge, 'off');
  assert.throws(() => loadConfig({ ...ok, ALLOW_PROXY_INDEX: 'true' }), /PROXY/);
  fs.chmodSync(key, 0o644);
  assert.throws(() => loadConfig(ok), /chmod 600/);
});

test('risk limits are range-checked and ordered', () => {
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: token, RISK_MAX_ORDER_FRAC: '0.5' }), ConfigError);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: token, RISK_MAX_ORDER_FRAC: '0.04', RISK_MAX_WINDOW_FRAC: '0.03' }), ConfigError);
  assert.throws(() => loadConfig({ DASHBOARD_TOKEN: token, STRATEGY_SERIES: 'KXUNKNOWN' }), /asset mapping/);
});

test('public config redacts secrets', () => {
  const pc = JSON.stringify(publicConfig(loadConfig({ DASHBOARD_TOKEN: token, ALERT_TELEGRAM_TOKEN: 'secret-telegram' }) as any));
  assert.ok(!pc.includes(token));
  assert.ok(!pc.includes('secret-telegram'));
});

test('training runs load a live server\'s settings in paper mode: live perps become paper instead of failing to load', () => {
  const live = { TRADING_MODE: 'live', PERP_HEDGE: 'live', PERP_TRADING: 'live', EXIT_POLICY: 'confluence_ratchet' };
  assert.throws(() => loadConfig({ ...live, TRADING_MODE: 'paper' }), /PERP_HEDGE=live requires TRADING_MODE=live/, 'the live check itself stays');
  const cfg = loadConfig(paperEnv(live));
  assert.equal(cfg.mode, 'paper');
  assert.equal(cfg.perps.hedge, 'paper');
  assert.equal(cfg.perps.trading, 'paper');
  assert.equal(cfg.strategy.exitPolicy, 'confluence_ratchet', 'every other setting is kept');
  assert.deepEqual(paperEnv({ PERP_HEDGE: 'off' }).PERP_HEDGE, 'off');
});

test('hunt mode is not blocked by the session by default (Steven, Nov 11 2026); HUNT_SESSION_GUARD=true brings the guard back', () => {
  assert.equal(loadConfig({}).strategy.huntSessionGuard, false);
  assert.equal(loadConfig({ HUNT_SESSION_GUARD: 'true' }).strategy.huntSessionGuard, true);
  assert.equal(loadConfig({ HUNT_SESSION_GUARD: 'false' }).strategy.huntSessionGuard, false);
});

test('DOGE series: out by default; the paper setting (empty pattern) trades them again; live and shadow keep them out unless LIVE_ALLOW_DOGE=true (Steven, Nov 12 2026)', () => {
  const ex = (env: Record<string, string>) => loadConfig(env).strategy.excludeSeries;
  const doge = ['KXDOGE15M', 'KXDOGE', 'KXDOGED'], others = ['KXBTC15M', 'KXBTCD', 'KXETH', 'KXETHD', 'KXSOL15M', 'KXXRPD'];
  // Default: DOGE excluded in paper, the other coins untouched.
  for (const s of doge) assert.ok(ex({})?.test(s), `${s} excluded by default`);
  for (const s of others) assert.ok(!ex({})?.test(s), `${s} still traded`);
  // The paper bot's setting (deploy/paper-settings.env writes STRATEGY_EXCLUDE_SERIES= into bot.env): nothing excluded.
  assert.equal(ex({ STRATEGY_EXCLUDE_SERIES: '' }), undefined);
  // A copy of that bot.env under live or shadow keeps DOGE out; other patterns stay in force; the switch lets live trade it.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'key-'));
  const key = path.join(dir, 'k.pem');
  fs.writeFileSync(key, 'x', { mode: 0o600 });
  const live = { DASHBOARD_TOKEN: token, DATA_DIR: dir, TRADING_MODE: 'live', KALSHI_KEY_ID: 'id', KALSHI_PRIVATE_KEY_PATH: key, KALSHI_ENV: 'prod', LIVE_TRADING_ACKNOWLEDGED: 'I_ACCEPT_REAL_MONEY_RISK' };
  for (const s of doge) assert.ok(ex({ ...live, STRATEGY_EXCLUDE_SERIES: '' })?.test(s), `${s} excluded in live with the paper setting`);
  assert.ok(ex({ ...live, TRADING_MODE: 'shadow', STRATEGY_EXCLUDE_SERIES: '' })?.test('KXDOGE15M'), 'shadow previews live: DOGE out');
  assert.ok(ex({ ...live, STRATEGY_EXCLUDE_SERIES: 'KXSOL' })?.test('KXSOL15M'), 'an explicit pattern still applies in live');
  assert.equal(ex({ ...live, STRATEGY_EXCLUDE_SERIES: '', LIVE_ALLOW_DOGE: 'true' }), undefined, 'LIVE_ALLOW_DOGE=true lets live trade DOGE');
  assert.ok(ex({ ...live, LIVE_ALLOW_DOGE: 'true' })?.test('KXDOGE15M'), 'the default pattern still excludes it until the pattern is emptied');
});
