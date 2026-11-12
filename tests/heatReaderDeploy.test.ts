// The heat curve reader on the server: deploy/activate.sh and deploy/rollback.sh make it follow the release they put
// in place (deploy/heat_reader_follow.sh), and the Server diagnostics report prints its state. Run against a scratch
// HOME with stand-ins for sudo, systemctl, journalctl, curl and sleep; the reader's installer is a stand-in too.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const REAL_SLEEP = execFileSync('bash', ['-c', 'command -v sleep'], { encoding: 'utf8' }).trim();
const SCRIPTS = ['activate.sh', 'ensure-env.sh', 'kalshi-bot.service', 'rollback.sh', 'https.sh', 'heat_reader_follow.sh'];

// Stand-in installers: each logs where it ran from and where ~/bot/current pointed at the time.
const installer = (body: string) => `#!/usr/bin/env bash
echo "heat-reader: stand-in installer"
echo "$(cd "$(dirname "$0")/.." && pwd) current=$(readlink "$HOME/bot/current")" >> "$HOME/installer.log"
${body}
`;
// FAILS stops at its checks before it touches the unit, as the real installer's die() does.
const OK = installer('exit 0'), FAILS = installer('echo "heat-reader: no traded_pack.json"; exit 1'), HANGS = installer(`exec ${REAL_SLEEP} 30`);
const STOPPED = ' heat-reader.service is stopped and disabled until an install succeeds.';
const DISABLE = 'sudo systemctl disable --now heat-reader';

function server(t: { after: (fn: () => void) => void }) {
  const home = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'heat-deploy-')));
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const bin = path.join(home, 'stub-bin'), units = path.join(home, 'units'), calls = path.join(home, 'calls.log');
  for (const d of [bin, units, path.join(home, 'bot')]) fs.mkdirSync(d, { recursive: true });
  const stub = (name: string, body: string) => fs.writeFileSync(path.join(bin, name), `#!/bin/bash\n${body}\n`, { mode: 0o755 });
  stub('sudo', 'echo "sudo $*" >> "$CALLS"; exit 0');
  stub('systemctl', 'echo "systemctl $*" >> "$CALLS"; case "$1" in show) echo running;; esac; exit 0');
  stub('journalctl', 'exit 0');
  stub('curl', 'printf 200');
  stub('sleep', 'exit 0');
  fs.writeFileSync(path.join(home, 'bot/bot.env'), 'TRADING_MODE=paper\nHTTPS=off\nHEAT_LANE=true\n');
  const release = (name: string, install?: string) => {
    const rel = path.join(home, 'releases', name), dir = path.join(rel, 'deploy');
    fs.mkdirSync(dir, { recursive: true });
    for (const f of SCRIPTS) fs.copyFileSync(path.resolve('deploy', f), path.join(dir, f));
    if (install !== undefined) fs.writeFileSync(path.join(dir, 'heat_reader_install.sh'), install, { mode: 0o755 });
    return rel;
  };
  const run = (script: string, args: string[], extra: Record<string, string> = {}) => {
    const t0 = Date.now();
    const r = spawnSync('bash', [script, ...args], { cwd: home, encoding: 'utf8', timeout: 60_000,
      env: { PATH: `${bin}:${path.dirname(process.execPath)}:${process.env.PATH}`, HOME: home, CALLS: calls, HEAT_READER_UNIT_DIR: units, ...extra } });
    return { ...r, ms: Date.now() - t0 };
  };
  const read = (f: string) => (fs.existsSync(f) ? fs.readFileSync(f, 'utf8').split('\n').filter(Boolean) : []);
  return {
    home, release, run, units,
    calls: () => read(calls),
    installs: () => read(path.join(home, 'installer.log')),
    link: (name: 'current' | 'previous') => fs.readlinkSync(path.join(home, 'bot', name)),
    unitInstalled: () => fs.writeFileSync(path.join(units, 'heat-reader.service'), '[Unit]\n'),
  };
}

// activate.sh as the deploy runs it: a live release (old), and the new one going in.
function activate(t: { after: (fn: () => void) => void }, install?: string, extra: Record<string, string> = {}, unit = false) {
  const s = server(t);
  const old = s.release('old');
  fs.symlinkSync(old, path.join(s.home, 'bot/current'));
  const rel = s.release('new', install);
  if (unit) s.unitInstalled();
  const r = s.run(path.join(rel, 'deploy/activate.sh'), [rel], extra);
  return { s, r, rel, old, heat: r.stdout.split('\n').filter((l) => l.startsWith('heat reader:')) };
}

