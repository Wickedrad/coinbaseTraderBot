/** Replays the heat decisions stored in a raw-tap journal through the bot's own decideHeat. RESEARCH ONLY.
 *
 *  A journal written with the receipt seam on holds, for each HeatLane.decide pass, the input decideHeat was given (minus fields it
 *  does not read, see heatReceiptInput) and the result it returned, as kind 'decision' records in the same hash chain as the frames.
 *  decideHeat is pure, so feeding the stored input back must give the stored result. This module walks the whole file, checks the
 *  hash chain and the numbering itself, replays every receipt and compares it with the stored result.
 *
 *  What a pass shows: the chain is unbroken and every stored result is what the decideHeat in this checkout computes from the stored
 *  input, and the number of receipts is the number the footer declares.
 *  What it does NOT show: that the receipts are authentic (a writer who re-chains the whole file can store any consistent pair; only
 *  an anchor kept elsewhere narrows that, and this module does not read one); that the code that ran on the server is this code (the
 *  journal records the release folder name, nothing stronger; compare it with the commit replayed here); that decideHeat depends on
 *  nothing outside its input (one pass cannot show that); or that the stored markets (best bid and ask, position) agree with the
 *  order-book frames before the receipt. That last step, binding the books, is not done.
 *
 *  Reads only. It calls decideHeat (pure) and nothing else of the bot. */
import fs from 'node:fs';
import { decideHeat, type HeatDecideInput } from '../../bot/heat/heatLane';
import { decodeDecisionJson, encodeDecisionJson, sha256 } from './rawTap';

const GENESIS = '0'.repeat(64);

export interface ReplayMismatch { n: number; seq: number; path: string; stored?: string; replayed?: string; threw?: string }
export interface ReplayReport {
  /** non-empty lines read */
  lines: number;
  /** the hash chain and the record numbers over every line read (this tool's own check, not an anchor) */
  chain: 'intact' | 'broken';
  chainBrokenAt?: number;
  /** a record after the footer, or no footer at all */
  footer: 'present' | 'missing' | 'not_last';
  /** the footer's declared receipt count (0 when an older journal has none) */
  footerDecisions: number;
  /** decision records seen */
  decisions: number;
  /** receipts whose number is not their position among the receipts */
  badNumbering: number;
  /** receipts whose text was stored in full and could be replayed */
  replayed: number;
  matched: number;
  /** replayed but the result differs (or decideHeat threw) */
  mismatched: number;
  /** stored without text (disk behind, too large, private field, not serializable): cannot be replayed */
  unrecorded: number;
  /** stored text whose SHA-256 is not the one recorded next to it */
  hashMismatch: number;
  /** receipts whose input held a NaN, Infinity or -0 (written as {"$num"}): decisions made on a corrupt number */
  nonFiniteInputs: number;
  /** the release folder the capturing process ran from, as the journal's header recorded it */
  journalRelease: string | null;
  first: ReplayMismatch[];
}

const MAX_LISTED = 10;
const short = (v: unknown) => { const t = JSON.stringify(v); return t === undefined ? 'undefined' : t.length > 160 ? t.slice(0, 160) + '...' : t; };
const has = (o: object, k: string) => Object.prototype.hasOwnProperty.call(o, k);

/** The first place two parsed JSON values differ, as a path like `plans[0].count`; undefined when they are the same. A key present
 *  on one side only is a difference, whatever its value. */
export function firstDifference(a: unknown, b: unknown, at = '$'): { path: string; a: unknown; b: unknown } | undefined {
  if (a === b) return undefined;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return { path: at, a, b };
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.max(a.length, b.length); i++) { const d = firstDifference(a[i], b[i], `${at}[${i}]`); if (d) return d; }
    return undefined;
  }
  const oa = a as Record<string, unknown>, ob = b as Record<string, unknown>;
  for (const k of [...new Set([...Object.keys(oa), ...Object.keys(ob)])].sort()) {
    if (has(oa, k) !== has(ob, k)) return { path: `${at}.${k}`, a: has(oa, k) ? oa[k] : '(absent)', b: has(ob, k) ? ob[k] : '(absent)' };
    const d = firstDifference(oa[k], ob[k], `${at}.${k}`);
    if (d) return d;
  }
  return undefined;
}

const list = (r: ReplayReport, m: ReplayMismatch) => { if (r.first.length < MAX_LISTED) r.first.push(m); };

