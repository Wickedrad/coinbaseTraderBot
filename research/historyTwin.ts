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
//   ... --stage match --real data/twin-real15m --twin data/replay-src --days C,D [--warm-days E] [--jobs N] --out data/twin   (--jobs: N days at once in child processes, the same files and lines)
//   ... --stage fill --src data/twin/requote --dst data/twin/depth --how depth --depth-model data/models/depth_model.json --split-file data/twin/split.json
//   ... --stage features --dirs real=data/twin/real,requote=data/twin/requote,depth=data/twin/depth --days C,D [--jobs N] --out data/twin   (--jobs: N (source, day) passes at once)
//   ... --stage unit --unit-file DIR/uN.in.json   (internal: one unit of match or features for a --jobs child process, answered in uN.out.json; never run by hand)
//   ... --stage backtest --dir data/twin/real --name real [--latency-ms 250] --days ... --out data/twin
//   ... --stage verdict --out data/twin [--confirm-look 2 --confirm-look-note "text"]   (reads features-*.json, windows-*.json, split.json; the note is required on the confirm days)
//   ... --stage sweep --fit-days A,B,C --twin-requote data/replay-src --real data/twin-real15m --depth-model data/models/depth_model.json --gen 0 --shard 0/7 --candidates 10 [--parents elite.json] --out data/sweep
//   ... --stage sweep-collect --dir DIR --gen 0 --shards 7 --candidates 10 --out OUT [--partial]   (merges the shards: best.json, elite.json, results.json)
//   ... --stage fill ... [--depth-params best.json]   (a sweep's best candidate: the fill-in then logs every parameter it used)
//   ... --stage fastrows --real data/twin-real15m --twin data/replay-src --days C,D --depth-model data/models/depth_model.json [--depth-params best.json] [--real-cache DIR --real-run RUN] --out data/twin
//   ... --stage depth-model-check --depth-model FILE --split-file data/twin/split.json [--run RUN] [--model-meta real-meta.json]   (a depth model an earlier run fitted: reusable or not)
//
// THE SWEEP (Nov 22). The depth simulator's dynamic constants (research/history/depthSim.ts DepthSimParams) are set by a machine
// optimizer instead of by hand: each candidate is the fill-in with one set of parameters, judged by the SAME judge on the FIT days
// only (the real FIT rows from the cached restricted real days, the twin FIT rows built in-stream: the fill-in's records go straight
// into the features code, no filled day is written). Loss = the leave-one-day-out adversary AUC over all 13 features (lower is
// better); each feature's own AUC and each regime's AUC come with it. Generation 0 is the defaults plus a Latin hypercube of
// DEPTH_PARAM_SPACE, later generations a cross-entropy step around the best 20 percent of the parents (research/history/
// depthParamSearch.ts; seeded, no clock). The sweep reads FIT days only (resolveSweepFit refuses anything but the dev split's FIT
// days, a DEV day or a CONFIRM day); the DEV verdict of the best candidate is read by a normal split=dev dispatch with
// depth_params_run, and the winning numbers become the new defaults only through a reviewed code change.
//
// THE FAST DEV RUN (Nov 22; workflow input fast, RUNBOOK 3.2.1). An iteration of the optimizer is one dev run, so its wall time is the
// loop's limit; the full route took 4 h 16 min (writes each filled day as gzip, reads it back, parses each real day four times and the
// fit days once more). `--stage fastrows` builds the same files without those: the requote rows, the depth rows in-stream (the fill-in's
// records go straight into the features code), the real rows and the paired mechanics in one pass over each real day, or, from a real
// side an earlier run kept (real_features_run), from its files, refused unless they were built for exactly these days, prepped real
// days, requote days and FEATURE_CODE_VERSION. A depth model an earlier run fitted is reused (depth_model_run) only when it records
// exactly the fit days and this version of the study (DEPTH_MODEL_SCHEMA). The confirm route stays the audited full one: a fast run
// is refused on a split that reads a confirm day. The rows, paired.json and the printed lines are the full route's, number for number.
//
// Prints counts, cents, $ and AUCs only (the repository is public).

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { performance } from 'perf_hooks';
import zlib from 'zlib';
import { OrderBook } from '../bot/marketdata/orderBook';
import { recordingFiles, recordingLines } from '../bot/marketdata/recordingFiles';
import { gbdtLogit } from '../bot/model/trees';
import { trainGbdt } from './gbdt';
import { assetOfTicker, DEPTH_ASSETS, readDepthModel, resolveDepthSimParams, validateDepthModel, type CalibrationCode, type DepthCalibration, type DepthModel, type DepthSimParams } from './history/depthSim';
import { REPLAY_VERSION } from './history/historyReplay';
import { runUnits, serveUnit } from './history/unitPool';
import { DEPTH_MODEL_SCHEMA } from './history/depthModelVersion';
import { calibrateDepthModel, CAL_HELD_IN_BUDGET_S, gapsOfAsset, heldInCheck, type CalRow } from './history/depthCalibrate';
import {
  describeParams, eliteOf, ELITE_FRACTION, generationCandidates, mergeShards, parentsFrom, parseShard, rankResults, shardRange, SWEEP_VERSION, type SweepResult, type SweepShardFile,
} from './history/depthParamSearch';
import type { DepthPicks, Ev } from './goLiveTally';

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
  const parsed = JSON.parse(fs.readFileSync(modelFile, 'utf8'));
  // The per-asset blocks and their stress rows come out of the same fit as the pooled tables, so `days` covers them; a file whose blocks
  // the simulator could not read as they were meant (a schema it does not know, stress rows without edges) is refused here, before any day is played.
  validateDepthModel(parsed);
  const days: unknown = parsed.days;
  if (!Array.isArray(days) || !days.length) throw new Error(`${modelFile} does not record the days it was fitted on`);
  assertDisjoint(days as string[], split.judge);
  const stray = (days as string[]).filter((d) => !split.fit.includes(d));
  if (stray.length) throw new Error(`the depth model was fitted on days outside the fit set: ${stray.join(', ')}`);
  // The per-asset calibration (schema 3) is fitted from the same days: a block that names other days was not made from this model's fit.
  const cal = parsed.calibration;
  if (cal !== undefined) {
    const cd = [...cal.fitDays].sort(), md = [...(days as string[])].sort();
    if (cd.join(',') !== md.join(',')) throw new Error(`the depth model's calibration was fitted on ${cd.join(', ')}, not on the days the model was fitted on (${md.join(', ')})`);
  }
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

/** One line of a real day as the restricted day keeps it ('\n' ended), or undefined when the line is dropped: a line naming a
 *  ticker outside `keep` goes; a line listing several tickers keeps only the kept ones (and goes when none is left). The
 *  ticker is read straight off the line (no parse): only the rare lines listing several tickers are parsed. */
const TICKER_RE = /"ticker":"([^"]+)"/;
export function restrictLine(line: string, keep: ReadonlySet<string>): string | undefined {
  const m = TICKER_RE.exec(line);
  if (m && !keep.has(m[1])) return undefined;
  if (line.includes('"tickers"')) {
    let e: Record<string, any>;
    try { e = JSON.parse(line); } catch { return undefined; }
    if (e.ticker && !keep.has(e.ticker)) return undefined;
    if (Array.isArray(e.tickers)) { e.tickers = e.tickers.filter((t: string) => keep.has(t)); if (!e.tickers.length) return undefined; return JSON.stringify(e) + '\n'; }
  }
  return line + '\n';
}

/** The real day with every contract the twin lacks taken out (its market, book, delta, trade, result records; alive
 *  marks keep only the twin's tickers). */
async function restrictDay(src: string, dst: string, keep: Set<string>): Promise<void> {
  async function* lines(): AsyncGenerator<string> {
    for await (const line of recordingLines(src)) {
      if (!line) continue;
      const r = restrictLine(line, keep);
      if (r !== undefined) yield r;
    }
  }
  await writeGz(dst, lines());
}

/** What the real side of the paired mechanics reads off a (restricted) real day: the book's mid and spread at each minute mark
 *  per contract, the index at each 15 s slot per asset, and the results. Fed record by record (`push`), so the file route
 *  (pairDay, a pass over the restricted file) and the fast route (one pass over the real day that also builds the rows)
 *  go through the same code. `want`: only these tickers' books are kept (the contracts both sides have). */
interface PairSide { push: (e: Record<string, any>) => void; q: Map<string, { mid: number; spread: number }>; ix: Map<string, number>; res: Map<string, string> }
function pairSide(want?: ReadonlySet<string>): PairSide {
  const q = new Map<string, { mid: number; spread: number }>(), ix = new Map<string, number>(), res = new Map<string, string>();
  const books = new Map<string, OrderBook>(), lastIx = new Map<string, number>();
  let mark = -1;
  const reach = (t: number) => {
    const s = Math.floor(t / SLOT);
    if (mark < 0) { mark = s; return; }
    for (; mark < s; mark++) {
      const at = (mark + 1) * SLOT;
      for (const [a, v] of lastIx) ix.set(`${a}|${at}`, v);
      if (at % MIN === 0) for (const [tk, b] of books) {
        const bb = b.bestBid()?.price, ba = b.bestAsk()?.price;
        if (bb !== undefined && ba !== undefined && ba > bb) q.set(`${tk}|${at}`, { mid: (bb + ba) / 2, spread: ba - bb });
      }
    }
  };
  const push = (e: Record<string, any>): void => {
    reach(e.t);
    if (e.k === 'book' && (!want || want.has(e.ticker))) { const b = books.get(e.ticker) ?? new OrderBook(e.ticker); books.set(e.ticker, b); b.applySnapshot({ bids: e.bids ?? [], asks: e.asks ?? [] }, e.t); }
    else if (e.k === 'delta' && (!want || want.has(e.ticker))) { const b = books.get(e.ticker) ?? new OrderBook(e.ticker); books.set(e.ticker, b); b.applyDelta(e.side, e.price, e.delta, e.t); }
    else if (e.k === 'index' && e.asset && e.value > 0) lastIx.set(e.asset, e.value);
    else if (e.k === 'result' && e.ticker && e.result) res.set(e.ticker, String(e.result));
  };
  return { push, q, ix, res };
}

/** The twin's side of the paired mechanics, against what the real side read: the twin's minute quote against the real
 *  book's mid, the twin's index against the real index, the results. */
