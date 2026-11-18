// Env-driven start of the raw frame journal inside the bot: off by default, caps, clean footer. Local loopback only.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { WebSocketServer } from 'ws';
import { KalshiWs } from '../bot/kalshi/ws';
import type { KalshiSigner } from '../bot/kalshi/auth';
import { attachRawTapFromEnv } from '../research/ralph_capture/attach';

const VERIFY = path.resolve('research/ralph_capture/verify_journal.py');
const signer = { headers: () => ({ 'KALSHI-ACCESS-KEY': 'SENTINEL-ATTACH-KEY' }) } as unknown as KalshiSigner;
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'ralph-attach-'));
const verify = (f: string) => JSON.parse(spawnSync('python3', ['-I', VERIFY, f], { encoding: 'utf8' }).stdout);
const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** A loopback exchange that sends a snapshot and a few deltas on the first command, then keeps the socket open. */
async function harness(deltas = 3) {
  const wss = new WebSocketServer({ host: '127.0.0.1', port: 0 });
  await new Promise<void>((r) => wss.once('listening', () => r()));
  const port = (wss.address() as { port: number }).port;
  let first = true;
  wss.on('connection', (sock) => sock.on('message', () => {
    if (!first) return;
    first = false;
    sock.send('{"type":"orderbook_snapshot","sid":1,"seq":1,"msg":{"market_ticker":"KXT-A","yes_dollars_fp":[["0.4500","10.00"]],"no_dollars_fp":[["0.5000","5.00"]]}}');
    for (let i = 0; i < deltas; i++) sock.send(`{"type":"orderbook_delta","sid":1,"seq":${i + 2},"msg":{"market_ticker":"KXT-A","price_dollars":"0.4500","delta_fp":"1.00","side":"yes"}}`);
  }));
  const url = `ws://127.0.0.1:${port}/trade-api/ws/v2`;
  const ws = new KalshiWs(url, signer, []);
  const events: string[] = [];
  ws.on('book_snapshot', () => events.push('snap'));
  ws.on('book_delta', () => events.push('delta'));
  ws.setMarkets(['KXT-A']);
  const close = async () => { const gone = new Promise<void>((r) => ws.once('disconnected', () => r())); ws.close(); await gone; await new Promise<void>((r) => wss.close(() => r())); };
  return { ws, url, events, close };
}

test('every way of being off leaves the socket untouched and writes nothing', async () => {
  const dir = path.join(tmp(), 'must-not-exist');
  const ws = new KalshiWs('ws://127.0.0.1:1/trade-api/ws/v2', signer, []);
  const ctx = { mode: 'paper', wsUrl: 'ws://127.0.0.1:1/trade-api/ws/v2' };
  const cases: [string, NodeJS.ProcessEnv, typeof ctx][] = [
    ['unset', {}, ctx],
    ['zero', { RALPH_RAW_TAP: '0', RALPH_RAW_TAP_DIR: dir }, ctx],
    ['yes', { RALPH_RAW_TAP: 'yes', RALPH_RAW_TAP_DIR: dir }, ctx],
    ['no dir', { RALPH_RAW_TAP: '1' }, ctx],
    ['relative dir', { RALPH_RAW_TAP: '1', RALPH_RAW_TAP_DIR: 'relative/dir' }, ctx],
    ['live mode', { RALPH_RAW_TAP: '1', RALPH_RAW_TAP_DIR: dir }, { ...ctx, mode: 'live' }],
    ['bad url', { RALPH_RAW_TAP: '1', RALPH_RAW_TAP_DIR: dir }, { ...ctx, wsUrl: 'not a url' }],
  ];
  for (const [name, env, c] of cases) {
    assert.equal(attachRawTapFromEnv(ws, env, c), undefined, name);
    assert.equal((ws as any).sink, undefined, `${name}: no sink attached`);
  }
  assert.equal(fs.existsSync(dir), false, 'no directory was created');
});

test('switched on: frames are journaled, stop() writes the footer and detaches, the bot sees the same events', async () => {
  const dir = path.join(tmp(), 'journals');
  const h = await harness();
  const handle = attachRawTapFromEnv(h.ws, { RALPH_RAW_TAP: '1', RALPH_RAW_TAP_DIR: dir }, { mode: 'paper', wsUrl: h.url })!;
  assert.ok(handle);
  h.ws.connect();
  await wait(300);
  const first = handle.stop();
  assert.equal(handle.stop(), first, 'stop is idempotent');
  await first;
  assert.equal((h.ws as any).sink, undefined);
  assert.deepEqual(h.events, ['snap', 'delta', 'delta', 'delta']);
  await h.close();
  const report = verify(handle.file);
  assert.equal(report.locally_consistent, true, JSON.stringify(report.reasons));
  assert.equal(report.notes.frames, 4);
  assert.equal(report.notes.footer.reason, 'stopped');
  assert.equal(fs.statSync(handle.file).mode & 0o777, 0o600);
  assert.ok(!fs.readFileSync(handle.file, 'utf8').includes('SENTINEL-ATTACH-KEY'));
});

for (const [name, tuning, reason] of [['size', { maxBytes: 1, pollMs: 20 }, 'size_cap'], ['time', { maxMs: 1, pollMs: 20 }, 'time_cap']] as const) {
  test(`the ${name} cap ends the capture with a footer while the bot keeps receiving`, async () => {
    const dir = path.join(tmp(), 'journals');
    const h = await harness();
    const handle = attachRawTapFromEnv(h.ws, { RALPH_RAW_TAP: '1', RALPH_RAW_TAP_DIR: dir }, { mode: 'paper', wsUrl: h.url }, tuning)!;
    h.ws.connect();
    await wait(400);
    assert.equal((h.ws as any).sink, undefined, 'detached by the cap');
    assert.deepEqual(h.events, ['snap', 'delta', 'delta', 'delta'], 'the bot saw every frame regardless');
    await handle.stop();                    // already stopped: resolves
    await h.close();
    const report = verify(handle.file);
    assert.equal(report.notes.footer.reason, reason);
    assert.equal(report.reasons.includes('missing_valid_footer'), false);
  });
}
