import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, spawnSync } from 'node:child_process';
import { buildRuns, bundleInputs, chooseBase, decide, HEAT_SHIP, heatShipped, researchOnly, stageHeat } from '../deploy/deploy-scope';

// One job's steps, cut out of deploy.yml by indentation (the repo has no YAML library), with the bodies of their
// `script: |` (ssh-action) and `run: |` blocks.
function jobSteps(job: string) {
  const lines = fs.readFileSync('.github/workflows/deploy.yml', 'utf8').split('\n');
  const start = lines.indexOf(`  ${job}:`);
  assert.ok(start >= 0, `deploy.yml job "${job}"`);
  const end = lines.findIndex((l, i) => i > start && /^  \S/.test(l));
  const jobLines = lines.slice(start, end < 0 ? undefined : end);
  const chunks: string[][] = [];
  for (const line of jobLines.slice(jobLines.indexOf('    steps:') + 1)) {
    if (line.startsWith('      - ')) chunks.push([]);
    chunks.at(-1)?.push(line);
  }
  const block = (chunk: string[], key: string) => {
    const at = chunk.findIndex((l) => new RegExp(`^ +${key}: \\|$`).test(l));
    if (at < 0) return '\n';
    const indent = chunk[at].indexOf(key) + 2;
    const body: string[] = [];
    for (const l of chunk.slice(at + 1)) { if (l.trim() && !l.startsWith(' '.repeat(indent))) break; body.push(l.slice(indent)); }
    return body.join('\n').trimEnd() + '\n';
  };
  return chunks.map((chunk) => {
    const name = chunk.map((l) => /^      (?:- | {2})name: (.*)$/.exec(l)?.[1]).find(Boolean) ?? '';
    return { name, text: chunk.join('\n'), script: block(chunk, 'script'), run: block(chunk, 'run') };
  });
}
const deploySteps = () => jobSteps('deploy');
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

// Pushes deploy by what they change, not by "[skip deploy]" (Steven, Nov 11, 8:18 AM EST / 13:18 UTC: merges that touch
// no bot code may skip the deploy and restart; every merge that changes bot code gets its own logged deploy).
const BUNDLED = new Set(['bot/main.ts', 'bot/engine.ts', 'research/pipeline.ts', 'research/replay.ts', 'bot/kalshi/feeScheduleSnapshot.json']);
const push = (files: string[], message = 'Merge (#9)', bundled: ReadonlySet<string> | null = BUNDLED, deleted: ReadonlySet<string> = new Set()) =>
  decide({ event: 'push', files, deleted, bundled, message });

test('deploy scope: research-only pushes skip, anything that reaches the server deploys', () => {
  for (const files of [['python/allpairs/run.py'], ['docs/DEPLOY.md', 'docs/OPPORTUNITY_ATLAS_ORACLE_VALIDATION.json', 'README.md'], ['tests/engine.test.ts'],
    ['.github/workflows/atlas-research.yml', '.github/scripts/ai_review.py'], ['OPPORTUNITY_ATLAS_DIRECTION_VALIDATION.json', 'OPPORTUNITY_ATLAS_DIRECTION_ITERATIONS.md'],
    ['research/btcd_fractal/out10/results.json', 'research/btcd_fractal/data/M2_1d.csv', 'research/btcd_fractal/study.py', 'research/btcd_fractal/ROUND9_PLAN.md'],
    ['research/study.ipynb', 'notebooks/a.ipynb', 'research/out/atlas/product.json', 'packaging/windows/Train.cmd']]) {
    const d = push(files);
    assert.equal(d.deploy, false, files.join(', ')); assert.equal(d.why, 'research-only'); assert.deepEqual(d.research, files);
    // These need no bundle check.
    assert.equal(push(files, 'x', null).deploy, false, files.join(', '));
  }
  for (const file of ['bot/engine.ts', 'bot/kalshi/feeScheduleSnapshot.json', 'research/pipeline.ts', 'package-lock.json', 'package.json', 'tsconfig.json',
    '.github/workflows/deploy.yml', 'deploy/install.sh', 'deploy/deploy-scope.ts', 'params/ta_net.json', 'vendor/talib/src/ta_func/ta_RSI.c',
    'web/src/App.tsx', 'web/index.html', 'scripts/mdc.ts', '.env.example', '.gitignore', 'bot/notes.ipynb', 'deploy/README.md']) {
    for (const bundled of [BUNDLED, null]) {
      const d = push([file], 'x', bundled);
      assert.equal(d.deploy, true, file); assert.deepEqual(d.bot, [file]);
    }
  }
  // Mixed research and bot code deploys, listing both.
  const mixed = push(['research/opportunity/atlas.ts', 'docs/SNN.md', 'bot/engine.ts', 'tests/engine.test.ts']);
  assert.equal(mixed.deploy, true); assert.deepEqual(mixed.bot, ['bot/engine.ts']); assert.deepEqual(mixed.research, ['research/opportunity/atlas.ts', 'docs/SNN.md', 'tests/engine.test.ts']);
});

