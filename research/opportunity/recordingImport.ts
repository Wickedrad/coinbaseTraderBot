/** Converts existing bot recordings into causal contract-study inputs, without replay bridges. */
import fs from 'node:fs';
import path from 'node:path';
import { recordingFiles } from '../../bot/marketdata/recordingFiles';
import { OrderBook } from '../../bot/marketdata/orderBook';
import { IndexTracker } from '../../bot/marketdata/indexTracker';
import { marketClockFeatures, sessionAt } from '../../bot/model/sessions';
import type { Candle } from '../../bot/ta/indicators';
import { readRecordings, type RecMarket } from '../replay';
import { CausalAtlasFeatures, type FeatureGroup } from './features';
import { FROZEN_FINAL_FROM, PATH_ASSETS, sha256File } from './jointPathData';
import { digest, stamp, validateEvent, type OfficialPrint, type TimelyMoveDefinition } from './contractDataset';
import type { AssemblySpec, RecordedDecision } from './productCli';
import type { AtlasSnnState } from './snnState';
import { validateSnnState } from './snnState';
import type { ContractTerms } from '../../bot/model/fairValue';
import { isRangeTicker } from '../../bot/model/fairValue';
import { studyPolicy } from './studyPolicy';
import { RecordedMarketContext } from './recordingContext';

