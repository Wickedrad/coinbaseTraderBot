// Heat entry lane: the contract between the curve reader and the bot (edge plan E01 / E07 / decision 8).
//
// A "heat source" publishes, per coin, the curve rows that FIRED at the last closed bar: each row is one cell of the
// oracle's direction table (python/oracle, run id in `run`) with its called side, its rank in the traded pack and its
// strength on the check period. The reader computes the TA readings (same code as the oracle run) outside the bot and
// writes one small JSON file a minute (HeatCallsFile); the bot only reads it. The lane (heatLane.ts) turns fired rows
// into at most one immediate-or-cancel entry per coin, through the engine's placeChecked, in paper and live alike.
//
// Nothing here is a settlement probability: a row says which way the coin tended to move over `h` minutes after the
// bar closed, how often (share), and how hot it is (rank). The lane's entries are judged by the project's one test
// (the called side's bid stays above cost plus fees long enough to sell), not by a fair value.

/** One fired row of the traded pack, as the reader publishes it. */
export interface HeatCallRow {
  /** The row's key in the direction table, e.g. `15m:RSI14=very low` (pairs and triples: the pack's own row key). */
  key: string;
  kind: 'single' | 'pair' | 'triple';
  /** Other names of the same event (identical samples under two readings, e.g. RSI14 and CMO14): one row, one bet. */
  aliases?: string[];
  /** The trigger reading's key for a pair or triple (the single it refines); absent on a single. */
  trig?: string;
  /** Timeframe of the trigger reading's bars, minutes: 1, 5, 15 or 60. */
  tf: number;
  /** Horizon in minutes the row's direction was measured over: 15 and 60 (the traded and pair packs), 240 and 1440 (the
   *  perp packs: perps only, never a Kalshi contract). */
  h: number;
  /** The called side of the coin: +1 up, -1 down. */
  dir: 1 | -1;
  /** Rank by heat among the coin's event levels at this horizon (the pack's rank_coin), 1 = hottest. */
  rank: number;
  /** How many of the coin's hottest levels the pack lists for this horizon (the pack's `top`). A row listed only for
   *  its share right can carry a rank above this. */
  of: number;
  /** Heat on the check period (windows per day x odds points). */
  heat: number;
  /** Share of events that went the called way on the check period, 0..1. */
  share: number;
  /** Odds shift on the check period, in points (P(called side) - P(other side) against the base, halved). */
  odds: number;
  /** Minutes the direction usually held, the usual wrong-way dip (bps) and the move on the called side (bps). */
  hold?: number;
  dip?: number;
  move?: number;
  /** Close time (ms) of the trigger bar: the reading is known from here and the measured entry is the next minute's open. */
  barClose: number;
}

export interface HeatCoinCalls {
  /** Close time (ms) of the last closed 1-minute bar the reader used for this coin. */
  asOf: number;
  /** SHA-256 of the coin's frozen heat table (meta.json table_sha256). */
  tableSha: string;
  /** false = the reader cannot vouch for this coin right now (minute gaps, a short window, a failed fetch): no entries. */
  ok: boolean;
  why?: string;
  calls: HeatCallRow[];
}

/** The file the reader writes atomically once a minute (HEAT_CALLS_FILE). */
export interface HeatCallsFile {
  v: 1;
  /** Which curves: 'oracle-heat' for the oracle direction curves. */
  source: string;
  /** The run the tables come from (GitHub run id of the oracle heat run). */
  run: string;
  /** SHA-256 of the traded pack the reader joined the fired keys with. */
  packSha: string;
  writtenAt: number;
  coins: Record<string, HeatCoinCalls>;
}

/** What a source hands the lane: the latest file, parsed and checked. */
export interface HeatSnapshot {
  source: string;
  run: string;
  packSha: string;
  writtenAt: number;
  coins: Map<string, HeatCoinCalls>;
}

export interface HeatSourceStatus {
  ok: boolean;
  why?: string;
  writtenAt?: number;
  ageMs?: number;
  coins?: Record<string, { ok: boolean; asOf: number; calls: number; why?: string }>;
}

/** The lane's only view of the curves. File-backed on the server, in-memory in tests, a recorded stream in a replay. */
export interface HeatSource {
  /** The newest snapshot, or undefined when there is none or it cannot be trusted (missing, unreadable, wrong version). */
  read(now: number): HeatSnapshot | undefined;
  status(now: number): HeatSourceStatus;
}

