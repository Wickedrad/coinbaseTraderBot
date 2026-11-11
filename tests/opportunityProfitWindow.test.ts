import { test } from 'node:test';
import assert from 'node:assert/strict';
import { oracleProfitWindows, type ProfitWindowBook } from '../research/opportunity/oracleProfitWindow';
import type { EdgeForecast } from '../research/opportunity/oracleEdge';
const t=Date.UTC(2026,10,11);
const f={id:'f',asset:'BTC',publishedAt:t,horizon:15,byAt:t+30000} as EdgeForecast;
function books(gap=false):ProfitWindowBook[]{return [0,5000,10000,15000,20000,25000,30000].filter(ms=>!gap||ms!==10000).map(ms=>({
 contract:{ticker:'T',asset:'BTC',openTime:t-1000,closeTime:t+120000,termsKnownAt:t,terms:{kind:'greater',strike:100},settlementReference:'fixture'},
 quote:{ticker:'T',at:t+ms,knownAt:t+ms,sourceSha256:'a'.repeat(64),bids:[{price:ms===0||ms>=25000?0.39:0.45,size:20}],asks:[{price:ms===0?0.40:0.46,size:20}]},
 fees:{schedule:{takerMultiplier:1,makerMultiplier:0,balancePrecision:0.01},knownAt:t,effectiveFrom:t,sourceSha256:'b'.repeat(64),basis:'observed-as-of'}}));}
test('a 15-second executable profit window counts despite a later reversal, with both fees and actual depth',()=>{
 const up=oracleProfitWindows([f],books(),t+30000).find(x=>'direction'in x&&x.direction==='up')!;
 assert.equal(up.status,'observed-15s-profit-window');assert.equal('confirmedAt'in up&&up.confirmedAt,t+20000);
 assert.ok('bestObservedNetUsd'in up&&Math.abs(up.bestObservedNetUsd!-.31)<1e-8);
 const thin=books(); for(const b of thin)if(b.quote.knownAt>t)b.quote.bids[0].size=1;
 assert.notEqual(oracleProfitWindows([f],thin,t+30000)[0].status,'observed-15s-profit-window');
});
test('gaps, brief or fee-negative opportunities and pending targets cannot become confirmed windows',()=>{
 assert.equal(oracleProfitWindows([f],books(true),t+30000)[0].status,'incomplete-coverage');
 const low=books();for(const b of low)if(b.quote.knownAt>t)b.quote.bids[0].price=.42;
 assert.equal(oracleProfitWindows([f],low,t+30000)[0].status,'no-observed-15s-window');
 assert.equal(oracleProfitWindows([f],books().slice(0,2),t+5000)[0].status,'pending');
});
test('remaining contract time supplies a shorter label window without borrowing terminal confidence',()=>{
 const shorter=books();for(const b of shorter)b.contract.closeTime=t+60000;
 const long={...f,horizon:60,byAt:t+3600000} as EdgeForecast;
 const row=oracleProfitWindows([long],shorter,t+30000)[0];
 assert.equal(row.status,'observed-15s-profit-window');assert.equal('remainingWindowMs'in row&&row.remainingWindowMs,30000);
});
test('stale and crossed entry snapshots cannot create opportunity labels',()=>{
 const bad=books();for(const b of bad)b.quote.at-=3000;
 assert.equal(oracleProfitWindows([f],bad,t+30000)[0].status,'no-eligible-entry');
 for(const b of bad){b.quote.at=b.quote.knownAt;b.quote.bids[0].price=.9;}
 assert.equal(oracleProfitWindows([f],bad,t+30000)[0].status,'no-eligible-entry');
});
