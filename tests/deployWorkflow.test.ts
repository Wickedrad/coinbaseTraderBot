import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, spawnSync } from 'node:child_process';

// The deploy job's steps, cut out of deploy.yml by indentation (the repo has no YAML library).
function deploySteps() {
  const lines = fs.readFileSync('.github/workflows/deploy.yml', 'utf8').split('\n');
  const chunks: string[][] = [];
  for (const line of lines.slice(lines.findIndex((l) => l === '    steps:') + 1)) {
    if (line.startsWith('      - ')) chunks.push([]);
    chunks.at(-1)?.push(line);
  }
  return chunks.map((chunk) => {
    const name = chunk.map((l) => /^      (?:- | {2})name: (.*)$/.exec(l)?.[1]).find(Boolean) ?? '';
    const at = chunk.findIndex((l) => l === '          script: |');
    const body: string[] = [];
    if (at >= 0) for (const l of chunk.slice(at + 1)) { if (l.trim() && !l.startsWith(' '.repeat(12))) break; body.push(l.slice(12)); }
    return { name, text: chunk.join('\n'), script: body.join('\n').trimEnd() + '\n' };
  });
}
const PRE = 'Verify paper mode before deploying this release';
const POST = 'Verify running paper process';
const step = (name: string) => {
  const s = deploySteps().find((x) => x.name === name);
  assert.ok(s, `deploy.yml step "${name}"`);
  return s;
};
// drone-ssh reads script_stop as a Go bool ("true", "True", "1", "t", quoted or not): anything but an explicit false counts as on.
const scriptStop = (text: string) => {
  const m = /^\s*script_stop:(.*)$/m.exec(text);
  return !!m && !/^\s*['"]?(false|f|0)['"]?\s*(#.*)?$/i.test(m[1]);
};
// The script as drone-ssh 1.7.3 (inside appleboy/ssh-action@v1.0.3) runs it on the server. With script_stop it splits the
// script into lines, trims each, drops blank ones and adds this exit-code line after every line not ending in a backslash.
const STOP_LINE = 'DRONE_SSH_PREV_COMMAND_EXIT_CODE=$? ; if [ $DRONE_SSH_PREV_COMMAND_EXIT_CODE -ne 0 ]; then exit $DRONE_SSH_PREV_COMMAND_EXIT_CODE; fi;';
const delivered = (s: { text: string; script: string }) => !scriptStop(s.text) ? s.script.trim()
  : s.script.split('\n').map((l) => l.trim()).filter(Boolean).flatMap((l) => (l.endsWith('\\') ? [l] : [l, STOP_LINE])).join('\n');

test('deploy: ssh steps that run a heredoc do not use script_stop and stop on the first failure with set -e', () => {
  const heredocs = deploySteps().filter((s) => /uses: appleboy\/ssh-action@/.test(s.text) && /<<-?\s*['"]?\w+/.test(s.script));
  assert.ok(heredocs.some((s) => s.name === PRE) && heredocs.some((s) => s.name === POST), heredocs.map((s) => s.name).join(', '));
  for (const s of heredocs) {
    // script_stop puts an exit-code shell line after every script line, inside the heredoc too: the Python is a SyntaxError.
    assert.equal(scriptStop(s.text), false, s.name);
    assert.equal(s.script.split('\n')[0], 'set -euo pipefail', s.name);
    assert.equal(spawnSync('bash', ['-n'], { input: s.script }).status, 0, s.name);
  }
});

test('deploy: the paper_only pre-deploy check passes for paper and blocks any other configured mode', (t) => {
  const s = step(PRE);
  assert.match(s.text, /if: inputs\.paper_only/);
  const home = fs.mkdtempSync(path.join(os.tmpdir(), 'deploy-guard-')); t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  fs.mkdirSync(path.join(home, 'bot'));
  const run = (env: string | null) => {
    const file = path.join(home, 'bot/bot.env');
    if (env === null) fs.rmSync(file, { force: true }); else fs.writeFileSync(file, env);
    return spawnSync('bash', ['-c', delivered(s)], { env: { ...process.env, HOME: home }, encoding: 'utf8' });
  };
  for (const env of ['KALSHI_ENV=demo\nTRADING_MODE=paper\n', 'TRADING_MODE="paper"\n', '# TRADING_MODE=live\nTRADING_MODE=paper\n', null]) {
    const r = run(env);
    assert.equal(r.status, 0, `${env}: ${r.stderr}`); assert.match(r.stdout, /Verified configured TRADING_MODE=paper/);
  }
  for (const env of ['TRADING_MODE=live\n', 'TRADING_MODE=paper\nTRADING_MODE=live\n', 'TRADING_MODE=shadow\n']) {
    const r = run(env);
    assert.notEqual(r.status, 0, env); assert.match(r.stderr, /Deployment blocked/);
  }
});

test('deploy: the paper_only post-activation check needs an active service running in paper mode', { skip: process.platform !== 'linux' && 'reads /proc' }, async (t) => {
  const s = step(POST);
  assert.match(s.text, /if: inputs\.paper_only/);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'deploy-guard-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  // A stand-in systemctl: is-active follows FAKE_ACTIVE, show prints the stand-in bot's pid.
  fs.writeFileSync(path.join(dir, 'systemctl'), '#!/bin/bash\ncase "$1" in is-active) [ "$FAKE_ACTIVE" = 1 ];; show) echo "$FAKE_PID";; *) exit 2;; esac\n', { mode: 0o755 });
  const run = async (mode: string | null, active: boolean) => {
    const bot = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 30000)'], { env: mode === null ? {} : { TRADING_MODE: mode }, stdio: 'ignore' });
    try {
      await new Promise((resolve) => bot.once('spawn', resolve));
      return spawnSync('bash', ['-c', delivered(s)], { env: { ...process.env, PATH: `${dir}:${process.env.PATH}`, FAKE_PID: String(bot.pid), FAKE_ACTIVE: active ? '1' : '0' }, encoding: 'utf8' });
    } finally { bot.kill(); }
  };
  let r = await run('paper', true); assert.equal(r.status, 0, r.stderr); assert.match(r.stdout, /Verified active kalshi-bot process in paper mode/);
  r = await run(null, true); assert.equal(r.status, 0, r.stderr);
  r = await run('live', true); assert.notEqual(r.status, 0); assert.match(r.stderr, /not in paper mode/);
  // An inactive service fails the step even though the process it last named is in paper mode (set -e).
  r = await run('paper', false); assert.notEqual(r.status, 0); assert.doesNotMatch(r.stdout, /Verified/);
});