/** Settings (config.heat). One set for paper and live: the lane has no mode branch except the live pilot budget. */
export interface HeatConfig {
  /** HEAT_LANE: master switch. Off = no heat entries; open heat positions keep their exits. */
  enabled: boolean;
  /** HEAT_CALLS_FILE: the reader's file. */
  callsFile: string;
  /** HEAT_ASSETS: coins the lane trades (never DOGE). */
  assets: string[];
  /** HEAT_HORIZONS: horizons that open contracts: 15 = the 15-minute contract, 60 = the hourly contract. The perps
   *  horizons (240, 1440) are refused here at config load: no Kalshi contract trades them. */
  horizons: number[];
  /** HEAT_TOP_N: only rows ranked this or hotter trade (the pack's batch size); 0 = every row in the pack. */
  topN: number;
  /** HEAT_MAX_AGE_SEC: a coin whose last closed minute is older than this gives no entries (reader stalled). A file
   *  written more than twice this long ago is ignored altogether. */
  maxAgeSec: number;
  /** HEAT_ENTRY_LAG_SEC: a fired row opens an entry only this long after its bar closed. */
  entryLagSec: number;
  /** HEAT_SIZING: stake = ORDER_USD_MIN + w x (ORDER_USD_MAX - ORDER_USD_MIN) by heat rank; off = flat ORDER_USD_MIN. */
  sizing: boolean;
  /** HEAT_CONTEXT: how the hour's direction acts on a 15-minute contract entry: 'size' (agree = hotter, against =
   *  ORDER_USD_MIN), 'block' (against = no entry), 'off'. */
  context: 'size' | 'block' | 'off';
  /** HEAT_CONTEXT_BOOST: weight added when the hour agrees (0..1). */
  contextBoost: number;
  /** HEAT_MAX_OPEN: open heat positions across all coins (decision 8: the hottest at heat size, the next at
   *  ORDER_USD_MIN, no third; hourly positions count). */
  maxOpen: number;
  /** HEAT_MAX_PER_COIN: open heat positions per coin across the 15-minute and hourly contracts. */
  maxPerCoin: number;
  /** HEAT_COOLDOWN_SEC: wait after a heat exit before a new heat entry on the same coin. */
  cooldownSec: number;
  /** Re-entry after a loss (Steven, Nov 11 6:59 PM EST / 23:59 UTC, and his card at 7:05 PM EST / 00:05 UTC): "That amount
   *  doesn't invalidate a signal", so a contract window the lane left at a loss (the loser cut, mostly) may be entered again
   *  on a fresh call, at most this many times. HEAT_REENTRIES_15M (default 3; Steven, 8:08 PM EST / 01:08 UTC): a 15-minute contract. 0 = never again. */
  reentries15m: number;
  /** HEAT_REENTRIES_HOURLY (default 6): an hourly window, all of its strikes together. 0 = never again. */
  reentriesHourly: number;
  /** HEAT_REENTRY_LOSS_STOP (default 0.5): no more re-entries once the window's losses reach this share of one order (the
   *  largest stake the lane lost there). 0 = off. */
  reentryLossStop: number;
  /** HEAT_FLAT_TRIPS: the book's first N heat round trips trade ORDER_USD_MIN with one position at a time (decision 11). */
  flatTrips: number;
  /** HEAT_PILOT_LOSS_USD: live only: heat entries stop once the live book's realized heat P&L reaches minus this
   *  (decision 6). 0 = off. Paper counts and reports it but never stops on it. */
  pilotLossUsd: number;
  /** HEAT_FEE_NET_CHECK: also require the row's odds to beat fee plus half the spread (the risk gateway's edge
   *  collar on the heat-implied value). Off by default: the proof standard is the one test, not a cost bar. */
  feeNetCheck: boolean;
  /** HEAT_PERPS: what the curves do on the perps (bot/setups/setupTrader.ts), only with HEAT_LANE on: 'log' journals the
   *  hour's, the 4 hours' and the day's direction beside every setup, 'gate' also keeps a 1h setup against the hour out,
   *  'entry' (default) also opens a setup of kind heat when a 60-minute or 240-minute call fires (HEAT_PERP_HORIZONS);
   *  'off' leaves the perps alone (and the lane then reads no 240- or 1440-minute rows). */
  perps: 'off' | 'log' | 'gate' | 'entry';
  /** HEAT_PERP_HORIZONS: the horizons whose calls open a perps heat setup (HEAT_PERPS=entry): 60 = on 1h, held to the next
   *  hourly close; 240 = on 4h, held to the next 4-hour close. Default both. */
  perpHorizons: number[];
  /** HEAT_PERPS_DAILY: the daily (1440-minute) call on the perps. 'context' (default): a heat perp entry against the
   *  coin's live daily call is not made; 'off': the lane reads no daily rows. Never an entry of its own: no daily row is
   *  above the no-signal twin's best (top heat 6.9 against the twin's 9.3). */
  perpsDaily: 'context' | 'off';
  /** HEAT_PAIR_CONFLICT: a refining pair or triple that calls the other side from the single it replaces: 'skip' (default)
   *  makes no entry ("pair against single"), 'pair' trades the pair's side. */
  pairConflict: 'skip' | 'pair';
  /** HEAT_DIAL: the evidence dial on the stake (Nov 12 2026, loss study lever 1). 'off' (default) = the stake as before;
   *  'log' = the plan records the stake the dial would have set (dialMult, dialStakeUsd) and trades the old stake, so fresh
   *  paper days can judge the dial against a plain shrink; 'on' = the dial sets the stake. It is a size, never a gate: every
   *  call still trades, at no less than HEAT_DIAL_FLOOR of ORDER_USD_MIN. */
  dial: 'off' | 'log' | 'on';
  /** HEAT_DIAL_PRIOR_TRIPS: the prior's weight in trips for a coin and side with no record. */
  dialPriorTrips: number;
  /** HEAT_DIAL_PRIOR_RETURN: the prior's return per dollar staked (a loss is negative). */
  dialPriorReturn: number;
  /** HEAT_DIAL_SCALE: the stake multiplier is 1 + mean return / scale, so a mean of minus this much is the floor. */
  dialScale: number;
  /** HEAT_DIAL_FLOOR: the smallest multiplier, as a share of the stake; the stake is never below this share of ORDER_USD_MIN. */
  dialFloor: number;
  /** HEAT_DIAL_MAX: the largest multiplier (the stake still stops at ORDER_USD_MAX). */
  dialMax: number;
}

