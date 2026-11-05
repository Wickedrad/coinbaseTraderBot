// Checks bot/model/regimeV1.ts against the regime.py v1 fixture (meta plan thread): feeds Binance 1m closes
// (<dir>/<ASSET>/1m.csv, rows ts,o,h,l,c,...) and compares rv60/q33/q67/tercile/z60 row by row.
//   node --import tsx research/regimeMatch.ts <binance-1m dir> <fixture.csv>
import fs from 'fs';
import { RegimeV1 } from '../bot/model/regimeV1';

const [dir, fixture] = process.argv.slice(2);
const rows = fs.readFileSync(fixture, 'utf8').trim().split('\n').slice(1).map((l) => l.split(','));
const assets = [...new Set(rows.map((r) => r[1]))];
const first = Math.min(...rows.map((r) => Date.parse(r[0])));
const last = Math.max(...rows.map((r) => Date.parse(r[0])));
const from = Math.floor(first / 86_400_000) * 86_400_000 - 32 * 86_400_000;
const reg = new RegimeV1();
const want = new Map<string, string[]>();
for (const r of rows) want.set(`${r[1]}|${Date.parse(r[0])}`, r);
let n = 0, bad = 0, maxRel = 0;
const rel = (a: string, b: number) => { if (a === '' && Number.isNaN(b)) return 0; if (a === '' || Number.isNaN(b)) return Infinity; const x = +a; return Math.abs(x - b) / Math.max(1e-300, Math.abs(x)); };
for (const asset of assets) {
  const lines = fs.readFileSync(`${dir}/${asset}/1m.csv`, 'utf8').split('\n');
  const bars: Array<[number, number]> = [];
  for (const l of lines) { if (!l || l.startsWith('ts')) continue; const f = l.split(','); let ts = +f[0]; const c = +f[4]; if (!(ts > 0) || !(c > 0)) continue; if (ts < 1e11) ts *= 1000; ts -= ts % 60_000; if (ts >= from && ts <= last) bars.push([ts, c]); }
  bars.sort((a, b) => a[0] - b[0]);
  // Label minute t before the bar opened at t is fed (it uses bars opened at t-1 and earlier).
  let i = 0;
  for (let t = from; t <= last; t += 60_000) {
    while (i < bars.length && bars[i][0] < t) { reg.feedClose(asset, bars[i][0], bars[i][1]); i++; }
    const w = want.get(`${asset}|${t}`);
    if (!w) continue;
    n++;
    const l = reg.label(asset, t);
    const errs = [rel(w[2], l.rv60), rel(w[3], l.q33), rel(w[4], l.q67), rel(w[6], l.z60)];
    const m = Math.max(...errs);
    if (Number.isFinite(m)) maxRel = Math.max(maxRel, m);
    if (m > 1e-9 || w[5] !== l.tercile) { bad++; if (bad <= 15) console.log(`MISMATCH ${w[0]} ${asset} want rv ${w[2]} q ${w[3]}/${w[4]} ${w[5]} z ${w[6]} | got rv ${l.rv60} q ${l.q33}/${l.q67} ${l.tercile} z ${l.z60}`); }
  }
}
console.log(`regime v1 TS vs fixture: ${n} rows compared, ${bad} mismatches, max relative error ${maxRel.toExponential(2)}`);
