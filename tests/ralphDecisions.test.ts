// Ralph Phase A, iteration 0049: heat decision receipts. HeatLane.decide hands an optional read-only observer the input and the
// result of each pass; the research tap journals them in the frame chain; replayDecisions.ts feeds the stored input back through
// decideHeat. These tests pin: the observer cannot change a decision, the receipt is taken before the lane changes its book,
// the journal with receipts verifies, a doctored receipt is caught, and the seam stays confined to its two call sites.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import {
  HeatLane, decideHeat, type HeatDecideInput, type HeatDecideResult, type HeatLaneState, type HeatWindows,
} from '../bot/heat/heatLane';
import type { HeatCallRow, HeatConfig, HeatMarketView, HeatSnapshot } from '../bot/heat/types';
import { RawFrameTap, decodeDecisionJson, encodeDecisionJson, sha256, MAX_DECISION_BYTES, type TapClock } from '../research/ralph_capture/rawTap';
import { firstDifference, replayDecisionFile, replayDecisionLines, replayPassed } from '../research/ralph_capture/replayDecisions';
import { loadConfig } from '../bot/config';

const VERIFY = path.resolve('research/ralph_capture/verify_journal.py');
const S = 1000, MIN = 60 * S;
const T0 = Date.UTC(2026, 10, 11, 15, 0, 0);
const NOW = T0 + 5 * S;
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'ralph-dec-'));
/** Recomputes the chain over edited lines, as a forger with write access would (the numbers stay, the hashes follow the bodies). */
function rechain(lines: string[]): string[] {
  let prev = '0'.repeat(64);
  return lines.map((l) => { const body = l.slice(l.indexOf('\t') + 1); const h = sha256(prev + '\n' + body); prev = h; return `${h}\t${body}`; });
}
function stepClock(): TapClock { let w = 1_800_000_000_000, m = 5_000_000_000n; return { wallMs: () => (w += 7), monoNs: () => (m += 7_000_000n) }; }
function verify(file: string, anchor?: string): any {
  const r = spawnSync('python3', ['-I', VERIFY, file, ...(anchor ? ['--anchor', anchor] : [])], { encoding: 'utf8' });
  return { code: r.status, report: JSON.parse(r.stdout) };
}

const DEFAULTS = {
  enabled: true, callsFile: '', assets: ['BTC', 'ETH', 'SOL', 'XRP'], horizons: [15, 60], topN: 10, maxAgeSec: 90, entryLagSec: 45,
  sizing: true, context: 'size', contextBoost: 0.25, maxOpen: 2, maxPerCoin: 1, cooldownSec: 60, reentries15m: 3, reentriesHourly: 6, reentryLossStop: 0.5,
  flatTrips: 30, pilotLossUsd: 15, feeNetCheck: false, perps: 'entry', perpHorizons: [60, 240], perpsDaily: 'context', pairConflict: 'skip', dial: 'off', dialPriorTrips: 20, dialPriorReturn: -0.05, dialScale: 0.1, dialFloor: 0.2, dialMax: 2,
};
const settings = (): HeatConfig => ({ ...DEFAULTS }) as HeatConfig;
const WINDOWS: HeatWindows = { entryWindowUpdown: [840, 300], entryWindowHourly: [3300, 600], hourlyMidBand: [0.1, 0.9] };
const OPTS = { orderMin: 10, orderMax: 20, minSide: 0.1, live: false, windows: WINDOWS };
const row = (o: Partial<HeatCallRow> = {}): HeatCallRow => ({ key: '1m:RSI14=very low', kind: 'single', tf: 1, h: 15, dir: 1, rank: 1, of: 40, heat: 100, share: 0.53, odds: 3, barClose: T0, ...o });
const snap = (rows: HeatCallRow[]): HeatSnapshot => ({ source: 'oracle-heat', run: 'R1', packSha: 'pack', writtenAt: T0 + 2 * S, coins: new Map([['BTC', { asOf: T0, tableSha: 'table', ok: true, calls: rows }]]) });
const m15 = (o: Partial<HeatMarketView> = {}): HeatMarketView => ({ ticker: 'KXBTC15M-1015', asset: 'BTC', kind: '15m', closeTs: NOW + 600 * S, openTs: NOW - 300 * S, yesBid: 0.49, yesAsk: 0.51, position: 0, working: 0, ...o });
/** A lane past its flat phase, so a hot call becomes a plan. */
const seasonedLane = (): HeatLane => { const l = new HeatLane(settings()); (l as unknown as { st: HeatLaneState }).st.trips = 30; return l; };