/** A coin's decided call at one horizon: the hottest firing row (a pair or triple replaces the single it refines). */
export interface HeatDecided {
  asset: string;
  h: number;
  row: HeatCallRow;
  /** Rows that fired for this coin and horizon this minute, and how many called the other side. */
  fired: number;
  against: number;
  /** The decided single a pair or triple replaced (`row` is then the refinement, with the hotter of the two ranks). */
  single?: HeatCallRow;
}

/** A coin's direction at one horizon: its latest decided call, valid until `until` (the bar close plus the horizon). The
 *  hour's direction (60 minutes) sizes the 15-minute contract and gates the perps; the 4 hours' (240) and the day's
 *  (1440) are the perps' only. */
export interface HeatContext {
  asset: string;
  dir: 1 | -1;
  key: string;
  rank: number;
  of: number;
  heat: number;
  barClose: number;
  until: number;
}

/** A market the lane may enter, as the engine shows it. Prices are YES prices, 0..1. */
export interface HeatMarketView {
  ticker: string;
  asset: string;
  kind: '15m' | 'hourly';
  closeTs: number;
  openTs?: number;
  yesBid?: number;
  yesAsk?: number;
  /** Signed YES contracts held (any lane). */
  position: number;
  /** Resting or in-flight orders of ours on this market (any lane). */
  working: number;
  /** A reason the market cannot take an entry now (fee schedule unverified, evaluation in flight, re-entry rule ...). */
  blocked?: string;
}

/** An open (or just sent) heat position, kept in the lane's book state. */
export interface HeatOpen {
  ticker: string;
  asset: string;
  kind: '15m' | 'hourly';
  side: 'yes' | 'no';
  ruleId: string;
  h: number;
  sentAt: number;
  /** Set once the position was seen open. */
  openedAt?: number;
  stakeUsd: number;
  closeTs: number;
  /** The market's net cash and fees when the entry was sent: the round trip's P&L is the change from here. */
  cash0: number;
  fees0: number;
}

