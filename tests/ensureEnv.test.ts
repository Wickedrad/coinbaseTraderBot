// deploy/ensure-env.sh moves a server bot.env off pinned old defaults on every deploy. Run it against a scratch HOME.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const script = path.resolve('deploy/ensure-env.sh');

// The release's deploy/ folder ships the heat reader's installer since #327, and ensure-env then turns the heat lane on
// (tested below). These older tests check other rules, so they run a copy of the script from a folder without it.
function run(lines: string[]): { env: string[]; out: string } {
  return runFrom(lines, false);
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

test('ensure-env: a bot.env pinning the old hunt session guard drops the line; HUNT_SESSION_GUARD=false stays', () => {
  const { env, out } = run(['TRADING_MODE=paper', 'HUNT_SESSION_GUARD=true', 'PORT=3000']);
  assert.deepEqual(env, ['TRADING_MODE=paper', 'PORT=3000']);
  assert.match(out, /HUNT_SESSION_GUARD=true removed/);
  assert.deepEqual(run(['TRADING_MODE=paper', 'HUNT_SESSION_GUARD=1']).env, ['TRADING_MODE=paper']);
  const kept = ['TRADING_MODE=paper', 'HUNT_SESSION_GUARD=false', 'HUNT_TRANSITION_BUFFER_MIN=10'];
  assert.deepEqual(run(kept).env, kept);
});

// The heat lane's switches (Steven, Nov 11): set only from a release that ships the curve reader's installer, only where
// bot.env has no line of its own. Run a copy of the script from a scratch deploy/ folder, with and without the installer.
function runFrom(lines: string[], withInstaller: boolean): { env: string[]; out: string } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ensure-env-heat-'));
  try {
    const home = path.join(root, 'home'), dep = path.join(root, 'release', 'deploy');
    fs.mkdirSync(path.join(home, 'bot'), { recursive: true });
    fs.mkdirSync(dep, { recursive: true });
    fs.copyFileSync(script, path.join(dep, 'ensure-env.sh'));
    if (withInstaller) fs.writeFileSync(path.join(dep, 'heat_reader_install.sh'), '#!/usr/bin/env bash\nexit 0\n');
    fs.writeFileSync(path.join(home, 'bot', 'bot.env'), lines.join('\n') + '\n', { mode: 0o600 });
    const out = execFileSync('bash', [path.join(dep, 'ensure-env.sh')], { env: { PATH: process.env.PATH ?? '', HOME: home }, encoding: 'utf8' });
    const file = path.join(home, 'bot', 'bot.env');
    assert.equal(fs.statSync(file).mode & 0o777, 0o600, 'bot.env keeps mode 600');
    return { env: fs.readFileSync(file, 'utf8').split('\n').filter(Boolean), out };
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

test('ensure-env: a release with the reader installer turns the heat lane and plan rules on where bot.env says nothing', () => {
  const { env, out } = runFrom(['TRADING_MODE=paper', 'PORT=3000'], true);
  assert.deepEqual(env, ['TRADING_MODE=paper', 'PORT=3000', 'HEAT_LANE=true', 'PLAN_RULES=true']);
  assert.match(out, /HEAT_LANE=true added/);
  assert.match(out, /PLAN_RULES=true added/);
  const again = runFrom(env, true);
  assert.deepEqual(again.env, env, 'idempotent');
  assert.doesNotMatch(again.out, /added/);
});

test('ensure-env: without the reader installer the heat lane switches are not touched', () => {
  const { env, out } = runFrom(['TRADING_MODE=paper'], false);
  assert.deepEqual(env, ['TRADING_MODE=paper']);
  assert.doesNotMatch(out, /HEAT_LANE|PLAN_RULES/);
});

test('ensure-env: an explicit HEAT_LANE=false stays off and adds no PLAN_RULES', () => {
  const { env, out } = runFrom(['TRADING_MODE=paper', 'HEAT_LANE=false'], true);
  assert.deepEqual(env, ['TRADING_MODE=paper', 'HEAT_LANE=false']);
  assert.doesNotMatch(out, /added|warning/);
});

test('ensure-env: HEAT_LANE=true keeps an explicit PLAN_RULES value and warns when it is off', () => {
  const kept = runFrom(['HEAT_LANE=true', 'PLAN_RULES=true'], true);
  assert.deepEqual(kept.env, ['HEAT_LANE=true', 'PLAN_RULES=true']);
  assert.doesNotMatch(kept.out, /added|warning/);
  const off = runFrom(['HEAT_LANE="true"', 'PLAN_RULES=false'], true);
  assert.deepEqual(off.env, ['HEAT_LANE="true"', 'PLAN_RULES=false']);
  assert.match(off.out, /warning: HEAT_LANE=true but PLAN_RULES=false/);
});
