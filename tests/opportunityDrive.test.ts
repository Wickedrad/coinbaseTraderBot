import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';

function simulate(tree: Record<string, unknown>, folderId?: string, samples: Record<string, string> = {}) {
  const code = `
import json,sys,runpy
module=runpy.run_path('research/opportunity/driveInventory.py')
tree=json.loads(sys.argv[1]);calls=[];samples=json.loads(sys.argv[3]);reads=[]
def listing(remote,recursive=False,folder_id=None):
    calls.append({'remote':remote,'recursive':recursive,'folder_id':folder_id})
    value=tree.get(remote)
    return (None,'directory not found') if value is None else (None,value) if isinstance(value,str) else (value,None)
def read_sample(remote,tail=False,folder_id=None):
    reads.append({'remote':remote,'tail':tail,'folder_id':folder_id})
    value=samples.get(remote)
    return (value.encode(),None) if value is not None else (None,'sample unavailable')
report=module['inventory'](sys.argv[2] or None,list_fn=listing,probe=bool(samples),read_fn=read_sample)
print(json.dumps({'report':report,'calls':calls,'reads':reads}))
`;
  const r = spawnSync('python3', ['-B', '-c', code, JSON.stringify(tree), folderId ?? '', JSON.stringify(samples)], { encoding: 'utf8', timeout: 10000 });
  assert.equal(r.status, 0, r.stderr);
  return { ...JSON.parse(r.stdout), text: r.stdout };
}
const dir = (Name: string) => ({ Name, IsDir: true });
const file = (Path: string, Size: number) => ({ Path, Name: Path.split('/').at(-1), Size, IsDir: false, ModTime: '2026-11-01T00:00:00Z', Token: 'MUST_NOT_PRINT_THIS' });

test('Drive metadata discovery separates TV minute candidates from native-minute files and skips models/audit', () => {
  const r = simulate({
    'gdrive:kalshi-bot-archive': [dir('raw'), dir('models'), dir('audit')],
    'gdrive:kalshi-bot-archive/raw': [dir('history'), dir('server-history')],
    'gdrive:kalshi-bot-archive/raw/history': [dir('tvspot'), dir('binance-1m'), dir('kalshi')],
    'gdrive:kalshi-bot-archive/raw/history/tvspot': [file('BTC/1m.csv', 123)],
    'gdrive:kalshi-bot-archive/raw/history/binance-1m': [file('BTC/1m.csv', 456)],
    'gdrive:kalshi-bot-archive/raw/server-history': [dir('tradingview')],
    'gdrive:kalshi-bot-archive/raw/server-history/tradingview': [file('BTC.D/1d.csv', 100)],
  });
  const root = r.report.roots[0];
  assert.equal(root.accessible, true); assert.equal(root.files.length, 3);
  assert.deepEqual(root.tv_minute_candidates, ['raw/history/tvspot/BTC/1m.csv']);
  assert.deepEqual(root.other_minute_files, ['raw/history/binance-1m/BTC/1m.csv']);
  assert.ok(r.calls.every((c: { remote: string }) => !/models|audit|kalshi$/.test(c.remote)));
  assert.ok(!r.text.includes('MUST_NOT_PRINT_THIS'));
  assert.ok(root.files.every((f: { provenance_verified: boolean }) => !f.provenance_verified));
});

test('the linked folder is queried with its explicit root id and no wider Drive-root traversal', () => {
  const id = '14aszEScwaC7yGPqGXZ17SoZ8sBTPPs-J';
  const r = simulate({ 'gdrive:': [dir('raw')], 'gdrive:raw': [dir('tvdatafeed-coinbase')],
    'gdrive:raw/tvdatafeed-coinbase': [file('ETH/1m.csv', 234)] }, id);
  assert.equal(r.report.roots[0].accessible, false);
  assert.equal(r.report.roots[1].accessible, true);
  assert.ok(r.calls.filter((c: { remote: string }) => !c.remote.startsWith('gdrive:kalshi-bot-archive')).every((c: { folder_id: string }) => c.folder_id === id));
  assert.deepEqual(r.report.roots[1].tv_minute_candidates, ['raw/tvdatafeed-coinbase/ETH/1m.csv']);
});