test('deploy scope: research/ sources count as bot code unless the bundle check shows the release does not bundle them', () => {
  for (const file of ['research/opportunity/oracleEdge.ts', 'research/opportunity/examples/profit-policy.json', 'research/opportunity/requirements-tvdatafeed.txt', 'research/workerDev.mjs']) {
    assert.equal(push([file], 'x', BUNDLED).deploy, false, file);
    assert.equal(push([file], 'x', null).deploy, true, `${file} without the bundle check`);
  }
  // A bundled research file is bot code; so is any bundled file, even under an otherwise research-only path.
  assert.equal(push(['research/replay.ts']).deploy, true);
  for (const file of ['docs/fees.json', 'tests/fixture.json', 'python/snn/column.cu', 'research/out/table.json']) {
    assert.equal(researchOnly(file, new Set()), true, file);
    assert.equal(researchOnly(file, new Set([file])), false, `${file} once bundled`);
  }
});

test('deploy scope: build configuration beside the sources is bot code, though the bundle check never lists it', () => {
  // esbuild reads the nearest tsconfig.json and package.json for every bundled file (useDefineForClassFields,
  // sideEffects, module type, imports) and git checks the sources out through .gitattributes.
  for (const file of ['research/tsconfig.json', 'research/package.json', 'research/history/tsconfig.json', 'research/history/package.json',
    'research/tsconfig.build.json', 'research/jsconfig.json', 'research/.gitattributes', 'research/.npmrc', 'research/opportunity/package.json',
    'bot/tsconfig.json', 'web/package.json', '.gitattributes']) {
    for (const bundled of [BUNDLED, null]) {
      const d = push([file], 'x', bundled);
      assert.equal(d.deploy, true, file); assert.deepEqual(d.bot, [file]);
    }
  }
  // In the research-only trees it counts only above a file the release bundles.
  for (const file of ['python/package.json', 'docs/tsconfig.json', 'tests/fixtures/package.json', 'packaging/windows/.gitattributes', '.github/scripts/package.json']) {
    assert.equal(push([file]).deploy, false, file); assert.equal(push([file], 'x', null).deploy, false, file);
  }
  assert.equal(researchOnly('docs/package.json', new Set(['docs/fees.json'])), false);
  assert.equal(researchOnly('docs/package.json', new Set(['docsx/fees.json'])), true);
  // Other research/ JSON stays research-only once the bundle check has run.
  assert.equal(push(['research/opportunity/examples/package-policy.json']).deploy, false);
});

test('deploy scope: a deleted research/ source is bot code (the bundle check only sees HEAD)', () => {
  // The bundle check ran at HEAD, where the file is gone: an import that reached it may now resolve to another file
  // (research/historyLedger.ts deleted, research/historyLedger/index.ts bundled in its place).
  for (const file of ['research/historyLedger.ts', 'research/opportunity/oracleEdge.ts', 'research/opportunity/examples/profit-policy.json', 'research/workerDev.mjs']) {
    const d = push([file], 'x', BUNDLED, new Set([file]));
    assert.equal(d.deploy, true, file); assert.deepEqual(d.bot, [file]);
    assert.equal(researchOnly(file, BUNDLED, true), false, file);
    assert.equal(push([file], 'x', BUNDLED).deploy, false, `${file} changed, not deleted`);
  }
  // Deleting a file of the research-only list stays research-only: those never depend on the bundle check.
  for (const file of ['research/out/atlas/product.json', 'research/btcd_fractal/study.py', 'docs/SNN.md', 'python/a.py', 'tests/engine.test.ts']) {
    assert.equal(push([file], 'x', BUNDLED, new Set([file])).deploy, false, file);
  }
});

test('deploy scope: [skip deploy] no longer skips bot code; unknown changes and manual runs deploy', () => {
  const tagged = push(['bot/engine.ts', 'docs/SNN.md'], 'Research and a fix (#12) [skip deploy] [skip ci]');
  assert.equal(tagged.deploy, true); assert.equal(tagged.tagIgnored, true);
  const research = push(['docs/SNN.md'], 'Research (#13) [skip deploy]');
  assert.equal(research.deploy, false); assert.equal(research.tagIgnored, false);
  assert.equal(push(['bot/engine.ts']).tagIgnored, false);
  const unknown = decide({ event: 'push', files: null, bundled: null, message: 'x [skip deploy]', unknown: 'no earlier deploy' });
  assert.equal(unknown.deploy, true); assert.equal(unknown.tagIgnored, true); assert.match(unknown.why, /no earlier deploy/);
  assert.equal(decide({ event: 'workflow_dispatch', files: [], bundled: null, message: '' }).deploy, true);
  // Nothing differs from the last deploy: nothing to restart for.
  assert.deepEqual([push([]).deploy, push([]).why], [false, 'nothing changed']);
});

test('deploy scope: compares with the last deployed commit, else the previous head, else deploys', () => {
  const a = 'a'.repeat(40), b = 'b'.repeat(40), zero = '0'.repeat(40);
  const asked: string[] = [];
  const has = (known: string[]) => (sha: string) => { asked.push(sha); return known.includes(sha); };
  assert.deepEqual(chooseBase(a, b, has([a, b]), 'ok'), { sha: a, kind: 'the last deploy' });
  // The last deploy's commit is gone (force push): deploy rather than compare with something else.
  assert.equal(chooseBase(a, b, has([b]), 'ok').sha, null);
  assert.deepEqual(chooseBase('', b, has([b]), 'ok'), { sha: b, kind: 'the previous main head (no successful deploy found)' });
  for (const before of [zero, '', b]) assert.equal(chooseBase('', before, has([a]), 'ok').sha, null, before);
  // A failed lookup is not "no deploy found": the previous head would miss a bot change whose own deploy failed.
  for (const lookup of ['failed', '', 'OK']) {
    const r = chooseBase('', b, has([b]), lookup);
    assert.equal(r.sha, null, lookup); assert.match('why' in r ? r.why : '', /could not be looked up/);
  }
  asked.length = 0;
  assert.equal(chooseBase('--output=/tmp/x', '-p', has([]), 'ok').sha, null); assert.deepEqual(asked, [], 'never hands git an option');
});