// The bot went in and stayed in: no rollback, one restart, the reader step after HTTPS.
function deployed(o: ReturnType<typeof activate>) {
  assert.equal(o.r.status, 0, o.r.stdout + o.r.stderr);
  assert.match(o.r.stdout, new RegExp(`activated ${o.rel} \\(dashboard HTTP 200\\)`));
  assert.equal(o.s.link('current'), o.rel); assert.equal(o.s.link('previous'), o.old);
  assert.deepEqual(o.s.calls().filter((c) => c.includes('restart kalshi-bot')), ['sudo systemctl restart kalshi-bot']);
  assert.doesNotMatch(o.r.stdout, /rolling back|rolled back/);
  const https = o.r.stdout.indexOf('https: off');
  assert.ok(https > o.r.stdout.indexOf('activated '), 'HTTPS after the bot is up');
  for (const l of o.heat) assert.ok(o.r.stdout.indexOf(l) > https, 'the reader after HTTPS');
}

test('activate: the release ships the installer and it succeeds: it runs once the bot is up, against the new release', (t) => {
  const o = activate(t, OK);
  deployed(o);
  assert.deepEqual(o.s.installs(), [`${o.rel} current=${o.rel}`]);
  assert.match(o.r.stdout, /heat-reader: stand-in installer/);
  assert.deepEqual(o.heat, [], 'nothing more to say');
  assert.ok(o.r.stdout.indexOf('heat-reader: stand-in installer') > o.r.stdout.indexOf('https: off'));
});

test('activate: the installer exits 1: one line says the reader is not running and why, the deploy goes on', (t) => {
  let o = activate(t, FAILS);
  deployed(o);
  assert.equal(o.s.installs().length, 1);
  assert.deepEqual(o.heat, ['heat reader: NOT running: heat_reader_install.sh exited 1 (the heat-reader lines above say why). The bot is not affected.']);
  assert.equal(o.s.calls().some((c) => c.includes('heat-reader')), false, 'no unit: nothing to stop');
  // A reader installed by an earlier release: the installer died at its checks without touching it, so the step stops
  // and disables it. The line is then true, and no reader runs an earlier release's code and packs beside this bot.
  o = activate(t, FAILS, {}, true);
  deployed(o);
  assert.deepEqual(o.heat, [`heat reader: NOT running: heat_reader_install.sh exited 1 (the heat-reader lines above say why).${STOPPED} The bot is not affected.`]);
  assert.deepEqual(o.s.calls().filter((c) => c.includes('heat-reader')), [DISABLE]);
  // A success leaves the unit to the installer.
  o = activate(t, OK, {}, true);
  deployed(o);
  assert.equal(o.s.calls().some((c) => c.includes('heat-reader')), false);
});

test('activate: an installer that does not finish is cut off at its bound and the deploy goes on', (t) => {
  let o = activate(t, HANGS, { HEAT_READER_INSTALL_TIMEOUT: '1' });
  deployed(o);
  assert.equal(o.heat.length, 1); assert.match(o.heat[0], /^heat reader: NOT running: heat_reader_install\.sh did not finish within 1 s \(exit 124\)\. The bot is not affected;/);
  assert.ok(o.r.ms < 20_000, `${o.r.ms} ms`);
  // Cut off mid-build with the unit installed: disabled, so a reboot cannot start it on a half-built venv.
  o = activate(t, HANGS, { HEAT_READER_INSTALL_TIMEOUT: '1' }, true);
  deployed(o);
  assert.equal(o.heat.length, 1); assert.ok(o.heat[0].includes(`(exit 124).${STOPPED} The bot is not affected;`), o.heat[0]);
  assert.deepEqual(o.s.calls().filter((c) => c.includes('heat-reader')), [DISABLE]);
});

