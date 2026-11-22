// Can a deep-history day stand in for a real recorded Kalshi day? (Steven, Nov 1: "its methodology has to be identical
// or at least indistinguishable from the real Kalshi contracts ... judge against real days with its own adversarial
// evaluator".)
//
// research/replayFidelity.ts tests one piece: it cuts a recorded day down to minute quotes and fills them back in, but
// keeps the recording's own index, contract list and settlement. A deep-history day has none of those: its index is
// Binance 1-minute bars bridged to 15 s prints and scaled by a basis, its quotes are Kalshi's public minute candles,
// its results come from Kalshi's API. This builds the deep-history twin of each recorded day with exactly the pipeline
// the deep history uses (research/kalshiReplayData.ts: Binance + Kalshi public history, requote; then the tally's
// fill-in), and judges the twin against the real day three ways:
//
//   1. paired mechanics   the same contract both ways: the twin's minute quote against the real book's mid at that
//                         minute, the twin's index against the real index, result agreement, contracts missing.
//   2. discriminator      the adversary. Each contract's life becomes a row of what the bot sees (spread, top size,
//                         depth, quote changes, 15 s mid moves, how the mid follows the index, trades, calibration);
//                         a logistic classifier, trained leaving one day out, tries to tell twin rows from real rows.
//                         AUC 0.5 = indistinguishable. Each feature's own AUC names what gives the twin away.
//   3. outcome            the decision model's backtest on the real days (restricted to the twin's contracts, so both
//                         trade the same universe) against the twin, window by window, beside a placebo: the real days
//                         again at +250 ms latency, the noise floor a difference must clear to mean anything.
//
// Pre-registered pass (all must hold, on days the depth model never saw): discriminator AUC <= 0.60; the twin's mean
// per-window P&L difference has a 95% bootstrap interval that contains 0; its per-window error <= 1.5x the placebo's;
// windows traded within 10% of real.
//
// THE HARNESS (Nov 22; runbook: depth-simulator/ralph-twin/RUNBOOK.md). A real full-depth day is 1.4-2.3 GB gzipped
// (~15 GB raw), so re-parsing it on every iteration made each optimizer iteration take hours. Each real day is reduced
// ONCE (stage prep, one pass, a string prefilter before any JSON.parse) to the records of its 15-minute-series contracts
// (REPLAY_EXCLUDE, DOGE by default, left out as everywhere) plus the index, candle, dominance, result and other
// non-contract records the judge and the backtests read; spot_book lines (no replay reads them) are dropped. The result,
// md-DAY.jsonl.gz + meta.json (day, REAL15M_VERSION tag, counts, source size, seconds, sha256), lives on Drive under
// derived/twin-real15m/DAY, meta.json uploaded last as the commit mark. An iteration then builds only the twin side
// (requote days from Drive simulated/kalshi-replay-200d while its manifest version is REPLAY_VERSION, else regenerated;
// the depth fill-in with a model fitted on the FIT days only) and judges it against those small cached days.
//
// Split: FIT days (the depth model is fitted here, --series 15m, and nowhere else) and JUDGED days are disjoint, asserted
// in the workflow and in stage split (assertDisjoint, resolveSplit, assertModelFitDays). split=dev: iteration decisions
// are read on its judged days; split=confirm is read once at the end of a round and never tuned on: its verdict prints
// ONLY the pass/fail checks, the AUC, the STRESS AUC and day counts (no per-feature, per-regime or correlation tables, no
// per-day lines), plus 'CONFIRM LOOK #n'. The confirm days (CONFIRM_DAYS) are HELD OUT (a recorded-data hold-out; not a future-day test): only split=confirm may read them (a
// dev or custom split that names one as a fit, judged or warm-up day throws, assertHeldOut), blindness follows the days and
// not the split's name (isBlind), and a blind verdict without a confirm_look_note throws: every look is numbered and logged.
// A custom split judges at least 2 days (leave-one-day-out needs a day to hold out).
//
// Diagnostics (dev/custom verdicts; counts and numbers only): per feature the real and twin p10/p50/p90, overall and per
// regime (calm/normal/volatile = terciles of ixMoveBps over the real rows); the 10 largest gaps between the real and twin
// pairwise feature correlations; AUC per judged day (the same leave-one-day-out folds as the headline AUC); every
// feature's own AUC. '[twin] STRESS' is a REPORT-ONLY second adversary (research/gbdt.ts boosted trees, same rows, same
// folds): it never enters pass/fail. The judge itself (FEATURES, discriminate, auc, fitLogit, outcome, the pass bar) is
// unchanged by the harness. Sources judged by default: requote and depth; the lag arms (lag, lagdepth) stay in the code
// but are off (workflow input lag_arms), because their fit is invalid until the quote lag is refit on post-Nov-10 days.
//
//   npm run research:history-twin -- --stage prep --raw data/raw --day 2026-11-13 --out data/real15m/2026-11-13
//   ... --stage prep-status --out DIR --day DAY      (exit 0 current, 11 absent or stale)
//   ... --stage prep-report --dir DIR --days A,B,... [--failed FILE]   (one DONE / NOT DONE line per day from DIR/DAY/meta.json; FILE: DAY<TAB>failed step name lines)
//   ... --stage split --split dev|confirm|custom [--fit-days A,B --judge-days C,D --warm-days E] --out data/twin
//   ... --stage real15m-check --dir data/twin-real15m --days A,B,...
//   ... --stage twin-source --dir data/replay-drive --days C,D --out data/twin
//   ... --stage match --real data/twin-real15m --twin data/replay-src --days C,D [--warm-days E] --out data/twin
//   ... --stage fill --src data/twin/requote --dst data/twin/depth --how depth --depth-model data/models/depth_model.json --split-file data/twin/split.json
//   ... --stage features --dirs real=data/twin/real,requote=data/twin/requote,depth=data/twin/depth --days C,D --out data/twin
//   ... --stage backtest --dir data/twin/real --name real [--latency-ms 250] --days ... --out data/twin
//   ... --stage verdict --out data/twin [--confirm-look 2 --confirm-look-note "text"]   (reads features-*.json, windows-*.json, split.json; the note is required on the confirm days)
//
// Prints counts, cents, $ and AUCs only (the repository is public).

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { OrderBook } from '../bot/marketdata/orderBook';
import { recordingFiles, recordingLines } from '../bot/marketdata/recordingFiles';
import { gbdtLogit } from '../bot/model/trees';
import { trainGbdt } from './gbdt';

const MIN = 60_000, SLOT = 15_000;
const logit = (p: number) => { const q = Math.min(0.995, Math.max(0.005, p)); return Math.log(q / (1 - q)); };
// Markets the replays leave out (REPLAY_EXCLUDE, DOGE by default) are left out of the twin too.
const EXCLUDE_SRC = process.env.REPLAY_EXCLUDE ?? 'DOGE';
const EXCLUDE = EXCLUDE_SRC ? new RegExp(EXCLUDE_SRC) : undefined;
const is15m = (series: string | undefined, ticker: string) => (/15M/.test(series ?? '') || /15M-/.test(ticker)) && !EXCLUDE?.test(ticker);
const dayFile = (dir: string, day: string) => ['.jsonl.gz', '.jsonl'].map((x) => path.join(dir, `md-${day}${x}`)).find((f) => fs.existsSync(f));
const arg = (k: string, d = ''): string => { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : d; };

async function* events(file: string): AsyncGenerator<Record<string, any>> {
  for await (const line of recordingLines(file)) {
    if (!line) continue;
    try { yield JSON.parse(line); } catch { /* a cut line */ }
  }
}

async function writeGz(file: string, lines: AsyncIterable<string>, level = 1): Promise<void> {
  const gz = zlib.createGzip({ level });
  const done = new Promise<void>((ok, fail) => gz.pipe(fs.createWriteStream(file)).on('finish', ok).on('error', fail));
  for await (const s of lines) if (!gz.write(s)) await new Promise<void>((ok) => gz.once('drain', ok));
  gz.end();
  await done;
}

