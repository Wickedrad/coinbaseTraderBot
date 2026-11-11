import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { acquireAtlasTv, closedTvRows, tvAtlasPlan, tvCoverage, TV_ATLAS_SCHEMA,
  type TvPayload, type TvPlan } from '../research/opportunity/tvHistory';
import { readSeries } from '../bot/marketdata/historyStore';
import { buildAtlas } from '../research/opportunity/train';

const MIN = 60_000, DAY = 86_400_000, epoch = Date.UTC(2026, 0, 1);
const through = epoch + 10 * DAY + 4 * MIN, now = through + 30000, from = through - 3 * MIN;
const row = (t: number): number[] => [t, 100, 102, 99, 101, 10];
function payload(plan: TvPlan): TvPayload {
  return { schema: TV_ATLAS_SCHEMA, provider: 'tvdatafeed', clientVersion: 'fixture', clientSource: null,
    series: plan.series.map((r) => ({ id: r.id, error: null, rows: r.tf === '1m'
      ? [from, from + MIN, from + 2 * MIN, through].map(row)
      : [epoch + 8 * DAY, epoch + 9 * DAY, epoch + 10 * DAY].map(row) })) };
}
function temp(): string { return fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-tv-')); }

test('tvdatafeed plan pins venues, supports one-minute spot, and requests both daily dominance series', () => {
  const p = tvAtlasPlan(['BTC', 'ETH']);
  assert.equal(p.bars, 5000);
  assert.deepEqual(p.series.map((r) => [r.exchange, r.symbol, r.tf]), [
    ['COINBASE', 'BTCUSD', '1m'], ['COINBASE', 'ETHUSD', '1m'], ['CRYPTOCAP', 'BTC.D', '1d'], ['CRYPTOCAP', 'USDT.D', '1d'],
  ]);
  assert.ok(p.series.every((r) => r.source === 'tradingview' || r.source.startsWith('tvdatafeed-')));
  assert.throws(() => tvAtlasPlan(['BTC'], 'COINBASE', 'USD', 5001), /pagination/);
  assert.throws(() => tvAtlasPlan(['BTC', 'BTC']), /unique/);
  assert.throws(() => tvAtlasPlan(['../BTC']), /symbols/);
});

test('coverage reports boundary holes and interior gaps without filling prices or looping over missing minutes', () => {
  const cs = [row(2 * MIN), row(4 * MIN)].map(([ts, o, h, l, c, v]) => ({ ts, o, h, l, c, v }));
  const c = tvCoverage(cs, '1m', MIN, 6 * MIN);
  assert.equal(c.expectedBars, 5); assert.equal(c.presentBars, 2); assert.equal(c.missingBars, 3);
  assert.equal(c.gapCount, 3); assert.equal(c.ready, false);
  assert.equal(c.gaps[1].from, new Date(3 * MIN).toISOString());
  const ancient = tvCoverage(cs, '1m', 0, 100000000 * MIN);
  assert.equal(ancient.missingBars, 99999998);
  assert.throws(() => tvCoverage(cs.reverse(), '1m', MIN, 6 * MIN), /increasing/);
});

test('only completed, valid, aligned candles can be imported', () => {
  const request = tvAtlasPlan(['BTC']).series[0];
  const r = closedTvRows([row(from), row(through)], request, now);
  assert.equal(r.candles.length, 1); assert.equal(r.formingBarsExcluded, 1);
  assert.throws(() => closedTvRows([row(from), row(from)], request, now), /unordered/);
  assert.throws(() => closedTvRows([row(from + 1)], request, now), /misaligned/);
  assert.throws(() => closedTvRows([[from, 100, 90, 99, 101, 0]], request, now), /OHLC/);
  assert.throws(() => closedTvRows([[from, 100, 102, 99, 101, null]], request, now), /volume/);
  const daily = tvAtlasPlan(['BTC']).series[1];
  const index = closedTvRows([[epoch + 8 * DAY, 100, 102, 99, 101, null]], daily, now);
  assert.equal(index.unknownVolumeBars, 1); assert.equal(index.candles[0].v, 0);
});

test('acquisition persists exact provider provenance, completed bars and repeatable per-series stores', async () => {
  const out = temp();
  try {
    const options = { out, assets: ['BTC', 'ETH'], now, from, through };
    const r = await acquireAtlasTv(options, async (plan) => payload(plan));
    assert.equal(r.ready, true); assert.equal(r.series.length, 4);
    assert.ok(r.series.every((s) => s.formingBarsExcluded === 1 && s.coverage.ready));
    const bytes = fs.readFileSync(r.rawFile);
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), r.rawSha256);
    const snapshot = fs.readFileSync(r.series[0].file, 'utf8');
    const repeat = await acquireAtlasTv(options, async (plan) => payload(plan));
    assert.equal(repeat.ready, true); assert.equal(fs.readFileSync(r.series[0].file, 'utf8'), snapshot);
    assert.equal(readSeries(r.series[0].file).length, 3);
    const proof = JSON.parse(fs.readFileSync(`${r.series[0].file}.provenance.json`, 'utf8'));
    assert.equal(proof.provider, 'tvdatafeed'); assert.equal(proof.request.symbol, 'BTCUSD');
    assert.equal(proof.lastReceipt, r.rawFile);
    assert.ok(readSeries(r.series[2].file).every((c) => c.ts + DAY <= now));
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test('limited minute history cannot be reported as coverage of a 2017 request', async () => {
  const out = temp();
  try {
    const r = await acquireAtlasTv({ out, assets: ['BTC'], now, from: Date.UTC(2017, 7, 17), through }, async (p) => payload(p));
    assert.equal(r.ready, false);
    assert.ok(r.series[0].coverage.missingBars > 4000000);
    assert.equal(r.series[0].coverage.firstStored, new Date(from).toISOString());
    assert.ok(r.series.every((s) => s.request.source !== 'binance-1m'));
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test('partial/no-data responses report incomplete coverage without alternate symbol/provider requests', async () => {
  const out = temp(); let calls = 0;
  try {
    const r = await acquireAtlasTv({ out, assets: ['BTC'], now, from, through }, async (p) => {
      calls++; const data = payload(p); data.series[0] = { id: 'BTC:1m', error: 'no data', rows: [] }; return data;
    });
    assert.equal(calls, 1); assert.equal(r.ready, false);
    assert.match(r.series[0].error!, /no data/);
    assert.equal(fs.existsSync(r.series[0].file), false);
    assert.equal(r.series[1].coverage.ready, true, 'independent daily acquisition remains useful');
    assert.equal(JSON.parse(fs.readFileSync(path.join(out, 'tvdatafeed-coverage.json'), 'utf8')).ready, false);
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test('pre-existing files with unknown providers or modified contents are left untouched', async () => {
  const out = temp();
  try {
    const options = { out, assets: ['BTC'], now, from, through };
    const r = await acquireAtlasTv(options, async (p) => payload(p));
    const file = r.series[0].file, text = fs.readFileSync(file, 'utf8');
    fs.unlinkSync(`${file}.provenance.json`);
    const unknown = await acquireAtlasTv(options, async (p) => payload(p));
    assert.equal(unknown.ready, false); assert.match(unknown.series[0].error!, /lacks tvdatafeed provenance/);
    assert.equal(fs.readFileSync(file, 'utf8'), text);
    fs.unlinkSync(file);
    await acquireAtlasTv(options, async (p) => payload(p));
    fs.appendFileSync(file, 'tampered\n');
    const bad = await acquireAtlasTv(options, async (p) => payload(p));
    assert.match(bad.series[0].error!, /content provenance mismatch/);
    assert.ok(fs.readFileSync(file, 'utf8').endsWith('tampered\n'));
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test('a venue/quote identity change cannot splice a different symbol into an existing series', async () => {
  const out = temp();
  try {
    const options = { out, assets: ['BTC'], now, from, through };
    const r = await acquireAtlasTv(options, async (p) => payload(p));
    const text = fs.readFileSync(r.series[0].file, 'utf8');
    const other = await acquireAtlasTv({ ...options, quote: 'USDT' }, async (p) => payload(p));
    assert.equal(other.ready, false); assert.match(other.series[0].error!, /symbol/);
    assert.equal(fs.readFileSync(r.series[0].file, 'utf8'), text);
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test('unexpected response identities fail before writing any acquisition data', async () => {
  const out = temp();
  try {
    await assert.rejects(acquireAtlasTv({ out, assets: ['BTC'], now, from, through }, async (p) => {
      const data = payload(p); data.series[0].id = '../../other'; return data;
    }), /identities/);
    assert.deepEqual(fs.readdirSync(out), []);
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test('the atlas refuses tvdatafeed-named files whose provenance is missing or no longer matches', async () => {
  const out = temp();
  try {
    const r = await acquireAtlasTv({ out, assets: ['BTC'], now, from, through }, async (p) => payload(p));
    fs.appendFileSync(r.series[0].file, 'modified\n');
    await assert.rejects(buildAtlas({ historyDir: out, source: 'tvdatafeed-coinbase', assets: ['BTC'],
      trainBefore: from + MIN, finalFrom: through - MIN }), /hash mismatch/);
    fs.unlinkSync(`${r.series[0].file}.provenance.json`);
    await assert.rejects(buildAtlas({ historyDir: out, source: 'tvdatafeed-coinbase', assets: ['BTC'],
      trainBefore: from + MIN, finalFrom: through - MIN }), /ENOENT/);
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test('tvdatafeed store feeds the atlas without relabeling provider provenance or requiring other sources', async () => {
  const out = temp();
  const products = temp();
  try {
    const end = epoch + 10 * DAY, start = end - 1600 * MIN;
    await acquireAtlasTv({ out, assets: ['BTC'], now: end + 1, from: start, through: end }, async (p) => {
      const data = payload(p);
      data.series[0].rows = Array.from({ length: 1600 }, (_, i) => row(start + i * MIN));
      for (const series of data.series.slice(1)) series.rows = [6, 7, 8, 9].map((d) => row(epoch + d * DAY));
      return data;
    });
    const reports = await buildAtlas({ historyDir: out, source: 'tvdatafeed-coinbase', assets: ['BTC'],
      trainBefore: end - 700 * MIN, finalFrom: end - 300 * MIN });
    assert.equal(reports[0].data!.source, 'tvdatafeed-coinbase');
    assert.ok(reports[0].data!.candidates > 0);
    assert.ok(reports[0].horizons[0].train > 0);
    assert.ok(reports[0].horizons[0].fit.groups.find(([g]) => g === 'dominance')![1].length > 0);
    const report = path.join(products, 'report.json'), labels = path.join(products, 'labels.jsonl');
    const cli = spawnSync(process.execPath, ['--import', 'tsx', 'research/opportunity/train.ts', '--history', out,
      '--assets', 'BTC', '--train-before', new Date(end - 700 * MIN).toISOString(),
      '--final-from', new Date(end - 300 * MIN).toISOString(), '--out', report, '--path-labels', labels,
      '--path-targets-atr', '1', '--path-stops-atr', '1'], { encoding: 'utf8', timeout: 30000 });
    assert.equal(cli.status, 0, cli.stderr);
    const saved = JSON.parse(fs.readFileSync(report, 'utf8'));
    assert.equal(saved.assets[0].data.source, 'tvdatafeed-coinbase');
    assert.equal(saved.assets[0].data.provenance.provider, 'tvdatafeed');
    const metadata = JSON.parse(fs.readFileSync(labels, 'utf8').split('\n')[0]);
    assert.equal(metadata.config.source, 'tvdatafeed-coinbase');
  } finally { fs.rmSync(out, { recursive: true, force: true }); fs.rmSync(products, { recursive: true, force: true }); }
});

test('Python bridge uses the exact requested symbol/interval and exports UTC stamps without TradingView access', () => {
  // This checks the bridge itself using a tiny fake tvdatafeed API, not a substitute
  // for the separately attempted real network acquisition.
  const script = `
import sys, types, io, json, runpy, datetime, importlib.metadata
class Frame:
    empty=False
    def __len__(self): return 1
    def __contains__(self,key): return key=='symbol'
    def __getitem__(self,key): return ['COINBASE:BTCUSD']
    def iterrows(self): return iter([(datetime.datetime(2026,1,1,tzinfo=datetime.timezone.utc),{'open':100,'high':102,'low':99,'close':101,'volume':10})])
class TV:
    def __init__(self,*args,**kwargs): assert not args and not kwargs
    def get_hist(self,**kwargs):
        assert kwargs=={'symbol':'BTCUSD','exchange':'COINBASE','interval':'1','n_bars':3}
        return Frame()
class Dist:
    version='fixture'
    def read_text(self,name): return '{}'
importlib.metadata.distribution=lambda name:Dist()
sys.modules['tvDatafeed']=types.SimpleNamespace(TvDatafeed=TV,Interval=types.SimpleNamespace(in_1_minute='1',in_daily='D'))
sys.stdin=io.StringIO(json.dumps({'bars':3,'series':[{'id':'BTC:1m','symbol':'BTCUSD','exchange':'COINBASE','tf':'1m'}]}))
runpy.run_path('research/opportunity/tvFetch.py',run_name='__main__')
`;
  const r = spawnSync('python3', ['-c', script], { encoding: 'utf8', timeout: 10000 });
  assert.equal(r.status, 0, r.stderr);
  const p = JSON.parse(r.stdout) as TvPayload;
  assert.equal(p.provider, 'tvdatafeed'); assert.equal(p.series[0].rows[0][0], epoch);
  assert.equal(p.series[0].error, null);
});
