// Does a push to main change anything that reaches the server? The Deploy workflow's scope job runs this
// (node --experimental-strip-types deploy/deploy-scope.ts) before the deploy job, and the deploy job only runs
// for a push when this says so. Manual runs always deploy.
//
// Steven, Nov 11 (8:18 AM EST / 13:18 UTC): merges that touch no bot code may skip the bot deploy and restart;
// every merge that changes bot code still gets its own logged deploy, no batching. So the decision rests on what
// changed since the last deploy, not on the commit message: a push that changes bot code deploys even with
// "[skip deploy]" in its message (with a warning), and a research-only push skips without the tag.
//
// Research-only means a path that never reaches the server (RESEARCH_ONLY): python/, docs/, tests/, packaging/,
// .github/ except the deploy workflow, top-level markdown and report files, notebooks, and in research/ the
// markdown, Python, CSV, HTML, images and study outputs (out/, out10/). The rest of research/ (its .ts among them:
// some of it is bundled into dist/) is research-only only when the bundle check ran and the release does not
// bundle it (bundleInputs: every esbuild run of `npm run build`, repeated with --metafile, and the dashboard's
// imports). Since the bundle check only sees HEAD and only lists source files, two kinds of research/ file stay bot
// code anyway: a deleted one (an import of it may now resolve to another file) and the build configuration esbuild,
// npm and git read beside the sources (BUILD_CONFIG: tsconfig, package.json, .gitattributes, .npmrc). Everything
// else is bot code: bot/, web/, deploy/, params/, vendor/, package.json, package-lock.json, tsconfig.json,
// scripts/, the deploy workflow and any path not listed. A file the release bundles is bot code wherever it lives.
// Whatever this cannot tell (the last deploy could not be looked up, no commit to compare with, git failing) deploys.
//
// The heat curve reader is the one part of python/ and research/ that reaches the server: it runs beside the bot from
// the release itself (docs/HEAT_READER.md). HEAT_SHIP lists its files: python/heat_reader and python/oracle (the
// engine it imports) without their tests, fixtures and preregistration notes, and the oracle run's packs
// (research/oracle_heat/latest/*.json and RUN). They are bot code, changed or deleted, and the release ships exactly
// these: the deploy job's "Stage the heat reader files" step runs this file with --stage-heat, so the upload and this
// check read the same list. Their neighbours stay research-only as before: the reader's and the engine's tests and
// fixtures, the league tables (latest/*.csv.gz, league.md), the rest of research/oracle_heat and the rest of python/.
//
// The comparison is with the commit of the newest run whose deploy job succeeded. A tag deployed by a manual run,
// or a rollback on the server, therefore stays in place through research-only pushes until bot code changes.
//
// Inputs (environment): EVENT_NAME, PREV_DEPLOY (the commit the last successful deploy shipped, or empty),
// PREV_LOOKUP ('ok' when the GitHub API answered; anything else deploys), BEFORE (github.event.before),
// HEAD_MESSAGE, ESBUILD (an esbuild binary, or empty: no bundle check).
// Outputs: deploy=true|false in $GITHUB_OUTPUT, a summary in $GITHUB_STEP_SUMMARY, a ::warning:: when the tag
// is ignored or when earlier pushes changed bot code without a deploy of their own (batched into this one).
//
// With `--stage-heat <dir>` (the deploy job) it decides nothing: it copies the heat reader set tracked at HEAD into
// <dir> at the same paths and writes files=<count> to $GITHUB_OUTPUT (0: nothing to upload).
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export const SKIP_TAG = '[skip deploy]';

// The heat curve reader's files, shipped with every release that has them (none until the reader and the oracle
// engine reach main: the deploy then ships nothing extra). `dir`: the folder each pattern lies in; `re`: the files of
// it that ship. Every module the reader can import ships: all of python/oracle but tests/ and prereg/ (the
// preregistration notes, read by no module the reader loads). Of research/oracle_heat only latest/'s packs (*.json)
// and RUN: not the league tables (*.csv.gz, league.md), the viewer (viewer.json.gz) or the parity fixtures.
export const HEAT_SHIP: readonly { dir: string; re: RegExp }[] = [
  { dir: 'python/heat_reader', re: /^python\/heat_reader\/(?!(tests|fixtures)\/)./ },
  { dir: 'python/oracle', re: /^python\/oracle\/(?!(tests|prereg)\/)./ },
  { dir: 'research/oracle_heat/latest', re: /^research\/oracle_heat\/latest\/([^/]+\.json|RUN)$/ },
];

/** True for a file of the heat reader set (HEAT_SHIP): the release ships it, so a change to it deploys. */
export const heatShipped = (file: string) => HEAT_SHIP.some((h) => h.re.test(file));

