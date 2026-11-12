// Heat sources: where the lane gets the curve reader's calls from (the contract is in types.ts).
//
// The reader runs outside the bot and rewrites one small JSON file a minute. Everything in that file is checked here
// before the lane sees it, because the lane sizes and sends orders from these numbers: a share written as a percent,
// a time written in seconds or a side that is neither up nor down must stop the coin, not trade it. A file that
// cannot be trusted as a whole (missing, unreadable, not JSON, another version) is dropped whole and the reason goes
// to status. One coin with a bad row loses only that coin: it stays in the snapshot marked not ok, with no calls and
// the reason, so the lane can say why it did nothing. Nothing in here throws: a source problem is a reason for no
// entries, never a reason for the engine's tick to fail.
//
// How old the calls are is not judged here. A source reports the file's age and the lane decides what is stale
// (HEAT_MAX_AGE_SEC), so that rule lives in one place.

import fs from 'fs';
import zlib from 'zlib';
import type { HeatCallRow, HeatCallsFile, HeatCoinCalls, HeatSnapshot, HeatSource, HeatSourceStatus } from './types';

/** What parseHeatCalls hands back: the checked snapshot, or why the text cannot be used. Never both. */
export type HeatParse = { snapshot: HeatSnapshot; error?: undefined } | { snapshot?: undefined; error: string };

type Obj = Record<string, unknown>;
const isObj = (x: unknown): x is Obj => typeof x === 'object' && x !== null && !Array.isArray(x);
const fin = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
/** A time in epoch milliseconds (1973 to 5138). Today's time in seconds is far below this range and in microseconds
 *  far above it, so a writer using the wrong unit is refused instead of read as a date in 1970 or the far future. */
const isMs = (x: unknown): x is number => fin(x) && x >= 1e11 && x < 1e14;
/** An optional field counts as left out when it is missing or null (a Python writer emits None as null). */
const absent = (x: unknown): boolean => x === undefined || x === null;
/** A short, safe rendering of a value from the file for a reason text. */
const show = (x: unknown): string => { try { return String(JSON.stringify(x)).slice(0, 40); } catch { return typeof x; } };
const errText = (e: unknown): string => {
  const code = (e as { code?: unknown } | null)?.code;
  return typeof code === 'string' ? code : String((e as { message?: unknown } | null)?.message ?? e).slice(0, 160);
};

/** DOGE is not traded anywhere in this project, so its calls are dropped on the way in, under any spelling of the
 *  name (DOGE, doge, DOGEUSDT, DOGE-USD). */
const isDoge = (coin: string): boolean => coin.trim().toUpperCase().startsWith('DOGE');

/** One row, checked field by field. Returns a clean copy (only the contract's fields), or the reason it is refused. */
function checkRow(raw: unknown): HeatCallRow | string {
  if (!isObj(raw)) return 'not an object';
  const { key, kind, tf, h, dir, rank, of, heat, share, odds, barClose, aliases, trig } = raw;
  if (typeof key !== 'string' || !key) return 'key must be a non-empty string';
  if (kind !== 'single' && kind !== 'pair' && kind !== 'triple') return 'kind must be single, pair or triple';
  if (!fin(tf) || tf <= 0) return 'tf must be a positive number of minutes';
  if (!fin(h) || h <= 0) return 'h must be a positive number of minutes';
  if (dir !== 1 && dir !== -1) return 'dir must be 1 or -1';
  // Not required to be whole: a row listed only for its share right may rank past `of`, and tied ranks can be halves.
  if (!fin(rank) || rank < 1) return 'rank must be 1 or more';
  if (!fin(of) || of < 1) return 'of must be 1 or more';
  if (!fin(heat)) return 'heat must be a finite number';
  // The pack stores the share as a percent; the reader divides by 100. A percent that slips through lands here.
  if (!fin(share) || share < 0 || share > 1) return 'share must be within 0..1 (a fraction, not a percent)';
  if (!fin(odds)) return 'odds must be a finite number';
  if (!isMs(barClose)) return 'barClose must be a time in ms';
  const row: HeatCallRow = { key, kind, tf, h, dir, rank, of, heat, share, odds, barClose };
  if (!absent(aliases)) {
    if (!Array.isArray(aliases) || !aliases.every((a) => typeof a === 'string')) return 'aliases must be an array of strings';
    row.aliases = aliases.slice() as string[];
  }
  // An empty trig is treated as none: the lane matches a pair to the single it refines by comparing trig values, and
  // two rows that both carry '' must not look like relatives.
  if (!absent(trig) && trig !== '') {
    if (typeof trig !== 'string') return 'trig must be a string';
    row.trig = trig;
  }
  for (const k of ['hold', 'dip', 'move'] as const) {
    const v = raw[k];
    if (absent(v)) continue;
    if (!fin(v)) return `${k} must be a finite number`;
    row[k] = v;
  }
  return row;
}

