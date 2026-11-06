import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { test } from 'node:test';
import { foldOf, judge, loadRows, logistic } from '../research/snnLeadJudge';

test('logistic recovers a known slope', () => {
  const X: number[][] = [], y: number[] = [];
  let s = 1;
  const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
  for (let i = 0; i < 4000; i++) { const x = rnd() * 4 - 2; X.push([1, x]); y.push(rnd() < 1 / (1 + Math.exp(-(0.5 + 1.5 * x))) ? 1 : 0); }
  const { b } = logistic(X, y);
  assert.ok(Math.abs(b[1] - 1.5) < 0.25, String(b));
});

test('folds are 16 days from Aug 1', () => {
  assert.equal(foldOf(Date.parse('2026-08-01T00:00:00Z')), 0);
  assert.equal(foldOf(Date.parse('2026-08-17T00:00:00Z')), 1);
  assert.equal(foldOf(Date.parse('2026-11-04T00:00:00Z')), 5);
});

test('the judge pairs arms, reads the gap and runs H-B on synthetic rows', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'h1-'));
  const write = (arm: string, f: (m: number, g: number, y: number) => number) => {
    const rows: string[] = [];
    let s = 7;
    const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
    for (let d = 0; d < 40; d++) for (let e = 0; e < 20; e++) {
      const t0 = Date.parse('2026-08-07T00:00:00Z') + d * 86_400_000 + e * 3_600_000;
      const truth = 0.2 + 0.6 * rnd(), y = rnd() < truth ? 1 : 0;
      for (let j = 0; j < 5; j++) {
        const m = Math.min(0.95, Math.max(0.05, truth - 0.04 + 0.01 * j)), g = (truth - m) * 100;
        rows.push(JSON.stringify({ t: t0 + j * 60_000, k: `K${d}-${e}`, e: `E${d}-${e}`, c: 'BTC-15m', kd: 'updown', p: f(m, g, y), m, f: truth, y, s: 0.02, g, x: 60000 + j, v: 1 }));
      }
    }
    fs.mkdirSync(path.join(dir, arm, 'run1'), { recursive: true });
    fs.writeFileSync(path.join(dir, arm, 'run1', 'rows-h-2026-08-07.jsonl.gz'), zlib.gzipSync(rows.join('\n') + '\n'));
  };
  write('C', (m) => m);
  write('G', (m, g) => m + g / 100);
  assert.ok(loadRows(path.join(dir, 'C')).size > 0);
  const out = judge(['--arms', `C:1=${path.join(dir, 'C')},G:1=${path.join(dir, 'G')}`]);
  assert.match(out, /## 2\. Paired/);
  const line = out.split('\n').find((l) => l.startsWith('| G:1 |') && l.includes('/3'))!;
  assert.match(line, /\| -0\.\d+ \[/);
  assert.match(out, /toward the gap/);
  if (process.env.SHOW_JUDGE) console.log(out);
});