// Paths that never reach the server. The release is dist/ (built by `npm run build`), web/dist, params/, deploy/,
// vendor/, package.json and package-lock.json (the workflow's upload step), and the heat reader set above (its own
// upload step); none of those is listed here, and the heat reader set wins over this list.
export const RESEARCH_ONLY: readonly RegExp[] = [
  /^python\//,
  /^docs\//,
  /^tests\//,
  /^packaging\//, // the Windows laptop trainer package
  /^\.github\/(?!workflows\/deploy\.yml$)/, // other workflows and their scripts and actions (deploy.yml uses none)
  /^[^/]+\.md$/, // top-level markdown
  /^[A-Z0-9_]+\.json$/, // top-level reports (OPPORTUNITY_ATLAS_DIRECTION_VALIDATION.json); not package.json or tsconfig.json
  /^(?!(bot|web|deploy|params|vendor|dist)\/).*\.ipynb$/, // notebooks, outside what the release ships
  /^research\/(.+\/)?out\d*\//, // study outputs: research/out/, research/btcd_fractal/out10/
  /^research\/.+\.(md|py|ipynb|csv|html|png|jpe?g|gif|svg|log)$/i, // types esbuild's default loaders cannot bundle
];

// Build configuration that esbuild (tsconfig.json and package.json above each bundled file: compiler options,
// module type, sideEffects, imports), npm (.npmrc) and git (.gitattributes: the bytes checked out) read without the
// metafile listing it. Bot code wherever it lies, except in the research-only trees below, where it counts only
// above a file the release bundles.
export const BUILD_CONFIG = /(^|\/)((tsconfig|jsconfig)[^/]*\.json|package\.json|\.gitattributes|\.npmrc)$/;
const RESEARCH_TREES = /^(python|docs|tests|packaging|\.github)\//;

const above = (file: string, bundled: ReadonlySet<string>) => {
  const dir = file.slice(0, file.lastIndexOf('/') + 1);
  for (const f of bundled) if (f.startsWith(dir)) return true;
  return false;
};

/**
 * True when the path never reaches the server. `bundled`: the files the release bundles at HEAD (null: unknown).
 * `deleted`: the path is gone at HEAD, so the bundle check cannot have seen it.
 */
export function researchOnly(file: string, bundled: ReadonlySet<string> | null, deleted = false): boolean {
  if (heatShipped(file)) return false; // the heat reader upload ships it (deleted: the release no longer has it)
  if (bundled?.has(file)) return false;
  if (BUILD_CONFIG.test(file) && (!RESEARCH_TREES.test(file) || (bundled !== null && above(file, bundled)))) return false;
  if (RESEARCH_ONLY.some((re) => re.test(file))) return true;
  // The rest of research/ is research-only when the bundle check ran and did not find it in the release. A deleted
  // file it cannot judge: an import that reached it may now resolve to another file.
  return bundled !== null && !deleted && file.startsWith('research/');
}

export function classify(files: readonly string[], bundled: ReadonlySet<string> | null, deleted: ReadonlySet<string> = new Set()) {
  const bot: string[] = [], research: string[] = [];
  for (const f of files) (researchOnly(f, bundled, deleted.has(f)) ? research : bot).push(f);
  return { bot, research };
}

export interface Decision {
  deploy: boolean;
  /** One line: why it deploys or skips. */
  why: string;
  bot: string[];
  research: string[];
  /** The head commit carries [skip deploy] but the push deploys. */
  tagIgnored: boolean;
}

/**
 * files: the paths changed since the last deploy (deleted: those gone at HEAD); null when that cannot be told
 * (deploys).
 */
export function decide(o: { event: string; files: readonly string[] | null; deleted?: ReadonlySet<string>; bundled: ReadonlySet<string> | null; message: string; unknown?: string }): Decision {
  const tagged = o.message.includes(SKIP_TAG);
  if (o.event !== 'push') return { deploy: true, why: 'manual run: always deploys', bot: [], research: [], tagIgnored: false };
  if (o.files === null) return { deploy: true, why: `${o.unknown ?? 'could not tell what changed'}: deploying to be safe`, bot: [], research: [], tagIgnored: tagged };
  const { bot, research } = classify(o.files, o.bundled, o.deleted);
  if (bot.length > 0) return { deploy: true, why: 'bot code changed', bot, research, tagIgnored: tagged };
  return { deploy: false, why: research.length > 0 ? 'research-only' : 'nothing changed', bot, research, tagIgnored: false };
}

const ZERO = /^0+$/;
const SHA = /^[0-9a-f]{7,40}$/;

