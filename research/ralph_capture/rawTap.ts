/** Raw Kalshi WebSocket frame journal. RESEARCH ONLY (Ralph Phase A, iteration 0047).
 *
 *  What it is: an observer a KalshiWs can be given with setRawSink(). It writes one hash-chained line per transport
 *  event, per command the bot sent, and per frame as received (SHA-256 of the bytes it was handed, text kept when public), with the receipt time
 *  on two clocks, a connection epoch, and a frozen capture configuration in the first line. The frame's sid and seq stay
 *  inside the raw text; verify_journal.py re-derives them and checks continuity, so this file never has to be trusted.
 *
 *  What it is not: exchange authentication. The chain lets a reader CHECK that no line was edited without re-hashing the rest
 *  (a forger who re-hashes everything is caught only by an anchor kept elsewhere); it does not prove Kalshi sent the bytes. The anchor file exists so the chain head can be kept somewhere this process cannot reach; until
 *  an operator does that, the journal is only locally consistent. The verifier reports exchange_authenticated=false always.
 *
 *  Safety: it imports nothing from the engine, execution, ledger or config. It never sees headers or keys (the sink
 *  interface has none). Every public method catches its own errors and, on any failure, stops writing and says so in
 *  status(); the missing footer then fails verification. A slow disk drops frames (counted, and marked in the journal) and
 *  never blocks or throws into the receive path. Nothing starts it: bot/main.ts does not reference this module. */
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import type { RawFrameSink } from '../../bot/kalshi/ws';

export const TAP_SCHEMA = 1;
const GENESIS = '0'.repeat(64);
/** Frames of these types are kept as text. Any other type (fills, own orders, positions, anything unknown or unparsable)
 *  is journaled as length + SHA-256 only, so an account's private data never lands in a research file. */
export const PUBLIC_TYPES: ReadonlySet<string> = new Set([
  'orderbook_snapshot', 'orderbook_delta', 'trade', 'ticker', 'ticker_v2', 'market_lifecycle', 'market_lifecycle_v2',
  'event_lifecycle', 'subscribed', 'ok', 'unsubscribed', 'error',
  'cfbenchmarks_value', 'cfbenchmarks_value_5hz', 'cfbenchmarks_value_indexlist', 'cfbenchmarks_value_5hz_indexlist',
]);
/** Fields that name the account's own orders; removed from the stored text of otherwise public frames. */
const PRIVATE_MSG_FIELDS = ['client_order_id', 'order_id', 'subaccount', 'subaccount_number', 'user_id'];
/** After scrubbing, a stored text that still names one of these (nested deeper, in an array, anywhere) is withheld instead. */
const PRIVATE_NAME_RE = /"(client_order_id|order_id|subaccount|subaccount_number|user_id)"\s*:/;
const SECRET_KEY = /key|secret|token|signature|password|passphrase|authorization|credential|pem/i;
const SECRET_VALUE = /-----BEGIN [A-Z ]*PRIVATE KEY-----|KALSHI-ACCESS|:\/\/[^/\s:@]+:[^/\s@]+@/i;

export interface TapClock { wallMs(): number; monoNs(): bigint }
export const REAL_CLOCK: TapClock = { wallMs: () => Date.now(), monoNs: () => process.hrtime.bigint() };

export interface TapOptions {
  /** New journal file. Created exclusively: an existing file is never overwritten or appended to. */
  file: string;
  /** Second file receiving {count, head} checkpoints, meant to be copied off this machine while the capture runs. */
  anchorFile?: string;
  /** Called with each checkpoint too (for example to log it or ship it elsewhere). Errors are swallowed. */
  onAnchor?: (a: { count: number; head: string; wall_ms: number }) => void;
  /** Frozen capture configuration: plain JSON, no secrets (rejected if a key or value looks like one). */
  config: Record<string, unknown>;
  clock?: TapClock;
  /** A checkpoint every this many records (default 1000), and one at close. */
  anchorEvery?: number;
  /** Frames are dropped (and a marker written) while more than this many bytes wait in the write buffer. */
  maxPendingBytes?: number;
}

export interface TapStatus {
  records: number; frames: number; redacted: number; dropped: number; bytes: number; head: string;
  failed: string | null; closed: boolean; epoch: number;
}

export function sha256(data: string | Buffer): string { return createHash('sha256').update(data).digest('hex'); }