/** The tickers a day file lists (market records), with their series. */
async function tickersOf(file: string): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  // Only market records are parsed (a real day is tens of millions of book lines: parsing them all took hours, Nov 2).
  for await (const line of recordingLines(file)) {
    if (!line || !line.includes('"k":"market"')) continue;
    try { const e = JSON.parse(line); if (e.k === 'market' && e.ticker) out.set(e.ticker, e.series ?? ''); } catch { /* a cut line */ }
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------
// The split: FIT days (the depth model is fitted on these only) and JUDGED days never overlap.

/** The pre-registered splits (BRIEF.md). dev: iteration decisions are read on its judged days; confirm: read once at the
 *  end of a round, never tuned on. The workflow (.github/workflows/history-twin.yml) spells the same lists out and a test
 *  holds the two together. */
export const SPLITS = {
  dev: { fit: ['2026-11-11', '2026-11-12', '2026-11-15'], judge: ['2026-11-13', '2026-11-14', '2026-11-16', '2026-11-17'] },
  confirm: { fit: ['2026-11-11', '2026-11-12', '2026-11-15', '2026-11-13', '2026-11-14', '2026-11-16', '2026-11-17'], judge: ['2026-11-18', '2026-11-19', '2026-11-20'] },
} as const;

/** The days only split=confirm may read (the confirm split's judged days). They are held out: a dev or custom split cannot fit,
 *  judge or warm up on them, and every stage prints blind (counts and ok/no, no tables) for any split that judges one. */
export const CONFIRM_DAYS: readonly string[] = SPLITS.confirm.judge;
/** Leave-one-day-out needs a day to hold out and days left to train on: a custom split judges at least this many days
 *  (with one judged day every fold is skipped and the AUC is a flat 0.500, which reads as "indistinguishable"). */
export const MIN_CUSTOM_JUDGED_DAYS = 2;

export interface Split { name: string; fit: string[]; judge: string[]; warm: string[] }

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;
const isDay = (d: string) => DAY_RE.test(d) && new Date(`${d}T00:00:00Z`).toISOString().slice(0, 10) === d;

/** A comma (or space) separated list of YYYY-MM-DD days: each a real calendar day, repeats dropped, order kept. */
export function parseDays(s: string, what = 'days'): string[] {
  const out: string[] = [];
  for (const d of s.split(/[,\s]+/).filter(Boolean)) {
    if (!isDay(d)) throw new Error(`${what}: "${d}" is not a YYYY-MM-DD day`);
    if (!out.includes(d)) out.push(d);
  }
  return out;
}

/** A fit day never appears in a judged set. Throws (a stage then exits non-zero) naming the days that do. */
export function assertDisjoint(fit: readonly string[], judge: readonly string[]): void {
  const f = new Set(fit);
  const both = [...new Set(judge.filter((d) => f.has(d)))];
  if (both.length) throw new Error(`fit days and judged days overlap (a fit day must never be judged): ${both.join(', ')}`);
}

/** The confirm days are read only through split=confirm (with a look note). Any other split that names one of them as a fit,
 *  judged or warm-up day (or in `extra`, the days a stage was asked to read) throws: reading them through a dev or custom
 *  split would print the full tables and number no look. A split named confirm is exempt (its own days are the confirm days;
 *  resolveSplit holds a named split to SPLITS). */
export function assertHeldOut(split: Pick<Split, 'name' | 'fit' | 'judge'> & { warm?: string[] }, extra: readonly string[] = []): void {
  if (split.name === 'confirm') return;
  const leak = [...new Set([...split.fit, ...split.judge, ...(split.warm ?? []), ...extra].filter((d) => CONFIRM_DAYS.includes(d)))];
  if (leak.length) throw new Error(`the confirm days (${leak.join(', ')}) are read only through split=confirm with a confirm_look_note: they cannot be fit, judged or warm-up days of a ${split.name} split`);
}

/** Does this run read the confirm days? True for a split named confirm, and for any split (or `days`, the days a stage was
 *  asked to read) that touches one of the CONFIRM_DAYS, whatever the split is called: blindness follows the days, not the name. */
export const isBlind = (split?: Pick<Split, 'name' | 'judge'>, days: readonly string[] = []): boolean =>
  split?.name === 'confirm' || [...(split?.judge ?? []), ...days].some((d) => CONFIRM_DAYS.includes(d));

/** The named split, or a custom one; the lists a caller passes next to a named split must be that split's own (so the
 *  workflow's copy of the lists cannot drift from SPLITS). Both sets non-empty and disjoint; the confirm days only in the
 *  confirm split; a custom split judges at least MIN_CUSTOM_JUDGED_DAYS days. */
export function resolveSplit(name: string, fitIn = '', judgeIn = '', warmIn = ''): Split {
  let fit: string[], judge: string[];
  if (name === 'dev' || name === 'confirm') {
    fit = [...SPLITS[name].fit]; judge = [...SPLITS[name].judge];
    const gotFit = fitIn ? parseDays(fitIn, 'fit days') : fit, gotJudge = judgeIn ? parseDays(judgeIn, 'judged days') : judge;
    if (gotFit.join(',') !== fit.join(',') || gotJudge.join(',') !== judge.join(',')) throw new Error(`split ${name}: the fit/judged lists passed (${gotFit.join(',')} | ${gotJudge.join(',')}) are not the split's own (${fit.join(',')} | ${judge.join(',')})`);
  } else if (name === 'custom') {
    fit = parseDays(fitIn, 'fit days'); judge = parseDays(judgeIn, 'judged days');
  } else throw new Error(`unknown split "${name}" (dev, confirm or custom)`);
  if (!fit.length) throw new Error(`split ${name}: no fit days`);
  if (!judge.length) throw new Error(`split ${name}: no judged days`);
  const warm = parseDays(warmIn, 'warm days').filter((d) => !judge.includes(d));
  assertHeldOut({ name, fit, judge, warm });
  assertDisjoint(fit, judge);
  if (name === 'custom' && judge.length < MIN_CUSTOM_JUDGED_DAYS) throw new Error(`split custom: leave-one-day-out needs at least ${MIN_CUSTOM_JUDGED_DAYS} judged days (3 or more recommended), got ${judge.length}: with one judged day no fold runs and the AUC is a flat 0.500`);
  return { name, fit, judge, warm };
}

/** The depth model must have been fitted on fit days only (depthStudy writes the days it read into its output). */
export function assertModelFitDays(modelFile: string, split: Pick<Split, 'fit' | 'judge'>): void {
  const days: unknown = JSON.parse(fs.readFileSync(modelFile, 'utf8')).days;
  if (!Array.isArray(days) || !days.length) throw new Error(`${modelFile} does not record the days it was fitted on`);
  assertDisjoint(days as string[], split.judge);
  const stray = (days as string[]).filter((d) => !split.fit.includes(d));
  if (stray.length) throw new Error(`the depth model was fitted on days outside the fit set: ${stray.join(', ')}`);
}

const splitFile = (out: string) => path.join(out, 'split.json');
function readSplit(file: string): Split | undefined {
  try { const s = JSON.parse(fs.readFileSync(file, 'utf8')) as Split; return s && Array.isArray(s.fit) && Array.isArray(s.judge) ? { ...s, warm: s.warm ?? [] } : undefined; } catch { return undefined; }
}

function stageSplit(): void {
  const out = arg('out', 'data/twin');
  const sp = resolveSplit(arg('split', 'custom'), arg('fit-days'), arg('judge-days'), arg('warm-days'));
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(splitFile(out), JSON.stringify(sp, null, 1));
  // A confirm split prints day counts only.
  console.log(isBlind(sp)
    ? `[twin] split confirm: ${sp.fit.length} fit day(s), ${sp.judge.length} judged day(s), ${sp.warm.length} warm-up day(s); fit and judged days are disjoint`
    : `[twin] split ${sp.name}: fit ${sp.fit.length} day(s) (${sp.fit.join(' ')}), judged ${sp.judge.length} day(s) (${sp.judge.join(' ')}), warm-up ${sp.warm.length} (${sp.warm.join(' ') || 'none'}); fit and judged days are disjoint`);
}

// ---------------------------------------------------------------------------------------------------------------
// Stage prep: one raw recorded day reduced ONCE to what the judge and the backtests read.

/** The restriction's code version: bump it whenever the keep rules below change, and every cached day is stale. */
export const REAL15M_VERSION = 'r15m-1';
/** What a cached day was made with: the rule version and the exclusion pattern (REPLAY_EXCLUDE) in force. */
export const real15mTag = () => `${REAL15M_VERSION}|exclude=${EXCLUDE_SRC}`;
/** Lines with no ticker that no replay reads (research/replay.ts apply has no case for them): the spot book, whole depth of
 *  each coin every few seconds. Everything else without a ticker (index, spot, candles, dominance, perp, snn, gap, ...)
 *  is kept, as restrictDay always did. */
const DROP_KINDS: ReadonlySet<string> = new Set(['spot_book']);

export interface Real15mMeta { day: string; version: string; exclude: string; dropped: string[]; contracts: number; markets: number; events: number; rawLines: number; indexPrints: number; sourceBytes: number; bytes: number; seconds: number; sha256: string }

/** The record kind, read off the line's head ("k" follows "t" in every recorded line). '' when it is not there. */
function kindOf(line: string): string {
  const i = line.indexOf('"k":"');
  if (i < 0 || i > 48) return '';
  const j = line.indexOf('"', i + 5);
  return j > i ? line.slice(i + 5, j) : '';
}

/** The raw day's lines worth keeping, one pass. A line naming a ticker (read off the line, no parse) stays only when
 *  that ticker is a 15-minute contract the replays do not exclude; market records are parsed (a few thousand a day) to
 *  read their series, the rare lines listing several tickers are filtered, lines with no ticker stay unless nothing
 *  reads them. Nothing here looks at time, so nothing can look ahead. */
async function* prepLines(src: string, st: { raw: number; events: number; index: number; seen: Set<string>; markets: Set<string> }): AsyncGenerator<string> {
  const keep = new Map<string, boolean>();
  const wants = (tk: string): boolean => { let v = keep.get(tk); if (v === undefined) { v = is15m(undefined, tk); keep.set(tk, v); } return v; };
  for await (const line of recordingLines(src)) {
    if (!line) continue;
    st.raw++;
    let tk: string | undefined;
    const i = line.indexOf('"ticker":"');
    if (i >= 0) { const j = line.indexOf('"', i + 10); if (j > i) tk = line.slice(i + 10, j); }
    const kind = kindOf(line);
    if (tk !== undefined) {
      if (kind === 'market') {
        let e: Record<string, any>;
        try { e = JSON.parse(line); } catch { continue; /* a cut line */ }
        const ok = is15m(e.series, tk);
        keep.set(tk, ok);
        if (!ok) continue;
        st.markets.add(tk);
      } else if (!wants(tk)) continue;
      st.seen.add(tk);
    } else if (DROP_KINDS.has(kind)) continue;
    if (kind === 'index') st.index++;
    if (line.includes('"tickers"')) {
      let e: Record<string, any>;
      try { e = JSON.parse(line); } catch { continue; }
      if (Array.isArray(e.tickers)) { e.tickers = e.tickers.filter((t: string) => wants(t)); if (!e.tickers.length) continue; st.events++; yield JSON.stringify(e) + '\n'; continue; }
    }
    st.events++;
    yield line + '\n';
  }
}

const sha256File = (file: string): Promise<string> => new Promise((ok, fail) => {
  const h = crypto.createHash('sha256');
  fs.createReadStream(file).on('data', (c) => h.update(c)).on('end', () => ok(h.digest('hex'))).on('error', fail);
});

/** Reduce one raw recorded day to `<dstDir>/md-DAY.jsonl.gz` + `meta.json`. meta.json is the commit mark: removed first,
 *  written last, so a folder holding the day file without it is an unfinished prep. Refuses a day with no 15-minute
 *  contract or no index print (nothing a judge could use). The same input gives the same bytes. */
export async function prepDay(src: string, dstDir: string, day: string): Promise<Real15mMeta> {
  if (!isDay(day)) throw new Error(`prep: "${day}" is not a YYYY-MM-DD day`);
  const t0 = process.hrtime.bigint();
  fs.mkdirSync(dstDir, { recursive: true });
  const out = path.join(dstDir, `md-${day}.jsonl.gz`), tmp = `${out}.tmp`, metaFile = path.join(dstDir, 'meta.json');
  fs.rmSync(metaFile, { force: true });
  const st = { raw: 0, events: 0, index: 0, seen: new Set<string>(), markets: new Set<string>() };
  await writeGz(tmp, prepLines(src, st), 6);
  if (!st.seen.size || !st.events) { fs.rmSync(tmp, { force: true }); throw new Error(`prep ${day}: no 15-minute contract among ${st.raw} lines; nothing cached`); }
  if (!st.index) { fs.rmSync(tmp, { force: true }); throw new Error(`prep ${day}: no index print among ${st.raw} lines; nothing cached`); }
  fs.renameSync(tmp, out);
  const meta: Real15mMeta = { day, version: real15mTag(), exclude: EXCLUDE_SRC, dropped: [...DROP_KINDS], contracts: st.seen.size, markets: st.markets.size, events: st.events, rawLines: st.raw, indexPrints: st.index, sourceBytes: fs.statSync(src).size, bytes: fs.statSync(out).size, seconds: Math.round(Number(process.hrtime.bigint() - t0) / 1e7) / 100, sha256: await sha256File(out) };
  fs.writeFileSync(metaFile, JSON.stringify(meta, null, 1));
  return meta;
}

/** Is the day in `dir` (a Drive day folder: md-DAY.jsonl.gz + meta.json) made by this code? Idempotency: 'current' skips the
 *  prep. With `withFile` the day file must be there too, at the size meta.json recorded. */
export function prepStatus(dir: string, day: string, withFile = false): 'current' | 'stale' | 'absent' {
  let m: Partial<Real15mMeta>;
  try { m = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json'), 'utf8')); } catch { return 'absent'; }
  if (m.day !== day || m.version !== real15mTag()) return 'stale';
  if (withFile) { try { if (fs.statSync(path.join(dir, `md-${day}.jsonl.gz`)).size !== m.bytes) return 'stale'; } catch { return 'absent'; } }
  return 'current';
}

/** Are all these days cached in the flat folder the build assembles (md-DAY.jsonl.gz + meta-DAY.json) and current? */
export function checkReal15m(dir: string, days: readonly string[]): { ok: string[]; missing: string[]; stale: string[] } {
  const ok: string[] = [], missing: string[] = [], stale: string[] = [];
  for (const d of days) {
    const mf = path.join(dir, `meta-${d}.json`), df = path.join(dir, `md-${d}.jsonl.gz`);
    let m: Partial<Real15mMeta> | undefined;
    try { m = JSON.parse(fs.readFileSync(mf, 'utf8')); } catch { /* no meta */ }
    if (!m || !fs.existsSync(df) || !fs.statSync(df).size) { missing.push(d); continue; }
    if (m.day !== d || m.version !== real15mTag() || m.bytes !== fs.statSync(df).size) { stale.push(d); continue; }
    ok.push(d);
  }
  return { ok, missing, stale };
}

async function stagePrep(): Promise<void> {
  const raw = arg('raw'), day = arg('day'), out = arg('out');
  if (!raw || !day || !out) throw new Error('prep needs --raw (a day file or a folder holding it), --day and --out');
  const file = fs.existsSync(raw) && fs.statSync(raw).isDirectory() ? recordingFiles(raw).find((d) => d.day === day)?.file : raw;
  if (!file || !fs.existsSync(file)) throw new Error(`prep ${day}: no recording for that day in ${raw}`);
  const m = await prepDay(file, out, day);
  console.log(`[twin] prep ${day}: ${prepSummary(m)}`);
}

/** What the prep log line says about one reduced day (counts, MB, seconds, tag and hash only). */
export function prepSummary(m: Real15mMeta): string {
  const mb = (n: number) => (n / 1e6).toFixed(1);
  return `${m.contracts} contracts (${m.markets} market records), ${m.events} of ${m.rawLines} lines kept (${((100 * m.events) / Math.max(1, m.rawLines)).toFixed(1)}%), ${m.indexPrints} index prints; source ${mb(m.sourceBytes)} MB, written ${mb(m.bytes)} MB, ${m.seconds} s; version ${m.version}; sha256 ${m.sha256.slice(0, 12)}`;
}

/** The prep dispatch's report: one line per day from the meta.json each day's folder holds (`dir/DAY/meta.json`, pulled from
 *  Drive), DONE or NOT DONE with the reason, and a total. The prep jobs run in parallel and cannot hand their lines to one
 *  job, but the commit mark each leaves is the day's own record (a day with no meta.json, or one made by another version,
 *  is not done, whatever its job log says). `failedAt` (day -> the name of the prep job's failed step, read by the workflow
 *  from the run's jobs) says where a failed day stopped: such a day is NOT DONE even when Drive still holds a current mark,
 *  because the mark may be from an earlier prep (a re-prep that died between its day file and its meta.json). */
export function prepReport(dir: string, days: readonly string[], failedAt: Readonly<Record<string, string>> = {}): { lines: string[]; done: string[]; notDone: string[] } {
  const lines: string[] = [], done: string[] = [], notDone: string[] = [];
  for (const day of days) {
    const d = path.join(dir, day), s = prepStatus(d, day), step = failedAt[day];
    if (s === 'current' && !step) {
      done.push(day);
      lines.push(`[twin] prep ${day}: DONE; ${prepSummary(JSON.parse(fs.readFileSync(path.join(d, 'meta.json'), 'utf8')))}`);
    } else {
      notDone.push(day);
      const why = step
        ? `the prep job failed at step "${step}" (its reason is an annotation of this run: gh run view <run id>); ${s === 'absent' ? 'no meta.json on Drive' : s === 'current' ? 'Drive holds a current meta.json that may be from an earlier prep: prep it again with force_prep=true' : 'meta.json on Drive is for another day or made by another version'}`
        : s === 'absent' ? 'no meta.json on Drive: the prep job failed, timed out or was cancelled (its reason is an annotation of this run: gh run view <run id>)'
        : `meta.json is for another day or made by another version (this code's tag is ${real15mTag()}): prep it again with force_prep=true`;
      lines.push(`[twin] prep ${day}: NOT DONE; ${why}`);
    }
  }
  lines.push(`[twin] prep report: ${done.length} of ${days.length} day(s) done${notDone.length ? `; not done: ${notDone.join(', ')}` : ''}`);
  return { lines, done, notDone };
}

/** The failed-step file the workflow writes: one `DAY<TAB>STEP NAME` line per prep job that failed. */
export function parseFailedSteps(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const l of text.split('\n')) {
    const m = /^(\d{4}-\d{2}-\d{2})\t(.+)$/.exec(l.trim());
    if (m) out[m[1]] = m[2].replace(/[^\x20-\x7e]/g, ' ').slice(0, 120);
  }
  return out;
}

function stagePrepReport(): void {
  const dir = arg('dir'), days = parseDays(arg('days'), 'days'), failed = arg('failed');
  if (!dir || !days.length) throw new Error('prep-report needs --dir (a folder with one DAY/meta.json per day) and --days');
  const failedAt = failed && fs.existsSync(failed) ? parseFailedSteps(fs.readFileSync(failed, 'utf8')) : {};
  for (const l of prepReport(dir, days, failedAt).lines) console.log(l);
}

function stagePrepStatus(): void {
  const dir = arg('out'), day = arg('day');
  if (!dir || !day) throw new Error('prep-status needs --out and --day');
  const s = prepStatus(dir, day, process.argv.includes('--with-file'));
  console.log(`[twin] prep ${day}: ${s === 'current' ? 'already on Drive with this version tag, skipped' : s === 'stale' ? 'on Drive with another version tag or day; prepared again' : 'not on Drive yet; prepared'} (tag ${real15mTag()})`);
  process.exit(s === 'current' ? 0 : 11);
}

/** What to tell the dispatcher when cached real days are missing or made by another version (undefined: all there). */
export function real15mError(c: { missing: string[]; stale: string[] }): string | undefined {
  if (!c.missing.length && !c.stale.length) return undefined;
  const fix = [...c.missing, ...c.stale].sort().join(',');
  return `real 15-minute days ${c.missing.length ? `missing on Drive (derived/twin-real15m): ${c.missing.join(', ')}` : ''}${c.missing.length && c.stale.length ? '; ' : ''}${c.stale.length ? `made by another version: ${c.stale.join(', ')}` : ''}. Dispatch this workflow with prep_days=${fix}${c.stale.length ? ' force_prep=true' : ''} first, then run it again.`;
}

function stageReal15mCheck(): void {
  const dir = arg('dir'), days = parseDays(arg('days'), 'days');
  const c = checkReal15m(dir, days);
  console.log(`[twin] real 15-minute days: ${c.ok.length}/${days.length} present and current (tag ${real15mTag()})`);
  const err = real15mError(c);
  if (err) throw new Error(err);
}

// ---------------------------------------------------------------------------------------------------------------
// Stage twin-source: the requote days from Drive (simulated/kalshi-replay-200d) while its manifest is this code's replay
// version, the rest regenerated.

export function twinSource(dir: string, days: readonly string[], replayVersion: number): { manifestVersion?: number; drive: string[]; regen: string[]; reason: string } {
  let manifestVersion: number | undefined;
  try { manifestVersion = JSON.parse(fs.readFileSync(path.join(dir, 'replay-manifest.json'), 'utf8')).version; } catch { /* no manifest */ }
  if (manifestVersion !== replayVersion) return { manifestVersion, drive: [], regen: [...days], reason: manifestVersion === undefined ? 'no replay-manifest.json on Drive' : `Drive's replay manifest is version ${manifestVersion}, this code's REPLAY_VERSION is ${replayVersion}` };
  const drive = days.filter((d) => { try { return fs.statSync(path.join(dir, `md-${d}.jsonl.gz`)).size > 0; } catch { return false; } });
  const regen = days.filter((d) => !drive.includes(d));
  return { manifestVersion, drive, regen, reason: regen.length ? `not on Drive: ${regen.join(', ')}` : '' };
}

async function stageTwinSource(): Promise<void> {
  const dir = arg('dir'), out = arg('out', 'data/twin'), days = parseDays(arg('days'), 'days');
  const { REPLAY_VERSION } = await import('./history/historyReplay');
  const r = twinSource(dir, days, REPLAY_VERSION);
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, 'twin-source.json'), JSON.stringify({ replayVersion: REPLAY_VERSION, ...r }, null, 1));
  fs.writeFileSync(path.join(out, 'regen-days.txt'), r.regen.join(','));
  fs.writeFileSync(path.join(out, 'drive-days.txt'), r.drive.join(','));
  console.log(`[twin] requote source: ${r.drive.length} of ${days.length} day(s) from Drive simulated/kalshi-replay-200d (manifest version ${r.manifestVersion ?? 'none'}, REPLAY_VERSION ${REPLAY_VERSION})${r.regen.length ? `; ${r.regen.length} regenerated with research/kalshiReplayData.ts (${r.reason})` : ''}`);
}