/** One coin. A coin that fails any check is not removed: it comes back not ok, with no calls and the reason, so it
 *  can never trade and the lane and the status can both say why. A bad row takes the whole coin with it because the
 *  bad row may be the pair that should have replaced a single, and trading the single then is a different bet. */
function checkCoin(raw: unknown): HeatCoinCalls {
  if (!isObj(raw)) return { asOf: 0, tableSha: '', ok: false, why: 'malformed: coin is not an object', calls: [] };
  const { asOf, tableSha, ok, why, calls } = raw;
  // The reader's own reason is kept in front, so a coin it already gave up on (a failed fetch) still says that.
  const said = ok === false && typeof why === 'string' && why ? `${why}; ` : '';
  const drop = (reason: string): HeatCoinCalls => ({
    asOf: isMs(asOf) ? asOf : 0, tableSha: typeof tableSha === 'string' ? tableSha : '', ok: false, why: `${said}malformed: ${reason}`, calls: [],
  });
  if (!isMs(asOf)) return drop('asOf must be a time in ms');
  if (typeof tableSha !== 'string') return drop('tableSha must be a string');
  if (typeof ok !== 'boolean') return drop('ok must be true or false');
  if (!absent(why) && typeof why !== 'string') return drop('why must be a string');
  if (!Array.isArray(calls)) return drop('calls must be an array');
  const rows: HeatCallRow[] = [];
  for (let i = 0; i < calls.length; i++) {
    const r = checkRow(calls[i]);
    if (typeof r === 'string') {
      const key = isObj(calls[i]) ? (calls[i] as Obj).key : undefined;
      return drop(`call ${i + 1}${typeof key === 'string' && key ? ` (${key.slice(0, 60)})` : ''}: ${r}`);
    }
    rows.push(r);
  }
  const coin: HeatCoinCalls = { asOf, tableSha, ok, calls: rows };
  if (typeof why === 'string') coin.why = why;
  return coin;
}

/** The whole file. A problem at this level means nothing in it can be trusted, so nothing is kept. */
function checkFile(raw: unknown): HeatParse {
  if (!isObj(raw)) return { error: 'calls file is not a JSON object' };
  const { v, source, run, packSha, writtenAt, coins } = raw;
  if (v !== 1) return { error: `unsupported version: v is ${show(v)}, this bot reads v 1` };
  if (typeof source !== 'string' || !source) return { error: 'source must be a non-empty string' };
  // The run goes into every rule id and order record, so it has to be there.
  if (typeof run !== 'string' || !run) return { error: 'run must be a non-empty string' };
  if (typeof packSha !== 'string') return { error: 'packSha must be a string' };
  if (!isMs(writtenAt)) return { error: 'writtenAt must be a time in ms' };
  if (!isObj(coins)) return { error: 'coins must be an object keyed by coin' };
  const map = new Map<string, HeatCoinCalls>();
  for (const [name, c] of Object.entries(coins)) if (!isDoge(name)) map.set(name, checkCoin(c));
  return { snapshot: { source, run, packSha, writtenAt, coins: map } };
}

/** The reader's file as text, parsed and checked. Never throws. */
export function parseHeatCalls(text: string): HeatParse {
  let raw: unknown;
  try {
    if (typeof text !== 'string' || !text.trim()) return { error: 'bad JSON: the file is empty' };
    raw = JSON.parse(text);
  } catch (e) {
    return { error: `bad JSON: ${errText(e)}` };
  }
  try { return checkFile(raw); } catch (e) { return { error: `calls file could not be checked: ${errText(e)}` }; }
}

/** A file built in code (tests, a recorder) as the snapshot the lane reads. No checks are run here: text from disk
 *  goes through parseHeatCalls. DOGE is left out here too. */