export interface RecordingImportOptions {
  studyPolicyId?: string;
  assets: string[]; events: TimelyMoveDefinition[]; everyMs: number; executionBufferMs: number;
  fromDay?: string; toDay?: string; maximumDecisions?: number;
  /** Predetermined sampling across a long archive, independent of labels/detector signals. */
  sampleEveryMs?: number; maximumContractsPerAsset?: number;
  /** Study actual full snapshots at arrival; never reconstruct economics from deltas. */
  snapshotDecisionsOnly?: boolean;
  maximumDecisionsPerDay?: number;
  costs: { entryFee: number; exitFee: number; settlementFee: number; slippage: number };
  /** Optional states produced by snn-replay, in time order, from one variant only. */
  snnStates?: AtlasSnnState[];
}
/** Writes into a caller-owned NEW staging directory. The CLI commits it atomically. */
export async function writeRecordingInputs(dir: string, staging: string, options: RecordingImportOptions) {
  const policy = studyPolicy(options.studyPolicyId);
  if (!options.assets.length || options.assets.some((a) => !PATH_ASSETS.includes(a)) || !options.events.length ||
      !Number.isSafeInteger(options.everyMs) || options.everyMs < 1000 || !Number.isSafeInteger(options.executionBufferMs) || options.executionBufferMs < 0 ||
      !Object.values(options.costs).every((v) => Number.isFinite(v) && v >= 0) ||
      (options.sampleEveryMs !== undefined && (!Number.isSafeInteger(options.sampleEveryMs) || options.sampleEveryMs < 1000)) ||
      (options.maximumContractsPerAsset !== undefined && (!Number.isInteger(options.maximumContractsPerAsset) || options.maximumContractsPerAsset < 1 || options.maximumContractsPerAsset > 100)) ||
      (options.maximumDecisionsPerDay !== undefined && (!Number.isInteger(options.maximumDecisionsPerDay) || options.maximumDecisionsPerDay < 1 || options.maximumDecisionsPerDay > 20000)) ||
      (options.maximumDecisions !== undefined && (!Number.isInteger(options.maximumDecisions) || options.maximumDecisions < 1 || options.maximumDecisions > 20000))) throw new Error('invalid recording import policy');
  options.events.forEach(validateEvent);
  const files = recordingFiles(dir).filter((f) => (!options.fromDay || f.day >= options.fromDay) && (!options.toDay || f.day <= options.toDay));
  if (!files.length) throw new Error('no recordings in requested dates');
  const inputs: Record<string, string> = {};
  for (const f of files) inputs[fs.realpathSync(f.file)] = await sha256File(f.file);
  const combinedHash = digest(inputs), states = options.snnStates ?? [], context = new RecordedMarketContext(combinedHash);
  for (let i = 0; i < states.length; i++) {
    validateSnnState(states[i], states[i].asOf);
    if (i && (states[i].asOf < states[i - 1].asOf || states[i].version !== states[0].version || states[i].provenance.variant !== states[0].provenance.variant)) throw new Error('incompatible or unordered imported SNN states');
  }
  let stateIndex = -1, latestState: AtlasSnnState | null = null;
  const providers = new Map(options.assets.map((asset) => [asset, new CausalAtlasFeatures(asset, { source: 'observed-recording-1m-candles', sha256: combinedHash })]));
  const minutes = new Map<string, number>(), arrivals = new Map<string, number>(), markets = new Map<string, RecMarket & { knownAt: number }>();
  const books = new Map<string, OrderBook>(), trackers = new Map<string, IndexTracker>();
  const previousPrint = new Map<string, OfficialPrint>(), printFiles = new Map<string, { file: string; fd: number; rows: number }>();
  for (const asset of options.assets) {
    const file = `index-${asset}.jsonl`; printFiles.set(asset, { file, fd: fs.openSync(path.join(staging, file), 'wx'), rows: 0 });
  }
  const bookKnownAt = new Map<string, number>(), lastDecision = new Map<string, number>();
  const snapshotIntact = new Map<string, boolean>();
  const counts = { events: 0, decisions: 0, proxyOrSyntheticSkipped: 0, formingCandlesSkipped: 0,
    staleOrMissingState: 0, lateIndexDropped: 0, finalResultsWithheld: 0, rangeKindCanonicalized: 0 };
  const decisionsFile = path.join(staging, 'decisions.jsonl'), resultsFile = path.join(staging, 'results.jsonl');
  const decisionsFd = fs.openSync(decisionsFile, 'wx'), resultsFd = fs.openSync(resultsFile, 'wx');
  const snapshotFd = options.snapshotDecisionsOnly ? fs.openSync(path.join(staging, 'snapshots.jsonl'), 'wx') : undefined;
  let lastAt = 0, stoppedEarly = false, selectedThrough = 0, lastAttemptAt = -Infinity;
  const allEventsNeedAnchor = options.events.every((event) => event.thresholdAtr || event.priorDriftAtr);
  const reported = new Map<string, string>();
  const lastAssetSample = new Map<string, number>();
  const decisionsByDay = new Map<string, number>();
  const termsAt = (m: RecMarket & { knownAt: number }, at: number): { terms: ContractTerms; knownAt: number; basis: 'recorded-contract' | 'computed-opening-index' } | null => {
    if (m.kind === 'updown') {
      if (m.strike && m.knownAt >= m.openTime) return { terms: { kind: 'updown', strike: m.strike }, knownAt: m.knownAt, basis: 'recorded-contract' };
      const avg = trackers.get(m.asset)?.settlement(m.openTime, m.openTime);
      return avg?.n === 60 ? { terms: { kind: 'updown', strike: avg.avg }, knownAt: at, basis: 'computed-opening-index' } : null;
    }
    if (m.kind === 'greater' && m.strike) return { terms: { kind: 'greater', strike: m.strike }, knownAt: m.knownAt, basis: 'recorded-contract' };
    if (m.kind === 'less' && m.cap) return { terms: { kind: 'less', cap: m.cap }, knownAt: m.knownAt, basis: 'recorded-contract' };
    if (m.kind === 'between' && m.strike && m.cap) return { terms: { kind: 'between', strike: m.strike, cap: m.cap }, knownAt: m.knownAt, basis: 'recorded-contract' };
    return null;
  };
  try {
    for await (const e of readRecordings(dir, '', options.fromDay, options.toDay, (k) =>
      (options.snapshotDecisionsOnly ? ['market', 'index', 'candles', 'book', 'gap', 'perp', 'dominance'] : ['market', 'index', 'candles', 'book', 'delta', 'result', 'gap', 'perp', 'dominance']).includes(k))) {
      if (!stamp(e.t) || e.t < lastAt) throw new Error('recording arrival timestamps are not ordered');
      lastAt = e.t; counts.events++;
      if (stoppedEarly && e.t > selectedThrough + 300000) break;
      if (e.hist || e.synth) { counts.proxyOrSyntheticSkipped++; continue; }
      context.observe(e);
      if (e.k === 'market' && options.assets.includes(e.asset) && ['updown', 'greater', 'between', 'less'].includes(e.kind)) {
        // Older recordings label some B-range tickers as greater. Reuse ReplayState's
        // venue ontology, requiring the actual recorded bounds in termsAt below.
        const kind = isRangeTicker(e.ticker) ? 'between' : e.kind;
        if (kind !== e.kind) counts.rangeKindCanonicalized++;
        markets.set(e.ticker, { ticker: e.ticker, asset: e.asset, series: e.series, kind, openTime: e.openTime,
          closeTime: e.closeTime, strike: e.strike, cap: e.cap, tickSize: e.tickSize ?? 0.01, knownAt: e.t });
      } else if (e.k === 'index' && options.assets.includes(e.asset)) {
        if (e.src !== 'kalshi') { counts.proxyOrSyntheticSkipped++; continue; }
        const ts = e.ts ?? e.t, previous = previousPrint.get(e.asset);
        if (!stamp(ts) || ts > e.t || !Number.isFinite(e.value) || e.value <= 0) throw new Error('invalid observed index clock/value');
        if (previous && ts === previous.ts && e.value !== previous.value) throw new Error('conflicting observed index correction needs audit');
        if (previous && ts <= previous.ts) { counts.lateIndexDropped++; continue; }
        const print = { ts, knownAt: e.t, value: e.value }, stream = printFiles.get(e.asset)!;
        previousPrint.set(e.asset, print); fs.writeSync(stream.fd, JSON.stringify(print) + '\n'); stream.rows++;
        if (!trackers.has(e.asset)) trackers.set(e.asset, new IndexTracker(e.asset, 2 * 3600000));
        trackers.get(e.asset)!.add(e.value, ts);
      } else if (e.k === 'candles' && e.tf === '1m' && providers.has(e.asset)) {
        // Native Coinbase recorder rows use seconds and [time, low, high, open, close,
        // volume, optional taker-buy volume], unlike the historical CSV's Candle objects.
        const rows = (e.rows ?? []).map((r: Candle | number[]): Candle => Array.isArray(r)
          ? { ts: r[0] * 1000, o: r[3], h: r[2], l: r[1], c: r[4], v: r[5], ...(r.length === 7 ? { tb: r[6] } : {}) }
          : r) as Candle[];
        rows.sort((a, b) => a.ts - b.ts);
        for (const bar of rows) {
          if (bar.ts + 60000 > e.t) { counts.formingCandlesSkipped++; continue; }
          if (bar.ts <= (minutes.get(e.asset) ?? -1)) continue;
          providers.get(e.asset)!.push(bar); minutes.set(e.asset, bar.ts); arrivals.set(e.asset, e.t);
        }
      } else if (e.k === 'book' || e.k === 'delta') {
        if (!markets.has(e.ticker)) continue;
        if (e.k === 'book') {
          let b = books.get(e.ticker); if (!b) { b = new OrderBook(e.ticker); books.set(e.ticker, b); }
          b.applySnapshot({ bids: e.bids ?? [], asks: e.asks ?? [] }, e.t); snapshotIntact.set(e.ticker, true);
        } else snapshotIntact.set(e.ticker, false);
        bookKnownAt.set(e.ticker, e.t);
      } else if (e.k === 'gap') {
        for (const b of books.values()) b.invalidate();
      } else if (e.k === 'result') {
        if (e.t >= policy.finalFrom) { counts.finalResultsWithheld++; continue; }
        if (e.result === 'yes' || e.result === 'no') {
          if (reported.has(e.ticker) && reported.get(e.ticker) !== e.result) throw new Error('conflicting recorded settlement result');
          if (!reported.has(e.ticker)) fs.writeSync(resultsFd, JSON.stringify({ ticker: e.ticker, yes: e.result === 'yes', knownAt: e.t }) + '\n');
          reported.set(e.ticker, e.result);
        }
      }
      if (snapshotFd !== undefined && e.k === 'book') {
        const m = markets.get(e.ticker), terms = m && termsAt(m, e.t);
        if (m && terms && e.t < policy.finalFrom) {
          const idx = trackers.get(m.asset)?.fresh(e.t, 3000);
          fs.writeSync(snapshotFd, JSON.stringify({ contract: { ticker: m.ticker, asset: m.asset, openTime: m.openTime, closeTime: m.closeTime,
            termsKnownAt: terms.knownAt, terms: terms.terms, settlementReference: `CF-RTI:${m.asset}:kalshi` },
            quote: { ticker: m.ticker, at: e.t, knownAt: e.t, sourceSha256: combinedHash, bids: e.bids ?? [], asks: e.asks ?? [],
              ...(idx ? { underlying: { price: idx.value, knownAt: e.t } } : {}) } }) + '\n');
        }
      }
      if (e.tie || e.k === 'skip') continue;
      // Deltas make snapshots unusable for economic evidence; rebuilding a partial
      // book cannot improve that evidence. All deltas remain in the original input
      // for the separate native SNN replay. Only actual input arrivals or a fresh
      // snapshot can trigger a sampled observation; bound attempts to 1 Hz.
      if (!['market', 'index', 'candles', 'book', 'perp', 'dominance'].includes(e.k)) continue;
      if (options.snapshotDecisionsOnly && e.k !== 'book') continue;
      if (e.k !== 'book' && e.t - lastAttemptAt < 1000) continue;
      lastAttemptAt = e.t;
      while (stateIndex + 1 < states.length && states[stateIndex + 1].asOf <= e.t) latestState = states[++stateIndex];
      const sampleEveryMs = options.sampleEveryMs ?? 0;
      if (sampleEveryMs && options.assets.every((asset) => e.t - (lastAssetSample.get(asset) ?? 0) < sampleEveryMs)) continue;
      const sampled = new Set<string>(), contractsPerAsset = new Map<string, number>();
      // Sampling across ladder strikes uses only current index distance, never subsequent outcomes.
      const byDistance = [...markets.values()].sort((a, b) => {
        const distance = (m: RecMarket) => { const price = trackers.get(m.asset)?.latest()?.value; const strike = m.strike ?? m.cap;
          return price && strike ? Math.abs(Math.log(price / strike)) : Infinity; };
        return distance(a) - distance(b) || a.ticker.localeCompare(b.ticker);
      });
      const geometryRanks = new Map<string, number>();
      const orderedMarkets = byDistance.map((m) => {
        const key = `${m.asset}:${m.kind}:${m.closeTime - m.openTime}`, rank = geometryRanks.get(key) ?? 0;
        geometryRanks.set(key, rank + 1); return { m, rank };
      }).sort((a, b) => a.rank - b.rank).map((x) => x.m);
      for (const m of orderedMarkets) {
        if (m.closeTime <= e.t) { markets.delete(m.ticker); books.delete(m.ticker); bookKnownAt.delete(m.ticker); snapshotIntact.delete(m.ticker); lastDecision.delete(m.ticker); continue; }
        if (stoppedEarly) continue;
        if (options.snapshotDecisionsOnly && m.ticker !== e.ticker) continue;
        if (options.snapshotDecisionsOnly && !['updown', 'greater', 'less'].includes(m.kind)) continue;
        const day = new Date(e.t).toISOString().slice(0, 10);
        if ((decisionsByDay.get(day) ?? 0) >= (options.maximumDecisionsPerDay ?? Infinity)) continue;
        if (options.sampleEveryMs && e.t - (lastAssetSample.get(m.asset) ?? 0) < options.sampleEveryMs) continue;
        if ((contractsPerAsset.get(m.asset) ?? 0) >= (options.maximumContractsPerAsset ?? 100)) continue;
        if (m.openTime > e.t || m.closeTime - options.executionBufferMs <= e.t || m.closeTime - e.t > 86400000 ||
            e.t - (lastDecision.get(m.ticker) ?? 0) < options.everyMs) continue;
        const idx = trackers.get(m.asset)?.fresh(e.t, 3000), minute = minutes.get(m.asset), terms = termsAt(m, e.t);
        if (!idx || minute === undefined || minute + 60000 > e.t || e.t - (minute + 60000) > 60000 || !terms) { counts.staleOrMissingState++; continue; }
        const provider = providers.get(m.asset)!, anchor = provider.entryAnchor();
        if (allEventsNeedAnchor && !anchor?.atrBps) continue;
        const baseFrame = provider.snapshot(), arrival = arrivals.get(m.asset)!;
        const groups: Record<string, Readonly<FeatureGroup>> = Object.fromEntries(Object.entries(baseFrame.groups).map(([key, g]) => [key,
          { ...g, knownAt: g.knownAt === null ? null : Math.max(g.knownAt, arrival), timing: 'completed observed bars, available no earlier than recorded arrival' }]));
        groups.clock = { ...baseFrame.groups.clock, knownAt: e.t, values: marketClockFeatures(e.t), timing: 'deterministic clock at actual recorded decision arrival' };
        const btcTracker = trackers.get('BTC'), assetTracker = trackers.get(m.asset);
        const btcSeries = btcTracker?.fresh(e.t, 3000) ? btcTracker.series(e.t, 60, 3000) : undefined;
        const assetSeries = assetTracker?.series(e.t, 60, 3000);
        const btcReturn = btcSeries ? Math.log(btcSeries.at(-1)! / btcSeries[0]) : null;
        const assetReturn = assetSeries ? Math.log(assetSeries.at(-1)! / assetSeries[0]) : null;
        groups.cross_asset = { source: 'observed-Kalshi-RTI-cross-asset', sha256: combinedHash, timeframe: 'micro',
          status: btcReturn === null ? 'warming' : 'ready', bars: btcSeries?.length ?? 0, firstOpen: null, lastOpen: null,
          knownAt: e.t, publicationLagMs: 0, timing: 'causal observed one-second index marks; unavailable gaps remain null',
          values: { btc_log_return_60s: btcReturn, relative_to_btc_60s: btcReturn === null || assetReturn === null ? null : assetReturn - btcReturn } };
        Object.assign(groups, context.at(m.asset, e.t, idx.value));
        const frame = { ...baseFrame, decisionAt: e.t, session: sessionAt(e.t), groups };
        // Existing recordings do not reliably persist every websocket gap/sequence event.
        // Use a fresh observed snapshot for economic evidence, never assume replayed deltas stayed intact.
        const book = books.get(m.ticker), validBook = snapshotIntact.get(m.ticker) && book?.isUsable(e.t, 2000), bid = validBook ? book!.bestBid() : undefined, ask = validBook ? book!.bestAsk() : undefined;
        const snn = latestState && e.t - latestState.stateAt <= 2000 ? { ...latestState, asOf: e.t } : null;
        lastDecision.set(m.ticker, e.t);
        let written = false;
        writeDecisions: for (const event of options.events) for (const side of (options.snapshotDecisionsOnly ? ['yes'] : ['yes', 'no']) as Array<'yes' | 'no'>) {
          if ((event.thresholdAtr || event.priorDriftAtr) && !anchor?.atrBps) continue;
          const d: RecordedDecision = { frame, anchor: anchor ? { ...anchor, knownAt: Math.max(anchor.knownAt, arrival) } : null,
            contract: { ticker: m.ticker, asset: m.asset, openTime: m.openTime, closeTime: m.closeTime, termsKnownAt: terms.knownAt,
              terms: terms.terms, settlementReference: `CF-RTI:${m.asset}:kalshi`, averagingSec: 60 }, event, side,
            executionBufferMs: options.executionBufferMs, asOf: e.t, snn, termsBasis: terms.basis };
          if (validBook && (bid || ask)) d.quote = { ticker: m.ticker, side, at: bookKnownAt.get(m.ticker)!, knownAt: bookKnownAt.get(m.ticker)!,
            bid: side === 'yes' ? bid?.price ?? null : ask ? 1 - ask.price : null,
            ask: side === 'yes' ? ask?.price ?? null : bid ? 1 - bid.price : null,
            bidSize: Math.floor((side === 'yes' ? bid : ask)?.size ?? 0), askSize: Math.floor((side === 'yes' ? ask : bid)?.size ?? 0),
            ...options.costs, sourceSha256: combinedHash };
          fs.writeSync(decisionsFd, JSON.stringify(d) + '\n'); counts.decisions++;
          decisionsByDay.set(day, (decisionsByDay.get(day) ?? 0) + 1);
          written = true;
          selectedThrough = Math.max(selectedThrough, m.closeTime);
          if (counts.decisions >= (options.maximumDecisions ?? 20000)) { stoppedEarly = true; break writeDecisions; }
          if ((decisionsByDay.get(day) ?? 0) >= (options.maximumDecisionsPerDay ?? Infinity)) break writeDecisions;
        }
        if (written) { sampled.add(m.asset); contractsPerAsset.set(m.asset, (contractsPerAsset.get(m.asset) ?? 0) + 1); }
        if (stoppedEarly) break;
      }
      // Continue index/result collection through the last selected contract's close; a row cap
      // must not truncate a selected label's future evidence. Further decisions are disabled.
      for (const asset of sampled) lastAssetSample.set(asset, e.t);
    }
  } finally { fs.closeSync(decisionsFd); fs.closeSync(resultsFd); if (snapshotFd !== undefined) fs.closeSync(snapshotFd); for (const stream of printFiles.values()) fs.closeSync(stream.fd); }
  const indices: AssemblySpec['indices'] = [];
  for (const [asset, stream] of printFiles) if (stream.rows) {
    const name = stream.file, file = path.join(staging, name);
    indices.push({ file: name, sha256: await sha256File(file), asset, reference: `CF-RTI:${asset}:kalshi`, basis: 'observed-index' });
  }
  if (!indices.length) throw new Error('no observed Kalshi index prints; proxy/synthetic data cannot satisfy contract labels');
  for (const [file, hash] of Object.entries(inputs)) if (await sha256File(file) !== hash) throw new Error('recording changed during import');
  const spec: AssemblySpec = { schema: 'opportunity-recording-spec-v1', studyPolicyId: policy.id, knownBy: lastAt, indices,
    decisions: { file: 'decisions.jsonl', sha256: await sha256File(decisionsFile) }, results: { file: 'results.jsonl', sha256: await sha256File(resultsFile) } };
  fs.writeFileSync(path.join(staging, 'spec.json'), JSON.stringify(spec, null, 2) + '\n');
  const report = { counts, inputHashes: inputs, aggregateSha256: combinedHash, stoppedEarly,
    sampling: { decisionAttemptIntervalMs: 1000, freshSnapshotsMayTriggerImmediately: true,
      sampleEveryMs: options.sampleEveryMs ?? 0, snapshotOnlyEconomicEvidence: true, snapshotDecisionsOnly: options.snapshotDecisionsOnly ?? false },
    decisionsByDay: Object.fromEntries(decisionsByDay),
    ...(snapshotFd !== undefined ? { snapshots: { file: 'snapshots.jsonl', sha256: await sha256File(path.join(staging, 'snapshots.jsonl')) } } : {}),
    limitations: ['Historical candle provider identity remains whatever the recording establishes; no provider fallback or relabeling',
      'No reconstructed price bridges or minute-derived ticks', 'Missing daily context remains absent',
      'The existing recording reader tolerates torn lines; sampled path gaps still fail closed',
      'Quoted costs are explicit import assumptions, not measured fills; final outcomes remain withheld under the registered study policy'] };
  fs.writeFileSync(path.join(staging, 'import-report.json'), JSON.stringify(report, null, 2) + '\n'); return report;
}