test('deploy scope: the bundle check mirrors every esbuild run of npm run build', { skip: !fs.existsSync('node_modules/.bin/esbuild') && 'needs esbuild' }, () => {
  const scripts = JSON.parse(fs.readFileSync('package.json', 'utf8')).scripts as Record<string, string>;
  const runs = buildRuns(scripts);
  assert.ok(runs);
  const entries = new Set([...`${scripts['build:bot']} ${scripts['build:trainer']}`.matchAll(/esbuild (\S+)/g)].map((m) => m[1]));
  assert.deepEqual(new Set(runs.esbuild.map((a) => a[0])), entries);
  assert.deepEqual(runs.vite, ['web/vite.config.ts']);
  // A build step it cannot mirror turns the check off (research/ sources then count as bot code).
  assert.equal(buildRuns({ ...scripts, build: `${scripts.build} && cp research/opportunity/examples/paper-policy.json dist/` }), null);
  assert.equal(buildRuns({ ...scripts, build: 'npm run build:missing' }), null);
  assert.equal(buildRuns({ build: 'npm run a', a: 'npm run build' }), null);

  const inputs = bundleInputs(process.cwd(), path.resolve('node_modules/.bin/esbuild'));
  assert.ok(inputs);
  for (const f of [...entries, 'bot/kalshi/feeScheduleSnapshot.json', 'web/src/main.tsx', 'web/src/index.css', 'web/vite.config.ts']) assert.ok(inputs.has(f), f);
  const research = spawnSync('git', ['ls-files', 'research/*.ts', 'research/**/*.ts'], { encoding: 'utf8' }).stdout.split('\n').filter(Boolean);
  assert.ok(research.some((f) => !inputs.has(f)), 'some research/ sources stay out of the release');
});

test('deploy scope: no research-only path is part of the uploaded release or used by the deploy workflow', () => {
  const upload = step('Upload release to server');
  const sources = /source: "([^"]+)"/.exec(upload.text)?.[1].split(',') ?? [];
  assert.ok(sources.includes('dist') && sources.includes('deploy'), sources.join(','));
  for (const src of sources) for (const f of src.endsWith('.json') ? [src] : [`${src}/x.json`, `${src}/x.md`, `${src}/out/x.ipynb`, `${src}/data/x.csv`]) {
    assert.equal(researchOnly(f, null), false, f); assert.equal(researchOnly(f, new Set()), false, f);
  }
  // .github/ is research-only apart from deploy.yml: the workflow must not use a local action or script from it.
  assert.doesNotMatch(fs.readFileSync('.github/workflows/deploy.yml', 'utf8'), /\.\/\.github|\.github\/(scripts|actions)/);
});

// The heat curve reader runs beside the bot from the release (docs/HEAT_READER.md): its files ship and are bot code.
const HEAT_FILES = ['python/heat_reader/__init__.py', 'python/heat_reader/__main__.py', 'python/heat_reader/cli.py', 'python/heat_reader/requirements.txt',
  'python/heat_reader/CHECK_RUN', 'python/heat_reader/sub/part.py', 'python/oracle/__init__.py', 'python/oracle/heat_live.py', 'python/oracle/heat.py',
  'python/oracle/common.py', 'python/oracle/cut.py', 'python/oracle/requirements.txt', 'python/oracle/SPEC.md',
  'research/oracle_heat/latest/traded_pack.json', 'research/oracle_heat/latest/pair_pack.json', 'research/oracle_heat/latest/clock_pack.json',
  'research/oracle_heat/latest/live_meta.json', 'research/oracle_heat/latest/summary.json', 'research/oracle_heat/latest/RUN'];
// Beside them, research-only as before (python/ always; the rest of research/ once the bundle check ran).
const HEAT_NEIGHBOURS_PYTHON = ['python/heat_reader/tests/test_cli.py', 'python/heat_reader/tests/conftest.py', 'python/heat_reader/fixtures/traded_pack.json',
  'python/oracle/tests/test_heat_live.py', 'python/oracle/tests/__init__.py', 'python/oracle/prereg/OR-H1.md', 'python/heat_reader_old/cli.py',
  'python/oracle.py', 'python/oracles/heat.py', 'python/allpairs/run.py'];
const HEAT_NEIGHBOURS_RESEARCH = ['research/oracle_heat/latest/league_ta.csv.gz', 'research/oracle_heat/latest/league_direction.csv.gz',
  'research/oracle_heat/latest/league.md', 'research/oracle_heat/latest/viewer.json.gz', 'research/oracle_heat/latest/RUN.bak',
  'research/oracle_heat/latest/old/traded_pack.json', 'research/oracle_heat/long/summary.json', 'research/oracle_heat/parity/BTC/parity.json',
  'research/oracle_heat/parity/RUN', 'research/oracle_heat_latest/traded_pack.json'];

