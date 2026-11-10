/** Observed executable-profit labels, separate from terminal-direction probabilities and funded P/L. */
import { orderFee } from '../../bot/fees';
import type { EdgeForecast } from './oracleEdge';
import type { PaperFeeTerms, SnapshotEvidence } from './directionPaper';
import type { TimedPriceContract } from './contractTiming';
export const PROFIT_WINDOW_POLICY = Object.freeze({ id: 'oracle-observed-profit-15s-v1', sustainMs: 15000, maximumGapMs: 7500,
  maximumQuoteAgeMs: 2000, maximumEntryDelayMs: 90000, maximumPositionCost: 20, maximumContracts: 40, minimumNetUsd: 0.01, saleBufferMs: 30000 });
export interface ProfitWindowBook { contract: TimedPriceContract; quote: SnapshotEvidence; fees: PaperFeeTerms }
export function oracleProfitWindows(forecasts: EdgeForecast[], books: ProfitWindowBook[], endedAt: number) {
  const ordered = [...books].sort((a,b) => a.quote.knownAt-b.quote.knownAt);
  const usable = (b: ProfitWindowBook) => b.quote.at <= b.quote.knownAt && b.quote.knownAt-b.quote.at <= 2000 && b.quote.knownAt <= endedAt &&
    [...b.quote.bids,...b.quote.asks].every(l=>Number.isFinite(l.price)&&l.price>0&&l.price<1&&Number.isFinite(l.size)&&l.size>=0) &&
    b.fees.knownAt <= b.quote.knownAt && b.fees.effectiveFrom <= b.quote.knownAt && b.contract.termsKnownAt <= b.quote.knownAt &&
    !(b.quote.bids.length && b.quote.asks.length && Math.max(...b.quote.bids.map(l=>l.price)) >= Math.min(...b.quote.asks.map(l=>l.price)));
  return forecasts.flatMap(f => {
    const first = ordered.find(b => usable(b) && b.contract.asset===f.asset && ['greater','less','updown'].includes(b.contract.terms.kind) &&
      b.contract.openTime<=b.quote.knownAt && b.quote.knownAt>=f.publishedAt && b.quote.knownAt-f.publishedAt<=90000 &&
      Math.min(f.byAt,b.contract.closeTime-30000)>b.quote.knownAt && b.quote.bids.length && b.quote.asks.length);
    if(!first) return [{forecastId:f.id, horizon:f.horizon, status:'no-eligible-entry' as const}];
    return (['up','down'] as const).map(direction => {
      const yes=(direction==='up') !== (first.contract.terms.kind==='less'), side=yes?'yes':'no';
      const levels=(yes?first.quote.asks:first.quote.bids).map(l=>({price:yes?l.price:1-l.price,size:l.size})).sort((a,b)=>a.price-b.price);
      const entry=levels[0]; let quantity=Math.min(40,Math.floor(entry.size),Math.floor(20/entry.price));
      while(quantity>0 && quantity*entry.price+orderFee(quantity,entry.price,true,first.fees.schedule)>20)quantity--;
      const basis=quantity*entry.price+orderFee(quantity,entry.price,true,first.fees.schedule), deadline=Math.min(f.byAt,first.contract.closeTime-30000);
      let since:number|null=null, confirmedAt:number|null=null, firstProfitAt:number|null=null, last=first.quote.knownAt, maximumGap=0, samples=0;
      let verified=first.fees.basis==='observed-as-of', bestNet:number|null=null;
      for(const b of ordered) {
        if(b.contract.ticker!==first.contract.ticker || b.quote.knownAt<=first.quote.knownAt || b.quote.knownAt>deadline)continue;
        const at=b.quote.knownAt; maximumGap=Math.max(maximumGap,at-last);
        if(at-last>7500)since=null;
        last=at;
        if(!usable(b)){since=null;continue;}
        verified &&= b.fees.basis==='observed-as-of'; samples++;
        const exits=(yes?b.quote.bids:b.quote.asks).map(l=>({price:yes?l.price:1-l.price,size:l.size})).sort((a,b)=>b.price-a.price);
        const exit=exits[0], net=quantity>0 && exit && exit.size>=quantity ? quantity*exit.price-orderFee(quantity,1-exit.price,true,b.fees.schedule)-basis : null;
        if(net!==null)bestNet=Math.max(bestNet??-Infinity,net);
        if(net!==null && net>=0.01-1e-9){firstProfitAt??=at; since??=at;if(at-since>=15000)confirmedAt??=at;}else since=null;
      }
      const coverageEnd=Math.min(deadline,endedAt); maximumGap=Math.max(maximumGap,coverageEnd-last);
      return {forecastId:f.id,horizon:f.horizon,direction,side,ticker:first.contract.ticker,entryAt:first.quote.knownAt,deadline,remainingWindowMs:deadline-first.quote.knownAt,quantity,entryBasisUsd:basis,
        firstProfitAt,confirmedAt,bestObservedNetUsd:bestNet,samples,maximumGapMs:maximumGap,verifiedFees:verified,
        status:quantity===0?'no-funded-depth':confirmedAt!==null?'observed-15s-profit-window':endedAt<deadline?'pending':maximumGap>7500?'incomplete-coverage':'no-observed-15s-window'};
    });
  });
}
