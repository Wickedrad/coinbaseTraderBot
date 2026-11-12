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

test('ensure-env: the retired HEAT_REENTER_AFTER_LOSS line is dropped, whatever its value (the bot refuses to start with it)', () => {
  for (const v of ['false', 'true', '']) {
    const { env, out } = run(['TRADING_MODE=paper', `HEAT_REENTER_AFTER_LOSS=${v}`, '# HEAT_REENTER_AFTER_LOSS=false', 'PORT=3000']);
    assert.deepEqual(env, ['TRADING_MODE=paper', '# HEAT_REENTER_AFTER_LOSS=false', 'PORT=3000'], v);
    assert.match(out, /HEAT_REENTER_AFTER_LOSS removed/);
  }
  // Spaces and an `export ` in front still set it for the bot: dropped too. A longer name is not it.
  const { env } = run(['  HEAT_REENTER_AFTER_LOSS=false', 'HEAT_REENTER_AFTER_LOSS =true', 'export HEAT_REENTER_AFTER_LOSS=1', 'HEAT_REENTER_AFTER_LOSS_X=1', 'PORT=3000']);
  assert.deepEqual(env, ['HEAT_REENTER_AFTER_LOSS_X=1', 'PORT=3000']);
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
function runFrom(lines: string[], withInstaller: boolean, paperSettings?: string): { env: string[]; out: string } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ensure-env-heat-'));
  try {
    const home = path.join(root, 'home'), dep = path.join(root, 'release', 'deploy');
    fs.mkdirSync(path.join(home, 'bot'), { recursive: true });
    fs.mkdirSync(dep, { recursive: true });
    fs.copyFileSync(script, path.join(dep, 'ensure-env.sh'));
    if (withInstaller) fs.writeFileSync(path.join(dep, 'heat_reader_install.sh'), '#!/usr/bin/env bash\nexit 0\n');
    if (paperSettings !== undefined) fs.writeFileSync(path.join(dep, 'paper-settings.env'), paperSettings);
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

// The paper bot's own settings (deploy/paper-settings.env, first the tennis two paper days, Nov 12): applied only while
// bot.env's TRADING_MODE is paper or not set, replacing any line of the same name; never under shadow or live.
const shipped = fs.readFileSync(path.resolve('deploy/paper-settings.env'), 'utf8');
const shippedLines = shipped.split('\n').filter((l) => /^[A-Z][A-Z0-9_]*=/.test(l));

test('ensure-env: the shipped paper settings are the tennis two paper days, and TENNIS_LIVE is not among them', () => {
  assert.deepEqual(shippedLines, ['TENNIS_CONF_MOMENTUM_CENTS=0.02', 'TENNIS_CONF_WINDOW_SEC=120', 'TENNIS_SERIES=KXATPMATCH,KXWTAMATCH']);
  assert.ok(!/^\s*(export\s+)?(TENNIS_LIVE|TRADING_MODE|LIVE_)/m.test(shipped), 'no live switch in the paper settings');
});

test('ensure-env: in paper the paper settings are written into bot.env, replacing a line of the same name; idempotent', () => {
  const { env, out } = runFrom(['TRADING_MODE=paper', 'TENNIS_SERIES=KXATPMATCH', 'PORT=3000'], false, shipped);
  assert.deepEqual(env, ['TRADING_MODE=paper', 'PORT=3000', ...shippedLines]);
  assert.match(out, /TENNIS_CONF_MOMENTUM_CENTS: \(not set\) -> 0\.02 in .* \(paper settings\)/);
  assert.match(out, /TENNIS_SERIES: KXATPMATCH -> KXATPMATCH,KXWTAMATCH/);
  const again = runFrom(env, false, shipped);
  assert.deepEqual(again.env, env, 'idempotent');
  assert.doesNotMatch(again.out, /paper settings/);
});

test('ensure-env: with no TRADING_MODE line (the bot defaults to paper) or a quoted PAPER, the paper settings apply', () => {
  assert.deepEqual(runFrom(['PORT=3000'], false, 'A_KEY=1\n').env, ['PORT=3000', 'A_KEY=1']);
  assert.deepEqual(runFrom(['TRADING_MODE="PAPER"'], false, 'A_KEY=1\n').env, ['TRADING_MODE="PAPER"', 'A_KEY=1']);
  // Spaces, an `export ` in front and duplicates of the name are all replaced by the one line; a longer name is not it.
  const { env } = runFrom(['export A_KEY=0', '  A_KEY = 2', 'A_KEY_X=5', 'PORT=3000'], false, 'A_KEY=1');
  assert.deepEqual(env, ['A_KEY_X=5', 'PORT=3000', 'A_KEY=1']);
});

test('ensure-env: under live or shadow the paper settings are not applied and nothing is removed', () => {
  for (const mode of ['live', 'shadow', 'export TRADING_MODE=live']) {
    const line = mode.includes('=') ? mode : `TRADING_MODE=${mode}`;
    const lines = [line, 'TENNIS_SERIES=KXATPMATCH', 'TENNIS_CONF_WINDOW_SEC=60'];
    const { env, out } = runFrom(lines, false, shipped);
    assert.deepEqual(env, lines, mode);
    assert.match(out, /paper-settings\.env not applied: TRADING_MODE=(live|shadow)/);
  }
});

test('ensure-env: a paper settings line that is not a plain KEY=VALUE is skipped with a warning', () => {
  const { env, out } = runFrom(['TRADING_MODE=paper'], false, '# note\n\nexport B=1\nC = 2\nD="x"\nlower=1\nE=ok\n');
  assert.deepEqual(env, ['TRADING_MODE=paper', 'E=ok']);
  assert.equal((out.match(/warning: skipped a line/g) ?? []).length, 4, out);
});