// ---- the observer cannot change a decision ----

test('a lane with an observer decides exactly as one without', () => {
  const plain = seasonedLane(), watched = seasonedLane();
  const seen: Array<[HeatDecideInput, HeatDecideResult]> = [];
  watched.receiptSink = (i, r) => { seen.push([i, r]); };
  const a = plain.decide(NOW, snap([row()]), [m15()], OPTS);
  const b = watched.decide(NOW, snap([row()]), [m15()], OPTS);
  assert.deepEqual(b, a);
  assert.ok(a.plans.length === 1, 'the fixture really produces a plan');
  assert.equal(seen.length, 1);
});

test('an observer that throws cannot change the decision or the lane book', () => {
  const plain = seasonedLane(), broken = seasonedLane();
  broken.receiptSink = () => { throw new Error('observer bug'); };
  const a = plain.decide(NOW, snap([row()]), [m15()], OPTS);
  const b = broken.decide(NOW, snap([row()]), [m15()], OPTS);
  assert.deepEqual(b, a);
  assert.deepEqual((broken as unknown as { st: unknown }).st, (plain as unknown as { st: unknown }).st);
});

test('the observer is called after decideHeat and before the lane changes its book', () => {
  const lane = seasonedLane();
  let atCall: string | undefined;
  lane.receiptSink = (i) => { atCall = encodeDecisionJson(i); };
  lane.decide(NOW, snap([row()]), [m15()], OPTS);
  const state = (JSON.parse(atCall!) as { state: HeatLaneState }).state;
  assert.deepEqual(Object.keys(state.acted), [], 'no call is claimed yet when the receipt is taken');
  assert.ok(Object.keys((lane as unknown as { st: HeatLaneState }).st.acted).length > 0, 'the lane claims the call right after');
});

test('the stored input, replayed, gives the stored result (the receipt is taken before the book changes)', () => {
  const lane = seasonedLane();
  let inText = '', outText = '';
  lane.receiptSink = (i, r) => { inText = encodeDecisionJson(i); outText = encodeDecisionJson(r); };
  lane.decide(NOW, snap([row()]), [m15()], OPTS);
  assert.deepEqual(JSON.parse(encodeDecisionJson(decideHeat(decodeDecisionJson(inText) as HeatDecideInput))), JSON.parse(outText));
});

// ---- the journal ----

/** A tap with a short, valid session: one connection, a subscribe command, one book snapshot and a few decisions from a real lane. */
async function session(decisions: number, edit?: (tap: RawFrameTap) => void): Promise<{ file: string; anchor: string; tap: RawFrameTap }> {
  const dir = tmp();
  const file = path.join(dir, 'j.journal'), anchor = path.join(dir, 'j.anchor');
  const tap = new RawFrameTap({ file, anchorFile: anchor, config: { tool: 'test', mode: 'paper' }, clock: stepClock(), anchorEvery: 2 });
  tap.connecting(); tap.opened(); tap.sent('{"id":1,"cmd":"subscribe","params":{"channels":["orderbook_delta"]}}');
  tap.frame(Buffer.from(JSON.stringify({ type: 'orderbook_snapshot', sid: 1, seq: 1, msg: { market_ticker: 'KXBTC15M-1015', yes_dollars_fp: [['0.4900', '10.00']] } })), false);
  const lane = seasonedLane();
  lane.receiptSink = (i, r) => tap.decision(i, r);
  for (let k = 0; k < decisions; k++) {
    // a later bar each time, so each pass rules on a fresh call
    const t = T0 + k * MIN;
    lane.decide(t + 5 * S, { ...snap([row({ barClose: t })]), coins: new Map([['BTC', { asOf: t, tableSha: 'table', ok: true, calls: [row({ barClose: t })] }]]), writtenAt: t + 2 * S }, [m15({ closeTs: t + 605 * S })], OPTS);
  }
  edit?.(tap);
  tap.closed(1000);
  await tap.close();
  return { file, anchor, tap };
}

