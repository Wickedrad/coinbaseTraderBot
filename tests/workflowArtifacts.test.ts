import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

// Steven's standing rule, applied to the workflows on Nov 11, 2026 (8:05 AM EST / 13:05 UTC): this repository is public,
// so copies of server data (bot recordings, audit logs, Drive history archives, or rows built from them) never become
// GitHub Actions artifacts. These are the uploads that did, removed that day; the scan below keeps them from coming back.
const SERVER_COPIES: Array<{ what: string; name?: RegExp; path?: (p: string) => boolean }> = [
  { what: 'copy of the Drive history archive (diagnose.yml atlas_archive_export)', name: /atlas-history-archive/, path: (p) => /atlas-history-archive/.test(p) },
  { what: "prefixes of the bot's recordings (public-prefix, in what was atlas-recordings.yml)", name: /atlas-public-/, path: (p) => /atlas-public-recordings/.test(p) },
  { what: 'observed-recording study bundling recording rows', name: /atlas-recording-study/, path: (p) => /atlas-recording-study/.test(p) },
  { what: 'refit of that study (paper-shadow rows with recorded quotes)', name: /atlas-recording-refit/, path: (p) => /atlas-recording-refit/.test(p) },
  { what: 'movement study (examples built from the recordings)', name: /atlas-movement-study/, path: (p) => /atlas-movement-study/.test(p) },
  { what: 'direction snapshots (recorded books and trades)', name: /atlas-direction-snapshots/, path: (p) => /atlas-direction-snapshots/.test(p) },
  { what: 'native direction study (copies of the recorded inputs)', name: /atlas-native-direction/, path: (p) => /atlas-native-direction/.test(p) },
  { what: 'direction paper study (snapshot datasets)', name: /atlas-direction-paper/, path: (p) => /atlas-direction-paper/.test(p) },
  { what: 'quarantined copy of the Drive history archive (oracle-prepare, in what was atlas-research.yml)', name: /atlas-oracle-input/, path: (p) => /atlas-oracle-input/.test(p) },
  { what: 'SNN ablation sides (market, time, mid and outcome rows from the recordings)', name: /snn-ablation-side-/, path: (p) => /research\/out\/side-/.test(p) },
  // The history study may upload its results (top-level JSON and trees/), never its dataset/ rows or the whole folder.
  { what: 'history study dataset rows built from the Drive archive', path: (p) => /atlas-history-study(\/|$)/.test(p) && !/atlas-history-study\/(\*\.json|trees\/?)$/.test(p) },
  // Beyond the named outputs: the folders and files that hold server copies on a runner, and a whole data/ or research/out/
  // folder (the jobs that copy recordings or the audit log keep them there), so a parent folder cannot carry them out.
  { what: 'recordings, audit log, server settings or Drive lab copies', path: (p) => /(^|\/)(recordings|audit|sweep-env|lab-copies)(\/|$)|(^|\/)(md|audit)-[^/]*\.(jsonl|mdc)/.test(p) },
  { what: 'a whole data/ or research/out/ folder', path: (p) => /^(\.\/)?(data|research\/out)\/?$/.test(p) },
];

const DIR = '.github/workflows';
const workflowFiles = () => fs.readdirSync(DIR).filter((f) => /\.ya?ml$/.test(f)).sort();
/** The repository's composite actions (their steps can upload too), as paths relative to DIR. */
const actionFiles = () => fs.readdirSync('.github/actions').flatMap((d) => ['action.yml', 'action.yaml'].map((f) => `../actions/${d}/${f}`))
  .filter((f) => fs.existsSync(path.join(DIR, f))).sort();
const indentOf = (l: string) => l.length - l.trimStart().length;
const isComment = (l: string) => /^\s*#/.test(l);
const firstIndent = (block: string[]) => { const l = block.find((x) => x.trim() && !isComment(x)); return l === undefined ? 0 : indentOf(l); };

