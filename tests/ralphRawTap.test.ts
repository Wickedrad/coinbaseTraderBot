// Ralph raw-frame tap: opt-in, off by default, research only. Local loopback server only: no network, no credentials.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { WebSocketServer } from 'ws';
import { KalshiWs, type RawFrameSink } from '../bot/kalshi/ws';
import type { KalshiSigner } from '../bot/kalshi/auth';
import { RawFrameTap, assertNoSecrets, sha256, type TapClock } from '../research/ralph_capture/rawTap';

const VERIFY = path.resolve('research/ralph_capture/verify_journal.py');
const SECRET_KEY_ID = 'SENTINEL-KEY-ID-9f3a';
const SECRET_TRADE = 'SENTINEL-PRIVATE-FILL-77c1';
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'ralph-tap-'));
const fakeSigner = { headers: () => ({ 'KALSHI-ACCESS-KEY': SECRET_KEY_ID, 'KALSHI-ACCESS-SIGNATURE': 'SENTINEL-SIGNATURE' }) } as unknown as KalshiSigner;

function stepClock(): TapClock {
  let w = 1_800_000_000_000, m = 5_000_000_000n;
  return { wallMs: () => (w += 7), monoNs: () => (m += 7_000_000n) };
}

function verify(file: string, anchor?: string): any {
  const args = ['-I', VERIFY, file, ...(anchor ? ['--anchor', anchor] : [])];
  const r = spawnSync('python3', args, { encoding: 'utf8' });
  return { code: r.status, report: JSON.parse(r.stdout) };
}

const EVENTS = ['book_snapshot', 'book_delta', 'book_gap', 'trade', 'fill', 'user_order', 'index', 'lifecycle', 'connected', 'reconnected', 'disconnected'] as const;
const NORMALIZED = new Set(['book_snapshot', 'book_delta', 'book_gap', 'trade', 'index', 'lifecycle']);
const strip = (v: unknown) => JSON.parse(JSON.stringify(v, (k, x) => (k === 'ts' ? undefined : x)));

interface Run { events: { name: string; e: unknown }[]; commands: string[]; headers: string[] }

/** One client against a scripted loopback exchange: two connections, a sequence gap, a garbage frame and a private fill. */
async function scenario(attach?: (ws: KalshiWs) => void): Promise<Run> {
  const run: Run = { events: [], commands: [], headers: [] };
  const wss = new WebSocketServer({ host: '127.0.0.1', port: 0 });
  await new Promise<void>((r) => wss.once('listening', () => r()));
  const port = (wss.address() as { port: number }).port;
  let conns = 0;
  let finished: () => void = () => undefined;
  const done = new Promise<void>((r) => { finished = r; });
  wss.on('connection', (sock, req) => {
    const me = conns++;
    run.headers.push(String(req.headers['kalshi-access-key']));
    let first = true;
    sock.on('message', (m) => {
      run.commands.push(m.toString());
      if (!first) return;
      first = false;
      if (me === 0) {
        sock.send('{"id":1,"type":"subscribed","msg":{"channel":"orderbook_delta","sid":7}}');
        sock.send('{"type":"orderbook_snapshot","sid":7,"seq":1,"msg":{"market_ticker":"KXT-A","yes_dollars_fp":[["0.4500","10.00"]],"no_dollars_fp":[["0.5000","5.00"]]}}');
        sock.send('{"type":"orderbook_delta","sid":7,"seq":2,"msg":{"market_ticker":"KXT-A","price_dollars":"0.4500","delta_fp":"2.00","side":"yes"}}');
        sock.send('{"type":"orderbook_delta","sid":7,"seq":4,"msg":{"market_ticker":"KXT-A","price_dollars":"0.4500","delta_fp":"1.00","side":"yes"}}');
        sock.send('this is not json');
        sock.send(`{"type":"fill","sid":9,"seq":1,"msg":{"trade_id":"${SECRET_TRADE}"}}`);
        sock.send('{"type":"trade","sid":8,"msg":{"market_ticker":"KXT-A","yes_price_dollars":"0.4600","count_fp":"3.00","taker_side":"yes","ts":1800000000}}');
        setTimeout(() => sock.close(1000), 30);
      } else {
        sock.send('{"type":"orderbook_snapshot","sid":3,"seq":1,"msg":{"market_ticker":"KXT-B","yes_dollars_fp":[["0.3000","4.00"]],"no_dollars_fp":[["0.6500","6.00"]]}}');
        sock.send('{"type":"orderbook_delta","sid":3,"seq":2,"msg":{"market_ticker":"KXT-B","price_dollars":"0.3000","delta_fp":"1.00","side":"yes"}}');
        setTimeout(finished, 80);
      }
    });
  });
  const ws = new KalshiWs(`ws://127.0.0.1:${port}/trade-api/ws/v2`, fakeSigner, []);
  for (const name of EVENTS) (ws as any).on(name, (e: unknown) => run.events.push({ name, e: strip(e ?? null) }));
  attach?.(ws);
  ws.setMarkets(['KXT-A']);
  ws.connect();
  await done;
  const gone = new Promise<void>((r) => ws.once('disconnected', () => r()));
  ws.close();
  await gone;
  await new Promise<void>((r) => wss.close(() => r()));
  return run;
}