test('activate: the installer (pip with it) runs with oom_score_adj 1000; the bot\'s side keeps its own', { skip: !fs.existsSync('/proc/self/oom_score_adj') && 'needs Linux /proc' }, (t) => {
  const base = fs.readFileSync('/proc/self/oom_score_adj', 'utf8').trim();
  const s = server(t);
  const oom = 'read -r a < /proc/self/oom_score_adj; echo "$a" >> "$HOME/$1.oom"';
  fs.writeFileSync(path.join(s.home, 'stub-bin/sudo'), `#!/bin/bash\necho "sudo $*" >> "$CALLS"\n${oom.replace('$1', 'sudo')}\nexit 0\n`, { mode: 0o755 });
  const old = s.release('old');
  fs.symlinkSync(old, path.join(s.home, 'bot/current'));
  const rel = s.release('new', installer(`${oom.replace('$1', 'installer')}\n( ${oom.replace('$1', 'pip')} )\nexit 1`));
  s.unitInstalled();
  const r = s.run(path.join(rel, 'deploy/activate.sh'), [rel]);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const read = (n: string) => fs.readFileSync(path.join(s.home, `${n}.oom`), 'utf8').split('\n').filter(Boolean);
  assert.deepEqual(read('installer'), ['1000']); assert.deepEqual(read('pip'), ['1000']);
  // Every sudo call, the bot's restart and the reader's stop after the failure among them, ran at the deploy's own score.
  assert.ok(s.calls().includes('sudo systemctl restart kalshi-bot') && s.calls().includes(DISABLE));
  assert.deepEqual([...new Set(read('sudo'))], [base]);
});

test('activate: a release without the installer prints one line and goes on (stopping a reader left installed)', (t) => {
  let o = activate(t);
  deployed(o);
  assert.deepEqual(o.s.installs(), []);
  assert.deepEqual(o.heat, [`heat reader: ${o.rel}/deploy has no heat_reader_install.sh: nothing to install`]);
  assert.equal(o.s.calls().some((c) => c.includes('heat-reader')), false);
  // The reader runs from ~/bot/current: a release without it cannot run it, so an installed reader is stopped.
  o = activate(t, undefined, {}, true);
  deployed(o);
  assert.deepEqual(o.heat, [`heat reader: ${o.rel}/deploy has no heat_reader_install.sh: the reader is stopped and disabled (this release does not carry it)`]);
  assert.ok(o.s.calls().includes('sudo systemctl disable --now heat-reader'));
});

test('activate: a release whose bot does not come up rolls back before the reader step, and the reader follows the old release', (t) => {
  const s = server(t);
  const old = s.release('old', OK);
  fs.symlinkSync(old, path.join(s.home, 'bot/current'));
  const rel = s.release('new', OK);
  // The dashboard never answers and the service is down.
  fs.writeFileSync(path.join(s.home, 'stub-bin/curl'), '#!/bin/bash\nprintf 000\n', { mode: 0o755 });
  fs.writeFileSync(path.join(s.home, 'stub-bin/systemctl'), '#!/bin/bash\necho "systemctl $*" >> "$CALLS"; case "$1" in is-active) exit 3;; show) echo failed;; esac; exit 0\n', { mode: 0o755 });
  const r = s.run(path.join(rel, 'deploy/activate.sh'), [rel]);
  assert.equal(r.status, 1);
  assert.match(r.stdout, /service is not running; rolling back/); assert.match(r.stdout, new RegExp(`rolled back to ${old}`));
  assert.equal(s.link('current'), old);
  assert.deepEqual(s.installs(), [`${old} current=${old}`], 'only the old release\'s installer, after the switch back');
});

// rollback.sh as documented: bash ~/bot/current/deploy/rollback.sh, with B live and A before it.
function rollback(t: { after: (fn: () => void) => void }, install?: string, unit = false) {
  const s = server(t);
  const a = s.release('A', install), b = s.release('B', OK);
  fs.symlinkSync(b, path.join(s.home, 'bot/current')); fs.symlinkSync(a, path.join(s.home, 'bot/previous'));
  if (unit) s.unitInstalled();
  const r = s.run(path.join(s.home, 'bot/current/deploy/rollback.sh'), []);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, new RegExp(`rolled back to ${a}\n`));
  assert.equal(s.link('current'), a); assert.equal(s.link('previous'), b);
  assert.ok(s.calls().includes('sudo systemctl restart kalshi-bot'));
  return { s, r, a, b, heat: r.stdout.split('\n').filter((l) => l.startsWith('heat reader:')) };
}

test('rollback: the reader follows the release now current: its installer runs after the switch', (t) => {
  const o = rollback(t, OK);
  assert.deepEqual(o.s.installs(), [`${o.a} current=${o.a}`]);
  assert.deepEqual(o.heat, []);
  assert.ok(o.r.stdout.indexOf('heat-reader: stand-in installer') > o.r.stdout.indexOf('rolled back to'));
});