/**
 * The commit to compare with: the one the last successful deploy shipped; when the lookup found no deploy, the
 * branch's previous head (github.event.before). Null (deploy) when the lookup failed (`lookup` other than 'ok': a
 * deploy it could not see may be older than the previous head, and a bot change since then would go undeployed),
 * when the last deploy's commit is gone from the history (force push), or when no deploy was found and there is no
 * previous head (first push, new branch).
 */
export function chooseBase(prev: string, before: string, has: (sha: string) => boolean, lookup: string): { sha: string; kind: string } | { sha: null; why: string } {
  if (lookup !== 'ok') return { sha: null, why: 'the last deploy could not be looked up (GitHub API failed)' };
  if (prev) {
    if (SHA.test(prev) && has(prev)) return { sha: prev, kind: 'the last deploy' };
    return { sha: null, why: `the last deployed commit ${prev.slice(0, 7)} is not in this history (force push?)` };
  }
  if (before && !ZERO.test(before) && SHA.test(before) && has(before)) return { sha: before, kind: 'the previous main head (no successful deploy found)' };
  return { sha: null, why: 'no earlier deploy and no previous main head to compare with' };
}

/**
 * The esbuild runs of `npm run <name>` in package.json, as argument lists, following `npm run` steps; `vite build`
 * steps come back in `vite` (their --config). Null when a step is anything else, so a build this cannot mirror
 * never narrows what counts as bot code.
 */
export function buildRuns(scripts: Record<string, string>, name = 'build', stack: readonly string[] = []): { esbuild: string[][]; vite: string[] } | null {
  const body = scripts[name];
  if (body === undefined || stack.includes(name)) return null;
  const out = { esbuild: [] as string[][], vite: [] as string[] };
  for (const part of body.split('&&').map((s) => s.trim())) {
    if (!/^[\w@%+=:,./\s-]+$/.test(part)) return null; // quotes, pipes, redirects, variables, globs
    const argv = part.split(/\s+/);
    if (argv[0] === 'npm' && argv[1] === 'run' && argv.length === 3) {
      const sub = buildRuns(scripts, argv[2], [...stack, name]);
      if (!sub) return null;
      out.esbuild.push(...sub.esbuild); out.vite.push(...sub.vite);
    } else if (argv[0] === 'esbuild' && argv.includes('--bundle')) out.esbuild.push(argv.slice(1));
    else if (argv[0] === 'vite' && argv[1] === 'build' && argv.length === 4 && argv[2] === '--config') out.vite.push(argv[3]);
    else return null;
  }
  return out;
}

/** Runs esbuild with a metafile and returns its input files (repo-relative), or null when it fails. */
function metaInputs(esbuild: string, root: string, args: string[], tmp: string, n: number): string[] | null {
  const meta = path.join(tmp, `${n}.json`);
  const r = spawnSync(esbuild, [...args, `--metafile=${meta}`, '--log-level=error'], { cwd: root, encoding: 'utf8' });
  if (r.status !== 0) return null;
  return Object.keys(JSON.parse(fs.readFileSync(meta, 'utf8')).inputs as Record<string, unknown>);
}

/**
 * Every file the release bundles: each esbuild run of `npm run build` repeated exactly, writing to a scratch
 * directory with a metafile; for the dashboard (vite), its index.html scripts and its config bundled the same
 * way. Null when anything cannot be mirrored or fails.
 */
export function bundleInputs(root: string, esbuild: string): Set<string> | null {
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')) as { scripts?: Record<string, string> };
  const runs = buildRuns(pkg.scripts ?? {});
  if (!runs || runs.esbuild.length === 0) return null;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'deploy-scope-'));
  try {
    const inputs = new Set<string>();
    let n = 0;
    const add = (args: string[]) => {
      const got = metaInputs(esbuild, root, args, tmp, n++);
      if (got) for (const f of got) inputs.add(f);
      return got !== null;
    };
    for (const args of runs.esbuild) {
      const kept = args.filter((a) => !/^--(outfile|outdir|metafile|log-level)(=|$)/.test(a));
      if (!add([...kept, `--outfile=${path.join(tmp, `${n}.out.cjs`)}`])) return null;
    }
    for (const config of runs.vite) {
      const text = fs.readFileSync(path.join(root, config), 'utf8');
      if (/\balias\b|\brollupOptions\b/.test(text)) return null; // could reach files outside the dashboard unseen
      const webRoot = path.posix.dirname(config);
      const html = fs.readFileSync(path.join(root, webRoot, 'index.html'), 'utf8');
      const entries = [...html.matchAll(/<script\b[^>]*\bsrc="([^"]+)"/g)].map((m) => path.posix.join(webRoot, m[1].replace(/^\//, '')));
      if (entries.length === 0) return null;
      inputs.add(config); inputs.add(path.posix.join(webRoot, 'index.html'));
      const loaders = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'woff', 'woff2'].map((e) => `--loader:.${e}=file`);
      if (!add([...entries, '--bundle', '--packages=external', '--jsx=automatic', ...loaders, `--outdir=${path.join(tmp, `web${n}`)}`])) return null;
      if (!add([config, '--bundle', '--platform=node', '--packages=external', `--outfile=${path.join(tmp, `${n}.config.cjs`)}`])) return null;
    }
    return inputs;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

