import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { TapeWriter, readTape, recordSnnTape, TAPE_OP } from '../research/snnTape';
import { DEFAULT_SNN } from '../bot/snn/params';
import { replayAtlasSnnTape } from '../research/opportunity/snnReplay';
import type { AtlasSnnState } from '../research/opportunity/snnState';

const start = Date.UTC(2023, 0, 2), sha = 'a'.repeat(64);
const params = { ...DEFAULT_SNN, nE: 8, nI: 2, nL1: 4 };
test('observed tape mode removes stale prices while preserving the legacy replay default', async (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-source-age-')); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const rows: object[] = [{ t: start, k: 'index', asset: 'BTC', value: 100, ts: start, src: 'kalshi' }];
  for (let sec = 1; sec <= 5; sec++) rows.push({ t: start + sec * 1000, k: 'book', ticker: 'KXBTC-FIXTURE', bids: [], asks: [] });
  rows.push({ t: start + 6000, k: 'index', asset: 'BTC', value: 110, ts: start + 6000, src: 'kalshi' });
  fs.writeFileSync(path.join(root, 'md-2023-01-02.jsonl'), rows.map((r) => JSON.stringify(r)).join('\n') + '\n');
  const counts: Record<string, Map<number, number>> = {};
  for (const [name, maximumInputPriceAgeMs] of [['legacy', undefined], ['observed', 3000]] as const) {
    const file = path.join(root, `${name}.tape`);
    await recordSnnTape(root, file, { params, domain: 'crypto', skipModel: true, lean: true, maximumInputPriceAgeMs });
    counts[name] = new Map([...readTape(file)].filter((o) => o.op === TAPE_OP.STEP).map((o) => [o.T, o.inputs.length]));
  }
  assert.equal(counts.legacy.get(start + 4000), 2);
  assert.equal(counts.observed.get(start + 4000), 0);
  assert.equal(counts.observed.get(start + 6000), 2);
});

test('one missing asset cannot earn direction labels from held prices while another keeps the clock alive', (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-column-age-')); t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, 'partial.tape'), w = new TapeWriter(file);
  const input = (asset: string, price: number) => ({ key: `${asset}-15m`, asset, price, mid: undefined, values: {} });
  w.step(start, [input('BTC', 100), input('ETH', 100)]);
  w.step(start + 1000, [input('BTC', 110), input('ETH', 100)]);
  for (let sec = 2; sec <= 900; sec++) w.step(start + sec * 1000, [input('ETH', 100)]);
  w.step(start + 901000, [input('BTC', 200), input('ETH', 100)]); w.close();
  const states: AtlasSnnState[] = [], final: AtlasSnnState[] = [];
  const r = replayAtlasSnnTape(file, { variant: 'S6', sourceSha256: sha, params, inputLagMs: 0, maximumInputPriceAgeMs: 3000,
    everyMs: 1000, onState: (s) => { if (s.asOf === start + 900000) states.push(s); if (s.asOf === start + 901000) final.push(s); } });
  const missing = states[0].columns.find((c) => c.asset === 'BTC')!;
  assert.equal(missing.values.observed_input_available, 0);
  assert.ok(Object.entries(missing.values).every(([k, v]) => k === 'observed_input_available' || v === null));
  assert.equal(r.unavailableColumnResets, 1); assert.equal(r.gapResets, 0);
  assert.equal(final[0].columns.find((c) => c.asset === 'BTC')!.values.readout_labelled, 0);
  const sparse: AtlasSnnState[] = [];
  const sparseReport = replayAtlasSnnTape(file, { variant: 'S6', sourceSha256: sha, params, inputLagMs: 0, maximumInputPriceAgeMs: 3000,
    everyMs: 1000, captureAt: new Set([start + 900000, start + 901000]), onState: (s) => sparse.push(s) });
  assert.deepEqual(sparse, [states[0], final[0]]);
  assert.equal(sparseReport.checkpointSha256, r.checkpointSha256, 'sampling observers cannot change learned weights or running state');
  assert.equal(sparseReport.snapshots, 2);
});