async function pairFinish(day: string, real: PairSide, realT: Map<string, string>, twinFile: string, twinT: Map<string, string>): Promise<Paired> {
  const both = [...twinT.keys()].filter((t) => realT.has(t));
  const bothSet = new Set(both);
  const realQ = real.q, realIx = real.ix, realRes = real.res;
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

/** Per contract both ways at each minute mark: the twin's candle quote against the real book there; per asset the
 *  index at each 15 s print; the results. */
async function pairDay(day: string, realFile: string, twinFile: string, realT: Map<string, string>, twinT: Map<string, string>): Promise<Paired> {
  const bothSet = new Set([...twinT.keys()].filter((t) => realT.has(t)));
  const side = pairSide(bothSet);
  for await (const e of events(realFile)) side.push(e);
  return pairFinish(day, side, realT, twinFile, twinT);
}

/** The per-day line the match stage prints (dev and custom only), also printed from a cached paired.json by the fast route. */
export const matchLine = (day: string, p: Paired): string => `[twin] ${day}: contracts real ${p.realContracts} / twin ${p.twinContracts} / both ${p.both} (real 15m missing from the twin ${p.onlyReal15m}, twin-only ${p.onlyTwin}); minute quote vs real mid: ${p.quoteN} pts, off ${p.quoteMaeC.toFixed(2)}c (bias ${p.quoteBiasC.toFixed(2)}c), spread real ${p.spreadRealC.toFixed(2)}c twin ${p.spreadTwinC.toFixed(2)}c; index ${p.indexN} pts off ${p.indexMaeBps.toFixed(1)} bps (bias ${p.indexBiasBps.toFixed(1)}); results agree ${p.resultsAgree}/${p.results}`;

// Round S1 (RUNBOOK 3.2 and 5): the match, fill and features steps took 290+ minutes serially on a 4-vCPU runner (P2 was cancelled at the job's 340-minute limit). The
// day passes of match and features are independent, so `--jobs N` runs them in N child processes (research/history/unitPool.ts); every global thing (the checks, the order of the
// files and lines, paired.json, the follow diagnostics) stays in the parent, and the files and every printed line except the timing lines are those of the serial route (a test
// holds them byte for byte). `--jobs 1` (the default) is the serial route: the same function, called in this process, one day after the other.

/** `--jobs N`: how many child processes the match and features stages may use (default 1: no child, today's route). */
export function jobsArg(): number {
  const raw = arg('jobs', '1');
  if (!/^\d+$/.test(raw) || +raw < 1 || +raw > 64) throw new Error(`--jobs must be a whole number from 1 to 64 (got "${raw.slice(0, 20)}")`);
  return +raw;
}
/** Seconds as the timing lines print them (one decimal). */
const fmtSecs = (ms: number): string => (ms / 1000).toFixed(1);
/** This file: the script a child process runs (`--stage unit`). */
const SELF = fileURLToPath(import.meta.url);
const prevDayOf = (day: string) => new Date(Date.parse(`${day}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10);

export interface MatchMs { tickers: number; restrict: number; pair: number }
/** What one day of the match stage gives back: the day's Paired and the milliseconds of its three parts, or `left` (which of the two files the day lacks). */
export interface MatchUnitResult { day: string; left?: { real: boolean; twin: boolean }; paired?: Paired; ms?: MatchMs }
export const matchTimingLine = (day: string, ms: MatchMs): string => `[twin] match ${day}: tickers ${fmtSecs(ms.tickers)} s, restrict ${fmtSecs(ms.restrict)} s, pair ${fmtSecs(ms.pair)} s`;

/** One day of the match stage, exactly as the loop did it: the day's real and twin files, the tickers of the real day, of the twin day and of the day before it, the real
 *  day restricted to those into out/real, the twin day copied to out/requote, the paired mechanics on the restricted day. In this process (jobs 1) or in a child. Nothing
 *  here reads any day but this one and the day before it in the twin folder (as before). The clock is read only for the timing line. */
export async function matchUnit(o: { realDir: string; twinDir: string; out: string; day: string }): Promise<MatchUnitResult> {
  const { realDir, twinDir, out, day } = o;
  const rf = dayFile(realDir, day), tf = dayFile(twinDir, day);
  if (!rf || !tf) return { day, left: { real: !!rf, twin: !!tf } };
  const ms: MatchMs = { tickers: 0, restrict: 0, pair: 0 };
  let t = performance.now();
  const realT = await tickersOf(rf), twinT = await tickersOf(tf);
  // Contracts open at midnight are listed the day before: keep every twin ticker of this day and the day before.
  const keep = new Set(twinT.keys());
  const prev = dayFile(twinDir, prevDayOf(day));
  if (prev) for (const tk of (await tickersOf(prev)).keys()) keep.add(tk);
  ms.tickers = performance.now() - t; t = performance.now();
  await restrictDay(rf, path.join(out, 'real', `md-${day}.jsonl.gz`), keep);
  fs.copyFileSync(tf, path.join(out, 'requote', path.basename(tf)));
  ms.restrict = performance.now() - t; t = performance.now();
  // Paired on the restricted day (the twin's contracts only): the same records for those contracts, far fewer lines.
  const paired = await pairDay(day, path.join(out, 'real', `md-${day}.jsonl.gz`), tf, realT, twinT);
  ms.pair = performance.now() - t;
  return { day, paired, ms };
}

async function stageMatch(): Promise<void> {
  const realDir = arg('real', 'data/recordings'), twinDir = arg('twin', 'data/history-replay'), out = arg('out', 'data/twin');
  const days = arg('days').split(',').filter(Boolean);
  // Warm-up days (the day before a judged day, for the backtests' sake) are matched too but never judged.
  const warm = arg('warm-days').split(',').filter((d) => d && !days.includes(d));
  const jobs = jobsArg();
  const split = readSplit(splitFile(out));
  if (split) { assertDisjoint(split.fit, days); assertHeldOut(split, [...days, ...warm]); }
  // Blind whenever a confirm day is read, whatever the split is called (and with no split on record at all).
  const quiet = isBlind(split, [...days, ...warm]);
  fs.mkdirSync(path.join(out, 'real'), { recursive: true });
  fs.mkdirSync(path.join(out, 'requote'), { recursive: true });
  const t0 = performance.now();
  const order = [...warm, ...days];
  const paired: Paired[] = [];
  const left: string[] = [];
  // A day's own lines, in the order of `order` whichever route produced the day (the timing line is printed when the day is done).
  const emit = (day: string, r: MatchUnitResult) => {
    if (r.left) { console.log(`[twin] ${day}: ${r.left.real ? '' : 'no real recording '}${r.left.twin ? '' : 'no history twin'}; left out`); left.push(day); return; }
    paired.push(r.paired!);
    if (!quiet) console.log(matchLine(day, r.paired!));
  };
  const unitOf = (day: string) => ({ realDir, twinDir, out, day });
  // the days with both files are the units a child may take; a day without them is left out here (a lookup, no child)
  const work = [...new Set(order)].filter((d) => dayFile(realDir, d) && dayFile(twinDir, d));
  const used = Math.min(jobs, work.length);
  if (used > 1) {
    const done = new Map<string, MatchUnitResult>();
    for (const d of new Set(order)) if (!work.includes(d)) done.set(d, await matchUnit(unitOf(d)));
    let cursor = 0;
    const flush = () => { for (; cursor < order.length && done.has(order[cursor]); cursor++) emit(order[cursor], done.get(order[cursor])!); };
    flush();
    await runUnits<MatchUnitResult>(work.map((d) => ({ id: d, spec: { kind: 'match', ...unitOf(d) } })), {
      script: SELF, dir: out, label: 'match', jobs: used,
      onResult: (_i, r) => { done.set(r.day, r); console.log(matchTimingLine(r.day, r.ms!)); flush(); },
    });
    flush();
  } else {
    for (const day of order) {
      const r = await matchUnit(unitOf(day));
      if (r.ms) console.log(matchTimingLine(day, r.ms));
      emit(day, r);
    }
  }
  // A confirm split reads no mechanics per day (nothing there to tune on): counts only.
  if (quiet) { const j = paired.filter((p) => days.includes(p.day)); console.log(`[twin] matched ${j.length} of ${days.length} judged day(s): ${j.reduce((a, p) => a + p.both, 0)} contracts in both, ${j.reduce((a, p) => a + p.onlyReal15m, 0)} real 15m missing from the twin, ${j.reduce((a, p) => a + p.onlyTwin, 0)} twin-only; results agree ${j.reduce((a, p) => a + p.resultsAgree, 0)}/${j.reduce((a, p) => a + p.results, 0)}`); }
  fs.writeFileSync(path.join(out, 'paired.json'), JSON.stringify(paired, null, 1));
  console.log(`[twin] match took ${fmtSecs(performance.now() - t0)} s (jobs ${Math.max(1, used)})`);
  // With a split on record every judged day must be there: a verdict on fewer days than asked is not the verdict asked for.
  const lost = left.filter((d) => days.includes(d));
  if (split && lost.length) throw new Error(`judged day(s) without a real recording or a twin: ${lost.join(', ')}`);
}

// ---------------------------------------------------------------------------------------------------------------
// Stage features: one row per contract life, what the bot sees, sampled at the 15 s prints both sources share.

export const FEATURES = ['spreadC', 'topSize', 'depth10', 'quotedShare', 'quoteChangesPerMin', 'midMoveSd', 'minuteJumpShare', 'followIx', 'followIxLag', 'tradesPerMin', 'tradeSize', 'ixMoveBps', 'brierT5'] as const;
/** The version of the code that turns a real day into contract-life rows and paired mechanics: MIN, SLOT, logit, is15m, corr,
 *  rowBuilder (and the OrderBook it reads), FEATURES, and the paired mechanics (tickersOf, restrictLine, pairSide, pairFinish). A
 *  real side cached by an earlier run (the fast route's real_features_run) is reused only when it was made by this version. Bump it
 *  in the same commit as any change to that code: tests/historyTwin.test.ts holds the hash of that source text per version, so a
 *  change that is not followed by a bump fails there. */
export const FEATURE_CODE_VERSION = 'f1';
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

/** One day's contract lives, built a record at a time (`push`), rows on `finish`. The file route (dayRows) and the in-stream route
 *  (filledDayRows: the fill-in's records straight in, no file) both go through it, so they cannot drift apart. `keep`: only these
 *  tickers. `diag` false: the follow diagnostics (global, printed by the features stage) are not fed: a sweep builds thousands of days. */
export interface RowBuilder { push: (e: Record<string, any>) => void; finish: () => Row[] }

export function rowBuilder(day: string, src: string, results: ReadonlyMap<string, string>, keep?: ReadonlySet<string>, diag = true): RowBuilder {
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
  const push = (e: Record<string, any>): void => {
    reach(e.t);
    if (e.k === 'market' && e.ticker && is15m(e.series, e.ticker) && (!keep || keep.has(e.ticker))) {
      if (!lives.has(e.ticker)) lives.set(e.ticker, { ticker: e.ticker, asset: e.asset, open: e.openTime, close: e.closeTime, book: new OrderBook(e.ticker), changes: 0, lastTop: '', slots: [], trades: 0, size: 0 });
    } else if (e.k === 'book' && lives.has(e.ticker)) { const l = lives.get(e.ticker)!; l.book.applySnapshot({ bids: e.bids ?? [], asks: e.asks ?? [] }, e.t); touch(l); }
    else if (e.k === 'delta' && lives.has(e.ticker)) { const l = lives.get(e.ticker)!; l.book.applyDelta(e.side, e.price, e.delta, e.t); touch(l); }
    else if (e.k === 'trade' && lives.has(e.ticker)) { const l = lives.get(e.ticker)!; l.trades++; l.size += e.count ?? 0; }
    else if (e.k === 'index' && e.asset && e.value > 0) ix.set(e.asset, e.value);
  };
  const finish = (): Row[] => {
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
        if (diag) { const g = (followDiag[src] ??= {}); const k = `${a.mid < 0.1 || a.mid > 0.9 ? 'tails' : 'middle'}${b.t % MIN === 0 ? ' at minute' : ''}`; (g[k] ??= { m: [], x: [] }).m.push(m); g[k].x.push(x); }
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
  };
  return { push, finish };
}

export async function dayRows(file: string, day: string, src: string, results: ReadonlyMap<string, string>, keep?: ReadonlySet<string>, diag = true): Promise<Row[]> {
  const b = rowBuilder(day, src, results, keep, diag);
  for await (const e of events(file)) b.push(e);
  return b.finish();
}

async function resultsOf(dir: string, days: string[]): Promise<Map<string, string>> {
  const r = new Map<string, string>();
  for (const d of days) { const f = dayFile(dir, d); if (f) for await (const line of recordingLines(f)) { if (!line || !line.includes('"k":"result"')) continue; try { const e = JSON.parse(line); if (e.ticker && e.result) r.set(e.ticker, String(e.result)); } catch { /* a cut line */ } } }
  return r;
}

// The per-day activity of a source's rows and the follow diagnostics, as lines. The numbers are built once (activityOf) and printed
// by one function (activityLines), so the real side of an earlier run (the fast route's real-activity.json, the same numbers the
// lines print) prints exactly as the features stage does.

/** The columns of the per-day activity line (feature names; the means are over the day's lives, topSize, depth10 and tradeSize log1p). */
const ACT_KEYS = ['tradesPerMin', 'tradeSize', 'topSize', 'depth10', 'quoteChangesPerMin', 'followIx', 'spreadC'] as const;
export interface FollowStat { key: string; moves: number; corr: number; sd: number; zeroPct: number }
/** `means`: the ACT_KEYS means, already rounded to the 2 places the line prints (a NaN mean prints 'NaN'). */
export interface DayActivity { label: string; lives: number; means: string[] }
export interface Activity { follow: FollowStat[]; days: DayActivity[] }

const perDayOf = (rows: readonly Row[]): Map<string, Row[]> => { const m = new Map<string, Row[]>(); for (const r of rows) m.set(r.day, [...(m.get(r.day) ?? []), r]); return m; };

/** Follow diagnostics of `src` (so far: followDiag) and the per-day means of `perDay`. */
function activityOf(src: string, perDay: ReadonlyMap<string, readonly Row[]>): Activity {
  const fi = (k: string) => FEATURES.indexOf(k as (typeof FEATURES)[number]);
  const sdv = (xs: number[]) => { const mu = xs.reduce((a, b) => a + b, 0) / Math.max(1, xs.length); return Math.sqrt(xs.reduce((a, b) => a + (b - mu) ** 2, 0) / Math.max(1, xs.length)); };
  const follow = Object.entries(followDiag[src] ?? {}).map(([key, g]) => ({ key, moves: g.m.length, corr: corr(g.m, g.x), sd: sdv(g.m), zeroPct: (g.m.filter((v) => v === 0).length / Math.max(1, g.m.length)) * 100 }));
  const days = [...perDay].map(([label, rs]) => ({ label, lives: rs.length, means: ACT_KEYS.map((k) => (rs.length ? rs.reduce((a, r) => a + (Number.isFinite(r.f[fi(k)]) ? r.f[fi(k)] : 0), 0) / rs.length : NaN).toFixed(2)) }));
  return { follow, days };
}

/** The lines the features stage prints for one source's activity (dev and custom only; the confirm split prints none). */
export function activityLines(src: string, a: Activity): string[] {
  return [
    ...a.follow.map((f) => `[twin] ${src} follow ${f.key}: ${f.moves} moves, corr ${f.corr.toFixed(3)}, mid move sd ${f.sd.toFixed(3)}, zero moves ${f.zeroPct.toFixed(0)}%`),
    ...a.days.map((d) => `[twin] ${src} ${d.label}: ${d.lives} lives, trades/min ${d.means[0]}, tradeSize ${d.means[1]}, topSize ${d.means[2]}, depth10 ${d.means[3]}, quote changes/min ${d.means[4]}, followIx ${d.means[5]}, spread ${d.means[6]}c`),
  ];
}

// The real side of a run, kept beside its judged features (twinlite/) so a later fast run can reuse it instead of parsing the real
// days again: real-meta.json (what it was built for: the cache key), real-activity.json (the activity lines of the real judged and
// fit days) and, with features-real.json and paired.json, everything the real side contributes to the verdict. Written by a run that
// reads no confirm day (a blind run keeps no per-day numbers), in the full route's features stage and in the fast route.

/** The format of real-meta.json and real-activity.json. */
export const REAL_SIDE_VERSION = 1;
export interface RealMeta {
  version: number;
  /** The judged days, in order (the rows and paired.json cover exactly these), and the fit days whose activity lines are kept. */
  judged: string[]; fit: string[];
  /** The real days' cache tag (real15mTag: the prep's keep rules and the REPLAY_EXCLUDE pattern) and the feature code's version. */
  real15m: string; featureCode: string;
  /** Per day: the sha256 of the prepped real day (its meta.json) and, for a judged day, of the requote day the real contracts were
   *  restricted to and the pairs were made against (its ticker list decides which real contracts are rows). '' = not known. */
  days: Record<string, { real: string; twin?: string }>;
  /** Informational: the run this was copied from when the real side was reused. Not part of the key. */
  reusedFrom?: string;
}

const sha256Text = (s: string | Buffer) => crypto.createHash('sha256').update(s).digest('hex');
/** The sha256 a prepped real day's meta.json records ('' when the file or the field is not there). */
function realDaySha(real15mDir: string, day: string): string {
  try { const m = JSON.parse(fs.readFileSync(path.join(real15mDir, `meta-${day}.json`), 'utf8')) as Partial<Real15mMeta>; return typeof m.sha256 === 'string' ? m.sha256 : ''; } catch { return ''; }
}

/** The key of the real side as this run sees it. */
export async function realMetaFor(o: { judged: readonly string[]; fit: readonly string[]; real15mDir: string; twinDir: string }): Promise<RealMeta> {
  const days: RealMeta['days'] = {};
  for (const d of o.fit) days[d] = { real: realDaySha(o.real15mDir, d) };
  for (const d of o.judged) { const f = dayFile(o.twinDir, d); days[d] = { real: realDaySha(o.real15mDir, d), twin: f ? await sha256File(f) : '' }; }
  return { version: REAL_SIDE_VERSION, judged: [...o.judged], fit: [...o.fit], real15m: real15mTag(), featureCode: FEATURE_CODE_VERSION, days };
}

/** What differs between the key a cached real side was built for and the key of this run (empty: it can be reused): each aspect with
 *  what the cached side had and what this run has. A sha that is not known on either side never matches. */
export function realMetaDiff(had: RealMeta, now: RealMeta): Array<{ aspect: string; had: string; now: string }> {
  const out: Array<{ aspect: string; had: string; now: string }> = [];
  if (had.version !== now.version) out.push({ aspect: 'sidecar format', had: `real-meta.json format ${had.version}`, now: `format ${now.version}` });
  if (had.judged.join(',') !== now.judged.join(',')) out.push({ aspect: 'judged days', had: `judged days ${had.judged.join(',')}`, now: `judged days ${now.judged.join(',')}` });
  if (had.fit.join(',') !== now.fit.join(',')) out.push({ aspect: 'fit days', had: `fit days ${had.fit.join(',')}`, now: `fit days ${now.fit.join(',')}` });
  if (had.real15m !== now.real15m) out.push({ aspect: 'real days tag', had: `real days tag ${had.real15m}`, now: `real days tag ${now.real15m}` });
  if (had.featureCode !== now.featureCode) out.push({ aspect: 'feature code', had: `feature code ${had.featureCode}`, now: `feature code ${now.featureCode}` });
  const sha = (a: string | undefined, b: string | undefined) => !!a && a === b;
  const badReal = [...new Set([...now.fit, ...now.judged])].filter((d) => !sha(had.days?.[d]?.real, now.days[d]?.real));
  if (badReal.length) out.push({ aspect: 'prepped real days', had: `prepped real day(s) ${badReal.join(',')} as they were then`, now: 'those days as they are now (sha256 differs or is not recorded)' });
  const badTwin = now.judged.filter((d) => !sha(had.days?.[d]?.twin, now.days[d]?.twin));
  if (badTwin.length) out.push({ aspect: 'requote days', had: `requote day(s) ${badTwin.join(',')} as they were then`, now: 'those days as they are now (sha256 differs or is not recorded)' });
  return out;
}

/** The real FIT days' rows (round R2): what the per-asset calibration (research/history/depthCalibrate.ts) fits the twin to. One file beside the judged
 *  real side, under the same real-meta.json key (its `fit` days and their prepped days' sha256): every real contract of each FIT day, built by the
 *  same rowBuilder as the activity lines' fit-day rows, with no result labels (brierT5 is NaN there: a FIT row is a pure function of its day). */
export const REAL_FIT_FILE = 'real-fit-features.json';
/** The handoff of the calibration stage to the stages after it (a folder of the same job, data/calib): the FIT rows and the follow diagnostics those
 *  days feed, under a key of the FIT days and their prepped days' sha256, so a later stage that needs the same rows does not parse the days again.
 *  Never trusted past its key: a stage that finds a key that is not exactly its own parses the days itself. */
export const REAL_FIT_FOLLOW_FILE = 'real-fit-follow.json';

/** The sidecars of the real side, next to features-real.json. `fitText`: the real FIT rows (REAL_FIT_FILE) as JSON text. */
function writeRealSidecars(out: string, meta: RealMeta, activity: Activity, fitText: string): void {
  fs.writeFileSync(path.join(out, 'real-meta.json'), JSON.stringify(meta, null, 1));
  fs.writeFileSync(path.join(out, 'real-activity.json'), JSON.stringify({ version: REAL_SIDE_VERSION, ...activity }, null, 1));
  fs.writeFileSync(path.join(out, REAL_FIT_FILE), fitText);
}

type FollowArrays = Record<string, { m: number[]; x: number[] }>;
export interface RealFitKey { fit: string[]; real15m: string; featureCode: string; shas: Record<string, string> }
export const realFitKey = (fit: readonly string[], real15mDir: string): RealFitKey => ({ fit: [...fit], real15m: real15mTag(), featureCode: FEATURE_CODE_VERSION, shas: Object.fromEntries(fit.map((d) => [d, realDaySha(real15mDir, d)])) });
/** Appends follow diagnostics (the m and x of each key) to `followDiag[src]`, in order (a loop: a day's arrays are too long to spread). */
function mergeFollow(src: string, add: FollowArrays): void {
  const g = (followDiag[src] ??= {});
  for (const [k, v] of Object.entries(add)) { const t = (g[k] ??= { m: [], x: [] }); for (const a of v.m) t.m.push(a); for (const a of v.x) t.x.push(a); }
}
export interface RealFit { rows: Row[]; perDay: Map<string, Row[]>; follow: FollowArrays; reused: boolean }
/** Rows read back from JSON: a feature that was NaN when the row was built (a FIT row has no result label, so its brierT5 is) is written as null; it is NaN again here,
 *  so a row read from a kept file is the row the parse gives. */
const reviveRows = (rows: Row[]): Row[] => rows.map((r) => (r.f.some((v) => v === null) ? { ...r, f: r.f.map((v) => (v === null ? NaN : v)) } : r));

/** The real FIT days' rows: from the handoff folder when it holds exactly these days' rows under the key of THIS run (`fit` and their prepped days'
 *  sha256, the real days tag and the feature code), else parsed from the cached real days in `realDir` (every contract of the day, no labels). Either
 *  way the follow diagnostics those days feed are appended to `followDiag.real`, after what is there (the judged days'), as parsing them one after the
 *  other always did. `skipMissing`: a day with no cached file is left out (the features stage always did) instead of refused (the fast run did, and the calibration, which
 *  says so in `needs`). */
export async function realFitRows(o: { fit: readonly string[]; realDir: string; handoff?: string; skipMissing?: boolean; needs?: string }): Promise<RealFit> {
  const key = realFitKey(o.fit, o.realDir);
  if (o.handoff && key.fit.length && Object.values(key.shas).every(Boolean)) {
    try {
      const fol = JSON.parse(fs.readFileSync(path.join(o.handoff, REAL_FIT_FOLLOW_FILE), 'utf8')), raw = JSON.parse(fs.readFileSync(path.join(o.handoff, REAL_FIT_FILE), 'utf8')) as Row[], rows = Array.isArray(raw) ? reviveRows(raw) : raw;
      const counts: Record<string, number> = {}; for (const r of rows) counts[r.day] = (counts[r.day] ?? 0) + 1;
      if (fol?.version === REAL_SIDE_VERSION && JSON.stringify(fol.key) === JSON.stringify(key) && typeof fol.follow === 'object' && fol.follow !== null && Array.isArray(rows) && JSON.stringify(fol.rowsPerDay) === JSON.stringify(Object.fromEntries(key.fit.map((d) => [d, counts[d] ?? 0]))) && Object.keys(counts).every((d) => key.fit.includes(d))) {
        const perDay = new Map<string, Row[]>(); for (const d of key.fit) perDay.set(d, rows.filter((r) => r.day === d));
        mergeFollow('real', fol.follow);
        return { rows, perDay, follow: fol.follow, reused: true };
      }
    } catch { /* not a usable handoff: the days are parsed */ }
  }
  const perDay = new Map<string, Row[]>(), saved = followDiag.real;
  delete followDiag.real;
  let follow: FollowArrays = {};
  try {
    for (const d of o.fit) {
      const f = dayFile(o.realDir, d);
      if (!f) { if (o.skipMissing) continue; throw new Error(`${o.needs ?? 'the fast run'} needs the cached real FIT day ${d} in ${o.realDir}${o.needs ? '' : ' (its activity line)'}; dispatch prep_days=${d} first`); }
      perDay.set(d, await dayRows(f, d, 'real', new Map()));
    }
  } finally { follow = followDiag.real ?? {}; if (saved) followDiag.real = saved; else delete followDiag.real; }
  mergeFollow('real', follow);
  return { rows: [...perDay.values()].flat(), perDay, follow, reused: false };
}

export const featuresTimingLine = (src: string, day: string, ms: number): string => `[twin] features ${src} ${day}: ${fmtSecs(ms)} s`;
/** What one (source, day) pass of the features stage gives back from a child: the day's rows, the follow diagnostics (the module global followDiag) that pass fed, its milliseconds. */
export interface FeaturesUnitResult { rows: Row[]; follow: Record<string, { m: number[]; x: number[] }>; ms: number }
/** One (source, day) pass in a child process: the rows `dayRows` builds from the day's file, and what it added to `followDiag[src]` (the child's global starts empty, so that is all of it). */
export async function featuresUnit(o: { src: string; file: string; day: string; results: Array<[string, string]> }): Promise<FeaturesUnitResult> {
  const t = performance.now();
  const rows = await dayRows(o.file, o.day, o.src, new Map(o.results));
  return { rows, follow: followDiag[o.src] ?? {}, ms: performance.now() - t };
}

/** The hidden stage the pool's children run (research/history/unitPool.ts): one unit of the match or features stage, answered through a file. */
async function stageUnit(): Promise<void> {
  await serveUnit(async (spec) => {
    if (spec?.kind === 'match') return matchUnit(spec);
    if (spec?.kind === 'features') return featuresUnit(spec);
    throw new Error(`unknown unit kind "${String(spec?.kind).slice(0, 40)}"`);
  });
}

async function stageFeatures(): Promise<void> {
  const out = arg('out', 'data/twin');
  const days = arg('days').split(',').filter(Boolean);
  const jobs = jobsArg();
  const split = readSplit(splitFile(out));
  if (split) { assertDisjoint(split.fit, days); assertHeldOut(split, days); }
  // A confirm split (or any run that reads a confirm day) prints no per-day activity or follow tables (the optimizer must
  // not tune on those rows).
  const quiet = isBlind(split, days);
  const dirs = Object.fromEntries(arg('dirs').split(',').filter(Boolean).map((kv) => kv.split('=') as [string, string]));
  // Labels from Kalshi's own results (the twin carries them for every contract), the same for both sides.
  const results = await resultsOf(dirs.requote ?? Object.values(dirs)[0], days);
  const t0 = performance.now();
  // The (source, day) passes are independent: with --jobs N they run N at a time in child processes, and their rows and follow diagnostics are merged below in the order the serial loop
  // would have made them (source, then day), so the files and the printed lines are the serial route's.
  const units: Array<{ src: string; day: string; file: string }> = [];
  for (const [src, dir] of Object.entries(dirs)) for (const d of days) { const file = dayFile(dir, d); if (file) units.push({ src, day: d, file }); }
  const used = Math.min(jobs, units.length);
  const pre = new Map<string, FeaturesUnitResult>();
  if (used > 1) {
    const res = [...results];
    await runUnits<FeaturesUnitResult>(units.map((u) => ({ id: `${u.src} ${u.day}`, spec: { kind: 'features', ...u, results: res } })), {
      script: SELF, dir: out, label: 'features', jobs: used,
      onResult: (i, r) => { pre.set(`${units[i].src}|${units[i].day}`, r); console.log(featuresTimingLine(units[i].src, units[i].day, r.ms)); },
    });
  }
  for (const [src, dir] of Object.entries(dirs)) {
    const rows: Row[] = [];
    for (const d of days) {
      const f = dayFile(dir, d);
      if (!f) continue;
      const r = pre.get(`${src}|${d}`);
      if (r) { rows.push(...reviveRows(r.rows)); if (Object.keys(r.follow).length) mergeFollow(src, r.follow); continue; }
      const t = performance.now();
      rows.push(...(await dayRows(f, d, src, results)));
      console.log(featuresTimingLine(src, d, performance.now() - t));
    }
    fs.writeFileSync(path.join(out, `features-${src}.json`), JSON.stringify(rows));
    console.log(`[twin] features ${src}: ${rows.length} contract lives over ${days.length} day(s)`);
    if (quiet) continue;
    // Per day (and, for the real side, the days around them, not judged: Nov 4, the depth model's fit days traded ~2.6x
    // the compared days a minute), the activity features' means. --extra-dir: where those extra days are (the cached
    // restricted real days, which hold the fit days too).
    const extra = src === 'real' ? arg('extra-days', '').split(',').filter((d) => d && !days.includes(d) && !CONFIRM_DAYS.includes(d)) : [];
    const perDay = perDayOf(rows), extraUsed: string[] = [];
    let fitText = '[]';
    if (extra.length) {
      // the FIT days' rows: the calibration stage's handoff (--handoff) when it holds exactly these days, else parsed here (realFitRows)
      const fr = await realFitRows({ fit: extra, realDir: arg('extra-dir') || dir, handoff: arg('handoff') || undefined, skipMissing: true });
      for (const [d, rs] of fr.perDay) { perDay.set(`${d} (not judged)`, rs); extraUsed.push(d); }
      fitText = JSON.stringify(fr.rows);
    }
    const act = activityOf(src, perDay);
    for (const l of activityLines(src, act)) console.log(l);
    // The real side is kept beside its rows for the fast route (--real15m: the folder of the prepped real days, whose meta files hold their sha256).
    if (src === 'real' && arg('real15m') && dirs.requote) writeRealSidecars(out, await realMetaFor({ judged: days, fit: extraUsed, real15mDir: arg('real15m'), twinDir: dirs.requote }), act, fitText);
  }
  console.log(`[twin] features took ${fmtSecs(performance.now() - t0)} s (jobs ${Math.max(1, used)})`);
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

type LoadedDepthParams = ReturnType<typeof loadDepthParamsFile>;

/** Everything the depth fill-in checks and logs before it starts, for the file route (stageFill) and the fast route (fastRows): the
 *  model must be there, a sweep's parameters (--depth-params) must be a valid best.json, with a split on record the model must
 *  have been fitted on fit days only and the sweep's days must not be judged ones, and the parameters the fill-in will use are
 *  logged. `say` gets each line as it happens. */
async function depthFillSetup(o: { how: string; model: string; splitFile: string; params: string }, say: (line: string) => void): Promise<{ depth: DepthModel | undefined; loaded: LoadedDepthParams | undefined }> {
  const depth = o.model ? readDepthModel(o.model) : undefined;
  if (o.how === 'depth' && !depth) throw new Error('the depth fill-in needs --depth-model');
  // A sweep's best candidate (--depth-params): its parameters go into the fill-in over the defaults and the model's own block.
  const loaded = o.params ? loadDepthParamsFile(o.params) : undefined;
  // With a split on record the model must have been fitted on fit days only.
  if (o.how === 'depth' && o.splitFile) {
    const sp = readSplit(o.splitFile);
    if (!sp) throw new Error(`no split in ${o.splitFile}`);
    assertHeldOut(sp);
    assertModelFitDays(o.model, sp);
    say(`[twin] depth model fitted on fit days only (checked against the split's ${sp.fit.length} fit and ${sp.judge.length} judged day(s))`);
    if (loaded && sp.name === 'confirm') throw new Error('depth_params_run is for dev and custom dispatches: the confirm run uses the code defaults, so promote the sweep\'s params to the defaults through a reviewed code change first');
    // The sweep fitted these params on its FIT days: a split that judges one of them would judge on the days the params were tuned on.
    if (loaded) assertDisjoint(loaded.fitDays, sp.judge);
  }
  if (o.how === 'depth') {
    const { depthModelNote, depthCalibrationNote } = await import('./goLiveTally');
    say(depthModelNote(depth!));
    // The per-asset calibration the model carries (research/history/depthCalibrate.ts), and what a sweep's parameters do to it (depthSim.ts header, layer 4).
    const calNote = depthCalibrationNote(depth!);
    if (calNote) say(calNote);
    if (calNote && loaded) say('[twin] WARNING: the sweep\'s parameters (depth_params_run) name tradeRateMult, tradeSizeMult and levelSizeMult, so for every asset they REPLACE the calibration\'s multipliers for those three knobs; its topSizeMult and flickMult still apply (a sweep is not calibrated: RUNBOOK 4.2)');
    // Every depth fill-in says which parameters it used (the defaults are spelled out too).
    const used = resolveDepthSimParams(depth!.params, loaded?.params);
    const from = loaded ? `sweep best, generation ${loaded.gen}, loss ${loaded.loss}, fitted on FIT days only` : depth!.params ? "the model's own params block" : 'defaults, as in the code';
    say(`[twin] depth simulator parameters (${from}): ${describeParams(used)}`);
  }
  return { depth, loaded };
}

/** The twin's days through the tally's fill-in (research/goLiveTally.ts fillDayFile), as the deep history plays them. */
async function stageFill(): Promise<void> {
  const { fillDayFile, depthSims, picksOf, simulatorLine } = await import('./goLiveTally');
  const src = arg('src'), dst = arg('dst'), how = arg('how', 'depth') as 'depth' | 'worst' | 'hold' | 'requote';
  const { depth, loaded } = await depthFillSetup({ how, model: arg('depth-model'), splitFile: arg('split-file'), params: arg('depth-params') }, (l) => console.log(l));
  fs.mkdirSync(dst, { recursive: true });
  const t0 = performance.now();
  for (const f of fs.readdirSync(src).filter((x) => x.startsWith('md-'))) {
    const t = performance.now();
    await fillDayFile(path.join(src, f), path.join(dst, f), { how }, depth, loaded?.params);
    console.log(`[twin] fill ${f.replace(/^md-/, '').replace(/\.(jsonl\.gz|jsonl|mdc)$/, '')}: ${fmtSecs(performance.now() - t)} s`);
  }
  console.log(`[twin] ${how} fill-in written for ${fs.readdirSync(dst).length} day(s)`);
  console.log(`[twin] fill took ${fmtSecs(performance.now() - t0)} s`);
  if (depthSims.length) console.log(simulatorLine(arg('dst'), depthSims.map((x) => x.stats), depthSims.map(picksOf)));
}

// ---------------------------------------------------------------------------------------------------------------
// In-stream features: the fill-in's records straight into the features code, no filled day on disk.

/** What the fill-in made while a day was built. */
export interface SimActivity { seconds: number; trades: number; sweepPrints: number; flickers: number }

/** One twin day's contract lives, built in-stream: `input` (a requote day's records in time order) goes through the depth fill-in
 *  (research/goLiveTally.ts streamFiller, with `params` over the defaults and the model's own block) and every record it emits goes
 *  into the features code as it comes (rowBuilder), so nothing is written. The rows are exactly those of fillDayFile followed by
 *  dayRows on its file (a test holds it). `events`: how many records the fill-in emitted; `sink` (tests): each one as it is emitted. */
export async function filledDayRows(input: Iterable<Record<string, any>> | AsyncIterable<Record<string, any>>, day: string, src: string, results: ReadonlyMap<string, string>, depth: DepthModel, params?: Partial<DepthSimParams>, o: { keep?: ReadonlySet<string>; diag?: boolean; sink?: (e: Record<string, any>) => void } = {}): Promise<{ rows: Row[]; events: number; sim: SimActivity; picks: DepthPicks }> {
  const { streamFiller, depthSims, picksOf } = await import('./goLiveTally');
  const at = depthSims.length;
  const f = streamFiller({ how: 'depth' }, depth, params);
  const sim = depthSims[at];
  const b = rowBuilder(day, src, results, o.keep, o.diag ?? true);
  let events = 0;
  try {
    const emit = (x: Record<string, any>) => { b.push(x); events++; o.sink?.(x); };
    const feed = (e: Record<string, any>) => { for (const x of f.push(e as Ev)) emit(x); };
    if (Symbol.asyncIterator in input) for await (const e of input as AsyncIterable<Record<string, any>>) feed(e); else for (const e of input as Iterable<Record<string, any>>) feed(e);
    for (const x of f.end()) emit(x);
  } finally { depthSims.splice(at, 1); } // a sweep builds thousands of days: the global list must not keep each simulator
  return { rows: b.finish(), events, sim: { ...sim.stats }, picks: picksOf(sim) };
}

// ---------------------------------------------------------------------------------------------------------------
// The fast dev run (workflow input fast; RUNBOOK 3.2.1). The full route writes the filled days and reads them back, parses each real
// day four times (tickersOf, restrictDay, pairDay, dayRows) and parses the fit days again for their activity lines. This builds the
// same files in one stage: the requote rows from the requote days, the depth rows IN-STREAM (the fill-in's records go straight into
// the features code, filledDayRows, honouring --depth-params exactly as the file route does), and the real rows and paired mechanics
// in ONE pass over each real day (restrictLine, the same restriction the match stage writes, then rowBuilder and pairSide on the
// records) - or, with a real side kept by an earlier run (real_features_run), none: the cached rows and activity lines are read
// and refused unless they were built for exactly these days, real days, requote days and feature code. It writes features-real/
// requote/depth.json, paired.json, requote/ and the sidecars the full route's features stage also writes, and prints the lines the
// match, fill and features stages print; a test holds the files and the lines equal to the full route's, number for number.

/** One real day in ONE pass: its rows (the contracts the twin has), its tickers (every market record) and the real side of the
 *  paired mechanics. `keep`: the tickers the restricted day keeps (the twin's and the day before's); `want`: the twin's. */
async function realDayOnePass(file: string, day: string, results: ReadonlyMap<string, string>, keep: ReadonlySet<string>, want: ReadonlySet<string>): Promise<{ rows: Row[]; realT: Map<string, string>; side: PairSide }> {
  const rb = rowBuilder(day, 'real', results), side = pairSide(want), realT = new Map<string, string>();
  for await (const line of recordingLines(file)) {
    if (!line) continue;
    if (line.includes('"k":"market"')) { try { const e = JSON.parse(line); if (e.k === 'market' && e.ticker) realT.set(e.ticker, e.series ?? ''); } catch { /* a cut line */ } }
    const kept = restrictLine(line, keep);
    if (kept === undefined) continue;
    let e: Record<string, any>;
    try { e = JSON.parse(kept); } catch { continue; /* a cut line */ }
    rb.push(e); side.push(e);
  }
  return { rows: rb.finish(), realT, side };
}

/** The real side of an earlier run, read from its twinlite files in `dir` and refused unless it was built for exactly `now` (the
 *  key of this run). Nothing is guessed: a run with no sidecars (made before the fast route, or on a confirm split) is refused. */
export function loadRealSide(dir: string, now: RealMeta, run: string): { rowsText: string; rows: Row[]; paired: Paired[]; activity: Activity; meta: RealMeta; fitText: string; fitRows: Row[] } {
  const who = `real_features_run ${run}`, file = (n: string) => path.join(dir, n);
  const missing = ['features-real.json', 'real-meta.json', 'real-activity.json', REAL_FIT_FILE, 'paired.json'].filter((n) => !fs.existsSync(file(n)));
  if (missing.length) {
    // the reason is read from the files other than the FIT rows first (an older real side lacks those too); a side that lacks only the FIT rows is one of an earlier round
    const others = missing.filter((n) => n !== REAL_FIT_FILE);
    const why = !others.length ? 'it was made before the per-asset calibration kept the real FIT rows (round R2), and an old run is never guessed at. Dispatch a dev run with this code (full, or fast without real_features_run) and use its run id'
      : others.some((n) => n.startsWith('real-')) ? 'it was made before the fast route kept its real side (or it read the confirm days), and an old run is never guessed at. Dispatch a dev run with this code (full, or fast without real_features_run) and use its run id'
        : 'its judged features are not complete on Drive';
    throw new Error(`${who} has no ${missing.join(', ')}: ${why}`);
  }
  const read = <T>(n: string): T => { try { return JSON.parse(fs.readFileSync(file(n), 'utf8')) as T; } catch { throw new Error(`${who}: ${n} is not readable JSON`); } };
  const had = read<RealMeta>('real-meta.json'), act = read<{ version?: number } & Activity>('real-activity.json');
  if (!Array.isArray(had?.judged) || !Array.isArray(had?.fit) || typeof had?.days !== 'object' || !Array.isArray(act?.follow) || !Array.isArray(act?.days)) throw new Error(`${who}: real-meta.json or real-activity.json is not what this code writes (an old or damaged copy); it is not reused. Leave real_features_run empty to parse the real days again`);
  const diff = realMetaDiff(had, now);
  if (act.version !== REAL_SIDE_VERSION && !diff.some((d) => d.aspect === 'sidecar format')) diff.push({ aspect: 'sidecar format', had: `real-activity.json format ${act.version}`, now: `format ${REAL_SIDE_VERSION}` });
  if (diff.length) throw new Error(`${who} was built for ${diff.map((d) => d.had).join('; ')}, not these (${diff.map((d) => d.now).join('; ')}): it differs in ${diff.map((d) => d.aspect).join(' / ')}. Leave real_features_run empty to parse the real days again`);
  const rowsText = fs.readFileSync(file('features-real.json'), 'utf8'), rows = read<Row[]>('features-real.json'), all = read<Paired[]>('paired.json');
  const strays = [...new Set(rows.map((r) => r.day))].filter((d) => !now.judged.includes(d));
  if (strays.length) throw new Error(`${who}: features-real.json holds rows of day(s) that are not judged here: ${strays.join(', ')}`);
  // the real FIT rows the calibration reads: exactly this run's fit days (real-meta.json's `fit`, compared above, says which days they were built for)
  const fitText = fs.readFileSync(file(REAL_FIT_FILE), 'utf8'), fitRaw = read<Row[]>(REAL_FIT_FILE);
  if (!Array.isArray(fitRaw)) throw new Error(`${who}: ${REAL_FIT_FILE} is not a list of rows`);
  const fitRows = reviveRows(fitRaw), fitDays = [...new Set(fitRows.map((r) => r.day))], otherFit = fitDays.filter((d) => !now.fit.includes(d)), noFit = now.fit.filter((d) => !fitDays.includes(d));
  if (otherFit.length || noFit.length) throw new Error(`${who}: ${REAL_FIT_FILE} holds rows of ${fitDays.join(', ') || 'no day'}, these fit days are ${now.fit.join(', ')}${otherFit.length ? ` (other fit days: ${otherFit.join(', ')})` : ''}${noFit.length ? ` (none for ${noFit.join(', ')})` : ''}. Leave real_features_run empty to parse the real days again`);
  const paired = now.judged.map((d) => all.find((p) => p.day === d));
  const lost = now.judged.filter((_, i) => !paired[i]);
  if (lost.length) throw new Error(`${who}: paired.json has no entry for ${lost.join(', ')}`);
  return { rowsText, rows, paired: paired as Paired[], activity: { follow: act.follow, days: act.days }, meta: had, fitText, fitRows };
}

export interface FastOpts {
  /** Where split.json is read and the files are written (data/twin). */
  out: string;
  /** The cached real days (md-DAY.jsonl.gz and meta-DAY.json: data/twin-real15m), the requote days (data/replay-src). */
  realDir: string; twinDir: string;
  /** The judged days (the split's). */
  days: string[];
  modelFile: string; paramsFile?: string;
  /** The twinlite files of an earlier run (its real side), and its run id for the messages. */
  realCache?: string; realRun?: string;
  /** The calibration stage's handoff folder (its FIT rows and follow diagnostics, REAL_FIT_FOLLOW_FILE): used only when its key is this run's. */
  handoff?: string;
  log?: (line: string) => void;
}

/** The fast route. Returns the seconds each step took (the `[twin] fast: ...` lines say the same). */
export async function fastRows(o: FastOpts): Promise<Array<[string, number]>> {
  const say = o.log ?? ((l: string) => console.log(l)), times: Array<[string, number]> = [];
  const lap = (name: string, t0: number) => { const sec = Math.round(hr() - t0); times.push([name, sec]); say(`[twin] fast: ${name} ${sec} s`); };
  const split = readSplit(splitFile(o.out));
  if (!split) throw new Error(`no split in ${splitFile(o.out)}: --stage split first`);
  assertDisjoint(split.fit, split.judge); assertHeldOut(split, o.days);
  if (isBlind(split, [...o.days, ...split.fit])) throw new Error('fast=true is for dev and custom splits only: a run that reads a confirm day stays on the audited full path');
  if (o.days.join(',') !== split.judge.join(',')) throw new Error(`the fast rows are for the split's judged days (${split.judge.join(',')}), got ${o.days.join(',') || 'none'}`);
  for (const k of Object.keys(followDiag)) delete followDiag[k]; // the diagnostics of THIS build only
  // What the depth side needs is checked first, before the long part (its lines are printed in the full route's order, after the match lines).
  const setup: string[] = [];
  const { simulatorLine } = await import('./goLiveTally');
  const { depth, loaded } = await depthFillSetup({ how: 'depth', model: o.modelFile, splitFile: splitFile(o.out), params: o.paramsFile ?? '' }, (l) => setup.push(l));
  const results = await resultsOf(o.twinDir, o.days);
  const outDir = (x: string) => path.join(o.out, x);
  fs.mkdirSync(outDir('requote'), { recursive: true });
  const twin = new Map<string, string>(), left: string[] = [];
  for (const day of o.days) {
    const rf = o.realCache ? 'cached' : dayFile(o.realDir, day), tf = dayFile(o.twinDir, day);
    if (!rf || !tf) { say(`[twin] ${day}: ${rf ? '' : 'no real recording '}${tf ? '' : 'no history twin'}; left out`); left.push(day); continue; }
    twin.set(day, tf);
    fs.copyFileSync(tf, path.join(outDir('requote'), path.basename(tf)));
  }
  if (left.length) throw new Error(`judged day(s) without a real recording or a twin: ${left.join(', ')}`);
  const extra = split.fit.filter((d) => !o.days.includes(d) && !CONFIRM_DAYS.includes(d));
  const now = await realMetaFor({ judged: o.days, fit: extra, real15mDir: o.realDir, twinDir: o.twinDir });

  // 1. the real side: reused from an earlier run, or built in one pass over each real day
  const t1 = hr();
  let realRows: Row[], paired: Paired[], activity: Activity, realText: string;
  if (o.realCache) {
    const r = loadRealSide(o.realCache, now, o.realRun ?? '?');
    realRows = r.rows; paired = r.paired; activity = r.activity; realText = r.rowsText;
    for (const p of paired) say(matchLine(p.day, p));
    writeRealSidecars(o.out, { ...now, reusedFrom: o.realRun }, activity, r.fitText);
  } else {
    realRows = []; paired = [];
    for (const day of o.days) {
      const rf = dayFile(o.realDir, day)!, tf = twin.get(day)!;
      const twinT = await tickersOf(tf), keep = new Set(twinT.keys());
      const prev = dayFile(o.twinDir, new Date(Date.parse(`${day}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10));
      if (prev) for (const t of (await tickersOf(prev)).keys()) keep.add(t);
      const one = await realDayOnePass(rf, day, results, keep, new Set(twinT.keys()));
      realRows.push(...one.rows);
      const p = await pairFinish(day, one.side, one.realT, tf, twinT);
      paired.push(p);
      say(matchLine(day, p));
    }
    // the fit days' own activity, printed beside the judged days' (not judged): the cached days themselves, as the features stage reads them
    const perDay = perDayOf(realRows);
    // (the FIT days' rows: the calibration stage's handoff when it holds exactly these days, else parsed here)
    const fr = await realFitRows({ fit: extra, realDir: o.realDir, handoff: o.handoff });
    for (const [d, rs] of fr.perDay) perDay.set(`${d} (not judged)`, rs);
    activity = activityOf('real', perDay);
    realText = JSON.stringify(realRows);
    writeRealSidecars(o.out, now, activity, JSON.stringify(fr.rows));
  }
  fs.writeFileSync(path.join(o.out, 'paired.json'), JSON.stringify(paired, null, 1));
  fs.writeFileSync(path.join(o.out, 'features-real.json'), realText);
  lap(o.realCache ? 'real rows reused' : 'real rows built', t1);
  for (const l of setup) say(l); // the depth model and parameters lines, where the fill stage prints them (after the match lines)

  // 2. the requote rows, from the requote days
  const t2 = hr(), requoteRows: Row[] = [];
  for (const d of o.days) { const f = dayFile(outDir('requote'), d); if (f) requoteRows.push(...(await dayRows(f, d, 'requote', results))); }
  lap('requote rows', t2);

  // 3. the depth rows, in-stream: the fill-in's records go straight into the features code, no filled day is written
  const t3 = hr(), depthRows: Row[] = [], sims: SimActivity[] = [], picks: DepthPicks[] = [];
  for (const d of o.days) { const r = await filledDayRows(events(twin.get(d)!), d, 'depth', results, depth!, loaded?.params); depthRows.push(...r.rows); sims.push(r.sim); picks.push(r.picks); }
  say(`[twin] depth fill-in: ${o.days.length} day(s) built in-stream (no filled day is written)`);
  say(simulatorLine(`${o.out}/depth`, sims, picks));
  lap('depth rows', t3);

  // the features lines, in the order of the features stage: real, requote, depth
  for (const [src, rows] of [['real', realRows], ['requote', requoteRows], ['depth', depthRows]] as Array<[string, Row[]]>) {
    if (src !== 'real') fs.writeFileSync(path.join(o.out, `features-${src}.json`), JSON.stringify(rows));
    say(`[twin] features ${src}: ${rows.length} contract lives over ${o.days.length} day(s)`);
    for (const l of activityLines(src, src === 'real' ? activity : activityOf(src, perDayOf(rows)))) say(l);
  }
  return times;
}

/** A depth model an earlier run fitted (workflow input depth_model_run), reused only when it is the model this run would fit: it
 *  records exactly these fit days (assertModelFitDays: fit days only, none judged), and it was written by this version of the
 *  study (`schema`, a model with none reads as 0, against DEPTH_MODEL_SCHEMA), and, when the earlier run's real-meta.json is at
 *  hand (`metaFile`), from real days of this tag. Returns the line to print; throws the reason otherwise. */
export function checkDepthModelReuse(modelFile: string, split: Pick<Split, 'fit' | 'judge'>, o: { run?: string; metaFile?: string } = {}): string {
  const who = `depth_model_run ${o.run ?? '?'}`;
  let m: Record<string, any>;
  try { m = JSON.parse(fs.readFileSync(modelFile, 'utf8')); } catch { throw new Error(`${who}: ${modelFile} is not readable JSON`); }
  const schema = typeof m.schema === 'number' ? m.schema : 0;
  if (schema !== DEPTH_MODEL_SCHEMA) throw new Error(`${who}: the model has schema ${schema}${m.schema === undefined ? ' (none recorded)' : ''}, this code reads schema ${DEPTH_MODEL_SCHEMA}: the depth study or the simulator changed since it was fitted, so it is not reused. Leave depth_model_run empty to fit it again`);
  try { assertModelFitDays(modelFile, split); } catch (e) { throw new Error(`${who}: ${(e as Error).message}`); }
  const days = [...(m.days as string[])].sort(), fit = [...split.fit].sort();
  if (days.join(',') !== fit.join(',')) throw new Error(`${who}: the model was fitted on ${days.join(', ')}, not exactly the fit days ${fit.join(', ')}. Leave depth_model_run empty to fit it again`);
  let tag = `; no real-meta.json beside it, so the real days' tag it was fitted from is not recorded`;
  if (o.metaFile) {
    let had: string | undefined;
    try { had = JSON.parse(fs.readFileSync(o.metaFile, 'utf8')).real15m; } catch { /* unreadable: treated as not recorded */ }
    if (typeof had === 'string') {
      if (had !== real15mTag()) throw new Error(`${who}: the model was fitted from real days tagged ${had}, these are tagged ${real15mTag()} (the prep's keep rules or REPLAY_EXCLUDE changed). Leave depth_model_run empty to fit it again`);
      tag = `; real days tag ${had}`;
    }
  }
  return `[twin] depth model reused from run ${o.run ?? '?'}: fitted on ${days.join(' ')} (exactly the fit days), schema ${schema}${tag}`;
}

function stageDepthModelCheck(): void {
  const split = readSplit(arg('split-file'));
  if (!split) throw new Error(`no split in ${arg('split-file') || '(no --split-file)'}`);
  assertHeldOut(split);
  console.log(checkDepthModelReuse(arg('depth-model'), split, { run: arg('run') || undefined, metaFile: arg('model-meta') || undefined }));
}

// ---------------------------------------------------------------------------------------------------------------
// Stage calibrate (round R2): the depth model's per-asset LEVEL calibration, fitted on the FIT days (research/history/depthCalibrate.ts).
// It runs in both routes right after the depth fit and before the match/fill or the fast rows, because the confirm run's refit on FIT+DEV
// must be calibrated by the same code. It reads the model's own days only (assertCalibrationDays), writes the `calibration` block into the
// model file (atomically, in place: Drive then keeps the calibrated model, and a depth_model_run reuse carries it), and leaves the real FIT
// rows and follow diagnostics it parsed in a handoff folder for the stages after it.

/** The days a calibration may read: exactly the days the depth model was fitted on, every one of them a FIT day of the split. A judged day, a DEV day of a
 *  dev split or a CONFIRM day refuses (before any file of a day is opened), as do a model whose days are not recorded and one fitted outside the fit set.
 *  Returns the model's days. */
export function assertCalibrationDays(modelFile: string, split: Pick<Split, 'name' | 'fit' | 'judge'>): string[] {
  assertHeldOut(split);
  assertDisjoint(split.fit, split.judge);
  assertModelFitDays(modelFile, split);
  const days = JSON.parse(fs.readFileSync(modelFile, 'utf8')).days as string[];
  const bad = days.filter((d) => !split.fit.includes(d) || split.judge.includes(d) || (split.name !== 'confirm' && CONFIRM_DAYS.includes(d)));
  if (bad.length) throw new Error(`the calibration reads FIT days only: ${bad.join(', ')} ${bad.length > 1 ? 'are' : 'is'} not a FIT day of the ${split.name} split`);
  return [...days];
}

/** The real FIT rows of an earlier run's real side (real_features_run): refused unless its real-meta.json was built for these fit days, this real days tag,
 *  the prepped days as they are now and this feature code, and its rows are exactly these days'. The judged part of its key is not this stage's business. */
export function loadRealFitRows(dir: string, fit: readonly string[], real15mDir: string, run: string): Row[] {
  const who = `real_features_run ${run}`, file = (n: string) => path.join(dir, n);
  const missing = ['real-meta.json', REAL_FIT_FILE].filter((n) => !fs.existsSync(file(n)));
  if (missing.length) throw new Error(`${who} has no ${missing.join(', ')}: it was made before the per-asset calibration kept the real FIT rows (round R2), and an old run is never guessed at. Dispatch a dev run with this code (full, or fast without real_features_run) and use its run id`);
  const read = <T>(n: string): T => { try { return JSON.parse(fs.readFileSync(file(n), 'utf8')) as T; } catch { throw new Error(`${who}: ${n} is not readable JSON`); } };
  const had = read<RealMeta>('real-meta.json'), rowsRaw = read<Row[]>(REAL_FIT_FILE), rows = Array.isArray(rowsRaw) ? reviveRows(rowsRaw) : rowsRaw;
  if (!Array.isArray(had?.judged) || !Array.isArray(had?.fit) || typeof had?.days !== 'object' || !Array.isArray(rows)) throw new Error(`${who}: real-meta.json or ${REAL_FIT_FILE} is not what this code writes (an old or damaged copy); it is not reused. Leave real_features_run empty to parse the real days again`);
  const now: RealMeta = { version: REAL_SIDE_VERSION, judged: had.judged, fit: [...fit], real15m: real15mTag(), featureCode: FEATURE_CODE_VERSION, days: { ...had.days, ...Object.fromEntries(fit.map((d) => [d, { real: realDaySha(real15mDir, d) }])) } };
  const diff = realMetaDiff(had, now);
  if (diff.length) throw new Error(`${who} was built for ${diff.map((d) => d.had).join('; ')}, not these (${diff.map((d) => d.now).join('; ')}): it differs in ${diff.map((d) => d.aspect).join(' / ')}. Leave real_features_run empty to parse the real days again`);
  const days = [...new Set(rows.map((r) => r.day))], other = days.filter((d) => !fit.includes(d)), none = fit.filter((d) => !days.includes(d));
  if (other.length || none.length) throw new Error(`${who}: ${REAL_FIT_FILE} holds rows of ${days.join(', ') || 'no day'}, these fit days are ${fit.join(', ')}${other.length ? ` (other fit days: ${other.join(', ')})` : ''}${none.length ? ` (none for ${none.join(', ')})` : ''}. Leave real_features_run empty to parse the real days again`);
  return rows;
}

/** Leaves the real FIT rows and the follow diagnostics they feed in `dir`, under the key of these days (realFitRows reads them back, only when its own key is exactly this). */
export function writeRealFitHandoff(dir: string, fit: readonly string[], real15mDir: string, fr: RealFit): void {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, REAL_FIT_FILE), JSON.stringify(fr.rows));
  fs.writeFileSync(path.join(dir, REAL_FIT_FOLLOW_FILE), JSON.stringify({ version: REAL_SIDE_VERSION, key: realFitKey(fit, real15mDir), rowsPerDay: Object.fromEntries(fit.map((d) => [d, fr.perDay.get(d)?.length ?? 0])), follow: fr.follow }));
}

/** The code a calibration is a fit of (stamped into its block by the calibrate stage, checked when a model is reused): the simulator's source (research/history/depthSim.ts
 *  with its comments and whitespace out, hashed: any edit that can move the fill-in's stream changes it, a doc edit does not), the requote layer's version (REPLAY_VERSION)
 *  and the feature code's version (FEATURE_CODE_VERSION). The multipliers are a fit of THIS simulator, requote layer and feature code on the FIT days; reused under other
 *  code they would be numbers fitted to a different twin, which no later line would flag. NOT seen by this stamp (so a change there bumps DEPTH_MODEL_SCHEMA in the same
 *  commit, research/history/depthModelVersion.ts): the fill-in's driver in research/goLiveTally.ts (streamFiller, fillQuotes) and the depth study. */
const DEPTH_SIM_FILE = fileURLToPath(new URL('./history/depthSim.ts', import.meta.url));
export function calibrationCode(simFile: string = DEPTH_SIM_FILE): CalibrationCode {
  const text = fs.readFileSync(simFile, 'utf8').replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/\/\/[^\n]*/g, ' ').replace(/\s+/g, ' ').trim();
  return { sim: sha256Text(text).slice(0, 16), replay: String(REPLAY_VERSION), featureCode: FEATURE_CODE_VERSION };
}

/** The tickers a requote day's twin has: the contracts whose `market` record is in it (the same condition rowBuilder opens a contract life on, so these are exactly
 *  the contracts the twin's FIT rows can hold). */
export function twinTickersOf(evs: Iterable<Record<string, any>>): Set<string> {
  const out = new Set<string>();
  for (const e of evs) if (e.k === 'market' && e.ticker && is15m(e.series, e.ticker)) out.add(e.ticker);
  return out;
}

/** The line that says which code a calibration is a fit of (names and hashes only). */
export const codeStampNote = (c: CalibrationCode | undefined, head: string): string => (c ? `${head} simulator ${c.sim}, requote layer ${c.replay}, feature code ${c.featureCode}` : `${head} no code recorded`);

/** The real FIT rows restricted to the contracts the twin has on the same day (round R2, fix round 1). The judge compares real and twin on the contracts the
 *  twin has: the judged real rows are the real day restricted to the requote day's tickers (stageMatch's `keep`, realDayOnePass's restrictLine). A real FIT
 *  day holds every 15-minute contract, including those with no Kalshi candle (the twin lacks them: `real 15m missing from the twin`), which are typically
 *  quiet ones with thin books. Fitting the twin's means to those rows as well would pull it toward a population the judge never sees and leave a first-moment gap on
 *  the judged days, the quantity the calibration exists to close. So the calibration sees the same population: a row stays only when its ticker is among the day's
 *  `twinTickers`. (A contract listed only in the PREVIOUS day's requote file, one that opens at midnight, is a judged real row but has no twin row, so it is
 *  not a comparable pair and is left out here too; it is under 1 percent of a day's lives.) `counts`: per asset, rows kept of rows read. */
export function restrictFitRows(rows: readonly Row[], twinTickers: ReadonlyMap<string, ReadonlySet<string>>): { rows: Row[]; counts: Array<{ asset: string; kept: number; of: number }> } {
  const kept = rows.filter((r) => twinTickers.get(r.day)?.has(r.ticker) === true);
  const inAsset = (rs: readonly Row[], a: string) => rs.filter((r) => assetOfTicker(r.ticker, DEPTH_ASSETS) === a).length;
  const counts = DEPTH_ASSETS.map((asset) => ({ asset, kept: inAsset(kept, asset), of: inAsset(rows, asset) })).filter((c) => c.of > 0);
  return { rows: kept, counts };
}

export interface CalibrateStageOpts {
  /** Where the handoff (the real FIT rows and follow diagnostics this stage parsed) is left for the stages after it. */
  out: string;
  modelFile: string; splitFile: string;
  /** The cached real days (data/twin-real15m) and the requote FIT days (data/replay-fit). */
  realDir: string; twinFitDir: string;
  /** The real side of an earlier run (twinlite files) and its run id: the real FIT rows are read from it instead of parsed. */
  realCache?: string; realRun?: string;
  /** Seconds the held-in check may cost (0: not run). */
  heldInBudgetS?: number;
  /** Fewest real and twin lives an asset needs (tests only: the stage's CLI uses the algorithm's own, CAL_MIN_LIVES). */
  minLives?: number;
  log?: (line: string) => void;
  now?: () => number;
}

/** The stage: calibrate the model file's depth model on its own FIT days and write the block into it. Returns the calibration. */
export async function calibrateStage(o: CalibrateStageOpts): Promise<DepthCalibration> {
  const say = o.log ?? ((l: string) => console.log(l)), now = o.now ?? hr;
  const split = readSplit(o.splitFile);
  if (!split) throw new Error(`no split in ${o.splitFile || '(no --split-file)'}`);
  const days = assertCalibrationDays(o.modelFile, split);
  const model = readDepthModel(o.modelFile);
  if (!model) throw new Error(`${o.modelFile} is not a depth model`);
  if (model.calibration) throw new Error('the depth model already carries a calibration: a model is calibrated once, right after it is fitted (a reused model keeps the one it has)');
  const t0 = now();
  // the real FIT rows: an earlier run's (real_features_run), else the cached real days parsed once (and left in the handoff folder)
  let realRows: Row[];
  if (o.realCache) realRows = loadRealFitRows(o.realCache, days, o.realDir, o.realRun ?? '?');
  else {
    const fr = await realFitRows({ fit: days, realDir: o.realDir, needs: 'the calibration' });
    realRows = fr.rows;
    writeRealFitHandoff(o.out, days, o.realDir, fr);
  }
  // the twin's FIT days: the requote days' records, read once (every pass of the fill-in plays them again)
  const requote = new Map<string, Array<Record<string, any>>>();
  for (const d of days) {
    const f = dayFile(o.twinFitDir, d);
    if (!f) throw new Error(`the calibration needs the requote day of FIT day ${d} in ${o.twinFitDir}`);
    const evs: Array<Record<string, any>> = [];
    for await (const e of events(f)) evs.push(e);
    requote.set(d, evs);
  }
  // The judge's population: only the real contracts the twin has on the day (restrictFitRows says why). The handoff above keeps every real FIT row (the activity lines read it).
  const fitRows = restrictFitRows(realRows, new Map([...requote].map(([d, evs]) => [d, twinTickersOf(evs)])));
  for (const c of fitRows.counts) say(`[twin] calibration: asset ${c.asset} real FIT lives kept ${c.kept} of ${c.of} (contract in the twin)`);
  if (realRows.length && !fitRows.rows.length) throw new Error(`the calibration: none of the ${realRows.length} real FIT lives is a contract the requote FIT days have (the requote days' tickers differ from the prepped real days')`);
  realRows = fitRows.rows;
  const fi = (k: (typeof FEATURES)[number]) => FEATURES.indexOf(k);
  const cols = { top: fi('topSize'), depth10: fi('depth10'), tradeSize: fi('tradeSize'), qchg: fi('quoteChangesPerMin'), trades: fi('tradesPerMin'), quotedShare: fi('quotedShare') };
  const twinRows = async (m: DepthModel, ds: readonly string[]): Promise<CalRow[]> => {
    const rows: CalRow[] = [];
    for (const d of ds) { const r = await filledDayRows(requote.get(d)!, d, 'depth', new Map(), m, undefined, { diag: false }); rows.push(...r.rows); }
    return rows;
  };
  const input = { model, fitDays: days, realRows, twinRows, cols, code: calibrationCode(), log: say, now, heldInBudgetS: o.heldInBudgetS ?? CAL_HELD_IN_BUDGET_S, ...(o.minLives !== undefined ? { minLives: o.minLives } : {}) };
  const res = await calibrateDepthModel(input);
  await heldInCheck(input, res);
  // the block goes into the model file in place (atomically: the file is read by every later step, and Drive keeps it)
  const tmp = `${o.modelFile}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(res.model));
  fs.renameSync(tmp, o.modelFile);
  say(codeStampNote(res.calibration.code, '[twin] calibration: fitted by'));
  say(`[twin] calibration: written into the depth model (schema ${DEPTH_MODEL_SCHEMA}); ${Math.round(now() - t0)} s`);
  return res.calibration;
}

async function stageCalibrate(): Promise<void> {
  await calibrateStage({
    out: arg('out', 'data/calib'), modelFile: arg('depth-model'), splitFile: arg('split-file'), realDir: arg('real', 'data/twin-real15m'), twinFitDir: arg('twin-fit', 'data/replay-fit'),
    realCache: arg('real-cache') || undefined, realRun: arg('real-run') || undefined, heldInBudgetS: arg('held-in-budget-s') ? Number(arg('held-in-budget-s')) : undefined,
  });
}

/** A depth model an earlier run fitted (depth_model_run) must carry its calibration: a model fitted before the calibration ran, or one whose calibration
 *  failed, plays as measured, and a reuse must never do that silently. Returns the line to print; throws the reason otherwise. */
export function checkDepthModelCalibration(modelFile: string, split: Pick<Split, 'name' | 'fit' | 'judge'>, o: { run?: string; code?: CalibrationCode } = {}): string {
  const who = `depth_model_run ${o.run ?? '?'}`;
  const days = (() => { try { return assertCalibrationDays(modelFile, split); } catch (e) { throw new Error(`${who}: ${(e as Error).message}`); } })();
  const m = readDepthModel(modelFile);
  if (!m) throw new Error(`${who}: ${modelFile} is not a depth model`);
  if (!m.calibration) throw new Error(`${who}: the model has no calibration block: it was fitted before the per-asset calibration ran, or its calibration failed, so it is not reused. Leave depth_model_run empty to fit and calibrate it again`);
  // The multipliers are a fit of the simulator, requote layer and feature code they were fitted with: a model whose block was fitted by other code (or by code that did not say) is stale
  const was = m.calibration.code, now = o.code ?? calibrationCode();
  if (!was) throw new Error(`${who}: the model's calibration carries no code stamp (the simulator, requote layer and feature code it was fitted with are not recorded), so it cannot be told from a stale one and is not reused. Leave depth_model_run empty to fit and calibrate it again`);
  const differs = ([['simulator', 'sim'], ['requote layer', 'replay'], ['feature code', 'featureCode']] as const).filter(([, k]) => was[k] !== now[k]);
  if (differs.length) throw new Error(`${who}: the model's calibration was fitted by other code than this ref's: ${differs.map(([what, k]) => `${what} ${was[k]} then, ${now[k]} now`).join('; ')}. Its multipliers are a fit of that twin, not of this one, so the model is not reused. Leave depth_model_run empty to fit and calibrate it again (a change that moves the fill-in's stream must come with a refit)`);
  return `[twin] depth model calibration carried by run ${o.run ?? '?'}: assets ${Object.keys(m.calibration.byAsset).join(' ')}, fitted on ${days.join(' ')}, ${m.calibration.iterations} iteration(s); no recalibration`;
}

function stageCalibrationCheck(): void {
  const split = readSplit(arg('split-file'));
  if (!split) throw new Error(`no split in ${arg('split-file') || '(no --split-file)'}`);
  console.log(checkDepthModelCalibration(arg('depth-model'), split, { run: arg('run') || undefined }));
  console.log(`${codeStampNote(readDepthModel(arg('depth-model'))?.calibration?.code, '[twin] depth model calibration was fitted by')} (this ref has the same: a calibration fitted by other code is refused)`);
}

async function stageFastRows(): Promise<void> {
  const out = arg('out', 'data/twin');
  await fastRows({ out, realDir: arg('real', 'data/twin-real15m'), twinDir: arg('twin', 'data/replay-src'), days: arg('days').split(',').filter(Boolean), modelFile: arg('depth-model'), paramsFile: arg('depth-params') || undefined, realCache: arg('real-cache') || undefined, realRun: arg('real-run') || undefined, handoff: arg('handoff') || undefined });
}

// ---------------------------------------------------------------------------------------------------------------
// Stage sweep: tune the depth simulator's 13 constants on the FIT days only, with the judge as the objective (a parameter search over an UNCALIBRATED model:
// not the R2 per-asset calibration, which is stage calibrate; a sweep's params replace three of its multipliers when both meet, RUNBOOK 9).

/** The days a sweep may read: the dev split's FIT days (all of them or at least two), never a DEV, CONFIRM or any other day. Any
 *  split name but dev is refused. Returns the days. */
export function resolveSweepFit(splitName: string, fitIn: string): string[] {
  if (splitName !== 'dev') throw new Error(`a sweep reads the dev split's FIT days only: split "${splitName}" is refused (the only split a sweep takes is dev)`);
  const fit = parseDays(fitIn, 'fit days');
  if (!fit.length) throw new Error(`a sweep needs --fit-days (the dev split's FIT days: ${SPLITS.dev.fit.join(',')})`);
  assertHeldOut({ name: 'dev', fit, judge: [] });
  assertDisjoint(fit, SPLITS.dev.judge);
  const stray = fit.filter((d) => !(SPLITS.dev.fit as readonly string[]).includes(d));
  if (stray.length) throw new Error(`not FIT days of the dev split: ${stray.join(', ')} (a sweep reads ${SPLITS.dev.fit.join(', ')} only)`);
  if (fit.length < MIN_CUSTOM_JUDGED_DAYS) throw new Error(`a sweep judges the FIT days leaving one day out: it needs at least ${MIN_CUSTOM_JUDGED_DAYS} fit days, got ${fit.length} (with one the AUC is a flat 0.500)`);
  return fit;
}

/** Fewest lives either side must hold for a candidate to be judged. */
export const MIN_SWEEP_LIVES = 20;
/** Fewest lives one FIT day must hold on each side. Leave-one-day-out scores a fold only when its held-out day has both real and twin
 *  lives; a day with none (the requote tickers do not match the real day, a thin day) drops its folds, and when every fold drops the AUC
 *  is a flat 0.5 that reads as "indistinguishable": a pooled count cannot see that, so the days are counted one by one. */
export const MIN_DAY_LIVES = 5;
const countByDay = (rs: readonly Row[]): Map<string, number> => { const m = new Map<string, number>(); for (const r of rs) m.set(r.day, (m.get(r.day) ?? 0) + 1); return m; };
export interface SweepJudgement { loss: number; features: Record<string, number>; regimes: Record<string, number | null>; top3: Array<{ name: string; auc: number }>; note?: string }

/** The judge's numbers for one candidate: the all-feature leave-one-day-out AUC (the loss), each feature's own AUC and each regime's
 *  AUC, computed exactly as the verdict computes them (discriminate, terciles of ixMoveBps over the real rows). A candidate whose
 *  twin left too few lives, or fewer than half of the real ones, or fewer than MIN_DAY_LIVES on any day the real rows are on, is not
 *  judged: loss 1 (an empty twin, or a day without twin lives, must never read as 0.5). The real side is the harness's, not the
 *  candidate's: real rows on fewer than two days, or fewer than MIN_DAY_LIVES on a day, refuse the judgement (a throw). */
export function judgeSweepRows(real: Row[], twin: Row[]): SweepJudgement {
  if (real.length < MIN_SWEEP_LIVES) throw new Error(`the real FIT rows hold ${real.length} lives (at least ${MIN_SWEEP_LIVES} are needed): refusing to judge`);
  const realDays = countByDay(real), twinDays = countByDay(twin);
  if (realDays.size < 2) throw new Error(`the real FIT rows are on ${realDays.size} day(s) (at least 2 are needed: with one, leave-one-day-out runs no fold and the AUC is a flat 0.5): refusing to judge`);
  const thin = [...realDays].filter(([, n]) => n < MIN_DAY_LIVES);
  if (thin.length) throw new Error(`a FIT day holds fewer than ${MIN_DAY_LIVES} real lives (${thin.map(([d, n]) => `${d} ${n}`).join(', ')}): refusing to judge (its folds would be skipped and the AUC could read 0.5 for that reason)`);
  if (twin.length < MIN_SWEEP_LIVES || twin.length < 0.5 * real.length) return { loss: 1, features: {}, regimes: {}, top3: [], note: `twin left ${twin.length} lives against ${real.length} real: not judged` };
  const bare = [...realDays].filter(([d]) => (twinDays.get(d) ?? 0) < MIN_DAY_LIVES);
  if (bare.length) return { loss: 1, features: {}, regimes: {}, top3: [], note: `a FIT day has no twin lives (${bare.map(([d, n]) => `${d} ${twinDays.get(d) ?? 0} twin against ${n} real`).join(', ')}; at least ${MIN_DAY_LIVES} needed): not judged` };
  const all = FEATURES.map((_, j) => j), r4 = (x: number) => +x.toFixed(4);
  const loss = discriminate(real, twin, all);
  const each = FEATURES.map((name, j) => ({ name, auc: discriminate(real, twin, [j]) }));
  const vi = FEATURES.indexOf('ixMoveBps');
  const cuts = [1 / 3, 2 / 3].map((q) => { const v = real.map((r) => r.f[vi]).filter(Number.isFinite).sort((x, y) => x - y); return v[Math.floor(q * v.length)] ?? 0; });
  const regimeOf = (r: Row) => (r.f[vi] <= cuts[0] ? 'calm' : r.f[vi] <= cuts[1] ? 'normal' : 'volatile');
  const regimes: Record<string, number | null> = {};
  for (const g of ['calm', 'normal', 'volatile']) { const rr = real.filter((r) => regimeOf(r) === g), tt = twin.filter((r) => regimeOf(r) === g); regimes[g] = rr.length > 20 && tt.length > 20 ? r4(discriminate(rr, tt, all)) : null; }
  const top3 = [...each].sort((x, y) => Math.abs(y.auc - 0.5) - Math.abs(x.auc - 0.5)).slice(0, 3).map((e) => ({ name: e.name, auc: r4(e.auc) }));
  if (!Number.isFinite(loss)) return { loss: 1, features: {}, regimes: {}, top3: [], note: 'the adversary returned no AUC: not judged' };
  return { loss: +loss.toFixed(6), features: Object.fromEntries(each.map((e) => [e.name, r4(e.auc)])), regimes, top3 };
}

export interface SweepOpts {
  /** Split the sweep was asked for (only dev). */
  split?: string; fitDays: string; twinDir: string; realDir: string; modelFile: string; gen: number; shard: number; shards: number; perShard: number; parentsFile?: string; out: string;
  /** Stop starting candidates after this many minutes from the stage's start (the shard then says it is incomplete). */
  budgetMin?: number;
  log?: (line: string) => void;
}
export const sweepShardName = (gen: number, shard: number, shards: number) => `sweep-g${gen}-shard${shard}of${shards}.json`;
const hr = () => Number(process.hrtime.bigint()) / 1e9;

/** One shard of one generation: every candidate of its slice judged on the FIT days, the shard file rewritten after each. */
export async function runSweep(o: SweepOpts): Promise<SweepShardFile> {
  const log = o.log ?? ((l: string) => console.log(l));
  const fit = resolveSweepFit(o.split ?? 'dev', o.fitDays);
  if (!Number.isInteger(o.perShard) || o.perShard < 1 || o.perShard > 500) throw new Error(`--candidates (per shard) must be a whole number from 1 to 500, got ${o.perShard}`);
  const population = o.shards * o.perShard, [lo, hi] = shardRange(population, o.shards, o.shard);
  // The cached real FIT days: present and made by this code (the same check the build runs).
  const err = real15mError(checkReal15m(o.realDir, fit));
  if (err) throw new Error(err);
  const days = fit.map((d) => ({ day: d, twin: dayFile(o.twinDir, d), real: dayFile(o.realDir, d) }));
  for (const x of days) if (!x.twin || !x.real) throw new Error(`a sweep needs the requote day and the cached real day of ${x.day} (twin ${x.twin ? 'ok' : `missing in ${o.twinDir}`}, real ${x.real ? 'ok' : `missing in ${o.realDir}`})`);
  // The depth model: fitted on the FIT days only (the model records the days it read).
  assertModelFitDays(o.modelFile, { fit, judge: [...SPLITS.dev.judge] });
  const model = readDepthModel(o.modelFile);
  if (!model) throw new Error(`${o.modelFile} is not a depth model`);
  let parents: ReturnType<typeof parentsFrom> | undefined;
  if (o.gen > 0) {
    if (!o.parentsFile) throw new Error(`generation ${o.gen} needs --parents (the previous generation's elite.json)`);
    parents = parentsFrom(JSON.parse(fs.readFileSync(o.parentsFile, 'utf8')));
  } else if (o.parentsFile) log('[twin] sweep: generation 0 takes no parents (the file is ignored)');
  const cands = generationCandidates(o.gen, population, parents?.parents, parents?.frac);
  // What does not change between candidates, once per shard: the requote days' records, the labels, the real FIT rows.
  const t0 = hr();
  const results = await resultsOf(o.twinDir, fit);
  const requote = new Map<string, Array<Record<string, any>>>(), realRows: Row[] = [], realPerDay = new Map<string, number>();
  for (const x of days) {
    const evs: Array<Record<string, any>> = [];
    for await (const e of events(x.twin!)) evs.push(e);
    requote.set(x.day, evs);
    // The real day restricted to the twin's contracts (the build's restrictDay): this day's requote contracts, and the day before's
    // when that is a FIT day too (contracts listed the day before); a day outside the fit set is never read.
    const keep = new Set((await tickersOf(x.twin!)).keys());
    const prev = new Date(Date.parse(`${x.day}T00:00:00Z`) - 86_400_000).toISOString().slice(0, 10), pf = fit.includes(prev) ? days[fit.indexOf(prev)].twin : undefined;
    if (pf) for (const t of (await tickersOf(pf)).keys()) keep.add(t);
    const dr = await dayRows(x.real!, x.day, 'real', results, keep, false);
    realPerDay.set(x.day, dr.length);
    realRows.push(...dr);
  }
  // Every FIT day must have real lives of its own: a day with none (the requote day's tickers do not match the real day, a thin day) drops its
  // leave-one-day-out folds, and with every fold dropped the AUC is a flat 0.5 for every candidate: refuse it here, before any candidate is judged.
  const thinDays = fit.filter((d) => (realPerDay.get(d) ?? 0) < MIN_DAY_LIVES);
  if (thinDays.length) throw new Error(`the real FIT day(s) ${thinDays.map((d) => `${d} (${realPerDay.get(d) ?? 0} lives)`).join(', ')} hold fewer than ${MIN_DAY_LIVES} contract lives that the requote day also has (at least ${MIN_DAY_LIVES} per FIT day are needed): the requote day's tickers do not match the real day's, or the real day is thin; refusing to sweep (every candidate would read AUC 0.5)`);
  if (realRows.length < MIN_SWEEP_LIVES) throw new Error(`the real FIT days hold ${realRows.length} contract lives (at least ${MIN_SWEEP_LIVES} are needed)`);
  log(`[twin] sweep g${o.gen} shard ${o.shard}/${o.shards}: candidates ${lo}..${hi - 1} of ${population} (${hi - lo} here), ${fit.length} FIT day(s), ${realRows.length} real lives, ${[...requote.values()].reduce((a, e) => a + e.length, 0)} requote records; loaded in ${(hr() - t0).toFixed(1)} s`);
  fs.mkdirSync(o.out, { recursive: true });
  const file = path.join(o.out, sweepShardName(o.gen, o.shard, o.shards));
  const shardFile: SweepShardFile = { kind: 'sweep-shard', version: SWEEP_VERSION, gen: o.gen, shard: o.shard, shards: o.shards, perShard: o.perShard, population, fitDays: fit, modelDays: model.days, complete: false, results: [] };
  const save = () => { fs.writeFileSync(`${file}.tmp`, JSON.stringify(shardFile)); fs.renameSync(`${file}.tmp`, file); };
  save();
  let events_ = 0, simSec = 0, judgeSec = 0;
  for (let i = lo; i < hi; i++) {
    if (o.budgetMin !== undefined && (hr() - t0) / 60 >= o.budgetMin) { log(`[twin] sweep g${o.gen} shard ${o.shard}/${o.shards}: the ${o.budgetMin}-minute budget is spent after ${shardFile.results.length} of ${hi - lo} candidates; the rest are not judged (the shard is kept as incomplete)`); break; }
    const params = resolveDepthSimParams(cands[i]), c0 = hr();
    const twinRows: Row[] = [];
    for (const x of days) { const r = await filledDayRows(requote.get(x.day)!, x.day, 'depth', results, model, params, { diag: false }); twinRows.push(...r.rows); events_ += r.events; }
    const c1 = hr(), j = judgeSweepRows(realRows, twinRows), c2 = hr();
    simSec += c1 - c0; judgeSec += c2 - c1;
    const res: SweepResult = { gen: o.gen, index: i, params, loss: j.loss, features: j.features, regimes: j.regimes, top3: j.top3, realRows: realRows.length, twinRows: twinRows.length, seconds: +(c2 - c0).toFixed(1), ...(j.note ? { note: j.note } : {}) };
    shardFile.results.push(res);
    save();
    log(`[twin] sweep g${o.gen} c${i}: loss ${j.loss.toFixed(4)}${j.top3.length ? ` (gives it away: ${j.top3.map((t) => `${t.name} ${t.auc}`).join(', ')})` : ` (${j.note})`}; ${twinRows.length} twin lives; ${res.seconds} s`);
  }
  shardFile.complete = shardFile.results.length === hi - lo;
  save();
  const best = rankResults(shardFile.results)[0];
  log(`[twin] sweep g${o.gen} shard ${o.shard}/${o.shards}: ${shardFile.results.length} candidates, best loss ${best ? best.loss.toFixed(4) : 'na'}${best ? ` (c${best.index})` : ''}; ${(simSec / Math.max(1, shardFile.results.length)).toFixed(1)} s a candidate in the fill-in and features (${Math.round(events_ / Math.max(1e-9, simSec))} records a second), ${(judgeSec / Math.max(1, shardFile.results.length)).toFixed(1)} s in the judge`);
  return shardFile;
}

/** The merged generation: its candidates ranked, the best one, and the elite (the next generation's parents). `lines`: what to print. */
export interface SweepCollected { best: Record<string, unknown>; elite: Record<string, unknown>; results: Record<string, unknown>; lines: string[] }

export function collectSweep(dir: string, o: { gen: number; shards: number; perShard: number; partial?: boolean }): SweepCollected {
  const files: SweepShardFile[] = [];
  for (let i = 0; i < o.shards; i++) {
    const f = path.join(dir, sweepShardName(o.gen, i, o.shards));
    if (fs.existsSync(f)) files.push(JSON.parse(fs.readFileSync(f, 'utf8')) as SweepShardFile);
  }
  // Every shard names the days it read: FIT days of the dev split, one set, and a model fitted on them only.
  const fits = new Set(files.map((f) => JSON.stringify(f.fitDays))), models = new Set(files.map((f) => JSON.stringify(f.modelDays)));
  if (fits.size > 1 || models.size > 1) throw new Error('the shard files were made on different fit days or depth models: they are not one generation');
  const fitDays = files.length ? resolveSweepFit('dev', files[0].fitDays.join(',')) : [];
  if (files.length) assertModelFitDaysList(files[0].modelDays, fitDays);
  if (!files.length && !o.partial) throw new Error(`no shard file for generation ${o.gen} in ${dir}`);
  const { results, missing, population, incomplete, noFile } = mergeShards(files, { gen: o.gen, shards: o.shards, perShard: o.perShard, partial: o.partial });
  const ranked = rankResults(results), best = ranked[0];
  const elite = eliteOf(ranked, ELITE_FRACTION);
  const dflt = results.find((r) => r.index === 0 && o.gen === 0);
  const lines = [`[twin] sweep g${o.gen}: ${results.length} of ${population} candidates judged by ${files.length} shard(s)${missing.length ? ` (${missing.length} missing: partial)` : ''}; best loss ${best.loss.toFixed(4)} (c${best.index}), median ${ranked[Math.floor(ranked.length / 2)].loss.toFixed(4)}, worst ${ranked[ranked.length - 1].loss.toFixed(4)}`];
  // A partial generation says which shards fell short (a green job that stopped at its budget is incomplete too, not only a failed one).
  for (const x of incomplete) lines.push(`[twin] sweep g${o.gen}: shard ${x.shard} incomplete: ${x.have} of ${x.of} candidates judged (it stopped at its budget, or its job failed)`);
  for (const i of noFile) lines.push(`[twin] sweep g${o.gen}: shard ${i} has no result file (its job failed before its first candidate)`);
  if (dflt) lines.push(`[twin] sweep g${o.gen}: the defaults (c0) score ${dflt.loss.toFixed(4)}; ${best.index === 0 ? 'no candidate beat them' : `the best candidate beats them by ${(dflt.loss - best.loss).toFixed(4)}`}`);
  for (const [k, r] of ranked.slice(0, 5).entries()) {
    lines.push(`[twin] sweep top ${k + 1}: c${r.index} loss ${r.loss.toFixed(4)}; ${describeParams(r.params)}`);
    lines.push(`[twin] sweep top ${k + 1}: gives it away ${r.top3.map((t) => `${t.name} ${t.auc}`).join(', ') || 'n/a'}; regimes ${Object.entries(r.regimes).map(([g, a]) => `${g} ${a ?? 'n/a'}`).join(', ') || 'n/a'}`);
  }
  // The exact values of the best candidate, every digit (JSON prints the shortest text that reads back as the same number): the 4-digit lines
  // above are for reading only. A promotion to the code defaults pastes THIS line (RUNBOOK 9.5); names and numbers only, public-safe.
  lines.push(`[twin] sweep best params exact (g${o.gen} c${best.index}, loss ${best.loss.toFixed(4)}): ${JSON.stringify(best.params)}`);
  const common = { version: SWEEP_VERSION, gen: o.gen, split: 'dev', fitDays, modelDays: files[0]?.modelDays ?? [], population };
  return {
    best: { kind: 'sweep-best', ...common, evaluated: results.length, index: best.index, loss: best.loss, params: best.params, features: best.features, regimes: best.regimes, top3: best.top3, ...(dflt ? { defaultLoss: dflt.loss } : {}) },
    elite: { kind: 'sweep-elite', ...common, eliteFraction: ELITE_FRACTION, elite },
    results: { kind: 'sweep-results', ...common, results: ranked },
    lines,
  };
}

/** The model's own days must be fit days (a sweep's depth model is fitted on the FIT days only). */
function assertModelFitDaysList(modelDays: readonly string[], fit: readonly string[]): void {
  if (!modelDays.length) throw new Error('a shard file does not record the days its depth model was fitted on');
  assertDisjoint(modelDays, SPLITS.dev.judge);
  const stray = modelDays.filter((d) => !fit.includes(d));
  if (stray.length) throw new Error(`the depth model was fitted on days outside the fit set: ${stray.join(', ')}`);
}

/** A sweep's best.json as the fill-in reads it (--depth-params): the file must be a sweep's best made on the dev split's FIT days
 *  only, and every parameter name and number must be a known, valid one. */
export function loadDepthParamsFile(file: string): { params: DepthSimParams; gen: number; loss: number; fitDays: string[] } {
  let j: Record<string, any>;
  try { j = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { throw new Error(`depth params file ${file} is not readable JSON (${String((e as Error).message).slice(0, 120)})`); }
  if (j?.kind !== 'sweep-best' || j.version !== SWEEP_VERSION) throw new Error(`depth params file ${file} is not a ${SWEEP_VERSION} sweep best.json (kind ${String(j?.kind)}, version ${String(j?.version)})`);
  if (j.split !== 'dev') throw new Error(`depth params file ${file} was not made on the dev split (split ${String(j.split)})`);
  resolveSweepFit('dev', Array.isArray(j.fitDays) ? j.fitDays.join(',') : '');
  if (typeof j.loss !== 'number' || !j.params || typeof j.params !== 'object') throw new Error(`depth params file ${file} has no params and loss`);
  return { params: resolveDepthSimParams(j.params), gen: Number(j.gen), loss: j.loss, fitDays: j.fitDays };
}

async function stageSweep(): Promise<void> {
  const { shard, shards } = parseShard(arg('shard', '0/1'));
  const o: SweepOpts = {
    split: arg('split', 'dev'), fitDays: arg('fit-days'), twinDir: arg('twin-requote'), realDir: arg('real'), modelFile: arg('depth-model'),
    gen: Number(arg('gen', '0')), shard, shards, perShard: Number(arg('candidates', '8')), parentsFile: arg('parents') || undefined, out: arg('out', 'data/sweep'),
    budgetMin: arg('budget-min') ? Number(arg('budget-min')) : undefined,
  };
  if (!o.twinDir || !o.realDir || !o.modelFile) throw new Error('sweep needs --twin-requote (the requote FIT days), --real (the cached real FIT days), --depth-model and --fit-days');
  if (!Number.isInteger(o.gen) || o.gen < 0) throw new Error(`--gen must be a whole number of at least 0, got "${arg('gen')}"`);
  await runSweep(o);
}

function stageSweepCollect(): void {
  const gen = Number(arg('gen', '0')), shards = Number(arg('shards', '0')), perShard = Number(arg('candidates', '0')), out = arg('out'), dir = arg('dir');
  if (!dir || !out || !(shards >= 1) || !(perShard >= 1)) throw new Error('sweep-collect needs --dir (the shard files), --out, --gen, --shards and --candidates (per shard)');
  const c = collectSweep(dir, { gen, shards, perShard, partial: process.argv.includes('--partial') });
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, 'best.json'), JSON.stringify(c.best, null, 1));
  fs.writeFileSync(path.join(out, 'elite.json'), JSON.stringify(c.elite, null, 1));
  fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(c.results));
  for (const l of c.lines) console.log(l);
}

/** A confirm look: the dispatch's note (free text) and its number (how many confirm looks there have been, counted by
 *  the workflow from the looks it logged on Drive). */
export interface ConfirmLook { n?: number; note: string }
const lookFromArgs = (): ConfirmLook | undefined => {
  const note = arg('confirm-look-note').replace(/[\u0000-\u001f\u007f]+/g, ' ').trim().slice(0, 200);
  return note ? { n: Number(arg('confirm-look')) || undefined, note } : undefined;
};

const fmtQ = (x: number) => (Number.isFinite(x) ? String(+x.toPrecision(3)) : 'na');
/** The six features the per-asset level gaps are read on (round R2; rounds/R1.md's table): where each is in a row. */
const GAP_FEATURES: Record<string, number> = Object.fromEntries((['depth10', 'tradeSize', 'quoteChangesPerMin', 'topSize', 'tradesPerMin', 'quotedShare'] as const).map((k) => [k, FEATURES.indexOf(k)]));

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
    // By asset (REPORT ONLY, never in the checks): the lives and medians of what the depth model's per-asset rows set (trades a minute, depth10
    // and trade size, the last two as the log1p values the features hold), real against twin, and the all-feature AUC within the asset.
    const gapByAsset: Record<string, { real: number; twin: number; gaps: Record<string, number | null> }> = {};
    for (const asset of DEPTH_ASSETS) {
      const rr = real.filter((r) => assetOfTicker(r.ticker) === asset), tt = tw.filter((r) => assetOfTicker(r.ticker) === asset);
      if (!rr.length && !tt.length) continue;
      const m = (rs: Row[], name: (typeof FEATURES)[number]) => (rs.length ? +med(rs.map((r) => r.f[FEATURES.indexOf(name)])).toFixed(3) : 'n/a');
      const au = rr.length > 20 && tt.length > 20 ? discriminate(rr, tt, all).toFixed(3) : 'n/a';
      console.log(`[twin] ${src} by asset ${asset}: lives ${rr.length} real/${tt.length} twin; medians real/twin tradesPerMin ${m(rr, 'tradesPerMin')}/${m(tt, 'tradesPerMin')}, depth10 ${m(rr, 'depth10')}/${m(tt, 'depth10')}, tradeSize ${m(rr, 'tradeSize')}/${m(tt, 'tradeSize')}; AUC ${au} (report only)`);
      // The mean gaps the linear adversary reads (round R2, REPORT ONLY): twin mean minus real mean of the six level features, in the real within-asset sd.
      if (rr.length && tt.length) {
        const g = gapsOfAsset(rr, tt, GAP_FEATURES);
        gapByAsset[asset] = { real: g.real, twin: g.twin, gaps: Object.fromEntries(Object.entries(g.gaps).map(([k, v]) => [k, Number.isFinite(v) ? +v.toFixed(3) : null])) };
        console.log(`[twin] ${src} gap by asset ${asset} (twin minus real, in real within-asset sd; report only): ${Object.entries(g.gaps).map(([k, v]) => `${k} ${Number.isFinite(v) ? v.toFixed(2) : 'na'}`).join(', ')}`);
      }
    }
    // The diagnostics block: per feature the real and twin p10/p50/p90 (all rows, then within each regime), the pairs whose
    // correlation differs most, and the AUC of each judged day (the same folds as the headline AUC).
    const groups = ['all', 'calm', 'normal', 'volatile'] as const;
    const of = (rs: Row[], g: (typeof groups)[number]) => (g === 'all' ? rs : rs.filter((r) => regimeOf(r) === g));
    const quant = Object.fromEntries(FEATURES.map((name, j) => [name, Object.fromEntries(groups.map((g) => [g, { real: quantiles3(of(real, g), j), twin: quantiles3(of(tw, g), j) }]))]));
    const gaps = topCorrDiffs(real, tw, 10);
    const perDay = discriminatePerDay(real, tw, all);
    report.twins[src] = { auc: +a.toFixed(3), stress: +stress.toFixed(3), aucByDay: perDay.byDay.map((d) => ({ ...d, auc: d.auc === null ? null : +d.auc.toFixed(3) })), features: each, regimes, quantiles: quant, corrGaps: gaps.map((g) => ({ ...g, real: +g.real.toFixed(3), twin: +g.twin.toFixed(3), diff: +g.diff.toFixed(3) })), gapByAsset, outcome: o, checks, pass };
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
  if (stage === 'unit') return stageUnit();
  if (stage === 'backtest') return stageBacktest();
  if (stage === 'fill') return stageFill();
  if (stage === 'fastrows') return stageFastRows();
  if (stage === 'depth-model-check') return stageDepthModelCheck();
  if (stage === 'calibrate') return stageCalibrate();
  if (stage === 'calibration-check') return stageCalibrationCheck();
  if (stage === 'sweep') return stageSweep();
  if (stage === 'sweep-collect') return stageSweepCollect();
  if (stage === 'verdict') { await stageVerdict(); return; }
  throw new Error(`unknown --stage ${stage}`);
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) historyTwinMain().catch((e) => {
  // One plain '[twin] ERROR:' line first: the workflow's reports keep '[twin]' lines, so a failure's reason reaches the commit comment.
  console.error(`[twin] ERROR: ${String(e?.message ?? e).split('\n')[0].slice(0, 400)}`);
  console.error(e);
  process.exit(1);
});