/** Replays one decision record (already parsed from the journal line). */
function replayOne(rec: Record<string, unknown>, r: ReplayReport): void {
  const n = Number(rec.n), seq = Number(rec.seq);
  if (seq !== r.decisions) { r.badNumbering++; list(r, { n, seq, path: `receipt number ${seq} where ${r.decisions} was expected` }); }
  r.decisions++;
  const inText = rec.input_json, outText = rec.result_json;
  if (typeof inText !== 'string' || typeof outText !== 'string') { r.unrecorded++; return; }
  if (sha256(inText) !== rec.input_sha256 || sha256(outText) !== rec.result_sha256) { r.hashMismatch++; list(r, { n, seq, path: 'sha256 of the stored text differs from the recorded hash' }); return; }
  r.replayed++;
  if (inText.includes('"$num"')) r.nonFiniteInputs++;
  let replayedJson: string;
  try {
    // Compared as parsed JSON of the encoded forms, so key order cannot matter, and NaN, Infinity and -0 (encoded as {"$num"}) are
    // not equal to null or 0.
    replayedJson = encodeDecisionJson(decideHeat(decodeDecisionJson(inText) as HeatDecideInput));
  } catch (e) {
    r.mismatched++;
    list(r, { n, seq, path: '$', threw: String(e).slice(0, 160) });
    return;
  }
  const d = firstDifference(JSON.parse(outText), JSON.parse(replayedJson));
  if (!d) { r.matched++; return; }
  r.mismatched++;
  list(r, { n, seq, path: d.path, stored: short(d.a), replayed: short(d.b) });
}

/** Feeds the journal one line at a time. Every line is parsed and chain-checked: nothing is skipped by looking for a keyword. */
export class DecisionReplayer {
  private prev = GENESIS;
  private idx = 0;
  private done = false;
  readonly report: ReplayReport = {
    lines: 0, chain: 'intact', footer: 'missing', footerDecisions: 0, decisions: 0, badNumbering: 0, replayed: 0, matched: 0, mismatched: 0,
    unrecorded: 0, hashMismatch: 0, nonFiniteInputs: 0, journalRelease: null, first: [],
  };

  private broken(): void { if (this.report.chain === 'intact') { this.report.chain = 'broken'; this.report.chainBrokenAt = this.idx; } }

  feed(line: string): void {
    const r = this.report;
    if (r.chain === 'broken') return;
    r.lines++;
    if (line === '') { this.broken(); return; }   // the verifier rejects a blank line; so does this
    const tab = line.indexOf('\t');
    const hash = tab < 0 ? '' : line.slice(0, tab), body = tab < 0 ? '' : line.slice(tab + 1);
    if (sha256(this.prev + '\n' + body) !== hash) { this.broken(); return; }
    let rec: Record<string, unknown>;
    try { const p = JSON.parse(body); if (!p || typeof p !== 'object' || Array.isArray(p)) throw new Error('not an object'); rec = p; } catch { this.broken(); return; }
    if (rec.n !== this.idx) { this.broken(); return; }
    this.prev = hash;
    if (this.done) { r.footer = 'not_last'; this.idx++; return; }
    if (this.idx === 0 && typeof rec.config_json === 'string') {
      try { const c = JSON.parse(rec.config_json); if (c && typeof c.release === 'string') r.journalRelease = c.release; } catch { /* the verifier reports an unreadable config */ }
    }
    if (rec.kind === 'decision') replayOne(rec, r);
    else if (rec.kind === 'end') { this.done = true; r.footer = 'present'; r.footerDecisions = typeof rec.decisions === 'number' ? rec.decisions : 0; }
    this.idx++;
  }
}

export function replayDecisionLines(lines: Iterable<string>): ReplayReport {
  const p = new DecisionReplayer();
  for (const line of lines) p.feed(line);
  return p.report;
}

/** Streams the file in constant memory. Lines end at LF only (a CR stays in the line and fails the hash, as it does in the verifier),
 *  and a file that ends without a final LF still yields its last line. */
export async function replayDecisionFile(file: string): Promise<ReplayReport> {
  const p = new DecisionReplayer();
  let rest = '';
  for await (const chunk of fs.createReadStream(file, { encoding: 'utf8' })) {
    rest += chunk as string;
    let at: number;
    while ((at = rest.indexOf('\n')) >= 0) { p.feed(rest.slice(0, at)); rest = rest.slice(at + 1); }
  }
  if (rest !== '') p.feed(rest);
  return p.report;
}

/** True when the chain is intact, the footer closes the file and counts the receipts, there was something to replay and every
 *  receipt reproduced. Read the limits at the top of this file before relying on it. */
export const replayPassed = (r: ReplayReport): boolean => r.chain === 'intact' && r.footer === 'present' && r.footerDecisions === r.decisions
  && r.decisions > 0 && r.badNumbering === 0 && r.mismatched === 0 && r.unrecorded === 0 && r.hashMismatch === 0 && r.matched === r.decisions;