test('a journal with decision receipts verifies, the footer counts them, and the replay reproduces every one', async () => {
  const { file, anchor, tap } = await session(3);
  const { code, report } = verify(file, anchor);
  assert.equal(code, 0, JSON.stringify(report.reasons));
  assert.equal(report.locally_consistent, true);
  assert.equal(report.notes.decisions, 3);
  assert.equal(report.notes.decisions_unrecorded, 0);
  assert.equal(report.notes.footer.failed, null);
  assert.equal(report.decision_replay_checked_here, false);
  assert.equal(tap.status().decisions, 3);
  const r = await replayDecisionFile(file);
  assert.deepEqual([r.decisions, r.replayed, r.matched, r.mismatched, r.unrecorded, r.hashMismatch], [3, 3, 3, 0, 0, 0]);
  assert.ok(replayPassed(r));
});

test('the stored snapshot survives the journal: a Map is written as $map and comes back as a Map', () => {
  const text = encodeDecisionJson({ snapshot: snap([row()]), s: new Set([1, 2]) });
  assert.ok(text.includes('"$map"') && text.includes('"$set"'));
  const back = decodeDecisionJson(text) as { snapshot: HeatSnapshot; s: Set<number> };
  assert.ok(back.snapshot.coins instanceof Map && back.snapshot.coins.get('BTC')!.calls[0].key === '1m:RSI14=very low');
  assert.deepEqual([...back.s], [1, 2]);
});

test('a doctored result is caught by the replay even when the whole chain is recomputed, the hash fixed up and the record respaced', async () => {
  const { file } = await session(2);
  const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean);
  const i = lines.findIndex((l) => l.includes('"kind":"decision"'));
  const rec = JSON.parse(lines[i].slice(lines[i].indexOf('\t') + 1));
  const result = JSON.parse(rec.result_json);
  result.plans = []; result.skips = [{ asset: 'BTC', h: 15, key: 'x', reason: 'doctored' }];
  rec.result_json = JSON.stringify(result); rec.result_sha256 = sha256(rec.result_json);
  lines[i] = `x\t${JSON.stringify(rec).replace('"kind":"decision"', '"kind": "decision"')}`;   // spaced, so a keyword filter would miss it
  const r = replayDecisionLines(rechain(lines));
  assert.equal(r.chain, 'intact');
  assert.equal(r.mismatched, 1);
  assert.equal(r.matched, 1);
  assert.match(r.first[0].path, /^\$\.(plans|skips)/);
  assert.ok(!replayPassed(r));
});

test('the replay checks the chain itself: an edit without re-chaining, a deleted tail receipt, a repeated receipt and a missing footer all fail it', async () => {
  const { file } = await session(3);
  const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean);
  assert.ok(replayPassed(replayDecisionLines(lines)));
  const di = lines.map((l, k) => (l.includes('"kind":"decision"') ? k : -1)).filter((k) => k >= 0);
  const edited = lines.map((l, k) => (k === di[0] ? l.replace('KXBTC15M-1015', 'KXBTC15M-9999') : l));
  assert.equal(replayDecisionLines(edited).chain, 'broken');
  assert.ok(!replayPassed(replayDecisionLines(rechain(lines.filter((_, k) => k !== di[2])))), 'deleted receipt: numbering and footer give it away');
  assert.ok(!replayPassed(replayDecisionLines(rechain([...lines.slice(0, di[2] + 1), lines[di[2]], ...lines.slice(di[2] + 1)]))), 'repeated receipt');
  assert.ok(!replayPassed(replayDecisionLines(lines.slice(0, lines.length - 1))), 'no footer');
});

test('a stored text that does not match its recorded hash is reported, not replayed', async () => {
  const { file } = await session(1);
  const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map((l) => (l.includes('"kind":"decision"') ? l.replace('KXBTC15M-1015', 'KXBTC15M-9999') : l));
  const r = replayDecisionLines(rechain(lines));
  assert.equal(r.hashMismatch, 1);
  assert.equal(r.matched, 0);
});

test('editing a stored receipt breaks the chain; re-chaining it is caught by the hash next to the text', async () => {
  const { file } = await session(1);
  const raw = fs.readFileSync(file, 'utf8');
  const edited = path.join(path.dirname(file), 'edited.journal');
  fs.writeFileSync(edited, raw.replace('yesBid', 'yesBld'));
  assert.ok(verify(edited).report.reasons.includes('hash_chain_invalid'));
});