export function toSnapshot(file: HeatCallsFile): HeatSnapshot {
  const coins = new Map<string, HeatCoinCalls>();
  for (const [name, c] of Object.entries(file.coins ?? {})) if (!isDoge(name)) coins.set(name, c);
  return { source: file.source, run: file.run, packSha: file.packSha, writtenAt: file.writtenAt, coins };
}

/** The status every source reports: is there a snapshot, how old is its file, and each coin's state. The age is
 *  only reported; whether it is too old is the lane's call. */
function statusOf(snap: HeatSnapshot | undefined, why: string | undefined, now: number): HeatSourceStatus {
  if (!snap) return { ok: false, why: why ?? 'no snapshot' };
  // fromEntries defines plain own fields, so an odd coin name from the file cannot reach the object's prototype.
  const coins = Object.fromEntries([...snap.coins].map(([name, c]) => [
    name, { ok: c.ok, asOf: c.asOf, calls: c.calls.length, ...(c.why !== undefined ? { why: c.why } : {}) },
  ]));
  return { ok: true, writtenAt: snap.writtenAt, ageMs: now - snap.writtenAt, coins };
}

/** The reader's file is a few kilobytes. Anything this large is the wrong file, and is not read into memory. */
const MAX_FILE_BYTES = 8 * 1024 * 1024;

/** The file-backed source the server runs on. The engine asks every second; the file changes once a minute. So the
 *  file is looked at (one stat) at most once a second, and read and parsed only when its modification time or size
 *  changed. The reader replaces the file atomically, so a read never sees half a file. */
export class FileHeatSource implements HeatSource {
  private readonly statEveryMs: number;
  /** When the file was last looked at, on the caller's clock. */
  private statAt: number | undefined;
  /** Modification time and size of the file the current result came from; undefined = look again and read. */
  private seen: { mtimeMs: number; size: number } | undefined;
  private snap: HeatSnapshot | undefined;
  private why: string | undefined = 'calls file not read yet';

  constructor(private readonly file: string, opts: { statEveryMs?: number } = {}) {
    this.statEveryMs = opts.statEveryMs ?? 1000;
  }

  read(now: number): HeatSnapshot | undefined {
    this.refresh(now);
    return this.snap;
  }

  status(now: number): HeatSourceStatus {
    this.refresh(now);
    return statusOf(this.snap, this.why, now);
  }

  /** A bad or missing file keeps nothing: the last good snapshot is not served in its place, because the lane would
   *  then trade calls the reader no longer stands behind. */
  private fail(why: string, keepSeen: boolean): void {
    this.snap = undefined;
    this.why = why;
    if (!keepSeen) this.seen = undefined;
  }

  private refresh(now: number): void {
    try {
      // A clock that stepped back must not freeze the source until it catches up.
      if (this.statAt !== undefined && now >= this.statAt && now - this.statAt < this.statEveryMs) return;
      this.statAt = now;
      let st: fs.Stats;
      try { st = fs.statSync(this.file); } catch (e) {
        const code = errText(e);
        return this.fail(code === 'ENOENT' ? `calls file missing: ${this.file}` : `calls file cannot be looked at (${code})`, false);
      }
      if (this.seen && this.seen.mtimeMs === st.mtimeMs && this.seen.size === st.size) return;
      if (!st.isFile()) return this.fail('calls file is not a regular file', false);
      // From here the result belongs to this modification time and size: a bad file is not parsed again every
      // second, only once the reader writes a new one.
      this.seen = { mtimeMs: st.mtimeMs, size: st.size };
      if (st.size > MAX_FILE_BYTES) return this.fail(`calls file is too large (${st.size} bytes)`, true);
      let text: string;
      // A failed read may be passing (the file was swapped between the look and the read), so it is tried again.
      try { text = fs.readFileSync(this.file, 'utf8'); } catch (e) { return this.fail(`calls file cannot be read (${errText(e)})`, false); }
      const r = parseHeatCalls(text);
      if (r.snapshot) { this.snap = r.snapshot; this.why = undefined; } else this.fail(r.error, true);
    } catch (e) {
      this.fail(`calls file check failed: ${errText(e)}`, false);
    }
  }
}

const isSnapshot = (x: HeatSnapshot | HeatCallsFile): x is HeatSnapshot => x.coins instanceof Map;

/** The source tests use: it serves whatever was set last. */
export class MemoryHeatSource implements HeatSource {
  private snap: HeatSnapshot | undefined;
  private why: string | undefined;