// ---------------------------------------------------------------------------------------------------------------
// Stage match: the real days restricted to the contracts the twin has (same universe for the backtests), and the
// paired mechanics.

export interface Paired { day: string; realContracts: number; twinContracts: number; both: number; onlyReal15m: number; onlyTwin: number; quoteN: number; quoteMaeC: number; quoteBiasC: number; spreadRealC: number; spreadTwinC: number; indexN: number; indexMaeBps: number; indexBiasBps: number; results: number; resultsAgree: number }

/** The real day with every contract the twin lacks taken out (its market, book, delta, trade, result records; alive
 *  marks keep only the twin's tickers). */
const TICKER_RE = /"ticker":"([^"]+)"/;
async function restrictDay(src: string, dst: string, keep: Set<string>): Promise<void> {
  async function* lines(): AsyncGenerator<string> {
    for await (const line of recordingLines(src)) {
      if (!line) continue;
      // The ticker read straight off the line (no parse): only the rare lines listing several tickers are parsed.
      const m = TICKER_RE.exec(line);
      if (m && !keep.has(m[1])) continue;
      if (line.includes('"tickers"')) {
        let e: Record<string, any>;
        try { e = JSON.parse(line); } catch { continue; }
        if (e.ticker && !keep.has(e.ticker)) continue;
        if (Array.isArray(e.tickers)) { e.tickers = e.tickers.filter((t: string) => keep.has(t)); if (!e.tickers.length) continue; yield JSON.stringify(e) + '\n'; continue; }
      }
      yield line + '\n';
    }
  }
  await writeGz(dst, lines());
}