test('deploy scope: the heat reader set is bot code, changed or deleted; its neighbours keep their research-only classification', () => {
  for (const file of HEAT_FILES) {
    assert.equal(heatShipped(file), true, file);
    for (const bundled of [BUNDLED, null]) for (const deleted of [new Set<string>(), new Set([file])]) {
      const d = push([file], 'x', bundled, deleted);
      assert.equal(d.deploy, true, `${file} (${bundled ? 'bundle check' : 'no bundle check'}, ${deleted.size ? 'deleted' : 'changed'})`);
      assert.deepEqual(d.bot, [file]); assert.deepEqual(d.research, []);
    }
  }
  // python/ outside the set stays research-only in every case, deleted too.
  for (const file of HEAT_NEIGHBOURS_PYTHON) {
    assert.equal(heatShipped(file), false, file);
    for (const bundled of [BUNDLED, null]) for (const deleted of [new Set<string>(), new Set([file])]) {
      assert.equal(push([file], 'x', bundled, deleted).deploy, false, `${file} ${bundled ? '' : 'without the bundle check'} ${deleted.size ? 'deleted' : ''}`);
    }
  }
  // The rest of research/oracle_heat is research-only once the bundle check ran (the markdown always), as any research/ file.
  for (const file of HEAT_NEIGHBOURS_RESEARCH) {
    assert.equal(heatShipped(file), false, file);
    assert.equal(push([file], 'x', BUNDLED).deploy, false, file);
    assert.equal(researchOnly(file, BUNDLED), researchOnly(file.replace('research/oracle_heat', 'research/other_study'), BUNDLED), `${file} like any research/ file`);
    for (const deleted of [false, true]) for (const bundled of [BUNDLED, null]) {
      assert.equal(researchOnly(file, bundled, deleted), researchOnly(file.replace('research/oracle_heat', 'research/other_study'), bundled, deleted), `${file} unchanged`);
    }
  }
  assert.equal(push(['research/oracle_heat/latest/league.md'], 'x', null, new Set(['research/oracle_heat/latest/league.md'])).deploy, false);
  // An oracle run that rewrites the packs, the league tables and the engine's tests deploys, listing each side.
  const run = push(['research/oracle_heat/latest/traded_pack.json', 'research/oracle_heat/latest/league_ta.csv.gz', 'python/oracle/tests/test_heat.py', 'python/oracle/heat.py']);
  assert.equal(run.deploy, true);
  assert.deepEqual(run.bot, ['research/oracle_heat/latest/traded_pack.json', 'python/oracle/heat.py']);
  assert.deepEqual(run.research, ['research/oracle_heat/latest/league_ta.csv.gz', 'python/oracle/tests/test_heat.py']);
  // Only the reader's own tests changed: no deploy.
  assert.equal(push(['python/heat_reader/tests/test_cli.py', 'python/heat_reader/fixtures/pair_pack.json', 'python/oracle/prereg/OR-HM1.md']).deploy, false);
  // Each pattern lies in its folder, and nothing outside python/heat_reader, python/oracle and research/oracle_heat/latest ships.
  for (const h of HEAT_SHIP) assert.equal(HEAT_FILES.filter((f) => h.re.test(f)).every((f) => f.startsWith(`${h.dir}/`)), true, h.dir);
  assert.deepEqual(HEAT_SHIP.map((h) => h.dir), ['python/heat_reader', 'python/oracle', 'research/oracle_heat/latest']);
});

test('deploy workflow: a push deploys on the scope job, never on the message tag; manual runs always deploy', () => {
  const yaml = fs.readFileSync('.github/workflows/deploy.yml', 'utf8');
  const job = (name: string) => yaml.slice(yaml.indexOf(`\n  ${name}:\n`), yaml.indexOf('\n    steps:\n', yaml.indexOf(`\n  ${name}:\n`)));
  const deploy = job('deploy'), scope = job('scope');
  assert.match(deploy, /\n    needs: scope\n/);
  const cond = /\n    if: (.*)\n/.exec(deploy)?.[1] ?? '';
  assert.equal(cond, "${{ !cancelled() && (github.event_name == 'workflow_dispatch' || (vars.AUTO_DEPLOY != 'false' && needs.scope.outputs.deploy != 'false')) }}");
  assert.doesNotMatch(cond, /skip deploy|head_commit/);
  assert.match(scope, /deploy: \$\{\{ steps\.scope\.outputs\.deploy \}\}/); assert.match(scope, /prev: \$\{\{ steps\.prev\.outputs\.prev \}\}/);
  // The scope job never touches the server: no secrets, no environment.
  const scopeAll = yaml.slice(yaml.indexOf('\n  scope:\n'), yaml.indexOf('\n  deploy:\n'));
  assert.doesNotMatch(scopeAll, /secrets\.|environment:|ssh-action|scp-action/);
  assert.match(step('Merges this deploy brings').text, /PREV: \$\{\{ needs\.scope\.outputs\.prev \}\}/);
  // The deploy log still records the previous deploy and the merges brought.
  assert.match(step('Activate release (keeps previous for rollback)').script, /steps\.merges\.outputs\.prev.*\n.*steps\.merges\.outputs\.prs/);
});

