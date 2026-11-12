import type { Candle } from '../../bot/ta/indicators';

/** Canonical observed OHLCV only. Missing taker-buy volume stays unknown. */
export function parseMinuteCsv(line: string): Candle | undefined {
  if (!line || line.startsWith('ts,')) return undefined;
  const z = line.split(',');
  if (z.length !== 6 && z.length !== 7) return undefined;
  const [ts, o, h, l, c, v] = z.slice(0, 6).map(Number);
  if (z.slice(0, 6).some((s) => !s.trim()) || ![ts, o, h, l, c, v].every(Number.isFinite) ||
      ts < 0 || ts % 60000 !== 0 || Math.min(o, h, l, c) <= 0 || h < Math.max(o, c) || l > Math.min(o, c) || v < 0) return undefined;
  const tb = z[6]?.trim() ? Number(z[6]) : undefined;
  if (tb !== undefined && (!Number.isFinite(tb) || tb < 0 || tb > v + 1e-9)) return undefined;
  return { ts, o, h, l, c, v, ...(tb === undefined ? {} : { tb }) };
}