/** What the lane wants sent for one coin this minute. */
export interface HeatPlan {
  asset: string;
  ticker: string;
  kind: '15m' | 'hourly';
  h: number;
  /** 'yes' = buy YES at the ask, 'no' = buy NO (sell YES at the bid). */
  side: 'yes' | 'no';
  /** YES price of the order (the touch): the YES ask for 'yes', the YES bid for 'no'. */
  price: number;
  /** What a contract of the called side costs at the touch. */
  sideCost: number;
  count: number;
  stakeUsd: number;
  /** Heat weight 0..1 after the hour context. */
  weight: number;
  /** HEAT_DIAL log/on: the dial's multiplier and the stake it sets for this plan (stakeUsd is that stake only when 'on'). */
  dialMult?: number;
  dialStakeUsd?: number;
  /** 1 = the hottest slot (heat size), 2 = the second slot (ORDER_USD_MIN). */
  slot: 1 | 2;
  context: 'agree' | 'against' | 'none' | 'n/a';
  /** Heat-implied YES value for the order record: YES mid moved by the row's odds toward the called side. */
  fair: number;
  ruleId: string;
  row: HeatCallRow;
  why: string;
}

export interface HeatSkip {
  asset: string;
  h: number;
  ticker?: string;
  key?: string;
  reason: string;
}

/** The persisted part of the lane, one file per book (paper and live each keep their own). */
export interface HeatBookState {
  v: 1;
  /** Finished heat round trips. */
  trips: number;
  wins: number;
  /** Realized heat P&L of the book, net of fees. */
  pnl: number;
  open: HeatOpen[];
  /** Per coin: when its last heat position closed. */
  lastExit: Record<string, number>;
  /** Contracts the lane left at a loss (ticker -> close time), pruned once the contract is over. */
  lossTickers: Record<string, number>;
  /** Per coin: the hour's direction. */
  context: Record<string, HeatContext>;
  /** Per coin: the 4 hours' and the day's direction (the perps' context). Absent in a file written before the perp packs:
   *  read as empty. */
  four?: Record<string, HeatContext>;
  day?: Record<string, HeatContext>;
  /** Calls already acted on: `${asset}:${h}:${barClose}` -> barClose, pruned after two hours. */
  acted: Record<string, number>;
  /** The dial's record per `${asset}:${side}`: finished round trips and the sum of their returns per dollar staked
   *  (P&L over the order's stake). Absent in a file written before the dial: read as empty. */
  seg?: Record<string, HeatSegment>;
}

/** What the lane has earned on one coin and side: n round trips, r the sum of pnl / stakeUsd. */
export interface HeatSegment { n: number; r: number }

/** What the engine is handed for the lane (EngineDeps.heat). `tag` and `untag` belong to the exits' owner (the plan
 *  positions): with no `tag` the lane does not enter, because an untagged position would be sold by the old model's exit. */
export interface HeatHooks {
  /** Called BEFORE the entry order goes out, so a fill that arrives later is already a plan position. */
  tag?: (t: HeatTag, now: number) => void;
  /** Called when the entry filled nothing: the tag must not wait for an old-lane fill on the same market. */
  untag?: (ticker: string) => void;
  /** A reason new heat entries are not allowed now (the soft pause, the hard stop), else undefined. */
  entryGate?: () => string | undefined;
  /** The exits' re-entry rule for a market (holdExits.reentryBlock): seconds to close and the window's length in. */
  reentryBlock?: (ticker: string, tauSec: number, windowSec: number | undefined) => string | undefined;
}

/** The exits' owner tags a heat position so the plan's exits manage it (bot/plan/planPositions.ts PlanTag has this shape). */
export interface HeatTag {
  ticker: string;
  side: 'yes' | 'no';
  ruleId: string;
  openedAt?: number;
  settings?: Record<string, unknown>;
}

/** What the perps side asks the lane (bot/setups/setupTrader.ts). An implementation never throws. */
export interface HeatDirection {
  /** The hour's direction for a coin: its latest decided 60-minute call still inside its hour, else undefined. */
  hour(asset: string, now: number): HeatContext | undefined;
  /** The coin's decided call at horizon `h` (60 or 240 for the perps) that fired within the entry lag, else undefined. */
  fired(asset: string, h: number, now: number): HeatDecided | undefined;
  /** The 4 hours' direction: the latest decided 240-minute call while its bar close plus 240 minutes is still ahead. */
  four(asset: string, now: number): HeatContext | undefined;
  /** The day's direction: the latest decided 1440-minute call while its bar close plus 1440 minutes is still ahead;
   *  always undefined with HEAT_PERPS_DAILY=off. */
  day(asset: string, now: number): HeatContext | undefined;
}