// The scope job's steps, run as Actions runs them, in a scratch repository with a stand-in gh.
const FAKE_GH = `#!/bin/bash
# Stand-in gh api: FAKE_RUNS ("id:sha", newest first) for the successful runs, FAKE_DEPLOYED (run ids whose deploy job succeeded),
# FAKE_FAIL (all, runs or jobs: those calls fail, as gh does on an HTTP error).
case "$FAKE_FAIL:$2" in all:*|runs:*/runs\?status=success*|jobs:*/jobs) echo "HTTP 502: Bad Gateway" >&2; exit 1;; esac
case "$2" in
  */actions/workflows/deploy.yml/runs\?status=success*) for r in $FAKE_RUNS; do echo "$r"; done;;
  */jobs) id=\${2%/jobs}; id=\${id##*/}; case " $FAKE_DEPLOYED " in *" $id "*) echo 1;; *) echo 0;; esac;;
  *) exit 2;;
esac
`;
const strip = Boolean(process.features.typescript);
function scopeRepo(t: { after: (fn: () => void) => void }) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'deploy-scope-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const repo = path.join(dir, 'repo'), bin = path.join(dir, 'bin');
  fs.mkdirSync(repo); fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, 'gh'), FAKE_GH, { mode: 0o755 });
  const env = { ...process.env, PATH: `${bin}:${path.dirname(process.execPath)}:${process.env.PATH}`, GIT_CONFIG_NOSYSTEM: '1', GIT_CONFIG_GLOBAL: '/dev/null',
    GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@example.com', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@example.com' };
  const git = (...args: string[]) => {
    const r = spawnSync('git', args, { cwd: repo, env, encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr); return r.stdout.trim();
  };
  const write = (files: Record<string, string>) => {
    for (const [f, text] of Object.entries(files)) { fs.mkdirSync(path.dirname(path.join(repo, f)), { recursive: true }); fs.writeFileSync(path.join(repo, f), text); }
  };
  const commit = (files: Record<string, string>, message: string) => { write(files); git('add', '-A'); git('commit', '-qm', message); return git('rev-parse', 'HEAD'); };
  const build = 'esbuild bot/main.ts --platform=node --bundle --format=cjs --outfile=dist/bot.cjs --packages=external && esbuild research/pipeline.ts --platform=node --bundle --format=cjs --outfile=dist/pipeline.cjs --packages=external';
  git('init', '-q', '-b', 'main');
  const deployed = commit({
    'package.json': JSON.stringify({ type: 'module', scripts: { build: 'npm run build:bot', 'build:bot': build } }), 'package-lock.json': '{}\n',
    'bot/main.ts': "import { x } from '../research/shared';\nconsole.log(x);\n", 'research/shared.ts': 'export const x = 1;\n',
    'research/pipeline.ts': "import { x } from './shared';\nconsole.log(x);\n", 'research/opportunity/study.ts': 'export const s = 2;\n',
    // Not bundled while research/shared.ts exists (a file wins over a directory index).
    'research/shared/index.ts': 'export const x = 5;\n',
    'docs/a.md': 'a\n', 'python/a.py': 'a = 1\n', '.github/workflows/deploy.yml': 'name: Deploy\n', '.github/workflows/atlas.yml': 'name: Atlas\n',
    'deploy/deploy-scope.ts': fs.readFileSync('deploy/deploy-scope.ts', 'utf8'),
  }, 'Deployed (#1)');
  let n = 0;
  const run = (job: string, name: string, extra: Record<string, string>) => {
    const s = jobSteps(job).find((x) => x.name === name);
    assert.ok(s && s.run.trim(), `deploy.yml ${job} step "${name}"`);
    const out = path.join(dir, `out${++n}`), summary = path.join(dir, `summary${n}`);
    fs.writeFileSync(out, ''); fs.writeFileSync(summary, '');
    const r = spawnSync('bash', ['--noprofile', '--norc', '-eo', 'pipefail', '-c', s.run],
      { cwd: repo, encoding: 'utf8', env: { ...env, GITHUB_OUTPUT: out, GITHUB_STEP_SUMMARY: summary, GITHUB_REPOSITORY: 'owner/repo', GITHUB_RUN_ID: '900', ...extra } });
    assert.equal(r.status, 0, r.stderr);
    const outputs: Record<string, string> = {};
    for (const line of fs.readFileSync(out, 'utf8').split('\n').filter(Boolean)) { const i = line.indexOf('='); outputs[line.slice(0, i)] = line.slice(i + 1); }
    return { stdout: r.stdout, outputs, summary: fs.readFileSync(summary, 'utf8') };
  };
  // The scope job: the last deployed commit (from the stand-in gh), then the decision for this push.
  const scope = (o: { runs?: string; deployedRuns?: string; fail?: 'all' | 'runs' | 'jobs'; before?: string; message?: string; esbuild?: string }) => {
    const prev = run('scope', 'Last deployed commit', { FAKE_RUNS: o.runs ?? '', FAKE_DEPLOYED: o.deployedRuns ?? '', FAKE_FAIL: o.fail ?? '' });
    const r = run('scope', 'Does this push change bot code', { EVENT_NAME: 'push', PREV_DEPLOY: prev.outputs.prev ?? '', PREV_LOOKUP: prev.outputs.lookup ?? '',
      BEFORE: o.before ?? '0'.repeat(40), HEAD_MESSAGE: o.message ?? 'Merge (#9)', ESBUILD: o.esbuild ?? path.resolve('node_modules/.bin/esbuild') });
    return { ...r, prev: prev.outputs.prev, lookup: prev.outputs.lookup };
  };
  const reset = () => git('reset', '-q', '--hard', deployed);
  return { repo, deployed, commit, git, run, scope, reset };
}
const scopeSkip = (!strip && 'needs node with type stripping') || (!fs.existsSync('node_modules/.bin/esbuild') && 'needs esbuild');