/** Reject a configuration that could carry a credential. Throws; the tap is then never created. */
export function assertNoSecrets(v: unknown, path = 'config'): void {
  if (typeof v === 'string') { if (SECRET_VALUE.test(v)) throw new Error(`${path} looks like a credential`); return; }
  if (Array.isArray(v)) { v.forEach((x, i) => assertNoSecrets(x, `${path}[${i}]`)); return; }
  if (v && typeof v === 'object') {
    for (const [k, x] of Object.entries(v)) {
      if (SECRET_KEY.test(k)) throw new Error(`${path}.${k} is a credential-like key`);
      assertNoSecrets(x, `${path}.${k}`);
    }
  }
}

export class RawFrameTap implements RawFrameSink {
  private readonly clock: TapClock;
  private readonly out: fs.WriteStream;
  private readonly anchorOut?: fs.WriteStream;
  private readonly anchorEvery: number;
  private readonly maxPending: number;
  private head = GENESIS;
  private n = 0;
  private bytes = 0;
  private epoch = -1;
  private frames = 0;
  private redacted = 0;
  private droppedTotal = 0;
  private droppedPending = 0;
  private failed: string | null = null;
  private ended = false;
  private finished: Promise<void> | undefined;

  constructor(private readonly opts: TapOptions) {
    assertNoSecrets(opts.config);
    this.clock = opts.clock ?? REAL_CLOCK;
    this.anchorEvery = Math.max(1, opts.anchorEvery ?? 1000);
    this.maxPending = Math.max(1, opts.maxPendingBytes ?? 32 * 1024 * 1024);
    const configJson = JSON.stringify(opts.config);
    this.out = fs.createWriteStream(opts.file, { flags: 'wx', mode: 0o600 });
    this.out.on('error', (e) => { this.failed = `write: ${String(e).slice(0, 160)}`; });
    if (opts.anchorFile) {
      this.anchorOut = fs.createWriteStream(opts.anchorFile, { flags: 'wx', mode: 0o600 });
      this.anchorOut.on('error', (e) => { this.failed = `anchor: ${String(e).slice(0, 160)}`; });
    }
    this.append({
      kind: 'header', schema: TAP_SCHEMA, tool: 'ralph-raw-tap@0047', source: 'kalshi-ws-unattested',
      exchange_authenticated: false, started_wall_ms: this.clock.wallMs(), started_mono_ns: this.clock.monoNs().toString(),
      config_json: configJson, config_sha256: sha256(configJson),
    });
  }

  status(): TapStatus {
    return { records: this.n, frames: this.frames, redacted: this.redacted, dropped: this.droppedTotal, bytes: this.bytes, head: this.head, failed: this.failed, closed: this.ended, epoch: this.epoch };
  }

  // ---- RawFrameSink ----
  connecting(): void { this.guard(() => { this.epoch++; this.transport('connecting'); }); }
  opened(): void { this.guard(() => this.transport('open')); }
  errored(message: string): void { this.guard(() => this.transport('error', { message: message.slice(0, 200) })); }

  closed(code: number): void { this.guard(() => this.transport('close', { code })); }

  sent(text: string): void {
    this.guard(() => {
      if (this.backpressure()) return;
      this.append({ kind: 'outbound', epoch: this.epoch, ...this.stamp(), text });
    });
  }

  frame(data: Buffer, isBinary: boolean): void {
    this.guard(() => {
      const stamp = this.stamp(); // first thing: the receipt time must not include our own work
      if (this.backpressure(stamp)) return;
      // What the bot parses is data.toString() (ws.ts), lossy or not; type, sid and seq are read from that same view so a
      // frame the bot would apply is never invisible here. The text is kept only when it is lossless UTF-8.
      const asText = data.toString('utf8');
      const lossless = !isBinary && Buffer.from(asText, 'utf8').equals(data);
      // One parse for the top-level type, sid and seq (real subscribed/ok/error frames put "id" before "type", so no pattern
      // on the text is safe). Duplicate keys are not seen here; verify_journal.py rejects them from the stored text.
      let env: Record<string, unknown> | null = null;
      try { const e = JSON.parse(asText) as unknown; if (e && typeof e === 'object' && !Array.isArray(e)) env = e as Record<string, unknown>; } catch { /* not JSON */ }
      const type = env && typeof env.type === 'string' && /^[a-z0-9_]{1,64}$/.test(env.type) ? env.type : null;
      const sid = env && Number.isSafeInteger(env.sid) ? (env.sid as number) : null;
      const seq = env && Number.isSafeInteger(env.seq) ? (env.seq as number) : null;
      const isPublic = type !== null && PUBLIC_TYPES.has(type);
      const base = { kind: 'frame', epoch: this.epoch, ...stamp, bytes: data.length, binary: isBinary, sha256: sha256(data), type };
      this.frames++;
      if (isPublic && lossless && env) {
        // Own-order identifiers can ride on a public book delta; they are dropped from the stored text (sha256 and bytes still
        // describe the original, stored_sha256 the stored text), so the delta stays replayable but names no order.
        const msg = env.msg;
        const found = msg && typeof msg === 'object' && !Array.isArray(msg) ? PRIVATE_MSG_FIELDS.filter((k) => k in (msg as object)) : [];
        const stored = found.length
          ? JSON.stringify({ ...env, msg: Object.fromEntries(Object.entries(msg as Record<string, unknown>).filter(([k]) => !found.includes(k))) })
          : asText;
        // also test the re-serialized object: a key written with \u escapes decodes to a plain name there
        if (!PRIVATE_NAME_RE.test(stored) && !PRIVATE_NAME_RE.test(JSON.stringify(JSON.parse(stored)))) {
          this.append(found.length ? { ...base, raw: stored, stored_sha256: sha256(stored), scrubbed: found } : { ...base, raw: stored });
          return;
        }
        // an identifier still present somewhere the scrub does not reach: withhold the whole frame
        this.redacted++;
        this.append({ ...base, redacted: true, redacted_reason: 'private_field_nested', sid, seq });
        return;
      }
      // Withheld content keeps its sid and seq so the continuity of that subscription stays checkable without its payload.
      this.redacted++;
      this.append({ ...base, redacted: true, redacted_reason: isPublic ? 'not_lossless_text' : 'non_public_type', sid, seq });
    });
  }