  constructor(snapshot?: HeatSnapshot | HeatCallsFile) { this.set(snapshot); }

  /** Replace what is served: a snapshot, a file object (turned into one with toSnapshot), or undefined for nothing,
   *  with `why` as the reason status then gives. */
  set(snapshot: HeatSnapshot | HeatCallsFile | undefined, why?: string): void {
    this.snap = snapshot === undefined ? undefined : isSnapshot(snapshot) ? snapshot : toSnapshot(snapshot);
    this.why = this.snap ? undefined : why ?? 'no snapshot set';
  }

  read(): HeatSnapshot | undefined { return this.snap; }

  status(now: number): HeatSourceStatus { return statusOf(this.snap, this.why, now); }
}

/** A recorded stream of the reader's files, for replays and backtests: a JSONL where each line is one HeatCallsFile
 *  as the reader wrote it, in time order, plain or gzipped. At replay time `now` it serves the newest line written
 *  at or before `now`, which is what the file source would have held then (the live source sees a new file up to a
 *  second or two later). Lines that fail the checks are skipped and counted; the line before stays served and ages,
 *  so the lane's own staleness rule stops entries, as it would on the server. */
export class ReplayHeatSource implements HeatSource {
  private snaps: HeatSnapshot[] = [];
  private bad = 0;
  private readonly errors: string[] = [];

  /** One file, or several (one per day, say). A file that cannot be read is reported in info() and status, never thrown. */
  constructor(files: string | string[] = []) {
    for (const f of Array.isArray(files) ? files : [files]) {
      try {
        const buf = fs.readFileSync(f);
        // Told apart by the gzip signature, not the name. The flush setting reads a file whose last gzip member was
        // cut short (a recording still being written) up to where it stops instead of failing the whole file.
        const gz = buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b;
        this.add(gz ? zlib.gunzipSync(buf, { finishFlush: zlib.constants.Z_SYNC_FLUSH }) : buf);
      } catch (e) {
        this.errors.push(`replay file cannot be read (${errText(e)}): ${f}`);
      }
    }
    this.sort();
  }

  /** The same from text already in memory. */
  static fromText(text: string): ReplayHeatSource {
    const s = new ReplayHeatSource();
    try { s.add(Buffer.from(String(text), 'utf8')); } catch (e) { s.errors.push(`replay text cannot be read (${errText(e)})`); }
    s.sort();
    return s;
  }

  /** Line by line off the buffer, so a long recording never has to fit in one string. */
  private add(buf: Buffer): void {
    for (let start = 0; start < buf.length;) {
      let end = buf.indexOf(0x0a, start);
      if (end < 0) end = buf.length;
      const line = buf.toString('utf8', start, end).trim();
      start = end + 1;
      if (!line) continue;
      const r = parseHeatCalls(line);
      if (r.snapshot) this.snaps.push(r.snapshot); else this.bad++;
    }
  }

  /** The lines are written in time order. If a file is not (days given out of order), put them in order once, so the
   *  lookup below stays right. Lines written at the same time keep their order: the later one is served. */
  private sort(): void {
    for (let i = 1; i < this.snaps.length; i++) {
      if (this.snaps[i].writtenAt < this.snaps[i - 1].writtenAt) { this.snaps.sort((a, b) => a.writtenAt - b.writtenAt); return; }
    }
  }

  /** The newest line written at or before `now`. */
  read(now: number): HeatSnapshot | undefined {
    let lo = 0, hi = this.snaps.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.snaps[mid].writtenAt <= now) lo = mid + 1; else hi = mid;
    }
    return lo > 0 ? this.snaps[lo - 1] : undefined;
  }

  status(now: number): HeatSourceStatus {
    const snap = this.read(now);
    if (snap) return statusOf(snap, undefined, now);
    const why = this.errors[0] ?? (this.snaps.length ? 'no recorded calls at or before this time'
      : this.bad ? `no usable line in the replay (${this.bad} bad)` : 'the replay is empty');
    return statusOf(undefined, why, now);
  }

  /** What was loaded: usable lines, skipped lines, the first and last write times, and files that could not be read. */
  info(): { lines: number; badLines: number; from?: number; to?: number; errors: string[] } {
    const n = this.snaps.length;
    return { lines: n, badLines: this.bad, ...(n ? { from: this.snaps[0].writtenAt, to: this.snaps[n - 1].writtenAt } : {}), errors: [...this.errors] };
  }
}