test('deploy scope job: research-only pushes skip with a summary; bot code deploys even with [skip deploy]', { skip: scopeSkip }, (t) => {
  const r = scopeRepo(t);
  // Runs newest first: this run (900, skipped), a research-only run whose deploy job was skipped (899), the last deploy (898).
  const runs = (head: string) => `900:${head} 899:${'c'.repeat(40)} 898:${r.deployed}`;
  const research = r.commit({ 'python/a.py': 'a = 2\n', 'docs/a.md': 'b\n', '.github/workflows/atlas.yml': 'name: Atlas 2\n', 'research/opportunity/study.ts': 'export const s = 3;\n' }, 'Research (#2)');
  let s = r.scope({ runs: runs(research), deployedRuns: '898' });
  assert.equal(s.prev, r.deployed); assert.equal(s.lookup, 'ok');
  assert.equal(s.outputs.deploy, 'false');
  assert.match(s.summary, /research-only: .*`python\/a\.py`.*`research\/opportunity\/study\.ts`.*; bot not restarted\./);
  assert.match(s.summary, new RegExp(`with the last deploy \\(\`${r.deployed.slice(0, 7)}\`\\)`));
  // Without the bundle check the unbundled research source counts as bot code.
  s = r.scope({ runs: runs(research), deployedRuns: '898', esbuild: '' });
  assert.equal(s.outputs.deploy, 'true'); assert.match(s.summary, /Bot code: `research\/opportunity\/study\.ts`/); assert.match(s.summary, /Bundle check unavailable/);

  r.reset();
  const tagged = r.commit({ 'bot/main.ts': "import { x } from '../research/shared';\nconsole.log(x + 1);\n", 'docs/a.md': 'c\n' }, 'Fix and notes (#3) [skip deploy]');
  s = r.scope({ runs: runs(tagged), deployedRuns: '898', before: r.deployed, message: 'Fix and notes (#3) [skip deploy]' });
  assert.equal(s.outputs.deploy, 'true');
  assert.match(s.stdout, /^::warning title=\[skip deploy\] ignored::This push changes bot code/m);
  // The previous head is the last deploy: nothing batched.
  assert.doesNotMatch(s.stdout + s.summary, /[Bb]atched/);
  assert.match(s.summary, /\*\*Warning:\*\* `\[skip deploy\]` ignored: this push changes bot code/);
  assert.match(s.summary, /Bot code: `bot\/main\.ts`\.\n\nResearch-only, also changed: `docs\/a\.md`/);

  // Bundled research, the lockfile, the deploy workflow, mixed research and bot code: each deploys.
  const deploys: Record<string, string>[] = [{ 'research/pipeline.ts': "import { x } from './shared';\nconsole.log(x, 2);\n" }, { 'research/shared.ts': 'export const x = 2;\n' },
    { 'package-lock.json': '{"lockfileVersion":3}\n' }, { '.github/workflows/deploy.yml': 'name: Deploy 2\n' },
    { 'research/opportunity/study.ts': 'export const s = 4;\n', 'python/a.py': 'a = 3\n', 'bot/extra.ts': 'export {};\n' }];
  for (const files of deploys) {
    r.reset();
    const head = r.commit(files, 'Change (#4) [skip deploy]');
    s = r.scope({ runs: runs(head), deployedRuns: '898', message: 'Change (#4) [skip deploy]' });
    assert.equal(s.outputs.deploy, 'true', Object.keys(files).join(', '));
    assert.match(s.stdout, /::warning/);
  }
});

test('deploy scope job: no batching, and anything it cannot compare deploys', { skip: scopeSkip }, (t) => {
  const r = scopeRepo(t);
  // A bot change that got no deploy of its own (pushed with [skip ci], so no run; or its deploy failed), then a docs-only
  // push: that push deploys the change, and its summary names the earlier push as batched.
  const fix = r.commit({ 'bot/main.ts': 'console.log(2);\n' }, 'Bot fix (#2) [skip ci]');
  const docs = r.commit({ 'docs/a.md': 'later\n' }, 'Docs (#3)');
  let s = r.scope({ runs: `900:${docs} 898:${r.deployed}`, deployedRuns: '898', before: fix });
  assert.equal(s.outputs.deploy, 'true'); assert.match(s.summary, /Bot code: `bot\/main\.ts`/);
  assert.match(s.summary, new RegExp(`\\*\\*Warning \\(batched\\):\\*\\* earlier pushes since the last deploy changed bot code .*: \`${fix.slice(0, 7)}\` Bot fix \\(#2\\) \\[skip ci\\]\\.`));
  assert.match(s.stdout, new RegExp(`^::warning title=Batched deploy::.*${fix.slice(0, 7)} Bot fix \\(#2\\)`, 'm'));

  // The GitHub API failing is not "no deploy found": the previous head (docs only) would hide the bot fix. Deploy.
  for (const fail of ['all', 'runs', 'jobs'] as const) {
    s = r.scope({ runs: `900:${docs} 898:${r.deployed}`, deployedRuns: '898', fail, before: fix });
    assert.equal(s.prev, '', fail); assert.equal(s.lookup, 'failed', fail);
    assert.equal(s.outputs.deploy, 'true', fail); assert.match(s.summary, /could not be looked up/, fail);
  }
  // The API answered and no earlier deploy exists: compare with the previous head instead (here docs only).
  s = r.scope({ runs: '', before: fix });
  assert.equal(s.prev, ''); assert.equal(s.lookup, 'ok'); assert.equal(s.outputs.deploy, 'false'); assert.match(s.summary, /the previous main head/);
  // No earlier deploy found and no previous head (first run, new branch): deploy.
  s = r.scope({ runs: '', before: '0'.repeat(40) });
  assert.equal(s.prev, ''); assert.equal(s.outputs.deploy, 'true'); assert.match(s.summary, /no earlier deploy and no previous main head/);
  // A previous head that is not in the history (force push): deploy.
  s = r.scope({ runs: '', before: 'e'.repeat(40) });
  assert.equal(s.outputs.deploy, 'true');
  // The last deployed commit is not in the history (force push): deploy.
  s = r.scope({ runs: `898:${'d'.repeat(40)}`, deployedRuns: '898', before: fix });
  assert.equal(s.outputs.deploy, 'true'); assert.match(s.summary, /not in this history/);
});

