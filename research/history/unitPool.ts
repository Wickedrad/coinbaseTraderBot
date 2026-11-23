// A small pool of child processes for the history-twin stages (round S1: `--stage match --jobs N`, `--stage features --jobs N`).
//
// The stages' day passes are independent of each other (one real day, one source's day), one node process uses one core, and a
// runner has four: the parent hands each unit to a child (`node --import tsx research/historyTwin.ts --stage unit --unit-file F`)
// and keeps everything global (the order of the files, the lines it prints, the checks). The protocol is two small JSON files in a
// temp folder under the stage's --out: the parent writes `uN.in.json` ({id, spec}), the child answers `uN.out.json`
// ({ok: true, result} or {ok: false, error}) and exits. Children print nothing (stdio is ignored): the repository is public, a
// child's own words never reach a log; the only text that crosses is the one-line error of a failed unit, which the parent prints
// as its own `[twin] ERROR:` line. Nothing here reads a recording or a clock that feeds an output.
//
// The pool never leaves a child behind: the first failed unit stops the launching and terminates the running children (and waits
// for them), a SIGTERM/SIGINT/SIGHUP of the parent (the workflow's `timeout`) kills them, a parent that is gone makes a child
// exit (it checks its parent every few seconds), and the temp folder is removed on every path that can run code.

import { spawn, type ChildProcess } from 'child_process';
import fs from 'fs';
import path from 'path';

/** The prefix of the pool's temp folder under the stage's --out. A folder a killed run left behind is removed by the next pool. */
export const UNIT_TMP_PREFIX = '.twin-units-';
/** The heap each child gets (MB) unless TWIN_CHILD_HEAP_MB says another: the job-level 12288 of the parent times four children would not fit a 16 GB runner. */
export const DEFAULT_CHILD_HEAP_MB = 3072;

export interface PoolUnit { id: string; spec: unknown }
export interface PoolOptions {
  /** The script a child runs: `node ...execArgv SCRIPT --stage unit --unit-file FILE` (an absolute path). */
  script: string;
  /** The stage's --out: the pool makes (and removes) its temp folder here. */
  dir: string;
  /** Names the stage in messages and in the temp folder: 'match' or 'features'. */
  label: string;
  /** How many children run at once (clamped to 1..units). */
  jobs: number;
  /** Called in the parent, as each unit finishes, with its index and result (a throw fails the pool like a failed unit). */
  onResult?: (index: number, result: any) => void;
  /** The heap of each child, MB (default TWIN_CHILD_HEAP_MB, else DEFAULT_CHILD_HEAP_MB). */
  heapMb?: number;
  /** The parent's environment (default process.env) and node arguments (default process.execArgv without the test runner's and the inspector's). */
  env?: NodeJS.ProcessEnv;
  execArgv?: string[];
}

/** The parent's NODE_OPTIONS with its own heap flag taken out and the child's put in. */
export function childNodeOptions(parent: string | undefined, heapMb: number): string {
  const kept = (parent ?? '').split(/\s+/).filter(Boolean);
  const out: string[] = [];
  for (let i = 0; i < kept.length; i++) {
    if (/^--max[-_]old[-_]space[-_]size(=|$)/.test(kept[i])) { if (!kept[i].includes('=')) i++; continue; }
    out.push(kept[i]);
  }
  return [...out, `--max-old-space-size=${heapMb}`].join(' ');
}

/** The node arguments a child gets: the parent's (so `--import tsx` is the same), without the test runner's, the watcher's and the inspector's. */
export function childExecArgv(argv: readonly string[] = process.execArgv): string[] {
  const out: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--test' || /^--test-/.test(a) || /^--watch/.test(a) || /^--inspect/.test(a)) {
      if (!a.includes('=') && argv[i + 1] !== undefined && !argv[i + 1].startsWith('-') && /^--(test-|watch-path)/.test(a)) i++; // `--test-name-pattern X`: its value goes too
      continue;
    }
    out.push(a);
  }
  return out;
}