test('a receipt too large, naming an own order, or not serializable is journaled as hashes and a reason; the tap keeps running', async () => {
  const { file, tap } = await session(0, (t) => {
    t.decision({ big: 'x'.repeat(MAX_DECISION_BYTES) }, {});
    t.decision({ msg: { client_order_id: 'abc' } }, {});
    t.decision({ n: 1n }, {});
    t.decision({ ok: true, now: NOW }, { decided: [] });
  });
  assert.equal(tap.status().failed, null);
  const { report } = verify(file);
  assert.equal(report.notes.decisions, 4);
  assert.equal(report.notes.decisions_unrecorded, 3);
  assert.ok(report.reasons.includes('decision_not_recorded'));
  assert.equal(report.locally_consistent, true, 'unrecorded receipts are a coverage gap, not a broken journal');
  const r = replayDecisionLines(fs.readFileSync(file, 'utf8').split('\n').filter(Boolean));
  assert.equal(r.unrecorded, 3);
  assert.ok(!replayPassed(r));
  const stored = fs.readFileSync(file, 'utf8');
  assert.ok(!stored.includes('client_order_id'), 'the own-order identifier never reaches the file');
});

test('receipts after the footer are not written, and a failed tap records none', async () => {
  const { file, tap } = await session(1);
  const size = fs.statSync(file).size;
  tap.decision({ now: 1 }, {});
  assert.equal(fs.statSync(file).size, size);
  assert.equal(tap.status().decisions, 1);
});

test('a journal with no receipts keeps its old footer shape and still verifies', async () => {
  const { file } = await session(0);
  const { code, report } = verify(file);
  assert.equal(code, 0, JSON.stringify(report.reasons));
  assert.equal(report.notes.decisions, 0);
});

// ---- the seam stays small ----

test('the receipt seam is declared once in the lane, called once, and wired only inside the tap block of main.ts', () => {
  const lane = fs.readFileSync('bot/heat/heatLane.ts', 'utf8');
  assert.equal(lane.match(/receiptSink/g)!.length, 3, 'declaration, the guard and the call');
  assert.ok(/if \(this\.receiptSink\) \{ try \{ const p: unknown = this\.receiptSink\(input, res\); if \(p instanceof Promise\) p\.catch\(\(\) => \{\}\); \} catch/.test(lane), 'the call is guarded and swallows a throw or a rejection');
  assert.ok(!/ralph_capture|setRawSink|rawTap/i.test(lane), 'the lane names no tap');
  const main = fs.readFileSync('bot/main.ts', 'utf8');
  const wires = main.match(/receiptSink/g) ?? [];
  assert.equal(wires.length, 1);
  assert.ok(/if \(heatLane && rawTap\?\.tap && cfg\.mode !== 'live'\) \{ const t = rawTap\.tap; heatLane\.receiptSink = \(i, r\) => t\.decision\(i, r\); \}/.test(main), 'wired once, never in live');
  // nothing else in bot/ may touch the sink
  const offenders: string[] = [];
  const walk = (d: string) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else if (/\.(ts|tsx|js)$/.test(e.name) && /receiptSink/.test(fs.readFileSync(p, 'utf8'))) offenders.push(p); } };
  walk('bot');
  assert.deepEqual(offenders.sort(), [path.join('bot', 'heat', 'heatLane.ts'), path.join('bot', 'main.ts')]);
});

// ---- critic round 1 ----

test('a real tap as the observer changes nothing, and the file holds no settings path, pacer budget, working-order count or entry cash', async () => {
  const winds = loadConfig().strategy as unknown as HeatWindows;
  const plain = seasonedLane(), watched = seasonedLane();
  for (const l of [plain, watched]) (l as unknown as { st: HeatLaneState }).st.open.push({ ticker: 'KXETH15M-1015', asset: 'ETH', kind: '15m', side: 'yes', ruleId: 'heat:R1', h: 15, sentAt: NOW - MIN, openedAt: NOW - MIN, stakeUsd: 10, closeTs: NOW + 600 * S, cash0: -9.5, fees0: 0.17 });
  const dir = tmp();
  const tap = new RawFrameTap({ file: path.join(dir, 'j.journal'), config: { tool: 'test' }, clock: stepClock() });
  tap.connecting(); tap.opened();
  watched.receiptSink = (i, r) => tap.decision(i, r);
  const o = { ...OPTS, windows: winds };
  const a = plain.decide(NOW, snap([row()]), [m15({ position: 7, working: 3 })], o);
  const b = watched.decide(NOW, snap([row()]), [m15({ position: 7, working: 3 })], o);
  assert.deepEqual(b, a);
  assert.deepEqual((watched as unknown as { st: unknown }).st, (plain as unknown as { st: unknown }).st);
  tap.closed(1000);
  await tap.close();
  const text = fs.readFileSync(path.join(dir, 'j.journal'), 'utf8');
  for (const gone of ['cash0', 'fees0', '/home/', 'pacer', 'callsFile', 'working', 'sessionRiskPath']) assert.ok(!text.includes(gone), `the journal does not contain ${gone}`);
  assert.ok(text.includes('entryWindowUpdown') && text.includes('\\"position\\":7'), 'what decideHeat reads is kept');
  const r = replayDecisionLines(text.split('\n').filter(Boolean));
  assert.deepEqual([r.decisions, r.matched], [1, 1], 'the projected input still replays to the stored result');
});