test('rollback: an installer that fails never fails the rollback, and the reader of the release rolled back from is stopped', (t) => {
  let o = rollback(t, FAILS);
  assert.equal(o.s.installs().length, 1);
  assert.deepEqual(o.heat, ['heat reader: NOT running: heat_reader_install.sh exited 1 (the heat-reader lines above say why). The bot is not affected.']);
  assert.equal(o.s.calls().some((c) => c.includes('heat-reader')), false);
  // B's reader is installed and running: A's installer dies at its checks, so B's reader is stopped and disabled
  // rather than left running B's code beside A's bot.
  o = rollback(t, FAILS, true);
  assert.deepEqual(o.s.installs(), [`${o.a} current=${o.a}`]);
  assert.deepEqual(o.heat, [`heat reader: NOT running: heat_reader_install.sh exited 1 (the heat-reader lines above say why).${STOPPED} The bot is not affected.`]);
  assert.deepEqual(o.s.calls().filter((c) => c.includes('heat-reader')), [DISABLE]);
  assert.ok(o.s.calls().indexOf(DISABLE) > o.s.calls().indexOf('sudo systemctl restart kalshi-bot'));
});

test('rollback: to a release without the reader, an installed reader is stopped and disabled; with none installed nothing is done', (t) => {
  let o = rollback(t, undefined, true);
  assert.deepEqual(o.s.installs(), []);
  assert.ok(o.s.calls().includes('sudo systemctl disable --now heat-reader'));
  assert.deepEqual(o.heat, [`heat reader: ${o.a}/deploy has no heat_reader_install.sh: the reader is stopped and disabled (this release does not carry it)`]);
  o = rollback(t);
  assert.equal(o.s.calls().some((c) => c.includes('heat-reader')), false);
  assert.deepEqual(o.heat, [`heat reader: ${o.a}/deploy has no heat_reader_install.sh: nothing to install`]);
});

