// The child of tests/historyTwin.test.ts's pool tests: `node --import tsx tests/unitPoolChild.ts --stage unit --unit-file F` answers one unit through
// research/history/unitPool.ts serveUnit, as research/historyTwin.ts's `--stage unit` does. Not a test file itself (the runner only picks up *.test.ts).
import fs from 'fs';
import path from 'path';
import { recordingLines } from '../bot/marketdata/recordingFiles';
import { serveUnit } from '../research/history/unitPool';

const sleep = (ms: number) => new Promise<void>((ok) => setTimeout(ok, ms));
/** Waits until `file` exists (at most `ms`); true when it does. */
async function until(file: string, ms: number): Promise<boolean> { const end = Date.now() + ms; while (Date.now() < end) { if (fs.existsSync(file)) return true; await sleep(25); } return fs.existsSync(file); }

void serveUnit(async (spec, id) => {
  switch (spec.kind) {
    case 'echo': await sleep(spec.ms ?? 0); return { id, n: spec.n * 2, pid: process.pid };
    case 'env': return { heap: process.env.NODE_OPTIONS, ppid: process.ppid };
    // two units that can only both answer true when they run AT THE SAME TIME
    case 'meet': { fs.writeFileSync(path.join(spec.dir, `${spec.me}.here`), ''); return { met: await until(path.join(spec.dir, `${spec.other}.here`), spec.wait ?? 20_000) }; }
    // how many of these units are alive at once (each leaves a file while it runs)
    case 'track': { const mine = path.join(spec.dir, `alive-${process.pid}`); fs.writeFileSync(mine, ''); await sleep(spec.ms ?? 300); const n = fs.readdirSync(spec.dir).filter((f) => f.startsWith('alive-')).length; fs.rmSync(mine); return { n }; }
    case 'fail': { if (spec.waitFor) for (const f of spec.waitFor) await until(f, 20_000); throw new Error(`${spec.msg}\nsecond line, never printed`); }
    case 'hang': { fs.writeFileSync(spec.pidFile, String(process.pid)); await new Promise(() => setInterval(() => undefined, 1000)); return undefined; }
    case 'exit': process.exit(spec.code); return undefined;
    // fills the heap until V8 aborts ("Fatal process out of memory"): node's 'exit' event then says code null, signal SIGABRT (not 134)
    case 'oom': { const keep: number[][] = []; for (;;) keep.push(new Array(100_000).fill(Math.random())); }
    // what the kernel's out-of-memory killer does to a process: SIGKILL
    case 'selfkill': { process.kill(process.pid, 'SIGKILL'); await sleep(10_000); return undefined; }
    // a day file that is not gzip: the error comes from a stream, as a corrupt recorded day's does
    case 'read': { let n = 0; for await (const l of recordingLines(spec.file)) n += l.length; return { n }; }
    default: throw new Error(`unknown unit kind ${spec.kind}`);
  }
});