test('without a sink the client behaves as before and the sink hooks are inert', async () => {
  const a = await scenario();
  assert.ok(a.events.some((x) => x.name === 'book_gap'), 'scenario produced a sequence gap');
  assert.ok(a.events.some((x) => x.name === 'reconnected'), 'scenario reconnected');
  assert.deepEqual(a.headers, [SECRET_KEY_ID, SECRET_KEY_ID], 'the signed headers did reach the server');
});

test('a tap changes nothing the bot sees, captures every frame raw, and the verifier accepts the result', async () => {
  const dir = tmp();
  const file = path.join(dir, 'j.journal'), anchor = path.join(dir, 'j.anchor');
  const base = await scenario();
  let tap!: RawFrameTap;
  const withTap = await scenario((ws) => {
    tap = new RawFrameTap({ file, anchorFile: anchor, anchorEvery: 3, clock: stepClock(), config: { ws_host: '127.0.0.1', mode: 'paper', tickers: ['KXT-A'] } });
    ws.setRawSink(tap);
  });
  await tap.close();
  // 1. behaviour identical (events, order, payloads except wall-clock stamps; commands the server saw)
  assert.deepEqual(withTap.events, base.events);
  assert.deepEqual(withTap.commands, base.commands);
  // 2. journal verifies, with continuity facts the bot itself does not keep
  const { code, report } = verify(file, anchor);
  assert.equal(code, 0, JSON.stringify(report.reasons));
  assert.equal(report.locally_consistent, true);
  assert.equal(report.exchange_authenticated, false);
  assert.equal(report.phase_b_eligible, false);
  assert.equal(report.anchor, 'matched');
  assert.equal(report.notes.epochs, 2);
  assert.equal(report.notes.frames, 9);          // 7 in the first connection, 2 in the second
  assert.equal(report.notes.redacted, 2);        // the garbage frame and the private fill
  assert.equal(report.notes.gaps_count, 1);
  assert.equal(report.continuity_intact, false, 'the gap is reported');
  assert.equal(report.notes.books['0:KXT-A'].valid_at_end, false);
  assert.equal(report.notes.books['1:KXT-B'].valid_at_end, false, 'a disconnect ends every window');
  assert.equal(report.notes.windows_ended_by_disconnect, 1, 'only the second book was still valid when its connection ended');
  assert.deepEqual({ sid: report.notes.gaps[0].sid, expected: report.notes.gaps[0].expected, got: report.notes.gaps[0].got }, { sid: 7, expected: 3, got: 4 });
  assert.ok(report.notes.outbound >= 2, 'commands sent are journaled');
  // 3. no credential or private payload in the file
  const text = fs.readFileSync(file, 'utf8');
  assert.ok(!text.includes(SECRET_KEY_ID) && !text.includes('SENTINEL-SIGNATURE'), 'headers never reach the journal');
  assert.ok(!text.includes(SECRET_TRADE), 'private fill content withheld');
  assert.ok(text.includes('this is not json') === false, 'unparsable frame content withheld, only its hash kept');
  // 4. the kept frames are the exact bytes: hashing the stored text reproduces the recorded SHA-256
  for (const line of text.trim().split('\n')) {
    const body = JSON.parse(line.slice(line.indexOf('\t') + 1));
    if (body.kind === 'frame' && !body.redacted) assert.equal(sha256(body.raw), body.sha256);
  }
});