interface Entry { value: string; block: string[] }
/** The keys of a YAML mapping whose keys sit `level` spaces in: each key's inline value and its deeper block. */
function mapping(lines: string[], level: number): Map<string, Entry> {
  const out = new Map<string, Entry>();
  let cur: Entry | undefined;
  for (const l of lines) {
    const m = /^(\s*)([\w-]+):(?:\s+(.*))?$/.exec(l);
    if (m && m[1].length === level) { cur = { value: (m[3] ?? '').trim(), block: [] }; out.set(m[2], cur); }
    else if (cur && (!l.trim() || indentOf(l) > level)) cur.block.push(l);
    else if (!isComment(l)) cur = undefined;
  }
  return out;
}
const sub = (e: Entry | undefined) => (e ? mapping(e.block, firstIndent(e.block)) : new Map<string, Entry>());
const unquote = (v: string) => v.replace(/^(['"])(.*)\1$/, '$2');
/** A scalar or a block list (`path: |`) as its non-empty lines. */
const values = (e?: Entry) => !e ? [] : /^[|>][-+]?$/.test(e.value) ? e.block.map((l) => l.trim()).filter(Boolean) : e.value ? [unquote(e.value)] : [];
/** A `run: |` block as the script bash receives (before GitHub's ${{ }} substitution). */
const script = (e?: Entry) => {
  if (!e) return '';
  if (!/^[|>]/.test(e.value)) return unquote(e.value) + '\n';
  const n = firstIndent(e.block);
  return e.block.map((l) => l.slice(n)).join('\n').trimEnd() + '\n';
};

interface Step { file: string; job: string; line: number; name: string; uses: string; with: Map<string, Entry>; env: Map<string, Entry>; run: string }
/** Every step of every job, cut out by indentation (the repository has no YAML library). */
function workflowSteps(file: string, text = fs.readFileSync(path.join(DIR, file), 'utf8')): Step[] {
  const lines = text.split('\n'), out: Step[] = [];
  let job = '', inJobs = false;
  for (let i = 0; i < lines.length; i++) {
    if (/^jobs:\s*$/.test(lines[i])) { inJobs = true; continue; }
    const j = inJobs ? /^ {2}([\w-]+):\s*$/.exec(lines[i]) : null;
    if (j) job = j[1];
    const s = /^(\s*)steps:\s*$/.exec(lines[i]);
    if (!s) continue;
    let end = i + 1;
    while (end < lines.length && (!lines[end].trim() || isComment(lines[end]) || indentOf(lines[end]) > s[1].length)) end++;
    const items: number[] = [];
    for (let k = i + 1; k < end; k++) if (/^\s*- /.test(lines[k]) && (!items.length || indentOf(lines[k]) === indentOf(lines[items[0]]))) items.push(k);
    items.forEach((at, n) => {
      const d = indentOf(lines[at]);
      const own = [lines[at].replace(/^(\s*)- /, '$1  '), ...lines.slice(at + 1, items[n + 1] ?? end)];
      const keys = mapping(own, d + 2);
      out.push({ file, job, line: at + 1, name: unquote(keys.get('name')?.value ?? ''), uses: unquote(keys.get('uses')?.value ?? ''),
        with: sub(keys.get('with')), env: sub(keys.get('env')), run: script(keys.get('run')) });
    });
    i = end - 1;
  }
  return out;
}
/** Each job's `if:` (empty: always runs) and the dispatch inputs. */
function workflowJobs(file: string) {
  const lines = fs.readFileSync(path.join(DIR, file), 'utf8').split('\n'), top = mapping(lines, 0);
  const jobs = new Map([...mapping(top.get('jobs')!.block, 2)].map(([name, e]) => [name, sub(e).get('if')?.value ?? '']));
  const inputs = [...sub(sub(sub(top.get('on')).get('workflow_dispatch')).get('inputs')).keys()];
  return { jobs, inputs };
}
/** A job's `if:` as GitHub would decide it, with every job it needs assumed successful. */
function runs(expr: string, inputs: Record<string, unknown>): boolean {
  if (!expr) return true;
  const js = expr.trim().replace(/^\$\{\{\s*/, '').replace(/\s*\}\}$/, '')
    .replace(/\bcancelled\(\)/g, 'false').replace(/\balways\(\)/g, 'true')
    .replace(/needs\.[\w-]+\.result/g, "'success'").replace(/fromJSON\(/g, 'JSON.parse(')
    .replace(/inputs\.(\w+)/g, (_, k: string) => JSON.stringify(inputs[k] ?? ''));
  return Boolean(Function(`return (${js})`)());
}

/** An upload, or a merge of uploaded artifacts into a new one (its `pattern` names what it bundles). */
const isUpload = (s: Step) => /^actions\/upload-artifact(\/merge)?@/.test(s.uses);
function serverCopyUploads(steps: Step[]): string[] {
  const found: string[] = [];
  for (const s of steps.filter(isUpload)) {
    const name = [...values(s.with.get('name')), ...values(s.with.get('pattern'))].join(' ');
    const paths = values(s.with.get('path')).filter((p) => !p.startsWith('!'));
    for (const c of SERVER_COPIES) {
      if (c.name?.test(name) || paths.some((p) => c.path?.(p))) found.push(`${s.file}:${s.line} uploads ${name} [${paths.join(', ')}]: ${c.what}`);
    }
  }
  return found;
}
const bash = (code: string, o: { cwd?: string; env?: Record<string, string> } = {}) =>
  spawnSync('bash', ['-c', code], { cwd: o.cwd, env: { ...process.env, ...o.env }, encoding: 'utf8' });
const tmp = (t: { after: (f: () => void) => void }) => { const d = fs.mkdtempSync(path.join(os.tmpdir(), 'wf-artifacts-')); t.after(() => fs.rmSync(d, { recursive: true, force: true })); return d; };
const step = (file: string, job: string, name: string) => {
  const s = workflowSteps(file).find((x) => x.job === job && x.name === name);
  assert.ok(s, `${file}: job ${job}, step "${name}"`);
  return s;
};

test('no workflow uploads a known server copy as an Actions artifact', () => {
  const steps = [...workflowFiles(), ...actionFiles()].flatMap((f) => workflowSteps(f)), uploads = steps.filter(isUpload);
  assert.ok(actionFiles().includes('../actions/drive-setup/action.yml'), 'composite actions are scanned too');
  // The scan has to see the uploads, each with a name and a path, or an empty result proves nothing.
  assert.ok(uploads.length >= 30, `only ${uploads.length} uploads found`);
  for (const s of uploads.filter((x) => !/merge@/.test(x.uses))) assert.ok(values(s.with.get('name')).length && values(s.with.get('path')).length, `${s.file}:${s.line}`);
  assert.ok(uploads.some((s) => values(s.with.get('name'))[0] === 'atlas-oracle-summary'), 'a results-only Atlas upload is still seen');
  assert.deepEqual(serverCopyUploads(steps), []);
});

test('the scan catches each removed upload as it was written, and passes results-only uploads', () => {
  const removed = [
    '      - uses: actions/upload-artifact@v4', '        with:', "          name: atlas-public-${{ matrix.day }}", '          path: research/out/atlas-public-recordings/',
    '      - name: Save study, provenance and paper abstention evidence', '        if: always()', '        uses: actions/upload-artifact@v4', '        with:',
    '          name: atlas-recording-study', '          path: research/out/atlas-recording-study/',
    '      - uses: actions/upload-artifact@v4', '        if: always()', '        with:',
    "          name: ${{ inputs.movement_only && 'atlas-movement-study' || 'atlas-recording-refit' }}",
    "          path: ${{ inputs.movement_only && 'research/out/atlas-movement-study/' || 'research/out/atlas-recording-refit/' }}",
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: atlas-direction-snapshots', '          path: research/out/atlas-direction-snapshots/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: atlas-native-direction', '          path: research/out/atlas-native-direction/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: atlas-direction-paper', '          path: research/out/atlas-direction-paper/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: atlas-oracle-input', '          path: ${{ runner.temp }}/atlas-oracle-input/',
    '      - name: Save research archive and audit (credentials excluded)', '        uses: actions/upload-artifact@v4', '        with:',
    '          name: atlas-history-archive', '          path: ${{ runner.temp }}/atlas-history-archive/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: atlas-history-study', '          path: research/out/atlas-history-study/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: snn-ablation-side-${{ matrix.side }}', '          path: research/out/side-${{ matrix.side }}.json',
    // The same, written in ways the scan must also see through: a quoted `uses`, a merge of the old uploads, a parent folder.
    '      - uses: "actions/upload-artifact@v4"', '        with:', '          name: atlas-history-archive', '          path: ${{ runner.temp }}/atlas-history-archive/',
    "      - uses: 'actions/upload-artifact/merge@v4'", '        with:', '          name: everything', '          pattern: snn-ablation-side-*',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: lab', '          path: research/out/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: copy', '          path: |', '            data/sweeps/x.json', '            data/recordings/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: day', '          path: ${{ runner.temp }}/md-2026-10-21.jsonl.gz',
  ];
  const allowed = [
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: atlas-history-study', '          # Results only.', '          path: |',
    '            research/out/atlas-history-study/*.json', '            research/out/atlas-history-study/trees/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: atlas-oracle-summary', '          path: research/out/atlas-oracle-summary/',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: replay-check', '          path: data/sweeps/replay-check-latest.json',
    '      - uses: actions/upload-artifact@v4', '        with:', '          name: fidelity', '          path: ${{ runner.temp }}/out/',
  ];
  const fixture = (body: string[]) => ['on: workflow_dispatch', 'jobs:', '  a:', '    runs-on: ubuntu-latest', '    steps:', ...body, ''].join('\n');
  const steps = workflowSteps('fixture.yml', fixture(removed));
  assert.equal(steps.filter(isUpload).length, 15);
  const caught = new Set(serverCopyUploads(steps).map((f) => Number(/^fixture\.yml:(\d+)/.exec(f)![1])));
  assert.deepEqual([...caught].sort((a, b) => a - b), steps.filter(isUpload).map((s) => s.line));
  assert.deepEqual(serverCopyUploads(workflowSteps('fixture.yml', fixture(allowed))), []);
});

test('the old Atlas workflow paths stay off this branch, so older branches\' copies of them cannot be dispatched', () => {
  // GitHub runs a dispatched workflow from the requested ref's copy of the file whenever a file at that path is on main.
  // Older branches still hold these three with the removed jobs, several of which need no secret (they re-upload the
  // existing artifacts), so environment rules cannot stop them: the paths themselves have to stay off main.
  for (const f of ['atlas-recordings.yml', 'atlas-research.yml', 'atlas-movement.yml']) assert.equal(fs.existsSync(path.join(DIR, f)), false, f);
  assert.ok(fs.existsSync(path.join(DIR, 'atlas-oracle-edge.yml')) && fs.existsSync(path.join(DIR, 'atlas-research-results.yml')));
});

test('atlas-oracle-edge: only the Oracle edge trial runs; every other dispatch fails closed', () => {
  const { jobs, inputs } = workflowJobs('atlas-oracle-edge.yml');
  assert.deepEqual([...jobs.keys()], ['server-copies-off', 'frozen-oracle-edge', 'assess-oracle-edge']);
  assert.deepEqual(inputs, ['source_run', 'oracle_edge', 'edge_cycles'], 'the removed modes cannot be requested');
  for (const oracle_edge of [false, true]) for (const source_run of ['', '42']) {
    const ran = [...jobs].filter(([, expr]) => runs(expr, { oracle_edge, source_run, edge_cycles: '72' })).map(([name]) => name);
    if (!oracle_edge) assert.deepEqual(ran, ['server-copies-off'], source_run);
    else assert.ok(!ran.includes('server-copies-off') && ran.length > 0, `${source_run}: ${ran}`);
  }
  const r = bash(step('atlas-oracle-edge.yml', 'server-copies-off', 'The observed-recording modes are off').run);
  assert.equal(r.status, 1); assert.match(r.stdout, /^::error::.*public, so server copies never become Actions artifacts/);
});

test('atlas-research-results: no job prepares a new Oracle input; oracle_blocks without prepared_run fails closed', () => {
  const { jobs } = workflowJobs('atlas-research-results.yml');
  assert.ok(!jobs.has('oracle-prepare'));
  for (const oracle_blocks of [false, true]) for (const prepared_run of ['', '7']) for (const results_run of ['', '9']) {
    const i = { oracle_blocks, prepared_run, results_run, importance_iteration: false, dataset_run: '', capture_public_books: false };
    assert.equal(runs(jobs.get('server-copies-off')!, i), oracle_blocks && !prepared_run && !results_run, JSON.stringify(i));
    if (runs(jobs.get('oracle-train')!, i)) assert.ok(prepared_run, JSON.stringify(i));
  }
  const train = workflowSteps('atlas-research-results.yml').filter((s) => s.job === 'oracle-train' && /download-artifact/.test(s.uses));
  assert.deepEqual(train.map((s) => values(s.with.get('run-id'))[0]), ['${{ inputs.prepared_run }}']);
  const r = bash(step('atlas-research-results.yml', 'server-copies-off', 'Preparing a new Oracle input is off').run);
  assert.equal(r.status, 1); assert.match(r.stdout, /^::error::.*Drive history archive.*public/);
});

test('diagnose: recording-probe fails closed before the Drive secret is written; the archive sources still run', (t) => {
  const s = step('diagnose.yml', 'atlas-archive-export', 'Export only the located historical files (Drive read-only)');
  const dir = tmp(t), bin = path.join(dir, 'bin'), calls = path.join(dir, 'rclone-calls');
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, 'rclone'), `#!/bin/bash\necho "$@" >> "${calls}"\n`, { mode: 0o755 });
  const run = (source: string, temp: string) => {
    fs.mkdirSync(temp);
    return bash(s.run, { env: { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: temp, RCLONE_CONF: 'stand-in', ATLAS_ARCHIVE_SOURCE: source, ATLAS_DO_STUDY: 'false' } });
  };
  const probe = run('recording-probe', path.join(dir, 'probe'));
  assert.equal(probe.status, 1); assert.match(probe.stdout, /^::error::Off since Nov 11, 2026: recording-probe .*public/);
  assert.equal(fs.existsSync(calls), false, 'no Drive read'); assert.equal(fs.existsSync(path.join(dir, 'probe/atlas-archive-config')), false, 'no config written');
  const recent = run('recent', path.join(dir, 'recent'));
  assert.doesNotMatch(recent.stdout, /Off since/);
  assert.match(fs.readFileSync(calls, 'utf8'), /^copy gdrive:kalshi-bot-archive\/raw\/history /m);
});

test('snn-ablation: replayed sides reach the judge through Drive, never artifacts', (t) => {
  const dir = tmp(t), log = path.join(dir, 'drive-calls');
  fs.mkdirSync(path.join(dir, 'deploy'));
  fs.writeFileSync(path.join(dir, 'deploy/drive_lab.sh'), `echo "$@" >> "${log}"\n[ "$2" != lab-copies/snn-ablation/404 ] || exit 3\n`);
  const put = step('snn-ablation.yml', 'side', 'Keep this side on Drive for the judge (rows from the recordings; never an artifact)');
  assert.equal(bash(put.run.replaceAll('${{ matrix.side }}', 'baseline'), { cwd: dir, env: { GITHUB_RUN_ID: '123' } }).status, 0);
  const get = step('snn-ablation.yml', 'judge', 'The two saved sides from Drive');
  assert.equal(values(get.env.get('SIDES_RUN'))[0], '${{ inputs.from_run || github.run_id }}');
  assert.equal(bash(get.run, { cwd: dir, env: { SIDES_RUN: '123' } }).status, 0);
  assert.deepEqual(fs.readFileSync(log, 'utf8').trim().split('\n'), [
    'put lab-copies/snn-ablation/123 research/out --include side-baseline.json',
    'get lab-copies/snn-ablation/123 research/out --include side-*.json']);
  const missing = bash(get.run, { cwd: dir, env: { SIDES_RUN: '404' } });
  assert.equal(missing.status, 1); assert.match(missing.stdout, /::error::no saved sides on Drive for run 404/);
  assert.equal(bash(get.run, { cwd: dir, env: { SIDES_RUN: '1;rm -rf x' } }).status, 1);
  assert.ok(!workflowSteps('snn-ablation.yml').some((s) => /artifact@/.test(s.uses) && /side/.test(values(s.with.get('name')).join() + values(s.with.get('pattern')).join())));
});

test('replay check: REPLAY_DUMP and REPLAY_PEEK (audit-log rows into the log, artifact and commit comment) are refused before any replay', (t) => {
  const s = step('kalshi-replay-check.yml', 'check', "Replay check (backtester vs paper, since the bot's last start)");
  const lines = s.run.split('\n'), from = lines.findIndex((l) => l.startsWith('for v in REPLAY_DUMP REPLAY_PEEK REPLAY_PEEK_ONLY; do'));
  const at = lines.findIndex((l, i) => i > from && l === 'done') + 1;
  assert.ok(from > 0 && at > from, 'the refusal');
  assert.ok(lines.slice(0, at).every((l) => !/node |replayCheck/.test(l)), 'it comes before the replay');
  const head = lines.slice(0, at).join('\n'), dir = tmp(t);
  fs.mkdirSync(path.join(dir, 'data/sweep-env'), { recursive: true });
  const run = (env: string, overrides: string) => {
    fs.writeFileSync(path.join(dir, 'data/sweep-env/train.env'), env);
    return bash(head, { cwd: dir, env: { OVERRIDES: overrides, REPLAY_DUMP: '', REPLAY_PEEK: '', REPLAY_PEEK_ONLY: '' } });
  };
  assert.equal(run('', 'EXIT_POLICY=hold').status, 0);
  for (const [v, value] of [['REPLAY_DUMP', 'mid'], ['REPLAY_PEEK', 'KXBTC15M-26NOV041200-00@2026-11-04T11:00:00Z/2026-11-04T12:00:00Z'], ['REPLAY_PEEK_ONLY', '1']]) {
    const refused = run('', `EXIT_POLICY=hold ${v}=${value}`);
    assert.equal(refused.status, 1, v); assert.match(refused.stdout, new RegExp(`::error::${v} is off on GitHub: it publishes audit-log rows`));
    assert.equal(run(`${v}=${value}\n`, '').status, 1, `${v} from the copied settings too`);
  }
});