const git = (root: string, args: string[]) => execFileSync('git', args, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });

/** The paths that differ between two commits (both sides of a rename), and those of them gone at `to`. */
export function changedFiles(root: string, from: string, to = 'HEAD'): { files: string[]; deleted: Set<string> } {
  const diff = (filter: string[]) => git(root, ['diff', '--name-only', '--no-renames', '-z', ...filter, from, to]).split('\0').filter(Boolean);
  return { files: diff([]), deleted: new Set(diff(['--diff-filter=D'])) };
}

/**
 * Copies the heat reader set tracked at `root`'s HEAD (HEAT_SHIP) into `dest`, a plain folder name under `root`
 * (removed first), at the same paths, for the deploy job's heat upload. Returns the files copied: none when the
 * commit has none of them, and then `dest` is not created.
 */
export function stageHeat(root: string, dest: string): string[] {
  if (!/^\w[\w.-]*$/.test(dest)) throw new Error(`--stage-heat takes a plain folder name, not ${JSON.stringify(dest)}`);
  const files = git(root, ['ls-files', '-z', '--', ...HEAT_SHIP.map((h) => h.dir)]).split('\0').filter((f) => f && heatShipped(f));
  const out = path.join(root, dest);
  fs.rmSync(out, { recursive: true, force: true });
  for (const f of files) {
    fs.mkdirSync(path.dirname(path.join(out, f)), { recursive: true });
    fs.copyFileSync(path.join(root, f), path.join(out, f));
  }
  return files;
}

/** --stage-heat: stages the set, prints and summarises what it staged, and writes files=<count> to $GITHUB_OUTPUT. */
export function stageHeatMain(dest: string, env: NodeJS.ProcessEnv = process.env, root = process.cwd()): string[] {
  const files = stageHeat(root, dest);
  const bytes = files.reduce((n, f) => n + fs.statSync(path.join(root, dest, f)).size, 0);
  const per = HEAT_SHIP.map((h) => `${h.dir} ${files.filter((f) => h.re.test(f)).length}`).join(', ');
  const line = files.length > 0
    ? `Heat reader set: ${files.length} files, ${(bytes / 1e6).toFixed(1)} MB, staged in ${dest}/ for upload (${per}).`
    : 'Heat reader set: none on this commit (no python/heat_reader, python/oracle or research/oracle_heat/latest packs); nothing extra to upload.';
  console.log(line);
  if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY, `${line}\n`);
  if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, `files=${files.length}\n`);
  return files;
}

export interface Undeployed { sha: string; subject: string; bot: string[] }

/**
 * Earlier pushes since the last deploy that changed bot code: the first-parent commits after the last deploy up to
 * the branch's previous head, each with the bot code it changed. None of them got a deploy of its own (a `[skip ci]`
 * push starts no workflow; a failed deploy, or a pending run the concurrency group cancelled, is not a successful
 * one), so this deploy ships them batched. Empty when the previous head is unknown or is the base itself.
 */
export function undeployed(root: string, base: string, before: string, bundled: ReadonlySet<string> | null, has: (sha: string) => boolean, max = 50): Undeployed[] {
  if (!before || before === base || ZERO.test(before) || !SHA.test(before) || !has(before)) return [];
  const out: Undeployed[] = [];
  const commits = git(root, ['log', '--first-parent', `--max-count=${max}`, '--format=%H%x09%s', `${base}..${before}`]).split('\n').filter(Boolean);
  for (const line of commits.reverse()) {
    const [sha, subject = ''] = line.split('\t');
    const { files, deleted } = changedFiles(root, `${sha}^1`, sha);
    const { bot } = classify(files, bundled, deleted);
    if (bot.length > 0) out.push({ sha, subject, bot });
  }
  return out;
}

const list = (files: readonly string[], max = 40) =>
  files.slice(0, max).map((f) => `\`${f}\``).join(', ') + (files.length > max ? ` and ${files.length - max} more` : '');