const oneLine = (e: unknown): string => String((e as any)?.message ?? e).split('\n')[0].slice(0, 400);

/** What the parent says about a child that exited and left no answer (the text after `its process `). Node's 'exit' event reports a V8 heap abort
 *  ("Fatal process out of memory") as code null, signal SIGABRT; 134 is the SHELL's number for the same abort and only arrives through a wrapper,
 *  so both are read as heap exhaustion. The kernel's out-of-memory killer (and anything else that sends SIGKILL) arrives as code null, signal
 *  SIGKILL (137 through a shell). Any other exit gets no guess. The hint says where the heap is set (the env of the workflow step: there is no
 *  dispatch input for it or for --jobs) and what bounds it: `jobs` children of `heapMb` plus the parent have to fit the runner's 16 GB. */
export function noAnswerMessage(code: number | null, signal: NodeJS.Signals | null, heapMb: number, jobs: number): string {
  const how = `exited with code ${code}${signal ? ` (signal ${signal})` : ''} and left no result`;
  const budget = `${jobs} job(s) x ${heapMb} MB; jobs x heap must stay under about 12 GB of the runner's 16 GB`;
  if (signal === 'SIGABRT' || code === 134) return `${how} (node ran out of memory at the child heap TWIN_CHILD_HEAP_MB = ${heapMb} MB, set in the env of the step "Match, fill in, and describe every contract both ways" of history-twin.yml, so changing it is a workflow edit; ${budget})`;
  if (signal === 'SIGKILL' || code === 137) return `${how} (killed from outside, most likely by the kernel's out-of-memory killer because the runner's memory ran out; TWIN_CHILD_HEAP_MB = ${heapMb} MB is set in the env of the step "Match, fill in, and describe every contract both ways" of history-twin.yml; ${budget})`;
  return how;
}

/** Run the units, at most `jobs` at a time, each in its own child process; the results come back in the units' order. The first failed
 *  unit rejects the whole pool with its own message (prefixed by the stage and the unit), after every other child is gone. */