// The "== heat reader" section of the Server diagnostics report (.github/workflows/diagnose.yml, job diagnose).
function heatSection(): string {
  const lines = fs.readFileSync('.github/workflows/diagnose.yml', 'utf8').split('\n');
  const start = lines.findIndex((l) => /^ +echo "== heat reader/.test(l));
  assert.ok(start > 0, 'diagnose.yml has a heat reader section');
  const end = lines.findIndex((l, i) => i > start && /^ +echo "== /.test(l));
  const indent = lines[start].length - lines[start].trimStart().length;
  return lines.slice(start, end).map((l) => l.slice(indent)).join('\n') + '\n';
}

const SECRETS = 'TRADING_MODE=paper\nDASHBOARD_PASSWORD=hunter2-dashboard\nKALSHI_KEY_ID=key-id-123\nKALSHI_PRIVATE_KEY_PATH=/home/x/.kalshi/pk.pem\n';

/**
 * Runs the section on a scratch server. botEnv: ~/bot/bot.env (__HOME__ stands for the scratch HOME); loaded: the
 * heat-reader unit is installed; status: the status file, as [path under HOME, text].
 */
function diagnose(t: { after: (fn: () => void) => void }, botEnv: string | null, o: { loaded?: boolean; status?: [string, string] } = {}) {
  const s = server(t);
  const envFile = path.join(s.home, 'bot/bot.env');
  if (botEnv === null) fs.rmSync(envFile); else fs.writeFileSync(envFile, botEnv.replace(/__HOME__/g, s.home));
  fs.writeFileSync(path.join(s.home, 'stub-bin/systemctl'), `#!/bin/bash
case "$*" in
  "show heat-reader -p LoadState --value") echo ${o.loaded ? 'loaded' : 'not-found'};;
  "is-enabled heat-reader") echo enabled;;
  "is-active heat-reader") echo active;;
  "show heat-reader -p NRestarts -p ActiveEnterTimestamp -p MemoryCurrent -p MemoryPeak") printf 'NRestarts=3\\nActiveEnterTimestamp=Wed 2026-11-11 13:00:00 UTC\\nMemoryCurrent=94371840\\nMemoryPeak=[not set]\\n';;
  *) echo "unexpected systemctl $*" >&2; exit 1;;
esac
`, { mode: 0o755 });
  fs.writeFileSync(path.join(s.home, 'stub-bin/journalctl'), '#!/bin/bash\necho "heat-reader pass BTC 2 fired in 1.2 s | ETH NOT OK: stale (3.1 s)"\n', { mode: 0o755 });
  const file = o.status ? path.join(s.home, o.status[0]) : '';
  if (o.status) { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, o.status[1]); }
  const script = path.join(s.home, 'section.sh');
  fs.writeFileSync(script, heatSection());
  const r = s.run(script, []);
  assert.equal(r.status, 0); assert.equal(r.stderr, '', 'no errors printed');
  // Of bot.env only HEAT_LANE and HEAT_CALLS_FILE.
  for (const secret of ['hunter2-dashboard', 'key-id-123', '/home/x/.kalshi/pk.pem', 'TRADING_MODE']) assert.ok(!r.stdout.includes(secret), `${secret} printed`);
  return { home: s.home, file, out: r.stdout, lines: r.stdout.split('\n') };
}

test('diagnose: with no reader installed and no status file the heat reader section says so, without errors', (t) => {
  const { home, out } = diagnose(t, SECRETS);
  assert.equal(out, `== heat reader (curve reader beside the bot; runs only with HEAT_LANE=true in bot.env)
HEAT_LANE not set in bot.env (off)
unit: not installed
status file: none at ${home}/bot/data/heat_calls.status.json
`);
  // No bot.env at all: the same, still without errors.
  assert.match(diagnose(t, null).out, /HEAT_LANE not set in bot\.env \(off\)\nunit: not installed\nstatus file: none at /);
});

test('diagnose: a running reader shows its unit, memory, log tail and the status file\'s age and short fields', (t) => {
  const status = {
    v: 1, writtenAt: Date.now() - 42_000, run: 'fd88805', packSha: 'a'.repeat(64), maxRank: 50, clockPack: false,
    packs: { 'traded_pack.json': { sha: 'b'.repeat(64), rows: 1200, schema: 'heat-pack-1' } },
    coins: { BTC: { ok: true, fired: { single: 2, pair: 1 }, rows: { wanted: { single: 400 } } }, ETH: { ok: false, fired: {}, why: 'stale '.repeat(100) } },
  };
  // HEAT_CALLS_FILE names its own path (quoted): the status file is beside it, .json -> .status.json.
  const env = `${SECRETS}HEAT_LANE=true\nHEAT_CALLS_FILE="__HOME__/bot/data/calls/heat.json"\nHEAT_LANE_X=other-value\n`;
  const { file, out, lines } = diagnose(t, env, { loaded: true, status: ['bot/data/calls/heat.status.json', JSON.stringify(status)] });
  assert.ok(lines.includes('HEAT_LANE=true'));
  assert.ok(lines.some((l) => /^HEAT_CALLS_FILE=".*\/bot\/data\/calls\/heat\.json"$/.test(l)));
  assert.doesNotMatch(out, /HEAT_LANE_X|other-value/);
  assert.ok(lines.includes('unit: installed, enabled, active'));
  assert.ok(lines.includes('NRestarts=3')); assert.ok(lines.includes('MemoryCurrent=90 MB')); assert.ok(lines.includes('MemoryPeak=[not set]'));
  assert.ok(lines.includes('heat-reader pass BTC 2 fired in 1.2 s | ETH NOT OK: stale (3.1 s)'));
  const head = lines.find((l) => l.startsWith('status file: ')) ?? '';
  assert.ok(head.startsWith(`status file: ${file} | age `), head);
  const written = Number(/written (\d+) s ago/.exec(head)?.[1]);
  assert.ok(written >= 41 && written <= 60, head);
  assert.match(head, /\| keys clockPack,coins,maxRank,packSha,packs,run,v,writtenAt$/);
  for (const l of ['  run: "fd88805"', '  maxRank: 50', '  clockPack: false', '  coin BTC: ok true | fired {"single": 2, "pair": 1} | why null']) assert.ok(lines.includes(l), l);
  const eth = lines.find((l) => l.startsWith('  coin ETH: ok false')) ?? '';
  assert.ok(eth && eth.length < 200, eth);
  // The pack table is not printed, only its key; every line is short and the section is a few lines.
  assert.doesNotMatch(out, /heat-pack-1|b{64}/);
  for (const l of lines) assert.ok(l.length <= 260, l);
  assert.ok(lines.length < 25, `${lines.length} lines`);
});

test('diagnose: a status file that is not JSON is reported, not an error', (t) => {
  const { file, out } = diagnose(t, 'HEAT_LANE=false\n', { status: ['bot/data/heat_calls.status.json', '{"v": 1, "coins": '] });
  assert.match(out, /^HEAT_LANE=false$/m);
  assert.match(out, new RegExp(`^status file: ${file} \\| age \\d+ s \\| not JSON: JSONDecodeError$`, 'm'));
});