/** Per contract both ways at each minute mark: the twin's candle quote against the real book there; per asset the
 *  index at each 15 s print; the results. */
async function pairDay(day: string, realFile: string, twinFile: string, realT: Map<string, string>, twinT: Map<string, string>): Promise<Paired> {
  const both = [...twinT.keys()].filter((t) => realT.has(t));
  const bothSet = new Set(both);
  // The real side: book mid and spread at each minute mark, index at each 15 s slot.
  const realQ = new Map<string, { mid: number; spread: number }>(), realIx = new Map<string, number>(), realRes = new Map<string, string>();
  const books = new Map<string, OrderBook>(), lastIx = new Map<string, number>();
  let mark = -1;
  const reach = (t: number) => {
    const s = Math.floor(t / SLOT);
    if (mark < 0) { mark = s; return; }
    for (; mark < s; mark++) {
      const at = (mark + 1) * SLOT;
      for (const [a, v] of lastIx) realIx.set(`${a}|${at}`, v);
      if (at % MIN === 0) for (const [tk, b] of books) {
        const bb = b.bestBid()?.price, ba = b.bestAsk()?.price;
        if (bb !== undefined && ba !== undefined && ba > bb) realQ.set(`${tk}|${at}`, { mid: (bb + ba) / 2, spread: ba - bb });
      }
    }
  };
  for await (const e of events(realFile)) {
    reach(e.t);
    if (e.k === 'book' && bothSet.has(e.ticker)) { const b = books.get(e.ticker) ?? new OrderBook(e.ticker); books.set(e.ticker, b); b.applySnapshot({ bids: e.bids ?? [], asks: e.asks ?? [] }, e.t); }
    else if (e.k === 'delta' && bothSet.has(e.ticker)) { const b = books.get(e.ticker) ?? new OrderBook(e.ticker); books.set(e.ticker, b); b.applyDelta(e.side, e.price, e.delta, e.t); }
    else if (e.k === 'index' && e.asset && e.value > 0) lastIx.set(e.asset, e.value);
    else if (e.k === 'result' && e.ticker && e.result) realRes.set(e.ticker, String(e.result));
  }
  const p: Paired = { day, realContracts: realT.size, twinContracts: twinT.size, both: both.length, onlyReal15m: [...realT].filter(([t, s]) => is15m(s, t) && !twinT.has(t)).length, onlyTwin: [...twinT.keys()].filter((t) => !realT.has(t)).length, quoteN: 0, quoteMaeC: 0, quoteBiasC: 0, spreadRealC: 0, spreadTwinC: 0, indexN: 0, indexMaeBps: 0, indexBiasBps: 0, results: 0, resultsAgree: 0 };
  for await (const e of events(twinFile)) {
    if (e.k === 'book' && bothSet.has(e.ticker) && e.t % MIN === 0 && e.bids?.[0] && e.asks?.[0]) {
      const r = realQ.get(`${e.ticker}|${e.t}`);
      if (r === undefined) continue;
      const realMid = r.mid, rSpread = r.spread, tMid = (e.bids[0].price + e.asks[0].price) / 2;
      p.quoteN++; p.quoteMaeC += Math.abs(tMid - realMid) * 100; p.quoteBiasC += (tMid - realMid) * 100;
      p.spreadRealC += rSpread * 100; p.spreadTwinC += (e.asks[0].price - e.bids[0].price) * 100;
    } else if (e.k === 'index' && e.asset && e.value > 0 && e.t % SLOT === 0) {
      const r = realIx.get(`${e.asset}|${e.t}`);
      if (r === undefined) continue;
      const bps = (e.value / r - 1) * 1e4;
      p.indexN++; p.indexMaeBps += Math.abs(bps); p.indexBiasBps += bps;
    } else if (e.k === 'result' && bothSet.has(e.ticker) && realRes.has(e.ticker)) {
      p.results++; if (String(e.result) === realRes.get(e.ticker)) p.resultsAgree++;
    }
  }
  if (p.quoteN) { p.quoteMaeC /= p.quoteN; p.quoteBiasC /= p.quoteN; p.spreadRealC /= p.quoteN; p.spreadTwinC /= p.quoteN; }
  if (p.indexN) { p.indexMaeBps /= p.indexN; p.indexBiasBps /= p.indexN; }
  return p;
}