test('partial namespace failures remain explicit instead of being described as absent history', () => {
  const r = simulate({ 'gdrive:kalshi-bot-archive': [dir('raw')], 'gdrive:kalshi-bot-archive/raw': [dir('history')],
    'gdrive:kalshi-bot-archive/raw/history': [dir('tradingview')],
    'gdrive:kalshi-bot-archive/raw/history/tradingview': 'HTTP 403' });
  const root = r.report.roots[0];
  assert.equal(root.accessible, true);
  assert.deepEqual(root.errors, [{ path: 'raw/history/tradingview', error: 'HTTP 403' }]);
  assert.deepEqual(root.files, []);
});

test('unknown names and parent-path names cannot redirect discovery outside the authorized archive', () => {
  const r = simulate({ 'gdrive:kalshi-bot-archive': [dir('../escape'), dir('..'), dir('secrets'), dir('raw')],
    'gdrive:kalshi-bot-archive/raw': [] });
  assert.deepEqual(r.calls.map((c: { remote: string }) => c.remote), ['gdrive:kalshi-bot-archive', 'gdrive:kalshi-bot-archive/raw']);
  assert.equal(r.report.roots[0].accessible, true);
  assert.equal(r.report.roots[0].truncated, false);
});

test('Yahoo Finance and other stored history are inventoried without being relabeled as tvdatafeed', () => {
  const r = simulate({
    'gdrive:kalshi-bot-archive': [dir('raw')],
    'gdrive:kalshi-bot-archive/raw': [dir('server-history')],
    'gdrive:kalshi-bot-archive/raw/server-history': [dir('yahoo'), dir('Yahoo Finance'), dir('binance'), dir('coinbase')],
    'gdrive:kalshi-bot-archive/raw/server-history/yahoo': [file('BTC/1d.csv', 222)],
    'gdrive:kalshi-bot-archive/raw/server-history/Yahoo Finance': [file('ETH/1h.csv', 333)],
    'gdrive:kalshi-bot-archive/raw/server-history/binance': [file('BTC/15m.csv', 444)],
    'gdrive:kalshi-bot-archive/raw/server-history/coinbase': [file('ETH/1m.csv', 555)],
  });
  const root = r.report.roots[0];
  assert.equal(root.files.length, 4);
  assert.equal(root.yahoo_layout_files.length, 2);
  assert.deepEqual(root.tv_minute_candidates, []);
  assert.deepEqual(root.other_minute_files, ['raw/server-history/coinbase/ETH/1m.csv']);
  assert.ok(root.files.filter((f: { source_namespace: string }) => /yahoo/i.test(f.source_namespace))
    .every((f: { source_evidence: string }) => f.source_evidence === 'yahoo-layout'));
});