test('NaN, Infinity and -0 are kept distinct from null and 0, and a stored receipt cannot swap one for the other unseen', () => {
  const back = decodeDecisionJson(encodeDecisionJson({ a: NaN, b: Infinity, c: -Infinity, d: -0, e: null, f: 0 })) as Record<string, number | null>;
  assert.ok(Number.isNaN(back.a) && back.b === Infinity && back.c === -Infinity && Object.is(back.d, -0) && back.e === null && Object.is(back.f, 0));
  const nan = JSON.parse(encodeDecisionJson({ position: NaN })), nul = JSON.parse(encodeDecisionJson({ position: null }));
  assert.equal(firstDifference(nan, nul)?.path, '$.position');
});

test('a data object that looks like a wrapper is refused, so the receipt cannot decode as something else', async () => {
  assert.throws(() => encodeDecisionJson({ x: { $map: [[1, 2]] } }));
  assert.throws(() => encodeDecisionJson({ x: { $num: 'NaN' } }));
  const { file, tap } = await session(0, (t) => t.decision({ now: NOW, x: { $set: [1] } }, {}));
  assert.equal(tap.status().failed, null);
  const { report } = verify(file);
  assert.equal(report.notes.decisions_unrecorded, 1);
  assert.ok(report.reasons.includes('decision_not_recorded'));
});

test('a key present on one side only is a difference even for __proto__', () => {
  assert.equal(firstDifference(JSON.parse('{"__proto__":{}}'), {})?.path, '$.__proto__');
});

test('an async observer that rejects cannot take the process down', async () => {
  const lane = seasonedLane();
  let unhandled = false;
  const onUnhandled = () => { unhandled = true; };
  process.on('unhandledRejection', onUnhandled);
  lane.receiptSink = (async () => { throw new Error('async observer bug'); }) as unknown as (i: HeatDecideInput, r: HeatDecideResult) => void;
  assert.doesNotThrow(() => lane.decide(NOW, snap([row()]), [m15()], OPTS));
  await new Promise((r) => setTimeout(r, 30));
  process.removeListener('unhandledRejection', onUnhandled);
  assert.equal(unhandled, false);
});

test('with the disk behind, a receipt is written as a reason only and memory does not grow with it', async () => {
  const dir = tmp();
  const tap = new RawFrameTap({ file: path.join(dir, 'j.journal'), config: { tool: 'test' }, clock: stepClock(), maxPendingBytes: 1 });
  tap.connecting(); tap.opened(); tap.sent('{"cmd":"subscribe"}');
  tap.decision({ now: NOW, markets: [], big: 'y'.repeat(100_000) }, {});
  tap.closed(1000);
  await tap.close();
  const text = fs.readFileSync(path.join(dir, 'j.journal'), 'utf8');
  assert.ok(text.includes('"withheld":"backpressure"') && !text.includes('yyyyyyyyyy'));
  const { report } = verify(path.join(dir, 'j.journal'));
  assert.equal(report.notes.decisions_unrecorded, 1);
  assert.ok(report.reasons.includes('decision_not_recorded'));
  assert.ok(!report.reasons.includes('malformed_record'));
});

// ---- critic round 2 ----

