// deploy/ensure-env.sh moves a server bot.env off pinned old defaults on every deploy. Run it against a scratch HOME.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const script = path.resolve('deploy/ensure-env.sh');

function run(lines: string[]): { env: string[]; out: string } {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'ensure-env-'));
  try {
    fs.mkdirSync(path.join(home, 'bot'));
    fs.writeFileSync(path.join(home, 'bot', 'bot.env'), lines.join('\n') + '\n');
    const out = execFileSync('bash', [script], { env: { PATH: process.env.PATH ?? '', HOME: home }, encoding: 'utf8' });
    return { env: fs.readFileSync(path.join(home, 'bot', 'bot.env'), 'utf8').split('\n').filter(Boolean), out };
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
}

test('ensure-env: a bot.env pinning the session-edge blackout or the model-health halt on drops the line (#321 defaults)', () => {
  const { env, out } = run(['TRADING_MODE=paper', 'SESSION_EDGE_NO_ENTRY=true', 'MODEL_HEALTH_HALT=1', 'PORT=3000']);
  assert.deepEqual(env, ['TRADING_MODE=paper', 'PORT=3000']);
  assert.match(out, /SESSION_EDGE_NO_ENTRY=true removed/);
  assert.match(out, /MODEL_HEALTH_HALT=1 removed/);
});

test('ensure-env: other values of those keys, and every other line, are left alone', () => {
  const lines = ['TRADING_MODE=paper', 'SESSION_EDGE_NO_ENTRY=false', 'MODEL_HEALTH_HALT=false', 'SESSION_EDGE_NO_ENTRY_X=true', 'PORT=3000'];
  const { env } = run(lines);
  assert.deepEqual(env, lines);
});

test('ensure-env: an unpinned bot.env is unchanged and the run is idempotent', () => {
  const first = run(['TRADING_MODE=paper', 'SESSION_EDGE_NO_ENTRY=true']);
  assert.deepEqual(first.env, ['TRADING_MODE=paper']);
  const second = run(first.env);
  assert.deepEqual(second.env, ['TRADING_MODE=paper']);
  assert.doesNotMatch(second.out, /removed/);
});