test('replaying the journaled frames through the original parser yields the events the live run produced', async () => {
  const dir = tmp();
  const file = path.join(dir, 'j.journal');
  let tap!: RawFrameTap;
  const live = await scenario((ws) => { tap = new RawFrameTap({ file, clock: stepClock(), config: { mode: 'paper' } }); ws.setRawSink(tap); });
  await tap.close();
  const replayed: { name: string; e: unknown }[] = [];
  let ws: KalshiWs | undefined;
  let epoch = -1;
  for (const line of fs.readFileSync(file, 'utf8').trim().split('\n')) {
    const r = JSON.parse(line.slice(line.indexOf('\t') + 1));
    if (r.kind === 'transport' && r.event === 'connecting') {
      epoch = r.epoch;
      ws = new KalshiWs('ws://replay.invalid/trade-api/ws/v2', undefined, []);   // a fresh client per connection, as the live one resets its sequence state on open
      for (const name of NORMALIZED) (ws as any).on(name, (e: unknown) => replayed.push({ name, e: strip(e ?? null) }));
    } else if (r.kind === 'frame' && !r.redacted) {
      assert.equal(r.epoch, epoch);
      (ws as any).onMessage(r.raw);             // the bot's own onMessage, untouched
    }
  }
  assert.deepEqual(replayed, live.events.filter((x) => NORMALIZED.has(x.name)));
});

test('a sink that throws is detached and cannot change what the bot sees', async () => {
  const base = await scenario();
  let calls = 0;
  const angry: RawFrameSink = {
    connecting: () => { calls++; throw new Error('boom'); }, opened: () => { calls++; throw new Error('boom'); },
    closed: () => { calls++; throw new Error('boom'); }, errored: () => { calls++; throw new Error('boom'); },
    sent: () => { calls++; throw new Error('boom'); }, frame: () => { calls++; throw new Error('boom'); },
  };
  const run = await scenario((ws) => ws.setRawSink(angry));
  assert.equal(calls, 1, 'detached after its first failure');
  assert.deepEqual(run.events, base.events);
  assert.deepEqual(run.commands, base.commands);
});

test('a slow disk drops frames, writes a marker with the count, and the verifier rejects continuity', async () => {
  const dir = tmp();
  const file = path.join(dir, 'j.journal');
  const tap = new RawFrameTap({ file, clock: stepClock(), maxPendingBytes: 1, config: { mode: 'paper' } });
  tap.connecting(); tap.opened();
  await new Promise<void>((r) => setTimeout(r, 50));                                // header and transport lines reach the disk
  const f = (s: string) => tap.frame(Buffer.from(s), false);
  f('{"type":"orderbook_snapshot","sid":1,"seq":1,"msg":{"market_ticker":"T"}}');   // buffered write waits: pending > 1 byte
  f('{"type":"orderbook_delta","sid":1,"seq":2,"msg":{"market_ticker":"T"}}');      // dropped
  f('{"type":"orderbook_delta","sid":1,"seq":3,"msg":{"market_ticker":"T"}}');      // dropped
  assert.equal(tap.status().dropped, 2);
  await new Promise<void>((r) => setTimeout(r, 50));                                // disk catches up
  tap.frame(Buffer.from('{"type":"orderbook_delta","sid":1,"seq":4,"msg":{"market_ticker":"T"}}'), false);
  tap.closed(1000);
  await tap.close();
  const { report } = verify(file);
  assert.ok(report.reasons.includes('frames_dropped'));
  assert.equal(report.notes.dropped_frames, 2);
  assert.ok(report.notes.anomalies.some((i: any) => i.why === 'frames_dropped'));
  assert.equal(report.locally_consistent, true, 'the file is intact; the market data in it is what is incomplete');
});

test('the journal file is create-only: an existing file is never overwritten', async () => {
  const file = path.join(tmp(), 'j.journal');
  fs.writeFileSync(file, 'KEEP');
  const tap = new RawFrameTap({ file, config: { mode: 'paper' } });
  tap.connecting(); tap.opened(); tap.frame(Buffer.from('{"type":"trade"}'), false);
  await tap.close();
  assert.equal(fs.readFileSync(file, 'utf8'), 'KEEP');
  assert.match(String(tap.status().failed), /EEXIST/);
});

