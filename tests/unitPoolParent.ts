// The parent of the pool's signal test in tests/historyTwin.test.ts: runs two hanging units and waits (the test sends it SIGTERM, as the workflow's `timeout` does).
// Not a test file itself (the runner only picks up *.test.ts).
import path from 'path';
import { runUnits } from '../research/history/unitPool';

const [dir, a, b] = process.argv.slice(2);
runUnits([{ id: 'h1', spec: { kind: 'hang', pidFile: a } }, { id: 'h2', spec: { kind: 'hang', pidFile: b } }], { script: path.join(process.cwd(), 'tests/unitPoolChild.ts'), dir, label: 'sig', jobs: 2, execArgv: ['--import', 'tsx'] })
  .then(() => process.exit(0), (e) => { console.error(String(e.message)); process.exit(1); });