async function stageMatch(): Promise<void> {
  const realDir = arg('real', 'data/recordings'), twinDir = arg('twin', 'data/history-replay'), out = arg('out', 'data/twin');
  const days = arg('days').split(',').filter(Boolean);
  // Warm-up days (the day before a judged day, for the backtests' sake) are matched too but never judged.
  const warm = arg('warm-days').split(',').filter((d) => d && !days.includes(d));
  const split = readSplit(splitFile(out));
  if (split) { assertDisjoint(split.fit, days); assertHeldOut(split, [...days, ...warm]); }
  // Blind whenever a confirm day is read, whatever the split is called (and with no split on record at all).
  const quiet = isBlind(split, [...days, ...warm]);
  fs.mkdirSync(path.join(out, 'real'), { recursive: true });
  fs.mkdirSync(path.join(out, 'requote'), { recursive: true });
  const paired: Paired[] = [];
  const left: string[] = [];
  for (const day of [...warm, ...days]) {
    const rf = dayFile(realDir, day), tf = dayFile(twinDir, day);
    if (!rf || !tf) { console.log(`[twin] ${day}: ${rf ? '' : 'no real recording '}${tf ? '' : 'no history twin'}; left out`); left.push(day); continue; }
    const realT = await tickersOf(rf), twinT = await tickersOf(tf);
    // Contracts open at midnight are listed the day before: keep every twin ticker of this day and the day before.
    const keep = new Set(twinT.keys());
    const prev = dayFile(twinDir, new Date(Date.parse(`${day}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10));
    if (prev) for (const t of (await tickersOf(prev)).keys()) keep.add(t);
    await restrictDay(rf, path.join(out, 'real', `md-${day}.jsonl.gz`), keep);
    fs.copyFileSync(tf, path.join(out, 'requote', path.basename(tf)));
    // Paired on the restricted day (the twin's contracts only): the same records for those contracts, far fewer lines.
    const p = await pairDay(day, path.join(out, 'real', `md-${day}.jsonl.gz`), tf, realT, twinT);
    paired.push(p);
    if (!quiet) console.log(`[twin] ${day}: contracts real ${p.realContracts} / twin ${p.twinContracts} / both ${p.both} (real 15m missing from the twin ${p.onlyReal15m}, twin-only ${p.onlyTwin}); minute quote vs real mid: ${p.quoteN} pts, off ${p.quoteMaeC.toFixed(2)}c (bias ${p.quoteBiasC.toFixed(2)}c), spread real ${p.spreadRealC.toFixed(2)}c twin ${p.spreadTwinC.toFixed(2)}c; index ${p.indexN} pts off ${p.indexMaeBps.toFixed(1)} bps (bias ${p.indexBiasBps.toFixed(1)}); results agree ${p.resultsAgree}/${p.results}`);
  }
  // A confirm split reads no mechanics per day (nothing there to tune on): counts only.
  if (quiet) { const j = paired.filter((p) => days.includes(p.day)); console.log(`[twin] matched ${j.length} of ${days.length} judged day(s): ${j.reduce((a, p) => a + p.both, 0)} contracts in both, ${j.reduce((a, p) => a + p.onlyReal15m, 0)} real 15m missing from the twin, ${j.reduce((a, p) => a + p.onlyTwin, 0)} twin-only; results agree ${j.reduce((a, p) => a + p.resultsAgree, 0)}/${j.reduce((a, p) => a + p.results, 0)}`); }
  fs.writeFileSync(path.join(out, 'paired.json'), JSON.stringify(paired, null, 1));
  // With a split on record every judged day must be there: a verdict on fewer days than asked is not the verdict asked for.
  const lost = left.filter((d) => days.includes(d));
  if (split && lost.length) throw new Error(`judged day(s) without a real recording or a twin: ${lost.join(', ')}`);
}

// ---------------------------------------------------------------------------------------------------------------
// Stage features: one row per contract life, what the bot sees, sampled at the 15 s prints both sources share.

export const FEATURES = ['spreadC', 'topSize', 'depth10', 'quotedShare', 'quoteChangesPerMin', 'midMoveSd', 'minuteJumpShare', 'followIx', 'followIxLag', 'tradesPerMin', 'tradeSize', 'ixMoveBps', 'brierT5'] as const;
export type Row = { day: string; ticker: string; src: string; f: number[] };

const corr = (a: number[], b: number[]) => {
  const n = a.length; if (n < 5) return 0;
  const ma = a.reduce((x, y) => x + y, 0) / n, mb = b.reduce((x, y) => x + y, 0) / n;
  let sab = 0, saa = 0, sbb = 0;
  for (let i = 0; i < n; i++) { sab += (a[i] - ma) * (b[i] - mb); saa += (a[i] - ma) ** 2; sbb += (b[i] - mb) ** 2; }
  return saa > 0 && sbb > 0 ? sab / Math.sqrt(saa * sbb) : 0;
};

interface Life { ticker: string; asset: string; open: number; close: number; book: OrderBook; changes: number; lastTop: string; slots: Array<{ t: number; mid?: number; spread?: number; top?: number; depth?: number; ix?: number }>; trades: number; size: number }

/** Diagnostics (not features): the 15 s mid moves against the index moves, by price band and minute mark, per source. */
export const followDiag: Record<string, Record<string, { m: number[]; x: number[] }>> = {};

export async function dayRows(file: string, day: string, src: string, results: ReadonlyMap<string, string>, keep?: ReadonlySet<string>): Promise<Row[]> {
  const lives = new Map<string, Life>(), ix = new Map<string, number>();
  const d0 = Date.parse(`${day}T00:00:00Z`), d1 = d0 + 86_400_000;
  let slot = -1;
  const sample = (at: number) => {
    for (const l of lives.values()) {
      if (at < l.open || at > l.close) continue;
      const b = l.book.bestBid(), a = l.book.bestAsk();
      const ok = b && a && a.price > b.price;
      let depth = 0;
      if (ok) { const s = l.book.snapshot(10); for (const x of s.bids ?? []) if (b!.price - x.price <= 0.1 + 1e-9) depth += x.size; for (const x of s.asks ?? []) if (x.price - a!.price <= 0.1 + 1e-9) depth += x.size; }
      l.slots.push({ t: at, mid: ok ? (b!.price + a!.price) / 2 : undefined, spread: ok ? a!.price - b!.price : undefined, top: ok ? b!.size + a!.size : undefined, depth: ok ? depth : undefined, ix: ix.get(l.asset) });
    }
  };
  const reach = (t: number) => { const s = Math.floor(t / SLOT); if (slot < 0) slot = s; for (; slot < s; slot++) sample((slot + 1) * SLOT); };
  const touch = (l: Life) => { const b = l.book.bestBid(), a = l.book.bestAsk(); const k = `${b?.price}|${a?.price}`; if (k !== l.lastTop) { l.changes++; l.lastTop = k; } };
  for await (const e of events(file)) {
    reach(e.t);
    if (e.k === 'market' && e.ticker && is15m(e.series, e.ticker) && (!keep || keep.has(e.ticker))) {
      if (!lives.has(e.ticker)) lives.set(e.ticker, { ticker: e.ticker, asset: e.asset, open: e.openTime, close: e.closeTime, book: new OrderBook(e.ticker), changes: 0, lastTop: '', slots: [], trades: 0, size: 0 });
    } else if (e.k === 'book' && lives.has(e.ticker)) { const l = lives.get(e.ticker)!; l.book.applySnapshot({ bids: e.bids ?? [], asks: e.asks ?? [] }, e.t); touch(l); }
    else if (e.k === 'delta' && lives.has(e.ticker)) { const l = lives.get(e.ticker)!; l.book.applyDelta(e.side, e.price, e.delta, e.t); touch(l); }
    else if (e.k === 'trade' && lives.has(e.ticker)) { const l = lives.get(e.ticker)!; l.trades++; l.size += e.count ?? 0; }
    else if (e.k === 'index' && e.asset && e.value > 0) ix.set(e.asset, e.value);
  }
  const rows: Row[] = [];
  for (const l of lives.values()) {
    // Only contracts that close on this day and lived through it (the day before warms the books).
    if (l.close <= d0 || l.close > d1 || l.open < d0) continue;
    const q = l.slots.filter((s) => s.mid !== undefined);
    if (q.length < 20) continue;
    const mins = (l.close - l.open) / MIN;
    const dm: number[] = [], di: number[] = [], dmNext: number[] = [];
    let jumpAtMin = 0, jumpAll = 0;
    for (let i = 1; i < l.slots.length; i++) {
      const a = l.slots[i - 1], b = l.slots[i];
      if (a.mid === undefined || b.mid === undefined || !a.ix || !b.ix) continue;
      const m = logit(b.mid) - logit(a.mid), x = Math.log(b.ix / a.ix) * 1e4;
      dm.push(m); di.push(x);
      { const g = (followDiag[src] ??= {}); const k = `${a.mid < 0.1 || a.mid > 0.9 ? 'tails' : 'middle'}${b.t % MIN === 0 ? ' at minute' : ''}`; (g[k] ??= { m: [], x: [] }).m.push(m); g[k].x.push(x); }
      const c = l.slots[i + 1];
      dmNext.push(c?.mid !== undefined && b.mid !== undefined ? logit(c.mid) - logit(b.mid) : 0);
      jumpAll += Math.abs(m); if (b.t % MIN === 0) jumpAtMin += Math.abs(m);
    }
    const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
    const sd = (xs: number[]) => { const m = mean(xs); return Math.sqrt(mean(xs.map((x) => (x - m) ** 2))); };
    const t5 = [...q].reverse().find((s) => s.t <= l.close - 5 * MIN);
    const res = results.get(l.ticker);
    const y = res === 'yes' ? 1 : res === 'no' ? 0 : NaN;
    rows.push({ day, ticker: l.ticker, src, f: [
      mean(q.map((s) => s.spread! * 100)), Math.log1p(mean(q.map((s) => s.top!))), Math.log1p(mean(q.map((s) => s.depth!))), q.length / Math.max(1, l.slots.length),
      l.changes / mins, sd(dm), jumpAll > 0 ? jumpAtMin / jumpAll : 0, corr(dm, di), corr(dmNext, di),
      l.trades / mins, l.trades ? Math.log1p(l.size / l.trades) : 0, sd(di), t5 && Number.isFinite(y) ? (t5.mid! - y) ** 2 : NaN,
    ] });
  }
  return rows;
}

async function resultsOf(dir: string, days: string[]): Promise<Map<string, string>> {
  const r = new Map<string, string>();
  for (const d of days) { const f = dayFile(dir, d); if (f) for await (const line of recordingLines(f)) { if (!line || !line.includes('"k":"result"')) continue; try { const e = JSON.parse(line); if (e.ticker && e.result) r.set(e.ticker, String(e.result)); } catch { /* a cut line */ } } }
  return r;
}

async function stageFeatures(): Promise<void> {
  const out = arg('out', 'data/twin');
  const days = arg('days').split(',').filter(Boolean);
  const split = readSplit(splitFile(out));
  if (split) { assertDisjoint(split.fit, days); assertHeldOut(split, days); }
  // A confirm split (or any run that reads a confirm day) prints no per-day activity or follow tables (the optimizer must
  // not tune on those rows).
  const quiet = isBlind(split, days);
  const dirs = Object.fromEntries(arg('dirs').split(',').filter(Boolean).map((kv) => kv.split('=') as [string, string]));
  // Labels from Kalshi's own results (the twin carries them for every contract), the same for both sides.
  const results = await resultsOf(dirs.requote ?? Object.values(dirs)[0], days);
  for (const [src, dir] of Object.entries(dirs)) {
    const rows: Row[] = [];
    for (const d of days) { const f = dayFile(dir, d); if (f) rows.push(...(await dayRows(f, d, src, results))); }
    fs.writeFileSync(path.join(out, `features-${src}.json`), JSON.stringify(rows));
    console.log(`[twin] features ${src}: ${rows.length} contract lives over ${days.length} day(s)`);
    if (quiet) continue;
    // Per day (and, for the real side, the days around them, not judged: Nov 4, the depth model's fit days traded ~2.6x
    // the compared days a minute), the activity features' means. --extra-dir: where those extra days are (the cached
    // restricted real days, which hold the fit days too).
    const extra = src === 'real' ? arg('extra-days', '').split(',').filter((d) => d && !days.includes(d) && !CONFIRM_DAYS.includes(d)) : [];
    const perDay = new Map<string, Row[]>();
    for (const r of rows) perDay.set(r.day, [...(perDay.get(r.day) ?? []), r]);
    for (const d of extra) { const f = dayFile(arg('extra-dir') || dir, d); if (f) perDay.set(`${d} (not judged)`, await dayRows(f, d, src, results)); }
    const fi = (k: string) => FEATURES.indexOf(k as (typeof FEATURES)[number]);
    for (const [k, g] of Object.entries(followDiag[src] ?? {})) {
      const sdv = (xs: number[]) => { const mu = xs.reduce((a, b) => a + b, 0) / Math.max(1, xs.length); return Math.sqrt(xs.reduce((a, b) => a + (b - mu) ** 2, 0) / Math.max(1, xs.length)); };
      console.log(`[twin] ${src} follow ${k}: ${g.m.length} moves, corr ${corr(g.m, g.x).toFixed(3)}, mid move sd ${sdv(g.m).toFixed(3)}, zero moves ${(g.m.filter((v) => v === 0).length / Math.max(1, g.m.length) * 100).toFixed(0)}%`);
    }
    for (const [d, rs] of perDay) {
      const m = (k: string) => (rs.length ? rs.reduce((a, r) => a + (Number.isFinite(r.f[fi(k)]) ? r.f[fi(k)] : 0), 0) / rs.length : NaN).toFixed(2);
      console.log(`[twin] ${src} ${d}: ${rs.length} lives, trades/min ${m('tradesPerMin')}, tradeSize ${m('tradeSize')}, topSize ${m('topSize')}, depth10 ${m('depth10')}, quote changes/min ${m('quoteChangesPerMin')}, followIx ${m('followIx')}, spread ${m('spreadC')}c`);
    }
  }
}

// ---------------------------------------------------------------------------------------------------------------
// The adversary: tell twin rows from real rows, leaving one day out.

export function auc(scores: number[], labels: number[]): number {
  const idx = scores.map((s, i) => [s, labels[i]] as const).sort((a, b) => a[0] - b[0]);
  let sumPos = 0, nPos = 0;
  for (let i = 0; i < idx.length;) {
    let j = i; while (j < idx.length && idx[j][0] === idx[i][0]) j++;
    const r = (i + j + 1) / 2; // average rank (1-based) of the tie group
    for (let k = i; k < j; k++) if (idx[k][1]) { sumPos += r; nPos++; }
    i = j;
  }
  const nNeg = idx.length - nPos;
  return nPos && nNeg ? (sumPos - (nPos * (nPos + 1)) / 2) / (nPos * nNeg) : 0.5;
}

/** Logistic regression (L2, plain gradient descent) on standardized features; NaN features impute to the mean. */
export function fitLogit(X: number[][], y: number[], l2 = 0.01, iters = 400, lr = 0.3): (x: number[]) => number {
  const d = X[0]?.length ?? 0;
  const mu = Array.from({ length: d }, (_, j) => { const v = X.map((r) => r[j]).filter(Number.isFinite); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0; });
  const sg = Array.from({ length: d }, (_, j) => { const v = X.map((r) => r[j]).filter(Number.isFinite); const s = Math.sqrt(v.reduce((a, b) => a + (b - mu[j]) ** 2, 0) / Math.max(1, v.length)); return s > 1e-12 ? s : 1; });
  const z = (r: number[]) => r.map((v, j) => (Number.isFinite(v) ? (v - mu[j]) / sg[j] : 0));
  const Z = X.map(z);
  const w = new Array(d).fill(0); let b = 0;
  for (let it = 0; it < iters; it++) {
    const gw = new Array(d).fill(0); let gb = 0;
    for (let i = 0; i < Z.length; i++) {
      let s = b; for (let j = 0; j < d; j++) s += w[j] * Z[i][j];
      const e = 1 / (1 + Math.exp(-s)) - y[i];
      gb += e; for (let j = 0; j < d; j++) gw[j] += e * Z[i][j];
    }
    b -= (lr * gb) / Z.length;
    for (let j = 0; j < d; j++) w[j] -= lr * (gw[j] / Z.length + l2 * w[j]);
  }
  return (x: number[]) => { const zz = z(x); let s = b; for (let j = 0; j < d; j++) s += w[j] * zz[j]; return 1 / (1 + Math.exp(-s)); };
}

/** Leave-one-day-out AUC of telling `twin` rows (label 1) from `real` rows (label 0), on the feature columns `cols`. */
export function discriminate(real: Row[], twin: Row[], cols: number[]): number {
  const all = [...real.map((r) => ({ r, y: 0 })), ...twin.map((r) => ({ r, y: 1 }))];
  const days = [...new Set(all.map((a) => a.r.day))].sort();
  const sc: number[] = [], lb: number[] = [];
  for (const d of days) {
    const tr = all.filter((a) => a.r.day !== d), te = all.filter((a) => a.r.day === d);
    if (!te.length || new Set(tr.map((a) => a.y)).size < 2) continue;
    const f = fitLogit(tr.map((a) => cols.map((c) => a.r.f[c])), tr.map((a) => a.y));
    for (const a of te) { sc.push(f(cols.map((c) => a.r.f[c]))); lb.push(a.y); }
  }
  return auc(sc, lb);
}

// ---------------------------------------------------------------------------------------------------------------
// Diagnostics (they only read the rows; the judge above is untouched) and the report-only stress adversary.

/** Linear-interpolated quantile ("type 7": p10 of 1..11 is 2) of the finite values; NaN when there are none. */
export function quantile(xs: readonly number[], p: number): number {
  const v = xs.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return NaN;
  const h = (v.length - 1) * Math.min(1, Math.max(0, p)), lo = Math.floor(h), hi = Math.ceil(h);
  return v[lo] + (v[hi] - v[lo]) * (h - lo);
}

/** p10, p50, p90 of one feature column. */
export const quantiles3 = (rows: readonly Row[], j: number): [number, number, number] => [0.1, 0.5, 0.9].map((p) => quantile(rows.map((r) => r.f[j]), p)) as [number, number, number];

/** Pearson correlation of every pair of feature columns over the rows where both are finite (the judge's own `corr`). */
export function corrMatrix(rows: readonly Row[]): number[][] {
  const d = FEATURES.length;
  const m = Array.from({ length: d }, () => new Array<number>(d).fill(0));
  for (let a = 0; a < d; a++) {
    m[a][a] = 1;
    for (let b = a + 1; b < d; b++) {
      const x: number[] = [], y: number[] = [];
      for (const r of rows) if (Number.isFinite(r.f[a]) && Number.isFinite(r.f[b])) { x.push(r.f[a]); y.push(r.f[b]); }
      m[a][b] = m[b][a] = corr(x, y);
    }
  }
  return m;
}

/** The `k` feature pairs whose correlation differs most between the real and the twin rows (ties in feature order). */
export function topCorrDiffs(real: readonly Row[], twin: readonly Row[], k = 10): Array<{ a: string; b: string; real: number; twin: number; diff: number }> {
  const R = corrMatrix(real), T = corrMatrix(twin), all: Array<{ a: string; b: string; real: number; twin: number; diff: number }> = [];
  for (let a = 0; a < FEATURES.length; a++) for (let b = a + 1; b < FEATURES.length; b++) all.push({ a: FEATURES[a], b: FEATURES[b], real: R[a][b], twin: T[a][b], diff: Math.abs(R[a][b] - T[a][b]) });
  return all.sort((x, y) => y.diff - x.diff).slice(0, k);
}

/** discriminate()'s own folds (same training, same scores, so the same pooled AUC), with the AUC of each held-out day
 *  beside it (null when a day holds only one source). */
export function discriminatePerDay(real: Row[], twin: Row[], cols: number[]): { auc: number; byDay: Array<{ day: string; auc: number | null; real: number; twin: number }> } {
  const all = [...real.map((r) => ({ r, y: 0 })), ...twin.map((r) => ({ r, y: 1 }))];
  const days = [...new Set(all.map((a) => a.r.day))].sort();
  const sc: number[] = [], lb: number[] = [], byDay: Array<{ day: string; auc: number | null; real: number; twin: number }> = [];
  for (const d of days) {
    const tr = all.filter((a) => a.r.day !== d), te = all.filter((a) => a.r.day === d);
    if (!te.length || new Set(tr.map((a) => a.y)).size < 2) continue;
    const f = fitLogit(tr.map((a) => cols.map((c) => a.r.f[c])), tr.map((a) => a.y));
    const s = te.map((a) => f(cols.map((c) => a.r.f[c]))), l = te.map((a) => a.y);
    for (let i = 0; i < s.length; i++) { sc.push(s[i]); lb.push(l[i]); }
    byDay.push({ day: d, auc: new Set(l).size === 2 ? auc(s, l) : null, real: l.filter((y) => y === 0).length, twin: l.filter((y) => y === 1).length });
  }
  return { auc: auc(sc, lb), byDay };
}

/** The stress adversary's boosted trees (research/gbdt.ts): depth 3, a fixed seed and no row or feature sampling, so the
 *  same rows give the same trees. */
const STRESS_PARAMS = { nTrees: 400, learningRate: 0.1, maxDepth: 3, minLeafWeight: 5, lambda: 2, featureFraction: 1, baggingFraction: 1, maxBins: 32, patience: 40, seed: 7, loss: 'logistic' as const };

/** REPORT ONLY (never part of the pass bar): leave-one-day-out AUC of a boosted-tree classifier telling twin rows (1) from
 *  real rows (0) on the same rows and folds as `discriminate`. It sees interactions the logistic adversary cannot. In each
 *  fold every 5th training row is held back to stop the boosting early; the test day is never seen. */
export function stressAuc(real: Row[], twin: Row[], cols: number[]): number {
  const all = [...real.map((r) => ({ r, y: 0 })), ...twin.map((r) => ({ r, y: 1 }))];
  const days = [...new Set(all.map((a) => a.r.day))].sort();
  const sc: number[] = [], lb: number[] = [];
  const X = (a: { r: Row }) => cols.map((c) => a.r.f[c]), Y = (a: { y: number }) => a.y;
  for (const d of days) {
    const tr = all.filter((a) => a.r.day !== d), te = all.filter((a) => a.r.day === d);
    if (!te.length || new Set(tr.map((a) => a.y)).size < 2) continue;
    const fit = tr.filter((_, i) => i % 5 !== 4), val = tr.filter((_, i) => i % 5 === 4);
    if (!val.length || new Set(fit.map(Y)).size < 2) continue;
    const { model } = trainGbdt(fit.map(X), fit.map(Y), fit.map(() => 1), fit.map(() => 0), val.map(X), val.map(Y), val.map(() => 1), val.map(() => 0), STRESS_PARAMS);
    for (const a of te) { sc.push(gbdtLogit(model, X(a))); lb.push(a.y); }
  }
  return auc(sc, lb);
}

// ---------------------------------------------------------------------------------------------------------------
// Stage verdict.

type Win = Map<number, { pnl: number; contracts: number }>;
const readWin = (f: string): Win => new Map(JSON.parse(fs.readFileSync(f, 'utf8')));

export function outcome(real: Win, other: Win, seed = 1): { pnl: number; realPnl: number; traded: number; realTraded: number; meanDiff: number; lo: number; hi: number; rmse: number; corr: number } {
  const keys = [...new Set([...real.keys(), ...other.keys()])].filter((k) => (real.get(k)?.contracts ?? 0) > 0 || (other.get(k)?.contracts ?? 0) > 0);
  const a = keys.map((k) => real.get(k)?.pnl ?? 0), b = keys.map((k) => other.get(k)?.pnl ?? 0), d = b.map((x, i) => x - a[i]);
  const n = d.length, mean = n ? d.reduce((x, y) => x + y, 0) / n : 0;
  let s = seed >>> 0 || 1; const rnd = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  const boots: number[] = [];
  for (let k = 0; k < 2000 && n; k++) { let t = 0; for (let i = 0; i < n; i++) t += d[Math.floor(rnd() * n)]; boots.push(t / n); }
  boots.sort((x, y) => x - y);
  return { pnl: b.reduce((x, y) => x + y, 0), realPnl: a.reduce((x, y) => x + y, 0), traded: keys.filter((k) => (other.get(k)?.contracts ?? 0) > 0).length, realTraded: keys.filter((k) => (real.get(k)?.contracts ?? 0) > 0).length, meanDiff: mean, lo: boots[Math.floor(0.025 * boots.length)] ?? 0, hi: boots[Math.floor(0.975 * boots.length)] ?? 0, rmse: Math.sqrt(n ? d.reduce((x, y) => x + y * y, 0) / n : 0), corr: corr(a, b) };
}

/** The decision model's backtest on one folder (replayFidelity's, the production settings), windows of `days` only. */
async function stageBacktest(): Promise<void> {
  const { backtestDir, onDays } = await import('./replayFidelity');
  const dir = arg('dir'), model = arg('model', 'data/models/model.json'), out = arg('out', 'data/twin'), name = arg('name');
  const days = arg('days').split(',').filter(Boolean);
  const extra: Record<string, string> = arg('latency-ms') ? { 'latency-ms': arg('latency-ms') } : {};
  const w = onDays(await backtestDir(dir, model, extra), days);
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, `windows-${name}.json`), JSON.stringify([...w.entries()]));
}

/** The twin's days through the tally's fill-in (research/goLiveTally.ts fillDayFile), as the deep history plays them. */
async function stageFill(): Promise<void> {
  const { fillDayFile, depthSims } = await import('./goLiveTally');
  const { readDepthModel } = await import('./history/depthSim');
  const src = arg('src'), dst = arg('dst'), how = arg('how', 'depth') as 'depth' | 'worst' | 'hold' | 'requote';
  const depth = arg('depth-model') ? readDepthModel(arg('depth-model')) : undefined;
  if (how === 'depth' && !depth) throw new Error('the depth fill-in needs --depth-model');
  // With a split on record the model must have been fitted on fit days only.
  if (how === 'depth' && arg('split-file')) {
    const sp = readSplit(arg('split-file'));
    if (!sp) throw new Error(`no split in ${arg('split-file')}`);
    assertHeldOut(sp);
    assertModelFitDays(arg('depth-model'), sp);
    console.log(`[twin] depth model fitted on fit days only (checked against the split's ${sp.fit.length} fit and ${sp.judge.length} judged day(s))`);
  }
  fs.mkdirSync(dst, { recursive: true });
  for (const f of fs.readdirSync(src).filter((x) => x.startsWith('md-'))) await fillDayFile(path.join(src, f), path.join(dst, f), { how }, depth);
  console.log(`[twin] ${how} fill-in written for ${fs.readdirSync(dst).length} day(s)`);
  if (depthSims.length) {
    const t = depthSims.reduce((a, x) => ({ seconds: a.seconds + x.stats.seconds, trades: a.trades + x.stats.trades, sweepPrints: a.sweepPrints + x.stats.sweepPrints, flickers: a.flickers + x.stats.flickers }), { seconds: 0, trades: 0, sweepPrints: 0, flickers: 0 });
    const perMin = (n: number) => (t.seconds ? ((60 * n) / t.seconds).toFixed(1) : '0');
    console.log(`[twin] ${arg('dst')} simulator: ${Math.round(t.seconds / 60)} contract-minutes, trades ${perMin(t.trades)}/min (sweep prints ${perMin(t.sweepPrints)}), flickers ${perMin(t.flickers)}/min`);
  }
}

/** A confirm look: the dispatch's note (free text) and its number (how many confirm looks there have been, counted by
 *  the workflow from the looks it logged on Drive). */
export interface ConfirmLook { n?: number; note: string }
const lookFromArgs = (): ConfirmLook | undefined => {
  const note = arg('confirm-look-note').replace(/[\u0000-\u001f\u007f]+/g, ' ').trim().slice(0, 200);
  return note ? { n: Number(arg('confirm-look')) || undefined, note } : undefined;
};

const fmtQ = (x: number) => (Number.isFinite(x) ? String(+x.toPrecision(3)) : 'na');

export async function stageVerdict(out = arg('out', 'data/twin'), look: ConfirmLook | undefined = lookFromArgs()): Promise<Record<string, any>> {
  const split = readSplit(splitFile(out));
  if (split) { assertDisjoint(split.fit, split.judge); assertHeldOut(split); }
  const rows = (src: string): Row[] => { const f = path.join(out, `features-${src}.json`); return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : []; };
  const real = rows('real');
  // split=confirm: read once at the end of a round, never tuned on. Its verdict prints ONLY the pass/fail checks, the AUC,
  // the STRESS AUC and day counts: no per-feature, per-regime, per-day or correlation tables (and verdict.json holds no more).
  // Blindness follows the days, not the split's name: a split that judges a confirm day, or rows of a confirm day with no
  // split on record, are blind too. Every blind verdict is a look: it needs its note (the workflow numbers and logs it).
  const confirm = isBlind(split, [...new Set(real.map((r) => r.day))]);
  if (confirm && !look) throw new Error('a verdict on the confirm days is a look: it needs a confirm look note (workflow input confirm_look_note, --confirm-look-note), which is numbered and logged on Drive');
  const report: Record<string, any> = { at: new Date().toISOString(), split: split ? { name: split.name, fit: confirm ? split.fit.length : split.fit, judge: confirm ? split.judge.length : split.judge } : undefined, paired: !confirm && fs.existsSync(path.join(out, 'paired.json')) ? JSON.parse(fs.readFileSync(path.join(out, 'paired.json'), 'utf8')) : [], twins: {} };
  const placebo = fs.existsSync(path.join(out, 'windows-placebo.json')) && fs.existsSync(path.join(out, 'windows-real.json')) ? outcome(readWin(path.join(out, 'windows-real.json')), readWin(path.join(out, 'windows-placebo.json'))) : undefined;
  if (confirm) console.log(`[twin] confirm split: ${split ? `${split.fit.length} fit day(s), ${split.judge.length} judged day(s)` : `no split on record, ${new Set(real.map((r) => r.day)).size} day(s) of rows`}; ${real.length} real contract lives`);
  else {
    report.placebo = placebo;
    // The adversary's sanity check: real against real (two halves of the real days' contracts) must score ~0.5.
    const half = real.filter((_, i) => i % 2 === 0), other = real.filter((_, i) => i % 2 === 1).map((r) => ({ ...r, src: 'real-b' }));
    report.realVsReal = +discriminate(half, other, FEATURES.map((_, j) => j)).toFixed(3);
    console.log(`[twin] adversary sanity, real vs real: AUC ${report.realVsReal}`);
    if (placebo) console.log(`[twin] placebo (real at +250 ms): P&L $${placebo.pnl.toFixed(2)} vs $${placebo.realPnl.toFixed(2)}, per-window error $${placebo.rmse.toFixed(2)}, corr ${placebo.corr.toFixed(2)}`);
  }
  for (const src of ['requote', 'depth', 'lag', 'lagdepth', 'worst', 'hold']) {
    const tw = rows(src);
    if (!tw.length) continue;
    const all = FEATURES.map((_, j) => j);
    const a = discriminate(real, tw, all);
    const each = confirm ? [] : FEATURES.map((name, j) => ({ name, auc: +discriminate(real, tw, [j]).toFixed(3), real: +med(real.map((r) => r.f[j])).toFixed(4), twin: +med(tw.map((r) => r.f[j])).toFixed(4) })).sort((x, y) => Math.abs(y.auc - 0.5) - Math.abs(x.auc - 0.5));
    const wf = path.join(out, `windows-${src}.json`), rf = path.join(out, 'windows-real.json');
    const o = fs.existsSync(wf) && fs.existsSync(rf) ? outcome(readWin(rf), readWin(wf)) : undefined;
    const checks = {
      indistinguishable: a <= 0.6,
      noBias: o ? o.lo <= 0 && o.hi >= 0 : false,
      errorWithinNoise: o && placebo ? o.rmse <= 1.5 * Math.max(placebo.rmse, 1e-9) : false,
      sameActivity: o ? Math.abs(o.traded - o.realTraded) <= 0.1 * Math.max(1, o.realTraded) : false,
    };
    const pass = Object.values(checks).every(Boolean);
    // REPORT ONLY: a tree-based second adversary on the same rows and folds. It is not in `checks`, so it cannot decide `pass`.
    const stress = stressAuc(real, tw, all);
    const stressLine = `[twin] STRESS ${src}: boosted-tree adversary AUC ${stress.toFixed(3)} (leave-one-day-out, same rows; report only, never part of pass/fail)`;
    if (confirm) {
      report.twins[src] = { auc: +a.toFixed(3), stress: +stress.toFixed(3), real: real.length, twin: tw.length, checks, pass };
      console.log(`[twin] ${src}: adversary AUC ${a.toFixed(3)} (0.5 = can't tell; pass <= 0.60) over ${real.length} real / ${tw.length} twin contract lives`);
      console.log(stressLine);
      console.log(`[twin] ${src}: ${pass ? 'PASS' : 'FAIL'} (${Object.entries(checks).map(([k, v]) => `${k} ${v ? 'ok' : 'no'}`).join(', ')})`);
      continue;
    }
    // Regimes (Steven, Nov 1: dynamics wherever possible): the adversary again within calm / normal / volatile contract
    // lives (terciles of the index's 15 s move over the real rows), so a fill-in can be fitted per regime where they differ.
    const vi = FEATURES.indexOf('ixMoveBps');
    const cuts = [1 / 3, 2 / 3].map((q) => { const v = real.map((r) => r.f[vi]).filter(Number.isFinite).sort((x, y) => x - y); return v[Math.floor(q * v.length)] ?? 0; });
    const regimeOf = (r: Row) => (r.f[vi] <= cuts[0] ? 'calm' : r.f[vi] <= cuts[1] ? 'normal' : 'volatile');
    const regimes = Object.fromEntries(['calm', 'normal', 'volatile'].map((g) => {
      const rr = real.filter((r) => regimeOf(r) === g), tt = tw.filter((r) => regimeOf(r) === g);
      const top = FEATURES.map((name, j) => ({ name, auc: discriminate(rr, tt, [j]) })).sort((x, y) => Math.abs(y.auc - 0.5) - Math.abs(x.auc - 0.5))[0];
      return [g, { real: rr.length, twin: tt.length, auc: rr.length > 20 && tt.length > 20 ? +discriminate(rr, tt, all).toFixed(3) : null, top: top ? `${top.name} ${top.auc.toFixed(3)}` : '' }];
    }));
    console.log(`[twin] ${src}: by regime: ${Object.entries(regimes).map(([g, x]) => `${g} AUC ${x.auc ?? 'n/a'} (${x.real}/${x.twin}; worst ${x.top})`).join('; ')}`);
    // The diagnostics block: per feature the real and twin p10/p50/p90 (all rows, then within each regime), the pairs whose
    // correlation differs most, and the AUC of each judged day (the same folds as the headline AUC).
    const groups = ['all', 'calm', 'normal', 'volatile'] as const;
    const of = (rs: Row[], g: (typeof groups)[number]) => (g === 'all' ? rs : rs.filter((r) => regimeOf(r) === g));
    const quant = Object.fromEntries(FEATURES.map((name, j) => [name, Object.fromEntries(groups.map((g) => [g, { real: quantiles3(of(real, g), j), twin: quantiles3(of(tw, g), j) }]))]));
    const gaps = topCorrDiffs(real, tw, 10);
    const perDay = discriminatePerDay(real, tw, all);
    report.twins[src] = { auc: +a.toFixed(3), stress: +stress.toFixed(3), aucByDay: perDay.byDay.map((d) => ({ ...d, auc: d.auc === null ? null : +d.auc.toFixed(3) })), features: each, regimes, quantiles: quant, corrGaps: gaps.map((g) => ({ ...g, real: +g.real.toFixed(3), twin: +g.twin.toFixed(3), diff: +g.diff.toFixed(3) })), outcome: o, checks, pass };
    console.log(`[twin] ${src}: adversary AUC ${a.toFixed(3)} (0.5 = can't tell; pass <= 0.60) over ${real.length} real / ${tw.length} twin contract lives`);
    console.log(`[twin] ${src}: gives it away most: ${each.slice(0, 5).map((e) => `${e.name} ${e.auc} (real median ${e.real}, twin median ${e.twin})`).join('; ')}`);
    console.log(`[twin] ${src}: every feature (AUC, real median/twin median): ${each.map((e) => `${e.name} ${e.auc} ${e.real}/${e.twin}`).join('; ')}`);
    console.log(`[twin] ${src}: AUC by judged day: ${perDay.byDay.map((d) => `${d.day} ${d.auc === null ? 'n/a' : d.auc.toFixed(3)} (${d.real} real/${d.twin} twin)`).join('; ')}`);
    console.log(stressLine);
    for (const [j, name] of FEATURES.entries()) console.log(`[twin] ${src} quantiles ${name} p10/p50/p90: ${groups.map((g) => `${g} real ${quantiles3(of(real, g), j).map(fmtQ).join('/')} twin ${quantiles3(of(tw, g), j).map(fmtQ).join('/')}`).join(' | ')}`);
    for (const [i, g] of gaps.entries()) console.log(`[twin] ${src} correlation gap #${i + 1}: ${g.a} ~ ${g.b}: real ${g.real.toFixed(2)}, twin ${g.twin.toFixed(2)} (diff ${g.diff.toFixed(2)})`);
    if (o) console.log(`[twin] ${src}: backtest P&L $${o.pnl.toFixed(2)} vs real $${o.realPnl.toFixed(2)}; windows ${o.traded} vs ${o.realTraded}; per-window diff $${o.meanDiff.toFixed(3)} [${o.lo.toFixed(3)}, ${o.hi.toFixed(3)}]; error $${o.rmse.toFixed(2)} (placebo $${placebo?.rmse.toFixed(2) ?? '?'}); corr ${o.corr.toFixed(2)}`);
    console.log(`[twin] ${src}: ${pass ? 'PASS' : 'FAIL'} (${Object.entries(checks).map(([k, v]) => `${k} ${v ? 'ok' : 'no'}`).join(', ')})`);
  }
  if (confirm && look) { report.look = { n: look.n ?? null }; console.log(`[twin] CONFIRM LOOK #${look.n ?? '?'}: ${look.note}`); }
  // (a blind verdict without a look threw at the top, before anything was read or printed)
  fs.writeFileSync(path.join(out, 'verdict.json'), JSON.stringify(report, null, 1));
  return report;
}

const med = (xs: number[]) => { const v = xs.filter(Number.isFinite).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : NaN; };

export async function historyTwinMain(): Promise<void> {
  const stage = arg('stage', 'verdict');
  if (stage === 'prep') return stagePrep();
  if (stage === 'prep-status') return stagePrepStatus();
  if (stage === 'prep-report') return stagePrepReport();
  if (stage === 'split') return stageSplit();
  if (stage === 'real15m-check') return stageReal15mCheck();
  if (stage === 'twin-source') return stageTwinSource();
  if (stage === 'match') return stageMatch();
  if (stage === 'features') return stageFeatures();
  if (stage === 'backtest') return stageBacktest();
  if (stage === 'fill') return stageFill();
  if (stage === 'verdict') { await stageVerdict(); return; }
  throw new Error(`unknown --stage ${stage}`);
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) historyTwinMain().catch((e) => {
  // One plain '[twin] ERROR:' line first: the workflow's reports keep '[twin]' lines, so a failure's reason reaches the commit comment.
  console.error(`[twin] ERROR: ${String(e?.message ?? e).split('\n')[0].slice(0, 400)}`);
  console.error(e);
  process.exit(1);
});