test('CSV probes find actual minute spacing in generic Coinbase filenames and reject misleading minute names', () => {
  const start = Date.UTC(2026, 0, 1);
  const csv = (step: number) => `ts,o,h,l,c,v\n${[0, 1, 2].map((i) => `${start + i * step},100,101,99,100,1`).join('\n')}\n`;
  const r = simulate({
    'gdrive:kalshi-bot-archive': [dir('raw')],
    'gdrive:kalshi-bot-archive/raw': [dir('history')],
    'gdrive:kalshi-bot-archive/raw/history': [dir('coinbase'), dir('binance-1m')],
    'gdrive:kalshi-bot-archive/raw/history/coinbase': [file('BTC/candles.csv', 200)],
    'gdrive:kalshi-bot-archive/raw/history/binance-1m': [file('ETH/1m.csv', 200)],
  }, undefined, {
    'gdrive:kalshi-bot-archive/raw/history/coinbase/BTC/candles.csv': csv(60000),
    'gdrive:kalshi-bot-archive/raw/history/binance-1m/ETH/1m.csv': csv(900000),
  });
  const root = r.report.roots[0];
  assert.deepEqual(root.minute_samples_confirmed, ['raw/history/coinbase/BTC/candles.csv']);
  assert.equal(root.content_probe.incomplete, false);
  const sample = root.files.find((f: { source_namespace: string }) => f.source_namespace === 'coinbase').csv_sample;
  assert.equal(sample.first_open_utc, '2026-01-01T00:00:00Z');
  assert.equal(sample.last_open_utc, '2026-01-01T00:02:00Z');
  assert.equal(sample.full_file_validation, false);
  assert.ok(r.reads.every((read: { remote: string }) => /coinbase|binance-1m/.test(read.remote)));
  assert.ok(!r.text.includes(',100,101,99'));
});

test('broader catalog reports only market archive metadata including tapes and compressed histories', () => {
  const code = `
import json,runpy
m=runpy.run_path('research/opportunity/driveInventory.py')
files=[{'Path':p,'Size':123,'Token':'DO_NOT_PRINT'} for p in ['raw/recordings/2024/index.jsonl','old/history-2017.zip','raw/snn-tape/2024.tape','raw/models/snn.jsonl','raw/history/account.csv','../history/escape.csv','bot.env']]
r=m['catalog'](list_fn=lambda *args: (files,None))
print(json.dumps(r))
`;
  const r = spawnSync('python3', ['-B', '-c', code], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const report = JSON.parse(r.stdout);
  assert.equal(report.contents_read, false);
  assert.deepEqual(report.roots[0].files.map((f: { path: string }) => f.path),
    ['raw/recordings/2024/index.jsonl', 'old/history-2017.zip', 'raw/snn-tape/2024.tape']);
  assert.ok(!r.stdout.includes('DO_NOT_PRINT'));
});

test('scoped discovery checks located laptop archives without broader Drive traversal or credential contents', () => {
  const code = `
import json,runpy
m=runpy.run_path('research/opportunity/driveInventory.py'); calls=[]; reads=[]
root='gdrive:kalshi-bot-archive/raw/laptop-history'
tree={root:[{'Name':'binance-1m','IsDir':True},{'Name':'models','IsDir':True}],root+'/binance-1m':[{'Name':'BTC','IsDir':True}],root+'/binance-1m/BTC':[{'Name':'1m.csv','Size':90000}]}
def listing(remote,recursive=False,folder_id=None):
 calls.append(remote); return (tree.get(remote,[]),None)
def read(remote,tail=False,folder_id=None):
 reads.append(remote); return (b'ts,o,h,l,c,v\\n1502942400000,100,101,99,100,1\\n1502942460000,100,101,99,100,1\\n',None)
r=m['catalog'](scope='raw/laptop-history',list_fn=listing,probe=True,read_fn=read)
try: m['catalog'](scope='../models',list_fn=listing); raise AssertionError('accepted unsafe scope')
except ValueError: pass
print(json.dumps({'report':r,'calls':calls,'reads':reads}))
`;
  const r = spawnSync('python3', ['-B', '-c', code], { encoding: 'utf8' }); assert.equal(r.status, 0, r.stderr);
  const { report, calls, reads } = JSON.parse(r.stdout);
  assert.equal(report.roots[0].accessible, true); assert.equal(report.contents_read, true);
  assert.ok(calls.every((p: string) => p.startsWith('gdrive:kalshi-bot-archive/raw/laptop-history') && !p.includes('models')));
  assert.ok(reads.every((p: string) => p.endsWith('raw/laptop-history/binance-1m/BTC/1m.csv')));
  assert.equal(report.roots[0].files[0].csv_sample.has_60_second_steps, true);
});