test('a configuration carrying a credential is refused before anything is written', () => {
  const file = path.join(tmp(), 'j.journal');
  for (const bad of [{ apiKey: 'x' }, { nested: { signature: 1 } }, { note: '-----BEGIN PRIVATE KEY-----abc' }, { url: 'wss://user:pw@host/x' }, { h: 'KALSHI-ACCESS-KEY: abc' }]) {
    assert.throws(() => new RawFrameTap({ file, config: bad as Record<string, unknown> }), /credential/);
  }
  assert.equal(fs.existsSync(file), false);
  assert.doesNotThrow(() => assertNoSecrets({ ws_host: 'api.elections.kalshi.com', tickers: ['A'], mode: 'paper' }));
});

test('the tap is not wired into the bot and imports nothing that can trade', () => {
  const read = (f: string) => fs.readFileSync(f, 'utf8');
  const imports = (src: string) => [...src.matchAll(/^\s*import\s[^'"]*['"]([^'"]+)['"]/gm)].map((m) => m[1]);
  assert.deepEqual(imports(read('research/ralph_capture/rawTap.ts')).sort(), ['../../bot/kalshi/ws', 'node:crypto', 'node:fs']);
  assert.deepEqual(imports(read('research/ralph_capture/captureCli.ts')).sort(), ['../../bot/kalshi/auth', '../../bot/kalshi/ws', './rawTap', 'node:fs', 'node:path']);
  assert.ok(!/placeChecked|createOrder|\/orders|fetch\(/.test(read('research/ralph_capture/captureCli.ts')), 'no REST or order call in the capture CLI');
  const offenders: string[] = [];
  const walk = (d: string) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else if (/\.(ts|tsx|js)$/.test(e.name) && /ralph_capture|setRawSink/.test(read(p)) && p !== path.join('bot', 'kalshi', 'ws.ts')) offenders.push(p); } };
  walk('bot');
  assert.deepEqual(offenders, [], 'nothing under bot/ other than ws.ts mentions the tap');
});

// ---- critic round 1 additions ----
type Hook = 'connecting' | 'opened' | 'closed' | 'errored' | 'sent' | 'frame';
const HOOKS: Hook[] = ['connecting', 'opened', 'closed', 'sent', 'frame'];

for (const bad of HOOKS) {
  test(`a sink that throws only in ${bad}() is detached at once and the bot sees the same events and commands`, async () => {
    const base = await scenario();
    const calls: Record<Hook, number> = { connecting: 0, opened: 0, closed: 0, errored: 0, sent: 0, frame: 0 };
    const mk = (h: Hook) => (..._a: unknown[]) => { calls[h]++; if (h === bad) throw new Error('boom'); };
    const sink = { connecting: mk('connecting'), opened: mk('opened'), closed: mk('closed'), errored: mk('errored'), sent: mk('sent'), frame: mk('frame') } as unknown as RawFrameSink;
    const run = await scenario((ws) => ws.setRawSink(sink));
    assert.equal(calls[bad], 1, `${bad} called once, then detached`);
    assert.deepEqual(run.events, base.events);
    assert.deepEqual(run.commands, base.commands);
  });
}

test('errored() is reached on a refused connection; a throw there is contained', async () => {
  const probe = new WebSocketServer({ host: '127.0.0.1', port: 0 });
  await new Promise<void>((r) => probe.once('listening', () => r()));
  const port = (probe.address() as { port: number }).port;
  await new Promise<void>((r) => probe.close(() => r()));                      // nothing listens there now
  let errored = 0;
  const sink = { connecting() {}, opened() {}, closed() {}, sent() {}, frame() {}, errored() { errored++; throw new Error('boom'); } } as RawFrameSink;
  const ws = new KalshiWs(`ws://127.0.0.1:${port}/trade-api/ws/v2`, undefined, []);
  ws.setRawSink(sink);
  await new Promise<void>((r) => { ws.on('disconnected', () => { ws.close(); r(); }); ws.connect(); });   // close inside the handler: no reconnect
  assert.equal(errored, 1);
});

test('own-order identifiers on a public book delta are removed from the stored text; the hash still describes the original bytes', async () => {
  const file = path.join(tmp(), 'j.journal');
  const tap = new RawFrameTap({ file, clock: stepClock(), config: { mode: 'paper' } });
  tap.connecting(); tap.opened(); tap.sent('{"id":1,"cmd":"subscribe","params":{}}');
  const snap = '{"type":"orderbook_snapshot","sid":1,"seq":1,"msg":{"market_ticker":"T","yes_dollars_fp":[["0.4500","10.00"]],"no_dollars_fp":[]}}';
  const own = '{"type":"orderbook_delta","sid":1,"seq":2,"msg":{"market_ticker":"T","price_dollars":"0.4500","delta_fp":"1.00","side":"yes","client_order_id":"SENTINEL-ORDER-1","subaccount":3}}';
  tap.frame(Buffer.from(snap), false); tap.frame(Buffer.from(own), false);
  tap.closed(1000);
  await tap.close();
  const text = fs.readFileSync(file, 'utf8');
  assert.ok(!text.includes('SENTINEL-ORDER-1'));
  const rec = text.trim().split('\n').map((l) => JSON.parse(l.slice(l.indexOf('\t') + 1))).find((r) => r.seq === undefined && r.scrubbed);
  assert.deepEqual(rec.scrubbed.sort(), ['client_order_id', 'subaccount']);
  assert.ok(!/client_order_id|subaccount|"order_id"/.test(rec.raw), 'the stored text names no own-order field');
  assert.equal(rec.sha256, sha256(own), 'hash and byte count describe the original frame');
  assert.equal(rec.bytes, Buffer.byteLength(own));
  const { report } = verify(file);
  assert.equal(report.locally_consistent, true, JSON.stringify(report.reasons));
  assert.equal(report.notes.scrubbed, 1);
  assert.equal(report.continuity_intact, true);
  // the scrubbed text drives the original parser to the same event as the original bytes
  const events = (raw: string) => { const w = new KalshiWs('ws://x.invalid/trade-api/ws/v2', undefined, []); const out: unknown[] = []; (w as any).on('book_delta', (e: unknown) => out.push(strip(e))); (w as any).onMessage(snap); (w as any).onMessage(raw); return out; };
  assert.deepEqual(events(rec.raw), events(own));
});

test('a binary frame the bot would parse is withheld but its type, sid and seq are still read, and the verifier refuses it', async () => {
  const file = path.join(tmp(), 'j.journal');
  const tap = new RawFrameTap({ file, clock: stepClock(), config: { mode: 'paper' } });
  tap.connecting(); tap.opened(); tap.sent('{"id":1,"cmd":"subscribe","params":{}}');
  tap.frame(Buffer.from('{"type":"orderbook_snapshot","sid":1,"seq":1,"msg":{"market_ticker":"T"}}'), true);
  tap.closed(1000);
  await tap.close();
  const { report } = verify(file);
  assert.ok(report.reasons.includes('redacted_public_frame'));
  assert.equal(report.locally_consistent, false);
});

test('after pressure lifts the drop marker comes before any later frame, and a late close() event cannot touch the finished file', async () => {
  const file = path.join(tmp(), 'j.journal');
  const tap = new RawFrameTap({ file, clock: stepClock(), maxPendingBytes: 1, config: { mode: 'paper' } });
  tap.connecting(); tap.opened();
  await new Promise<void>((r) => setTimeout(r, 50));
  tap.sent('{"id":1,"cmd":"subscribe","params":{}}');
  await new Promise<void>((r) => setTimeout(r, 50));
  const f = (seq: number) => tap.frame(Buffer.from(`{"type":"orderbook_delta","sid":1,"seq":${seq},"msg":{"market_ticker":"T"}}`), false);
  f(1); f(2); f(3);
  await new Promise<void>((r) => setTimeout(r, 50));
  f(4);
  tap.closed(1000);
  await tap.close();
  const before = tap.status();
  tap.closed(1006); tap.errored('late'); tap.frame(Buffer.from('{"type":"trade"}'), false);   // events after the footer
  assert.deepEqual(tap.status(), before);
  const kinds = fs.readFileSync(file, 'utf8').trim().split('\n').map((l) => JSON.parse(l.slice(l.indexOf('\t') + 1)));
  const iMarker = kinds.findIndex((r) => r.kind === 'dropped'), iLast = kinds.findIndex((r) => r.kind === 'frame' && r.sha256 === sha256('{"type":"orderbook_delta","sid":1,"seq":4,"msg":{"market_ticker":"T"}}'));
  assert.ok(iMarker > 0 && iMarker < iLast, 'marker precedes the first frame written after the drops');
  assert.equal(kinds[kinds.length - 1].kind, 'end');
  assert.equal(verify(file).report.notes.dropped_frames, 2);
  assert.equal(fs.statSync(file).mode & 0o777, 0o600, 'journal is private to the owner');
});