test('the replay reads like the verifier: a blank line or a CR breaks the chain, and a last line without LF is still read', async () => {
  const { file } = await session(2);
  const lines = fs.readFileSync(file, 'utf8').split('\n').filter(Boolean);
  const d = path.dirname(file);
  const write = (name: string, text: string) => { const f = path.join(d, name); fs.writeFileSync(f, text); return f; };
  assert.ok(replayPassed(await replayDecisionFile(write('lf.journal', lines.join('\n') + '\n'))));
  assert.ok(replayPassed(await replayDecisionFile(write('nolf.journal', lines.join('\n')))), 'no final LF');
  const blank = await replayDecisionFile(write('blank.journal', [...lines.slice(0, 3), '', ...lines.slice(3)].join('\n') + '\n'));
  assert.equal(blank.chain, 'broken');
  assert.equal(verify(path.join(d, 'blank.journal')).report.locally_consistent, false, 'the verifier rejects it too');
  const crlf = await replayDecisionFile(write('crlf.journal', lines.join('\r\n') + '\r\n'));
  assert.equal(crlf.chain, 'broken');
  assert.equal(verify(path.join(d, 'crlf.journal')).report.locally_consistent, false);
});

test('a decision made on a NaN number is replayed faithfully and flagged by both tools', async () => {
  const dir = tmp();
  const tap = new RawFrameTap({ file: path.join(dir, 'j.journal'), config: { tool: 'test' }, clock: stepClock() });
  tap.connecting(); tap.opened(); tap.sent('{"cmd":"subscribe"}');
  tap.frame(Buffer.from(JSON.stringify({ type: 'orderbook_snapshot', sid: 1, seq: 1, msg: { market_ticker: 'T1' } })), false);
  const lane = seasonedLane();
  lane.receiptSink = (i, r) => tap.decision(i, r);
  lane.decide(NOW, snap([row()]), [m15({ position: NaN })], OPTS);
  tap.closed(1000);
  await tap.close();
  const f = path.join(dir, 'j.journal');
  const r = await replayDecisionFile(f);
  assert.deepEqual([r.matched, r.nonFiniteInputs], [1, 1]);
  const { report } = verify(f);
  assert.equal(report.notes.decisions_on_non_finite_number, 1);
  assert.ok(report.reasons.includes('decision_on_non_finite_number'));
  assert.equal(report.locally_consistent, true, 'a flag, not a broken journal');
});

test('receipts have their own byte budget: past it they are reasons with hashes, so they cannot spend the cap that frames need', async () => {
  const dir = tmp();
  const tap = new RawFrameTap({ file: path.join(dir, 'j.journal'), config: { tool: 'test' }, clock: stepClock(), maxDecisionBytes: 600 });
  tap.connecting(); tap.opened(); tap.sent('{"cmd":"subscribe"}');
  tap.frame(Buffer.from(JSON.stringify({ type: 'orderbook_snapshot', sid: 1, seq: 1, msg: { market_ticker: 'T1' } })), false);
  tap.decision({ now: 1 }, { decided: [] });
  tap.decision({ now: 2, pad: 'z'.repeat(2000) }, { decided: [] });
  tap.decision({ now: 3 }, { decided: [] });
  tap.closed(1000);
  await tap.close();
  const f = path.join(dir, 'j.journal');
  const { report } = verify(f);
  assert.equal(report.notes.decisions, 3);
  assert.equal(report.notes.decisions_unrecorded, 1);
  assert.ok(report.reasons.includes('decision_not_recorded'));
  assert.equal(report.locally_consistent, true);
  const r = await replayDecisionFile(f);
  assert.deepEqual([r.decisions, r.replayed, r.unrecorded], [3, 2, 1]);
});

test('the replay command names the checkout it ran from and the files it depends on, whatever directory it is called from', async () => {
  const { file } = await session(1);
  const r = spawnSync('node', ['--import', 'tsx', 'research/ralph_capture/replayCli.ts', file], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const out = JSON.parse(r.stdout);
  assert.equal(out.passed, true);
  assert.equal(out.chain_checked_here, true);
  assert.equal(out.verifier_checks_included, false);
  assert.equal(path.resolve(out.replayed_with.checkout), path.resolve('.'));
  assert.deepEqual(Object.keys(out.replayed_with.decide_files_sha256).sort(), ['bot/heat/heatBook.ts', 'bot/heat/heatLane.ts', 'bot/plan/planRatchet.ts', 'bot/util/num.ts']);
  assert.ok(Object.values(out.replayed_with.decide_files_sha256).every((h) => typeof h === 'string' && (h as string).length === 64));
});