test('deploy scope job: research/ build configuration and deleted research/ sources deploy', { skip: scopeSkip }, (t) => {
  const r = scopeRepo(t);
  const runs = (head: string) => `900:${head} 898:${r.deployed}`;
  // esbuild applies these to research/pipeline.ts (bundled) without listing them in the metafile.
  const configs: Record<string, string>[] = [{ 'research/tsconfig.json': '{"compilerOptions":{"useDefineForClassFields":false}}\n' },
    { 'research/package.json': '{"sideEffects":false}\n' }, { 'research/.gitattributes': '*.ts text eol=crlf\n' }];
  for (const files of configs) {
    r.reset();
    const head = r.commit(files, 'Config (#5)');
    const s = r.scope({ runs: runs(head), deployedRuns: '898', before: r.deployed });
    const [file] = Object.keys(files);
    assert.equal(s.outputs.deploy, 'true', file); assert.ok(s.summary.includes(`Bot code: \`${file}\``), `${file} listed as bot code`);
    assert.doesNotMatch(s.summary, /Bundle check unavailable/, 'the bundle check ran');
  }
  // Deleting research/shared.ts makes bot/main.ts bundle research/shared/index.ts, which did not change: only the
  // deletion shows in the diff, and the bundle check at HEAD no longer sees the deleted file.
  r.reset();
  r.git('rm', '-q', 'research/shared.ts'); r.git('commit', '-qm', 'Drop shared (#6)');
  const head = r.git('rev-parse', 'HEAD');
  assert.ok(bundleInputs(r.repo, path.resolve('node_modules/.bin/esbuild'))?.has('research/shared/index.ts'), 'the release now bundles the sibling');
  let s = r.scope({ runs: runs(head), deployedRuns: '898', before: r.deployed });
  assert.equal(s.outputs.deploy, 'true'); assert.match(s.summary, /Bot code: `research\/shared\.ts`/);
  // Deleting a research-only listed file still skips.
  r.reset();
  r.git('rm', '-q', 'docs/a.md', 'python/a.py'); r.git('commit', '-qm', 'Drop notes (#7)');
  s = r.scope({ runs: runs(r.git('rev-parse', 'HEAD')), deployedRuns: '898', before: r.deployed });
  assert.equal(s.outputs.deploy, 'false'); assert.match(s.summary, /research-only: `docs\/a\.md`, `python\/a\.py`; bot not restarted\./);
});

test('deploy job: the merges log uses the last deployed commit the scope job found', (t) => {
  const r = scopeRepo(t);
  r.commit({ 'bot/main.ts': 'console.log(2);\n' }, 'Merge pull request #5 from x/y');
  r.commit({ 'docs/a.md': 'b\n' }, 'Notes (#6)');
  let m = r.run('deploy', 'Merges this deploy brings', { PREV: r.deployed });
  assert.equal(m.outputs.prev, r.deployed); assert.equal(m.outputs.prs, '#5,#6');
  assert.match(m.summary, new RegExp(`Previous deploy: \`${r.deployed.slice(0, 7)}\`\nBrings: #5,#6`));
  m = r.run('deploy', 'Merges this deploy brings', { PREV: '' });
  assert.equal(m.outputs.prev, ''); assert.equal(m.outputs.prs, ''); assert.match(m.summary, /Brings: none found/);
});

// Every file under a folder, as repo-relative paths.
const walk = (dir: string, base = dir): string[] => !fs.existsSync(dir) ? [] : fs.readdirSync(dir, { withFileTypes: true })
  .flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name), base) : [path.relative(base, path.join(dir, e.name)).split(path.sep).join('/')]));

