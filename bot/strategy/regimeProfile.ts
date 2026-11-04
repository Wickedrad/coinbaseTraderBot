// Volatility-regime profiles (untouched-levers lab, Nov 4; Steven's dynamics rule of Nov 1: a setting that earns in some
// market conditions and not in others is switched by condition, not cut). The coin's 1-hour realised volatility (the market
// state's rv1h, the same reading DYN_EDGE uses) puts each evaluation in a regime:
//
//   calm    rv1h <  VOLREG_RV1H lo        -> the strategy settings with VOLREG_CALM applied
//   normal  lo <= rv1h <= hi              -> with VOLREG_NORMAL applied
//   wild    rv1h >  hi                    -> with VOLREG_WILD applied
//
// A profile is "KEY=VALUE+KEY=VALUE" over any STRATEGY-section setting (VOL_FALLBACK_MULT, STRATEGY_KAPPA, STRATEGY_STYLE,
// STRATEGY_MIN_EDGE, HOURLY_MID_BAND, FV_ENTRY_GATE_MARGIN, ...), parsed by loadConfig into a full strategy config, so a
// regime's settings are validated exactly as the bot's own are. It switches what the engine reads per evaluation (pricing
// sigma, edge, gates, windows, sizing inputs); objects built once at startup from the settings (the pacer, the cadence gate,
// the accuracy gate's scorecard) keep the bot's own values. The reading used is the coin's last one (the previous
// evaluation's), so classifying never touches the market state's cache. No VOLREG_RV1H = no regimes, nothing changes.
// One function for the engine and the backtester (research/backtest.ts), so paper, live and the replay switch alike.
import type { Config, StrategyConfig } from '../config';

export type VolRegime = 'calm' | 'normal' | 'wild';

export interface VolRegimeProfiles {
  /** [lo, hi] rv1h bounds (the market state's 1-hour realised volatility per 1-minute return). */
  rv1h: [number, number];
  calm?: StrategyConfig;
  normal?: StrategyConfig;
  wild?: StrategyConfig;
}

export function volRegime(rv1h: number | null | undefined, bounds: [number, number]): VolRegime | undefined {
  if (rv1h === null || rv1h === undefined || !Number.isFinite(rv1h)) return undefined;
  return rv1h < bounds[0] ? 'calm' : rv1h > bounds[1] ? 'wild' : 'normal';
}

/** The strategy settings for a coin whose last rv1h reading is `rv1h`: its regime's profile, else the bot's own (same object). */
export function regimeStrategy(s: StrategyConfig, rv1h: number | null | undefined): StrategyConfig {
  const p = s.volRegime;
  if (!p) return s;
  const r = volRegime(rv1h, p.rv1h);
  return (r && p[r]) || s;
}

/** The whole config with the regime's strategy settings (the same object when no profile applies). */
export function regimeConfig<C extends Pick<Config, 'strategy'>>(cfg: C, rv1h: number | null | undefined): C {
  const s = regimeStrategy(cfg.strategy, rv1h);
  return s === cfg.strategy ? cfg : { ...cfg, strategy: s };
}

/** "KEY=VALUE+KEY=VALUE" -> { KEY: VALUE }; undefined for an empty string. Keys must be upper-case setting names. */
export function parseProfile(raw: string | undefined, key: string): Record<string, string> | undefined {
  const s = (raw ?? '').trim();
  if (!s) return undefined;
  const out: Record<string, string> = {};
  for (const part of s.split('+').map((x) => x.trim()).filter(Boolean)) {
    const i = part.indexOf('=');
    const k = i > 0 ? part.slice(0, i).trim() : '';
    if (!/^[A-Z][A-Z0-9_]*$/.test(k) || k.startsWith('VOLREG_')) throw new Error(`${key}=${raw}: "${part}" must be SETTING=value (VOLREG_* not allowed inside a profile)`);
    out[k] = part.slice(i + 1).trim();
  }
  return out;
}