  /** Write the footer (with the reason the capture ended) and a final checkpoint, flush, and resolve. Safe to call twice. */
  close(reason = 'closed'): Promise<void> {
    if (this.finished) return this.finished;
    this.finished = new Promise<void>((resolve) => {
      try {
        if (!this.ended && !this.failed) {
          this.flushDropMarker(true);
          this.append({ kind: 'end', records: this.n, frames: this.frames, dropped_total: this.droppedTotal, failed: this.failed, reason });
          this.checkpoint();
        }
      } catch (e) { this.failed = `close: ${String(e).slice(0, 160)}`; }
      this.ended = true;
      let pending = this.anchorOut ? 2 : 1;
      const done = () => { if (--pending === 0) resolve(); };
      this.out.end(done);
      this.anchorOut?.end(done);
    });
    return this.finished;
  }

  // ---- internals ----
  private stamp() { return { wall_ms: this.clock.wallMs(), mono_ns: this.clock.monoNs().toString() }; }

  private transport(event: string, extra: Record<string, unknown> = {}): void {
    this.append({ kind: 'transport', event, epoch: this.epoch, ...this.stamp(), ...extra });
  }

  /** True when this record must be dropped (disk behind). The first record after the pressure lifts is a marker with the
   *  count, so the verifier sees exactly where frames are missing. */
  private backpressure(stamp?: { wall_ms: number; mono_ns: string }): boolean {
    if (this.ended || this.failed) return true;
    const pending = this.out.writableLength;
    if (pending > this.maxPending || (this.droppedPending > 0 && pending > this.maxPending / 2)) { this.droppedPending++; this.droppedTotal++; return true; }
    this.flushDropMarker(true, stamp);
    return false;
  }

  /** The marker takes the stamp of the record that triggers it (not a newer one), so the journal's clocks never step back. */
  private flushDropMarker(_force: boolean, stamp?: { wall_ms: number; mono_ns: string }): void {
    if (this.droppedPending === 0) return;
    this.append({ kind: 'dropped', epoch: this.epoch, ...(stamp ?? this.stamp()), count: this.droppedPending, cause: 'backpressure' });
    this.droppedPending = 0;
  }

  private append(rec: Record<string, unknown>): void {
    if (this.failed || (this.ended && rec.kind !== 'end')) return;
    const body = JSON.stringify({ n: this.n, ...rec });
    const hash = sha256(this.head + '\n' + body);
    const line = `${hash}\t${body}\n`;
    this.out.write(line);
    this.bytes += Buffer.byteLength(line);
    this.head = hash;
    this.n++;
    if (this.n % this.anchorEvery === 0) this.checkpoint();
  }

  private checkpoint(): void {
    const a = { count: this.n, head: this.head, wall_ms: this.clock.wallMs() };
    this.anchorOut?.write(JSON.stringify(a) + '\n');
    try { this.opts.onAnchor?.(a); } catch { /* a faulty shipper must not stop the capture */ }
  }

  private guard(fn: () => void): void {
    try { fn(); } catch (e) { this.failed = `internal: ${String(e).slice(0, 160)}`; }
  }
}