const batched = (u: readonly Undeployed[]) =>
  `earlier pushes since the last deploy changed bot code without a deploy of their own (\`[skip ci]\`, or a failed or cancelled deploy); this deploy ships them with this push: ${u.map((c) => `\`${c.sha.slice(0, 7)}\` ${c.subject}`).join('; ')}`;

export function summary(d: Decision, head: string, base: { sha: string; kind: string } | null, notes: readonly string[] = [], late: readonly Undeployed[] = []): string {
  const lines: string[] = [];
  if (!d.deploy) {
    lines.push(`### No deploy: ${d.why}`);
    lines.push(d.research.length > 0 ? `research-only: ${list(d.research)}; bot not restarted.` : 'No file differs from the last deploy; bot not restarted.');
  } else {
    lines.push(`### Deploying: ${d.why}`);
    if (d.tagIgnored) lines.push(`**Warning:** \`${SKIP_TAG}\` ignored: ${d.bot.length > 0 ? 'this push changes bot code' : 'what changed is unknown'}, so it gets its own deploy and restart (no batching).`);
    if (late.length > 0) lines.push(`**Warning (batched):** ${batched(late)}.`);
    if (d.bot.length > 0) lines.push(`Bot code: ${list(d.bot)}.`);
    if (d.research.length > 0) lines.push(`Research-only, also changed: ${list(d.research)}.`);
  }
  if (base) lines.push(`Compared ${head.slice(0, 7)} with ${base.kind} (\`${base.sha.slice(0, 7)}\`).`);
  lines.push(...notes);
  return lines.join('\n\n') + '\n';
}

export function main(env: NodeJS.ProcessEnv = process.env, root = process.cwd()): Decision {
  const event = env.EVENT_NAME ?? '', message = env.HEAD_MESSAGE ?? '', notes: string[] = [];
  let d: Decision, base: { sha: string; kind: string } | null = null, head = '', late: Undeployed[] = [];
  try {
    head = git(root, ['rev-parse', 'HEAD']).trim();
    if (event !== 'push') d = decide({ event, files: [], bundled: null, message });
    else {
      const has = (sha: string) => spawnSync('git', ['cat-file', '-e', `${sha}^{commit}`], { cwd: root }).status === 0;
      const before = (env.BEFORE ?? '').trim();
      const b = chooseBase((env.PREV_DEPLOY ?? '').trim(), before, has, (env.PREV_LOOKUP ?? '').trim());
      if (b.sha === null) d = decide({ event, files: null, bundled: null, message, unknown: b.why });
      else {
        base = b;
        let bundled: Set<string> | null = null;
        try { bundled = env.ESBUILD ? bundleInputs(root, env.ESBUILD) : null; } catch { bundled = null; }
        if (bundled === null) notes.push('Bundle check unavailable: every research/ source file counted as bot code.');
        const { files, deleted } = changedFiles(root, b.sha);
        d = decide({ event, files, deleted, bundled, message });
        // Only a warning: whatever it finds is already in this deploy.
        if (d.bot.length > 0) try { late = undeployed(root, b.sha, before, bundled, has); } catch { late = []; }
      }
    }
  } catch (e) {
    d = decide({ event: 'push', files: null, bundled: null, message, unknown: `could not tell what changed (${(e as Error).message.split('\n')[0]})` });
  }
  const parts = [`deploy=${d.deploy}: ${d.why}`, d.bot.length ? `bot code: ${d.bot.join(', ')}` : '', d.research.length ? `research-only: ${d.research.join(', ')}` : '', ...notes];
  console.log(parts.filter(Boolean).join('; '));
  if (d.tagIgnored) console.log(`::warning title=${SKIP_TAG} ignored::${d.bot.length > 0 ? 'This push changes bot code' : 'What changed since the last deploy is unknown'}, so it deploys and restarts the bot on its own.`);
  // Workflow command data: % and line breaks escaped (a commit subject can hold a %).
  if (late.length > 0) console.log(`::warning title=Batched deploy::${batched(late).replace(/`/g, '').replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A')}`);
  if (env.GITHUB_STEP_SUMMARY) fs.appendFileSync(env.GITHUB_STEP_SUMMARY, summary(d, head, base, notes, late));
  if (env.GITHUB_OUTPUT) fs.appendFileSync(env.GITHUB_OUTPUT, `deploy=${d.deploy}\n`);
  return d;
}

const runAsScript = () => {
  try { return import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1] ?? '')).href; } catch { return false; }
};
if (runAsScript()) {
  const at = process.argv.indexOf('--stage-heat');
  if (at >= 0) stageHeatMain(process.argv[at + 1] ?? '');
  else main();
}