export async function runUnits<R = unknown>(units: readonly PoolUnit[], o: PoolOptions): Promise<R[]> {
  if (!units.length) return [];
  const jobs = Math.max(1, Math.min(Math.floor(o.jobs) || 1, units.length));
  fs.mkdirSync(o.dir, { recursive: true });
  for (const f of fs.readdirSync(o.dir)) if (f.startsWith(UNIT_TMP_PREFIX)) fs.rmSync(path.join(o.dir, f), { recursive: true, force: true });
  const tmp = fs.mkdtempSync(path.join(o.dir, `${UNIT_TMP_PREFIX}${o.label}-`));
  const inFile = (i: number) => path.join(tmp, `u${i}.in.json`), outFile = (i: number) => path.join(tmp, `u${i}.out.json`);
  const heap = o.heapMb ?? (Number(process.env.TWIN_CHILD_HEAP_MB) || DEFAULT_CHILD_HEAP_MB);
  const env = { ...(o.env ?? process.env), NODE_OPTIONS: childNodeOptions((o.env ?? process.env).NODE_OPTIONS, heap) };
  const execArgv = o.execArgv ?? childExecArgv();
  const results: R[] = new Array(units.length);
  const children = new Map<ChildProcess, number>();
  let failure: Error | undefined, next = 0, running = 0, killTimer: NodeJS.Timeout | undefined;
  const killAll = (sig: NodeJS.Signals) => { for (const c of children.keys()) { try { c.kill(sig); } catch { /* already gone */ } } };
  const onSignal = (sig: NodeJS.Signals) => { killAll('SIGKILL'); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* best effort */ } process.exit(sig === 'SIGINT' ? 130 : 143); };
  const onExit = () => killAll('SIGKILL');
  const signals: NodeJS.Signals[] = ['SIGTERM', 'SIGINT', 'SIGHUP'];
  for (const s of signals) process.on(s, onSignal);
  process.on('exit', onExit);
  try {
    for (const [i, u] of units.entries()) fs.writeFileSync(inFile(i), JSON.stringify({ id: u.id, spec: u.spec }));
    await new Promise<void>((resolve) => {
      const fail = (message: string) => {
        if (failure) return;
        failure = new Error(message);
        killAll('SIGTERM');
        killTimer = setTimeout(() => killAll('SIGKILL'), 10_000);
      };
      const pump = () => {
        while (!failure && running < jobs && next < units.length) start(next++);
        if (running === 0 && (failure || next >= units.length)) resolve();
      };
      const settle = (i: number, child: ChildProcess, code: number | null, signal: NodeJS.Signals | null, startErr?: Error) => {
        if (!children.delete(child)) return; // 'error' and 'exit' can both fire: the first one settles
        running--;
        let answer: { ok: boolean; result?: R; error?: string } | undefined;
        try { answer = JSON.parse(fs.readFileSync(outFile(i), 'utf8')); } catch { answer = undefined; }
        const who = `${o.label} ${units[i].id}`;
        if (!startErr && code === 0 && answer?.ok) {
          results[i] = answer.result as R;
          try { o.onResult?.(i, answer.result); } catch (e) { fail(`${who}: ${oneLine(e)}`); }
        } else if (answer && !answer.ok) fail(`${who}: ${answer.error ?? 'failed'}`);
        else if (startErr) fail(`${who}: its process could not be started (${oneLine(startErr)})`);
        else fail(`${who}: its process ${noAnswerMessage(code, signal, heap, jobs)}`);
        pump();
      };
      const start = (i: number) => {
        running++;
        const child = spawn(process.execPath, [...execArgv, o.script, '--stage', 'unit', '--unit-file', inFile(i)], { env, stdio: 'ignore', cwd: process.cwd() });
        children.set(child, i);
        child.once('error', (e) => settle(i, child, null, null, e));
        child.once('exit', (code, signal) => settle(i, child, code, signal));
      };
      pump();
    });
    if (failure) throw failure;
    return results;
  } finally {
    if (killTimer) clearTimeout(killTimer);
    killAll('SIGKILL'); // none is left when the pool is done; this only matters on a path that threw before the pool started them all
    for (const s of signals) process.off(s, onSignal);
    process.off('exit', onExit);
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

/** The child's side: read the unit file named by `--unit-file`, run the handler, write the answer next to it and exit (0 on success, 1 with the
 *  error's first line in the answer on a failure, including an uncaught exception: a corrupt gzip day throws from a stream, not from the handler). */
export async function serveUnit(handler: (spec: any, id: string) => Promise<unknown>, argv: readonly string[] = process.argv): Promise<never> {
  const at = argv.indexOf('--unit-file'), inFile = at >= 0 ? argv[at + 1] : '';
  if (!inFile || !/\.in\.json$/.test(inFile)) { console.error('[twin] ERROR: unit: --unit-file FILE.in.json is needed'); process.exit(1); }
  const outFile = inFile.replace(/\.in\.json$/, '.out.json');
  const write = (o: object) => { fs.writeFileSync(`${outFile}.tmp`, JSON.stringify(o)); fs.renameSync(`${outFile}.tmp`, outFile); };
  const die = (e: unknown): never => { try { write({ ok: false, error: oneLine(e) }); } catch { /* the parent reports a unit with no answer */ } process.exit(1); };
  process.on('uncaughtException', die);
  process.on('unhandledRejection', die);
  // the parent's pid: when it is gone (killed: this process is adopted by another), do not go on alone
  const parent = process.ppid;
  setInterval(() => { if (process.ppid !== parent) process.exit(1); }, 5000).unref();
  try {
    const { id, spec } = JSON.parse(fs.readFileSync(inFile, 'utf8'));
    write({ ok: true, result: await handler(spec, id) });
  } catch (e) { die(e); }
  process.exit(0);
}