test('deploy job: the heat upload ships the heat reader set at its own paths and nothing else; the bot upload is unchanged', { skip: !strip && 'needs node with type stripping' }, (t) => {
  const names = deploySteps().map((s) => s.name);
  const at = (name: string) => { const i = names.indexOf(name); assert.ok(i >= 0, name); return i; };
  // Staged after the build, uploaded right after the bot's own upload into the same release folder, before activation.
  assert.ok(at('Install (lockfile only), verify, build') < at('Stage the heat reader files'));
  assert.ok(at('Stage the heat reader files') < at('Upload release to server'));
  assert.equal(at('Upload the heat reader files'), at('Upload release to server') + 1);
  assert.ok(at('Upload the heat reader files') < at('Activate release (keeps previous for rollback)'));
  const bot = step('Upload release to server'), heat = step('Upload the heat reader files'), stage = step('Stage the heat reader files');
  const key = (text: string, k: string) => new RegExp(`^ {6}(?:- | {2}| {4})${k}: (.+)$`, 'm').exec(text)?.[1];
  assert.equal(key(bot.text, 'source'), '"dist,web/dist,params,package.json,package-lock.json,deploy,vendor"', 'what the bot upload ships today');
  assert.equal(key(heat.text, 'uses'), key(bot.text, 'uses'));
  assert.equal(key(heat.text, 'target'), key(bot.text, 'target'));
  assert.equal(key(heat.text, 'source'), '"heat-release"');
  assert.equal(key(heat.text, 'strip_components'), '1');
  assert.equal(key(heat.text, 'if'), 'steps.heat.outputs.files > 0');
  assert.equal(key(heat.text, 'rm'), undefined, 'rm would empty the release the bot upload just sent');
  // Neither step can stop the bot's deploy.
  assert.equal(key(heat.text, 'continue-on-error'), 'true'); assert.equal(key(stage.text, 'continue-on-error'), 'true');
  assert.equal(key(stage.text, 'id'), 'heat');
  assert.match(stage.run, /deploy\/deploy-scope\.ts --stage-heat heat-release\n/);
  for (const k of ['host', 'username', 'key', 'port']) assert.equal(key(heat.text, k), key(bot.text, k), k);

  const r = scopeRepo(t);
  const out = path.join(r.repo, 'heat-release');
  // Main before the reader lands: nothing staged, the upload is skipped.
  let s = r.run('deploy', 'Stage the heat reader files', {});
  assert.equal(s.outputs.files, '0'); assert.equal(fs.existsSync(out), false);
  assert.match(s.summary, /Heat reader set: none on this commit/);

  const files: Record<string, string> = {};
  for (const f of [...HEAT_FILES, ...HEAT_NEIGHBOURS_PYTHON, ...HEAT_NEIGHBOURS_RESEARCH]) files[f] = `${f}\n`;
  r.commit(files, 'Heat reader and oracle (#8)');
  // Left in the checkout but not tracked: never shipped. A stale folder from an earlier run is replaced.
  fs.mkdirSync(path.join(r.repo, 'python/heat_reader/__pycache__'), { recursive: true });
  fs.writeFileSync(path.join(r.repo, 'python/heat_reader/__pycache__/cli.cpython-312.pyc'), 'x');
  fs.writeFileSync(path.join(r.repo, 'research/oracle_heat/latest/scratch.json'), '{}\n');
  fs.mkdirSync(path.join(out, 'python'), { recursive: true }); fs.writeFileSync(path.join(out, 'python/stale.py'), '');
  s = r.run('deploy', 'Stage the heat reader files', {});
  const staged = walk(out).sort();
  assert.deepEqual(staged, [...HEAT_FILES].sort());
  assert.equal(s.outputs.files, String(HEAT_FILES.length));
  for (const f of staged) {
    assert.equal(fs.readFileSync(path.join(out, f), 'utf8'), `${f}\n`, f);
    // What ships is what the scope check counts as bot code (changed or deleted).
    assert.equal(researchOnly(f, BUNDLED), false, f); assert.equal(researchOnly(f, null, true), false, f);
  }
  assert.match(s.stdout, new RegExp(`Heat reader set: ${HEAT_FILES.length} files, .* \\(python/heat_reader 6, python/oracle 7, research/oracle_heat/latest 6\\)`));
  assert.match(s.summary, /Heat reader set: 19 files/);

  // A tag from before the list (its deploy-scope.ts has no HEAT_SHIP): nothing staged, nothing uploaded.
  fs.rmSync(out, { recursive: true, force: true });
  r.commit({ 'deploy/deploy-scope.ts': 'export {};\n' }, 'Older deploy scope (#9)');
  s = r.run('deploy', 'Stage the heat reader files', {});
  assert.equal(s.outputs.files, '0'); assert.match(s.stdout, /lists no heat reader files/); assert.equal(fs.existsSync(out), false);
  // The folder is a plain name under the checkout, never a path out of it.
  for (const bad of ['', '.', '..', '../x', '/tmp/x', 'a/b']) assert.throws(() => stageHeat(r.repo, bad), /plain folder name/, bad);
});

test('deploy job: the activate step leaves room for a first heat reader install on top of the old 30 minutes', () => {
  const s = step('Activate release (keeps previous for rollback)');
  const minutes = Number(/^\s*command_timeout: (\d+)m$/m.exec(s.text)?.[1]);
  const bound = Number(/HEAT_READER_INSTALL_TIMEOUT:-(\d+)/.exec(fs.readFileSync('deploy/heat_reader_follow.sh', 'utf8'))?.[1]);
  assert.ok(bound > 0 && bound <= 20 * 60, `installer bound ${bound} s`);
  // The bot's own worst case (a TA-Lib compile, the start, Caddy) kept its 30 minutes; the installer's bound and its
  // 30 s kill grace come on top, with room to spare.
  assert.ok(minutes * 60 >= 30 * 60 + bound + 30 + 10 * 60, `command_timeout ${minutes}m`);
  const yaml = fs.readFileSync('.github/workflows/deploy.yml', 'utf8');
  const job = yaml.slice(yaml.indexOf('\n  deploy:\n'), yaml.indexOf('\n    steps:\n', yaml.indexOf('\n  deploy:\n')));
  const jobLimit = /\n    timeout-minutes: (\d+)/.exec(job)?.[1];
  assert.ok(jobLimit === undefined || Number(jobLimit) > minutes + 30, `job timeout-minutes ${jobLimit}`);
  // The deploy log line is written after activate.sh, in the same script: activate.sh must not fail on the reader.
  assert.match(s.script, /bash deploy\/activate\.sh [^\n]+\n(.*\n)*.*>> ~\/bot\/deploys\.log/);
});
