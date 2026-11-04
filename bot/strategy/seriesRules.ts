// Per-series rules (untouched-levers lab, Nov 4): a series that keeps losing gets a higher bar or no new entries, the
// rest trade as before. Shared by the engine and the backtester (research/backtest.ts) so paper, live and the replay agree.
// The series is the ticker's first part (KXBTCD-26OCT2802-T80799.99 -> KXBTCD), the same in recordings and live.

export interface SeriesRules {
  seriesEdgeAdd: Record<string, number>;
  seriesNoEntry: string[];
}

export function seriesOf(ticker: string): string {
  const i = ticker.indexOf('-');
  return (i > 0 ? ticker.slice(0, i) : ticker).toUpperCase();
}

/** Extra minimum edge (dollars per contract) for this market's series; 0 when no rule names it. */
export function seriesEdgeAdd(r: Pick<SeriesRules, 'seriesEdgeAdd'> | undefined, ticker: string): number {
  const add = r?.seriesEdgeAdd?.[seriesOf(ticker)];
  return add !== undefined && Number.isFinite(add) && add > 0 ? add : 0;
}

/** True when the series takes no new entries (exits and settlement go on). */
export function seriesBlocked(r: Pick<SeriesRules, 'seriesNoEntry'> | undefined, ticker: string): boolean {
  return Boolean(r?.seriesNoEntry?.length) && r!.seriesNoEntry.includes(seriesOf(ticker));
}
